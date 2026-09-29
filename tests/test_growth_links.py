"""النمو — المرحلة 7: روابط التتبّع (إنشاء · تحويل · عدّ النقرات · النسبة وحذف الرمز · تليجرام) ·
نقرات إعلانات CTWA (التقاط `referral` · التقرير · مشغّل الفلو) · Conversions API (لمن جاء من إعلان فقط ·
السرّ لا يعود للمتصفح) · مصدر العميل في الصندوق المشترك.

    python tests/test_growth_links.py
"""
import asyncio, json, os, secrets, sys, tempfile, unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_TMPDIR = tempfile.mkdtemp(prefix="botyalla-grl-")
os.environ["BOTYALLA_DB"] = os.path.join(_TMPDIR, "test.db")   # قبل استيراد database
os.environ["BOTYALLA_UPLOADS"] = _TMPDIR
os.environ["BOTYALLA_LOGS"] = os.path.join(_TMPDIR, "logs")
os.environ["ADMIN_USER"] = "admin"
os.environ["ADMIN_PASS"] = "Gl#" + secrets.token_hex(6)

import auth                                # noqa: E402
import database as db                      # noqa: E402
import flow_engine as FE                   # noqa: E402
import growth as GR                        # noqa: E402
import app as web                          # noqa: E402
from channels.whatsapp import WhatsAppChannel   # noqa: E402

PW = "Str0ng!Pass" + secrets.token_hex(3)
db.init_db(); web.seed_platform_defaults(); web.contact_defaults(); web.seed_default_admin()
web.app.config["TESTING"] = True


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


class Ch:
    phone_id = page_id = None

    def __init__(self):
        self.out = []

    async def send_text(self, peer, text):
        self.out.append(text); return True

    async def remove_keyboard(self, peer, text):
        self.out.append(text); return True

    async def send_buttons(self, peer, text, options):
        self.out.append(text); return True


def say(bot, peer, text, kind="text", **extra):
    ch = Ch()
    asyncio.run(FE.handle_message(db.get_bot(bot), ch, dict({"peer": peer, "kind": kind, "text": text, "name": "Ali"}, **extra)))
    return ch.out


class Acct:
    def __init__(self):
        self.owner = user("own")
        self.bot = db.create_bot(self.owner, "WA", f"wa:{secrets.randbelow(10**12)}", "flow",
                                 {"bot_username": "+966 50 000 0999", "wa_waba_id": "555000"}, "whatsapp")
        self.c = client(self.owner)

    def link(self, name="حملة رمضان", text="أريد عرض العمرة"):
        r = post(self.c, "/api/growth/links", {"bot": self.bot, "name": name, "text": text}).get_json()
        assert r["ok"], r
        return next(l for l in r["links"] if l["name"] == name)


def peer():
    return f"wa:9665{secrets.randbelow(10**8):08d}"


