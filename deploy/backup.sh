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

mkdir -p "$DEST"

# نسخة متّسقة من SQLite: .backup آمن أثناء الكتابة، بعكس cp الذي قد يلتقط
# القاعدة في منتصف معاملة (خصوصاً مع WAL).
if [[ -f "$APP_DIR/botyalla.db" ]]; then
  sqlite3 "$APP_DIR/botyalla.db" ".backup '$DEST/db_$STAMP.sqlite'"
  gzip -f "$DEST/db_$STAMP.sqlite"
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

# احذف ما تجاوز مدة الاحتفاظ
find "$DEST" -type f -mtime "+$KEEP_DAYS" -delete 2>/dev/null || true

echo "[$(date -Is)] backup ok → $DEST (db + uploads + env), keeping ${KEEP_DAYS}d"

# ---------------------------------------------------------------------------
#  الاستعادة:
#    systemctl stop botyalla
#    gunzip -c /var/backups/botyalla/db_TIMESTAMP.sqlite.gz > /opt/botyalla/botyalla.db
#    tar -xzf /var/backups/botyalla/uploads_TIMESTAMP.tar.gz -C /opt/botyalla
#    chown -R botyalla:botyalla /opt/botyalla
#    systemctl start botyalla
#
#  مهم: هذه نسخة محلية على نفس القرص. انسخها خارج السيرفر دورياً
#  (rclone / scp إلى جهازك) وإلا فعطل القرص يأخذ النسخ معه.
# ---------------------------------------------------------------------------
