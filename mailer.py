"""BotYalla — إرسال الإيميل عبر SMTP.

**best-effort:** لا ترمي أي دالة هنا استثناءً أبداً. الإيميل ليس مساراً حرجاً —
فشل الإرسال يُسجَّل ولا يُسقط الطلب ولا التسوية المالية.

الإعداد من `.env`:
    SMTP_HOST · SMTP_PORT (587) · SMTP_USER · SMTP_PASS · SMTP_FROM
    SMTP_TLS = starttls (افتراضي) | ssl | none
بلا `SMTP_HOST` و`SMTP_FROM` لا يُرسل شيء (يُسجَّل «غير مضبوط» فقط).
"""
import logging, os, smtplib, ssl, threading, time, datetime as _dt
from email.message import EmailMessage
from email.utils import make_msgid
from html import escape

import database as db
import plans

log = logging.getLogger("mailer")

# معدّل محدود لكل عنوان — حتى لا تصبح المنصة أداة إغراق صندوق بريد أحد.
RATE_LIMIT, RATE_WINDOW = 5, 3600
_sent = {}                    # address -> [timestamps]
_lock = threading.Lock()

# الاختبارات تضبطها True ليجري الإرسال في نفس الخيط.
SYNC = False


def _cfg():
    try:
        port = int(os.getenv("SMTP_PORT", "587") or 587)
    except ValueError:
        port = 587
    return {"host": os.getenv("SMTP_HOST", "").strip(), "port": port,
            "user": os.getenv("SMTP_USER", "").strip(), "password": os.getenv("SMTP_PASS", ""),
            "from": os.getenv("SMTP_FROM", "").strip(),
            "tls": (os.getenv("SMTP_TLS", "starttls") or "starttls").strip().lower()}


def configured():
    c = _cfg()
    return bool(c["host"] and c["from"])


def _mask(addr):
    """لا نكتب العناوين كاملة في السجل."""
    name, _, dom = (addr or "").partition("@")
    return (name[:2] + "***@" + dom) if dom else "***"


def _allow(addr):
    now = time.time()
    with _lock:
        recent = [t for t in _sent.get(addr, ()) if now - t < RATE_WINDOW]
        if len(recent) >= RATE_LIMIT:
            _sent[addr] = recent
            return False
        recent.append(now)
        _sent[addr] = recent
        if len(_sent) > 5000:                      # لا نموّ بلا حد
            for k in [k for k, v in _sent.items() if not v or now - v[-1] >= RATE_WINDOW]:
                _sent.pop(k, None)
        return True


def send_mail(to, subject, html, text=None):
    """يرسل رسالة. يرجّع True عند النجاح، وFalse في أي حالة أخرى — لا يرمي."""
    try:
        to = (to or "").strip()
        if not to or "@" not in to or any(ch in to for ch in "\r\n,;"):
            return False                           # عنوان واحد صالح فقط — لا حقن ترويسات
        cfg = _cfg()
        if not cfg["host"] or not cfg["from"]:
            log.info("mail skipped (SMTP not configured): %s", subject)
            return False
        if not _allow(to.lower()):
            log.warning("mail rate-limited: %s → %s", subject, _mask(to))
            return False
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = cfg["from"]
        msg["To"] = to
        msg["Message-ID"] = make_msgid(domain=cfg["from"].rpartition("@")[2].strip("> ") or None)
        msg.set_content(text or subject)
        msg.add_alternative(html, subtype="html")
        ctx = ssl.create_default_context()
        if cfg["tls"] == "ssl":
            server = smtplib.SMTP_SSL(cfg["host"], cfg["port"], timeout=15, context=ctx)
        else:
            server = smtplib.SMTP(cfg["host"], cfg["port"], timeout=15)
        with server:
            if cfg["tls"] == "starttls":
                server.starttls(context=ctx)
            if cfg["user"]:
                server.login(cfg["user"], cfg["password"])
            server.send_message(msg)
        log.info("mail sent: %s → %s", subject, _mask(to))
        return True
    except Exception as e:                         # best-effort: سجّل ولا ترمِ
        log.error("mail failed: %s → %s: %s", subject, _mask(to), e)
        return False


