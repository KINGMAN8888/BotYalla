"""حساب مراجعة لمراجعي Meta (App Review) — كلمة مرور عشوائية تُطبع مرة واحدة.

    python tools/make_reviewer.py                      # meta_reviewer@botyalla.com
    python tools/make_reviewer.py reviewer@example.com --plan whatsapp_pro

لماذا سكربت بدل إنشاء الحساب يدوياً:
  * **دور `user` لا `admin`.** المراجع يحتاج أن يجرّب «اربط رقمك بضغطة» كعميل عادي،
    ودور الأدمن يفتح له لوحة المنصة وأسرارها وحسابات كل العملاء — وحساب المراجعة
    يُنشر في نموذج Meta فيقرأه كل من يصل إليه.
  * **كلمة المرور تُولَّد عشوائياً هنا ولا تُكتب في أي ملف.** أي كلمة مرور مكتوبة في
    مستودع عام = حساب مفتوح للجميع (AGENTS.md §3: لا أسرار في الكود).
  * يمرّ على `database` لا على sqlite مباشرة، فيحترم الهجرات والقيود.

يعمل على القاعدة التي يشير إليها `BOTYALLA_DB` (أو `botyalla.db` في جذر المشروع كما
يفعل التطبيق). شغّله على الخادم، وانسخ كلمة المرور من الخرج ثم امسح الطرفية.
"""
import argparse
import os
import secrets
import string
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:                                          # طرفية ويندوز بترميز cp1252 تكسر العربية
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import auth                                   # noqa: E402
import database as db                         # noqa: E402

ALPHABET = string.ascii_letters + string.digits + "!@#$%^&*-_"


def new_password(n=18):
    """كبير وصغير ورقم ورمز — نفس سياسة صفحة التسجيل."""
    while True:
        pw = "".join(secrets.choice(ALPHABET) for _ in range(n))
        if (any(c.isupper() for c in pw) and any(c.islower() for c in pw)
                and any(c.isdigit() for c in pw) and any(c in "!@#$%^&*-_" for c in pw)):
            return pw


def main():
    p = argparse.ArgumentParser(description="Create or reset the Meta App Review test account.")
    p.add_argument("username", nargs="?", default="meta_reviewer@botyalla.com")
    p.add_argument("--plan", default="whatsapp", help="خطة الاشتراك (افتراضي: whatsapp)")
    p.add_argument("--days", type=int, default=90, help="مدة الاشتراك بالأيام")
    a = p.parse_args()

    db.init_db()
    pw = new_password()
    pw_hash = auth.hash_password(pw)
    u = db.get_user_by_name(a.username)
    if u:
        if u["role"] != "user":
            print(f"⚠️  «{a.username}» دوره {u['role']} — حساب المراجعة يجب أن يكون عميلاً عادياً.")
            print("    غيّر دوره من «المستخدمون» في لوحة الأدمن، أو مرّر اسماً آخر.")
            return 1
        ok, err = db.update_user_credentials(u["id"], pw_hash=pw_hash)
        if not ok:
            print(f"❌ {err}")
            return 1
        uid, what = u["id"], "أُعيد ضبط كلمة مروره"
    else:
        # أول حساب في قاعدة فارغة يصير admin (database.create_account) — وحساب المراجعة
        # لا يصح أن يكون أدمن، فنرفض بدل أن نسلّم Meta مفتاح المنصة.
        with db.get_conn() as c:
            if c.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0:
                print("❌ القاعدة فارغة — أنشئ حساب الأدمن أولاً، ثم شغّل هذا السكربت.")
                return 1
        uid, err = db.create_account(a.username, pw_hash, a.username, email_verified=True)
        if err:
            print(f"❌ {err}")
            return 1
        what = "أُنشئ"

    db.activate_subscription(uid, a.plan, days=a.days)
    print(f"✅ حساب المراجعة {what}: {a.username}")
    print(f"🔑 كلمة المرور (تظهر مرة واحدة): {pw}")
    print(f"📦 الباقة: {a.plan} لمدة {a.days} يوماً · الدور: user")
    print("   ضعها في نموذج Meta، وبعد انتهاء المراجعة شغّل السكربت ثانيةً لتغييرها.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
