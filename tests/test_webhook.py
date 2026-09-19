"""اختبار ويبهوك واتساب — على قاعدة مؤقتة، لا على قاعدة الإنتاج.
    python tests/test_webhook.py
"""
import hashlib, hmac, os, sys, tempfile, unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_TMP = os.path.join(tempfile.mkdtemp(prefix="botyalla-test-"), "test.db")
os.environ["BOTYALLA_DB"] = _TMP          # يجب أن يسبق استيراد database/app
os.environ.setdefault("SECRET_KEY", "test-secret")

import database as db                      # noqa: E402
import app as web                          # noqa: E402

SECRET = "test-app-secret"
VERIFY = "test-verify-token"


class WebhookTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        db.init_db()
        cls.c = web.app.test_client()

    def _sign(self, body):
        return "sha256=" + hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()

    def test_get_is_refused_when_no_verify_token_configured(self):
        db.set_platform("wa_verify_token", "")
        r = self.c.get("/wh/whatsapp?hub.mode=subscribe&hub.verify_token=&hub.challenge=1234")
        self.assertEqual(r.status_code, 403, "الويبهوك يجب أن يرفض قبل الضبط، لا أن يفتح الباب")

    def test_get_echoes_challenge_with_the_right_token(self):
        db.set_platform("wa_verify_token", VERIFY)
        r = self.c.get(f"/wh/whatsapp?hub.mode=subscribe&hub.verify_token={VERIFY}&hub.challenge=1234")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data, b"1234")

    def test_get_refuses_a_wrong_token(self):
        db.set_platform("wa_verify_token", VERIFY)
        r = self.c.get("/wh/whatsapp?hub.mode=subscribe&hub.verify_token=nope&hub.challenge=1234")
        self.assertEqual(r.status_code, 403)

    def test_post_is_refused_when_no_secret_configured(self):
        db.set_platform("wa_app_secret", "")
        r = self.c.post("/wh/whatsapp", data=b"{}",
                        headers={"Content-Type": "application/json"})
        self.assertEqual(r.status_code, 403, "بلا سرّ يجب أن يُرفض الطلب لا أن يُقبل بلا تحقّق")

    def test_post_refuses_a_bad_signature(self):
        db.set_platform("wa_app_secret", SECRET)
        r = self.c.post("/wh/whatsapp", data=b"{}",
                        headers={"X-Hub-Signature-256": "sha256=invalid",
                                 "Content-Type": "application/json"})
        self.assertEqual(r.status_code, 403)

    def test_post_accepts_a_valid_signature(self):
        db.set_platform("wa_app_secret", SECRET)
        body = (b'{"entry":[{"changes":[{"value":{"messages":[],'
                b'"metadata":{"phone_number_id":"123"}}}]}]}')
        r = self.c.post("/wh/whatsapp", data=body,
                        headers={"X-Hub-Signature-256": self._sign(body),
                                 "Content-Type": "application/json"})
        self.assertEqual(r.status_code, 200)

    def test_post_accepts_either_app_secret(self):
        """رقم المنصة على تطبيق، وأرقام العملاء (الربط بضغطة) على تطبيق الـTech Provider."""
        db.set_platform("wa_app_secret", SECRET)
        db.set_platform("wa_es_app_secret", "es-secret")
        try:
            body = b'{"entry":[]}'
            for key in (SECRET, "es-secret"):
                sig = "sha256=" + hmac.new(key.encode(), body, hashlib.sha256).hexdigest()
                r = self.c.post("/wh/whatsapp", data=body,
                                headers={"X-Hub-Signature-256": sig, "Content-Type": "application/json"})
                self.assertEqual(r.status_code, 200, key)
            sig = "sha256=" + hmac.new(b"other", body, hashlib.sha256).hexdigest()
            r = self.c.post("/wh/whatsapp", data=body,
                            headers={"X-Hub-Signature-256": sig, "Content-Type": "application/json"})
            self.assertEqual(r.status_code, 403)
            db.set_platform("wa_app_secret", "")            # سرّ الـTech Provider وحده يكفي للفتح
            sig = "sha256=" + hmac.new(b"es-secret", body, hashlib.sha256).hexdigest()
            r = self.c.post("/wh/whatsapp", data=body,
                            headers={"X-Hub-Signature-256": sig, "Content-Type": "application/json"})
            self.assertEqual(r.status_code, 200)
        finally:
            db.set_platform("wa_es_app_secret", "")

    def test_post_needs_no_csrf_token(self):
        """المسار مُستثنى من CSRF عمداً — التوقيع هو الحارس."""
        db.set_platform("wa_app_secret", SECRET)
        body = b'{"entry":[]}'
        r = self.c.post("/wh/whatsapp", data=body,
                        headers={"X-Hub-Signature-256": self._sign(body),
                                 "Content-Type": "application/json"})
        self.assertEqual(r.status_code, 200)


class NormalizeTests(unittest.TestCase):
    def test_button_reply_becomes_its_title(self):
        from channels.whatsapp import WhatsAppChannel
        ch = WhatsAppChannel("123", "tok")
        msg = ch.normalize({"entry": [{"changes": [{"value": {
            "contacts": [{"profile": {"name": "Youssef"}}],
            "messages": [{"from": "201001234567", "type": "interactive",
                          "interactive": {"type": "button_reply",
                                          "button_reply": {"id": "btn_0", "title": "نعم"}}}]}}]}]})
        self.assertEqual(msg["peer"], "wa:201001234567")
        self.assertEqual(msg["text"], "نعم")
        self.assertEqual(msg["name"], "Youssef")

    def test_status_update_is_ignored(self):
        from channels.whatsapp import WhatsAppChannel
        ch = WhatsAppChannel("123", "tok")
        self.assertIsNone(ch.normalize({"entry": [{"changes": [{"value": {"statuses": []}}]}]}))


if __name__ == "__main__":
    unittest.main(verbosity=2)
