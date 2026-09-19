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
            # واتساب كبوت المالك الحقيقي — ويختبر أن حملته لا تشمل زوّار تليجرام
            return mine[0]["id"] if mine else db.create_bot(
                owner, name, token, "customer_service", {"business_name": biz, "flow": FLOW},
                channel="whatsapp")
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
        c = json.loads(db.get_bot(self.official)["config_json"])
        c.pop("ai_menu", None)                  # الافتراضي: قائمة البداية مفعّلة لمساعد المنصة
        db.update_bot_config(self.official, c)
        self.say(self.official, "wa:201000000002", "start", "مرحبا")
        kind, text, opts = self.ch.sent[-1]
        self.assertEqual(kind, "buttons")
        self.assertEqual(text, platform_kb.welcome("ar"))
        self.assertEqual(opts, FE._menu_labels("ar"), "مساعد المنصة يبدأ بقائمة «محتاج إيه؟»")
        self.ch.sent.clear()
        self.say(self.official, "wa:201000000003", "start", "hello")
        self.assertEqual(self.ch.sent[-1][2], FE._menu_labels("en"))

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


class ReliabilityTests(Base):
    def _post(self, outcomes, seen):
        orig = ai._post_json

        def fake(url, payload, headers, timeout=30):
            seen.append(url.split("/models/")[-1].split(":")[0] if "/models/" in url else payload.get("model"))
            o = outcomes.pop(0)
            if isinstance(o, Exception):
                raise o
            return o
        ai._post_json = fake
        self.addCleanup(setattr, ai, "_post_json", orig)

    def test_busy_model_falls_back_to_the_next(self):
        seen = []
        ok = {"candidates": [{"content": {"parts": [{"text": '{"reply":"x"}'}]}}]}
        self._post([ai.AIError("HTTP 429: quota", retry=True), ok], seen)
        self.assertEqual(ai.call_gemini("k", "s", "u"), '{"reply":"x"}')
        self.assertEqual(seen, list(ai.GEMINI_MODELS[:2]))

    def test_bad_key_is_not_retried_and_explains_why(self):
        seen = []
        self._post([ai.AIError("HTTP 400: API key not valid", retry=False)], seen)
        ok, msg = ai.check_key("gemini", "bad")
        self.assertFalse(ok)
        self.assertIn("API key not valid", msg)
        self.assertEqual(len(seen), 1)

    def test_key_travels_in_header_not_url(self):
        captured = {}
        orig = ai._post_json

        def fake(url, payload, headers, timeout=30):
            captured.update(url=url, headers=headers)
            return {"candidates": [{"content": {"parts": [{"text": "{}"}]}}]}
        ai._post_json = fake
        self.addCleanup(setattr, ai, "_post_json", orig)
        ai.call_gemini("SECRET", "s", "u")
        self.assertNotIn("SECRET", captured["url"])
        self.assertEqual(captured["headers"]["x-goog-api-key"], "SECRET")

    def test_chain_moves_to_next_free_provider_and_cools_the_limited_one(self):
        ai._cool.clear()
        seen = []
        orig = ai._post_json

        def fake(url, payload, headers, timeout=30):
            seen.append(payload.get("model") or url.split("/models/")[-1].split(":")[0])
            if "groq" in url:
                raise ai.AIError("HTTP 429: rate limit", retry=True)
            if "cerebras" in url:
                raise ai.AIError("HTTP 401: invalid api key")
            return {"choices": [{"message": {"content": '<think>hmm</think> sure: {"reply":"أهلاً"} done'}}]}
        ai._post_json = fake
        self.addCleanup(setattr, ai, "_post_json", orig)
        chain = [{"p": "groq", "key": "g", "models": ["a", "b"]},
                 {"p": "cerebras", "key": "c", "models": ["x", "y"]},
                 {"p": "openrouter", "key": "o", "models": ["free-1"]}]
        self.assertEqual(ai._loads(ai._call("auto", chain, "s", "u")), {"reply": "أهلاً"})
        self.assertEqual(seen, ["a", "b", "x", "free-1"], "مفتاح مرفوض يجب أن يتخطّى نماذج مزوّده كلها")
        seen.clear()
        ai._call("auto", chain, "s", "u")                    # Groq مبرَّد دقيقة: لا يُنتظر رفضه
        self.assertEqual(seen, ["x", "free-1"])
        ai._cool.clear()

    def test_key_chain_order_and_legacy_key(self):
        vals = {"ai_provider": "gemini", "ai_key": "old", "ai_key_nvidia": "n",
                "ai_key_groq": "g", "ai_models_groq": '["gpt-oss"]'}
        chain = ai.key_chain(lambda k, d=None: vals.get(k, d))
        self.assertEqual([(x["p"], x["key"]) for x in chain], [("gemini", "old"), ("groq", "g"), ("nvidia", "n")])
        self.assertEqual(chain[1]["models"], ["gpt-oss"])
        self.assertEqual(ai.key_chain(lambda k, d=None: d), [])

    def test_discover_keeps_available_models(self):
        orig = ai._get_json
        self.addCleanup(setattr, ai, "_get_json", orig)
        ai._get_json = lambda url, h, timeout=20: {"data": [{"id": "llama-3.3-70b-versatile"},
                                                             {"id": "whisper-large"}]}
        self.assertEqual(ai.discover("groq", "k"), ["llama-3.3-70b-versatile"])
        ai._get_json = lambda url, h, timeout=20: {"data": [{"id": "vendor/new-model:free"},
                                                             {"id": "vendor/embed:free"}]}
        self.assertEqual(ai.discover("openrouter", "k"), ["vendor/new-model:free"])

    def test_customer_escapes_fallback_flow_when_ai_returns(self):
        self.cfg(self.bid, response_mode="ai")
        peer = "tg:40"

        def boom(*a): raise ai.AIError("HTTP 503: overloaded", retry=True)
        ai._call = boom
        self.say(self.bid, peer, "text", "بكام؟")
        self.assertIn("اسمك؟", [s[1] for s in self.ch.sent])
        self.assertIsNotNone(db.get_chat_state(self.bid, peer))
        self.assertIn("overloaded", json.loads(db.get_platform("ai_last_error"))["msg"])
        self.capture("التفصيل بـ 1500.")
        self.say(self.bid, peer, "text", "طب بكام التفصيل؟")
        self.assertEqual(self.ch.sent[-1], ("text", "التفصيل بـ 1500."))
        self.assertIsNone(db.get_chat_state(self.bid, peer), "العميل ما زال عالقاً في الفلو")

    def test_official_bot_answers_offline_instead_of_flow(self):
        self.cfg(self.official, response_mode="ai", platform_kb=True)

        def boom(*a): raise ai.AIError("HTTP 429", retry=True)
        ai._call = boom
        peer = "wa:201000000041"
        self.say(self.official, peer, "text", "الباقات والأسعار")
        texts = " ".join(str(s[1]) for s in self.ch.sent)
        self.assertNotIn("اسمك", texts)
        for pid in A.plans.ORDER:
            self.assertIn(A.plans.PLANS[pid]["name_ar"], texts)
        self.assertIsNone(db.get_chat_state(self.official, peer))
        self.say(self.official, peer, "text", "ابدأ مجاناً")
        self.assertIn("https://botyalla.test/register", self.ch.sent[-1][1])
        self.say(self.official, peer, "text", "عايز أكلم موظف")
        self.assertIn("فريقنا", self.ch.sent[-1][1])
        self.assertNotEqual(db.get_conversation(self.official, peer)["mode"], "human",
                            "التحويل أسكت البوت قبل أي رد بشري")

    def test_missing_key_is_recorded(self):
        self.cfg(self.bid, response_mode="ai")
        db.set_platform("ai_key", "")
        self.say(self.bid, "tg:42", "text", "سؤال")
        self.assertIn("no platform AI key", json.loads(db.get_platform("ai_last_error"))["msg"])


