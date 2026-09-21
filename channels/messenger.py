"""قناة ماسنجر فيسبوك + رسائل إنستجرام — Messenger Platform (نفس الـSend API للاثنين).

الهوية:
  * البوت: `fb:<page_id>` (ماسنجر) أو `ig:<ig_user_id>` (إنستجرام — حساب احترافي مربوط بالصفحة).
  * العميل: `fb:<PSID>` أو `ig:<IGSID>` — معرّفات خاصة بالصفحة، لا أرقام هواتف.
  * التوكن: **Page Access Token** للصفحة نفسها (الإنستجرام يُرسل بتوكن صفحته المربوطة).

سياسة Meta (تُطبَّق في bot_manager وinbox_relay لا هنا): الرد الحر داخل **24 ساعة** من آخر
رسالة للعميل فقط (`messaging_type: RESPONSE`). بعدها لا رسائل تسويقية ولا بث — المخالفة
تُقيّد الصفحة. الردود التلقائية هنا كلها ردود على رسالة العميل.

الأزرار: `quick_replies` (حتى 13، العنوان ≤20 حرفاً) — مدعومة في ماسنجر وإنستجرام معاً،
والـpayload هو العنوان نفسه فيصل للمحرك كأن العميل كتبه. أكثر من ذلك: قائمة مرقّمة
(نفس سلوك واتساب الذي يقبل المحرك رقمه كإجابة)."""
import logging

import httpx

from .base import Channel

log = logging.getLogger("channels.messenger")
GRAPH = "https://graph.facebook.com/v21.0"
TIMEOUT = 15
QR_MAX, QR_TITLE = 13, 20

_client = None


async def _http():
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(timeout=TIMEOUT)
    return _client


