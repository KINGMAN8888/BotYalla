#!/usr/bin/env bash
# رفع المشروع لأول مرة على GitHub
# 1) أنشئ ريبو فاضي على GitHub (بدون README).
# 2) شغّل:  bash push_to_github.sh https://github.com/KINGMAN8888/BotYalla.git
set -e
REPO="${1:?ضع رابط الريبو}"
cd "$(dirname "$0")/.."
git init -b main 2>/dev/null || git init
git add .
git commit -m "BotYalla — initial release" || echo "لا جديد للحفظ"
git remote remove origin 2>/dev/null || true
git remote add origin "$REPO"
git push -u origin main
echo "✅ تم الرفع على $REPO"
