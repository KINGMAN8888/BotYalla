"""باقة «راحة البال» (VIP) + العمولة المتكررة بسقف 12 شهراً — business/DEV_REQUIREMENTS_GROWTH.md §2 و§3.
    python tests/test_vip_affiliate.py
"""
import itertools, json, os, sys, tempfile, time, unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_TMP = tempfile.mkdtemp(prefix="botyalla-vip-")
os.environ["BOTYALLA_DB"] = os.path.join(_TMP, "t.db")        # قبل أي استيراد
os.environ["BOTYALLA_UPLOADS"] = _TMP
os.environ["BOTYALLA_LOGS"] = _TMP

import database as db          # noqa: E402
import plans                   # noqa: E402
import app as A                # noqa: E402

CSRF = "c" * 32
_n = itertools.count(1)


def user(name=None):
    name = name or f"u{next(_n)}_{int(time.time() * 1000)}"
    return db.create_user(name, "x")


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        db.init_db()
        with db.get_conn() as c:
            c.execute("INSERT OR IGNORE INTO users(id,username,pw_hash,role,created_at) VALUES(1,'root','x','admin',0)")
        if not db.get_bot_by_token("wa:9999"):
            db.create_bot(1, "BotYalla", "wa:9999", "customer_service",
                          {"business_name": "BotYalla", "platform_kb": True, "response_mode": "ai",
                           "bot_username": "+201281275886"},
                          channel="whatsapp")

    def setUp(self):
        A._login_attempts.clear()
        self.alerts = []
        self._notify = A.notify_admins
        A.notify_admins = self.alerts.append
        self._tk = A._alert_ticket
        A._alert_ticket = lambda tid, body: self.alerts.append(f"#T{tid} {body}")

    def tearDown(self):
        A.notify_admins = self._notify
        A._alert_ticket = self._tk

    def client(self, uid=None):
        c = A.app.test_client()
        with c.session_transaction() as s:
            s["_csrf"] = CSRF
            if uid:
                s["uid"] = uid
        return c

    def pay(self, u, plan="merchant", amount=299, cycle="monthly"):
        pid = db.create_payment(u, plan, "instapay", amount, "R", "s.png",
                                f"h{u}{next(_n)}", "{}", base_amount=amount, billing_cycle=cycle)
        db.finalize_payment(pid, "approved")
        return pid


# --------------------------------------------------------------------------- VIP
class VipTests(Base):
    def test_vip_is_sold_annual_only_whatever_is_requested(self):
        self.assertIn("vip", plans.ORDER)
        self.assertEqual(plans.norm_cycle("monthly", "vip"), "annual")
        self.assertEqual(plans.norm_cycle("monthly", "merchant"), "monthly")
        q = A.quote("vip", user(), cycle="monthly")
        self.assertEqual(q["cycle"], "annual")
        self.assertEqual(q["days"], 365)
        self.assertEqual(q["base"], plans.annual_price("vip"))

    def test_checkout_page_forces_annual(self):
        u = user()
        html = self.client(u).get("/subscribe/vip?cycle=monthly").get_data(as_text=True)
        self.assertIn('"cycle": "annual"', html)

    def test_public_pricing_marks_vip_as_by_call(self):
        html = self.client().get("/").get_data(as_text=True)
        self.assertIn('"by_call": true', html)
        self.assertIn('"csrf"', html)

    def test_visitor_request_becomes_a_lead_and_an_alert(self):
        body = {"name": "م. سامي", "company": "مصنع الدلتا", "phone": "01001234567",
                "notes": "طلبات جملة", "consent": True}
        d = self.client().post("/vip/request", json=body, headers={"X-CSRF-Token": CSRF}).get_json()
        self.assertTrue(d["ok"], d)
        official = db.get_bot_by_token("wa:9999")["id"]
        leads = [json.loads(l["data_json"]) if "data_json" in l else l["data"] for l in db.list_leads(official)]
        self.assertTrue(any(x.get("source") == "vip_call" and x["company"] == "مصنع الدلتا" for x in leads))
        self.assertTrue(any("مصنع الدلتا" in a for a in self.alerts))

    def test_member_request_opens_one_ticket(self):
        u = user()
        body = {"name": "أحمد", "company": "شركة النور", "phone": "+201001234567", "consent": True}
        c = self.client(u)
        d1 = c.post("/vip/request", json=body, headers={"X-CSRF-Token": CSRF}).get_json()
        d2 = c.post("/vip/request", json=body, headers={"X-CSRF-Token": CSRF}).get_json()
        self.assertTrue(d1["ok"] and d2["ok"])
        self.assertTrue(d2.get("existing"))
        self.assertEqual(db.open_ticket_of_kind(u, "vip_call"), d2["id"])

    def test_consent_and_validation(self):
        base = {"name": "x", "company": "y", "phone": "01001234567"}
        c = self.client()
        self.assertEqual(c.post("/vip/request", json=dict(base, consent=False),
                                headers={"X-CSRF-Token": CSRF}).status_code, 400)
        self.assertEqual(c.post("/vip/request", json=dict(base, phone="12", consent=True),
                                headers={"X-CSRF-Token": CSRF}).status_code, 400)
        self.assertEqual(c.post("/vip/request", json=dict(base, consent=True)).status_code, 400)   # CSRF


