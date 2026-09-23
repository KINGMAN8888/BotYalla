"""التقرير الأسبوعي · تحليل المحادثات · سحب السجل.

    python tests/test_reports.py
"""
import json, os, secrets, sys, tempfile, time, unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_TMPDIR = tempfile.mkdtemp(prefix="botyalla-reports-")
os.environ["BOTYALLA_DB"] = os.path.join(_TMPDIR, "test.db")   # قبل استيراد database
os.environ["BOTYALLA_UPLOADS"] = _TMPDIR
os.environ["BOTYALLA_LOGS"] = os.path.join(_TMPDIR, "logs")    # لا يُكتب في logs/ الحقيقي
PW = "rp_" + secrets.token_hex(6)
os.environ["ADMIN_USER"] = "admin"
os.environ["ADMIN_PASS"] = PW

import database as db                      # noqa: E402
import app as web                          # noqa: E402
import weekly_report as WR                 # noqa: E402
import conv_insights as CI                 # noqa: E402
import log_scan as LS                      # noqa: E402
import mailer                              # noqa: E402
from _signup import signup, STRONG_PW      # noqa: E402

DAY = 86400


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


def _login_admin():
    c = _client()
    c.post("/login", data={"username": "admin", "password": PW, "csrf_token": "tk"},
           follow_redirects=True)
    return c


def _seed():
    """منصة صغيرة لكنها كاملة: مالك متجر نشط، وتاجر توقّف، ومسجّل بلا بوت."""
    now = int(time.time())
    with db.get_conn() as c:
        for name, ago, ver in (("shop", 3 * DAY, now), ("stalled", 2 * DAY, now),
                               ("ghost", DAY, None)):
            c.execute("INSERT INTO users(username,pw_hash,role,created_at,email,"
                      "verify_required,email_verified_at) VALUES(?,'x','user',?,?,1,?)",
                      (name, now - ago, f"{name}@example.com", ver))
    shop = db.get_user_by_name("shop")["id"]
    stalled = db.get_user_by_name("stalled")["id"]

    live = db.create_bot(shop, "كوكي اون لاين", "T:live", "store", {"business_name": "كوكي"})
    db.set_bot_active(live, 1)
    silent = db.create_bot(shop, "بوت صامت", "T:silent", "flow", {})
    db.set_bot_active(silent, 1)
    db.create_bot(stalled, "بوت ما اشتغلش", "T:off", "store", {})     # لم يُشغَّل أبداً

    for i, peer in enumerate(("tg:101", "tg:102", "tg:103")):
        db.add_bot_user(live, 100 + i, "عميل", peer=peer)
        db.log_message(live, peer, "in", "customer", "السلام عليكم الفستان ده بكام؟")
        db.log_message(live, peer, "out", "bot", "أهلاً! السعر 250 جنيه.")
        db.log_message(live, peer, "in", "customer", "والشحن لاسكندرية بكام؟")   # بلا ردّ
    db.log_message(live, "tg:101", "in", "customer", "طلبي وصل فين؟ تأخير وحش والله")
    db.log_message(live, "tg:101", "out", "human", "آسفين، هيوصل النهاردة.")
    db.add_order(live, 101, "منى", "01000000000", "اسكندرية",
                 [{"name": "فستان", "price": 250, "qty": 1}], 320, shipping=70,
                 ship_zone="الإسكندرية")
    db.add_lead(live, 102, {"الاسم": "سارة"})

    pid = db.create_payment(shop, "merchant", "vodafone", 199, "R1", None, None, "{}")
    db.decide_payment(pid, "approved")
    db.create_payment(stalled, "merchant", "vodafone", 199, "R2", None, None, "{}")
    db.log_receipt_refusal(stalled, "not_receipt")
    db.create_ticket(stalled, "support", "الإيصال مترفض", "ساعدوني")
    db.activate_subscription(shop, "merchant", days=5)
    return {"shop": shop, "stalled": stalled, "live": live, "silent": silent}


# التهيئة مرة واحدة عند الاستيراد: unittest يرتّب الأصناف أبجدياً، فلو زُرعت
# البيانات في `setUpClass` لصنف متأخر وجدت الأصناف قبله قاعدة فارغة.
_boot()
IDS = _seed()
# لقطة واحدة من التقرير يقرأها كل من يتحقق من أرقامه: أصناف أخرى تسجّل حسابات
# وتنشئ بوتات، وunittest لا يضمن ترتيبها.
REPORT = WR.build(days=7)


