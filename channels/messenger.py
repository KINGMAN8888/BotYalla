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
# حدّ نص الرسالة: إنستجرام 1000 **بايت** UTF-8 (الحرف العربي بايتان)، ماسنجر 2000 حرف. الأطول
# يُرفض كله من Meta — فيظهر في صندوقنا ولا يصل للعميل. نقسّمه رسائل متتالية عند سطر/مسافة.
IG_TEXT_BYTES, FB_TEXT_CHARS = 1000, 2000

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
_LAST_SEND = {}                      # (حسابنا، العميل) ← [(وقت، نص)] لآخر ما أرسله البوت
ECHO_WINDOW = 90                     # ثانية: نص مطابق لما أرسلناه خلالها = صدى البوت
ECHO_BLIND = 8                       # صدى بلا نص (صورة/ملف) بعد إرسالنا بثوانٍ = صدى البوت


def _norm_text(s):
    return " ".join(str(s or "").split())


def is_our_echo(own_id, customer_id, mid, text=None, app_id=None, ours=None):
    """هل هذا الصدى رسالة أرسلها البوت (لا إنسان من Meta Business Suite/الموبايل)؟
    بالمعرّف أولاً، ثم بتطابق النص — لا بالتوقيت وحده: ردّ صاحب الصفحة بعد البوت بثوانٍ كان
    يُحسب صدى للبوت فيختفي من صندوق الوارد. app_id تطبيق آخر (صندوق Business Suite) = إنسان."""
    import time as _t
    if mid and mid in _OUR_MIDS:
        return True
    if app_id and ours and str(app_id) == str(ours):
        return True
    if app_id:                                   # تطبيق آخر أرسلها — ليست نحن
        return False
    now = _t.time()
    recent = [(t, x) for t, x in _LAST_SEND.get((str(own_id), str(customer_id)), []) if now - t < ECHO_WINDOW]
    t_ = _norm_text(text)
    if t_:
        return any(x == t_ for _, x in recent)
    return any(now - t < ECHO_BLIND for t, _ in recent)


