"""قفل واتساب على الباقات التي لا تشمله + ربط واتساب بمساعدة الفريق.

القواعد المختبَرة: **لا واتساب لباقة لا تشمله** (ولا نتصل بـ Meta أصلاً)، وطلب
المساعدة لباقات واتساب وحدها وطلب مفتوح واحد لكل عميل، والفريق لا يُنشئ بوتاً إلا
من تذكرة «ربط واتساب» وفي حساب صاحبها **وبحدود باقته هو**، والتوكن لا يُكتب في التذكرة.

    python tests/test_wa_assist.py
"""
import json, os, re, secrets, sys, tempfile, unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_TMPDIR = tempfile.mkdtemp(prefix="botyalla-waassist-")
os.environ["BOTYALLA_DB"] = os.path.join(_TMPDIR, "test.db")   # قبل استيراد database
os.environ["BOTYALLA_UPLOADS"] = _TMPDIR
os.environ["ADMIN_USER"] = "admin"
os.environ["ADMIN_PASS"] = f"tst_adm_{secrets.token_hex(8)}"

import auth                                # noqa: E402
import database as db                      # noqa: E402
import app as web                          # noqa: E402

H = {"X-CSRF-Token": "tk"}
ASK = {"business": "محل رغد", "number": "+20 100 123 4567", "meta": "no", "contact": "بعد 6"}


def _boot():
    db.init_db()
    web.seed_platform_defaults()
    web.contact_defaults()
    web.seed_default_admin()
    web.app.config["TESTING"] = True


def _client():
    c = web.app.test_client()
    with c.session_transaction() as s:
        s["_csrf"] = "tk"
    return c


class WhatsAppLockAndAssistTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        _boot()
        cls.pw = "wa_" + secrets.token_hex(6)

        def mk(name, plan=None, role=None):
            u = db.create_user(name, auth.hash_password(cls.pw))
            if plan:
                db.activate_subscription(u, plan, days=30)
            if role:
                db.set_user_role(u, role)
            return u
        cls.free, cls.merch = mk("wa_free"), mk("wa_merch", "merchant")
        cls.cust, cls.staff = mk("wa_cust", "whatsapp"), mk("wa_staff", role="support")
        cls._verify = web.wa_verify
        cls.verified = []

        def fake_verify(phone_id, token):
            cls.verified.append(phone_id)
            return {"ok": True, "number": "+20 100 123 4567", "name": "Raghad"}
        web.wa_verify = fake_verify

    @classmethod
    def tearDownClass(cls):
        web.wa_verify = cls._verify

    def setUp(self):
        web._login_attempts.clear()

    def _as(self, name):
        c = _client()
        c.post("/login", data={"username": name, "password": self.pw, "csrf_token": "tk"})
        return c

    def _connect(self, who, tid, phone_id, **extra):
        data = {"name": "رغد واتساب", "template": "customer_service", "wa_phone_id": phone_id,
                "wa_token": "EAAG-secret-token", "waba_id": "777", "csrf_token": "tk", **extra}
        return self._as(who).post(f"/admin/tickets/{tid}/wa-connect", data=data)

    def _ticket(self):
        r = self._as("wa_cust").post("/whatsapp/assist", json=ASK, headers=H)
        return r.get_json()["id"]

    # ---- القفل ----
    def test_the_dashboard_locks_whatsapp_for_free_and_merchant(self):
        for name in ("wa_free", "wa_merch"):
            html = self._as(name).get("/dashboard").get_data(as_text=True)
            self.assertRegex(html, r'"waAllowed":\s*false', name)
            self.assertRegex(html, r'"waPlan":\s*false', name)
        self.assertRegex(self._as("wa_cust").get("/dashboard").get_data(as_text=True),
                         r'"waPlan":\s*true')

    def test_a_locked_plan_cannot_create_a_whatsapp_bot(self):
        before = len(self.verified)
        for name, u in (("wa_free", self.free), ("wa_merch", self.merch)):
            r = self._as(name).post("/bot/create", data={
                "channel": "whatsapp", "name": "X", "template": "flow", "wa_phone_id": "123",
                "wa_token": "t", "csrf_token": "tk"})
            self.assertEqual(r.status_code, 302)
            self.assertIn("pricing", r.headers["Location"])
            self.assertEqual(db.count_user_bots(u), 0)
        self.assertEqual(len(self.verified), before, "لا اتصال بـ Meta لباقة لا تشمل واتساب")

    # ---- طلب المساعدة ----
    def test_assist_is_refused_outside_whatsapp_plans(self):
        r = self._as("wa_merch").post("/whatsapp/assist", json=ASK, headers=H)
        self.assertEqual(r.status_code, 403)
        self.assertIsNone(db.open_ticket_of_kind(self.merch, "wa_setup"))

    def test_assist_opens_one_wa_setup_ticket_and_reuses_it(self):
        c = self._as("wa_cust")
        a = c.post("/whatsapp/assist", json=ASK, headers=H).get_json()
        b = c.post("/whatsapp/assist", json=ASK, headers=H).get_json()
        self.assertTrue(a["ok"])
        self.assertEqual(b["id"], a["id"])
        self.assertTrue(b["existing"], "طلب مفتوح واحد لكل عميل")
        tk = db.get_ticket(a["id"])
        self.assertEqual((tk["kind"], tk["user_id"]), ("wa_setup", self.cust))
        body = db.list_tickets(user_id=self.cust)[0]["msgs"][0]["body"]
        self.assertIn("+201001234567", body)
        self.assertIn("محل رغد", body)

    def test_a_bad_number_is_refused(self):
        u = db.create_user("wa_cust2", auth.hash_password(self.pw))   # بلا طلب مفتوح سابق
        db.activate_subscription(u, "whatsapp", days=30)
        r = self._as("wa_cust2").post("/whatsapp/assist", json=dict(ASK, number="12"), headers=H)
        self.assertEqual(r.status_code, 400)
        self.assertIsNone(db.open_ticket_of_kind(u, "wa_setup"))

    def test_the_general_support_form_cannot_open_a_wa_setup_ticket(self):
        before = {t["id"] for t in db.list_tickets(user_id=self.merch)}
        self._as("wa_merch").post("/support", data={
            "kind": "wa_setup", "subject": "x", "body": "اربطوا لي واتساب لو سمحتم", "csrf_token": "tk"})
        new = [t["kind"] for t in db.list_tickets(user_id=self.merch) if t["id"] not in before]
        self.assertEqual(new, ["other"], "نموذج الدعم العام لا يفتح تذكرة ربط واتساب")

    # ---- الربط من الفريق ----
    def test_staff_connects_whatsapp_into_the_customers_account(self):
        tid = self._ticket()
        before = db.count_user_bots(self.cust)
        r = self._connect("wa_staff", tid, "5550001")
        self.assertEqual(r.status_code, 302)
        self.assertEqual(db.count_user_bots(self.cust), before + 1)
        b = [x for x in db.list_bots(self.cust) if x["token"] == "wa:5550001"][0]
        cfg = json.loads(b["config_json"])
        self.assertEqual(b["channel"], "whatsapp")
        self.assertEqual((cfg["wa_token"], cfg["wa_waba_id"], cfg["created_via"]),
                         ("EAAG-secret-token", "777", "staff"))
        tk = [t for t in db.list_tickets(user_id=self.cust) if t["id"] == tid][0]
        self.assertEqual(tk["status"], "answered", "العميل يُبلَّغ في التذكرة")
        self.assertTrue(all("EAAG-secret-token" not in m["body"] for m in tk["msgs"]),
                        "التوكن لا يُكتب في التذكرة")

    def test_staff_connect_respects_the_customers_plan(self):
        tid = db.create_ticket(self.merch, "wa_setup", "ربط واتساب — X", "طلب قبل تغيير الباقة")
        self._connect("wa_staff", tid, "5550002")
        self.assertEqual(db.count_user_bots(self.merch), 0, "حدود باقة العميل لا صلاحيات الفريق")

    def test_staff_connect_only_from_wa_setup_tickets(self):
        tid = db.create_ticket(self.cust, "support", "مشكلة", "البوت مش بيرد خالص")
        n = db.count_user_bots(self.cust)
        self._connect("wa_staff", tid, "5550003")
        self.assertEqual(db.count_user_bots(self.cust), n)

    def test_customers_cannot_use_the_staff_connect(self):
        tid = self._ticket()
        n = db.count_user_bots(self.cust)
        r = self._connect("wa_cust", tid, "5550004")
        self.assertEqual(r.status_code, 403)
        self.assertEqual(db.count_user_bots(self.cust), n)

    def test_the_admin_ticket_page_shows_the_customers_plan(self):
        self._ticket()
        html = self._as("wa_staff").get("/admin/tickets").get_data(as_text=True)
        self.assertTrue(re.search(r'"wa":\s*\{[^}]*"ok":\s*true', html), "باقة العميل تظهر للفريق")


if __name__ == "__main__":
    unittest.main(verbosity=2)
