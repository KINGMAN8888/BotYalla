"""الموقع العام: الرئيسية · الوثائق القانونية · 404 · ملفات محركات البحث.

ما يُختبَر هنا هو ما يجعل الموقع «رسمياً» فعلاً: الرئيسية عامة وأسعارها هي
أسعار الخادم نفسها، المحتوى مرسوم في الخادم فيُفهرَس بلا جافاسكربت، الروابط
المطلقة من `PUBLIC_URL` لا من ترويسة Host، والبيانات المنظّمة صالحة.

    python tests/test_public_site.py
"""
import json, os, re, secrets, struct, sys, tempfile, unittest
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_TMPDIR = tempfile.mkdtemp(prefix="botyalla-public-")
os.environ["BOTYALLA_DB"] = os.path.join(_TMPDIR, "test.db")   # قبل استيراد database/app
os.environ["BOTYALLA_UPLOADS"] = _TMPDIR
ADMIN_PW = os.environ.setdefault("ADMIN_PASS", f"tst_adm_{secrets.token_hex(8)}")
TEST_PW = f"tst_pw_{secrets.token_hex(8)}"
os.environ["ADMIN_USER"] = "admin"
os.environ["ADMIN_PASS"] = ADMIN_PW
os.environ["PUBLIC_URL"] = "https://botyalla.test"

import auth                                # noqa: E402
import database as db                      # noqa: E402
import i18n                                # noqa: E402
import legal_content as LEGAL              # noqa: E402
import app as web                          # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LEGAL_PATHS = {"terms": "/terms", "privacy": "/privacy", "refund": "/refund", "aup": "/acceptable-use"}


def _boot():
    db.init_db()
    web.seed_platform_defaults()
    web.contact_defaults()
    web.seed_default_admin()
    web.app.config["TESTING"] = True


def _client():
    c = web.app.test_client()
    with c.session_transaction() as s:
        s["_csrf"] = "tk"
    return c


def _by(html):
    i = html.index("window.BY = ") + len("window.BY = ")
    return json.loads(html[i:html.index(";</script>", i)])


