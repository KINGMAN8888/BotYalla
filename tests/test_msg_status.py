"""حالة رسائل واتساب الصادرة — المرحلة 2: تسجيل كل إرسال بمعرّف Meta · تحديثات الويبهوك
(مرتّبة لا تتراجع) · تصنيف الأخطاء · وسم الحملة · الإحصاءات.

    python tests/test_msg_status.py
"""
import asyncio, hashlib, hmac, json, os, secrets, sys, tempfile, unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_TMPDIR = tempfile.mkdtemp(prefix="botyalla-msgst-")
os.environ["BOTYALLA_DB"] = os.path.join(_TMPDIR, "test.db")   # قبل استيراد database
os.environ["BOTYALLA_UPLOADS"] = _TMPDIR
os.environ["BOTYALLA_LOGS"] = os.path.join(_TMPDIR, "logs")
os.environ["ADMIN_USER"] = "admin"
os.environ["ADMIN_PASS"] = "Ms#" + secrets.token_hex(6)

import auth                                # noqa: E402
import database as db                      # noqa: E402
import msg_status as MS                    # noqa: E402
import app as web                          # noqa: E402
from channels import whatsapp as W        # noqa: E402

SECRET = "wh-" + secrets.token_hex(8)


def _boot():
    db.init_db()
    web.seed_platform_defaults()
    web.contact_defaults()
    web.seed_default_admin()
    web.app.config["TESTING"] = True


_boot()
OWNER = db.create_user("ms" + secrets.token_hex(3), auth.hash_password("x"))
PHONE = str(secrets.randbelow(10**12))
BOT = db.create_bot(OWNER, "wa", f"wa:{PHONE}", "store", {}, "whatsapp")


class FakeResp:
    def __init__(self, code, body):
        self.status_code, self._b = code, body
        self.text = json.dumps(body)

    def json(self):
        return self._b


def channel(responses):
    ch = W.WhatsAppChannel(PHONE, "tok", bot_id=BOT)
    it = iter(responses)

    async def raw(payload):
        return next(it)
    ch._raw = raw
    return ch


def row(wamid=None, peer=None):
    with db.get_conn() as c:
        if wamid:
            r = c.execute("SELECT * FROM wa_messages WHERE wamid=?", (wamid,)).fetchone()
        else:
            r = c.execute("SELECT * FROM wa_messages WHERE peer=? ORDER BY id DESC", (peer,)).fetchone()
    return dict(r) if r else None


def status_payload(*items):
    return {"object": "whatsapp_business_account", "entry": [{"changes": [{"value": {
        "metadata": {"phone_number_id": PHONE},
        "statuses": [dict(id=w, status=s, timestamp=str(ts), recipient_id="966500000000", **extra)
                     for w, s, ts, extra in items]}}]}]}


class PureTests(unittest.TestCase):
    def test_error_buckets(self):
        self.assertEqual(MS.bucket(131026), "not_on_whatsapp")
        self.assertEqual(MS.bucket("131049"), "frequency_limit")
        self.assertEqual(MS.bucket(131050), "unsubscribed")
        self.assertEqual(MS.bucket(132015), "template")
        self.assertEqual(MS.bucket(None), "other")
        self.assertEqual(MS.bucket(999999), "other")

    def test_parse_statuses_reads_pricing_and_errors_and_skips_junk(self):
        p = status_payload(("wamid.A", "delivered", 1700000000, {"pricing": {"category": "marketing", "billable": True}}),
                           ("wamid.B", "failed", 1700000001, {"errors": [{"code": 131049, "title": "healthy ecosystem"}]}),
                           ("wamid.C", "weird", 1, {}))
        u = MS.parse_statuses(p)
        self.assertEqual([x["wamid"] for x in u], ["wamid.A", "wamid.B"])
        self.assertEqual((u[0]["category"], u[0]["billable"]), ("marketing", 1))
        self.assertEqual((u[1]["code"], u[1]["phone_id"]), (131049, PHONE))
        self.assertEqual(MS.parse_statuses({"entry": "nonsense"}), [])
        self.assertEqual(MS.parse_statuses(None), [])

    def test_ids_and_errors_from_meta_responses(self):
        self.assertEqual(MS.wamid_from({"messages": [{"id": "wamid.Z"}]}), "wamid.Z")
        self.assertIsNone(MS.wamid_from({}))
        self.assertEqual(MS.error_from({"error": {"code": 131026, "message": "undeliverable"}}), (131026, "undeliverable"))


class SendTrackingTests(unittest.TestCase):
    def test_a_successful_send_is_recorded_as_sent(self):
        ch = channel([FakeResp(200, {"messages": [{"id": "wamid.S1"}]})])
        asyncio.run(ch.send_text("wa:966500000001", "hi"))
        r = row("wamid.S1")
        self.assertEqual((r["bot_id"], r["status"], r["kind"], r["peer"]), (BOT, "sent", "text", "wa:966500000001"))

    def test_a_rejected_send_is_recorded_as_failed_with_its_code(self):
        ch = channel([FakeResp(400, {"error": {"code": 131026, "message": "Message undeliverable"}})])
        self.assertIsNone(asyncio.run(ch.send_text("wa:966500000002", "hi")))
        r = row(peer="wa:966500000002")
        self.assertEqual((r["status"], r["error_code"], r["wamid"]), ("failed", 131026, None))

    def test_campaign_context_tags_the_message(self):
        async def go():
            MS.SEND_CTX.set({"campaign_id": 77})
            await channel([FakeResp(200, {"messages": [{"id": "wamid.C1"}]})]).send_text("wa:966500000003", "x")
        asyncio.run(go())
        self.assertEqual(row("wamid.C1")["campaign_id"], 77)

    def test_no_bot_id_means_no_tracking_and_no_crash(self):
        ch = W.WhatsAppChannel(PHONE, "tok")
        async def raw(p):
            return FakeResp(200, {"messages": [{"id": "wamid.N1"}]})
        ch._raw = raw
        asyncio.run(ch.send_text("wa:966500000004", "x"))
        self.assertIsNone(row("wamid.N1"))

    def test_a_tracking_failure_never_breaks_sending(self):
        orig = db.record_wa_send
        db.record_wa_send = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("disk"))
        try:
            res = asyncio.run(channel([FakeResp(200, {"messages": [{"id": "wamid.X"}]})]).send_text("wa:966500000005", "x"))
        finally:
            db.record_wa_send = orig
        self.assertEqual(MS.wamid_from(res), "wamid.X")


