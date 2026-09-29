"""البث 2.0 — المرحلة 3 من docs/ENTERPRISE_PLAN.md: حملات قوالب واتساب على **جهات الاتصال**،
فورية أو مجدولة، بإعادة محاولة ذكية وتحليلات لكل حالة وإعادة استهداف.

هذا الملف هو المسار الوحيد لإطلاق حملة (من الصفحة ومن المجدوِل معاً)، ويلتزم حرفياً بقواعد
المال في AGENTS.md:
  §20 الفئة من Meta لا من الفورم — تعذّر قراءتها = لا إرسال.
  §19 المال قروش صحيحة؛ الخصم ذرّي **قبل** الإرسال (`wallet_charge` يرفض لو لم يكفِ).
  §22 التكلفة على القائمة نفسها التي تُرسَل إليها (`campaign_recipients` لقطة ثابتة)،
      والردّ = المخصوم − المقبول × السعر، داخل finally.
  §38 في الخلفية، حملة واحدة لكل بوت (`manager.start_campaign`)، ولا `.result(timeout)`.
  §55 STOP مستبعد دائماً (`db.campaign_audience`).
الحملة المجدولة تُخصم **عند الإرسال** لا عند الجدولة — الرصيد قد يتغيّر بينهما.

دوال التسعير والفئة تبقى في app.py (مصدر واحد) وتُحقن هنا عبر `configure()`.
"""
import json
import logging
import time

import database as db
import msg_status as MS
import tpl_studio as TS

log = logging.getLogger("broadcasts")

_HOOKS = {}
AUDIENCE_TYPES = ("segment", "all", "subscribers", "retarget")
RETARGET_STATES = ("sent", "delivered", "read", "not_read", "replied", "delivered_not_replied", "failed")
# ما يستحق إعادة المحاولة: فشل مؤقت لا عيب في الرقم أو القالب
RETRYABLE = ("frequency_limit", "rate_limit", "meta_unavailable")
RETRY_EVERY = 6 * 3600
RETRY_MAX_HOURS = 72
MAX_ATTEMPTS = 4
MAX_VARS = 20


def configure(**hooks):
    """app.py يمرّر: category(bot_row, name, lang) · quote(owner, n, category) · manager."""
    _HOOKS.update(hooks)


# ─────────────────────────── المتغيّرات ───────────────────────────
def clean_vars(raw, fields):
    """ربط متغيّرات القالب من المتصفح ⇒ قائمة نظيفة أو ValueError.
    كل متغيّر: {"src": "text", "text": …} أو {"src": "contact", "field": name|phone|email|f:<key>, "fallback": …}."""
    if not isinstance(raw, list) or len(raw) > MAX_VARS:
        raise ValueError("vars")
    out = []
    for v in raw:
        if not isinstance(v, dict):
            raise ValueError("vars")
        if v.get("src") == "contact":
            f = str(v.get("field") or "")
            if f not in ("name", "phone", "email") and not (f.startswith("f:") and f[2:] in fields):
                raise ValueError("var_field")
            out.append({"src": "contact", "field": f, "fallback": str(v.get("fallback") or "")[:200]})
        else:
            t = str(v.get("text") or "").strip()[:1000]
            if not t:
                raise ValueError("var_empty")
            out.append({"src": "text", "text": t})
    return out


def _value(spec, contact):
    if spec["src"] == "text":
        return spec["text"]
    f = spec["field"]
    if f.startswith("f:"):
        v = (contact.get("fields") or {}).get(f[2:])
        v = ", ".join(map(str, v)) if isinstance(v, list) else v
    else:
        v = contact.get(f)
    v = str(v).strip() if v not in (None, "") else ""
    # Meta ترفض معاملاً فارغاً (132000) — البديل ثم شرطة، لا رسالة فاشلة
    return (v or spec.get("fallback") or "-")[:1000]


