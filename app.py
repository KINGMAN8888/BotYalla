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
                   get_flashed_messages)

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
import tg_helpers as tg
from channels.whatsapp import verify_credentials as wa_verify
import channels.wa_templates as WT
import media_store
from bot_manager import WA_WINDOW
import ai_agent as ai
import i18n
import plans
import payments as pay
import platform_bot as PB
import time as _time
import datetime as _dt
import hashlib
import hmac
import secrets as _secrets
from markupsafe import Markup
from werkzeug.utils import secure_filename
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
    MAX_CONTENT_LENGTH=10 * 1024 * 1024,   # حد أقصى 10MB للطلب (حماية رفع الملفات)
)

# BOTYALLA_UPLOADS يسمح للاختبارات بالكتابة في مجلد مؤقت — بدونه تتراكم
# ملفات وهمية بين إيصالات الدفع الحقيقية، كما حدث فعلاً.
UPLOAD_DIR = os.environ.get(
    "BOTYALLA_UPLOADS",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "uploads"))
os.makedirs(UPLOAD_DIR, exist_ok=True)

# ---------- حماية CSRF (خفيفة، بدون مكتبات) ----------
_login_attempts = {}   # ip -> (count, first_ts)

@app.before_request
def _csrf_protect():
    if request.method in ("POST", "PUT", "PATCH", "DELETE"):
        if request.path == "/wh/whatsapp":
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
    g.user = row
    # مزامنة الجلسة مع القاعدة (قد يكون الأدمن غيّر الدور أو الاسم)
    if session.get("role") != row["role"]: session["role"] = row["role"]
    if session.get("uname") != row["username"]: session["uname"] = row["username"]

@app.context_processor
def _csrf_ctx():
    if "_csrf" not in session:
        session["_csrf"] = _secrets.token_hex(16)
    tok = session["_csrf"]
    return {"csrf_token": tok,
            "csrf_field": lambda: Markup(f'<input type="hidden" name="csrf_token" value="{tok}">')}

def _rate_limited(ip, limit=8, window=300):
    now = int(_time.time())
    cnt, first = _login_attempts.get(ip, (0, now))
    if now - first > window:
        cnt, first = 0, now
    cnt += 1
    _login_attempts[ip] = (cnt, first)
    return cnt > limit

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
    cfg["tg_synced_at"] = int(_time.time())
    cfg["tg_sync_ok"] = bool(res.get("ok"))
    cfg["tg_sync_errors"] = res.get("errors", [])
    db.update_bot_config(bot_row["id"], cfg)
    return res

def notify_admins(text):
    """إشعار كل الأدمنز على تليجرام بأي حركة (best-effort)."""
    try:
        for aid in db.admin_chat_ids():
            manager.notify_text(aid, text)
    except Exception:
        pass

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
    return redirect(url_for("dashboard"))

# ---------- المصادقة ----------
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        u = request.form.get("username", "").strip()
        p = request.form.get("password", "")
        if len(u) < 3 or len(p) < 6:
            flash("اسم المستخدم 3 أحرف على الأقل وكلمة المرور 6.", "error")
        elif db.get_user_by_name(u):
            flash("اسم المستخدم موجود بالفعل.", "error")
        else:
            user_id = db.create_user(u, auth.hash_password(p))
            urow = db.get_user(user_id)
            session["uid"] = user_id; session["uname"] = u; session["role"] = urow["role"]
            ref_code = session.pop("ref", None)      # التُقط من ?ref= على أي صفحة
            if ref_code:
                db.attach_referral(user_id, ref_code)
            notify_admins(f"🆕 تسجيل مستخدم جديد / New user: {u} (#{user_id})"
                          + (f" — عبر إحالة {ref_code}" if ref_code else ""))
            return redirect(url_for("dashboard"))
    return react_page("register", "register")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        if _rate_limited(request.remote_addr or "?"):
            flash("محاولات كثيرة. انتظر قليلاً." if session.get("lang")!="en" else "Too many attempts. Please wait.", "error")
            return react_page("login", "login")
        u = request.form.get("username", "").strip()
        p = request.form.get("password", "")
        row = db.get_user_by_name(u)
        if row and row.get("is_blocked"):
            flash("تم حظر هذا الحساب." if session.get("lang")!="en" else "This account is blocked.", "error")
            return react_page("login", "login")
        if row and auth.verify_password(p, row["pw_hash"]):
            session["uid"] = row["id"]; session["uname"] = u; session["role"] = row.get("role","user")
            return redirect(url_for("dashboard"))
        flash("بيانات دخول غير صحيحة.", "error")
    return react_page("login", "login")

