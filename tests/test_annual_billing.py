"""L-08 — الدورة الفوترية السنوية.

الخطر هنا مالي بحت: المستخدم يختار «سنوي» في الواجهة، والمبلغ والمدة لا بد أن
يُحسبا في الخادم من اسم الدورة وحده. أي ثغرة تعني إما اشتراكاً سنوياً بسعر شهر،
أو دفعة سنوية تفعّل 30 يوماً فقط. الاختبارات أدناه تغطّي الحالتين معاً، ومعهما
حالة العبث المباشر بالفورم.

    python tests/test_annual_billing.py
"""
import io, os, secrets, sys, tempfile, time, unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_TMPDIR = tempfile.mkdtemp(prefix="botyalla-annual-")
os.environ["BOTYALLA_DB"] = os.path.join(_TMPDIR, "test.db")   # قبل استيراد database
os.environ["BOTYALLA_UPLOADS"] = _TMPDIR
ADMIN_PW = os.environ.setdefault("ADMIN_PASS", f"tst_adm_{secrets.token_hex(8)}")
TEST_PW = f"tst_pw_{secrets.token_hex(8)}"
os.environ["ADMIN_USER"] = "admin"
os.environ["ADMIN_PASS"] = ADMIN_PW

import auth                                # noqa: E402
import plans                               # noqa: E402
import database as db                      # noqa: E402
import app as web                          # noqa: E402

NOW = int(time.time())
DAY = 86400

# أصغر PNG يمرّ من `pay.validate_bytes`: التوقيع الصحيح + حشو يتجاوز MIN_BYTES.
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 8192


def _boot():
    db.init_db()
    web.seed_platform_defaults()
    web.contact_defaults()
    web.seed_default_admin()
    web._migrate_ai_key()
    web.app.config["TESTING"] = True
    os.makedirs(web.UPLOAD_DIR, exist_ok=True)


def _client():
    c = web.app.test_client()
    with c.session_transaction() as s:
        s["_csrf"] = "tk"
    return c


class CycleNormalisationTests(unittest.TestCase):
    """أي قيمة قادمة من المستخدم تُطبَّع قبل أي حساب."""

    def test_only_two_cycles_exist(self):
        self.assertEqual(plans.CYCLES, ("monthly", "annual"))

    def test_garbage_falls_back_to_monthly(self):
        for bad in ("", None, "yearly", "ANNUAL", "annual ", 12, {}, "weekly"):
            self.assertEqual(plans.norm_cycle(bad), "monthly", repr(bad))

    def test_days_follow_the_cycle(self):
        self.assertEqual(plans.cycle_days("annual"), 365)
        self.assertEqual(plans.cycle_days("nonsense"), 30)

    def test_annual_of_never_returns_negative_or_free_price(self):
        self.assertEqual(plans.annual_of(0), 0.0)
        self.assertEqual(plans.annual_of(None), 0.0)
        self.assertEqual(plans.annual_of(-50), 0.0)


class ServerPricingTests(unittest.TestCase):
    """السعر يُبنى في الخادم، ويتبع تجاوزات المالك على الدورتين."""

    @classmethod
    def setUpClass(cls):
        _boot()
        cls.u = db.create_user("annual_pricer", auth.hash_password(TEST_PW))

    def test_annual_quote_equals_the_annual_price(self):
        with web.app.test_request_context():
            q = web.quote("merchant", self.u, None, cycle="annual")
        self.assertEqual(q["cycle"], "annual")
        self.assertEqual(q["days"], 365)
        self.assertEqual(q["total"], float(plans.annual_price("merchant")))

    def test_monthly_is_still_the_default(self):
        with web.app.test_request_context():
            q = web.quote("merchant", self.u)
        self.assertEqual((q["cycle"], q["days"], q["total"]), ("monthly", 30, 299.0))

    def test_a_forged_cycle_is_priced_as_monthly(self):
        """أسوأ ما يفعله العابث: يدفع سعر شهر ويأخذ شهراً — لا سنة بسعر شهر."""
        with web.app.test_request_context():
            q = web.quote("merchant", self.u, None, cycle="annual_free_please")
        self.assertEqual((q["cycle"], q["days"], q["total"]), ("monthly", 30, 299.0))

    def test_owner_override_carries_into_the_annual_price(self):
        """لو خفّض المالك السعر الشهري، ينزل السنوي معه — لا يبقى على القائمة."""
        db.set_plan_override("merchant", price=100, discount_pct=0)
        try:
            with web.app.test_request_context():
                pr = web._plan_pricing("merchant", cycle="annual")
                q = web.quote("merchant", self.u, None, cycle="annual")
            self.assertEqual(pr["list_price"], plans.annual_of(100))   # 100×12×0.7 = 840
            self.assertEqual(q["total"], 840.0)
        finally:
            db.set_plan_override("merchant", price=None, discount_pct=0)

    def test_plan_discount_applies_on_top_of_the_annual_price(self):
        db.set_plan_override("merchant", price=None, discount_pct=50)
        try:
            with web.app.test_request_context():
                q = web.quote("merchant", self.u, None, cycle="annual")
            self.assertEqual(q["total"], round(plans.annual_price("merchant") * 0.5, 2))
        finally:
            db.set_plan_override("merchant", price=None, discount_pct=0)

    def test_priced_plans_exposes_both_cycles(self):
        with web.app.test_request_context():
            rows = {p["id"]: p for p in web.priced_plans("ar")}
        m = rows["merchant"]
        self.assertEqual(m["price"], 299)
        self.assertEqual(m["annual_price"], float(plans.annual_price("merchant")))
        self.assertEqual(m["annual_saving_pct"], 30)
        self.assertAlmostEqual(m["annual_monthly_equiv"], round(2510 / 12.0, 2), places=2)

    def test_free_has_no_annual_trap(self):
        with web.app.test_request_context():
            rows = {p["id"]: p for p in web.priced_plans("ar")}
        self.assertEqual(rows["free"]["annual_price"], 0)
        self.assertEqual(rows["free"]["annual_saving_pct"], 0)


