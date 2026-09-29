"""باني الفلو المرئي — المحرك البياني (المرحلة 5 من docs/ENTERPRISE_PLAN.md).

عدّة فلوهات لكل بوت في `config["flows"]`، لكل فلو مشغّل (أي رسالة · كلمات · بداية) ونسختان:
`draft` (يحرّرها الكانفس) و`published` (يشغّلها المحرك). الفلو رسم بياني من بطاقات؛ كل بطاقة
تشير لما بعدها (`next`) أو تتفرّع (أزرار · شرط · ساعات العمل).

**يعمل بجانب المحرك الخطّي لا بدلاً منه:** بوت بلا فلوهات منشورة يبقى على `config["flow"]` كما
هو حرفياً. الحالة في `chat_state` نفسه بـ`step = -1` وموضعها داخل البيانات (`__g`) — فلا تختلط
بحالة خطّية، وتنجو من إعادة التشغيل مثلها.

الإرسال عبر LoggedChannel دائماً (صندوق الوارد §28)، والمدخلات تمرّ بالتحقق هنا، والملفات بـ
`flow_engine._store_media` (الحصة وفحص البايتات)، والتحويل لإنسان بـ`flow_engine._escalate`.
"""
import asyncio
import json
import logging
import re
import secrets
import time
from datetime import datetime, timedelta, timezone

import database as db

log = logging.getLogger("flow_graph")

GRAPH_STEP = -1                 # قيمة step في chat_state للحالة البيانية
MAX_NODES = 200
MAX_HOPS = 60                   # حارس الحلقات: بطاقات متتالية بلا انتظار في رسالة واحدة
MAX_DELAY = 30                  # ثوانٍ — التأخير داخل حلقة البوتات (أطول منه يعطّل الجميع)
DROP_AFTER = 24 * 3600          # جلسة نشطة بلا حركة يوماً = تسرّب
VAR_RE = re.compile(r"^[A-Za-z_؀-ۿ][\w؀-ۿ]{0,39}$")
ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,40}$")
TPL_RE = re.compile(r"\{\{\s*([\w؀-ۿ.]{1,60})\s*\}\}")

TYPES = ("text", "media", "buttons", "ask", "ask_media", "tag", "set_field", "handoff", "notify",
         "save_lead", "condition", "set_var", "delay", "jump", "hours", "goal", "end",
         "location", "template", "api", "sheets", "ai", "assign", "switch", "resolve", "products", "form",
         "sequence", "payment")
WAITS = ("buttons", "ask", "ask_media", "ai", "form", "payment")
# بطاقات تتفرّع بنفسها (لا `next` عام). TWO_WAY: «نجح» في next و«فشل» في fail
BRANCHING = ("buttons", "condition", "hours", "handoff", "jump", "end", "switch", "resolve")
TWO_WAY = ("template", "api", "ai", "products", "form", "payment")
DIGITS_RE = re.compile(r"^\d{5,25}$")
RETAILER_RE = re.compile(r"^[\w.\-]{1,100}$")
SCREEN_RE = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$")
VALIDATE = ("text", "number", "email", "phone", "date", "url")
COND_OPS = ("eq", "neq", "contains", "gt", "lt", "empty", "not_empty")
TRIGGERS = ("any", "keywords", "start", "ad", "link")
SPECIFIC = ("keywords", "ad", "link")      # مشغّلات محدّدة: تتعدّد في البوت، وتبدأ فلوها حتى أثناء انتظار فلو آخر
METHODS = ("GET", "POST", "PUT", "PATCH", "DELETE")
SHEETS_RE = re.compile(r"^https://script\.google\.com/macros/s/[A-Za-z0-9_-]{10,120}/exec$")
BAD_HEADERS = {"host", "content-length", "connection", "transfer-encoding", "cookie", "upgrade"}
AI_EXIT = ["خلاص", "شكرا", "شكراً", "القائمة", "menu", "exit"]
TEST_TTL = 30 * 60               # رابط «جرّب على واتساب» صالح نصف ساعة
TEST_RE = re.compile(r"\btest-([0-9a-f]{8})\b")
REMIND_MAX = 23 * 60             # دقائق — التذكير داخل نافذة واتساب (24 ساعة)


class Invalid(ValueError):
    """رمز خطأ: node:<id>:<سبب> · flow:<سبب>"""


def _s(v, n):
    return str(v or "").strip()[:n]


def _team_ref(nid, v, teams):
    """فريق من فِرق الحساب أو None. `teams=None` يتخطّى الفحص (اختبارات المحرك وحده)."""
    if v in (None, "", 0):
        return None
    try:
        v = int(v)
    except (TypeError, ValueError):
        raise Invalid(f"node:{nid}:team")
    if teams is not None and v not in teams:
        raise Invalid(f"node:{nid}:team")
    return v


