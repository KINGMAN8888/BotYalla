#!/usr/bin/env bash
# ============================================================================
#  BotYalla — نشر الإنتاج على سيرفر Hostinger
#
#  التشغيل على السيرفر (كـ root):
#     bash hostinger_deploy.sh                 # أول نشر بلا دومين (عبر IP)
#     bash hostinger_deploy.sh botyalla.com    # مع دومين + HTTPS
#     bash hostinger_deploy.sh --update        # تحديث فقط (سحب + بناء + إعادة تشغيل)
#
#  آمن للتكرار: تشغيله مرتين لا يكسر شيئاً ولا يعيد توليد الأسرار.
# ============================================================================
set -euo pipefail

APP_DIR="/opt/botyalla"
SVC_USER="botyalla"
REPO="${REPO:-https://github.com/KINGMAN8888/BotYalla.git}"
BRANCH="${BRANCH:-main}"
DOMAIN=""
UPDATE_ONLY=0

for arg in "$@"; do
  case "$arg" in
    --update) UPDATE_ONLY=1 ;;
    -*) ;;
    *) DOMAIN="$arg" ;;
  esac
done

log()  { echo -e "\n\033[1;36m▸ $*\033[0m"; }
warn() { echo -e "\033[1;33m  ! $*\033[0m"; }
die()  { echo -e "\033[1;31m✗ $*\033[0m" >&2; exit 1; }

[[ $EUID -eq 0 ]] || die "شغّل السكربت كـ root"

# ---------------------------------------------------------------- 1) الحزم
if [[ $UPDATE_ONLY -eq 0 ]]; then
  log "[1/9] تثبيت الحزم"
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -y
  apt-get install -y python3 python3-venv python3-pip nginx git curl sqlite3 ufw fail2ban
  # OCR اختياري: يفحص المبلغ داخل صورة الإيصال
  apt-get install -y tesseract-ocr tesseract-ocr-ara || warn "تعذّر تثبيت OCR — الفحص اليدوي يبقى شغّالاً"

  # Node مطلوب لبناء الواجهة. لو فشل التثبيت نعتمد على static/dist المرفوع مع الكود.
  if ! command -v node >/dev/null 2>&1; then
    curl -fsSL https://deb.nodesource.com/setup_22.x | bash - || true
    apt-get install -y nodejs || warn "تعذّر تثبيت Node — سنستخدم static/dist المرفوع"
  fi
fi

# ------------------------------------------------------- 2) المستخدم والكود
log "[2/9] المستخدم والكود"
id -u "$SVC_USER" &>/dev/null || useradd -r -m -d "$APP_DIR" -s /usr/sbin/nologin "$SVC_USER"

if [[ -d "$APP_DIR/.git" ]]; then
  git -C "$APP_DIR" fetch --all --prune
  git -C "$APP_DIR" reset --hard "origin/$BRANCH"
else
  mkdir -p "$APP_DIR"
  # لو المجلد غير فارغ (نشر يدوي سابق) نستنسخ في مسار مؤقت وننقل .git فقط
  if [[ -n "$(ls -A "$APP_DIR" 2>/dev/null)" ]]; then
    tmp="$(mktemp -d)"
    git clone --branch "$BRANCH" --depth 1 "$REPO" "$tmp/src"
    cp -a "$tmp/src/.git" "$APP_DIR/"
    git -C "$APP_DIR" reset --hard "origin/$BRANCH"
    rm -rf "$tmp"
  else
    git clone --branch "$BRANCH" "$REPO" "$APP_DIR"
  fi
fi
mkdir -p "$APP_DIR/uploads" /var/log/botyalla

# ------------------------------------------------------------ 3) بايثون
log "[3/9] البيئة الافتراضية"
[[ -d "$APP_DIR/venv" ]] || python3 -m venv "$APP_DIR/venv"
"$APP_DIR/venv/bin/pip" install --quiet --upgrade pip
"$APP_DIR/venv/bin/pip" install --quiet -r "$APP_DIR/requirements.txt"
"$APP_DIR/venv/bin/pip" install --quiet pytesseract Pillow || true

# ------------------------------------------------------------ 4) الأسرار
log "[4/9] ملف البيئة"
if [[ ! -f "$APP_DIR/.env" ]]; then
  SECRET="$("$APP_DIR/venv/bin/python" -c 'import secrets;print(secrets.token_hex(32))')"
  # كلمة مرور أدمن عشوائية — لا قيمة افتراضية معروفة إطلاقاً
  ADMPASS="$("$APP_DIR/venv/bin/python" -c 'import secrets;print(secrets.token_urlsafe(14))')"
  # بلا دومين نصل عبر http، وكوكي Secure لن يُرسَل أصلاً فيفشل الدخول صامتاً.
  if [[ -n "$DOMAIN" ]]; then COOKIE=1; else COOKIE=0; fi
  cat > "$APP_DIR/.env" <<ENV
FLASK_SECRET=$SECRET
COOKIE_SECURE=$COOKIE
ADMIN_USER=admin
ADMIN_PASS=$ADMPASS
ENV
  NEW_CREDS=1
