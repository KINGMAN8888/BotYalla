"""وكيل الذكاء الاصطناعي — يحوّل وصف النشاط إلى إعدادات بوت احترافية.
يدعم مزودين مجانيين: Google Gemini (افتراضي) و Groq.
لو مفيش مفتاح API أو فشل الاتصال، يستخدم مولّد احتياطي ذكي (offline) بحيث لا تتعطل المنصة."""
import json as _json
import urllib.request
import urllib.error

GEMINI_MODEL = "gemini-2.5-flash"
GROQ_MODEL = "llama-3.3-70b-versatile"

# ------------------- استدعاء النماذج -------------------
def _post_json(url, payload, headers, timeout=40):
    data = _json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return _json.loads(resp.read().decode("utf-8"))

def call_gemini(api_key, system, user):
    url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
           f"{GEMINI_MODEL}:generateContent?key={api_key}")
    payload = {
        "system_instruction": {"parts": [{"text": system}]},
        "contents": [{"parts": [{"text": user}]}],
        "generationConfig": {"response_mime_type": "application/json", "temperature": 0.7},
    }
    data = _post_json(url, payload, {"Content-Type": "application/json"})
    return data["candidates"][0]["content"]["parts"][0]["text"]

def call_groq(api_key, system, user):
    url = "https://api.groq.com/openai/v1/chat/completions"
    payload = {"model": GROQ_MODEL,
               "messages": [{"role": "system", "content": system},
                            {"role": "user", "content": user}],
               "response_format": {"type": "json_object"}, "temperature": 0.7}
    data = _post_json(url, payload,
                      {"Content-Type": "application/json",
                       "Authorization": f"Bearer {api_key}"})
    return data["choices"][0]["message"]["content"]

def _call(provider, api_key, system, user):
    if provider == "groq":
        return call_groq(api_key, system, user)
    return call_gemini(api_key, system, user)

# ------------------- بناء التعليمات -------------------
SYSTEM_PROMPT = (
    "أنت خبير في إعداد بوتات خدمة العملاء والمتاجر على تليجرام للسوق العربي. "
    "مهمتك: من وصف نشاط تجاري، تنشئ إعدادات بوت احترافية باللهجة المناسبة، ودّية ومختصرة. "
    "أعد الرد بصيغة JSON فقط، بدون أي شرح خارج الـ JSON."
)

def _user_prompt(description, template):
    schema_common = (
        '{\n'
        '  "business_name": "اسم مختصر مناسب للنشاط",\n'
        '  "welcome": "رسالة ترحيب قصيرة جذابة (سطر أو سطرين)",\n'
        '  "thanks": "رسالة شكر بعد إتمام الطلب/الإدخال",\n'
    )
    if template in ("flow", "customer_service"):
        schema = schema_common + (
        '  "flow": {\n'
        '    "start_message": "رسالة أول ما يفتح العميل البوت",\n'
        '    "steps": [ {"type":"question|buttons","prompt":"السؤال","var":"اسم الحقل","options":["خيار1","خيار2"]} ],\n'
        '    "end_message": "رسالة النهاية"\n'
        '  }\n}'
        )
        extra = ("أنشئ 3 إلى 5 خطوات منطقية لجمع بيانات العميل المناسبة لهذا النشاط "
                 "(مثل الاسم، التليفون، نوع الطلب كأزرار، التفاصيل). "
                 "استخدم type=buttons مع options عندما تكون الإجابة اختيار من قائمة، و type=question للنص الحر.")
    elif template == "store":
        schema = schema_common + (
        '  "products": [ {"name":"اسم المنتج","price": 0} ]\n}'
        )
        extra = ("اقترح 4 إلى 8 منتجات/خدمات منطقية لهذا النشاط بأسعار تقديرية بالجنيه المصري (أرقام فقط).")
    elif template == "booking":
        schema = schema_common + (
        '  "booking": {"service_name":"اسم الخدمة","open_hour":10,"close_hour":22,"slot_minutes":30,"days_ahead":7}\n}'
        )
        extra = ("اضبط ساعات العمل ومدة الموعد المناسبة لهذا النوع من النشاط (عيادة/صالون/مركز...).")
    else:
        schema = schema_common + "}"
        extra = ""
    return (f"وصف النشاط: «{description}»\n\n"
            f"أعد JSON بالبنية التالية بالضبط:\n{schema}\n\n{extra}")

