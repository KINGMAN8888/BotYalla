"""بوت المنصة — يرسل تنبيه الدفع للأدمن بزرّي موافقة/رفض ويعالج القرار.
منفصل عن بوتات المستخدمين. يعمل داخل حلقة bot_manager."""
import json, logging
from telegram import (InlineKeyboardButton, InlineKeyboardMarkup, InputFile, KeyboardButton,
                      ReplyKeyboardMarkup, ReplyKeyboardRemove, Update)
from telegram.ext import (Application, CallbackQueryHandler, CommandHandler, ContextTypes,
                          MessageHandler, TypeHandler, filters)
import database as db
import managed_bots
import plans
import i18n
import mailer
import support_desk

log = logging.getLogger("platform_bot")

def _kb(pid):
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ موافقة / Approve", callback_data=f"pay_approve:{pid}"),
        InlineKeyboardButton("❌ رفض / Reject", callback_data=f"pay_reject:{pid}"),
    ]])

def build_caption(payment, username, auto_verdict):
    # شحن المحفظة ليس باقة: `plan_name` تُسقط أي معرّف مجهول إلى «Free»، فكان
    # الأدمن يقرأ «اشتراك في المجانية» على دفعة مال حقيقية وهو يقرّر اعتمادها.
    # والمدة من دورة الدفعة: دفعة سنوية تفعّل 365 يوماً لا 30.
    if payment["plan"] == db.WALLET_PLAN:
        head = "💳 طلب شحن رصيد / Wallet top-up"
        item = "📦 البند / Item: رصيد الرسائل التسويقية / Marketing credit"
        action = ("اضغط موافقة لإضافة المبلغ إلى رصيد العميل، أو رفض للإلغاء.\n"
                  "Tap Approve to credit the wallet, or Reject.")
    elif db.addon_bot_id(payment["plan"]):
        b = db.get_bot(db.addon_bot_id(payment["plan"])) or {}
        head = "🧩 طلب إضافة «تحصيل المدفوعات» / Payments add-on"
        item = (f"📦 البند / Item: تحصيل مدفوعات العملاء — بوت «{b.get('name', '?')}» "
                f"(#{b.get('id', '?')}) · 30 يوماً / days")
        action = ("اضغط موافقة لتفعيل الإضافة 30 يوماً على هذا البوت، أو رفض للإلغاء.\n"
                  "Tap Approve to enable the add-on on this bot for 30 days, or Reject.")
    else:
        annual = (payment.get("billing_cycle") or "monthly") == "annual"
        days = 365 if annual else 30
        head = "💳 طلب اشتراك جديد / New subscription payment"
        item = (f"📦 الباقة / Plan: {plans.plan_name(payment['plan'], 'en')} · "
                + ("سنوي / annual" if annual else "شهري / monthly"))
        action = (f"اضغط موافقة لتفعيل الاشتراك {days} يوماً، أو رفض للإلغاء.\n"
                  f"Tap Approve to activate {days} days, or Reject.")
    return (
        f"{head}\n\n"
        f"👤 المستخدم / User: {username} (#{payment['user_id']})\n"
        f"{item}\n"
        f"💰 المبلغ / Amount: {payment['amount']} EGP\n"
        f"🏦 الطريقة / Method: {payment['method']}\n"
        f"🧾 المرجع / Ref: {payment.get('ref') or '—'}\n"
        f"{auto_verdict}\n\n"
        f"{action}"
    )

async def _send_alert_async(app, admin_id, payment, username, caption, screenshot_path):
    # تعليق الصورة حدّه 1024 حرفاً في تليجرام — تجاوزه يُسقط التنبيه كله
    with open(screenshot_path, "rb") as f:
        msg = await app.bot.send_photo(int(admin_id), InputFile(f), caption=caption[:1024],
                                       reply_markup=_kb(payment["id"]))
    return msg.message_id


def _is_admin(uid):
    return str(uid) in db.admin_chat_ids()


# ---------------------------------------------------------------- تذاكر الدعم
async def on_ticket_close(update, ctx):
    """زرّ «✅ تم الحل» تحت تنبيه التذكرة — للأدمن وحده."""
    q = update.callback_query
    if not _is_admin(q.from_user.id):
        await q.answer("غير مصرّح / Not authorized", show_alert=True)
        return
    await q.answer()
    try:
        tid = int(q.data.split(":", 1)[1])
    except (IndexError, ValueError):
        return
    if db.set_ticket_status(tid, "closed"):
        try:
            await q.edit_message_text((q.message.text or "") + "\n\n✅ اتقفلت / Resolved")
        except Exception:
            pass