class PromoOnAnnualTests(unittest.TestCase):
    """كود الخصم يُطبَّق على أساس الدورة المختارة لا على السعر الشهري."""

    @classmethod
    def setUpClass(cls):
        _boot()
        cls.u = db.create_user("annual_promo", auth.hash_password(TEST_PW))
        db.create_promo("ANNUAL10", "percent", 10, None, None, None, 0)

    def test_percent_promo_cuts_from_the_annual_base(self):
        with web.app.test_request_context():
            q = web.quote("merchant", self.u, "ANNUAL10", cycle="annual")
        annual = float(plans.annual_price("merchant"))
        self.assertEqual(q["base"], annual)
        self.assertEqual(q["promo_cut"], round(annual * 0.10, 2))
        self.assertEqual(q["total"], round(annual * 0.90, 2))

    def test_a_fixed_promo_never_exceeds_the_base(self):
        db.create_promo("HUGE", "fixed", 999999, None, None, None, 0)
        with web.app.test_request_context():
            q = web.quote("merchant", self.u, "HUGE", cycle="annual")
        self.assertEqual(q["total"], 0.0)
        self.assertGreaterEqual(q["total"], 0.0)


class AnnualPaymentFlowTests(unittest.TestCase):
    """المسار الكامل: فورم ← دفعة ← اعتماد ← اشتراك سنوي."""

    # كل اختبار هنا يأخذ **مستخدماً جديداً**: unittest يرتّب الدوال أبجدياً،
    # فمشاركة مستخدم واحد تجعل مدّة اختبار تُضاف إلى مدّة الذي قبله (التجديد
    # المبكر يمدّد عمداً) فينهار التأكيد لسببٍ لا علاقة له بما يختبره.
    _n = 0

    @classmethod
    def setUpClass(cls):
        _boot()

    def setUp(self):
        web._login_attempts.clear()
        AnnualPaymentFlowTests._n += 1
        self.uname = f"buyer_{AnnualPaymentFlowTests._n}"
        self.u = db.create_user(self.uname, auth.hash_password(TEST_PW))

    def _pay(self, cycle, extra=None):
        c = _client()
        c.post("/login", data={"username": self.uname, "password": TEST_PW,
                               "csrf_token": "tk"})
        data = {"method": "instapay", "ref": "R1", "csrf_token": "tk",
                # بصمة جديدة لكل دفعة: الإيصال المستخدم في طلب قائم يُرفض (payments.auto_check)
                "screenshot": (io.BytesIO(PNG + os.urandom(16)), "proof.png")}
        if cycle is not None:
            data["cycle"] = cycle
        data.update(extra or {})
        c.post("/subscribe/merchant", data=data,
               content_type="multipart/form-data", follow_redirects=True)
        return db.list_payments(self.u)[0]

    def test_an_annual_purchase_is_stored_with_its_cycle_and_price(self):
        p = self._pay("annual")
        self.assertEqual(p["billing_cycle"], "annual")
        self.assertEqual(p["amount"], float(plans.annual_price("merchant")))

    def test_a_forged_amount_in_the_form_is_ignored(self):
        """AGENTS.md §3.3 — لا يُقرأ أي مبلغ من الفورم، على أي دورة."""
        p = self._pay("annual", {"amount": "1", "total": "1", "price": "1"})
        self.assertEqual(p["amount"], float(plans.annual_price("merchant")))

    def test_a_forged_cycle_is_stored_as_monthly_at_the_monthly_price(self):
        p = self._pay("annual; DROP TABLE payments")
        self.assertEqual(p["billing_cycle"], "monthly")
        self.assertEqual(p["amount"], 299.0)

    def test_a_missing_cycle_defaults_to_monthly(self):
        p = self._pay(None)
        self.assertEqual(p["billing_cycle"], "monthly")
        self.assertEqual(p["amount"], 299.0)

    def test_approving_an_annual_payment_activates_365_days(self):
        p = self._pay("annual")
        row = db.finalize_payment(p["id"], "approved")
        self.assertIsNotNone(row)
        sub = db.get_subscription(self.u)
        self.assertEqual(sub["billing_cycle"], "annual")
        self.assertAlmostEqual((sub["expires_at"] - int(time.time())) / DAY, 365, delta=2)

    def test_approving_a_monthly_payment_activates_30_days(self):
        p = self._pay("monthly")
        db.finalize_payment(p["id"], "approved")
        sub = db.get_subscription(self.u)
        self.assertEqual(sub["billing_cycle"], "monthly")
        self.assertAlmostEqual((sub["expires_at"] - int(time.time())) / DAY, 30, delta=1)

    def test_a_monthly_renewal_extends_an_annual_subscription_instead_of_cutting_it(self):
        """التجديد المبكر يُضاف إلى المتبقّي — شهرٌ لا يقصّ سنةً إلى ثلاثين يوماً."""
        db.finalize_payment(self._pay("annual")["id"], "approved")
        before = db.get_subscription(self.u)["expires_at"]
        db.finalize_payment(self._pay("monthly")["id"], "approved")
        sub = db.get_subscription(self.u)
        self.assertAlmostEqual((sub["expires_at"] - before) / DAY, 30, delta=1)
        self.assertEqual(sub["billing_cycle"], "monthly")

    def test_a_rejected_annual_payment_activates_nothing(self):
        p = self._pay("annual")
        db.finalize_payment(p["id"], "rejected")
        sub = db.get_subscription(self.u)
        self.assertEqual(sub["plan"], "free")
        self.assertIsNone(sub["expires_at"])

    def test_an_annual_payment_cannot_be_approved_twice(self):
        """الحراسة الذرّية تبقى كما هي مع الدورة الجديدة — لا سنتان بدفعة واحدة."""
        p = self._pay("annual")
        self.assertIsNotNone(db.finalize_payment(p["id"], "approved"))
        first = db.get_subscription(self.u)["expires_at"]
        self.assertIsNone(db.finalize_payment(p["id"], "approved"))
        self.assertEqual(db.get_subscription(self.u)["expires_at"], first)


