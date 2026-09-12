"""اختبار انحدار: حقن الحمولة داخل <script>window.BY = ...</script>.

`json.dumps` وحده لا يهرّب `</script>`، والقالب يحقن الناتج بـ `|safe`. فأي نص
يكتبه مستخدم يمكنه إغلاق الوسم مبكراً وتشغيل كود في جلسة من يفتح الصفحة —
وتوكن CSRF معروض في نفس الحمولة. هذه الاختبارات تقفل المسارات الثلاثة.

    python tests/test_xss.py
"""
import json, os, secrets, sys, tempfile, unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_TMPDIR = tempfile.mkdtemp(prefix="botyalla-xss-")
os.environ["BOTYALLA_DB"] = os.path.join(_TMPDIR, "test.db")   # قبل استيراد database/app
os.environ["BOTYALLA_UPLOADS"] = _TMPDIR
ADMIN_PW = os.environ.setdefault("ADMIN_PASS", f"tst_adm_{secrets.token_hex(8)}")
TEST_PW = f"tst_pw_{secrets.token_hex(8)}"
os.environ["ADMIN_USER"] = "admin"
os.environ["ADMIN_PASS"] = ADMIN_PW

import auth                                # noqa: E402
import database as db                      # noqa: E402
import app as web                          # noqa: E402

PAYLOAD = '</script><img src=x onerror=alert(document.domain)>'


def _boot():
    db.init_db()
    web.seed_platform_defaults()
    web.contact_defaults()
    web.seed_default_admin()
    web._migrate_ai_key()
    web.app.config["TESTING"] = True
    web.manager.is_running = lambda bid: False


def _client():
    c = web.app.test_client()
    with c.session_transaction() as s:
        s["_csrf"] = "tk"
    return c


def _login(c, user, pw):
    return c.post("/login", data={"username": user, "password": pw, "csrf_token": "tk"})


class ScriptInjectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _boot()
        # مهاجم يسجّل باسم يحمل الحمولة — لا قيد على أحرف الاسم، الطول فقط
        c = _client()
        c.post("/register", data={"username": PAYLOAD, "password": TEST_PW,
                                  "csrf_token": "tk"}, follow_redirects=True)
        # صاحب بوت، وعميل من تليجرام/واتساب يحقن عبر lead
        cls.owner = db.create_user("shopowner", auth.hash_password(TEST_PW))
        cls.bot = db.create_bot(cls.owner, "MyBot", "TOK:xss", "flow",
                                {"business_name": "MyBot", "flow": None, "menu_items": []})
        db.add_lead(cls.bot, 555, {"name": PAYLOAD, "note": "order"})

    def _by_payload(self, html):
        """يقتطع حمولة window.BY ويتأكد أنها JSON صالح."""
        i = html.index("window.BY = ") + len("window.BY = ")
        raw = html[i:html.index(";</script>", i)]
        json.loads(raw)                     # لو الهروب كسر الصياغة يسقط هنا
        return raw

    def test_a_malicious_username_cannot_close_the_script_tag_for_the_admin(self):
        """أخطر مسار: الأدمن يفتح «المستخدمون» فينفَّذ الكود في جلسته."""
        c = _client()
        _login(c, "admin", ADMIN_PW)
        html = c.get("/admin/users").get_data(as_text=True)
        self.assertNotIn(PAYLOAD, html)
        self.assertNotIn("</script><img", html)
        self.assertIn("u003c", self._by_payload(html))

    def test_customer_text_cannot_close_the_script_tag_for_the_bot_owner(self):
        """أي زبون على تليجرام/واتساب يكتب النص، وصاحب البوت يفتح صفحته."""
        c = _client()
        _login(c, "shopowner", TEST_PW)
        html = c.get(f"/bot/{self.bot}").get_data(as_text=True)
        self.assertNotIn(PAYLOAD, html)
        self.assertNotIn("</script><img", html)

    def test_platform_settings_cannot_inject_into_the_public_landing_page(self):
        """صفحة الهبوط عامة — ما يضبطه الأدمن فيها يصل لكل زائر."""
        db.set_platform("support_email", PAYLOAD)
        html = web.app.test_client().get("/").get_data(as_text=True)
        self.assertNotIn("</script><img", html)
        db.set_platform("support_email", "info@youssefalsherief.tech")

    def test_the_escaping_keeps_the_payload_usable(self):
        """الهروب داخل السلاسل فقط: JSON يفكّ لنفس القيم، والأيقونات تبقى SVG."""
        c = _client()
        _login(c, "shopowner", TEST_PW)
        obj = json.loads(self._by_payload(c.get("/dashboard").get_data(as_text=True)))
        self.assertTrue(obj["icons"]["grid"].startswith("<svg"))
        self.assertEqual(obj["user"]["name"], "shopowner")
        self.assertTrue(obj["t"]["nav_bots"])

    def test_line_separators_are_escaped_too(self):
        """U+2028/U+2029 صالحان في JSON ويكسران جافاسكربت — لا يمرّان خاماً."""
        out = web._js_json({"x": "a b c"})
        self.assertNotIn(" ", out)
        self.assertNotIn(" ", out)
        self.assertEqual(json.loads(out)["x"], "a b c")


if __name__ == "__main__":
    unittest.main(verbosity=2)
