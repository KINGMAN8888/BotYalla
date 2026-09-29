"""Template Studio — المرحلة 4 من docs/ENTERPRISE_PLAN.md. منطق نقي بلا شبكة ولا Flask:

1) **الإنشاء:** نموذج المحرّر ⇒ حمولة Meta الصحيحة لأربعة أنواع: custom (تسويق/خدمة) ·
   carousel · lto (عرض محدود المدة) · auth (رمز تحقق). كل قاعدة ترفضها Meta بعد ساعات من
   الانتظار تُفحص هنا قبل الإرسال (الأطوال، ترتيب المتغيّرات، حدود الأزرار، تطابق البطاقات).
2) **الإرسال:** قالب كما تعيده Meta ⇒ `spec` يصف ما يحتاجه عند الإرسال (متغيّرات الترويسة
   والجسم، أزرار بمتغيّر، كوبون، عدّاد، بطاقات)، و`send_components` تبني معاملات الإرسال.
   البث (broadcasts.py) يعتمد عليهما فيرسل كل الأنواع لا النصّي وحده.

عيّنات الوسائط (صورة/فيديو) تُرفع لـ Meta كـ handle في app قبل استدعاء `build_create`.
"""
import re

NAME_RE = re.compile(r"^[a-z0-9_]{1,512}$")
VAR_RE = re.compile(r"\{\{(\d+)\}\}")
KINDS = ("custom", "carousel", "lto", "auth")
HEADERS = ("NONE", "TEXT", "IMAGE", "VIDEO", "LOCATION")
BTN_LIMITS = {"QUICK_REPLY": 10, "URL": 2, "PHONE_NUMBER": 1, "COPY_CODE": 1}
MAX_BUTTONS = 10
LIM = {"header": 60, "body": 1024, "footer": 60, "button": 25, "url": 2000, "code": 15, "lto": 16,
       "card_body": 160, "carousel_body": 1024}
STOP_FOOTER = {"ar": "أرسل STOP لإيقاف الرسائل التسويقية", "en": "Reply STOP to unsubscribe from marketing messages"}


class Invalid(ValueError):
    """رمز خطأ مفهوم للواجهة (مع موضعه): name · body · vars · buttons · cards …"""


def nums(text):
    return [int(n) for n in VAR_RE.findall(text or "")]


def _check_vars(text, samples, where, edges=True):
    """المتغيّرات {{1}}..{{n}} متتالية، وعيّنة غير فارغة لكل واحد. `edges`: لا متغيّر في أول النص
    أو آخره — قاعدة Meta **للجسم** («متغيّر طرفي»)، والترويسة مستثناة منها («عرض {{1}}» مقبولة)."""
    n = sorted(set(nums(text)))
    if n and n != list(range(1, len(n) + 1)):
        raise Invalid(f"{where}:order")
    s = (text or "").strip()
    if edges and n and (s.startswith("{{") or s.endswith("}}")):
        raise Invalid(f"{where}:edge_var")
    samples = [str(x or "").strip() for x in (samples or [])][:len(n)]
    if len(samples) < len(n) or not all(samples):
        raise Invalid(f"{where}:samples")
    return samples


def _text(v, key, required=True):
    v = (v or "").strip()
    if required and not v:
        raise Invalid(f"{key}:required")
    if len(v) > LIM.get(key, 1024):
        raise Invalid(f"{key}:too_long")
    return v


