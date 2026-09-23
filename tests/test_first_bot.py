"""أول بوت (/start) · لحظة الترقية داخل المنتج · إقفال بوت المنصة.

    python tests/test_first_bot.py
"""
import os, secrets, sys, tempfile, time, unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_TMPDIR = tempfile.mkdtemp(prefix="botyalla-firstbot-")
os.environ["BOTYALLA_DB"] = os.path.join(_TMPDIR, "test.db")   # قبل استيراد database
os.environ["BOTYALLA_UPLOADS"] = _TMPDIR
os.environ["BOTYALLA_LOGS"] = os.path.join(_TMPDIR, "logs")
PW = "fb_" + secrets.token_hex(6)
os.environ["ADMIN_USER"] = "admin"
os.environ["ADMIN_PASS"] = PW
os.environ.setdefault("PUBLIC_URL", "https://example.test")

import database as db                      # noqa: E402
import app as web                          # noqa: E402
import activation as A                     # noqa: E402
import platform_kb as KB                   # noqa: E402
from _signup import signup                 # noqa: E402


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


_boot()


class UpgradeMomentTests(unittest.TestCase):
    """العرض يظهر عند النتيجة لا قبلها — دالّة خالصة."""

    BOT = [{"id": 1}]

    def test_nothing_before_a_first_result(self):
        self.assertIsNone(web.upgrade_moment("free", [], {}))
        self.assertIsNone(web.upgrade_moment("free", self.BOT, {"subscribers": 2, "leads": 0}))

    def test_subscribers_unlock_the_broadcast_offer(self):
        m = web.upgrade_moment("free", self.BOT, {"subscribers": 12})
        self.assertEqual(m["key"], "broadcast")
        self.assertEqual(m["n"], 12)

    def test_results_unlock_the_inbox_offer(self):
        m = web.upgrade_moment("free", self.BOT, {"leads": 2, "orders": 1, "subscribers": 3})
        self.assertEqual(m["key"], "inbox")
        self.assertEqual(m["n"], 3)

    def test_bot_limit_only_after_the_first_bot_works(self):
        self.assertIsNone(web.upgrade_moment("free", self.BOT, {"subscribers": 0}))
        m = web.upgrade_moment("free", self.BOT, {"subscribers": 6})
        self.assertEqual(m["key"], "bots")

    def test_paying_customers_are_never_nagged(self):
        for plan in ("merchant", "whatsapp", "vip", "agency"):
            self.assertIsNone(web.upgrade_moment(plan, self.BOT, {"subscribers": 99, "leads": 9}),
                              plan)

    def test_every_key_has_its_texts(self):
        import i18n
        for key in ("broadcast", "inbox", "bots"):
            for k in (f"upg_{key}_t", f"upg_{key}_d"):
                self.assertIn(k, i18n.T, k)
                self.assertTrue(i18n.T[k]["en"])


class StartPageTests(unittest.TestCase):
    """/start: طريق واحد لمن لا بوت له، ولا حصار لمن بدأ."""

    def setUp(self):
        self.c = _client()
        self.name = "u" + secrets.token_hex(3)
        self.c.post("/register", data=signup(self.name), follow_redirects=True)
        with self.c.session_transaction() as s:
            self.uid = s.get("uid")
        if self.uid:                       # بيئة فيها SMTP تحجب الحساب حتى التأكيد
            db.mark_email_verified(self.uid)

    def test_a_new_account_lands_on_start_not_the_dashboard(self):
        self.assertTrue(self.uid, "لم يُنشأ الحساب")
        r = self.c.get("/start")
        self.assertEqual(r.status_code, 200)
        self.assertIn(b'"focus": "first_bot"', r.data.replace(b'"focus":"first_bot"',
                                                              b'"focus": "first_bot"'))

    def test_whoever_has_a_bot_is_sent_back_to_the_dashboard(self):
        db.create_bot(self.uid, "بوتي", f"T:{secrets.token_hex(4)}", "store", {})
        r = self.c.get("/start")
        self.assertEqual(r.status_code, 302)
        self.assertIn("/dashboard", r.headers["Location"])

    def test_the_page_needs_a_login(self):
        anon = _client()
        r = anon.get("/start")
        self.assertIn(r.status_code, (302, 401, 403))


class NudgeTargetTests(unittest.TestCase):
    """رسالة التفعيل تفتح الخطوة الناقصة نفسها."""

    def test_links_point_at_the_missing_step(self):
        self.assertEqual(A.target("no_bot_1h", {}), "/start")
        self.assertEqual(A.target("no_bot_72h", {"ref": 0}), "/start")
        self.assertEqual(A.target("bot_off_2h", {"ref": 7}), "/bot/7")
        self.assertEqual(A.target("bot_silent_24h", {"ref": 9}), "/bot/9")
        self.assertEqual(A.target("verify_stuck_2h", {}), "/dashboard")

    def test_the_text_carries_that_link(self):
        msg = A.message("bot_silent_24h", {"username": "أحمد", "bot_name": "كافيه", "ref": 9})
        self.assertIn("https://example.test/bot/9", msg)
        msg = A.message("no_bot_1h", {"username": "أحمد"})
        self.assertIn("https://example.test/start", msg)


class PlatformBotClosesTests(unittest.TestCase):
    """كل رد ينتهي بخطوة واحدة — إلا حين يكون الردّ نفسه هو الخطوة."""

    def test_answers_end_with_one_question(self):
        tail = KB.closer().strip()
        for q in ("إيه هي بوت يلا", "بكام الباقات", "ازاي ابدا", "الدفع ازاي", "واتساب",
                  "أي كلام تاني"):
            text, _ = KB.offline_reply(q)
            self.assertIn(tail, text, q)

    def test_it_never_asks_twice(self):
        text, _ = KB.offline_reply("ازاي ابدا")
        self.assertEqual(text.count(KB.closer().strip()), 1)

    def test_a_request_for_a_human_or_a_job_is_the_answer_itself(self):
        for q in ("عايز اكلم حد", "فيه شغل عندكم؟"):
            text, _ = KB.offline_reply(q)
            self.assertNotIn(KB.closer().strip(), text, q)

    def test_the_first_button_is_the_next_step(self):
        self.assertEqual(KB.starters()[0], "اعملّي بوت لنشاطي")
        self.assertTrue(KB.starters("en")[0].lower().startswith("build"))

    def test_english_closes_in_english(self):
        text, _ = KB.offline_reply("what is botyalla", "en")
        self.assertIn(KB.closer("en").strip(), text)

    def test_the_partners_path_is_in_the_facts_and_the_notes(self):
        f = KB.facts()
        self.assertIn("partners", f)
        self.assertIn("/affiliate", f["links"].get("partners", ""))
        notes = " ".join(f["sales_notes"])
        self.assertIn("الشركاء", notes)
        self.assertIn("اقفل كل رد", notes)


if __name__ == "__main__":
    unittest.main(verbosity=2)
