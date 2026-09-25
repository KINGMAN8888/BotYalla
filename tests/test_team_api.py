"""فريق الحساب · بوابة الأسرار · مفاتيح الـAPI · تمرير الوارد للشريك.

    python tests/test_team_api.py
"""
import json, os, secrets, sys, tempfile, time, unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_TMPDIR = tempfile.mkdtemp(prefix="botyalla-team-")
os.environ["BOTYALLA_DB"] = os.path.join(_TMPDIR, "test.db")   # قبل استيراد database
os.environ["BOTYALLA_UPLOADS"] = _TMPDIR
os.environ["BOTYALLA_LOGS"] = os.path.join(_TMPDIR, "logs")
os.environ["ADMIN_USER"] = "admin"
os.environ["ADMIN_PASS"] = "tm_" + secrets.token_hex(6)
os.environ.setdefault("PUBLIC_URL", "https://example.test")

import database as db                      # noqa: E402
import app as web                          # noqa: E402
import auth                                # noqa: E402

PW = "Str0ng!Pass" + secrets.token_hex(3)


def _boot():
    db.init_db()
    web.seed_platform_defaults()
    web.contact_defaults()
    web.seed_default_admin()
    web.app.config["TESTING"] = True


def _user(name):
    uid, err = db.create_account(name, auth.hash_password(PW), f"{name}@example.test",
                                 None, 30, "person", verify_required=False)
    assert not err, err
    db.mark_email_verified(uid)
    return uid


def _client(user_id=None):
    c = web.app.test_client()
    with c.session_transaction() as s:
        s["_csrf"] = "tk"
        if user_id:
            u = db.get_user(user_id)
            s.update(uid=user_id, uname=u["username"], role=u["role"])
    return c


def _wa_bot(owner_id, phone_id, token="EAA-secret-token"):
    """بوت واتساب كما ينشئه الربط بضغطة: token = wa:<phone_id> والتوكن في الإعداد."""
    bid = db.create_bot(owner_id, "بوت واتساب", f"wa:{phone_id}", "store", {})
    db.update_bot_config(bid, {"wa_token": token, "wa_waba_id": "10099887766"})
    return bid


_boot()
OWNER = _user("owner" + secrets.token_hex(3))
STAFF = _user("staff" + secrets.token_hex(3))
BOT = _wa_bot(OWNER, "5550001")


class AccountVsUserTests(unittest.TestCase):
    """`account_of` هي النقطة الوحيدة التي تفرّق بين المستخدم والحساب."""

    def test_a_lone_user_is_their_own_account(self):
        self.assertEqual(db.account_of(OWNER), OWNER)
        self.assertEqual(db.team_role(OWNER), "owner")

    def test_a_member_works_inside_the_owner_account(self):
        m = _user("m" + secrets.token_hex(3))
        self.assertEqual(db.join_team(OWNER, m, "member"), "")
        self.assertEqual(db.account_of(m), OWNER)
        self.assertEqual(db.team_role(m), "member")
        # البوتات التي يراها = بوتات الحساب لا بوتاته هو
        self.assertTrue(db.list_bots(db.account_of(m)))
        self.assertFalse(db.list_bots(m))

    def test_someone_who_owns_bots_cannot_join(self):
        other = _user("o" + secrets.token_hex(3))
        db.create_bot(other, "بوته هو", f"T:{secrets.token_hex(5)}", "store", {})
        self.assertEqual(db.join_team(OWNER, other, "member"), "has_bots")
        self.assertEqual(db.account_of(other), other)      # لم تختفِ بوتاته

    def test_an_owner_of_a_team_cannot_become_a_member(self):
        boss = _user("b" + secrets.token_hex(3))
        emp = _user("e" + secrets.token_hex(3))
        db.join_team(boss, emp, "member")
        self.assertEqual(db.join_team(OWNER, boss, "member"), "has_team")

    def test_nobody_joins_themselves(self):
        self.assertEqual(db.join_team(OWNER, OWNER, "admin"), "self")

    def test_removing_a_member_keeps_their_login(self):
        m = _user("r" + secrets.token_hex(3))
        db.join_team(OWNER, m, "member")
        self.assertTrue(db.remove_team_member(OWNER, m))
        self.assertEqual(db.account_of(m), m)
        self.assertIsNotNone(db.get_user(m))


