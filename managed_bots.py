"""إنشاء بوت تليجرام بضغطة واحدة — Telegram Managed Bots (Bot API 9.6، 3 أبريل 2026).

الطريقة الرسمية لإنشاء بوت نيابةً عن مستخدم، **بموافقته داخل تليجرام نفسه**:

1. المنصة تولّد رابطاً لمرة واحدة إلى بوت المنصة: ``t.me/<platform>?start=mb-<code>``
   (زر على الموبايل · QR على الكمبيوتر). الكود يُخزَّن تجزئةً وصالح 15 دقيقة.
2. بوت المنصة يربط حساب تليجرام بطلب المنصة، ثم يعرض زر «أنشئ بوتي» برابط
   ``t.me/newbot/<platform>/<username>?name=<name>`` — شاشة الإنشاء الأصلية في تليجرام
   مملوءة مسبقاً بالاسم واليوزر المقترحين.
   (زر لوحة المفاتيح ``request_managed_bot`` يصل للتطبيق كطلب محادثة
   ``requestPeerTypeCreateBot``، وتليجرام iOS فتحه كشاشة «Forward» فارغة بدل شاشة
   الإنشاء — 2026-09-13. الرابط هو الطريق الموثّق ويعمل على كل التطبيقات.)
3. المستخدم يؤكّد ← تحديث ``managed_bot`` ``{user, bot}`` ← ``getManagedBotToken(bot.id)``
   ← صفّ البوت يُنشأ بالقالب المختار ويُهيّأ بروفايله ويُشغَّل ← «بوتك جاهز» برابطه.

الربط في الخطوة 2 ضروري لأن التحديث يحمل معرّف تليجرام لا حساب المنصة: بلا كود
صادر من جلسة مسجّلة لا نعرف لمن البوت، فتحديث بلا طلب مربوط **لا يُنشئ شيئاً**.

لا نطلب ولا نرى أي بيانات دخول لحساب تليجرام (AGENTS.md §6). المستخدم هو مالك
البوت في تليجرام، والمنصة تشغّله بتوكنه كأي بوت آخر.

python-telegram-bot 21.6 لا يعرف هذه الحقول: تصل في ``api_kwargs``، والطرق تُستدعى
عبر ``bot.do_api_request`` — داخل حلقة asyncio بلا طلب HTTP متزامن يجمّد باقي البوتات.
"""
import asyncio
import hashlib
import logging
import os
import random
import re
import secrets
from urllib.parse import urlencode

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardRemove

import database as db
import i18n
import plans
import templates_bot as T
import tg_helpers as tg

log = logging.getLogger("managed_bots")

CODE_PREFIX = "mb-"
# التحديثات التي يستقبلها بوت المنصة. managed_bot لا يصل إلا لو طُلب صراحةً.
PLATFORM_UPDATES = ["message", "callback_query", "managed_bot"]


def token_hash(code):
    return hashlib.sha256((code or "").encode("utf-8")).hexdigest()


def new_code():
    """24 محرفاً من [A-Za-z0-9_-] — ضمن حدود معامل start (64 محرفاً)."""
    return secrets.token_urlsafe(18)


# نقحرة عربية بسيطة (نطق مصري) لاقتراح يوزر لاتيني من اسم النشاط
_AR = {"ا": "a", "أ": "a", "إ": "e", "آ": "a", "ب": "b", "ت": "t", "ث": "s", "ج": "g",
       "ح": "h", "خ": "kh", "د": "d", "ذ": "z", "ر": "r", "ز": "z", "س": "s", "ش": "sh",
       "ص": "s", "ض": "d", "ط": "t", "ظ": "z", "ع": "a", "غ": "gh", "ف": "f", "ق": "k",
       "ك": "k", "ل": "l", "م": "m", "ن": "n", "ه": "h", "و": "w", "ي": "y", "ى": "a",
       "ة": "a", "ء": "", "ؤ": "o", "ئ": "e", "ـ": ""}


def suggest_username(name, rnd=None):
    """يوزر بوت صالح لتليجرام: يبدأ بحرف، [a-z0-9_]، 5–32 محرفاً، ينتهي بـ bot.
    لاحقة رقمية تقلّل احتمال أن يكون محجوزاً — والمستخدم يعدّله في شاشة تليجرام."""
    rnd = rnd or random.Random()
    s = "".join(_AR.get(ch, ch) for ch in (name or "").strip().lower())
    s = re.sub(r"[^a-z0-9]+", "_", s).strip("_")
    if not s or not s[0].isalpha():
        s = ("my_" + s).strip("_") if s else "my_shop"
    s = s[:20].rstrip("_")
    return f"{s}_{rnd.randint(100, 999)}_bot"


