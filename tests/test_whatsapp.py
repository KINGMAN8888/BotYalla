"""اختبارات منطق واتساب: التطبيع، منع التكرار، عدّاد الاستهلاك، نافذة الـ24 ساعة.
    python tests/test_whatsapp.py
"""
import asyncio, os, sys, tempfile, time, unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_TMP = os.path.join(tempfile.mkdtemp(prefix="botyalla-wa-"), "test.db")
os.environ["BOTYALLA_DB"] = _TMP

import database as db                          # noqa: E402
import flow_engine                             # noqa: E402
import plans                                   # noqa: E402
from channels.whatsapp import WhatsAppChannel  # noqa: E402
import bot_manager                             # noqa: E402


def payload(*messages, phone_id="123", contact="Youssef"):
    return {"entry": [{"changes": [{"value": {
        "metadata": {"phone_number_id": phone_id},
        "contacts": [{"profile": {"name": contact}}],
        "messages": list(messages)}}]}]}


def text_msg(mid, body, frm="201001234567"):
    return {"id": mid, "from": frm, "type": "text", "text": {"body": body}}


class NormalizeTests(unittest.TestCase):
    ch = WhatsAppChannel("123", "tok")

    def test_every_message_in_a_batch_is_returned(self):
        """Meta قد تسلّم أكثر من رسالة في الدفعة — أخذ الأولى فقط يفقد إجابات."""
        msgs = self.ch.normalize_all(payload(text_msg("m1", "أحمد"), text_msg("m2", "0100")))
        self.assertEqual([m["text"] for m in msgs], ["أحمد", "0100"])
        self.assertEqual([m["id"] for m in msgs], ["m1", "m2"])

    def test_media_is_flagged_not_silently_emptied(self):
        msgs = self.ch.normalize_all(payload(
            {"id": "m3", "from": "201001234567", "type": "image", "image": {"id": "x"}}))
        self.assertEqual(msgs[0]["kind"], "unsupported")
        self.assertEqual(msgs[0]["media"], "image")

    def test_greeting_starts_the_flow(self):
        for word in ("مرحبا", "hi", "/start", "ابدأ"):
            self.assertEqual(self.ch.normalize_all(payload(text_msg("x", word)))[0]["kind"],
                             "start", word)

    def test_statuses_produce_nothing(self):
        self.assertEqual(self.ch.normalize_all(
            {"entry": [{"changes": [{"value": {"statuses": [{"status": "delivered"}]}}]}]}), [])

    def test_button_titles_over_20_chars_fall_back_to_a_numbered_list(self):
        calls = []

        class Spy(WhatsAppChannel):
            async def _post(self, p):
                calls.append(p); return {}

        long = ["خيار قصير", "خيار طويل جداً يتجاوز عشرين حرفاً بوضوح"]
        asyncio.run(Spy("1", "t").send_buttons("wa:20100", "اختر:", long))
        self.assertEqual(calls[0]["type"], "text", "الاقتطاع الصامت يكسر مطابقة الإجابة")
        self.assertIn("2. ", calls[0]["text"]["body"])

    def test_three_short_options_use_real_buttons(self):
        calls = []

        class Spy(WhatsAppChannel):
            async def _post(self, p):
                calls.append(p); return {}

        asyncio.run(Spy("1", "t").send_buttons("wa:20100", "اختر:", ["نعم", "لا", "ربما"]))
        self.assertEqual(calls[0]["type"], "interactive")
        self.assertEqual(len(calls[0]["interactive"]["action"]["buttons"]), 3)


class DedupeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        db.init_db()

    def test_a_message_id_is_accepted_once(self):
        self.assertTrue(db.mark_msg_seen("wamid.unique-1"))
        self.assertFalse(db.mark_msg_seen("wamid.unique-1"))

    def test_payload_splits_per_phone_number(self):
        pairs = bot_manager._split_wa_payload({"entry": [
            {"changes": [{"value": {"metadata": {"phone_number_id": "111"},
                                    "messages": [text_msg("a", "x")]}}]},
            {"changes": [{"value": {"metadata": {"phone_number_id": "222"},
                                    "messages": [text_msg("b", "y")]}}]}]})
        self.assertEqual([p[0] for p in pairs], ["111", "222"])


class UsageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        db.init_db()
        with db.get_conn() as c:
            c.execute("INSERT OR IGNORE INTO users(id,username,pw_hash,role,created_at)"
                      " VALUES(41,'wauser','x','user',0)")
        cls.bot_id = db.create_bot(41, "wa bot", "wa:999", "flow", {}, channel="whatsapp")

    def setUp(self):
        with db.get_conn() as c:
            c.execute("DELETE FROM usage_msgs WHERE owner_id=41")

    def test_the_counter_stops_at_the_plan_limit(self):
        for i in range(3):
            self.assertTrue(db.try_consume_msg(self.bot_id, 41, limit=3), f"رسالة {i+1}")
        self.assertFalse(db.try_consume_msg(self.bot_id, 41, limit=3),
                         "تجاوز الحدّ يعني فاتورة أكبر من الاشتراك")
        self.assertEqual(db.owner_usage(41)["sent"], 3)

    def test_no_limit_means_no_block(self):
        for _ in range(5):
            self.assertTrue(db.try_consume_msg(self.bot_id, 41, limit=None))

    def test_free_plan_has_no_whatsapp(self):
        self.assertFalse(plans.plan("free")["whatsapp"])
        self.assertEqual(plans.wa_limit("free"), 0)
        self.assertTrue(plans.plan("pro")["whatsapp"])

    def test_a_blocked_send_never_reaches_meta(self):
        """الحارس يمنع قبل أي طلب شبكة — التوكن هنا وهمي، فلو مرّ لفشل الاختبار."""
        async def deny():
            return False

        ch = WhatsAppChannel("999", "tok", on_send=deny)
        self.assertIsNone(asyncio.run(ch.send_text("wa:20100", "hi")))

    def test_an_allowed_send_reaches_the_transport(self):
        posted = []

        class Spy(WhatsAppChannel):
            async def _post(self, p):
                if self.on_send is not None and (await self.on_send()) is False:
                    return None
                posted.append(p); return {}

        async def allow():
            return db.try_consume_msg(self.bot_id, 41, limit=2)

        ch = Spy("999", "tok", on_send=allow)
        asyncio.run(ch.send_text("wa:20100", "1"))
        asyncio.run(ch.send_text("wa:20100", "2"))
        asyncio.run(ch.send_text("wa:20100", "3"))
        self.assertEqual(len(posted), 2, "الرسالة الثالثة تجاوزت الحدّ ويجب أن تُمنع")


class WindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        db.init_db()
        with db.get_conn() as c:
            c.execute("INSERT OR IGNORE INTO users(id,username,pw_hash,role,created_at)"
                      " VALUES(42,'wauser2','x','user',0)")
        cls.bot_id = db.create_bot(42, "wa bot 2", "wa:888", "flow", {}, channel="whatsapp")
        db.add_bot_user(cls.bot_id, 201001, "recent", peer="wa:201001")
        db.add_bot_user(cls.bot_id, 201002, "old", peer="wa:201002")
        with db.get_conn() as c:
            c.execute("UPDATE bot_users SET last_in_at=? WHERE peer='wa:201002'",
                      (int(time.time()) - 30 * 3600,))

    def test_broadcast_targets_only_the_24h_window(self):
        every = db.list_bot_peers(self.bot_id)
        inside = db.list_bot_peers(self.bot_id, within_seconds=bot_manager.WA_WINDOW)
        self.assertEqual(sorted(every), ["wa:201001", "wa:201002"])
        self.assertEqual(inside, ["wa:201001"],
                         "البثّ خارج النافذة يُقيّد الرقم لا الرسالة")


class EngineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        db.init_db()
        with db.get_conn() as c:
            c.execute("INSERT OR IGNORE INTO users(id,username,pw_hash,role,created_at)"
                      " VALUES(43,'wauser3','x','user',0)")
        cls.bot_id = db.create_bot(43, "wa bot 3", "wa:777", "flow", {}, channel="whatsapp")

    def setUp(self):
        self.bot = db.get_bot(self.bot_id)
        self.sent = []
        outer = self

        class Ch:
            async def send_text(self, peer, text): outer.sent.append(text)
            async def send_buttons(self, peer, text, opts): outer.sent.append(text)
            async def send_image(self, peer, url, caption=None): outer.sent.append(caption)
            async def remove_keyboard(self, peer, text): outer.sent.append(text)
        self.ch = Ch()
        db.clear_chat_state(self.bot_id, "wa:20100")

    def send(self, kind, text="", **extra):
        asyncio.run(flow_engine.handle_message(
            self.bot, self.ch, dict({"peer": "wa:20100", "kind": kind, "name": "y",
                                     "text": text}, **extra)))

    def test_media_does_not_advance_the_flow(self):
        self.send("start", "مرحبا")
        step = db.get_chat_state(self.bot_id, "wa:20100")["step"]
        self.send("unsupported", "", media="image")
        after = db.get_chat_state(self.bot_id, "wa:20100")
        self.assertEqual(after["step"], step, "الصورة حفظت إجابة فارغة وقفزت خطوة")
        self.assertEqual(after["data"], {})
        self.assertIn("نص", self.sent[-1])

    def test_a_numbered_reply_selects_the_option(self):
        cfg = {"flow": {"start_message": "أهلاً", "end_message": "تم",
                        "steps": [{"id": "s0", "type": "buttons", "var": "الخيار",
                                   "prompt": "اختر:", "options": ["أ", "ب", "ج"]}]}}
        db.update_bot_config(self.bot_id, cfg)
        self.bot = db.get_bot(self.bot_id)
        self.send("start", "مرحبا")
        self.send("text", "2")
        with db.get_conn() as c:
            lead = c.execute("SELECT data_json FROM leads WHERE bot_id=? ORDER BY id DESC LIMIT 1",
                             (self.bot_id,)).fetchone()
        self.assertIn('"ب"', lead["data_json"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
