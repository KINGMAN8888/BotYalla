#!/usr/bin/env python3
"""تقرير BotYalla الأسبوعي من سطر الأوامر — يُشغَّل على الخادم في مجلد التطبيق.

    python tools/weekly_report.py                    # يطبع التقرير ماركداون
    python tools/weekly_report.py --days 30          # فترة أطول (7 | 14 | 30 …)
    python tools/weekly_report.py --out report.md    # يحفظه ملفاً
    python tools/weekly_report.py --send             # يرسله الآن: بريد الإدارة + تليجرام
    python tools/weekly_report.py --send --out r.md  # الاثنان معاً

لماذا أداة سطر أوامر والصفحة موجودة؟ لأن التقرير يُحتاج أحياناً بلا متصفح: بعد
النشر مباشرةً، أو من cron، أو لسحب ملف ماركداون وإرساله لمن يحلّله. ولأن
`--send` هنا لا يشغّل بوت المنصة إطلاقاً (يرسل برسالة Bot API واحدة عبر
`weekly_report.tg_send`) فلا يتصارع مع البوت العامل على `getUpdates`.

⚠️ يقرأ قاعدة الإنتاج نفسها التي تقرؤها الخدمة (`BOTYALLA_DB` أو `botyalla.db`
بجانب التطبيق) — **قراءة فقط**: لا يكتب في القاعدة شيئاً إلا طابع «أُرسل» عند
`--send` وحده.
"""
import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def load_env():
    """يقرأ `.env` كما يقرؤه `app.py` عند الاستيراد.

    ضروري: هذه الأداة لا تستورد `app`، وبلا `.env` يرى `mailer` أن SMTP
    غير مضبوط فلا يُرسل التقرير بالبريد ويظنّ المُشغّل أن المشكلة في الخادم."""
    path = os.path.join(ROOT, ".env")
    if not os.path.isfile(path):
        return
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip().strip("'\""))
    except OSError:
        pass


load_env()


def main():
    ap = argparse.ArgumentParser(description="BotYalla weekly report")
    ap.add_argument("--days", type=int, default=7, help="طول الفترة بالأيام (افتراضي 7)")
    ap.add_argument("--lang", default="ar", choices=("ar", "en"))
    ap.add_argument("--out", help="حفظ الماركداون في ملف بدل الطباعة")
    ap.add_argument("--send", action="store_true", help="إرسال التقرير الآن (بريد + تليجرام)")
    ap.add_argument("--no-logs", action="store_true", help="بلا قراءة سجل الخادم")
    ap.add_argument("--quiet", action="store_true", help="لا يطبع الماركداون")
    a = ap.parse_args()

    import time
    import database as db
    import weekly_report as WR

    rep = WR.build(a.days, lang=a.lang, with_logs=not a.no_logs)
    md = WR.to_markdown(rep)

    if a.out:
        with open(a.out, "w", encoding="utf-8") as f:
            f.write(md)
        print(f"✔ التقرير: {os.path.abspath(a.out)} ({len(md)} حرفاً)", file=sys.stderr)
    elif not a.quiet:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        print(md)

    if a.send:
        res = WR.deliver(rep)
        if res["email"] or res["telegram"]:
            db.set_platform("weekly_report_at", str(int(time.time())))
            print(f"✔ أُرسل: {res['email']} بريد · {res['telegram']} تليجرام", file=sys.stderr)
        else:
            print("✖ لم يُرسل. تأكّد من: SMTP مضبوط في .env · لحساب الإدارة بريد · "
                  "توكن بوت المنصة و«معرّف تليجرام للأدمن» مضبوطان في إعدادات المنصة.",
                  file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
