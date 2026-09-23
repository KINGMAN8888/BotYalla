"""BotYalla — إرسال الإيميل عبر SMTP + قوالب الرسائل بهوية العلامة.

**best-effort:** لا ترمي أي دالة هنا استثناءً أبداً. الإيميل ليس مساراً حرجاً —
فشل الإرسال يُسجَّل ولا يُسقط الطلب ولا التسوية المالية.

الإعداد من `.env`:
    SMTP_HOST · SMTP_PORT (587) · SMTP_USER · SMTP_PASS · SMTP_FROM
    SMTP_TLS = starttls (افتراضي) | ssl | none
    SMTP_REPLY_TO (اختياري) — وإلا «إيميل الدعم» من إعدادات المنصة
بلا `SMTP_HOST` و`SMTP_FROM` لا يُرسل شيء (يُسجَّل «غير مضبوط» فقط).

**التصميم:** كل رسالة تمرّ بـ `_layout` — رأس داكن بشعار العلامة وتدرّجها
(بنفسجي ← سماوي ← أخضر مائي كالموقع)، بطاقة بيضاء للمحتوى، وتذييل داكن. الشعار
PNG مضمَّن في الرسالة نفسها (`cid:`) لا رابط خارجي: Gmail وOutlook لا يعرضان SVG،
ويحجبان الصور الخارجية افتراضياً — والمضمَّن يظهر فوراً وبلا PUBLIC_URL.
الأنماط داخلية (inline) لأن برامج البريد تتجاهل معظم <style>.
"""
import hashlib, hmac, logging, os, re, secrets, smtplib, ssl, threading, time, datetime as _dt
from email.message import EmailMessage
from email.utils import make_msgid
from html import escape
from urllib.parse import urlsplit, urlencode

import database as db
import plans

log = logging.getLogger("mailer")

# معدّل محدود لكل عنوان — حتى لا تصبح المنصة أداة إغراق صندوق بريد أحد.
RATE_LIMIT, RATE_WINDOW = 5, 3600
_sent = {}                    # address -> [timestamps]
_lock = threading.Lock()

# الاختبارات تضبطها True ليجري الإرسال في نفس الخيط.
SYNC = False

# الشعار المضمَّن: `cid:` في القالب ↔ Content-ID للصورة المرفقة (RFC 2392).
MARK_CID = "by-mark@botyalla"
MARK_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "brand", "email-mark.png")
_mark_cache = []

# ترويسات إضافية مسموحة من المستدعي (حملات البريد) — لا ترويسة حرة.
_EXTRA_HEADERS = ("List-Unsubscribe", "List-Unsubscribe-Post", "X-BotYalla-Campaign")


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


def _one_addr(v):
    """عنوان واحد صالح أو "" — لا قوائم ولا حقن ترويسات."""
    v = (v or "").strip()
    return v if v and "@" in v and not any(ch in v for ch in "\r\n,;<>") else ""


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


def _mark():
    """بايتات الشعار (مرة واحدة). ملف مفقود ⇒ b"" والرسالة تُرسل بلا صورة."""
    if not _mark_cache:
        try:
            with open(MARK_PATH, "rb") as f:
                _mark_cache.append(f.read())
        except OSError:
            log.warning("email mark missing: %s", MARK_PATH)
            _mark_cache.append(b"")
    return _mark_cache[0]


def _support_email():
    try:
        v = (db.get_platform("support_email", "") or "").strip()
    except Exception:
        v = ""
    return _one_addr(v) or "info@botyalla.com"


def _reply_to():
    """المرسل no-reply بلا صندوق وارد — والترحيب يقول «ردّ على هذه الرسالة». بلا Reply-To
    يضيع ردّ العميل. SMTP_REPLY_TO إن ضُبط، وإلا إيميل الدعم من إعدادات المنصة."""
    return _one_addr(os.getenv("SMTP_REPLY_TO", "")) or _support_email()


def send_mail(to, subject, html, text=None, headers=None):
    """يرسل رسالة. يرجّع True عند النجاح، وFalse في أي حالة أخرى — لا يرمي.
    `headers`: ترويسات حملات البريد فقط (`_EXTRA_HEADERS`)."""
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
        rt = _reply_to()
        if rt and rt.lower() != to.lower():
            msg["Reply-To"] = rt
        msg["Message-ID"] = make_msgid(domain=cfg["from"].rpartition("@")[2].strip("> ") or None)
        for k, v in (headers or {}).items():
            if k in _EXTRA_HEADERS and v and not any(ch in str(v) for ch in "\r\n"):
                msg[k] = str(v)
        msg.set_content(text or subject)
        msg.add_alternative(html, subtype="html")
        if f"cid:{MARK_CID}" in html and _mark():
            # multipart/related: الصورة جزء من الرسالة، لا مرفق يظهر في شريط المرفقات
            msg.get_payload()[1].add_related(_mark(), "image", "png", cid=f"<{MARK_CID}>",
                                             disposition="inline", filename="botyalla.png")
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


# ---------------------------------------------------------------- الروابط
def site_base():
    """أصل الموقع من `PUBLIC_URL` وحدها (AGENTS.md §14) — None بلا إعداد.
    لا رابط في أي إيميل يُبنى من ترويسة Host."""
    base = (os.getenv("PUBLIC_URL") or "").strip().rstrip("/")
    return base if base.startswith(("https://", "http://")) else None


def site_url(path):
    base = site_base()
    return base + path if base else None


