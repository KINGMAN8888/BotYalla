"""ربط واتساب بضغطة (Embedded Signup) — بلا Meta حقيقية: httpx.Client مزيّف يسجّل الطلبات.
    python tests/test_wa_signup.py
"""
import json, os, sys, tempfile, unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_TMP = tempfile.mkdtemp(prefix="botyalla-wasignup-")
os.environ["BOTYALLA_DB"] = os.path.join(_TMP, "t.db")        # قبل أي استيراد
os.environ["BOTYALLA_UPLOADS"] = _TMP
os.environ["BOTYALLA_LOGS"] = _TMP
os.environ["META_APP_ID"] = "1337778974883863"
os.environ["WA_ES_CONFIG_ID"] = "1384888526614030"

import database as db          # noqa: E402
import wa_signup as WAS        # noqa: E402
import app as A                # noqa: E402

WABA, PHONE, OTHER = "111222333444", "555666777888", "999000111222"


class Resp:
    def __init__(self, code, body):
        self.status_code, self._b = code, body

    def json(self):
        return self._b


class FakeMeta:
    """يحاكي Graph API: تبديل الكود · أرقام الـWABA · الاشتراك · التسجيل."""
    calls = []
    register_status = 200
    code_ok = True

    def __init__(self, *a, **k): pass
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def close(self): pass

    def get(self, url, params=None, headers=None):
        FakeMeta.calls.append(("GET", url, dict(params or {}), dict(headers or {})))
        if url.endswith("/oauth/access_token"):
            if FakeMeta.code_ok and params.get("client_secret") == "app-secret":
                return Resp(200, {"access_token": "EAAB-customer-token"})
            return Resp(400, {"error": {"message": "Invalid verification code format."}})
        if url.endswith(f"/{WABA}/phone_numbers"):
            return Resp(200, {"data": [{"id": PHONE, "display_phone_number": "+20 100 000 0001",
                                        "verified_name": "Raghad Store"}]})
        return Resp(404, {"error": {"message": "unknown"}})

    def post(self, url, headers=None, json=None):
        FakeMeta.calls.append(("POST", url, dict(json or {}), dict(headers or {})))
        if url.endswith("/subscribed_apps"):
            return Resp(200, {"success": True})
        if url.endswith("/register"):
            if FakeMeta.register_status == 200:
                return Resp(200, {"success": True})
            return Resp(400, {"error": {"message": "Two-step verification PIN mismatch."}})
        return Resp(404, {})


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        db.init_db()
        with db.get_conn() as c:
            c.execute("INSERT OR IGNORE INTO users(id,username,pw_hash,role,created_at) VALUES(1,'root','x','admin',0)")
            c.execute("INSERT OR IGNORE INTO users(username,pw_hash,role,created_at) VALUES('shop','x','user',0)")
            c.execute("INSERT OR IGNORE INTO users(username,pw_hash,role,created_at) VALUES('free1','x','user',0)")
        cls.owner = db.get_user_by_name("shop")["id"]
        cls.free = db.get_user_by_name("free1")["id"]
        db.set_platform("wa_app_secret", "app-secret")

    def setUp(self):
        FakeMeta.calls, FakeMeta.register_status, FakeMeta.code_ok = [], 200, True
        self._client = WAS.httpx.Client
        WAS.httpx.Client = FakeMeta
        db.activate_subscription(self.owner, "whatsapp")
        A._login_attempts.clear()                      # حدّ المحاولات لكل مستخدم — لا يتراكم بين الاختبارات
        with db.get_conn() as c:
            c.execute("DELETE FROM bots")

    def tearDown(self):
        WAS.httpx.Client = self._client

    def client(self, uid):
        c = A.app.test_client()
        with c.session_transaction() as s:
            s["uid"] = uid; s["_csrf"] = "c" * 32
        return c

    def finish(self, uid, **kw):
        body = {"code": "AQD-code", "waba_id": WABA, "phone_id": PHONE, "name": "رغد", "template": "store"}
        body.update(kw)
        return self.client(uid).post("/whatsapp/es/finish", json=body, headers={"X-CSRF-Token": "c" * 32})


