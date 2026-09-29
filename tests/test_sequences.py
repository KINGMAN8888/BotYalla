"""التسلسلات — المرحلة 6: التحقق من المواصفة · ساعات الإرسال · التسجيل (يدوي · وسم · بطاقة فلو) ·
الإرسال في موعده والحجز الذرّي · نافذة 24 ساعة · التوقّف بالرد وSTOP والتولّي · مال القالب · الصلاحيات.

    python tests/test_sequences.py
"""
import asyncio, json, os, secrets, sys, tempfile, time, unittest
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_TMPDIR = tempfile.mkdtemp(prefix="botyalla-seq-")
os.environ["BOTYALLA_DB"] = os.path.join(_TMPDIR, "test.db")   # قبل استيراد database
os.environ["BOTYALLA_UPLOADS"] = _TMPDIR
os.environ["BOTYALLA_LOGS"] = os.path.join(_TMPDIR, "logs")
os.environ["ADMIN_USER"] = "admin"
os.environ["ADMIN_PASS"] = "Sq#" + secrets.token_hex(6)

import auth                                # noqa: E402
import database as db                      # noqa: E402
import flow_engine as FE                   # noqa: E402
import sequences as SQ                     # noqa: E402
import app as web                          # noqa: E402

PW = "Str0ng!Pass" + secrets.token_hex(3)
db.init_db(); web.seed_platform_defaults(); web.contact_defaults(); web.seed_default_admin()
web.app.config["TESTING"] = True


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


class Ch:
    phone_id = "1"
    page_id = None

    def __init__(self, accept_tpl=True):
        self.out, self.accept = [], accept_tpl

    async def send_text(self, peer, text):
        self.out.append(("text", text)); return {"messages": [{"id": "w"}]}

    async def remove_keyboard(self, peer, text):
        return await self.send_text(peer, text)

    async def send_template(self, peer, name, lang="ar", components=None):
        self.out.append(("template", name)); return {"messages": [{"id": "t"}]} if self.accept else None


class Acct:
    def __init__(self):
        self.owner = user("own")
        self.member = user("mem", None)
        db.join_team(self.owner, self.member, "member")
        self.bot = db.create_bot(self.owner, "WA", f"wa:{secrets.randbelow(10**12)}", "flow", {}, "whatsapp")
        self.c, self.mc = client(self.owner), client(self.member)

    def customer(self, name="منى"):
        p = f"wa:9665{secrets.randbelow(10**8):08d}"
        db.add_bot_user(self.bot, int(p[3:]), name, peer=p)
        db.log_message(self.bot, p, "in", "customer", "مرحبا", name=name)
        db.touch_bot_user(self.bot, p)
        return p

    def seq(self, steps, **spec):
        r = post(self.c, "/api/sequences/save", {"name": "متابعة", "bot": self.bot, "active": True,
                                                  "spec": dict({"steps": steps}, **spec)}).get_json()
        assert r["ok"], r
        return r["item"]

    def enroll(self, seq_id, p, who=None):
        return post(who or self.c, "/api/sequences/enroll", {"bot": self.bot, "peer": p, "sequence": seq_id}).get_json()


def run_due(now, ch):
    for e, s, b in SQ.due(now):
        asyncio.run(SQ.run_step(b, ch, e, s, now))


class SpecTests(unittest.TestCase):
    def test_validation(self):
        with self.assertRaises(SQ.Invalid):
            SQ.clean_spec({"steps": []})
        with self.assertRaises(SQ.Invalid):
            SQ.clean_spec({"steps": [{"kind": "text", "text": ""}]})
        with self.assertRaises(SQ.Invalid):
            SQ.clean_spec({"steps": [{"kind": "template", "template": {"name": "Bad Name!"}}]})
        with self.assertRaises(SQ.Invalid):
            SQ.clean_spec({"steps": [{"text": "x"}], "trigger": {"type": "tag", "tag": "ghost"}}, {"vip"})
        s = SQ.clean_spec({"steps": [{"text": "x", "delay": 10**9}], "hours": {"start": 9, "end": 21, "tz": 3}})
        self.assertEqual((s["steps"][0]["delay"], s["stop_on_reply"], s["trigger"]["type"]), (SQ.MAX_DELAY, True, "manual"))

    def test_send_hours(self):
        h = {"start": 9, "end": 21, "tz": 3, "days": list(range(7))}
        riyadh = timezone(timedelta(hours=3))
        late = datetime(2026, 10, 1, 23, 30, tzinfo=riyadh).timestamp()
        self.assertEqual(datetime.fromtimestamp(SQ.fit(late, h), riyadh).strftime("%d %H:%M"), "02 09:00")
        early = datetime(2026, 10, 1, 6, 0, tzinfo=riyadh).timestamp()
        self.assertEqual(datetime.fromtimestamp(SQ.fit(early, h), riyadh).strftime("%d %H:%M"), "01 09:00")
        ok = datetime(2026, 10, 1, 12, 0, tzinfo=riyadh).timestamp()
        self.assertEqual(SQ.fit(ok, h), int(ok))


