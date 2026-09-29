"""مكالمات واتساب — المرحلة 8: العميل يتصل من زر الاتصال في واتساب ⇒ ترنّ في الصندوق المشترك ⇒ الموظف يرد
من المتصفح (WebRTC) بصوت مباشر مع العميل. مكالمة فائتة ⇒ رسالة تلقائية ونداء للفريق.

الطريق (WhatsApp Business Calling API):
  1. ويبهوك `calls` بحدث `connect` (USER_INITIATED) ومعه عرض SDP ⇒ نحفظ المكالمة «ترنّ».
  2. متصفح الموظف يستطلع المكالمات الرانّة، ينشئ RTCPeerConnection بعرض Meta ويولّد الجواب (answer).
  3. الخادم يرسل الجواب لـ Meta: `pre_accept` ثم `accept` — والصوت يجري مباشرة بين المتصفح وخوادم Meta.
  4. `terminate` من أي طرف ⇒ المدة في سجل المحادثة.

القواعد (AGENTS §71):
  · **موظف واحد يرد** — الاستلام ذرّي (`db.claim_call` من «ترنّ» فقط)؛ الثاني يرى «ردّ زميل».
  · عرض SDP للمكالمة لا يصل إلا لمن يرى المحادثة ويملك الرد (`_inbox_guard` + `_can_reply`).
  · الويبهوك يكتب محلياً فقط (سريع) — لا نداء لـ Meta داخله.
"""
import logging
import re
import time

import httpx

import database as db

log = logging.getLogger("calling")
GRAPH = "https://graph.facebook.com/v21.0"
TIMEOUT = 15
RING_SECONDS = 60                     # بعدها تُعدّ فائتة لو لم يصل terminate (Meta تنهيها قبل ذلك عادةً)
SDP_MAX = 20000
_CALL_ID = re.compile(r"[\w.:\-]{6,200}")


class CallError(Exception):
    pass


def _cfg(bot_row):
    import json
    return json.loads(bot_row.get("config_json") or "{}")


def _post(bot_row, path, body):
    phone_id = (bot_row.get("token") or "").split(":", 1)[-1]
    token = _cfg(bot_row).get("wa_token") or ""
    if not phone_id or not token:
        raise CallError("channel")
    with httpx.Client(timeout=TIMEOUT) as c:
        r = c.post(f"{GRAPH}/{phone_id}/{path}", json=body, headers={"Authorization": f"Bearer {token}"})
    if r.status_code >= 400:
        try:
            msg = ((r.json() or {}).get("error") or {}).get("message") or r.text
        except ValueError:
            msg = r.text
        raise CallError(str(msg)[:200])
    return r.json() if r.content else {}


# ─────────────────────────── الويبهوك ───────────────────────────
def on_webhook(payload):
    """أحداث `calls` من ويبهوك واتساب الموقَّع ⇒ عدد ما عولج. كتابة محلية فقط."""
    if (payload or {}).get("object") != "whatsapp_business_account":
        return 0
    n = 0
    for entry in payload.get("entry") or []:
        for ch in entry.get("changes") or []:
            if ch.get("field") != "calls":
                continue
            v = ch.get("value") or {}
            phone_id = str((v.get("metadata") or {}).get("phone_number_id") or "")
            bot = db.get_bot_by_token(f"wa:{phone_id}") if phone_id else None
            if not bot or not bot.get("is_active"):
                continue
            names = {str(c.get("wa_id")): (c.get("profile") or {}).get("name") or "" for c in v.get("contacts") or []}
            for call in v.get("calls") or []:
                cid = str(call.get("id") or "")
                if not _CALL_ID.fullmatch(cid):
                    continue
                peer = "wa:" + re.sub(r"\D", "", str(call.get("from") or ""))
                ev = call.get("event")
                if ev == "connect" and call.get("direction") == "BUSINESS_INITIATED":
                    # مكالمتنا الصادرة: العميل ردّ — جواب SDP لمتصفح الموظف المتصل
                    sess = call.get("session") or {}
                    if sess.get("sdp_type") == "answer" and db.set_call_answer(cid, str(sess.get("sdp") or "")[:SDP_MAX]):
                        n += 1
                    continue
                if ev == "connect" and call.get("direction", "USER_INITIATED") == "USER_INITIATED":
                    sdp = str((call.get("session") or {}).get("sdp") or "")[:SDP_MAX]
                    if sdp and db.add_call(bot["id"], cid, peer, names.get(peer[3:], ""), sdp):
                        db.log_message(bot["id"], peer, "in", "customer", "📞 مكالمة واردة", name=names.get(peer[3:], ""))
                        n += 1
                elif ev == "terminate":
                    c = db.end_call(cid, int(call.get("duration") or 0))
                    if c:
                        _log_end(bot, c)
                        n += 1
    return n


def _fmt(sec):
    return f"{sec // 60}:{sec % 60:02d}"


def _log_end(bot, c):
    if c.get("direction") == "out":                # صادرة: المدة أو «لم يرد» — لا رسالة فائتة لعميل لم يتصل
        text = f"📞 مكالمة صادرة — {_fmt(c['duration'])}" if c["status"] == "ended" and c["duration"] else "📞 اتصلنا ولم يرد العميل"
        db.log_message(bot["id"], c["peer"], "out", "human", text, user_id=c.get("agent_id"))
        return
    if c["status"] == "ended" and c["duration"]:
        db.log_message(bot["id"], c["peer"], "out", "human", f"📞 مكالمة — {_fmt(c['duration'])}", user_id=c.get("agent_id"))
    else:
        db.log_message(bot["id"], c["peer"], "in", "customer", "📞 مكالمة فائتة")
        HOOKS["missed"](dict(bot), c)


