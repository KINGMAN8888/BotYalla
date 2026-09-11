"""اختبارات التحصينات من REVIEW.md §3 و§4.

تغطّي: ذرّية تسوية الدفعة · تحديد المحاولات على التسجيل وفحص أكواد الخصم ·
فصل عدّادات المحاولات وتنظيفها · قيود اسم المستخدم · عدم لمس القرص بملف
ليس صورة.

    python tests/test_hardening.py
"""
import os, secrets, sys, tempfile, unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_TMPDIR = tempfile.mkdtemp(prefix="botyalla-hard-")
os.environ["BOTYALLA_DB"] = os.path.join(_TMPDIR, "test.db")   # قبل استيراد database/app
os.environ["BOTYALLA_UPLOADS"] = os.path.join(_TMPDIR, "uploads")
ADMIN_PW = os.environ.setdefault("ADMIN_PASS", f"tst_adm_{secrets.token_hex(8)}")
TEST_PW = f"tst_pw_{secrets.token_hex(8)}"
os.environ["ADMIN_USER"] = "admin"
os.environ["ADMIN_PASS"] = ADMIN_PW

import auth                                # noqa: E402
import database as db                      # noqa: E402
import payments as pay                     # noqa: E402
import app as web                          # noqa: E402


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


class SettlementAtomicityTests(unittest.TestCase):
    """§3.2 — البتّ والتفعيل والكود والعمولة في معاملة واحدة."""

    @classmethod
    def setUpClass(cls):
        _boot()
        cls.uid = db.create_user("settler", auth.hash_password(TEST_PW))

    def test_a_crash_mid_settlement_rolls_the_decision_back(self):
        """لا تبقى دفعة «معتمدة» بلا اشتراك مفعَّل."""
        pid = db.create_payment(self.uid, "whatsapp", "instapay", 899, "R", "s.png", "HX", "{}")
        before = db.get_subscription(self.uid)["plan"]
        orig = db.credit_referral
        db.credit_referral = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("crash"))
        try:
            with self.assertRaises(RuntimeError):
                db.finalize_payment(pid, "approved")
        finally:
            db.credit_referral = orig
        self.assertEqual(db.get_payment(pid)["status"], "pending", "كان يجب التراجع عن البتّ")
        self.assertEqual(db.get_subscription(self.uid)["plan"], before, "لا ترقية بلا تسوية مكتملة")

    def test_the_same_payment_settles_cleanly_after_recovery(self):
        pid = db.create_payment(self.uid, "merchant", "instapay", 299, "R2", "s2.png", "HY", "{}")
        self.assertIsNotNone(db.finalize_payment(pid, "approved"))
        sub = db.get_subscription(self.uid)
        self.assertEqual((sub["plan"], sub["status"]), ("merchant", "active"))

    def test_a_decided_payment_is_never_settled_twice(self):
        pid = db.create_payment(self.uid, "merchant", "instapay", 299, "R3", "s3.png", "HZ", "{}")
        self.assertIsNotNone(db.finalize_payment(pid, "approved"))
        self.assertIsNone(db.finalize_payment(pid, "approved"), "البتّ مرة واحدة فقط")


class RateLimitTests(unittest.TestCase):
    """§3.3 و§3.4 — الحدود وفصل العدّادات وتنظيفها."""

    @classmethod
    def setUpClass(cls):
        _boot()

    def setUp(self):
        web._login_attempts.clear()
        web._last_prune = 0

    def test_registration_is_throttled(self):
        c = _client()
        blocked = 0
        for i in range(8):
            r = c.post("/register", data={"username": f"zz{i}", "password": TEST_PW,
                                          "csrf_token": "tk"}, follow_redirects=True)
            if "انتظر قليلاً" in r.get_data(as_text=True):
                blocked += 1
        self.assertGreater(blocked, 0, "التسجيل بلا حدّ يسمح بإغراق المنصة بحسابات")

    def test_the_promo_endpoint_is_throttled(self):
        db.create_user("promoprobe", auth.hash_password(TEST_PW))
        c = _client()
        c.post("/login", data={"username": "promoprobe", "password": TEST_PW,
                               "csrf_token": "tk"})
        codes = [c.post("/api/promo/check", json={"plan": "merchant", "code": f"GUESS{i}"},
                        headers={"X-CSRF-Token": "tk"}).status_code for i in range(25)]
        self.assertIn(429, codes, "فحص الأكواد بلا حدّ يصبح أداة تخمين آلي")

    def test_buckets_do_not_share_a_counter(self):
        """استهلاك رصيد التسجيل يجب ألا يقفل الدخول."""
        for _ in range(9):
            web._rate_limited("1.2.3.4", limit=5, window=600, bucket="register")
        self.assertFalse(web._rate_limited("1.2.3.4", limit=8, window=300, bucket="login"))

    def test_expired_entries_are_pruned(self):
        """القاموس لا ينمو بلا حدّ مع كل IP جديد."""
        web._login_attempts[("login", "9.9.9.9")] = (3, 0)   # قديم جداً
        web._last_prune = 0
        web._rate_limited("1.1.1.1", bucket="login")
        self.assertNotIn(("login", "9.9.9.9"), web._login_attempts)

    def test_pruning_respects_each_buckets_own_window(self):
        """نداء دلو الدخول (نافذة 5 دقائق) لا يمسح عدّاد التسجيل (نافذة 10)
        وهو في منتصفه — وإلا صار حدّ التسجيل فعلياً نصف قيمته."""
        import time
        web._rate_limited("5.5.5.5", limit=5, window=600, bucket="register")
        web._login_attempts[("register", "5.5.5.5")] = (5, int(time.time()) - 400)
        web._last_prune = 0
        web._rate_limited("1.1.1.1", bucket="login")          # نافذة 300
        self.assertIn(("register", "5.5.5.5"), web._login_attempts)
        self.assertTrue(web._rate_limited("5.5.5.5", limit=5, window=600, bucket="register"),
                        "العدّاد باقٍ فالمحاولة السادسة تُحجب")


