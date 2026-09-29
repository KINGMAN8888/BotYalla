"""الصندوق المشترك — المرحلة 6: الحالة (مفتوحة/معلّقة/مغلقة وإعادة الفتح) · الإسناد والفِرق والتناوب ·
التحويل من الفلو ومن إعداد القناة · الملاحظات الداخلية والإشارات (لا تصل للعميل ولا للذكاء) ·
الردود الجاهزة · رؤية «ما يخصّني» في الصندوقين · الصلاحيات والباقة.

    python tests/test_shared_inbox.py
"""
import asyncio, json, os, secrets, sys, tempfile, unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_TMPDIR = tempfile.mkdtemp(prefix="botyalla-hub-")
os.environ["BOTYALLA_DB"] = os.path.join(_TMPDIR, "test.db")   # قبل استيراد database
os.environ["BOTYALLA_UPLOADS"] = _TMPDIR
os.environ["BOTYALLA_LOGS"] = os.path.join(_TMPDIR, "logs")
os.environ["ADMIN_USER"] = "admin"
os.environ["ADMIN_PASS"] = "Hb#" + secrets.token_hex(6)

import auth                                # noqa: E402
import database as db                      # noqa: E402
import flow_engine as FE                   # noqa: E402
import app as web                          # noqa: E402

PW = "Str0ng!Pass" + secrets.token_hex(3)
db.init_db(); web.seed_platform_defaults(); web.contact_defaults(); web.seed_default_admin()
web.app.config["TESTING"] = True
SENT = []
web.manager.send_to_peer = lambda bot_id, peer, text=None, asset=None: SENT.append((bot_id, peer, text)) or (True, "")


async def _quiet(*a, **k):
    return False
FE.notify_owner = lambda *a, **k: _quiet()


def user(name, plan="enterprise"):
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


def peer():
    return f"wa:9665{secrets.randbelow(10**8):08d}"


class Account:
    """حساب بمالك ومديرة وموظفَين وبوت واتساب."""
    def __init__(self):
        self.owner = user("own")
        self.admin, self.m1, self.m2 = user("adm", None), user("ag1", None), user("ag2", None)
        db.join_team(self.owner, self.admin, "admin")
        db.join_team(self.owner, self.m1, "member"); db.join_team(self.owner, self.m2, "member")
        self.bot = db.create_bot(self.owner, "Alforsan", f"wa:{secrets.randbelow(10**12)}", "flow", {}, "whatsapp")
        self.c = {k: client(getattr(self, k)) for k in ("owner", "admin", "m1", "m2")}

    def customer(self, text="السلام عليكم"):
        p = peer()
        db.add_bot_user(self.bot, int(p[3:]), "Ali", peer=p)
        db.log_message(self.bot, p, "in", "customer", text, name="Ali")
        return p

    def rows(self, who, view="open"):
        return self.c[who].get(f"/api/inbox?view={view}").get_json()


class StatusTests(unittest.TestCase):
    def test_resolve_then_customer_writes_again_reopens(self):
        a = Account()
        p = a.customer()
        db.set_conversation_mode(a.bot, p, "human")
        r = post(a.c["owner"], "/api/inbox/status", {"bot": a.bot, "peer": p, "status": "resolved"}).get_json()
        self.assertEqual((r["conv"]["status"], r["conv"]["mode"], r["conv"]["unread"]), ("resolved", "bot", 0))
        self.assertNotIn(p, [x["peer"] for x in a.rows("owner")["rows"]], "المغلقة خارج «المفتوحة»")
        self.assertIn(p, [x["peer"] for x in a.rows("owner", "resolved")["rows"]])
        db.log_message(a.bot, p, "in", "customer", "عندي سؤال آخر")
        self.assertEqual(db.get_conversation(a.bot, p)["status"], "open", "رسالة جديدة تعيد الفتح")
        self.assertEqual(post(a.c["owner"], "/api/inbox/status", {"bot": a.bot, "peer": p, "status": "x"}).status_code, 400)

    def test_views_and_counts(self):
        a = Account()
        bot_p, wait_p, mine_p = a.customer(), a.customer(), a.customer()
        db.set_conversation_mode(a.bot, wait_p, "human")
        post(a.c["m1"], "/api/inbox/assign", {"bot": a.bot, "peer": mine_p, "user": a.m1})
        d = a.rows("m1", "mine")
        self.assertEqual([x["peer"] for x in d["rows"]], [mine_p])
        self.assertEqual([x["peer"] for x in a.rows("m1", "unassigned")["rows"]], [wait_p], "تنتظر إنساناً")
        self.assertEqual([x["peer"] for x in a.rows("m1", "bot")["rows"]], [bot_p], "البوت يتولّاها")
        self.assertEqual((d["counts"]["mine"], d["counts"]["unassigned"], d["counts"]["open"]), (1, 1, 3))
        self.assertEqual(a.rows("owner")["rows"][0]["bot_name"], "Alforsan")