def _unsub_key():
    """مفتاح روابط إلغاء الاشتراك — منفصل عن FLASK_SECRET عمداً: تدوير سرّ الجلسات لا
    يُبطل روابط رسائل وصلت صناديق الناس. يُولَّد مرة واحدة ويُحفظ (INSERT OR IGNORE:
    خيطان يولّدانه معاً يقرآن نفس القيمة)."""
    return db.platform_setdefault("email_unsub_key", secrets.token_hex(32))


def unsub_token(user_id):
    return hmac.new(_unsub_key().encode(), f"unsub:{int(user_id)}".encode(),
                    hashlib.sha256).hexdigest()[:32]


def check_unsub(user_id, token):
    try:
        return hmac.compare_digest(unsub_token(user_id), str(token or ""))
    except Exception:
        return False


def unsub_url(user_id):
    base = site_base()
    return f"{base}/email/unsubscribe/{int(user_id)}/{unsub_token(user_id)}" if base else None


# ---------------------------------------------------------------- الهوية
_BRAND = "BotYalla"
INK, BODY, MUTED, LINE, SOFT = "#0B1020", "#2A3245", "#6B7280", "#E6E9F2", "#F5F7FB"
LINK = "#5B4BDB"
_GRAD = "linear-gradient(90deg,#7C6CF6 0%,#22D3EE 55%,#2DD4A7 100%)"

# شارة نوع الرسالة أعلى العنوان: (رمز، عربي، إنجليزي، لون النص، الخلفية)
_BADGES = {
    "security": ("🔐", "أمان الحساب", "Account security", "#4C3FD1", "#EEEBFF"),
    "welcome":  ("👋", "أهلاً بك", "Welcome aboard", "#0F766E", "#E3FAF4"),
    "receipt":  ("🧾", "إيصال دفع", "Payment receipt", "#0F766E", "#E3FAF4"),
    "payment":  ("⚠️", "مراجعة الدفع", "Payment review", "#9A5B00", "#FFF4DB"),
    "support":  ("💬", "الدعم الفني", "Support", "#0369A1", "#E4F4FD"),
    "reminder": ("⏰", "تذكير الاشتراك", "Subscription reminder", "#9A5B00", "#FFF4DB"),
    "news":     ("📣", "جديد BotYalla", "BotYalla news", "#4C3FD1", "#EEEBFF"),
    "offer":    ("🎁", "عرض خاص", "Special offer", "#BE185D", "#FDECF5"),
    "service":  ("🛠️", "إشعار خدمة", "Service notice", "#0369A1", "#E4F4FD"),
}


def _rtl(lang):
    return lang != "en"


def _p(html, muted=False, small=False, last=False):
    color = MUTED if muted else BODY
    size = "13px" if small else "15px"
    return (f'<p style="margin:0 0 {0 if last else 14}px;color:{color};font-size:{size};'
            f'line-height:1.85;">{html}</p>')


def _button(href, label):
    """زر «مضاد للرصاص»: خلية جدول بلون احتياطي + تدرّج العلامة للبرامج التي تدعمه."""
    return ('<table role="presentation" cellspacing="0" cellpadding="0" border="0" style="margin:24px 0 8px;">'
            '<tr><td bgcolor="#6D5DF5" style="border-radius:12px;background-color:#6D5DF5;'
            'background-image:linear-gradient(100deg,#6D5DF5 0%,#0891B2 100%);">'
            f'<a href="{escape(href, quote=True)}" target="_blank" style="display:inline-block;'
            'padding:14px 30px;font-size:15px;font-weight:800;color:#FFFFFF;text-decoration:none;'
            f'border-radius:12px;">{escape(label)}</a></td></tr></table>')


def _link_hint(href, lang):
    """الرابط نصاً تحت الزر: بعض برامج البريد (أو فلاتر الشركات) تُعطّل الأزرار."""
    lead = "Button not working? Paste this link into your browser:" if lang == "en" else \
           "الزر لا يعمل؟ انسخ هذا الرابط في المتصفح:"
    return (f'<p style="margin:10px 0 0;color:{MUTED};font-size:12px;line-height:1.7;">{escape(lead)}<br>'
            f'<a href="{escape(href, quote=True)}" style="color:{LINK};word-break:break-all;" dir="ltr">'
            f'{escape(href)}</a></p>')


def _note(html, lang, tone="info"):
    """صندوق ملاحظة بشريط لوني على جهة بداية السطر."""
    bar, bg = {"info": ("#7C6CF6", "#F4F2FF"), "ok": ("#2DD4A7", "#ECFBF6"),
               "warn": ("#F5A524", "#FFF7E6")}[tone]
    side = "right" if _rtl(lang) else "left"
    return (f'<table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" '
            f'style="margin:20px 0 4px;"><tr><td style="background:{bg};border-{side}:4px solid {bar};'
            f'border-radius:10px;padding:14px 16px;color:{BODY};font-size:13.5px;line-height:1.8;">'
            f'{html}</td></tr></table>')


def _facts(rows, lang):
    """جدول حقائق (إيصال/تفاصيل) داخل صندوق ناعم."""
    align = "right" if _rtl(lang) else "left"
    oalign = "left" if _rtl(lang) else "right"
    cells = "".join(
        f'<tr><td style="padding:11px 16px;color:{MUTED};font-size:13.5px;text-align:{align};'
        f'{"" if i == len(rows) - 1 else f"border-bottom:1px solid {LINE};"}">{escape(k)}</td>'
        f'<td style="padding:11px 16px;color:{INK};font-size:14px;font-weight:700;text-align:{oalign};'
        f'{"" if i == len(rows) - 1 else f"border-bottom:1px solid {LINE};"}">{escape(str(v))}</td></tr>'
        for i, (k, v) in enumerate(rows))
    return (f'<table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" '
            f'style="margin:6px 0 18px;background:{SOFT};border:1px solid {LINE};border-radius:12px;'
            f'border-collapse:separate;">{cells}</table>')


