"""قوالب BotYalla: flow (No-Code)، store (متجر)، booking (حجوزات)، customer_service.
store و booking مدفوعان بالإعدادات. جميعها تسجّل المشترك وحدث البدء."""
import asyncio, datetime, hashlib, json, logging
from telegram import (Update, ReplyKeyboardMarkup, ReplyKeyboardRemove, InlineKeyboardButton,
                      InlineKeyboardMarkup)
from telegram.ext import (Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters,
                          ContextTypes, ConversationHandler)
import database as db
import payments as pay
from flow_engine import build_flow, _cfg, _bid, notify_owner, track_start, send_intro, inbox_out
import tg_helpers as tg

# ---------- صندوق الوارد ----------
# المتجر والحجز والقائمة لا تمرّ بمحرك الفلو (LoggedChannel)، فكانت ردودها الجاهزة لا تظهر في
# صندوق الوارد: صاحب النشاط يرى رسالة عميله ولا يرى ما ردّ به بوته. كل رد قالب يمرّ من هنا.
async def _say(update, ctx, text, **kw):
    msg = await update.effective_message.reply_text(text, **kw)
    inbox_out(update, ctx, text, kw.get("reply_markup"))
    return msg

async def _photo(update, ctx, photo, **kw):
    msg = await update.effective_message.reply_photo(photo, **kw)
    inbox_out(update, ctx, kw.get("caption") or "", kw.get("reply_markup"), kind="media")
    return msg

log = logging.getLogger("templates_bot")

async def _tell_owner(ctx, text):
    """إشعار صاحب البوت من قالب. `flow_engine.notify_owner` تأخذ (صف البوت، القناة، النص)؛
    القوالب كانت تستدعيها بـ (ctx, نص) فترمي TypeError بعد رسالة الشكر: لا إشعار بالطلب ولا
    بالحجز، ويبقى العميل عالقاً في آخر خطوة."""
    row = db.get_bot(_bid(ctx))
    if row:
        from channels.telegram import TelegramChannel
        await notify_owner(row, TelegramChannel(ctx.bot), text)

# ---------- تحصيل المدفوعات (إضافة مدفوعة لكل بوت) ----------
# بعد تأكيد الطلب: العميل يحوّل على حسابات صاحب البوت ويرسل صورة الإيصال، فيُفحص بمحرك
# إيصالات المنصة ويصل صاحب البوت بزرّين. الدوال على مستوى الوحدة لتُختبر بلا تليجرام.
_PAY_REFS = ("vodafone", "instapay", "bank_iban", "bank_account", "bank_holder")
PAY_CANCEL = "❌ إلغاء الطلب"
_BOT_REFUSAL = {
    "not_receipt": "⛔ الصورة دي مش إيصال تحويل. ابعت لقطة شاشة لرسالة أو شاشة نجاح التحويل، "
                   "يظهر فيها المبلغ ورقم المستلم.",
    "duplicate": "⛔ الإيصال ده اتبعت قبل كده. لو عملت تحويل جديد ابعت إيصاله.",
    "wrong_recipient": "⛔ الإيصال مش ظاهر فيه إن التحويل على حسابنا ({ref}). اتأكد من الرقم، "
                       "وابعت لقطة يظهر فيها المستلم.",
    "amount_mismatch": "⛔ المبلغ المطلوب ({amount} ج) مش ظاهر في الإيصال. ابعت لقطة واضحة يظهر "
                       "فيها المبلغ كامل.",
}

def _pay_kb():
    return ReplyKeyboardMarkup([[PAY_CANCEL]], resize_keyboard=True)

def pay_enabled(ctx):
    """الإضافة سارية (تُقرأ من القاعدة لحظة الطلب) ولصاحب البوت وسيلة استلام واحدة على الأقل."""
    m = _cfg(ctx).get("pay") or {}
    return bool(any(m.get(k) for k in ("vodafone", "instapay", "bank_account", "bank_iban"))
                and db.addon_active(_bid(ctx)))

