"""سياسات الحساب: اسم المستخدم · كلمة المرور · الهاتف · السن · نوع الكيان.

دوال نقية بلا قاعدة بيانات — **الخادم هو الحكم**. الواجهة (`frontend/src/app/auth.jsx`) تعرض
نفس القواعد حيّاً للتوجيه فقط؛ أي تعديل هنا يُنسخ هناك. كل دالة ترجّع مفتاح خطأ (أو قائمة
مفاتيح) والنص في `MSG` بالعربية والإنجليزية — `msg(key, lang)`.

تنطبق على **الحسابات والكلمات الجديدة** فقط (تسجيل · استرجاع · تغيير من «حسابي» · إضافة من
الأدمن). الحسابات القديمة تدخل بكلماتها كما هي.
"""
import re
import secrets

# ---------------------------------------------------------------- اسم المستخدم
# نفس محارف app.USERNAME_RE (لا محارف تنسيق عربية غير مرئية — راجع التعليق هناك).
USERNAME_RE = re.compile(r"^[A-Za-z0-9_.\-ؠ-ي٠-٩ٱ-ۓ]{3,32}\Z")
_LETTER = re.compile(r"[A-Za-zؠ-يٱ-ۓ]")
_NOT_ALLOWED = re.compile(r"[^A-Za-z0-9_.\-ؠ-ي٠-٩ٱ-ۓ]")

# أسماء تنتحل المنصة أو فريقها — تُقارن بعد حذف . _ - وتصغير الحروف.
RESERVED = {"root", "system", "api", "www", "mail", "email", "info", "help", "owner", "staff",
            "team", "security", "billing", "payments", "null", "undefined", "anonymous", "bot",
            "telegram", "whatsapp", "meta", "facebook", "google", "moderator", "official"}
RESERVED_PREFIX = ("admin", "botyalla", "support", "official", "moderator")


def username_problem(u):
    """مفتاح أول قاعدة مكسورة أو None. التفرّد (u_taken) يفحصه المستدعي من القاعدة."""
    u = u or ""
    if not 3 <= len(u) <= 32:
        return "u_len"
    if not USERNAME_RE.match(u):
        return "u_chars"
    if not _LETTER.search(u):
        return "u_digits"
    if not _LETTER.match(u):
        return "u_start"
    if u[-1] in "._-":
        return "u_end"
    if re.search(r"[._-]{2}", u):
        return "u_repeat"
    key = re.sub(r"[._-]", "", u.lower())
    if key in RESERVED or key.startswith(RESERVED_PREFIX):
        return "u_reserved"
    return None


def username_base(raw):
    """اسم معروض (من جوجل/فيسبوك أو اسم مأخوذ) ⇒ أساس صالح لاقتراح اسم مستخدم."""
    s = _NOT_ALLOWED.sub("", re.sub(r"\s+", "_", (raw or "").strip()))
    s = re.sub(r"[._-]{2,}", "_", s)
    while s and not _LETTER.match(s):
        s = s[1:]
    s = s[:24].rstrip("._-")
    return s if len(s) >= 3 and not username_problem(s) else "user"


def username_candidates(base, n=6):
    """اقتراحات حول أساس: الأساس نفسه ثم أشكال بأرقام. المستدعي يستبعد المأخوذ."""
    base = username_base(base)
    out = [base]
    for suffix in ("_eg", "_biz"):
        if len(base) + len(suffix) <= 32:
            out.append(base + suffix)
    while len(out) < n:
        out.append(f"{base[:28]}{secrets.randbelow(900) + 100}")
    return [c for c in dict.fromkeys(out) if not username_problem(c)]


# ---------------------------------------------------------------- كلمة المرور
PW_MIN, PW_MAX = 8, 128
COMMON = {"12345678", "123456789", "1234567890", "password", "password1", "password123",
          "qwerty123", "qwertyuiop", "11111111", "00000000", "abc12345", "abcd1234", "iloveyou",
          "admin123", "welcome1", "p@ssw0rd", "passw0rd", "1q2w3e4r", "1qaz2wsx", "zaq12wsx",
          "qwe12345", "aa123456", "asdf1234", "asdfghjkl", "letmein1", "botyalla"}
