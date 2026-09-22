"""متجر تليجرام: الشحن مسار ثابت · صور المنتجات تصل فعلاً · وإضافة «منتجاتي من تليجرام».

القواعد المختبَرة: إعداد شحن فاسد يسقط إلى «بلا شحن» · الشحن يُسأل مرة ويُجمع على
الإجمالي ويُحفظ مع الطلب · صورة المنتج من مكتبة الوسائط (لا الرابط وحده) · كونسول
المنتجات لصاحب البوت وحده وبإضافة سارية · الكود المجاني يفعّل شهراً ولا يُستعمل مرتين ·
سعر الإضافة من الخادم وتفعيلها بموافقة الأدمن.

    python tests/test_store_catalog.py
"""
import asyncio, io, json, os, secrets, sys, tempfile, time, unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_TMP = tempfile.mkdtemp(prefix="botyalla-cat-")
os.environ["BOTYALLA_DB"] = os.path.join(_TMP, "t.db")        # قبل أي استيراد
os.environ["BOTYALLA_UPLOADS"] = _TMP
os.environ["BOTYALLA_LOGS"] = _TMP
os.environ["BOTYALLA_OCR"] = "0"
os.environ["PUBLIC_URL"] = "https://botyalla.test"
PW = "st_" + secrets.token_hex(6)
os.environ["ADMIN_USER"] = "admin"
os.environ["ADMIN_PASS"] = PW

from telegram.ext import ApplicationHandlerStop, CommandHandler, ConversationHandler  # noqa: E402

import asset_store                          # noqa: E402
import auth                                 # noqa: E402
import catalog_bot as CB                    # noqa: E402
import database as db                       # noqa: E402
import flow_engine as FE                    # noqa: E402
import templates_bot as T                   # noqa: E402
import app as web                           # noqa: E402

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 8192
CSRF = "tk"


def _boot():
    db.init_db()
    web.seed_platform_defaults()
    web.contact_defaults()
    web.seed_default_admin()
    web.seed_catalog_promo()
    web.app.config["TESTING"] = True
    web.notify_admins = lambda *a, **k: None
    web.manager.is_running = lambda bid: False
    web.manager.restart_bot = lambda bid: (True, "ok")


def _as(name):
    c = web.app.test_client()
    with c.session_transaction() as s:
        s["_csrf"] = CSRF
    c.post("/login", data={"username": name, "password": PW, "csrf_token": CSRF})
    return c


# --------------------------------------------------------------- تليجرام مزيّف
class FakeMsg:
    def __init__(self, text="", photo=None, caption=None):
        self.text, self.caption = text, caption
        self.photo = photo or []
        self.sent = []

    async def reply_text(self, text, **kw):
        self.sent.append(text)
        return self

    async def reply_photo(self, photo, **kw):
        self.sent.append(("photo", kw.get("caption")))
        return self


class FakePhoto:
    file_id = "ph1"


class FakeFile:
    def __init__(self, data): self._d = data
    async def download_as_bytearray(self): return bytearray(self._d)


class FakeBot:
    def __init__(self, data=PNG):
        self.sent = []
        self._data = data

    async def send_photo(self, chat_id=None, photo=None, caption=None, reply_markup=None, **kw):
        self.sent.append(("photo", caption))
        return type("M", (), {"photo": [type("P", (), {"file_id": "fid"})()], "video": None})()

    async def send_message(self, chat_id=None, text=None, reply_markup=None, **kw):
        self.sent.append(("text", text))
        return object()

    async def get_file(self, file_id):
        return FakeFile(self._data)


class FakeUpdate:
    def __init__(self, chat=777, msg=None, cb=None):
        self.message = self.effective_message = msg or FakeMsg()
        self.effective_chat = type("C", (), {"id": chat})()
        self.effective_user = type("U", (), {"id": chat, "first_name": "زبون"})()
        self.callback_query = cb


class FakeApp:
    """يجمع الهاندلرز بدل تشغيل تليجرام — الاختبار يستدعي دوالها مباشرة."""
    def __init__(self, bot_id, cfg, bot=None):
        self.bot_data = {"bot_id": bot_id, "config": cfg}
        self.handlers = []
        self.bot = bot

    def add_handler(self, h, group=0):
        self.handlers.append((group, h))


