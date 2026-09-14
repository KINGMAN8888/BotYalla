"""محرك التحقق من إيصالات الدفع (طبقة الأتمتة) — الإصدار 2.

الفحص يجري **قبل** إنشاء أي طلب دفع:
1. الصورة نفسها (التوقيع والحجم) ← 2. التكرار ← 3. قراءة النص (OCR) ← 4. التحليل:
   علامات إيصال التحويل · المبلغ المطلوب · رقم/حساب المستلم (حسابك أنت).

ما ليس إيصالاً، أو إيصال لتحويل على حساب آخر أو بمبلغ آخر، أو إيصال مستخدم في
طلب قائم — **يُرفض قبل الحفظ**: لا ملف على القرص ولا طلب دفع ولا تنبيه للأدمن،
والعميل يعرف السبب فوراً. ما يمرّ يبقى **استشارياً**: التفعيل بموافقة الأدمن وحده
(AGENTS.md §3.3).

OCR = pytesseract + Pillow + برنامج tesseract (عربي وإنجليزي). لو غير متاح لا يُرفض
شيء آلياً (لا حكم بلا قراءة)، والسبب يظهر للأدمن مع طريقة الإصلاح.
"""
import hashlib
import io
import logging
import os
import re
import shutil

log = logging.getLogger("payments")

MAX_BYTES = 8 * 1024 * 1024   # 8MB
MIN_BYTES = 2 * 1024          # 2KB
ALLOWED_EXT = {".jpg", ".jpeg", ".png", ".webp"}

# بعد رفضين خلال ساعة، الإيصال «الشبيه» يمرّ للأدمن موسوماً «مشبوه» بدل الرفض —
# حتى لا يُحبس عميل حوّل فعلاً وقراءة صورته ضعيفة. الصورة التي ليست إيصالاً لا تمرّ.
RETRY_AFTER = 2

# سبب الرفض ← مفتاح رسالة العميل في i18n
REFUSAL_KEYS = {"not_receipt": "pay_rej_not_receipt", "duplicate": "pay_rej_duplicate",
                "wrong_recipient": "pay_rej_recipient", "amount_mismatch": "pay_rej_amount"}


# توقيعات ملفات الصور (magic bytes)
def _sniff_image(head: bytes):
    if head[:3] == b"\xff\xd8\xff": return "jpeg"
    if head[:8] == b"\x89PNG\r\n\x1a\n": return "png"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP": return "webp"
    return None

def file_sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()

def validate_bytes(data):
    """يفحص البايتات مباشرة — يسمح بالتحقق **قبل** أي كتابة على القرص، فلا
    يلمس ما ليس صورةً نظامَ الملفات أصلاً. الامتداد المُعلَن لا يصنع نوعاً:
    البايتات الأولى هي الحكم."""
    size = len(data)
    if size < MIN_BYTES:
        return {"ok": False, "reason": "too_small", "bytes": size}
    if size > MAX_BYTES:
        return {"ok": False, "reason": "too_large", "bytes": size}
    kind = _sniff_image(data[:16])
    if not kind:
        return {"ok": False, "reason": "not_an_image", "bytes": size}
    return {"ok": True, "kind": kind, "bytes": size}

def validate_image(path):
    try:
        with open(path, "rb") as f:
            data = f.read(MAX_BYTES + 1)
    except OSError:
        return {"ok": False, "reason": "file_missing"}
    return validate_bytes(data)


# ------------------------------------------------------------------ القراءة (OCR)
# خدمة systemd قد تحصر PATH في venv وحده فلا يُرى /usr/bin/tesseract — نبحث بأنفسنا.
_TESS_PATHS = ("/usr/bin/tesseract", "/usr/local/bin/tesseract",
               r"C:\Program Files\Tesseract-OCR\tesseract.exe")
_OCR = None

def ocr_status(refresh=False):
    """{'ok', 'reason', 'langs'} — يُفحص مرة لكل عملية.
    reason عند ok=False: disabled · no_module · no_binary · no_lang.
    وعند ok=True قد تكون no_ara (الإنجليزية وحدها — الكلمات العربية لن تُقرأ)."""
    global _OCR
    if _OCR is None or refresh:
        _OCR = _probe()
    return dict(_OCR)

