"""البث 2.0 — المرحلة 3: الجمهور (شرائح · STOP · سياسة الموافقة) · المال (فئة من Meta، خصم
ذرّي قبل الإرسال، ردّ ما لم يُقبل، الجدولة تُخصم عند وقتها) · متغيّرات لكل مستلم · إعادة
المحاولة الذكية · الإحصاءات وإعادة الاستهداف · الصلاحيات والتحقق.

Meta مُحاكاة: كل رقم ينتهي بـ9 يُرفض فوراً (131026)، والباقي يُقبل بـ wamid.<الرقم>.

    python tests/test_broadcasts.py
"""
import asyncio, json, os, secrets, sys, tempfile, threading, time, unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_TMPDIR = tempfile.mkdtemp(prefix="botyalla-bc-")
os.environ["BOTYALLA_DB"] = os.path.join(_TMPDIR, "test.db")   # قبل استيراد database
os.environ["BOTYALLA_UPLOADS"] = _TMPDIR
os.environ["BOTYALLA_LOGS"] = os.path.join(_TMPDIR, "logs")
os.environ["ADMIN_USER"] = "admin"
os.environ["ADMIN_PASS"] = "Bc#" + secrets.token_hex(6)

import auth                                # noqa: E402
import bot_manager                         # noqa: E402
import broadcasts as BC                    # noqa: E402
import database as db                      # noqa: E402
import msg_status as MS                    # noqa: E402
import app as web                          # noqa: E402
from channels import whatsapp as W        # noqa: E402

PW = "Str0ng!Pass" + secrets.token_hex(3)
TEMPLATES = [
    {"name": "promo", "language": "ar", "status": "APPROVED", "category": "MARKETING", "vars": [1, 2],
     "header_format": "", "header_vars": [], "body": "أهلاً {{1}}، عرض {{2}}"},
    {"name": "notice", "language": "ar", "status": "APPROVED", "category": "UTILITY", "vars": [1],
     "header_format": "", "header_vars": [], "body": "تنبيه {{1}}"},
    {"name": "img", "language": "ar", "status": "APPROVED", "category": "MARKETING", "vars": [],
     "header_format": "IMAGE", "header_vars": [], "body": "صورة"},
    {"name": "draft_tpl", "language": "ar", "status": "PENDING", "category": "MARKETING", "vars": [],
     "header_format": "", "header_vars": [], "body": "x"},
]
META = {"ok": True}
SENT = []
_IDS = __import__('itertools').count(1)


def fake_list(waba, token, *a, **k):
    return {"ok": True, "items": TEMPLATES} if META["ok"] else {"ok": False, "error": "down"}


class FakeResp:
    def __init__(self, code, body):
        self.status_code, self._b, self.text = code, body, json.dumps(body)

    def json(self):
        return self._b


async def fake_raw(self, payload):
    SENT.append(payload)
    to = str(payload.get("to"))
    if to.endswith("9"):
        return FakeResp(400, {"error": {"code": 131026, "message": "undeliverable"}})
    return FakeResp(200, {"messages": [{"id": f"wamid.{to}.{next(_IDS)}"}]})       # فريد كمعرّفات Meta


def _boot():
    db.init_db()
    web.seed_platform_defaults()
    web.contact_defaults()
    web.seed_default_admin()
    web.app.config["TESTING"] = True
    web.WT.list_templates = fake_list
    W.WhatsAppChannel._raw = fake_raw
    m = bot_manager.BotManager()
    m._thread = threading.Thread(target=m._run, daemon=True)
    m._thread.start()
    m._ready.wait(5)
    BC.configure(manager=m)
    return m


def _user(name, plan="enterprise"):
    uid, err = db.create_account(name, auth.hash_password(PW), f"{name}@example.test",
                                 None, 30, "person", verify_required=False)
    assert not err, err
    db.mark_email_verified(uid)
    if plan:
        db.activate_subscription(uid, plan, 30)
    return uid


def _client(user_id):
    c = web.app.test_client()
    with c.session_transaction() as s:
        u = db.get_user(user_id)
        s.update(_csrf="tk", uid=user_id, uname=u["username"], role=u["role"], pwv=web._pw_stamp(u["pw_hash"]))
    return c


