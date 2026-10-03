"""«مساعد BotYalla» كوكيل: تنقّل فوري · تعديلات البوت ببطاقة «نفّذ» · الصوت (تفريغ ونطق) بمفاتيح المنصة.
    python tests/test_assistant_agent.py
"""
import json, os, sys, tempfile, unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_TMP = tempfile.mkdtemp(prefix="botyalla-agent-")
os.environ["BOTYALLA_DB"] = os.path.join(_TMP, "t.db")        # قبل أي استيراد
os.environ["BOTYALLA_UPLOADS"] = _TMP
os.environ["BOTYALLA_LOGS"] = _TMP
os.environ["PUBLIC_URL"] = "https://botyalla.test"

import database as db          # noqa: E402
import ai_agent                # noqa: E402
import site_assistant as SA    # noqa: E402
import voice_ai as VA          # noqa: E402
import app as A                # noqa: E402

CSRF = "tk"
H = {"X-CSRF-Token": CSRF}
REPLY = {}                     # ما «يقوله» النموذج المحاكى في الاختبار الجاري


def setUpModule():
    db.init_db()
    A.app.config["TESTING"] = True
    A.manager.notify_text = lambda *a, **k: None
    A.manager.is_running = lambda *a, **k: False
    db.set_platform("ai_provider", "gemini")
    db.set_platform("ai_key_gemini", "test-key")
    ai_agent._call = lambda *a, **k: json.dumps(REPLY["v"], ensure_ascii=False)


def user(name):
    with db.get_conn() as c:
        c.execute("INSERT INTO users(username,pw_hash,role,created_at) VALUES(?,?,?,0)", (name, "x", "user"))
        return c.execute("SELECT id FROM users WHERE username=?", (name,)).fetchone()[0]


def client(uid=None):
    c = A.app.test_client()
    with c.session_transaction() as s:
        s["_csrf"] = CSRF
        if uid:
            u = db.get_user(uid)
            s.update(uid=uid, uname=u["username"], role=u["role"], pwv=A._pw_stamp(u["pw_hash"]))
    return c


def ask(c, text="x", voice=False):
    return c.post("/api/assistant", json={"text": text, "view": "dashboard", "voice": voice}, headers=H).get_json()


class Base(unittest.TestCase):
    def setUp(self):
        A._login_attempts.clear()
        try:
            A._rate.clear()
        except AttributeError:
            pass
        self.uid = user(f"owner{self.id()[-12:].replace('.', '')}")
        self.store = db.create_bot(self.uid, "متجري", f"1{self.uid}:AAstoreTOKENxxxxxxxxxxxxxxxxxxxxxxxxx", "store",
                                   {"welcome": "قديم", "products": [{"name": "تيشيرت", "price": 100}]})
        self.c = client(self.uid)


class CleanActionTests(unittest.TestCase):
    def test_navigate_only_to_allowed_pages_and_own_bots(self):
        pages = {"billing", "wallet"}
        self.assertEqual(SA.clean_action({"type": "navigate", "args": {"page": "billing"}}, {5}, pages)["args"],
                         {"page": "billing"})
        self.assertEqual(SA.clean_action({"type": "navigate", "args": {"page": "inbox:5"}}, {5}, pages)["args"],
                         {"page": "inbox:5"})
        for bad in ("admin_payments", "inbox:6", "bot:abc", "https://evil.test", "settings"):
            self.assertIsNone(SA.clean_action({"type": "navigate", "args": {"page": bad}}, {5}, pages), bad)

    def test_edit_actions_are_validated(self):
        ok = SA.clean_action({"type": "add_product", "args": {"bot_id": 5, "name": "هودي", "price": "450.5"}},
                             {5}, (), {5: "store"})
        self.assertEqual(ok["args"]["price"], 450.5)
        self.assertIsNone(SA.clean_action({"type": "add_product", "args": {"bot_id": 5, "name": "x", "price": 1}},
                                          {5}, (), {5: "booking"}), "منتج لبوت غير متجر")
        self.assertIsNone(SA.clean_action({"type": "add_product", "args": {"bot_id": 5, "name": "x", "price": "free"}},
                                          {5}, (), {5: "store"}))
        self.assertIsNone(SA.clean_action({"type": "add_faq", "args": {"bot_id": 5, "q": "سؤال"}}, {5}))
        self.assertIsNone(SA.clean_action({"type": "update_info", "args": {"bot_id": 5, "secret": "x"}}, {5}))
        info = SA.clean_action({"type": "update_info", "args": {"bot_id": 5, "hours": "9-5", "token": "x"}}, {5})
        self.assertEqual(info["args"], {"bot_id": 5, "hours": "9-5"})
        self.assertIsNone(SA.clean_action({"type": "set_welcome", "args": {"bot_id": 9, "text": "أهلاً"}}, {5}),
                          "بوت ليس للمستخدم")


