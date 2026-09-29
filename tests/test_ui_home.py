"""اللوحة الذكية: التنقّل المجمَّع حسب الصلاحية · الرئيسية حسب الدور والباقة · تفضيلات منظَّفة · التعلّم من الاستخدام."""
import json, os, re, secrets, sys, tempfile, unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_TMPDIR = tempfile.mkdtemp(prefix="botyalla-ui-")
os.environ["BOTYALLA_DB"] = os.path.join(_TMPDIR, "test.db")   # قبل استيراد database
os.environ["BOTYALLA_UPLOADS"] = _TMPDIR
os.environ["BOTYALLA_LOGS"] = os.path.join(_TMPDIR, "logs")
os.environ["ADMIN_USER"] = "admin"
os.environ["ADMIN_PASS"] = "Ui#" + secrets.token_hex(6)

import auth                                # noqa: E402
import database as db                      # noqa: E402
import ui as UI                            # noqa: E402
import app as web                          # noqa: E402

PW = "Str0ng!Pass" + secrets.token_hex(3)
db.init_db(); web.seed_platform_defaults(); web.contact_defaults(); web.seed_default_admin()
web.app.config["TESTING"] = True


def user(name, plan="enterprise", role=None):
    uid, err = db.create_account(name + secrets.token_hex(3), auth.hash_password(PW), f"{name}{secrets.token_hex(3)}@example.test",
                                 None, 30, "person", verify_required=False)
    assert not err, err
    db.mark_email_verified(uid)
    if plan:
        db.activate_subscription(uid, plan, 30)
    if role:
        with db.get_conn() as c:
            c.execute("UPDATE users SET role=? WHERE id=?", (role, uid))
    return uid


def client(user_id):
    c = web.app.test_client()
    with c.session_transaction() as s:
        u = db.get_user(user_id)
        s.update(_csrf="tk", uid=user_id, uname=u["username"], role=u["role"], pwv=web._pw_stamp(u["pw_hash"]))
    return c


def boot(c, path):
    html = c.get(path).get_data(as_text=True)
    m = re.search(r'<script[^>]*id="by-data"[^>]*>(.*?)</script>', html, re.S) or re.search(r"window\.BY\s*=\s*(\{.*?\});\s*</script>", html, re.S)
    assert m, html[:500]
    return json.loads(m.group(1))


def post(c, url, body=None):
    return c.post(url, data=json.dumps(body or {}), content_type="application/json", headers={"X-CSRF-Token": "tk"})


def keys(by):
    return {g["k"]: [it["k"] for it in g["items"]] for g in by["navGroups"]}


class NavTests(unittest.TestCase):
    def test_groups_follow_plan_and_role(self):
        ent = user("ent")
        db.create_bot(ent, "WA", f"wa:{secrets.randbelow(10**12)}", "flow", {}, "whatsapp")
        g = keys(boot(client(ent), "/home"))
        self.assertEqual(list(g)[:2], ["home", "conversations"])
        self.assertIn("shared_inbox", g["conversations"])
        self.assertIn("integrations", g["commerce"])
        self.assertNotIn("adm_overview", g)
        free = user("free", plan=None)
        g = keys(boot(client(free), "/dashboard"))
        self.assertNotIn("conversations", g, "لا CRM بلا باقة الشركات")
        self.assertEqual(g["automation"], ["dashboard"])
        sup = user("sup", plan=None, role="support")
        g = keys(boot(client(sup), "/home"))
        self.assertIn("admin_tickets", g["adm_support"])
        self.assertNotIn("admin_pricing", g.get("adm_finance", []), "الدعم لا يرى تسعير المالك")
        self.assertNotIn("adm_platform", g)
        adm = user("adm", plan=None, role="admin")
        g = keys(boot(client(adm), "/home"))
        self.assertIn("admin_platform", g["adm_platform"])
        self.assertIn("admin_pricing", g["adm_finance"])