def _coupon(code, lang):
    label = "Your code" if lang == "en" else "كود الخصم"
    hint = "Enter it at checkout." if lang == "en" else "اكتبه في صفحة الدفع."
    return ('<table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" '
            'style="margin:20px 0 6px;"><tr><td align="center" style="border:2px dashed #7C6CF6;'
            'border-radius:14px;background:#F6F4FF;padding:16px 12px;">'
            f'<div style="font-size:12px;font-weight:700;color:#4C3FD1;letter-spacing:.5px;">{escape(label)}</div>'
            f'<div dir="ltr" style="font-family:Consolas,\'Courier New\',monospace;font-size:26px;font-weight:800;'
            f'letter-spacing:4px;color:{INK};margin:6px 0 4px;">{escape(code)}</div>'
            f'<div style="font-size:12px;color:{MUTED};">{escape(hint)}</div></td></tr></table>')


def _badge(kind, lang):
    b = _BADGES.get(kind)
    if not b:
        return ""
    icon, ar, en, fg, bg = b
    return (f'<span style="display:inline-block;background:{bg};color:{fg};font-size:12px;'
            f'font-weight:800;padding:5px 12px;border-radius:999px;">{icon}&nbsp; '
            f'{escape(en if lang == "en" else ar)}</span>')


def _layout(lang, title, body_html, badge=None, preheader="", why=None, unsubscribe=None):
    """الغلاف الموحّد لكل رسائل المنصة.

    `preheader`: السطر الرمادي بجانب العنوان في صندوق الوارد (مخفي داخل الرسالة).
    `why` + `unsubscribe`: لماذا وصلت الرسالة ورابط الإلغاء — إلزاميان في رسائل الأخبار."""
    rtl = _rtl(lang)
    d, align, oalign = ("rtl", "right", "left") if rtl else ("ltr", "left", "right")
    font = ("'Segoe UI',Tahoma,'Noto Sans Arabic',Arial,sans-serif" if rtl
            else "'Segoe UI',Roboto,Helvetica,Arial,sans-serif")
    base = site_base()
    host = urlsplit(base).netloc if base else ""
    en = lang == "en"

    pre = ""
    if preheader:
        # الحشو يمنع برامج البريد من سحب أول سطر من المتن ليكمل المعاينة
        pre = (f'<div style="display:none;max-height:0;overflow:hidden;opacity:0;mso-hide:all;'
               f'font-size:1px;line-height:1px;color:#EEF1F7;">{escape(preheader)}'
               + "&#847;&zwnj;&nbsp;" * 60 + "</div>")

    head_side = (f'<a href="{escape(base, quote=True)}" target="_blank" dir="ltr" '
                 f'style="color:#8B96B5;font-size:12px;text-decoration:none;">{escape(host)}</a>'
                 if base else "")
    links = ""
    if base:
        items = ([("Website", "/"), ("Pricing", "/pricing"), ("Support", "/support"), ("Privacy", "/privacy")]
                 if en else [("الموقع", "/"), ("الأسعار", "/pricing"), ("الدعم", "/support"),
                             ("الخصوصية", "/privacy")])
        links = ('<p style="margin:0 0 10px;font-size:12.5px;line-height:1.9;">' + " &nbsp;·&nbsp; ".join(
            f'<a href="{escape(base + path, quote=True)}" target="_blank" style="color:#7DE3F4;'
            f'text-decoration:none;font-weight:700;">{escape(lbl)}</a>' for lbl, path in items) + "</p>")
    tagline = ("A bot that replies, sells and books — on Telegram and WhatsApp." if en
               else "بوت يرد ويبيع ويحجز على تليجرام وواتساب.")
    contact = ("Questions? Just reply, or write to" if en else "عندك سؤال؟ ردّ على الرسالة أو راسلنا على")
    foot_why = ""
    if why or unsubscribe:
        un = ""
        if unsubscribe:
            un = (f' <a href="{escape(unsubscribe, quote=True)}" target="_blank" style="color:#AEB9D4;'
                  f'text-decoration:underline;">{"Unsubscribe" if en else "إلغاء الاشتراك"}</a>')
        foot_why = (f'<p style="margin:12px 0 0;padding-top:12px;border-top:1px solid #1C2335;'
                    f'color:#6B7699;font-size:11.5px;line-height:1.8;">{escape(why or "")}{un}</p>')

    return f"""<!doctype html>
<html lang="{'en' if en else 'ar'}" dir="{d}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="light">
<meta name="supported-color-schemes" content="light">
<title>{escape(title)} · {_BRAND}</title>
<style>
  @media (max-width:620px) {{
    .by-wrap {{ padding:14px 8px !important; }}
    .by-px {{ padding-left:22px !important; padding-right:22px !important; }}
    .by-h1 {{ font-size:21px !important; }}
  }}
</style>
</head>
<body style="margin:0;padding:0;background:#EEF1F7;-webkit-text-size-adjust:100%;">
{pre}
<table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" bgcolor="#EEF1F7" style="background:#EEF1F7;">
<tr><td align="center" class="by-wrap" style="padding:32px 12px;font-family:{font};">
<table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="max-width:600px;">

<tr><td class="by-px" bgcolor="#05070D" style="background-color:#05070D;background-image:linear-gradient(135deg,#231A55 0%,#05070D 55%,#06303A 100%);border-radius:18px 18px 0 0;padding:24px 32px;">
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" dir="{d}"><tr>
    <td style="text-align:{align};">
      <img src="cid:{MARK_CID}" width="40" height="43" alt="" style="display:inline-block;vertical-align:middle;border:0;outline:none;">
      <span dir="ltr" style="display:inline-block;vertical-align:middle;margin:0 10px;font-size:23px;font-weight:800;letter-spacing:-.3px;color:#F2F5FC;">Bot<span style="color:#22D3EE;">Yalla</span></span>
    </td>
    <td style="text-align:{oalign};vertical-align:middle;">{head_side}</td>
  </tr></table>
</td></tr>
<tr><td height="4" style="height:4px;line-height:4px;font-size:0;background-color:#22D3EE;background-image:{_GRAD};">&nbsp;</td></tr>

<tr><td class="by-px" dir="{d}" bgcolor="#FFFFFF" style="background:#FFFFFF;padding:34px 36px 30px;text-align:{align};color:{BODY};font-size:15px;line-height:1.85;">
{_badge(badge, lang) if badge else ""}
<h1 class="by-h1" style="margin:{'14px' if badge else '0'} 0 14px;font-size:24px;line-height:1.45;font-weight:800;color:{INK};">{escape(title)}</h1>
{body_html}
</td></tr>

<tr><td class="by-px" dir="{d}" bgcolor="#0B1020" style="background:#0B1020;border-radius:0 0 18px 18px;padding:24px 36px 26px;text-align:{align};">
  <p style="margin:0 0 10px;color:#C9D3EA;font-size:13px;font-weight:700;line-height:1.7;">
    <img src="cid:{MARK_CID}" width="20" height="21" alt="" style="display:inline-block;vertical-align:middle;border:0;">
    &nbsp;{escape(tagline)}</p>
  {links}
  <p style="margin:0;color:#8B96B5;font-size:12px;line-height:1.8;">{escape(contact)} <span dir="ltr" style="color:#C9D3EA;">{escape(_support_email())}</span></p>
  {foot_why}
</td></tr>

<tr><td align="center" style="padding:18px 12px 0;color:#98A2B8;font-size:11px;font-family:{font};">© {_dt.date.today().year} {_BRAND}</td></tr>
</table>
</td></tr></table>
</body></html>"""


