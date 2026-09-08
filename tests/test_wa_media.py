"""وسائط واتساب من الويبهوك حتى القرص — بخطوتَي التنزيل اللتين تفرضهما Meta.
    python tests/test_wa_media.py
"""
import asyncio, json, os, shutil, sys, tempfile, unittest
from unittest import mock

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)
os.chdir(_ROOT)
_TMP = tempfile.mkdtemp(prefix="botyalla-wamedia-")
os.environ["BOTYALLA_DB"] = os.path.join(_TMP, "t.db")
os.environ["BOTYALLA_UPLOADS"] = _TMP
os.environ.setdefault("SECRET_KEY", "wa-media")

import database as db                             # noqa: E402
import media_store                                # noqa: E402
import flow_engine                                # noqa: E402
from channels.whatsapp import WhatsAppChannel     # noqa: E402


JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 4096
OGG = b"OggS" + b"\x00" * 4096
MEDIA_URL = "https://lookaside.fbsbx.com/whatsapp/one-time-url"


def wrap(*messages):
    return {"entry": [{"changes": [{"value": {
        "metadata": {"phone_number_id": "5550001"},
        "contacts": [{"profile": {"name": "أحمد"}}],
        "messages": list(messages)}}]}]}


class NormalizeTests(unittest.TestCase):
    ch = WhatsAppChannel("5550001", "tok")

    def test_an_image_carries_its_reference_mime_and_caption(self):
        m = self.ch.normalize_all(wrap({
            "id": "m1", "from": "201001", "type": "image",
            "image": {"id": "MEDIA-1", "mime_type": "image/jpeg", "caption": "العطل هنا"}}))[0]
        self.assertEqual(m["kind"], "media")
        self.assertEqual(m["media"]["ref"], "MEDIA-1")
        self.assertEqual(m["media"]["mime"], "image/jpeg")
        self.assertEqual(m["text"], "العطل هنا", "التعليق هو نص العميل — لا يجوز فقده")

    def test_a_voice_note_is_media_too(self):
        m = self.ch.normalize_all(wrap({
            "id": "m2", "from": "201001", "type": "voice",
            "voice": {"id": "MEDIA-2", "mime_type": "audio/ogg; codecs=opus"}}))[0]
        self.assertEqual(m["kind"], "media")
        self.assertEqual(m["media"]["ref"], "MEDIA-2")

    def test_documents_stickers_and_video_are_media(self):
        for kind in ("document", "sticker", "video", "audio"):
            m = self.ch.normalize_all(wrap({
                "id": "x", "from": "201001", "type": kind, kind: {"id": "R"}}))[0]
            self.assertEqual(m["kind"], "media", kind)

    def test_a_location_stays_unsupported_because_there_is_no_file(self):
        m = self.ch.normalize_all(wrap({
            "id": "m3", "from": "201001", "type": "location",
            "location": {"latitude": 30, "longitude": 31}}))[0]
        self.assertEqual(m["kind"], "unsupported")


class FetchTests(unittest.TestCase):
    """Meta تفرض خطوتين: المعرّف يعطي رابطاً صالحاً 5 دقائق، والرابط لا يُفتح
    إلا بترويسة Authorization. إغفال الترويسة يفشل التنزيل بصمت."""

    def _client(self, calls, url_status=200, blob_status=200):
        class R:
            def __init__(s, status, payload=None, content=b""):
                s.status_code, s._p, s.content, s.text = status, payload, content, ""

            def json(s):
                return s._p

        class C:
            async def get(s, url, params=None, headers=None):
                calls.append({"url": url, "params": params, "headers": headers})
                if url.startswith(MEDIA_URL):
                    return R(blob_status, content=JPEG)
                return R(url_status, {"url": MEDIA_URL, "mime_type": "image/jpeg",
                                      "file_size": len(JPEG), "id": "MEDIA-1"})
        return C()

    def test_the_two_step_download_sends_the_token_on_both_calls(self):
        calls = []
        ch = WhatsAppChannel("5550001", "TOKEN")
        with mock.patch("channels.whatsapp._http", return_value=self._client(calls)):
            data, mime = asyncio.run(ch.fetch_media({"ref": "MEDIA-1"}))
        self.assertEqual(data, JPEG)
        self.assertEqual(mime, "image/jpeg")
        self.assertEqual(len(calls), 2, "التنزيل خطوتان لا واحدة")
        self.assertTrue(calls[0]["url"].endswith("/MEDIA-1"))
        self.assertEqual(calls[0]["params"], {"phone_number_id": "5550001"})
        for c in calls:
            self.assertEqual(c["headers"], {"Authorization": "Bearer TOKEN"},
                             "بلا التوكن يفشل التنزيل")

    def test_a_failed_lookup_returns_nothing_rather_than_raising(self):
        ch = WhatsAppChannel("5550001", "TOKEN")
        with mock.patch("channels.whatsapp._http",
                        return_value=self._client([], url_status=404)):
            self.assertEqual(asyncio.run(ch.fetch_media({"ref": "X"})), (None, None))

    def test_a_failed_blob_download_returns_nothing(self):
        ch = WhatsAppChannel("5550001", "TOKEN")
        with mock.patch("channels.whatsapp._http",
                        return_value=self._client([], blob_status=403)):
            self.assertEqual(asyncio.run(ch.fetch_media({"ref": "X"})), (None, None))

    def test_no_reference_means_no_network_call(self):
        calls = []
        ch = WhatsAppChannel("5550001", "TOKEN")
        with mock.patch("channels.whatsapp._http", return_value=self._client(calls)):
            self.assertEqual(asyncio.run(ch.fetch_media({})), (None, None))
        self.assertEqual(calls, [])