else
  NEW_CREDS=0
  # ارفع COOKIE_SECURE تلقائياً عند إضافة دومين لاحقاً
  if [[ -n "$DOMAIN" ]] && grep -q '^COOKIE_SECURE=0' "$APP_DIR/.env"; then
    sed -i 's/^COOKIE_SECURE=0/COOKIE_SECURE=1/' "$APP_DIR/.env"
    warn "تم رفع COOKIE_SECURE إلى 1 (دومين + HTTPS)"
  fi
fi
chmod 600 "$APP_DIR/.env"

# ------------------------------------------------------------ 5) الواجهة
log "[5/9] بناء الواجهة"
if command -v npm >/dev/null 2>&1; then
  ( cd "$APP_DIR/frontend" && npm ci --silent && npm run build --silent ) \
    && echo "  ✓ تم بناء الواجهة" \
    || warn "فشل البناء — سنستخدم static/dist المرفوع مع الكود"
else
  echo "  ✓ Node غير متاح — نستخدم static/dist المرفوع مع الكود"
fi
[[ -f "$APP_DIR/static/dist/console.js" ]] || die "static/dist مفقود — الواجهة لن تعمل"

chown -R "$SVC_USER:$SVC_USER" "$APP_DIR" /var/log/botyalla

# ------------------------------------------------------------ 6) الخدمة
log "[6/9] خدمة systemd"
cp "$APP_DIR/deploy/botyalla.service" /etc/systemd/system/botyalla.service
systemctl daemon-reload
systemctl enable --quiet botyalla
systemctl restart botyalla

# ------------------------------------------------------------ 7) Nginx
log "[7/9] Nginx"
SERVER_NAME="${DOMAIN:-_}"
[[ -n "$DOMAIN" ]] && SERVER_NAME="$DOMAIN www.$DOMAIN"
sed "s/__SERVER_NAME__/$SERVER_NAME/" "$APP_DIR/deploy/nginx.conf" \
  > /etc/nginx/sites-available/botyalla
ln -sf /etc/nginx/sites-available/botyalla /etc/nginx/sites-enabled/botyalla
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl reload nginx

# ------------------------------------------- 8) الجدار الناري والنسخ الاحتياطي
if [[ $UPDATE_ONLY -eq 0 ]]; then
  log "[8/9] الجدار الناري والنسخ الاحتياطي"
  ufw allow OpenSSH >/dev/null 2>&1 || true
  ufw allow 'Nginx Full' >/dev/null 2>&1 || true
  ufw --force enable >/dev/null 2>&1 || warn "تعذّر تفعيل ufw"
  systemctl enable --now fail2ban >/dev/null 2>&1 || true

  chmod +x "$APP_DIR/deploy/backup.sh"
  cat > /etc/cron.d/botyalla-backup <<'CRON'
# نسخة احتياطية يومية 3 صباحاً
0 3 * * * root /opt/botyalla/deploy/backup.sh >> /var/log/botyalla/backup.log 2>&1
CRON
  "$APP_DIR/deploy/backup.sh" >/dev/null 2>&1 || true
fi

# ------------------------------------------------------------ 9) التحقق
log "[9/9] التحقق"
sleep 3
HEALTH="$(curl -fsS -m 10 http://127.0.0.1:8000/healthz 2>/dev/null || echo FAIL)"
if [[ "$HEALTH" == *'"ok": true'* || "$HEALTH" == *'"ok":true'* ]]; then
  echo "  ✓ التطبيق يستجيب والقاعدة تعمل"
else
  echo "  ✗ الفحص الصحّي فشل — آخر السجلات:"
  journalctl -u botyalla -n 30 --no-pager
  die "النشر لم يكتمل"
fi

if [[ -n "$DOMAIN" ]]; then
  log "HTTPS"
  apt-get install -y certbot python3-certbot-nginx >/dev/null 2>&1 || true
  echo "  شغّل الآن:  certbot --nginx -d $DOMAIN -d www.$DOMAIN"
  echo "  ثم فعّل سطر HSTS في /etc/nginx/sites-available/botyalla وأعد تحميل nginx"
fi

echo ""
echo "============================================================"
echo "  ✅ تم النشر"
echo "  العنوان : http://${DOMAIN:-$(hostname -I | awk '{print $1}')}/"
if [[ "${NEW_CREDS:-0}" -eq 1 ]]; then
  echo ""
  echo "  🔐 بيانات الدخول (تظهر مرة واحدة فقط — احفظها الآن):"
  echo "     المستخدم : admin"
  echo "     كلمة المرور: $(grep '^ADMIN_PASS=' "$APP_DIR/.env" | cut -d= -f2-)"
  echo "     غيّرها فوراً من صفحة «حسابي»."
fi
echo ""
echo "  السجلات : journalctl -u botyalla -f"
echo "  التحديث : bash $APP_DIR/deploy/hostinger_deploy.sh --update"
echo "============================================================"