def build_components(camp, contact, media_id=None, card_media=None):
    """مكوّنات قالب لمستلم واحد. حملة بمواصفة قالب (`extra.spec`، المرحلة 4) تمرّ بـ
    tpl_studio.send_components فتدعم أزرار الرابط بمتغيّر والكوبون والعدّاد والموقع والبطاقات؛
    حملات المرحلة 3 بلا مواصفة تبقى على السلوك القديم حرفياً."""
    ex = camp.get("extra") or {}
    header = camp.get("header") or {}
    if ex.get("spec"):
        val = lambda s: _value(s, contact)
        url_of = lambda d: {int(k): val(v) for k, v in (d or {}).items()}
        cards = [{"media_id": (card_media or {}).get(c.get("asset_id")),
                  "body": [val(s) for s in c.get("vars") or []], "url_values": url_of(c.get("url"))}
                 for c in ex.get("cards") or []]
        return TS.send_components(
            ex["spec"], [val(s) for s in header.get("vars") or []] if header.get("format") == "TEXT" else (),
            [val(s) for s in camp.get("vars") or []], media_id, ex.get("location"), url_of(ex.get("url")),
            ex.get("coupon"), (ex.get("expire_at") or 0) * 1000 or None, cards)
    comps = []
    fmt = header.get("format")
    if fmt in ("IMAGE", "VIDEO", "DOCUMENT") and media_id:
        k = fmt.lower()
        comps.append({"type": "header", "parameters": [{"type": k, k: {"id": media_id}}]})
    elif fmt == "TEXT" and header.get("vars"):
        comps.append({"type": "header", "parameters": [
            {"type": "text", "text": _value(s, contact)} for s in header["vars"]]})
    body = [_value(s, contact) for s in camp.get("vars") or []]
    if body:
        comps.append({"type": "body", "parameters": [{"type": "text", "text": v} for v in body]})
    return comps or None


# ─────────────────────────── الإطلاق ───────────────────────────
class LaunchError(Exception):
    """سبب مفهوم للواجهة: category · empty · balance · busy · charge · state · bot."""


def launch(cid, scheduled=False):
    """يطلق حملة (مسودة أو مجدولة حلّ وقتها). يرمي LaunchError بلا أي خصم عند الفشل.
    `scheduled`: من المجدوِل — الفشل يُسجَّل على الحملة بدل أن يعود للمستخدم."""
    camp = db.get_campaign(cid)
    if not camp or camp["status"] not in ("draft", "scheduled"):
        raise LaunchError("state")
    try:
        return _launch(camp)
    except LaunchError as e:
        if scheduled and str(e) != "busy":
            db.update_campaign(cid, status="failed", error=str(e), finished_at=int(time.time()))
            log.warning("scheduled campaign %s failed to launch: %s", cid, e)
        raise


def _launch(camp):
    cid, owner = camp["id"], camp["owner_id"]
    bot = db.get_bot(camp["bot_id"])
    if not bot or bot.get("owner_id") != owner or (bot.get("channel") or "") != "whatsapp":
        raise LaunchError("bot")
    # §20: الفئة من Meta الآن، لا المحفوظة عند الإنشاء (قد يعيد Meta تصنيف القالب)
    category = _HOOKS["category"](bot, camp["template"], camp["lang"])
    if category is None:
        raise LaunchError("category")
    audience = db.campaign_audience(owner, bot["id"], camp["audience"], bool(camp["policy_optin"]))
    if not audience:
        raise LaunchError("empty")
    q = _HOOKS["quote"](owner, len(audience), category)
    if q["billable"] and not q["enough"]:
        raise LaunchError("balance")
    # المطالبة بالحملة ذرّية: طلبان متزامنان (أو المجدوِل والمستخدم) لا يطلقانها مرتين
    if not db.claim_campaign(cid, camp["status"]):
        raise LaunchError("state")
    charged = 0
    if q["billable"]:
        if db.wallet_charge(owner, q["cost"], ref=f"campaign:{cid}",
                            note=f"campaign {camp['template']} ×{q['n']}") is None:
            db.update_campaign(cid, status=camp["status"])          # يعود كما كان — لا خصم
            raise LaunchError("charge")
        charged = q["cost"]
    db.snapshot_recipients(cid, audience)
    # المخصوم الصافي والمردود يتراكمان عند انتهاء كل جولة (finish_campaign_round) — فأرقام الحملة
    # تطابق قيود المحفظة دائماً، في الإرسال الأول وكل إعادة محاولة
    db.update_campaign(cid, category=category, total=len(audience),
                       price=q["price"] if charged else 0, started_at=int(time.time()), error=None)
    items = db.campaign_send_items(cid)
    if not _start(camp, bot, items, charged, q["price"] if charged else 0, attempt=0):
        if charged:
            db.wallet_refund(owner, charged, ref=f"campaign:{cid}", note="another campaign is running")
        db.clear_recipients(cid)
        db.update_campaign(cid, status=camp["status"], total=0)
        raise LaunchError("busy")
    return {"total": len(audience), "charged": charged, "category": category}


