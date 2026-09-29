"""التكاملات (المرحلة 9): سلة · زد · Shopify · WooCommerce · Webhook ⇒ قوالب واتساب ووسوم وتسلسلات.

قناة واتساب محاكاة وفئة القالب محاكاة — لا شبكة ولا Meta. القاعدة والملفات في مجلد مؤقت.
"""
import base64, hashlib, hmac, json, os, secrets, sys, tempfile, time, unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_TMPDIR = tempfile.mkdtemp(prefix="botyalla-integ-")
os.environ["BOTYALLA_DB"] = os.path.join(_TMPDIR, "test.db")   # قبل استيراد database
os.environ["BOTYALLA_UPLOADS"] = _TMPDIR
os.environ["BOTYALLA_LOGS"] = os.path.join(_TMPDIR, "logs")
os.environ["ADMIN_USER"] = "admin"
os.environ["ADMIN_PASS"] = "In#" + secrets.token_hex(6)

import auth                                # noqa: E402
import broadcasts as BC                    # noqa: E402
import database as db                      # noqa: E402
import integrations as INTEG               # noqa: E402
import sequences as SQ                     # noqa: E402
import app as web                          # noqa: E402

PW = "Str0ng!Pass" + secrets.token_hex(3)
db.init_db(); web.seed_platform_defaults(); web.contact_defaults(); web.seed_default_admin()
web.app.config["TESTING"] = True
db.set_platform("mkt_msg_price", "30")

CATS = {"order_confirmed": "UTILITY", "cart_reminder": "MARKETING", "booking_ok": "UTILITY"}
BC._HOOKS["category"] = lambda bot, name, lang: CATS.get(name)


class WaCh:
    phone_id, page_id = "555", None

    def __init__(self):
        self.sent, self.accept = [], True

    async def send_template(self, peer, name, lang, comps):
        self.sent.append((peer, name, [p["text"] for p in (comps or [{}])[0].get("parameters", [])] if comps else []))
        return {"messages": [{"id": "wamid.x"}]} if self.accept else None


CH = WaCh()
INTEG.HOOKS["channel"] = lambda bot_row: CH
INTEG.HOOKS["spawn"] = None                      # تنفيذ متزامن في الاختبار


def user(name, plan="enterprise"):
    uid, err = db.create_account(name + secrets.token_hex(3), auth.hash_password(PW), f"{name}{secrets.token_hex(3)}@example.test",
                                 None, 30, "person", verify_required=False)
    assert not err, err
    db.mark_email_verified(uid)
    if plan:
        db.activate_subscription(uid, plan, 30)
    return uid


def client(user_id):
    c = web.app.test_client()
    with c.session_transaction() as s:
        u = db.get_user(user_id)
        s.update(_csrf="tk", uid=user_id, uname=u["username"], role=u["role"], pwv=web._pw_stamp(u["pw_hash"]))
    return c


def post(c, url, body=None):
    return c.post(url, data=json.dumps(body or {}), content_type="application/json", headers={"X-CSRF-Token": "tk"})


class Acct:
    def __init__(self, provider, secret="", rules=None):
        self.owner = user("st")
        self.c = client(self.owner)
        self.bot = db.create_bot(self.owner, "WA", f"wa:{secrets.randbelow(10**12)}", "flow", {}, "whatsapp")
        r = post(self.c, "/api/integrations", {"provider": provider, "name": "متجر الفرسان", "bot": self.bot, "secret": secret}).get_json()
        assert r["ok"], r
        self.item = r["items"][-1]
        self.secret = secret
        if rules is not None:
            self.save(rules)

    def save(self, rules, **kw):
        body = {"name": self.item["name"], "bot": self.bot, "cc": "+966", "rules": rules, **kw}
        r = post(self.c, f"/api/integrations/{self.item['id']}/save", body).get_json()
        if r["ok"]:
            self.item = next(x for x in r["items"] if x["id"] == self.item["id"])
        return r

    def path(self):
        return "/" + self.item["url"].split("://", 1)[1].split("/", 1)[1]

    def send(self, payload, headers=None, raw=None):
        body = raw if raw is not None else json.dumps(payload).encode()
        return web.app.test_client().post(self.path(), data=body, headers=headers or {}, content_type="application/json")

    def events(self):
        return client(self.owner).get(f"/api/integrations/{self.item['id']}/events").get_json()["events"]


