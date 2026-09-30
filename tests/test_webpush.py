"""الإشعارات الفورية وتطبيق الهاتف: تشفير RFC 8291 يُفكّ فعلاً · توقيع VAPID صحيح · لا SSRF ·
اشتراك الجهاز لصاحبه · الإشعار يصل أجهزة صاحبه وحده · المنتهي يُحذف · من يُنبَّه بمحادثة
(نفس رؤية صندوق الوارد) · عامل الخدمة والبيان وصفحة offline."""
import base64, json, os, secrets, sys, tempfile, time, unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_TMPDIR = tempfile.mkdtemp(prefix="botyalla-push-")
os.environ["BOTYALLA_DB"] = os.path.join(_TMPDIR, "test.db")   # قبل استيراد database
os.environ["BOTYALLA_UPLOADS"] = _TMPDIR
os.environ["BOTYALLA_LOGS"] = os.path.join(_TMPDIR, "logs")
os.environ["ADMIN_USER"] = "admin"
os.environ["ADMIN_PASS"] = "Wp#" + secrets.token_hex(6)
os.environ.pop("VAPID_PRIVATE_KEY", None)

from cryptography.hazmat.primitives import hashes, serialization     # noqa: E402
from cryptography.hazmat.primitives.asymmetric import ec             # noqa: E402
from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature  # noqa: E402
from cryptography.hazmat.primitives.ciphers.aead import AESGCM       # noqa: E402
from cryptography.hazmat.primitives.kdf.hkdf import HKDF             # noqa: E402

import auth                                # noqa: E402
import database as db                      # noqa: E402
import app as web                          # noqa: E402
import webpush as WP                       # noqa: E402
import inbox_relay as IR                   # noqa: E402

PW = "Str0ng!Pass" + secrets.token_hex(3)
db.init_db(); web.seed_platform_defaults(); web.contact_defaults(); web.seed_default_admin()
web.app.config["TESTING"] = True
db.NOTIFY_HOOKS.clear()                    # الاختبارات تستدعي deliver مباشرة — لا خيط خلفي


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


def post(c, url, body=None, csrf=True):
    return c.post(url, data=json.dumps(body or {}), content_type="application/json",
                  headers={"X-CSRF-Token": "tk"} if csrf else {})


class Device:
    """متصفح وهمي: زوج مفاتيح P-256 + سرّ auth — يفكّ ما يرسله الخادم كما يفعل المتصفح."""
    def __init__(self):
        self.key = ec.generate_private_key(ec.SECP256R1())
        self.pub = self.key.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
        self.auth = os.urandom(16)
        self.endpoint = "https://fcm.googleapis.com/fcm/send/" + secrets.token_urlsafe(24)

    def sub(self):
        return {"endpoint": self.endpoint, "keys": {"p256dh": WP.b64u(self.pub), "auth": WP.b64u(self.auth)}}

    def decrypt(self, body):
        salt, rs, idlen = body[:16], int.from_bytes(body[16:20], "big"), body[20]
        as_pub = body[21:21 + idlen]
        ct = body[21 + idlen:]
        shared = self.key.exchange(ec.ECDH(), ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), as_pub))
        ikm = HKDF(hashes.SHA256(), 32, salt=self.auth, info=b"WebPush: info\x00" + self.pub + as_pub).derive(shared)
        cek = HKDF(hashes.SHA256(), 16, salt=salt, info=b"Content-Encoding: aes128gcm\x00").derive(ikm)
        nonce = HKDF(hashes.SHA256(), 12, salt=salt, info=b"Content-Encoding: nonce\x00").derive(ikm)
        plain = AESGCM(cek).decrypt(nonce, ct, None)
        assert rs == 4096 and plain.endswith(b"\x02")
        return plain[:-1]


class Wire:
    """خدمة دفع وهمية: تلتقط الطلبات وترد بالحالة المطلوبة."""
    def __init__(self, code=201):
        self.code, self.calls = code, []

    def __call__(self, url, headers, body):
        self.calls.append((url, headers, body))
        return self.code


