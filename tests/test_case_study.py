"""الحالة المرجعية (خطة النمو — business/DEV_REQUIREMENTS_GROWTH.md §6) + صفحة الوكالات.
    python tests/test_case_study.py
"""
import asyncio, json, os, sys, tempfile, unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_TMP = tempfile.mkdtemp(prefix="botyalla-case-")
os.environ["BOTYALLA_DB"] = os.path.join(_TMP, "t.db")        # قبل أي استيراد
os.environ["BOTYALLA_UPLOADS"] = _TMP
os.environ["BOTYALLA_LOGS"] = _TMP
os.environ["PUBLIC_URL"] = "https://botyalla.test"

import database as db          # noqa: E402
import flow_engine as FE       # noqa: E402
import platform_kb             # noqa: E402
import app as A                # noqa: E402

CSRF = "c" * 32


class Ch:
    def __init__(self):
        self.sent = []

    async def send_text(self, p, t): self.sent.append(("text", t))
    async def send_buttons(self, p, t, o): self.sent.append(("buttons", t, list(o)))
    async def remove_keyboard(self, p, t): self.sent.append(("text", t))
    async def send_document_link(self, p, url, name, caption=""): self.sent.append(("doc", url, caption))
    async def fetch_media(self, m): return None, None


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        db.init_db()
        with db.get_conn() as c:
            c.execute("INSERT OR IGNORE INTO users(id,username,pw_hash,role,created_at) VALUES(1,'root','x','admin',0)")
            c.execute("INSERT OR IGNORE INTO users(username,pw_hash,role,created_at) VALUES('shop','x','user',0)")
        cls.shop = db.get_user_by_name("shop")["id"]
        # الفئات تتشارك قاعدة الملف — الإنشاء مرة واحدة
        def bot(owner, name, token, cfg):
            row = db.get_bot_by_token(token)
            return row["id"] if row else db.create_bot(owner, name, token, "customer_service", cfg,
                                                       channel="whatsapp")
        cls.official = bot(1, "BotYalla", "wa:1111", {"business_name": "BotYalla", "response_mode": "ai",
                                                      "platform_kb": True, "bot_username": "+201281275886"})
        cls.customer = bot(cls.shop, "shop", "wa:2222", {"business_name": "رغد"})

    def setUp(self):
        A._login_attempts.clear()
        self.alerts = []
        self._notify = A.notify_admins
        A.notify_admins = self.alerts.append

    def tearDown(self):
        A.notify_admins = self._notify

    def client(self):
        c = A.app.test_client()
        with c.session_transaction() as s:
            s["_csrf"] = CSRF
        return c

    def lead(self, c=None, **kw):
        body = {"name": "م. أحمد", "company": "مصنع النيل", "role": "مدير مبيعات",
                "phone": "+20 100 123 4567", "consent": True, "segment": "factory"}
        body.update(kw)
        return (c or self.client()).post("/case-study/lead", json=body, headers={"X-CSRF-Token": CSRF})


class PageTests(Base):
    def test_b2b_pages_carry_the_form_others_dont(self):
        for code in ("factory", "company", "agency"):
            html = self.client().get(f"/for/{code}").get_data(as_text=True)
            self.assertIn('"caseStudy": true', html, code)
        html = self.client().get("/for/market").get_data(as_text=True)
        self.assertNotIn('"caseStudy"', html)

    def test_agency_segment_page_exists(self):
        r = self.client().get("/for/agency")
        self.assertEqual(r.status_code, 200)
        self.assertIn("البطاقة البيضاء", r.get_data(as_text=True))

    def test_short_link_redirects_to_the_form(self):
        r = self.client().get("/case-study")
        self.assertEqual(r.status_code, 302)
        self.assertTrue(r.headers["Location"].endswith("/for/factory#case"))


class LeadTests(Base):
    def test_valid_lead_is_stored_alerted_and_links_start_the_chat(self):
        d = self.lead().get_json()
        self.assertTrue(d["ok"], d)
        self.assertIn("%23case", d["wa"])                    # «مرحبا #case» — العميل هو من يبدأ
        leads = db.list_leads(self.official)
        data = json.loads(leads[0]["data_json"]) if "data_json" in leads[0] else leads[0]["data"]
        self.assertEqual(data["source"], "case_study")
        self.assertEqual(data["phone"], "+201001234567")
        self.assertTrue(data["consent"] and data["consent_at"])       # قانون 151/2020
        self.assertTrue(any("مصنع النيل" in a for a in self.alerts))

    def test_consent_is_required(self):
        r = self.lead(consent=False)
        self.assertEqual(r.status_code, 400)
        r = self.lead(consent="yes")                         # قيمة منطقية حقيقية فقط
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self.alerts, [])

    def test_bad_phone_and_missing_fields(self):
        self.assertEqual(self.lead(phone="abc").status_code, 400)
        self.assertEqual(self.lead(company="").status_code, 400)

    def test_csrf_and_rate_limit(self):
        r = self.client().post("/case-study/lead", json={"name": "x"})
        self.assertEqual(r.status_code, 400)
        c = self.client()
        codes = [self.lead(c).status_code for _ in range(6)]
        self.assertEqual(codes[:5], [200] * 5)
        self.assertEqual(codes[5], 429)


class BotTests(Base):
    def say(self, bid, text):
        ch = Ch()
        asyncio.run(FE.handle_message(db.get_bot(bid), ch, {
            "peer": "wa:201001234567", "kind": "start", "text": text,
            "start_arg": "seg-case", "name": "أحمد"}))
        return ch.sent

    def test_official_bot_sends_the_pdf_to_whoever_started_the_chat(self):
        self.assertEqual(platform_kb.official_bot()["id"], self.official)
        sent = self.say(self.official, "مرحبا #case")
        docs = [s for s in sent if s[0] == "doc"]
        self.assertEqual(len(docs), 1)
        self.assertEqual(docs[0][1], "https://botyalla.test/static/BotYalla_Case_Study.pdf")
        self.assertIn("مش نتايج عميل", docs[0][2])            # لا ادّعاء نتائج (AGENTS §3.26)

    def test_customer_bots_never_send_our_pdf(self):
        sent = self.say(self.customer, "مرحبا #case")
        self.assertFalse([s for s in sent if s[0] == "doc"])

    def test_pdf_is_publicly_served(self):
        r = self.client().get("/static/BotYalla_Case_Study.pdf")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.mimetype, "application/pdf")


class PricingTests(Base):
    def test_annual_discount_badge_matches_the_real_factor(self):
        import plans
        self.assertAlmostEqual(plans.ANNUAL_FACTOR, 0.70)   # «وفر 30%» صادقة


if __name__ == "__main__":
    unittest.main(verbosity=2)
