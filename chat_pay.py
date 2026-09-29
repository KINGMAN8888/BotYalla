"""الدفع داخل المحادثة — المرحلة 9: «احجز وادفع دون مغادرة واتساب».

طلب دفع (من بطاقة «دفع» في الفلو أو زر في الصندوق المشترك) ⇒ رابط من بوابة صاحب النشاط (Moyasar/Tap)
يصل العميل بزر «ادفع الآن» ⇒ تأكيد تلقائي ⇒ رسالة إيصال · الفلو يكمل من فرع «دُفع» · تحويل Purchase لـ Meta ·
تنبيه للفريق. رابط انتهت مدته ⇒ فرع «لم يُدفع».

القواعد (AGENTS §67):
  · **البوابة هي المصدر:** لا ويبهوك ولا صفحة عودة يسوّي دفعة؛ كلاهما يطلب `confirm` الذي يسأل البوابة.
  · **تسوية ذرّية مرة واحدة** (`db.settle_chat_payment` من «معلّق» فقط) — لا إيصال مكرر ولا استئناف مزدوج.
  · **المال لا يمرّ بالمنصة ولا بمحفظتها:** مفتاح البوابة لصاحب الحساب، مختوم (`db.seal`) ولا يصل المتصفح.
  · المبلغ بالوحدة الصغرى صحيحاً.
"""
import asyncio
import hashlib
import hmac
import json
import logging
import time
from datetime import datetime, timezone

import database as db
import payments_gw as GW

log = logging.getLogger("chat_pay")

CFG_KEY = "pay_gateway"
MAX_AMOUNT = 10_000_000 * 100          # سقف عاقل لرابط واحد
CANCEL_WORDS = {"الغاء", "إلغاء", "cancel", "الغ", "لا اريد"}

# app.py يضبطها: سرّ التوقيع · أصل الموقع · قناة البوت · تشغيل coroutine في حلقة البوتات
HOOKS = {"secret": b"", "base": lambda: "", "channel": lambda bot_row, peer: None, "run": None}


# ─────────────────────────── الإعداد ───────────────────────────
def config(owner_id):
    raw = db.get_setting(owner_id, CFG_KEY)
    if not raw:
        return None
    try:
        c = json.loads(raw)
    except ValueError:
        return None
    if c.get("provider") not in GW.PROVIDERS or not c.get("secret"):
        return None
    return {"provider": c["provider"], "currency": c.get("currency") or "SAR",
            "secret": db.unseal(c["secret"]), "webhook_secret": db.unseal(c.get("webhook_secret") or ""),
            "entity": c.get("entity") or "", "entity_mada": c.get("entity_mada") or "", "test": bool(c.get("test"))}


def public_config(owner_id):
    raw = db.get_setting(owner_id, CFG_KEY)
    c = json.loads(raw) if raw else {}
    return {"provider": c.get("provider") or "", "currency": c.get("currency") or "SAR",
            "hasSecret": bool(c.get("secret")), "hasWebhookSecret": bool(c.get("webhook_secret")),
            "entity": c.get("entity") or "", "entity_mada": c.get("entity_mada") or "", "test": bool(c.get("test"))}


def gw_opts(cfg):
    """خيارات البوابة غير السرّية (HyperPay: الكيانات ووضع الاختبار)."""
    return {"entity": cfg.get("entity"), "entity_mada": cfg.get("entity_mada"), "test": cfg.get("test")}


def save_config(owner_id, provider, currency, secret=None, webhook_secret=None, entity="", entity_mada="", test=False):
    old = json.loads(db.get_setting(owner_id, CFG_KEY) or "{}")
    c = {"provider": provider, "currency": currency,
         "secret": db.seal(secret) if secret else old.get("secret"),
         "webhook_secret": db.seal(webhook_secret) if webhook_secret else old.get("webhook_secret"),
         "entity": entity or "", "entity_mada": entity_mada or "", "test": bool(test)}
    if old.get("provider") and old["provider"] != provider and not secret:
        c["secret"] = None                                   # بوابة جديدة بلا مفتاحها = لا مفتاح
    db.set_setting(owner_id, CFG_KEY, json.dumps(c))


def clear_config(owner_id):
    db.set_setting(owner_id, CFG_KEY, "")


def _sig(*parts):
    return hmac.new(HOOKS["secret"], ":".join(map(str, parts)).encode(), hashlib.sha256).hexdigest()[:32]


def webhook_url(owner_id, provider):
    return f"{HOOKS['base']()}/pay/wh/{provider}/{owner_id}/{_sig('paywh', owner_id, provider)}"


def webhook_ok(owner_id, provider, sig):
    return hmac.compare_digest(str(sig or ""), _sig("paywh", owner_id, provider))


def return_url(pid):
    return f"{HOOKS['base']()}/pay/r/{pid}/{_sig('payr', pid)}"


