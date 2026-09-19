"""ربط واتساب بضغطة — WhatsApp Embedded Signup (BotYalla معتمد من Meta كمزوّد خدمة تقنية).

الرحلة: زر في خطوة واتساب ← نافذة Meta (Facebook Login for Business بـ `WA_ES_CONFIG_ID`)
يختار فيها العميل نشاطه وحساب واتساب ورقمه ← المتصفح يستلم `code` + (waba_id,
phone_number_id) ← الخادم وحده:

1. يبدّل `code` بتوكن عميل (Business Integration System User) بسرّ التطبيق — السرّ لا
   يغادر الخادم، و`code` صالح مرة واحدة ولدقائق.
2. **يتحقّق** أن الرقم ضمن أرقام الـWABA التي يراها هذا التوكن — المعرّفات القادمة من
   المتصفح لا يُوثق بها وحدها (لا يُربط رقم لم يمنحه صاحبه لنا في النافذة).
3. يشترك التطبيق في ويبهوك الـWABA (`subscribed_apps`) فتصل رسائل العملاء إلى `/wh/whatsapp`.
4. يسجّل الرقم على Cloud API (`/register` برمز PIN من 6 أرقام يُحفظ مع البوت).

تكلفة رسائل الحساب على وسيلة دفع العميل في Meta لا على المنصة (مسار «أ» في docs/WHATSAPP.md).

الإعداد من `.env` (مثل معرّفات القياس في analytics.py): بلا `META_APP_ID` و`WA_ES_CONFIG_ID`
لا يظهر الزر ولا تُفتح نطاقات فيسبوك في CSP. سرّ التطبيق = `wa_app_secret` نفسه الذي يوقّع
الويبهوك (إعدادات المنصة) — نفس تطبيق Meta."""
import logging
import os
import re
import secrets

import httpx

log = logging.getLogger("wa_signup")
GRAPH = "https://graph.facebook.com/v21.0"
SDK_VERSION = "v21.0"
TIMEOUT = 20
_ID = re.compile(r"^\d{5,25}$")


def app_id():
    v = os.getenv("META_APP_ID", "").strip()
    return v if _ID.match(v) else ""


def config_id():
    v = os.getenv("WA_ES_CONFIG_ID", "").strip()
    return v if _ID.match(v) else ""


def configured():
    return bool(app_id() and config_id())


def csp_sources():
    """نطاقات SDK فيسبوك ونافذة الربط — فقط لو الربط بضغطة مضبوط."""
    if not configured():
        return {}
    return {"script-src": ["https://connect.facebook.net"],
            "connect-src": ["https://connect.facebook.net", "https://www.facebook.com",
                            "https://graph.facebook.com"],
            "frame-src": ["https://www.facebook.com", "https://web.facebook.com",
                          "https://staticxx.facebook.com"]}


def client_config():
    """ما يحتاجه المتصفح (ليس سرّاً): معرّف التطبيق والتكوين وإصدار الـSDK."""
    if not configured():
        return None
    return {"appId": app_id(), "configId": config_id(), "version": SDK_VERSION}


class SignupError(Exception):
    """فشل خطوة برسالة مفهومة (بلا توكنات). `step`: exchange · verify · subscribe · register."""

    def __init__(self, step, message):
        super().__init__(message)
        self.step = step


def _err(r):
    try:
        e = (r.json() or {}).get("error") or {}
        return str(e.get("error_user_msg") or e.get("message") or f"HTTP {r.status_code}")[:300]
    except Exception:
        return f"HTTP {r.status_code}"


def exchange_code(code, secret, c=None):
    """code ← توكن العميل. يرمي SignupError('exchange')."""
    if not (code and secret and app_id()):
        raise SignupError("exchange", "missing code or app secret")
    own = c is None
    c = c or httpx.Client(timeout=TIMEOUT)
    try:
        r = c.get(f"{GRAPH}/oauth/access_token",
                  params={"client_id": app_id(), "client_secret": secret, "code": code})
        tok = (r.json() or {}).get("access_token") if r.status_code == 200 else None
        if not tok:
            raise SignupError("exchange", _err(r))
        return tok
    finally:
        if own:
            c.close()


def connect(code, waba_id, phone_id, secret):
    """الرحلة كاملة بعد النافذة ← {token, waba_id, phone_id, number, name, pin, registered, warning}.

    يرمي SignupError قبل أي أثر جانبي لو فشل التبديل أو التحقق. الاشتراك والتسجيل
    يُحاولان، وفشلهما لا يُسقط الربط (الكود استُهلك، والبوت قابل للإصلاح لاحقاً) بل
    يعود `warning` يُعرض لصاحب البوت والأدمن."""
    waba_id, phone_id = str(waba_id or "").strip(), str(phone_id or "").strip()
    if not (_ID.match(waba_id) and _ID.match(phone_id)):
        raise SignupError("verify", "invalid WhatsApp account or phone id")
    with httpx.Client(timeout=TIMEOUT) as c:
        token = exchange_code(code, secret, c)
        auth = {"Authorization": f"Bearer {token}"}
        # 2) الرقم فعلاً ضمن الحساب الذي منحه العميل لهذا التوكن
        r = c.get(f"{GRAPH}/{waba_id}/phone_numbers", headers=auth,
                  params={"fields": "id,display_phone_number,verified_name"})
        if r.status_code != 200:
            raise SignupError("verify", _err(r))
        phones = {str(p.get("id")): p for p in (r.json() or {}).get("data") or []}
        if phone_id not in phones:
            raise SignupError("verify", "the selected number is not in the shared WhatsApp account")
        p = phones[phone_id]
        warnings = []
        # 3) ويبهوك الـWABA ← تطبيقنا
        r = c.post(f"{GRAPH}/{waba_id}/subscribed_apps", headers=auth)
        if r.status_code != 200:
            warnings.append(f"subscribe: {_err(r)}")
        # 4) تسجيل الرقم على Cloud API (رقم مسجّل من قبل يُرجع خطأ لا يضر)
        pin = f"{secrets.randbelow(10 ** 6):06d}"
        r = c.post(f"{GRAPH}/{phone_id}/register", headers=auth,
                   json={"messaging_product": "whatsapp", "pin": pin})
        registered = r.status_code == 200
        if not registered:
            msg = _err(r)
            if "already" not in msg.lower():
                warnings.append(f"register: {msg}")
    return {"token": token, "waba_id": waba_id, "phone_id": phone_id,
            "number": p.get("display_phone_number") or phone_id,
            "name": p.get("verified_name") or "", "pin": pin, "registered": registered,
            "warning": " | ".join(warnings)}
