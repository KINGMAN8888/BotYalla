"""ربط واتساب بضغطة — WhatsApp Embedded Signup (BotYalla معتمد من Meta كمزوّد خدمة تقنية).

الرحلة: زر في الداشبورد ← **نافذة منبثقة على رابط حوار Meta نبنيه بأنفسنا** (`dialog_url`)
يختار فيها العميل نشاطه وحساب واتساب ورقمه ← Meta تعيده إلى `/whatsapp/es/return` بـ `code`
← الخادم وحده:

لماذا نافذة بدل `FB.login` من الـSDK: متصفحات Chrome الحديثة تُحوّل نداء الـSDK إلى مسار
FedCM فيُسقِط `config_id` ويطلب `scope=openid` وحده، فترد Meta بـ«هذا التطبيق يحتاج إلى
supported permission واحد على الأقل». الرابط المبنيّ يدوياً يحمل `config_id` دائماً، ويعمل
كذلك مع مانعات الإعلانات التي تحجب سكربت فيسبوك.

1. يبدّل `code` بتوكن عميل (Business Integration System User) بسرّ التطبيق — السرّ لا
   يغادر الخادم، و`code` صالح مرة واحدة ولدقائق.
2. **يكتشف ويتحقّق**: حساب واتساب الممنوح يُقرأ من التوكن نفسه (`debug_token` ←
   `granular_scopes.whatsapp_business_management.target_ids`)، والرقم من أرقام ذلك الحساب.
   المعرّفات القادمة من المتصفح لا يُوثق بها وحدها (لا يُربط رقم لم يمنحه صاحبه في النافذة).
3. يشترك التطبيق في ويبهوك الـWABA (`subscribed_apps`) فتصل رسائل العملاء إلى `/wh/whatsapp`.
4. يسجّل الرقم على Cloud API (`/register` برمز PIN من 6 أرقام يُحفظ مع البوت).

**وضع التعايش (Coexistence)** — `coexist=True` (featureType `whatsapp_business_app_onboarding`):
رقم شغّال فعلاً على تطبيق WhatsApp Business يتربط ويفضل شغّال على موبايل صاحبه. الفرق:
**لا `/register`** (الرقم مسجّل على التطبيق، والتسجيل بـPIN قد يفصله عن الموبايل)، ولو النافذة
لم ترجع phone_number_id نأخذ رقم الحساب الوحيد. ردود صاحب الرقم من موبايله تصل كـ
`smb_message_echoes` (bot_manager.record_wa_echoes). لا نطلب مزامنة جهات الاتصال ولا تاريخ
المحادثات (`smb_app_data`) — لا نحتاجها، وأقل بيانات = أقل مسؤولية.

تكلفة رسائل الحساب على وسيلة دفع العميل في Meta لا على المنصة (مسار «أ» في docs/WHATSAPP.md).

الإعداد من `.env` (مثل معرّفات القياس في analytics.py): بلا `META_APP_ID` و`WA_ES_CONFIG_ID`
لا يظهر الزر ولا تُفتح نطاقات فيسبوك في CSP. سرّ التطبيق = `wa_es_app_secret` في إعدادات المنصة
(سرّ تطبيق الـTech Provider)، ويرجع لـ`wa_app_secret` لو فاضي (تطبيق واحد للاتنين). الويبهوك يقبل
التوقيع بأي من السرّين: أرقام العملاء المربوطة بضغطة تشترك في تطبيق الـTech Provider."""
import json
import logging
import os
import re
import secrets
from urllib.parse import urlencode

import httpx

log = logging.getLogger("wa_signup")
GRAPH = "https://graph.facebook.com/v21.0"
SDK_VERSION = "v21.0"
TIMEOUT = 20
_ID = re.compile(r"^\d{5,25}$")


def dialog_url(redirect_uri, state, coexist=False):
    """رابط حوار Meta كاملاً — بديل `FB.login` (انظر أعلى الملف). `state` يعود كما هو."""
    if not (configured() and redirect_uri and state):
        return None
    extras = {"sessionInfoVersion": "3", "setup": {},
              "featureType": "whatsapp_business_app_onboarding" if coexist else ""}
    q = {"client_id": app_id(), "config_id": config_id(), "response_type": "code",
         "override_default_response_type": "true", "redirect_uri": redirect_uri,
         "state": state, "extras": json.dumps(extras, separators=(",", ":"))}
    return f"https://www.facebook.com/{SDK_VERSION}/dialog/oauth?" + urlencode(q)


