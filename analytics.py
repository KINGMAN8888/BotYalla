"""القياس والتتبّع — GTM · GA4 · Meta Pixel · TikTok Pixel · Clarity.

كل المعرّفات تأتي من البيئة (`.env`)، والمبدأ الحاكم:
**بلا معرّف لا يُحقن سكربت ولا تُفتح CSP.**

الموقع يبقى على سياسته الضيّقة (`script-src 'self' 'nonce-…'` · `connect-src 'self'`)
حتى تُفعَّل أداة بعينها، فلا يحمّل زائرٌ ثمنَ أداة غير مستخدمة ولا تتّسع مساحة
الهجوم بلا مقابل. وتوسيع CSP يقع **لكل أداة على حدة** — ضبط Clarity وحده لا يفتح
نطاقات فيسبوك.

**معرّف مضبوط = الأداة تعمل.** كل أداة لها معرّف تُحقن بسكربتها المباشر، سواء
كان GTM مضبوطاً أم لا. هذا هو السلوك المتوقَّع: من يضع `META_PIXEL_ID` يقصد أن
يقيس بكسل ميتا، لا أن يبني وسماً في حاوية أخرى أولاً.

و`GTM_ID` يُحقن **بالإضافة** إليها، لأن الحاوية تُستعمل عادةً لأشياء أخرى
(وسوم تسويق، خرائط حرارة، تجارب) لا لتكرار البكسلات نفسها.

`GTM_MANAGES` لمنع الازدواج: لو أنشأت وسم ميتا **داخل** الحاوية، اكتب
`GTM_MANAGES=meta` فيتوقّف الحقن المباشر له ويبقى معرّفه مقروءاً لتوسيع CSP
(وسوم الحاوية تحتاج نطاقاتها مفتوحة وإلا حُجبت بصمت). القيم: `ga4` · `meta` ·
`tiktok` · `clarity`، مفصولة بفواصل.

⚠️ لا تُضِف `'unsafe-inline'` إلى `script-src` مهما كان المزوّد يقترحه: كل سكربتاتنا
تحمل nonce، وفتح inline يُبطل الحماية الموثّقة في REVIEW.md §3.1 ويعيد ثغرة الحقن.
GTM وكل المزوّدين هنا يعملون بالـnonce بلا مشاكل.

الأحداث: `queue()` تضعها في الجلسة، و`drain()` تفرغها في حمولة الصفحة التالية —
لأن التسجيل والدفع ينتهيان بـ redirect، فحدث يُطلق في نفس الطلب لا يصل المتصفح.
"""
import os

# اسم المفتاح في الجلسة. قصير لأن كوكي الجلسة موقّعة وتُرسل مع كل طلب.
_SESSION_KEY = "_tr"
# سقف الطابور: حارس ضد تضخّم الكوكي لو حدث تسريب في مسار ما.
_MAX_QUEUED = 8


def _env(name):
    return os.getenv(name, "").strip()


def ids():
    """المعرّفات المضبوطة. تُقرأ عند كل نداء لا عند الاستيراد، فاختبارات
    البيئة تستطيع ضبطها بعد تحميل الوحدة (نفس نمط بقية إعدادات المنصة)."""
    return {
        "gtm":     _env("GTM_ID"),            # GTM-XXXXXXX
        "ga4":     _env("GA4_ID"),            # G-XXXXXXXXXX
        "meta":    _env("META_PIXEL_ID"),     # 15 رقماً
        "tiktok":  _env("TIKTOK_PIXEL_ID"),   # CXXXXXXXXXXXXXXXXXXX
        "clarity": _env("CLARITY_ID"),        # 10 محارف
    }


def configured():
    """هل أي أداة مضبوطة؟ بلا ذلك لا يُحقن شيء ولا تتغيّر CSP."""
    return any(ids().values())


# الأدوات التي يمكن لـ GTM أن يتولّاها بدل الحقن المباشر. GTM نفسه ليس منها.
_MANAGEABLE = ("ga4", "meta", "tiktok", "clarity")


def gtm_manages():
    """الأدوات التي أنشأت لها وسوماً **داخل** حاوية GTM.

    بلا معنى بلا `GTM_ID` — تُتجاهل عندئذ، وإلا أوقفت الحقن المباشر بلا أن
    يحلّ محلّه شيء، فيتوقّف القياس تماماً بلا رسالة."""
    if not _env("GTM_ID"):
        return set()
    return {p.strip().lower() for p in _env("GTM_MANAGES").split(",")
            if p.strip().lower() in _MANAGEABLE}