class RunTests(unittest.TestCase):
    def test_steps_arrive_on_time_once_and_finish(self):
        a = Acct()
        s = a.seq([{"delay": 0, "text": "أهلاً {{contact.name}} 👋"}, {"delay": 60, "text": "هل تحتاج مساعدة في الحجز؟"}])
        p = a.customer()
        self.assertTrue(a.enroll(s["id"], p)["ok"])
        self.assertEqual(a.enroll(s["id"], p)["error"], "already", "لا تسجيل مكرر")
        now = int(time.time())
        ch = Ch()
        run_due(now, ch)
        self.assertEqual(ch.out, [("text", "أهلاً منى 👋")])
        run_due(now, ch)
        self.assertEqual(len(ch.out), 1, "الخطوة الثانية بعد ساعة لا الآن")
        run_due(now + 3601, ch)
        self.assertEqual(ch.out[-1], ("text", "هل تحتاج مساعدة في الحجز؟"))
        st = db.sequence_stats(s["id"])
        self.assertEqual((st["done"], st["steps"][0]["sent"], st["steps"][1]["sent"]), (1, 1, 1))

    def test_claim_is_atomic(self):
        a = Acct()
        s = a.seq([{"delay": 0, "text": "x"}])
        a.enroll(s["id"], a.customer())
        now = int(time.time())
        mine = lambda rows: [e for e, sq, b in rows if sq["id"] == s["id"]]
        self.assertEqual((len(mine(SQ.due(now))), mine(SQ.due(now))), (1, []), "دورتان متزامنتان لا تأخذان الخطوة نفسها")

    def test_window_closed_skips_or_stops(self):
        a = Acct()
        skip = a.seq([{"delay": 0, "text": "نص حر"}, {"delay": 0, "kind": "template", "template": {"name": "reminder", "lang": "ar"}}])
        stop = a.seq([{"delay": 0, "text": "نص حر", "closed": "stop"}, {"delay": 0, "text": "لن تصل"}])
        p = a.customer()
        a.enroll(skip["id"], p); a.enroll(stop["id"], p)
        import broadcasts as BC
        orig = dict(BC._HOOKS)
        BC.configure(category=lambda b, n, l: "UTILITY")
        try:
            ch = Ch()
            later = int(time.time()) + 25 * 3600                      # خارج نافذة الـ24 ساعة
            run_due(later, ch); run_due(later, ch)
        finally:
            BC._HOOKS.clear(); BC._HOOKS.update(orig)
        self.assertEqual(ch.out, [("template", "reminder")], "النص الحر لا يُرسل خارج النافذة — القالب يُرسل")
        self.assertEqual(db.sequence_stats(stop["id"])["reasons"], {"window": 1})

    def test_reply_stop_and_takeover_stop_the_sequence(self):
        a = Acct()
        s = a.seq([{"delay": 60, "text": "متابعة"}])
        keep = a.seq([{"delay": 60, "text": "تذكير"}], stop_on_reply=False)
        p1, p2, p3 = a.customer(), a.customer(), a.customer()
        for p in (p1, p2, p3):
            a.enroll(s["id"], p)
        a.enroll(keep["id"], p1)
        asyncio.run(FE.handle_message(db.get_bot(a.bot), Ch(), {"peer": p1, "kind": "text", "text": "تمام", "name": "منى"}))
        db.set_opt_out(a.bot, p2, True)
        db.set_conversation_mode(a.bot, p3, "human")
        ch = Ch()
        run_due(int(time.time()) + 3700, ch)
        self.assertEqual(ch.out, [("text", "تذكير")], "لا يصل إلا تسلسل stop_on_reply=False")
        self.assertEqual(db.sequence_stats(s["id"])["reasons"], {"replied": 1, "opted_out": 1, "human": 1})
        self.assertEqual(a.enroll(s["id"], p2)["error"], "opted_out")

    def test_template_step_uses_broadcast_money_rules(self):
        import broadcasts as BC
        a = Acct()
        db.wallet_topup(a.owner, 1000)
        s = a.seq([{"delay": 0, "kind": "template", "template": {"name": "offer", "lang": "ar", "vars": ["{{contact.name}}"]}}])
        orig = dict(BC._HOOKS)
        BC.configure(category=lambda b, n, l: "MARKETING")
        try:
            a.enroll(s["id"], a.customer())
            run_due(int(time.time()), Ch(accept_tpl=True))
            self.assertEqual(db.wallet_balance(a.owner), 1000 - web.mkt_price())
            a.enroll(s["id"], a.customer())
            run_due(int(time.time()), Ch(accept_tpl=False))
            self.assertEqual(db.wallet_balance(a.owner), 1000 - web.mkt_price(), "رفض Meta = ردّ")
            self.assertEqual(db.sequence_stats(s["id"])["steps"][0], {"sent": 1, "failed": 1})
        finally:
            BC._HOOKS.clear(); BC._HOOKS.update(orig)
        tg = db.create_bot(a.owner, "TG", "tg-x", "flow", {}, "telegram")
        r = post(a.c, "/api/sequences/save", {"name": "x", "bot": tg, "spec": {"steps": [{"kind": "template", "template": {"name": "a"}}]}}).get_json()
        self.assertEqual(r["error"], "template_channel")