class FakeCtx:
    def __init__(self, app, bot):
        self.application, self.bot = app, bot
        self.user_data, self.args = {}, []


def run(cb, up, ctx):
    """ينفّذ هاندلر ويبتلع ApplicationHandlerStop (هي إشارة توقف لا خطأ)."""
    async def go():
        try:
            return await cb(up, ctx)
        except ApplicationHandlerStop:
            return "STOP"
    return asyncio.run(go())


def store_app(bot_id, cfg, bot=None):
    bot = bot or FakeBot()
    app = FakeApp(bot_id, cfg, bot)
    T.build_store(app)
    conv = next(h for _g, h in app.handlers if isinstance(h, ConversationHandler))
    return app, FakeCtx(app, bot), conv


def cmd(app, name):
    for _g, h in app.handlers:
        if isinstance(h, CommandHandler) and name in h.commands:
            return h.callback
    raise AssertionError(name)


# --------------------------------------------------------------- حساب الشحن
class ShippingMathTests(unittest.TestCase):
    def test_a_broken_setting_means_no_shipping_not_an_invented_price(self):
        for bad in (None, "x", {"mode": "zones", "zones": []}, {"mode": "weird", "cost": 50}):
            self.assertEqual(T.ship_conf({"shipping": bad})["mode"], "none", bad)
        sh = T.ship_conf({"shipping": {"mode": "flat", "cost": "abc", "free_over": -5}})
        self.assertEqual((sh["cost"], sh["free_over"]), (0.0, 0.0))

    def test_flat_zones_and_free_over(self):
        flat = T.ship_conf({"shipping": {"mode": "flat", "cost": 70, "free_over": 1000}})
        self.assertEqual(T.ship_cost(flat, None, 300), 70)
        self.assertEqual(T.ship_cost(flat, None, 1000), 0, "مجاني فوق الحد")
        zones = T.ship_conf({"shipping": {"mode": "zones", "zones": [
            {"name": "القاهرة", "cost": 60}, {"name": "الصعيد", "cost": 90}]}})
        self.assertEqual(T.ship_cost(zones, "الصعيد", 100), 90)
        self.assertEqual(T.ship_cost(zones, "منطقة مجهولة", 100), 60, "المجهولة تأخذ أول سعر لا صفراً")
        self.assertEqual(T.match_zone(zones, "القاهرة — 60 ج"), "القاهرة")
        self.assertEqual(T.match_zone(zones, "مدينة نصر، القاهرة"), "القاهرة")
        self.assertIsNone(T.match_zone(zones, "الإسكندرية"))

    def test_the_summary_adds_shipping_once(self):
        sh = T.ship_conf({"shipping": {"mode": "flat", "cost": 70}})
        text, sub, cost, total = T.order_summary(
            [{"name": "فستان", "price": 250, "qty": 2}], sh)
        self.assertEqual((sub, cost, total), (500, 70, 570))
        self.assertIn("🚚", text)
        self.assertIn("570", text)