def _buttons(raw, allowed=("QUICK_REPLY", "URL", "PHONE_NUMBER", "COPY_CODE"), limit=MAX_BUTTONS):
    """أزرار المحرّر ⇒ أزرار Meta، مجمّعة: الردود السريعة معاً ثم أزرار الإجراء (قاعدة Meta)."""
    raw = raw or []
    if len(raw) > limit:
        raise Invalid("buttons:too_many")
    counts, qr, cta = {}, [], []
    for i, b in enumerate(raw):
        t = (b or {}).get("type")
        if t not in allowed:
            raise Invalid(f"buttons:{i}:type")
        counts[t] = counts.get(t, 0) + 1
        if counts[t] > BTN_LIMITS[t]:
            raise Invalid(f"buttons:{i}:limit")
        if t == "COPY_CODE":
            code = _text(b.get("example"), "code")
            if not re.fullmatch(r"[A-Za-z0-9_-]{1,15}", code):
                raise Invalid(f"buttons:{i}:code")
            cta.append({"type": "COPY_CODE", "example": code})
            continue
        label = _text(b.get("text"), "button")
        if t == "QUICK_REPLY":
            qr.append({"type": "QUICK_REPLY", "text": label})
        elif t == "URL":
            url = _text(b.get("url"), "url")
            if not re.match(r"^https://[^\s{}]+(\{\{1\}\})?$", url) or url.count("{{") > 1:
                raise Invalid(f"buttons:{i}:url")          # https فقط، ومتغيّر واحد في آخره
            btn = {"type": "URL", "text": label, "url": url}
            if "{{1}}" in url:
                ex = _text(b.get("example"), "url")
                if not ex.startswith(url.split("{{")[0]):
                    raise Invalid(f"buttons:{i}:url_example")
                btn["example"] = [ex]
            cta.append(btn)
        else:
            phone = re.sub(r"[^\d+]", "", b.get("phone") or "")
            if not re.fullmatch(r"\+[1-9]\d{7,14}", phone):
                raise Invalid(f"buttons:{i}:phone")
            cta.append({"type": "PHONE_NUMBER", "text": label, "phone_number": phone})
    return qr + cta


def _header(h, handles, allowed):
    """ترويسة المحرّر ⇒ مكوّن Meta أو None. `handles`: {"header": handle} من رفع العيّنة."""
    h = h or {}
    fmt = (h.get("format") or "NONE").upper()
    if fmt not in allowed:
        raise Invalid("header:format")
    if fmt == "NONE":
        return None
    if fmt == "TEXT":
        text = _text(h.get("text"), "header")
        if len(set(nums(text))) > 1:
            raise Invalid("header:one_var")
        comp = {"type": "HEADER", "format": "TEXT", "text": text}
        if nums(text):
            comp["example"] = {"header_text": _check_vars(text, h.get("samples"), "header", edges=False)}
        return comp
    if fmt == "LOCATION":
        return {"type": "HEADER", "format": "LOCATION"}
    handle = (handles or {}).get("header")
    if not handle:
        raise Invalid("header:media")
    return {"type": "HEADER", "format": fmt, "example": {"header_handle": [handle]}}


def _body(text, samples, key="body"):
    text = _text(text, key)
    comp = {"type": "BODY", "text": text}
    if nums(text):
        comp["example"] = {"body_text": [_check_vars(text, samples, key)]}
    return comp


def location_of(d):
    """دبّوس الموقع لترويسة LOCATION — يُحفظ عندنا ويُرسل مع كل رسالة."""
    loc = d or {}
    try:
        lat, lng = float(loc.get("lat")), float(loc.get("lng"))
    except (TypeError, ValueError):
        raise Invalid("location:coords")
    if not (-90 <= lat <= 90 and -180 <= lng <= 180):
        raise Invalid("location:coords")
    name = (loc.get("name") or "").strip()[:100]
    addr = (loc.get("address") or "").strip()[:500]
    if not name or not addr:
        raise Invalid("location:required")
    return {"latitude": lat, "longitude": lng, "name": name, "address": addr}