def pay_instructions(methods, total, order_id):
    lines = [f"💳 لإتمام طلبك (#{order_id}) حوّل {total:g} ج على:"]
    if methods.get("vodafone"):
        lines.append(f"• فودافون كاش: {methods['vodafone']}")
    if methods.get("instapay"):
        lines.append(f"• انستاباي: {methods['instapay']}"
                     + (f"\n  {methods['instapay_link']}" if methods.get("instapay_link") else ""))
    bank = " · ".join(x for x in (methods.get("bank_name"), methods.get("bank_account"),
                                  methods.get("bank_iban")) if x)
    if bank:
        lines.append(f"• تحويل بنكي: {bank}"
                     + (f" — باسم {methods['bank_holder']}" if methods.get("bank_holder") else ""))
    lines.append("\n📸 بعد التحويل ابعت هنا صورة (سكرين شوت) الإيصال، ونأكدلك الطلب.")
    return "\n".join(lines)

def pay_decision_text(row):
    """رسالة العميل بقرار صاحب البوت — من زرّ تليجرام أو من اللوحة (app.bot_payment_decide)."""
    oid = f" (#{row['order_id']})" if row.get("order_id") else ""
    if row.get("status") == "approved":
        return f"✅ تم تأكيد دفع طلبك{oid} — شكراً لك! هنتواصل معاك للتوصيل."
    return (f"❌ لم نتمكن من تأكيد الدفع لطلبك{oid}. راجع التحويل وابعت الإيصال الصحيح، "
            "أو تواصل معنا.")

async def on_receipt(update, ctx):
    """صورة إيصال من العميل: فحص آلي في خيط منفصل (قراءة الصورة لا توقف حلقة كل البوتات) ←
    رفض فوري لما ليس إيصالاً أو على مستلم آخر أو بمبلغ آخر أو مكرر، وإلا دفعة معلّقة تصل
    صاحب البوت بزرّي تأكيد/رفض."""
    info = ctx.user_data.get("pay")
    if not info:
        return ConversationHandler.END
    msg = update.message
    media = msg.photo[-1] if msg.photo else msg.document
    if media is None:
        await _say(update, ctx, "📸 ابعت صورة الإيصال نفسها.", reply_markup=_pay_kb())
        return ST_PAY
    data = bytes(await (await media.get_file()).download_as_bytearray())
    methods = _cfg(ctx).get("pay") or {}
    bid = _bid(ctx)
    img_hash = hashlib.sha256(data).hexdigest()
    prior = ctx.user_data.get("pay_refusals", 0)
    ac = await asyncio.to_thread(pay.auto_check, data, info["amount"],
                                 [methods[k] for k in _PAY_REFS if methods.get(k)],
                                 db.bot_payment_hash_used(bid, img_hash), prior)
    if not (ac.get("image") or {}).get("ok"):
        await _say(update, ctx, "⛔ الملف ده مش صورة صالحة. ابعت صورة إيصال التحويل.", reply_markup=_pay_kb())
        return ST_PAY
    if ac.get("refuse"):
        ctx.user_data["pay_refusals"] = prior + 1
        to = methods.get("vodafone") or methods.get("instapay") or "—"
        text = _BOT_REFUSAL.get(ac.get("reason"), _BOT_REFUSAL["not_receipt"])
        await _say(update, ctx, text.format(amount=f"{float(info['amount']):g}", ref=to),
                   reply_markup=_pay_kb())
        return ST_PAY
    u = update.effective_user
    customer = info.get("customer") or (u.first_name or "")
    fname = pay.save_receipt(data, f"bpay_{bid}")
    pid = db.create_bot_payment(bid, info.get("order"), u.id, customer, info["amount"], fname,
                                img_hash, media.file_id, json.dumps(ac, ensure_ascii=False))
    await _say(update, ctx, "✅ وصلنا إيصال التحويل — هنراجعه ونأكدلك الطلب في أقرب وقت.",
               reply_markup=ReplyKeyboardRemove())
    owner = _cfg(ctx).get("owner_chat_id")
    if owner:
        caption = (f"💳 إيصال دفع لطلب #{info.get('order')}\n👤 {customer}\n"
                   f"💰 {float(info['amount']):g} ج\n{pay.verdict_label(ac.get('verdict'), 'ar')}\n\n"
                   "راجع حسابك: هل وصلك المبلغ فعلاً؟")
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("✅ تأكيد الدفع", callback_data=f"bp:ok:{pid}"),
                                    InlineKeyboardButton("❌ رفض", callback_data=f"bp:no:{pid}")]])
        try:
            send = ctx.bot.send_photo if msg.photo else ctx.bot.send_document
            await send(int(owner), media.file_id, caption=caption[:1024], reply_markup=kb)
        except Exception:
            log.exception("could not send the receipt of payment #%s to the owner", pid)
    ctx.user_data.clear()
    return ConversationHandler.END

