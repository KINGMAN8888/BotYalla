"""نظام الحساب: السياسات · التسجيل الكامل · تأكيد البريد الإجباري · الدخول بالبريد ·
جوجل/فيسبوك (المزوّد مُحاكى) · تأكيد الهاتف عبر بوت المنصة · كلمة المرور في الاسترجاع و«حسابي».

    python tests/test_accounts.py
"""
import asyncio, os, re, secrets, sys, tempfile, time, unittest
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_TMPDIR = tempfile.mkdtemp(prefix="botyalla-accounts-")
os.environ["BOTYALLA_DB"] = os.path.join(_TMPDIR, "test.db")   # قبل استيراد database
os.environ["BOTYALLA_UPLOADS"] = _TMPDIR
os.environ["BOTYALLA_LOGS"] = _TMPDIR
ADMIN_PW = "Adm#" + secrets.token_hex(6)
os.environ["ADMIN_USER"] = "admin"
os.environ["ADMIN_PASS"] = ADMIN_PW
os.environ["PUBLIC_URL"] = "https://botyalla.test"
SMTP_ENV = {"SMTP_HOST": "smtp.test", "SMTP_PORT": "587", "SMTP_USER": "bot", "SMTP_PASS": "pw",
            "SMTP_FROM": "BotYalla <no-reply@botyalla.test>", "SMTP_TLS": "starttls"}
os.environ.update(SMTP_ENV)
os.environ.update({"GOOGLE_CLIENT_ID": "gid", "GOOGLE_CLIENT_SECRET": "gsec",
                   "FACEBOOK_APP_ID": "fid", "FACEBOOK_APP_SECRET": "fsec"})

import accounts as ACC                     # noqa: E402
import auth                                # noqa: E402
import database as db                      # noqa: E402
import app as web                          # noqa: E402
import mailer                              # noqa: E402
import platform_bot                        # noqa: E402
from _signup import signup, STRONG_PW      # noqa: E402

SENT = []


class FakeSMTP:
    def __init__(self, *a, **k): pass
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def starttls(self, context=None): pass
    def login(self, u, p): pass
    def send_message(self, msg): SENT.append(msg)


def _boot():
    db.init_db()
    web.seed_platform_defaults()
    web.contact_defaults()
    web.seed_default_admin()
    web.app.config["TESTING"] = True
    web.manager.notify_text = lambda *a, **k: None
    mailer.smtplib.SMTP = FakeSMTP
    mailer.SYNC = True


def _client():
    c = web.app.test_client()
    with c.session_transaction() as s:
        s["_csrf"] = "tk"
    return c


def _fresh():
    SENT.clear()
    mailer._sent.clear()
    web._login_attempts.clear()
    os.environ.update(SMTP_ENV)
    os.environ["PUBLIC_URL"] = "https://botyalla.test"


def _last_to(addr):
    return [m for m in SENT if m["To"] == addr][-1]


def _code(msg):
    return re.match(r"(\d{6})", msg["Subject"]).group(1)


def _text(msg):
    return msg.get_body(preferencelist=("plain",)).get_content()


