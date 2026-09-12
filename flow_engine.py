"""محرك الفلو العام (No-Code) — يشغّل أي بوت مبني من باني المحادثات.
الفلو محفوظ في config['flow'] = {start_message, steps:[...], end_message}.
كل خطوة: {type: 'question'|'buttons'|'message'|'media'|'show', prompt, var, options?, asset?}.
  · show: صورة/فيديو من مكتبة الوسائط، وبأزرار تحتها تصير «فيديو تفاعلي» ينتظر اختياراً.

المحرك نفسه لا يعرف تليجرام ولا واتساب: يتعامل مع Channel مجرّد،
وحالة المحادثة محفوظة في جدول chat_state لا في الذاكرة.

**أوضاع الرد** (`config.response_mode`):
  · flow   — الفلو كما هو (الافتراضي، كل الباقات).
  · hybrid — الفلو يجمع البيانات، والذكاء الاصطناعي يجيب أي سؤال حرّ خارجه.
  · ai     — الذكاء الاصطناعي يدير المحادثة كلها («عقل البوت») بأدوات تنفّذ فعلاً.
الوضعان الأخيران ميزة مدفوعة بحصة شهرية ثم المحفظة؛ نفادها أو تعطّل المزوّد يعيد
البوت للفلو تلقائياً — عميل يرد عليه فلو أفضل من عميل بلا رد.

**صاحب النشاط يتقدّم على الجميع:** محادثة «تولّاها» من صندوق الوارد لا يرد فيها بوت
ولا ذكاء اصطناعي، وتعود للبوت وحدها لو نسيها 12 ساعة."""
import asyncio, json, logging, re, time
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

RESPONSE_MODES = ("flow", "hybrid", "ai")
HUMAN_IDLE = 12 * 3600          # تولٍّ منسيّ يعود للبوت بعدها
START_SOURCES = ("qr", "link", "poster", "share")
AI_PRICE_FALLBACK = 25          # قرشاً للرد فوق الحصة — لو ضاع الإعداد


def _peer_num(peer):
    """tg:123 -> 123 · wa:2010… -> 2010… (يُخزَّن في bot_users.tg_user_id)."""
    tail = peer.split(":")[-1] if ":" in peer else peer
    return int(tail) if tail.lstrip("+").isdigit() else 0


def _cfg_of(bot_row):
    return json.loads(bot_row.get("config_json") or "{}")


# ------------------------------------------------------------ تسجيل الصادر
class LoggedChannel:
    """غلاف حول القناة يسجّل كل ما يُرسل في صندوق الوارد. المحرك يرسل عبره
    فلا يُنسى تسجيل رسالة في أي مسار. `sender` = bot | ai."""

    def __init__(self, inner, bot_id, sender="bot"):
        self._c, self._bot_id, self.sender = inner, bot_id, sender

    def _log(self, peer, text, res, kind="text"):
        # قناة واتساب ترجّع None حين يُرفض الإرسال (حدّ الباقة) — لا نسجّل ما لم يُرسَل
        if res is None and getattr(self._c, "phone_id", None) is not None:
            return
        try:
            db.log_message(self._bot_id, peer, "out", self.sender, text or "", kind=kind)
        except Exception:
            log.exception("could not log outbound message")

    async def send_text(self, peer, text):
        r = await self._c.send_text(peer, text)
        self._log(peer, text, r)
        return r

    async def send_buttons(self, peer, text, options):
        r = await self._c.send_buttons(peer, text, options)
        self._log(peer, text + "\n" + " · ".join(f"[{o}]" for o in options), r)
        return r

    async def send_image(self, peer, url, caption=None):
        r = await self._c.send_image(peer, url, caption=caption)
        self._log(peer, caption or "", r, "media")
        return r

    async def remove_keyboard(self, peer, text):
        r = await self._c.remove_keyboard(peer, text)
        self._log(peer, text, r)
        return r

    async def send_media(self, peer, asset, bot_id, caption=None, options=None):
        r = await self._c.send_media(peer, asset, bot_id, caption=caption, options=options)
        tail = (" · " + " · ".join(f"[{o}]" for o in options)) if options else ""
        self._log(peer, (caption or "") + tail, r, "media")
        return r

    async def send_typing(self, peer):
        fn = getattr(self._c, "send_typing", None)
        if fn:
            await fn(peer)

    async def fetch_media(self, media):
        return await self._c.fetch_media(media)


