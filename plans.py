"""باقات BotYalla — التعريفات والحدود. الأسعار بالجنيه المصري (شهرياً)."""
PLANS = {
 "free": {
    "name_ar": "مجانية", "name_en": "Free", "price": 0, "max_bots": 1,
    "features_ar": ["بوت واحد", "مولّد احتياطي مجاني", "تحليلات أساسية"],
    "features_en": ["1 bot", "Free fallback generator", "Basic analytics"],
    "ai": False, "broadcast": False,
 },
 "pro": {
    "name_ar": "احترافية", "name_en": "Pro", "price": 199, "max_bots": 5,
    "features_ar": ["حتى 5 بوتات", "وكيل الذكاء الاصطناعي", "حملات Broadcast", "تحليلات كاملة", "دعم الصور"],
    "features_en": ["Up to 5 bots", "AI agent", "Broadcast campaigns", "Full analytics", "Media support"],
    "ai": True, "broadcast": True,
 },
 "business": {
    "name_ar": "الأعمال", "name_en": "Business", "price": 499, "max_bots": 9999,
    "features_ar": ["بوتات غير محدودة", "كل مميزات الاحترافية", "أولوية الدعم", "تصدير كامل"],
    "features_en": ["Unlimited bots", "Everything in Pro", "Priority support", "Full export"],
    "ai": True, "broadcast": True,
 },
}
ORDER = ["free", "pro", "business"]

def plan(pid):
    return PLANS.get(pid, PLANS["free"])

def plan_name(pid, lang="ar"):
    return plan(pid).get("name_ar" if lang == "ar" else "name_en", pid)
