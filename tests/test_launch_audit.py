"""إصلاحات تقرير ما قبل الإطلاق (business/LAUNCH_AUDIT_EN.md) — كل بند باختبار يثبته.

    python tests/test_launch_audit.py
"""
import asyncio, csv, io, json, os, secrets, sys, tempfile, threading, time, unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_TMPDIR = tempfile.mkdtemp(prefix="botyalla-audit-")
os.environ["BOTYALLA_DB"] = os.path.join(_TMPDIR, "test.db")   # قبل استيراد database
os.environ["BOTYALLA_UPLOADS"] = _TMPDIR
os.environ["ADMIN_USER"] = "admin"
os.environ["ADMIN_PASS"] = f"tst_adm_{secrets.token_hex(8)}"

import auth                                # noqa: E402
import database as db                      # noqa: E402
import app as web                          # noqa: E402
import bot_manager                         # noqa: E402
import flow_engine                         # noqa: E402
import payments as pay                     # noqa: E402

PW = "aud_" + secrets.token_hex(6)


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


def _user(name, plan=None):
    u = db.create_user(name, auth.hash_password(PW))
    if plan:
        db.activate_subscription(u, plan, days=30)
    return u


def _as(name):
    c = _client()
    c.post("/login", data={"username": name, "password": PW, "csrf_token": "tk"})
    return c


def _rate_text():
    return web.i18n.t("ai_rate", web.i18n.DEFAULT)


def _flashed(c, text):
    with c.session_transaction() as s:
        return any(text in m for _, m in s.get("_flashes", []))


def _loop_manager():
    """مدير بحلقة asyncio وحدها — بلا خيط التذكيرات ولا بوت المنصة."""
    m = bot_manager.BotManager()
    m._thread = threading.Thread(target=m._run, daemon=True)
    m._thread.start()
    m._ready.wait(5)
    return m


class CampaignTests(unittest.TestCase):
    """C-1: مهلة الحملة كانت تُعلن «فشل الكل» فيُردّ الثمن كاملاً والرسائل تصل فعلاً.
    C-6: الإرسال داخل الطلب يتجاوز مهلة nginx فتُضغط «إرسال» ثانيةً — خصم مزدوج."""

    @classmethod
    def setUpClass(cls):
        _boot()
        cls.m = _loop_manager()
        cls.u = _user("aud_camp", "whatsapp")
        cls.bid = db.create_bot(cls.u, "WA", "wa:aud", "flow",
                                {"business_name": "WA", "wa_token": "t"}, channel="whatsapp")
        for i in range(5):
            db.add_bot_user(cls.bid, 7100 + i, f"p{i}", peer=f"wa:2013000000{i:02d}")
        cls._orig = web.manager.broadcast_direct

    @classmethod
    def tearDownClass(cls):
        web.manager.broadcast_direct = cls._orig

    def setUp(self):
        web._login_attempts.clear()

    def test_a_timeout_charges_what_was_delivered_and_stops_sending(self):
        async def slow(prog):
            for _ in range(40):
                if prog["stop"]:
                    return
                await asyncio.sleep(0.05)
                prog["sent"] += 1
        prog = self.m._progress(None, 40)
        sent, not_sent = self.m._run_counted(slow(prog), prog, 40, 0.3, "test")
        self.assertTrue(0 < sent < 40, sent)        # قبلها: (0, 40) = ردّ كامل رغم الوصول
        self.assertEqual(sent + not_sent, 40)
        time.sleep(0.3)
        self.assertEqual(prog["sent"], sent, "الإرسال توقف فعلاً عند المهلة")

    def test_one_campaign_per_bot(self):
        gate = threading.Event()
        self.assertTrue(self.m.start_campaign(1, lambda st: gate.wait(5) and {"sent": 1}))
        self.assertFalse(self.m.start_campaign(1, lambda st: {"sent": 1}), "حملة ثانية وهي تعمل")
        gate.set()
        self.m.join_campaigns()
        self.assertEqual(self.m.campaign_status(1)["state"], "done")
        self.assertTrue(self.m.start_campaign(1, lambda st: {"sent": 1}), "بعد انتهائها تُقبل")
        self.m.join_campaigns()

    def test_a_second_send_while_one_is_running_charges_nothing(self):
        gate = threading.Event()

        def fake(bot_id, text, category="utility", peers=None, prog=None):
            gate.wait(5)
            return len(peers), 0
        web.manager.broadcast_direct = fake
        db.wallet_topup(self.u, 100000)
        start = db.wallet_balance(self.u)
        c = _as("aud_camp")
        form = {"mode": "direct_send", "text": "طلبك جاهز", "csrf_token": "tk"}
        c.post(f"/bot/{self.bid}/broadcast", data=form)      # يرجع فوراً والإرسال في الخلفية
        c.post(f"/bot/{self.bid}/broadcast", data=form)      # الضغطة الثانية
        self.assertTrue(_flashed(c, web._CAMPAIGN_BUSY[0]))
        gate.set()
        web.manager.join_campaigns()
        self.assertEqual(start - db.wallet_balance(self.u), 5 * web.mkt_price(), "خصم واحد لا اثنان")


