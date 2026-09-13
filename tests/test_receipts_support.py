"""الفحص الآلي للإيصالات (المحرك 2) · تذاكر الدعم على بوت المنصة · أسرار المنصة لا تصل المتصفح.
كل الشبكة مستبدَلة، وقراءة الصور (OCR) مستبدَلة بنص جاهز — لا حاجة لـ tesseract.
    python tests/test_receipts_support.py
"""
import asyncio, io, json, os, sys, tempfile, unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_TMP = tempfile.mkdtemp(prefix="botyalla-receipts-")
os.environ["BOTYALLA_DB"] = os.path.join(_TMP, "t.db")        # قبل أي استيراد
os.environ["BOTYALLA_UPLOADS"] = _TMP
os.environ["BOTYALLA_LOGS"] = _TMP

import database as db          # noqa: E402
import payments as pay         # noqa: E402
import platform_bot as PB      # noqa: E402
import support_desk as SD      # noqa: E402
import app as A                # noqa: E402
from bot_manager import manager  # noqa: E402

CS = "r" * 32
NUMBER = "01097585951"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 4096


def img():
    """بصمة مختلفة لكل رفع — لإعادة الاستخدام اختباره الخاص."""
    return PNG + os.urandom(16)


# لقطة فودافون كاش كما يقرؤها OCR: أرقام عربية وتاريخ ورقم عملية
GOOD = ("تم تحويل مبلغ {amt} جنيه بنجاح إلى رقم ٠١٠٩٧٥٨٥٩٥١\n"
        "رقم العملية 55667788 التاريخ 13/09/2026 10:45")


class EngineTests(unittest.TestCase):
    REFS = [NUMBER, "botyalla@instapay"]

    def test_an_arabic_vodafone_cash_receipt_matches(self):
        r = pay.analyze(GOOD.format(amt="٢٩٩٫٠٠"), 299, self.REFS)
        self.assertTrue(r["receipt"])
        self.assertTrue(r["amount_found"], "الأرقام العربية لم تُقرأ")
        self.assertEqual(r["recipient"], "full")

    def test_instapay_masked_number_and_thousands(self):
        txt = "InstaPay\nTransfer successful\nAmount EGP 1,299.00\nTo 010*****951\nReference 7788991122"
        r = pay.analyze(txt, 1299, self.REFS)
        self.assertTrue(r["amount_found"])
        self.assertEqual(r["recipient"], "masked")

    def test_spaced_phone_and_instapay_handle(self):
        self.assertEqual(pay.analyze("sent to 010 9758 5951", 1, [NUMBER])["recipient"], "full")
        self.assertEqual(pay.analyze("to: BotYalla@InstaPay", 1, self.REFS)["recipient"], "full")

    def test_phone_and_reference_digits_are_not_the_amount(self):
        r = pay.analyze("Transfer successful EGP to 01029912345 ref 299001", 299, self.REFS)
        self.assertFalse(r["amount_found"])

    def test_a_transfer_to_someone_else_is_detected(self):
        r = pay.analyze("تم تحويل 299 جنيه بنجاح إلى 01111111111 رقم العملية 123456", 299, self.REFS)
        self.assertEqual(r["recipient"], "none")

    def test_a_photo_is_not_a_receipt(self):
        self.assertFalse(pay.analyze(" ~ . , ", 299, self.REFS)["receipt"])


