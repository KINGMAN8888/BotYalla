"""التقرير الأسبوعي — كل ما حدث في المنصة في فترة، ومقارنته بسابقتها، وما يُتوقَّع.

مصادره ثلاثة، ولا رابع:
1. **قاعدة البيانات** عبر دوال `database.report_*` (لا SQL هنا — AGENTS §1).
2. **سجل الخادم** عبر `log_scan` (محجوب الأسرار قبل أن يصل إلى هنا).
3. **المحادثات** عبر `conv_insights` (تحليل نصّي بقواعد صريحة، بلا مزوّد خارجي).

ثلاث قواعد تحكم هذا الملف:

- **كل رقم يُقارَن بسابقه.** رقم وحده لا يعني شيئاً: «12 تسجيلاً» ليست خبراً حتى
  تُقرأ بجانب 20 الأسبوع الماضي. لذلك تُبنى نافذتان متساويتان دائماً.
- **التنبؤ يُعلَن تنبؤاً.** `forecast` خطُّ اتجاه (انحدار خطّي على السلسلة اليومية)
  لا وعد، ومعه `confidence` وعدد الأيام التي بُني عليها. حين لا تكفي البيانات
  يقول ذلك صراحةً بدل أن يخترع رقماً.
- **كل ملاحظة معها إجراء.** `findings` لا تصف الحال فقط؛ كل سطر فيه ما يُفعل،
  لأن تقريراً لا يُفعل به شيء ورقٌ جميل.
"""
import datetime
import time

import database as db
import plans

DEFAULT_DAYS = 7
MAX_DAYS = 90
TREND_DAYS = 28                  # سلسلة الاتجاه: أربعة أسابيع تكفي لموسمية الأسبوع
CAPACITY_FALLBACK = 120          # نفس احتياطي bot_manager — لا استيراد متبادل


# ---------------------------------------------------------------- الفترة
def period(days=DEFAULT_DAYS, end=None):
    """`(a, b)` بالثواني: `days` يوماً تقويمياً تنتهي الآن.

    البداية منتصف ليل اليوم الأول **بالتوقيت المحلي** — لا «قبل 604800 ثانية» —
    حتى يطابق الرسم اليومي ما يراه صاحب المنصة في تقويمه."""
    days = max(1, min(int(days or DEFAULT_DAYS), MAX_DAYS))
    # +1 لأن النافذة نصف مفتوحة `[a, b)`: بدونها تسقط كل حركة وقعت في الثانية
    # الجارية — وهو ما يجعل أي اختبار يزرع بياناته ثم يبني التقرير فوراً يرى صفراً.
    b = int(end or time.time()) + 1
    start_day = datetime.date.fromtimestamp(b) - datetime.timedelta(days=days - 1)
    a = int(time.mktime(start_day.timetuple()))
    return a, b


def label(a, b):
    f = datetime.date.fromtimestamp(a).isoformat()
    t = datetime.date.fromtimestamp(max(a, b - 1)).isoformat()
    return f"{f} → {t}"


# ---------------------------------------------------------------- المقارنة
_COMPARE = ("signups", "bots_new", "bots_new_active", "msgs_in", "msgs_out", "customers_new",
            "customers_active", "leads", "orders", "orders_value", "revenue", "pay_sent",
            "pay_approved", "visitors", "tickets_new", "refusals", "emails_sent", "emails_failed",
            "bots_never_started", "bots_started_silent", "signups_no_bot")


def _change(now, prev):
    """نسبة التغيّر. من صفر إلى رقم ليست «+∞» بل `new` — والمقارنة تبقى مفهومة."""
    if prev == now:
        return 0.0
    if not prev:
        return None
    return round((now - prev) * 100.0 / prev, 1)


def compare(now, prev):
    return {k: {"now": now.get(k, 0), "prev": prev.get(k, 0),
                "change": _change(now.get(k, 0) or 0, prev.get(k, 0) or 0)}
            for k in _COMPARE}


# ---------------------------------------------------------------- التنبؤ
def trend(values):
    """انحدار خطّي بسيط على سلسلة يومية ⇒ `{slope, mean, next_day, confidence}`.

    `confidence` من نسبة التباين المفسَّر (R²) وعدد النقاط: بيانات قليلة أو
    متذبذبة تُعلَن «منخفضة» بدل أن يُعرض الخط كأنه حقيقة."""
    xs = [float(v or 0) for v in values]
    n = len(xs)
    if n < 3 or not any(xs):
        return {"slope": 0.0, "mean": round(sum(xs) / n, 2) if n else 0.0,
                "next_day": round(sum(xs) / n, 2) if n else 0.0, "confidence": "none", "points": n}
    mx = (n - 1) / 2.0
    my = sum(xs) / n
    sxy = sum((i - mx) * (y - my) for i, y in enumerate(xs))
    sxx = sum((i - mx) ** 2 for i in range(n))
    slope = sxy / sxx if sxx else 0.0
    inter = my - slope * mx
    ss_tot = sum((y - my) ** 2 for y in xs)
    ss_res = sum((y - (inter + slope * i)) ** 2 for i, y in enumerate(xs))
    r2 = 1 - (ss_res / ss_tot) if ss_tot else 0.0
    conf = "high" if (r2 >= 0.5 and n >= 14) else ("medium" if (r2 >= 0.2 and n >= 7) else "low")
    return {"slope": round(slope, 3), "mean": round(my, 2),
            "next_day": round(max(0.0, inter + slope * n), 2), "confidence": conf,
            "r2": round(max(0.0, r2), 2), "points": n}


