#!/usr/bin/env bash
# ============================================================
#  BotYalla — سكربت النشر التلقائي على سيرفر Ubuntu (VPS)
#  الاستخدام:  sudo bash deploy.sh <github_repo_url> [domain]
#  مثال:       sudo bash deploy.sh https://github.com/you/botyalla.git botyalla.com
# ============================================================
set -euo pipefail
REPO="${1:-}"
DOMAIN="${2:-}"
APP_DIR="/opt/botyalla"
USER="botyalla"

if [[ -z "$REPO" ]]; then echo "❌ Usage: sudo bash deploy.sh <repo_url> [domain]"; exit 1; fi
if [[ $EUID -ne 0 ]]; then echo "❌ شغّل بصلاحية root (sudo)"; exit 1; fi

echo "🔧 [1/8] تثبيت الحزم..."
apt-get update -y
apt-get install -y python3 python3-venv python3-pip git nginx
# OCR اختياري (لتفعيل فحص المبلغ في الاسكرين)
apt-get install -y tesseract-ocr tesseract-ocr-ara || true

echo "👤 [2/8] إنشاء مستخدم الخدمة..."
id -u "$USER" &>/dev/null || useradd -r -m -d "$APP_DIR" -s /bin/bash "$USER"

echo "📥 [3/8] جلب الكود..."
if [[ -d "$APP_DIR/.git" ]]; then
  git -C "$APP_DIR" pull
else
  rm -rf "$APP_DIR"; git clone "$REPO" "$APP_DIR"
fi
mkdir -p "$APP_DIR/uploads"

echo "🐍 [4/8] البيئة الافتراضية والاعتماديات..."
python3 -m venv "$APP_DIR/venv"
"$APP_DIR/venv/bin/pip" install --upgrade pip
"$APP_DIR/venv/bin/pip" install -r "$APP_DIR/requirements.txt"
# pytesseract اختياري
"$APP_DIR/venv/bin/pip" install pytesseract Pillow || true

echo "🔐 [5/8] ملف البيئة (.env)..."
if [[ ! -f "$APP_DIR/.env" ]]; then
  SECRET=$("$APP_DIR/venv/bin/python" -c "import secrets;print(secrets.token_hex(32))")
  cat > "$APP_DIR/.env" <<ENV
FLASK_SECRET=$SECRET
COOKIE_SECURE=1
ENV
  echo "  ✓ تم توليد FLASK_SECRET عشوائي"
fi

chown -R "$USER:$USER" "$APP_DIR"

echo "⚙️ [6/8] خدمة systemd..."
cp "$APP_DIR/deploy/botyalla.service" /etc/systemd/system/botyalla.service
systemctl daemon-reload
systemctl enable botyalla
systemctl restart botyalla

echo "🌐 [7/8] Nginx..."
CONF=/etc/nginx/sites-available/botyalla
cp "$APP_DIR/deploy/nginx.conf" "$CONF"
if [[ -n "$DOMAIN" ]]; then sed -i "s/botyalla.com/$DOMAIN/g" "$CONF"; fi
ln -sf "$CONF" /etc/nginx/sites-enabled/botyalla
rm -f /etc/nginx/sites-enabled/default || true
nginx -t && systemctl restart nginx

echo "🔒 [8/8] HTTPS (اختياري)..."
if [[ -n "$DOMAIN" ]]; then
  apt-get install -y certbot python3-certbot-nginx || true
  echo "  شغّل يدوياً بعد ربط الدومين:  sudo certbot --nginx -d $DOMAIN -d www.$DOMAIN"
fi

echo ""
echo "✅ تم النشر! الحالة:"
systemctl --no-pager status botyalla | head -5
echo ""
echo "افتح: http://${DOMAIN:-<server-ip>}/  ثم سجّل أول حساب (سيكون المالك/الأدمن)."
echo "لتحديث الموقع لاحقاً:  sudo bash $APP_DIR/deploy/deploy.sh $REPO $DOMAIN"
