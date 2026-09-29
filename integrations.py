"""التكاملات — المرحلة 9: أحداث المتاجر والأنظمة الخارجية ⇒ رسائل واتساب تلقائية.

سلة · زد · Shopify · WooCommerce · Webhook عام (Zapier / Make / محرك الحجز / PMS):
المتجر يرسل الحدث لمسار سرّي خاص بالتكامل (`/in/<key>`) ⇒ نفهمه ونوحّده (طلب جديد · دُفع · شُحن · اكتمل ·
أُلغي · سلة متروكة · أو حدث مخصّص مثل booking_confirmed) ⇒ قواعد صاحب الحساب: قالب واتساب معتمد بمتغيّرات
من الطلب · وسوم على جهة الاتصال · تسجيل في تسلسل متابعة.

القواعد (AGENTS §68):
  · المسار سرّي (128 بت) + توقيع المزوّد HMAC حين يُضبط سرّه — لا حدث يُقبل بتوقيع خاطئ.
  · **مرة واحدة لكل (حدث، طلب)** (`db.claim_integration_event`) — إعادة المتجر للإشعار لا تكرّر الرسالة.
  · القالب بقواعد المال نفسها (`flow_graph._send_template`: الفئة من Meta · خصم قبل الإرسال · ردّ في finally).
  · **STOP مستبعد دائماً**، والقالب التسويقي (سلة متروكة…) لا يُرسل إلا لمن وافق صراحة (§55).
  · الردّ على المتجر فوري (200)؛ الإرسال في حلقة البوتات.
"""
import asyncio
import base64
import hashlib
import hmac
import json
import logging
import re
import secrets
import time

import crm as CRM
import database as db

log = logging.getLogger("integrations")

PROVIDERS = ("salla", "zid", "shopify", "woocommerce", "webhook", "fb_leads", "sheets")
STORE_EVENTS = ("order_created", "order_paid", "order_shipped", "order_completed", "order_cancelled", "cart_abandoned")
EVENT_RE = re.compile(r"[a-z0-9][a-z0-9_.\-]{0,39}")
VAR_KEY_RE = re.compile(r"[A-Za-z_][\w.]{0,39}")
MAX_RULES = 20
LEAD_EVENT_RE = re.compile(r"lead|form_\d{5,30}")      # كل النماذج، أو نموذج بعينه (أولوية)
LEAD_VARS = ("full_name", "phone_number", "email", "city", "form_id", "ad_name", "campaign_name", "platform")
STORE_VARS = ("order_id", "order_total", "order_status", "order_items", "order_url", "tracking_url", "customer_name", "store")

# app.py يضبطها: قناة البوت (من حلقة البوتات) · تشغيل coroutine بلا انتظار · بوابة باقة صاحب الحساب
HOOKS = {"channel": lambda bot_row: None, "spawn": None, "gate": lambda owner_id: True}


class Invalid(Exception):
    pass


def new_key():
    return secrets.token_hex(16)


# ─────────────────────────── التوقيع ───────────────────────────
def _hmac(secret, body):
    return hmac.new(secret.encode(), body, hashlib.sha256)


def verify(provider, secret, headers, body):
    """True لو لا سرّ مضبوط (المسار السرّي وحده الحارس) أو التوقيع مطابق لطريقة المزوّد."""
    if not secret:
        return True
    h = {k.lower(): v for k, v in headers.items()}
    if provider == "shopify":
        got, want = h.get("x-shopify-hmac-sha256", ""), base64.b64encode(_hmac(secret, body).digest()).decode()
    elif provider == "woocommerce":
        got, want = h.get("x-wc-webhook-signature", ""), base64.b64encode(_hmac(secret, body).digest()).decode()
    elif provider == "salla":
        got, want = h.get("x-salla-signature", ""), _hmac(secret, body).hexdigest()
        if not got and h.get("authorization"):              # استراتيجية «Token» في سلة
            got, want = h["authorization"].removeprefix("Bearer ").strip(), secret
    elif provider == "zid":
        got, want = h.get("x-zid-token", "") or h.get("authorization", "").removeprefix("Bearer ").strip(), secret
    else:
        got, want = h.get("x-botyalla-signature", ""), _hmac(secret, body).hexdigest()
    return bool(got) and hmac.compare_digest(str(got), str(want))


