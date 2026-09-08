import httpx
import json
import logging
from .base import Channel

log = logging.getLogger("whatsapp_channel")
META_API = "https://graph.facebook.com/v19.0"

class WhatsAppChannel(Channel):
    def __init__(self, phone_id: str, token: str):
        self.phone_id = phone_id
        self.token = token

    async def _post(self, payload: dict):
        url = f"{META_API}/{self.phone_id}/messages"
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }
        async with httpx.AsyncClient() as client:
            try:
                r = await client.post(url, json=payload, headers=headers, timeout=10)
                r.raise_for_status()
                return r.json()
            except Exception as e:
                log.error(f"WhatsApp API error: {e}")
                return None

    def _extract_peer(self, peer: str) -> str:
        if peer.startswith("wa:"):
            return peer[3:]
        return peer

    async def send_text(self, peer: str, text: str):
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": self._extract_peer(peer),
            "type": "text",
            "text": {"preview_url": False, "body": text}
        }
        return await self._post(payload)

    async def send_buttons(self, peer: str, text: str, options: list):
        # واتساب: 3 أزرار كحد أقصى، وعنوان الزر 20 حرفاً. أي خيار أطول
        # سيُقتطع ولن يطابق نص الإجابة المتوقّع، فنعرض القائمة كنص بدلاً منه.
        if len(options) > 3 or any(len(str(o)) > 20 for o in options):
            txt = text + "\n\n" + "\n".join(f"{i+1}. {o}" for i, o in enumerate(options))
            return await self.send_text(peer, txt)

        buttons = []
        for i, opt in enumerate(options):
            buttons.append({
                "type": "reply",
                "reply": {"id": f"btn_{i}", "title": str(opt)}
            })

        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": self._extract_peer(peer),
            "type": "interactive",
            "interactive": {
                "type": "button",
                "body": {"text": text},
                "action": {"buttons": buttons}
            }
        }
        return await self._post(payload)

    async def send_image(self, peer: str, url: str, caption: str = None):
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": self._extract_peer(peer),
            "type": "image",
            "image": {"link": url}
        }
        if caption:
            payload["image"]["caption"] = caption
        return await self._post(payload)

    async def remove_keyboard(self, peer: str, text: str):
        # WhatsApp doesn't have a persistent keyboard to remove.
        return await self.send_text(peer, text)

    def normalize(self, raw) -> dict:
        """
        يحوّل رسالة واردة من Webhook الخاصة بـ Meta إلى الهيكل الموحد.
        """
        try:
            val = raw["entry"][0]["changes"][0]["value"]
            if "messages" not in val or not val["messages"]:
                return None
            msg = val["messages"][0]
            peer = f"wa:{msg['from']}"
            
            text = ""
            if msg.get("type") == "text":
                text = msg["text"]["body"]
            elif msg.get("type") == "interactive":
                inter = msg["interactive"]
                if inter["type"] == "button_reply":
                    text = inter["button_reply"]["title"]
                elif inter["type"] == "list_reply":
                    text = inter["list_reply"]["title"]

            name = ""
            if "contacts" in val and val["contacts"]:
                name = val["contacts"][0].get("profile", {}).get("name", "")

            kind = "text"
            text_lower = text.strip().lower()
            if text_lower in ("/start", "start", "مرحبا", "hi", "hello"):
                kind = "start"
            elif text_lower in ("/cancel", "cancel", "الغاء", "إلغاء"):
                kind = "cancel"

            return {
                "peer": peer,
                "text": text,
                "name": name,
                "kind": kind
            }
        except (KeyError, IndexError, TypeError):
            return None