def shopify_order(oid=4501, phone="0551234567"):
    return {"id": oid, "name": f"#{oid}", "total_price": "1350.00", "currency": "SAR", "financial_status": "paid",
            "phone": None, "email": "a@example.test", "order_status_url": "https://shop.example/o/1",
            "customer": {"first_name": "عبدالله", "last_name": "القحطاني", "phone": phone},
            "line_items": [{"title": "جناح ديلوكس", "quantity": 1}]}


def shopify_headers(secret, body, topic="orders/create"):
    sig = base64.b64encode(hmac.new(secret.encode(), body, hashlib.sha256).digest()).decode()
    return {"X-Shopify-Topic": topic, "X-Shopify-Hmac-Sha256": sig}


CONFIRM = [{"event": "order_created", "template": {"name": "order_confirmed", "lang": "ar",
                                                   "vars": ["{{customer_name}}", "{{order_id}}", "{{order_total}}"]},
            "tags": ["عميل متجر"]}]


class ShopifyTests(unittest.TestCase):
    def test_signed_order_sends_template_once_and_creates_contact(self):
        a = Acct("shopify", secret="shpss_" + secrets.token_hex(8), rules=CONFIRM)
        body = json.dumps(shopify_order()).encode()
        self.assertEqual(a.send(None, raw=body, headers={"X-Shopify-Topic": "orders/create", "X-Shopify-Hmac-Sha256": "bad"}).status_code, 401)
        n = len(CH.sent)
        r = a.send(None, raw=body, headers=shopify_headers(a.secret, body))
        self.assertEqual(r.get_json()["status"], "queued")
        self.assertEqual(CH.sent[n], ("wa:966551234567", "order_confirmed", ["عبدالله القحطاني", "#4501", "1,350 SAR"]))
        again = a.send(None, raw=body, headers=shopify_headers(a.secret, body))          # المتجر يعيد الإشعار
        self.assertEqual(again.get_json()["status"], "duplicate")
        self.assertEqual(len(CH.sent), n + 1, "نفس الطلب لا يصل العميل مرتين")
        with db.get_conn() as c:
            ct = c.execute("SELECT id, name, email, source FROM contacts WHERE owner_id=? AND phone=?", (a.owner, "+966551234567")).fetchone()
            tags = [r[0] for r in c.execute("SELECT t.name FROM contact_tags ct JOIN tags t ON t.id=ct.tag_id WHERE ct.contact_id=?", (ct["id"],))]
        self.assertEqual((ct["name"], ct["email"], ct["source"]), ("عبدالله القحطاني", "a@example.test", "integration"))
        self.assertEqual(tags, ["عميل متجر"])
        ev = a.events()[0]
        self.assertEqual((ev["event"], ev["status"], ev["phone"]), ("order_created", "sent", "+966551234567"))
        self.assertTrue(db.peer_known(a.bot, "wa:966551234567"), "الرسالة المرسلة تفتح محادثة في الصندوق")

    def test_unhandled_topic_and_no_rule_are_ignored_and_no_phone_skipped(self):
        a = Acct("shopify", rules=CONFIRM)
        body = json.dumps(shopify_order(9)).encode()
        self.assertEqual(a.send(None, raw=body, headers={"X-Shopify-Topic": "products/update"}).get_json()["status"], "ignored")
        self.assertEqual(a.send(None, raw=body, headers={"X-Shopify-Topic": "orders/paid"}).get_json()["status"], "ignored")
        o = shopify_order(10, phone=None)
        o["customer"]["phone"] = None
        self.assertEqual(a.send(o, headers={"X-Shopify-Topic": "orders/create"}).get_json()["status"], "skipped")
        self.assertEqual(a.events()[0]["detail"], "no_phone")


