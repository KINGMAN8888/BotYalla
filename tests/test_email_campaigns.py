"""رسائل البريد: القالب بالهوية · حملات الأدمن · الإلغاء بضغطة · تذكير الانتهاء بالإيميل.

    python tests/test_email_campaigns.py
"""
import json, os, secrets, sys, tempfile, time, unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_TMPDIR = tempfile.mkdtemp(prefix="botyalla-mailcamp-")
os.environ["BOTYALLA_DB"] = os.path.join(_TMPDIR, "test.db")   # قبل استيراد database
os.environ["BOTYALLA_UPLOADS"] = _TMPDIR
os.environ["BOTYALLA_LOGS"] = _TMPDIR
PW = "mc_" + secrets.token_hex(6)
os.environ["ADMIN_USER"] = "admin"
os.environ["ADMIN_PASS"] = PW
os.environ["PUBLIC_URL"] = "https://botyalla.test"
SMTP_ENV = {"SMTP_HOST": "smtp.test", "SMTP_PORT": "587", "SMTP_USER": "bot", "SMTP_PASS": "pw",
            "SMTP_FROM": "BotYalla <no-reply@botyalla.test>", "SMTP_TLS": "starttls"}
os.environ.update(SMTP_ENV)

import auth                                # noqa: E402
import database as db                      # noqa: E402
import app as web                          # noqa: E402
import mailer                              # noqa: E402
import email_campaigns as EC               # noqa: E402

SENT = []


class FakeSMTP:
    """بديل smtplib.SMTP يسجّل الرسائل ولا يلمس الشبكة."""
    fail = None

    def __init__(self, host, port, timeout=None, context=None):
        if FakeSMTP.fail:
            raise FakeSMTP.fail

    def __enter__(self): return self
    def __exit__(self, *a): return False
    def starttls(self, context=None): pass
    def login(self, u, p): pass
    def send_message(self, msg): SENT.append(msg)


def _boot():
    db.init_db()
    web.seed_platform_defaults()
    web.contact_defaults()
    web.seed_default_admin()
    web.app.config["TESTING"] = True
    mailer.smtplib.SMTP = FakeSMTP
    mailer.smtplib.SMTP_SSL = FakeSMTP
    mailer.SYNC = True
    EC.SYNC, EC.INTERVAL = True, 0


def _client(login=None):
    c = web.app.test_client()
    with c.session_transaction() as s:
        s["_csrf"] = "tk"
    if login:
        r = c.post("/login", data={"username": login, "password": PW, "csrf_token": "tk"})
        assert r.status_code == 302, r.status_code
    return c


def _user(name, email=None, news=False, plan=None, blocked=False, role=None):
    uid = db.create_user(name, auth.hash_password(PW), email=email)
    if news:
        db.set_email_news(uid, True)
    if plan:
        db.activate_subscription(uid, plan)
    with db.get_conn() as c:
        if blocked:
            c.execute("UPDATE users SET is_blocked=1 WHERE id=?", (uid,))
        if role:
            c.execute("UPDATE users SET role=? WHERE id=?", (role, uid))
    return uid


def _to(msgs=None):
    return sorted(m["To"] for m in (SENT if msgs is None else msgs))


def _reset_state():
    SENT.clear()
    FakeSMTP.fail = None
    mailer._sent.clear()
    web._login_attempts.clear()
    os.environ.update(SMTP_ENV)
    os.environ["PUBLIC_URL"] = "https://botyalla.test"
    db.set_platform("email_daily_cap", "250")
    with db.get_conn() as c:                       # لا حملة عالقة من اختبار سابق
        c.execute("UPDATE email_campaigns SET status='done' WHERE status='sending'")


