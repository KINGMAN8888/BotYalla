"""L-07 — الباقات الجديدة وحماية المشتركين القدامى.

الخطر في هذا البند أنه يمسّ **اشتراكات مدفوعة قائمة**. والقرار المُختبَر هنا:
**لا ترحيل إطلاقاً.** الباقتان القديمتان تبقيان بحدودهما الأصلية خارج قائمة
البيع — لأن `pro` كانت تشمل واتساب و`merchant` لا تشمله، فأي ترحيل يسحب
من مشتركٍ ميزةً دفع مقابلها.

    python tests/test_plans_migration.py
"""
import os, secrets, sys, tempfile, time, unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_TMPDIR = tempfile.mkdtemp(prefix="botyalla-plans-")
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
FUTURE = NOW + 20 * 86400          # اشتراك قائم لم ينتهِ بعد


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


class PlanDefinitionTests(unittest.TestCase):
    """الباقات الأربع وحدودها."""

    def test_the_four_plans_exist_in_order(self):
        # «راحة البال» (vip) أُضيفت بقرار صريح 2026-09-21 — سنوية إلزامياً وتُحجز بمكالمة
        self.assertEqual(plans.ORDER, ["free", "merchant", "whatsapp", "vip", "agency"])

    def test_prices_are_what_the_strategy_specifies(self):
        self.assertEqual([plans.PLANS[p]["price"] for p in plans.ORDER], [0, 299, 899, 1999, 2999])

    def test_whatsapp_is_closed_below_the_whatsapp_plan(self):
        """Meta تحاسب لكل رسالة — واتساب لا يُفتح على مجاني أو تاجر."""
        self.assertFalse(plans.PLANS["free"]["whatsapp"])
        self.assertFalse(plans.PLANS["merchant"]["whatsapp"])
        self.assertTrue(plans.PLANS["whatsapp"]["whatsapp"])
        self.assertTrue(plans.PLANS["agency"]["whatsapp"])

    def test_white_label_belongs_to_the_agency_alone(self):
        self.assertEqual([p for p in plans.ORDER if plans.PLANS[p]["white_label"]], ["agency"])

    def test_every_plan_declares_every_gate_key(self):
        """بوابة ناقصة في باقة = صلاحية تُمنح صامتةً عبر .get() الافتراضي."""
        for pid in plans.ORDER:
            for k in ("ai", "broadcast", "whatsapp", "white_label",
                      "wa_msgs", "media_files", "max_bots", "price"):
                self.assertIn(k, plans.PLANS[pid], f"{pid} ينقصه {k}")

    def test_features_exist_in_both_languages(self):
        for pid in plans.ORDER:
            self.assertTrue(plans.PLANS[pid]["features_ar"])
            self.assertTrue(plans.PLANS[pid]["features_en"])


class AnnualPricingTests(unittest.TestCase):
    """التسعير السنوي — تمهيد L-08، والمبلغ يبقى من الخادم."""

    def test_annual_is_thirty_percent_off_twelve_months(self):
        self.assertEqual(plans.annual_price("merchant"), 2510)   # 299×12×0.7 ≈ 2511 → 2510
        self.assertEqual(plans.annual_price("whatsapp"), 7550)
        self.assertEqual(plans.annual_price("agency"), 25190)

    def test_free_stays_free_on_any_cycle(self):
        self.assertEqual(plans.annual_price("free"), 0)
        self.assertEqual(plans.cycle_price("free", "annual"), 0)

    def test_annual_beats_twelve_monthly_payments(self):
        for pid in ("merchant", "whatsapp", "agency"):
            self.assertLess(plans.annual_price(pid), plans.PLANS[pid]["price"] * 12)

    def test_cycle_days(self):
        self.assertEqual(plans.cycle_days("monthly"), 30)
        self.assertEqual(plans.cycle_days("annual"), 365)


class LegacyPlanTests(unittest.TestCase):
    """الباقات الموروثة: محفوظة بالكامل، وغير قابلة للبيع."""

    def test_legacy_plans_still_exist_with_their_original_limits(self):
        self.assertEqual(plans.PLANS["pro"]["price"], 199)
        self.assertEqual(plans.PLANS["pro"]["max_bots"], 5)
        self.assertEqual(plans.PLANS["business"]["price"], 499)
        self.assertEqual(plans.PLANS["business"]["max_bots"], 9999)

    def test_legacy_pro_keeps_the_whatsapp_it_paid_for(self):
        """جوهر القرار: `pro` كانت تشمل واتساب — ولا تُسحب منها."""
        self.assertTrue(plans.plan("pro")["whatsapp"])
        self.assertEqual(plans.wa_limit("pro"), 1000)
        self.assertTrue(plans.plan("business")["whatsapp"])
        self.assertEqual(plans.wa_limit("business"), 5000)

    def test_legacy_plans_are_marked_and_out_of_the_sale_list(self):
        for pid in ("pro", "business"):
            self.assertTrue(plans.is_legacy(pid))
            self.assertNotIn(pid, plans.ORDER)
            self.assertFalse(plans.is_sellable(pid))

    def test_new_plans_are_not_marked_legacy(self):
        for pid in plans.ORDER:
            self.assertFalse(plans.is_legacy(pid), pid)

    def test_free_is_never_sellable(self):
        self.assertFalse(plans.is_sellable("free"))

    def test_an_unknown_id_falls_back_to_free_not_to_a_paid_plan(self):
        self.assertEqual(plans.plan("nonsense")["price"], 0)
        self.assertFalse(plans.is_sellable("nonsense"))