def _jsonld(html):
    m = re.search(r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', html, re.S)
    return json.loads(m.group(1)) if m else None


class HomeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _boot()
        db.create_user("visitor1", auth.hash_password(TEST_PW))

    def setUp(self):
        web._login_attempts.clear()

    def test_the_home_page_is_public(self):
        r = web.app.test_client().get("/")
        self.assertEqual(r.status_code, 200)
        by = _by(r.get_data(as_text=True))
        self.assertEqual(by["page"], "home")
        self.assertFalse(by["auth"]["in"])

    def test_public_prices_are_the_server_prices(self):
        """ما يراه الزائر هو ما سيدفعه — لا رقم مكتوب في الواجهة."""
        with web.app.test_request_context():
            server = {p["id"]: (p["price"], p["annual_price"]) for p in web.priced_plans("ar")}
        by = _by(web.app.test_client().get("/").get_data(as_text=True))
        self.assertEqual([p["id"] for p in by["plans"]], ["free", "merchant", "whatsapp", "agency"])
        self.assertEqual({p["id"]: (p["price"], p["annual_price"]) for p in by["plans"]}, server)

    def test_the_content_is_rendered_server_side_for_crawlers(self):
        """بلا جافاسكربت: العنوان والباقات والأسئلة موجودة في HTML نفسه."""
        html = web.app.test_client().get("/?lang=ar").get_data(as_text=True)
        fallback = html[html.index('id="fallback"'):]
        self.assertIn(i18n.t("lp2_h1a", "ar"), fallback)
        for pid in ("merchant", "whatsapp", "agency"):
            self.assertIn(web.plans.plan_name(pid, "ar"), fallback)
        self.assertIn(i18n.t("lp2_q5", "ar"), fallback)

    def test_a_signed_in_visitor_gets_the_dashboard_button(self):
        c = _client()
        c.post("/login", data={"username": "visitor1", "password": TEST_PW, "csrf_token": "tk"})
        by = _by(c.get("/").get_data(as_text=True))
        self.assertTrue(by["auth"]["in"])

    def test_the_dashboard_moved_and_still_requires_login(self):
        r = web.app.test_client().get("/dashboard")
        self.assertIn("/login", r.headers["Location"])
        c = _client()
        r = c.post("/login", data={"username": "visitor1", "password": TEST_PW, "csrf_token": "tk"})
        self.assertTrue(r.headers["Location"].endswith("/dashboard"))
        self.assertEqual(c.get("/dashboard").status_code, 200)

    def test_the_old_landing_link_redirects_permanently_and_keeps_the_ref(self):
        """روابط أفيليت منشورة سابقاً على /landing?ref= يجب ألا تنكسر."""
        c = web.app.test_client()
        r = c.get("/landing?ref=ABC123&utm_source=fb")
        self.assertEqual(r.status_code, 301)
        self.assertTrue(r.headers["Location"].endswith("/?ref=ABC123&utm_source=fb"))
        with c.session_transaction() as s:
            self.assertEqual(s.get("ref"), "ABC123")

    def test_lang_query_switches_the_language(self):
        html = web.app.test_client().get("/?lang=en").get_data(as_text=True)
        self.assertIn('<html lang="en" dir="ltr">', html)

    def test_every_translation_key_exists_in_both_languages(self):
        missing = [k for k, v in i18n.T.items() if k.startswith(("lp2_", "pf_"))
                   and not (v.get("ar") and v.get("en"))]
        self.assertEqual(missing, [])

    def test_the_hero_is_a_one_tap_demo_with_a_real_qr(self):
        """البطل مسرح «ضغطة واحدة»: أنشطة تجريبية كاملة، وQR حقيقي (مربّع من 0/1)."""
        by = _by(web.app.test_client().get("/?lang=ar").get_data(as_text=True))
        self.assertGreaterEqual(len(by["hero"]), 3)
        for h in by["hero"]:
            self.assertTrue(h["name"] and h["label"] and h["q"] and h["a"] and h["kbd"])
            self.assertRegex(h["handle"], r"^[a-z][a-z0-9_]{3,28}bot$")   # يوزر تليجرام صالح
        rows = by["heroQr"]
        self.assertTrue(rows and all(len(r) == len(rows) and set(r) <= {"0", "1"} for r in rows))

    def test_faq_prices_are_filled_by_the_server(self):
        """لا عنصر نائب في الأسئلة: سعر رسالة التسويق وسعر ردّ «عقل البوت» من الخادم."""
        by = _by(web.app.test_client().get("/?lang=ar").get_data(as_text=True))
        self.assertEqual([x["q"] for x in by["faq"] if "{" in x["a"]], [])
        ai = f"{web.FE.ai_reply_price() / 100:g}"
        self.assertTrue(any(ai in x["a"] for x in by["faq"]))

    def test_plan_cards_show_the_limits_that_are_enforced(self):
        """أرقام وكيل الإعداد و«عقل البوت» في بطاقات الأسعار = الحدود المطبَّقة فعلاً."""
        by = _by(web.app.test_client().get("/?lang=en").get_data(as_text=True))
        cards = {p["id"]: " | ".join(p["features"]) for p in by["plans"]}
        for pid in ("free", "merchant", "whatsapp", "agency"):
            self.assertIn(f"AI setup agent ({web.plans.ai_setups_limit(pid):,}/month)", cards[pid])
            n = web.plans.ai_replies_limit(pid)
            self.assertEqual(n > 0, f"{n:,} AI replies" in cards[pid])
            self.assertEqual(web.plans.inbox_reply(pid), "manual replies" in cards[pid])
        # PLANS نفسها لم تتغيّر: السطور المولَّدة نسخ، لا إلحاق على القوائم الأصلية
        self.assertFalse(any("AI setup agent" in f for f in web.plans.PLANS["merchant"]["features_en"]))

    def test_every_landing_icon_ships_with_the_page(self):
        """كل أيقونة تطلبها بيانات الرئيسية موجودة في حمولة الصفحة — لا خانة فارغة."""
        by = _by(web.app.test_client().get("/?lang=ar").get_data(as_text=True))
        want = ({h["icon"] for h in by["hero"]} | {k["i"] for h in by["hero"] for k in h["kbd"]}
                | {k["i"] for d in by["demos"] for k in d["kbd"]} | {c["icon"] for c in by["bento"]}
                | {x["icon"] for x in by["trust"]} | {"refresh", "arrow", "user", "link", "check", "rocket"})
        self.assertEqual(sorted(want - set(by["icons"])), [])

    def test_the_landing_draws_icons_not_emoji(self):
        """الرموز في العروض والقصة من مجموعة المنصة المرسومة (icons.py)، لا إيموجي."""
        by = _by(web.app.test_client().get("/?lang=ar").get_data(as_text=True))
        emoji = re.compile("[\U0001F300-\U0001FAFF☀-➿]")
        texts = json.dumps([by["hero"], by["demos"], by["journey"], by["t"].get("lp2_foot_hi")],
                           ensure_ascii=False)
        self.assertIsNone(emoji.search(texts))
        self.assertNotIn("lp2_foot_made", by["t"])

    def test_every_icon_is_valid_svg_on_the_24_grid(self):
        import icons
        for name in icons._P:
            svg = ET.fromstring(str(icons.icon(name)))
            self.assertEqual(svg.get("viewBox"), "0 0 24 24", name)
            self.assertTrue(len(svg), name)


class SeoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _boot()

    def test_the_head_carries_complete_metadata(self):
        html = web.app.test_client().get("/?lang=ar").get_data(as_text=True)
        for needle in ("<title>", 'name="description"', 'rel="canonical" href="https://botyalla.test/"',
                       'hreflang="ar"', 'hreflang="en"', 'hreflang="x-default"',
                       # بإصدار ?v= من تاريخ الملف: /static/ يُخزَّن immutable ثلاثين يوماً
                       'property="og:image" content="https://botyalla.test/static/brand/og-ar.png?v=',
                       'name="twitter:card" content="summary_large_image"', 'rel="manifest"'):
            self.assertIn(needle, html, needle)

    def test_absolute_links_never_come_from_the_host_header(self):
        html = web.app.test_client().get("/", headers={"X-Forwarded-Host": "evil.example"}).get_data(as_text=True)
        self.assertNotIn("evil.example", html)

    def test_structured_data_is_valid_and_matches_the_server(self):
        html = web.app.test_client().get("/?lang=ar").get_data(as_text=True)
        ld = _jsonld(html)
        self.assertIsNotNone(ld, "لا بيانات منظّمة")
        types = {n["@type"] for n in ld["@graph"]}
        self.assertTrue({"Organization", "WebSite", "SoftwareApplication", "FAQPage"} <= types)
        app_node = next(n for n in ld["@graph"] if n["@type"] == "SoftwareApplication")
        with web.app.test_request_context():
            server = {web.plans.plan_name(p["id"], "ar"): f"{float(p['price']):.2f}"
                      for p in web.priced_plans("ar")}
        self.assertEqual({o["name"]: o["price"] for o in app_node["offers"]}, server)
        faq = next(n for n in ld["@graph"] if n["@type"] == "FAQPage")
        self.assertEqual(len(faq["mainEntity"]), len(i18n.LANDING2["faq"]))
        self.assertNotIn("{price}", json.dumps(faq, ensure_ascii=False), "سعر غير مملوء في الأسئلة")

    def test_every_script_on_public_pages_carries_the_nonce(self):
        c = web.app.test_client()
        for path in ("/", "/terms", "/privacy", "/refund", "/acceptable-use", "/no-such-page"):
            r = c.get(path)
            nonce = re.search(r"'nonce-([\w\-]+)'", r.headers["Content-Security-Policy"]).group(1)
            tags = re.findall(r"<script\b[^>]*>", r.get_data(as_text=True))
            self.assertTrue(tags, path)
            self.assertEqual([t for t in tags if f'nonce="{nonce}"' not in t], [], path)

    def test_robots_and_sitemap(self):
        c = web.app.test_client()
        robots = c.get("/robots.txt").get_data(as_text=True)
        for p in ("Disallow: /dashboard", "Disallow: /admin", "Disallow: /api/",
                  "Sitemap: https://botyalla.test/sitemap.xml"):
            self.assertIn(p, robots)
        r = c.get("/sitemap.xml")
        self.assertEqual(r.mimetype, "application/xml")
        ns = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
        locs = [e.text for e in ET.fromstring(r.data).findall("s:url/s:loc", ns)]
        for path in ("/", "/terms", "/privacy", "/refund", "/acceptable-use", "/register"):
            self.assertIn("https://botyalla.test" + path, locs)
        self.assertFalse(any("/dashboard" in u or "/admin" in u for u in locs))

    def test_manifest_and_security_txt(self):
        c = web.app.test_client()
        m = json.loads(c.get("/site.webmanifest").data)
        self.assertEqual(m["name"], "BotYalla")
        self.assertTrue(any(i["sizes"] == "512x512" for i in m["icons"]))
        sec = c.get("/.well-known/security.txt").get_data(as_text=True)
        self.assertIn("Contact: mailto:", sec)
        self.assertIn("Expires: ", sec)

    def test_brand_images_exist_with_the_right_sizes(self):
        want = {"og-ar.png": (1200, 630), "og-en.png": (1200, 630), "icon-512.png": (512, 512),
                "icon-192.png": (192, 192), "apple-touch-icon.png": (180, 180), "favicon-32.png": (32, 32)}
        for name, size in want.items():
            with open(os.path.join(ROOT, "static", "brand", name), "rb") as f:
                head = f.read(24)
            self.assertEqual(head[:8], b"\x89PNG\r\n\x1a\n", name)
            self.assertEqual(struct.unpack(">II", head[16:24]), size, name)
        self.assertEqual(web.app.test_client().get("/favicon.ico").mimetype, "image/png")


class LegalAndNotFoundTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _boot()

    def test_every_policy_renders_server_side_in_both_languages(self):
        for doc, path in LEGAL_PATHS.items():
            for lang in ("ar", "en"):
                html = web.app.test_client().get(f"{path}?lang={lang}").get_data(as_text=True)
                self.assertIn(LEGAL.title(doc, lang), html, (doc, lang))
                first = LEGAL.render(doc, lang)["sections"][0]["h"]
                served = html[html.index('id="fallback"'):]       # ما يقرؤه الزائر ومحرك البحث
                self.assertIn(first, served, (doc, lang))
                # الوثيقة نفسها (المرسومة ونسخة React) بلا أي عنصر نائب غير مملوء.
                # (قوالب نصوص الواجهة في BY.t تحمل {email} عمداً وتملؤها الواجهة.)
                legal_json = json.dumps(_by(html)["legal"], ensure_ascii=False)
                for ph in ("{email}", "{whatsapp}", "{updated}", "{site}"):
                    self.assertNotIn(ph, served, (doc, lang, ph))
                    self.assertNotIn(ph, legal_json, (doc, lang, ph))

    def test_policies_use_the_public_layout_not_the_dashboard_shell(self):
        html = web.app.test_client().get("/privacy").get_data(as_text=True)
        self.assertIn("dist/landing-", html)
        self.assertNotIn("dist/console-", html)
        self.assertEqual(_by(html)["page"], "legal")

    def test_every_policy_is_linked_from_every_public_page(self):
        by = _by(web.app.test_client().get("/").get_data(as_text=True))
        self.assertEqual([d["url"] for d in by["legalDocs"]], list(LEGAL_PATHS.values()))

    def test_an_unknown_page_is_a_branded_noindex_404(self):
        r = web.app.test_client().get("/no-such-page")
        self.assertEqual(r.status_code, 404)
        html = r.get_data(as_text=True)
        self.assertIn('content="noindex,follow"', html)
        self.assertEqual(_by(html)["page"], "notfound")

    def test_api_404s_stay_plain(self):
        r = web.app.test_client().get("/api/no-such-endpoint")
        self.assertEqual(r.status_code, 404)
        self.assertNotIn("window.BY", r.get_data(as_text=True))


if __name__ == "__main__":
    unittest.main(verbosity=2)
