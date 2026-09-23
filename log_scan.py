"""سحب سجل الخادم وتحليله — `logs/botyalla.log` وملفاته المدوّرة.

لماذا وحدة مستقلة عن التقرير: القراءة نفسها فيها ثلاث مخاطر لا علاقة لها
بالتقرير.

1. **الحجم** — عشرة ميجابايت × ستة ملفات. لا يُقرأ الكل: سقف بايتات لكل نداء،
   والقراءة من الأحدث إلى الأقدم، ومن كل ملف **ذيله** لا رأسه، فالتقرير يخصّ
   الأيام الأخيرة. ما لم يُقرأ يُعلَن (`truncated`) ولا يُخمَّن.
2. **الأسرار** — AGENTS.md §17 يمنع تسجيلها، وnothing يضمن أن مكتبة خارجية
   تلتزم. كل سطر يمرّ بـ`redact()` **قبل** أن يُحفظ في تجميع أو يُعرض أو يُرسل
   بالبريد: توكن بوت، مفتاح Fernet، بريد كامل، هاتف، `token=`/`password=`.
   الحجب قبل التخزين لا عند العرض — فلا تتسرّب نسخة في طريق آخر.
3. **الضجيج** — عطل واحد يكتب آلاف السطور المتشابهة. `signature()` تطبّع الأرقام
   والنصوص المقتبسة فتتجمّع في صفٍّ واحد بعدّاد وأول/آخر ظهور.

`parse()` و`aggregate()` و`signature()` دوالّ نقية تُختبر بنصٍّ جاهز بلا ملفات.
"""
import os
import re
import time
import logging

log = logging.getLogger("log_scan")

LOG_NAME = "botyalla.log"
ROTATIONS = 5                        # botyalla.log.1 … .5 (RotatingFileHandler)
MAX_BYTES = 12 * 1024 * 1024         # سقف ما يُقرأ في النداء الواحد
TAIL_BYTES = 4 * 1024 * 1024         # أقصى ما يُقرأ من ملف واحد (من آخره)
MAX_GROUPS = 30                      # أكثر الأعطال تكراراً
SAMPLE_LEN = 300

# 2026-09-23 10:11:12,345 ERROR botyalla: message
_LINE = re.compile(r"^(\d{4}-\d{2}-\d{2}) (\d{2}):(\d{2}):(\d{2}),\d+ "
                   r"([A-Z]+) ([\w.\- ]+): (.*)$")
_LEVELS = ("CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG")

# ---------------------------------------------------------------- الحجب
# كل نمط يُستبدل بعلامة مفهومة. الترتيب مهم: الأطول أولاً حتى لا يقطعه الأقصر.
_REDACT = (
    (re.compile(r"\b\d{6,12}:[A-Za-z0-9_-]{30,}"), "«توكن»"),          # توكن بوت تليجرام
    (re.compile(r"\bgAAAAA[A-Za-z0-9_\-=]{20,}"), "«مشفّر»"),          # Fernet
    (re.compile(r"(?i)\b(token|password|secret|api[_-]?key|code)=[^\s&\"']+"), r"\1=«محجوب»"),
    (re.compile(r"/reset/[A-Za-z0-9_\-]{10,}"), "/reset/«توكن»"),
    (re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}"), "«بريد»"),
    (re.compile(r"\b(?:\+?20|0)1[0-9]{9}\b"), "«هاتف»"),
    (re.compile(r"\b[0-9a-f]{32,}\b"), "«بصمة»"),
)


def redact(text):
    """يمسح كل ما يشبه سرّاً من سطر سجل. يُنادى **قبل** أي تخزين أو عرض."""
    s = str(text or "")
    for rx, rep in _REDACT:
        s = rx.sub(rep, s)
    return s


# ---------------------------------------------------------------- التوقيع
_NUM = re.compile(r"\d+")
_QUOTED = re.compile(r"(['\"])(?:(?!\1).){0,80}\1")
_WS = re.compile(r"\s+")


def signature(logger_name, msg, trace=""):
    """بصمة تجميع: نفس العطل بأرقام مختلفة (رقم بوت، رقم مستخدم، مسار) صفٌّ واحد.
    سطر الاستثناء الأخير أدقّ من نصّ الرسالة، فيُقدَّم عليه حين يوجد."""
    base = trace or msg
    s = _QUOTED.sub("'…'", base)
    s = _NUM.sub("#", s)
    return f"{logger_name}: {_WS.sub(' ', s).strip()[:160]}"