# ---------------------------------------------------------------- القوالب
def reset_email(link, lang="ar", minutes=60):
    """(subject, html, text) لرابط استرجاع كلمة المرور."""
    if lang == "en":
        subject = "Reset your BotYalla password"
        title = "Set a new password"
        intro = "We received a request to reset the password for your BotYalla account."
        facts = f"The link works for {minutes} minutes and only once."
        note = "Didn't ask for this? Ignore this email — your password stays the same and no one can use it without access to your inbox."
        label = "Set a new password"
        pre = f"Your reset link — valid for {minutes} minutes."
    else:
        subject = "استرجاع كلمة مرور BotYalla"
        title = "اضبط كلمة مرور جديدة"
        intro = "وصلنا طلب لاسترجاع كلمة مرور حسابك على BotYalla."
        facts = f"الرابط صالح {minutes} دقيقة ولمرة واحدة فقط."
        note = "لم تطلب ذلك؟ تجاهل هذه الرسالة — كلمة مرورك تبقى كما هي، ولا يستطيع أحد استخدام الرابط دون الوصول لبريدك."
        label = "اضبط كلمة مرور جديدة"
        pre = f"رابط الاسترجاع — صالح {minutes} دقيقة."
    body = (_p(escape(intro)) + _p(f"⏱️ <b style=\"color:{INK};\">{escape(facts)}</b>")
            + _button(link, label) + _link_hint(link, lang) + _note(escape(note), lang, "info"))
    html = _layout(lang, title, body, badge="security", preheader=pre)
    text = f"{intro}\n{facts}\n\n{link}\n\n{note}"
    return subject, html, text