class StatusOrderTests(unittest.TestCase):
    def setUp(self):
        self.w = "wamid." + secrets.token_hex(4)
        db.record_wa_send(BOT, PHONE, "wa:966500000010", "template", self.w)

    def apply(self, *items):
        return db.apply_wa_statuses(MS.parse_statuses(status_payload(*items)))

    def test_normal_progression(self):
        self.apply((self.w, "delivered", 100, {}))
        self.apply((self.w, "read", 200, {}))
        r = row(self.w)
        self.assertEqual((r["status"], r["delivered_at"], r["read_at"]), ("read", 100, 200))

    def test_read_before_delivered_never_goes_backwards(self):
        self.apply((self.w, "read", 200, {}))
        self.apply((self.w, "delivered", 150, {}))
        r = row(self.w)
        self.assertEqual((r["status"], r["delivered_at"], r["read_at"]), ("read", 200, 200))

    def test_failed_after_read_is_ignored_and_failed_keeps_its_reason(self):
        other = "wamid." + secrets.token_hex(4)
        db.record_wa_send(BOT, PHONE, "wa:966500000011", "template", other)
        self.apply((self.w, "read", 200, {}), (self.w, "failed", 300, {"errors": [{"code": 131000}]}))
        self.assertEqual(row(self.w)["status"], "read")
        self.apply((other, "failed", 300, {"errors": [{"code": 131049, "title": "withheld"}]}))
        r = row(other)
        self.assertEqual((r["status"], r["error_code"], r["error_title"]), ("failed", 131049, "withheld"))
        self.apply((other, "delivered", 400, {}))
        self.assertEqual(row(other)["status"], "failed", "failed لا يعود delivered")

    def test_unknown_ids_are_ignored(self):
        self.assertEqual(self.apply(("wamid.never-sent", "read", 1, {})), 0)


class WebhookAndStatsTests(unittest.TestCase):
    def test_signed_webhook_updates_statuses(self):
        w = "wamid." + secrets.token_hex(4)
        db.record_wa_send(BOT, PHONE, "wa:966500000020", "template", w)
        db.set_platform("wa_app_secret", SECRET)
        body = json.dumps(status_payload((w, "read", 500, {"pricing": {"category": "utility", "billable": False}}))).encode()
        sig = "sha256=" + hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()
        r = web.app.test_client().post("/wh/whatsapp", data=body, content_type="application/json",
                                       headers={"X-Hub-Signature-256": sig})
        self.assertEqual(r.status_code, 200)
        got = row(w)
        self.assertEqual((got["status"], got["category"], got["billable"]), ("read", "utility", 0))

    def test_unsigned_statuses_change_nothing(self):
        w = "wamid." + secrets.token_hex(4)
        db.record_wa_send(BOT, PHONE, "wa:966500000021", "template", w)
        db.set_platform("wa_app_secret", SECRET)
        body = json.dumps(status_payload((w, "read", 500, {}))).encode()
        r = web.app.test_client().post("/wh/whatsapp", data=body, content_type="application/json",
                                       headers={"X-Hub-Signature-256": "sha256=bad"})
        self.assertEqual(r.status_code, 403)
        self.assertEqual(row(w)["status"], "sent")

    def test_delivery_stats_and_buckets(self):
        bot = db.create_bot(OWNER, "wa2", f"wa:{secrets.randbelow(10**12)}", "store", {}, "whatsapp")
        ids = ["wamid.st" + secrets.token_hex(3) for _ in range(4)]
        for i, w in enumerate(ids):
            db.record_wa_send(bot, PHONE, f"wa:9665000001{i}", "template", w, campaign_id=5)
        db.record_wa_send(bot, PHONE, "wa:966500000199", "template", None, 131026, "undeliverable", campaign_id=5)
        db.apply_wa_statuses(MS.parse_statuses(status_payload(
            (ids[0], "read", 10, {}), (ids[1], "delivered", 10, {}),
            (ids[2], "failed", 10, {"errors": [{"code": 131049}]}))))
        s = db.wa_delivery_stats([bot], campaign_id=5)
        self.assertEqual({k: s[k] for k in ("total", "sent", "delivered", "read", "failed")},
                         {"total": 5, "sent": 3, "delivered": 2, "read": 1, "failed": 2})
        self.assertEqual(s["failures"], {"frequency_limit": 1, "not_on_whatsapp": 1})
        self.assertEqual({f["bucket"] for f in db.wa_failed_messages([bot])}, {"frequency_limit", "not_on_whatsapp"})


if __name__ == "__main__":
    unittest.main(verbosity=2)
