"""قوالب BotYalla: flow (No-Code)، store (متجر)، booking (حجوزات)، customer_service.
store و booking مدفوعان بالإعدادات. جميعها تسجّل المشترك وحدث البدء."""
import datetime
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (Application, CommandHandler, MessageHandler, filters,
                          ContextTypes, ConversationHandler)
import database as db
from flow_engine import build_flow, _cfg, _bid, notify_owner, track_start, send_intro
import tg_helpers as tg

# ---------- متجر ----------
ST_MENU, ST_QTY, ST_NAME, ST_PHONE, ST_ADDR, ST_CONFIRM = range(10, 16)

def build_store(app: Application):
    def prods(ctx): return _cfg(ctx).get("products", [])
    def menu_kb(ctx):
        rows = [[f"{i+1}. {p['name']} - {p['price']} ج"] for i, p in enumerate(prods(ctx))]
        rows.append(["🛒 إنهاء الطلب", "❌ إلغاء"])
        return ReplyKeyboardMarkup(rows, resize_keyboard=True)

    async def start(update, ctx):
        if await tg.try_claim_owner(update, ctx):
            return ConversationHandler.END
        await track_start(update, ctx)
        ctx.user_data["cart"] = []
        if not prods(ctx):
            await update.message.reply_text("⚠️ لا توجد منتجات بعد.")
            return ConversationHandler.END
        await send_intro(update, ctx,
            _cfg(ctx).get("welcome") or f"🛍️ أهلاً بك في «{_cfg(ctx).get('business_name','متجرنا')}»! اختر منتجاً:",
            menu_kb(ctx))
        return ST_MENU

    async def choose(update, ctx):
        t = update.message.text.strip()
        if t == "❌ إلغاء": return await cancel(update, ctx)
        if t.startswith("🛒"):
            if not ctx.user_data.get("cart"):
                await update.message.reply_text("سلتك فارغة."); return ST_MENU
            await update.message.reply_text("👤 اكتب اسمك:", reply_markup=ReplyKeyboardRemove()); return ST_NAME
        try: idx = int(t.split(".")[0]) - 1
        except Exception: idx = -1
        ps = prods(ctx)
        if not (0 <= idx < len(ps)):
            await update.message.reply_text("اختر منتجاً من القائمة."); return ST_MENU
        ctx.user_data["pending"] = ps[idx]
        if ps[idx].get("image"):
            try: await update.message.reply_photo(ps[idx]["image"])
            except Exception: pass
        await update.message.reply_text(f"كم عدد «{ps[idx]['name']}»؟", reply_markup=ReplyKeyboardRemove())
        return ST_QTY

    async def qty(update, ctx):
        try:
            n = int(update.message.text.strip()); assert 0 < n <= 999
        except Exception:
            await update.message.reply_text("اكتب رقماً صحيحاً:"); return ST_QTY
        p = ctx.user_data.pop("pending")
        ctx.user_data["cart"].append({"name": p["name"], "price": p["price"], "qty": n})
        tot = sum(i["price"]*i["qty"] for i in ctx.user_data["cart"])
        await update.message.reply_text(f"✅ أضيف. إجمالي السلة: {tot} ج", reply_markup=menu_kb(ctx))
        return ST_MENU

    async def name(update, ctx):
        ctx.user_data["c_name"] = update.message.text.strip()
        await update.message.reply_text("📱 رقم التليفون:"); return ST_PHONE
    async def phone(update, ctx):
        ctx.user_data["c_phone"] = update.message.text.strip()
        await update.message.reply_text("📍 العنوان بالتفصيل:"); return ST_ADDR
    async def addr(update, ctx):
        ctx.user_data["c_addr"] = update.message.text.strip()
        cart = ctx.user_data["cart"]; tot = sum(i["price"]*i["qty"] for i in cart)
        lines = "\n".join(f"• {i['name']} × {i['qty']} = {i['price']*i['qty']} ج" for i in cart)
        await update.message.reply_text(
            f"📋 تأكيد الطلب:\n{lines}\n\n💰 الإجمالي: {tot} ج\n\nاكتب «تأكيد» أو «إلغاء».",
            reply_markup=ReplyKeyboardMarkup([["تأكيد", "إلغاء"]], resize_keyboard=True))
        return ST_CONFIRM

    async def confirm(update, ctx):
        if update.message.text.strip() != "تأكيد": return await cancel(update, ctx)
        cart = ctx.user_data["cart"]; tot = sum(i["price"]*i["qty"] for i in cart)
        u = update.effective_user
        db.add_order(_bid(ctx), u.id, ctx.user_data.get("c_name"), ctx.user_data.get("c_phone"),
                     ctx.user_data.get("c_addr"), cart, tot)
        await update.message.reply_text(
            _cfg(ctx).get("thanks") or "🎉 تم استلام طلبك! هنتواصل لتأكيد التوصيل.",
            reply_markup=ReplyKeyboardRemove())
        lines = "\n".join(f"• {i['name']} × {i['qty']}" for i in cart)
        await notify_owner(ctx, f"🛒 طلب جديد «{_cfg(ctx).get('business_name','')}»\n"
                                f"👤 {ctx.user_data.get('c_name')}\n📱 {ctx.user_data.get('c_phone')}\n"
                                f"📍 {ctx.user_data.get('c_addr')}\n{lines}\n💰 {tot} ج")
        ctx.user_data.clear(); return ConversationHandler.END

    async def cancel(update, ctx):
        await update.message.reply_text("تم الإلغاء. /start للبدء.", reply_markup=ReplyKeyboardRemove())
        ctx.user_data.clear(); return ConversationHandler.END

    app.add_handler(ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={ST_MENU:[MessageHandler(filters.TEXT & ~filters.COMMAND, choose)],
                ST_QTY:[MessageHandler(filters.TEXT & ~filters.COMMAND, qty)],
                ST_NAME:[MessageHandler(filters.TEXT & ~filters.COMMAND, name)],
                ST_PHONE:[MessageHandler(filters.TEXT & ~filters.COMMAND, phone)],
                ST_ADDR:[MessageHandler(filters.TEXT & ~filters.COMMAND, addr)],
                ST_CONFIRM:[MessageHandler(filters.TEXT & ~filters.COMMAND, confirm)]},
        fallbacks=[CommandHandler("cancel", cancel)]))

