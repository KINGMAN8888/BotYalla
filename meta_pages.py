"""ربط صفحة فيسبوك (ماسنجر) وحساب إنستجرام الاحترافي المربوط بها — المرحلة الأولى (للفريق).

الربط اليدوي بتوكن: الأدمن يلصق Page ID + توكن. يُقبل نوعان:
  * **توكن صفحة** (أفضلها من System User في Business Settings — لا ينتهي).
  * **توكن مستخدم** من Graph API Explorer: يُبدَّل بتوكن طويل (60 يوماً) بسرّ التطبيق، ثم
    يُستخرج منه توكن الصفحة من `/me/accounts` — وتوكن صفحة مأخوذ من توكن مستخدم طويل
    **لا ينتهي**. فلصق أي توكن من Explorer ينتج ربطاً دائماً.

ثم يشترك التطبيق في أحداث الصفحة (`subscribed_apps`) فتصل رسائل ماسنجر وإنستجرام معاً إلى
`/wh/meta`. المرحلة الثانية (الطرح للعملاء) تضيف نافذة Facebook Login for Business بتكوين
صفحات مستقل — تنتهي بنفس `connect` هنا بعد اختيار الصفحة، فلا يتغيّر شيء بعدها.

التطبيق = `META_APP_ID` (تطبيق الـTech Provider حيث أُضيف منتجا Messenger وInstagram)،
والسرّ = `wa_es_app_secret` ثم `wa_app_secret` — نفس ما يتحقق به الويبهوك من التوقيع."""
import logging
import re

import httpx

log = logging.getLogger("meta_pages")
GRAPH = "https://graph.facebook.com/v21.0"
TIMEOUT = 20
FIELDS = "messages,messaging_postbacks,messaging_referrals"
_ID = re.compile(r"^\d{5,25}$")


class PagesError(Exception):
    """فشل خطوة برسالة مفهومة (بلا توكنات). step: token · page · subscribe."""

    def __init__(self, step, message):
        super().__init__(message)
        self.step = step


def _err(r):
    try:
        e = (r.json() or {}).get("error") or {}
        return str(e.get("error_user_msg") or e.get("message") or f"HTTP {r.status_code}")[:300]
    except Exception:
        return f"HTTP {r.status_code}"


def connect(page_id, token, app_id="", secret=""):
    """← {page_token, name, ig_id, ig_username, warning}. يرمي PagesError قبل أي أثر جانبي
    لو التوكن أو الصفحة غير صالحين. فشل الاشتراك لا يُسقط الربط بل يرجع `warning`."""
    page_id, token = str(page_id or "").strip(), str(token or "").strip()
    if not _ID.match(page_id) or len(token) < 20:
        raise PagesError("token", "invalid Page ID or token")
    with httpx.Client(timeout=TIMEOUT) as c:
        r = c.get(f"{GRAPH}/me", params={"fields": "id,name", "access_token": token})
        if r.status_code != 200:
            raise PagesError("token", _err(r))
        page_token = token
        if str((r.json() or {}).get("id")) != page_id:
            # توكن مستخدم: طويل الأمد أولاً (إن توفّر السرّ)، ثم توكن الصفحة منه
            if app_id and secret:
                x = c.get(f"{GRAPH}/oauth/access_token", params={
                    "grant_type": "fb_exchange_token", "client_id": app_id,
                    "client_secret": secret, "fb_exchange_token": token})
                if x.status_code == 200 and (x.json() or {}).get("access_token"):
                    token = x.json()["access_token"]
            a = c.get(f"{GRAPH}/me/accounts", params={"fields": "id,name,access_token", "limit": 200,
                                                      "access_token": token})
            if a.status_code != 200:
                raise PagesError("token", _err(a))
            match = [p for p in (a.json() or {}).get("data") or [] if str(p.get("id")) == page_id]
            if not match or not match[0].get("access_token"):
                raise PagesError("page", "this token has no access to that Page")
            page_token = match[0]["access_token"]
        r = c.get(f"{GRAPH}/{page_id}", params={
            "fields": "name,instagram_business_account{id,username}", "access_token": page_token})
        if r.status_code != 200:
            raise PagesError("page", _err(r))
        info = r.json() or {}
        ig = info.get("instagram_business_account") or {}
        warning = ""
        s = c.post(f"{GRAPH}/{page_id}/subscribed_apps",
                   params={"subscribed_fields": FIELDS, "access_token": page_token})
        if s.status_code != 200 or not (s.json() or {}).get("success"):
            warning = f"subscribe: {_err(s)}"
    return {"page_token": page_token, "name": info.get("name") or page_id,
            "ig_id": str(ig.get("id") or ""), "ig_username": ig.get("username") or "",
            "warning": warning}