def welcome_email(username, link=None, lang="ar"):
    """(subject, html, text) لرسالة الترحيب بعد التسجيل.

    الخطوات الثلاث مكتوبة **داخل** الرسالة لا خلف رابط دليل. الطريق الأساسي الآن
    الإنشاء بضغطة (Bot Management Mode) — بلا BotFather ولا نسخ توكن؛ والطريق
    اليدوي (توكن من BotFather) مذكور كبديل. الرابط اختياري: بلا `PUBLIC_URL`
    تُرسل الرسالة بلا زرّ بدل ألا تُرسل (لا تحمل أي توكن).
    """
    en = lang == "en"
    if en:
        subject = "Welcome to BotYalla — your bot in 3 steps"
        title = f"Welcome, {username} 👋"
        intro = ("Your account is ready. Your first bot takes a few minutes and zero code — "
                 "here's the whole path:")
        steps = [("Create your bot in one tap",
                  "In your dashboard press “Create your Telegram bot in one tap” and type your business "
                  "name. Telegram opens a ready-made creation page — press Create and the bot appears in "
                  "your dashboard, linked to you. Prefer the manual way? Paste a token from @BotFather."),
                 ("Let the AI set it up",
                  "Describe your business to the setup agent. It asks a few questions and shows you the "
                  "design (store, bookings, customer service…) to approve before anything is applied."),
                 ("Start it and try it yourself",
                  "Press Start, then open your bot on Telegram and send it a message. "
                  "What you see is exactly what your customer sees.")]
        outro = "Stuck on any step? Reply to this email — a person reads it."
        label = "Open my dashboard"
        pre = "Your account is ready — here's how to launch your first bot."
    else:
        subject = "أهلاً بك في BotYalla — بوتك في 3 خطوات"
        title = f"أهلاً {username} 👋"
        intro = "حسابك جاهز. أول بوت يأخذ دقائق معدودة وبلا أي برمجة — وهذا الطريق كله:"
        steps = [("أنشئ بوتك بضغطة",
                  "من لوحتك اضغط «أنشئ بوتك على تليجرام بضغطة» واكتب اسم نشاطك، فيفتح تليجرام صفحة "
                  "إنشاء جاهزة — اضغط «إنشاء» فيظهر البوت في لوحتك مربوطاً بك. تفضّل الطريقة اليدوية؟ "
                  "الصق توكن من ‎@BotFather."),
                 ("خلّي الذكاء الاصطناعي يجهّزه",
                  "اوصف نشاطك لوكيل الإعداد، فيسألك أسئلة قليلة ويعرض عليك تصميم البوت (متجر · حجوزات · "
                  "خدمة عملاء…) لتوافق عليه قبل التطبيق."),
                 ("شغّله وجرّبه بنفسك",
                  "اضغط «تشغيل»، ثم افتح بوتك على تليجرام وأرسل له رسالة. ما تراه هو نفسه "
                  "ما يراه زبونك.")]
        outro = "وقفت في أي خطوة؟ ردّ على هذه الرسالة — يقرأها إنسان."
        label = "افتح لوحتي"
        pre = "حسابك جاهز — هذا طريق أول بوت لك."
    pad = "padding:12px 0 12px 14px;" if not en else "padding:12px 14px 12px 0;"
    items = "".join(
        f'<tr><td valign="top" width="44" style="{pad}">'
        f'<span style="display:inline-block;width:32px;height:32px;line-height:32px;text-align:center;'
        f'border-radius:10px;background-color:#6D5DF5;background-image:linear-gradient(135deg,#7C6CF6,#22D3EE);'
        f'color:#fff;font-weight:800;font-size:15px;">{i}</span></td>'
        f'<td style="padding:12px 0;{"" if i == len(steps) else f"border-bottom:1px solid {LINE};"}">'
        f'<b style="color:{INK};font-size:15px;">{escape(t)}</b><br>'
        f'<span style="color:{BODY};font-size:14px;line-height:1.8;">{escape(d)}</span></td></tr>'
        for i, (t, d) in enumerate(steps, 1))
    body = (_p(escape(intro))
            + f'<table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0">{items}</table>'
            + (_button(link, label) if link else "")
            + _note(escape(outro), lang, "ok"))
    text = (intro + "\n\n"
            + "\n\n".join(f"{i}. {t}\n   {d}" for i, (t, d) in enumerate(steps, 1))
            + (f"\n\n{link}" if link else "") + f"\n\n{outro}")
    return subject, _layout(lang, title, body, badge="welcome", preheader=pre), text


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
    wallet = row.get("plan") == db.WALLET_PLAN
    if wallet:
        pname = "Marketing credit" if en else "رصيد الرسائل التسويقية"
    elif db.addon_bot_id(row.get("plan")):
        pname = "Customer payments add-on (30 days)" if en else "إضافة تحصيل المدفوعات (30 يوماً)"
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
        if wallet:
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
            if row.get("carried_days"):
                rows.append(("Carried over", f"+{row['carried_days']} days from your previous plan")
                            if en else ("رصيد منقول", f"+{row['carried_days']} يوماً من باقتك السابقة"))
            outro = ("Your subscription is active. Keep this email as your receipt." if en
                     else "اشتراكك مفعَّل الآن. احتفظ بهذه الرسالة كإيصال.")
        badge, tone, intro = "receipt", "ok", ("Thank you — we've verified your transfer." if en
                                               else "شكراً لك — تحقّقنا من تحويلك.")
        link, label = site_url("/wallet" if wallet else "/billing"), ("Open billing" if en else "افتح الفواتير")
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
        badge, tone, intro = "payment", "warn", ("Nothing was charged twice — here's what we received:" if en
                                                 else "لم يُخصم منك شيء مرتين — هذه تفاصيل ما وصلنا:")
        link, label = site_url("/billing"), ("Upload a new receipt" if en else "ارفع إيصالاً جديداً")
    body = (_p(escape(intro)) + _facts(rows, lang) + _note(escape(outro), lang, tone)
            + (_button(link, label) if link else ""))
    html = _layout(lang, title, body, badge=badge, preheader=f"{pname} · {amount}")
    text = title + "\n\n" + "\n".join(f"{k}: {v}" for k, v in rows) + "\n\n" + outro
    return subject, html, text


def ticket_reply_email(t, body, lang="ar", link=None):
    """(subject, html, text) لرد فريق الدعم على تذكرة."""
    en = lang == "en"
    subject = f"Reply to your ticket #T{t['id']}" if en else f"رد على تذكرتك #T{t['id']}"
    title = "Our team replied" if en else "فريقنا ردّ عليك"
    intro = (f"About “{t['subject']}” (#T{t['id']}):" if en else f"بخصوص «{t['subject']}» (#T{t['id']}):")
    side = "right" if _rtl(lang) else "left"
    quote = (f'<div style="white-space:pre-wrap;background:{SOFT};border-{side}:4px solid #22D3EE;'
             f'border-radius:10px;padding:14px 16px;margin:4px 0 8px;color:{INK};font-size:14.5px;'
             f'line-height:1.85;">{escape(body)}</div>')
    html = _layout(lang, title,
                   _p(escape(intro), muted=True) + quote
                   + (_button(link, "Open support" if en else "افتح صفحة الدعم") if link else "")
                   + _p(escape("You can reply from the support page or directly to this email." if en
                               else "تقدر ترد من صفحة الدعم أو بالرد على هذه الرسالة مباشرة."),
                        muted=True, small=True, last=True),
                   badge="support", preheader=body[:110])
    text = f"{intro}\n\n{body}" + (f"\n\n{link}" if link else "")
    return subject, html, text


