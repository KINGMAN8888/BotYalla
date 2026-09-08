"""محرك الفلو العام (No-Code) — يشغّل أي بوت مبني من باني المحادثات.
الفلو محفوظ في config['flow'] = {start_message, steps:[...], end_message}.
كل خطوة: {type: 'question'|'buttons'|'message', prompt, var, options?}.

المحرك نفسه لا يعرف تليجرام ولا واتساب: يتعامل مع Channel مجرّد،
وحالة المحادثة محفوظة في جدول chat_state لا في الذاكرة."""
import json, logging
from telegram import Update
from telegram.ext import (Application, CommandHandler, MessageHandler,
                          filters, ContextTypes)
import database as db
import tg_helpers as tg
from channels.telegram import TelegramChannel

log = logging.getLogger("flow_engine")

DEFAULT_CS_FLOW = {
    "start_message": "👋 أهلاً بك! هجمع منك بعض البيانات بسرعة.",
    "steps": [
        {"id": "name",  "type": "question", "prompt": "📝 اكتب اسمك:",        "var": "الاسم"},
        {"id": "phone", "type": "question", "prompt": "📱 رقم تليفونك:",       "var": "التليفون"},
        {"id": "msg",   "type": "question", "prompt": "✍️ اكتب استفسارك:",     "var": "الرسالة"},
    ],
    "end_message": "✅ تم استلام طلبك وسنتواصل معك قريباً. شكراً لك!",
}


def _peer_num(peer):
    """tg:123 -> 123 · wa:2010… -> 2010… (يُخزَّن في bot_users.tg_user_id)."""
    tail = peer.split(":")[-1] if ":" in peer else peer
    return int(tail) if tail.lstrip("+").isdigit() else 0


def _cfg_of(bot_row):
    return json.loads(bot_row.get("config_json") or "{}")


async def notify_owner(bot_row, channel, text):
    """يبلّغ صاحب البوت بإدخال جديد.
    بوت تليجرام: عبر نفس البوت (بلا إنشاء Bot جديد يسرّب اتصالاً كل مرة).
    بوت واتساب: صاحبه مربوط على تليجرام، فالتبليغ يمرّ ببوت المنصة."""
    owner = _cfg_of(bot_row).get("owner_chat_id")
    is_tg = (bot_row.get("channel") or "telegram") == "telegram"
    if not owner and not is_tg:
        # بوت واتساب لا يملك رابط ربط مثل تليجرام — نرجع لحساب المالك المربوط
        # على تليجرام من صفحة «حسابي»، وإلا فلا وسيلة تبليغ.
        owner = db.user_tg_channel(bot_row.get("owner_id"))
    if not owner:
        return
    try:
        if is_tg:
            await channel.send_text(f"tg:{owner}", text)
        else:
            import bot_manager
            await bot_manager.manager.notify_text_async(owner, text)
    except Exception:
        log.exception("notify_owner failed for bot #%s", bot_row.get("id"))


async def handle_message(bot_row, channel, msg):
    """محرك الفلو المجرد — لا يعرف تليجرام ولا واتساب."""
    bot_row = dict(bot_row)          # قد يصل sqlite3.Row وهو بلا .get()
    bot_id = bot_row["id"]
    peer = msg["peer"]
    cfg = _cfg_of(bot_row)
    f = cfg.get("flow") or DEFAULT_CS_FLOW
    steps = f.get("steps", [])

    if msg["kind"] == "cancel":
        db.clear_chat_state(bot_id, peer)
        await channel.remove_keyboard(peer, "تم الإلغاء. للبدء أرسل من جديد.")
        return

    if msg["kind"] == "unsupported":
        # موقع أو جهة اتصال: لا نص ولا ملف. حفظها كإجابة فارغة يقفز خطوة
        # ويُفسد الـ lead — نطلب نصاً ونبقى في نفس الخطوة.
        db.touch_bot_user(bot_id, peer)
        await channel.send_text(peer, "📝 من فضلك أرسل إجابتك كنص.")
        return

    if msg["kind"] != "start":
        state = db.get_chat_state(bot_id, peer)
        if state:
            db.touch_bot_user(bot_id, peer)
            return await _on_input(bot_row, channel, peer, f, steps, state, msg)
        # لا حالة محفوظة. أول تفاعل → نبدأ الفلو. أما من أنهى الفلو من قبل
        # فلا نعيد تشغيله عليه لمجرد أنه كتب «شكراً» — نذكّره كيف يبدأ.
        if db.bot_user_exists(bot_id, peer):
            db.touch_bot_user(bot_id, peer)
            word = "/start" if (bot_row.get("channel") or "telegram") == "telegram" else "start"
            await channel.send_text(peer, f"للبدء من جديد أرسل: {word}")
            return

    db.add_bot_user(bot_id, _peer_num(peer), msg.get("name", ""), peer=peer)
    db.log_event(bot_id, "start")
    db.set_chat_state(bot_id, peer, 0, {})

    start_msg = f.get("start_message")
    if start_msg:
        img = cfg.get("welcome_image")
        if img:
            await channel.send_image(peer, img, caption=start_msg)
        else:
            await channel.remove_keyboard(peer, start_msg)

    await _present(bot_row, channel, peer, f, steps, 0, {})


