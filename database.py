"""BotYalla — قاعدة البيانات (SQLite).
جداول: users (لوحة التحكم)، bots، bot_users (مشتركو كل بوت للبث)،
leads، orders، bookings، events (للتحليلات)."""
import sqlite3, json, os, time, logging, hmac, hashlib
from contextlib import contextmanager

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
    for col, ddl in (("phone", "TEXT"), ("phone_verified_at", "INTEGER"),
                     ("email_verified_at", "INTEGER"), ("verify_required", "INTEGER NOT NULL DEFAULT 0"),
                     ("age", "INTEGER"), ("entity_type", "TEXT")):
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

def set_optin(bot_id, peer, yes=True):
    """موافقة العميل الصريحة على استقبال العروض (أو سحبها)."""
    with get_conn() as c:
        c.execute("UPDATE bot_users SET optin_at=?, opted_out=CASE WHEN ? THEN 0 ELSE opted_out END"
                  " WHERE bot_id=? AND peer=?",
                  (int(time.time()) if yes else None, 1 if yes else 0, bot_id, peer))

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

def add_order(bot_id, tg_user_id, customer, phone, address, items, total, pay_status=None):
    """يرجّع رقم الطلب — تحصيل المدفوعات يربط به إيصال العميل."""
    with get_conn() as c:
        cur = c.execute("INSERT INTO orders(bot_id,tg_user_id,customer,phone,address,items_json,total,"
                        "created_at,pay_status) VALUES(?,?,?,?,?,?,?,?,?)",
                        (bot_id, tg_user_id, customer, phone, address,
                         json.dumps(items, ensure_ascii=False), total, int(time.time()), pay_status))
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
            # إضافة «تحصيل المدفوعات» لبوت بعينه — 30 يوماً تُمدّ من انتهائها لو ما زالت
            # سارية. داخل نفس المعاملة: لا دفعة معتمدة بلا إضافة مفعّلة.
            bid = addon_bot_id(row["plan"])
            if c.execute("SELECT 1 FROM bots WHERE id=?", (bid,)).fetchone():
                row["addon_expires"] = extend_addon(bid, "pay", days=30, conn=c)
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
        return tid

def add_ticket_msg(tid, sender, body, via="web"):
    """رسالة العميل تفتح التذكرة، ورد الفريق يجعلها «اتردّ عليها»."""
    now = int(time.time())
    with get_conn() as c:
        c.execute("INSERT INTO ticket_msgs(ticket_id,sender,body,via,created_at) VALUES(?,?,?,?,?)",
                  (tid, sender, body, via, now))
        c.execute("UPDATE tickets SET status=?, updated_at=? WHERE id=?",
                  ("answered" if sender == "staff" else "open", now, tid))

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

def log_message(bot_id, peer, direction, sender, text="", kind="text", media_id=None, name=None):
    """يسجّل رسالة ويحدّث ملخّص المحادثة في معاملة واحدة.
    الوارد يزيد عدّاد غير المقروء؛ ردّ صاحب النشاط يصفّره."""
    now = int(time.time())
    text = (text or "")[:MSG_TEXT_MAX]
    with get_conn() as c:
        c.execute("INSERT INTO messages(bot_id,peer,direction,sender,kind,text,media_id,created_at)"
                  " VALUES(?,?,?,?,?,?,?,?)",
                  (bot_id, peer, direction, sender, kind, text, media_id, now))
        preview = text[:140] if text else ("📎" if kind == "media" else "")
        c.execute("INSERT INTO conversations(bot_id,peer,name,unread,last_text,last_at)"
                  " VALUES(?,?,?,?,?,?)"
                  " ON CONFLICT(bot_id,peer) DO UPDATE SET"
                  " name=COALESCE(NULLIF(excluded.name,''), conversations.name),"
                  " unread=CASE WHEN ?='in' THEN conversations.unread+1"
                  "             WHEN ?='human' THEN 0 ELSE conversations.unread END,"
                  " last_text=excluded.last_text, last_at=excluded.last_at",
                  (bot_id, peer, name or "", 1 if direction == "in" else 0, preview, now,
                   direction, sender))


def get_conversation(bot_id, peer):
    with get_conn() as c:
        r = c.execute("SELECT * FROM conversations WHERE bot_id=? AND peer=?",
                      (bot_id, peer)).fetchone()
        return dict(r) if r else None


def list_conversations(bot_id, limit=200):
    with get_conn() as c:
        rows = c.execute("SELECT * FROM conversations WHERE bot_id=? ORDER BY last_at DESC LIMIT ?",
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
        rows = c.execute("SELECT direction, sender, text FROM messages WHERE bot_id=? AND peer=? "
                         "AND text<>'' ORDER BY id DESC LIMIT ?", (bot_id, peer, limit)).fetchall()
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


# ---------- تحصيل مدفوعات عملاء البوت (إضافة مدفوعة لكل بوت) ----------
# شراء الإضافة دفعة منصة عادية (إيصال + موافقة الأدمن) بـ plan = __addon_pay__:<bot_id> —
# كشحن المحفظة: `plans.is_sellable` ترفضه، و`finalize_payment` تفعّل الإضافة لذلك البوت.
ADDON_PAY = "__addon_pay__"


def addon_plan(bot_id):
    return f"{ADDON_PAY}:{int(bot_id)}"


def addon_bot_id(plan):
    if isinstance(plan, str) and plan.startswith(ADDON_PAY + ":"):
        try:
            return int(plan.split(":", 1)[1])
        except ValueError:
            return None
    return None


def addon_plans_in_payments():
    with get_conn() as c:
        return [r[0] for r in c.execute("SELECT DISTINCT plan FROM payments WHERE substr(plan,1,?)=?",
                                        (len(ADDON_PAY) + 1, ADDON_PAY + ":")).fetchall()]


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
