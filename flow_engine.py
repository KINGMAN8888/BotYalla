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
_BG = set()                     # مهام خلفية قصيرة (علامة القراءة) — مرجع يمنع جمعها قبل انتهائها
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
    import inbox_relay
    if await inbox_relay.alert(bot_row, peer, "💬 رسالة جديدة من عميل متولّي محادثته في"):
        return
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


def _note_ai(ok, err=None, key=""):
    """آخر نجاح/خطأ للذكاء الاصطناعي في إعدادات المنصة — الأدمن يرى سبب الفشل في
    صفحة الإعدادات بلا دخول للسيرفر. المفتاح يُحذف من الرسالة احتياطاً."""
    try:
        if ok:
            db.set_platform("ai_last_ok_at", str(int(time.time())))
        else:
            msg = f"{type(err).__name__}: {err}"[:300]
            for k in ([x.get("key", "") for x in key] if isinstance(key, list) else [key]):
                if k:
                    msg = msg.replace(k, "***")
            db.set_platform("ai_last_error", json.dumps({"at": int(time.time()), "msg": msg},
                                                        ensure_ascii=False))
    except Exception:
        log.exception("could not record AI status")


def _platform_facts(bot_row, cfg):
    """حقائق BotYalla الحيّة لبوت المنصة الرسمي فقط: الخيار مفعّل **و** صاحب البوت أدمن/دعم —
    فلا يستطيع عميل أن يجعل بوته يتكلّم باسم المنصة بتعديل إعداده."""
    if not cfg.get("platform_kb") or not db.bot_owner_is_staff(bot_row["id"]):
        return None
    try:
        import platform_kb
        return platform_kb.facts()
    except Exception:
        log.exception("platform facts failed for bot #%s", bot_row["id"])
        return None


def _lang_of(text):
    import ai_agent
    return "en" if ai_agent._is_en(text) else "ar"


def _welcome_of(bot_row, cfg, f, text=""):
    """رسالة البداية في وضع «عقل البوت» وأزرارها: ما كتبه صاحب البوت أولاً، ثم رسالة
    بوت المنصة الرسمي الجاهزة، ثم ترحيب الفلو القديم."""
    lang = _lang_of(text)
    official = bool(cfg.get("platform_kb")) and db.bot_owner_is_staff(bot_row["id"])
    kb = None
    if official:
        import platform_kb as kb
    text_ = ((cfg.get("ai_welcome") or "").strip() or (kb.welcome(lang) if kb else "") or
             f.get("start_message") or cfg.get("welcome") or
             f"👋 أهلاً بك في «{cfg.get('business_name', '')}»! اسألني عن أي حاجة.")
    opts = [s for s in (cfg.get("ai_starters") or []) if isinstance(s, str) and s.strip()]
    if not opts and kb:
        opts = kb.starters(lang)
    return text_, opts[:3]


# إيقاف الرسائل الترويجية — سياسة Meta: أي طلب إيقاف يُحترم فوراً وفي كل وضع.
# كلمات صريحة فقط: «إلغاء» وحدها تعني إلغاء النموذج الجاري لا الاشتراك.
OPT_OUT_WORDS = {"stop", "unsubscribe", "stop promotions", "optout", "opt out", "opt-out",
                 "إلغاء الاشتراك", "الغاء الاشتراك", "ايقاف الرسائل", "إيقاف الرسائل",
                 "ايقاف العروض", "إيقاف العروض", "وقف الرسائل", "وقف العروض"}
OPT_IN_WORDS = {"تفعيل العروض", "تفعيل الرسائل", "resume offers", "subscribe offers"}
OPT_TEXT = {
    ("out", "ar"): "✅ تم إيقاف الرسائل الترويجية، ومش هيوصلك مننا عروض تاني.\n"
                   "لو احتجت أي حاجة ابعتلنا في أي وقت، ولو حبيت ترجع للعروض ابعت «تفعيل العروض».",
    ("out", "en"): "✅ Done — you won't receive promotional messages from us anymore.\n"
                   "Message us any time you need help, or send «resume offers» to get offers again.",
    ("in", "ar"): "✅ تم تفعيل العروض من جديد. أهلاً بيك تاني 👋",
    ("in", "en"): "✅ Offers are back on. Welcome back 👋",
}


