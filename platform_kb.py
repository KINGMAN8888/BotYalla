"""معرفة BotYalla الحيّة لبوت المنصة الرسمي (مساعد المبيعات والدعم على واتساب/تليجرام).

بوت يملكه حساب الإدارة ويفعّل «مساعد BotYalla الرسمي» (`cfg["platform_kb"]`) يأخذ
هذه الحقائق بدل معلومات نشاط يكتبها صاحبها يدوياً — فلا يختلف سعر يقوله البوت عن
سعر صفحة الباقات أبداً:

- الأسعار من `plans.PLANS` بعد تجاوزات المالك (`db.plan_overrides`) بنفس معادلة
  `app._plan_pricing` (سعر الشهر ← معامل السنة ← خصم الباقة). لا نستورد `app` هنا:
  في التطوير يعمل كـ`__main__` واستيراده يعيد تشغيل الوحدة كلها.
- الحدود من `plans.FEATURES` نفسها التي تُطبَّق بها.
- وسائل الدفع والتواصل من مفاتيح `_PUBLIC_PLAT` وحدها — لا توكنات ولا أسرار
  (AGENTS.md §3.35): ما يصل للنموذج قد يصل لأي عميل.
- الروابط من `PUBLIC_URL` (AGENTS.md §3.14)، وبدونه يُحذف الرابط لا يُخمَّن.

كل ما هنا حقائق عن المنتج كما هو في الكود — لا شهادات ولا أرقام عملاء (AGENTS.md §3.26)."""
import os
import re

import database as db
import plans

# ما يجوز أن يقوله البوت عن وسائل الدفع والتواصل — مرآة `app._PUBLIC_PLAT`
_PUBLIC_KEYS = ("vodafone_number", "instapay_handle", "support_email", "support_whatsapp",
                "support_telegram")

WELCOME = {
    "ar": ("أهلاً بيك في BotYalla 👋\n"
           "أنا المساعد الذكي للمنصة — بساعدك تعمل بوت يرد على عملائك ويبيع ويحجز "
           "على واتساب وتليجرام، من غير برمجة.\n"
           "محتاج إيه النهارده؟ اختار من القائمة 👇"),
    "en": ("Welcome to BotYalla 👋\n"
           "I'm the platform's AI assistant — I help you launch a bot that answers, sells and "
           "books for your customers on WhatsApp and Telegram, no coding needed.\n"
           "What do you need today? Pick from the menu 👇"),
}
STARTERS = {
    "ar": ["إيه هي BotYalla؟", "الباقات والأسعار", "ابدأ مجاناً"],
    "en": ["What is BotYalla?", "Plans & pricing", "Start for free"],
}


def _site():
    base = os.getenv("PUBLIC_URL", "").strip().rstrip("/")
    return base if base.startswith(("https://", "http://")) else ""


def _price(pid, ov):
    """نفس ترتيب `app._plan_pricing`: تجاوز المالك ← السنة ← خصم الباقة."""
    o = ov.get(pid) or {}
    monthly = float(plans.plan(pid)["price"] if o.get("price") is None else o["price"])
    disc = float(o.get("discount_pct") or 0)
    cut = lambda v: round(max(0.0, v * (1 - disc / 100.0)), 2)
    return cut(monthly), cut(plans.annual_of(monthly))


def _num(v):
    return f"{v:,.0f}" if float(v).is_integer() else f"{v:,.2f}"