def forecast(series, days, keys=("signups", "msgs_in", "orders", "revenue", "visitors")):
    """توقّع الفترة القادمة لكل مقياس: مجموع الخط المتوقّع على `days` يوماً."""
    out = {}
    for k in keys:
        vals = [row.get(k, 0) for row in series]
        t = trend(vals)
        n = len(vals)
        total = 0.0
        if t["confidence"] == "none":
            total = t["mean"] * days
        else:
            inter = t["mean"] - t["slope"] * ((n - 1) / 2.0)
            total = sum(max(0.0, inter + t["slope"] * (n + i)) for i in range(days))
        last = sum(vals[-days:]) if vals else 0
        out[k] = {"expected": round(total, 2), "last_period": round(float(last), 2),
                  "per_day": t["next_day"], "confidence": t["confidence"],
                  "slope": t["slope"], "points": t["points"]}
    return out


def _capacity():
    try:
        v = int(str(db.get_platform("bot_capacity", "") or "").strip() or 0)
    except (TypeError, ValueError):
        v = 0
    return v if v > 0 else CAPACITY_FALLBACK


def _renewal_value(expiring):
    """قيمة التجديدات المنتظرة بسعر القائمة — تقدير أعلى (بلا أكواد خصم)."""
    total = 0.0
    for r in expiring:
        p = plans.plan(r.get("plan") or "free")
        total += float(p.get("price") or 0)
    return round(total, 2)


# ---------------------------------------------------------------- الملاحظات
def _txt(lang, ar, en):
    return en if lang == "en" else ar