def send_ticket_reply(t, body, lang="ar"):
    """best-effort: الرد محفوظ ويظهر في صفحة الدعم أياً كان مصير الإيميل.
    True لو أُرسل للإرسال (SMTP مضبوط وللعميل إيميل)."""
    try:
        u = db.get_user(t["user_id"])
        if not configured() or not u or not u.get("email"):
            return False
        base = (os.getenv("PUBLIC_URL") or "").strip().rstrip("/")
        link = f"{base}/support" if base.startswith("https://") else None   # AGENTS.md §14
        return bool(send_async(u["email"], *ticket_reply_email(t, body, lang, link)))
    except Exception as e:
        log.error("ticket reply mail failed for #T%s: %s", t.get("id"), e)
        return False


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


def verify_email(code, link=None, lang="ar", minutes=60):
    """(subject, html, text) لكود تأكيد البريد + رابط بضغطة. الكود في العنوان كعادة
    المواقع الكبرى: يُقرأ من إشعار الموبايل دون فتح الرسالة."""
    en = lang == "en"
    if en:
        subject = f"{code} is your BotYalla verification code"
        title = "Confirm your email"
        intro = "Enter this code on the verification page to activate your BotYalla account:"
        or_btn = "Or confirm with one tap:"
        label = "Confirm my email"
        note = (f"The code and the button work for {minutes} minutes. Didn't create an account? "
                "Ignore this email — nothing happens without the code.")
        pre = f"Your code: {code} — valid for {minutes} minutes."
    else:
        subject = f"{code} كود تأكيد بريدك على BotYalla"
        title = "أكّد بريدك الإلكتروني"
        intro = "اكتب هذا الكود في صفحة التأكيد لتفعيل حسابك على BotYalla:"
        or_btn = "أو أكّد بضغطة واحدة:"
        label = "أكّد بريدي"
        note = (f"الكود والزر صالحان {minutes} دقيقة. لم تنشئ حساباً؟ تجاهل هذه الرسالة — "
                "لا شيء يحدث بدون الكود.")
        pre = f"كودك: {code} — صالح {minutes} دقيقة."
    box = ('<table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" '
           'style="margin:8px 0 18px;"><tr><td align="center" style="background:#F4F2FF;border:1px solid #DCD6FF;'
           'border-radius:14px;padding:18px 12px;">'
           f'<div dir="ltr" style="font-family:Consolas,\'Courier New\',monospace;font-size:34px;font-weight:800;'
           f'letter-spacing:10px;color:{INK};">{escape(code)}</div></td></tr></table>')
    body = (_p(escape(intro)) + box
            + ((_p(escape(or_btn), muted=True, small=True, last=True) + _button(link, label)
                + _link_hint(link, lang)) if link else "")
            + _note(escape(note), lang, "info"))
    html = _layout(lang, title, body, badge="security", preheader=pre)
    text = f"{intro}\n\n{code}\n\n" + (f"{or_btn} {link}\n\n" if link else "") + note
    return subject, html, text


def assist_email(staff_name, lang="ar", link=None, via="user"):
    """(subject, html, text): فريق المنصة بدأ يعمل داخل حساب العميل بإذنه — شفافية كاملة."""
    en = lang == "en"
    if en:
        subject = "The BotYalla team is setting up your bot"
        title = "Our team is working on your bot"
        intro = (f"{staff_name} from the BotYalla team started setting up your bot inside your account"
                 + (" with the permission you gave." if via == "user" else " with the consent you gave us."))
        scope = ("They can only work on your bots (settings, replies, flow, media). They can't see your password, "
                 "payments, wallet or your customers' conversations, and every change is logged for you.")
        stop = "You can stop this permission any time from your dashboard."
        label = "Open my dashboard"
    else:
        subject = "فريق BotYalla بيجهّز بوتك دلوقتي"
        title = "فريقنا شغال على بوتك"
        intro = (f"{staff_name} من فريق BotYalla بدأ يجهّز بوتك جوه حسابك"
                 + (" بالإذن اللي أنت اديته." if via == "user" else " بموافقتك اللي بلّغتنا بيها."))
        scope = ("بيشتغل على البوتات بس (الإعدادات والردود والخطوات والصور). مش بيشوف كلمة السر ولا المدفوعات "
                 "ولا الرصيد ولا محادثات عملائك، وكل تعديل بيتسجّل وتقدر تشوفه.")
        stop = "تقدر توقف الإذن في أي وقت من لوحة التحكم."
        label = "افتح لوحة التحكم"
    body = _p(escape(intro)) + _p(escape(scope), muted=True) + (_button(link, label) if link else "") + \
        _note(escape(stop), lang, "info")
    html = _layout(lang, title, body, badge="security", preheader=intro[:90])
    return subject, html, f"{intro}\n\n{scope}\n\n{stop}" + (f"\n\n{link}" if link else "")