async def on_pay_text(update, ctx):
    """نص بدل صورة الإيصال: إلغاء الطلب، أو تذكير بإرسال الصورة."""
    if (update.message.text or "").strip() in (PAY_CANCEL, "إلغاء", "الغاء"):
        order = (ctx.user_data.get("pay") or {}).get("order")
        if order:
            db.set_order_pay_status(order, "cancelled")
        await _say(update, ctx, "تم إلغاء الطلب. /start للبدء من جديد.", reply_markup=ReplyKeyboardRemove())
        ctx.user_data.clear()
        return ConversationHandler.END
    await _say(update, ctx, "📸 مستنيين صورة إيصال التحويل — أو اضغط «إلغاء الطلب».",
               reply_markup=_pay_kb())
    return ST_PAY

async def on_pay_decision(update, ctx):
    """زرّا صاحب البوت على إيصال العميل. القرار ذرّي (decide_bot_payment) فالضغطة المكررة
    — أو زرّ مع اللوحة — لا تُحتسب مرتين، والعميل يُبلَّغ بالنتيجة."""
    q = update.callback_query
    owner = str(_cfg(ctx).get("owner_chat_id") or "")
    # الإجابة بعد فحص الصلاحية: تليجرام يقبل إجابة واحدة، والمبكرة تبتلع «غير مسموح»
    if not owner or str(q.from_user.id) != owner:
        await q.answer("غير مسموح", show_alert=True)
        return
    await q.answer()
    _, act, sid = q.data.split(":")
    row = db.decide_bot_payment(int(sid), _bid(ctx), "approved" if act == "ok" else "rejected")
    if not row:
        tail = "\n\n⚠️ سبق البتّ في هذه الدفعة."
    else:
        text = pay_decision_text(row)
        try:
            await ctx.bot.send_message(int(row["tg_user_id"]), text)
            db.log_message(_bid(ctx), f"tg:{row['tg_user_id']}", "out", "bot", text)
        except Exception:
            log.exception("could not tell the customer about payment #%s", sid)
        tail = ("\n\n✅ تم تأكيد الدفع وإبلاغ العميل." if row["status"] == "approved"
                else "\n\n❌ تم الرفض وإبلاغ العميل.")
    try:
        await q.edit_message_caption(caption=(q.message.caption or "") + tail)
    except Exception:
        pass

