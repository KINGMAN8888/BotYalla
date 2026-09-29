"""HyperPay (المرحلة 9): صفحة دفع عندنا بسكربتهم · جلسة لكل فتح · مدى بكيان منفصل · الحالة بمرجعنا · المسح الدوري.

خادم oppwa محاكى — لا شبكة ولا مال. القاعدة والملفات في مجلد مؤقت.
"""
import asyncio, json, os, secrets, sys, tempfile, time, unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_TMPDIR = tempfile.mkdtemp(prefix="botyalla-hp-")
os.environ["BOTYALLA_DB"] = os.path.join(_TMPDIR, "test.db")   # قبل استيراد database
os.environ["BOTYALLA_UPLOADS"] = _TMPDIR
os.environ["BOTYALLA_LOGS"] = os.path.join(_TMPDIR, "logs")
os.environ["ADMIN_USER"] = "admin"
os.environ["ADMIN_PASS"] = "Hp#" + secrets.token_hex(6)
os.environ["PUBLIC_URL"] = "https://botyalla.test"

import auth                                # noqa: E402
import chat_pay as CP                      # noqa: E402
import database as db                      # noqa: E402
import payments_gw as GW                   # noqa: E402
import app as web                          # noqa: E402

PW = "Str0ng!Pass" + secrets.token_hex(3)
db.init_db(); web.seed_platform_defaults(); web.contact_defaults(); web.seed_default_admin()
web.app.config["TESTING"] = True
TOKEN = "OGE4Mjk0MTc0YjdlY2IyODAxNGI5Njk5MjIwMDE1Y2N8c3k2S0pzVDg="
CARD, MADA = "8a8294174b7ecb28014b9699220015ca", "8a8294174b7ecb28014b9699220015cb"


class R:
    def __init__(self, code, body):
        self.status_code, self._b, self.text = code, body, json.dumps(body)

    def json(self):
        return self._b


class Oppwa:
    def __init__(self):
        self.checkouts, self.payments, self.queries = [], {}, 0

    def post(self, url, headers=None, data=None, **k):
        if headers.get("Authorization") != f"Bearer {TOKEN}":
            return R(401, {"result": {"code": "800.900.300"}})
        assert url.startswith("https://eu-test.oppwa.com/v1/checkouts")
        self.checkouts.append(dict(data))
        return R(200, {"id": "CHK" + secrets.token_hex(6), "result": {"code": "000.200.100"}})

    def get(self, url, headers=None, params=None, **k):
        self.queries += 1
        pays = self.payments.get((params["entityId"], params["merchantTransactionId"]))
        return R(200, {"payments": pays}) if pays else R(400, {"result": {"code": "700.400.580"}})


OPP = Oppwa()
GW._client = lambda http: OPP


class Ch:
    phone_id = page_id = None

    def __init__(self):
        self.out = []

    async def send_text(self, peer, text):
        self.out.append(("text", text)); return True

    async def remove_keyboard(self, peer, text):
        self.out.append(("text", text)); return True

    async def send_cta(self, peer, text, button, url):
        self.out.append(("cta", url)); return True


CH = Ch()
web._pay_channel = lambda bot_row, peer: CH
CP.HOOKS["channel"] = lambda bot_row, peer: CH


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