class WindowTests(unittest.TestCase):
    """أرقام الفترة: كل رقم يقيس ما يقوله اسمه بالضبط."""

    @classmethod
    def setUpClass(cls):
        cls.ids, cls.rep = IDS, REPORT

    def test_period_includes_the_current_second(self):
        """النافذة `[a, b)` لا يجوز أن تسقط ما وقع الآن — وإلا كان كل تقرير متأخراً ثانية."""
        a, b = WR.period(7)
        self.assertLessEqual(a, int(time.time()))
        self.assertGreater(b, int(time.time()))
        self.assertEqual(WR.label(a, b).count("→"), 1)

    def test_signups_and_stuck_verification(self):
        n = self.rep["now"]
        self.assertEqual(n["signups"], 3)
        self.assertEqual(n["signups_verified"], 2)
        self.assertEqual(n["signups_stuck_verify"], 1)      # ghost لم يؤكّد بريده
        self.assertEqual(n["signups_no_bot"], 1)            # ghost بلا بوت

    def test_created_but_never_used(self):
        """السؤال الذي بُني له التقرير: من أنشأ بوتاً ولم يستعمله."""
        n = self.rep["now"]
        self.assertEqual(n["bots_new"], 3)
        self.assertEqual(n["bots_never_started"], 1)        # بوت ما اشتغلش
        self.assertEqual(n["bots_started_silent"], 1)       # بوت صامت (شغّال بلا رسالة)
        self.assertEqual(n["silent_active_bots"], 1)

    def test_messages_and_results(self):
        n = self.rep["now"]
        self.assertEqual(n["msgs_in"], 7)
        self.assertEqual(n["msgs_out"], 4)
        self.assertEqual(n["customers_active"], 3)
        self.assertEqual(n["customers_new"], 3)
        self.assertEqual(n["orders"], 1)
        self.assertEqual(n["orders_value"], 320.0)
        self.assertEqual(n["leads"], 1)

    def test_money_and_support(self):
        n = self.rep["now"]
        self.assertEqual(n["revenue"], 199.0)
        self.assertEqual(n["pay_approved"], 1)
        self.assertEqual(n["pay_pending"], 1)
        self.assertEqual(n["refusals"], 1)
        self.assertEqual(n["refusals_by_reason"][0]["k"], "not_receipt")
        self.assertEqual(n["tickets_new"], 1)
        self.assertEqual(n["tickets_unanswered"], 1)

    def test_previous_window_is_equal_and_empty(self):
        """المقارنة لا تصحّ إلا بنافذتين متساويتين — والسابقة هنا فارغة فالتغيّر «جديد»."""
        p = self.rep["period"]
        self.assertEqual(self.rep["prev"]["signups"], 0)
        self.assertIsNone(self.rep["delta"]["signups"]["change"])
        self.assertEqual(self.rep["delta"]["signups"]["now"], 3)
        self.assertEqual(p["days"], 7)

    def test_daily_series_covers_every_day(self):
        self.assertEqual(len(self.rep["daily"]), 7)
        self.assertEqual(sum(d["msgs_in"] for d in self.rep["daily"]), 7)

    def test_per_bot_rows(self):
        rows = {b["name"]: b for b in self.rep["bots"]}
        self.assertEqual(rows["كوكي اون لاين"]["msgs_in"], 7)
        self.assertEqual(rows["كوكي اون لاين"]["customers"], 3)
        self.assertEqual(rows["كوكي اون لاين"]["orders"], 1)
        self.assertEqual(rows["كوكي اون لاين"]["human_replies"], 1)
        self.assertEqual(rows["بوت صامت"]["msgs_in"], 0)
        self.assertEqual(rows["كوكي اون لاين"]["owner"], "shop")

    def test_problem_users_carry_their_reasons(self):
        by = {u["username"]: u["problems"] for u in self.rep["problems"]}
        self.assertIn("receipt_refused", by["stalled"])
        self.assertIn("ticket_open", by["stalled"])
        self.assertIn("bot_never_started", by["stalled"])
        self.assertIn("verify_stuck", by["ghost"])
        self.assertIn("no_bot", by["ghost"])
        # صاحب المتجر الناجح يظهر بسبب واحد لا غير: بوته الثاني لم تصله رسالة
        self.assertEqual(list(by["shop"]), ["bot_silent"])
        for kind in (k for u in self.rep["problems"] for k in u["problems"]):
            self.assertIn(kind, db.PROBLEM_KINDS)   # لا رمز بلا ترجمة في الواجهة

    def test_findings_are_actionable_and_ranked(self):
        keys = [f["key"] for f in self.rep["findings"]]
        self.assertIn("tickets_unanswered", keys)
        self.assertIn("bots_never_started", keys)
        self.assertIn("bots_started_silent", keys)
        self.assertIn("verify_stuck", keys)
        levels = [f["level"] for f in self.rep["findings"]]
        self.assertEqual(levels, sorted(levels, key={"risk": 0, "warn": 1, "good": 2,
                                                     "info": 3}.get))
        for f in self.rep["findings"]:
            self.assertTrue(f["title"] and f["action"], f)

    def test_expiring_subscriptions_and_renewal_value(self):
        self.assertEqual([x["username"] for x in self.rep["expiring"]], ["shop"])
        self.assertGreater(self.rep["renewal_value"], 0)

    def test_english_report_is_english(self):
        rep = WR.build(days=7, lang="en")
        self.assertTrue(any("signups" in s.lower() for s in rep["summary"]))


