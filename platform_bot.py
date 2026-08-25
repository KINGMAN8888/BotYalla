"""بوت المنصة — يرسل تنبيه الدفع للأدمن بزرّي موافقة/رفض ويعالج القرار.
منفصل عن بوتات المستخدمين. يعمل داخل حلقة bot_manager."""
import json, logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes
import database as db
import plans

log = logging.getLogger("platform_bot")

def _kb(pid):
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ موافقة / Approve", callback_data=f"pay_approve:{pid}"),
        InlineKeyboardButton("❌ رفض / Reject", callback_data=f"pay_reject:{pid}"),
    ]])

def build_caption(payment, username, auto_verdict):
    plan = plans.plan_name(payment["plan"], "en")
    return (
        f"💳 طلب اشتراك جديد / New subscription payment\n\n"
        f"👤 المستخدم / User: {username} (#{payment['user_id']})\n"
        f"📦 الباقة / Plan: {plan}\n"
        f"💰 المبلغ / Amount: {payment['amount']} EGP\n"
        f"🏦 الطريقة / Method: {payment['method']}\n"
        f"🧾 المرجع / Ref: {payment.get('ref') or '—'}\n"
        f"{auto_verdict}\n\n"
        f"اضغط موافقة لتفعيل الاشتراك 30 يوماً، أو رفض للإلغاء.\n"
        f"Tap Approve to activate 30 days, or Reject."
    )

async def _send_alert_async(app, admin_id, payment, username, caption, screenshot_path):
    with open(screenshot_path, "rb") as f:
        msg = await app.bot.send_photo(int(admin_id), InputFile(f), caption=caption, reply_markup=_kb(payment["id"]))
    return msg.message_id


def _is_admin(uid):
    return str(uid) in db.admin_chat_ids()

def stats_text():
    st = db.platform_stats()
    by = st.get("by_plan", {})
    lines = [
        "📊 لوحة المنصة / Platform",
        f"👥 المستخدمون: {st['users']}",
        f"🤖 البوتات: {st['bots']} (يعمل {st['active_bots']})",
        f"💎 مشتركون مدفوعون: {st['paying']}",
        f"⏳ مدفوعات معلّقة: {st['pending']}",
        f"💰 إجمالي الإيرادات المقبولة: {st['revenue']} EGP",
    ]
    if by:
        lines.append("— الباقات: " + " · ".join(f"{k}:{v}" for k, v in by.items()))
    return "\n".join(lines)

def register_admin_commands(app: Application):
    async def guard(update):
        return update.effective_user and _is_admin(update.effective_user.id)

    async def cmd_start(update, ctx):
        if not await guard(update):
            await update.message.reply_text("👋 هذا بوت إدارة المنصة (للمالك فقط).")
            return
        await update.message.reply_text(
            "🛡️ أهلاً بك في لوحة إدارة BotYalla\n\n"
            "الأوامر:\n/stats — إحصائيات المنصة\n/pending — المدفوعات المعلّقة\n"
            "/users — آخر المستخدمين\n/revenue — الإيرادات\n/help — المساعدة")

    async def cmd_stats(update, ctx):
        if not await guard(update): return
        await update.message.reply_text(stats_text())

    async def cmd_pending(update, ctx):
        if not await guard(update): return
        rows = db.all_pending_payments()
        if not rows:
            await update.message.reply_text("لا توجد مدفوعات معلّقة ✅"); return
        for r in rows[:10]:
            kb = _kb(r["id"])
            await update.message.reply_text(
                f"⏳ دفعة #{r['id']}\n👤 {r['username']}\n📦 {r['plan']} — {r['amount']} EGP\n🏦 {r['method']}",
                reply_markup=kb)

    async def cmd_users(update, ctx):
        if not await guard(update): return
        us = db.list_all_users(limit=15)
        lines = ["👥 آخر المستخدمين:"]
        for u in us:
            lines.append(f"#{u['id']} {u['username']} · {u['role']} · {u['plan']}" + (" · 🚫" if u['is_blocked'] else ""))
        await update.message.reply_text("\n".join(lines))

    async def cmd_revenue(update, ctx):
        if not await guard(update): return
        st = db.platform_stats()
        await update.message.reply_text(f"💰 إجمالي الإيرادات المقبولة: {st['revenue']} EGP\n💎 مشتركون مدفوعون: {st['paying']}")

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("stats", cmd_stats))
    app.add_handler(CommandHandler(["pending","payments"], cmd_pending))
    app.add_handler(CommandHandler("users", cmd_users))
    app.add_handler(CommandHandler(["revenue","sales"], cmd_revenue))
    app.add_handler(CommandHandler("help", cmd_start))

def register(app: Application):
    async def on_decision(update, ctx: ContextTypes.DEFAULT_TYPE):
        q = update.callback_query
        await q.answer()
        admin_id = db.get_platform("admin_chat_id", "")
        # التفويض: الأدمن فقط
        if not admin_id or str(q.from_user.id) != str(admin_id):
            await q.answer("غير مصرّح / Not authorized", show_alert=True)
            return
        action, _, sid = q.data.partition(":")
        try: pid = int(sid)
        except ValueError: return
        status = "approved" if action == "pay_approve" else "rejected"
        row = db.finalize_payment(pid, status)    # ذرّي: يرجّع None لو سبق البتّ
        if not row:
            await q.edit_message_caption(caption=(q.message.caption or "") + "\n\n⚠️ سبق البتّ في هذا الطلب / Already decided.")
            return
        if status == "approved":
            tail = f"\n\n✅ تمت الموافقة وتفعيل «{plans.plan_name(row['plan'],'ar')}» / Approved & activated."
        else:
            tail = "\n\n❌ تم الرفض / Rejected."
        try:
            await q.edit_message_caption(caption=(q.message.caption or "") + tail)
        except Exception:
            pass
        # إشعار المستخدم عبر بوتاته غير متاح هنا؛ الحالة تظهر في لوحته.
    app.add_handler(CallbackQueryHandler(on_decision, pattern=r"^pay_(approve|reject):"))
    register_admin_commands(app)
