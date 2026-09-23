"""عملاء واتساب بأرقام مخفية (اسم مستخدم · BSUID): البوت يرد عليهم والمحادثة تظهر في الصندوق.
    python tests/test_wa_bsuid.py
"""
import asyncio, os, sys, tempfile, unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_TMP = tempfile.mkdtemp(prefix="botyalla-bsuid-")
os.environ["BOTYALLA_DB"] = os.path.join(_TMP, "t.db")        # قبل أي استيراد
os.environ["BOTYALLA_UPLOADS"] = _TMP
os.environ["BOTYALLA_LOGS"] = _TMP

import database as db                             # noqa: E402
import flow_engine as FE                          # noqa: E402
import inbox_relay                                # noqa: E402
import channels.whatsapp as W                     # noqa: E402
import app as A                                   # noqa: E402

U1, U2 = "EG.13491208655302741918", "EG.99887766554433221100"
CSRF = "c" * 32


def payload(msg, contact=None):
    return {"entry": [{"changes": [{"value": {
        "metadata": {"phone_number_id": "123"},
        "contacts": [contact or {"profile": {"name": "Shaarawy"}, "user_id": msg.get("from_user_id", "")}],
        "messages": [msg]}}]}]}


def hidden(mid, body, uid=U1):
    """Meta تحذف `from` تماماً لمن أخفى رقمه، و`from_user_id` موجود دائماً."""
    return {"id": mid, "from_user_id": uid, "type": "text", "text": {"body": body}}


class R:
    status_code = 200
    def json(self): return {"messages": [{"id": "wamid.x"}]}
    text = ""


class Err400:
    """رفض Meta الحقيقي حين يكون الحقل خاطئاً."""
    status_code = 400
    text = '{"error":{"message":"(#100) The parameter recipient is required.","code":100}}'
    def json(self): return {"error": {"message": "The parameter recipient is required.",
                                      "code": 100}}


class FakeHttp:
    sent = []
    is_closed = False
    # ردّ لكل طلب بالترتيب؛ الفارغ يعني 200
    replies = []

    async def post(self, url, json=None, headers=None, **k):
        FakeHttp.sent.append(json)
        if FakeHttp.replies:
            return FakeHttp.replies.pop(0)
        return R()


def setUpModule():
    db.init_db()


class NormalizeTests(unittest.TestCase):
    ch = W.WhatsAppChannel("123", "tok")

    def test_hidden_number_message_is_kept_with_its_user_id(self):
        m = self.ch.normalize(payload(hidden("m1", "بوت كفته ولا ايه ؟")))
        self.assertIsNotNone(m, "كانت تُرمى فلا يرد البوت ولا تظهر في الصندوق")
        self.assertEqual(m["peer"], f"wa:{U1}")
        self.assertEqual(m["text"], "بوت كفته ولا ايه ؟")

    def test_phone_wins_and_links_the_user_id(self):
        m = self.ch.normalize(payload({"id": "m2", "from": "201001112223", "from_user_id": U2,
                                       "type": "text", "text": {"body": "hi"}}))
        self.assertEqual(m["peer"], "wa:201001112223")
        m = self.ch.normalize(payload(hidden("m3", "تاني", U2)))
        self.assertEqual(m["peer"], "wa:201001112223", "نفس العميل يرجع لنفس المحادثة لما رقمه يختفي")

    def test_username_is_the_name_when_no_profile_name(self):
        m = self.ch.normalize(payload(hidden("m4", "x"), contact={"profile": {"username": "shaarawy"}, "user_id": U1}))
        self.assertEqual(m["name"], "@shaarawy")

    def test_no_identity_at_all_is_dropped(self):
        self.assertIsNone(self.ch.normalize(payload({"id": "m5", "type": "text", "text": {"body": "x"}},
                                                    contact={"profile": {"name": "?"}})))
        self.assertIsNone(self.ch.normalize(payload({"id": "m6", "from_user_id": "not-valid", "type": "text",
                                                     "text": {"body": "x"}}, contact={"profile": {}})))