class SignupTests(Base):
    def test_one_tap_creates_a_working_whatsapp_bot(self):
        r = self.finish(self.owner)
        d = r.get_json()
        self.assertTrue(d["ok"], d)
        bots = db.list_bots(self.owner)
        self.assertEqual(len(bots), 1)
        b = db.get_bot(bots[0]["id"])
        self.assertEqual(b["token"], f"wa:{PHONE}")
        self.assertEqual(b["channel"], "whatsapp")
        cfg = json.loads(b["config_json"])
        self.assertEqual(cfg["wa_token"], "EAAB-customer-token")
        self.assertEqual(cfg["wa_waba_id"], WABA)
        self.assertEqual(cfg["created_via"], "embedded_signup")
        self.assertRegex(cfg["wa_pin"], r"^\d{6}$")
        # الخطوات بالترتيب: تبديل ← تحقق ← اشتراك ← تسجيل بنفس الـPIN
        urls = [c[1].rsplit("/", 1)[-1] for c in FakeMeta.calls]
        self.assertEqual(urls, ["access_token", "phone_numbers", "subscribed_apps", "register"])
        self.assertEqual(FakeMeta.calls[-1][2]["pin"], cfg["wa_pin"])
        self.assertEqual(FakeMeta.calls[0][2]["client_id"], "1337778974883863")

    def test_number_outside_the_shared_account_is_refused(self):
        d = self.finish(self.owner, phone_id=OTHER).get_json()
        self.assertFalse(d["ok"])
        self.assertEqual(d["step"], "verify")
        self.assertEqual(db.list_bots(self.owner), [])
        self.assertFalse(any(c[1].endswith("/register") for c in FakeMeta.calls), "سجّل رقماً لم يُتحقّق منه")

    def test_bad_code_creates_nothing(self):
        FakeMeta.code_ok = False
        d = self.finish(self.owner).get_json()
        self.assertEqual((d["ok"], d["step"]), (False, "exchange"))
        self.assertEqual(db.list_bots(self.owner), [])

    def test_registration_problem_is_reported_not_hidden(self):
        FakeMeta.register_status = 400
        d = self.finish(self.owner).get_json()
        self.assertTrue(d["ok"])
        self.assertIn("PIN mismatch", d["warning"])
        cfg = json.loads(db.get_bot(db.list_bots(self.owner)[0]["id"])["config_json"])
        self.assertIn("PIN mismatch", cfg["wa_setup_warning"])

    def test_free_plan_cannot_connect(self):
        r = self.finish(self.free)
        self.assertEqual(r.status_code, 403)
        self.assertTrue(r.get_json().get("upgrade"))
        self.assertEqual(FakeMeta.calls, [], "استدعى Meta لباقة لا تتيح واتساب")

    def test_bad_ids_and_csrf(self):
        self.assertFalse(self.finish(self.owner, waba_id="abc").get_json()["ok"])
        r = self.client(self.owner).post("/whatsapp/es/finish", json={"code": "x"})
        self.assertEqual(r.status_code, 400)

    def test_same_number_twice_is_refused(self):
        self.assertTrue(self.finish(self.owner).get_json()["ok"])
        d = self.finish(self.owner).get_json()
        self.assertFalse(d["ok"])
        self.assertEqual(len(db.list_bots(self.owner)), 1)


class PageAndPolicyTests(Base):
    def test_dashboard_gets_config_only_with_whatsapp_plan(self):
        html = self.client(self.owner).get("/dashboard").get_data(as_text=True)
        self.assertIn("1384888526614030", html)
        self.assertNotIn("app-secret", html)
        html = self.client(self.free).get("/dashboard").get_data(as_text=True)
        self.assertNotIn("1384888526614030", html)

    def test_csp_opens_facebook_only_when_configured(self):
        csp = A._build_csp()
        self.assertIn("https://connect.facebook.net", csp)
        self.assertIn("frame-src", csp)
        script = [d for d in csp.split("; ") if d.startswith("script-src ")][0]
        self.assertNotIn("unsafe-inline", script)
        os.environ.pop("WA_ES_CONFIG_ID")
        try:
            self.assertIsNone(WAS.client_config())
            self.assertEqual(WAS.csp_sources(), {})
        finally:
            os.environ["WA_ES_CONFIG_ID"] = "1384888526614030"

    def test_customer_token_and_pin_never_reach_the_browser(self):
        self.assertTrue(self.finish(self.owner).get_json()["ok"])
        bid = db.list_bots(self.owner)[0]["id"]
        html = self.client(self.owner).get(f"/bot/{bid}").get_data(as_text=True)
        self.assertNotIn("EAAB-customer-token", html)
        pin = json.loads(db.get_bot(bid)["config_json"])["wa_pin"]
        self.assertNotIn(f'"wa_pin"', html)
        self.assertIn(f"wa:{PHONE}", html)                # معرّف الرقم ليس سراً
        del pin


if __name__ == "__main__":
    unittest.main(verbosity=2)