# --------------------------------------------------------------- مسار المتجر
class StoreFlowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _boot()
        cls.u = db.create_user("st_owner", auth.hash_password(PW))
        cls.asset = asset_store.save(cls.u, PNG, "فستان")["id"]
        cls.cfg = {"business_name": "متجر النور", "owner_chat_id": "999",
                   "products": [{"name": "فستان", "price": 250, "asset": cls.asset}],
                   "shipping": {"mode": "zones", "cost": 0,
                                "zones": [{"name": "القاهرة", "cost": 60},
                                          {"name": "الصعيد", "cost": 90}]}}
        cls.bid = db.create_bot(cls.u, "النور", "T:st-1", "store", cls.cfg)

    def _order(self, zone_reply="الصعيد — 90 ج"):
        app, ctx, conv = store_app(self.bid, self.cfg)
        start = conv.entry_points[0].callback
        step = lambda st, text: run(conv.states[st][0].callback, FakeUpdate(msg=FakeMsg(text)), ctx)
        run(start, FakeUpdate(msg=FakeMsg("/start")), ctx)
        step(T.ST_MENU, "1. فستان - 250 ج")
        step(T.ST_QTY, "2")
        step(T.ST_MENU, "🛒 إنهاء الطلب")
        step(T.ST_NAME, "منى")
        step(T.ST_PHONE, "01000000000")
        nxt = step(T.ST_ADDR, "٥ شارع النيل")
        if nxt == T.ST_SHIP:
            nxt = step(T.ST_SHIP, zone_reply)
        step(T.ST_CONFIRM, "تأكيد")
        return app, ctx, db.list_orders(self.bid)[0]

    def test_the_customer_sees_the_product_photo_from_the_media_library(self):
        """الخلل الذي كان: القالب يقرأ `image` (رابط) وحده، فصورة المنتج المختارة من
        المكتبة لا تصل العميل إطلاقاً."""
        bot = FakeBot()
        app, ctx, conv = store_app(self.bid, self.cfg, bot)
        run(conv.entry_points[0].callback, FakeUpdate(msg=FakeMsg("/start")), ctx)
        run(conv.states[T.ST_MENU][0].callback, FakeUpdate(msg=FakeMsg("1. فستان - 250 ج")), ctx)
        photos = [c for k, c in bot.sent if k == "photo"]
        self.assertTrue(photos, "الصورة وصلت")
        self.assertIn("250", photos[0], "ومعها السعر في نفس البطاقة")

    def test_shipping_is_asked_once_and_stored_with_the_order(self):
        _app, _ctx, o = self._order()
        self.assertEqual(o["ship_zone"], "الصعيد")
        self.assertEqual(o["shipping"], 90)
        self.assertEqual(o["total"], 590, "الإجمالي = المنتجات + الشحن")
        self.assertEqual([i["name"] for i in o["items"]], ["فستان"], "الشحن ليس منتجاً في السلة")

    def test_the_owner_notification_shows_the_shipping_line(self):
        sent = []

        async def fake_notify(row, ch, text):
            sent.append(text)
        orig, FE.notify_owner = FE.notify_owner, fake_notify
        T.notify_owner = fake_notify
        try:
            self._order()
        finally:
            FE.notify_owner = orig
            T.notify_owner = orig
        self.assertTrue(sent and "🚚" in sent[0], sent)
        self.assertIn("590", sent[0])

    def test_a_known_zone_inside_the_address_skips_the_question(self):
        app, ctx, conv = store_app(self.bid, self.cfg)
        step = lambda st, text: run(conv.states[st][0].callback, FakeUpdate(msg=FakeMsg(text)), ctx)
        run(conv.entry_points[0].callback, FakeUpdate(msg=FakeMsg("/start")), ctx)
        step(T.ST_MENU, "1. فستان - 250 ج")
        step(T.ST_QTY, "1")
        step(T.ST_MENU, "🛒 إنهاء الطلب")
        step(T.ST_NAME, "منى")
        step(T.ST_PHONE, "01000000000")
        self.assertEqual(step(T.ST_ADDR, "مدينة نصر، القاهرة"), T.ST_CONFIRM)

    def test_an_ai_order_carries_the_shipping_too(self):
        sent = []

        class Ch:
            async def send_text(self, peer, text): sent.append(text)
        row = dict(db.get_bot(self.bid))
        asyncio.run(FE._ai_action(row, self.cfg, Ch(), "tg:555",
                                  {"type": "order", "items": [{"name": "فستان", "qty": 1}],
                                   "customer": "سارة", "phone": "0100", "address": "أسيوط، الصعيد"}))
        o = db.list_orders(self.bid)[0]
        self.assertEqual((o["ship_zone"], o["shipping"], o["total"]), ("الصعيد", 90, 340))


