"""إضافة «تحصيل المدفوعات» — شراؤها لكل بوت، وإيصالات عملاء البوت وقرار صاحبه.

القواعد المختبَرة: سعر الإضافة من الخادم لا من الفورم · تتفعّل بموافقة الأدمن وحدها وتُمدّ
من انتهائها · حسابات الاستلام لصاحب البوت وحده · قرار الدفعة ذرّي ولصاحب البوت وحده ·
الإيصال المرفوض لا يُحفظ · المقبول يصل صاحب البوت بزرّين والعميل يُبلَّغ بالقرار.

    python tests/test_customer_pay.py
"""
import asyncio, json, os, secrets, sys, tempfile, time, unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_TMPDIR = tempfile.mkdtemp(prefix="botyalla-cpay-")
os.environ["BOTYALLA_DB"] = os.path.join(_TMPDIR, "test.db")   # قبل استيراد database
os.environ["BOTYALLA_UPLOADS"] = _TMPDIR
os.environ["BOTYALLA_OCR"] = "0"
PW = "cp_" + secrets.token_hex(6)
os.environ["ADMIN_USER"] = "admin"
os.environ["ADMIN_PASS"] = PW

import auth                                # noqa: E402
import database as db                      # noqa: E402
import app as web                          # noqa: E402
import payments as pay                     # noqa: E402
import templates_bot as T                  # noqa: E402

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 8192


def _boot():
    db.init_db()
    web.seed_platform_defaults()
    web.contact_defaults()
    web.seed_default_admin()
    web.app.config["TESTING"] = True


def _client():
    c = web.app.test_client()
    with c.session_transaction() as s:
        s["_csrf"] = "tk"
    return c


def _as(name):
    c = _client()
    c.post("/login", data={"username": name, "password": PW, "csrf_token": "tk"})
    return c


def _upload(c, path, **form):
    import io
    data = {"method": "vodafone", "ref": "123", "csrf_token": "tk",
            "screenshot": (io.BytesIO(PNG + os.urandom(16)), "r.png"), **form}
    return c.post(path, data=data, content_type="multipart/form-data")


class AddonPurchaseTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        _boot()
        cls.u = db.create_user("cp_owner", auth.hash_password(PW))
        db.activate_subscription(cls.u, "merchant", days=30)
        cls.store = db.create_bot(cls.u, "Shop", "T:cp-store", "store", {"business_name": "Shop"})
        cls.flow = db.create_bot(cls.u, "Flow", "T:cp-flow", "flow", {"business_name": "Flow"})

    def setUp(self):
        web._login_attempts.clear()

    def _addon_payments(self, bid):
        return [p for p in db.list_payments(self.u) if p["plan"] == db.addon_plan(bid)]

    def test_the_price_comes_from_the_server_and_approval_activates_30_days(self):
        r = _upload(_as("cp_owner"), f"/bot/{self.store}/addon/pay", amount="1")
        self.assertEqual(r.status_code, 302)
        p = self._addon_payments(self.store)[0]
        self.assertEqual(float(p["amount"]), float(web.addon_pay_price()), "المبلغ من الخادم")
        self.assertFalse(db.addon_active(self.store), "لا تفعيل قبل موافقة الأدمن")
        db.finalize_payment(p["id"], "approved")
        self.assertTrue(db.addon_active(self.store))
        first = db.addon_expires(self.store)
        self.assertAlmostEqual(first - time.time(), 30 * 86400, delta=120)
        self.assertIn(db.addon_plan(self.store), web._plan_names("ar"), "اسم مفهوم في جداول المدفوعات")

        _upload(_as("cp_owner"), f"/bot/{self.store}/addon/pay")
        second = [p for p in self._addon_payments(self.store) if p["status"] == "pending"][0]
        db.finalize_payment(second["id"], "approved")
        self.assertEqual(db.addon_expires(self.store) - first, 30 * 86400, "التجديد يُمدّ من الانتهاء")

    def test_only_store_bots_can_buy_it(self):
        _upload(_as("cp_owner"), f"/bot/{self.flow}/addon/pay")
        self.assertEqual(self._addon_payments(self.flow), [])

    def test_receiving_accounts_keep_only_known_fields(self):
        _as("cp_owner").post(f"/bot/{self.store}/pay-settings", data={
            "pay_vodafone": " 01001234567 ", "pay_instapay": "", "pay_evil": "x", "csrf_token": "tk"})
        cfg = json.loads(db.get_bot(self.store)["config_json"])
        self.assertEqual(cfg["pay"], {"vodafone": "01001234567"})