class TeamInviteTests(unittest.TestCase):
    """الرابط المخصّص: يُستعمل مرة واحدة، ولا يُخزَّن نصّه."""

    def test_a_valid_invite_admits_once(self):
        tok = secrets.token_urlsafe(24)
        db.create_team_invite(OWNER, tok, role="admin")
        self.assertIsNotNone(db.team_invite(tok))
        m = _user("i" + secrets.token_hex(3))
        self.assertEqual(db.use_team_invite(tok, m), "")
        self.assertEqual(db.team_role(m), "admin")
        self.assertIsNone(db.team_invite(tok))             # استُهلكت
        m2 = _user("i2" + secrets.token_hex(3))
        self.assertEqual(db.use_team_invite(tok, m2), "invalid")

    def test_the_raw_token_is_never_stored(self):
        tok = secrets.token_urlsafe(24)
        db.create_team_invite(OWNER, tok)
        with db.get_conn() as c:
            rows = c.execute("SELECT token_idx FROM team_invites").fetchall()
        self.assertTrue(rows)
        self.assertFalse(any(tok in (r["token_idx"] or "") for r in rows))

    def test_an_expired_invite_is_refused(self):
        tok = secrets.token_urlsafe(24)
        iid = db.create_team_invite(OWNER, tok)
        with db.get_conn() as c:
            c.execute("UPDATE team_invites SET expires_at=? WHERE id=?",
                      (int(time.time()) - 5, iid))
        self.assertIsNone(db.team_invite(tok))

    def test_a_revoked_invite_is_refused(self):
        tok = secrets.token_urlsafe(24)
        iid = db.create_team_invite(OWNER, tok)
        self.assertTrue(db.revoke_team_invite(OWNER, iid))
        self.assertIsNone(db.team_invite(tok))

    def test_the_join_link_sends_a_guest_to_register(self):
        tok = secrets.token_urlsafe(24)
        db.create_team_invite(OWNER, tok)
        r = _client().get(f"/join/team/{tok}")
        self.assertEqual(r.status_code, 302)
        self.assertIn("/register", r.headers["Location"])
        self.assertEqual(r.headers.get("Referrer-Policy"), "no-referrer")


class PermissionTests(unittest.TestCase):
    """الموظف يدير البوتات ولا يقترب من الأسرار ولا من الفريق."""

    def setUp(self):
        self.member = _user("p" + secrets.token_hex(3))
        db.join_team(OWNER, self.member, "member")

    def test_a_member_sees_the_account_bots(self):
        r = _client(self.member).get(f"/bot/{BOT}")
        self.assertEqual(r.status_code, 200)

    def test_a_member_is_refused_the_developer_page(self):
        self.assertEqual(_client(self.member).get(f"/bot/{BOT}/developer").status_code, 403)

    def test_a_member_is_refused_the_team_page(self):
        self.assertEqual(_client(self.member).get("/team").status_code, 403)

    def test_an_admin_member_is_allowed_both(self):
        db.set_team_role(OWNER, self.member, "admin")
        c = _client(self.member)
        self.assertEqual(c.get("/team").status_code, 200)
        self.assertEqual(c.get(f"/bot/{BOT}/developer").status_code, 200)

    def test_only_the_owner_changes_roles(self):
        db.set_team_role(OWNER, self.member, "admin")
        r = _client(self.member).post(f"/team/{self.member}/remove", data={"csrf_token": "tk"})
        self.assertEqual(r.status_code, 403)

    def test_a_stranger_cannot_touch_the_bot(self):
        outsider = _user("x" + secrets.token_hex(3))
        self.assertEqual(_client(outsider).get(f"/bot/{BOT}/developer").status_code, 404)