class UsernameRuleTests(unittest.TestCase):
    """§4.2 — الاسم محصور في محارف آمنة، لا الطول وحده."""

    @classmethod
    def setUpClass(cls):
        _boot()

    def setUp(self):
        web._login_attempts.clear()

    def test_markup_in_a_username_is_refused(self):
        c = _client()
        c.post("/register", data={"username": "<script>bad</script>", "password": TEST_PW,
                                  "csrf_token": "tk"}, follow_redirects=True)
        self.assertIsNone(db.get_user_by_name("<script>bad</script>"))

    def test_ordinary_names_still_pass(self):
        for name in ("client_1", "متجر.النور", "abc", "a-b.c_9"):
            self.assertTrue(web.USERNAME_RE.match(name), name)

    def test_too_short_or_too_long_is_refused(self):
        self.assertFalse(web.USERNAME_RE.match("ab"))
        self.assertFalse(web.USERNAME_RE.match("x" * 33))

    def test_spaces_and_control_characters_are_refused(self):
        for bad in ("a b", "a\tb", "a\nb", 'a"b', "a/b", "a\\b", "abc\n"):
            self.assertFalse(web.USERNAME_RE.match(bad), repr(bad))

    def test_invisible_arabic_format_characters_are_refused(self):
        """علامة الاتجاه والتنسيق والتشكيل تصنع اسماً يطابق «admin» بصرياً."""
        for bad in ("admin؜", "؀abc", "abc۝", "مَتجر", "admin‏"):
            self.assertFalse(web.USERNAME_RE.match(bad), repr(bad))
        for ok in ("محمد_٢٠٢٦", "گل.فروشی", "ةىيءأإآؤئ"):
            self.assertTrue(web.USERNAME_RE.match(ok), ok)

    def test_a_legacy_username_can_still_change_its_password(self):
        """حساب سُجّل قبل USERNAME_RE: النموذج يعيد إرسال اسمه كما هو، وهذا
        يجب ألا يمنعه من تغيير كلمة المرور."""
        db.create_user("old name@x.com", auth.hash_password(TEST_PW))
        c = _client()
        c.post("/login", data={"username": "old name@x.com", "password": TEST_PW,
                               "csrf_token": "tk"})
        c.post("/account", data={"username": "old name@x.com", "new_password": "newpass456",
                                 "current_password": TEST_PW, "csrf_token": "tk"})
        row = db.get_user_by_name("old name@x.com")
        self.assertTrue(auth.verify_password("newpass456", row["pw_hash"]))


class FirstVisitCsrfTests(unittest.TestCase):
    """جلسة فارغة (زائر جديد · بعد الخروج) يجب أن تخرج صفحتها بتوكن صالح.
    باقي الاختبارات تزرع `_csrf` مسبقاً فلم تلتقط هذا — اكتُشف في المتصفح."""

    @classmethod
    def setUpClass(cls):
        _boot()
        db.create_user("visitor", auth.hash_password(TEST_PW))

    def setUp(self):
        web._login_attempts.clear()

    @staticmethod
    def _page_token(c, path):
        import re
        html = c.get(path).get_data(as_text=True)
        return re.search(r'"csrf": "([^"]*)"', html).group(1)

    def test_a_fresh_visitor_can_sign_in_on_the_first_try(self):
        c = web.app.test_client()                     # بلا أي جلسة
        tok = self._page_token(c, "/login")
        self.assertTrue(tok, "BY.csrf فارغ في أول زيارة")
        r = c.post("/login", data={"username": "visitor", "password": TEST_PW, "csrf_token": tok})
        self.assertEqual(r.status_code, 302)

    def test_a_fresh_visitor_can_register_on_the_first_try(self):
        c = web.app.test_client()
        tok = self._page_token(c, "/register")
        r = c.post("/register", data={"username": "firsttry", "password": TEST_PW, "csrf_token": tok})
        self.assertNotEqual(r.status_code, 400)
        self.assertIsNotNone(db.get_user_by_name("firsttry"))

    def test_signing_back_in_after_logout_works_on_the_first_try(self):
        c = web.app.test_client()
        c.post("/login", data={"username": "visitor", "password": TEST_PW,
                               "csrf_token": self._page_token(c, "/login")})
        c.get("/logout")                              # يمسح الجلسة كلها
        r = c.post("/login", data={"username": "visitor", "password": TEST_PW,
                                   "csrf_token": self._page_token(c, "/login")})
        self.assertEqual(r.status_code, 302)


