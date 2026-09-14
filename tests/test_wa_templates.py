"""قوالب واتساب المعتمدة: التحقق، المسارات، والبثّ بقالب.
Meta تُحاكى على مستوى httpx فقط — كل ما فوقه حقيقي.
    python tests/test_wa_templates.py
"""
import json, os, secrets, sys, tempfile, unittest
from unittest import mock

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)
os.chdir(_ROOT)
os.environ["BOTYALLA_DB"] = os.path.join(tempfile.mkdtemp(prefix="wa-tpl-"), "t.db")
os.environ.setdefault("SECRET_KEY", "tpl-test")

import database as db                        # noqa: E402
import app as web                            # noqa: E402
import channels.wa_templates as WT           # noqa: E402

WABA = "102290129340398"
PHONE = "5550001"

SAMPLE = {"data": [
    {"id": "1", "name": "order_ready", "status": "APPROVED", "category": "UTILITY",
     "language": "ar", "components": [
         {"type": "HEADER", "format": "TEXT", "text": "طلبك جاهز"},
         {"type": "BODY", "text": "أهلاً {{1}}، طلبك رقم {{2}} جاهز."},
         {"type": "FOOTER", "text": "شكراً"},
         {"type": "BUTTONS", "buttons": [{"type": "QUICK_REPLY", "text": "تمام"}]}]},
    {"id": "2", "name": "promo_eid", "status": "REJECTED", "category": "MARKETING",
     "language": "ar", "rejected_reason": "INVALID_FORMAT",
     "components": [{"type": "BODY", "text": "عرض العيد"}]},
    {"id": "3", "name": "waiting", "status": "PENDING", "category": "UTILITY",
     "language": "ar", "components": [{"type": "BODY", "text": "قيد المراجعة"}]},
]}


class FakeResponse:
    def __init__(self, payload, status=200):
        self._p, self.status_code = payload, status
        self.text = json.dumps(payload)

    def json(self):
        return self._p


class FakeClient:
    """يسجّل كل نداء ويردّ بما تُمليه القائمة."""
    calls = []
    script = {}

    def __init__(self, *a, **k): pass
    def __enter__(self): return self
    def __exit__(self, *a): return False

    def request(self, method, url, **kw):
        FakeClient.calls.append({"method": method, "url": url,
                                 "params": kw.get("params"), "json": kw.get("json"),
                                 "auth": (kw.get("headers") or {}).get("Authorization")})
        return FakeClient.script.get(method, FakeResponse(SAMPLE))

    def get(self, url, **kw):
        return self.request("GET", url, **kw)


def use_fake():
    FakeClient.calls = []
    FakeClient.script = {}
    return mock.patch.object(WT.httpx, "Client", FakeClient)


class ValidationTests(unittest.TestCase):
    """كل رفض هنا يوفّر على العميل انتظار مراجعة Meta ثم رفضاً غامضاً."""

    def test_a_good_template_passes(self):
        self.assertIsNone(WT.validate("order_ready", "UTILITY", "أهلاً {{1}} طلبك {{2}}"))

    def test_names_must_be_lowercase_without_spaces(self):
        for bad in ("Order Ready", "order-ready", "طلب", "", "a" * 600):
            self.assertIsNotNone(WT.validate(bad, "UTILITY", "x"), bad)

    def test_variables_must_start_at_one_without_gaps(self):
        self.assertIsNotNone(WT.validate("a", "UTILITY", "{{2}} فقط"))
        self.assertIsNotNone(WT.validate("a", "UTILITY", "{{1}} و {{3}}"))
        self.assertIsNone(WT.validate("a", "UTILITY", "{{1}} و {{2}}"))

    def test_variables_are_rejected_outside_the_body(self):
        self.assertIsNotNone(WT.validate("a", "UTILITY", "ok", header="{{1}}"))
        self.assertIsNotNone(WT.validate("a", "UTILITY", "ok", footer="{{1}}"))

    def test_length_limits_match_meta(self):
        self.assertIsNotNone(WT.validate("a", "UTILITY", "x", header="h" * 61))
        self.assertIsNotNone(WT.validate("a", "UTILITY", "b" * 1025))
        self.assertIsNotNone(WT.validate("a", "UTILITY", "x", buttons=["z" * 26]))

    def test_body_is_required(self):
        self.assertIsNotNone(WT.validate("a", "UTILITY", "   "))

    def test_unknown_category_is_refused(self):
        self.assertIsNotNone(WT.validate("a", "PROMOTIONAL", "x"))