def _probe():
    if os.getenv("BOTYALLA_OCR", "1").strip() == "0":
        return {"ok": False, "reason": "disabled", "langs": ""}
    try:
        import pytesseract
        from PIL import Image  # noqa: F401
    except Exception:
        return {"ok": False, "reason": "no_module", "langs": ""}
    cmd = shutil.which("tesseract") or next((p for p in _TESS_PATHS if os.path.isfile(p)), None)
    if not cmd:
        return {"ok": False, "reason": "no_binary", "langs": ""}
    pytesseract.pytesseract.tesseract_cmd = cmd
    try:
        have = set(pytesseract.get_languages(config=""))
    except Exception:
        log.exception("tesseract found at %s but did not run", cmd)
        return {"ok": False, "reason": "no_binary", "langs": ""}
    use = [lang for lang in ("ara", "eng") if lang in have]
    if not use:
        return {"ok": False, "reason": "no_lang", "langs": ""}
    return {"ok": True, "reason": None if "ara" in use else "no_ara", "langs": "+".join(use)}

import threading

# قراءتان متزامنتان على الأكثر. gunicorn يشغّل 4 خيوط فقط وحلقة بوتات العملاء في العملية
# نفسها: أربعة إيصالات معاً كانت تشغل الخيوط كلها فيتجمّد الموقع. من لا يجد مكاناً خلال
# OCR_WAIT لا يُرفض — يرجع None فيذهب إيصاله للمراجعة اليدوية كما لو OCR غير متاح.
_OCR_SLOTS = threading.BoundedSemaphore(2)
OCR_WAIT, OCR_TIMEOUT = 8, 10          # لقطة موبايل تُقرأ في أقل من 3 ثوانٍ

# إيصالات عملاء البوتات (إضافة «تحصيل المدفوعات») — في مجلد رفع إيصالات المنصة نفسه
import time as _time
UPLOAD_DIR = os.environ.get("BOTYALLA_UPLOADS",
                            os.path.join(os.path.dirname(os.path.abspath(__file__)), "uploads"))
_EXT = {"jpeg": ".jpg", "png": ".png", "webp": ".webp"}

def save_receipt(data, prefix):
    """يكتب إيصالاً اجتاز الفحص ويرجّع اسم ملفه (مولَّد داخلياً — لا اسم من المستخدم)."""
    kind = validate_bytes(data).get("kind") or "jpeg"
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    fname = f"{prefix}_{int(_time.time())}_{os.urandom(3).hex()}{_EXT.get(kind, '.jpg')}"
    with open(os.path.join(UPLOAD_DIR, fname), "wb") as f:
        f.write(data)
    return fname

def read_text(data):
    """نص الصورة بعد تجهيزها للقراءة، أو None لو OCR غير متاح أو فشل أو مشغول."""
    st = ocr_status()
    if not st["ok"]:
        return None
    if not _OCR_SLOTS.acquire(timeout=OCR_WAIT):
        log.warning("receipt OCR busy — this receipt goes to manual review")
        return None
    try:
        import pytesseract
        from PIL import Image, ImageOps, ImageStat
        Image.MAX_IMAGE_PIXELS = 40_000_000        # لقطة موبايل ≈ 3M — أكبر من هذا قنبلة ضغط
        g = ImageOps.exif_transpose(Image.open(io.BytesIO(data))).convert("L")
        w = g.width
        # القراءة أدق حول 1400px: اللقطات الصغيرة تُكبَّر والضخمة تُصغَّر (سرعة)
        f = 1400 / w if w < 1000 else (2000 / w if w > 2400 else 1)
        if f != 1:
            g = g.resize((max(1, int(w * f)), max(1, int(g.height * f))), Image.LANCZOS)
        if ImageStat.Stat(g).mean[0] < 110:          # الوضع الليلي: نص فاتح على خلفية داكنة
            g = ImageOps.invert(g)
        g = ImageOps.autocontrast(g)
        return pytesseract.image_to_string(g, lang=st["langs"], timeout=OCR_TIMEOUT) or ""
    except Exception:
        log.warning("receipt OCR failed", exc_info=True)
        return None
    finally:
        _OCR_SLOTS.release()


# ------------------------------------------------------------------ التحليل
_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹٫٬", "01234567890123456789.,")
_AR_NORM = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ة": "ه", "ى": "ي", "ـ": None})
_TASHKEEL = re.compile(r"[\u064B-\u0652\u0670]")

