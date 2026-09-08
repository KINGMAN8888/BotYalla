"""قوالب رسائل واتساب المعتمدة (Message Templates).

لماذا تلزم أصلاً: بعد 24 ساعة من آخر رسالة للعميل لا يسمح واتساب بأي نص حر.
القالب المعتمد من Meta هو الطريقة الوحيدة لبدء محادثة بعدها.

كل شيء هنا على WABA ID (حساب واتساب للأعمال) لا على Phone Number ID —
وهما رقمان مختلفان في لوحة Meta، وخلطهما أشهر سبب لفشل الاستدعاء.
الدوال متزامنة لأنها تُستدعى من Flask."""
import logging, re
import httpx

log = logging.getLogger("wa_templates")
META_API = "https://graph.facebook.com/v20.0"
TIMEOUT = 20

FIELDS = "id,name,status,category,language,components,rejected_reason,quality_score"
CATEGORIES = ("MARKETING", "UTILITY", "AUTHENTICATION")
# Meta ترفض أي اسم فيه حرف كبير أو مسافة أو شرطة — والرفض يأتي متأخراً وغامضاً
NAME_RE = re.compile(r"^[a-z0-9_]{1,512}$")
PLACEHOLDER_RE = re.compile(r"\{\{(\d+)\}\}")

LIMITS = {"header": 60, "body": 1024, "footer": 60}


def _err(r):
    try:
        return (r.json().get("error") or {}).get("message") or f"HTTP {r.status_code}"
    except Exception:
        return f"HTTP {r.status_code}"


def _call(method, waba_id, token, **kw):
    waba_id = (waba_id or "").strip()
    if not waba_id.isdigit():
        return None, "WABA ID أرقام فقط — انسخه من لوحة Meta (WhatsApp Business Account ID)."
    if not token:
        return None, "Access Token مفقود."
    try:
        with httpx.Client(timeout=TIMEOUT) as c:
            r = c.request(method, f"{META_API}/{waba_id}/message_templates",
                          headers={"Authorization": f"Bearer {token}"}, **kw)
    except Exception as e:
        return None, f"تعذّر الاتصال بـ Meta: {e}"
    if r.status_code >= 400:
        return None, _err(r)
    try:
        return r.json(), None
    except Exception:
        return None, "رد غير مفهوم من Meta."


def placeholders(text):
    """أرقام المتغيّرات {{1}} {{2}} داخل نص، مرتّبة بلا تكرار."""
    return sorted({int(n) for n in PLACEHOLDER_RE.findall(text or "")})


def verify_waba(waba_id, token):
    """يتحقّق أن الـ WABA ID والتوكن يعملان معاً — باستدعاء حقيقي لا بالشكل.
    هذا هو ما يميّز WABA ID الصحيح عن Phone Number ID الذي يشبهه."""
    data, err = _call("GET", waba_id, token, params={"fields": "id,name", "limit": 1})
    if err:
        return {"ok": False, "error": err}
    return {"ok": True, "count": len(data.get("data") or [])}


def list_templates(waba_id, token, limit=200):
    data, err = _call("GET", waba_id, token, params={"fields": FIELDS, "limit": limit})
    if err:
        return {"ok": False, "error": err}
    out = []
    for t in data.get("data") or []:
        body = header = footer = ""
        buttons = []
        for comp in t.get("components") or []:
            ctype = (comp.get("type") or "").upper()
            if ctype == "BODY":
                body = comp.get("text", "")
            elif ctype == "HEADER" and (comp.get("format") or "TEXT").upper() == "TEXT":
                header = comp.get("text", "")
            elif ctype == "FOOTER":
                footer = comp.get("text", "")
            elif ctype == "BUTTONS":
                buttons = [b.get("text", "") for b in comp.get("buttons") or []]
        out.append({
            "id": t.get("id"), "name": t.get("name"), "status": (t.get("status") or "").upper(),
            "category": t.get("category"), "language": t.get("language"),
            "header": header, "body": body, "footer": footer, "buttons": buttons,
            "vars": placeholders(body),
            "rejected_reason": t.get("rejected_reason") or "",
        })
    out.sort(key=lambda x: (x["status"] != "APPROVED", x["name"] or ""))
    return {"ok": True, "items": out}


def build_components(body, header="", footer="", buttons=None):
    """يبني components بالشكل الذي تتوقّعه Meta. BODY إلزامي."""
    comps = []
    if header:
        comps.append({"type": "HEADER", "format": "TEXT", "text": header})
    comps.append({"type": "BODY", "text": body})
    if footer:
        comps.append({"type": "FOOTER", "text": footer})
    buttons = [b for b in (buttons or []) if b]
    if buttons:
        comps.append({"type": "BUTTONS",
                      "buttons": [{"type": "QUICK_REPLY", "text": b[:25]} for b in buttons[:3]]})
    return comps


def validate(name, category, body, header="", footer="", buttons=None):
    """يمنع الأخطاء التي ترفضها Meta بعد ساعات من الانتظار."""
    if not NAME_RE.match(name or ""):
        return "الاسم: حروف إنجليزية صغيرة وأرقام و _ فقط، بلا مسافات."
    if category not in CATEGORIES:
        return "فئة غير معروفة."
    if not (body or "").strip():
        return "نص القالب مطلوب."
    for key, val in (("header", header), ("body", body), ("footer", footer)):
        if len(val or "") > LIMITS[key]:
            return f"{key} أطول من {LIMITS[key]} حرفاً."
    nums = placeholders(body)
    if nums and nums != list(range(1, len(nums) + 1)):
        return "المتغيّرات يجب أن تكون {{1}} ثم {{2}} بالترتيب بلا فجوات."
    if placeholders(header) or placeholders(footer):
        return "المتغيّرات مسموحة في نص القالب فقط."
    if any(len(b or "") > 25 for b in (buttons or [])):
        return "عنوان الزر أطول من 25 حرفاً."
    return None


def create_template(waba_id, token, name, language, category, body,
                    header="", footer="", buttons=None):
    problem = validate(name, category, body, header, footer, buttons)
    if problem:
        return {"ok": False, "error": problem}
    payload = {"name": name, "language": language, "category": category,
               "components": build_components(body, header, footer, buttons)}
    data, err = _call("POST", waba_id, token, json=payload)
    if err:
        return {"ok": False, "error": err}
    return {"ok": True, "id": data.get("id"), "status": data.get("status", "PENDING")}


def delete_template(waba_id, token, name):
    data, err = _call("DELETE", waba_id, token, params={"name": name})
    if err:
        return {"ok": False, "error": err}
    return {"ok": bool(data.get("success", True))}


def body_components(values):
    """معاملات جسم القالب عند الإرسال: [{type:text,text:...}, ...]"""
    values = [v for v in (values or [])]
    if not values:
        return None
    return [{"type": "body",
             "parameters": [{"type": "text", "text": str(v)} for v in values]}]