def _start(camp, bot, items, charged, price, attempt):
    """يسلّم الإرسال لخيط الحملات. الردّ في finally: ما لم تقبله Meta يعود بسعر الخصم نفسه."""
    manager = _HOOKS["manager"]
    cid, owner = camp["id"], camp["owner_id"]

    def job(state):
        state.update(mode="campaign", label=camp["name"], total=len(items), campaign_id=cid)
        accepted = None
        try:
            accepted, failed = manager.send_campaign_items(bot["id"], camp, items, prog=state)
            return {"sent": accepted, "failed": failed}
        finally:
            got = accepted if accepted is not None else state.get("sent", 0)
            back = max(0, charged - got * price) if charged else 0
            if back:
                db.wallet_refund(owner, back, ref=f"campaign:{cid}",
                                 note=f"undelivered {len(items) - got} of {len(items)}")
            db.finish_campaign_round(cid, charged - back, back, attempt)
            log.info("campaign %s attempt=%s items=%s accepted=%s charged=%s refunded=%s",
                     cid, attempt, len(items), got, charged, back)

    return manager.start_campaign(bot["id"], job)


# ─────────────────────────── المجدوِل وإعادة المحاولة ───────────────────────────
def tick(now=None):
    """يُستدعى دورياً من bot_manager: يطلق ما حلّ وقته ويعيد المحاولة لما يستحق."""
    if not _HOOKS:
        return                          # app لم يُحمَّل (عملية بلا ويب) — لا تسعير ولا فئة
    now = now or int(time.time())
    for cid in db.due_campaigns(now):
        try:
            launch(cid, scheduled=True)
        except LaunchError:
            pass                       # busy يبقى مجدولاً للدورة التالية؛ الباقي سُجّل على الحملة
        except Exception:
            log.exception("scheduled campaign %s", cid)
    for cid in db.retry_due_campaigns(now):
        try:
            retry(cid, now)
        except Exception:
            log.exception("campaign retry %s", cid)


def retry(cid, now=None):
    """جولة إعادة: المستلمون الذين فشلوا فشلاً مؤقتاً فقط، بخصم جديد على عددهم وحده."""
    now = now or int(time.time())
    camp = db.get_campaign(cid)
    if not camp or camp["status"] != "done" or not camp["retry_until"] or camp["retry_until"] <= now:
        return None
    bot = db.get_bot(camp["bot_id"])
    items = db.retryable_items(cid, RETRYABLE, MAX_ATTEMPTS)
    if not bot or not items:
        db.update_campaign(cid, next_retry_at=None)
        return 0
    category = _HOOKS["category"](bot, camp["template"], camp["lang"])
    if category is None:
        db.update_campaign(cid, next_retry_at=now + RETRY_EVERY)      # Meta لا تجيب — نحاول لاحقاً
        return None
    q = _HOOKS["quote"](camp["owner_id"], len(items), category)
    if q["billable"] and not q["enough"]:
        db.update_campaign(cid, next_retry_at=None, error="retry_balance")
        return None
    if not db.claim_campaign(cid, "done"):
        return None
    charged = 0
    if q["billable"]:
        if db.wallet_charge(camp["owner_id"], q["cost"], ref=f"campaign:{cid}",
                            note=f"campaign retry ×{q['n']}") is None:
            db.update_campaign(cid, status="done")
            return None
        charged = q["cost"]
    attempt = (camp.get("retries") or 0) + 1
    if not _start(camp, bot, items, charged, q["price"] if charged else 0, attempt):
        if charged:
            db.wallet_refund(camp["owner_id"], charged, ref=f"campaign:{cid}", note="retry: bot busy")
        db.update_campaign(cid, status="done")
        return None
    return len(items)


def dumps(v):
    return json.dumps(v, ensure_ascii=False, separators=(",", ":"))
