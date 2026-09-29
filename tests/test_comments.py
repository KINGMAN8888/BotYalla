"""أتمتة التعليقات (المرحلة 8): تعليق فيسبوك/إنستجرام ⇒ ردّ علني + رسالة خاصة، مرة واحدة، بلا حلقات.

Graph محاكاة — لا شبكة. القاعدة والملفات في مجلد مؤقت.
"""
import asyncio, json, os, secrets, sys, tempfile, unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_TMPDIR = tempfile.mkdtemp(prefix="botyalla-cmt-")
os.environ["BOTYALLA_DB"] = os.path.join(_TMPDIR, "test.db")   # قبل استيراد database
os.environ["BOTYALLA_UPLOADS"] = _TMPDIR
os.environ["BOTYALLA_LOGS"] = os.path.join(_TMPDIR, "logs")
os.environ["ADMIN_USER"] = "admin"
os.environ["ADMIN_PASS"] = "Cm#" + secrets.token_hex(6)

import auth                                # noqa: E402
import comments as CM                      # noqa: E402
import database as db                      # noqa: E402
import app as web                          # noqa: E402

PW = "Str0ng!Pass" + secrets.token_hex(3)
db.init_db(); web.seed_platform_defaults(); web.contact_defaults(); web.seed_default_admin()
web.app.config["TESTING"] = True


class R:
    def __init__(self, code, body=None):
        self.status_code, self._b = code, body or {}
        self.text = json.dumps(self._b)

    def json(self):
        return self._b


class Http:
    def __init__(self, fail=()):
        self.calls, self.fail = [], set(fail)

    async def post(self, url, params=None, json=None):
        self.calls.append((url, dict(params or {}), json))
        kind = "dm" if url.endswith("/me/messages") else "pub"
        return R(400, {"error": {"message": "(#10) not allowed"}}) if kind in self.fail else R(200, {"id": "x"})


def user(name):
    uid, err = db.create_account(name + secrets.token_hex(3), auth.hash_password(PW), f"{name}{secrets.token_hex(3)}@example.test",
                                 None, 30, "person", verify_required=False)
    assert not err, err
    db.mark_email_verified(uid)
    db.activate_subscription(uid, "enterprise", 30)
    return uid


def client(user_id):
    c = web.app.test_client()
    with c.session_transaction() as s:
        u = db.get_user(user_id)
        s.update(_csrf="tk", uid=user_id, uname=u["username"], role=u["role"], pwv=web._pw_stamp(u["pw_hash"]))
    return c


def post(c, url, body=None):
    return c.post(url, data=json.dumps(body or {}), content_type="application/json", headers={"X-CSRF-Token": "tk"})


RULES = {"enabled": True, "rules": [
    {"id": "price", "name": "السعر", "match": "contains", "keywords": ["سعر", "price"],
     "public": ["أرسلنا لك التفاصيل في الخاص 🌙 {{name}}"], "private": "أهلاً {{name}}! أسعار الجناح تبدأ من 900 ريال. اكتب «حجز» لنكمل.", "once": True},
    {"id": "promo", "match": "any", "posts": ["media_77"], "public": ["شكراً لتفاعلك 🌟"], "private": ""}]}


class Base(unittest.TestCase):
    def make(self, channel="instagram"):
        owner = user("so")
        own_id = str(17841400000000000 + secrets.randbelow(10**6))
        bot = db.create_bot(owner, "IG", f"{'ig' if channel == 'instagram' else 'fb'}:{own_id}", "flow",
                            {"page_token": db.seal("EAA-page"), "page_id": "1234567"}, channel)
        c = client(owner)
        r = post(c, f"/api/comments/{bot}/save", RULES).get_json()
        assert r["ok"], r
        return owner, c, bot, own_id

    def run_entry(self, bot, entry, pfx, http):
        return asyncio.run(CM.process(dict(db.get_bot(bot)), entry, pfx, "EAA-page", http=http))


def ig_entry(own, cid, text, media="media_1", uid="9001", uname="noura.sa"):
    return {"id": own, "changes": [{"field": "comments", "value": {
        "id": cid, "text": text, "from": {"id": uid, "username": uname}, "media": {"id": media}}}]}