class AIReplyRefundTests(unittest.TestCase):
    """C-5: ثمن رد الذكاء الاصطناعي كان يُخصم ولا يُردّ لو لم يصل الرد."""

    @classmethod
    def setUpClass(cls):
        _boot()
        cls.u = _user("aud_ai", "merchant")

    def test_a_paid_reservation_is_returned_in_full(self):
        db.wallet_topup(self.u, 1000)
        before, used = db.wallet_balance(self.u), db.ai_usage_of(self.u)["replies"]
        grant = db.ai_reply_allow(self.u, 0, 50, ref="ai:test")      # الحصة صفر ← من المحفظة
        self.assertEqual(grant, "paid")
        self.assertEqual(db.wallet_balance(self.u), before - 50)
        db.ai_reply_release(self.u, grant, 50, ref="ai:test")
        self.assertEqual(db.wallet_balance(self.u), before)
        self.assertEqual(db.ai_usage_of(self.u)["replies"], used)

    def test_an_undelivered_whatsapp_reply_is_not_counted(self):
        bid = db.create_bot(self.u, "AI", "wa:ai-aud", "flow",
                            {"business_name": "AI", "wa_token": "t"}, channel="whatsapp")
        row = db.get_bot(bid)
        import ai_agent
        orig = ai_agent.brain_reply
        ai_agent.brain_reply = lambda *a, **k: {"reply": "أهلاً بيك"}
        db.set_platform("ai_key", "test-key")

        class ClosedWindow:            # قناة واتساب ترجّع None حين تُرفض الرسالة
            phone_id = "1"

            async def send_text(self, peer, text):
                return None

            async def send_typing(self, peer):
                return None
        try:
            used = db.ai_usage_of(self.u)["replies"]
            ok = asyncio.run(flow_engine._ai_answer(row, {}, ClosedWindow(), "wa:201", "سلام"))
        finally:
            ai_agent.brain_reply = orig
            db.set_platform("ai_key", "")
        self.assertFalse(ok)
        self.assertEqual(db.ai_usage_of(self.u)["replies"], used, "رد لم يصل لا يُحتسب")