# --------------------------------------------------------------- كونسول المنتجات
class CatalogConsoleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _boot()
        cls.u = db.create_user("cat_owner", auth.hash_password(PW))
        db.activate_subscription(cls.u, "merchant", days=30)
        cls.cfg = {"business_name": "كوكي", "owner_chat_id": "999", "products": []}
        cls.bid = db.create_bot(cls.u, "كوكي", "T:cat-1", "store", cls.cfg)

    def setUp(self):
        db.update_bot_config(self.bid, dict(self.cfg, products=[]))
        with db.get_conn() as c:
            c.execute("DELETE FROM bot_addons WHERE bot_id=?", (self.bid,))

    def _console(self, uid=999, bot=None):
        app, ctx, _conv = store_app(self.bid, dict(self.cfg), bot)
        up = FakeUpdate(chat=uid)
        return app, ctx, up

    def test_parsing_what_the_owner_types(self):
        self.assertEqual(CB.parse_product("فستان صيفي 250"), ("فستان صيفي", 250))
        self.assertEqual(CB.parse_product("فستان - 250 ج"), ("فستان", 250))
        self.assertEqual(CB.parse_product("مقاس 38 حذاء 199.5"), ("مقاس 38 حذاء", 199.5))
        self.assertEqual(CB.parse_product("شنطة ٣٠٠"), ("شنطة", 300), "أرقام عربية")
        self.assertEqual(CB.parse_product("بلوزة"), ("بلوزة", None), "بلا رقم: يسأل لا يخترع")

    def test_only_the_owner_with_an_active_addon_gets_in(self):
        app, ctx, up = self._console(uid=555)                  # عميل عادي
        run(cmd(app, "products"), up, ctx)
        self.assertIn("لصاحب المتجر", up.message.sent[-1])
        app, ctx, up = self._console()                          # صاحب المتجر بلا إضافة
        run(cmd(app, "products"), up, ctx)
        self.assertIn("/bot/", up.message.sent[-1], "يعرض رابط التفعيل")
        self.assertNotIn("cat", ctx.user_data)
        db.extend_addon(self.bid, "catalog", days=30)
        app, ctx, up = self._console()
        run(cmd(app, "products"), up, ctx)
        self.assertIn("cat", ctx.user_data)

    def test_a_photo_with_its_name_and_price_becomes_a_product(self):
        db.extend_addon(self.bid, "catalog", days=30)
        bot = FakeBot()
        app, ctx, up = self._console(bot=bot)
        run(cmd(app, "products"), up, ctx)
        on_msg = next(h.callback for g, h in app.handlers
                      if g == CB.GROUP and not isinstance(h, CommandHandler)
                      and hasattr(h, "filters"))
        photo_up = FakeUpdate(chat=999, msg=FakeMsg(photo=[FakePhoto()], caption="فستان صيفي 250"))
        run(on_msg, photo_up, ctx)
        prods = json.loads(db.get_bot(self.bid)["config_json"])["products"]
        self.assertEqual(len(prods), 1)
        self.assertEqual((prods[0]["name"], prods[0]["price"]), ("فستان صيفي", 250))
        self.assertTrue(prods[0].get("asset"), "الصورة اتحفظت في مكتبة الوسائط")
        self.assertIsNotNone(db.get_asset(prods[0]["asset"], owner_id=self.u))
        self.assertEqual(ctx.application.bot_data["config"]["products"], prods,
                         "البوت الشغّال يشوف المنتج فوراً")

    def test_a_photo_alone_gets_asked_for_name_then_price(self):
        db.extend_addon(self.bid, "catalog", days=30)
        app, ctx, up = self._console()
        run(cmd(app, "products"), up, ctx)
        on_msg = next(h.callback for g, h in app.handlers
                      if g == CB.GROUP and not isinstance(h, CommandHandler) and hasattr(h, "filters"))
        run(on_msg, FakeUpdate(chat=999, msg=FakeMsg(photo=[FakePhoto()])), ctx)
        self.assertEqual(ctx.user_data["cat"]["step"], "ask_name")
        run(on_msg, FakeUpdate(chat=999, msg=FakeMsg("شنطة جلد")), ctx)
        self.assertEqual(ctx.user_data["cat"]["step"], "ask_price")
        run(on_msg, FakeUpdate(chat=999, msg=FakeMsg("٤٥٠")), ctx)
        prods = json.loads(db.get_bot(self.bid)["config_json"])["products"]
        self.assertEqual((prods[0]["name"], prods[0]["price"]), ("شنطة جلد", 450))

    def test_a_customer_message_is_never_swallowed_by_the_console(self):
        db.extend_addon(self.bid, "catalog", days=30)
        app, ctx, _up = self._console()
        on_msg = next(h.callback for g, h in app.handlers
                      if g == CB.GROUP and not isinstance(h, CommandHandler) and hasattr(h, "filters"))
        out = run(on_msg, FakeUpdate(chat=555, msg=FakeMsg("عايز أشتري")), ctx)
        self.assertIsNone(out, "تكمل لمحادثة الشراء")

    def test_price_edit_and_delete(self):
        db.extend_addon(self.bid, "catalog", days=30)
        db.update_bot_config(self.bid, dict(self.cfg, products=[{"name": "فستان", "price": 250}]))
        app, ctx, up = self._console()
        run(cmd(app, "products"), up, ctx)
        cb_handler = next(h.callback for g, h in app.handlers
                          if g == CB.GROUP and hasattr(h, "pattern"))
        on_msg = next(h.callback for g, h in app.handlers
                      if g == CB.GROUP and not isinstance(h, CommandHandler) and hasattr(h, "filters"))

        class CB_:
            def __init__(self, data):
                self.data, self.from_user = data, type("U", (), {"id": 999})()
                self.message = FakeMsg()
            async def answer(self, *a, **k): pass
        q = CB_("cat:price:0")
        run(cb_handler, FakeUpdate(chat=999, cb=q), ctx)
        run(on_msg, FakeUpdate(chat=999, msg=FakeMsg("300")), ctx)
        self.assertEqual(json.loads(db.get_bot(self.bid)["config_json"])["products"][0]["price"], 300)
        run(cb_handler, FakeUpdate(chat=999, cb=CB_("cat:delok:0")), ctx)
        self.assertEqual(json.loads(db.get_bot(self.bid)["config_json"])["products"], [])


