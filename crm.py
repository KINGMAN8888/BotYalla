"""جهات الاتصال (CRM) — المنطق النقي: أنواع الحقول، تطبيع القيم، قواعد الشرائح، قراءة الملفات.

لا SQL هنا (كل SQL في database.py) ولا Flask — دوال تُختبر بمدخلات جاهزة.
المرحلة 1 من docs/ENTERPRISE_PLAN.md · قائمة القبول في docs/COMPETITOR_PARITY.md §1.
"""
import csv
import io
import json
import re
import time
from datetime import datetime, timedelta, timezone

import accounts as ACC

# ─────────────────────────── الحقول المخصّصة ───────────────────────────
FIELD_TYPES = ("text", "multi_text", "number", "select", "multi_select", "date", "switch", "user")
ENTITIES = ("contact", "company")
KEY_RE = re.compile(r"^[a-z][a-z0-9_]{0,39}$")
MAX_FIELDS = 100          # لكل كيان في الحساب
MAX_OPTIONS = 100
MAX_TEXT = 1000
SOURCES = ("chat", "manual", "import", "api")

# فروق التوقيت: السعودية ومصر (صيفاً) +3 — حدود «اليوم» في قواعد التاريخ تُحسب بها.
TZ = timezone(timedelta(hours=3))


def make_key(label):
    """مفتاح المتغيّر من الاسم الظاهر: «Lead Stage» ⇒ lead_stage. العربي بلا مقابل ⇒ field_<n>."""
    k = re.sub(r"[^a-z0-9]+", "_", (label or "").lower()).strip("_")
    if not k or not k[0].isalpha():
        k = "field_" + (k or str(int(time.time()) % 100000))
    return k[:40]


def clean_field_def(d):
    """تعريف حقل من النموذج ⇒ (dict نظيف, None) أو (None, رمز الخطأ)."""
    label = (d.get("label") or "").strip()[:60]
    if not label:
        return None, "label"
    ftype = d.get("type")
    if ftype not in FIELD_TYPES:
        return None, "type"
    key = (d.get("key") or make_key(label)).strip().lower()
    if not KEY_RE.match(key):
        return None, "key"
    opts = []
    if ftype in ("select", "multi_select"):
        seen = set()
        for o in d.get("options") or []:
            o = str(o).strip()[:80]
            if o and o.lower() not in seen:
                seen.add(o.lower()); opts.append(o)
        if not opts:
            return None, "options"
        opts = opts[:MAX_OPTIONS]
    return {"label": label, "key": key, "type": ftype, "options": opts,
            "active": 1 if d.get("active", True) else 0,
            "required": 1 if d.get("required") else 0}, None


def _as_list(v):
    if v is None or v == "":
        return []
    if isinstance(v, (list, tuple)):
        return list(v)
    return [x.strip() for x in str(v).replace("؛", ",").replace(";", ",").split(",")]


def clean_value(fdef, v, users=()):
    """قيمة حقل مخصّص ⇒ (القيمة المخزّنة, None) أو (None, رمز الخطأ). None/"" = فارغ.
    `users`: معرّفات أعضاء الحساب المسموح إسنادهم لحقل «User»."""
    t = fdef["type"]
    if v is None or v == "" or v == []:
        return None, ("required" if fdef.get("required") else None)
    if t == "text":
        return str(v).strip()[:MAX_TEXT], None
    if t == "multi_text":
        vals = [str(x).strip()[:MAX_TEXT] for x in _as_list(v) if str(x).strip()]
        return (vals[:50] or None), None
    if t == "number":
        try:
            n = float(str(v).replace(",", "").translate(ACC._DIGITS))
        except ValueError:
            return None, "number"
        if n != n or abs(n) > 1e15:                   # NaN / قيم غير معقولة
            return None, "number"
        return (int(n) if n.is_integer() else n), None
    if t == "switch":
        s = str(v).strip().lower()
        if s in ("1", "true", "yes", "y", "on", "نعم", "✓"):
            return True, None
        if s in ("0", "false", "no", "n", "off", "لا"):
            return False, None
        return None, "switch"
    if t == "date":
        d = parse_date(v)
        return (d, None) if d else (None, "date")
    if t == "select":
        m = {o.lower(): o for o in fdef.get("options") or []}
        o = m.get(str(v).strip().lower())
        return (o, None) if o else (None, "option")
    if t == "multi_select":
        m = {o.lower(): o for o in fdef.get("options") or []}
        out = []
        for x in _as_list(v):
            o = m.get(str(x).strip().lower())
            if o is None:
                return None, "option"
            if o not in out:
                out.append(o)
        return (out or None), None
    if t == "user":
        try:
            u = int(v)
        except (TypeError, ValueError):
            return None, "user"
        return (u, None) if u in users else (None, "user")
    return None, "type"


