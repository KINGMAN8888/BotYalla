"""«عقل البوت» كمساعد مبيعات ودعم: رسالة البداية وأزرارها · أزرار الرد السريع ·
مساعد BotYalla الرسمي بأسعار حيّة · إيقاف الرسائل الترويجية (سياسة Meta) — بلا نموذج حقيقي.
    python tests/test_ai_sales.py
"""
import asyncio, json, os, sys, tempfile, unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_TMP = tempfile.mkdtemp(prefix="botyalla-aisales-")
os.environ["BOTYALLA_DB"] = os.path.join(_TMP, "t.db")        # قبل أي استيراد
os.environ["BOTYALLA_UPLOADS"] = _TMP
os.environ["BOTYALLA_LOGS"] = _TMP
os.environ["PUBLIC_URL"] = "https://botyalla.test"

import database as db          # noqa: E402
import flow_engine as FE       # noqa: E402
import ai_agent as ai          # noqa: E402
import platform_kb             # noqa: E402
import app as A                # noqa: E402


class Mock:
    def __init__(self):
        self.sent = []

    async def send_text(self, p, t): self.sent.append(("text", t))
    async def send_buttons(self, p, t, o): self.sent.append(("buttons", t, list(o)))
    async def send_image(self, p, u, caption=None): self.sent.append(("image", caption))
    async def remove_keyboard(self, p, t): self.sent.append(("text", t))
    async def fetch_media(self, m): return None, None


FLOW = {"start_message": "أهلاً من الفلو!", "end_message": "شكراً!", "steps": [
    {"id": "s1", "type": "question", "prompt": "اسمك؟", "var": "الاسم"}]}


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        db.init_db()
        with db.get_conn() as c:
            c.execute("INSERT OR IGNORE INTO users(id,username,pw_hash,role,created_at) VALUES(1,'root','x','admin',0)")
            c.execute("INSERT OR IGNORE INTO users(username,pw_hash,role,created_at) VALUES('shop','x','user',0)")
        cls.owner = db.get_user_by_name("shop")["id"]
        # الفئات تتشارك قاعدة الملف — الإنشاء مرة واحدة
        def bot(owner, name, token, biz):
            mine = [b for b in db.list_bots(owner) if b["name"] == name]
            return mine[0]["id"] if mine else db.create_bot(
                owner, name, token, "customer_service", {"business_name": biz, "flow": FLOW})
        cls.bid = bot(cls.owner, "shop", "tk-sales", "رغد")
        cls.official = bot(1, "BotYalla", "tk-official", "BotYalla")

    def setUp(self):
        self.ch = Mock()
        self._call = ai._call
        db.set_platform("ai_key", "test-key")
        db.activate_subscription(self.owner, "merchant")
        with db.get_conn() as c:
            c.execute("DELETE FROM ai_usage")

    def tearDown(self):
        ai._call = self._call

    def cfg(self, bid, **kw):
        c = json.loads(db.get_bot(bid)["config_json"])
        c.update(kw)
        db.update_bot_config(bid, c)

    def say(self, bid, peer, kind, text=""):
        asyncio.run(FE.handle_message(db.get_bot(bid), self.ch,
                                      {"peer": peer, "kind": kind, "text": text, "name": "منى"}))

    def capture(self, reply="تمام", action=None, suggestions=None):
        seen = {}

        def fake(provider, key, system, user):
            seen.setdefault("calls", []).append((system, user))
            return json.dumps({"reply": reply, "action": action, "suggestions": suggestions or []})
        ai._call = fake
        return seen