class LinkTests(unittest.TestCase):
    def test_create_redirect_and_count_clicks_once_per_visitor(self):
        a = Acct()
        l = a.link()
        self.assertTrue(GR.CODE_RE.match(l["code"]) and any(ch.isdigit() for ch in l["code"]))
        c = web.app.test_client()
        r = c.get(f"/go/{l['code']}")
        self.assertEqual(r.status_code, 302)
        self.assertEqual(r.headers["Location"], "https://wa.me/966500000999?text=" +
                         __import__("urllib.parse").parse.quote(f"أريد عرض العمرة #{l['code']}"))
        c.get(f"/go/{l['code']}")
        self.assertEqual(db.get_growth_link(code=l["code"])["clicks"], 1, "النقرة المكررة من نفس العنوان لا تُعدّ")
        self.assertEqual(c.get("/go/zzzzz9").status_code, 404)
        self.assertEqual(a.c.get(f"/go/{l['code']}/qr.svg").mimetype, "image/svg+xml")
        self.assertEqual(client(user("x")).get(f"/go/{l['code']}/qr.svg").status_code, 404, "QR لصاحب الرابط فقط")

    def test_attribution_strips_the_code_and_counts_the_conversation(self):
        a = Acct()
        l = a.link()
        p = peer()
        say(a.bot, p, f"أريد عرض العمرة #{l['code']}")
        msgs = db.list_messages(a.bot, p)
        self.assertEqual(msgs[0]["text"], "أريد عرض العمرة", "الرمز لا يظهر في الصندوق ولا يصل للفلو")
        say(a.bot, p, f"مرة أخرى #{l['code']}")
        link = next(x for x in db.list_growth_links(a.owner) if x["id"] == l["id"])
        self.assertEqual(link["conversations"], 1, "محادثة واحدة لكل عميل")
        other = Acct()
        ol = other.link()
        p2 = peer()
        say(a.bot, p2, f"سلام #{ol['code']}")
        self.assertIn(f"#{ol['code']}", db.list_messages(a.bot, p2)[0]["text"], "رمز بوت آخر نص عادي")
        m = GR.attribute(db.get_bot(a.bot), "tg:5", {"kind": "start", "text": f"/start l-{l['code']}"})
        self.assertEqual((m["text"], m["link"]), ("/start", l["code"]))

    def test_link_trigger_starts_its_own_flow(self):
        a = Acct()
        l = a.link()
        fid = post(a.c, f"/api/bot/{a.bot}/flows", {"name": "من الرابط", "trigger": {"type": "link", "links": [l["code"]]}}).get_json()["flow"]["id"]
        post(a.c, f"/api/bot/{a.bot}/flows/{fid}/save", {"draft": {"start": "a", "nodes": {"a": {"type": "text", "text": "أهلاً من حملة رمضان 🌙"}}}})
        post(a.c, f"/api/bot/{a.bot}/flows/{fid}/publish"); post(a.c, f"/api/bot/{a.bot}/flows/{fid}/toggle", {"active": True})
        self.assertEqual(say(a.bot, peer(), f"مرحبا #{l['code']}")[0], "أهلاً من حملة رمضان 🌙")
        self.assertEqual(post(a.c, f"/api/bot/{a.bot}/flows", {"name": "x", "trigger": {"type": "link", "links": []}}).get_json()["error"], "flow:links")

    def test_permissions(self):
        a = Acct()
        m = user("mem", None)
        db.join_team(a.owner, m, "member")
        self.assertEqual(post(client(m), "/api/growth/links", {"bot": a.bot, "name": "x"}).status_code, 403)
        self.assertEqual(post(client(user("o")), "/api/growth/links", {"bot": a.bot, "name": "x"}).status_code, 404)
        nolink = db.create_bot(a.owner, "WA2", f"wa:{secrets.randbelow(10**12)}", "flow", {}, "whatsapp")
        self.assertEqual(post(a.c, "/api/growth/links", {"bot": nolink, "name": "x"}).get_json()["error"], "bot_link")


AD = {"source_type": "ad", "source_id": "120210000000001", "source_url": "https://fb.me/abc",
      "headline": "عروض العمرة 1448", "body": "احجز الآن", "ctwa_clid": "ARAkLkA8rmlFeiCktEJQ-QTwRiyYHAFDLMNDBH0CD3qpjd0HR4irJ6LEkR7JwFF4XvnO2E4Nx0-eM-GABDLOPaOdRMv-_zfUQ2a"}


class AdTests(unittest.TestCase):
    def test_whatsapp_parses_the_referral(self):
        m = WhatsAppChannel("1", "t")._one({"from": "966500000001", "id": "w1", "type": "text", "text": {"body": "مرحبا"},
                                            "referral": dict(AD, media_type="image", image_url="https://x")}, "Ali")
        self.assertEqual(m["referral"]["source_id"], AD["source_id"])
        self.assertEqual(m["referral"]["ctwa_clid"], AD["ctwa_clid"])
        self.assertNotIn("referral", WhatsAppChannel("1", "t")._one({"from": "1", "id": "w", "type": "text", "text": {"body": "x"}}, ""))

    def test_ad_click_is_recorded_reported_and_triggers_its_flow(self):
        a = Acct()
        fid = post(a.c, f"/api/bot/{a.bot}/flows", {"name": "إعلان العمرة", "trigger": {"type": "ad", "ads": [AD["source_id"], "bad!"]}}).get_json()["flow"]["id"]
        post(a.c, f"/api/bot/{a.bot}/flows/{fid}/save", {"draft": {"start": "q", "nodes": {
            "q": {"type": "ask", "text": "كم شخص؟", "var": "n", "next": None}}}})
        post(a.c, f"/api/bot/{a.bot}/flows/{fid}/publish"); post(a.c, f"/api/bot/{a.bot}/flows/{fid}/toggle", {"active": True})
        self.assertEqual(json.loads(db.get_bot(a.bot)["config_json"])["flows"][0]["trigger"]["ads"], [AD["source_id"]])
        p = peer()
        self.assertEqual(say(a.bot, p, "مرحبا", referral=AD)[0], "كم شخص؟", "نقرة هذا الإعلان تبدأ فلوه")
        say(a.bot, p, "4")
        rep = a.c.get("/api/growth/ads?days=30").get_json()["ads"]
        self.assertEqual((rep[0]["source_id"], rep[0]["people"], rep[0]["leads"], rep[0]["headline"]),
                         (AD["source_id"], 1, 1, "عروض العمرة 1448"))
        src = a.c.get(f"/api/inbox/thread?bot={a.bot}&peer={p}").get_json()["source"]
        self.assertEqual((src["kind"], src["name"]), ("ad", "عروض العمرة 1448"))
        p2 = peer()
        self.assertEqual(say(a.bot, p2, "مرحبا", referral=dict(AD, source_id="999999")), [], "إعلان آخر لا يبدأ هذا الفلو")


