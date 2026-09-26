"""CAPTCHA (Cloudflare Turnstile): مطفأ بلا مفاتيح · التسجيل ونسيت كلمة المرور دائماً ·
الدخول بعد فشل متكرر فقط وقبل فحص كلمة المرور · يفشل مغلقاً · CSP يفتح Cloudflare حين يُفعَّل.
لا شبكة: `captcha._post` مُستبدلة.

    python tests/test_captcha.py
"""
import os, secrets, sys, tempfile, unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_TMPDIR = tempfile.mkdtemp(prefix="botyalla-captcha-")
os.environ["BOTYALLA_DB"] = os.path.join(_TMPDIR, "test.db")   # قبل استيراد database/app
os.environ["BOTYALLA_UPLOADS"] = os.path.join(_TMPDIR, "uploads")
os.environ["ADMIN_USER"] = "admin"
os.environ["ADMIN_PASS"] = "Adm#" + secrets.token_hex(6)
TEST_PW = "Tst#" + secrets.token_hex(6) + "Aa1"

import auth                                # noqa: E402
import captcha as CAP                      # noqa: E402
import database as db                      # noqa: E402
import app as web                          # noqa: E402

SITE, SECRET = "1x00000000000000000000AA", "tst-" + secrets.token_hex(8)
CALLS = []


def _cf(success=True, action=None, raises=False):
    def post(data):
        CALLS.append(data)
        if raises:
            raise TimeoutError("cloudflare down")
        return {"success": success, "action": action or "", "error-codes": [] if success else ["invalid-input-response"]}
    CAP._post = post


def _on():
    os.environ["TURNSTILE_SITE_KEY"], os.environ["TURNSTILE_SECRET_KEY"] = SITE, SECRET


def _off():
    os.environ.pop("TURNSTILE_SITE_KEY", None); os.environ.pop("TURNSTILE_SECRET_KEY", None)


def _client():
    c = web.app.test_client()
    with c.session_transaction() as s:
        s["_csrf"] = "tk"
    return c


class VerifyTests(unittest.TestCase):
    def tearDown(self):
        _off(); CALLS.clear()

    def test_off_without_keys_passes_and_never_calls_out(self):
        _off(); _cf(success=False)
        self.assertTrue(CAP.verify(""))
        self.assertEqual(CALLS, [])
        self.assertEqual(CAP.csp_sources(), {})

    def test_one_key_alone_does_not_switch_it_on(self):
        os.environ["TURNSTILE_SITE_KEY"] = SITE
        self.assertFalse(CAP.configured())

    def test_fails_closed(self):
        _on()
        _cf(); self.assertFalse(CAP.verify(""), "رمز فارغ")
        _cf(success=False); self.assertFalse(CAP.verify("tok"), "رفض Cloudflare")
        _cf(raises=True); self.assertFalse(CAP.verify("tok"), "Cloudflare لا يرد")
        _cf(); self.assertFalse(CAP.verify("x" * 5000), "رمز أطول من المعقول")

    def test_action_must_match(self):
        _on(); _cf(action="login")
        self.assertFalse(CAP.verify("tok", action="register"))
        self.assertTrue(CAP.verify("tok", action="login"))

    def test_secret_and_ip_go_to_cloudflare(self):
        _on(); _cf()
        CAP.verify("tok", ip="1.2.3.4")
        self.assertEqual(CALLS[-1], {"secret": SECRET, "response": "tok", "remoteip": "1.2.3.4"})


class RouteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        db.init_db()
        web.seed_platform_defaults()
        web.contact_defaults()
        web.seed_default_admin()
        web.app.config["TESTING"] = True
        db.create_user("alice", auth.hash_password(TEST_PW))

    def setUp(self):
        web._login_attempts.clear(); CALLS.clear(); _on(); _cf(success=False)

    def tearDown(self):
        _off()

    def _login(self, pw, ip="10.0.0.1", token=None, user="alice"):
        data = {"username": user, "password": pw, "csrf_token": "tk"}
        if token:
            data[CAP.FIELD] = token
        return _client().post("/login", data=data, environ_base={"REMOTE_ADDR": ip})

    def test_widget_key_reaches_signup_and_forgot_pages(self):
        for path in ("/register", "/forgot"):
            self.assertIn(SITE, _client().get(path).get_data(as_text=True), path)

    def test_csp_opens_cloudflare_only_when_on(self):
        csp = web._build_csp()
        self.assertIn(CAP.ORIGIN, csp.split("script-src")[1].split(";")[0])
        self.assertIn(CAP.ORIGIN, csp.split("frame-src")[1].split(";")[0])
        _off()
        self.assertNotIn(CAP.ORIGIN, web._build_csp())

    def test_signup_without_a_valid_token_creates_nothing(self):
        before = db.count_users()
        r = _client().post("/register", data={"username": "bot1", "email": "b@x.io", "password": TEST_PW,
                                               "password2": TEST_PW, "csrf_token": "tk"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(db.count_users(), before)
        self.assertEqual(CALLS, [], "رمز فارغ يُرفض دون انتظار Cloudflare")

    def test_forgot_without_a_token_sends_nothing(self):
        sent = []
        orig = web._send_reset
        web._send_reset = lambda *a: sent.append(a)
        try:
            _client().post("/forgot", data={"email": "alice@x.io", "csrf_token": "tk"})
        finally:
            web._send_reset = orig
        self.assertEqual(sent, [])

    def test_first_logins_need_no_captcha(self):
        page = _client().get("/login", environ_base={"REMOTE_ADDR": "10.0.0.9"}).get_data(as_text=True)
        self.assertNotIn(SITE, page)
        self.assertEqual(self._login(TEST_PW, ip="10.0.0.9").status_code, 302)
        self.assertEqual(CALLS, [], "لا استدعاء لـ Cloudflare لمستخدم عادي")

    def test_after_failures_the_right_password_alone_is_not_enough(self):
        for _ in range(CAP.LOGIN_AFTER_FAILS):
            self._login("wrong")
        r = self._login("wrong")
        self.assertIn(SITE, r.get_data(as_text=True), "الودجت يظهر بعد الفشل المتكرر")
        self.assertEqual(self._login(TEST_PW).status_code, 200, "بلا رمز لا دخول ولو صحّت كلمة المرور")
        _cf(success=True, action="login")
        self.assertEqual(self._login(TEST_PW, token="ok").status_code, 302)

    def test_account_failures_from_other_ips_also_trigger_it(self):
        for i in range(CAP.LOGIN_AFTER_FAILS):
            self._login("wrong", ip=f"10.3.0.{i}")
        self.assertEqual(self._login(TEST_PW, ip="10.3.9.9").status_code, 200)

    def test_captcha_checked_before_the_password(self):
        """رفض CAPTCHA لا يُحتسب فشلاً في كلمة المرور ولا يكشف صحّتها."""
        for _ in range(CAP.LOGIN_AFTER_FAILS):
            self._login("wrong")
        a = self._login(TEST_PW).get_data(as_text=True)
        b = self._login("wrong").get_data(as_text=True)
        msg = "تعذّر التأكد أنك لست روبوتاً"
        self.assertIn(msg, a); self.assertIn(msg, b)
        self.assertNotIn("بيانات دخول غير صحيحة", b)


if __name__ == "__main__":
    unittest.main(verbosity=2)
