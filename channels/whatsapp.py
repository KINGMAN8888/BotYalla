"""قناة واتساب — WhatsApp Cloud API من Meta.

فروق جوهرية عن تليجرام تحكم كل ما في هذا الملف:
· كل رسالة صادرة **مدفوعة** — لذلك كل إرسال يمرّ بعدّاد الاستهلاك.
· لا مراسلة حرّة بعد 24 ساعة من آخر رسالة للعميل — والمخالفة تُقيّد الرقم.
· 3 أزرار كحد أقصى، وعنوان الزر 20 حرفاً."""
import asyncio, json, logging
import httpx
from .base import Channel

log = logging.getLogger("whatsapp_channel")
META_API = "https://graph.facebook.com/v20.0"
TIMEOUT = 15

# عميل واحد مشترك: فتح Pool جديد لكل رسالة يعني اتصال TLS جديد كل مرة.
_client = None
_client_lock = asyncio.Lock()

async def _http():
    global _client
    if _client is None or _client.is_closed:
        async with _client_lock:
            if _client is None or _client.is_closed:
                _client = httpx.AsyncClient(timeout=TIMEOUT)
    return _client


def verify_credentials(phone_id, token):
    """يتحقّق أن Phone Number ID والتوكن صالحان معاً — نظير tg.validate_token.
    يمنع إنشاء بوت ميت بسبب خطأ نسخ أو توكن منتهٍ. متزامنة: تُستدعى من Flask."""
    phone_id = (phone_id or "").strip()
    token = (token or "").strip()
    if not phone_id.isdigit():
        return {"ok": False, "error": "Phone Number ID أرقام فقط."}
    if not token:
        return {"ok": False, "error": "Access Token مفقود."}
    try:
        with httpx.Client(timeout=TIMEOUT) as c:
            r = c.get(f"{META_API}/{phone_id}",
                      params={"fields": "display_phone_number,verified_name,quality_rating"},
                      headers={"Authorization": f"Bearer {token}"})
        data = r.json()
    except Exception as e:
        return {"ok": False, "error": f"تعذّر الاتصال بـ Meta: {e}"}
    if r.status_code != 200:
        err = (data.get("error") or {}).get("message") or f"HTTP {r.status_code}"
        return {"ok": False, "error": err}
    return {"ok": True,
            "number": data.get("display_phone_number", ""),
            "name": data.get("verified_name", ""),
            "quality": data.get("quality_rating", "")}


