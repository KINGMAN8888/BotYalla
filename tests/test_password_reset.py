"""اختبارات الإيميل واسترجاع كلمة المرور والإيصالات (LAUNCH_READINESS L-05 · L-06 · L-09).

    python tests/test_password_reset.py
"""
import hashlib, os, re, secrets, sqlite3, sys, tempfile, time, unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_TMPDIR = tempfile.mkdtemp(prefix="botyalla-reset-")
os.environ["BOTYALLA_DB"] = os.path.join(_TMPDIR, "test.db")   # قبل استيراد database/app
os.environ["BOTYALLA_UPLOADS"] = os.path.join(_TMPDIR, "uploads")
ADMIN_PW = os.environ.setdefault("ADMIN_PASS", f"tst_adm_{secrets.token_hex(8)}")
TEST_PW = f"tst_pw_{secrets.token_hex(8)}"
os.environ["ADMIN_USER"] = "admin"
os.environ["ADMIN_PASS"] = ADMIN_PW
os.environ["PUBLIC_URL"] = "https://botyalla.test"

import auth                                # noqa: E402
import database as db                      # noqa: E402
import mailer                              # noqa: E402
import app as web                          # noqa: E402

MAIL = []
mailer.SYNC = True
mailer.send_mail = lambda to, subject, html, text=None: MAIL.append((to, subject, text)) or True


def _boot():
    db.init_db()
    web.seed_platform_defaults()
    web.contact_defaults()
    web.seed_default_admin()
    web.app.config["TESTING"] = True
    web.manager.notify_text = lambda *a, **k: None


def _client():
    c = web.app.test_client()
    with c.session_transaction() as s:
        s["_csrf"] = "tk"
    return c


def _login(c, user, pw):
    return c.post("/login", data={"username": user, "password": pw, "csrf_token": "tk"})


def _signed_in(c):
    # «/» صارت الصفحة العامة (200 للجميع) — اللوحة هي ما يكشف الجلسة
    return c.get("/dashboard").status_code == 200


def _token_from_mail():
    return re.search(r"/reset/([\w\-]+)", MAIL[-1][2]).group(1)


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _boot()

    def setUp(self):
        MAIL.clear()
        web._login_attempts.clear()
        os.environ["PUBLIC_URL"] = "https://botyalla.test"


class EmailFieldTests(Base):
    """L-05 — إيميل اختياري، فريد، ولا يكسر الحسابات القديمة."""

    def test_an_old_database_gains_the_column_and_its_accounts_keep_working(self):
        path = os.path.join(_TMPDIR, "old.db")
        con = sqlite3.connect(path)
        con.execute("CREATE TABLE users(id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE NOT NULL,"
                    " pw_hash TEXT NOT NULL, role TEXT NOT NULL DEFAULT 'user',"
                    " is_blocked INTEGER NOT NULL DEFAULT 0, created_at INTEGER NOT NULL)")
        con.execute("INSERT INTO users(username,pw_hash,created_at) VALUES('legacy','h',1)")
        con.commit(); con.close()
        orig = db.DB_PATH
        db.DB_PATH = path
        try:
            db.init_db()
            u = db.get_user_by_name("legacy")
            self.assertIn("email", u)
            self.assertIsNone(u["email"])
        finally:
            db.DB_PATH = orig

    def test_registration_accepts_an_optional_email_normalised(self):
        _client().post("/register", data={"username": "withmail", "password": TEST_PW,
                                          "email": "  Owner@Shop.COM ", "csrf_token": "tk"})
        self.assertEqual(db.get_user_by_name("withmail")["email"], "owner@shop.com")
        _client().post("/register", data={"username": "nomail", "password": TEST_PW,
                                          "csrf_token": "tk"})
        self.assertIsNone(db.get_user_by_name("nomail")["email"])

    def test_the_same_email_cannot_belong_to_two_accounts(self):
        _client().post("/register", data={"username": "first1", "password": TEST_PW,
                                          "email": "dup@x.co", "csrf_token": "tk"})
        _client().post("/register", data={"username": "second1", "password": TEST_PW,
                                          "email": "DUP@x.co", "csrf_token": "tk"})
        self.assertIsNone(db.get_user_by_name("second1"))
        other = db.create_user("third1", "h")
        self.assertEqual(db.set_user_email(other, "dup@x.co"), (False, "email_taken"))

    def test_a_malformed_email_is_refused(self):
        _client().post("/register", data={"username": "badmail", "password": TEST_PW,
                                          "email": "not an email", "csrf_token": "tk"})
        self.assertIsNone(db.get_user_by_name("badmail"))

    def test_the_account_page_sets_the_email_and_an_old_form_does_not_erase_it(self):
        db.create_user("acct", auth.hash_password(TEST_PW))
        c = _client(); _login(c, "acct", TEST_PW)
        c.post("/account", data={"username": "acct", "email": "acct@x.co",
                                 "current_password": TEST_PW, "csrf_token": "tk"})
        self.assertEqual(db.get_user_by_name("acct")["email"], "acct@x.co")
        # بناء واجهة أقدم بلا حقل email
        c.post("/account", data={"username": "acct", "current_password": TEST_PW,
                                 "csrf_token": "tk"})
        self.assertEqual(db.get_user_by_name("acct")["email"], "acct@x.co")