# ------------------- التطبيق -------------------
def _coerce_config(raw: dict, template: str) -> dict:
    """يحوّل مخرجات النموذج إلى تعديلات config آمنة."""
    patch = {}
    if isinstance(raw.get("business_name"), str) and raw["business_name"].strip():
        patch["business_name"] = raw["business_name"].strip()[:80]
    for k in ("welcome", "thanks"):
        if isinstance(raw.get(k), str):
            patch[k] = raw[k].strip()[:1000]
    if template in ("flow", "customer_service"):
        f = raw.get("flow") or {}
        steps = []
        for s in (f.get("steps") or [])[:8]:
            if not isinstance(s, dict): continue
            t = s.get("type") if s.get("type") in ("question", "buttons", "message") else "question"
            prompt = str(s.get("prompt", "")).strip()
            if not prompt: continue
            step = {"id": f"s{len(steps)}", "type": t, "prompt": prompt[:300],
                    "var": (str(s.get("var", "")).strip() or f"حقل{len(steps)+1}")[:40]}
            if t == "buttons":
                opts = [str(o).strip()[:40] for o in (s.get("options") or []) if str(o).strip()]
                step["options"] = opts[:8]
            steps.append(step)
        if steps:
            patch["flow"] = {"start_message": str(f.get("start_message", patch.get("welcome",""))).strip()[:1000],
                             "steps": steps,
                             "end_message": str(f.get("end_message", patch.get("thanks",""))).strip()[:1000]}
    elif template == "store":
        prods = []
        for p in (raw.get("products") or [])[:20]:
            if not isinstance(p, dict): continue
            name = str(p.get("name", "")).strip()
            if not name: continue
            try: price = float(p.get("price", 0))
            except (ValueError, TypeError): price = 0.0
            item = {"name": name[:80], "price": price}
            if isinstance(p.get("image"), str) and p["image"].startswith("http"):
                item["image"] = p["image"].strip()
            prods.append(item)
        if prods: patch["products"] = prods
    elif template == "booking":
        b = raw.get("booking") or {}
        if isinstance(b.get("service_name"), str): patch["service_name"] = b["service_name"].strip()[:80]
        for k in ("open_hour", "close_hour", "slot_minutes", "days_ahead"):
            try:
                if k in b: patch[k] = int(b[k])
            except (ValueError, TypeError): pass
    return patch

def _fallback(description, template) -> dict:
    """مولّد احتياطي بدون AI — يعطي إعدادات معقولة من الوصف."""
    name = (description.strip().split("\n")[0][:40] or "نشاطي")
    welcome = f"👋 أهلاً بك في «{name}»! سعداء بخدمتك."
    thanks = "✅ تم استلام طلبك، وسنتواصل معك قريباً. شكراً لك!"
    patch = {"welcome": welcome, "thanks": thanks}
    if template in ("flow", "customer_service"):
        patch["flow"] = {"start_message": welcome,
            "steps": [
                {"id": "s0", "type": "question", "prompt": "📝 اكتب اسمك:", "var": "الاسم"},
                {"id": "s1", "type": "question", "prompt": "📱 رقم تليفونك:", "var": "التليفون"},
                {"id": "s2", "type": "buttons", "prompt": "كيف نقدر نساعدك؟",
                 "var": "نوع الطلب", "options": ["استفسار", "طلب خدمة", "شكوى"]},
                {"id": "s3", "type": "question", "prompt": "✍️ اكتب التفاصيل:", "var": "التفاصيل"},
            ], "end_message": thanks}
    elif template == "store":
        patch["products"] = [{"name": "منتج 1", "price": 50}, {"name": "منتج 2", "price": 75}]
    elif template == "booking":
        patch.update({"service_name": name, "open_hour": 10, "close_hour": 22,
                      "slot_minutes": 30, "days_ahead": 7})
    return patch

def generate_bot_config(description, template, api_key=None, provider="gemini"):
    """يرجّع (patch, source) حيث source = 'ai' أو 'fallback'."""
    description = (description or "").strip()
    if not description:
        return {}, "empty"
    if api_key:
        try:
            text = _call(provider, api_key, SYSTEM_PROMPT, _user_prompt(description, template))
            raw = _json.loads(text)
            patch = _coerce_config(raw, template)
            if patch:
                return patch, "ai"
        except Exception as e:
            # نرجع للاحتياطي عند أي فشل
            return _fallback(description, template), f"fallback:{type(e).__name__}"
    return _fallback(description, template), "fallback"
