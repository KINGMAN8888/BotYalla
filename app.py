"""BotYalla — لوحة التحكم (Flask).
حسابات مستخدمين بتشفير، إنشاء/تشغيل بوتات، باني فلو No-Code،
تحليلات (JSON للرسوم)، بث جماعي، حجوزات، تصدير."""
import os, json, csv, io, functools
from flask import (Flask, request, redirect, url_for, render_template,
                   session, flash, abort, jsonify, Response, send_from_directory)
import database as db
import auth
from bot_manager import manager
import templates_bot as T
import tg_helpers as tg
import ai_agent as ai
import i18n
import plans
import payments as pay
import platform_bot as PB
import time as _time
import datetime as _dt
import hashlib
import secrets as _secrets
from markupsafe import Markup
from werkzeug.utils import secure_filename
from icons import icon

app = Flask(__name__, template_folder="templates_web", static_folder="static")
app.secret_key = os.getenv("FLASK_SECRET", "botyalla-dev-secret-change-me")
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.getenv("COOKIE_SECURE", "0") == "1",  # فعّلها على HTTPS
    MAX_CONTENT_LENGTH=10 * 1024 * 1024,   # حد أقصى 10MB للطلب (حماية رفع الملفات)
)

# ---------- حماية CSRF (خفيفة، بدون مكتبات) ----------
_login_attempts = {}   # ip -> (count, first_ts)

@app.before_request
def _csrf_protect():
    if request.method in ("POST", "PUT", "PATCH", "DELETE"):
        token = session.get("_csrf")
        sent = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token")
        if not token or not sent or not _secrets.compare_digest(str(token), str(sent)):
            abort(400, "CSRF token invalid")

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
    return session.get("role", "user")