# ------------------------------------------------------------ الشكر والتقييم
# «شكراً» ليست سؤالاً: رد فوري بلا ذكاء اصطناعي (أسرع ومجاني)، ثم طلب تقييم بثلاثة أزرار
# مرة كل 24 ساعة. التقييم حدث `rating` (3 ممتاز · 2 كويس · 1 محتاج تحسين) في التحليلات،
# والسلبي يطلب ملاحظة تُحفظ عميلاً محتملاً وتصل صاحب البوت على تليجرام ليرد عليها.
_THANKS = ("شكرا", "شكر", "متشكر", "متشكرين", "تسلم", "تسلمي", "تسلموا", "ميرسي", "مرسي",
           "ربنا يخليك", "جزاك الله", "الله يعطيك العافيه", "thanks", "thank you", "thx", "ty",
           "مع السلامه", "باي", "bye", "goodbye")
RATING = {"ar": ["ممتاز 🌟", "كويس 👍", "محتاج تحسين"],
          "en": ["Excellent 🌟", "Good 👍", "Needs work"]}
_RATING_SCORE = {o: 3 - i for opts in RATING.values() for i, o in enumerate(opts)}
RATING_EVERY = 24 * 3600
RATING_WAIT = 3600               # زر تقييم يُقبل خلال ساعة من طلبه
COMMENT_WAIT = 15 * 60           # الملاحظة بعد تقييم سلبي
_rating_asked = {}
_comment_wait = {}


def _norm_ar(s):
    s = (s or "").strip().lower()
    for a, b in (("أ", "ا"), ("إ", "ا"), ("آ", "ا"), ("ة", "ه"), ("ى", "ي"), ("ـ", "")):
        s = s.replace(a, b)
    return re.sub(r"[ً-ْ!.،,؟?🙏❤️♥️😍🌹👍]+", " ", s).strip()


def is_thanks(text):
    """شكر/وداع قصير فقط — «شكراً بس بكام الباقة؟» سؤال يذهب للذكاء الاصطناعي."""
    t = _norm_ar(text)
    if not t or len(t) > 40 or "؟" in (text or "") or "?" in (text or ""):
        return False
    return any(w in t for w in _THANKS)


async def _closing(bot_row, cfg, channel, peer, text):
    """يرد على الشكر والتقييم وملاحظته. True = تم الرد ولا حاجة للذكاء الاصطناعي."""
    key, now = (bot_row["id"], peer), time.time()
    lang = _lang_of(text)
    raw = text.strip()
    if now - _comment_wait.get(key, 0) < COMMENT_WAIT and raw not in _RATING_SCORE:
        _comment_wait.pop(key, None)
        db.add_lead(bot_row["id"], _peer_num(peer), {"التقييم": "محتاج تحسين", "ملاحظة العميل": raw[:500]})
        import inbox_relay
        await inbox_relay.alert(bot_row, peer, "⚠️ تقييم سلبي وملاحظة من عميل في", raw[:200])
        await channel.remove_keyboard(peer, "Thanks — your note reached our team and we'll use it to improve 🙏"
                                      if lang == "en" else
                                      "وصلت ملاحظتك لفريقنا، وشكراً إنك بتساعدنا نتحسّن 🙏")
        return True
    if raw in _RATING_SCORE and now - _rating_asked.get(key, 0) < RATING_WAIT:
        score = _RATING_SCORE[raw]
        lang = "en" if raw in RATING["en"] else "ar"
        db.log_event(bot_row["id"], "rating", score)
        _rating_asked[key] = now - RATING_WAIT      # زر واحد يُحتسب — الضغطة الثانية سؤال عادي
        if score == 1:
            _comment_wait[key] = now
            await channel.remove_keyboard(peer, "Sorry it wasn't better 🙏 What should we improve?"
                                          if lang == "en" else
                                          "آسفين إن التجربة ماكانتش أحسن 🙏 قولنا إيه اللي نقدر نحسّنه؟")
        else:
            await channel.remove_keyboard(peer, "Thank you for the rating 🌟 We're always here for you."
                                          if lang == "en" else
                                          "شكراً لتقييمك 🌟 يسعدنا نخدمك دايماً.")
        return True
    if not is_thanks(raw):
        return False
    ask = cfg.get("ai_rating", True) is not False and now - _rating_asked.get(key, 0) > RATING_EVERY
    if ask:
        _rating_asked[key] = now
        await channel.send_buttons(peer, "You're welcome 🙏 Happy to help! How was your experience with us?"
                                   if lang == "en" else
                                   "العفو 🙏 سعدنا بخدمتك! قبل ما تمشي، قيّم تجربتك معانا:", RATING[lang])
    else:
        await channel.remove_keyboard(peer, "You're welcome 🙏 We're here any time."
                                      if lang == "en" else "العفو 🙏 تحت أمرك في أي وقت.")
    return True