class HomeTests(unittest.TestCase):
    def test_personas(self):
        free = user("nb", plan=None)
        self.assertTrue(client(free).get("/home").headers["Location"].endswith("/dashboard"), "بلا بوتات ⇒ رحلة الإعداد")
        db.create_bot(free, "TG", f"tg{secrets.token_hex(6)}", "flow", {}, "telegram")
        p = boot(client(free), "/home")["props"]
        self.assertEqual(p["persona"], "basic")
        self.assertIn("journey", p["widgets"])
        self.assertEqual(p["journey"]["current"], "teach")
        owner = user("own")
        bot = db.create_bot(owner, "WA", f"wa:{secrets.randbelow(10**12)}", "flow", {}, "whatsapp")
        db.log_message(bot, "wa:966500000001", "in", "customer", "مرحبا", name="منى")
        p = boot(client(owner), "/home")["props"]
        self.assertEqual(p["persona"], "owner")
        self.assertEqual((p["metrics"]["msgs_today"], p["metrics"]["chats_today"], p["metrics"]["bots"]), (1, 1, 1))
        self.assertEqual(len(p["metrics"]["activity"]), 14)
        self.assertEqual(p["inbox"]["rows"][0]["name"], "منى")
        self.assertIn("bots_stopped", [a["k"] for a in p["attention"]])
        member = user("mem", plan=None)
        db.join_team(owner, member, "member")
        p = boot(client(member), "/home")["props"]
        self.assertEqual(p["persona"], "member")
        self.assertIn("member_kpis", p["widgets"])
        adm = user("adm2", plan=None, role="admin")
        p = boot(client(adm), "/home")["props"]
        self.assertEqual(p["persona"], "admin")
        self.assertIn("payments", p["queues"])
        self.assertTrue(p["signups"])
        self.assertNotIn("pw_hash", json.dumps(p["signups"]))


class PrefsTests(unittest.TestCase):
    def test_prefs_are_cleaned_against_what_the_user_may_see(self):
        free = user("pf", plan=None)
        db.create_bot(free, "TG", f"tg{secrets.token_hex(6)}", "flow", {}, "telegram")
        c = client(free)
        r = post(c, "/api/ui/prefs", {"pins": ["media", "admin_platform", "shared_inbox", "evil", 5], "collapsed": ["account", "nope"],
                                      "compact": True, "widgets": ["bots", "admin_kpis", "kpis"], "hidden": ["frequent"],
                                      "actions": ["upgrade", "adm_platform", "open_inbox"], "extra": "x"}).get_json()
        self.assertEqual(r["prefs"], {"pins": ["media"], "collapsed": ["account"], "compact": True, "widgets": ["bots", "kpis"],
                                      "hidden": ["frequent"], "actions": ["upgrade"], "tour": False, "scale": 100})
        self.assertEqual(post(c, "/api/ui/prefs", {"scale": 110, "tour": True}).get_json()["prefs"]["scale"], 110)
        self.assertEqual(post(c, "/api/ui/prefs", {"scale": 400}).get_json()["prefs"]["scale"], 100, "حجم خارج القائمة يسقط")
        p = boot(c, "/home")["props"]
        self.assertEqual([w for w in p["widgets"] if w in ("bots", "kpis")], ["bots", "kpis"], "ترتيب المستخدم محفوظ")
        self.assertEqual(p["widgets"][0], "insights", "أداة جديدة لم يرها تظهر في موضعها الطبيعي لا آخر القائمة")
        self.assertEqual(p["hidden"], ["frequent"])
        self.assertEqual(p["actions"], ["upgrade"])
        self.assertEqual(post(c, "/api/ui/prefs", {"compact": False}).get_json()["prefs"]["pins"], ["media"], "الحفظ الجزئي لا يمسح الباقي")
        self.assertEqual(web.app.test_client().post("/api/ui/prefs", data="{}", content_type="application/json").status_code in (302, 400, 401), True)

    def test_usage_learning(self):
        owner = user("us")
        db.create_bot(owner, "WA", f"wa:{secrets.randbelow(10**12)}", "flow", {}, "whatsapp")
        c = client(owner)
        for _ in range(3):
            c.get("/contacts")
        c.get("/payments")
        p = boot(c, "/home")["props"]
        self.assertEqual([f["k"] for f in p["frequent"]][:2], ["contacts", "chat_payments"])
        self.assertEqual(UI.frequent(owner, {"contacts"}, now=__import__("time").time() + 400 * 86400), [], "القديم جداً يتلاشى")