class WelcomeTests(Base):
    def test_ai_welcome_with_starter_buttons(self):
        self.cfg(self.bid, response_mode="ai", ai_welcome="أهلاً في رغد 👗", ai_starters=["الأسعار", "المقاسات"])
        self.say(self.bid, "wa:201000000001", "start", "مرحبا")
        self.assertEqual(self.ch.sent[-1], ("buttons", "أهلاً في رغد 👗", ["الأسعار", "المقاسات"]))

    def test_without_custom_welcome_keeps_flow_greeting(self):
        self.cfg(self.bid, response_mode="ai", ai_welcome="", ai_starters=[])
        self.say(self.bid, "tg:5", "start", "/start")
        self.assertEqual(self.ch.sent[-1], ("text", "أهلاً من الفلو!"))

    def test_official_bot_gets_platform_welcome(self):
        self.cfg(self.official, response_mode="ai", platform_kb=True, ai_welcome="", ai_starters=[])
        self.say(self.official, "wa:201000000002", "start", "مرحبا")
        kind, text, opts = self.ch.sent[-1]
        self.assertEqual(kind, "buttons")
        self.assertEqual(text, platform_kb.welcome("ar"))
        self.assertEqual(opts, platform_kb.starters("ar"))
        self.ch.sent.clear()
        self.say(self.official, "wa:201000000003", "start", "hello")
        self.assertEqual(self.ch.sent[-1][2], platform_kb.starters("en"))

    def test_customer_bot_cannot_claim_platform_welcome(self):
        self.cfg(self.bid, response_mode="ai", platform_kb=True, ai_welcome="", ai_starters=[])
        self.say(self.bid, "tg:6", "start", "/start")
        self.assertEqual(self.ch.sent[-1], ("text", "أهلاً من الفلو!"))


class BrainSalesTests(Base):
    def test_suggestions_become_buttons_and_are_cleaned(self):
        self.cfg(self.bid, response_mode="ai")
        self.capture("عندنا تفصيل وتعديل.", suggestions=["تفصيل", "تفصيل", "زر طويل جداً أكثر من عشرين حرفاً", "تعديل", "x", "y"])
        self.say(self.bid, "tg:10", "text", "بتعملوا إيه؟")
        self.assertEqual(self.ch.sent[-1], ("buttons", "عندنا تفصيل وتعديل.", ["تفصيل", "تعديل", "x"]))
        self.assertEqual(db.ai_usage_of(self.owner)["replies"], 1)

    def test_first_message_rule_only_once(self):
        self.cfg(self.bid, response_mode="ai")
        seen = self.capture("أهلاً!")
        self.say(self.bid, "tg:11", "text", "بكام التفصيل؟")
        self.say(self.bid, "tg:11", "text", "وبياخد قد إيه؟")
        first, second = seen["calls"][0][0], seen["calls"][1][0]
        self.assertIn("FIRST message", first)
        self.assertNotIn("FIRST message", second)
        self.assertIn("WhatsApp Business Messaging Policy", first)

    def test_official_bot_sees_live_prices_and_links(self):
        db.set_plan_override("merchant", 250, 10)
        self.cfg(self.official, response_mode="ai", platform_kb=True)
        seen = self.capture("الباقات…")
        self.say(self.official, "wa:201000000004", "text", "بكام الباقات؟")
        user = seen["calls"][0][1]
        facts = json.loads(user.split("<business>\n", 1)[1].split("\n</business>", 1)[0])
        self.assertEqual(facts["business_name"], "BotYalla")
        names = [p["plan"] for p in facts["platform"]["plans"]]
        self.assertEqual(names, [A.plans.PLANS[p]["name_ar"] for p in A.plans.ORDER])
        expect = A._plan_pricing("merchant")["price"]
        merchant = facts["platform"]["plans"][1]
        self.assertEqual(float(merchant["price_monthly_egp"].replace(",", "")), expect)
        self.assertEqual(facts["platform"]["links"]["signup"], "https://botyalla.test/register")
        self.assertNotIn("ai_key", user)
        self.assertNotIn("test-key", user)

    def test_customer_bot_never_gets_platform_facts(self):
        self.cfg(self.bid, response_mode="ai", platform_kb=True)
        seen = self.capture()
        self.say(self.bid, "tg:12", "text", "سؤال")
        self.assertNotIn('"platform"', seen["calls"][0][1])

    def test_optout_action_removes_from_campaigns(self):
        self.cfg(self.bid, response_mode="ai")
        self.capture("تمام، مش هنبعتلك عروض تاني.", action={"type": "optout"})
        self.say(self.bid, "wa:201000000005", "text", "كفاية رسايل لو سمحت")
        self.assertTrue(db.is_opted_out(self.bid, "wa:201000000005"))
        self.assertNotIn("wa:201000000005", db.list_bot_peers(self.bid))