def return_ok(pid, sig):
    return hmac.compare_digest(str(sig or ""), _sig("payr", pid))


def hosted_url(pid):
    """صفحة الدفع عندنا (HyperPay: نموذج البطاقة بسكربتهم داخل صفحتنا)."""
    return f"{HOOKS['base']()}/pay/h/{pid}/{_sig('payh', pid)}"


def hosted_ok(pid, sig):
    return hmac.compare_digest(str(sig or ""), _sig("payh", pid))


def fmt(amount, currency):
    f = GW.minor_factor(currency)
    v = amount / f
    return f"{v:,.{3 if f == 1000 else 2}f}".rstrip("0").rstrip(".") + f" {currency}"


def to_minor(value, currency):
    """«250» أو «٢٥٠٫٥» أو 250.5 ⇒ وحدة صغرى صحيحة، أو None."""
    s = str(value or "").strip().translate(str.maketrans("٠١٢٣٤٥٦٧٨٩٫", "0123456789.")).replace(",", "")
    try:
        v = round(float(s) * GW.minor_factor(currency))
    except ValueError:
        return None
    return v if 0 < v <= MAX_AMOUNT else None


# ─────────────────────────── الطلب ───────────────────────────
async def request(bot_row, channel, peer, amount, currency, description, *, minutes=60, text="", button="",
                  flow_id=None, node_id=None, created_by=None, name=""):
    """يُنشئ رابط الدفع ويرسله للعميل. يرجّع (الدفعة, None) أو (None, سبب)."""
    owner = bot_row["owner_id"]
    cfg = config(owner)
    if not cfg:
        return None, "not_configured"
    if not str(HOOKS["base"]() or "").startswith(("https://", "http://")):
        log.warning("payment link refused: PUBLIC_URL is not set (return/webhook URLs would be relative)")
        return None, "no_base"
    currency = currency or cfg["currency"]
    if currency not in GW.CURRENCIES or not isinstance(amount, int) or not 0 < amount <= MAX_AMOUNT:
        return None, "amount"
    minutes = max(5, min(24 * 60, int(minutes or 60)))
    expires = int(time.time()) + minutes * 60
    pid = db.create_chat_payment(owner, bot_row["id"], peer, cfg["provider"], amount, currency, description or "",
                                 expires, flow_id, node_id, created_by)
    try:
        gw_id, url = await asyncio.to_thread(
            GW.create, cfg["provider"], cfg["secret"], amount=amount, currency=currency,
            description=description or f"#{pid}", ref=f"by{pid}", return_url=return_url(pid),
            webhook_url=webhook_url(owner, cfg["provider"]),
            expires_at_iso=datetime.fromtimestamp(expires, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            customer_name=name, peer=peer)
    except GW.GatewayError as e:
        db.settle_chat_payment(pid, "failed")
        log.info("payment link failed owner=%s: %s", owner, e)
        return None, f"gateway_{e}"
    url = url or hosted_url(pid)
    db.set_chat_payment_link(pid, gw_id, url)
    body = (text or "💳 رابط الدفع جاهز") + f"\n\n{description}\nالمبلغ: {fmt(amount, currency)}".rstrip()
    sent = await channel.send_cta(peer, body.strip(), (button or "ادفع الآن")[:20], url)
    if _undelivered(channel, sent):
        db.settle_chat_payment(pid, "failed")               # لم يصل العميل — لا رابط «معلّق» يظنّه الفريق أُرسل
        return None, "send"
    db.log_event(bot_row["id"], "pay_request")
    return db.get_chat_payment(pid), None


def _undelivered(channel, res):
    """نفس عُرف `LoggedChannel._log`: واتساب وماسنجر/إنستجرام ترجّع None حين يُرفض الإرسال."""
    raw = getattr(channel, "_c", channel)
    return res is None and (getattr(raw, "phone_id", None) is not None or getattr(raw, "page_id", None) is not None)


# ─────────────────────────── التأكيد ───────────────────────────
def confirm(pid, now=None):
    """يسأل البوابة عن الدفعة، ويسوّيها مرة واحدة إن تغيّرت حالتها. يرجّع الحالة الحالية.
    يستدعيه الويبهوك وصفحة العودة وكاتب العميل «دفعت» والمسح الدوري — كلهم بنفس الطريق."""
    p = db.get_chat_payment(pid)
    if not p or p["status"] in ("paid", "failed") or not p.get("gw_id"):
        return (p or {}).get("status")
    cfg = config(p["owner_id"])
    if not cfg or cfg["provider"] != p["provider"]:
        return p["status"]
    try:
        st = GW.status(p["provider"], cfg["secret"], p["gw_id"], opts=gw_opts(cfg))
    except GW.GatewayError:
        return p["status"]
    if p["status"] != "pending":
        # ملغاة/منتهية محلياً ثم دفع العميل فعلاً: المال وصل — تُسجَّل مدفوعة ويصله إيصاله
        if st == "paid" and db.settle_chat_payment(pid, "paid", ("cancelled", "expired")):
            _dispatch(after_settle(pid))
            return "paid"
        return p["status"]
    if st == "pending" and p["expires_at"] <= (now or time.time()):
        st = "expired"
    if st != "pending" and db.settle_chat_payment(pid, st):
        _dispatch(after_settle(pid))
    return st


def _dispatch(coro):
    run = HOOKS.get("run")
    if run:
        run(coro)
    else:
        asyncio.run(coro)


async def after_settle(pid):
    """ما بعد التسوية: إيصال أو اعتذار · استئناف الفلو من فرعه · Meta · تنبيه الفريق."""
    import flow_engine as FE
    p = db.get_chat_payment(pid)
    bot_row = db.get_bot(p["bot_id"]) if p else None
    if not bot_row:
        return
    bot_row = dict(bot_row)
    raw = HOOKS["channel"](bot_row, p["peer"])
    ch = FE.LoggedChannel(raw, bot_row["id"]) if raw else None
    paid = p["status"] == "paid"
    amount = fmt(p["amount"], p["currency"])
    if paid:
        db.log_event(bot_row["id"], "pay_paid")
        import growth
        growth.capi_async(bot_row, p["peer"], "Purchase", p["amount"] / GW.minor_factor(p["currency"]), p["currency"])
        if ch:
            try:
                await FE.notify_owner(bot_row, ch, f"💳 دفعة جديدة {amount} — {p['description'] or ''} ({p['peer']})")
            except Exception:
                log.exception("payment owner notify failed")
    resumed = await _resume_flow(bot_row, ch, p) if p.get("flow_id") else False
    if not resumed and ch:
        text = (f"✅ تم استلام دفعتك {amount} — شكراً لك! رقم العملية #{p['id']}" if paid
                else "⌛ لم يكتمل الدفع وانتهى الرابط. اكتب لنا لو حاب نرسل رابطاً جديداً.")
        await ch.remove_keyboard(p["peer"], text)


async def _resume_flow(bot_row, ch, p):
    """الفلو ينتظر عند بطاقة الدفع نفسها؟ يكمل من «دُفع» أو «لم يُدفع». غير ذلك (العميل غادر) = لا شيء."""
    import flow_graph as FG
    if not ch:
        return False
    st = db.get_chat_state(bot_row["id"], p["peer"])
    g = (st or {}).get("data", {}).get("__g") if st and st["step"] == FG.GRAPH_STEP else None
    if not g or g.get("f") != p["flow_id"] or g.get("n") != p["node_id"]:
        return False
    cfg = json.loads(bot_row.get("config_json") or "{}")
    flow = FG._test_flow(cfg, g["t"]) if g.get("t") else FG._find(cfg, p["flow_id"])
    node = ((flow or {}).get("published") or {}).get("nodes", {}).get(p["node_id"])
    if not node:
        return False
    data = st["data"]
    data.pop("__pay", None)
    if node.get("var"):
        data[node["var"]] = "paid" if p["status"] == "paid" else p["status"]
    data["payment_ref"] = f"#{p['id']}"
    if p["status"] == "paid":
        await ch.remove_keyboard(p["peer"], f"✅ تم استلام دفعتك {fmt(p['amount'], p['currency'])} — رقم العملية #{p['id']}")
        nxt = node.get("next")
    else:
        nxt = node.get("fail")
    await FG.run(bot_row, cfg, ch, p["peer"], flow, nxt, data, g.get("s"))
    return True


_CHECKED = {}                                # دفعة ⇒ آخر سؤال للبوابة (الذاكرة تكفي — المسح كل 30 ثانية)
POLL_EVERY = 120


def sweep(now=None):
    """(1) الروابط المعلّقة: سؤال البوابة كل دقيقتين لكل دفعة — HyperPay بلا ويبهوك، وأي ويبهوك قد يضيع.
    (2) روابط انتهت مدتها: سؤال أخير للبوابة (ربما دُفعت ولم يصل الإشعار) ثم «منتهية»."""
    t = int(now or time.time())
    for p in db.pending_chat_payments(t - 60, t):
        if t - _CHECKED.get(p["id"], 0) >= POLL_EVERY:
            _CHECKED[p["id"]] = t
            try:
                confirm(p["id"], now)
            except Exception:
                log.exception("payment poll failed id=%s", p["id"])
    if len(_CHECKED) > 5000:
        _CHECKED.clear()
    for p in db.due_chat_payments(int(now or time.time())):
        if not p.get("gw_id"):
            if db.settle_chat_payment(p["id"], "failed"):
                _dispatch(after_settle(p["id"]))
            continue
        confirm(p["id"], now)