@app.route("/logout")
def logout():
    session.clear(); return redirect(url_for("login"))

# ---------- الرئيسية ----------
@app.route("/")
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
    wa_ok = current_role() in ("admin", "support") or bool(plans.plan(plan_id).get("whatsapp"))
    return react_page("dashboard", "nav_bots",
                      {"bots": bots, "total": total, "waAllowed": wa_ok})

def _owned(bot_id):
    b = db.get_bot(bot_id, uid())
    if not b: abort(404)
    return b

@app.route("/bot/create", methods=["POST"])
@login_required
def bot_create():
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
                flash(("بوتات واتساب متاحة من الباقة الاحترافية فأعلى."
                       if session.get("lang") != "en" else
                       "WhatsApp bots require the Pro plan or higher."), "error")
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
    cfg = {"business_name": name, "owner_chat_id": request.form.get("owner_chat_id", "").strip(),
           "welcome": "", "thanks": "", "products": [],
           "service_name": name, "days_ahead": 7, "open_hour": 10, "close_hour": 22,
           "slot_minutes": 60, "working_days": None, "flow": None, "welcome_image": "",
           "menu_items": [], "bot_username": info.get("username"), "bot_name": info.get("name"),
           "pending_owner_code": None}
    # قوالب ثابتة جاهزة حسب النوع
    if template in T.PRESET_FLOWS:
        cfg["flow"] = json.loads(json.dumps(T.PRESET_FLOWS[template]))  # نسخة قابلة للتعديل
    if template == "faq":
        cfg["menu_items"] = json.loads(json.dumps(T.DEFAULT_MENU_ITEMS))
        
    if channel == "whatsapp":
        cfg["wa_token"] = request.form.get("wa_token", "").strip()
        
    try:
        db.create_bot(uid(), name, token, template, cfg, channel)
        notify_admins(f"🤖 بوت جديد / New bot: «{name}» (@{info.get('username')}) — {session.get('uname')}")
        # تهيئة رسمية للبوت على تليجرام (إذا كان تليجرام)
        if channel == "telegram":
            try:
                _row = [b for b in db.list_bots(uid()) if b["token"] == token]
                if _row: sync_bot_telegram(_row[0])
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
    
    sub = db.get_subscription(uid())
    plan_id = sub["plan"] if sub["status"] == "active" else "free"
    p = plans.plan(plan_id)
    if current_role() in ("admin", "support"):
        p = plans.plan("business") # Full access

    usage = None
    if (b.get("channel") or "telegram") == "whatsapp":
        limit = None if current_role() in ("admin", "support") else plans.wa_limit(plan_id)
        usage = dict(db.owner_usage(uid()), limit=limit,
                     bot=db.bot_usage(bot_id), webhook=url_for("whatsapp_webhook", _external=True))

    return react_page("bot_detail", "nav_bots",
                      {"bot": b, "leads": leads, "orders": orders, "bookings": bookings,
                       "plan": p, "usage": usage},
                      title=b["name"])

