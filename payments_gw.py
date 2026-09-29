"""بوابات دفع صاحب النشاط (المرحلة 9) — Moyasar و Tap. المنصة لا تلمس المال: الرابط من حساب
صاحب النشاط نفسه والمبلغ يذهب لحسابه مباشرة.

قاعدتان لا تُكسران:
  · **الحالة من البوابة لا من الويبهوك:** الإشعار الوارد مجرد «تنبيه»؛ نسأل البوابة بمفتاحنا السرّي عن
    حالة الفاتورة/العملية قبل اعتبارها مدفوعة (`status`). ويبهوك مزوَّر لا يدفع شيئاً.
  · **المبلغ بالوحدة الصغرى صحيحاً** (هللة/قرش) كما في AGENTS §19 — لا أعداد عشرية في الحسابات.

كل دالة تتلقّى `http` (عميل httpx) ليُحقن في الاختبارات بلا شبكة.
"""
import logging

log = logging.getLogger("payments_gw")

PROVIDERS = ("moyasar", "tap", "hyperpay")
# HyperPay (COPYandPAY): جلسة الدفع تنتهي خلال 30 دقيقة ونموذج البطاقة يُعرض في صفحتنا بسكربتهم —
# فالرابط صفحتنا الموقَّعة تنشئ جلسة جديدة عند كل فتح، والمرجع الثابت `merchantTransactionId` هو ما نسأل عنه.
HYPERPAY = {True: "https://eu-test.oppwa.com", False: "https://eu-prod.oppwa.com"}
_HP_OK = __import__("re").compile(r"^(000\.000\.|000\.100\.1|000\.[36])")
_HP_PENDING = __import__("re").compile(r"^(000\.200)")
CURRENCIES = ("SAR", "EGP", "AED", "KWD", "BHD", "QAR", "OMR", "USD")
MINOR = {"KWD": 1000, "BHD": 1000, "OMR": 1000}          # عملات بثلاث خانات عشرية
MOYASAR = "https://api.moyasar.com/v1"
TAP = "https://api.tap.company/v2"
TIMEOUT = 15
_CC = ("966", "971", "965", "973", "974", "968", "962", "961", "212", "216", "213", "20", "44", "1")


class GatewayError(Exception):
    """سبب مفهوم: auth · rejected · network · bad_response"""


def minor_factor(currency):
    return MINOR.get(currency, 100)


def _client(http):
    if http is not None:
        return http
    import httpx
    return httpx.Client(timeout=TIMEOUT)


def _json(r):
    try:
        return r.json()
    except ValueError:
        raise GatewayError("bad_response")


def _check(r, secret):
    if r.status_code in (401, 403):
        raise GatewayError("auth")
    if r.status_code >= 400:
        log.info("gateway rejected %s: %s", r.status_code, (r.text or "")[:300].replace(secret, "***"))
        raise GatewayError("rejected")


def _phone(peer):
    digits = "".join(ch for ch in (peer or "").split(":", 1)[-1] if ch.isdigit())
    for cc in _CC:
        if digits.startswith(cc) and len(digits) - len(cc) >= 7:
            return {"country_code": cc, "number": digits[len(cc):]}
    return None


def create(provider, secret, *, amount, currency, description, ref, return_url, webhook_url, expires_at_iso,
           customer_name="", peer="", http=None):
    """يُنشئ رابط دفع ويرجّع (معرّف البوابة, الرابط). `amount` بالوحدة الصغرى.
    HyperPay: لا نداء هنا — المعرّف هو مرجعنا والرابط صفحتنا (chat_pay يبنيها)، فيرجّع (ref, "")."""
    if provider == "hyperpay":
        return ref, ""
    c = _client(http)
    try:
        if provider == "moyasar":
            r = c.post(f"{MOYASAR}/invoices", auth=(secret, ""), json={
                "amount": int(amount), "currency": currency, "description": description[:255],
                "callback_url": return_url, "success_url": return_url, "back_url": return_url,
                "expired_at": expires_at_iso, "metadata": {"ref": ref}})
            _check(r, secret)
            d = _json(r)
            if not d.get("id") or not str(d.get("url") or "").startswith("https://"):
                raise GatewayError("bad_response")
            return d["id"], d["url"]
        if provider == "tap":
            cust = {"first_name": (customer_name or "Customer")[:40]}
            ph = _phone(peer)
            if ph:
                cust["phone"] = ph
            else:
                cust["email"] = "customer@example.com"     # Tap تشترط بريداً أو هاتفاً
            r = c.post(f"{TAP}/charges", headers={"Authorization": f"Bearer {secret}"}, json={
                "amount": round(int(amount) / minor_factor(currency), 3), "currency": currency,
                "customer_initiated": True, "threeDSecure": True, "save_card": False,
                "description": description[:255], "metadata": {"udf1": ref}, "reference": {"transaction": ref},
                "customer": cust, "source": {"id": "src_all"},
                "post": {"url": webhook_url}, "redirect": {"url": return_url}})
            _check(r, secret)
            d = _json(r)
            url = ((d.get("transaction") or {}).get("url") or "")
            if not d.get("id") or not url.startswith("https://"):
                raise GatewayError("bad_response")
            return d["id"], url
    except GatewayError:
        raise
    except Exception as e:
        log.info("gateway %s create failed: %s", provider, type(e).__name__)
        raise GatewayError("network")
    raise GatewayError("provider")


