#!/usr/bin/env bash
# مشغّل الاختبارات في CI: يفشل على **كسر جديد** فقط.
#
# لماذا لا `run_tests.sh` مباشرة: المستودع فيه مجموعات مكسورة من قبل (انظر
# tools/expected_failures.txt). لو فشل CI بسببها لصار أحمر دائماً، والأحمر الدائم
# لا يُقرأ — فيمرّ الكسر الحقيقي بلا أن ينتبه أحد. هنا نقارن مجموعة الفاشلين
# بالقائمة المعروفة: أي اسم جديد = فشل، وأي اسم تعافى = تنبيه ليُشطب من القائمة.
#
#   ./tools/ci_tests.sh
set -u
cd "$(dirname "$0")/.."
PY="${PYTHON:-python3}"
export BOTYALLA_OCR="${BOTYALLA_OCR:-0}"

# اسم الملف وحده: نقتطع التعليق بعده والمسافات (وسطور ويندوز)
known=$(tr -d '\r' < tools/expected_failures.txt | sed -e 's/#.*//' -e 's/[[:space:]]//g' \
        | grep -v '^$' | sort -u)
failed=()
passed=0

for f in tests/test_*.py; do
    name=$(basename "$f")
    printf "  %-32s" "$name"
    if out=$("$PY" "$f" 2>&1); then
        echo "PASS"
        passed=$((passed + 1))
    else
        echo "FAIL"
        printf '%s\n' "$out" | tail -15 | sed 's/^/      /'
        failed+=("$name")
    fi
done

echo
new=()
for n in "${failed[@]:-}"; do
    [ -z "$n" ] && continue
    grep -qxF "$n" <<< "$known" || new+=("$n")
done
fixed=()
while read -r n; do
    [ -z "$n" ] && continue
    printf '%s\n' "${failed[@]:-}" | grep -qxF "$n" || fixed+=("$n")
done <<< "$known"

echo "نجح: $passed · فشل: ${#failed[@]} (معروف مسبقاً: $(( ${#failed[@]} - ${#new[@]} )))"
if [ "${#fixed[@]}" -gt 0 ]; then
    echo "ℹ️  تعافت ولم تعد فاشلة — اشطبها من tools/expected_failures.txt: ${fixed[*]}"
fi
if [ "${#new[@]}" -gt 0 ]; then
    echo "❌ كسر جديد: ${new[*]}"
    exit 1
fi
echo "✅ لا كسر جديد."