# ---------- متجر ----------
ST_MENU, ST_QTY, ST_NAME, ST_PHONE, ST_ADDR, ST_CONFIRM = range(10, 16)
ST_PAY = 16                                  # ينتظر صورة إيصال التحويل (إضافة التحصيل)

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
            await _say(update, ctx, "⚠️ لا توجد منتجات بعد.")
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
                await _say(update, ctx, "سلتك فارغة."); return ST_MENU
            await _say(update, ctx, "👤 اكتب اسمك:", reply_markup=ReplyKeyboardRemove()); return ST_NAME
        try: idx = int(t.split(".")[0]) - 1
        except Exception: idx = -1
        ps = prods(ctx)
        if not (0 <= idx < len(ps)):
            await _say(update, ctx, "اختر منتجاً من القائمة."); return ST_MENU
        ctx.user_data["pending"] = ps[idx]
        if ps[idx].get("image"):
            try: await _photo(update, ctx, ps[idx]["image"])
            except Exception: pass
        await _say(update, ctx, f"كم عدد «{ps[idx]['name']}»؟", reply_markup=ReplyKeyboardRemove())
        return ST_QTY

    async def qty(update, ctx):
        try:
            n = int(update.message.text.strip()); assert 0 < n <= 999
        except Exception:
            await _say(update, ctx, "اكتب رقماً صحيحاً:"); return ST_QTY
        p = ctx.user_data.pop("pending")
        ctx.user_data["cart"].append({"name": p["name"], "price": p["price"], "qty": n})
        tot = sum(i["price"]*i["qty"] for i in ctx.user_data["cart"])
        await _say(update, ctx, f"✅ أضيف. إجمالي السلة: {tot} ج", reply_markup=menu_kb(ctx))
        return ST_MENU

    async def name(update, ctx):
        ctx.user_data["c_name"] = update.message.text.strip()
        await _say(update, ctx, "📱 رقم التليفون:"); return ST_PHONE
    async def phone(update, ctx):
        ctx.user_data["c_phone"] = update.message.text.strip()
        await _say(update, ctx, "📍 العنوان بالتفصيل:"); return ST_ADDR
    async def addr(update, ctx):
        ctx.user_data["c_addr"] = update.message.text.strip()
        cart = ctx.user_data["cart"]; tot = sum(i["price"]*i["qty"] for i in cart)
        lines = "\n".join(f"• {i['name']} × {i['qty']} = {i['price']*i['qty']} ج" for i in cart)
        await _say(update, ctx, 
            f"📋 تأكيد الطلب:\n{lines}\n\n💰 الإجمالي: {tot} ج\n\nاكتب «تأكيد» أو «إلغاء».",
            reply_markup=ReplyKeyboardMarkup([["تأكيد", "إلغاء"]], resize_keyboard=True))
        return ST_CONFIRM

    async def confirm(update, ctx):
        if update.message.text.strip() != "تأكيد": return await cancel(update, ctx)
        cart = ctx.user_data["cart"]; tot = sum(i["price"]*i["qty"] for i in cart)
        u = update.effective_user
        pay_on = pay_enabled(ctx)                # إضافة التحصيل سارية ولصاحبه وسيلة استلام
        order_id = db.add_order(_bid(ctx), u.id, ctx.user_data.get("c_name"), ctx.user_data.get("c_phone"),
                                ctx.user_data.get("c_addr"), cart, tot,
                                pay_status="awaiting" if pay_on else None)
        if pay_on:
            await _say(update, ctx, pay_instructions(_cfg(ctx).get("pay") or {}, tot, order_id),
                       reply_markup=_pay_kb())
        else:
            await _say(update, ctx,
                _cfg(ctx).get("thanks") or "🎉 تم استلام طلبك! هنتواصل لتأكيد التوصيل.",
                reply_markup=ReplyKeyboardRemove())
        lines = "\n".join(f"• {i['name']} × {i['qty']}" for i in cart)
        await _tell_owner(ctx, f"🛒 طلب جديد #{order_id} «{_cfg(ctx).get('business_name','')}»\n"
                               f"👤 {ctx.user_data.get('c_name')}\n📱 {ctx.user_data.get('c_phone')}\n"
                               f"📍 {ctx.user_data.get('c_addr')}\n{lines}\n💰 {tot} ج"
                               + ("\n💳 في انتظار إيصال الدفع" if pay_on else ""))
        customer = ctx.user_data.get("c_name")
        ctx.user_data.clear()
        if pay_on:
            ctx.user_data["pay"] = {"order": order_id, "amount": tot, "customer": customer}
            return ST_PAY
        return ConversationHandler.END

    async def cancel(update, ctx):
        await _say(update, ctx, "تم الإلغاء. /start للبدء.", reply_markup=ReplyKeyboardRemove())
        ctx.user_data.clear(); return ConversationHandler.END

    app.add_handler(ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={ST_MENU:[MessageHandler(filters.TEXT & ~filters.COMMAND, choose)],
                ST_QTY:[MessageHandler(filters.TEXT & ~filters.COMMAND, qty)],
                ST_NAME:[MessageHandler(filters.TEXT & ~filters.COMMAND, name)],
                ST_PHONE:[MessageHandler(filters.TEXT & ~filters.COMMAND, phone)],
                ST_ADDR:[MessageHandler(filters.TEXT & ~filters.COMMAND, addr)],
                ST_CONFIRM:[MessageHandler(filters.TEXT & ~filters.COMMAND, confirm)],
                ST_PAY:[MessageHandler(filters.PHOTO | filters.Document.IMAGE, on_receipt),
                        MessageHandler(filters.TEXT & ~filters.COMMAND, on_pay_text)]},
        fallbacks=[CommandHandler("cancel", cancel)],
        # /start يبدأ من جديد في أي خطوة — بدونه كان العميل العالق لا يخرج إلا بـ /cancel
        allow_reentry=True))
    # زرّا صاحب البوت على الإيصال — خارج المحادثة (يصلان من محادثته هو لا من العميل)
    app.add_handler(CallbackQueryHandler(on_pay_decision, pattern=r"^bp:(ok|no):\d+$"))

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
            await _say(update, ctx, "⚠️ لا توجد مواعيد متاحة حالياً.")
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
            await _say(update, ctx, "اختر يوماً من القائمة."); return BK_DATE
        ctx.user_data["date"] = t
        rows = [[tm] for tm in s[t]] + [["❌ إلغاء"]]
        await _say(update, ctx, "⏰ اختر الوقت:", reply_markup=ReplyKeyboardMarkup(rows, resize_keyboard=True))
        return BK_TIME

    async def pick_time(update, ctx):
        t = update.message.text.strip()
        if t == "❌ إلغاء": return await cancel(update, ctx)
        s = ctx.user_data.get("slots", {}); date = ctx.user_data.get("date")
        if t not in s.get(date, []):
            await _say(update, ctx, "اختر وقتاً من القائمة."); return BK_TIME
        ctx.user_data["time"] = t
        await _say(update, ctx, "👤 اكتب اسمك:", reply_markup=ReplyKeyboardRemove())
        return BK_NAME

    async def get_name(update, ctx):
        ctx.user_data["b_name"] = update.message.text.strip()
        await _say(update, ctx, "📱 رقم تليفونك:"); return BK_PHONE

    async def get_phone(update, ctx):
        ctx.user_data["b_phone"] = update.message.text.strip()
        slot = f"{ctx.user_data['date']} {ctx.user_data['time']}"
        u = update.effective_user
        ok = db.book_slot(_bid(ctx), u.id, ctx.user_data.get("b_name"),
                          ctx.user_data.get("b_phone"), _cfg(ctx).get("service_name",""), slot)
        if not ok:
            await _say(update, ctx, "⚠️ عذراً، تم حجز هذا الموعد للتو. أرسل /start لاختيار موعد آخر.",
                                            reply_markup=ReplyKeyboardRemove())
            ctx.user_data.clear(); return ConversationHandler.END
        await _say(update, ctx, 
            (_cfg(ctx).get("thanks") or "✅ تم تأكيد حجزك!") + f"\n🗓️ {slot}",
            reply_markup=ReplyKeyboardRemove())
        await _tell_owner(ctx, f"📅 حجز جديد «{_cfg(ctx).get('business_name','')}»\n"
                                f"👤 {ctx.user_data.get('b_name')}\n📱 {ctx.user_data.get('b_phone')}\n🗓️ {slot}")
        ctx.user_data.clear(); return ConversationHandler.END

    async def cancel(update, ctx):
        await _say(update, ctx, "تم الإلغاء. /start للبدء.", reply_markup=ReplyKeyboardRemove())
        ctx.user_data.clear(); return ConversationHandler.END

    app.add_handler(ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={BK_DATE:[MessageHandler(filters.TEXT & ~filters.COMMAND, pick_date)],
                BK_TIME:[MessageHandler(filters.TEXT & ~filters.COMMAND, pick_time)],
                BK_NAME:[MessageHandler(filters.TEXT & ~filters.COMMAND, get_name)],
                BK_PHONE:[MessageHandler(filters.TEXT & ~filters.COMMAND, get_phone)]},
        fallbacks=[CommandHandler("cancel", cancel)]))