class ExpensiveRouteTests(unittest.TestCase):
    """C-2/C-3/C-4: المسارات الغالية (OCR · شبكة تليجرام · مفتاح AI) كانت بلا حد."""

    @classmethod
    def setUpClass(cls):
        _boot()
        cls.u = _user("aud_rate", "merchant")

    def setUp(self):
        web._login_attempts.clear()

    def test_receipt_uploads_are_rate_limited(self):
        c = _as("aud_rate")
        for _ in range(8):
            c.post("/wallet/topup", data={"amount": "0", "csrf_token": "tk"})
        with c.session_transaction() as s:
            s.pop("_flashes", None)
        c.post("/wallet/topup", data={"amount": "0", "csrf_token": "tk"})
        self.assertTrue(_flashed(c, _rate_text()))

    def test_token_checks_are_rate_limited(self):
        orig = web.tg.validate_token
        web.tg.validate_token = lambda t: {"ok": False, "error": "bad token"}
        try:
            c = _as("aud_rate")
            answers = [c.post("/api/validate-token", json={"token": "x"},
                              headers={"X-CSRF-Token": "tk"}).get_json() for _ in range(31)]
        finally:
            web.tg.validate_token = orig
        self.assertEqual(answers[0]["error"], "bad token")
        self.assertEqual(answers[-1]["error"], _rate_text())

    def test_the_unmetered_ai_route_is_gone(self):
        bid = db.create_bot(self.u, "B", "T:aud-rate", "flow", {"business_name": "B"})
        r = _as("aud_rate").post(f"/bot/{bid}/ai-setup", json={"description": "مطعم"},
                                 headers={"X-CSRF-Token": "tk"})
        self.assertIn(r.status_code, (404, 405))

    def test_ocr_never_takes_every_thread(self):
        """قراءتان متزامنتان على الأكثر — الثالثة تذهب للمراجعة اليدوية بدل أن تنتظر."""
        orig, wait = pay.ocr_status, pay.OCR_WAIT
        pay.ocr_status = lambda refresh=False: {"ok": True, "reason": None, "langs": "eng"}
        pay.OCR_WAIT = 0.1
        took = [pay._OCR_SLOTS.acquire(timeout=1), pay._OCR_SLOTS.acquire(timeout=1)]
        try:
            self.assertTrue(all(took))
            t0 = time.time()
            self.assertIsNone(pay.read_text(b"x"))
            self.assertLess(time.time() - t0, 2)
        finally:
            for ok in took:
                if ok:
                    pay._OCR_SLOTS.release()
            pay.ocr_status, pay.OCR_WAIT = orig, wait


class ExportTests(unittest.TestCase):
    """I-3: خلية تبدأ بـ = تُنفَّذ صيغةً في Excel. I-4: التصدير كان يقف عند 300 صف بصمت."""

    @classmethod
    def setUpClass(cls):
        _boot()
        cls.u = _user("aud_csv", "merchant")
        cls.bid = db.create_bot(cls.u, "S", "T:aud-csv", "store", {"business_name": "S"})
        now = int(time.time())
        rows = [(cls.bid, 1, f"c{i}", "0100", "addr", "[]", 10, now - i) for i in range(305)]
        rows.append((cls.bid, 1, '=HYPERLINK("http://evil.example","x")', "+201001", "a", "[]", 5,
                     now + 10))
        with db.get_conn() as c:
            c.executemany("INSERT INTO orders(bot_id,tg_user_id,customer,phone,address,items_json,"
                          "total,created_at) VALUES(?,?,?,?,?,?,?,?)", rows)

    def setUp(self):
        web._login_attempts.clear()

    def _rows(self):
        r = _as("aud_csv").get(f"/bot/{self.bid}/export/orders")
        self.assertEqual(r.status_code, 200)
        return list(csv.reader(io.StringIO(r.get_data(as_text=True).lstrip("﻿"))))

    def test_export_is_not_truncated_at_300(self):
        self.assertEqual(len(self._rows()) - 1, 306)

    def test_formula_cells_are_neutralised(self):
        rows = self._rows()
        evil = rows[1]                                     # الأحدث أولاً
        self.assertTrue(evil[0].startswith("'="), evil[0])
        self.assertEqual(evil[1], "'+201001")
        tot = rows[0].index("الإجمالي")            # موضع العمود من الترويسة لا برقم ثابت
        self.assertFalse(rows[2][tot].startswith("'"), "الأرقام تبقى أرقاماً")
        self.assertEqual(float(rows[2][tot]), 10)
        self.assertEqual(len(db.list_orders(self.bid)), 300, "اللوحة ما زالت تكتفي بـ 300")


