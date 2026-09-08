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

    def normalize(self, update) -> dict:
        if not update or not update.effective_user:
            return None
        user = update.effective_user
        msg = update.message
        text = msg.text.strip() if msg and msg.text else ""
        
        kind = "text"
        if text.startswith("/start"):
            kind = "start"
        elif text.startswith("/cancel"):
            kind = "cancel"

        return {
            "peer": f"tg:{user.id}",
            "text": text,
            "name": user.first_name or "",
            "kind": kind
        }
