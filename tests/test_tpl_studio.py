"""Template Studio — المرحلة 4: قواعد Meta قبل الإرسال (أنواع custom/carousel/lto/auth) ·
قراءة القالب إلى مواصفة إرسال · البث يرسل الكوبون والعدّاد والموقع والبطاقات · المسارات
(إنشاء بعيّنات، حذف، إرسال تجريبي بنفس قواعد المال) · الصلاحيات.

Meta مُحاكاة بالكامل — لا شبكة.

    python tests/test_tpl_studio.py
"""
import asyncio, itertools, json, os, secrets, sys, tempfile, threading, time, unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_TMPDIR = tempfile.mkdtemp(prefix="botyalla-tpl-")
os.environ["BOTYALLA_DB"] = os.path.join(_TMPDIR, "test.db")   # قبل استيراد database
os.environ["BOTYALLA_UPLOADS"] = _TMPDIR
os.environ["BOTYALLA_LOGS"] = os.path.join(_TMPDIR, "logs")
os.environ["ADMIN_USER"] = "admin"
os.environ["ADMIN_PASS"] = "Tp#" + secrets.token_hex(6)

import auth                                # noqa: E402
import bot_manager                         # noqa: E402
import broadcasts as BC                    # noqa: E402
import database as db                      # noqa: E402
import tpl_studio as TS                    # noqa: E402
import app as web                          # noqa: E402
from channels import whatsapp as W        # noqa: E402

PW = "Str0ng!Pass" + secrets.token_hex(3)
SENT, CREATED, UPLOADS = [], [], []
_IDS = itertools.count(1)
LIVE = []                                  # قوالب «عند Meta» كما تعيدها list_templates


def meta_item(payload, status="APPROVED"):
    comps = payload["components"]
    body = next((c.get("text", "") for c in comps if c["type"] == "BODY"), "")
    return {"name": payload["name"], "language": payload["language"], "status": status,
            "category": payload["category"], "vars": sorted(set(TS.nums(body))), "header_vars": [],
            "header_format": next((c["format"] for c in comps if c["type"] == "HEADER"), ""),
            "body": body, "components": comps, "spec": TS.spec_of(comps)}


class R:
    def __init__(s, c, b): s.status_code, s._b, s.text = c, b, json.dumps(b)
    def json(s): return s._b


async def fake_raw(self, payload):
    SENT.append(payload)
    return R(200, {"messages": [{"id": f"wamid.t{next(_IDS)}"}]})


async def fake_ref(self, asset, bot_id):
    return f"mid-{asset['id']}"


def _boot():
    db.init_db()
    web.seed_platform_defaults(); web.contact_defaults(); web.seed_default_admin()
    web.app.config["TESTING"] = True
    web.WT.list_templates = lambda *a, **k: {"ok": True, "items": LIVE}
    web.WT.create_raw = lambda waba, token, payload: CREATED.append(payload) or {"ok": True, "status": "PENDING"}
    web.WT.delete_template = lambda *a, **k: {"ok": True}
    web.WAC.upload_handle = lambda token, data, mime, name, app_id=None: (UPLOADS.append(mime) or f"h{len(UPLOADS)}", "", "4242")
    W.WhatsAppChannel._raw = fake_raw
    W.WhatsAppChannel.media_ref = fake_ref
    m = bot_manager.BotManager()
    m._thread = threading.Thread(target=m._run, daemon=True); m._thread.start(); m._ready.wait(5)
    BC.configure(manager=m)
    return m


def _user(name, plan="enterprise"):
    uid, err = db.create_account(name, auth.hash_password(PW), f"{name}@example.test", None, 30, "person",
                                 verify_required=False)
    assert not err, err
    db.mark_email_verified(uid)
    if plan:
        db.activate_subscription(uid, plan, 30)
    return uid


def _client(user_id):
    c = web.app.test_client()
    with c.session_transaction() as s:
        u = db.get_user(user_id)
        s.update(_csrf="tk", uid=user_id, uname=u["username"], role=u["role"], pwv=web._pw_stamp(u["pw_hash"]))
    return c


def post(c, url, body=None):
    return c.post(url, data=json.dumps(body or {}), content_type="application/json", headers={"X-CSRF-Token": "tk"})


def asset(owner, kind="image"):
    import asset_store                     # الملف داخل مجلد المكتبة الفعلي كما يحفظه الرفع
    p = asset_store.path_of(f"a{secrets.token_hex(3)}.jpg")
    os.makedirs(os.path.dirname(p), exist_ok=True)
    open(p, "wb").write(b"\xff\xd8\xff" + b"0" * 64)
    return db.add_asset(owner, kind, "image/jpeg" if kind == "image" else "video/mp4", 67, os.path.basename(p))