# الكلمة بعد حذف الأرقام والرموز: «Password@123» جوهرها password — شائعة مهما زُيّنت.
_COMMON_CORE = {"password", "passwd", "pass", "qwerty", "qwertyuiop", "asdf", "asdfgh", "admin",
                "welcome", "botyalla", "iloveyou", "letmein", "abc", "abcd", "abcdef", "azerty",
                "monkey", "dragon", "football", "master", "sunshine", "princess", "test", "user"}


def password_problems(pw, username="", email=""):
    """قائمة مفاتيح القواعد المكسورة ([] = مقبولة)."""
    pw = pw or ""
    low = pw.lower()
    out = []
    if len(pw) < PW_MIN:
        out.append("p_len")
    if len(pw) > PW_MAX:
        out.append("p_long")
    if not re.search(r"[a-z]", pw):
        out.append("p_lower")
    if not re.search(r"[A-Z]", pw):
        out.append("p_upper")
    if not re.search(r"\d", pw):
        out.append("p_digit")
    if not re.search(r"[^A-Za-z0-9]", pw):
        out.append("p_symbol")
    if low in COMMON or re.sub(r"[^a-z]", "", low) in _COMMON_CORE:
        out.append("p_common")
    uname = (username or "").lower()
    local = (email or "").split("@")[0].lower()
    if (len(uname) >= 3 and uname in low) or (len(local) >= 4 and local in low):
        out.append("p_user")
    return out


# ---------------------------------------------------------------- الهاتف
# (الرمز، مفتاح الاتصال، عربي، إنجليزي) — الواجهة تعرض نفس القائمة (auth.jsx).
COUNTRIES = [("EG", "+20", "مصر", "Egypt"), ("SA", "+966", "السعودية", "Saudi Arabia"),
             ("AE", "+971", "الإمارات", "UAE"), ("KW", "+965", "الكويت", "Kuwait"),
             ("QA", "+974", "قطر", "Qatar"), ("BH", "+973", "البحرين", "Bahrain"),
             ("OM", "+968", "عُمان", "Oman"), ("JO", "+962", "الأردن", "Jordan"),
             ("LB", "+961", "لبنان", "Lebanon"), ("IQ", "+964", "العراق", "Iraq"),
             ("LY", "+218", "ليبيا", "Libya"), ("SD", "+249", "السودان", "Sudan"),
             ("MA", "+212", "المغرب", "Morocco"), ("DZ", "+213", "الجزائر", "Algeria"),
             ("TN", "+216", "تونس", "Tunisia"), ("TR", "+90", "تركيا", "Türkiye"),
             ("GB", "+44", "المملكة المتحدة", "United Kingdom"), ("DE", "+49", "ألمانيا", "Germany"),
             ("US", "+1", "أمريكا / كندا", "US / Canada")]
_CODES = {c[1] for c in COUNTRIES}
_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")


def normalize_phone(cc, number):
    """(مفتاح الدولة، الرقم كما كُتب) ⇒ صيغة دولية موحّدة «+201012345678» أو None.
    يقبل الأرقام العربية الهندية، والصفر الأول المحلي (010… ⇒ +2010…)، والرقم الدولي كاملاً.
    مصر: موبايل فقط (010 · 011 · 012 · 015) — البوت والتنبيهات تحتاج رقماً عليه تليجرام/واتساب."""
    cc = (cc or "+20").strip()
    if not cc.startswith("+"):
        cc = "+" + cc
    raw = re.sub(r"[\s\-().]", "", (number or "").translate(_DIGITS))
    if raw.startswith("+"):
        full = raw
    elif raw.startswith("00"):
        full = "+" + raw[2:]
    else:
        if cc not in _CODES:
            return None
        full = cc + raw.lstrip("0")
    if not re.fullmatch(r"\+\d{8,15}", full):
        return None
    if full.startswith("+20") and not re.fullmatch(r"\+201[0125]\d{8}", full):
        return None
    return full


def same_phone(a, b):
    """رقم تليجرام يصل بلا «+» أحياناً — المقارنة بالأرقام وحدها."""
    d = lambda s: re.sub(r"\D", "", s or "")
    return bool(d(a)) and d(a) == d(b)


