"""الإنشاء بضغطة (§1) · الوصول للبوت (§2) · مكتبة الوسائط (§6) — كل الشبكة مستبدَلة.
    python tests/test_managed_media.py
"""
import asyncio, io, json, os, struct, sys, tempfile, unittest, zlib

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_TMP = tempfile.mkdtemp(prefix="botyalla-managed-")
os.environ["BOTYALLA_DB"] = os.path.join(_TMP, "t.db")        # قبل أي استيراد
os.environ["BOTYALLA_UPLOADS"] = _TMP
os.environ["BOTYALLA_LOGS"] = _TMP

import database as db          # noqa: E402
import managed_bots as MB      # noqa: E402
import asset_store             # noqa: E402
import tg_helpers as tg        # noqa: E402
import app as A                # noqa: E402
from bot_manager import manager  # noqa: E402


def png(w=4, h=4):
    raw = b"".join(b"\x00" + b"\x10\x80\xf0" * w for _ in range(h))
    ch = lambda t, d: struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xffffffff)
    return (b"\x89PNG\r\n\x1a\n" + ch(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + ch(b"IDAT", zlib.compress(raw)) + ch(b"IEND", b""))


class FakePlatformBot:
    username = "BotYallaBot"

    def __init__(self, token="888888:MANAGEDtokenABCDEFGHIJKLMN"):
        self.token, self.msgs, self.calls = token, [], []

    async def do_api_request(self, endpoint, api_kwargs=None, **k):
        self.calls.append((endpoint, api_kwargs))
        return self.token

    async def send_message(self, **k):
        self.msgs.append(k.get("text"))


class _Resp:
    def __init__(self, d): self.d = json.dumps(d).encode()
    def read(self): return self.d
    def __enter__(self): return self
    def __exit__(self, *a): return False


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        tg.urllib.request.urlopen = lambda *a, **k: _Resp(
            {"ok": True, "result": {"id": 5, "username": "shop_bot", "first_name": "Shop"}})
        tg._tg_post = lambda *a, **k: (True, "OK")
        db.init_db()
        with db.get_conn() as c:
            c.execute("INSERT OR IGNORE INTO users(id,username,pw_hash,role,created_at) VALUES(1,'root','x','admin',0)")
            c.execute("INSERT INTO users(username,pw_hash,role,created_at) VALUES('owner','x','user',0)")
            c.execute("INSERT INTO users(username,pw_hash,role,created_at) VALUES('other','x','user',0)")
        cls.uid = db.get_user_by_name("owner")["id"]
        cls.other = db.get_user_by_name("other")["id"]
        cls.c = cls.client(cls.uid)

        async def ok_start(bot_id): return True, "ok"
        async def ok_notify(*a, **k): return True
        manager.start_bot_async = ok_start
        manager.notify_text_async = ok_notify
        manager.platform_info = lambda: {"username": "BotYallaBot", "can_manage": True}

    @staticmethod
    def client(uid):
        c = A.app.test_client()
        with c.session_transaction() as s:
            s["uid"] = uid; s["_csrf"] = "m" * 32
        return c

    def post(self, url, body=None, client=None, **kw):
        return (client or self.c).post(url, json=body, headers={"X-CSRF-Token": "m" * 32}, **kw)


class ManagedBotsTests(Base):
    def setUp(self):
        with db.get_conn() as c:
            c.execute("DELETE FROM bots WHERE owner_id IN (?,?)", (self.uid, self.other))
            c.execute("DELETE FROM managed_bot_requests")
            c.execute("DELETE FROM settings WHERE key='tg_chat_id'")

    def request(self, name="Raghad Tailor", template="customer_service"):
        d = self.post("/bot/create/managed", {"name": name, "template": template}).get_json()
        self.assertTrue(d["ok"], d)
        return d, d["link"].split("?start=mb-", 1)[1]

    def test_link_qr_and_hashed_code(self):
        d, code = self.request()
        self.assertTrue(d["link"].startswith("https://t.me/BotYallaBot?start=mb-"))
        self.assertTrue(d["qr"].startswith("data:image/svg+xml;base64,"))
        self.assertRegex(d["suggested"], r"^[a-z][a-z0-9_]{2,}_\d{3}_bot$")
        with db.get_conn() as c:
            stored = c.execute("SELECT token_hash FROM managed_bot_requests").fetchone()[0]
        self.assertNotEqual(stored, code, "الكود مخزّن نصاً")

    def test_end_to_end_creation(self):
        d, code = self.request()
        self.assertIsNotNone(db.link_managed_request(MB.token_hash(code), 4242))
        pb = FakePlatformBot()
        bid = asyncio.run(MB.provision(pb, 4242, {"id": 888, "username": "raghad_tailor_123_bot",
                                                  "first_name": "Raghad"}))
        row = db.get_bot(bid)
        self.assertEqual(row["owner_id"], self.uid)
        self.assertEqual(row["token"], pb.token)
        cfg = json.loads(row["config_json"])
        self.assertEqual((cfg["owner_chat_id"], cfg["tg_bot_id"], cfg["created_via"]), ("4242", 888, "managed"))
        self.assertEqual(pb.calls[0], ("getManagedBotToken", {"user_id": 888}))
        self.assertEqual(db.get_setting(self.uid, "tg_chat_id"), "4242", "حساب تليجرام لم يُربط")
        st = self.c.get(f"/bot/create/managed/{d['id']}").get_json()
        self.assertEqual((st["status"], st["bot_id"]), ("created", bid))

    def test_code_is_single_use_and_bound(self):
        _, code = self.request()
        self.assertIsNotNone(db.link_managed_request(MB.token_hash(code), 1))
        self.assertIsNone(db.link_managed_request(MB.token_hash(code), 2), "حساب ثانٍ استولى على الطلب")

    def test_new_request_supersedes_old(self):
        _, old = self.request()
        self.request(name="Second")
        self.assertIsNone(db.link_managed_request(MB.token_hash(old), 1))

    def test_expired_code_refused(self):
        d, code = self.request()
        with db.get_conn() as c:
            c.execute("UPDATE managed_bot_requests SET expires_at=0")
        self.assertIsNone(db.link_managed_request(MB.token_hash(code), 1))
        self.assertEqual(self.c.get(f"/bot/create/managed/{d['id']}").get_json()["status"], "expired")

    def test_unknown_telegram_user_creates_nothing(self):
        pb = FakePlatformBot()
        self.assertIsNone(asyncio.run(MB.provision(pb, 31337, {"id": 999, "username": "x_bot"})))
        self.assertEqual(db.count_user_bots(self.uid), 0)

    def test_duplicate_update_creates_one_bot(self):
        _, code = self.request()
        db.link_managed_request(MB.token_hash(code), 7)
        pb = FakePlatformBot()
        a = asyncio.run(MB.provision(pb, 7, {"id": 700, "username": "a_bot"}))
        b = asyncio.run(MB.provision(pb, 7, {"id": 700, "username": "a_bot"}))
        self.assertEqual(a, b)
        self.assertEqual(db.count_user_bots(self.uid), 1)

    def test_token_rotation_updates_existing_bot(self):
        _, code = self.request()
        db.link_managed_request(MB.token_hash(code), 8)
        bid = asyncio.run(MB.provision(FakePlatformBot(), 8, {"id": 800, "username": "b_bot"}))
        asyncio.run(MB.provision(FakePlatformBot("800800:ROTATEDtokenABCDEFGHIJK"), 8, {"id": 800}))
        self.assertEqual(db.get_bot(bid)["token"], "800800:ROTATEDtokenABCDEFGHIJK")

    def test_plan_limit_checked_again_at_creation(self):
        _, code = self.request()
        db.link_managed_request(MB.token_hash(code), 9)
        db.create_bot(self.uid, "manual", "1:MANUALxxxxxxxxxxxxxxxxxx", "flow", {})   # الباقة المجانية: بوت واحد
        pb = FakePlatformBot()
        self.assertIsNone(asyncio.run(MB.provision(pb, 9, {"id": 900, "username": "c_bot"})))
        self.assertEqual(db.count_user_bots(self.uid), 1)
        self.assertTrue(any("حد" in (m or "") for m in pb.msgs))

    def test_unavailable_without_management_mode(self):
        orig = manager.platform_info
        manager.platform_info = lambda: {"username": "BotYallaBot", "can_manage": False}
        try:
            d = self.post("/bot/create/managed", {"name": "x", "template": "flow"}).get_json()
        finally:
            manager.platform_info = orig
        self.assertFalse(d["ok"]); self.assertTrue(d["unavailable"])

    def test_status_is_owner_only(self):
        d, _ = self.request()
        self.assertEqual(self.client(self.other).get(f"/bot/create/managed/{d['id']}").status_code, 404)

    def test_extract_handles_both_shapes(self):
        class U:  # PTB 21.6: الحقول المجهولة في api_kwargs
            api_kwargs = {"managed_bot": {"user": {"id": 1}, "bot": {"id": 2, "username": "z_bot"}}}
            message = None
        self.assertEqual(MB.extract(U())[0], 1)
        self.assertRegex(MB.suggest_username("محل رغد للتفصيل"), r"^[a-z][a-z0-9_]{2,}_\d{3}_bot$")
        self.assertLessEqual(len(MB.suggest_username("x" * 80)), 32)


class LinksTests(Base):
    def test_qr_poster_and_links(self):
        bid = db.create_bot(self.uid, "رغد", "2:LINKSxxxxxxxxxxxxxxxxxxx", "flow",
                            {"business_name": "رغد <b>", "bot_username": "raghad_bot"})
        r = self.c.get(f"/bot/{bid}/qr.svg?src=poster")
        self.assertEqual((r.status_code, r.mimetype), (200, "image/svg+xml"))
        r = self.c.get(f"/bot/{bid}/poster")
        self.assertEqual(r.status_code, 200)
        self.assertNotIn(b"<b>", r.data, "اسم النشاط لم يُهرَّب في الملصق")
        self.assertIn(b"nonce=", r.data)
        page = self.c.get(f"/bot/{bid}").data.decode()
        self.assertIn("t.me/raghad_bot?start=src-link", page)
        self.assertEqual(self.client(self.other).get(f"/bot/{bid}/qr.svg").status_code, 404)


class AssetsTests(Base):
    def upload(self, data, name="f.png", client=None):
        return self.post("/api/assets/upload", None, client=client,
                         data={"file": (io.BytesIO(data), name)},
                         content_type="multipart/form-data").get_json()

    def test_upload_serve_delete(self):
        d = self.upload(png())
        self.assertTrue(d["ok"])
        aid = d["asset"]["id"]
        self.assertEqual(self.c.get(f"/assets/{aid}").mimetype, "image/png")
        self.assertEqual(self.client(self.other).get(f"/assets/{aid}").status_code, 404)
        self.assertEqual(self.post(f"/api/assets/{aid}/delete", client=self.client(self.other)).status_code, 404)
        self.assertTrue(self.post(f"/api/assets/{aid}/delete").get_json()["ok"])
        self.assertIsNone(db.get_asset(aid))

    def test_type_is_sniffed_not_trusted(self):
        self.assertFalse(self.upload(b"MZ" + b"\0" * 500, "cute.jpg")["ok"])
        mov = b"\0\0\0\x14ftypqt  " + b"\0" * 200                      # QuickTime ليس MP4
        self.assertFalse(asset_store.validate(mov)["ok"])
        mp4 = b"\0\0\0\x18ftypisom" + b"\0" * 200
        self.assertEqual(asset_store.validate(mp4)["kind"], "video")

    def test_quota_enforced(self):
        orig = A.plans.asset_bytes_limit
        A.plans.asset_bytes_limit = lambda pid: 10
        try:
            d = self.upload(png())
        finally:
            A.plans.asset_bytes_limit = orig
        self.assertFalse(d["ok"]); self.assertTrue(d.get("upgrade"))

    def test_ssrf_guards(self):
        for url in ("http://example.com/a.png", "https://127.0.0.1/a.png", "https://10.0.0.5/a.png",
                    "https://169.254.169.254/latest", "https://user:pw@example.com/a.png",
                    "https://example.com:8443/a.png", "ftp://example.com/a.png"):
            data, err = asset_store.fetch_url(url)
            self.assertIsNone(data, url)
            self.assertIn(err, ("url", "host"), url)

    def test_foreign_asset_not_attachable(self):
        mine = self.upload(png())["asset"]["id"]
        theirs = self.upload(png(), client=self.client(self.other))["asset"]["id"]
        bid = db.create_bot(self.uid, "b", "3:ASSETxxxxxxxxxxxxxxxxxxx", "flow", {"business_name": "b"})
        self.c.post(f"/bot/{bid}/config", data={"business_name": "b", "welcome_asset": str(theirs),
                                                "csrf_token": "m" * 32})
        self.assertIsNone(json.loads(db.get_bot(bid)["config_json"]).get("welcome_asset"))
        self.c.post(f"/bot/{bid}/config", data={"business_name": "b", "welcome_asset": str(mine),
                                                "csrf_token": "m" * 32})
        self.assertEqual(json.loads(db.get_bot(bid)["config_json"])["welcome_asset"], mine)

    def test_flow_show_step_saved_with_own_asset(self):
        aid = self.upload(png())["asset"]["id"]
        bid = db.create_bot(self.uid, "f", "4:FLOWxxxxxxxxxxxxxxxxxxxx", "flow", {"business_name": "f"})
        self.c.post(f"/bot/{bid}/flow", data={
            "start_message": "hi", "end_message": "bye", "csrf_token": "m" * 32,
            "s_type": ["show", "media"], "s_prompt": ["شوف الموديل", "ابعت صورتك"],
            "s_var": ["اختيار", "صورة"], "s_options": ["أعجبني, غيره", ""],
            "s_asset": [str(aid), ""], "s_optional": ["", "1"]})
        steps = json.loads(db.get_bot(bid)["config_json"])["flow"]["steps"]
        self.assertEqual(steps[0]["asset"], aid)
        self.assertEqual(steps[0]["options"], ["أعجبني", "غيره"])
        self.assertTrue(steps[1]["optional"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
