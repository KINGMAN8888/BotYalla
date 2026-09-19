"""تنبيه «عميل محتاج دعم» على تليجرام صاحب البوت، والرد عليه من تليجرام مباشرة.

الوسم ``#C<bot_id>:<peer>`` في نص التنبيه هو الربط (نفس فكرة ``#T<id>`` للتذاكر،
AGENTS.md §3.36): صاحب البوت يعمل **Reply** على التنبيه في بوت المنصة ← الرد يصل
العميل على قناته (واتساب/تليجرام) ويُسجَّل في صندوق الوارد كرد بشري ويتولّى المحادثة.

- المستلمون = من يُسمح لهم بالرد: تليجرام صاحب البوت المربوط (`user_tg_channel`) +
  `owner_chat_id` لبوت واتساب + أدمنز المنصة لو صاحب البوت حساب إدارة. الرد يُقبل
  **فقط** من أحدهم — الوسم وحده لا يمنح صلاحية (من ينسخه في Reply لا يرسل شيئاً).
- الإرسال بنفس قواعد صندوق الوارد: باقة تتيح الرد اليدوي · نافذة واتساب 24 ساعة ·
  عدّاد الاستهلاك عبر `_wa_channel` (داخل `manager._send_to_peer`).
- كل شيء هنا يعمل **داخل حلقة المدير** (معالجات بوت المنصة) — لذا `_send_to_peer`
  المتزامنة مع الحلقة لا `send_to_peer` التي تنتظر الحلقة نفسها فتتجمّد (§3.32)."""
import json
import logging
import re
import time

import database as db

log = logging.getLogger("inbox_relay")

TAG_RE = re.compile(r"#C(\d+):((?:wa|tg):-?\d+)")
WA_WINDOW = 24 * 3600
ALERT_EVERY = 20 * 60            # تنبيه «محتاج دعم» واحد لكل محادثة كل 20 دقيقة
_last_alert = {}


def tag(bot_id, peer):
    return f"#C{int(bot_id)}:{peer}"


def parse(text):
    m = TAG_RE.search(text or "")
    return (int(m.group(1)), m.group(2)) if m else None


def recipients(bot_row):
    """معرّفات تليجرام التي يصلها التنبيه عبر بوت المنصة — وهي وحدها من يحق له الرد."""
    out = []
    cfg = json.loads(bot_row.get("config_json") or "{}")
    owner = bot_row.get("owner_id")
    for v in (db.user_tg_channel(owner) if owner else None,
              cfg.get("owner_chat_id") if (bot_row.get("channel") or "telegram") == "whatsapp" else None):
        if v and str(v) not in out:
            out.append(str(v))
    if db.bot_owner_is_staff(bot_row["id"]):
        for v in db.admin_chat_ids():
            if v not in out:
                out.append(v)
    return out


def can_reply(bot_row, tg_user_id):
    return bool(bot_row) and str(tg_user_id) in recipients(bot_row)


def _markup(bot_id, peer):
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    return InlineKeyboardMarkup([[InlineKeyboardButton(
        "🤖 رجّع المحادثة للبوت / Back to bot", callback_data=f"cv_bot:{int(bot_id)}:{peer}")]])


def _alert_text(bot_row, peer, headline, detail=""):
    conv = db.get_conversation(bot_row["id"], peer) or {}
    cfg = json.loads(bot_row.get("config_json") or "{}")
    biz = cfg.get("business_name") or bot_row.get("name") or ""
    who = conv.get("name") or ""
    num = peer.split(":", 1)[1] if ":" in peer else peer
    contact = f"+{num}" if peer.startswith("wa:") else f"Telegram {num}"
    recent = [m for m in db.recent_history(bot_row["id"], peer, 8) if m.get("direction") == "in"][-3:]
    lines = [f"{headline} «{biz}»", f"👤 {who + ' · ' if who else ''}{contact}"]
    if detail:
        lines.append(f"📝 {detail[:200]}")
    if recent:
        lines.append("💬 آخر رسائله:")
        lines += [f"  • {(m.get('text') or '📎')[:160]}" for m in recent]
    lines.append("")
    lines.append("↩️ اعمل Reply على الرسالة دي وردّك يوصله مباشرة "
                 + ("على واتساب." if peer.startswith("wa:") else "على تليجرام."))
    lines.append(tag(bot_row["id"], peer))
    return "\n".join(lines)


async def alert(bot_row, peer, headline, detail="", throttle=False):
    """يرسل التنبيه لكل المستلمين عبر بوت المنصة. يرجّع True لو وصل لواحد على الأقل
    (وإلا يستعمل المستدعي طريق الإشعار القديم)."""
    key = (bot_row["id"], peer)
    now = time.time()
    if throttle and now - _last_alert.get(key, 0) < ALERT_EVERY:
        return True                      # نُبّه مؤخراً — لا إزعاج مع كل رسالة
    import bot_manager
    text = _alert_text(bot_row, peer, headline, detail)
    sent = False
    for chat in recipients(bot_row):
        if await bot_manager.manager.notify_text_async(chat, text, reply_markup=_markup(bot_row["id"], peer)):
            sent = True
    if sent:
        _last_alert[key] = now
    return sent


def _reply_allowed(bot_row):
    """نفس بوابة الرد في صندوق الوارد (`app._can_reply`) لكن بصاحب البوت."""
    import plans
    owner = db.get_user(bot_row["owner_id"]) or {}
    if owner.get("role") in ("admin", "support"):
        return True
    sub = db.get_subscription(bot_row["owner_id"])
    pid = sub["plan"] if sub and sub.get("status") == "active" else "free"
    return plans.inbox_reply(pid)


async def relay_reply(bot_id, peer, tg_user_id, text):
    """رد صاحب البوت من تليجرام ← العميل. يرجّع (ok, رسالة للمرسل)."""
    import bot_manager
    row = db.get_bot(bot_id)
    if not row or not can_reply(row, tg_user_id):
        return False, "⚠️ مش مسموح لك ترد على المحادثة دي."
    text = (text or "").strip()[:4000]
    if not text:
        return False, "⚠️ اكتب نص الرد."
    if not _reply_allowed(row):
        return False, "⚠️ باقتك لا تتيح الرد اليدوي — رقّي الباقة من اللوحة."
    if peer.startswith("wa:") and int(time.time()) - db.peer_last_in(bot_id, peer) > WA_WINDOW:
        return False, ("⚠️ عدّت 24 ساعة على آخر رسالة من العميل — واتساب لا يسمح برسالة حرة. "
                       "استخدم قالباً معتمداً من صفحة البث.")
    ok, err = await bot_manager.manager._send_to_peer(row, peer, text)
    if not ok:
        return False, f"⚠️ الرسالة لم تُرسل ({err})."
    db.log_message(bot_id, peer, "out", "human", text)
    db.set_conversation_mode(bot_id, peer, "human")   # الرد اليدوي تولٍّ — البوت يسكت معه
    db.mark_conversation_read(bot_id, peer)
    return True, "✅ اتبعت للعميل. البوت واقف في المحادثة دي لحد ما ترجّعها له (الزر تحت التنبيه)."


def back_to_bot(bot_id, peer, tg_user_id):
    row = db.get_bot(bot_id)
    if not row or not can_reply(row, tg_user_id):
        return False
    db.set_conversation_mode(bot_id, peer, "bot")
    return True
