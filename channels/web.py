"""قناة «محادثة الويب» — ودجت الموقع (المرحلة 7).

زائر موقع العميل يكتب في الودجت فتمرّ رسالته بمحرك الفلو نفسه (فلوهات · ذكاء · تحويل لموظف ·
الصندوق المشترك) بهوية `wb:<رقم>`. الرد لا يُدفع للمتصفح: يُكتب في `web_outbox` ويستطلعه الودجت.
الوسائط من مكتبة صاحب الحساب تُعرض برابط موقَّع قصير العمر (`asset_url`) — المكتبة نفسها خاصة.
"""
import database as db

from .base import Channel

# app.py يضبطه عند التحميل: (asset) -> رابط عام موقَّع قصير العمر لملف من المكتبة
SIGNER = None


class WebChannel(Channel):
    def __init__(self, bot_id, asset_url=None):
        self.bot_id = bot_id
        self.asset_url = asset_url or SIGNER
        self.phone_id = self.page_id = None

    def _push(self, peer, **payload):
        return {"id": db.web_push(self.bot_id, peer, payload)}

    async def send_text(self, peer, text):
        return self._push(peer, text=text)

    async def remove_keyboard(self, peer, text):
        return self._push(peer, text=text)

    async def send_buttons(self, peer, text, options):
        return self._push(peer, text=text, buttons=[str(o)[:40] for o in (options or [])][:10])

    async def send_image(self, peer, url, caption=None):
        return self._push(peer, text=caption or "", link=url if str(url).startswith("https://") else None)

    async def send_media(self, peer, asset, bot_id, caption=None, options=None):
        url = self.asset_url(asset) if self.asset_url else None
        return self._push(peer, text=caption or "", media={"kind": asset.get("kind"), "url": url} if url else None,
                          buttons=[str(o)[:40] for o in (options or [])][:10] or None)

    async def send_document_link(self, peer, url, filename, caption=""):
        return self._push(peer, text=caption or filename, link=url if str(url).startswith("https://") else None)

    async def send_cta(self, peer, text, button, url):
        return self._push(peer, text=text, link=url if str(url).startswith("https://") else None, cta=str(button)[:20])

    async def send_typing(self, peer):
        return None

    async def fetch_media(self, media):
        return None, None                    # الزائر يكتب نصاً فقط
