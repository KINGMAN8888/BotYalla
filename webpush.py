"""الإشعارات الفورية (Web Push) — تصل الهاتف/الكمبيوتر والمتصفح مغلق.

كل إشعار يُخزَّن في مركز الإشعارات (`db._notify`) يمرّ بخطّاف `NOTIFY_HOOKS` إلى طابور
هنا، وخيط خلفي يرسله لكل أجهزة المستخدم. لا شبكة داخل معاملة القاعدة ولا تأخير للعملية
الأصلية — الإشعار الفوري إضافة، وفشله لا يُسقط شيئاً.

- **التشفير** RFC 8291 (aes128gcm) و**هوية المرسل** RFC 8292 (VAPID/ES256) بمكتبة
  `cryptography` نفسها — بلا تبعية جديدة. المفتاح يُولَّد مرة ويُحفظ مختوماً (`db.seal`)
  في إعدادات المنصة؛ عمّال gunicorn المتعددون يتفقون عليه (`db.platform_once`).
- **لا SSRF:** الـendpoint يأتي من المتصفح، فلا نرسل إلا لخدمات الدفع المعروفة (HTTPS).
- **النص بلغة المستخدم** يُكتب هنا (الإشعار مخزّن بنوعه وبياناته — مثل bell.jsx).
- 404/410 من خدمة الدفع = الاشتراك انتهى ⇒ حذف فوري؛ غيره فشل مؤقت يُحذف بعد 5 متتالية.
"""
import base64
import json
import logging
import os
import queue
import threading
import time
import urllib.parse

import database as db

log = logging.getLogger("webpush")

# خدمات الدفع الرسمية وحدها (Chrome/Edge-Android/Opera/Samsung ⇐ FCM · Firefox · Safari · Edge-Windows)
PUSH_HOSTS = ("fcm.googleapis.com", "android.googleapis.com", "updates.push.services.mozilla.com",
              "push.services.mozilla.com", "web.push.apple.com")
PUSH_SUFFIXES = (".notify.windows.com", ".push.apple.com")
MAX_PAYLOAD = 3000                 # الحدّ الفعلي ~4078 بايت بعد التشفير — هامش أمان
HTTP = None                        # للاختبار: دالة (url, headers, body) ⇒ status
_Q = queue.Queue(maxsize=2000)
_worker = None
_lock = threading.Lock()
_key = None


def b64u(b):
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def ub64u(s):
    s = str(s or "")
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


# ─────────────────────────── المفاتيح (VAPID) ───────────────────────────
def _private():
    """مفتاح المنصة الخاص (P-256). البيئة أولاً (VAPID_PRIVATE_KEY بصيغة PEM أو b64url خام) ثم القاعدة."""
    global _key
    if _key is not None:
        return _key
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives import serialization
    raw = os.getenv("VAPID_PRIVATE_KEY", "").strip()
    if not raw:
        stored = db.get_platform("vapid_private")
        if not stored:
            k = ec.generate_private_key(ec.SECP256R1())
            fresh = b64u(k.private_numbers().private_value.to_bytes(32, "big"))
            stored = db.platform_once("vapid_private", db.seal(fresh))
        raw = db.unseal(stored)
    if raw.startswith("-----"):
        _key = serialization.load_pem_private_key(raw.encode(), password=None)
    else:
        _key = ec.derive_private_key(int.from_bytes(ub64u(raw), "big"), ec.SECP256R1())
    return _key


def public_key():
    """المفتاح العام بصيغة applicationServerKey (نقطة غير مضغوطة، b64url) — للمتصفح."""
    from cryptography.hazmat.primitives import serialization
    return b64u(_private().public_key().public_bytes(serialization.Encoding.X962,
                                                    serialization.PublicFormat.UncompressedPoint))


def _subject():
    email = db.get_platform("support_email", "") or "info@botyalla.com"
    return f"mailto:{email}"


def vapid_header(endpoint, now=None):
    """Authorization: vapid t=<JWT ES256>, k=<المفتاح العام> — aud = أصل خدمة الدفع."""
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
    u = urllib.parse.urlsplit(endpoint)
    claims = {"aud": f"{u.scheme}://{u.netloc}", "exp": int(now or time.time()) + 12 * 3600, "sub": _subject()}
    head = b64u(json.dumps({"typ": "JWT", "alg": "ES256"}, separators=(",", ":")).encode())
    body = b64u(json.dumps(claims, separators=(",", ":")).encode())
    signing = f"{head}.{body}".encode()
    r, s = decode_dss_signature(_private().sign(signing, ec.ECDSA(hashes.SHA256())))
    sig = b64u(r.to_bytes(32, "big") + s.to_bytes(32, "big"))
    return f"vapid t={head}.{body}.{sig}, k={public_key()}"


