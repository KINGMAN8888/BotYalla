"""BotYalla — قاعدة البيانات (SQLite).
جداول: users (لوحة التحكم)، bots، bot_users (مشتركو كل بوت للبث)،
leads، orders، bookings، events (للتحليلات)."""
import sqlite3, json, os, time, logging
from contextlib import contextmanager

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
    # فهرس جزئي: الإيميل فريد إن وُجد، والحسابات القديمة بلا إيميل (NULL) لا تتعارض.
    c.execute("CREATE UNIQUE INDEX IF NOT EXISTS ix_users_email ON users(email) WHERE email IS NOT NULL")
    # أول مستخدم = admin دائماً
    c.execute("UPDATE users SET role='admin' WHERE id=1 AND role<>'admin'")

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
            token TEXT NOT NULL UNIQUE,
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
        """)
        _migrate(c)

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
        cur = c.execute("INSERT INTO bots(owner_id,name,token,template,config_json,is_active,created_at,channel)"
                        " VALUES(?,?,?,?,?,0,?,?)",
                        (owner_id, name, token.strip(), template,
                         json.dumps(config, ensure_ascii=False), int(time.time()), channel))
        return cur.lastrowid

def list_bots(owner_id):
    with get_conn() as c:
        rows = c.execute("SELECT * FROM bots WHERE owner_id=? ORDER BY created_at DESC, id DESC",
                         (owner_id,)).fetchall()
        return [dict(r) for r in rows]

def get_bot(bot_id, owner_id=None):
    with get_conn() as c:
        if owner_id is None:
            r = c.execute("SELECT * FROM bots WHERE id=?", (bot_id,)).fetchone()
        else:
            r = c.execute("SELECT * FROM bots WHERE id=? AND owner_id=?", (bot_id, owner_id)).fetchone()
        return dict(r) if r else None

def all_active_bots():
    with get_conn() as c:
        return [dict(r) for r in c.execute("SELECT * FROM bots WHERE is_active=1").fetchall()]

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

def list_bot_user_ids(bot_id):
    with get_conn() as c:
        return [r[0] for r in c.execute("SELECT tg_user_id FROM bot_users WHERE bot_id=?", (bot_id,)).fetchall()]

def list_bot_peers(bot_id, within_seconds=None):
    """يرجّع peers المشتركين. within_seconds يقصرها على من راسل البوت مؤخراً."""
    q = "SELECT peer FROM bot_users WHERE bot_id=? AND peer IS NOT NULL"
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

# ---------- leads / orders / bookings ----------
def add_lead(bot_id, tg_user_id, data: dict):
    with get_conn() as c:
        cur = c.execute("INSERT INTO leads(bot_id,tg_user_id,data_json,created_at) VALUES(?,?,?,?)",
                        (bot_id, tg_user_id, json.dumps(data, ensure_ascii=False), int(time.time())))
        lead_id = cur.lastrowid
    log_event(bot_id, "lead")
    return lead_id

def list_leads(bot_id):
    with get_conn() as c:
        rows = c.execute("SELECT * FROM leads WHERE bot_id=? ORDER BY created_at DESC, id DESC LIMIT 300",
                         (bot_id,)).fetchall()
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

def add_order(bot_id, tg_user_id, customer, phone, address, items, total):
    with get_conn() as c:
        c.execute("INSERT INTO orders(bot_id,tg_user_id,customer,phone,address,items_json,total,created_at)"
                  " VALUES(?,?,?,?,?,?,?,?)",
                  (bot_id, tg_user_id, customer, phone, address,
                   json.dumps(items, ensure_ascii=False), total, int(time.time())))
    log_event(bot_id, "order", total)

def list_orders(bot_id):
    with get_conn() as c:
        rows = c.execute("SELECT * FROM orders WHERE bot_id=? ORDER BY created_at DESC, id DESC LIMIT 300",
                         (bot_id,)).fetchall()
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

def list_bookings(bot_id):
    with get_conn() as c:
        rows = c.execute("SELECT * FROM bookings WHERE bot_id=? ORDER BY slot DESC, id DESC LIMIT 300",
                         (bot_id,)).fetchall()
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
    with get_conn() as c:
        rows = c.execute(
            "SELECT day, kind, COUNT(*) cnt, COALESCE(SUM(value),0) val "
            "FROM events WHERE bot_id=? GROUP BY day, kind", (bot_id,)).fetchall()
    import datetime
    today = datetime.date.today()
    labels = [(today - datetime.timedelta(days=i)).isoformat() for i in range(days-1, -1, -1)]
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

def credit_referral(referred_user_id, payment_id, amount, conn=None):
    """يحتسب العمولة عند اعتماد أول دفعة للمُحال. يرجّع (affiliate_user_id, commission)
    أو None. ذرّي: يُحدّث فقط الصف الذي لم يُحوَّل بعد."""
    with _conn_or(conn) as c:
        r = c.execute("SELECT r.id, r.affiliate_user_id, a.rate_pct, a.is_active "
                      "FROM referrals r JOIN affiliates a ON a.user_id=r.affiliate_user_id "
                      "WHERE r.referred_user_id=? AND r.converted_at IS NULL",
                      (referred_user_id,)).fetchone()
        if not r or not r["is_active"]:
            return None
        commission = round(float(amount) * float(r["rate_pct"]) / 100.0, 2)
        cur = c.execute("UPDATE referrals SET payment_id=?, commission=?, converted_at=? "
                        "WHERE id=? AND converted_at IS NULL",
                        (payment_id, commission, int(time.time()), r["id"]))
        if cur.rowcount != 1:
            return None
        c.execute("UPDATE affiliates SET total_earned=total_earned+? WHERE user_id=?",
                  (commission, r["affiliate_user_id"]))
        return (r["affiliate_user_id"], commission)

def affiliate_summary(user_id):
    with get_conn() as c:
        r = c.execute("SELECT COUNT(*) signups, "
                      "COALESCE(SUM(CASE WHEN converted_at IS NOT NULL THEN 1 ELSE 0 END),0) conversions "
                      "FROM referrals WHERE affiliate_user_id=?", (user_id,)).fetchone()
        return {"signups": r["signups"], "conversions": r["conversions"]}

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
            SELECT s.user_id, u.username, s.plan, s.expires_at,
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
            SELECT s.user_id, u.username, s.plan, s.expires_at,
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
    with get_conn() as c:
        r = c.execute("SELECT * FROM bots WHERE token=?", (token,)).fetchone()
        return dict(r) if r else None

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
    """ملفات وصلت ولم يكتمل الفلو الذي كانت جزءاً منه — لا يشير إليها شيء."""
    with get_conn() as c:
        rows = c.execute("SELECT id, fname FROM media WHERE lead_id IS NULL AND created_at < ?",
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