class TemplateTests(unittest.TestCase):
    """كل رسالة بهوية العلامة: الشعار مضمَّن، والرد يصل صندوقاً حقيقياً."""

    @classmethod
    def setUpClass(cls):
        _boot()

    def setUp(self):
        _reset_state()

    def test_every_email_carries_the_logo_inline_and_a_reply_to(self):
        subject, html, text = mailer.reset_email("https://botyalla.test/reset/abc", "ar")
        self.assertIn(f"cid:{mailer.MARK_CID}", html)
        self.assertTrue(mailer.send_mail("a@b.co", subject, html, text))
        msg = SENT[0]
        imgs = [p for p in msg.walk() if p.get_content_type() == "image/png"]
        self.assertEqual(len(imgs), 1, "الشعار جزء من الرسالة لا رابط خارجي")
        self.assertEqual(imgs[0]["Content-ID"], f"<{mailer.MARK_CID}>")
        self.assertEqual(msg["Reply-To"], "info@botyalla.com", "المرسل no-reply — الرد يذهب للدعم")

    def test_the_support_email_is_the_official_domain_and_migrates_once(self):
        self.assertEqual(db.get_platform("support_email"), "info@botyalla.com")
        db.set_platform("support_email", "info@youssefalsherief.tech")    # القيمة الافتراضية القديمة
        web.contact_defaults()
        self.assertEqual(db.get_platform("support_email"), "info@botyalla.com")
        db.set_platform("support_email", "help@example.com")              # كتبها الأدمن بنفسه
        web.contact_defaults()
        self.assertEqual(db.get_platform("support_email"), "help@example.com", "لا يُلمس ما كتبه الأدمن")
        db.set_platform("support_email", "info@botyalla.com")
        body = _client().get("/.well-known/security.txt").get_data(as_text=True)
        self.assertIn("mailto:info@botyalla.com", body)

    def test_campaign_text_is_escaped_then_formatted(self):
        content = {"ar": {"subject": "جديد", "body": "أهلاً {name}\n\n- نقطة **مهمة**\n"
                          "<script>alert(1)</script> https://botyalla.test/x?a=1&b=2"},
                   "en": None, "url": "", "code": "YALLA20"}
        _, html, text = mailer.campaign_email(content, "ar", "x<b>y", "news", unsub="https://botyalla.test/u")
        self.assertNotIn("<script>alert", html)
        self.assertIn("&lt;script&gt;", html)
        self.assertIn("x&lt;b&gt;y", html, "{name} يمرّ بالهروب")
        self.assertIn(">مهمة</b>", html)
        self.assertIn('href="https://botyalla.test/x?a=1&amp;b=2"', html)
        self.assertIn("YALLA20", html)
        self.assertIn("https://botyalla.test/u", html, "رابط الإلغاء في كل رسالة أخبار")
        self.assertNotIn("**", text)

    def test_links_to_our_site_carry_utm_but_external_links_do_not(self):
        c = {"ar": {"subject": "s", "body": "body text"}, "en": None, "code": "",
             "url": "https://botyalla.test/pricing"}
        _, html, _ = mailer.campaign_email(c, "ar", "n", "service", campaign_id=7)
        self.assertIn("utm_source=email", html)
        self.assertIn("utm_campaign=c7", html)
        c["url"] = "https://example.com/x"
        _, html, _ = mailer.campaign_email(c, "ar", "n", "service", campaign_id=7)
        self.assertNotIn("utm_source", html)

    def test_english_readers_get_the_english_version_only_when_written(self):
        c = {"ar": {"subject": "عربي", "body": "نص عربي"}, "en": {"subject": "English", "body": "English body"},
             "url": "", "code": ""}
        self.assertEqual(mailer.campaign_email(c, "en", "n")[0], "English")
        self.assertEqual(mailer.campaign_email(c, "ar", "n")[0], "عربي")
        c["en"] = None
        self.assertEqual(mailer.campaign_email(c, "en", "n")[0], "عربي")

    def test_welcome_leads_with_one_tap_creation(self):
        _, html, text = mailer.welcome_email("sara", "https://botyalla.test/dashboard", "ar")
        self.assertIn("بضغطة", text)
        self.assertIn("BotFather", text, "الطريق اليدوي مذكور كبديل")


