"""التسلسلات — المرحلة 6 من docs/ENTERPRISE_PLAN.md: متابعة آلية على خطوات بتأخير لكل عميل.

عميل يُسجَّل (يدوياً من الصندوق · بوسم · ببطاقة في الفلو) فتصله الخطوات في مواعيدها. قواعد لا تُكسر:
  · STOP يوقف كل تسجيلات العميل فوراً (db.set_opt_out) ولا يُرسل لمن طلب الإيقاف أبداً (§55).
  · نافذة الـ24 ساعة: خطوة «نص» خارج النافذة على واتساب/ماسنجر لا تُرسل (تُتخطّى أو تُوقف التسلسل
    حسب إعداد الخطوة) — والقالب هو الطريق الوحيد خارجها.
  · القالب بقواعد مال البث حرفياً عبر flow_graph._send_template (الفئة من Meta · خصم ذرّي قبل الإرسال ·
    ردّ في finally). لا منطق مال هنا.
  · ردّ العميل يوقف التسلسل (ما لم يُطفأ `stop_on_reply`)، وتولّي موظف للمحادثة يوقفه أيضاً.
  · كل خطوة تُحجز ذرّياً قبل إرسالها (db.claim_enrollment) — لا إرسال مزدوج من دورتين.
الإرسال في حلقة البوتات (bot_manager.sequence_tick كل 30ث).
"""
import logging
import re
import time
from datetime import datetime, timedelta, timezone

import database as db

log = logging.getLogger("sequences")

MAX_STEPS = 10
MAX_DELAY = 30 * 24 * 60          # دقائق — شهر
WINDOW = 24 * 3600
RETRY_OFFLINE = 600               # بوت تليجرام متوقّف: نعيد المحاولة بعد عشر دقائق


class Invalid(ValueError):
    pass


def _s(v, n):
    return str(v or "").strip()[:n]


def clean_spec(raw, tag_names=None):
    """مواصفة من الواجهة ⇒ مواصفة نظيفة أو Invalid(رمز)."""
    raw = raw or {}
    steps_in = raw.get("steps") or []
    if not 1 <= len(steps_in) <= MAX_STEPS:
        raise Invalid("steps")
    steps = []
    for i, st in enumerate(steps_in):
        st = st or {}
        try:
            delay = max(0, min(MAX_DELAY, int(st.get("delay") or 0)))
        except (TypeError, ValueError):
            raise Invalid(f"step:{i}:delay")
        kind = st.get("kind") if st.get("kind") in ("text", "template") else "text"
        out = {"delay": delay, "kind": kind}
        if kind == "text":
            out["text"] = _s(st.get("text"), 1024)
            if not out["text"]:
                raise Invalid(f"step:{i}:text")
            out["closed"] = "stop" if st.get("closed") == "stop" else "skip"
        else:
            tp = st.get("template") or {}
            name, lang = _s(tp.get("name"), 512), _s(tp.get("lang"), 15) or "ar"
            if not re.fullmatch(r"[a-z0-9_]{1,512}", name) or not re.fullmatch(r"[A-Za-z_]{2,15}", lang):
                raise Invalid(f"step:{i}:template")
            out["template"] = {"name": name, "lang": lang, "vars": [_s(v, 1000) or "-" for v in (tp.get("vars") or [])][:20]}
        steps.append(out)
    trig = raw.get("trigger") or {}
    trigger = {"type": "tag", "tag": _s(trig.get("tag"), 50)} if trig.get("type") == "tag" else {"type": "manual"}
    if trigger["type"] == "tag" and (not trigger["tag"] or (tag_names is not None and trigger["tag"].lower() not in tag_names)):
        raise Invalid("trigger")
    hours = None
    h = raw.get("hours")
    if h:
        try:
            hours = {"start": max(0, min(23, int(h.get("start", 9)))), "end": max(1, min(24, int(h.get("end", 21)))),
                     "tz": max(-12.0, min(14.0, float(h.get("tz", 3))))}
        except (TypeError, ValueError):
            raise Invalid("hours")
        days = sorted({int(d) for d in (h.get("days") or range(7)) if str(d).isdigit() and 0 <= int(d) <= 6})
        hours["days"] = days or list(range(7))
        if hours["end"] <= hours["start"]:
            raise Invalid("hours")
    return {"steps": steps, "trigger": trigger, "stop_on_reply": raw.get("stop_on_reply", True) is not False,
            "hours": hours}


def fit(ts, hours):
    """أقرب لحظة ≥ ts داخل ساعات الإرسال المفضّلة (أيام Python: 0 الاثنين)."""
    if not hours:
        return int(ts)
    tz = timezone(timedelta(hours=hours["tz"]))
    t = datetime.fromtimestamp(ts, tz)
    for _ in range(9):
        if t.weekday() in hours["days"] and hours["start"] <= t.hour < hours["end"]:
            return int(t.timestamp())
        if t.weekday() in hours["days"] and t.hour < hours["start"]:
            t = t.replace(hour=hours["start"], minute=0, second=0, microsecond=0)
            continue
        t = (t + timedelta(days=1)).replace(hour=hours["start"], minute=0, second=0, microsecond=0)
    return int(ts)


