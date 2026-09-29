"""الدفع داخل المحادثة — المرحلة 9: المبلغ بالوحدة الصغرى · مفتاح البوابة مختوم ولا يصل المتصفح ·
رابط من الصندوق المشترك · الويبهوك تنبيه فقط والحالة من البوابة · تسوية مرة واحدة · صفحة العودة ·
بطاقة «دفع» في الفلو (انتظار · استئناف بعد الدفع · فرع عدم الدفع عند الانتهاء · إلغاء ثم دفع متأخر).
البوابة محاكاة بالكامل — لا شبكة ولا مال.

    python tests/test_chat_pay.py
"""
import asyncio, json, os, secrets, sys, tempfile, time, unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_TMPDIR = tempfile.mkdtemp(prefix="botyalla-cpay-")
os.environ["BOTYALLA_DB"] = os.path.join(_TMPDIR, "test.db")   # قبل استيراد database
os.environ["BOTYALLA_UPLOADS"] = _TMPDIR
os.environ["BOTYALLA_LOGS"] = os.path.join(_TMPDIR, "logs")
os.environ["ADMIN_USER"] = "admin"
os.environ["PUBLIC_URL"] = "https://botyalla.test"          # روابط العودة والويبهوك مطلقة دائماً — لا تعتمد على .env المحلي
os.environ["ADMIN_PASS"] = "Cp#" + secrets.token_hex(6)

import auth                                # noqa: E402
import database as db                      # noqa: E402
import flow_engine as FE                   # noqa: E402
import chat_pay as CP                      # noqa: E402
import payments_gw as GW                   # noqa: E402
import growth                              # noqa: E402
import app as web                          # noqa: E402

PW = "Str0ng!Pass" + secrets.token_hex(3)
db.init_db(); web.seed_platform_defaults(); web.contact_defaults(); web.seed_default_admin()
web.app.config["TESTING"] = True

# ---- بوابة محاكاة ----
GATE = {"status": {}, "created": [], "n": 0}


def fake_create(provider, secret, **kw):
    GATE["n"] += 1
    gid = f"inv_{GATE['n']}"
    GATE["created"].append(dict(kw, provider=provider, secret=secret, gid=gid))
    GATE["status"][gid] = "pending"
    return gid, f"https://pay.example.test/{gid}"


GW.create = fake_create
GW.status = lambda provider, secret, gid, http=None, opts=None: GATE["status"].get(gid, "pending")
CAPI = []
growth.capi_async = lambda row, peer, ev, val=None, cur=None: CAPI.append((peer, ev, val, cur))
NOTES = []


async def _note(bot_row, channel, text):
    NOTES.append(text)
FE.notify_owner = _note


class Ch:
    phone_id = page_id = None

    def __init__(self):
        self.out = []

    async def send_text(self, peer, text):
        self.out.append(("text", text)); return True

    async def remove_keyboard(self, peer, text):
        self.out.append(("text", text)); return True

    async def send_buttons(self, peer, text, options):
        self.out.append(("buttons", text)); return True

    async def send_cta(self, peer, text, button, url):
        self.out.append(("cta", text, button, url)); return True


CHANNEL = {"ch": Ch()}
web._pay_channel = lambda bot_row, peer: CHANNEL["ch"]
CP.HOOKS["channel"] = lambda bot_row, peer: CHANNEL["ch"]


def user(name, plan="enterprise"):
    uid, err = db.create_account(name + secrets.token_hex(3), auth.hash_password(PW), f"{name}{secrets.token_hex(3)}@example.test",
                                 None, 30, "person", verify_required=False)
    assert not err, err
    db.mark_email_verified(uid)
    if plan:
        db.activate_subscription(uid, plan, 30)
    return uid


def client(user_id):
    c = web.app.test_client()
    with c.session_transaction() as s:
        u = db.get_user(user_id)
        s.update(_csrf="tk", uid=user_id, uname=u["username"], role=u["role"], pwv=web._pw_stamp(u["pw_hash"]))
    return c


def post(c, url, body=None):
    return c.post(url, data=json.dumps(body or {}), content_type="application/json", headers={"X-CSRF-Token": "tk"})