class NavigateTests(Base):
    def test_navigate_returns_a_server_built_url_without_a_card(self):
        REPLY["v"] = {"reply": "بفتحلك", "action": {"type": "navigate", "args": {"page": f"inbox:{self.store}"}}}
        d = ask(self.c)
        self.assertIsNone(d["action"])
        self.assertEqual(d["go"]["url"], f"/bot/{self.store}/inbox")
        REPLY["v"] = {"reply": "تمام", "action": {"type": "navigate", "args": {"page": "billing"}}}
        self.assertEqual(ask(self.c)["go"]["url"], "/billing")

    def test_admin_pages_and_foreign_bots_are_refused(self):
        other = user("someone_else")
        foreign = db.create_bot(other, "غريب", "999:AAforeignTOKENxxxxxxxxxxxxxxxxxxxxxxx", "store", {})
        for page in ("admin_payments", f"inbox:{foreign}"):
            REPLY["v"] = {"reply": "حاضر", "action": {"type": "navigate", "args": {"page": page}}}
            d = ask(self.c)
            self.assertIsNone(d["go"], page)
            self.assertIsNone(d["action"], page)

    def test_visitor_gets_no_actions(self):
        REPLY["v"] = {"reply": "تمام", "action": {"type": "navigate", "args": {"page": "billing"}}}
        d = ask(client())
        self.assertIsNone(d["go"])
        self.assertIsNone(d["action"])

    def test_voice_mode_reaches_the_model(self):
        seen = {}
        orig = ai_agent._call
        ai_agent._call = lambda p, k, system, ctx: seen.update(ctx=ctx) or json.dumps({"reply": "أهلاً"})
        try:
            ask(self.c, voice=True)
        finally:
            ai_agent._call = orig
        self.assertIn("<mode>voice</mode>", seen["ctx"])
        self.assertIn('"metrics"', seen["ctx"])


class EditTests(Base):
    def card(self, action):
        REPLY["v"] = {"reply": "أنفّذ؟", "action": action}
        d = ask(self.c)
        self.assertTrue(d["action"], "بطاقة «نفّذ» — لا تنفيذ قبل الموافقة")
        return d["action"]["token"]

    def run_(self, token):
        return self.c.post("/api/assistant/act", json={"token": token}, headers=H).get_json()

    def cfg(self):
        return json.loads(db.get_bot(self.store)["config_json"])

    def test_nothing_changes_before_do_it_and_old_version_is_kept(self):
        tok = self.card({"type": "set_welcome", "args": {"bot_id": self.store, "text": "أهلاً بيك في متجري الجديد"}})
        self.assertEqual(self.cfg()["welcome"], "قديم")
        d = self.run_(tok)
        self.assertTrue(d["ok"], d)
        self.assertEqual(self.cfg()["welcome"], "أهلاً بيك في متجري الجديد")
        self.assertEqual(self.cfg()["products"][0]["name"], "تيشيرت", "باقي الإعداد كما هو (الحفظ كامل)")
        versions = db.list_config_versions(self.store) if hasattr(db, "list_config_versions") else None
        if versions is not None:
            self.assertTrue(versions)
        self.assertFalse(self.run_(tok)["ok"], "التوكن لمرة واحدة")

    def test_info_faq_and_product(self):
        self.assertTrue(self.run_(self.card({"type": "update_info", "args": {"bot_id": self.store, "hours": "10ص - 10م"}}))["ok"])
        self.assertTrue(self.run_(self.card({"type": "add_faq", "args": {"bot_id": self.store, "q": "بتوصلوا؟", "a": "أيوه لكل مصر"}}))["ok"])
        self.assertTrue(self.run_(self.card({"type": "add_product", "args": {"bot_id": self.store, "name": "هودي", "price": 450, "desc": "قطن"}}))["ok"])
        cfg = self.cfg()
        self.assertEqual(cfg["kb"]["hours"], "10ص - 10م")
        self.assertEqual(cfg["kb"]["faqs"], [{"q": "بتوصلوا؟", "a": "أيوه لكل مصر"}])
        self.assertEqual([p["name"] for p in cfg["products"]], ["تيشيرت", "هودي"])
        self.assertEqual(cfg["products"][1]["price"], 450.0)

    def test_faq_limit(self):
        cfg = self.cfg()
        cfg["kb"] = {"faqs": [{"q": f"س{i}", "a": "ج"} for i in range(12)]}
        db.update_bot_config(self.store, cfg)
        d = self.run_(self.card({"type": "add_faq", "args": {"bot_id": self.store, "q": "جديد", "a": "ج"}}))
        self.assertFalse(d["ok"])
        self.assertEqual(len(self.cfg()["kb"]["faqs"]), 12)

    def test_token_from_another_session_is_useless(self):
        tok = self.card({"type": "set_welcome", "args": {"bot_id": self.store, "text": "اختراق"}})
        intruder = client(user("intruder"))
        d = intruder.post("/api/assistant/act", json={"token": tok}, headers=H).get_json()
        self.assertFalse(d["ok"])
        self.assertEqual(self.cfg()["welcome"], "قديم")