def findings(rep, lang="ar"):
    """ملاحظات مرتّبة بالأهمية: `risk` ← `warn` ← `good` ← `info`. لكل واحدة إجراء."""
    T = lambda ar, en: _txt(lang, ar, en)
    now, delta = rep["now"], rep["delta"]
    logs, conv = rep.get("logs") or {}, rep.get("conv") or {}
    out = []

    def add(level, key, title, detail, action, value=None):
        out.append({"level": level, "key": key, "title": title, "detail": detail,
                    "action": action, "value": value})

    if now["pay_pending_late"]:
        add("risk", "pay_pending_late",
            T(f"{now['pay_pending_late']} دفعة تنتظر قرارك من أكثر من 24 ساعة",
              f"{now['pay_pending_late']} payments have been waiting over 24 hours"),
            T("العميل دفع فعلاً وينتظر التفعيل — كل ساعة تأخير هنا شكوى محتملة.",
              "These customers already paid and are waiting to be activated."),
            T("افتح «إدارة المدفوعات» وابتّها الآن.", "Open Payments and decide them now."),
            now["pay_pending_late"])
    if now["tickets_unanswered"]:
        add("risk", "tickets_unanswered",
            T(f"{now['tickets_unanswered']} تذكرة دعم بلا ردّ واحد",
              f"{now['tickets_unanswered']} support tickets have no reply at all"),
            T("تذكرة مفتوحة بلا ردّ أسوأ من تذكرة مرفوضة.",
              "An open ticket with no reply is worse than a rejected one."),
            T("ردّ عليها من «تذاكر الدعم» أو بالردّ على تنبيه تليجرام.",
              "Reply from Support tickets, or by replying to the Telegram alert."),
            now["tickets_unanswered"])
    if now["bots_never_started"]:
        add("warn", "bots_never_started",
            T(f"{now['bots_never_started']} بوت أُنشئ في الفترة ولم يُشغَّل",
              f"{now['bots_never_started']} bots were created but never started"),
            T("توقّف أصحابها عند الإعداد — أقرب نقطة لكسب عميل بلا تسويق.",
              "Their owners stalled during setup — the cheapest win available."),
            T("راسلهم برسالة واحدة تسأل أين توقّفوا، أو فعّل «فريقنا يجهّزه لك».",
              "Message them once asking where they stopped, or offer the done-for-you setup."),
            now["bots_never_started"])
    if now["bots_started_silent"]:
        add("warn", "bots_started_silent",
            T(f"{now['bots_started_silent']} بوت شغّال لم تصله رسالة عميل واحدة",
              f"{now['bots_started_silent']} live bots never received a single customer message"),
            T("المشكلة هنا ليست المنتج بل الوصول: البوت جاهز ولا أحد يعرفه.",
              "This is a distribution problem, not a product one: the bot works, nobody uses it."),
            T("أرسل لأصحابها رابط البوت وQR وملصق A4 وطريقة نشره.",
              "Send their bot link, QR and A4 poster, and how to share it."),
            now["bots_started_silent"])
    if now["signups_stuck_verify"]:
        add("warn", "verify_stuck",
            T(f"{now['signups_stuck_verify']} حساباً جديداً لم يؤكّد بريده",
              f"{now['signups_stuck_verify']} new accounts never confirmed their email"),
            T("الحساب محجوب حتى التأكيد — فالمسجّل لم يدخل المنصة أصلاً.",
              "The account is gated until confirmation, so they never got in."),
            T("افحص وصول رسائل التأكيد (SPF/DKIM)، وأكّد يدوياً من «المستخدمون» عند الحاجة.",
              "Check deliverability (SPF/DKIM), and verify manually from Users when needed."),
            now["signups_stuck_verify"])
    if now["refusals"]:
        add("warn", "refusals",
            T(f"{now['refusals']} إيصالاً رُفض آلياً قبل الحفظ",
              f"{now['refusals']} receipts were auto-refused before saving"),
            T("لكل سبب معناه: «ليس إيصالاً» تعليمات غير واضحة، و«مستلم آخر» حساب دفع قديم.",
              "Each reason means something: “not a receipt” is unclear instructions, "
              "“wrong recipient” is a stale payment account."),
            T("راجع أسباب الرفض في التقرير وصحّح صفحة الدفع أو بيانات الحساب.",
              "Review the refusal reasons below and fix the payment page or account details."),
            now["refusals"])
    if now["emails_sent"] and now["emails_failed"] * 10 > now["emails_sent"]:
        add("risk", "email_failures",
            T(f"فشل {now['emails_failed']} رسالة بريد من {now['emails_sent']}",
              f"{now['emails_failed']} of {now['emails_sent']} emails failed"),
            T("نسبة فشل فوق 10% تعني مشكلة في SMTP أو في سمعة النطاق لا في المحتوى.",
              "Over 10% failures points at SMTP or domain reputation, not content."),
            T("راجع سجل الخادم وإعدادات SMTP وسجلات SPF/DKIM/DMARC.",
              "Check the server log, SMTP settings and SPF/DKIM/DMARC records."),
            now["emails_failed"])
    ans = conv.get("answer_rate")
    if ans is not None and conv.get("in_count") and ans < 85:
        add("warn", "answer_rate",
            T(f"نسبة الرد على رسائل العملاء {ans}%",
              f"Customer message answer rate is {ans}%"),
            T(f"{conv.get('unanswered_total', 0)} سؤالاً لم يجد إجابة — وكلها مكتوبة في «أسئلة بلا إجابة».",
              f"{conv.get('unanswered_total', 0)} questions went unanswered — all listed below."),
            T("حوّل أكثرها تكراراً إلى ردود جاهزة أو خطوات في الفلو.",
              "Turn the most repeated ones into canned answers or flow steps."), ans)
    intents = {i["k"]: i for i in (conv.get("intents") or [])}
    lost = intents.get("confused")
    if lost and lost["pct"] >= 5:
        add("risk" if lost["pct"] >= 10 else "warn", "confused",
            T(f"{lost['pct']}% من رسائل العملاء تقول «مش فاهم» ({lost['v']} رسالة)",
              f"{lost['pct']}% of customer messages say “I don't understand” ({lost['v']})"),
            T("من لا يفهم لا يشترك ولا يشتري — هذه أعلى نقطة تسريب في المنصة كلها.",
              "People who don't understand never subscribe — this is the biggest leak there is."),
            T("افتح «تحليل المحادثات» واقرأ العبارات نفسها، ثم حوّل أكثرها تكراراً إلى "
              "ردّ جاهز أو خطوة في الفلو أو فيديو من دقيقة.",
              "Open Conversation insights, read the actual phrasing, and turn the most "
              "repeated ones into a canned answer, a flow step, or a one-minute video."),
            lost["pct"])
    money = intents.get("earn")
    if money and money["pct"] >= 5:
        add("warn", "earn_expectation",
            T(f"{money['pct']}% من الرسائل تسأل «هكسب منها إزاي؟»",
              f"{money['pct']}% of messages ask “how do I make money from this?”"),
            T("الزائر فهم أن المنصة فرصة دخل لا أداة لنشاطه — غالباً من نصّ إعلان أو "
              "منشور يَعِد بالربح. هؤلاء لا يتحوّلون إلى مشتركين ويستهلكون وقت الدعم.",
              "They read the platform as an income opportunity, not a tool for their business — "
              "usually because of ad copy. They rarely convert and they consume support time."),
            T("صحّح نصّ الإعلان ليقول «بوت لنشاطك»، أو حوّلهم لبرنامج الشركاء (الأفيليت) "
              "برسالة جاهزة بدل الشرح اليدوي كل مرة.",
              "Fix the ad copy to say “a bot for your business”, or route them to the affiliate "
              "programme with a canned reply instead of explaining by hand every time."),
            money["pct"])
    if conv.get("waiting_total"):
        add("warn", "waiting",
            T(f"{conv['waiting_total']} محادثة آخر رسالة فيها من العميل",
              f"{conv['waiting_total']} conversations end on the customer's message"),
            T("عميل كتب ولم يُردّ عليه — وهو ينتظر الآن.",
              "Someone wrote and got nothing back — they are waiting now."),
            T("افتح صندوق الوارد وردّ عليها، أو نبّه أصحاب البوتات.",
              "Open the inbox and reply, or alert those bot owners."),
            conv["waiting_total"])
    errs = logs.get("errors") or 0
    if errs:
        top = (logs.get("groups") or [{}])[0]
        add("risk" if errs > 50 else "warn", "errors",
            T(f"{errs} خطأ في سجل الخادم خلال الفترة",
              f"{errs} errors in the server log during the period"),
            (top.get("sample") or "")[:200],
            T("ابدأ بأكثرها تكراراً — عادةً عطل واحد يفسّر معظم السطور.",
              "Start with the most frequent group — one fault usually explains most lines."),
            errs)
    if logs.get("signals", {}).get("capacity_refused"):
        add("risk", "capacity",
            T("رُفض تشغيل بوت لبلوغ سقف الخادم", "A bot was refused: server at capacity"),
            T("البوتات كلها في عملية الويب نفسها، فالسقف حماية لكل العملاء لا حدّ اعتباطي.",
              "All bots share the web process — the cap protects everyone, it is not arbitrary."),
            T("أوقف بوتات غير مستخدمة أو ارفع السقف بعد زيادة موارد الخادم.",
              "Stop unused bots, or raise the cap after adding server resources."))
    cap = rep["capacity"]
    if cap["pct"] >= 80:
        add("warn", "capacity_near",
            T(f"البوتات العاملة {cap['running']} من {cap['capacity']} ({cap['pct']}%)",
              f"Running bots {cap['running']} of {cap['capacity']} ({cap['pct']}%)"),
            T(f"بمعدّل النمو الحالي يبلغ السقف خلال {cap['weeks_to_full']} أسبوعاً تقريباً."
              if cap.get("weeks_to_full") else "",
              f"At the current growth rate the cap is reached in about {cap['weeks_to_full']} weeks."
              if cap.get("weeks_to_full") else ""),
            T("خطّط لزيادة الموارد قبل أن تُرفض بوتات العملاء.",
              "Plan more resources before customer bots start being refused."), cap["pct"])
    if rep["expiring"]:
        add("warn", "expiring",
            T(f"{len(rep['expiring'])} اشتراكاً ينتهي خلال 7 أيام "
              f"(≈ {rep['renewal_value']} ج.م)",
              f"{len(rep['expiring'])} subscriptions expire within 7 days "
              f"(≈ {rep['renewal_value']} EGP)"),
            T("التذكير يصل آلياً قبل 3 أيام — لكن رسالة شخصية تضاعف التجديد.",
              "The automatic reminder goes out 3 days ahead — a personal message does better."),
            T("راسلهم قبل الانتهاء بيومين.", "Message them two days before they lapse."),
            len(rep["expiring"]))
    rev = delta["revenue"]
    if rev["now"] and (rev["change"] is None or rev["change"] >= 0):
        add("good", "revenue_up",
            T(f"إيراد الفترة {rev['now']} ج.م", f"Revenue this period: {rev['now']} EGP"),
            T(f"مقابل {rev['prev']} في الفترة السابقة.", f"Against {rev['prev']} last period."),
            T("كرّر ما نجح: راجع مصادر التسجيل أدناه.",
              "Repeat what worked — check the signup sources below."), rev["now"])
    elif rev["change"] is not None and rev["change"] < 0:
        add("warn", "revenue_down",
            T(f"الإيراد نزل {abs(rev['change'])}% عن الفترة السابقة",
              f"Revenue is down {abs(rev['change'])}% versus last period"),
            T(f"{rev['now']} مقابل {rev['prev']} ج.م.", f"{rev['now']} vs {rev['prev']} EGP."),
            T("افحص القمع: هل قلّ الزوار أم قلّ تحوّلهم؟",
              "Check the funnel: fewer visitors, or worse conversion?"), rev["change"])
    if not logs.get("available"):
        add("info", "no_logs",
            T("سجل الخادم غير متاح في هذه البيئة", "The server log is not available here"),
            T(f"المسار: {logs.get('dir', '')}", f"Path: {logs.get('dir', '')}"),
            T("على الخادم يُكتب السجل في logs/botyalla.log — التقرير يقرأه تلقائياً.",
              "On the server the log lives in logs/botyalla.log and is read automatically."))
    order = {"risk": 0, "warn": 1, "good": 2, "info": 3}
    out.sort(key=lambda f: order.get(f["level"], 9))
    return out


