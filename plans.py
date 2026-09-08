"""باقات BotYalla — التعريفات والحدود. الأسعار بالجنيه المصري (شهرياً).

`whatsapp` و`wa_msgs`: تليجرام مجاني التشغيل، أما واتساب فمدفوع لكل رسالة
من Meta. بلا حدّ شهري قد يتجاوز ما ندفعه عن عميل نشط قيمة اشتراكه —
لذلك واتساب مغلق على الباقة المجانية، ومحدود بعدد رسائل صادرة فيما بعدها."""
PLANS = {
 "free": {
    "name_ar": "مجانية", "name_en": "Free", "price": 0, "max_bots": 1,
    "features_ar": ["بوت واحد", "تليجرام فقط", "مولّد احتياطي مجاني", "تحليلات أساسية"],
    "features_en": ["1 bot", "Telegram only", "Free fallback generator", "Basic analytics"],
    "ai": False, "broadcast": False, "whatsapp": False, "wa_msgs": 0,
 },
 "pro": {
    "name_ar": "احترافية", "name_en": "Pro", "price": 199, "max_bots": 5,
    "features_ar": ["حتى 5 بوتات", "واتساب + تليجرام", "1000 رسالة واتساب شهرياً",
                    "وكيل الذكاء الاصطناعي", "حملات Broadcast", "تحليلات كاملة", "دعم الصور"],
    "features_en": ["Up to 5 bots", "WhatsApp + Telegram", "1,000 WhatsApp messages/month",
                    "AI agent", "Broadcast campaigns", "Full analytics", "Media support"],
    "ai": True, "broadcast": True, "whatsapp": True, "wa_msgs": 1000,
 },
 "business": {
    "name_ar": "الأعمال", "name_en": "Business", "price": 499, "max_bots": 9999,
    "features_ar": ["بوتات غير محدودة", "5000 رسالة واتساب شهرياً",
                    "كل مميزات الاحترافية", "أولوية الدعم", "تصدير كامل"],
    "features_en": ["Unlimited bots", "5,000 WhatsApp messages/month",
                    "Everything in Pro", "Priority support", "Full export"],
    "ai": True, "broadcast": True, "whatsapp": True, "wa_msgs": 5000,
 },
}
ORDER = ["free", "pro", "business"]

def plan(pid):
    return PLANS.get(pid, PLANS["free"])

def plan_name(pid, lang="ar"):
    return plan(pid).get("name_ar" if lang == "ar" else "name_en", pid)

def wa_limit(pid):
    """حدّ الرسائل الصادرة شهرياً على واتساب. None = بلا حد (الأدمن)."""
    return plan(pid).get("wa_msgs", 0)
