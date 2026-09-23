"""محرّك التفعيل: من توقّف في منتصف الطريق، ومن ينتظر رداً.

    python tests/test_activation.py
"""
import os, secrets, sys, tempfile, time, unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_TMPDIR = tempfile.mkdtemp(prefix="botyalla-activation-")
os.environ["BOTYALLA_DB"] = os.path.join(_TMPDIR, "test.db")   # قبل استيراد database
os.environ["BOTYALLA_UPLOADS"] = _TMPDIR
os.environ["BOTYALLA_LOGS"] = os.path.join(_TMPDIR, "logs")
os.environ["ADMIN_PASS"] = "act_" + secrets.token_hex(6)
os.environ.setdefault("PUBLIC_URL", "https://example.test")

import database as db                      # noqa: E402
import activation as A                     # noqa: E402
import i18n                                # noqa: E402
import mailer                              # noqa: E402

HOUR, DAY = 3600, 86400


def _user(name, ago, email=None, verify=0, role="user", blocked=0):
    with db.get_conn() as c:
        c.execute("INSERT INTO users(username,pw_hash,role,created_at,email,verify_required,"
                  "is_blocked) VALUES(?,'x',?,?,?,?,?)",
                  (name, role, int(time.time()) - ago, email, verify, blocked))
    return db.get_user_by_name(name)["id"]


def _bot(owner, name, ago, active=1, token=None):
    bid = db.create_bot(owner, name, token or f"T:{secrets.token_hex(4)}", "store", {})
    with db.get_conn() as c:
        c.execute("UPDATE bots SET created_at=?, is_active=? WHERE id=?",
                  (int(time.time()) - ago, active, bid))
    return bid


class Sent:
    """بديل قناة الإرسال: يجمع ما أُرسل بدل أن يرسله."""

    def __init__(self, ok=True):
        self.ok, self.msgs = ok, []

    def __call__(self, chat, text, **k):
        self.msgs.append((str(chat), text))
        return self.ok


class CandidateTests(unittest.TestCase):
    """الاستعلامات تختار الحالة الصحيحة — لا أحداً أكثر ولا أقل."""

    @classmethod
    def setUpClass(cls):
        db.init_db()

    def setUp(self):
        with db.get_conn() as c:
            for t in ("nudge_log", "messages", "conversations", "bots", "users"):
                c.execute(f"DELETE FROM {t}")

    def test_no_bot_after_an_hour_only(self):
        fresh = _user("fresh", 10 * 60)                  # سجّل من 10 دقائق — لسه بدري
        ready = _user("ready", 2 * HOUR)
        _user("has_bot", 2 * HOUR)
        _bot(db.get_user_by_name("has_bot")["id"], "بوته", 1 * HOUR)
        ids = [r["user_id"] for r in db.activation_candidates("no_bot_1h", HOUR)]
        self.assertIn(ready, ids)
        self.assertNotIn(fresh, ids)
        self.assertEqual(len(ids), 1, "صاحب البوت لا يُلاحَق")

    def test_staff_and_blocked_are_never_nudged(self):
        _user("admin2", 2 * HOUR, role="admin")
        _user("supp", 2 * HOUR, role="support")
        _user("banned", 2 * HOUR, blocked=1)
        self.assertEqual(db.activation_candidates("no_bot_1h", HOUR), [])

    def test_old_accounts_are_left_alone(self):
        _user("ancient", 40 * DAY)
        self.assertEqual(db.activation_candidates("no_bot_1h", HOUR, A.MAX_AGE), [])

    def test_bot_created_but_never_started(self):
        u = _user("off", 5 * HOUR)
        bid = _bot(u, "بوت متوقف", 3 * HOUR, active=0)
        _bot(u, "بوت شغال", 3 * HOUR, active=1)
        rows = db.activation_candidates("bot_off_2h", 2 * HOUR)
        self.assertEqual([r["ref"] for r in rows], [bid])
        self.assertEqual(rows[0]["bot_name"], "بوت متوقف")

    def test_live_bot_with_no_customer_message(self):
        u = _user("silent", 3 * DAY)
        quiet = _bot(u, "بوت صامت", 2 * DAY)
        busy = _bot(u, "بوت شغّال", 2 * DAY)
        db.log_message(busy, "tg:5", "in", "customer", "أهلاً")
        refs = [r["ref"] for r in db.activation_candidates("bot_silent_24h", DAY)]
        self.assertEqual(refs, [quiet])

    def test_verification_stuck(self):
        u = _user("stuck", 3 * HOUR, email="s@example.test", verify=1)
        _user("done", 3 * HOUR, email="d@example.test", verify=0)
        ids = [r["user_id"] for r in db.activation_candidates("verify_stuck_2h", 2 * HOUR)]
        self.assertEqual(ids, [u])

    def test_unknown_kind_is_refused(self):
        with self.assertRaises(ValueError):
            db.activation_candidates("whatever", HOUR)