class ExistingSubscriberTests(unittest.TestCase):
    """مشترك قديم قائم — لا شيء في اشتراكه يتغيّر."""

    @classmethod
    def setUpClass(cls):
        _boot()
        cls.u = db.create_user("legacy_pro", auth.hash_password(TEST_PW))
        with db.get_conn() as c:
            c.execute("INSERT INTO subscriptions(user_id,plan,status,started_at,expires_at) "
                      "VALUES(?, 'pro', 'active',?,?)", (cls.u, NOW - 10 * 86400, FUTURE))
            c.execute("INSERT INTO payments(user_id,plan,method,amount,status,created_at) "
                      "VALUES(?, 'pro', 'instapay',199, 'approved',?)", (cls.u, NOW - 10 * 86400))
        db.init_db()          # يشغّل _migrate — ويجب ألا يمسّ شيئاً

    def _sub(self):
        with db.get_conn() as c:
            return dict(c.execute("SELECT * FROM subscriptions WHERE user_id=?", (self.u,)).fetchone())

    def test_the_plan_id_is_untouched(self):
        self.assertEqual(self._sub()["plan"], "pro")

    def test_dates_and_status_are_untouched(self):
        s = self._sub()
        self.assertEqual(s["expires_at"], FUTURE)
        self.assertEqual(s["started_at"], NOW - 10 * 86400)
        self.assertEqual(s["status"], "active")

    def test_the_paid_amount_is_untouched(self):
        with db.get_conn() as c:
            r = c.execute("SELECT plan, amount FROM payments WHERE user_id=?", (self.u,)).fetchone()
        self.assertEqual((r["plan"], r["amount"]), ("pro", 199))

    def test_he_still_has_every_capability_he_paid_for(self):
        p = plans.plan(db.get_subscription(self.u)["plan"])
        self.assertTrue(p["whatsapp"] and p["ai"] and p["broadcast"])
        self.assertEqual(p["max_bots"], 5)

    def test_repeated_startups_never_touch_his_row(self):
        before = self._sub()
        db.init_db(); db.init_db()
        self.assertEqual(self._sub(), before)


class GateTests(unittest.TestCase):
    """بوابات الصلاحيات على الباقات الأربع عبر الويب."""

    @classmethod
    def setUpClass(cls):
        _boot()
        cls.users = {}
        for pid in plans.ORDER:
            uid_ = db.create_user(f"gate_{pid}", auth.hash_password(TEST_PW))
            db.activate_subscription(uid_, pid, days=30)
            cls.users[pid] = uid_

    def setUp(self):
        web._login_attempts.clear()

    def _login(self, pid):
        c = _client()
        c.post("/login", data={"username": f"gate_{pid}", "password": TEST_PW,
                               "csrf_token": "tk"})
        return c

    def test_broadcast_is_closed_on_free_and_open_above_it(self):
        for pid in plans.ORDER:
            bid = db.create_bot(self.users[pid], f"b_{pid}", f"T:{pid}", "flow",
                                {"business_name": pid, "flow": None, "menu_items": []})
            r = self._login(pid).get(f"/bot/{bid}/broadcast")
            blocked = r.status_code in (302, 303) and "/pricing" in r.headers.get("Location", "")
            self.assertEqual(blocked, pid == "free", f"{pid}: البث تصرّف عكس الباقة")

    def test_bot_limit_matches_the_plan(self):
        for pid in plans.ORDER:
            self.assertEqual(plans.plan(pid)["max_bots"], plans.PLANS[pid]["max_bots"])
        self.assertEqual(plans.plan("free")["max_bots"], 1)
        self.assertEqual(plans.plan("merchant")["max_bots"], 3)

    def test_admin_gets_the_top_plan_not_a_hardcoded_name(self):
        """الأدمن يأخذ أعلى باقة من ORDER — لا اسماً مثبّتاً يصير وسطياً لاحقاً."""
        top = plans.plan(plans.ORDER[-1])
        self.assertTrue(top["white_label"] and top["whatsapp"] and top["ai"])
        self.assertEqual(top["max_bots"], max(plans.PLANS[p]["max_bots"] for p in plans.ORDER))

    def test_pricing_page_lists_the_four_sellable_plans_only(self):
        html = _client().get("/pricing").get_data(as_text=True)
        for pid in plans.ORDER:
            self.assertIn(plans.plan_name(pid, "ar"), html, pid)
        for pid in ("pro", "business"):
            self.assertNotIn(plans.plan_name(pid, "ar"), html, f"{pid} معروضة للبيع!")

    def test_subscribe_refuses_free_and_unknown_plans(self):
        c = self._login("free")
        self.assertIn(c.get("/subscribe/free").status_code, (302, 303))
        self.assertIn(c.get("/subscribe/nonsense").status_code, (302, 303))
        for pid in ("pro", "business"):        # الموروثة لا تُباع لأحد جديد
            self.assertIn(c.get(f"/subscribe/{pid}").status_code, (302, 303), pid)
        self.assertEqual(c.get("/subscribe/merchant").status_code, 200)


if __name__ == "__main__":
    unittest.main(verbosity=2)