def _node(nid, n, link, asset_ok, flow_ids, fields, members=None, teams=None, seqs=None):
    t = n.get("type")
    if t not in TYPES:
        raise Invalid(f"node:{nid}:type")
    try:
        c = {"type": t, "x": float(n.get("x") or 0), "y": float(n.get("y") or 0)}
    except (TypeError, ValueError):
        raise Invalid(f"node:{nid}:position")

    def var(key="var", required=True):
        v = _s(n.get(key), 40)
        if (required or v) and not VAR_RE.match(v):
            raise Invalid(f"node:{nid}:{key}")
        return v

    if t in ("text", "ask", "ask_media", "buttons"):
        c["text"] = _s(n.get("text"), 1024)
        if not c["text"]:
            raise Invalid(f"node:{nid}:text")
    if t in ("ask", "ask_media"):
        c["var"] = var()
        if t == "ask":
            c["validate"] = n.get("validate") if n.get("validate") in VALIDATE else "text"
            c["error"] = _s(n.get("error"), 300)
    elif t == "media":
        if not asset_ok(n.get("asset")):
            raise Invalid(f"node:{nid}:asset")
        c["asset"], c["caption"] = int(n["asset"]), _s(n.get("caption"), 1024)
    elif t == "buttons":
        opts = n.get("options") or []
        if not 1 <= len(opts) <= 10:
            raise Invalid(f"node:{nid}:options")
        c["var"], c["options"], seen = var(required=False), [], set()
        for o in opts:
            label = _s((o or {}).get("label"), 20)
            if not label or label in seen:
                raise Invalid(f"node:{nid}:option_label")
            seen.add(label)
            c["options"].append({"label": label, "next": link((o or {}).get("next"), nid, "option")})
    elif t == "condition":
        c["var"] = _s(n.get("var"), 60)
        if not c["var"]:
            raise Invalid(f"node:{nid}:var")
        c["op"] = n.get("op") if n.get("op") in COND_OPS else "eq"
        c["value"] = _s(n.get("value"), 200)
        c["yes"], c["no"] = link(n.get("yes"), nid, "yes"), link(n.get("no"), nid, "no")
    elif t == "hours":
        try:
            c["start"] = max(0, min(23, int(n.get("start", 9))))
            c["end"] = max(1, min(24, int(n.get("end", 17))))
            c["tz"] = max(-12.0, min(14.0, float(n.get("tz", 3))))
        except (TypeError, ValueError):
            raise Invalid(f"node:{nid}:hours")
        days = [int(d) for d in (n.get("days") or [0, 1, 2, 3, 6]) if str(d).isdigit() and 0 <= int(d) <= 6]
        c["days"] = sorted(set(days)) or [0, 1, 2, 3, 6]
        c["open"], c["closed"] = link(n.get("open"), nid, "open"), link(n.get("closed"), nid, "closed")
    elif t == "set_var":
        c["var"], c["value"] = var(), _s(n.get("value"), 500)
    elif t == "tag":
        tags = [_s(x, 50) for x in (n.get("tags") or []) if _s(x, 50)]
        if not tags:
            raise Invalid(f"node:{nid}:tags")
        c["tags"] = tags[:10]
    elif t == "set_field":
        c["field"] = _s(n.get("field"), 40)
        if c["field"] not in ("name", "email") and c["field"] not in fields:
            raise Invalid(f"node:{nid}:field")
        c["value"] = _s(n.get("value"), 500)
    elif t in ("handoff", "notify", "end"):
        c["text"] = _s(n.get("text"), 1024)
        if t == "handoff":
            c["reason"] = _s(n.get("reason"), 200)
            c["team"] = _team_ref(nid, n.get("team"), teams)
        if t == "notify" and not c["text"]:
            raise Invalid(f"node:{nid}:text")
    elif t == "delay":
        try:
            c["seconds"] = max(1, min(MAX_DELAY, int(n.get("seconds") or 2)))
        except (TypeError, ValueError):
            raise Invalid(f"node:{nid}:seconds")
    elif t == "jump":
        if n.get("flow") not in flow_ids:
            raise Invalid(f"node:{nid}:flow")
        c["flow"] = n["flow"]
    elif t == "goal":
        c["name"] = re.sub(r"[^\w-]", "_", _s(n.get("name"), 40)) or "goal"
        import growth
        c["event"] = n.get("event") if n.get("event") in growth.CAPI_EVENTS else ""
        c["value"] = _s(n.get("value"), 60)          # رقم أو {{متغيّر}} — للشراء
        c["currency"] = (_s(n.get("currency"), 3) or "SAR").upper()
    elif t == "location":
        try:
            c["lat"], c["lng"] = float(n.get("lat")), float(n.get("lng"))
        except (TypeError, ValueError):
            raise Invalid(f"node:{nid}:location")
        if not (-90 <= c["lat"] <= 90 and -180 <= c["lng"] <= 180):
            raise Invalid(f"node:{nid}:location")
        c["name"], c["address"] = _s(n.get("name"), 100), _s(n.get("address"), 200)
    elif t == "template":
        c["name"] = _s(n.get("name"), 512)
        if not re.fullmatch(r"[a-z0-9_]{1,512}", c["name"]):
            raise Invalid(f"node:{nid}:template")
        c["lang"] = _s(n.get("lang"), 15) or "ar"
        if not re.fullmatch(r"[A-Za-z_]{2,15}", c["lang"]):
            raise Invalid(f"node:{nid}:template")
        c["vars"] = [_s(v, 1000) or "-" for v in (n.get("vars") or [])][:20]
    elif t == "api":
        c["method"] = n.get("method") if n.get("method") in METHODS else "GET"
        c["url"] = _s(n.get("url"), 1000)
        host = re.match(r"^https://([^/?#{}\s]+)(?:[/?#]|$)", c["url"])
        if not host or "@" in host.group(1):
            raise Invalid(f"node:{nid}:url")         # المضيف نصّ ثابت — لا متغيّر فيه (SSRF)
        c["headers"] = []
        for h in (n.get("headers") or [])[:5]:
            k, v = _s((h or {}).get("k"), 60), _s((h or {}).get("v"), 500)
            if not k:
                continue
            if k.lower() in BAD_HEADERS or not re.fullmatch(r"[A-Za-z0-9-]{1,60}", k):
                raise Invalid(f"node:{nid}:headers")
            c["headers"].append({"k": k, "v": v})
        c["body"] = _s(n.get("body"), 4000) if c["method"] != "GET" else ""
        c["save"] = []
        for m in (n.get("save") or [])[:10]:
            v, p = _s((m or {}).get("var"), 40), _s((m or {}).get("path"), 120)
            if not v and not p:
                continue
            if not VAR_RE.match(v) or not re.fullmatch(r"[\w.\-؀-ۿ]{1,120}", p):
                raise Invalid(f"node:{nid}:save")
            c["save"].append({"var": v, "path": p})
        c["status_var"] = var("status_var", required=False)
    elif t == "sheets":
        c["url"] = _s(n.get("url"), 300)
        if not SHEETS_RE.match(c["url"]):
            raise Invalid(f"node:{nid}:sheets")
        c["fields"] = [v for v in (_s(x, 40) for x in (n.get("fields") or [])) if VAR_RE.match(v)][:30]
    elif t == "ai":
        c["text"] = _s(n.get("text"), 1024)
        try:
            c["turns"] = max(1, min(20, int(n.get("turns") or 5)))
        except (TypeError, ValueError):
            raise Invalid(f"node:{nid}:turns")
        words = [_s(w, 30).lower() for w in (n.get("exit") or []) if _s(w, 30)][:10]
        c["exit"] = words or list(AI_EXIT)
    elif t == "assign":
        mode = n.get("mode") if n.get("mode") in ("member", "least", "team") else "member"
        c["mode"] = mode
        if mode == "team":
            c["team"] = _team_ref(nid, n.get("team"), teams)
            if not c["team"]:
                raise Invalid(f"node:{nid}:team")
        elif mode == "member":
            try:
                c["member"] = int(n.get("member"))
            except (TypeError, ValueError):
                raise Invalid(f"node:{nid}:member")
            if members is not None and c["member"] not in members:
                raise Invalid(f"node:{nid}:member")
        c["text"] = _s(n.get("text"), 1024)
    elif t == "switch":
        c["var"] = _s(n.get("var"), 60)
        if not c["var"]:
            raise Invalid(f"node:{nid}:var")
        cases, seen = [], set()
        for x in (n.get("cases") or [])[:10]:
            v = _s((x or {}).get("value"), 100)
            if not v or _norm(v) in seen:
                raise Invalid(f"node:{nid}:cases")
            seen.add(_norm(v))
            cases.append({"value": v, "next": link((x or {}).get("next"), nid, "case")})
        if not cases:
            raise Invalid(f"node:{nid}:cases")
        c["cases"], c["other"] = cases, link(n.get("other"), nid, "other")
    elif t == "resolve":
        c["text"] = _s(n.get("text"), 1024)
    elif t == "payment":
        import payments_gw as GW
        c["amount"] = _s(n.get("amount"), 60)            # رقم أو {{متغيّر}} — يُحسب عند التشغيل
        if not c["amount"]:
            raise Invalid(f"node:{nid}:amount")
        c["currency"] = _s(n.get("currency"), 3).upper()     # فارغ = عملة الحساب الافتراضية في إعداد البوابة
        if c["currency"] and c["currency"] not in GW.CURRENCIES:
            raise Invalid(f"node:{nid}:currency")
        c["description"] = _s(n.get("description"), 200)
        c["text"] = _s(n.get("text"), 700)
        c["button"] = _s(n.get("button"), 20)
        try:
            c["minutes"] = max(5, min(24 * 60, int(n.get("minutes") or 60)))
        except (TypeError, ValueError):
            raise Invalid(f"node:{nid}:minutes")
        c["var"] = var(required=False)
    elif t == "sequence":
        try:
            c["sequence"] = int(n.get("sequence"))
        except (TypeError, ValueError):
            raise Invalid(f"node:{nid}:sequence")
        if seqs is not None and c["sequence"] not in seqs:
            raise Invalid(f"node:{nid}:sequence")
    elif t == "products":
        c["catalog"] = _s(n.get("catalog"), 25)
        if not DIGITS_RE.match(c["catalog"]):
            raise Invalid(f"node:{nid}:catalog")
        ids = [_s(x, 100) for x in (n.get("items") or []) if _s(x, 100)]
        if not 1 <= len(ids) <= 30 or not all(RETAILER_RE.match(x) for x in ids):
            raise Invalid(f"node:{nid}:items")
        c["items"] = ids
        c["text"], c["header"] = _s(n.get("text"), 1024), _s(n.get("header"), 60)
        if len(ids) > 1 and (not c["header"] or not c["text"]):
            raise Invalid(f"node:{nid}:header")        # قائمة المنتجات تشترط ترويسة ونصاً عند Meta
    elif t == "form":
        c["flow_id"] = _s(n.get("flow_id"), 25)
        if not DIGITS_RE.match(c["flow_id"]):
            raise Invalid(f"node:{nid}:flow_id")
        c["screen"] = _s(n.get("screen"), 64)
        if not SCREEN_RE.match(c["screen"]):
            raise Invalid(f"node:{nid}:screen")
        c["cta"] = _s(n.get("cta"), 20)
        c["text"] = _s(n.get("text"), 1024)
        if not c["cta"] or not c["text"]:
            raise Invalid(f"node:{nid}:text")
        c["header"] = _s(n.get("header"), 60)
        c["prefix"] = var("prefix", required=False)
    if t not in BRANCHING:
        c["next"] = link(n.get("next"), nid)
    if t in TWO_WAY:
        c["fail"] = link(n.get("fail"), nid, "fail")
    return c


