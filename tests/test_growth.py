"""قياس الزوار داخل المنصة + ظهور ردود قوالب تليجرام في صندوق الوارد.

    python tests/test_growth.py
"""
import asyncio, os, secrets, sys, tempfile, unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_TMPDIR = tempfile.mkdtemp(prefix="botyalla-growth-")
os.environ["BOTYALLA_DB"] = os.path.join(_TMPDIR, "test.db")   # قبل استيراد database
os.environ["BOTYALLA_UPLOADS"] = _TMPDIR
PW = "gr_" + secrets.token_hex(6)
os.environ["ADMIN_USER"] = "admin"
os.environ["ADMIN_PASS"] = PW

import auth                                # noqa: E402
import database as db                      # noqa: E402
import app as web                          # noqa: E402
import flow_engine                         # noqa: E402
import templates_bot                       # noqa: E402
from telegram import ReplyKeyboardMarkup, ReplyKeyboardRemove   # noqa: E402

PHONE = {"User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0) Mobile Safari/604.1"}
DESKTOP = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/128.0 Safari/537.36"}


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


def _views(path=None):
    with db.get_conn() as c:
        if path:
            return [dict(r) for r in c.execute("SELECT * FROM page_views WHERE path=?", (path,))]
        return [dict(r) for r in c.execute("SELECT * FROM page_views")]


class PageViewTests(unittest.TestCase):
    """زيارات الصفحات العامة تُعدّ بلا كوكي تتبّع؛ الروبوتات والصفحات الخاصة لا تُعدّ."""

    @classmethod
    def setUpClass(cls):
        _boot()

    def setUp(self):
        web._login_attempts.clear()
        with db.get_conn() as c:
            c.execute("DELETE FROM page_views")

    def test_a_visit_is_counted_with_its_source_and_device(self):
        r = _client().get("/?utm_source=TikTok", headers=PHONE)
        self.assertEqual(r.status_code, 200)
        v = _views("/")
        self.assertEqual(len(v), 1)
        self.assertEqual((v[0]["src"], v[0]["device"]), ("tiktok", "mobile"))
        self.assertEqual(len(v[0]["vid"]), 16, "بصمة يومية لا IP خام")

    def test_bots_monitors_and_private_pages_are_not_counted(self):
        c = _client()
        c.get("/", headers={"User-Agent": "Googlebot/2.1"})
        c.get("/", headers={"User-Agent": "Mozilla/5.0+(compatible; UptimeRobot/2.0)"})
        c.get("/healthz", headers=DESKTOP)
        c.get("/robots.txt", headers=DESKTOP)
        self.assertEqual(_views(), [])

    def test_one_visitor_is_one_visitor_per_day(self):
        c = _client()
        for _ in range(3):
            c.get("/", headers=DESKTOP)
        c.get("/pricing", headers=DESKTOP)
        a = db.analytics_summary(7)
        self.assertEqual((a["visitors"], a["views"], a["pricing_visitors"]), (1, 4, 1))

    def test_an_external_referrer_is_kept_as_its_domain(self):
        _client().get("/", headers=dict(DESKTOP, Referer="https://www.facebook.com/groups/x"))
        self.assertEqual(_views("/")[0]["ref"], "facebook.com")


class FunnelTests(unittest.TestCase):
    """التسجيل يُنسب لأول مصدر للزائر، والقمع يُحسب على دفعة المسجّلين."""

    @classmethod
    def setUpClass(cls):
        _boot()

    def setUp(self):
        web._login_attempts.clear()

    def test_a_signup_is_attributed_to_the_first_source(self):
        c = _client()
        c.get("/?utm_source=facebook", headers=PHONE)
        c.get("/?utm_source=google", headers=PHONE)          # المصدر الأول هو المحسوب
        r = c.post("/register", data={"username": "gr_new", "password": PW, "csrf_token": "tk"})
        self.assertEqual(r.status_code, 302)
        u = db.get_user_by_name("gr_new")["id"]
        self.assertEqual(db.get_setting(u, "signup_src"), "facebook")

    def test_the_funnel_counts_each_stage_of_the_cohort(self):
        before = db.analytics_summary(30)["funnel"]
        u = db.create_user("gr_funnel", auth.hash_password(PW))
        bid = db.create_bot(u, "F", "T:gr-funnel", "flow", {"business_name": "F"})
        db.track("bot_live", u, bid)
        db.track("bot_live", u, bid)                       # المرحلة تُعدّ مرة واحدة
        db.log_message(bid, "tg:9001", "in", "customer", "سلام")
        after = db.analytics_summary(30)["funnel"]
        for k in ("signup", "bot_created", "bot_live", "first_message"):
            self.assertEqual(after[k] - before[k], 1, k)

    def test_the_page_is_for_the_owner_alone(self):
        c = _client()
        c.post("/login", data={"username": "admin", "password": PW, "csrf_token": "tk"})
        self.assertEqual(c.get("/admin/analytics?days=7").status_code, 200)
        sid = db.create_user("gr_support", auth.hash_password(PW))
        db.set_user_role(sid, "support")
        s = _client()
        s.post("/login", data={"username": "gr_support", "password": PW, "csrf_token": "tk"})
        self.assertEqual(s.get("/admin/analytics").status_code, 403)


class _Msg:
    def __init__(self):
        self.sent = []

    async def reply_text(self, text, **kw):
        self.sent.append(text)
        return object()

    async def reply_photo(self, photo, **kw):
        self.sent.append(("photo", photo))
        return object()


class _Update:
    def __init__(self, chat):
        self.message = self.effective_message = _Msg()
        self.effective_chat = type("Chat", (), {"id": chat})()


class _Ctx:
    def __init__(self, bid):
        self.application = type("App", (), {"bot_data": {"bot_id": bid, "config": {}}})()
        self.bot = None


class TemplateInboxTests(unittest.TestCase):
    """المتجر والحجز والقائمة: ردود البوت الجاهزة تظهر في صندوق الوارد كغيرها."""

    @classmethod
    def setUpClass(cls):
        _boot()
        u = db.create_user("gr_shop", auth.hash_password(PW))
        cls.bid = db.create_bot(u, "Shop", "T:gr-shop", "store", {"business_name": "Shop"})

    def _out(self):
        with db.get_conn() as c:
            return [r["text"] for r in c.execute(
                "SELECT text FROM messages WHERE bot_id=? AND direction='out' ORDER BY id", (self.bid,))]

    def test_a_template_reply_is_logged_with_its_buttons(self):
        up, ctx = _Update(555), _Ctx(self.bid)
        asyncio.run(templates_bot._say(up, ctx, "📋 تأكيد الطلب",
                                       reply_markup=ReplyKeyboardMarkup([["تأكيد", "إلغاء"]])))
        self.assertEqual(up.message.sent, ["📋 تأكيد الطلب"], "الرد نفسه أُرسل")
        self.assertIn("📋 تأكيد الطلب\n[تأكيد] · [إلغاء]", self._out())

    def test_a_plain_reply_and_the_welcome_are_logged(self):
        up, ctx = _Update(556), _Ctx(self.bid)
        asyncio.run(templates_bot._say(up, ctx, "تم الإلغاء.", reply_markup=ReplyKeyboardRemove()))
        asyncio.run(flow_engine.send_intro(up, ctx, "🛍️ أهلاً بك"))
        out = self._out()
        self.assertIn("تم الإلغاء.", out)
        self.assertIn("🛍️ أهلاً بك", out)


if __name__ == "__main__":
    unittest.main(verbosity=2)
