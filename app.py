"""BotYalla — لوحة التحكم (Flask).
حسابات مستخدمين بتشفير، إنشاء/تشغيل بوتات، باني فلو No-Code،
تحليلات (JSON للرسوم)، بث جماعي، حجوزات، تصدير."""
import os, sys, json, csv, io, functools

# على ويندوز عند إعادة توجيه الخرج (ملف/أنبوب/خدمة) يصير الترميز cp1252،
# فأي print فيه عربي أو إيموجي يرمي UnicodeEncodeError ويُسقط bootstrap().
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
from flask import (Flask, request, redirect, url_for, render_template,
                   session, flash, abort, jsonify, Response, send_from_directory, g,
                   get_flashed_messages, make_response)

# تحميل متغيرات .env تلقائياً إذا وُجد الملف
_env_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
if os.path.isfile(_env_file):
    try:
        with open(_env_file, "r", encoding="utf-8") as _f:
            for _line in _f:
                _line = _line.strip()
                if _line and not _line.startswith("#") and "=" in _line:
                    _k, _v = _line.split("=", 1)
                    os.environ.setdefault(_k.strip(), _v.strip().strip("'\""))
    except Exception:
        pass

import database as db
import auth
from bot_manager import manager
import templates_bot as T
from flow_engine import DEFAULT_CS_FLOW as _DEFAULT_FLOW
import tg_helpers as tg
from channels.whatsapp import verify_credentials as wa_verify
import channels.wa_templates as WT
import channels.whatsapp as WAC
import media_store
from bot_manager import WA_WINDOW
import ai_agent as ai
import managed_bots as MB
import support_desk as SD
import asset_store
import flow_engine as FE
import base64
import urllib.parse as _up
import i18n
import plans
import payments as pay
import platform_bot as PB
import mailer
import email_campaigns as EC
import accounts as ACC
import urllib.request as _ureq
import legal_content as LEGAL
import analytics as AN
from xml.sax.saxutils import escape as _xesc
import time as _time
import logging
from logging.handlers import RotatingFileHandler
import datetime as _dt
import re as _re
import hashlib
import hmac
import secrets as _secrets
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from markupsafe import Markup
from werkzeug.utils import secure_filename
from werkzeug.exceptions import InternalServerError
from icons import icon
import icons

app = Flask(__name__, template_folder="templates_web", static_folder="static")

# خلف nginx كل الطلبات تصل من 127.0.0.1 وبمخطّط http. بدون هذا يعدّ محدِّد
# محاولات الدخول كل المستخدمين كعنوان واحد فيقفل الدخول على الجميع، وتُبنى
# الروابط الخارجية بـ http رغم TLS. نثق بقفزة بروكسي واحدة فقط (nginx).
from werkzeug.middleware.proxy_fix import ProxyFix
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

app.secret_key = os.getenv("FLASK_SECRET", "botyalla-dev-secret-change-me")
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.getenv("COOKIE_SECURE", "0") == "1",  # فعّلها على HTTPS
    # حد أقصى للطلب كله: فيديو مكتبة الوسائط حتى 16MB (حدّ واتساب) + هامش النموذج.
    # كل نوع رفع يفرض حدّه الأضيق بنفسه — الإيصالات 8MB في payments.MAX_BYTES.
    MAX_CONTENT_LENGTH=18 * 1024 * 1024,
)

# BOTYALLA_UPLOADS يسمح للاختبارات بالكتابة في مجلد مؤقت — بدونه تتراكم
# ملفات وهمية بين إيصالات الدفع الحقيقية، كما حدث فعلاً.
UPLOAD_DIR = os.environ.get(
    "BOTYALLA_UPLOADS",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "uploads"))
os.makedirs(UPLOAD_DIR, exist_ok=True)

