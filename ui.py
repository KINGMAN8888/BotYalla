"""هيكل اللوحة الذكي: التنقّل المجمَّع · مكتبة الأدوات والاختصارات لكل دور · تفضيلات المستخدم · التعلّم من الاستخدام.

مصدر واحد للتنقّل (`NAV`): كل صفحة بمفتاحها ومجموعتها الأم وشرط ظهورها. `build_nav` يرجّع المجموعات
المرئية لهذا المستخدم فقط (الشرط يُفحص في الخادم — الواجهة لا تقرّر الصلاحيات).

التفضيلات (`settings: ui_prefs`) تُنظَّف دائماً مقابل الكتالوج: مفتاح غير معروف أو غير متاح لهذا المستخدم
يسقط بصمت — لا يُحقن رابط ولا أداة من المتصفح. الاستخدام (`settings: ui_usage`) عدّاد لكل صفحة يغذّي
«الأكثر استخداماً».
"""
import json
import time

import database as db

# (المفتاح/العرض, نقطة Flask, الأيقونة, (عربي, إنجليزي), المجموعة, الشرط)
# الشرط: all · crm (باقة الشركات) · team_admin (مالك/مدير الفريق) · staff (أدمن أو دعم) · admin (الأدمن وحده)
NAV = [
    ("home", "home_page", "grid", ("الرئيسية", "Home"), "home", "all"),     # «home» = صفحة الهبوط العامة
    ("shared_inbox", "shared_inbox", "inbox", ("الصندوق المشترك", "Team inbox"), "conversations", "crm"),
    ("contacts", "contacts_page", "users", ("جهات الاتصال", "Contacts"), "conversations", "crm"),
    ("dashboard", "dashboard", "bot", ("بوتاتي", "My bots"), "automation", "all"),
    ("sequences", "sequences_page", "clock", ("التسلسلات", "Sequences"), "automation", "crm"),
    ("tpl_studio", "templates_studio", "mail", ("القوالب", "Templates"), "automation", "crm"),
    ("broadcasts", "broadcasts_page", "megaphone", ("البث", "Broadcasts"), "marketing", "crm"),
    ("growth", "growth_page", "rocket", ("النمو والإعلانات", "Growth & ads"), "marketing", "crm"),
    ("chat_payments", "payments_page", "card", ("المدفوعات", "Payments"), "commerce", "crm"),
    ("integrations", "integrations_page", "link", ("التكاملات", "Integrations"), "commerce", "crm"),
    ("media", "media_page", "image", ("مكتبة الوسائط", "Media library"), "library", "all"),
    ("team", "team_page", "users", ("الفريق", "Team"), "account", "team_admin"),
    ("billing", "billing", "card", ("اشتراكي", "My subscription"), "account", "all"),
    ("wallet", "wallet_page", "wallet", ("الرصيد", "Wallet"), "account", "all"),
    ("pricing", "pricing", "tag", ("الباقات", "Plans"), "account", "all"),
    ("affiliate", "affiliate", "crown", ("برنامج الشركاء", "Partner program"), "account", "all"),
    ("support", "support", "help", ("الدعم والشكاوى", "Support"), "help", "all"),
    ("request_bot", "request_bot", "sparkles", ("بوت مخصّص لك بالكامل", "Done-for-you bot"), "help", "all"),
    # ---- الإدارة ----
    ("admin_overview", "admin_home", "shield", ("لوحة الأدمن", "Admin overview"), "adm_overview", "staff"),
    ("admin_analytics", "admin_analytics", "chart", ("إحصائيات الزوار", "Visitor analytics"), "adm_overview", "admin"),
    ("admin_report", "admin_report", "chart", ("التقرير الأسبوعي", "Weekly report"), "adm_overview", "admin"),
    ("admin_convo", "admin_conversations", "chat", ("تحليل المحادثات", "Conversation insights"), "adm_overview", "admin"),
    ("admin_users", "admin_users", "users", ("إدارة المستخدمين", "Users"), "adm_customers", "staff"),
    ("admin_requests", "admin_requests", "inbox", ("طلبات مخصّصة", "Custom requests"), "adm_customers", "staff"),
    ("admin_affiliates", "admin_affiliates", "users", ("الأفيليت", "Affiliates"), "adm_customers", "admin"),
    ("admin_payments", "admin_payments", "wallet", ("إدارة المدفوعات", "Payments review"), "adm_finance", "staff"),
    ("admin_pricing", "admin_pricing", "tag", ("الأسعار والخصومات", "Pricing"), "adm_finance", "admin"),
    ("admin_promos", "admin_promos", "bolt", ("أكواد الخصم", "Promo codes"), "adm_finance", "admin"),
    ("admin_tickets", "admin_tickets", "chat", ("تذاكر الدعم", "Support tickets"), "adm_support", "staff"),
    ("settings", "settings", "sparkles", ("الذكاء الاصطناعي", "AI settings"), "adm_platform", "admin"),
    ("admin_meta", "admin_meta", "chat", ("Meta — ماسنجر وإنستجرام", "Meta — Messenger & Instagram"), "adm_platform", "admin"),
    ("admin_emails", "admin_emails", "mail", ("حملات البريد", "Email campaigns"), "adm_platform", "admin"),
    ("admin_growth", "admin_growth", "megaphone", ("نمو المنصة", "Platform growth"), "adm_platform", "admin"),
    ("admin_platform", "admin_platform", "settings", ("إعدادات المنصة", "Platform settings"), "adm_platform", "admin"),
]
GROUPS = [
    ("home", "grid", ("", ""), False),
    ("conversations", "inbox", ("المحادثات والعملاء", "Conversations & customers"), False),
    ("automation", "bot", ("البوتات والأتمتة", "Bots & automation"), False),
    ("marketing", "megaphone", ("التسويق والنمو", "Marketing & growth"), False),
    ("commerce", "card", ("المبيعات والربط", "Sales & integrations"), False),
    ("library", "image", ("المحتوى", "Content"), False),
    ("account", "wallet", ("الحساب والفوترة", "Account & billing"), False),
    ("help", "help", ("المساعدة", "Help"), False),
    ("adm_overview", "shield", ("نظرة عامة", "Overview"), True),
    ("adm_customers", "users", ("العملاء", "Customers"), True),
    ("adm_finance", "wallet", ("المالية", "Finance"), True),
    ("adm_support", "chat", ("الدعم", "Support"), True),
    ("adm_platform", "settings", ("المنصة", "Platform"), True),
]

