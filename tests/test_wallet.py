"""L-16 — محفظة الرسائل التسويقية.

القاعدة التي تُختبَر هنا: **لا رصيد سالب، ولا حملة تسويقية بلا رصيد، ولا
محاسبة على ما لم يصل.** والوحدة قرش صحيح لا جنيه عائم — فحساب 3.28 × 1000
بالعائم يعطي 3279.9999999999995، وهذا لا يُقبل في المال.

    python tests/test_wallet.py
"""
import io, json, os, secrets, sys, tempfile, threading, unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_TMPDIR = tempfile.mkdtemp(prefix="botyalla-wallet-")
os.environ["BOTYALLA_DB"] = os.path.join(_TMPDIR, "test.db")   # قبل استيراد database
os.environ["BOTYALLA_UPLOADS"] = _TMPDIR
ADMIN_PW = os.environ.setdefault("ADMIN_PASS", f"tst_adm_{secrets.token_hex(8)}")
PW = f"tst_wal_{secrets.token_hex(8)}"
os.environ["ADMIN_USER"] = "admin"
os.environ["ADMIN_PASS"] = ADMIN_PW

import auth                                # noqa: E402
import database as db                      # noqa: E402
import app as web                          # noqa: E402

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


class LedgerTests(unittest.TestCase):
    """الرصيد والسجل — الطبقة التي لا يجوز أن تخطئ."""

    @classmethod
    def setUpClass(cls):
        _boot()

    def _user(self, name):
        return db.create_user(name, auth.hash_password(PW))

    def test_a_new_account_starts_at_zero_without_a_row(self):
        self.assertEqual(db.wallet_balance(self._user("w_new")), 0)

    def test_topup_then_charge_moves_the_balance_exactly(self):
        u = self._user("w_move")
        self.assertEqual(db.wallet_topup(u, 50000), 50000)      # 500ج
        self.assertEqual(db.wallet_charge(u, 31200), 18800)     # 100 رسالة
        self.assertEqual(db.wallet_balance(u), 18800)

    def test_a_charge_larger_than_the_balance_changes_nothing(self):
        u = self._user("w_short")
        db.wallet_topup(u, 1000)
        self.assertIsNone(db.wallet_charge(u, 1001))
        self.assertEqual(db.wallet_balance(u), 1000)
        # ولا يُكتب قيد لمحاولة فاشلة
        self.assertEqual([x["kind"] for x in db.wallet_ledger(u)], ["topup"])

    def test_the_balance_can_never_go_negative(self):
        u = self._user("w_neg")
        db.wallet_topup(u, 500)
        for _ in range(5):
            db.wallet_charge(u, 200)
        self.assertGreaterEqual(db.wallet_balance(u), 0)
        self.assertEqual(db.wallet_balance(u), 100)

    def test_zero_and_negative_amounts_are_refused(self):
        u = self._user("w_zero")
        for bad in (0, -1, None, ""):
            self.assertIsNone(db.wallet_topup(u, bad), repr(bad))
            self.assertIsNone(db.wallet_charge(u, bad), repr(bad))
        self.assertEqual(db.wallet_balance(u), 0)

    def test_every_move_is_written_to_the_ledger_with_the_running_balance(self):
        u = self._user("w_led")
        db.wallet_topup(u, 10000)
        db.wallet_charge(u, 3000)
        db.wallet_refund(u, 1000)
        rows = list(reversed(db.wallet_ledger(u)))
        self.assertEqual([r["kind"] for r in rows], ["topup", "spend", "refund"])
        self.assertEqual([r["delta"] for r in rows], [10000, -3000, 1000])
        self.assertEqual([r["balance_after"] for r in rows], [10000, 7000, 8000])

    def test_the_ledger_always_sums_to_the_balance(self):
        """الرصيد عمود مُخزَّن — وهذا ما يضمن أنه ليس كذبة."""
        u = self._user("w_sum")
        db.wallet_topup(u, 7777)
        db.wallet_charge(u, 1234)
        db.wallet_refund(u, 12)
        db.wallet_adjust(u, -500, note="تصحيح")
        self.assertEqual(sum(r["delta"] for r in db.wallet_ledger(u, 999)),
                         db.wallet_balance(u))

    def test_two_simultaneous_campaigns_cannot_both_spend_the_same_credit(self):
        """الخصم المشروط هو القفل: رصيد يكفي واحدة لا يمرّر اثنتين."""
        u = self._user("w_race")
        db.wallet_topup(u, 1000)
        results = []
        lock = threading.Lock()

        def spend():
            r = db.wallet_charge(u, 700)
            with lock:
                results.append(r)

        ts = [threading.Thread(target=spend) for _ in range(2)]
        [t.start() for t in ts]
        [t.join() for t in ts]
        self.assertEqual(sum(1 for r in results if r is not None), 1, results)
        self.assertEqual(db.wallet_balance(u), 300)


