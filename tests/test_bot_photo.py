"""صورة بروفايل البوت: رفع واحد ← صورة نظيفة ← مزامنة مع تليجرام أو واتساب (المزوّد مُحاكى).

    python tests/test_bot_photo.py
"""
import io, json, os, secrets, sys, tempfile, unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_TMPDIR = tempfile.mkdtemp(prefix="botyalla-botphoto-")
os.environ["BOTYALLA_DB"] = os.path.join(_TMPDIR, "test.db")   # قبل استيراد database
os.environ["BOTYALLA_UPLOADS"] = _TMPDIR
os.environ["BOTYALLA_LOGS"] = _TMPDIR
os.environ["ADMIN_USER"] = "admin"
os.environ["ADMIN_PASS"] = "Adm#" + secrets.token_hex(6)

from PIL import Image                      # noqa: E402
import auth                                # noqa: E402
import database as db                      # noqa: E402
import app as web                          # noqa: E402
import tg_helpers                          # noqa: E402
import channels.whatsapp as WAC            # noqa: E402

PW = "Photo#Test2026"
CALLS = []


def _png(w=500, h=320, alpha=True):
    b = io.BytesIO()
    Image.new("RGBA" if alpha else "RGB", (w, h), (124, 108, 246, 120) if alpha else (30, 60, 90)).save(b, "PNG")
    return b.getvalue()


def _boot():
    db.init_db()
    web.seed_platform_defaults()
    web.contact_defaults()
    web.seed_default_admin()
    web.app.config["TESTING"] = True
    web.manager.is_running = lambda *a, **k: False
    web.tg.configure_bot_profile = lambda *a, **k: {"ok": True, "errors": []}


def _client(user):
    c = web.app.test_client()
    with c.session_transaction() as s:
        s["_csrf"] = "tk"
    c.post("/login", data={"username": user, "password": PW, "csrf_token": "tk"})
    return c


def _cfg(bid):
    return json.loads(db.get_bot(bid)["config_json"] or "{}")


class BotPhotoTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        _boot()
        cls.uid = db.create_user("photo_owner", auth.hash_password(PW), email="po@x.co")
        db.create_user("photo_other", auth.hash_password(PW), email="px@x.co")
        cls.tg_bot = db.create_bot(cls.uid, "tg", "111111:PHOTOTESTxxxxxxxxxxxxxxxx", "flow", {})
        cls.wa_bot = db.create_bot(cls.uid, "wa", "wa:5550001", "flow", {"wa_token": "EAAtok"}, channel="whatsapp")
        cls._orig = (web.tg.set_bot_photo, web.tg.remove_bot_photo, web.WAC.set_profile_photo)

    @classmethod
    def tearDownClass(cls):
        # الدوال الحقيقية ترجع — ProviderCallTests يختبر شكل طلباتها نفسها
        web.tg.set_bot_photo, web.tg.remove_bot_photo, web.WAC.set_profile_photo = cls._orig

    def setUp(self):
        CALLS.clear()
        web._login_attempts.clear()
        self.result = (True, "")
        web.tg.set_bot_photo = lambda token, jpeg: CALLS.append(("tg", token, jpeg)) or self.result
        web.tg.remove_bot_photo = lambda token: CALLS.append(("tg_rm", token)) or (True, "")
        web.WAC.set_profile_photo = lambda pid, tok, jpeg, app_id=None: (
            CALLS.append(("wa", pid, tok, jpeg, app_id)) or (True, "", "987654"))

    def _up(self, c, bid, data):
        return c.post(f"/bot/{bid}/photo", data={"photo": (io.BytesIO(data), "logo.png"), "csrf_token": "tk"},
                      content_type="multipart/form-data")

    def test_a_telegram_bot_gets_a_clean_square_jpeg(self):
        c = _client("photo_owner")
        self._up(c, self.tg_bot, _png())
        kind, token, jpeg = CALLS[-1]
        self.assertEqual((kind, token), ("tg", "111111:PHOTOTESTxxxxxxxxxxxxxxxx"))
        im = Image.open(io.BytesIO(jpeg))
        self.assertEqual((im.format, im.size), ("JPEG", (640, 640)), "تليجرام يقبل JPG للصورة الثابتة")
        cfg = _cfg(self.tg_bot)
        self.assertTrue(cfg["bot_photo"].endswith(".jpg"))
        self.assertTrue(cfg["bot_photo_sync"]["ok"])
        r = c.get(f"/bot/{self.tg_bot}/photo")
        self.assertEqual(r.status_code, 200)
        self.assertIn("private", r.headers["Cache-Control"])
        r.close()
        self.assertEqual(_client("photo_other").get(f"/bot/{self.tg_bot}/photo").status_code, 404,
                         "بوت غيرك ليس لك")

    def test_a_failed_sync_is_kept_and_retried_until_it_works(self):
        c = _client("photo_owner")
        self.result = (False, "Bad Request: PHOTO_INVALID")
        self._up(c, self.tg_bot, _png(alpha=False))
        self.assertFalse(_cfg(self.tg_bot)["bot_photo_sync"]["ok"])
        # حفظ الإعدادات (مزامنة تليجرام) يعيد المحاولة ما دامت لم تنجح
        self.result = (True, "")
        CALLS.clear()
        web.sync_bot_telegram(db.get_bot(self.tg_bot))
        self.assertEqual([k[0] for k in CALLS], ["tg"])
        self.assertTrue(_cfg(self.tg_bot)["bot_photo_sync"]["ok"])
        # وبعد النجاح لا تُرفع ثانيةً مع كل حفظ
        CALLS.clear()
        web.sync_bot_telegram(db.get_bot(self.tg_bot))
        self.assertEqual(CALLS, [])
        c.post(f"/bot/{self.tg_bot}/photo/sync", data={"csrf_token": "tk"})
        self.assertEqual([k[0] for k in CALLS], ["tg"], "«إعادة المزامنة» ترفعها صراحةً")

    def test_a_whatsapp_bot_syncs_to_the_business_number_and_stores_the_app_id(self):
        c = _client("photo_owner")
        self._up(c, self.wa_bot, _png())
        kind, pid, tok, jpeg, app_id = CALLS[-1]
        self.assertEqual((kind, pid, tok, app_id), ("wa", "5550001", "EAAtok", None))
        self.assertEqual(_cfg(self.wa_bot)["wa_app_id"], "987654")
        c.post(f"/bot/{self.wa_bot}/photo/sync", data={"csrf_token": "tk"})
        self.assertEqual(CALLS[-1][4], "987654", "App ID المخزَّن يُعاد استخدامه")

    def test_a_non_image_is_refused_and_removal_cleans_up(self):
        c = _client("photo_owner")
        self._up(c, self.tg_bot, _png())
        name = _cfg(self.tg_bot)["bot_photo"]
        CALLS.clear()
        self._up(c, self.tg_bot, b"<svg onload=alert(1)></svg>")
        self.assertEqual(CALLS, [])
        self.assertEqual(_cfg(self.tg_bot)["bot_photo"], name)
        c.post(f"/bot/{self.tg_bot}/photo/remove", data={"csrf_token": "tk"})
        self.assertEqual(CALLS[-1][0], "tg_rm")
        self.assertNotIn("bot_photo", _cfg(self.tg_bot))
        self.assertFalse(os.path.exists(os.path.join(web.BOT_PHOTO_DIR, name)))