class ThanksRatingTests(Base):
    def setUp(self):
        super().setUp()
        FE._rating_asked.clear(); FE._comment_wait.clear()
        self.cfg(self.bid, response_mode="ai", ai_rating=True)
        self.seen = self.capture("أهلاً!")

    def test_thanks_asks_rating_without_ai_then_records_it(self):
        peer = "wa:201000000050"
        self.say(self.bid, peer, "text", "بكام؟")
        calls = len(self.seen["calls"])
        self.say(self.bid, peer, "text", "شكراً ليك 🙏")
        self.assertEqual(len(self.seen["calls"]), calls, "الشكر استدعى النموذج")
        self.assertEqual(self.ch.sent[-1][0], "buttons")
        self.assertEqual(self.ch.sent[-1][2], FE.RATING["ar"])
        self.say(self.bid, peer, "text", "ممتاز 🌟")
        self.assertIn("شكراً لتقييمك", self.ch.sent[-1][1])
        self.assertGreaterEqual(db.rating_summary(self.bid)["great"], 1)
        # شكر ثانٍ خلال 24 ساعة: «العفو» بلا تقييم جديد
        self.say(self.bid, peer, "text", "شكرا")
        self.assertEqual(self.ch.sent[-1], ("text", "العفو 🙏 تحت أمرك في أي وقت."))

    def test_low_rating_collects_note_as_lead(self):
        peer = "wa:201000000051"
        self.say(self.bid, peer, "text", "سؤال")
        self.say(self.bid, peer, "text", "متشكر")
        leads = len(db.list_leads(self.bid))
        self.say(self.bid, peer, "text", "محتاج تحسين")
        self.assertIn("إيه اللي نقدر نحسّنه", self.ch.sent[-1][1])
        self.say(self.bid, peer, "text", "الرد كان بطيء")
        self.assertEqual(len(db.list_leads(self.bid)), leads + 1)
        self.assertIn("الرد كان بطيء", json.dumps(db.list_leads(self.bid)[0], ensure_ascii=False))

    def test_thanks_with_question_goes_to_ai_and_rating_word_is_not_hijacked(self):
        peer = "wa:201000000052"
        self.say(self.bid, peer, "text", "أهلاً")
        n, before = len(self.seen["calls"]), db.rating_summary(self.bid)["total"]
        self.say(self.bid, peer, "text", "شكرا بس بكام الباقة؟")
        self.say(self.bid, peer, "text", "ممتاز 🌟")        # بلا طلب تقييم ← سؤال عادي
        self.assertEqual(len(self.seen["calls"]), n + 2)
        self.assertEqual(db.rating_summary(self.bid)["total"], before)

    def test_rating_can_be_turned_off(self):
        self.cfg(self.bid, ai_rating=False)
        peer = "wa:201000000053"
        self.say(self.bid, peer, "text", "سؤال")
        self.say(self.bid, peer, "text", "thanks")
        self.assertEqual(self.ch.sent[-1][0], "text")


