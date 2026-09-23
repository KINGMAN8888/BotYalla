"""«التسجيل السهل» من الأدمن (تفعيل بلا كود البريد + روابط لمرة واحدة) و«مساعد BotYalla» في الموقع.
    python tests/test_easy_signup_assistant.py
"""
import os, sys, tempfile, unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_TMP = tempfile.mkdtemp(prefix="botyalla-easy-")
os.environ["BOTYALLA_DB"] = os.path.join(_TMP, "t.db")        # قبل أي استيراد
os.environ["BOTYALLA_UPLOADS"] = _TMP
os.environ["BOTYALLA_LOGS"] = _TMP
os.environ["PUBLIC_URL"] = "https://botyalla.test"
os.environ.update({"SMTP_HOST": "smtp.test", "SMTP_PORT": "587", "SMTP_USER": "bot", "SMTP_PASS": "pw",
                   "SMTP_FROM": "BotYalla <no-reply@botyalla.test>", "SMTP_TLS": "starttls"})

import database as db          # noqa: E402
import mailer                  # noqa: E402
import site_assistant as SA    # noqa: E402
import app as A                # noqa: E402
from _signup import signup     # noqa: E402

CSRF = "tk"


class FakeSMTP:
    def __init__(self, *a, **k): pass
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def starttls(self, context=None): pass
    def login(self, u, p): pass
    def send_message(self, msg): pass


def setUpModule():
    db.init_db()
    with db.get_conn() as c:
        c.execute("INSERT OR IGNORE INTO users(id,username,pw_hash,role,created_at) VALUES(1,'root','x','admin',0)")
        c.execute("INSERT OR IGNORE INTO users(id,username,pw_hash,role,created_at) VALUES(2,'helper','x','support',0)")
    A.app.config["TESTING"] = True
    A.manager.notify_text = lambda *a, **k: None
    A.notify_admins = lambda *a, **k: None
    mailer.smtplib.SMTP = FakeSMTP
    mailer.SYNC = True


def client(uid=None, role="user"):
    c = A.app.test_client()
    with c.session_transaction() as s:
        s["_csrf"] = CSRF
        if uid:
            u = db.get_user(uid)
            s.update(uid=uid, uname=u["username"], role=u["role"], pwv=A._pw_stamp(u["pw_hash"]))
    return c


class Base(unittest.TestCase):
    def setUp(self):
        A._login_attempts.clear()


class ManualVerifyTests(Base):
    def test_admin_lets_a_stuck_customer_in(self):
        c = client()
        c.post("/register", data=signup("mona_stuck"))
        u = db.get_user_by_name("mona_stuck")
        self.assertTrue(db.email_gate(u))
        self.assertIn("/verify-email", c.get("/dashboard").headers["Location"])
        r = client(1).post(f"/admin/users/{u['id']}/verify-email", data={"csrf_token": CSRF})
        self.assertEqual(r.status_code, 302)
        u = db.get_user(u["id"])
        self.assertFalse(db.email_gate(u), "رُفع الحجب")
        self.assertIsNone(u["email_verified_at"], "لا ندّعي أن البريد مؤكَّد")
        self.assertTrue(db.get_setting(u["id"], "email_waived").startswith("1:"), "مسجَّل مين فعّله")
        self.assertEqual(c.get("/dashboard").status_code, 200)

    def test_support_role_and_users_cannot_waive(self):
        client().post("/register", data=signup("no_waive"))
        u = db.get_user_by_name("no_waive")
        for who in (2, u["id"]):
            client(who).post(f"/admin/users/{u['id']}/verify-email", data={"csrf_token": CSRF})
        self.assertTrue(db.email_gate(db.get_user(u["id"])))

    def test_admin_users_page_lists_pending_flag(self):
        client().post("/register", data=signup("flag_me"))
        html = client(1).get("/admin/users").get_data(as_text=True)
        self.assertIn('"verify_required": 1', html)
        self.assertIn('"invites"', html)


class InviteTests(Base):
    def make(self, **kw):
        r = client(1).post("/admin/invites", json=dict({"note": "منى", "days": 3}, **kw),
                           headers={"X-CSRF-Token": CSRF})
        return r.get_json()

    def test_invite_signup_skips_the_email_code_once(self):
        d = self.make()
        self.assertTrue(d["ok"])
        self.assertTrue(d["url"].startswith("https://botyalla.test/join/"))
        token = d["url"].rsplit("/", 1)[1]
        with db.get_conn() as c:
            self.assertFalse(c.execute("SELECT 1 FROM signup_invites WHERE token_hash=?", (token,)).fetchone(),
                             "التوكن نفسه لا يُخزَّن")
        c = client()
        self.assertIn("/register", c.get(f"/join/{token}").headers["Location"])
        self.assertIn('"invite": true', c.get("/register").get_data(as_text=True))
        r = c.post("/register", data=signup("invited_one"))
        self.assertIn("/start", r.headers["Location"])   # حساب جديد بلا بوت
        u = db.get_user_by_name("invited_one")
        self.assertFalse(db.email_gate(u))
        self.assertEqual(db.list_invites()[0]["used_by"], u["id"])
        # الرابط لمرة واحدة: زائر ثاني يسجّل عادي بالكود
        c2 = client()
        c2.get(f"/join/{token}")
        c2.post("/register", data=signup("second_try"))
        self.assertTrue(db.email_gate(db.get_user_by_name("second_try")))

    def test_failed_signup_keeps_the_link_valid(self):
        token = self.make()["url"].rsplit("/", 1)[1]
        c = client()
        c.get(f"/join/{token}")
        c.post("/register", data=signup("bad_pw", password="x", password2="x"))
        self.assertIsNotNone(db.invite_valid(A._token_hash(token)))

    def test_revoked_and_non_admin(self):
        d = self.make()
        token = d["url"].rsplit("/", 1)[1]
        iid = d["invites"][0]["id"]
        r = client(1).post(f"/admin/invites/{iid}/revoke", headers={"X-CSRF-Token": CSRF})
        self.assertTrue(r.get_json()["ok"])
        self.assertIsNone(db.invite_valid(A._token_hash(token)))
        r = client(2).post("/admin/invites", json={}, headers={"X-CSRF-Token": CSRF})
        self.assertNotEqual(r.status_code, 200)

    def test_days_are_capped(self):
        self.make(days=999)
        inv = db.list_invites()[0]
        self.assertLessEqual(inv["expires_at"] - inv["created_at"], db.INVITE_MAX_DAYS * 86400)


