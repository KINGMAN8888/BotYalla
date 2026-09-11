"""اختبارات تسجيل الأخطاء (LAUNCH_READINESS L-03).

معيار القبول: استثناء مُصطنع في أي مسار يظهر في ملف السجل **ويصل إشعاره
للأدمن** — مرة واحدة لا مع كل تكرار.

    python tests/test_logging.py
"""
import logging, os, secrets, sys, tempfile, unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_TMPDIR = tempfile.mkdtemp(prefix="botyalla-log-")
os.environ["BOTYALLA_DB"] = os.path.join(_TMPDIR, "test.db")   # قبل استيراد database/app
os.environ["BOTYALLA_UPLOADS"] = os.path.join(_TMPDIR, "uploads")
os.environ["BOTYALLA_LOGS"] = os.path.join(_TMPDIR, "logs")    # لا يُكتب في logs/ الحقيقي
ADMIN_PW = os.environ.setdefault("ADMIN_PASS", f"tst_adm_{secrets.token_hex(8)}")
TEST_PW = f"tst_pw_{secrets.token_hex(8)}"
os.environ["ADMIN_USER"] = "admin"
os.environ["ADMIN_PASS"] = ADMIN_PW

import auth                                # noqa: E402
import database as db                      # noqa: E402
import app as web                          # noqa: E402

LOG_FILE = os.path.join(_TMPDIR, "logs", "botyalla.log")
NOTES = []


def _boom():
    return 1 / 0


# قبل أي طلب — Flask يمنع إضافة مسارات بعد أول طلب
web.app.add_url_rule("/__boom", "boom", _boom)


def _log_text():
    for h in logging.getLogger().handlers:
        h.flush()
    with open(LOG_FILE, encoding="utf-8") as f:
        return f.read()


class LoggingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        web.setup_logging()
        db.init_db()
        web.seed_default_admin()
        web.app.config["TESTING"] = True
        # كالإنتاج: الاستثناء لا ينتشر إلى العميل بل يمرّ بمعالج 500
        web.app.config["PROPAGATE_EXCEPTIONS"] = False
        web.notify_admins = NOTES.append

    def setUp(self):
        NOTES.clear()
        web._err_notified.clear()

    def test_an_unhandled_exception_is_logged_with_its_traceback(self):
        r = web.app.test_client().get("/__boom")
        self.assertEqual(r.status_code, 500)
        text = _log_text()
        self.assertIn("Traceback", text)
        self.assertIn("ZeroDivisionError", text)

    def test_the_admin_is_notified_once_not_per_repeat(self):
        c = web.app.test_client()
        for _ in range(3):
            c.get("/__boom")
        self.assertEqual(len(NOTES), 1, "عطل متكرر لا يُغرق تليجرام")
        self.assertIn("ZeroDivisionError", NOTES[0])
        self.assertIn("/__boom", NOTES[0])

    def test_client_errors_do_not_page_the_admin(self):
        web.app.test_client().get("/no-such-page")
        self.assertEqual(NOTES, [])

    def test_settlements_are_logged_only_after_commit(self):
        uid = db.create_user("payer", auth.hash_password(TEST_PW))
        pid = db.create_payment(uid, "pro", "instapay", 199, "R", "s.png", "H1", "{}")
        db.finalize_payment(pid, "approved")
        self.assertIn(f"payment #{pid} approved user={uid} plan=pro", _log_text())

    def test_setup_is_idempotent(self):
        before = len(logging.getLogger().handlers)
        web.setup_logging()
        self.assertEqual(len(logging.getLogger().handlers), before)

    def test_bot_tokens_in_httpx_request_lines_never_reach_the_file(self):
        """httpx يسجّل رابط كل طلب لتليجرام وفيه توكن البوت."""
        logging.getLogger("httpx").info("HTTP Request: POST https://api.telegram.org/bot123:SECRET/getUpdates")
        self.assertNotIn("123:SECRET", _log_text())


if __name__ == "__main__":
    unittest.main(verbosity=2)
