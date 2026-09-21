"""ماسنجر + إنستجرام (المرحلة الأولى — للفريق): القناة · الربط · الويبهوك · حماية توكن الصفحة.
    python tests/test_messenger.py
"""
import asyncio, hashlib, hmac, json, os, sys, tempfile, unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_TMP = tempfile.mkdtemp(prefix="botyalla-msgr-")
os.environ["BOTYALLA_DB"] = os.path.join(_TMP, "t.db")        # قبل أي استيراد
os.environ["BOTYALLA_UPLOADS"] = _TMP
os.environ["BOTYALLA_LOGS"] = _TMP
os.environ["META_APP_ID"] = "1337778974883863"

import database as db                       # noqa: E402
import meta_pages as MP                     # noqa: E402
import bot_manager as BM                    # noqa: E402
import channels.messenger as CM             # noqa: E402
import app as A                             # noqa: E402

PAGE, IG, PSID, IGSID = "111000111", "178400000000001", "9000000000000001", "9100000000000002"
CSRF = "c" * 32


class R:
    def __init__(self, code, body, headers=None):
        self.status_code, self._b, self.headers = code, body, headers or {}
        self.content = b""

    def json(self):
        return self._b


# ------------------------------------------------------------------ Send API مزيّف (async)
class FakeAsync:
    sent = []
    is_closed = False

    def __init__(self, *a, **k): pass

    async def post(self, url, json=None, params=None, **k):
        FakeAsync.sent.append((url, json, params))
        return R(200, {"message_id": "m1"})


# ------------------------------------------------------------------ Graph مزيّف (sync) للربط
class FakeGraph:
    calls = []
    me_is_page = True
    has_ig = True
    subscribe_ok = True

    def __init__(self, *a, **k): pass
    def __enter__(self): return self
    def __exit__(self, *a): return False

    def get(self, url, params=None, **k):
        FakeGraph.calls.append(("GET", url, dict(params or {})))
        if url.endswith("/me"):
            return R(200, {"id": PAGE if FakeGraph.me_is_page else "555", "name": "x"})
        if url.endswith("/oauth/access_token"):
            return R(200, {"access_token": "EAA-long-user"})
        if url.endswith("/me/accounts"):
            return R(200, {"data": [{"id": PAGE, "name": "Raghad", "access_token": "EAA-page-from-user"}]})
        if url.endswith(f"/{PAGE}/subscribed_apps"):
            return R(200, {"data": [{"id": "1337778974883863", "subscribed_fields": ["messages"]}]})
        if url.endswith(f"/{PAGE}"):
            body = {"name": "Raghad Store"}
            if FakeGraph.has_ig:
                body["instagram_business_account"] = {"id": IG, "username": "raghad.store"}
            return R(200, body)
        return R(404, {"error": {"message": "nope"}})

    reject = set()                       # حقول ترفضها Meta (تحتاج أذونات)

    def post(self, url, params=None, **k):
        FakeGraph.calls.append(("POST", url, dict(params or {})))
        if url.endswith("/subscribed_apps"):
            asked = set((params or {}).get("subscribed_fields", "").split(","))
            if not FakeGraph.subscribe_ok or asked & FakeGraph.reject:
                return R(400, {"error": {"message": "perm"}})
            return R(200, {"success": True})
        return R(404, {})

    def delete(self, url, params=None, **k):
        FakeGraph.calls.append(("DELETE", url, dict(params or {})))
        return R(200, {"success": True})


def ev_text(text, sender=PSID, mid="mid.1", **extra):
    m = {"mid": mid, "text": text}
    m.update(extra)
    return {"object": "page", "entry": [{"id": PAGE, "messaging": [
        {"sender": {"id": sender}, "recipient": {"id": PAGE}, "timestamp": 1, "message": m}]}]}