class TrendTests(unittest.TestCase):
    """التنبؤ: خطّ اتجاه معلن الثقة — لا رقم مخترع عند قلّة البيانات."""

    def test_rising_series(self):
        t = WR.trend([1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14])
        self.assertAlmostEqual(t["slope"], 1.0, places=2)
        self.assertEqual(t["confidence"], "high")

    def test_flat_and_empty_series(self):
        self.assertEqual(WR.trend([0, 0, 0])["confidence"], "none")
        self.assertEqual(WR.trend([])["confidence"], "none")
        self.assertEqual(WR.trend([2])["confidence"], "none")

    def test_forecast_never_negative(self):
        series = [{"signups": v} for v in (9, 7, 5, 3, 1, 0, 0)]
        f = WR.forecast(series, 7, keys=("signups",))["signups"]
        self.assertGreaterEqual(f["expected"], 0)
        self.assertEqual(f["last_period"], 25)


class LogScanTests(unittest.TestCase):
    """السجل: التجميع بالتوقيع، والحجب قبل أي تخزين."""

    SAMPLE = (
        "2026-09-22 10:00:01,100 INFO botyalla: mail sent: welcome -> ab***@x.com\n"
        "2026-09-22 10:00:02,100 ERROR flask.app: Exception on /bot/12/pay [POST]\n"
        "Traceback (most recent call last):\n"
        '  File "app.py", line 1, in x\n'
        "ValueError: bad thing 42\n"
        "2026-09-22 10:05:02,100 ERROR flask.app: Exception on /bot/99/pay [POST]\n"
        "ValueError: bad thing 77\n"
        "2026-09-22 11:00:00,000 WARNING bot_manager: bot start refused — at capacity: 120/120\n"
        "2026-09-22 11:30:00,000 ERROR mailer: mail failed: reset -> ab***@x.com: timeout\n")

    def test_parse_attaches_traceback_to_its_line(self):
        recs = LS.parse(self.SAMPLE)
        self.assertEqual(len(recs), 5)                     # الأثر ليس سطراً مستقلاً
        self.assertEqual(recs[1]["level"], "ERROR")
        self.assertTrue(recs[1]["trace"].startswith("ValueError"))

    def test_same_fault_different_ids_is_one_group(self):
        agg = LS.aggregate(LS.parse(self.SAMPLE))
        sigs = {g["sig"]: g["count"] for g in agg["groups"]}
        self.assertIn(2, sigs.values())                    # العطلان بنفس التوقيع
        self.assertEqual(agg["errors"], 3)
        self.assertEqual(agg["warnings"], 1)
        self.assertEqual(agg["signals"]["http_500"], 2)
        self.assertEqual(agg["signals"]["capacity_refused"], 1)
        self.assertEqual(agg["signals"]["mail_failed"], 1)
        self.assertEqual(agg["paths"][0]["k"], "/bot/#/pay")

    def test_secrets_are_redacted_before_storage(self):
        """توكن أو بريد في سطر سجل يجب ألا يصل تقريراً يُعرض أو يُرسل بالبريد."""
        line = ("2026-09-22 12:00:00,000 WARNING x: token 123456789:AAHdqTcvCH1vGWJxfSeof"
                "SAs0K5PALDsaw for ali@example.com 01012345678 reset /reset/abcdef1234567890\n")
        rec = LS.parse(line)[0]
        self.assertNotIn("AAHdqTcv", rec["msg"])
        self.assertNotIn("ali@example.com", rec["msg"])
        self.assertNotIn("01012345678", rec["msg"])
        self.assertNotIn("abcdef1234567890", rec["msg"])

    def test_window_filters_by_time(self):
        recs = LS.parse(self.SAMPLE)
        cut = recs[2]["ts"]
        self.assertEqual(len(LS.parse(self.SAMPLE, since=cut)), 3)
        self.assertEqual(len(LS.parse(self.SAMPLE, until=cut)), 2)

    def test_missing_log_file_is_declared_not_guessed(self):
        out = LS.scan()
        self.assertFalse(out["available"])
        self.assertEqual(out["errors"], 0)