class InsightsTests(unittest.TestCase):
    def test_owner_suggestions_come_from_real_numbers(self):
        import time
        owner = user("ins")
        wa = db.create_bot(owner, "WA", f"wa:{secrets.randbelow(10**12)}", "flow", {}, "whatsapp")
        p = boot(client(owner), "/home")["props"]
        self.assertEqual([x["k"] for x in p["insights"]], ["pay", "integ"], "واتساب بلا بوابة دفع ولا تكاملات")
        pid = db.create_chat_payment(owner, wa, "wa:966500000001", "moyasar", 1000, "SAR", "x", int(time.time()) + 3600)
        with db.get_conn() as c:
            c.execute("UPDATE chat_payments SET created_at=? WHERE id=?", (int(time.time()) - 3 * 3600, pid))
        for i in range(4):
            db.add_lead(wa, 966500000100 + i, {"n": i})
        with db.get_conn() as c:
            c.execute("UPDATE leads SET created_at=? WHERE bot_id=?", (int(time.time()) - 10 * 86400, wa))
        ks = [x["k"] for x in boot(client(owner), "/home")["props"]["insights"]]
        self.assertEqual(ks[:2], ["stale_pay", "leads_drop"], "الأهم أولاً: مال معلّق ثم هبوط العملاء")
        self.assertLessEqual(len(ks), 3)

    def test_basic_upgrade_moment(self):
        free = user("ib", plan=None)
        bot = db.create_bot(free, "TG", f"tg{secrets.token_hex(6)}", "flow", {}, "telegram")
        for i in range(12):
            db.add_bot_user(bot, 500 + i, "x")
        ins = boot(client(free), "/home")["props"]["insights"]
        self.assertEqual([x["k"] for x in ins], ["upgrade"])
        self.assertIn("12", ins[0]["text"])


class SupportCenterTests(unittest.TestCase):
    def test_tickets_page_metrics_customer_profile_and_canned(self):
        import time
        cust = user("cst", plan="merchant")
        db.create_bot(cust, "Shop", f"tg{secrets.token_hex(6)}", "flow", {}, "telegram")
        with db.get_conn() as c:
            tid = c.execute("INSERT INTO tickets(user_id,kind,subject,status,created_at,updated_at) VALUES(?,?,?,?,?,?)",
                            (cust, "support", "البوت لا يرد", "open", int(time.time()) - 6 * 3600, int(time.time()) - 6 * 3600)).lastrowid
            c.execute("INSERT INTO ticket_msgs(ticket_id,sender,body,created_at) VALUES(?,?,?,?)", (tid, "user", "ساعدوني", int(time.time()) - 6 * 3600))
        sup = user("sp", plan=None, role="support")
        c = client(sup)
        p = boot(c, "/admin/tickets")["props"]
        self.assertGreaterEqual(p["metrics"]["waiting"], 1, "تنتظر ردّنا أكثر من 4 ساعات")
        prof = p["customers"][str(cust)]
        self.assertEqual((prof["plan"], len(prof["bots"]), prof["tickets"]), ("merchant", 1, 1))
        self.assertNotIn("pw_hash", json.dumps(p["customers"]))
        r = post(c, "/admin/support/canned", {"items": [{"title": "ترحيب", "body": "أهلاً {{name}}، نراجع طلبك الآن"},
                                                         {"title": "", "body": "x"}, "junk"]}).get_json()
        self.assertEqual(r["items"], [{"title": "ترحيب", "body": "أهلاً {{name}}، نراجع طلبك الآن"}])
        self.assertEqual(boot(c, "/admin/tickets")["props"]["canned"][0]["title"], "ترحيب")
        self.assertIn(post(client(cust), "/admin/support/canned", {"items": []}).status_code, (302, 403), "العميل لا يعدّل ردود الدعم")
        home = boot(c, "/home")["props"]
        self.assertIn("sla", [x["k"] for x in home["insights"]])
        self.assertIn("support_kpis", home["widgets"])

    def test_admin_revenue(self):
        adm = user("rv", plan=None, role="admin")
        user("payer", plan="merchant")
        p = boot(client(adm), "/home")["props"]
        self.assertGreaterEqual(p["revenue"]["active_paid"], 1)
        self.assertGreaterEqual(p["revenue"]["mrr"], 299)
        self.assertIn("admin_revenue", p["widgets"])


