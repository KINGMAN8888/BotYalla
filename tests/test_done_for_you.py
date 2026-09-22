"""«فريقنا يجهّزه لك» (الموظف يعمل داخل حساب العميل بإذنه) + وكيل المساعد + رحلة النجاح.
    python tests/test_done_for_you.py
"""
import json, os, sys, tempfile, unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_TMP = tempfile.mkdtemp(prefix="botyalla-dfy-")
os.environ["BOTYALLA_DB"] = os.path.join(_TMP, "t.db")        # قبل أي استيراد
os.environ["BOTYALLA_UPLOADS"] = _TMP
os.environ["BOTYALLA_LOGS"] = _TMP
os.environ["PUBLIC_URL"] = "https://botyalla.test"

import database as db          # noqa: E402
import site_assistant as SA    # noqa: E402
import app as A                # noqa: E402

CSRF = "tk"


def setUpModule():
    db.init_db()
    with db.get_conn() as c:
        for i, (n, r) in enumerate((("root", "admin"), ("helper", "support"), ("mona", "user"),
                                    ("other", "user"), ("boss2", "admin")), start=1):
            c.execute("INSERT OR IGNORE INTO users(id,username,pw_hash,role,created_at) VALUES(?,?,?,?,0)",
                      (i, n, "pbkdf2:x$" + n, r))
    A.app.config["TESTING"] = True
    A.manager.notify_text = lambda *a, **k: None
    A.notify_admins = lambda *a, **k: None
    A.manager.start_bot = lambda bid: (True, "started")
    A.manager.stop_bot = lambda bid: (True, "stopped")
    A.manager.is_running = lambda bid: False


MONA, OTHER = 3, 4


def client(uid):
    c = A.app.test_client()
    u = db.get_user(uid)
    with c.session_transaction() as s:
        s.update(_csrf=CSRF, uid=uid, uname=u["username"], role=u["role"], pwv=A._pw_stamp(u["pw_hash"]))
    return c


def bot_of(owner, name="shop"):
    return db.create_bot(owner, name, f"wa:{owner}{len(name)}{name[:3].encode().hex()}", "customer_service",
                         {"business_name": name}, channel="whatsapp")


class Base(unittest.TestCase):
    def setUp(self):
        A._login_attempts.clear()
        db.revoke_grant(MONA)
        db.revoke_grant(OTHER)


class GrantTests(Base):
    def test_user_grant_needs_explicit_consent_and_opens_a_ticket(self):
        c = client(MONA)
        r = c.post("/assist/request", json={"note": "محل ملابس"}, headers={"X-CSRF-Token": CSRF})
        self.assertEqual(r.status_code, 400)
        d = c.post("/assist/request", json={"note": "محل ملابس", "consent": True}, headers={"X-CSRF-Token": CSRF}).get_json()
        self.assertTrue(d["ok"])
        self.assertIsNotNone(db.active_grant(MONA))
        self.assertIsNotNone(db.open_ticket_of_kind(MONA, "done_for_you"))
        c.post("/assist/revoke", headers={"X-CSRF-Token": CSRF})
        self.assertIsNone(db.active_grant(MONA))