async def on_admin_reply(update, ctx):
    """Reply من الأدمن على تنبيه تذكرة (#T<id>) ← يُحفظ ويصل للعميل."""
    msg = update.message
    if (msg is None or msg.from_user is None or msg.reply_to_message is None
            or not _is_admin(msg.from_user.id)):
        return
    ref = msg.reply_to_message
    tid = support_desk.ticket_id_from(ref.text or ref.caption)
    body = (msg.text or "").strip()[:support_desk.BODY_MAX]
    if not tid or not body:
        return
    res = support_desk.record_staff_reply(tid, body, "telegram")
    if not res:
        await msg.reply_text(f"⚠️ التذكرة #T{tid} مش موجودة.")
        return
    via = []
    if res["chat"]:
        try:
            await ctx.bot.send_message(int(res["chat"]), res["text"])
            via.append("تليجرام")
        except Exception:
            log.warning("ticket #T%s reply to the customer's Telegram failed", tid)
    if res["emailed"]:
        via.append("الإيميل")
    await msg.reply_text(f"✅ ردّك اتسجّل على #T{tid} وظهر للعميل في صفحة الدعم"
                         + (f" + {' و'.join(via)}" if via else "") + ".")

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
        # ربط حساب العميل: /start link-CODE  → نحفظ chat_id لإرسال التذكيرات
        args = getattr(ctx, "args", None) or []
        if args and args[0].startswith(managed_bots.CODE_PREFIX):
            # إنشاء بوت بضغطة: الكود يربط هذا الحساب بطلب المنصة ثم يعرض زر الإنشاء
            await managed_bots.on_start_code(update, ctx, args[0][len(managed_bots.CODE_PREFIX):])
            return
        if args and args[0].startswith("phone-"):
            # تأكيد رقم الهاتف: زرّ «شارك رقمي» — تليجرام يرسل رقم الحساب نفسه (لا رقماً يكتبه أحد)
            code = args[0][6:]
            uid_ = db.phone_code_user(code)
            en = bool(uid_) and db.user_lang(uid_) == "en"
            if not uid_:
                await update.message.reply_text("⚠️ الرابط انتهى — اطلب رابطاً جديداً من صفحة «حسابي».\n"
                                                "⚠️ The link expired — request a new one from your account page.")
                return
            ctx.user_data["phone_verify"] = (uid_, code)
            kb = ReplyKeyboardMarkup([[KeyboardButton("📱 Share my number" if en else "📱 شارك رقمي للتأكيد",
                                                      request_contact=True)]],
                                     resize_keyboard=True, one_time_keyboard=True)
            await update.message.reply_text(
                "Tap the button below to share your number. Telegram sends your own account's number — "
                "that's how we know it's yours." if en else
                "اضغط الزر تحت لمشاركة رقمك. تليجرام بيبعت رقم حسابك أنت نفسه — وده اللي بيثبت إن الرقم رقمك.",
                reply_markup=kb)
            return
        if args and args[0].startswith("link-"):
            uid_ = db.claim_tg_link(args[0][5:], update.effective_user.id)
            if uid_:
                lang = db.user_lang(uid_)
                await update.message.reply_text(i18n.t("tg_link_done", lang))
            else:
                await update.message.reply_text(i18n.t("tg_link_bad", "ar"))
            return
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

    async def on_contact(update, ctx):
        """جهة اتصال بعد «شارك رقمي». تُقبل جهة اتصال صاحب الحساب وحده (contact.user_id)."""
        pending = ctx.user_data.get("phone_verify")
        c = update.message.contact if update.message else None
        if not pending or not c:
            return
        uid_, code = pending
        en = db.user_lang(uid_) == "en"
        if c.user_id != update.effective_user.id:
            await update.message.reply_text("Share your own number with the button — not another contact." if en
                                            else "شارك رقمك أنت بالزر — مش جهة اتصال تانية.")
            return
        res = db.verify_phone_tg(uid_, code, c.phone_number, update.effective_user.id)
        if res == "ok":
            ctx.user_data.pop("phone_verify", None)
            text = ("✅ Your phone number is verified, and this Telegram is now linked for account alerts."
                    if en else "✅ تم تأكيد رقم هاتفك، واتربط تليجرام ده بحسابك لتنبيهات الاشتراك.")
        elif res == "mismatch":
            text = ("⚠️ This Telegram number differs from the one on your account. Change it on your account "
                    "page to this number, then try again." if en else
                    "⚠️ رقم تليجرام ده مختلف عن الرقم المسجّل في حسابك. عدّل الرقم في «حسابي» لنفس رقم "
                    "تليجرام وجرّب تاني.")
        else:
            ctx.user_data.pop("phone_verify", None)
            text = ("⚠️ The link expired — request a new one from your account page." if en
                    else "⚠️ الرابط انتهى — اطلب رابطاً جديداً من صفحة «حسابي».")
        await update.message.reply_text(text, reply_markup=ReplyKeyboardRemove())

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(MessageHandler(filters.CONTACT, on_contact))
    app.add_handler(CommandHandler("stats", cmd_stats))
    app.add_handler(CommandHandler(["pending","payments"], cmd_pending))
    app.add_handler(CommandHandler("users", cmd_users))
    app.add_handler(CommandHandler(["revenue","sales"], cmd_revenue))
    app.add_handler(CommandHandler("help", cmd_start))