class AssignTests(unittest.TestCase):
    def test_assign_validates_and_takes_over(self):
        a = Account()
        p = a.customer()
        stranger = user("str")
        self.assertEqual(post(a.c["owner"], "/api/inbox/assign", {"bot": a.bot, "peer": p, "user": stranger}).get_json()["error"], "user")
        other = Account()
        tid, _ = db.save_inbox_team(other.owner, None, "خارجي", "round_robin", [other.m1])
        self.assertEqual(post(a.c["owner"], "/api/inbox/assign", {"bot": a.bot, "peer": p, "team": tid}).get_json()["error"], "team")
        conv = post(a.c["owner"], "/api/inbox/assign", {"bot": a.bot, "peer": p, "user": a.m2}).get_json()["conv"]
        self.assertEqual((conv["assignee_id"], conv["mode"]), (a.m2, "human"), "الإسناد لموظف = تولٍّ")
        self.assertEqual(post(client(stranger), "/api/inbox/assign", {"bot": a.bot, "peer": p, "user": stranger}).status_code, 404)

    def test_round_robin_team_and_manual_team(self):
        a = Account()
        rr, _ = db.save_inbox_team(a.owner, None, "الحجوزات", "round_robin", [a.m1, a.m2, a.admin])
        got = []
        for _ in range(4):
            p = a.customer()
            got.append(post(a.c["owner"], "/api/inbox/assign", {"bot": a.bot, "peer": p, "team": rr, "route": True}).get_json()["conv"]["assignee_id"])
        order = sorted([a.m1, a.m2, a.admin])
        self.assertEqual(got, order + order[:1], "بالتناوب وبلا تكرار")
        man, _ = db.save_inbox_team(a.owner, None, "الشركات", "manual", [a.m1])
        conv = post(a.c["owner"], "/api/inbox/assign", {"bot": a.bot, "peer": a.customer(), "team": man, "route": True}).get_json()["conv"]
        self.assertEqual((conv["team_id"], conv["assignee_id"]), (man, None), "الفريق اليدوي: على الفريق بلا مسؤول")
        self.assertEqual(db.save_inbox_team(a.owner, None, "الحجوزات", "manual", [])[1], "duplicate")
        tid, _ = db.save_inbox_team(a.owner, None, "غرباء", "manual", [user("x", None)])
        self.assertEqual(db.get_inbox_team(a.owner, tid)["members"], [], "لا يُضاف لفريق من ليس في الحساب")

    def test_reply_assigns_to_the_replier_without_stealing(self):
        a = Account()
        p = a.customer()
        r = post(a.c["m1"], "/api/inbox/send", {"bot": a.bot, "peer": p, "text": "أهلاً، معك سارة"}).get_json()
        self.assertTrue(r["ok"], r)
        self.assertEqual((r["conv"]["assignee_id"], r["conv"]["mode"]), (a.m1, "human"))
        post(a.c["m2"], "/api/inbox/send", {"bot": a.bot, "peer": p, "text": "وأنا كذلك"})
        self.assertEqual(db.get_conversation(a.bot, p)["assignee_id"], a.m1, "الرد لا ينتزع إسناداً قائماً")
        msgs = db.list_messages(a.bot, p)
        self.assertEqual([m["user_id"] for m in msgs if m["sender"] == "human"], [a.m1, a.m2], "يُعرف من ردّ")

    def test_escalation_routes_to_channel_team_and_flow_team(self):
        a = Account()
        rr, _ = db.save_inbox_team(a.owner, None, "العمرة", "round_robin", [a.m2])
        post(a.c["owner"], "/api/inbox/settings", {"routes": {str(a.bot): rr}})
        self.assertEqual(json.loads(db.get_bot(a.bot)["config_json"])["route_team"], rr)
        p = a.customer()

        class Ch:
            phone_id = page_id = None
            async def remove_keyboard(self, peer, text): return True
            async def send_text(self, peer, text): return True
        asyncio.run(FE._escalate(db.get_bot(a.bot), Ch(), p, "طلب موظف", say=False))
        conv = db.get_conversation(a.bot, p)
        self.assertEqual((conv["team_id"], conv["assignee_id"], conv["mode"], conv["status"]), (rr, a.m2, "human", "open"))
        other, _ = db.save_inbox_team(a.owner, None, "الشركات", "round_robin", [a.m1])
        p2 = a.customer()
        asyncio.run(FE._escalate(db.get_bot(a.bot), Ch(), p2, "x", say=False, team_id=other))
        self.assertEqual(db.get_conversation(a.bot, p2)["assignee_id"], a.m1, "فريق بطاقة الفلو يتقدّم على فريق القناة")
        post(a.c["owner"], "/api/inbox/teams/delete", {"id": rr})
        self.assertNotIn("route_team", json.loads(db.get_bot(a.bot)["config_json"]), "لا مرجع لفريق محذوف")
        self.assertEqual(json.loads(db.get_bot(a.bot)["config_json"]).get("route_team"), None)