class AssistModeTests(Base):
    def start(self, staff=1, user=MONA, note=None):
        c = client(staff)
        data = {"csrf_token": CSRF}
        if note:
            data["consent_note"] = note
        return c, c.post(f"/admin/users/{user}/assist", data=data)

    def test_no_consent_no_entry(self):
        c, r = self.start()
        self.assertIn("/admin/users", r.headers["Location"])
        with c.session_transaction() as s:
            self.assertEqual(s["uid"], 1)
            self.assertNotIn("assist", s)

    def test_staff_works_inside_with_limits_and_everything_is_logged(self):
        db.grant_create(MONA, "user", "عايز بوت")
        bid = bot_of(MONA, "mona_shop")
        c, r = self.start(staff=2)                           # الدعم مسموح له
        self.assertIn("/dashboard", r.headers["Location"])
        with c.session_transaction() as s:
            self.assertEqual(s["uid"], MONA)
        self.assertEqual(c.get("/dashboard").status_code, 200)
        self.assertIn('"assist"', c.get("/dashboard").get_data(as_text=True))
        self.assertEqual(c.get(f"/bot/{bid}").status_code, 200)
        # مقفول: الحساب · الدفع · الرصيد · محادثات العملاء · الحذف · الحملات · لوحة الأدمن
        for path in ("/account", "/billing", "/wallet", f"/bot/{bid}/inbox", "/admin/users", "/affiliate"):
            self.assertEqual(c.get(path).status_code, 302, path)
        self.assertEqual(c.post(f"/bot/{bid}/delete", data={"csrf_token": CSRF}).status_code, 403)
        self.assertIsNotNone(db.get_bot(bid, MONA), "الحذف اتمنع")
        self.assertEqual(c.post(f"/api/bot/{bid}/inbox", data={"csrf_token": CSRF}).status_code, 403)
        c.post(f"/bot/{bid}/stop", data={"csrf_token": CSRF})
        acts = [a["action"] for a in db.staff_actions_for(MONA)]
        self.assertIn("assist_start", acts)
        self.assertTrue(any(a.endswith(f"/bot/{bid}/stop") for a in acts))
        self.assertEqual({a["staff_id"] for a in db.staff_actions_for(MONA) if a["bot_id"] == bid}, {2})
        # الخروج يرجّع جلسة الموظف
        c.post("/assist/exit", data={"csrf_token": CSRF})
        with c.session_transaction() as s:
            self.assertEqual((s["uid"], s["role"]), (2, "support"))
            self.assertNotIn("assist", s)

    def test_customer_revoke_ends_the_session_immediately(self):
        db.grant_create(MONA, "user")
        c, _ = self.start()
        db.revoke_grant(MONA)
        r = c.get("/dashboard")
        self.assertIn("/admin/users", r.headers["Location"])
        with c.session_transaction() as s:
            self.assertEqual(s["uid"], 1)

    def test_staff_recorded_consent_needs_a_real_note(self):
        c, _ = self.start(note="تمام")                        # قصيرة جداً
        with c.session_transaction() as s:
            self.assertNotIn("assist", s)
        c, _ = self.start(note="وافقت على واتساب النهارده الساعة 3")
        with c.session_transaction() as s:
            self.assertEqual(s["uid"], MONA)
        self.assertEqual(db.active_grant(MONA)["via"], "staff")

    def test_cannot_enter_staff_accounts_or_as_plain_user(self):
        db.grant_create(5, "user")
        c, _ = self.start(staff=2, user=5)
        with c.session_transaction() as s:
            self.assertEqual(s["uid"], 2)
        db.grant_create(MONA, "user")
        r = client(OTHER).post(f"/admin/users/{MONA}/assist", data={"csrf_token": CSRF})
        self.assertEqual(r.status_code, 403)

    def test_user_sees_what_the_team_did(self):
        db.grant_create(MONA, "user")
        c, _ = self.start()
        c.post("/assist/exit", data={"csrf_token": CSRF})
        html = client(MONA).get("/dashboard").get_data(as_text=True)
        self.assertIn("بدأ يجهّز البوت", html)


