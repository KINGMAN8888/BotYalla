"""BotYalla — قاعدة البيانات (SQLite).
جداول: users (لوحة التحكم)، bots، bot_users (مشتركو كل بوت للبث)،
leads، orders، bookings، events (للتحليلات)."""
import sqlite3, json, os, re, time, logging, hmac, hashlib
import urllib.parse
from contextlib import contextmanager

log = logging.getLogger("database")

# ============================================================================
#  تشفير توكنات البوتات في القاعدة (Fernet)
# ============================================================================
# التوكن مفتاح تشغيل البوت كاملاً — نسخة مسرّبة من القاعدة يجب ألا تسلّم بوتات العملاء.
# · المفتاح من FERNET_KEY في .env، وإلا ملف `.token.key` يُولَّد مرة بجانب القاعدة
#   (خارج Git · صلاحية 600 · يُنسخ احتياطياً مع .env). **لا مفتاح مكتوب في الكود.**
# · Fernet عشوائي: نفس التوكن يُشفَّر كل مرة بنص مختلف، فالبحث بالتوكن (ويبهوك واتساب
#   بـ`wa:<phone_id>`) ومنع إضافة نفس البوت مرتين يمرّان بفهرس أعمى حتمي
#   `token_idx` = HMAC-SHA256(التوكن). بدونه يضيع كل وارد واتساب بصمت.
# · المفتاح الذي كان مكتوباً في الكود سابقاً يُقبل **للقراءة فقط** ويُدوَّر عند التهجير.
# · فشل فكّ التشفير (مفتاح خاطئ) يُسجَّل ويرجّع توكناً فارغاً — يفشل مغلقاً، فلا يُرسل
#   نص مشفّر إلى تليجرام على أنه توكن.
try:
    from cryptography.fernet import Fernet, MultiFernet, InvalidToken
except ImportError:          # بيئة بلا المكتبة: التوكنات تبقى كما هي
    Fernet = MultiFernet = None
    class InvalidToken(Exception): pass

_ENC_PREFIX = "gAAAAA"      # كل رمز Fernet يبدأ بها؛ توكن تليجرام يبدأ بأرقام وواتساب بـ wa:
_LEGACY_KEY = b"Ym90eWFsbGEtZGV2LXNlY3JldC1mZXJuZXQta2V5LTE="   # كان مكتوباً في الكود — قراءة فقط
_seclog = logging.getLogger("security")
_crypto_cache = {}


def _key_path():
    return os.environ.get("BOTYALLA_KEYFILE") or os.path.join(
        os.path.dirname(os.path.abspath(DB_PATH)), ".token.key")


def _load_key():
    k = (os.environ.get("FERNET_KEY") or "").strip()
    if k:
        return k.encode()
    path = _key_path()
    try:
        with open(path, "rb") as f:
            return f.read().strip()
    except FileNotFoundError:
        pass
    key = Fernet.generate_key()
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as f:
            f.write(key)
        _seclog.warning("FERNET_KEY is not set — generated %s. Back it up with .env: "
                        "without it, stored bot tokens cannot be read.", path)
        return key
    except FileExistsError:                  # عملية أخرى أنشأته للتو
        with open(path, "rb") as f:
            return f.read().strip()


def _crypto():
    """(MultiFernet, Fernet الحالي, مفتاح الفهرس) — يُحمَّل عند أول حاجة لا عند
    الاستيراد، فيحترم .env الذي يحمّله app.py وقاعدة الاختبار المؤقتة.
    مفتاح بصيغة فاسدة يرمي هنا عند أول استعمال (init_db) — يفشل عالياً لا بصمت."""
    if Fernet is None:
        return None, None, None
    c = _crypto_cache.get("k")
    if c is None:
        key = _load_key()
        primary = Fernet(key)
        keys = [primary] + ([Fernet(_LEGACY_KEY)] if key != _LEGACY_KEY else [])
        idx_key = hashlib.sha256(b"botyalla-token-index\0" + key).digest()
        c = _crypto_cache["k"] = (MultiFernet(keys), primary, idx_key)
    return c


def _encrypt(token):
    if not token:
        return token
    multi, _, _ = _crypto()
    if multi is None or token.startswith(_ENC_PREFIX):
        return token
    return multi.encrypt(token.encode()).decode()


def _decrypt(token):
    if not token or not token.startswith(_ENC_PREFIX):
        return token
    multi, _, _ = _crypto()
    if multi is None:
        return ""
    try:
        return multi.decrypt(token.encode()).decode()
    except InvalidToken:
        _seclog.error("a bot token could not be decrypted — is FERNET_KEY the key it was stored with?")
        return ""


def seal(value):
    """ختم سرّ داخل إعداد البوت (توكن صفحة فيسبوك) بنفس مفتاح توكنات البوتات."""
    return _encrypt(value) if value else value


def unseal(value):
    return _decrypt(value) if value else ""


def _token_idx(token):
    """فهرس أعمى حتمي: نفس التوكن ← نفس القيمة، ولا يُستخرج منه التوكن."""
    token = (token or "").strip()
    _, _, k = _crypto()
    if not token or k is None:
        return None
    return hmac.new(k, token.encode(), hashlib.sha256).hexdigest()


def _map_bot(r):
    if not r: return r
    b = dict(r)
    b["token"] = _decrypt(b.get("token", ""))
    b.pop("token_idx", None)
    return b

# سجل الأحداث المالية (بتّ الدفعات والتفعيل وحرق الأكواد) — يصل ملف السجل عبر root.
log = logging.getLogger("billing")

# BOTYALLA_DB يسمح للاختبارات بالعمل على قاعدة مؤقتة بدل قاعدة الإنتاج.
DB_PATH = os.environ.get("BOTYALLA_DB", "botyalla.db")

# معرّف «الباقة» لدفعات شحن المحفظة. ليس باقة حقيقية: خارج `plans.PLANS`
# فـ`plans.is_sellable` ترفضه ولا يُباع من صفحة الأسعار، و`finalize_payment`
# تميّزه فتشحن الرصيد بدل أن تفعّل اشتراكاً.
WALLET_PLAN = "__wallet__"

@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    # gunicorn يشغّل 4 خيوط: بدون مهلة انتظار يرمي "database is locked" فوراً
    # عند أي تزاحم على الكتابة بدل أن ينتظر لحظة.
    conn.execute("PRAGMA busy_timeout=15000")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()

@contextmanager
def _conn_or(c):
    """يعمل على اتصال قائم إن مُرّر، وإلا يفتح اتصاله الخاص.

    يسمح بتركيب عدة دوال داخل **معاملة واحدة** (مثل تسوية الدفعة) دون أن تفقد
    أيٌّ منها قدرتها على العمل وحدها. عند تمرير `c` لا تُنفَّذ commit هنا —
    صاحب الاتصال هو من يبتّ الأمر، فإما تنجح الخطوات كلها أو لا شيء منها."""
    if c is not None:
        yield c
    else:
        with get_conn() as own:
            yield own


def _migrate(c):
    cols = {r[1] for r in c.execute("PRAGMA table_info(users)").fetchall()}
    if "role" not in cols:
        c.execute("ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT 'user'")
    if "is_blocked" not in cols:
        c.execute("ALTER TABLE users ADD COLUMN is_blocked INTEGER NOT NULL DEFAULT 0")
    if "ref_by" not in cols:                      # كود الأفيليت الذي جاء منه المستخدم
        c.execute("ALTER TABLE users ADD COLUMN ref_by TEXT")
    if "email" not in cols:                       # اختياري: استرجاع الحساب والإيصالات
        c.execute("ALTER TABLE users ADD COLUMN email TEXT")
    # نظام الحساب (2026-09-15): الهاتف وتأكيده، تأكيد البريد، السن، نوع الكيان.
    # verify_required=1 للحسابات الجديدة وحدها — القديمة تبقى تعمل بلا تأكيد إجباري.
    # فريق الحساب (2026-09-25): الموظف يعمل داخل حساب صاحب العمل، فـ`works_for` يحدّد
    # «الحساب الفعّال» لكل استعلامات البوتات. NULL = يعمل في حسابه هو.
    for col, ddl in (("phone", "TEXT"), ("phone_verified_at", "INTEGER"),
                     ("email_verified_at", "INTEGER"), ("verify_required", "INTEGER NOT NULL DEFAULT 0"),
                     ("age", "INTEGER"), ("entity_type", "TEXT"),
                     ("works_for", "INTEGER"), ("team_role", "TEXT")):
        if col not in cols:
            c.execute(f"ALTER TABLE users ADD COLUMN {col} {ddl}")
    c.execute("CREATE UNIQUE INDEX IF NOT EXISTS ix_users_phone ON users(phone) WHERE phone IS NOT NULL")
    # فهرس جزئي: الإيميل فريد إن وُجد، والحسابات القديمة بلا إيميل (NULL) لا تتعارض.
    c.execute("CREATE UNIQUE INDEX IF NOT EXISTS ix_users_email ON users(email) WHERE email IS NOT NULL")
    # أول مستخدم = admin دائماً
    c.execute("UPDATE users SET role='admin' WHERE id=1 AND role<>'admin'")
    # تحصيل مدفوعات عملاء البوت (إضافة لكل بوت): حالة دفع الطلب
    # NULL = بلا تحصيل · awaiting (ينتظر الإيصال) · pending (للمراجعة) · paid · rejected
    ocols = {r[1] for r in c.execute("PRAGMA table_info(orders)").fetchall()}
    if "pay_status" not in ocols:
        c.execute("ALTER TABLE orders ADD COLUMN pay_status TEXT")
    # الشحن (2026-09-22): كان التاجر يضيفه «منتجاً» في الكتالوج ليظهر سعره، فيُحسب
    # بالعدد أو يُتخطّى. صار إعداداً في مساره: قيمته ومنطقته تُحفظان مع الطلب.
    if "shipping" not in ocols:
        c.execute("ALTER TABLE orders ADD COLUMN shipping REAL NOT NULL DEFAULT 0")
    if "ship_zone" not in ocols:
        c.execute("ALTER TABLE orders ADD COLUMN ship_zone TEXT")

    pcols = {r[1] for r in c.execute("PRAGMA table_info(payments)").fetchall()}
    if "promo_id" not in pcols:                   # الكود المستخدم وقيمة الخصم وقت الدفع
        c.execute("ALTER TABLE payments ADD COLUMN promo_id INTEGER")
    if "discount" not in pcols:
        c.execute("ALTER TABLE payments ADD COLUMN discount REAL NOT NULL DEFAULT 0")
    if "base_amount" not in pcols:                # السعر قبل أي خصم (للتدقيق)
        c.execute("ALTER TABLE payments ADD COLUMN base_amount REAL")

    # Whatsapp integration (Phase 1/2)
    bcols = {r[1] for r in c.execute("PRAGMA table_info(bots)").fetchall()}
    if "channel" not in bcols:
        c.execute("ALTER TABLE bots ADD COLUMN channel TEXT NOT NULL DEFAULT 'telegram'")

    # تنبيه «عميل ينتظر رداً»: وقت آخر تنبيه أُرسل عن هذه المحادثة
    vcols = {r[1] for r in c.execute("PRAGMA table_info(conversations)").fetchall()}
    if vcols and "waiting_alert_at" not in vcols:
        c.execute("ALTER TABLE conversations ADD COLUMN waiting_alert_at INTEGER")

    ucols = {r[1] for r in c.execute("PRAGMA table_info(bot_users)").fetchall()}
    if "peer" not in ucols:
        c.execute("ALTER TABLE bot_users ADD COLUMN peer TEXT")
        c.execute("UPDATE bot_users SET peer='tg:'||tg_user_id WHERE peer IS NULL")
    if "last_in_at" not in ucols:
        # آخر رسالة واردة من العميل — واتساب يمنع المراسلة الحرة بعد 24 ساعة منها.
        c.execute("ALTER TABLE bot_users ADD COLUMN last_in_at INTEGER")
        c.execute("UPDATE bot_users SET last_in_at=created_at WHERE last_in_at IS NULL")
    if "opted_out" not in ucols:
        # العميل طلب إيقاف الرسائل الترويجية (STOP) — سياسة Meta: لا حملات له بعدها.
        c.execute("ALTER TABLE bot_users ADD COLUMN opted_out INTEGER NOT NULL DEFAULT 0")
    if "optin_at" not in ucols:
        # موافقة صريحة على العروض («أيوه ابعتلي») — أساس قائمة تسويق نظيفة بسياسة Meta
        c.execute("ALTER TABLE bot_users ADD COLUMN optin_at INTEGER")

    # ---- الدورة الفوترية (شهري/سنوي) ----
    # الافتراضي 'monthly' فكل صفّ قائم يبقى على ما هو عليه بلا لمس.
    scols = {r[1] for r in c.execute("PRAGMA table_info(subscriptions)").fetchall()}
    if "billing_cycle" not in scols:
        c.execute("ALTER TABLE subscriptions ADD COLUMN "
                  "billing_cycle TEXT NOT NULL DEFAULT 'monthly'")
    pcols = {r[1] for r in c.execute("PRAGMA table_info(payments)").fetchall()}
    if "billing_cycle" not in pcols:
        c.execute("ALTER TABLE payments ADD COLUMN "
                  "billing_cycle TEXT NOT NULL DEFAULT 'monthly'")

    # ---- الباقات الجديدة: لا ترحيل، وهذا مقصود ----
    # الباقتان القديمتان (`pro` / `business`) تبقيان في `plans.PLANS` بحدودهما
    # الأصلية وخارج `plans.ORDER`. السبب: `pro` كانت تشمل واتساب و`merchant`
    # لا تشمله، و`business` كانت بلا حدّ للبوتات — فأي ترحيل يسحب من مشتركٍ
    # ميزةً دفع مقابلها. لا صفّ اشتراك أو دفعة يُلمس هنا إطلاقاً.

    # ---- تشفير التوكن + الفهرس الأعمى (راجع أعلى الملف) ----
    # كل تشغيل: يُشفَّر ما بقي نصاً، ويُدوَّر ما شُفّر بالمفتاح القديم المكتوب في الكود،
    # ويُملأ token_idx. الصفوف السليمة لا تُلمس (لا كتابة بلا تغيير).
    bcols = {r[1] for r in c.execute("PRAGMA table_info(bots)").fetchall()}
    if "token_idx" not in bcols:
        c.execute("ALTER TABLE bots ADD COLUMN token_idx TEXT")
    multi, primary, _ = _crypto()
    for row in c.execute("SELECT id, token, token_idx FROM bots").fetchall():
        stored = row["token"] or ""
        plain = _decrypt(stored)
        if not plain:
            continue                       # لم يُفكّ (مفتاح خاطئ) — لا نكتب فوقه أبداً
        enc = stored
        if multi is not None:
            if not stored.startswith(_ENC_PREFIX):
                enc = _encrypt(plain)
            else:
                try:
                    primary.decrypt(stored.encode())
                except InvalidToken:
                    enc = multi.rotate(stored.encode()).decode()   # مفتاح قديم ← الحالي
        idx = _token_idx(plain)
        if enc != stored or idx != row["token_idx"]:
            c.execute("UPDATE bots SET token=?, token_idx=? WHERE id=?", (enc, idx, row["id"]))
    try:
        c.execute("CREATE UNIQUE INDEX IF NOT EXISTS ix_bots_token_idx ON bots(token_idx) "
                  "WHERE token_idx IS NOT NULL")
    except sqlite3.IntegrityError:
        # قاعدة قديمة فيها نفس التوكن مرتين: البحث يعمل، والتكرار يُمنع عند الإنشاء في التطبيق
        log.error("duplicate bot tokens found — ix_bots_token_idx created non-unique")
        c.execute("CREATE INDEX IF NOT EXISTS ix_bots_token_idx_nu ON bots(token_idx)")

def init_db():
    with get_conn() as c:
        # WAL: يسمح بقراءات متزامنة مع الكتابة. إعداد دائم يُضبط مرة واحدة.
        c.execute("PRAGMA journal_mode=WAL")
        c.execute("PRAGMA synchronous=NORMAL")
        c.executescript("""
        CREATE TABLE IF NOT EXISTS users(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            pw_hash  TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'user',       -- admin | support | user
            is_blocked INTEGER NOT NULL DEFAULT 0,
            email TEXT,                              -- اختياري؛ فريد إن وُجد (ix_users_email)
            created_at INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS settings(
            user_id INTEGER NOT NULL,
            key TEXT NOT NULL,
            value TEXT,
            PRIMARY KEY(user_id, key),
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS bots(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            owner_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            token TEXT NOT NULL UNIQUE,          -- مشفّر (Fernet) — لا يُبحث به مباشرة
            token_idx TEXT,                      -- HMAC للتوكن: البحث ومنع التكرار
            template TEXT NOT NULL,              -- flow | store | booking | customer_service
            config_json TEXT NOT NULL DEFAULT '{}',
            is_active INTEGER NOT NULL DEFAULT 0,
            created_at INTEGER NOT NULL,
            FOREIGN KEY(owner_id) REFERENCES users(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS bot_users(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bot_id INTEGER NOT NULL,
            tg_user_id INTEGER NOT NULL,
            first_name TEXT,
            created_at INTEGER NOT NULL,
            UNIQUE(bot_id, tg_user_id),
            FOREIGN KEY(bot_id) REFERENCES bots(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS leads(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bot_id INTEGER NOT NULL, tg_user_id INTEGER,
            data_json TEXT, created_at INTEGER NOT NULL,
            FOREIGN KEY(bot_id) REFERENCES bots(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS orders(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bot_id INTEGER NOT NULL, tg_user_id INTEGER,
            customer TEXT, phone TEXT, address TEXT,
            items_json TEXT, total REAL, status TEXT DEFAULT 'new',
            created_at INTEGER NOT NULL,
            FOREIGN KEY(bot_id) REFERENCES bots(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS bookings(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bot_id INTEGER NOT NULL, tg_user_id INTEGER,
            customer TEXT, phone TEXT, service TEXT,
            slot TEXT,                            -- 'YYYY-MM-DD HH:MM'
            status TEXT DEFAULT 'booked',
            created_at INTEGER NOT NULL,
            UNIQUE(bot_id, slot),
            FOREIGN KEY(bot_id) REFERENCES bots(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS subscriptions(
            user_id INTEGER PRIMARY KEY,
            plan TEXT NOT NULL DEFAULT 'free',
            status TEXT NOT NULL DEFAULT 'active',   -- active | expired
            started_at INTEGER, expires_at INTEGER,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS payments(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            plan TEXT NOT NULL,
            method TEXT,                              -- vodafone | instapay | bank
            amount REAL,
            ref TEXT,                                 -- transaction ref entered by user
            screenshot TEXT,                          -- filename in uploads/
            img_hash TEXT,
            auto_check TEXT,                          -- JSON of automated checks
            status TEXT NOT NULL DEFAULT 'pending',   -- pending | approved | rejected
            admin_msg_id INTEGER,
            created_at INTEGER NOT NULL,
            decided_at INTEGER,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS platform(
            key TEXT PRIMARY KEY, value TEXT
        );
        CREATE TABLE IF NOT EXISTS bot_requests(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            username TEXT,
            business TEXT,
            description TEXT,
            budget TEXT,
            contact TEXT,
            status TEXT NOT NULL DEFAULT 'new',   -- new | in_progress | done | rejected
            created_at INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS chat_state(
            bot_id      INTEGER NOT NULL,
            peer        TEXT NOT NULL,        -- tg:12345  |  wa:201001234567
            step        INTEGER NOT NULL DEFAULT 0,
            data_json   TEXT NOT NULL DEFAULT '{}',
            updated_at  INTEGER NOT NULL,
            PRIMARY KEY(bot_id, peer),
            FOREIGN KEY(bot_id) REFERENCES bots(id) ON DELETE CASCADE
        );
        -- استهلاك الرسائل شهرياً. واتساب مدفوع لكل رسالة، فبلا هذا العدّاد
        -- قد يكلّف عميل واحد نشط أكثر من قيمة اشتراكه.
        CREATE TABLE IF NOT EXISTS usage_msgs(
            bot_id      INTEGER NOT NULL,
            owner_id    INTEGER NOT NULL,
            month       TEXT NOT NULL,           -- 'YYYY-MM'
            sent        INTEGER NOT NULL DEFAULT 0,
            received    INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY(bot_id, month),
            FOREIGN KEY(bot_id) REFERENCES bots(id) ON DELETE CASCADE
        );
        -- محفظة رصيد الرسائل التسويقية. الرسالة التسويقية في مصر ≈ 3.12ج،
        -- فأربعون رسالة تلتهم باقة التاجر كاملة — إدراجها في باقة نزيف مضمون.
        -- **الوحدة قرش (عدد صحيح)**: لا عشريات عائمة في المال إطلاقاً.
        CREATE TABLE IF NOT EXISTS wallet(
            owner_id   INTEGER PRIMARY KEY,
            balance    INTEGER NOT NULL DEFAULT 0,     -- بالقروش، لا يقلّ عن صفر أبداً
            updated_at INTEGER NOT NULL,
            FOREIGN KEY(owner_id) REFERENCES users(id) ON DELETE CASCADE
        );
        -- كل حركة على المحفظة تُقيَّد هنا. الرصيد أعلاه مجرّد مجموع مُخزَّن
        -- يُحدَّث في نفس المعاملة، فأي شكّ يُحسم بإعادة جمع هذا السجل.
        CREATE TABLE IF NOT EXISTS wallet_ledger(
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            owner_id   INTEGER NOT NULL,
            delta      INTEGER NOT NULL,               -- موجب شحن · سالب خصم
            kind       TEXT NOT NULL,                  -- topup | spend | refund | adjust
            ref        TEXT,                           -- مرجع الحملة أو الدفعة
            note       TEXT,
            balance_after INTEGER NOT NULL,
            created_at INTEGER NOT NULL,
            FOREIGN KEY(owner_id) REFERENCES users(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS ix_ledger_owner ON wallet_ledger(owner_id, id DESC);
        -- Meta تُعيد إرسال الويبهوك عند أي تأخّر أو فشل. بلا هذا الجدول
        -- تُعالَج الإجابة مرتين ويتقدّم الفلو خطوة زائدة.
        CREATE TABLE IF NOT EXISTS seen_msgs(
            msg_id     TEXT PRIMARY KEY,
            created_at INTEGER NOT NULL
        );
        -- وسائط العملاء (صور/صوت). الملف على القرص والسجل هنا.
        -- lead_id يُملأ عند انتهاء الفلو؛ ما يبقى NULL هو ملف يتيم يُنظَّف لاحقاً.
        CREATE TABLE IF NOT EXISTS media(
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            bot_id      INTEGER NOT NULL,
            owner_id    INTEGER NOT NULL,
            peer        TEXT NOT NULL,
            lead_id     INTEGER,
            kind        TEXT NOT NULL,        -- image | audio | video | document
            mime        TEXT,
            size        INTEGER NOT NULL DEFAULT 0,
            fname       TEXT NOT NULL,        -- اسم مولَّد داخلياً، لا اسم العميل
            caption     TEXT,
            created_at  INTEGER NOT NULL,
            FOREIGN KEY(bot_id) REFERENCES bots(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS ix_media_bot ON media(bot_id, created_at);
        CREATE TABLE IF NOT EXISTS events(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bot_id INTEGER NOT NULL,
            kind TEXT NOT NULL,                   -- start | lead | order | booking
            value REAL DEFAULT 0,
            day TEXT NOT NULL,                    -- 'YYYY-MM-DD'
            created_at INTEGER NOT NULL,
            FOREIGN KEY(bot_id) REFERENCES bots(id) ON DELETE CASCADE
        );

        -- ===================== التسعير والعروض (مالك المنصة) =====================
        -- تجاوزات سعر الباقة. الأساس يبقى في plans.py؛ هذا يعلوه عند وجوده.
        CREATE TABLE IF NOT EXISTS plan_overrides(
            plan_id TEXT PRIMARY KEY,
            price REAL,                           -- NULL = استخدم سعر plans.py
            discount_pct REAL NOT NULL DEFAULT 0, -- خصم معلن على الباقة 0..90
            updated_at INTEGER NOT NULL
        );

        CREATE TABLE IF NOT EXISTS promos(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT NOT NULL UNIQUE,            -- يُخزَّن UPPERCASE
            kind TEXT NOT NULL DEFAULT 'percent', -- percent | fixed
            value REAL NOT NULL,
            plan TEXT,                            -- NULL = كل الباقات
            max_uses INTEGER,                     -- NULL = بلا حد
            used INTEGER NOT NULL DEFAULT 0,
            per_user_once INTEGER NOT NULL DEFAULT 1,
            expires_at INTEGER,
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at INTEGER NOT NULL
        );

        -- استهلاك الكود يُسجَّل عند **الموافقة** لا عند الإرسال
        CREATE TABLE IF NOT EXISTS promo_uses(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            promo_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            payment_id INTEGER,
            created_at INTEGER NOT NULL,
            UNIQUE(promo_id, payment_id),
            FOREIGN KEY(promo_id) REFERENCES promos(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS affiliates(
            user_id INTEGER PRIMARY KEY,
            code TEXT NOT NULL UNIQUE,
            rate_pct REAL NOT NULL DEFAULT 20,
            total_earned REAL NOT NULL DEFAULT 0,
            paid_out REAL NOT NULL DEFAULT 0,
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at INTEGER NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        );

        -- إحالة واحدة لكل مُحال. العمولة تُحتسب عند اعتماد الدفعة فقط.
        CREATE TABLE IF NOT EXISTS referrals(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            affiliate_user_id INTEGER NOT NULL,
            referred_user_id INTEGER NOT NULL UNIQUE,
            payment_id INTEGER,
            commission REAL NOT NULL DEFAULT 0,
            converted_at INTEGER,
            created_at INTEGER NOT NULL,
            FOREIGN KEY(affiliate_user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY(referred_user_id) REFERENCES users(id) ON DELETE CASCADE
        );

        -- سجل أحداث صفحات فيسبوك/إنستجرام غير الرسائل (تسليم المحادثة · تفاعلات · تعليقات ·
        -- سياسات…) — يُعرض في «/admin/meta». يُقصّ لآخر 3000 حدث (log_meta_event).
        CREATE TABLE IF NOT EXISTS meta_events(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bot_id INTEGER,
            account TEXT NOT NULL,             -- fb:<page_id> · ig:<ig_user_id>
            kind TEXT NOT NULL,
            peer TEXT,
            summary TEXT,
            created_at INTEGER NOT NULL
        );

        -- «فريقنا يجهّزه لك»: إذن العميل لفريق المنصة بالعمل داخل حسابه (البوتات فقط) لمدة محدودة.
        -- via: user (العميل ضغط الموافقة) · staff (موظف سجّل موافقة أخذها من العميل — مع ملاحظة إلزامية).
        CREATE TABLE IF NOT EXISTS setup_grants(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            via TEXT NOT NULL,
            note TEXT,
            staff_id INTEGER,
            created_at INTEGER NOT NULL,
            expires_at INTEGER NOT NULL,
            revoked_at INTEGER
        );
        CREATE INDEX IF NOT EXISTS idx_grants_user ON setup_grants(user_id, expires_at);
        -- سجل تدقيق: كل ما فعله موظف داخل حساب عميل — يراه العميل والأدمن
        CREATE TABLE IF NOT EXISTS staff_actions(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            staff_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            bot_id INTEGER,
            action TEXT NOT NULL,
            detail TEXT,
            created_at INTEGER NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_staff_actions_user ON staff_actions(user_id, id);

        -- عميل واتساب برقم مخفي (اسم مستخدم): معرّفه الخاص بالنشاط (BSUID) ← رقمه إن ظهر مرة،
        -- فتبقى محادثته واحدة حين يظهر الرقم ثم يختفي (نافذة الـ30 يوماً عند Meta).
        CREATE TABLE IF NOT EXISTS wa_user_ids(
            bsuid TEXT PRIMARY KEY,
            phone TEXT NOT NULL,
            updated_at INTEGER NOT NULL
        );

        -- روابط «التسجيل السهل»: يصدرها الأدمن لعميل لا يستطيع الوصول لكود البريد، فيسجّل
        -- بلا تأكيد إجباري على مسؤولية الأدمن. التوكن لا يُخزَّن (hash فقط)، والرابط لمرة واحدة.
        CREATE TABLE IF NOT EXISTS signup_invites(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            token_hash TEXT NOT NULL UNIQUE,
            note TEXT,
            created_by INTEGER,
            created_at INTEGER NOT NULL,
            expires_at INTEGER NOT NULL,
            claimed_at INTEGER,
            used_by INTEGER,
            revoked INTEGER NOT NULL DEFAULT 0
        );

        -- عمولات التجديد (بعد أول دفعة) — سطر لكل دفعة معتمدة داخل سقف الـ12 شهراً.
        -- UNIQUE(payment_id) هو حارس الازدواج: اعتماد نفس الدفعة مرتين (ويب + زرّ تليجرام)
        -- لا يحتسب عمولتها مرتين.
        CREATE TABLE IF NOT EXISTS affiliate_commissions(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            referral_id INTEGER NOT NULL,
            affiliate_user_id INTEGER NOT NULL,
            referred_user_id INTEGER NOT NULL,
            payment_id INTEGER NOT NULL UNIQUE,
            amount REAL NOT NULL,
            commission REAL NOT NULL,
            created_at INTEGER NOT NULL,
            FOREIGN KEY(referral_id) REFERENCES referrals(id) ON DELETE CASCADE
        );

        -- سجل التذكيرات: يمنع تكرار إرسال نفس التذكير لنفس المستخدم في نفس الدورة.
        CREATE TABLE IF NOT EXISTS reminder_log(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            kind TEXT NOT NULL,          -- 'pre3' | 'pre1' | 'expired'
            sent_at INTEGER NOT NULL,
            UNIQUE(user_id, kind),
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        );
        -- روابط استرجاع كلمة المرور. تُخزَّن **تجزئة** التوكن لا التوكن: تسريب
        -- القاعدة يجب ألا يعطي مفاتيح دخول صالحة.
        CREATE TABLE IF NOT EXISTS password_resets(
            token_hash TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            created_at INTEGER NOT NULL,
            expires_at INTEGER NOT NULL,
            used_at INTEGER,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        );

        -- ===================== إنشاء بوت بضغطة (Telegram Managed Bots) =====================
        -- الرابط يُفتح في بوت المنصة بكود لمرة واحدة. الكود يربط حساب تليجرام بحساب
        -- المنصة **قبل** الإنشاء، لأن تحديث managed_bot يحمل معرّف تليجرام لا حسابنا.
        -- تُخزَّن تجزئة الكود لا الكود (نفس نمط password_resets).
        CREATE TABLE IF NOT EXISTS managed_bot_requests(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            token_hash TEXT NOT NULL UNIQUE,
            user_id INTEGER NOT NULL,
            template TEXT NOT NULL,
            business_name TEXT NOT NULL,
            suggested_username TEXT,
            tg_user_id INTEGER,                    -- يُملأ حين يفتح المستخدم الرابط
            bot_id INTEGER,                        -- يُملأ عند الإنشاء
            status TEXT NOT NULL DEFAULT 'pending',-- pending | linked | created | failed
            error TEXT,
            created_at INTEGER NOT NULL,
            expires_at INTEGER NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS ix_mbr_tg ON managed_bot_requests(tg_user_id, status);

        -- ===================== الدعم والشكاوى (support_desk.py) =====================
        -- كل رسالة تصل الأدمن فوراً على بوت المنصة بالوسم #T<id>، ورده (Reply) يرجع هنا.
        CREATE TABLE IF NOT EXISTS tickets(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            kind TEXT NOT NULL DEFAULT 'support',  -- support | complaint | payment | other
            subject TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'open',   -- open | answered | closed
            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS ix_tickets_user ON tickets(user_id, updated_at);
        CREATE TABLE IF NOT EXISTS ticket_msgs(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticket_id INTEGER NOT NULL,
            sender TEXT NOT NULL,                  -- user | staff
            body TEXT NOT NULL,
            via TEXT NOT NULL DEFAULT 'web',       -- web | telegram
            created_at INTEGER NOT NULL,
            FOREIGN KEY(ticket_id) REFERENCES tickets(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS ix_ticket_msgs ON ticket_msgs(ticket_id);

        -- ===================== الإيصالات المرفوضة آلياً (payments.auto_check) =====================
        -- المرفوض لا ملف له ولا طلب دفع — هذا السجل وحده: عدّاد المحاولات (يمرّ للأدمن
        -- «مشبوهاً» بعد رفضين) وما يراه الأدمن في «إدارة المدفوعات».
        CREATE TABLE IF NOT EXISTS receipt_refusals(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            reason TEXT NOT NULL,
            img_hash TEXT,
            created_at INTEGER NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS ix_rr_user ON receipt_refusals(user_id, created_at);

        -- ===================== المحادثات (صندوق الوارد والتدخّل اليدوي) =====================
        -- كل رسالة واردة وصادرة (بوت · ذكاء اصطناعي · صاحب النشاط). بلاها لا يرى
        -- صاحب البوت محادثة عميله ولا يستطيع الرد عليه.
        CREATE TABLE IF NOT EXISTS messages(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bot_id INTEGER NOT NULL,
            peer TEXT NOT NULL,
            direction TEXT NOT NULL,              -- in | out
            sender TEXT NOT NULL,                 -- customer | bot | ai | human
            kind TEXT NOT NULL DEFAULT 'text',    -- text | media | system
            text TEXT,
            media_id INTEGER,                     -- وسائط العميل (media) إن وُجدت
            created_at INTEGER NOT NULL,
            FOREIGN KEY(bot_id) REFERENCES bots(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS ix_msg_conv ON messages(bot_id, peer, id);
        -- ملخّص كل محادثة + وضعها. mode='human' يعني أن صاحب النشاط تولّاها
        -- فلا يردّ البوت ولا الذكاء الاصطناعي حتى يُعيدها.
        CREATE TABLE IF NOT EXISTS conversations(
            bot_id INTEGER NOT NULL,
            peer TEXT NOT NULL,
            name TEXT,
            mode TEXT NOT NULL DEFAULT 'bot',     -- bot | human
            unread INTEGER NOT NULL DEFAULT 0,
            last_text TEXT,
            last_at INTEGER NOT NULL,
            human_at INTEGER,                     -- آخر نشاط بشري: للعودة التلقائية للبوت
            waiting_alert_at INTEGER,             -- آخر تنبيه «عميل ينتظر رداً» عن هذه المحادثة
            PRIMARY KEY(bot_id, peer),
            FOREIGN KEY(bot_id) REFERENCES bots(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS ix_conv_bot ON conversations(bot_id, last_at);

        -- ===================== وكيل الإعداد بالذكاء الاصطناعي =====================
        CREATE TABLE IF NOT EXISTS ai_setup_sessions(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bot_id INTEGER NOT NULL,
            owner_id INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'asking', -- asking | proposed | applied | discarded
            source TEXT,                           -- ai | offline
            brief_json TEXT NOT NULL DEFAULT '{}',
            turns_json TEXT NOT NULL DEFAULT '[]',
            proposal_json TEXT,
            rounds INTEGER NOT NULL DEFAULT 0,
            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL,
            FOREIGN KEY(bot_id) REFERENCES bots(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS ix_ais_owner ON ai_setup_sessions(owner_id, created_at);
        -- نسخ إعدادات البوت قبل كل تطبيق — «تراجع» بضغطة بدل خسارة ما كتبه صاحبه.
        CREATE TABLE IF NOT EXISTS bot_config_versions(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bot_id INTEGER NOT NULL,
            config_json TEXT NOT NULL,
            reason TEXT,
            created_at INTEGER NOT NULL,
            FOREIGN KEY(bot_id) REFERENCES bots(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS ix_cfgv_bot ON bot_config_versions(bot_id, id);

        -- ===================== ردود الذكاء الاصطناعي (عقل البوت) =====================
        -- الحصة الشهرية لكل حساب. ما فوقها يُخصم من المحفظة بالقروش (paid).
        CREATE TABLE IF NOT EXISTS ai_usage(
            owner_id INTEGER NOT NULL,
            month TEXT NOT NULL,                  -- 'YYYY-MM'
            replies INTEGER NOT NULL DEFAULT 0,
            paid INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY(owner_id, month),
            FOREIGN KEY(owner_id) REFERENCES users(id) ON DELETE CASCADE
        );

        -- ===================== مكتبة وسائط صاحب النشاط =====================
        -- منفصلة عن `media` (وسائط العملاء الخاصة): هذه صور وفيديوهات يرسلها البوت.
        CREATE TABLE IF NOT EXISTS assets(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            owner_id INTEGER NOT NULL,
            kind TEXT NOT NULL,                   -- image | video
            mime TEXT NOT NULL,
            size INTEGER NOT NULL,
            fname TEXT NOT NULL,                  -- اسم مولَّد داخلياً
            name TEXT,
            source_url TEXT,
            created_at INTEGER NOT NULL,
            FOREIGN KEY(owner_id) REFERENCES users(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS ix_assets_owner ON assets(owner_id, id);
        -- مرجع الملف لدى كل قناة (file_id لتليجرام · media_id لواتساب) — يُرفع مرة
        -- ويُعاد استعماله. media_id لواتساب ينتهي، فيُحفظ وقت انتهائه.
        CREATE TABLE IF NOT EXISTS asset_refs(
            asset_id INTEGER NOT NULL,
            bot_id INTEGER NOT NULL,
            ref TEXT NOT NULL,
            expires_at INTEGER,
            PRIMARY KEY(asset_id, bot_id),
            FOREIGN KEY(asset_id) REFERENCES assets(id) ON DELETE CASCADE,
            FOREIGN KEY(bot_id) REFERENCES bots(id) ON DELETE CASCADE
        );
        """)
        _migrate(c)
        _hot_indexes(c)
        _analytics_tables(c)
        _customer_pay_tables(c)
        _email_tables(c)
        _auth_tables(c)
        _activation_tables(c)
        _team_tables(c)
        _crm_tables(c)
        _msg_status_tables(c)
        _campaign_tables(c)
        _flow_tables(c)
        _inbox_tables(c)
        _sequence_tables(c)
        _growth_tables(c)
        _widget_tables(c)
        _chat_pay_tables(c)
        _integration_tables(c)
        _comment_tables(c)
        _crm_sync_tables(c)
        _call_tables(c)
        _notify_tables(c)

def _hot_indexes(c):
    """فهارس الاستعلامات الساخنة. EXPLAIN QUERY PLAN كان يُظهر مسحاً كاملاً لـ events و
    leads و orders و payments و bots — ومع workers=1 أي بطء يصيب كل المستخدمين.
    بعد `_migrate` لأن بعض الأعمدة يضيفها الترحيل في القواعد القديمة. (حجوزات البوت
    يغطيها فهرس UNIQUE(bot_id, slot) أصلاً.)"""
    for sql in ("CREATE INDEX IF NOT EXISTS ix_events_bot_day ON events(bot_id, day)",
                "CREATE INDEX IF NOT EXISTS ix_events_created ON events(created_at)",
                "CREATE INDEX IF NOT EXISTS ix_leads_bot ON leads(bot_id, created_at)",
                "CREATE INDEX IF NOT EXISTS ix_orders_bot ON orders(bot_id, created_at)",
                "CREATE INDEX IF NOT EXISTS ix_payments_user ON payments(user_id, created_at)",
                "CREATE INDEX IF NOT EXISTS ix_payments_status ON payments(status, created_at)",
                "CREATE INDEX IF NOT EXISTS ix_payments_img ON payments(img_hash)",
                "CREATE INDEX IF NOT EXISTS ix_bots_owner ON bots(owner_id)"):
        try:
            c.execute(sql)
        except sqlite3.OperationalError:
            log.warning("index skipped: %s", sql, exc_info=True)

def _analytics_tables(c):
    """قياس الزوار داخل المنصة — بلا سكربت خارجي (CSP يبقى 'self') ولا كوكي تتبّع.
    page_views: زيارة صفحة عامة. `vid` بصمة يومية تُعدّ الزوار الفريدين بلا تخزين IP.
    funnel: أول مرة فقط لكل (مرحلة، مستخدم، بوت) — مراحل قمع لا عدّاد نقرات."""
    c.executescript("""
        CREATE TABLE IF NOT EXISTS page_views(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            day TEXT NOT NULL,
            path TEXT NOT NULL,
            ref TEXT,                             -- دومين المُحيل الخارجي
            src TEXT,                             -- utm_source أو ref (أفيليت)
            device TEXT,                          -- mobile | desktop
            vid TEXT,
            created_at INTEGER NOT NULL
        );
        CREATE INDEX IF NOT EXISTS ix_pv_day ON page_views(day);
        CREATE TABLE IF NOT EXISTS funnel(
            kind TEXT NOT NULL,
            user_id INTEGER NOT NULL,
            bot_id INTEGER NOT NULL DEFAULT 0,
            created_at INTEGER NOT NULL,
            PRIMARY KEY(kind, user_id, bot_id)
        );
    """)

def _customer_pay_tables(c):
    """إضافة «تحصيل المدفوعات» (مدفوعة لكل بوت): عميل البوت يحوّل على حسابات صاحبه ويرسل
    الإيصال للبوت، فيُفحص بنفس محرك إيصالات المنصة ويعتمده صاحب البوت.
    bot_addons: صلاحية الإضافة لكل بوت. bot_payments: إيصالات عملاء البوت."""
    c.executescript("""
        CREATE TABLE IF NOT EXISTS bot_addons(
            bot_id INTEGER NOT NULL,
            addon TEXT NOT NULL,                  -- pay
            expires_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL,
            PRIMARY KEY(bot_id, addon),
            FOREIGN KEY(bot_id) REFERENCES bots(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS bot_payments(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bot_id INTEGER NOT NULL,
            order_id INTEGER,
            tg_user_id INTEGER,
            customer TEXT,
            amount REAL NOT NULL,
            screenshot TEXT,                      -- اسم مولَّد داخلياً في مجلد الرفع
            img_hash TEXT,
            file_id TEXT,                         -- معرّف الصورة في تليجرام (لإعادة إرسالها للمالك)
            auto_check TEXT,
            status TEXT NOT NULL DEFAULT 'pending',   -- pending | approved | rejected
            created_at INTEGER NOT NULL,
            decided_at INTEGER,
            FOREIGN KEY(bot_id) REFERENCES bots(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS ix_bp_bot ON bot_payments(bot_id, status, created_at);
        CREATE INDEX IF NOT EXISTS ix_bp_img ON bot_payments(bot_id, img_hash);
    """)

def _email_tables(c):
    """حملات البريد من لوحة الأدمن (email_campaigns.py).
    email_campaigns: الحملة ومحتواها (JSON بالعربية واختيارياً الإنجليزية) وجمهورها.
    email_sends: مستلم واحد لكل (حملة، مستخدم) — المفتاح هو ما يمنع تكرار رسالة لأحد عند
    الاستئناف بعد إيقاف أو إعادة تشغيل. الموافقة على الأخبار في settings (email_news)."""
    c.executescript("""
        CREATE TABLE IF NOT EXISTS email_campaigns(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            kind TEXT NOT NULL,                   -- news (للموافقين فقط) | service (إشعار خدمة)
            audience TEXT NOT NULL,               -- all | paid | free | expiring | lapsed | no_bot | plan:<id>
            content TEXT NOT NULL,                -- JSON: {ar:{subject,preheader,title,body,cta}, en, url, code}
            status TEXT NOT NULL DEFAULT 'sending',   -- sending | stopped | done
            note TEXT,                            -- cap_wait | smtp_error | no_public_url | error
            total INTEGER NOT NULL DEFAULT 0,
            created_by INTEGER,
            created_at INTEGER NOT NULL,
            finished_at INTEGER
        );
        CREATE TABLE IF NOT EXISTS email_sends(
            campaign_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            status TEXT NOT NULL,                 -- sent | failed | skipped
            sent_at INTEGER NOT NULL,
            PRIMARY KEY(campaign_id, user_id)
        );
        CREATE INDEX IF NOT EXISTS ix_es_day ON email_sends(sent_at);
    """)

def _auth_tables(c):
    """نظام الحساب: كود تأكيد البريد (مجزّأ — لا يُخزَّن الكود نفسه) وهويات الدخول الخارجية.
    email_verifications: صف واحد لكل مستخدم؛ إعادة الإرسال تستبدله وتصفّر المحاولات.
    user_identities: (مزوّد، معرّف الحساب عنده) ⇒ مستخدم. جوجل: sub · فيسبوك: id."""
    c.executescript("""
        CREATE TABLE IF NOT EXISTS email_verifications(
            user_id INTEGER PRIMARY KEY,
            email TEXT NOT NULL,                  -- البريد الذي أُرسل له الكود (تغيّره يُبطله)
            code_hash TEXT NOT NULL,
            token_hash TEXT NOT NULL,             -- رابط التأكيد في نفس الرسالة
            attempts INTEGER NOT NULL DEFAULT 0,
            sent_at INTEGER NOT NULL,
            expires_at INTEGER NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS ix_ev_token ON email_verifications(token_hash);
        CREATE TABLE IF NOT EXISTS user_identities(
            provider TEXT NOT NULL,               -- google | facebook
            subject TEXT NOT NULL,
            user_id INTEGER NOT NULL,
            email TEXT,
            created_at INTEGER NOT NULL,
            PRIMARY KEY(provider, subject),
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS ix_ui_user ON user_identities(user_id);
    """)

# ---------- حملات البريد (email_campaigns.py) ----------
EMAIL_AUDIENCES = ("all", "paid", "free", "expiring", "lapsed", "no_bot")
_PAID_SQL = ("(s.plan IS NOT NULL AND s.plan<>'free' AND s.status='active' "
             "AND (s.expires_at IS NULL OR s.expires_at>:now))")

def _audience_sql(audience, kind):
    """(شرط SQL، معاملات) لجمهور حملة — (None, None) لجمهور غير معروف.
    الأخبار (news) لمن وافق صراحةً فقط؛ المحظور لا يصله شيء."""
    now = int(time.time())
    p = {"now": now, "soon": now + 7 * 86400}
    where = ["u.email IS NOT NULL", "u.email<>''", "u.is_blocked=0"]
    if audience == "all":
        pass
    elif audience == "paid":
        where.append(_PAID_SQL)
    elif audience == "free":
        where.append("NOT " + _PAID_SQL)
    elif audience == "expiring":                              # مدفوع ينتهي خلال 7 أيام
        where += [_PAID_SQL, "s.expires_at IS NOT NULL", "s.expires_at<=:soon"]
    elif audience == "lapsed":                                # كان مدفوعاً وانتهى
        where += ["s.plan IS NOT NULL", "s.plan<>'free'", "s.expires_at IS NOT NULL", "s.expires_at<=:now"]
    elif audience == "no_bot":                                # سجّل ولم ينشئ بوتاً
        where.append("NOT EXISTS(SELECT 1 FROM bots b WHERE b.owner_id=u.id)")
    elif audience.startswith("plan:") and audience[5:]:
        where += [_PAID_SQL, "s.plan=:plan"]
        p["plan"] = audience[5:]
    else:
        return None, None
    if kind == "news":
        where.append("EXISTS(SELECT 1 FROM settings st WHERE st.user_id=u.id "
                     "AND st.key='email_news' AND st.value='1')")
    return " AND ".join(where), p

def email_audience(audience, kind):
    """مستلمو حملة: [{id, username, email, lang}] مرتّبين بالمعرّف."""
    cond, p = _audience_sql(audience, kind)
    if cond is None:
        return []
    with get_conn() as c:
        rows = c.execute(f"""SELECT u.id, u.username, u.email,
                   COALESCE((SELECT value FROM settings WHERE user_id=u.id AND key='lang'),'ar') AS lang
                   FROM users u LEFT JOIN subscriptions s ON s.user_id=u.id
                   WHERE {cond} ORDER BY u.id""", p).fetchall()
        return [dict(r) for r in rows]

def email_audience_count(audience, kind):
    cond, p = _audience_sql(audience, kind)
    if cond is None:
        return 0
    with get_conn() as c:
        return c.execute(f"SELECT COUNT(*) FROM users u LEFT JOIN subscriptions s ON s.user_id=u.id "
                         f"WHERE {cond}", p).fetchone()[0]

def email_reach():
    """{with_email, opted_in}: من يمكن مراسلته أصلاً، ومن وافق على الأخبار."""
    return {"with_email": email_audience_count("all", "service"),
            "opted_in": email_audience_count("all", "news")}

def create_email_campaign(kind, audience, content, created_by):
    with get_conn() as c:
        return c.execute("INSERT INTO email_campaigns(kind,audience,content,status,created_by,created_at) "
                         "VALUES(?,?,?,'sending',?,?)",
                         (kind, audience, content, created_by, int(time.time()))).lastrowid

_EC_COUNTS = """(SELECT COUNT(*) FROM email_sends e WHERE e.campaign_id=c.id AND e.status='sent') AS sent,
                (SELECT COUNT(*) FROM email_sends e WHERE e.campaign_id=c.id AND e.status='failed') AS failed,
                (SELECT COUNT(*) FROM email_sends e WHERE e.campaign_id=c.id AND e.status='skipped') AS skipped"""

def get_email_campaign(cid):
    with get_conn() as c:
        r = c.execute(f"SELECT c.*, {_EC_COUNTS} FROM email_campaigns c WHERE c.id=?", (cid,)).fetchone()
        return dict(r) if r else None

def list_email_campaigns(status=None, limit=30):
    with get_conn() as c:
        q = f"SELECT c.*, {_EC_COUNTS} FROM email_campaigns c"
        args = []
        if status:
            q += " WHERE c.status=?"
            args.append(status)
        q += " ORDER BY c.id DESC LIMIT ?"
        return [dict(r) for r in c.execute(q, (*args, limit)).fetchall()]

def set_email_campaign(cid, **kw):
    cols = {k: v for k, v in kw.items() if k in ("status", "note", "total", "finished_at")}
    if not cols:
        return
    with get_conn() as c:
        c.execute(f"UPDATE email_campaigns SET {', '.join(k + '=?' for k in cols)} WHERE id=?",
                  (*cols.values(), cid))

def email_done_ids(cid):
    """من انتهى أمرهم في الحملة (أُرسل أو تُخطّي). الفاشل يُعاد عند الاستئناف."""
    with get_conn() as c:
        return {r[0] for r in c.execute("SELECT user_id FROM email_sends WHERE campaign_id=? "
                                        "AND status IN ('sent','skipped')", (cid,)).fetchall()}

def record_email_send(cid, user_id, status):
    """مستلم واحد لكل (حملة، مستخدم). الفاشل وحده يُحدَّث — المُرسَل لا يُكتب فوقه."""
    with get_conn() as c:
        c.execute("INSERT INTO email_sends(campaign_id,user_id,status,sent_at) VALUES(?,?,?,?) "
                  "ON CONFLICT(campaign_id,user_id) DO UPDATE SET status=excluded.status, "
                  "sent_at=excluded.sent_at WHERE email_sends.status='failed'",
                  (cid, user_id, status, int(time.time())))

def email_sends_today():
    """رسائل حملات أُرسلت منذ منتصف الليل (توقيت الخادم) — للسقف اليومي."""
    midnight = int(time.mktime(time.localtime()[:3] + (0, 0, 0, 0, 0, -1)))
    with get_conn() as c:
        return c.execute("SELECT COUNT(*) FROM email_sends WHERE status='sent' AND sent_at>=?",
                         (midnight,)).fetchone()[0]

def email_news_on(user_id):
    return get_setting(user_id, "email_news") == "1"

def set_email_news(user_id, on):
    """موافقة الأخبار والعروض بالبريد + وقتها (إثبات الموافقة)."""
    set_setting(user_id, "email_news", "1" if on else "0")
    set_setting(user_id, "email_news_at", str(int(time.time())))

def platform_setdefault(key, value):
    """يكتب القيمة فقط لو المفتاح غير موجود، ويرجّع المحفوظ — ذرّي بين الخيوط."""
    with get_conn() as c:
        c.execute("INSERT OR IGNORE INTO platform(key,value) VALUES(?,?)", (key, value))
        return c.execute("SELECT value FROM platform WHERE key=?", (key,)).fetchone()[0]

# ---------- نظام الحساب: التسجيل والتحقق والهويات (السياسات في accounts.py) ----------
def create_account(username, pw_hash, email, phone=None, age=None, entity_type=None,
                   verify_required=False, email_verified=False):
    """حساب جديد بكل بيانات التسجيل. يرجّع (user_id, error). الفحوص هنا ثم القيود الفريدة
    هي الحارس الأخير لو سبق طلبٌ متزامن. أول حساب = admin كما في create_user."""
    now = int(time.time())
    with get_conn() as c:
        if c.execute("SELECT 1 FROM users WHERE LOWER(username)=LOWER(?)", (username,)).fetchone():
            return None, "u_taken"
        if email and c.execute("SELECT 1 FROM users WHERE email=?", (email,)).fetchone():
            return None, "email_taken"
        if phone and c.execute("SELECT 1 FROM users WHERE phone=?", (phone,)).fetchone():
            return None, "phone_taken"
        role = "admin" if c.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0 else "user"
        try:
            cur = c.execute(
                "INSERT INTO users(username,pw_hash,role,created_at,email,phone,age,entity_type,"
                "verify_required,email_verified_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (username, pw_hash, role, now, email or None, phone, age, entity_type,
                 1 if verify_required else 0, now if email_verified else None))
        except sqlite3.IntegrityError:
            return None, "u_taken"
        return cur.lastrowid, None

def username_taken(username, exclude_id=None):
    """التفرّد بلا حساسية لحالة الأحرف: «Ahmed» و«ahmed» حساب واحد في عين العميل."""
    with get_conn() as c:
        return bool(c.execute("SELECT 1 FROM users WHERE LOWER(username)=LOWER(?) AND id<>?",
                              (username, exclude_id or 0)).fetchone())

def phone_taken(phone, exclude_id=None):
    with get_conn() as c:
        return bool(c.execute("SELECT 1 FROM users WHERE phone=? AND id<>?",
                              (phone, exclude_id or 0)).fetchone())

def get_user_by_login(ident):
    """الدخول باسم المستخدم أو البريد. الاسم: مطابقة تامة، ثم بلا حساسية للحالة إن كانت فريدة."""
    ident = (ident or "").strip()
    if not ident:
        return None
    with get_conn() as c:
        r = None
        if "@" in ident:
            r = c.execute("SELECT * FROM users WHERE email=?", (ident.lower(),)).fetchone()
        if not r:
            # أسماء قديمة (قبل USERNAME_RE) قد تحمل «@» — فالاسم احتياطي حتى مع @
            r = c.execute("SELECT * FROM users WHERE username=?", (ident,)).fetchone()
            if not r:
                rows = c.execute("SELECT * FROM users WHERE LOWER(username)=LOWER(?)", (ident,)).fetchall()
                r = rows[0] if len(rows) == 1 else None
        return dict(r) if r else None

def email_gate(u):
    """هل يُمنع هذا الحساب من اللوحة حتى يؤكد بريده؟ الحسابات الجديدة وحدها (verify_required)،
    والأدمن والدعم لا يُحجبون أبداً."""
    return bool(u and u.get("verify_required") and not u.get("email_verified_at")
                and u.get("role", "user") == "user")

def start_email_verification(user_id, email, code_hash, token_hash, ttl):
    now = int(time.time())
    with get_conn() as c:
        c.execute("INSERT INTO email_verifications(user_id,email,code_hash,token_hash,attempts,sent_at,expires_at) "
                  "VALUES(?,?,?,?,0,?,?) ON CONFLICT(user_id) DO UPDATE SET email=excluded.email, "
                  "code_hash=excluded.code_hash, token_hash=excluded.token_hash, attempts=0, "
                  "sent_at=excluded.sent_at, expires_at=excluded.expires_at",
                  (user_id, email, code_hash, token_hash, now, now + ttl))

def email_verification(user_id):
    with get_conn() as c:
        r = c.execute("SELECT * FROM email_verifications WHERE user_id=?", (user_id,)).fetchone()
        return dict(r) if r else None

def _confirm_email(c, user_id, email, now):
    # شرط email=?: لو غيّر المستخدم بريده بعد الإرسال فالكود القديم لا يؤكد الجديد
    cur = c.execute("UPDATE users SET email_verified_at=? WHERE id=? AND email=?", (now, user_id, email))
    c.execute("DELETE FROM email_verifications WHERE user_id=?", (user_id,))
    return "ok" if cur.rowcount == 1 else "expired"

def check_email_code(user_id, code_hash, max_attempts=5):
    """'ok' | 'bad' | 'locked' | 'expired'. الخطأ يُحسب، وبعد max_attempts يلزم كود جديد."""
    import hmac as _hmac
    now = int(time.time())
    with get_conn() as c:
        r = c.execute("SELECT * FROM email_verifications WHERE user_id=?", (user_id,)).fetchone()
        if not r or r["expires_at"] <= now:
            return "expired"
        if r["attempts"] >= max_attempts:
            return "locked"
        if not _hmac.compare_digest(r["code_hash"], code_hash or ""):
            c.execute("UPDATE email_verifications SET attempts=attempts+1 WHERE user_id=?", (user_id,))
            return "locked" if r["attempts"] + 1 >= max_attempts else "bad"
        return _confirm_email(c, user_id, r["email"], now)

def confirm_email_token(token_hash):
    """رابط التأكيد من الرسالة. يرجّع user_id أو None."""
    now = int(time.time())
    with get_conn() as c:
        r = c.execute("SELECT * FROM email_verifications WHERE token_hash=? AND expires_at>?",
                      (token_hash, now)).fetchone()
        if not r:
            return None
        return r["user_id"] if _confirm_email(c, r["user_id"], r["email"], now) == "ok" else None

GRANT_DAYS = 7

def grant_create(user_id, via, note="", staff_id=None, days=GRANT_DAYS):
    """إذن جديد يلغي أي سابق. يرجّع معرّفه."""
    now = int(time.time())
    days = max(1, min(30, int(days or GRANT_DAYS)))
    with get_conn() as c:
        c.execute("UPDATE setup_grants SET revoked_at=? WHERE user_id=? AND revoked_at IS NULL", (now, user_id))
        return c.execute("INSERT INTO setup_grants(user_id,via,note,staff_id,created_at,expires_at) "
                         "VALUES(?,?,?,?,?,?)", (user_id, via, (note or "")[:500], staff_id, now,
                                                 now + days * 86400)).lastrowid

def active_grant(user_id):
    with get_conn() as c:
        r = c.execute("SELECT * FROM setup_grants WHERE user_id=? AND revoked_at IS NULL AND expires_at>? "
                      "ORDER BY id DESC LIMIT 1", (user_id, int(time.time()))).fetchone()
        return dict(r) if r else None

def revoke_grant(user_id):
    with get_conn() as c:
        return c.execute("UPDATE setup_grants SET revoked_at=? WHERE user_id=? AND revoked_at IS NULL",
                         (int(time.time()), user_id)).rowcount > 0

def active_grants():
    """{user_id: grant} للإذونات السارية — شارة «طالب مساعدة» في إدارة المستخدمين."""
    with get_conn() as c:
        rows = c.execute("SELECT * FROM setup_grants WHERE revoked_at IS NULL AND expires_at>?",
                         (int(time.time()),)).fetchall()
        return {r["user_id"]: dict(r) for r in rows}

def log_staff_action(staff_id, user_id, action, detail="", bot_id=None):
    with get_conn() as c:
        c.execute("INSERT INTO staff_actions(staff_id,user_id,bot_id,action,detail,created_at) VALUES(?,?,?,?,?,?)",
                  (staff_id, user_id, bot_id, action[:60], (detail or "")[:300], int(time.time())))

def staff_actions_for(user_id, limit=30):
    with get_conn() as c:
        rows = c.execute("SELECT a.*, u.username AS staff_name FROM staff_actions a LEFT JOIN users u "
                         "ON u.id=a.staff_id WHERE a.user_id=? ORDER BY a.id DESC LIMIT ?",
                         (user_id, limit)).fetchall()
        return [dict(r) for r in rows]


def remember_wa_user(bsuid, phone):
    with get_conn() as c:
        c.execute("INSERT INTO wa_user_ids(bsuid,phone,updated_at) VALUES(?,?,?) ON CONFLICT(bsuid) "
                  "DO UPDATE SET phone=excluded.phone, updated_at=excluded.updated_at",
                  (bsuid, phone, int(time.time())))

def wa_user_phone(bsuid):
    with get_conn() as c:
        r = c.execute("SELECT phone FROM wa_user_ids WHERE bsuid=?", (bsuid,)).fetchone()
        return r[0] if r else None


def admin_verify_email(user_id, admin_id):
    """الأدمن يعفي الحساب من تأكيد البريد على مسؤوليته (عميل لا يصل للكود). يرجّع True لو
    كان محجوباً ورُفع عنه الحجب. لا يدّعي أن البريد مؤكَّد — `verify_required` يُرفع فقط،
    فيبقى تنبيه «أكّد بريدك» الاختياري واسترجاع كلمة المرور على البريد كما هو."""
    now = int(time.time())
    with get_conn() as c:
        cur = c.execute("UPDATE users SET verify_required=0 WHERE id=? AND verify_required=1 "
                        "AND email_verified_at IS NULL", (user_id,))
        c.execute("DELETE FROM email_verifications WHERE user_id=?", (user_id,))
        if cur.rowcount:
            c.execute("INSERT INTO settings(user_id,key,value) VALUES(?,?,?) ON CONFLICT(user_id,key) "
                      "DO UPDATE SET value=excluded.value", (user_id, "email_waived", f"{admin_id}:{now}"))
        return cur.rowcount == 1


INVITE_MAX_DAYS = 14

def create_invite(token_hash, admin_id, days, note=""):
    now = int(time.time())
    days = max(1, min(INVITE_MAX_DAYS, int(days or 3)))
    with get_conn() as c:
        return c.execute("INSERT INTO signup_invites(token_hash,note,created_by,created_at,expires_at) "
                         "VALUES(?,?,?,?,?)", (token_hash, (note or "")[:120], admin_id, now,
                                               now + days * 86400)).lastrowid

def invite_valid(token_hash):
    now = int(time.time())
    with get_conn() as c:
        r = c.execute("SELECT id FROM signup_invites WHERE token_hash=? AND revoked=0 AND claimed_at IS NULL "
                      "AND expires_at>?", (token_hash or "", now)).fetchone()
        return r[0] if r else None

def claim_invite(token_hash):
    """حجز ذرّي للرابط قبل إنشاء الحساب — طلبان متزامنان بنفس الرابط لا ينجحان معاً."""
    now = int(time.time())
    with get_conn() as c:
        cur = c.execute("UPDATE signup_invites SET claimed_at=? WHERE token_hash=? AND revoked=0 "
                        "AND claimed_at IS NULL AND expires_at>?", (now, token_hash or "", now))
        return cur.rowcount == 1

def finish_invite(token_hash, user_id):
    with get_conn() as c:
        c.execute("UPDATE signup_invites SET used_by=? WHERE token_hash=?", (user_id, token_hash))

def release_invite(token_hash):
    """فشل إنشاء الحساب بعد الحجز (اسم مأخوذ…) — الرابط يرجع صالحاً لمحاولة ثانية."""
    with get_conn() as c:
        c.execute("UPDATE signup_invites SET claimed_at=NULL WHERE token_hash=? AND used_by IS NULL",
                  (token_hash,))

def revoke_invite(invite_id):
    with get_conn() as c:
        return c.execute("UPDATE signup_invites SET revoked=1 WHERE id=? AND used_by IS NULL",
                         (invite_id,)).rowcount == 1

def list_invites(limit=30):
    with get_conn() as c:
        rows = c.execute("SELECT i.id, i.note, i.created_at, i.expires_at, i.claimed_at, i.used_by, i.revoked, "
                         "u.username AS used_name FROM signup_invites i LEFT JOIN users u ON u.id=i.used_by "
                         "ORDER BY i.id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]


def mark_email_verified(user_id):
    """بريد أكّده مزوّد الدخول (جوجل/فيسبوك) — لا حاجة لكود."""
    with get_conn() as c:
        c.execute("UPDATE users SET email_verified_at=? WHERE id=? AND email IS NOT NULL",
                  (int(time.time()), user_id))

def set_user_profile(user_id, phone=None, age=None, entity_type=None):
    """بيانات النشاط. تغيير الهاتف يُسقط تأكيده. يرجّع (ok, error)."""
    with get_conn() as c:
        row = c.execute("SELECT phone FROM users WHERE id=?", (user_id,)).fetchone()
        if not row:
            return False, "missing"
        if phone and phone != row["phone"]:
            if c.execute("SELECT 1 FROM users WHERE phone=? AND id<>?", (phone, user_id)).fetchone():
                return False, "phone_taken"
            try:
                c.execute("UPDATE users SET phone=?, phone_verified_at=NULL WHERE id=?", (phone, user_id))
            except sqlite3.IntegrityError:
                return False, "phone_taken"
        if age is not None:
            c.execute("UPDATE users SET age=? WHERE id=?", (age, user_id))
        if entity_type:
            c.execute("UPDATE users SET entity_type=? WHERE id=?", (entity_type, user_id))
    return True, None

PHONE_CODE_TTL = 900        # رابط تأكيد الهاتف عبر بوت المنصة: 15 دقيقة

def set_phone_code(user_id, code):
    set_setting(user_id, "phone_code", code)
    set_setting(user_id, "phone_code_at", str(int(time.time())))

def phone_code_user(code):
    """صاحب كود تأكيد الهاتف إن كان صالحاً، وإلا None."""
    code = (code or "").strip()
    if not code:
        return None
    with get_conn() as c:
        r = c.execute("SELECT user_id FROM settings WHERE key='phone_code' AND value=?", (code,)).fetchone()
    if not r:
        return None
    at = int(get_setting(r["user_id"], "phone_code_at", "0") or 0)
    return r["user_id"] if at + PHONE_CODE_TTL > time.time() else None

def verify_phone_tg(user_id, code, contact_phone, tg_id):
    """جهة اتصال شاركها صاحبها مع بوت المنصة (تليجرام يثبت أن الرقم رقمه).
    'ok' | 'mismatch' (رقم تليجرام غير رقم الحساب) | 'expired'. النجاح يربط تليجرام للتنبيهات أيضاً."""
    import re as _re
    if phone_code_user(code) != user_id:
        return "expired"
    u = get_user(user_id)
    digits = lambda s: _re.sub(r"\D", "", s or "")
    if not u or not u.get("phone") or digits(u["phone"]) != digits(contact_phone):
        return "mismatch"
    with get_conn() as c:
        c.execute("UPDATE users SET phone_verified_at=? WHERE id=?", (int(time.time()), user_id))
        c.execute("DELETE FROM settings WHERE user_id=? AND key IN ('phone_code','phone_code_at')", (user_id,))
        c.execute("INSERT INTO settings(user_id,key,value) VALUES(?,'tg_chat_id',?) "
                  "ON CONFLICT(user_id,key) DO UPDATE SET value=excluded.value", (user_id, str(tg_id)))
    return "ok"

def get_identity(provider, subject):
    with get_conn() as c:
        r = c.execute("SELECT * FROM user_identities WHERE provider=? AND subject=?",
                      (provider, str(subject))).fetchone()
        return dict(r) if r else None

def add_identity(provider, subject, user_id, email=None):
    """يربط هوية خارجية بحساب. False لو كانت مربوطة بحساب (أي حساب) من قبل."""
    with get_conn() as c:
        cur = c.execute("INSERT OR IGNORE INTO user_identities(provider,subject,user_id,email,created_at) "
                        "VALUES(?,?,?,?,?)", (provider, str(subject), user_id, email, int(time.time())))
        return cur.rowcount == 1

def list_identities(user_id):
    with get_conn() as c:
        return [r[0] for r in c.execute("SELECT provider FROM user_identities WHERE user_id=?",
                                        (user_id,)).fetchall()]

def remove_identity(user_id, provider):
    """فك ربط هوية خارجية. يرجّع عدد ما حُذف (0 = لم تكن مربوطة)."""
    with get_conn() as c:
        return c.execute("DELETE FROM user_identities WHERE user_id=? AND provider=?",
                         (user_id, provider)).rowcount

# ---------- users ----------
def create_user(username, pw_hash, email=None):
    with get_conn() as c:
        n = c.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        role = "admin" if n == 0 else "user"   # أول مستخدم = admin
        cur = c.execute("INSERT INTO users(username,pw_hash,role,created_at,email) VALUES(?,?,?,?,?)",
                        (username, pw_hash, role, int(time.time()), email or None))
        return cur.lastrowid

def get_user_by_name(username):
    with get_conn() as c:
        r = c.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
        return dict(r) if r else None

def count_users():
    with get_conn() as c:
        return c.execute("SELECT COUNT(*) FROM users").fetchone()[0]

# ---------- bots ----------
def create_bot(owner_id, name, token, template, config, channel="telegram"):
    with get_conn() as c:
        # token_idx فريد: إضافة نفس البوت مرتين ترمي IntegrityError كما كانت قبل التشفير
        cur = c.execute("INSERT INTO bots(owner_id,name,token,token_idx,template,config_json,"
                        "is_active,created_at,channel) VALUES(?,?,?,?,?,?,0,?,?)",
                        (owner_id, name, _encrypt(token.strip()), _token_idx(token), template,
                         json.dumps(config, ensure_ascii=False), int(time.time()), channel))
        return cur.lastrowid

def list_bots(owner_id):
    with get_conn() as c:
        rows = c.execute("SELECT * FROM bots WHERE owner_id=? ORDER BY created_at DESC, id DESC",
                         (owner_id,)).fetchall()
        return [_map_bot(r) for r in rows]

def get_bot(bot_id, owner_id=None):
    with get_conn() as c:
        if owner_id is None:
            r = c.execute("SELECT * FROM bots WHERE id=?", (bot_id,)).fetchone()
        else:
            r = c.execute("SELECT * FROM bots WHERE id=? AND owner_id=?", (bot_id, owner_id)).fetchone()
        return _map_bot(r) if r else None

def all_active_bots():
    with get_conn() as c:
        return [_map_bot(r) for r in c.execute("SELECT * FROM bots WHERE is_active=1").fetchall()]

def set_bot_active(bot_id, active):
    with get_conn() as c:
        c.execute("UPDATE bots SET is_active=? WHERE id=?", (1 if active else 0, bot_id))

def update_bot_config(bot_id, config):
    with get_conn() as c:
        c.execute("UPDATE bots SET config_json=? WHERE id=?",
                  (json.dumps(config, ensure_ascii=False), bot_id))

def delete_bot(bot_id):
    with get_conn() as c:
        c.execute("DELETE FROM bots WHERE id=?", (bot_id,))

# ---------- subscribers / events ----------
def add_bot_user(bot_id, tg_user_id, first_name, peer=None):
    now = int(time.time())
    peer = peer or f"tg:{tg_user_id}"
    with get_conn() as c:
        c.execute("INSERT INTO bot_users(bot_id,tg_user_id,first_name,created_at,peer,last_in_at)"
                  " VALUES(?,?,?,?,?,?)"
                  " ON CONFLICT(bot_id,tg_user_id) DO UPDATE SET"
                  " peer=excluded.peer, last_in_at=excluded.last_in_at",
                  (bot_id, tg_user_id, first_name, now, peer, now))
    link_contact(bot_id, peer, first_name)      # كل عميل لأي بوت = جهة اتصال للحساب (CRM)

def bot_user_exists(bot_id, peer):
    with get_conn() as c:
        return c.execute("SELECT 1 FROM bot_users WHERE bot_id=? AND peer=? LIMIT 1",
                         (bot_id, peer)).fetchone() is not None

def touch_bot_user(bot_id, peer):
    """يسجّل وقت آخر رسالة واردة — أساس نافذة الـ24 ساعة في واتساب."""
    with get_conn() as c:
        c.execute("UPDATE bot_users SET last_in_at=? WHERE bot_id=? AND peer=?",
                  (int(time.time()), bot_id, peer))

def set_opt_out(bot_id, peer, out=True):
    """إيقاف/استئناف الرسائل الترويجية لعميل. من طلب الإيقاف يخرج من كل بثّ وحملة
    (`list_bot_peers` · `list_bot_user_ids`) — وهي القائمة نفسها التي تُحسب عليها
    تكلفة الحملة، فلا يُخصم على من لن يُرسل إليه (AGENTS.md §3.22)."""
    with get_conn() as c:
        # الإيقاف يسقط الموافقة على العروض أيضاً — لا يعود للقائمة إلا بموافقة جديدة
        c.execute("UPDATE bot_users SET opted_out=?, optin_at=CASE WHEN ? THEN NULL ELSE optin_at END"
                  " WHERE bot_id=? AND peer=?", (1 if out else 0, 1 if out else 0, bot_id, peer))
    if out:                                     # الإيقاف يسقط موافقة الجهة؛ الاستئناف لا يمنحها
        set_contact_optin_by_peer(bot_id, peer, 0)
        stop_enrollments_for_peer(bot_id, peer, "opted_out")   # ولا تصله خطوة تسلسل بعده أبداً

def set_optin(bot_id, peer, yes=True):
    """موافقة العميل الصريحة على استقبال العروض (أو سحبها)."""
    with get_conn() as c:
        c.execute("UPDATE bot_users SET optin_at=?, opted_out=CASE WHEN ? THEN 0 ELSE opted_out END"
                  " WHERE bot_id=? AND peer=?",
                  (int(time.time()) if yes else None, 1 if yes else 0, bot_id, peer))
    set_contact_optin_by_peer(bot_id, peer, 1 if yes else 0)

def bot_user_optin(bot_id, peer):
    with get_conn() as c:
        r = c.execute("SELECT optin_at FROM bot_users WHERE bot_id=? AND peer=? AND opted_out=0",
                      (bot_id, peer)).fetchone()
        return bool(r and r[0])

def optin_stats(bot_id):
    """{optin: الموافقون على العروض, out: من طلب الإيقاف, total: كل المشتركين}."""
    with get_conn() as c:
        r = c.execute("SELECT COUNT(*) total, SUM(optin_at IS NOT NULL AND opted_out=0) optin,"
                      " SUM(opted_out) out FROM bot_users WHERE bot_id=?", (bot_id,)).fetchone()
    return {"total": r["total"] or 0, "optin": r["optin"] or 0, "out": r["out"] or 0}

def list_optins(bot_id):
    """الموافقون على العروض (للتصدير) — الأحدث أولاً."""
    with get_conn() as c:
        return [dict(r) for r in c.execute(
            "SELECT peer, first_name, optin_at FROM bot_users WHERE bot_id=? AND optin_at IS NOT NULL"
            " AND opted_out=0 ORDER BY optin_at DESC", (bot_id,)).fetchall()]

def is_opted_out(bot_id, peer):
    with get_conn() as c:
        r = c.execute("SELECT opted_out FROM bot_users WHERE bot_id=? AND peer=?",
                      (bot_id, peer)).fetchone()
        return bool(r and r[0])

# عملاء قناة البوت نفسها فقط: صفّ المساعد الرسمي (واتساب) يحمل أيضاً عملاء بوت المنصة على
# تليجرام (`tg:`) — حملة واتساب لهم تفشل وتُحسب تكلفتها على قائمة أطول مما يصل (§3.22).
_SAME_CHANNEL = ("substr(COALESCE(peer,'tg:'),1,3) = (SELECT CASE channel WHEN 'whatsapp' THEN 'wa:' "
                 "WHEN 'messenger' THEN 'fb:' WHEN 'instagram' THEN 'ig:' ELSE 'tg:' END "
                 "FROM bots WHERE id=bot_users.bot_id)")

def list_bot_user_ids(bot_id):
    with get_conn() as c:
        return [r[0] for r in c.execute("SELECT tg_user_id FROM bot_users WHERE bot_id=? AND opted_out=0 AND "
                                        + _SAME_CHANNEL, (bot_id,)).fetchall()]

def list_bot_peers(bot_id, within_seconds=None):
    """يرجّع peers المشتركين على قناة البوت. within_seconds يقصرها على من راسل البوت
    مؤخراً. من طلب إيقاف الرسائل (`opted_out`) لا يُرجَع أبداً."""
    q = ("SELECT peer FROM bot_users WHERE bot_id=? AND peer IS NOT NULL AND opted_out=0 AND "
         + _SAME_CHANNEL)
    args = [bot_id]
    if within_seconds:
        q += " AND last_in_at IS NOT NULL AND last_in_at >= ?"
        args.append(int(time.time()) - int(within_seconds))
    with get_conn() as c:
        return [r[0] for r in c.execute(q, args).fetchall()]

def _day():
    return time.strftime("%Y-%m-%d")

def log_event(bot_id, kind, value=0):
    with get_conn() as c:
        c.execute("INSERT INTO events(bot_id,kind,value,day,created_at) VALUES(?,?,?,?,?)",
                  (bot_id, kind, value, _day(), int(time.time())))

def rating_summary(bot_id):
    """تقييمات العملاء بعد المحادثة (حدث `rating`: 3 ممتاز · 2 كويس · 1 محتاج تحسين)."""
    with get_conn() as c:
        rows = c.execute("SELECT value, COUNT(*) n FROM events WHERE bot_id=? AND kind='rating' "
                         "GROUP BY value", (bot_id,)).fetchall()
    by = {int(r["value"]): r["n"] for r in rows}
    return {"total": sum(by.values()), "great": by.get(3, 0), "good": by.get(2, 0), "bad": by.get(1, 0)}

def source_counts(bot_id):
    """من أين دخل العملاء (qr · link · poster · share) — أحداث src_* في التحليلات."""
    with get_conn() as c:
        rows = c.execute("SELECT kind, COUNT(*) n FROM events WHERE bot_id=? "
                         "AND substr(kind,1,4)='src_' GROUP BY kind", (bot_id,)).fetchall()
        return {r["kind"][4:]: r["n"] for r in rows}

# ---------- leads / orders / bookings ----------
def add_lead(bot_id, tg_user_id, data: dict):
    with get_conn() as c:
        cur = c.execute("INSERT INTO leads(bot_id,tg_user_id,data_json,created_at) VALUES(?,?,?,?)",
                        (bot_id, tg_user_id, json.dumps(data, ensure_ascii=False), int(time.time())))
        lead_id = cur.lastrowid
    log_event(bot_id, "lead")
    return lead_id

def _lim(limit):
    """حدّ الصفوف لقوائم اللوحة. None = الكل (التصدير) — LIMIT -1 في SQLite بلا حد."""
    return -1 if limit is None else int(limit)

def list_leads(bot_id, limit=300):
    with get_conn() as c:
        rows = c.execute("SELECT * FROM leads WHERE bot_id=? ORDER BY created_at DESC, id DESC LIMIT ?",
                         (bot_id, _lim(limit))).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            try: d["data"] = json.loads(d["data_json"] or "{}")
            except Exception: d["data"] = {}
            out.append(d)
        # ملفات كل lead مرة واحدة بدل استعلام لكل صف
        by_lead = {}
        for m in c.execute("SELECT id,lead_id,kind,mime,size,caption FROM media"
                           " WHERE bot_id=? AND lead_id IS NOT NULL ORDER BY id",
                           (bot_id,)).fetchall():
            by_lead.setdefault(m["lead_id"], []).append(dict(m))
        for d in out:
            d["media"] = by_lead.get(d["id"], [])
        return out

def add_order(bot_id, tg_user_id, customer, phone, address, items, total, pay_status=None,
              shipping=0, ship_zone=None):
    """يرجّع رقم الطلب — تحصيل المدفوعات يربط به إيصال العميل.

    `total` يشمل الشحن (هو المبلغ المطلوب من العميل فعلاً)، و`shipping` يُحفظ
    منفصلاً ليعرف التاجر صافي منتجاته."""
    with get_conn() as c:
        cur = c.execute("INSERT INTO orders(bot_id,tg_user_id,customer,phone,address,items_json,total,"
                        "created_at,pay_status,shipping,ship_zone) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                        (bot_id, tg_user_id, customer, phone, address,
                         json.dumps(items, ensure_ascii=False), total, int(time.time()), pay_status,
                         float(shipping or 0), (ship_zone or None)))
        order_id = cur.lastrowid
    log_event(bot_id, "order", total)
    return order_id

def list_orders(bot_id, limit=300):
    with get_conn() as c:
        rows = c.execute("SELECT * FROM orders WHERE bot_id=? ORDER BY created_at DESC, id DESC LIMIT ?",
                         (bot_id, _lim(limit))).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            try: d["items"] = json.loads(d["items_json"] or "[]")
            except Exception: d["items"] = []
            out.append(d)
        return out

def book_slot(bot_id, tg_user_id, customer, phone, service, slot):
    """يرجّع True لو تم الحجز، False لو الموعد محجوز (تعارض)."""
    with get_conn() as c:
        try:
            c.execute("INSERT INTO bookings(bot_id,tg_user_id,customer,phone,service,slot,created_at)"
                      " VALUES(?,?,?,?,?,?,?)",
                      (bot_id, tg_user_id, customer, phone, service, slot, int(time.time())))
        except sqlite3.IntegrityError:
            return False
    log_event(bot_id, "booking")
    return True

def taken_slots(bot_id):
    with get_conn() as c:
        return set(r[0] for r in c.execute(
            "SELECT slot FROM bookings WHERE bot_id=? AND status='booked'", (bot_id,)).fetchall())

def list_bookings(bot_id, limit=300):
    with get_conn() as c:
        rows = c.execute("SELECT * FROM bookings WHERE bot_id=? ORDER BY slot DESC, id DESC LIMIT ?",
                         (bot_id, _lim(limit))).fetchall()
        return [dict(r) for r in rows]

# ---------- analytics ----------
def stats_summary(bot_id):
    with get_conn() as c:
        def one(q, *a): return c.execute(q, a).fetchone()[0]
        subs = one("SELECT COUNT(*) FROM bot_users WHERE bot_id=?", bot_id)
        leads = one("SELECT COUNT(*) FROM leads WHERE bot_id=?", bot_id)
        orders = one("SELECT COUNT(*) FROM orders WHERE bot_id=?", bot_id)
        bookings = one("SELECT COUNT(*) FROM bookings WHERE bot_id=?", bot_id)
        revenue = one("SELECT COALESCE(SUM(total),0) FROM orders WHERE bot_id=?", bot_id)
        return {"subscribers": subs, "leads": leads, "orders": orders,
                "bookings": bookings, "revenue": round(revenue, 2)}

def stats_daily(bot_id, days=14):
    """سلاسل زمنية لآخر N يوم لكل نوع حدث."""
    import datetime
    today = datetime.date.today()
    labels = [(today - datetime.timedelta(days=i)).isoformat() for i in range(days-1, -1, -1)]
    # النافذة في SQL لا في بايثون: كان يسحب كل أحداث البوت منذ إنشائه ثم يصفّي 14 يوماً
    with get_conn() as c:
        rows = c.execute(
            "SELECT day, kind, COUNT(*) cnt, COALESCE(SUM(value),0) val "
            "FROM events WHERE bot_id=? AND day >= ? GROUP BY day, kind", (bot_id, labels[0])).fetchall()
    series = {k: {d: 0 for d in labels} for k in ("start", "lead", "order", "booking")}
    revenue = {d: 0 for d in labels}
    for r in rows:
        if r["day"] in labels and r["kind"] in series:
            series[r["kind"]][r["day"]] = r["cnt"]
            if r["kind"] == "order":
                revenue[r["day"]] = r["val"]
    return {"labels": labels,
            "starts": [series["start"][d] for d in labels],
            "leads": [series["lead"][d] for d in labels],
            "orders": [series["order"][d] for d in labels],
            "bookings": [series["booking"][d] for d in labels],
            "revenue": [revenue[d] for d in labels]}

# ---------- settings (مفاتيح المستخدم مثل AI) ----------
def set_setting(user_id, key, value):
    with get_conn() as c:
        c.execute("INSERT INTO settings(user_id,key,value) VALUES(?,?,?) "
                  "ON CONFLICT(user_id,key) DO UPDATE SET value=excluded.value",
                  (user_id, key, value))

def get_setting(user_id, key, default=None):
    with get_conn() as c:
        r = c.execute("SELECT value FROM settings WHERE user_id=? AND key=?", (user_id, key)).fetchone()
        return r[0] if r else default

def pop_setting(user_id, key, default=None):
    """يقرأ المفتاح ويحذفه في **معاملة واحدة** — استعمال لمرة واحدة.

    القراءة ثم الحذف على اتصالين يسمحان لطلبين متزامنين (تبويبان مفتوحان) بقراءة
    نفس القيمة قبل حذفها، فيُطلَق الحدث مرتين ويتضاعف تحويلٌ واحد في تقارير
    الإعلانات. هنا `DELETE … RETURNING` يضمن أن رابحاً واحداً فقط يحصل عليها."""
    with get_conn() as c:
        r = c.execute("DELETE FROM settings WHERE user_id=? AND key=? RETURNING value",
                      (user_id, key)).fetchone()
        return r[0] if r else default


# ---------- platform settings (global) ----------
def set_platform(key, value):
    with get_conn() as c:
        c.execute("INSERT INTO platform(key,value) VALUES(?,?) "
                  "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))

def get_platform(key, default=None):
    with get_conn() as c:
        r = c.execute("SELECT value FROM platform WHERE key=?", (key,)).fetchone()
        return r[0] if r else default

def all_platform():
    with get_conn() as c:
        return {r[0]: r[1] for r in c.execute("SELECT key,value FROM platform").fetchall()}

# ---------- subscriptions ----------
def get_subscription(user_id):
    with get_conn() as c:
        r = c.execute("SELECT * FROM subscriptions WHERE user_id=?", (user_id,)).fetchone()
        if not r:
            return {"user_id": user_id, "plan": "free", "status": "active",
                    "started_at": None, "expires_at": None, "billing_cycle": "monthly"}
        d = dict(r)
        # انتهاء تلقائي
        if d["plan"] != "free" and d["expires_at"] and d["expires_at"] < int(time.time()):
            d["status"] = "expired"
        return d

def activate_subscription(user_id, plan, days=30, conn=None, cycle="monthly", extra_days=0.0):
    """يفعّل الاشتراك ويرجّع تاريخ الانتهاء.
    التجديد المبكر على **نفس** الباقة يُضاف إلى المتبقّي بدل أن يلغيه (العميل
    دفع عن 30 يوماً فيأخذها كاملة). تغيير الباقة أو اشتراك منتهٍ يبدأ من الآن."""
    now = int(time.time())
    base, started = now, now
    with _conn_or(conn) as c:
        if plan != "free":
            r = c.execute("SELECT plan, started_at, expires_at FROM subscriptions WHERE user_id=?",
                          (user_id,)).fetchone()
            if r and r["plan"] == plan and r["expires_at"] and r["expires_at"] > now:
                base = r["expires_at"]                  # مدّد من نهاية الفترة الحالية
                started = r["started_at"] or now        # واحتفظ ببداية الاشتراك الأصلية
        # `extra_days`: رصيد منقول من باقة سابقة (carry_over_days) — بالثانية لا باليوم
        # الكامل، فلا يُقرَّب لصالح أحد.
        exp = base + days * 86400 + int(round(max(0.0, float(extra_days or 0)) * 86400))
        c.execute("INSERT INTO subscriptions(user_id,plan,status,started_at,expires_at,billing_cycle) "
                  "VALUES(?,?, 'active',?,?,?) "
                  "ON CONFLICT(user_id) DO UPDATE SET plan=excluded.plan, status='active', "
                  "started_at=excluded.started_at, expires_at=excluded.expires_at, "
                  "billing_cycle=excluded.billing_cycle",
                  (user_id, plan, started, exp,
                   cycle if cycle in ("monthly", "annual") else "monthly"))
        # تجديد الاشتراك يمسح سجل التذكيرات ليسمح بتذكيرات الدورة التالية
        clear_reminder_log(user_id, conn=c)
    return exp

def _paid_daily_rate(c, user_id, plan):
    """ما دفعه المشترك فعلاً عن اليوم الواحد في باقته، من آخر دفعة معتمدة لها.
    None لو لم يدفع عنها شيئاً (باقة منحها الأدمن يدوياً): لا قيمة مدفوعة تُنقل."""
    r = c.execute("SELECT amount, billing_cycle FROM payments WHERE user_id=? AND plan=? "
                  "AND status='approved' ORDER BY decided_at DESC, id DESC LIMIT 1",
                  (user_id, plan)).fetchone()
    if not r or not r["amount"] or float(r["amount"]) <= 0:
        return None
    return float(r["amount"]) / (365 if r["billing_cycle"] == "annual" else 30)


def carry_over_days(user_id, new_plan, new_period_price, new_days, conn=None, now=None):
    """قيمة ما تبقّى **مدفوعاً** من الباقة الحالية، محوَّلةً إلى أيام في الباقة الجديدة.

    بدونها كان تغيير الباقة يبدأ من الآن ويُسقط المتبقي: مشترك «تاجر» سنوي
    ينتقل إلى «واتساب» بعد شهر كان يخسر 335 يوماً دفع ثمنها. الآن:
        القيمة  = الأيام المتبقية × ما دفعه فعلاً عن اليوم (آخر دفعة معتمدة للباقة)
        الرصيد = القيمة ÷ السعر اليومي للباقة الجديدة
    الترقية تعطي أياماً أقل والتخفيض أياماً أكثر — القيمة نفسها في الحالتين.

    السعر الجديد هو **سعر القائمة** للدورة (`base_amount`) لا المبلغ بعد كود
    الخصم: كود 100% كان سيقسم على صفر، وأي كود كان سيضخّم الرصيد المنقول.

    يرجّع None حين لا شيء يُنقل: نفس الباقة (التمديد في `activate_subscription`
    يتكفّل بها) · المجانية · اشتراك منتهٍ · باقة لم يُدفع عنها شيء.
    """
    now = int(now or time.time())
    try:
        price_new = float(new_period_price or 0)
        new_days = float(new_days or 0)
    except (TypeError, ValueError):
        return None
    if price_new <= 0 or new_days <= 0:
        return None
    with _conn_or(conn) as c:
        s = c.execute("SELECT plan, expires_at FROM subscriptions WHERE user_id=?",
                      (user_id,)).fetchone()
        if (not s or s["plan"] in ("free", new_plan) or not s["expires_at"]
                or s["expires_at"] <= now):
            return None
        rate_old = _paid_daily_rate(c, user_id, s["plan"])
        if not rate_old:
            return None
        remaining = (s["expires_at"] - now) / 86400.0
        value = remaining * rate_old
        return {"from_plan": s["plan"], "remaining_days": remaining,
                "value": round(value, 2), "credit_days": value / (price_new / new_days)}


# ---------- payments ----------
def create_payment(user_id, plan, method, amount, ref, screenshot, img_hash, auto_check,
                   promo_id=None, discount=0, base_amount=None, billing_cycle="monthly"):
    with get_conn() as c:
        cur = c.execute("INSERT INTO payments(user_id,plan,method,amount,ref,screenshot,img_hash,"
                        "auto_check,status,created_at,promo_id,discount,base_amount,billing_cycle) "
                        "VALUES(?,?,?,?,?,?,?,?, 'pending', ?,?,?,?,?)",
                        (user_id, plan, method, amount, ref, screenshot, img_hash, auto_check,
                         int(time.time()), promo_id, discount or 0,
                         base_amount if base_amount is not None else amount,
                         billing_cycle if billing_cycle in ("monthly", "annual") else "monthly"))
        return cur.lastrowid

def get_payment(pid):
    with get_conn() as c:
        r = c.execute("SELECT * FROM payments WHERE id=?", (pid,)).fetchone()
        return dict(r) if r else None

def set_payment_msg(pid, msg_id):
    with get_conn() as c:
        c.execute("UPDATE payments SET admin_msg_id=? WHERE id=?", (msg_id, pid))

def decide_payment(pid, status, conn=None):
    """يحدّث حالة الدفعة إن كانت لسه pending. يرجّع dict الدفعة أو None لو سبق البتّ فيها.
    **ذرّي:** التحديث المشروط (`AND status='pending'`) هو القفل نفسه — SQLite يسلسل
    الكتابة، فطلبان متزامنان (gunicorn threads=4 / زر تليجرام + الويب معاً) لا يمكن
    أن ينجحا معاً؛ الثاني يجد rowcount=0 فيرجّع None ولا يُفعَّل الاشتراك مرتين."""
    with _conn_or(conn) as c:
        cur = c.execute("UPDATE payments SET status=?, decided_at=? WHERE id=? AND status='pending'",
                        (status, int(time.time()), pid))
        if cur.rowcount != 1:
            return None
        r = c.execute("SELECT * FROM payments WHERE id=?", (pid,)).fetchone()
        return dict(r) if r else None

def finalize_payment(pid, status):
    """قرار نهائي مشترك (ويب/بوت): يبتّ الدفعة ويفعّل الاشتراك عند الموافقة.

    **معاملة واحدة:** البتّ والتفعيل وحرق كود الخصم واحتساب العمولة تجري كلها
    على اتصال واحد، فإما تُثبَّت جميعاً أو لا شيء منها. لو انهارت العملية في
    المنتصف يُغلق الاتصال بلا commit فيتراجع كل شيء — ولا تبقى دفعة «معتمدة»
    بلا اشتراك مفعَّل. الحراسة ضد الازدواج تبقى كما هي: التحديث المشروط في
    `decide_payment`، وقيد UNIQUE في `consume_promo`، وشرط `converted_at IS NULL`
    في `credit_referral`."""
    promo = ref = None
    with get_conn() as c:
        row = decide_payment(pid, status, conn=c)
        if not row:
            return None
        if status == "approved" and row["plan"] == WALLET_PLAN:
            # شحن محفظة لا اشتراك. يمرّ بنفس مسار الإيصال والموافقة المُجرَّب
            # (فحص الصورة · زرّ الأدمن · كشف التكرار)، وداخل **نفس المعاملة**
            # فلا تبقى دفعة معتمدة بلا رصيد.
            row["wallet_after"] = wallet_topup(
                row["user_id"], int(round(float(row["amount"] or 0) * 100)),
                ref=f"payment:{row['id']}", note="topup", conn=c)
        elif status == "approved" and addon_bot_id(row["plan"]):
            # إضافة لبوت بعينه (تحصيل المدفوعات · منتجاتي من تليجرام) — 30 يوماً تُمدّ من
            # انتهائها لو ما زالت سارية. داخل نفس المعاملة: لا دفعة معتمدة بلا إضافة مفعّلة.
            kind, bid = parse_addon_plan(row["plan"])
            if c.execute("SELECT 1 FROM bots WHERE id=?", (bid,)).fetchone():
                row["addon_kind"] = kind
                row["addon_expires"] = extend_addon(bid, kind, days=30, conn=c)
            else:
                log.warning("payment #%s approved for the add-on of deleted bot #%s", row["id"], bid)
        elif status == "approved":
            # تاريخ الانتهاء يُرجَع مع الصف لإيصال الإيميل (mailer.send_payment_receipt)
            # المدة من **دورة الدفعة نفسها** لا من افتراض ثابت — فدفعة سنوية
            # تفعّل 365 يوماً حتى لو اعتُمدت من زرّ تليجرام بعد أيام.
            cyc = row.get("billing_cycle") or "monthly"
            days = 365 if cyc == "annual" else 30
            # تغيير الباقة لا يُسقط ما دُفع: قيمة الأيام المتبقية تُنقل إلى الجديدة.
            # تُحسب **قبل** التفعيل لأنه يكتب فوق صفّ الاشتراك الحالي، وداخل نفس
            # المعاملة فلا تُنقل قيمة لتسوية لم تثبت.
            carry = carry_over_days(row["user_id"], row["plan"],
                                    row.get("base_amount") or row["amount"], days, conn=c)
            row["carried_days"] = int(carry["credit_days"]) if carry else 0
            row["expires_at"] = activate_subscription(
                row["user_id"], row["plan"], days=days, conn=c, cycle=cyc,
                extra_days=carry["credit_days"] if carry else 0)
            # التسوية هنا لا في المسار الويبي وحده: الموافقة تأتي أيضاً من زرّ
            # تليجرام، ولو تُركت بالخارج لفات الكود والعمولة على ذلك المسار.
            if row.get("promo_id"):
                promo = consume_promo(row["promo_id"], row["user_id"], row["id"], conn=c)
            ref = credit_referral(row["user_id"], row["id"], row["amount"], conn=c)
    # التسجيل بعد خروج `with` فقط — أي بعد commit. سطر «approved» في السجل يعني
    # أن التسوية ثبتت فعلاً، لا أنها بدأت.
    log.info("payment #%s %s user=%s plan=%s amount=%s expires_at=%s carried_days=%s "
             "promo=%s referral=%s",
             row["id"], status, row["user_id"], row["plan"], row["amount"],
             row.get("expires_at"), row.get("carried_days", 0), promo, ref)
    # تحويل مؤكَّد لم يُبلَّغ به بعد. هنا لا في مسار الويب وحده لأن الاعتماد يأتي
    # أيضاً من زرّ تليجرام — ولأن الاعتماد يقع في **جلسة الأدمن** لا العميل، فلا
    # سبيل لإطلاق الحدث لحظتها. app.py يلتقطه ويمسحه عند أول صفحة يفتحها العميل
    # (راجع `_claim_purchase`). بعد الـcommit: لا نعلن تحويلاً لم يثبت.
    if status == "approved" and row["plan"] != WALLET_PLAN and not addon_bot_id(row["plan"]):
        try:
            set_setting(row["user_id"], "track_purchase", json.dumps(
                {"id": row["id"], "plan": row["plan"], "value": float(row["amount"] or 0),
                 "cycle": row.get("billing_cycle") or "monthly"}))
        except Exception:
            log.warning("could not queue the purchase conversion for payment #%s", row["id"])
    return row

def img_hash_seen(img_hash, exclude_id=None):
    with get_conn() as c:
        if exclude_id:
            r = c.execute("SELECT COUNT(*) FROM payments WHERE img_hash=? AND id<>?", (img_hash, exclude_id)).fetchone()
        else:
            r = c.execute("SELECT COUNT(*) FROM payments WHERE img_hash=?", (img_hash,)).fetchone()
        return r[0] > 0

def list_payments(user_id=None, limit=100):
    with get_conn() as c:
        if user_id:
            rows = c.execute("SELECT * FROM payments WHERE user_id=? ORDER BY created_at DESC, id DESC LIMIT ?", (user_id, limit)).fetchall()
        else:
            rows = c.execute("SELECT * FROM payments ORDER BY created_at DESC, id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]

def count_user_bots(user_id):
    with get_conn() as c:
        return c.execute("SELECT COUNT(*) FROM bots WHERE owner_id=?", (user_id,)).fetchone()[0]


def update_user_credentials(user_id, username=None, pw_hash=None):
    """تحديث اسم المستخدم و/أو كلمة المرور. يرجّع (ok, error)."""
    with get_conn() as c:
        if username:
            ex = c.execute("SELECT id FROM users WHERE username=? AND id<>?", (username, user_id)).fetchone()
            if ex:
                return False, "username_taken"
            c.execute("UPDATE users SET username=? WHERE id=?", (username, user_id))
        if pw_hash:
            c.execute("UPDATE users SET pw_hash=? WHERE id=?", (pw_hash, user_id))
    return True, None

def get_user_by_email(email):
    if not email:
        return None
    with get_conn() as c:
        r = c.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
        return dict(r) if r else None

def set_user_email(user_id, email):
    """يضبط الإيميل (أو يمسحه بـ None). يرجّع (ok, error). الفهرس الفريد هو
    الحارس الأخير لو سبق طلبٌ متزامن الفحصَ."""
    with get_conn() as c:
        if email and c.execute("SELECT id FROM users WHERE email=? AND id<>?",
                               (email, user_id)).fetchone():
            return False, "email_taken"
        try:
            # بريد جديد = غير مؤكَّد حتى يثبت صاحبه ملكيته
            c.execute("UPDATE users SET email_verified_at=NULL WHERE id=? AND COALESCE(email,'')<>COALESCE(?,'')",
                      (user_id, email or None))
            c.execute("UPDATE users SET email=? WHERE id=?", (email or None, user_id))
        except sqlite3.IntegrityError:
            return False, "email_taken"
    return True, None

# ---------- استرجاع كلمة المرور ----------
def create_password_reset(user_id, token_hash, ttl=3600):
    """رابط واحد صالح لكل مستخدم: الطلب الجديد يُبطل ما قبله وينظّف المنتهي."""
    now = int(time.time())
    with get_conn() as c:
        c.execute("DELETE FROM password_resets WHERE user_id=? OR expires_at<?", (user_id, now))
        c.execute("INSERT INTO password_resets(token_hash,user_id,created_at,expires_at) VALUES(?,?,?,?)",
                  (token_hash, user_id, now, now + ttl))

def get_password_reset(token_hash):
    """الصف إن كان الرابط صالحاً (لم يُستعمل ولم ينتهِ)، وإلا None."""
    with get_conn() as c:
        r = c.execute("SELECT * FROM password_resets WHERE token_hash=? AND used_at IS NULL "
                      "AND expires_at>?", (token_hash, int(time.time()))).fetchone()
        return dict(r) if r else None

def consume_password_reset(token_hash, pw_hash):
    """يستهلك الرابط ويضبط كلمة المرور في معاملة واحدة. يرجّع user_id أو None.
    **ذرّي:** التحديث المشروط (`used_at IS NULL`) هو القفل — طلبان متزامنان بنفس
    الرابط لا ينجحان معاً (نفس نمط `decide_payment`)."""
    now = int(time.time())
    with get_conn() as c:
        r = c.execute("SELECT user_id FROM password_resets WHERE token_hash=? AND used_at IS NULL "
                      "AND expires_at>?", (token_hash, now)).fetchone()
        if not r:
            return None
        cur = c.execute("UPDATE password_resets SET used_at=? WHERE token_hash=? AND used_at IS NULL",
                        (now, token_hash))
        if cur.rowcount != 1:
            return None
        c.execute("UPDATE users SET pw_hash=? WHERE id=?", (pw_hash, r["user_id"]))
        return r["user_id"]

def admin_create_user(username, pw_hash, role="user"):
    """إنشاء حساب بواسطة الأدمن بدور محدد. يرجّع (user_id, error)."""
    if role not in ("admin", "support", "user"):
        role = "user"
    with get_conn() as c:
        if c.execute("SELECT id FROM users WHERE username=?", (username,)).fetchone():
            return None, "username_taken"
        cur = c.execute("INSERT INTO users(username,pw_hash,role,created_at) VALUES(?,?,?,?)",
                        (username, pw_hash, role, int(time.time())))
        return cur.lastrowid, None


# ---------- إدارة المستخدمين (أدمن) ----------
def get_user(user_id):
    with get_conn() as c:
        r = c.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
        return dict(r) if r else None

def set_user_role(user_id, role):
    if role not in ("admin", "support", "user"): return
    with get_conn() as c:
        # لا تسمح بتغيير دور المستخدم رقم 1 (المالك الأساسي)
        if user_id == 1: return
        c.execute("UPDATE users SET role=? WHERE id=?", (role, user_id))

def set_user_blocked(user_id, blocked):
    with get_conn() as c:
        if user_id == 1: return
        c.execute("UPDATE users SET is_blocked=? WHERE id=?", (1 if blocked else 0, user_id))

def list_all_users(limit=500):
    with get_conn() as c:
        rows = c.execute("""
            SELECT u.id, u.username, u.role, u.is_blocked, u.created_at,
                   u.email, u.email_verified_at, u.phone, u.phone_verified_at, u.entity_type, u.age,
                   u.verify_required,
                   COALESCE(s.plan,'free') AS plan, s.status AS sub_status, s.expires_at,
                   (SELECT COUNT(*) FROM bots b WHERE b.owner_id=u.id) AS bots
            FROM users u LEFT JOIN subscriptions s ON s.user_id=u.id
            ORDER BY u.id DESC LIMIT ?""", (limit,)).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            if d["plan"] != "free" and d["expires_at"] and d["expires_at"] < int(time.time()):
                d["sub_status"] = "expired"
            out.append(d)
        return out

def platform_stats():
    with get_conn() as c:
        one = lambda q, *a: c.execute(q, a).fetchone()[0]
        total_users = one("SELECT COUNT(*) FROM users")
        total_bots = one("SELECT COUNT(*) FROM bots")
        active_bots = one("SELECT COUNT(*) FROM bots WHERE is_active=1")
        paying = one("SELECT COUNT(*) FROM subscriptions WHERE plan<>'free' AND status='active' AND (expires_at IS NULL OR expires_at>?)", int(time.time()))
        pending = one("SELECT COUNT(*) FROM payments WHERE status='pending'")
        revenue = one("SELECT COALESCE(SUM(amount),0) FROM payments WHERE status='approved'")
        by_plan = {r[0]: r[1] for r in c.execute(
            "SELECT plan, COUNT(*) FROM subscriptions WHERE status='active' GROUP BY plan").fetchall()}
        return {"users": total_users, "bots": total_bots, "active_bots": active_bots,
                "paying": paying, "pending": pending, "revenue": round(revenue, 2),
                "by_plan": by_plan}

def revenue_daily(days=14):
    import datetime
    with get_conn() as c:
        rows = c.execute("SELECT decided_at, amount FROM payments WHERE status='approved' AND decided_at IS NOT NULL").fetchall()
    today = datetime.date.today()
    labels = [(today - datetime.timedelta(days=i)).isoformat() for i in range(days-1, -1, -1)]
    rev = {d: 0 for d in labels}
    for ts, amt in rows:
        d = datetime.date.fromtimestamp(ts).isoformat()
        if d in rev: rev[d] += amt
    # مستخدمون جدد يومياً
    urows = c.execute if False else None
    with get_conn() as c2:
        us = c2.execute("SELECT created_at FROM users").fetchall()
    newu = {d: 0 for d in labels}
    for (ts,) in us:
        d = datetime.date.fromtimestamp(ts).isoformat()
        if d in newu: newu[d] += 1
    return {"labels": labels, "revenue": [rev[d] for d in labels], "new_users": [newu[d] for d in labels]}

def all_pending_payments():
    with get_conn() as c:
        rows = c.execute("""SELECT p.*, u.username FROM payments p JOIN users u ON u.id=p.user_id
                            WHERE p.status='pending' ORDER BY p.created_at DESC, p.id DESC""").fetchall()
        return [dict(r) for r in rows]

def admin_chat_ids():
    """معرّفات تليجرام لكل الأدمنز (من إعداد المنصة admin_chat_id، ويمكن التوسّع)."""
    v = get_platform("admin_chat_id", "")
    return [x.strip() for x in v.split(",") if x.strip()]

# ---------- طلبات البوتات المخصّصة ----------
def create_bot_request(user_id, username, business, description, budget, contact):
    with get_conn() as c:
        cur = c.execute("INSERT INTO bot_requests(user_id,username,business,description,budget,contact,status,created_at) "
                        "VALUES(?,?,?,?,?,?, 'new', ?)",
                        (user_id, username, business, description, budget, contact, int(time.time())))
        return cur.lastrowid

def list_bot_requests(limit=200):
    with get_conn() as c:
        rows = c.execute("SELECT * FROM bot_requests ORDER BY created_at DESC, id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]

def count_new_bot_requests():
    with get_conn() as c:
        return c.execute("SELECT COUNT(*) FROM bot_requests WHERE status='new'").fetchone()[0]

def set_bot_request_status(req_id, status):
    if status not in ("new", "in_progress", "done", "rejected"):
        return
    with get_conn() as c:
        c.execute("UPDATE bot_requests SET status=? WHERE id=?", (status, req_id))

# ---------- تذاكر الدعم والشكاوى (support_desk.py) ----------
def create_ticket(user_id, kind, subject, body):
    now = int(time.time())
    with get_conn() as c:
        tid = c.execute("INSERT INTO tickets(user_id,kind,subject,status,created_at,updated_at) "
                        "VALUES(?,?,?,'open',?,?)", (user_id, kind, subject, now, now)).lastrowid
        c.execute("INSERT INTO ticket_msgs(ticket_id,sender,body,via,created_at) VALUES(?,?,?,?,?)",
                  (tid, "user", body, "web", now))
        _notify_staff(c, "ticket_new", {"subject": subject[:120], "user": _username(c, user_id)}, f"/admin/tickets#t{tid}")
        return tid

def add_ticket_msg(tid, sender, body, via="web"):
    """رسالة العميل تفتح التذكرة، ورد الفريق يجعلها «اتردّ عليها». الطرف الآخر يصله إشعار."""
    now = int(time.time())
    with get_conn() as c:
        c.execute("INSERT INTO ticket_msgs(ticket_id,sender,body,via,created_at) VALUES(?,?,?,?,?)",
                  (tid, sender, body, via, now))
        c.execute("UPDATE tickets SET status=?, updated_at=? WHERE id=?",
                  ("answered" if sender == "staff" else "open", now, tid))
        t = c.execute("SELECT user_id, subject FROM tickets WHERE id=?", (tid,)).fetchone()
        if t and sender == "staff":
            _notify(c, t["user_id"], "ticket_reply", {"subject": t["subject"][:120]}, f"/support#t{tid}")
        elif t:
            _notify_staff(c, "ticket_user", {"subject": t["subject"][:120], "user": _username(c, t["user_id"])}, f"/admin/tickets#t{tid}")

def get_ticket(tid):
    with get_conn() as c:
        r = c.execute("SELECT t.*, u.username FROM tickets t LEFT JOIN users u ON u.id=t.user_id "
                      "WHERE t.id=?", (tid,)).fetchone()
        return dict(r) if r else None

def list_tickets(user_id=None, limit=200):
    """التذاكر مع رسائلها، المفتوحة أولاً."""
    q = ("SELECT t.*, u.username FROM tickets t LEFT JOIN users u ON u.id=t.user_id "
         + ("WHERE t.user_id=? " if user_id else "")
         + "ORDER BY CASE t.status WHEN 'open' THEN 0 WHEN 'answered' THEN 1 ELSE 2 END, "
           "t.updated_at DESC, t.id DESC LIMIT ?")
    with get_conn() as c:
        rows = [dict(r) for r in c.execute(q, ([user_id] if user_id else []) + [limit]).fetchall()]
        if rows:
            ids = [r["id"] for r in rows]
            by = {}
            for m in c.execute(f"SELECT * FROM ticket_msgs WHERE ticket_id IN ({','.join('?' * len(ids))}) "
                               "ORDER BY id", ids).fetchall():
                by.setdefault(m["ticket_id"], []).append(dict(m))
            for r in rows:
                r["msgs"] = by.get(r["id"], [])
        return rows

def set_ticket_status(tid, status):
    """True لو تغيّرت الحالة فعلاً (زرّ «تم الحل» المكرّر لا يعيد شيئاً)."""
    if status not in ("open", "answered", "closed"):
        return False
    with get_conn() as c:
        cur = c.execute("UPDATE tickets SET status=?, updated_at=? WHERE id=? AND status<>?",
                        (status, int(time.time()), tid, status))
        return cur.rowcount == 1

def count_open_tickets():
    with get_conn() as c:
        return c.execute("SELECT COUNT(*) FROM tickets WHERE status='open'").fetchone()[0]

def open_ticket_of_kind(user_id, kind):
    """أحدث تذكرة غير مقفولة من نوع معيّن للمستخدم (طلب ربط واتساب مثلاً) — أو None."""
    with get_conn() as c:
        r = c.execute("SELECT id FROM tickets WHERE user_id=? AND kind=? AND status<>'closed' "
                      "ORDER BY id DESC LIMIT 1", (user_id, kind)).fetchone()
        return r[0] if r else None

# ---------- الإيصالات المرفوضة آلياً ----------
def img_hash_active(img_hash):
    """إيصال بنفس البصمة في دفعة معلّقة أو معتمدة = إعادة استخدام. المرفوضة لا تُحسب:
    الأدمن قد يرفض لسبب آخر (باقة خطأ) فيعيد العميل رفع نفس الإيصال."""
    with get_conn() as c:
        return c.execute("SELECT 1 FROM payments WHERE img_hash=? AND status IN ('pending','approved') "
                         "LIMIT 1", (img_hash,)).fetchone() is not None

def log_receipt_refusal(user_id, reason, img_hash=None):
    with get_conn() as c:
        c.execute("INSERT INTO receipt_refusals(user_id,reason,img_hash,created_at) VALUES(?,?,?,?)",
                  (user_id, reason, img_hash, int(time.time())))

def count_receipt_refusals(user_id=None, since=0, exclude=()):
    q, args = "SELECT COUNT(*) FROM receipt_refusals WHERE created_at>=?", [since]
    if user_id is not None:
        q += " AND user_id=?"; args.append(user_id)
    if exclude:
        q += f" AND reason NOT IN ({','.join('?' * len(exclude))})"; args += list(exclude)
    with get_conn() as c:
        return c.execute(q, args).fetchone()[0]

def recent_receipt_refusals(limit=8):
    with get_conn() as c:
        rows = c.execute("SELECT r.id, r.reason, r.created_at, u.username FROM receipt_refusals r "
                         "LEFT JOIN users u ON u.id=r.user_id ORDER BY r.id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]


if __name__ == "__main__":
    init_db(); print("DB ready:", DB_PATH)


# ============================================================================
#  التسعير والعروض والأفيليت — كل الحسابات هنا، ولا مبلغ يأتي من الواجهة.
# ============================================================================

# ---------- تجاوزات أسعار الباقات ----------
def plan_overrides():
    """{plan_id: {price, discount_pct}} لكل ما ضبطه المالك."""
    with get_conn() as c:
        return {r["plan_id"]: dict(r)
                for r in c.execute("SELECT * FROM plan_overrides").fetchall()}

def set_plan_override(plan_id, price=None, discount_pct=0):
    """price=None يعني: ارجع لسعر plans.py الأساسي."""
    try:
        discount_pct = max(0.0, min(90.0, float(discount_pct or 0)))
    except (TypeError, ValueError):
        discount_pct = 0.0
    if price in ("", None):
        price = None
    else:
        try:
            price = max(0.0, float(price))
        except (TypeError, ValueError):
            price = None
    with get_conn() as c:
        c.execute("INSERT INTO plan_overrides(plan_id,price,discount_pct,updated_at) VALUES(?,?,?,?) "
                  "ON CONFLICT(plan_id) DO UPDATE SET price=excluded.price, "
                  "discount_pct=excluded.discount_pct, updated_at=excluded.updated_at",
                  (plan_id, price, discount_pct, int(time.time())))

# ---------- أكواد الخصم ----------
def list_promos(limit=200):
    with get_conn() as c:
        return [dict(r) for r in c.execute(
            "SELECT * FROM promos ORDER BY created_at DESC, id DESC LIMIT ?", (limit,)).fetchall()]

def create_promo(code, kind, value, plan=None, max_uses=None,
                 expires_at=None, per_user_once=1):
    code = (code or "").strip().upper()
    if not code or kind not in ("percent", "fixed"):
        return None, "invalid"
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None, "invalid"
    if value <= 0 or (kind == "percent" and value > 90):
        return None, "invalid"
    with get_conn() as c:
        try:
            cur = c.execute(
                "INSERT INTO promos(code,kind,value,plan,max_uses,per_user_once,expires_at,created_at) "
                "VALUES(?,?,?,?,?,?,?,?)",
                (code, kind, value, plan or None,
                 int(max_uses) if max_uses else None,
                 1 if per_user_once else 0,
                 int(expires_at) if expires_at else None, int(time.time())))
            return cur.lastrowid, None
        except sqlite3.IntegrityError:
            return None, "duplicate"

def ensure_promo(code, kind, value, plan=None, max_uses=None, per_user_once=1):
    """ينشئ كوداً مرة واحدة فقط (لو الكود غير موجود) ويرجّع صفّه.

    للأكواد التي تزرعها المنصة نفسها عند الإقلاع. حذف المالك للكود لاحقاً قرارٌ
    له: المستدعي يحرس بعلامة في `platform` فلا يعود الكود بعد حذفه."""
    row = get_promo_by_code(code)
    if row:
        return row
    create_promo(code, kind, value, plan=plan, max_uses=max_uses, per_user_once=per_user_once)
    return get_promo_by_code(code)


def set_promo_active(promo_id, active):
    with get_conn() as c:
        c.execute("UPDATE promos SET is_active=? WHERE id=?", (1 if active else 0, promo_id))

def delete_promo(promo_id):
    with get_conn() as c:
        c.execute("DELETE FROM promos WHERE id=?", (promo_id,))

def get_promo_by_code(code):
    with get_conn() as c:
        r = c.execute("SELECT * FROM promos WHERE code=?",
                      ((code or "").strip().upper(),)).fetchone()
        return dict(r) if r else None

def promo_used_by(promo_id, user_id):
    with get_conn() as c:
        return c.execute("SELECT COUNT(*) FROM promo_uses WHERE promo_id=? AND user_id=?",
                         (promo_id, user_id)).fetchone()[0] > 0

def consume_promo(promo_id, user_id, payment_id, conn=None):
    """يُستدعى عند اعتماد الدفعة فقط — لا يُحرق الكود على دفعة مرفوضة.
    ذرّي: القيد UNIQUE(promo_id,payment_id) يمنع الاحتساب مرتين.
    التقاط IntegrityError آمن داخل معاملة مشتركة: SQLite يتراجع عن العبارة
    الفاشلة وحدها لا عن المعاملة كلها."""
    with _conn_or(conn) as c:
        try:
            c.execute("INSERT INTO promo_uses(promo_id,user_id,payment_id,created_at) VALUES(?,?,?,?)",
                      (promo_id, user_id, payment_id, int(time.time())))
        except sqlite3.IntegrityError:
            return False
        c.execute("UPDATE promos SET used=used+1 WHERE id=?", (promo_id,))
        return True

def promo_stats(promo_id):
    with get_conn() as c:
        r = c.execute("SELECT COUNT(*) n, COALESCE(SUM(p.discount),0) saved "
                      "FROM promo_uses u LEFT JOIN payments p ON p.id=u.payment_id "
                      "WHERE u.promo_id=?", (promo_id,)).fetchone()
        return {"uses": r[0], "saved": round(r[1] or 0, 2)}

# ---------- الأفيليت ----------
def get_affiliate(user_id):
    with get_conn() as c:
        r = c.execute("SELECT * FROM affiliates WHERE user_id=?", (user_id,)).fetchone()
        return dict(r) if r else None

def get_affiliate_by_code(code):
    with get_conn() as c:
        r = c.execute("SELECT * FROM affiliates WHERE code=? AND is_active=1",
                      ((code or "").strip().upper(),)).fetchone()
        return dict(r) if r else None

def ensure_affiliate(user_id, code, rate_pct=20):
    """ينشئ حساب أفيليت إن لم يوجد. يرجّع الصف."""
    cur = get_affiliate(user_id)
    if cur:
        return cur
    with get_conn() as c:
        c.execute("INSERT OR IGNORE INTO affiliates(user_id,code,rate_pct,created_at) VALUES(?,?,?,?)",
                  (user_id, code.strip().upper(), float(rate_pct), int(time.time())))
    return get_affiliate(user_id)

def set_affiliate(user_id, rate_pct=None, is_active=None):
    sets, args = [], []
    if rate_pct is not None:
        try:
            sets.append("rate_pct=?"); args.append(max(0.0, min(90.0, float(rate_pct))))
        except (TypeError, ValueError):
            pass
    if is_active is not None:
        sets.append("is_active=?"); args.append(1 if is_active else 0)
    if not sets:
        return
    args.append(user_id)
    with get_conn() as c:
        c.execute("UPDATE affiliates SET " + ",".join(sets) + " WHERE user_id=?", args)

def affiliate_payout(user_id, amount):
    """يسجّل صرف عمولة. لا يسمح بتجاوز المستحقّ."""
    with get_conn() as c:
        r = c.execute("SELECT total_earned, paid_out FROM affiliates WHERE user_id=?",
                      (user_id,)).fetchone()
        if not r:
            return False
        due = (r["total_earned"] or 0) - (r["paid_out"] or 0)
        try:
            amount = float(amount)
        except (TypeError, ValueError):
            return False
        if amount <= 0 or amount > due + 1e-9:
            return False
        c.execute("UPDATE affiliates SET paid_out=paid_out+? WHERE user_id=?", (amount, user_id))
        return True

def attach_referral(referred_user_id, code):
    """يربط مستخدماً جديداً بمُحيله. مرة واحدة، ولا يحيل أحد نفسه."""
    aff = get_affiliate_by_code(code)
    if not aff or aff["user_id"] == referred_user_id:
        return False
    with get_conn() as c:
        try:
            c.execute("INSERT INTO referrals(affiliate_user_id,referred_user_id,created_at) VALUES(?,?,?)",
                      (aff["user_id"], referred_user_id, int(time.time())))
            c.execute("UPDATE users SET ref_by=? WHERE id=?", (aff["code"], referred_user_id))
            return True
        except sqlite3.IntegrityError:
            return False

# العمولة تُحتسب على كل دفعة اشتراك معتمدة خلال 12 شهراً من **أول** دفعة للمُحال، ثم تتوقف.
# عمولة أبدية بنسبة 20% = خُمس إيراد المشترك يخرج ما دام مشتركاً (قرار الإدارة 2026-09-21:
# سقف 12 شهراً). لا أثر رجعي: الاحتساب يقع لحظة الاعتماد فقط، فالدفعات السابقة لا تمرّ هنا.
RECURRING_MONTHS = 12
RECURRING_WINDOW = 365 * 86400


def credit_referral(referred_user_id, payment_id, amount, conn=None):
    """عمولة دفعة اشتراك معتمدة للمُحال. يرجّع (affiliate_user_id, commission) أو None.

    الأولى: تُحوِّل الإحالة (`referrals.converted_at`) — مسارها كما كان حرفياً.
    التالية داخل سقف الـ12 شهراً: سطر في `affiliate_commissions` (UNIQUE على الدفعة).
    ذرّي في الحالتين: التحديث المشروط / القيد الفريد يمنعان الاحتساب المزدوج."""
    with _conn_or(conn) as c:
        r = c.execute("SELECT r.id, r.affiliate_user_id, r.payment_id, r.converted_at, "
                      "a.rate_pct, a.is_active "
                      "FROM referrals r JOIN affiliates a ON a.user_id=r.affiliate_user_id "
                      "WHERE r.referred_user_id=?", (referred_user_id,)).fetchone()
        if not r or not r["is_active"]:
            return None
        if r["converted_at"] is not None:
            return _credit_renewal(c, r, referred_user_id, payment_id, amount)
        commission = round(float(amount) * float(r["rate_pct"]) / 100.0, 2)
        cur = c.execute("UPDATE referrals SET payment_id=?, commission=?, converted_at=? "
                        "WHERE id=? AND converted_at IS NULL",
                        (payment_id, commission, int(time.time()), r["id"]))
        if cur.rowcount != 1:
            return None
        c.execute("UPDATE affiliates SET total_earned=total_earned+? WHERE user_id=?",
                  (commission, r["affiliate_user_id"]))
        return (r["affiliate_user_id"], commission)


def _credit_renewal(c, r, referred_user_id, payment_id, amount):
    if payment_id == r["payment_id"]:                  # نفس الدفعة الأولى تُعتمد ثانيةً
        return None
    now = int(time.time())
    if now - int(r["converted_at"]) > RECURRING_WINDOW:  # خارج السقف — لا عمولة
        return None
    commission = round(float(amount) * float(r["rate_pct"]) / 100.0, 2)
    if commission <= 0:
        return None
    try:
        c.execute("INSERT INTO affiliate_commissions(referral_id,affiliate_user_id,referred_user_id,"
                  "payment_id,amount,commission,created_at) VALUES(?,?,?,?,?,?,?)",
                  (r["id"], r["affiliate_user_id"], referred_user_id, payment_id,
                   float(amount), commission, now))
    except sqlite3.IntegrityError:                     # احتُسبت من قبل
        return None
    c.execute("UPDATE affiliates SET total_earned=total_earned+? WHERE user_id=?",
              (commission, r["affiliate_user_id"]))
    return (r["affiliate_user_id"], commission)


META_EVENTS_KEEP = 3000


def log_meta_event(account, kind, summary="", bot_id=None, peer=None):
    now = int(time.time())
    with get_conn() as c:
        cur = c.execute("INSERT INTO meta_events(bot_id,account,kind,peer,summary,created_at) "
                        "VALUES(?,?,?,?,?,?)", (bot_id, account, kind, peer, (summary or "")[:500], now))
        if cur.lastrowid % 200 == 0:                 # قصّ دوري لا مع كل حدث
            c.execute("DELETE FROM meta_events WHERE id <= ?", (cur.lastrowid - META_EVENTS_KEEP,))
        return cur.lastrowid


def list_meta_events(limit=150, account=None):
    q, args = "SELECT * FROM meta_events", []
    if account:
        q += " WHERE account=?"; args.append(account)
    q += " ORDER BY id DESC LIMIT ?"; args.append(int(limit))
    with get_conn() as c:
        return [dict(r) for r in c.execute(q, args).fetchall()]


def meta_bots():
    """كل بوتات ماسنجر/إنستجرام في المنصة (للأدمن) — بلا الإعداد (فيه توكن الصفحة)."""
    with get_conn() as c:
        rows = c.execute("SELECT b.id, b.owner_id, b.name, b.channel, b.is_active, b.created_at, "
                         "u.username FROM bots b JOIN users u ON u.id=b.owner_id "
                         "WHERE b.channel IN ('messenger','instagram') ORDER BY b.id DESC").fetchall()
    out = []
    for r in rows:
        d = dict(r)
        full = get_bot(d["id"]) or {}
        d["account"] = full.get("token") or ""
        try:
            d["page_id"] = json.loads(full.get("config_json") or "{}").get("page_id", "")
        except ValueError:
            d["page_id"] = ""
        out.append(d)
    return out


def commission_of_payment(payment_id):
    """عمولة دفعة بعينها (أولى أو تجديد) ← {affiliate_user_id, commission, renewal} أو None."""
    with get_conn() as c:
        r = c.execute("SELECT affiliate_user_id, commission FROM referrals WHERE payment_id=?",
                      (payment_id,)).fetchone()
        if r and r["commission"]:
            return {"affiliate_user_id": r["affiliate_user_id"], "commission": r["commission"],
                    "renewal": False}
        r = c.execute("SELECT affiliate_user_id, commission FROM affiliate_commissions WHERE payment_id=?",
                      (payment_id,)).fetchone()
        return ({"affiliate_user_id": r["affiliate_user_id"], "commission": r["commission"],
                 "renewal": True} if r else None)


def affiliate_summary(user_id):
    """أرقام لوحة الشريك. `expected_monthly` **تقدير** لا وعد: ما تدرّه الإحالات النشطة
    داخل السقف شهرياً بسعر باقتها الحالي (السنوية ÷ 12)، ويسقط بالإلغاء أو انتهاء السقف."""
    import plans
    now = int(time.time())
    with get_conn() as c:
        r = c.execute("SELECT COUNT(*) signups, "
                      "COALESCE(SUM(CASE WHEN converted_at IS NOT NULL THEN 1 ELSE 0 END),0) conversions "
                      "FROM referrals WHERE affiliate_user_id=?", (user_id,)).fetchone()
        renewals = c.execute("SELECT COALESCE(SUM(commission),0) FROM affiliate_commissions "
                             "WHERE affiliate_user_id=?", (user_id,)).fetchone()[0]
        rate = c.execute("SELECT rate_pct FROM affiliates WHERE user_id=?", (user_id,)).fetchone()
        rate = float(rate["rate_pct"]) if rate else 0.0
        active = c.execute(
            "SELECT s.plan, s.billing_cycle FROM referrals r "
            "JOIN subscriptions s ON s.user_id=r.referred_user_id "
            "WHERE r.affiliate_user_id=? AND r.converted_at IS NOT NULL AND r.converted_at>=? "
            "AND s.status='active' AND s.plan<>'free' AND (s.expires_at IS NULL OR s.expires_at>?)",
            (user_id, now - RECURRING_WINDOW, now)).fetchall()
    monthly = 0.0
    for a in active:
        p = plans.plan(a["plan"])["price"]
        monthly += (plans.annual_price(a["plan"]) / 12.0) if a["billing_cycle"] == "annual" else p
    return {"signups": r["signups"], "conversions": r["conversions"],
            "renewals": round(float(renewals), 2), "active": len(active),
            "expected_monthly": round(monthly * rate / 100.0, 2),
            "months": RECURRING_MONTHS}

def list_affiliates(limit=200):
    with get_conn() as c:
        rows = c.execute(
            "SELECT a.*, u.username, "
            "(SELECT COUNT(*) FROM referrals r WHERE r.affiliate_user_id=a.user_id) signups, "
            "(SELECT COUNT(*) FROM referrals r WHERE r.affiliate_user_id=a.user_id "
            "   AND r.converted_at IS NOT NULL) conversions "
            "FROM affiliates a JOIN users u ON u.id=a.user_id "
            "ORDER BY a.total_earned DESC, a.created_at DESC LIMIT ?", (limit,)).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["due"] = round((d["total_earned"] or 0) - (d["paid_out"] or 0), 2)
            out.append(d)
        return out

def referral_of(referred_user_id):
    with get_conn() as c:
        r = c.execute("SELECT * FROM referrals WHERE referred_user_id=?",
                      (referred_user_id,)).fetchone()
        return dict(r) if r else None


# ---------- تذكيرات الاشتراك ----------
def reminder_sent(user_id, kind):
    """هل أُرسل هذا النوع من التذكير لهذا المستخدم في الدورة الحالية؟"""
    with get_conn() as c:
        return c.execute("SELECT COUNT(*) FROM reminder_log WHERE user_id=? AND kind=?",
                         (user_id, kind)).fetchone()[0] > 0

def log_reminder(user_id, kind):
    """يسجّل إرسال تذكير. UNIQUE يمنع التكرار."""
    with get_conn() as c:
        try:
            c.execute("INSERT INTO reminder_log(user_id,kind,sent_at) VALUES(?,?,?)",
                      (user_id, kind, int(time.time())))
            return True
        except sqlite3.IntegrityError:
            return False

def clear_reminder_log(user_id, conn=None):
    """يمسح سجل التذكيرات عند تجديد الاشتراك."""
    with _conn_or(conn) as c:
        c.execute("DELETE FROM reminder_log WHERE user_id=?", (user_id,))

def expiring_subscriptions(within_days=3):
    """يجلب الاشتراكات المدفوعة التي تنتهي خلال N يوم (ولم تنتهِ بعد).
    يرجّع [{user_id, username, plan, expires_at, tg_chat_id}, ...].
    tg_chat_id: الربط الصريح من settings، وإلا owner_chat_id لأول بوت للمستخدم
    (يكون قد ربطه كأدمن للبوت، وهو نفس حسابه على تليجرام)."""
    now = int(time.time())
    cutoff = now + within_days * 86400
    with get_conn() as c:
        rows = c.execute("""
            SELECT s.user_id, u.username, u.email, s.plan, s.expires_at,
COALESCE(
                     (SELECT st.value FROM settings st
                       WHERE st.user_id=s.user_id AND st.key='tg_chat_id'),
                     (SELECT json_extract(b.config_json,'$.owner_chat_id') FROM bots b
                       WHERE b.owner_id=s.user_id
                         AND json_extract(b.config_json,'$.owner_chat_id') IS NOT NULL
                         AND json_extract(b.config_json,'$.owner_chat_id') <> ''
                       ORDER BY b.id LIMIT 1)
                   ) AS tg_chat_id
            FROM subscriptions s JOIN users u ON u.id=s.user_id
            WHERE s.plan<>'free' AND s.expires_at IS NOT NULL
              AND s.expires_at > ? AND s.expires_at <= ?
        """, (now, cutoff)).fetchall()
        return [dict(r) for r in rows]

def recently_expired_subscriptions():
    """يجلب الاشتراكات المنتهية خلال آخر 48 ساعة (للتذكير الأخير)."""
    now = int(time.time())
    since = now - 48 * 3600
    with get_conn() as c:
        rows = c.execute("""
            SELECT s.user_id, u.username, u.email, s.plan, s.expires_at,
COALESCE(
                     (SELECT st.value FROM settings st
                       WHERE st.user_id=s.user_id AND st.key='tg_chat_id'),
                     (SELECT json_extract(b.config_json,'$.owner_chat_id') FROM bots b
                       WHERE b.owner_id=s.user_id
                         AND json_extract(b.config_json,'$.owner_chat_id') IS NOT NULL
                         AND json_extract(b.config_json,'$.owner_chat_id') <> ''
                       ORDER BY b.id LIMIT 1)
                   ) AS tg_chat_id
            FROM subscriptions s JOIN users u ON u.id=s.user_id
            WHERE s.plan<>'free' AND s.expires_at IS NOT NULL
              AND s.expires_at <= ? AND s.expires_at >= ?
        """, (now, since)).fetchall()
        return [dict(r) for r in rows]


def user_lang(user_id, default="ar"):
    """لغة المستخدم المحفوظة عند آخر تبديل. التذكيرات تُرسَل بها."""
    return get_setting(user_id, "lang", default) or default

def user_tg_channel(user_id):
    """قناة تليجرام التي نصل بها للمستخدم: ربط صريح، وإلا أول بوت ربطه كأدمن."""
    v = get_setting(user_id, "tg_chat_id")
    if v:
        return v
    with get_conn() as c:
        r = c.execute(
            "SELECT json_extract(config_json,'$.owner_chat_id') v FROM bots "
            "WHERE owner_id=? AND json_extract(config_json,'$.owner_chat_id') IS NOT NULL "
            "AND json_extract(config_json,'$.owner_chat_id') <> '' ORDER BY id LIMIT 1",
            (user_id,)).fetchone()
        return r["v"] if r else None

# ---- ربط حساب تليجرام الشخصي بحساب المنصة (عبر بوت المنصة) ----
def set_tg_link_code(user_id, code):
    set_setting(user_id, "tg_link_code", code)

def claim_tg_link(code, chat_id):
    """يربط chat_id بالمستخدم صاحب هذا الكود. يرجّع user_id أو None.
    الكود يُستهلك فوراً فلا يُعاد استخدامه."""
    code = (code or "").strip()
    if not code:
        return None
    with get_conn() as c:
        r = c.execute("SELECT user_id FROM settings WHERE key='tg_link_code' AND value=?",
                      (code,)).fetchone()
        if not r:
            return None
        uid_ = r["user_id"]
        c.execute("INSERT INTO settings(user_id,key,value) VALUES(?,'tg_chat_id',?) "
                  "ON CONFLICT(user_id,key) DO UPDATE SET value=excluded.value",
                  (uid_, str(chat_id)))
        c.execute("DELETE FROM settings WHERE user_id=? AND key='tg_link_code'", (uid_,))
        return uid_

# ---------- حالة المحادثات (Chat State) ----------
def get_chat_state(bot_id, peer):
    with get_conn() as c:
        r = c.execute("SELECT * FROM chat_state WHERE bot_id=? AND peer=?", (bot_id, peer)).fetchone()
        if not r:
            return None
        return {"step": r["step"], "data": json.loads(r["data_json"]), "updated_at": r["updated_at"]}

def set_chat_state(bot_id, peer, step, data):
    with get_conn() as c:
        c.execute("INSERT INTO chat_state(bot_id, peer, step, data_json, updated_at) "
                  "VALUES(?, ?, ?, ?, ?) "
                  "ON CONFLICT(bot_id, peer) DO UPDATE SET "
                  "step=excluded.step, data_json=excluded.data_json, updated_at=excluded.updated_at",
                  (bot_id, peer, step, json.dumps(data), int(time.time())))

def clear_chat_state(bot_id, peer):
    with get_conn() as c:
        c.execute("DELETE FROM chat_state WHERE bot_id=? AND peer=?", (bot_id, peer))

def purge_stale_chat_state(max_age_seconds=7 * 24 * 3600):
    """محادثات مهجورة في منتصف الفلو تبقى للأبد بدون هذا — تُنظَّف دورياً."""
    with get_conn() as c:
        cur = c.execute("DELETE FROM chat_state WHERE updated_at < ?",
                        (int(time.time()) - int(max_age_seconds),))
        return cur.rowcount

def get_bot_by_token(token):
    """البحث بالتوكن (ويبهوك واتساب: wa:<phone_id>) عبر الفهرس الأعمى — التوكن نفسه
    مخزّن مشفّراً بنص عشوائي فلا يطابقه `WHERE token=?`."""
    idx = _token_idx(token)
    with get_conn() as c:
        if idx:
            r = c.execute("SELECT * FROM bots WHERE token_idx=?", (idx,)).fetchone()
        else:
            r = c.execute("SELECT * FROM bots WHERE token=?", (token,)).fetchone()
        return _map_bot(r) if r else None

# ---------- استهلاك الرسائل (واتساب مدفوع لكل رسالة) ----------
def _month():
    return time.strftime("%Y-%m")

def try_consume_msg(bot_id, owner_id, limit=None):
    """يزيد عدّاد الصادر إن كان صاحب البوت تحت حدّ باقته. يرجّع True لو سُمح.
    الزيادة والفحص في جملة UPDATE واحدة فلا يتسلّل إرسال زائد بين خيطين."""
    m = _month()
    with get_conn() as c:
        c.execute("INSERT OR IGNORE INTO usage_msgs(bot_id,owner_id,month) VALUES(?,?,?)",
                  (bot_id, owner_id, m))
        if limit is None:
            c.execute("UPDATE usage_msgs SET sent=sent+1 WHERE bot_id=? AND month=?", (bot_id, m))
            return True
        cur = c.execute(
            "UPDATE usage_msgs SET sent=sent+1 WHERE bot_id=? AND month=? AND ("
            " SELECT COALESCE(SUM(sent),0) FROM usage_msgs u WHERE u.owner_id=? AND u.month=?) < ?",
            (bot_id, m, owner_id, m, limit))
        return cur.rowcount == 1

def bump_received(bot_id, owner_id):
    m = _month()
    with get_conn() as c:
        c.execute("INSERT OR IGNORE INTO usage_msgs(bot_id,owner_id,month) VALUES(?,?,?)",
                  (bot_id, owner_id, m))
        c.execute("UPDATE usage_msgs SET received=received+1 WHERE bot_id=? AND month=?", (bot_id, m))

def bot_usage(bot_id, month=None):
    with get_conn() as c:
        r = c.execute("SELECT sent, received FROM usage_msgs WHERE bot_id=? AND month=?",
                      (bot_id, month or _month())).fetchone()
        return {"sent": r["sent"], "received": r["received"]} if r else {"sent": 0, "received": 0}

def owner_usage(owner_id, month=None):
    with get_conn() as c:
        r = c.execute("SELECT COALESCE(SUM(sent),0) s, COALESCE(SUM(received),0) g"
                      " FROM usage_msgs WHERE owner_id=? AND month=?",
                      (owner_id, month or _month())).fetchone()
        return {"sent": r["s"], "received": r["g"]}

# ---------- محفظة الرسائل التسويقية ----------

def wallet_balance(owner_id, conn=None):
    """الرصيد بالقروش. حساب بلا محفظة = صفر، لا خطأ."""
    with _conn_or(conn) as c:
        r = c.execute("SELECT balance FROM wallet WHERE owner_id=?", (owner_id,)).fetchone()
        return int(r["balance"]) if r else 0


def _wallet_move(owner_id, delta, kind, ref=None, note=None, conn=None, require=True):
    """حركة واحدة على المحفظة + قيدها في السجل، في معاملة واحدة.

    **الخصم ذرّي بشرطه:** `UPDATE ... WHERE balance >= ?` هو القفل نفسه —
    طلبان متزامنان (حملتان من تبويبين) لا يمكن أن ينجحا معاً على رصيد يكفي
    واحدة، فالثاني يجد rowcount=0 ويرجّع None. لا رصيد سالب بأي مسار.
    """
    now = int(time.time())
    with _conn_or(conn) as c:
        c.execute("INSERT OR IGNORE INTO wallet(owner_id,balance,updated_at) VALUES(?,0,?)",
                  (owner_id, now))
        if delta < 0 and require:
            cur = c.execute("UPDATE wallet SET balance=balance+?, updated_at=? "
                            "WHERE owner_id=? AND balance >= ?",
                            (delta, now, owner_id, -delta))
            if cur.rowcount != 1:
                return None                      # الرصيد لا يكفي — لم يتغيّر شيء
        else:
            c.execute("UPDATE wallet SET balance=balance+?, updated_at=? WHERE owner_id=?",
                      (delta, now, owner_id))
        bal = c.execute("SELECT balance FROM wallet WHERE owner_id=?", (owner_id,)).fetchone()["balance"]
        c.execute("INSERT INTO wallet_ledger(owner_id,delta,kind,ref,note,balance_after,created_at) "
                  "VALUES(?,?,?,?,?,?,?)", (owner_id, delta, kind, ref, note, bal, now))
        return int(bal)


def wallet_topup(owner_id, amount, ref=None, note=None, conn=None):
    """شحن بالقروش. يرجّع الرصيد الجديد، أو None لمبلغ غير موجب."""
    amount = int(amount or 0)
    if amount <= 0:
        return None
    return _wallet_move(owner_id, amount, "topup", ref, note, conn)


def wallet_charge(owner_id, amount, ref=None, note=None, conn=None):
    """خصم بالقروش. يرجّع الرصيد الجديد، أو **None لو لم يكفِ الرصيد** —
    وحينها لم يُخصم ولا قرش ولم يُكتب أي قيد."""
    amount = int(amount or 0)
    if amount <= 0:
        return None
    return _wallet_move(owner_id, -amount, "spend", ref, note, conn)


def wallet_refund(owner_id, amount, ref=None, note=None, conn=None):
    """ردّ ما لم يُستهلك (رسائل فشل إرسالها). لا يُشترط رصيد — هو إضافة."""
    amount = int(amount or 0)
    if amount <= 0:
        return None
    return _wallet_move(owner_id, amount, "refund", ref, note, conn)


def wallet_adjust(owner_id, delta, note=None, conn=None):
    """تعديل يدوي من الأدمن (تصحيح · تعويض). يُقيَّد كغيره ولا يُخفى."""
    delta = int(delta or 0)
    if delta == 0:
        return None
    return _wallet_move(owner_id, delta, "adjust", None, note, conn, require=True)


def wallet_ledger(owner_id, limit=50):
    with get_conn() as c:
        rows = c.execute("SELECT * FROM wallet_ledger WHERE owner_id=? ORDER BY id DESC LIMIT ?",
                         (owner_id, limit)).fetchall()
        return [dict(r) for r in rows]


# ---------- منع تكرار معالجة رسائل الويبهوك ----------
def mark_msg_seen(msg_id):
    """يرجّع True لو كانت جديدة، False لو سبقت معالجتها (إعادة إرسال من Meta)."""
    if not msg_id:
        return True
    with get_conn() as c:
        cur = c.execute("INSERT OR IGNORE INTO seen_msgs(msg_id,created_at) VALUES(?,?)",
                        (str(msg_id), int(time.time())))
        return cur.rowcount == 1

# ---------- وسائط العملاء ----------
def add_media(bot_id, owner_id, peer, kind, mime, size, fname, caption=""):
    with get_conn() as c:
        cur = c.execute(
            "INSERT INTO media(bot_id,owner_id,peer,kind,mime,size,fname,caption,created_at)"
            " VALUES(?,?,?,?,?,?,?,?,?)",
            (bot_id, owner_id, peer, kind, mime, size, fname, caption, int(time.time())))
        return cur.lastrowid

def get_media(media_id, bot_id=None):
    q = "SELECT * FROM media WHERE id=?"
    args = [media_id]
    if bot_id is not None:                 # الملكية تُفرض في الاستعلام لا بعده
        q += " AND bot_id=?"
        args.append(bot_id)
    with get_conn() as c:
        r = c.execute(q, args).fetchone()
        return dict(r) if r else None

def attach_media_to_lead(bot_id, peer, lead_id):
    """يربط ما رفعه العميل في هذه المحادثة بالـ lead الناتج عنها."""
    with get_conn() as c:
        c.execute("UPDATE media SET lead_id=? WHERE bot_id=? AND peer=? AND lead_id IS NULL",
                  (lead_id, bot_id, peer))

def media_count_this_month(owner_id):
    with get_conn() as c:
        return c.execute(
            "SELECT COUNT(*) FROM media WHERE owner_id=? AND created_at >= ?",
            (owner_id, int(time.mktime(time.strptime(time.strftime("%Y-%m-01"), "%Y-%m-%d"))))
        ).fetchone()[0]

def orphan_media(max_age_seconds=7 * 24 * 3600):
    """ملفات وصلت ولم يكتمل الفلو الذي كانت جزءاً منه — لا يشير إليها شيء.
    ملف تشير إليه رسالة في صندوق الوارد ليس يتيماً: يبقى ما بقيت المحادثة."""
    with get_conn() as c:
        rows = c.execute("SELECT id, fname FROM media WHERE lead_id IS NULL AND created_at < ? "
                         "AND id NOT IN (SELECT media_id FROM messages WHERE media_id IS NOT NULL)",
                         (int(time.time()) - int(max_age_seconds),)).fetchall()
        return [dict(r) for r in rows]

def drop_media(ids):
    if not ids:
        return 0
    with get_conn() as c:
        cur = c.execute(f"DELETE FROM media WHERE id IN ({','.join('?' * len(ids))})", list(ids))
        return cur.rowcount

def purge_seen_msgs(max_age_seconds=3 * 24 * 3600):
    with get_conn() as c:
        cur = c.execute("DELETE FROM seen_msgs WHERE created_at < ?",
                        (int(time.time()) - int(max_age_seconds),))
        return cur.rowcount


def update_bot_token(bot_id, token):
    """توكن جديد لبوت قائم — تليجرام يدوّره (replaceManagedBotToken) ولا يتغيّر البوت."""
    with get_conn() as c:
        c.execute("UPDATE bots SET token=?, token_idx=? WHERE id=?",
                  (_encrypt(token.strip()), _token_idx(token), bot_id))


def bot_by_tg_id(tg_bot_id):
    """البوت الذي معرّفه على تليجرام هذا (يُحفظ في config.tg_bot_id عند الإنشاء بضغطة)."""
    with get_conn() as c:
        r = c.execute("SELECT * FROM bots WHERE json_extract(config_json,'$.tg_bot_id')=? "
                      "ORDER BY id LIMIT 1", (int(tg_bot_id),)).fetchone()
        return _map_bot(r) if r else None


# ============================================================================
#  إنشاء بوت بضغطة — Telegram Managed Bots (Bot API 9.6)
# ============================================================================
MANAGED_TTL = 15 * 60

def create_managed_request(user_id, token_hash, template, business_name, suggested_username,
                           ttl=MANAGED_TTL):
    """طلب جديد لمرة واحدة. الطلبات المعلّقة السابقة لنفس المستخدم تُلغى —
    رابط واحد صالح في كل لحظة، فلا يُستهلك رابط قديم منسيّ لإنشاء بوت لم يعد مطلوباً."""
    now = int(time.time())
    with get_conn() as c:
        c.execute("UPDATE managed_bot_requests SET status='failed', error='superseded' "
                  "WHERE user_id=? AND status IN ('pending','linked')", (user_id,))
        cur = c.execute(
            "INSERT INTO managed_bot_requests(token_hash,user_id,template,business_name,"
            "suggested_username,created_at,expires_at) VALUES(?,?,?,?,?,?,?)",
            (token_hash, user_id, template, business_name[:80], suggested_username, now, now + ttl))
        return cur.lastrowid


def get_managed_request(req_id, user_id=None):
    q, args = "SELECT * FROM managed_bot_requests WHERE id=?", [req_id]
    if user_id is not None:                   # الملكية في الاستعلام لا بعده
        q += " AND user_id=?"
        args.append(user_id)
    with get_conn() as c:
        r = c.execute(q, args).fetchone()
        return dict(r) if r else None


def link_managed_request(token_hash, tg_user_id):
    """يربط الطلب بحساب تليجرام الذي فتح الرابط. ذرّي: شرط الحالة هو القفل،
    فحساب تليجرام ثانٍ لا يستولي على طلب ربطه غيره. يرجّع الصف أو None."""
    now = int(time.time())
    with get_conn() as c:
        cur = c.execute("UPDATE managed_bot_requests SET tg_user_id=?, status='linked' "
                        "WHERE token_hash=? AND status='pending' AND expires_at>?",
                        (int(tg_user_id), token_hash, now))
        if cur.rowcount != 1:
            return None
        r = c.execute("SELECT * FROM managed_bot_requests WHERE token_hash=?",
                      (token_hash,)).fetchone()
        return dict(r) if r else None


def pending_managed_for_tg(tg_user_id):
    """أحدث طلب مربوط وصالح لهذا الحساب على تليجرام — لا غيره."""
    with get_conn() as c:
        r = c.execute("SELECT * FROM managed_bot_requests WHERE tg_user_id=? AND status='linked' "
                      "AND expires_at>? ORDER BY id DESC LIMIT 1",
                      (int(tg_user_id), int(time.time()))).fetchone()
        return dict(r) if r else None


def claim_managed_request(req_id):
    """linked ← creating، مرة واحدة. تليجرام قد يرسل `managed_bot` ورسالة
    `managed_bot_created` معاً لنفس البوت — بلا هذا القفل يُنشأ صفّان."""
    with get_conn() as c:
        cur = c.execute("UPDATE managed_bot_requests SET status='creating' "
                        "WHERE id=? AND status='linked'", (req_id,))
        return cur.rowcount == 1


def finish_managed_request(req_id, status, bot_id=None, error=None):
    """creating ← created | failed. يرجّع True لو تم الانتقال."""
    with get_conn() as c:
        cur = c.execute("UPDATE managed_bot_requests SET status=?, bot_id=?, error=? "
                        "WHERE id=? AND status IN ('linked','creating')",
                        (status, bot_id, (error or None) and str(error)[:200], req_id))
        return cur.rowcount == 1


# ============================================================================
#  المحادثات — سجل الرسائل وصندوق الوارد
# ============================================================================
MSG_TEXT_MAX = 4000

def log_message(bot_id, peer, direction, sender, text="", kind="text", media_id=None, name=None, user_id=None):
    """يسجّل رسالة ويحدّث ملخّص المحادثة في معاملة واحدة.
    الوارد يزيد عدّاد غير المقروء؛ ردّ صاحب النشاط يصفّره. رسالة واردة لمحادثة مغلقة تعيد فتحها.
    `user_id`: الموظف صاحب الرد اليدوي (الصندوق المشترك)."""
    # حماية: peer فاسد (مثل "wa:" بلا رقم) يُفسد صندوق الوارد كله (404 عند فتحه)
    # عميل واتساب برقم مخفي (wa:EG.1349…) هوية صحيحة — رفضه كان يُخفي محادثته كلها
    parts = (peer or "").split(":", 1)
    if len(parts) != 2 or not (parts[1].strip().lstrip("-").isdigit() or
                               (parts[0] == "wa" and re.fullmatch(r"[A-Z]{2}\.[A-Za-z0-9]{1,128}", parts[1]))):
        log.warning("log_message: rejected broken peer %r for bot #%s", peer, bot_id)
        return
    now = int(time.time())
    text = (text or "")[:MSG_TEXT_MAX]
    with get_conn() as c:
        c.execute("INSERT INTO messages(bot_id,peer,direction,sender,kind,text,media_id,created_at,user_id)"
                  " VALUES(?,?,?,?,?,?,?,?,?)",
                  (bot_id, peer, direction, sender, kind, text, media_id, now, user_id))
        preview = text[:140] if text else ("📎" if kind == "media" else "")
        c.execute("INSERT INTO conversations(bot_id,peer,name,unread,last_text,last_at)"
                  " VALUES(?,?,?,?,?,?)"
                  " ON CONFLICT(bot_id,peer) DO UPDATE SET"
                  " name=COALESCE(NULLIF(excluded.name,''), conversations.name),"
                  " unread=CASE WHEN ?='in' THEN conversations.unread+1"
                  "             WHEN ?='human' THEN 0 ELSE conversations.unread END,"
                  " status=CASE WHEN ?='in' AND conversations.status='resolved' THEN 'open'"
                  "             ELSE conversations.status END,"
                  " last_text=excluded.last_text, last_at=excluded.last_at",
                  (bot_id, peer, name or "", 1 if direction == "in" else 0, preview, now,
                   direction, sender, direction))


def get_conversation(bot_id, peer):
    with get_conn() as c:
        r = c.execute("SELECT * FROM conversations WHERE bot_id=? AND peer=?",
                      (bot_id, peer)).fetchone()
        return dict(r) if r else None


def list_conversations(bot_id, limit=200):
    with get_conn() as c:
        # peer صحيح: tg:123 · wa:201xxx · tg:-100… (مجموعة) · wa:EG.1349… (رقم مخفي/اسم مستخدم).
        # «wa:» الفارغة محادثة قديمة قبل دعم الأرقام المخفية — تظهر للقراءة فقط (app._LEGACY_PEER).
        rows = c.execute("SELECT * FROM conversations WHERE bot_id=?"
                         " AND (peer GLOB '[a-z][a-z]:[0-9]*' OR peer GLOB '[a-z][a-z]:-[0-9]*'"
                         "      OR peer GLOB 'wa:[A-Z][A-Z].[A-Za-z0-9]*' OR peer = 'wa:')"
                         " ORDER BY last_at DESC LIMIT ?",
                         (bot_id, limit)).fetchall()
        return [dict(r) for r in rows]


def list_messages(bot_id, peer, after_id=0, limit=300):
    """آخر الرسائل تصاعدياً. after_id يجلب الجديد فقط (الاستطلاع الدوري)."""
    with get_conn() as c:
        if after_id:
            rows = c.execute("SELECT * FROM messages WHERE bot_id=? AND peer=? AND id>? "
                             "ORDER BY id LIMIT ?", (bot_id, peer, int(after_id), limit)).fetchall()
        else:
            rows = c.execute("SELECT * FROM (SELECT * FROM messages WHERE bot_id=? AND peer=? "
                             "ORDER BY id DESC LIMIT ?) ORDER BY id", (bot_id, peer, limit)).fetchall()
        return [dict(r) for r in rows]


def recent_history(bot_id, peer, limit=12):
    """آخر N رسالة نصية للمحادثة — ذاكرة الذكاء الاصطناعي."""
    with get_conn() as c:
        # الملاحظات الداخلية (direction='note') لا تدخل ذاكرة الذكاء الاصطناعي أبداً — قد تحوي ما لا يُقال للعميل
        rows = c.execute("SELECT direction, sender, text FROM messages WHERE bot_id=? AND peer=? "
                         "AND text<>'' AND direction<>'note' ORDER BY id DESC LIMIT ?", (bot_id, peer, limit)).fetchall()
        return [dict(r) for r in reversed(rows)]


def set_conversation_mode(bot_id, peer, mode, human_at=None):
    """bot | human. التولّي يسجّل وقت النشاط البشري (أساس العودة التلقائية).
    `human_at` صريح (أقدم من الآن) = تولٍّ مؤقت يعود للبوت أبكر — تحويل آلي لم يرد عليه أحد."""
    if mode not in ("bot", "human"):
        return False
    now = int(time.time())
    stamp = int(human_at) if (mode == "human" and human_at) else (now if mode == "human" else None)
    with get_conn() as c:
        c.execute("INSERT INTO conversations(bot_id,peer,mode,last_at,human_at) VALUES(?,?,?,?,?)"
                  " ON CONFLICT(bot_id,peer) DO UPDATE SET mode=excluded.mode,"
                  " human_at=CASE WHEN excluded.mode='human' THEN excluded.human_at"
                  "               ELSE conversations.human_at END",
                  (bot_id, peer, mode, now, stamp))
    return True


def count_recent_in(bot_id, peer, since):
    """رسائل العميل الواردة منذ `since` — مقياس «يدور في دوائر» قبل التحويل لصاحب النشاط."""
    with get_conn() as c:
        return c.execute("SELECT COUNT(*) FROM messages WHERE bot_id=? AND peer=? AND direction='in' "
                         "AND created_at>=?", (bot_id, peer, int(since))).fetchone()[0]


def touch_human(bot_id, peer):
    with get_conn() as c:
        c.execute("UPDATE conversations SET human_at=? WHERE bot_id=? AND peer=?",
                  (int(time.time()), bot_id, peer))


def mark_conversation_read(bot_id, peer):
    with get_conn() as c:
        c.execute("UPDATE conversations SET unread=0 WHERE bot_id=? AND peer=?", (bot_id, peer))


def unread_total(bot_id):
    with get_conn() as c:
        return c.execute("SELECT COALESCE(SUM(unread),0) FROM conversations WHERE bot_id=?",
                         (bot_id,)).fetchone()[0]


def peer_known(bot_id, peer):
    """هل هذا العميل تواصل مع هذا البوت فعلاً؟ لا نراسل رقماً لم يراسلنا."""
    with get_conn() as c:
        return (c.execute("SELECT 1 FROM bot_users WHERE bot_id=? AND peer=? LIMIT 1",
                          (bot_id, peer)).fetchone() is not None or
                c.execute("SELECT 1 FROM conversations WHERE bot_id=? AND peer=? LIMIT 1",
                          (bot_id, peer)).fetchone() is not None)


def peer_last_in(bot_id, peer):
    """آخر رسالة واردة من العميل — أساس نافذة الـ24 ساعة لرد صاحب النشاط على واتساب."""
    with get_conn() as c:
        r = c.execute("SELECT last_in_at FROM bot_users WHERE bot_id=? AND peer=?",
                      (bot_id, peer)).fetchone()
        return (r["last_in_at"] if r else None) or 0


def purge_old_messages(max_age_seconds=365 * 24 * 3600):
    """مدة الاحتفاظ بالمحادثات (سياسة الخصوصية §7): 12 شهراً."""
    cutoff = int(time.time()) - int(max_age_seconds)
    with get_conn() as c:
        cur = c.execute("DELETE FROM messages WHERE created_at < ?", (cutoff,))
        c.execute("DELETE FROM conversations WHERE last_at < ?", (cutoff,))
        return cur.rowcount


# ============================================================================
#  وكيل الإعداد — الجلسات ونسخ الإعدادات
# ============================================================================
def create_setup_session(bot_id, owner_id, source):
    now = int(time.time())
    with get_conn() as c:
        cur = c.execute("INSERT INTO ai_setup_sessions(bot_id,owner_id,source,created_at,updated_at)"
                        " VALUES(?,?,?,?,?)", (bot_id, owner_id, source, now, now))
        return cur.lastrowid


def get_setup_session(sid, bot_id):
    with get_conn() as c:
        r = c.execute("SELECT * FROM ai_setup_sessions WHERE id=? AND bot_id=?",
                      (sid, bot_id)).fetchone()
        if not r:
            return None
        d = dict(r)
        d["brief"] = json.loads(d.get("brief_json") or "{}")
        d["turns"] = json.loads(d.get("turns_json") or "[]")
        d["proposal"] = json.loads(d["proposal_json"]) if d.get("proposal_json") else None
        return d


def save_setup_session(sid, status, brief, turns, proposal=None, rounds=None, source=None):
    with get_conn() as c:
        c.execute("UPDATE ai_setup_sessions SET status=?, brief_json=?, turns_json=?,"
                  " proposal_json=?, rounds=COALESCE(?,rounds), source=COALESCE(?,source),"
                  " updated_at=? WHERE id=?",
                  (status, json.dumps(brief or {}, ensure_ascii=False),
                   json.dumps(turns or [], ensure_ascii=False),
                   json.dumps(proposal, ensure_ascii=False) if proposal is not None else None,
                   rounds, source, int(time.time()), sid))


def close_setup_session(sid, status):
    """applied | discarded — مرة واحدة: جلسة طُبّقت لا تُطبَّق ثانية."""
    with get_conn() as c:
        cur = c.execute("UPDATE ai_setup_sessions SET status=?, updated_at=? "
                        "WHERE id=? AND status IN ('asking','proposed')",
                        (status, int(time.time()), sid))
        return cur.rowcount == 1


def setup_sessions_this_month(owner_id):
    with get_conn() as c:
        return c.execute("SELECT COUNT(*) FROM ai_setup_sessions WHERE owner_id=? AND created_at>=?",
                         (owner_id, _month_start())).fetchone()[0]


CONFIG_VERSIONS_KEEP = 20

def save_config_version(bot_id, config, reason):
    """يحفظ الإعداد **الحالي** قبل استبداله، ويبقي آخر 20 نسخة فقط."""
    with get_conn() as c:
        c.execute("INSERT INTO bot_config_versions(bot_id,config_json,reason,created_at)"
                  " VALUES(?,?,?,?)",
                  (bot_id, json.dumps(config, ensure_ascii=False), reason, int(time.time())))
        c.execute("DELETE FROM bot_config_versions WHERE bot_id=? AND id NOT IN ("
                  "SELECT id FROM bot_config_versions WHERE bot_id=? ORDER BY id DESC LIMIT ?)",
                  (bot_id, bot_id, CONFIG_VERSIONS_KEEP))


def list_config_versions(bot_id, limit=CONFIG_VERSIONS_KEEP):
    with get_conn() as c:
        rows = c.execute("SELECT id, reason, created_at FROM bot_config_versions WHERE bot_id=? "
                         "ORDER BY id DESC LIMIT ?", (bot_id, limit)).fetchall()
        return [dict(r) for r in rows]


def get_config_version(vid, bot_id):
    with get_conn() as c:
        r = c.execute("SELECT * FROM bot_config_versions WHERE id=? AND bot_id=?",
                      (vid, bot_id)).fetchone()
        return json.loads(r["config_json"]) if r else None


# ============================================================================
#  ردود الذكاء الاصطناعي — الحصة الشهرية ثم المحفظة
# ============================================================================
def _month_start():
    return int(time.mktime(time.strptime(time.strftime("%Y-%m-01"), "%Y-%m-%d")))


def ai_reply_allow(owner_id, allowance, price, ref=None):
    """يحجز رداً واحداً للذكاء الاصطناعي. يرجّع 'included' أو 'paid' أو None.

    **ذرّي في معاملة واحدة:** الحجز من الحصة شرطه `replies < allowance` في جملة
    UPDATE نفسها (نفس قفل `try_consume_msg`)، فردّان متزامنان عند حافة الحصة
    لا يتجاوزانها. ما فوق الحصة يُخصم من المحفظة بـ`_wallet_move` على **نفس**
    الاتصال — لا خصم بلا ردّ محسوب ولا ردّ محسوب بلا خصم.
    allowance=None: بلا حد (الأدمن)."""
    m = _month()
    with get_conn() as c:
        c.execute("INSERT OR IGNORE INTO ai_usage(owner_id,month) VALUES(?,?)", (owner_id, m))
        if allowance is None:
            c.execute("UPDATE ai_usage SET replies=replies+1 WHERE owner_id=? AND month=?",
                      (owner_id, m))
            return "included"
        cur = c.execute("UPDATE ai_usage SET replies=replies+1 WHERE owner_id=? AND month=? "
                        "AND replies < ?", (owner_id, m, int(allowance)))
        if cur.rowcount == 1:
            return "included"
        price = int(price or 0)
        if price <= 0:
            return None
        if _wallet_move(owner_id, -price, "spend", ref=ref, note="ai reply", conn=c) is None:
            return None
        c.execute("UPDATE ai_usage SET replies=replies+1, paid=paid+1 WHERE owner_id=? AND month=?",
                  (owner_id, m))
        return "paid"


def ai_reply_release(owner_id, grant, price, ref=None):
    """يعكس حجز `ai_reply_allow` لرد لم يصل (نافذة الـ24 ساعة · خطأ Meta · حدّ الباقة ·
    الشبكة): يعيد العدّاد، ويردّ ثمنه لو كان مدفوعاً — في معاملة واحدة. قبلها كانت
    القروش تُخصم على ردود لم تصل أبداً، بصمت وبتكرار."""
    if grant not in ("included", "paid"):
        return
    m = _month()
    with get_conn() as c:
        if grant == "paid":
            c.execute("UPDATE ai_usage SET replies=MAX(replies-1,0), paid=MAX(paid-1,0) "
                      "WHERE owner_id=? AND month=?", (owner_id, m))
            if int(price or 0) > 0:
                _wallet_move(owner_id, int(price), "refund", ref=ref,
                             note="ai reply not delivered", conn=c)
        else:
            c.execute("UPDATE ai_usage SET replies=MAX(replies-1,0) WHERE owner_id=? AND month=?",
                      (owner_id, m))


def purge_old_events(max_age_seconds=365 * 24 * 3600):
    """أحداث التحليلات (`start` مع كل /start لكل بوت) كانت تنمو بلا حد ولا يمسّها التنظيف.
    نحتفظ بسنة — مدة الاحتفاظ المعلنة للمحادثات. التحليلات اليومية تعرض 14 يوماً."""
    cutoff = int(time.time()) - max_age_seconds
    with get_conn() as c:
        return c.execute("DELETE FROM events WHERE created_at < ?", (cutoff,)).rowcount


# ---------- قياس الزوار والقمع ----------
def log_page_view(path, ref, src, device, vid):
    with get_conn() as c:
        c.execute("INSERT INTO page_views(day,path,ref,src,device,vid,created_at) VALUES(?,?,?,?,?,?,?)",
                  (_day(), (path or "/")[:120], (ref or None) and ref[:80], (src or None) and src[:60],
                   device, vid, int(time.time())))


def track(kind, user_id, bot_id=0):
    """مرحلة قمع — أول مرة فقط لكل (مرحلة، مستخدم، بوت)."""
    if not user_id:
        return
    with get_conn() as c:
        c.execute("INSERT OR IGNORE INTO funnel(kind,user_id,bot_id,created_at) VALUES(?,?,?,?)",
                  (kind, int(user_id), int(bot_id or 0), int(time.time())))


def purge_old_page_views(max_age_seconds=400 * 24 * 3600):
    cutoff = int(time.time()) - max_age_seconds
    with get_conn() as c:
        return c.execute("DELETE FROM page_views WHERE created_at < ?", (cutoff,)).rowcount


def analytics_summary(days=30):
    """لوحة «إحصائيات الزوار»: الزوار ومصادرهم، وقمع التسجيل على **دفعة** من سجّلوا في
    الفترة (cohort): من كل مسجّل كم وصل لكل مرحلة — لا أحداث متفرقة من أزمنة مختلفة.
    النسبة الحاكمة: مسجّل ← بوت شغّال (تحت 40% المشكلة في المنتج لا في التسويق)."""
    import datetime
    days = max(1, int(days))
    since_ts = int(time.time()) - days * 86400
    since_day = (datetime.date.today() - datetime.timedelta(days=days - 1)).isoformat()
    uv = "COUNT(DISTINCT day || '|' || vid)"        # الزائر الفريد يُعدّ مرة لكل يوم
    cohort = "SELECT id FROM users WHERE created_at >= ? AND role = 'user'"
    with get_conn() as c:
        one = lambda q, *a: c.execute(q, a).fetchone()[0] or 0
        rows = lambda q, *a: [dict(r) for r in c.execute(q, a).fetchall()]
        out = {
            "days": days,
            "visitors": one(f"SELECT {uv} FROM page_views WHERE day >= ?", since_day),
            "views": one("SELECT COUNT(*) FROM page_views WHERE day >= ?", since_day),
            "pricing_visitors": one(f"SELECT {uv} FROM page_views WHERE day >= ? AND path = '/pricing'",
                                    since_day),
            "daily": rows(f"SELECT day, {uv} v, COUNT(*) n FROM page_views WHERE day >= ? "
                          "GROUP BY day ORDER BY day", since_day),
            "pages": rows(f"SELECT path k, {uv} v, COUNT(*) n FROM page_views WHERE day >= ? "
                          "GROUP BY path ORDER BY v DESC LIMIT 10", since_day),
            "sources": rows(f"SELECT COALESCE(src, ref, 'direct') k, {uv} v FROM page_views "
                            "WHERE day >= ? GROUP BY k ORDER BY v DESC LIMIT 10", since_day),
            "devices": rows(f"SELECT COALESCE(device, 'other') k, {uv} v FROM page_views "
                            "WHERE day >= ? GROUP BY k ORDER BY v DESC", since_day),
            "signup_sources": rows(
                "SELECT COALESCE(s.value, 'direct') k, COUNT(*) v FROM users u LEFT JOIN settings s "
                "ON s.user_id = u.id AND s.key = 'signup_src' WHERE u.created_at >= ? AND u.role = 'user' "
                "GROUP BY k ORDER BY v DESC LIMIT 10", since_ts),
            "funnel": {
                "signup": one(f"SELECT COUNT(*) FROM ({cohort})", since_ts),
                "bot_created": one(f"SELECT COUNT(DISTINCT owner_id) FROM bots WHERE owner_id IN ({cohort})",
                                   since_ts),
                "bot_live": one("SELECT COUNT(DISTINCT user_id) FROM funnel WHERE kind = 'bot_live' "
                                f"AND user_id IN ({cohort})", since_ts),
                "first_message": one("SELECT COUNT(DISTINCT b.owner_id) FROM bots b "
                                     f"WHERE b.owner_id IN ({cohort}) AND EXISTS (SELECT 1 FROM messages m "
                                     "WHERE m.bot_id = b.id AND m.direction = 'in')", since_ts),
                "payment_sent": one("SELECT COUNT(DISTINCT user_id) FROM payments WHERE plan <> ? "
                                    f"AND user_id IN ({cohort})", WALLET_PLAN, since_ts),
                "paid": one("SELECT COUNT(DISTINCT user_id) FROM payments WHERE plan <> ? AND "
                            f"status = 'approved' AND user_id IN ({cohort})", WALLET_PLAN, since_ts),
            },
        }
    return out


# ---------- إضافات البوت المدفوعة (لكل بوت على حدة) ----------
# `pay`     : تحصيل مدفوعات عملاء البوت.
# `catalog` : إدارة المنتجات من داخل تليجرام (catalog_bot).
# شراء أي إضافة دفعة منصة عادية (إيصال + موافقة الأدمن) بـ plan = __addon_<kind>__:<bot_id> —
# كشحن المحفظة: `plans.is_sellable` ترفضه، و`finalize_payment` تفعّل الإضافة لذلك البوت.
ADDON_PAY = "__addon_pay__"                 # موروث: كود دفعات الإضافة الأولى كما هو
ADDON_KINDS = ("pay", "catalog")
_ADDON_PLAN_RE = re.compile(r"^__addon_([a-z]{1,16})__:(\d{1,12})$")


def addon_plan(bot_id, addon="pay"):
    if addon not in ADDON_KINDS:
        raise ValueError(f"unknown addon: {addon}")
    return f"__addon_{addon}__:{int(bot_id)}"


def parse_addon_plan(plan):
    """(نوع الإضافة، رقم البوت) أو (None, None) لأي كود آخر."""
    m = _ADDON_PLAN_RE.match(str(plan or ""))
    if not m or m.group(1) not in ADDON_KINDS:
        return None, None
    return m.group(1), int(m.group(2))


def addon_bot_id(plan):
    """رقم البوت من كود دفعة إضافة — أياً كان نوعها."""
    return parse_addon_plan(plan)[1]


def addon_plans_in_payments():
    with get_conn() as c:
        return [r[0] for r in c.execute(
            "SELECT DISTINCT plan FROM payments WHERE substr(plan,1,8)='__addon_'").fetchall()]


def addon_expires(bot_id, addon="pay"):
    with get_conn() as c:
        r = c.execute("SELECT expires_at FROM bot_addons WHERE bot_id=? AND addon=?",
                      (bot_id, addon)).fetchone()
        return r[0] if r else None


def bot_owner_is_staff(bot_id):
    """صاحب البوت أدمن أو دعم؟ حساب الإدارة مفتوح له كل شيء بلا شراء (قرار المالك) — كما
    يتخطّى حدود الباقات في كل مكان آخر (app.py، flow_engine، bot_manager.wa_limit_for)."""
    with get_conn() as c:
        r = c.execute("SELECT u.role FROM bots b JOIN users u ON u.id = b.owner_id WHERE b.id=?",
                      (bot_id,)).fetchone()
    return bool(r and r[0] in ("admin", "support"))


def addon_active(bot_id, addon="pay"):
    # بوت يملكه حساب الإدارة: الإضافة سارية دائماً — المنصة لا تبيع لنفسها. يُفحص بصاحب
    # البوت لا بمن يتصفّح: بوت عميل يفتحه الأدمن يبقى محتاجاً شراء صاحبه.
    if bot_owner_is_staff(bot_id):
        return True
    exp = addon_expires(bot_id, addon)
    return bool(exp and exp > time.time())


def extend_addon(bot_id, addon="pay", days=30, conn=None):
    """يمدّ الإضافة `days` يوماً — من تاريخ انتهائها لو ما زالت سارية، فالتجديد المبكر لا يضيع."""
    now = int(time.time())
    with _conn_or(conn) as c:
        r = c.execute("SELECT expires_at FROM bot_addons WHERE bot_id=? AND addon=?",
                      (bot_id, addon)).fetchone()
        exp = max(now, r[0] if r else now) + int(days) * 86400
        c.execute("INSERT INTO bot_addons(bot_id,addon,expires_at,updated_at) VALUES(?,?,?,?) "
                  "ON CONFLICT(bot_id,addon) DO UPDATE SET expires_at=excluded.expires_at, "
                  "updated_at=excluded.updated_at", (bot_id, addon, exp, now))
        return exp


def set_order_pay_status(order_id, status):
    with get_conn() as c:
        c.execute("UPDATE orders SET pay_status=? WHERE id=?", (status, order_id))


def bot_payment_hash_used(bot_id, img_hash):
    """إيصال بنفس البصمة في دفعة معلّقة أو معتمدة لنفس البوت = إعادة استخدام."""
    with get_conn() as c:
        return c.execute("SELECT 1 FROM bot_payments WHERE bot_id=? AND img_hash=? "
                         "AND status IN ('pending','approved') LIMIT 1",
                         (bot_id, img_hash)).fetchone() is not None


def create_bot_payment(bot_id, order_id, tg_user_id, customer, amount, screenshot, img_hash,
                       file_id, auto_check):
    """إيصال عميل اجتاز الفحص ← معلّق لصاحب البوت، والطلب «للمراجعة» في المعاملة نفسها."""
    now = int(time.time())
    with get_conn() as c:
        pid = c.execute("INSERT INTO bot_payments(bot_id,order_id,tg_user_id,customer,amount,screenshot,"
                        "img_hash,file_id,auto_check,status,created_at) VALUES(?,?,?,?,?,?,?,?,?,'pending',?)",
                        (bot_id, order_id, tg_user_id, customer, amount, screenshot, img_hash, file_id,
                         auto_check, now)).lastrowid
        if order_id:
            c.execute("UPDATE orders SET pay_status='pending' WHERE id=? AND bot_id=?", (order_id, bot_id))
        return pid


def get_bot_payment(pid, bot_id=None):
    with get_conn() as c:
        if bot_id is None:
            r = c.execute("SELECT * FROM bot_payments WHERE id=?", (pid,)).fetchone()
        else:
            r = c.execute("SELECT * FROM bot_payments WHERE id=? AND bot_id=?", (pid, bot_id)).fetchone()
        return dict(r) if r else None


def list_bot_payments(bot_id, limit=100):
    """المعلّقة أولاً ثم الأحدث."""
    with get_conn() as c:
        return [dict(r) for r in c.execute(
            "SELECT id,order_id,tg_user_id,customer,amount,status,created_at,decided_at,auto_check "
            "FROM bot_payments WHERE bot_id=? ORDER BY CASE status WHEN 'pending' THEN 0 ELSE 1 END, "
            "id DESC LIMIT ?", (bot_id, int(limit))).fetchall()]


def decide_bot_payment(pid, bot_id, status):
    """قرار صاحب البوت — ذرّي كقرار دفعات المنصة: التحديث المشروط (`status='pending'`) هو القفل،
    فزرّ تليجرام واللوحة معاً لا ينجحان مرتين. حالة الطلب تتحدّث في المعاملة نفسها.
    يرجّع صفّ الدفعة، أو None لو سبق البتّ فيها أو ليست لهذا البوت."""
    if status not in ("approved", "rejected"):
        return None
    with get_conn() as c:
        cur = c.execute("UPDATE bot_payments SET status=?, decided_at=? WHERE id=? AND bot_id=? "
                        "AND status='pending'", (status, int(time.time()), pid, bot_id))
        if cur.rowcount != 1:
            return None
        row = dict(c.execute("SELECT * FROM bot_payments WHERE id=?", (pid,)).fetchone())
        if row.get("order_id"):
            c.execute("UPDATE orders SET pay_status=? WHERE id=? AND bot_id=?",
                      ("paid" if status == "approved" else "rejected", row["order_id"], bot_id))
        return row


def ai_usage_of(owner_id, month=None):
    with get_conn() as c:
        r = c.execute("SELECT replies, paid FROM ai_usage WHERE owner_id=? AND month=?",
                      (owner_id, month or _month())).fetchone()
        return {"replies": r["replies"], "paid": r["paid"]} if r else {"replies": 0, "paid": 0}


# ============================================================================
#  مكتبة وسائط صاحب النشاط
# ============================================================================
def add_asset(owner_id, kind, mime, size, fname, name="", source_url=None):
    with get_conn() as c:
        cur = c.execute("INSERT INTO assets(owner_id,kind,mime,size,fname,name,source_url,created_at)"
                        " VALUES(?,?,?,?,?,?,?,?)",
                        (owner_id, kind, mime, size, fname, (name or "")[:80], source_url,
                         int(time.time())))
        return cur.lastrowid


def get_asset(asset_id, owner_id=None):
    q, args = "SELECT * FROM assets WHERE id=?", [asset_id]
    if owner_id is not None:                   # الملكية في الاستعلام
        q += " AND owner_id=?"
        args.append(owner_id)
    with get_conn() as c:
        r = c.execute(q, args).fetchone()
        return dict(r) if r else None


def list_assets(owner_id, limit=300):
    with get_conn() as c:
        rows = c.execute("SELECT * FROM assets WHERE owner_id=? ORDER BY id DESC LIMIT ?",
                         (owner_id, limit)).fetchall()
        return [dict(r) for r in rows]


def assets_bytes(owner_id):
    with get_conn() as c:
        return c.execute("SELECT COALESCE(SUM(size),0) FROM assets WHERE owner_id=?",
                         (owner_id,)).fetchone()[0]


def delete_asset(asset_id, owner_id):
    """يرجّع الصف المحذوف (لحذف ملفه) أو None لو ليس ملكه."""
    with get_conn() as c:
        r = c.execute("SELECT * FROM assets WHERE id=? AND owner_id=?",
                      (asset_id, owner_id)).fetchone()
        if not r:
            return None
        c.execute("DELETE FROM assets WHERE id=?", (asset_id,))
        return dict(r)


def get_asset_ref(asset_id, bot_id):
    """مرجع القناة إن كان صالحاً (لم ينتهِ)."""
    with get_conn() as c:
        r = c.execute("SELECT ref, expires_at FROM asset_refs WHERE asset_id=? AND bot_id=?",
                      (asset_id, bot_id)).fetchone()
        if not r:
            return None
        if r["expires_at"] and r["expires_at"] <= int(time.time()):
            return None
        return r["ref"]


def set_asset_ref(asset_id, bot_id, ref, expires_at=None):
    with get_conn() as c:
        c.execute("INSERT INTO asset_refs(asset_id,bot_id,ref,expires_at) VALUES(?,?,?,?)"
                  " ON CONFLICT(asset_id,bot_id) DO UPDATE SET ref=excluded.ref,"
                  " expires_at=excluded.expires_at", (asset_id, bot_id, ref, expires_at))


def drop_asset_ref(asset_id, bot_id):
    with get_conn() as c:
        c.execute("DELETE FROM asset_refs WHERE asset_id=? AND bot_id=?", (asset_id, bot_id))


# ============================================================================
#  تقارير ورؤى — قراءة فقط (weekly_report.py · conv_insights.py)
# ============================================================================
# كل استعلامات التقارير هنا لا في الوحدتين، فـ«لا SQL خارج database.py» (AGENTS §1).
# كلها **قراءة فقط** وبنافذة زمنية صريحة `[a, b)` بالثواني: لا «آخر 7 أيام» داخل
# استعلام، حتى تُقارَن أي فترة بسابقتها بنفس الدوال بالضبط.
# اليوم يُحسب بالتوقيت المحلي (`localtime`) مثل `page_views.day` و`_day()` —
# خلط UTC بالمحلي يزيح صفوف الرسم يوماً كاملاً.

_DAY = "strftime('%Y-%m-%d', {c}, 'unixepoch', 'localtime')"
# دفعات الاشتراكات وحدها: لا شحن محفظة ولا شراء إضافة (كلاهما يمرّ بجدول payments).
_SUB_PAY = f"plan <> '{WALLET_PLAN}' AND substr(plan,1,8) <> '__addon_'"


def _win(c, q, a, b, *extra):
    return c.execute(q, (a, b, *extra)).fetchone()[0] or 0


def report_window(a, b):
    """كل أرقام الفترة `[a, b)` في نداء واحد — أساس التقرير الأسبوعي.

    الأسماء تصف ما يعنيه الرقم للمالك لا للجدول: `bots_never_started` بوت أُنشئ
    ولم يُشغَّل، و`bots_started_silent` بوت شغّال لم تصله رسالة عميل واحدة —
    وهما سؤالان مختلفان تماماً (الأول توقّف عند الإعداد، والثاني عند التسويق)."""
    cohort = "SELECT id FROM users WHERE created_at >= ? AND created_at < ? AND role = 'user'"
    with get_conn() as c:
        one = lambda q, *p: c.execute(q, p).fetchone()[0] or 0
        rows = lambda q, *p: [dict(r) for r in c.execute(q, p).fetchall()]
        now = int(time.time())
        out = {
            "from": a, "to": b, "generated_at": now,
            # ---------- الحسابات ----------
            "signups": _win(c, "SELECT COUNT(*) FROM users WHERE created_at>=? AND created_at<? "
                               "AND role='user'", a, b),
            "signups_verified": _win(c, "SELECT COUNT(*) FROM users WHERE created_at>=? AND created_at<? "
                                        "AND role='user' AND email_verified_at IS NOT NULL", a, b),
            "signups_stuck_verify": _win(c, "SELECT COUNT(*) FROM users WHERE created_at>=? AND created_at<? "
                                            "AND role='user' AND verify_required=1 "
                                            "AND email_verified_at IS NULL", a, b),
            "signups_with_phone": _win(c, "SELECT COUNT(*) FROM users WHERE created_at>=? AND created_at<? "
                                          "AND role='user' AND phone IS NOT NULL", a, b),
            "signups_oauth": _win(c, "SELECT COUNT(DISTINCT u.id) FROM users u JOIN user_identities i "
                                     "ON i.user_id=u.id WHERE u.created_at>=? AND u.created_at<?", a, b),
            "users_total": one("SELECT COUNT(*) FROM users WHERE role='user'"),
            "users_blocked": one("SELECT COUNT(*) FROM users WHERE is_blocked=1"),
            "signup_sources": rows(
                "SELECT COALESCE(s.value,'direct') k, COUNT(*) v FROM users u "
                "LEFT JOIN settings s ON s.user_id=u.id AND s.key='signup_src' "
                "WHERE u.created_at>=? AND u.created_at<? AND u.role='user' "
                "GROUP BY k ORDER BY v DESC LIMIT 10", a, b),
            # ---------- البوتات ----------
            "bots_new": _win(c, "SELECT COUNT(*) FROM bots WHERE created_at>=? AND created_at<?", a, b),
            "bots_new_active": _win(c, "SELECT COUNT(*) FROM bots WHERE created_at>=? AND created_at<? "
                                       "AND is_active=1", a, b),
            "bots_total": one("SELECT COUNT(*) FROM bots"),
            "bots_active": one("SELECT COUNT(*) FROM bots WHERE is_active=1"),
            "bots_by_template": rows("SELECT template k, COUNT(*) v FROM bots WHERE created_at>=? "
                                     "AND created_at<? GROUP BY k ORDER BY v DESC", a, b),
            "bots_by_channel": rows("SELECT COALESCE(channel,'telegram') k, COUNT(*) v FROM bots "
                                    "WHERE created_at>=? AND created_at<? GROUP BY k ORDER BY v DESC", a, b),
            # أُنشئ في الفترة ولم يُشغَّل بعد
            "bots_never_started": _win(c, "SELECT COUNT(*) FROM bots WHERE created_at>=? AND created_at<? "
                                          "AND is_active=0", a, b),
            # شغّال لكن لم تصله رسالة عميل واحدة منذ إنشائه
            "bots_started_silent": _win(
                c, "SELECT COUNT(*) FROM bots b WHERE b.created_at>=? AND b.created_at<? AND b.is_active=1 "
                   "AND NOT EXISTS (SELECT 1 FROM messages m WHERE m.bot_id=b.id AND m.direction='in')", a, b),
            # أصحاب حسابات سجّلوا في الفترة ولم ينشئوا بوتاً أصلاً
            "signups_no_bot": _win(c, f"SELECT COUNT(*) FROM ({cohort}) x WHERE NOT EXISTS "
                                      "(SELECT 1 FROM bots b WHERE b.owner_id=x.id)", a, b),
            # كل البوتات الصامتة (لا رسائل واردة في الفترة) بغضّ النظر عن تاريخ إنشائها
            "silent_active_bots": one(
                "SELECT COUNT(*) FROM bots b WHERE b.is_active=1 AND NOT EXISTS "
                "(SELECT 1 FROM messages m WHERE m.bot_id=b.id AND m.direction='in' "
                " AND m.created_at>=? AND m.created_at<?)", a, b),
            # ---------- المحادثات ----------
            "msgs_in": _win(c, "SELECT COUNT(*) FROM messages WHERE direction='in' "
                               "AND created_at>=? AND created_at<?", a, b),
            "msgs_out": _win(c, "SELECT COUNT(*) FROM messages WHERE direction='out' "
                                "AND created_at>=? AND created_at<?", a, b),
            "msgs_by_sender": rows("SELECT sender k, COUNT(*) v FROM messages WHERE created_at>=? "
                                   "AND created_at<? GROUP BY k ORDER BY v DESC", a, b),
            "customers_active": _win(c, "SELECT COUNT(DISTINCT bot_id || '|' || peer) FROM messages "
                                        "WHERE direction='in' AND created_at>=? AND created_at<?", a, b),
            "customers_new": _win(c, "SELECT COUNT(*) FROM bot_users WHERE created_at>=? "
                                     "AND created_at<?", a, b),
            "opted_out": one("SELECT COUNT(*) FROM bot_users WHERE opted_out=1"),
            "human_takeovers": one("SELECT COUNT(*) FROM conversations WHERE mode='human'"),
            # ---------- النتائج ----------
            "leads": _win(c, "SELECT COUNT(*) FROM leads WHERE created_at>=? AND created_at<?", a, b),
            "orders": _win(c, "SELECT COUNT(*) FROM orders WHERE created_at>=? AND created_at<?", a, b),
            "orders_value": round(float(_win(c, "SELECT COALESCE(SUM(total),0) FROM orders "
                                                "WHERE created_at>=? AND created_at<?", a, b)), 2),
            "bookings": _win(c, "SELECT COUNT(*) FROM bookings WHERE created_at>=? AND created_at<?", a, b),
            # ---------- المال ----------
            "pay_sent": _win(c, f"SELECT COUNT(*) FROM payments WHERE {_SUB_PAY} "
                                "AND created_at>=? AND created_at<?", a, b),
            "pay_approved": _win(c, f"SELECT COUNT(*) FROM payments WHERE {_SUB_PAY} AND status='approved' "
                                    "AND decided_at>=? AND decided_at<?", a, b),
            "pay_rejected": _win(c, f"SELECT COUNT(*) FROM payments WHERE {_SUB_PAY} AND status='rejected' "
                                    "AND decided_at>=? AND decided_at<?", a, b),
            "revenue": round(float(_win(c, f"SELECT COALESCE(SUM(amount),0) FROM payments WHERE {_SUB_PAY} "
                                           "AND status='approved' AND decided_at>=? AND decided_at<?",
                                        a, b)), 2),
            "wallet_topups": round(float(one("SELECT COALESCE(SUM(amount),0) FROM payments WHERE plan=? "
                                            "AND status='approved' AND decided_at>=? AND decided_at<?",
                                            WALLET_PLAN, a, b)), 2),
            "addons_sold": _win(c, "SELECT COUNT(*) FROM payments WHERE substr(plan,1,8)='__addon_' "
                                   "AND status='approved' AND decided_at>=? AND decided_at<?", a, b),
            "pay_pending": one("SELECT COUNT(*) FROM payments WHERE status='pending'"),
            "pay_pending_late": one("SELECT COUNT(*) FROM payments WHERE status='pending' "
                                    "AND created_at < ?", now - 86400),
            "refusals": _win(c, "SELECT COUNT(*) FROM receipt_refusals WHERE created_at>=? "
                                "AND created_at<?", a, b),
            "refusals_by_reason": rows("SELECT reason k, COUNT(*) v FROM receipt_refusals "
                                       "WHERE created_at>=? AND created_at<? GROUP BY k ORDER BY v DESC",
                                       a, b),
            "paying_now": one("SELECT COUNT(*) FROM subscriptions WHERE plan<>'free' AND status='active' "
                              "AND (expires_at IS NULL OR expires_at>?)", now),
            "subs_expired": _win(c, "SELECT COUNT(*) FROM subscriptions WHERE expires_at>=? "
                                    "AND expires_at<?", a, b),
            "bot_payments": _win(c, "SELECT COUNT(*) FROM bot_payments WHERE created_at>=? "
                                    "AND created_at<?", a, b),
            # ---------- الدعم ----------
            "tickets_new": _win(c, "SELECT COUNT(*) FROM tickets WHERE created_at>=? AND created_at<?", a, b),
            "tickets_by_kind": rows("SELECT kind k, COUNT(*) v FROM tickets WHERE created_at>=? "
                                    "AND created_at<? GROUP BY k ORDER BY v DESC", a, b),
            "tickets_open": one("SELECT COUNT(*) FROM tickets WHERE status='open'"),
            "tickets_first_reply_avg": int(c.execute(
                "SELECT COALESCE(AVG(m.fr - t.created_at),0) FROM tickets t JOIN "
                "(SELECT ticket_id, MIN(created_at) fr FROM ticket_msgs WHERE sender='staff' "
                " GROUP BY ticket_id) m ON m.ticket_id=t.id "
                "WHERE t.created_at>=? AND t.created_at<?", (a, b)).fetchone()[0] or 0),
            "tickets_unanswered": one(
                "SELECT COUNT(*) FROM tickets t WHERE t.status='open' AND NOT EXISTS "
                "(SELECT 1 FROM ticket_msgs m WHERE m.ticket_id=t.id AND m.sender='staff')"),
            "custom_requests": _win(c, "SELECT COUNT(*) FROM bot_requests WHERE created_at>=? "
                                       "AND created_at<?", a, b),
            # ---------- الزوار ----------
            "visitors": _win(c, "SELECT COUNT(DISTINCT day || '|' || vid) FROM page_views "
                                "WHERE created_at>=? AND created_at<?", a, b),
            "views": _win(c, "SELECT COUNT(*) FROM page_views WHERE created_at>=? AND created_at<?", a, b),
            "pricing_visitors": _win(c, "SELECT COUNT(DISTINCT day || '|' || vid) FROM page_views "
                                        "WHERE created_at>=? AND created_at<? AND path='/pricing'", a, b),
            "top_pages": rows("SELECT path k, COUNT(DISTINCT day || '|' || vid) v FROM page_views "
                              "WHERE created_at>=? AND created_at<? GROUP BY k ORDER BY v DESC LIMIT 8",
                              a, b),
            "visitor_sources": rows("SELECT COALESCE(src, ref, 'direct') k, "
                                    "COUNT(DISTINCT day || '|' || vid) v FROM page_views "
                                    "WHERE created_at>=? AND created_at<? GROUP BY k ORDER BY v DESC LIMIT 8",
                                    a, b),
            # ---------- البريد ----------
            "emails_sent": _win(c, "SELECT COUNT(*) FROM email_sends WHERE status='sent' "
                                   "AND sent_at>=? AND sent_at<?", a, b),
            "emails_failed": _win(c, "SELECT COUNT(*) FROM email_sends WHERE status='failed' "
                                     "AND sent_at>=? AND sent_at<?", a, b),
            "emails_skipped": _win(c, "SELECT COUNT(*) FROM email_sends WHERE status='skipped' "
                                      "AND sent_at>=? AND sent_at<?", a, b),
            "verify_emails": _win(c, "SELECT COUNT(*) FROM email_verifications WHERE sent_at>=? "
                                     "AND sent_at<?", a, b),
            # ---------- قمع دفعة المسجّلين في الفترة ----------
            "funnel": {
                "signup": _win(c, f"SELECT COUNT(*) FROM ({cohort})", a, b),
                "bot_created": _win(c, f"SELECT COUNT(DISTINCT owner_id) FROM bots "
                                       f"WHERE owner_id IN ({cohort})", a, b),
                "bot_live": _win(c, "SELECT COUNT(DISTINCT user_id) FROM funnel WHERE kind='bot_live' "
                                    f"AND user_id IN ({cohort})", a, b),
                "first_message": _win(c, f"SELECT COUNT(DISTINCT b.owner_id) FROM bots b "
                                         f"WHERE b.owner_id IN ({cohort}) AND EXISTS "
                                         "(SELECT 1 FROM messages m WHERE m.bot_id=b.id "
                                         " AND m.direction='in')", a, b),
                "paid": _win(c, f"SELECT COUNT(DISTINCT user_id) FROM payments WHERE {_SUB_PAY} "
                                f"AND status='approved' AND user_id IN ({cohort})", a, b),
            },
        }
    return out


def report_daily(a, b):
    """سلسلة يومية للفترة: التسجيل والبوتات والرسائل والإيراد والطلبات.
    منها يُرسم البياني وتُحسب خطوط الاتجاه والتنبؤ."""
    day_u = _DAY.format(c="created_at")
    day_d = _DAY.format(c="decided_at")
    with get_conn() as c:
        grab = lambda q, *p: {r[0]: r[1] for r in c.execute(q, p).fetchall()}
        signups = grab(f"SELECT {day_u} d, COUNT(*) FROM users WHERE created_at>=? AND created_at<? "
                       "AND role='user' GROUP BY d", a, b)
        bots = grab(f"SELECT {day_u} d, COUNT(*) FROM bots WHERE created_at>=? AND created_at<? "
                    "GROUP BY d", a, b)
        mi = grab(f"SELECT {day_u} d, COUNT(*) FROM messages WHERE direction='in' "
                  "AND created_at>=? AND created_at<? GROUP BY d", a, b)
        mo = grab(f"SELECT {day_u} d, COUNT(*) FROM messages WHERE direction='out' "
                  "AND created_at>=? AND created_at<? GROUP BY d", a, b)
        orders = grab(f"SELECT {day_u} d, COUNT(*) FROM orders WHERE created_at>=? AND created_at<? "
                      "GROUP BY d", a, b)
        rev = grab(f"SELECT {day_d} d, COALESCE(SUM(amount),0) FROM payments WHERE {_SUB_PAY} "
                   "AND status='approved' AND decided_at>=? AND decided_at<? GROUP BY d", a, b)
        views = grab(f"SELECT day d, COUNT(DISTINCT vid) FROM page_views WHERE created_at>=? "
                     "AND created_at<? GROUP BY d", a, b)
    import datetime
    out, day = [], datetime.date.fromtimestamp(a)
    last = datetime.date.fromtimestamp(max(a, b - 1))
    while day <= last:
        k = day.isoformat()
        out.append({"day": k, "signups": signups.get(k, 0), "bots": bots.get(k, 0),
                    "msgs_in": mi.get(k, 0), "msgs_out": mo.get(k, 0),
                    "orders": orders.get(k, 0), "revenue": round(float(rev.get(k, 0) or 0), 2),
                    "visitors": views.get(k, 0)})
        day += datetime.timedelta(days=1)
    return out


def report_bots(a, b, limit=200):
    """صفّ لكل بوت: حركته في الفترة ونتائجها ومن يملكه. مرتّب بالأكثر نشاطاً."""
    win = "created_at>=? AND created_at<?"
    q = f"""
        SELECT b.id, b.name, b.template, COALESCE(b.channel,'telegram') channel, b.is_active,
               b.created_at, b.owner_id, u.username owner, u.role owner_role,
               COALESCE(s.plan,'free') plan,
               (SELECT COUNT(*) FROM messages m WHERE m.bot_id=b.id AND m.direction='in'
                 AND m.{win}) msgs_in,
               (SELECT COUNT(*) FROM messages m WHERE m.bot_id=b.id AND m.direction='out'
                 AND m.{win}) msgs_out,
               (SELECT COUNT(*) FROM messages m WHERE m.bot_id=b.id AND m.sender='ai'
                 AND m.{win}) ai_replies,
               (SELECT COUNT(*) FROM messages m WHERE m.bot_id=b.id AND m.sender='human'
                 AND m.{win}) human_replies,
               (SELECT COUNT(DISTINCT peer) FROM messages m WHERE m.bot_id=b.id AND m.direction='in'
                 AND m.{win}) customers,
               (SELECT COUNT(*) FROM bot_users x WHERE x.bot_id=b.id AND x.{win}) new_customers,
               (SELECT COUNT(*) FROM bot_users x WHERE x.bot_id=b.id AND x.opted_out=1) opted_out,
               (SELECT COUNT(*) FROM leads l WHERE l.bot_id=b.id AND l.{win}) leads,
               (SELECT COUNT(*) FROM orders o WHERE o.bot_id=b.id AND o.{win}) orders,
               (SELECT COALESCE(SUM(total),0) FROM orders o WHERE o.bot_id=b.id AND o.{win}) orders_value,
               (SELECT COUNT(*) FROM bookings k WHERE k.bot_id=b.id AND k.{win}) bookings,
               (SELECT MAX(created_at) FROM messages m WHERE m.bot_id=b.id AND m.direction='in') last_in,
               (SELECT COUNT(*) FROM conversations v WHERE v.bot_id=b.id AND v.mode='human') human_convos
        FROM bots b JOIN users u ON u.id=b.owner_id
        LEFT JOIN subscriptions s ON s.user_id=b.owner_id
        ORDER BY msgs_in DESC, b.created_at DESC LIMIT ?
    """
    p = (a, b) * 10          # عدد نوافذ {win} في الاستعلام أعلاه
    with get_conn() as c:
        rows = [dict(r) for r in c.execute(q, (*p, int(limit))).fetchall()]
    for r in rows:
        r["orders_value"] = round(float(r["orders_value"] or 0), 2)
    return rows


def report_bot_options(limit=400):
    """قائمة مختصرة للفلترة (رقم البوت واسمه وصاحبه) — بلا توكن ولا إعداد."""
    with get_conn() as c:
        return [dict(r) for r in c.execute(
            "SELECT b.id, b.name, u.username owner FROM bots b JOIN users u ON u.id=b.owner_id "
            "ORDER BY b.id DESC LIMIT ?", (int(limit),)).fetchall()]


# رموز المشاكل: المفتاح يُترجم في الواجهة، فلا نصّ عربي في القاعدة.
PROBLEM_KINDS = ("verify_stuck", "receipt_refused", "payment_rejected", "payment_waiting",
                 "ticket_open", "bot_never_started", "bot_silent", "no_bot", "blocked")


def report_problem_users(a, b, limit=200):
    """من تعثّر في الفترة ولماذا — صفٌّ لكل مستخدم بقائمة أسبابه.

    «مشكلة» هنا حدث ملموس لا انطباع: إيصال مرفوض آلياً، دفعة رُفضت، دفعة تنتظرنا
    أكثر من يوم، تذكرة دعم مفتوحة، بريد لم يُؤكَّد فالحساب محجوب، بوت أُنشئ ولم
    يُشغَّل، بوت شغّال بلا رسالة واحدة، حساب بلا بوت أصلاً، وحساب محظور."""
    late = int(time.time()) - 86400
    parts = (
        ("verify_stuck", "SELECT id user_id, 1 n FROM users WHERE created_at>=? AND created_at<? "
                         "AND role='user' AND verify_required=1 AND email_verified_at IS NULL"),
        ("receipt_refused", "SELECT user_id, COUNT(*) n FROM receipt_refusals "
                            "WHERE created_at>=? AND created_at<? GROUP BY user_id"),
        ("payment_rejected", f"SELECT user_id, COUNT(*) n FROM payments WHERE {_SUB_PAY} "
                             "AND status='rejected' AND decided_at>=? AND decided_at<? GROUP BY user_id"),
        ("payment_waiting", "SELECT user_id, COUNT(*) n FROM payments WHERE status='pending' "
                            "AND created_at>=? AND created_at<? AND created_at<? GROUP BY user_id"),
        ("ticket_open", "SELECT user_id, COUNT(*) n FROM tickets WHERE created_at>=? AND created_at<? "
                        "AND status<>'closed' GROUP BY user_id"),
        ("bot_never_started", "SELECT owner_id user_id, COUNT(*) n FROM bots WHERE created_at>=? "
                              "AND created_at<? AND is_active=0 GROUP BY owner_id"),
        ("bot_silent", "SELECT b.owner_id user_id, COUNT(*) n FROM bots b WHERE b.created_at>=? "
                       "AND b.created_at<? AND b.is_active=1 AND NOT EXISTS "
                       "(SELECT 1 FROM messages m WHERE m.bot_id=b.id AND m.direction='in') "
                       "GROUP BY b.owner_id"),
        ("no_bot", "SELECT id user_id, 1 n FROM users u WHERE created_at>=? AND created_at<? "
                   "AND role='user' AND NOT EXISTS (SELECT 1 FROM bots b WHERE b.owner_id=u.id)"),
        ("blocked", "SELECT id user_id, 1 n FROM users WHERE is_blocked=1 AND created_at>=? "
                    "AND created_at<?"),
    )
    found = {}
    with get_conn() as c:
        for kind, q in parts:
            p = (a, b, late) if kind == "payment_waiting" else (a, b)
            for r in c.execute(q, p).fetchall():
                u = found.setdefault(r["user_id"], {"user_id": r["user_id"], "problems": {}})
                u["problems"][kind] = u["problems"].get(kind, 0) + (r["n"] or 1)
        ids = list(found)
        for i in range(0, len(ids), 400):          # SQLite: سقف المتغيّرات في الاستعلام
            chunk = ids[i:i + 400]
            ph = ",".join("?" * len(chunk))
            for r in c.execute(
                    f"SELECT u.id, u.username, u.created_at, u.email IS NOT NULL has_email, "
                    f"COALESCE(s.plan,'free') plan FROM users u "
                    f"LEFT JOIN subscriptions s ON s.user_id=u.id WHERE u.id IN ({ph})",
                    chunk).fetchall():
                found[r["id"]].update(username=r["username"], created_at=r["created_at"],
                                      has_email=bool(r["has_email"]), plan=r["plan"])
    out = [u for u in found.values() if u.get("username")]
    out.sort(key=lambda u: (-len(u["problems"]), -sum(u["problems"].values())))
    return out[:limit]


def report_emails(a, b):
    """نتائج البريد في الفترة: كل حملة وما وصل منها وما فشل، وإجمالي الفترة."""
    with get_conn() as c:
        camps = [dict(r) for r in c.execute(
            "SELECT c.id, c.kind, c.audience, c.status, c.note, c.total, c.created_at, c.finished_at, "
            " c.content, "
            " (SELECT COUNT(*) FROM email_sends e WHERE e.campaign_id=c.id AND e.status='sent') sent, "
            " (SELECT COUNT(*) FROM email_sends e WHERE e.campaign_id=c.id AND e.status='failed') failed, "
            " (SELECT COUNT(*) FROM email_sends e WHERE e.campaign_id=c.id AND e.status='skipped') skipped "
            "FROM email_campaigns c WHERE c.created_at>=? AND c.created_at<? "
            "ORDER BY c.created_at DESC", (a, b)).fetchall()]
        by_status = {r[0]: r[1] for r in c.execute(
            "SELECT status, COUNT(*) FROM email_sends WHERE sent_at>=? AND sent_at<? "
            "GROUP BY status", (a, b)).fetchall()}
        failed_users = [dict(r) for r in c.execute(
            "SELECT u.username, COUNT(*) n FROM email_sends e JOIN users u ON u.id=e.user_id "
            "WHERE e.status='failed' AND e.sent_at>=? AND e.sent_at<? "
            "GROUP BY u.id ORDER BY n DESC LIMIT 20", (a, b)).fetchall()]
    for r in camps:
        try:
            content = json.loads(r.pop("content") or "{}")
        except ValueError:
            content = {}
        r["subject"] = ((content.get("ar") or {}).get("subject") or "").strip()[:120]
    return {"campaigns": camps, "by_status": by_status, "failed_users": failed_users}


def report_expiring(days=7):
    """اشتراكات تنتهي خلال الأيام القادمة — أساس تقدير التجديد وخطر الفقد."""
    now = int(time.time())
    with get_conn() as c:
        return [dict(r) for r in c.execute(
            "SELECT u.id user_id, u.username, s.plan, s.expires_at, s.billing_cycle "
            "FROM subscriptions s JOIN users u ON u.id=s.user_id "
            "WHERE s.plan<>'free' AND s.status='active' AND s.expires_at IS NOT NULL "
            "AND s.expires_at>=? AND s.expires_at<? ORDER BY s.expires_at",
            (now, now + int(days) * 86400)).fetchall()]


# ---------- تحليل الرسائل (conv_insights.py) ----------
def conv_totals(a, b, bot_id=None):
    """أعداد الرسائل في الفترة مقسّمة كما يحتاجها التحليل (مرسِل · نوع · ساعة)."""
    where = "created_at>=? AND created_at<? AND direction<>'note'" + (" AND bot_id=?" if bot_id else "")
    p = (a, b) + ((int(bot_id),) if bot_id else ())
    with get_conn() as c:
        rows = lambda q: [dict(r) for r in c.execute(q, p).fetchall()]
        one = lambda q: c.execute(q, p).fetchone()[0] or 0
        return {
            "total": one(f"SELECT COUNT(*) FROM messages WHERE {where}"),
            "by_sender": rows(f"SELECT sender k, COUNT(*) v FROM messages WHERE {where} "
                              "GROUP BY k ORDER BY v DESC"),
            "by_kind": rows(f"SELECT kind k, COUNT(*) v FROM messages WHERE {where} "
                            "GROUP BY k ORDER BY v DESC"),
            "by_direction": rows(f"SELECT direction k, COUNT(*) v FROM messages WHERE {where} "
                                 "GROUP BY k ORDER BY v DESC"),
            "conversations": one(f"SELECT COUNT(DISTINCT bot_id || '|' || peer) FROM messages "
                                 f"WHERE {where}"),
            "bots": one(f"SELECT COUNT(DISTINCT bot_id) FROM messages WHERE {where}"),
        }


CONV_ROWS_MAX = 40000


def conv_rows(a, b, bot_id=None, limit=CONV_ROWS_MAX):
    """رسائل الفترة للتحليل النصّي — الأحدث أولاً وبسقف صريح.

    السقف مقصود: التحليل يمرّ على كل صف في الذاكرة، وعملية الويب نفسها تشغّل
    البوتات (`workers=1`). ما تجاوز السقف يُعلَن في التقرير بدل أن يُسقَط بصمت."""
    where = "m.created_at>=? AND m.created_at<? AND m.direction<>'note'" + (" AND m.bot_id=?" if bot_id else "")
    p = (a, b) + ((int(bot_id),) if bot_id else ()) + (int(limit),)
    with get_conn() as c:
        rows = [dict(r) for r in c.execute(
            f"SELECT m.bot_id, m.peer, m.direction, m.sender, m.kind, m.text, m.created_at, "
            f"b.name bot_name FROM messages m LEFT JOIN bots b ON b.id=m.bot_id "
            f"WHERE {where} ORDER BY m.id DESC LIMIT ?", p).fetchall()]
    rows.reverse()                                  # التحليل يحتاجها بترتيبها الزمني
    return rows


def admin_emails():
    """بريد حسابات الإدارة وحدها — إليه يُرسل التقرير الأسبوعي."""
    with get_conn() as c:
        return [r[0] for r in c.execute(
            "SELECT email FROM users WHERE role='admin' AND email IS NOT NULL "
            "AND is_blocked=0 ORDER BY id").fetchall() if r[0]]


# ============================================================================
#  محرّك التفعيل — من توقّف في منتصف الطريق (activation.py)
# ============================================================================
# التقرير قال إن 6 من كل 10 مسجّلين لا ينشئون بوتاً أبداً، وإن بوتات تُشغَّل ولا
# تصلها رسالة واحدة. هذه الدوال تجد **من توقّف وأين بالضبط**، مرة واحدة لكل حالة.
#
# `nudge_log` يمنع تكرار الرسالة نفسها للشخص نفسه إلى الأبد: المفتاح
# (المستخدم، النوع، المرجع) — والمرجع رقم البوت في الحالات الخاصة ببوت بعينه،
# فصاحب بوتين يُنبَّه لكل واحد منهما مرة، لا مرة واحدة للاثنين.

def _activation_tables(c):
    c.executescript("""
        CREATE TABLE IF NOT EXISTS nudge_log(
            user_id INTEGER NOT NULL,
            kind TEXT NOT NULL,                  -- no_bot_1h | bot_off_2h | ...
            ref INTEGER NOT NULL DEFAULT 0,      -- رقم البوت إن كانت الرسالة عن بوت
            sent_at INTEGER NOT NULL,
            channel TEXT,                        -- telegram | email (أول قناة وصلت)
            PRIMARY KEY(user_id, kind, ref),
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS ix_nudge_at ON nudge_log(sent_at);
    """)


def nudge_sent(user_id, kind, ref=0):
    with get_conn() as c:
        return c.execute("SELECT 1 FROM nudge_log WHERE user_id=? AND kind=? AND ref=?",
                         (user_id, kind, ref)).fetchone() is not None


def log_nudge(user_id, kind, ref=0, channel=None):
    """يُسجَّل **بعد** وصول الرسالة فعلاً — رسالة لم تصل تُعاد في الدورة التالية."""
    with get_conn() as c:
        c.execute("INSERT OR IGNORE INTO nudge_log(user_id,kind,ref,sent_at,channel) "
                  "VALUES(?,?,?,?,?)", (user_id, kind, ref, int(time.time()), channel))


def nudge_counts(a, b):
    """كم رسالة تفعيل أُرسلت في الفترة، وكم من أصحابها تقدّم بعدها فعلاً.

    `advanced` = أنشأ بوتاً بعد الرسالة (لحالات «بلا بوت») أو شغّل بوته (للباقي) —
    وهي الطريقة الوحيدة لمعرفة إن كانت الرسائل تنفع أصلاً بدل إرسالها على الإيمان."""
    with get_conn() as c:
        return [dict(r) for r in c.execute("""
            SELECT n.kind k, COUNT(*) v,
                   SUM(CASE WHEN EXISTS (SELECT 1 FROM bots b WHERE b.owner_id = n.user_id
                                          AND b.created_at >= n.sent_at)
                             OR EXISTS (SELECT 1 FROM bots b2 WHERE b2.owner_id = n.user_id
                                          AND b2.is_active = 1 AND n.ref = b2.id)
                        THEN 1 ELSE 0 END) advanced
            FROM nudge_log n WHERE n.sent_at >= ? AND n.sent_at < ?
            GROUP BY k ORDER BY v DESC""", (a, b)).fetchall()]


# المرشّحون لكل حالة. كل استعلام يستبعد من نُبِّه من قبل، ومن حُظر، وحسابات الفريق.
_ALIVE = "u.role = 'user' AND u.is_blocked = 0"
_NOT_NUDGED = ("NOT EXISTS (SELECT 1 FROM nudge_log n WHERE n.user_id = u.id "
               "AND n.kind = ? AND n.ref = {ref})")


def activation_candidates(kind, older_than, younger_than=30 * 86400, limit=50):
    """صفوف {user_id, username, email, ref, bot_name} لمن ينطبق عليه `kind` الآن.

    `younger_than` سقف عمر: لا نلاحق من سجّل من شهر — الرسالة بعد شهر إزعاج لا مساعدة."""
    now = int(time.time())
    hi, lo = now - int(older_than), now - int(younger_than)      # القديم ≤ التسجيل ≤ الأحدث
    base = ("SELECT u.id user_id, u.username, u.email, 0 ref, '' bot_name FROM users u "
            f"WHERE {_ALIVE} AND u.created_at <= ? AND u.created_at >= ? ")
    if kind in ("no_bot_1h", "no_bot_24h", "no_bot_72h"):
        q = (base + "AND NOT EXISTS (SELECT 1 FROM bots b WHERE b.owner_id = u.id) AND "
             + _NOT_NUDGED.format(ref=0) + " ORDER BY u.created_at DESC LIMIT ?")
    elif kind == "verify_stuck_2h":
        q = (base + "AND u.verify_required = 1 AND u.email_verified_at IS NULL AND "
             + _NOT_NUDGED.format(ref=0) + " ORDER BY u.created_at DESC LIMIT ?")
    elif kind in ("bot_off_2h", "bot_silent_24h"):
        active = "1" if kind == "bot_silent_24h" else "0"
        silent = ("AND NOT EXISTS (SELECT 1 FROM messages m WHERE m.bot_id = b.id "
                  "AND m.direction = 'in') " if kind == "bot_silent_24h" else "")
        q = ("SELECT u.id user_id, u.username, u.email, b.id ref, b.name bot_name "
             "FROM bots b JOIN users u ON u.id = b.owner_id "
             f"WHERE {_ALIVE} AND b.is_active = {active} AND b.created_at <= ? "
             f"AND b.created_at >= ? {silent}"
             "AND NOT EXISTS (SELECT 1 FROM nudge_log n WHERE n.user_id = u.id "
             "AND n.kind = ? AND n.ref = b.id) ORDER BY b.created_at DESC LIMIT ?")
    else:
        raise ValueError(f"unknown activation kind: {kind}")
    with get_conn() as c:
        return [dict(r) for r in c.execute(q, (hi, lo, kind, int(limit))).fetchall()]


# ---------- محادثات تنتظر رداً (تنبيه صاحب البوت) ----------
def waiting_conversations(min_seconds=900, max_seconds=24 * 3600, limit=30):
    """محادثات آخر رسالة فيها من العميل ومضى عليها `min_seconds` بلا ردّ.

    الحدّ الأعلى مقصود: محادثة من يومين ليست «تنتظر» — إنها ضائعة، والتنبيه عليها
    الآن إزعاج بلا فائدة. `waiting_alert_at` يمنع تكرار التنبيه لنفس الانتظار."""
    now = int(time.time())
    with get_conn() as c:
        return [dict(r) for r in c.execute("""
            SELECT v.bot_id, v.peer, v.name, v.last_text, v.last_at, b.name bot_name,
                   b.owner_id
            FROM conversations v JOIN bots b ON b.id = v.bot_id
            WHERE v.mode = 'bot' AND v.last_at <= ? AND v.last_at >= ?
              AND (v.waiting_alert_at IS NULL OR v.waiting_alert_at < v.last_at)
              AND (SELECT m.direction FROM messages m WHERE m.bot_id = v.bot_id
                    AND m.peer = v.peer ORDER BY m.id DESC LIMIT 1) = 'in'
            ORDER BY v.last_at LIMIT ?""",
            (now - int(min_seconds), now - int(max_seconds), int(limit))).fetchall()]


def mark_waiting_alerted(bot_id, peer):
    with get_conn() as c:
        c.execute("UPDATE conversations SET waiting_alert_at=? WHERE bot_id=? AND peer=?",
                  (int(time.time()), bot_id, peer))


# ─────────────────────────────  فريق الحساب ومفاتيح الـAPI  ─────────────────────────────
# «الحساب» ليس «المستخدم»: صاحب العمل يدعو موظفيه، فيعملون داخل حسابه هو على نفس البوتات.
# `users.works_for` هو كل الفرق — و`account_of()` هي النقطة الوحيدة التي تترجم مستخدماً إلى
# حساب، فلا يتسرّب هذا التفريق إلى بقية الكود.
#
# الأدوار: owner (صاحب الحساب) · admin (يرى الأسرار ويدير الفريق) · member (البوتات فقط).
# الأسرار (توكن واتساب، مفاتيح الـAPI) لا يراها member إطلاقاً، ولا يراها admin إلا بعد
# إعادة إدخال كلمة مروره (بوابة `app._sudo_ok`).
TEAM_ROLES = ("admin", "member")


def _team_tables(c):
    c.executescript("""
        CREATE TABLE IF NOT EXISTS team_invites(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            owner_id INTEGER NOT NULL,
            token_idx TEXT NOT NULL UNIQUE,      -- HMAC للرمز: لا نخزّن الرابط نفسه أبداً
            role TEXT NOT NULL DEFAULT 'member',
            email TEXT,                          -- اختياري: الدعوة مقصورة على هذا البريد
            note TEXT NOT NULL DEFAULT '',
            created_at INTEGER NOT NULL,
            expires_at INTEGER NOT NULL,
            used_at INTEGER,
            used_by INTEGER,
            revoked_at INTEGER,
            FOREIGN KEY(owner_id) REFERENCES users(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS ix_team_inv_owner ON team_invites(owner_id);
        CREATE TABLE IF NOT EXISTS api_keys(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            owner_id INTEGER NOT NULL,           -- الحساب لا المستخدم
            bot_id INTEGER,                      -- NULL = كل بوتات الحساب
            name TEXT NOT NULL DEFAULT '',
            key_idx TEXT NOT NULL UNIQUE,        -- HMAC للمفتاح؛ المفتاح نفسه لا يُخزَّن
            prefix TEXT NOT NULL,                -- أول محارف للعرض والتمييز
            created_at INTEGER NOT NULL,
            created_by INTEGER,
            last_used_at INTEGER,
            revoked_at INTEGER,
            FOREIGN KEY(owner_id) REFERENCES users(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS ix_api_keys_owner ON api_keys(owner_id);
    """)


def account_of(user_id):
    """الحساب الذي يعمل فيه المستخدم: نفسه، أو صاحب العمل الذي انضمّ إلى فريقه."""
    if not user_id:
        return user_id
    with get_conn() as c:
        r = c.execute("SELECT works_for FROM users WHERE id=?", (user_id,)).fetchone()
    return (r["works_for"] or user_id) if r else user_id


def team_role(user_id):
    """owner | admin | member — صاحب الحساب دائماً owner."""
    with get_conn() as c:
        r = c.execute("SELECT works_for, team_role FROM users WHERE id=?", (user_id,)).fetchone()
    if not r or not r["works_for"]:
        return "owner"
    return r["team_role"] if r["team_role"] in TEAM_ROLES else "member"


def team_members(owner_id):
    with get_conn() as c:
        rows = c.execute(
            "SELECT id, username, email, team_role, created_at FROM users "
            "WHERE works_for=? ORDER BY id", (owner_id,)).fetchall()
    return [dict(r) for r in rows]


def team_size(owner_id):
    with get_conn() as c:
        return c.execute("SELECT COUNT(*) n FROM users WHERE works_for=?",
                         (owner_id,)).fetchone()["n"]


def join_team(owner_id, member_id, role="member"):
    """يُدخِل المستخدم في حساب صاحب العمل. يرفض حين يفقد المستخدم شيئاً يملكه.

    الرفض مقصود: `works_for` يحوّل كل استعلامات البوتات إلى حساب آخر، فمن يملك بوتات
    ستختفي من أمامه. ومن هو صاحب فريق بالفعل لا يصير موظفاً (لا سلسلة حسابات)."""
    if not owner_id or not member_id or owner_id == member_id:
        return "self"
    with get_conn() as c:
        if c.execute("SELECT 1 FROM bots WHERE owner_id=? LIMIT 1", (member_id,)).fetchone():
            return "has_bots"
        if c.execute("SELECT 1 FROM users WHERE works_for=? LIMIT 1", (member_id,)).fetchone():
            return "has_team"
        o = c.execute("SELECT works_for FROM users WHERE id=?", (owner_id,)).fetchone()
        if not o or o["works_for"]:
            return "bad_owner"
        m = c.execute("SELECT role FROM users WHERE id=?", (member_id,)).fetchone()
        if not m:
            return "bad_member"
        if m["role"] != "user":
            return "staff"                        # أدمن المنصة لا ينضم لفريق عميل
        c.execute("UPDATE users SET works_for=?, team_role=? WHERE id=?",
                  (owner_id, role if role in TEAM_ROLES else "member", member_id))
    return ""


def set_team_role(owner_id, member_id, role):
    if role not in TEAM_ROLES:
        return False
    with get_conn() as c:
        return c.execute("UPDATE users SET team_role=? WHERE id=? AND works_for=?",
                         (role, member_id, owner_id)).rowcount > 0


def remove_team_member(owner_id, member_id):
    """يخرج الموظف إلى حسابه هو — لا يُحذف حسابه ولا بوتات صاحب العمل."""
    with get_conn() as c:
        return c.execute("UPDATE users SET works_for=NULL, team_role=NULL "
                         "WHERE id=? AND works_for=?", (member_id, owner_id)).rowcount > 0


# ── دعوات الفريق: رابط تسجيل مخصّص لكل موظف ──────────────────────────────────
def create_team_invite(owner_id, token, role="member", email="", days=7, note=""):
    now = int(time.time())
    with get_conn() as c:
        cur = c.execute(
            "INSERT INTO team_invites(owner_id, token_idx, role, email, note, created_at, expires_at) "
            "VALUES(?,?,?,?,?,?,?)",
            (owner_id, _token_idx(token), role if role in TEAM_ROLES else "member",
             (email or "").strip().lower() or None, (note or "")[:120], now,
             now + max(1, int(days)) * 86400))
        return cur.lastrowid


def team_invite(token):
    """صف الدعوة الصالحة (غير مستعملة ولا ملغاة ولا منتهية) أو None."""
    if not token:
        return None
    with get_conn() as c:
        r = c.execute("SELECT i.*, u.username AS owner_name FROM team_invites i "
                      "JOIN users u ON u.id=i.owner_id "
                      "WHERE i.token_idx=? AND i.used_at IS NULL AND i.revoked_at IS NULL "
                      "AND i.expires_at > ?", (_token_idx(token), int(time.time()))).fetchone()
    return dict(r) if r else None


def use_team_invite(token, user_id):
    """يستهلك الدعوة ويُدخِل المستخدم الفريق — خطوة واحدة فلا تُستعمل مرتين."""
    inv = team_invite(token)
    if not inv:
        return "invalid"
    err = join_team(inv["owner_id"], user_id, inv["role"])
    if err:
        return err
    with get_conn() as c:
        c.execute("UPDATE team_invites SET used_at=?, used_by=? WHERE id=? AND used_at IS NULL",
                  (int(time.time()), user_id, inv["id"]))
    return ""


def list_team_invites(owner_id, limit=20):
    with get_conn() as c:
        rows = c.execute(
            "SELECT id, role, email, note, created_at, expires_at, used_at, used_by, revoked_at "
            "FROM team_invites WHERE owner_id=? ORDER BY id DESC LIMIT ?",
            (owner_id, int(limit))).fetchall()
    return [dict(r) for r in rows]


def revoke_team_invite(owner_id, invite_id):
    with get_conn() as c:
        return c.execute("UPDATE team_invites SET revoked_at=? WHERE id=? AND owner_id=? "
                         "AND used_at IS NULL AND revoked_at IS NULL",
                         (int(time.time()), invite_id, owner_id)).rowcount > 0


# ── مفاتيح الـAPI: يُعرض المفتاح مرة واحدة، ويُخزَّن HMAC له وحده ────────────────
def create_api_key(owner_id, key, name="", bot_id=None, created_by=None):
    with get_conn() as c:
        cur = c.execute(
            "INSERT INTO api_keys(owner_id, bot_id, name, key_idx, prefix, created_at, created_by) "
            "VALUES(?,?,?,?,?,?,?)",
            (owner_id, bot_id or None, (name or "")[:60], _token_idx(key), key[:12],
             int(time.time()), created_by))
        return cur.lastrowid


def list_api_keys(owner_id, include_revoked=False):
    q = ("SELECT k.id, k.bot_id, k.name, k.prefix, k.created_at, k.last_used_at, k.revoked_at, "
         "b.name AS bot_name FROM api_keys k LEFT JOIN bots b ON b.id=k.bot_id WHERE k.owner_id=?")
    if not include_revoked:
        q += " AND k.revoked_at IS NULL"
    with get_conn() as c:
        return [dict(r) for r in c.execute(q + " ORDER BY k.id DESC", (owner_id,)).fetchall()]


def revoke_api_key(owner_id, key_id):
    with get_conn() as c:
        return c.execute("UPDATE api_keys SET revoked_at=? WHERE id=? AND owner_id=? "
                         "AND revoked_at IS NULL",
                         (int(time.time()), key_id, owner_id)).rowcount > 0


def api_key_row(key):
    """صف المفتاح الصالح + تحديث آخر استعمال. None لمفتاح خاطئ أو ملغى."""
    if not key or len(key) < 20:
        return None
    with get_conn() as c:
        r = c.execute("SELECT * FROM api_keys WHERE key_idx=? AND revoked_at IS NULL",
                      (_token_idx(key),)).fetchone()
        if not r:
            return None
        c.execute("UPDATE api_keys SET last_used_at=? WHERE id=?", (int(time.time()), r["id"]))
        return dict(r)


# ─────────────────────────────  جهات الاتصال (CRM)  ─────────────────────────────
# المرحلة 1 من docs/ENTERPRISE_PLAN.md. الجهة ملك **الحساب** (`owner_id` = account_of) لا البوت:
# العميل نفسه على بوتين للحساب = جهة واحدة، و`contact_peers` تربطها بكل (بوت، peer).
# القيم المخصّصة في `fields_json` (JSON1: json_extract/json_each) بدل جدول EAV — الشرائح
# تبحث فيها مباشرةً. المنطق النقي (أنواع، تحقّق، قواعد) في crm.py؛ هنا SQL وحده.
import crm as CRM
from datetime import datetime as _dt, timedelta as _td


def _crm_tables(c):
    c.executescript("""
        CREATE TABLE IF NOT EXISTS companies(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            owner_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            fields_json TEXT NOT NULL DEFAULT '{}',
            created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL,
            FOREIGN KEY(owner_id) REFERENCES users(id) ON DELETE CASCADE
        );
        CREATE UNIQUE INDEX IF NOT EXISTS ux_companies_name ON companies(owner_id, name COLLATE NOCASE);
        CREATE TABLE IF NOT EXISTS contacts(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            owner_id INTEGER NOT NULL,
            name TEXT NOT NULL DEFAULT '',
            phone TEXT,                      -- دولي «+9665…» — مفتاح المطابقة الأساسي
            email TEXT,
            bsuid TEXT,                      -- عميل واتساب باسم مستخدم (رقم مخفي)
            tg_id INTEGER,
            ig_id TEXT,
            company_id INTEGER,
            assignee_id INTEGER,             -- «مسؤول الجهة» من فريق الحساب
            optin INTEGER,                   -- موافقة تسويقية: NULL غير معروف · 1 نعم · 0 لا
            optin_at INTEGER,
            fields_json TEXT NOT NULL DEFAULT '{}',
            source TEXT NOT NULL DEFAULT 'chat',
            created_by INTEGER,
            created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL,
            last_seen_at INTEGER,
            FOREIGN KEY(owner_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY(company_id) REFERENCES companies(id) ON DELETE SET NULL
        );
        CREATE INDEX IF NOT EXISTS ix_contacts_owner ON contacts(owner_id, id);
        CREATE UNIQUE INDEX IF NOT EXISTS ux_contacts_phone ON contacts(owner_id, phone) WHERE phone IS NOT NULL;
        CREATE UNIQUE INDEX IF NOT EXISTS ux_contacts_bsuid ON contacts(owner_id, bsuid) WHERE bsuid IS NOT NULL;
        CREATE UNIQUE INDEX IF NOT EXISTS ux_contacts_tg ON contacts(owner_id, tg_id) WHERE tg_id IS NOT NULL;
        CREATE TABLE IF NOT EXISTS contact_peers(
            bot_id INTEGER NOT NULL,
            peer TEXT NOT NULL,
            contact_id INTEGER NOT NULL,
            PRIMARY KEY(bot_id, peer),
            FOREIGN KEY(bot_id) REFERENCES bots(id) ON DELETE CASCADE,
            FOREIGN KEY(contact_id) REFERENCES contacts(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS ix_contact_peers_c ON contact_peers(contact_id);
        CREATE TABLE IF NOT EXISTS contact_fields(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            owner_id INTEGER NOT NULL,
            entity TEXT NOT NULL DEFAULT 'contact',
            key TEXT NOT NULL,
            label TEXT NOT NULL,
            type TEXT NOT NULL,
            options_json TEXT NOT NULL DEFAULT '[]',
            active INTEGER NOT NULL DEFAULT 1,
            required INTEGER NOT NULL DEFAULT 0,
            position INTEGER NOT NULL DEFAULT 0,
            created_at INTEGER NOT NULL,
            UNIQUE(owner_id, entity, key),
            FOREIGN KEY(owner_id) REFERENCES users(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS tags(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            owner_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            color TEXT NOT NULL DEFAULT 'cyan',
            created_at INTEGER NOT NULL,
            FOREIGN KEY(owner_id) REFERENCES users(id) ON DELETE CASCADE
        );
        CREATE UNIQUE INDEX IF NOT EXISTS ux_tags_name ON tags(owner_id, name COLLATE NOCASE);
        CREATE TABLE IF NOT EXISTS contact_tags(
            contact_id INTEGER NOT NULL,
            tag_id INTEGER NOT NULL,
            created_at INTEGER NOT NULL,
            PRIMARY KEY(contact_id, tag_id),
            FOREIGN KEY(contact_id) REFERENCES contacts(id) ON DELETE CASCADE,
            FOREIGN KEY(tag_id) REFERENCES tags(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS ix_contact_tags_tag ON contact_tags(tag_id);
        CREATE TABLE IF NOT EXISTS segments(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            owner_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            rules_json TEXT NOT NULL DEFAULT '[]',
            created_by INTEGER,
            created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL,
            FOREIGN KEY(owner_id) REFERENCES users(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS ix_segments_owner ON segments(owner_id);
    """)
    _crm_backfill(c)


def _peer_identity(peer):
    """peer ⇒ {عمود: قيمة}: «wa:9665…» رقم · «wa:SA.123…» اسم مستخدم · «tg:123» تليجرام."""
    kind, _, tail = (peer or "").partition(":")
    if kind == "wa" and tail.isdigit():
        return {"phone": "+" + tail}
    if kind == "wa" and tail:
        return {"bsuid": tail}
    if kind == "tg" and tail.lstrip("-").isdigit():
        return {"tg_id": int(tail)}
    return {}


# الأعمدة المسموح البحث بها من _peer_identity — اسم العمود من هنا لا من المدخل
_PEER_COLS = {"phone": "phone", "bsuid": "bsuid", "tg_id": "tg_id"}


def _contact_for_peer(c, bot_id, peer, name="", owner_id=None):
    """يربط (بوت، peer) بجهة اتصال الحساب — ينشئها لو لم توجد. يعيد معرّفها أو None.
    يُستدعى مع كل عميل للبوت، فالمسار الشائع استعلام واحد على المفتاح الأساسي."""
    now = int(time.time())
    name = (name or "")[:120]
    r = c.execute("SELECT contact_id FROM contact_peers WHERE bot_id=? AND peer=?",
                  (bot_id, peer)).fetchone()
    if r:
        c.execute("UPDATE contacts SET last_seen_at=?, name=CASE WHEN name='' THEN ? ELSE name END"
                  " WHERE id=?", (now, name, r[0]))
        return r[0]
    ident = _peer_identity(peer)
    if not ident:
        return None
    if owner_id is None:
        b = c.execute("SELECT owner_id FROM bots WHERE id=?", (bot_id,)).fetchone()
        if not b:
            return None
        owner_id = b[0]
    (key, val), = ident.items()
    col = _PEER_COLS[key]
    row = c.execute(f"SELECT id FROM contacts WHERE owner_id=? AND {col}=?", (owner_id, val)).fetchone()
    if row:
        cid = row[0]
        c.execute("UPDATE contacts SET last_seen_at=?, name=CASE WHEN name='' THEN ? ELSE name END"
                  " WHERE id=?", (now, name, cid))
    else:
        cid = c.execute(f"INSERT INTO contacts(owner_id,name,{col},source,created_at,updated_at,last_seen_at)"
                        " VALUES(?,?,?,'chat',?,?,?)", (owner_id, name, val, now, now, now)).lastrowid
    c.execute("INSERT OR IGNORE INTO contact_peers(bot_id,peer,contact_id) VALUES(?,?,?)",
              (bot_id, peer, cid))
    return cid


def _crm_backfill(c):
    """مرة واحدة: كل عملاء البوتات القائمين يصبحون جهات اتصال لحساباتهم."""
    if c.execute("SELECT 1 FROM platform WHERE key='crm_backfill_v1'").fetchone():
        return
    rows = c.execute("SELECT bu.bot_id, bu.peer, bu.first_name, b.owner_id FROM bot_users bu"
                     " JOIN bots b ON b.id=bu.bot_id WHERE bu.peer IS NOT NULL").fetchall()
    for r in rows:
        _contact_for_peer(c, r["bot_id"], r["peer"], r["first_name"] or "", r["owner_id"])
    c.execute("INSERT OR REPLACE INTO platform(key,value) VALUES('crm_backfill_v1',?)", (str(len(rows)),))


def link_contact(bot_id, peer, name=""):
    """أي عميل يراسل بوتاً يصبح جهة اتصال. لا يرمي أبداً — المحادثة أهم من السجل."""
    try:
        with get_conn() as c:
            return _contact_for_peer(c, bot_id, peer, name)
    except Exception:
        log.exception("link_contact failed bot=%s", bot_id)
        return None


def contact_channels(contact_id):
    with get_conn() as c:
        return [dict(r) for r in c.execute(
            "SELECT cp.bot_id, cp.peer, b.name AS bot_name, b.channel FROM contact_peers cp"
            " JOIN bots b ON b.id=cp.bot_id WHERE cp.contact_id=?", (contact_id,))]


def set_contact_optin_by_peer(bot_id, peer, value):
    """STOP أو الموافقة من المحادثة تنعكس على جهة الاتصال (§55): 0 إيقاف · 1 موافقة."""
    now = int(time.time())
    try:
        with get_conn() as c:
            c.execute("UPDATE contacts SET optin=?, optin_at=CASE WHEN ?=1 THEN ? ELSE optin_at END,"
                      " updated_at=? WHERE id=(SELECT contact_id FROM contact_peers WHERE bot_id=? AND peer=?)",
                      (value, value, now, now, bot_id, peer))
    except Exception:
        log.exception("contact optin sync failed bot=%s", bot_id)


# ---- الحقول المخصّصة ----
def _field_row(r):
    d = dict(r)
    d["options"] = json.loads(d.pop("options_json") or "[]")
    return d


def list_fields(owner_id, entity="contact", active_only=False):
    q = "SELECT * FROM contact_fields WHERE owner_id=? AND entity=?"
    if active_only:
        q += " AND active=1"
    with get_conn() as c:
        return [_field_row(r) for r in c.execute(q + " ORDER BY position, id", (owner_id, entity))]


def fields_map(owner_id, entity="contact", active_only=True):
    return {f["key"]: f for f in list_fields(owner_id, entity, active_only)}


def save_field(owner_id, entity, d, field_id=None):
    """d نظيف من crm.clean_field_def ⇒ (المعرّف, None) أو (None, رمز). المفتاح والنوع ثابتان
    بعد الإنشاء: القيم المخزّنة والشرائح والمتغيّرات مبنية عليهما."""
    now = int(time.time())
    with get_conn() as c:
        if field_id:
            n = c.execute("UPDATE contact_fields SET label=?, options_json=?, active=?, required=?"
                          " WHERE id=? AND owner_id=? AND entity=?",
                          (d["label"], CRM.dumps(d["options"]), d["active"], d["required"],
                           field_id, owner_id, entity)).rowcount
            return (field_id, None) if n else (None, "not_found")
        cnt = c.execute("SELECT COUNT(*) FROM contact_fields WHERE owner_id=? AND entity=?",
                        (owner_id, entity)).fetchone()[0]
        if cnt >= CRM.MAX_FIELDS:
            return None, "limit"
        try:
            return c.execute("INSERT INTO contact_fields(owner_id,entity,key,label,type,options_json,"
                             "active,required,position,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                             (owner_id, entity, d["key"], d["label"], d["type"], CRM.dumps(d["options"]),
                              d["active"], d["required"], cnt, now)).lastrowid, None
        except sqlite3.IntegrityError:
            return None, "key_taken"


def delete_field(owner_id, field_id):
    """يحذف التعريف ويمسح قيمه من كل الجهات (أو الشركات) — لا بيانات يتيمة."""
    with get_conn() as c:
        r = c.execute("SELECT entity, key FROM contact_fields WHERE id=? AND owner_id=?",
                      (field_id, owner_id)).fetchone()
        if not r:
            return False
        path = '$."' + r["key"] + '"'
        if r["entity"] == "company":
            c.execute("UPDATE companies SET fields_json=json_remove(fields_json, ?) WHERE owner_id=?",
                      (path, owner_id))
        else:
            c.execute("UPDATE contacts SET fields_json=json_remove(fields_json, ?) WHERE owner_id=?",
                      (path, owner_id))
        c.execute("DELETE FROM contact_fields WHERE id=?", (field_id,))
        return True


def reorder_fields(owner_id, entity, ids):
    with get_conn() as c:
        for pos, fid in enumerate(ids):
            c.execute("UPDATE contact_fields SET position=? WHERE id=? AND owner_id=? AND entity=?",
                      (pos, int(fid), owner_id, entity))


# ---- الوسوم ----
TAG_COLORS = ("cyan", "teal", "violet", "amber", "rose", "sky", "lime", "slate")


def _tag_name(name):
    return re.sub(r"\s+", " ", (name or "").strip())[:50]


def list_tags(owner_id):
    with get_conn() as c:
        return [dict(r) for r in c.execute(
            "SELECT t.id, t.name, t.color, t.created_at, COUNT(ct.contact_id) AS contacts"
            " FROM tags t LEFT JOIN contact_tags ct ON ct.tag_id=t.id WHERE t.owner_id=?"
            " GROUP BY t.id ORDER BY t.name COLLATE NOCASE", (owner_id,))]


def _tag_id(c, owner_id, name):
    name = _tag_name(name)
    if not name:
        return None
    r = c.execute("SELECT id FROM tags WHERE owner_id=? AND name=? COLLATE NOCASE", (owner_id, name)).fetchone()
    if r:
        return r[0]
    return c.execute("INSERT INTO tags(owner_id,name,created_at) VALUES(?,?,?)",
                     (owner_id, name, int(time.time()))).lastrowid


def save_tag(owner_id, name, color="cyan", tag_id=None):
    color = color if color in TAG_COLORS else "cyan"
    name = _tag_name(name)
    if not name:
        return None, "name"
    with get_conn() as c:
        try:
            if tag_id:
                n = c.execute("UPDATE tags SET name=?, color=? WHERE id=? AND owner_id=?",
                              (name, color, tag_id, owner_id)).rowcount
                return (tag_id, None) if n else (None, "not_found")
            return c.execute("INSERT INTO tags(owner_id,name,color,created_at) VALUES(?,?,?,?)",
                             (owner_id, name, color, int(time.time()))).lastrowid, None
        except sqlite3.IntegrityError:
            return None, "taken"


def delete_tag(owner_id, tag_id):
    with get_conn() as c:
        return c.execute("DELETE FROM tags WHERE id=? AND owner_id=?", (tag_id, owner_id)).rowcount > 0


def _owned_ids(c, table, owner_id, ids):
    """من قائمة وصلت من المتصفح: المعرّفات التي يملكها الحساب فعلاً (الجدول اسم ثابت من الكود)."""
    assert table in ("contacts", "tags", "companies")
    try:
        ids = [int(i) for i in ids][:5000]
    except (TypeError, ValueError):
        return []
    out = []
    for i in range(0, len(ids), 500):
        chunk = ids[i:i + 500]
        out += [r[0] for r in c.execute(
            f"SELECT id FROM {table} WHERE owner_id=? AND id IN ({','.join('?' * len(chunk))})",
            (owner_id, *chunk))]
    return out


def tag_contacts(owner_id, contact_ids, tag_ids, add=True):
    """وسم أو إزالة وسم جماعي. الملكية تُفحص للجهات وللوسوم معاً."""
    now = int(time.time())
    with get_conn() as c:
        cids = _owned_ids(c, "contacts", owner_id, contact_ids)
        tids = _owned_ids(c, "tags", owner_id, tag_ids)
        for cid in cids:
            for tid in tids:
                if add:
                    c.execute("INSERT OR IGNORE INTO contact_tags(contact_id,tag_id,created_at) VALUES(?,?,?)",
                              (cid, tid, now))
                else:
                    c.execute("DELETE FROM contact_tags WHERE contact_id=? AND tag_id=?", (cid, tid))
            if tids:
                c.execute("UPDATE contacts SET updated_at=? WHERE id=?", (now, cid))
        return len(cids) if tids else 0


# ---- الشركات ----
def _like(s):
    return str(s).replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def list_companies(owner_id, q=""):
    sql = ("SELECT co.*, (SELECT COUNT(*) FROM contacts WHERE company_id=co.id) AS contacts"
           " FROM companies co WHERE co.owner_id=?")
    args = [owner_id]
    if q:
        sql += " AND co.name LIKE ? ESCAPE '\\'"
        args.append("%" + _like(q) + "%")
    with get_conn() as c:
        out = []
        for r in c.execute(sql + " ORDER BY co.name COLLATE NOCASE LIMIT 2000", args):
            d = dict(r); d["fields"] = json.loads(d.pop("fields_json") or "{}"); out.append(d)
        return out


def save_company(owner_id, name, fields=None, company_id=None):
    name = (name or "").strip()[:120]
    if not name:
        return None, "name"
    now = int(time.time())
    with get_conn() as c:
        try:
            if company_id:
                cur = c.execute("SELECT fields_json FROM companies WHERE id=? AND owner_id=?",
                                (company_id, owner_id)).fetchone()
                if not cur:
                    return None, "not_found"
                merged = json.loads(cur[0] or "{}")
                for k, v in (fields or {}).items():
                    if v is None:
                        merged.pop(k, None)
                    else:
                        merged[k] = v
                c.execute("UPDATE companies SET name=?, fields_json=?, updated_at=? WHERE id=?",
                          (name, CRM.dumps(merged), now, company_id))
                return company_id, None
            clean = {k: v for k, v in (fields or {}).items() if v is not None}
            return c.execute("INSERT INTO companies(owner_id,name,fields_json,created_at,updated_at)"
                             " VALUES(?,?,?,?,?)", (owner_id, name, CRM.dumps(clean), now, now)).lastrowid, None
        except sqlite3.IntegrityError:
            return None, "taken"


def delete_company(owner_id, company_id):
    with get_conn() as c:
        return c.execute("DELETE FROM companies WHERE id=? AND owner_id=?", (company_id, owner_id)).rowcount > 0


def company_owned(owner_id, company_id):
    with get_conn() as c:
        return c.execute("SELECT 1 FROM companies WHERE id=? AND owner_id=?", (company_id, owner_id)).fetchone() is not None


def _company_id(c, owner_id, name):
    name = (name or "").strip()[:120]
    if not name:
        return None
    r = c.execute("SELECT id FROM companies WHERE owner_id=? AND name=? COLLATE NOCASE", (owner_id, name)).fetchone()
    if r:
        return r[0]
    now = int(time.time())
    return c.execute("INSERT INTO companies(owner_id,name,created_at,updated_at) VALUES(?,?,?,?)",
                     (owner_id, name, now, now)).lastrowid


# ---- الشرائح: قواعد منظَّفة (crm.clean_rules) ⇒ WHERE بمعاملات ----
_SYS_COLS = {"name": "c.name", "phone": "c.phone", "email": "c.email", "optin": "c.optin",
             "created_at": "c.created_at", "updated_at": "c.updated_at",
             "last_seen_at": "c.last_seen_at", "assignee": "c.assignee_id",
             "company": "c.company_id", "source": "c.source"}
_JSON_COL = "json_extract(c.fields_json, ?)"


def segment_where(rules, fields):
    """(جملة WHERE، المعاملات) من قواعد **منظَّفة**. أسماء الأعمدة من `_SYS_COLS` ومسار JSON
    معامل — لا شيء من المستخدم يدخل نص الاستعلام."""
    parts, args = [], []
    for r in rules:
        f, op, v = r["field"], r["op"], r["value"]
        if f == "tags":
            ph = ",".join("?" * len(v))
            if op == "has_any":
                parts.append(f"EXISTS(SELECT 1 FROM contact_tags x WHERE x.contact_id=c.id AND x.tag_id IN ({ph}))")
                args += v
            elif op == "has_none":
                parts.append(f"NOT EXISTS(SELECT 1 FROM contact_tags x WHERE x.contact_id=c.id AND x.tag_id IN ({ph}))")
                args += v
            else:
                parts.append(f"(SELECT COUNT(DISTINCT x.tag_id) FROM contact_tags x WHERE x.contact_id=c.id"
                             f" AND x.tag_id IN ({ph}))=?")
                args += v + [len(set(v))]
            continue
        if f.startswith("f:"):
            kind, path = fields[f[2:]]["type"], '$."' + f[2:] + '"'
            col, cargs = _JSON_COL, [path]
        else:
            kind, path = CRM.SYSTEM_FIELDS[f], None
            col, cargs = _SYS_COLS[f], []

        def add(sql, *vals):
            # كل ظهور للعمود في الجملة يحتاج معاملاته (مسار JSON) من جديد، بالترتيب
            parts.append(sql.replace("{c}", col))
            args.extend(cargs * sql.count("{c}"))
            args.extend(vals)

        if op == "empty":
            add("{c} IS NULL" if kind == "ts" else "({c} IS NULL OR {c}='' OR {c}='[]')")
        elif op == "not_empty":
            add("{c} IS NOT NULL" if kind == "ts" else "({c} IS NOT NULL AND {c}!='' AND {c}!='[]')")
        elif kind in ("text", "multi_text", "select", "source"):
            if op == "is":
                add("lower(COALESCE({c},''))=lower(?)", v)
            elif op == "is_not":
                add("lower(COALESCE({c},''))!=lower(?)", v)
            elif op == "contains":
                add("COALESCE({c},'') LIKE ? ESCAPE '\\'", "%" + _like(v) + "%")
            elif op == "not_contains":
                add("COALESCE({c},'') NOT LIKE ? ESCAPE '\\'", "%" + _like(v) + "%")
            elif op == "starts_with":
                add("COALESCE({c},'') LIKE ? ESCAPE '\\'", _like(v) + "%")
            elif op == "any_of":
                add("{c} IN (" + ",".join("?" * len(v)) + ")", *v)
        elif kind == "number":
            add("CAST({c} AS REAL)" + {"eq": "=", "neq": "!=", "gt": ">", "lt": "<"}[op] + "?", v)
        elif kind == "switch":
            add("COALESCE({c},0)=?", 1 if v else 0)
        elif kind in ("user", "company"):
            add("{c}=?" if op == "is" else "COALESCE({c},0)!=?", v)
        elif kind == "multi_select":
            ph = ",".join("?" * len(v))
            each = "SELECT value FROM json_each(c.fields_json, ?)"
            if op == "has_any":
                parts.append(f"EXISTS({each} WHERE value IN ({ph}))"); args += [path] + v
            elif op == "has_none":
                parts.append(f"NOT EXISTS({each} WHERE value IN ({ph}))"); args += [path] + v
            else:
                parts.append(f"(SELECT COUNT(DISTINCT value) FROM json_each(c.fields_json, ?)"
                             f" WHERE value IN ({ph}))=?")
                args += [path] + v + [len(set(v))]
        elif kind == "ts":
            if op == "last_days":
                add("{c}>=?", int(time.time()) - v * 86400)
            else:
                a, b = CRM.day_bounds(v)
                if op == "on":
                    add("({c}>=? AND {c}<?)", a, b)
                elif op == "before":
                    add("{c}<?", a)
                else:
                    add("{c}>=?", b)
        elif kind == "date":
            if op == "last_days":
                add("{c}>=?", (_dt.now(CRM.TZ) - _td(days=v)).strftime("%Y-%m-%d"))
            else:
                add("{c}" + {"on": "=", "before": "<", "after": ">"}[op] + "?", v)
    return (" AND ".join(parts) or "1=1"), args


# ---- جهات الاتصال ----
def _contact_row(r):
    d = dict(r)
    d["fields"] = json.loads(d.pop("fields_json") or "{}")
    d["tags"] = [int(x) for x in (d.pop("tag_ids") or "").split(",") if x]
    return d


_CONTACT_SELECT = ("SELECT c.*, co.name AS company_name, u.username AS assignee_name,"
                   " (SELECT group_concat(tag_id) FROM contact_tags WHERE contact_id=c.id) AS tag_ids"
                   " FROM contacts c LEFT JOIN companies co ON co.id=c.company_id"
                   " LEFT JOIN users u ON u.id=c.assignee_id")
CONTACT_SORTS = {"new": "c.id DESC", "old": "c.id ASC", "name": "c.name COLLATE NOCASE, c.id",
                 "seen": "COALESCE(c.last_seen_at,0) DESC, c.id DESC",
                 "updated": "c.updated_at DESC, c.id DESC"}


def query_contacts(owner_id, rules=(), fields=None, q="", limit=20, offset=0, sort="new"):
    """(الصفوف، العدد الكلّي). `rules` منظَّفة مسبقاً. `limit=None` = الكل (للتصدير)."""
    where, args = segment_where(list(rules), fields or {})
    sql = f" WHERE c.owner_id=? AND ({where})"
    args = [owner_id] + args
    q = (q or "").strip()[:80]
    if q:
        like = "%" + _like(q) + "%"
        sql += " AND (c.name LIKE ? ESCAPE '\\' OR c.phone LIKE ? ESCAPE '\\' OR c.email LIKE ? ESCAPE '\\')"
        args += [like, like, like]
    with get_conn() as c:
        total = c.execute("SELECT COUNT(*) FROM contacts c" + sql, args).fetchone()[0]
        tail, targs = " ORDER BY " + CONTACT_SORTS.get(sort, CONTACT_SORTS["new"]), list(args)
        if limit is not None:
            tail += " LIMIT ? OFFSET ?"
            targs += [int(limit), int(offset)]
        rows = [_contact_row(r) for r in c.execute(_CONTACT_SELECT + sql + tail, targs)]
    return rows, total


def count_contacts(owner_id, rules=(), fields=None):
    where, args = segment_where(list(rules), fields or {})
    with get_conn() as c:
        return c.execute(f"SELECT COUNT(*) FROM contacts c WHERE c.owner_id=? AND ({where})",
                         [owner_id] + args).fetchone()[0]


def get_contact(owner_id, contact_id):
    with get_conn() as c:
        r = c.execute(_CONTACT_SELECT + " WHERE c.id=? AND c.owner_id=?", (contact_id, owner_id)).fetchone()
    return _contact_row(r) if r else None


def save_contact(owner_id, d, contact_id=None, by=None):
    """d منظَّف في app ⇒ (المعرّف, None) أو (None, رمز). الحقول المخصّصة **تُدمج** مع المخزّن
    (قيمة None تحذف مفتاحها)، و`tags` لو وُجد يستبدل وسوم الجهة كلها."""
    now = int(time.time())
    with get_conn() as c:
        cur = None
        if contact_id:
            cur = c.execute("SELECT fields_json, optin FROM contacts WHERE id=? AND owner_id=?",
                            (contact_id, owner_id)).fetchone()
            if not cur:
                return None, "not_found"
        fields = json.loads(cur["fields_json"]) if cur else {}
        for k, v in (d.get("fields") or {}).items():
            if v is None:
                fields.pop(k, None)
            else:
                fields[k] = v
        optin = d.get("optin")
        newly = optin == 1 and (cur is None or cur["optin"] != 1)
        try:
            if contact_id:
                c.execute("UPDATE contacts SET name=?, phone=?, email=?, company_id=?, assignee_id=?, optin=?,"
                          " fields_json=?, updated_at=?, optin_at=CASE WHEN ? THEN ? ELSE optin_at END"
                          " WHERE id=? AND owner_id=?",
                          ((d.get("name") or "")[:120], d.get("phone"), d.get("email"), d.get("company_id"),
                           d.get("assignee_id"), optin, CRM.dumps(fields), now, 1 if newly else 0, now,
                           contact_id, owner_id))
                cid = contact_id
            else:
                cid = c.execute("INSERT INTO contacts(owner_id,name,phone,email,company_id,assignee_id,"
                                "optin,optin_at,fields_json,source,created_by,created_at,updated_at)"
                                " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                                (owner_id, (d.get("name") or "")[:120], d.get("phone"), d.get("email"),
                                 d.get("company_id"), d.get("assignee_id"), optin, now if newly else None,
                                 CRM.dumps(fields), d.get("source") or "manual", by, now, now)).lastrowid
        except sqlite3.IntegrityError:
            return None, "phone_taken"
        if "tags" in d:
            tids = _owned_ids(c, "tags", owner_id, d["tags"])
            c.execute("DELETE FROM contact_tags WHERE contact_id=?", (cid,))
            for tid in tids:
                c.execute("INSERT OR IGNORE INTO contact_tags(contact_id,tag_id,created_at) VALUES(?,?,?)",
                          (cid, tid, now))
        return cid, None


def delete_contacts(owner_id, ids):
    with get_conn() as c:
        cids = _owned_ids(c, "contacts", owner_id, ids)
        for i in range(0, len(cids), 500):
            chunk = cids[i:i + 500]
            c.execute(f"DELETE FROM contacts WHERE id IN ({','.join('?' * len(chunk))})", chunk)
        return len(cids)


def assign_contacts(owner_id, ids, assignee_id):
    """مسؤول الجهة لجهات عدّة. `assignee_id` يُتحقَّق منه في app (عضو في الحساب) أو None."""
    now = int(time.time())
    with get_conn() as c:
        cids = _owned_ids(c, "contacts", owner_id, ids)
        for cid in cids:
            c.execute("UPDATE contacts SET assignee_id=?, updated_at=? WHERE id=?", (assignee_id, now, cid))
        return len(cids)


def import_contacts(owner_id, records, update_existing=True, by=None):
    """سجلات crm.build_records في معاملة واحدة. المطابقة بالهاتف: القائم يُحدَّث (الحقول تُدمج،
    الوسوم تُضاف ولا تُمسح، القيمة الفارغة لا تمحو القائمة) أو يُتخطّى؛ الجديد يُنشأ."""
    now = int(time.time())
    stats = {"created": 0, "updated": 0, "skipped": 0}
    with get_conn() as c:
        tag_cache, company_cache = {}, {}
        for rec in records:
            row = c.execute("SELECT id, fields_json, name, email, optin FROM contacts"
                            " WHERE owner_id=? AND phone=?", (owner_id, rec["phone"])).fetchone()
            if row and not update_existing:
                stats["skipped"] += 1
                continue
            company_id = None
            if rec.get("company"):
                ck = rec["company"].lower()
                if ck not in company_cache:
                    company_cache[ck] = _company_id(c, owner_id, rec["company"])
                company_id = company_cache[ck]
            optin = rec.get("optin")
            if row:
                fields = json.loads(row["fields_json"] or "{}")
                fields.update(rec["fields"])
                keep = row["optin"] if optin is None else optin
                c.execute("UPDATE contacts SET name=?, email=?, optin=?, fields_json=?,"
                          " company_id=COALESCE(?, company_id), updated_at=?,"
                          " optin_at=CASE WHEN ?=1 AND COALESCE(optin,0)!=1 THEN ? ELSE optin_at END"
                          " WHERE id=?",
                          (rec.get("name") or row["name"], rec.get("email") or row["email"], keep,
                           CRM.dumps(fields), company_id, now, keep, now, row["id"]))
                cid = row["id"]
                stats["updated"] += 1
            else:
                cid = c.execute("INSERT INTO contacts(owner_id,name,phone,email,company_id,optin,optin_at,"
                                "fields_json,source,created_by,created_at,updated_at)"
                                " VALUES(?,?,?,?,?,?,?,?,'import',?,?,?)",
                                (owner_id, rec.get("name") or "", rec["phone"], rec.get("email"), company_id,
                                 optin, now if optin == 1 else None, CRM.dumps(rec["fields"]), by, now, now)).lastrowid
                stats["created"] += 1
            for name in rec.get("tags") or []:
                k = _tag_name(name).lower()
                if k and k not in tag_cache:
                    tag_cache[k] = _tag_id(c, owner_id, name)
                if k and tag_cache.get(k):
                    c.execute("INSERT OR IGNORE INTO contact_tags(contact_id,tag_id,created_at) VALUES(?,?,?)",
                              (cid, tag_cache[k], now))
    return stats


# ---- الشرائح المحفوظة ----
def _segment_row(r):
    d = dict(r); d["rules"] = json.loads(d.pop("rules_json") or "[]")
    return d


def list_segments(owner_id):
    with get_conn() as c:
        return [_segment_row(r) for r in c.execute(
            "SELECT * FROM segments WHERE owner_id=? ORDER BY name COLLATE NOCASE", (owner_id,))]


def get_segment(owner_id, seg_id):
    with get_conn() as c:
        r = c.execute("SELECT * FROM segments WHERE id=? AND owner_id=?", (seg_id, owner_id)).fetchone()
    return _segment_row(r) if r else None


def save_segment(owner_id, name, rules, seg_id=None, by=None):
    name = (name or "").strip()[:80]
    if not name:
        return None, "name"
    now = int(time.time())
    with get_conn() as c:
        if seg_id:
            n = c.execute("UPDATE segments SET name=?, rules_json=?, updated_at=? WHERE id=? AND owner_id=?",
                          (name, CRM.dumps(rules), now, seg_id, owner_id)).rowcount
            return (seg_id, None) if n else (None, "not_found")
        return c.execute("INSERT INTO segments(owner_id,name,rules_json,created_by,created_at,updated_at)"
                         " VALUES(?,?,?,?,?,?)", (owner_id, name, CRM.dumps(rules), by, now, now)).lastrowid, None


def delete_segment(owner_id, seg_id):
    with get_conn() as c:
        return c.execute("DELETE FROM segments WHERE id=? AND owner_id=?", (seg_id, owner_id)).rowcount > 0


# ─────────────────────────────  حالة رسائل واتساب الصادرة  ─────────────────────────────
# المرحلة 2 من docs/ENTERPRISE_PLAN.md — المنطق في msg_status.py. صفّ لكل رسالة صادرة
# بمعرّف Meta (`wamid`)، والويبهوك يرفع حالتها. الترتيب **لا يتراجع**: Meta قد ترسل «read»
# قبل «delivered»، فالحالة ترتفع فقط (sent<delivered<read)، و«failed» لا يمحو «read».
import msg_status as MS


def _msg_status_tables(c):
    c.executescript("""
        CREATE TABLE IF NOT EXISTS wa_messages(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            wamid TEXT UNIQUE,                  -- NULL لرسالة رفضتها Meta عند الإرسال (لا معرّف)
            bot_id INTEGER,
            phone_id TEXT,
            peer TEXT,
            kind TEXT,                          -- text | template | image | interactive | …
            campaign_id INTEGER,                -- من msg_status.SEND_CTX عند الإرسال ضمن حملة
            status TEXT NOT NULL DEFAULT 'sent',
            error_code INTEGER,
            error_title TEXT,
            category TEXT,                      -- فئة التسعير من Meta (marketing · utility · service …)
            billable INTEGER,
            created_at INTEGER NOT NULL,
            delivered_at INTEGER, read_at INTEGER, failed_at INTEGER,
            FOREIGN KEY(bot_id) REFERENCES bots(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS ix_wa_msgs_bot ON wa_messages(bot_id, created_at);
        CREATE INDEX IF NOT EXISTS ix_wa_msgs_campaign ON wa_messages(campaign_id) WHERE campaign_id IS NOT NULL;
    """)


def record_wa_send(bot_id, phone_id, peer, kind, wamid=None, error_code=None, error_title="", campaign_id=None):
    """تسجيل رسالة صادرة. لا يرمي أبداً — فشل السجل لا يجوز أن يُفشل الإرسال نفسه."""
    now = int(time.time())
    try:
        code = int(error_code) if error_code is not None else None
    except (TypeError, ValueError):
        code = None
    try:
        with get_conn() as c:
            c.execute("INSERT OR IGNORE INTO wa_messages(wamid,bot_id,phone_id,peer,kind,campaign_id,status,"
                      "error_code,error_title,created_at,failed_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                      (wamid, bot_id, str(phone_id or "")[:40], (peer or "")[:160], (kind or "")[:30], campaign_id,
                       "sent" if wamid else "failed", code, (error_title or "")[:200] or None, now,
                       None if wamid else now))
    except Exception:
        log.exception("record_wa_send failed bot=%s", bot_id)


def apply_wa_statuses(updates):
    """تحديثات من msg_status.parse_statuses. يعيد عدد الصفوف التي تغيّرت. معرّف لا نعرفه (رسالة
    أرسلها الشريك مباشرةً عبر /api/v1، أو من قبل هذه الميزة) يُتجاهل بصمت."""
    n = 0
    with get_conn() as c:
        for u in updates:
            st, ts = u["status"], u["ts"]
            if st == "failed":
                try:
                    code = int(u["code"]) if u.get("code") is not None else None
                except (TypeError, ValueError):
                    code = None
                cur = c.execute("UPDATE wa_messages SET status='failed', failed_at=?, error_code=?, error_title=?,"
                                " category=COALESCE(?,category) WHERE wamid=? AND status!='read'",
                                (ts, code, u.get("title") or None, u.get("category"), u["wamid"]))
            else:
                rank = MS.RANK[st]
                # «read» يعني «delivered» ضمناً: وقت التسليم يُملأ إن لم يصل حدثه بعد
                cur = c.execute(
                    "UPDATE wa_messages SET"
                    " status=CASE WHEN status='failed' THEN status"
                    "             WHEN (CASE status WHEN 'read' THEN 3 WHEN 'delivered' THEN 2 ELSE 1 END) < ? THEN ?"
                    "             ELSE status END,"
                    " delivered_at=CASE WHEN ?>=2 THEN COALESCE(delivered_at, ?) ELSE delivered_at END,"
                    " read_at=CASE WHEN ?=3 THEN COALESCE(read_at, ?) ELSE read_at END,"
                    " category=COALESCE(?,category), billable=COALESCE(?,billable)"
                    " WHERE wamid=?",
                    (rank, st, rank, ts, rank, ts, u.get("category"), u.get("billable"), u["wamid"]))
            n += cur.rowcount
    return n


def wa_delivery_stats(bot_ids, since=0, campaign_id=None):
    """{total, sent, delivered, read, failed, failures: {فئة: عدد}} لبوتات حساب أو حملة.
    «delivered» تشمل ما قُرئ (القراءة تسليم ضمناً) — كقراءة المنافس للأرقام."""
    if not bot_ids and campaign_id is None:
        return {"total": 0, "sent": 0, "delivered": 0, "read": 0, "failed": 0, "failures": {}}
    where, args = ["created_at>=?"], [since]
    if campaign_id is not None:
        where.append("campaign_id=?"); args.append(campaign_id)
    if bot_ids:
        where.append(f"bot_id IN ({','.join('?' * len(bot_ids))})"); args += list(bot_ids)
    w = " AND ".join(where)
    with get_conn() as c:
        r = c.execute("SELECT COUNT(*) total,"
                      " SUM(status IN ('sent','delivered','read')) sent,"
                      " SUM(status IN ('delivered','read')) delivered,"
                      " SUM(status='read') read, SUM(status='failed') failed"
                      f" FROM wa_messages WHERE {w}", args).fetchone()
        fails = {}
        for row in c.execute(f"SELECT error_code, COUNT(*) n FROM wa_messages WHERE {w} AND status='failed'"
                             " GROUP BY error_code", args):
            b = MS.bucket(row["error_code"])
            fails[b] = fails.get(b, 0) + row["n"]
    out = {k: int(r[k] or 0) for k in ("total", "sent", "delivered", "read", "failed")}
    out["failures"] = fails
    return out


def wa_failed_messages(bot_ids, limit=100):
    """آخر الرسائل الفاشلة (للتقرير «WhatsApp Failed Messages»)."""
    if not bot_ids:
        return []
    with get_conn() as c:
        rows = c.execute(f"SELECT id, bot_id, peer, kind, error_code, error_title, created_at, failed_at"
                         f" FROM wa_messages WHERE status='failed' AND bot_id IN ({','.join('?' * len(bot_ids))})"
                         " ORDER BY id DESC LIMIT ?", (*bot_ids, int(limit))).fetchall()
    out = []
    for r in rows:
        d = dict(r); d["bucket"] = MS.bucket(d["error_code"]); out.append(d)
    return out


def purge_old_wa_messages(days=365):
    with get_conn() as c:
        return c.execute("DELETE FROM wa_messages WHERE created_at<?",
                         (int(time.time()) - days * 86400,)).rowcount


# ─────────────────────────────  البث 2.0: الحملات  ─────────────────────────────
# المرحلة 3 — المنطق والمال في broadcasts.py. `campaign_recipients` لقطة ثابتة للجمهور عند
# الإطلاق: هي القائمة التي حُسبت عليها التكلفة وهي نفسها المُرسَل إليها (§22)، وتربط كل مستلم
# بـ`wamid` آخر محاولة فتُقرأ حالته من `wa_messages`.
_CAMP_JSON = ("header_json", "vars_json", "audience_json")


def _campaign_tables(c):
    c.executescript("""
        CREATE TABLE IF NOT EXISTS campaigns(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            owner_id INTEGER NOT NULL,
            bot_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            template TEXT NOT NULL,
            lang TEXT NOT NULL,
            category TEXT,
            header_json TEXT NOT NULL DEFAULT '{}',
            vars_json TEXT NOT NULL DEFAULT '[]',
            audience_json TEXT NOT NULL DEFAULT '{}',
            policy_optin INTEGER NOT NULL DEFAULT 1,
            status TEXT NOT NULL DEFAULT 'draft',  -- draft|scheduled|running|done|cancelled|failed
            error TEXT,
            scheduled_at INTEGER, started_at INTEGER, finished_at INTEGER,
            total INTEGER NOT NULL DEFAULT 0,
            charged INTEGER NOT NULL DEFAULT 0,    -- قروش: المخصوم الصافي (بعد الردّ) لكل الجولات
            refunded INTEGER NOT NULL DEFAULT 0,
            price INTEGER NOT NULL DEFAULT 0,
            retry_until INTEGER, next_retry_at INTEGER,
            retries INTEGER NOT NULL DEFAULT 0,
            assign_to INTEGER,
            created_by INTEGER,
            created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL,
            FOREIGN KEY(owner_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY(bot_id) REFERENCES bots(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS ix_campaigns_owner ON campaigns(owner_id, id);
        CREATE INDEX IF NOT EXISTS ix_campaigns_due ON campaigns(status, scheduled_at);
        CREATE TABLE IF NOT EXISTS campaign_recipients(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            campaign_id INTEGER NOT NULL,
            contact_id INTEGER,
            peer TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',  -- pending|accepted|failed (قبول Meta عند الإرسال)
            wamid TEXT,
            error_code INTEGER,
            attempts INTEGER NOT NULL DEFAULT 0,
            updated_at INTEGER,
            UNIQUE(campaign_id, peer),
            FOREIGN KEY(campaign_id) REFERENCES campaigns(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS ix_camp_rcpt_wamid ON campaign_recipients(wamid);
        -- ما لا تحفظه Meta من قوالبنا ونحتاجه عند الإرسال (دبّوس ترويسة LOCATION) — المرحلة 4
        CREATE TABLE IF NOT EXISTS template_meta(
            bot_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            lang TEXT NOT NULL,
            data_json TEXT NOT NULL DEFAULT '{}',
            created_by INTEGER,
            created_at INTEGER NOT NULL,
            PRIMARY KEY(bot_id, name, lang),
            FOREIGN KEY(bot_id) REFERENCES bots(id) ON DELETE CASCADE
        );
    """)
    # المرحلة 4: قيم الإرسال الإضافية (مواصفة القالب، كوبون، عدّاد، بطاقات، موقع). حارس لقواعد
    # أنشأت الجدول في المرحلة 3 قبل العمود.
    cols = {r[1] for r in c.execute("PRAGMA table_info(campaigns)")}
    if "extra_json" not in cols:
        c.execute("ALTER TABLE campaigns ADD COLUMN extra_json TEXT NOT NULL DEFAULT '{}'")


def set_template_meta(bot_id, name, lang, data, by=None):
    with get_conn() as c:
        c.execute("INSERT INTO template_meta(bot_id,name,lang,data_json,created_by,created_at) VALUES(?,?,?,?,?,?)"
                  " ON CONFLICT(bot_id,name,lang) DO UPDATE SET data_json=excluded.data_json",
                  (bot_id, name, lang, json.dumps(data or {}), by, int(time.time())))


def get_template_meta(bot_id, name, lang):
    with get_conn() as c:
        r = c.execute("SELECT data_json FROM template_meta WHERE bot_id=? AND name=? AND lang=?",
                      (bot_id, name, lang)).fetchone()
    return json.loads(r[0]) if r else {}


def delete_template_meta(bot_id, name):
    with get_conn() as c:
        c.execute("DELETE FROM template_meta WHERE bot_id=? AND name=?", (bot_id, name))


def _campaign_row(r):
    d = dict(r)
    d["header"] = json.loads(d.pop("header_json") or "{}")
    d["vars"] = json.loads(d.pop("vars_json") or "[]")
    d["audience"] = json.loads(d.pop("audience_json") or "{}")
    d["extra"] = json.loads(d.pop("extra_json", None) or "{}")
    return d


def create_campaign(owner_id, d, by=None):
    """d منظَّف في app. يعيد المعرّف."""
    now = int(time.time())
    with get_conn() as c:
        return c.execute(
            "INSERT INTO campaigns(owner_id,bot_id,name,template,lang,category,header_json,vars_json,audience_json,"
            "extra_json,policy_optin,status,scheduled_at,retry_until,assign_to,created_by,created_at,updated_at)"
            " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (owner_id, d["bot_id"], d["name"], d["template"], d["lang"], d.get("category"),
             json.dumps(d.get("header") or {}), json.dumps(d.get("vars") or []), json.dumps(d["audience"]),
             json.dumps(d.get("extra") or {}),
             1 if d.get("policy_optin", True) else 0, d.get("status", "draft"), d.get("scheduled_at"),
             d.get("retry_until"), d.get("assign_to"), by, now, now)).lastrowid


def get_campaign(cid, owner_id=None):
    q, args = "SELECT * FROM campaigns WHERE id=?", [cid]
    if owner_id is not None:
        q += " AND owner_id=?"; args.append(owner_id)
    with get_conn() as c:
        r = c.execute(q, args).fetchone()
    return _campaign_row(r) if r else None


_CAMP_COLS = {"status", "error", "category", "total", "charged", "refunded", "price", "started_at",
              "finished_at", "scheduled_at", "retry_until", "next_retry_at", "retries"}


def update_campaign(cid, **kw):
    cols = {k: v for k, v in kw.items() if k in _CAMP_COLS}
    if not cols:
        return
    with get_conn() as c:
        c.execute(f"UPDATE campaigns SET {', '.join(k + '=?' for k in cols)}, updated_at=? WHERE id=?",
                  (*cols.values(), int(time.time()), cid))


def claim_campaign(cid, from_status):
    """ذرّي: يحوّل الحملة إلى running فقط لو ما زالت على حالتها — طلبان لا يطلقانها مرتين."""
    with get_conn() as c:
        return c.execute("UPDATE campaigns SET status='running', updated_at=? WHERE id=? AND status=?",
                         (int(time.time()), cid, from_status)).rowcount == 1


def cancel_campaign(owner_id, cid):
    with get_conn() as c:
        return c.execute("UPDATE campaigns SET status='cancelled', updated_at=? WHERE id=? AND owner_id=?"
                         " AND status IN ('scheduled','draft')", (int(time.time()), cid, owner_id)).rowcount == 1


def stop_campaign_retries(owner_id, cid):
    with get_conn() as c:
        return c.execute("UPDATE campaigns SET retry_until=NULL, next_retry_at=NULL, updated_at=?"
                         " WHERE id=? AND owner_id=?", (int(time.time()), cid, owner_id)).rowcount == 1


def snapshot_recipients(cid, audience):
    now = int(time.time())
    with get_conn() as c:
        c.executemany("INSERT OR IGNORE INTO campaign_recipients(campaign_id,contact_id,peer,updated_at)"
                      " VALUES(?,?,?,?)", [(cid, a.get("contact_id"), a["peer"], now) for a in audience])


def clear_recipients(cid):
    with get_conn() as c:
        c.execute("DELETE FROM campaign_recipients WHERE campaign_id=?", (cid,))


def _items(c, rows):
    """صفوف مستلمين ⇒ عناصر إرسال بجهة الاتصال (لتخصيص المتغيّرات)."""
    ids = [r["contact_id"] for r in rows if r["contact_id"]]
    contacts = {}
    for i in range(0, len(ids), 500):
        chunk = ids[i:i + 500]
        for r in c.execute(f"SELECT id,name,phone,email,fields_json FROM contacts WHERE id IN ({','.join('?' * len(chunk))})",
                           chunk):
            d = dict(r); d["fields"] = json.loads(d.pop("fields_json") or "{}"); contacts[d["id"]] = d
    return [{"rid": r["id"], "peer": r["peer"],
             "contact": contacts.get(r["contact_id"]) or {"name": "", "phone": "", "email": "", "fields": {}}}
            for r in rows]


def campaign_send_items(cid):
    with get_conn() as c:
        rows = c.execute("SELECT id, contact_id, peer FROM campaign_recipients WHERE campaign_id=? ORDER BY id",
                         (cid,)).fetchall()
        return _items(c, rows)


def mark_recipient(rid, wamid=None, error_code=None):
    """نتيجة محاولة إرسال لمستلم: قبلتها Meta (wamid) أو رفضتها فوراً (رمز)."""
    try:
        code = int(error_code) if error_code is not None else None
    except (TypeError, ValueError):
        code = None
    with get_conn() as c:
        c.execute("UPDATE campaign_recipients SET status=?, wamid=COALESCE(?, wamid), error_code=?,"
                  " attempts=attempts+1, updated_at=? WHERE id=?",
                  ("accepted" if wamid else "failed", wamid, None if wamid else code, int(time.time()), rid))


def finish_campaign_round(cid, kept, refunded, attempt):
    """نهاية جولة إرسال: تراكم المال، وموعد الإعادة التالية لو ما زالت نافذتها مفتوحة."""
    import broadcasts as BC
    now = int(time.time())
    with get_conn() as c:
        c.execute("UPDATE campaigns SET status='done', finished_at=?, charged=charged+?, refunded=refunded+?,"
                  " retries=?, next_retry_at=CASE WHEN retry_until IS NOT NULL AND retry_until>? THEN ? ELSE NULL END,"
                  " updated_at=? WHERE id=?",
                  (now, int(kept), int(refunded), attempt, now, now + BC.RETRY_EVERY, now, cid))


def due_campaigns(now):
    with get_conn() as c:
        return [r[0] for r in c.execute("SELECT id FROM campaigns WHERE status='scheduled' AND scheduled_at<=?"
                                        " ORDER BY scheduled_at LIMIT 20", (now,))]


def retry_due_campaigns(now):
    with get_conn() as c:
        return [r[0] for r in c.execute("SELECT id FROM campaigns WHERE status='done' AND retry_until>?"
                                        " AND next_retry_at IS NOT NULL AND next_retry_at<=? LIMIT 20", (now, now))]


def _state_of(rcpt_status, rcpt_code, wa_status, wa_code):
    """حالة المستلم الفعلية ورمز الفشل من سجلّين: قبول Meta عند الإرسال ثم الويبهوك."""
    if rcpt_status == "failed":
        return "failed", rcpt_code
    if wa_status == "failed":
        return "failed", wa_code
    return (wa_status or ("sent" if rcpt_status == "accepted" else "pending")), None


def retryable_items(cid, buckets, max_attempts):
    with get_conn() as c:
        rows = c.execute("SELECT r.id, r.contact_id, r.peer, r.status, r.error_code, r.attempts,"
                         " w.status wa_status, w.error_code wa_code FROM campaign_recipients r"
                         " LEFT JOIN wa_messages w ON w.wamid=r.wamid WHERE r.campaign_id=? AND r.attempts<?",
                         (cid, max_attempts)).fetchall()
        keep = [r for r in rows if _state_of(r["status"], r["error_code"], r["wa_status"], r["wa_code"])[0] == "failed"
                and MS.bucket(_state_of(r["status"], r["error_code"], r["wa_status"], r["wa_code"])[1]) in buckets]
        return _items(c, keep)


def campaign_recipient_states(cid):
    """[{id, contact_id, peer, state, bucket, replied, wamid}] — أساس الإحصاءات وإعادة الاستهداف."""
    with get_conn() as c:
        camp = c.execute("SELECT bot_id, started_at FROM campaigns WHERE id=?", (cid,)).fetchone()
        if not camp:
            return []
        since = camp["started_at"] or 0
        rows = c.execute(
            "SELECT r.id, r.contact_id, r.peer, r.status, r.error_code, r.wamid, w.status wa_status, w.error_code wa_code,"
            " EXISTS(SELECT 1 FROM messages m WHERE m.bot_id=? AND m.peer=r.peer AND m.direction='in'"
            "        AND m.created_at>=?) AS replied"
            " FROM campaign_recipients r LEFT JOIN wa_messages w ON w.wamid=r.wamid WHERE r.campaign_id=?",
            (camp["bot_id"], since, cid)).fetchall()
    out = []
    for r in rows:
        st, code = _state_of(r["status"], r["error_code"], r["wa_status"], r["wa_code"])
        out.append({"id": r["id"], "contact_id": r["contact_id"], "peer": r["peer"], "state": st,
                    "code": code, "bucket": MS.bucket(code) if st == "failed" else None,
                    "replied": bool(r["replied"]) and st != "failed", "wamid": r["wamid"]})
    return out


def campaign_stats(cid):
    """أرقام الحملة كما يعرضها المنافس: كل حالة **تشمل** ما بعدها (القراءة تسليم ضمناً)."""
    rs = campaign_recipient_states(cid)
    s = {"recipients": len(rs), "pending": 0, "sent": 0, "delivered": 0, "read": 0, "replied": 0,
         "delivered_not_replied": 0, "failed": 0, "failures": {}}
    for r in rs:
        st = r["state"]
        if st == "failed":
            s["failed"] += 1
            s["failures"][r["bucket"]] = s["failures"].get(r["bucket"], 0) + 1
            continue
        if st == "pending":
            s["pending"] += 1
            continue
        s["sent"] += 1
        if st in ("delivered", "read"):
            s["delivered"] += 1
            if not r["replied"]:
                s["delivered_not_replied"] += 1
        if st == "read":
            s["read"] += 1
        if r["replied"]:
            s["replied"] += 1
    return s


CAMPAIGN_STATES = ("draft", "scheduled", "running", "done", "cancelled", "failed")


def list_campaigns(owner_id, limit=50, offset=0, status=None):
    """`status` تصفية اختيارية — من قائمة ثابتة فقط (غيرها يُتجاهل = الكل)."""
    where, args = "cp.owner_id=?", [owner_id]
    if status in CAMPAIGN_STATES:
        where += " AND cp.status=?"
        args.append(status)
    with get_conn() as c:
        total = c.execute(f"SELECT COUNT(*) FROM campaigns cp WHERE {where}", args).fetchone()[0]
        rows = [_campaign_row(r) for r in c.execute(
            "SELECT cp.*, b.name AS bot_name, u.username AS creator FROM campaigns cp"
            " LEFT JOIN bots b ON b.id=cp.bot_id LEFT JOIN users u ON u.id=cp.created_by"
            f" WHERE {where} ORDER BY cp.id DESC LIMIT ? OFFSET ?", args + [int(limit), int(offset)])]
    return rows, total


def campaign_status_counts(owner_id):
    """عدد الحملات لكل حالة ⇒ {status: n} — لعدّادات تبويبات صفحة البث."""
    with get_conn() as c:
        return {r[0]: r[1] for r in c.execute(
            "SELECT status, COUNT(*) FROM campaigns WHERE owner_id=? GROUP BY status", (owner_id,))}


def _contact_peer(row):
    """جهة اتصال ⇒ peer واتساب: الرقم أولاً، وإلا اسم المستخدم (BSUID)."""
    if row["phone"]:
        return "wa:" + row["phone"].lstrip("+")
    if row["bsuid"]:
        return "wa:" + row["bsuid"]
    return None


def campaign_audience(owner_id, bot_id, spec, require_optin=True):
    """الجمهور الفعلي لحملة ⇒ [{contact_id, peer}] بلا تكرار. **STOP مستبعد دائماً** (§55):
    جهة موافقتها 0، أو peer طلب الإيقاف على هذا البوت. `require_optin` (سياسة واتساب للتسويق):
    الموافقون صراحةً وحدهم — جهة موافقتها 1 أو مشترك وافق من داخل المحادثة."""
    kind = (spec or {}).get("type")
    fields = fields_map(owner_id, "contact", active_only=False)
    with get_conn() as c:
        stopped = {r[0] for r in c.execute("SELECT peer FROM bot_users WHERE bot_id=? AND opted_out=1", (bot_id,))}
        opted = {r[0] for r in c.execute("SELECT peer FROM bot_users WHERE bot_id=? AND optin_at IS NOT NULL"
                                         " AND opted_out=0", (bot_id,))}
    out, seen = [], set()

    def add(contact_id, peer, optin):
        if not peer or peer in seen or peer in stopped or optin == 0:
            return
        if require_optin and optin != 1 and peer not in opted:
            return
        seen.add(peer)
        out.append({"contact_id": contact_id, "peer": peer})

    if kind in ("segment", "all"):
        rules = []
        if kind == "segment":
            seg = get_segment(owner_id, int(spec.get("id") or 0))
            if not seg:
                return []
            rules, err = CRM.clean_rules(seg["rules"], fields)
            if err:
                return []
        rows, _ = query_contacts(owner_id, rules, fields, limit=None, sort="old")
        for r in rows:
            add(r["id"], _contact_peer(r), r["optin"])
    elif kind == "subscribers":
        with get_conn() as c:
            for r in c.execute("SELECT bu.peer, cp.contact_id, ct.optin FROM bot_users bu"
                               " LEFT JOIN contact_peers cp ON cp.bot_id=bu.bot_id AND cp.peer=bu.peer"
                               " LEFT JOIN contacts ct ON ct.id=cp.contact_id"
                               " WHERE bu.bot_id=? AND bu.peer LIKE 'wa:%' ORDER BY bu.id", (bot_id,)):
                add(r["contact_id"], r["peer"], r["optin"])
    elif kind == "numbers":
        # إرسال تجريبي لقالب (Template Studio) — أرقام منظَّفة في app، بحد 5. STOP مستبعد كالعادة؛
        # سياسة الموافقة لا تنطبق (المستلم هو صاحب الحساب أو فريقه يختبر).
        with get_conn() as c:
            for p in (spec.get("phones") or [])[:5]:
                peer = "wa:" + str(p).lstrip("+")
                r = c.execute("SELECT id FROM contacts WHERE owner_id=? AND phone=?", (owner_id, p)).fetchone()
                if peer not in stopped and peer not in seen:
                    seen.add(peer)
                    out.append({"contact_id": r[0] if r else None, "peer": peer})
    elif kind == "retarget":
        src = get_campaign(int(spec.get("campaign_id") or 0), owner_id)
        state = spec.get("state")
        if not src or state not in ("sent", "delivered", "read", "not_read", "replied",
                                    "delivered_not_replied", "failed"):
            return []
        with get_conn() as c:
            optins = {r[0]: r[1] for r in c.execute("SELECT id, optin FROM contacts WHERE owner_id=?", (owner_id,))}
        for r in campaign_recipient_states(src["id"]):
            st = r["state"]
            hit = {"sent": st in ("sent", "delivered", "read"), "delivered": st in ("delivered", "read"),
                   "read": st == "read", "not_read": st in ("sent", "delivered"), "replied": r["replied"],
                   "delivered_not_replied": st in ("delivered", "read") and not r["replied"],
                   "failed": st == "failed"}[state]
            if hit:
                add(r["contact_id"], r["peer"], optins.get(r["contact_id"]))
    return out


def campaigns_overview(owner_id, since):
    """بطاقات «نظرة عامة» لآخر فترة: مجموع حالات كل الحملات التي بدأت بعد `since`."""
    with get_conn() as c:
        ids = [r[0] for r in c.execute("SELECT id FROM campaigns WHERE owner_id=? AND started_at>=?",
                                       (owner_id, since))]
    agg = {"campaigns": len(ids), "recipients": 0, "sent": 0, "delivered": 0, "read": 0, "replied": 0,
           "failed": 0, "failures": {}}
    for cid in ids:
        s = campaign_stats(cid)
        for k in ("recipients", "sent", "delivered", "read", "replied", "failed"):
            agg[k] += s[k]
        for b, n in s["failures"].items():
            agg["failures"][b] = agg["failures"].get(b, 0) + n
    return agg


# ─────────────────────────────  الفلو المرئي: الجلسات والزيارات  ─────────────────────────────
# المرحلة 5 — المحرك في flow_graph.py. جلسة لكل مرور عميل بفلو (نشطة · مكتملة · تحويل · متسرّبة)
# وعدّاد زيارات لكل بطاقة: منهما Sessions/Completed/Dropped و«خريطة التسرّب» على الكانفس.
def _flow_tables(c):
    c.executescript("""
        CREATE TABLE IF NOT EXISTS flow_sessions(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bot_id INTEGER NOT NULL,
            flow_id TEXT NOT NULL,
            peer TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'active',   -- active|completed|handoff|dropped
            last_node TEXT,
            started_at INTEGER NOT NULL, updated_at INTEGER NOT NULL, ended_at INTEGER,
            FOREIGN KEY(bot_id) REFERENCES bots(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS ix_flow_sess ON flow_sessions(bot_id, flow_id, status);
        CREATE INDEX IF NOT EXISTS ix_flow_sess_peer ON flow_sessions(bot_id, peer, status);
        CREATE TABLE IF NOT EXISTS flow_visits(
            bot_id INTEGER NOT NULL,
            flow_id TEXT NOT NULL,
            node_id TEXT NOT NULL,
            visits INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY(bot_id, flow_id, node_id),
            FOREIGN KEY(bot_id) REFERENCES bots(id) ON DELETE CASCADE
        );
    """)
    # مهلة الرد والتذكير (المرحلة 5): موعدا الجلسة المنتظرة يُحسبان عند الانتظار فيُستعلَم بفهرس
    cols = {r[1] for r in c.execute("PRAGMA table_info(flow_sessions)")}
    for col in ("remind_at INTEGER", "end_at INTEGER", "reminded INTEGER NOT NULL DEFAULT 0"):
        if col.split()[0] not in cols:
            c.execute(f"ALTER TABLE flow_sessions ADD COLUMN {col}")
    c.execute("CREATE INDEX IF NOT EXISTS ix_flow_sess_due ON flow_sessions(status, remind_at, end_at)")


def flow_session_start(bot_id, flow_id, peer):
    """جلسة جديدة. جلسة نشطة سابقة لنفس العميل على نفس البوت = تسرّب (بدأ شيئاً آخر)."""
    now = int(time.time())
    with get_conn() as c:
        c.execute("UPDATE flow_sessions SET status='dropped', ended_at=? WHERE bot_id=? AND peer=? AND status='active'",
                  (now, bot_id, peer))
        return c.execute("INSERT INTO flow_sessions(bot_id,flow_id,peer,started_at,updated_at) VALUES(?,?,?,?,?)",
                         (bot_id, flow_id, peer, now, now)).lastrowid


def flow_session_touch(sid, node_id, remind_at=None, end_at=None):
    """الجلسة تنتظر رد العميل عند `node_id`. موعدا التذكير والإنهاء يُعادان مع كل انتظار جديد."""
    if not sid:
        return
    with get_conn() as c:
        c.execute("UPDATE flow_sessions SET last_node=?, updated_at=?, remind_at=?, end_at=?, reminded=0"
                  " WHERE id=? AND status='active'", (node_id, int(time.time()), remind_at, end_at, sid))


def flow_sessions_due(now, limit=200):
    """جلسات نشطة حلّ موعد تذكيرها (ولم تُذكَّر) أو موعد إنهائها."""
    with get_conn() as c:
        rows = c.execute(
            "SELECT * FROM flow_sessions WHERE status='active' AND ((remind_at IS NOT NULL AND remind_at<=?"
            " AND reminded=0) OR (end_at IS NOT NULL AND end_at<=?)) ORDER BY id LIMIT ?",
            (now, now, limit)).fetchall()
    return [dict(r) for r in rows]


def flow_session_mark(sid, reminded=None, clear=False):
    with get_conn() as c:
        if clear:
            c.execute("UPDATE flow_sessions SET remind_at=NULL, end_at=NULL WHERE id=?", (sid,))
        elif reminded:
            c.execute("UPDATE flow_sessions SET reminded=1 WHERE id=?", (sid,))


def resolve_conversation(bot_id, peer):
    """«إغلاق المحادثة» من الفلو: حالة «مغلقة» في الصندوق المشترك، تعود للبوت، ويُصفَّر غير المقروء."""
    set_conversation_status(bot_id, peer, "resolved")


def least_loaded_assignee(owner_id, ids):
    """من فريق الحساب: صاحب أقل عدد من جهات الاتصال المسندة (التعادل = الأسبق في القائمة)."""
    if not ids:
        return None
    with get_conn() as c:
        load = {r[0]: r[1] for r in c.execute(
            "SELECT assignee_id, COUNT(*) FROM contacts WHERE owner_id=? AND assignee_id IN (%s) GROUP BY assignee_id"
            % ",".join("?" * len(ids)), (owner_id, *ids))}
    return min(ids, key=lambda i: (load.get(i, 0), ids.index(i)))


def flow_session_end(sid, status, node_id=None):
    if not sid:
        return
    now = int(time.time())
    with get_conn() as c:
        c.execute("UPDATE flow_sessions SET status=?, last_node=COALESCE(?, last_node), ended_at=?, updated_at=?"
                  " WHERE id=? AND status='active'", (status, node_id, now, now, sid))


def flow_visit(bot_id, flow_id, node_id):
    try:
        with get_conn() as c:
            c.execute("INSERT INTO flow_visits(bot_id,flow_id,node_id,visits) VALUES(?,?,?,1)"
                      " ON CONFLICT(bot_id,flow_id,node_id) DO UPDATE SET visits=visits+1", (bot_id, flow_id, node_id))
    except Exception:
        log.exception("flow_visit failed bot=%s", bot_id)


def flow_stats(bot_id, flow_id, drop_after=24 * 3600):
    """{sessions, completed, handoff, dropped, active, visits:{node:n}, drops:{node:n}}.
    جلسة نشطة لم تتحرّك منذ `drop_after` تُحتسب متسرّبة عند آخر بطاقة وصلها العميل."""
    stale = int(time.time()) - drop_after
    with get_conn() as c:
        rows = c.execute("SELECT status, last_node, updated_at FROM flow_sessions WHERE bot_id=? AND flow_id=?",
                         (bot_id, flow_id)).fetchall()
        visits = {r[0]: r[1] for r in c.execute(
            "SELECT node_id, visits FROM flow_visits WHERE bot_id=? AND flow_id=?", (bot_id, flow_id))}
    s = {"sessions": len(rows), "completed": 0, "handoff": 0, "dropped": 0, "active": 0, "visits": visits, "drops": {}}
    for r in rows:
        st = r["status"]
        if st == "active" and r["updated_at"] < stale:
            st = "dropped"
        s[st] = s.get(st, 0) + 1
        if st == "dropped" and r["last_node"]:
            s["drops"][r["last_node"]] = s["drops"].get(r["last_node"], 0) + 1
    return s


def delete_flow_stats(bot_id, flow_id):
    with get_conn() as c:
        c.execute("DELETE FROM flow_sessions WHERE bot_id=? AND flow_id=?", (bot_id, flow_id))
        c.execute("DELETE FROM flow_visits WHERE bot_id=? AND flow_id=?", (bot_id, flow_id))


# ---- جهة الاتصال من داخل الفلو (بطاقات الوسم وتحديث الحقل) ----
def contact_id_for_peer(bot_id, peer):
    with get_conn() as c:
        r = c.execute("SELECT contact_id FROM contact_peers WHERE bot_id=? AND peer=?", (bot_id, peer)).fetchone()
    return r[0] if r else None


def get_contact_by_id(contact_id):
    with get_conn() as c:
        r = c.execute(_CONTACT_SELECT + " WHERE c.id=?", (contact_id,)).fetchone()
    return _contact_row(r) if r else None


def tag_contact_by_names(owner_id, contact_id, names):
    """وسوم بأسمائها (تُنشأ لو لم توجد) — الجهة يجب أن تكون ملك الحساب."""
    now = int(time.time())
    with get_conn() as c:
        if not c.execute("SELECT 1 FROM contacts WHERE id=? AND owner_id=?", (contact_id, owner_id)).fetchone():
            return 0
        n = 0
        for name in names:
            tid = _tag_id(c, owner_id, name)
            if tid:
                n += c.execute("INSERT OR IGNORE INTO contact_tags(contact_id,tag_id,created_at) VALUES(?,?,?)",
                               (contact_id, tid, now)).rowcount
        return n


def set_contact_value(owner_id, contact_id, field, value):
    """قيمة من الفلو إلى جهة الاتصال: الاسم أو البريد أو حقل مخصّص — بنفس تحقّق الإدخال اليدوي.
    قيمة لا تناسب نوع الحقل تُتجاهل بصمت (لا تكسر المحادثة)."""
    now = int(time.time())
    value = (value or "").strip()
    if field == "name":
        with get_conn() as c:
            return c.execute("UPDATE contacts SET name=?, updated_at=? WHERE id=? AND owner_id=?",
                             (value[:120], now, contact_id, owner_id)).rowcount > 0
    if field == "email":
        email = CRM.norm_email(value)
        if not email:
            return False
        with get_conn() as c:
            return c.execute("UPDATE contacts SET email=?, updated_at=? WHERE id=? AND owner_id=?",
                             (email, now, contact_id, owner_id)).rowcount > 0
    fd = fields_map(owner_id, "contact").get(field)
    if not fd or fd["type"] == "user":
        return False
    val, err = CRM.clean_value(dict(fd, required=0), value)
    if err or val is None:
        return False
    with get_conn() as c:
        return c.execute("UPDATE contacts SET fields_json=json_set(fields_json, ?, json(?)), updated_at=?"
                         " WHERE id=? AND owner_id=?",
                         ('$."' + field + '"', CRM.dumps(val), now, contact_id, owner_id)).rowcount > 0



# ─────────────────────────────  الصندوق المشترك (المرحلة 6)  ─────────────────────────────
# المحادثة صارت وحدة عمل للفريق: حالة (مفتوحة · معلّقة · مغلقة) ومسؤول وفريق. `mode` (bot|human)
# يبقى كما هو: من يرد الآن — البوت أم إنسان. الحالة تقول هل انتهى العمل عليها، والإسناد يقول لمن.
# الملاحظات الداخلية رسائل `direction='note'` لا تُرسل للعميل ولا تدخل ذاكرة الذكاء الاصطناعي.
CONV_STATUSES = ("open", "pending", "resolved")
_VALID_PEER = ("(c.peer GLOB '[a-z][a-z]:[0-9]*' OR c.peer GLOB '[a-z][a-z]:-[0-9]*'"
               " OR c.peer GLOB 'wa:[A-Z][A-Z].[A-Za-z0-9]*')")


def _inbox_tables(c):
    c.executescript("""
        CREATE TABLE IF NOT EXISTS inbox_teams(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            owner_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            rule TEXT NOT NULL DEFAULT 'round_robin',   -- round_robin | manual
            rr_last INTEGER,                            -- آخر من استلم بالتناوب
            created_at INTEGER NOT NULL,
            UNIQUE(owner_id, name),
            FOREIGN KEY(owner_id) REFERENCES users(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS inbox_team_members(
            team_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            PRIMARY KEY(team_id, user_id),
            FOREIGN KEY(team_id) REFERENCES inbox_teams(id) ON DELETE CASCADE,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS canned_replies(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            owner_id INTEGER NOT NULL,
            shortcut TEXT NOT NULL,
            title TEXT NOT NULL DEFAULT '',
            body TEXT NOT NULL,
            created_by INTEGER,
            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL,
            UNIQUE(owner_id, shortcut),
            FOREIGN KEY(owner_id) REFERENCES users(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS inbox_mentions(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            owner_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            bot_id INTEGER NOT NULL,
            peer TEXT NOT NULL,
            message_id INTEGER NOT NULL,
            by_user INTEGER,
            created_at INTEGER NOT NULL,
            seen_at INTEGER,
            FOREIGN KEY(bot_id) REFERENCES bots(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS ix_mention_user ON inbox_mentions(user_id, seen_at);
    """)
    cols = {r[1] for r in c.execute("PRAGMA table_info(conversations)")}
    for col in ("status TEXT NOT NULL DEFAULT 'open'", "assignee_id INTEGER", "team_id INTEGER",
                "status_at INTEGER", "resolved_at INTEGER"):
        if col.split()[0] not in cols:
            c.execute(f"ALTER TABLE conversations ADD COLUMN {col}")
    if "user_id" not in {r[1] for r in c.execute("PRAGMA table_info(messages)")}:
        c.execute("ALTER TABLE messages ADD COLUMN user_id INTEGER")      # من أرسل الرد اليدوي/كتب الملاحظة
    c.execute("CREATE INDEX IF NOT EXISTS ix_conv_status ON conversations(bot_id, status, last_at)")
    c.execute("CREATE INDEX IF NOT EXISTS ix_conv_assignee ON conversations(assignee_id, status)")


# ---- الفرق ----
def account_user_ids(owner_id):
    """صاحب الحساب وكل فريقه — من يجوز إسناد المحادثات إليهم."""
    with get_conn() as c:
        return [owner_id] + [r[0] for r in c.execute("SELECT id FROM users WHERE works_for=? ORDER BY id", (owner_id,))]


def list_inbox_teams(owner_id):
    with get_conn() as c:
        teams = [dict(r) for r in c.execute("SELECT id, name, rule, created_at FROM inbox_teams WHERE owner_id=?"
                                            " ORDER BY name", (owner_id,))]
        for t in teams:
            t["members"] = [r[0] for r in c.execute("SELECT user_id FROM inbox_team_members WHERE team_id=?"
                                                    " ORDER BY user_id", (t["id"],))]
    return teams


def get_inbox_team(owner_id, team_id):
    return next((t for t in list_inbox_teams(owner_id) if t["id"] == team_id), None)


def save_inbox_team(owner_id, team_id, name, rule, members):
    """ينشئ أو يعدّل فريقاً. الأعضاء يُصفّون إلى أفراد الحساب فقط. يرجّع (id, خطأ)."""
    name = (name or "").strip()[:60]
    if not name:
        return None, "name"
    rule = rule if rule in ("round_robin", "manual") else "round_robin"
    allowed = set(account_user_ids(owner_id))
    members = sorted({int(m) for m in members or [] if str(m).isdigit() and int(m) in allowed})
    now = int(time.time())
    try:
        with get_conn() as c:
            if team_id:
                if not c.execute("UPDATE inbox_teams SET name=?, rule=? WHERE id=? AND owner_id=?",
                                 (name, rule, team_id, owner_id)).rowcount:
                    return None, "not_found"
            else:
                team_id = c.execute("INSERT INTO inbox_teams(owner_id,name,rule,created_at) VALUES(?,?,?,?)",
                                    (owner_id, name, rule, now)).lastrowid
            c.execute("DELETE FROM inbox_team_members WHERE team_id=?", (team_id,))
            c.executemany("INSERT INTO inbox_team_members(team_id,user_id) VALUES(?,?)", [(team_id, m) for m in members])
    except sqlite3.IntegrityError:
        return None, "duplicate"
    return team_id, None


def delete_inbox_team(owner_id, team_id):
    with get_conn() as c:
        if not c.execute("DELETE FROM inbox_teams WHERE id=? AND owner_id=?", (team_id, owner_id)).rowcount:
            return False
        c.execute("UPDATE conversations SET team_id=NULL WHERE team_id=?", (team_id,))
    return True


def user_team_ids(user_id):
    with get_conn() as c:
        return [r[0] for r in c.execute("SELECT team_id FROM inbox_team_members WHERE user_id=?", (user_id,))]


def next_in_team(owner_id, team_id):
    """التالي بالتناوب في فريق (round-robin) — ذرّي: طلبان متزامنان لا يأخذان نفس الموظف.
    فريق «يدوي» أو بلا أعضاء = None (تبقى المحادثة على الفريق بلا مسؤول)."""
    with get_conn() as c:
        c.execute("BEGIN IMMEDIATE")
        t = c.execute("SELECT rule, rr_last FROM inbox_teams WHERE id=? AND owner_id=?", (team_id, owner_id)).fetchone()
        if not t or t["rule"] != "round_robin":
            return None
        ids = [r[0] for r in c.execute("SELECT user_id FROM inbox_team_members WHERE team_id=? ORDER BY user_id",
                                       (team_id,))]
        if not ids:
            return None
        nxt = next((i for i in ids if t["rr_last"] is not None and i > t["rr_last"]), ids[0])
        c.execute("UPDATE inbox_teams SET rr_last=? WHERE id=?", (nxt, team_id))
        return nxt


# ---- حالة المحادثة والإسناد ----
def _conv_touch(c, bot_id, peer):
    c.execute("INSERT OR IGNORE INTO conversations(bot_id,peer,last_at) VALUES(?,?,?)", (bot_id, peer, int(time.time())))


def assign_conversation(bot_id, peer, user_id=None, team_id=None, takeover=True, actor=None):
    """مسؤول و/أو فريق المحادثة. إسنادها لموظف = تولٍّ بشري (البوت يسكت) ما لم `takeover=False`.
    المستدعي يتحقق أن الموظف والفريق من الحساب. الموظف الجديد يصله إشعار — إلا من أسندها لنفسه (`actor`)."""
    now = int(time.time())
    with get_conn() as c:
        _conv_touch(c, bot_id, peer)
        prev = c.execute("SELECT assignee_id, name FROM conversations WHERE bot_id=? AND peer=?", (bot_id, peer)).fetchone()
        if user_id and user_id != actor and (not prev or prev["assignee_id"] != user_id):
            _notify(c, user_id, "assigned", {"name": (prev["name"] if prev else "") or peer.split(":", 1)[-1]},
                    f"/inbox?bot={bot_id}&peer={urllib.parse.quote(peer)}")
        c.execute("UPDATE conversations SET assignee_id=?, team_id=?,"
                  " status=CASE WHEN status='resolved' THEN 'open' ELSE status END, status_at=?"
                  " WHERE bot_id=? AND peer=?", (user_id, team_id, now, bot_id, peer))
        if user_id and takeover:
            c.execute("UPDATE conversations SET mode='human', human_at=? WHERE bot_id=? AND peer=?", (now, bot_id, peer))


def set_conversation_status(bot_id, peer, status):
    """open | pending | resolved. الإغلاق يعيد المحادثة للبوت ويصفّر غير المقروء — رسالة جديدة من
    العميل تعيد فتحها تلقائياً (log_message)."""
    if status not in CONV_STATUSES:
        return False
    now = int(time.time())
    with get_conn() as c:
        _conv_touch(c, bot_id, peer)
        if status == "resolved":
            c.execute("UPDATE conversations SET status='resolved', status_at=?, resolved_at=?, mode='bot',"
                      " human_at=NULL, unread=0 WHERE bot_id=? AND peer=?", (now, now, bot_id, peer))
        else:
            c.execute("UPDATE conversations SET status=?, status_at=? WHERE bot_id=? AND peer=?",
                      (status, now, bot_id, peer))
    return True


def auto_resolve_idle(now=None):
    """إغلاق آلي للمحادثات المفتوحة الخاملة حسب إعداد كل قناة (`inbox.auto_resolve` بالساعات).
    «المعلّقة» لا تُغلق آلياً — تعليقها قرار موظف. يرجّع عدد ما أُغلق."""
    now = int(now or time.time())
    n = 0
    with get_conn() as c:
        for bid, cfg in c.execute("SELECT id, config_json FROM bots WHERE config_json LIKE '%auto_resolve%'").fetchall():
            try:
                hours = int((json.loads(cfg or "{}").get("inbox") or {}).get("auto_resolve") or 0)
            except (TypeError, ValueError):
                continue
            if hours <= 0:
                continue
            n += c.execute("UPDATE conversations SET status='resolved', status_at=?, resolved_at=?, mode='bot',"
                           " human_at=NULL, unread=0 WHERE bot_id=? AND status='open' AND last_at<?",
                           (now, now, bid, now - hours * 3600)).rowcount
    return n


def route_conversation(owner_id, bot_id, peer, team_id):
    """تحويل آلي لفريق (من الفلو أو إعداد القناة): الفريق + التالي بالتناوب إن وُجد.
    لا يغيّر مسؤولاً قائماً — المحادثة التي يتابعها موظف تبقى معه."""
    conv = get_conversation(bot_id, peer) or {}
    if conv.get("assignee_id") and conv.get("status") != "resolved":
        return conv["assignee_id"]
    if not get_inbox_team(owner_id, team_id):
        return None
    who = next_in_team(owner_id, team_id)
    assign_conversation(bot_id, peer, who, team_id, takeover=False)
    return who


# ---- الملاحظات والإشارات ----
def add_note(bot_id, peer, user_id, text, mention_ids=()):
    """ملاحظة داخلية على المحادثة + إشارة لكل موظف مذكور. لا تمسّ ملخّص المحادثة ولا غير المقروء."""
    now = int(time.time())
    text = (text or "")[:MSG_TEXT_MAX]
    with get_conn() as c:
        mid = c.execute("INSERT INTO messages(bot_id,peer,direction,sender,kind,text,created_at,user_id)"
                        " VALUES(?,?,?,?,?,?,?,?)", (bot_id, peer, "note", "human", "note", text, now, user_id)).lastrowid
        owner = c.execute("SELECT owner_id FROM bots WHERE id=?", (bot_id,)).fetchone()[0]
        by = (c.execute("SELECT username FROM users WHERE id=?", (user_id,)).fetchone() or [""])[0]
        name = (c.execute("SELECT name FROM conversations WHERE bot_id=? AND peer=?", (bot_id, peer)).fetchone() or [""])[0]
        for u in set(mention_ids):
            if u != user_id:
                c.execute("INSERT INTO inbox_mentions(owner_id,user_id,bot_id,peer,message_id,by_user,created_at)"
                          " VALUES(?,?,?,?,?,?,?)", (owner, u, bot_id, peer, mid, user_id, now))
                _notify(c, u, "mention", {"by": by, "name": name or peer.split(":", 1)[-1], "text": text[:140]},
                        f"/inbox?bot={bot_id}&peer={urllib.parse.quote(peer)}")
    return mid


def mentions_seen(user_id, bot_id, peer):
    with get_conn() as c:
        c.execute("UPDATE inbox_mentions SET seen_at=? WHERE user_id=? AND bot_id=? AND peer=? AND seen_at IS NULL",
                  (int(time.time()), user_id, bot_id, peer))


# ---- القائمة الموحّدة ----
def _view_where(view, user_id, team_ids):
    """(شرط SQL, معاملات) لكل عرض. العروض: open · mine · unassigned · bot · pending · resolved · team:<id> · mentions · all."""
    if view == "mine":
        return "c.assignee_id=? AND c.status<>'resolved'", [user_id]
    if view == "unassigned":           # تنتظر إنساناً ولم يستلمها أحد
        return "c.assignee_id IS NULL AND c.status<>'resolved' AND c.mode='human'", []
    if view == "bot":
        return "c.assignee_id IS NULL AND c.status='open' AND c.mode='bot'", []
    if view in ("pending", "resolved"):
        return "c.status=?", [view]
    if view.startswith("team:") and view[5:].isdigit():
        return "c.team_id=? AND c.status<>'resolved'", [int(view[5:])]
    if view == "mentions":
        return ("EXISTS(SELECT 1 FROM inbox_mentions x WHERE x.bot_id=c.bot_id AND x.peer=c.peer"
                " AND x.user_id=? AND x.seen_at IS NULL)"), [user_id]
    if view == "all":
        return "1=1", []
    return "c.status<>'resolved'", []                      # open (الافتراضي): كل ما لم يُغلق


def _scope_where(own_only, user_id, team_ids):
    """الموظف في حساب «يرى ما يخصّه فقط»: المسندة إليه، وغير المسندة، ومحادثات فِرقه."""
    if not own_only:
        return "1=1", []
    q = "(c.assignee_id=? OR c.assignee_id IS NULL"
    args = [user_id]
    if team_ids:
        q += " OR c.team_id IN (%s)" % ",".join("?" * len(team_ids))
        args += list(team_ids)
    return q + ")", args


def inbox_list(owner_id, user_id, view="open", bot_id=None, q=None, own_only=False, team_ids=(),
               limit=50, offset=0):
    vw, va = _view_where(view, user_id, team_ids)
    sw, sa = _scope_where(own_only, user_id, team_ids)
    where = [f"b.owner_id=?", _VALID_PEER, vw, sw]
    args = [owner_id] + va + sa
    if bot_id:
        where.append("c.bot_id=?"); args.append(bot_id)
    if q:
        like = "%" + q.replace("%", "").replace("_", "")[:60] + "%"
        where.append("(c.name LIKE ? OR c.peer LIKE ? OR c.last_text LIKE ?)"); args += [like, like, like]
    sql = ("SELECT c.*, b.name bot_name, b.channel bot_channel, u.username assignee_name, t.name team_name"
           " FROM conversations c JOIN bots b ON b.id=c.bot_id"
           " LEFT JOIN users u ON u.id=c.assignee_id LEFT JOIN inbox_teams t ON t.id=c.team_id"
           " WHERE " + " AND ".join(where) + " ORDER BY c.last_at DESC LIMIT ? OFFSET ?")
    with get_conn() as c:
        return [dict(r) for r in c.execute(sql, args + [int(limit), int(offset)])]


def inbox_counts(owner_id, user_id, own_only=False, team_ids=()):
    sw, sa = _scope_where(own_only, user_id, team_ids)
    views = ["open", "mine", "unassigned", "bot", "pending", "resolved", "mentions"] + [f"team:{t}" for t in team_ids]
    out = {}
    with get_conn() as c:
        for v in views:
            vw, va = _view_where(v, user_id, team_ids)
            out[v] = c.execute(f"SELECT COUNT(*) FROM conversations c JOIN bots b ON b.id=c.bot_id WHERE b.owner_id=?"
                               f" AND {_VALID_PEER} AND {vw} AND {sw}", [owner_id] + va + sa).fetchone()[0]
        out["unread"] = c.execute(f"SELECT COALESCE(SUM(c.unread),0) FROM conversations c JOIN bots b ON b.id=c.bot_id"
                                  f" WHERE b.owner_id=? AND c.status<>'resolved' AND {_VALID_PEER} AND {sw}",
                                  [owner_id] + sa).fetchone()[0]
    return out


def conv_visible(bot_id, peer, user_id, own_only, team_ids):
    if not own_only:
        return True
    conv = get_conversation(bot_id, peer) or {}
    return not conv.get("assignee_id") or conv["assignee_id"] == user_id or conv.get("team_id") in set(team_ids)


# ---- الردود الجاهزة ----
def list_canned(owner_id):
    with get_conn() as c:
        return [dict(r) for r in c.execute("SELECT id, shortcut, title, body, updated_at FROM canned_replies"
                                           " WHERE owner_id=? ORDER BY shortcut", (owner_id,))]


def save_canned(owner_id, cid, shortcut, title, body, by):
    shortcut = re.sub(r"[^\w\-؀-ۿ]", "", (shortcut or "").strip().lstrip("/").lower())[:30]
    body = (body or "").strip()[:4000]
    if not shortcut:
        return None, "shortcut"
    if not body:
        return None, "body"
    now = int(time.time())
    try:
        with get_conn() as c:
            if cid:
                if not c.execute("UPDATE canned_replies SET shortcut=?, title=?, body=?, updated_at=? WHERE id=? AND owner_id=?",
                                 (shortcut, (title or "")[:80], body, now, cid, owner_id)).rowcount:
                    return None, "not_found"
                return cid, None
            if c.execute("SELECT COUNT(*) FROM canned_replies WHERE owner_id=?", (owner_id,)).fetchone()[0] >= 500:
                return None, "limit"
            return c.execute("INSERT INTO canned_replies(owner_id,shortcut,title,body,created_by,created_at,updated_at)"
                             " VALUES(?,?,?,?,?,?,?)", (owner_id, shortcut, (title or "")[:80], body, by, now, now)).lastrowid, None
    except sqlite3.IntegrityError:
        return None, "duplicate"


def delete_canned(owner_id, cid):
    with get_conn() as c:
        return c.execute("DELETE FROM canned_replies WHERE id=? AND owner_id=?", (cid, owner_id)).rowcount > 0



# ─────────────────────────────  التسلسلات (المرحلة 6)  ─────────────────────────────
# متابعة آلية على خطوات بتأخير لكل عميل مسجَّل. المنطق (الإرسال والمال والنافذة) في sequences.py.
def _sequence_tables(c):
    c.executescript("""
        CREATE TABLE IF NOT EXISTS sequences(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            owner_id INTEGER NOT NULL,
            bot_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            active INTEGER NOT NULL DEFAULT 0,
            spec_json TEXT NOT NULL DEFAULT '{}',   -- {steps, trigger, stop_on_reply, hours}
            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL,
            FOREIGN KEY(bot_id) REFERENCES bots(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS ix_seq_owner ON sequences(owner_id);
        CREATE TABLE IF NOT EXISTS sequence_enrollments(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sequence_id INTEGER NOT NULL,
            bot_id INTEGER NOT NULL,
            peer TEXT NOT NULL,
            step INTEGER NOT NULL DEFAULT 0,          -- الخطوة التالية
            next_at INTEGER,
            status TEXT NOT NULL DEFAULT 'active',    -- active | done | stopped
            reason TEXT,                              -- سبب التوقّف: replied · opted_out · human · manual · deleted
            started_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL,
            FOREIGN KEY(sequence_id) REFERENCES sequences(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS ix_enr_due ON sequence_enrollments(status, next_at);
        CREATE INDEX IF NOT EXISTS ix_enr_peer ON sequence_enrollments(bot_id, peer, status);
        CREATE TABLE IF NOT EXISTS sequence_sends(
            enrollment_id INTEGER NOT NULL,
            sequence_id INTEGER NOT NULL,
            step INTEGER NOT NULL,
            ok INTEGER NOT NULL,
            note TEXT,
            created_at INTEGER NOT NULL,
            FOREIGN KEY(sequence_id) REFERENCES sequences(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS ix_seq_sends ON sequence_sends(sequence_id, step);
    """)


def _seq_row(r):
    d = dict(r)
    d["spec"] = json.loads(d.pop("spec_json") or "{}")
    d["active"] = bool(d["active"])
    return d


def list_sequences(owner_id, bot_id=None):
    q, a = "SELECT * FROM sequences WHERE owner_id=?", [owner_id]
    if bot_id:
        q += " AND bot_id=?"; a.append(bot_id)
    with get_conn() as c:
        return [_seq_row(r) for r in c.execute(q + " ORDER BY id DESC", a)]


def get_sequence(seq_id, owner_id=None):
    q, a = "SELECT * FROM sequences WHERE id=?", [seq_id]
    if owner_id is not None:
        q += " AND owner_id=?"; a.append(owner_id)
    with get_conn() as c:
        r = c.execute(q, a).fetchone()
    return _seq_row(r) if r else None


def save_sequence(owner_id, seq_id, bot_id, name, spec, active):
    now = int(time.time())
    with get_conn() as c:
        if seq_id:
            ok = c.execute("UPDATE sequences SET bot_id=?, name=?, spec_json=?, active=?, updated_at=? WHERE id=? AND owner_id=?",
                           (bot_id, name, json.dumps(spec, ensure_ascii=False), int(bool(active)), now, seq_id, owner_id)).rowcount
            return seq_id if ok else None
        return c.execute("INSERT INTO sequences(owner_id,bot_id,name,spec_json,active,created_at,updated_at) VALUES(?,?,?,?,?,?,?)",
                         (owner_id, bot_id, name, json.dumps(spec, ensure_ascii=False), int(bool(active)), now, now)).lastrowid


def set_sequence_active(owner_id, seq_id, active):
    with get_conn() as c:
        return c.execute("UPDATE sequences SET active=?, updated_at=? WHERE id=? AND owner_id=?",
                         (int(bool(active)), int(time.time()), seq_id, owner_id)).rowcount > 0


def delete_sequence(owner_id, seq_id):
    with get_conn() as c:
        return c.execute("DELETE FROM sequences WHERE id=? AND owner_id=?", (seq_id, owner_id)).rowcount > 0


def enroll_peer(seq_id, bot_id, peer, next_at):
    """تسجيل عميل في تسلسل. تسجيل نشط قائم لنفس العميل في نفس التسلسل = لا تكرار (None)."""
    now = int(time.time())
    with get_conn() as c:
        c.execute("BEGIN IMMEDIATE")
        if c.execute("SELECT 1 FROM sequence_enrollments WHERE sequence_id=? AND peer=? AND status='active'",
                     (seq_id, peer)).fetchone():
            return None
        return c.execute("INSERT INTO sequence_enrollments(sequence_id,bot_id,peer,step,next_at,started_at,updated_at)"
                         " VALUES(?,?,?,0,?,?,?)", (seq_id, bot_id, peer, next_at, now, now)).lastrowid


def due_enrollments(now, limit=100):
    with get_conn() as c:
        return [dict(r) for r in c.execute(
            "SELECT e.* FROM sequence_enrollments e JOIN sequences s ON s.id=e.sequence_id"
            " WHERE e.status='active' AND e.next_at<=? AND s.active=1 ORDER BY e.next_at LIMIT ?", (now, limit))]


def claim_enrollment(eid, step, next_at_was):
    """حجز ذرّي لإرسال خطوة: دورتان متزامنتان لا ترسلان الخطوة نفسها مرتين."""
    with get_conn() as c:
        return c.execute("UPDATE sequence_enrollments SET next_at=NULL, updated_at=? WHERE id=? AND status='active'"
                         " AND step=? AND next_at=?", (int(time.time()), eid, step, next_at_was)).rowcount > 0


def advance_enrollment(eid, step, next_at):
    with get_conn() as c:
        c.execute("UPDATE sequence_enrollments SET step=?, next_at=?, updated_at=? WHERE id=? AND status='active'",
                  (step, next_at, int(time.time()), eid))


def end_enrollment(eid, status, reason=None):
    with get_conn() as c:
        c.execute("UPDATE sequence_enrollments SET status=?, reason=?, next_at=NULL, updated_at=? WHERE id=? AND status='active'",
                  (status, reason, int(time.time()), eid))


def stop_enrollments_for_peer(bot_id, peer, reason, only_stop_on_reply=False):
    """إيقاف تسجيلات العميل النشطة (ردّ · STOP · تولٍّ بشري). `only_stop_on_reply`: ما يطلب التوقّف عند الرد فقط."""
    now = int(time.time())
    with get_conn() as c:
        q = ("UPDATE sequence_enrollments SET status='stopped', reason=?, next_at=NULL, updated_at=?"
             " WHERE bot_id=? AND peer=? AND status='active'")
        if only_stop_on_reply:
            q += (" AND sequence_id IN (SELECT id FROM sequences WHERE"
                  " COALESCE(json_extract(spec_json,'$.stop_on_reply'),1)=1)")
        return c.execute(q, (reason, now, bot_id, peer)).rowcount


def log_sequence_send(eid, seq_id, step, ok, note=None):
    with get_conn() as c:
        c.execute("INSERT INTO sequence_sends(enrollment_id,sequence_id,step,ok,note,created_at) VALUES(?,?,?,?,?,?)",
                  (eid, seq_id, step, int(bool(ok)), (note or "")[:200], int(time.time())))


def sequence_stats(seq_id):
    with get_conn() as c:
        st = {r[0]: r[1] for r in c.execute("SELECT status, COUNT(*) FROM sequence_enrollments WHERE sequence_id=?"
                                            " GROUP BY status", (seq_id,))}
        steps = {}
        for r in c.execute("SELECT step, SUM(ok), SUM(1-ok) FROM sequence_sends WHERE sequence_id=? GROUP BY step", (seq_id,)):
            steps[r[0]] = {"sent": r[1] or 0, "failed": r[2] or 0}
        reasons = {r[0] or "": r[1] for r in c.execute(
            "SELECT reason, COUNT(*) FROM sequence_enrollments WHERE sequence_id=? AND status='stopped' GROUP BY reason", (seq_id,))}
    return {"enrolled": sum(st.values()), "active": st.get("active", 0), "done": st.get("done", 0),
            "stopped": st.get("stopped", 0), "steps": steps, "reasons": reasons}


def peer_enrollments(bot_id, peer):
    with get_conn() as c:
        return [dict(r) for r in c.execute(
            "SELECT e.id, e.sequence_id, s.name, e.step, e.next_at, e.status FROM sequence_enrollments e"
            " JOIN sequences s ON s.id=e.sequence_id WHERE e.bot_id=? AND e.peer=? ORDER BY e.id DESC LIMIT 20",
            (bot_id, peer))]


def sequences_for_tags(owner_id, tag_names):
    """التسلسلات النشطة التي يشغّلها وسم من هذه الوسوم."""
    names = {str(n).strip().lower() for n in tag_names if n}
    return [s for s in list_sequences(owner_id) if s["active"]
            and (s["spec"].get("trigger") or {}).get("type") == "tag"
            and str((s["spec"].get("trigger") or {}).get("tag") or "").strip().lower() in names]



# ─────────────────────────────  النمو (المرحلة 7): روابط التتبّع · إعلانات CTWA · ودجت الموقع  ─────────────────────────────
def _growth_tables(c):
    c.executescript("""
        CREATE TABLE IF NOT EXISTS growth_links(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            owner_id INTEGER NOT NULL,
            bot_id INTEGER NOT NULL,
            code TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL,
            text TEXT NOT NULL DEFAULT '',
            clicks INTEGER NOT NULL DEFAULT 0,
            created_at INTEGER NOT NULL,
            FOREIGN KEY(bot_id) REFERENCES bots(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS growth_hits(
            link_id INTEGER NOT NULL,
            bot_id INTEGER NOT NULL,
            peer TEXT NOT NULL,
            created_at INTEGER NOT NULL,
            PRIMARY KEY(link_id, peer),
            FOREIGN KEY(link_id) REFERENCES growth_links(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS ad_referrals(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bot_id INTEGER NOT NULL,
            peer TEXT NOT NULL,
            source_type TEXT, source_id TEXT, source_url TEXT,
            headline TEXT, body TEXT, ctwa_clid TEXT,
            created_at INTEGER NOT NULL,
            FOREIGN KEY(bot_id) REFERENCES bots(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS ix_adref_bot ON ad_referrals(bot_id, source_id);
        CREATE INDEX IF NOT EXISTS ix_adref_peer ON ad_referrals(bot_id, peer, created_at);
        CREATE TABLE IF NOT EXISTS capi_events(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bot_id INTEGER NOT NULL,
            peer TEXT NOT NULL,
            event TEXT NOT NULL,
            value REAL, currency TEXT,
            ok INTEGER NOT NULL DEFAULT 0,
            error TEXT,
            created_at INTEGER NOT NULL,
            FOREIGN KEY(bot_id) REFERENCES bots(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS ix_capi_bot ON capi_events(bot_id, created_at);
    """)


# ---- روابط التتبّع ----
def create_growth_link(owner_id, bot_id, code, name, text):
    try:
        with get_conn() as c:
            return c.execute("INSERT INTO growth_links(owner_id,bot_id,code,name,text,created_at) VALUES(?,?,?,?,?,?)",
                             (owner_id, bot_id, code, name, text, int(time.time()))).lastrowid
    except sqlite3.IntegrityError:
        return None                                   # رمز مكرر — المستدعي يولّد غيره


def update_growth_link(owner_id, link_id, name, text):
    with get_conn() as c:
        return c.execute("UPDATE growth_links SET name=?, text=? WHERE id=? AND owner_id=?",
                         (name, text, link_id, owner_id)).rowcount > 0


def delete_growth_link(owner_id, link_id):
    with get_conn() as c:
        return c.execute("DELETE FROM growth_links WHERE id=? AND owner_id=?", (link_id, owner_id)).rowcount > 0


def get_growth_link(code=None, link_id=None, owner_id=None):
    q, a = "SELECT * FROM growth_links WHERE ", []
    if code:
        q += "code=?"; a.append(code)
    else:
        q += "id=?"; a.append(link_id)
    if owner_id is not None:
        q += " AND owner_id=?"; a.append(owner_id)
    with get_conn() as c:
        r = c.execute(q, a).fetchone()
    return dict(r) if r else None


def list_growth_links(owner_id):
    with get_conn() as c:
        return [dict(r) for r in c.execute(
            "SELECT l.*, b.name bot_name, b.channel bot_channel,"
            " (SELECT COUNT(*) FROM growth_hits h WHERE h.link_id=l.id) conversations,"
            " (SELECT COUNT(*) FROM growth_hits h JOIN leads d ON d.bot_id=h.bot_id"
            "   AND d.tg_user_id=CAST(substr(h.peer, 4) AS INTEGER) WHERE h.link_id=l.id) leads"
            " FROM growth_links l JOIN bots b ON b.id=l.bot_id WHERE l.owner_id=? ORDER BY l.id DESC", (owner_id,))]


def growth_click(code):
    with get_conn() as c:
        c.execute("UPDATE growth_links SET clicks=clicks+1 WHERE code=?", (code,))


def growth_hit(bot_id, code, peer):
    """محادثة جاءت من رابط تتبّع (أول مرة لكل عميل). الرابط يجب أن يكون لهذا البوت. يرجّع الرابط أو None."""
    link = get_growth_link(code=code)
    if not link or link["bot_id"] != bot_id:
        return None
    with get_conn() as c:
        c.execute("INSERT OR IGNORE INTO growth_hits(link_id,bot_id,peer,created_at) VALUES(?,?,?,?)",
                  (link["id"], bot_id, peer, int(time.time())))
    return link


# ---- إعلانات Click-to-WhatsApp ----
def record_ad_referral(bot_id, peer, ref):
    with get_conn() as c:
        return c.execute("INSERT INTO ad_referrals(bot_id,peer,source_type,source_id,source_url,headline,body,ctwa_clid,created_at)"
                         " VALUES(?,?,?,?,?,?,?,?,?)",
                         (bot_id, peer, (ref.get("source_type") or "")[:20], (ref.get("source_id") or "")[:40],
                          (ref.get("source_url") or "")[:500], (ref.get("headline") or "")[:200],
                          (ref.get("body") or "")[:500], (ref.get("ctwa_clid") or "")[:500], int(time.time()))).lastrowid


def last_ad_referral(bot_id, peer, within=7 * 86400):
    """آخر نقرة إعلان للعميل خلال النافذة (Meta تقبل التحويلات حتى 7 أيام من النقرة)."""
    with get_conn() as c:
        r = c.execute("SELECT * FROM ad_referrals WHERE bot_id=? AND peer=? AND created_at>=? ORDER BY id DESC LIMIT 1",
                      (bot_id, peer, int(time.time()) - within)).fetchone()
    return dict(r) if r else None


def ads_report(owner_id, since):
    """لكل إعلان: المحادثات · العملاء · الإدخالات (leads) · الأهداف المحقّقة (goal_*) · تحويلات أُرسلت لـ Meta."""
    with get_conn() as c:
        rows = [dict(r) for r in c.execute(
            "SELECT a.bot_id, b.name bot_name, a.source_id, a.source_type, MAX(a.headline) headline, MAX(a.source_url) source_url,"
            " COUNT(*) clicks, COUNT(DISTINCT a.peer) people, MIN(a.created_at) first_at, MAX(a.created_at) last_at,"
            " (SELECT COUNT(DISTINCT d.tg_user_id) FROM leads d WHERE d.bot_id=a.bot_id AND d.created_at>=MIN(a.created_at)"
            "   AND d.tg_user_id IN (SELECT CAST(substr(x.peer,4) AS INTEGER) FROM ad_referrals x"
            "                        WHERE x.bot_id=a.bot_id AND x.source_id=a.source_id)) leads,"
            " (SELECT COUNT(*) FROM capi_events e WHERE e.bot_id=a.bot_id AND e.ok=1 AND e.peer IN"
            "   (SELECT x.peer FROM ad_referrals x WHERE x.bot_id=a.bot_id AND x.source_id=a.source_id)) conversions"
            " FROM ad_referrals a JOIN bots b ON b.id=a.bot_id WHERE b.owner_id=? AND a.created_at>=?"
            " GROUP BY a.bot_id, a.source_id ORDER BY people DESC LIMIT 200", (owner_id, since))]
    return rows


def peer_source(bot_id, peer):
    """من أين جاء العميل: آخر نقرة إعلان، وإلا رابط التتبّع — للوحة جهة الاتصال في الصندوق المشترك."""
    with get_conn() as c:
        r = c.execute("SELECT headline, source_url, source_id, created_at FROM ad_referrals WHERE bot_id=? AND peer=?"
                      " ORDER BY id DESC LIMIT 1", (bot_id, peer)).fetchone()
        if r:
            return {"kind": "ad", "name": r["headline"] or r["source_id"], "url": r["source_url"], "at": r["created_at"]}
        r = c.execute("SELECT l.name, h.created_at FROM growth_hits h JOIN growth_links l ON l.id=h.link_id"
                      " WHERE h.bot_id=? AND h.peer=? ORDER BY h.created_at DESC LIMIT 1", (bot_id, peer)).fetchone()
    return {"kind": "link", "name": r["name"], "at": r["created_at"]} if r else None


def log_capi_event(bot_id, peer, event, value, currency, ok, error=None):
    with get_conn() as c:
        c.execute("INSERT INTO capi_events(bot_id,peer,event,value,currency,ok,error,created_at) VALUES(?,?,?,?,?,?,?,?)",
                  (bot_id, peer, event, value, currency, int(bool(ok)), (error or "")[:300], int(time.time())))


def capi_recent(owner_id, limit=50):
    with get_conn() as c:
        return [dict(r) for r in c.execute(
            "SELECT e.*, b.name bot_name FROM capi_events e JOIN bots b ON b.id=e.bot_id WHERE b.owner_id=?"
            " ORDER BY e.id DESC LIMIT ?", (owner_id, limit))]



# ---- ودجت الموقع ومحادثة الويب (المرحلة 7) ----
def _widget_tables(c):
    c.executescript("""
        CREATE TABLE IF NOT EXISTS web_widgets(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            owner_id INTEGER NOT NULL,
            key TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL,
            bot_id INTEGER,                      -- البوت الذي يرد في محادثة الويب
            wa_bot_id INTEGER,                   -- رقم واتساب لزر «أكمل على واتساب»
            settings_json TEXT NOT NULL DEFAULT '{}',
            views INTEGER NOT NULL DEFAULT 0,
            wa_clicks INTEGER NOT NULL DEFAULT 0,
            chats INTEGER NOT NULL DEFAULT 0,
            created_at INTEGER NOT NULL,
            FOREIGN KEY(owner_id) REFERENCES users(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS web_outbox(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bot_id INTEGER NOT NULL,
            peer TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            created_at INTEGER NOT NULL,
            FOREIGN KEY(bot_id) REFERENCES bots(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS ix_web_outbox ON web_outbox(bot_id, peer, id);
    """)


def _widget_row(r):
    d = dict(r)
    d["settings"] = json.loads(d.pop("settings_json") or "{}")
    return d


def list_widgets(owner_id):
    with get_conn() as c:
        return [_widget_row(r) for r in c.execute("SELECT * FROM web_widgets WHERE owner_id=? ORDER BY id DESC", (owner_id,))]


def get_widget(key=None, widget_id=None, owner_id=None):
    q, a = ("SELECT * FROM web_widgets WHERE key=?", [key]) if key else ("SELECT * FROM web_widgets WHERE id=?", [widget_id])
    if owner_id is not None:
        q += " AND owner_id=?"; a.append(owner_id)
    with get_conn() as c:
        r = c.execute(q, a).fetchone()
    return _widget_row(r) if r else None


def save_widget(owner_id, widget_id, key, name, bot_id, wa_bot_id, settings):
    s = json.dumps(settings, ensure_ascii=False)
    with get_conn() as c:
        if widget_id:
            return widget_id if c.execute("UPDATE web_widgets SET name=?, bot_id=?, wa_bot_id=?, settings_json=? WHERE id=? AND owner_id=?",
                                          (name, bot_id, wa_bot_id, s, widget_id, owner_id)).rowcount else None
        return c.execute("INSERT INTO web_widgets(owner_id,key,name,bot_id,wa_bot_id,settings_json,created_at) VALUES(?,?,?,?,?,?,?)",
                         (owner_id, key, name, bot_id, wa_bot_id, s, int(time.time()))).lastrowid


def delete_widget(owner_id, widget_id):
    with get_conn() as c:
        return c.execute("DELETE FROM web_widgets WHERE id=? AND owner_id=?", (widget_id, owner_id)).rowcount > 0


def widget_count(widget_id, col):
    if col not in ("views", "wa_clicks", "chats"):
        return
    with get_conn() as c:
        c.execute(f"UPDATE web_widgets SET {col}={col}+1 WHERE id=?", (widget_id,))


def web_push(bot_id, peer, payload):
    """رسالة صادرة لزائر محادثة الويب (من البوت أو الموظف أو صداه هو) — يستطلعها الودجت."""
    with get_conn() as c:
        return c.execute("INSERT INTO web_outbox(bot_id,peer,payload_json,created_at) VALUES(?,?,?,?)",
                         (bot_id, peer, json.dumps(payload, ensure_ascii=False), int(time.time()))).lastrowid


def web_pull(bot_id, peer, after=0, limit=60):
    with get_conn() as c:
        if after:
            rows = c.execute("SELECT id, payload_json, created_at FROM web_outbox WHERE bot_id=? AND peer=? AND id>?"
                             " ORDER BY id LIMIT ?", (bot_id, peer, int(after), limit)).fetchall()
        else:
            rows = c.execute("SELECT * FROM (SELECT id, payload_json, created_at FROM web_outbox WHERE bot_id=? AND peer=?"
                             " ORDER BY id DESC LIMIT ?) ORDER BY id", (bot_id, peer, limit)).fetchall()
    return [dict(json.loads(r["payload_json"]), id=r["id"], at=r["created_at"]) for r in rows]


def purge_web_outbox(max_age=90 * 86400):
    with get_conn() as c:
        return c.execute("DELETE FROM web_outbox WHERE created_at<?", (int(time.time()) - max_age,)).rowcount



# ─────────────────────────────  الدفع داخل المحادثة (المرحلة 9)  ─────────────────────────────
# روابط دفع من بوابة صاحب النشاط نفسه (payments_gw). المبلغ بالوحدة الصغرى صحيحاً.
def _chat_pay_tables(c):
    c.executescript("""
        CREATE TABLE IF NOT EXISTS chat_payments(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            owner_id INTEGER NOT NULL,
            bot_id INTEGER NOT NULL,
            peer TEXT NOT NULL,
            provider TEXT NOT NULL,
            gw_id TEXT,
            amount INTEGER NOT NULL,                  -- بالوحدة الصغرى (هللة/قرش)
            currency TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'pending',   -- pending | paid | failed | expired | cancelled
            url TEXT,
            flow_id TEXT, node_id TEXT,               -- بطاقة الفلو التي تنتظر الدفع (إن وُجدت)
            created_by INTEGER,                        -- موظف أرسله من الصندوق، أو NULL للفلو
            created_at INTEGER NOT NULL,
            expires_at INTEGER NOT NULL,
            paid_at INTEGER,
            FOREIGN KEY(bot_id) REFERENCES bots(id) ON DELETE CASCADE
        );
        CREATE UNIQUE INDEX IF NOT EXISTS ux_chatpay_gw ON chat_payments(provider, gw_id) WHERE gw_id IS NOT NULL;
        CREATE INDEX IF NOT EXISTS ix_chatpay_owner ON chat_payments(owner_id, created_at);
        CREATE INDEX IF NOT EXISTS ix_chatpay_due ON chat_payments(status, expires_at);
    """)


def create_chat_payment(owner_id, bot_id, peer, provider, amount, currency, description, expires_at,
                        flow_id=None, node_id=None, created_by=None):
    with get_conn() as c:
        return c.execute("INSERT INTO chat_payments(owner_id,bot_id,peer,provider,amount,currency,description,flow_id,"
                         "node_id,created_by,created_at,expires_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                         (owner_id, bot_id, peer, provider, int(amount), currency, description[:255], flow_id, node_id,
                          created_by, int(time.time()), int(expires_at))).lastrowid


def set_chat_payment_link(pid, gw_id, url):
    with get_conn() as c:
        c.execute("UPDATE chat_payments SET gw_id=?, url=? WHERE id=?", (gw_id, url, pid))


def get_chat_payment(pid=None, provider=None, gw_id=None, owner_id=None):
    if pid is not None:
        q, a = "SELECT * FROM chat_payments WHERE id=?", [pid]
    else:
        q, a = "SELECT * FROM chat_payments WHERE provider=? AND gw_id=?", [provider, gw_id]
    if owner_id is not None:
        q += " AND owner_id=?"; a.append(owner_id)
    with get_conn() as c:
        r = c.execute(q, a).fetchone()
    return dict(r) if r else None


def settle_chat_payment(pid, status, from_states=("pending",)):
    """انتقال ذرّي من حالة مسموحة فقط — إشعاران متزامنان (ويبهوك + صفحة العودة) لا يسوّيان مرتين.
    `from_states`: «مدفوعة» تُقبل أيضاً بعد «ملغاة/منتهية» محلياً — المال وصل فعلاً عند البوابة.
    يرجّع True لمن نفّذ الانتقال فعلاً."""
    now = int(time.time())
    states = tuple(s for s in from_states if s in ("pending", "cancelled", "expired"))
    with get_conn() as c:
        return c.execute("UPDATE chat_payments SET status=?, paid_at=CASE WHEN ?='paid' THEN ? ELSE paid_at END"
                         f" WHERE id=? AND status IN ({','.join('?' * len(states))})",
                         (status, status, now, pid, *states)).rowcount > 0


def cancel_pending_payments(bot_id, peer):
    """العميل ألغى المحادثة: روابطه المعلّقة تُعلَّم ملغاة (ولو دفع لاحقاً تُقبل — confirm)."""
    with get_conn() as c:
        return c.execute("UPDATE chat_payments SET status='cancelled' WHERE bot_id=? AND peer=? AND status='pending'",
                         (bot_id, peer)).rowcount


def due_chat_payments(now, limit=100):
    with get_conn() as c:
        return [dict(r) for r in c.execute("SELECT * FROM chat_payments WHERE status='pending' AND expires_at<=?"
                                           " ORDER BY expires_at LIMIT ?", (now, limit))]


def pending_chat_payments(created_before, now, limit=100):
    """معلّقة لم تنتهِ مدتها وعمرها دقيقة على الأقل (لا نسأل البوابة عن رابط أُرسل للتوّ)."""
    with get_conn() as c:
        return [dict(r) for r in c.execute("SELECT * FROM chat_payments WHERE status='pending' AND gw_id IS NOT NULL"
                                           " AND created_at<=? AND expires_at>? ORDER BY id LIMIT ?",
                                           (created_before, now, limit))]


def list_chat_payments(owner_id, status=None, limit=200):
    q, a = ("SELECT p.*, b.name bot_name, cv.name customer FROM chat_payments p JOIN bots b ON b.id=p.bot_id"
            " LEFT JOIN conversations cv ON cv.bot_id=p.bot_id AND cv.peer=p.peer WHERE p.owner_id=?"), [owner_id]
    if status:
        q += " AND p.status=?"; a.append(status)
    with get_conn() as c:
        return [dict(r) for r in c.execute(q + " ORDER BY p.id DESC LIMIT ?", a + [limit])]


def chat_payment_totals(owner_id, since):
    with get_conn() as c:
        rows = c.execute("SELECT currency, status, COUNT(*) n, COALESCE(SUM(amount),0) total FROM chat_payments"
                         " WHERE owner_id=? AND created_at>=? GROUP BY currency, status", (owner_id, since)).fetchall()
    return [dict(r) for r in rows]



# ════════════════════════ التكاملات — المرحلة 9 (سلة · زد · Shopify · WooCommerce · Webhook) ════════════════════════
def _integration_tables(c):
    c.executescript("""
        CREATE TABLE IF NOT EXISTS integrations(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            owner_id INTEGER NOT NULL,
            provider TEXT NOT NULL,                    -- salla | zid | shopify | woocommerce | webhook
            name TEXT NOT NULL DEFAULT '',
            bot_id INTEGER NOT NULL,                   -- قناة واتساب التي تُرسل منها الرسائل
            key TEXT NOT NULL UNIQUE,                  -- جزء مسار الاستقبال (128 بت عشوائية)
            secret TEXT,                               -- سرّ توقيع المزوّد (مختوم db.seal) أو NULL
            cc TEXT NOT NULL DEFAULT '+966',           -- مفتاح الدولة لأرقام بلا مفتاح
            rules_json TEXT NOT NULL DEFAULT '[]',
            active INTEGER NOT NULL DEFAULT 1,
            created_at INTEGER NOT NULL,
            last_at INTEGER,
            FOREIGN KEY(bot_id) REFERENCES bots(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS ix_integ_owner ON integrations(owner_id);
        CREATE TABLE IF NOT EXISTS integration_events(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            integration_id INTEGER NOT NULL,
            dedupe TEXT NOT NULL,                      -- «الحدث:رقم الطلب» — نفس الإشعار لا يصل العميل مرتين
            event TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'received',   -- received | sent | done | skipped | failed | ignored
            detail TEXT NOT NULL DEFAULT '',
            phone TEXT,
            summary TEXT NOT NULL DEFAULT '',
            created_at INTEGER NOT NULL,
            UNIQUE(integration_id, dedupe),
            FOREIGN KEY(integration_id) REFERENCES integrations(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS ix_integ_ev ON integration_events(integration_id, id);
    """)
    # Facebook Lead Ads: الصفحة المربوطة وتوكنها (مختوم) — أعمدة منفصلة عن سرّ التوقيع
    cols = {r[1] for r in c.execute("PRAGMA table_info(integrations)")}
    for col in ("ext_id", "ext_name", "token", "meta"):
        if col not in cols:
            c.execute(f"ALTER TABLE integrations ADD COLUMN {col} TEXT")
    for col in ("cursor", "checked_at"):                # Google Sheets: عدد الصفوف المعالَجة وآخر فحص
        if col not in cols:
            c.execute(f"ALTER TABLE integrations ADD COLUMN {col} INTEGER NOT NULL DEFAULT 0")
    c.execute("CREATE INDEX IF NOT EXISTS ix_integ_ext ON integrations(provider, ext_id)")


def _integration_row(r):
    d = dict(r)
    d["rules"] = json.loads(d.pop("rules_json") or "[]")
    d["has_secret"] = bool(d.get("secret"))
    d["has_token"] = bool(d.get("token"))
    try:
        d["meta"] = json.loads(d.get("meta") or "{}")
    except ValueError:
        d["meta"] = {}
    return d


def set_integration_page(owner_id, iid, page_id, page_name, page_token):
    with get_conn() as c:
        return c.execute("UPDATE integrations SET ext_id=?, ext_name=?, token=? WHERE id=? AND owner_id=?",
                         (page_id, (page_name or "")[:120], seal(page_token), iid, owner_id)).rowcount > 0


def integration_token(row):
    return unseal(row["token"]) if row and row.get("token") else ""


def set_integration_sheet(iid, link=None, cursor=None, meta=None, checked_at=None):
    """Google Sheets: الرابط · المؤشّر (صفوف عولجت) · العناوين وعمود الهاتف · آخر فحص — ما يُمرَّر فقط."""
    sets, args = [], []
    for col, v in (("ext_id", link), ("cursor", cursor), ("meta", json.dumps(meta, ensure_ascii=False) if meta is not None else None),
                   ("checked_at", checked_at)):
        if v is not None:
            sets.append(f"{col}=?"); args.append(v)
    if sets:
        with get_conn() as c:
            c.execute(f"UPDATE integrations SET {', '.join(sets)} WHERE id=?", args + [iid])


def sheet_integrations():
    with get_conn() as c:
        return [_integration_row(r) for r in c.execute("SELECT * FROM integrations WHERE provider='sheets' AND active=1")]


def integrations_for_page(page_id):
    with get_conn() as c:
        return [_integration_row(r) for r in c.execute(
            "SELECT * FROM integrations WHERE provider='fb_leads' AND ext_id=? AND active=1", (str(page_id),))]


def set_integration_event_info(eid, phone, summary):
    with get_conn() as c:
        c.execute("UPDATE integration_events SET phone=?, summary=? WHERE id=?", (phone, (summary or "")[:200], eid))


def create_integration(owner_id, provider, name, bot_id, key, secret, cc, rules):
    with get_conn() as c:
        return c.execute("INSERT INTO integrations(owner_id,provider,name,bot_id,key,secret,cc,rules_json,created_at)"
                         " VALUES(?,?,?,?,?,?,?,?,?)",
                         (owner_id, provider, name, bot_id, key, seal(secret) if secret else None, cc,
                          json.dumps(rules, ensure_ascii=False), int(time.time()))).lastrowid


def update_integration(owner_id, iid, name, bot_id, cc, rules, active, secret=None, clear_secret=False):
    with get_conn() as c:
        n = c.execute("UPDATE integrations SET name=?, bot_id=?, cc=?, rules_json=?, active=? WHERE id=? AND owner_id=?",
                      (name, bot_id, cc, json.dumps(rules, ensure_ascii=False), 1 if active else 0, iid, owner_id)).rowcount
        if n and (secret or clear_secret):
            c.execute("UPDATE integrations SET secret=? WHERE id=?", (seal(secret) if secret else None, iid))
        return n > 0


def delete_integration(owner_id, iid):
    with get_conn() as c:
        c.execute("DELETE FROM integration_events WHERE integration_id IN"
                  " (SELECT id FROM integrations WHERE id=? AND owner_id=?)", (iid, owner_id))
        return c.execute("DELETE FROM integrations WHERE id=? AND owner_id=?", (iid, owner_id)).rowcount > 0


def get_integration(iid=None, owner_id=None, key=None):
    """بالمعرّف (مع صاحبه) أو بمفتاح المسار. السرّ يبقى مختوماً هنا — `integration_secret` تفتحه."""
    with get_conn() as c:
        if key is not None:
            r = c.execute("SELECT * FROM integrations WHERE key=?", (key,)).fetchone()
        else:
            r = c.execute("SELECT * FROM integrations WHERE id=? AND owner_id=?", (iid, owner_id)).fetchone()
    return _integration_row(r) if r else None


def integration_secret(row):
    return unseal(row["secret"]) if row and row.get("secret") else ""


def list_integrations(owner_id):
    since = int(time.time()) - 30 * 86400
    with get_conn() as c:
        rows = c.execute("SELECT i.*, b.name bot_name,"
                         " (SELECT COUNT(*) FROM integration_events e WHERE e.integration_id=i.id AND e.created_at>=?) n30,"
                         " (SELECT COUNT(*) FROM integration_events e WHERE e.integration_id=i.id AND e.created_at>=?"
                         "   AND e.status IN ('sent','done')) ok30"
                         " FROM integrations i JOIN bots b ON b.id=i.bot_id WHERE i.owner_id=? ORDER BY i.id",
                         (since, since, owner_id)).fetchall()
    return [_integration_row(r) for r in rows]


def claim_integration_event(iid, dedupe, event, phone, summary):
    """يسجّل الحدث مرة واحدة ⇒ معرّفه، أو None لو وصل من قبل (إعادة إرسال المتجر لنفس الإشعار)."""
    now = int(time.time())
    with get_conn() as c:
        try:
            eid = c.execute("INSERT INTO integration_events(integration_id,dedupe,event,phone,summary,created_at)"
                            " VALUES(?,?,?,?,?,?)", (iid, dedupe[:200], event[:60], phone, summary[:200], now)).lastrowid
        except sqlite3.IntegrityError:
            return None
        c.execute("UPDATE integrations SET last_at=? WHERE id=?", (now, iid))
        # سجلّ محدود: آخر 2000 حدث لكل تكامل (منع التكرار يعمل داخل هذه النافذة)
        c.execute("DELETE FROM integration_events WHERE integration_id=? AND id <="
                  " (SELECT id FROM integration_events WHERE integration_id=? ORDER BY id DESC LIMIT 1 OFFSET 2000)",
                  (iid, iid))
        return eid


def set_integration_event(eid, status, detail=""):
    with get_conn() as c:
        c.execute("UPDATE integration_events SET status=?, detail=? WHERE id=?", (status, str(detail)[:300], eid))


def list_integration_events(owner_id, iid, limit=50):
    with get_conn() as c:
        return [dict(r) for r in c.execute(
            "SELECT e.* FROM integration_events e JOIN integrations i ON i.id=e.integration_id"
            " WHERE e.integration_id=? AND i.owner_id=? ORDER BY e.id DESC LIMIT ?", (iid, owner_id, limit))]


def upsert_contact_by_phone(owner_id, phone, name="", email=None, source="integration"):
    """جهة اتصال بالهاتف من متجر/نظام خارجي ⇒ (المعرّف, الموافقة). القائمة لا يُمحى اسمها ولا بريدها،
    ولا تُغيَّر موافقتها (STOP يبقى STOP)."""
    now = int(time.time())
    with get_conn() as c:
        r = c.execute("SELECT id, name, email, optin FROM contacts WHERE owner_id=? AND phone=?", (owner_id, phone)).fetchone()
        if r:
            c.execute("UPDATE contacts SET name=?, email=?, updated_at=? WHERE id=?",
                      (r["name"] or (name or "")[:120], r["email"] or email, now, r["id"]))
            return r["id"], r["optin"]
        try:
            cid = c.execute("INSERT INTO contacts(owner_id,name,phone,email,fields_json,source,created_at,updated_at)"
                            " VALUES(?,?,?,?,'{}',?,?,?)",
                            (owner_id, (name or "")[:120], phone, email, source, now, now)).lastrowid
        except sqlite3.IntegrityError:          # سباق مع إدخال آخر لنفس الرقم
            r = c.execute("SELECT id, optin FROM contacts WHERE owner_id=? AND phone=?", (owner_id, phone)).fetchone()
            return (r["id"], r["optin"]) if r else (None, None)
        return cid, None


def peer_consented(bot_id, peer):
    """موافقة من داخل المحادثة (زر «أوافق على العروض») على هذا البوت، وليس بعدها STOP."""
    with get_conn() as c:
        return c.execute("SELECT 1 FROM bot_users WHERE bot_id=? AND peer=? AND optin_at IS NOT NULL AND opted_out=0",
                         (bot_id, peer)).fetchone() is not None


# ════════════════════════ أتمتة التعليقات — المرحلة 8 ════════════════════════
def _comment_tables(c):
    c.executescript("""
        CREATE TABLE IF NOT EXISTS comment_actions(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bot_id INTEGER NOT NULL,
            comment_id TEXT NOT NULL,
            post_id TEXT NOT NULL DEFAULT '',
            user_id TEXT NOT NULL DEFAULT '',
            user_name TEXT NOT NULL DEFAULT '',
            text TEXT NOT NULL DEFAULT '',
            rule_id TEXT NOT NULL DEFAULT '',
            public_ok INTEGER,                         -- NULL لم يُطلب · 1 نجح · 0 فشل
            private_ok INTEGER,
            error TEXT NOT NULL DEFAULT '',
            created_at INTEGER NOT NULL,
            UNIQUE(bot_id, comment_id),
            FOREIGN KEY(bot_id) REFERENCES bots(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS ix_cmt_user ON comment_actions(bot_id, rule_id, post_id, user_id);
        CREATE INDEX IF NOT EXISTS ix_cmt_time ON comment_actions(bot_id, created_at);
    """)


def claim_comment(bot_id, c, rule_id):
    """يحجز التعليق مرة واحدة ⇒ المعرّف، أو None لو عولج من قبل."""
    with get_conn() as conn:
        try:
            return conn.execute("INSERT INTO comment_actions(bot_id,comment_id,post_id,user_id,user_name,text,rule_id,created_at)"
                                " VALUES(?,?,?,?,?,?,?,?)",
                                (bot_id, c["comment_id"], c["post_id"], c["user_id"], c["user_name"][:80],
                                 c["text"][:500], rule_id, int(time.time()))).lastrowid
        except sqlite3.IntegrityError:
            return None


def finish_comment(aid, public_ok, private_ok, error=""):
    def b(v):
        return None if v is None else (1 if v else 0)
    with get_conn() as c:
        c.execute("UPDATE comment_actions SET public_ok=?, private_ok=?, error=? WHERE id=?",
                  (b(public_ok), b(private_ok), str(error or "")[:300], aid))


def comment_user_done(bot_id, rule_id, post_id, user_id):
    with get_conn() as c:
        return c.execute("SELECT 1 FROM comment_actions WHERE bot_id=? AND rule_id=? AND post_id=? AND user_id=? LIMIT 1",
                         (bot_id, rule_id, post_id, user_id)).fetchone() is not None


def comment_stats(bot_id, since):
    """لكل قاعدة: التعليقات المعالَجة · الردود العلنية · الرسائل الخاصة الناجحة · الإخفاقات."""
    with get_conn() as c:
        rows = c.execute("SELECT rule_id, COUNT(*) n, SUM(public_ok=1) pub, SUM(private_ok=1) dm,"
                         " SUM(public_ok=0 OR private_ok=0) bad"
                         " FROM comment_actions WHERE bot_id=? AND created_at>=? GROUP BY rule_id", (bot_id, since)).fetchall()
    return {r["rule_id"]: {"n": r["n"], "pub": r["pub"] or 0, "dm": r["dm"] or 0, "bad": r["bad"] or 0} for r in rows}


def _crm_sync_tables(c):
    c.executescript("""
        CREATE TABLE IF NOT EXISTS crm_links(
            owner_id INTEGER NOT NULL,
            contact_id INTEGER NOT NULL,
            provider TEXT NOT NULL,
            ext_id TEXT NOT NULL,
            synced_at INTEGER NOT NULL,
            PRIMARY KEY(owner_id, contact_id, provider),
            FOREIGN KEY(contact_id) REFERENCES contacts(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS ix_contacts_upd ON contacts(owner_id, updated_at, id);
    """)
    if "hash" not in {r[1] for r in c.execute("PRAGMA table_info(crm_links)")}:   # المزامنة باتجاهين: بصمة آخر تطابق
        c.execute("ALTER TABLE crm_links ADD COLUMN hash TEXT")
    c.execute("CREATE INDEX IF NOT EXISTS ix_crm_ext ON crm_links(owner_id, provider, ext_id)")


def crm_link(owner_id, contact_id, provider):
    with get_conn() as c:
        r = c.execute("SELECT ext_id FROM crm_links WHERE owner_id=? AND contact_id=? AND provider=?",
                      (owner_id, contact_id, provider)).fetchone()
    return r[0] if r else None


def crm_link_hash(owner_id, contact_id, provider):
    with get_conn() as c:
        r = c.execute("SELECT hash FROM crm_links WHERE owner_id=? AND contact_id=? AND provider=?",
                      (owner_id, contact_id, provider)).fetchone()
    return r[0] if r else None


def crm_contact_by_ext(owner_id, provider, ext_id):
    with get_conn() as c:
        r = c.execute("SELECT contact_id, hash FROM crm_links WHERE owner_id=? AND provider=? AND ext_id=?",
                      (owner_id, provider, str(ext_id))).fetchone()
    return (r[0], r[1]) if r else (None, None)


def set_crm_link(owner_id, contact_id, provider, ext_id, hash_=None):
    """`hash_`: بصمة آخر قيم متطابقة بين الطرفين — تمنع الصدى (دفع ثم سحب ثم دفع…)."""
    with get_conn() as c:
        c.execute("INSERT INTO crm_links(owner_id,contact_id,provider,ext_id,synced_at,hash) VALUES(?,?,?,?,?,?)"
                  " ON CONFLICT(owner_id,contact_id,provider) DO UPDATE SET ext_id=excluded.ext_id,"
                  " synced_at=excluded.synced_at, hash=COALESCE(excluded.hash, crm_links.hash)",
                  (owner_id, contact_id, provider, str(ext_id), int(time.time()), hash_))


def contact_by_email(owner_id, email):
    with get_conn() as c:
        r = c.execute("SELECT id FROM contacts WHERE owner_id=? AND lower(email)=lower(?) LIMIT 1", (owner_id, email)).fetchone()
    return r[0] if r else None


def contact_by_phone(owner_id, phone):
    with get_conn() as c:
        r = c.execute("SELECT id FROM contacts WHERE owner_id=? AND phone=? LIMIT 1", (owner_id, phone)).fetchone()
    return r[0] if r else None


def update_contact_from_crm(owner_id, contact_id, name, phone, email):
    """قيم الـ CRM على جهة قائمة — الفارغ لا يمحو، والهاتف المأخوذ لجهة أخرى لا يُكتب (يبقى القديم)."""
    now = int(time.time())
    with get_conn() as c:
        if name:
            c.execute("UPDATE contacts SET name=?, updated_at=? WHERE id=? AND owner_id=?", (name[:120], now, contact_id, owner_id))
        if email:
            c.execute("UPDATE contacts SET email=?, updated_at=? WHERE id=? AND owner_id=?", (email, now, contact_id, owner_id))
        if phone:
            try:
                c.execute("UPDATE contacts SET phone=?, updated_at=? WHERE id=? AND owner_id=?", (phone, now, contact_id, owner_id))
            except sqlite3.IntegrityError:
                pass


def create_contact_from_crm(owner_id, name, phone, email):
    now = int(time.time())
    with get_conn() as c:
        try:
            return c.execute("INSERT INTO contacts(owner_id,name,phone,email,fields_json,source,created_at,updated_at)"
                             " VALUES(?,?,?,?,'{}','crm',?,?)", (owner_id, (name or "")[:120], phone, email, now, now)).lastrowid
        except sqlite3.IntegrityError:
            return None


def contacts_changed_since(owner_id, cursor, limit=100):
    """جهات تغيّرت بعد المؤشّر [updated_at, id] مرتّبةً — المؤشّر المركّب لا يُسقط جهتين بنفس الثانية."""
    ts, cid = (cursor if isinstance(cursor, (list, tuple)) and len(cursor) == 2 else (0, 0))
    with get_conn() as c:
        return [dict(r) for r in c.execute(
            "SELECT id, name, phone, email, updated_at FROM contacts WHERE owner_id=? AND"
            " (updated_at > ? OR (updated_at = ? AND id > ?)) ORDER BY updated_at, id LIMIT ?",
            (owner_id, int(ts), int(ts), int(cid), limit))]


def max_lead_id(owner_id):
    with get_conn() as c:
        r = c.execute("SELECT MAX(l.id) FROM leads l JOIN bots b ON b.id=l.bot_id WHERE b.owner_id=?", (owner_id,)).fetchone()
    return r[0] or 0


def leads_after(owner_id, lead_id, limit=100):
    with get_conn() as c:
        return [dict(r) for r in c.execute(
            "SELECT l.id, l.bot_id, l.tg_user_id, l.data_json, l.created_at, b.name bot_name FROM leads l"
            " JOIN bots b ON b.id=l.bot_id WHERE b.owner_id=? AND l.id>? ORDER BY l.id LIMIT ?",
            (owner_id, int(lead_id or 0), limit))]


def lead_contact(lead):
    """جهة اتصال الإدخال: بمعرّف العميل في قناة البوت (واتساب: الرقم نفسه)."""
    if not lead.get("tg_user_id"):
        return None
    with get_conn() as c:
        r = c.execute("SELECT contact_id FROM contact_peers WHERE bot_id=? AND substr(peer, instr(peer, ':') + 1)=?",
                      (lead["bot_id"], str(lead["tg_user_id"]))).fetchone()
    return r[0] if r else None


def owners_with_setting(key):
    with get_conn() as c:
        return [r[0] for r in c.execute("SELECT user_id FROM settings WHERE key=? AND value IS NOT NULL AND value!=''", (key,))]


# ════════════════════════ مكالمات واتساب — المرحلة 8 ════════════════════════
def _call_tables(c):
    c.executescript("""
        CREATE TABLE IF NOT EXISTS wa_calls(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bot_id INTEGER NOT NULL,
            call_id TEXT NOT NULL UNIQUE,
            peer TEXT NOT NULL,
            name TEXT NOT NULL DEFAULT '',
            sdp TEXT NOT NULL DEFAULT '',              -- عرض Meta — يُمسح عند الانتهاء
            status TEXT NOT NULL DEFAULT 'ringing',    -- ringing | answered | rejected | ended | missed
            agent_id INTEGER,
            duration INTEGER NOT NULL DEFAULT 0,
            created_at INTEGER NOT NULL,
            answered_at INTEGER,
            ended_at INTEGER,
            FOREIGN KEY(bot_id) REFERENCES bots(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS ix_calls_ring ON wa_calls(status, created_at);
        CREATE INDEX IF NOT EXISTS ix_calls_bot ON wa_calls(bot_id, id);
        CREATE TABLE IF NOT EXISTS call_permissions(
            bot_id INTEGER NOT NULL,
            peer TEXT NOT NULL,
            granted INTEGER NOT NULL,
            expires_at INTEGER NOT NULL DEFAULT 0,     -- 0 = دائم
            updated_at INTEGER NOT NULL,
            PRIMARY KEY(bot_id, peer),
            FOREIGN KEY(bot_id) REFERENCES bots(id) ON DELETE CASCADE
        );
    """)
    cols = {r[1] for r in c.execute("PRAGMA table_info(wa_calls)")}
    if "direction" not in cols:                        # المكالمات الصادرة: الاتجاه وجواب SDP من العميل
        c.execute("ALTER TABLE wa_calls ADD COLUMN direction TEXT NOT NULL DEFAULT 'in'")
    if "answer_sdp" not in cols:
        c.execute("ALTER TABLE wa_calls ADD COLUMN answer_sdp TEXT NOT NULL DEFAULT ''")


def set_call_permission(bot_id, peer, granted, expires_at):
    with get_conn() as c:
        c.execute("INSERT INTO call_permissions(bot_id,peer,granted,expires_at,updated_at) VALUES(?,?,?,?,?)"
                  " ON CONFLICT(bot_id,peer) DO UPDATE SET granted=excluded.granted, expires_at=excluded.expires_at,"
                  " updated_at=excluded.updated_at", (bot_id, peer, 1 if granted else 0, int(expires_at or 0), int(time.time())))


def get_call_permission(bot_id, peer):
    with get_conn() as c:
        r = c.execute("SELECT * FROM call_permissions WHERE bot_id=? AND peer=?", (bot_id, peer)).fetchone()
    return dict(r) if r else None


def add_out_call(bot_id, call_id, peer, agent_id):
    with get_conn() as c:
        c.execute("INSERT INTO wa_calls(bot_id,call_id,peer,status,agent_id,direction,created_at) VALUES(?,?,?,'dialing',?,'out',?)",
                  (bot_id, call_id, peer, agent_id, int(time.time())))


def set_call_answer(call_id, sdp):
    """العميل ردّ على مكالمتنا ⇒ جواب SDP مرة واحدة (من «يتصل» فقط)."""
    with get_conn() as c:
        return c.execute("UPDATE wa_calls SET status='answered', answer_sdp=?, answered_at=? WHERE call_id=?"
                         " AND status='dialing' AND direction='out'", (sdp, int(time.time()), call_id)).rowcount > 0


def agent_busy(agent_id):
    with get_conn() as c:
        return c.execute("SELECT 1 FROM wa_calls WHERE agent_id=? AND status IN ('dialing','answered') AND ended_at IS NULL"
                         " AND created_at>? LIMIT 1", (agent_id, int(time.time()) - 4 * 3600)).fetchone() is not None


def add_call(bot_id, call_id, peer, name, sdp):
    with get_conn() as c:
        try:
            return c.execute("INSERT INTO wa_calls(bot_id,call_id,peer,name,sdp,created_at) VALUES(?,?,?,?,?,?)",
                             (bot_id, call_id, peer, (name or "")[:120], sdp, int(time.time()))).lastrowid
        except sqlite3.IntegrityError:          # Meta تعيد الحدث
            return None


def get_call(call_id):
    with get_conn() as c:
        r = c.execute("SELECT * FROM wa_calls WHERE call_id=?", (call_id,)).fetchone()
    return dict(r) if r else None


def claim_call(call_id, agent_id, status="answered"):
    """من «ترنّ» فقط — موظف واحد يرد مهما ضغط الفريق معاً."""
    with get_conn() as c:
        return c.execute("UPDATE wa_calls SET status=?, agent_id=?, answered_at=? WHERE call_id=? AND status='ringing'",
                         (status, agent_id, int(time.time()) if status == "answered" else None, call_id)).rowcount > 0


def release_call(call_id):
    with get_conn() as c:
        c.execute("UPDATE wa_calls SET status='ringing', agent_id=NULL, answered_at=NULL"
                  " WHERE call_id=? AND status IN ('answered','rejected') AND ended_at IS NULL", (call_id,))


def end_call(call_id, duration):
    """انتهاء مرة واحدة ⇒ الصف بعد التحديث، أو None. مُجابة ⇒ ended بمدتها، وإلا missed (والمرفوضة تبقى)."""
    now = int(time.time())
    with get_conn() as c:
        n = c.execute("UPDATE wa_calls SET status=CASE status WHEN 'answered' THEN 'ended' WHEN 'rejected' THEN 'rejected'"
                      " WHEN 'dialing' THEN 'no_answer' ELSE 'missed' END, duration=?, ended_at=?, sdp='', answer_sdp=''"
                      " WHERE call_id=? AND ended_at IS NULL",
                      (max(0, int(duration or 0)), now, call_id)).rowcount
        r = c.execute("SELECT * FROM wa_calls WHERE call_id=?", (call_id,)).fetchone() if n else None
    return dict(r) if r else None


def stale_ringing_calls(before):
    with get_conn() as c:
        return [dict(r) for r in c.execute("SELECT * FROM wa_calls WHERE status IN ('ringing','dialing') AND created_at<?"
                                           " AND ended_at IS NULL", (before,))]


def ringing_calls(owner_id, since):
    with get_conn() as c:
        return [dict(r) for r in c.execute(
            "SELECT w.*, b.name bot_name FROM wa_calls w JOIN bots b ON b.id=w.bot_id"
            " WHERE b.owner_id=? AND w.status IN ('ringing','answered','dialing') AND w.ended_at IS NULL"
            " AND (w.created_at>=? OR w.status!='ringing') AND w.created_at>?"
            " ORDER BY w.id", (owner_id, since, int(time.time()) - 4 * 3600))]


# ════════════════════════ مركز الإشعارات ════════════════════════
# تُخزَّن بنوعها وبياناتها (لا نصاً جاهزاً) — الواجهة تكتبها بلغة المستخدم. آخر 200 لكل مستخدم.
NOTIFY_KEEP = 200
NOTIFY_HOOKS = []          # webpush.install() يضيف دالته: تُستدعى بكل إشعار جديد ولا ترمي


def save_push_sub(user_id, endpoint, p256dh, auth, ua=""):
    """اشتراك جهاز ⇒ id. نفس الـendpoint لمستخدم آخر (جهاز مشترك سجّل غيره دخوله) يُنقل له."""
    now = int(time.time())
    with get_conn() as c:
        c.execute("INSERT INTO push_subs(user_id,endpoint,p256dh,auth,ua,created_at) VALUES(?,?,?,?,?,?)"
                  " ON CONFLICT(endpoint) DO UPDATE SET user_id=excluded.user_id, p256dh=excluded.p256dh,"
                  " auth=excluded.auth, ua=excluded.ua, fails=0",
                  (user_id, endpoint, p256dh, auth, (ua or "")[:200], now))
        return c.execute("SELECT id FROM push_subs WHERE endpoint=?", (endpoint,)).fetchone()[0]


def delete_push_sub(endpoint, user_id=None):
    with get_conn() as c:
        if user_id is None:
            return c.execute("DELETE FROM push_subs WHERE endpoint=?", (endpoint,)).rowcount
        return c.execute("DELETE FROM push_subs WHERE endpoint=? AND user_id=?", (endpoint, user_id)).rowcount


def list_push_subs(user_id):
    with get_conn() as c:
        return [dict(r) for r in c.execute("SELECT * FROM push_subs WHERE user_id=? ORDER BY id", (user_id,))]


def push_sub_result(sub_id, ok, drop_after=5):
    """نتيجة إرسال: نجاح يصفّر العدّاد، والفشل المتتالي يحذف الاشتراك عند `drop_after`."""
    with get_conn() as c:
        if ok:
            c.execute("UPDATE push_subs SET last_ok=?, fails=0 WHERE id=?", (int(time.time()), sub_id))
        else:
            c.execute("UPDATE push_subs SET fails=fails+1 WHERE id=?", (sub_id,))
            c.execute("DELETE FROM push_subs WHERE id=? AND fails>=?", (sub_id, drop_after))


def unread_notifications(user_id):
    with get_conn() as c:
        return c.execute("SELECT COUNT(*) FROM notifications WHERE user_id=? AND read_at IS NULL", (user_id,)).fetchone()[0]


def platform_once(key, value):
    """يكتب القيمة فقط إن لم توجد ⇒ القيمة المخزّنة فعلاً (عمّال متعددون يولّدون معاً — واحد يفوز)."""
    with get_conn() as c:
        c.execute("INSERT OR IGNORE INTO platform(key,value) VALUES(?,?)", (key, value))
        return c.execute("SELECT value FROM platform WHERE key=?", (key,)).fetchone()[0]


def _notify_tables(c):
    c.executescript("""
        CREATE TABLE IF NOT EXISTS notifications(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            kind TEXT NOT NULL,
            data_json TEXT NOT NULL DEFAULT '{}',
            url TEXT NOT NULL DEFAULT '',
            created_at INTEGER NOT NULL,
            read_at INTEGER,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS ix_notify_user ON notifications(user_id, id);
        -- أجهزة الإشعارات الفورية (Web Push): اشتراك لكل متصفح/هاتف. endpoint فريد — نفس
        -- الجهاز يعيد الاشتراك فيُحدَّث صاحبه ولا يتكرر. fails: رفضات متتالية ⇒ حذف عند 5.
        CREATE TABLE IF NOT EXISTS push_subs(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            endpoint TEXT UNIQUE NOT NULL,
            p256dh TEXT NOT NULL,
            auth TEXT NOT NULL,
            ua TEXT NOT NULL DEFAULT '',
            created_at INTEGER NOT NULL,
            last_ok INTEGER,
            fails INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS ix_push_user ON push_subs(user_id);
    """)


def _username(c, user_id):
    r = c.execute("SELECT username FROM users WHERE id=?", (user_id,)).fetchone()
    return r[0] if r else ""


def _notify(c, user_id, kind, data, url="", dedupe=0):
    """داخل معاملة المستدعي (نفس الاتصال — لا كاتب ثانٍ ينتظر القفل). `dedupe` ثوانٍ: لا تكرار لنفس النوع والرابط."""
    if not user_id:
        return
    now = int(time.time())
    if dedupe and c.execute("SELECT 1 FROM notifications WHERE user_id=? AND kind=? AND url=? AND created_at>? LIMIT 1",
                            (user_id, kind, url, now - dedupe)).fetchone():
        return
    nid = c.execute("INSERT INTO notifications(user_id,kind,data_json,url,created_at) VALUES(?,?,?,?,?)",
                    (user_id, kind, json.dumps(data or {}, ensure_ascii=False)[:2000], url[:500], now)).lastrowid
    for hook in NOTIFY_HOOKS:           # الإشعار الفوري (webpush) — طابور في الذاكرة، لا شبكة داخل المعاملة
        try:
            hook({"id": nid, "user_id": user_id, "kind": kind, "data": data or {}, "url": url[:500], "created_at": now})
        except Exception:
            pass
    c.execute("DELETE FROM notifications WHERE user_id=? AND id <= (SELECT id FROM notifications WHERE user_id=?"
              " ORDER BY id DESC LIMIT 1 OFFSET ?)", (user_id, user_id, NOTIFY_KEEP))


def _notify_staff(c, kind, data, url):
    for (sid,) in c.execute("SELECT id FROM users WHERE role IN ('admin','support') AND COALESCE(is_blocked,0)=0").fetchall():
        _notify(c, sid, kind, data, url)


def notify(user_id, kind, data, url="", dedupe=0):
    """من خارج قاعدة البيانات (الدفع · التكاملات). لا يرمي — الإشعار لا يُسقط العملية الأصلية."""
    try:
        with get_conn() as c:
            _notify(c, user_id, kind, data, url, dedupe)
    except Exception:
        pass


def list_notifications(user_id, limit=30):
    with get_conn() as c:
        rows = [dict(r) for r in c.execute("SELECT id, kind, data_json, url, created_at, read_at FROM notifications"
                                           " WHERE user_id=? ORDER BY id DESC LIMIT ?", (user_id, limit))]
        unread = c.execute("SELECT COUNT(*) FROM notifications WHERE user_id=? AND read_at IS NULL", (user_id,)).fetchone()[0]
    for r in rows:
        r["data"] = json.loads(r.pop("data_json") or "{}")
    return rows, unread


def mark_notifications_read(user_id, ids=None):
    now = int(time.time())
    with get_conn() as c:
        if ids is None:
            return c.execute("UPDATE notifications SET read_at=? WHERE user_id=? AND read_at IS NULL", (now, user_id)).rowcount
        ids = [int(i) for i in ids if str(i).isdigit()][:100]
        if not ids:
            return 0
        return c.execute(f"UPDATE notifications SET read_at=? WHERE user_id=? AND read_at IS NULL AND id IN ({','.join('?' * len(ids))})",
                         (now, user_id, *ids)).rowcount


def support_metrics(now=None, sla=4 * 3600):
    """مؤشرات الدعم: المفتوحة · المنتظرة فوق حدّ الخدمة · متوسط أول رد (7 أيام) · نسبة الرد خلال ساعة · المحلولة."""
    now = int(now or time.time())
    week = now - 7 * 86400
    with get_conn() as c:
        opened = c.execute("SELECT COUNT(*) FROM tickets WHERE status='open'").fetchone()[0]
        waiting = c.execute(
            "SELECT COUNT(*) FROM tickets t WHERE t.status<>'closed' AND"
            " (SELECT sender FROM ticket_msgs m WHERE m.ticket_id=t.id ORDER BY m.id DESC LIMIT 1)='user' AND"
            " (SELECT created_at FROM ticket_msgs m WHERE m.ticket_id=t.id ORDER BY m.id DESC LIMIT 1)<?", (now - sla,)).fetchone()[0]
        firsts = [r[0] for r in c.execute(
            "SELECT (SELECT MIN(m.created_at) FROM ticket_msgs m WHERE m.ticket_id=t.id AND m.sender='staff') - t.created_at"
            " FROM tickets t WHERE t.created_at>=?", (week,))]
        answered = [x for x in firsts if x is not None and x >= 0]
        closed = c.execute("SELECT COUNT(*) FROM tickets WHERE status='closed' AND updated_at>=?", (week,)).fetchone()[0]
    return {"open": opened, "waiting": waiting, "new_week": len(firsts), "closed_week": closed,
            "avg_first": int(sum(answered) / len(answered)) if answered else None,
            "within_hour": round(100 * sum(1 for x in answered if x <= 3600) / len(firsts)) if firsts else None}


def customer_360(user_ids):
    """ملف العميل لفريق الدعم: الباقة وانتهاؤها · البوتات وحالتها · الرصيد · آخر دفعة · تذاكره — بلا أسرار."""
    ids = [int(x) for x in set(user_ids) if x]
    if not ids:
        return {}
    q = ",".join("?" * len(ids))
    out = {}
    with get_conn() as c:
        for r in c.execute(f"SELECT u.id, u.username, u.email, u.email_verified_at, u.created_at, u.is_blocked,"
                           f" s.plan, s.status sub_status, s.expires_at FROM users u LEFT JOIN subscriptions s ON s.user_id=u.id"
                           f" WHERE u.id IN ({q})", ids):
            out[r["id"]] = {"username": r["username"], "email": r["email"] or "", "verified": bool(r["email_verified_at"]),
                            "since": r["created_at"], "blocked": bool(r["is_blocked"]),
                            "plan": r["plan"] if r["sub_status"] == "active" else "free", "expires": r["expires_at"],
                            "bots": [], "tickets": 0, "last_payment": None, "wallet": 0}
        for r in c.execute(f"SELECT owner_id, name, channel, is_active FROM bots WHERE owner_id IN ({q}) ORDER BY id", ids):
            if r["owner_id"] in out:
                out[r["owner_id"]]["bots"].append({"name": r["name"], "channel": r["channel"] or "telegram", "active": bool(r["is_active"])})
        for r in c.execute(f"SELECT user_id, COUNT(*) n FROM tickets WHERE user_id IN ({q}) GROUP BY user_id", ids):
            out[r["user_id"]]["tickets"] = r["n"]
        for r in c.execute(f"SELECT user_id, plan, amount, status, created_at FROM payments WHERE id IN"
                           f" (SELECT MAX(id) FROM payments WHERE user_id IN ({q}) GROUP BY user_id)", ids):
            out[r["user_id"]]["last_payment"] = {"plan": r["plan"], "amount": r["amount"], "status": r["status"], "at": r["created_at"]}
    for i in out:
        try:
            out[i]["wallet"] = wallet_balance(i)
        except Exception:
            pass
    return out


def admin_revenue_stats(prices, now=None):
    """للأدمن: الإيراد الشهري المتكرّر (تقديري بسعر الباقة الشهري) · اشتراكات جديدة وانتهت (30 يوماً) · معتمد 30 يوماً."""
    now = int(now or time.time())
    month = now - 30 * 86400
    with get_conn() as c:
        active = c.execute("SELECT plan, COUNT(*) n FROM subscriptions WHERE status='active' AND plan<>'free'"
                           " AND (expires_at IS NULL OR expires_at>?) GROUP BY plan", (now,)).fetchall()
        new = c.execute("SELECT COUNT(DISTINCT user_id) FROM payments WHERE status='approved' AND decided_at>=?", (month,)).fetchone()[0]
        ended = c.execute("SELECT COUNT(*) FROM subscriptions WHERE plan<>'free' AND expires_at BETWEEN ? AND ?", (month, now)).fetchone()[0]
        approved = c.execute("SELECT COALESCE(SUM(amount),0) FROM payments WHERE status='approved' AND decided_at>=?", (month,)).fetchone()[0]
        stale = c.execute("SELECT COUNT(*) FROM payments WHERE status='pending' AND created_at<?", (now - 86400,)).fetchone()[0]
    mrr = sum((prices.get(r["plan"]) or 0) * r["n"] for r in active)
    return {"mrr": round(mrr, 2), "active_paid": sum(r["n"] for r in active), "new_30": new, "ended_30": ended,
            "approved_30": round(approved or 0, 2), "stale_payments": stale,
            "by_plan": {r["plan"]: r["n"] for r in active}}


def owner_signals(owner_id, now=None):
    """ما تُبنى عليه اقتراحات الرئيسية الذكية — أعداد فقط."""
    now = int(now or time.time())
    with get_conn() as c:
        bots = [dict(r) for r in c.execute("SELECT id, channel FROM bots WHERE owner_id=?", (owner_id,))]
        ids = [b["id"] for b in bots] or [0]
        q = ",".join("?" * len(ids))
        one = lambda sql, *a: c.execute(sql, (*ids, *a)).fetchone()[0] or 0
        return {
            "channels": sorted({b["channel"] or "telegram" for b in bots}),
            "dormant": one(f"SELECT COUNT(*) FROM bot_users WHERE bot_id IN ({q}) AND opted_out=0 AND last_in_at<?", now - 30 * 86400),
            "leads_week": one(f"SELECT COUNT(*) FROM leads WHERE bot_id IN ({q}) AND created_at>=?", now - 7 * 86400),
            "leads_prev": one(f"SELECT COUNT(*) FROM leads WHERE bot_id IN ({q}) AND created_at>=? AND created_at<?",
                              now - 14 * 86400, now - 7 * 86400),
            "stale_pay": c.execute("SELECT COUNT(*) FROM chat_payments WHERE owner_id=? AND status='pending' AND created_at<? AND expires_at>?",
                                   (owner_id, now - 2 * 3600, now)).fetchone()[0],
            "teams": c.execute("SELECT COUNT(*) FROM inbox_teams WHERE owner_id=?", (owner_id,)).fetchone()[0],
            "integrations": c.execute("SELECT COUNT(*) FROM integrations WHERE owner_id=?", (owner_id,)).fetchone()[0],
            "sequences": c.execute("SELECT COUNT(*) FROM sequences WHERE owner_id=?", (owner_id,)).fetchone()[0],
            "pay_ready": bool(c.execute("SELECT 1 FROM settings WHERE user_id=? AND key='pay_gateway' AND value<>''", (owner_id,)).fetchone()),
        }


def recent_signups(limit=6):
    """أحدث المسجّلين للأدمن والدعم — بلا كلمات مرور ولا أسرار."""
    with get_conn() as c:
        return [dict(r) for r in c.execute(
            "SELECT u.id, u.username, u.created_at, u.email_verified_at IS NOT NULL verified,"
            " COALESCE((SELECT s.plan FROM subscriptions s WHERE s.user_id=u.id AND s.status='active'), 'free') plan,"
            " (SELECT COUNT(*) FROM bots b WHERE b.owner_id=u.id) bots"
            " FROM users u ORDER BY u.id DESC LIMIT ?", (limit,))]


# ════════════════════════ الرئيسية — أرقام اليوم لصاحب الحساب ════════════════════════
def assistant_bot_stats(owner_id, now=None, limit=10):
    """تقرير «مساعد BotYalla» لكل بوت (7 أيام و30 يوماً) — أعداد فقط، بلا بيانات عملاء."""
    now = int(now or time.time())
    w, m = now - 7 * 86400, now - 30 * 86400
    out = []
    with get_conn() as c:
        for b in c.execute("SELECT id, name, channel, template, is_active FROM bots WHERE owner_id=? ORDER BY id LIMIT ?",
                           (owner_id, limit)).fetchall():
            bid = b["id"]
            one = lambda q, *a: c.execute(q, (bid, *a)).fetchone()[0] or 0
            out.append({
                "bot": b["name"], "channel": b["channel"] or "telegram", "template": b["template"],
                "active": bool(b["is_active"]),
                "subscribers": one("SELECT COUNT(*) FROM bot_users WHERE bot_id=?"),
                "new_subscribers_7d": one("SELECT COUNT(*) FROM bot_users WHERE bot_id=? AND created_at>=?", w),
                "messages_in_7d": one("SELECT COUNT(*) FROM messages WHERE bot_id=? AND direction='in' AND created_at>=?", w),
                "messages_out_7d": one("SELECT COUNT(*) FROM messages WHERE bot_id=? AND direction='out' AND created_at>=?", w),
                "leads_7d": one("SELECT COUNT(*) FROM leads WHERE bot_id=? AND created_at>=?", w),
                "leads_30d": one("SELECT COUNT(*) FROM leads WHERE bot_id=? AND created_at>=?", m),
                "orders_30d": one("SELECT COUNT(*) FROM orders WHERE bot_id=? AND created_at>=?", m),
                "orders_total_30d": round(one("SELECT SUM(total) FROM orders WHERE bot_id=? AND created_at>=?", m), 2),
                "bookings_30d": one("SELECT COUNT(*) FROM bookings WHERE bot_id=? AND created_at>=?", m),
                "human_chats_open": one("SELECT COUNT(*) FROM conversations WHERE bot_id=? AND mode='human'"),
            })
    return out


def home_metrics(owner_id, tz=3 * 3600, now=None):
    """أرقام «مركز القيادة» في استعلامات قليلة مفهرسة. `tz` إزاحة المنطقة (السعودية افتراضياً) لحدود اليوم."""
    now = int(now or time.time())
    day0 = (now + tz) // 86400 * 86400 - tz
    week0, span0 = now - 7 * 86400, day0 - 13 * 86400
    with get_conn() as c:
        bots = [r[0] for r in c.execute("SELECT id FROM bots WHERE owner_id=?", (owner_id,))]
        if not bots:
            return {"bots": 0}
        q = ",".join("?" * len(bots))
        one = lambda sql, *a: c.execute(sql, (*bots, *a)).fetchone()[0] or 0
        out = {
            "bots": len(bots),
            "bots_live": one(f"SELECT COUNT(*) FROM bots WHERE id IN ({q}) AND is_active=1"),
            "msgs_today": one(f"SELECT COUNT(*) FROM messages WHERE bot_id IN ({q}) AND direction='in' AND created_at>=?", day0),
            "chats_today": one(f"SELECT COUNT(DISTINCT bot_id || '|' || peer) FROM messages WHERE bot_id IN ({q})"
                               " AND direction='in' AND created_at>=?", day0),
            "leads_week": one(f"SELECT COUNT(*) FROM leads WHERE bot_id IN ({q}) AND created_at>=?", week0),
            "subscribers": one(f"SELECT COUNT(*) FROM bot_users WHERE bot_id IN ({q})"),
            "new_subs_week": one(f"SELECT COUNT(*) FROM bot_users WHERE bot_id IN ({q}) AND created_at>=?", week0),
        }
        out["contacts_week"] = c.execute("SELECT COUNT(*) FROM contacts WHERE owner_id=? AND created_at>=?",
                                         (owner_id, week0)).fetchone()[0]
        out["paid_week"] = [dict(r) for r in c.execute(
            "SELECT currency, SUM(amount) total, COUNT(*) n FROM chat_payments WHERE owner_id=? AND status='paid'"
            " AND paid_at>=? GROUP BY currency ORDER BY total DESC", (owner_id, week0))]
        out["pay_pending"] = c.execute("SELECT COUNT(*) FROM chat_payments WHERE owner_id=? AND status='pending'"
                                       " AND expires_at>?", (owner_id, now)).fetchone()[0]
        out["integ_failed"] = c.execute(
            "SELECT COUNT(*) FROM integration_events e JOIN integrations i ON i.id=e.integration_id"
            " WHERE i.owner_id=? AND e.status='failed' AND e.created_at>=?", (owner_id, now - 86400)).fetchone()[0]
        # نشاط 14 يوماً: الوارد والصادر لكل يوم بتوقيت الحساب
        series = {}
        for d, direction, n in c.execute(
                f"SELECT (created_at + ?) / 86400 d, direction, COUNT(*) FROM messages WHERE bot_id IN ({q})"
                " AND created_at>=? AND direction IN ('in','out') GROUP BY d, direction", (tz, *bots, span0)):
            series.setdefault(d, {"in": 0, "out": 0})[direction] = n
        first = (span0 + tz) // 86400
        out["activity"] = [{"d": (first + i) * 86400 - tz, **series.get(first + i, {"in": 0, "out": 0})} for i in range(14)]
    return out


def comment_recent(bot_id, limit=30):
    with get_conn() as c:
        return [dict(r) for r in c.execute(
            "SELECT id, post_id, user_name, text, rule_id, public_ok, private_ok, error, created_at FROM comment_actions"
            " WHERE bot_id=? ORDER BY id DESC LIMIT ?", (bot_id, limit))]