# اختصارات «إجراء سريع»: (مفتاح, أيقونة, (عربي, إنجليزي), نقطة Flask, معاملات, الشرط)
ACTIONS = [
    ("new_bot", "plus", ("بوت جديد", "New bot"), "dashboard", {}, "all"),
    ("open_inbox", "inbox", ("الصندوق المشترك", "Open inbox"), "shared_inbox", {}, "crm"),
    ("add_contact", "users", ("جهات الاتصال", "Contacts"), "contacts_page", {}, "crm"),
    ("new_broadcast", "megaphone", ("حملة بث", "New broadcast"), "broadcasts_page", {}, "crm"),
    ("new_template", "mail", ("قالب واتساب", "New template"), "templates_studio", {}, "crm"),
    ("request_payment", "card", ("المدفوعات", "Payments"), "payments_page", {}, "crm"),
    ("tracking_link", "link", ("رابط تتبّع", "Tracking link"), "growth_page", {}, "crm"),
    ("comment_rules", "chat", ("أتمتة التعليقات", "Comment automation"), "growth_page", {"tab": "comments"}, "crm"),
    ("website_widget", "globe", ("ودجت الموقع", "Website widget"), "growth_page", {"tab": "widget"}, "crm"),
    ("connect_store", "link", ("ربط متجر أو نظام", "Connect a store"), "integrations_page", {}, "crm"),
    ("sequences", "clock", ("تسلسل متابعة", "Follow-up sequence"), "sequences_page", {}, "crm"),
    ("media", "image", ("رفع وسائط", "Upload media"), "media_page", {}, "all"),
    ("wallet", "wallet", ("شحن الرصيد", "Top up wallet"), "wallet_page", {}, "all"),
    ("upgrade", "crown", ("ترقية الباقة", "Upgrade plan"), "pricing", {}, "all"),
    ("support", "help", ("تذكرة دعم", "Support ticket"), "support", {}, "all"),
    ("adm_payments", "wallet", ("مراجعة المدفوعات", "Review payments"), "admin_payments", {}, "staff"),
    ("adm_tickets", "chat", ("تذاكر الدعم", "Support tickets"), "admin_tickets", {}, "staff"),
    ("adm_users", "users", ("المستخدمون", "Users"), "admin_users", {}, "staff"),
    ("adm_requests", "inbox", ("الطلبات المخصّصة", "Custom requests"), "admin_requests", {}, "staff"),
    ("adm_report", "chart", ("التقرير الأسبوعي", "Weekly report"), "admin_report", {}, "admin"),
    ("adm_platform", "settings", ("إعدادات المنصة", "Platform settings"), "admin_platform", {}, "admin"),
    ("adm_meta", "chat", ("Meta", "Meta"), "admin_meta", {}, "admin"),
]
DEFAULT_ACTIONS = {
    "owner": ["open_inbox", "new_broadcast", "request_payment", "new_template", "tracking_link", "connect_store"],
    "basic": ["new_bot", "media", "upgrade", "support"],
    "member": ["open_inbox", "add_contact", "request_payment", "support"],
    "admin": ["adm_payments", "adm_tickets", "adm_users", "adm_requests", "adm_report", "adm_platform"],
    "support": ["adm_tickets", "adm_payments", "adm_users", "adm_requests"],
}
# أدوات الرئيسية لكل دور — بالترتيب الافتراضي
WIDGETS = {
    "owner": ["insights", "kpis", "attention", "actions", "frequent", "inbox", "activity", "bots"],
    "basic": ["insights", "kpis", "journey", "actions", "frequent", "bots"],
    "member": ["member_kpis", "inbox", "actions", "frequent"],
    "admin": ["insights", "admin_kpis", "admin_revenue", "admin_queues", "actions", "support_kpis", "frequent", "admin_chart", "signups"],
    "support": ["insights", "support_kpis", "support_queues", "actions", "frequent", "signups"],
}
MAX_PINS, MAX_ACTIONS = 12, 12
SCALES = (90, 100, 110, 125)


