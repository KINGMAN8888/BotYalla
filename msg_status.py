"""تتبّع حالة رسائل واتساب الصادرة — المرحلة 2 من docs/ENTERPRISE_PLAN.md.

كل رسالة صادرة عبر `WhatsAppChannel._post` تُسجَّل بمعرّفها من Meta (`wamid`)، ثم يحدّث ويبهوك
`statuses` حالتها: sent ← delivered ← read، أو failed برمز الخطأ. هذا أساس تحليلات البثّ
(Delivered/Read/Failed/Not in WhatsApp/Frequency limit) وإعادة الاستهداف.

منطق نقي هنا (قراءة الحمولة وتصنيف الأخطاء)، والتخزين في database.py.
"""
import contextvars
import time

# سياق الإرسال: من يرسل ضمن حملة يضبط `SEND_CTX.set({"campaign_id": …})` فتُوسَم كل رسالة بها —
# بلا تمرير معامل عبر كل طبقات القناة. ContextVar يتبع مهمة asyncio نفسها لا الخيط.
SEND_CTX = contextvars.ContextVar("wa_send_ctx", default=None)

RANK = {"sent": 1, "delivered": 2, "read": 3}
STATES = ("sent", "delivered", "read", "failed")

# رموز أخطاء Meta ⇒ فئة مفهومة (نفس تقسيم لوحة المنافس: Not in WhatsApp · Frequency limit ·
# Unsubscribed · قالب · …). الرمز الخام يُحفظ دائماً — الفئة للعرض والتجميع.
_BUCKETS = {
    "not_on_whatsapp": (131026,),
    "frequency_limit": (131049,),
    "unsubscribed": (131050,),
    "window_closed": (131047,),
    "experiment": (130472,),
    "rate_limit": (131048, 131056, 130429, 80007, 4, 80004),
    "account": (368, 131031, 131042, 131045, 190, 200, 10, 131005, 133010, 133015),
    "invalid_request": (100, 131008, 131009, 131021, 131051, 131053, 135000),
    "meta_unavailable": (131000, 131016, 133004, 1, 2),
}
_CODE_BUCKET = {c: b for b, codes in _BUCKETS.items() for c in codes}


def bucket(code):
    """رمز خطأ Meta ⇒ فئة. قوالب 132000–132016 كلها «template»."""
    try:
        code = int(code)
    except (TypeError, ValueError):
        return "other"
    if 132000 <= code <= 132099:
        return "template"
    return _CODE_BUCKET.get(code, "other")


def _first_error(obj):
    errs = (obj or {}).get("errors") or []
    if errs and isinstance(errs, list):
        e = errs[0] or {}
        return e.get("code"), (e.get("title") or e.get("message") or "")[:200]
    return None, ""


def parse_statuses(payload):
    """حمولة الويبهوك ⇒ قائمة تحديثات [{wamid, status, ts, code, title, category, billable, phone_id}].
    يتجاهل ما لا يُفهم بدل أن يرمي — الويبهوك يحمل رسائل واردة أيضاً ولا يجوز أن تتعطّل."""
    out = []
    try:
        for entry in (payload or {}).get("entry") or []:
            for change in entry.get("changes") or []:
                val = change.get("value") or {}
                phone_id = str((val.get("metadata") or {}).get("phone_number_id") or "")
                for s in val.get("statuses") or []:
                    wamid, status = str(s.get("id") or ""), s.get("status")
                    if not wamid or status not in STATES:
                        continue
                    try:
                        ts = int(s.get("timestamp") or 0) or int(time.time())
                    except (TypeError, ValueError):
                        ts = int(time.time())
                    code, title = _first_error(s)
                    pricing = s.get("pricing") or {}
                    out.append({"wamid": wamid[:200], "status": status, "ts": ts,
                                "code": code, "title": title,
                                "category": (pricing.get("category") or "")[:40] or None,
                                "billable": (1 if pricing.get("billable") else 0) if "billable" in pricing else None,
                                "phone_id": phone_id})
    except (AttributeError, TypeError):
        pass
    return out


def wamid_from(resp):
    """رد Meta الناجح ⇒ معرّف الرسالة (`messages[0].id`) أو None."""
    try:
        return str(resp["messages"][0]["id"])[:200]
    except (KeyError, IndexError, TypeError):
        return None


def error_from(body):
    """جسم رد خطأ من Graph ⇒ (الرمز, العنوان)."""
    try:
        e = (body or {}).get("error") or {}
        return e.get("code"), (e.get("error_user_title") or e.get("message") or "")[:200]
    except AttributeError:
        return None, ""
