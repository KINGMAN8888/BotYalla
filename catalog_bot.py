"""كتالوج صاحب المتجر من داخل تليجرام — إضافة مدفوعة لكل بوت (`bot_addons.addon='catalog'`).

**لماذا:** أصحاب متاجر كثيرون لا يفتحون لوحة تحكم أصلاً. هنا يضيف صاحب المتجر منتجه
بصورة واحدة مكتوب تحتها الاسم والسعر («فستان صيفي 250»)، ويحذف ويعدّل السعر بضغطة —
من نفس البوت الذي يبيع به.

**الحدود — لا تتوسّع بلا قرار صريح من المالك:**
· **صاحب البوت وحده** (`config.owner_chat_id`) — لا عميل ولا من يعرف الأمر.
· **الإضافة سارية** (`db.addon_active(bot_id, "catalog")`) — وحساب الإدارة مفتوح له.
· **المنتجات فقط.** هذا الملف يكتب في `config["products"]` ولا شيء غيره: لا توكن ولا
  حسابات استلام ولا تشغيل/إيقاف ولا حذف. أي توسعة تُناقش قبل أن تُكتب.
· **الصورة تمرّ بمكتبة الوسائط** (`asset_store`): النوع من البايتات وحصة الباقة تُفحص
  قبل الكتابة على القرص — نفس مسار الرفع من اللوحة، لا مسار جانبي.

المحادثة كلها في `user_data["cat"]`، والحارس في المجموعة `-2` (قبل حارس الوارد وقبل
محادثة المتجر) ويوقف السلسلة بـ `ApplicationHandlerStop` لما يستهلك رسالة — فلا تفهمها
محادثة الشراء على أنها اسم عميل أو كمية.
"""
import json
import logging
import os
import re

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (ApplicationHandlerStop, CallbackQueryHandler, CommandHandler,
                          MessageHandler, filters)

import asset_store
import database as db

log = logging.getLogger("catalog_bot")

GROUP = -2                     # قبل حارس الوارد (-1) ومحادثة المتجر (0)
MAX_PRODUCTS = 60              # سقف الكتالوج من البوت — اللوحة تبقى للقوائم الطويلة
LIST_ROWS = 12                 # أزرار المنتجات المعروضة في الشاشة الواحدة
NAME_MAX, DESC_MAX = 80, 400

# أرقام عربية/فارسية → لاتينية قبل أي قراءة سعر
_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")
_PRICE_RE = re.compile(r"(?<![\d.,])(\d{1,7}(?:[.,]\d{1,2})?)\s*(?:ج\.?م?|جنيه|egp|le)?(?![\d.,])",
                       re.I)
_SEP = " \t-—–|،,:.؛ب"


def parse_product(text):
    """«فستان صيفي 250» · «فستان - 250 ج» · «فستان\\n250» → (الاسم، السعر).

    السعر هو **آخر** رقم في النص: اسم فيه رقم («مقاس 38») يبقى اسماً. بلا رقم
    يرجّع السعر None — والبوت يسأل عنه بدل أن يخترعه."""
    t = re.sub(r"\s+", " ", str(text or "").translate(_DIGITS).strip())
    if not t:
        return "", None
    last = None
    for last in _PRICE_RE.finditer(t):
        pass
    if not last:
        return t[:NAME_MAX], None
    name = (t[:last.start()] + " " + t[last.end():]).strip(_SEP)
    try:
        price = round(float(last.group(1).replace(",", ".")), 2)
    except ValueError:
        return t[:NAME_MAX], None
    return name[:NAME_MAX], max(0.0, price)


def parse_price(text):
    """سعر وحده من رسالة. None = ليس رقماً."""
    _name, price = parse_product(text)
    if price is None:
        return None
    return price


def catalog_text(products, biz=""):
    """شاشة الكتالوج: كل منتج برقمه وسعره وعلامة الصورة."""
    head = f"🗂️ منتجات «{biz}»" if biz else "🗂️ منتجاتك"
    if not products:
        return head + "\n\nلسه مفيش منتجات. اضغط «➕ منتج جديد» وابعت صورته."
    lines = []
    for i, p in enumerate(products[:LIST_ROWS], start=1):
        pic = "🖼️" if (p.get("asset") or p.get("image")) else "▫️"
        try:
            price = f"{float(p.get('price') or 0):g}"
        except (TypeError, ValueError):
            price = "0"
        lines.append(f"{pic} {i}. {p.get('name', '')} — {price} ج")
    more = len(products) - LIST_ROWS
    tail = f"\n… و{more} منتج آخر (عدّلها من الموقع)" if more > 0 else ""
    return head + f" ({len(products)})\n\n" + "\n".join(lines) + tail