class BotPaymentTests(unittest.TestCase):
    """قرار الدفعة ذرّي ولصاحب البوت وحده، والعميل يُبلَّغ عبر البوت."""

    @classmethod
    def setUpClass(cls):
        _boot()
        cls.u = db.create_user("cp_shop", auth.hash_password(PW))
        cls.other = db.create_user("cp_other", auth.hash_password(PW))
        cls.bid = db.create_bot(cls.u, "S", "T:cp-s", "store", {"business_name": "S"})
        cls.other_bid = db.create_bot(cls.other, "O", "T:cp-o", "store", {"business_name": "O"})
        cls._send = web.manager.bot_send

    @classmethod
    def tearDownClass(cls):
        web.manager.bot_send = cls._send

    def setUp(self):
        web._login_attempts.clear()
        self.sent = []
        web.manager.bot_send = lambda bot_id, chat, text: self.sent.append((bot_id, chat, text)) or True

    def _pending(self):
        oid = db.add_order(self.bid, 777, "منى", "010", "عنوان", [{"name": "x", "qty": 1, "price": 50}], 50,
                           pay_status="awaiting")
        fname = pay.save_receipt(PNG, "bpay_test")
        pid = db.create_bot_payment(self.bid, oid, 777, "منى", 50, fname, secrets.token_hex(8), "F1", "{}")
        return oid, pid

    def _order(self, oid):
        return [o for o in db.list_orders(self.bid) if o["id"] == oid][0]

    def test_a_decision_is_atomic_and_updates_the_order(self):
        oid, pid = self._pending()
        self.assertEqual(self._order(oid)["pay_status"], "pending")
        self.assertIsNone(db.decide_bot_payment(pid, self.other_bid, "approved"), "بوت آخر لا يبتّ")
        row = db.decide_bot_payment(pid, self.bid, "approved")
        self.assertEqual(row["status"], "approved")
        self.assertEqual(self._order(oid)["pay_status"], "paid")
        self.assertIsNone(db.decide_bot_payment(pid, self.bid, "rejected"), "لا بتّ مرتين")

    def test_the_owner_decides_from_the_dashboard_and_the_customer_is_told(self):
        oid, pid = self._pending()
        _as("cp_shop").post(f"/bot/{self.bid}/payments/{pid}/approve", data={"csrf_token": "tk"})
        self.assertEqual(db.get_bot_payment(pid)["status"], "approved")
        self.assertEqual(len(self.sent), 1)
        self.assertEqual(self.sent[0][1], 777)
        self.assertIn("تم تأكيد دفع طلبك", self.sent[0][2])

    def test_another_user_cannot_decide_or_see_the_receipt(self):
        oid, pid = self._pending()
        c = _as("cp_other")
        self.assertEqual(c.post(f"/bot/{self.bid}/payments/{pid}/approve",
                                data={"csrf_token": "tk"}).status_code, 404)
        self.assertEqual(c.get(f"/bot/{self.bid}/payments/{pid}/receipt").status_code, 404)
        self.assertEqual(db.get_bot_payment(pid)["status"], "pending")
        self.assertEqual(_as("cp_shop").get(f"/bot/{self.bid}/payments/{pid}/receipt").status_code, 200)


# ---- محاكاة تليجرام للدوال الخالصة في templates_bot ----
class _File:
    async def download_as_bytearray(self):
        return bytearray(PNG + os.urandom(8))


class _Photo:
    file_id = "PHOTO-1"

    async def get_file(self):
        return _File()


class _Bot:
    def __init__(self):
        self.calls = []

    async def send_photo(self, chat, photo, **kw):
        self.calls.append(("photo", chat, photo, kw))

    async def send_document(self, chat, doc, **kw):
        self.calls.append(("doc", chat, doc, kw))

    async def send_message(self, chat, text, **kw):
        self.calls.append(("msg", chat, text))


class _Msg:
    def __init__(self, text=None, photo=True):
        self.text, self.photo, self.document, self.caption = text, [_Photo()] if photo else [], None, "💳"
        self.replies = []

    async def reply_text(self, text, **kw):
        self.replies.append(text)


def _update(msg, user=555):
    u = type("U", (), {"id": user, "first_name": "منى"})()
    return type("Upd", (), {"message": msg, "effective_message": msg, "effective_user": u,
                            "effective_chat": type("C", (), {"id": user})()})()


def _ctx(bid, cfg):
    app = type("App", (), {"bot_data": {"bot_id": bid, "config": cfg}})()
    return type("Ctx", (), {"application": app, "user_data": {}, "bot": _Bot()})()


