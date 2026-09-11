"""L-11 — حارس سقف البوتات وتنبيه الـ80%.

`workers=1` وكل بوتات تليجرام داخل عملية الويب نفسها، فالبوت الذي يتجاوز السقف
لا يبطئ صاحبه وحده بل كل من يشاركه العملية. الحارس يرفض عند السقف، والتنبيه
يصل **مرّة لكل عتبة جديدة** لا عند كل تشغيل — وإلا صار ضجيجاً يُتجاهَل.

    python tests/test_capacity.py
"""
import os, secrets, sys, tempfile, unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_TMPDIR = tempfile.mkdtemp(prefix="botyalla-cap-")
os.environ["BOTYALLA_DB"] = os.path.join(_TMPDIR, "test.db")   # قبل استيراد database
os.environ["BOTYALLA_UPLOADS"] = _TMPDIR
ADMIN_PW = os.environ.setdefault("ADMIN_PASS", f"tst_adm_{secrets.token_hex(8)}")
TEST_PW = f"tst_pw_{secrets.token_hex(8)}"
os.environ["ADMIN_USER"] = "admin"
os.environ["ADMIN_PASS"] = ADMIN_PW

import bot_manager                          # noqa: E402
import database as db                       # noqa: E402
import app as web                           # noqa: E402


def _boot():
    db.init_db()
    web.seed_platform_defaults()
    web.contact_defaults()
    web.seed_default_admin()
    web._migrate_ai_key()
    web.app.config["TESTING"] = True


class CapacityReadingTests(unittest.TestCase):
    """السقف يُقرأ من الإعدادات، وأي قيمة فاسدة تسقط إلى احتياطي — لا إلى بلا حدّ."""

    @classmethod
    def setUpClass(cls):
        _boot()
        cls.m = bot_manager.BotManager()

    def tearDown(self):
        db.set_platform("bot_capacity", "")

    def test_a_configured_capacity_is_used(self):
        db.set_platform("bot_capacity", "40")
        self.assertEqual(self.m.capacity(), 40)

    def test_a_broken_capacity_falls_back_instead_of_becoming_unlimited(self):
        for bad in ("", "abc", "0", "-5", "  "):
            db.set_platform("bot_capacity", bad)
            self.assertEqual(self.m.capacity(), bot_manager.CAPACITY_FALLBACK, repr(bad))

    def test_status_reports_running_capacity_and_percent(self):
        db.set_platform("bot_capacity", "10")
        self.m._apps = {i: object() for i in range(4)}
        st = self.m.capacity_status()
        self.assertEqual((st["running"], st["capacity"], st["pct"]), (4, 10, 40))
        self.assertFalse(st["warn"])
        self.assertFalse(st["full"])
        self.m._apps = {}

    def test_the_warning_flips_at_eighty_percent_exactly(self):
        db.set_platform("bot_capacity", "10")
        for n, warn in ((7, False), (8, True), (9, True), (10, True)):
            self.m._apps = {i: object() for i in range(n)}
            self.assertEqual(self.m.capacity_status()["warn"], warn, n)
        self.m._apps = {}

    def test_full_only_at_the_cap(self):
        db.set_platform("bot_capacity", "3")
        self.m._apps = {i: object() for i in range(2)}
        self.assertFalse(self.m.capacity_status()["full"])
        self.m._apps[99] = object()
        self.assertTrue(self.m.capacity_status()["full"])
        self.m._apps = {}


class StartGuardTests(unittest.TestCase):
    """الرفض عند السقف — ولا يُلمس أي بوت موجود."""

    @classmethod
    def setUpClass(cls):
        _boot()
        cls.m = bot_manager.BotManager()
        # بوت حقيقي: «غير موجود» تُفحص قبل السقف عمداً (رسالة أدقّ لمعرّف خاطئ)،
        # فاختبار الحارس يحتاج صفّاً فعلياً لا رقماً وهمياً.
        import auth
        u = db.create_user("cap_owner", auth.hash_password("cap-pw-123"))
        cls.bid = db.create_bot(u, "بوت السعة", "999:CAPTEST", "flow",
                                {"business_name": "س", "flow": None, "menu_items": []})

    def setUp(self):
        db.set_platform("bot_capacity", "2")
        self.m._apps = {}

    def tearDown(self):
        self.m._apps = {}
        db.set_platform("bot_capacity", "")

    def test_starting_at_capacity_is_refused_with_a_useful_message(self):
        self.m._apps = {9001: object(), 9002: object()}
        ok, msg = self.m.start_bot(self.bid)
        self.assertFalse(ok)
        self.assertIn("سقف", msg)
        self.assertIn("2", msg)

    def test_an_already_running_bot_is_never_blocked_by_the_cap(self):
        """من يعمل يظل يعمل: الحارس يمنع الإضافة لا يطرد القائم."""
        self.m._apps = {7: object(), 8: object()}
        ok, msg = self.m.start_bot(7)
        self.assertTrue(ok)
        self.assertIn(7, self.m._apps)

    def test_the_refusal_does_not_touch_the_running_set(self):
        self.m._apps = {9001: object(), 9002: object()}
        before = dict(self.m._apps)
        self.m.start_bot(self.bid)
        self.assertEqual(self.m._apps, before)


class AdminWarningTests(unittest.TestCase):
    """التنبيه يصل مرّة لكل عتبة جديدة — لا عند كل تشغيل."""

    @classmethod
    def setUpClass(cls):
        _boot()
        cls._orig = web.notify_admins
        cls.msgs = []
        web.notify_admins = lambda m: cls.msgs.append(m)

    @classmethod
    def tearDownClass(cls):
        web.notify_admins = cls._orig

    def setUp(self):
        type(self).msgs.clear()
        web._capacity_warned["at"] = 0
        db.set_platform("bot_capacity", "10")
        self._saved = web.manager._apps
        web.manager._apps = {}

    def tearDown(self):
        web.manager._apps = self._saved
        db.set_platform("bot_capacity", "")

    def _at(self, n):
        web.manager._apps = {i: object() for i in range(n)}
        web._warn_capacity_once()

    def test_nothing_is_sent_below_the_threshold(self):
        self._at(7)
        self.assertEqual(self.msgs, [])

    def test_one_message_at_the_threshold(self):
        self._at(8)
        self.assertEqual(len(self.msgs), 1)
        self.assertIn("80", self.msgs[0])

    def test_the_same_level_does_not_repeat(self):
        self._at(8); self._at(8); self._at(8)
        self.assertEqual(len(self.msgs), 1)

    def test_each_new_level_warns_again(self):
        self._at(8); self._at(9); self._at(10)
        self.assertEqual(len(self.msgs), 3)

    def test_dropping_below_rearms_the_warning(self):
        """أوقف بوتاً ثم عاد فارتفع — يجب أن يُنبَّه من جديد لا أن يُكتم."""
        self._at(9)
        self.assertEqual(len(self.msgs), 1)
        self._at(3)                      # نزل تحت العتبة
        self._at(9)                      # وعاد
        self.assertEqual(len(self.msgs), 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