def catalog_kb(products):
    rows = [[InlineKeyboardButton("➕ منتج جديد", callback_data="cat:new")]]
    for i, p in enumerate(products[:LIST_ROWS]):
        name = str(p.get("name", ""))[:18]
        rows.append([InlineKeyboardButton(f"💵 سعر {name}", callback_data=f"cat:price:{i}"),
                     InlineKeyboardButton("🗑", callback_data=f"cat:del:{i}")])
    rows.append([InlineKeyboardButton("✅ خلاص", callback_data="cat:close")])
    return InlineKeyboardMarkup(rows)


ADD_HELP = ("📸 ابعت «صورة المنتج» ومكتوب تحتها الاسم والسعر في نفس الرسالة، مثال:\n"
            "«فستان صيفي 250»\n\n"
            "• لو ابعت الصورة لوحدها هسألك على الاسم والسعر.\n"
            "• ولو مفيش صورة، اكتب الاسم والسعر بس.")


# ------------------------------------------------------------------ الصلاحية
def _cfg_of(bot_row):
    try:
        return json.loads(bot_row["config_json"] or "{}")
    except (TypeError, ValueError):
        return {}


def access(bot_id, user_id):
    """None = مسموح. وإلا سبب المنع: not_owner | inactive."""
    row = db.get_bot(bot_id)
    if not row:
        return "not_owner"
    owner_chat = str(_cfg_of(row).get("owner_chat_id") or "").strip()
    if not owner_chat or str(user_id) != owner_chat:
        return "not_owner"
    if not db.addon_active(bot_id, "catalog"):
        return "inactive"
    return None


def buy_link(bot_id):
    """رابط تفعيل الإضافة — من PUBLIC_URL وحدها (AGENTS.md §3.14)، وبدونها بلا رابط."""
    base = os.getenv("PUBLIC_URL", "").strip().rstrip("/")
    return f"{base}/bot/{bot_id}/addon/catalog" if base else ""


def _offer(bot_id):
    link = buy_link(bot_id)
    return ("🗂️ «منتجاتي من تليجرام» إضافة منفصلة: تضيف وتعدّل منتجاتك من هنا بصورة "
            "ورسالة واحدة، بلا ما تفتح الموقع.\n\nفعّلها من لوحة التحكم"
            + (f":\n{link}" if link else " ← صفحة البوت ← «منتجاتي من تليجرام»."))


# ------------------------------------------------------------------ الكتابة
def _products(bot_id):
    row = db.get_bot(bot_id)
    prods = _cfg_of(row).get("products") if row else []
    return list(prods) if isinstance(prods, list) else []


def save_products(ctx, bot_id, products):
    """المصدر هو القاعدة لا ذاكرة البوت: نقرأ الإعدادات، نكتب المنتجات وحدها، ثم
    نحدّث نسخة البوت الشغّال فيرى التعديل فوراً بلا إعادة تشغيل."""
    row = db.get_bot(bot_id)
    if not row:
        return False
    cfg = _cfg_of(row)
    cfg["products"] = products[:MAX_PRODUCTS]
    db.update_bot_config(bot_id, cfg)
    try:
        ctx.application.bot_data["config"] = cfg
    except Exception:                       # سياق اختبار بلا application كامل
        log.debug("could not refresh the running config for bot #%s", bot_id)
    return True


def save_photo(bot_row, data, name=""):
    """يحفظ صورة المنتج في مكتبة صاحب البوت. يرجّع (asset_id، سبب الرفض)."""
    owner_id = bot_row["owner_id"]
    user = db.get_user(owner_id) or {}
    sub = db.get_subscription(owner_id) or {}
    plan_id = sub.get("plan") if sub.get("status") == "active" else "free"
    if not asset_store.quota_ok(owner_id, user.get("role"), plan_id, len(data)):
        return None, "quota"
    res = asset_store.save(owner_id, data, name=(name or "منتج")[:60])
    return (res.get("id"), None) if res.get("ok") else (None, res.get("reason"))