class DecisionTests(unittest.TestCase):
    def check(self, text, prior=0, dup=False):
        orig = pay.read_text
        pay.read_text = lambda _d: text
        try:
            return pay.auto_check(img(), 299, [NUMBER], duplicate=dup, prior_refusals=prior)
        finally:
            pay.read_text = orig

    def test_a_valid_receipt_passes_but_is_never_final(self):
        ac = self.check(GOOD.format(amt="299"))
        self.assertEqual((ac["verdict"], ac["refuse"]), ("auto_pass", False))

    def test_a_photo_is_refused_even_after_retries(self):
        for prior in (0, 5):
            ac = self.check("", prior)
            self.assertEqual((ac["verdict"], ac["reason"], ac["refuse"]), ("reject", "not_receipt", True))

    def test_wrong_recipient_is_refused_then_escalated(self):
        bad = GOOD.format(amt="299").replace("٠١٠٩٧٥٨٥٩٥١", "01111111111")
        self.assertTrue(self.check(bad)["refuse"])
        ac = self.check(bad, prior=pay.RETRY_AFTER)
        self.assertEqual((ac["verdict"], ac["refuse"], ac["retries"]), ("suspect", False, pay.RETRY_AFTER))

    def test_wrong_amount_is_refused(self):
        ac = self.check(GOOD.format(amt="150"))
        self.assertEqual((ac["reason"], ac["refuse"]), ("amount_mismatch", True))

    def test_a_reused_receipt_is_refused(self):
        ac = self.check(GOOD.format(amt="299"), dup=True)
        self.assertEqual((ac["reason"], ac["refuse"]), ("duplicate", True))

    def test_without_ocr_nothing_is_refused(self):
        ac = self.check(None)
        self.assertEqual((ac["verdict"], ac["refuse"]), ("needs_review", False))
        self.assertTrue(ac["ocr_off"])

    def test_admin_lines_render_every_shape(self):
        for ac in (self.check(GOOD.format(amt="299")), self.check(""), self.check(None),
                   {"image": {"ok": True, "kind": "png"}, "ocr": {"amount_found": True, "ref_found": False}}):
            for lang in ("ar", "en"):
                lines = pay.check_lines(ac, lang)
                self.assertTrue(lines and all("text" in x for x in lines))


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        db.init_db()
        with db.get_conn() as c:
            c.execute("INSERT OR IGNORE INTO users(id,username,pw_hash,role,created_at) VALUES(1,'root','x','admin',0)")
            c.execute("INSERT OR IGNORE INTO users(username,pw_hash,role,created_at) VALUES('payer','x','user',0)")
            c.execute("INSERT OR IGNORE INTO users(username,pw_hash,role,created_at) VALUES('nosy','x','user',0)")
        cls.uid = db.get_user_by_name("payer")["id"]
        cls.other = db.get_user_by_name("nosy")["id"]
        db.set_platform("vodafone_number", NUMBER)
        db.set_platform("admin_chat_id", "999")
        cls.alerts, cls.notes = [], []
        manager.send_payment_alert = lambda *a, **k: cls.alerts.append(a) or 77
        manager.notify_text = lambda *a, **k: cls.notes.append((a, k)) or True
        manager.platform_info = lambda: {}

    def setUp(self):
        A._login_attempts.clear()
        self.alerts.clear()
        self.notes.clear()

    @staticmethod
    def client(uid):
        c = A.app.test_client()
        with c.session_transaction() as s:
            s["uid"] = uid; s["_csrf"] = CS
        return c


