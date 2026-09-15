"""اختبارات طبقة القياس — analytics.py و`_analytics.html` و`_track_events`.

الثابت المحوري الذي تحرسه هذه الملفات:
**بلا معرّف في البيئة لا يتغيّر شيء إطلاقاً** — لا سكربت في الصفحة ولا نطاق
إضافي في CSP. وعند الضبط: لكل أداة نطاقاتها هي وحدها، وكل سكربت يحمل nonce،
و`script-src` لا يحمل 'unsafe-inline' مهما كان.

والأحداث تُطلق **مرة واحدة**: `sign_up` بعد redirect التسجيل، و`purchase` عند
أول صفحة يفتحها العميل بعد اعتماد دفعته — لا في جلسة الأدمن الذي اعتمدها.

    python tests/test_analytics.py
"""
import os, re, secrets, sys, tempfile, unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_TMPDIR = tempfile.mkdtemp(prefix="botyalla-an-")
os.environ["BOTYALLA_DB"] = os.path.join(_TMPDIR, "test.db")   # قبل استيراد database/app
os.environ["BOTYALLA_UPLOADS"] = os.path.join(_TMPDIR, "uploads")
os.environ["ADMIN_USER"] = "admin"
os.environ.setdefault("ADMIN_PASS", f"tst_adm_{secrets.token_hex(8)}")

import analytics as AN                     # noqa: E402
import auth                                # noqa: E402
import database as db                      # noqa: E402
import app as web                          # noqa: E402
from _signup import signup, STRONG_PW      # noqa: E402

_TRACK_HOSTS = ("googletagmanager.com", "google-analytics.com", "connect.facebook.net",
                "analytics.tiktok.com", "clarity.ms")


def _boot():
    db.init_db()
    web.seed_platform_defaults()
    web.contact_defaults()
    web.seed_default_admin()
    web._migrate_ai_key()
    web.app.config["TESTING"] = True


def _client():
    c = web.app.test_client()
    with c.session_transaction() as s:
        s["_csrf"] = "tk"
    return c


class _EnvTestCase(unittest.TestCase):
    """يضبط متغيّرات البيئة ويعيدها كما كانت — الوحدة تقرأها عند كل نداء."""

    KEYS = ("GTM_ID", "GA4_ID", "META_PIXEL_ID", "TIKTOK_PIXEL_ID", "CLARITY_ID",
            "SOCIAL_LINKS")

    def setUp(self):
        self._saved = {k: os.environ.get(k) for k in self.KEYS}
        for k in self.KEYS:
            os.environ.pop(k, None)

    def tearDown(self):
        for k, v in self._saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


class OffByDefaultTests(_EnvTestCase):
    """بلا ضبط: الموقع كما كان قبل إضافة القياس، حرفياً."""

    def test_nothing_is_configured(self):
        self.assertFalse(AN.configured())
        self.assertEqual(AN.csp_sources(), {})
        self.assertEqual(AN.social_links(), [])

    def test_the_policy_gains_no_source(self):
        csp = web._build_csp()
        for host in _TRACK_HOSTS:
            self.assertNotIn(host, csp, f"{host} ظهر في CSP بلا ضبط أي أداة")
        self.assertIn("connect-src 'self';", csp + ";")

    def test_no_script_is_injected(self):
        html = _client().get("/").get_data(as_text=True)
        for host in _TRACK_HOSTS:
            self.assertNotIn(host, html, f"{host} حُقن في الصفحة بلا ضبط أي أداة")

    def test_no_event_is_queued(self):
        """`queue` تصمت تماماً بلا ضبط — فلا تتضخّم كوكي الجلسة بلا فائدة."""
        s = {}
        AN.queue(s, "sign_up")
        self.assertEqual(s, {})


