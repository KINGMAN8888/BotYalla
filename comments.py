"""أتمتة التعليقات — المرحلة 8: تعليق على منشور فيسبوك أو إنستجرام ⇒ ردّ علني + رسالة خاصة (DM).

«اكتب "سعر" في التعليقات ونرسل لك التفاصيل في الخاص» — أشهر حيلة نمو على إنستجرام. عند تعليق يطابق
كلمة القاعدة: ردّ علني قصير (نصوص متعدّدة يُختار منها عشوائياً فلا يبدو آلياً) + رسالة خاصة للمعلّق
(Private Reply عبر Send API بـ `recipient.comment_id`) — ردّه عليها يفتح المحادثة ويكمل البوت بفلوهاته.

القواعد (AGENTS §69):
  · **مرة واحدة لكل تعليق** (`UNIQUE(bot_id, comment_id)`) — إعادة Meta للحدث لا تكرّر الرد.
  · تعليقات الصفحة/الحساب نفسه (ومنها ردودنا العلنية) تُتجاهل — لا حلقات.
  · «مرة لكل شخص في المنشور» اختيارية لكل قاعدة (لا نغرق من يعلّق مرتين).
  · Meta تسمح برسالة خاصة **واحدة** لكل تعليق خلال 7 أيام — لا نحاول غيرها.
"""
import logging
import random
import re
import time

import httpx

import database as db

log = logging.getLogger("comments")
GRAPH = "https://graph.facebook.com/v21.0"
TIMEOUT = 15
MAX_RULES = 30
CFG_KEY = "comment_auto"
_ID = re.compile(r"[\w\-]{1,80}")


class Invalid(Exception):
    pass


def _s(v, n):
    return str(v if v is not None else "").strip()[:n]


def _norm(t):
    t = str(t or "").lower().strip()
    t = re.sub(r"[ً-ْـ]", "", t)                      # تشكيل وتطويل
    return t.translate(str.maketrans("أإآة", "اااه"))


# ─────────────────────────── القواعد ───────────────────────────
def clean(raw):
    """{enabled, rules:[{id, name, match, keywords, posts, public, private, once}]} منظَّفة، أو Invalid."""
    raw = raw if isinstance(raw, dict) else {}
    rules_in = raw.get("rules") or []
    if not isinstance(rules_in, list) or len(rules_in) > MAX_RULES:
        raise Invalid("rules")
    out, ids = [], set()
    for r in rules_in:
        if not isinstance(r, dict):
            raise Invalid("rules")
        rid = _s(r.get("id"), 20) or f"r{len(out) + 1}"
        if not re.fullmatch(r"[\w\-]{1,20}", rid) or rid in ids:
            raise Invalid("id")
        ids.add(rid)
        match = r.get("match") if r.get("match") in ("any", "contains", "exact") else "contains"
        kws = [k for k in (_s(x, 40) for x in (r.get("keywords") or [])[:20]) if k]
        if match != "any" and not kws:
            raise Invalid("keywords")
        posts = [p for p in (_s(x, 80) for x in (r.get("posts") or [])[:30]) if p]
        if any(not _ID.fullmatch(p) for p in posts):
            raise Invalid("posts")
        public = [p for p in (_s(x, 300) for x in (r.get("public") or [])[:5]) if p]
        private = _s(r.get("private"), 900)
        if not public and not private:
            raise Invalid("action")
        out.append({"id": rid, "name": _s(r.get("name"), 60), "match": match, "keywords": kws, "posts": posts,
                    "public": public, "private": private, "once": bool(r.get("once", True)),
                    "active": bool(r.get("active", True))})
    return {"enabled": bool(raw.get("enabled", True)), "rules": out}


def pick(rules, text, post_id):
    """أول قاعدة مفعّلة تطابق المنشور والنص. المنشور المحدَّد أولى من «كل المنشورات»."""
    t = _norm(text)
    live = [r for r in rules if r.get("active", True)]
    for scoped in (True, False):
        for r in live:
            if bool(r["posts"]) != scoped or (scoped and post_id not in r["posts"]):
                continue
            if r["match"] == "any":
                return r
            words = [_norm(k) for k in r["keywords"]]
            if r["match"] == "exact" and t in words:
                return r
            if r["match"] == "contains" and any(w and w in t for w in words):
                return r
    return None