class MessengerChannel(Channel):
    START_WORDS = {"start", "/start", "ابدأ", "ابدا", "بداية", "مرحبا", "مرحباً", "اهلا", "أهلا",
                   "hi", "hello", "hey", "get started"}
    CANCEL_WORDS = {"/cancel", "cancel", "الغاء", "إلغاء", "توقف", "stop"}

    def __init__(self, platform, page_id, token, on_send=None):
        """platform: 'fb' أو 'ig' (بادئة الـpeer). on_send: حارس async قبل كل إرسال."""
        self.platform = platform
        self.page_id = str(page_id)
        self.token = token
        self.on_send = on_send
        self._peer_of_mid = {}                 # mid ← peer: mark_read يحتاج المستلم لا الرسالة

    # ------------------------------------------------------------------ إرسال
    def _to(self, peer):
        return peer.split(":", 1)[1] if ":" in peer else peer

    async def _call(self, body, count=True):
        if count and self.on_send is not None and (await self.on_send()) is False:
            return None
        try:
            c = await _http()
            r = await c.post(f"{GRAPH}/me/messages", json=body,
                             params={"access_token": self.token})
            if r.status_code >= 400:
                log.error("Messenger API %s (%s): %s", r.status_code, self.platform, r.text[:400])
                return None
            return r.json()
        except Exception:
            log.exception("Messenger API call failed")
            return None

    async def _send(self, peer, message):
        return await self._call({"recipient": {"id": self._to(peer)},
                                 "messaging_type": "RESPONSE", "message": message})

    async def send_text(self, peer, text):
        return await self._send(peer, {"text": (text or "")[:2000]})

    async def send_buttons(self, peer, text, options):
        opts = [str(o) for o in (options or [])]
        if not opts:
            return await self.send_text(peer, text)
        if len(opts) <= QR_MAX and all(len(o) <= QR_TITLE for o in opts):
            return await self._send(peer, {
                "text": (text or "👇")[:2000],
                "quick_replies": [{"content_type": "text", "title": o, "payload": o} for o in opts]})
        body = (text or "") + "\n\n" + "\n".join(f"{i + 1}. {o}" for i, o in enumerate(opts))
        return await self.send_text(peer, body)

    async def send_image(self, peer, url, caption=None):
        res = await self._send(peer, {"attachment": {"type": "image",
                                                     "payload": {"url": url, "is_reusable": True}}})
        if caption:
            await self.send_text(peer, caption)
        return res

    async def send_document_link(self, peer, url, filename, caption=""):
        if self.platform == "ig":                      # إنستجرام لا يستقبل ملفات: الرابط نصاً
            return await self.send_text(peer, f"{caption}\n{url}".strip())
        res = await self._send(peer, {"attachment": {"type": "file",
                                                     "payload": {"url": url, "is_reusable": True}}})
        if caption:
            await self.send_text(peer, caption)
        return res

    async def send_media(self, peer, asset, bot_id, caption=None, options=None):
        """وسائط المكتبة خاصة (تحتاج جلسة) فلا يجلبها Meta برابط — المرحلة الأولى ترسل
        التعليق والأزرار وحدها بدل فشل صامت. (الرفع عبر Attachment Upload API لاحقاً.)"""
        if options:
            return await self.send_buttons(peer, caption or "👇", options)
        return await self.send_text(peer, caption or "📎")

    async def remove_keyboard(self, peer, text):
        return await self.send_text(peer, text)

    async def mark_read(self, message_id, typing=True):
        """«تمت المشاهدة» + «يكتب…» — ليست رسائل فلا تمرّ بحارس الاستهلاك."""
        peer = self._peer_of_mid.get(message_id)
        if not peer:
            return None
        rid = {"id": self._to(peer)}
        await self._call({"recipient": rid, "sender_action": "mark_seen"}, count=False)
        if typing:
            await self._call({"recipient": rid, "sender_action": "typing_on"}, count=False)
        return True

    async def send_typing(self, peer):
        await self._call({"recipient": {"id": self._to(peer)}, "sender_action": "typing_on"}, count=False)

    async def fetch_media(self, media):
        """المرفقات الواردة روابط CDN موقّعة مؤقتة — تُنزَّل مباشرة بلا توكن."""
        url = (media or {}).get("ref")
        if not url:
            return None, None
        try:
            c = await _http()
            r = await c.get(url)
            if r.status_code == 200:
                return r.content, r.headers.get("content-type", "application/octet-stream")
        except Exception:
            log.info("Messenger media fetch failed", exc_info=True)
        return None, None

    # ------------------------------------------------------------------ استقبال
    def normalize_all(self, raw):
        """حدث واحد من entry.messaging[] ← رسالة موحّدة. صدى رسائلنا (`is_echo`) والقراءة
        والتسليم ليست وارداً فتُهمل."""
        out = []
        try:
            for entry in (raw or {}).get("entry", []):
                for ev in entry.get("messaging", []) or []:
                    n = self._one(ev)
                    if n:
                        out.append(n)
        except (AttributeError, TypeError, KeyError):
            log.exception("could not parse Messenger payload")
        return out

    def normalize(self, raw):
        msgs = self.normalize_all(raw)
        return msgs[0] if msgs else None

    def _one(self, ev):
        sender = str((ev.get("sender") or {}).get("id") or "")
        if not sender or sender == self.page_id:
            return None
        peer = f"{self.platform}:{sender}"
        m = ev.get("message")
        pb = ev.get("postback")
        ref = (ev.get("referral") or (pb or {}).get("referral") or {}).get("ref") or ""
        if pb:                                          # زرّ «ابدأ» أو زرّ في قالب
            payload = str(pb.get("payload") or "")
            kind = "start" if payload.upper() == "GET_STARTED" else "text"
            out = {"id": pb.get("mid") or f"pb:{sender}:{ev.get('timestamp')}", "peer": peer,
                   "text": "" if kind == "start" else (pb.get("title") or payload), "name": "",
                   "kind": kind}
            if kind == "start" and ref.startswith("seg-"):
                out["start_arg"] = ref
            return out
        if ev.get("referral") and not m:               # m.me/…?ref=seg-market لمحادثة قائمة
            return {"id": f"ref:{sender}:{ev.get('timestamp')}", "peer": peer, "text": "",
                    "name": "", "kind": "start", **({"start_arg": ref} if ref.startswith("seg-") else {})}
        if not m or m.get("is_echo"):
            return None
        mid = m.get("mid") or ""
        self._peer_of_mid[mid] = peer
        qr = (m.get("quick_reply") or {}).get("payload")
        text = str(qr or m.get("text") or "").strip()
        if not text and m.get("attachments"):
            a = m["attachments"][0]
            return {"id": mid, "peer": peer, "text": "", "name": "", "kind": "media",
                    "media": {"ref": (a.get("payload") or {}).get("url"), "mime": a.get("type"),
                              "caption": ""}}
        if not text:
            return None
        low = text.lower()
        kind = "start" if low in self.START_WORDS else "cancel" if low in self.CANCEL_WORDS else "text"
        return {"id": mid, "peer": peer, "text": text, "name": "", "kind": kind}