class CarryOverTests(unittest.TestCase):
    """تغيير الباقة لا يُسقط ما دُفع: قيمة الأيام المتبقية تُنقل إلى الجديدة.

    قبلها: «تاجر» سنوي (2510ج) ينتقل إلى «واتساب» فيبدأ من الصفر ويخسر
    السنة كلها. القيمة = المتبقي × ما دُفع فعلاً عن اليوم، والرصيد = القيمة ÷
    السعر اليومي للباقة الجديدة (سعر القائمة لا بعد الكود)."""

    @classmethod
    def setUpClass(cls):
        _boot()

    def _user(self, name):
        return db.create_user(name, auth.hash_password(TEST_PW))

    def _paid(self, u, plan, amount, cycle, base=None):
        pid = db.create_payment(u, plan, "instapay", amount, "R", "s.png",
                                f"co{u}{plan}{cycle}{amount}", "{}",
                                base_amount=amount if base is None else base, billing_cycle=cycle)
        return db.finalize_payment(pid, "approved")

    def _days_left(self, u):
        return (db.get_subscription(u)["expires_at"] - time.time()) / DAY

    def test_switching_mid_annual_converts_the_remaining_value(self):
        u = self._user("co_switch")
        self._paid(u, "merchant", 2510, "annual")
        row = self._paid(u, "whatsapp", 899, "monthly")
        credit = 2510 / (899 / 30.0)                 # ~365 يوماً × (2510/365) ÷ (899/30)
        self.assertAlmostEqual(self._days_left(u), 30 + credit, delta=0.05)
        self.assertEqual(row["carried_days"], int(credit))

    def test_a_downgrade_gives_more_days_not_fewer(self):
        u = self._user("co_down")
        self._paid(u, "agency", 2999, "monthly")
        self._paid(u, "merchant", 299, "monthly")
        self.assertAlmostEqual(self._days_left(u), 30 + 2999 / (299 / 30.0), delta=0.05)

    def test_the_same_plan_still_extends_without_conversion(self):
        u = self._user("co_same")
        self._paid(u, "merchant", 299, "monthly")
        row = self._paid(u, "merchant", 2510, "annual")
        self.assertAlmostEqual(self._days_left(u), 30 + 365, delta=0.05)
        self.assertEqual(row["carried_days"], 0)

    def test_a_plan_granted_by_the_admin_carries_nothing(self):
        u = self._user("co_gift")
        db.activate_subscription(u, "agency", days=30)          # بلا دفعة
        row = self._paid(u, "merchant", 299, "monthly")
        self.assertAlmostEqual(self._days_left(u), 30, delta=0.05)
        self.assertEqual(row["carried_days"], 0)

    def test_an_expired_plan_carries_nothing(self):
        u = self._user("co_expired")
        self._paid(u, "agency", 2999, "monthly")
        with db.get_conn() as c:
            c.execute("UPDATE subscriptions SET expires_at=? WHERE user_id=?", (NOW - DAY, u))
        self._paid(u, "merchant", 299, "monthly")
        self.assertAlmostEqual(self._days_left(u), 30, delta=0.05)

    def test_a_promo_on_the_new_plan_does_not_inflate_the_conversion(self):
        u = self._user("co_promo")
        self._paid(u, "merchant", 2510, "annual")
        self._paid(u, "whatsapp", 0, "monthly", base=899)        # كود 100%
        self.assertAlmostEqual(self._days_left(u), 30 + 2510 / (899 / 30.0), delta=0.05)

    def test_the_subscribe_page_shows_the_carry_over_before_paying(self):
        import re
        u = self._user("co_preview")
        self._paid(u, "merchant", 2510, "annual")
        c = _client()
        c.post("/login", data={"username": "co_preview", "password": TEST_PW, "csrf_token": "tk"})
        html = c.get("/subscribe/whatsapp?cycle=monthly").get_data(as_text=True)
        m = re.search(r'"carry": \{[^}]*"credit": (\d+)', html)
        self.assertIsNotNone(m, "المعاينة يجب أن تصل للصفحة قبل الدفع")
        self.assertEqual(int(m.group(1)), int(2510 / (899 / 30.0)))

    def test_the_receipt_mentions_the_carried_days(self):
        import mailer
        row = {"id": 9, "user_id": 1, "plan": "whatsapp", "amount": 899, "expires_at": NOW,
               "carried_days": 83}
        self.assertIn("+83 days", mailer.receipt_email(row, "approved", "en")[2])