def post(c, url, body=None):
    return c.post(url, data=json.dumps(body or {}), content_type="application/json", headers={"X-CSRF-Token": "tk"})


def wa_bot(owner):
    bid = db.create_bot(owner, "WA", f"wa:{secrets.randbelow(10**12)}", "store", {}, "whatsapp")
    db.update_bot_config(bid, {"wa_token": "tok", "wa_waba_id": "1009"})
    return bid


M = _boot()
PRICE = web.mkt_price()


def wait():
    M.join_campaigns(20)


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.owner = _user("bc" + secrets.token_hex(3))
        cls.bot = wa_bot(cls.owner)
        cls.vip, _ = db.save_tag(cls.owner, "VIP")
        o = cls.owner
        # 4 موافقون (أحدهم رقمه ينتهي بـ9 فيُرفض) · 1 بلا موافقة معروفة · 1 رافض · 1 طلب STOP من البوت
        cls.c1, _ = db.save_contact(o, {"name": "Ali", "phone": "+966500000011", "optin": 1, "tags": [cls.vip]})
        cls.c2, _ = db.save_contact(o, {"name": "", "phone": "+966500000012", "optin": 1, "tags": [cls.vip]})
        cls.c3, _ = db.save_contact(o, {"name": "Bad", "phone": "+966500000019", "optin": 1, "tags": [cls.vip]})
        cls.c4, _ = db.save_contact(o, {"name": "Mona", "phone": "+966500000013", "optin": 1})
        cls.c5, _ = db.save_contact(o, {"name": "Unknown", "phone": "+966500000014", "tags": [cls.vip]})
        cls.c6, _ = db.save_contact(o, {"name": "No", "phone": "+966500000015", "optin": 0, "tags": [cls.vip]})
        db.add_bot_user(cls.bot, 966500000016, "Stop", peer="wa:966500000016")
        db.set_optin(cls.bot, "wa:966500000016", True)
        db.set_opt_out(cls.bot, "wa:966500000016", True)
        cls.seg, _ = db.save_segment(o, "VIPs", [{"field": "tags", "op": "has_any", "value": [cls.vip]}])
        cls.c = _client(o)

    def setUp(self):
        META["ok"] = True
        web._login_attempts.clear()

    def create(self, **kw):
        body = {"bot_id": self.bot, "template": "promo", "lang": "ar",
                "vars": [{"src": "contact", "field": "name", "fallback": "عميلنا"}, {"src": "text", "text": "20%"}],
                "audience": {"type": "segment", "id": self.seg}, "policy_optin": True}
        body.update(kw)
        return post(self.c, "/api/broadcasts", body)


class AudienceTests(Base):
    def peers(self, spec, optin=True):
        return {a["peer"] for a in db.campaign_audience(self.owner, self.bot, spec, optin)}

    def test_policy_on_keeps_only_consenting_and_never_stop(self):
        self.assertEqual(self.peers({"type": "segment", "id": self.seg}),
                         {"wa:966500000011", "wa:966500000012", "wa:966500000019"})

    def test_policy_off_still_excludes_refusals_and_stop(self):
        p = self.peers({"type": "all"}, optin=False)
        self.assertIn("wa:966500000014", p)
        self.assertNotIn("wa:966500000015", p, "موافقة 0 = رفض صريح")
        self.assertNotIn("wa:966500000016", p, "STOP من داخل المحادثة")

    def test_foreign_segment_is_empty(self):
        other = _user("bo" + secrets.token_hex(3))
        self.assertEqual(db.campaign_audience(other, self.bot, {"type": "segment", "id": self.seg}), [])