async def _on_input(bot_row, channel, peer, f, steps, state, msg):
    bot_id = bot_row["id"]
    i, data = state["step"], state["data"]
    if i >= len(steps):
        return await _finish(bot_row, channel, peer, f, data)

    step = steps[i]
    stype = step.get("type")
    ans = msg["text"]

    if stype == "media":
        if msg["kind"] != "media":
            await channel.send_text(peer, step.get("hint") or "📎 من فضلك أرسل الملف نفسه.")
            return
        ans = await _store_media(bot_row, channel, peer, msg)
        if ans is None:
            return                       # الرسالة أُرسلت للعميل داخل _store_media
    elif msg["kind"] == "media":
        # وسائط في خطوة نصية: نقبل التعليق إن وُجد، ولا نحفظ ملفاً لم يُطلب
        # (القرص مورد محدود، وحفظ كل ما يصل بابُ إغراق).
        if not ans:
            await channel.send_text(peer, "📝 هذه الخطوة تحتاج إجابة نصية.")
            return

    opts = step.get("options") or []
    if stype == "buttons" and opts and ans not in opts:
        # واتساب يعرض الخيارات الطويلة كقائمة مرقّمة، فنقبل الرقم كإجابة.
        if ans.strip().isdigit() and 1 <= int(ans.strip()) <= len(opts):
            ans = opts[int(ans.strip()) - 1]
        else:
            await channel.send_text(peer, "↩️ من فضلك اختر من الأزرار المتاحة.")
            return

    data[step.get("var") or step.get("id")] = ans
    db.set_chat_state(bot_id, peer, i + 1, data)
    await _present(bot_row, channel, peer, f, steps, i + 1, data)


MEDIA_ERRORS = {
    "quota": "⚠️ انتهى حدّ الملفات المسموح لهذا الشهر. تواصل مع صاحب النشاط.",
    "too_large": "⚠️ الملف كبير جداً — أرسل نسخة أصغر.",
    "too_small": "⚠️ الملف صغير جداً أو فارغ.",
    "type": "⚠️ نوع الملف غير مدعوم. أرسل صورة أو تسجيلاً صوتياً.",
    "disk": "⚠️ تعذّر حفظ الملف الآن. حاول بعد قليل.",
    "download": "⚠️ تعذّر تحميل الملف. أرسله مرة أخرى.",
}


async def _store_media(bot_row, channel, peer, msg):
    """ينزّل الملف ويحفظه. يرجّع مرجعاً يُخزَّن في الـ lead، أو None بعد إبلاغ العميل."""
    import media_store, plans
    owner_id = bot_row["owner_id"]
    owner = db.get_user(owner_id) or {}
    sub = db.get_subscription(owner_id)
    plan_id = sub["plan"] if sub and sub.get("status") == "active" else "free"
    quota = media_store.quota_left(owner_id, owner.get("role", "user"), plan_id)

    if quota is not None and quota <= 0:
        await channel.send_text(peer, MEDIA_ERRORS["quota"])
        log.warning("media quota exhausted for owner #%s", owner_id)
        return None

    data, mime = await channel.fetch_media(msg.get("media") or {})
    if not data:
        await channel.send_text(peer, MEDIA_ERRORS["download"])
        return None

    res = media_store.save(bot_row, peer, data, declared_mime=mime,
                           caption=msg.get("text", ""), quota=quota)
    if not res.get("ok"):
        await channel.send_text(peer, MEDIA_ERRORS.get(res.get("reason"), MEDIA_ERRORS["disk"]))
        return None

    caption = (msg.get("text") or "").strip()
    return f"media:{res['id']}" + (f" — {caption}" if caption else "")


