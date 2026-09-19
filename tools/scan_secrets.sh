#!/usr/bin/env bash
# حارس أسرار للملفات المتتبَّعة — يفشل البناء لو تسرّب سرّ إلى المستودع.
#
# المستودع عام: أي توكن أو كلمة مرور تصل إليه تُعتبر محروقة فور الدفع، وحذفها
# لاحقاً لا يُرجعها (التاريخ يبقى، والنسخ المرآة تبقى). فالحارس يمنعها قبل الدفع.
#
#   ./tools/scan_secrets.sh
#
# يفحص ما يتتبّعه git فقط: ‎.env و‎botyalla.db و‎.token.key مستثناة في ‎.gitignore،
# ووجود أيٍّ منها متتبَّعاً هو ذاته فشل.
set -u
cd "$(dirname "$0")/.."
fail=0

say_fail() { echo "❌ $1"; fail=1; }

# 1) ملفات لا يصح أن تُتتبَّع إطلاقاً
bad_files=$(git ls-files | grep -iE '(^|/)\.env$|(^|/)\.env\.(local|prod|production)$|\.db$|\.sqlite3?$|\.token\.key$|(^|/)id_rsa|\.pem$|\.p12$|\.pfx$|\.xlsx?$' || true)
[ -n "$bad_files" ] && say_fail "ملفات حسّاسة متتبَّعة:
$bad_files"

# 2) أنماط أسرار في محتوى الملفات المتتبَّعة (النصية فقط: -I)
#    الاستثناءات: أمثلة الوثائق وبيانات الاختبار المولَّدة عشوائياً.
scan() {   # scan <اسم> <نمط>
    hits=$(git grep -nIE "$2" -- . ':!*.lock' ':!package-lock.json' ':!static/dist/*' 2>/dev/null \
           | grep -viE 'example|placeholder|xxxx|your[_-]|<[a-z_]+>|token_hex|secrets\.|getenv|os\.environ' || true)
    [ -n "$hits" ] && say_fail "$1:
$hits"
}
scan "توكن تليجرام"        '[0-9]{8,10}:[A-Za-z0-9_-]{30,}'
scan "مفتاح OpenAI/Groq"   '(sk-[A-Za-z0-9_-]{20,}|gsk_[A-Za-z0-9]{30,}|nvapi-[A-Za-z0-9_-]{30,})'
scan "مفتاح Google"        'AIza[0-9A-Za-z_-]{30,}'
scan "توكن Meta"           'EAA[A-Za-z0-9]{40,}'
scan "كلمة مرور مكتوبة"    "(password|passwd|pw|secret|app_secret)\s*=\s*[\"'][^\"'\\\$\{]{8,}[\"']"

if [ "$fail" = 0 ]; then
    echo "✅ لا أسرار في الملفات المتتبَّعة."
else
    echo
    echo "لو كان الاكتشاف صحيحاً: غيّر السرّ فوراً عند مزوّده، ثم احذفه من الكود."
    echo "لو كان إنذاراً كاذباً: عدّل النمط أو استثنِ الملف في tools/scan_secrets.sh."
fi
exit "$fail"