def mask_phone(p):
    return (p[:4] + "•" * max(0, len(p) - 7) + p[-3:]) if p and len(p) > 7 else (p or "")


# ---------------------------------------------------------------- السن والكيان
AGE_MIN, AGE_MAX = 18, 100          # الشروط: 18 عاماً على الأقل (legal_content «الأهلية»)
ENTITIES = ("individual", "company", "institution")


def parse_age(v):
    """(السن، مفتاح خطأ)."""
    try:
        a = int(str(v or "").translate(_DIGITS).strip())
    except ValueError:
        return None, "age_bad"
    if a < AGE_MIN:
        return None, "age_min"
    if a > AGE_MAX:
        return None, "age_bad"
    return a, None


# ---------------------------------------------------------------- الرسائل
MSG = {
    "u_len":      ("اسم المستخدم من 3 إلى 32 حرفاً.", "Username must be 3–32 characters."),
    "u_chars":    ("اسم المستخدم حروف وأرقام و _ . - فقط — بلا مسافات.",
                   "Username may only use letters, digits and _ . - (no spaces)."),
    "u_digits":   ("اسم المستخدم لازم يكون فيه حروف — مش أرقام بس.", "Username can't be digits only."),
    "u_start":    ("اسم المستخدم يبدأ بحرف.", "Username must start with a letter."),
    "u_end":      ("اسم المستخدم لا ينتهي بـ . أو _ أو -.", "Username can't end with . _ or -."),
    "u_repeat":   ("لا تكرر الرموز . _ - متتالية.", "Don't repeat . _ - in a row."),
    "u_reserved": ("هذا الاسم محجوز — اختر اسماً آخر.", "That name is reserved — pick another."),
    "u_taken":    ("اسم المستخدم مستخدم بالفعل.", "That username is taken."),
    "p_len":      ("كلمة المرور 8 أحرف على الأقل.", "Password must be at least 8 characters."),
    "p_long":     ("كلمة المرور طويلة جداً (128 حداً أقصى).", "Password is too long (128 max)."),
    "p_lower":    ("أضف حرفاً إنجليزياً صغيراً (a-z).", "Add a lowercase letter (a-z)."),
    "p_upper":    ("أضف حرفاً إنجليزياً كبيراً (A-Z).", "Add an uppercase letter (A-Z)."),
    "p_digit":    ("أضف رقماً (0-9).", "Add a number (0-9)."),
    "p_symbol":   ("أضف رمزاً مثل ! @ # $ %.", "Add a symbol such as ! @ # $ %."),
    "p_common":   ("كلمة المرور شائعة وسهلة التخمين.", "That password is too common."),
    "p_user":     ("لا تضع اسم المستخدم أو بريدك داخل كلمة المرور.",
                   "Don't put your username or email in the password."),
    "p_match":    ("كلمتا المرور غير متطابقتين.", "The passwords don't match."),
    "email_req":  ("البريد الإلكتروني مطلوب.", "Email is required."),
    "email_bad":  ("صيغة البريد الإلكتروني غير صحيحة.", "That email doesn't look right."),
    "email_taken": ("هذا البريد مسجّل بحساب آخر.", "That email belongs to another account."),
    "phone_bad":  ("رقم الهاتف غير صحيح — في مصر رقم موبايل يبدأ بـ 010 أو 011 أو 012 أو 015.",
                   "That phone number isn't valid — in Egypt use a mobile starting 010/011/012/015."),
    "phone_taken": ("هذا الرقم مسجّل بحساب آخر.", "That phone number belongs to another account."),
    "age_min":    ("المنصة لمن هم 18 عاماً فأكثر.", "You must be 18 or older."),
    "age_bad":    ("اكتب سنّك بالأرقام.", "Enter your age as a number."),
    "entity_bad": ("اختر نوع الحساب: فرد أو شركة أو مؤسسة.", "Choose an account type: individual, company or institution."),
    "terms_req":  ("لازم توافق على الشروط وسياسة الخصوصية.", "Please accept the Terms and Privacy Policy."),
}


def msg(key, lang="ar"):
    pair = MSG.get(key)
    return (pair[1] if lang == "en" else pair[0]) if pair else key