class ConvTests(unittest.TestCase):
    """تحليل المحادثات — دالّة نقية تُختبر بمحادثة مكتوبة بالسطر."""

    @staticmethod
    def rows(*items):
        out, t0 = [], int(time.time()) - 3600
        for i, (peer, direction, sender, text, gap) in enumerate(items):
            out.append({"bot_id": 1, "bot_name": "متجر", "peer": peer, "direction": direction,
                        "sender": sender, "kind": "text", "text": text, "created_at": t0 + gap})
        return out

    def test_normalization_and_intent(self):
        self.assertEqual(CI.normalize("الفُستان ده بِكَام؟"), "الفستان ده بكام")
        self.assertEqual(CI.classify("الفستان ده بكام؟"), "price")
        self.assertEqual(CI.classify("الشحن لاسكندرية بيوصل امتى؟"), "shipping")
        self.assertEqual(CI.classify("عايز اتكلم مع موظف"), "human")
        self.assertEqual(CI.classify("ازيك"), "other")

    def test_question_detection(self):
        self.assertTrue(CI.is_question("بكام ده؟"))
        self.assertTrue(CI.is_question("امتى يوصل"))
        self.assertFalse(CI.is_question("تمام شكرا"))

    def test_unanswered_questions_are_grouped_with_a_sample(self):
        rows = self.rows(
            ("tg:1", "in", "customer", "الشحن لاسكندرية بكام؟", 0),
            ("tg:2", "in", "customer", "الشحن لاسكندرية بكام؟", 10),
            ("tg:3", "in", "customer", "عندكم مقاس 38؟", 20),
            ("tg:3", "out", "bot", "أيوه متوفر", 25),
        )
        rep = CI.analyze(rows)
        self.assertEqual(rep["unanswered_total"], 2)
        self.assertEqual(rep["unanswered"][0]["v"], 2)
        self.assertIn("الشحن", rep["unanswered"][0]["sample"])
        self.assertEqual(rep["answer_rate"], 33.3)   # 1 من 3 واردة

    def test_reply_times_are_split_by_responder(self):
        rows = self.rows(
            ("tg:1", "in", "customer", "بكام؟", 0),
            ("tg:1", "out", "bot", "250 جنيه", 4),
            ("tg:2", "in", "customer", "فين طلبي؟", 10),
            ("tg:2", "out", "human", "هيوصل النهاردة", 610),
        )
        rep = CI.analyze(rows)
        self.assertEqual(rep["response"]["bot"]["median"], 4)
        self.assertEqual(rep["response"]["human"]["median"], 600)
        self.assertIsNone(rep["response"]["ai"])

    def test_late_reply_is_not_a_reply(self):
        """ردّ بعد ستّ ساعات لا يُحتسب ردّاً — وإلا بدت نسبة الرد ممتازة وهي ليست كذلك."""
        rows = self.rows(("tg:1", "in", "customer", "بكام؟", 0),
                         ("tg:1", "out", "bot", "250", CI.REPLY_WINDOW + 60))
        self.assertEqual(CI.analyze(rows)["unanswered_total"], 1)

    def test_waiting_conversations(self):
        rows = self.rows(("tg:1", "in", "customer", "حد موجود؟", 0))
        rep = CI.analyze(rows, now=int(time.time()))
        self.assertEqual(rep["waiting_total"], 1)
        self.assertEqual(rep["waiting"][0]["peer"], "tg:1")

    def test_sentiment_and_samples_are_redacted(self):
        rows = self.rows(("tg:1", "in", "customer", "تأخير وحش كلمني على 01012345678", 0))
        rep = CI.analyze(rows)
        self.assertEqual(rep["sentiment"]["neg"], 1)
        self.assertNotIn("01012345678", rep["negatives"][0]["text"])

    def test_empty_input_has_the_same_shape(self):
        rep = CI.analyze([])
        for k in ("intents", "unanswered", "keywords", "bots", "waiting"):
            self.assertEqual(rep[k], [])
        self.assertEqual(rep["messages"], 0)

    def test_analysis_over_the_seeded_platform(self):
        a, b = WR.period(7)
        rep = WR.conv_summary(a, b)
        self.assertEqual(rep["in_count"], 7)
        self.assertEqual(rep["conversations"], 3)
        # ردّ واحد بعد رسالتي عميل يُحتسب ردّاً عليهما — فالمتبقي سؤالان بلا إجابة
        self.assertEqual(rep["unanswered_total"], 2)
        self.assertTrue(any(i["k"] == "price" for i in rep["intents"]))
        self.assertTrue(CI.headline(rep))