class NotificationTests(unittest.TestCase):
    def test_events_reach_the_right_people(self):
        import time
        import chat_pay as CP
        owner = user("nt")
        sara, omar = user("sara", plan=None), user("omar", plan=None)
        db.join_team(owner, sara, "admin"); db.join_team(owner, omar, "member")
        bot = db.create_bot(owner, "WA", f"wa:{secrets.randbelow(10**12)}", "flow", {}, "whatsapp")
        peer = "wa:966500000077"
        db.log_message(bot, peer, "in", "customer", "مرحبا", name="منى")
        cs = client(sara)
        self.assertTrue(post(cs, "/api/inbox/assign", {"bot": bot, "peer": peer, "user": omar}).get_json()["ok"])
        items, unread = db.list_notifications(omar)
        self.assertEqual((items[0]["kind"], items[0]["data"]["name"], unread), ("assigned", "منى", 1))
        self.assertIn(f"/inbox?bot={bot}&peer=wa%3A966500000077", items[0]["url"])
        post(client(omar), "/api/inbox/assign", {"bot": bot, "peer": peer, "user": omar})
        self.assertEqual(db.list_notifications(omar)[1], 1, "لا إشعار لمن أسندها لنفسه أو لم يتغيّر مسؤولها")
        post(cs, "/api/inbox/note", {"bot": bot, "peer": peer, "text": f"@{db.get_user(omar)['username']} تابع العرض"})
        items, _ = db.list_notifications(omar)
        self.assertEqual((items[0]["kind"], items[0]["data"]["by"]), ("mention", db.get_user(sara)["username"]))
        self.assertEqual(db.list_notifications(sara)[1], 0, "الكاتب لا يُشعَر بنفسه")
        # قراءة
        co = client(omar)
        r = co.get("/api/notifications").get_json()
        self.assertEqual(r["unread"], 2)
        post(co, "/api/notifications/read", {"ids": [r["items"][0]["id"], "x"]})
        self.assertEqual(co.get("/api/notifications").get_json()["unread"], 1)
        post(co, "/api/notifications/read", {"all": True})
        self.assertEqual(co.get("/api/notifications").get_json()["unread"], 0)
        self.assertEqual(client(sara).get("/api/notifications").get_json()["items"], [], "كل مستخدم إشعاراته فقط")
        # دفعة وصلت ⇒ صاحب الحساب
        pid = db.create_chat_payment(owner, bot, peer, "moyasar", 45000, "SAR", "حجز", int(time.time()) + 3600)
        db.settle_chat_payment(pid, "paid")
        import asyncio
        CP.HOOKS["channel"] = lambda b, p: None
        asyncio.run(CP.after_settle(pid))
        items, _ = db.list_notifications(owner)
        self.assertEqual((items[0]["kind"], items[0]["data"]["amount"], items[0]["url"]), ("paid", "450 SAR", "/payments"))
        # تكامل فشل ⇒ مرة في الساعة
        for _ in range(3):
            db.notify(owner, "integ_failed", {"name": "سلة"}, "/integrations#i9", dedupe=3600)
        self.assertEqual(sum(1 for n in db.list_notifications(owner)[0] if n["kind"] == "integ_failed"), 1)

    def test_tickets_notify_staff_and_customer(self):
        cust = user("tc", plan=None)
        sup = user("tsup", plan=None, role="support")
        tid = db.create_ticket(cust, "support", "البوت متوقف", "ساعدوني")
        items, _ = db.list_notifications(sup)
        self.assertEqual((items[0]["kind"], items[0]["data"]["subject"]), ("ticket_new", "البوت متوقف"))
        db.add_ticket_msg(tid, "staff", "تم الحل")
        self.assertEqual(db.list_notifications(cust)[0][0]["kind"], "ticket_reply")
        db.add_ticket_msg(tid, "user", "شكراً")
        self.assertEqual(db.list_notifications(sup)[0][0]["kind"], "ticket_user")
        self.assertIn('"unread": 2', client(sup).get("/home").get_data(as_text=True).replace(" ", "").replace('"unread":2', '"unread": 2'))


if __name__ == "__main__":
    unittest.main(verbosity=2)
