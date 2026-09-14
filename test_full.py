import os, json, secrets, tempfile, time, shutil, unittest

# بيانات أدمن خاصة بالاختبار — تُضبط **قبل** استيراد app، لأن الوحدة تحمّل ‎.env
# بـ setdefault فالقيمة المضبوطة هنا تسبقه ولا تُقرأ كلمة مرور الإنتاج إطلاقاً.
# تُولَّد ديناميكياً لتجنب تحذيرات أدوات فحص الأمان (Secret Scanners).
ADMIN_USER = os.environ.setdefault("ADMIN_USER", "admin")
ADMIN_PASS = os.environ.setdefault("ADMIN_PASS", f"tst_adm_{secrets.token_hex(8)}")
CLIENT_PW = f"tst_cli_{secrets.token_hex(8)}"
# bootstrap() يفعّل سجل الملف — لا يُكتب في logs/ الحقيقي (على الخادم = سجل الإنتاج)
os.environ.setdefault("BOTYALLA_LOGS", tempfile.mkdtemp(prefix="botyalla-e2e-logs-"))

import database as db
import app as A
import bot_manager
import tg_helpers as tg
import ai_agent

# ==============================================================================
#  BotYalla — End-to-End Market Readiness Test
#  هذا السكربت يختبر التدفق الكامل للنظام بدون تليجرام حقيقي.
#  يحاكي: التسجيل، إنشاء البوتات، الدفع، الاعتماد، والتذكيرات الجديدة.
# ==============================================================================