def build_create(d, handles=None):
    """نموذج المحرّر ⇒ (حمولة Meta، معلومات محلية) أو Invalid.
    المعلومات المحلية = ما لا تحفظه Meta ونحتاجه عند الإرسال (دبّوس الموقع)."""
    kind = d.get("kind")
    if kind not in KINDS:
        raise Invalid("kind")
    name = (d.get("name") or "").strip().lower().replace(" ", "_")
    if not NAME_RE.match(name) or len(name) > 60:
        raise Invalid("name")
    lang = (d.get("language") or "").strip()
    if not re.fullmatch(r"[a-z]{2,3}(_[A-Z]{2})?", lang):
        raise Invalid("language")
    handles = handles or {}
    local = {}
    if kind == "auth":
        try:
            exp = int(d.get("code_expiration_minutes") or 10)
        except (TypeError, ValueError):
            raise Invalid("auth:expiry")
        if not 1 <= exp <= 90:
            raise Invalid("auth:expiry")
        comps = [{"type": "BODY", "add_security_recommendation": bool(d.get("security_recommendation", True))},
                 {"type": "FOOTER", "code_expiration_minutes": exp},
                 {"type": "BUTTONS", "buttons": [{"type": "OTP", "otp_type": "COPY_CODE",
                                                  "text": _text(d.get("button_text") or "Copy code", "button")}]}]
        return {"name": name, "language": lang, "category": "AUTHENTICATION", "components": comps}, local

    if kind == "carousel":
        fmt = (d.get("card_format") or "IMAGE").upper()
        if fmt not in ("IMAGE", "VIDEO"):
            raise Invalid("cards:format")
        cards = d.get("cards") or []
        if not 2 <= len(cards) <= 10:
            raise Invalid("cards:count")
        shape, out_cards = None, []
        for i, c in enumerate(cards):
            btns = _buttons(c.get("buttons"), ("QUICK_REPLY", "URL", "PHONE_NUMBER"), 2)
            if not btns:
                raise Invalid(f"cards:{i}:buttons")
            this = [b["type"] for b in btns]
            if shape is None:
                shape = this
            elif this != shape:
                raise Invalid(f"cards:{i}:shape")        # كل البطاقات بنفس نوع الأزرار وترتيبها
            h = handles.get(f"card{i}")
            if not h:
                raise Invalid(f"cards:{i}:media")
            out_cards.append({"components": [
                {"type": "HEADER", "format": fmt, "example": {"header_handle": [h]}},
                _body(c.get("body"), c.get("samples"), key="card_body"),
                {"type": "BUTTONS", "buttons": btns}]})
        comps = [_body(d.get("body"), d.get("samples"), "carousel_body"),
                 {"type": "CAROUSEL", "cards": out_cards}]
        return {"name": name, "language": lang, "category": "MARKETING", "components": comps}, local

    if kind == "lto":
        comps = []
        head = _header(d.get("header"), handles, ("NONE", "IMAGE", "VIDEO"))
        if head:
            comps.append(head)
        has_exp = bool(d.get("has_expiration"))
        comps.append({"type": "LIMITED_TIME_OFFER",
                      "limited_time_offer": {"text": _text(d.get("offer_text"), "lto"), "has_expiration": has_exp}})
        comps.append(_body(d.get("body"), d.get("samples")))
        btns = _buttons(d.get("buttons"), ("URL", "COPY_CODE"), 2)
        types = [b["type"] for b in btns]
        if "URL" not in types:
            raise Invalid("buttons:url_required")
        if has_exp and "COPY_CODE" not in types:
            raise Invalid("buttons:code_required")
        # زر الكوبون أولاً دائماً في هذا النوع
        btns.sort(key=lambda b: 0 if b["type"] == "COPY_CODE" else 1)
        comps.append({"type": "BUTTONS", "buttons": btns})
        return {"name": name, "language": lang, "category": "MARKETING", "components": comps}, local

    # custom — تسويق أو خدمة
    category = (d.get("category") or "MARKETING").upper()
    if category not in ("MARKETING", "UTILITY"):
        raise Invalid("category")
    comps = []
    head = _header(d.get("header"), handles, HEADERS)
    if head:
        comps.append(head)
        if head["format"] == "LOCATION":
            local["location"] = location_of((d.get("header") or {}).get("location"))
    comps.append(_body(d.get("body"), d.get("samples")))
    footer = _text(d.get("footer"), "footer", required=False)
    if footer:
        if nums(footer):
            raise Invalid("footer:vars")
        comps.append({"type": "FOOTER", "text": footer})
    btns = _buttons(d.get("buttons"))
    if btns:
        comps.append({"type": "BUTTONS", "buttons": btns})
    return {"name": name, "language": lang, "category": category, "components": comps}, local


# ─────────────────────────── الإرسال: قالب من Meta ⇒ ما يحتاجه ───────────────────────────
def _btn_spec(buttons):
    out = []
    for i, b in enumerate(buttons or []):
        t = (b.get("type") or "").upper()
        out.append({"index": i, "type": t, "text": b.get("text", ""),
                    "url_var": t == "URL" and "{{1}}" in (b.get("url") or ""), "url": b.get("url", "")})
    return out