# ─────────────────────────── فهم الحدث ───────────────────────────
def _s(v, n=300):
    return str(v if v is not None else "").strip()[:n]


def _money(amount, currency):
    try:
        v = float(str(amount).replace(",", ""))
    except (TypeError, ValueError):
        return _s(amount, 40)
    return (f"{v:,.2f}".rstrip("0").rstrip(".") + (f" {currency}" if currency else "")).strip()


def _items(lst, name_key, qty_key="quantity"):
    out = []
    for it in (lst or [])[:10]:
        if isinstance(it, dict):
            q, n = it.get(qty_key) or 1, _s(it.get(name_key), 60)
            if n:
                out.append(f"{q}× {n}")
    return "، ".join(out)[:300]


def _full(*parts):
    return " ".join(p for p in (_s(x, 60) for x in parts) if p)


WOO_STATUS = {"processing": "order_paid", "completed": "order_completed", "cancelled": "order_cancelled",
              "refunded": "order_cancelled", "failed": "order_cancelled"}
SALLA_STATUS = {"completed": "order_completed", "delivered": "order_completed", "shipped": "order_shipped",
                "delivering": "order_shipped", "in_progress": "order_paid", "canceled": "order_cancelled",
                "cancelled": "order_cancelled", "restored": "order_cancelled"}
ZID_STATUS = {"new": "order_created", "preparing": "order_paid", "ready": "order_shipped", "indelivery": "order_shipped",
              "delivered": "order_completed", "cancelled": "order_cancelled"}
SHOPIFY_TOPIC = {"orders/create": "order_created", "orders/paid": "order_paid", "orders/fulfilled": "order_shipped",
                 "orders/cancelled": "order_cancelled"}