class LaunchMoneyTests(Base):
    def test_marketing_charges_first_and_refunds_what_meta_rejected(self):
        db.wallet_topup(self.owner, 100 * PRICE)
        before = db.wallet_balance(self.owner)
        SENT.clear()
        r = self.create().get_json()
        self.assertTrue(r["ok"], r)
        self.assertEqual((r["total"], r["charged"]), (3, 3 * PRICE))
        wait()
        self.assertEqual(db.wallet_balance(self.owner), before - 2 * PRICE, "الرقم المرفوض يُردّ")
        cp = db.get_campaign(r["id"])
        self.assertEqual((cp["status"], cp["charged"], cp["refunded"]), ("done", 2 * PRICE, PRICE))
        # متغيّرات لكل مستلم: الاسم أو البديل
        bodies = {p["to"]: p["template"]["components"][0]["parameters"][0]["text"] for p in SENT}
        self.assertEqual(bodies["966500000011"], "Ali")
        self.assertEqual(bodies["966500000012"], "عميلنا")
        # كل رسالة موسومة بالحملة في سجل الحالات
        self.assertEqual(db.wa_delivery_stats([self.bot], campaign_id=r["id"])["total"], 3)
        s = db.campaign_stats(r["id"])
        self.assertEqual((s["recipients"], s["sent"], s["failed"], s["failures"]),
                         (3, 2, 1, {"not_on_whatsapp": 1}))

    def test_not_enough_credit_sends_nothing_and_charges_nothing(self):
        owner = _user("poor" + secrets.token_hex(3))
        bot = wa_bot(owner)
        db.save_contact(owner, {"name": "A", "phone": "+966500000031", "optin": 1})
        SENT.clear()
        r = post(_client(owner), "/api/broadcasts", {"bot_id": bot, "template": "img" if False else "promo", "lang": "ar",
                 "vars": [{"src": "text", "text": "a"}, {"src": "text", "text": "b"}], "audience": {"type": "all"}})
        self.assertEqual(r.get_json()["error"], "balance")
        self.assertEqual((SENT, db.wallet_balance(owner)), ([], 0))
        self.assertEqual(db.get_campaign(r.get_json()["id"])["status"], "failed")

    def test_utility_templates_are_free(self):
        before = db.wallet_balance(self.owner)
        r = self.create(template="notice", vars=[{"src": "text", "text": "x"}]).get_json()
        self.assertTrue(r["ok"], r)
        wait()
        self.assertEqual((r["charged"], db.wallet_balance(self.owner)), (0, before))

    def test_unknown_category_means_no_send(self):
        META["ok"] = False
        SENT.clear()
        r = self.create().get_json()
        self.assertEqual(r["error"], "template")          # لا نعرف القالب ولا فئته — لا إرسال
        self.assertEqual(SENT, [])

    def test_a_campaign_cannot_be_launched_twice(self):
        db.wallet_topup(self.owner, 100 * PRICE)
        r = self.create().get_json()
        wait()
        with self.assertRaises(BC.LaunchError):
            BC.launch(r["id"])


class ScheduleRetryTests(Base):
    def test_scheduled_campaign_charges_only_when_it_fires(self):
        db.wallet_topup(self.owner, 100 * PRICE)
        at = int(time.time()) + 3600
        r = self.create(scheduled_at=at).get_json()
        self.assertEqual(r["status"], "scheduled")
        bal = db.wallet_balance(self.owner)
        BC.tick(now=at - 10)
        self.assertEqual(db.get_campaign(r["id"])["status"], "scheduled")
        BC.tick(now=at + 1)
        wait()
        cp = db.get_campaign(r["id"])
        self.assertEqual(cp["status"], "done")
        self.assertEqual(db.wallet_balance(self.owner), bal - 2 * PRICE)

    def test_cancel_before_it_fires(self):
        r = self.create(scheduled_at=int(time.time()) + 3600).get_json()
        self.assertTrue(post(self.c, f"/api/broadcasts/{r['id']}/cancel").get_json()["ok"])
        BC.tick(now=int(time.time()) + 7200)
        self.assertEqual(db.get_campaign(r["id"])["status"], "cancelled")

    def test_smart_retry_resends_only_temporary_failures(self):
        db.wallet_topup(self.owner, 100 * PRICE)
        r = self.create(retry=True, retry_hours=24).get_json()
        wait()
        # Meta قبلت 2 ثم أعلنت فشل أحدهما بحدّ التكرار (مؤقت) — المرفوض 131026 لا يُعاد
        rs = {x["peer"]: x for x in db.campaign_recipient_states(r["id"])}
        w = rs["wa:966500000011"]["wamid"]
        db.apply_wa_statuses([{"wamid": w, "status": "failed", "ts": 1, "code": 131049, "title": "",
                               "category": None, "billable": None}])
        cp = db.get_campaign(r["id"])
        bal = db.wallet_balance(self.owner)
        SENT.clear()
        BC.tick(now=cp["next_retry_at"] + 1)
        wait()
        self.assertEqual([p["to"] for p in SENT], ["966500000011"])
        self.assertEqual(db.wallet_balance(self.owner), bal - PRICE)
        self.assertEqual(db.get_campaign(r["id"])["retries"], 1)