def spec_of(components):
    """مكوّنات القالب كما تعيدها Meta ⇒ وصف الإرسال."""
    s = {"kind": "custom", "header_format": "", "header_vars": 0, "body_vars": 0, "buttons": [],
         "lto": None, "cards": []}
    for comp in components or []:
        t = (comp.get("type") or "").upper()
        if t == "HEADER":
            s["header_format"] = (comp.get("format") or "TEXT").upper()
            s["header_vars"] = len(set(nums(comp.get("text"))))
        elif t == "BODY":
            if comp.get("add_security_recommendation") is not None and not comp.get("text"):
                s["kind"] = "auth"
            s["body_vars"] = len(set(nums(comp.get("text"))))
        elif t == "BUTTONS":
            s["buttons"] = _btn_spec(comp.get("buttons"))
            if any(b["type"] == "OTP" for b in s["buttons"]):
                s["kind"] = "auth"
        elif t == "LIMITED_TIME_OFFER":
            s["kind"] = "lto"
            s["lto"] = {"has_expiration": bool((comp.get("limited_time_offer") or {}).get("has_expiration"))}
        elif t == "CAROUSEL":
            s["kind"] = "carousel"
            for card in comp.get("cards") or []:
                cs = {"format": "", "body_vars": 0, "buttons": []}
                for cc in card.get("components") or []:
                    ct = (cc.get("type") or "").upper()
                    if ct == "HEADER":
                        cs["format"] = (cc.get("format") or "").upper()
                    elif ct == "BODY":
                        cs["body_vars"] = len(set(nums(cc.get("text"))))
                    elif ct == "BUTTONS":
                        cs["buttons"] = _btn_spec(cc.get("buttons"))
                s["cards"].append(cs)
    return s


def _button_params(buttons, url_values, coupon):
    out = []
    for b in buttons:
        if b["type"] == "URL" and b["url_var"]:
            out.append({"type": "button", "sub_type": "url", "index": str(b["index"]),
                        "parameters": [{"type": "text", "text": url_values.get(b["index"]) or "-"}]})
        elif b["type"] == "COPY_CODE":
            out.append({"type": "button", "sub_type": "copy_code", "index": str(b["index"]),
                        "parameters": [{"type": "coupon_code", "coupon_code": coupon or "-"}]})
    return out


def send_components(spec, header_text=(), body=(), header_media_id=None, location=None,
                    url_values=None, coupon=None, expire_ms=None, cards=()):
    """معاملات إرسال قالب لمستلم واحد (القيم محسوبة مسبقاً لهذا المستلم).
    `cards`: [{"media_id", "body": [...], "url_values": {index: text}}] بعدد بطاقات القالب."""
    comps = []
    fmt = spec.get("header_format")
    if fmt in ("IMAGE", "VIDEO", "DOCUMENT") and header_media_id:
        k = fmt.lower()
        comps.append({"type": "header", "parameters": [{"type": k, k: {"id": header_media_id}}]})
    elif fmt == "LOCATION" and location:
        comps.append({"type": "header", "parameters": [{"type": "location", "location": location}]})
    elif fmt == "TEXT" and header_text:
        comps.append({"type": "header", "parameters": [{"type": "text", "text": v} for v in header_text]})
    if spec.get("kind") == "lto" and (spec.get("lto") or {}).get("has_expiration") and expire_ms:
        comps.append({"type": "limited_time_offer", "parameters": [
            {"type": "limited_time_offer", "limited_time_offer": {"expiration_time_ms": int(expire_ms)}}]})
    if body:
        comps.append({"type": "body", "parameters": [{"type": "text", "text": v} for v in body]})
    comps += _button_params(spec.get("buttons") or [], url_values or {}, coupon)
    if spec.get("kind") == "carousel":
        out_cards = []
        for i, (cs, cv) in enumerate(zip(spec.get("cards") or [], cards or [])):
            k = (cs.get("format") or "IMAGE").lower()
            cc = [{"type": "header", "parameters": [{"type": k, k: {"id": cv.get("media_id")}}]}]
            if cv.get("body"):
                cc.append({"type": "body", "parameters": [{"type": "text", "text": v} for v in cv["body"]]})
            cc += _button_params(cs.get("buttons") or [], cv.get("url_values") or {}, None)
            out_cards.append({"card_index": i, "components": cc})
        comps.append({"type": "carousel", "cards": out_cards})
    return comps or None
