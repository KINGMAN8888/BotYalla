from .base import Channel
from telegram import Bot, ReplyKeyboardMarkup, ReplyKeyboardRemove

class TelegramChannel(Channel):
    def __init__(self, bot: Bot):
        self.bot = bot

    async def send_text(self, peer: str, text: str):
        chat_id = self._extract_chat_id(peer)
        await self.bot.send_message(chat_id=chat_id, text=text)

    async def send_buttons(self, peer: str, text: str, options: list):
        chat_id = self._extract_chat_id(peer)
        kb = ReplyKeyboardMarkup([[o] for o in options], resize_keyboard=True, one_time_keyboard=True)
        await self.bot.send_message(chat_id=chat_id, text=text, reply_markup=kb)

    async def send_image(self, peer: str, url: str, caption: str = None):
        chat_id = self._extract_chat_id(peer)
        await self.bot.send_photo(chat_id=chat_id, photo=url, caption=caption)

    async def remove_keyboard(self, peer: str, text: str):
        chat_id = self._extract_chat_id(peer)
        await self.bot.send_message(chat_id=chat_id, text=text, reply_markup=ReplyKeyboardRemove())

    def _extract_chat_id(self, peer: str) -> int:
        if peer.startswith("tg:"):
            return int(peer[3:])
        return int(peer)

    def _media_of(self, msg):
        """يستخرج (file_id, mime) من أول نوع وسائط موجود في الرسالة."""
        if msg.photo:
            # PhotoSize مرتّبة تصاعدياً — الأخيرة أعلى دقة
            return msg.photo[-1].file_id, "image/jpeg"
        for attr, mime in (("voice", "audio/ogg"), ("audio", ""), ("video", "video/mp4"),
                           ("video_note", "video/mp4"), ("document", ""), ("sticker", "image/webp")):
            obj = getattr(msg, attr, None)
            if obj:
                return obj.file_id, (getattr(obj, "mime_type", "") or mime)
        return None, None

    async def fetch_media(self, media):
        ref = (media or {}).get("ref")
        if not ref:
            return None, None
        try:
            f = await self.bot.get_file(ref)
            data = await f.download_as_bytearray()
            return bytes(data), media.get("mime", "")
        except Exception:
            return None, None

    def normalize(self, update) -> dict:
        if not update or not update.effective_user:
            return None
        user = update.effective_user
        msg = update.message
        if not msg:
            return None
        text = msg.text.strip() if msg.text else ""

        kind = "text"
        if text.startswith("/start"):
            kind = "start"
        elif text.startswith("/cancel"):
            kind = "cancel"

        out = {
            "id": str(msg.message_id),
            "peer": f"tg:{user.id}",
            "text": text,
            "name": user.first_name or "",
            "kind": kind,
        }
        if not text:
            ref, mime = self._media_of(msg)
            caption = (msg.caption or "").strip()
            if ref:
                out.update(kind="media", text=caption,
                           media={"ref": ref, "mime": mime, "caption": caption})
            else:
                out["kind"] = "unsupported"    # موقع/جهة اتصال — لا ملف نحفظه
        return out