class ProviderCallTests(unittest.TestCase):
    """شكل الطلبات نفسها لتليجرام وMeta — بلا شبكة."""

    def test_telegram_uses_set_my_profile_photo_multipart_with_attach(self):
        seen = {}

        class Resp:
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def read(self): return b'{"ok": true, "result": true}'

        def fake_open(req, timeout=None):
            seen["url"], seen["ctype"], seen["body"] = req.full_url, req.headers.get("Content-type"), req.data
            return Resp()
        orig = tg_helpers.urllib.request.urlopen
        tg_helpers.urllib.request.urlopen = fake_open
        try:
            jpeg = b"\xff\xd8\xff\xe0FAKEJPEG"
            self.assertEqual(tg_helpers.set_bot_photo("123:ABC", jpeg), (True, ""))
        finally:
            tg_helpers.urllib.request.urlopen = orig
        self.assertTrue(seen["url"].endswith("/bot123:ABC/setMyProfilePhoto"))
        self.assertIn("multipart/form-data; boundary=", seen["ctype"])
        self.assertIn(b'"attach://botphoto"', seen["body"])
        self.assertIn(b'"type": "static"', seen["body"])
        self.assertIn(jpeg, seen["body"])

    def test_whatsapp_runs_the_three_step_resumable_upload(self):
        log = []

        class R:
            def __init__(self, data, code=200): self._d, self.status_code = data, code
            def json(self): return self._d

        class FakeClient:
            def __init__(self, **k): pass
            def __enter__(self): return self
            def __exit__(self, *a): return False

            def get(self, url, headers=None, params=None):
                log.append(("GET", url, headers))
                return R({"id": "4242"})

            def post(self, url, headers=None, params=None, json=None, content=None):
                log.append(("POST", url, headers, params, json, content))
                if url.endswith("/4242/uploads"):
                    return R({"id": "upload:SESSION"})
                if url.endswith("/upload:SESSION"):
                    return R({"h": "HANDLE"})
                return R({"success": True})
        orig = WAC.httpx.Client
        WAC.httpx.Client = FakeClient
        try:
            ok, err, app_id = WAC.set_profile_photo("5550001", "EAAtok", b"\xff\xd8JPEG")
        finally:
            WAC.httpx.Client = orig
        self.assertEqual((ok, err, app_id), (True, "", "4242"))
        self.assertTrue(log[0][1].endswith("/app"))
        up = log[1]
        self.assertEqual(up[3]["file_type"], "image/jpeg")
        self.assertEqual(up[3]["file_length"], len(b"\xff\xd8JPEG"))
        data = log[2]
        self.assertEqual(data[2]["Authorization"], "OAuth EAAtok", "رفع البايتات بترويسة OAuth لا Bearer")
        self.assertEqual(data[2]["file_offset"], "0")
        prof = log[3]
        self.assertTrue(prof[1].endswith("/5550001/whatsapp_business_profile"))
        self.assertEqual(prof[4], {"messaging_product": "whatsapp", "profile_picture_handle": "HANDLE"})


if __name__ == "__main__":
    unittest.main(verbosity=2)