# ---------- قائمة / أسئلة شائعة (menu) ----------
MENU_STATE = 30
def build_menu(app: Application):
    """بوت قائمة: يعرض أزرار، وعند الضغط يرد بالإجابة، ويكرّر. مثالي للأسئلة الشائعة والروابط."""
    def items(ctx): return _cfg(ctx).get("menu_items", [])
    def kb(ctx):
        rows = [[it["q"]] for it in items(ctx) if it.get("q")]
        rows.append(["🔚 إنهاء"])
        return ReplyKeyboardMarkup(rows, resize_keyboard=True)

    async def start(update, ctx):
        await track_start(update, ctx)
        if not items(ctx):
            await _say(update, ctx, "⚠️ لم تُضَف عناصر بعد.")
            return ConversationHandler.END
        await send_intro(update, ctx,
            _cfg(ctx).get("welcome") or f"👋 أهلاً بك في «{_cfg(ctx).get('business_name','')}»! اختر من القائمة:",
            kb(ctx))
        return MENU_STATE

    async def pick(update, ctx):
        t = (update.message.text or "").strip()
        if t.startswith("🔚"):
            await _say(update, ctx, _cfg(ctx).get("thanks") or "شكراً لتواصلك! 🙏",
                                            reply_markup=ReplyKeyboardRemove())
            return ConversationHandler.END
        for it in items(ctx):
            if it.get("q") == t:
                await _say(update, ctx, it.get("a") or "—")
                return MENU_STATE
        await _say(update, ctx, "اختر عنصراً من الأزرار.", reply_markup=kb(ctx))
        return MENU_STATE

    async def cancel(update, ctx):
        await _say(update, ctx, "تم الإنهاء. /start للبدء.", reply_markup=ReplyKeyboardRemove())
        return ConversationHandler.END

    app.add_handler(ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={MENU_STATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, pick)]},
        fallbacks=[CommandHandler("cancel", cancel)]))