def expiry_email(kind, plan_name, date, lang="ar", link=None):
    """(subject, html, text) لتذكير انتهاء الاشتراك: pre3 · pre1 · expired.
    سياسة الخصوصية تعد بتذكير الانتهاء بالبريد — هذا هو (من حلقة التذكيرات في bot_manager)."""
    en = lang == "en"
    if kind == "expired":
        subject = (f"Your {plan_name} plan has expired" if en else f"انتهى اشتراكك في باقة {plan_name}")
        title = "Your subscription has ended" if en else "انتهى اشتراكك"
        intro = (f"Your {plan_name} plan ended on {date}. Your bots may stop until you renew — "
                 f"everything you built (bots, settings, customers) is kept." if en else
                 f"انتهت باقتك {plan_name} في {date}. قد تتوقف بوتاتك حتى تجدّد — وكل ما بنيته "
                 f"(البوتات والإعدادات والعملاء) محفوظ كما هو.")
        tone = "warn"
    else:
        days = "tomorrow" if (kind == "pre1" and en) else ("غداً" if kind == "pre1" else
                                                           ("in 3 days" if en else "خلال 3 أيام"))
        subject = (f"Your {plan_name} plan expires {days}" if en else
                   f"اشتراكك في باقة {plan_name} ينتهي {days}")
        title = "Your subscription ends soon" if en else "اشتراكك ينتهي قريباً"
        intro = (f"Your {plan_name} plan is active until {date}. Renew before then so your bots keep "
                 f"answering customers without a pause." if en else
                 f"باقتك {plan_name} سارية حتى {date}. جدّد قبلها لتستمر بوتاتك في الرد على عملائك بلا توقف.")
        tone = "info"
    rows = ([("Plan", plan_name), ("Ends" if kind != "expired" else "Ended", date)] if en else
            [("الباقة", plan_name), ("ينتهي في" if kind != "expired" else "انتهى في", date)])
    label = "Renew my plan" if en else "جدّد اشتراكي"
    how = ("Pay with Vodafone Cash, InstaPay or bank transfer and upload the receipt — activation follows the review."
           if en else "ادفع بفودافون كاش أو انستاباي أو تحويل بنكي وارفع الإيصال — التفعيل بعد المراجعة.")
    body = (_p(escape(intro)) + _facts(rows, lang) + (_button(link, label) if link else "")
            + _note(escape(how), lang, tone))
    html = _layout(lang, title, body, badge="reminder", preheader=subject)
    text = f"{intro}\n\n" + "\n".join(f"{k}: {v}" for k, v in rows) + (f"\n\n{link}" if link else "") + f"\n\n{how}"
    return subject, html, text


def weekly_report_email(rep, lang="ar"):
    """(subject, html, text) لتقرير المنصة الأسبوعي — لصاحب المنصة وحده.

    إشعار داخلي لا حملة: بلا رابط إلغاء اشتراك (ليس بريداً تسويقياً)، وكل نصّ
    يمرّ بـ`escape` لأن فيه أسماء مستخدمين وعيّنات رسائل عملاء."""
    en = lang == "en"
    p = rep.get("period", {})
    d = rep.get("delta", {})
    n = rep.get("now", {})
    title = "تقرير الأسبوع" if not en else "Your weekly report"
    subject = (f"BotYalla weekly report · {p.get('label', '')}" if en else
               f"تقرير BotYalla الأسبوعي · {p.get('label', '')}")
    intro = ("هذا ما حدث في المنصة خلال الفترة، ومقارنته بالفترة السابقة، وما يحتاج تدخّلك."
             if not en else
             "Here is what happened on the platform, how it compares with the period before, "
             "and what needs you.")

    def row(key, ar, e):
        v = d.get(key) or {}
        c = v.get("change")
        arrow = "" if c is None else f"  ({'+' if c > 0 else ''}{c}%)"
        return ((e if en else ar), f"{v.get('now', 0)}{arrow}")

    rows = [row("signups", "تسجيلات جديدة", "New signups"),
            row("bots_new", "بوتات جديدة", "New bots"),
            row("msgs_in", "رسائل عملاء", "Customer messages"),
            row("orders", "طلبات", "Orders"),
            row("revenue", "إيراد معتمد (ج.م)", "Approved revenue (EGP)"),
            (("Payments awaiting you" if en else "دفعات تنتظر قرارك"), n.get("pay_pending", 0)),
            (("Created but never started" if en else "بوتات أُنشئت ولم تُشغَّل"),
             n.get("bots_never_started", 0)),
            (("Live bots with no customer" if en else "بوتات شغّالة بلا عميل"),
             n.get("bots_started_silent", 0))]

    body = _p(escape(intro)) + _facts(rows, lang)

    tone = {"risk": "warn", "warn": "warn", "good": "ok", "info": "info"}
    for f in (rep.get("findings") or [])[:5]:
        html = (f'<b style="color:{INK};">{escape(f["title"])}</b>'
                + (f'<br>{escape(f["detail"])}' if f.get("detail") else "")
                + (f'<br>← {escape(f["action"])}' if f.get("action") else ""))
        body += _note(html, lang, tone.get(f["level"], "info"))

    conv = rep.get("conv") or {}
    if conv.get("unanswered"):
        head = ("Top unanswered customer questions" if en else "أكثر أسئلة العملاء بلا إجابة")
        items = "".join(f'<li style="margin:4px 0;">({q["v"]}×) {escape(q.get("sample") or q["k"])}</li>'
                        for q in conv["unanswered"][:5])
        body += (f'<p style="margin:22px 0 6px;color:{INK};font-size:15px;font-weight:800;">'
                 f'{escape(head)}</p>'
                 f'<ul style="margin:0;padding-inline-start:20px;color:{BODY};font-size:13.5px;'
                 f'line-height:1.9;">{items}</ul>')

    link = site_url("/admin/report")
    if link:
        body += _button(link, "افتح التقرير كاملاً" if not en else "Open the full report")

    html = _layout(lang, title, body, badge="service", preheader=subject)
    text = (f"{intro}\n\n" + "\n".join(f"{k}: {v}" for k, v in rows)
            + "\n\n" + "\n".join(f"- {f['title']} -> {f.get('action', '')}"
                                  for f in (rep.get("findings") or [])[:5])
            + (f"\n\n{link}" if link else ""))
    return subject, html, text


