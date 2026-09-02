"""محرك التحقق من مدفوعات الاشتراك (طبقة الأتمتة).
لا يعتمد على أي مكتبة خارجية إلزامية — يستخدم stdlib فقط.
OCR (pytesseract) اختياري: لو متاح يفحص المبلغ والمُستلِم، وإلا يتجاوزه بأمان.
المبدأ: الفحص الآلي *استشاري* فقط — التفعيل النهائي يتم بموافقة الأدمن على تليجرام."""
import os, json, hashlib

MAX_BYTES = 8 * 1024 * 1024   # 8MB
MIN_BYTES = 2 * 1024          # 2KB
ALLOWED_EXT = {".jpg", ".jpeg", ".png", ".webp"}

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

def validate_image(path):
    try:
        size = os.path.getsize(path)
    except OSError:
        return {"ok": False, "reason": "file_missing"}
    if size < MIN_BYTES:
        return {"ok": False, "reason": "too_small", "bytes": size}
    if size > MAX_BYTES:
        return {"ok": False, "reason": "too_large", "bytes": size}
    with open(path, "rb") as f:
        head = f.read(16)
    kind = _sniff_image(head)
    if not kind:
        return {"ok": False, "reason": "not_an_image", "bytes": size}
    return {"ok": True, "kind": kind, "bytes": size}

def try_ocr(path, expected_amount=None, expected_refs=None):
    """يرجّع None لو OCR غير متاح، أو dict بنتائج الفحص."""
    try:
        import pytesseract           # noqa
        from PIL import Image        # noqa
    except Exception:
        return None
    try:
        text = pytesseract.image_to_string(Image.open(path), lang="eng+ara")
    except Exception:
        return None
    low = text.lower().replace(",", "")
    amount_found = None
    if expected_amount is not None:
        # نبحث عن الرقم (مع أو بدون كسور)
        for token in (str(int(expected_amount)), f"{expected_amount:.2f}"):
            if token in low:
                amount_found = True; break
        if amount_found is None:
            amount_found = False
    ref_found = None
    if expected_refs:
        ref_found = any(r and r.lower() in low for r in expected_refs)
    return {"ocr": True, "amount_found": amount_found, "ref_found": ref_found,
            "text_len": len(text)}

def auto_check(path, expected_amount, expected_refs, duplicate: bool):
    """يجمع كل الفحوصات ويعطي verdict استشاري."""
    img = validate_image(path)
    result = {"image": img, "duplicate": duplicate, "ocr": None}
    if not img["ok"]:
        result["verdict"] = "suspect"
        result["reason"] = f"image:{img.get('reason')}"
        return result
    if duplicate:
        result["verdict"] = "suspect"
        result["reason"] = "duplicate_screenshot"
        return result
    ocr = try_ocr(path, expected_amount, expected_refs)
    result["ocr"] = ocr
    if ocr and ocr.get("amount_found") and (ocr.get("ref_found") in (True, None)):
        result["verdict"] = "auto_pass"      # مؤشر قوي — لكن يبقى بحاجة لموافقة الأدمن
    elif ocr and (ocr.get("amount_found") is False):
        result["verdict"] = "suspect"
        result["reason"] = "amount_not_found_in_screenshot"
    else:
        result["verdict"] = "needs_review"   # صورة سليمة وغير مكرّرة، بانتظار مراجعة الأدمن
    return result


def check_lines(auto: dict, lang="ar"):
    """يحوّل نتيجة الفحص الآلي إلى قائمة بنود مقروءة للأدمن: [{ok, text}]."""
    lines = []
    AR = lang != "en"
    img = (auto or {}).get("image", {}) or {}
    # 1) صحة الصورة
    if img.get("ok"):
        lines.append({"ok": True, "text": ("صورة صحيحة" if AR else "Valid image") + f" ({img.get('kind','')})"})
    else:
        reason = img.get("reason", "")
        lines.append({"ok": False, "text": ("صورة غير صالحة" if AR else "Invalid image") + f" — {reason}"})
    # 2) التكرار
    if (auto or {}).get("duplicate"):
        lines.append({"ok": False, "text": "⚠️ " + ("إيصال مكرر (استُخدم من قبل)" if AR else "Duplicate receipt (used before)")})
    else:
        lines.append({"ok": True, "text": ("غير مكرر" if AR else "Not a duplicate")})
    # 3) OCR / فحص المبلغ
    ocr = (auto or {}).get("ocr")
    if ocr is None:
        lines.append({"ok": None, "text": ("فحص المبلغ (OCR) غير متاح على هذا الجهاز — راجع الصورة يدوياً"
                                           if AR else "Amount check (OCR) unavailable on this machine — review the image manually")})
    else:
        af = ocr.get("amount_found")
        if af is True:
            lines.append({"ok": True, "text": ("المبلغ ظاهر في الإيصال" if AR else "Amount found in receipt")})
        elif af is False:
            lines.append({"ok": False, "text": ("⚠️ المبلغ غير ظاهر في الإيصال" if AR else "Amount NOT found in receipt")})
        rf = ocr.get("ref_found")
        if rf is True:
            lines.append({"ok": True, "text": ("رقم الاستلام/المُستلِم ظاهر" if AR else "Recipient/ref found")})
        elif rf is False:
            lines.append({"ok": False, "text": "⚠️ " + ("رقم الاستلام/المُستلِم غير ظاهر في الإيصال"
                                                        if AR else "Recipient/ref NOT found in receipt")})
    return lines

VERDICT_STYLE = {
    "auto_pass":    ("on",  "✓"),
    "needs_review": ("mid", "؟"),
    "suspect":      ("off", "⚠"),
}

def verdict_label(v, lang="ar"):
    m = {
        "auto_pass":   ("✅ الفحص الآلي: مبدئياً سليم", "✅ Auto-check: looks valid"),
        "needs_review":("🕵️ الفحص الآلي: بحاجة لمراجعتك", "🕵️ Auto-check: needs your review"),
        "suspect":     ("⚠️ الفحص الآلي: مشبوه — راجع بعناية", "⚠️ Auto-check: suspicious — review carefully"),
    }
    pair = m.get(v, ("—", "—"))
    return pair[0] if lang == "ar" else pair[1]