M = _boot()
OWNER = _user("tp" + secrets.token_hex(3))
BOT = db.create_bot(OWNER, "WA", f"wa:{secrets.randbelow(10**12)}", "store", {}, "whatsapp")
db.update_bot_config(BOT, {"wa_token": "tok", "wa_waba_id": "1009"})
C = _client(OWNER)


def base(**kw):
    d = {"kind": "custom", "name": "umrah_offer", "language": "ar", "category": "MARKETING",
         "body": "أهلاً {{1}}، عروض العمرة لموسم {{2}} متاحة الآن.", "samples": ["أحمد", "1448"],
         "footer": TS.STOP_FOOTER["ar"]}
    d.update(kw)
    return d


class BuildRulesTests(unittest.TestCase):
    def bad(self, code, d, handles=None):
        with self.assertRaises(TS.Invalid) as e:
            TS.build_create(d, handles)
        self.assertTrue(str(e.exception).startswith(code), str(e.exception))

    def test_custom_template_payload(self):
        p, local = TS.build_create(base(header={"format": "TEXT", "text": "عرض {{1}}", "samples": ["خاص"]},
            buttons=[{"type": "URL", "text": "احجز", "url": "https://x.sa/b/{{1}}", "example": "https://x.sa/b/7"},
                     {"type": "QUICK_REPLY", "text": "مهتم"}, {"type": "COPY_CODE", "example": "UMRAH20"}]))
        types = [b["type"] for b in p["components"][-1]["buttons"]]
        self.assertEqual(types, ["QUICK_REPLY", "URL", "COPY_CODE"], "الردود السريعة أولاً (قاعدة Meta)")
        self.assertEqual(p["components"][0]["example"], {"header_text": ["خاص"]})
        self.assertEqual(p["components"][1]["example"], {"body_text": [["أحمد", "1448"]]})
        self.assertEqual(local, {})

    def test_meta_rejection_rules_are_caught_early(self):
        self.bad("name", base(name="Umrah Offer!"))
        self.bad("body:order", base(body="مرحبا {{2}} ثم {{3}} اليوم", samples=["a", "b"]))
        self.bad("body:edge_var", base(body="{{1}} عرضنا", samples=["a"]))
        self.bad("body:samples", base(samples=["أحمد"]))
        self.bad("footer:vars", base(footer="اسمك {{1}}"))
        self.bad("buttons:2:limit", base(buttons=[{"type": "URL", "text": "a", "url": "https://a.sa"}] * 3))
        self.bad("buttons:0:url", base(buttons=[{"type": "URL", "text": "a", "url": "http://a.sa"}]))
        self.bad("buttons:0:url_example", base(buttons=[{"type": "URL", "text": "a", "url": "https://a.sa/{{1}}", "example": "https://evil.x/1"}]))
        self.bad("buttons:0:code", base(buttons=[{"type": "COPY_CODE", "example": "كود"}]))
        self.bad("buttons:0:phone", base(buttons=[{"type": "PHONE_NUMBER", "text": "اتصل", "phone": "0501"}]))
        self.bad("header:media", base(header={"format": "IMAGE"}))
        self.bad("location", base(header={"format": "LOCATION", "location": {"lat": 200, "lng": 1, "name": "x", "address": "y"}}))

    def test_location_pin_is_kept_locally(self):
        _, local = TS.build_create(base(header={"format": "LOCATION", "location":
                                   {"lat": "21.42", "lng": "39.82", "name": "فندق الفرسان", "address": "مكة"}}))
        self.assertEqual(local["location"]["name"], "فندق الفرسان")

    def test_carousel_rules(self):
        card = lambda b: {"body": "غرفة {{1}} مطلّة", "samples": ["مزدوجة"], "buttons": b}
        qr = [{"type": "QUICK_REPLY", "text": "احجز"}]
        d = {"kind": "carousel", "name": "rooms", "language": "ar", "body": "اختر غرفتك", "cards": [card(qr)]}
        self.bad("cards:count", d)
        d["cards"] = [card(qr), card([{"type": "URL", "text": "x", "url": "https://a.sa"}])]
        self.bad("cards:1:shape", d, {"card0": "h", "card1": "h"})
        d["cards"] = [card(qr), card(qr)]
        self.bad("cards:1:media", d, {"card0": "h"})
        p, _ = TS.build_create(d, {"card0": "h0", "card1": "h1"})
        self.assertEqual(len(p["components"][1]["cards"]), 2)
        self.assertEqual(p["category"], "MARKETING")

    def test_lto_rules(self):
        d = {"kind": "lto", "name": "flash", "language": "ar", "offer_text": "ينتهي قريباً",
             "body": "خصم على {{1}} الليلة", "samples": ["الإقامة"], "has_expiration": True,
             "buttons": [{"type": "URL", "text": "احجز", "url": "https://a.sa"}]}
        self.bad("buttons:code_required", d)
        d["buttons"].append({"type": "COPY_CODE", "example": "FLASH20"})
        p, _ = TS.build_create(d)
        self.assertEqual([b["type"] for b in p["components"][-1]["buttons"]], ["COPY_CODE", "URL"])
        self.assertFalse(any(c["type"] == "FOOTER" for c in p["components"]), "لا تذييل في هذا النوع")
        self.bad("lto:too_long", dict(d, offer_text="x" * 17))

    def test_auth_payload(self):
        p, _ = TS.build_create({"kind": "auth", "name": "otp", "language": "en", "code_expiration_minutes": 5})
        self.assertEqual(p["category"], "AUTHENTICATION")
        self.assertEqual(TS.spec_of(p["components"])["kind"], "auth")