class RelayTests(Base):
    def setUp(self):
        super().setUp()
        import inbox_relay
        self.R = inbox_relay
        inbox_relay._last_alert.clear()
        db.set_platform("admin_chat_id", "999")
        self.alerts, self.sent = [], []

        async def notify(chat, text, reply_markup=None):
            self.alerts.append((chat, text)); return True

        async def send(row, peer, text=None, asset=None):
            self.sent.append((row["id"], peer, text)); return True, None
        from bot_manager import manager
        self.m = manager
        self._orig = (manager.notify_text_async, manager._send_to_peer)
        manager.notify_text_async, manager._send_to_peer = notify, send

    def tearDown(self):
        super().tearDown()
        self.m.notify_text_async, self.m._send_to_peer = self._orig

    def test_handoff_alerts_admin_with_tag_and_bot_keeps_going(self):
        self.cfg(self.official, response_mode="ai", platform_kb=True)
        self.capture("بلّغت الفريق.", action={"type": "handoff", "reason": "يطلب موظف"})
        peer = "wa:201000000060"
        self.say(self.official, peer, "text", "عايز أكلم حد")
        self.assertEqual(len(self.alerts), 1)
        chat, text = self.alerts[0]
        self.assertEqual(chat, "999")
        self.assertIn(self.R.tag(self.official, peer), text)
        self.assertIn("عايز أكلم حد", text)
        self.assertNotEqual((db.get_conversation(self.official, peer) or {}).get("mode"), "human")
        self.say(self.official, peer, "text", "لسه محتاج حد")   # تنبيه واحد كل 20 دقيقة
        self.assertEqual(len(self.alerts), 1)

    def test_owner_replies_from_telegram(self):
        peer = "wa:201000000061"
        db.add_bot_user(self.official, 201000000061, "x", peer=peer)
        ok, note = asyncio.run(self.R.relay_reply(self.official, peer, 999, "أهلاً، معاك يوسف"))
        self.assertTrue(ok, note)
        self.assertEqual(self.sent[-1], (self.official, peer, "أهلاً، معاك يوسف"))
        self.assertEqual(db.get_conversation(self.official, peer)["mode"], "human")
        self.assertEqual(db.list_messages(self.official, peer)[-1]["sender"], "human")
        self.assertTrue(self.R.back_to_bot(self.official, peer, 999))
        self.assertEqual(db.get_conversation(self.official, peer)["mode"], "bot")

    def test_stranger_cannot_reply_even_with_the_tag(self):
        peer = "wa:201000000062"
        db.add_bot_user(self.official, 201000000062, "x", peer=peer)
        ok, _ = asyncio.run(self.R.relay_reply(self.official, peer, 12345, "hack"))
        self.assertFalse(ok)
        self.assertEqual(self.sent, [])
        self.assertFalse(self.R.back_to_bot(self.official, peer, 12345))
        # أدمن المنصة لا يرد على بوت عميل عادي
        ok, _ = asyncio.run(self.R.relay_reply(self.bid, peer, 999, "x"))
        self.assertFalse(ok)

    def test_whatsapp_window_applies(self):
        peer = "wa:201000000063"
        db.add_bot_user(self.official, 201000000063, "x", peer=peer)
        with db.get_conn() as c:
            c.execute("UPDATE bot_users SET last_in_at=0 WHERE peer=?", (peer,))
        ok, note = asyncio.run(self.R.relay_reply(self.official, peer, 999, "مرحبا"))
        self.assertFalse(ok)
        self.assertIn("24", note)

    def test_parse(self):
        self.assertEqual(self.R.parse("...\n#C12:wa:2010"), (12, "wa:2010"))
        self.assertEqual(self.R.parse("#C3:tg:-100"), (3, "tg:-100"))
        self.assertIsNone(self.R.parse("#T5"))


