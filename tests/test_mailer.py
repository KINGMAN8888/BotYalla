"""اختبارات mailer.py — بنية الإيميل (LAUNCH_READINESS L-04).

الثابت الأهم: **لا ترمي أي دالة استثناءً أبداً.** الإيميل ليس مساراً حرجاً،
وفشل SMTP يجب ألا يُسقط تسجيلاً ولا تسوية دفعة.

    python tests/test_mailer.py
"""
import os, sys, tempfile, unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_TMPDIR = tempfile.mkdtemp(prefix="botyalla-mail-")
os.environ["BOTYALLA_DB"] = os.path.join(_TMPDIR, "test.db")   # قبل استيراد database
os.environ["BOTYALLA_UPLOADS"] = _TMPDIR

import mailer                              # noqa: E402

SENT = []


class FakeSMTP:
    """بديل smtplib.SMTP يسجّل ما أُرسل ولا يلمس الشبكة."""
    fail = None

    def __init__(self, host, port, timeout=None, context=None):
        if FakeSMTP.fail:
            raise FakeSMTP.fail
        self.host, self.port, self.tls, self.auth = host, port, False, None

    def __enter__(self): return self
    def __exit__(self, *a): return False
    def starttls(self, context=None): self.tls = True
    def login(self, u, p): self.auth = (u, p)
    def send_message(self, msg): SENT.append((self, msg))


class MailerTests(unittest.TestCase):
    def setUp(self):
        SENT.clear()
        FakeSMTP.fail = None
        mailer._sent.clear()
        self._orig = (mailer.smtplib.SMTP, mailer.smtplib.SMTP_SSL)
        mailer.smtplib.SMTP = FakeSMTP
        mailer.smtplib.SMTP_SSL = FakeSMTP
        for k, v in {"SMTP_HOST": "smtp.test", "SMTP_PORT": "587", "SMTP_USER": "bot",
                     "SMTP_PASS": "pw", "SMTP_FROM": "BotYalla <no-reply@botyalla.test>",
                     "SMTP_TLS": "starttls"}.items():
            os.environ[k] = v

    def tearDown(self):
        mailer.smtplib.SMTP, mailer.smtplib.SMTP_SSL = self._orig

    def test_a_message_is_sent_with_html_and_text_parts(self):
        self.assertTrue(mailer.send_mail("a@b.co", "Hi", "<p>hi</p>", "hi"))
        server, msg = SENT[0]
        self.assertEqual((msg["To"], msg["Subject"]), ("a@b.co", "Hi"))
        self.assertTrue(server.tls, "STARTTLS يجب أن يُفعَّل افتراضياً")
        self.assertEqual(server.auth, ("bot", "pw"))
        kinds = [p.get_content_type() for p in msg.iter_parts()]
        self.assertEqual(kinds, ["text/plain", "text/html"])

    def test_nothing_is_sent_when_smtp_is_not_configured(self):
        os.environ["SMTP_HOST"] = ""
        self.assertFalse(mailer.send_mail("a@b.co", "Hi", "<p>hi</p>"))
        self.assertEqual(SENT, [])

    def test_an_smtp_failure_never_raises(self):
        """جوهر best-effort: الخادم لا يستجيب ⇒ False لا استثناء."""
        FakeSMTP.fail = ConnectionRefusedError("down")
        self.assertFalse(mailer.send_mail("a@b.co", "Hi", "<p>hi</p>"))

    def test_header_injection_is_refused(self):
        for bad in ("a@b.co\nBcc: x@y.co", "a@b.co\r\nX: y", "a@b.co, c@d.co", "not-an-email", ""):
            self.assertFalse(mailer.send_mail(bad, "Hi", "<p>hi</p>"), repr(bad))
        self.assertEqual(SENT, [])

    def test_each_address_is_rate_limited(self):
        """المنصة لا تصبح أداة إغراق لصندوق أحد."""
        results = [mailer.send_mail("victim@b.co", "Hi", "<p>hi</p>") for _ in range(mailer.RATE_LIMIT + 2)]
        self.assertEqual(results.count(True), mailer.RATE_LIMIT)
        self.assertTrue(mailer.send_mail("other@b.co", "Hi", "<p>hi</p>"), "الحدّ لكل عنوان لا عام")

    def test_ssl_mode_uses_smtp_ssl(self):
        os.environ["SMTP_TLS"] = "ssl"
        calls = []
        mailer.smtplib.SMTP_SSL = lambda *a, **k: calls.append(a) or FakeSMTP(*a, **k)
        self.assertTrue(mailer.send_mail("a@b.co", "Hi", "<p>hi</p>"))
        self.assertEqual(len(calls), 1)

    def test_templates_escape_and_follow_the_language_direction(self):
        _, html_ar, _ = mailer.reset_email('https://x.test/reset/"><script>alert(1)</script>', "ar")
        self.assertNotIn("<script>alert", html_ar)
        self.assertIn('dir="rtl"', html_ar)
        _, html_en, text_en = mailer.reset_email("https://x.test/reset/abc", "en")
        self.assertIn('dir="ltr"', html_en)
        self.assertIn("https://x.test/reset/abc", text_en, "الرابط يجب أن يظهر في النص الخام أيضاً")

    def test_the_receipt_carries_the_payment_facts(self):
        row = {"id": 42, "user_id": 1, "plan": "pro", "amount": 199.0, "expires_at": 1893456000}
        subject, html, text = mailer.receipt_email(row, "approved", "en")
        self.assertIn("#42", subject)
        for fact in ("199 EGP", "2030-01-01", "Pro"):
            self.assertIn(fact, text, fact)
        subject, _, text = mailer.receipt_email(row, "rejected", "ar")
        self.assertIn("#42", subject)
        self.assertNotIn("ساري حتى", text, "الرفض لا يَعِد بتاريخ انتهاء")


if __name__ == "__main__":
    unittest.main(verbosity=2)
