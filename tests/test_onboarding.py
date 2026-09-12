"""L-10 — إرشاد المستخدم الجديد.

ما يُختبَر هنا ليس شكل البطاقة بل **المنطق الذي يقرّر ما يراه المستخدم**:
أي مرحلة (لا بوت · بوت غير جاهز · انتهى)، وأي خطوة صارت مكتملة، ومتى يختفي
الإرشاد من نفسه. وكذلك أن رسالة الترحيب تُرسل عند التسجيل وأن غيابها — أو
غياب `PUBLIC_URL` — لا يمنع إنشاء الحساب.

    python tests/test_onboarding.py
"""
import json, os, secrets, sys, tempfile, time, unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_TMPDIR = tempfile.mkdtemp(prefix="botyalla-onboard-")
os.environ["BOTYALLA_DB"] = os.path.join(_TMPDIR, "test.db")   # قبل استيراد database
os.environ["BOTYALLA_UPLOADS"] = _TMPDIR
ADMIN_PW = os.environ.setdefault("ADMIN_PASS", f"tst_adm_{secrets.token_hex(8)}")
PW = f"tst_onb_{secrets.token_hex(8)}"
os.environ["ADMIN_USER"] = "admin"
os.environ["ADMIN_PASS"] = ADMIN_PW

import auth                                # noqa: E402
import mailer                              # noqa: E402
import database as db                      # noqa: E402
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


class StageTests(unittest.TestCase):
    """المراحل الثلاث ومتى تنتقل بينها."""

    @classmethod
    def setUpClass(cls):
        _boot()
        cls.u = db.create_user("ob_stage", auth.hash_password(PW))

    def _bot(self, cfg=None, running=False, subs=0):
        """بوت وهمي بالشكل الذي يصل به إلى `_onboarding` من مسار اللوحة."""
        return {"id": 1, "name": "متجري", "channel": "telegram",
                "config_json": json.dumps(cfg or {}, ensure_ascii=False),
                "running": running, "stats": {"subscribers": subs}}

    def test_a_flow_bot_greets_from_its_flow_not_from_welcome(self):
        """بوتات الفلو (4 من 7 أنواع) لا تقرأ `welcome` — فحصه وحده كان يُبقي
        البطاقة معلّقة للأبد. والنص الجاهز لا يُعدّ تخصيصاً."""
        import templates_bot as TB
        flow = json.loads(json.dumps(TB.PRESET_FLOWS["support"]))
        ready = dict(self._bot(cfg={"flow": flow}, running=True, subs=3), template="support")
        self.assertEqual(web._onboarding([ready])["stage"], "first_run", "الافتراضي ليس تخصيصاً")
        flow["start_message"] = "أهلاً بك في دعم متجر النور 👋"
        custom = dict(self._bot(cfg={"flow": flow}, running=True, subs=3), template="support")
        self.assertEqual(web._onboarding([custom])["stage"], "done")

    def test_the_card_says_where_a_flow_bot_sets_its_greeting(self):
        self.assertTrue(web._onboarding([dict(self._bot(), template="flow")])["flowBot"])
        self.assertFalse(web._onboarding([dict(self._bot(), template="store")])["flowBot"])

    def test_no_bots_means_the_botfather_guide(self):
        self.assertEqual(web._onboarding([])["stage"], "first_bot")

    def test_a_bare_new_bot_is_not_ready_yet(self):
        ob = web._onboarding([self._bot()])
        self.assertEqual(ob["stage"], "first_run")
        self.assertEqual([s["done"] for s in ob["steps"]], [False, False, False])
        self.assertEqual(ob["botName"], "متجري")

    def test_each_step_flips_on_its_own_signal(self):
        ob = web._onboarding([self._bot(cfg={"welcome": "أهلاً"})])
        self.assertEqual([s["done"] for s in ob["steps"]], [True, False, False])
        ob = web._onboarding([self._bot(running=True)])
        self.assertEqual([s["done"] for s in ob["steps"]], [False, True, False])
        ob = web._onboarding([self._bot(subs=3)])
        self.assertEqual([s["done"] for s in ob["steps"]], [False, False, True])

    def test_a_whitespace_greeting_does_not_count(self):
        """مسافة في الحقل ليست رسالة ترحيب — البوت سيرسل الافتراضي رغمها."""
        ob = web._onboarding([self._bot(cfg={"welcome": "   "})])
        self.assertFalse(ob["steps"][0]["done"])

    def test_the_guide_disappears_by_itself_when_all_three_are_done(self):
        ob = web._onboarding([self._bot(cfg={"welcome": "أهلاً"}, running=True, subs=1)])
        self.assertEqual(ob["stage"], "done")
        self.assertNotIn("steps", ob)

    def test_it_follows_the_first_bot_not_the_newest(self):
        """اللوحة ترتّب بالأحدث أولاً؛ الإرشاد يجب أن يتبع البوت **الأول**."""
        first = dict(self._bot(), id=1, name="الأول")
        newest = dict(self._bot(cfg={"welcome": "x"}, running=True, subs=9), id=7, name="الأحدث")
        ob = web._onboarding([newest, first])
        self.assertEqual(ob["botName"], "الأول")
        self.assertEqual(ob["stage"], "first_run")

    def test_broken_config_json_does_not_crash_the_dashboard(self):
        b = self._bot()
        b["config_json"] = "{ليس JSON"
        ob = web._onboarding([b])
        self.assertEqual(ob["stage"], "first_run")
        self.assertFalse(ob["steps"][0]["done"])


