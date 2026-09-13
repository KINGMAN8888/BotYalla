#!/usr/bin/env bash
# ============================================================================
#  BotYalla — Production Deployment on Hostinger VPS
#
#  Run on the server (as root):
#     bash hostinger_deploy.sh                 # Initial deployment without domain (via IP)
#     bash hostinger_deploy.sh botyalla.com    # With domain + HTTPS
#     bash hostinger_deploy.sh --update        # Update only (pull + build + restart)
#
#  Idempotent: Running it twice breaks nothing and doesn't regenerate secrets.
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

[[ $EUID -eq 0 ]] || die "Run this script as root"

# ---------------------------------------------------------------- 1) Packages
if [[ $UPDATE_ONLY -eq 0 ]]; then
  log "[1/9] Installing packages"
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -y
  apt-get install -y python3 python3-venv python3-pip nginx git curl sqlite3 ufw fail2ban

  # Node is required for frontend build. If installation fails, we rely on uploaded static/dist.
  if ! command -v node >/dev/null 2>&1; then
    curl -fsSL https://deb.nodesource.com/setup_22.x | bash - || true
    apt-get install -y nodejs || warn "Could not install Node — we will use the uploaded static/dist"
  fi
fi

# ------------------------------------------------------- 2) User and Source Code
log "[2/9] User and Source Code"
id -u "$SVC_USER" &>/dev/null || useradd -r -m -d "$APP_DIR" -s /usr/sbin/nologin "$SVC_USER"

git config --global --add safe.directory "$APP_DIR"

if [[ -d "$APP_DIR/.git" ]]; then
  git -C "$APP_DIR" fetch --all --prune
  git -C "$APP_DIR" reset --hard "origin/$BRANCH"
else
  mkdir -p "$APP_DIR"
  # If directory is not empty (previous manual deploy), clone to a temp dir and copy .git only
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

# ------------------------------------------------------------ 3) Python
log "[3/9] Virtual Environment"
[[ -d "$APP_DIR/venv" ]] || python3 -m venv "$APP_DIR/venv"
"$APP_DIR/venv/bin/pip" install --quiet --upgrade pip
"$APP_DIR/venv/bin/pip" install --quiet -r "$APP_DIR/requirements.txt"

# Receipt OCR — on every run, --update included: without it no fake receipt is refused
# automatically (payments.py). apt skips it quickly when already installed.
DEBIAN_FRONTEND=noninteractive apt-get install -y -qq tesseract-ocr tesseract-ocr-ara tesseract-ocr-eng >/dev/null \
  || warn "Could not install tesseract — receipts will wait for manual review"

# ------------------------------------------------------------ 4) Secrets
log "[4/9] Environment File"
if [[ ! -f "$APP_DIR/.env" ]]; then
  SECRET="$("$APP_DIR/venv/bin/python" -c 'import secrets;print(secrets.token_hex(32))')"
  # Random admin password — no known default value at all
  ADMPASS="$("$APP_DIR/venv/bin/python" -c 'import secrets;print(secrets.token_urlsafe(14))')"
  # Without a domain we access via http, and Secure cookie won't be sent so login would fail silently.
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
  # Automatically upgrade COOKIE_SECURE when adding a domain later
  if [[ -n "$DOMAIN" ]] && grep -q '^COOKIE_SECURE=0' "$APP_DIR/.env"; then
    sed -i 's/^COOKIE_SECURE=0/COOKIE_SECURE=1/' "$APP_DIR/.env"
    warn "Upgraded COOKIE_SECURE to 1 (Domain + HTTPS)"
  fi
fi
chmod 600 "$APP_DIR/.env"

# ------------------------------------------------------------ 5) Frontend
log "[5/9] Building Frontend"
if command -v npm >/dev/null 2>&1; then
  ( cd "$APP_DIR/frontend" && npm ci --silent && npm run build --silent ) \
    && echo "  ✓ Frontend built successfully" \
    || warn "Build failed — we will use the uploaded static/dist"
else
  echo "  ✓ Node is not available — using the uploaded static/dist"
fi
[[ -f "$APP_DIR/static/dist/console.js" ]] || die "static/dist is missing — the frontend will not work"

chown -R "$SVC_USER:$SVC_USER" "$APP_DIR" /var/log/botyalla

# ------------------------------------------------------------ 6) Systemd Service
log "[6/9] systemd service"
cp "$APP_DIR/deploy/botyalla.service" /etc/systemd/system/botyalla.service
systemctl daemon-reload
systemctl enable --quiet botyalla
systemctl restart botyalla

