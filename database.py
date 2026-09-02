"""BotYalla — قاعدة البيانات (SQLite).
جداول: users (لوحة التحكم)، bots، bot_users (مشتركو كل بوت للبث)،
leads، orders، bookings، events (للتحليلات)."""
import sqlite3, json, time
from contextlib import contextmanager

DB_PATH = "botyalla.db"

@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()

def _migrate(c):
    cols = {r[1] for r in c.execute("PRAGMA table_info(users)").fetchall()}
    if "role" not in cols:
        c.execute("ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT 'user'")
    if "is_blocked" not in cols:
        c.execute("ALTER TABLE users ADD COLUMN is_blocked INTEGER NOT NULL DEFAULT 0")
    # أول مستخدم = admin دائماً
    c.execute("UPDATE users SET role='admin' WHERE id=1 AND role<>'admin'")

def init_db():
    with get_conn() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS users(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            pw_hash  TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'user',       -- admin | support | user
            is_blocked INTEGER NOT NULL DEFAULT 0,
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
        CREATE TABLE IF NOT EXISTS events(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bot_id INTEGER NOT NULL,
            kind TEXT NOT NULL,                   -- start | lead | order | booking
            value REAL DEFAULT 0,
            day TEXT NOT NULL,                    -- 'YYYY-MM-DD'
            created_at INTEGER NOT NULL,
            FOREIGN KEY(bot_id) REFERENCES bots(id) ON DELETE CASCADE
        );
        """)
        _migrate(c)

# ---------- users ----------
def create_user(username, pw_hash):
    with get_conn() as c:
        n = c.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        role = "admin" if n == 0 else "user"   # أول مستخدم = admin
        cur = c.execute("INSERT INTO users(username,pw_hash,role,created_at) VALUES(?,?,?,?)",
                        (username, pw_hash, role, int(time.time())))
        return cur.lastrowid

def get_user_by_name(username):
    with get_conn() as c:
        r = c.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
        return dict(r) if r else None

def count_users():
    with get_conn() as c:
        return c.execute("SELECT COUNT(*) FROM users").fetchone()[0]

# ---------- bots ----------
def create_bot(owner_id, name, token, template, config):
    with get_conn() as c:
        cur = c.execute("INSERT INTO bots(owner_id,name,token,template,config_json,is_active,created_at)"
                        " VALUES(?,?,?,?,?,0,?)",
                        (owner_id, name, token.strip(), template,
                         json.dumps(config, ensure_ascii=False), int(time.time())))
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
def add_bot_user(bot_id, tg_user_id, first_name):
    with get_conn() as c:
        c.execute("INSERT OR IGNORE INTO bot_users(bot_id,tg_user_id,first_name,created_at)"
                  " VALUES(?,?,?,?)", (bot_id, tg_user_id, first_name, int(time.time())))

def list_bot_user_ids(bot_id):
    with get_conn() as c:
        return [r[0] for r in c.execute("SELECT tg_user_id FROM bot_users WHERE bot_id=?", (bot_id,)).fetchall()]

def _day():
    return time.strftime("%Y-%m-%d")

def log_event(bot_id, kind, value=0):
    with get_conn() as c:
        c.execute("INSERT INTO events(bot_id,kind,value,day,created_at) VALUES(?,?,?,?,?)",
                  (bot_id, kind, value, _day(), int(time.time())))

# ---------- leads / orders / bookings ----------
def add_lead(bot_id, tg_user_id, data: dict):
    with get_conn() as c:
        c.execute("INSERT INTO leads(bot_id,tg_user_id,data_json,created_at) VALUES(?,?,?,?)",
                  (bot_id, tg_user_id, json.dumps(data, ensure_ascii=False), int(time.time())))
    log_event(bot_id, "lead")

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
                    "started_at": None, "expires_at": None}
        d = dict(r)
        # انتهاء تلقائي
        if d["plan"] != "free" and d["expires_at"] and d["expires_at"] < int(time.time()):
            d["status"] = "expired"
        return d

def activate_subscription(user_id, plan, days=30):
    """يفعّل الاشتراك ويرجّع تاريخ الانتهاء.
    التجديد المبكر على **نفس** الباقة يُضاف إلى المتبقّي بدل أن يلغيه (العميل
    دفع عن 30 يوماً فيأخذها كاملة). تغيير الباقة أو اشتراك منتهٍ يبدأ من الآن."""
    now = int(time.time())
    base, started = now, now
    if plan != "free":
        with get_conn() as c:
            r = c.execute("SELECT plan, started_at, expires_at FROM subscriptions WHERE user_id=?",
                          (user_id,)).fetchone()
        if r and r["plan"] == plan and r["expires_at"] and r["expires_at"] > now:
            base = r["expires_at"]                      # مدّد من نهاية الفترة الحالية
            started = r["started_at"] or now            # واحتفظ ببداية الاشتراك الأصلية
    exp = base + days * 86400
    with get_conn() as c:
        c.execute("INSERT INTO subscriptions(user_id,plan,status,started_at,expires_at) VALUES(?,?, 'active',?,?) "
                  "ON CONFLICT(user_id) DO UPDATE SET plan=excluded.plan, status='active', "
                  "started_at=excluded.started_at, expires_at=excluded.expires_at",
                  (user_id, plan, started, exp))
    return exp

# ---------- payments ----------
def create_payment(user_id, plan, method, amount, ref, screenshot, img_hash, auto_check):
    with get_conn() as c:
        cur = c.execute("INSERT INTO payments(user_id,plan,method,amount,ref,screenshot,img_hash,auto_check,status,created_at) "
                        "VALUES(?,?,?,?,?,?,?,?, 'pending', ?)",
                        (user_id, plan, method, amount, ref, screenshot, img_hash, auto_check, int(time.time())))
        return cur.lastrowid

def get_payment(pid):
    with get_conn() as c:
        r = c.execute("SELECT * FROM payments WHERE id=?", (pid,)).fetchone()
        return dict(r) if r else None

def set_payment_msg(pid, msg_id):
    with get_conn() as c:
        c.execute("UPDATE payments SET admin_msg_id=? WHERE id=?", (msg_id, pid))

def decide_payment(pid, status):
    """يحدّث حالة الدفعة إن كانت لسه pending. يرجّع dict الدفعة أو None لو سبق البتّ فيها.
    **ذرّي:** التحديث المشروط (`AND status='pending'`) هو القفل نفسه — SQLite يسلسل
    الكتابة، فطلبان متزامنان (gunicorn threads=4 / زر تليجرام + الويب معاً) لا يمكن
    أن ينجحا معاً؛ الثاني يجد rowcount=0 فيرجّع None ولا يُفعَّل الاشتراك مرتين."""
    with get_conn() as c:
        cur = c.execute("UPDATE payments SET status=?, decided_at=? WHERE id=? AND status='pending'",
                        (status, int(time.time()), pid))
        if cur.rowcount != 1:
            return None
        r = c.execute("SELECT * FROM payments WHERE id=?", (pid,)).fetchone()
        return dict(r) if r else None

def finalize_payment(pid, status):
    """قرار نهائي مشترك (ويب/بوت): يبتّ الدفعة ويفعّل الاشتراك عند الموافقة. ذرّي."""
    row = decide_payment(pid, status)
    if not row:
        return None
    if status == "approved":
        activate_subscription(row["user_id"], row["plan"], days=30)
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