class PlatformTelegramTests(Base):
    def test_official_bot_lookup(self):
        self.cfg(self.official, response_mode="ai", platform_kb=True)
        self.assertEqual(platform_kb.official_bot()["id"], self.official)
        self.cfg(self.official, response_mode="flow")
        self.assertIsNone(platform_kb.official_bot())

    def test_whatsapp_campaign_skips_telegram_visitors(self):
        db.add_bot_user(self.official, 777001, "tg visitor", peer="tg:777001")
        db.add_bot_user(self.official, 201000000070, "wa", peer="wa:201000000070")
        peers = db.list_bot_peers(self.official)
        self.assertIn("wa:201000000070", peers)
        self.assertNotIn("tg:777001", peers)
        self.assertNotIn(777001, db.list_bot_user_ids(self.official))

    def test_telegram_visitor_reply_goes_through_platform_bot(self):
        from bot_manager import manager
        sent = []

        class FakeBot:
            async def send_message(self, chat_id, text, reply_markup=None):
                sent.append((chat_id, text))

        class FakeApp:
            bot = FakeBot()
        orig = manager._platform
        manager._platform = FakeApp()
        try:
            ok, err = asyncio.run(manager._send_to_peer(db.get_bot(self.official), "tg:555", "مرحبا"))
        finally:
            manager._platform = orig
        self.assertTrue(ok, err)
        self.assertEqual(sent, [(555, "mرحبا".replace("m", "م"))])

    def test_whatsapp_read_receipt_is_requested(self):
        self.cfg(self.bid, response_mode="ai")
        self.capture("تمام")
        marked = []

        class WA(Mock):
            async def mark_read(self, mid, typing=True): marked.append(mid)
        self.ch = WA()
        asyncio.run(FE.handle_message(db.get_bot(self.bid), self.ch,
                                      {"id": "wamid.X", "peer": "wa:201000000071", "kind": "text",
                                       "text": "سؤال", "name": "x"}))
        self.assertEqual(marked, ["wamid.X"])


