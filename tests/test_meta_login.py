"""ماسنجر + إنستجرام بضغطة للعملاء: الباقة تحكم · state يمنع كوداً غريباً · التوكن لا يصل المتصفح
ويُحفظ مختوماً ويُمسح بعد الربط · البوتات لصاحب العمل وتعمل فوراً · حدّ البوتات · الموظف العادي لا يربط ·
حساب مربوط عند غيرك مقفول · انتهاء الصلاحية · الباقات والصفحة العامة تعرض القنوات."""
import json, os, secrets, sys, tempfile, time, unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_TMPDIR = tempfile.mkdtemp(prefix="botyalla-metalogin-")
os.environ["BOTYALLA_DB"] = os.path.join(_TMPDIR, "test.db")   # قبل استيراد database
os.environ["BOTYALLA_UPLOADS"] = _TMPDIR
os.environ["BOTYALLA_LOGS"] = os.path.join(_TMPDIR, "logs")
os.environ["ADMIN_USER"] = "admin"
os.environ["ADMIN_PASS"] = "Ml#" + secrets.token_hex(6)
os.environ["META_APP_ID"] = "1234567890123"
os.environ["PUBLIC_URL"] = "https://app.example.test"
os.environ.pop("META_PAGES_CONFIG_ID", None)

import auth                                # noqa: E402
import database as db                      # noqa: E402
import app as web                          # noqa: E402
import meta_pages as MP                    # noqa: E402
import plans                               # noqa: E402

PW = "Str0ng!Pass" + secrets.token_hex(3)
db.init_db(); web.seed_platform_defaults(); web.contact_defaults(); web.seed_default_admin()
web.app.config["TESTING"] = True
db.set_platform("wa_app_secret", "s3cret-app")
USER_TOKEN = "EAAuserLONG" + secrets.token_hex(16)
PAGE_TOKEN = "EAApage" + secrets.token_hex(16)


def user(name, plan="merchant"):
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


class FakeMeta:
    """يستبدل نداءات Graph: كود ⇒ توكن، صفحات المستخدم، والربط."""
    def __init__(self):
        n = lambda: str(10**11 + secrets.randbelow(10**11))      # صفحات فريدة لكل اختبار (القاعدة مشتركة)
        self.pages = [{"id": n(), "name": "فندق الفرسان", "category": "Hotel", "picture": "", "can_message": True,
                       "ig": {"id": n(), "username": "alforsan", "picture": ""}},
                      {"id": n(), "name": "Page Two", "category": "", "picture": "", "can_message": True, "ig": None}]
        self.exchanged = []

    def install(self):
        self.orig = (MP.login_exchange, MP.list_pages, MP.connect)
        MP.login_exchange = self.exchange
        MP.list_pages = lambda tok: (self.pages if tok == USER_TOKEN else (_ for _ in ()).throw(MP.PagesError("pages", "bad")))
        MP.connect = self.connect

    def restore(self):
        MP.login_exchange, MP.list_pages, MP.connect = self.orig

    def exchange(self, code, redirect, app_id, secret):
        self.exchanged.append((code, redirect, app_id, secret))
        return USER_TOKEN

    def connect(self, page_id, token, app_id="", secret="", ig_hint=""):
        assert token == USER_TOKEN
        p = next((x for x in self.pages if x["id"] == page_id), None)
        if not p:
            raise MP.PagesError("page", "this token has no access to that Page")
        ig = p["ig"] or {}
        return {"page_token": PAGE_TOKEN, "name": p["name"], "ig_id": ig.get("id", ""), "ig_username": ig.get("username", ""),
                "ig_reason": "", "warning": "", "username": ""}


def login(c):
    """start ← return (state صحيح) ← pages بالكود."""
    r = post(c, "/meta/login/start").get_json()
    assert r["ok"], r
    state = r["url"].split("state=")[1].split("&")[0]
    html = c.get(f"/meta/login/return?state={state}&code=CODE123").get_data(as_text=True)
    assert "CODE123" in html
    return post(c, "/meta/login/pages", {"code": "CODE123"}).get_json()