# ------------------------------------------------------------ إشعار المالك
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
    inner = channel._c if isinstance(channel, LoggedChannel) else channel
    try:
        if is_tg:
            # إشعار المالك ليس جزءاً من محادثة العميل — لا يُسجَّل في صندوق الوارد
            await inner.send_text(f"tg:{owner}", text)
        else:
            import bot_manager
            await bot_manager.manager.notify_text_async(owner, text)
    except Exception:
        log.exception("notify_owner failed for bot #%s", bot_row.get("id"))


# ------------------------------------------------------------ التولّي البشري
def human_active(bot_id, peer, conv=None):
    """هل صاحب النشاط متولٍّ هذه المحادثة الآن؟ تولٍّ نُسي أكثر من 12 ساعة
    يعود للبوت تلقائياً — عميل بلا رد أسوأ من بوت يرد."""
    conv = conv if conv is not None else db.get_conversation(bot_id, peer)
    if not conv or conv.get("mode") != "human":
        return False
    if (conv.get("human_at") or 0) + HUMAN_IDLE < time.time():
        db.set_conversation_mode(bot_id, peer, "bot")
        return False
    return True


async def notify_human_inbound(bot_row, channel, peer, text):
    """رسالة وصلت لمحادثة يتولّاها صاحب النشاط: تنبيه واحد لكل دفعة غير مقروءة
    (أول رسالة بعد آخر قراءة) — لا تنبيه لكل سطر."""
    conv = db.get_conversation(bot_row["id"], peer) or {}
    if int(conv.get("unread") or 0) != 1:
        return
    name = conv.get("name") or peer
    await notify_owner(bot_row, channel,
                       f"💬 رسالة جديدة من {name} في «{_cfg_of(bot_row).get('business_name', '')}»"
                       f" — المحادثة معك الآن:\n{(text or '📎')[:300]}")


async def _keep_inbox_media(bot_row, channel, peer, msg):
    """ملف أرسله عميل أثناء تولّي صاحب النشاط: يُحفظ ليراه في صندوق الوارد
    (بنفس الفحص والحصة)، وبصمت لو امتلأت الحصة — لا رسالة خطأ من بوت متوقف."""
    import media_store, plans
    try:
        owner_id = bot_row["owner_id"]
        owner = db.get_user(owner_id) or {}
        sub = db.get_subscription(owner_id)
        plan_id = sub["plan"] if sub and sub.get("status") == "active" else "free"
        quota = media_store.quota_left(owner_id, owner.get("role", "user"), plan_id)
        if quota is not None and quota <= 0:
            return None
        data, mime = await channel.fetch_media(msg.get("media") or {})
        if not data:
            return None
        res = media_store.save(bot_row, peer, data, declared_mime=mime,
                               caption=msg.get("text", ""), quota=quota)
        return res.get("id") if res.get("ok") else None
    except Exception:
        log.exception("inbox media store failed")
        return None


def _start_source(text):
    """/start src-qr → 'qr'. مصدر الدخول (QR · رابط · ملصق) يُحتسب في التحليلات."""
    parts = (text or "").split()
    if len(parts) > 1 and parts[1].startswith("src-") and parts[1][4:] in START_SOURCES:
        return parts[1][4:]
    return None


# ------------------------------------------------------------ وضع الرد
def ai_reply_price():
    """سعر رد الذكاء الاصطناعي فوق الحصة، بالقروش، من إعدادات المنصة."""
    try:
        v = int(str(db.get_platform("ai_reply_price", "") or "").strip() or 0)
    except (TypeError, ValueError):
        v = 0
    return v if v > 0 else AI_PRICE_FALLBACK


def _owner_ai_terms(bot_row):
    """(الحصة, السعر) لصاحب البوت. الحصة None = بلا حد (الأدمن والدعم)،
    و0 = باقته لا تتيح «عقل البوت» أصلاً."""
    import plans
    owner = db.get_user(bot_row["owner_id"]) or {}
    if owner.get("role") in ("admin", "support"):
        return None, 0
    sub = db.get_subscription(bot_row["owner_id"])
    pid = sub["plan"] if sub and sub.get("status") == "active" else "free"
    return plans.ai_replies_limit(pid), ai_reply_price()


def _mode_of(bot_row, cfg):
    mode = cfg.get("response_mode") or "flow"
    if mode not in RESPONSE_MODES or mode == "flow":
        return "flow"
    allowance, _ = _owner_ai_terms(bot_row)
    if allowance == 0:
        return "flow"                 # باقة لا تتيحه (انتهى الاشتراك مثلاً) — الفلو يرد
    return mode