async def _ai_answer(bot_row, cfg, raw_channel, peer, text, extra=None):
    """يرد بالذكاء الاصطناعي. يرجّع True لو أُرسل رد، وإلا False ليرجع المستدعي للفلو.

    الحجز من الحصة/المحفظة يحدث **بعد** نجاح التوليد وقبل الإرسال مباشرة: فشل
    المزوّد لا يُحتسب على صاحب النشاط، ورد لم يُحجز له رصيد لا يُرسل أبداً."""
    import ai_agent
    import ai_agent as _ai
    key = _ai.key_chain(db.get_platform)          # المزوّد الأساسي ثم الاحتياطي المجاني
    if not key:
        _note_ai(False, RuntimeError("no platform AI key — add it in /settings"))
        return False
    if not _ai_can_try(bot_row):
        return False
    provider = "auto"
    ch = LoggedChannel(raw_channel, bot_row["id"], "ai")
    await ch.send_typing(peer)
    history = db.recent_history(bot_row["id"], peer, 12)
    facts = _platform_facts(bot_row, cfg)
    if facts:
        extra = dict(extra or {}, platform=facts)
    try:
        out = await asyncio.to_thread(ai_agent.brain_reply, cfg, bot_row, history, text,
                                      key, provider, extra)
    except Exception as e:
        log.error("AI reply failed for bot #%s: %s", bot_row["id"], str(e)[:300])
        _note_ai(False, e, key)
        return False
    _note_ai(True)
    reply = (out or {}).get("reply")
    if not reply:
        return False
    allowance, price = _owner_ai_terms(bot_row)
    grant = db.ai_reply_allow(bot_row["owner_id"], allowance, price, ref=f"ai:{bot_row['id']}")
    if not grant:
        log.info("AI reply dropped for bot #%s — allowance and wallet exhausted", bot_row["id"])
        return False
    inner = raw_channel._c if isinstance(raw_channel, LoggedChannel) else raw_channel
    tips = (out or {}).get("suggestions") or []
    try:
        # أزرار الرد السريع: واتساب ≤3 أزرار بعنوان ≤20 حرفاً (القناة تتحقق)، تليجرام لوحة تختفي بعد الضغط
        res = await (ch.send_buttons(peer, reply, tips) if tips else ch.send_text(peer, reply))
        # واتساب يرجّع None حين يُرفض الإرسال (نافذة 24 ساعة · خطأ Meta · حدّ الباقة)،
        # وتليجرام لا يرجّع شيئاً عند النجاح ويرمي عند الفشل — تمييز LoggedChannel._log نفسه
        delivered = not (res is None and getattr(inner, "phone_id", None) is not None)
    except Exception:
        log.exception("AI reply send failed for bot #%s", bot_row["id"])
        delivered = False
    if not delivered:
        # حُجز للرد (من الحصة أو بالقروش) ولم يصل: يُعاد الحجز كله — لا خصم على ما لم يصل
        db.ai_reply_release(bot_row["owner_id"], grant, price, ref=f"ai:{bot_row['id']}")
        return False
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
        # لا نُسكت البوت هنا: العميل الذي طلب موظفاً ثم سأل ولم يرد أحد كان يلقى صمتاً
        # 12 ساعة. التنبيه يصل صاحب البوت (Reply عليه من تليجرام يرد مباشرة)، والتولّي
        # الفعلي يبدأ بأول رد بشري (صندوق الوارد أو تليجرام) — حتى ذلك يكمل البوت.
        import inbox_relay
        reason = str(action.get("reason") or "")[:200]
        if not await inbox_relay.alert(bot_row, peer, "🙋 عميل محتاج دعم في", reason, throttle=True):
            conv = db.get_conversation(bot_id, peer) or {}
            await notify_owner(bot_row, raw_channel,
                               f"🙋 العميل {conv.get('name') or peer} في «{biz}» يطلب التحدث مع موظف."
                               f"\n{reason}\nافتح صندوق الوارد للرد عليه.")
    elif kind == "notify":
        await notify_owner(bot_row, raw_channel,
                           f"❓ سؤال لم يجد الذكاء الاصطناعي إجابته في «{biz}»:\n"
                           f"{str(action.get('note') or '')[:400]}")
    elif kind == "optout":
        # قد تكون أول رسالة للعميل — صفّه لم يُنشأ بعد، والإيقاف بلا صفّ يضيع
        db.add_bot_user(bot_id, _peer_num(peer), "", peer=peer)
        db.set_opt_out(bot_id, peer, True)
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

    # واتساب: علامتا القراءة و«يكتب…» فوراً (في الخلفية — لا تؤخّر الرد) — العميل يرى أن
    # رسالته وصلت وأن الرد قادم بدل شاشة صامتة أثناء توليد الذكاء الاصطناعي
    if not human and msg.get("id") and hasattr(raw, "mark_read"):
        t = asyncio.create_task(raw.mark_read(msg["id"]))
        _BG.add(t); t.add_done_callback(_BG.discard)

    # إيقاف/استئناف العروض يُسجَّل في كل وضع (حتى أثناء تولّي صاحب النشاط)
    word = (msg.get("text") or "").strip().lower() if msg["kind"] != "media" else ""
    opt = "out" if word in OPT_OUT_WORDS else "in" if word in OPT_IN_WORDS else None
    if opt:
        db.add_bot_user(bot_id, _peer_num(peer), msg.get("name", ""), peer=peer)
        db.set_opt_out(bot_id, peer, opt == "out")
        if not human:
            db.clear_chat_state(bot_id, peer)
            await channel.remove_keyboard(peer, OPT_TEXT[(opt, _lang_of(word))])
            return

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
    ai_down = False
    if mode == "ai":
        if await _ai_mode(bot_row, cfg, raw, channel, peer, msg, f):
            return
        # الذكاء الاصطناعي لم يرد (لا مفتاح · نفدت الحصة والرصيد · تعطّل المزوّد):
        # العميل لم يمرّ بالفلو قط، فالفلو يبدأ معه — لا «أرسل /start».
        ai_down = True

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
        if db.bot_user_exists(bot_id, peer) and not ai_down:
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