class FlowRoutingTests(unittest.TestCase):
    def test_handoff_and_assign_cards_route_to_teams(self):
        a = Account()
        book, _ = db.save_inbox_team(a.owner, None, "الحجوزات", "round_robin", [a.m1])
        corp, _ = db.save_inbox_team(a.owner, None, "الشركات", "round_robin", [a.m2])
        other = Account()
        foreign, _ = db.save_inbox_team(other.owner, None, "خارجي", "round_robin", [other.m1])
        c = a.c["owner"]
        fid = post(c, f"/api/bot/{a.bot}/flows", {"name": "توجيه"}).get_json()["flow"]["id"]

        def publish(nodes):
            post(c, f"/api/bot/{a.bot}/flows/{fid}/save", {"draft": {"start": "a", "nodes": nodes}})
            return post(c, f"/api/bot/{a.bot}/flows/{fid}/publish").get_json()
        self.assertEqual(publish({"a": {"type": "handoff", "team": foreign}})["error"], "node:a:team", "فريق حساب آخر")
        self.assertEqual(publish({"a": {"type": "assign", "mode": "team"}})["error"], "node:a:team")
        self.assertTrue(publish({"a": {"type": "assign", "mode": "team", "team": corp, "next": "b"},
                                 "b": {"type": "handoff", "text": "نحوّلك", "team": book}})["ok"])
        post(c, f"/api/bot/{a.bot}/flows/{fid}/toggle", {"active": True})

        class Ch:
            phone_id = page_id = None
            async def remove_keyboard(self, peer, text): return True
            async def send_text(self, peer, text): return True
        p = peer()
        asyncio.run(FE.handle_message(db.get_bot(a.bot), Ch(), {"peer": p, "kind": "text", "text": "hi", "name": "Ali"}))
        conv = db.get_conversation(a.bot, p)
        self.assertEqual((conv["team_id"], conv["assignee_id"], conv["mode"]), (corp, a.m2, "human"),
                         "الإسناد لفريق ثم التحويل: المسؤول القائم لا يُنتزع")