class CycleTests(unittest.TestCase):
    """الدورة: رسالة واحدة لكل حالة، ولا تُسجَّل إلا إن وصلت."""

    @classmethod
    def setUpClass(cls):
        db.init_db()
        mailer.SYNC = True

    def setUp(self):
        with db.get_conn() as c:
            for t in ("nudge_log", "messages", "conversations", "bots", "users", "settings"):
                c.execute(f"DELETE FROM {t}")
        db.set_platform("activation_nudges", "1")

    def test_one_message_per_case_forever(self):
        u = _user("u1", 2 * HOUR)
        db.set_setting(u, "tg_chat_id", "555")
        tg = Sent()
        first = A.run_cycle(tg, force=True)
        self.assertEqual(first.get("no_bot_1h"), 1)
        self.assertEqual(A.run_cycle(tg, force=True), {}, "لا تتكرر أبداً")
        self.assertEqual(len(tg.msgs), 1)
        self.assertTrue(db.nudge_sent(u, "no_bot_1h"))

    def test_nothing_is_logged_when_delivery_fails(self):
        u = _user("u2", 2 * HOUR)
        db.set_setting(u, "tg_chat_id", "555")
        dead = Sent(ok=False)
        self.assertEqual(A.run_cycle(dead, force=True), {})
        self.assertFalse(db.nudge_sent(u, "no_bot_1h"), "رسالة لم تصل تُعاد لاحقاً")
        ok = Sent()
        self.assertEqual(A.run_cycle(ok, force=True).get("no_bot_1h"), 1)

    def test_a_user_who_moved_on_gets_nothing(self):
        u = _user("u3", 30 * HOUR)
        _bot(u, "بوته", 1 * HOUR)                      # أنشأ بوتاً بعد التسجيل
        db.set_setting(u, "tg_chat_id", "555")
        out = A.run_cycle(Sent(), force=True)
        self.assertNotIn("no_bot_1h", out)
        self.assertNotIn("no_bot_24h", out)

    def test_the_message_carries_the_bot_name_and_a_link(self):
        u = _user("u4", 3 * DAY)
        db.set_setting(u, "tg_chat_id", "555")
        _bot(u, "كافيه سلام", 2 * DAY)
        tg = Sent()
        A.run_cycle(tg, force=True)
        text = "\n".join(t for _, t in tg.msgs)
        self.assertIn("كافيه سلام", text)
        self.assertIn("https://example.test", text)

    def test_every_rule_has_a_message_and_a_subject(self):
        for kind, _after, key in A.RULES:
            self.assertIn(key, i18n.T, kind)
            self.assertIn(key + "_s", i18n.T, kind)
            row = {"user_id": 1, "username": "أحمد", "email": "a@b.test", "bot_name": "بوتي"}
            for lang in ("ar", "en"):
                msg = A.message(kind, row, lang)
                self.assertNotIn("{", msg, f"{kind}/{lang}: عنصر نائب لم يُملأ")
                self.assertGreater(len(msg), 40)

    def test_quiet_hours_and_the_kill_switch(self):
        u = _user("u5", 2 * HOUR)
        db.set_setting(u, "tg_chat_id", "555")
        night = time.mktime(time.localtime()[:3] + (3, 0, 0) + time.localtime()[6:])
        self.assertTrue(A.quiet_now(night))
        self.assertEqual(A.run_cycle(Sent(), now=night), {}, "لا رسائل الثالثة فجراً")
        db.set_platform("activation_nudges", "0")
        noon = time.mktime(time.localtime()[:3] + (12, 0, 0) + time.localtime()[6:])
        self.assertEqual(A.run_cycle(Sent(), now=noon), {}, "المفتاح العام يوقفها")

    def test_email_is_used_when_there_is_no_telegram(self):
        sent = []
        old = mailer.send_mail
        mailer.send_mail = lambda to, s, h, t=None, headers=None: (sent.append((to, s, h)) or True)
        mailer.configured = lambda: True
        try:
            _user("u6", 2 * HOUR, email="u6@example.test")
            out = A.run_cycle(Sent(), force=True)
        finally:
            mailer.send_mail = old
        self.assertEqual(out.get("no_bot_1h"), 1)
        self.assertTrue(sent)
        to, subject, html = sent[0]
        self.assertEqual(to, "u6@example.test")
        self.assertTrue(subject)
        self.assertIn("<table", html, "مرّت بغلاف mailer لا نصاً خاماً")

    def test_report_counts_what_was_sent_and_who_moved(self):
        u = _user("u7", 2 * HOUR)
        db.set_setting(u, "tg_chat_id", "555")
        A.run_cycle(Sent(), force=True)
        now = int(time.time())
        rows = {r["k"]: r for r in db.nudge_counts(now - HOUR, now + HOUR)}
        self.assertEqual(rows["no_bot_1h"]["v"], 1)
        self.assertEqual(rows["no_bot_1h"]["advanced"], 0)
        _bot(u, "بوت بعد الرسالة", 0)                   # تقدّم بعد الرسالة
        rows = {r["k"]: r for r in db.nudge_counts(now - HOUR, now + HOUR)}
        self.assertEqual(rows["no_bot_1h"]["advanced"], 1)