class MenuEscalationTests(Base):
    def setUp(self):
        super().setUp()
        FE._rating_asked.clear()
        import inbox_relay
        inbox_relay._last_alert.clear()
        db.set_platform("admin_chat_id", "999")
        self.alerts = []

        async def notify(chat, text, reply_markup=None):
            self.alerts.append(text); return True
        from bot_manager import manager
        self.m, self._orig = manager, manager.notify_text_async
        manager.notify_text_async = notify
        self.cfg(self.official, response_mode="ai", platform_kb=True, ai_menu=True, ai_max_turns=10)

    def tearDown(self):
        super().tearDown()
        self.m.notify_text_async = self._orig

    def test_support_choice_answers_instantly_then_ai_knows_the_goal(self):
        seen = self.capture("جرّب تسجيل خروج ودخول.")
        peer = "wa:201000000080"
        self.say(self.official, peer, "start", "مرحبا")
        self.say(self.official, peer, "text", "🛠 دعم فني")
        self.assertEqual(seen.get("calls"), None, "اختيار القائمة استدعى النموذج")
        self.assertIn("إيميل حسابك", self.ch.sent[-1][1])
        self.say(self.official, peer, "text", "مش عارف أدخل حسابي")
        self.assertIn("TECH SUPPORT", seen["calls"][0][0])

    def test_learn_more_goes_to_ai_with_pitch_goal(self):
        seen = self.capture("BotYalla بتعمل بوت لنشاطك.")
        peer = "wa:201000000081"
        self.say(self.official, peer, "start", "مرحبا")
        self.say(self.official, peer, "text", "💡 اعرف أكتر")
        system, user = seen["calls"][0]
        self.assertIn("LEARN MORE", system)
        self.assertIn("عايز أعرف أكتر", user)

    def test_goal_reached_closes_with_rating(self):
        orig = ai._call
        ai._call = lambda *a: json.dumps({"reply": "الرابط: https://x — بالتوفيق!", "done": True})
        peer = "wa:201000000082"
        self.say(self.official, peer, "start", "مرحبا")
        self.say(self.official, peer, "text", "عايز أسجل")
        self.assertEqual(self.ch.sent[-1], ("buttons", "الرابط: https://x — بالتوفيق!", FE.RATING["ar"]))
        ai._call = orig

    def test_too_many_messages_hand_the_chat_to_the_owner(self):
        seen = self.capture("رد")
        peer = "wa:201000000083"
        self.say(self.official, peer, "start", "مرحبا")
        for i in range(10):
            self.say(self.official, peer, "text", f"سؤال عشوائي {i}")
        calls = len(seen["calls"])
        self.say(self.official, peer, "text", "وسؤال كمان")
        self.assertEqual(len(seen["calls"]), calls, "الرسالة الزائدة استدعت النموذج بدل التحويل")
        self.assertIn("فريقنا", self.ch.sent[-1][1])
        self.assertTrue(FE.human_active(self.official, peer))
        self.assertTrue(any("محتاجة تدخّلك" in a for a in self.alerts))
        self.say(self.official, peer, "text", "ألو؟")        # البوت ساكت أثناء التحويل
        self.assertEqual(len(seen["calls"]), calls)
        # لم يرد أحد خلال نصف ساعة ← يرجع للبوت
        with db.get_conn() as c:
            c.execute("UPDATE conversations SET human_at=human_at-? WHERE peer=?", (FE.ESCALATE_HOLD + 5, peer))
        self.assertFalse(FE.human_active(self.official, peer))

    def test_ai_escalate_action_transfers(self):
        self.capture("هوصّلك بحد من الفريق يكمل معاك.", action={"type": "escalate", "reason": "أسئلة عشوائية"})
        peer = "wa:201000000084"
        self.say(self.official, peer, "text", "سؤال")
        self.assertTrue(FE.human_active(self.official, peer))
        self.assertTrue(any("أسئلة عشوائية" in a for a in self.alerts))

    def test_three_off_topic_messages_in_a_row_transfer_without_charge(self):
        FE._off_topic.clear()
        orig = ai._call
        self.addCleanup(setattr, ai, "_call", orig)
        ai._call = lambda *a: json.dumps({"reply": "أنا متخصص في BotYalla.", "on_topic": False})
        peer = "wa:201000000085"
        self.say(self.official, peer, "text", "بتحب الكورة؟")
        self.say(self.official, peer, "text", "اعملي نكتة")
        self.assertFalse(FE.human_active(self.official, peer))
        used = db.ai_usage_of(1)["replies"]
        self.say(self.official, peer, "text", "الجو حر")
        self.assertTrue(FE.human_active(self.official, peer))
        self.assertIn("فريقنا", self.ch.sent[-1][1])
        self.assertEqual(db.ai_usage_of(1)["replies"], used, "رد لم يُرسل احتُسب")
        # سؤال عن النشاط بين الرسائل يصفّر العدّاد
        peer2 = "wa:201000000086"
        for t, on in (("x", False), ("y", False), ("بكام؟", True), ("z", False), ("w", False)):
            ai._call = (lambda o: (lambda *a: json.dumps({"reply": "رد", "on_topic": o})))(on)
            self.say(self.official, peer2, "text", t)
        self.assertFalse(FE.human_active(self.official, peer2))

    def test_whatsapp_shows_four_options_as_a_list(self):
        from channels.whatsapp import WhatsAppChannel
        calls = []

        class Spy(WhatsAppChannel):
            async def _post(self, p):
                calls.append(p); return {}
        asyncio.run(Spy("1", "t").send_buttons("wa:20100", "محتاج إيه؟", FE._menu_labels("ar")))
        self.assertEqual(calls[0]["interactive"]["type"], "list")
        rows = calls[0]["interactive"]["action"]["sections"][0]["rows"]
        self.assertEqual([r["title"] for r in rows], FE._menu_labels("ar"))
        norm = WhatsAppChannel("1", "t")._one({"from": "20100", "id": "w", "type": "interactive",
                                               "interactive": {"type": "list_reply",
                                                               "list_reply": {"id": "row_0", "title": "🛠 دعم فني"}}}, "x")
        self.assertEqual(norm["text"], "🛠 دعم فني")