def split_text(text, platform):
    """نص طويل ← أجزاء ضمن حدّ المنصة، مقسومة عند سطر ثم مسافة."""
    text = text or ""
    fits = (lambda s: len(s.encode("utf-8")) <= IG_TEXT_BYTES - 10) if platform == "ig" else \
           (lambda s: len(s) <= FB_TEXT_CHARS)
    out = []
    while text and not fits(text):
        cut = len(text)
        while cut > 1 and not fits(text[:cut]):
            cut = int(cut * 0.9)
        for sep in ("\n", " "):
            k = text.rfind(sep, 0, cut)
            if k > cut // 2:
                cut = k
                break
        out.append(text[:cut].rstrip())
        text = text[cut:].lstrip()
    if text or not out:
        out.append(text)
    return out


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
        self.last_error = ""
        # توكن ألغاه فيسبوك (تغيير كلمة السر · جلسة أمنية — OAuthException 190): توكنات بديلة لنفس
        # الصفحة (بوت الصفحة الآخر · صفحة المنصة) تُجرَّب وأول سليم يُحفظ. callables يضبطها bot_manager.
        self.token_fallbacks = None            # () -> [token, …]
        self.on_token_fixed = None             # (token) -> None
        self.on_token_dead = None              # (error_text) -> None

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
            key = (self.page_id, rid)                            # قبل الإرسال — الصدى قد يسبق الرد
            _LAST_SEND[key] = (_LAST_SEND.get(key) or [])[-9:] + \
                [(_t.time(), _norm_text((body.get("message") or {}).get("text")))]
        try:
            c = await _http()
            r = await c.post(f"{GRAPH}/me/messages", json=body,
                             params={"access_token": self.token})
            if r.status_code >= 400 and self._token_error(r) and await self._heal_token():
                r = await c.post(f"{GRAPH}/me/messages", json=body, params={"access_token": self.token})
            if r.status_code >= 400 and "message" in body and rid and self._thread_error(r) and \
                    await self.take_thread(rid):
                # المحادثة كانت مع صندوق الصفحة (Business Suite) بعد تسليمها لإنسان — استرجعناها
                r = await c.post(f"{GRAPH}/me/messages", json=body, params={"access_token": self.token})
            if r.status_code >= 400:
                # (#551/#10/#100-2018001) العميل نفسه غير قابل للمراسلة الآن: حذف المحادثة
                # أو حظر الصفحة أو انتهت نافذة الـ24 ساعة. ليست عطلاً في المنصة، وتسجيلها
                # خطأً يدفن الأعطال الحقيقية — تحذير سطر واحد يكفي.
                if self._unreachable(r):
                    log.warning("Messenger (%s): recipient not reachable now (#551/window)",
                                self.platform)
                else:
                    log.error("Messenger API %s (%s): %s", r.status_code, self.platform,
                              r.text[:400])
                self.last_error = r.text[:300]
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

    @staticmethod
    def _unreachable(r):
        """المستلم غير قابل للمراسلة الآن — لا عطل عندنا."""
        try:
            e = (r.json() or {}).get("error") or {}
        except Exception:                                    # noqa: BLE001
            return False
        return (e.get("code") in (551, 10, 2018001)
                or e.get("error_subcode") in (2018001, 2018108)
                or "not available" in str(e.get("message", "")).lower())

    @staticmethod
    def _token_error(r):
        """التوكن نفسه لم يعد صالحاً (190) — لا خطأ في الرسالة."""
        try:
            e = (r.json() or {}).get("error") or {}
        except Exception:
            return False
        return e.get("code") in (190, 102) or e.get("type") == "OAuthException" and "session" in str(e.get("message", "")).lower()

    async def _heal_token(self):
        """يجرّب التوكنات البديلة بـ GET /me؛ أول سليم يصبح توكن القناة ويُحفظ. False لو لا بديل."""
        dead = self.token
        try:
            cands = [t for t in (self.token_fallbacks() if self.token_fallbacks else []) if t and t != dead]
        except Exception:
            cands = []
        c = await _http()
        for t in dict.fromkeys(cands):
            try:
                r = await c.get(f"{GRAPH}/me", params={"fields": "id", "access_token": t})
            except Exception:
                continue
            if r.status_code == 200:
                self.token = t
                if self.on_token_fixed:
                    try:
                        self.on_token_fixed(t)
                    except Exception:
                        log.exception("saving healed page token failed")
                log.warning("%s page %s: dead token replaced by a working one", self.platform, self.page_id)
                return True
        if self.on_token_dead:
            try:
                self.on_token_dead(self.last_error or "token invalid")
            except Exception:
                log.exception("token dead hook failed")
        return False

    @staticmethod
    def _thread_error(r):
        """رفض لأن تطبيقاً آخر يملك المحادثة (بروتوكول التسليم)."""
        try:
            e = (r.json() or {}).get("error") or {}
        except Exception:
            return False
        msg = str(e.get("message") or "").lower()
        return e.get("error_subcode") in (2018109, 2018108) or "thread" in msg or "handover" in msg

    async def take_thread(self, rid):
        """يستعيد المحادثة لتطبيقنا من صندوق الصفحة — لازم قبل أن يرد البوت بعد تسليمها لإنسان."""
        try:
            c = await _http()
            r = await c.post(f"{GRAPH}/me/take_thread_control", params={"access_token": self.token},
                             json={"recipient": {"id": rid}, "metadata": "botyalla: bot resumed"})
            if r.status_code >= 400:
                log.info("take_thread_control %s (%s): %s", r.status_code, self.platform, r.text[:200])
            return r.status_code < 400
        except Exception:
            log.info("take_thread_control failed", exc_info=True)
            return False

    async def _send(self, peer, message):
        """نص أطول من حدّ المنصة يُرسل أجزاءً (الأزرار مع الجزء الأخير). يرجّع رد آخر جزء،
        أو None لو فشل أي جزء — فلا يُسجَّل في الصندوق ما لم يصل كاملاً."""
        parts = split_text(message.get("text"), self.platform) if message.get("text") else [None]
        res = None
        for i, part in enumerate(parts):
            msg = dict(message)
            if part is not None:
                msg["text"] = part
            if i < len(parts) - 1:
                msg.pop("quick_replies", None)
            res = await self._call({"recipient": {"id": self._to(peer)},
                                    "messaging_type": "RESPONSE", "message": msg}, count=(i == 0))
            if res is None:
                return None
        return res

    async def send_text(self, peer, text):
        return await self._send(peer, {"text": text or ""})

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
                "text": body,
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
        # ردّ على إعلان (Click-to-Direct/Messenger): الإحالة داخل message، وقد تصل بلا نص (ضغطة الإعلان
        # وحدها) — تُعامل بداية محادثة مصدرها الإعلان فيرحّب البوت بدل أن تُهمل
        ad = m.get("referral") or {}
        ad_src = "src-ads" if str(ad.get("source") or "").upper() == "ADS" else ""
        if ad and not (m.get("text") or m.get("attachments") or m.get("quick_reply")):
            out = {"id": mid, "peer": peer, "text": "", "name": "", "kind": "start"}
            if ad_src:
                out["start_arg"] = ad_src
            return out
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
        out = {"id": mid, "peer": peer, "text": text, "name": "", "kind": kind}
        # نص الإعلان الجاهز «مرحبا #brand» (كواتساب): بداية + مصدرها
        tagged = re.fullmatch(r"(.+?)\s*#([a-z]{2,15})", low)
        if tagged and tagged.group(1).strip() in self.START_WORDS:
            import segments
            tag = tagged.group(2)
            # وسم ليس شريحة معروفة (#brand) من إعلان ← المصدر «إعلانات» لا يضيع في التحليلات
            out.update(kind="start", start_arg=f"seg-{tag}" if segments.get(tag) or not ad_src else ad_src)
        elif ad_src and kind == "start":
            out["start_arg"] = ad_src
        return out