def enroll(seq, bot_id, peer, now=None):
    """يسجّل العميل ويرجّع رقم التسجيل، أو None (مسجَّل بالفعل · طلب الإيقاف · قناة أخرى · تسلسل متوقّف)."""
    if not seq or not seq["active"] or seq["bot_id"] != bot_id or not db.peer_known(bot_id, peer):
        return None
    if db.is_opted_out(bot_id, peer):
        return None
    now = int(now or time.time())
    steps = seq["spec"]["steps"]
    return db.enroll_peer(seq["id"], bot_id, peer, fit(now + steps[0]["delay"] * 60, seq["spec"].get("hours")))


def on_tags(owner_id, contact_id, tag_names):
    """وسم أُضيف لجهة اتصال ⇒ تسجيلها في كل تسلسل نشط يشغّله هذا الوسم (على قناة التسلسل)."""
    seqs = db.sequences_for_tags(owner_id, tag_names)
    if not seqs:
        return 0
    with db.get_conn() as c:
        peers = [(r[0], r[1]) for r in c.execute("SELECT bot_id, peer FROM contact_peers WHERE contact_id=?", (contact_id,))]
    n = 0
    for s in seqs:
        for bot_id, peer in peers:
            if bot_id == s["bot_id"] and enroll(s, bot_id, peer):
                n += 1
    return n


def due(now=None, limit=100):
    """[(تسجيل, تسلسل, بوت)] حلّ موعدها وحُجزت ذرّياً للإرسال."""
    now = int(now or time.time())
    out, cache = [], {}
    for e in db.due_enrollments(now, limit):
        if not db.claim_enrollment(e["id"], e["step"], e["next_at"]):
            continue
        sid = e["sequence_id"]
        if sid not in cache:
            s = db.get_sequence(sid)
            b = db.get_bot(s["bot_id"]) if s else None
            cache[sid] = (s, dict(b) if b else None)
        s, b = cache[sid]
        out.append((e, s, b))
    return out


async def run_step(bot_row, channel, e, seq, now=None):
    """يرسل خطوة واحدة لتسجيل محجوز ثم يجدول التالية أو ينهيه."""
    import flow_engine as FE
    import flow_graph as FG
    now = int(now or time.time())
    if not seq or not bot_row:
        db.end_enrollment(e["id"], "stopped", "deleted")
        return
    bot_id, peer, i = bot_row["id"], e["peer"], e["step"]
    steps = seq["spec"]["steps"]
    if i >= len(steps):
        db.end_enrollment(e["id"], "done")
        return
    if db.is_opted_out(bot_id, peer):
        db.end_enrollment(e["id"], "stopped", "opted_out")
        return
    if FE.human_active(bot_id, peer):
        db.end_enrollment(e["id"], "stopped", "human")
        return
    if channel is None:                                   # البوت متوقّف — لا يضيع، يُعاد لاحقاً
        db.advance_enrollment(e["id"], i, now + RETRY_OFFLINE)
        return
    st = steps[i]
    cid = db.contact_id_for_peer(bot_id, peer)
    contact = db.get_contact_by_id(cid) if cid else None
    say = lambda s: FG.render(s, {}, contact)
    ch = FE.LoggedChannel(channel, bot_id)
    ok, note = False, ""
    if st["kind"] == "text":
        meta = peer.startswith(("wa:", "fb:", "ig:"))
        if meta and now - (db.peer_last_in(bot_id, peer) or 0) > WINDOW:
            note = "window"
            if st.get("closed") == "stop":
                db.log_sequence_send(e["id"], seq["id"], i, False, note)
                db.end_enrollment(e["id"], "stopped", "window")
                return
        else:
            try:
                res = await ch.remove_keyboard(peer, say(st["text"]))
                ok = not (res is None and meta)
            except Exception:
                log.exception("sequence %s text step bot=%s", seq["id"], bot_id)
            note = "" if ok else "send"
    else:
        tp = st["template"]
        node = {"name": tp["name"], "lang": tp["lang"], "vars": tp.get("vars") or []}
        ok = await FG._send_template(bot_row, ch, peer, {"id": f"seq{seq['id']}"}, node, say)
        note = "" if ok else "template"
    db.log_sequence_send(e["id"], seq["id"], i, ok, note)
    if i + 1 < len(steps):
        db.advance_enrollment(e["id"], i + 1, fit(now + steps[i + 1]["delay"] * 60, seq["spec"].get("hours")))
    else:
        db.end_enrollment(e["id"], "done")