class CryptoTests(unittest.TestCase):
    def test_payload_round_trips_through_rfc8291(self):
        d = Device()
        msg = json.dumps({"t": "مرحبا", "b": "x" * 500}, ensure_ascii=False).encode()
        self.assertEqual(d.decrypt(WP.encrypt(WP.b64u(d.pub), WP.b64u(d.auth), msg)), msg)

    def test_vapid_jwt_is_signed_by_the_published_key_for_the_push_origin(self):
        h = WP.vapid_header("https://fcm.googleapis.com/fcm/send/abc")
        t = h.split("t=")[1].split(",")[0]
        k = h.split("k=")[1]
        self.assertEqual(k, WP.public_key())
        head, body, sig = t.split(".")
        claims = json.loads(WP.ub64u(body))
        self.assertEqual(claims["aud"], "https://fcm.googleapis.com")
        self.assertTrue(claims["sub"].startswith("mailto:"))
        self.assertGreater(claims["exp"], time.time())
        raw = WP.ub64u(sig)
        pub = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), WP.ub64u(k))
        pub.verify(encode_dss_signature(int.from_bytes(raw[:32], "big"), int.from_bytes(raw[32:], "big")),
                   f"{head}.{body}".encode(), ec.ECDSA(hashes.SHA256()))       # يرمي لو التوقيع خاطئ

    def test_key_is_generated_once_and_stored_sealed(self):
        stored = db.get_platform("vapid_private")
        self.assertTrue(stored)
        self.assertNotIn(WP.b64u(WP._private().private_numbers().private_value.to_bytes(32, "big")), stored)

    def test_only_known_push_services(self):
        ok = ["https://fcm.googleapis.com/fcm/send/x", "https://updates.push.services.mozilla.com/wpush/v2/x",
              "https://web.push.apple.com/QK", "https://wns2-par02p.notify.windows.com/w/?token=x"]
        bad = ["http://fcm.googleapis.com/x", "https://evil.com/x", "https://fcm.googleapis.com.evil.com/x",
               "https://user:pw@fcm.googleapis.com/x", "https://fcm.googleapis.com:8443/x", "https://127.0.0.1/x",
               "https://localhost/x", "javascript:alert(1)", ""]
        for u in ok:
            self.assertTrue(WP.endpoint_ok(u), u)
        for u in bad:
            self.assertFalse(WP.endpoint_ok(u), u)


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.u = user("pu")
        self.c = client(self.u)

    def test_subscribe_validates_and_is_per_user(self):
        d = Device()
        self.assertEqual(post(self.c, "/api/push/subscribe", d.sub(), csrf=False).status_code, 400)   # CSRF
        self.assertEqual(web.app.test_client().post("/api/push/subscribe").status_code in (302, 400, 401), True)
        bad = dict(d.sub(), endpoint="https://evil.com/steal")
        self.assertEqual(post(self.c, "/api/push/subscribe", bad).get_json()["error"], "endpoint")
        badk = d.sub(); badk["keys"]["p256dh"] = "AAAA"
        self.assertEqual(post(self.c, "/api/push/subscribe", badk).get_json()["error"], "keys")
        self.assertTrue(post(self.c, "/api/push/subscribe", d.sub()).get_json()["ok"])
        self.assertEqual(len(db.list_push_subs(self.u)), 1)
        self.assertTrue(post(self.c, "/api/push/subscribe", d.sub()).get_json()["ok"])     # نفس الجهاز لا يتكرر
        self.assertEqual(len(db.list_push_subs(self.u)), 1)
        other = user("po")
        post(client(other), "/api/push/unsubscribe", {"endpoint": d.endpoint})               # لا يحذف جهاز غيره
        self.assertEqual(len(db.list_push_subs(self.u)), 1)
        post(self.c, "/api/push/unsubscribe", {"endpoint": d.endpoint})
        self.assertEqual(db.list_push_subs(self.u), [])

    def test_logout_stops_this_devices_alerts(self):
        d = Device()
        self.assertTrue(post(self.c, "/api/push/subscribe", d.sub()).get_json()["ok"])
        other = Device()                                      # جهاز آخر للمستخدم نفسه يبقى
        db.save_push_sub(self.u, other.endpoint, other.sub()["keys"]["p256dh"], other.sub()["keys"]["auth"])
        self.c.post("/logout", data={"csrf_token": "tk"})
        self.assertEqual([s["endpoint"] for s in db.list_push_subs(self.u)], [other.endpoint])

    def test_key_endpoint(self):
        r = self.c.get("/api/push/key").get_json()
        self.assertEqual((r["ok"], r["key"]), (True, WP.public_key()))
        self.assertEqual(len(WP.ub64u(r["key"])), 65)


