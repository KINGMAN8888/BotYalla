#!/usr/bin/env bash
# ============================================================================
#  BotYalla — الاستعادة من نسخة احتياطية
#
#  لماذا سكربت لا خطوات في ويكي: الاستعادة تحدث في أسوأ لحظة ممكنة — الخدمة
#  متوقفة، والعملاء يسألون، والوقت يمرّ. خطوة منسيّة هناك تكلّف أكثر من العطل
#  نفسه. هذا السكربت يفعل الترتيب الصحيح، ويرفض المضيّ لو بدت النسخة تالفة.
#
#  الاستعمال:
#     sudo deploy/restore.sh /var/backups/botyalla/db_2026-09-11_0300.sqlite.gz
#     sudo deploy/restore.sh <db.gz> <uploads.tar.gz>        # القاعدة والإيصالات
#     DRY_RUN=1 deploy/restore.sh <db.gz>                    # افحص بلا أي تغيير
#
#  **جرّبه على خادم اختبار قبل أن تحتاجه.** راجع docs/BACKUP_RESTORE.md.
# ============================================================================
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/botyalla}"
SERVICE="${SERVICE:-botyalla}"
OWNER="${OWNER:-botyalla:botyalla}"
DRY_RUN="${DRY_RUN:-0}"

DB_SRC="${1:-}"
UPLOADS_SRC="${2:-}"

die() { echo "❌ $*" >&2; exit 1; }
say() { echo "[$(date +%H:%M:%S)] $*"; }

[[ -n "$DB_SRC" ]] || die "مرّر ملف نسخة القاعدة. مثال: $0 /var/backups/botyalla/db_2026-09-11_0300.sqlite.gz"
[[ -f "$DB_SRC" ]] || die "الملف غير موجود: $DB_SRC"
command -v sqlite3 >/dev/null || die "sqlite3 غير مثبّت — بدونه لا فحص ولا استعادة موثوقة"

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

# ---- 1) افحص النسخة **قبل** لمس أي شيء ------------------------------------
# الترتيب هو كل شيء: نتأكد أن البديل سليم قبل أن نوقف الخدمة أو نزيح الأصل.
say "فحص النسخة…"
case "$DB_SRC" in
  *.gz) gunzip -c "$DB_SRC" > "$TMP/restore.db" || die "تعذّر فكّ الضغط — الملف تالف" ;;
  *)    cp "$DB_SRC" "$TMP/restore.db" ;;
esac

sqlite3 "$TMP/restore.db" "PRAGMA integrity_check;" | grep -qx "ok" \
  || die "النسخة فشلت في integrity_check — لا تستعدها. جرّب نسخة أقدم."

USERS="$(sqlite3 "$TMP/restore.db" "SELECT COUNT(*) FROM users;" 2>/dev/null || echo 0)"
BOTS="$(sqlite3 "$TMP/restore.db" "SELECT COUNT(*) FROM bots;" 2>/dev/null || echo 0)"
PAYS="$(sqlite3 "$TMP/restore.db" "SELECT COUNT(*) FROM payments;" 2>/dev/null || echo 0)"
[[ "${USERS:-0}" -ge 1 ]] || die "النسخة بلا مستخدمين — شبه مؤكّد أنها ليست قاعدة الإنتاج"

say "✅ النسخة سليمة: $USERS مستخدماً · $BOTS بوتاً · $PAYS دفعة"

if [[ -f "$APP_DIR/botyalla.db" ]]; then
  CUR_USERS="$(sqlite3 "$APP_DIR/botyalla.db" "SELECT COUNT(*) FROM users;" 2>/dev/null || echo "?")"
  say "الحالية على الخادم: $CUR_USERS مستخدماً"
  if [[ "$CUR_USERS" != "?" && "$USERS" -lt "$CUR_USERS" ]]; then
    say "⚠️  النسخة أقدم من الحالية ($USERS < $CUR_USERS مستخدماً) — ستفقد الفرق."
    if [[ "$DRY_RUN" != "1" ]]; then
      read -r -p "متأكد؟ اكتب YES للمتابعة: " ans
      [[ "$ans" == "YES" ]] || die "أُلغيت الاستعادة"
    fi
  fi