class ReceiptWriteOrderTests(unittest.TestCase):
    """§4.3 — ما ليس صورة لا يلمس القرص إطلاقاً."""

    @classmethod
    def setUpClass(cls):
        _boot()
        cls.uid = db.create_user("uploader", auth.hash_password(TEST_PW))
        os.makedirs(web.UPLOAD_DIR, exist_ok=True)

    def setUp(self):
        web._login_attempts.clear()

    def test_a_non_image_is_rejected_without_writing_a_file(self):
        import io
        before = set(os.listdir(web.UPLOAD_DIR))
        c = _client()
        c.post("/login", data={"username": "uploader", "password": TEST_PW,
                               "csrf_token": "tk"})
        c.post("/subscribe/merchant", data={
            "method": "instapay", "ref": "R",
            "screenshot": (io.BytesIO(b"MZ\x90\x00 not an image at all"), "evil.png"),
            "csrf_token": "tk"}, content_type="multipart/form-data", follow_redirects=True)
        self.assertEqual(set(os.listdir(web.UPLOAD_DIR)), before, "الملف المرفوض كُتب على القرص")
        self.assertEqual(db.list_payments(self.uid), [], "لا يُنشأ طلب دفع لملف ليس صورة")

    def test_validate_bytes_and_validate_image_agree(self):
        """المسار الجديد (بايتات) والقديم (مسار) يجب ألا يفترقا في الحكم."""
        data = b"\x89PNG\r\n\x1a\n" + b"\x00" * 4096
        p = os.path.join(web.UPLOAD_DIR, "agree.png")
        with open(p, "wb") as f:
            f.write(data)
        try:
            self.assertEqual(pay.validate_bytes(data)["ok"], pay.validate_image(p)["ok"])
            self.assertTrue(pay.validate_bytes(data)["ok"])
        finally:
            os.remove(p)


class ContentSecurityPolicyTests(unittest.TestCase):
    """§3.1 — CSP بـ nonce تُبطل أثر أي سكربت محقون."""

    @classmethod
    def setUpClass(cls):
        _boot()
        cls.pages = ("/landing", "/login", "/register")

    def _csp(self, r):
        return r.headers.get("Content-Security-Policy", "")

    def test_every_page_carries_a_policy(self):
        c = _client()
        for p in self.pages:
            self.assertIn("script-src", self._csp(c.get(p)), p)

    def test_script_src_has_no_unsafe_inline(self):
        """جوهر الحماية: سكربت بلا nonce لا يعمل."""
        csp = self._csp(_client().get("/landing"))
        script_part = csp.split("style-src")[0]
        self.assertNotIn("'unsafe-inline'", script_part)
        self.assertIn("'nonce-", script_part)

    def test_every_inline_script_carries_the_matching_nonce(self):
        import re
        c = _client()
        for p in self.pages:
            r = c.get(p)
            nonce = re.search(r"'nonce-([\w\-]+)'", self._csp(r)).group(1)
            tags = re.findall(r"<script\b[^>]*>", r.get_data(as_text=True))
            missing = [t for t in tags if f'nonce="{nonce}"' not in t]
            self.assertEqual(missing, [], f"{p}: وسم سكربت بلا nonce سيُحجب")

    def test_the_nonce_is_not_reused_across_requests(self):
        import re
        c = _client()
        seen = {re.search(r"'nonce-([\w\-]+)'", self._csp(c.get("/landing"))).group(1)
                for _ in range(3)}
        self.assertEqual(len(seen), 3, "nonce ثابت = nonce بلا قيمة")

    def test_a_rejected_request_still_gets_a_valid_nonce(self):
        """رفض CSRF يوقف الطلب قبل `_csp_nonce`؛ السياسة يجب ألا تحمل 'nonce-' فارغة."""
        r = web.app.test_client().post("/login", data={"username": "x", "password": "y"})
        self.assertEqual(r.status_code, 400)
        self.assertNotIn("'nonce-'", self._csp(r))
        self.assertRegex(self._csp(r), r"'nonce-[\w\-]{8,}'")

    def test_hsts_only_on_secure_requests(self):
        """إرسالها على http يثبّت الترقية قبل جهوزية الشهادة."""
        c = _client()
        self.assertNotIn("Strict-Transport-Security", c.get("/landing").headers)
        r = c.get("/landing", headers={"X-Forwarded-Proto": "https"}, base_url="https://localhost")
        self.assertIn("Strict-Transport-Security", r.headers)


if __name__ == "__main__":
    unittest.main(verbosity=2)