class PageTests(unittest.TestCase):
    """المسارات: للمالك وحده، وترندر في اللغتين، وتصدّر ملفاً."""

    @classmethod
    def setUpClass(cls):
        cls.c = _login_admin()

    def test_report_page_renders_in_both_languages(self):
        for lang in ("ar", "en"):
            self.c.get(f"/lang/{lang}")
            r = self.c.get("/admin/report")
            self.assertEqual(r.status_code, 200, lang)
            self.assertIn(b'data-view="admin_report"', r.data)
        self.c.get("/lang/ar")

    def test_report_days_are_restricted_to_known_values(self):
        for q, want in (("?days=14", 14), ("?days=30", 30), ("?days=999", 7), ("?days=x", 7)):
            r = self.c.get("/admin/report" + q)
            self.assertEqual(r.status_code, 200)
            payload = r.data.decode("utf-8")
            self.assertIn(f'"days": {want}'.replace(" ", ""), payload.replace(" ", ""))

    def test_conversations_page_and_bot_filter(self):
        live = db.get_user_by_name("shop")
        r = self.c.get("/admin/conversations")
        self.assertEqual(r.status_code, 200)
        self.assertIn(b'data-view="admin_convo"', r.data)
        bots = db.report_bot_options()
        r = self.c.get(f"/admin/conversations?bot={bots[-1]['id']}")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.c.get("/admin/conversations?bot=abc").status_code, 200)
        self.assertTrue(live)

    def test_markdown_export(self):
        r = self.c.get("/admin/report.md")
        self.assertEqual(r.status_code, 200)
        self.assertIn("markdown", r.headers["Content-Type"])
        self.assertIn("botyalla_report", r.headers["Content-Disposition"])
        md = r.data.decode("utf-8")
        for section in ("# تقرير BotYalla", "## الخلاصة",
                        "## المال", "## سجل الخادم",
                        "## المحادثات", "## نتائج كل بوت"):
            self.assertIn(section, md, section)

    def test_csv_exports(self):
        r = self.c.get("/admin/report.csv")
        self.assertEqual(r.status_code, 200)
        self.assertIn("text/csv", r.headers["Content-Type"])
        body = r.data.decode("utf-8")
        self.assertIn("كوكي اون لاين", body)
        self.assertIn("stalled", body)
        r = self.c.get("/admin/conversations.csv")
        self.assertEqual(r.status_code, 200)
        self.assertIn("الشحن", r.data.decode("utf-8"))

    def test_csv_cells_are_not_formulas(self):
        """اسم بوت يبدأ بـ«=» يُنفَّذ صيغةً في Excel — التصدير يسبقه بعلامة اقتباس."""
        bid = db.create_bot(db.get_user_by_name("shop")["id"], "=cmd|' /c calc'!A1",
                            "T:evil", "flow", {})
        body = self.c.get("/admin/report.csv").data.decode("utf-8")
        self.assertIn("'=cmd", body)
        db.delete_bot(bid)

    def test_only_the_owner_sees_it(self):
        """الدعم يرى المدفوعات لا أرقام العمل ولا رسائل العملاء."""
        anon = _client()
        for path in ("/admin/report", "/admin/conversations", "/admin/report.csv"):
            r = anon.get(path)
            self.assertIn(r.status_code, (302, 401, 403), path)
        user = _client()
        user.post("/register", data=signup("plainuser"), follow_redirects=True)
        for path in ("/admin/report", "/admin/conversations"):
            self.assertIn(user.get(path).status_code, (302, 403, 404), path)

    def test_state_changing_routes_are_post_only(self):
        for path in ("/admin/report/send", "/admin/report/auto"):
            self.assertEqual(self.c.get(path).status_code, 405, path)

    def test_auto_toggle_persists(self):
        self.c.post("/admin/report/auto", data={"on": "0", "csrf_token": "tk"},
                    follow_redirects=True)
        self.assertEqual(db.get_platform("weekly_report"), "0")
        self.c.post("/admin/report/auto", data={"on": "1", "csrf_token": "tk"},
                    follow_redirects=True)
        self.assertEqual(db.get_platform("weekly_report"), "1")

    def test_send_now_uses_the_same_digest(self):
        sent = []
        old_sync, old_send = mailer.SYNC, mailer.send_mail
        mailer.SYNC = True
        mailer.send_mail = lambda to, subject, html, text=None, headers=None: (
            sent.append((to, subject, html)) or True)
        mailer.configured = lambda: True
        try:
            with db.get_conn() as c:
                c.execute("UPDATE users SET email='owner@example.com' WHERE role='admin'")
            r = self.c.post("/admin/report/send", data={"csrf_token": "tk"}, follow_redirects=True)
            self.assertEqual(r.status_code, 200)
        finally:
            mailer.SYNC, mailer.send_mail = old_sync, old_send
        self.assertTrue(sent, "التقرير لم يُرسل إلى بريد الإدارة")
        to, subject, html = sent[0]
        self.assertEqual(to, "owner@example.com")
        self.assertIn("BotYalla", subject)
        self.assertIn("<table", html)                   # مرّ بغلاف mailer لا نصاً خاماً
        self.assertNotEqual(db.get_platform("weekly_report_at", "0"), "0")