class ChannelSettingsTests(unittest.TestCase):
    def test_away_message_outside_hours_and_auto_resolve(self):
        import time as _t
        a = Account()
        r = post(a.c["owner"], "/api/inbox/settings", {"channels": {str(a.bot): {"hours": {"start": 9, "end": 10, "tz": 3, "days": []}}}}).get_json()
        self.assertEqual(r["error"], "hours", "بلا أيام")
        r = post(a.c["owner"], "/api/inbox/settings", {"channels": {str(a.bot): {"hours": {"start": 9, "end": 17, "tz": 3, "days": [0]}}}}).get_json()
        self.assertEqual(r["error"], "away_text")
        # ساعات مستحيلة الآن (يوم واحد، ساعة واحدة في منطقة بعيدة) ⇒ خارج الدوام دائماً تقريباً
        import flow_graph as FG
        hours = {"start": 3, "end": 4, "tz": -11, "days": [0]}
        if FG.is_open(hours):
            hours["days"] = [1]
        self.assertTrue(post(a.c["owner"], "/api/inbox/settings", {"channels": {str(a.bot): {
            "hours": hours, "away_text": "فريقنا خارج الدوام الآن، نرد عليك صباحاً 🌙", "auto_resolve": 2}}}).get_json()["ok"])
        sent = []

        class Ch:
            phone_id = page_id = None
            async def remove_keyboard(self, peer, text): sent.append(text); return True
            async def send_text(self, peer, text): sent.append(text); return True
        p = a.customer()
        asyncio.run(FE._escalate(db.get_bot(a.bot), Ch(), p, "طلب موظف", say=False))
        self.assertEqual(sent, ["فريقنا خارج الدوام الآن، نرد عليك صباحاً 🌙"])
        idle, fresh, pend = a.customer(), a.customer(), a.customer()
        with db.get_conn() as c:
            c.execute("UPDATE conversations SET last_at=? WHERE bot_id=? AND peer IN (?,?)", (int(_t.time()) - 3 * 3600, a.bot, idle, pend))
        db.set_conversation_status(a.bot, pend, "pending")
        db.auto_resolve_idle()
        st = {x: db.get_conversation(a.bot, x)["status"] for x in (idle, fresh, pend)}
        self.assertEqual(st, {idle: "resolved", fresh: "open", pend: "pending"}, "المعلّقة لا تُغلق آلياً")
        cfg = json.loads(db.get_bot(a.bot)["config_json"])
        self.assertEqual(cfg["inbox"]["auto_resolve"], 2)


class NoteTests(unittest.TestCase):
    def test_notes_are_internal_and_mentions_notify(self):
        a = Account()
        p = a.customer("كم سعر الجناح؟")
        m2name = db.get_user(a.m2)["username"]
        r = post(a.c["m1"], "/api/inbox/note", {"bot": a.bot, "peer": p, "text": f"عميل VIP — @{m2name} تابع السعر"}).get_json()
        self.assertEqual(r["mentioned"], 1)
        SENT.clear()
        conv = db.get_conversation(a.bot, p)
        self.assertEqual((conv["last_text"], conv["unread"]), ("كم سعر الجناح؟", 1), "الملاحظة لا تغيّر ملخّص المحادثة")
        self.assertEqual([m["text"] for m in db.recent_history(a.bot, p)], ["كم سعر الجناح؟"], "لا تدخل ذاكرة الذكاء")
        self.assertEqual(SENT, [], "لا تُرسل للعميل")
        self.assertEqual([x["peer"] for x in a.rows("m2", "mentions")["rows"]], [p])
        a.c["m2"].get(f"/api/inbox/thread?bot={a.bot}&peer={p}")
        self.assertEqual(a.rows("m2", "mentions")["rows"], [], "فتحها يعلّمها مقروءة")
        thread = a.c["m1"].get(f"/api/inbox/thread?bot={a.bot}&peer={p}").get_json()
        self.assertEqual(thread["messages"][-1]["direction"], "note")