class SecretGateTests(unittest.TestCase):
    """السرّ لا يصل مع الصفحة، ولا يُعطى إلا بكلمة المرور."""

    def test_the_page_carries_no_token(self):
        r = _client(OWNER).get(f"/bot/{BOT}/developer")
        self.assertEqual(r.status_code, 200)
        self.assertNotIn(b"EAA-secret-token", r.data)
        self.assertIn(b"10099887766", r.data)              # الـWABA ليس سرّاً
        self.assertIn(b"5550001", r.data)                  # ولا معرّف الرقم

    def test_a_wrong_password_reveals_nothing(self):
        r = _client(OWNER).post(f"/bot/{BOT}/developer/reveal",
                                json={"password": "not-it"},
                                headers={"X-CSRF-Token": "tk"})
        self.assertEqual(r.status_code, 403)
        self.assertNotIn(b"EAA-secret-token", r.data)

    def test_the_right_password_reveals_the_token(self):
        r = _client(OWNER).post(f"/bot/{BOT}/developer/reveal", json={"password": PW},
                                headers={"X-CSRF-Token": "tk"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["token"], "EAA-secret-token")

    def test_a_key_cannot_be_made_before_the_gate_opens(self):
        c = _client(OWNER)
        before = len(db.list_api_keys(OWNER))
        c.post(f"/bot/{BOT}/keys", data={"csrf_token": "tk", "name": "x"})
        self.assertEqual(len(db.list_api_keys(OWNER)), before)


class ApiKeyTests(unittest.TestCase):
    def test_the_key_itself_is_not_stored(self):
        key = "by_live_" + secrets.token_urlsafe(32)
        db.create_api_key(OWNER, key, name="server")
        with db.get_conn() as c:
            rows = c.execute("SELECT key_idx, prefix FROM api_keys").fetchall()
        self.assertFalse(any(r["key_idx"] == key for r in rows))
        self.assertTrue(db.api_key_row(key))

    def test_a_revoked_key_stops_working(self):
        key = "by_live_" + secrets.token_urlsafe(32)
        kid = db.create_api_key(OWNER, key)
        self.assertTrue(db.api_key_row(key))
        self.assertTrue(db.revoke_api_key(OWNER, kid))
        self.assertIsNone(db.api_key_row(key))

    def test_another_account_cannot_revoke_it(self):
        key = "by_live_" + secrets.token_urlsafe(32)
        kid = db.create_api_key(OWNER, key)
        self.assertFalse(db.revoke_api_key(STAFF, kid))
        self.assertTrue(db.api_key_row(key))

    def test_using_a_key_records_the_time(self):
        key = "by_live_" + secrets.token_urlsafe(32)
        kid = db.create_api_key(OWNER, key)
        db.api_key_row(key)
        row = [k for k in db.list_api_keys(OWNER) if k["id"] == kid][0]
        self.assertTrue(row["last_used_at"])


class PartnerApiTests(unittest.TestCase):
    """`/api/v1/<phone_id>/messages` — بنية Meta، ومفتاحنا بدل توكنها."""

    def setUp(self):
        self.key = "by_live_" + secrets.token_urlsafe(32)
        db.create_api_key(OWNER, self.key, name="partner")
        self.c = web.app.test_client()

    def _post(self, phone="5550001", key=None, body=None):
        return self.c.post(f"/api/v1/{phone}/messages",
                           json=body if body is not None else {"to": "2010", "type": "text",
                                                               "text": {"body": "hi"}},
                           headers={"Authorization": f"Bearer {key or self.key}"})

    def test_no_key_is_rejected(self):
        r = self.c.post("/api/v1/5550001/messages", json={})
        self.assertEqual(r.status_code, 401)

    def test_a_wrong_key_is_rejected(self):
        self.assertEqual(self._post(key="by_live_nope_nope_nope_nope").status_code, 401)

    def test_a_key_cannot_send_from_another_account_number(self):
        other = _user("z" + secrets.token_hex(3))
        _wa_bot(other, "5559999")
        self.assertEqual(self._post(phone="5559999").status_code, 403)

    def test_an_unknown_number_is_refused(self):
        self.assertEqual(self._post(phone="4040404").status_code, 403)

    def test_a_bot_scoped_key_is_refused_elsewhere(self):
        b2 = _wa_bot(OWNER, "5550002")
        k = "by_live_" + secrets.token_urlsafe(32)
        db.create_api_key(OWNER, k, bot_id=b2)
        self.assertEqual(self._post(phone="5550001", key=k).status_code, 403)
        # وعلى بوته هو يمرّ التحقق ويصل إلى القناة — نُبدلها فلا يُنادى Meta في الاختبار
        real, web.WAC.proxy_send = web.WAC.proxy_send, lambda *a: (200, {"ok": 1})
        try:
            self.assertEqual(self._post(phone="5550002", key=k).status_code, 200)
        finally:
            web.WAC.proxy_send = real

    def test_the_route_does_not_demand_a_csrf_token(self):
        """بلا استثناء CSRF لكان الرد 400 قبل النظر في المفتاح أصلاً."""
        self.assertNotEqual(self._post().status_code, 400)

    def test_a_valid_call_reaches_the_channel(self):
        calls = []

        def fake(phone_id, token, payload):
            calls.append((phone_id, token, payload))
            return 200, {"messages": [{"id": "wamid.TEST"}]}

        real = web.WAC.proxy_send
        web.WAC.proxy_send = fake
        try:
            r = self._post()
        finally:
            web.WAC.proxy_send = real
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["messages"][0]["id"], "wamid.TEST")
        self.assertEqual(calls[0][0], "5550001")
        self.assertEqual(calls[0][1], "EAA-secret-token")   # توكن Meta لم يغادر الخادم