def is_platform_admin():
    return current_role() == "admin"

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
            "tmpl_label": lambda key: i18n.t({"flow":"tmpl_flow","store":"tmpl_store","booking":"tmpl_booking","customer_service":"tmpl_cs"}.get(key,"tmpl_flow"), lang),
            "tmpl_icon": lambda key: {"flow":"flow","store":"store","booking":"calendar","customer_service":"phone"}.get(key,"bot"),
            "role": session.get("role","user"),
            "fmt_date": lambda ts: (_dt.datetime.fromtimestamp(int(ts)).strftime("%Y-%m-%d") if ts else "—"),
            "days_left": lambda ts: (max(0, int((int(ts) - _time.time()) // 86400)) if ts else 0)}

@app.route("/lang/<code>")
def set_lang(code):
    if code in i18n.LANGS:
        session["lang"] = code
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
            notify_admins(f"🆕 تسجيل مستخدم جديد / New user: {u} (#{user_id})")
            return redirect(url_for("dashboard"))
    return render_template("register.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        if _rate_limited(request.remote_addr or "?"):
            flash("محاولات كثيرة. انتظر قليلاً." if session.get("lang")!="en" else "Too many attempts. Please wait.", "error")
            return render_template("login.html")
        u = request.form.get("username", "").strip()
        p = request.form.get("password", "")
        row = db.get_user_by_name(u)
        if row and row.get("is_blocked"):
            flash("تم حظر هذا الحساب." if session.get("lang")!="en" else "This account is blocked.", "error")
            return render_template("login.html")
        if row and auth.verify_password(p, row["pw_hash"]):
            session["uid"] = row["id"]; session["uname"] = u; session["role"] = row.get("role","user")
            return redirect(url_for("dashboard"))
        flash("بيانات دخول غير صحيحة.", "error")
    return render_template("login.html")

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
    return render_template("dashboard.html", bots=bots, total=total)

def _owned(bot_id):
    b = db.get_bot(bot_id, uid())
    if not b: abort(404)
    return b

@app.route("/bot/create", methods=["POST"])
@login_required
def bot_create():
    name = request.form.get("name", "").strip()
    token = request.form.get("token", "").strip()
    template = request.form.get("template", "")
    if not (name and token and template in T.TEMPLATES):
        flash("أكمل كل الحقول.", "error"); return redirect(url_for("dashboard"))
    info = tg.validate_token(token)
    if not info["ok"]:
        flash(f"❌ التوكن غير صالح: {info['error']}", "error")
        return redirect(url_for("dashboard"))
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
           "bot_username": info.get("username"), "bot_name": info.get("name"),
           "pending_owner_code": None}
    try:
        db.create_bot(uid(), name, token, template, cfg)
        notify_admins(f"🤖 بوت جديد / New bot: «{name}» (@{info.get('username')}) — {session.get('uname')}")
        flash(f"تم إنشاء البوت @{info.get('username')} 🎉 اضبط إعداداته ثم شغّله.", "ok")
    except Exception as e:
        flash(f"خطأ: {e} (قد يكون التوكن مستخدماً بالفعل).", "error")
    return redirect(url_for("dashboard"))

@app.route("/bot/<int:bot_id>")
@login_required
def bot_detail(bot_id):
    b = _owned(bot_id)
    b["config"] = json.loads(b["config_json"] or "{}")
    b["running"] = manager.is_running(bot_id)
    b["stats"] = db.stats_summary(bot_id)
    leads = db.list_leads(bot_id) if b["template"] in ("flow", "customer_service") else []
    orders = db.list_orders(bot_id) if b["template"] == "store" else []
    bookings = db.list_bookings(bot_id) if b["template"] == "booking" else []
    return render_template("bot_detail.html", bot=b, leads=leads, orders=orders, bookings=bookings)

@app.route("/bot/<int:bot_id>/config", methods=["POST"])
@login_required
def bot_config(bot_id):
    b = _owned(bot_id); cfg = json.loads(b["config_json"] or "{}")
    for k in ("business_name", "owner_chat_id", "welcome", "thanks", "welcome_image"):
        cfg[k] = request.form.get(k, cfg.get(k, "")).strip()
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
    db.update_bot_config(bot_id, cfg)
    if manager.is_running(bot_id): manager.restart_bot(bot_id)
    flash("تم حفظ الإعدادات ✅", "ok")
    return redirect(url_for("bot_detail", bot_id=bot_id))

# ---------- باني الفلو No-Code ----------
@app.route("/bot/<int:bot_id>/flow", methods=["GET", "POST"])
@login_required
def flow_builder(bot_id):
    b = _owned(bot_id); cfg = json.loads(b["config_json"] or "{}")
    if b["template"] not in ("flow", "customer_service"):
        flash("باني الفلو متاح لبوتات «باني المحادثات» و«خدمة العملاء».", "error")
        return redirect(url_for("bot_detail", bot_id=bot_id))
    if request.method == "POST":
        flow = {"start_message": request.form.get("start_message", "").strip(),
                "end_message": request.form.get("end_message", "").strip(), "steps": []}
        types = request.form.getlist("s_type")
        prompts = request.form.getlist("s_prompt")
        vars_ = request.form.getlist("s_var")
        opts = request.form.getlist("s_options")
        for i, t in enumerate(types):
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
    return render_template("flow_builder.html", bot=b, flow=flow)

# ---------- تشغيل / إيقاف / حذف ----------
@app.route("/bot/<int:bot_id>/<action>")
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
    return render_template("analytics.html", bot=b)

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
    subs = len(db.list_bot_user_ids(bot_id))
    if request.method == "POST":
        text = request.form.get("text", "").strip()
        if not text:
            flash("اكتب نص الرسالة.", "error")
        else:
            sent, failed = manager.broadcast(bot_id, text)
            flash(f"📢 تم الإرسال إلى {sent} مشترك (فشل {failed}).", "ok")
        return redirect(url_for("broadcast", bot_id=bot_id))
    return render_template("broadcast.html", bot=b, subs=subs)

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
    return render_template("settings.html",
        ai_provider=db.get_platform("ai_provider", "gemini"),
        ai_key=db.get_platform("ai_key", ""))

@app.route("/bot/<int:bot_id>/ai-setup", methods=["POST"])
@login_required
def ai_setup(bot_id):
    b = _owned(bot_id); cfg = json.loads(b["config_json"] or "{}")
    desc = (request.get_json(silent=True) or {}).get("description", "").strip()
    if not desc:
        return jsonify({"ok": False, "error": "اكتب وصف نشاطك أولاً."})
    key = db.get_platform("ai_key", "")
    provider = db.get_platform("ai_provider", "gemini")
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
    return render_template("pricing.html", plans=plans, sub=sub)

@app.route("/subscribe/<plan_id>", methods=["GET"])
@login_required
def subscribe(plan_id):
    if plan_id not in plans.PLANS or plan_id == "free":
        return redirect(url_for("pricing"))
    p = plans.plan(plan_id)
    plat = db.all_platform()
    return render_template("subscribe.html", plan_id=plan_id, plan=p, plat=plat)

@app.route("/subscribe/<plan_id>", methods=["POST"])
@login_required
def subscribe_pay(plan_id):
    if plan_id not in plans.PLANS or plan_id == "free":
        return redirect(url_for("pricing"))
    p = plans.plan(plan_id)
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
    # الفحص الآلي
    img_hash = pay.file_sha256(fpath)
    dup = db.img_hash_seen(img_hash)
    refs = [db.get_platform("vodafone_number",""), db.get_platform("instapay_handle",""),
            db.get_platform("bank_iban",""), db.get_platform("bank_account","")]
    ac = pay.auto_check(fpath, p["price"], [r for r in refs if r], duplicate=dup)
    pid = db.create_payment(uid(), plan_id, method, p["price"], ref, fname, img_hash,
                            json.dumps(ac, ensure_ascii=False))
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
        notify_admins(f"💳 طلب دفع جديد #{pid} / New payment — {session.get('uname')} — {p['price']} EGP ({plan_id}). راجعه من لوحة الأدمن.")
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
    return render_template("billing.html", sub=sub, pays=pays, plans=plans)

@app.route("/admin/platform", methods=["GET", "POST"])
@login_required
def admin_platform():
    if not is_platform_admin():
        abort(403)
    if request.method == "POST":
        for k in ("vodafone_number","instapay_handle","instapay_link",
                  "bank_holder","bank_name","bank_account","bank_iban",
                  "platform_bot_token","admin_chat_id"):
            db.set_platform(k, request.form.get(k, "").strip())
        tok = db.get_platform("platform_bot_token",""); adm = db.get_platform("admin_chat_id","")
        if tok and adm:
            ok, msg = manager.start_platform_bot(tok)
            flash(("تم الحفظ. " if session.get("lang")!="en" else "Saved. ")+msg, "ok" if ok else "error")
        else:
            flash("تم الحفظ." if session.get("lang")!="en" else "Saved.", "ok")
        return redirect(url_for("admin_platform"))
    return render_template("admin_platform.html", plat=db.all_platform(),
                           platform_running=manager.platform_running())

# ---------- لوحة تحكم الأدمن ----------
@app.route("/admin")
@require_roles("admin", "support")
def admin_home():
    return render_template("admin_overview.html", stats=db.platform_stats(), plans=plans)

@app.route("/api/admin/stats")
@require_roles("admin", "support")
def api_admin_stats():
    return jsonify({"summary": db.platform_stats(), "daily": db.revenue_daily(14)})

@app.route("/admin/users")
@require_roles("admin", "support")
def admin_users():
    return render_template("admin_users.html", users=db.list_all_users(), plans=plans)

@app.route("/admin/users/<int:user_id>/role", methods=["POST"])
@require_roles("admin")
def admin_user_role(user_id):
    db.set_user_role(user_id, request.form.get("role", "user"))
    flash("تم تحديث الدور." if session.get("lang")!="en" else "Role updated.", "ok")
    return redirect(url_for("admin_users"))

@app.route("/admin/users/<int:user_id>/block/<int:val>")
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
    return render_template("admin_payments.html", pays=pays, plans=plans)

@app.route("/admin/payments/<int:pid>/<decision>")
@require_roles("admin")
def admin_payment_decide(pid, decision):
    status = "approved" if decision == "approve" else "rejected"
    row = db.finalize_payment(pid, status)
    if row:
        u = db.get_user(row["user_id"])
        notify_admins(f"{'✅ موافقة' if status=='approved' else '❌ رفض'} دفعة #{pid} — {u['username'] if u else ''} (من الويب)")
        flash(("تمت الموافقة والتفعيل." if status=="approved" else "تم الرفض.") if session.get("lang")!="en"
              else ("Approved & activated." if status=="approved" else "Rejected."), "ok")
    else:
        flash("سبق البتّ في هذا الطلب." if session.get("lang")!="en" else "Already decided.", "error")
    return redirect(url_for("admin_payments"))

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
    return render_template("account.html", me=me)

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

@app.route("/landing")
def landing():
    return render_template("landing.html")

UPLOAD_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)


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
    db.set_platform("seeded", "1")

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
    db.init_db(); seed_platform_defaults(); seed_default_admin(); _migrate_ai_key()
    manager.start(); manager.resume_active_bots()
    tok = db.get_platform("platform_bot_token", "")
    if tok and db.get_platform("admin_chat_id", ""):
        manager.start_platform_bot(tok)

if __name__ == "__main__":
    bootstrap()
    app.run(host="127.0.0.1", port=5000, debug=False)