class CannedTests(unittest.TestCase):
    def test_crud_and_roles(self):
        a = Account()
        r = post(a.c["admin"], "/api/canned/save", {"shortcut": "/Umrah", "title": "باقات", "body": "أهلاً {{contact.name}}، باقاتنا…"}).get_json()
        self.assertTrue(r["ok"])
        self.assertEqual(r["items"][0]["shortcut"], "umrah")
        self.assertEqual(post(a.c["admin"], "/api/canned/save", {"shortcut": "umrah", "body": "x"}).get_json()["error"], "duplicate")
        self.assertEqual(post(a.c["admin"], "/api/canned/save", {"shortcut": "a", "body": ""}).get_json()["error"], "body")
        self.assertEqual(post(a.c["m1"], "/api/canned/save", {"shortcut": "b", "body": "x"}).status_code, 403, "الموظف يستعملها لا يديرها")
        self.assertEqual(len(a.c["m1"].get("/api/canned").get_json()["items"]), 1)
        other = Account()
        self.assertEqual(post(other.c["owner"], "/api/canned/delete", {"id": r["id"]}).status_code, 404)


class ScopeTests(unittest.TestCase):
    def test_own_scope_hides_colleagues_conversations_everywhere(self):
        a = Account()
        tid, _ = db.save_inbox_team(a.owner, None, "الحجوزات", "manual", [a.m1])
        theirs, free, team_p = a.customer(), a.customer(), a.customer()
        post(a.c["owner"], "/api/inbox/assign", {"bot": a.bot, "peer": theirs, "user": a.m2})
        post(a.c["owner"], "/api/inbox/assign", {"bot": a.bot, "peer": team_p, "team": tid})
        self.assertIn(theirs, [x["peer"] for x in a.rows("m1")["rows"]], "الافتراضي: الكل يرى الكل")
        self.assertEqual(post(a.c["m1"], "/api/inbox/settings", {"scope": "own"}).status_code, 403, "الإعداد للإدارة")
        post(a.c["owner"], "/api/inbox/settings", {"scope": "own"})
        seen = {x["peer"] for x in a.rows("m1")["rows"]}
        self.assertEqual(seen, {free, team_p}, "غير المسندة + فريقه")
        self.assertEqual(a.c["m1"].get(f"/api/inbox/thread?bot={a.bot}&peer={theirs}").status_code, 404)
        self.assertEqual(a.c["m1"].get(f"/api/bot/{a.bot}/inbox/thread?peer={theirs}").status_code, 404, "وصندوق البوت القديم أيضاً")
        self.assertEqual(post(a.c["m1"], f"/bot/{a.bot}/inbox/send", {"peer": theirs, "text": "x"}).status_code, 404)
        self.assertNotIn(theirs, [c["peer"] for c in a.c["m1"].get(f"/api/bot/{a.bot}/inbox").get_json()["conversations"]])
        self.assertIn(theirs, {x["peer"] for x in a.rows("admin")["rows"]}, "المدير يرى الكل")
        self.assertEqual(a.rows("m1", f"team:{tid}")["rows"][0]["peer"], team_p)


class GateTests(unittest.TestCase):
    def test_plan_and_other_accounts(self):
        basic = user("basic", "merchant")
        self.assertEqual(client(basic).get("/api/inbox").status_code, 403)
        a, b = Account(), Account()
        p = a.customer()
        self.assertEqual(b.c["owner"].get(f"/api/inbox/thread?bot={a.bot}&peer={p}").status_code, 404)
        self.assertNotIn(p, [x["peer"] for x in b.rows("owner")["rows"]])
        self.assertEqual(a.c["owner"].get("/inbox").status_code, 200)


if __name__ == "__main__":
    unittest.main(verbosity=2)