class Acct:
    def __init__(self):
        self.owner = user("own")
        self.c = client(self.owner)
        self.bot = db.create_bot(self.owner, "WA", f"wa:{secrets.randbelow(10**12)}", "flow", {"bot_username": "966500000777"}, "whatsapp")
        self.secret = "sk_test_" + secrets.token_hex(16)
        r = post(self.c, "/api/pay/settings", {"provider": "moyasar", "currency": "SAR", "secret": self.secret, "webhook_secret": "whs"}).get_json()
        assert r["ok"], r

    def customer(self):
        p = f"wa:9665{secrets.randbelow(10**8):08d}"
        db.add_bot_user(self.bot, int(p[3:]), "منى", peer=p)
        db.log_message(self.bot, p, "in", "customer", "مرحبا", name="منى")
        db.touch_bot_user(self.bot, p)
        with db.get_conn() as c:
            c.execute("UPDATE bot_users SET last_in_at=? WHERE bot_id=? AND peer=?", (int(time.time()), self.bot, p))
        return p

    def hook(self, gid, provider="moyasar", secret_token="whs"):
        return web.app.test_client().post(CP.webhook_url(self.owner, provider).split("://", 1)[1].split("/", 1)[1].join(["/", ""]),
                                          data=json.dumps({"type": "payment_paid", "secret_token": secret_token,
                                                           "data": {"invoice_id": gid, "status": "paid"}}),
                                          content_type="application/json")


def say(bot, peer, text):
    CHANNEL["ch"] = Ch()
    asyncio.run(FE.handle_message(db.get_bot(bot), CHANNEL["ch"], {"peer": peer, "kind": "text", "text": text, "name": "منى"}))
    return CHANNEL["ch"].out


class AmountTests(unittest.TestCase):
    def test_minor_units(self):
        self.assertEqual(CP.to_minor("٢٥٠٫٥", "SAR"), 25050)
        self.assertEqual(CP.to_minor("1,200", "SAR"), 120000)
        self.assertEqual(CP.to_minor("1.25", "KWD"), 1250)
        self.assertIsNone(CP.to_minor("-5", "SAR"))
        self.assertIsNone(CP.to_minor("abc", "SAR"))
        self.assertEqual(CP.fmt(25050, "SAR"), "250.5 SAR")


class SettingsTests(unittest.TestCase):
    def test_secret_is_sealed_and_validated(self):
        a = Acct()
        raw = db.get_setting(a.owner, CP.CFG_KEY)
        self.assertNotIn(a.secret, raw, "المفتاح مختوم في القاعدة")
        self.assertEqual(CP.config(a.owner)["secret"], a.secret)
        self.assertNotIn(a.secret, a.c.get("/payments").get_data(as_text=True), "ولا يصل للصفحة")
        self.assertEqual(post(a.c, "/api/pay/settings", {"provider": "moyasar", "secret": "pk_live_x"}).get_json()["error"], "secret")
        self.assertEqual(post(a.c, "/api/pay/settings", {"provider": "paypal"}).get_json()["error"], "provider")
        m = user("mem", None); db.join_team(a.owner, m, "member")
        self.assertEqual(post(client(m), "/api/pay/settings", {"provider": "tap"}).status_code, 403)


class InboxRequestTests(unittest.TestCase):
    def test_link_webhook_settles_once_with_receipt_and_conversion(self):
        a = Acct()
        p = a.customer()
        CHANNEL["ch"] = Ch()
        r = post(a.c, "/api/pay/request", {"bot": a.bot, "peer": p, "amount": "450", "description": "حجز جناح — ليلتان"}).get_json()
        self.assertTrue(r["ok"], r)
        pay = r["payment"]
        self.assertEqual((pay["amount"], pay["currency"], pay["status"]), (45000, "SAR", "pending"))
        self.assertEqual(GATE["created"][-1]["secret"], a.secret)
        kind, text, button, url = CHANNEL["ch"].out[-1]
        self.assertEqual((kind, button, url), ("cta", "ادفع الآن", f"https://pay.example.test/{pay['gw_id']}"))
        self.assertIn("450 SAR", text)
        # ويبهوك بتوقيع مسار خاطئ
        self.assertEqual(web.app.test_client().post(f"/pay/wh/moyasar/{a.owner}/deadbeef", json={}).status_code, 404)
        # ويبهوك صحيح لكن البوابة تقول «لم يُدفع» — لا شيء
        a.hook(pay["gw_id"])
        self.assertEqual(db.get_chat_payment(pay["id"])["status"], "pending", "الإشعار وحده لا يدفع")
        # سرّ Moyasar خاطئ — يُتجاهل
        GATE["status"][pay["gw_id"]] = "paid"
        a.hook(pay["gw_id"], secret_token="nope")
        self.assertEqual(db.get_chat_payment(pay["id"])["status"], "pending")
        CHANNEL["ch"] = Ch()
        a.hook(pay["gw_id"]); a.hook(pay["gw_id"])
        self.assertEqual(db.get_chat_payment(pay["id"])["status"], "paid")
        receipts = [o for o in CHANNEL["ch"].out if "تم استلام دفعتك" in o[1]]
        self.assertEqual(len(receipts), 1, "إيصال واحد مهما تكرر الإشعار")
        self.assertIn((p, "Purchase", 450.0, "SAR"), CAPI)
        self.assertTrue(any("450 SAR" in n for n in NOTES))

    def test_window_amount_and_account_guards(self):
        a = Acct()
        p = a.customer()
        self.assertEqual(post(a.c, "/api/pay/request", {"bot": a.bot, "peer": p, "amount": "0"}).get_json()["error"], "amount")
        with db.get_conn() as c:
            c.execute("UPDATE bot_users SET last_in_at=? WHERE bot_id=? AND peer=?", (int(time.time()) - 90000, a.bot, p))
        self.assertEqual(post(a.c, "/api/pay/request", {"bot": a.bot, "peer": p, "amount": "10"}).get_json()["error"], "window")
        other = Acct()
        self.assertEqual(post(other.c, "/api/pay/request", {"bot": a.bot, "peer": p, "amount": "10"}).status_code, 404)
        self.assertEqual(client(user("basic", "merchant")).get("/api/pay/list").status_code, 403)

    def test_undelivered_link_is_failed_not_pending(self):
        a = Acct()
        p = a.customer()

        class Down(Ch):                                        # واتساب رفض الإرسال (توكن/نافذة/حدّ) ⇒ None
            phone_id = "555"

            async def send_cta(self, peer, text, button, url):
                return None
        CHANNEL["ch"] = Down()
        try:
            self.assertEqual(post(a.c, "/api/pay/request", {"bot": a.bot, "peer": p, "amount": "10"}).get_json()["error"], "send")
        finally:
            CHANNEL["ch"] = Ch()
        self.assertEqual(db.list_chat_payments(a.owner)[0]["status"], "failed")

    def test_return_page_confirms_immediately(self):
        a = Acct()
        p = a.customer()
        CHANNEL["ch"] = Ch()
        pay = post(a.c, "/api/pay/request", {"bot": a.bot, "peer": p, "amount": "99"}).get_json()["payment"]
        GATE["status"][pay["gw_id"]] = "paid"
        path = "/" + CP.return_url(pay["id"]).split("://", 1)[1].split("/", 1)[1]
        page = web.app.test_client().get(path).get_data(as_text=True)
        self.assertIn("تم الدفع بنجاح", page)
        self.assertIn("https://wa.me/966500000777", page)
        self.assertEqual(web.app.test_client().get(f"/pay/r/{pay['id']}/bad").status_code, 404)


