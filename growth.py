"""النمو — المرحلة 7 من docs/ENTERPRISE_PLAN.md: روابط التتبّع · إعلانات Click-to-WhatsApp · Conversions API.

**النسبة (attribution)** تحدث لكل رسالة واردة قبل أي محرك (flow_engine.handle_message):
  · رابط تتبّع: واتساب يحمل الرمز في آخر الرسالة المعبّأة مسبقاً (`… #a1b2c3`)، وتليجرام في
    `/start l-<code>`، وماسنجر في `ref=l-<code>`. الرمز يُحذف من النص قبل الفلو — فلا يكسر كلمات المشغّل.
    يُحتسب فقط لو الرابط لهذا البوت نفسه (رمز بوت آخر = نص عادي).
  · إعلان CTWA: Meta ترفق `referral` بأول رسالة؛ يُحفظ بـ`ctwa_clid` الذي يربط التحويلات لاحقاً.

**Conversions API** (إرسال التحويلات لـ Meta ليتعلّم الإعلان من يشتري): فقط لعميل جاء من إعلان خلال
7 أيام، وفقط لقناة ضبط صاحبها Dataset ID ورمز الوصول (سرّ تشغيلي في `_SECRET_CFG` لا يصل المتصفح).
الإرسال في خيط خلفي — لا يؤخّر رد البوت — ونتيجته تُسجَّل (`capi_events`) ليراها صاحب الحساب.
"""
import logging
import re
import secrets
import string
import threading
import time

import database as db

log = logging.getLogger("growth")

LINK_RE = re.compile(r"(?:^|\s)#([a-z0-9]{6})\s*$")
TG_START_RE = re.compile(r"^/start\s+l-([a-z0-9]{6})$")
CODE_RE = re.compile(r"^[a-z0-9]{6}$")
CAPI_EVENTS = ("LeadSubmitted", "Purchase", "InitiateCheckout", "AddToCart", "ViewContent", "QualifiedLead", "OrderCreated")
GRAPH = "https://graph.facebook.com/v21.0"
START_WORDS = {"/start", "start", "بدء", "ابدأ", "مرحبا", "مرحباً", "السلام عليكم", "hi", "hello", "hey"}


def new_code():
    """6 حروف وأرقام، فيها رقم واحد على الأقل — فلا تتصادم مع رموز الشرائح (`#market` حروف فقط)."""
    alphabet = string.ascii_lowercase + string.digits
    while True:
        c = "".join(secrets.choice(alphabet) for _ in range(6))
        if any(ch.isdigit() for ch in c) and any(ch.isalpha() for ch in c):
            return c


def attribute(bot_row, peer, msg):
    """ينسب الرسالة لرابط تتبّع أو إعلان، ويرجّع الرسالة بلا رمز الرابط."""
    bot_id = bot_row["id"]
    ref = msg.get("referral")
    if isinstance(ref, dict):
        try:
            db.record_ad_referral(bot_id, peer, ref)
            db.log_event(bot_id, "src_ad")
        except Exception:
            log.exception("could not record ad referral bot=%s", bot_id)
    if msg.get("kind") not in ("text", "start"):
        return msg
    text = (msg.get("text") or "").strip()
    code, clean = None, text
    arg = msg.get("start_arg") or ""
    if arg.startswith("l-") and CODE_RE.match(arg[2:]):
        code = arg[2:]
    m = TG_START_RE.match(text) or None
    if m:
        code, clean = m.group(1), "/start"
    else:
        m = LINK_RE.search(text)
        if m:
            code, clean = m.group(1), text[:m.start()].rstrip()
    if not code or not db.growth_hit(bot_id, code, peer):
        return msg
    db.log_event(bot_id, "src_link")
    out = dict(msg, text=clean, link=code)           # `link`: مشغّل «رابط بعينه» في الفلو المرئي
    if msg.get("kind") == "text" and (not clean or clean.lower() in START_WORDS):
        out["kind"] = "start"                        # رسالة الرابط المعبّأة = بداية محادثة
    return out


def target_url(links, code, text):
    """رابط القناة الذي يحوّل إليه رابط التتبّع."""
    from urllib.parse import quote
    kind = links["kind"]
    if kind == "whatsapp":
        return f"{links['plain']}?text=" + quote(((text or "").strip() + f" #{code}").strip())
    if kind == "telegram":
        return f"{links['plain']}?start=l-{code}"
    return f"{links['plain']}?ref=l-{code}"


# ─────────────────────────── Conversions API ───────────────────────────
def capi_ready(cfg):
    return bool(cfg.get("capi_dataset") and cfg.get("capi_token"))


def capi_send(bot_row, peer, event, value=None, currency=None, http=None):
    """يرسل تحويلاً لـ Meta لعميل جاء من إعلان. يرجّع True/False، أو None إن لم ينطبق (لا إعداد · ليس من إعلان)."""
    import json as _json
    cfg = _json.loads(bot_row.get("config_json") or "{}")
    if event not in CAPI_EVENTS or not capi_ready(cfg) or (bot_row.get("channel") or "") != "whatsapp":
        return None
    ref = db.last_ad_referral(bot_row["id"], peer)
    if not ref or not ref.get("ctwa_clid"):
        return None
    data = {"event_name": event, "event_time": int(time.time()), "action_source": "business_messaging",
            "messaging_channel": "whatsapp",
            "user_data": {"whatsapp_business_account_id": str(cfg.get("wa_waba_id") or ""), "ctwa_clid": ref["ctwa_clid"]}}
    if value is not None:
        data["custom_data"] = {"value": float(value), "currency": (currency or "SAR").upper()[:3]}
    try:
        if http is None:
            import httpx
            http = httpx.Client(timeout=10)
        r = http.post(f"{GRAPH}/{cfg['capi_dataset']}/events", params={"access_token": cfg["capi_token"]},
                      json={"data": [data]})
        ok = r.status_code < 400
        err = "" if ok else (r.text or "")[:300].replace(cfg["capi_token"], "***")
    except Exception as e:
        ok, err = False, f"{type(e).__name__}: {str(e)[:200]}".replace(cfg["capi_token"], "***")
    db.log_capi_event(bot_row["id"], peer, event, value, currency, ok, err)
    if not ok:
        log.info("capi %s bot=%s failed: %s", event, bot_row["id"], err)
    return ok


def capi_async(bot_row, peer, event, value=None, currency=None):
    """نفس capi_send في خيط خلفي — لا ينتظره رد البوت."""
    if not capi_ready(__import__("json").loads(bot_row.get("config_json") or "{}")):
        return
    threading.Thread(target=capi_send, args=(dict(bot_row), peer, event, value, currency), daemon=True).start()