@app.route("/bot/<int:bot_id>/config", methods=["POST"])
@login_required
def bot_config(bot_id):
    b = _owned(bot_id); cfg = json.loads(b["config_json"] or "{}")
    for k in ("business_name", "owner_chat_id", "welcome", "thanks", "welcome_image"):
        cfg[k] = request.form.get(k, cfg.get(k, "")).strip()
    if b["template"] == "faq":
        items = []
        for q, a in zip(request.form.getlist("m_q"), request.form.getlist("m_a")):
            q = q.strip()
            if q: items.append({"q": q[:60], "a": (a or "").strip()[:1000]})
        cfg["menu_items"] = items
    if b["template"] == "store":
        prods = []
        imgs = request.form.getlist("p_image")
        for i, (n, p) in enumerate(zip(request.form.getlist("p_name"), request.form.getlist("p_price"))):
            n = n.strip()
            if not n: continue
            try: price = float(p)
            except ValueError: price = 0.0
            item = {"name": n, "price": price}
            img = (imgs[i].strip() if i < len(imgs) else "")
            if img.startswith("http"): item["image"] = img
            prods.append(item)
        cfg["products"] = prods
    if b["template"] == "booking":
        for k, cast in (("days_ahead", int), ("open_hour", int),
                        ("close_hour", int), ("slot_minutes", int)):
            try: cfg[k] = cast(request.form.get(k, cfg.get(k)))
            except (ValueError, TypeError): pass
        cfg["service_name"] = request.form.get("service_name", cfg.get("service_name", "")).strip()
        wd = request.form.getlist("working_days")
        cfg["working_days"] = [int(x) for x in wd] if wd else None
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
    db.update_bot_config(bot_id, cfg)
    if manager.is_running(bot_id): manager.restart_bot(bot_id)
    if is_wa:
        flash("تم حفظ الإعدادات ✅" if session.get("lang") != "en" else "Settings saved ✅", "ok")
        return redirect(url_for("bot_detail", bot_id=bot_id))
    try: sync_bot_telegram(db.get_bot(bot_id, uid()))
    except Exception: pass
    flash("تم حفظ الإعدادات ومزامنتها مع تليجرام ✅", "ok")
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
        STEP_TYPES = ("question", "buttons", "message", "media")
        for i, t in enumerate(types):
            if t not in STEP_TYPES:      # نوع غير معروف يجعل المحرك يعامله كسؤال نصي
                t = "question"
            prompt = (prompts[i] if i < len(prompts) else "").strip()
            if not prompt: continue
            step = {"id": f"s{i}", "type": t, "prompt": prompt,
                    "var": (vars_[i] if i < len(vars_) else "").strip() or f"حقل{i+1}"}
            if t == "buttons":
                o = [x.strip() for x in (opts[i] if i < len(opts) else "").split(",") if x.strip()]
                step["options"] = o
            step.pop("var", None) if t == "message" else None
            flow["steps"].append(step)
        cfg["flow"] = flow
        db.update_bot_config(bot_id, cfg)
        if manager.is_running(bot_id): manager.restart_bot(bot_id)
        flash("تم حفظ الفلو ✅", "ok")
        return redirect(url_for("flow_builder", bot_id=bot_id))
    flow = cfg.get("flow") or {"start_message": "", "end_message": "", "steps": []}
    return react_page("flow", "flow_title", {"bot": b, "flow": flow},
                      title=i18n.t("flow_title", session.get("lang", i18n.DEFAULT)) + " · " + b["name"])

# ---------- تشغيل / إيقاف / حذف ----------
@app.route("/bot/<int:bot_id>/<any(start,stop,delete):action>", methods=["POST"])
@login_required
def bot_action(bot_id, action):
    _owned(bot_id)
    if action == "start": ok, msg = manager.start_bot(bot_id)
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
    return react_page("analytics", "analytics", {"bot": b}, needs_chart=True,
                      title=i18n.t("analytics", session.get("lang", i18n.DEFAULT)) + " · " + b["name"])

@app.route("/api/bot/<int:bot_id>/stats")
@login_required
def api_stats(bot_id):
    _owned(bot_id)
    return jsonify({"summary": db.stats_summary(bot_id), "daily": db.stats_daily(bot_id, 14)})