class Http:
    def __init__(self, status=200):
        self.calls, self.status = [], status

    def post(self, url, params=None, json=None):
        self.calls.append((url, params, json))
        return type("R", (), {"status_code": self.status, "text": f"bad token {params['access_token']}"})()


class CapiTests(unittest.TestCase):
    def test_settings_hide_the_token_and_validate(self):
        a = Acct()
        tok = "EAAG" + secrets.token_hex(20)
        self.assertEqual(post(a.c, "/api/growth/capi", {"bot": a.bot, "dataset": "abc"}).get_json()["error"], "dataset")
        r = post(a.c, "/api/growth/capi", {"bot": a.bot, "dataset": "1234567890", "token": tok, "lead": True}).get_json()
        b = next(x for x in r["bots"] if x["id"] == a.bot)
        self.assertEqual(b["capi"], {"dataset": "1234567890", "token": True, "lead": True})
        self.assertNotIn(tok, a.c.get("/growth").get_data(as_text=True), "الرمز لا يصل للصفحة")
        self.assertNotIn(tok, a.c.get(f"/bot/{a.bot}").get_data(as_text=True))
        post(a.c, "/api/growth/capi", {"bot": a.bot, "dataset": "1234567890", "lead": True})
        self.assertEqual(json.loads(db.get_bot(a.bot)["config_json"])["capi_token"], tok, "رمز فارغ = يبقى القديم")

    def test_only_ad_customers_are_reported_and_errors_hide_the_token(self):
        a = Acct()
        tok = "EAAG" + secrets.token_hex(20)
        post(a.c, "/api/growth/capi", {"bot": a.bot, "dataset": "1234567890", "token": tok})
        row = db.get_bot(a.bot)
        organic = peer()
        self.assertIsNone(GR.capi_send(row, organic, "Purchase", 100, "SAR", http=Http()), "ليس من إعلان")
        p = peer()
        db.record_ad_referral(a.bot, p, AD)
        h = Http()
        self.assertTrue(GR.capi_send(row, p, "Purchase", 2500, "sar", http=h))
        url, params, body = h.calls[0]
        ev = body["data"][0]
        self.assertEqual(url, "https://graph.facebook.com/v21.0/1234567890/events")
        self.assertEqual((ev["action_source"], ev["messaging_channel"], ev["user_data"]["ctwa_clid"],
                          ev["user_data"]["whatsapp_business_account_id"], ev["custom_data"]),
                         ("business_messaging", "whatsapp", AD["ctwa_clid"], "555000", {"value": 2500.0, "currency": "SAR"}))
        self.assertFalse(GR.capi_send(row, p, "Purchase", http=Http(400)))
        last = db.capi_recent(a.owner, 1)[0]
        self.assertNotIn(tok, last["error"])
        self.assertIsNone(GR.capi_send(row, p, "EvilEvent", http=Http()))

    def test_goal_card_sends_its_event(self):
        a = Acct()
        post(a.c, "/api/growth/capi", {"bot": a.bot, "dataset": "1234567890", "token": "EAAG" + secrets.token_hex(20)})
        sent = []
        orig = GR.capi_async
        GR.capi_async = lambda row, p, ev, val=None, cur=None: sent.append((p, ev, val, cur))
        try:
            fid = post(a.c, f"/api/bot/{a.bot}/flows", {"name": "شراء"}).get_json()["flow"]["id"]
            post(a.c, f"/api/bot/{a.bot}/flows/{fid}/save", {"draft": {"start": "q", "nodes": {
                "q": {"type": "ask", "text": "المبلغ؟", "var": "amount", "validate": "number", "next": "g"},
                "g": {"type": "goal", "name": "paid", "event": "Purchase", "value": "{{amount}}", "currency": "sar"}}}})
            self.assertTrue(post(a.c, f"/api/bot/{a.bot}/flows/{fid}/publish").get_json()["ok"])
            post(a.c, f"/api/bot/{a.bot}/flows/{fid}/toggle", {"active": True})
            p = peer()
            say(a.bot, p, "hi"); say(a.bot, p, "٢٥٠٠")
        finally:
            GR.capi_async = orig
        self.assertEqual(sent, [(p, "Purchase", 2500.0, "SAR")])


if __name__ == "__main__":
    unittest.main(verbosity=2)
