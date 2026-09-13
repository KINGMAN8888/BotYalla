#!/usr/bin/env bash
# مشغّل الاختبارات — عملية مستقلة لكل ملف.
#
# لماذا لا `pytest tests/` مباشرة؟ لأن `database.DB_PATH` يُقرأ مرة واحدة عند
# الاستيراد، وكل ملف اختبار يضبط BOTYALLA_DB قبل استيراده. تحت pytest تُستورد
# كل الملفات في عملية واحدة، فيفوز أول ملف بالقاعدة ويتشارك الباقون قاعدته
# فتتصادم بياناتهم (UNIQUE constraint failed: bots.token). عملية لكل ملف تحفظ
# العزل الذي بُنيت عليه الاختبارات.
#
#   ./run_tests.sh
set -u
cd "$(dirname "$0")"

PY="${PYTHON:-python3}"
# نتائج الاختبارات لا تتغيّر بوجود tesseract على الجهاز: القراءة مطفأة، واختبارات
# المحرك (test_receipts_support.py) تستبدل payments.read_text بنص جاهز.
export BOTYALLA_OCR="${BOTYALLA_OCR:-0}"
pass=0; fail=0; failed=()

run() {
    printf "  %-30s" "$(basename "$1")"
    if out=$("$PY" "$1" 2>&1); then
        n=$(printf '%s' "$out" | grep -oE "Ran [0-9]+" | head -1 | grep -oE "[0-9]+")
        printf "PASS%s\n" "${n:+ ($n)}"
        pass=$((pass + 1))
    else
        echo "FAIL"
        printf '%s\n' "$out" | tail -20 | sed 's/^/      /'
        fail=$((fail + 1)); failed+=("$(basename "$1")")
    fi
    # بقايا test_full.py وحده. ⚠️ لا تضِف botyalla.db هنا أبداً: هذا المجلد هو
    # WorkingDirectory على الخادم (/opt/botyalla)، فحذفه = حذف قاعدة الإنتاج.
    # لا يوجد اختبار ينشئ botyalla.db — كلها تعمل على قواعد مؤقتة.
    rm -f test_e2e.db
}

echo "BotYalla — الاختبارات"
for f in tests/test_*.py; do run "$f"; done
run test_full.py

echo
if [ "$fail" -eq 0 ]; then
    echo "✅ كل الملفات ناجحة ($pass)"
    exit 0
fi
echo "❌ فشل $fail من $((pass + fail)): ${failed[*]}"
exit 1