_REFUSE = {"quota": "مساحة مكتبة الوسائط خلصت — امسح صوراً قديمة أو رقّي باقتك.",
           "too_large": "الصورة كبيرة (الحد 5 ميجا).",
           "too_small": "الملف ده مش صورة.",
           "type": "ابعت صورة JPG أو PNG.",
           "disk": "حصلت مشكلة في الحفظ، جرّب تاني."}


# ------------------------------------------------------------------ الحارس
def register(app):
    """يركّب كونسول الكتالوج على بوت متجر. آمن بلا إضافة: كل مسار يفحص الصلاحية."""

    def bid(ctx):
        return ctx.application.bot_data.get("bot_id")

    async def stop(update, ctx, text, markup=None):
        await update.effective_message.reply_text(text, reply_markup=markup)
        raise ApplicationHandlerStop

    async def screen(update, ctx, note=""):
        prods = _products(bid(ctx))
        cfg = _cfg_of(db.get_bot(bid(ctx)) or {})
        text = (note + "\n\n" if note else "") + catalog_text(prods, cfg.get("business_name", ""))
        await update.effective_message.reply_text(text, reply_markup=catalog_kb(prods))

    async def open_console(update, ctx):
        why = access(bid(ctx), update.effective_user.id)
        if why == "not_owner":
            await stop(update, ctx, "القائمة دي لصاحب المتجر. اضغط /start عشان تتسوّق 🛍️")
        if why == "inactive":
            await stop(update, ctx, _offer(bid(ctx)))
        ctx.user_data["cat"] = {"step": "idle"}
        await screen(update, ctx, "أهلاً يا صاحب المتجر 👋")
        raise ApplicationHandlerStop

    async def on_start(update, ctx):
        ctx.user_data.pop("cat", None)      # /start يخرج من الكونسول ويكمل للمتجر

    async def on_cb(update, ctx):
        q = update.callback_query
        if access(bid(ctx), q.from_user.id):
            await q.answer("غير مسموح", show_alert=True)
            raise ApplicationHandlerStop
        await q.answer()
        st = ctx.user_data.setdefault("cat", {"step": "idle"})
        parts = q.data.split(":")
        act = parts[1]
        idx = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else -1
        prods = _products(bid(ctx))
        if act == "close":
            ctx.user_data.pop("cat", None)
            await q.message.reply_text("تمام ✅ افتح /products في أي وقت.")
        elif act == "new":
            st["step"] = "add"
            st.pop("draft", None)
            await q.message.reply_text(ADD_HELP)
        elif act in ("price", "del") and not (0 <= idx < len(prods)):
            await q.message.reply_text("القائمة اتغيّرت — افتح /products تاني.")
        elif act == "price":
            st["step"], st["idx"] = "price", idx
            await q.message.reply_text(f"💵 السعر الجديد لـ«{prods[idx].get('name','')}» بالجنيه:")
        elif act == "del":
            await q.message.reply_text(
                f"متأكد إنك عايز تمسح «{prods[idx].get('name','')}»؟",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🗑 أيوه امسح", callback_data=f"cat:delok:{idx}"),
                    InlineKeyboardButton("لا", callback_data="cat:back")]]))
        elif act == "delok":
            if 0 <= idx < len(prods):
                gone = prods.pop(idx)
                save_products(ctx, bid(ctx), prods)
                await q.message.reply_text(f"🗑 اتمسح «{gone.get('name','')}».")
            await screen(update, ctx)
        elif act == "back":
            await screen(update, ctx)
        raise ApplicationHandlerStop

    async def add_product(update, ctx, name, price, asset_id=None):
        prods = _products(bid(ctx))
        if len(prods) >= MAX_PRODUCTS:
            await stop(update, ctx, f"وصلت للحد ({MAX_PRODUCTS} منتج) — امسح منتجاً أو عدّل من الموقع.")
        item = {"name": name[:NAME_MAX], "price": float(price)}
        if asset_id:
            item["asset"] = int(asset_id)
        prods.append(item)
        save_products(ctx, bid(ctx), prods)
        ctx.user_data["cat"] = {"step": "idle"}
        await screen(update, ctx, f"✅ اتضاف «{item['name']}» بسعر {item['price']:g} ج"
                                  + ("" if asset_id else "\n(من غير صورة — ابعت الصورة مع الاسم المرة الجاية)"))

    async def take_photo(update, ctx, msg):
        """ينزّل أكبر مقاس ويحفظه في المكتبة. يرجّع asset_id أو None (وقد ردّ بالسبب)."""
        row = db.get_bot(bid(ctx))
        photo = msg.photo[-1]
        try:
            f = await ctx.bot.get_file(photo.file_id)
            data = bytes(await f.download_as_bytearray())
        except Exception:
            log.exception("could not download a product photo for bot #%s", bid(ctx))
            await msg.reply_text("مقدرتش أنزّل الصورة، جرّب تبعتها تاني.")
            return None
        aid, why = save_photo(row, data, name=(msg.caption or "منتج"))
        if not aid:
            await msg.reply_text("⚠️ " + _REFUSE.get(why, "الصورة مرفوضة."))
        return aid

    async def on_msg(update, ctx):
        st = ctx.user_data.get("cat")
        if not st:
            return                                   # الكونسول مقفول: رسالة عميل عادية
        msg = update.effective_message
        if access(bid(ctx), update.effective_user.id):
            ctx.user_data.pop("cat", None)
            return
        text = (msg.text or msg.caption or "").strip()
        if text in ("خروج", "❌ خروج", "الغاء", "إلغاء"):
            ctx.user_data.pop("cat", None)
            await stop(update, ctx, "خرجت من إدارة المنتجات ✅")
        step = st.get("step", "idle")

        if step == "price":                          # تعديل سعر منتج قائم
            price = parse_price(text)
            if price is None:
                await stop(update, ctx, "اكتب رقم السعر بس، مثال: 250")
            prods = _products(bid(ctx))
            i = st.get("idx", -1)
            if not (0 <= i < len(prods)):
                ctx.user_data["cat"] = {"step": "idle"}
                await stop(update, ctx, "القائمة اتغيّرت — افتح /products تاني.")
            prods[i]["price"] = price
            save_products(ctx, bid(ctx), prods)
            ctx.user_data["cat"] = {"step": "idle"}
            await screen(update, ctx, f"✅ سعر «{prods[i].get('name','')}» بقى {price:g} ج")
            raise ApplicationHandlerStop

        draft = st.setdefault("draft", {})
        if msg.photo:                                 # صورة (ومعها الاسم والسعر غالباً)
            aid = await take_photo(update, ctx, msg)
            if aid:
                draft["asset"] = aid
            name, price = parse_product(text)
            if name and price is not None:
                await add_product(update, ctx, name, price, draft.get("asset"))
                raise ApplicationHandlerStop
            if name:
                draft["name"] = name
                st["step"] = "ask_price"
                await stop(update, ctx, f"تمام، «{name}» — السعر كام بالجنيه؟")
            st["step"] = "ask_name"
            await stop(update, ctx, "وصلت الصورة ✅ اسم المنتج إيه؟")

        if step == "ask_name":
            name, price = parse_product(text)
            if not name:
                await stop(update, ctx, "اكتب اسم المنتج:")
            draft["name"] = name
            if price is not None:
                await add_product(update, ctx, name, price, draft.get("asset"))
                raise ApplicationHandlerStop
            st["step"] = "ask_price"
            await stop(update, ctx, f"تمام، «{name}» — السعر كام بالجنيه؟")

        if step == "ask_price":
            price = parse_price(text)
            if price is None:
                await stop(update, ctx, "اكتب رقم السعر بس، مثال: 250")
            await add_product(update, ctx, draft.get("name", ""), price, draft.get("asset"))
            raise ApplicationHandlerStop

        # step == "add" أو "idle": رسالة نصية فيها اسم وسعر = منتج بلا صورة
        name, price = parse_product(text)
        if name and price is not None:
            await add_product(update, ctx, name, price, draft.get("asset"))
            raise ApplicationHandlerStop
        if name:
            draft["name"] = name
            st["step"] = "ask_price"
            await stop(update, ctx, f"تمام، «{name}» — السعر كام بالجنيه؟")
        await stop(update, ctx, ADD_HELP, None)

    app.add_handler(CommandHandler("products", open_console), group=GROUP)
    app.add_handler(CommandHandler("start", on_start), group=GROUP)
    app.add_handler(CallbackQueryHandler(on_cb, pattern=r"^cat:"), group=GROUP)
    app.add_handler(MessageHandler(~filters.COMMAND, on_msg), group=GROUP)