class ChannelTests(unittest.TestCase):
    def setUp(self):
        FakeAsync.sent = []
        self._c = CM._client
        CM._client = FakeAsync()
        self.ch = CM.MessengerChannel("fb", PAGE, "EAA-page")

    def tearDown(self):
        CM._client = self._c

    def test_normalize_text_quick_reply_start_and_echo(self):
        n = self.ch.normalize(ev_text("عايز أعرف الأسعار"))
        self.assertEqual((n["peer"], n["kind"], n["text"]), (f"fb:{PSID}", "text", "عايز أعرف الأسعار"))
        n = self.ch.normalize(ev_text("الأسعار", quick_reply={"payload": "الأسعار"}))
        self.assertEqual(n["text"], "الأسعار")
        self.assertEqual(self.ch.normalize(ev_text("hi"))["kind"], "start")
        self.assertIsNone(self.ch.normalize(ev_text("echo", is_echo=True)), "صدى رسائلنا ليس وارداً")
        self.assertIsNone(self.ch.normalize(ev_text("self", sender=PAGE)))

    def test_get_started_and_ad_referral_become_start(self):
        raw = {"entry": [{"id": PAGE, "messaging": [{"sender": {"id": PSID}, "timestamp": 2,
               "postback": {"payload": "GET_STARTED", "title": "Get Started",
                            "referral": {"ref": "seg-market"}}}]}]}
        n = self.ch.normalize(raw)
        self.assertEqual((n["kind"], n.get("start_arg")), ("start", "seg-market"))

    def test_attachment_is_media(self):
        n = self.ch.normalize(ev_text("", attachments=[{"type": "image", "payload": {"url": "https://cdn/x.jpg"}}]))
        self.assertEqual(n["kind"], "media")
        self.assertEqual(n["media"]["ref"], "https://cdn/x.jpg")

    def test_send_uses_response_type_and_quick_replies(self):
        asyncio.run(self.ch.send_buttons(f"fb:{PSID}", "تحب إيه؟", ["الأسعار", "المنيو"]))
        url, body, params = FakeAsync.sent[-1]
        self.assertTrue(url.endswith("/me/messages"))
        self.assertEqual(params["access_token"], "EAA-page")
        self.assertEqual(body["messaging_type"], "RESPONSE")
        self.assertEqual(body["recipient"]["id"], PSID)
        self.assertEqual([q["title"] for q in body["message"]["quick_replies"]], ["الأسعار", "المنيو"])

    def test_too_many_or_long_options_fall_back_to_numbered_text(self):
        asyncio.run(self.ch.send_buttons(f"fb:{PSID}", "اختار", [f"خيار {i}" for i in range(14)]))
        msg = FakeAsync.sent[-1][1]["message"]
        self.assertNotIn("quick_replies", msg)
        self.assertIn("14. خيار 13", msg["text"])

    def test_instagram_gets_documents_as_links(self):
        ig = CM.MessengerChannel("ig", IG, "EAA-page")
        asyncio.run(ig.send_document_link(f"ig:{IGSID}", "https://x/a.pdf", "a.pdf", "الملف"))
        self.assertIn("https://x/a.pdf", FakeAsync.sent[-1][1]["message"]["text"])

    def test_mark_read_knows_the_sender_of_a_message(self):
        n = self.ch.normalize(ev_text("سلام", mid="mid.9"))
        asyncio.run(self.ch.mark_read(n["id"]))
        actions = [b.get("sender_action") for _, b, _ in FakeAsync.sent]
        self.assertEqual(actions[-2:], ["mark_seen", "typing_on"])


class ConnectTests(unittest.TestCase):
    def setUp(self):
        FakeGraph.calls, FakeGraph.me_is_page, FakeGraph.has_ig, FakeGraph.subscribe_ok = [], True, True, True
        self._c = MP.httpx.Client
        MP.httpx.Client = FakeGraph

    def tearDown(self):
        MP.httpx.Client = self._c

    def test_page_token_connects_and_subscribes(self):
        r = MP.connect(PAGE, "EAA-page-token-xxxxxxxx")
        self.assertEqual((r["page_token"], r["ig_id"], r["ig_username"]), ("EAA-page-token-xxxxxxxx", IG, "raghad.store"))
        sub = [c for c in FakeGraph.calls if c[1].endswith("/subscribed_apps")][0]
        self.assertIn("messages", sub[2]["subscribed_fields"])
        self.assertEqual(r["warning"], "")

    def test_user_token_becomes_a_permanent_page_token(self):
        FakeGraph.me_is_page = False
        r = MP.connect(PAGE, "EAA-short-user-token-xx", app_id="1337778974883863", secret="s")
        self.assertEqual(r["page_token"], "EAA-page-from-user")
        acc = [c for c in FakeGraph.calls if c[1].endswith("/me/accounts")][0]
        self.assertEqual(acc[2]["access_token"], "EAA-long-user")         # بعد التبديل للطويل

    def test_subscribe_failure_is_a_warning_not_a_crash(self):
        FakeGraph.subscribe_ok = False
        self.assertIn("perm", MP.connect(PAGE, "EAA-page-token-xxxxxxxx")["warning"])

    def test_bad_input(self):
        with self.assertRaises(MP.PagesError):
            MP.connect("abc", "EAA-page-token-xxxxxxxx")