class ApiShapeTests(unittest.TestCase):
    def test_list_hits_the_waba_edge_and_flattens_components(self):
        with use_fake():
            res = WT.list_templates(WABA, "tok")
        self.assertTrue(res["ok"])
        call = FakeClient.calls[0]
        self.assertEqual(call["method"], "GET")
        self.assertTrue(call["url"].endswith(f"/{WABA}/message_templates"), call["url"])
        self.assertEqual(call["auth"], "Bearer tok")

        first = res["items"][0]
        self.assertEqual(first["name"], "order_ready")
        self.assertEqual(first["header"], "طلبك جاهز")
        self.assertEqual(first["footer"], "شكراً")
        self.assertEqual(first["buttons"], ["تمام"])
        self.assertEqual(first["vars"], [1, 2])

    def test_approved_templates_are_listed_first(self):
        with use_fake():
            res = WT.list_templates(WABA, "tok")
        self.assertEqual(res["items"][0]["status"], "APPROVED")

    def test_rejection_reason_survives(self):
        with use_fake():
            res = WT.list_templates(WABA, "tok")
        rej = [x for x in res["items"] if x["status"] == "REJECTED"][0]
        self.assertEqual(rej["rejected_reason"], "INVALID_FORMAT")

    def test_a_phone_id_pasted_instead_of_a_waba_id_surfaces_metas_error(self):
        """الرقمان متشابهان ويُخلط بينهما دوماً — الخطأ يجب أن يصل للمستخدم."""
        with use_fake():
            FakeClient.script["GET"] = FakeResponse(
                {"error": {"message": "Unsupported get request."}}, 400)
            res = WT.verify_waba(PHONE, "tok")
        self.assertFalse(res["ok"])
        self.assertIn("Unsupported", res["error"])

    def test_a_non_numeric_waba_never_reaches_the_network(self):
        with use_fake():
            res = WT.list_templates("not-an-id", "tok")
        self.assertFalse(res["ok"])
        self.assertEqual(FakeClient.calls, [])

    def test_create_sends_the_component_shape_meta_expects(self):
        with use_fake():
            FakeClient.script["POST"] = FakeResponse({"id": "9", "status": "PENDING"})
            res = WT.create_template(WABA, "tok", "order_ready", "ar", "UTILITY",
                                     "أهلاً {{1}}", header="عنوان", footer="تذييل",
                                     buttons=["نعم", "لا"])
        self.assertTrue(res["ok"], res)
        body = FakeClient.calls[0]["json"]
        self.assertEqual([c["type"] for c in body["components"]],
                         ["HEADER", "BODY", "FOOTER", "BUTTONS"])
        self.assertEqual(body["components"][3]["buttons"][0]["type"], "QUICK_REPLY")
        self.assertEqual(body["category"], "UTILITY")

    def test_create_refuses_locally_before_calling_meta(self):
        with use_fake():
            res = WT.create_template(WABA, "tok", "Bad Name", "ar", "UTILITY", "x")
        self.assertFalse(res["ok"])
        self.assertEqual(FakeClient.calls, [], "طلب شبكة لطلب مرفوض محلياً")

    def test_delete_identifies_the_template_by_name(self):
        with use_fake():
            FakeClient.script["DELETE"] = FakeResponse({"success": True})
            res = WT.delete_template(WABA, "tok", "order_ready")
        self.assertTrue(res["ok"])
        self.assertEqual(FakeClient.calls[0]["method"], "DELETE")
        self.assertEqual(FakeClient.calls[0]["params"], {"name": "order_ready"})


class RouteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        db.init_db()
        cls.c = web.app.test_client()
        cls.c.get("/register")                       # يولّد توكن CSRF في الجلسة
        with cls.c.session_transaction() as s:
            tok = s.get("_csrf")
        pw = f"tpl_{secrets.token_hex(8)}"
        cls.c.post("/register", data={"username": "tpl", "password": pw,
                                      "csrf_token": tok}, follow_redirects=True)
        with cls.c.session_transaction() as s:
            cls.tok, cls.uid = s.get("_csrf"), s.get("uid")
        assert cls.uid, "لم يكتمل التسجيل"
        db.activate_subscription(cls.uid, "pro", days=30)
        cls.wa = db.create_bot(cls.uid, "WA", f"wa:{PHONE}", "flow",
                               {"wa_token": "tok"}, channel="whatsapp")
        cls.tg = db.create_bot(cls.uid, "TG", "111:AAA", "flow", {})

    def setUp(self):
        # كل اختبار يبدأ من بوت بلا WABA — وإلا سرّب اختبارٌ حالتَه للتالي
        db.update_bot_config(self.wa, {"wa_token": "tok"})

    def test_the_page_is_whatsapp_only(self):
        self.assertEqual(self.c.get(f"/bot/{self.tg}/templates").status_code, 404)
        self.assertEqual(self.c.get(f"/bot/{self.wa}/templates").status_code, 200)

    def test_the_api_says_a_waba_is_still_missing(self):
        d = self.c.get(f"/api/bot/{self.wa}/templates").get_json()
        self.assertFalse(d["ok"])
        self.assertTrue(d["needs_waba"])

    def test_a_wrong_waba_is_refused_and_not_stored(self):
        with use_fake():
            FakeClient.script["GET"] = FakeResponse({"error": {"message": "bad id"}}, 400)
            self.c.post(f"/bot/{self.wa}/templates/waba",
                        data={"waba_id": PHONE, "csrf_token": self.tok}, follow_redirects=True)
        cfg = json.loads(db.get_bot(self.wa)["config_json"])
        self.assertNotIn("wa_waba_id", cfg, "حُفظ WABA خاطئ رغم رفض Meta له")

    def test_a_verified_waba_is_stored_and_then_lists(self):
        with use_fake():
            self.c.post(f"/bot/{self.wa}/templates/waba",
                        data={"waba_id": WABA, "csrf_token": self.tok}, follow_redirects=True)
        cfg = json.loads(db.get_bot(self.wa)["config_json"])
        self.assertEqual(cfg.get("wa_waba_id"), WABA)

        with use_fake():
            d = self.c.get(f"/api/bot/{self.wa}/templates").get_json()
        self.assertTrue(d["ok"])
        self.assertEqual(d["items"][0]["name"], "order_ready")

    def test_the_webhook_hint_never_becomes_the_stored_waba_on_its_own(self):
        """entry.id ليس موثقاً كـ WABA ID — يُقترح فقط، ولا يُستعمل بلا تحقق."""
        import bot_manager
        row = db.get_bot(self.tg)
        bot_manager._remember_waba_hint(row, "777888999")
        cfg = json.loads(db.get_bot(self.tg)["config_json"])
        self.assertEqual(cfg.get("wa_waba_hint"), "777888999")
        self.assertIsNone(cfg.get("wa_waba_id"))

    def test_creating_a_template_requires_csrf(self):
        r = self.c.post(f"/bot/{self.wa}/templates/create", data={"name": "x", "body": "y"})
        self.assertEqual(r.status_code, 400)

    def test_a_free_plan_cannot_open_the_templates_page(self):
        db.activate_subscription(self.uid, "free", days=30)
        try:
            self.assertEqual(self.c.get(f"/bot/{self.wa}/templates").status_code, 403)
        finally:
            db.activate_subscription(self.uid, "pro", days=30)