class AudienceTests(unittest.TestCase):
    """الأخبار لمن وافق فقط؛ إشعار الخدمة لكل من له إيميل؛ المحظور لا يصله شيء."""

    @classmethod
    def setUpClass(cls):
        _boot()
        cls.news = _user("au_news", "au_news@x.co", news=True)
        cls.plain = _user("au_plain", "au_plain@x.co")
        cls.noemail = _user("au_noemail", None, news=True)
        cls.blocked = _user("au_blocked", "au_blocked@x.co", news=True, blocked=True)
        cls.paid = _user("au_paid", "au_paid@x.co", news=True, plan="merchant")
        db.create_bot(cls.paid, "متجر", "999001:AUDIENCExxxxxxxxxxxxxxxxx", "store", {})

    def ids(self, audience, kind):
        return {r["id"] for r in db.email_audience(audience, kind)}

    def test_news_only_reaches_members_who_opted_in(self):
        got = self.ids("all", "news")
        self.assertIn(self.news, got)
        self.assertIn(self.paid, got)
        for uid in (self.plain, self.noemail, self.blocked):
            self.assertNotIn(uid, got)

    def test_service_notices_reach_everyone_with_an_email(self):
        got = self.ids("all", "service")
        self.assertTrue({self.news, self.plain, self.paid} <= got)
        self.assertFalse({self.noemail, self.blocked} & got)

    def test_segments(self):
        self.assertEqual(self.ids("paid", "service") & {self.news, self.plain, self.paid}, {self.paid})
        self.assertIn(self.paid, self.ids("plan:merchant", "service"))
        self.assertNotIn(self.paid, self.ids("free", "service"))
        self.assertIn(self.plain, self.ids("free", "service"))
        self.assertNotIn(self.paid, self.ids("no_bot", "service"))
        self.assertIn(self.plain, self.ids("no_bot", "service"))
        self.assertEqual(db.email_audience("nonsense", "service"), [])
        self.assertEqual(db.email_audience_count("all", "news"), len(self.ids("all", "news")))


class CampaignTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        _boot()
        cls.members = [_user(f"cp_{i}", f"cp_{i}@x.co", news=(i % 2 == 0)) for i in range(6)]
        _user("cp_support", "cp_support@x.co", role="support")
        _user("cp_user", "cp_user@x.co")

    def setUp(self):
        _reset_state()
        self.admin = _client("admin")

    def send(self, **kw):
        body = {"kind": "news", "audience": "all",
                "ar": {"subject": "جديد في BotYalla", "body": "أهلاً {name}، هذه رسالة تجريبية."},
                "url": "/pricing"}
        body.update(kw)
        return self.admin.post("/admin/emails/send", json=body, headers={"X-CSRF-Token": "tk"}).get_json()

    def test_news_reaches_opted_in_members_once_with_one_click_unsubscribe(self):
        r = self.send()
        self.assertTrue(r["ok"], r)
        camp = db.get_email_campaign(r["id"])
        self.assertEqual(camp["status"], "done")
        expected = sorted(x["email"] for x in db.email_audience("all", "news"))
        self.assertEqual(_to(), expected)
        for m in SENT:
            self.assertIn("/email/unsubscribe/", m["List-Unsubscribe"])
            self.assertEqual(m["List-Unsubscribe-Post"], "List-Unsubscribe=One-Click")
        self.assertEqual(json.loads(camp["content"])["url"], "https://botyalla.test/pricing",
                         "المسار الداخلي يصير رابطاً من PUBLIC_URL")
        # استئناف الحملة نفسها لا يكرر رسالة لأحد
        SENT.clear()
        db.set_email_campaign(r["id"], status="sending")
        EC.start(r["id"])
        self.assertEqual(SENT, [])

    def test_service_notices_carry_no_unsubscribe_header(self):
        r = self.send(kind="service")
        self.assertTrue(r["ok"], r)
        self.assertEqual(_to(), sorted(x["email"] for x in db.email_audience("all", "service")))
        self.assertTrue(all(m["List-Unsubscribe"] is None for m in SENT))

    def test_bad_drafts_are_refused(self):
        self.assertFalse(self.send(url="javascript:alert(1)")["ok"])
        self.assertFalse(self.send(ar={"subject": "عنوان", "body": ""})["ok"])
        self.assertFalse(self.send(audience="plan:free")["ok"])
        self.assertFalse(self.send(code="bad code!")["ok"])
        os.environ["PUBLIC_URL"] = ""
        r = self.send(url="")
        self.assertFalse(r["ok"], "الأخبار بلا PUBLIC_URL = بلا رابط إلغاء ⇒ لا تُرسل")
        self.assertIn("PUBLIC_URL", r["error"])
        self.assertEqual(SENT, [])

    def test_only_the_owner_manages_email_campaigns(self):
        for name in ("cp_support", "cp_user"):
            c = _client(name)
            self.assertEqual(c.get("/admin/emails").status_code, 403, name)
            r = c.post("/admin/emails/send", json={"kind": "service"}, headers={"X-CSRF-Token": "tk"})
            self.assertEqual(r.status_code, 403, name)
        self.assertEqual(self.admin.get("/admin/emails").status_code, 200)

    def test_the_daily_cap_pauses_the_campaign_and_it_resumes_later(self):
        db.set_platform("email_daily_cap", "1")
        with db.get_conn() as c:
            c.execute("DELETE FROM email_sends")           # عدّاد اليوم يبدأ من الصفر
        r = self.send(kind="service")
        camp = db.get_email_campaign(r["id"])
        self.assertEqual((camp["sent"], camp["status"], camp["note"]), (1, "sending", "cap_wait"))
        db.set_platform("email_daily_cap", "250")
        EC.start(r["id"])
        camp = db.get_email_campaign(r["id"])
        self.assertEqual(camp["status"], "done")
        self.assertEqual(camp["sent"], camp["total"])
        self.assertEqual(len(_to()), len(set(_to())), "لا أحد استلم مرتين")

    def test_a_dead_smtp_stops_the_campaign_and_resume_retries_failures(self):
        FakeSMTP.fail = ConnectionRefusedError("down")
        r = self.send(kind="service")
        camp = db.get_email_campaign(r["id"])
        self.assertEqual((camp["status"], camp["note"], camp["failed"]), ("stopped", "smtp_error", EC.FAIL_STREAK))
        FakeSMTP.fail = None
        mailer._sent.clear()
        res = self.admin.post(f"/admin/emails/{r['id']}/resume", headers={"X-CSRF-Token": "tk"}).get_json()
        self.assertTrue(res["ok"], res)
        camp = db.get_email_campaign(r["id"])
        self.assertEqual((camp["status"], camp["failed"]), ("done", 0))
        self.assertEqual(camp["sent"], camp["total"])

    def test_preview_renders_the_real_template_and_test_goes_to_the_admin(self):
        p = self.admin.post("/admin/emails/preview", json={"kind": "news", "audience": "all", "ar": {}},
                            headers={"X-CSRF-Token": "tk"}).get_json()
        self.assertIn("data:image/png;base64,", p["html"])
        self.assertNotIn("cid:", p["html"])
        self.assertEqual(p["count"], db.email_audience_count("all", "news"))
        r = self.admin.post("/admin/emails/test", json={"kind": "news", "ar": {"subject": "تجربة", "body": "نص تجربة طويل"}},
                            headers={"X-CSRF-Token": "tk"}).get_json()
        self.assertFalse(r["ok"], "الأدمن بلا إيميل — لا تجربة")
        db.set_user_email(1, "owner@botyalla.test")
        r = self.admin.post("/admin/emails/test", json={"kind": "news", "ar": {"subject": "تجربة", "body": "نص تجربة طويل"}},
                            headers={"X-CSRF-Token": "tk"}).get_json()
        self.assertTrue(r["ok"], r)
        self.assertEqual(SENT[-1]["To"], "owner@botyalla.test")
        self.assertTrue(SENT[-1]["Subject"].startswith("[تجربة]"))
        db.set_user_email(1, None)

    def test_the_unsubscribe_key_never_reaches_the_platform_page(self):
        mailer.unsub_token(1)
        page = self.admin.get("/admin/platform").get_data(as_text=True)
        self.assertNotIn(db.get_platform("email_unsub_key"), page)


