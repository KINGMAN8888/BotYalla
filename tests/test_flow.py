"""اختبار محرك الفلو بلا تليجرام — على قاعدة مؤقتة، لا على قاعدة الإنتاج.
    python tests/test_flow.py
"""
import asyncio, os, sys, tempfile, unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_TMP = os.path.join(tempfile.mkdtemp(prefix="botyalla-test-"), "test.db")
os.environ["BOTYALLA_DB"] = _TMP          # يجب أن يسبق استيراد database

import database as db                      # noqa: E402
import flow_engine                         # noqa: E402


class MockChannel:
    """يسجّل ما كان سيُرسل بدل إرساله."""
    def __init__(self):
        self.sent = []

    async def send_text(self, peer, text):
        self.sent.append(("text", peer, text))

    async def send_buttons(self, peer, text, options):
        self.sent.append(("buttons", peer, text, list(options)))

    async def send_image(self, peer, url, caption=None):
        self.sent.append(("image", peer, url, caption))

    async def remove_keyboard(self, peer, text):
        self.sent.append(("text", peer, text))

    def texts(self):
        return [s[2] for s in self.sent]


class FlowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        db.init_db()
        with db.get_conn() as c:
            c.execute("INSERT INTO users(id,username,pw_hash,role,created_at)"
                      " VALUES(99,'flowtest','x','user',0)")
        cls.bot_id = db.create_bot(99, "testbot", "tk-flow-test", "flow", {"business_name": "Test"})

    def setUp(self):
        self.bot = db.get_bot(self.bot_id)
        self.ch = MockChannel()
        db.clear_chat_state(self.bot_id, "tg:1")

    def send(self, kind, text=""):
        asyncio.run(flow_engine.handle_message(
            self.bot, self.ch, {"peer": "tg:1", "kind": kind, "name": "y", "text": text}))

    def test_full_flow_saves_a_lead(self):
        self.send("start", "/start")
        self.send("text", "Youssef")
        self.send("text", "010123")
        self.send("text", "Help me")
        with db.get_conn() as c:
            lead = c.execute("SELECT data_json FROM leads WHERE bot_id=? ORDER BY id DESC LIMIT 1",
                             (self.bot_id,)).fetchone()
        self.assertIsNotNone(lead, "لم يُحفظ أي lead")
        self.assertIn("Youssef", lead["data_json"])
        self.assertIsNone(db.get_chat_state(self.bot_id, "tg:1"), "الحالة لم تُمسح بعد الانتهاء")

    def test_state_survives_a_restart(self):
        """جوهر المرحلة 1: الحالة في القاعدة لا في الذاكرة."""
        self.send("start", "/start")
        self.send("text", "Youssef")
        state = db.get_chat_state(self.bot_id, "tg:1")
        self.assertEqual(state["step"], 1)
        self.assertIn("Youssef", state["data"].values())

    def test_cancel_clears_state(self):
        self.send("start", "/start")
        self.send("cancel", "/cancel")
        self.assertIsNone(db.get_chat_state(self.bot_id, "tg:1"))

    def test_stray_text_after_finishing_does_not_restart(self):
        self.send("start", "/start")
        for a in ("a", "b", "c"):
            self.send("text", a)
        self.ch.sent.clear()
        self.send("text", "شكراً")
        self.assertIsNone(db.get_chat_state(self.bot_id, "tg:1"))
        self.assertTrue(any("/start" in t for t in self.ch.texts()))

    def test_peer_is_recorded_for_broadcast(self):
        self.send("start", "/start")
        self.assertIn("tg:1", db.list_bot_peers(self.bot_id))
        self.assertIn("tg:1", db.list_bot_peers(self.bot_id, within_seconds=3600))


if __name__ == "__main__":
    unittest.main(verbosity=2)