def summary(rep, lang="ar"):
    """خلاصة تُقرأ في عشر ثوانٍ — أول ما يظهر في الصفحة وفي البريد."""
    T = lambda ar, en: _txt(lang, ar, en)
    n, d = rep["now"], rep["delta"]

    def mv(key, ar, en):
        c = d[key]["change"]
        arrow = "" if c is None else (f" ({'+' if c > 0 else ''}{c}%)")
        return T(f"{ar}: {d[key]['now']}{arrow}", f"{en}: {d[key]['now']}{arrow}")

    lines = [
        mv("signups", "تسجيلات جديدة", "New signups"),
        mv("bots_new", "بوتات جديدة", "New bots"),
        mv("msgs_in", "رسائل عملاء وصلت البوتات", "Customer messages received"),
        mv("revenue", "إيراد معتمد (ج.م)", "Approved revenue (EGP)"),
        T(f"دفعات تنتظر قرارك: {n['pay_pending']}", f"Payments awaiting your decision: {n['pay_pending']}"),
        T(f"بوتات أُنشئت ولم تُشغَّل: {n['bots_never_started']} · "
          f"شغّالة بلا عميل: {n['bots_started_silent']}",
          f"Created but never started: {n['bots_never_started']} · "
          f"live with no customer: {n['bots_started_silent']}"),
    ]
    f = rep.get("forecast", {}).get("signups") or {}
    if f.get("confidence") not in (None, "none"):
        lines.append(T(f"المتوقّع الفترة القادمة: {int(f['expected'])} تسجيلاً "
                       f"(ثقة {f['confidence']})",
                       f"Next period forecast: {int(f['expected'])} signups "
                       f"(confidence {f['confidence']})"))
    return lines