class TriggerTests(unittest.TestCase):
    def test_tag_trigger_from_contacts_and_flow_card(self):
        a = Acct()
        vip, _ = db.save_tag(a.owner, "VIP", "teal")
        s = a.seq([{"delay": 0, "text": "مرحباً بعملائنا المميزين"}], trigger={"type": "tag", "tag": "vip"})
        p = a.customer()
        cid = db.contact_id_for_peer(a.bot, p)
        self.assertTrue(post(a.c, "/api/crm/contacts/bulk", {"ids": [cid], "action": "tag", "tags": [vip]}).get_json()["ok"])
        self.assertEqual(db.sequence_stats(s["id"])["active"], 1, "الوسم من جهات الاتصال يسجّل")
        # بطاقة «تسجيل في تسلسل» في الفلو + بطاقة وسم تشغّل التسلسل
        s2 = a.seq([{"delay": 0, "text": "خطوة"}])
        fid = post(a.c, f"/api/bot/{a.bot}/flows", {"name": "f"}).get_json()["flow"]["id"]
        post(a.c, f"/api/bot/{a.bot}/flows/{fid}/save", {"draft": {"start": "q", "nodes": {"q": {"type": "sequence", "sequence": 999999}}}})
        self.assertEqual(post(a.c, f"/api/bot/{a.bot}/flows/{fid}/publish").get_json()["error"], "node:q:sequence")
        post(a.c, f"/api/bot/{a.bot}/flows/{fid}/save", {"draft": {"start": "q", "nodes": {
            "q": {"type": "sequence", "sequence": s2["id"], "next": "t"}, "t": {"type": "tag", "tags": ["VIP"]}}}})
        self.assertTrue(post(a.c, f"/api/bot/{a.bot}/flows/{fid}/publish").get_json()["ok"])
        post(a.c, f"/api/bot/{a.bot}/flows/{fid}/toggle", {"active": True})
        p2 = a.customer()
        asyncio.run(FE.handle_message(db.get_bot(a.bot), Ch(), {"peer": p2, "kind": "text", "text": "hi", "name": "x"}))
        self.assertEqual((db.sequence_stats(s2["id"])["active"], db.sequence_stats(s["id"])["active"]), (1, 2))


class PermissionTests(unittest.TestCase):
    def test_roles_and_accounts(self):
        a, b = Acct(), Acct()
        s = a.seq([{"delay": 0, "text": "x"}])
        self.assertEqual(post(a.mc, "/api/sequences/save", {"name": "y", "bot": a.bot, "spec": {"steps": [{"text": "x"}]}}).status_code, 403)
        self.assertTrue(a.enroll(s["id"], a.customer(), who=a.mc)["ok"], "الموظف يسجّل من الصندوق")
        p = b.customer()
        self.assertEqual(post(b.c, "/api/sequences/enroll", {"bot": b.bot, "peer": p, "sequence": s["id"]}).status_code, 404)
        self.assertEqual(post(b.c, "/api/sequences/delete", {"id": s["id"]}).status_code, 404)
        self.assertEqual(client(user("basic", "merchant")).get("/api/sequences").status_code, 403)


if __name__ == "__main__":
    unittest.main(verbosity=2)
