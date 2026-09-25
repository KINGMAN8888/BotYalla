"""قناة واتساب — WhatsApp Cloud API من Meta.

فروق جوهرية عن تليجرام تحكم كل ما في هذا الملف:
· كل رسالة صادرة **مدفوعة** — لذلك كل إرسال يمرّ بعدّاد الاستهلاك.
· لا مراسلة حرّة بعد 24 ساعة من آخر رسالة للعميل — والمخالفة تُقيّد الرقم.
· 3 أزرار كحد أقصى، وعنوان الزر 20 حرفاً."""
import asyncio, json, logging, os, re
import httpx
from .base import Channel

# معرّف العميل الخاص بالنشاط (BSUID) لمن فعّل «اسم المستخدم» وأخفى رقمه على واتساب:
# كود الدولة ثم نقطة ثم حتى 128 حرفاً/رقماً — مثل EG.13491208655302741918. Meta تحذف `from`
# تماماً في هذه الحالة وترسل `from_user_id`.
#
# ⚠️ الرد يُرسل في حقل `to` كأي عميل. جُرِّب `recipient` أولاً (كما فهمناه من التوثيق)
# فرفضته Meta في الإنتاج 21 مرة بـ«The parameter to is required» — أي أن كل رسالة إلى
# عميل مخفي الرقم كانت تضيع بصمت: محادثته تظهر في الوارد ولا يصله ردّ أبداً.
# لذلك: `to` دائماً، ومع رفضٍ يذكر `recipient` صراحةً تُعاد المحاولة مرة واحدة بالحقل
# الآخر (بلا خصم ثانٍ من العدّاد) — فأي تغيير مستقبلي في Meta لا يُسكت البوت من جديد.
BSUID_RE = re.compile(r"^[A-Z]{2}\.[A-Za-z0-9]{1,128}$")


def is_bsuid(v):
    return bool(BSUID_RE.match(str(v or "")))

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


def proxy_send(phone_id, token, payload):
    """يمرّر حمولة الشريك كما هي إلى Cloud API ويعيد (الحالة، الرد) — نداء متزامن.

    لا نُعيد تشكيل الحمولة عمداً: كل ما تقبله Meta (نص، قالب، وسائط، تفاعلي) يمرّ بلا
    وسيط، فكود الشريك المكتوب أصلاً على Graph يعمل بتغيير عنوان الأساس وحده. وتوكن
    Meta يبقى على خادمنا — الشريك يحمل مفتاحنا نحن، ونلغيه وحده متى شئنا."""
    body = dict(payload or {})
    body.setdefault("messaging_product", "whatsapp")
    try:
        with httpx.Client(timeout=TIMEOUT) as c:
            r = c.post(f"{META_API}/{phone_id}/messages", json=body,
                       headers={"Authorization": f"Bearer {token}"})
        try:
            data = r.json()
        except ValueError:
            data = {"error": {"message": (r.text or "")[:300], "code": r.status_code}}
        return r.status_code, data
    except httpx.HTTPError as e:
        log.warning("proxy_send upstream error: %s", type(e).__name__)
        return 502, {"error": {"message": f"upstream unreachable ({type(e).__name__})",
                               "type": "upstream", "code": 502}}


def _meta_err(r):
    try:
        return ((r.json() or {}).get("error") or {}).get("message") or f"HTTP {r.status_code}"
    except Exception:
        return f"HTTP {r.status_code}"