def parse_date(v):
    """«2026-09-26» · «26/09/2026» · «26-09-2026» ⇒ «2026-09-26» أو None."""
    s = str(v).strip().translate(ACC._DIGITS)[:10]
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except ValueError:
            pass
    return None


# ─────────────────────────── الهاتف والبريد ───────────────────────────
EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,255}\.[^@\s]{2,}$")


def norm_phone(raw, default_cc="+966"):
    """رقم كما كُتب في ملف أو نموذج ⇒ «+9665…» أو None.
    أوسع من `accounts.normalize_phone` (التي تقصر مصر على الموبايل للتسجيل): جهة الاتصال
    قد تكون من أي بلد، وعمود ملف مستورد يأتي غالباً بمفتاح الدولة بلا «+»."""
    s = re.sub(r"[\s\-().]", "", str(raw or "").translate(ACC._DIGITS))
    if not s:
        return None
    if s.startswith("+"):
        full = s
    elif s.startswith("00"):
        full = "+" + s[2:]
    elif s.startswith("0"):
        full = (default_cc or "+966") + s[1:]
    elif len(s) >= 11:                  # 9665… — مفتاح الدولة بلا «+»
        full = "+" + s
    else:
        full = (default_cc or "+966") + s
    return full if re.fullmatch(r"\+[1-9]\d{7,14}", full) else None


def norm_email(v):
    v = (v or "").strip().lower()
    return v if v and EMAIL_RE.match(v) and len(v) <= 254 else None


def truthy(v):
    return str(v or "").strip().lower() in ("1", "true", "yes", "y", "on", "opted in", "optin", "نعم", "✓")


def falsy(v):
    return str(v or "").strip().lower() in ("0", "false", "no", "n", "off", "opted out", "لا")


# ─────────────────────────── قواعد الشرائح (Segments) ───────────────────────────
# الحقول القياسية ونوعها. الشروط مربوطة بـ AND (كالمنافس) — مصفوفة شروط لا شجرة.
SYSTEM_FIELDS = {
    "name": "text", "phone": "text", "email": "text", "optin": "switch", "tags": "tags",
    "created_at": "ts", "updated_at": "ts", "last_seen_at": "ts",
    "assignee": "user", "company": "company", "source": "source",
}
OPS = {
    "text":         ("is", "is_not", "contains", "not_contains", "starts_with", "empty", "not_empty"),
    "multi_text":   ("contains", "not_contains", "empty", "not_empty"),
    "number":       ("eq", "neq", "gt", "lt", "empty", "not_empty"),
    "switch":       ("is",),
    "date":         ("on", "before", "after", "last_days", "empty", "not_empty"),
    "ts":           ("on", "before", "after", "last_days", "empty", "not_empty"),
    "select":       ("is", "is_not", "any_of", "empty", "not_empty"),
    "multi_select": ("has_any", "has_all", "has_none", "empty", "not_empty"),
    "user":         ("is", "is_not", "empty", "not_empty"),
    "tags":         ("has_any", "has_all", "has_none"),
    "company":      ("is", "empty", "not_empty"),
    "source":       ("is", "is_not"),
}
NO_VALUE = ("empty", "not_empty")
MAX_RULES = 20