# ---------- البث الجماعي ----------
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
        if is_wa and request.form.get("mode") == "template":
            name = request.form.get("template", "").strip()
            lang_code = request.form.get("template_lang", "").strip() or "ar"
            values = [v.strip() for v in request.form.getlist("var") if v.strip()]
            if not name:
                flash("اختر قالباً معتمداً." if ar else "Pick an approved template.", "error")
            else:
                sent, failed = manager.broadcast_template(bot_id, name, lang_code, values)
                flash((f"📢 أُرسل القالب «{name}» إلى {sent} مشترك (فشل {failed})." if ar else
                       f"📢 Template «{name}» sent to {sent} subscribers ({failed} failed)."), "ok")
        else:
            text = request.form.get("text", "").strip()
            if not text:
                flash("اكتب نص الرسالة." if ar else "Write the message.", "error")
            else:
                sent, failed = manager.broadcast(bot_id, text)
                flash((f"📢 تم الإرسال إلى {sent} مشترك (فشل {failed})." if ar else
                       f"📢 Sent to {sent} subscribers ({failed} failed)."), "ok")
        return redirect(url_for("broadcast", bot_id=bot_id))

    return react_page("broadcast", "campaign_title",
                      {"bot": b, "subs": subs, "isWa": is_wa, "reachable": reachable,
                       "waba": _waba_of(b)[0] if is_wa else ""},
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
                      {"bot": b, "waba": waba, "wabaHint": hint,
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

# ---------- تصدير CSV ----------
@app.route("/bot/<int:bot_id>/export/<kind>")
@login_required
def export_csv(bot_id, kind):
    _owned(bot_id)
    out = io.StringIO(); w = csv.writer(out)
    if kind == "orders":
        w.writerow(["العميل", "التليفون", "العنوان", "المنتجات", "الإجمالي", "الوقت"])
        for o in db.list_orders(bot_id):
            items = "; ".join(f"{i['name']}x{i['qty']}" for i in o["items"])
            w.writerow([o["customer"], o["phone"], o["address"], items, o["total"], o["created_at"]])
    elif kind == "bookings":
        w.writerow(["العميل", "التليفون", "الخدمة", "الموعد", "الحالة"])
        for x in db.list_bookings(bot_id):
            w.writerow([x["customer"], x["phone"], x["service"], x["slot"], x["status"]])
    elif kind == "leads":
        w.writerow(["البيانات", "الوقت"])
        for l in db.list_leads(bot_id):
            w.writerow([json.dumps(l["data"], ensure_ascii=False), l["created_at"]])
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

@app.route("/bot/<int:bot_id>/ai-setup", methods=["POST"])
@login_required
def ai_setup(bot_id):
    b = _owned(bot_id); cfg = json.loads(b["config_json"] or "{}")
    desc = (request.get_json(silent=True) or {}).get("description", "").strip()
    if not desc:
        return jsonify({"ok": False, "error": "اكتب وصف نشاطك أولاً."})
        
    sub = db.get_subscription(uid())
    plan_id = sub["plan"] if sub["status"] == "active" else "free"
    p = plans.plan(plan_id)
    
    key = db.get_platform("ai_key", "")
    provider = db.get_platform("ai_provider", "gemini")
    
    if current_role() not in ("admin", "support") and not p.get("ai"):
        key = None  # Force fallback offline generator
    patch, source = ai.generate_bot_config(desc, b["template"], api_key=key or None, provider=provider)
    if not patch:
        return jsonify({"ok": False, "error": "تعذّر توليد الإعدادات."})
    cfg.update(patch)
    db.update_bot_config(bot_id, cfg)
    if manager.is_running(bot_id): manager.restart_bot(bot_id)
    return jsonify({"ok": True, "source": source, "applied": list(patch.keys())})


# ---------- تكامل تليجرام ----------
@app.route("/api/validate-token", methods=["POST"])
@login_required
def api_validate_token():
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
    return react_page("pricing", "pricing_title",
                      {"plans": [dict(p, name=plans.plan_name(p["id"], lang))
                                 for p in priced_plans(lang)], "sub": sub})

@app.route("/subscribe/<plan_id>", methods=["GET"])
@login_required
def subscribe(plan_id):
    if plan_id not in plans.PLANS or plan_id == "free":
        return redirect(url_for("pricing"))
    p = plans.plan(plan_id)
    plat = db.all_platform()
    _pr = _plan_pricing(plan_id)
    return react_page("subscribe", "pay_title",
                      {"planId": plan_id, "plan": dict(p, id=plan_id, **_pr), "plat": plat,
                       "qr": url_for("static", filename="instapay_qr.jpg"),
                       "action": url_for("subscribe_pay", plan_id=plan_id)})

@app.route("/subscribe/<plan_id>", methods=["POST"])
@login_required
def subscribe_pay(plan_id):
    if plan_id not in plans.PLANS or plan_id == "free":
        return redirect(url_for("pricing"))
    # التسعيرة تُحسب في الخادم: سعر الباقة بعد تجاوز المالك وخصمها، ثم كود
    # الخصم إن صحّ. لا يُقرأ أي مبلغ من الفورم (AGENTS.md §3.3).
    q = quote(plan_id, uid(), request.form.get("promo", ""))
    method = request.form.get("method", "")
    ref = request.form.get("ref", "").strip()
    file = request.files.get("screenshot")
    if not file or not file.filename:
        flash("يجب رفع صورة إثبات الدفع." if session.get("lang")!="en" else "Please upload the payment screenshot.", "error")
        return redirect(url_for("subscribe", plan_id=plan_id))
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in pay.ALLOWED_EXT:
        flash("صيغة الصورة غير مدعومة (jpg/png/webp)." if session.get("lang")!="en" else "Unsupported image type (jpg/png/webp).", "error")
        return redirect(url_for("subscribe", plan_id=plan_id))
    fname = f"pay_{uid()}_{int(_time.time())}{ext}"
    fpath = os.path.join(UPLOAD_DIR, secure_filename(fname))
    file.save(fpath)
    # فحص توقيع الملف قبل تسجيل أي شيء: ما ليس صورة ليس إيصالاً،
    # فلا يُحفظ على القرص ولا يُنشأ له طلب دفع (AGENTS.md §3.7).
    imgchk = pay.validate_image(fpath)
    if not imgchk["ok"]:
        try: os.remove(fpath)
        except OSError: pass
        _reason = {"not_an_image": ("الملف ليس صورة صالحة.", "The file is not a valid image."),
                   "too_small":    ("الصورة صغيرة جداً.", "The image is too small."),
                   "too_large":    ("الصورة كبيرة جداً (الحد 8 ميجابايت).", "The image is too large (8MB max)."),
                   }.get(imgchk.get("reason"), ("تعذّر قراءة الصورة.", "Could not read the image."))
        flash(_reason[0] if session.get("lang")!="en" else _reason[1], "error")
        return redirect(url_for("subscribe", plan_id=plan_id))
    # الفحص الآلي
    img_hash = pay.file_sha256(fpath)
    dup = db.img_hash_seen(img_hash)
    refs = [db.get_platform("vodafone_number",""), db.get_platform("instapay_handle",""),
            db.get_platform("bank_iban",""), db.get_platform("bank_account","")]
    ac = pay.auto_check(fpath, q["total"], [r for r in refs if r], duplicate=dup)
    pid = db.create_payment(uid(), plan_id, method, q["total"], ref, fname, img_hash,
                            json.dumps(ac, ensure_ascii=False),
                            promo_id=(q["promo"]["id"] if q["promo"] else None),
                            discount=round(q["list_price"] - q["total"], 2),
                            base_amount=q["list_price"])
    # تنبيه الأدمن على تليجرام بزرّي موافقة/رفض (طبقة التحقق الثانية)
    admin_id = db.get_platform("admin_chat_id", "")
    payment = db.get_payment(pid)
    lang = session.get("lang","ar")
    _lines = pay.check_lines(ac, "ar")
    _detail = pay.verdict_label(ac["verdict"], "ar") + "\n" + "\n".join(
        ("✅ " if c["ok"] else ("❌ " if c["ok"] is False else "• ")) + c["text"] for c in _lines)
    caption = PB.build_caption(payment, session.get("uname",""), _detail)
    msg_id = manager.send_payment_alert(admin_id, payment, session.get("uname",""), caption, fpath) if admin_id else None
    if msg_id: db.set_payment_msg(pid, msg_id)
    if not msg_id:
        notify_admins(f"💳 طلب دفع جديد #{pid} / New payment — {session.get('uname')} — {q['total']} EGP ({plan_id})"
                      + (f" · كود {q['promo_code']}" if q["promo_code"] else "") + ". راجعه من لوحة الأدمن.")
    flash(("✅ تم استلام إثبات الدفع (#{}). سيتم تفعيل اشتراكك بعد المراجعة والموافقة."
           if lang!="en" else
           "✅ Payment proof received (#{}). Your subscription will activate after review and approval.").format(pid), "ok")
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
                       "names": {k: plans.plan_name(k, session.get("lang", i18n.DEFAULT)) for k in plans.PLANS}})