# ---------------------------------------------------------------- الإشارات
# أنماط نعرفها ونريد عدّها بالاسم — لأن رقمها وحده قرار تشغيلي.
_SIGNALS = (
    ("http_500",         re.compile(r"Exception on ")),
    ("capacity_refused", re.compile(r"bot start refused")),
    ("bot_start_failed", re.compile(r"(?i)(start failed|failed to start|Conflict)")),
    ("telegram_error",   re.compile(r"(?i)telegram\.error|TimedOut|NetworkError|RetryAfter")),
    ("whatsapp_failed",  re.compile(r"(?i)(whatsapp|wa) (send|template|message) failed|wa send")),
    ("ocr_off",          re.compile(r"(?i)ocr (unavailable|not available|disabled)")),
    ("ai_failed",        re.compile(r"(?i)(ai|gemini|groq).{0,20}(failed|error|quota)")),
    ("mail_failed",      re.compile(r"^mail failed")),
    ("mail_limited",     re.compile(r"^mail rate-limited")),
    ("mail_skipped",     re.compile(r"^mail skipped")),
    ("mail_sent",        re.compile(r"^mail sent")),
    ("payment_settled",  re.compile(r"(?i)payment .*(approved|rejected)")),
    ("db_locked",        re.compile(r"(?i)database is locked")),
)
_PATH = re.compile(r"Exception on (\S+)")


# ---------------------------------------------------------------- القراءة
def log_dir():
    """نفس ما يقرؤه `app.LOG_DIR` — بلا استيراد `app` (يستورد هذه الوحدة بدوره)."""
    return os.environ.get("BOTYALLA_LOGS") or os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "logs")


def files():
    """ملفات السجل الموجودة من الأحدث إلى الأقدم، مع أحجامها."""
    d = log_dir()
    out = []
    for i in range(ROTATIONS + 1):
        p = os.path.join(d, LOG_NAME + (f".{i}" if i else ""))
        try:
            out.append({"path": p, "name": os.path.basename(p), "size": os.path.getsize(p)})
        except OSError:
            continue
    return out


def _read_tail(path, size, budget):
    """آخر `budget` بايت من الملف، مقطوعة عند أول سطر كامل. (bool مقطوع، نص)."""
    take = min(size, budget, TAIL_BYTES)
    try:
        with open(path, "rb") as f:
            if take < size:
                f.seek(size - take)
            raw = f.read(take)
    except OSError as e:
        log.warning("log read failed: %s", e)
        return False, ""
    cut = take < size
    if cut:
        raw = raw.partition(b"\n")[2]          # السطر الأول مبتور — اطرحه
    return cut, raw.decode("utf-8", "replace")


# ---------------------------------------------------------------- التحليل
def parse(text, since=None, until=None):
    """نصّ سجل ⇒ سجلات `{ts, day, hour, level, logger, msg, trace}`.

    السطر الذي لا يطابق النمط تتمّةٌ لما قبله (traceback): نحتفظ بآخر سطر غير
    فارغ منه، فهو سطر الاستثناء نفسه — أنفع ما في الأثر كله لتسمية العطل."""
    out, cur = [], None

    def close():
        if cur is not None and (since is None or cur["ts"] >= since) \
                and (until is None or cur["ts"] < until):
            out.append(cur)

    for raw in str(text or "").splitlines():
        m = _LINE.match(raw)
        if not m:
            if cur is not None and raw.strip():
                cur["trace"] = redact(raw.strip())[:SAMPLE_LEN]
                cur["trace_lines"] += 1
            continue
        close()
        day, hh, mm, ss, level, logger_name, msg = m.groups()
        try:
            ts = int(time.mktime(time.strptime(f"{day} {hh}:{mm}:{ss}", "%Y-%m-%d %H:%M:%S")))
        except (ValueError, OverflowError):
            cur = None
            continue
        cur = {"ts": ts, "day": day, "hour": int(hh), "level": level,
               "logger": logger_name.strip(), "msg": redact(msg), "trace": "", "trace_lines": 0}
    close()
    return out