def clean_graph(raw, asset_ok=lambda a: True, flow_ids=(), fields=(), members=None, teams=None, seqs=None):
    """رسم من الكانفس ⇒ رسم نظيف أو Invalid. `asset_ok(id)`: هل الملف ملك الحساب.
    `flow_ids`: فلوهات البوت (لبطاقة الانتقال). `fields`: مفاتيح حقول جهات الاتصال المخصّصة.
    `members`: معرّفات صاحب الحساب وفريقه (لبطاقة الإسناد) — None يتخطّى الفحص."""
    nodes_in = (raw or {}).get("nodes") or {}
    if not isinstance(nodes_in, dict) or not 1 <= len(nodes_in) <= MAX_NODES:
        raise Invalid("flow:size")
    ids = set(nodes_in)
    if not all(ID_RE.match(i) for i in ids):
        raise Invalid("flow:ids")

    def link(v, nid, what="next"):
        if v in (None, ""):
            return None
        if not isinstance(v, str) or v not in ids or (v == nid and what == "next"):
            raise Invalid(f"node:{nid}:{what}")
        return v

    out = {nid: _node(nid, n or {}, link, asset_ok, flow_ids, fields, members, teams, seqs) for nid, n in nodes_in.items()}
    start = (raw or {}).get("start")
    if start not in out:
        raise Invalid("flow:start")
    return {"start": start, "nodes": out}


def clean_trigger(t):
    t = t or {}
    kind = t.get("type") if t.get("type") in TRIGGERS else "any"
    words = [_s(w, 60).lower() for w in (t.get("keywords") or []) if _s(w, 60)][:30]
    if kind == "keywords" and not words:
        raise Invalid("flow:keywords")
    out = {"type": kind, "keywords": words, "match": "exact" if t.get("match") == "exact" else "contains"}
    if kind == "ad":                                  # نقرة إعلان CTWA: كل الإعلانات، أو معرّفات بعينها
        out["ads"] = [a for a in (_s(x, 30) for x in (t.get("ads") or [])) if re.fullmatch(r"\d{5,30}", a)][:30]
    if kind == "link":                                # رابط تتبّع بعينه (رموزه من صفحة النمو)
        out["links"] = [x for x in (_s(v, 6).lower() for v in (t.get("links") or [])) if re.fullmatch(r"[a-z0-9]{6}", x)][:30]
        if not out["links"]:
            raise Invalid("flow:links")
    return out


def new_id(prefix="f"):
    return f"{prefix}_{secrets.token_hex(4)}"


# ─────────────────────────── اختيار الفلو والقيم ───────────────────────────
def _norm(s):
    s = (s or "").strip().lower()
    s = re.sub("[إأآا]", "ا", s)
    return re.sub("[ًٌٍَُِّْـ]", "", s).replace("ة", "ه").replace("ى", "ي")


def live_flows(cfg):
    return [f for f in (cfg.get("flows") or []) if f.get("active") and (f.get("published") or {}).get("nodes")]


def has_graph(cfg):
    return bool(live_flows(cfg)) or bool(_tests(cfg))


# ---- «جرّب على واتساب»: مسودة مُتحقَّق منها تعمل لمن يرسل رمزها فقط، نصف ساعة، بلا إحصاءات ----
def _tests(cfg, now=None):
    now = now or time.time()
    return {k: v for k, v in (cfg.get("flow_tests") or {}).items() if (v or {}).get("exp", 0) > now}