class OptOutTests(Base):
    def test_stop_word_in_flow_mode(self):
        self.cfg(self.bid, response_mode="flow")
        peer = "wa:201000000006"
        self.say(self.bid, peer, "start", "مرحبا")
        self.assertIn(peer, db.list_bot_peers(self.bid))
        self.say(self.bid, peer, "cancel", "STOP")
        self.assertTrue(db.is_opted_out(self.bid, peer))
        self.assertNotIn(peer, db.list_bot_peers(self.bid))
        self.assertIn("Done", self.ch.sent[-1][1])
        self.assertIsNone(db.get_chat_state(self.bid, peer))
        self.say(self.bid, peer, "text", "تفعيل العروض")
        self.assertFalse(db.is_opted_out(self.bid, peer))
        self.assertIn(peer, db.list_bot_peers(self.bid))

    def test_arabic_stop_before_any_contact(self):
        peer = "wa:201000000007"
        self.say(self.bid, peer, "text", "إيقاف الرسائل")
        self.assertTrue(db.is_opted_out(self.bid, peer))
        self.assertIn("تم إيقاف الرسائل الترويجية", self.ch.sent[-1][1])

    def test_plain_cancel_is_not_optout(self):
        peer = "wa:201000000008"
        self.say(self.bid, peer, "start", "مرحبا")
        self.say(self.bid, peer, "cancel", "إلغاء")
        self.assertFalse(db.is_opted_out(self.bid, peer))


class RouteTests(Base):
    def client(self, uid):
        c = A.app.test_client()
        with c.session_transaction() as s:
            s["uid"] = uid; s["_csrf"] = "c" * 32
        return c

    def form(self, **kw):
        d = {"csrf_token": "c" * 32, "response_mode": "ai", "ai_consent": "1",
             "ai_welcome": "  أهلاً 👋  ", "ai_starter": ["الأسعار", "الأسعار", "زر أطول من عشرين حرفاً بكثير", ""]}
        d.update(kw)
        return d

    def test_owner_saves_welcome_and_starters_not_platform_flag(self):
        r = self.client(self.owner).post(f"/bot/{self.bid}/brain", data=self.form(platform_kb="1"))
        self.assertEqual(r.status_code, 302)
        cfg = json.loads(db.get_bot(self.bid)["config_json"])
        self.assertEqual(cfg["ai_welcome"], "أهلاً 👋")
        self.assertEqual(cfg["ai_starters"], ["الأسعار", "زر أطول من عشرين حرفاً بكثير"[:20].strip()])
        self.assertFalse(cfg.get("platform_kb"), "عميل فعّل مساعد المنصة الرسمي")

    def test_admin_toggles_official_assistant(self):
        c = self.client(1)
        c.post(f"/bot/{self.official}/brain", data=self.form(platform_kb="1"))
        self.assertTrue(json.loads(db.get_bot(self.official)["config_json"])["platform_kb"])
        c.post(f"/bot/{self.official}/brain", data=self.form())
        self.assertFalse(json.loads(db.get_bot(self.official)["config_json"])["platform_kb"])

    def test_bot_page_renders_both_languages(self):
        c = self.client(1)
        for lang in ("ar", "en"):
            c.get(f"/lang/{lang}")
            r = c.get(f"/bot/{self.official}")
            self.assertEqual(r.status_code, 200)
            self.assertIn(b'"canOfficial": true', r.data.replace(b'"canOfficial":true', b'"canOfficial": true'))


if __name__ == "__main__":
    unittest.main(verbosity=2)