class Flow(unittest.TestCase):
    def setUp(self):
        self.fake = FakeMeta(); self.fake.install()
        web._login_attempts.clear()

    def tearDown(self):
        self.fake.restore()

    def test_free_plan_sees_an_upgrade_and_cannot_start(self):
        c = client(user("fr", None))
        r = post(c, "/meta/login/start")
        self.assertEqual(r.status_code, 403)
        self.assertTrue(r.get_json()["upgrade"])

    def test_dialog_url_asks_for_page_permissions_with_our_return(self):
        c = client(user("mu"))
        url = post(c, "/meta/login/start").get_json()["url"]
        self.assertTrue(url.startswith("https://www.facebook.com/"))
        for part in ("client_id=1234567890123", "pages_messaging", "instagram_manage_messages",
                     "redirect_uri=https%3A%2F%2Fapp.example.test%2Fmeta%2Flogin%2Freturn"):
            self.assertIn(part, url)

    def test_foreign_state_or_code_is_refused(self):
        c = client(user("st"))
        post(c, "/meta/login/start")
        html = c.get("/meta/login/return?state=forged&code=EVIL").get_data(as_text=True)
        self.assertNotIn("EVIL", html)
        self.assertIn('"state"', html)
        self.assertEqual(post(c, "/meta/login/pages", {"code": "EVIL"}).status_code, 400)   # بلا نافذة بدأتها الجلسة
        self.assertEqual(self.fake.exchanged, [])

    def test_pages_never_expose_tokens_and_the_token_is_sealed(self):
        u = user("pg")
        c = client(u)
        r = login(c)
        self.assertEqual([p["id"] for p in r["pages"]], [x["id"] for x in self.fake.pages])
        self.assertEqual(r["slots"], 3)
        self.assertEqual(self.fake.exchanged[0][1], "https://app.example.test/meta/login/return")   # نفس redirect_uri
        blob = json.dumps(r)
        self.assertNotIn(USER_TOKEN, blob)
        self.assertNotIn("access_token", blob)
        stored = db.get_setting(u, "meta_login_tmp")
        self.assertNotIn(USER_TOKEN, stored)
        self.assertEqual(db.unseal(json.loads(stored)["t"]), USER_TOKEN)

    def test_finish_creates_live_bots_for_the_account_and_forgets_the_token(self):
        u = user("fi")
        c = client(u)
        login(c)
        r = post(c, "/meta/login/finish", {"page_id": self.fake.pages[0]["id"], "messenger": True, "instagram": True,
                                           "template": "booking", "name": "الفرسان"}).get_json()
        self.assertTrue(r["ok"], r)
        self.assertEqual(sorted(b["channel"] for b in r["bots"]), ["instagram", "messenger"])
        bots = {b["channel"]: b for b in db.list_bots(u)}
        self.assertEqual(bots["messenger"]["token"], "fb:" + self.fake.pages[0]["id"])
        self.assertEqual(bots["instagram"]["token"], "ig:" + self.fake.pages[0]["ig"]["id"])
        self.assertTrue(all(b["is_active"] for b in bots.values()))
        self.assertEqual(bots["messenger"]["template"], "booking")
        cfg = json.loads(bots["messenger"]["config_json"])
        self.assertNotIn(PAGE_TOKEN, bots["messenger"]["config_json"])              # مختوم
        self.assertEqual(db.unseal(cfg["page_token"]), PAGE_TOKEN)
        self.assertIsNone(db.get_setting(u, "meta_login_tmp"))
        self.assertEqual(post(c, "/meta/login/finish", {"page_id": self.fake.pages[0]["id"], "messenger": True}).get_json()["error"], "expired")

    def test_instagram_only_needs_a_linked_account(self):
        c = client(user("ig"))
        login(c)
        r = post(c, "/meta/login/finish", {"page_id": self.fake.pages[1]["id"], "instagram": True}).get_json()
        self.assertFalse(r["ok"])
        self.assertEqual(r["step"], "instagram")

    def test_plan_bot_limit(self):
        u = user("lm")
        for i in range(2):
            db.create_bot(u, f"T{i}", f"{secrets.randbelow(10**9)}:AA{secrets.token_hex(8)}", "flow", {}, "telegram")
        c = client(u)
        self.assertEqual(login(c)["slots"], 1)
        r = post(c, "/meta/login/finish", {"page_id": self.fake.pages[0]["id"], "messenger": True, "instagram": True})
        self.assertEqual(r.status_code, 403)
        self.assertTrue(r.get_json()["upgrade"])
        self.assertTrue(post(c, "/meta/login/finish", {"page_id": self.fake.pages[0]["id"], "messenger": True}).get_json()["ok"])

    def test_team_member_cannot_connect_but_admin_does_for_the_owner(self):
        owner = user("ow", "enterprise")
        mem, adm = user("me", None), user("ad", None)
        db.join_team(owner, mem, "member"); db.join_team(owner, adm, "admin")
        self.assertEqual(post(client(mem), "/meta/login/start").status_code, 403)
        c = client(adm)
        login(c)
        self.assertTrue(post(c, "/meta/login/finish", {"page_id": self.fake.pages[1]["id"], "messenger": True}).get_json()["ok"])
        self.assertEqual([b["channel"] for b in db.list_bots(owner)], ["messenger"])

    def test_a_page_used_by_another_account_is_marked_and_refused(self):
        other = user("ot")
        db.create_bot(other, "X", "fb:" + self.fake.pages[0]["id"], "flow", {}, "messenger")
        c = client(user("ta"))
        p = login(c)["pages"][0]
        self.assertEqual(p["linked"]["messenger"], "taken")
        r = post(c, "/meta/login/finish", {"page_id": self.fake.pages[0]["id"], "messenger": True}).get_json()
        self.assertFalse(r["ok"])

    def test_expired_login(self):
        u = user("ex")
        c = client(u)
        login(c)
        d = json.loads(db.get_setting(u, "meta_login_tmp")); d["at"] -= web.META_LOGIN_TTL + 5
        db.set_setting(u, "meta_login_tmp", json.dumps(d))
        self.assertEqual(post(c, "/meta/login/finish", {"page_id": self.fake.pages[0]["id"], "messenger": True}).get_json()["error"], "expired")


class Surface(unittest.TestCase):
    def test_plans_include_meta_from_merchant(self):
        self.assertFalse(plans.plan("free").get("meta"))
        for pid in ("merchant", "whatsapp", "vip", "agency", "enterprise", "pro", "business"):
            self.assertTrue(plans.plan(pid).get("meta"), pid)

    def test_dashboard_card_locked_for_free_open_for_merchant(self):
        import re
        def boot(uid):
            html = client(uid).get("/dashboard").get_data(as_text=True)
            return json.loads(re.search(r"window\.BY\s*=\s*(\{.*?\});\s*</script>", html, re.S).group(1))["props"]["metaLogin"]
        self.assertEqual((boot(user("cf", None))["allowed"], boot(user("cf2", None))["upgrade"]), (False, True))
        self.assertTrue(boot(user("cm"))["allowed"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