class PolicyTests(unittest.TestCase):
    """القواعد نفسها في accounts.py — الواجهة مرآة لها فقط."""

    def test_username_rules(self):
        for name, want in (("12345", "u_digits"), ("1abc", "u_start"), ("ab", "u_len"), ("nour store", "u_chars"),
                           ("nour_", "u_end"), ("nour__x", "u_repeat"), ("admin_shop", "u_reserved"),
                           ("BotYalla_eg", "u_reserved"), ("support.team", "u_reserved"),
                           ("nour_store", None), ("متجر.النور", None), ("Ahmed99", None)):
            self.assertEqual(ACC.username_problem(name), want, name)

    def test_password_rules(self):
        self.assertEqual(ACC.password_problems("Yalla#Test2026"), [])
        for pw, key in (("yalla#test2026", "p_upper"), ("YALLA#TEST2026", "p_lower"), ("Yalla#Test", "p_digit"),
                        ("YallaTest2026", "p_symbol"), ("Ya#1", "p_len"), ("Password@123", "p_common"),
                        ("Qwerty!2026", "p_common")):
            self.assertIn(key, ACC.password_problems(pw), pw)
        self.assertIn("p_user", ACC.password_problems("Nour#store1", "nour_store1"[:4]))
        self.assertIn("p_user", ACC.password_problems("Sara.m#2026x", "", "sara.m@x.co"))

    def test_phone_normalisation(self):
        for cc, raw, want in (("+20", "01012345678", "+201012345678"), ("+20", "٠١٥١٢٣٤٥٦٧٨", "+201512345678"),
                              ("+20", "010 1234 5678", "+201012345678"), ("+20", "+966501234567", "+966501234567"),
                              ("+966", "0501234567", "+966501234567"), ("+20", "0223456789", None),
                              ("+20", "0123", None), ("+999", "123456789", None), ("+20", "abc", None)):
            self.assertEqual(ACC.normalize_phone(cc, raw), want, (cc, raw))
        self.assertTrue(ACC.same_phone("201012345678", "+201012345678"))

    def test_age(self):
        self.assertEqual(ACC.parse_age("17"), (None, "age_min"))
        self.assertEqual(ACC.parse_age("٣٠"), (30, None))
        self.assertEqual(ACC.parse_age("abc"), (None, "age_bad"))
        self.assertEqual(ACC.parse_age("150"), (None, "age_bad"))


class SignupTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        _boot()

    def setUp(self):
        _fresh()

    def test_a_full_signup_is_gated_until_the_email_code_is_entered(self):
        c = _client()
        r = c.post("/register", data=signup("nour_store", entity_type="company", age="34"))
        self.assertIn("/verify-email", r.headers["Location"])
        u = db.get_user_by_name("nour_store")
        self.assertEqual((u["phone"][:3], u["age"], u["entity_type"], u["verify_required"]), ("+20", 34, "company", 1))
        self.assertIsNone(u["email_verified_at"])
        self.assertTrue(db.get_setting(u["id"], "terms_at"), "وقت الموافقة على الشروط محفوظ")
        # البوابة: اللوحة والـ API مغلقان، والصفحات العامة وصفحة التأكيد مفتوحة
        self.assertIn("/verify-email", c.get("/dashboard").headers["Location"])
        self.assertEqual(c.post("/bot/create", data={"csrf_token": "tk"}).status_code, 403)
        self.assertEqual(c.get("/pricing").status_code, 200)
        self.assertEqual(c.get("/verify-email").status_code, 200)
        msg = _last_to(u["email"])
        code = _code(msg)
        self.assertNotIn(code, db.email_verification(u["id"])["code_hash"], "الكود لا يُخزَّن")
        welcome_before = [m for m in SENT if "Welcome" in m["Subject"] or "أهلاً" in m["Subject"]]
        self.assertEqual(welcome_before, [], "الترحيب بعد التأكيد لا قبله")
        bad = "000000" if code != "000000" else "111111"
        c.post("/verify-email", data={"code": bad, "csrf_token": "tk"})
        self.assertIsNone(db.get_user(u["id"])["email_verified_at"])
        r = c.post("/verify-email", data={"code": code, "csrf_token": "tk"})
        self.assertIn("/dashboard", r.headers["Location"])
        self.assertIsNotNone(db.get_user(u["id"])["email_verified_at"])
        self.assertEqual(c.get("/dashboard").status_code, 200)
        self.assertTrue(any("أهلاً" in m["Subject"] for m in SENT), "الترحيب بعد التأكيد")

    def test_five_wrong_codes_lock_the_code_until_a_new_one(self):
        c = _client()
        c.post("/register", data=signup("lock_me"))
        u = db.get_user_by_name("lock_me")
        code = _code(_last_to(u["email"]))
        wrong = "123456" if code != "123456" else "654321"
        for _ in range(5):
            c.post("/verify-email", data={"code": wrong, "csrf_token": "tk"})
        c.post("/verify-email", data={"code": code, "csrf_token": "tk"})
        self.assertIsNone(db.get_user(u["id"])["email_verified_at"], "بعد 5 أخطاء الكود الصحيح نفسه لا يكفي")
        with db.get_conn() as cx:
            cx.execute("UPDATE email_verifications SET sent_at=0 WHERE user_id=?", (u["id"],))
        c.post("/verify-email/resend", data={"csrf_token": "tk"})
        c.post("/verify-email", data={"code": _code(_last_to(u["email"])), "csrf_token": "tk"})
        self.assertIsNotNone(db.get_user(u["id"])["email_verified_at"])

    def test_the_email_link_verifies_even_on_another_device(self):
        _client().post("/register", data=signup("link_user"))
        u = db.get_user_by_name("link_user")
        tok = re.search(r"/verify-email/t/([\w\-]+)", _text(_last_to(u["email"]))).group(1)
        r = web.app.test_client().get(f"/verify-email/t/{tok}")        # بلا جلسة
        self.assertIn("/login", r.headers["Location"])
        self.assertIsNotNone(db.get_user(u["id"])["email_verified_at"])
        self.assertIn("/login", web.app.test_client().get(f"/verify-email/t/{tok}").headers["Location"],
                      "الرابط لمرة واحدة")

    def test_a_typo_email_can_be_corrected_from_the_gate(self):
        c = _client()
        c.post("/register", data=signup("typo_user", email="typo@exmaple.com"))
        c.post("/verify-email/change", data={"email": "typo@example.com", "password": STRONG_PW, "csrf_token": "tk"})
        u = db.get_user_by_name("typo_user")
        self.assertEqual(u["email"], "typo@example.com")
        c.post("/verify-email", data={"code": _code(_last_to("typo@example.com")), "csrf_token": "tk"})
        self.assertIsNotNone(db.get_user(u["id"])["email_verified_at"])

    def test_bad_forms_are_refused_field_by_field(self):
        _client().post("/register", data=signup("dup_name"))
        for name, over in (("Dup_Name", {}),                                     # نفس الاسم بحالة أحرف أخرى
                           ("weak_pw", {"password": "weakpass1", "password2": "weakpass1"}),
                           ("mismatch", {"password2": "Other#Pass2026"}),
                           ("young", {"age": "16"}),
                           ("no_terms", {"terms": ""}),
                           ("no_entity", {"entity_type": "alien"}),
                           ("bad_phone", {"phone": "0223456789"}),
                           ("dup_phone", {"phone": signup("dup_name")["phone"]}),
                           ("98765", {})):
            web._login_attempts.clear()
            r = _client().post("/register", data=signup(name, **over))
            self.assertEqual(r.status_code, 200, name)
            self.assertIsNone(db.get_user_by_name(name), name)
        body = _client().post("/register", data=signup("young2", age="16")).get_data(as_text=True)
        self.assertIn('"values"', body, "القيم المكتوبة ترجع للنموذج")
        self.assertNotIn(STRONG_PW, body, "كلمة المرور لا ترجع للصفحة أبداً")

    def test_the_live_username_check(self):
        _client().post("/register", data=signup("taken_one"))
        c = _client()
        self.assertTrue(c.get("/api/check-username?u=free_name").get_json()["ok"])
        d = c.get("/api/check-username?u=Taken_One").get_json()
        self.assertFalse(d["ok"])
        self.assertTrue(d["suggestions"] and all(not db.username_taken(s) for s in d["suggestions"]))
        self.assertFalse(c.get("/api/check-username?u=12345").get_json()["ok"])
        self.assertFalse(c.get("/api/check-username?u=admin").get_json()["ok"])

    def test_without_smtp_new_accounts_are_not_locked_out(self):
        os.environ["SMTP_HOST"] = ""
        c = _client()
        r = c.post("/register", data=signup("no_smtp"))
        self.assertIn("/dashboard", r.headers["Location"])
        self.assertEqual(c.get("/dashboard").status_code, 200)

    def test_legacy_accounts_are_never_gated_and_can_sign_in_with_email(self):
        uid = db.create_user("legacy_u", auth.hash_password("old-weak"), email="legacy@x.co")
        c = _client()
        r = c.post("/login", data={"username": "LEGACY@x.co", "password": "old-weak", "csrf_token": "tk"})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(c.get("/dashboard").status_code, 200, "الحسابات القديمة تعمل بكلماتها كما هي")
        c2 = _client()
        c2.post("/login", data={"username": "Legacy_U", "password": "old-weak", "csrf_token": "tk"})
        self.assertEqual(c2.get("/dashboard").status_code, 200, "اسم المستخدم بلا حساسية لحالة الأحرف")
        self.assertFalse(db.email_gate(db.get_user(uid)))