# ------------------------------------------------------------ 7) Nginx
log "[7/9] Nginx"
# Preserve existing domain if updating without specifying one
if [[ -z "$DOMAIN" && -f /etc/nginx/sites-available/botyalla ]]; then
  EXISTING_SN=$(grep -oP '(?<=server_name ).*(?=;)' /etc/nginx/sites-available/botyalla | head -n 1)
  if [[ -n "$EXISTING_SN" && "$EXISTING_SN" != "_" && "$EXISTING_SN" != "__SERVER_NAME__" ]]; then
    DOMAIN=$(echo "$EXISTING_SN" | awk '{print $1}')
  fi
fi

SERVER_NAME="${DOMAIN:-_}"
[[ -n "$DOMAIN" ]] && SERVER_NAME="$DOMAIN www.$DOMAIN"

sed "s/__SERVER_NAME__/$SERVER_NAME/" "$APP_DIR/deploy/nginx.conf" \
  > /etc/nginx/sites-available/botyalla
ln -sf /etc/nginx/sites-available/botyalla /etc/nginx/sites-enabled/botyalla
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl reload nginx

# ------------------------------------------- 8) Firewall and Backups
if [[ $UPDATE_ONLY -eq 0 ]]; then
  log "[8/9] Firewall and Backups"
  ufw allow OpenSSH >/dev/null 2>&1 || true
  ufw allow 'Nginx Full' >/dev/null 2>&1 || true
  ufw --force enable >/dev/null 2>&1 || warn "Could not enable ufw"
  systemctl enable --now fail2ban >/dev/null 2>&1 || true

  chmod +x "$APP_DIR/deploy/backup.sh"
  cat > /etc/cron.d/botyalla-backup <<'CRON'
# Daily backup at 3 AM
0 3 * * * root /opt/botyalla/deploy/backup.sh >> /var/log/botyalla/backup.log 2>&1
CRON
  "$APP_DIR/deploy/backup.sh" >/dev/null 2>&1 || true
fi

# ------------------------------------------------------------ 9) Verification
log "[9/9] Verification"
sleep 3
HEALTH="$(curl -fsS -m 10 http://127.0.0.1:8000/healthz 2>/dev/null || echo FAIL)"
if [[ "$HEALTH" == *'"ok": true'* || "$HEALTH" == *'"ok":true'* ]]; then
  echo "  ✓ Application is responding and database is working"
else
  echo "  ✗ Health check failed — latest logs:"
  journalctl -u botyalla -n 30 --no-pager
  die "Deployment incomplete"
fi
# Same PATH as the service: this is what the app sees when it reads a receipt
( cd "$APP_DIR" && env -i PATH="$APP_DIR/venv/bin:/usr/local/bin:/usr/bin:/bin" "$APP_DIR/venv/bin/python" -c \
  'import payments as p; s = p.ocr_status(); print("  ✓ Receipt OCR:", s["langs"]) if s["ok"] else print("  ✗ Receipt OCR off:", s["reason"])' ) \
  || warn "Could not check receipt OCR"

if [[ -n "$DOMAIN" && "$DOMAIN" != "_" ]]; then
  log "HTTPS Configuration (Auto-fixing SSL)"
  apt-get install -y certbot python3-certbot-nginx >/dev/null 2>&1 || true
  
  # Remove old configs that might cause 502 due to stale proxy_pass
  rm -f /etc/nginx/sites-enabled/botyalla-le-ssl.conf
  rm -f /etc/nginx/sites-available/botyalla-le-ssl.conf
  systemctl reload nginx
  
  # Re-issue and configure Nginx automatically
  echo "  Securing $DOMAIN with Let's Encrypt..."
  certbot --nginx -d "$DOMAIN" -d "www.$DOMAIN" --non-interactive --agree-tos -m "info@youssefalsherief.tech" --redirect >/dev/null 2>&1 || warn "SSL setup failed. Run certbot manually."
fi

echo ""
echo "============================================================"
echo "  ✅ Deployment completed"
echo "  URL : http://${DOMAIN:-$(hostname -I | awk '{print $1}')}/"
if [[ "${NEW_CREDS:-0}" -eq 1 ]]; then
  echo ""
  echo "  🔐 Login credentials (displayed only once — save them now):"
  echo "     Username : admin"
  echo "     Password: $(grep '^ADMIN_PASS=' "$APP_DIR/.env" | cut -d= -f2-)"
  echo "     Change it immediately from the 'My Account' page."
fi
echo ""
echo "  Logs   : journalctl -u botyalla -f"
echo "  Update : bash $APP_DIR/deploy/hostinger_deploy.sh --update"
echo "============================================================"