def facts():
    """قاموس الحقائق الذي يُحقن في `<business>` لعقل البوت."""
    ov = db.plan_overrides()
    rows = []
    for pid in plans.ORDER:
        p = plans.PLANS[pid]
        m, a = _price(pid, ov)
        feats = list(p.get("features_ar") or [])
        if plans.ai_replies_limit(pid):
            feats.append(f"عقل البوت: {plans.ai_replies_limit(pid):,} رد ذكي شهرياً")
        feats.append(f"وكيل الإعداد الذكي: {plans.ai_setups_limit(pid):,} جلسة شهرياً")
        if plans.inbox_reply(pid):
            feats.append("صندوق الوارد والرد اليدوي على العملاء")
        rows.append({"plan": p["name_ar"],
                     "price_monthly_egp": "مجانية" if m <= 0 else _num(m),
                     "price_annual_egp": None if a <= 0 else _num(a),
                     "features": feats})

    plat = {k: (db.get_platform(k, "") or "").strip() for k in _PUBLIC_KEYS}
    # أرقام المحافظ لا تُقال في المحادثة: رقم فودافون كاش خط شخصي، ومكانه صفحة الدفع داخل الحساب
    # (تظهر للمشترك لحظة الدفع مع الإيصال). البوت يوجّه إليها بدل نشر الرقم لكل من يسأل.
    pay = ["فودافون كاش", "انستاباي", "تحويل بنكي",
           "بيانات التحويل بتظهر في صفحة الدفع جوه حسابك بعد ما تختار الباقة"]
    # واتساب التواصل = الرقم الرسمي للمنصة (رقم البوت الرسمي) وحده — لا أي رقم آخر
    support = {k: v for k, v in (("email", plat["support_email"]),
                                 ("whatsapp", official_wa_number()),
                                 ("telegram", plat["support_telegram"])) if v}

    site = _site()
    links = {}
    if site:
        links = {"site": site + "/", "signup": site + "/register", "pricing": site + "/pricing",
                 "privacy": site + "/privacy", "terms": site + "/terms"}

    return {
        "about": ("BotYalla منصة مصرية عربية/إنجليزية لإنشاء وتشغيل بوتات محادثة لأصحاب الأنشطة "
                  "التجارية على تليجرام وواتساب (WhatsApp Cloud API الرسمي من Meta) بدون أي برمجة. "
                  "البوت يرد على العملاء 24 ساعة، يعرض المنتجات، ياخد الطلبات والحجوزات، ويجمع بيانات "
                  "العملاء المهتمين، وصاحب النشاط يتابع كل حاجة من لوحة تحكم واحدة."),
        "how_it_works": [
            "سجّل حساب مجاني من الموقع (مفيش بطاقة ائتمان).",
            "اختار قالب جاهز أو احكي عن نشاطك لوكيل الإعداد الذكي فيصمّم البوت كامل ويعرضه عليك قبل الحفظ.",
            "تليجرام: إنشاء البوت بضغطة واحدة من داخل المنصة. واتساب: اربط رقمك بنفسك بضغطة من نافذة Meta الرسمية داخل المنصة، أو فريقنا يربطه لك (مشمول في باقات واتساب).",
            "شارك رابط البوت أو رمز QR أو ملصق جاهز للطباعة مع عملائك.",
        ],
        "features": [
            "7 قوالب جاهزة: باني محادثات · متجر صغير · حجوزات ومواعيد · خدمة عملاء · أسئلة شائعة · تقييم وآراء · دعم فني/تذاكر",
            "وكيل إعداد ذكي يصمّم البوت من وصف النشاط بالعامية",
            "عقل البوت: ردود ذكاء اصطناعي من معلومات نشاطك وحدها، مع تحويل لموظف عند الحاجة",
            "صندوق وارد لكل المحادثات مع إمكانية تولّي المحادثة يدوياً",
            "مكتبة صور وفيديو للترحيب والمنتجات",
            "حملات Broadcast وقوالب واتساب المعتمدة من Meta (الرسائل التسويقية على واتساب من محفظة رصيد منفصلة)",
            "تحليلات: مصادر العملاء والطلبات والحجوزات",
            "إضافة تحصيل مدفوعات عملائك بفودافون كاش وانستاباي لبوتات المتجر على تليجرام",
            "بوت مخصّص بالكامل عند الطلب",
        ],
        "plans": rows,
        "billing": ("الاشتراك شهري أو سنوي (السنوي بخصم 30%). الترقية تنقل قيمة الأيام المتبقية للباقة الجديدة. "
                    "الدفع يدوي: حوّل المبلغ وارفع صورة الإيصال من صفحة الاشتراك، والفريق يفعّل الاشتراك بعد المراجعة."),
        "payment_methods": pay,
        "requirements": ("الباقة المجانية وتليجرام بدون سجل تجاري. قناة واتساب الرسمية تحتاج سجل تجاري وبطاقة "
                         "ضريبية (شرط من Meta)."),
        "security": "توكنات البوتات مشفّرة، ولا نطلب أبداً كلمة سر فيسبوك أو كود تحقق من أي عميل.",
        "meta": ("BotYalla مزوّد خدمة تقنية (Tech Provider) معتمد من Meta لواتساب للأعمال: العميل يربط رقمه "
                 "بنفسه من نافذة Meta الرسمية بضغطة من داخل المنصة، ورسائل رقمه تُحاسب على حسابه في Meta مباشرة. "
                 "(لا تقل «شريك Meta» — الاعتماد مزوّد خدمة تقنية فقط.)"),
        "support": support,
        "links": links,
        "owner": "Youssef Alsherief",
        "sales_notes": [
            "افهم نشاط العميل وقناته (واتساب أم تليجرام) ثم رشّح الباقة المناسبة: تليجرام فقط ← المجانية للتجربة ثم التاجر؛ واتساب ← باقة واتساب؛ وكالات تدير بوتات لعملاء ← الوكالة.",
            "أفضل خطوة تالية دائماً: التسجيل المجاني من رابط signup وتجربة البوت بنفسه.",
            "لو العميل عايز بوت مخصّص أو حالة خاصة أو خصم: اعرض تحويله لفريق المبيعات (handoff).",
        ],
    }