def inject():
    """ما يُحقن مباشرةً في الصفحة — هذا ما يقرؤه القالب.

    مثل `ids()` لكن بمعرّف فارغ لكل أداة تتولّاها الحاوية، فيتوقّف حقنها
    المباشر. `ids()` تبقى كاملة لأن `csp_sources()` تحتاج نطاق كل أداة مضبوطة
    حتى لو كان وسمها داخل الحاوية — وإلا حجبته CSP بصمت."""
    managed = gtm_manages()
    return {k: ("" if k in managed else v) for k, v in ids().items()}


def csp_sources():
    """مصادر CSP الإضافية — لكل أداة مضبوطة مصادرها هي وحدها.

    تُدمج في `_CSP` في app.py عند الإقلاع. `img-src` غير مذكور هنا لأنه يسمح
    بـ`https:` أصلاً (صور أصحاب البوتات)، فبكسلات الصور تمرّ بلا توسيع."""
    i = ids()
    script, connect, frame = [], [], []

    # GTM و gtag.js يُقدَّمان من نفس النطاق.
    if i["gtm"] or i["ga4"]:
        script.append("https://www.googletagmanager.com")
        connect.append("https://www.googletagmanager.com")
    if i["gtm"]:
        # وسم <noscript> في GTM إطارٌ من نفس النطاق. `frame-ancestors 'none'`
        # يخصّ من يؤطّرنا نحن، فلا تعارض بينهما.
        frame.append("https://www.googletagmanager.com")
    if i["ga4"] or i["gtm"]:
        connect += ["https://www.google-analytics.com", "https://analytics.google.com",
                    "https://*.google-analytics.com", "https://*.analytics.google.com"]
    if i["meta"]:
        script.append("https://connect.facebook.net")
        connect += ["https://connect.facebook.net", "https://www.facebook.com"]
    if i["tiktok"]:
        script += ["https://analytics.tiktok.com", "https://sf16-scmcdn-va.ibytedtos.com"]
        connect += ["https://analytics.tiktok.com", "https://analytics-sg.tiktok.com"]
    if i["clarity"]:
        script.append("https://www.clarity.ms")
        connect += ["https://*.clarity.ms", "https://c.bing.com"]

    out = {}
    if script:
        out["script-src"] = script
    if connect:
        out["connect-src"] = connect
    if frame:
        out["frame-src"] = frame
    return out


# ---------- الأحداث ----------

def queue(session, event, **params):
    """يضع حدثاً ليُطلق على **الصفحة التالية** التي يراها المستخدم.

    لماذا الجلسة لا الطلب الحالي؟ لأن التسجيل وإنشاء البوت ورفع الإيصال كلها
    تنتهي بـ`redirect`، والصفحة التي تُرسم في نفس الطلب لا تصل المتصفح أصلاً.
    القيم البسيطة فقط (نص/رقم) — الكوكي موقّعة لا مشفّرة."""
    if not configured():
        return
    q = session.get(_SESSION_KEY) or []
    if len(q) >= _MAX_QUEUED:
        return
    q.append({"event": event, "params": {k: v for k, v in params.items() if v is not None}})
    session[_SESSION_KEY] = q


def drain(session):
    """يفرغ الطابور ويرجّعه — نداء واحد لكل صفحة مرسومة، فلا يتكرّر حدث."""
    if not session.get(_SESSION_KEY):
        return []
    return session.pop(_SESSION_KEY)


# ---------- الحسابات الاجتماعية ----------
# نطاقات معروفة فقط. الرابط يظهر في تذييل الموقع وفي `sameAs` داخل البيانات
# المنظّمة، وكلاهما يُقرأ كتزكية منّا — فقيمة مكتوبة خطأً في `.env` لا يجب أن
# تتحوّل إلى رابط حيّ لأي جهة.
_SOCIAL_HOSTS = {
    "facebook.com": "facebook", "instagram.com": "instagram", "tiktok.com": "tiktok",
    "linkedin.com": "linkedin", "youtube.com": "youtube", "t.me": "telegram",
    "x.com": "x", "twitter.com": "x", "wa.me": "whatsapp", "github.com": "github",
}


def social_links():
    """روابط حسابات المنصة من `SOCIAL_LINKS` (مفصولة بفواصل).

    بلا ضبط ترجع فارغة: لا أيقونات في التذييل ولا `sameAs` في السكيما — وهذا
    أصحّ من روابط تشير إلى حسابات لم تُنشأ بعد."""
    out, seen = [], set()
    for raw in _env("SOCIAL_LINKS").split(","):
        url = raw.strip()
        if not url.startswith("https://") or url in seen:
            continue
        host = url.split("/", 3)[2].lower()
        host = host[4:] if host.startswith("www.") else host
        name = _SOCIAL_HOSTS.get(host)
        if name:
            seen.add(url)
            out.append({"name": name, "url": url})
    return out
