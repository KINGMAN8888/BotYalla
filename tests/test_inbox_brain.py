"""صندوق الوارد والتدخّل اليدوي (§5) + «عقل البوت» (§4) — بلا تليجرام ولا نموذج حقيقي.
    python tests/test_inbox_brain.py
"""
import asyncio, json, os, sys, tempfile, time, unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_TMP = tempfile.mkdtemp(prefix="botyalla-inbox-")
os.environ["BOTYALLA_DB"] = os.path.join(_TMP, "t.db")        # قبل أي استيراد
os.environ["BOTYALLA_UPLOADS"] = _TMP
os.environ["BOTYALLA_LOGS"] = _TMP

import database as db          # noqa: E402
import flow_engine as FE       # noqa: E402
import ai_agent as ai          # noqa: E402
import app as A                # noqa: E402
from bot_manager import manager  # noqa: E402


class Mock:
    def __init__(self):
        self.sent = []

    async def send_text(self, p, t): self.sent.append(("text", t))
    async def send_buttons(self, p, t, o): self.sent.append(("buttons", t, list(o)))
    async def send_image(self, p, u, caption=None): self.sent.append(("image", caption))
    async def remove_keyboard(self, p, t): self.sent.append(("text", t))
    async def fetch_media(self, m): return None, None

    def texts(self):
        return [s[1] for s in self.sent]


FLOW = {"start_message": "أهلاً!", "end_message": "شكراً!", "steps": [
    {"id": "s0", "type": "buttons", "prompt": "الخدمة؟", "var": "الخدمة", "options": ["تفصيل", "تعديل"]},
    {"id": "s1", "type": "question", "prompt": "اسمك؟", "var": "الاسم"}]}


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        db.init_db()
        # الفئات تتشارك قاعدة الملف — الإعداد يجب أن يكون متكرّر الأمان
        with db.get_conn() as c:
            c.execute("INSERT OR IGNORE INTO users(id,username,pw_hash,role,created_at) VALUES(1,'root','x','admin',0)")
            c.execute("INSERT OR IGNORE INTO users(username,pw_hash,role,created_at) VALUES('shop','x','user',0)")
        cls.owner = db.get_user_by_name("shop")["id"]
        mine = [b for b in db.list_bots(cls.owner) if b["name"] == "shop"]
        cls.bid = mine[0]["id"] if mine else db.create_bot(
            cls.owner, "shop", "tk-inbox", "customer_service",
            {"business_name": "رغد", "flow": FLOW, "products": [{"name": "فستان سهرة", "price": 1500}]})

    def setUp(self):
        self.ch = Mock()
        self._call = ai._call

    def tearDown(self):
        ai._call = self._call

    def row(self):
        return db.get_bot(self.bid)

    def cfg(self, **kw):
        c = json.loads(self.row()["config_json"])
        c.update(kw)
        db.update_bot_config(self.bid, c)

    def say(self, peer, kind, text=""):
        asyncio.run(FE.handle_message(self.row(), self.ch, {"peer": peer, "kind": kind, "text": text, "name": "منى"}))


class InboxTests(Base):
    def test_everything_is_logged(self):
        self.say("tg:1", "start", "/start src-poster")
        self.say("tg:1", "text", "تفصيل")
        msgs = db.list_messages(self.bid, "tg:1")
        self.assertEqual([m["direction"] for m in msgs][:1], ["in"])
        self.assertTrue(any(m["sender"] == "bot" for m in msgs))
        self.assertEqual(db.source_counts(self.bid).get("poster"), 1)
        conv = db.get_conversation(self.bid, "tg:1")
        self.assertEqual(conv["name"], "منى")
        self.assertGreaterEqual(conv["unread"], 2)

    def test_takeover_silences_bot_and_notifies_once(self):
        self.say("tg:2", "start", "/start")
        db.set_conversation_mode(self.bid, "tg:2", "human")
        db.mark_conversation_read(self.bid, "tg:2")
        notes = []

        async def fake_notify(bot_row, channel, text):
            notes.append(text)
        orig = FE.notify_owner
        FE.notify_owner = fake_notify
        try:
            self.ch.sent.clear()
            self.say("tg:2", "text", "في حد هنا؟")
            self.say("tg:2", "text", "رد عليا")
        finally:
            FE.notify_owner = orig
        self.assertEqual(self.ch.sent, [], "البوت ردّ رغم تولّي صاحب النشاط")
        self.assertEqual(len(notes), 1, "تنبيه لكل رسالة بدل واحد للدفعة")

    def test_forgotten_takeover_returns_to_bot(self):
        self.say("tg:3", "start", "/start")
        db.set_conversation_mode(self.bid, "tg:3", "human")
        with db.get_conn() as c:
            c.execute("UPDATE conversations SET human_at=? WHERE bot_id=? AND peer=?",
                      (int(time.time()) - FE.HUMAN_IDLE - 5, self.bid, "tg:3"))
        self.ch.sent.clear()
        self.say("tg:3", "text", "تفصيل")
        self.assertTrue(self.ch.sent, "المحادثة لم تعد للبوت بعد 12 ساعة")
        self.assertEqual(db.get_conversation(self.bid, "tg:3")["mode"], "bot")

    def test_old_messages_purged(self):
        db.log_message(self.bid, "tg:9", "in", "customer", "قديمة")
        with db.get_conn() as c:
            c.execute("UPDATE messages SET created_at=0 WHERE peer='tg:9'")
        self.assertGreaterEqual(db.purge_old_messages(), 1)


