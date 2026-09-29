"""مكالمات واتساب (المرحلة 8): ويبهوك الرنين ⇒ الصندوق ⇒ موظف واحد يرد (WebRTC) ⇒ المدة أو «فائتة».

Meta محاكاة (`calling._post`) — لا شبكة. القاعدة والملفات في مجلد مؤقت.
"""
import hashlib, hmac, json, os, secrets, sys, tempfile, time, unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_TMPDIR = tempfile.mkdtemp(prefix="botyalla-calls-")
os.environ["BOTYALLA_DB"] = os.path.join(_TMPDIR, "test.db")   # قبل استيراد database
os.environ["BOTYALLA_UPLOADS"] = _TMPDIR
os.environ["BOTYALLA_LOGS"] = os.path.join(_TMPDIR, "logs")
os.environ["ADMIN_USER"] = "admin"
os.environ["ADMIN_PASS"] = "Cl#" + secrets.token_hex(6)

import auth                                # noqa: E402
import calling as CALLS                    # noqa: E402
import database as db                      # noqa: E402
import app as web                          # noqa: E402

PW = "Str0ng!Pass" + secrets.token_hex(3)
db.init_db(); web.seed_platform_defaults(); web.contact_defaults(); web.seed_default_admin()
web.app.config["TESTING"] = True
APP_SECRET = "app-" + secrets.token_hex(8)
db.set_platform("wa_app_secret", APP_SECRET)

META, SENT = [], []


def fake_post(bot_row, path, body):
    META.append((path, body.get("action") or body.get("type") or body))
    return {"calls": [{"id": "wacid.out" + secrets.token_hex(4)}]} if body.get("action") == "connect" else {"success": True}


CALLS._post = fake_post
CALLS.HOOKS["send"] = lambda bot, peer, text: SENT.append((peer, text))
OFFER = "v=0\r\no=- 1 2 IN IP4 127.0.0.1\r\ns=-\r\nm=audio 9 UDP/TLS/RTP/SAVPF 111\r\n"
ANSWER = "v=0\r\no=- 3 4 IN IP4 127.0.0.1\r\ns=-\r\nm=audio 9 UDP/TLS/RTP/SAVPF 111\r\n"


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


def hook(phone_id, calls, name="منى"):
    body = json.dumps({"object": "whatsapp_business_account", "entry": [{"id": "WABA", "changes": [{"field": "calls", "value": {
        "messaging_product": "whatsapp", "metadata": {"phone_number_id": phone_id},
        "contacts": [{"profile": {"name": name}, "wa_id": c.get("from")} for c in calls[:1]], "calls": calls}}]}]}).encode()
    sig = "sha256=" + hmac.new(APP_SECRET.encode(), body, hashlib.sha256).hexdigest()
    return web.app.test_client().post("/wh/whatsapp", data=body, content_type="application/json", headers={"X-Hub-Signature-256": sig})


class Acct:
    def __init__(self):
        self.owner = user("cl")
        self.c = client(self.owner)
        self.phone = str(10**14 + secrets.randbelow(10**13))
        self.bot = db.create_bot(self.owner, "WA", f"wa:{self.phone}", "flow", {"wa_token": "EAA-x"}, "whatsapp")
        db.set_bot_active(self.bot, True)                  # رقم متوقّف لا يرنّ عند الفريق
        self.cust = f"9665{secrets.randbelow(10**8):08d}"

    def ring(self, cid):
        return hook(self.phone, [{"id": cid, "from": self.cust, "event": "connect", "direction": "USER_INITIATED",
                                  "timestamp": "1", "session": {"sdp_type": "offer", "sdp": OFFER}}])

    def end(self, cid, duration=0):
        return hook(self.phone, [{"id": cid, "from": self.cust, "event": "terminate", "status": ["Completed"], "duration": duration}])


def texts(bot, peer):
    with db.get_conn() as c:
        return [r[0] for r in c.execute("SELECT text FROM messages WHERE bot_id=? AND peer=? ORDER BY id", (bot, peer))]