class WhatsAppChannel(Channel):
    def __init__(self, phone_id, token, on_send=None):
        """on_send: دالة async تُستدعى قبل كل إرسال — تحجز رسالة من رصيد الباقة
        وتُرجع False لمنع الإرسال عند تجاوز الحدّ."""
        self.phone_id = phone_id
        self.token = token
        self.on_send = on_send

    async def _post(self, payload):
        if self.on_send is not None and (await self.on_send()) is False:
            log.warning("send blocked for phone_id %s: monthly limit reached", self.phone_id)
            return None
        try:
            c = await _http()
            r = await c.post(f"{META_API}/{self.phone_id}/messages", json=payload,
                             headers={"Authorization": f"Bearer {self.token}",
                                      "Content-Type": "application/json"})
            if r.status_code >= 400:
                # نص خطأ Meta هو الوحيد الذي يفسّر سبب الرفض (نافذة، قالب، توكن)
                log.error("WhatsApp API %s: %s", r.status_code, r.text[:400])
                return None
            return r.json()
        except Exception:
            log.exception("WhatsApp API call failed")
            return None

    def _to(self, peer):
        return peer[3:] if peer.startswith("wa:") else peer

    def _base(self, peer, kind):
        return {"messaging_product": "whatsapp", "recipient_type": "individual",
                "to": self._to(peer), "type": kind}

    async def send_text(self, peer, text):
        p = self._base(peer, "text")
        p["text"] = {"preview_url": False, "body": text}
        return await self._post(p)

    async def send_buttons(self, peer, text, options):
        # أكثر من 3 خيارات أو عنوان أطول من 20 حرفاً: واتساب يرفض أو يقتطع،
        # والاقتطاع يكسر مطابقة الإجابة بالخيار. نعرضها قائمة مرقّمة بدل ذلك،
        # والمحرك يقبل الرقم كإجابة (flow_engine._on_input).
        options = [str(o) for o in (options or [])]
        if len(options) > 3 or any(len(o) > 20 for o in options):
            body = text + "\n\n" + "\n".join(f"{i+1}. {o}" for i, o in enumerate(options))
            return await self.send_text(peer, body)

        p = self._base(peer, "interactive")
        p["interactive"] = {
            "type": "button",
            "body": {"text": text},
            "action": {"buttons": [{"type": "reply", "reply": {"id": f"btn_{i}", "title": o}}
                                   for i, o in enumerate(options)]},
        }
        return await self._post(p)

    async def send_image(self, peer, url, caption=None):
        p = self._base(peer, "image")
        p["image"] = {"link": url}
        if caption:
            p["image"]["caption"] = caption
        return await self._post(p)

    async def remove_keyboard(self, peer, text):
        # لا لوحة مفاتيح دائمة في واتساب — مجرد نص.
        return await self.send_text(peer, text)

    async def send_template(self, peer, name, lang="ar", components=None):
        """القالب المعتمد هو الطريقة الوحيدة لبدء محادثة خارج نافذة الـ24 ساعة."""
        p = self._base(peer, "template")
        p["template"] = {"name": name, "language": {"code": lang}}
        if components:
            p["template"]["components"] = components
        return await self._post(p)

    async def fetch_media(self, media):
        """خطوتان تفرضهما Meta: المعرّف يعطي رابطاً صالحاً 5 دقائق فقط،
        والرابط نفسه لا يُفتح إلا بترويسة Authorization. والوارد يبقى قابلاً
        للتنزيل 7 أيام — لذلك ننزّل لحظة الوصول لا لاحقاً."""
        ref = (media or {}).get("ref")
        if not ref:
            return None, None
        auth = {"Authorization": f"Bearer {self.token}"}
        try:
            c = await _http()
            meta = await c.get(f"{META_API}/{ref}",
                               params={"phone_number_id": self.phone_id}, headers=auth)
            if meta.status_code >= 400:
                log.error("media lookup %s: %s", meta.status_code, meta.text[:300])
                return None, None
            info = meta.json()
            url = info.get("url")
            if not url:
                return None, None
            blob = await c.get(url, headers=auth)
            if blob.status_code >= 400:
                log.error("media download %s: %s", blob.status_code, blob.text[:300])
                return None, None
            return blob.content, info.get("mime_type") or media.get("mime", "")
        except Exception:
            log.exception("WhatsApp media fetch failed")
            return None, None

    # ------------------------------------------------------------- الوارد
    START_WORDS = {"/start", "start", "بدء", "ابدأ", "مرحبا", "مرحباً", "السلام عليكم",
                   "hi", "hello", "hey"}
    CANCEL_WORDS = {"/cancel", "cancel", "الغاء", "إلغاء", "توقف", "stop"}

    def normalize_all(self, raw):
        """يحوّل payload الويبهوك إلى قائمة رسائل موحّدة.
        Meta قد ترسل أكثر من رسالة في الدفعة الواحدة — تجاهل الباقي يفقد إجابات."""
        out = []
        try:
            for entry in raw.get("entry", []):
                for change in entry.get("changes", []):
                    val = change.get("value") or {}
                    msgs = val.get("messages") or []
                    if not msgs:
                        continue          # statuses / تحديث تسليم — ليس وارداً
                    name = ""
                    contacts = val.get("contacts") or []
                    if contacts:
                        name = (contacts[0].get("profile") or {}).get("name", "") or ""
                    for m in msgs:
                        n = self._one(m, name)
                        if n:
                            out.append(n)
        except (AttributeError, KeyError, IndexError, TypeError):
            log.exception("could not parse WhatsApp payload")
        return out

    MEDIA_TYPES = ("image", "audio", "voice", "video", "document", "sticker")

    def _one(self, m, name):
        mtype = m.get("type")
        text = ""
        if mtype == "text":
            text = (m.get("text") or {}).get("body", "") or ""
        elif mtype == "interactive":
            inter = m.get("interactive") or {}
            sub = inter.get(inter.get("type") or "", {})
            text = sub.get("title", "") or ""
        elif mtype == "button":       # ردّ زر قالب
            text = (m.get("button") or {}).get("text", "") or ""
        elif mtype in self.MEDIA_TYPES:
            part = m.get(mtype) or {}
            caption = part.get("caption", "") or ""
            return {"id": m.get("id", ""), "peer": f"wa:{m.get('from','')}",
                    "text": caption, "name": name, "kind": "media",
                    "media": {"ref": part.get("id", ""), "mime": part.get("mime_type", ""),
                              "caption": caption, "type": mtype}}
        else:
            # موقع/جهة اتصال/غيرها: لا نص ولا ملف نحفظه.
            return {"id": m.get("id", ""), "peer": f"wa:{m.get('from','')}",
                    "text": "", "name": name, "kind": "unsupported", "media_type": mtype}

        low = text.strip().lower()
        kind = "text"
        if low in self.START_WORDS:
            kind = "start"
        elif low in self.CANCEL_WORDS:
            kind = "cancel"
        return {"id": m.get("id", ""), "peer": f"wa:{m.get('from','')}",
                "text": text.strip(), "name": name, "kind": kind}

    def normalize(self, raw):
        msgs = self.normalize_all(raw)
        return msgs[0] if msgs else None