class SendTests(unittest.TestCase):
    def setUp(self):
        FakeHttp.sent = []
        FakeHttp.replies = []
        self._c = W._client
        W._client = FakeHttp()

    def tearDown(self):
        W._client = self._c

    def test_reply_to_hidden_number_uses_to(self):
        """الإنتاج ردّ «The parameter to is required» 21 مرة على `recipient`،
        فكل رسالة لعميل مخفي الرقم كانت تضيع بصمت. الحقل `to` كأي عميل."""
        ch = W.WhatsAppChannel("123", "tok")
        asyncio.run(ch.send_text(f"wa:{U1}", "أهلاً"))
        body = FakeHttp.sent[-1]
        self.assertEqual(body.get("to"), U1)
        self.assertNotIn("recipient", body)
        asyncio.run(ch.send_buttons(f"wa:{U1}", "اختار", ["أ", "ب"]))
        self.assertEqual(FakeHttp.sent[-1].get("to"), U1)

    def test_a_meta_refusal_naming_recipient_is_retried_once(self):
        """لو عادت Meta تطلب الحقل الآخر: محاولة واحدة به، بلا خصم ثانٍ من العدّاد."""
        charged = []

        async def on_send():
            charged.append(1)
            return True

        ch = W.WhatsAppChannel("123", "tok", on_send=on_send)
        FakeHttp.replies = [Err400()]                 # الأولى تُرفض، والثانية تنجح
        res = asyncio.run(ch.send_text(f"wa:{U1}", "أهلاً"))
        self.assertIsNotNone(res, "الرسالة يجب أن تصل في المحاولة الثانية")
        self.assertEqual(len(FakeHttp.sent), 2)
        self.assertEqual(FakeHttp.sent[0].get("to"), U1)
        self.assertEqual(FakeHttp.sent[1].get("recipient"), U1)
        self.assertNotIn("to", FakeHttp.sent[1])
        self.assertEqual(len(charged), 1, "لا تُخصم رسالتان من رصيد الباقة")

    def test_a_phone_refusal_is_not_retried(self):
        """الرفض لعميل برقم عادي لا علاقة له بالحقل — لا إعادة محاولة."""
        ch = W.WhatsAppChannel("123", "tok")
        FakeHttp.replies = [Err400()]
        self.assertIsNone(asyncio.run(ch.send_text("wa:201001234567", "x")))
        self.assertEqual(len(FakeHttp.sent), 1)

    def test_phone_still_uses_to(self):
        asyncio.run(W.WhatsAppChannel("123", "tok").send_text("wa:201001234567", "x"))
        self.assertEqual(FakeHttp.sent[-1].get("to"), "201001234567")
        self.assertNotIn("recipient", FakeHttp.sent[-1])


class IdentityTests(unittest.TestCase):
    def test_hidden_customers_get_distinct_stable_ids(self):
        a, b = FE._peer_num(f"wa:{U1}"), FE._peer_num(f"wa:{U2}")
        self.assertNotEqual(a, 0)
        self.assertNotEqual(a, b, "كانوا كلهم 0 فيمحو كل عميل الآخر في bot_users")
        self.assertEqual(a, FE._peer_num(f"wa:{U1}"))
        self.assertEqual(FE._peer_num("wa:201001234567"), 201001234567)

    def test_peer_patterns_accept_bsuid(self):
        self.assertTrue(A._PEER_RE.match(f"wa:{U1}"))
        self.assertFalse(A._PEER_RE.match("wa:"))
        self.assertFalse(A._PEER_RE.match("wa:EG.bad id"))
        self.assertEqual(inbox_relay.parse(f"x #C5:wa:{U1}"), (5, f"wa:{U1}"))

    def test_alert_shows_hidden_number_label_and_long_ids_skip_button(self):
        self.assertIsNotNone(inbox_relay._markup(5, f"wa:{U1}"))
        self.assertIsNone(inbox_relay._markup(5, "wa:EG." + "a" * 100))


class InboxTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with db.get_conn() as c:
            c.execute("INSERT OR IGNORE INTO users(id,username,pw_hash,role,created_at) VALUES(1,'root','x','admin',0)")
        cls.bot = db.create_bot(1, "wa", "wa:123", "customer_service", {"business_name": "x"}, channel="whatsapp")
        db.add_bot_user(cls.bot, FE._peer_num(f"wa:{U1}"), "Shaarawy", peer=f"wa:{U1}")
        db.log_message(cls.bot, f"wa:{U1}", "in", "user", "بوت كفته ولا ايه ؟")
        with db.get_conn() as c:       # محادثة قديمة بلا هوية (قبل التحديث) — log_message يرفضها الآن
            c.execute("INSERT INTO messages(bot_id,peer,direction,sender,kind,text,created_at) "
                      "VALUES(?,'wa:','in','user','text','رسالة قديمة بلا رقم',1)", (cls.bot,))
            c.execute("INSERT INTO conversations(bot_id,peer,name,unread,last_text,last_at) "
                      "VALUES(?,'wa:','Shaarawy',10,'x',1)", (cls.bot,))

    def client(self):
        c = A.app.test_client()
        u = db.get_user(1)
        with c.session_transaction() as s:
            s.update(_csrf=CSRF, uid=1, uname=u["username"], role="admin", pwv=A._pw_stamp(u["pw_hash"]))
        return c

    def test_hidden_number_thread_opens(self):
        d = self.client().get(f"/api/bot/{self.bot}/inbox/thread?peer=wa:{U1}").get_json()
        self.assertEqual([m["text"] for m in d["messages"]], ["بوت كفته ولا ايه ؟"])

    def test_legacy_empty_thread_is_readable_not_replyable(self):
        c = self.client()
        r = c.get(f"/api/bot/{self.bot}/inbox/thread?peer=wa:")
        self.assertEqual(r.status_code, 200, "كانت 404 فتعلق الشاشة على «…»")
        self.assertEqual(r.get_json()["messages"][0]["text"], "رسالة قديمة بلا رقم")
        r = c.post(f"/bot/{self.bot}/inbox/send", json={"peer": "wa:", "text": "x"}, headers={"X-CSRF-Token": CSRF})
        self.assertEqual(r.status_code, 404)


class Ch:
    def __init__(self): self.sent = []
    async def send_text(self, p, t): self.sent.append((p, t))
    async def send_buttons(self, p, t, o): self.sent.append((p, t))
    async def remove_keyboard(self, p, t): self.sent.append((p, t))
    async def send_typing(self, p): pass
    async def send_photo(self, p, *a, **k): self.sent.append((p, "photo"))
    async def fetch_media(self, m): return None, None


class EndToEndTests(unittest.TestCase):
    def test_bot_replies_and_two_hidden_customers_stay_separate(self):
        with db.get_conn() as c:
            c.execute("INSERT OR IGNORE INTO users(id,username,pw_hash,role,created_at) VALUES(1,'root','x','admin',0)")
        bid = db.create_bot(1, "shop", "wa:777", "customer_service", {"business_name": "محل"}, channel="whatsapp")
        row = dict(db.get_bot(bid))
        for uid, text in ((U1, "مرحبا"), (U2, "مرحبا")):
            ch = Ch()
            asyncio.run(FE.handle_message(row, ch, {"id": "x" + uid, "peer": f"wa:{uid}", "kind": "start",
                                                     "text": text, "name": "عميل"}))
            self.assertTrue(ch.sent, "البوت رد")
            self.assertTrue(all(p == f"wa:{uid}" for p, _ in ch.sent))
        self.assertTrue(db.bot_user_exists(bid, f"wa:{U1}"))
        self.assertTrue(db.bot_user_exists(bid, f"wa:{U2}"), "العميل الثاني لم يمحُ الأول")
        peers = {c["peer"] for c in db.list_conversations(bid)}
        self.assertTrue({f"wa:{U1}", f"wa:{U2}"} <= peers, "المحادثتان ظاهرتان في الصندوق")


if __name__ == "__main__":
    unittest.main()