class OAuthTests(unittest.TestCase):
    """جوجل/فيسبوك: المزوّد مُحاكى في _oauth_profile — نختبر منطقنا لا شبكتهم."""

    @classmethod
    def setUpClass(cls):
        _boot()
        cls._orig = web._oauth_profile

    @classmethod
    def tearDownClass(cls):
        web._oauth_profile = cls._orig

    def setUp(self):
        _fresh()

    def _go(self, c, provider, profile, state=None, link=False):
        r = c.get(f"/auth/{provider}" + ("?link=1" if link else ""))
        self.assertEqual(r.status_code, 302)
        with c.session_transaction() as s:
            st = s["oauth"]["state"]
        web._oauth_profile = lambda p, code, v: dict(profile)
        return c.get(f"/auth/{provider}/callback?state={state or st}&code=abc")

    def test_the_start_uses_state_pkce_and_public_url(self):
        r = _client().get("/auth/google")
        loc = r.headers["Location"]
        self.assertTrue(loc.startswith("https://accounts.google.com/"))
        for part in ("client_id=gid", "code_challenge=", "code_challenge_method=S256", "state=",
                     "redirect_uri=https%3A%2F%2Fbotyalla.test%2Fauth%2Fgoogle%2Fcallback"):
            self.assertIn(part, loc)

    def test_a_forged_state_is_refused(self):
        c = _client()
        r = self._go(c, "google", {"sub": "g-x", "email": "x@g.co", "email_verified": True, "name": "X"},
                     state="forged")
        self.assertIn("/login", r.headers["Location"])
        self.assertIsNone(db.get_identity("google", "g-x"))

    def test_a_new_google_user_completes_the_profile_and_is_verified(self):
        c = _client()
        r = self._go(c, "google", {"sub": "g-1", "email": "mona@gmail.com", "email_verified": True, "name": "Mona Ali"})
        self.assertIn("/register/complete", r.headers["Location"])
        page = c.get("/register/complete").get_data(as_text=True)
        self.assertIn("mona@gmail.com", page)
        form = signup("mona_ali")
        for k in ("email", "password", "password2"):
            form.pop(k)
        r = c.post("/register/complete", data=form)
        self.assertIn("/dashboard", r.headers["Location"])
        u = db.get_user_by_name("mona_ali")
        self.assertEqual(u["email"], "mona@gmail.com")
        self.assertIsNotNone(u["email_verified_at"], "جوجل أكّد البريد — لا كود")
        self.assertEqual(db.get_identity("google", "g-1")["user_id"], u["id"])
        self.assertEqual(db.get_setting(u["id"], "pw_set"), "0")
        self.assertEqual(c.get("/dashboard").status_code, 200)
        # الدخول التالي بجوجل مباشرة
        r = self._go(_client(), "google", {"sub": "g-1", "email": "mona@gmail.com", "email_verified": True, "name": "M"})
        self.assertIn("/dashboard", r.headers["Location"])

    def test_facebook_without_email_must_give_and_verify_one(self):
        c = _client()
        self._go(c, "facebook", {"sub": "f-1", "email": "", "email_verified": False, "name": "Hana"})
        form = signup("hana_fb", email="hana@x.co")
        form.pop("password"); form.pop("password2")
        r = c.post("/register/complete", data=form)
        self.assertIn("/verify-email", r.headers["Location"])
        self.assertTrue(db.email_gate(db.get_user_by_name("hana_fb")))

    def test_an_existing_account_is_linked_only_if_its_email_is_verified(self):
        v = db.create_user("verified_acc", auth.hash_password(STRONG_PW), email="v@x.co")
        db.mark_email_verified(v)
        r = self._go(_client(), "google", {"sub": "g-v", "email": "v@x.co", "email_verified": True, "name": "V"})
        self.assertIn("/dashboard", r.headers["Location"])
        self.assertEqual(db.get_identity("google", "g-v")["user_id"], v)
        # بريد غير مؤكَّد: من سجّل حساباً ببريد غيره لا يستولي على صاحبه الحقيقي حين يدخل بجوجل
        db.create_user("squatter", auth.hash_password(STRONG_PW), email="victim@x.co")
        r = self._go(_client(), "google", {"sub": "g-victim", "email": "victim@x.co", "email_verified": True, "name": "V"})
        self.assertIn("/login", r.headers["Location"])
        self.assertIsNone(db.get_identity("google", "g-victim"))

    def test_linking_from_the_account_page(self):
        uid = db.create_user("linker", auth.hash_password(STRONG_PW), email="linker@x.co")
        c = _client()
        c.post("/login", data={"username": "linker", "password": STRONG_PW, "csrf_token": "tk"})
        r = self._go(c, "facebook", {"sub": "f-link", "email": "other@fb.com", "email_verified": True, "name": "L"},
                     link=True)
        self.assertIn("/account", r.headers["Location"])
        self.assertEqual(db.list_identities(uid), ["facebook"])

    def test_buttons_hide_without_keys(self):
        os.environ["GOOGLE_CLIENT_ID"] = ""
        try:
            self.assertFalse(web._oauth_on("google"))
            self.assertIn("/login", _client().get("/auth/google").headers["Location"])
        finally:
            os.environ["GOOGLE_CLIENT_ID"] = "gid"