fi

if [[ "$DRY_RUN" == "1" ]]; then
  say "🔎 DRY_RUN — الفحص فقط، لم يُغيَّر شيء."
  exit 0
fi

# ---- 2) أوقف الخدمة -------------------------------------------------------
# الاستعادة فوق قاعدة مفتوحة تعطي ملفاً تالفاً. لا استثناء.
say "إيقاف $SERVICE…"
systemctl stop "$SERVICE" 2>/dev/null || say "(الخدمة ليست عاملة — نكمل)"

# ---- 3) أزِح الحالية جانباً — لا تحذفها ------------------------------------
# لو تبيّن أن النسخة خطأ، الرجوع خطوةٌ واحدة لا كارثة ثانية.
SAFE="$APP_DIR/botyalla.db.before-restore.$(date +%F_%H%M)"
if [[ -f "$APP_DIR/botyalla.db" ]]; then
  mv "$APP_DIR/botyalla.db" "$SAFE"
  say "أُزيحت الحالية إلى: $SAFE"
fi
# ملف WAL جزء من القاعدة الحالية لا فضلة: قد يحمل آخر المعاملات لو لم يكن
# الإيقاف نظيفاً. يُنقل مع نسختها الاحتياطية — لو حُذف صارت «نسخة الرجوع»
# ناقصة. وإزاحته من مكانه ضرورية: SQLite كان سيطبّقه على القاعدة المستعادة.
for ext in wal shm; do
  if [[ -f "$APP_DIR/botyalla.db-$ext" ]]; then
    mv "$APP_DIR/botyalla.db-$ext" "$SAFE-$ext"
  fi
done

# ---- 4) ضع النسخة ---------------------------------------------------------
cp "$TMP/restore.db" "$APP_DIR/botyalla.db"
say "وُضعت القاعدة المستعادة."

# ---- 5) الإيصالات (اختياري) -----------------------------------------------
if [[ -n "$UPLOADS_SRC" ]]; then
  [[ -f "$UPLOADS_SRC" ]] || die "ملف الإيصالات غير موجود: $UPLOADS_SRC"
  if [[ -d "$APP_DIR/uploads" ]]; then
    mv "$APP_DIR/uploads" "$APP_DIR/uploads.before-restore.$(date +%F_%H%M)"
  fi
  tar -xzf "$UPLOADS_SRC" -C "$APP_DIR"
  say "استُعيدت الإيصالات."
fi

# ---- 6) الملكية والتشغيل --------------------------------------------------
chown -R "$OWNER" "$APP_DIR" 2>/dev/null || say "⚠️ تعذّر ضبط الملكية ($OWNER) — اضبطها يدوياً"
say "تشغيل $SERVICE…"
systemctl start "$SERVICE"
sleep 3
systemctl is-active --quiet "$SERVICE" \
  && say "✅ الخدمة تعمل." \
  || die "الخدمة لم تبدأ. راجع: journalctl -u $SERVICE -n 50"

cat <<EOF

────────────────────────────────────────────────────────────
تمّت الاستعادة. الآن **تحقّق بنفسك** قبل أن تعلن أنها انتهت:
  1. افتح الموقع وسجّل الدخول.
  2. تأكد أن بوتاتك ظاهرة وشغّل واحداً.
  3. راجع آخر دفعة في لوحة الأدمن.
  4. FLASK_SECRET في .env لم يُلمس؟ لو تغيّر خرج كل المستخدمين.

الحالية قبل الاستعادة محفوظة في:
  $SAFE
لا تحذفها قبل أن تتأكد أن كل شيء سليم.
────────────────────────────────────────────────────────────
EOF