class QuoteTests(unittest.TestCase):
    """تسعير الحملة — تليجرام مجاني وغير التسويقي مجاني."""

    @classmethod
    def setUpClass(cls):
        _boot()
        cls.u = db.create_user("w_quote", auth.hash_password(PW))
        db.wallet_topup(cls.u, 100000)                 # 1000ج

    def test_marketing_costs_price_times_recipients(self):
        q = web._campaign_quote(self.u, 100, "MARKETING")
        self.assertTrue(q["billable"])
        self.assertEqual(q["cost"], 100 * web.mkt_price())
        self.assertTrue(q["enough"])

    def test_utility_and_authentication_are_never_charged(self):
        for cat in ("UTILITY", "AUTHENTICATION", None, "", "marketing"):
            q = web._campaign_quote(self.u, 1000, cat)
            self.assertFalse(q["billable"], repr(cat))
            self.assertEqual(q["cost"], 0)
            self.assertTrue(q["enough"])

    def test_an_unaffordable_campaign_reports_exactly_what_is_missing(self):
        q = web._campaign_quote(self.u, 10000, "MARKETING")
        self.assertFalse(q["enough"])
        self.assertEqual(q["short"], q["cost"] - q["balance"])
        self.assertGreater(q["short"], 0)

    def test_the_price_comes_from_platform_settings_not_a_constant(self):
        db.set_platform("mkt_msg_price", "500")
        try:
            self.assertEqual(web.mkt_price(), 500)
            self.assertEqual(web._campaign_quote(self.u, 10, "MARKETING")["cost"], 5000)
        finally:
            db.set_platform("mkt_msg_price", "328")

    def test_a_broken_price_setting_falls_back_instead_of_charging_zero(self):
        """سعر صفر يعني حملات مجانية بلا حدّ — أخطر من سعر خاطئ."""
        for bad in ("", "abc", "0", "-5", None):
            db.set_platform("mkt_msg_price", bad if bad is not None else "")
            self.assertEqual(web.mkt_price(), web.MKT_PRICE_FALLBACK, repr(bad))
        db.set_platform("mkt_msg_price", "328")

    def test_money_stays_in_integer_piastres(self):
        """3.28 × 1000 بالعائم = 3279.9999999999995. بالقروش = 328000 بالضبط."""
        db.set_platform("mkt_msg_price", "328")
        q = web._campaign_quote(self.u, 1000, "MARKETING")
        self.assertIsInstance(q["cost"], int)
        self.assertEqual(q["cost"], 328000)
        self.assertEqual(web._egp(328000), 3280.0)