def parse(provider, headers, body):
    """حمولة المزوّد ⇒ {event, ref, phone_raw, name, email, vars, summary} أو None (حدث لا نتعامل معه)."""
    h = {k.lower(): v for k, v in headers.items()}
    b = body if isinstance(body, dict) else {}
    if provider == "shopify":
        ev = SHOPIFY_TOPIC.get(h.get("x-shopify-topic", ""))
        if not ev:
            return None
        cust = b.get("customer") or {}
        ship, bill = b.get("shipping_address") or {}, b.get("billing_address") or {}
        track = next((f.get("tracking_url") for f in b.get("fulfillments") or [] if f.get("tracking_url")), "")
        ref = _s(b.get("name") or b.get("order_number") or b.get("id"), 40)
        return {"event": ev, "ref": _s(b.get("id") or ref, 60),
                "phone_raw": b.get("phone") or cust.get("phone") or ship.get("phone") or bill.get("phone"),
                "name": _full(cust.get("first_name"), cust.get("last_name")) or _s(ship.get("name"), 120),
                "email": b.get("email") or cust.get("email"),
                "vars": {"order_id": ref, "order_total": _money(b.get("total_price"), b.get("currency")),
                         "order_status": _s(b.get("fulfillment_status") or b.get("financial_status"), 40),
                         "order_items": _items(b.get("line_items"), "title"), "order_url": _s(b.get("order_status_url"), 500),
                         "tracking_url": _s(track, 500)}}
    if provider == "woocommerce":
        topic = h.get("x-wc-webhook-topic", "")
        status = _s(b.get("status"), 30)
        ev = "order_created" if topic == "order.created" else WOO_STATUS.get(status) if topic == "order.updated" else None
        if not ev or not b.get("id"):
            return None
        bill = b.get("billing") or {}
        return {"event": ev, "ref": _s(b.get("id"), 60), "phone_raw": bill.get("phone"),
                "name": _full(bill.get("first_name"), bill.get("last_name")), "email": bill.get("email"),
                "vars": {"order_id": "#" + _s(b.get("number") or b.get("id"), 30),
                         "order_total": _money(b.get("total"), b.get("currency")), "order_status": status,
                         "order_items": _items(b.get("line_items"), "name"), "order_url": "", "tracking_url": ""}}
    if provider == "salla":
        name, d = _s(b.get("event"), 60), b.get("data") or {}
        cust = d.get("customer") or {}
        phone = f"{_s(cust.get('mobile_code'), 6)}{_s(cust.get('mobile'), 20)}" if cust.get("mobile") else None
        if name == "abandoned.cart":
            tot = d.get("total") or {}
            return {"event": "cart_abandoned", "ref": _s(d.get("id"), 60), "phone_raw": phone,
                    "name": _full(cust.get("name")) or _full(cust.get("first_name"), cust.get("last_name")),
                    "email": cust.get("email"),
                    "vars": {"order_id": "", "order_total": _money(tot.get("amount"), tot.get("currency")),
                             "order_status": "", "order_items": _items(d.get("items"), "name"),
                             "order_url": _s(d.get("checkout_url"), 500), "tracking_url": ""}}
        slug = _s((d.get("status") or {}).get("slug") if isinstance(d.get("status"), dict) else d.get("status"), 30)
        ev = "order_created" if name == "order.created" else SALLA_STATUS.get(slug) if name == "order.status.updated" else None
        if not ev:
            return None
        tot = (d.get("amounts") or {}).get("total") or {}
        ship = next((s for s in d.get("shipments") or [] if isinstance(s, dict)), {}) if d.get("shipments") else {}
        return {"event": ev, "ref": _s(d.get("id"), 60), "phone_raw": phone,
                "name": _full(cust.get("first_name"), cust.get("last_name")), "email": cust.get("email"),
                "vars": {"order_id": "#" + _s(d.get("reference_id") or d.get("id"), 30),
                         "order_total": _money(tot.get("amount"), tot.get("currency")),
                         "order_status": _s((d.get("status") or {}).get("name") if isinstance(d.get("status"), dict) else slug, 40),
                         "order_items": _items(d.get("items"), "name"),
                         "order_url": _s((d.get("urls") or {}).get("customer"), 500),
                         "tracking_url": _s(ship.get("tracking_link"), 500)}}
    if provider == "zid":
        st = b.get("order_status") or {}
        code = _s(st.get("code") if isinstance(st, dict) else st, 30)
        ev = ZID_STATUS.get(code)
        if not ev or not b.get("id"):
            return None
        cust = b.get("customer") or {}
        return {"event": ev, "ref": _s(b.get("id"), 60), "phone_raw": cust.get("mobile"), "name": _s(cust.get("name"), 120),
                "email": cust.get("email"),
                "vars": {"order_id": "#" + _s(b.get("code") or b.get("id"), 30),
                         "order_total": _money(b.get("order_total"), b.get("currency_code")),
                         "order_status": _s(st.get("name") if isinstance(st, dict) else code, 40),
                         "order_items": _items(b.get("products"), "name"), "order_url": _s(b.get("order_url"), 500),
                         "tracking_url": _s((b.get("shipping") or {}).get("tracking_url") if isinstance(b.get("shipping"), dict) else "", 500)}}
    # Webhook عام: {"event": "booking_confirmed", "id": "...", "phone": "...", "name": "...", "email": "...", "data": {...}}
    ev = _s(b.get("event"), 40).lower()
    if not EVENT_RE.fullmatch(ev):
        return None
    data = b.get("data") if isinstance(b.get("data"), dict) else {}
    vars_ = {}
    for k, v in list(data.items())[:30]:
        if VAR_KEY_RE.fullmatch(str(k)) and isinstance(v, (str, int, float)) and not isinstance(v, bool):
            vars_[str(k)] = _s(v, 300)
    return {"event": ev, "ref": _s(b.get("id"), 80) or secrets.token_hex(8), "phone_raw": b.get("phone"),
            "name": _s(b.get("name"), 120), "email": b.get("email"), "vars": vars_}