# --------------------------------------------------------------- الشراء والكوبون
class AddonCatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _boot()
        cls.u = db.create_user("cat_buyer", auth.hash_password(PW))
        db.activate_subscription(cls.u, "merchant", days=30)
        cls.bid = db.create_bot(cls.u, "متجر", "T:cat-buy", "store", {"business_name": "متجر"})
        cls.flow = db.create_bot(cls.u, "فلو", "T:cat-flow", "flow", {})

    def setUp(self):
        web._login_attempts.clear()
        web._rate_hits.clear() if hasattr(web, "_rate_hits") else None
        with db.get_conn() as c:
            c.execute("DELETE FROM bot_addons WHERE bot_id=?", (self.bid,))

    def _pay(self, c, **form):
        data = {"method": "vodafone", "ref": "1", "csrf_token": CSRF,
                "screenshot": (io.BytesIO(PNG + os.urandom(16)), "r.png"), **form}
        return c.post(f"/bot/{self.bid}/addon/catalog", data=data, content_type="multipart/form-data")

    def test_the_price_comes_from_the_server_and_approval_activates_30_days(self):
        self._pay(_as("cat_buyer"), amount="1")
        p = [x for x in db.list_payments(self.u)
             if x["plan"] == db.addon_plan(self.bid, "catalog")][0]
        self.assertEqual(float(p["amount"]), float(web.addon_price("catalog")))
        self.assertFalse(db.addon_active(self.bid, "catalog"), "لا تفعيل قبل موافقة الأدمن")
        self.assertFalse(db.addon_active(self.bid, "pay"), "إضافة لا تفتح إضافة أخرى")
        db.finalize_payment(p["id"], "approved")
        self.assertTrue(db.addon_active(self.bid, "catalog"))
        self.assertAlmostEqual(db.addon_expires(self.bid, "catalog") - time.time(), 30 * 86400, delta=120)
        self.assertIn(db.addon_plan(self.bid, "catalog"), web._plan_names("ar"))

    def test_the_free_coupon_activates_a_month_once_per_user(self):
        c = _as("cat_buyer")
        r = c.post(f"/bot/{self.bid}/addon/catalog",
                   data={"promo": web.CATALOG_PROMO, "csrf_token": CSRF})
        self.assertEqual(r.status_code, 302)
        self.assertTrue(db.addon_active(self.bid, "catalog"), "اتفعّلت بالكود بلا دفعة")
        self.assertEqual([x for x in db.list_payments(self.u)
                          if x["plan"] == db.addon_plan(self.bid, "catalog")], [])
        with db.get_conn() as conn:
            conn.execute("DELETE FROM bot_addons WHERE bot_id=?", (self.bid,))
        c.post(f"/bot/{self.bid}/addon/catalog", data={"promo": web.CATALOG_PROMO, "csrf_token": CSRF})
        self.assertFalse(db.addon_active(self.bid, "catalog"), "الكود لا يُستعمل مرتين لنفس الشخص")

    def test_codes_that_must_not_open_the_addon(self):
        db.create_promo("HALFOFF", "percent", 50, plan="addon_catalog")
        db.create_promo("PLANCODE", "fixed", 999, plan="merchant")
        c = _as("cat_buyer")
        for code in ("HALFOFF", "PLANCODE", "NOPE"):
            c.post(f"/bot/{self.bid}/addon/catalog", data={"promo": code, "csrf_token": CSRF})
            self.assertFalse(db.addon_active(self.bid, "catalog"), code)

    def test_only_telegram_store_bots(self):
        c = _as("cat_buyer")
        r = c.post(f"/bot/{self.flow}/addon/catalog",
                   data={"promo": web.CATALOG_PROMO, "csrf_token": CSRF})
        self.assertEqual(r.status_code, 302)
        self.assertFalse(db.addon_active(self.flow, "catalog"))

    def test_another_owner_cannot_buy_for_your_bot(self):
        other = db.create_user("cat_other", auth.hash_password(PW))
        db.activate_subscription(other, "merchant", days=30)
        r = _as("cat_other").post(f"/bot/{self.bid}/addon/catalog",
                                  data={"promo": web.CATALOG_PROMO, "csrf_token": CSRF})
        self.assertEqual(r.status_code, 404)
        self.assertFalse(db.addon_active(self.bid, "catalog"))