class PolicyTests(unittest.TestCase):
    def test_stop_is_never_messaged(self):
        a = Acct("woocommerce", rules=CONFIRM)
        cid, _ = db.upsert_contact_by_phone(a.owner, "+966500000111", "سارة")
        with db.get_conn() as c:
            c.execute("UPDATE contacts SET optin=0 WHERE id=?", (cid,))
        n = len(CH.sent)
        body = {"id": 77, "number": "77", "status": "pending", "total": "99", "currency": "SAR",
                "billing": {"first_name": "سارة", "phone": "0500000111"}, "line_items": []}
        self.assertEqual(a.send(body, headers={"X-WC-Webhook-Topic": "order.created"}).get_json()["status"], "queued")
        self.assertEqual(len(CH.sent), n)
        self.assertEqual((a.events()[0]["status"], a.events()[0]["detail"]), ("skipped", "stopped"))
        # «ping» غير JSON عند إنشاء الويبهوك في WooCommerce
        self.assertEqual(a.send(None, raw=b"webhook_id=5").get_json()["status"], "ignored")

    def test_abandoned_cart_is_marketing_needs_optin_charges_and_refunds(self):
        rules = [{"event": "cart_abandoned", "template": {"name": "cart_reminder", "lang": "ar", "vars": ["{{order_url}}"]}}]
        a = Acct("salla", rules=rules)
        db.wallet_topup(a.owner, 1000)
        price = web.mkt_price()

        def cart(cid, mobile):
            return {"event": "abandoned.cart", "data": {"id": cid, "total": {"amount": 450, "currency": "SAR"},
                                                        "checkout_url": f"https://salla.sa/c/{cid}",
                                                        "customer": {"name": "خالد", "mobile": mobile, "mobile_code": "+966"}}}
        n = len(CH.sent)
        a.send(cart(1, "511111111"))
        self.assertEqual((a.events()[0]["status"], a.events()[0]["detail"]), ("skipped", "no_optin"))
        self.assertEqual(len(CH.sent), n)
        cid, _ = db.upsert_contact_by_phone(a.owner, "+966522222222", "ريم")
        with db.get_conn() as c:
            c.execute("UPDATE contacts SET optin=1 WHERE id=?", (cid,))
        a.send(cart(2, "522222222"))
        self.assertEqual(CH.sent[-1], ("wa:966522222222", "cart_reminder", ["https://salla.sa/c/2"]))
        self.assertEqual(db.wallet_balance(a.owner), 1000 - price)
        CH.accept = False
        try:
            cid, _ = db.upsert_contact_by_phone(a.owner, "+966533333333", "فهد")
            with db.get_conn() as c:
                c.execute("UPDATE contacts SET optin=1 WHERE id=?", (cid,))
            a.send(cart(3, "533333333"))
        finally:
            CH.accept = True
        self.assertEqual(a.events()[0]["status"], "failed")
        self.assertEqual(db.wallet_balance(a.owner), 1000 - price, "رفض Meta = ردّ كامل")

    def test_salla_signature_and_status_mapping(self):
        rules = [{"event": "order_shipped", "template": {"name": "order_confirmed", "lang": "ar", "vars": ["{{order_status}}", "{{tracking_url}}"]}}]
        sec = secrets.token_hex(12)
        a = Acct("salla", secret=sec, rules=rules)
        body = json.dumps({"event": "order.status.updated", "data": {
            "id": 88, "reference_id": 2231, "status": {"slug": "shipped", "name": "تم الشحن"},
            "amounts": {"total": {"amount": 300, "currency": "SAR"}}, "shipments": [{"tracking_link": "https://t.example/1"}],
            "customer": {"first_name": "منى", "mobile": 544444444, "mobile_code": "+966"}}}).encode()
        self.assertEqual(a.send(None, raw=body).status_code, 401)
        sig = hmac.new(sec.encode(), body, hashlib.sha256).hexdigest()
        a.send(None, raw=body, headers={"X-Salla-Signature": sig})
        self.assertEqual(CH.sent[-1], ("wa:966544444444", "order_confirmed", ["تم الشحن", "https://t.example/1"]))