# ------------------------------------------------ رد بلا ذكاء اصطناعي
# حين يتعطّل المزوّد (مفتاح · حصة · شبكة) لا يسقط بوت المنصة لفلو «اسمك؟ رقمك؟» —
# يرد من الحقائق نفسها بمطابقة كلمات. الترتيب مهم: الأسعار قبل «واتساب» (بكام باقة واتساب؟).
_INTENTS = (
    ("human",   ("موظف", "حد من الفريق", "خدمه العملاء", "شكوي", "مشكله", "كلم حد", "بشري",
                 "human", "agent", "person", "complain", "support team")),
    ("prices",  ("سعر", "اسعار", "بكام", "كام", "باقه", "باقات", "اشتراك", "تكلفه", "فلوس",
                 "price", "pricing", "plan", "cost", "how much", "subscription")),
    ("start",   ("ابدا", "ابدء", "سجل", "تسجيل", "حساب", "جرب", "مجان", "start", "sign", "register",
                 "free", "try")),
    ("pay",     ("دفع", "ادفع", "فودافون", "انستاباي", "تحويل", "كاش", "pay", "instapay", "vodafone")),
    ("whatsapp", ("واتساب", "واتس", "whatsapp")),
    ("about",   ("ايه هي", "ايه هو", "يعني ايه", "بتعملوا", "botyalla", "بوت يلا", "بوتيلا", "مميزات",
                 "خدمات", "what is", "features", "what do you", "how does", "ازاي")),
)


def _norm(s):
    s = (s or "").lower()
    for a, b in (("أ", "ا"), ("إ", "ا"), ("آ", "ا"), ("ة", "ه"), ("ى", "ي"), ("ـ", "")):
        s = s.replace(a, b)
    return re.sub(r"[ً-ْ]", "", s)


def _intent(text):
    t = _norm(text)
    for name, words in _INTENTS:
        if any(w in t for w in words):
            return name
    return None


def offline_reply(text, lang="ar"):
    """(نص، أزرار) من حقائق المنصة بلا نموذج. لا يَعِد بشيء خارج `facts()`."""
    f = facts()
    en = lang == "en"
    links, sup = f["links"], f["support"]
    signup = links.get("signup", "")
    intent = _intent(text)
    btns = starters(lang)
    if intent == "prices":
        lines = []
        for p in f["plans"]:
            m = p["price_monthly_egp"]
            price = ("Free" if en else "مجانية") if m == "مجانية" else (f"{m} EGP/month" if en else f"{m} ج/شهر")
            lines.append(f"• {p['plan']}: {price}")
        tail = (f"\nYearly billing saves 30%. Details: {links['pricing']}" if en and links else
                f"\nالاشتراك السنوي بخصم 30%. التفاصيل: {links['pricing']}" if links else "")
        head = "Our plans:" if en else "باقاتنا:"
        return head + "\n" + "\n".join(lines) + tail, (["Start for free", "WhatsApp or Telegram"]
                                                       if en else ["ابدأ مجاناً", "واتساب ولا تليجرام؟"])
    if intent == "start":
        msg = ("Create your free account in a minute — no card needed:" if en else
               "اعمل حسابك المجاني في دقيقة — من غير بطاقة:")
        return (msg + (f"\n{signup}" if signup else "") +
                ("\nThen describe your business and the setup agent builds your bot." if en else
                 "\nوبعدها احكي عن نشاطك ووكيل الإعداد يصمّملك البوت كامل.")), []
    if intent == "whatsapp":
        return (("Our WhatsApp plan uses the official Meta WhatsApp Cloud API, and our team connects "
                 "your number for you. It needs a commercial register and tax card (a Meta requirement). "
                 "Telegram works on the free plan with no paperwork.") if en else
                ("باقة واتساب على واتساب الرسمي من Meta، وفريقنا بيربط رقمك بنفسه. محتاجة سجل تجاري "
                 "وبطاقة ضريبية (شرط من Meta). أما تليجرام فشغّال على الباقة المجانية من غير أي أوراق.")), \
               (["Plans & pricing", "Start for free"] if en else ["الباقات والأسعار", "ابدأ مجاناً"])
    if intent == "pay":
        pays = " · ".join(f["payment_methods"])
        return ((f"Pay by: {pays}. Transfer, upload the receipt on the subscription page, and the team "
                 "activates your plan after review.") if en else
                (f"الدفع بـ: {pays}. حوّل المبلغ وارفع صورة الإيصال من صفحة الاشتراك، والفريق يفعّل "
                 "باقتك بعد المراجعة.")), []
    if intent == "human":
        contact = " · ".join(v for v in (sup.get("whatsapp"), sup.get("email")) if v)
        return ((f"Sure — our team will get back to you here shortly. You can also reach us at: {contact}")
                if en else
                (f"أكيد — حد من فريقنا هيرد عليك هنا في أقرب وقت. وتقدر تكلمنا كمان على: {contact}")
                ) if contact else (("Sure — our team will get back to you here shortly." if en else
                                    "أكيد — حد من فريقنا هيرد عليك هنا في أقرب وقت.")), []
    if intent == "about":
        return ((("BotYalla lets you launch a chatbot for your business on WhatsApp and Telegram with no "
                  "coding: it answers customers 24/7, shows products, takes orders and bookings, and "
                  "collects leads — all managed from one dashboard.") if en else
                 ("BotYalla منصة مصرية تخليك تعمل بوت لنشاطك على واتساب وتليجرام من غير برمجة: يرد على "
                  "عملائك 24 ساعة، يعرض منتجاتك، ياخد الطلبات والحجوزات، ويجمع بيانات المهتمين — "
                  "وتتابع كل ده من لوحة واحدة.")),
                ["Plans & pricing", "Start for free"] if en else ["الباقات والأسعار", "ابدأ مجاناً"])
    return (("I can help with BotYalla: what it does, plans and prices, or getting started. "
             "What would you like to know?") if en else
            "أقدر أساعدك في كل حاجة عن BotYalla: بتعمل إيه، الباقات والأسعار، أو إزاي تبدأ. تحب تعرف إيه؟"), btns