def send_async(to, subject, html, text=None):
    """يرسل في خيط خلفي: SMTP قد يستغرق ثوانٍ، ولا يجوز أن ينتظرها زرّ الأدمن
    أو حلقة asyncio لبوت المنصة."""
    if SYNC:
        return send_mail(to, subject, html, text)
    threading.Thread(target=send_mail, args=(to, subject, html, text), daemon=True).start()
    return True


# ---------------------------------------------------------------- القوالب
_BRAND = "BotYalla"


def _layout(lang, title, body_html):
    """قالب بسيط بهوية العلامة: أنماط داخلية لأن برامج البريد تتجاهل <style>."""
    rtl = lang != "en"
    d, align = ("rtl", "right") if rtl else ("ltr", "left")
    font = "Tahoma,'Segoe UI',Arial,sans-serif" if rtl else "'Segoe UI',Arial,sans-serif"
    return f"""<!doctype html><html lang="{'ar' if rtl else 'en'}" dir="{d}"><body style="margin:0;background:#EEF1F6;padding:24px 12px;font-family:{font};">
<table role="presentation" width="100%" cellspacing="0" cellpadding="0"><tr><td align="center">
<table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="max-width:560px;background:#ffffff;border-radius:14px;overflow:hidden;">
<tr><td style="background:#05070D;padding:18px 24px;color:#ffffff;font-size:20px;font-weight:800;text-align:{align};">{_BRAND}</td></tr>
<tr><td dir="{d}" style="padding:28px 24px;color:#111827;font-size:15px;line-height:1.8;text-align:{align};">
<h1 style="margin:0 0 14px;font-size:20px;color:#05070D;">{escape(title)}</h1>
{body_html}
</td></tr>
<tr><td style="padding:14px 24px;background:#F6F7FA;color:#6B7280;font-size:12px;text-align:{align};">{_BRAND} · info@youssefalsherief.tech</td></tr>
</table></td></tr></table></body></html>"""


def _button(href, label):
    return (f'<p style="margin:22px 0;"><a href="{escape(href, quote=True)}" '
            f'style="display:inline-block;background:#0EA5E9;color:#ffffff;text-decoration:none;'
            f'padding:12px 22px;border-radius:10px;font-weight:700;">{escape(label)}</a></p>')


def reset_email(link, lang="ar", minutes=60):
    """(subject, html, text) لرابط استرجاع كلمة المرور."""
    if lang == "en":
        subject = "Reset your BotYalla password"
        intro = (f"We received a request to reset your password. The link is valid for "
                 f"{minutes} minutes and can be used once.")
        note = "If you didn't ask for this, ignore this email — your password stays the same."
        label = "Set a new password"
    else:
        subject = "استرجاع كلمة مرور BotYalla"
        intro = f"وصلنا طلب لاسترجاع كلمة مرورك. الرابط صالح {minutes} دقيقة ولمرة واحدة فقط."
        note = "لو لم تطلب ذلك تجاهل هذه الرسالة — كلمة مرورك تبقى كما هي."
        label = "اضبط كلمة مرور جديدة"
    html = _layout(lang, subject, f"<p>{escape(intro)}</p>{_button(link, label)}"
                                  f"<p style=\"color:#6B7280;font-size:13px;\">{escape(note)}</p>")
    text = f"{intro}\n\n{link}\n\n{note}"
    return subject, html, text