PAY_FLOW = {"start": "q", "nodes": {
    "q": {"type": "buttons", "text": "اختر الغرفة:", "var": "room",
          "options": [{"label": "جناح", "next": "set"}, {"label": "مزدوجة", "next": "set2"}]},
    "set": {"type": "set_var", "var": "price", "value": "900", "next": "pay"},
    "set2": {"type": "set_var", "var": "price", "value": "450", "next": "pay"},
    "pay": {"type": "payment", "amount": "{{price}}", "currency": "SAR", "description": "حجز {{room}}",
            "text": "لتأكيد حجزك ادفع من الزر:", "button": "ادفع وأكّد", "minutes": 30, "var": "paid",
            "next": "ok", "fail": "no"},
    "ok": {"type": "end", "text": "🎉 تم تأكيد حجز {{room}} ({{payment_ref}})"},
    "no": {"type": "end", "text": "لم يكتمل الدفع — نحن هنا متى أردت"}}}


class FlowCardTests(unittest.TestCase):
    def setUp(self):
        self.a = Acct()
        c = self.a.c
        fid = post(c, f"/api/bot/{self.a.bot}/flows", {"name": "حجز ودفع"}).get_json()["flow"]["id"]
        post(c, f"/api/bot/{self.a.bot}/flows/{fid}/save", {"draft": PAY_FLOW})
        r = post(c, f"/api/bot/{self.a.bot}/flows/{fid}/publish").get_json()
        assert r["ok"], r
        post(c, f"/api/bot/{self.a.bot}/flows/{fid}/toggle", {"active": True})

    def test_pay_then_flow_continues_on_the_paid_branch(self):
        p = self.a.customer()
        say(self.a.bot, p, "hi")
        out = say(self.a.bot, p, "جناح")
        kind, text, button, url = out[-1]
        self.assertEqual((kind, button), ("cta", "ادفع وأكّد"))
        self.assertIn("900 SAR", text)
        self.assertIn("حجز جناح", text)
        pay = db.list_chat_payments(self.a.owner)[0]
        self.assertEqual(pay["amount"], 90000)
        out = say(self.a.bot, p, "دفعت")
        self.assertIn("لم يصلنا الدفع بعد", out[-1][1], "ينتظر ويذكّر بالرابط")
        GATE["status"][pay["gw_id"]] = "paid"
        CHANNEL["ch"] = Ch()
        self.a.hook(pay["gw_id"])
        texts = [o[1] for o in CHANNEL["ch"].out]
        self.assertIn(f"🎉 تم تأكيد حجز جناح (#{pay['id']})", texts)
        self.assertIsNone(db.get_chat_state(self.a.bot, p), "الفلو انتهى")

    def test_customer_says_paid_and_the_gateway_agrees(self):
        p = self.a.customer()
        say(self.a.bot, p, "hi"); say(self.a.bot, p, "مزدوجة")
        pay = db.list_chat_payments(self.a.owner)[0]
        GATE["status"][pay["gw_id"]] = "paid"
        say(self.a.bot, p, "دفعت")                     # الويبهوك تأخر — كتابة العميل تكفي لسؤال البوابة
        self.assertEqual(db.get_chat_payment(pay["id"])["status"], "paid")
        self.assertIsNone(db.get_chat_state(self.a.bot, p))

    def test_expiry_takes_the_unpaid_branch_and_a_late_payment_still_counts(self):
        p = self.a.customer()
        say(self.a.bot, p, "hi"); say(self.a.bot, p, "جناح")
        pay = db.list_chat_payments(self.a.owner)[0]
        CHANNEL["ch"] = Ch()
        CP.sweep(pay["expires_at"] + 1)
        self.assertEqual(db.get_chat_payment(pay["id"])["status"], "expired")
        self.assertIn("لم يكتمل الدفع — نحن هنا متى أردت", [o[1] for o in CHANNEL["ch"].out])
        GATE["status"][pay["gw_id"]] = "paid"                 # دفع بعد انتهاء المهلة محلياً
        CHANNEL["ch"] = Ch()
        self.a.hook(pay["gw_id"])
        self.assertEqual(db.get_chat_payment(pay["id"])["status"], "paid", "المال وصل — يُسجَّل")
        self.assertTrue(any("تم استلام دفعتك" in o[1] for o in CHANNEL["ch"].out))

    def test_not_configured_or_bad_amount_goes_to_the_fail_branch(self):
        CP.clear_config(self.a.owner)
        p = self.a.customer()
        say(self.a.bot, p, "hi")
        self.assertEqual(say(self.a.bot, p, "جناح")[-1], ("text", "لم يكتمل الدفع — نحن هنا متى أردت"))
        fid = post(self.a.c, f"/api/bot/{self.a.bot}/flows", {"name": "x", "trigger": {"type": "keywords", "keywords": ["x"]}}).get_json()["flow"]["id"]
        post(self.a.c, f"/api/bot/{self.a.bot}/flows/{fid}/save", {"draft": {"start": "a", "nodes": {"a": {"type": "payment", "amount": "", "currency": "SAR"}}}})
        self.assertEqual(post(self.a.c, f"/api/bot/{self.a.bot}/flows/{fid}/publish").get_json()["error"], "node:a:amount")
        post(self.a.c, f"/api/bot/{self.a.bot}/flows/{fid}/save", {"draft": {"start": "a", "nodes": {"a": {"type": "payment", "amount": "5", "currency": "XYZ"}}}})
        self.assertEqual(post(self.a.c, f"/api/bot/{self.a.bot}/flows/{fid}/publish").get_json()["error"], "node:a:currency")

    def test_empty_currency_uses_the_account_default_and_no_public_url_refuses(self):
        a = Acct()                                               # حساب بلا فلو «أي رسالة» يسبق المشغّل
        c = a.c
        post(c, "/api/pay/settings", {"provider": "moyasar", "currency": "KWD"})    # بلا مفتاح جديد = يبقى المحفوظ
        fid = post(c, f"/api/bot/{a.bot}/flows", {"name": "kw", "trigger": {"type": "keywords", "keywords": ["kw"]}}).get_json()["flow"]["id"]
        post(c, f"/api/bot/{a.bot}/flows/{fid}/save", {"draft": {"start": "a", "nodes": {
            "a": {"type": "payment", "amount": "1.5", "currency": "", "next": None, "fail": "b"},
            "b": {"type": "end", "text": "لا بوابة"}}}})
        self.assertTrue(post(c, f"/api/bot/{a.bot}/flows/{fid}/publish").get_json()["ok"])
        post(c, f"/api/bot/{a.bot}/flows/{fid}/toggle", {"active": True})
        p = a.customer()
        n = len(GATE["created"])
        out = say(a.bot, p, "kw")
        self.assertEqual(len(GATE["created"]), n + 1, out)
        self.assertEqual(GATE["created"][-1]["currency"], "KWD")
        self.assertEqual(GATE["created"][-1]["amount"], 1500)               # 1.5 دينار = 1500 فلس
        base = CP.HOOKS["base"]
        CP.HOOKS["base"] = lambda: ""
        try:
            p2 = a.customer()
            self.assertEqual(say(a.bot, p2, "kw")[-1], ("text", "لا بوابة"))   # لا رابط نسبي يصل للبوابة
        finally:
            CP.HOOKS["base"] = base


if __name__ == "__main__":
    unittest.main(verbosity=2)