def add_test(cfg, flow, graph):
    """يسجّل رمز تجربة في الإعداد (المستدعي يحفظ الإعداد كاملاً). يرجّع الرمز «test-xxxxxxxx»."""
    tests = _tests(cfg)
    while len(tests) >= 5:                      # أقدمها يسقط — لا تتراكم مسودات في الإعداد
        tests.pop(min(tests, key=lambda k: tests[k]["exp"]))
    code = secrets.token_hex(4)
    tests[code] = {"f": flow["id"], "name": flow.get("name", ""), "graph": graph, "exp": int(time.time()) + TEST_TTL}
    cfg["flow_tests"] = tests
    return "test-" + code


def _test_flow(cfg, code):
    t = _tests(cfg).get(code)
    return {"id": t["f"], "name": t.get("name", ""), "published": t["graph"], "test": code} if t else None


def pick_flow(cfg, msg):
    """أي فلو يبدأ لهذه الرسالة؟ نقرة الإعلان ورابط التتبّع أولاً (مصدر العميل)، ثم الكلمات، ثم «البداية»
    لرسالة البدء، ثم «أي رسالة»."""
    flows = live_flows(cfg)
    ref, link = msg.get("referral") or {}, msg.get("link")
    for f in flows:
        tr = f.get("trigger") or {}
        if tr.get("type") == "ad" and ref and (not tr.get("ads") or ref.get("source_id") in tr["ads"]):
            return f
        if tr.get("type") == "link" and link and link in (tr.get("links") or []):
            return f
    text = _norm(msg.get("text"))
    if text:
        for f in flows:
            tr = f.get("trigger") or {}
            if tr.get("type") != "keywords":
                continue
            for w in tr.get("keywords") or []:
                w = _norm(w)
                if (tr.get("match") == "exact" and text == w) or (tr.get("match") != "exact" and w and w in text):
                    return f
    if msg.get("kind") == "start":
        for f in flows:
            if (f.get("trigger") or {}).get("type") == "start":
                return f
    for f in flows:
        if (f.get("trigger") or {}).get("type", "any") == "any":
            return f
    return None


def render(text, data, contact=None):
    """{{var}} من بيانات الجلسة، و{{contact.name}} أو {{contact.<حقل>}} من جهة الاتصال."""
    def sub(m):
        k = m.group(1)
        if k.startswith("contact."):
            key = k[8:]
            v = (contact or {}).get(key)
            if v is None:
                v = ((contact or {}).get("fields") or {}).get(key)
            return "" if v is None else str(v)
        v = data.get(k)
        return "" if v is None else str(v)
    return TPL_RE.sub(sub, text or "")


_AR_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")


def check(validate, ans):
    """(القيمة المنظّفة، صالحة؟) لكل نوع إدخال."""
    a = (ans or "").strip()
    if not a:
        return a, False
    if validate == "number":
        a2 = a.translate(_AR_DIGITS).replace(",", "")
        try:
            float(a2)
            return a2, True
        except ValueError:
            return a, False
    if validate == "email":
        return a.lower(), bool(re.fullmatch(r"[^@\s]{1,64}@[^@\s]{1,255}\.[^@\s]{2,}", a))
    if validate == "phone":
        d = re.sub(r"[\s\-()]", "", a.translate(_AR_DIGITS))
        return d, bool(re.fullmatch(r"\+?\d{8,15}", d))
    if validate == "date":
        import crm
        d = crm.parse_date(a)
        return (d or a), bool(d)
    if validate == "url":
        return a, bool(re.fullmatch(r"https?://\S{3,}", a))
    return a[:1000], True


def evaluate(node, data, contact=None):
    var = node["var"]
    v = render(var if "{{" in var else "{{" + var + "}}", data, contact)
    target = render(node.get("value", ""), data, contact)
    op = node.get("op", "eq")
    if op == "empty":
        return not v.strip()
    if op == "not_empty":
        return bool(v.strip())
    if op in ("gt", "lt"):
        try:
            a, b = float(v.translate(_AR_DIGITS)), float(target.translate(_AR_DIGITS))
        except ValueError:
            return False
        return a > b if op == "gt" else a < b
    if op == "contains":
        return _norm(target) in _norm(v)
    same = _norm(v) == _norm(target)
    return same if op == "eq" else not same


def is_open(node, now=None):
    tz = timezone(timedelta(hours=node.get("tz", 3)))
    t = datetime.fromtimestamp(now or time.time(), tz)
    # أيام الأسبوع بترقيم Python: 0 الاثنين … 6 الأحد — المحرّر يرسل نفس الترقيم
    return t.weekday() in node.get("days", []) and node.get("start", 9) <= t.hour < node.get("end", 17)


# ─────────────────────────── التشغيل ───────────────────────────
def _find(cfg, fid):
    return next((f for f in cfg.get("flows") or [] if f.get("id") == fid), None)


def _num(peer):
    from flow_engine import _peer_num
    return _peer_num(peer)


async def handle(bot_row, cfg, channel, raw, peer, msg):
    """نقطة الدخول من flow_engine.handle_message. يرجّع True لو تولّى الرسالة.
    False = لا حالة بيانية ولا فلو مطابق — يكمل المحرك الخطّي (انتقال سلس بين النظامين)."""
    bot_id = bot_row["id"]
    state = db.get_chat_state(bot_id, peer)
    # رمز «جرّب على واتساب»: يتقدّم على كل شيء — حتى محادثة خطّية جارية (المختبِر يطلبه صراحةً)
    m = TEST_RE.search(f"{msg.get('text') or ''} {msg.get('start_arg') or ''}".lower())
    test = _test_flow(cfg, m.group(1)) if m and msg.get("kind") in ("start", "text") else None
    if test:
        old = (state or {}).get("data", {}).get("__g") if state and state["step"] == GRAPH_STEP else None
        if old:
            db.flow_session_end(old.get("s"), "dropped", old.get("n"))
        db.clear_chat_state(bot_id, peer)
        db.add_bot_user(bot_id, _num(peer), msg.get("name", ""), peer=peer)
        await channel.remove_keyboard(peer, f"🧪 تجربة «{test['name']}» (مسودة — لا تُحتسب في الإحصاءات)")
        await run(bot_row, cfg, channel, peer, test, test["published"]["start"], {"_test": 1}, None)
        return True
    if state and state["step"] != GRAPH_STEP:
        return False                              # محادثة بدأت على الفلو الخطّي — تكمل عليه
    pick = pick_flow(cfg, msg) if msg.get("kind") in ("start", "text") else None
    g = state["data"].get("__g") if state else None
    # كلمة مشغّل لفلو آخر أثناء الانتظار = بداية جديدة (العميل غيّر وجهته)، وإلا يكمل حيث توقّف
    switching = bool(pick and (pick.get("trigger") or {}).get("type") in SPECIFIC
                     and g and pick["id"] != g.get("f"))
    if g and not switching:
        flow = _test_flow(cfg, g["t"]) if g.get("t") else _find(cfg, g.get("f"))
        if flow and (flow.get("published") or {}).get("nodes", {}).get(g.get("n")):
            db.add_bot_user(bot_id, _num(peer), msg.get("name", ""), peer=peer)
            db.touch_bot_user(bot_id, peer)
            return await _resume(bot_row, cfg, channel, peer, flow, g, state["data"], msg)
        db.clear_chat_state(bot_id, peer)          # فلو حُذف أو نُشر بدون هذه البطاقة
    if not pick:
        return False
    if g:
        db.flow_session_end(g.get("s"), "dropped", g.get("n"))
    db.add_bot_user(bot_id, _num(peer), msg.get("name", ""), peer=peer)
    db.log_event(bot_id, "start")
    await start(bot_row, cfg, channel, peer, pick, {})
    return True