def _ai_can_try(bot_row):
    """فحص رخيص قبل استدعاء مدفوع: هل تبقّت حصة أو رصيد يغطي رداً؟"""
    allowance, price = _owner_ai_terms(bot_row)
    if allowance is None:
        return True
    if allowance == 0:
        return False
    if db.ai_usage_of(bot_row["owner_id"])["replies"] < allowance:
        return True
    return price > 0 and db.wallet_balance(bot_row["owner_id"]) >= price


async def _ai_answer(bot_row, cfg, raw_channel, peer, text, extra=None):
    """يرد بالذكاء الاصطناعي. يرجّع True لو أُرسل رد، وإلا False ليرجع المستدعي للفلو.

    الحجز من الحصة/المحفظة يحدث **بعد** نجاح التوليد وقبل الإرسال مباشرة: فشل
    المزوّد لا يُحتسب على صاحب النشاط، ورد لم يُحجز له رصيد لا يُرسل أبداً."""
    import ai_agent
    key = db.get_platform("ai_key", "")
    if not key or not _ai_can_try(bot_row):
        return False
    provider = db.get_platform("ai_provider", "gemini")
    ch = LoggedChannel(raw_channel, bot_row["id"], "ai")
    await ch.send_typing(peer)
    history = db.recent_history(bot_row["id"], peer, 12)
    try:
        out = await asyncio.to_thread(ai_agent.brain_reply, cfg, bot_row, history, text,
                                      key, provider, extra)
    except Exception:
        log.exception("AI reply failed for bot #%s", bot_row["id"])
        return False
    reply = (out or {}).get("reply")
    if not reply:
        return False
    allowance, price = _owner_ai_terms(bot_row)
    grant = db.ai_reply_allow(bot_row["owner_id"], allowance, price, ref=f"ai:{bot_row['id']}")
    if not grant:
        log.info("AI reply dropped for bot #%s — allowance and wallet exhausted", bot_row["id"])
        return False
    await ch.send_text(peer, reply)
    try:
        await _ai_action(bot_row, cfg, raw_channel, peer, out.get("action"))
    except Exception:
        log.exception("AI action failed for bot #%s", bot_row["id"])
    return True


async def _ai_action(bot_row, cfg, raw_channel, peer, action):
    """الأدوات التي يطلبها النموذج تُنفَّذ هنا بعد التحقق — لا يكتب النموذج في
    القاعدة مباشرة، ولا يحدّد سعراً: مجموع الطلب يُحسب من أسعار المنتجات المحفوظة."""
    if not isinstance(action, dict):
        return
    kind = action.get("type")
    bot_id = bot_row["id"]
    biz = cfg.get("business_name", "")
    if kind == "lead":
        data = action.get("data") or {}
        if isinstance(data, dict) and data:
            lead_id = db.add_lead(bot_id, _peer_num(peer), data)
            db.attach_media_to_lead(bot_id, peer, lead_id)
            lines = "\n".join(f"• {k}: {v}" for k, v in data.items())
            await notify_owner(bot_row, raw_channel, f"🔔 عميل جديد عبر الذكاء الاصطناعي «{biz}»\n{lines}")
    elif kind == "order":
        prices = {str(p.get("name", "")).strip().lower(): p for p in (cfg.get("products") or [])}
        items = []
        for it in action.get("items") or []:
            p = prices.get(str(it.get("name", "")).strip().lower())
            try:
                qty = int(it.get("qty") or 1)
            except (TypeError, ValueError):
                qty = 1
            if p and 1 <= qty <= 99:
                items.append({"name": p["name"], "price": float(p.get("price") or 0), "qty": qty})
        if items:
            total = round(sum(i["price"] * i["qty"] for i in items), 2)
            db.add_order(bot_id, _peer_num(peer), action.get("customer"), action.get("phone"),
                         action.get("address"), items, total)
            lines = "\n".join(f"• {i['name']} × {i['qty']}" for i in items)
            await notify_owner(bot_row, raw_channel,
                               f"🛒 طلب جديد عبر الذكاء الاصطناعي «{biz}»\n👤 {action.get('customer') or '—'}"
                               f"\n📱 {action.get('phone') or '—'}\n📍 {action.get('address') or '—'}"
                               f"\n{lines}\n💰 {total:g} ج")
    elif kind == "handoff":
        db.set_conversation_mode(bot_id, peer, "human")
        conv = db.get_conversation(bot_id, peer) or {}
        await notify_owner(bot_row, raw_channel,
                           f"🙋 العميل {conv.get('name') or peer} في «{biz}» يطلب التحدث مع موظف."
                           f"\n{str(action.get('reason') or '')[:200]}\nافتح صندوق الوارد للرد عليه.")
    elif kind == "notify":
        await notify_owner(bot_row, raw_channel,
                           f"❓ سؤال لم يجد الذكاء الاصطناعي إجابته في «{biz}»:\n"
                           f"{str(action.get('note') or '')[:400]}")
    elif kind == "product":
        name = str(action.get("name", "")).strip().lower()
        for p in cfg.get("products") or []:
            if str(p.get("name", "")).strip().lower() == name:
                cap = f"{p['name']} — {p.get('price', '')} ج"
                ch = LoggedChannel(raw_channel, bot_id, "ai")
                asset = db.get_asset(p["asset"], owner_id=bot_row["owner_id"]) if p.get("asset") else None
                if asset:
                    await ch.send_media(peer, asset, bot_id, caption=cap)
                elif p.get("image"):
                    await ch.send_image(peer, p["image"], caption=cap)
                break