def start_link(platform_username, code):
    return f"https://t.me/{platform_username}?start={CODE_PREFIX}{code}"


def newbot_link(platform_username, suggested, name=None):
    """https://t.me/newbot/{manager}/{suggested_username}[?name={suggested_name}] (Bot API 9.6)."""
    link = f"https://t.me/newbot/{platform_username}/{suggested}"
    name = (name or "").strip()[:64]
    return f"{link}?{urlencode({'name': name})}" if name else link


def extract(update):
    """(معرّف المنشئ، بيانات البوت) من تحديث managed_bot أو رسالة managed_bot_created.
    يدعم الحالتين: حقول مجهولة في api_kwargs (PTB 21.6) أو كائنات (PTB ≥ 22.8)."""
    obj = getattr(update, "managed_bot", None)
    if obj is not None and getattr(obj, "user", None) and getattr(obj, "bot", None):
        b = obj.bot
        return int(obj.user.id), {"id": b.id, "username": b.username, "first_name": b.first_name}
    mb = (getattr(update, "api_kwargs", None) or {}).get("managed_bot")
    if isinstance(mb, dict):
        u, b = mb.get("user") or {}, mb.get("bot") or {}
        if u.get("id") and b.get("id"):
            return int(u["id"]), b
    msg = getattr(update, "message", None)
    if msg is not None and msg.from_user:
        mc = (getattr(msg, "api_kwargs", None) or {}).get("managed_bot_created")
        if isinstance(mc, dict) and (mc.get("bot") or {}).get("id"):
            return int(msg.from_user.id), mc["bot"]
    return None


# ------------------------------------------------------------ بوت المنصة
async def on_start_code(update, ctx, code):
    """/start mb-<code>: يربط حساب تليجرام بالطلب ثم يعرض زر الإنشاء (رابط newbot).
    التأكيد في تليجرام يرسل تحديث ``managed_bot`` فيلتقطه ``on_update``."""
    u = update.effective_user
    req = db.link_managed_request(token_hash(code), u.id)
    if not req:
        await update.message.reply_text(i18n.t("mb_tg_bad", "ar") + "\n" + i18n.t("mb_tg_bad", "en"))
        return
    lang = db.user_lang(req["user_id"])
    link = newbot_link(ctx.bot.username, req["suggested_username"], req["business_name"])
    await update.message.reply_text(
        i18n.t("mb_tg_prompt", lang).format(name=req["business_name"]),
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(
            i18n.t("mb_tg_button", lang), url=link)]]))


async def on_update(update, ctx):
    """معالج عام في بوت المنصة: يلتقط إنشاء بوت مُدار ويتجاهل غيره."""
    got = extract(update)
    if not got:
        return
    creator_id, new_bot = got
    try:
        await provision(ctx.bot, creator_id, new_bot)
    except Exception:
        log.exception("managed bot provisioning failed (tg user %s)", creator_id)


async def _fetch_token(pbot, bot_user_id):
    try:
        tok = await pbot.do_api_request("getManagedBotToken",
                                        api_kwargs={"user_id": int(bot_user_id)})
    except Exception:
        log.exception("getManagedBotToken failed for bot %s", bot_user_id)
        return None
    if isinstance(tok, dict):
        tok = tok.get("token")
    return tok if isinstance(tok, str) and ":" in tok else None


async def _say(pbot, chat_id, text, reply_markup=None):
    try:
        await pbot.send_message(chat_id=int(chat_id), text=text, reply_markup=reply_markup)
    except Exception:
        log.exception("managed bot message to %s failed", chat_id)