async def start(bot_row, cfg, channel, peer, flow, data):
    sid = db.flow_session_start(bot_row["id"], flow["id"], peer)
    await run(bot_row, cfg, channel, peer, flow, flow["published"]["start"], dict(data), sid)


_ERR_TEXT = {"number": "🔢 من فضلك اكتب رقماً.", "email": "📧 اكتب بريداً صحيحاً مثل name@mail.com",
             "phone": "📱 اكتب رقم هاتف صحيحاً.", "date": "📅 اكتب التاريخ هكذا: 26/09/2026",
             "url": "🔗 اكتب رابطاً يبدأ بـ https://"}


async def _resume(bot_row, cfg, channel, peer, flow, g, data, msg):
    node = flow["published"]["nodes"][g["n"]]
    t = node["type"]
    ans = msg.get("text") or ""
    if t == "buttons":
        labels = [o["label"] for o in node["options"]]
        if ans.strip().isdigit() and 1 <= int(ans.strip()) <= len(labels):   # القائمة المرقّمة في واتساب
            ans = labels[int(ans.strip()) - 1]
        opt = next((o for o in node["options"] if _norm(o["label"]) == _norm(ans)), None)
        if not opt:
            await channel.send_buttons(peer, "↩️ اختر من الأزرار من فضلك:", labels)
            return True
        if node.get("var"):
            data[node["var"]] = opt["label"]
        nxt = opt["next"]
    elif t == "ask_media":
        if msg.get("kind") != "media":
            await channel.send_text(peer, "📎 من فضلك أرسل الملف نفسه.")
            return True
        from flow_engine import _store_media
        ref = await _store_media(bot_row, channel, peer, msg)
        if ref is None:
            return True
        data[node["var"]] = ref
        nxt = node.get("next")
    elif t == "form":
        form = msg.get("form") if msg.get("kind") == "form" else None
        if not isinstance(form, dict) or (form.get("flow_token") and form["flow_token"] != data.get("__ft")):
            await channel.send_text(peer, "📝 من فضلك املأ النموذج من الزر في الرسالة السابقة.")
            return True
        for k, v in form.items():
            if k == "flow_token":
                continue
            key = f"{node['prefix']}_{k}" if node.get("prefix") else k
            if VAR_RE.match(key):
                v = ", ".join(map(str, v)) if isinstance(v, list) else v
                data[key] = str(v)[:1000] if not isinstance(v, (dict, list)) else json.dumps(v, ensure_ascii=False)[:1000]
        data.pop("__ft", None)
        nxt = node.get("next")
    elif t == "payment":
        import chat_pay as CP
        pid = data.get("__pay")
        if _norm(ans) in {_norm(w) for w in CP.CANCEL_WORDS} and pid and db.settle_chat_payment(pid, "cancelled"):
            data.pop("__pay", None)
            if node.get("var"):
                data[node["var"]] = "cancelled"
            nxt = node.get("fail")
        else:
            st = await asyncio.to_thread(CP.confirm, pid) if pid else None    # ربما دفع ولم يصل الإشعار بعد
            if st in ("paid", "failed", "expired"):
                return True                            # التسوية استأنفت الفلو من فرعها
            p = db.get_chat_payment(pid) if pid else None
            link = ("\n" + p["url"]) if p and p.get("url") else ""
            await channel.send_text(peer, "⏳ لم يصلنا الدفع بعد." + link + "\nللإلغاء اكتب: إلغاء")
            return True
    elif t == "ai":
        if not ans.strip():
            await channel.send_text(peer, "📝 اكتب سؤالك نصاً من فضلك.")
            return True
        if _norm(ans) in {_norm(w) for w in node.get("exit") or []}:
            nxt = node.get("next")
        else:
            nxt = await _ai_turn(bot_row, cfg, channel, peer, flow, g, node, data, ans)
            if nxt is _STAY:
                return True
    else:                                          # ask
        if msg.get("kind") == "media" and not ans:
            await channel.send_text(peer, "📝 هذه الخطوة تحتاج إجابة نصية.")
            return True
        val, ok = check(node.get("validate", "text"), ans)
        if not ok:
            await channel.send_text(peer, node.get("error") or _ERR_TEXT.get(node.get("validate"), "↩️ أعد المحاولة من فضلك."))
            return True
        data[node["var"]] = val
        nxt = node.get("next")
    await run(bot_row, cfg, channel, peer, flow, nxt, data, g.get("s"))
    return True


_STAY = object()


async def _ai_turn(bot_row, cfg, channel, peer, flow, g, node, data, ans):
    """رد «عقل البوت» على سؤال داخل الفلو — بالحصة والمحفظة وحجز ما بعد التوليد كما هي في
    flow_engine._ai_answer حرفياً (لا منطق مال هنا). يرجّع البطاقة التالية أو _STAY للبقاء."""
    import flow_engine as FE
    inner = getattr(channel, "_c", channel)
    ok = await FE._ai_answer(bot_row, cfg, inner, peer, ans)
    bot_id = bot_row["id"]
    if FE.human_active(bot_id, peer, db.get_conversation(bot_id, peer)):
        # الذكاء حوّل المحادثة لإنسان (أسئلة متتالية خارج النشاط): الجلسة تنتهي «تحويلاً»
        _save_lead(bot_row, peer, data)
        db.clear_chat_state(bot_id, peer)
        db.flow_session_end(g.get("s"), "handoff", g.get("n"))
        return _STAY
    if not ok:
        return node.get("fail") or node.get("next")       # لا مفتاح · نفدت الحصة والرصيد · تعطّل المزوّد
    data["__ai"] = int(data.get("__ai") or 0) + 1
    if data["__ai"] >= node.get("turns", 5):
        data.pop("__ai", None)
        return node.get("next")
    db.set_chat_state(bot_id, peer, GRAPH_STEP, data)
    db.flow_session_touch(g.get("s"), g.get("n"), *_deadlines(flow))
    return _STAY


