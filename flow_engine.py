"""محرك الفلو العام (No-Code) — يشغّل أي بوت مبني من باني المحادثات.
الفلو محفوظ في config['flow'] = {start_message, steps:[...], end_message}.
كل خطوة: {type: 'question'|'buttons'|'message', prompt, var, options?}."""
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (Application, CommandHandler, MessageHandler, filters,
                          ContextTypes, ConversationHandler)
import database as db
import tg_helpers as tg

FLOW = 1

def _cfg(ctx):  return ctx.application.bot_data.get("config", {})
def _bid(ctx):  return ctx.application.bot_data.get("bot_id")

async def notify_owner(ctx, text):
    owner = _cfg(ctx).get("owner_chat_id")
    if owner:
        try: await ctx.bot.send_message(int(owner), text)
        except Exception: pass

async def send_intro(update, ctx, text, reply_markup=None):
    """يرسل صورة الترحيب مع النص إن وُجدت، وإلا نصاً فقط."""
    img = _cfg(ctx).get("welcome_image")
    if img:
        try:
            await update.message.reply_photo(img, caption=text, reply_markup=reply_markup)
            return
        except Exception:
            pass
    await update.message.reply_text(text, reply_markup=reply_markup)

async def track_start(update, ctx):
    u = update.effective_user
    db.add_bot_user(_bid(ctx), u.id, u.first_name or "")
    db.log_event(_bid(ctx), "start")

DEFAULT_CS_FLOW = {
    "start_message": "👋 أهلاً بك! هجمع منك بعض البيانات بسرعة.",
    "steps": [
        {"id": "name",  "type": "question", "prompt": "📝 اكتب اسمك:",        "var": "الاسم"},
        {"id": "phone", "type": "question", "prompt": "📱 رقم تليفونك:",       "var": "التليفون"},
        {"id": "msg",   "type": "question", "prompt": "✍️ اكتب استفسارك:",     "var": "الرسالة"},
    ],
    "end_message": "✅ تم استلام طلبك وسنتواصل معك قريباً. شكراً لك!",
}

def _flow(ctx):
    f = _cfg(ctx).get("flow")
    if not f or not f.get("steps"):
        return DEFAULT_CS_FLOW
    return f

def build_flow(app: Application):
    async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if await tg.try_claim_owner(update, ctx):
            return ConversationHandler.END
        await track_start(update, ctx)
        f = _flow(ctx)
        ctx.user_data["fi"] = 0
        ctx.user_data["fdata"] = {}
        if f.get("start_message"):
            await send_intro(update, ctx, f["start_message"], ReplyKeyboardRemove())
        return await present(update, ctx)

    async def present(update, ctx):
        f = _flow(ctx); steps = f.get("steps", [])
        i = ctx.user_data.get("fi", 0)
        # تخطّي خطوات الرسالة النصية (بدون إدخال)
        while i < len(steps) and steps[i].get("type") == "message":
            await update.message.reply_text(steps[i].get("prompt", ""), reply_markup=ReplyKeyboardRemove())
            i += 1
        ctx.user_data["fi"] = i
        if i >= len(steps):
            return await finish(update, ctx)
        step = steps[i]
        if step.get("type") == "buttons" and step.get("options"):
            kb = ReplyKeyboardMarkup([[o] for o in step["options"]],
                                     resize_keyboard=True, one_time_keyboard=True)
            await update.message.reply_text(step.get("prompt", "اختر:"), reply_markup=kb)
        else:
            await update.message.reply_text(step.get("prompt", "اكتب:"), reply_markup=ReplyKeyboardRemove())
        return FLOW

    async def on_input(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        f = _flow(ctx); steps = f.get("steps", [])
        i = ctx.user_data.get("fi", 0)
        if i >= len(steps):
            return await finish(update, ctx)
        step = steps[i]
        ans = (update.message.text or "").strip()
        if step.get("type") == "buttons" and step.get("options") and ans not in step["options"]:
            await update.message.reply_text("↩️ من فضلك اختر من الأزرار المتاحة.")
            return FLOW
        ctx.user_data.setdefault("fdata", {})[step.get("var") or step.get("id")] = ans
        ctx.user_data["fi"] = i + 1
        return await present(update, ctx)

    async def finish(update, ctx):
        data = ctx.user_data.get("fdata", {})
        u = update.effective_user
        db.add_lead(_bid(ctx), u.id, data)
        f = _flow(ctx)
        await update.message.reply_text(
            f.get("end_message", "✅ تم الاستلام، شكراً لك!"),
            reply_markup=ReplyKeyboardRemove())
        if data:
            lines = "\n".join(f"• {k}: {v}" for k, v in data.items())
            await notify_owner(ctx, f"🔔 إدخال جديد على «{_cfg(ctx).get('business_name','')}»\n{lines}")
        ctx.user_data.clear()
        return ConversationHandler.END

    async def cancel(update, ctx):
        await update.message.reply_text("تم الإلغاء. أرسل /start للبدء.", reply_markup=ReplyKeyboardRemove())
        ctx.user_data.clear()
        return ConversationHandler.END

    app.add_handler(ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={FLOW: [MessageHandler(filters.TEXT & ~filters.COMMAND, on_input)]},
        fallbacks=[CommandHandler("cancel", cancel)],
    ))

# دوال منطقية قابلة للاختبار بدون تليجرام
def compute_next(step_index, steps):
    i = step_index
    while i < len(steps) and steps[i].get("type") == "message":
        i += 1
    return i
