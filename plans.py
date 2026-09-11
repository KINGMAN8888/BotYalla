"""باقات BotYalla — التعريفات والحدود. الأسعار بالجنيه المصري.

**التسعير يتبع التكلفة، لا المميزات.** تليجرام تكلفته الحدّية صفر — لا رسوم
لكل رسالة إطلاقاً — فالباقة المجانية عليه لا تكلّفنا شيئاً وتصلح قناة اكتساب.
أما واتساب فـMeta تحاسب على كل رسالة، فهو مغلق على المجانية ومحدود بعدها.

**الرسائل التسويقية لا تُدرج في أي باقة.** الرسالة التسويقية في مصر ≈ 3.12ج،
فألف رسالة = 3,123ج — أكثر من أي باقة هنا. تُسعَّر بالاستهلاك من محفظة رصيد
منفصلة. `wa_msgs` أدناه هو حدّ الرسائل **الخدمية** وحدها.

**الدورة السنوية** = 70% من (السعر × 12)، أي خصم 30%. سببها ليس الخصم بل
الاحتفاظ: الدفع السنوي يحتفظ بـ62% من العملاء مقابل 41% للشهري.
"""

# نسبة سعر السنة من مجموع 12 شهراً (خصم 30%)
ANNUAL_FACTOR = 0.70

PLANS = {
 "free": {
    "name_ar": "مجانية", "name_en": "Free", "price": 0, "max_bots": 1,
    "features_ar": ["بوت واحد على تليجرام", "رسائل بلا حد", "قوالب جاهزة",
                    "بدون سجل تجاري", "مجانية للأبد"],
    "features_en": ["1 Telegram bot", "Unlimited messages", "Ready-made templates",
                    "No commercial register needed", "Free forever"],
    "ai": False, "broadcast": False, "whatsapp": False, "white_label": False,
    "wa_msgs": 0, "media_files": 100,
 },
 "merchant": {
    "name_ar": "تاجر", "name_en": "Merchant", "price": 299, "max_bots": 3,
    "features_ar": ["3 بوتات على تليجرام", "تحصيل فودافون كاش وانستاباي",
                    "وكيل الذكاء الاصطناعي", "حملات Broadcast",
                    "تحليلات كاملة ودعم الصور", "بدون تذييل BotYalla"],
    "features_en": ["3 Telegram bots", "Vodafone Cash & InstaPay collection",
                    "AI agent", "Broadcast campaigns",
                    "Full analytics and media support", "No BotYalla footer"],
    "ai": True, "broadcast": True, "whatsapp": False, "white_label": False,
    "wa_msgs": 0, "media_files": 1000,
 },
 "whatsapp": {
    "name_ar": "واتساب", "name_en": "WhatsApp", "price": 899, "max_bots": 5,
    "features_ar": ["كل مميزات باقة التاجر", "قناة واتساب الرسمية",
                    "2000 رسالة خدمية شهرياً", "قوالب Meta",
                    "يتطلب سجلاً تجارياً وبطاقة ضريبية"],
    "features_en": ["Everything in Merchant", "Official WhatsApp channel",
                    "2,000 service messages/month", "Meta templates",
                    "Requires a commercial register and tax card"],
    "ai": True, "broadcast": True, "whatsapp": True, "white_label": False,
    "wa_msgs": 2000, "media_files": 3000,
 },
 "agency": {
    "name_ar": "وكالة", "name_en": "Agency", "price": 2999, "max_bots": 9999,
    "features_ar": ["بوتات عملاء بلا حد", "علامة بيضاء (White-label)",
                    "10000 رسالة خدمية شهرياً", "لوحة إدارة العملاء",
                    "أولوية الدعم", "تصدير كامل"],
    "features_en": ["Unlimited client bots", "White-label branding",
                    "10,000 service messages/month", "Client management console",
                    "Priority support", "Full export"],
    "ai": True, "broadcast": True, "whatsapp": True, "white_label": True,
    "wa_msgs": 10000, "media_files": 20000,
 },

 # ---- باقات موروثة: لا تُباع، ولا تُحذف ----
 # المشترك دفع مقابل ما في يده. الباقة القديمة `pro` (199ج) كانت **تشمل
 # واتساب**، والجديدة `merchant` (299ج) لا تشمله — فترحيله إليها يرفع سعره
 # ويسحب ميزةً دفع مقابلها. لذلك لا تُرحَّل الصفوف إطلاقاً: تبقى الباقتان
 # القديمتان هنا بحدودهما الأصلية حرفياً، خارج ORDER فلا يشتريهما أحد جديد،
 # وينتقل صاحبها إلى الباقات الجديدة باختياره عند انتهاء مدته.
 "pro": {
    "name_ar": "احترافية (سابقة)", "name_en": "Pro (legacy)", "price": 199, "max_bots": 5,
    "features_ar": ["حتى 5 بوتات", "واتساب + تليجرام", "1000 رسالة واتساب شهرياً",
                    "وكيل الذكاء الاصطناعي", "حملات Broadcast", "تحليلات كاملة", "دعم الصور"],
    "features_en": ["Up to 5 bots", "WhatsApp + Telegram", "1,000 WhatsApp messages/month",
                    "AI agent", "Broadcast campaigns", "Full analytics", "Media support"],
    "ai": True, "broadcast": True, "whatsapp": True, "white_label": False,
    "wa_msgs": 1000, "media_files": 2000, "legacy": True,
 },
 "business": {
    "name_ar": "الأعمال (سابقة)", "name_en": "Business (legacy)", "price": 499, "max_bots": 9999,
    "features_ar": ["بوتات غير محدودة", "5000 رسالة واتساب شهرياً",
                    "كل مميزات الاحترافية", "أولوية الدعم", "تصدير كامل"],
    "features_en": ["Unlimited bots", "5,000 WhatsApp messages/month",
                    "Everything in Pro", "Priority support", "Full export"],
    "ai": True, "broadcast": True, "whatsapp": True, "white_label": False,
    "wa_msgs": 5000, "media_files": 10000, "legacy": True,
 },
}