def norm(text):
    """أرقام عربية/فارسية ← لاتينية، توحيد الهمزات والتاء المربوطة، بلا تشكيل، أحرف صغيرة."""
    return _TASHKEEL.sub("", (text or "").translate(_DIGITS).translate(_AR_NORM).lower())

# علامات إيصال التحويل — مجموعات لا كلمات: «تحويل» و«حولت» علامة واحدة.
# الكلمات بالصيغة المطبَّعة (ا بدل أ/إ، ه بدل ة).
_SIGNALS = {
    "transfer": ("تحويل", "حولت", "ارسال", "transfer", "sent", "send money"),
    "success":  ("بنجاح", "ناجح", "تمت", "success", "successful", "completed", "done"),
    "amount":   ("المبلغ", "مبلغ", "الاجمالي", "amount", "total"),
    "currency": ("جنيه", "ج.م", "egp"),
    "ref":      ("رقم العمليه", "العمليه", "المرجع", "مرجع", "reference", "transaction", "txn", "ref"),
    "provider": ("فودافون", "كاش", "انستاباي", "انستا باي", "محفظه", "بنك",
                 "instapay", "vodafone", "wallet", "bank", "ipn"),
    "party":    ("المستلم", "مستلم", "المستفيد", "المرسل", "receiver", "recipient", "beneficiary"),
    "fees":     ("رسوم", "الرصيد", "fees", "fee", "balance"),
}
_SHORT = re.compile(r"^[a-z.]{1,4}$")     # كلمة لاتينية قصيرة تُطابَق ككلمة كاملة لا كجزء
_DATE = re.compile(r"(?<!\d)\d{1,2}[:/\-.]\d{1,2}(?:[:/\-.]\d{2,4})?(?!\d)")
_MASK = re.compile(r"(\d{2,6})\s*[*xX•●·#]{2,}\s*(\d{2,4})(?!\d)")

def _signals(t):
    words = set(re.findall(r"[a-z][a-z.]*|[\u0600-\u06ff]+", t))
    hit = set()
    for group, keys in _SIGNALS.items():
        if any((k in words) if _SHORT.match(k) else (k in t) for k in keys):
            hit.add(group)
    if _DATE.search(t):
        hit.add("date")
    return hit

def _amounts(t):
    """كل المبالغ الظاهرة. أرقام الموبايل والمراجع (أكثر من 7 أرقام) لا تُحسب مبالغ."""
    s = re.sub(r"(?<=\d),(?=\d{3}(?!\d))", "", t)          # 1,500 ← 1500
    s = re.sub(r"(?<=\d),(?=\d{1,2}(?!\d))", ".", s)       # 299,00 ← 299.00
    out = set()
    for m in re.finditer(r"(?<![\d.])\d{1,7}(?:\.\d{1,2})?(?!\d)", s):
        out.add(round(float(m.group(0)), 2))
    return out

def _ref_hit(ref, t):
    """'full' | 'masked' | None — هل يظهر حساب المنصة هذا في نص الإيصال؟"""
    r = norm(ref).strip()
    if not r:
        return None
    dg = re.sub(r"\D", "", r)
    letters = re.sub(r"[\d\W_]", "", r)
    if len(dg) >= 8 and len(letters) <= 4:              # موبايل · رقم حساب · IBAN
        stream = re.sub(r"(?<=\d)[\s\-–_.]+(?=\d)", "", t)
        if dg[-10:] in stream:
            return "full"
        variants = {dg, "0" + dg[-10:], "20" + dg[-10:]}
        for m in _MASK.finditer(t):                     # انستاباي يخفي المنتصف: 010****951
            pre, suf = m.group(1), m.group(2)
            if len(pre) + len(suf) >= 4 and any(v.startswith(pre) and v.endswith(suf) for v in variants):
                return "masked"
        return None
    flat = re.sub(r"\s+", "", t)
    if "@" in r or (letters and " " not in r):          # عنوان انستاباي
        h = r.replace(" ", "")
        local = h.split("@")[0]
        return "full" if (h in flat or (len(local) >= 4 and local in flat)) else None
    words = [w for w in r.split() if len(w) >= 3][:2]   # اسم صاحب الحساب
    return "full" if words and all(w in t for w in words) else None