def _contact(bot_id, peer):
    cid = db.contact_id_for_peer(bot_id, peer)
    return (db.get_contact_by_id(cid) if cid else None), cid


async def run(bot_row, cfg, channel, peer, flow, nid, data, sid):
    """ينفّذ البطاقات من `nid` حتى بطاقة تنتظر رداً (فيحفظ الموضع) أو نهاية الفلو."""
    bot_id = bot_row["id"]
    nodes = flow["published"]["nodes"]
    contact, cid = _contact(bot_id, peer)
    last, hops = nid, 0
    while nid and nid in nodes:
        hops += 1
        if hops > MAX_HOPS:
            log.warning("flow %s bot=%s: hop limit (loop?) at %s", flow["id"], bot_id, nid)
            break
        last = nid
        node = nodes[nid]
        t = node["type"]
        if not flow.get("test"):
            db.flow_visit(bot_id, flow["id"], nid)
        say = lambda s: render(s, data, contact)
        if t == "text":
            await channel.remove_keyboard(peer, say(node["text"]))
        elif t == "media":
            from flow_engine import _asset
            asset = _asset(bot_row, node.get("asset"))
            if asset:
                try:
                    await channel.send_media(peer, asset, bot_id, caption=say(node.get("caption")) or None)
                except Exception:
                    log.exception("flow media failed bot=%s", bot_id)
            elif node.get("caption"):
                await channel.remove_keyboard(peer, say(node["caption"]))
        elif t == "switch":
            v = _norm(render("{{" + node["var"] + "}}" if "{{" not in node["var"] else node["var"], data, contact))
            nid = next((x["next"] for x in node["cases"] if _norm(x["value"]) == v), node.get("other"))
            continue
        elif t == "resolve":
            if node.get("text"):
                await channel.remove_keyboard(peer, say(node["text"]))
            _save_lead(bot_row, peer, data)
            db.clear_chat_state(bot_id, peer)
            db.flow_session_end(sid, "completed", nid)
            db.resolve_conversation(bot_id, peer)
            if not flow.get("test"):
                db.log_event(bot_id, "resolved")
            return
        elif t == "products":
            nid = node["next"] if await _send_products(bot_row, channel, peer, node, say) else node.get("fail")
            continue
        elif t == "payment":
            import chat_pay as CP
            cur = node.get("currency") or (CP.public_config(bot_row["owner_id"]) or {}).get("currency") or "SAR"
            amount = CP.to_minor(say(node["amount"]), cur)
            p, err = (await CP.request(bot_row, channel, peer, amount, cur, say(node.get("description")),
                                       minutes=node.get("minutes"), text=say(node.get("text")), button=node.get("button"),
                                       flow_id=flow["id"], node_id=nid, name=(contact or {}).get("name") or "")
                      if amount else (None, "amount"))
            if not p:
                log.info("flow %s payment not created bot=%s: %s", flow["id"], bot_id, err)
                nid = node.get("fail")
                continue
            data["__pay"] = p["id"]
            data["__g"] = {"f": flow["id"], "n": nid, "s": sid}
            if flow.get("test"):
                data["__g"]["t"] = flow["test"]
            db.set_chat_state(bot_id, peer, GRAPH_STEP, data)
            db.flow_session_touch(sid, nid)          # المهلة هنا مدة الرابط نفسه (chat_pay.sweep)
            return
        elif t == "form":
            token = secrets.token_hex(8)
            if not await _send_form(bot_row, channel, peer, node, say, token):
                nid = node.get("fail")
                continue
            data["__ft"] = token
            data["__g"] = {"f": flow["id"], "n": nid, "s": sid}
            if flow.get("test"):
                data["__g"]["t"] = flow["test"]
            db.set_chat_state(bot_id, peer, GRAPH_STEP, data)
            db.flow_session_touch(sid, nid, *_deadlines(flow))
            return
        elif t in WAITS:
            if t == "buttons":
                await channel.send_buttons(peer, say(node["text"]), [o["label"] for o in node["options"]])
            elif node.get("text"):
                await channel.remove_keyboard(peer, say(node["text"]))
            data["__g"] = {"f": flow["id"], "n": nid, "s": sid}
            if flow.get("test"):
                data["__g"]["t"] = flow["test"]
            db.set_chat_state(bot_id, peer, GRAPH_STEP, data)
            db.flow_session_touch(sid, nid, *_deadlines(flow))
            return
        elif t == "condition":
            nid = node["yes"] if evaluate(node, data, contact) else node["no"]
            continue
        elif t == "hours":
            nid = node["open"] if is_open(node) else node["closed"]
            continue
        elif t == "set_var":
            data[node["var"]] = say(node["value"])
        elif t == "tag":
            if cid:
                db.tag_contact_by_names(bot_row["owner_id"], cid, node["tags"])
                import sequences as SQ               # وسم يشغّل تسلسلاً ⇒ يُسجَّل العميل فيه
                SQ.on_tags(bot_row["owner_id"], cid, node["tags"])
        elif t == "set_field":
            if cid:
                db.set_contact_value(bot_row["owner_id"], cid, node["field"], say(node["value"]))
                contact, cid = _contact(bot_id, peer)
        elif t == "notify":
            from flow_engine import notify_owner
            await notify_owner(bot_row, channel, say(node["text"]))
        elif t == "save_lead":
            _save_lead(bot_row, peer, data)
        elif t == "goal":
            if not flow.get("test"):
                db.log_event(bot_id, f"goal_{node['name']}"[:60])
                if node.get("event"):                 # تحويل لـ Meta لعميل جاء من إعلان (Conversions API)
                    import growth
                    try:
                        val = float(say(node.get("value") or "").translate(_AR_DIGITS).replace(",", "")) if node.get("value") else None
                    except ValueError:
                        val = None
                    growth.capi_async(bot_row, peer, node["event"], val, node.get("currency"))
        elif t == "location":
            await channel.send_location(peer, node["lat"], node["lng"], say(node.get("name")), say(node.get("address")))
        elif t == "template":
            nid = node["next"] if await _send_template(bot_row, channel, peer, flow, node, say) else node.get("fail")
            continue
        elif t == "api":
            nid = node["next"] if await _api_call(bot_id, node, data, contact) else node.get("fail")
            continue
        elif t == "sheets":
            await _sheets_append(bot_id, node, data, peer, flow)
        elif t == "assign":
            await _assign(bot_row, channel, peer, cid, node, say)
        elif t == "sequence":
            if not flow.get("test"):                  # التجربة لا تسجّل المختبِر في متابعة حقيقية
                import sequences as SQ
                SQ.enroll(db.get_sequence(node["sequence"], bot_row["owner_id"]), bot_id, peer)
        elif t == "delay":
            await asyncio.sleep(node["seconds"])
        elif t == "jump":
            target = _find(cfg, node["flow"])
            _save_lead(bot_row, peer, data)
            db.clear_chat_state(bot_id, peer)
            db.flow_session_end(sid, "completed", nid)
            if target and (target.get("published") or {}).get("nodes") and target.get("id") != flow["id"]:
                return await start(bot_row, cfg, channel, peer, target,
                                   {k: v for k, v in data.items() if not k.startswith("_")})
            return
        elif t == "handoff":
            from flow_engine import _escalate
            if node.get("text"):
                await channel.remove_keyboard(peer, say(node["text"]))
            _save_lead(bot_row, peer, data)
            db.clear_chat_state(bot_id, peer)
            db.flow_session_end(sid, "handoff", nid)
            await _escalate(bot_row, channel, peer, node.get("reason") or f"فلو «{flow.get('name', '')}»", say=False,
                            team_id=node.get("team"))
            return
        elif t == "end":
            if node.get("text"):
                await channel.remove_keyboard(peer, say(node["text"]))
            break
        nid = node.get("next")
    # النهاية: الفلو اكتمل. البيانات المجمَّعة تُحفظ كـ lead (تصدير «الإدخالات» يعمل كما في الخطّي)
    _save_lead(bot_row, peer, data)
    db.clear_chat_state(bot_id, peer)
    db.flow_session_end(sid, "completed", last)