def app_id():
    v = os.getenv("META_APP_ID", "").strip()
    return v if _ID.match(v) else ""


def config_id():
    v = os.getenv("WA_ES_CONFIG_ID", "").strip()
    return v if _ID.match(v) else ""


def configured():
    return bool(app_id() and config_id())


def csp_sources():
    """لا شيء: الحوار يفتح في نافذة مستقلة (لا إطار)، ولا سكربت فيسبوك في صفحاتنا بعد
    التخلّي عن الـSDK، والاتصال بـGraph من الخادم وحده. تبقى الدالة ليظل `_build_csp`
    موحّداً لو احتجنا مصادر لاحقاً."""
    return {}


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


def discover_assets(token, c):
    """ما منحه العميل فعلاً لهذا التوكن ← (waba_id, [أرقام]). Meta وحدها تحدّده،
    فلا يستطيع المتصفح أن يطلب حساباً لم يُمنح. يرمي SignupError('verify')."""
    r = c.get(f"{GRAPH}/debug_token", params={"input_token": token, "access_token": token})
    if r.status_code != 200:
        raise SignupError("verify", _err(r))
    data = (r.json() or {}).get("data") or {}
    ids = []
    for g in data.get("granular_scopes") or []:
        if g.get("scope") in ("whatsapp_business_management", "whatsapp_business_messaging"):
            ids += [str(t) for t in (g.get("target_ids") or []) if _ID.match(str(t))]
    if not ids:
        raise SignupError("verify", "no WhatsApp account was shared in the Meta window")
    return ids


def _phones_of(c, waba_id, auth):
    r = c.get(f"{GRAPH}/{waba_id}/phone_numbers", headers=auth,
              params={"fields": "id,display_phone_number,verified_name"})
    if r.status_code != 200:
        raise SignupError("verify", _err(r))
    return {str(p.get("id")): p for p in (r.json() or {}).get("data") or []}


def connect(code, waba_id, phone_id, secret, coexist=False):
    """الرحلة كاملة بعد النافذة ← {token, waba_id, phone_id, number, name, pin, registered, warning, coexist}.

    يرمي SignupError قبل أي أثر جانبي لو فشل التبديل أو التحقق. الاشتراك والتسجيل
    يُحاولان، وفشلهما لا يُسقط الربط (الكود استُهلك، والبوت قابل للإصلاح لاحقاً) بل
    يعود `warning` يُعرض لصاحب البوت والأدمن."""
    waba_id, phone_id = str(waba_id or "").strip(), str(phone_id or "").strip()
    if (waba_id and not _ID.match(waba_id)) or (phone_id and not _ID.match(phone_id)):
        raise SignupError("verify", "invalid WhatsApp account or phone id")
    with httpx.Client(timeout=TIMEOUT) as c:
        token = exchange_code(code, secret, c)
        auth = {"Authorization": f"Bearer {token}"}
        # 2) ما مُنح فعلاً لهذا التوكن — من Meta لا من المتصفح
        granted = discover_assets(token, c)
        if waba_id and waba_id not in granted:
            raise SignupError("verify", "this WhatsApp account was not shared in the Meta window")
        phones = {}
        for wid in ([waba_id] if waba_id else granted):
            phones = _phones_of(c, wid, auth)
            if phone_id in phones or (not phone_id and phones):
                waba_id = wid
                break
        if not phone_id:
            if len(phones) != 1:
                raise SignupError("verify", "choose one number in the Meta window and try again")
            phone_id = next(iter(phones))
        if phone_id not in phones:
            raise SignupError("verify", "the selected number is not in the shared WhatsApp account")
        p = phones[phone_id]
        warnings = []
        # 3) ويبهوك الـWABA ← تطبيقنا
        r = c.post(f"{GRAPH}/{waba_id}/subscribed_apps", headers=auth)
        if r.status_code != 200:
            warnings.append(f"subscribe: {_err(r)}")
        # 4) تسجيل الرقم على Cloud API (رقم مسجّل من قبل يُرجع خطأ لا يضر).
        #    التعايش: لا تسجيل — الرقم مسجّل على تطبيق Business، وMeta تتولّى الربط.
        pin, registered = None, False
        if not coexist:
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
            "coexist": bool(coexist), "warning": " | ".join(warnings)}