class PhoneVerifyTests(unittest.TestCase):
    """تأكيد الهاتف مجاناً: جهة اتصال يشاركها صاحبها مع بوت المنصة."""

    @classmethod
    def setUpClass(cls):
        _boot()

    def setUp(self):
        _fresh()

    def _bot(self):
        handlers = []
        platform_bot.register_admin_commands(SimpleNamespace(add_handler=handlers.append))
        start = next(h for h in handlers if getattr(h, "commands", None) and "start" in h.commands).callback
        contact = next(h for h in handlers if h.__class__.__name__ == "MessageHandler").callback
        return start, contact

    def _update(self, tg_id, contact=None):
        out = []

        async def reply_text(text, reply_markup=None):
            out.append(text)
        msg = SimpleNamespace(reply_text=reply_text, contact=contact)
        return SimpleNamespace(message=msg, effective_user=SimpleNamespace(id=tg_id)), out

    def test_sharing_the_matching_number_verifies_and_links_telegram(self):
        uid, _ = db.create_account("phone_ok", auth.hash_password(STRONG_PW), "p1@x.co", "+201011112222", 30,
                                   "individual")
        db.set_phone_code(uid, "abc123")
        start, contact = self._bot()
        ctx = SimpleNamespace(args=["phone-abc123"], user_data={})
        upd, out = self._update(777)
        asyncio.run(start(upd, ctx))
        self.assertIn("phone_verify", ctx.user_data)
        # جهة اتصال شخص آخر لا تُقبل
        upd, out = self._update(777, SimpleNamespace(user_id=999, phone_number="201011112222"))
        asyncio.run(contact(upd, ctx))
        self.assertIsNone(db.get_user(uid)["phone_verified_at"])
        upd, out = self._update(777, SimpleNamespace(user_id=777, phone_number="201011112222"))
        asyncio.run(contact(upd, ctx))
        self.assertIsNotNone(db.get_user(uid)["phone_verified_at"])
        self.assertEqual(db.get_setting(uid, "tg_chat_id"), "777", "تليجرام اتربط للتنبيهات")

    def test_a_different_number_or_an_old_link_is_refused(self):
        uid, _ = db.create_account("phone_no", auth.hash_password(STRONG_PW), "p2@x.co", "+201033334444", 30,
                                   "individual")
        db.set_phone_code(uid, "zzz999")
        self.assertEqual(db.verify_phone_tg(uid, "zzz999", "201099990000", 5), "mismatch")
        db.set_setting(uid, "phone_code_at", str(int(time.time()) - 3600))
        self.assertEqual(db.verify_phone_tg(uid, "zzz999", "201033334444", 5), "expired")
        self.assertIsNone(db.get_user(uid)["phone_verified_at"])

    def test_changing_the_number_drops_its_verification(self):
        uid, _ = db.create_account("phone_chg", auth.hash_password(STRONG_PW), "p3@x.co", "+201055556666", 30,
                                   "individual")
        with db.get_conn() as cx:
            cx.execute("UPDATE users SET phone_verified_at=1, email_verified_at=1 WHERE id=?", (uid,))
        c = _client()
        c.post("/login", data={"username": "phone_chg", "password": STRONG_PW, "csrf_token": "tk"})
        c.post("/account/profile", data={"phone_cc": "+20", "phone": "01077778888", "age": "31",
                                         "entity_type": "company", "csrf_token": "tk"})
        u = db.get_user(uid)
        self.assertEqual((u["phone"], u["age"], u["entity_type"]), ("+201077778888", 31, "company"))
        self.assertIsNone(u["phone_verified_at"])