# ------------------------------------------------------------ حملات البريد
_URL_RE = re.compile(r"https://[^\s<>\"'()\[\]]+")
_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
_TRAIL = ".,،؛!?؟:"


def _fmt(s):
    return _BOLD_RE.sub(rf'<b style="color:{INK};">\1</b>', escape(s))


def _inline(raw):
    """سطر نص خام ⇒ HTML آمن: هروب كامل، ثم **عريض** وروابط https فقط."""
    out, pos = [], 0
    for m in _URL_RE.finditer(raw):
        url = m.group(0).rstrip(_TRAIL)
        out.append(_fmt(raw[pos:m.start()]))
        out.append(f'<a href="{escape(url, quote=True)}" target="_blank" style="color:{LINK};'
                   f'word-break:break-all;">{escape(url)}</a>')
        pos = m.start() + len(url)
    out.append(_fmt(raw[pos:]))
    return "".join(out)


def rich_text(text, lang="ar"):
    """نص الأدمن ⇒ فقرات ونقاط. سطر فارغ = فقرة جديدة، وسطر يبدأ بـ «- » أو «• » = نقطة.
    لا HTML خام من المدخل إطلاقاً — كل حرف يمرّ بالهروب."""
    html = []
    pad = "padding:0 0 8px 10px;" if _rtl(lang) else "padding:0 10px 8px 0;"
    for block in re.split(r"\n\s*\n", (text or "").strip()):
        para, items = [], []

        def flush_p():
            if para:
                html.append(_p("<br>".join(_inline(x) for x in para)))
                para.clear()

        def flush_ul():
            if items:
                rows = "".join(
                    f'<tr><td valign="top" width="18" style="{pad}"><span style="display:inline-block;'
                    f'width:8px;height:8px;border-radius:50%;background:#22D3EE;margin-top:10px;"></span></td>'
                    f'<td style="padding:0 0 8px;color:{BODY};font-size:15px;line-height:1.85;">{_inline(x)}</td></tr>'
                    for x in items)
                html.append(f'<table role="presentation" cellspacing="0" cellpadding="0" border="0" '
                            f'style="margin:0 0 14px;">{rows}</table>')
                items.clear()

        for line in block.split("\n"):
            s = line.strip()
            if s[:2] in ("- ", "• ", "* "):
                flush_p()
                items.append(s[2:].strip())
            elif s:
                flush_ul()
                para.append(s)
        flush_p()
        flush_ul()
    return "".join(html)


def _plain(text):
    return _BOLD_RE.sub(r"\1", text or "")


def _tracked(url, campaign_id):
    """روابط موقعنا في الحملة تحمل utm_source=email — فتظهر في «إحصائيات الزوار» ومصادر التسجيل."""
    base = site_base()
    if not url or not base or not campaign_id or urlsplit(url).netloc != urlsplit(base).netloc:
        return url
    q = urlencode({"utm_source": "email", "utm_medium": "email", "utm_campaign": f"c{campaign_id}"})
    return url + ("&" if "?" in url else "?") + q


def campaign_email(content, lang, name, kind="news", unsub=None, campaign_id=None):
    """(subject, html, text) لرسالة حملة. `content` كما حفظته لوحة الأدمن:
    {ar:{subject,preheader,title,body,cta}, en:{…}|None, url, code}. النسخة الإنجليزية
    لمن لغته en إن كُتبت، وإلا العربية للجميع. `{name}` ⇒ اسم المستلم."""
    en_part = content.get("en") or {}
    use_en = lang == "en" and (en_part.get("subject") or "").strip()
    part = en_part if use_en else (content.get("ar") or {})
    L = "en" if use_en else "ar"
    sub = lambda s: (s or "").replace("{name}", name or "")
    subject = sub(part.get("subject")).strip() or ("BotYalla news" if use_en else "أخبار BotYalla")
    title = sub(part.get("title")).strip() or subject
    body_raw = sub(part.get("body"))
    url = _tracked((content.get("url") or "").strip(), campaign_id)
    label = (part.get("cta") or "").strip() or ("Open" if use_en else "افتح")
    code = (content.get("code") or "").strip()

    body = rich_text(body_raw, L)
    if code:
        body += _coupon(code, L)
    if url:
        body += _button(url, label)
    if kind == "service":
        badge = "service"
        why = ("This is a service notice about your BotYalla account — it goes to every member and "
               "contains no marketing." if use_en else
               "هذا إشعار خدمة يخص حسابك على BotYalla — يصل كل المشتركين ولا يحتوي تسويقاً.")
    else:
        badge = "offer" if code else "news"
        why = ("You're getting this because you opted in to BotYalla news and offers." if use_en else
               "وصلتك هذه الرسالة لأنك اشتركت في أخبار وعروض BotYalla.")
    html = _layout(L, title, body, badge=badge, preheader=sub(part.get("preheader")).strip(),
                   why=why, unsubscribe=unsub)
    text = (title + "\n\n" + _plain(body_raw).strip()
            + (f"\n\n{'Code' if use_en else 'الكود'}: {code}" if code else "")
            + (f"\n\n{label}: {url}" if url else "")
            + f"\n\n— {why}"
            + (f"\n{'Unsubscribe' if use_en else 'إلغاء الاشتراك'}: {unsub}" if unsub else ""))
    return subject, html, text