class DashboardPayloadTests(unittest.TestCase):
    """الحالة تصل فعلاً إلى الصفحة."""

    @classmethod
    def setUpClass(cls):
        _boot()
        db.create_user("ob_page", auth.hash_password(PW))

    def setUp(self):
        web._login_attempts.clear()
        self.c = _client()
        self.c.post("/login", data={"username": "ob_page", "password": PW, "csrf_token": "tk"})

    def test_a_fresh_account_gets_the_first_bot_stage(self):
        html = self.c.get("/dashboard").get_data(as_text=True)
        self.assertIn("first_bot", html)

    def test_the_onboarding_strings_ship_with_every_page(self):
        import i18n
        for k in ("ob_title", "ob_s1", "ob_greeting", "ob_run", "ob_try", "ob_progress"):
            self.assertIn(k, i18n.T, k)
            for lang in ("ar", "en"):
                self.assertTrue(i18n.t(k, lang) != k, f"{k}/{lang} بلا ترجمة")


class WelcomeEmailTests(unittest.TestCase):
    """الترحيب best-effort — ولا يعطّل التسجيل أبداً."""

    @classmethod
    def setUpClass(cls):
        _boot()
        cls.sent = []
        cls._orig = mailer.send_async
        mailer.send_async = lambda to, subject, html, text=None: (
            cls.sent.append((to, subject, html, text)) or True)

    @classmethod
    def tearDownClass(cls):
        mailer.send_async = cls._orig

    def setUp(self):
        web._login_attempts.clear()
        type(self).sent.clear()
        os.environ["PUBLIC_URL"] = "https://botyalla.test"

    def _register(self, name, email=""):
        return _client().post("/register", data={"username": name, "password": PW,
                                                 "email": email, "csrf_token": "tk"},
                              follow_redirects=False)

    def test_registering_with_an_email_sends_the_three_steps(self):
        self._register("ob_mail_1", "ob1@example.com")
        self.assertEqual(len(self.sent), 1)
        to, subject, html, text = self.sent[0]
        self.assertEqual(to, "ob1@example.com")
        self.assertIn("BotFather", text)
        self.assertIn("https://botyalla.test/", html)

    def test_registering_without_an_email_sends_nothing(self):
        self._register("ob_mail_2")
        self.assertEqual(self.sent, [])
        self.assertIsNotNone(db.get_user_by_name("ob_mail_2"))

    def test_without_public_url_the_email_still_goes_out_without_a_button(self):
        """الرسالة لا تحمل أي سرّ، فحجبها كلها خسارة بلا مكسب (بعكس رابط الاسترجاع)."""
        os.environ["PUBLIC_URL"] = ""
        self._register("ob_mail_3", "ob3@example.com")
        self.assertEqual(len(self.sent), 1)
        _, _, html, _ = self.sent[0]
        self.assertNotIn("<a href", html)

    def test_a_failing_mailer_never_blocks_the_account(self):
        def boom(*a, **k):
            raise RuntimeError("SMTP down")
        mailer.send_async = boom
        try:
            r = self._register("ob_mail_4", "ob4@example.com")
            self.assertIn(r.status_code, (302, 303))
            self.assertIsNotNone(db.get_user_by_name("ob_mail_4"))
        finally:
            mailer.send_async = lambda to, s, h, t=None: (type(self).sent.append((to, s, h, t)) or True)

    def test_the_email_is_written_in_the_account_language(self):
        c = _client()
        c.get("/lang/en")
        c.post("/register", data={"username": "ob_mail_5", "password": PW,
                                  "email": "ob5@example.com", "csrf_token": "tk"})
        self.assertTrue(any("Welcome" in s for _, s, _, _ in self.sent))


class PublicUrlTests(unittest.TestCase):
    """`_public_url` هي البوابة الوحيدة لأي رابط مطلق (AGENTS.md §3.14)."""

    @classmethod
    def setUpClass(cls):
        _boot()

    def test_it_refuses_to_build_a_link_without_a_scheme(self):
        for bad in ("", "botyalla.com", "ftp://x", "   "):
            os.environ["PUBLIC_URL"] = bad
            with web.app.test_request_context():
                self.assertIsNone(web._public_url("dashboard"), repr(bad))

    def test_it_builds_from_public_url_not_from_the_host_header(self):
        os.environ["PUBLIC_URL"] = "https://botyalla.test/"
        with web.app.test_request_context("/", headers={"Host": "evil.example"}):
            link = web._public_url("dashboard")
        self.assertTrue(link.startswith("https://botyalla.test/"))
        self.assertNotIn("evil", link)

    def test_the_reset_link_still_goes_through_the_same_gate(self):
        os.environ["PUBLIC_URL"] = ""
        with web.app.test_request_context():
            self.assertIsNone(web._reset_link("tok"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
