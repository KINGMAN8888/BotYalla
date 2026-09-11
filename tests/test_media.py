"""استقبال وسائط العملاء: التحقق من النوع، الحصة، ربطها بالـ lead، وخصوصية العرض.
    python tests/test_media.py
"""
import asyncio, io, json, os, shutil, sys, tempfile, time, unittest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)
os.chdir(_ROOT)
_TMP = tempfile.mkdtemp(prefix="botyalla-media-")
os.environ["BOTYALLA_DB"] = os.path.join(_TMP, "t.db")
os.environ["BOTYALLA_UPLOADS"] = _TMP
os.environ.setdefault("SECRET_KEY", "media-test")

import database as db                        # noqa: E402
import media_store                           # noqa: E402
import flow_engine                           # noqa: E402
import app as web                            # noqa: E402


JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 2048
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 2048
OGG = b"OggS" + b"\x00" * 2048
EXE = b"MZ\x90\x00" + b"\x00" * 2048

MEDIA_FLOW = {
    "start_message": "أهلاً",
    "end_message": "تم",
    "steps": [
        {"id": "s0", "type": "question", "prompt": "اسمك؟", "var": "الاسم"},
        {"id": "s1", "type": "media", "prompt": "أرسل صورة المشكلة:", "var": "الصورة"},
    ],
}


class FakeChannel:
    """قناة تحمل ملفاً واحداً جاهزاً للتنزيل، وتسجّل ما أُرسل للعميل."""
    def __init__(self, blob=JPEG, mime="image/jpeg", fail=False):
        self.sent, self.blob, self.mime, self.fail = [], blob, mime, fail

    async def send_text(self, peer, text): self.sent.append(text)
    async def send_buttons(self, peer, text, opts): self.sent.append(text)
    async def send_image(self, peer, url, caption=None): self.sent.append(caption)
    async def remove_keyboard(self, peer, text): self.sent.append(text)

    async def fetch_media(self, media):
        if self.fail:
            return None, None
        return self.blob, self.mime


class StoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        db.init_db()
        with db.get_conn() as c:
            c.execute("INSERT OR IGNORE INTO users(id,username,pw_hash,role,created_at)"
                      " VALUES(70,'m','x','user',0)")
        cls.bot = db.get_bot(db.create_bot(70, "b", "tk-media", "flow", {}))

    def save(self, data, mime="", quota=None):
        return media_store.save(self.bot, "tg:1", data, declared_mime=mime, quota=quota)

    def test_a_real_image_is_stored_on_disk(self):
        r = self.save(JPEG)
        self.assertTrue(r["ok"], r)
        self.assertEqual(r["kind"], "image")
        row = db.get_media(r["id"])
        self.assertTrue(os.path.exists(media_store.path_of(row["fname"])))

    def test_the_stored_name_is_generated_not_the_customers(self):
        r = self.save(PNG)
        row = db.get_media(r["id"])
        self.assertTrue(row["fname"].endswith(".png"))
        self.assertNotIn("/", row["fname"])
        self.assertNotIn("..", row["fname"])

    def test_an_executable_renamed_as_an_image_is_refused(self):
        """الامتداد المُعلَن لا يصنع نوعاً — البايتات تحكم."""
        r = self.save(EXE, mime="image/jpeg")
        self.assertFalse(r["ok"])
        self.assertEqual(r["reason"], "type")

    def test_an_unlisted_type_is_refused(self):
        r = self.save(b"%!PS-Adobe" + b"\x00" * 2048, mime="application/postscript")
        self.assertFalse(r["ok"])

    def test_an_oversized_image_is_refused_before_it_hits_the_disk(self):
        before = len(os.listdir(media_store.BASE_DIR)) if os.path.isdir(media_store.BASE_DIR) else 0
        r = self.save(JPEG[:4] + b"\x00" * (7 * 1024 * 1024))
        self.assertFalse(r["ok"])
        self.assertEqual(r["reason"], "too_large")
        after = len(os.listdir(media_store.BASE_DIR)) if os.path.isdir(media_store.BASE_DIR) else 0
        self.assertEqual(before, after, "كُتب ملف رغم تجاوزه الحد")

    def test_an_empty_file_is_refused(self):
        self.assertFalse(self.save(b"")["ok"])
        self.assertFalse(self.save(b"\xff\xd8\xff")["ok"])

    def test_the_quota_stops_storage(self):
        r = self.save(JPEG, quota=0)
        self.assertFalse(r["ok"])
        self.assertEqual(r["reason"], "quota")

    def test_audio_is_recognised_as_audio(self):
        r = self.save(OGG)
        self.assertTrue(r["ok"])
        self.assertEqual(r["kind"], "audio")


class EngineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        db.init_db()
        with db.get_conn() as c:
            c.execute("INSERT OR IGNORE INTO users(id,username,pw_hash,role,created_at)"
                      " VALUES(71,'m2','x','user',0)")
        db.activate_subscription(71, "pro", days=30)
        cls.bot_id = db.create_bot(71, "b2", "tk-media2", "flow", {"flow": MEDIA_FLOW})

    def setUp(self):
        self.bot = db.get_bot(self.bot_id)
        db.clear_chat_state(self.bot_id, "tg:5")

    def run_msg(self, ch, kind, text="", media=None):
        msg = {"peer": "tg:5", "kind": kind, "name": "y", "text": text}
        if media:
            msg["media"] = media
        asyncio.run(flow_engine.handle_message(self.bot, ch, msg))

    def test_a_photo_answers_the_media_step_and_lands_on_the_lead(self):
        ch = FakeChannel()
        self.run_msg(ch, "start", "/start")
        self.run_msg(ch, "text", "أحمد")
        self.run_msg(ch, "media", "صورة العطل", media={"ref": "f1", "mime": "image/jpeg"})

        with db.get_conn() as c:
            lead = c.execute("SELECT * FROM leads WHERE bot_id=? ORDER BY id DESC LIMIT 1",
                             (self.bot_id,)).fetchone()
        self.assertIsNotNone(lead, "لم يكتمل الفلو بعد إرسال الصورة")
        data = json.loads(lead["data_json"])
        self.assertIn("media:", data["الصورة"])
        self.assertIn("صورة العطل", data["الصورة"], "ضاع تعليق العميل")

        rows = db.list_leads(self.bot_id)
        self.assertEqual(len(rows[0]["media"]), 1, "الملف لم يُربط بالـ lead")
        self.assertEqual(rows[0]["media"][0]["kind"], "image")

    def test_text_on_a_media_step_asks_for_the_file_and_does_not_advance(self):
        ch = FakeChannel()
        self.run_msg(ch, "start", "/start")
        self.run_msg(ch, "text", "أحمد")
        step = db.get_chat_state(self.bot_id, "tg:5")["step"]
        self.run_msg(ch, "text", "مش هبعت صورة")
        after = db.get_chat_state(self.bot_id, "tg:5")
        self.assertEqual(after["step"], step, "تقدّم الفلو بلا الملف المطلوب")
        self.assertIn("الملف", ch.sent[-1])

    def test_a_photo_on_a_text_step_is_refused_and_not_stored(self):
        """حفظ كل ما يصل بابُ إغراق للقرص — نحفظ ما طُلب فقط."""
        ch = FakeChannel()
        self.run_msg(ch, "start", "/start")
        before = db.media_count_this_month(71)
        self.run_msg(ch, "media", "", media={"ref": "f9", "mime": "image/jpeg"})
        self.assertEqual(db.media_count_this_month(71), before)
        self.assertEqual(db.get_chat_state(self.bot_id, "tg:5")["step"], 0)

    def test_a_caption_on_a_text_step_is_taken_as_the_answer(self):
        ch = FakeChannel()
        self.run_msg(ch, "start", "/start")
        self.run_msg(ch, "media", "أحمد", media={"ref": "f8", "mime": "image/jpeg"})
        self.assertEqual(db.get_chat_state(self.bot_id, "tg:5")["data"]["الاسم"], "أحمد")

    def test_a_failed_download_keeps_the_step_and_tells_the_customer(self):
        ch = FakeChannel(fail=True)
        self.run_msg(ch, "start", "/start")
        self.run_msg(ch, "text", "أحمد")
        step = db.get_chat_state(self.bot_id, "tg:5")["step"]
        self.run_msg(ch, "media", "", media={"ref": "bad", "mime": "image/jpeg"})
        self.assertEqual(db.get_chat_state(self.bot_id, "tg:5")["step"], step)
        self.assertIn("تعذّر", ch.sent[-1])

    def test_an_exhausted_quota_never_downloads_the_file(self):
        db.activate_subscription(71, "free", days=30)
        try:
            with db.get_conn() as c:      # الباقة المجانية: 100 ملف شهرياً
                for i in range(100):
                    c.execute("INSERT INTO media(bot_id,owner_id,peer,kind,mime,size,fname,created_at)"
                              " VALUES(?,?,?,?,?,?,?,?)",
                              (self.bot_id, 71, "tg:9", "image", "image/jpeg", 10,
                               f"pad{i}.jpg", int(time.time())))
            ch = FakeChannel()
            self.run_msg(ch, "start", "/start")
            self.run_msg(ch, "text", "أحمد")
            self.run_msg(ch, "media", "", media={"ref": "f1", "mime": "image/jpeg"})
            self.assertIn("حدّ الملفات", ch.sent[-1])
        finally:
            with db.get_conn() as c:
                c.execute("DELETE FROM media WHERE peer='tg:9'")
            db.activate_subscription(71, "pro", days=30)

    def test_unsupported_messages_still_ask_for_text(self):
        ch = FakeChannel()
        self.run_msg(ch, "start", "/start")
        self.run_msg(ch, "unsupported", "")
        self.assertIn("نص", ch.sent[-1])
        self.assertEqual(db.get_chat_state(self.bot_id, "tg:5")["step"], 0)