class ReceiptRouteTests(Base):
    def setUp(self):
        super().setUp()
        with db.get_conn() as c:
            c.execute("DELETE FROM payments")
            c.execute("DELETE FROM receipt_refusals")
        self.c = self.client(self.uid)
        self._orig = pay.read_text
        with A.app.test_request_context():
            self.total = A.quote("merchant", self.uid)["total"]

    def tearDown(self):
        pay.read_text = self._orig

    def send(self, text, data=None):
        pay.read_text = lambda _d: text
        return self.c.post("/subscribe/merchant", content_type="multipart/form-data",
                           data={"method": "vodafone", "ref": "R", "csrf_token": CS,
                                 "screenshot": (io.BytesIO(data or img()), "r.png")})

    def good(self):
        return GOOD.format(amt=f"{self.total:g}")

    def test_a_photo_is_refused_before_anything_is_stored(self):
        before = set(os.listdir(A.UPLOAD_DIR))
        self.send("")
        self.assertEqual(db.list_payments(self.uid), [])
        self.assertEqual(set(os.listdir(A.UPLOAD_DIR)), before, "الصورة المرفوضة اتكتبت على القرص")
        self.assertEqual(self.alerts, [], "الأدمن اتنبّه لصورة مرفوضة")
        self.assertEqual(db.count_receipt_refusals(self.uid), 1)

    def test_a_real_receipt_reaches_the_admin_but_stays_pending(self):
        self.send(self.good())
        p = db.list_payments(self.uid)[0]
        self.assertEqual(json.loads(p["auto_check"])["verdict"], "auto_pass")
        self.assertEqual(p["status"], "pending", "اتفعّل من غير موافقة الأدمن")
        self.assertEqual(len(self.alerts), 1)

    def test_wrong_recipient_is_refused_twice_then_reaches_the_admin_flagged(self):
        bad = self.good().replace("٠١٠٩٧٥٨٥٩٥١", "01111111111")
        self.send(bad); self.send(bad)
        self.assertEqual(db.list_payments(self.uid), [])
        self.send(bad)
        ac = json.loads(db.list_payments(self.uid)[0]["auto_check"])
        self.assertEqual((ac["verdict"], ac["retries"]), ("suspect", 2))

    def test_a_receipt_in_a_live_request_cannot_be_reused_but_a_rejected_one_can(self):
        data = img()
        self.send(self.good(), data)
        self.send(self.good(), data)
        pays = db.list_payments(self.uid)
        self.assertEqual(len(pays), 1, "نفس الإيصال اتقبل مرتين")
        db.finalize_payment(pays[0]["id"], "rejected")
        self.send(self.good(), data)
        self.assertEqual(len(db.list_payments(self.uid)), 2)

    def test_without_ocr_the_receipt_waits_for_the_admin(self):
        self.send(None)
        ac = json.loads(db.list_payments(self.uid)[0]["auto_check"])
        self.assertEqual(ac["verdict"], "needs_review")

    def test_wallet_topup_uses_the_same_check(self):
        pay.read_text = lambda _d: ""
        self.c.post("/wallet/topup", content_type="multipart/form-data",
                    data={"amount": "250", "method": "vodafone", "csrf_token": CS,
                          "screenshot": (io.BytesIO(img()), "r.png")})
        self.assertEqual(db.list_payments(self.uid), [])


class SecretsTests(Base):
    def test_customer_pages_never_ship_platform_secrets(self):
        for k, v in (("platform_bot_token", "123456:PLATFORMSECRET"), ("wa_app_secret", "WASECRET42"),
                     ("ai_key", "AIKEYSECRET")):
            db.set_platform(k, v)
        c = self.client(self.uid)
        for url in ("/subscribe/merchant", "/request-bot", "/wallet", "/support"):
            page = c.get(url).data.decode()
            for secret in ("PLATFORMSECRET", "WASECRET42", "AIKEYSECRET"):
                self.assertNotIn(secret, page, f"{secret} ظهر في {url}")
        # وسائل الدفع نفسها لازم تفضل ظاهرة في صفحتي الدفع
        for url in ("/subscribe/merchant", "/wallet"):
            self.assertIn(NUMBER, c.get(url).data.decode(), f"رقم الدفع اختفى من {url}")


