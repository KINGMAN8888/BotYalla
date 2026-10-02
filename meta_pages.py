"""ربط صفحة فيسبوك (ماسنجر) وحساب إنستجرام الاحترافي المربوط بها — يدوياً للفريق، وبضغطة للعملاء (login_*).

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
import os
import re
from urllib.parse import urlencode

import httpx

log = logging.getLogger("meta_pages")
GRAPH = "https://graph.facebook.com/v21.0"
TIMEOUT = 20
# حقول اشتراك الصفحة (Edit Page Subscriptions في لوحة Meta) — كلها قابلة للاختيار من
# «/admin/meta». `handled`: ما يتصرف فيه BotYalla فعلاً؛ الباقي يُسجَّل في سجل الأحداث فقط.
ALL_FIELDS = [
    # (الحقل, المجموعة, يعالجه BotYalla؟)
    ("messages", "رسائل", True), ("messaging_postbacks", "رسائل", True),
    ("messaging_referrals", "رسائل", True), ("message_echoes", "رسائل", True),
    ("message_edits", "رسائل", True), ("message_reactions", "رسائل", True),
    ("message_reads", "رسائل", True), ("message_deliveries", "رسائل", True),
    ("standby", "تسليم المحادثة", True), ("messaging_handovers", "تسليم المحادثة", True),
    ("messaging_optins", "الموافقة", True), ("messaging_optouts", "الموافقة", True),
    ("feed", "الصفحة", True), ("inbox_labels", "الصفحة", True),
    ("messaging_feedback", "الصفحة", True), ("response_feedback", "الصفحة", True),
    ("messaging_customer_information", "الصفحة", True), ("messaging_account_linking", "الصفحة", False),
    ("messaging_policy_enforcement", "سياسات", True), ("messaging_integrity", "سياسات", True),
    ("business_integrity", "سياسات", True), ("marketing_message_delivery_failed", "سياسات", True),
    ("message_template_status_update", "سياسات", False),
    ("messaging_in_thread_lead_form_submit", "عملاء محتملون", True),
    ("messaging_payments", "مدفوعات", False), ("messaging_pre_checkouts", "مدفوعات", False),
    ("messaging_checkout_updates", "مدفوعات", False), ("send_cart", "مدفوعات", False),
    ("messaging_game_plays", "أخرى", False), ("group_feed", "أخرى", False),
    ("leadgen", "عملاء محتملون", False),      # نماذج إعلانات Lead Ads — يشترك فيه تكامل «Facebook Lead Ads» وحده
    ("calls", "مكالمات", False), ("call_permission_reply", "مكالمات", False),
    ("call_settings_update", "مكالمات", False),
]
FIELD_NAMES = [f for f, _, _ in ALL_FIELDS]
# ما يُشترك فيه تلقائياً عند الربط — ما يعالجه BotYalla. المدفوعات والمكالمات والألعاب
# تحتاج أذونات وميزات منفصلة من Meta؛ طلبها بلا داعٍ يُفشل الاشتراك كله.
DEFAULT_FIELDS = [f for f, _, h in ALL_FIELDS if h]
FIELDS = ",".join(DEFAULT_FIELDS)
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


IG_FIELDS = "name,username,instagram_business_account{id,username},connected_instagram_account{id,username}"


def _ig_of(info):
    """حساب إنستجرام الصفحة: `instagram_business_account` (الربط الرسمي) أو
    `connected_instagram_account` (الربط من إعدادات الصفحة) — أيهما وُجد."""
    return info.get("instagram_business_account") or info.get("connected_instagram_account") or {}


def _ig_reason(c, page_token, app_id, secret):
    """لماذا لا يظهر إنستجرام؟ ← نص عربي محدد. Meta ترجع الحقل فارغاً بلا خطأ في حالتين:
    التوكن بلا إذن instagram_basic، أو الحساب لم يُختر في نافذة إنشاء التوكن."""
    scopes = []
    if app_id and secret:
        r = c.get(f"{GRAPH}/debug_token", params={"input_token": page_token,
                                                  "access_token": f"{app_id}|{secret}"})
        if r.status_code == 200:
            scopes = ((r.json() or {}).get("data") or {}).get("scopes") or []
    missing = [p for p in ("instagram_basic", "instagram_manage_messages") if scopes and p not in scopes]
    if missing:
        return ("التوكن مفيهوش إذن " + " و".join(missing) + " — اعمل توكن جديد من Graph API Explorer "
                "بالإذنين دول، واختار حساب إنستجرام في النافذة.")
    return ("Meta مش راجعة حساب إنستجرام للصفحة بالتوكن ده. غالباً ما اخترتش الحساب في نافذة إنشاء "
            "التوكن — اعمل توكن جديد واختار الحساب، أو اكتب معرّف حساب إنستجرام في الخانة الاختيارية.")


def connect(page_id, token, app_id="", secret="", ig_hint=""):
    """← {page_token, name, ig_id, ig_username, ig_reason, warning}. يرمي PagesError قبل أي أثر
    جانبي لو التوكن أو الصفحة غير صالحين. فشل الاشتراك لا يُسقط الربط بل يرجع `warning`.
    `ig_hint`: معرّف حساب إنستجرام يدوي (يُتحقق منه بتوكن الصفحة) لو لم ترجعه Meta تلقائياً."""
    page_id, token = str(page_id or "").strip(), str(token or "").strip()
    if not _ID.match(page_id) or len(token) < 20:
        raise PagesError("token", "invalid Page ID or token")
    with httpx.Client(timeout=TIMEOUT) as c:
        page_token = _page_token(c, page_id, token, app_id, secret)
        r = c.get(f"{GRAPH}/{page_id}", params={"fields": IG_FIELDS, "access_token": page_token})
        if r.status_code != 200:
            raise PagesError("page", _err(r))
        info = r.json() or {}
        ig = _ig_of(info)
        ig_reason = ""
        hint = str(ig_hint or "").strip()
        if not ig.get("id") and _ID.match(hint):
            h = c.get(f"{GRAPH}/{hint}", params={"fields": "id,username", "access_token": page_token})
            if h.status_code == 200 and (h.json() or {}).get("id"):
                ig = h.json()
            else:
                ig_reason = f"معرّف إنستجرام {hint} مش متاح بتوكن الصفحة: {_err(h)}"
        if not ig.get("id") and not ig_reason:
            ig_reason = _ig_reason(c, page_token, app_id, secret)
        ok, rejected = _subscribe(c, page_id, page_token, DEFAULT_FIELDS)
        warning = ("subscribe: " + "; ".join(f"{k}: {v}" for k, v in list(rejected.items())[:4])
                   if rejected else "")
    return {"page_token": page_token, "name": info.get("name") or page_id,
            "ig_id": str(ig.get("id") or ""), "ig_username": ig.get("username") or "",
            "ig_reason": ig_reason, "warning": warning, "username": info.get("username") or ""}


def _page_token(c, page_id, token, app_id="", secret=""):
    """أي توكن ملصوق ⇒ توكن الصفحة. توكن مستخدم يُبدَّل بطويل الأمد (إن توفّر السرّ) ثم يُستخرج
    منه توكن الصفحة من `/me/accounts` — وتوكن صفحة من توكن مستخدم طويل لا ينتهي."""
    r = c.get(f"{GRAPH}/me", params={"fields": "id,name", "access_token": token})
    if r.status_code != 200:
        raise PagesError("token", _err(r))
    if str((r.json() or {}).get("id")) == page_id:
        return token
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
    return match[0]["access_token"]


# ════════════════ «اربط ماسنجر وإنستجرام بضغطة» — للعملاء (المرحلة الثانية) ════════════════
# نافذة تسجيل دخول فيسبوك (redirect كامل، لا SDK — نفس سبب واتساب: FedCM يسقط config_id) ←
# كود ← توكن مستخدم طويل الأمد ← قائمة صفحاته (وحساب إنستجرام كل صفحة) ← يختار صفحة ←
# `connect` نفسها أعلاه. التوكن لا يصل المتصفح أبداً: يُحفظ مختوماً في الخادم دقائق معدودة.
# config_id اختياري: تكوين «Facebook Login for Business» (أفضل: اختيار الصفحات في النافذة
# نفسها)؛ بدونه نطلب الأذونات بأسمائها (Facebook Login العادي).
LOGIN_SCOPES = ("pages_show_list", "pages_messaging", "pages_manage_metadata", "pages_read_engagement",
                "instagram_basic", "instagram_manage_messages", "business_management")


def login_config_id():
    v = os.getenv("META_PAGES_CONFIG_ID", "").strip()
    return v if _ID.match(v) else ""


def login_url(app_id, redirect_uri, state, config_id=""):
    """رابط نافذة فيسبوك كاملاً. `state` يعود كما هو (يمنع تمرير كود من نافذة لم نبدأها)."""
    if not (_ID.match(str(app_id or "")) and redirect_uri and state):
        return None
    q = {"client_id": app_id, "redirect_uri": redirect_uri, "state": state, "response_type": "code"}
    if config_id:
        q.update(config_id=config_id, override_default_response_type="true")
    else:
        q["scope"] = ",".join(LOGIN_SCOPES)
    return f"https://www.facebook.com/{GRAPH.rsplit('/', 1)[-1]}/dialog/oauth?" + urlencode(q)


def login_exchange(code, redirect_uri, app_id, secret):
    """كود النافذة ⇒ توكن مستخدم **طويل الأمد** (60 يوماً؛ توكنات الصفحات المستخرجة منه لا تنتهي).
    `redirect_uri` يجب أن يطابق حرفياً ما فُتحت به النافذة — شرط Meta. يرمي PagesError('login')."""
    code = str(code or "").strip()
    if not (code and secret and _ID.match(str(app_id or ""))):
        raise PagesError("login", "missing code or app secret")
    with httpx.Client(timeout=TIMEOUT) as c:
        r = c.get(f"{GRAPH}/oauth/access_token", params={"client_id": app_id, "client_secret": secret,
                                                          "redirect_uri": redirect_uri, "code": code})
        tok = (r.json() or {}).get("access_token") if r.status_code == 200 else None
        if not tok:
            raise PagesError("login", _err(r))
        x = c.get(f"{GRAPH}/oauth/access_token", params={"grant_type": "fb_exchange_token", "client_id": app_id,
                                                          "client_secret": secret, "fb_exchange_token": tok})
        if x.status_code == 200 and (x.json() or {}).get("access_token"):
            tok = x.json()["access_token"]
    return tok


def list_pages(user_token):
    """صفحات المستخدم التي منحها للتطبيق ⇒ [{id, name, picture, category, can_message, ig}] بلا أي توكن.
    `can_message`: للمستخدم دور يسمح بالرسائل (MESSAGING/MODERATE) — بدونه لن يعمل البوت."""
    with httpx.Client(timeout=TIMEOUT) as c:
        r = c.get(f"{GRAPH}/me/accounts", params={
            "fields": "id,name,category,tasks,picture.width(120).height(120){url},"
                      "instagram_business_account{id,username,profile_picture_url}",
            "limit": 100, "access_token": user_token})
        if r.status_code != 200:
            raise PagesError("pages", _err(r))
        out = []
        for p in (r.json() or {}).get("data") or []:
            pid = str(p.get("id") or "")
            if not _ID.match(pid):
                continue
            ig = p.get("instagram_business_account") or {}
            tasks = set(p.get("tasks") or [])
            out.append({"id": pid, "name": str(p.get("name") or pid)[:120], "category": str(p.get("category") or "")[:80],
                        "picture": (((p.get("picture") or {}).get("data") or {}).get("url") or "")[:600],
                        "can_message": not tasks or bool(tasks & {"MESSAGING", "MODERATE", "MANAGE"}),
                        "ig": ({"id": str(ig["id"]), "username": str(ig.get("username") or "")[:60],
                                "picture": str(ig.get("profile_picture_url") or "")[:600]}
                               if _ID.match(str(ig.get("id") or "")) else None)})
    return out


def leads_connect(page_id, token, app_id="", secret=""):
    """ربط صفحة لنماذج Lead Ads وحدها ⇒ {page_token, name}. **يضيف** `leadgen` لحقول اشتراك الصفحة
    الحالية (subscribed_fields يستبدل القائمة كلها — بلا دمج كانت ستنقطع رسائل ماسنجر عن بوت الصفحة).
    يرمي PagesError بخطوة مفهومة: token · page · subscribe (غالباً إذن leads_retrieval)."""
    page_id, token = str(page_id or "").strip(), str(token or "").strip()
    if not _ID.match(page_id) or len(token) < 20:
        raise PagesError("token", "invalid Page ID or token")
    with httpx.Client(timeout=TIMEOUT) as c:
        page_token = _page_token(c, page_id, token, app_id, secret)
        r = c.get(f"{GRAPH}/{page_id}", params={"fields": "id,name", "access_token": page_token})
        if r.status_code != 200:
            raise PagesError("page", _err(r))
        name = (r.json() or {}).get("name") or page_id
        current = []
        s = c.get(f"{GRAPH}/{page_id}/subscribed_apps", params={"access_token": page_token})
        if s.status_code == 200:
            for a in (s.json() or {}).get("data") or []:
                if not app_id or str(a.get("id")) == str(app_id):
                    current = [f for f in a.get("subscribed_fields") or [] if f in FIELD_NAMES]
        want = list(dict.fromkeys(current + ["leadgen"]))
        ok, bad = _subscribe(c, page_id, page_token, want)
        if "leadgen" not in ok:
            raise PagesError("subscribe", bad.get("leadgen") or "leadgen subscription was refused")
    return {"page_token": page_token, "name": name}


LEAD_FIELDS = "id,created_time,ad_id,ad_name,campaign_name,form_id,platform,field_data"


def fetch_lead(leadgen_id, page_token):
    """بيانات نموذج Lead Ads بتوكن الصفحة ⇒ dict، أو يرمي PagesError("lead", …)."""
    if not re.fullmatch(r"\d{5,30}", str(leadgen_id or "")):
        raise PagesError("lead", "invalid leadgen id")
    with httpx.Client(timeout=TIMEOUT) as c:
        r = c.get(f"{GRAPH}/{leadgen_id}", params={"fields": LEAD_FIELDS, "access_token": page_token})
    if r.status_code != 200:
        raise PagesError("lead", _err(r))
    return r.json() or {}


def _subscribe(c, page_id, page_token, fields):
    """اشتراك بالحقول المطلوبة ← (مقبولة, {مرفوضة: السبب}). Meta ترفض الطلب كله لو حقل واحد
    يحتاج إذناً لا نملكه — فعند الفشل نجرّب حقلاً حقلاً لنعرف ما يعمل ونشترك فيه وحده."""
    fields = [f for f in fields if f in FIELD_NAMES]
    if not fields:
        return [], {}
    r = c.post(f"{GRAPH}/{page_id}/subscribed_apps",
               params={"subscribed_fields": ",".join(fields), "access_token": page_token})
    if r.status_code == 200 and (r.json() or {}).get("success"):
        return fields, {}
    ok, bad = [], {}
    for f in fields:
        x = c.post(f"{GRAPH}/{page_id}/subscribed_apps",
                   params={"subscribed_fields": ",".join(ok + [f]), "access_token": page_token})
        if x.status_code == 200 and (x.json() or {}).get("success"):
            ok.append(f)
        else:
            bad[f] = _err(x)
    return ok, bad


def subscribe(page_id, page_token, fields):
    """من «/admin/meta»: يستبدل حقول اشتراك الصفحة ← (مقبولة, مرفوضة)."""
    with httpx.Client(timeout=TIMEOUT) as c:
        return _subscribe(c, str(page_id), page_token, list(fields or []))


def status(page_id, page_token, app_id=""):
    """حالة الصفحة الحية ← {name, ig_username, fields, subscribed}. لا يرمي — الخطأ في `error`."""
    out = {"name": "", "ig_username": "", "ig_id": "", "fields": [], "subscribed": False, "error": ""}
    try:
        with httpx.Client(timeout=TIMEOUT) as c:
            r = c.get(f"{GRAPH}/{page_id}", params={"fields": IG_FIELDS, "access_token": page_token})
            if r.status_code != 200:
                out["error"] = _err(r)
                return out
            info = r.json() or {}
            ig = _ig_of(info)
            out.update(name=info.get("name") or "", ig_username=ig.get("username") or "",
                       ig_id=str(ig.get("id") or ""))
            s = c.get(f"{GRAPH}/{page_id}/subscribed_apps", params={"access_token": page_token})
            if s.status_code == 200:
                for a in (s.json() or {}).get("data") or []:
                    if not app_id or str(a.get("id")) == str(app_id):
                        out["subscribed"] = True
                        out["fields"] = list(a.get("subscribed_fields") or [])
            else:
                out["error"] = _err(s)
    except Exception as e:
        out["error"] = str(e)[:200]
    return out


def unsubscribe(page_id, page_token):
    """فصل التطبيق عن أحداث الصفحة (لا يحذف البوتات) ← (ok, error)."""
    try:
        with httpx.Client(timeout=TIMEOUT) as c:
            r = c.delete(f"{GRAPH}/{page_id}/subscribed_apps", params={"access_token": page_token})
            return (r.status_code == 200, "" if r.status_code == 200 else _err(r))
    except Exception as e:
        return False, str(e)[:200]


# ============================================================== ويبهوك التطبيق + التشخيص
# اشتراك الصفحة (`subscribed_apps`) وحده لا يكفي: Meta لا ترسل شيئاً ما لم يكن **التطبيق** نفسه
# مشتركاً في كائنَي `page` و`instagram` بعنوان ويبهوكنا. هذا ما يُضبط يدوياً في لوحة Meta
# (Messenger/Instagram ← Webhooks) — وهنا يُضبط ويُفحص من «/admin/meta» بتوكن التطبيق.
PAGE_APP_FIELDS = ("messages,messaging_postbacks,messaging_referrals,message_echoes,message_reactions,"
                   "message_reads,message_deliveries,messaging_optins,messaging_handovers,standby,feed,leadgen")
IG_APP_FIELDS = ("messages,messaging_postbacks,messaging_seen,messaging_referral,message_reactions,"
                 "messaging_handover,standby,comments,mentions")
MIN_FIELDS = "messages,messaging_postbacks"
# رسائل الإعلانات (Click-to-Direct/Messenger) لا تصل إلا مع حقل الإحالة — اسمه يختلف بين الكائنين
REFERRAL_FIELD = {"page": "messaging_referrals", "instagram": "messaging_referral"}
NEEDED_SCOPES = ("pages_messaging", "pages_manage_metadata", "instagram_basic", "instagram_manage_messages")


def app_subscriptions(app_id, secret):
    """اشتراكات ويبهوك التطبيق ← ({object: {callback, fields, active}}, خطأ)."""
    try:
        with httpx.Client(timeout=TIMEOUT) as c:
            r = c.get(f"{GRAPH}/{app_id}/subscriptions", params={"access_token": f"{app_id}|{secret}"})
            if r.status_code != 200:
                return {}, _err(r)
            out = {}
            for s in (r.json() or {}).get("data") or []:
                out[s.get("object")] = {"callback": s.get("callback_url") or "", "active": bool(s.get("active")),
                                        "fields": [f.get("name") for f in s.get("fields") or [] if f.get("name")]}
            return out, ""
    except Exception as e:
        return {}, str(e)[:200]


def ensure_app_webhooks(app_id, secret, callback, verify_token):
    """يشترك التطبيق في `page` و`instagram` بعنواننا ← {object: خطأ أو ""}. Meta تتحقق فوراً
    باستدعاء GET على العنوان بالـverify token — الخادم يرد من خيط آخر (gunicorn threads)."""
    out = {}
    with httpx.Client(timeout=TIMEOUT + 10) as c:
        def sub(obj, flds):
            r = c.post(f"{GRAPH}/{app_id}/subscriptions", params={
                "object": obj, "callback_url": callback, "fields": ",".join(flds), "verify_token": verify_token,
                "include_values": "true", "access_token": f"{app_id}|{secret}"})
            return (r.status_code == 200 and bool((r.json() or {}).get("success"))), r

        for obj, fields in (("page", PAGE_APP_FIELDS), ("instagram", IG_APP_FIELDS)):
            want = fields.split(",")
            ok, r = sub(obj, want)
            if ok:
                out[obj] = ""
                continue
            # حقل واحد مرفوض (إذن ناقص) كان يُسقطنا للحد الأدنى — بلا حقل الإحالة فتضيع رسائل
            # الإعلانات بصمت. نبني المجموعة حقلاً حقلاً ونحتفظ بكل ما يقبله Meta.
            keep = MIN_FIELDS.split(",")
            ok, r = sub(obj, keep)
            if not ok:
                out[obj] = _err(r)
                continue
            skipped = []
            for f in want:
                if f in keep:
                    continue
                ok, _ = sub(obj, keep + [f])
                (keep.append(f) if ok else skipped.append(f))
            sub(obj, keep)                                    # آخر حالة = كل المقبول
            out[obj] = ("حقول لم تُقبل: " + ", ".join(skipped)) if REFERRAL_FIELD[obj] in skipped else ""
    return out


def diagnose(app_id, secret, page_id, page_token, callback):
    """فحص سلسلة الوصول كاملة ← [{ok, label, detail}] — من التطبيق إلى الصفحة إلى التوكن."""
    checks = []
    add = lambda ok, label, detail="": checks.append({"ok": bool(ok), "label": label, "detail": detail})
    add(app_id, "App ID مضبوط (META_APP_ID)", app_id or "ناقص في .env")
    add(secret, "سرّ التطبيق مضبوط", "" if secret else "حطه في إعدادات المنصة ← App Secret — تطبيق Tech Provider")
    if app_id and secret:
        subs, err = app_subscriptions(app_id, secret)
        for obj, label in (("page", "ويبهوك ماسنجر على مستوى التطبيق"), ("instagram", "ويبهوك إنستجرام على مستوى التطبيق")):
            s = subs.get(obj)
            if err:
                add(False, label, err)
            elif not s:
                add(False, label, "التطبيق مش مشترك — اضغط «اضبط ويبهوك التطبيق تلقائياً»")
            else:
                same = s["callback"].rstrip("/") == callback.rstrip("/")
                has = "messages" in s["fields"]
                add(same and has and s["active"], label,
                    ("العنوان: " + s["callback"] + ("" if same else " (مختلف عن عنواننا)")) +
                    ("" if has else " · حقل messages غير مفعّل"))
                ref = REFERRAL_FIELD[obj]
                add(ref in s["fields"], label.replace("ويبهوك", "رسائل الإعلانات —"),
                    ref if ref in s["fields"] else f"حقل {ref} ناقص: رسائل العملاء الجايين من إعلان مش هتوصل "
                                                   "— اضغط «اضبط ويبهوك التطبيق تلقائياً»")
    if page_id and page_token:
        with httpx.Client(timeout=TIMEOUT) as c:
            r = c.get(f"{GRAPH}/{page_id}/subscribed_apps", params={"access_token": page_token})
            mine = [a for a in ((r.json() or {}).get("data") or [] if r.status_code == 200 else [])
                    if str(a.get("id")) == str(app_id)]
            add(bool(mine) and "messages" in (mine[0].get("subscribed_fields") or [] if mine else []),
                "الصفحة مشتركة في التطبيق", "" if mine else (_err(r) if r.status_code != 200 else "اضغط «حدّث واشترك»"))
            scopes = []
            if app_id and secret:
                d = c.get(f"{GRAPH}/debug_token", params={"input_token": page_token,
                                                          "access_token": f"{app_id}|{secret}"})
                scopes = ((d.json() or {}).get("data") or {}).get("scopes") or [] if d.status_code == 200 else []
            missing = [s for s in NEEDED_SCOPES if s not in scopes]
            add(scopes and not missing, "أذونات توكن الصفحة",
                ("ناقص: " + ", ".join(missing)) if scopes and missing else ("" if scopes else "تعذّر قراءة الأذونات"))
            i = c.get(f"{GRAPH}/{page_id}", params={"fields": IG_FIELDS, "access_token": page_token})
            ig = _ig_of(i.json() or {}) if i.status_code == 200 else {}
            add(ig.get("id"), "حساب إنستجرام مربوط بالصفحة", ("@" + ig.get("username", "")) if ig.get("id") else "")
    else:
        add(False, "صفحة المنصة محفوظة", "احفظ Page ID والتوكن أولاً")
    return checks