class TopupFlowTests(unittest.TestCase):
    """الشحن يمرّ بنفس مسار الموافقة — ولا يُضاف رصيد قبلها."""

    @classmethod
    def setUpClass(cls):
        _boot()
        cls.u = db.create_user("w_top", auth.hash_password(PW))

    def setUp(self):
        web._login_attempts.clear()
        self.c = _client()
        self.c.post("/login", data={"username": "w_top", "password": PW, "csrf_token": "tk"})

    def _request(self, amount):
        self.c.post("/wallet/topup",
                    data={"amount": str(amount), "method": "instapay", "ref": "R",
                          "screenshot": (io.BytesIO(PNG), "p.png"), "csrf_token": "tk"},
                    content_type="multipart/form-data", follow_redirects=True)
        pays = db.list_payments(self.u)
        return pays[0] if pays else None

    def test_a_request_creates_a_pending_payment_and_no_credit_yet(self):
        before = db.wallet_balance(self.u)
        p = self._request(250)
        self.assertEqual(p["plan"], db.WALLET_PLAN)
        self.assertEqual(p["status"], "pending")
        self.assertEqual(p["amount"], 250.0)
        self.assertEqual(db.wallet_balance(self.u), before, "شُحن الرصيد قبل الموافقة!")

    def test_approval_credits_the_wallet_in_piastres(self):
        p = self._request(250)
        before = db.wallet_balance(self.u)
        row = db.finalize_payment(p["id"], "approved")
        self.assertEqual(db.wallet_balance(self.u), before + 25000)
        self.assertEqual(row["wallet_after"], before + 25000)

    def test_rejection_credits_nothing(self):
        p = self._request(300)
        before = db.wallet_balance(self.u)
        db.finalize_payment(p["id"], "rejected")
        self.assertEqual(db.wallet_balance(self.u), before)

    def test_a_topup_cannot_be_approved_twice(self):
        p = self._request(100)
        db.finalize_payment(p["id"], "approved")
        after = db.wallet_balance(self.u)
        self.assertIsNone(db.finalize_payment(p["id"], "approved"))
        self.assertEqual(db.wallet_balance(self.u), after)

    def test_amounts_outside_the_range_are_refused(self):
        n = len(db.list_payments(self.u))
        for bad in (0, 1, 49, 50001, -100, "abc"):
            self.c.post("/wallet/topup",
                        data={"amount": str(bad), "method": "instapay",
                              "screenshot": (io.BytesIO(PNG), "p.png"), "csrf_token": "tk"},
                        content_type="multipart/form-data", follow_redirects=True)
        self.assertEqual(len(db.list_payments(self.u)), n, "أُنشئ طلب بمبلغ خارج الحدود")

    def test_a_topup_is_not_a_plan_and_cannot_be_bought_as_one(self):
        """`__wallet__` يجب ألا يصير باقة قابلة للشراء بأي مسار."""
        import plans
        self.assertFalse(plans.is_sellable(db.WALLET_PLAN))
        self.assertNotIn(db.WALLET_PLAN, plans.PLANS)
        self.assertIn(self.c.get(f"/subscribe/{db.WALLET_PLAN}").status_code, (302, 303, 404))

    def test_a_topup_never_activates_a_subscription(self):
        p = self._request(500)
        db.finalize_payment(p["id"], "approved")
        self.assertEqual(db.get_subscription(self.u)["plan"], "free")

    def test_the_receipt_does_not_call_a_topup_a_free_plan(self):
        import mailer
        p = self._request(200)
        row = db.finalize_payment(p["id"], "approved")
        subject, html, text = mailer.receipt_email(row, "approved", "ar")
        self.assertNotIn("مجانية", html)
        self.assertIn("رصيد", html)


class WalletPageTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        _boot()
        cls.u = db.create_user("w_page", auth.hash_password(PW))
        db.wallet_topup(cls.u, 12345)

    def setUp(self):
        web._login_attempts.clear()
        self.c = _client()
        self.c.post("/login", data={"username": "w_page", "password": PW, "csrf_token": "tk"})

    def test_the_page_shows_the_balance_and_the_price(self):
        html = self.c.get("/wallet").get_data(as_text=True)
        self.assertIn("12345", html)
        self.assertIn(str(web.mkt_price()), html)

    def test_the_wallet_is_private_to_its_owner(self):
        other = _client()
        self.assertIn(other.get("/wallet").status_code, (302, 303))

    def test_the_strings_exist_in_both_languages(self):
        import i18n
        for k in ("wallet_title", "wallet_balance", "camp_cost_title", "camp_short",
                  "wallet_topup_label"):
            for lang in ("ar", "en"):
                self.assertNotEqual(i18n.t(k, lang), k, f"{k}/{lang}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