class DeliveryTests(unittest.TestCase):
    def setUp(self):
        self.u = user("dl")
        self.d = Device()
        db.save_push_sub(self.u, self.d.endpoint, self.d.sub()["keys"]["p256dh"], self.d.sub()["keys"]["auth"])
        WP.HTTP = self.wire = Wire(201)

    def tearDown(self):
        WP.HTTP = None

    def test_notification_reaches_only_its_owners_devices_in_their_language(self):
        stranger = user("st"); sd = Device()
        db.save_push_sub(stranger, sd.endpoint, sd.sub()["keys"]["p256dh"], sd.sub()["keys"]["auth"])
        db.set_setting(self.u, "lang", "en")
        n = {"id": 7, "user_id": self.u, "kind": "paid", "data": {"amount": "SAR 50", "name": "Ali"}, "url": "/payments", "created_at": int(time.time())}
        self.assertEqual(WP.deliver(n), 1)
        (url, headers, body), = self.wire.calls
        self.assertEqual(url, self.d.endpoint)
        self.assertEqual(headers["Content-Encoding"], "aes128gcm")
        self.assertTrue(headers["Authorization"].startswith("vapid t="))
        p = json.loads(self.d.decrypt(body))
        self.assertEqual((p["t"], p["u"], p["id"], p["lang"]), ("💳 New payment received", "/payments", 7, "en"))
        self.assertIn("Ali", p["b"])

    def test_urgent_kinds_and_url_is_always_local(self):
        n = {"id": 1, "user_id": self.u, "kind": "call", "data": {"name": "منى"}, "url": "//evil.com/x", "created_at": int(time.time())}
        WP.deliver(n)
        _, headers, body = self.wire.calls[-1]
        p = json.loads(self.d.decrypt(body))
        self.assertEqual((headers["Urgency"], headers["TTL"], p["ri"], p["u"]), ("high", "60", True, "/home"))
        self.assertIn("منى", p["b"])

    def test_gone_subscription_is_removed_and_repeated_failures_drop_it(self):
        self.wire.code = 410
        WP.deliver({"id": 1, "user_id": self.u, "kind": "test", "data": {}, "url": "/home", "created_at": 1})
        self.assertEqual(db.list_push_subs(self.u), [])
        db.save_push_sub(self.u, self.d.endpoint, self.d.sub()["keys"]["p256dh"], self.d.sub()["keys"]["auth"])
        self.wire.code = 500
        for i in range(4):
            WP.deliver({"id": 1, "user_id": self.u, "kind": "test", "data": {}, "url": "/home", "created_at": 1})
        self.assertEqual(db.list_push_subs(self.u)[0]["fails"], 4)
        WP.deliver({"id": 1, "user_id": self.u, "kind": "test", "data": {}, "url": "/home", "created_at": 1})
        self.assertEqual(db.list_push_subs(self.u), [])

    def test_every_stored_notification_is_queued_by_the_hook(self):
        got = []
        db.NOTIFY_HOOKS.append(got.append)
        try:
            db.notify(self.u, "ticket_reply", {"subject": "S"}, "/support")
        finally:
            db.NOTIFY_HOOKS.remove(got.append)
        self.assertEqual((got[0]["user_id"], got[0]["kind"], got[0]["url"]), (self.u, "ticket_reply", "/support"))
        self.assertTrue(got[0]["id"])

    def test_test_endpoint_reports_devices(self):
        r = post(client(self.u), "/api/push/test").get_json()
        self.assertEqual((r["ok"], r["sent"]), (True, 1))
        self.assertEqual(json.loads(self.d.decrypt(self.wire.calls[-1][2]))["k"], "test")