# --------------------------------------------------------------- حفظ الإعدادات
class ConfigFormTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _boot()
        cls.u = db.create_user("cfg_owner", auth.hash_password(PW))
        cls.bid = db.create_bot(cls.u, "متجر", "T:cfg-1", "store", {"business_name": "متجر"})

    def _save(self, **extra):
        data = {"csrf_token": CSRF, "business_name": "متجر", "owner_chat_id": "",
                "welcome": "", "thanks": "", "welcome_image": "",
                "p_name": "فستان", "p_price": "250", "p_image": "", "p_asset": "",
                "p_desc": "قطن ١٠٠٪", **extra}
        _as("cfg_owner").post(f"/bot/{self.bid}/config", data=data)
        return json.loads(db.get_bot(self.bid)["config_json"])

    def test_zones_and_description_are_saved_as_the_bot_reads_them(self):
        cfg = self._save(ship_mode="zones", z_name=["القاهرة", ""], z_cost=["60", "10"],
                         ship_free_over="1000", ship_note="خلال يومين")
        self.assertEqual(cfg["products"][0]["desc"], "قطن ١٠٠٪")
        self.assertEqual(cfg["shipping"]["mode"], "zones")
        self.assertEqual(cfg["shipping"]["zones"], [{"name": "القاهرة", "cost": 60.0}])
        self.assertEqual(cfg["shipping"]["free_over"], 1000.0)
        self.assertEqual(T.ship_cost(T.ship_conf(cfg), "القاهرة", 200), 60)

    def test_zones_mode_without_zones_falls_back_to_no_shipping(self):
        cfg = self._save(ship_mode="zones", z_name="", z_cost="")
        self.assertEqual(cfg["shipping"]["mode"], "none")


if __name__ == "__main__":
    unittest.main(verbosity=2)