# الباقات المعروضة للبيع. الموروثة خارجها عمداً — `priced_plans` تقرأ من هنا،
# ومسارا الاشتراك يرفضان أي معرّف ليس فيها.
ORDER = ["free", "merchant", "whatsapp", "agency"]

# ما يراه الأدمن في قائمة تغيير باقة مستخدم (يشمل الموروثة لدعم الحالات القائمة)
ALL_IDS = ORDER + ["pro", "business"]


def plan(pid):
    """تعريف الباقة — يشمل الموروثة. أي معرّف مجهول يسقط إلى free."""
    return PLANS.get(pid, PLANS["free"])


def is_sellable(pid):
    """هل يجوز بيع هذه الباقة لمشترك جديد؟"""
    return pid in ORDER and pid != "free"


def is_legacy(pid):
    return bool(PLANS.get(pid, {}).get("legacy"))


def plan_name(pid, lang="ar"):
    return plan(pid).get("name_ar" if lang == "ar" else "name_en", pid)


def annual_price(pid):
    """سعر السنة مقرّباً لأقرب عشرة جنيهات."""
    monthly = plan(pid)["price"]
    if not monthly:
        return 0
    return int(round(monthly * 12 * ANNUAL_FACTOR / 10.0) * 10)


def cycle_price(pid, cycle="monthly"):
    """السعر حسب الدورة — المصدر الوحيد الذي يُبنى عليه أي مبلغ."""
    return annual_price(pid) if cycle == "annual" else plan(pid)["price"]


def cycle_days(cycle="monthly"):
    return 365 if cycle == "annual" else 30


def wa_limit(pid):
    """حدّ الرسائل الخدمية الصادرة شهرياً على واتساب. None = بلا حد (الأدمن)."""
    return plan(pid).get("wa_msgs", 0)


def media_limit(pid):
    """عدد ملفات العملاء المقبولة شهرياً. القرص مورد محدود على السيرفر."""
    return plan(pid).get("media_files", 100)
