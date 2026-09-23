"""محرّك التفعيل — رسالة واحدة، في الوقت الصح، لمن توقّف في منتصف الطريق.

تقرير 17–23 سبتمبر 2026 قال الرقم الذي بُني له هذا الملف: **6 من كل 10 مسجّلين
لا ينشئون بوتاً أبداً**، وبوتات تُشغَّل ولا تصلها رسالة عميل واحدة. هؤلاء ليسوا
عملاء خسرناهم — هم عملاء توقّفوا عند خطوة واحدة ولم يسألهم أحد.

القواعد التي تحكم كل رسالة هنا:

1. **رسالة واحدة لكل حالة، إلى الأبد.** `nudge_log` مفتاحه (المستخدم، النوع،
   المرجع)، ولا يُكتب إلا **بعد** وصول الرسالة فعلاً — فرسالة لم تصل تُعاد في
   الدورة التالية، ورسالة وصلت لا تتكرر أبداً.
2. **من تقدّم يخرج من القائمة بنفسه.** الاستعلام يسأل عن الحالة الآن لا عن حدث
   قديم: من أنشأ بوتاً لا يظهر في «بلا بوت» ولو كان دوره قد حان.
3. **لا رسائل في نصّ الليل.** `QUIET` يمنع الإرسال خارج 9ص–10م بتوقيت الجهاز،
   فالمتوقّف عن الإعداد لا يُوقَظ الثالثة فجراً باسم «المساعدة».
4. **خدمة لا تسويق.** كل نصّ هنا يكمل خطوةً بدأها المستخدم بنفسه (AGENTS §47)،
   بلا عروض ولا خصومات — ولذلك تصل بالبريد لمن له بريد بلا اشتراك في الأخبار.
5. **سقف لكل دورة.** `PER_CYCLE` يمنع أن يتحوّل عطل في استعلام إلى مئة رسالة.

التشغيل من حلقة `bot_manager` كل نصف ساعة. الإرسال يُحقَن (`notify`) فتُختبر
الدالّة كاملةً بلا تليجرام ولا بريد.
"""
import logging
import time

import database as db
import i18n

log = logging.getLogger("activation")

QUIET = (9, 22)              # لا إرسال قبل 9 صباحاً ولا بعد 10 مساءً (توقيت الخادم)
PER_CYCLE = 40               # سقف الرسائل في الدورة الواحدة
MAX_AGE = 21 * 86400         # لا نلاحق حساباً أقدم من ثلاثة أسابيع

# (النوع، بعد كم ثانية من الحدث، مفتاح الترجمة). الترتيب = ترتيب الإرسال.
RULES = (
    ("no_bot_1h",       1 * 3600,  "act_no_bot_1h"),
    ("verify_stuck_2h", 2 * 3600,  "act_verify_2h"),
    ("bot_off_2h",      2 * 3600,  "act_bot_off"),
    ("no_bot_24h",      24 * 3600, "act_no_bot_24h"),
    ("bot_silent_24h",  24 * 3600, "act_bot_silent"),
    ("no_bot_72h",      72 * 3600, "act_no_bot_72h"),
)


def enabled():
    return (db.get_platform("activation_nudges", "1") or "1") != "0"


def quiet_now(now=None):
    """هل الوقت الآن خارج ساعات الإرسال؟"""
    h = time.localtime(now or time.time()).tm_hour
    return not (QUIET[0] <= h < QUIET[1])


def _link(path=""):
    import mailer
    return mailer.site_url(path) or ""


def message(kind, row, lang="ar"):
    """نصّ الرسالة لهذه الحالة — مفتاح ترجمة واحد بعناصر نائبة، لا نصّ في الكود."""
    key = dict((k, t) for k, _, t in RULES)[kind]
    return i18n.t(key, lang).format(
        name=row.get("username") or "", bot=row.get("bot_name") or "",
        email=row.get("email") or "",
        link=_link("/dashboard"), verify=_link("/verify-email"),
        bots=_link("/dashboard"), support=_link("/support"))


def deliver(row, text, notify=None, subject=None, lang="ar"):
    """تليجرام أولاً (فوري ومجاني)، ثم البريد. يرجّع اسم أول قناة وصلت أو None."""
    user_id = row["user_id"]
    chat = db.user_tg_channel(user_id)
    if chat and notify:
        try:
            if notify(chat, text):
                return "telegram"
        except Exception:                                  # noqa: BLE001
            log.warning("activation: telegram failed for user #%s", user_id)
    email = row.get("email")
    if email:
        try:
            import mailer
            if mailer.configured():
                if mailer.send_mail(email, *mailer.activation_email(subject, text, lang)):
                    return "email"
        except Exception:                                  # noqa: BLE001
            log.warning("activation: email failed for user #%s", user_id)
    return None


def run_cycle(notify=None, now=None, force=False):
    """دورة واحدة: يرجّع {kind: عدد ما أُرسل}. آمنة للتكرار — لا تكرّر رسالة وصلت."""
    out = {}
    if not force and (not enabled() or quiet_now(now)):
        return out
    budget = PER_CYCLE
    for kind, after, _key in RULES:
        if budget <= 0:
            break
        try:
            rows = db.activation_candidates(kind, after, MAX_AGE, limit=min(budget, 20))
        except Exception:                                  # noqa: BLE001
            log.exception("activation: candidates failed for %s", kind)
            continue
        for row in rows:
            lang = db.user_lang(row["user_id"])
            key = dict((k, t) for k, _, t in RULES)[kind]
            ch = deliver(row, message(kind, row, lang), notify,
                         subject=i18n.t(f"{key}_s", lang), lang=lang)
            if ch:
                db.log_nudge(row["user_id"], kind, row.get("ref") or 0, ch)
                out[kind] = out.get(kind, 0) + 1
                budget -= 1
                if budget <= 0:
                    break
    if out:
        log.info("activation nudges sent: %s", out)
    return out


# ---------------------------------------------------------------- عميل ينتظر
def waiting_cycle(alert=None, min_seconds=900):
    """عميل كتب ولم يُردّ عليه: تنبيه صاحب البوت مرة واحدة لكل انتظار.

    لماذا هنا لا في المحرّك: المحرّك يرد لحظةً بلحظة ولا يعرف ما لم يحدث. هذا
    الفحص يرى **الصمت** — وهو ما يخسر العميل فعلاً."""
    sent = 0
    for c in db.waiting_conversations(min_seconds=min_seconds):
        row = db.get_bot(c["bot_id"])
        if not row:
            continue
        mins = max(1, int((time.time() - c["last_at"]) / 60))
        head = i18n.t("act_waiting", db.user_lang(row["owner_id"])).format(
            name=(c.get("name") or c["peer"]), bot=c.get("bot_name") or "", mins=mins)
        try:
            if alert and alert(row, c["peer"], head, (c.get("last_text") or "")[:200]):
                sent += 1
        except Exception:                                  # noqa: BLE001
            log.warning("waiting alert failed for bot #%s", c["bot_id"])
        db.mark_waiting_alerted(c["bot_id"], c["peer"])     # لا نعيد المحاولة لنفس الانتظار
    if sent:
        log.info("waiting-customer alerts sent: %s", sent)
    return sent