class PasswordResetTests(Base):
    """L-06 — رابط لمرة واحدة، ساعة، بلا تعداد، ويُنهي الجلسات القديمة."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.uid = db.create_user("forgetful", auth.hash_password("old-password"), email="me@shop.co")

    def _request(self, email="me@shop.co", **kw):
        return _client().post("/forgot", data={"email": email, "csrf_token": "tk"}, **kw)

    def test_the_pages_render_in_both_languages(self):
        self._request()
        tok = _token_from_mail()
        for lang in ("ar", "en"):
            c = _client()
            c.get(f"/lang/{lang}")
            for path in ("/forgot", f"/reset/{tok}", "/login", "/register"):
                r = c.get(path)
                self.assertEqual(r.status_code, 200, f"{lang} {path}")
            self.assertEqual(c.get(f"/reset/{tok}").headers.get("Cache-Control"), "no-store")

    def test_the_route_never_reveals_whether_an_account_exists(self):
        known = self._request("me@shop.co", follow_redirects=True)
        unknown = self._request("nobody@shop.co", follow_redirects=True)
        self.assertEqual(known.status_code, unknown.status_code)
        strip = lambda r: re.sub(r"nonce[-=\"'][\w\-\"']+|\"csrf\": \"[^\"]*\"", "", r.get_data(as_text=True))
        self.assertEqual(strip(known), strip(unknown), "الردّ يجب أن يتطابق حرفياً")
        self.assertEqual([m[0] for m in MAIL], ["me@shop.co"], "الإيميل يصل للحساب الموجود وحده")

    def test_a_link_resets_the_password_exactly_once(self):
        self._request()
        tok = _token_from_mail()
        self.assertEqual(_client().get(f"/reset/{tok}").status_code, 200)
        r = _client().post(f"/reset/{tok}", data={"password": "new-password", "csrf_token": "tk"})
        self.assertIn("/login", r.headers["Location"])
        self.assertTrue(auth.verify_password("new-password", db.get_user(self.uid)["pw_hash"]))
        # إعادة الاستخدام مرفوضة ولا تغيّر شيئاً
        r = _client().post(f"/reset/{tok}", data={"password": "attacker-pass", "csrf_token": "tk"})
        self.assertIn("/forgot", r.headers["Location"])
        self.assertTrue(auth.verify_password("new-password", db.get_user(self.uid)["pw_hash"]))

    def test_the_first_sign_in_after_a_reset_is_accepted(self):
        """الاسترجاع يمسح الجلسة؛ صفحة الدخول بعده يجب أن تحمل توكن CSRF صالحاً
        (اكتُشف في المتصفح: كان أول دخول بعد الاسترجاع يُرفض بـ 400)."""
        self._request()
        c = _client()
        r = c.post(f"/reset/{_token_from_mail()}", data={"password": "after-reset-1", "csrf_token": "tk"},
                   follow_redirects=True)
        tok = re.search(r'"csrf": "([^"]*)"', r.get_data(as_text=True)).group(1)
        self.assertTrue(tok)
        r = c.post("/login", data={"username": "forgetful", "password": "after-reset-1", "csrf_token": tok})
        self.assertEqual(r.status_code, 302)
        self.assertTrue(_signed_in(c))

    def test_an_expired_link_is_refused(self):
        self._request()
        tok = _token_from_mail()
        with db.get_conn() as c:
            c.execute("UPDATE password_resets SET expires_at=? WHERE user_id=?", (int(time.time()) - 1, self.uid))
        self.assertIn("/forgot", _client().get(f"/reset/{tok}").headers["Location"])

    def test_only_the_hash_of_the_token_is_stored(self):
        self._request()
        tok = _token_from_mail()
        with db.get_conn() as c:
            stored = [r[0] for r in c.execute("SELECT token_hash FROM password_resets")]
        self.assertNotIn(tok, stored)
        self.assertIn(hashlib.sha256(tok.encode()).hexdigest(), stored)

    def test_a_new_request_invalidates_the_previous_link(self):
        self._request(); first = _token_from_mail()
        self._request(); second = _token_from_mail()
        self.assertIn("/forgot", _client().get(f"/reset/{first}").headers["Location"])
        self.assertEqual(_client().get(f"/reset/{second}").status_code, 200)

    def test_a_reset_signs_out_every_existing_session(self):
        db.update_user_credentials(self.uid, pw_hash=auth.hash_password("pw-before"))
        victim_laptop = _client(); _login(victim_laptop, "forgetful", "pw-before")
        self.assertTrue(_signed_in(victim_laptop))
        self._request()
        _client().post(f"/reset/{_token_from_mail()}", data={"password": "pw-after", "csrf_token": "tk"})
        self.assertFalse(_signed_in(victim_laptop), "الجلسة القديمة كان يجب أن تنتهي")

    def test_changing_the_password_keeps_this_session_and_ends_the_others(self):
        db.create_user("twodevices", auth.hash_password("pw-one"))
        phone, laptop = _client(), _client()
        _login(phone, "twodevices", "pw-one"); _login(laptop, "twodevices", "pw-one")
        phone.post("/account", data={"username": "twodevices", "new_password": "pw-two",
                                     "current_password": "pw-one", "csrf_token": "tk"})
        self.assertTrue(_signed_in(phone))
        self.assertFalse(_signed_in(laptop))

    def test_requests_are_rate_limited_per_email(self):
        for _ in range(5):
            self._request()
        self.assertEqual(len(MAIL), 3)

    def test_without_public_url_no_link_is_sent(self):
        """افشل مغلقاً: لا رابط يُبنى من ترويسة Host."""
        os.environ.pop("PUBLIC_URL")
        self._request()
        self.assertEqual(MAIL, [])

    def test_a_forged_host_header_cannot_poison_the_link(self):
        # X-Forwarded-Host يكفي: ProxyFix(x_host=1) يجعله request.host في الخادم.
        # (ترويسة Host نفسها تمنع عميل الاختبار من إرسال كوكي الجلسة فيسقط CSRF.)
        self._request(headers={"X-Forwarded-Host": "evil.example"})
        self.assertIn("https://botyalla.test/reset/", MAIL[-1][2])
        self.assertNotIn("evil.example", MAIL[-1][2])


class ReceiptTests(Base):
    """L-09 — إيصال بالإيميل بعد البتّ، وفشله لا يمسّ التسوية."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.uid = db.create_user("buyer", auth.hash_password(TEST_PW), email="buyer@shop.co")

    def _admin(self):
        c = _client(); _login(c, "admin", ADMIN_PW)
        return c

    def test_an_approval_emails_a_receipt_with_the_expiry(self):
        pid = db.create_payment(self.uid, "pro", "instapay", 199, "R", "s.png", "HR1", "{}")
        self._admin().post(f"/admin/payments/{pid}/approve", data={"csrf_token": "tk"})
        to, subject, text = MAIL[-1]
        self.assertEqual(to, "buyer@shop.co")
        self.assertIn(f"#{pid}", subject)
        exp = db.get_subscription(self.uid)["expires_at"]
        self.assertIn(time.strftime("%Y-%m-%d", time.localtime(exp)), text)

    def test_a_rejection_emails_the_next_step(self):
        pid = db.create_payment(self.uid, "pro", "instapay", 199, "R", "s.png", "HR2", "{}")
        self._admin().post(f"/admin/payments/{pid}/reject", data={"csrf_token": "tk"})
        self.assertIn(f"#{pid}", MAIL[-1][1])

    def test_a_mail_failure_does_not_undo_the_settlement(self):
        pid = db.create_payment(self.uid, "business", "instapay", 499, "R", "s.png", "HR3", "{}")
        orig = mailer.send_mail
        mailer.send_mail = lambda *a, **k: (_ for _ in ()).throw(OSError("smtp down"))
        try:
            r = self._admin().post(f"/admin/payments/{pid}/approve", data={"csrf_token": "tk"})
        finally:
            mailer.send_mail = orig
        self.assertEqual(r.status_code, 302)
        self.assertEqual(db.get_payment(pid)["status"], "approved")
        self.assertEqual(db.get_subscription(self.uid)["plan"], "business")


if __name__ == "__main__":
    unittest.main(verbosity=2)