async def _greet(bot_row, cfg, channel, peer, text, options=None):
    """رسالة البداية — بصورة/فيديو الترحيب من المكتبة إن وُجد، أو رابط صورة قديم.
    `options`: أزرار بداية (وضع «عقل البوت») — تحت الوسائط مباشرة لو أمكن."""
    if not text:
        return
    asset = _asset(bot_row, cfg.get("welcome_asset"))
    if asset:
        try:
            await channel.send_media(peer, asset, bot_row["id"], caption=text, options=options or None)
            return
        except Exception:
            log.exception("welcome media failed for bot #%s", bot_row["id"])
    img = cfg.get("welcome_image")
    if img:
        await channel.send_image(peer, img, caption=None if options else text)
        if not options:
            return
    if options:
        await channel.send_buttons(peer, text, options)
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
        greeting, starters = _welcome_of(bot_row, cfg, f, msg.get("text", ""))
        await _greet(bot_row, cfg, channel, peer, greeting, starters)
        return True
    if kind == "unsupported":
        await channel.send_text(peer, "📝 اكتب لي سؤالك أو طلبك نصاً وأنا أساعدك.")
        return True
    if kind == "media":
        await channel.send_text(peer, "📎 وصلني الملف. اكتب لي كمان طلبك أو سؤالك نصاً عشان أساعدك.")
        return True
    # عميل في فلو احتياطي (تعطّل الذكاء الاصطناعي في رسالة سابقة): نجرّب الذكاء أولاً في
    # كل رسالة — لو رد يُمسح الفلو فلا يعلق العميل في «اسمك؟ رقمك؟» بعد عودة المزوّد.
    in_flow = bool(db.get_chat_state(bot_id, peer))
    first = not db.bot_user_exists(bot_id, peer)
    text = msg.get("text", "")
    # الشكر والتقييم: رد فوري مجاني قبل أي استدعاء للنموذج
    if not first and await _closing(bot_row, cfg, channel, peer, text):
        db.clear_chat_state(bot_id, peer)
        db.touch_bot_user(bot_id, peer)
        return True
    if not await _ai_answer(bot_row, cfg, raw, peer, text):
        # بوت المنصة الرسمي لا يسقط لفلو «اسمك؟»: يرد من حقائق المنصة الثابتة
        if _platform_facts(bot_row, cfg) is not None:
            import platform_kb
            reply, opts = platform_kb.offline_reply(text, _lang_of(text))
            db.add_bot_user(bot_id, _peer_num(peer), msg.get("name", ""), peer=peer)
            db.clear_chat_state(bot_id, peer)
            await (channel.send_buttons(peer, reply, opts) if opts else channel.send_text(peer, reply))
            if platform_kb._intent(text) == "human":   # وعدناه بموظف — نحوّله فعلاً
                await _ai_action(bot_row, cfg, raw, peer, {"type": "handoff", "reason": text[:200]})
            return True
        return False                  # لا تسجيل هنا — الفلو يسجّله ويحتسب بدايته مرة واحدة
    if in_flow:
        db.clear_chat_state(bot_id, peer)
    db.add_bot_user(bot_id, _peer_num(peer), msg.get("name", ""), peer=peer)
    if first:
        db.log_event(bot_id, "start")
    return True


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