class TicketTests(Base):
    def setUp(self):
        super().setUp()
        with db.get_conn() as c:
            c.execute("DELETE FROM tickets")
        self.c = self.client(self.uid)

    def open_ticket(self, body="البوت مش بيرد على العملاء من الصبح"):
        self.c.post("/support", data={"kind": "complaint", "subject": "البوت واقف",
                                      "body": body, "csrf_token": CS})
        ts = db.list_tickets(user_id=self.uid)
        return ts[0] if ts else None

    def test_a_ticket_reaches_the_admin_instantly(self):
        tk = self.open_ticket()
        self.assertEqual(tk["kind"], "complaint")
        (chat, text), kw = self.notes[-1]
        self.assertEqual(chat, "999")
        self.assertIn(f"#T{tk['id']}", text)
        self.assertIsNotNone(kw.get("reply_markup"), "تنبيه التذكرة بلا زرّ «تم الحل»")

    def test_a_too_short_message_is_refused(self):
        self.assertIsNone(self.open_ticket("hi"))

    def test_only_the_owner_sees_and_follows_up(self):
        tk = self.open_ticket()
        nosy = self.client(self.other)
        self.assertEqual(nosy.post(f"/support/{tk['id']}/reply",
                                   data={"body": "hello", "csrf_token": CS}).status_code, 404)
        self.assertNotIn("البوت واقف", nosy.get("/support").data.decode())
        self.assertIn(nosy.get("/admin/tickets").status_code, (302, 403, 404))

    def test_an_admin_web_reply_reaches_the_customer(self):
        tk = self.open_ticket()
        db.set_setting(self.uid, "tg_chat_id", "5555")
        self.client(1).post(f"/admin/tickets/{tk['id']}/reply",
                            data={"body": "اتحلت، جرّب دلوقتي", "csrf_token": CS})
        t2 = db.list_tickets(user_id=self.uid)[0]
        self.assertEqual((t2["status"], t2["msgs"][-1]["sender"]), ("answered", "staff"))
        self.assertTrue(any(a[0] == "5555" for a, _ in self.notes), "الرد ماوصلش تليجرام العميل")

    def _msg(self, uid, text, replied_to, out):
        class Msg:
            from_user = type("U", (), {"id": uid})()
            reply_to_message = type("R", (), {"text": replied_to, "caption": None})()
            async def reply_text(self, t, **k): out.append(t)
        m = Msg(); m.text = text
        return type("Up", (), {"message": m})()

    def test_a_telegram_reply_from_the_admin_is_saved_and_forwarded(self):
        tk = self.open_ticket()
        db.set_setting(self.uid, "tg_chat_id", "5555")
        sent, acks = [], []

        class Bot:
            async def send_message(self, chat_id, text, **k): sent.append((chat_id, text))
        ctx = type("C", (), {"bot": Bot()})()
        alert = SD.alert_text(db.get_ticket(tk["id"]), "…")
        asyncio.run(PB.on_admin_reply(self._msg(12345, "مش أدمن", alert, acks), ctx))
        self.assertEqual((sent, acks), ([], []), "رد من غير الأدمن اتقبل")
        asyncio.run(PB.on_admin_reply(self._msg(999, "اتحلت ✅", alert, acks), ctx))
        self.assertEqual(sent[0][0], 5555)
        self.assertIn("اتحلت ✅", sent[0][1])
        self.assertEqual(db.list_tickets(user_id=self.uid)[0]["msgs"][-1]["via"], "telegram")
        self.assertTrue(acks, "الأدمن ماعرفش إن رده اتبعت")

    def test_the_resolve_button_is_admin_only(self):
        tk = self.open_ticket()

        class Q:
            def __init__(self, uid):
                self.from_user = type("U", (), {"id": uid})()
                self.data = f"tk_close:{tk['id']}"
                self.message = type("M", (), {"text": "x"})()
            async def answer(self, *a, **k): pass
            async def edit_message_text(self, *a, **k): pass
        asyncio.run(PB.on_ticket_close(type("Up", (), {"callback_query": Q(1)})(), None))
        self.assertNotEqual(db.get_ticket(tk["id"])["status"], "closed")
        asyncio.run(PB.on_ticket_close(type("Up", (), {"callback_query": Q(999)})(), None))
        self.assertEqual(db.get_ticket(tk["id"])["status"], "closed")


if __name__ == "__main__":
    unittest.main(verbosity=2)