# ─────────────────────────── القواعد ───────────────────────────
def clean_rules(raw, provider, seq_ids=None):
    if not isinstance(raw, list) or len(raw) > MAX_RULES:
        raise Invalid("rules")
    out, seen = [], set()
    for r in raw:
        if not isinstance(r, dict):
            raise Invalid("rules")
        ev = _s(r.get("event"), 40).lower()
        allowed = (LEAD_EVENT_RE.fullmatch(ev) if provider == "fb_leads" else ev == "row_added" if provider == "sheets"
                   else True if provider == "webhook" else ev in STORE_EVENTS)
        if not allowed or not EVENT_RE.fullmatch(ev) or ev in seen:
            raise Invalid("event")
        seen.add(ev)
        rule = {"event": ev, "active": bool(r.get("active", True)), "template": None, "tags": [], "sequence": None}
        t = r.get("template")
        if t and _s(t.get("name")):
            name, lang = _s(t.get("name"), 512), _s(t.get("lang"), 15) or "ar"
            if not re.fullmatch(r"[a-z0-9_]{1,512}", name) or not re.fullmatch(r"[A-Za-z_]{2,15}", lang):
                raise Invalid("template")
            vars_ = [_s(v, 300) for v in (t.get("vars") or [])][:20]
            rule["template"] = {"name": name, "lang": lang, "vars": vars_}
        rule["tags"] = [x for x in (_s(v, 40) for v in (r.get("tags") or [])[:10]) if x]
        if r.get("sequence") not in (None, "", 0):
            try:
                sq = int(r["sequence"])
            except (TypeError, ValueError):
                raise Invalid("sequence")
            if seq_ids is not None and sq not in seq_ids:
                raise Invalid("sequence")
            rule["sequence"] = sq
        if not (rule["template"] or rule["tags"] or rule["sequence"]):
            raise Invalid("action")
        out.append(rule)
    return out


def render(text, vars_, contact):
    import flow_graph as FG
    return FG.render(text, vars_, contact)


# ─────────────────────────── الاستقبال والتنفيذ ───────────────────────────
def receive(integ, headers, raw_body):
    """من مسار الاستقبال: تحقّق · فهم · حجز الحدث مرة واحدة ⇒ (الحالة, معرّف الحدث).
    التنفيذ (الإرسال) يُطلق في الخلفية ولا ينتظره المتجر."""
    if integ["provider"] in ("fb_leads", "sheets"):
        return "ignored", None                          # يصلان من ويبهوك Meta الموقَّع / الاستطلاع وحدهما — لا من /in/
    if not verify(integ["provider"], db.integration_secret(integ), headers, raw_body):
        return "bad_signature", None
    try:
        body = json.loads(raw_body or b"{}")
    except ValueError:
        return "ignored", None                          # مثل «ping» من WooCommerce عند الإنشاء
    ev = parse(integ["provider"], headers, body)
    if not ev:
        return "ignored", None
    return _dispatch(integ, ev)


def _dispatch(integ, ev, summary=None):
    """حدث موحّد ⇒ حجز مرة واحدة ثم التنفيذ في الخلفية. مشترك بين /in/ و Google Sheets."""
    rule = next((r for r in integ["rules"] if r["event"] == ev["event"] and r["active"]), None)
    phone = CRM.norm_phone(ev.get("phone_raw"), integ["cc"]) if ev.get("phone_raw") else None
    if summary is None:
        summary = " · ".join(x for x in (ev["vars"].get("order_id"), ev["vars"].get("order_total"), ev.get("name")) if x)
    eid = db.claim_integration_event(integ["id"], f"{ev['event']}:{ev['ref']}", ev["event"], phone, summary)
    if eid is None:
        return "duplicate", None
    if not integ["active"] or not rule:
        db.set_integration_event(eid, "ignored", "no_rule" if integ["active"] else "paused")
        return "ignored", eid
    if not phone:
        db.set_integration_event(eid, "skipped", "no_phone")
        return "skipped", eid
    _spawn(run(integ, rule, ev, phone, eid))
    return "queued", eid