class BroadcastTests(unittest.TestCase):
    """القالب يصل لمن خرج من نافذة الـ24 ساعة — وهذا سبب وجود الميزة."""

    @classmethod
    def setUpClass(cls):
        db.init_db()
        with db.get_conn() as c:
            c.execute("INSERT OR IGNORE INTO users(id,username,pw_hash,role,created_at)"
                      " VALUES(61,'bc','x','user',0)")
        db.activate_subscription(61, "pro", days=30)
        cls.bot = db.create_bot(61, "WA BC", "wa:5559999", "flow",
                                {"wa_token": "tok"}, channel="whatsapp")
        db.add_bot_user(cls.bot, 201001, "recent", peer="wa:201001")
        db.add_bot_user(cls.bot, 201002, "old", peer="wa:201002")
        import time
        with db.get_conn() as c:
            c.execute("UPDATE bot_users SET last_in_at=? WHERE peer='wa:201002'",
                      (int(time.time()) - 30 * 3600,))

    def test_a_template_reaches_everyone_while_free_text_does_not(self):
        import asyncio, bot_manager
        from channels.whatsapp import WhatsAppChannel
        posted = []

        async def fake_post(self, payload):
            if self.on_send is not None and (await self.on_send()) is False:
                return None
            posted.append(payload)
            return {"messages": [{"id": "x"}]}

        row = db.get_bot(self.bot)
        with mock.patch.object(WhatsAppChannel, "_post", fake_post):
            ch = bot_manager._wa_channel(row)
            peers = db.list_bot_peers(self.bot)
            asyncio.run(bot_manager.BotManager._broadcast_template(
                bot_manager.manager, row, peers, "order_ready", "ar", ["أحمد", "A-12"],
                bot_manager.BotManager._progress(None, len(peers))))

        self.assertEqual(len(posted), 2, "القالب يجب أن يصل للاثنين")
        self.assertEqual(posted[0]["type"], "template")
        self.assertEqual(posted[0]["template"]["name"], "order_ready")
        self.assertEqual(posted[0]["template"]["language"], {"code": "ar"})
        params = posted[0]["template"]["components"][0]["parameters"]
        self.assertEqual([p["text"] for p in params], ["أحمد", "A-12"])

        inside = db.list_bot_peers(self.bot, within_seconds=bot_manager.WA_WINDOW)
        self.assertEqual(inside, ["wa:201001"], "النص الحر يصل لواحد فقط")

    def test_template_sends_still_pass_through_the_usage_counter(self):
        """القوالب مدفوعة أيضاً — تجاوزها للعدّاد يعني فاتورة بلا سقف."""
        import asyncio, bot_manager
        from channels.whatsapp import WhatsAppChannel
        posted = []

        async def fake_post(self, payload):
            if self.on_send is not None and (await self.on_send()) is False:
                return None
            posted.append(payload)
            return {"ok": True}

        with db.get_conn() as c:
            c.execute("DELETE FROM usage_msgs WHERE owner_id=61")
            c.execute("INSERT INTO usage_msgs(bot_id,owner_id,month,sent)"
                      " VALUES(?,?,strftime('%Y-%m','now'),1000)", (self.bot, 61))
        row = db.get_bot(self.bot)
        with mock.patch.object(WhatsAppChannel, "_post", fake_post):
            peers = db.list_bot_peers(self.bot)
            asyncio.run(bot_manager.BotManager._broadcast_template(
                bot_manager.manager, row, peers, "order_ready", "ar", [],
                bot_manager.BotManager._progress(None, len(peers))))
        self.assertEqual(posted, [], "أُرسل قالب رغم نفاد رصيد الباقة")


if __name__ == "__main__":
    unittest.main(verbosity=2)