# ---------- حجوزات ----------
BK_DATE, BK_TIME, BK_NAME, BK_PHONE = range(20, 24)
AR_DAYS = ["الإثنين","الثلاثاء","الأربعاء","الخميس","الجمعة","السبت","الأحد"]  # Mon..Sun (weekday())

def generate_slots(cfg, taken):
    """يرجّع {date: [times]} للمواعيد المتاحة."""
    days_ahead = int(cfg.get("days_ahead", 7))
    open_h = int(cfg.get("open_hour", 10))
    close_h = int(cfg.get("close_hour", 22))
    step = int(cfg.get("slot_minutes", 60))
    work_days = cfg.get("working_days")  # قائمة أرقام weekday() 0..6، أو None = كل الأيام
    today = datetime.date.today()
    result = {}
    for d in range(days_ahead):
        day = today + datetime.timedelta(days=d)
        if work_days is not None and day.weekday() not in work_days:
            continue
        times = []
        cur = datetime.datetime.combine(day, datetime.time(open_h, 0))
        end = datetime.datetime.combine(day, datetime.time(close_h, 0))
        while cur < end:
            slot = cur.strftime("%Y-%m-%d %H:%M")
            # تجاوز المواعيد الماضية في نفس اليوم
            if cur > datetime.datetime.now() and slot not in taken:
                times.append(cur.strftime("%H:%M"))
            cur += datetime.timedelta(minutes=step)
        if times:
            result[day.strftime("%Y-%m-%d")] = times
    return result