def _spawn(coro):
    fn = HOOKS.get("spawn")
    if fn:
        fn(coro)
    else:
        asyncio.run(coro)


async def run(integ, rule, ev, phone, eid):
    try:
        status, detail = await _run(integ, rule, ev, phone)
    except Exception as e:                               # لا يسقط حلقة البوتات حدثٌ غريب
        log.exception("integration %s event %s failed", integ["id"], eid)
        status, detail = "failed", type(e).__name__
    db.set_integration_event(eid, status, detail)
    return status, detail


async def _run(integ, rule, ev, phone):
    import broadcasts as BC
    import flow_graph as FG
    import sequences as SQ
    owner = integ["owner_id"]
    bot = db.get_bot(integ["bot_id"])
    if not bot or bot["owner_id"] != owner:
        return "failed", "bot"
    bot = dict(bot)
    cid, optin = db.upsert_contact_by_phone(owner, phone, ev.get("name") or "", CRM.norm_email(ev.get("email")) if ev.get("email") else None)
    if cid and rule["tags"]:
        db.tag_contact_by_names(owner, cid, rule["tags"])
    contact = (db.get_contact(owner, cid) or {}) if cid else {}
    peer = "wa:" + phone.lstrip("+")
    vars_ = dict(ev["vars"], customer_name=ev.get("name") or contact.get("name") or "", store=integ["name"])
    sent = None
    if rule["template"]:
        if optin == 0 or db.is_opted_out(bot["id"], peer):
            return "skipped", "stopped"                   # طلب الإيقاف — لا شيء يصله منّا (§55)
        t = rule["template"]
        category = await asyncio.to_thread(BC._HOOKS["category"], bot, t["name"], t["lang"]) if "category" in BC._HOOKS else None
        if category is None:
            return "failed", "category"
        if category == "MARKETING" and optin != 1 and not db.peer_consented(bot["id"], peer):
            return "skipped", "no_optin"                 # تسويقي (سلة متروكة…) لمن وافق صراحةً فقط
        ch = HOOKS["channel"](bot)
        if ch is None:
            return "failed", "channel"
        node = {"name": t["name"], "lang": t["lang"], "vars": t["vars"]}
        sent = await FG._send_template(bot, ch, peer, {"id": f"int{integ['id']}"}, node,
                                       lambda s: render(s or "", vars_, contact), category=category)
        if not sent:
            return "failed", "send"
    if rule["sequence"]:
        seq = db.get_sequence(rule["sequence"])
        if seq and seq["owner_id"] == owner:
            SQ.enroll(seq, bot["id"], peer)
    return ("sent", t["name"]) if sent else ("done", "")


# ─────────────────────────── Facebook Lead Ads ───────────────────────────
def parse_lead(lead):
    """نموذج Lead Ads ⇒ حدث موحّد. كل سؤال في النموذج متغيّر باسمه ({{full_name}} · {{city}} · أسئلتك المخصّصة)."""
    vars_ = {}
    for f in (lead.get("field_data") or [])[:40]:
        k = re.sub(r"[^\w]", "_", _s(f.get("name"), 40)).strip("_").lower()
        vals = f.get("values") or []
        if k and VAR_KEY_RE.fullmatch(k):
            vars_[k] = _s(", ".join(str(v) for v in vals), 300)
    for k in ("form_id", "ad_name", "campaign_name", "platform"):
        if lead.get(k):
            vars_[k] = _s(lead[k], 200)
    name = vars_.get("full_name") or _full(vars_.get("first_name"), vars_.get("last_name"))
    return {"event": "lead", "form_id": _s(lead.get("form_id"), 30), "ref": _s(lead.get("id"), 40),
            "phone_raw": vars_.get("phone_number") or vars_.get("phone"), "name": name, "email": vars_.get("email"),
            "vars": vars_}