@app.route("/admin/platform", methods=["GET", "POST"])
@require_roles("admin")
def admin_platform():
    if request.method == "POST":
        for k in ("vodafone_number","instapay_handle","instapay_link",
                  "bank_holder","bank_name","bank_account","bank_iban",
                  "platform_bot_token","admin_chat_id",
                  "support_email","support_whatsapp","support_telegram",
                  "wa_verify_token","wa_app_secret"):
            db.set_platform(k, request.form.get(k, "").strip())
        tok = db.get_platform("platform_bot_token",""); adm = db.get_platform("admin_chat_id","")
        if tok and adm:
            ok, msg = manager.start_platform_bot(tok)
            flash(("تم الحفظ. " if session.get("lang")!="en" else "Saved. ")+msg, "ok" if ok else "error")
        else:
            flash("تم الحفظ." if session.get("lang")!="en" else "Saved.", "ok")
        return redirect(url_for("admin_platform"))
    return react_page("admin_platform", "platform_title",
                      {"plat": db.all_platform(), "running": manager.platform_running()})

# ---------- لوحة تحكم الأدمن ----------
@app.route("/admin")
@require_roles("admin", "support")
def admin_home():
    return react_page("admin_overview", "nav_admin", {"stats": db.platform_stats()}, needs_chart=True)

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
                       "names": {k: plans.plan_name(k, session.get("lang", i18n.DEFAULT)) for k in plans.PLANS}})