class BotYallaE2ETest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # استخدام قاعدة بيانات منفصلة للاختبار
        cls.db_path = "test_e2e.db"
        if os.path.exists(cls.db_path):
            os.remove(cls.db_path)
        
        # حفظ مسار القاعدة الأصلي واستبداله
        cls.orig_db = db.DB_PATH
        db.DB_PATH = cls.db_path

        # ومجلد الرفع كذلك — وإلا تراكمت إيصالات وهمية بين الحقيقية في uploads/
        cls._tmp_uploads = tempfile.mkdtemp(prefix="botyalla-e2e-uploads-")
        cls.orig_uploads = A.UPLOAD_DIR
        A.UPLOAD_DIR = cls._tmp_uploads
        
        # إيقاف خيوط مدير البوتات
        bot_manager.manager.start = lambda: None
        
        # تهيئة النظام
        A.bootstrap()
        
        # Stubs لـ تليجرام
        cls.orig_urlopen = tg.urllib.request.urlopen
        class DummyResponse:
            def read(self):
                return b'{"ok": true, "result": {"id": 12345, "first_name": "TestBot", "username": "testbot"}}'
            def __enter__(self):
                return self
            def __exit__(self, exc_type, exc_val, exc_tb):
                pass
        tg.urllib.request.urlopen = lambda *a, **k: DummyResponse()
        tg._tg_post = lambda *a, **k: (True, "OK")
        
        # Stubs لـ AI
        ai_agent._call = lambda *a, **k: json.dumps({"status": "success", "response": "test AI response"})
        
        # Stub لـ التحقق من الصور (تفادي الفشل بسبب dummy file).
        # يجب تغطية المسارين: `validate_bytes` يفحص قبل الكتابة على القرص،
        # و`validate_image` يبقى مستخدماً داخل `auto_check`.
        import payments as pay
        _ok = {"ok": True, "kind": "png", "bytes": 4096}
        cls.orig_validate_image = pay.validate_image
        cls.orig_validate_bytes = pay.validate_bytes
        pay.validate_image = lambda f: dict(_ok)
        pay.validate_bytes = lambda data: dict(_ok)

        cls.client = A.app.test_client()
        cls.app = A.app

    @classmethod
    def tearDownClass(cls):
        import payments as pay
        pay.validate_image = cls.orig_validate_image
        pay.validate_bytes = cls.orig_validate_bytes
        db.DB_PATH = cls.orig_db
        A.UPLOAD_DIR = cls.orig_uploads
        shutil.rmtree(cls._tmp_uploads, ignore_errors=True)
        tg.urllib.request.urlopen = cls.orig_urlopen
        if os.path.exists(cls.db_path):
            os.remove(cls.db_path)

    def _tk(self):
        """يجلب CSRF Token للتصفح"""
        self.client.get("/login")
        with self.client.session_transaction() as s:
            return s.get("_csrf")

    def test_01_public_pages(self):
        """التأكد أن الصفحات العامة (بما فيها القانونية الجديدة) تعمل."""
        for path in ["/", "/terms", "/privacy", "/refund", "/acceptable-use", "/pricing", "/login", "/register"]:
            r = self.client.get(path)
            self.assertEqual(r.status_code, 200, f"{path} should return 200")

    def test_02_registration_and_login(self):
        """اختبار التسجيل والدخول وإنشاء أدمن تلقائياً."""
        # الأدمن (أول مستخدم) يُنشأ تلقائياً في bootstrap
        with db.get_conn() as c:
            admin = c.execute("SELECT * FROM users WHERE username='admin'").fetchone()
            self.assertIsNotNone(admin, "Admin should be created by bootstrap")
        
        # تسجيل عميل جديد
        tk = self._tk()
        r = self.client.post("/register", data={
            "username": "client1",
            "password": CLIENT_PW,
            "csrf_token": tk
        }, follow_redirects=True)
        self.assertEqual(r.status_code, 200)
        self.assertIn(b"client1", r.data) # يجب أن يظهر اسمه في لوحة التحكم

    def test_03_bot_creation(self):
        """اختبار إنشاء بوت جديد (من نوع menu)."""
        self.client.post("/login", data={"username": "client1", "password": CLIENT_PW, "csrf_token": self._tk()})
        tk = self._tk()
        
        # يجب أن يُرفض إذا كانت الباقة مجانية وبلغ الحد (1)
        # لكن هذا أول بوت، فيجب أن يُقبل.
        r = self.client.post("/bot/create", data={
            "name": "MyBot",
            "token": "12345:ABCDEF1234567890",
            "template": "support", # القالب المتاح في PRESET_FLOWS
            "csrf_token": tk
        }, follow_redirects=True)
        self.assertEqual(r.status_code, 200)
        
        # التأكد أنه أُضيف لقاعدة البيانات
        with db.get_conn() as c:
            bot = c.execute("SELECT * FROM bots WHERE name='MyBot'").fetchone()
            all_bots = c.execute("SELECT * FROM bots").fetchall()
            self.assertIsNotNone(bot, f"Bot not created. All bots: {all_bots}\nResponse: {r.data.decode('utf-8')}")
            self.bot_id = bot["id"]
        
        # التأكد أن PRESET_FLOWS حُقنت (لأن support يستخدم فلو افتراضي)
        cfg = json.loads(bot["config_json"])
        self.assertIsNotNone(cfg.get("flow"))
        self.assertIn("steps", cfg["flow"])

    def test_04_payment_and_activation(self):
        """اختبار الدفع، الاعتماد، والتفعيل."""
        self.client.post("/login", data={"username": "client1", "password": CLIENT_PW, "csrf_token": self._tk()})
        
        # محاكاة رفع الدفع
        tk = self._tk()
        with open("dummy_receipt.png", "wb") as f: f.write(b"dummy")
        
        r = self.client.post("/subscribe/merchant", data={
            "method": "instapay",
            "ref": "REF123",
            "screenshot": (open("dummy_receipt.png", "rb"), "receipt.png"),
            "csrf_token": tk
        }, content_type="multipart/form-data", follow_redirects=True)
        
        os.remove("dummy_receipt.png")
        self.assertEqual(r.status_code, 200, r.data.decode('utf-8')) # يرجّع صفحة dashboard مجدداً
        
        # جلب الـ Payment ID
        with db.get_conn() as c:
            pay = c.execute("SELECT * FROM payments WHERE user_id=(SELECT id FROM users WHERE username='client1')").fetchone()
            self.assertIsNotNone(pay, f"Payment not created. Response: {r.data.decode('utf-8')}")
            self.assertEqual(pay["status"], "pending")
            pay_id = pay["id"]
        
        # الآن دخول كـ Admin للاعتماد
        self.client.post("/logout", data={"csrf_token": self._tk()})   # الخروج POST فقط
        self.client.post("/login", data={"username": ADMIN_USER, "password": ADMIN_PASS, "csrf_token": self._tk()})
        # تأكيد نجاح الدخول صراحةً: بدونه يفشل الاختبار لاحقاً عند فحص الباقة
        # برسالة مضلِّلة ('free' != 'merchant') بدل السبب الحقيقي — كلمة مرور خاطئة.
        with self.client.session_transaction() as s:
            self.assertEqual(s.get("role"), "admin", "فشل دخول الأدمن — راجع ADMIN_USER/ADMIN_PASS")

        # البتّ
        r = self.client.post(f"/admin/payments/{pay_id}/approve", data={"csrf_token": self._tk()}, follow_redirects=True)
        self.assertEqual(r.status_code, 200) # يرجّع صفحة admin_payments
        
        # التحقق من الاشتراك
        sub = db.get_subscription(pay["user_id"])
        self.assertEqual(sub["plan"], "merchant")
        self.assertEqual(sub["status"], "active")

    def test_05_subscription_reminders(self):
        """اختبار منطق تذكيرات الاشتراك الذي أضفناه حديثاً."""
        with db.get_conn() as c:
            u = c.execute("SELECT id FROM users WHERE username='client1'").fetchone()
            uid = u["id"]
        
        # 1. دفع الاشتراك ليقترب من الانتهاء (بعد يومين)
        now = int(time.time())
        exp = now + (2 * 86400)
        with db.get_conn() as c:
            c.execute("UPDATE subscriptions SET expires_at=? WHERE user_id=?", (exp, uid))
        
        # جلب الاشتراكات التي تنتهي خلال 3 أيام
        expiring = db.expiring_subscriptions(3)
        self.assertEqual(len(expiring), 1)
        self.assertEqual(expiring[0]["user_id"], uid)
        
        # 2. تسجيل تذكير والتأكد أنه لا يتكرر
        ok1 = db.log_reminder(uid, "pre3")
        ok2 = db.log_reminder(uid, "pre3")
        self.assertTrue(ok1)
        self.assertFalse(ok2, "Should not log duplicate reminders")
        self.assertTrue(db.reminder_sent(uid, "pre3"))
        
        # 3. التأكد من مسح التذكيرات عند التجديد
        db.activate_subscription(uid, "merchant", days=30)
        self.assertFalse(db.reminder_sent(uid, "pre3"), "Reminders should be cleared after renewal")

if __name__ == "__main__":
    unittest.main()