# ─────────────────────────── التشفير (RFC 8291) ───────────────────────────
def encrypt(p256dh, auth, plaintext, salt=None, server_key=None):
    """نص ⇒ جسم aes128gcm (رأس + سجل واحد). `salt`/`server_key` للاختبار فقط."""
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF
    ua_pub = ub64u(p256dh)
    secret = ub64u(auth)
    ua_key = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), ua_pub)
    as_key = server_key or ec.generate_private_key(ec.SECP256R1())
    as_pub = as_key.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    shared = as_key.exchange(ec.ECDH(), ua_key)
    ikm = HKDF(hashes.SHA256(), 32, salt=secret, info=b"WebPush: info\x00" + ua_pub + as_pub).derive(shared)
    salt = salt or os.urandom(16)
    cek = HKDF(hashes.SHA256(), 16, salt=salt, info=b"Content-Encoding: aes128gcm\x00").derive(ikm)
    nonce = HKDF(hashes.SHA256(), 12, salt=salt, info=b"Content-Encoding: nonce\x00").derive(ikm)
    body = AESGCM(cek).encrypt(nonce, plaintext + b"\x02", None)     # 0x02 = آخر سجل
    return salt + (4096).to_bytes(4, "big") + bytes([len(as_pub)]) + as_pub + body


def endpoint_ok(endpoint):
    try:
        u = urllib.parse.urlsplit(str(endpoint or ""))
    except ValueError:
        return False
    host = (u.hostname or "").lower()
    return (u.scheme == "https" and not u.username and not u.password and u.port in (None, 443)
            and len(endpoint) <= 800 and (host in PUSH_HOSTS or host.endswith(PUSH_SUFFIXES)))


def keys_ok(p256dh, auth):
    try:
        return len(ub64u(p256dh)) == 65 and ub64u(p256dh)[0] == 4 and 12 <= len(ub64u(auth)) <= 32
    except (ValueError, TypeError):
        return False


# ─────────────────────────── النص بلغة المستخدم ───────────────────────────
def _t(lang, ar, en):
    return en if lang == "en" else ar


def render(n, lang="ar"):
    """إشعار مخزّن ⇒ {title, body, urgent, ttl}. نفس معاني bell.jsx (KIND)."""
    d = n.get("data") or {}
    k = n.get("kind")
    L = lambda ar, en: _t(lang, ar, en)
    name = d.get("name") or ""
    if k == "call":
        return {"title": L("📞 مكالمة واتساب واردة", "📞 Incoming WhatsApp call"),
                "body": L(f"{name or 'عميل'} يتصل الآن — اضغط للرد من صندوق الوارد", f"{name or 'A customer'} is calling — tap to answer in the inbox"),
                "urgent": True, "ttl": 60}
    if k == "attention":
        why = d.get("why")
        title = {"needs_support": L("🙋 عميل يحتاج مساعدتك", "🙋 A customer needs you"),
                 "handoff": L("🚨 محادثة تحتاج تدخّلك", "🚨 A conversation needs you"),
                 "bad_rating": L("⚠️ تقييم سلبي من عميل", "⚠️ Negative rating from a customer"),
                 "human_msg": L("💬 رسالة جديدة من عميل", "💬 New customer message")}.get(why, L("💬 عميل ينتظر ردّك", "💬 A customer is waiting"))
        who = " · ".join(x for x in (name, d.get("bot")) if x)
        text = d.get("text") or ""
        return {"title": title, "body": (f"{who}\n{text}" if who and text else who or text)[:300],
                "urgent": why in ("needs_support", "handoff"), "ttl": 6 * 3600}
    if k == "assigned":
        return {"title": L("👤 محادثة أُسندت إليك", "👤 Conversation assigned to you"), "body": name, "urgent": True, "ttl": 6 * 3600}
    if k == "mention":
        return {"title": L(f"💬 {d.get('by') or 'زميل'} أشار إليك", f"💬 {d.get('by') or 'A teammate'} mentioned you"),
                "body": f"{name}: {d.get('text') or ''}"[:300], "urgent": True, "ttl": 6 * 3600}
    if k == "paid":
        return {"title": L("💳 دفعة جديدة وصلت", "💳 New payment received"),
                "body": " · ".join(x for x in (str(d.get("amount") or ""), name, d.get("desc") or "") if x), "urgent": False, "ttl": 86400}
    if k == "integ_failed":
        return {"title": L("🔗 تعذّر تنفيذ حدث في تكامل", "🔗 An integration event failed"), "body": name, "urgent": False, "ttl": 86400}
    if k == "ticket_new":
        return {"title": L("🎫 تذكرة دعم جديدة", "🎫 New support ticket"), "body": f"{d.get('user') or ''}: {d.get('subject') or ''}", "urgent": False, "ttl": 86400}
    if k == "ticket_user":
        return {"title": L("🎫 ردّ جديد على تذكرة", "🎫 New ticket reply"), "body": f"{d.get('user') or ''}: {d.get('subject') or ''}", "urgent": False, "ttl": 86400}
    if k == "ticket_reply":
        return {"title": L("🎧 فريق الدعم ردّ عليك", "🎧 Support replied"), "body": d.get("subject") or "", "urgent": False, "ttl": 86400}
    if k == "test":
        return {"title": L("🔔 التنبيهات تعمل!", "🔔 Notifications are on!"),
                "body": L("هكذا سيصلك كل عميل جديد وكل مكالمة ودفعة — فوراً.", "This is how every new customer, call and payment will reach you — instantly."),
                "urgent": False, "ttl": 600}
    return {"title": "BotYalla", "body": L("لديك إشعار جديد", "You have a new notification"), "urgent": False, "ttl": 86400}