class InboxRouteTests(Base):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.c = A.app.test_client()
        with cls.c.session_transaction() as s:
            s["uid"] = cls.owner; s["_csrf"] = "c" * 32
        db.add_bot_user(cls.bid, 77, "Ali", peer="tg:77")

    def post(self, url, body):
        return self.c.post(url, json=body, headers={"X-CSRF-Token": "c" * 32})

    def test_free_plan_reads_but_cannot_reply(self):
        with db.get_conn() as c:                     # فئات أخرى فعّلت باقة مدفوعة
            c.execute("DELETE FROM subscriptions WHERE user_id=?", (self.owner,))
        self.assertEqual(self.c.get(f"/bot/{self.bid}/inbox").status_code, 200)
        r = self.post(f"/bot/{self.bid}/inbox/send", {"peer": "tg:77", "text": "أهلاً"})
        self.assertEqual(r.status_code, 403)

    def test_paid_reply_takes_over(self):
        db.activate_subscription(self.owner, "merchant")
        sent = []
        orig = manager.send_to_peer
        manager.send_to_peer = lambda bid, peer, text=None, asset=None: (sent.append((peer, text)) or (True, None))
        try:
            d = self.post(f"/bot/{self.bid}/inbox/send", {"peer": "tg:77", "text": "أهلاً يا علي"}).get_json()
        finally:
            manager.send_to_peer = orig
        self.assertTrue(d["ok"])
        self.assertEqual(sent, [("tg:77", "أهلاً يا علي")])
        self.assertEqual(db.get_conversation(self.bid, "tg:77")["mode"], "human")
        self.assertEqual(db.list_messages(self.bid, "tg:77")[-1]["sender"], "human")

    def test_unknown_peer_and_other_owner_refused(self):
        self.assertEqual(self.post(f"/bot/{self.bid}/inbox/send", {"peer": "tg:404", "text": "x"}).status_code, 404)
        self.assertEqual(self.post(f"/bot/{self.bid}/inbox/send", {"peer": "../etc", "text": "x"}).status_code, 404)
        other = A.app.test_client()
        with other.session_transaction() as s:
            s["uid"] = 1; s["_csrf"] = "d" * 32
        r = other.get(f"/api/bot/{self.bid}/inbox/thread?peer=tg:77")
        self.assertEqual(r.status_code, 404, "صاحب نشاط آخر قرأ المحادثة")

    def test_whatsapp_window_enforced(self):
        db.activate_subscription(self.owner, "whatsapp")
        wa = db.create_bot(self.owner, "wa", "wa:5550001", "customer_service", {"business_name": "x"}, "whatsapp")
        db.add_bot_user(wa, 201000000001, "Sara", peer="wa:201000000001")
        with db.get_conn() as c:
            c.execute("UPDATE bot_users SET last_in_at=? WHERE bot_id=?", (int(time.time()) - 90000, wa))
        d = self.post(f"/bot/{wa}/inbox/send", {"peer": "wa:201000000001", "text": "مرحبا"}).get_json()
        self.assertFalse(d["ok"])
        self.assertTrue(d.get("window"))