def analyze(text, expected_amount, refs):
    """تحليل نص الإيصال — دالة نقية (بلا OCR) فتُختبر بنص جاهز."""
    t = norm(text)
    chars = len(re.findall(r"[0-9a-z\u0600-\u06ff]", t))
    sig = _signals(t)
    amount_found = expected_amount is not None and any(
        abs(a - float(expected_amount)) < 0.01 for a in _amounts(t))
    refs = [r for r in (refs or []) if r and str(r).strip()]
    if not refs:
        recipient = "n/a"
    else:
        hits = {_ref_hit(str(r), t) for r in refs}
        recipient = "full" if "full" in hits else ("masked" if "masked" in hits else "none")
    receipt = len(sig) >= 2 or (amount_found and recipient in ("full", "masked"))
    return {"ocr": True, "chars": chars, "signals": sorted(sig), "amount_found": amount_found,
            "recipient": recipient, "receipt": receipt}

def auto_check(src, expected_amount, expected_refs, duplicate, prior_refusals=0):
    """يجمع الفحوصات ويحكم. src = بايتات الصورة (المسار الحالي) أو مسار ملف.

    verdict: auto_pass (مؤشر قوي — يبقى بموافقة الأدمن) · needs_review (OCR غير متاح)
    · suspect (مرّ بعد رفضين، أو صورة غير صالحة) · reject مع refuse=True (لا يُنشأ طلب)."""
    if isinstance(src, (bytes, bytearray)):
        data = bytes(src)
        img = validate_bytes(data)
    else:
        img, data = validate_image(src), None
        if img.get("ok"):
            try:
                with open(src, "rb") as f:
                    data = f.read(MAX_BYTES + 1)
            except OSError:
                data = None
    res = {"engine": 2, "image": img, "duplicate": bool(duplicate), "ocr": None, "refuse": False}
    if not img.get("ok"):
        return dict(res, verdict="suspect", reason=f"image:{img.get('reason')}")
    if duplicate:
        return dict(res, verdict="reject", reason="duplicate", refuse=True)
    text = read_text(data) if data is not None else None
    if text is None:
        st = ocr_status()
        return dict(res, verdict="needs_review", reason="ocr_off",
                    ocr_off=(st["reason"] if not st["ok"] else "error"))
    a = analyze(text, expected_amount, expected_refs)
    res["ocr"] = a
    if a["chars"] < 25 or not a["receipt"]:
        reason = "not_receipt"
    elif a["recipient"] == "none":
        reason = "wrong_recipient"
    elif not a["amount_found"]:
        reason = "amount_mismatch"
    else:
        return dict(res, verdict="auto_pass", reason=None)
    escapable = (reason in ("wrong_recipient", "amount_mismatch")
                 or (reason == "not_receipt" and a["chars"] >= 25 and a["amount_found"]))
    if escapable and prior_refusals >= RETRY_AFTER:
        return dict(res, verdict="suspect", reason=reason, retries=int(prior_refusals))
    return dict(res, verdict="reject", reason=reason, refuse=True)


# ------------------------------------------------------------------ العرض للأدمن
_OCR_OFF = {
    "disabled":  ("قراءة الإيصالات (OCR) متوقفة بالإعداد BOTYALLA_OCR=0 — راجع الصورة يدوياً",
                  "Receipt reading (OCR) disabled by BOTYALLA_OCR=0 — review manually"),
    "no_module": ("مكتبة قراءة الإيصالات مش متثبّتة على السيرفر — راجع الصورة يدوياً",
                  "OCR library not installed on the server — review manually"),
    "no_binary": ("برنامج tesseract مش متاح للخدمة على السيرفر — راجع الصورة يدوياً",
                  "tesseract isn't available to the service — review manually"),
    "no_lang":   ("لغات القراءة مش متثبّتة (tesseract-ocr-ara) — راجع الصورة يدوياً",
                  "OCR languages missing (tesseract-ocr-ara) — review manually"),
    "error":     ("تعذّرت قراءة الصورة — راجعها يدوياً", "Couldn't read the image — review manually"),
    "unknown":   ("فحص المبلغ (OCR) غير متاح على هذا الجهاز — راجع الصورة يدوياً",
                  "Amount check (OCR) unavailable on this machine — review the image manually"),
}