# ---------- الفلوهات الافتراضية للأنواع الجديدة ----------
PRESET_FLOWS = {
    "feedback": {
        "start_message": "🌟 رأيك يهمّنا! ساعدنا نتحسّن في أقل من دقيقة.",
        "steps": [
            {"id": "s0", "type": "buttons", "prompt": "كيف تقيّم تجربتك معنا؟", "var": "التقييم",
             "options": ["⭐ ممتاز", "🙂 جيد", "😐 مقبول", "☹️ سيئ"]},
            {"id": "s1", "type": "question", "prompt": "✍️ اكتب ملاحظاتك أو اقتراحاتك:", "var": "الملاحظات"},
            {"id": "s2", "type": "question", "prompt": "📱 رقمك للتواصل (اختياري):", "var": "التليفون"},
        ],
        "end_message": "🙏 شكراً لوقتك! رأيك وصلنا وهنستفيد منه.",
    },
    "support": {
        "start_message": "🛠️ أهلاً بك في الدعم الفني. هنساعدك خطوة بخطوة.",
        "steps": [
            {"id": "s0", "type": "question", "prompt": "📝 اسمك:", "var": "الاسم"},
            {"id": "s1", "type": "buttons", "prompt": "نوع المشكلة؟", "var": "النوع",
             "options": ["مشكلة تقنية", "استفسار", "شكوى", "أخرى"]},
            {"id": "s2", "type": "question", "prompt": "🔎 اشرح المشكلة بالتفصيل:", "var": "التفاصيل"},
            {"id": "s3", "type": "question", "prompt": "📱 رقم للتواصل:", "var": "التليفون"},
        ],
        "end_message": "✅ تم فتح تذكرتك! فريق الدعم هيتواصل معك في أقرب وقت.",
    },
}

DEFAULT_MENU_ITEMS = [
    {"q": "🕐 مواعيد العمل", "a": "نعمل يومياً من 10 صباحاً حتى 10 مساءً."},
    {"q": "📍 العنوان", "a": "أضف عنوانك هنا من إعدادات البوت."},
    {"q": "📞 التواصل", "a": "للتواصل: أضف رقمك هنا من إعدادات البوت."},
]

def initial_config(name, template, info=None, owner_chat_id=""):
    """إعدادات البوت عند إنشائه — مصدر واحد للإنشاء اليدوي (توكن من BotFather)
    والإنشاء بضغطة (Managed Bots)، فلا يختلف بوتان بحسب طريقة إنشائهما."""
    import json as _json
    info = info or {}
    cfg = {"business_name": name, "owner_chat_id": (owner_chat_id or "").strip(),
           "welcome": "", "thanks": "", "products": [],
           "service_name": name, "days_ahead": 7, "open_hour": 10, "close_hour": 22,
           "slot_minutes": 60, "working_days": None, "flow": None, "welcome_image": "",
           "menu_items": [], "bot_username": info.get("username"), "bot_name": info.get("name"),
           "pending_owner_code": None}
    # قوالب ثابتة جاهزة حسب النوع — نسخة قابلة للتعديل لا مرجع مشترك
    if template in PRESET_FLOWS:
        cfg["flow"] = _json.loads(_json.dumps(PRESET_FLOWS[template]))
    if template == "faq":
        cfg["menu_items"] = _json.loads(_json.dumps(DEFAULT_MENU_ITEMS))
    return cfg


TEMPLATES = {
    "flow":             {"label": "باني محادثات (No-Code)", "build": build_flow,     "icon": "🧩"},
    "store":            {"label": "متجر صغير",              "build": build_store,    "icon": "🛍️"},
    "booking":          {"label": "حجوزات ومواعيد",         "build": build_booking,  "icon": "📅"},
    "customer_service": {"label": "خدمة عملاء",             "build": build_flow,     "icon": "📞"},
    "faq":              {"label": "أسئلة شائعة / قائمة",     "build": build_menu,     "icon": "❓"},
    "feedback":         {"label": "تقييم وآراء",            "build": build_flow,     "icon": "⭐"},
    "support":          {"label": "دعم فني / تذاكر",        "build": build_flow,     "icon": "🛟"},
}