def _empty(reason=""):
    return {"available": False, "reason": reason, "dir": log_dir(), "files": [], "bytes": 0,
            "lines": 0, "truncated": False, "from": None, "to": None,
            "levels": {}, "daily": [], "groups": [], "loggers": [], "paths": [],
            "signals": {k: 0 for k, _ in _SIGNALS}, "errors": 0, "warnings": 0}


def aggregate(records, truncated=False, meta=None):
    """سجلات ⇒ ملخّص قابل للعرض والإرسال. لا نصّ خام غير محجوب يخرج من هنا."""
    out = _empty()
    out.update(meta or {})
    out["available"] = True
    out["truncated"] = bool(truncated)
    if not records:
        return out
    levels, daily, loggers, paths = {}, {}, {}, {}
    groups, signals = {}, {k: 0 for k, _ in _SIGNALS}
    for r in records:
        lvl = r["level"] if r["level"] in _LEVELS else "OTHER"
        levels[lvl] = levels.get(lvl, 0) + 1
        d = daily.setdefault(r["day"], {"day": r["day"], "error": 0, "warning": 0,
                                        "info": 0, "total": 0})
        d["total"] += 1
        if lvl in ("ERROR", "CRITICAL"):
            d["error"] += 1
        elif lvl == "WARNING":
            d["warning"] += 1
        else:
            d["info"] += 1
        for key, rx in _SIGNALS:
            if rx.search(r["msg"]):
                signals[key] += 1
        if lvl in ("ERROR", "CRITICAL", "WARNING"):
            loggers[r["logger"]] = loggers.get(r["logger"], 0) + 1
            sig = signature(r["logger"], r["msg"], r["trace"])
            g = groups.get(sig)
            if g is None:
                g = groups[sig] = {"sig": sig, "level": lvl, "logger": r["logger"],
                                   "count": 0, "first": r["ts"], "last": r["ts"],
                                   "sample": r["msg"][:SAMPLE_LEN], "trace": r["trace"],
                                   "days": {}}
            g["count"] += 1
            g["last"] = max(g["last"], r["ts"])
            g["first"] = min(g["first"], r["ts"])
            g["days"][r["day"]] = g["days"].get(r["day"], 0) + 1
            if lvl != "WARNING":
                g["level"] = lvl
            if r["trace"] and not g["trace"]:
                g["trace"] = r["trace"]
        m = _PATH.search(r["msg"])
        if m:
            p = _NUM.sub("#", m.group(1))[:80]
            paths[p] = paths.get(p, 0) + 1

    out["lines"] = len(records)
    out["from"] = min(r["ts"] for r in records)
    out["to"] = max(r["ts"] for r in records)
    out["levels"] = levels
    out["errors"] = levels.get("ERROR", 0) + levels.get("CRITICAL", 0)
    out["warnings"] = levels.get("WARNING", 0)
    out["daily"] = sorted(daily.values(), key=lambda x: x["day"])
    out["groups"] = sorted(groups.values(), key=lambda g: -g["count"])[:MAX_GROUPS]
    out["loggers"] = [{"k": k, "v": v} for k, v in
                      sorted(loggers.items(), key=lambda kv: -kv[1])[:10]]
    out["paths"] = [{"k": k, "v": v} for k, v in
                    sorted(paths.items(), key=lambda kv: -kv[1])[:10]]
    out["signals"] = signals
    return out


def scan(since=None, until=None, max_bytes=MAX_BYTES):
    """يقرأ ملفات السجل (الأحدث أولاً) ويرجّع تجميعها للفترة المطلوبة."""
    fs = files()
    if not fs:
        return _empty("no_log_file")
    budget, read, records, cut = max_bytes, [], [], False
    for f in fs:
        if budget <= 0:
            cut = True
            break
        was_cut, text = _read_tail(f["path"], f["size"], budget)
        if not text:
            continue
        budget -= min(f["size"], TAIL_BYTES)
        cut = cut or was_cut
        rec = parse(text, since, until)
        records += rec
        read.append({"name": f["name"], "size": f["size"], "lines": len(rec)})
        # الملف أقدم من الفترة كلها: ما قبله أقدم منه، فلا داعي لفتحه
        if since and rec == [] and f is not fs[0]:
            break
    records.sort(key=lambda r: r["ts"])
    return aggregate(records, truncated=cut,
                     meta={"dir": log_dir(), "files": read,
                           "bytes": sum(x["size"] for x in read)})