class LandingOfficialBotsTests(Base):
    def test_landing_shows_official_whatsapp_and_telegram_with_qr(self):
        self.cfg(self.official, response_mode="ai", platform_kb=True, bot_username="+20 128 127 5886")
        db.set_platform("platform_tg_username", "BotYallaMainbot")
        c = A.app.test_client()
        for lang in ("ar", "en"):
            c.get(f"/lang/{lang}")
            r = c.get("/")
            self.assertEqual(r.status_code, 200)
            html = r.get_data(as_text=True)
            self.assertIn("https://wa.me/201281275886?text=", html)
            self.assertIn("https://t.me/BotYallaMainbot?start=site", html)
            self.assertIn('id="official"', html)                      # نسخة الخادم للفهرسة
        with A.app.test_request_context():
            bots = A._official_bots("ar")
        self.assertTrue(bots["wa"]["qr"] and set("".join(bots["wa"]["qr"])) <= {"0", "1"})
        self.assertEqual(bots["tg"]["handle"], "@BotYallaMainbot")

    def test_section_hidden_when_nothing_is_configured(self):
        self.cfg(self.official, response_mode="flow")
        db.set_platform("platform_tg_username", "")
        db.set_platform("official_wa_number", "")
        with A.app.test_request_context():
            self.assertEqual(A._official_bots("ar"), {})
        self.assertNotIn('id="official"', A.app.test_client().get("/").get_data(as_text=True))

    def test_telegram_menu_is_two_columns(self):
        from channels.telegram import _rows
        self.assertEqual(_rows(["a", "b", "c", "d"]), [["a", "b"], ["c", "d"]])
        self.assertEqual(_rows(["a", "b"]), [["a"], ["b"]])

    def test_platform_bot_branding_calls_telegram(self):
        import platform_bot
        calls = []

        class FakeBot:
            async def set_my_description(self, **kw): calls.append(("desc", kw.get("language_code")))
            async def set_my_short_description(self, **kw): calls.append(("short", kw.get("language_code")))
            async def set_my_commands(self, commands, **kw):
                calls.append(("cmds", [c.command for c in commands], "scope" in kw))
        db.set_platform("admin_chat_id", "999")
        asyncio.run(platform_bot.brand(FakeBot()))
        self.assertIn(("desc", None), calls)
        self.assertIn(("desc", "en"), calls)
        admin = [c for c in calls if c[0] == "cmds" and c[2]]
        self.assertIn("stats", admin[0][1])
        public = [c for c in calls if c[0] == "cmds" and not c[2]]
        self.assertNotIn("stats", public[0][1])
        self.assertEqual(public[0][1][:2], ["start", "menu"])


