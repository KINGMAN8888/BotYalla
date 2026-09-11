#!/usr/bin/env python3
"""L-11 — قياس سقف عدد البوتات في عملية واحدة.

**لماذا هذا القياس أصلاً:** `gunicorn_conf.py` يشغّل `workers=1`، وكل بوتات
تليجرام تعيش داخل عملية الويب نفسها على حلقة asyncio واحدة. فالبوت رقم 200 لا
يبطئ صاحبه وحده — يبطئ **كل** مستخدم على المنصة، وصفحة الويب معهم. وتجاوز
السقف لا يعطي خطأً واضحاً بل تدهوراً يزحف، وهذا أسوأ أنواع الأعطال.

**ما يقيسه هذا السكربت بصدق:**
  ✅ الذاكرة لكل بوت (RSS) — وهي المورد الذي ينفد أولاً على خادم صغير.
  ✅ زمن بناء البوت وتسجيل معالجاته.
  ✅ زمن استجابة الويب **بينما** العدد يرتفع (إن مُرِّر `--web`).

**ما لا يقيسه — وعليك قياسه بنفسك:**
  ❌ حِمل الـpolling الحقيقي. كل بوت عامل يفتح طلب `getUpdates` طويل الأمد إلى
     تليجرام، وهذا يحتاج **توكنات حقيقية** ولا يمكن تزييفه. قِسه على الخادم
     بعشرة بوتات حقيقية ثم اضرب خطياً — أو الأدق: راقب الإنتاج عند كل عشرة.

الاستعمال (على **خادم اختبار**، لا الإنتاج):

    python3 tools/loadtest_bots.py                 # 10 · 50 · 100 · 200
    python3 tools/loadtest_bots.py --steps 10,50   # خطوات مخصّصة
    python3 tools/loadtest_bots.py --web http://127.0.0.1:8000/login

ثم انقل الرقم الناتج إلى إعداد `bot_capacity` من لوحة الأدمن، وسجّله في
`PROJECT_MEMORY.md` مع تاريخ القياس ومواصفات الخادم.
"""
import argparse, gc, json, os, resource, statistics, sys, time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# قاعدة مؤقتة دائماً: هذا السكربت ينشئ بوتات وهمية ولا يجوز أن يلمس الإنتاج.
import tempfile
_TMP = tempfile.mkdtemp(prefix="botyalla-load-")
os.environ.setdefault("BOTYALLA_DB", os.path.join(_TMP, "load.db"))
os.environ.setdefault("BOTYALLA_UPLOADS", _TMP)

DEFAULT_STEPS = [10, 50, 100, 200]
# عتبات الحكم. الذاكرة سقف صلب، وزمن الويب هو ما يشعر به المستخدم.
MEM_BUDGET_MB = 1500          # اضبطها على ذاكرة خادمك المتاحة فعلاً
WEB_SLOW_MS = 800             # فوقها تبدأ الصفحة تُحسّ بطيئة


def rss_mb():
    """الذاكرة المقيمة بالميجابايت. ru_maxrss بالكيلوبايت على لينكس."""
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0


def build_one(i):
    """يبني بوت تليجرام كاملاً بمعالجاته — بلا أي اتصال بالشبكة.

    هذا هو بالضبط ما يفعله `BotManager._start` قبل `initialize()`، فالذاكرة
    المقيسة هنا هي ذاكرة البوت الحقيقية ناقص مخازن الشبكة.
    """
    from telegram.ext import Application
    import templates_bot as T
    import tg_helpers as tg
    # توكن بالشكل الصحيح لكن بلا حساب خلفه — لا يُستدعى أي طلب هنا.
    token = f"{100000000 + i}:AA{'x' * 32}"
    app = Application.builder().token(token).build()
    app.bot_data["config"] = {"business_name": f"متجر {i}", "menu_items": [], "flow": None}
    app.bot_data["bot_id"] = i
    T.TEMPLATES["flow"]["build"](app)
    tg.register_common(app)
    return app