async def _present(bot_row, channel, peer, f, steps, i, data):
    bot_id = bot_row["id"]

    # خطوات الرسالة النصية لا تنتظر إدخالاً — تُعرض ثم نتخطاها
    while i < len(steps) and steps[i].get("type") == "message":
        await channel.remove_keyboard(peer, steps[i].get("prompt", ""))
        i += 1
        db.set_chat_state(bot_id, peer, i, data)

    if i >= len(steps):
        return await _finish(bot_row, channel, peer, f, data)

    step = steps[i]
    stype = step.get("type")
    if stype == "buttons" and step.get("options"):
        await channel.send_buttons(peer, step.get("prompt", "اختر:"), step["options"])
    elif stype == "media":
        await channel.remove_keyboard(peer, step.get("prompt", "📎 أرسل الملف:"))
    else:
        await channel.remove_keyboard(peer, step.get("prompt", "اكتب:"))


async def _finish(bot_row, channel, peer, f, data):
    bot_id = bot_row["id"]
    cfg = _cfg_of(bot_row)

    lead_id = db.add_lead(bot_id, _peer_num(peer), data)
    # الملفات وصلت أثناء المحادثة قبل وجود الـ lead — تُربط به الآن،
    # وما يبقى بلا lead هو محادثة لم تكتمل ويُنظَّف دورياً.
    db.attach_media_to_lead(bot_id, peer, lead_id)
    db.clear_chat_state(bot_id, peer)
    await channel.remove_keyboard(peer, f.get("end_message", "✅ تم الاستلام، شكراً لك!"))

    if data:
        lines = "\n".join(f"• {k}: {v}" for k, v in data.items())
        await notify_owner(bot_row, channel,
                           f"🔔 إدخال جديد على «{cfg.get('business_name','')}»\n{lines}")


def build_flow(app: Application):
    """ربط تليجرام بالمحرك المجرد.
    ملاحظة: لا نستخدم MessageHandler شاملاً للأوامر — فهو يبتلع /id و/owner
    المسجَّلين بعده في نفس المجموعة، ويُفقد ctx.args اللازم لرابط ربط المالك."""
    async def _run(update: Update, ctx: ContextTypes.DEFAULT_TYPE, kind=None):
        channel = TelegramChannel(ctx.bot)
        msg = channel.normalize(update)
        if not msg:
            return
        if kind:
            msg["kind"] = kind
        bot_row = db.get_bot(ctx.application.bot_data["bot_id"])
        if not bot_row:
            return
        await handle_message(bot_row, channel, msg)

    async def on_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        # /start owner-CODE يربط صاحب البوت — CommandHandler وحده يملأ ctx.args
        if await tg.try_claim_owner(update, ctx):
            return
        await _run(update, ctx, "start")

    async def on_cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        await _run(update, ctx, "cancel")

    async def on_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        await _run(update, ctx)

    app.add_handler(CommandHandler("start", on_start))
    app.add_handler(CommandHandler("cancel", on_cancel))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))


# دوال منطقية قابلة للاختبار بدون تليجرام
def compute_next(step_index, steps):
    i = step_index
    while i < len(steps) and steps[i].get("type") == "message":
        i += 1
    return i


# متوافقة مع الاستدعاءات القديمة في templates_bot.py
def _cfg(ctx):  return ctx.application.bot_data.get("config", {})
def _bid(ctx):  return ctx.application.bot_data.get("bot_id")

async def track_start(update, ctx):
    u = update.effective_user
    db.add_bot_user(_bid(ctx), u.id, u.first_name or "", peer=f"tg:{u.id}")
    db.log_event(_bid(ctx), "start")

async def send_intro(update, ctx, text, reply_markup=None):
    img = _cfg(ctx).get("welcome_image")
    if img:
        try:
            await update.message.reply_photo(img, caption=text, reply_markup=reply_markup)
            return
        except Exception:
            pass
    await update.message.reply_text(text, reply_markup=reply_markup)