def clean_rules(rules, fields):
    """قواعد من المتصفح ⇒ (قائمة نظيفة, None) أو (None, رمز الخطأ).
    `fields`: {key: fdef} للحقول المخصّصة النشطة في الحساب. أي حقل أو عامل غير معروف يُرفض —
    database.segment_where يبني SQL من هذه القائمة وحدها."""
    if not isinstance(rules, list) or len(rules) > MAX_RULES:
        return None, "rules"
    out = []
    for r in rules:
        if not isinstance(r, dict):
            return None, "rules"
        f, op, v = r.get("field"), r.get("op"), r.get("value")
        if isinstance(f, str) and f.startswith("f:"):
            fd = fields.get(f[2:])
            if not fd:
                return None, "field"
            kind = fd["type"]
        elif f in SYSTEM_FIELDS:
            kind = SYSTEM_FIELDS[f]
        else:
            return None, "field"
        if op not in OPS[kind]:
            return None, "op"
        if op in NO_VALUE:
            v = None
        elif op == "last_days":
            try:
                v = max(0, min(3650, int(v)))
            except (TypeError, ValueError):
                return None, "value"
        elif kind in ("date", "ts"):
            v = parse_date(v)
            if not v:
                return None, "value"
        elif kind == "switch":
            v = bool(v) if isinstance(v, bool) else truthy(v)
        elif kind == "number":
            try:
                v = float(v)
            except (TypeError, ValueError):
                return None, "value"
        elif kind in ("tags", "multi_select") or op == "any_of":
            vals = v if isinstance(v, list) else _as_list(v)
            if kind == "tags":
                try:
                    vals = [int(x) for x in vals]
                except (TypeError, ValueError):
                    return None, "value"
            else:
                vals = [str(x)[:80] for x in vals if str(x).strip()]
            if not vals or len(vals) > 100:
                return None, "value"
            v = vals
        elif kind in ("user", "company"):
            try:
                v = int(v)
            except (TypeError, ValueError):
                return None, "value"
        else:
            v = str(v if v is not None else "").strip()[:200]
            if not v:
                return None, "value"
        out.append({"field": f, "op": op, "value": v})
    return out, None


def day_bounds(d):
    """«YYYY-MM-DD» ⇒ (بداية اليوم, بداية اليوم التالي) بتوقيت TZ كـ epoch."""
    start = datetime.strptime(d, "%Y-%m-%d").replace(tzinfo=TZ)
    return int(start.timestamp()), int((start + timedelta(days=1)).timestamp())


def today():
    return datetime.now(TZ).strftime("%Y-%m-%d")


# ─────────────────────────── الاستيراد ───────────────────────────
MAX_IMPORT_ROWS = 20000
MAX_IMPORT_BYTES = 8 * 1024 * 1024
STD_TARGETS = ("name", "phone", "email", "tags", "optin", "company")

# تخمين الربط من عنوان العمود — يوفّر على المستخدم تعبئة الشاشة يدوياً لملف مصدَّر من منصة أخرى
_GUESS = [
    ("phone", ("phone", "mobile", "whatsapp", "number", "جوال", "هاتف", "رقم", "موبايل")),
    ("email", ("email", "e-mail", "mail", "بريد", "ايميل", "إيميل")),
    ("name", ("name", "full name", "contact", "الاسم", "اسم")),
    ("tags", ("tags", "tag", "labels", "وسوم", "تاغ", "تصنيف")),
    ("optin", ("optin", "opt-in", "opt in", "marketing", "messageoptin", "موافقة")),
    ("company", ("company", "organization", "شركة", "الشركة")),
]