def welcome_email(username, link=None, lang="ar"):
    """(subject, html, text) لرسالة الترحيب بعد التسجيل.

    الخطوات الثلاث مكتوبة **داخل** الرسالة لا خلف رابط دليل: أكبر فجوة فهم عند
    المستخدم الجديد أن التوكن يُجلب من BotFather — وهي خطوة خارج المنصة كلها،
    فلو انتظرت أن يضغط رابطاً ليقرأها فقد خسرتها. الرابط اختياري: بلا
    `PUBLIC_URL` تُرسل الرسالة بلا زرّ بدل ألا تُرسل (لا تحمل أي توكن).
    """
    en = lang == "en"
    if en:
        subject = "Welcome to BotYalla — your bot in 3 steps"
        intro = (f"Welcome, {username}. Your account is ready. Building your first bot "
                 f"takes about five minutes, and the only step outside BotYalla is the first one.")
        steps = [("Get a token from BotFather",
                  "Open @BotFather on Telegram, send /newbot, pick a name, and copy the long "
                  "token it sends back. It looks like 123456789:AAE-xxxxxxxx."),
                 ("Paste the token and choose a type",
                  "In your dashboard, paste the token, name your business, and pick a bot type "
                  "(store, bookings, FAQ…). We verify the token as you type."),
                 ("Start it and try it yourself",
                  "Press Start, then open your bot on Telegram and send it a message. "
                  "What you see is exactly what your customer sees.")]
        outro = "Stuck on any step? Reply to this email — a person reads it."
        label = "Open my dashboard"
    else:
        subject = "أهلاً بك في BotYalla — بوتك في 3 خطوات"
        intro = (f"أهلاً {username}، حسابك جاهز. بناء أول بوت يستغرق خمس دقائق تقريباً، "
                 f"والخطوة الوحيدة خارج المنصة هي الأولى.")
        steps = [("احصل على توكن من BotFather",
                  "افتح @BotFather على تليجرام، أرسل /newbot، اختر اسماً، وانسخ التوكن الطويل "
                  "الذي يرسله. شكله هكذا: 123456789:AAE-xxxxxxxx"),
                 ("الصق التوكن واختر نوع البوت",
                  "في لوحتك، الصق التوكن واكتب اسم نشاطك واختر النوع (متجر · حجوزات · أسئلة "
                  "شائعة…). نتحقّق من التوكن وأنت تكتب."),
                 ("شغّله وجرّبه بنفسك",
                  "اضغط «تشغيل»، ثم افتح بوتك على تليجرام وأرسل له رسالة. ما تراه هو نفسه "
                  "ما يراه زبونك.")]
        outro = "وقفت في أي خطوة؟ ردّ على هذه الرسالة — يقرأها إنسان."
        label = "افتح لوحتي"
    items = "".join(
        f'<tr><td valign="top" style="padding:10px 0 10px 0;">'
        f'<span style="display:inline-block;width:26px;height:26px;line-height:26px;'
        f'text-align:center;border-radius:8px;background:#0EA5E9;color:#fff;font-weight:800;">{i}</span>'
        f'</td><td style="padding:10px 12px;">'
        f'<b style="color:#05070D;">{escape(t)}</b><br>'
        f'<span style="color:#374151;">{escape(d)}</span></td></tr>'
        for i, (t, d) in enumerate(steps, 1))
    body = (f"<p>{escape(intro)}</p>"
            f'<table role="presentation" cellspacing="0" cellpadding="0">{items}</table>'
            + (_button(link, label) if link else "")
            + f'<p style="color:#6B7280;font-size:13px;">{escape(outro)}</p>')
    text = (intro + "\n\n"
            + "\n\n".join(f"{i}. {t}\n   {d}" for i, (t, d) in enumerate(steps, 1))
            + (f"\n\n{link}" if link else "") + f"\n\n{outro}")
    return subject, _layout(lang, subject, body), text


def send_welcome(user_id, email, username, link=None, lang="ar"):
    """ترحيب best-effort بعد التسجيل. فشله لا يمنع إنشاء الحساب إطلاقاً."""
    try:
        if not email:
            return False
        return send_async(email, *welcome_email(username, link, lang))
    except Exception as e:
        log.error("welcome email failed for user #%s: %s", user_id, e)
        return False


def _date(ts):
    return _dt.datetime.fromtimestamp(int(ts)).strftime("%Y-%m-%d") if ts else "—"