class VoiceTests(Base):
    def test_boot_advertises_voice_fallbacks(self):
        html = self.c.get("/dashboard").get_data(as_text=True)
        self.assertIn('"stt": "/api/assistant/stt"', html)
        self.assertIn('"voice": {"stt": true, "tts": true}', html)

    def test_stt_passes_audio_to_the_provider_and_never_stores_it(self):
        seen = {}
        orig = VA.transcribe
        VA.transcribe = lambda audio, mime, lang, chain: seen.update(n=len(audio), mime=mime) or "عايز أغيّر الترحيب"
        try:
            r = self.c.post("/api/assistant/stt", data=b"\x1aE\xdf\xa3" + b"0" * 2000,
                            headers={**H, "Content-Type": "audio/webm;codecs=opus"})
        finally:
            VA.transcribe = orig
        self.assertEqual(r.get_json(), {"ok": True, "text": "عايز أغيّر الترحيب"})
        self.assertEqual(seen["mime"], "audio/webm")
        self.assertFalse([f for f in os.listdir(_TMP) if f.endswith((".webm", ".ogg", ".wav"))])

    def test_stt_rejects_bad_type_size_and_missing_csrf(self):
        self.assertEqual(self.c.post("/api/assistant/stt", data=b"x" * 10,
                                     headers={**H, "Content-Type": "text/html"}).status_code, 400)
        big = b"0" * (VA.MAX_AUDIO + 10)
        self.assertEqual(self.c.post("/api/assistant/stt", data=big,
                                     headers={**H, "Content-Type": "audio/webm"}).status_code, 400)
        self.assertEqual(self.c.post("/api/assistant/stt", data=b"0" * 100,
                                     headers={"Content-Type": "audio/webm"}).status_code, 400)

    def test_tts_returns_wav_or_204(self):
        orig = VA.speak
        VA.speak = lambda text, lang, chain: VA._wav(b"\x00\x00" * 100)
        try:
            r = self.c.post("/api/assistant/tts", json={"text": "أهلاً"}, headers=H)
            self.assertEqual(r.status_code, 200)
            self.assertEqual(r.mimetype, "audio/wav")
            self.assertEqual(r.data[:4], b"RIFF")
            VA.speak = lambda *a: None
            self.assertEqual(self.c.post("/api/assistant/tts", json={"text": "أهلاً"}, headers=H).status_code, 204)
        finally:
            VA.speak = orig

    def test_csp_allows_blob_audio_only(self):
        csp = self.c.get("/dashboard").headers.get("Content-Security-Policy", "")
        self.assertIn("media-src 'self' blob:", csp)
        self.assertNotIn("'unsafe-inline'", csp.split("script-src")[1].split(";")[0])


class VoiceModuleTests(unittest.TestCase):
    def test_speakable_strips_symbols(self):
        t = VA.speakable("1. اضغط «تشغيل» 🎉\nhttps://x.test/a")
        self.assertNotIn("«", t)
        self.assertNotIn("http", t)
        self.assertNotIn("🎉", t)

    def test_find_audio_handles_both_response_shapes(self):
        pcm = b"\x01\x00" * 50
        import base64
        b64 = base64.b64encode(pcm).decode()
        legacy = {"candidates": [{"content": {"parts": [{"inlineData": {"mimeType": "audio/L16;codec=pcm;rate=24000", "data": b64}}]}}]}
        wav = VA._as_wav(*VA._find_audio(legacy))
        self.assertEqual(wav[:4], b"RIFF")
        self.assertEqual(wav[44:], pcm)
        inter = {"steps": [{"content": [{"type": "audio", "data": base64.b64encode(wav).decode()}]}]}
        self.assertEqual(VA._as_wav(*VA._find_audio(inter)), wav)

    def test_no_key_no_call(self):
        self.assertIsNone(VA.speak("أهلاً", "ar", []))
        self.assertIsNone(VA.transcribe(b"0" * 10, "audio/webm", "ar", []))
        self.assertIsNone(VA.transcribe(b"0" * 10, "video/mp4", "ar", [{"p": "gemini", "key": "k"}]))


if __name__ == "__main__":
    unittest.main()
