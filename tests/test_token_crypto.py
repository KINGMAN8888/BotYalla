"""تشفير توكنات البوتات في القاعدة — والبحث بها رغم أن Fernet عشوائي.
أول نسخة من التشفير خزّنت نصاً عشوائياً وبقي البحث `WHERE token=?`، فضاع كل وارد
واتساب بصمت (`wa:<phone_id>` لا يطابق نصه المشفّر). هذه الاختبارات تمنع عودته.
    python tests/test_token_crypto.py
"""
import os, sqlite3, sys, tempfile, unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_TMP = tempfile.mkdtemp(prefix="botyalla-crypto-")
os.environ["BOTYALLA_DB"] = os.path.join(_TMP, "t.db")        # قبل أي استيراد
os.environ.pop("FERNET_KEY", None)                          # المسار الافتراضي: ملف المفتاح
os.environ.pop("BOTYALLA_KEYFILE", None)

import database as db                                        # noqa: E402
from cryptography.fernet import Fernet                       # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class TokenCryptoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        db.init_db()
        with db.get_conn() as c:
            c.execute("INSERT INTO users(username,pw_hash,role,created_at) VALUES('o','x','user',0)")
        cls.uid = db.get_user_by_name("o")["id"]

    def raw(self, bot_id):
        with db.get_conn() as c:
            return dict(c.execute("SELECT token, token_idx FROM bots WHERE id=?", (bot_id,)).fetchone())

    def test_stored_encrypted_but_found_by_token(self):
        bid = db.create_bot(self.uid, "wa", "wa:5550001", "flow", {}, "whatsapp")
        r = self.raw(bid)
        self.assertTrue(r["token"].startswith(db._ENC_PREFIX), "التوكن مخزّن نصاً")
        self.assertNotIn("5550001", r["token"])
        self.assertEqual(db.get_bot(bid)["token"], "wa:5550001")
        found = db.get_bot_by_token("wa:5550001")
        self.assertIsNotNone(found, "ويبهوك واتساب لن يجد البوت")
        self.assertEqual(found["id"], bid)
        self.assertNotIn("token_idx", found)
        self.assertIsNone(db.get_bot_by_token("wa:5550002"))

    def test_duplicate_token_refused(self):
        db.create_bot(self.uid, "a", "111:DUPLICATExxxxxxxxxxxxxx", "flow", {})
        with self.assertRaises(sqlite3.IntegrityError):
            db.create_bot(self.uid, "b", "111:DUPLICATExxxxxxxxxxxxxx", "flow", {})

    def test_legacy_rows_are_encrypted_and_rotated(self):
        legacy = Fernet(db._LEGACY_KEY).encrypt(b"222:LEGACYKEYxxxxxxxxxxxxx").decode()
        with db.get_conn() as c:
            c.execute("INSERT INTO bots(owner_id,name,token,template,config_json,created_at)"
                      " VALUES(?,?,?,?,?,0)", (self.uid, "old", legacy, "flow", "{}"))
            c.execute("INSERT INTO bots(owner_id,name,token,template,config_json,created_at)"
                      " VALUES(?,?,?,?,?,0)", (self.uid, "plain", "333:PLAINTEXTxxxxxxxxxxxxx", "flow", "{}"))
        db.init_db()                                           # التهجير عند كل تشغيل
        old = db.get_bot_by_token("222:LEGACYKEYxxxxxxxxxxxxx")
        plain = db.get_bot_by_token("333:PLAINTEXTxxxxxxxxxxxxx")
        self.assertIsNotNone(old); self.assertIsNotNone(plain)
        _, primary, _ = db._crypto()
        primary.decrypt(self.raw(old["id"])["token"].encode())      # دُوِّر للمفتاح الحالي
        self.assertTrue(self.raw(plain["id"])["token"].startswith(db._ENC_PREFIX))

    def test_migration_does_not_rewrite_healthy_rows(self):
        bid = db.create_bot(self.uid, "s", "444:STABLExxxxxxxxxxxxxxxxx", "flow", {})
        before = self.raw(bid)
        db.init_db()
        self.assertEqual(self.raw(bid), before)

    def test_wrong_key_fails_closed_and_is_not_overwritten(self):
        foreign = Fernet(Fernet.generate_key()).encrypt(b"555:FOREIGNxxxxxxxxxxxxxx").decode()
        with db.get_conn() as c:
            cur = c.execute("INSERT INTO bots(owner_id,name,token,template,config_json,created_at)"
                            " VALUES(?,?,?,?,?,0)", (self.uid, "f", foreign, "flow", "{}"))
            bid = cur.lastrowid
        self.assertEqual(db.get_bot(bid)["token"], "", "نص مشفّر مُرِّر على أنه توكن")
        db.init_db()
        self.assertEqual(self.raw(bid)["token"], foreign, "التهجير كتب فوق توكن لم يستطع فكّه")

    def test_rotated_token_replaces_lookup(self):
        bid = db.create_bot(self.uid, "r", "666:BEFORExxxxxxxxxxxxxxxxx", "flow", {})
        db.update_bot_token(bid, "666:AFTERxxxxxxxxxxxxxxxxxx")
        self.assertEqual(db.get_bot(bid)["token"], "666:AFTERxxxxxxxxxxxxxxxxxx")
        self.assertEqual(db.get_bot_by_token("666:AFTERxxxxxxxxxxxxxxxxxx")["id"], bid)
        self.assertIsNone(db.get_bot_by_token("666:BEFORExxxxxxxxxxxxxxxxx"))
        self.assertTrue(self.raw(bid)["token"].startswith(db._ENC_PREFIX))

    def test_key_lives_beside_the_db_not_in_code(self):
        path = db._key_path()
        self.assertTrue(os.path.isfile(path))
        self.assertTrue(path.startswith(_TMP), "ملف المفتاح خارج مجلد القاعدة")
        with open(path, "rb") as f:
            self.assertNotEqual(f.read().strip(), db._LEGACY_KEY)
        with open(os.path.join(REPO, ".gitignore"), encoding="utf-8") as f:
            self.assertIn(".token.key", f.read())


if __name__ == "__main__":
    unittest.main(verbosity=2)