def leadgen(payload):
    """من ويبهوك Meta الموقَّع (`/wh/meta`، object=page، field=leadgen): يحجز كل عميل محتمل مرة واحدة لكل
    تكامل مربوط بالصفحة، ثم يجلب النموذج وينفّذ القواعد في الخلفية. يرجّع عدد ما حُجز."""
    if (payload or {}).get("object") != "page":
        return 0
    n = 0
    for entry in payload.get("entry") or []:
        for ch in entry.get("changes") or []:
            if ch.get("field") != "leadgen":
                continue
            v = ch.get("value") or {}
            lid, page = _s(v.get("leadgen_id"), 40), _s(v.get("page_id") or entry.get("id"), 30)
            if not re.fullmatch(r"\d{5,30}", lid):
                continue
            for integ in db.integrations_for_page(page):
                if not HOOKS["gate"](integ["owner_id"]):
                    continue
                eid = db.claim_integration_event(integ["id"], f"lead:{lid}", "lead", None, f"form {_s(v.get('form_id'), 30)}")
                if eid:
                    n += 1
                    _spawn(run_lead(integ, lid, eid))
    return n


async def run_lead(integ, leadgen_id, eid):
    import meta_pages as MP
    try:
        lead = await asyncio.to_thread(MP.fetch_lead, leadgen_id, db.integration_token(integ))
    except MP.PagesError as e:
        db.set_integration_event(eid, "failed", f"fetch: {e}"[:300])
        return "failed", "fetch"
    ev = parse_lead(lead)
    rules = [r for r in integ["rules"] if r["active"]]
    rule = next((r for r in rules if r["event"] == f"form_{ev['form_id']}"), None) or \
        next((r for r in rules if r["event"] == "lead"), None)
    phone = CRM.norm_phone(ev["phone_raw"], integ["cc"]) if ev.get("phone_raw") else None
    db.set_integration_event_info(eid, phone, " · ".join(x for x in (ev.get("name"), ev["vars"].get("ad_name")) if x))
    if not rule:
        db.set_integration_event(eid, "ignored", "no_rule")
        return "ignored", "no_rule"
    if not phone:
        db.set_integration_event(eid, "skipped", "no_phone")
        return "skipped", "no_phone"
    return await run(integ, rule, ev, phone, eid)


# ─────────────────────────── Google Sheets (مصدر) ───────────────────────────
# جدول Google (ردود Google Forms · جدول عملاء) ⇒ كل صف **جديد** بعد الربط حدث `row_added` بأعمدته متغيّرات.
# لا نجلب إلا من docs.google.com (ونتبع تحويلاته لـ googleusercontent فقط) — الرابط يكتبه المستخدم فلا SSRF.
SHEET_RE = re.compile(r"https://docs\.google\.com/spreadsheets/d/(e/)?([A-Za-z0-9_\-]{20,120})")
SHEET_HOSTS = ("docs.google.com",)
SHEET_MAX = 5 * 1024 * 1024
SHEET_EVERY = 120
PHONE_COLS = ("phone", "mobile", "phone_number", "whatsapp", "جوال", "الجوال", "رقم_الجوال", "الهاتف", "رقم_الهاتف",
              "واتساب", "رقم_الواتساب")
NAME_COLS = ("name", "full_name", "الاسم", "الاسم_الكامل")
EMAIL_COLS = ("email", "e_mail", "البريد", "البريد_الإلكتروني", "الإيميل")


def sheet_csv_url(link):
    """رابط الجدول كما نسخه المستخدم ⇒ رابط CSV نبنيه نحن (أو None)."""
    m = SHEET_RE.match(str(link or "").strip())
    if not m:
        return None
    gid = (re.search(r"[#&?]gid=(\d{1,15})", link) or [None, "0"])[1]
    if m.group(1):                                       # «النشر على الويب»
        return f"https://docs.google.com/spreadsheets/d/e/{m.group(2)}/pub?output=csv&gid={gid}"
    return f"https://docs.google.com/spreadsheets/d/{m.group(2)}/export?format=csv&gid={gid}"


def _col(h):
    return re.sub(r"[^\w]", "_", str(h or "").strip()).strip("_").lower()[:40]