class StatsRetargetTests(Base):
    def test_funnel_replies_and_retarget(self):
        db.wallet_topup(self.owner, 100 * PRICE)
        r = self.create().get_json()
        wait()
        rs = {x["peer"]: x for x in db.campaign_recipient_states(r["id"])}
        db.apply_wa_statuses([{"wamid": rs["wa:966500000011"]["wamid"], "status": "read", "ts": 5,
                               "code": None, "title": "", "category": None, "billable": None},
                              {"wamid": rs["wa:966500000012"]["wamid"], "status": "delivered", "ts": 5,
                               "code": None, "title": "", "category": None, "billable": None}])
        db.log_message(self.bot, "wa:966500000011", "in", "customer", "مهتم")
        s = db.campaign_stats(r["id"])
        self.assertEqual({k: s[k] for k in ("sent", "delivered", "read", "replied", "delivered_not_replied", "failed")},
                         {"sent": 2, "delivered": 2, "read": 1, "replied": 1, "delivered_not_replied": 1, "failed": 1})
        tgt = lambda st: {a["peer"] for a in db.campaign_audience(
            self.owner, self.bot, {"type": "retarget", "campaign_id": r["id"], "state": st})}
        self.assertEqual(tgt("delivered_not_replied"), {"wa:966500000012"})
        self.assertEqual(tgt("not_read"), {"wa:966500000012"})
        self.assertEqual(tgt("failed"), {"wa:966500000019"})
        d = self.c.get(f"/api/broadcasts/{r['id']}").get_json()
        self.assertEqual(d["campaign"]["stats"]["replied"], 1)
        csv_ = self.c.get(f"/broadcasts/{r['id']}/export.csv").get_data(as_text=True)
        self.assertIn("not_on_whatsapp", csv_)


class ValidationTests(Base):
    def test_variable_count_must_match_the_template(self):
        self.assertEqual(self.create(vars=[{"src": "text", "text": "x"}]).get_json()["error"], "vars_count")

    def test_only_approved_templates(self):
        self.assertEqual(self.create(template="draft_tpl", vars=[]).get_json()["error"], "template")

    def test_image_header_needs_an_owned_image(self):
        self.assertEqual(self.create(template="img", vars=[]).get_json()["error"], "header_media")

    def test_contact_variables_must_be_known_fields(self):
        r = self.create(vars=[{"src": "contact", "field": "pw_hash"}, {"src": "text", "text": "x"}])
        self.assertEqual(r.get_json()["error"], "var_field")

    def test_another_accounts_bot_is_refused(self):
        other = _user("ot" + secrets.token_hex(3))
        self.assertEqual(self.create(bot_id=wa_bot(other)).get_json()["error"], "bot")

    def test_schedule_window(self):
        self.assertEqual(self.create(scheduled_at=int(time.time()) + 5).get_json()["error"], "schedule")
        self.assertEqual(self.create(scheduled_at=int(time.time()) + 90 * 86400).get_json()["error"], "schedule")

    def test_members_cannot_send_campaigns_and_free_plans_are_locked(self):
        m = _user("mm" + secrets.token_hex(3), plan=None)
        self.assertEqual(db.join_team(self.owner, m, "member"), "")
        self.assertEqual(post(_client(m), "/api/broadcasts", {}).status_code, 403)
        free = _user("fr" + secrets.token_hex(3), plan=None)
        self.assertEqual(_client(free).get("/broadcasts").status_code, 302)

    def test_estimate_matches_what_launch_charges(self):
        e = post(self.c, "/api/broadcasts/estimate", {"bot_id": self.bot, "template": "promo", "lang": "ar",
                 "audience": {"type": "segment", "id": self.seg}, "policy_optin": True}).get_json()
        self.assertEqual((e["count"], e["category"], e["cost"]), (3, "MARKETING", 3 * PRICE))


if __name__ == "__main__":
    unittest.main(verbosity=2)