def hp_checkout(secret, entity, *, amount, currency, ref, test, customer_name="", http=None):
    """جلسة دفع HyperPay لصفحتنا ⇒ checkoutId. `amount` بالوحدة الصغرى."""
    c = _client(http)
    try:
        f = minor_factor(currency)
        r = c.post(f"{HYPERPAY[bool(test)]}/v1/checkouts", headers={"Authorization": f"Bearer {secret}"}, data={
            "entityId": entity, "amount": f"{int(amount) / f:.{3 if f == 1000 else 2}f}", "currency": currency,
            "paymentType": "DB", "merchantTransactionId": ref,
            **({"customer.givenName": customer_name[:40]} if customer_name else {})})
        _check(r, secret)
        d = _json(r)
        if not d.get("id") or not _HP_PENDING.match(str((d.get("result") or {}).get("code") or "")):
            raise GatewayError("rejected")
        return str(d["id"])
    except GatewayError:
        raise
    except Exception as e:
        log.info("hyperpay checkout failed: %s", type(e).__name__)
        raise GatewayError("network")


def hp_widget(checkout_id, test):
    return f"{HYPERPAY[bool(test)]}/v1/paymentWidgets.js?checkoutId={checkout_id}"


def status(provider, secret, gw_id, http=None, opts=None):
    """حالة الدفع كما تقولها البوابة: paid · pending · failed · expired.
    HyperPay: `gw_id` مرجعنا، ونسأل كل كيان (البطاقات ومدى) عن أي عملية ناجحة بهذا المرجع."""
    c = _client(http)
    opts = opts or {}
    try:
        if provider == "hyperpay":
            seen_fail = False
            for entity in [e for e in (opts.get("entity"), opts.get("entity_mada")) if e]:
                r = c.get(f"{HYPERPAY[bool(opts.get('test'))]}/v1/query", headers={"Authorization": f"Bearer {secret}"},
                          params={"entityId": entity, "merchantTransactionId": gw_id})
                if r.status_code == 400 or r.status_code == 404:
                    continue                                   # «لا عمليات بهذا المرجع» بعد
                _check(r, secret)
                for p in _json(r).get("payments") or []:
                    code = str((p.get("result") or {}).get("code") or "")
                    if _HP_OK.match(code) and str(p.get("paymentType") or "DB") == "DB":
                        return "paid"
                    if not _HP_PENDING.match(code):
                        seen_fail = True
            return "failed" if seen_fail and opts.get("final") else "pending"
    except GatewayError:
        raise
    except Exception as e:
        log.info("gateway hyperpay status failed: %s", type(e).__name__)
        raise GatewayError("network")
    try:
        if provider == "moyasar":
            r = c.get(f"{MOYASAR}/invoices/{gw_id}", auth=(secret, ""))
            _check(r, secret)
            s = str(_json(r).get("status") or "").lower()
            return {"paid": "paid", "expired": "expired", "failed": "failed", "canceled": "failed",
                    "cancelled": "failed", "voided": "failed"}.get(s, "pending")
        if provider == "tap":
            r = c.get(f"{TAP}/charges/{gw_id}", headers={"Authorization": f"Bearer {secret}"})
            _check(r, secret)
            s = str(_json(r).get("status") or "").upper()
            if s == "CAPTURED":
                return "paid"
            if s in ("FAILED", "DECLINED", "CANCELLED", "RESTRICTED", "VOID", "TIMEDOUT", "UNKNOWN", "ABANDONED"):
                return "failed"
            return "pending"
    except GatewayError:
        raise
    except Exception as e:
        log.info("gateway %s status failed: %s", provider, type(e).__name__)
        raise GatewayError("network")
    raise GatewayError("provider")


def webhook_gw_id(provider, body):
    """معرّف الفاتورة/العملية من إشعار البوابة (للبحث فقط — الحالة تُسأل من البوابة)."""
    body = body if isinstance(body, dict) else {}
    if provider == "moyasar":
        d = body.get("data") or {}
        return str(d.get("invoice_id") or (d.get("id") if str(body.get("type", "")).startswith("invoice") else "") or "")
    if provider == "tap":
        return str(body.get("id") or "")
    return ""