class PolicyTests(_EnvTestCase):
    """كل أداة تفتح نطاقاتها هي وحدها."""

    def test_each_tool_opens_only_its_own_hosts(self):
        os.environ["CLARITY_ID"] = "abcd123456"
        csp = web._build_csp()
        self.assertIn("clarity.ms", csp)
        for host in ("connect.facebook.net", "analytics.tiktok.com", "googletagmanager.com"):
            self.assertNotIn(host, csp, "ضبط Clarity وحده وسّع نطاقات أداة أخرى")

    def test_every_configured_tool_reaches_the_policy(self):
        os.environ.update({"GTM_ID": "GTM-TEST01", "GA4_ID": "G-TEST01",
                           "META_PIXEL_ID": "123456789012345",
                           "TIKTOK_PIXEL_ID": "CTEST01", "CLARITY_ID": "abcd123456"})
        csp = web._build_csp()
        for host in _TRACK_HOSTS:
            self.assertIn(host, csp, f"{host} مضبوط ولم يدخل CSP — سيُحجب بصمت")
        # وسم <noscript> في GTM إطار، فبلا frame-src لا يعمل.
        self.assertIn("frame-src", csp)

    def test_script_src_never_allows_inline(self):
        """الثابت الأهم: توسيع CSP للقياس لا يُدخل 'unsafe-inline' أبداً.

        فتحه يُبطل حماية REVIEW.md §3.1 ويعيد ثغرة الحقن المخزّنة — والمزوّدون
        يقترحونه كثيراً في وثائقهم. كل مزوّد هنا يعمل بالـnonce."""
        os.environ.update({"GTM_ID": "GTM-TEST01", "GA4_ID": "G-TEST01",
                           "META_PIXEL_ID": "123456789012345",
                           "TIKTOK_PIXEL_ID": "CTEST01", "CLARITY_ID": "abcd123456"})
        script_src = [d for d in web._build_csp().split("; ") if d.startswith("script-src ")][0]
        self.assertNotIn("unsafe-inline", script_src)
        self.assertNotIn("unsafe-eval", script_src)
        self.assertIn("'nonce-{n}'", script_src)


class InjectionTests(_EnvTestCase):
    """السكربتات المحقونة: موجودة، وكلها بالـnonce."""

    @classmethod
    def setUpClass(cls):
        _boot()

    def _page(self):
        os.environ.update({"META_PIXEL_ID": "123456789012345", "CLARITY_ID": "abcd123456"})
        return _client().get("/").get_data(as_text=True)

    def test_the_pixels_are_injected(self):
        html = self._page()
        self.assertIn("connect.facebook.net", html)
        self.assertIn("123456789012345", html)
        self.assertIn("clarity.ms", html)

    def test_every_script_tag_carries_the_nonce(self):
        """سكربت بلا nonce = سكربت محجوب. والأسوأ أنه يبدو مركّباً وهو صامت."""
        html = self._page()
        for tag in re.findall(r"<script\b[^>]*>", html):
            if "application/ld+json" in tag:
                continue
            self.assertIn("nonce=", tag, f"وسم بلا nonce سيُحجب: {tag[:90]}")

    def test_gtm_passes_the_nonce_to_the_tags_it_injects(self):
        """بدون `setAttribute('nonce')` تُحجب كل وسوم الحاوية بصمت."""
        os.environ["GTM_ID"] = "GTM-TEST01"
        html = _client().get("/").get_data(as_text=True)
        self.assertIn("GTM-TEST01", html)
        self.assertIn("setAttribute('nonce'", html)

    def test_the_dispatcher_is_present_for_client_side_events(self):
        self.assertIn("window.byTrack", self._page())