class AssistantTests(Base):
    def ask(self, c, text, view="home", history=None):
        return c.post("/api/assistant", json={"text": text, "view": view, "history": history or []},
                      headers={"X-CSRF-Token": CSRF})

    def test_boot_payload_on_landing_and_dashboard(self):
        html = client().get("/").get_data(as_text=True)
        self.assertIn('"assistant"', html)
        self.assertIn("/api/assistant", html)
        u = db.get_user_by_name("root")
        self.assertIn('"view": "dashboard"', client(u["id"]).get("/dashboard").get_data(as_text=True))

    def test_offline_answer_from_the_guide_with_safe_links(self):
        orig = A.ai.key_chain
        A.ai.key_chain = lambda get: []
        try:
            d = self.ask(client(), "مش لاقي الكود على الايميل").get_json()
        finally:
            A.ai.key_chain = orig
        self.assertTrue(d["ok"])
        self.assertIn("Spam", d["reply"])
        self.assertTrue(all(l["url"].startswith("/") for l in d["links"]))

    def test_ai_links_are_whitelisted_and_user_context_has_no_contacts(self):
        seen = {}
        orig_call, orig_chain = A.ai._call, A.ai.key_chain
        def fake(provider, key, system, user):
            seen["user"] = user
            return '{"reply": "تمام", "links": ["pricing", "https://evil.test", "hack"], "suggestions": ["أ", "%s"], "handoff": true}' % ("x" * 40)
        A.ai._call, A.ai.key_chain = fake, (lambda get: [{"p": "gemini", "key": "k"}])
        try:
            client().post("/register", data=signup("asker"))
            u = db.get_user_by_name("asker")
            d = self.ask(client(u["id"]), "ليه مش عارف أدخل؟", view="verify_email").get_json()
        finally:
            A.ai._call, A.ai.key_chain = orig_call, orig_chain
        self.assertEqual([l["k"] for l in d["links"]], ["pricing"])
        self.assertEqual(d["suggestions"], ["أ"])
        self.assertTrue(d["handoff"])
        self.assertIn('"must_verify_email": true', seen["user"], "المحجوب يقدر يسأل المساعد")
        self.assertNotIn(u["email"], seen["user"])
        self.assertNotIn(u["phone"], seen["user"])

    def test_handoff_signed_in_opens_ticket_visitor_gets_whatsapp(self):
        u = db.get_user_by_name("root")
        hist = [{"role": "user", "text": "دفعت ومفعّلتش"}, {"role": "bot", "text": "هوصلك بالفريق"}]
        c = client()
        c.post("/register", data=signup("needs_human"))
        uid = db.get_user_by_name("needs_human")["id"]
        d = client(uid).post("/api/assistant/handoff", json={"history": hist, "view": "billing"},
                             headers={"X-CSRF-Token": CSRF}).get_json()
        self.assertEqual(d["kind"], "ticket")
        self.assertEqual(db.get_ticket(d["id"])["user_id"], uid)
        d = client().post("/api/assistant/handoff", json={"history": hist},
                          headers={"X-CSRF-Token": CSRF}).get_json()
        self.assertEqual(d["kind"], "whatsapp")
        self.assertTrue(d["url"].startswith("https://wa.me/201281275886?text="))
        self.assertIsNotNone(u)

    def test_csrf_and_rate_limit(self):
        c = client()
        self.assertEqual(c.post("/api/assistant", json={"text": "hi"}).status_code, 400)
        orig = A.ai.key_chain
        A.ai.key_chain = lambda get: []
        try:
            codes = [self.ask(c, "سعر").status_code for _ in range(31)]
        finally:
            A.ai.key_chain = orig
        self.assertEqual(codes[-1], 429)

    def test_every_guide_link_resolves(self):
        with A.app.test_request_context():
            for k, ep in SA.LINK_KEYS.items():
                self.assertTrue(A.url_for(ep).startswith("/"), k)
        for g in SA.GUIDE.values():
            self.assertTrue(set(g["links"]) <= set(SA.LINK_KEYS))


if __name__ == "__main__":
    unittest.main()