# ─────────────────────────── الأحداث ───────────────────────────
def extract(entry, pfx):
    """حدث صفحة ⇒ [{comment_id, post_id, text, user_id, user_name}] لتعليقات جديدة من غير الصفحة نفسها."""
    own = str(entry.get("id") or "")
    out = []
    for ch in entry.get("changes") or []:
        v = ch.get("value") or {}
        frm = v.get("from") or {}
        if pfx == "ig" and ch.get("field") == "comments":
            c = {"comment_id": _s(v.get("id"), 80), "post_id": _s((v.get("media") or {}).get("id"), 80),
                 "text": _s(v.get("text"), 1000), "user_id": _s(frm.get("id"), 80),
                 "user_name": _s(frm.get("username"), 80)}
        elif pfx == "fb" and ch.get("field") == "feed" and v.get("item") == "comment" and v.get("verb") == "add":
            c = {"comment_id": _s(v.get("comment_id"), 80), "post_id": _s(v.get("post_id"), 80),
                 "text": _s(v.get("message"), 1000), "user_id": _s(frm.get("id"), 80),
                 "user_name": _s(frm.get("name"), 80)}
        else:
            continue
        if c["comment_id"] and c["user_id"] and c["user_id"] != own:
            out.append(c)
    return out


def _fill(text, c):
    first = (c.get("user_name") or "").split(" ")[0]
    return text.replace("{{name}}", first).replace("{{username}}", c.get("user_name") or "")


async def _public_reply(http, pfx, comment_id, text, token):
    url = f"{GRAPH}/{comment_id}/replies" if pfx == "ig" else f"{GRAPH}/{comment_id}/comments"
    r = await http.post(url, params={"message": text, "access_token": token})
    return r.status_code < 400, "" if r.status_code < 400 else r.text[:200]


async def _private_reply(http, comment_id, text, token):
    r = await http.post(f"{GRAPH}/me/messages", params={"access_token": token},
                        json={"recipient": {"comment_id": comment_id}, "message": {"text": text}})
    return r.status_code < 400, "" if r.status_code < 400 else r.text[:200]


async def process(row, entry, pfx, token, http=None):
    """تعليقات حدث واحد ⇒ عدد ما رُدّ عليه. لا يرمي — الخطأ يُسجَّل في سجل التعليقات."""
    import json
    cfg = json.loads(row.get("config_json") or "{}").get(CFG_KEY) or {}
    if not cfg.get("enabled") or not cfg.get("rules") or not token:
        return 0
    comments = extract(entry, pfx)
    if not comments:
        return 0
    own_client = http is None
    http = http or httpx.AsyncClient(timeout=TIMEOUT)
    n = 0
    try:
        for c in comments:
            rule = pick(cfg["rules"], c["text"], c["post_id"])
            if not rule:
                continue
            if rule["once"] and db.comment_user_done(row["id"], rule["id"], c["post_id"], c["user_id"]):
                continue
            aid = db.claim_comment(row["id"], c, rule["id"])
            if not aid:
                continue                                         # وصل من قبل
            pub_ok = priv_ok = None
            err = ""
            try:
                if rule["public"]:
                    pub_ok, e = await _public_reply(http, pfx, c["comment_id"], _fill(random.choice(rule["public"]), c), token)
                    err = err or e
                if rule["private"]:
                    priv_ok, e = await _private_reply(http, c["comment_id"], _fill(rule["private"], c), token)
                    err = err or e
            except Exception as e:                               # شبكة — يُسجَّل ولا يسقط الحلقة
                log.info("comment reply failed bot=%s: %s", row["id"], e)
                err = type(e).__name__
            db.finish_comment(aid, pub_ok, priv_ok, err)
            if priv_ok:
                db.log_event(row["id"], "comment_dm")
            n += 1
    finally:
        if own_client:
            await http.aclose()
    return n


def stats(bot_id, since=None):
    return db.comment_stats(bot_id, since or int(time.time()) - 30 * 86400)
