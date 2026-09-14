#!/usr/bin/env bash
# ============================================================================
#  BotYalla — نسخ احتياطي يومي
#  ينسخ قاعدة البيانات وصور الإيصالات وملف البيئة، ويحتفظ بآخر 14 يوماً.
#  يُثبَّت في cron من سكربت النشر:  0 3 * * * /opt/botyalla/deploy/backup.sh
# ============================================================================
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/botyalla}"
DEST="${BACKUP_DIR:-/var/backups/botyalla}"
KEEP_DAYS="${KEEP_DAYS:-14}"
STAMP="$(date +%F_%H%M)"

# تحميل متغيرات البيئة بآمان لتفادي أخطاء صياغة Bash
if [[ -f "$APP_DIR/.env" ]]; then
  export RCLONE_REMOTE=$(grep '^RCLONE_REMOTE=' "$APP_DIR/.env" | cut -d= -f2- | tr -d '"' | tr -d "'")
  export ALERT_BOT_TOKEN=$(grep '^ALERT_BOT_TOKEN=' "$APP_DIR/.env" | cut -d= -f2- | tr -d '"' | tr -d "'")
  export ALERT_CHAT_ID=$(grep '^ALERT_CHAT_ID=' "$APP_DIR/.env" | cut -d= -f2- | tr -d '"' | tr -d "'")
fi

mkdir -p "$DEST"

# ---- التنبيه عند الفشل ------------------------------------------------------
# نسخة احتياطية تفشل بصمت في cron لثلاثة أسابيع هي أسوأ من لا نسخة: الأولى
# تعطيك طمأنينة كاذبة. أي خروج غير صفري هنا يرسل تنبيهاً إن ضُبط بوت التنبيه
# (ALERT_BOT_TOKEN + ALERT_CHAT_ID في بيئة التشغيل).
alert() {
  local msg="$1"
  echo "[$(date -Is)] ❌ $msg" >&2
  if [[ -n "${ALERT_BOT_TOKEN:-}" && -n "${ALERT_CHAT_ID:-}" ]]; then
    curl -sS -m 15 -o /dev/null \
      "https://api.telegram.org/bot${ALERT_BOT_TOKEN}/sendMessage" \
      -d "chat_id=${ALERT_CHAT_ID}" \
      --data-urlencode "text=🚨 فشل النسخ الاحتياطي لـBotYalla على $(hostname): ${msg}" || true
  fi
}
trap 'alert "توقّف السكربت عند السطر $LINENO"' ERR

# نسخة متّسقة من SQLite: .backup آمن أثناء الكتابة، بعكس cp الذي قد يلتقط
# القاعدة في منتصف معاملة (خصوصاً مع WAL).
if [[ -f "$APP_DIR/botyalla.db" ]]; then
  sqlite3 "$APP_DIR/botyalla.db" ".backup '$DEST/db_$STAMP.sqlite'"

  # ---- التحقّق قبل الضغط ---------------------------------------------------
  # **نسخة لم تُفحص ليست نسخة.** الفحص هنا يكشف القرص التالف أو النسخة
  # المقطوعة *اليوم*، لا يوم تحتاجها. وهو رخيص: ثوانٍ على قاعدة بهذا الحجم.
  if ! sqlite3 "$DEST/db_$STAMP.sqlite" "PRAGMA integrity_check;" | grep -qx "ok"; then
    alert "النسخة الجديدة فشلت في PRAGMA integrity_check — القاعدة أو القرص فيهما خلل"
    rm -f "$DEST/db_$STAMP.sqlite"
    exit 1
  fi

  # وفحص ثانٍ بمعنى تشغيلي: قاعدة سليمة بنيوياً لكن بلا مستخدمين تعني أننا
  # نسخنا ملفاً خطأً (قاعدة اختبار مثلاً) وسنكتشفها بعد أن نكون قد فقدنا الأصل.
  USERS="$(sqlite3 "$DEST/db_$STAMP.sqlite" "SELECT COUNT(*) FROM users;" 2>/dev/null || echo 0)"
  if [[ "${USERS:-0}" -lt 1 ]]; then
    alert "النسخة الجديدة سليمة بنيوياً لكنها بلا مستخدمين — تأكّد أن APP_DIR يشير للإنتاج"
    rm -f "$DEST/db_$STAMP.sqlite"
    exit 1
  fi

  gzip -f "$DEST/db_$STAMP.sqlite"
  echo "[$(date -Is)] db ok — integrity_check نجح، $USERS مستخدماً"