class DigestTests(unittest.TestCase):
    """الخلاصة النصّية (تليجرام/البريد) لا تتجاوز حدّ الرسالة ولا تُفرغ من الإجراءات."""

    @classmethod
    def setUpClass(cls):
        cls.rep = REPORT

    def test_text_digest(self):
        text = WR.to_text(cls_rep := self.rep)
        self.assertLessEqual(len(text), 3500)
        self.assertIn(cls_rep["period"]["label"], text)
        self.assertIn("←", text)                        # كل ملاحظة ومعها إجراؤها

    def test_csv_rows_have_every_section(self):
        rows = WR.csv_rows(self.rep)
        flat = json.dumps(rows, ensure_ascii=False)
        self.assertIn(WR.metric_name("signups"), flat)
        self.assertIn("كوكي اون لاين", flat)
        self.assertIn("stalled", flat)

    def test_markdown_carries_the_numbers_not_a_summary(self):
        md = WR.to_markdown(self.rep)
        self.assertIn("كوكي اون لاين", md)          # جدول البوتات
        self.assertIn("stalled", md)                 # المتعثّرون
        self.assertIn("|---", md)                    # جداول ماركداون سليمة
        self.assertNotIn("pw_hash", md)
        self.assertNotIn("T:live", md)               # لا توكن في ملف يُرسل أو يُلصق

    def test_email_has_no_secrets_and_a_link(self):
        subject, html, text = mailer.weekly_report_email(self.rep, "ar")
        self.assertIn("BotYalla", subject)
        self.assertNotIn("pw_hash", html)
        self.assertTrue(text.strip())


if __name__ == "__main__":
    unittest.main(verbosity=2)