def _restart_word(bot_row):
    return "/start" if (bot_row.get("channel") or "telegram") == "telegram" else "start"


# ------------------------------------------------------------ نقطة الدخول
async def handle_message(bot_row, channel, msg):
    """محرك الفلو المجرد — لا يعرف تليجرام ولا واتساب."""
    bot_row = dict(bot_row)          # قد يصل sqlite3.Row وهو بلا .get()
    bot_id = bot_row["id"]
    peer = msg["peer"]
    cfg = _cfg_of(bot_row)
    f = cfg.get("flow") or DEFAULT_CS_FLOW
    steps = f.get("steps", [])
    raw = channel
    channel = LoggedChannel(raw, bot_id)

    # 1) كل رسالة واردة تُسجَّل أولاً — في كل وضع، وقبل أي قرار
    conv = db.get_conversation(bot_id, peer)
    human = human_active(bot_id, peer, conv)
    media_id = await _keep_inbox_media(bot_row, raw, peer, msg) \
        if human and msg["kind"] == "media" else None
    try:
        db.log_message(bot_id, peer, "in", "customer", msg.get("text", ""),
                       kind="media" if msg["kind"] == "media" else "text",
                       media_id=media_id, name=msg.get("name", ""))
    except Exception:
        log.exception("could not log inbound message")

    # 2) صاحب النشاط يتولّى المحادثة: لا بوت ولا ذكاء اصطناعي
    if human:
        db.add_bot_user(bot_id, _peer_num(peer), msg.get("name", ""), peer=peer)
        await notify_human_inbound(bot_row, raw, peer, msg.get("text") or "📎")
        return

    if msg["kind"] == "start":
        src = _start_source(msg.get("text", ""))
        if src:
            db.log_event(bot_id, f"src_{src}")

    mode = _mode_of(bot_row, cfg)
    if mode == "ai" and await _ai_mode(bot_row, cfg, raw, channel, peer, msg, f):
        return

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
            return await _on_input(bot_row, channel, peer, f, steps, state, msg, mode, raw, cfg)
        # لا حالة محفوظة. أول تفاعل → نبدأ الفلو. أما من أنهى الفلو من قبل
        # فلا نعيد تشغيله عليه لمجرد أنه كتب «شكراً» — نذكّره كيف يبدأ.
        if db.bot_user_exists(bot_id, peer):
            db.touch_bot_user(bot_id, peer)
            word = _restart_word(bot_row)
            # الوضع الهجين: سؤال حرّ بعد انتهاء الفلو يجيبه الذكاء الاصطناعي
            if (mode == "hybrid" and msg["kind"] == "text" and msg.get("text")
                    and await _ai_answer(bot_row, cfg, raw, peer, msg["text"],
                                         extra={"restart": word})):
                return
            await channel.send_text(peer, f"للبدء من جديد أرسل: {word}")
            return

    await _begin(bot_row, cfg, channel, peer, msg, f, steps)