def guess_target(header, fields):
    h = (header or "").strip().lower()
    for f in fields.values():
        if h in (f["key"], f["label"].lower()):
            return "f:" + f["key"]
    for target, words in _GUESS:
        if any(h == w or h.replace("_", " ") == w for w in words):
            return target
    for target, words in _GUESS:
        if any(w in h for w in words if len(w) > 3):
            return target
    return "skip"


def read_table(data, filename):
    """بايتات CSV/XLSX ⇒ (العناوين, الصفوف) أو يرمي ValueError برمز مفهوم."""
    if len(data) > MAX_IMPORT_BYTES:
        raise ValueError("too_big")
    name = (filename or "").lower()
    if name.endswith(".xlsx") or data[:2] == b"PK":
        rows = _read_xlsx(data)
    else:
        rows = _read_csv(data)
    rows = [[("" if c is None else str(c)).strip() for c in r] for r in rows]
    rows = [r for r in rows if any(r)]
    if not rows:
        raise ValueError("empty")
    head, body = rows[0], rows[1:]
    if len(body) > MAX_IMPORT_ROWS:
        raise ValueError("too_many")
    width = len(head)
    body = [(r + [""] * width)[:width] for r in body]
    return head, body


def _read_csv(data):
    for enc in ("utf-8-sig", "cp1256", "latin-1"):
        try:
            text = data.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    return list(csv.reader(io.StringIO(text), dialect))


def _read_xlsx(data):
    try:
        import openpyxl
    except ImportError:
        raise ValueError("xlsx_unavailable")
    try:
        wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    except Exception:
        raise ValueError("bad_file")
    ws = wb.worksheets[0]
    out = []
    for i, r in enumerate(ws.iter_rows(values_only=True)):
        if i > MAX_IMPORT_ROWS + 1:
            raise ValueError("too_many")
        out.append([_xl(c) for c in r])
    wb.close()
    return out


def _xl(c):
    if isinstance(c, datetime):
        return c.strftime("%Y-%m-%d")
    if isinstance(c, float) and c.is_integer():
        return str(int(c))                         # رقم هاتف مخزّن كرقم: 966501234567.0
    return c


def build_records(head, body, mapping, fields, default_cc, users=()):
    """الصفوف + الربط ⇒ (سجلات جاهزة, أخطاء [(رقم الصف, السبب)]).
    `mapping`: {رقم العمود: الهدف} حيث الهدف ∈ STD_TARGETS أو «f:<key>» أو «skip»."""
    cols = {}
    for i, target in (mapping or {}).items():
        i = int(i)
        if not 0 <= i < len(head) or target == "skip":
            continue
        if target in STD_TARGETS or (target.startswith("f:") and target[2:] in fields):
            cols[i] = target
    if "phone" not in cols.values():
        raise ValueError("no_phone")
    recs, errs = [], []
    for n, r in enumerate(body, start=2):          # رقم الصف كما يراه المستخدم في Excel
        rec = {"fields": {}, "tags": []}
        bad = None
        for i, target in cols.items():
            v = r[i]
            if target == "phone":
                rec["phone"] = norm_phone(v, default_cc)
                if not rec["phone"]:
                    bad = "phone"
            elif target == "email":
                rec["email"] = norm_email(v) if v else None
            elif target == "name":
                rec["name"] = v[:120]
            elif target == "tags":
                rec["tags"] = [x[:50] for x in _as_list(v) if x][:20]
            elif target == "optin":
                rec["optin"] = 1 if truthy(v) else (0 if falsy(v) else None)
            elif target == "company":
                rec["company"] = v[:120] or None
            else:
                fd = fields[target[2:]]
                val, err = clean_value(dict(fd, required=0), v, users)
                if err:
                    bad = bad or f"{fd['key']}:{err}"
                elif val is not None:
                    rec["fields"][fd["key"]] = val
        if bad:
            errs.append((n, bad))
        else:
            recs.append(rec)
    return recs, errs


def dumps(v):
    return json.dumps(v, ensure_ascii=False, separators=(",", ":"))