def receipt_email(row, status, lang="ar"):
    """(subject, html, text) لإيصال دفعة بعد البتّ فيها."""
    en = lang == "en"
    # شحن المحفظة ليس باقة: بدون هذا السطر يقرأ العميل «باقة مجانية» على
    # إيصال دفع، لأن `plan_name` تُسقط أي معرّف مجهول إلى المجانية.
    if row.get("plan") == db.WALLET_PLAN:
        pname = "Marketing credit" if en else "رصيد الرسائل التسويقية"
    else:
        pname = plans.plan_name(row.get("plan"), "en" if en else "ar")
    amount = f"{float(row.get('amount') or 0):g} EGP"
    cycle = row.get("billing_cycle") or "monthly"
    cycle_l = ({"monthly": "Monthly", "annual": "Annual"} if en else
               {"monthly": "شهري", "annual": "سنوي"}).get(cycle, cycle)
    if status == "approved":
        subject = (f"Payment receipt #{row['id']} — {pname}" if en
                   else f"إيصال الدفعة #{row['id']} — باقة {pname}")
        title = "Payment approved ✅" if en else "تم اعتماد دفعتك ✅"
        if row.get("plan") == db.WALLET_PLAN:
            bal = row.get("wallet_after")
            bal_s = f"{(int(bal) / 100):g} EGP" if bal is not None else "—"
            rows = ([("Payment", f"#{row['id']}"), ("For", pname), ("Amount", amount),
                     ("New balance", bal_s)] if en else
                    [("رقم الدفعة", f"#{row['id']}"), ("البند", pname), ("المبلغ", amount),
                     ("الرصيد بعد الشحن", bal_s)])
            outro = ("Your credit is available now. Keep this email as your receipt." if en
                     else "رصيدك متاح الآن. احتفظ بهذه الرسالة كإيصال.")
        else:
            rows = ([("Payment", f"#{row['id']}"), ("Plan", pname), ("Amount", amount),
                     ("Billing", cycle_l), ("Active until", _date(row.get("expires_at")))] if en else
                    [("رقم الدفعة", f"#{row['id']}"), ("الباقة", pname), ("المبلغ", amount),
                     ("الدورة", cycle_l), ("ساري حتى", _date(row.get("expires_at")))])
            outro = ("Your subscription is active. Keep this email as your receipt." if en
                     else "اشتراكك مفعَّل الآن. احتفظ بهذه الرسالة كإيصال.")
    else:
        subject = (f"Payment #{row['id']} could not be verified" if en
                   else f"تعذّر التحقق من الدفعة #{row['id']}")
        title = "We couldn't verify your payment" if en else "لم نتمكن من التحقق من دفعتك"
        rows = ([("Payment", f"#{row['id']}"), ("Plan", pname), ("Amount", amount)] if en else
                [("رقم الدفعة", f"#{row['id']}"), ("الباقة", pname), ("المبلغ", amount)])
        outro = ("Please upload a clear screenshot of the transfer showing the amount and reference, "
                 "or reply to this email and we'll sort it out." if en else
                 "ارفع لقطة واضحة للتحويل يظهر فيها المبلغ والرقم المرجعي، أو راسلنا بالرد على "
                 "هذه الرسالة وسنحلّها معك.")
    table = "".join(f'<tr><td style="padding:6px 0;color:#6B7280;">{escape(k)}</td>'
                    f'<td style="padding:6px 12px;font-weight:700;">{escape(str(v))}</td></tr>'
                    for k, v in rows)
    html = _layout(lang, title, f'<table role="presentation" cellspacing="0" cellpadding="0">{table}</table>'
                                f"<p>{escape(outro)}</p>")
    text = title + "\n\n" + "\n".join(f"{k}: {v}" for k, v in rows) + "\n\n" + outro
    return subject, html, text


def send_payment_receipt(row, status):
    """إيصال بعد `finalize_payment` — من الويب ومن زرّ تليجرام معاً.
    **خارج المعاملة الذرّية:** يُستدعى بعد أن ثبتت التسوية، وفشله لا يمسّها."""
    try:
        u = db.get_user(row["user_id"])
        if not u or not u.get("email"):
            return False
        lang = db.get_setting(row["user_id"], "lang", "ar") or "ar"
        return send_async(u["email"], *receipt_email(row, status, lang))
    except Exception as e:
        log.error("receipt failed for payment #%s: %s", row.get("id"), e)
        return False