def inbox_out(update, ctx, text, markup=None, kind="text"):
    """يسجّل رد قالب تليجرام (متجر · حجز · قائمة) في صندوق الوارد. هذه القوالب لا تمرّ بـ
    LoggedChannel، فكان صاحب النشاط يرى رسالة عميله ولا يرى ما ردّ به بوته. نفس صيغته:
    النص ثم الأزرار [..]."""
    kb = getattr(markup, "keyboard", None) or ()
    opts = [getattr(b, "text", b) for row in kb for b in row]
    body = (text or "") + ("\n" + " · ".join(f"[{o}]" for o in opts) if opts else "")
    try:
        db.log_message(_bid(ctx), f"tg:{update.effective_chat.id}", "out", "bot", body, kind=kind)
    except Exception:
        log.exception("could not log a template reply")

async def send_intro(update, ctx, text, reply_markup=None):
    """ترحيب قوالب المتجر والحجز والقائمة (وحدها تستعمله) — ويُسجَّل في صندوق الوارد."""
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
                inbox_out(update, ctx, text, reply_markup, "media")
                return
            except Exception:
                log.exception("welcome media failed for bot #%s", _bid(ctx))
    img = cfg.get("welcome_image")
    if img:
        try:
            await update.message.reply_photo(img, caption=text, reply_markup=reply_markup)
            inbox_out(update, ctx, text, reply_markup, "media")
            return
        except Exception:
            pass
    await update.message.reply_text(text, reply_markup=reply_markup)
    inbox_out(update, ctx, text, reply_markup)