class PasswordEverywhereTests(unittest.TestCase):
    """نفس سياسة كلمة المرور في الاسترجاع و«حسابي» وإضافة الأدمن."""

    @classmethod
    def setUpClass(cls):
        _boot()

    def setUp(self):
        _fresh()

    def test_reset_refuses_a_weak_password(self):
        uid = db.create_user("resetter", auth.hash_password("old-weak"), email="r@x.co")
        db.create_password_reset(uid, web._token_hash("tok123"), 3600)
        _client().post("/reset/tok123", data={"password": "weakpass", "csrf_token": "tk"})
        self.assertTrue(auth.verify_password("old-weak", db.get_user(uid)["pw_hash"]))
        _client().post("/reset/tok123", data={"password": "Strong#Pass9", "password2": "Strong#Pass9",
                                              "csrf_token": "tk"})
        self.assertTrue(auth.verify_password("Strong#Pass9", db.get_user(uid)["pw_hash"]))

    def test_account_and_admin_refuse_weak_passwords(self):
        db.create_user("acct_pw", auth.hash_password(STRONG_PW), email="a@x.co")
        c = _client()
        c.post("/login", data={"username": "acct_pw", "password": STRONG_PW, "csrf_token": "tk"})
        c.post("/account", data={"username": "acct_pw", "new_password": "short", "current_password": STRONG_PW,
                                 "csrf_token": "tk"})
        self.assertTrue(auth.verify_password(STRONG_PW, db.get_user_by_name("acct_pw")["pw_hash"]))
        adm = _client()
        adm.post("/login", data={"username": "admin", "password": ADMIN_PW, "csrf_token": "tk"})
        adm.post("/admin/users/add", data={"username": "staff_new", "password": "weak", "role": "support",
                                           "csrf_token": "tk"})
        self.assertIsNone(db.get_user_by_name("staff_new"))
        adm.post("/admin/users/add", data={"username": "staff_new", "password": "Staff#2026x", "role": "support",
                                           "csrf_token": "tk"})
        self.assertIsNotNone(db.get_user_by_name("staff_new"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