class CallTests(unittest.TestCase):
    def test_ring_answer_once_and_duration(self):
        a = Acct()
        cid = "wacid." + secrets.token_hex(8)
        self.assertEqual(a.ring(cid).status_code, 200)
        a.ring(cid)                                                          # Meta تعيد الحدث
        calls = a.c.get("/api/calls/ringing").get_json()["calls"]
        self.assertEqual(len(calls), 1)
        self.assertEqual((calls[0]["name"], calls[0]["sdp"], calls[0]["status"]), ("منى", OFFER, "ringing"))
        self.assertEqual(post(a.c, f"/api/calls/{cid}/answer", {"sdp": "bad"}).get_json()["error"], "sdp")
        META.clear()
        self.assertTrue(post(a.c, f"/api/calls/{cid}/answer", {"sdp": ANSWER}).get_json()["ok"])
        self.assertEqual([x[1] for x in META], ["pre_accept", "accept"])
        self.assertEqual(post(a.c, f"/api/calls/{cid}/answer", {"sdp": ANSWER}).get_json()["error"], "taken", "موظف واحد فقط")
        self.assertEqual(db.get_conversation(a.bot, "wa:" + a.cust)["mode"], "human")
        a.end(cid, 65)
        a.end(cid, 65)
        self.assertEqual(texts(a.bot, "wa:" + a.cust), ["📞 مكالمة واردة", "📞 مكالمة — 1:05"])
        self.assertEqual(db.get_call(cid)["sdp"], "", "العرض يُمسح بعد الانتهاء")
        self.assertEqual(a.c.get("/api/calls/ringing").get_json()["calls"], [])

    def test_missed_call_message_and_settings(self):
        a = Acct()
        META.clear()
        r = post(a.c, "/api/calls/settings", {"bot": a.bot, "enabled": True, "missed_text": "فاتتنا مكالمتك 🙏 اكتب لنا هنا"})
        self.assertTrue(r.get_json()["ok"])
        self.assertEqual(META[-1][0], "settings")
        self.assertEqual(json.loads(db.get_bot(a.bot)["config_json"])["calls"]["enabled"], True)
        self.assertEqual(json.loads(db.get_bot(a.bot)["config_json"])["wa_token"], "EAA-x", "الإعداد الكامل محفوظ")
        cid = "wacid." + secrets.token_hex(8)
        a.ring(cid)
        SENT.clear()
        a.end(cid)
        self.assertEqual(texts(a.bot, "wa:" + a.cust)[-1], "📞 مكالمة فائتة")
        self.assertEqual(SENT, [("wa:" + a.cust, "فاتتنا مكالمتك 🙏 اكتب لنا هنا")])

    def test_reject_sweep_and_access(self):
        a = Acct()
        cid = "wacid." + secrets.token_hex(8)
        a.ring(cid)
        other = Acct()
        self.assertEqual(post(other.c, f"/api/calls/{cid}/answer", {"sdp": ANSWER}).status_code, 404, "حساب آخر")
        self.assertEqual(other.c.get("/api/calls/ringing").get_json()["calls"], [])
        META.clear()
        self.assertTrue(post(a.c, f"/api/calls/{cid}/reject").get_json()["ok"])
        self.assertEqual(META[-1][1], "reject")
        cid2 = "wacid." + secrets.token_hex(8)
        a.ring(cid2)
        with db.get_conn() as c:
            c.execute("UPDATE wa_calls SET created_at=? WHERE call_id=?", (int(time.time()) - 600, cid2))
        CALLS.sweep()
        self.assertEqual(db.get_call(cid2)["status"], "missed", "ويبهوك الانتهاء ضاع ⇒ فائتة")
        free = user("free", plan=None)
        self.assertIn(client(free).get("/api/calls/ringing").status_code, (302, 403))

    def test_answer_failure_returns_call_to_ringing(self):
        a = Acct()
        cid = "wacid." + secrets.token_hex(8)
        a.ring(cid)
        orig = CALLS._post

        def boom(bot_row, path, body):
            raise CALLS.CallError("(#138006) call not found")
        CALLS._post = boom
        try:
            r = post(a.c, f"/api/calls/{cid}/answer", {"sdp": ANSWER}).get_json()
        finally:
            CALLS._post = orig
        self.assertEqual(r["error"], "meta")
        self.assertEqual(db.get_call(cid)["status"], "ringing", "زميل آخر يقدر يرد")
        CALLS._post = boom
        try:
            self.assertEqual(post(a.c, f"/api/calls/{cid}/reject").get_json()["error"], "meta")
        finally:
            CALLS._post = orig
        self.assertEqual(db.get_call(cid)["status"], "ringing", "رفض لم تقبله Meta = ما زالت ترنّ")