def set_profile_photo(phone_id, token, jpeg, app_id=None):
    """صورة بروفايل رقم واتساب للأعمال. ثلاث خطوات (Resumable Upload): جلسة رفع على التطبيق
    `/{app-id}/uploads` ← رفع البايتات (ترويسة `OAuth` لا `Bearer` + `file_offset`) فيرجع handle
    ← `/{phone-id}/whatsapp_business_profile` بـ `profile_picture_handle`.
    App ID يُقرأ من `GET /app` بنفس التوكن ويُعاد للمستدعي ليخزّنه. متزامنة (تُستدعى من Flask).
    يرجّع (ok, خطأ, app_id)."""
    bearer = {"Authorization": f"Bearer {token}"}
    try:
        with httpx.Client(timeout=TIMEOUT) as c:
            if not app_id:
                r = c.get(f"{META_API}/app", headers=bearer)
                app_id = str((r.json() or {}).get("id") or "") if r.status_code == 200 else ""
                if not app_id:
                    return False, "app_id", None
            r = c.post(f"{META_API}/{app_id}/uploads", headers=bearer,
                       params={"file_name": "profile.jpg", "file_length": len(jpeg), "file_type": "image/jpeg"})
            sid = (r.json() or {}).get("id") if r.status_code == 200 else None
            if not sid:
                return False, _meta_err(r), app_id
            r = c.post(f"{META_API}/{sid}", content=jpeg,
                       headers={"Authorization": f"OAuth {token}", "file_offset": "0"})
            h = (r.json() or {}).get("h") if r.status_code == 200 else None
            if not h:
                return False, _meta_err(r), app_id
            r = c.post(f"{META_API}/{phone_id}/whatsapp_business_profile", headers=bearer,
                       json={"messaging_product": "whatsapp", "profile_picture_handle": h})
            if r.status_code == 200 and (r.json() or {}).get("success"):
                return True, "", app_id
            return False, _meta_err(r), app_id
    except Exception as e:
        log.warning("WhatsApp profile photo failed for %s", phone_id, exc_info=True)
        return False, str(e)[:200], app_id