class RelayTests(unittest.TestCase):
    """الوارد يُمرَّر لخادم الشريك — لأن ويبهوك Meta يصل إلى تطبيقنا نحن."""

    def test_only_public_https_is_accepted(self):
        for bad in ("http://x.com/h", "https://localhost/h", "https://127.0.0.1/h",
                    "https://10.0.0.5/h", "https://192.168.1.9/h", "https://box.local/h",
                    "ftp://x.com", ""):
            self.assertTrue(web._relay_url_error(bad), bad)
        self.assertEqual(web._relay_url_error("https://api.partner.com/wa"), "")

    def test_saving_a_url_mints_a_secret(self):
        c = _client(OWNER)
        c.post(f"/bot/{BOT}/developer/reveal", json={"password": PW},
               headers={"X-CSRF-Token": "tk"})
        r = c.post(f"/bot/{BOT}/relay", data={"csrf_token": "tk",
                                              "relay_url": "https://api.partner.com/wa"})
        self.assertEqual(r.status_code, 302)
        cfg = json.loads(db.get_bot(BOT)["config_json"])
        self.assertEqual(cfg["relay_url"], "https://api.partner.com/wa")
        self.assertTrue(len(cfg["relay_secret"]) > 20)

    def test_a_bad_url_changes_nothing(self):
        before = json.loads(db.get_bot(BOT)["config_json"]).get("relay_url", "")
        _client(OWNER).post(f"/bot/{BOT}/relay",
                            data={"csrf_token": "tk", "relay_url": "http://evil.internal/x"})
        self.assertEqual(json.loads(db.get_bot(BOT)["config_json"]).get("relay_url", ""), before)

    def test_targets_are_found_by_phone_number_id(self):
        bid = _wa_bot(OWNER, "5550777")
        db.update_bot_config(bid, dict(json.loads(db.get_bot(bid)["config_json"]),
                                       relay_url="https://api.partner.com/wa",
                                       relay_secret="s3cr3t-relay-key"))
        payload = {"entry": [{"changes": [{"value": {
            "metadata": {"phone_number_id": "5550777"},
            "messages": [{"from": "2010", "text": {"body": "hi"}}]}}]}]}
        t = web._relay_targets(payload)
        self.assertEqual(t["5550777"][0], "https://api.partner.com/wa")
        self.assertEqual(t["5550777"][1], "s3cr3t-relay-key")

    def test_a_number_without_a_webhook_is_not_a_target(self):
        payload = {"entry": [{"changes": [{"value": {
            "metadata": {"phone_number_id": "5550001"}}}]}]}
        self.assertNotIn("5550001", web._relay_targets(payload))

    def test_a_malformed_payload_is_survived(self):
        for bad in ({}, {"entry": None}, {"entry": [{}]}, {"entry": [{"changes": [{}]}]}):
            self.assertEqual(web._relay_targets(bad), {})


if __name__ == "__main__":
    unittest.main(verbosity=2)