class WebhookTests(unittest.TestCase):
    def test_booking_engine_event_with_custom_vars_tags_and_sequence(self):
        owner_probe = Acct("webhook")
        seq = db.save_sequence(owner_probe.owner, None, owner_probe.bot, "بعد الحجز",
                               SQ.clean_spec({"steps": [{"delay": 60, "kind": "template",
                                                          "template": {"name": "booking_ok", "lang": "ar", "vars": []}}]}), True)
        rules = [{"event": "booking_confirmed", "template": {"name": "booking_ok", "lang": "ar",
                                                             "vars": ["{{contact.name}}", "{{hotel}}", "{{checkin}}"]},
                  "tags": ["حجز مؤكد"], "sequence": seq}]
        self.assertTrue(owner_probe.save(rules)["ok"])
        sec = secrets.token_hex(10)
        self.assertTrue(owner_probe.save(rules, secret=sec)["ok"])
        body = json.dumps({"event": "booking_confirmed", "id": "BK-1", "phone": "+966555000999", "name": "أحمد",
                           "data": {"hotel": "الفرسان مكة", "checkin": "2026-10-12", "nested": {"x": 1}, "bad key": "x"}}).encode()
        self.assertEqual(owner_probe.send(None, raw=body).status_code, 401)
        sig = hmac.new(sec.encode(), body, hashlib.sha256).hexdigest()
        owner_probe.send(None, raw=body, headers={"X-BotYalla-Signature": sig})
        self.assertEqual(CH.sent[-1], ("wa:966555000999", "booking_ok", ["أحمد", "الفرسان مكة", "2026-10-12"]))
        with db.get_conn() as c:
            st = c.execute("SELECT status FROM sequence_enrollments WHERE sequence_id=? AND peer=?", (seq, "wa:966555000999")).fetchone()
        self.assertEqual(st["status"], "active")

    def test_rules_validation_page_props_and_access(self):
        a = Acct("shopify", secret="topsecret-" + secrets.token_hex(6))
        self.assertEqual(a.save([{"event": "booking_confirmed", "tags": ["x"]}])["error"], "rule:event")
        self.assertEqual(a.save([{"event": "order_paid"}])["error"], "rule:action")
        self.assertEqual(a.save([{"event": "order_paid", "template": {"name": "Bad Name", "lang": "ar"}}])["error"], "rule:template")
        self.assertEqual(a.save([{"event": "order_paid", "tags": ["x"], "sequence": 999999}])["error"], "rule:sequence")
        page = a.c.get("/integrations").get_data(as_text=True)
        self.assertNotIn(a.secret, page)
        self.assertNotIn(db.get_integration(a.item["id"], a.owner)["secret"], page, "ولا حتى مختوماً")
        self.assertTrue(a.item["has_secret"])
        other = Acct("webhook")
        self.assertEqual(post(other.c, f"/api/integrations/{a.item['id']}/save", {"name": "x", "bot": other.bot, "rules": []}).status_code, 404)
        self.assertEqual(client(user("basic", "merchant")).get("/integrations").status_code in (302, 403), True)
        self.assertEqual(web.app.test_client().post("/in/" + "0" * 32, data=b"{}").status_code, 404)
        old = a.path()
        post(a.c, f"/api/integrations/{a.item['id']}/rotate")
        self.assertEqual(web.app.test_client().post(old, data=b"{}").status_code, 404, "الرابط القديم يتوقّف فوراً")
        # صاحب التكامل نزل من باقة الشركات ⇒ المسار يتوقّف
        b = Acct("webhook", rules=[{"event": "x", "tags": ["y"]}])
        with db.get_conn() as c:
            c.execute("UPDATE subscriptions SET status='expired' WHERE user_id=?", (b.owner,))
        self.assertEqual(b.send({"event": "x", "phone": "0551112222"}).status_code, 404)