def _missed_default(bot, c):
    """فائتة: رسالة للعميل (نافذة الـ24 ساعة مفتوحة — اتصاله يفتحها) ونداء للفريق في الصندوق."""
    text = (_cfg(bot).get("calls") or {}).get("missed_text")
    if text:
        HOOKS["send"](bot, c["peer"], text)


HOOKS = {"missed": _missed_default, "send": lambda bot, peer, text: None}


def sweep(now=None):
    """مكالمات ترنّ بلا رد ولا terminate بعد مهلة الرنين ⇒ فائتة (ويبهوك ضاع)."""
    for c in db.stale_ringing_calls(int(now or time.time()) - RING_SECONDS):
        done = db.end_call(c["call_id"], 0)
        bot = db.get_bot(c["bot_id"]) if done else None
        if bot:
            _log_end(dict(bot), done)


# ─────────────────────────── أفعال الموظف ───────────────────────────
def answer(bot_row, call, agent_id, sdp_answer):
    """استلام ذرّي ثم pre_accept + accept بجواب متصفح الموظف. يرمي CallError(taken|…)."""
    sdp = str(sdp_answer or "")
    if not sdp.startswith("v=0") or len(sdp) > SDP_MAX:
        raise CallError("sdp")
    if not db.claim_call(call["call_id"], agent_id):
        raise CallError("taken")
    session = {"sdp_type": "answer", "sdp": sdp}
    try:
        _post(bot_row, "calls", {"messaging_product": "whatsapp", "call_id": call["call_id"], "action": "pre_accept", "session": session})
        _post(bot_row, "calls", {"messaging_product": "whatsapp", "call_id": call["call_id"], "action": "accept", "session": session})
    except CallError:
        db.release_call(call["call_id"])                           # فشل Meta ⇒ تعود ترنّ لزميل آخر
        raise
    db.set_conversation_mode(bot_row["id"], call["peer"], "human")
    return True


def reject(bot_row, call):
    if not db.claim_call(call["call_id"], None, status="rejected"):
        raise CallError("taken")
    try:
        _post(bot_row, "calls", {"messaging_product": "whatsapp", "call_id": call["call_id"], "action": "reject"})
    except CallError:
        db.release_call(call["call_id"])                           # ما زالت ترنّ عند العميل — تعود للفريق
        raise


def hangup(bot_row, call):
    _post(bot_row, "calls", {"messaging_product": "whatsapp", "call_id": call["call_id"], "action": "terminate"})


# ─────────────────────────── المكالمات الصادرة ───────────────────────────
PERMISSION_TEXT = "نحب نتصل بك على واتساب لنكمل طلبك — هل توافق؟"


def on_permission(bot_id, peer, p):
    """ردّ العميل على طلب الإذن (من محرك الفلو). الدائم بلا انتهاء؛ المؤقت حتى `expires` من Meta."""
    expires = 0 if p.get("permanent") else int(p.get("expires") or (time.time() + 7 * 86400))
    db.set_call_permission(bot_id, peer, bool(p.get("accept")), expires)


def permission(bot_id, peer, now=None):
    """granted · declined · expired · none"""
    p = db.get_call_permission(bot_id, peer)
    if not p:
        return "none"
    if not p["granted"]:
        return "declined"
    return "expired" if p["expires_at"] and p["expires_at"] <= (now or time.time()) else "granted"


def request_permission(bot_row, peer, text=""):
    """رسالة تفاعلية بزر «السماح بالاتصال» — داخل نافذة الـ24 ساعة (المسار يتحقّق)."""
    body = {"messaging_product": "whatsapp", "recipient_type": "individual", "to": peer.split(":", 1)[-1],
            "type": "interactive", "interactive": {"type": "call_permission_request",
                                                   "action": {"name": "call_permission_request"},
                                                   "body": {"text": (text or PERMISSION_TEXT)[:1024]}}}
    _post(bot_row, "messages", body)
    db.log_message(bot_row["id"], peer, "out", "human", "📞 طلبنا إذن الاتصال بالعميل")


def dial(bot_row, peer, agent_id, sdp_offer):
    """اتصال صادر بعرض متصفح الموظف ⇒ معرّف المكالمة. الجواب يصل بويبهوك connect (BUSINESS_INITIATED)."""
    sdp = str(sdp_offer or "")
    if not sdp.startswith("v=0") or len(sdp) > SDP_MAX:
        raise CallError("sdp")
    if permission(bot_row["id"], peer) != "granted":
        raise CallError("permission")
    if db.agent_busy(agent_id):
        raise CallError("busy")
    res = _post(bot_row, "calls", {"messaging_product": "whatsapp", "to": peer.split(":", 1)[-1], "action": "connect",
                                   "session": {"sdp_type": "offer", "sdp": sdp}})
    cid = str(((res.get("calls") or [{}])[0]).get("id") or "")
    if not _CALL_ID.fullmatch(cid):
        raise CallError("meta")
    db.add_out_call(bot_row["id"], cid, peer, agent_id)
    db.set_conversation_mode(bot_row["id"], peer, "human")
    return cid


def set_enabled(bot_row, enabled):
    """تفعيل زر الاتصال على الرقم (يظهر للعملاء في المحادثة وملف النشاط)."""
    return _post(bot_row, "settings", {"calling": {"status": "enabled" if enabled else "disabled",
                                                    "call_icon_visibility": "DEFAULT",
                                                    "callback_permission_status": "ENABLED" if enabled else "DISABLED"}})