def register(app: Application):
    async def on_decision(update, ctx: ContextTypes.DEFAULT_TYPE):
        q = update.callback_query
        admin_id = db.get_platform("admin_chat_id", "")
        # التفويض: الأدمن فقط. لا تُجب على الاستعلام قبل هذا الفحص —
        # تليجرام يقبل إجابة واحدة فقط، وإجابة مبكرة تبتلع تنبيه «غير مصرّح».
        if not admin_id or str(q.from_user.id) != str(admin_id):
            await q.answer("غير مصرّح / Not authorized", show_alert=True)
            return
        await q.answer()
        action, _, sid = q.data.partition(":")
        try: pid = int(sid)
        except ValueError: return
        status = "approved" if action == "pay_approve" else "rejected"
        row = db.finalize_payment(pid, status)    # ذرّي: يرجّع None لو سبق البتّ
        if not row:
            await q.edit_message_caption(caption=(q.message.caption or "") + "\n\n⚠️ سبق البتّ في هذا الطلب / Already decided.")
            return
        # إيصال بالإيميل — نفس ما يحدث في الموافقة من الويب. في خيط خلفي،
        # فلا يحجب حلقة asyncio، وفشله لا يمسّ التسوية التي ثبتت فعلاً.
        mailer.send_payment_receipt(row, status)
        if status == "approved" and row["plan"] == db.WALLET_PLAN:
            bal = row.get("wallet_after")
            tail = (f"\n\n✅ تمت الموافقة وشحن الرصيد — الرصيد الآن {(bal or 0) / 100:g} EGP"
                    f" / Approved & credited.")
        elif status == "approved" and db.addon_bot_id(row["plan"]):
            tail = "\n\n✅ تمت الموافقة وتفعيل إضافة «تحصيل المدفوعات» 30 يوماً / Add-on activated."
        elif status == "approved":
            tail = f"\n\n✅ تمت الموافقة وتفعيل «{plans.plan_name(row['plan'],'ar')}» / Approved & activated."
        else:
            tail = "\n\n❌ تم الرفض / Rejected."
        try:
            await q.edit_message_caption(caption=(q.message.caption or "") + tail)
        except Exception:
            pass
        # إشعار المستخدم عبر بوتاته غير متاح هنا؛ الحالة تظهر في لوحته.
    app.add_handler(CallbackQueryHandler(on_decision, pattern=r"^pay_(approve|reject):"))
    app.add_handler(CallbackQueryHandler(on_ticket_close, pattern=r"^tk_close:\d+$"))
    app.add_handler(MessageHandler(filters.TEXT & filters.REPLY & ~filters.COMMAND, on_admin_reply))
    register_admin_commands(app)
    # تحديثات managed_bot (ورسالة managed_bot_created) — مجموعة -1 مستقلة: المعالج
    # يطابق كل تحديث ويتجاهل ما ليس إنشاء بوت، فلا يحجب الأوامر في المجموعة 0.
    app.add_handler(TypeHandler(Update, managed_bots.on_update), group=-1)