class AgentTests(Base):
    def ask(self, c, action):
        orig_call, orig_chain = A.ai._call, A.ai.key_chain
        A.ai._call = lambda *a: json.dumps({"reply": "تمام", "links": [], "suggestions": [], "handoff": False,
                                            "action": action})
        A.ai.key_chain = lambda get: [{"p": "gemini", "key": "k"}]
        try:
            return c.post("/api/assistant", json={"text": "اعملها", "view": "dashboard"},
                          headers={"X-CSRF-Token": CSRF}).get_json()
        finally:
            A.ai._call, A.ai.key_chain = orig_call, orig_chain

    def act(self, c, tok):
        return c.post("/api/assistant/act", json={"token": tok}, headers={"X-CSRF-Token": CSRF}).get_json()

    def test_nothing_happens_before_the_user_presses_do_it(self):
        bid = bot_of(MONA, "agent_bot")
        c = client(MONA)
        r0 = self.act(c, self.ask(c, {"type": "ai_replies", "args": {"bot_id": bid, "on": True}})["action"]["token"])
        self.assertTrue(r0.get("upgrade"), "المجانية بلا ردود ذكية — حدّ الباقة محترم")
        db.activate_subscription(MONA, "merchant", days=30)
        d = self.ask(c, {"type": "ai_replies", "args": {"bot_id": bid, "on": True}})
        card = d["action"]
        self.assertIn("الردود الذكية", card["label"])
        self.assertIn("مزوّد الذكاء", card["warn"])
        self.assertNotEqual(json.loads(db.get_bot(bid)["config_json"]).get("response_mode"), "ai")
        r = self.act(c, card["token"])
        self.assertTrue(r["ok"], r)
        cfg = json.loads(db.get_bot(bid)["config_json"])
        self.assertEqual(cfg["response_mode"], "ai")
        self.assertTrue(cfg["ai_consent_at"])
        self.assertFalse(self.act(c, card["token"])["ok"], "الضغطة الثانية بنفس البطاقة لا تنفّذ")

    def test_someone_elses_bot_is_never_accepted(self):
        foreign = bot_of(OTHER, "not_mine")
        d = self.ask(client(MONA), {"type": "stop_bot", "args": {"bot_id": foreign}})
        self.assertIsNone(d["action"])

    def test_start_and_share(self):
        bid = bot_of(MONA, "run_me")
        c = client(MONA)
        self.assertTrue(self.act(c, self.ask(c, {"type": "start_bot", "args": {"bot_id": bid}})["action"]["token"])["ok"])
        r = self.act(c, self.ask(c, {"type": "share_bot", "args": {"bot_id": bid}})["action"]["token"])
        self.assertEqual(r["kind"], "share")
        self.assertIn("/poster", r["poster"])

    def test_team_help_grants_access_but_not_from_inside_assist(self):
        c = client(MONA)
        r = self.act(c, self.ask(c, {"type": "team_help", "args": {"note": "اعملوا لي بوت محل"}})["action"]["token"])
        self.assertTrue(r["ok"])
        self.assertIsNotNone(db.active_grant(MONA))
        s = client(1)
        s.post(f"/admin/users/{MONA}/assist", data={"csrf_token": CSRF})
        r = self.act(s, self.ask(s, {"type": "team_help", "args": {"note": "x"}})["action"]["token"])
        self.assertFalse(r["ok"], "الموظف لا يمنح نفسه إذناً باسم العميل")

    def test_visitors_get_no_actions(self):
        c = A.app.test_client()
        with c.session_transaction() as s:
            s["_csrf"] = CSRF
        d = self.ask(c, {"type": "create_telegram_bot", "args": {"name": "x"}})
        self.assertIsNone(d["action"])

    def test_clean_action_validation(self):
        self.assertIsNone(SA.clean_action({"type": "delete_account"}, {1}))
        self.assertIsNone(SA.clean_action({"type": "design_bot", "args": {"bot_id": 1, "description": "قصير"}}, {1}))
        a = SA.clean_action({"type": "create_telegram_bot", "args": {"name": "محل", "template": "evil"}}, set())
        self.assertEqual(a["args"]["template"], "customer_service")


class JourneyTests(unittest.TestCase):
    def test_steps_follow_real_progress(self):
        j = A._journey([], "free")
        self.assertEqual(j["current"], "create")
        b = {"id": 9, "name": "x", "channel": "telegram", "template": "store", "running": True,
             "config_json": json.dumps({"kb": {"about": "ملابس"}, "bot_username": "shop_bot"}),
             "stats": {"subscribers": 5, "orders": 1}}
        j = A._journey([b], "free")
        self.assertEqual(j["current"], "grow")
        self.assertEqual(j["botUsername"], "shop_bot")
        self.assertIsNone(A._journey([b], "merchant")["current"])


if __name__ == "__main__":
    unittest.main()
