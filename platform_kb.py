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

import database as db
import plans

# ما يجوز أن يقوله البوت عن وسائل الدفع والتواصل — مرآة `app._PUBLIC_PLAT`
_PUBLIC_KEYS = ("vodafone_number", "instapay_handle", "support_email", "support_whatsapp",
                "support_telegram")

WELCOME = {
    "ar": ("أهلاً بيك في BotYalla 👋\n"
           "أنا المساعد الذكي للمنصة — بساعدك تعمل بوت يرد على عملائك ويبيع ويحجز "
           "على واتساب وتليجرام، من غير برمجة.\n"
           "قولي نشاطك إيه، أو اختار من تحت 👇"),
    "en": ("Welcome to BotYalla 👋\n"
           "I'm the platform's AI assistant — I help you launch a bot that answers, sells and "
           "books for your customers on WhatsApp and Telegram, no coding needed.\n"
           "Tell me about your business, or pick an option below 👇"),
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
    pay = ["فودافون كاش" + (f" ({plat['vodafone_number']})" if plat["vodafone_number"] else ""),
           "انستاباي" + (f" ({plat['instapay_handle']})" if plat["instapay_handle"] else ""),
           "تحويل بنكي"]
    support = {k: v for k, v in (("email", plat["support_email"]),
                                 ("whatsapp", plat["support_whatsapp"]),
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
            "تليجرام: إنشاء البوت بضغطة واحدة من داخل المنصة. واتساب: فريقنا يربط رقمك بنفسه في باقات واتساب.",
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
        "support": support,
        "links": links,
        "owner": "Youssef Alsherief",
        "sales_notes": [
            "افهم نشاط العميل وقناته (واتساب أم تليجرام) ثم رشّح الباقة المناسبة: تليجرام فقط ← المجانية للتجربة ثم التاجر؛ واتساب ← باقة واتساب؛ وكالات تدير بوتات لعملاء ← الوكالة.",
            "أفضل خطوة تالية دائماً: التسجيل المجاني من رابط signup وتجربة البوت بنفسه.",
            "لو العميل عايز بوت مخصّص أو حالة خاصة أو خصم: اعرض تحويله لفريق المبيعات (handoff).",
        ],
    }


def welcome(lang="ar"):
    return WELCOME.get(lang, WELCOME["ar"])


def starters(lang="ar"):
    return list(STARTERS.get(lang, STARTERS["ar"]))