# ---------------------------------------------------------------- البناء
def build(days=DEFAULT_DAYS, end=None, lang="ar", with_logs=True, with_conv=True):
    """التقرير كاملاً. النافذتان متساويتان دائماً: الحالية `[a,b)` والسابقة `[a-len,a)`."""
    a, b = period(days, end)
    span = b - a
    now = db.report_window(a, b)
    prev = db.report_window(a - span, a)
    series_from = min(a, int(time.mktime((datetime.date.fromtimestamp(b) -
                                          datetime.timedelta(days=TREND_DAYS - 1)).timetuple())))
    daily = db.report_daily(a, b)
    trend_daily = db.report_daily(series_from, b)
    expiring = db.report_expiring(7)
    cap_total = _capacity()
    running = now["bots_active"]
    weekly_growth = max(0.0, (now["bots_new_active"] or 0) * 7.0 / max(1, days))
    rep = {
        "period": {"days": days, "from": a, "to": b, "label": label(a, b),
                   "prev_label": label(a - span, a), "generated_at": int(time.time())},
        "now": now, "prev": prev, "delta": compare(now, prev),
        "daily": daily, "trend_daily": trend_daily,
        "bots": db.report_bots(a, b), "problems": db.report_problem_users(a, b),
        "emails": db.report_emails(a, b), "expiring": expiring,
        "renewal_value": _renewal_value(expiring),
        "capacity": {"running": running, "capacity": cap_total,
                     "pct": int(round(running * 100.0 / cap_total)) if cap_total else 0,
                     "weeks_to_full": (int((cap_total - running) / weekly_growth)
                                       if weekly_growth and running < cap_total else None)},
        "forecast": forecast(trend_daily, days),
    }
    rep["logs"] = log_summary(a, b) if with_logs else {"available": False, "reason": "off"}
    rep["conv"] = conv_summary(a, b) if with_conv else {}
    rep["findings"] = findings(rep, lang)
    rep["summary"] = summary(rep, lang)
    rep["lang"] = lang
    return rep


def log_summary(a, b):
    """قراءة السجل — لا يجوز أن يُسقط عطلٌ فيها التقرير كله."""
    try:
        import log_scan
        return log_scan.scan(since=a, until=b)
    except Exception as e:                       # noqa: BLE001 — التقرير أهم من قسم فيه
        return {"available": False, "reason": f"{type(e).__name__}", "dir": "", "files": [],
                "levels": {}, "daily": [], "groups": [], "loggers": [], "paths": [],
                "signals": {}, "errors": 0, "warnings": 0, "lines": 0, "truncated": False}


def conv_summary(a, b, bot_id=None):
    try:
        import conv_insights
        rows = db.conv_rows(a, b, bot_id)
        return conv_insights.analyze(rows, truncated=len(rows) >= db.CONV_ROWS_MAX)
    except Exception as e:                       # noqa: BLE001
        return {"messages": 0, "error": type(e).__name__}