@app.route("/admin/payments/<int:pid>/<any(approve,reject):decision>", methods=["POST"])
@require_roles("admin")
def admin_payment_decide(pid, decision):
    status = "approved" if decision == "approve" else "rejected"
    row = db.finalize_payment(pid, status)
    if row:
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
    plat = db.all_platform()
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
        if new_user and len(new_user) < 3:
            flash("اسم المستخدم قصير." if session.get("lang")!="en" else "Username too short.", "error")
            return redirect(url_for("account"))
        if new_pw and len(new_pw) < 6:
            flash("كلمة المرور قصيرة." if session.get("lang")!="en" else "Password too short.", "error")
            return redirect(url_for("account"))
        ok, err = db.update_user_credentials(
            uid(),
            username=new_user if (new_user and new_user != me["username"]) else None,
            pw_hash=auth.hash_password(new_pw) if new_pw else None)
        if not ok and err == "username_taken":
            flash("اسم المستخدم مستخدم بالفعل." if session.get("lang")!="en" else "Username already taken.", "error")
            return redirect(url_for("account"))
        if new_user: session["uname"] = new_user
        flash("تم تحديث بيانات حسابك ✅" if session.get("lang")!="en" else "Account updated ✅", "ok")
        return redirect(url_for("account"))
    return react_page("account", "account_title", {
        "me": dict(me, pw_hash=None),
        "tgLinked": bool(db.get_setting(uid(), "tg_chat_id")),
        "tgFallback": bool(db.user_tg_channel(uid())),
        "hasPlatformBot": bool(db.get_platform("platform_bot_token", "")),
    })

@app.route("/account/link-telegram", methods=["POST"])
@login_required
def account_link_telegram():
    """يولّد رابط ربط لمرة واحدة عبر بوت المنصة، ليصل العميل تذكير الاشتراك."""
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
    if len(u) < 3 or len(pw) < 6:
        flash("اسم 3 أحرف وكلمة مرور 6 على الأقل." if session.get("lang")!="en" else "Username 3+ and password 6+ chars.", "error")
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

def _plan_pricing(plan_id, overrides=None):
    """يرجّع تسعير الباقة بعد تجاوزات المالك وخصمها المعلن."""
    base = plans.plan(plan_id)
    ov = (overrides if overrides is not None else db.plan_overrides()).get(plan_id) or {}
    price = ov.get("price")
    price = float(base["price"]) if price is None else float(price)
    disc = float(ov.get("discount_pct") or 0)
    final = round(price * (1 - disc / 100.0), 2)
    return {"list_price": round(price, 2), "discount_pct": disc,
            "price": max(0.0, final), "has_discount": disc > 0 and final < price}

def priced_plans(lang=None):
    """كل الباقات بأسعارها الفعلية — للعرض في الواجهة."""
    lang = lang or session.get("lang", i18n.DEFAULT)
    ov = db.plan_overrides()
    out = []
    for pid in plans.ORDER:
        p = dict(plans.PLANS[pid], id=pid)
        p.update(_plan_pricing(pid, ov))
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