def _save_lead(bot_row, peer, data):
    clean = {k: v for k, v in data.items() if not k.startswith("_")}
    if clean and not data.get("_saved") and not data.get("_test"):
        lead_id = db.add_lead(bot_row["id"], _num(peer), clean)
        db.attach_media_to_lead(bot_row["id"], peer, lead_id)
        data["_saved"] = 1
        if json.loads(bot_row.get("config_json") or "{}").get("capi_lead"):
            import growth                              # «عميل محتمل» لـ Meta لمن جاء من إعلان
            growth.capi_async(bot_row, peer, "LeadSubmitted")


# ─────────────────────────── بطاقات التكامل ───────────────────────────
async def _send_template(bot_row, channel, peer, flow, node, say, category=None):
    """قالب واتساب معتمد من داخل الفلو — بقواعد المال نفسها للبث (AGENTS §19–§20):
    الفئة من Meta الآن (تعذّرها = لا إرسال)، الخصم الذرّي قبل الإرسال، والردّ في finally
    لو لم تقبله Meta. التسعير وقراءة الفئة من app.py عبر broadcasts._HOOKS (مصدر واحد)."""
    import broadcasts as BC
    inner = getattr(channel, "_c", channel)
    if (bot_row.get("channel") or "") != "whatsapp" or not hasattr(inner, "send_template") \
            or "category" not in BC._HOOKS:
        return False
    owner = bot_row["owner_id"]
    if category is None:                     # المستدعي قرأها من Meta للتوّ (التكاملات) — لا نداء ثانٍ
        category = await asyncio.to_thread(BC._HOOKS["category"], bot_row, node["name"], node["lang"])
    if category is None:
        return False
    q = BC._HOOKS["quote"](owner, 1, category)
    ref = f"flow:{bot_row['id']}:{flow['id']}"
    charged = 0
    if q["billable"]:
        if db.wallet_charge(owner, q["cost"], ref=ref, note=f"flow template {node['name']}") is None:
            return False
        charged = q["cost"]
    res = None
    try:
        vals = [(say(v) or "-")[:1000] for v in node.get("vars") or []]
        comps = [{"type": "body", "parameters": [{"type": "text", "text": v} for v in vals]}] if vals else None
        res = await inner.send_template(peer, node["name"], node["lang"], comps)
    except Exception:
        log.exception("flow template send bot=%s", bot_row["id"])
        res = None
    finally:
        if charged and not res:
            db.wallet_refund(owner, charged, ref=ref, note="flow template not accepted")
    if res:
        try:
            db.log_message(bot_row["id"], peer, "out", "bot", f"📄 {node['name']}", kind="text")
        except Exception:
            log.exception("could not log flow template")
    return bool(res)


def _render_body(body, data, contact):
    """جسم الطلب: JSON تُهرَّب قيمه داخل النصوص (قيمة فيها علامة تنصيص لا تكسر البنية)، وإلا نص."""
    s = body.strip()
    if s[:1] in "{[":
        out = TPL_RE.sub(lambda m: json.dumps(render("{{" + m.group(1) + "}}", data, contact),
                                              ensure_ascii=False)[1:-1], body)
        try:
            json.loads(out)
            return out, "application/json"
        except ValueError:
            pass
    return render(body, data, contact), "text/plain; charset=utf-8"


async def _api_call(bot_id, node, data, contact):
    """True = رد 2xx (والقيم المطلوبة حُفظت في المتغيّرات) · False = فشل ⇒ فرع «فشل»."""
    import flow_http
    from urllib.parse import quote
    url = TPL_RE.sub(lambda m: quote(render("{{" + m.group(1) + "}}", data, contact), safe=""), node["url"])
    headers = {h["k"]: render(h["v"], data, contact)[:500].replace("\r", "").replace("\n", "")
               for h in node.get("headers") or []}
    body = None
    if node.get("body"):
        body, ctype = _render_body(node["body"], data, contact)
        headers.setdefault("Content-Type", ctype)
    status, payload = await asyncio.to_thread(flow_http.request, node["method"], url, headers, body)
    if node.get("status_var"):
        data[node["status_var"]] = str(status or 0)
    ok = 200 <= (status or 0) < 300
    if ok:
        for m in node.get("save") or []:
            v = flow_http.pick(payload, m["path"])
            if v is not None:
                data[m["var"]] = (v if isinstance(v, str) else json.dumps(v, ensure_ascii=False))[:1000]
    else:
        log.info("flow api bot=%s status=%s", bot_id, status)
    return ok