def build_booking(app: Application):
    def slots(ctx):
        return generate_slots(_cfg(ctx), db.taken_slots(_bid(ctx)))

    async def start(update, ctx):
        if await tg.try_claim_owner(update, ctx):
            return ConversationHandler.END
        await track_start(update, ctx)
        s = slots(ctx)
        if not s:
            await update.message.reply_text("⚠️ لا توجد مواعيد متاحة حالياً.")
            return ConversationHandler.END
        ctx.user_data["slots"] = s
        rows = [[d] for d in list(s.keys())[:12]] + [["❌ إلغاء"]]
        await send_intro(update, ctx,
            _cfg(ctx).get("welcome") or f"📅 احجز موعدك في «{_cfg(ctx).get('business_name','')}». اختر اليوم:",
            ReplyKeyboardMarkup(rows, resize_keyboard=True))
        return BK_DATE

    async def pick_date(update, ctx):
        t = update.message.text.strip()
        if t == "❌ إلغاء": return await cancel(update, ctx)
        s = ctx.user_data.get("slots", {})
        if t not in s:
            await update.message.reply_text("اختر يوماً من القائمة."); return BK_DATE
        ctx.user_data["date"] = t
        rows = [[tm] for tm in s[t]] + [["❌ إلغاء"]]
        await update.message.reply_text("⏰ اختر الوقت:", reply_markup=ReplyKeyboardMarkup(rows, resize_keyboard=True))
        return BK_TIME

    async def pick_time(update, ctx):
        t = update.message.text.strip()
        if t == "❌ إلغاء": return await cancel(update, ctx)
        s = ctx.user_data.get("slots", {}); date = ctx.user_data.get("date")
        if t not in s.get(date, []):
            await update.message.reply_text("اختر وقتاً من القائمة."); return BK_TIME
        ctx.user_data["time"] = t
        await update.message.reply_text("👤 اكتب اسمك:", reply_markup=ReplyKeyboardRemove())
        return BK_NAME

    async def get_name(update, ctx):
        ctx.user_data["b_name"] = update.message.text.strip()
        await update.message.reply_text("📱 رقم تليفونك:"); return BK_PHONE

    async def get_phone(update, ctx):
        ctx.user_data["b_phone"] = update.message.text.strip()
        slot = f"{ctx.user_data['date']} {ctx.user_data['time']}"
        u = update.effective_user
        ok = db.book_slot(_bid(ctx), u.id, ctx.user_data.get("b_name"),
                          ctx.user_data.get("b_phone"), _cfg(ctx).get("service_name",""), slot)
        if not ok:
            await update.message.reply_text("⚠️ عذراً، تم حجز هذا الموعد للتو. أرسل /start لاختيار موعد آخر.",
                                            reply_markup=ReplyKeyboardRemove())
            ctx.user_data.clear(); return ConversationHandler.END
        await update.message.reply_text(
            (_cfg(ctx).get("thanks") or "✅ تم تأكيد حجزك!") + f"\n🗓️ {slot}",
            reply_markup=ReplyKeyboardRemove())
        await notify_owner(ctx, f"📅 حجز جديد «{_cfg(ctx).get('business_name','')}»\n"
                                f"👤 {ctx.user_data.get('b_name')}\n📱 {ctx.user_data.get('b_phone')}\n🗓️ {slot}")
        ctx.user_data.clear(); return ConversationHandler.END

    async def cancel(update, ctx):
        await update.message.reply_text("تم الإلغاء. /start للبدء.", reply_markup=ReplyKeyboardRemove())
        ctx.user_data.clear(); return ConversationHandler.END

    app.add_handler(ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={BK_DATE:[MessageHandler(filters.TEXT & ~filters.COMMAND, pick_date)],
                BK_TIME:[MessageHandler(filters.TEXT & ~filters.COMMAND, pick_time)],
                BK_NAME:[MessageHandler(filters.TEXT & ~filters.COMMAND, get_name)],
                BK_PHONE:[MessageHandler(filters.TEXT & ~filters.COMMAND, get_phone)]},
        fallbacks=[CommandHandler("cancel", cancel)]))

TEMPLATES = {
    "flow":             {"label": "باني محادثات (No-Code)", "build": build_flow,     "icon": "🧩"},
    "store":            {"label": "متجر صغير",              "build": build_store,    "icon": "🛍️"},
    "booking":          {"label": "حجوزات ومواعيد",         "build": build_booking,  "icon": "📅"},
    "customer_service": {"label": "خدمة عملاء",             "build": build_flow,     "icon": "📞"},
}
