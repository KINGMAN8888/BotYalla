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
        {peer, text, name, kind: 'text'|'button'|'start'|'cancel'}"""
        raise NotImplementedError