def check_lines(auto: dict, lang="ar"):
    """يحوّل نتيجة الفحص الآلي إلى بنود مقروءة للأدمن: [{ok, text}].
    يقرأ سجلات المحرك 1 القديمة (amount_found/ref_found) والمحرك 2 معاً."""
    ar = lang != "en"
    L = lambda a, e: a if ar else e                     # noqa: E731
    auto = auto or {}
    lines = []
    img = auto.get("image") or {}
    if img.get("ok"):
        lines.append({"ok": True, "text": L("صورة صحيحة", "Valid image") + f" ({img.get('kind', '')})"})
    else:
        lines.append({"ok": False, "text": L("صورة غير صالحة", "Invalid image") + f" — {img.get('reason', '')}"})
    if auto.get("duplicate"):
        lines.append({"ok": False, "text": L("إيصال مكرر (مستخدم في طلب تاني)",
                                             "Duplicate receipt (used in another request)")})
    else:
        lines.append({"ok": True, "text": L("غير مكرر", "Not a duplicate")})
    ocr = auto.get("ocr")
    if ocr is None:
        lines.append({"ok": None, "text": L(*_OCR_OFF.get(auto.get("ocr_off"), _OCR_OFF["unknown"]))})
    elif "recipient" in ocr:
        n = len(ocr.get("signals") or [])
        lines.append({"ok": True, "text": L(f"شكل إيصال تحويل ({n} علامات)",
                                            f"Looks like a transfer receipt ({n} signs)")}
                     if ocr.get("receipt") else
                     {"ok": False, "text": L("مش شبه إيصال تحويل", "Doesn't look like a transfer receipt")})
        lines.append({"ok": True, "text": L("المبلغ مطابق", "Amount matches")} if ocr.get("amount_found")
                     else {"ok": False, "text": L("المبلغ المطلوب مش ظاهر في الإيصال",
                                                  "Required amount isn't on the receipt")})
        lines.append({
            "full":   {"ok": True, "text": L("التحويل على رقمك/حسابك", "Sent to your number/account")},
            "masked": {"ok": True, "text": L("رقم المستلم مطابق (مخفي جزئياً)", "Recipient matches (partly masked)")},
            "none":   {"ok": False, "text": L("المستلم مش رقمك ولا حسابك", "Recipient isn't your number/account")},
        }.get(ocr.get("recipient"), {"ok": None, "text": L("مفيش وسائل دفع في إعدادات المنصة للمقارنة",
                                                            "No payment details in platform settings to compare")}))
    else:
        af = ocr.get("amount_found")
        if af is True:
            lines.append({"ok": True, "text": L("المبلغ ظاهر في الإيصال", "Amount found in receipt")})
        elif af is False:
            lines.append({"ok": False, "text": L("المبلغ غير ظاهر في الإيصال", "Amount NOT found in receipt")})
        rf = ocr.get("ref_found")
        if rf is True:
            lines.append({"ok": True, "text": L("رقم الاستلام/المُستلِم ظاهر", "Recipient/ref found")})
        elif rf is False:
            lines.append({"ok": False, "text": L("رقم الاستلام/المُستلِم غير ظاهر في الإيصال",
                                                 "Recipient/ref NOT found in receipt")})
    if auto.get("retries"):
        lines.append({"ok": False, "text": L(f"اترفض آلياً {auto['retries']} مرات خلال ساعة قبل ما يعدّي — راجعه بعناية",
                                             f"Auto-refused {auto['retries']} times in the hour before — review carefully")})
    return lines

VERDICT_STYLE = {
    "auto_pass":    ("on",  "✓"),
    "needs_review": ("mid", "؟"),
    "suspect":      ("off", "⚠"),
    "reject":       ("off", "⛔"),
}

def verdict_label(v, lang="ar"):
    m = {
        "auto_pass":   ("✅ الفحص الآلي: مبدئياً سليم", "✅ Auto-check: looks valid"),
        "needs_review":("🕵️ الفحص الآلي: بحاجة لمراجعتك", "🕵️ Auto-check: needs your review"),
        "suspect":     ("⚠️ الفحص الآلي: مشبوه — راجع بعناية", "⚠️ Auto-check: suspicious — review carefully"),
        "reject":      ("⛔ الفحص الآلي: مرفوض", "⛔ Auto-check: refused"),
    }
    pair = m.get(v, ("—", "—"))
    return pair[0] if lang == "ar" else pair[1]