class SiteTests(unittest.TestCase):
    """I-6 · robots/sitemap · www مقابل الدومين المجرّد."""

    @classmethod
    def setUpClass(cls):
        _boot()
        _user("aud_site")

    def setUp(self):
        web._login_attempts.clear()

    def test_logout_is_post_only(self):
        c = _as("aud_site")
        self.assertEqual(c.get("/logout").status_code, 405)
        with c.session_transaction() as s:
            self.assertIn("uid", s, "GET لا يُخرج أحداً")
        self.assertEqual(c.post("/logout", data={"csrf_token": "tk"}).status_code, 302)
        with c.session_transaction() as s:
            self.assertNotIn("uid", s)

    def test_pricing_is_crawlable(self):
        c = _client()
        self.assertNotIn("Disallow: /pricing", c.get("/robots.txt").get_data(as_text=True))
        self.assertIn("/pricing</loc>", c.get("/sitemap.xml").get_data(as_text=True))

    def test_www_redirects_to_the_canonical_host(self):
        old = os.environ.get("PUBLIC_URL")
        os.environ["PUBLIC_URL"] = "https://botyalla.com"
        try:
            c = _client()
            r = c.get("/pricing?ref=A1", base_url="https://www.botyalla.com")
            self.assertEqual(r.status_code, 301)
            self.assertEqual(r.headers["Location"], "https://botyalla.com/pricing?ref=A1")
            self.assertNotEqual(c.get("/pricing", base_url="https://botyalla.com").status_code, 301)
            self.assertNotEqual(c.get("/wh/whatsapp", base_url="https://www.botyalla.com").status_code,
                                301, "Meta تتحقق من عنوان الويبهوك كما سُجّل")
            self.assertNotEqual(c.get("/pricing", base_url="http://localhost").status_code, 301)
        finally:
            if old is None:
                os.environ.pop("PUBLIC_URL", None)
            else:
                os.environ["PUBLIC_URL"] = old


class DataTests(unittest.TestCase):
    """I-1: الجداول الساخنة بلا فهارس. I-2: أحداث التحليلات لا تُنظَّف أبداً."""

    @classmethod
    def setUpClass(cls):
        _boot()
        cls.u = _user("aud_data")
        cls.bid = db.create_bot(cls.u, "D", "T:aud-data", "flow", {"business_name": "D"})

    def test_hot_tables_are_indexed(self):
        with db.get_conn() as c:
            names = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='index'")}
            plan = " ".join(str(tuple(r)) for r in c.execute(
                "EXPLAIN QUERY PLAN SELECT * FROM orders WHERE bot_id=? ORDER BY created_at DESC", (1,)))
        for ix in ("ix_events_bot_day", "ix_events_created", "ix_leads_bot", "ix_orders_bot",
                   "ix_payments_user", "ix_payments_status", "ix_payments_img", "ix_bots_owner"):
            self.assertIn(ix, names)
        self.assertIn("ix_orders_bot", plan, "طلبات البوت كانت مسحاً كاملاً")

    def test_old_events_are_purged_and_recent_ones_kept(self):
        old = int(time.time()) - 400 * 86400
        with db.get_conn() as c:
            c.execute("INSERT INTO events(bot_id,kind,value,day,created_at) VALUES(?,?,?,?,?)",
                      (self.bid, "start", 0, "2020-01-01", old))
        db.log_event(self.bid, "start")
        self.assertGreaterEqual(db.purge_old_events(), 1)
        with db.get_conn() as c:
            left = c.execute("SELECT COUNT(*) FROM events WHERE bot_id=?", (self.bid,)).fetchone()[0]
        self.assertEqual(left, 1)
        self.assertEqual(sum(db.stats_daily(self.bid)["starts"]), 1)


class BookingConfigTests(unittest.TestCase):
    """I-5: قيمة غير رقمية في working_days كانت ترمي ValueError فيسقط الحفظ بـ 500."""

    @classmethod
    def setUpClass(cls):
        _boot()
        cls.u = _user("aud_book", "merchant")
        cls.bid = db.create_bot(cls.u, "Bk", "T:aud-book", "booking", {"business_name": "Bk"})

    def setUp(self):
        web._login_attempts.clear()

    def test_bad_working_days_are_ignored_not_crashed(self):
        r = _as("aud_book").post(f"/bot/{self.bid}/config", data={
            "working_days": ["x", "1", "9", "3"], "csrf_token": "tk"})
        self.assertLess(r.status_code, 500)
        cfg = json.loads(db.get_bot(self.bid)["config_json"])
        self.assertEqual(cfg["working_days"], [1, 3])


if __name__ == "__main__":
    unittest.main(verbosity=2)