class EventTests(_EnvTestCase):
    """الأحداث تصل مرة واحدة، وفي الجلسة الصحيحة."""

    @classmethod
    def setUpClass(cls):
        _boot()

    def setUp(self):
        super().setUp()
        os.environ["META_PIXEL_ID"] = "123456789012345"
        web._login_attempts.clear()

    def test_the_queue_survives_the_redirect_and_drains_once(self):
        s = {}
        AN.queue(s, "sign_up", method="password")
        self.assertEqual(AN.drain(s)[0]["event"], "sign_up")
        self.assertEqual(AN.drain(s), [], "الحدث تكرّر — تضخيم لتحويل واحد")

    def test_the_queue_is_capped(self):
        s = {}
        for i in range(30):
            AN.queue(s, f"e{i}")
        self.assertLessEqual(len(s["_tr"]), 8, "طابور بلا سقف يضخّم كوكي الجلسة")

    def test_signup_emits_the_conversion_on_the_next_page(self):
        """التسجيل ينتهي بـredirect، فحدث يُطلق في نفس الطلب لا يصل المتصفح."""
        c = _client()
        r = c.post("/register", data=signup("anevent"), follow_redirects=True)
        self.assertEqual(r.status_code, 200)
        self.assertIn('"event": "sign_up"', r.get_data(as_text=True))

    def test_an_approved_payment_reaches_the_customer_not_the_admin(self):
        """`purchase` عند التفعيل الفعلي، وفي جلسة **العميل**.

        الاعتماد يقع في جلسة الأدمن، فلو عُلّق الحدث بها لضاع التحويل كله —
        ولَنُسب إلى زيارة الأدمن لا إلى إعلان العميل."""
        uid_ = db.create_user("payevent", auth.hash_password(STRONG_PW))
        pid = db.create_payment(uid_, "merchant", "vodafone", 299.0, "ref1", "f.png",
                                "h1", "{}")
        db.finalize_payment(pid, "approved")

        c = _client()
        with c.session_transaction() as s:
            s["uid"] = uid_
        events = None
        with web.app.test_request_context("/"):
            from flask import session as fsession
            fsession["uid"] = uid_
            events = web._track_events()
        names = [e["event"] for e in events]
        self.assertIn("purchase", names)
        purchase = [e for e in events if e["event"] == "purchase"][0]
        self.assertEqual(purchase["params"]["value"], 299.0)
        self.assertEqual(purchase["params"]["currency"], "EGP")

        # ومرة واحدة فقط: تبويبان مفتوحان لا يضاعفان التحويل (pop_setting ذرّية).
        with web.app.test_request_context("/"):
            from flask import session as fsession
            fsession["uid"] = uid_
            again = [e["event"] for e in web._track_events()]
        self.assertNotIn("purchase", again, "تحويل واحد حُسب مرتين")

    def test_a_wallet_topup_is_not_a_subscription_purchase(self):
        """شحن المحفظة ليس بيعاً لباقة — احتسابه يضخّم الإيراد في تقارير الإعلانات."""
        uid_ = db.create_user("walletevent", auth.hash_password(STRONG_PW))
        pid = db.create_payment(uid_, db.WALLET_PLAN, "vodafone", 100.0, "ref2", "f2.png",
                                "h2", "{}")
        db.finalize_payment(pid, "approved")
        self.assertIsNone(db.get_setting(uid_, "track_purchase"))

    def test_a_rejected_payment_emits_nothing(self):
        uid_ = db.create_user("rejevent", auth.hash_password(STRONG_PW))
        pid = db.create_payment(uid_, "merchant", "vodafone", 299.0, "ref3", "f3.png",
                                "h3", "{}")
        db.finalize_payment(pid, "rejected")
        self.assertIsNone(db.get_setting(uid_, "track_purchase"))


class SocialLinkTests(_EnvTestCase):
    """`sameAs` يُقرأ كتزكية منّا — فلا يُبنى من نص غير مفحوص."""

    @classmethod
    def setUpClass(cls):
        _boot()

    def test_only_known_networks_are_accepted(self):
        os.environ["SOCIAL_LINKS"] = ("https://www.facebook.com/botyalla, "
                                      "https://evil.example.com/x, http://t.me/insecure, "
                                      "https://t.me/botyalla")
        urls = [s["url"] for s in AN.social_links()]
        self.assertIn("https://www.facebook.com/botyalla", urls)
        self.assertIn("https://t.me/botyalla", urls)
        self.assertNotIn("https://evil.example.com/x", urls, "نطاق مجهول دخل sameAs")
        self.assertNotIn("http://t.me/insecure", urls, "رابط http دخل sameAs")

    def test_same_as_is_absent_until_configured(self):
        """حقل فارغ في السكيما أسوأ من غائب."""
        html = _client().get("/").get_data(as_text=True)
        self.assertNotIn("sameAs", html)

    def test_same_as_appears_once_configured(self):
        os.environ["SOCIAL_LINKS"] = "https://www.tiktok.com/@botyalla"
        html = _client().get("/").get_data(as_text=True)
        self.assertIn("sameAs", html)
        self.assertIn("tiktok.com/@botyalla", html)


if __name__ == "__main__":
    _boot()
    unittest.main(verbosity=2)