async def _begin(bot_row, cfg, channel, peer, msg, f, steps):
    bot_id = bot_row["id"]
    db.add_bot_user(bot_id, _peer_num(peer), msg.get("name", ""), peer=peer)
    db.log_event(bot_id, "start")
    db.set_chat_state(bot_id, peer, 0, {})
    await _greet(bot_row, cfg, channel, peer, f.get("start_message"))
    await _present(bot_row, channel, peer, f, steps, 0, {})


async def _greet(bot_row, cfg, channel, peer, text):
    """رسالة البداية — بصورة/فيديو الترحيب من المكتبة إن وُجد، أو رابط صورة قديم."""
    if not text:
        return
    asset = _asset(bot_row, cfg.get("welcome_asset"))
    if asset:
        try:
            await channel.send_media(peer, asset, bot_row["id"], caption=text)
            return
        except Exception:
            log.exception("welcome media failed for bot #%s", bot_row["id"])
    img = cfg.get("welcome_image")
    if img:
        await channel.send_image(peer, img, caption=text)
    else:
        await channel.remove_keyboard(peer, text)


def _asset(bot_row, asset_id):
    """ملف من مكتبة صاحب البوت نفسه — الملكية شرط في الاستعلام."""
    if not asset_id:
        return None
    try:
        return db.get_asset(int(asset_id), owner_id=bot_row["owner_id"])
    except (TypeError, ValueError):
        return None


async def _ai_mode(bot_row, cfg, raw, channel, peer, msg, f):
    """«عقل البوت»: الذكاء الاصطناعي يدير المحادثة. يرجّع False ليرجع المحرك للفلو
    (لا مفتاح · نفدت الحصة والرصيد · تعطّل المزوّد)."""
    bot_id = bot_row["id"]
    kind = msg["kind"]
    if kind == "cancel":
        db.clear_chat_state(bot_id, peer)
        await channel.remove_keyboard(peer, "تم. أنا هنا لو احتجت أي حاجة 👋")
        return True
    if kind == "start":
        db.add_bot_user(bot_id, _peer_num(peer), msg.get("name", ""), peer=peer)
        db.log_event(bot_id, "start")
        db.clear_chat_state(bot_id, peer)
        greeting = (f.get("start_message") or cfg.get("welcome") or
                    f"👋 أهلاً بك في «{cfg.get('business_name', '')}»! اسألني عن أي حاجة.")
        await _greet(bot_row, cfg, channel, peer, greeting)
        return True
    if kind == "unsupported":
        await channel.send_text(peer, "📝 اكتب لي سؤالك أو طلبك نصاً وأنا أساعدك.")
        return True
    if kind == "media":
        await channel.send_text(peer, "📎 وصلني الملف. اكتب لي كمان طلبك أو سؤالك نصاً عشان أساعدك.")
        return True
    if db.get_chat_state(bot_id, peer):
        return False                  # عميل في منتصف فلو قديم — يكمله الفلو
    first = not db.bot_user_exists(bot_id, peer)
    db.add_bot_user(bot_id, _peer_num(peer), msg.get("name", ""), peer=peer)
    if first:
        db.log_event(bot_id, "start")
    return await _ai_answer(bot_row, cfg, raw, peer, msg.get("text", ""))


def _waits(step):
    """هل الخطوة تنتظر إجابة؟ message وshow بلا أزرار تُعرض ثم تُتخطّى."""
    t = step.get("type")
    if t == "message":
        return False
    if t == "show":
        return bool(step.get("options"))
    return True


async def _on_input(bot_row, channel, peer, f, steps, state, msg, mode="flow", raw=None, cfg=None):
    bot_id = bot_row["id"]
    i, data = state["step"], state["data"]
    if i >= len(steps):
        return await _finish(bot_row, channel, peer, f, data)

    step = steps[i]
    stype = step.get("type")
    ans = msg["text"]

    if stype == "media":
        if msg["kind"] != "media":
            # خطوة اختيارية («ابعت صورة التصميم — أو اكتب لا»): النص يُقبل ويتخطّاها
            if not (step.get("optional") and ans):
                await channel.send_text(peer, step.get("hint") or "📎 من فضلك أرسل الملف نفسه.")
                return
        else:
            ans = await _store_media(bot_row, channel, peer, msg)
            if ans is None:
                return                   # الرسالة أُرسلت للعميل داخل _store_media
    elif msg["kind"] == "media":
        # وسائط في خطوة نصية: نقبل التعليق إن وُجد، ولا نحفظ ملفاً لم يُطلب
        # (القرص مورد محدود، وحفظ كل ما يصل بابُ إغراق).
        if not ans:
            await channel.send_text(peer, "📝 هذه الخطوة تحتاج إجابة نصية.")
            return

    opts = step.get("options") or []
    if stype in ("buttons", "show") and opts and ans not in opts:
        # واتساب يعرض الخيارات الطويلة كقائمة مرقّمة، فنقبل الرقم كإجابة.
        if ans.strip().isdigit() and 1 <= int(ans.strip()) <= len(opts):
            ans = opts[int(ans.strip()) - 1]
        else:
            # الوضع الهجين: العميل سأل بدل أن يختار — نجيبه ثم نعيد عرض الخيارات
            if (mode == "hybrid" and raw is not None and ans
                    and await _ai_answer(bot_row, cfg or _cfg_of(bot_row), raw, peer, ans,
                                         extra={"step": step.get("prompt", "")})):
                await _present(bot_row, channel, peer, f, steps, i, data)
                return
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