def quote(plan_id, user_id, code=None):
    """التسعيرة النهائية: سعر الباقة بعد خصمها المعلن، ثم كود الخصم إن صحّ.
    هذه الدالة وحدها تحدّد ما يُخزَّن في payments.amount."""
    pricing = _plan_pricing(plan_id)
    base = pricing["price"]
    promo, reason = validate_promo(code, plan_id, user_id)
    cut = 0.0
    if promo:
        cut = (base * float(promo["value"]) / 100.0) if promo["kind"] == "percent" else float(promo["value"])
        cut = round(min(cut, base), 2)
    total = round(max(0.0, base - cut), 2)
    return {
        "plan": plan_id,
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
                  "check","rocket","tag","phone","bot","card","users","wallet","bolt")

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

def react_page(view, title_key, props=None, needs_chart=False, title=None):
    """يرسم صفحة React مع قشرة اللوحة وبياناتها."""
    lang = session.get("lang", i18n.DEFAULT)
    role = current_role()
    nav = [
        {"k": "dashboard",   "u": url_for("dashboard"),    "i": "grid",     "l": i18n.t("nav_bots", lang)},
        {"k": "pricing",     "u": url_for("pricing"),      "i": "tag",      "l": i18n.t("nav_pricing", lang)},
        {"k": "billing",     "u": url_for("billing"),      "i": "card",     "l": i18n.t("nav_billing", lang)},
        {"k": "request_bot", "u": url_for("request_bot"),  "i": "sparkles", "l": i18n.t("custom_bot", lang)},
        {"k": "affiliate",   "u": url_for("affiliate"),    "i": "crown",    "l": i18n.t("aff_title", lang)},
    ]
    admin_nav = []
    if role in ("admin", "support"):
        admin_nav = [
            {"k": "admin_overview", "u": url_for("admin_home"),     "i": "shield", "l": i18n.t("nav_admin", lang)},
            {"k": "admin_users",    "u": url_for("admin_users"),    "i": "users",  "l": i18n.t("admin_users_t", lang)},
            {"k": "admin_payments", "u": url_for("admin_payments"), "i": "wallet", "l": i18n.t("admin_payments_t", lang)},
            {"k": "admin_requests", "u": url_for("admin_requests"), "i": "inbox",  "l": i18n.t("nav_requests", lang)},
        ]
        if role == "admin":
            # مزايا المالك وحده — لا يراها الدعم إطلاقاً
            admin_nav += [
                {"k": "admin_pricing",    "u": url_for("admin_pricing"),    "i": "tag",      "l": i18n.t("adm_pricing", lang)},
                {"k": "admin_promos",     "u": url_for("admin_promos"),     "i": "bolt",     "l": i18n.t("adm_promos", lang)},
                {"k": "admin_affiliates", "u": url_for("admin_affiliates"), "i": "users",    "l": i18n.t("adm_affiliates", lang)},
                {"k": "settings",         "u": url_for("settings"),         "i": "sparkles", "l": i18n.t("nav_ai", lang)},
                {"k": "admin_platform",   "u": url_for("admin_platform"),   "i": "settings", "l": i18n.t("nav_platform", lang)},
            ]

    payload = {
        "view": view, "lang": lang, "dir": i18n.dir_for(lang), "brand": "BotYalla",
        "csrf": session.get("_csrf", ""),
        "user": {"name": session.get("uname"), "role": role},
        "t": {k: i18n.t(k, lang) for k in i18n.T},
        "icons": {n: _icon_svg(n) for n in icons._P},
        "nav": nav, "adminNav": admin_nav,
        "flashes": [{"c": c, "m": m} for c, m in get_flashed_messages(with_categories=True)],
        "urls": {
            "dashboard": url_for("dashboard"), "pricing": url_for("pricing"),
            "billing": url_for("billing"), "account": url_for("account"),
            "logout": url_for("logout"), "login": url_for("login"),
            "register": url_for("register"), "landing": url_for("landing"),
            "requestBot": url_for("request_bot"), "botCreate": url_for("bot_create"),
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
                           by_json=json.dumps(payload, ensure_ascii=False, default=str))

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
    if plan_id not in plans.PLANS or plan_id == "free":
        return jsonify({"ok": False})
    q = quote(plan_id, uid(), d.get("code", ""))
    lang = session.get("lang", i18n.DEFAULT)
    return jsonify({
        "ok": True,
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
        "link": (url_for("landing", _external=True) + "?ref=" + aff["code"]) if aff else None,
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


# تاريخ آخر تعديل فعلي على النصوص القانونية — حدّثه عند تغيير الشروط.
LEGAL_UPDATED = "2026-09-02"

@app.route("/terms")
def terms():
    return react_page("terms", "terms_title",
                      {"email": db.get_platform("support_email", "info@youssefalsherief.tech"),
                       "updated": LEGAL_UPDATED})

@app.route("/privacy")
def privacy():
    return react_page("privacy", "privacy_title",
                      {"email": db.get_platform("support_email", "info@youssefalsherief.tech"),
                       "updated": LEGAL_UPDATED})


@app.route("/landing")
def landing():
    lang = session.get("lang", i18n.DEFAULT)
    # كل نصوص الواجهة تُحقن من الخادم — لا نص مكتوب داخل حزمة React
    keys = ("hero_title_a","hero_title_b","hero_sub","lp_badge","lp_cta_demo",
            "lp_trust_1","lp_trust_2","lp_trust_3","lp_live","get_started_free",
            "signin_link","daily_activity","lp_feats_t","lp_feats_sub","lp_how_t",
            "lp_how_sub","lp_faq_t","lp_final_t","lp_final_sub","nav_pricing","login",
            "brand_tag","footer_terms","footer_privacy")
    payload = i18n.landing_payload(lang)
    plat = db.all_platform()
    payload.update({
        "lang": lang,
        "dir": i18n.dir_for(lang),
        "brand": "BotYalla",
        "t": {k: i18n.t(k, lang) for k in keys},
        "icons": {n: _icon_svg(n) for n in _LANDING_ICONS},
        "urls": {"register": url_for("register"), "login": url_for("login"),
                 "pricing": url_for("pricing"), "home": url_for("landing"),
                 "logo": url_for("static", filename="logo.svg"),
                 "lang": url_for("set_lang", code="en" if lang == "ar" else "ar"),
                 "terms": url_for("terms"), "privacy": url_for("privacy")},
        "contact": [
            {"l": plat.get("support_email", ""), "h": "mailto:" + plat.get("support_email", "")},
            {"l": "WhatsApp", "h": "https://wa.me/" + plat.get("support_whatsapp", "")},
            {"l": "youssefalsherief.tech", "h": "https://youssefalsherief.tech/"},
        ],
        "templates": [
            {"icon": {"flow":"flow","store":"store","booking":"calendar",
                      "customer_service":"phone","faq":"grid","feedback":"sparkles",
                      "support":"shield"}.get(k, "bot"),
             "name": i18n.t({"flow":"tmpl_flow","store":"tmpl_store","booking":"tmpl_booking",
                             "customer_service":"tmpl_cs","faq":"tmpl_faq",
                             "feedback":"tmpl_feedback","support":"tmpl_support"}[k], lang)}
            for k in ("flow","store","booking","customer_service","faq","feedback","support")
        ],
    })
    return render_template("landing.html", by_json=json.dumps(payload, ensure_ascii=False))


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
    db.set_platform("support_email", "info@youssefalsherief.tech")
    db.set_platform("support_whatsapp", "201097585951")
    db.set_platform("support_telegram", "")
    db.set_platform("seeded", "1")

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

def contact_defaults():
    """يضمن وجود بيانات التواصل حتى لو كانت القاعدة قديمة قبل هذه الإضافة."""
    if not db.get_platform("support_email"):
        db.set_platform("support_email", "info@youssefalsherief.tech")
    if not db.get_platform("support_whatsapp"):
        db.set_platform("support_whatsapp", "201097585951")

def seed_default_admin():
    """ينشئ حساب أدمن افتراضياً عند أول تشغيل (لو لا يوجد أي مستخدم)."""
    if db.count_users() > 0:
        return
    u = os.getenv("ADMIN_USER", "admin")
    pw = os.getenv("ADMIN_PASS", "admin1234")
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
    db.init_db(); seed_platform_defaults(); contact_defaults(); seed_default_admin(); _migrate_ai_key()
    manager.start(); manager.resume_active_bots()
    tok = db.get_platform("platform_bot_token", "")
    if tok and db.get_platform("admin_chat_id", ""):
        manager.start_platform_bot(tok)

if __name__ == "__main__":
    bootstrap()
    try: _port = int(os.getenv("PORT", "5000"))
    except ValueError: _port = 5000
    app.run(host=os.getenv("HOST", "127.0.0.1"), port=_port, debug=False)