class SendSpecTests(unittest.TestCase):
    def test_lto_coupon_and_url_parameters(self):
        p, _ = TS.build_create({"kind": "lto", "name": "f", "language": "ar", "offer_text": "قريباً",
                                "body": "عرض {{1}} لك", "samples": ["x"], "has_expiration": True,
                                "buttons": [{"type": "COPY_CODE", "example": "A1"},
                                            {"type": "URL", "text": "احجز", "url": "https://a.sa/{{1}}", "example": "https://a.sa/1"}]})
        spec = TS.spec_of(p["components"])
        comps = TS.send_components(spec, body=["خاص"], url_values={1: "abc"}, coupon="LIVE99", expire_ms=1_900_000_000_000)
        types = [(c["type"], c.get("sub_type")) for c in comps]
        self.assertIn(("limited_time_offer", None), types)
        self.assertIn(("button", "copy_code"), types)
        self.assertIn(("button", "url"), types)
        code = next(c for c in comps if c.get("sub_type") == "copy_code")["parameters"][0]
        self.assertEqual(code, {"type": "coupon_code", "coupon_code": "LIVE99"})


class RouteTests(unittest.TestCase):
    def setUp(self):
        CREATED.clear(); UPLOADS.clear(); SENT.clear(); LIVE.clear()
        web._login_attempts.clear()

    def test_create_uploads_samples_then_submits(self):
        a1, a2 = asset(OWNER), asset(OWNER)
        r = post(C, "/api/templates", {"bot_id": BOT, "kind": "carousel", "name": "rooms", "language": "ar",
                 "body": "اختر غرفتك", "card_format": "IMAGE",
                 "cards": [{"asset_id": a, "body": "غرفة رقم 1", "buttons": [{"type": "QUICK_REPLY", "text": "احجز"}]}
                           for a in (a1, a2)]}).get_json()
        self.assertTrue(r["ok"], r)
        self.assertEqual(len(UPLOADS), 2)
        self.assertEqual(CREATED[0]["components"][1]["cards"][0]["components"][0]["example"]["header_handle"], ["h1"])
        cfg = json.loads(db.get_bot(BOT)["config_json"])
        self.assertEqual(cfg.get("wa_app_id"), "4242", "App ID يُحفظ للمرة التالية")
        self.assertEqual((cfg.get("wa_token"), cfg.get("wa_waba_id")), ("tok", "1009"),
                         "حفظ App ID لا يمسح توكن واتساب ولا الـWABA")

    def test_invalid_template_uploads_nothing(self):
        r = post(C, "/api/templates", {"bot_id": BOT, **base(body="{{1}} عرض", samples=["x"])}).get_json()
        self.assertEqual(r["error"], "body:edge_var")
        self.assertEqual((UPLOADS, CREATED), ([], []))

    def test_foreign_media_is_refused(self):
        other = _user("ot" + secrets.token_hex(3))
        r = post(C, "/api/templates", {"bot_id": BOT, **base(header={"format": "IMAGE", "asset_id": asset(other)})}).get_json()
        self.assertEqual(r["error"], "header:media")
        self.assertEqual(UPLOADS, [])

    def test_members_cannot_create_or_delete(self):
        m = _user("mm" + secrets.token_hex(3), plan=None)
        self.assertEqual(db.join_team(OWNER, m, "member"), "")
        self.assertEqual(post(_client(m), "/api/templates", base(bot_id=BOT)).status_code, 403)
        self.assertEqual(post(_client(m), "/api/templates/delete", {"bot_id": BOT, "name": "x"}).status_code, 403)

    def test_location_template_sends_its_pin(self):
        d = base(name="visit_us", header={"format": "LOCATION", "location":
                 {"lat": 21.42, "lng": 39.82, "name": "فندق الفرسان", "address": "مكة"}}, category="UTILITY")
        self.assertTrue(post(C, "/api/templates", {"bot_id": BOT, **d}).get_json()["ok"])
        LIVE.append(meta_item(CREATED[-1]))
        r = post(C, "/api/templates/test", {"bot_id": BOT, "template": "visit_us", "lang": "ar", "phones": ["0500000001"],
                 "vars": [{"src": "text", "text": "a"}, {"src": "text", "text": "b"}]}).get_json()
        self.assertTrue(r["ok"], r)
        M.join_campaigns(10)
        head = SENT[-1]["template"]["components"][0]
        self.assertEqual(head["parameters"][0]["location"]["name"], "فندق الفرسان")