async def _show(bot_row, channel, peer, step):
    """خطوة «عرض وسائط»: الملف بتعليقه وأزراره. ملف حُذف من المكتبة لا يوقف
    الفلو — يُرسل النص وحده (والأزرار إن وُجدت)."""
    opts = step.get("options") or None
    asset = _asset(bot_row, step.get("asset"))
    if asset:
        try:
            await channel.send_media(peer, asset, bot_row["id"], caption=step.get("prompt"),
                                     options=opts)
            return
        except Exception:
            log.exception("show step media failed for bot #%s", bot_row["id"])
    if opts:
        await channel.send_buttons(peer, step.get("prompt") or "👇", opts)
    elif step.get("prompt"):
        await channel.remove_keyboard(peer, step["prompt"])


async def _present(bot_row, channel, peer, f, steps, i, data):
    bot_id = bot_row["id"]

    # خطوات العرض (نص أو وسائط بلا أزرار) لا تنتظر إدخالاً — تُعرض ثم نتخطاها
    while i < len(steps) and not _waits(steps[i]):
        if steps[i].get("type") == "show":
            await _show(bot_row, channel, peer, steps[i])
        else:
            await channel.remove_keyboard(peer, steps[i].get("prompt", ""))
        i += 1
        db.set_chat_state(bot_id, peer, i, data)

    if i >= len(steps):
        return await _finish(bot_row, channel, peer, f, data)

    step = steps[i]
    stype = step.get("type")
    if stype == "show":
        await _show(bot_row, channel, peer, step)
    elif stype == "buttons" and step.get("options"):
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
    # النص **والوسائط**: خطوة «أرسل صورة» وصندوق الوارد يحتاجان الملفات أيضاً.
    # رسائل الخدمة (انضمام · تثبيت…) مستبعدة، والأوامر لمعالجاتها.
    app.add_handler(MessageHandler(~filters.COMMAND & ~filters.StatusUpdate.ALL, on_text))


# دوال منطقية قابلة للاختبار بدون تليجرام
def compute_next(step_index, steps):
    i = step_index
    while i < len(steps) and not _waits(steps[i]):
        i += 1
    return i


# متوافقة مع الاستدعاءات القديمة في templates_bot.py
def _cfg(ctx):  return ctx.application.bot_data.get("config", {})
def _bid(ctx):  return ctx.application.bot_data.get("bot_id")

async def track_start(update, ctx):
    u = update.effective_user
    db.add_bot_user(_bid(ctx), u.id, u.first_name or "", peer=f"tg:{u.id}")
    db.log_event(_bid(ctx), "start")
    src = _start_source(getattr(update.message, "text", "") or "")
    if src:
        db.log_event(_bid(ctx), f"src_{src}")

async def send_intro(update, ctx, text, reply_markup=None):
    cfg = _cfg(ctx)
    aid = cfg.get("welcome_asset")
    if aid:
        row = db.get_bot(_bid(ctx))
        asset = _asset(row, aid) if row else None
        if asset:
            try:
                await TelegramChannel(ctx.bot).send_media(
                    f"tg:{update.effective_chat.id}", asset, _bid(ctx), caption=text,
                    markup=reply_markup)
                return
            except Exception:
                log.exception("welcome media failed for bot #%s", _bid(ctx))
    img = cfg.get("welcome_image")
    if img:
        try:
            await update.message.reply_photo(img, caption=text, reply_markup=reply_markup)
            return
        except Exception:
            pass
    await update.message.reply_text(text, reply_markup=reply_markup)