def fetch_sheet(link, http=None):
    """⇒ (العناوين, الصفوف كقواميس) أو يرمي Invalid("sheet"). ملف مشترك «لأي شخص معه الرابط» أو منشور."""
    import csv
    import io
    import urllib.parse
    import httpx
    url = sheet_csv_url(link)
    if not url:
        raise Invalid("sheet")
    own = http is None
    http = http or httpx.Client(timeout=20)
    try:
        for _ in range(4):
            host = urllib.parse.urlparse(url).hostname or ""
            if host not in SHEET_HOSTS and not host.endswith(".googleusercontent.com"):
                raise Invalid("sheet")
            r = http.get(url)
            if r.status_code in (301, 302, 303, 307, 308) and r.headers.get("location"):
                url = urllib.parse.urljoin(url, r.headers["location"])
                continue
            break
        else:
            raise Invalid("sheet")
        body = r.content or b""
        if r.status_code != 200 or len(body) > SHEET_MAX or body.lstrip()[:1] == b"<":   # صفحة دخول Google = غير مشترك
            raise Invalid("sheet")
    except httpx.HTTPError:
        raise Invalid("sheet")
    finally:
        if own:
            http.close()
    rows = list(csv.reader(io.StringIO(body.decode("utf-8-sig", "replace"))))
    if not rows:
        return [], []
    heads = [_col(h) or f"col{i + 1}" for i, h in enumerate(rows[0][:40])]
    data = [{heads[i]: _s(v, 300) for i, v in enumerate(row[:len(heads)])} for row in rows[1:5001] if any(x.strip() for x in row)]
    return heads, data


def _pick_col(heads, wanted, chosen=""):
    if chosen and chosen in heads:
        return chosen
    return next((h for h in heads if h in wanted), "")


def sheet_event(integ, row, heads):
    meta = integ.get("meta") or {}
    pc = _pick_col(heads, PHONE_COLS, meta.get("phone_col"))
    nc, ec = _pick_col(heads, NAME_COLS), _pick_col(heads, EMAIL_COLS)
    ref = hashlib.sha256(json.dumps(row, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:24]
    return {"event": "row_added", "ref": ref, "phone_raw": row.get(pc) if pc else None,
            "name": row.get(nc, "") if nc else "", "email": row.get(ec) if ec else None, "vars": dict(row)}


def sheet_baseline(integ, http=None):
    """عند الربط: الصفوف الموجودة لا تُراسَل أبداً — المؤشّر يبدأ من آخرها."""
    heads, rows = fetch_sheet(integ["ext_id"], http)
    meta = dict(integ.get("meta") or {}, headers=heads)
    db.set_integration_sheet(integ["id"], cursor=len(rows), meta=meta, checked_at=int(time.time()))
    return heads, len(rows)


def sheets_tick(http=None, now=None):
    """كل صف أُضيف بعد المؤشّر ⇒ حدث (مرة واحدة بالبصمة). جدول نقص (حُذفت صفوف) ⇒ المؤشّر يتبعه بلا إرسال."""
    t = int(now or time.time())
    n = 0
    for integ in db.sheet_integrations():
        if t - (integ.get("checked_at") or 0) < SHEET_EVERY or not HOOKS["gate"](integ["owner_id"]):
            continue
        db.set_integration_sheet(integ["id"], checked_at=t)
        try:
            heads, rows = fetch_sheet(integ["ext_id"], http)
        except Invalid:
            log.info("sheet integration %s: fetch failed", integ["id"])
            continue
        cur = integ.get("cursor") or 0
        for row in rows[cur:cur + 200]:                      # دفعة محدودة؛ الباقي في الدورة التالية
            name = row.get(_pick_col(heads, NAME_COLS), "")
            _dispatch(integ, sheet_event(integ, row, heads), summary=name)
            n += 1
        meta = dict(integ.get("meta") or {}, headers=heads)
        db.set_integration_sheet(integ["id"], cursor=min(len(rows), cur + 200) if len(rows) >= cur else len(rows), meta=meta)
    return n