class _PageBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        db.init_db()
        with db.get_conn() as c:
            c.execute("INSERT OR IGNORE INTO users(id,username,pw_hash,role,created_at) VALUES(1,'root','x','admin',0)")
            c.execute("INSERT OR IGNORE INTO users(username,pw_hash,role,created_at) VALUES('shop','x','user',0)")
        cls.shop = db.get_user_by_name("shop")["id"]
        db.set_platform("wa_app_secret", "app-secret")

    def setUp(self):
        A._login_attempts.clear()
        FakeGraph.calls, FakeGraph.me_is_page, FakeGraph.has_ig, FakeGraph.subscribe_ok = [], True, True, True
        FakeGraph.reject = set()
        self._c = MP.httpx.Client
        MP.httpx.Client = FakeGraph
        with db.get_conn() as c:
            c.execute("DELETE FROM bots")
            c.execute("DELETE FROM meta_events")
        db.set_platform("meta_page_id", ""); db.set_platform("meta_page_token", "")

    def tearDown(self):
        MP.httpx.Client = self._c

    def client(self, uid):
        c = A.app.test_client()
        with c.session_transaction() as s:
            s["uid"] = uid; s["_csrf"] = CSRF
        return c

    def connect(self, uid, **kw):
        body = {"page_id": PAGE, "token": "EAA-page-token-xxxxxxxx", "name": "رغد",
                "messenger": True, "instagram": True}
        body.update(kw)
        return self.client(uid).post("/meta/connect", json=body, headers={"X-CSRF-Token": CSRF})


class RouteAndWebhookTests(_PageBase):
    def test_team_only_in_phase_one(self):
        r = self.connect(self.shop)
        self.assertIn(r.status_code, (302, 403))
        self.assertEqual(FakeGraph.calls, [], "استدعى Meta لغير الفريق")

    def test_connect_creates_both_bots_with_a_sealed_token(self):
        d = self.connect(1).get_json()
        self.assertTrue(d["ok"], d)
        fb, ig = db.get_bot_by_token(f"fb:{PAGE}"), db.get_bot_by_token(f"ig:{IG}")
        self.assertEqual((fb["channel"], ig["channel"]), ("messenger", "instagram"))
        cfg = json.loads(fb["config_json"])
        self.assertEqual(db.unseal(cfg["page_token"]), "EAA-page-token-xxxxxxxx")
        html = self.client(1).get(f"/bot/{fb['id']}").get_data(as_text=True)
        self.assertNotIn("EAA-page-token", html)
        self.assertNotIn('"page_token"', html)

    def test_instagram_requires_a_linked_account(self):
        FakeGraph.has_ig = False
        d = self.connect(1, messenger=False).get_json()
        self.assertFalse(d["ok"])
        self.assertIsNone(db.get_bot_by_token(f"fb:{PAGE}"))

    def test_webhook_path_is_signed_and_csrf_exempt(self):
        body = json.dumps({"object": "page", "entry": []}).encode()
        c = A.app.test_client()
        self.assertEqual(c.post("/wh/meta", data=body, headers={"Content-Type": "application/json"}).status_code, 403)
        sig = "sha256=" + hmac.new(b"app-secret", body, hashlib.sha256).hexdigest()
        r = c.post("/wh/meta", data=body, headers={"Content-Type": "application/json", "X-Hub-Signature-256": sig})
        self.assertEqual(r.status_code, 200)

    def test_events_reach_the_engine_once_and_only_for_active_bots(self):
        self.assertTrue(self.connect(1).get_json()["ok"])
        fb = db.get_bot_by_token(f"fb:{PAGE}")
        seen = []
        import flow_engine
        orig = flow_engine.handle_message

        async def fake(row, ch, msg):
            seen.append((row["id"], msg["peer"], msg["text"]))
        flow_engine.handle_message = fake
        try:
            asyncio.run(BM.manager._handle_meta_pages(ev_text("سلام", mid="mid.a")))
            self.assertEqual(seen, [], "بوت غير مفعّل لا يرد")
            db.set_bot_active(fb["id"], True)
            asyncio.run(BM.manager._handle_meta_pages(ev_text("سلام", mid="mid.b")))
            asyncio.run(BM.manager._handle_meta_pages(ev_text("سلام", mid="mid.b")))   # إعادة إرسال Meta
            self.assertEqual(seen, [(fb["id"], f"fb:{PSID}", "سلام")])
        finally:
            flow_engine.handle_message = orig

    def test_peers_are_scoped_to_the_bot_channel(self):
        self.assertTrue(self.connect(1).get_json()["ok"])
        fb = db.get_bot_by_token(f"fb:{PAGE}")
        db.add_bot_user(fb["id"], int(PSID), "منى", peer=f"fb:{PSID}")
        db.add_bot_user(fb["id"], 42, "tg", peer="tg:42")
        self.assertEqual(db.list_bot_peers(fb["id"]), [f"fb:{PSID}"])