class RecipientTests(unittest.TestCase):
    """من يُنبَّه بمحادثة تحتاج تدخّلاً = من يراها في صندوق الوارد."""
    @classmethod
    def setUpClass(cls):
        cls.owner = user("ow")
        cls.m1, cls.m2, cls.adm = user("m1", None), user("m2", None), user("ad", None)
        db.join_team(cls.owner, cls.m1, "member"); db.join_team(cls.owner, cls.m2, "member"); db.join_team(cls.owner, cls.adm, "admin")
        cls.bot = db.create_bot(cls.owner, "Hotel", f"wa:{secrets.randbelow(10**12)}", "flow", {"business_name": "الفرسان"}, "whatsapp")
        cls.row = db.get_bot(cls.bot)

    def kinds(self, u):
        return [(n["kind"], n["data"].get("why"), n["url"]) for n in db.list_notifications(u)[0]]

    def test_unassigned_goes_to_the_whole_team_with_the_customer_text(self):
        peer = "wa:966500000101"
        db.log_message(self.bot, peer, "in", "customer", "أبغى أحجز غرفة", name="أحمد")
        IR.notify_platform(self.row, peer, "needs_support")
        for u in (self.owner, self.m1, self.m2, self.adm):
            self.assertIn("attention", [k for k, *_ in self.kinds(u)])
        n = db.list_notifications(self.m1)[0][0]
        self.assertEqual((n["data"]["name"], n["data"]["bot"], n["data"]["text"]), ("أحمد", "الفرسان", "أبغى أحجز غرفة"))
        self.assertTrue(n["url"].startswith(f"/inbox?bot={self.bot}&peer="))
        IR.notify_platform(self.row, peer, "needs_support")          # خلال 20 دقيقة: لا تكرار
        self.assertEqual(sum(1 for k in self.kinds(self.m1) if k[1] == "needs_support"), 1)

    def test_assigned_goes_to_the_assignee_only(self):
        peer = "wa:966500000102"
        db.log_message(self.bot, peer, "in", "customer", "مرحبا")
        db.assign_conversation(self.bot, peer, self.m2, actor=self.owner)
        before = {u: len(self.kinds(u)) for u in (self.owner, self.m1, self.adm)}
        IR.notify_platform(self.row, peer, "human_msg")
        self.assertIn(("attention", "human_msg"), [(k, w) for k, w, _ in self.kinds(self.m2)])
        for u, n in before.items():
            self.assertEqual(len(self.kinds(u)), n, u)

    def test_team_conversation_skips_members_outside_the_team(self):
        tid, err = db.save_inbox_team(self.owner, None, "Reception", "manual", [self.m1])
        self.assertFalse(err)
        peer = "wa:966500000103"
        db.log_message(self.bot, peer, "in", "customer", "hi")
        db.assign_conversation(self.bot, peer, None, team_id=tid, takeover=False)
        IR.notify_platform(self.row, peer, "handoff")
        whys = lambda u: [w for _, w, url in self.kinds(u) if peer.split(":")[1] in url]
        self.assertEqual(whys(self.m1), ["handoff"])
        self.assertEqual(whys(self.adm), ["handoff"])
        self.assertEqual(whys(self.owner), ["handoff"])
        self.assertEqual(whys(self.m2), [])

    def test_non_crm_plans_link_to_the_bot_inbox(self):
        solo = user("so", "starter")
        b = db.create_bot(solo, "S", "123:ABC" + secrets.token_hex(4), "flow", {}, "telegram")
        db.log_message(b, "tg:555", "in", "customer", "hey")
        IR.notify_platform(db.get_bot(b), "tg:555", "handoff")
        self.assertEqual(db.list_notifications(solo)[0][0]["url"], f"/bot/{b}/inbox?peer=tg%3A555")


class AppShellTests(unittest.TestCase):
    def test_service_worker_offline_and_manifest(self):
        c = web.app.test_client()
        r = c.get("/sw.js")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.headers["Service-Worker-Allowed"], "/")
        self.assertIn("no-cache", r.headers["Cache-Control"])
        self.assertIn(b"showNotification", r.get_data())
        r.close()
        o = c.get("/offline")
        self.assertEqual(o.status_code, 200)
        o.close()
        m = c.get("/site.webmanifest").get_json(force=True)
        self.assertEqual((m["id"], m["display"], m["scope"]), ("/home", "standalone", "/"))
        self.assertTrue(m["start_url"].startswith("/home"))
        self.assertGreaterEqual(len(m["shortcuts"]), 2)
        self.assertTrue(any(i.get("purpose") == "maskable" for i in m["icons"]))

    def test_console_pages_link_the_manifest(self):
        u = user("sh")
        html = client(u).get("/dashboard").get_data(as_text=True)     # /home يحوّل حساباً بلا بوتات إلى هنا
        for s in ('rel="manifest"', "apple-touch-icon", "viewport-fit=cover", "apple-mobile-web-app-capable"):
            self.assertIn(s, html)


if __name__ == "__main__":
    unittest.main(verbosity=2)