class OutboundTests(unittest.TestCase):
    def test_permission_then_dial_answer_and_duration(self):
        import asyncio
        import flow_engine as FE
        from channels.whatsapp import WhatsAppChannel
        a = Acct()
        peer = "wa:" + a.cust
        db.add_bot_user(a.bot, int(a.cust), "منى", peer=peer)
        db.log_message(a.bot, peer, "in", "customer", "مرحبا", name="منى")
        db.touch_bot_user(a.bot, peer)
        post(a.c, "/api/calls/settings", {"bot": a.bot, "enabled": True})
        self.assertEqual(a.c.get(f"/api/calls/permission?bot={a.bot}&peer={peer}").get_json(), {"ok": True, "enabled": True, "status": "none"})
        self.assertEqual(post(a.c, "/api/calls/start", {"bot": a.bot, "peer": peer, "sdp": OFFER}).get_json()["error"], "permission")
        META.clear()
        self.assertTrue(post(a.c, "/api/calls/permission", {"bot": a.bot, "peer": peer}).get_json()["ok"])
        self.assertEqual(META[-1], ("messages", "interactive"))
        # ردّ العميل «السماح» كما يصل من Meta ⇒ يُحفظ ولا يمرّ بالفلو
        ch = WhatsAppChannel(a.phone, "EAA-x")
        msg = ch._one({"from": a.cust, "id": "wamid.p1", "type": "interactive", "interactive": {
            "type": "call_permission_reply", "call_permission_reply": {"response": "accept", "is_permanent": False,
                                                                       "expiration_timestamp": int(time.time()) + 86400}}}, "منى")
        self.assertEqual(msg["kind"], "call_permission")

        class Silent:
            phone_id, page_id, out = a.phone, None, []

            async def send_text(self, p, t):
                Silent.out.append(t); return {"messages": [{}]}
        asyncio.run(FE.handle_message(db.get_bot(a.bot), Silent(), msg))
        self.assertEqual(Silent.out, [], "لا رد آلي على إذن الاتصال")
        self.assertEqual(a.c.get(f"/api/calls/permission?bot={a.bot}&peer={peer}").get_json()["status"], "granted")
        r = post(a.c, "/api/calls/start", {"bot": a.bot, "peer": peer, "sdp": OFFER}).get_json()
        self.assertTrue(r["ok"], r)
        cid = r["id"]
        self.assertEqual(post(a.c, "/api/calls/start", {"bot": a.bot, "peer": peer, "sdp": OFFER}).get_json()["error"], "busy")
        mine = a.c.get("/api/calls/ringing").get_json()["calls"]
        self.assertEqual([(c["id"], c["status"], c["dir"], c["answer"]) for c in mine], [(cid, "dialing", "out", "")])
        other = Acct()
        self.assertEqual(post(other.c, f"/api/calls/{cid}/hangup").status_code, 404)
        hook(a.phone, [{"id": cid, "from": a.cust, "event": "connect", "direction": "BUSINESS_INITIATED",
                        "session": {"sdp_type": "answer", "sdp": ANSWER}}])
        mine = a.c.get("/api/calls/ringing").get_json()["calls"]
        self.assertEqual((mine[0]["status"], mine[0]["answer"]), ("answered", ANSWER))
        with db.get_conn() as c:
            c.execute("UPDATE wa_calls SET created_at=? WHERE call_id=?", (int(time.time()) - 300, cid))
        self.assertEqual(len(a.c.get("/api/calls/ringing").get_json()["calls"]), 1, "مكالمة جارية طويلة لا تختفي من الاستطلاع")
        a.end(cid, 40)
        self.assertEqual(texts(a.bot, peer)[-1], "📞 مكالمة صادرة — 0:40")

    def test_unanswered_outbound_is_logged_without_missed_text(self):
        a = Acct()
        peer = "wa:" + a.cust
        db.add_bot_user(a.bot, int(a.cust), "x", peer=peer)
        post(a.c, "/api/calls/settings", {"bot": a.bot, "enabled": True, "missed_text": "فاتتنا مكالمتك"})
        CALLS.on_permission(a.bot, peer, {"accept": True, "permanent": True})
        cid = post(a.c, "/api/calls/start", {"bot": a.bot, "peer": peer, "sdp": OFFER}).get_json()["id"]
        SENT.clear()
        a.end(cid)
        self.assertEqual(texts(a.bot, peer)[-1], "📞 اتصلنا ولم يرد العميل")
        self.assertEqual(SENT, [], "لا رسالة «فاتتنا» لعميل لم يتصل")
        CALLS.on_permission(a.bot, peer, {"accept": True, "expires": int(time.time()) - 1})
        self.assertEqual(CALLS.permission(a.bot, peer), "expired")


if __name__ == "__main__":
    unittest.main(verbosity=2)