class HyperPayTests(unittest.TestCase):
    def setUp(self):
        self.owner = user("hp")
        self.c = client(self.owner)
        self.bot = db.create_bot(self.owner, "WA", f"wa:{secrets.randbelow(10**12)}", "flow", {"bot_username": "966500000777"}, "whatsapp")
        self.peer = f"wa:9665{secrets.randbelow(10**8):08d}"
        db.add_bot_user(self.bot, int(self.peer[3:]), "منى", peer=self.peer)
        db.log_message(self.bot, self.peer, "in", "customer", "مرحبا", name="منى")
        db.touch_bot_user(self.bot, self.peer)

    def connect(self, mada=True):
        return post(self.c, "/api/pay/settings", {"provider": "hyperpay", "currency": "SAR", "secret": TOKEN,
                                                  "entity": CARD, "entity_mada": MADA if mada else "", "test": True}).get_json()

    def request(self, amount="1350"):
        r = post(self.c, "/api/pay/request", {"bot": self.bot, "peer": self.peer, "amount": amount, "description": "حجز جناح"}).get_json()
        assert r["ok"], r
        return r["payment"]

    def test_settings_validation_and_secret_sealed(self):
        bad = post(self.c, "/api/pay/settings", {"provider": "hyperpay", "secret": TOKEN, "entity": "xyz"}).get_json()
        self.assertEqual(bad["error"], "entity")
        r = self.connect()
        self.assertTrue(r["ok"], r)
        self.assertEqual((r["config"]["entity"], r["config"]["entity_mada"], r["config"]["test"]), (CARD, MADA, True))
        self.assertNotIn(TOKEN, db.get_setting(self.owner, CP.CFG_KEY))
        self.assertNotIn(TOKEN, self.c.get("/payments").get_data(as_text=True))
        self.assertTrue(post(self.c, "/api/pay/test").get_json()["ok"])
        self.assertEqual({c["entityId"] for c in OPP.checkouts[-2:]}, {CARD, MADA}, "الفحص يثبت الكيانين")

    def test_hosted_page_mada_choice_checkout_and_paid(self):
        self.connect()
        p = self.request()
        self.assertEqual(p["gw_id"], f"by{p['id']}")
        self.assertTrue(p["url"].startswith(f"https://botyalla.test/pay/h/{p['id']}/"))
        self.assertEqual(CH.out[-1], ("cta", p["url"]))
        path = "/" + p["url"].split("://", 1)[1].split("/", 1)[1]
        cl = web.app.test_client()
        self.assertEqual(cl.get(f"/pay/h/{p['id']}/bad").status_code, 404)
        page = cl.get(path).get_data(as_text=True)
        self.assertIn("?b=mada", page)
        self.assertIn("?b=card", page)
        n = len(OPP.checkouts)
        r = cl.get(path + "?b=mada")
        html, csp = r.get_data(as_text=True), r.headers["Content-Security-Policy"]
        self.assertEqual(len(OPP.checkouts), n + 1)
        self.assertEqual((OPP.checkouts[-1]["entityId"], OPP.checkouts[-1]["amount"], OPP.checkouts[-1]["merchantTransactionId"]),
                         (MADA, "1350.00", p["gw_id"]))
        self.assertIn('data-brands="MADA"', html)
        self.assertIn("https://eu-test.oppwa.com/v1/paymentWidgets.js?checkoutId=CHK", html)
        self.assertIn("frame-src https://eu-test.oppwa.com", csp)
        self.assertIn(f'action="{CP.return_url(p["id"])}"', html)
        # فشل بطاقة لا يُنهي الرابط — العميل يعيد المحاولة
        OPP.payments[(MADA, p["gw_id"])] = [{"result": {"code": "800.100.151"}, "paymentType": "DB"}]
        self.assertEqual(CP.confirm(p["id"]), "pending")
        OPP.payments[(MADA, p["gw_id"])].append({"result": {"code": "000.100.110"}, "paymentType": "DB"})
        ret = cl.get("/" + CP.return_url(p["id"]).split("://", 1)[1].split("/", 1)[1]).get_data(as_text=True)
        self.assertIn("تم الدفع بنجاح", ret)
        self.assertEqual(db.get_chat_payment(p["id"])["status"], "paid")
        self.assertEqual(cl.get(path).status_code, 302, "مدفوعة ⇒ صفحة العودة لا جلسة جديدة")

    def test_single_entity_brands_and_background_poll(self):
        self.connect(mada=False)
        p = self.request("99.5")
        path = "/" + p["url"].split("://", 1)[1].split("/", 1)[1]
        html = web.app.test_client().get(path).get_data(as_text=True)
        self.assertIn('data-brands="VISA MASTER MADA"', html)
        self.assertEqual(OPP.checkouts[-1]["amount"], "99.50")
        OPP.payments[(CARD, p["gw_id"])] = [{"result": {"code": "000.000.000"}, "paymentType": "DB"}]
        with db.get_conn() as c:
            c.execute("UPDATE chat_payments SET created_at=? WHERE id=?", (int(time.time()) - 120, p["id"]))
        CP._CHECKED.clear()
        CP.HOOKS["run"] = asyncio.run
        CP.sweep()
        self.assertEqual(db.get_chat_payment(p["id"])["status"], "paid", "المسح الدوري يلتقط الدفع بلا ويبهوك")
        q = OPP.queries
        CP.sweep()
        self.assertEqual(OPP.queries, q, "المدفوعة لا تُسأل ثانيةً")


if __name__ == "__main__":
    unittest.main(verbosity=2)