def tg_send(chat_id, text):
    """رسالة واحدة عبر Bot API مباشرةً — بلا `bot_manager`.

    لماذا لا المدير؟ لأن التقرير يُرسل أيضاً من سطر الأوامر ومن cron خارج عملية
    الويب، وتشغيل بوت المنصة هناك يفتح `getUpdates` ثانياً فيتصارع مع الإنتاج
    (تليجرام يعطي 409 ويتوقف استقبال رسائل الأدمن). `sendMessage` وحدها بلا polling
    آمنة تماماً. التوكن لا يُسجَّل ولا يُطبع (AGENTS §17)."""
    import json as _json
    import urllib.request
    token = db.get_platform("platform_bot_token", "") or ""
    if not token or not chat_id:
        return False
    data = _json.dumps({"chat_id": str(chat_id), "text": text,
                        "disable_web_page_preview": True}).encode("utf-8")
    req = urllib.request.Request(f"https://api.telegram.org/bot{token}/sendMessage", data=data,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return _json.loads(r.read().decode("utf-8")).get("ok", False)
    except Exception:                            # noqa: BLE001 — best-effort مثل البريد
        return False


def deliver(rep, notify=None, emails=None):
    """يوصّل التقرير: تليجرام لكل أدمن + بريد لكل حساب إدارة. `{email, telegram}`.

    best-effort بالكامل (AGENTS §15): فشل قناة لا يمنع الأخرى، ولا يرمي أبداً —
    يُستدعى من مسار الأدمن ومن خيط خلفي في `bot_manager` معاً.
    الإرسال **متزامن** هنا عمداً: المُنادي يحتاج نتيجة حقيقية ليقرّر تسجيل
    «أُرسل هذا الأسبوع»، وإلا أحرق أول تشغيل التقرير بلا أن يصل."""
    out = {"email": 0, "telegram": 0}
    text = to_text(rep)
    notify = notify or tg_send        # بلا مدير بوتات: Bot API مباشرةً
    if notify:
        for cid in db.admin_chat_ids():
            try:
                if notify(cid, text):
                    out["telegram"] += 1
            except Exception:                    # noqa: BLE001
                pass
    try:
        import mailer
        if mailer.configured():
            subject, html, plain = mailer.weekly_report_email(rep, rep.get("lang", "ar"))
            for addr in (emails if emails is not None else db.admin_emails()):
                if mailer.send_mail(addr, subject, html, plain):
                    out["email"] += 1
    except Exception:                            # noqa: BLE001
        pass
    return out


# ---------------------------------------------------------------- الإخراج
def to_text(rep, limit=3500):
    """نسخة نصّية للبريد العادي وتليجرام — الخلاصة وأهم الملاحظات فقط."""
    lang = rep.get("lang", "ar")
    en = lang == "en"
    p = rep["period"]
    lines = [("📊 BotYalla — weekly report" if en else "📊 تقرير BotYalla الأسبوعي"),
             p["label"], ""]
    lines += [f"• {s}" for s in rep["summary"]]
    if rep["findings"]:
        lines += ["", ("What needs you:" if en else "يحتاج تدخّلك:")]
        icon = {"risk": "🔴", "warn": "🟠", "good": "🟢", "info": "⚪"}
        for f in rep["findings"][:8]:
            lines.append(f"{icon.get(f['level'], '•')} {f['title']}")
            if f.get("action"):
                lines.append(f"   ← {f['action']}")
    conv = rep.get("conv") or {}
    if conv.get("unanswered"):
        lines += ["", ("Top unanswered questions:" if en else "أكثر الأسئلة بلا إجابة:")]
        for q in conv["unanswered"][:5]:
            lines.append(f"• ({q['v']}×) {q.get('sample') or q['k']}")
    text = "\n".join(lines)
    return text[:limit]


# اسم كل مقياس في ملف التصدير: من يفتحه في Excel لا يعرف `bots_new_active`.
METRIC_NAMES = {
    "signups": ("تسجيلات جديدة", "New signups"),
    "bots_new": ("بوتات جديدة", "New bots"),
    "bots_new_active": ("بوتات جديدة شُغِّلت", "New bots started"),
    "msgs_in": ("رسائل عملاء واردة", "Customer messages in"),
    "msgs_out": ("رسائل صادرة", "Messages out"),
    "customers_new": ("عملاء جدد", "New customers"),
    "customers_active": ("عملاء نشطون", "Active customers"),
    "leads": ("بيانات مجمّعة", "Leads"),
    "orders": ("طلبات", "Orders"),
    "orders_value": ("قيمة الطلبات", "Orders value"),
    "revenue": ("إيراد معتمد", "Approved revenue"),
    "pay_sent": ("دفعات وصلت", "Payments received"),
    "pay_approved": ("دفعات معتمدة", "Payments approved"),
    "visitors": ("زوار", "Visitors"),
    "tickets_new": ("تذاكر دعم", "Support tickets"),
    "refusals": ("إيصالات مرفوضة آلياً", "Auto-refused receipts"),
    "emails_sent": ("رسائل بريد وصلت", "Emails delivered"),
    "emails_failed": ("رسائل بريد فشلت", "Emails failed"),
    "bots_never_started": ("بوتات أُنشئت ولم تُشغَّل", "Bots never started"),
    "bots_started_silent": ("بوتات شغّالة بلا عميل", "Live bots with no customer"),
    "signups_no_bot": ("سجّلوا بلا بوت", "Signed up without a bot"),
}


def metric_name(key, lang="ar"):
    pair = METRIC_NAMES.get(key)
    return (pair[1] if lang == "en" else pair[0]) if pair else key


# ---------------------------------------------------------------- ماركداون
def _md_table(head, rows):
    if not rows:
        return "_لا بيانات._\n"
    out = ["| " + " | ".join(str(h) for h in head) + " |",
           "|" + "|".join(["---"] * len(head)) + "|"]
    for r in rows:
        cells = [str(x).replace("|", "/").replace("\n", " ") for x in r]
        out.append("| " + " | ".join(cells) + " |")
    return "\n".join(out) + "\n"


def _when(ts):
    return datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M") if ts else "—"


def to_markdown(rep):
    """التقرير كاملاً ملفَّ ماركداون — للقراءة، وللأرشفة، ولتحليله بأداة أخرى.

    لماذا ماركداون لا JSON: الملف يُقرأ بعين الإنسان أولاً، ويُلصق في محادثة تحليل
    ثانياً. الأرقام كلها هنا كما هي في الصفحة — لا ملخّص ولا اجتزاء — وعيّنات رسائل
    العملاء مرّت بالحجب قبل أن تصل إلى هنا."""
    n, d, p = rep["now"], rep["delta"], rep["period"]
    logs, conv, em = rep.get("logs") or {}, rep.get("conv") or {}, rep.get("emails") or {}
    L = []
    add = L.append

    add(f"# تقرير BotYalla — {p['label']}")
    add(f"\n> الفترة: **{p['label']}** ({p['days']} يوماً) · المقارنة بـ **{p['prev_label']}**"
        f" · أُنشئ: {_when(p['generated_at'])}\n")

    add("## الخلاصة\n")
    for s in rep["summary"]:
        add(f"- {s}")
    add("")

    add("## ما يحتاج تدخّلاً\n")
    icon = {"risk": "🔴 عاجل", "warn": "🟠 انتبه", "good": "🟢 جيد", "info": "⚪ معلومة"}
    if rep["findings"]:
        for f in rep["findings"]:
            add(f"### {icon.get(f['level'], '•')} — {f['title']}")
            if f.get("detail"):
                add(f"{f['detail']}")
            if f.get("action"):
                add(f"**الإجراء:** {f['action']}")
            add("")
    else:
        add("_لا ملاحظة عاجلة في هذه الفترة._\n")

    add("## المقاييس مقارنةً بالفترة السابقة\n")
    add(_md_table(["المقياس", "الفترة", "السابقة", "التغيّر %"],
                  [[metric_name(k), v["now"], v["prev"],
                    "جديد" if v["change"] is None else v["change"]] for k, v in d.items()]))

    add("## أين يتوقّف الناس\n")
    f = n["funnel"]
    add(_md_table(["المرحلة", "العدد"],
                  [["سجّلوا", f["signup"]], ["أنشأوا بوتاً", f["bot_created"]],
                   ["شغّلوا البوت", f["bot_live"]], ["وصلتهم أول رسالة عميل", f["first_message"]],
                   ["اشتراك مدفوع", f["paid"]]]))
    add(_md_table(["الحالة", "العدد"],
                  [["سجّل ولم ينشئ بوتاً", n["signups_no_bot"]],
                   ["أنشأ بوتاً ولم يشغّله", n["bots_never_started"]],
                   ["شغّل بوتاً ولم تصله رسالة عميل", n["bots_started_silent"]],
                   ["بوتات شغّالة صامتة في الفترة", n["silent_active_bots"]],
                   ["حساب جديد لم يؤكّد بريده", n["signups_stuck_verify"]]]))

    add("## التنبؤ للفترة القادمة\n")
    add("> خطّ اتجاه (انحدار خطّي) على السلسلة اليومية — تقدير لا وعد، ومعه درجة الثقة.\n")
    add(_md_table(["المقياس", "المتوقّع", "الفترة الماضية", "لليوم", "الثقة"],
                  [[metric_name(k), round(v["expected"], 1), v["last_period"], v["per_day"],
                    v["confidence"]] for k, v in (rep.get("forecast") or {}).items()]))
    cap = rep["capacity"]
    add(f"- سعة الخادم: **{cap['running']} / {cap['capacity']}** بوت شغّال ({cap['pct']}%)"
        + (f" — يبلغ السقف خلال ~{cap['weeks_to_full']} أسبوعاً بمعدّل النمو الحالي."
           if cap.get("weeks_to_full") else "."))
    add(f"- اشتراكات تنتهي خلال 7 أيام: **{len(rep['expiring'])}** "
        f"(قيمة تجديدها بسعر القائمة ≈ {rep['renewal_value']} ج.م): "
        + (", ".join(x["username"] for x in rep["expiring"][:20]) or "—") + "\n")

    add("## المال\n")
    add(_md_table(["البند", "القيمة"],
                  [["إيراد معتمد في الفترة", n["revenue"]],
                   ["دفعات وصلت", n["pay_sent"]], ["اعتُمدت", n["pay_approved"]],
                   ["رُفضت", n["pay_rejected"]],
                   ["تنتظر قراراً الآن", n["pay_pending"]],
                   ["منها متأخرة أكثر من يوم", n["pay_pending_late"]],
                   ["شحن محفظة", n["wallet_topups"]], ["إضافات بيعت", n["addons_sold"]],
                   ["مشتركون يدفعون الآن", n["paying_now"]],
                   ["إيصالات مرفوضة آلياً", n["refusals"]],
                   ["طلبات عملاء البوتات", n["orders"]],
                   ["قيمتها", n["orders_value"]],
                   ["إيصالات عملاء البوتات", n["bot_payments"]]]))
    if n["refusals_by_reason"]:
        add("أسباب رفض الإيصالات:\n")
        add(_md_table(["السبب", "مرات"], [[r["k"], r["v"]] for r in n["refusals_by_reason"]]))

    add("## الزوار ومصادرهم\n")
    add(_md_table(["المصدر", "زوار"], [[r["k"], r["v"]] for r in n["visitor_sources"]]))
    add(_md_table(["الصفحة", "زوار"], [[r["k"], r["v"]] for r in n["top_pages"]]))
    add(_md_table(["مصدر التسجيل", "عدد"], [[r["k"], r["v"]] for r in n["signup_sources"]]))

    add("## نتائج كل بوت\n")
    add(_md_table(["البوت", "المالك", "النوع", "القناة", "شغّال", "وارد", "صادر", "ذكاء",
                   "بشري", "عملاء", "جدد", "بيانات", "طلبات", "قيمة", "حجوزات", "آخر رسالة"],
                  [[b["name"], b["owner"], b["template"], b["channel"],
                    "نعم" if b["is_active"] else "لا", b["msgs_in"], b["msgs_out"],
                    b["ai_replies"], b["human_replies"], b["customers"], b["new_customers"],
                    b["leads"], b["orders"], b["orders_value"], b["bookings"],
                    _when(b["last_in"])] for b in rep["bots"]]))

    add("## من حدثت معه مشكلة\n")
    add(_md_table(["المستخدم", "الباقة", "سجّل في", "ما حدث"],
                  [[u.get("username", ""), u.get("plan", ""), _when(u.get("created_at")),
                    " · ".join(f"{k}×{v}" for k, v in u["problems"].items())]
                   for u in rep["problems"]]))

    add("## البريد\n")
    add(_md_table(["الحالة", "عدد"],
                  [["وصلت", n["emails_sent"]], ["فشلت", n["emails_failed"]],
                   ["تُخطّيت", n["emails_skipped"]], ["أكواد تأكيد أُرسلت", n["verify_emails"]]]))
    if em.get("campaigns"):
        add(_md_table(["الحملة", "النوع", "الجمهور", "وصلت", "فشلت", "تُخطّيت", "الحالة"],
                      [[c["subject"] or f"#{c['id']}", c["kind"], c["audience"], c["sent"],
                        c["failed"], c["skipped"], c["status"]] for c in em["campaigns"]]))
    if em.get("failed_users"):
        add("لم تصلهم: " + ", ".join(f"{x['username']} ({x['n']})" for x in em["failed_users"]) + "\n")

    add("## سجل الخادم\n")
    if logs.get("available"):
        add(f"- قُرئ **{logs['lines']}** سطراً من {len(logs.get('files') or [])} ملف"
            + (" (الأحدث فقط — السجل أكبر من سقف القراءة)" if logs.get("truncated") else "") + ".")
        add(f"- أخطاء: **{logs['errors']}** · تحذيرات: **{logs['warnings']}**.")
        sig = {k: v for k, v in (logs.get("signals") or {}).items() if v}
        if sig:
            add("- إشارات: " + " · ".join(f"`{k}`={v}" for k, v in sig.items()))
        add("")
        add(_md_table(["العطل", "المستوى", "مرات", "أول ظهور", "آخر ظهور"],
                      [[(g["trace"] or g["sample"])[:120], g["level"], g["count"],
                        _when(g["first"]), _when(g["last"])] for g in logs.get("groups") or []]))
        if logs.get("paths"):
            add(_md_table(["مسار انهار", "مرات"], [[x["k"], x["v"]] for x in logs["paths"]]))
    else:
        add(f"_السجل غير متاح ({logs.get('reason', '')}) — المسار: {logs.get('dir', '')}._\n")

    add("## المحادثات\n")
    if conv.get("messages"):
        add(f"- **{conv['in_count']}** رسالة عميل من **{conv['customers']}** عميلاً في "
            f"**{conv['conversations']}** محادثة · نسبة الرد **{conv['answer_rate']}%** · "
            f"**{conv['unanswered_total']}** سؤالاً بلا إجابة · **{conv['waiting_total']}** "
            f"محادثة تنتظر رداً الآن.")
        if conv.get("truncated"):
            add("- ⚠️ الرسائل أكثر من سقف التحليل، فحُلِّل الأحدث منها فقط.")
        add("")
        add("### عمّ يسأل العملاء\n")
        import conv_insights as _CI
        add(_md_table(["النيّة", "عدد", "%"],
                      [[_CI.intent_name(i["k"]), i["v"], i["pct"]] for i in conv["intents"]]))
        add("### أسئلة بلا إجابة (أهم قائمة في التقرير)\n")
        add(_md_table(["السؤال", "تكرّر", "البوت"],
                      [[q.get("sample") or q["k"], q["v"], q.get("bot_id")]
                       for q in conv["unanswered"]]))
        add("### عبارات تتكرر حرفياً\n")
        add(_md_table(["العبارة", "مرات"],
                      [[x.get("sample") or x["k"], x["v"]] for x in conv["phrases"]]))
        add("### سرعة الرد (بالثواني)\n")
        add(_md_table(["من يردّ", "ردود", "الوسيط", "المتوسط", "أبطأ 10%"],
                      [[k, v["n"], v["median"], v["avg"], v["p90"]]
                       for k, v in (conv.get("response") or {}).items() if v]))
        s = conv.get("sentiment") or {}
        add(f"- النبرة: سلبية **{s.get('neg', 0)}** ({s.get('neg_pct', 0)}%) · "
            f"إيجابية {s.get('pos', 0)} · محايدة {s.get('neutral', 0)}")
        if conv.get("negatives"):
            add("\n### شكاوى متكررة\n")
            add(_md_table(["الشكوى", "مرات"],
                          [[x.get("text", ""), x.get("count", 1)] for x in conv["negatives"]]))
        if conv.get("bots"):
            add("### المحادثات لكل بوت\n")
            add(_md_table(["البوت", "وارد", "صادر", "عملاء", "بلا إجابة", "نسبة الرد", "أكثر نيّة"],
                          [[b["name"], b["msgs_in"], b["msgs_out"], b["customers"],
                            b["unanswered"], b["answer_rate"], b["top_intent"]]
                           for b in conv["bots"]]))
        add("### ساعات الذروة\n")
        add(_md_table(["الساعة", "رسائل"],
                      [[f"{h['k']:02d}", h["v"]] for h in conv.get("hours") or [] if h["v"]]))
    else:
        add("_لا رسائل في هذه الفترة._\n")

    add("---\n")
    add("_وُلِّد آلياً من BotYalla. عيّنات رسائل العملاء مرّت بالحجب: لا أرقام هواتف ولا "
        "عناوين بريد ولا توكنات في هذا الملف._")
    return "\n".join(L) + "\n"


_CSV_SECTIONS = ("summary", "bots", "problems", "unanswered")


def csv_rows(rep):
    """صفوف التصدير — قسم تلو الآخر في ملف واحد، كل قسم بعنوان أعمدته."""
    lang = rep.get("lang", "ar")
    en = lang == "en"
    T = lambda ar, e: e if en else ar
    out = [[T("تقرير BotYalla", "BotYalla report"), rep["period"]["label"]], []]
    out.append([T("المقياس", "Metric"), T("الفترة", "This period"),
                T("السابقة", "Previous"), T("التغيّر %", "Change %")])
    for k, v in rep["delta"].items():
        out.append([metric_name(k, lang), v["now"], v["prev"],
                    "" if v["change"] is None else v["change"]])
    out += [[], [T("البوت", "Bot"), T("المالك", "Owner"), T("النوع", "Template"),
                 T("القناة", "Channel"), T("وارد", "In"), T("صادر", "Out"),
                 T("عملاء", "Customers"), T("عملاء جدد", "New customers"),
                 T("بيانات", "Leads"), T("طلبات", "Orders"), T("قيمة الطلبات", "Orders value"),
                 T("حجوزات", "Bookings"), T("شغّال", "Active")]]
    for r in rep["bots"]:
        out.append([r["name"], r["owner"], r["template"], r["channel"], r["msgs_in"],
                    r["msgs_out"], r["customers"], r["new_customers"], r["leads"],
                    r["orders"], r["orders_value"], r["bookings"], 1 if r["is_active"] else 0])
    out += [[], [T("المستخدم", "User"), T("الباقة", "Plan"), T("المشاكل", "Problems")]]
    for u in rep["problems"]:
        out.append([u.get("username", ""), u.get("plan", ""),
                    " | ".join(f"{k}×{v}" for k, v in u["problems"].items())])
    conv = rep.get("conv") or {}
    if conv.get("unanswered"):
        out += [[], [T("سؤال بلا إجابة", "Unanswered question"), T("مرات", "Times"),
                     T("البوت", "Bot")]]
        for q in conv["unanswered"]:
            out.append([q.get("sample") or q["k"], q["v"], q.get("bot_id") or ""])
    return out
