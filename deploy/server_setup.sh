#!/usr/bin/env bash
# ============================================================
#  BotYalla — إعداد السيرفر (يُشغَّل تلقائياً من deploy_hostinger.bat)
#  يفترض أن ملفات المشروع موجودة بالفعل في /opt/botyalla
#  الاستخدام:  bash server_setup.sh [domain]
# ============================================================
set -euo pipefail
DOMAIN="${1:-}"
APP_DIR="/opt/botyalla"
SVC_USER="botyalla"

echo "🔧 [1/7] تحديث النظام وتثبيت الحزم..."
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y python3 python3-venv python3-pip nginx
# OCR اختياري لفحص المبالغ في إيصالات الدفع
apt-get install -y tesseract-ocr tesseract-ocr-ara || true

echo "👤 [2/7] مستخدم الخدمة..."
id -u "$SVC_USER" &>/dev/null || useradd -r -m -d "$APP_DIR" -s /bin/bash "$SVC_USER"
mkdir -p "$APP_DIR/uploads"

echo "🐍 [3/7] البيئة الافتراضية والاعتماديات..."
python3 -m venv "$APP_DIR/venv"
"$APP_DIR/venv/bin/pip" install --upgrade pip
"$APP_DIR/venv/bin/pip" install -r "$APP_DIR/requirements.txt"
"$APP_DIR/venv/bin/pip" install pytesseract Pillow || true   # اختياري

echo "🔐 [4/7] ملف البيئة (.env)..."
if [[ ! -f "$APP_DIR/.env" ]]; then
  SECRET=$("$APP_DIR/venv/bin/python" -c "import secrets;print(secrets.token_hex(32))")
  cat > "$APP_DIR/.env" <<ENV
FLASK_SECRET=$SECRET
COOKIE_SECURE=1
ADMIN_USER=admin
ADMIN_PASS=admin1234
ENV
  echo "  ✓ تم توليد FLASK_SECRET عشوائي"
fi

chown -R "$SVC_USER:$SVC_USER" "$APP_DIR"

echo "⚙️ [5/7] خدمة systemd..."
if [[ -f "$APP_DIR/deploy/botyalla.service" ]]; then
  cp "$APP_DIR/deploy/botyalla.service" /etc/systemd/system/botyalla.service
fi
systemctl daemon-reload
systemctl enable botyalla
systemctl restart botyalla

echo "🌐 [6/7] Nginx..."
CONF=/etc/nginx/sites-available/botyalla
cp "$APP_DIR/deploy/nginx.conf" "$CONF"
if [[ -n "$DOMAIN" ]]; then sed -i "s/botyalla.com/$DOMAIN/g" "$CONF"; fi
ln -sf "$CONF" /etc/nginx/sites-enabled/botyalla
rm -f /etc/nginx/sites-enabled/default || true
nginx -t && systemctl restart nginx

echo "🔒 [7/7] تجهيز HTTPS..."
if [[ -n "$DOMAIN" ]]; then
  apt-get install -y certbot python3-certbot-nginx || true
  echo "  لتفعيل HTTPS شغّل:  sudo certbot --nginx -d $DOMAIN -d www.$DOMAIN"
fi

echo ""
echo "✅ تم النشر بنجاح!"
systemctl --no-pager status botyalla | head -4 || true
echo ""
echo "افتح: http://${DOMAIN:-<server-ip>}/   ·   دخول: admin / admin1234"