def _allowed(cond, ctx):
    return (cond == "all" or (cond == "crm" and ctx["crm"]) or (cond == "team_admin" and ctx["team_admin"])
            or (cond == "staff" and ctx["role"] in ("admin", "support")) or (cond == "admin" and ctx["role"] == "admin"))


def persona(ctx):
    """من هو هذا المستخدم للوحة: admin · support · member (موظف في فريق) · owner (باقة الشركات) · basic."""
    if ctx["role"] == "admin":
        return "admin"
    if ctx["role"] == "support":
        return "support"
    if ctx["member"]:
        return "member"
    return "owner" if ctx["crm"] else "basic"


def build_nav(ctx, lang, url_for):
    """⇒ (المجموعات المرئية, القائمة المسطّحة للمستخدم, القائمة المسطّحة للإدارة) — المسطّحتان للتوافق."""
    ar = lang != "en"
    items = {}
    for k, ep, icon, label, group, cond in NAV:
        if not _allowed(cond, ctx):
            continue
        try:
            url = url_for(ep)
        except Exception:                       # نقطة غير مسجّلة (بيئة جزئية) — لا تُسقط الصفحة
            continue
        items.setdefault(group, []).append({"k": k, "u": url, "i": icon, "l": label[0 if ar else 1]})
    groups = [{"k": g, "i": icon, "l": label[0 if ar else 1], "admin": adm, "items": items[g]}
              for g, icon, label, adm in GROUPS if items.get(g)]
    flat = [it for g in groups if not g["admin"] for it in g["items"]]
    admin_flat = [it for g in groups if g["admin"] for it in g["items"]]
    return groups, flat, admin_flat


def actions(ctx, lang, url_for):
    ar = lang != "en"
    out = []
    for k, icon, label, ep, args, cond in ACTIONS:
        if _allowed(cond, ctx):
            try:
                out.append({"k": k, "i": icon, "l": label[0 if ar else 1], "u": url_for(ep, **args)})
            except Exception:
                continue
    return out


# ─────────────────────────── التفضيلات ───────────────────────────
def prefs(user_id):
    try:
        return json.loads(db.get_setting(user_id, "ui_prefs") or "{}")
    except ValueError:
        return {}


def clean_prefs(raw, nav_keys, action_keys, widget_keys, group_keys):
    """ما يرسله المتصفح ⇒ تفضيلات بمفاتيح معروفة ومتاحة لهذا المستخدم فقط."""
    raw = raw if isinstance(raw, dict) else {}

    def keys(v, allowed, n):
        out = []
        for x in v if isinstance(v, list) else []:
            if isinstance(x, str) and x in allowed and x not in out:
                out.append(x)
        return out[:n]
    return {"pins": keys(raw.get("pins"), nav_keys, MAX_PINS),
            "collapsed": keys(raw.get("collapsed"), group_keys, 20),
            "compact": bool(raw.get("compact")),
            "widgets": keys(raw.get("widgets"), widget_keys, 20),
            "hidden": keys(raw.get("hidden"), widget_keys, 20),
            "actions": keys(raw.get("actions"), action_keys, MAX_ACTIONS),
            "tour": bool(raw.get("tour")),                                   # جولة أول استخدام انتهت
            "scale": raw.get("scale") if raw.get("scale") in SCALES else 100}  # حجم العرض %


def save_prefs(user_id, p):
    db.set_setting(user_id, "ui_prefs", json.dumps(p))


# ─────────────────────────── التعلّم من الاستخدام ───────────────────────────
NAV_KEYS = {k for k, *_ in NAV}


def track(user_id, view, now=None):
    """زيارة صفحة من التنقّل ⇒ عدّادها. صفحات خارج التنقّل (بوت بعينه · تسجيل) لا تُحتسب."""
    if not user_id or view not in NAV_KEYS or view == "home":
        return
    try:
        u = json.loads(db.get_setting(user_id, "ui_usage") or "{}")
    except ValueError:
        u = {}
    c, _ = u.get(view) or [0, 0]
    u[view] = [min(int(c) + 1, 10 ** 6), int(now or time.time())]
    db.set_setting(user_id, "ui_usage", json.dumps(u))


def frequent(user_id, visible, n=6, now=None):
    """الأكثر استخداماً: العدد مخفّفاً بالقِدم (نصف القيمة كل أسبوعين) — ما تستعمله الآن يعلو."""
    try:
        u = json.loads(db.get_setting(user_id, "ui_usage") or "{}")
    except ValueError:
        return []
    t = now or time.time()
    score = {k: c * 0.5 ** ((t - last) / (14 * 86400)) for k, (c, last) in u.items() if k in visible}
    return [k for k, s in sorted(score.items(), key=lambda x: -x[1]) if s >= 0.5][:n]