class MigrationTests(unittest.TestCase):
    """الصفوف القائمة قبل L-08 لا تتغيّر، وتُقرأ كشهرية."""

    @classmethod
    def setUpClass(cls):
        _boot()
        cls.u = db.create_user("pre_l08", auth.hash_password(TEST_PW))
        with db.get_conn() as c:
            c.execute("INSERT INTO subscriptions(user_id,plan,status,started_at,expires_at) "
                      "VALUES(?, 'merchant', 'active',?,?)",
                      (cls.u, NOW - 5 * DAY, NOW + 25 * DAY))
        db.init_db()          # يشغّل _migrate مرة أخرى

    def test_an_existing_row_reads_as_monthly(self):
        self.assertEqual(db.get_subscription(self.u)["billing_cycle"], "monthly")

    def test_a_user_with_no_row_at_all_reads_as_monthly(self):
        ghost = db.create_user("no_sub_row", auth.hash_password(TEST_PW))
        self.assertEqual(db.get_subscription(ghost)["billing_cycle"], "monthly")

    def test_repeated_migrations_do_not_duplicate_the_column(self):
        db.init_db(); db.init_db()
        with db.get_conn() as c:
            cols = [r[1] for r in c.execute("PRAGMA table_info(subscriptions)").fetchall()]
        self.assertEqual(cols.count("billing_cycle"), 1)

    def test_the_column_exists_on_payments_too(self):
        with db.get_conn() as c:
            cols = [r[1] for r in c.execute("PRAGMA table_info(payments)").fetchall()]
        self.assertIn("billing_cycle", cols)


class SubscribePageTests(unittest.TestCase):
    """صفحة الدفع تعرف دورتها من الرابط."""

    @classmethod
    def setUpClass(cls):
        _boot()
        db.create_user("page_viewer", auth.hash_password(TEST_PW))

    def setUp(self):
        web._login_attempts.clear()
        self.c = _client()
        self.c.post("/login", data={"username": "page_viewer", "password": TEST_PW,
                                    "csrf_token": "tk"})

    def test_the_annual_link_renders_the_annual_price(self):
        html = self.c.get("/subscribe/merchant?cycle=annual").get_data(as_text=True)
        self.assertIn(str(plans.annual_price("merchant")), html)

    def test_a_bogus_cycle_in_the_url_renders_monthly(self):
        html = self.c.get("/subscribe/merchant?cycle=free").get_data(as_text=True)
        self.assertNotIn(str(plans.annual_price("merchant")), html)
        self.assertIn("monthly", html)


if __name__ == "__main__":
    unittest.main(verbosity=2)