class WhatsAppChannel(Channel):
    def __init__(self, phone_id, token, on_send=None):
        """on_send: دالة async تُستدعى قبل كل إرسال — تحجز رسالة من رصيد الباقة
        وتُرجع False لمنع الإرسال عند تجاوز الحدّ."""
        self.phone_id = phone_id
        self.token = token
        self.on_send = on_send

    async def _raw(self, payload):
        """طلب واحد بلا حجز رصيد — تستعمله `_post` وإعادة المحاولة معاً."""
        c = await _http()
        return await c.post(f"{META_API}/{self.phone_id}/messages", json=payload,
                            headers={"Authorization": f"Bearer {self.token}",
                                     "Content-Type": "application/json"})

    async def _post(self, payload):
        if self.on_send is not None and (await self.on_send()) is False:
            log.warning("send blocked for phone_id %s: monthly limit reached", self.phone_id)
            return None
        try:
            r = await self._raw(payload)
            if r.status_code >= 400 and is_bsuid(payload.get("to", "")) and \
                    "recipient" in (r.text or "").lower():
                # Meta تطلب الحقل الآخر لهذا النوع من المعرّفات: محاولة واحدة بلا خصم ثانٍ
                alt = dict(payload)
                alt["recipient"] = alt.pop("to")
                r2 = await self._raw(alt)
                if r2.status_code < 400:
                    log.warning("WhatsApp: hidden-number recipient accepted via `recipient`")
                    return r2.json()
            if r.status_code >= 400:
                # نص خطأ Meta هو الوحيد الذي يفسّر سبب الرفض (نافذة، قالب، توكن)
                log.error("WhatsApp API %s: %s", r.status_code, r.text[:400])
                return None
            return r.json()
        except Exception:
            log.exception("WhatsApp API call failed")
            return None

    async def mark_read(self, message_id, typing=True):
        """علامتا القراءة الزرقاوان + «يكتب…» فوراً للعميل حتى يصل الرد (حتى 25ث أو الرد).
        ليست رسالة: لا تمرّ بعدّاد الاستهلاك (`on_send`) ولا تُحاسَب من Meta."""
        if not message_id:
            return None
        p = {"messaging_product": "whatsapp", "status": "read", "message_id": message_id}
        if typing:
            p["typing_indicator"] = {"type": "text"}
        try:
            c = await _http()
            r = await c.post(f"{META_API}/{self.phone_id}/messages", json=p,
                             headers={"Authorization": f"Bearer {self.token}",
                                      "Content-Type": "application/json"})
            if r.status_code >= 400:
                log.info("WhatsApp mark_read %s: %s", r.status_code, r.text[:200])
            return r.status_code < 400
        except Exception:
            log.info("WhatsApp mark_read failed", exc_info=True)
            return None

    def _to(self, peer):
        return peer[3:] if peer.startswith("wa:") else peer

    def _base(self, peer, kind):
        # `to` لكل العملاء — بمن فيهم مخفيو الرقم (راجع التعليق أعلى الملف)
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
        if 3 < len(options) <= 10 and all(len(o) <= 24 for o in options):
            # 4-10 خيارات قصيرة: رسالة «قائمة» تفاعلية (زر يفتح الخيارات) — الرد يصل بعنوان
            # الصف نفسه (`list_reply.title` في `_one`) فيطابقه المحرك كأي زر
            p = self._base(peer, "interactive")
            p["interactive"] = {
                "type": "list",
                "body": {"text": text[:1024]},
                "action": {"button": "اختار من هنا 👇" if not text.isascii() else "Choose 👇",
                           "sections": [{"title": "—", "rows": [{"id": f"row_{i}", "title": o}
                                                                 for i, o in enumerate(options)]}]},
            }
            return await self._post(p)
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

    # media_id لدى Meta صالح 30 يوماً — نعيد الرفع قبل ذلك بهامش.
    MEDIA_REF_TTL = 25 * 86400

    async def upload_media(self, path, mime):
        """يرفع ملفاً إلى Meta ويرجّع media_id. الرفع ليس رسالة فلا يمرّ بالعدّاد."""
        try:
            with open(path, "rb") as f:
                data = f.read()
            c = await _http()
            r = await c.post(f"{META_API}/{self.phone_id}/media",
                             headers={"Authorization": f"Bearer {self.token}"},
                             data={"messaging_product": "whatsapp", "type": mime},
                             files={"file": ("file" + os.path.splitext(path)[1], data, mime)})
            if r.status_code >= 400:
                log.error("WhatsApp media upload %s: %s", r.status_code, r.text[:300])
                return None
            return (r.json() or {}).get("id")
        except Exception:
            log.exception("WhatsApp media upload failed")
            return None

    async def send_document_link(self, peer, url, filename, caption=""):
        """Cloud API تجلب الملف من الرابط بنفسها — لا رفع ولا مرجع يُخزَّن."""
        p = self._base(peer, "document")
        p["document"] = {"link": url, "filename": filename[:240]}
        if caption:
            p["document"]["caption"] = caption[:1024]
        return await self._post(p)

    async def send_media(self, peer, asset, bot_id, caption=None, options=None):
        """حتى 3 خيارات قصيرة (≤20 حرفاً): رسالة تفاعلية بترويسة صورة/فيديو وأزرار
        تحتها — «الفيديو التفاعلي». أكثر من ذلك: الوسائط ثم الخيارات قائمة مرقّمة
        (نفس سلوك send_buttons الذي يقبل المحرك رقمه كإجابة)."""
        import time as _t
        import database as db, asset_store
        mid = db.get_asset_ref(asset["id"], bot_id)
        if not mid:
            mid = await self.upload_media(asset_store.path_of(asset["fname"]), asset["mime"])
            if not mid:
                return None
            db.set_asset_ref(asset["id"], bot_id, mid, expires_at=int(_t.time()) + self.MEDIA_REF_TTL)
        kind = "video" if asset["kind"] == "video" else "image"
        opts = [str(o) for o in (options or [])]
        caption = (caption or "").strip()
        if opts and len(opts) <= 3 and all(len(o) <= 20 for o in opts):
            p = self._base(peer, "interactive")
            p["interactive"] = {
                "type": "button",
                "header": {"type": kind, kind: {"id": mid}},
                "body": {"text": (caption or "👇")[:1024]},
                "action": {"buttons": [{"type": "reply", "reply": {"id": f"btn_{i}", "title": o}}
                                       for i, o in enumerate(opts)]},
            }
            return await self._post(p)
        p = self._base(peer, kind)
        p[kind] = {"id": mid}
        if caption:
            p[kind]["caption"] = caption[:1024]
        res = await self._post(p)
        if opts:
            await self.send_buttons(peer, "👇", opts)
        return res

    async def send_template(self, peer, name, lang="ar", components=None):
        """القالب المعتمد هو الطريقة الوحيدة لبدء محادثة خارج نافذة الـ24 ساعة."""
        p = self._base(peer, "template")
        p["template"] = {"name": name, "language": {"code": lang}}
        if components:
            p["template"]["components"] = components
        return await self._post(p)

    async def send_direct(self, peer, text, category="utility"):
        """Direct Send API (بيتا) — إرسال بدون قالب مسبق.

        Meta تُنشئ القالب تلقائياً في الخلفية. يدعم فقط utility و authentication —
        لا يدعم marketing. الحقل الإضافي الوحيد هو ``category`` في جسم الطلب."""
        if category not in ("utility", "authentication"):
            log.warning("send_direct called with unsupported category %r", category)
            return None
        p = self._base(peer, "text")
        p["text"] = {"body": text}
        p["category"] = category
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
                    name, uid = "", ""
                    contacts = val.get("contacts") or []
                    if contacts:
                        prof = contacts[0].get("profile") or {}
                        uname = prof.get("username") or ""
                        name = prof.get("name") or (f"@{uname}" if uname else "")
                        uid = contacts[0].get("user_id") or ""
                    for m in msgs:
                        n = self._one(m, name, uid)
                        if n:
                            out.append(n)
        except (AttributeError, KeyError, IndexError, TypeError):
            log.exception("could not parse WhatsApp payload")
        return out

    MEDIA_TYPES = ("image", "audio", "voice", "video", "document", "sticker")

    def _sender(self, m, uid=""):
        """هوية العميل: رقمه إن ظهر، وإلا معرّفه الخاص (BSUID). الرقم أولاً حتى لا تنقسم محادثة
        قديمة، والمعرّف المربوط برقم سبق ظهوره يرجع لنفس المحادثة (db.wa_user_phone)."""
        phone = str(m.get("from") or "").strip().lstrip("+")
        bsuid = str(m.get("from_user_id") or uid or "").strip()
        if not is_bsuid(bsuid):
            bsuid = ""
        try:
            import database as _db
            if phone.isdigit() and bsuid:
                _db.remember_wa_user(bsuid, phone)
            elif bsuid and not phone:
                phone = _db.wa_user_phone(bsuid) or ""
        except Exception:
            log.debug("wa user id map unavailable", exc_info=True)
        if phone.isdigit():
            return phone
        return bsuid

    def _one(self, m, name, uid=""):
        sender = self._sender(m, uid)
        if not sender:
            log.warning("WhatsApp message without a phone or user id: %s", m.get("id"))
            return None
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
            return {"id": m.get("id", ""), "peer": f"wa:{sender}",
                    "text": caption, "name": name, "kind": "media",
                    "media": {"ref": part.get("id", ""), "mime": part.get("mime_type", ""),
                              "caption": caption, "type": mtype}}
        else:
            # موقع/جهة اتصال/غيرها: لا نص ولا ملف نحفظه.
            return {"id": m.get("id", ""), "peer": f"wa:{sender}",
                    "text": "", "name": name, "kind": "unsupported", "media_type": mtype}

        low = text.strip().lower()
        kind, arg = "text", None
        # رابط إعلان/صفحة شريحة: «مرحبا #market» = بداية + مصدرها (segments.wa_text)
        tagged = re.fullmatch(r"(.+?)\s*#([a-z]{2,15})", low)
        if tagged and tagged.group(1).strip() in self.START_WORDS:
            kind, arg = "start", f"seg-{tagged.group(2)}"
        elif low in self.START_WORDS:
            kind = "start"
        elif low in self.CANCEL_WORDS:
            kind = "cancel"
        out = {"id": m.get("id", ""), "peer": f"wa:{sender}",
               "text": text.strip(), "name": name, "kind": kind}
        if arg:
            out["start_arg"] = arg
        return out

    def normalize(self, raw):
        msgs = self.normalize_all(raw)
        return msgs[0] if msgs else None