class StoreFlowTests(unittest.TestCase):
    """إيصال العميل داخل بوت المتجر: المرفوض لا يُحفظ، والمقبول يصل صاحب البوت بزرّين."""

    CFG = {"owner_chat_id": "4242", "business_name": "Shop",
           "pay": {"vodafone": "01001234567", "instapay": "shop@instapay"}}

    @classmethod
    def setUpClass(cls):
        _boot()
        cls.u = db.create_user("cp_flow", auth.hash_password(PW))
        cls.bid = db.create_bot(cls.u, "F", "T:cp-f", "store", {"business_name": "F"})
        cls._check = pay.auto_check

    @classmethod
    def tearDownClass(cls):
        pay.auto_check = cls._check

    def _ctx(self, amount=120):
        ctx = _ctx(self.bid, self.CFG)
        oid = db.add_order(self.bid, 555, "منى", "010", "عنوان", [], amount, pay_status="awaiting")
        ctx.user_data["pay"] = {"order": oid, "amount": amount, "customer": "منى"}
        return ctx, oid

    def test_payment_is_asked_only_when_the_addon_is_active(self):
        ctx = _ctx(self.bid, self.CFG)
        with db.get_conn() as c:
            c.execute("DELETE FROM bot_addons WHERE bot_id=?", (self.bid,))
        self.assertFalse(T.pay_enabled(ctx))
        db.extend_addon(self.bid, "pay", days=30)
        self.assertTrue(T.pay_enabled(ctx))
        self.assertFalse(T.pay_enabled(_ctx(self.bid, {"pay": {}})), "بلا وسيلة استلام لا طلب دفع")
        text = T.pay_instructions(self.CFG["pay"], 120, 9)
        self.assertIn("01001234567", text)
        self.assertIn("120", text)

    def test_a_refused_receipt_is_not_saved(self):
        pay.auto_check = lambda *a, **k: {"image": {"ok": True}, "refuse": True,
                                          "reason": "amount_mismatch", "verdict": "reject"}
        ctx, oid = self._ctx()
        msg = _Msg()
        state = asyncio.run(T.on_receipt(_update(msg), ctx))
        self.assertEqual(state, T.ST_PAY, "يبقى ينتظر إيصالاً صحيحاً")
        self.assertIn("المبلغ المطلوب (120 ج)", msg.replies[-1])
        self.assertEqual(db.list_bot_payments(self.bid), [])
        self.assertEqual(ctx.bot.calls, [], "لا شيء يصل صاحب البوت")

    def test_an_accepted_receipt_reaches_the_owner_with_two_buttons(self):
        pay.auto_check = lambda *a, **k: {"image": {"ok": True}, "refuse": False,
                                          "verdict": "needs_review", "ocr": None}
        ctx, oid = self._ctx(80)
        msg = _Msg()
        state = asyncio.run(T.on_receipt(_update(msg), ctx))
        self.assertEqual(state, T.ConversationHandler.END)
        rows = [p for p in db.list_bot_payments(self.bid) if p["order_id"] == oid]
        self.assertEqual((len(rows), rows[0]["status"], rows[0]["amount"]), (1, "pending", 80))
        kind, chat, photo, kw = ctx.bot.calls[0]
        self.assertEqual((kind, chat, photo), ("photo", 4242, "PHOTO-1"))
        datas = [b.callback_data for row in kw["reply_markup"].inline_keyboard for b in row]
        self.assertEqual(datas, [f"bp:ok:{rows[0]['id']}", f"bp:no:{rows[0]['id']}"])
        self.assertEqual([o for o in db.list_orders(self.bid) if o["id"] == oid][0]["pay_status"], "pending")

        # زرّ صاحب البوت: غريب يُرفض، وصاحبه يؤكد والعميل يُبلَّغ
        answers = []

        async def answer(*a, **k):
            answers.append(k.get("show_alert", False))

        async def edit(**k):
            answers.append("edited")

        def query(user):
            return type("Q", (), {"from_user": type("F", (), {"id": user})(), "data": datas[0],
                                  "message": msg, "answer": answer, "edit_message_caption": edit})()
        stranger = type("U", (), {"callback_query": query(999)})()
        asyncio.run(T.on_pay_decision(stranger, ctx))
        self.assertEqual(db.get_bot_payment(rows[0]["id"])["status"], "pending")
        owner = type("U", (), {"callback_query": query(4242)})()
        asyncio.run(T.on_pay_decision(owner, ctx))
        self.assertEqual(db.get_bot_payment(rows[0]["id"])["status"], "approved")
        told = [c for c in ctx.bot.calls if c[0] == "msg"]
        self.assertEqual(told[0][1], 555)
        self.assertIn("تم تأكيد دفع طلبك", told[0][2])


if __name__ == "__main__":
    unittest.main(verbosity=2)