class GrowthTests(Base):
    """شرائح الإعلانات · الموافقة على العروض · صفحات الهبوط · روابط الحملات."""
    def setUp(self):
        super().setUp()
        FE._rating_asked.clear(); FE._optin_asked.clear()
        self.cfg(self.official, response_mode="ai", platform_kb=True, ai_menu=True,
                 bot_username="+20 128 127 5886", ai_rating=True)
        db.set_platform("platform_tg_username", "BotYallaMainbot")

    def test_whatsapp_segment_link_starts_with_segment_welcome_and_source(self):
        from channels.whatsapp import WhatsAppChannel
        import segments
        msg = WhatsAppChannel("1", "t")._one({"from": "201000000090", "id": "w1", "type": "text",
                                              "text": {"body": segments.wa_text("gold")}}, "Ali")
        self.assertEqual((msg["kind"], msg["start_arg"]), ("start", "seg-gold"))
        asyncio.run(FE.handle_message(db.get_bot(self.official), self.ch, msg))
        self.assertIn("الذهب", self.ch.sent[-1][1])
        self.assertEqual(self.ch.sent[-1][2], FE._menu_labels("ar"))
        self.assertGreaterEqual(db.source_counts(self.official).get("seg_gold", 0), 1)
        # الرد التالي يعرف نشاط العميل
        seen = self.capture("تمام")
        self.say(self.official, "wa:201000000090", "text", "بكام؟")
        self.assertIn("gold/jewelry", seen["calls"][0][1])

    def test_unknown_tag_is_a_plain_message(self):
        from channels.whatsapp import WhatsAppChannel
        msg = WhatsAppChannel("1", "t")._one({"from": "2", "id": "w", "type": "text",
                                              "text": {"body": "مرحبا #hacker"}}, "x")
        self.assertEqual(msg["kind"], "start")
        self.assertIsNone(FE._start_source(msg["text"], msg.get("start_arg")))

    def test_good_rating_asks_optin_and_stop_removes_it(self):
        peer = "wa:201000000091"
        self.capture("تمام")
        self.say(self.official, peer, "text", "سؤال")
        self.say(self.official, peer, "text", "شكرا")
        self.say(self.official, peer, "text", "ممتاز 🌟")
        self.assertEqual(self.ch.sent[-1][2], FE.OPTIN["ar"])
        self.say(self.official, peer, "text", "✅ أيوه ابعتلي")
        self.assertTrue(db.bot_user_optin(self.official, peer))
        self.assertGreaterEqual(db.optin_stats(self.official)["optin"], 1)
        self.say(self.official, peer, "text", "إيقاف الرسائل")
        self.assertFalse(db.bot_user_optin(self.official, peer), "الإيقاف لم يُسقط الموافقة")

    def test_optin_word_without_question_is_not_consent(self):
        peer = "wa:201000000092"
        self.capture("تمام")
        self.say(self.official, peer, "text", "سؤال")
        self.say(self.official, peer, "text", "✅ أيوه ابعتلي")
        self.assertFalse(db.bot_user_optin(self.official, peer))

    def test_segment_pages_render_and_are_listed(self):
        import segments
        c = A.app.test_client()
        for lang in ("ar", "en"):
            c.get(f"/lang/{lang}")
            for code in segments.ORDER:
                r = c.get(f"/for/{code}")
                self.assertEqual(r.status_code, 200, code)
                html = r.get_data(as_text=True)
                self.assertIn(segments.text(code, lang)["h1"], html)
                self.assertIn(f"seg-{code}", html)                           # رابط تليجرام بالشريحة
                self.assertIn("%23" + code, html)                            # رابط واتساب «#code»
        self.assertEqual(c.get("/for/unknown").status_code, 404)
        self.assertEqual(c.get("/for/<script>").status_code, 404)
        sm = c.get("/sitemap.xml").get_data(as_text=True)
        self.assertIn("/for/market", sm)
        self.assertIn("/for/gold", c.get("/").get_data(as_text=True))

    def test_admin_growth_page_links_and_qr(self):
        c = A.app.test_client()
        with c.session_transaction() as s:
            s["uid"] = 1; s["_csrf"] = "c" * 32
        r = c.get("/admin/growth")
        self.assertEqual(r.status_code, 200)
        html = r.get_data(as_text=True)
        self.assertIn("utm_source=ads_market", html)
        q = c.get("/admin/growth/qr/market/wa.svg")
        self.assertEqual(q.status_code, 200)
        self.assertEqual(q.mimetype, "image/svg+xml")
        self.assertEqual(c.get("/admin/growth/qr/nope/wa.svg").status_code, 404)
        u = A.app.test_client()
        with u.session_transaction() as s:
            s["uid"] = self.owner; s["_csrf"] = "c" * 32
        self.assertIn(u.get("/admin/growth").status_code, (302, 403))

    def test_optins_export(self):
        peer = "wa:201000000093"
        db.add_bot_user(self.official, 201000000093, "Mona", peer=peer)
        db.set_optin(self.official, peer, True)
        c = A.app.test_client()
        with c.session_transaction() as s:
            s["uid"] = 1; s["_csrf"] = "c" * 32
        csv_text = c.get(f"/bot/{self.official}/export/optins").get_data(as_text=True)
        self.assertIn("201000000093", csv_text)
        self.assertIn("Mona", csv_text)


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

    def test_admin_tests_the_keys(self):
        c = self.client(1)
        orig = ai.check_provider
        self.addCleanup(setattr, ai, "check_provider", orig)
        ai.check_provider = lambda p, k: {"provider": p, "name": p, "ok": True, "msg": "OK",
                                          "model": "m-1", "models": ["m-1", "m-2"], "ms": 900}
        r = c.post("/settings/ai-test", headers={"X-CSRF-Token": "c" * 32})
        self.assertTrue(r.get_json()["ok"])
        self.assertEqual(json.loads(db.get_platform("ai_models_gemini")), ["m-1", "m-2"])

        ai.check_provider = lambda p, k: {"provider": p, "name": p, "ok": False,
                                          "msg": f"HTTP 400: API key not valid {k}", "model": "",
                                          "models": None, "ms": 0}
        r = c.post("/settings/ai-test", headers={"X-CSRF-Token": "c" * 32})
        self.assertFalse(r.get_json()["ok"])
        self.assertIn("API key not valid", r.get_json()["msg"])
        self.assertNotIn("test-key", r.get_json()["msg"])
        self.assertEqual(c.get("/settings").status_code, 200)
        owner = self.client(self.owner).post("/settings/ai-test", headers={"X-CSRF-Token": "c" * 32})
        self.assertIn(owner.status_code, (302, 403))

    def test_admin_saves_several_free_providers(self):
        c = self.client(1)
        c.post("/settings", data={"csrf_token": "c" * 32, "ai_provider": "groq", "ai_key_groq": " gsk_1 ",
                                  "ai_key_cerebras": "csk_2", "ai_key_gemini": "test-key",
                                  "ai_key_openrouter": "", "ai_key_nvidia": ""})
        chain = ai.key_chain(db.get_platform)
        self.assertEqual([x["p"] for x in chain], ["groq", "cerebras", "gemini"])
        self.assertEqual(chain[0]["key"], "gsk_1")
        self.assertEqual(db.get_platform("ai_key"), "gsk_1")
        c.post("/settings", data={"csrf_token": "c" * 32, "ai_provider": "evil", "ai_key_gemini": "test-key",
                                  "ai_key_groq": "", "ai_key_cerebras": ""})
        self.assertEqual(db.get_platform("ai_provider"), "gemini")
        db.set_platform("ai_provider", "gemini")
        self.assertEqual(db.get_platform("ai_key"), "test-key")

    def test_bot_page_renders_both_languages(self):
        c = self.client(1)
        for lang in ("ar", "en"):
            c.get(f"/lang/{lang}")
            r = c.get(f"/bot/{self.official}")
            self.assertEqual(r.status_code, 200)
            self.assertIn(b'"canOfficial": true', r.data.replace(b'"canOfficial":true', b'"canOfficial": true'))


if __name__ == "__main__":
    unittest.main(verbosity=2)