class ConsentTests(unittest.TestCase):
    """الموافقة: من التسجيل أو «حسابي»، والإلغاء بضغطة من الرسالة نفسها."""

    @classmethod
    def setUpClass(cls):
        _boot()

    def setUp(self):
        _reset_state()

    def test_signup_opt_in_needs_the_box_and_an_email(self):
        for name, email, box, want in (("cs_a", "cs_a@x.co", "1", True), ("cs_b", "cs_b@x.co", None, False),
                                       ("cs_c", "", "1", False)):
            data = {"username": name, "password": PW, "email": email, "csrf_token": "tk"}
            if box:
                data["email_news"] = box
            _client().post("/register", data=data)
            self.assertEqual(db.email_news_on(db.get_user_by_name(name)["id"]), want, name)

    def test_account_toggle(self):
        uid = _user("cs_acc", "cs_acc@x.co")
        c = _client("cs_acc")
        c.post("/account/email-prefs", data={"email_news": "1", "csrf_token": "tk"})
        self.assertTrue(db.email_news_on(uid))
        c.post("/account/email-prefs", data={"email_news": "0", "csrf_token": "tk"})
        self.assertFalse(db.email_news_on(uid))
        _user("cs_noemail")
        c2 = _client("cs_noemail")
        c2.post("/account/email-prefs", data={"email_news": "1", "csrf_token": "tk"})
        self.assertFalse(db.email_news_on(db.get_user_by_name("cs_noemail")["id"]), "بلا إيميل لا موافقة")

    def test_one_click_unsubscribe_works_without_a_session_and_needs_the_right_token(self):
        uid = _user("cs_unsub", "cs_unsub@x.co", news=True)
        url = mailer.unsub_url(uid).replace("https://botyalla.test", "")
        c = web.app.test_client()                          # بلا جلسة ولا CSRF — كما يرسل Gmail
        self.assertEqual(c.get(url).status_code, 200)
        self.assertTrue(db.email_news_on(uid), "فتح الرابط وحده لا يلغي (ماسحات الروابط)")
        self.assertEqual(c.post(url, data={"List-Unsubscribe": "One-Click"}).status_code, 200)
        self.assertFalse(db.email_news_on(uid))
        self.assertEqual(c.post(url, data={"on": "1"}).status_code, 302)
        self.assertTrue(db.email_news_on(uid))
        bad = url.rsplit("/", 1)[0] + "/" + "0" * 32
        self.assertEqual(c.post(bad, data={"List-Unsubscribe": "One-Click"}).status_code, 404)
        other = _user("cs_other", "cs_other@x.co", news=True)
        self.assertFalse(mailer.check_unsub(other, mailer.unsub_token(uid)), "توكن مستخدم لا يصلح لغيره")


class ReminderTests(unittest.TestCase):
    """سياسة الخصوصية تعد بتذكير الانتهاء بالبريد — يصل حتى لو بوت المنصة متوقف."""

    @classmethod
    def setUpClass(cls):
        _boot()

    def setUp(self):
        _reset_state()

    def test_expiry_reminders_go_by_email_without_the_platform_bot(self):
        soon = _user("rm_soon", "rm_soon@x.co", plan="merchant")
        gone = _user("rm_gone", "rm_gone@x.co", plan="merchant")
        now = int(time.time())
        with db.get_conn() as c:
            c.execute("UPDATE subscriptions SET expires_at=? WHERE user_id=?", (now + int(2.5 * 86400), soon))
            c.execute("UPDATE subscriptions SET expires_at=? WHERE user_id=?", (now - 3600, gone))
        self.assertFalse(web.manager.platform_running())
        web.manager._send_reminder_cycle()
        by_to = {m["To"]: m for m in SENT}
        self.assertIn("rm_soon@x.co", by_to)
        self.assertIn("rm_gone@x.co", by_to)
        self.assertIn("3", by_to["rm_soon@x.co"]["Subject"])
        self.assertTrue(db.reminder_sent(soon, "pre3"))
        self.assertTrue(db.reminder_sent(gone, "expired"))
        SENT.clear()
        web.manager._send_reminder_cycle()
        self.assertNotIn("rm_soon@x.co", _to(), "التذكير مرة واحدة")


if __name__ == "__main__":
    unittest.main(verbosity=2)
