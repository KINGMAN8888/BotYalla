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
import re

import httpx

from .base import Channel

log = logging.getLogger("channels.messenger")
GRAPH = "https://graph.facebook.com/v21.0"
TIMEOUT = 15
QR_MAX, QR_TITLE = 13, 20

_client = None
# آخر أزرار أُرسلت لكل عميل (الصفحة، الـpeer) ← الخيارات: رقم يكتبه العميل («2») أو العنوان بلا
# الإيموجي («دعم فني») يُترجم للخيار نفسه — إنستجرام على الويب لا يعرض الأزرار أصلاً، والعميل يكتب.
# في الذاكرة (عملية gunicorn واحدة)، ومحدود الحجم.
_LAST_OPTS = {}
_LAST_MAX = 5000
_NAMES = {}                           # peer ← اسم العميل (أو "" لو فشل الجلب) — لا نسأل Graph كل رسالة
_EMOJI = re.compile(r"[^\w\s؀-ۿ]", re.UNICODE)


# صدى رسائل البوت نفسه: إنستجرام يرسل `message_echoes` **بلا app_id**، فلا يُميَّز رد البوت من رد
# صاحب الصفحة بالتطبيق. نتذكر كل ما أرسلناه: معرّف الرسالة (mid) من رد الـSend API، ووقت بدء
# الإرسال لكل عميل — الصدى قد يصل قبل أن يعود رد الـAPI (نفس حلقة asyncio).
_OUR_MIDS = set()
_LAST_SEND = {}                      # (حسابنا، العميل) ← وقت آخر إرسال من البوت
ECHO_WINDOW = 30                     # ثانية: صدى خلالها بعد إرسال البوت = صدى البوت


def is_our_echo(own_id, customer_id, mid):
    """هل هذا الصدى رسالة أرسلها البوت (لا إنسان من Meta Business Suite/الموبايل)؟"""
    import time as _t
    if mid and mid in _OUR_MIDS:
        return True
    return _t.time() - _LAST_SEND.get((str(own_id), str(customer_id)), 0) < ECHO_WINDOW


def _plain(s):
    return " ".join(_EMOJI.sub(" ", s or "").split()).lower()


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
        rid = str((body.get("recipient") or {}).get("id") or "")
        if "message" in body and rid:
            import time as _t
            if len(_LAST_SEND) > _LAST_MAX:
                _LAST_SEND.clear()
            _LAST_SEND[(self.page_id, rid)] = _t.time()        # قبل الإرسال — الصدى قد يسبق الرد
        try:
            c = await _http()
            r = await c.post(f"{GRAPH}/me/messages", json=body,
                             params={"access_token": self.token})
            if r.status_code >= 400:
                log.error("Messenger API %s (%s): %s", r.status_code, self.platform, r.text[:400])
                return None
            res = r.json() or {}
            if res.get("message_id"):
                if len(_OUR_MIDS) > _LAST_MAX:
                    _OUR_MIDS.clear()
                _OUR_MIDS.add(res["message_id"])
            return res
        except Exception:
            log.exception("Messenger API call failed")
            return None

    async def _send(self, peer, message):
        return await self._call({"recipient": {"id": self._to(peer)},
                                 "messaging_type": "RESPONSE", "message": message})

    async def send_text(self, peer, text):
        return await self._send(peer, {"text": (text or "")[:2000]})

    def _remember(self, peer, opts):
        if len(_LAST_OPTS) > _LAST_MAX:
            _LAST_OPTS.clear()
        _LAST_OPTS[(self.page_id, peer)] = list(opts)

    async def send_buttons(self, peer, text, options):
        opts = [str(o) for o in (options or [])]
        if not opts:
            return await self.send_text(peer, text)
        self._remember(peer, opts)
        numbered = "\n".join(f"{i + 1}. {o}" for i, o in enumerate(opts))
        if len(opts) <= QR_MAX and all(len(o) <= QR_TITLE for o in opts):
            # إنستجرام يعرض الأزرار في التطبيق فقط لا على الويب: القائمة المرقّمة في النص أيضاً،
            # والرقم أو العنوان يُقبلان كإجابة (`_one`). ماسنجر يعرضها في كل مكان.
            body = (text or "👇") if self.platform != "ig" else f"{text or ''}\n\n{numbered}".strip()
            return await self._send(peer, {
                "text": body[:2000],
                "quick_replies": [{"content_type": "text", "title": o, "payload": o} for o in opts]})
        return await self.send_text(peer, (text or "") + "\n\n" + numbered)

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

    def _as_option(self, peer, text):
        """«2» أو «دعم فني» (بلا الإيموجي) ← عنوان الخيار الذي أُرسل لهذا العميل آخر مرة."""
        opts = _LAST_OPTS.get((self.page_id, peer))
        if not opts:
            return text
        t = text.strip()
        if t.isdigit() and 1 <= int(t) <= len(opts):
            return opts[int(t) - 1]
        p = _plain(t)
        for o in opts:
            if p and p == _plain(o):
                return o
        return text

    async def profile_name(self, peer):
        """اسم العميل لصندوق الوارد: ماسنجر `first_name last_name` (User Profile API)، وإنستجرام
        `name` أو `username`. مرة واحدة لكل عميل؛ الفشل (إذن ناقص/خصوصية) يُحفظ فلا يتكرر."""
        if peer in _NAMES:
            return _NAMES[peer]
        fields = "name,username" if self.platform == "ig" else "first_name,last_name"
        name = ""
        try:
            c = await _http()
            r = await c.get(f"{GRAPH}/{self._to(peer)}", params={"fields": fields, "access_token": self.token})
            if r.status_code == 200:
                d = r.json() or {}
                name = (d.get("name") or " ".join(x for x in (d.get("first_name"), d.get("last_name")) if x)
                        or (("@" + d["username"]) if d.get("username") else ""))
            else:
                log.info("profile lookup %s for %s: %s", r.status_code, self.platform, r.text[:200])
        except Exception:
            log.info("profile lookup failed", exc_info=True)
        if len(_NAMES) > _LAST_MAX:
            _NAMES.clear()
        _NAMES[peer] = name[:80]
        return _NAMES[peer]

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
            if kind == "start" and ref.startswith(("seg-", "src-")):
                out["start_arg"] = ref
            return out
        if ev.get("referral") and not m:               # m.me/…?ref=seg-market لمحادثة قائمة
            return {"id": f"ref:{sender}:{ev.get('timestamp')}", "peer": peer, "text": "",
                    "name": "", "kind": "start", **({"start_arg": ref} if ref.startswith(("seg-", "src-")) else {})}
        if not m or m.get("is_echo"):
            return None
        mid = m.get("mid") or ""
        self._peer_of_mid[mid] = peer
        qr = (m.get("quick_reply") or {}).get("payload")
        text = str(qr or m.get("text") or "").strip()
        if text and not qr:
            text = self._as_option(peer, text)
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