async def _sheets_append(bot_id, node, data, peer, flow):
    """صفّ في Google Sheets عبر Web App من Apps Script (الرابط `/exec`). فشلها لا يوقف الفلو."""
    import flow_http
    keys = node.get("fields") or [k for k in data if not k.startswith("_")]
    row = {k: data.get(k, "") for k in keys}
    row.update(_phone=peer.split(":", 1)[-1], _flow=flow.get("name", ""),
               _at=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"))
    status, _ = await asyncio.to_thread(flow_http.request, "POST", node["url"], {},
                                        json.dumps(row, ensure_ascii=False), True)
    if not 200 <= (status or 0) < 300:
        log.info("flow sheets bot=%s status=%s", bot_id, status)


async def _assign(bot_row, channel, peer, cid, node, say):
    """مسؤول جهة الاتصال: عضو محدّد أو الأقل انشغالاً في فريق الحساب (يراه صندوق الوارد وجهات الاتصال)."""
    owner = bot_row["owner_id"]
    ids = [owner] + [m["id"] for m in db.team_members(owner)]
    if node.get("mode") == "team":
        # المحادثة لفريق (التالي بالتناوب يستلمها) — والبوت يكمل الفلو: الإسناد ليس تحويلاً فورياً
        who = db.route_conversation(owner, bot_row["id"], peer, node["team"])
    else:
        who = node.get("member") if node.get("mode") == "member" else db.least_loaded_assignee(owner, ids)
        if who in ids:
            db.assign_conversation(bot_row["id"], peer, who, (db.get_conversation(bot_row["id"], peer) or {}).get("team_id"),
                                   takeover=False)
    if cid and who in ids:
        db.assign_contacts(owner, [cid], who)
    if node.get("text"):
        await channel.remove_keyboard(peer, say(node["text"]))


def _wa_inner(bot_row, channel, method):
    inner = getattr(channel, "_c", channel)
    return inner if (bot_row.get("channel") or "") == "whatsapp" and hasattr(inner, method) else None


def _log_out(bot_id, peer, text):
    try:
        db.log_message(bot_id, peer, "out", "bot", text, kind="text")
    except Exception:
        log.exception("could not log flow message")


async def _send_products(bot_row, channel, peer, node, say):
    """منتج واحد أو قائمة منتجات من كتالوج Meta المربوط بالرقم. رسالة جلسة عادية (لا قالب ولا خصم)."""
    inner = _wa_inner(bot_row, channel, "send_products")
    if not inner:
        return False
    res = await inner.send_products(peer, node["catalog"], node["items"], say(node.get("header")), say(node.get("text")))
    if res:
        _log_out(bot_row["id"], peer, "🛍️ " + (say(node.get("header")) or ", ".join(node["items"][:3])))
    return bool(res)


async def _send_form(bot_row, channel, peer, node, say, token):
    """نموذج WhatsApp Flows منشور في Meta. الرد (nfm_reply) يحمل الرمز نفسه فيُطابَق عند الاستئناف."""
    inner = _wa_inner(bot_row, channel, "send_flow")
    if not inner:
        return False
    res = await inner.send_flow(peer, node["flow_id"], node["screen"], node["cta"], say(node["text"]),
                                say(node.get("header")), token)
    if res:
        _log_out(bot_row["id"], peer, f"📝 {say(node['text'])} [{node['cta']}]")
    return bool(res)


# ─────────────────────────── مهلة الرد والتذكير ───────────────────────────
def clean_timeout(t):
    """إعداد الفلو: {remind (دقائق), remind_text, end (دقائق), end_text} — 0 = معطّل.
    التذكير داخل 23 ساعة (نافذة واتساب)، والإنهاء بعده."""
    t = t or {}

    def mins(k, hi):
        try:
            return max(0, min(hi, int(t.get(k) or 0)))
        except (TypeError, ValueError):
            raise Invalid("flow:timeout")
    out = {"remind": mins("remind", REMIND_MAX), "remind_text": _s(t.get("remind_text"), 1024),
           "end": mins("end", 7 * 24 * 60), "end_text": _s(t.get("end_text"), 1024)}
    if out["remind"] and not out["remind_text"]:
        raise Invalid("flow:remind_text")
    if out["remind"] and out["end"] and out["end"] <= out["remind"]:
        raise Invalid("flow:timeout")
    return out


def _deadlines(flow):
    to = flow.get("timeout") or {}
    now = int(time.time())
    return (now + to["remind"] * 60 if to.get("remind") else None,
            now + to["end"] * 60 if to.get("end") else None)


def due_timeouts(now=None):
    """[(bot_row, session, flow, action)] — action remind|end|stale. يستدعيها bot_manager دورياً."""
    now = int(now or time.time())
    out, bots = [], {}
    for s in db.flow_sessions_due(now):
        bid = s["bot_id"]
        if bid not in bots:
            b = db.get_bot(bid)
            bots[bid] = (dict(b), json.loads(b.get("config_json") or "{}")) if b else (None, {})
        bot, cfg = bots[bid]
        flow = _find(cfg, s["flow_id"]) if bot else None
        st = db.get_chat_state(bid, s["peer"]) if bot else None
        g = (st or {}).get("data", {}).get("__g") if st and st["step"] == GRAPH_STEP else None
        if not flow or not g or g.get("s") != s["id"]:
            out.append((bot, s, flow, "stale"))          # لم تعد تنتظر هنا — يُلغى الموعدان فقط
        elif s.get("end_at") and s["end_at"] <= now:
            out.append((bot, s, flow, "end"))
        else:
            out.append((bot, s, flow, "remind"))
    return out


async def apply_timeout(bot_row, channel, s, flow, action):
    """ينفّذ التذكير أو الإنهاء لجلسة واحدة. قناة None (بوت متوقّف) = لا إرسال، والإنهاء يتمّ."""
    import flow_engine as FE
    if action == "stale" or not bot_row:
        db.flow_session_mark(s["id"], clear=True)
        return
    bot_id, peer = bot_row["id"], s["peer"]
    if FE.human_active(bot_id, peer, db.get_conversation(bot_id, peer)):
        db.flow_session_mark(s["id"], clear=True)        # صاحب النشاط يتولّى — لا رسائل آلية
        return
    st = db.get_chat_state(bot_id, peer)
    data = (st or {}).get("data") or {}
    to = flow.get("timeout") or {}
    contact, _ = _contact(bot_id, peer)
    ch = FE.LoggedChannel(channel, bot_id) if channel else None
    if action == "remind":
        db.flow_session_mark(s["id"], reminded=True)
        if ch and to.get("remind_text"):
            await ch.remove_keyboard(peer, render(to["remind_text"], data, contact))
        return
    if ch and to.get("end_text"):
        await ch.remove_keyboard(peer, render(to["end_text"], data, contact))
    _save_lead(bot_row, peer, data)
    db.clear_chat_state(bot_id, peer)
    db.flow_session_end(s["id"], "dropped", s.get("last_node"))