class ParseTests(unittest.TestCase):
    def test_zid_and_woo_status_mapping(self):
        z = INTEG.parse("zid", {}, {"id": 5, "code": "Z5", "order_status": {"code": "delivered", "name": "تم التوصيل"},
                                    "order_total": "220.5", "currency_code": "SAR", "customer": {"name": "ليلى", "mobile": "0566666666"},
                                    "products": [{"name": "سجادة", "quantity": 2}]})
        self.assertEqual((z["event"], z["vars"]["order_id"], z["vars"]["order_total"], z["vars"]["order_items"]),
                         ("order_completed", "#Z5", "220.5 SAR", "2× سجادة"))
        w = INTEG.parse("woocommerce", {"X-WC-Webhook-Topic": "order.updated"}, {"id": 3, "status": "processing", "billing": {}})
        self.assertEqual(w["event"], "order_paid")
        self.assertIsNone(INTEG.parse("woocommerce", {"X-WC-Webhook-Topic": "order.updated"}, {"id": 3, "status": "on-hold"}))
        self.assertIsNone(INTEG.parse("webhook", {}, {"event": "Bad Event!"}))


# ---- Facebook Lead Ads ----
import meta_pages as MP                    # noqa: E402

APP_SECRET = "app-" + secrets.token_hex(8)
db.set_platform("wa_app_secret", APP_SECRET)
LEADS = {}


def fake_fetch(leadgen_id, page_token):
    if leadgen_id not in LEADS:
        raise MP.PagesError("lead", "(#100) lead not found")
    assert page_token == "EAA-page-token-leads"
    return LEADS[leadgen_id]


def meta_post(payload):
    body = json.dumps(payload).encode()
    sig = "sha256=" + hmac.new(APP_SECRET.encode(), body, hashlib.sha256).hexdigest()
    return web.app.test_client().post("/wh/meta", data=body, content_type="application/json",
                                      headers={"X-Hub-Signature-256": sig})


def leadgen_payload(page, lid, form="778899001"):
    return {"object": "page", "entry": [{"id": page, "time": 1, "changes": [{"field": "leadgen", "value": {
        "leadgen_id": lid, "page_id": page, "form_id": form, "ad_id": "1200001", "created_time": 1}}]}]}


class FakeGoogle:
    """docs.google.com يحوّل لـ googleusercontent ثم CSV — أو صفحة دخول لجدول غير مشترك."""
    csv, shared, redirect_to = "", True, "https://doc-0s-9c.sheets.googleusercontent.com/export/abc"

    def __init__(self, *a, **k): pass
    def close(self): pass

    def get(self, url):
        class Resp:
            def __init__(s, code, body=b"", loc=None):
                s.status_code, s.content, s.headers = code, body, ({"location": loc} if loc else {})
        if url.startswith("https://docs.google.com/"):
            return Resp(307, loc=FakeGoogle.redirect_to)
        if not FakeGoogle.shared:
            return Resp(200, b"<!doctype html><html>Sign in</html>")
        return Resp(200, FakeGoogle.csv.encode("utf-8"))


SHEET = "https://docs.google.com/spreadsheets/d/1AbCdEfGhIjKlMnOpQrStUvWxYz0123456789/edit#gid=0"