class BroadcastIntegrationTests(unittest.TestCase):
    """البث (المرحلة 3) يرسل الأنواع الجديدة بقيمها ويرفض ما ينقصها."""

    @classmethod
    def setUpClass(cls):
        db.wallet_topup(OWNER, 1_000_000)
        LIVE.clear()
        p, _ = TS.build_create({"kind": "lto", "name": "flash", "language": "ar", "offer_text": "قريباً",
                                "body": "عرض {{1}} لك", "samples": ["x"], "has_expiration": True,
                                "buttons": [{"type": "COPY_CODE", "example": "A1"},
                                            {"type": "URL", "text": "احجز", "url": "https://a.sa/{{1}}", "example": "https://a.sa/1"}]})
        cls.lto = meta_item(p)
        card = {"body": "غرفة {{1}} مميزة", "samples": ["x"], "buttons": [{"type": "QUICK_REPLY", "text": "احجز"}]}
        p2, _ = TS.build_create({"kind": "carousel", "name": "rooms", "language": "ar", "body": "اختر",
                                 "cards": [card, card]}, {"card0": "h", "card1": "h"})
        cls.car = meta_item(p2)
        db.save_contact(OWNER, {"name": "Ali", "phone": "+966500000099", "optin": 1})

    def setUp(self):
        LIVE[:] = [self.lto, self.car]
        SENT.clear()
        web._login_attempts.clear()

    def send(self, **kw):
        d = {"bot_id": BOT, "lang": "ar", "audience": {"type": "all"}, "policy_optin": True}
        d.update(kw)
        return post(C, "/api/broadcasts", d).get_json()

    def test_lto_needs_code_and_future_expiry_then_sends_them(self):
        v = [{"src": "contact", "field": "name"}]
        url = {"1": {"src": "text", "text": "ali"}}
        self.assertEqual(self.send(template="flash", vars=v, url=url, expire_at=int(time.time()) + 3600)["error"], "coupon")
        self.assertEqual(self.send(template="flash", vars=v, url=url, coupon="LIVE99",
                                   expire_at=int(time.time()) + 60)["error"], "expire_at")
        r = self.send(template="flash", vars=v, url=url, coupon="LIVE99", expire_at=int(time.time()) + 7200)
        self.assertTrue(r["ok"], r)
        M.join_campaigns(10)
        comps = SENT[-1]["template"]["components"]
        self.assertIn("limited_time_offer", [c["type"] for c in comps])
        self.assertEqual(next(c for c in comps if c.get("sub_type") == "url")["parameters"][0]["text"], "ali")

    def test_carousel_needs_owned_media_per_card(self):
        a = asset(OWNER)
        cards = [{"asset_id": a, "vars": [{"src": "text", "text": "مزدوجة"}]}] * 2
        self.assertEqual(self.send(template="rooms", cards=cards[:1])["error"], "cards")
        other = asset(_user("o2" + secrets.token_hex(3)))
        self.assertEqual(self.send(template="rooms", cards=[{"asset_id": other, "vars": cards[0]["vars"]}] * 2)["error"], "card_media")
        r = self.send(template="rooms", cards=cards)
        self.assertTrue(r["ok"], r)
        M.join_campaigns(10)
        car = next(c for c in SENT[-1]["template"]["components"] if c["type"] == "carousel")
        self.assertEqual([c["card_index"] for c in car["cards"]], [0, 1])
        self.assertEqual(car["cards"][0]["components"][0]["parameters"][0]["image"]["id"], f"mid-{a}")

    def test_auth_templates_are_not_broadcast(self):
        p, _ = TS.build_create({"kind": "auth", "name": "otp", "language": "ar"})
        LIVE.append(dict(meta_item(p), vars=[]))
        self.assertEqual(self.send(template="otp", vars=[])["error"], "template_auth")


if __name__ == "__main__":
    unittest.main(verbosity=2)