async def provision(pbot, creator_id, new_bot):
    """ينشئ صفّ البوت من طلب مربوط، أو يحدّث توكن بوت قائم. يرجّع bot_id أو None."""
    import bot_manager
    mgr = bot_manager.manager

    # تليجرام يرسل managed_bot أيضاً عند تغيير توكن بوت مُدار أو مالكه
    existing = db.bot_by_tg_id(new_bot["id"])
    if existing:
        token = await _fetch_token(pbot, new_bot["id"])
        if token and token != existing["token"]:
            db.update_bot_token(existing["id"], token)
            if mgr.is_running(existing["id"]):
                await mgr.restart_bot_async(existing["id"])
            log.info("managed bot #%s token refreshed", existing["id"])
        return existing["id"]

    req = db.pending_managed_for_tg(creator_id)
    if not req:
        # بلا طلب مربوط من جلسة مسجّلة لا نعرف لمن البوت — لا ننشئ شيئاً
        log.warning("managed_bot from tg user %s without a linked request — ignored", creator_id)
        await _say(pbot, creator_id, i18n.t("mb_tg_no_request", "ar"))
        return None
    if not db.claim_managed_request(req["id"]):
        return None                                   # تحديث مكرّر لنفس الطلب
    lang = db.user_lang(req["user_id"])
    owner = db.get_user(req["user_id"])
    if not owner or owner.get("is_blocked"):
        db.finish_managed_request(req["id"], "failed", error="account")
        return None

    # حدّ الباقة يُفحص ثانيةً هنا: قد يكون أنشأ بوتاً آخر بين الرابط والتأكيد
    if owner.get("role") not in ("admin", "support"):
        sub = db.get_subscription(owner["id"])
        pid = sub["plan"] if sub["status"] == "active" else "free"
        if db.count_user_bots(owner["id"]) >= plans.plan(pid)["max_bots"]:
            db.finish_managed_request(req["id"], "failed", error="limit")
            await _say(pbot, creator_id, i18n.t("mb_tg_limit", lang))
            return None

    token = await _fetch_token(pbot, new_bot["id"])
    if not token:
        db.finish_managed_request(req["id"], "failed", error="token")
        await _say(pbot, creator_id, i18n.t("mb_tg_failed", lang))
        return None

    info = {"username": new_bot.get("username"), "name": new_bot.get("first_name")}
    # صاحب البوت هو من أكّد الإنشاء — فإشعارات الطلبات تصله فوراً بلا ربط يدوي
    cfg = T.initial_config(req["business_name"], req["template"], info,
                           owner_chat_id=str(creator_id))
    cfg["tg_bot_id"] = int(new_bot["id"])
    cfg["created_via"] = "managed"
    try:
        bot_id = db.create_bot(req["user_id"], req["business_name"], token, req["template"], cfg)
    except Exception as e:
        db.finish_managed_request(req["id"], "failed", error=type(e).__name__)
        await _say(pbot, creator_id, i18n.t("mb_tg_failed", lang))
        log.exception("create_bot failed for managed bot %s", new_bot.get("id"))
        return None
    db.finish_managed_request(req["id"], "created", bot_id=bot_id)
    if not db.get_setting(req["user_id"], "tg_chat_id"):
        db.set_setting(req["user_id"], "tg_chat_id", str(creator_id))

    # البروفايل الرسمي (اسم · وصف · أوامر): urllib متزامن، فخارج الحلقة
    try:
        prof = tg.build_profile_from_config(cfg, req["template"])
        res = await asyncio.to_thread(tg.configure_bot_profile, token, **prof)
        row = db.get_bot(bot_id)
        c2 = __import__("json").loads(row["config_json"] or "{}")
        c2.update(tg_synced_at=int(__import__("time").time()), tg_sync_ok=bool(res.get("ok")),
                  tg_sync_errors=res.get("errors", []))
        db.update_bot_config(bot_id, c2)
    except Exception:
        log.exception("profile sync failed for managed bot #%s", bot_id)

    started, _ = await mgr.start_bot_async(bot_id)
    if started:
        db.track("bot_live", req["user_id"], bot_id)     # مرحلة القمع: البوت شغّال
    uname = info["username"] or ""
    await _say(pbot, creator_id,
               i18n.t("mb_tg_done" if started else "mb_tg_done_stopped", lang).format(u=uname),
               reply_markup=ReplyKeyboardRemove())
    buttons = [[InlineKeyboardButton(i18n.t("mb_tg_open_bot", lang),
                                     url=f"https://t.me/{uname}?start=src-link")]]
    base = (os.getenv("PUBLIC_URL") or "").strip().rstrip("/")
    if base.startswith("https://"):
        buttons.append([InlineKeyboardButton(i18n.t("mb_tg_dashboard", lang),
                                             url=f"{base}/bot/{bot_id}")])
    await _say(pbot, creator_id, "👇", reply_markup=InlineKeyboardMarkup(buttons))
    for aid in db.admin_chat_ids():
        await mgr.notify_text_async(aid, f"🤖 بوت جديد بضغطة / One-tap bot: @{uname} — "
                                         f"{owner['username']}")
    log.info("managed bot #%s created for user #%s (@%s)", bot_id, owner["id"], uname)
    return bot_id
