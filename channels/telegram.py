from .base import Channel
from telegram import Bot, ReplyKeyboardMarkup, ReplyKeyboardRemove

def _rows(options):
    """أزرار لوحة المفاتيح: 3 أو أقل صفّ لكل زر، و4 فأكثر (قائمة «محتاج إيه؟») عمودان."""
    options = list(options or [])
    if len(options) <= 3:
        return [[o] for o in options]
    return [options[i:i + 2] for i in range(0, len(options), 2)]


class TelegramChannel(Channel):
    # file_id يُحفظ لكل (ملف، بوت). بوت المنصة يخدم صفّ بوت المساعد الرسمي (واتساب) فمفتاح
    # الحفظ نفسه يحمل media_id واتساب — قناته تضبط False فترفع الملف كل مرة ولا تلمس المرجع.
    cache_refs = True

    def __init__(self, bot: Bot):
        self.bot = bot

    async def send_text(self, peer: str, text: str):
        chat_id = self._extract_chat_id(peer)
        await self.bot.send_message(chat_id=chat_id, text=text)

    async def send_buttons(self, peer: str, text: str, options: list):
        chat_id = self._extract_chat_id(peer)
        kb = ReplyKeyboardMarkup(_rows(options), resize_keyboard=True, one_time_keyboard=True)
        await self.bot.send_message(chat_id=chat_id, text=text, reply_markup=kb)

    async def send_image(self, peer: str, url: str, caption: str = None):
        chat_id = self._extract_chat_id(peer)
        await self.bot.send_photo(chat_id=chat_id, photo=url, caption=caption)

    async def remove_keyboard(self, peer: str, text: str):
        chat_id = self._extract_chat_id(peer)
        await self.bot.send_message(chat_id=chat_id, text=text, reply_markup=ReplyKeyboardRemove())

    async def send_typing(self, peer: str):
        try:
            await self.bot.send_chat_action(chat_id=self._extract_chat_id(peer), action="typing")
        except Exception:
            pass                               # تجميلي — فشله لا يوقف الرد

    async def send_media(self, peer, asset, bot_id, caption=None, options=None, markup=None):
        """أول إرسال يرفع الملف، وتليجرام يعيد file_id يُحفظ لهذا البوت ويُعاد
        استعماله (file_id خاص بكل بوت). مرجع لم يعد صالحاً يُمسح ويُرفع الملف ثانية.
        `markup`: لوحة جاهزة (قوائم المتجر والحجز) بدل بنائها من `options`."""
        import database as db, asset_store
        from telegram.error import BadRequest
        chat_id = self._extract_chat_id(peer)
        caption = (caption or "").strip()
        long_caption = len(caption) > 1024            # حدّ تليجرام لتعليق الوسائط
        kb = markup if markup is not None else (
            ReplyKeyboardMarkup(_rows(options), resize_keyboard=True, one_time_keyboard=True)
            if options else ReplyKeyboardRemove())
        ref = db.get_asset_ref(asset["id"], bot_id) if self.cache_refs else None
        for _ in (0, 1):
            src = ref or open(asset_store.path_of(asset["fname"]), "rb")
            try:
                kw = dict(chat_id=chat_id, caption=None if long_caption else (caption or None),
                          reply_markup=None if long_caption else kb)
                if asset["kind"] == "video":
                    m = await self.bot.send_video(video=src, supports_streaming=True, **kw)
                    fid = m.video.file_id if m.video else None
                else:
                    m = await self.bot.send_photo(photo=src, **kw)
                    fid = m.photo[-1].file_id if m.photo else None
                if fid and not ref and self.cache_refs:
                    db.set_asset_ref(asset["id"], bot_id, fid)
                if long_caption:
                    await self.bot.send_message(chat_id=chat_id, text=caption, reply_markup=kb)
                return m
            except BadRequest:
                if not ref:
                    raise
                db.drop_asset_ref(asset["id"], bot_id)
                ref = None
            finally:
                if not isinstance(src, str):
                    src.close()

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