class EndToEndTests(unittest.TestCase):
    """من payload الويبهوك حتى الملف على القرص مربوطاً بـ lead."""

    @classmethod
    def setUpClass(cls):
        db.init_db()
        with db.get_conn() as c:
            c.execute("INSERT OR IGNORE INTO users(id,username,pw_hash,role,created_at)"
                      " VALUES(80,'wam','x','user',0)")
        db.activate_subscription(80, "pro", days=30)
        cls.bot_id = db.create_bot(80, "WA", "wa:5550001", "flow", {
            "wa_token": "TOKEN",
            "flow": {"start_message": "أهلاً", "end_message": "تم", "steps": [
                {"id": "s0", "type": "media", "prompt": "أرسل صورة:", "var": "الصورة"}]}},
            channel="whatsapp")
        db.set_bot_active(cls.bot_id, True)

    def test_a_photo_sent_on_whatsapp_ends_up_on_the_lead(self):
        import bot_manager
        sent = []

        async def fake_post(self, payload):
            sent.append(payload)
            return {"messages": [{"id": "o"}]}

        async def fake_fetch(self, media):
            return (JPEG, "image/jpeg") if media.get("ref") else (None, None)

        payload = wrap({"id": "in-1", "from": "201009", "type": "text",
                        "text": {"body": "مرحبا"}})
        photo = wrap({"id": "in-2", "from": "201009", "type": "image",
                      "image": {"id": "MEDIA-9", "mime_type": "image/jpeg",
                                "caption": "الشاشة مكسورة"}})

        with mock.patch.object(WhatsAppChannel, "_post", fake_post), \
             mock.patch.object(WhatsAppChannel, "fetch_media", fake_fetch):
            asyncio.run(bot_manager.manager._handle_wa_webhook(payload))
            asyncio.run(bot_manager.manager._handle_wa_webhook(photo))

        # نقصر على هذا العميل: اختبارات أخرى في نفس الصف تنشئ leads لعملاء آخرين
        rows = [r for r in db.list_leads(self.bot_id) if r["tg_user_id"] == 201009]
        self.assertEqual(len(rows), 1, "لم يكتمل الفلو")
        self.assertEqual(len(rows[0]["media"]), 1, "الملف لم يُربط بالـ lead")
        m = rows[0]["media"][0]
        self.assertEqual(m["kind"], "image")
        self.assertEqual(m["caption"], "الشاشة مكسورة")
        self.assertTrue(os.path.exists(
            media_store.path_of(db.get_media(m["id"])["fname"])))
        self.assertIn("media:", json.loads(
            json.dumps(rows[0]["data"], ensure_ascii=False))["الصورة"])

    def test_a_duplicate_delivery_does_not_store_the_file_twice(self):
        """Meta تُعيد الإرسال — تخزين مرتين يضاعف استهلاك القرص والحصة."""
        import bot_manager
        db.clear_chat_state(self.bot_id, "wa:201007")

        async def fake_post(self, payload):
            return {"ok": True}

        async def fake_fetch(self, media):
            return OGG, "audio/ogg"

        start = wrap({"id": "d-0", "from": "201007", "type": "text", "text": {"body": "مرحبا"}})
        voice = wrap({"id": "d-1", "from": "201007", "type": "voice",
                      "voice": {"id": "MEDIA-D", "mime_type": "audio/ogg"}})

        before = db.media_count_this_month(80)
        with mock.patch.object(WhatsAppChannel, "_post", fake_post), \
             mock.patch.object(WhatsAppChannel, "fetch_media", fake_fetch):
            asyncio.run(bot_manager.manager._handle_wa_webhook(start))
            asyncio.run(bot_manager.manager._handle_wa_webhook(voice))
            asyncio.run(bot_manager.manager._handle_wa_webhook(voice))   # إعادة إرسال
        self.assertEqual(db.media_count_this_month(80), before + 1)


def tearDownModule():
    shutil.rmtree(_TMP, ignore_errors=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