class AdminMetaTests(_PageBase):
    """«/admin/meta»: للأدمن وحده · صفحة المنصة تُحفظ مرة · الحقول · الرسمي · الربط لمستخدم."""
    def setUp(self):
        super().setUp()
        self.started = []
        self._start = A.manager.start_bot
        A.manager.start_bot = lambda bid: self.started.append(bid) or (True, "")
        with db.get_conn() as c:
            c.execute("INSERT OR IGNORE INTO users(username,pw_hash,role,created_at) VALUES('agent','x','support',0)")
        self.agent = db.get_user_by_name("agent")["id"]

    def tearDown(self):
        A.manager.start_bot = self._start
        super().tearDown()

    def post(self, uid, url, body=None):
        return self.client(uid).post(url, json=body or {}, headers={"X-CSRF-Token": CSRF})

    def save_page(self):
        return self.post(1, "/admin/meta/page", {"page_id": PAGE, "token": "EAA-page-token-xxxxxxxx"}).get_json()

    def test_admin_only_even_for_support(self):
        self.assertIn(self.client(self.agent).get("/admin/meta").status_code, (302, 403))
        self.assertIn(self.post(self.agent, "/admin/meta/page", {"page_id": PAGE, "token": "x" * 30}).status_code,
                      (302, 403))
        self.assertEqual(FakeGraph.calls, [])

    def test_platform_page_is_saved_once_and_never_shown(self):
        self.assertTrue(self.save_page()["ok"])
        self.assertEqual(db.get_platform("meta_page_id"), PAGE)
        self.assertEqual(db.unseal(db.get_platform("meta_page_token")), "EAA-page-token-xxxxxxxx")
        sealed = db.get_platform("meta_page_token")
        for url in ("/admin/meta", "/admin/platform"):
            html = self.client(1).get(url).get_data(as_text=True)
            self.assertNotIn("EAA-page-token", html, url)
            self.assertNotIn(sealed[:24], html, url)
        # «حدّث واشترك» بلا توكن جديد = نفس المحفوظ
        self.assertTrue(self.post(1, "/admin/meta/page", {"page_id": PAGE, "token": ""}).get_json()["ok"])

    def test_fields_rejected_by_meta_are_reported_the_rest_subscribed(self):
        self.save_page()
        FakeGraph.reject = {"calls"}
        d = self.post(1, "/admin/meta/fields", {"fields": ["messages", "feed", "calls", "not_a_field"]}).get_json()
        self.assertEqual(d["accepted"], ["messages", "feed"])
        self.assertEqual(list(d["rejected"]), ["calls"])

    def test_official_bots_come_from_the_saved_token(self):
        self.save_page()
        d = self.post(1, "/admin/meta/official", {"messenger": True, "instagram": True}).get_json()
        self.assertTrue(d["ok"], d)
        fb = db.get_bot_by_token(f"fb:{PAGE}")
        cfg = json.loads(fb["config_json"])
        self.assertTrue(cfg["platform_kb"])
        self.assertEqual(cfg["response_mode"], "ai")
        self.assertEqual(sorted(self.started), sorted(b["id"] for b in d["bots"]))
        d2 = self.post(1, "/admin/meta/official", {}).get_json()      # لا تكرار — تحديث التوكن
        self.assertTrue(all(b.get("updated") for b in d2["bots"]))

    def test_assign_creates_bots_in_the_users_account(self):
        d = self.post(1, "/admin/meta/assign", {"username": "shop", "page_id": PAGE,
                                               "token": "EAA-page-token-xxxxxxxx", "messenger": True,
                                               "instagram": False}).get_json()
        self.assertTrue(d["ok"], d)
        self.assertEqual(db.get_bot_by_token(f"fb:{PAGE}")["owner_id"], self.shop)
        self.assertIsNone(db.get_bot_by_token(f"ig:{IG}"))
        self.assertEqual(self.started, [d["bots"][0]["id"]])

    def test_side_events_echo_handover_standby_and_log(self):
        self.save_page()
        self.post(1, "/admin/meta/official", {"messenger": True, "instagram": False})
        fb = db.get_bot_by_token(f"fb:{PAGE}")
        db.set_bot_active(fb["id"], True)
        peer = f"fb:{PSID}"

        def entry(**kw):
            e = {"id": PAGE}
            e.update(kw)
            return {"object": "page", "entry": [e]}
        seen = []
        import flow_engine
        orig = flow_engine.handle_message

        async def fake(row, ch, msg):
            seen.append(msg["text"])
        flow_engine.handle_message = fake
        try:
            asyncio.run(BM.manager._handle_meta_pages(entry(messaging=[{
                "sender": {"id": PAGE}, "recipient": {"id": PSID}, "timestamp": 3,
                "message": {"is_echo": True, "mid": "e1", "text": "أهلاً، معاك أحمد"}}])))
            self.assertEqual(db.get_conversation(fb["id"], peer)["mode"], "human")
            db.set_conversation_mode(fb["id"], peer, "bot")
            asyncio.run(BM.manager._handle_meta_pages(entry(messaging=[{
                "sender": {"id": PAGE}, "recipient": {"id": PSID}, "timestamp": 4,
                "message": {"is_echo": True, "app_id": 1337778974883863, "mid": "e2", "text": "رد البوت"}}])))
            self.assertEqual(db.get_conversation(fb["id"], peer)["mode"], "bot")
            asyncio.run(BM.manager._handle_meta_pages(entry(messaging=[{
                "sender": {"id": PSID}, "recipient": {"id": PAGE}, "timestamp": 5,
                "pass_thread_control": {"new_owner_app_id": "263902037430900"}}])))
            self.assertEqual(db.get_conversation(fb["id"], peer)["mode"], "human")
            asyncio.run(BM.manager._handle_meta_pages(entry(standby=[{
                "sender": {"id": PSID}, "recipient": {"id": PAGE}, "timestamp": 6,
                "message": {"mid": "s1", "text": "حد موجود؟"}}],
                changes=[{"field": "feed", "value": {"item": "comment", "verb": "add",
                                                     "message": "بكام؟", "from": {"name": "منى"}}}])))
            self.assertEqual(seen, [], "لا رد على standby ولا على صدى")
            kinds = [e["kind"] for e in db.list_meta_events(20)]
            self.assertIn("handover", kinds)
            self.assertIn("feed", kinds)
            asyncio.run(BM.manager._handle_meta_pages({"object": "page", "entry": [
                {"id": "999", "messaging": [{"sender": {"id": "1"}, "read": {"watermark": 1}}]}]}))
            self.assertEqual(db.list_meta_events(1)[0]["kind"], "unrouted")
        finally:
            flow_engine.handle_message = orig


if __name__ == "__main__":
    unittest.main(verbosity=2)