fi

# الإيصالات — دليل الدفع، فقدانها يعني فقدان القدرة على مراجعة أي نزاع
if [[ -d "$APP_DIR/uploads" ]]; then
  tar -czf "$DEST/uploads_$STAMP.tar.gz" -C "$APP_DIR" uploads
fi

# .env يحوي FLASK_SECRET — بدونه تُبطَل كل الجلسات عند الاستعادة
if [[ -f "$APP_DIR/.env" ]]; then
  cp "$APP_DIR/.env" "$DEST/env_$STAMP.bak"
  chmod 600 "$DEST/env_$STAMP.bak"
fi

# مفتاح تشفير توكنات البوتات (لو لم يُضبط FERNET_KEY في .env). قاعدة بلا مفتاحها
# تُستعاد سليمةً لكن توكنات بوتاتها لا تُقرأ — فالمفتاح يُنسخ مع القاعدة دائماً.
if [[ -f "$APP_DIR/.token.key" ]]; then
  cp "$APP_DIR/.token.key" "$DEST/token_$STAMP.key"
  chmod 600 "$DEST/token_$STAMP.key"
fi

# احذف ما تجاوز مدة الاحتفاظ — **بعد** أن نجحت نسخة اليوم لا قبلها.
# الترتيب مقصود: لو فشل الفحص أعلاه خرجنا بـexit 1 ولم نصل هنا، فتبقى نسخ
# الأمس. حذفٌ يسبق نسخةً ناجحة قد يترك الخادم بلا أي نسخة إطلاقاً.
find "$DEST" -type f -mtime "+$KEEP_DAYS" -delete 2>/dev/null || true

echo "[$(date -Is)] backup ok → $DEST (db + uploads + env), keeping ${KEEP_DAYS}d"

# -- نسخ خارجي (اختياري) --
# للنسخ لـ Google Drive مثلاً:
# 1. ثبّت rclone: curl https://rclone.org/install.sh | bash
# 2. قم بإعداده: rclone config (وسمّي الوجهة gdrive)
# 3. عيّن المتغير RCLONE_REMOTE="gdrive:botyalla_backups" في بيئة التشغيل أو هنا:
# RCLONE_REMOTE="gdrive:botyalla_backups"

if [[ -n "${RCLONE_REMOTE:-}" ]] && command -v rclone &> /dev/null; then
  echo "[$(date -Is)] syncing to external remote: $RCLONE_REMOTE"
  rclone sync "$DEST" "$RCLONE_REMOTE"
  echo "[$(date -Is)] external sync ok"
fi

trap - ERR

# ---------------------------------------------------------------------------
#  الاستعادة: استعمل `deploy/restore.sh` — لا تستعد يدوياً تحت الضغط.
#      sudo deploy/restore.sh /var/backups/botyalla/db_2026-09-11_0300.sqlite.gz
#
#  والأهم: **جرّب الاستعادة على خادم اختبار مرّة كل شهر.** الدليل الكامل
#  والبروفة في `docs/BACKUP_RESTORE.md`. نسخة لم تُستعَد مرّةً واحدة هي
#  فرضية لا خطّة.
#
#  مهم: هذه نسخة محلية على نفس القرص. اضبط RCLONE_REMOTE لتخرج عن الخادم،
#  وإلا فعطل القرص يأخذ النسخ معه.
# ---------------------------------------------------------------------------