class PrivacyTests(unittest.TestCase):
    """ملفات العملاء خاصة — لا يراها إلا مالك البوت."""

    @classmethod
    def setUpClass(cls):
        db.init_db()
        cls.owner = web.app.test_client()
        cls.other = web.app.test_client()
        for cl, name in ((cls.owner, "mowner"), (cls.other, "mother")):
            cl.get("/register")
            with cl.session_transaction() as s:
                tok = s.get("_csrf")
            cl.post("/register", data={"username": name, "password": "tst_" + os.urandom(6).hex(),
                                       "csrf_token": tok}, follow_redirects=True)
        with cls.owner.session_transaction() as s:
            cls.owner_uid = s.get("uid")
        cls.bot_id = db.create_bot(cls.owner_uid, "priv", "tk-priv", "flow", {})
        row = db.get_bot(cls.bot_id)
        r = media_store.save(row, "tg:3", JPEG, declared_mime="image/jpeg")
        cls.mid = r["id"]

    def test_the_owner_can_open_the_file(self):
        r = self.owner.get(f"/bot/{self.bot_id}/media/{self.mid}")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data[:4], JPEG[:4])

    def test_another_user_gets_404_not_the_file(self):
        r = self.other.get(f"/bot/{self.bot_id}/media/{self.mid}")
        self.assertEqual(r.status_code, 404)
        self.assertNotEqual(r.data[:4], JPEG[:4])

    def test_a_signed_out_visitor_is_sent_to_login(self):
        r = web.app.test_client().get(f"/bot/{self.bot_id}/media/{self.mid}")
        self.assertIn(r.status_code, (302, 401, 403))

    def test_a_media_id_from_another_bot_is_not_served(self):
        """المرجع وحده لا يكفي — الملكية مشروطة في الاستعلام."""
        other_bot = db.create_bot(self.owner_uid, "b2", "tk-priv2", "flow", {})
        r = self.owner.get(f"/bot/{other_bot}/media/{self.mid}")
        self.assertEqual(r.status_code, 404)

    def test_media_is_not_reachable_under_static(self):
        row = db.get_media(self.mid)
        self.assertEqual(web.app.test_client().get(f"/static/media/{row['fname']}").status_code, 404)
        self.assertEqual(web.app.test_client().get(f"/static/{row['fname']}").status_code, 404)


class CleanupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        db.init_db()
        with db.get_conn() as c:
            c.execute("INSERT OR IGNORE INTO users(id,username,pw_hash,role,created_at)"
                      " VALUES(72,'m3','x','user',0)")
        cls.bot = db.get_bot(db.create_bot(72, "b3", "tk-media3", "flow", {}))

    def test_orphans_are_collected_but_attached_files_are_kept(self):
        old = media_store.save(self.bot, "tg:7", JPEG, declared_mime="image/jpeg")
        kept = media_store.save(self.bot, "tg:8", PNG, declared_mime="image/png")
        with db.get_conn() as c:
            c.execute("UPDATE media SET created_at=? WHERE id=?",
                      (int(time.time()) - 8 * 24 * 3600, old["id"]))
            c.execute("UPDATE media SET lead_id=1, created_at=? WHERE id=?",
                      (int(time.time()) - 8 * 24 * 3600, kept["id"]))

        orphans = db.orphan_media()
        ids = [o["id"] for o in orphans]
        self.assertIn(old["id"], ids)
        self.assertNotIn(kept["id"], ids, "حُذف ملف مرتبط بـ lead")

        path = media_store.path_of(db.get_media(old["id"])["fname"])
        media_store.delete_files(orphans)
        db.drop_media(ids)
        self.assertFalse(os.path.exists(path))
        self.assertIsNone(db.get_media(old["id"]))
        self.assertIsNotNone(db.get_media(kept["id"]))


def tearDownModule():
    shutil.rmtree(_TMP, ignore_errors=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