class InstagramTests(Base):
    def test_keyword_comment_gets_public_reply_and_dm_once(self):
        _, _, bot, own = self.make()
        http = Http()
        self.assertEqual(self.run_entry(bot, ig_entry(own, "c1", "كم السعر؟"), "ig", http), 1)
        (u1, p1, _), (u2, p2, j2) = http.calls
        self.assertTrue(u1.endswith("/c1/replies"))
        self.assertEqual(p1["message"], "أرسلنا لك التفاصيل في الخاص 🌙 noura.sa")
        self.assertTrue(u2.endswith("/me/messages"))
        self.assertEqual(j2["recipient"], {"comment_id": "c1"})
        self.assertIn("900 ريال", j2["message"]["text"])
        self.assertEqual(self.run_entry(bot, ig_entry(own, "c1", "كم السعر؟"), "ig", http), 0, "Meta تعيد الحدث")
        self.assertEqual(self.run_entry(bot, ig_entry(own, "c2", "price please"), "ig", http), 0, "مرة لكل شخص في المنشور")
        self.assertEqual(self.run_entry(bot, ig_entry(own, "c3", "السعر", uid="9002", uname="x"), "ig", http), 1)
        self.assertEqual(len(http.calls), 4)

    def test_own_comments_unmatched_and_scoped_post_rules(self):
        _, _, bot, own = self.make()
        http = Http()
        self.assertEqual(self.run_entry(bot, ig_entry(own, "c9", "سعر", uid=own), "ig", http), 0, "ردودنا العلنية لا تُعالَج")
        self.assertEqual(self.run_entry(bot, ig_entry(own, "c10", "جميل جداً"), "ig", http), 0)
        self.assertEqual(self.run_entry(bot, ig_entry(own, "c11", "جميل جداً", media="media_77"), "ig", http), 1)
        self.assertEqual([u.rsplit("/", 2)[-2:] for u, _, _ in http.calls], [["c11", "replies"]], "قاعدة المنشور: علني فقط")

    def test_failures_are_recorded_and_stats(self):
        owner, c, bot, own = self.make()
        self.run_entry(bot, ig_entry(own, "c20", "سعر"), "ig", Http(fail={"dm"}))
        items = c.get(f"/api/comments/{bot}/recent").get_json()["items"]
        self.assertEqual((items[0]["public_ok"], items[0]["private_ok"]), (1, 0))
        self.assertIn("not allowed", items[0]["error"])
        self.assertEqual(CM.stats(bot)["price"], {"n": 1, "pub": 1, "dm": 0, "bad": 1})

    def test_disabled_does_nothing(self):
        _, c, bot, own = self.make()
        post(c, f"/api/comments/{bot}/save", dict(RULES, enabled=False))
        http = Http()
        self.assertEqual(self.run_entry(bot, ig_entry(own, "c30", "سعر"), "ig", http), 0)
        self.assertEqual(http.calls, [])


class FacebookTests(Base):
    def test_feed_comment_add_only(self):
        _, _, bot, own = self.make("messenger")
        http = Http()
        entry = {"id": own, "changes": [
            {"field": "feed", "value": {"item": "comment", "verb": "add", "comment_id": "p_1", "post_id": "post_1",
                                        "message": "بكم السعر", "from": {"id": "55", "name": "Ali Hassan"}}},
            {"field": "feed", "value": {"item": "comment", "verb": "edited", "comment_id": "p_2", "post_id": "post_1",
                                        "message": "سعر", "from": {"id": "56", "name": "x"}}},
            {"field": "feed", "value": {"item": "reaction", "verb": "add", "post_id": "post_1", "from": {"id": "57"}}}]}
        self.assertEqual(self.run_entry(bot, entry, "fb", http), 1)
        self.assertTrue(http.calls[0][0].endswith("/p_1/comments"))
        self.assertEqual(http.calls[0][1]["message"], "أرسلنا لك التفاصيل في الخاص 🌙 Ali")


class ValidationTests(Base):
    def test_rules_validation_and_access(self):
        owner, c, bot, own = self.make()
        bad = [({"rules": [{"match": "contains", "keywords": [], "public": ["x"]}]}, "rule:keywords"),
               ({"rules": [{"match": "any", "public": [], "private": ""}]}, "rule:action"),
               ({"rules": [{"match": "any", "posts": ["bad id!"], "public": ["x"]}]}, "rule:posts"),
               ({"rules": [{"id": "a", "match": "any", "public": ["x"]}, {"id": "a", "match": "any", "public": ["y"]}]}, "rule:id")]
        for body, err in bad:
            self.assertEqual(post(c, f"/api/comments/{bot}/save", body).get_json()["error"], err)
        wa = db.create_bot(owner, "WA", f"wa:{secrets.randbelow(10**12)}", "flow", {}, "whatsapp")
        self.assertEqual(post(c, f"/api/comments/{wa}/save", RULES).get_json()["error"], "bot")
        other = client(user("x"))
        self.assertEqual(post(other, f"/api/comments/{bot}/save", RULES).status_code, 404)
        page = c.get("/growth").get_data(as_text=True)
        self.assertNotIn("EAA-page", page)
        cfg = json.loads(db.get_bot(bot)["config_json"])
        self.assertTrue(cfg["page_token"], "حفظ القواعد لا يمسح توكن الصفحة")


if __name__ == "__main__":
    unittest.main(verbosity=2)