class SheetsTests(unittest.TestCase):
    def setUp(self):
        import httpx
        self._orig = httpx.Client
        httpx.Client = FakeGoogle
        FakeGoogle.shared, FakeGoogle.redirect_to = True, "https://doc-0s-9c.sheets.googleusercontent.com/export/abc"
        FakeGoogle.csv = "الاسم,رقم الجوال,الباقة\nقديم,0500000001,عادية\nقديم2,0500000002,عادية\n"

    def tearDown(self):
        import httpx
        httpx.Client = self._orig

    def make(self, **extra):
        owner = user("sh")
        c = client(owner)
        bot = db.create_bot(owner, "WA", f"wa:{secrets.randbelow(10**12)}", "flow", {}, "whatsapp")
        r = post(c, "/api/integrations", {"provider": "sheets", "name": "ردود نموذج العمرة", "bot": bot, "sheet_url": SHEET, **extra}).get_json()
        return owner, c, bot, r

    def test_only_new_rows_are_messaged_once(self):
        owner, c, bot, r = self.make()
        self.assertTrue(r["ok"], r)
        item = r["items"][-1]
        self.assertEqual((item["rows_seen"], item["headers"], item["url"]), (2, ["الاسم", "رقم_الجوال", "الباقة"], ""))
        rules = [{"event": "row_added", "template": {"name": "booking_ok", "lang": "ar", "vars": ["{{الاسم}}", "{{الباقة}}", "-"]}, "tags": ["نموذج العمرة"]}]
        self.assertTrue(post(c, f"/api/integrations/{item['id']}/save", {"name": item["name"], "bot": bot, "rules": rules}).get_json()["ok"])
        self.assertEqual(post(c, f"/api/integrations/{item['id']}/save", {"name": "x", "bot": bot, "rules": [{"event": "lead", "tags": ["x"]}]}).get_json()["error"], "rule:event")
        n = len(CH.sent)
        FakeGoogle.csv += "سارة,0555000111,VIP\nبلا رقم,,عادية\n"
        future = int(time.time()) + 300
        self.assertEqual(INTEG.sheets_tick(now=future), 2)
        self.assertEqual(CH.sent[n:], [("wa:966555000111", "booking_ok", ["سارة", "VIP", "-"])], "القدامى لا يُراسَلون")
        ev = client(owner).get(f"/api/integrations/{item['id']}/events").get_json()["events"]
        self.assertEqual(sorted((e["status"], e["detail"]) for e in ev), [("sent", "booking_ok"), ("skipped", "no_phone")])
        self.assertEqual(INTEG.sheets_tick(now=future + 1), 0, "كل دقيقتين لا أكثر")
        INTEG.sheets_tick(now=future + 400)             # (تكاملات جداول الاختبارات الأخرى تُستطلع أيضاً)
        ev = client(owner).get(f"/api/integrations/{item['id']}/events").get_json()["events"]
        self.assertEqual(len(ev), 2, "لا صف جديد = لا حدث جديد")
        self.assertEqual(db.get_integration(item["id"], owner)["cursor"], 4)
        self.assertEqual(len(CH.sent), n + 1)

    def test_link_validation_and_hosts(self):
        _, _, _, r = self.make(sheet_url="https://evil.example/spreadsheets/d/1AbCdEfGhIjKlMnOpQrStUvWxYz0123456789")
        self.assertEqual(r["error"], "sheet")
        FakeGoogle.shared = False
        self.assertEqual(self.make()[3]["error"], "sheet", "جدول غير مشترك ⇒ صفحة دخول ⇒ خطأ واضح")
        FakeGoogle.shared, FakeGoogle.redirect_to = True, "http://169.254.169.254/latest"
        self.assertEqual(self.make()[3]["error"], "sheet", "لا تحويل إلا لمضيفات Google")
        self.assertEqual(INTEG.sheet_csv_url("https://docs.google.com/spreadsheets/d/e/2PACX-1vQabcdefghijklmnopqrstuv/pubhtml?gid=55"),
                         "https://docs.google.com/spreadsheets/d/e/2PACX-1vQabcdefghijklmnopqrstuv/pub?output=csv&gid=55")

    def test_chosen_phone_column(self):
        FakeGoogle.csv = "name,mobile_2\nold,0500000009\n"
        owner, c, bot, r = self.make(phone_col="mobile_2")
        item = r["items"][-1]
        post(c, f"/api/integrations/{item['id']}/save", {"name": item["name"], "bot": bot, "phone_col": "mobile_2",
                                                          "rules": [{"event": "row_added", "tags": ["x"]}]})
        FakeGoogle.csv += "new,0566600011\n"
        INTEG.sheets_tick(now=int(time.time()) + 300)
        ev = client(owner).get(f"/api/integrations/{item['id']}/events").get_json()["events"][0]
        self.assertEqual((ev["status"], ev["phone"]), ("done", "+966566600011"))