def probe_web(url, n=5):
    """زمن استجابة الويب الآن — المؤشر الذي يهمّ المستخدم فعلاً."""
    import urllib.request
    times = []
    for _ in range(n):
        t0 = time.perf_counter()
        try:
            urllib.request.urlopen(url, timeout=10).read(1024)
        except Exception as e:
            return {"error": str(e)}
        times.append((time.perf_counter() - t0) * 1000)
    return {"p50_ms": round(statistics.median(times), 1),
            "max_ms": round(max(times), 1)}


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--steps", default=",".join(map(str, DEFAULT_STEPS)),
                    help="أعداد البوتات المتراكمة، مفصولة بفواصل")
    ap.add_argument("--web", default="", help="رابط صفحة لقياس زمن استجابتها أثناء التحميل")
    ap.add_argument("--budget", type=int, default=MEM_BUDGET_MB, help="ميزانية الذاكرة بالميجابايت")
    ap.add_argument("--json", default="", help="اكتب النتائج إلى ملف JSON")
    a = ap.parse_args()
    steps = sorted({int(x) for x in a.steps.split(",") if x.strip().isdigit()})
    if not steps:
        ap.error("لا خطوات صالحة")

    base = rss_mb()
    print(f"الذاكرة قبل أي بوت: {base:.1f} MB")
    # «الحدّي» هو ما يُبنى عليه التقدير: أول البوتات تحمل معها استيراد المكتبات
    # مرّة واحدة، فمتوسط «المستهلك ÷ العدد» يبالغ في التكلفة عند الأعداد الصغيرة.
    print(f"{'بوتات':>7} {'الذاكرة':>10} {'المتوسط':>9} {'الحدّي':>9} {'بناء/بوت':>11}   الويب")
    print("-" * 72)

    apps, rows, verdict = [], [], None
    t_build_total = 0.0
    for target in steps:
        t0 = time.perf_counter()
        while len(apps) < target:
            apps.append(build_one(len(apps) + 1))
        t_build_total += time.perf_counter() - t0
        gc.collect()
        mem = rss_mb()
        used = mem - base
        per = used / len(apps) if apps else 0
        web = probe_web(a.web) if a.web else {}
        if rows:
            d_mem, d_bots = used - rows[-1]["used_mb"], len(apps) - rows[-1]["bots"]
            marginal = d_mem / d_bots if d_bots else per
        else:
            marginal = per
        row = {"bots": len(apps), "rss_mb": round(mem, 1), "used_mb": round(used, 1),
               "per_bot_mb": round(per, 2), "marginal_mb": round(marginal, 2),
               "build_ms_per_bot": round(t_build_total * 1000 / len(apps), 1), **web}
        rows.append(row)
        web_s = (f"{web.get('p50_ms')}ms (أقصى {web.get('max_ms')}ms)"
                 if "p50_ms" in web else web.get("error", "—"))
        print(f"{row['bots']:>7} {row['rss_mb']:>9.1f}M {row['per_bot_mb']:>8.2f}M "
              f"{row['marginal_mb']:>8.2f}M {row['build_ms_per_bot']:>10.1f}ms   {web_s}")

        if verdict is None:
            if mem > a.budget:
                verdict = (row["bots"], f"تجاوزت الذاكرة الميزانية ({a.budget}MB)")
            elif web.get("p50_ms", 0) > WEB_SLOW_MS:
                verdict = (row["bots"], f"زمن الويب تجاوز {WEB_SLOW_MS}ms")

    print("-" * 72)
    # التقدير على الحدّي لا المتوسط — وإلا قلّلنا السقف بلا سبب
    per = rows[-1]["marginal_mb"] if rows else 0
    if verdict:
        n, why = verdict
        print(f"⚠️  بدأ التدهور عند **{n}** بوتاً — {why}")
        safe = int(n * 0.8)
    else:
        safe = int((a.budget - base) / per) if per > 0 else 0
        print(f"✅ لم يظهر تدهور حتى {rows[-1]['bots']} بوتاً.")
        print(f"   بالتكلفة الحدّية {per:.2f}MB للبوت، ميزانية {a.budget}MB تكفي ≈ {safe} بوتاً.")

    print(f"\n📌 اضبط `bot_capacity` = **{safe}** من لوحة الأدمن، وسجّل في PROJECT_MEMORY.md:")
    print(f"   «قيس في {time.strftime('%Y-%m-%d')} — {per:.2f}MB/بوت، السقف {safe}».")
    print("\n⚠️  هذا القياس **لا يشمل** حِمل الـpolling الحقيقي (يحتاج توكنات حقيقية).")
    print("   قِس عشرة بوتات حقيقية على الخادم وقارن قبل أن تعتمد الرقم.")

    if a.json:
        with open(a.json, "w", encoding="utf-8") as f:
            json.dump({"base_mb": round(base, 1), "rows": rows, "suggested_capacity": safe,
                       "measured_at": time.strftime("%Y-%m-%d %H:%M")}, f,
                      ensure_ascii=False, indent=2)
        print(f"\nكُتبت النتائج في {a.json}")


if __name__ == "__main__":
    main()
