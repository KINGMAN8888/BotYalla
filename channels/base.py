class Channel:
    """الواجهة المجردة لطبقة الإرسال (تليجرام، واتساب، الخ).
    أي قناة يجب أن تنفذ هذه الدوال."""
    
    async def send_text(self, peer: str, text: str):
        """إرسال رسالة نصية بسيطة"""
        raise NotImplementedError

    async def send_buttons(self, peer: str, text: str, options: list):
        """إرسال رسالة مع أزرار (Reply Keyboard)"""
        raise NotImplementedError

    async def send_image(self, peer: str, url: str, caption: str = None):
        """إرسال صورة مع نص اختياري"""
        raise NotImplementedError

    async def remove_keyboard(self, peer: str, text: str):
        """إزالة لوحة المفاتيح (مفيد لتليجرام)، أو مجرد إرسال نص عادي لواتساب"""
        raise NotImplementedError

    def normalize(self, raw) -> dict:
        """يحوّل رسالة واردة إلى شكل موحّد:
        {id, peer, text, name, kind: 'text'|'start'|'cancel'|'media'|'unsupported'}
        رسالة 'media' تحمل أيضاً media={ref, mime, caption} — مرجع لا ملف."""
        raise NotImplementedError

    async def fetch_media(self, media) -> tuple:
        """ينزّل ملفاً وارداً من مرجعه. يرجّع (bytes, mime) أو (None, None).
        منفصل عن normalize لأننا لا ننزّل إلا ما سنحفظه فعلاً."""
        return None, None

    def normalize_all(self, raw) -> list:
        """بعض القنوات تسلّم أكثر من رسالة في الدفعة الواحدة (واتساب)."""
        one = self.normalize(raw)
        return [one] if one else []
