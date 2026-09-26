"""CAPTCHA بـ Cloudflare Turnstile — طبقة ضد البوتات فوق حدود المحاولات.

مطفأ بالكامل ما لم يُضبط المفتاحان في `.env` (`TURNSTILE_SITE_KEY` + `TURNSTILE_SECRET_KEY`)
— كأزرار جوجل/فيسبوك: بلا مفاتيح لا ودجت ولا مصدر خارجي في CSP ولا فحص.

- المفتاح العام وحده يصل المتصفح؛ السرّ يبقى في الخادم.
- التحقق دائماً في الخادم (`siteverify`) — الودجت في المتصفح لا يُثبت شيئاً وحده.
- **يفشل مغلقاً:** رمز مفقود أو مرفوض أو تعذّر الوصول لـ Cloudflare = رفض الطلب.
- الرمز لمرة واحدة وصالح 5 دقائق (من Cloudflare)، ويُطابَق `action` حتى لا يُعاد
  استخدام رمز صفحة الدخول في التسجيل.
"""
import json
import logging
import os
import urllib.parse
import urllib.request

log = logging.getLogger("botyalla.captcha")

VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"
ORIGIN = "https://challenges.cloudflare.com"
FIELD = "cf-turnstile-response"   # الحقل الذي يحقنه الودجت داخل النموذج تلقائياً
TIMEOUT = 5

# الدخول لا يطلب CAPTCHA من أول مرة: بعد هذا العدد من المحاولات الفاشلة (للـIP
# أو للحساب) خلال النافذة. المستخدم العادي لا يراه، ومن يخمّن يصطدم به سريعاً.
LOGIN_AFTER_FAILS, LOGIN_FAIL_WINDOW = 3, 900


def site_key():
    return os.getenv("TURNSTILE_SITE_KEY", "").strip()


def _secret():
    return os.getenv("TURNSTILE_SECRET_KEY", "").strip()


def configured():
    return bool(site_key() and _secret())


def csp_sources():
    """سكربت الودجت وإطاره — فقط لو مفعّل، فبلا مفاتيح تبقى السياسة كما هي."""
    if not configured():
        return {}
    return {"script-src": [ORIGIN], "frame-src": [ORIGIN]}


def _post(data):
    """طلب siteverify. دالة مستقلة لتُستبدل في الاختبار — لا شبكة في الاختبارات."""
    req = urllib.request.Request(VERIFY_URL, data=urllib.parse.urlencode(data).encode(),
                                 headers={"Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return json.loads(r.read().decode("utf-8"))


def verify(token, ip=None, action=None):
    """True فقط لو أكّدت Cloudflare الرمز (ونفس `action` لو مُرِّر). غير مفعّل = True."""
    if not configured():
        return True
    token = (token or "").strip()
    if not token or len(token) > 2048:
        return False
    data = {"secret": _secret(), "response": token}
    if ip:
        data["remoteip"] = ip
    try:
        res = _post(data)
    except Exception as e:                       # شبكة/مهلة/JSON فاسد → رفض
        log.warning("turnstile verify unavailable: %s", type(e).__name__)
        return False
    if not res.get("success"):
        log.info("turnstile rejected: %s", ",".join(res.get("error-codes") or []) or "-")
        return False
    if action and res.get("action") and res["action"] != action:
        log.info("turnstile action mismatch: %s != %s", res.get("action"), action)
        return False
    return True