class LeadAdsTests(unittest.TestCase):
    def setUp(self):
        self._c, self._f = MP.leads_connect, MP.fetch_lead
        MP.leads_connect = lambda page_id, token, app_id="", secret="": {"page_token": "EAA-page-token-leads", "name": "Alforsan Hotels"}
        MP.fetch_lead = fake_fetch

    def tearDown(self):
        MP.leads_connect, MP.fetch_lead = self._c, self._f

    def make(self):
        owner = user("ld")
        c = client(owner)
        bot = db.create_bot(owner, "WA", f"wa:{secrets.randbelow(10**12)}", "flow", {}, "whatsapp")
        page = str(10**14 + secrets.randbelow(10**13))
        r = post(c, "/api/integrations", {"provider": "fb_leads", "name": "إعلانات العمرة", "bot": bot,
                                          "page_id": page, "token": "EAA-user-token-xxxxxxxxxxxx"}).get_json()
        assert r["ok"], r
        item = r["items"][-1]
        return owner, c, bot, page, item

    def test_lead_form_reaches_whatsapp_in_seconds_with_form_specific_rule(self):
        owner, c, bot, page, item = self.make()
        self.assertEqual((item["page_id"], item["page_name"], item["url"], item["has_token"]), (page, "Alforsan Hotels", "", True))
        self.assertNotIn("EAA-page-token-leads", c.get("/integrations").get_data(as_text=True))
        body = {"name": item["name"], "bot": bot, "cc": "+966", "rules": [
            {"event": "lead", "template": {"name": "booking_ok", "lang": "ar", "vars": ["{{full_name}}", "{{city}}", "{{ad_name}}"]}, "tags": ["Lead Ads"]},
            {"event": "form_555000111", "template": {"name": "order_confirmed", "lang": "ar", "vars": ["{{full_name}}", "{{package}}", "-"]}}]}
        self.assertTrue(post(c, f"/api/integrations/{item['id']}/save", body).get_json()["ok"])
        self.assertEqual(post(c, f"/api/integrations/{item['id']}/save", dict(body, rules=[{"event": "order_created", "tags": ["x"]}])).get_json()["error"], "rule:event")
        LEADS["900000001"] = {"id": "900000001", "form_id": "778899001", "ad_name": "عمرة 1448",
                              "field_data": [{"name": "full_name", "values": ["نورة"]}, {"name": "phone_number", "values": ["+966 50 777 1234"]},
                                             {"name": "city", "values": ["الرياض"]}, {"name": "email", "values": ["n@example.test"]}]}
        n = len(CH.sent)
        self.assertEqual(meta_post(leadgen_payload(page, "900000001")).status_code, 200)
        self.assertEqual(CH.sent[n], ("wa:966507771234", "booking_ok", ["نورة", "الرياض", "عمرة 1448"]))
        meta_post(leadgen_payload(page, "900000001"))                  # Meta تعيد الإشعار
        self.assertEqual(len(CH.sent), n + 1)
        LEADS["900000002"] = {"id": "900000002", "form_id": "555000111",
                              "field_data": [{"name": "full_name", "values": ["سعد"]}, {"name": "phone_number", "values": ["0508889999"]},
                                             {"name": "Package?", "values": ["VIP"]}]}
        meta_post(leadgen_payload(page, "900000002", form="555000111"))
        self.assertEqual(CH.sent[-1], ("wa:966508889999", "order_confirmed", ["سعد", "VIP", "-"]))
        ev = client(owner).get(f"/api/integrations/{item['id']}/events").get_json()["events"]
        self.assertEqual([(e["status"], e["phone"]) for e in ev[:2]], [("sent", "+966508889999"), ("sent", "+966507771234")])
        with db.get_conn() as cc:
            self.assertEqual(cc.execute("SELECT name FROM contacts WHERE owner_id=? AND phone=?", (owner, "+966507771234")).fetchone()["name"], "نورة")

    def test_unsigned_unknown_page_and_fetch_failure(self):
        owner, c, bot, page, item = self.make()
        post(c, f"/api/integrations/{item['id']}/save", {"name": "x", "bot": bot, "rules": [{"event": "lead", "tags": ["t"]}]})
        body = json.dumps(leadgen_payload(page, "900000009")).encode()
        self.assertEqual(web.app.test_client().post("/wh/meta", data=body, content_type="application/json",
                                                    headers={"X-Hub-Signature-256": "sha256=bad"}).status_code, 403)
        self.assertEqual(INTEG.leadgen(leadgen_payload("123456789012", "900000010")), 0)
        meta_post(leadgen_payload(page, "900000011"))                  # غير موجود عند Meta
        ev = client(owner).get(f"/api/integrations/{item['id']}/events").get_json()["events"][0]
        self.assertEqual(ev["status"], "failed")
        self.assertIn("lead not found", ev["detail"])
        # حمولة على مسار /in/ لتكامل Lead Ads لا تُنفَّذ أبداً
        with db.get_conn() as cc:
            key = cc.execute("SELECT key FROM integrations WHERE id=?", (item["id"],)).fetchone()["key"]
        self.assertEqual(web.app.test_client().post(f"/in/{key}", data=b'{"event":"lead","phone":"0501"}').get_json()["status"], "ignored")

    def test_connect_error_is_explained(self):
        def refuse(*a, **k):
            raise MP.PagesError("subscribe", "(#200) requires leads_retrieval permission")
        MP.leads_connect = refuse
        owner = user("ld")
        bot = db.create_bot(owner, "WA", f"wa:{secrets.randbelow(10**12)}", "flow", {}, "whatsapp")
        r = post(client(owner), "/api/integrations", {"provider": "fb_leads", "name": "x", "bot": bot, "page_id": "123456789", "token": "EAA-x" * 5})
        self.assertEqual((r.status_code, r.get_json()["error"]), (400, "page_subscribe"))
        self.assertIn("leads_retrieval", r.get_json()["message"])
        self.assertEqual(db.list_integrations(owner), [], "لا تكامل نصف مربوط")

    def test_leads_connect_merges_existing_page_fields(self):
        posted = []

        class R:
            def __init__(self, code, body):
                self.status_code, self._b, self.text = code, body, json.dumps(body)

            def json(self):
                return self._b

        class G:
            def __init__(self, *a, **k):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def get(self, url, params=None, **k):
                if url.endswith("/me"):
                    return R(200, {"id": "4455667788", "name": "p"})
                if url.endswith("/subscribed_apps"):
                    return R(200, {"data": [{"id": "77", "subscribed_fields": ["messages", "messaging_postbacks"]}]})
                return R(200, {"id": "4455667788", "name": "Alforsan"})

            def post(self, url, params=None, **k):
                posted.append(params["subscribed_fields"])
                return R(200, {"success": True})
        orig = MP.httpx.Client
        MP.httpx.Client = G
        try:
            r = self._c("4455667788", "EAA-page-token-xxxxxxxxxxxx", "77")
        finally:
            MP.httpx.Client = orig
        self.assertEqual(r["name"], "Alforsan")
        self.assertEqual(posted, ["messages,messaging_postbacks,leadgen"], "ماسنجر يبقى مشتركاً")


if __name__ == "__main__":
    unittest.main(verbosity=2)