class WaitingTests(unittest.TestCase):
    """عميل كتب ولم يُردّ عليه: تنبيه واحد لكل انتظار."""

    @classmethod
    def setUpClass(cls):
        db.init_db()

    def setUp(self):
        with db.get_conn() as c:
            for t in ("messages", "conversations", "bots", "users"):
                c.execute(f"DELETE FROM {t}")
        self.owner = _user("owner", DAY)
        self.bid = _bot(self.owner, "متجري", DAY)

    def _age(self, peer, seconds):
        with db.get_conn() as c:
            ts = int(time.time()) - seconds
            c.execute("UPDATE messages SET created_at=? WHERE bot_id=? AND peer=?",
                      (ts, self.bid, peer))
            c.execute("UPDATE conversations SET last_at=? WHERE bot_id=? AND peer=?",
                      (ts, self.bid, peer))

    def test_only_conversations_ending_on_the_customer(self):
        db.log_message(self.bid, "tg:1", "in", "customer", "حد موجود؟")
        self._age("tg:1", 30 * 60)
        db.log_message(self.bid, "tg:2", "in", "customer", "بكام؟")
        db.log_message(self.bid, "tg:2", "out", "bot", "250")
        self._age("tg:2", 30 * 60)
        peers = [c["peer"] for c in db.waiting_conversations(min_seconds=15 * 60)]
        self.assertEqual(peers, ["tg:1"])

    def test_fresh_and_ancient_waits_are_skipped(self):
        db.log_message(self.bid, "tg:3", "in", "customer", "لسه دلوقتي")
        db.log_message(self.bid, "tg:4", "in", "customer", "من يومين")
        self._age("tg:4", 3 * DAY)
        peers = [c["peer"] for c in db.waiting_conversations(min_seconds=15 * 60)]
        self.assertEqual(peers, [])

    def test_one_alert_per_wait(self):
        db.log_message(self.bid, "tg:5", "in", "customer", "فين الرد؟")
        self._age("tg:5", 30 * 60)
        calls = []
        alert = lambda bot, peer, head, detail: (calls.append((peer, head)) or True)
        self.assertEqual(A.waiting_cycle(alert, min_seconds=15 * 60), 1)
        self.assertEqual(A.waiting_cycle(alert, min_seconds=15 * 60), 0, "لا تنبيه مكرر")
        self.assertIn("متجري", calls[0][1])
        # رسالة جديدة من العميل = انتظار جديد يستحق تنبيهاً
        with db.get_conn() as c:                       # التنبيه الأول كان قبل ساعة
            c.execute("UPDATE conversations SET waiting_alert_at=? WHERE bot_id=?",
                      (int(time.time()) - 3600, self.bid))
        db.log_message(self.bid, "tg:5", "in", "customer", "؟؟")
        self._age("tg:5", 20 * 60)
        self.assertEqual(A.waiting_cycle(alert, min_seconds=15 * 60), 1)

    def test_a_conversation_taken_over_by_a_human_is_not_alerted(self):
        db.log_message(self.bid, "tg:6", "in", "customer", "مستني")
        db.set_conversation_mode(self.bid, "tg:6", "human")
        self._age("tg:6", 30 * 60)
        self.assertEqual(db.waiting_conversations(min_seconds=15 * 60), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