_MENU_REPLY = {
    ("support", "ar"): "تمام 👌 اكتبلي المشكلة في رسالة واحدة + اسم المستخدم أو إيميل حسابك، وهحلها معاك أو أوصّلها للفريق فوراً.",
    ("support", "en"): "Sure 👌 Describe the problem in one message + your username or account email, and I'll fix it or pass it to the team right away.",
    ("help", "ar"): "قولي نوع نشاطك، وعايز البوت على واتساب ولا تليجرام، وأنا أقولك الخطوة الجاية في رسالة واحدة 👇",
    ("help", "en"): "Tell me your business type and whether you want WhatsApp or Telegram, and I'll give you the next step in one message 👇",
}


def menu_reply(key, lang="ar"):
    """رد قائمة البداية لمساعد المنصة (يطلب ما يحتاجه الفريق فعلاً)؛ None = الرد العام."""
    return _MENU_REPLY.get((key, lang))


def official_wa_number():
    """رقم واتساب الرسمي الذي يُعطى للعملاء: `official_wa_number` إن ضبطه الأدمن، وإلا رقم بوت
    المساعد الرسمي على واتساب، وإلا الرقم الرسمي الثابت. لا يرجع أبداً رقماً شخصياً."""
    import re
    n = re.sub(r"\D", "", db.get_platform("official_wa_number", "") or "")
    if len(n) >= 8:
        return n
    row = official_bot()
    if row and (row.get("channel") or "telegram") == "whatsapp":
        import json
        n = re.sub(r"\D", "", json.loads(row.get("config_json") or "{}").get("bot_username") or "")
        if len(n) >= 8:
            return n
    return "201281275886"


def official_bot():
    """صفّ بوت «مساعد BotYalla الرسمي»: أقدم بوت يملكه حساب إدارة ومفعّل عليه
    `platform_kb` ويرد بغير الفلو. بوت المنصة على تليجرام يخدم عملاءه بنفس الصف —
    ذكاء وترحيب وتقييم وصندوق وارد وتنبيهات واحدة للقناتين. None = لا مساعد رسمي بعد."""
    with db.get_conn() as c:
        rows = c.execute(
            "SELECT b.id FROM bots b JOIN users u ON u.id=b.owner_id "
            "WHERE u.role IN ('admin','support') AND json_extract(b.config_json,'$.platform_kb') IN (1, 'true') "
            "AND COALESCE(json_extract(b.config_json,'$.response_mode'),'flow') <> 'flow' "
            "ORDER BY b.id").fetchall()
    for r in rows:
        row = db.get_bot(r[0])
        if row:
            return dict(row)
    return None


def welcome(lang="ar"):
    return WELCOME.get(lang, WELCOME["ar"])


def starters(lang="ar"):
    return list(STARTERS.get(lang, STARTERS["ar"]))