def payload(n, lang, unread=None):
    r = render(n, lang)
    url = n.get("url") or "/home"
    if not url.startswith("/") or url.startswith("//"):
        url = "/home"
    out = {"t": r["title"][:120], "b": (r["body"] or "")[:400], "u": url, "k": n.get("kind"), "id": n.get("id"),
           "tag": f"{n.get('kind')}:{url}"[:120], "ri": bool(r["urgent"]), "ts": int(n.get("created_at") or time.time()) * 1000,
           "dir": "ltr" if lang == "en" else "rtl", "lang": lang}
    if unread is not None:
        out["n"] = int(unread)
    raw = json.dumps(out, ensure_ascii=False).encode()
    while len(raw) > MAX_PAYLOAD and out["b"]:
        out["b"] = out["b"][: len(out["b"]) // 2]
        raw = json.dumps(out, ensure_ascii=False).encode()
    return raw, r


# ─────────────────────────── الإرسال ───────────────────────────
def _post(url, headers, body):
    if HTTP:
        return HTTP(url, headers, body)
    import httpx
    return httpx.post(url, headers=headers, content=body, timeout=10).status_code


def send_one(sub, raw, ttl=86400, urgent=False, topic=None):
    """جهاز واحد ⇒ True/False. يحدّث عدّاد الفشل ويحذف المنتهي."""
    if not endpoint_ok(sub["endpoint"]):
        db.delete_push_sub(sub["endpoint"])
        return False
    try:
        body = encrypt(sub["p256dh"], sub["auth"], raw)
        headers = {"Content-Encoding": "aes128gcm", "Content-Type": "application/octet-stream",
                   "TTL": str(int(ttl)), "Urgency": "high" if urgent else "normal",
                   "Authorization": vapid_header(sub["endpoint"])}
        if topic:
            headers["Topic"] = topic
        code = _post(sub["endpoint"], headers, body)
    except Exception as e:                       # شبكة/مفتاح تالف — فشل مؤقت
        log.warning("push send failed: %s", type(e).__name__)
        db.push_sub_result(sub["id"], False)
        return False
    if code in (404, 410):                       # الاشتراك انتهى (ألغى المستخدم الإذن أو حذف التطبيق)
        db.delete_push_sub(sub["endpoint"])
        return False
    ok = 200 <= code < 300
    db.push_sub_result(sub["id"], ok)
    if not ok:
        log.info("push rejected status=%s host=%s", code, urllib.parse.urlsplit(sub["endpoint"]).hostname)
    return ok


def deliver(n):
    """إشعار ⇒ عدد الأجهزة التي وصلها. متزامن (الخيط الخلفي يستدعيه، والاختبارات مباشرة)."""
    subs = db.list_push_subs(n["user_id"])
    if not subs:
        return 0
    lang = db.user_lang(n["user_id"])
    raw, r = payload(n, lang, db.unread_notifications(n["user_id"]))
    # Topic يستبدل إشعاراً معلّقاً لنفس المحادثة لم يُسلَّم بعد (جهاز مغلق) بدل أن تتراكم
    topic = b64u(str(n.get("kind")).encode() + b":" + (n.get("url") or "").encode())[:32] if n.get("kind") != "test" else None
    return sum(send_one(s, raw, r["ttl"], r["urgent"], topic) for s in subs)


def _run():
    while True:
        n = _Q.get()
        time.sleep(0.4)          # يترك معاملة المُنشئ تكتمل قبل قراءة عدد غير المقروء
        try:
            deliver(n)
        except Exception:
            log.exception("push delivery failed")


def enqueue(n):
    global _worker
    if not n.get("user_id"):
        return
    with _lock:
        if _worker is None or not _worker.is_alive():
            _worker = threading.Thread(target=_run, name="webpush", daemon=True)
            _worker.start()
    try:
        _Q.put_nowait(n)
    except queue.Full:
        log.warning("push queue full — dropping")


def install():
    """يُستدعى مرة عند الإقلاع: كل إشعار جديد يُدفع فوراً."""
    if enqueue not in db.NOTIFY_HOOKS:
        db.NOTIFY_HOOKS.append(enqueue)


def test(user_id):
    """إشعار تجربة لكل أجهزة المستخدم (متزامن — لنعرف النتيجة) ⇒ عدد الأجهزة."""
    return deliver({"id": 0, "user_id": user_id, "kind": "test", "data": {}, "url": "/home", "created_at": int(time.time())})
