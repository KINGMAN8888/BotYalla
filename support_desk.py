"""الدعم والشكاوى ومشاكل الدفع — تذاكر تصل الأدمن فوراً على بوت المنصة.

كل رسالة من العميل (جديدة أو متابعة) تُرسل لكل أدمن على بوت المنصة وفيها الوسم
``#T<id>``. الأدمن يرد بـ **Reply** على نفس الرسالة في تليجرام (أو من «تذاكر الدعم»
في اللوحة) فيُحفظ الرد ويصل للعميل: في صفحة الدعم دائماً، وعلى تليجرام لو ربط
حسابه ببوت المنصة، وبالإيميل لو له إيميل. الوسم في نص التنبيه هو الربط — بلا جدول
لمعرّفات رسائل تليجرام.
"""
import re

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

import database as db
import mailer

KINDS = ("support", "complaint", "payment", "other", "wa_setup", "vip_call", "done_for_you")
# done_for_you: «فريقنا يجهّزه لك» — العميل منح الفريق إذناً مؤقتاً بتجهيز بوته (app.assist_request)
# vip_call: طلب مكالمة لباقة «راحة البال» (/vip/request) — لا يُختار من النموذج العام أيضاً
# wa_setup لا يُختار من نموذج الدعم العام: يُفتح من «سيبها علينا» في خطوة واتساب وحدها
# (/whatsapp/assist)، حيث تُفحص باقة العميل — ومنه وحده يربط الفريق بوتاً في حسابه.
USER_KINDS = KINDS[:4]
_KIND = {"support":   ("🛠️", "دعم فني", "Support"),
         "complaint": ("⚠️", "شكوى", "Complaint"),
         "payment":   ("💳", "مشكلة دفع", "Payment issue"),
         "other":     ("💬", "أخرى", "Other"),
         "wa_setup":  ("🟢", "ربط واتساب", "WhatsApp setup"),
         "vip_call":  ("⭐", "مكالمة راحة البال", "Peace of Mind call"),
         "done_for_you": ("🧰", "جهّزوه لي", "Done for you")}
TAG_RE = re.compile(r"#T(\d+)\b")
SUBJECT_MAX, BODY_MIN, BODY_MAX = 120, 10, 3000


def norm_kind(kind):
    """نوع تذكرة من نموذج الدعم العام — لا يقبل wa_setup (انظر USER_KINDS)."""
    return kind if kind in USER_KINDS else "other"


def alert_text(t, body, followup=False):
    """نص التنبيه للأدمن. الوسم #T<id> إلزامي: منه يعرف معالج الرد أي تذكرة."""
    icon, ar, en = _KIND.get(t.get("kind"), _KIND["other"])
    head = (f"↩️ رد جديد من العميل على #T{t['id']}" if followup
            else f"{icon} {ar} / {en} — تذكرة جديدة #T{t['id']}")
    how = ("\n🔧 للربط: «تذاكر الدعم» في اللوحة ← «ربط واتساب للعميل».\n"
           "To connect: Support tickets → «Connect WhatsApp for the customer»."
           if t.get("kind") == "wa_setup" and not followup else "")
    return (f"{head}\n👤 {t.get('username') or '?'} (#{t['user_id']})\n📌 {t['subject']}\n\n"
            f"{body[:1500]}\n\n"
            "↩️ اعمل Reply على الرسالة دي واكتب ردّك — هيوصل للعميل.\n"
            "Reply to this message to answer the customer." + how)


def alert_markup(tid):
    return InlineKeyboardMarkup([[InlineKeyboardButton("✅ تم الحل / Resolve",
                                                       callback_data=f"tk_close:{tid}")]])


def ticket_id_from(text):
    m = TAG_RE.search(text or "")
    return int(m.group(1)) if m else None


def user_text(t, body, lang="ar"):
    if lang == "en":
        return (f"💬 The BotYalla team replied to your ticket #T{t['id']} “{t['subject']}”:\n\n{body}"
                "\n\nTo reply: Support in your dashboard.")
    return (f"💬 رد فريق BotYalla على تذكرتك #T{t['id']} «{t['subject']}»:\n\n{body}"
            "\n\nللرد: صفحة «الدعم والشكاوى» في لوحتك.")


def record_staff_reply(tid, body, via="web"):
    """يحفظ رد الفريق ويرسل الإيميل. None لو التذكرة غير موجودة، وإلا dict:
    ticket · chat (تليجرام العميل إن ربطه) · text (الرسالة له) · emailed.

    الإرسال على تليجرام على المستدعي: من الويب ``manager.notify_text``، ومن داخل بوت
    المنصة ``ctx.bot.send_message`` — انتظار الحلقة من داخلها يجمّدها."""
    t = db.get_ticket(tid)
    if not t:
        return None
    db.add_ticket_msg(tid, "staff", body, via)
    lang = db.user_lang(t["user_id"])
    emailed = mailer.send_ticket_reply(t, body, lang)
    return {"ticket": t, "chat": db.get_setting(t["user_id"], "tg_chat_id"),
            "text": user_text(t, body, lang), "emailed": bool(emailed)}