# ---------- تسجيل الأخطاء والأحداث ----------
log = logging.getLogger("botyalla")
LOG_DIR = os.environ.get(
    "BOTYALLA_LOGS", os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs"))

def setup_logging():
    """INFO إلى stderr (يلتقطه journald) وإلى ملف دوّار `logs/botyalla.log` (10MB × 5).
    تُستدعى من `bootstrap()` وحده لا عند الاستيراد — حتى لا تكتب الاختبارات في
    logs/ الحقيقي. تكرار الاستدعاء بلا أثر."""
    root = logging.getLogger()
    if any(getattr(h, "_botyalla", False) for h in root.handlers):
        return
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    root.setLevel(logging.INFO)
    handlers = [logging.StreamHandler()]
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        handlers.append(RotatingFileHandler(os.path.join(LOG_DIR, "botyalla.log"),
                                            maxBytes=10 * 1024 * 1024, backupCount=5,
                                            encoding="utf-8"))
    except OSError as e:
        print(f"file logging disabled: {e}", file=sys.stderr)
    for h in handlers:
        h.setFormatter(fmt)
        h._botyalla = True
        root.addHandler(h)
    # Flask يضيف معالج stderr خاصاً به؛ مع معالج root يتكرر كل سطر مرتين.
    from flask.logging import default_handler
    app.logger.removeHandler(default_handler)
    # ⚠️ httpx يسجّل كل طلب بمستوى INFO والرابط فيه **توكن البوت**
    # (api.telegram.org/bot<TOKEN>/getUpdates) كل بضع ثوانٍ لكل بوت — سرّ في
    # ملف السجل وملف يتضخّم. لا يُسجَّل منه إلا التحذيرات.
    logging.getLogger("httpx").setLevel(logging.WARNING)

# ---------- حماية CSRF (خفيفة، بدون مكتبات) ----------
_login_attempts = {}   # ip -> (count, first_ts)

@app.before_request
def _csrf_protect():
    if request.method in ("POST", "PUT", "PATCH", "DELETE"):
        if request.path == "/wh/whatsapp":
            return
        # إلغاء اشتراك البريد بضغطة (RFC 8058): Gmail/Yahoo يرسلان POST من خوادمهما بلا
        # جلسة. الحارس هنا توكن HMAC في الرابط نفسه (mailer.check_unsub) + حدّ للطلبات.
        if request.path.startswith("/email/unsubscribe/"):
            return
        token = session.get("_csrf")
        sent = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token")
        if not token or not sent or not _secrets.compare_digest(str(token), str(sent)):
            abort(400, "CSRF token invalid")

@app.before_request
def _capture_ref():
    """?ref=CODE على أي صفحة يُحفظ في الجلسة ويُستهلك عند التسجيل."""
    code = request.args.get("ref")
    if code and not session.get("uid"):
        session["ref"] = code.strip().upper()[:32]

@app.before_request
def _lang_from_query():
    """`?lang=en` على أي صفحة: روابط hreflang ثابتة تجعل النسخة الإنجليزية قابلة
    للفهرسة، ورابطاً يُشارَك فيفتح بلغة صاحبه. تفضيل عرض فقط — لا حالة حسّاسة."""
    code = request.args.get("lang")
    if request.method == "GET" and code in i18n.LANGS and session.get("lang") != code:
        session["lang"] = code

@app.before_request
def _canonical_host():
    """www والدومين المجرّد كانا نسختين منفصلتين (200 لكلٍّ): محتوى مكرر يقسم Google
    الروابط بينه، والجلسة لا تنتقل بينهما. الأصل مضيف PUBLIC_URL — أي GET على «نفس
    الدومين مع www أو بدونه» يُحوَّل إليه 301. الويبهوك مستثنى: Meta تتحقق من العنوان
    كما سُجّل عندها، والتحويل يكسر التحقق."""
    if request.method not in ("GET", "HEAD") or request.path.startswith("/wh/"):
        return None
    base = os.getenv("PUBLIC_URL", "").strip().rstrip("/")
    if not base.startswith(("https://", "http://")):
        return None
    canon = _up.urlsplit(base).netloc.lower()
    host = (request.host or "").lower()
    bare = lambda h: h[4:] if h.startswith("www.") else h
    if host == canon or bare(host) != bare(canon):
        return None
    qs = request.query_string.decode("latin-1")
    return redirect(base + request.path + ("?" + qs if qs else ""), 301)

# ---------- قياس الزوار — داخل المنصة، بلا سكربت خارجي ولا كوكي تتبّع ----------
_PV_PATHS = {"/", "/pricing", "/register", "/login", "/terms", "/privacy", "/refund", "/acceptable-use"}
_BOT_UA = _re.compile(r"bot|crawl|spider|slurp|preview|facebookexternalhit|whatsapp|telegram|curl|"
                      r"wget|python|httpx|headless|lighthouse|uptime", _re.I)

def _visitor_source():
    """(مصدر الحملة، دومين المُحيل): utm_source أو كود أفيليت، ومُحيل من خارج الموقع."""
    src = (request.args.get("utm_source") or "").strip().lower()[:40]
    if not src and request.args.get("ref"):
        src = "ref"
    ref = ""
    host = (_up.urlsplit(request.referrer or "").hostname or "").lower()
    own = (request.host or "").split(":")[0].lower()
    bare = lambda h: h[4:] if h.startswith("www.") else h
    if host and bare(host) != bare(own):
        ref = bare(host)[:60]
    return src, ref

@app.after_request
def _count_view(resp):
    """زيارة صفحة عامة واحدة. `vid` بصمة يومية (IP+المتصفح+اليوم+سرّ التطبيق) تعدّ الزوار
    الفريدين بلا تخزين IP ولا تتبّع عبر الأيام — فلا كوكي تتبّع ولا لافتة موافقة. أول مصدر
    للزائر (first-touch) يُحفظ في جلسته الموجودة أصلاً (CSRF) ليُنسب له تسجيله."""
    try:
        if (request.method != "GET" or resp.status_code != 200 or request.path not in _PV_PATHS
                or resp.mimetype != "text/html"):
            return resp
        ua = request.headers.get("User-Agent", "")
        if not ua or _BOT_UA.search(ua):
            return resp
        src, ref = _visitor_source()
        if (src or ref) and not session.get("src"):
            session["src"] = src or ref
        vid = hashlib.sha256(f"{request.remote_addr}|{ua}|{db._day()}|{app.secret_key}".encode()
                             ).hexdigest()[:16]
        device = "mobile" if _re.search(r"Mobi|Android|iPhone", ua) else "desktop"
        db.log_page_view(request.path, ref, src, device, vid)
    except Exception:
        log.warning("page view not counted", exc_info=True)
    return resp

@app.before_request
def _revalidate_identity():
    """يعيد قراءة هوية المستخدم من قاعدة البيانات في كل طلب.
    الدور والحظر مصدرهما القاعدة لا الجلسة — حتى يسري الحظر أو تغيير الدور
    فوراً على الجلسات المفتوحة، بدل انتظار خروج المستخدم وعودته."""
    g.user = None
    if request.endpoint == "static" or not session.get("uid"):
        return
    row = db.get_user(session["uid"])
    if not row or row.get("is_blocked"):
        # الحساب حُذف أو حُظر أثناء الجلسة → أنهِ الجلسة فوراً (مع إبقاء اللغة)
        lang = session.get("lang")
        session.clear()
        if lang: session["lang"] = lang
        flash("تم حظر هذا الحساب." if lang != "en" else "This account is blocked.", "error")
        return
    # بصمة كلمة المرور: تغييرها (استرجاع أو «حسابي») يُنهي كل جلسة قديمة —
    # الجهاز المسروق أو المنسيّ يخرج فوراً. جلسة من قبل هذه الميزة بلا بصمة
    # تُعتمد مرة واحدة حتى لا يُطرد كل المستخدمين عند النشر.
    stamp = _pw_stamp(row["pw_hash"])
    if not session.get("pwv"):
        session["pwv"] = stamp
    elif not _secrets.compare_digest(str(session["pwv"]), stamp):
        lang = session.get("lang")
        session.clear()
        if lang: session["lang"] = lang
        flash(i18n.t("session_pw_changed", lang or i18n.DEFAULT), "error")
        return
    g.user = row
    # مزامنة الجلسة مع القاعدة (قد يكون الأدمن غيّر الدور أو الاسم)
    if session.get("role") != row["role"]: session["role"] = row["role"]
    if session.get("uname") != row["username"]: session["uname"] = row["username"]

# ما يبقى متاحاً لحساب جديد لم يؤكد بريده — كل ما عداه يحوّل لصفحة التأكيد.
_GATE_OPEN = ("/verify-email", "/logout", "/lang/", "/static/", "/wh/", "/email/unsubscribe/",
              "/auth/", "/.well-known/", "/api/check-username")
_GATE_PUBLIC = _PV_PATHS | {"/forgot", "/robots.txt", "/sitemap.xml", "/favicon.ico", "/healthz",
                            "/manifest.webmanifest", "/site.webmanifest"}

@app.before_request
def _email_gate():
    """حساب جديد لا يستخدم المنصة قبل تأكيد بريده (قرار المالك: «إجباري قبل أي استخدام»).
    الحسابات القديمة والأدمن والدعم لا يُحجبون (db.email_gate)، والصفحات العامة تبقى متاحة."""
    u = getattr(g, "user", None)
    if not u or not db.email_gate(u):
        return None
    p = request.path
    if p in _GATE_PUBLIC or p.startswith(_GATE_OPEN):
        return None
    if request.method != "GET" or p.startswith("/api/") or request.is_json:
        lang = session.get("lang", i18n.DEFAULT)
        return jsonify({"ok": False, "verify": url_for("verify_email"),
                        "error": "أكّد بريدك الإلكتروني أولاً." if lang != "en" else "Verify your email first."}), 403
    return redirect(url_for("verify_email"))

# ---------- ترويسات الأمان (CSP بـ nonce) ----------
# CSP هي الطبقة التي تُبطل أثر أي حقن حتى لو نفذ من رقابة الهروب. لا تُضبط في
# nginx لأن الـ nonce يجب أن يتغيّر مع كل طلب، و Flask هو من يرسم القوالب.
#
# `script-src` بلا 'unsafe-inline': كل سكربت داخلي عندنا يحمل nonce، فسكربت
# يحقنه مهاجم لن يحمله ولن يعمل. أما `style-src` فيبقى 'unsafe-inline' لأن
# React يكتب أنماطاً في خاصية style ولا سبيل لتمرير nonce إليها.
# `img-src` يسمح بـ https: لأن صور الترحيب والمنتجات روابط يضعها أصحاب البوتات.
_CSP_BASE = {
    "default-src":     ["'self'"],
    "script-src":      ["'self'", "'nonce-{n}'"],
    "style-src":       ["'self'", "'unsafe-inline'", "https://fonts.googleapis.com"],
    "font-src":        ["'self'", "https://fonts.gstatic.com"],
    "img-src":         ["'self'", "data:", "https:"],
    "connect-src":     ["'self'"],
    "form-action":     ["'self'"],
    "base-uri":        ["'self'"],
    "object-src":      ["'none'"],
    "frame-ancestors": ["'none'"],
}

def _build_csp():
    """السياسة = الأساس أعلاه + مصادر أدوات القياس **المضبوطة وحدها**.

    بلا أداة مضبوطة تخرج السياسة حرفياً كما كانت قبل إضافة القياس. وكل أداة
    تفتح نطاقاتها هي فقط (راجع analytics.csp_sources) — فضبط Clarity وحده لا
    يفتح نطاقات فيسبوك. ⚠️ لا تُضِف 'unsafe-inline' إلى script-src أبداً:
    كل سكربتاتنا (وGTM) تحمل nonce، وفتح inline يُبطل حماية REVIEW.md §3.1."""
    d = {k: list(v) for k, v in _CSP_BASE.items()}
    for directive, srcs in AN.csp_sources().items():
        cur = d.setdefault(directive, [])
        for s in srcs:
            if s not in cur:
                cur.append(s)
    return "; ".join(f"{k} {' '.join(v)}" for k, v in d.items())

# تُبنى مرة عند الإقلاع: المعرّفات من البيئة ولا تتغيّر أثناء التشغيل، وإعادة
# البناء في كل طلب تكلفة بلا فائدة. تغيير `.env` يحتاج إعادة تشغيل الخدمة.
_CSP = _build_csp()

@app.before_request
def _csp_nonce():
    g.nonce = _secrets.token_urlsafe(16)

@app.after_request
def _security_headers(resp):
    # لو أوقف before_request سابقٌ الطلبَ (رفض CSRF بـ 400) لا يعمل `_csp_nonce`،
    # و'nonce-' فارغة مصدرٌ غير صالح يطبع المتصفح عنه تحذيراً — ولّد واحدة.
    nonce = getattr(g, "nonce", None) or _secrets.token_urlsafe(16)
    resp.headers.setdefault("Content-Security-Policy", _CSP.format(n=nonce))
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    # HSTS على HTTPS فقط: إرسالها على http يثبّت الترقية قبل أن تكون الشهادة
    # جاهزة فيحجب الموقع عن زوّاره.
    if request.is_secure:
        resp.headers.setdefault("Strict-Transport-Security",
                                "max-age=31536000; includeSubDomains")
    return resp

@app.context_processor
def _nonce_ctx():
    # `an` = ما **يُحقن مباشرةً** لا كل ما هو مضبوط: أداة أُنشئ وسمها داخل حاوية
    # GTM (`GTM_MANAGES`) تخرج بمعرّف فارغ فلا تُحقن مرتين. و`ids()` تبقى كاملة
    # في CSP لأن وسم الحاوية يحتاج نطاقه مفتوحاً هو الآخر.
    return {"csp_nonce": getattr(g, "nonce", ""), "an": AN.inject()}

def _track_events():
    """أحداث القياس التي ستُطلق على هذه الصفحة — تدخل الحمولة كـ`BY.track`.

    مصدران: طابور الجلسة (تسجيل، إنشاء بوت، نيّة دفع…)، و«تحويل مؤكَّد لم
    يُبلَّغ به» المخزّن على حساب المستخدم. الثاني موجود لأن اعتماد الدفعة يقع في
    جلسة الأدمن لا العميل، فلا سبيل لإطلاق `purchase` لحظتها.

    `pop_setting` تقرأ وتحذف في معاملة واحدة، فتبويبان مفتوحان لا يضاعفان
    التحويل. وأي خطأ هنا يُبتلع: القياس لا يُسقط صفحة على مستخدم أبداً."""
    if not AN.configured():
        return []
    events = AN.drain(session)
    u = uid()
    if u:
        try:
            raw = db.pop_setting(u, "track_purchase")
            if raw:
                d = json.loads(raw)
                events.append({"event": "purchase",
                               "params": {"plan": d.get("plan"), "cycle": d.get("cycle"),
                                          "value": d.get("value"), "currency": "EGP",
                                          "transaction_id": str(d.get("id", ""))}})
        except Exception:
            log.warning("could not read the pending purchase conversion", exc_info=True)
    return events

def _static_v(filename):
    """رابط ملف ثابت بإصدار من تاريخ تعديله (`?v=`). nginx يقدّم /static/ بـ
    `immutable` لثلاثين يوماً، فبلا إصدار يبقى الزائر العائد — ومعاينات الشبكات
    الاجتماعية — على صورة أو أيقونة قديمة بعد إعادة توليدها ونشرها."""
    try:
        v = str(int(os.path.getmtime(os.path.join(app.static_folder, filename))))
    except OSError:
        v = "0"
    return url_for("static", filename=filename, v=v)

_DIST_MANIFEST = {"mtime": None, "data": {}}

def _dist_manifest():
    """dist/.vite/manifest.json (خريطة Vite: مدخل ← ملفه وقطعه). يُعاد قراءته فقط حين
    يتغيّر بعد بناء جديد."""
    path = os.path.join(app.static_folder, "dist", ".vite", "manifest.json")
    try:
        mtime = os.path.getmtime(path)
        if _DIST_MANIFEST["mtime"] != mtime:
            with open(path, encoding="utf-8") as f:
                _DIST_MANIFEST.update(data=json.load(f), mtime=mtime)
    except (OSError, ValueError):
        return {}
    return _DIST_MANIFEST["data"]

def _dist_entry(entry):
    """رابط مدخل Vite الفعلي (`src/main.jsx` أو `src/console-main.jsx`) — اسمه يحمل hash.
    بلا ?v=: قطع العروض تستورد المدخل باسمه المجرّد، ورابط مختلف يجعل المتصفح ينفّذه مرتين."""
    m = _dist_manifest().get(entry)
    return url_for("static", filename="dist/" + m["file"]) if m else ""

def _dist_preloads(entry):
    """روابط القطع المشتركة التي يستوردها مدخل Vite — تُطلب بـ modulepreload مع الصفحة بدل
    أن تنتظر تحليل المدخل (جولة شبكة كاملة على كل صفحة). أسماؤها تحمل hash فلا تحتاج ?v=."""
    man, out, seen = _dist_manifest(), [], set()
    def walk(key):
        for k in man.get(key, {}).get("imports", []):
            if k not in seen and k in man:
                seen.add(k)
                out.append(url_for("static", filename="dist/" + man[k]["file"]))
                walk(k)
    walk(entry)
    return out

@app.context_processor
def _static_ctx():
    return {"static_v": _static_v, "dist_entry": _dist_entry, "dist_preloads": _dist_preloads}

def _csrf_token():
    """توكن CSRF للجلسة، يُنشأ عند أول حاجة. `react_page` تحتاجه **قبل** أن تعمل
    معالجات السياق (تبني حمولة `BY.csrf` ثم ترسم) — فلو اكتفينا بإنشائه في
    المعالج لخرجت الصفحة بتوكن فارغ في كل جلسة فارغة: زائر جديد يفتح /login
    أو /register مباشرة، وبعد الخروج، وبعد الاسترجاع — فيُرفض أول إرسال بـ 400."""
    if "_csrf" not in session:
        session["_csrf"] = _secrets.token_hex(16)
    return session["_csrf"]

@app.context_processor
def _csrf_ctx():
    tok = _csrf_token()
    return {"csrf_token": tok,
            "csrf_field": lambda: Markup(f'<input type="hidden" name="csrf_token" value="{tok}">')}

# اسم المستخدم: حروف لاتينية/عربية وأرقام و `_ . -` فقط، 3–32 حرفاً.
# ليس تجميلاً: الاسم يُعرض للأدمن في «المستخدمون» ويُحقن في حمولة الصفحة،
# فحصره في محارف آمنة يغلق باب إساءة الاستخدام من أصله بدل الاعتماد على
# طبقة الهروب وحدها (راجع REVIEW.md §1 و§4.2).
# الحرف العربي من الحروف الأساسية (U+0620–U+064A) والأرقام العربية الهندية والحروف
# الموسّعة (فارسي/أردو) فقط — لا الكتلة كاملة (U+0600–U+06FF)، لأنها تضم محارف
# تنسيق غير مرئية (U+061C علامة الاتجاه، U+0600–U+0605، U+06DD) والتشكيل؛
# بها يصنع مهاجم اسماً يطابق «admin» بصرياً في قائمة الأدمن.
USERNAME_RE = _re.compile(r"^[A-Za-z0-9_.\-ؠ-ي٠-٩ٱ-ۓ]{3,32}\Z")

# إيميل واحد عادي: لا مسافات ولا أقواس ولا فواصل (عنوان واحد لا قائمة)، ونطاق ASCII.
EMAIL_RE = _re.compile(r"^(?=.{6,254}\Z)[^@\s<>\"',;]{1,64}@[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,24}\Z")

def _norm_email(v):
    return (v or "").strip().lower()

def _pw_stamp(pw_hash):
    """بصمة كلمة المرور المحفوظة في الجلسة. HMAC بمفتاح الخادم لأن كوكي الجلسة
    موقَّع لا مشفَّر — يُقرأ ولا يُزوَّر، فلا نضع فيه مشتقاً خاماً من التجزئة."""
    return hmac.new(app.secret_key.encode(), (pw_hash or "").encode(),
                    hashlib.sha256).hexdigest()[:24]

_last_prune = 0
_bucket_window = {}    # bucket -> window: كل دلو يُنظَّف بنافذته هو لا بنافذة من استدعى

def _prune_attempts(now):
    """يحذف المدخلات المنتهية. بدونه ينمو القاموس مع كل IP جديد بلا حدّ —
    تسريب ذاكرة بطيء في عملية طويلة العمر. التنظيف كل دقيقة على الأكثر.
    `list(...)` لقطة ذرّية: gunicorn يشغّل 4 خيوط، والمرور على القاموس مباشرة
    بينما يضيف خيط آخر مدخلاً يرمي RuntimeError فيسقط طلب الدخول بـ 500."""
    global _last_prune
    if now - _last_prune < 60:
        return
    _last_prune = now
    for k, (_, first) in list(_login_attempts.items()):
        if now - first > _bucket_window.get(k[0], 300):
            _login_attempts.pop(k, None)

def _rate_limited(ip, limit=8, window=300, bucket="login"):
    """محدِّد بسيط لكل (نافذة، IP، غرض). `bucket` يفصل العدّادات حتى لا تستهلك
    محاولات التسجيل رصيد الدخول أو العكس.

    ملاحظة: العدّاد في ذاكرة العملية، فمع أكثر من worker يتضاعف الحدّ الفعلي.
    `limit_req` في nginx هو الحاجز الخارجي المكمّل."""
    now = int(_time.time())
    _bucket_window[bucket] = window
    _prune_attempts(now)
    key = (bucket, ip)
    cnt, first = _login_attempts.get(key, (0, now))
    if now - first > window:
        cnt, first = 0, now
    cnt += 1
    _login_attempts[key] = (cnt, first)
    return cnt > limit

# حدّ التسجيل لكل IP في 10 دقائق — مكان واحد لأنه مطبَّق على مسارين (النموذج
# العادي ومسار جوجل/فيسبوك).
#
# ⚠️ لماذا 20 لا 5: شبكات الموبايل المصرية تستخدم CGNAT، فمئات المستخدمين خلف
# IP واحد. بحدّ 5 تكفي خمسة تسجيلات من فودافون لتُغلق الصفحة أمام الباقين —
# وفي ذروة حملة إعلانية هذا يعني دفع ثمن نقرات ثم رفض أصحابها. خطر إساءة
# الاستخدام هنا محدود: التسجيل لا يكلّف المنصة مالاً، والبريد يُؤكَّد لاحقاً،
# و`limit_req` في nginx هو الحاجز الخارجي ضد الإغراق الآلي.
_REG_LIMIT, _REG_WINDOW = 20, 600

def login_required(f):
    @functools.wraps(f)
    def w(*a, **k):
        if not session.get("uid"): return redirect(url_for("login"))
        return f(*a, **k)
    return w

def uid(): return session.get("uid")

def current_role():
    """الدور الحقيقي من القاعدة (يملؤه `_revalidate_identity`)، والجلسة احتياطياً."""
    u = getattr(g, "user", None)
    return u["role"] if u else session.get("role", "user")

def require_roles(*roles):
    from functools import wraps
    def deco(f):
        @wraps(f)
        def w(*a, **k):
            if not uid(): return redirect(url_for("login"))
            if current_role() not in roles: abort(403)
            return f(*a, **k)
        return w
    return deco


def sync_bot_telegram(bot_row):
    """يهيّئ بروفايل البوت رسمياً على تليجرام من إعداداته. best-effort."""
    try:
        cfg = json.loads(bot_row["config_json"] or "{}")
    except Exception:
        cfg = {}
    prof = tg.build_profile_from_config(cfg, bot_row["template"])
    res = tg.configure_bot_profile(bot_row["token"], **prof)
    # صورة لم تصل بعد (فشل سابق أو توكن جديد) تُعاد مع كل مزامنة حتى تنجح — والناجحة لا تُرفع
    # ثانيةً مع كل حفظ للإعدادات (تليجرام لا يعيد استخدام الصور، فكل رفع ملف جديد)
    if cfg.get("bot_photo") and not (cfg.get("bot_photo_sync") or {}).get("ok"):
        _push_bot_photo(bot_row, cfg)
    cfg["tg_synced_at"] = int(_time.time())
    cfg["tg_sync_ok"] = bool(res.get("ok"))
    cfg["tg_sync_errors"] = res.get("errors", [])
    db.update_bot_config(bot_row["id"], cfg)
    return res

# حقول المنصة التي يجوز أن تصل متصفح أي مستخدم: وسائل الدفع والتواصل فقط.
# `all_platform()` فيها توكن بوت المنصة وسرّ واتساب ومفتاح الـ AI — لا تُمرَّر لصفحة عميل أبداً.
_PUBLIC_PLAT = ("vodafone_number", "instapay_handle", "instapay_link", "bank_holder",
                "bank_name", "bank_account", "bank_iban",
                "support_email", "support_whatsapp", "support_telegram")

def _public_plat():
    p = db.all_platform()
    return {k: p.get(k, "") for k in _PUBLIC_PLAT}

def notify_admins(text):
    """إشعار كل الأدمنز على تليجرام بأي حركة (best-effort)."""
    try:
        for aid in db.admin_chat_ids():
            manager.notify_text(aid, text)
    except Exception:
        pass

_err_notified = {}    # (نوع الخطأ، المسار) -> آخر إشعار

@app.errorhandler(InternalServerError)
def _on_server_error(e):
    """Flask سجّل الـtraceback كاملاً قبل الوصول هنا (`log_exception` → ملف السجل).
    هنا يُشعَر الأدمن على تليجرام — مرة لكل (نوع الخطأ، المسار) كل 10 دقائق،
    حتى لا يُغرق عطلٌ متكرر تليجرام بمئات الرسائل. الاستجابة نفسها لا تتغيّر."""
    orig = getattr(e, "original_exception", None) or e
    key = (type(orig).__name__, request.endpoint)
    now = _time.time()
    if now - _err_notified.get(key, 0) > 600:
        _err_notified[key] = now
        notify_admins(f"🔥 خطأ في الخادم / Server error\n{request.method} {request.path}\n"
                      f"{type(orig).__name__}: {str(orig)[:300]}")
    return e

@app.context_processor
def inject():
    lang = session.get("lang", i18n.DEFAULT)
    return {"brand": "BotYalla", "templates_meta": T.TEMPLATES,
            "username": session.get("uname"),
            "lang": lang, "dir": i18n.dir_for(lang), "langs": i18n.LANGS,
            "t": lambda k: i18n.t(k, lang), "icon": icon,
            "tmpl_label": lambda key: i18n.t({"flow":"tmpl_flow","store":"tmpl_store","booking":"tmpl_booking","customer_service":"tmpl_cs","faq":"tmpl_faq","feedback":"tmpl_feedback","support":"tmpl_support"}.get(key,"tmpl_flow"), lang),
            "tmpl_icon": lambda key: {"flow":"flow","store":"store","booking":"calendar","customer_service":"phone","faq":"grid","feedback":"sparkles","support":"shield"}.get(key,"bot"),
            "role": current_role(),
            "fmt_date": lambda ts: (_dt.datetime.fromtimestamp(int(ts)).strftime("%Y-%m-%d") if ts else "—"),
            "days_left": lambda ts: (max(0, int((int(ts) - _time.time()) // 86400)) if ts else 0)}

@app.route("/lang/<code>")
def set_lang(code):
    if code in i18n.LANGS:
        session["lang"] = code
        # ثبّت التفضيل للمستخدم ليصله التذكير بلغته لا بالعربية دائماً
        if session.get("uid"):
            db.set_setting(session["uid"], "lang", code)
    ref = request.referrer or ""
    # حماية من Open Redirect: ارجع فقط لمسار داخلي
    if ref.startswith(request.host_url):
        return redirect(ref)
    return redirect(url_for("dashboard") if session.get("uid") else url_for("home"))

# ---------- المصادقة ----------
def _oauth_on(provider):
    c = _OAUTH.get(provider)
    return bool(c and os.getenv(c["id"], "").strip() and os.getenv(c["secret"], "").strip()
                and _public_url("home"))

def _auth_props(**kw):
    """حمولة صفحات الدخول والتسجيل: أزرار جوجل/فيسبوك (المفعّلة فقط) وقائمة الدول."""
    return dict({"oauth": {p: _oauth_on(p) for p in _OAUTH},
                 "countries": [list(c) for c in ACC.COUNTRIES]}, **kw)

_SIGNUP_FIELDS = ("username", "email", "phone", "phone_cc", "age", "entity_type")

def _signup_check(f, lang, need_password=True, locked_email=None):
    """يفحص نموذج التسجيل (العادي أو إكمال جوجل/فيسبوك) بسياسات accounts.py.
    يرجّع (بيانات مُطبَّعة، {الحقل: رسالة الخطأ})."""
    errs = {}
    u = f.get("username", "").strip()
    k = ACC.username_problem(u) or ("u_taken" if db.username_taken(u) else None)
    if k:
        errs["username"] = ACC.msg(k, lang)
    email = locked_email or _norm_email(f.get("email", ""))
    if not email:
        errs["email"] = ACC.msg("email_req", lang)
    elif not EMAIL_RE.match(email):
        errs["email"] = ACC.msg("email_bad", lang)
    elif db.get_user_by_email(email):
        errs["email"] = ACC.msg("email_taken", lang)
    phone = ACC.normalize_phone(f.get("phone_cc", "+20"), f.get("phone", ""))
    if not phone:
        errs["phone"] = ACC.msg("phone_bad", lang)
    elif db.phone_taken(phone):
        errs["phone"] = ACC.msg("phone_taken", lang)
    age, ak = ACC.parse_age(f.get("age"))
    if ak:
        errs["age"] = ACC.msg(ak, lang)
    entity = f.get("entity_type", "")
    if entity not in ACC.ENTITIES:
        errs["entity_type"] = ACC.msg("entity_bad", lang)
    pw = f.get("password", "")
    if need_password:
        probs = ACC.password_problems(pw, u, email or "")
        if probs:
            errs["password"] = ACC.msg(probs[0], lang)
        elif pw != f.get("password2", ""):
            errs["password2"] = ACC.msg("p_match", lang)
    if f.get("terms") != "1":
        errs["terms"] = ACC.msg("terms_req", lang)
    return {"username": u, "email": email, "phone": phone, "age": age,
            "entity_type": entity, "password": pw}, errs

def _signup_failed(view, title, errs, extra=None):
    flash(next(iter(errs.values())), "error")
    vals = {k: request.form.get(k, "") for k in _SIGNUP_FIELDS}
    return react_page(view, title, _auth_props(errors=errs, values=vals, **(extra or {})))

def _finish_signup(user_id, d, lang, news):
    """بعد إنشاء الحساب (عادي أو بجوجل/فيسبوك): الجلسة، التتبّع، الإحالة، التنبيه، البريد."""
    db.track("signup", user_id)
    db.set_setting(user_id, "terms_at", str(int(_time.time())))
    # أخبار وعروض بالبريد: موافقة صريحة فقط — المربع غير محدد افتراضياً
    if news and d["email"]:
        db.set_email_news(user_id, True)
    src = session.pop("src", None)           # أول مصدر وصل منه (_count_view)
    if src:
        db.set_setting(user_id, "signup_src", src)
    urow = db.get_user(user_id)
    session["uid"] = user_id; session["uname"] = urow["username"]; session["role"] = urow["role"]
    session["pwv"] = _pw_stamp(urow["pw_hash"])
    ref_code = session.pop("ref", None)      # التُقط من ?ref= على أي صفحة
    if ref_code:
        db.attach_referral(user_id, ref_code)
    # حدث التحويل الأساسي للإعلانات. يُطلق على الصفحة التالية لأن كل مسارات
    # التسجيل تنتهي بـ redirect (اللوحة أو تأكيد البريد).
    AN.queue(session, "sign_up", method=("social" if d.get("oauth") else "password"),
             src=src or None)
    notify_admins(f"🆕 تسجيل مستخدم جديد / New user: {urow['username']} (#{user_id})"
                  + (f" — عبر إحالة {ref_code}" if ref_code else ""))
    if db.email_gate(urow):
        _send_verify(urow, lang)
        return redirect(url_for("verify_email"))
    # بلا تأكيد إجباري (بريد أكّده جوجل، أو SMTP غير مضبوط): الترحيب فوراً. الرابط من
    # `PUBLIC_URL` وحدها، وبدونه تُرسل بلا زرّ — الرسالة لا تحمل توكناً.
    mailer.send_welcome(user_id, d["email"], urow["username"], _public_url("dashboard"), lang)
    return redirect(url_for("dashboard"))

@app.route("/register", methods=["GET", "POST"])
def register():
    lang = session.get("lang", i18n.DEFAULT)
    if request.method == "POST":
        # التسجيل مُحدَّد كالدخول: بدونه يمكن إغراق المنصة بحسابات آلياً.
        if _rate_limited(request.remote_addr or "?", limit=_REG_LIMIT, window=_REG_WINDOW, bucket="register"):
            flash("محاولات كثيرة. انتظر قليلاً." if lang != "en" else "Too many attempts. Please wait.", "error")
            return react_page("register", "register", _auth_props())
        d, errs = _signup_check(request.form, lang)
        if not errs:
            # التأكيد إجباري للحسابات الجديدة — إلا لو SMTP غير مضبوط: لا كود سيصل،
            # وقفل الحساب عندها يُضيع العميل بلا أي مكسب.
            need = mailer.configured()
            if not need:
                log.warning("signup without email verification: SMTP is not configured")
            user_id, err = db.create_account(d["username"], auth.hash_password(d["password"]), d["email"],
                                              d["phone"], d["age"], d["entity_type"], verify_required=need)
            if not err:
                return _finish_signup(user_id, d, lang, request.form.get("email_news") == "1")
            errs[{"email_taken": "email", "phone_taken": "phone"}.get(err, "username")] = ACC.msg(err, lang)
        return _signup_failed("register", "register", errs)
    return react_page("register", "register", _auth_props())

@app.route("/api/check-username")
def api_check_username():
    """فحص حيّ لاسم المستخدم أثناء الكتابة: القواعد + التفرّد + اقتراحات لو مأخوذ."""
    lang = session.get("lang", i18n.DEFAULT)
    if _rate_limited(request.remote_addr or "?", limit=60, window=300, bucket="u_check"):
        return jsonify({"ok": False, "error": i18n.t("ai_rate", lang)}), 429
    u = request.args.get("u", "").strip()[:40]
    k = ACC.username_problem(u)
    if not k and db.username_taken(u, exclude_id=uid()):
        k = "u_taken"
    out = {"ok": not k, "error": ACC.msg(k, lang) if k else None}
    if k in ("u_taken", "u_reserved"):
        out["suggestions"] = [c for c in ACC.username_candidates(u) if not db.username_taken(c)][:3]
    return jsonify(out)

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        if _rate_limited(request.remote_addr or "?"):
            flash("محاولات كثيرة. انتظر قليلاً." if session.get("lang")!="en" else "Too many attempts. Please wait.", "error")
            return react_page("login", "login", _auth_props())
        u = request.form.get("username", "").strip()
        p = request.form.get("password", "")
        row = db.get_user_by_login(u)            # اسم المستخدم أو البريد
        if row and row.get("is_blocked"):
            flash("تم حظر هذا الحساب." if session.get("lang")!="en" else "This account is blocked.", "error")
            return react_page("login", "login", _auth_props())
        if row and auth.verify_password(p, row["pw_hash"]):
            session["uid"] = row["id"]; session["uname"] = row["username"]; session["role"] = row.get("role","user")
            session["pwv"] = _pw_stamp(row["pw_hash"])
            return redirect(url_for("dashboard"))
        flash("بيانات دخول غير صحيحة." if session.get("lang") != "en" else "Wrong login details.", "error")
    return react_page("login", "login", _auth_props())

@app.route("/logout", methods=["POST"])
def logout():
    """POST فقط (يمرّ بفحص CSRF): بـ GET كان أي موقع يُخرج زائرك بـ <img src=".../logout">."""
    session.clear(); return redirect(url_for("login"))

# ---------- تأكيد البريد: كود من 6 أرقام + رابط بضغطة ----------
VERIFY_TTL = 3600         # الكود والرابط صالحان ساعة
RESEND_GAP = 60           # ثانية بين إرسالين

def _code_hash(user_id, code):
    """الكود لا يُخزَّن — HMAC مربوط بالمستخدم فلا يصلح كود مستخدم لغيره."""
    return hmac.new(app.secret_key.encode(), f"ev:{user_id}:{code}".encode(), hashlib.sha256).hexdigest()

def _send_verify(u, lang=None):
    """كود جديد + رابط يستبدلان أي سابق. الرابط من PUBLIC_URL وحدها (§14) — وبدونها الكود وحده."""
    code = f"{_secrets.randbelow(1000000):06d}"
    tok = _secrets.token_urlsafe(32)
    db.start_email_verification(u["id"], u["email"], _code_hash(u["id"], code), _token_hash(tok), VERIFY_TTL)
    mailer.send_async(u["email"], *mailer.verify_email(
        code, _public_url("verify_email_link", token=tok), lang or db.user_lang(u["id"]), VERIFY_TTL // 60))
    log.info("email verification sent user=%s", u["id"])

def _after_verified(u, lang):
    # الحساب الجديد يصله الترحيب بعد التأكيد لا قبله — رسالة واحدة في كل خطوة
    if u.get("verify_required") and u.get("email"):
        mailer.send_welcome(u["id"], u["email"], u["username"], _public_url("dashboard"), lang)
    log.info("email verified user=%s", u["id"])

def _vmsg(key, lang):
    return {"ok": ("✅ تم تأكيد بريدك — أهلاً بك في BotYalla!", "✅ Email verified — welcome to BotYalla!"),
            "bad": ("الكود غير صحيح — راجع الأرقام وجرّب تاني.", "That code isn't right — check the digits and try again."),
            "locked": ("محاولات كثيرة بكود خاطئ — اطلب كوداً جديداً.", "Too many wrong tries — request a new code."),
            "expired": ("الكود انتهى أو اتغيّر — اطلب كوداً جديداً.", "The code expired or was replaced — request a new one."),
            "sent": ("بعتنا كوداً جديداً على بريدك.", "We sent a new code to your email."),
            "wait": ("استنى دقيقة قبل ما تطلب كوداً تاني.", "Wait a minute before asking for another code."),
            "nosmtp": ("إرسال البريد متوقف مؤقتاً — كلّم الدعم.", "Email sending is paused — contact support."),
            "link_bad": ("رابط التأكيد انتهى أو اتستخدم — اطلب كوداً جديداً.", "That link expired or was used — request a new code."),
            }[key][1 if lang == "en" else 0]

@app.route("/verify-email", methods=["GET", "POST"])
@login_required
def verify_email():
    lang = session.get("lang", i18n.DEFAULT)
    u = db.get_user(uid())
    if not u.get("email"):
        flash(i18n.t("email_prompt", lang), "error")
        return redirect(url_for("account"))
    if u.get("email_verified_at"):
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        if _rate_limited(f"u{uid()}", limit=10, window=900, bucket="ev_code"):
            flash(_vmsg("locked", lang), "error")
            return redirect(url_for("verify_email"))
        code = _re.sub(r"\D", "", request.form.get("code", "").translate(ACC._DIGITS))[:6]
        res = db.check_email_code(uid(), _code_hash(uid(), code))
        if res == "ok":
            _after_verified(u, lang)
            flash(_vmsg("ok", lang), "ok")
            return redirect(url_for("dashboard"))
        flash(_vmsg(res, lang), "error")
        return redirect(url_for("verify_email"))
    ev = db.email_verification(uid())
    now = int(_time.time())
    return react_page("verify_email", "verify_title", {
        "email": u["email"], "sent": bool(ev and ev["expires_at"] > now),
        "wait": max(0, RESEND_GAP - (now - ev["sent_at"])) if ev else 0,
        "gated": db.email_gate(u)})

@app.route("/verify-email/resend", methods=["POST"])
@login_required
def verify_email_resend():
    lang = session.get("lang", i18n.DEFAULT)
    u = db.get_user(uid())
    if u.get("email_verified_at") or not u.get("email"):
        return redirect(url_for("account"))
    ev = db.email_verification(uid())
    if ev and _time.time() - ev["sent_at"] < RESEND_GAP:
        flash(_vmsg("wait", lang), "error")
    elif not mailer.configured():
        flash(_vmsg("nosmtp", lang), "error")
    elif _rate_limited(f"u{uid()}", limit=5, window=3600, bucket="ev_send"):
        flash(_vmsg("wait", lang), "error")
    else:
        _send_verify(u, lang)
        flash(_vmsg("sent", lang), "ok")
    return redirect(url_for("verify_email"))

@app.route("/verify-email/change", methods=["POST"])
@login_required
def verify_email_change():
    """بريد كُتب غلطاً وقت التسجيل: يُصحَّح هنا (بكلمة المرور) ويصله كود جديد."""
    lang = session.get("lang", i18n.DEFAULT)
    u = db.get_user(uid())
    email = _norm_email(request.form.get("email", ""))
    if not auth.verify_password(request.form.get("password", ""), u["pw_hash"]):
        flash("كلمة المرور غير صحيحة." if lang != "en" else "Wrong password.", "error")
    elif not EMAIL_RE.match(email):
        flash(ACC.msg("email_bad", lang), "error")
    else:
        other = db.get_user_by_email(email)
        ok = not (other and other["id"] != u["id"]) and db.set_user_email(uid(), email)[0]
        if not ok:
            flash(ACC.msg("email_taken", lang), "error")
        elif mailer.configured() and not _rate_limited(f"u{uid()}", limit=5, window=3600, bucket="ev_send"):
            _send_verify(db.get_user(uid()), lang)
            flash(_vmsg("sent", lang), "ok")
    return redirect(url_for("verify_email"))

@app.route("/verify-email/t/<token>")
def verify_email_link(token):
    """الزر في رسالة التأكيد — يعمل حتى بلا جلسة (فُتح على جهاز آخر)."""
    lang = session.get("lang", i18n.DEFAULT)
    if _rate_limited(request.remote_addr or "?", limit=20, window=600, bucket="ev_link"):
        abort(429)
    user_id = db.confirm_email_token(_token_hash(token))
    if not user_id:
        flash(_vmsg("link_bad", lang), "error")
        resp = redirect(url_for("verify_email") if session.get("uid") else url_for("login"))
    else:
        _after_verified(db.get_user(user_id), lang)
        flash(_vmsg("ok", lang), "ok")
        resp = redirect(url_for("dashboard") if session.get("uid") == user_id else url_for("login"))
    resp.headers["Referrer-Policy"] = "no-referrer"
    return resp

# ---------- الدخول بجوجل وفيسبوك (OAuth 2.0 — مكتبة Python القياسية، بلا تبعيات) ----------
# المفاتيح في .env: GOOGLE_CLIENT_ID/SECRET · FACEBOOK_APP_ID/SECRET. بلا مفاتيح لا يظهر الزر.
# عنوان الرجوع من PUBLIC_URL وحدها: {PUBLIC_URL}/auth/<provider>/callback (§14).
_OAUTH = {
    "google": {"auth": "https://accounts.google.com/o/oauth2/v2/auth",
               "token": "https://oauth2.googleapis.com/token",
               "me": "https://openidconnect.googleapis.com/v1/userinfo",
               "scope": "openid email profile", "id": "GOOGLE_CLIENT_ID", "secret": "GOOGLE_CLIENT_SECRET"},
    "facebook": {"auth": "https://www.facebook.com/v19.0/dialog/oauth",
                 "token": "https://graph.facebook.com/v19.0/oauth/access_token",
                 "me": "https://graph.facebook.com/v19.0/me?fields=id,name,email",
                 "scope": "email,public_profile", "id": "FACEBOOK_APP_ID", "secret": "FACEBOOK_APP_SECRET"},
}
_OAUTH_NAME = {"google": ("جوجل", "Google"), "facebook": ("فيسبوك", "Facebook")}

def _http_json(url, data=None, headers=None):
    req = _ureq.Request(url, data=_up.urlencode(data).encode() if data else None,
                        headers={"Accept": "application/json", **(headers or {})})
    with _ureq.urlopen(req, timeout=10) as r:
        return json.loads(r.read().decode("utf-8"))

def _oauth_profile(provider, code, verifier):
    """code ⇒ {sub, email, email_verified, name}. يرمي عند أي فشل — المستدعي يعالج."""
    c = _OAUTH[provider]
    data = {"client_id": os.getenv(c["id"], ""), "client_secret": os.getenv(c["secret"], ""), "code": code,
            "redirect_uri": _public_url("oauth_callback", provider=provider)}
    if provider == "google":
        data.update(grant_type="authorization_code", code_verifier=verifier)
    at = _http_json(c["token"], data).get("access_token")
    if not at:
        raise ValueError("no access token")
    me = _http_json(c["me"], headers={"Authorization": f"Bearer {at}"})
    if provider == "google":
        return {"sub": str(me["sub"]), "email": _norm_email(me.get("email")),
                "email_verified": bool(me.get("email_verified")), "name": me.get("name") or ""}
    # فيسبوك لا يرجّع إلا البريد الأساسي المؤكَّد — وقد لا يرجّع بريداً أصلاً (حساب بالهاتف)
    return {"sub": str(me["id"]), "email": _norm_email(me.get("email")),
            "email_verified": bool(me.get("email")), "name": me.get("name") or ""}

def _oauth_login(u, lang):
    if not u or u.get("is_blocked"):
        flash("تم حظر هذا الحساب." if lang != "en" else "This account is blocked.", "error")
        return redirect(url_for("login"))
    session["uid"] = u["id"]; session["uname"] = u["username"]; session["role"] = u.get("role", "user")
    session["pwv"] = _pw_stamp(u["pw_hash"])
    return redirect(url_for("dashboard"))

@app.route("/auth/<any(google,facebook):provider>")
def oauth_start(provider):
    lang = session.get("lang", i18n.DEFAULT)
    back = url_for("account") if session.get("uid") else url_for("login")
    if not _oauth_on(provider):
        flash("الدخول بهذه الطريقة غير مفعّل حالياً." if lang != "en" else "This sign-in option isn't enabled.", "error")
        return redirect(back)
    if _rate_limited(request.remote_addr or "?", limit=20, window=600, bucket="oauth"):
        flash(i18n.t("ai_rate", lang), "error")
        return redirect(back)
    c = _OAUTH[provider]
    state, verifier = _secrets.token_urlsafe(24), _secrets.token_urlsafe(48)
    session["oauth"] = {"p": provider, "state": state, "v": verifier, "t": int(_time.time()),
                        "link": bool(session.get("uid")) and request.args.get("link") == "1"}
    q = {"client_id": os.getenv(c["id"], ""), "redirect_uri": _public_url("oauth_callback", provider=provider),
         "response_type": "code", "scope": c["scope"], "state": state}
    if provider == "google":
        q.update(code_challenge=base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
                 .rstrip(b"=").decode(), code_challenge_method="S256", prompt="select_account")
    return redirect(c["auth"] + "?" + _up.urlencode(q))

@app.route("/auth/<any(google,facebook):provider>/callback")
def oauth_callback(provider):
    """الرجوع من جوجل/فيسبوك. الأمان: state + PKCE (جوجل) + مهلة 10 دقائق، والربط التلقائي
    بحساب قائم **فقط** لو بريده مؤكَّد عندنا وعند المزوّد — وإلا يسرق من سجّل حساباً ببريد
    غيره (بلا تأكيد) حساب صاحب البريد الحقيقي حين يدخل بجوجل (pre-account takeover)."""
    lang = session.get("lang", i18n.DEFAULT)
    name = _OAUTH_NAME[provider][1 if lang == "en" else 0]
    st = session.pop("oauth", None) or {}
    back = url_for("account") if st.get("link") else url_for("login")

    def fail():
        flash(f"تعذّر الدخول بـ{name} — جرّب تاني." if lang != "en" else f"Couldn't sign in with {name} — try again.",
              "error")
        return redirect(back)

    got = request.args.get("state", "")
    if (st.get("p") != provider or not got or not _secrets.compare_digest(str(st.get("state", "")), got)
            or _time.time() - st.get("t", 0) > 600 or not request.args.get("code")):
        return fail()
    if _rate_limited(request.remote_addr or "?", limit=20, window=600, bucket="oauth"):
        return fail()
    try:
        prof = _oauth_profile(provider, request.args["code"], st.get("v"))
    except Exception:
        log.warning("oauth %s exchange failed", provider, exc_info=True)
        return fail()
    ident = db.get_identity(provider, prof["sub"])
    if st.get("link") and session.get("uid"):                      # ربط من «حسابي»
        if ident and ident["user_id"] != uid():
            flash(f"حساب {name} ده مربوط بحساب BotYalla تاني." if lang != "en"
                  else f"That {name} account is linked to another BotYalla account.", "error")
        else:
            db.add_identity(provider, prof["sub"], uid(), prof["email"])
            db.set_setting(uid(), f"oauth_off_{provider}", "0")          # ربط صريح يلغي «فكّيته»
            flash(f"✅ اتربط {name} بحسابك — تقدر تدخل بيه من دلوقتي." if lang != "en"
                  else f"✅ {name} is linked — you can sign in with it now.", "ok")
        return redirect(url_for("account"))
    if ident:
        return _oauth_login(db.get_user(ident["user_id"]), lang)
    if prof["email"]:
        ex = db.get_user_by_email(prof["email"])
        if ex:
            # ومن فكّ الربط بنفسه لا يُعاد ربطه بصمت بالبريد — يربط صراحةً من «حسابي»
            if (ex.get("email_verified_at") and prof["email_verified"]
                    and db.get_setting(ex["id"], f"oauth_off_{provider}") != "1"):
                db.add_identity(provider, prof["sub"], ex["id"], prof["email"])
                return _oauth_login(ex, lang)
            flash(f"فيه حساب بالبريد ده — ادخل بكلمة المرور وأكّد بريدك، وبعدين اربط {name} من «حسابي»."
                  if lang != "en" else
                  f"An account already uses this email — sign in with your password, verify your email, "
                  f"then link {name} from your account page.", "error")
            return redirect(url_for("login"))
    session["oauth_new"] = {"p": provider, "sub": prof["sub"], "name": prof["name"][:60],
                            "email": prof["email"] if prof["email_verified"] else "", "t": int(_time.time())}
    return redirect(url_for("register_complete"))

@app.route("/register/complete", methods=["GET", "POST"])
def register_complete():
    """حساب جديد بجوجل/فيسبوك: البريد (إن أكّده المزوّد) جاهز، والباقي يكمله العميل هنا."""
    lang = session.get("lang", i18n.DEFAULT)
    pend = session.get("oauth_new")
    if not pend or _time.time() - pend.get("t", 0) > 1800:
        session.pop("oauth_new", None)
        flash("انتهت الجلسة — ابدأ التسجيل من جديد." if lang != "en" else "Session expired — start again.", "error")
        return redirect(url_for("register"))
    view = {"provider": pend["p"], "email": pend["email"], "name": pend["name"]}
    if request.method == "POST":
        if _rate_limited(request.remote_addr or "?", limit=_REG_LIMIT, window=_REG_WINDOW, bucket="register"):
            flash("محاولات كثيرة. انتظر قليلاً." if lang != "en" else "Too many attempts. Please wait.", "error")
            return redirect(url_for("register_complete"))
        ident = db.get_identity(pend["p"], pend["sub"])
        if ident:                                                   # إرسال مزدوج
            session.pop("oauth_new", None)
            return _oauth_login(db.get_user(ident["user_id"]), lang)
        d, errs = _signup_check(request.form, lang, need_password=False, locked_email=pend["email"] or None)
        if not errs:
            verified = bool(pend["email"])
            user_id, err = db.create_account(
                d["username"], auth.hash_password(_secrets.token_urlsafe(32)), d["email"], d["phone"], d["age"],
                d["entity_type"], verify_required=not verified and mailer.configured(), email_verified=verified)
            if not err:
                db.add_identity(pend["p"], pend["sub"], user_id, d["email"])
                db.set_setting(user_id, "pw_set", "0")      # بلا كلمة مرور — يضبطها بـ«نسيت كلمة المرور»
                d["oauth"] = pend["p"]                      # لتمييز مصدر التسجيل في حدث القياس
                session.pop("oauth_new", None)
                return _finish_signup(user_id, d, lang, request.form.get("email_news") == "1")
            errs[{"email_taken": "email", "phone_taken": "phone"}.get(err, "username")] = ACC.msg(err, lang)
        return _signup_failed("complete_profile", "complete_title", errs, {"pending": view})
    base = pend["name"] or pend["email"].split("@")[0]
    return react_page("complete_profile", "complete_title", _auth_props(
        pending=view, suggestions=[c for c in ACC.username_candidates(base) if not db.username_taken(c)][:3]))

# ---------- إلغاء اشتراك البريد (أخبار وعروض) ----------
@app.route("/email/unsubscribe/<int:user_id>/<token>", methods=["GET", "POST"])
def email_unsubscribe(user_id, token):
    """رابط الإلغاء في كل رسالة أخبار. GET يعرض صفحة بزرّ — ماسحات الروابط في برامج البريد
    تفتح الروابط تلقائياً، فالفتح وحده لا يلغي شيئاً. POST يلغي: من زرّ الصفحة، أو من
    Gmail/Yahoo مباشرة (List-Unsubscribe=One-Click, RFC 8058). مستثنى من CSRF: التوكن
    (HMAC لكل مستخدم) هو الحارس، ولا يغيّر إلا تفضيل الأخبار لصاحبه."""
    if not mailer.check_unsub(user_id, token) or not db.get_user(user_id):
        abort(404)
    if request.method == "POST":
        if _rate_limited(request.remote_addr or "?", limit=30, window=3600, bucket="unsub"):
            abort(429)
        on = request.form.get("on") == "1"
        db.set_email_news(user_id, on)
        log.info("email news %s for user=%s", "on" if on else "off", user_id)
        if request.form.get("List-Unsubscribe") == "One-Click":
            return "", 200
        return redirect(url_for("email_unsubscribe", user_id=user_id, token=token,
                                done="on" if on else "off"))
    return react_page("unsubscribe", "unsub_title",
                      {"on": db.email_news_on(user_id), "done": request.args.get("done", "")[:3]})

# ---------- استرجاع كلمة المرور ----------
RESET_TTL = 3600          # ساعة واحدة، واستخدام مرة واحدة

def _token_hash(tok):
    return hashlib.sha256((tok or "").encode()).hexdigest()

def _public_url(endpoint, **kw):
    """رابط مطلق لأي مسار، مبنيّاً من `PUBLIC_URL` وحدها (AGENTS.md §3.14).
    يرجّع None بلا إعداد — والمستدعي يقرّر: رابط الاسترجاع يُحجب تماماً، ورسالة
    الترحيب تُرسل بلا زرّ لأنها لا تحمل أي سرّ."""
    base = os.getenv("PUBLIC_URL", "").strip().rstrip("/")
    if not base.startswith(("https://", "http://")):
        return None
    return base + url_for(endpoint, **kw)


def _reset_link(token):
    """الرابط يُبنى من `PUBLIC_URL` لا من ترويسة Host. nginx يمرّر Host كما أرسله
    العميل، فلو بُني الرابط منها لطلب مهاجمٌ استرجاعاً لحساب ضحية بـ Host مزوّر،
    فيصلها رابط يسرّب التوكن إلى نطاقه (password-reset poisoning).
    بلا PUBLIC_URL لا يُرسل أي رابط — افشل مغلقاً."""
    return _public_url("reset_password", token=token)

def _send_reset(email, lang):
    u = db.get_user_by_email(email)
    if not u or u.get("is_blocked"):
        return
    tok = _secrets.token_urlsafe(32)
    link = _reset_link(tok)
    if not link:
        log.error("password reset requested but PUBLIC_URL is not set — no link sent")
        return
    db.create_password_reset(u["id"], _token_hash(tok), RESET_TTL)
    ulang = db.get_setting(u["id"], "lang", lang) or lang
    mailer.send_async(email, *mailer.reset_email(link, ulang, RESET_TTL // 60))
    log.info("password reset link issued user=%s", u["id"])

@app.route("/forgot", methods=["GET", "POST"])
def forgot():
    lang = session.get("lang", i18n.DEFAULT)
    if request.method == "POST":
        email = _norm_email(request.form.get("email", ""))
        # كل الفروع تنتهي بنفس الرسالة ونفس التحويل: المسار لا يكشف أبداً هل
        # الإيميل مسجّل (منع تعداد الحسابات). الحدّان: 3 لكل إيميل و10 لكل IP
        # في الساعة — والإرسال نفسه في خيط خلفي فلا يفضح زمنُ الردّ شيئاً.
        if (EMAIL_RE.match(email)
                and not _rate_limited(request.remote_addr or "?", limit=10, window=3600, bucket="reset_ip")
                and not _rate_limited(email, limit=3, window=3600, bucket="reset")):
            _send_reset(email, lang)
        flash(i18n.t("forgot_sent", lang), "ok")
        return redirect(url_for("forgot"))
    return react_page("forgot", "forgot_title")

@app.route("/reset/<token>", methods=["GET", "POST"])
def reset_password(token):
    lang = session.get("lang", i18n.DEFAULT)
    th = _token_hash(token)
    if not db.get_password_reset(th):
        flash(i18n.t("reset_invalid", lang), "error")
        return redirect(url_for("forgot"))
    if request.method == "POST":
        p = request.form.get("password", "")
        owner = db.get_user(db.get_password_reset(th)["user_id"]) or {}
        probs = ACC.password_problems(p, owner.get("username", ""), owner.get("email") or "")
        if probs or p != request.form.get("password2", p):
            flash(ACC.msg(probs[0] if probs else "p_match", lang), "error")
            return redirect(url_for("reset_password", token=token))
        user_id = db.consume_password_reset(th, auth.hash_password(p))
        if not user_id:
            flash(i18n.t("reset_invalid", lang), "error")
            return redirect(url_for("forgot"))
        log.info("password reset completed user=%s", user_id)
        db.set_setting(user_id, "pw_set", "1")      # حساب جوجل/فيسبوك صار له كلمة مرور
        # الجلسات القائمة على أي جهاز تنتهي تلقائياً: بصمة كلمة المرور تغيّرت.
        session.clear()
        session["lang"] = lang
        flash(i18n.t("reset_done", lang), "ok")
        return redirect(url_for("login"))
    resp = make_response(react_page("reset", "reset_title"))
    # التوكن في الرابط: لا يُخزَّن في كاش ولا يُرسل في Referer لأي طرف.
    resp.headers["Cache-Control"] = "no-store"
    resp.headers["Referrer-Policy"] = "no-referrer"
    return resp

# ---------- الرئيسية ----------
@app.route("/dashboard")
@login_required
def dashboard():
    bots = db.list_bots(uid())
    total = {"subscribers": 0, "orders": 0, "leads": 0, "bookings": 0, "revenue": 0}
    for b in bots:
        b["running"] = manager.is_running(b["id"])
        b["stats"] = db.stats_summary(b["id"])
        for k in total: total[k] += b["stats"].get(k, 0)
    total["revenue"] = round(total["revenue"], 2)
    sub = db.get_subscription(uid())
    plan_id = sub["plan"] if sub["status"] == "active" else "free"
    wa_plan = bool(plans.plan(plan_id).get("whatsapp"))
    wa_ok = current_role() in ("admin", "support") or wa_plan
    info = manager.platform_info()
    return react_page("dashboard", "nav_bots",
                      {"bots": [_public_bot(b) for b in bots], "total": total, "waAllowed": wa_ok,
                       # «فريقنا يربط واتساب لك» مشمولة في باقات واتساب — باقة العميل نفسه لا
                       # صلاحية الفريق. `open` = طلبه المفتوح إن وُجد (طلب واحد لكل عميل)
                       "waPlan": wa_plan,
                       "waAssist": {"open": db.open_ticket_of_kind(uid(), "wa_setup") if wa_plan else None},
                       "onboarding": _onboarding(bots),
                       # الإنشاء بضغطة متاح فقط لو بوت المنصة يعمل وفيه «وضع إدارة البوتات»
                       "oneTap": {"available": bool(info.get("username") and info.get("can_manage")),
                                  "platformRunning": manager.platform_running()}})


def _onboarding(bots):
    """حالة البدء لأول بوت — تُحسب في الخادم لأن «هل ضبط الترحيب؟» و«هل جرّبه
    أحد؟» لا تُعرفان من الواجهة (الأولى داخل `config` والثانية عدّ مشتركين).

    تختفي البطاقة من نفسها حين تكتمل الخطوات الثلاث، فلا حاجة لعمود «أخفِ
    الإرشاد» في القاعدة ولا لزرّ تجاهل ينساه المستخدم ثم لا يجد الإرشاد.
    """
    if not bots:
        return {"stage": "first_bot"}          # لا بوت بعد: تُعرض خطوات BotFather
    b = min(bots, key=lambda x: x.get("id") or 0)     # أول بوت أنشأه، لا الأحدث
    try:
        cfg = json.loads(b.get("config_json") or "{}")
    except (ValueError, TypeError):
        cfg = {}
    # دالة خالصة عمداً: لا `url_for` ولا أي شيء يحتاج سياق طلب — فتُختبر وحدها
    # بلا خادم، والواجهة تبني `/bot/{id}` من `botId` كما تفعل في كل مكان آخر.
    steps = [
        {"k": "greeting", "done": _greeting_set(b, cfg)},
        {"k": "run", "done": bool(b.get("running"))},
        {"k": "try", "done": bool((b.get("stats") or {}).get("subscribers"))},
    ]
    if all(x["done"] for x in steps):
        return {"stage": "done"}
    return {"stage": "first_run", "botId": b["id"], "botName": b.get("name"),
            "channel": b.get("channel") or "telegram", "steps": steps,
            # «جرّبه بنفسك» يفتح البوت مباشرة بدل أن يبحث عنه صاحبه في تليجرام
            "botUsername": cfg.get("bot_username") or "",
            # لتقول الواجهة أين تُضبط التحية: «باني المحادثة» لا صفحة الإعدادات
            "flowBot": _is_flow_bot(b, cfg)}


def _is_flow_bot(b, cfg):
    return bool(cfg.get("flow")) or b.get("template") in T.PRESET_FLOWS or b.get("template") == "flow"


def _greeting_set(b, cfg):
    """هل خصّص صاحب البوت رسالة الترحيب؟

    نوعا البوت يحيّيان من مكانين مختلفين: القوالب الثابتة (متجر · حجز…) من
    `welcome`، وبوتات الفلو من `flow.start_message` — ولا تقرأ `welcome` إطلاقاً.
    فحص `welcome` وحده كان يترك بطاقة البدء معلّقة للأبد عند 4 من 7 أنواع.
    والنص الجاهز (قالب الفلو أو الافتراضي) لا يُعدّ تخصيصاً، كما أن الترحيب
    الافتراضي للمتجر لا يُعدّ."""
    if (cfg.get("welcome") or "").strip():
        return True
    sm = ((cfg.get("flow") or {}).get("start_message") or "").strip()
    defaults = {(T.PRESET_FLOWS.get(b.get("template")) or {}).get("start_message", "").strip(),
                (_DEFAULT_FLOW.get("start_message") or "").strip()}
    return bool(sm) and sm not in defaults

def _owned(bot_id):
    b = db.get_bot(bot_id, uid())
    if not b: abort(404)
    return b

def _public_bot(b):
    """نسخة من صفّ البوت صالحة لحمولة الصفحة: توكن تليجرام سرّ تشغيل البوت
    كاملاً فلا يصل للمتصفح (ولا لأي XSS محتمل). `wa:<phone_id>` ليس سراً —
    لوحة واتساب تعرضه — فيبقى."""
    b = dict(b)
    if not str(b.get("token") or "").startswith("wa:"):
        b["token"] = ""
    return b

@app.route("/bot/create", methods=["POST"])
@login_required
def bot_create():
    # التحقق من التوكن ينتظر تليجرام/Meta حتى 15ث داخل الطلب — بلا حدّ تُشغل الخيوط كلها
    if _rate_limited(f"u{uid()}", limit=10, window=3600, bucket="bot_create"):
        flash(i18n.t("ai_rate", session.get("lang", i18n.DEFAULT)), "error")
        return redirect(url_for("dashboard"))
    name = request.form.get("name", "").strip()
    template = request.form.get("template", "")
    channel = request.form.get("channel", "telegram")
    
    info = {}
    if channel == "telegram":
        token = request.form.get("token", "").strip()
        if not (name and token and template in T.TEMPLATES):
            flash("أكمل كل الحقول.", "error"); return redirect(url_for("dashboard"))
        info = tg.validate_token(token)
        if not info["ok"]:
            flash(f"❌ التوكن غير صالح: {info['error']}", "error")
            return redirect(url_for("dashboard"))
    elif channel == "whatsapp":
        phone_id = request.form.get("wa_phone_id", "").strip()
        wa_token = request.form.get("wa_token", "").strip()
        if not (name and phone_id and wa_token and template in T.TEMPLATES):
            flash("أكمل كل الحقول الخاصة بواتساب.", "error"); return redirect(url_for("dashboard"))
        # واتساب مدفوع لكل رسالة — ممنوع على الباقة المجانية
        if current_role() not in ("admin", "support"):
            sub = db.get_subscription(uid())
            plan_id = sub["plan"] if sub["status"] == "active" else "free"
            if not plans.plan(plan_id).get("whatsapp"):
                flash(("واتساب ميزة مدفوعة 🔒 — متاحة في باقة «واتساب» فأعلى. رقّي باقتك لتفعيلها."
                       if session.get("lang") != "en" else
                       "WhatsApp is a paid feature 🔒 — it starts at the «WhatsApp» plan. Upgrade to enable it."),
                      "error")
                return redirect(url_for("pricing"))
        chk = wa_verify(phone_id, wa_token)
        if not chk["ok"]:
            flash(f"❌ بيانات واتساب غير صالحة: {chk['error']}", "error")
            return redirect(url_for("dashboard"))
        token = f"wa:{phone_id}"
        info = {"username": chk.get("number") or phone_id, "name": chk.get("name") or name}
    else:
        abort(400)
    # الأدمن (مالك المنصة) والدعم: صلاحيات غير محدودة — بلا حدود باقات
    if current_role() not in ("admin", "support"):
        sub = db.get_subscription(uid())
        plan_id = sub["plan"] if sub["status"] == "active" else "free"
        maxb = plans.plan(plan_id)["max_bots"]
        if db.count_user_bots(uid()) >= maxb:
            flash(("لقد وصلت للحد الأقصى لباقتك ({} بوت). قم بالترقية لإنشاء المزيد."
                   if session.get("lang")!="en" else
                   "You reached your plan limit ({} bots). Upgrade to create more.").format(maxb), "error")
            return redirect(url_for("pricing"))
    # مصدر واحد لإعدادات البوت الأولى — نفسه في الإنشاء بضغطة (managed_bots)
    cfg = T.initial_config(name, template, info, request.form.get("owner_chat_id", ""))
        
    if channel == "whatsapp":
        cfg["wa_token"] = request.form.get("wa_token", "").strip()
        
    try:
        new_id = db.create_bot(uid(), name, token, template, cfg, channel)
        notify_admins(f"🤖 بوت جديد / New bot: «{name}» (@{info.get('username')}) — {session.get('uname')}")
        # تهيئة رسمية للبوت على تليجرام (إذا كان تليجرام)
        if channel == "telegram":
            try:
                sync_bot_telegram(db.get_bot(new_id))
            except Exception:
                pass
        _uname = info.get('username')
        if channel == "telegram":
            flash((f"تم إنشاء البوت @{_uname} 🎉 وتهيئته رسمياً على تليجرام. اضبط إعداداته ثم شغّله."
                   if session.get("lang") != "en" else
                   f"Bot @{_uname} created 🎉 and officially configured on Telegram. Adjust its settings then start it."), "ok")
        else:
            flash((f"تم إنشاء بوت واتساب «{name}» 🎉 — تأكد أن Webhook في Meta يشير إلى /wh/whatsapp ثم شغّله."
                   if session.get("lang") != "en" else
                   f"WhatsApp bot «{name}» created 🎉 — point the Meta webhook to /wh/whatsapp, then start it."), "ok")
        # ★ لحظة التفعيل الحقيقية. `sign_up` وحده لا يعني شيئاً: مستخدم سجّل ولم
        # ينشئ بوتاً لم يحدث معه شيء. النسبة bot_created/sign_up هي المؤشر الذي
        # يُحكم به على جودة الحملة — لا عدد التسجيلات.
        AN.queue(session, "bot_created", channel=channel, template=template)
        # صفحة البوت نفسها لا اللوحة: فيها رابطه ورمز QR — أول ما يحتاجه صاحبه
        return redirect(url_for("bot_detail", bot_id=new_id, new=1))
    except Exception as e:
        flash((f"خطأ: {e} (قد يكون التوكن مستخدماً بالفعل)."
               if session.get("lang") != "en" else
               f"Error: {e} (the token may already be in use)."), "error")
    return redirect(url_for("dashboard"))

@app.route("/bot/<int:bot_id>")
@login_required
def bot_detail(bot_id):
    b = _owned(bot_id)
    b["config"] = json.loads(b["config_json"] or "{}")
    b["running"] = manager.is_running(bot_id)
    b["stats"] = db.stats_summary(bot_id)
    leads = db.list_leads(bot_id) if b["template"] in ("flow", "customer_service", "feedback", "support") else []
    orders = db.list_orders(bot_id) if b["template"] == "store" else []
    bookings = db.list_bookings(bot_id) if b["template"] == "booking" else []
    # معرّف المحادثة لكل صف — زرّ «محادثة» بجانب العميل يفتح صندوق الوارد عليه
    pfx = "wa:" if (b.get("channel") or "telegram") == "whatsapp" else "tg:"
    for row in leads + orders + bookings:
        row["peer"] = f"{pfx}{row['tg_user_id']}" if row.get("tg_user_id") else ""

    sub = db.get_subscription(uid())
    plan_id = sub["plan"] if sub["status"] == "active" else "free"
    p = plans.plan(plan_id)
    if current_role() in ("admin", "support"):
        # أعلى باقة = وصول كامل. تُقرأ من ORDER ولا تُثبَّت باسم، فإضافة باقة
        # أعلى مستقبلاً لا تترك الأدمن عالقاً على باقة صارت وسطى.
        p = plans.plan(plans.ORDER[-1])

    usage = None
    if (b.get("channel") or "telegram") == "whatsapp":
        limit = None if current_role() in ("admin", "support") else plans.wa_limit(plan_id)
        usage = dict(db.owner_usage(uid()), limit=limit,
                     bot=db.bot_usage(bot_id), webhook=url_for("whatsapp_webhook", _external=True))

    staff = current_role() in ("admin", "support")
    replies_limit = None if staff else plans.ai_replies_limit(plan_id)
    return react_page("bot_detail", "nav_bots",
                      {"bot": _public_bot(b), "leads": leads, "orders": orders, "bookings": bookings,
                       "pay": _pay_state(b),
                       "plan": p, "usage": usage,
                       "links": _bot_links(b),
                       "isNew": bool(request.args.get("new")),
                       "unread": db.unread_total(bot_id),
                       "versions": db.list_config_versions(bot_id),
                       "canReply": staff or plans.inbox_reply(plan_id),
                       "ai": {
                           "setups": {"used": db.setup_sessions_this_month(uid()),
                                      "limit": None if staff else plans.ai_setups_limit(plan_id)},
                           "replies": {"used": db.ai_usage_of(uid())["replies"], "limit": replies_limit},
                           "price": FE.ai_reply_price(), "wallet": db.wallet_balance(uid()),
                           "hasKey": bool(db.get_platform("ai_key", "")),
                           "modeAllowed": staff or bool(replies_limit),
                           "canOfficial": current_role() == "admin" and db.bot_owner_is_staff(bot_id),
                           "engine": _uses_engine(b)}},
                      title=b["name"])

@app.route("/bot/<int:bot_id>/config", methods=["POST"])
@login_required
def bot_config(bot_id):
    b = _owned(bot_id); cfg = json.loads(b["config_json"] or "{}")
    for k in ("business_name", "owner_chat_id", "welcome", "thanks", "welcome_image"):
        cfg[k] = request.form.get(k, cfg.get(k, "")).strip()
    # صورة/فيديو الترحيب من مكتبة الوسائط — ملف يملكه صاحب البوت فقط
    if "welcome_asset" in request.form:
        cfg["welcome_asset"] = _own_asset_id(request.form.get("welcome_asset"))
    if b["template"] == "faq":
        items = []
        for q, a in zip(request.form.getlist("m_q"), request.form.getlist("m_a")):
            q = q.strip()
            if q: items.append({"q": q[:60], "a": (a or "").strip()[:1000]})
        cfg["menu_items"] = items
    if b["template"] == "store":
        prods = []
        imgs = request.form.getlist("p_image")
        assets = request.form.getlist("p_asset")
        for i, (n, p) in enumerate(zip(request.form.getlist("p_name"), request.form.getlist("p_price"))):
            n = n.strip()
            if not n: continue
            try: price = float(p)
            except ValueError: price = 0.0
            item = {"name": n, "price": price}
            img = (imgs[i].strip() if i < len(imgs) else "")
            if img.startswith("http"): item["image"] = img
            aid = _own_asset_id(assets[i] if i < len(assets) else "")
            if aid: item["asset"] = aid
            prods.append(item)
        cfg["products"] = prods
    if b["template"] == "booking":
        for k, cast in (("days_ahead", int), ("open_hour", int),
                        ("close_hour", int), ("slot_minutes", int)):
            try: cfg[k] = cast(request.form.get(k, cfg.get(k)))
            except (ValueError, TypeError): pass
        cfg["service_name"] = request.form.get("service_name", cfg.get("service_name", "")).strip()
        # أيام الأسبوع 0..6 فقط — قيمة غير رقمية كانت ترمي ValueError فيسقط الحفظ بـ 500
        wd = sorted({int(x) for x in request.form.getlist("working_days")
                     if str(x).strip().isdigit() and int(x) <= 6})
        cfg["working_days"] = wd or None
    is_wa = (b.get("channel") or "telegram") == "whatsapp"
    if is_wa:
        # توكنات Meta المؤقتة تنتهي خلال 24 ساعة — بلا تحديثها يموت البوت بصمت
        new_tok = request.form.get("wa_token", "").strip()
        if new_tok and new_tok != cfg.get("wa_token"):
            chk = wa_verify(b["token"][3:], new_tok)
            if not chk["ok"]:
                flash(f"❌ التوكن الجديد مرفوض: {chk['error']}", "error")
                return redirect(url_for("bot_detail", bot_id=bot_id))
            cfg["wa_token"] = new_tok
            cfg.pop("wa_limit_warned", None)
        app_id = request.form.get("wa_app_id", "").strip()
        if app_id.isdigit():                       # احتياطي لو تعذّر اكتشافه من التوكن
            cfg["wa_app_id"] = app_id
    db.update_bot_config(bot_id, cfg)
    if manager.is_running(bot_id): manager.restart_bot(bot_id)
    if is_wa:
        flash("تم حفظ الإعدادات ✅" if session.get("lang") != "en" else "Settings saved ✅", "ok")
        return redirect(url_for("bot_detail", bot_id=bot_id))
    try: sync_bot_telegram(db.get_bot(bot_id, uid()))
    except Exception: pass
    flash("تم حفظ الإعدادات ومزامنتها مع تليجرام ✅", "ok")
    return redirect(url_for("bot_detail", bot_id=bot_id))

# ---------- صورة بروفايل البوت: رفع واحد يُزامَن مع قناته (تليجرام أو واتساب) ----------
BOT_PHOTO_DIR = os.path.join(UPLOAD_DIR, "bot_photos")
BOT_PHOTO_MAX = 5 * 1024 * 1024
BOT_PHOTO_PX = 640          # مربع 640: توصية واتساب، وتليجرام يقبله (JPG للصورة الثابتة)

def _bot_photo_path(cfg):
    name = secure_filename(cfg.get("bot_photo") or "")
    path = os.path.join(BOT_PHOTO_DIR, name)
    return path if name and os.path.exists(path) else None

def _push_bot_photo(b, cfg):
    """يرسل صورة البوت لقناته ويكتب النتيجة في cfg['bot_photo_sync'] (المستدعي يحفظ cfg). لا يرمي."""
    path = _bot_photo_path(cfg)
    if not path:
        return None
    with open(path, "rb") as f:
        jpeg = f.read()
    try:
        if (b.get("channel") or "telegram") == "whatsapp":
            ok, err, app_id = WAC.set_profile_photo(b["token"][3:], cfg.get("wa_token", ""), jpeg,
                                                    cfg.get("wa_app_id"))
            if app_id:
                cfg["wa_app_id"] = app_id
        else:
            ok, err = tg.set_bot_photo(b["token"], jpeg)
    except Exception as e:
        ok, err = False, str(e)
    cfg["bot_photo_sync"] = {"ok": bool(ok), "err": (err or "")[:200], "at": int(_time.time())}
    if not ok:
        log.warning("bot #%s photo sync failed: %s", b["id"], err)
    return bool(ok)

def _photo_flash(b, ok, cfg, lang):
    ch = ("واتساب" if lang != "en" else "WhatsApp") if (b.get("channel") or "") == "whatsapp" else \
         ("تليجرام" if lang != "en" else "Telegram")
    if ok:
        flash(f"✅ صورة البوت اتحدثت على {ch}." if lang != "en" else f"✅ Bot photo updated on {ch}.", "ok")
        return
    err = (cfg.get("bot_photo_sync") or {}).get("err", "")
    if err == "app_id":
        err = ("مقدرناش نعرف App ID من التوكن — اكتبه في إعدادات البوت وجرّب «إعادة المزامنة»."
               if lang != "en" else "Couldn't read the App ID from the token — add it in the bot settings and sync again.")
    flash((f"اتحفظت الصورة، لكن المزامنة مع {ch} فشلت: {err}" if lang != "en"
           else f"Photo saved, but syncing to {ch} failed: {err}"), "error")

@app.route("/bot/<int:bot_id>/photo", methods=["GET", "POST"])
@login_required
def bot_photo(bot_id):
    """GET: معاينة لصاحب البوت. POST: رفع صورة جديدة ← Pillow (مربع 640 JPEG نظيف بلا EXIF)
    ← مزامنة فورية مع قناة البوت. الشبكة داخل الطلب ⇒ حدّ طلبات (§40)."""
    b = _owned(bot_id)
    cfg = json.loads(b["config_json"] or "{}")
    if request.method == "GET":
        path = _bot_photo_path(cfg)
        if not path:
            abort(404)
        resp = send_from_directory(BOT_PHOTO_DIR, os.path.basename(path), mimetype="image/jpeg", max_age=86400)
        resp.headers["Cache-Control"] = "private, max-age=86400"
        return resp
    lang = session.get("lang", i18n.DEFAULT)
    L = lambda a, e: e if lang == "en" else a
    back = redirect(url_for("bot_detail", bot_id=bot_id))
    if _rate_limited(f"u{uid()}", limit=10, window=3600, bucket="bot_photo"):
        flash(i18n.t("ai_rate", lang), "error")
        return back
    f = request.files.get("photo")
    data = f.read(BOT_PHOTO_MAX + 1) if f else b""
    if not data or len(data) > BOT_PHOTO_MAX:
        flash(L("اختار صورة حجمها أقل من 5MB.", "Choose an image under 5MB."), "error")
        return back
    try:
        from PIL import Image, ImageOps
        im = Image.open(io.BytesIO(data))
        if im.format not in ("JPEG", "PNG", "WEBP") or im.width * im.height > 40_000_000:
            raise ValueError(f"refused {im.format} {im.size}")
        im.load()
        im = ImageOps.exif_transpose(im).convert("RGBA")
        bg = Image.new("RGBA", im.size, (255, 255, 255, 255))      # لوجو شفاف ← خلفية بيضاء (JPEG بلا شفافية)
        im = ImageOps.fit(Image.alpha_composite(bg, im).convert("RGB"), (BOT_PHOTO_PX, BOT_PHOTO_PX), Image.LANCZOS)
        os.makedirs(BOT_PHOTO_DIR, exist_ok=True)
        name = f"{bot_id}_{_secrets.token_hex(6)}.jpg"
        im.save(os.path.join(BOT_PHOTO_DIR, name), "JPEG", quality=90, optimize=True)
    except Exception:
        log.info("bot photo refused for bot #%s", bot_id, exc_info=True)
        flash(L("الملف مش صورة صالحة — استخدم JPG أو PNG أو WebP.", "That isn't a valid image — use JPG, PNG or WebP."),
              "error")
        return back
    old = _bot_photo_path(cfg)
    cfg["bot_photo"] = name
    if old:
        try:
            os.remove(old)
        except OSError:
            pass
    ok = _push_bot_photo(b, cfg)
    db.update_bot_config(bot_id, cfg)
    _photo_flash(b, ok, cfg, lang)
    return back

@app.route("/bot/<int:bot_id>/photo/sync", methods=["POST"])
@login_required
def bot_photo_sync(bot_id):
    """إعادة إرسال الصورة الحالية (بعد تحديث توكن واتساب أو فشل سابق)."""
    b = _owned(bot_id)
    cfg = json.loads(b["config_json"] or "{}")
    lang = session.get("lang", i18n.DEFAULT)
    if _rate_limited(f"u{uid()}", limit=10, window=3600, bucket="bot_photo"):
        flash(i18n.t("ai_rate", lang), "error")
    elif _bot_photo_path(cfg):
        ok = _push_bot_photo(b, cfg)
        db.update_bot_config(bot_id, cfg)
        _photo_flash(b, ok, cfg, lang)
    return redirect(url_for("bot_detail", bot_id=bot_id))

@app.route("/bot/<int:bot_id>/photo/remove", methods=["POST"])
@login_required
def bot_photo_remove(bot_id):
    """تليجرام: removeMyProfilePhoto. واتساب لا يوفّر حذف صورة الرقم عبر الـ API — تبقى حتى تُستبدل."""
    b = _owned(bot_id)
    cfg = json.loads(b["config_json"] or "{}")
    lang = session.get("lang", i18n.DEFAULT)
    wa = (b.get("channel") or "") == "whatsapp"
    if not wa:
        ok, err = tg.remove_bot_photo(b["token"])
        if not ok:
            log.warning("bot #%s photo removal on Telegram failed: %s", bot_id, err)
    path = _bot_photo_path(cfg)
    if path:
        try:
            os.remove(path)
        except OSError:
            pass
    cfg.pop("bot_photo", None)
    cfg.pop("bot_photo_sync", None)
    db.update_bot_config(bot_id, cfg)
    flash(("تم حذف الصورة من المنصة. على واتساب تفضل الصورة الحالية لحد ما ترفع غيرها." if wa else
           "تم حذف صورة البوت من المنصة وتليجرام.") if lang != "en" else
          ("Removed from the platform. WhatsApp keeps the current photo until you upload another." if wa else
           "Bot photo removed from the platform and Telegram."), "ok")
    return redirect(url_for("bot_detail", bot_id=bot_id))

# ---------- باني الفلو No-Code ----------
@app.route("/bot/<int:bot_id>/flow", methods=["GET", "POST"])
@login_required
def flow_builder(bot_id):
    b = _owned(bot_id); cfg = json.loads(b["config_json"] or "{}")
    if b["template"] not in ("flow", "customer_service", "feedback", "support"):
        flash("باني الفلو متاح لبوتات المحادثات فقط." if session.get("lang")!="en" else "Flow builder is for conversation bots only.", "error")
        return redirect(url_for("bot_detail", bot_id=bot_id))
    if request.method == "POST":
        flow = {"start_message": request.form.get("start_message", "").strip(),
                "end_message": request.form.get("end_message", "").strip(), "steps": []}
        types = request.form.getlist("s_type")
        prompts = request.form.getlist("s_prompt")
        vars_ = request.form.getlist("s_var")
        opts = request.form.getlist("s_options")
        assets = request.form.getlist("s_asset")
        optional = request.form.getlist("s_optional")
        STEP_TYPES = ("question", "buttons", "message", "media", "show")
        for i, t in enumerate(types):
            if t not in STEP_TYPES:      # نوع غير معروف يجعل المحرك يعامله كسؤال نصي
                t = "question"
            prompt = (prompts[i] if i < len(prompts) else "").strip()
            if not prompt: continue
            step = {"id": f"s{i}", "type": t, "prompt": prompt,
                    "var": (vars_[i] if i < len(vars_) else "").strip() or f"حقل{i+1}"}
            o = [x.strip() for x in (opts[i] if i < len(opts) else "").split(",") if x.strip()]
            if t == "buttons":
                step["options"] = o
            elif t == "show":
                # صورة/فيديو من المكتبة؛ بأزرار تحته = «فيديو تفاعلي» ينتظر اختياراً
                aid = _own_asset_id(assets[i] if i < len(assets) else "")
                if aid: step["asset"] = aid
                if o: step["options"] = o
                else: step.pop("var", None)      # بلا أزرار: عرض فقط لا ينتظر إجابة
            elif t == "media" and i < len(optional) and optional[i] == "1":
                step["optional"] = True          # «ابعت صورة — أو اكتب لا»
            step.pop("var", None) if t == "message" else None
            flow["steps"].append(step)
        cfg["flow"] = flow
        db.update_bot_config(bot_id, cfg)
        if manager.is_running(bot_id): manager.restart_bot(bot_id)
        flash("تم حفظ الفلو ✅", "ok")
        return redirect(url_for("flow_builder", bot_id=bot_id))
    flow = cfg.get("flow") or {"start_message": "", "end_message": "", "steps": []}
    return react_page("flow", "flow_title", {"bot": _public_bot(b), "flow": flow},
                      title=i18n.t("flow_title", session.get("lang", i18n.DEFAULT)) + " · " + b["name"])

# ---------- سعة الخادم (L-11) ----------
_capacity_warned = {"at": 0}


def _warn_capacity_once():
    """ينبّه الأدمن مرّة واحدة عند تجاوز 80% من سقف البوتات.

    «مرّة واحدة» تعني: عند كل عتبة جديدة تُبلَغ لأول مرة، لا عند كل تشغيل —
    وإلا صار التنبيه ضجيجاً يُتجاهَل بالضبط حين يصير مهمّاً. والعدّاد يُصفَّر
    لو نزل العدد، فبلوغ العتبة مرّةً أخرى ينبّه من جديد.
    """
    try:
        st = manager.capacity_status()
    except Exception:
        return
    if not st["warn"]:
        _capacity_warned["at"] = 0
        return
    if st["running"] <= _capacity_warned["at"]:
        return
    _capacity_warned["at"] = st["running"]
    log.warning("bot capacity at %s%% — %s/%s running",
                st["pct"], st["running"], st["capacity"])
    notify_admins(f"⚠️ سعة البوتات {st['pct']}% — {st['running']} من {st['capacity']} يعملون. "
                  f"Bot capacity at {st['pct']}%. راجع الخادم قبل أن يتدهور الأداء للجميع.")


# ---------- تشغيل / إيقاف / حذف ----------
@app.route("/bot/<int:bot_id>/<any(start,stop,delete):action>", methods=["POST"])
@login_required
def bot_action(bot_id, action):
    _owned(bot_id)
    if action == "start":
        ok, msg = manager.start_bot(bot_id)
        if ok:
            _warn_capacity_once()
            db.track("bot_live", uid(), bot_id)      # مرحلة القمع: أول تشغيل لهذا البوت
    elif action == "stop": ok, msg = manager.stop_bot(bot_id)
    elif action == "delete":
        manager.stop_bot(bot_id); db.delete_bot(bot_id)
        flash("تم حذف البوت 🗑️", "ok"); return redirect(url_for("dashboard"))
    else: abort(404)
    flash(msg, "ok" if ok else "error")
    return redirect(url_for("bot_detail", bot_id=bot_id))

# ---------- التحليلات ----------
@app.route("/bot/<int:bot_id>/analytics")
@login_required
def analytics(bot_id):
    b = _owned(bot_id); b["stats"] = db.stats_summary(bot_id)
    return react_page("analytics", "analytics", {"bot": _public_bot(b)}, needs_chart=True,
                      title=i18n.t("analytics", session.get("lang", i18n.DEFAULT)) + " · " + b["name"])

@app.route("/api/bot/<int:bot_id>/stats")
@login_required
def api_stats(bot_id):
    _owned(bot_id)
    return jsonify({"summary": db.stats_summary(bot_id), "daily": db.stats_daily(bot_id, 14),
                    "sources": db.source_counts(bot_id)})

# ---------- البث الجماعي ----------
_CAMPAIGN_BUSY = ("هناك حملة قيد الإرسال لهذا البوت الآن — انتظر حتى تنتهي ثم أرسل التالية.",
                  "A campaign is already sending for this bot — wait for it to finish first.")

def _launch_campaign(bot_id, ar, mode, label, q, charged, send):
    """يبدأ الحملة في الخلفية ويردّ ثمن ما لم يصل عند انتهائها. يرجّع True لو بدأت.

    كان الإرسال داخل الطلب: مع ~110 مشترك يتجاوز مهلة nginx (60ث) فيرى صاحب البوت خطأً
    بينما الخصم تمّ والإرسال مستمر، فيضغط «إرسال» ثانيةً — خصم مزدوج وحملة مكررة لعملائه.
    الآن يرجع الطلب فوراً، وحملة واحدة لكل بوت (manager.start_campaign)، والنتيجة في الصفحة.
    الخصم — إن كانت بمقابل — تمّ قبل الاستدعاء بقفل المحفظة الذرّي (`charged` قروش).
    `send(state)` ترسل وتحدّث العدّاد الحيّ في state وترجّع (وصل, لم يصل)."""
    owner = uid()
    price = q["price"] if (q and charged) else 0

    def job(state):
        state.update(mode=mode, label=label, total=(q or {}).get("n") or state.get("total", 0))
        sent = None
        try:
            sent, failed = send(state)
            return {"sent": sent, "failed": failed}
        finally:
            # في finally: خطأ أثناء الإرسال لا يُبقي خصماً بلا ردّ — نعتمد العدّاد الحيّ حينها.
            # لا نحاسب إلا على ما وصل، بالسعر نفسه المخصوم به لا بسعر اليوم.
            got = sent if sent is not None else state.get("sent", 0)
            back = max(0, charged - got * price) if charged else 0
            if back:
                n = state.get("total") or 0
                db.wallet_refund(owner, back, ref=f"bot:{bot_id}",
                                 note=f"undelivered {n - got} of {n}")
            state.update(charged=charged - back, refunded=back)
            log.info("campaign bot=%s mode=%s %s total=%s sent=%s charged=%s refunded=%s",
                     bot_id, mode, label, state.get("total"), got, charged, back)

    if not manager.start_campaign(bot_id, job):
        if charged:           # سباق بين طلبين: الثاني لا يبقى مخصوماً
            db.wallet_refund(owner, charged, ref=f"bot:{bot_id}", note="another campaign is running")
        flash(_CAMPAIGN_BUSY[0 if ar else 1], "error")
        return False
    flash(("📢 بدأ إرسال الحملة في الخلفية — تقدر تقفل الصفحة، والنتيجة تظهر هنا في «آخر حملة»"
           + (f" (حُجز {_egp(charged)} ج.م ويُردّ منها ما لا يصل تلقائياً)." if charged else "."))
          if ar else
          ("📢 The campaign is sending in the background — you can close this page; the result "
           "shows here under «Last campaign»"
           + (f" ({_egp(charged)} EGP reserved; anything undelivered is refunded automatically)."
              if charged else ".")), "ok")
    return True

@app.route("/bot/<int:bot_id>/broadcast/status")
@login_required
def broadcast_status(bot_id):
    """حالة آخر حملة للبوت — تستطلعها الصفحة أثناء الإرسال."""
    _owned(bot_id)
    return jsonify(manager.campaign_status(bot_id) or {})

@app.route("/bot/<int:bot_id>/broadcast", methods=["GET", "POST"])
@login_required
def broadcast(bot_id):
    b = _owned(bot_id)
    
    sub = db.get_subscription(uid())
    plan_id = sub["plan"] if sub["status"] == "active" else "free"
    p = plans.plan(plan_id)
    if current_role() not in ("admin", "support") and not p.get("broadcast"):
        flash("هذه الميزة غير متاحة في باقتك الحالية. يرجى الترقية." if session.get("lang")!="en" else "This feature is not available in your current plan. Please upgrade.", "error")
        return redirect(url_for("pricing"))

    is_wa = (b.get("channel") or "telegram") == "whatsapp"
    subs = len(db.list_bot_user_ids(bot_id))
    # على واتساب النص الحر لا يصل إلا لمن راسل البوت خلال 24 ساعة
    reachable = len(db.list_bot_peers(bot_id, within_seconds=WA_WINDOW)) if is_wa else subs

    if request.method == "POST":
        ar = session.get("lang") != "en"
        # قبل أي خصم: حملة جارية للبوت نفسه تُرفض الثانية (والسباق بين طلبين يحسمه
        # start_campaign، فيُردّ ما خُصم فوراً)
        if (manager.campaign_status(bot_id) or {}).get("state") == "running":
            flash(_CAMPAIGN_BUSY[0 if ar else 1], "error")
            return redirect(url_for("broadcast", bot_id=bot_id))
        if is_wa and request.form.get("mode") == "template":
            name = request.form.get("template", "").strip()
            lang_code = request.form.get("template_lang", "").strip() or "ar"
            values = [v.strip() for v in request.form.getlist("var") if v.strip()]
            if not name:
                flash("اختر قالباً معتمداً." if ar else "Pick an approved template.", "error")
            else:
                # الفئة من Meta لا من الفورم: هي ما يقرّر الخصم، فقراءتها من
                # المستخدم تعني حملة تسويقية مؤشَّرة «UTILITY» تمرّ مجاناً.
                cat = _template_category(b, name, lang_code)
                if cat is None:
                    flash(("تعذّر التأكد من فئة القالب لدى Meta الآن. أعد المحاولة بعد قليل — "
                           "لا نرسل حملة قبل أن نعرف تكلفتها." if ar else
                           "Could not confirm the template category with Meta right now. Try again "
                           "shortly — we don't send a campaign before knowing its cost."), "error")
                    return redirect(url_for("broadcast", bot_id=bot_id))
                # الجمهور = من سيصلهم القالب فعلاً: **كل** المشتركين، لا نافذة الـ24
                # ساعة (القوالب وُجدت أصلاً لمن هم خارجها). الحساب على `reachable`
                # كان يخصم رسالة ويُرسل عشراً، والفرق تدفعه المنصة لـMeta.
                # القائمة نفسها تُمرَّر للإرسال — المحسوب هو المُرسَل إليه حرفياً.
                audience = db.list_bot_peers(bot_id)
                q = _campaign_quote(uid(), len(audience), cat)
                charged = 0
                if q["billable"]:
                    if not q["enough"]:
                        flash(((f"رصيد الرسائل التسويقية لا يكفي: الحملة {_egp(q['cost'])} ج.م "
                                f"لـ{q['n']} رسالة، ورصيدك {_egp(q['balance'])} ج.م. "
                                f"اشحن {_egp(q['short'])} ج.م على الأقل.") if ar else
                               (f"Not enough marketing credit: this campaign costs "
                                f"{_egp(q['cost'])} EGP for {q['n']} messages and your balance is "
                                f"{_egp(q['balance'])} EGP. Top up at least {_egp(q['short'])} EGP.")),
                              "error")
                        return redirect(url_for("broadcast", bot_id=bot_id))
                    # يُخصم **قبل** الإرسال: الخصم الذرّي هو ما يمنع حملتين
                    # متوازيتين من تجاوز الرصيد معاً. ثم يُردّ ما فشل إرساله.
                    if db.wallet_charge(uid(), q["cost"], ref=f"bot:{bot_id}",
                                        note=f"campaign {name} ×{q['n']}") is None:
                        flash("تعذّر حجز الرصيد — أعد المحاولة." if ar else
                              "Could not reserve credit — please retry.", "error")
                        return redirect(url_for("broadcast", bot_id=bot_id))
                    charged = q["cost"]
                # في الخلفية: ما لم يصل (فاشل أو لم يُحاوَل) يُردّ عند الانتهاء (_launch_campaign)
                _launch_campaign(bot_id, ar, "template", name, q, charged,
                                 lambda st: manager.broadcast_template(bot_id, name, lang_code, values,
                                                                       peers=audience, prog=st))
        elif is_wa and request.form.get("mode") == "direct_send":
            # ---- Direct Send (بيتا): نص بلا قالب مسبق، وMeta تولّد القالب في الخلفية ----
            # الفئة نحن من يعلنها ولا يراجعها أحد قبل الإرسال — فلا شيء يمنع إعلاناً
            # مؤشَّراً «utility»، والمنصة هي من تدفع لـMeta. لذا تُحاسَب من المحفظة بسعر
            # الرسالة كالحملة التسويقية (§20)، والفئة ثابتة لا تُقرأ من الفورم.
            # و«authentication» مستبعدة: قوالبها لرموز التحقق وحدها.
            ds_text = request.form.get("text", "").strip()
            if not ds_text:
                flash("اكتب نص الرسالة." if ar else "Write the message.", "error")
            elif len(ds_text) > 4096:
                flash("النص أطول من 4096 حرفاً." if ar else "Text exceeds 4096 characters.", "error")
            else:
                # كل المشتركين، والقائمة المحسوبة هي نفسها المُرسَل إليها (§22)
                audience = db.list_bot_peers(bot_id)
                q = _campaign_quote(uid(), len(audience), "MARKETING")
                if not audience:
                    flash("لا مشتركين بعد." if ar else "No subscribers yet.", "error")
                    return redirect(url_for("broadcast", bot_id=bot_id))
                if not q["enough"]:
                    flash(((f"رصيد الرسائل لا يكفي: الإرسال {_egp(q['cost'])} ج.م "
                            f"لـ{q['n']} رسالة، ورصيدك {_egp(q['balance'])} ج.م. "
                            f"اشحن {_egp(q['short'])} ج.م على الأقل.") if ar else
                           (f"Not enough credit: this send costs {_egp(q['cost'])} EGP for "
                            f"{q['n']} messages and your balance is {_egp(q['balance'])} EGP. "
                            f"Top up at least {_egp(q['short'])} EGP.")), "error")
                    return redirect(url_for("broadcast", bot_id=bot_id))
                # خصم ذرّي قبل الإرسال، ثم ردّ كل ما لم يصل بالسعر نفسه
                if db.wallet_charge(uid(), q["cost"], ref=f"bot:{bot_id}",
                                    note=f"direct send ×{q['n']}") is None:
                    flash("تعذّر حجز الرصيد — أعد المحاولة." if ar else
                          "Could not reserve credit — please retry.", "error")
                    return redirect(url_for("broadcast", bot_id=bot_id))
                # في الخلفية، والنتيجة في «آخر حملة». لا شيء وصل (mode=direct و sent=0) =
                # أشهر سبب أن الحساب غير مفعّل لبيتا Meta — الصفحة تقوله صراحةً مع الردّ الكامل.
                _launch_campaign(bot_id, ar, "direct", "", q, q["cost"],
                                 lambda st: manager.broadcast_direct(bot_id, ds_text, "utility",
                                                                     peers=audience, prog=st))
        else:
            text = request.form.get("text", "").strip()
            # صورة/فيديو اختياري من مكتبة المستخدم نفسه (والنص يصير تعليقه)
            aid = _own_asset_id(request.form.get("asset_id"))
            asset = db.get_asset(aid, owner_id=uid()) if aid else None
            if not text and not asset:
                flash("اكتب نص الرسالة." if ar else "Write the message.", "error")
            else:
                # مجاني (تليجرام أو داخل نافذة واتساب) — في الخلفية أيضاً: ~110 مشترك تتجاوز
                # مهلة nginx، والضغطة الثانية كانت ترسل الحملة مرتين لعملائه
                _launch_campaign(bot_id, ar, "text", "", None, 0,
                                 lambda st: manager.broadcast(bot_id, text, asset=asset, prog=st))
        return redirect(url_for("broadcast", bot_id=bot_id))

    return react_page("broadcast", "campaign_title",
                      {"bot": _public_bot(b), "subs": subs, "isWa": is_wa, "reachable": reachable,
                       "campaign": manager.campaign_status(bot_id),
                       # جمهور القالب (كل المشتركين) — هو ما تُعرض عليه التكلفة
                       "audience": len(db.list_bot_peers(bot_id)) if is_wa else subs,
                       "waba": _waba_of(b)[0] if is_wa else "",
                       # التكلفة تُعرض **قبل** التأكيد — والخادم يعيد حسابها عند الإرسال
                       "wallet": {"balance": db.wallet_balance(uid()),
                                  "price": mkt_price(),
                                  "topupUrl": url_for("wallet_page")}},
                      title=i18n.t("campaign_title", session.get("lang", i18n.DEFAULT)) + " · " + b["name"])

# ---------- قوالب واتساب المعتمدة ----------
def _waba_of(bot_row):
    """يرجّع (waba_id, hint). الأول مؤكَّد، والثاني مرشّح من الويبهوك لم يُتحقق منه."""
    cfg = json.loads(bot_row["config_json"] or "{}")
    return cfg.get("wa_waba_id", ""), cfg.get("wa_waba_hint", "")

def _wa_bot(bot_id):
    """بوت واتساب يملكه المستخدم، وباقته تسمح — وإلا 404/403."""
    b = _owned(bot_id)
    if (b.get("channel") or "telegram") != "whatsapp":
        abort(404)
    if current_role() not in ("admin", "support"):
        sub = db.get_subscription(uid())
        plan_id = sub["plan"] if sub["status"] == "active" else "free"
        if not plans.plan(plan_id).get("whatsapp"):
            abort(403)
    return b

@app.route("/bot/<int:bot_id>/templates")
@login_required
def wa_templates_page(bot_id):
    b = _wa_bot(bot_id)
    waba, hint = _waba_of(b)
    return react_page("wa_templates", "wa_tpl_title",
                      {"bot": _public_bot(b), "waba": waba, "wabaHint": hint,
                       "cats": list(WT.CATEGORIES), "limits": WT.LIMITS},
                      title=i18n.t("wa_tpl_title", session.get("lang", i18n.DEFAULT)) + " · " + b["name"])

@app.route("/api/bot/<int:bot_id>/templates")
@login_required
def api_wa_templates(bot_id):
    b = _wa_bot(bot_id)
    cfg = json.loads(b["config_json"] or "{}")
    waba, _ = _waba_of(b)
    if not waba:
        return jsonify({"ok": False, "error": "لم يُضبط WABA ID بعد.", "needs_waba": True})
    return jsonify(WT.list_templates(waba, cfg.get("wa_token", "")))

@app.route("/bot/<int:bot_id>/templates/waba", methods=["POST"])
@login_required
def wa_set_waba(bot_id):
    b = _wa_bot(bot_id)
    cfg = json.loads(b["config_json"] or "{}")
    waba = request.form.get("waba_id", "").strip()
    # نتحقّق باستدعاء حقيقي: WABA ID و Phone Number ID يتشابهان ويُخلط بينهما دوماً
    res = WT.verify_waba(waba, cfg.get("wa_token", ""))
    if not res["ok"]:
        flash(f"❌ {res['error']}", "error")
    else:
        cfg["wa_waba_id"] = waba
        cfg.pop("wa_waba_hint", None)
        db.update_bot_config(bot_id, cfg)
        flash("تم ربط حساب واتساب للأعمال ✅" if session.get("lang") != "en"
              else "WhatsApp Business Account linked ✅", "ok")
    return redirect(url_for("wa_templates_page", bot_id=bot_id))

@app.route("/bot/<int:bot_id>/templates/create", methods=["POST"])
@login_required
def wa_create_template(bot_id):
    b = _wa_bot(bot_id)
    cfg = json.loads(b["config_json"] or "{}")
    waba, _ = _waba_of(b)
    if not waba:
        flash("اضبط WABA ID أولاً.", "error")
        return redirect(url_for("wa_templates_page", bot_id=bot_id))
    res = WT.create_template(
        waba, cfg.get("wa_token", ""),
        name=request.form.get("name", "").strip().lower(),
        language=request.form.get("language", "ar").strip(),
        category=request.form.get("category", "UTILITY").strip().upper(),
        body=request.form.get("body", "").strip(),
        header=request.form.get("header", "").strip(),
        footer=request.form.get("footer", "").strip(),
        buttons=[x.strip() for x in request.form.getlist("button") if x.strip()])
    if res["ok"]:
        flash(("أُرسل القالب لمراجعة Meta ⏳ — الاعتماد يستغرق من دقائق إلى 24 ساعة."
               if session.get("lang") != "en" else
               "Submitted to Meta for review ⏳ — approval takes minutes to 24 hours."), "ok")
    else:
        flash(f"❌ {res['error']}", "error")
    return redirect(url_for("wa_templates_page", bot_id=bot_id))

@app.route("/bot/<int:bot_id>/templates/delete", methods=["POST"])
@login_required
def wa_delete_template(bot_id):
    b = _wa_bot(bot_id)
    cfg = json.loads(b["config_json"] or "{}")
    waba, _ = _waba_of(b)
    name = request.form.get("name", "").strip()
    res = WT.delete_template(waba, cfg.get("wa_token", ""), name) if (waba and name) else {"ok": False, "error": "بيانات ناقصة."}
    flash((f"تم حذف القالب «{name}»." if res.get("ok") else f"❌ {res.get('error')}"),
          "ok" if res.get("ok") else "error")
    return redirect(url_for("wa_templates_page", bot_id=bot_id))

# ---------- تحصيل مدفوعات عملاء البوت (إضافة مدفوعة لكل بوت) ----------
# عميل البوت يحوّل على حسابات **صاحب البوت** ويرسل الإيصال للبوت، فيُفحص بمحرك إيصالات المنصة
# نفسه ويعتمده صاحب البوت (زرّ في تليجرام أو من اللوحة). v1: بوتات المتجر على تليجرام.
ADDON_PAY_PRICE_FALLBACK = 99          # جنيه شهرياً لكل بوت — يُعدَّل من «إعدادات المنصة»
_PAY_FIELDS = (("vodafone", 20), ("instapay", 60), ("instapay_link", 200), ("bank_name", 60),
               ("bank_account", 40), ("bank_iban", 40), ("bank_holder", 80))

def addon_pay_price():
    """سعر الإضافة بالجنيه. قيمة فاسدة أو صفر تسقط للاحتياطي — لا إضافة مجانية بالخطأ."""
    try:
        v = int(float(str(db.get_platform("addon_pay_price", "") or "0").strip()))
    except (TypeError, ValueError, OverflowError):
        v = 0
    return v if 0 < v <= 100000 else ADDON_PAY_PRICE_FALLBACK

def _pay_eligible(b):
    return b.get("template") == "store" and (b.get("channel") or "telegram") == "telegram"

def _pay_state(b):
    """حالة الإضافة لصفحة البوت."""
    if not _pay_eligible(b):
        return {"eligible": False}
    cfg = json.loads(b.get("config_json") or "{}")
    staff = db.bot_owner_is_staff(b["id"])            # حساب الإدارة: مشمولة بلا شراء ولا انتهاء
    return {"eligible": True, "active": db.addon_active(b["id"]), "staff": staff,
            "expires": None if staff else db.addon_expires(b["id"]),
            "price": addon_pay_price(), "methods": cfg.get("pay") or {},
            "payments": db.list_bot_payments(b["id"])}

@app.route("/bot/<int:bot_id>/addon/pay", methods=["GET", "POST"])
@login_required
def addon_pay(bot_id):
    """شراء/تجديد الإضافة 30 يوماً — بمسار إيصالات المنصة نفسه: فحص آلي قبل الحفظ ثم موافقة
    الأدمن. المبلغ من الخادم (`addon_pay_price`) لا من الفورم (§3.3)."""
    b = _owned(bot_id)
    ar = session.get("lang") != "en"
    if not _pay_eligible(b):
        flash("الإضافة متاحة لبوتات المتجر على تليجرام." if ar else
              "The add-on is available for Telegram store bots.", "error")
        return redirect(url_for("bot_detail", bot_id=bot_id))
    if db.bot_owner_is_staff(bot_id):
        # لا دفعة ولا إيصال لحساب الإدارة — الإضافة مفتوحة له أصلاً (db.addon_active)
        flash("الإضافة مفتوحة لحساب الإدارة بلا اشتراك ✅" if ar else
              "The add-on is included for the admin account ✅", "ok")
        return redirect(url_for("bot_detail", bot_id=bot_id) + "#pay")
    price = addon_pay_price()
    if request.method == "POST":
        back = redirect(url_for("addon_pay", bot_id=bot_id))
        if _rate_limited(f"u{uid()}", limit=8, window=3600, bucket="receipt"):
            flash(i18n.t("ai_rate", session.get("lang", i18n.DEFAULT)), "error")
            return back
        file = request.files.get("screenshot")
        ext = os.path.splitext(file.filename)[1].lower() if file and file.filename else ""
        if ext not in pay.ALLOWED_EXT:
            flash("ارفع صورة إيصال التحويل (jpg/png/webp)." if ar else
                  "Upload the transfer receipt image (jpg/png/webp).", "error")
            return back
        data = file.read()
        if not pay.validate_bytes(data)["ok"]:
            flash("الملف ليس صورة صالحة." if ar else "The file is not a valid image.", "error")
            return back
        ac, img_hash, refused = _receipt_check(data, price)
        if refused:
            flash(refused, "error")
            return back
        fname = f"addon_{uid()}_{bot_id}_{int(_time.time())}{ext}"
        fpath = os.path.join(UPLOAD_DIR, secure_filename(fname))
        with open(fpath, "wb") as _f:
            _f.write(data)
        pid = db.create_payment(uid(), db.addon_plan(bot_id), request.form.get("method", ""),
                                float(price), request.form.get("ref", "").strip(), fname, img_hash,
                                json.dumps(ac, ensure_ascii=False))
        log.info("add-on payment #%s requested user=%s bot=%s verdict=%s", pid, uid(), bot_id,
                 ac.get("verdict"))
        admin_id = db.get_platform("admin_chat_id", "")
        payment = db.get_payment(pid)
        caption = PB.build_caption(payment, session.get("uname", ""), _verdict_detail(ac))
        msg_id = manager.send_payment_alert(admin_id, payment, session.get("uname", ""),
                                            caption, fpath) if admin_id else None
        if msg_id:
            db.set_payment_msg(pid, msg_id)
        else:
            notify_admins(f"🧩 طلب إضافة تحصيل المدفوعات #{pid} — {session.get('uname')} — "
                          f"بوت #{bot_id} — {price} EGP. راجعه من لوحة الأدمن.")
        flash(("✅ وصل إثبات الدفع (#{}). تتفعّل الإضافة بعد المراجعة والموافقة." if ar else
               "✅ Payment proof received (#{}). The add-on activates after review.").format(pid), "ok")
        return redirect(url_for("bot_detail", bot_id=bot_id) + "#pay")
    return react_page("addon_pay", "addon_pay_title",
                      {"bot": _public_bot(b), "price": price, "expires": db.addon_expires(bot_id),
                       "plat": _public_plat(), "qr": url_for("static", filename="instapay_qr.jpg"),
                       "action": url_for("addon_pay", bot_id=bot_id)})

@app.route("/bot/<int:bot_id>/pay-settings", methods=["POST"])
@login_required
def bot_pay_settings(bot_id):
    """حسابات استلام **صاحب البوت** (لا حسابات المنصة): عليها يحوّل عملاؤه وبها يُطابَق الإيصال."""
    b = _owned(bot_id)
    ar = session.get("lang") != "en"
    cfg = json.loads(b["config_json"] or "{}")
    methods = {k: (request.form.get(f"pay_{k}") or "").strip()[:n] for k, n in _PAY_FIELDS}
    cfg["pay"] = {k: v for k, v in methods.items() if v}
    db.update_bot_config(bot_id, cfg)
    if manager.is_running(bot_id):
        manager.restart_bot(bot_id)            # القالب يقرأ إعداداته عند التشغيل
    flash("تم حفظ حسابات الاستلام ✅" if ar else "Receiving accounts saved ✅", "ok")
    return redirect(url_for("bot_detail", bot_id=bot_id) + "#pay")

@app.route("/bot/<int:bot_id>/payments/<int:pid>/<any(approve,reject):action>", methods=["POST"])
@login_required
def bot_payment_decide(bot_id, pid, action):
    """قرار صاحب البوت من اللوحة — نفس القرار الذرّي لزرّ تليجرام، والعميل يُبلَّغ عبر البوت."""
    _owned(bot_id)
    ar = session.get("lang") != "en"
    row = db.decide_bot_payment(pid, bot_id, "approved" if action == "approve" else "rejected")
    if not row:
        flash("سبق البتّ في هذه الدفعة." if ar else "This payment was already decided.", "error")
    else:
        told = manager.bot_send(bot_id, row.get("tg_user_id"), T.pay_decision_text(row))
        done = ("✅ تم تأكيد الدفع" if action == "approve" else "❌ تم رفض الدفعة") if ar else \
               ("✅ Payment confirmed" if action == "approve" else "❌ Payment rejected")
        flash(done + ((" وإبلاغ العميل." if ar else " — the customer was notified.") if told else
                      (" — البوت متوقف فلم يُبلَّغ العميل." if ar else
                       " — the bot is stopped, so the customer wasn't notified.")), "ok")
    return redirect(url_for("bot_detail", bot_id=bot_id) + "#pay")

@app.route("/bot/<int:bot_id>/payments/<int:pid>/receipt")
@login_required
def bot_payment_receipt(bot_id, pid):
    """صورة إيصال عميل — لصاحب البوت وحده."""
    _owned(bot_id)
    row = db.get_bot_payment(pid, bot_id)
    if not row or not row.get("screenshot"):
        abort(404)
    fname = secure_filename(row["screenshot"])
    if not os.path.exists(os.path.join(UPLOAD_DIR, fname)):
        abort(404)
    resp = send_from_directory(UPLOAD_DIR, fname)
    resp.headers["Cache-Control"] = "private, no-store"
    return resp

# ---------- تصدير CSV ----------
_CSV_FORMULA = ("=", "+", "-", "@", "\t", "\r")

def _csv_cell(v):
    """خلية آمنة لـ Excel. نصّ يبدأ بـ = + - @ يُنفَّذ صيغةً عند فتح الملف — اسم عميل مثل
    =HYPERLINK(...) يصل عبر البوت ثم يُفتح عند صاحب النشاط نفسه. تسبيقه بـ ' يجعله
    نصاً. الأرقام الحقيقية (الإجمالي والوقت) تبقى أرقاماً."""
    if isinstance(v, str) and v.startswith(_CSV_FORMULA):
        return "'" + v
    return v

@app.route("/bot/<int:bot_id>/export/<kind>")
@login_required
def export_csv(bot_id, kind):
    _owned(bot_id)
    out = io.StringIO(); w = csv.writer(out)
    put = lambda cells: w.writerow([_csv_cell(x) for x in cells])
    # limit=None: «صدّر كل الطلبات» يعني الكل — اللوحة وحدها تكتفي بآخر 300
    if kind == "orders":
        put(["العميل", "التليفون", "العنوان", "المنتجات", "الإجمالي", "الوقت"])
        for o in db.list_orders(bot_id, limit=None):
            items = "; ".join(f"{i['name']}x{i['qty']}" for i in o["items"])
            put([o["customer"], o["phone"], o["address"], items, o["total"], o["created_at"]])
    elif kind == "bookings":
        put(["العميل", "التليفون", "الخدمة", "الموعد", "الحالة"])
        for x in db.list_bookings(bot_id, limit=None):
            put([x["customer"], x["phone"], x["service"], x["slot"], x["status"]])
    elif kind == "leads":
        put(["البيانات", "الوقت"])
        for l in db.list_leads(bot_id, limit=None):
            put([json.dumps(l["data"], ensure_ascii=False), l["created_at"]])
    else:
        abort(404)
    csv_bytes = "﻿" + out.getvalue()   # BOM لدعم العربية في Excel
    return Response(csv_bytes, mimetype="text/csv",
                    headers={"Content-Disposition": f"attachment; filename={kind}_{bot_id}.csv"})

# ---------- إعدادات الذكاء الاصطناعي ----------
@app.route("/settings", methods=["GET", "POST"])
@require_roles("admin")
def settings():
    if request.method == "POST":
        db.set_platform("ai_provider", request.form.get("ai_provider", "gemini"))
        db.set_platform("ai_key", request.form.get("ai_key", "").strip())
        flash("تم حفظ إعدادات الذكاء الاصطناعي للمنصة ✅" if session.get("lang")!="en"
              else "Platform AI settings saved ✅", "ok")
        return redirect(url_for("settings"))
    return react_page("settings", "ai_settings",
                      {"aiProvider": db.get_platform("ai_provider", "gemini"),
                       "aiKey": db.get_platform("ai_key", "")})

# (المسار القديم POST /bot/<id>/ai-setup حُذف: لا تستعمله الواجهة، وكان بلا حصة ولا حدّ
#  فيحرق مفتاح الذكاء الاصطناعي للمنصة بطلبين لكل استدعاء. وكيل الإعداد /ai/session يغنيه.)


# ---------- وكيل الإعداد (محادثة ← أسئلة ← تصميم ← معاينة ← تطبيق) ----------
def _plan_id():
    sub = db.get_subscription(uid())
    return sub["plan"] if sub["status"] == "active" else "free"


def _setup_provider():
    """مفتاح المنصة ومزوّدها. الباقة المجانية تحصل على الوكيل الحقيقي نفسه
    بحصة صغيرة (plans.FEATURES) — لا مولّد نصوص ثابت يُقدَّم على أنه ذكاء."""
    return (db.get_platform("ai_key", "") or None), db.get_platform("ai_provider", "gemini")


def _setup_quota():
    """(المستخدَم، الحد) لجلسات الوكيل هذا الشهر. الحد None = بلا حد."""
    used = db.setup_sessions_this_month(uid())
    if current_role() in ("admin", "support"):
        return used, None
    return used, plans.ai_setups_limit(_plan_id())


def _run_setup_turn(b, sid, turns, rounds):
    key, provider = _setup_provider()
    cfg = json.loads(b["config_json"] or "{}")
    res = ai.setup_step(turns, template=b["template"], channel=b.get("channel") or "telegram",
                        current_name=cfg.get("business_name") or b["name"],
                        api_key=key, provider=provider)
    if res["status"] == "questions":
        turns = turns + [{"role": "agent", "questions": res["questions"]}]
        db.save_setup_session(sid, "asking", res.get("brief"), turns, None, rounds + 1, res["source"])
        return {"ok": True, "sid": sid, "status": "questions", "questions": res["questions"],
                "source": res["source"]}
    prop = res["proposal"]
    db.save_setup_session(sid, "proposed", res.get("brief"), turns,
                          {"patch": prop, "summary": res.get("summary"), "notes": res.get("notes")},
                          rounds, res["source"])
    # «قبل» لكل حقل سيتغيّر — الواجهة تعرض الفرق ولا يُحفظ شيء قبل الموافقة
    return {"ok": True, "sid": sid, "status": "proposal", "proposal": prop,
            "before": {k: cfg.get(k) for k in prop}, "summary": res.get("summary") or "",
            "notes": res.get("notes") or [], "source": res["source"]}


def _setup_session_or_404(bot_id, sid, status):
    s = db.get_setup_session(sid, bot_id)
    if not s or s["owner_id"] != uid() or s["status"] != status:
        abort(404)
    return s


@app.route("/bot/<int:bot_id>/ai/session", methods=["POST"])
@login_required
def ai_session_start(bot_id):
    b = _owned(bot_id)
    lang = session.get("lang", i18n.DEFAULT)
    desc = ((request.get_json(silent=True) or {}).get("description") or "").strip()[:2000]
    if len(desc) < 3:
        return jsonify({"ok": False, "error": i18n.t("ai_need_desc", lang)})
    if _rate_limited(f"u{uid()}", limit=20, window=3600, bucket="ai_setup"):
        return jsonify({"ok": False, "error": i18n.t("ai_rate", lang)})
    used, limit = _setup_quota()
    if limit is not None and used >= limit:
        return jsonify({"ok": False, "upgrade": True,
                        "error": i18n.t("ai_quota_out", lang).format(n=limit)})
    key, _ = _setup_provider()
    sid = db.create_setup_session(bot_id, uid(), "ai" if key else "offline")
    return jsonify(_run_setup_turn(b, sid, [{"role": "owner", "text": desc}], 0))


@app.route("/bot/<int:bot_id>/ai/session/<int:sid>/reply", methods=["POST"])
@login_required
def ai_session_reply(bot_id, sid):
    b = _owned(bot_id)
    s = _setup_session_or_404(bot_id, sid, "asking")
    data = request.get_json(silent=True) or {}
    answers = [str(a or "").strip()[:300] for a in (data.get("answers") or [])][:ai.MAX_QUESTIONS]
    turns = s["turns"] + [{"role": "owner", "answers": answers}]
    extra = str(data.get("text") or "").strip()[:1000]
    if extra:
        turns.append({"role": "owner", "text": extra})
    return jsonify(_run_setup_turn(b, sid, turns, s["rounds"]))


@app.route("/bot/<int:bot_id>/ai/session/<int:sid>/<any(apply,discard):action>", methods=["POST"])
@login_required
def ai_session_close(bot_id, sid, action):
    b = _owned(bot_id)
    s = db.get_setup_session(sid, bot_id)
    if not s or s["owner_id"] != uid() or s["status"] not in ("asking", "proposed"):
        abort(404)
    if action == "discard":
        db.close_setup_session(sid, "discarded")
        return jsonify({"ok": True})
    # ذرّي: جلسة طُبّقت لا تُطبَّق ثانية (نقرتان متتاليتان · تبويبان)
    if s["status"] != "proposed" or not s.get("proposal") or not db.close_setup_session(sid, "applied"):
        abort(404)
    cfg = json.loads(b["config_json"] or "{}")
    db.save_config_version(bot_id, cfg, "ai_apply")          # «تراجع» بضغطة
    cfg.update(s["proposal"]["patch"])
    db.update_bot_config(bot_id, cfg)
    if manager.is_running(bot_id): manager.restart_bot(bot_id)
    if (b.get("channel") or "telegram") == "telegram":
        try: sync_bot_telegram(db.get_bot(bot_id, uid()))
        except Exception: pass
    return jsonify({"ok": True})


@app.route("/bot/<int:bot_id>/config/restore/<int:vid>", methods=["POST"])
@login_required
def config_restore(bot_id, vid):
    b = _owned(bot_id)
    old = db.get_config_version(vid, bot_id)          # الملكية: bot_id شرط في الاستعلام
    if old is None:
        abort(404)
    cur = json.loads(b["config_json"] or "{}")
    db.save_config_version(bot_id, cur, "restore")
    # الحقول التشغيلية لا تُستعاد من نسخة قديمة: ربط المالك والتوكنات وهوية البوت
    for k in ("owner_chat_id", "wa_token", "tg_bot_id", "bot_username", "bot_name",
              "pending_owner_code", "wa_waba_id", "wa_waba_hint", "created_via",
              "ai_consent_at", "tg_synced_at", "tg_sync_ok", "tg_sync_errors"):
        if k in cur:
            old[k] = cur[k]
        else:
            old.pop(k, None)
    db.update_bot_config(bot_id, old)
    if manager.is_running(bot_id): manager.restart_bot(bot_id)
    flash(i18n.t("restore_done", session.get("lang", i18n.DEFAULT)), "ok")
    return redirect(url_for("bot_detail", bot_id=bot_id))


# ---------- تكامل تليجرام ----------
@app.route("/api/validate-token", methods=["POST"])
@login_required
def api_validate_token():
    # ينتظر تليجرام حتى 10ث داخل الطلب، وكان بلا حدّ: خيوط gunicorn تُشغل كلها، ووسيلة
    # مجانية لفحص توكنات مسروقة بالجملة. الواجهة تفحص بعد توقف الكتابة — 30 تكفي.
    if _rate_limited(f"u{uid()}", limit=30, window=600, bucket="tg_check"):
        return jsonify({"ok": False, "error": i18n.t("ai_rate", session.get("lang", i18n.DEFAULT))})
    token = (request.get_json(silent=True) or {}).get("token", "")
    return jsonify(tg.validate_token(token))

@app.route("/bot/<int:bot_id>/gen-owner-link", methods=["POST"])
@login_required
def gen_owner_link(bot_id):
    b = _owned(bot_id); cfg = json.loads(b["config_json"] or "{}")
    if (b.get("channel") or "telegram") != "telegram":
        return jsonify({"ok": False, "error": "رابط الربط لتليجرام فقط. "
                                              "اربط تليجرام من صفحة «حسابي» لتصلك إشعارات بوت واتساب."})
    username = cfg.get("bot_username")
    if not username:
        info = tg.validate_token(b["token"])
        if info["ok"]:
            username = info.get("username"); cfg["bot_username"] = username; cfg["bot_name"] = info.get("name")
    if not username:
        return jsonify({"ok": False, "error": "تعذّر معرفة يوزر البوت. تأكد من التوكن."})
    code = tg.gen_owner_code(); cfg["pending_owner_code"] = code
    db.update_bot_config(bot_id, cfg)
    if manager.is_running(bot_id): manager.restart_bot(bot_id)
    running = manager.is_running(bot_id)
    return jsonify({"ok": True, "link": tg.owner_deep_link(username, code),
                    "username": username, "running": running})

@app.route("/api/bot/<int:bot_id>/owner-status")
@login_required
def owner_status(bot_id):
    b = _owned(bot_id); cfg = json.loads(b["config_json"] or "{}")
    return jsonify({"owner_chat_id": cfg.get("owner_chat_id") or ""})

@app.route("/pricing")
def pricing():
    sub = db.get_subscription(uid()) if uid() else {"plan":"free","status":"active"}
    lang = session.get("lang", i18n.DEFAULT)
    AN.queue(session, "view_pricing")
    return react_page("pricing", "pricing_title",
                      {"plans": [dict(p, name=plans.plan_name(p["id"], lang))
                                 for p in priced_plans(lang)], "sub": sub})

@app.route("/subscribe/<plan_id>", methods=["GET"])
@login_required
def subscribe(plan_id):
    # `is_sellable` لا `in PLANS`: الباقات الموروثة موجودة في PLANS لتخدم
    # مشتركيها القدامى، لكنها ليست معروضة للبيع لأحد جديد.
    if not plans.is_sellable(plan_id):
        return redirect(url_for("pricing"))
    p = plans.plan(plan_id)
    plat = _public_plat()
    # الدورة تأتي من رابط صفحة الأسعار، وتُطبَّع فوراً: `?cycle=anything` تصير شهرية.
    cyc = plans.norm_cycle(request.args.get("cycle"))
    _pr = _plan_pricing(plan_id, cycle=cyc)
    _mo = _plan_pricing(plan_id, cycle="monthly")
    # معاينة نقل الرصيد قبل الدفع — بنفس ما تستعمله `finalize_payment` عند
    # الاعتماد (سعر القائمة للدورة). تقديرية: الأيام تُحسب فعلياً يوم الاعتماد.
    _carry = db.carry_over_days(uid(), plan_id, _pr["list_price"], plans.cycle_days(cyc))
    # بداية السلة: القيمة من الخادم (`_plan_pricing`) لا من الواجهة — نفس المبدأ
    # المطبَّق على الدفع نفسه، فلا رقم في تقارير الإعلانات يخالف ما يدفعه العميل.
    AN.queue(session, "subscribe_intent", plan=plan_id, cycle=cyc,
             value=float(_pr["price"]), currency="EGP")
    return react_page("subscribe", "pay_title",
                      {"planId": plan_id, "plan": dict(p, id=plan_id, **_pr), "plat": plat,
                       "cycle": cyc, "days": plans.cycle_days(cyc),
                       "carry": ({"fromPlan": plans.plan_name(_carry["from_plan"],
                                                              session.get("lang", i18n.DEFAULT)),
                                  "remaining": int(_carry["remaining_days"]),
                                  "credit": int(_carry["credit_days"])} if _carry else None),
                       "monthlyPrice": _mo["price"],
                       "annualSavingPct": (int(round((1 - _pr["price"] / (_mo["price"] * 12.0)) * 100))
                                           if cyc == "annual" and _mo["price"] > 0 else 0),
                       "qr": url_for("static", filename="instapay_qr.jpg"),
                       "action": url_for("subscribe_pay", plan_id=plan_id)})

def _receipt_check(data, amount):
    """الفحص الآلي للإيصال **قبل** أي كتابة على القرص (AGENTS.md §3.12).
    يرجّع (نتيجة الفحص، بصمة الصورة، رسالة الرفض أو None). المرفوض لا ملف له ولا
    طلب دفع ولا تنبيه للأدمن — يُسجَّل في receipt_refusals فقط، والعميل يعرف السبب."""
    img_hash = hashlib.sha256(data).hexdigest()
    refs = [db.get_platform(k, "") for k in ("vodafone_number", "instapay_handle",
                                             "bank_iban", "bank_account", "bank_holder")]
    prior = db.count_receipt_refusals(uid(), since=int(_time.time()) - 3600, exclude=("duplicate",))
    ac = pay.auto_check(data, amount, [r for r in refs if r],
                        duplicate=db.img_hash_active(img_hash), prior_refusals=prior)
    if not ac.get("refuse"):
        return ac, img_hash, None
    db.log_receipt_refusal(uid(), ac.get("reason") or "not_receipt", img_hash)
    log.info("receipt refused user=%s reason=%s", uid(), ac.get("reason"))
    to = db.get_platform("vodafone_number", "") or db.get_platform("instapay_handle", "") or "—"
    msg = i18n.t(pay.REFUSAL_KEYS.get(ac.get("reason"), "pay_rej_not_receipt"),
                 session.get("lang", i18n.DEFAULT)).format(amount=f"{float(amount):g}", ref=to)
    return ac, img_hash, msg

def _verdict_detail(ac):
    """ملخص الفحص الآلي لتنبيه تليجرام (بالعربي — لغة الأدمن)."""
    return pay.verdict_label(ac["verdict"], "ar") + "\n" + "\n".join(
        ("✅ " if c["ok"] else ("❌ " if c["ok"] is False else "• ")) + c["text"]
        for c in pay.check_lines(ac, "ar"))

@app.route("/subscribe/<plan_id>", methods=["POST"])
@login_required
def subscribe_pay(plan_id):
    if not plans.is_sellable(plan_id):
        return redirect(url_for("pricing"))
    # قراءة الإيصال (OCR) أغلى ما في المنصة وتعمل داخل الطلب — مسارا الدفع يتشاركان حداً
    if _rate_limited(f"u{uid()}", limit=8, window=3600, bucket="receipt"):
        flash(i18n.t("ai_rate", session.get("lang", i18n.DEFAULT)), "error")
        return redirect(url_for("subscribe", plan_id=plan_id))
    # التسعيرة تُحسب في الخادم: سعر الباقة على الدورة المختارة بعد تجاوز المالك
    # وخصمها، ثم كود الخصم إن صحّ. لا يُقرأ أي مبلغ من الفورم (AGENTS.md §3.3).
    # الفورم يرسل اسم الدورة فقط — لا سعرها — و`norm_cycle` تردّ أي قيمة ملفّقة
    # إلى الشهرية، فأسوأ ما يفعله العابث أن يدفع سعر شهر ويأخذ شهراً.
    q = quote(plan_id, uid(), request.form.get("promo", ""),
              cycle=request.form.get("cycle"))
    method = request.form.get("method", "")
    ref = request.form.get("ref", "").strip()
    file = request.files.get("screenshot")
    if not file or not file.filename:
        flash("يجب رفع صورة إثبات الدفع." if session.get("lang")!="en" else "Please upload the payment screenshot.", "error")
        return redirect(url_for("subscribe", plan_id=plan_id, cycle=q["cycle"]))
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in pay.ALLOWED_EXT:
        flash("صيغة الصورة غير مدعومة (jpg/png/webp)." if session.get("lang")!="en" else "Unsupported image type (jpg/png/webp).", "error")
        return redirect(url_for("subscribe", plan_id=plan_id, cycle=q["cycle"]))
    # فحص توقيع الملف **قبل** أي كتابة: ما ليس صورة ليس إيصالاً، فلا يلمس
    # القرص أصلاً ولا يُنشأ له طلب دفع (AGENTS.md §3.7). الحجم محدود سلفاً
    # بـ MAX_CONTENT_LENGTH فالقراءة إلى الذاكرة مأمونة.
    data = file.read()
    imgchk = pay.validate_bytes(data)
    if not imgchk["ok"]:
        _reason = {"not_an_image": ("الملف ليس صورة صالحة.", "The file is not a valid image."),
                   "too_small":    ("الصورة صغيرة جداً.", "The image is too small."),
                   "too_large":    ("الصورة كبيرة جداً (الحد 8 ميجابايت).", "The image is too large (8MB max)."),
                   }.get(imgchk.get("reason"), ("تعذّر قراءة الصورة.", "Could not read the image."))
        flash(_reason[0] if session.get("lang")!="en" else _reason[1], "error")
        return redirect(url_for("subscribe", plan_id=plan_id, cycle=q["cycle"]))
    # الفحص الآلي قبل الكتابة: ما ليس إيصالاً لتحويل على حسابنا بهذا المبلغ يُرفض
    # هنا — لا ملف ولا طلب دفع ولا تنبيه للأدمن.
    ac, img_hash, refused = _receipt_check(data, q["total"])
    if refused:
        flash(refused, "error")
        return redirect(url_for("subscribe", plan_id=plan_id, cycle=q["cycle"]))
    fname = f"pay_{uid()}_{int(_time.time())}{ext}"
    fpath = os.path.join(UPLOAD_DIR, secure_filename(fname))
    with open(fpath, "wb") as _f:
        _f.write(data)
    pid = db.create_payment(uid(), plan_id, method, q["total"], ref, fname, img_hash,
                            json.dumps(ac, ensure_ascii=False),
                            promo_id=(q["promo"]["id"] if q["promo"] else None),
                            discount=round(q["list_price"] - q["total"], 2),
                            base_amount=q["list_price"], billing_cycle=q["cycle"])
    log.info("payment #%s created user=%s plan=%s cycle=%s amount=%s method=%s promo=%s verdict=%s",
             pid, uid(), plan_id, q["cycle"], q["total"], method, q["promo_code"], ac.get("verdict"))
    # تنبيه الأدمن على تليجرام بزرّي موافقة/رفض (طبقة التحقق الثانية)
    admin_id = db.get_platform("admin_chat_id", "")
    payment = db.get_payment(pid)
    lang = session.get("lang","ar")
    caption = PB.build_caption(payment, session.get("uname",""), _verdict_detail(ac))
    msg_id = manager.send_payment_alert(admin_id, payment, session.get("uname",""), caption, fpath) if admin_id else None
    if msg_id: db.set_payment_msg(pid, msg_id)
    if not msg_id:
        notify_admins(f"💳 طلب دفع جديد #{pid} / New payment — {session.get('uname')} — {q['total']} EGP ({plan_id})"
                      + (f" · كود {q['promo_code']}" if q["promo_code"] else "") + ". راجعه من لوحة الأدمن.")
    flash(("✅ تم استلام إثبات الدفع (#{}). سيتم تفعيل اشتراكك بعد المراجعة والموافقة."
           if lang!="en" else
           "✅ Payment proof received (#{}). Your subscription will activate after review and approval.").format(pid), "ok")
    # ليس `purchase`: الاعتماد يدوي وقد يُرفض. `purchase` يُطلق عند التفعيل
    # الفعلي (راجع `_track_purchase`)، وهذا الحدث الوسيط يقيس نيّة الدفع.
    AN.queue(session, "subscribe_submit", plan=plan_id, cycle=q["cycle"],
             value=float(q["total"]), currency="EGP")
    return redirect(url_for("billing"))

@app.route("/billing")
@login_required
def billing():
    sub = db.get_subscription(uid())
    pays = db.list_payments(uid())
    for x in pays:
        try: x["auto"] = json.loads(x.get("auto_check") or "{}")
        except Exception: x["auto"] = {}
    return react_page("billing", "billing_title",
                      {"sub": sub, "pays": pays,
                       "planName": plans.plan_name(sub["plan"], session.get("lang", i18n.DEFAULT)),
                       "names": _plan_names()})

@app.route("/admin/platform", methods=["GET", "POST"])
@require_roles("admin")
def admin_platform():
    if request.method == "POST":
        for k in ("vodafone_number","instapay_handle","instapay_link",
                  "bank_holder","bank_name","bank_account","bank_iban",
                  "platform_bot_token","admin_chat_id",
                  "support_email","support_whatsapp","support_telegram",
                  "wa_verify_token","wa_app_secret","addon_pay_price"):
            db.set_platform(k, request.form.get(k, "").strip())
        for bad in _save_ops_settings(request.form):
            flash(bad, "error")
        tok = db.get_platform("platform_bot_token",""); adm = db.get_platform("admin_chat_id","")
        if tok and adm:
            ok, msg = manager.start_platform_bot(tok)
            flash(("تم الحفظ. " if session.get("lang")!="en" else "Saved. ")+msg, "ok" if ok else "error")
        else:
            flash("تم الحفظ." if session.get("lang")!="en" else "Saved.", "ok")
        return redirect(url_for("admin_platform"))
    return react_page("admin_platform", "platform_title",
                      {"plat": dict({k: v for k, v in db.all_platform().items() if k != "email_unsub_key"},
                                    mkt_msg_price_egp=f"{mkt_price() / 100:g}",
                                    ai_reply_price_egp=f"{FE.ai_reply_price() / 100:g}"),
                       "running": manager.platform_running(),
                       # هل يستطيع بوت المنصة إنشاء بوتات بضغطة (Bot Management Mode)؟
                       "managed": manager.platform_info(),
                       "capacity": manager.capacity_status()})

@app.route("/admin/platform/test-notify", methods=["POST"])
@require_roles("admin")
def admin_platform_test():
    """رسالة اختبار لكل أدمن — تكشف لماذا لا تصل التنبيهات بدل الصمت."""
    lang = session.get("lang", i18n.DEFAULT)
    ids = db.admin_chat_ids()
    if not ids:
        flash(i18n.t("plat_test_no_admin", lang), "error")
    elif not manager.platform_running():
        flash(i18n.t("plat_test_stopped", lang), "error")
    else:
        for aid in ids:
            ok, err = manager.notify_probe(aid)
            flash(i18n.t("plat_test_ok", lang).format(id=aid) if ok
                  else i18n.t("plat_test_fail", lang).format(id=aid, err=err), "ok" if ok else "error")
    return redirect(url_for("admin_platform"))

# ---------- لوحة تحكم الأدمن ----------
@app.route("/admin")
@require_roles("admin", "support")
def admin_home():
    return react_page("admin_overview", "nav_admin", {"stats": db.platform_stats()}, needs_chart=True)

@app.route("/admin/analytics")
@require_roles("admin")
def admin_analytics():
    """إحصائيات الزوار وقمع التسجيل — للمالك وحده (أرقام العمل)."""
    days = request.args.get("days", "30")
    days = int(days) if days in ("7", "30", "90") else 30
    return react_page("admin_analytics", "adm_analytics", {"a": db.analytics_summary(days)})

# ---------- رسائل البريد: حملات الأدمن (email_campaigns.py) ----------
_EMAIL_PARTS = (("subject", 150), ("preheader", 150), ("title", 150), ("body", 6000), ("cta", 40))

def _email_audience_ok(a):
    return a in db.EMAIL_AUDIENCES or (a.startswith("plan:") and a[5:] in plans.PLANS and a[5:] != "free")

def _email_content(d):
    """مسودة حملة من JSON اللوحة ⇒ محتوى مُطبَّع (بلا تحقق — المعاينة تعمل وأنت تكتب).
    المسار الداخلي (/pricing) يصير رابطاً مطلقاً من PUBLIC_URL وحدها (§14)."""
    def part(p):
        p = p if isinstance(p, dict) else {}
        return {k: str(p.get(k) or "").strip()[:n] for k, n in _EMAIL_PARTS}
    ar, en = part(d.get("ar")), part(d.get("en"))
    url = str(d.get("url") or "").strip()[:500]
    base = mailer.site_base()
    if base and url.startswith("/") and not url.startswith("//"):
        url = base + url
    code = _re.sub(r"\s+", "", str(d.get("code") or ""))[:32].upper()
    return {"ar": ar, "en": en if (en["subject"] or en["body"]) else None, "url": url, "code": code}

def _email_errors(content, kind, audience, lang):
    L = lambda a, e: e if lang == "en" else a
    ar, en, url = content["ar"], content["en"], content["url"]
    if kind not in ("news", "service"):
        return L("اختر نوع الرسالة.", "Pick a message type.")
    if not _email_audience_ok(audience):
        return L("الجمهور غير معروف.", "Unknown audience.")
    if len(ar["subject"]) < 3 or len(ar["body"]) < 10:
        return L("اكتب عنوان الرسالة (3 أحرف على الأقل) ونصها (10 أحرف على الأقل).",
                 "Write the Arabic subject (3+ chars) and body (10+ chars).")
    if en and (len(en["subject"]) < 3 or len(en["body"]) < 10):
        return L("النسخة الإنجليزية ناقصة: اكتب عنوانها ونصها أو امسحهما.",
                 "The English version is incomplete: fill its subject and body, or clear both.")
    base = mailer.site_base()
    if url and not (_re.match(r"^https://[^\s<>\"']+$", url) or (base and url.startswith(base + "/"))):
        return L("رابط الزر لازم يبدأ بـ https:// — أو مسار داخلي مثل /pricing بعد ضبط PUBLIC_URL.",
                 "The button link must start with https:// — or an internal path like /pricing once PUBLIC_URL is set.")
    if content["code"] and not _re.match(r"^[A-Z0-9_-]{2,32}$", content["code"]):
        return L("كود الخصم حروف إنجليزية وأرقام فقط.", "The promo code must be letters and digits only.")
    if kind == "news" and not base:
        return L("رسائل الأخبار تحتاج PUBLIC_URL لرابط إلغاء الاشتراك — اضبطه في .env أولاً.",
                 "News emails need PUBLIC_URL for the unsubscribe link — set it in .env first.")
    return None

def _email_json():
    d = request.get_json(silent=True) or {}
    kind = d.get("kind") if d.get("kind") in ("news", "service") else "news"
    return d, kind, str(d.get("audience") or "all")[:40], _email_content(d)

def _emails_state():
    rows = []
    for c in db.list_email_campaigns():
        try:
            content = json.loads(c["content"] or "{}")
        except ValueError:
            content = {}
        rows.append(dict(c, content=content, running=EC.running(c["id"])))
    return {"campaigns": rows, "today": db.email_sends_today(), "cap": EC.daily_cap()}

@app.route("/admin/emails")
@require_roles("admin")
def admin_emails():
    """حملات البريد للمالك وحده: أخبار وعروض للموافقين، وإشعارات خدمة لكل من له إيميل."""
    from email.utils import parseaddr
    lang = session.get("lang", i18n.DEFAULT)
    me = db.get_user(uid()) or {}
    paid = [p for p in plans.ORDER if p != "free"]
    auds = (*db.EMAIL_AUDIENCES, *(f"plan:{p}" for p in paid))
    name, addr = parseaddr(os.getenv("SMTP_FROM", ""))
    return react_page("admin_emails", "adm_emails", dict(
        _emails_state(), reach=db.email_reach(),
        counts={k: {a: db.email_audience_count(a, k) for a in auds} for k in ("news", "service")},
        plans=[{"id": p, "name": plans.plan_name(p, lang)} for p in paid],
        smtp=mailer.configured(), publicUrl=bool(mailer.site_base()),
        myEmail=me.get("email") or "", sender={"name": name or "BotYalla", "addr": addr}))

@app.route("/admin/emails/status")
@require_roles("admin")
def admin_emails_status():
    return jsonify(_emails_state())

@app.route("/admin/emails/preview", methods=["POST"])
@require_roles("admin")
def admin_emails_preview():
    """الرسالة كما ستصل. الشعار data: بدل cid: (المتصفح لا يفهم cid، و data مسموح في CSP)."""
    import base64
    d, kind, audience, content = _email_json()
    lang = "en" if d.get("lang") == "en" else "ar"
    ar = content["ar"]
    ar["subject"] = ar["subject"] or "عنوان رسالتك"
    ar["body"] = ar["body"] or "اكتب نص رسالتك وسيظهر هنا كما يصل للمشترك تماماً."
    if content["en"]:
        content["en"]["subject"] = content["en"]["subject"] or "Your subject"
        content["en"]["body"] = content["en"]["body"] or "Write your message — it shows here exactly as subscribers get it."
    me = db.get_user(uid()) or {}
    unsub = (mailer.unsub_url(uid()) or "#") if kind == "news" else None
    subject, html, _ = mailer.campaign_email(content, lang, me.get("username", ""), kind, unsub=unsub)
    mark = "data:image/png;base64," + base64.b64encode(mailer._mark()).decode()
    html = html.replace(f"cid:{mailer.MARK_CID}", mark).replace("<head>", '<head><base target="_blank">', 1)
    part = content["en"] if (lang == "en" and content["en"]) else ar
    return jsonify({"html": html, "subject": subject, "preheader": part["preheader"],
                    "count": db.email_audience_count(audience, kind) if _email_audience_ok(audience) else 0})

@app.route("/admin/emails/test", methods=["POST"])
@require_roles("admin")
def admin_emails_test():
    """نسخة تجربة لإيميل الأدمن نفسه — قبل أن تصل المئات."""
    lang = session.get("lang", i18n.DEFAULT)
    L = lambda a, e: e if lang == "en" else a
    if _rate_limited(f"u{uid()}", limit=10, window=3600, bucket="mail_test"):
        return jsonify({"ok": False, "error": i18n.t("ai_rate", lang)})
    d, kind, audience, content = _email_json()
    me = db.get_user(uid()) or {}
    err = _email_errors(content, kind, audience, lang)
    if not err and not mailer.configured():
        err = L("SMTP غير مضبوط على الخادم — راجع docs/EMAIL_DNS.md.", "SMTP is not configured — see docs/EMAIL_DNS.md.")
    if not err and not me.get("email"):
        err = L("أضف إيميلك من صفحة «حسابي» لتصلك رسالة التجربة.", "Add your email on the Account page to receive the test.")
    if err:
        return jsonify({"ok": False, "error": err})
    mlang = "en" if d.get("lang") == "en" else "ar"
    unsub = mailer.unsub_url(uid()) if kind == "news" else None
    subject, html, text = mailer.campaign_email(content, mlang, me["username"], kind, unsub=unsub)
    mailer.send_async(me["email"], ("[TEST] " if mlang == "en" else "[تجربة] ") + subject, html, text)
    return jsonify({"ok": True, "to": mailer._mask(me["email"])})

@app.route("/admin/emails/send", methods=["POST"])
@require_roles("admin")
def admin_emails_send():
    lang = session.get("lang", i18n.DEFAULT)
    L = lambda a, e: e if lang == "en" else a
    d, kind, audience, content = _email_json()
    err = _email_errors(content, kind, audience, lang)
    if not err and not mailer.configured():
        err = L("SMTP غير مضبوط على الخادم — لا شيء سيُرسل. راجع docs/EMAIL_DNS.md.",
                "SMTP is not configured — nothing would be sent. See docs/EMAIL_DNS.md.")
    if not err and db.list_email_campaigns(status="sending"):
        err = L("فيه حملة بتتبعت دلوقتي — استنى تخلص أو أوقفها الأول.",
                "A campaign is already sending — wait for it or stop it first.")
    n = 0 if err else db.email_audience_count(audience, kind)
    if not err and not n:
        err = L("مفيش مستلمين في الجمهور ده.", "Nobody matches this audience.")
    if err:
        return jsonify({"ok": False, "error": err})
    cid = db.create_email_campaign(kind, audience, json.dumps(content, ensure_ascii=False), uid())
    log.info("email campaign #%s started by user=%s kind=%s audience=%s recipients=%s",
             cid, uid(), kind, audience, n)
    EC.start(cid)
    return jsonify(dict(_emails_state(), ok=True, id=cid))

@app.route("/admin/emails/<int:cid>/<any(stop,resume):action>", methods=["POST"])
@require_roles("admin")
def admin_emails_action(cid, action):
    lang = session.get("lang", i18n.DEFAULT)
    L = lambda a, e: e if lang == "en" else a
    camp = db.get_email_campaign(cid)
    if not camp:
        abort(404)
    err = None
    if action == "stop" and camp["status"] == "sending":
        EC.stop(cid)
    elif action == "resume" and camp["status"] == "stopped":
        if db.list_email_campaigns(status="sending"):
            err = L("فيه حملة تانية بتتبعت دلوقتي.", "Another campaign is sending right now.")
        elif not mailer.configured():
            err = L("SMTP غير مضبوط على الخادم.", "SMTP is not configured.")
        elif camp["kind"] == "news" and not mailer.site_base():
            err = L("رسائل الأخبار تحتاج PUBLIC_URL.", "News emails need PUBLIC_URL.")
        else:
            db.set_email_campaign(cid, status="sending", note=None)
            EC.start(cid)
    return jsonify(dict(_emails_state(), ok=not err, error=err))

@app.route("/admin/emails/settings", methods=["POST"])
@require_roles("admin")
def admin_emails_settings():
    """السقف اليومي لرسائل الحملات — تحت حدّ مزوّد SMTP (Brevo المجاني 300/يوم)."""
    lang = session.get("lang", i18n.DEFAULT)
    try:
        cap = int((request.get_json(silent=True) or {}).get("cap"))
    except (TypeError, ValueError):
        cap = 0
    if not 1 <= cap <= 100000:
        return jsonify({"ok": False, "error": "1 – 100000"})
    db.set_platform("email_daily_cap", str(cap))
    return jsonify(dict(_emails_state(), ok=True))

@app.route("/api/admin/stats")
@require_roles("admin", "support")
def api_admin_stats():
    return jsonify({"summary": db.platform_stats(), "daily": db.revenue_daily(14)})

@app.route("/admin/users")
@require_roles("admin", "support")
def admin_users():
    return react_page("admin_users", "admin_users_t",
                      {"users": db.list_all_users(),
                       "plans": [{"id": k, "name": plans.plan_name(k, session.get("lang", i18n.DEFAULT))}
                                 for k in plans.ORDER]})

@app.route("/admin/users/<int:user_id>/role", methods=["POST"])
@require_roles("admin")
def admin_user_role(user_id):
    db.set_user_role(user_id, request.form.get("role", "user"))
    flash("تم تحديث الدور." if session.get("lang")!="en" else "Role updated.", "ok")
    return redirect(url_for("admin_users"))

@app.route("/admin/users/<int:user_id>/block/<int:val>", methods=["POST"])
@require_roles("admin")
def admin_user_block(user_id, val):
    db.set_user_blocked(user_id, bool(val))
    flash("تم التحديث." if session.get("lang")!="en" else "Updated.", "ok")
    return redirect(url_for("admin_users"))

@app.route("/admin/users/<int:user_id>/plan", methods=["POST"])
@require_roles("admin")
def admin_user_plan(user_id):
    plan_id = request.form.get("plan", "free")
    if plan_id == "free":
        db.activate_subscription(user_id, "free", days=3650)
    elif plan_id in plans.PLANS:
        db.activate_subscription(user_id, plan_id, days=30)
    u = db.get_user(user_id)
    log.info("manual plan change user=%s -> %s by admin=%s", user_id, plan_id, uid())
    notify_admins(f"✏️ تعديل يدوي للباقة: {u['username'] if u else user_id} -> {plan_id}")
    flash("تم تحديث الباقة." if session.get("lang")!="en" else "Plan updated.", "ok")
    return redirect(url_for("admin_users"))

@app.route("/admin/payments")
@require_roles("admin", "support")
def admin_payments():
    pays = db.list_payments(limit=200)
    users = {u["id"]: u["username"] for u in db.list_all_users()}
    lang = session.get("lang", "ar")
    for x in pays:
        x["uname"] = users.get(x["user_id"], "?")
        try: x["auto"] = json.loads(x.get("auto_check") or "{}")
        except Exception: x["auto"] = {}
        x["checks"] = pay.check_lines(x["auto"], lang)
        st, sym = pay.VERDICT_STYLE.get(x["auto"].get("verdict", "needs_review"), ("mid", "؟"))
        x["vstyle"] = st; x["vsym"] = sym
    return react_page("admin_payments", "admin_payments_t",
                      {"pays": pays,
                       "names": _plan_names(),
                       # حالة قراءة الإيصالات: بدونها لا رفض آلياً — الأدمن يرى السبب وطريقة الإصلاح
                       "ocr": pay.ocr_status(),
                       "refused24": db.count_receipt_refusals(since=int(_time.time()) - 86400),
                       "refusals": db.recent_receipt_refusals(8)})

@app.route("/admin/payments/<int:pid>/<any(approve,reject):decision>", methods=["POST"])
@require_roles("admin")
def admin_payment_decide(pid, decision):
    status = "approved" if decision == "approve" else "rejected"
    row = db.finalize_payment(pid, status)
    if row:
        # بعد ثبات التسوية وخارج معاملتها: فشل الإيميل لا يمسّها
        mailer.send_payment_receipt(row, status)
        u = db.get_user(row["user_id"])
        if status == "approved":
            settle_payment(row)
        notify_admins(f"{'✅ موافقة' if status=='approved' else '❌ رفض'} دفعة #{pid} — {u['username'] if u else ''} (من الويب)")
        flash(("تمت الموافقة والتفعيل." if status=="approved" else "تم الرفض.") if session.get("lang")!="en"
              else ("Approved & activated." if status=="approved" else "Rejected."), "ok")
    else:
        flash("سبق البتّ في هذا الطلب." if session.get("lang")!="en" else "Already decided.", "error")
    return redirect(url_for("admin_payments"))

# ---------- طلب بوت مخصّص ----------
@app.route("/request-bot", methods=["GET", "POST"])
@login_required
def request_bot():
    plat = _public_plat()
    if request.method == "POST":
        business = request.form.get("business", "").strip()
        desc = request.form.get("description", "").strip()
        budget = request.form.get("budget", "").strip()
        contact = request.form.get("contact", "").strip()
        if len(desc) < 10:
            flash("اكتب وصفاً أوضح لطلبك." if session.get("lang")!="en" else "Please describe your request more clearly.", "error")
            return redirect(url_for("request_bot"))
        rid = db.create_bot_request(uid(), session.get("uname", ""), business, desc, budget, contact)
        notify_admins(f"🛠️ طلب بوت مخصّص جديد #{rid}\n👤 {session.get('uname')}\n🏢 {business}\n💬 {desc[:300]}\n📞 {contact}")
        flash("✅ تم استلام طلبك! سنتواصل معك قريباً." if session.get("lang")!="en"
              else "✅ Request received! We'll contact you soon.", "ok")
        return redirect(url_for("request_bot", sent=1))
    return react_page("request_bot", "req_title",
                      {"plat": plat, "sent": bool(request.args.get("sent"))})

@app.route("/admin/requests")
@require_roles("admin", "support")
def admin_requests():
    return react_page("admin_requests", "admin_requests_t", {"reqs": db.list_bot_requests()})

@app.route("/admin/requests/<int:req_id>/<any(new,in_progress,done,rejected):status>", methods=["POST"])
@require_roles("admin")
def admin_request_status(req_id, status):
    db.set_bot_request_status(req_id, status)
    flash("تم التحديث." if session.get("lang")!="en" else "Updated.", "ok")
    return redirect(url_for("admin_requests"))

# ---------- الدعم والشكاوى (support_desk.py) ----------
def _alert_ticket(tid, body, followup=False):
    """التذكرة تصل كل أدمن فوراً على بوت المنصة. best-effort: محفوظة في اللوحة أياً كان."""
    t = db.get_ticket(tid)
    if not t:
        return False
    sent = False
    for aid in db.admin_chat_ids():
        sent = manager.notify_text(aid, SD.alert_text(t, body, followup),
                                   reply_markup=SD.alert_markup(tid)) or sent
    if not sent:
        log.warning("ticket #T%s saved but not delivered on Telegram "
                    "(platform bot stopped or admin_chat_id missing)", tid)
    return sent

@app.route("/support", methods=["GET", "POST"])
@login_required
def support():
    lang = session.get("lang", i18n.DEFAULT)
    if request.method == "POST":
        body = (request.form.get("body") or "").strip()[:SD.BODY_MAX]
        subject = (request.form.get("subject") or "").strip()[:SD.SUBJECT_MAX] or body[:60]
        if len(body) < SD.BODY_MIN:
            flash(i18n.t("sup_short", lang), "error")
            return redirect(url_for("support"))
        if _rate_limited(f"u{uid()}", limit=6, window=3600, bucket="ticket"):
            flash(i18n.t("ai_rate", lang), "error")
            return redirect(url_for("support"))
        tid = db.create_ticket(uid(), SD.norm_kind(request.form.get("kind")), subject, body)
        log.info("ticket #T%s opened by user=%s", tid, uid())
        _alert_ticket(tid, body)
        flash(i18n.t("sup_sent", lang).format(id=tid), "ok")
        return redirect(url_for("support"))
    return react_page("support", "nav_support",
                      {"tickets": db.list_tickets(user_id=uid()), "plat": _public_plat()})

@app.route("/support/<int:tid>/reply", methods=["POST"])
@login_required
def support_reply(tid):
    lang = session.get("lang", i18n.DEFAULT)
    t = db.get_ticket(tid)
    if not t or t["user_id"] != uid():
        abort(404)
    body = (request.form.get("body") or "").strip()[:SD.BODY_MAX]
    if len(body) < 2:
        flash(i18n.t("sup_short", lang), "error")
    elif _rate_limited(f"u{uid()}", limit=20, window=3600, bucket="ticket_msg"):
        flash(i18n.t("ai_rate", lang), "error")
    else:
        db.add_ticket_msg(tid, "user", body, "web")
        _alert_ticket(tid, body, followup=True)
        flash(i18n.t("sup_reply_sent", lang), "ok")
    return redirect(url_for("support") + f"#t{tid}")

@app.route("/admin/tickets")
@require_roles("admin", "support")
def admin_tickets():
    lang = session.get("lang", i18n.DEFAULT)
    tickets = db.list_tickets()
    for tk in tickets:
        if tk["kind"] == "wa_setup":
            tk["wa"] = _wa_setup_status(tk, lang)
    return react_page("admin_tickets", "nav_tickets", {"tickets": tickets})

# ---------- ربط واتساب بمساعدة الفريق (مشمول في باقات واتساب) ----------
def _active_plan(user_id):
    sub = db.get_subscription(user_id)
    return sub["plan"] if sub["status"] == "active" else "free"

def _wa_setup_status(tk, lang):
    """ما يلزم الفريق قبل الربط: هل باقة العميل تشمل واتساب، وهل بقي له مكان لبوت."""
    pid = _active_plan(tk["user_id"])
    p = plans.plan(pid)
    bots = db.list_bots(tk["user_id"])
    subj = tk.get("subject") or ""
    return {"plan": plans.plan_name(pid, lang), "ok": bool(p.get("whatsapp")),
            "bots": len(bots), "max": p["max_bots"], "full": len(bots) >= p["max_bots"],
            "waBots": sum(1 for b in bots if (b.get("channel") or "telegram") == "whatsapp"),
            "biz": subj.split(" — ", 1)[1].strip() if " — " in subj else ""}

_WA_META = {"yes":    ("عنده حساب Meta Business", "Has a Meta Business account"),
            "no":     ("معندوش حساب Meta Business", "No Meta Business account"),
            "unsure": ("مش متأكد من حساب Meta Business", "Not sure about Meta Business")}

@app.route("/whatsapp/assist", methods=["POST"])
@login_required
def wa_assist():
    """«سيبها علينا»: فريقنا يربط واتساب للعميل — مشمولة في باقات واتساب وحدها.
    الطلب تذكرة wa_setup تصل الفريق فوراً على بوت المنصة، والمحادثة كلها (ما يلزم من
    العميل) في صفحة الدعم. طلب مفتوح واحد لكل عميل: الثاني يرجّع الأول لا تذكرة جديدة."""
    lang = session.get("lang", i18n.DEFAULT)
    ar = lang != "en"
    if not plans.plan(_active_plan(uid())).get("whatsapp"):
        return jsonify({"ok": False, "error": ("ربط واتساب مشمول في باقة «واتساب» فأعلى — رقّي باقتك أولاً."
                                               if ar else "WhatsApp setup is included from the «WhatsApp» "
                                               "plan — upgrade first.")}), 403
    open_tid = db.open_ticket_of_kind(uid(), "wa_setup")
    if open_tid:
        return jsonify({"ok": True, "id": open_tid, "existing": True})
    d = request.get_json(silent=True) or {}
    biz = str(d.get("business") or "").strip()[:80]
    number = _re.sub(r"\D", "", str(d.get("number") or ""))
    meta = d.get("meta") if d.get("meta") in _WA_META else "unsure"
    contact = str(d.get("contact") or "").strip()[:60]
    notes = str(d.get("notes") or "").strip()[:1000]
    if not biz or not 8 <= len(number) <= 15:
        return jsonify({"ok": False, "error": ("اكتب اسم النشاط ورقم واتساب صحيح." if ar else
                                               "Enter your business name and a valid WhatsApp number.")}), 400
    if _rate_limited(f"u{uid()}", limit=3, window=86400, bucket="wa_assist"):
        return jsonify({"ok": False, "error": i18n.t("ai_rate", lang)}), 429
    shown = number if number.startswith("0") else "+" + number
    if ar:
        subject = f"ربط واتساب — {biz}"
        body = (f"طلب ربط واتساب (مشمول في الباقة)\n• النشاط: {biz}\n• رقم واتساب للبوت: {shown}\n"
                f"• {_WA_META[meta][0]}" + (f"\n• للتواصل: {contact}" if contact else "")
                + (f"\n• ملاحظات: {notes}" if notes else ""))
    else:
        subject = f"WhatsApp setup — {biz}"
        body = (f"WhatsApp setup request (included in plan)\n• Business: {biz}\n• Bot number: {shown}\n"
                f"• {_WA_META[meta][1]}" + (f"\n• Contact: {contact}" if contact else "")
                + (f"\n• Notes: {notes}" if notes else ""))
    tid = db.create_ticket(uid(), "wa_setup", subject[:SD.SUBJECT_MAX], body[:SD.BODY_MAX])
    log.info("wa_setup ticket #T%s opened by user=%s", tid, uid())
    _alert_ticket(tid, body)
    return jsonify({"ok": True, "id": tid, "existing": False})

@app.route("/admin/tickets/<int:tid>/wa-connect", methods=["POST"])
@require_roles("admin", "support")
def admin_wa_connect(tid):
    """الفريق يربط واتساب نيابةً عن العميل — من تذكرة wa_setup وحدها، فلا يُنشئ الدعم
    بوتاً في أي حساب بلا طلب صاحبه. البوت يُنشأ في حساب العميل **وبحدود باقته هو**
    (واتساب + max_bots) لا بصلاحيات الفريق. التوكن لا يُكتب في التذكرة ولا يُعرض."""
    ar = session.get("lang") != "en"
    back = redirect(url_for("admin_tickets") + f"#t{tid}")
    t = db.get_ticket(tid)
    if not t:
        abort(404)
    if t["kind"] != "wa_setup":
        flash("الربط من تذاكر «ربط واتساب» فقط." if ar else
              "Connect only from «WhatsApp setup» tickets.", "error")
        return back
    st = _wa_setup_status(t, "ar" if ar else "en")
    if not st["ok"]:
        flash((f"باقة العميل ({st['plan']}) لا تشمل واتساب — اطلب منه الترقية أولاً." if ar else
               f"The customer's plan ({st['plan']}) doesn't include WhatsApp — ask them to upgrade first."),
              "error")
        return back
    if st["full"]:
        flash((f"العميل وصل للحد الأقصى لبوتات باقته ({st['max']})." if ar else
               f"The customer reached their plan's bot limit ({st['max']})."), "error")
        return back
    name = (request.form.get("name") or "").strip()[:60]
    template = request.form.get("template", "")
    phone_id = (request.form.get("wa_phone_id") or "").strip()
    wa_token = (request.form.get("wa_token") or "").strip()
    waba = (request.form.get("waba_id") or "").strip()
    if not (name and phone_id.isdigit() and wa_token and template in T.TEMPLATES) or \
            (waba and not waba.isdigit()):
        flash("أكمل: الاسم والنوع وPhone Number ID (أرقام) والتوكن." if ar else
              "Fill in the name, type, Phone Number ID (digits) and token.", "error")
        return back
    chk = wa_verify(phone_id, wa_token)
    if not chk["ok"]:
        flash((f"❌ بيانات واتساب غير صالحة: {chk['error']}" if ar else
               f"❌ Invalid WhatsApp credentials: {chk['error']}"), "error")
        return back
    info = {"username": chk.get("number") or phone_id, "name": chk.get("name") or name}
    cfg = T.initial_config(name, template, info, "")
    cfg["wa_token"] = wa_token
    cfg["created_via"] = "staff"
    if waba:
        cfg["wa_waba_id"] = waba
    try:
        new_id = db.create_bot(t["user_id"], name, f"wa:{phone_id}", template, cfg, "whatsapp")
    except Exception:
        log.exception("wa connect for ticket #T%s", tid)
        flash("تعذّر الإنشاء — غالباً الرقم ده مربوط ببوت آخر بالفعل." if ar else
              "Could not create it — this number is most likely connected to another bot already.", "error")
        return back
    number = info["username"]
    msg = ((f"✅ ربطنا واتساب لبوتك «{name}» على الرقم {number}.\n"
            "البوت في «بوتاتي» الآن: افتحه، راجع رسالة الترحيب، ثم اضغط «تشغيل». أي سؤال؟ ردّ هنا.")
           if db.user_lang(t["user_id"]) != "en" else
           (f"✅ We connected WhatsApp to your bot «{name}» on {number}.\n"
            "It's in «My bots» now: open it, review the welcome message, then press «Start». "
            "Questions? Reply here."))
    res = SD.record_staff_reply(tid, msg, "web")
    tg_ok = bool(res and res["chat"]) and manager.notify_text(res["chat"], res["text"])
    log.info("wa connect: staff=%s user=%s ticket=#T%s bot=%s", uid(), t["user_id"], tid, new_id)
    notify_admins(f"🤖 بوت واتساب جديد (ربط من الفريق) / New WhatsApp bot (staff setup): «{name}» "
                  f"— {t.get('username')} · {session.get('uname')}")
    flash(((f"✅ اتعمل بوت واتساب «{name}» في حساب {t.get('username')} واتبلّغ العميل" if ar else
            f"✅ WhatsApp bot «{name}» created in {t.get('username')}'s account; the customer was notified")
           + (" + Telegram" if tg_ok else "") + (" + Email" if res and res["emailed"] else "")), "ok")
    return back

@app.route("/admin/tickets/<int:tid>/reply", methods=["POST"])
@require_roles("admin", "support")
def admin_ticket_reply(tid):
    lang = session.get("lang", i18n.DEFAULT)
    body = (request.form.get("body") or "").strip()[:SD.BODY_MAX]
    if len(body) < 2:
        flash(i18n.t("sup_short", lang), "error")
        return redirect(url_for("admin_tickets"))
    res = SD.record_staff_reply(tid, body, "web")
    if not res:
        abort(404)
    tg_ok = bool(res["chat"]) and manager.notify_text(res["chat"], res["text"])
    flash(i18n.t("sup_staff_sent", lang) + (" + Telegram" if tg_ok else "")
          + (" + Email" if res["emailed"] else ""), "ok")
    return redirect(url_for("admin_tickets") + f"#t{tid}")

@app.route("/admin/tickets/<int:tid>/<any(close,open):action>", methods=["POST"])
@require_roles("admin", "support")
def admin_ticket_status(tid, action):
    db.set_ticket_status(tid, "closed" if action == "close" else "open")
    flash(i18n.t("sup_closed" if action == "close" else "sup_opened",
                 session.get("lang", i18n.DEFAULT)), "ok")
    return redirect(url_for("admin_tickets"))

# ---------- حساب المستخدم (تعديل الاسم/كلمة المرور) ----------
@app.route("/account", methods=["GET", "POST"])
@login_required
def account():
    me = db.get_user(uid())
    if request.method == "POST":
        cur_pw = request.form.get("current_password", "")
        if not auth.verify_password(cur_pw, me["pw_hash"]):
            flash("كلمة المرور الحالية غير صحيحة." if session.get("lang")!="en" else "Current password is incorrect.", "error")
            return redirect(url_for("account"))
        new_user = request.form.get("username", "").strip()
        new_pw = request.form.get("new_password", "").strip()
        # يُفحص الاسم عند تغييره فقط: النموذج يرسل الاسم الحالي دائماً
        # (defaultValue)، وحسابات قديمة سُجّلت قبل USERNAME_RE قد لا تطابقه —
        # فحصه دائماً كان سيمنع أصحابها من تغيير كلمة المرور نفسها.
        _l = session.get("lang", i18n.DEFAULT)
        if new_user and new_user != me["username"]:
            k = ACC.username_problem(new_user) or ("u_taken" if db.username_taken(new_user, me["id"]) else None)
            if k:
                flash(ACC.msg(k, _l), "error")
                return redirect(url_for("account"))
        if new_pw:
            probs = ACC.password_problems(new_pw, new_user or me["username"], me.get("email") or "")
            if probs or new_pw != request.form.get("new_password2", new_pw):
                flash(ACC.msg(probs[0] if probs else "p_match", _l), "error")
                return redirect(url_for("account"))
        # الإيميل يُعالج فقط لو أرسله النموذج: بناء واجهة أقدم بلا هذا الحقل
        # يجب ألا يمسح إيميلاً محفوظاً. ويُفحص كله **قبل** أي كتابة.
        lang = session.get("lang", i18n.DEFAULT)
        new_email = _norm_email(request.form.get("email", ""))
        email_changed = "email" in request.form and new_email != (me.get("email") or "")
        if email_changed and new_email:
            if not EMAIL_RE.match(new_email):
                flash(i18n.t("email_invalid", lang), "error")
                return redirect(url_for("account"))
            other = db.get_user_by_email(new_email)
            if other and other["id"] != me["id"]:
                flash(i18n.t("email_taken", lang), "error")
                return redirect(url_for("account"))
        new_hash = auth.hash_password(new_pw) if new_pw else None
        ok, err = db.update_user_credentials(
            uid(),
            username=new_user if (new_user and new_user != me["username"]) else None,
            pw_hash=new_hash)
        if not ok and err == "username_taken":
            flash("اسم المستخدم مستخدم بالفعل." if session.get("lang")!="en" else "Username already taken.", "error")
            return redirect(url_for("account"))
        if email_changed:
            ok, err = db.set_user_email(uid(), new_email or None)
            if not ok:
                flash(i18n.t("email_taken", lang), "error")
                return redirect(url_for("account"))
            if new_email and mailer.configured():          # بريد جديد = كود تأكيد جديد
                _send_verify(db.get_user(uid()), lang)
        if new_hash:
            db.set_setting(uid(), "pw_set", "1")
        if new_user: session["uname"] = new_user
        if new_hash:
            # هذه الجلسة تبقى، وكل جلسة أخرى (جهاز آخر أو مسروقة) تنتهي.
            session["pwv"] = _pw_stamp(new_hash)
        flash("تم تحديث بيانات حسابك ✅" if session.get("lang")!="en" else "Account updated ✅", "ok")
        return redirect(url_for("account"))
    return react_page("account", "account_title", {
        "me": dict(me, pw_hash=None),
        "tgLinked": bool(db.get_setting(uid(), "tg_chat_id")),
        "tgFallback": bool(db.user_tg_channel(uid())),
        "hasPlatformBot": bool(db.get_platform("platform_bot_token", "")),
        "emailNews": db.email_news_on(uid()),
        "identities": db.list_identities(uid()),
        "pwSet": db.get_setting(uid(), "pw_set", "1") != "0",
        **_auth_props(),
    })

@app.route("/account/profile", methods=["POST"])
@login_required
def account_profile():
    """بيانات النشاط (الهاتف · السن · نوع الحساب) — بلا كلمة مرور: ليست بيانات دخول.
    تغيير الهاتف يُسقط تأكيده."""
    lang = session.get("lang", i18n.DEFAULT)
    f = request.form
    phone = ACC.normalize_phone(f.get("phone_cc", "+20"), f.get("phone", ""))
    age, ak = ACC.parse_age(f.get("age"))
    entity = f.get("entity_type", "")
    err = ("phone_bad" if not phone else ak if ak else None if entity in ACC.ENTITIES else "entity_bad")
    if not err:
        ok, err = db.set_user_profile(uid(), phone, age, entity)
    if err:
        flash(ACC.msg(err, lang), "error")
    else:
        flash("تم حفظ بياناتك ✅" if lang != "en" else "Details saved ✅", "ok")
    return redirect(url_for("account"))

@app.route("/account/unlink/<any(google,facebook):provider>", methods=["POST"])
@login_required
def account_unlink(provider):
    """فك ربط جوجل/فيسبوك. **لا تُفك آخر طريقة دخول:** حساب بلا كلمة مرور (pw_set=0) بهوية
    واحدة كان سيُقفل على صاحبه — يضبط كلمة مرور أولاً من «نسيت كلمة المرور». بعد الفك لا
    يُعاد الربط تلقائياً بالبريد عند الدخول بنفس الحساب (oauth_off_<provider>)."""
    lang = session.get("lang", i18n.DEFAULT)
    name = _OAUTH_NAME[provider][1 if lang == "en" else 0]
    ids = db.list_identities(uid())
    if provider not in ids:
        flash(f"{name} مش مربوط بحسابك." if lang != "en" else f"{name} isn't linked to your account.", "error")
    elif db.get_setting(uid(), "pw_set", "1") == "0" and len(ids) == 1:
        flash(f"{name} هو طريقة الدخول الوحيدة لحسابك — اضبط كلمة مرور الأول من «نسيت كلمة المرور»، "
              f"وبعدين فك الربط." if lang != "en" else
              f"{name} is your only way to sign in — set a password first via “Forgot password”, then unlink.",
              "error")
    else:
        db.remove_identity(uid(), provider)
        db.set_setting(uid(), f"oauth_off_{provider}", "1")
        log.info("identity %s unlinked user=%s", provider, uid())
        flash(f"تم فك ربط {name} ✅ — تقدر تربطه تاني في أي وقت." if lang != "en"
              else f"{name} unlinked ✅ — you can link it again anytime.", "ok")
    return redirect(url_for("account"))

# ---------- الصورة الشخصية / لوجو النشاط ----------
AVATAR_DIR = os.path.join(UPLOAD_DIR, "avatars")
AVATAR_MAX = 3 * 1024 * 1024          # 3MB قبل إعادة الرسم
AVATAR_PX = 256

def _avatar_url(user_id):
    """رابط الصورة بنسخة (?v=) تتغيّر مع كل رفع — فالتخزين المؤقت لا يعرض القديمة."""
    name = db.get_setting(user_id, "avatar") if user_id else None
    return url_for("user_avatar", user_id=user_id, v=name.rsplit("_", 1)[-1].split(".")[0]) if name else None

def _drop_avatar(user_id):
    old = db.get_setting(user_id, "avatar")
    if old:
        try:
            os.remove(os.path.join(AVATAR_DIR, secure_filename(old)))
        except OSError:
            pass
        db.set_setting(user_id, "avatar", "")

@app.route("/account/avatar", methods=["POST"])
@login_required
def account_avatar():
    """صورة شخصية أو لوجو الشركة. تُعاد رسمها بـ Pillow: مربع 256px WebP بلا بيانات EXIF (موقع GPS
    في صور الموبايل) ولا بايت واحد من الملف الأصلي — ما يُحفظ صورة نظيفة لا الملف المرفوع."""
    lang = session.get("lang", i18n.DEFAULT)
    L = lambda a, e: e if lang == "en" else a
    if _rate_limited(f"u{uid()}", limit=20, window=3600, bucket="avatar"):
        flash(i18n.t("ai_rate", lang), "error")
        return redirect(url_for("account"))
    f = request.files.get("avatar")
    data = f.read(AVATAR_MAX + 1) if f else b""
    if not data:
        flash(L("اختار صورة الأول.", "Choose an image first."), "error")
        return redirect(url_for("account"))
    if len(data) > AVATAR_MAX:
        flash(L("الصورة أكبر من 3MB — اختار صورة أصغر.", "The image is over 3MB — pick a smaller one."), "error")
        return redirect(url_for("account"))
    try:
        from PIL import Image, ImageOps
        im = Image.open(io.BytesIO(data))
        # الأبعاد تُفحص قبل فكّ البكسلات: صورة «قنبلة» صغيرة الحجم ضخمة الأبعاد تستهلك الذاكرة
        if im.format not in ("JPEG", "PNG", "WEBP") or im.width * im.height > 40_000_000:
            raise ValueError(f"refused {im.format} {im.size}")
        im.load()
        im = ImageOps.fit(ImageOps.exif_transpose(im).convert("RGBA"), (AVATAR_PX, AVATAR_PX), Image.LANCZOS)
        os.makedirs(AVATAR_DIR, exist_ok=True)
        name = f"{uid()}_{_secrets.token_hex(6)}.webp"
        im.save(os.path.join(AVATAR_DIR, name), "WEBP", quality=88, method=4)
    except Exception:
        log.info("avatar refused for user=%s", uid(), exc_info=True)
        flash(L("الملف مش صورة صالحة — استخدم JPG أو PNG أو WebP.", "That isn't a valid image — use JPG, PNG or WebP."),
              "error")
        return redirect(url_for("account"))
    _drop_avatar(uid())
    db.set_setting(uid(), "avatar", name)
    flash(L("تم تحديث الصورة ✅", "Picture updated ✅"), "ok")
    return redirect(url_for("account"))

@app.route("/account/avatar/remove", methods=["POST"])
@login_required
def account_avatar_remove():
    _drop_avatar(uid())
    flash("تم حذف الصورة." if session.get("lang") != "en" else "Picture removed.", "ok")
    return redirect(url_for("account"))

@app.route("/u/<int:user_id>/avatar")
@login_required
def user_avatar(user_id):
    """صاحب الحساب وفريق المنصة فقط — الصورة بيانات شخصية لا ملف عام (ليست في static/)."""
    if user_id != uid() and current_role() not in ("admin", "support"):
        abort(404)
    name = secure_filename(db.get_setting(user_id, "avatar") or "")
    if not name or not os.path.exists(os.path.join(AVATAR_DIR, name)):
        abort(404)
    resp = send_from_directory(AVATAR_DIR, name, mimetype="image/webp", max_age=86400)
    resp.headers["Cache-Control"] = "private, max-age=86400"
    return resp

@app.route("/account/verify-phone", methods=["POST"])
@login_required
def account_verify_phone():
    """رابط تأكيد الهاتف عبر بوت المنصة: العميل يشارك رقمه بزرّ تليجرام (مجاناً، وتليجرام
    يثبت أن الرقم رقمه) — platform_bot يطابقه برقم الحساب ويربط تليجرام للتنبيهات."""
    lang = session.get("lang", i18n.DEFAULT)
    if _rate_limited(f"u{uid()}", limit=10, window=3600, bucket="tg_link"):   # ينتظر تليجرام
        return jsonify({"ok": False, "error": i18n.t("ai_rate", lang)})
    if not (db.get_user(uid()) or {}).get("phone"):
        return jsonify({"ok": False, "error": "أضف رقم هاتفك أولاً." if lang != "en" else "Add your phone number first."})
    token = db.get_platform("platform_bot_token", "")
    info = tg.validate_token(token) if token else {}
    if not info.get("ok") or not info.get("username"):
        return jsonify({"ok": False, "error": i18n.t("tg_link_no_bot", lang)})
    code = _secrets.token_hex(6)
    db.set_phone_code(uid(), code)
    return jsonify({"ok": True, "link": f"https://t.me/{info['username']}?start=phone-{code}"})

@app.route("/account/email-prefs", methods=["POST"])
@login_required
def account_email_prefs():
    """أخبار وعروض بالبريد: موافقة صريحة يغيّرها صاحب الحساب وحده (بلا كلمة مرور —
    ليست بيانات دخول). رسائل الحساب المهمة لا تتأثر بها."""
    lang = session.get("lang", i18n.DEFAULT)
    on = request.form.get("email_news") == "1"
    me = db.get_user(uid()) or {}
    if on and not me.get("email"):
        flash("أضف إيميلك أولاً." if lang != "en" else "Add your email first.", "error")
    else:
        db.set_email_news(uid(), on)
        flash((("✅ هتوصلك أخبار وعروض BotYalla على إيميلك." if on else
                "تم إيقاف رسائل الأخبار والعروض. رسائل حسابك المهمة (الإيصالات والاسترجاع) مستمرة.")
               if lang != "en" else
               ("✅ You'll get BotYalla news and offers by email." if on else
                "News and offers are off. Important account emails (receipts, password reset) continue.")),
              "ok")
    return redirect(url_for("account"))

@app.route("/account/link-telegram", methods=["POST"])
@login_required
def account_link_telegram():
    """يولّد رابط ربط لمرة واحدة عبر بوت المنصة، ليصل العميل تذكير الاشتراك."""
    if _rate_limited(f"u{uid()}", limit=10, window=3600, bucket="tg_link"):   # ينتظر تليجرام
        return jsonify({"ok": False, "error": i18n.t("ai_rate", session.get("lang", i18n.DEFAULT))})
    token = db.get_platform("platform_bot_token", "")
    if not token:
        return jsonify({"ok": False, "error": i18n.t("tg_link_no_bot",
                        session.get("lang", i18n.DEFAULT))})
    info = tg.validate_token(token)
    if not info.get("ok") or not info.get("username"):
        return jsonify({"ok": False, "error": i18n.t("tg_link_no_bot",
                        session.get("lang", i18n.DEFAULT))})
    code = _secrets.token_hex(4)
    db.set_tg_link_code(uid(), code)
    return jsonify({"ok": True,
                    "link": f"https://t.me/{info['username']}?start=link-{code}"})


@app.route("/admin/users/add", methods=["POST"])
@require_roles("admin")
def admin_user_add():
    u = request.form.get("username", "").strip()
    pw = request.form.get("password", "")
    role = request.form.get("role", "user")
    k = ACC.username_problem(u) or ("u_taken" if db.username_taken(u) else None)
    probs = ACC.password_problems(pw, u)
    if k or probs:
        flash(ACC.msg(k or probs[0], session.get("lang", i18n.DEFAULT)), "error")
        return redirect(url_for("admin_users"))
    user_id, err = db.admin_create_user(u, auth.hash_password(pw), role)
    if err == "username_taken":
        flash("اسم المستخدم موجود بالفعل." if session.get("lang")!="en" else "Username already exists.", "error")
    else:
        flash(f"تم إنشاء الحساب «{u}» ({role}) ✅" if session.get("lang")!="en" else f"Account '{u}' ({role}) created ✅", "ok")
    return redirect(url_for("admin_users"))

@app.route("/admin/payments/<int:pid>/screenshot")
@require_roles("admin", "support")
def admin_payment_screenshot(pid):
    p = db.get_payment(pid)
    if not p or not p.get("screenshot"):
        abort(404)
    # اسم الملف مولّد داخلياً وآمن؛ نتحقق أنه داخل مجلد الرفع
    from werkzeug.utils import secure_filename as _sf
    fname = _sf(p["screenshot"])
    if not os.path.exists(os.path.join(UPLOAD_DIR, fname)):
        abort(404)
    return send_from_directory(UPLOAD_DIR, fname)

@app.route("/bot/<int:bot_id>/media/<int:media_id>")
@login_required
def bot_media(bot_id, media_id):
    """ملفات العملاء خاصة: خارج static/ وتُقدَّم فقط لمالك البوت.
    الملكية مفروضة في الاستعلام نفسه (bot_id شرط) لا بفحص لاحق."""
    _owned(bot_id)
    m = db.get_media(media_id, bot_id=bot_id)
    if not m:
        abort(404)
    from werkzeug.utils import secure_filename as _sf
    fname = _sf(m["fname"])
    if not os.path.exists(media_store.path_of(fname)):
        abort(404)
    # النوع من سجلّنا (المستنتج من بايتات الملف) لا من ترويسة أرسلها أحد.
    # الصور والصوت تُعرض في مكانها؛ ما عداها يُنزَّل ولا يُفتح داخل نطاقنا.
    inline = m["kind"] in ("image", "audio", "video")
    resp = send_from_directory(media_store.BASE_DIR, fname, mimetype=m.get("mime"),
                               as_attachment=not inline)
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["Cache-Control"] = "private, max-age=3600"
    return resp

@app.route("/bot/<int:bot_id>/sync-telegram", methods=["POST"])
@login_required
def sync_telegram(bot_id):
    b = _owned(bot_id)
    if (b.get("channel") or "telegram") != "telegram":
        flash("هذه المزامنة لبوتات تليجرام فقط." if session.get("lang") != "en"
              else "This sync is for Telegram bots only.", "error")
        return redirect(url_for("bot_detail", bot_id=bot_id))
    res = sync_bot_telegram(b)
    if res.get("ok"):
        flash("تم تحديث بروفايل البوت على تليجرام رسمياً ✅" if session.get("lang")!="en"
              else "Bot profile updated on Telegram ✅", "ok")
    else:
        flash(("بعض الإعدادات لم تُحفظ: " if session.get("lang")!="en" else "Some settings failed: ")
              + "، ".join(res.get("errors", []))[:200], "error")
    return redirect(url_for("bot_detail", bot_id=bot_id))

# ============================================================================
#  الوصول للبوت: رابط مباشر · QR · ملصق للطباعة  (TESTER_FEEDBACK_PLAN §2)
# ============================================================================
_QR_SOURCES = ("qr", "poster", "share")
_PEER_RE = _re.compile(r"^(tg|wa):\d{1,20}\Z")


def _uses_engine(b):
    """هل يمرّ البوت بمحرك الفلو (فتعمل عليه أوضاع الذكاء الاصطناعي والوسائط)؟
    واتساب كله يمرّ به؛ وعلى تليجرام قوالب المحادثة وحدها."""
    return (b.get("channel") or "telegram") == "whatsapp" or b.get("template") in ai.FLOW_TEMPLATES


def _own_asset_id(v):
    """معرّف ملف من مكتبة المستخدم الحالي أو None — لا يُحفظ مرجع لملف غيره."""
    try:
        aid = int(str(v or "").strip())
    except ValueError:
        return None
    return aid if aid > 0 and db.get_asset(aid, owner_id=uid()) else None


def _bot_links(b):
    """روابط الوصول للبوت. لكل مصدر معامل start مختلف (src-link · src-qr ·
    src-poster · src-share) فتقول التحليلات من أين جاء العميل."""
    cfg = json.loads(b.get("config_json") or "{}")
    if (b.get("channel") or "telegram") == "whatsapp":
        digits = _re.sub(r"\D", "", cfg.get("bot_username") or "")
        if len(digits) < 8:
            return None
        base = f"https://wa.me/{digits}"
        # «start» من كلمات بدء الفلو في واتساب — الرابط يفتح المحادثة ويبدأها
        return {"kind": "whatsapp", "handle": f"+{digits}", "plain": base,
                "open": base + "?text=" + _up.quote("start"), "share": base + "?text=" + _up.quote("start"),
                "qr": url_for("bot_qr", bot_id=b["id"]), "poster": url_for("bot_poster", bot_id=b["id"])}
    uname = (cfg.get("bot_username") or "").strip().lstrip("@")
    if not _re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{3,31}", uname):
        return None
    base = f"https://t.me/{uname}"
    return {"kind": "telegram", "handle": f"@{uname}", "plain": base,
            "open": base + "?start=src-link", "share": base + "?start=src-share",
            "qr": url_for("bot_qr", bot_id=b["id"]), "poster": url_for("bot_poster", bot_id=b["id"])}


def _qr_target(links, src):
    return f"{links['plain']}?start=src-{src}" if links["kind"] == "telegram" else links["open"]


def _qr_svg(data, scale=8, dark="#07090F"):
    """رمز QR كـ SVG من الخادم — حادّ بأي حجم، بلا صورة خارجية ولا سكربت."""
    import segno
    buf = io.BytesIO()
    segno.make(data, error="m").save(buf, kind="svg", scale=scale, border=2, dark=dark,
                                     light="#ffffff", xmldecl=False, svgns=True)
    return buf.getvalue().decode("utf-8")


_QR_ROWS = {}


def _qr_rows(data):
    """مصفوفة QR كصفوف «0/1» يرسمها React مساراً واحداً — بلا innerHTML ولا صورة.
    الذاكرة محدودة: الرابط واحد تقريباً لكل زائر (التسجيل أو اللوحة)."""
    rows = _QR_ROWS.get(data)
    if rows is None:
        import segno
        rows = ["".join("1" if c else "0" for c in r) for r in segno.make(data, error="m").matrix]
        if len(_QR_ROWS) < 32:
            _QR_ROWS[data] = rows
    return rows


@app.route("/bot/<int:bot_id>/qr.svg")
@login_required
def bot_qr(bot_id):
    b = _owned(bot_id)
    links = _bot_links(b)
    if not links:
        abort(404)
    src = request.args.get("src", "qr")
    resp = Response(_qr_svg(_qr_target(links, src if src in _QR_SOURCES else "qr")),
                    mimetype="image/svg+xml")
    resp.headers["Cache-Control"] = "private, max-age=300"
    if request.args.get("dl"):
        resp.headers["Content-Disposition"] = f'attachment; filename="bot-{bot_id}-qr.svg"'
    return resp


@app.route("/bot/<int:bot_id>/poster")
@login_required
def bot_poster(bot_id):
    """ملصق A4 للطباعة: اسم النشاط ورمز QR كبير ورابط البوت — على الكاونتر وفي
    العبوات والمنشورات. بلا تذييل BotYalla لأصحاب العلامة البيضاء."""
    b = _owned(bot_id)
    links = _bot_links(b)
    if not links:
        abort(404)
    cfg = json.loads(b["config_json"] or "{}")
    lang = session.get("lang", i18n.DEFAULT)
    white = current_role() in ("admin", "support") or bool(plans.plan(_plan_id()).get("white_label"))
    return render_template("poster.html", lang=lang, dir=i18n.dir_for(lang),
                           name=cfg.get("business_name") or b["name"], handle=links["handle"],
                           link=links["plain"], channel=links["kind"],
                           qr=Markup(_qr_svg(_qr_target(links, "poster"), scale=10)),
                           back=url_for("bot_detail", bot_id=bot_id), branded=not white)


# ============================================================================
#  إنشاء بوت بضغطة — Telegram Managed Bots  (TESTER_FEEDBACK_PLAN §1)
# ============================================================================
@app.route("/bot/create/managed", methods=["POST"])
@login_required
def bot_create_managed():
    """يولّد رابطاً لمرة واحدة إلى بوت المنصة (زر + QR). الإنشاء نفسه يحدث حين
    يؤكّد المستخدم داخل تليجرام — راجع managed_bots.py."""
    lang = session.get("lang", i18n.DEFAULT)
    data = request.get_json(silent=True) or {}
    name = str(data.get("name") or "").strip()[:60]
    template = str(data.get("template") or "")
    if not name or template not in T.TEMPLATES:
        return jsonify({"ok": False, "error": i18n.t("mb_err_fields", lang)})
    info = manager.platform_info()
    if not (info.get("username") and info.get("can_manage")):
        return jsonify({"ok": False, "unavailable": True, "error": i18n.t("mb_err_unavailable", lang)})
    # حدّ الباقة قبل إصدار الرابط — ويُفحص ثانيةً لحظة الإنشاء
    if current_role() not in ("admin", "support"):
        maxb = plans.plan(_plan_id())["max_bots"]
        if db.count_user_bots(uid()) >= maxb:
            return jsonify({"ok": False, "upgrade": True,
                            "error": i18n.t("mb_err_limit", lang).format(n=maxb)})
    if _rate_limited(f"u{uid()}", limit=10, window=600, bucket="managed"):
        return jsonify({"ok": False, "error": i18n.t("ai_rate", lang)})
    code = MB.new_code()
    suggested = MB.suggest_username(name)
    rid = db.create_managed_request(uid(), MB.token_hash(code), template, name, suggested)
    link = MB.start_link(info["username"], code)
    # QR داخل الرد لا مسار مستقل: الرابط يحمل الكود السرّي، ولا يُخزَّن إلا تجزئته
    qr = "data:image/svg+xml;base64," + base64.b64encode(_qr_svg(link).encode("utf-8")).decode("ascii")
    return jsonify({"ok": True, "id": rid, "link": link, "qr": qr, "ttl": db.MANAGED_TTL,
                    "suggested": suggested})


@app.route("/bot/create/managed/<int:rid>")
@login_required
def bot_create_managed_status(rid):
    r = db.get_managed_request(rid, user_id=uid())      # الملكية في الاستعلام
    if not r:
        abort(404)
    st = r["status"]
    if st in ("pending", "linked") and r["expires_at"] <= int(_time.time()):
        st = "expired"
    out = {"status": st}
    if st == "created" and r.get("bot_id"):
        bot = db.get_bot(r["bot_id"], uid())
        if bot:
            cfg = json.loads(bot["config_json"] or "{}")
            out.update(bot_id=bot["id"], username=cfg.get("bot_username") or "",
                       url=url_for("bot_detail", bot_id=bot["id"], new=1))
    if st == "failed":
        out["error"] = r.get("error") or ""
    return jsonify(out)


# ============================================================================
#  طريقة الرد: فلو · هجين · عقل البوت  (TESTER_FEEDBACK_PLAN §4)
# ============================================================================
@app.route("/bot/<int:bot_id>/brain", methods=["POST"])
@login_required
def bot_brain(bot_id):
    b = _owned(bot_id)
    cfg = json.loads(b["config_json"] or "{}")
    lang = session.get("lang", i18n.DEFAULT)
    back = url_for("bot_detail", bot_id=bot_id) + "#brain"
    mode = request.form.get("response_mode", "flow")
    if mode not in FE.RESPONSE_MODES:
        mode = "flow"
    if mode != "flow":
        if not _uses_engine(b):
            flash(i18n.t("brain_not_engine", lang), "error"); return redirect(back)
        if current_role() not in ("admin", "support") and not plans.ai_replies_limit(_plan_id()):
            flash(i18n.t("brain_locked", lang), "error"); return redirect(url_for("pricing"))
        # موافقة صريحة مرة واحدة: رسائل العملاء ستصل لمزوّد الذكاء الاصطناعي
        if not cfg.get("ai_consent_at"):
            if request.form.get("ai_consent") != "1":
                flash(i18n.t("brain_consent_req", lang), "error"); return redirect(back)
            cfg["ai_consent_at"] = int(_time.time())
    cfg["response_mode"] = mode
    cfg["ai_persona"] = request.form.get("ai_persona", "").strip()[:600]
    # رسالة البداية وأزرارها (≤3، ≤20 حرفاً — حدّ زر الرد في واتساب)
    cfg["ai_welcome"] = request.form.get("ai_welcome", "").strip()[:900]
    starters = []
    for s in request.form.getlist("ai_starter"):
        s = " ".join(s.split())[:20].strip()
        if s and s not in starters:
            starters.append(s)
    cfg["ai_starters"] = starters[:3]
    # «مساعد BotYalla الرسمي»: يتكلّم باسم المنصة بأسعارها الحيّة — للأدمن على بوت يملكه
    # حساب إدارة فقط (والمحرك يعيد الفحص بصاحب البوت عند كل رد)
    if not db.bot_owner_is_staff(bot_id):
        cfg.pop("platform_kb", None)
    elif current_role() == "admin":
        cfg["platform_kb"] = request.form.get("platform_kb") == "1"
    kb = {k: request.form.get(f"kb_{k}", "") for k in
          ("about", "hours", "location", "delivery", "payment", "policies")}
    kb["faqs"] = [{"q": q, "a": a} for q, a in zip(request.form.getlist("kb_q"),
                                                    request.form.getlist("kb_a"))]
    cfg["kb"] = ai._coerce_kb(kb)
    db.update_bot_config(bot_id, cfg)
    if manager.is_running(bot_id): manager.restart_bot(bot_id)
    flash(i18n.t("brain_saved", lang), "ok")
    return redirect(back)


# ============================================================================
#  صندوق الوارد والتدخّل اليدوي  (TESTER_FEEDBACK_PLAN §5)
# ============================================================================
def _can_reply():
    return current_role() in ("admin", "support") or plans.inbox_reply(_plan_id())


def _inbox_peer(bot_id, peer):
    """عميل تواصل فعلاً مع **هذا** البوت — لا نراسل رقماً لم يراسلنا."""
    peer = str(peer or "")
    if not _PEER_RE.match(peer) or not db.peer_known(bot_id, peer):
        abort(404)
    return peer


@app.route("/bot/<int:bot_id>/inbox")
@login_required
def inbox(bot_id):
    b = _owned(bot_id)
    peer = request.args.get("peer", "")
    is_wa = (b.get("channel") or "telegram") == "whatsapp"
    lang = session.get("lang", i18n.DEFAULT)
    return react_page("inbox", "inbox_title",
                      {"bot": {"id": b["id"], "name": b["name"], "channel": b.get("channel") or "telegram"},
                       "conversations": db.list_conversations(bot_id),
                       "peer": peer if _PEER_RE.match(peer) else "",
                       "canReply": _can_reply(), "isWa": is_wa, "windowSec": WA_WINDOW},
                      title=i18n.t("inbox_title", lang) + " · " + b["name"])


@app.route("/api/bot/<int:bot_id>/inbox")
@login_required
def api_inbox(bot_id):
    _owned(bot_id)
    return jsonify({"conversations": db.list_conversations(bot_id),
                    "unread": db.unread_total(bot_id)})


@app.route("/api/bot/<int:bot_id>/inbox/thread")
@login_required
def api_inbox_thread(bot_id):
    _owned(bot_id)
    peer = _inbox_peer(bot_id, request.args.get("peer"))
    try:
        after = max(0, int(request.args.get("after") or 0))
    except ValueError:
        after = 0
    msgs = db.list_messages(bot_id, peer, after)
    if msgs or not after:
        db.mark_conversation_read(bot_id, peer)
    return jsonify({"messages": msgs, "conv": db.get_conversation(bot_id, peer) or {},
                    "lastIn": db.peer_last_in(bot_id, peer), "now": int(_time.time())})


@app.route("/bot/<int:bot_id>/inbox/send", methods=["POST"])
@login_required
def inbox_send(bot_id):
    b = _owned(bot_id)
    lang = session.get("lang", i18n.DEFAULT)
    data = request.get_json(silent=True) or {}
    peer = _inbox_peer(bot_id, data.get("peer"))
    if not _can_reply():
        return jsonify({"ok": False, "upgrade": True, "error": i18n.t("inbox_readonly", lang)}), 403
    text = str(data.get("text") or "").strip()[:4000]
    asset = None
    if data.get("asset_id"):
        aid = _own_asset_id(data.get("asset_id"))
        if not aid:
            abort(404)
        asset = db.get_asset(aid, owner_id=uid())
    if not text and not asset:
        return jsonify({"ok": False, "error": i18n.t("inbox_empty_text", lang)})
    if _rate_limited(f"u{uid()}:b{bot_id}", limit=40, window=60, bucket="inbox"):
        return jsonify({"ok": False, "error": i18n.t("ai_rate", lang)})
    # واتساب: لا نص حر بعد 24 ساعة من آخر رسالة للعميل — المخالفة تُقيّد الرقم
    if (b.get("channel") or "telegram") == "whatsapp" and \
            int(_time.time()) - db.peer_last_in(bot_id, peer) > WA_WINDOW:
        return jsonify({"ok": False, "window": True, "error": i18n.t("inbox_wa_window", lang)})
    ok, err = manager.send_to_peer(bot_id, peer, text=text or None, asset=asset)
    if not ok:
        return jsonify({"ok": False, "error": i18n.t(f"inbox_err_{err}", lang)})
    db.log_message(bot_id, peer, "out", "human", text, kind="media" if asset else "text")
    # الرد اليدوي يعني التولّي — لا يقاطعه البوت ولا الذكاء الاصطناعي
    db.set_conversation_mode(bot_id, peer, "human")
    return jsonify({"ok": True, "conv": db.get_conversation(bot_id, peer)})


@app.route("/bot/<int:bot_id>/inbox/mode", methods=["POST"])
@login_required
def inbox_mode(bot_id):
    _owned(bot_id)
    data = request.get_json(silent=True) or {}
    peer = _inbox_peer(bot_id, data.get("peer"))
    mode = data.get("mode")
    if mode not in ("bot", "human"):
        abort(400)
    if mode == "human" and not _can_reply():
        return jsonify({"ok": False, "upgrade": True,
                        "error": i18n.t("inbox_readonly", session.get("lang", i18n.DEFAULT))}), 403
    db.set_conversation_mode(bot_id, peer, mode)
    return jsonify({"ok": True, "conv": db.get_conversation(bot_id, peer)})


# ============================================================================
#  مكتبة الوسائط  (TESTER_FEEDBACK_PLAN §6)
# ============================================================================
def _asset_json(a):
    return {"id": a["id"], "kind": a["kind"], "mime": a["mime"], "size": a["size"],
            "name": a.get("name") or "", "created_at": a["created_at"],
            "source": a.get("source_url") or "", "url": url_for("asset_file", asset_id=a["id"])}


def _asset_quota():
    used = db.assets_bytes(uid())
    limit = None if current_role() in ("admin", "support") else plans.asset_bytes_limit(_plan_id())
    return {"used": used, "limit": limit}


def _asset_saved(data, name, source_url=None):
    lang = session.get("lang", i18n.DEFAULT)
    if not asset_store.quota_ok(uid(), current_role(), _plan_id(), len(data or b"")):
        return jsonify({"ok": False, "upgrade": True, "error": i18n.t("asset_err_quota", lang)})
    res = asset_store.save(uid(), data, name=name, source_url=source_url)
    if not res.get("ok"):
        return jsonify({"ok": False, "error": i18n.t(f"asset_err_{res.get('reason', 'type')}", lang)})
    return jsonify({"ok": True, "asset": _asset_json(db.get_asset(res["id"], owner_id=uid())),
                    "quota": _asset_quota()})


def _clean_asset_name(v):
    return _re.sub(r"[\x00-\x1f\x7f<>]", "", str(v or "")).strip()[:80]


@app.route("/media")
@login_required
def media_page():
    return react_page("media", "media_title",
                      {"assets": [_asset_json(a) for a in db.list_assets(uid())],
                       "quota": _asset_quota()})


@app.route("/api/assets")
@login_required
def api_assets():
    return jsonify({"assets": [_asset_json(a) for a in db.list_assets(uid())],
                    "quota": _asset_quota()})


@app.route("/api/assets/upload", methods=["POST"])
@login_required
def api_asset_upload():
    f = request.files.get("file")
    if not f:
        return jsonify({"ok": False, "error": i18n.t("asset_err_too_small",
                                                     session.get("lang", i18n.DEFAULT))})
    data = f.read(asset_store.MAX_ANY + 1)          # لا نقرأ أكثر من الحد قبل الحكم
    if len(data) > asset_store.MAX_ANY:
        return jsonify({"ok": False, "error": i18n.t("asset_err_too_large",
                                                     session.get("lang", i18n.DEFAULT))})
    name = _clean_asset_name(request.form.get("name") or os.path.splitext(f.filename or "")[0])
    return _asset_saved(data, name)


@app.route("/api/assets/url", methods=["POST"])
@login_required
def api_asset_url():
    lang = session.get("lang", i18n.DEFAULT)
    data = request.get_json(silent=True) or {}
    url = str(data.get("url") or "").strip()[:1000]
    if _rate_limited(f"u{uid()}", limit=20, window=600, bucket="asset_url"):
        return jsonify({"ok": False, "error": i18n.t("ai_rate", lang)})
    blob, err = asset_store.fetch_url(url)
    if err:
        return jsonify({"ok": False, "error": i18n.t(f"asset_err_{err}", lang)})
    return _asset_saved(blob, _clean_asset_name(data.get("name")), source_url=url[:500])


@app.route("/api/assets/<int:asset_id>/delete", methods=["POST"])
@login_required
def api_asset_delete(asset_id):
    row = db.delete_asset(asset_id, uid())          # الملكية شرط في الحذف نفسه
    if not row:
        abort(404)
    asset_store.delete_file(row["fname"])
    return jsonify({"ok": True, "quota": _asset_quota()})


@app.route("/assets/<int:asset_id>")
@login_required
def asset_file(asset_id):
    a = db.get_asset(asset_id, owner_id=uid())
    if not a:
        abort(404)
    fname = secure_filename(a["fname"])
    if not os.path.exists(asset_store.path_of(fname)):
        abort(404)
    resp = send_from_directory(asset_store.BASE_DIR, fname, mimetype=a["mime"], conditional=True)
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["Cache-Control"] = "private, max-age=3600"
    return resp


def settle_payment(row):
    """إشعار المالك بعمولة الإحالة إن تحققت. التسوية نفسها تمّت داخل
    db.finalize_payment ليشملها مسار تليجرام أيضاً."""
    try:
        r = db.referral_of(row["user_id"])
        if r and r.get("payment_id") == row["id"] and r.get("commission"):
            aff = db.get_user(r["affiliate_user_id"])
            notify_admins(f"🤝 عمولة إحالة {r['commission']} EGP لـ "
                          f"{aff['username'] if aff else r['affiliate_user_id']} (دفعة #{row['id']})")
    except Exception:
        pass


# ============================================================================
#  محرّك التسعير — المصدر الوحيد للمبالغ.
#  قاعدة AGENTS.md §3.3 تبقى كما هي: المبلغ يُحسب هنا في الخادم، ولا يُقرأ
#  من الفورم أبداً. كل ما تفعله الواجهة هو إرسال معرّف الباقة وكود الخصم.
# ============================================================================

def _plan_pricing(plan_id, overrides=None, cycle="monthly"):
    """يرجّع تسعير الباقة بعد تجاوزات المالك وخصمها المعلن، على الدورة المطلوبة.

    **الترتيب مقصود:** سعر الشهر (بعد تجاوز المالك) ← معامل السنة ← خصم الباقة.
    فلو خفّض المالك سعر باقة، ينزل السعر السنوي معها تلقائياً — لا يبقى مثبّتاً
    على سعر القائمة الأصلي. و`norm_cycle` تضمن أن أي قيمة قادمة من المستخدم
    تسقط إلى الشهرية بدل أن تُسعَّر بصفر."""
    base = plans.plan(plan_id)
    ov = (overrides if overrides is not None else db.plan_overrides()).get(plan_id) or {}
    price = ov.get("price")
    monthly = float(base["price"]) if price is None else float(price)
    cyc = plans.norm_cycle(cycle)
    price = plans.annual_of(monthly) if cyc == "annual" else monthly
    disc = float(ov.get("discount_pct") or 0)
    final = round(price * (1 - disc / 100.0), 2)
    return {"cycle": cyc, "monthly_price": round(monthly, 2),
            "list_price": round(price, 2), "discount_pct": disc,
            "price": max(0.0, final), "has_discount": disc > 0 and final < price}

def _plan_feature_lines(pid):
    """سطور مزايا الإصدار الجديد (وكيل الإعداد · عقل البوت · صندوق الوارد) تُولَّد من
    plans.FEATURES نفسها التي تُطبَّق بها الحدود — فلا يختلف رقم معروض عن حدّ فعلي."""
    out = {"ar": [], "en": []}

    def add(key, **kw):
        for lg in out:
            out[lg].append(i18n.t(key, lg).format(**kw))

    add("pf_agent", n=f"{plans.ai_setups_limit(pid):,}")
    if plans.ai_replies_limit(pid):
        add("pf_brain", n=f"{plans.ai_replies_limit(pid):,}")
    if plans.inbox_reply(pid):
        add("pf_inbox")
    return out


def priced_plans(lang=None):
    """كل الباقات بأسعارها الفعلية على الدورتين — للعرض في الواجهة.

    الدورتان تُرسَلان معاً ليعمل زرّ التبديل (شهري/سنوي) بلا طلب شبكة، ومع ذلك
    يبقى المبلغ المخزَّن محسوباً في الخادم وحده عند الدفع (AGENTS.md §3.3)."""
    lang = lang or session.get("lang", i18n.DEFAULT)
    ov = db.plan_overrides()
    out = []
    for pid in plans.ORDER:
        p = dict(plans.PLANS[pid], id=pid)
        extra = _plan_feature_lines(pid)                # نسخ جديدة — لا نعدّل PLANS نفسها
        p["features_ar"] = list(p.get("features_ar", [])) + extra["ar"]
        p["features_en"] = list(p.get("features_en", [])) + extra["en"]
        m = _plan_pricing(pid, ov, "monthly")
        a = _plan_pricing(pid, ov, "annual")
        p.update(m)                                    # الشهري هو الافتراضي المعروض
        p["annual_list_price"] = a["list_price"]
        p["annual_price"] = a["price"]
        p["annual_has_discount"] = a["has_discount"]
        # التوفير يُحسب من السعرين الفعليين لا من ثابت، فيعكس تجاوزات المالك
        p["annual_saving_pct"] = (int(round((1 - a["price"] / (m["price"] * 12.0)) * 100))
                                  if m["price"] > 0 else 0)
        p["annual_monthly_equiv"] = round(a["price"] / 12.0, 2) if a["price"] else 0
        out.append(p)
    return out

def validate_promo(code, plan_id, user_id):
    """يتحقّق من كود الخصم مقابل الباقة والمستخدم.
    يرجّع (promo_row | None, reason_key). لا يستهلك الكود — الاستهلاك عند الاعتماد."""
    code = (code or "").strip().upper()
    if not code:
        return None, None
    pr = db.get_promo_by_code(code)
    if not pr or not pr["is_active"]:
        return None, "promo_bad"
    if pr["expires_at"] and pr["expires_at"] < int(_time.time()):
        return None, "promo_expired"
    if pr["max_uses"] is not None and pr["used"] >= pr["max_uses"]:
        return None, "promo_exhausted"
    if pr["plan"] and pr["plan"] != plan_id:
        return None, "promo_wrong_plan"
    if pr["per_user_once"] and db.promo_used_by(pr["id"], user_id):
        return None, "promo_used"
    return pr, None

def quote(plan_id, user_id, code=None, cycle="monthly"):
    """التسعيرة النهائية: سعر الباقة على الدورة المطلوبة بعد خصمها المعلن، ثم
    كود الخصم إن صحّ. هذه الدالة وحدها تحدّد ما يُخزَّن في payments.amount،
    و`cycle` المُطبَّعة التي ترجّعها هي وحدها ما يُخزَّن في payments.billing_cycle."""
    pricing = _plan_pricing(plan_id, cycle=cycle)
    base = pricing["price"]
    promo, reason = validate_promo(code, plan_id, user_id)
    cut = 0.0
    if promo:
        cut = (base * float(promo["value"]) / 100.0) if promo["kind"] == "percent" else float(promo["value"])
        cut = round(min(cut, base), 2)
    total = round(max(0.0, base - cut), 2)
    return {
        "plan": plan_id,
        "cycle": pricing["cycle"],
        "days": plans.cycle_days(pricing["cycle"]),
        "list_price": pricing["list_price"],
        "plan_discount_pct": pricing["discount_pct"],
        "base": base,                 # بعد خصم الباقة، قبل الكود
        "promo": promo,
        "promo_code": promo["code"] if promo else None,
        "promo_cut": cut,
        "total": total,
        "reason": reason,             # سبب رفض الكود إن وُجد
    }

_LANDING_ICONS = ("store","calendar","shield","grid","flow","sparkles","chart","megaphone",
                  "check","rocket","tag","phone","bot","card","users","wallet","bolt",
                  "globe","image","lock","key","download","link","back","clock","play","inbox",
                  # أيقونات العروض الحيّة في البطل والقنوات والقصة
                  "pizza","dress","stethoscope","bag","menu","cart","ruler","camera","ticket",
                  "folder","chat","truck","return","refresh","user","close","arrow")

# ---------------------------------------------------------------------------
#  طبقة تقديم React: Flask يبقى مسؤولاً عن التوجيه والصلاحيات والنماذج،
#  و React يرسم الواجهة فقط. لا API جديدة ولا SPA — النماذج تبقى POST عادية
#  بـ CSRF، فلا تتغيّر أي ضمانة أمنية.
# ---------------------------------------------------------------------------
_TMPL_ICON = {"flow":"flow","store":"store","booking":"calendar","customer_service":"phone",
              "faq":"grid","feedback":"sparkles","support":"shield"}
_TMPL_KEY  = {"flow":"tmpl_flow","store":"tmpl_store","booking":"tmpl_booking",
              "customer_service":"tmpl_cs","faq":"tmpl_faq","feedback":"tmpl_feedback",
              "support":"tmpl_support"}

def _js_json(payload):
    """JSON مُهيّأ للحقن داخل وسم <script>.

    `json.dumps` لا يهرّب `</script>` ولا فاصلي السطر U+2028/U+2029، والقالب
    يحقن الناتج بـ `|safe`. فأي نص يكتبه مستخدم — اسم حساب، أو رسالة عميل
    وصلت من تليجرام/واتساب داخل lead — يمكنه إغلاق الوسم مبكراً وتشغيل كود
    في جلسة من يفتح الصفحة (الأدمن في «المستخدمون»، أو صاحب البوت في صفحته)
    حيث توكن CSRF معروض في نفس الحمولة. الهروب هنا يقع داخل السلاسل فقط،
    وجافاسكربت تفكّه تلقائياً، فلا يتغيّر أي سلوك في الواجهة."""
    return (json.dumps(payload, ensure_ascii=False, default=str)
            .replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
            .replace("\u2028", "\\u2028").replace("\u2029", "\\u2029"))


def react_page(view, title_key, props=None, needs_chart=False, title=None):
    """يرسم صفحة React مع قشرة اللوحة وبياناتها."""
    lang = session.get("lang", i18n.DEFAULT)
    role = current_role()
    nav = [
        {"k": "dashboard",   "u": url_for("dashboard"),    "i": "grid",     "l": i18n.t("nav_bots", lang)},
        {"k": "media",       "u": url_for("media_page"),   "i": "image",    "l": i18n.t("media_nav", lang)},
        {"k": "pricing",     "u": url_for("pricing"),      "i": "tag",      "l": i18n.t("nav_pricing", lang)},
        {"k": "billing",     "u": url_for("billing"),      "i": "card",     "l": i18n.t("nav_billing", lang)},
        {"k": "wallet",      "u": url_for("wallet_page"),  "i": "wallet",   "l": i18n.t("wallet_nav", lang)},
        {"k": "request_bot", "u": url_for("request_bot"),  "i": "sparkles", "l": i18n.t("custom_bot", lang)},
        {"k": "support",     "u": url_for("support"),      "i": "help",     "l": i18n.t("nav_support", lang)},
        {"k": "affiliate",   "u": url_for("affiliate"),    "i": "crown",    "l": i18n.t("aff_title", lang)},
    ]
    admin_nav = []
    if role in ("admin", "support"):
        admin_nav = [
            {"k": "admin_overview", "u": url_for("admin_home"),     "i": "shield", "l": i18n.t("nav_admin", lang)},
            {"k": "admin_users",    "u": url_for("admin_users"),    "i": "users",  "l": i18n.t("admin_users_t", lang)},
            {"k": "admin_payments", "u": url_for("admin_payments"), "i": "wallet", "l": i18n.t("admin_payments_t", lang)},
            {"k": "admin_requests", "u": url_for("admin_requests"), "i": "inbox",  "l": i18n.t("nav_requests", lang)},
            {"k": "admin_tickets",  "u": url_for("admin_tickets"),  "i": "chat",   "l": i18n.t("nav_tickets", lang)},
        ]
        if role == "admin":
            # مزايا المالك وحده — لا يراها الدعم إطلاقاً
            admin_nav += [
                {"k": "admin_pricing",    "u": url_for("admin_pricing"),    "i": "tag",      "l": i18n.t("adm_pricing", lang)},
                {"k": "admin_promos",     "u": url_for("admin_promos"),     "i": "bolt",     "l": i18n.t("adm_promos", lang)},
                {"k": "admin_affiliates", "u": url_for("admin_affiliates"), "i": "users",    "l": i18n.t("adm_affiliates", lang)},
                {"k": "settings",         "u": url_for("settings"),         "i": "sparkles", "l": i18n.t("nav_ai", lang)},
                {"k": "admin_analytics",  "u": url_for("admin_analytics"),  "i": "chart",    "l": i18n.t("adm_analytics", lang)},
                {"k": "admin_emails",     "u": url_for("admin_emails"),     "i": "mail",     "l": i18n.t("adm_emails", lang)},
                {"k": "admin_platform",   "u": url_for("admin_platform"),   "i": "settings", "l": i18n.t("nav_platform", lang)},
            ]

    payload = {
        "view": view, "lang": lang, "dir": i18n.dir_for(lang), "brand": "BotYalla",
        "csrf": _csrf_token(), "track": _track_events(),
        "user": {"name": session.get("uname"), "role": role,
                 # لمطالبة لطيفة بإضافة إيميل — بدونه لا استرجاع للحساب
                 "hasEmail": bool((getattr(g, "user", None) or {}).get("email")),
                 "emailVerified": bool((getattr(g, "user", None) or {}).get("email_verified_at")),
                 "avatar": _avatar_url(session.get("uid"))},
        "t": {k: i18n.t(k, lang) for k in i18n.T},
        "icons": {n: _icon_svg(n) for n in icons._P},
        "nav": nav, "adminNav": admin_nav,
        "flashes": [{"c": c, "m": m} for c, m in get_flashed_messages(with_categories=True)],
        "urls": {
            "dashboard": url_for("dashboard"), "pricing": url_for("pricing"),
            "billing": url_for("billing"), "account": url_for("account"),
            "wallet": url_for("wallet_page"),
            "logout": url_for("logout"), "login": url_for("login"),
            "register": url_for("register"), "landing": url_for("home"),
            "forgot": url_for("forgot"), "verify": url_for("verify_email"),
            "checkUsername": url_for("api_check_username"),
            "requestBot": url_for("request_bot"), "botCreate": url_for("bot_create"),
            "botCreateManaged": url_for("bot_create_managed"),
            "media": url_for("media_page"), "assets": url_for("api_assets"),
            "logo": url_for("static", filename="logo.svg"),
            "lang": url_for("set_lang", code="en" if lang == "ar" else "ar"),
            "terms": url_for("terms"), "privacy": url_for("privacy"),
        },
        "templates": [{"k": k, "icon": _TMPL_ICON[k], "label": i18n.t(_TMPL_KEY[k], lang)}
                      for k in ("flow","store","booking","customer_service","faq","feedback","support")],
        "props": props or {},
    }
    return render_template("react_app.html", view=view,
                           page_title=title or i18n.t(title_key, lang), brand="BotYalla",
                           lang=lang, dir=i18n.dir_for(lang), needs_chart=needs_chart,
                           by_json=_js_json(payload))

def _icon_svg(name):
    """SVG خام (يملأ حاويته) لحقنه داخل مكوّنات React."""
    body = icons._P.get(name) or icons._P["grid"]
    return ('<svg viewBox="0 0 24 24" width="100%" height="100%" fill="none" '
            'stroke="currentColor" stroke-width="1.7" stroke-linecap="round" '
            f'stroke-linejoin="round" aria-hidden="true">{body}</svg>')

# ============================================================================
#  لوحة المالك: التسعير · أكواد الخصم · الأفيليت
#  كلها @require_roles("admin") — الدعم (support) لا يصل إليها إطلاقاً.
# ============================================================================

@app.route("/admin/pricing", methods=["GET", "POST"])
@require_roles("admin")
def admin_pricing():
    if request.method == "POST":
        for pid in plans.ORDER:
            if pid == "free":
                continue
            db.set_plan_override(pid,
                                 price=request.form.get(f"price_{pid}"),
                                 discount_pct=request.form.get(f"disc_{pid}"))
        flash("تم تحديث الأسعار." if session.get("lang") != "en" else "Pricing updated.", "ok")
        return redirect(url_for("admin_pricing"))
    lang = session.get("lang", i18n.DEFAULT)
    return react_page("admin_pricing", "adm_pricing", {
        "plans": [dict(p, name=plans.plan_name(p["id"], lang)) for p in priced_plans(lang)],
    })


@app.route("/admin/promos", methods=["GET", "POST"])
@require_roles("admin")
def admin_promos():
    if request.method == "POST":
        exp = request.form.get("expires_at", "").strip()
        try:
            exp_ts = int(_dt.datetime.strptime(exp, "%Y-%m-%d").timestamp()) if exp else None
        except ValueError:
            exp_ts = None
        _, err = db.create_promo(
            request.form.get("code", ""),
            request.form.get("kind", "percent"),
            request.form.get("value", 0),
            plan=(request.form.get("plan") or None),
            max_uses=request.form.get("max_uses") or None,
            expires_at=exp_ts,
            per_user_once=1 if request.form.get("per_user_once") else 0)
        if err == "duplicate":
            flash("هذا الكود موجود بالفعل." if session.get("lang") != "en" else "That code already exists.", "error")
        elif err:
            flash("بيانات الكود غير صحيحة." if session.get("lang") != "en" else "Invalid promo data.", "error")
        else:
            flash("تم إنشاء الكود." if session.get("lang") != "en" else "Promo created.", "ok")
        return redirect(url_for("admin_promos"))

    lang = session.get("lang", i18n.DEFAULT)
    rows = db.list_promos()
    for r in rows:
        r.update(db.promo_stats(r["id"]))
    return react_page("admin_promos", "adm_promos", {
        "promos": rows,
        "plans": [{"id": p, "name": plans.plan_name(p, lang)} for p in plans.ORDER if p != "free"],
    })


@app.route("/admin/promos/<int:promo_id>/<any(on,off,delete):action>", methods=["POST"])
@require_roles("admin")
def admin_promo_action(promo_id, action):
    if action == "delete":
        db.delete_promo(promo_id)
    else:
        db.set_promo_active(promo_id, action == "on")
    flash("تم التحديث." if session.get("lang") != "en" else "Updated.", "ok")
    return redirect(url_for("admin_promos"))


@app.route("/admin/affiliates", methods=["GET", "POST"])
@require_roles("admin")
def admin_affiliates():
    if request.method == "POST":
        db.set_platform("aff_default_rate", request.form.get("default_rate", "20").strip())
        flash("تم الحفظ." if session.get("lang") != "en" else "Saved.", "ok")
        return redirect(url_for("admin_affiliates"))
    return react_page("admin_affiliates", "adm_affiliates", {
        "affiliates": db.list_affiliates(),
        "defaultRate": db.get_platform("aff_default_rate", "20"),
    })


@app.route("/admin/affiliates/<int:user_id>/<any(rate,toggle,payout):action>", methods=["POST"])
@require_roles("admin")
def admin_affiliate_action(user_id, action):
    if action == "rate":
        db.set_affiliate(user_id, rate_pct=request.form.get("rate_pct"))
    elif action == "toggle":
        cur = db.get_affiliate(user_id)
        db.set_affiliate(user_id, is_active=not (cur and cur["is_active"]))
    elif action == "payout":
        if not db.affiliate_payout(user_id, request.form.get("amount")):
            flash("مبلغ الصرف غير صحيح أو يتجاوز المستحقّ."
                  if session.get("lang") != "en" else
                  "Payout amount is invalid or exceeds what is due.", "error")
            return redirect(url_for("admin_affiliates"))
    flash("تم التحديث." if session.get("lang") != "en" else "Updated.", "ok")
    return redirect(url_for("admin_affiliates"))


# ---------------------------------------------------------------- العميل
@app.route("/api/promo/check", methods=["POST"])
@login_required
def api_promo_check():
    """تسعيرة حيّة لصفحة الدفع. لا تستهلك الكود ولا تعتمد عليها في التسجيل —
    المبلغ المخزَّن يُحسب من جديد داخل subscribe_pay."""
    d = request.get_json(silent=True) or {}
    plan_id = d.get("plan")
    if not plans.is_sellable(plan_id):
        return jsonify({"ok": False})
    # المسار يجيب بنعم/لا عن صلاحية أي كود، فبدون حدّ يصبح أداة تخمين آلي.
    # الحدّ على المستخدم لا على الـIP: الحساب هو ما يلزم لبلوغ المسار أصلاً.
    if _rate_limited(str(uid()), limit=20, window=300, bucket="promo"):
        return jsonify({"ok": False, "valid": False,
                        "error": i18n.t("promo_bad", session.get("lang", i18n.DEFAULT))}), 429
    q = quote(plan_id, uid(), d.get("code", ""), cycle=d.get("cycle"))
    lang = session.get("lang", i18n.DEFAULT)
    return jsonify({
        "ok": True,
        "cycle": q["cycle"], "days": q["days"],
        "listPrice": q["list_price"], "base": q["base"], "total": q["total"],
        "planDiscountPct": q["plan_discount_pct"],
        "promoCode": q["promo_code"], "promoCut": q["promo_cut"],
        "valid": bool(q["promo"]),
        "error": i18n.t(q["reason"], lang) if q["reason"] else None,
    })


@app.route("/affiliate", methods=["GET", "POST"])
@login_required
def affiliate():
    """لوحة الأفيليت للمستخدم: كوده، رابطه، إحالاته وأرباحه."""
    me = db.get_user(uid())
    aff = db.get_affiliate(uid())
    if request.method == "POST":
        if not aff:
            rate = db.get_platform("aff_default_rate", "20")
            base = "".join(ch for ch in (me["username"] or "").upper() if ch.isalnum())[:10]
            code = (base or "BY") + _secrets.token_hex(2).upper()
            aff = db.ensure_affiliate(uid(), code, rate)
        return redirect(url_for("affiliate"))
    return react_page("affiliate", "aff_title", {
        "aff": aff,
        "summary": db.affiliate_summary(uid()) if aff else {"signups": 0, "conversions": 0},
        # رابط يُنشر خارج المنصة: من PUBLIC_URL (النطاق الرسمي) لا من ترويسة Host
        "link": (_site_base() + url_for("home") + "?ref=" + aff["code"]) if aff else None,
        "defaultRate": db.get_platform("aff_default_rate", "20"),
    })


@app.route("/healthz")
def healthz():
    """فحص صحّي للمراقبة: يتحقق أن القاعدة تستجيب فعلاً لا أن العملية حيّة فقط."""
    try:
        db.count_users()
        return jsonify({"ok": True}), 200
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)[:120]}), 503


# ============================================================================
#  الموقع العام: الرئيسية · الوثائق القانونية · 404 · ملفات محركات البحث.
#  كل صفحة عامة تمرّ بـ `_render_public`: وسوم SEO وبيانات منظّمة وحمولة React
#  ومحتوى مرسوم في الخادم يُفهرَس ويُقرأ بلا جافاسكربت (templates_web/public.html).
# ============================================================================

# تاريخ آخر تعديل فعلي على النصوص القانونية — حدّثه عند تغيير أي وثيقة.
LEGAL_UPDATED = "2026-09-15"
# آخر تعديل جوهري على الصفحة الرئيسية (يظهر في sitemap.xml)
SITE_UPDATED = "2026-09-12"

LEGAL_ENDPOINTS = {"terms": "terms", "privacy": "privacy",
                   "refund": "refund_policy", "aup": "acceptable_use"}

# نصوص الموقع العام: كل مفاتيح الصفحة الرئيسية بالبادئة، لا قائمة يدوية تنسى مفتاحاً
_PUBLIC_T_PREFIXES = ("lp", "hero_", "feat_", "ai_setup", "tmpl_", "footer_")
_PUBLIC_T_EXTRA = ("get_started_free", "login", "signin_link", "brand_tag", "daily_activity",
                   "legal_updated", "stat_subs", "stat_orders", "stat_revenue", "stat_leads")

# مسارات لا تُفهرَس: خاصة بالمستخدم أو تقنية. /pricing مفهرسة عمداً: أعلى صفحة نيّة شراء —
# من يبحث «سعر بوت واتساب مصر» عميل جاهز يدفع.
_NOINDEX_PATHS = ("/dashboard", "/admin", "/bot/", "/account", "/billing", "/wallet",
                  "/subscribe/", "/settings", "/api/", "/wh/", "/reset/",
                  "/request-bot", "/affiliate", "/email/")

_SITEMAP = (("home", "1.0", "weekly"), ("pricing", "0.8", "weekly"),
            ("register", "0.6", "monthly"), ("login", "0.3", "yearly"),
            ("terms", "0.3", "yearly"), ("privacy", "0.3", "yearly"),
            ("refund_policy", "0.3", "yearly"), ("acceptable_use", "0.3", "yearly"))


def _site_base():
    """أصل الموقع للروابط المطلقة (canonical · og · sitemap · رابط الأفيليت).
    `PUBLIC_URL` أولاً (AGENTS.md §3.14)، وإلا أصل الطلب — روابط لا تحمل أسراراً."""
    base = os.getenv("PUBLIC_URL", "").strip().rstrip("/")
    return base if base.startswith(("https://", "http://")) else request.host_url.rstrip("/")


def _public_payload(page, lang):
    """الحمولة المشتركة لكل صفحات الموقع العام (window.BY في public.html)."""
    plat = db.all_platform()
    user = getattr(g, "user", None)
    email = plat.get("support_email", "") or "info@botyalla.com"
    wa = plat.get("support_whatsapp", "")
    contact = [{"l": email, "h": "mailto:" + email}]
    if wa:
        contact.append({"l": "WhatsApp", "h": "https://wa.me/" + wa})
    contact.append({"l": "youssefalsherief.tech", "h": "https://youssefalsherief.tech/"})
    return {
        "page": page, "lang": lang, "dir": i18n.dir_for(lang), "brand": "BotYalla",
        "year": _dt.date.today().year, "email": email, "track": _track_events(),
        "social": AN.social_links(),
        "t": {k: i18n.t(k, lang) for k in i18n.T
              if k.startswith(_PUBLIC_T_PREFIXES) or k in _PUBLIC_T_EXTRA},
        "icons": {n: _icon_svg(n) for n in _LANDING_ICONS},
        "auth": {"in": bool(user), "name": session.get("uname") if user else None},
        "urls": {"home": url_for("home"), "register": url_for("register"), "login": url_for("login"),
                 "dashboard": url_for("dashboard"), "subscribe": "/subscribe/",
                 "logo": _static_v("logo.svg"), "mark": _static_v("mark.svg"),
                 "lang": url_for("set_lang", code="en" if lang == "ar" else "ar")},
        "contact": contact,
        "legalDocs": [{"id": d, "title": LEGAL.title(d, lang), "url": url_for(LEGAL_ENDPOINTS[d])}
                      for d in LEGAL.ORDER],
    }


def _seo(lang, title, description, path, jsonld=None, index=True, alternates=True):
    base = _site_base()
    canonical = base + path
    return {
        "title": title, "description": description, "canonical": canonical,
        "robots": "index,follow,max-image-preview:large" if index else "noindex,follow",
        "alternates": ([{"lang": "ar", "href": canonical + "?lang=ar"},
                        {"lang": "en", "href": canonical + "?lang=en"},
                        {"lang": "x-default", "href": canonical}] if alternates else []),
        "og_image": base + _static_v(f"brand/og-{lang}.png"),
        "og_locale": "ar_EG" if lang == "ar" else "en_US",
        "og_locale_alt": "en_US" if lang == "ar" else "ar_EG",
        # _js_json لا json.dumps: البيانات المنظّمة داخل <script> أيضاً (AGENTS.md §3.9)
        "jsonld": _js_json(jsonld) if jsonld else None,
        "gsv": os.getenv("GOOGLE_SITE_VERIFICATION", "").strip(),
    }


def _render_public(payload, seo, status=200):
    return render_template("public.html", by_json=_js_json(payload), P=payload, seo=seo), status


def _public_plan(p, lang):
    """باقة للعرض العام — من `priced_plans` نفسها التي تُبنى عليها صفحة الدفع."""
    return {"id": p["id"], "name": plans.plan_name(p["id"], lang),
            "features": p.get("features_ar" if lang == "ar" else "features_en", []),
            "price": p["price"], "list_price": p["list_price"], "has_discount": p["has_discount"],
            "annual_price": p["annual_price"], "annual_list_price": p["annual_list_price"],
            "annual_has_discount": p["annual_has_discount"],
            "annual_saving_pct": p["annual_saving_pct"],
            "annual_monthly_equiv": p["annual_monthly_equiv"],
            "whatsapp": bool(p.get("whatsapp")), "hot": p["id"] == "whatsapp"}


def _home_jsonld(lang, plist, faq):
    """بيانات منظّمة (schema.org): المنظّمة · الموقع · التطبيق وعروضه · الأسئلة.
    الأسعار من الخادم نفسه — لا رقم يختلف عمّا يدفعه العميل."""
    base = _site_base()
    plat = db.all_platform()
    email = plat.get("support_email", "") or "info@botyalla.com"
    wa = plat.get("support_whatsapp", "")
    contact = {"@type": "ContactPoint", "contactType": "customer support", "email": email,
               "availableLanguage": ["ar", "en"], "areaServed": "EG"}
    if wa:
        contact["telephone"] = "+" + wa
    offers = []
    for p in plist:
        o = {"@type": "Offer", "name": p["name"], "price": f"{float(p['price']):.2f}",
             "priceCurrency": "EGP", "url": base + "/#pricing"}
        if p["price"]:
            o["priceSpecification"] = {"@type": "UnitPriceSpecification",
                                       "price": f"{float(p['price']):.2f}", "priceCurrency": "EGP",
                                       "billingDuration": "P1M", "unitText": "MONTH"}
        offers.append(o)
    # `sameAs` يربط الكيان بحساباته الرسمية، فيعرف جوجل أن الصفحات كلها لجهة
    # واحدة (لوحة المعرفة وبحث العلامة). يُحذف كلياً إن لم تُضبط `SOCIAL_LINKS`:
    # حقل فارغ أسوأ من غائب.
    org = {"@type": "Organization", "@id": base + "/#org", "name": "BotYalla", "url": base + "/",
           "logo": base + _static_v("brand/icon-512.png"), "email": email,
           "founder": {"@type": "Person", "name": "Youssef Alsherief",
                       "url": "https://youssefalsherief.tech/"},
           "contactPoint": [contact]}
    same_as = [s["url"] for s in AN.social_links()]
    if same_as:
        org["sameAs"] = same_as
    return {"@context": "https://schema.org", "@graph": [
        org,
        {"@type": "WebSite", "@id": base + "/#site", "url": base + "/", "name": "BotYalla",
         "inLanguage": ["ar", "en"], "publisher": {"@id": base + "/#org"}},
        {"@type": "SoftwareApplication", "name": "BotYalla",
         "applicationCategory": "BusinessApplication", "operatingSystem": "Web",
         "url": base + "/", "inLanguage": lang, "publisher": {"@id": base + "/#org"},
         "offers": offers},
        {"@type": "FAQPage", "mainEntity": [
            {"@type": "Question", "name": x["q"],
             "acceptedAnswer": {"@type": "Answer", "text": x["a"]}} for x in faq]},
    ]}


@app.route("/")
def home():
    """الصفحة الرئيسية = صفحة الهبوط لكل زائر، مسجّلاً أو لا (للمسجّل زرّ «لوحتي»)."""
    lang = session.get("lang", i18n.DEFAULT)
    payload = _public_payload("home", lang)
    payload.update(i18n.landing_payload(lang))
    price = _egp(mkt_price())
    ai_price = FE.ai_reply_price() / 100
    payload["mktPrice"] = price
    # الأسعار تُملأ هنا لا في الواجهة: نفس النص يدخل البيانات المنظّمة لمحركات البحث
    payload["faq"] = [{"q": x["q"], "a": x["a"].replace("{price}", f"{price:g}")
                                               .replace("{ai_price}", f"{ai_price:g}")}
                      for x in payload["faq"]]
    # QR البطل يفتح التسجيل (أو اللوحة) على موبايل الزائر — رابط حقيقي لا زخرفة
    payload["heroQr"] = _qr_rows(_site_base() + (url_for("dashboard") if getattr(g, "user", None)
                                                  else url_for("register")))
    plist = [_public_plan(p, lang) for p in priced_plans(lang)]
    payload["plans"] = plist
    payload["templates"] = [
        {"icon": _TMPL_ICON[k], "name": i18n.t(_TMPL_KEY[k], lang)}
        for k in ("flow", "store", "booking", "customer_service", "faq", "feedback", "support")
    ]
    seo = _seo(lang, i18n.t("lp2_seo_title", lang), i18n.t("lp2_seo_desc", lang), url_for("home"),
               jsonld=_home_jsonld(lang, plist, payload["faq"]))
    return _render_public(payload, seo)


@app.route("/landing")
def landing():
    """الرابط القديم للرئيسية — تحويل دائم يحفظ الاستعلام، فروابط الأفيليت
    المنشورة سابقاً (`/landing?ref=CODE`) لا تنكسر."""
    qs = request.query_string.decode("utf-8", "ignore")
    return redirect(url_for("home") + ("?" + qs if qs else ""), code=301)


def _legal(doc):
    lang = session.get("lang", i18n.DEFAULT)
    payload = _public_payload("legal", lang)
    wa = db.get_platform("support_whatsapp", "")
    L = LEGAL.render(doc, lang, {"email": payload["email"], "whatsapp": ("+" + wa) if wa else "—",
                                 "updated": LEGAL_UPDATED, "site": _site_base()})
    payload["legal"] = L
    seo = _seo(lang, f"{L['title']} · BotYalla", L["intro"][:158], request.path)
    return _render_public(payload, seo)


@app.route("/terms")
def terms():
    return _legal("terms")


@app.route("/privacy")
def privacy():
    return _legal("privacy")


@app.route("/refund")
def refund_policy():
    return _legal("refund")


@app.route("/acceptable-use")
def acceptable_use():
    return _legal("aup")


@app.errorhandler(404)
def _not_found(e):
    """404 بهوية الموقع لطلبات الصفحات. مسارات API والويبهوك والملفات الثابتة،
    وأي طلب يريد JSON، تبقى كما هي — لا صفحة HTML لعميل برمجي."""
    if (request.path.startswith(("/api/", "/wh/", "/static/"))
            or request.accept_mimetypes.best == "application/json"):
        return e
    lang = session.get("lang", i18n.DEFAULT)
    payload = _public_payload("notfound", lang)
    seo = _seo(lang, i18n.t("lp2_nf_t", lang) + " · BotYalla", i18n.t("lp2_nf_d", lang),
               request.path, index=False, alternates=False)
    return _render_public(payload, seo, 404)


@app.route("/robots.txt")
def robots_txt():
    lines = (["User-agent: *", "Allow: /"] + [f"Disallow: {p}" for p in _NOINDEX_PATHS]
             + ["", f"Sitemap: {_site_base()}/sitemap.xml", ""])
    return Response("\n".join(lines), mimetype="text/plain")


@app.route("/sitemap.xml")
def sitemap_xml():
    base = _site_base()
    out = ['<?xml version="1.0" encoding="UTF-8"?>',
           '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" '
           'xmlns:xhtml="http://www.w3.org/1999/xhtml">']
    for ep, prio, freq in _SITEMAP:
        loc = _xesc(base + url_for(ep))
        mod = SITE_UPDATED if ep in ("home", "pricing", "register", "login") else LEGAL_UPDATED
        alts = "".join(f'<xhtml:link rel="alternate" hreflang="{l}" href="{loc}?lang={l}"/>'
                       for l in ("ar", "en"))
        out.append(f"<url><loc>{loc}</loc><lastmod>{mod}</lastmod><changefreq>{freq}</changefreq>"
                   f"<priority>{prio}</priority>{alts}</url>")
    out.append("</urlset>")
    return Response("\n".join(out), mimetype="application/xml")


@app.route("/site.webmanifest")
def webmanifest():
    lang = session.get("lang", i18n.DEFAULT)
    icon = lambda n, s, **kw: dict({"src": _static_v(f"brand/{n}.png"),
                                    "sizes": f"{s}x{s}", "type": "image/png"}, **kw)
    data = {"name": "BotYalla", "short_name": "BotYalla", "description": i18n.t("lp2_seo_desc", lang),
            "lang": lang, "dir": i18n.dir_for(lang), "start_url": "/dashboard", "scope": "/",
            "display": "standalone", "background_color": "#05070D", "theme_color": "#05070D",
            "icons": [icon("icon-192", 192), icon("icon-512", 512),
                      icon("icon-512", 512, purpose="maskable")]}
    return Response(json.dumps(data, ensure_ascii=False), mimetype="application/manifest+json")


@app.route("/.well-known/security.txt")
def security_txt():
    """RFC 9116: أين يُبلَّغ عن ثغرة — الباحث الأمني لا يبحث في صفحة «تواصل معنا»."""
    email = db.get_platform("support_email", "") or "info@botyalla.com"
    exp = (_dt.datetime.now(_dt.timezone.utc) + _dt.timedelta(days=365)).strftime("%Y-%m-%dT00:00:00Z")
    body = (f"Contact: mailto:{email}\nExpires: {exp}\nPreferred-Languages: ar, en\n"
            f"Canonical: {_site_base()}/.well-known/security.txt\n")
    return Response(body, mimetype="text/plain")


@app.route("/favicon.ico")
def favicon():
    return send_from_directory(os.path.join(app.static_folder, "brand"), "favicon-32.png",
                               mimetype="image/png", max_age=86400)


def seed_platform_defaults():
    if db.get_platform("seeded"): return
    db.set_platform("vodafone_number", "01097585951")
    db.set_platform("instapay_handle", "youssefalsherief@instapay")
    db.set_platform("instapay_link", "https://ipn.eg/S/youssefalsherief/instapay/0iOBCP")
    db.set_platform("bank_holder", "Youssef Mahmoud Saber Mahmoud")
    db.set_platform("bank_name", "Mashreq Bank")
    db.set_platform("bank_account", "059101546889")
    db.set_platform("bank_iban", "EG160046020400000059101546889")
    db.set_platform("platform_bot_token", "")
    db.set_platform("admin_chat_id", "")
    db.set_platform("support_email", "info@botyalla.com")
    db.set_platform("support_whatsapp", "201097585951")
    db.set_platform("support_telegram", "")
    # سعر الرسالة التسويقية **بالقروش**. مصر: $0.0644 للرسالة بعد خفض Meta
    # 1 يناير 2026 (كان $0.1073)، عند ~50.9ج/دولار ≈ 3.28ج. راجع
    # `business/WHATSAPP_PRICING_2026.md` — وأعد الحساب كل ربع سنة.
    # إعداد لا ثابت: السعر والصرف يتغيّران، والتعديل يجب ألا يحتاج نشراً.
    db.set_platform("mkt_msg_price", "328")
    db.set_platform("seeded", "1")

def _plan_names(lang=None):
    """أسماء الباقات للعرض في الجداول — ومعها شحن المحفظة.
    بدون السطر الأخير تظهر دفعة شحن في سجل المدفوعات باسم «مجانية»، لأن
    `plan_name` تُسقط أي معرّف مجهول إلى الباقة المجانية."""
    lang = lang or session.get("lang", i18n.DEFAULT)
    out = {k: plans.plan_name(k, lang) for k in plans.PLANS}
    out[db.WALLET_PLAN] = i18n.t("wallet_topup_label", lang)
    # إضافة «تحصيل المدفوعات» تُشترى لكل بوت: plan = __addon_pay__:<bot_id>
    for code in db.addon_plans_in_payments():
        out[code] = i18n.t("addon_pay_label", lang).format(id=db.addon_bot_id(code))
    return out


# ---------- محفظة الرسائل التسويقية (L-16) ----------
MKT_PRICE_FALLBACK = 328          # قرشاً — يُستعمل فقط لو ضاع الإعداد


def mkt_price():
    """سعر الرسالة التسويقية الواحدة بالقروش، من إعدادات المنصة."""
    try:
        v = int(str(db.get_platform("mkt_msg_price", "") or "").strip() or 0)
    except (TypeError, ValueError):
        v = 0
    return v if v > 0 else MKT_PRICE_FALLBACK


def _save_ops_settings(form):
    """سعر الرسالة التسويقية وسقف البوتات من لوحة الأدمن.

    يُحفظ كلٌّ منهما **فقط لو أرسله النموذج** (نموذج أقدم بلا الحقل لا يمسحه)،
    ويُتحقَّق منه قبل الحفظ: قيمة فاسدة لا تُحفظ أبداً — فلا يصير السعر صفراً
    (حملات تسويقية مجانية على حساب المنصة) ولا السقف بلا حدّ. السعر يُكتب
    بالجنيه (3.28) ويُخزَّن بالقروش الصحيحة (328) بـDecimal لا بالعائم.
    يرجّع رسائل الخطأ."""
    lang = session.get("lang", i18n.DEFAULT)
    errors = []
    if "mkt_msg_price_egp" in form:
        try:
            d = Decimal((form.get("mkt_msg_price_egp") or "").strip())
            ok = d.is_finite() and Decimal("0.01") <= d <= Decimal("1000")
        except InvalidOperation:
            ok = False
        if ok:
            db.set_platform("mkt_msg_price",
                            str(int((d * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))))
        else:
            errors.append(i18n.t("plat_bad_price", lang))
    if "ai_reply_price_egp" in form:
        # سعر رد «عقل البوت» فوق حصة الباقة — نفس قواعد السعر أعلاه، بسقف 100ج
        try:
            d = Decimal((form.get("ai_reply_price_egp") or "").strip())
            ok = d.is_finite() and Decimal("0.01") <= d <= Decimal("100")
        except InvalidOperation:
            ok = False
        if ok:
            db.set_platform("ai_reply_price",
                            str(int((d * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))))
        else:
            errors.append(i18n.t("plat_bad_ai_price", lang))
    if "bot_capacity" in form:
        raw = (form.get("bot_capacity") or "").strip()
        if raw == "":
            db.set_platform("bot_capacity", "")        # فارغ = الاحتياطي المحافظ
        elif raw.isdigit() and 1 <= int(raw) <= 100000:
            db.set_platform("bot_capacity", str(int(raw)))
        else:
            errors.append(i18n.t("plat_bad_capacity", lang))
    return errors


def _egp(piastres):
    """قروش → جنيهات للعرض. القسمة هنا فقط — الحساب كله بالقروش."""
    return round(int(piastres or 0) / 100.0, 2)


def _template_category(bot_row, name, language=None):
    """فئة القالب كما تقولها Meta — لا كما يرسلها الفورم.

    الفئة هي ما يقرّر الخصم من عدمه، فلو قُرئت من الفورم لأرسل أي أحد حملة
    تسويقية مؤشَّرة «UTILITY» ومرّت مجاناً. تُرجَع None لو تعذّرت القراءة،
    والمستدعي يرفض الإرسال حينها بدل أن يخمّن.
    """
    waba, _ = _waba_of(bot_row)
    cfg = json.loads(bot_row["config_json"] or "{}")
    if not waba or not cfg.get("wa_token"):
        return None
    res = WT.list_templates(waba, cfg.get("wa_token", ""))
    if not res.get("ok"):
        return None
    for t in res.get("items", []):
        if t.get("name") == name and (not language or t.get("language") == language):
            return (t.get("category") or "").upper()
    return None


def _campaign_quote(owner_id, recipients, category):
    """تكلفة حملة قبل إرسالها. تليجرام وكل ما ليس تسويقياً = صفر.

    تليجرام تكلفته الحدّية صفر فلا يُخصم عليه شيء أبداً؛ وقوالب UTILITY /
    AUTHENTICATION خارج المحفظة لأنها جزء من الخدمة المدفوعة في الباقة.
    """
    n = max(0, int(recipients or 0))
    if category != "MARKETING":
        return {"billable": False, "n": n, "price": 0, "cost": 0,
                "balance": db.wallet_balance(owner_id), "enough": True, "short": 0}
    price = mkt_price()
    cost = n * price
    bal = db.wallet_balance(owner_id)
    return {"billable": True, "n": n, "price": price, "cost": cost,
            "balance": bal, "enough": bal >= cost, "short": max(0, cost - bal)}


TOPUP_MIN, TOPUP_MAX = 50, 50000        # بالجنيه — حدّان عاقلان لا أكثر


@app.route("/wallet")
@login_required
def wallet_page():
    n = 25
    return react_page("wallet", "wallet_title",
                      {"balance": db.wallet_balance(uid()), "price": mkt_price(),
                       "ledger": db.wallet_ledger(uid(), n),
                       "plat": _public_plat(),
                       "qr": url_for("static", filename="instapay_qr.jpg"),
                       "min": TOPUP_MIN, "max": TOPUP_MAX,
                       "presets": [100, 250, 500, 1000],
                       "action": url_for("wallet_topup")})


@app.route("/wallet/topup", methods=["POST"])
@login_required
def wallet_topup():
    """طلب شحن رصيد. **لا يشحن شيئاً بنفسه** — ينشئ دفعة معلّقة كغيرها.

    مبلغ الشحن يختاره المستخدم بطبيعته (بعكس سعر الباقة الذي يفرضه الخادم،
    AGENTS.md §3.3): هو يعلن كم حوّل، والأدمن يطابقه مع الإيصال قبل الاعتماد.
    والرصيد لا يُضاف إلا داخل `finalize_payment` بعد تلك الموافقة.
    """
    ar = session.get("lang") != "en"
    if _rate_limited(f"u{uid()}", limit=8, window=3600, bucket="receipt"):   # نفس حدّ الاشتراك
        flash(i18n.t("ai_rate", session.get("lang", i18n.DEFAULT)), "error")
        return redirect(url_for("wallet_page"))
    try:
        amount = int(float(request.form.get("amount", "0") or 0))
    except (TypeError, ValueError, OverflowError):    # "inf" / "1e999" ترمي OverflowError
        amount = 0
    if not (TOPUP_MIN <= amount <= TOPUP_MAX):
        flash((f"مبلغ الشحن بين {TOPUP_MIN} و{TOPUP_MAX} ج.م." if ar else
               f"Top-up amount must be between {TOPUP_MIN} and {TOPUP_MAX} EGP."), "error")
        return redirect(url_for("wallet_page"))

    file = request.files.get("screenshot")
    if not file or not file.filename:
        flash("يجب رفع صورة إثبات الدفع." if ar else "Please upload the payment screenshot.", "error")
        return redirect(url_for("wallet_page"))
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in pay.ALLOWED_EXT:
        flash("صيغة الصورة غير مدعومة (jpg/png/webp)." if ar else
              "Unsupported image type (jpg/png/webp).", "error")
        return redirect(url_for("wallet_page"))
    data = file.read()
    imgchk = pay.validate_bytes(data)                 # الفحص قبل أي كتابة (§3.7)
    if not imgchk["ok"]:
        flash("الملف ليس صورة صالحة." if ar else "The file is not a valid image.", "error")
        return redirect(url_for("wallet_page"))
    # نفس فحص الاشتراك قبل الكتابة: المبلغ المطلوب هنا هو ما أعلنه للشحن
    ac, img_hash, refused = _receipt_check(data, amount)
    if refused:
        flash(refused, "error")
        return redirect(url_for("wallet_page"))
    fname = f"topup_{uid()}_{int(_time.time())}{ext}"
    fpath = os.path.join(UPLOAD_DIR, secure_filename(fname))
    with open(fpath, "wb") as _f:
        _f.write(data)
    pid = db.create_payment(uid(), db.WALLET_PLAN, request.form.get("method", ""),
                            float(amount), request.form.get("ref", "").strip(), fname,
                            img_hash, json.dumps(ac, ensure_ascii=False))
    log.info("wallet topup #%s requested user=%s amount=%s verdict=%s",
             pid, uid(), amount, ac.get("verdict"))
    admin_id = db.get_platform("admin_chat_id", "")
    payment = db.get_payment(pid)
    caption = PB.build_caption(payment, session.get("uname", ""), _verdict_detail(ac))
    msg_id = manager.send_payment_alert(admin_id, payment, session.get("uname", ""),
                                        caption, fpath) if admin_id else None
    if msg_id:
        db.set_payment_msg(pid, msg_id)
    else:
        notify_admins(f"💳 طلب شحن رصيد #{pid} / Wallet top-up — {session.get('uname')} — "
                      f"{amount} EGP. راجعه من لوحة الأدمن.")
    flash(("✅ تم استلام إثبات الشحن (#{}). يُضاف الرصيد بعد المراجعة والموافقة."
           if ar else
           "✅ Top-up proof received (#{}). Credit is added after review and approval.").format(pid),
          "ok")
    return redirect(url_for("wallet_page"))


# ---------- Webhooks ----------
@app.route("/wh/whatsapp", methods=["GET", "POST"])
def whatsapp_webhook():
    # المسار مُستثنى من CSRF، فالتوقيع هو الحارس الوحيد:
    # بلا سرّ مضبوط لا نقبل شيئاً (fail closed) بدل أن نفتح الباب للجميع.
    if request.method == "GET":
        verify = db.get_platform("wa_verify_token", "") or ""
        if not verify:
            abort(403)
        if (request.args.get("hub.mode") == "subscribe"
                and _secrets.compare_digest(request.args.get("hub.verify_token", ""), verify)):
            return request.args.get("hub.challenge", ""), 200
        abort(403)

    secret = db.get_platform("wa_app_secret", "") or ""
    if not secret:
        app.logger.warning("WhatsApp webhook POST rejected: wa_app_secret is not configured")
        abort(403)

    expected = "sha256=" + hmac.new(
        secret.encode("utf-8"), request.get_data(), hashlib.sha256).hexdigest()
    if not _secrets.compare_digest(request.headers.get("X-Hub-Signature-256", ""), expected):
        abort(403)

    payload = request.get_json(silent=True)
    if payload:
        manager.process_wa_webhook(payload)
    return "OK", 200

# إيميلات دعم افتراضية قديمة — تُستبدل بإيميل الدومين الرسمي عند الإقلاع.
_OLD_SUPPORT_EMAILS = ("info@youssefalsherief.tech",)

def contact_defaults():
    """يضمن وجود بيانات التواصل حتى لو كانت القاعدة قديمة قبل هذه الإضافة.
    القيمة الافتراضية القديمة (إيميل المالك الشخصي) تتحوّل لـ info@botyalla.com مرة واحدة؛
    أي إيميل آخر كتبه الأدمن بنفسه في «إعدادات المنصة» لا يُلمس."""
    cur = (db.get_platform("support_email") or "").strip().lower()
    if not cur or cur in _OLD_SUPPORT_EMAILS:
        db.set_platform("support_email", "info@botyalla.com")
    if not db.get_platform("support_whatsapp"):
        db.set_platform("support_whatsapp", "201097585951")

def seed_default_admin():
    """ينشئ حساب أدمن عند أول تشغيل (لو لا يوجد أي مستخدم). كلمة المرور من ADMIN_PASS،
    وإلا عشوائية تُطبع مرة واحدة — لا كلمة افتراضية ثابتة: admin1234 كانت مكتوبة في
    الوثائق وفي تاريخ git، فأي خادم نُسي ضبطه كان مفتوحاً لمن قرأها."""
    if db.count_users() > 0:
        return
    u = os.getenv("ADMIN_USER", "admin")
    pw = os.getenv("ADMIN_PASS") or _secrets.token_urlsafe(12)
    db.create_user(u, auth.hash_password(pw))   # أول مستخدم = admin تلقائياً
    print("=" * 56)
    print("  🔐 تم إنشاء حساب الأدمن الافتراضي / Default admin created")
    print(f"     Username: {u}")
    print(f"     Password: {pw}")
    print("  ⚠️  غيّر كلمة المرور بعد أول دخول من صفحة «حسابي».")
    print("=" * 56)

def _migrate_ai_key():
    if not db.get_platform("ai_key", ""):
        old = db.get_setting(1, "ai_key", "")
        if old:
            db.set_platform("ai_key", old)
            db.set_platform("ai_provider", db.get_setting(1, "ai_provider", "gemini"))

def bootstrap():
    setup_logging()
    db.init_db(); seed_platform_defaults(); contact_defaults(); seed_default_admin(); _migrate_ai_key()
    manager.start(); manager.resume_active_bots()
    EC.resume_pending()          # حملة بريد قُطعت بإعادة التشغيل تكمل من حيث توقفت
    tok = db.get_platform("platform_bot_token", "")
    if tok and db.get_platform("admin_chat_id", ""):
        manager.start_platform_bot(tok)

if __name__ == "__main__":
    bootstrap()
    try: _port = int(os.getenv("PORT", "5000"))
    except ValueError: _port = 5000
    app.run(host=os.getenv("HOST", "127.0.0.1"), port=_port, debug=False)