class BrainTests(Base):
    def setUp(self):
        super().setUp()
        db.set_platform("ai_key", "test-key")
        db.activate_subscription(self.owner, "merchant")
        with db.get_conn() as c:
            c.execute("DELETE FROM ai_usage")
            c.execute("DELETE FROM wallet")

    def test_ai_mode_replies_and_records_lead(self):
        self.cfg(response_mode="ai")
        ai._call = lambda *a: json.dumps({"reply": "أهلاً يا منى! سجلت طلبك.",
                                          "action": {"type": "lead", "data": {"الاسم": "منى", "التليفون": "010"}}})
        before = len(db.list_leads(self.bid))
        self.say("tg:20", "text", "عايزة أفصّل فستان")
        self.assertIn("أهلاً يا منى! سجلت طلبك.", self.ch.texts())
        self.assertEqual(len(db.list_leads(self.bid)), before + 1)
        self.assertEqual(db.ai_usage_of(self.owner)["replies"], 1)
        self.assertEqual(db.list_messages(self.bid, "tg:20")[-1]["sender"], "ai")

    def test_exhausted_allowance_uses_wallet_then_falls_back(self):
        self.cfg(response_mode="ai")
        ai._call = lambda *a: json.dumps({"reply": "رد ذكي", "action": None})
        m = time.strftime("%Y-%m")
        with db.get_conn() as c:
            c.execute("INSERT INTO ai_usage(owner_id,month,replies) VALUES(?,?,500)", (self.owner, m))
        db.wallet_topup(self.owner, FE.ai_reply_price())            # يكفي رداً واحداً
        self.say("tg:21", "text", "سؤال 1")
        self.assertIn("رد ذكي", self.ch.texts())
        self.assertEqual(db.wallet_balance(self.owner), 0)
        self.assertEqual(db.ai_usage_of(self.owner)["paid"], 1)
        self.ch.sent.clear()
        self.say("tg:21", "text", "سؤال 2")
        self.assertNotIn("رد ذكي", self.ch.texts(), "رد بلا حصة ولا رصيد")
        self.assertIn("الخدمة؟", self.ch.texts(), "لم يرجع للفلو")

    def test_provider_failure_falls_back_and_is_not_charged(self):
        self.cfg(response_mode="ai")
        def boom(*a): raise OSError("down")
        ai._call = boom
        self.say("tg:22", "text", "مرحبا")
        self.assertIn("الخدمة؟", self.ch.texts())
        self.assertEqual(db.ai_usage_of(self.owner)["replies"], 0)

    def test_free_plan_never_uses_ai(self):
        self.cfg(response_mode="ai")
        with db.get_conn() as c:
            c.execute("DELETE FROM subscriptions WHERE user_id=?", (self.owner,))
        ai._call = lambda *a: json.dumps({"reply": "لا يجب", "action": None})
        self.say("tg:23", "text", "مرحبا")
        self.assertNotIn("لا يجب", self.ch.texts())

    def test_hybrid_answers_question_inside_buttons_step(self):
        self.cfg(response_mode="hybrid")
        seen = {}

        def fake(provider, key, system, user):
            seen["system"] = system
            return json.dumps({"reply": "التفصيل بياخد أسبوع.", "action": {"type": "lead", "data": {"x": "y"}}})
        ai._call = fake
        self.say("tg:24", "start", "/start")
        leads = len(db.list_leads(self.bid))
        self.ch.sent.clear()
        self.say("tg:24", "text", "التفصيل بياخد قد إيه؟")
        self.assertEqual(self.ch.sent[0], ("text", "التفصيل بياخد أسبوع."))
        self.assertEqual(self.ch.sent[1][0], "buttons", "الأزرار لم تُعرض من جديد")
        self.assertEqual(len(db.list_leads(self.bid)), leads, "الهجين سجّل lead بأداة غير مسموحة")
        self.assertIn("form step", seen["system"])

    def test_order_total_comes_from_saved_prices(self):
        ai._call = lambda *a: json.dumps({"reply": "تم", "action": {
            "type": "order", "items": [{"name": "فستان سهرة", "qty": 2}, {"name": "منتج وهمي", "qty": 1}],
            "customer": "منى", "phone": "010", "address": "القاهرة", "total": 1}})
        self.cfg(response_mode="ai")
        self.say("tg:25", "text", "عايزة فستانين")
        o = db.list_orders(self.bid)[0]
        self.assertEqual(o["total"], 3000.0, "المجموع لم يُحسب من أسعار المنصة")
        self.assertEqual([i["name"] for i in o["items"]], ["فستان سهرة"])

    def test_injected_action_types_are_dropped(self):
        self.assertIsNone(ai._clean_action({"type": "delete_all"}, ai.ALL_ACTIONS))
        self.assertIsNone(ai._clean_action({"type": "lead", "data": {}}, ai.ALL_ACTIONS))
        self.assertIsNone(ai._clean_action({"type": "lead", "data": {"a": "b"}}, ai.HYBRID_ACTIONS))

    def test_handoff_alerts_but_keeps_answering(self):
        # 2026-09-19: التحويل كان يُسكت البوت 12 ساعة فيلقى العميل صمتاً حتى يرد أحد. الآن
        # التنبيه يصل والبوت يكمل؛ التولّي الفعلي يبدأ بأول رد بشري (test_paid_reply_takes_over).
        self.cfg(response_mode="ai")
        ai._call = lambda *a: json.dumps({"reply": "بلّغت الفريق وهيرد عليك هنا.", "action": {"type": "handoff"}})
        self.say("tg:26", "text", "عايز أكلم حد")
        self.assertNotEqual((db.get_conversation(self.bid, "tg:26") or {}).get("mode"), "human")
        ai._call = lambda *a: json.dumps({"reply": "لسه معاك، اسأل براحتك.", "action": None})
        self.say("tg:26", "text", "طب الأسعار؟")
        self.assertIn("لسه معاك، اسأل براحتك.", self.ch.texts())

    def test_concurrent_allowance_edge_is_atomic(self):
        m = time.strftime("%Y-%m")
        with db.get_conn() as c:
            c.execute("INSERT OR REPLACE INTO ai_usage(owner_id,month,replies,paid) VALUES(?,?,9,0)", (self.owner, m))
        grants = [db.ai_reply_allow(self.owner, 10, 0) for _ in range(3)]
        self.assertEqual(grants, ["included", None, None])


if __name__ == "__main__":
    unittest.main(verbosity=2)