# --------------------------------------------------------------------- العمولة
class RecurringCommissionTests(Base):
    def setUp(self):
        super().setUp()
        self.aff = user()
        db.ensure_affiliate(self.aff, f"AFF{self.aff}", 20)
        self.ref = user()
        self.assertTrue(db.attach_referral(self.ref, f"AFF{self.aff}"))

    def earned(self):
        return db.get_affiliate(self.aff)["total_earned"]

    def test_first_payment_then_every_renewal_within_12_months(self):
        self.pay(self.ref)                                  # الأولى: 20% × 299
        self.assertAlmostEqual(self.earned(), 59.8)
        p2 = self.pay(self.ref)
        self.assertAlmostEqual(self.earned(), 119.6)
        self.assertEqual(db.commission_of_payment(p2)["renewal"], True)
        s = db.affiliate_summary(self.aff)
        self.assertAlmostEqual(s["renewals"], 59.8)
        self.assertEqual(s["active"], 1)
        self.assertAlmostEqual(s["expected_monthly"], 59.8)   # 299 × 20%
        self.assertEqual(s["months"], 12)

    def test_approving_the_same_payment_twice_pays_once(self):
        self.pay(self.ref)
        p2 = self.pay(self.ref)
        before = self.earned()
        with db.get_conn() as c:
            row = c.execute("SELECT amount FROM payments WHERE id=?", (p2,)).fetchone()
            self.assertIsNone(db.credit_referral(self.ref, p2, row["amount"], conn=c))
        self.assertEqual(self.earned(), before)

    def test_no_commission_after_the_12_month_cap(self):
        self.pay(self.ref)
        with db.get_conn() as c:                            # أول دفعة قبل 366 يوماً
            c.execute("UPDATE referrals SET converted_at=? WHERE referred_user_id=?",
                      (int(time.time()) - 366 * 86400, self.ref))
        before = self.earned()
        self.pay(self.ref)
        self.assertEqual(self.earned(), before)
        self.assertEqual(db.affiliate_summary(self.aff)["expected_monthly"], 0)

    def test_inactive_partner_earns_nothing(self):
        self.pay(self.ref)
        db.set_affiliate(self.aff, is_active=False)
        before = self.earned()
        self.pay(self.ref)
        self.assertEqual(self.earned(), before)

    def test_annual_referral_counts_its_monthly_equivalent(self):
        self.pay(self.ref, plan="whatsapp", amount=plans.annual_price("whatsapp"), cycle="annual")
        s = db.affiliate_summary(self.aff)
        self.assertAlmostEqual(s["expected_monthly"], round(plans.annual_price("whatsapp") / 12 * 0.2, 2), places=1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
