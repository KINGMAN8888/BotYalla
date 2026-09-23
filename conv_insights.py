"""تحليل المحادثات — كل رسالة بين العميل والبوت والذكاء الاصطناعي وصاحب النشاط.

الغرض عملي لا إحصائي: أن يخرج من آلاف الرسائل **ما يُعمل به**. لذلك التحليل
يجيب على أسئلة بعينها:

- عن ماذا يسأل العملاء فعلاً؟ (`intents` + `phrases` + `keywords`)
- ما الذي سُئل ولم يُجَب؟ (`unanswered` — هذه أثمن قائمة في الملف كله: كل سطر
  فيها سؤال متكرر يستحق ردّاً جاهزاً في البوت)
- كم يستغرق الرد، ومن يردّ؟ (`response` — البوت مقابل الإنسان)
- متى يراسلنا الناس؟ (`hours` · `weekdays`)
- من ينتظر رداً الآن؟ (`waiting`)
- أين تتوقّف المحادثات؟ (`one_and_done` · `stalled`)

**لا نموذج لغوي هنا.** التحليل قواعد صريحة على نصٍّ مُطبَّع: مجاني، فوري،
قابل للاختبار بنصّ جاهز، ولا يرسل رسالة عميل إلى أي مزوّد خارجي. هذا قرار لا
نقص: رسائل عملاء أصحاب الأنشطة ليست بياناتنا لنبعث بها.

**كل عيّنة تُعرض تمرّ بـ`log_scan.redact`** فلا يظهر رقم هاتف أو بريد عميل في
تقرير يُقرأ في اللوحة أو يُرسل بالبريد.
"""
import re
import time

from log_scan import redact

REPLY_WINDOW = 6 * 3600        # بعدها لا يُحسب الردّ ردّاً على تلك الرسالة
WAITING_AFTER = 30 * 60        # عميل آخر كلامه سؤال ومرّ هذا الوقت = ينتظر
TOP = 15                       # طول القوائم المعروضة
SAMPLE_LEN = 160

# ---------------------------------------------------------------- التطبيع
_TASHKEEL = re.compile(r"[ؗ-ًؚ-ْـ]")
_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")
# `\w` في بايثون3 يشمل الحروف العربية أصلاً؛ ما لا يشمله علامات الترقيم —
# **بما فيها العربية** (؟ ، ؛) وهي داخل نطاق يونيكود العربي، فلو استُثني النطاق
# كله بقيت «بكام؟» كلمةً غير «بكام» وسقطت نيّة السؤال عن السعر كلها.
_PUNCT = re.compile(r"[^\w\s]+", re.U)
_WS = re.compile(r"\s+")


def normalize(text):
    """نصّ عربي مُطبَّع: بلا تشكيل ولا تطويل، الهمزات والتاء المربوطة والألف
    المقصورة موحّدة، والأرقام العربية لاتينية. بدونه «إزاي» و«ازاي» كلمتان."""
    s = _TASHKEEL.sub("", str(text or "")).translate(_DIGITS)
    s = (s.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا")
          .replace("ة", "ه").replace("ى", "ي").replace("ؤ", "و").replace("ئ", "ي"))
    return _WS.sub(" ", _PUNCT.sub(" ", s.lower())).strip()


_STOP = set("""
و في من على عن الي الى هذا هذه ذلك التي الذي كل كان يكون ما مش لا نعم ايوه اه او ثم
انا انت انتي احنا هو هي هم لي لك له لها بس كده كدا يعني عشان علشان لو ان انه اني عند
مع بعد قبل دي ده دى ايه ليه فين امتي ازاي بكام هل يا يااخي حضرتك لو سمحت من فضلك
the a an is are to for of and or in on it my your you i we how what when where can do
does please hi hello ok okay yes no thanks thank
السلام عليكم ورحمه الله وبركاته صباح مساء الخير النور اهلا هاي هلا مرحبا ازيك عامل ايه
""".split())

_QUESTION = re.compile(r"[؟?]|^(?:ايه|ازاي|امتي|فين|كام|بكام|هل|ليه|مين|كيف|متي|اين|كم|what|how|when|where|why|who|can|do|is)\b")

# النيّة بقواعد صريحة. الترتيب مهم: أول تطابق يفوز، فالأدقّ أولاً.
INTENTS = (
    ("price",      "سعر اسعار بكام كام تمن ثمن التمن كم السعر price cost how much"),
    ("shipping",   "شحن توصيل التوصيل الشحن دليفري مصاريف محافظه محافظات شيبينج shipping delivery"),
    ("stock",      "متوفر متاح موجود عندكم فيه مقاس مقاسات لون الوان stock available size color"),
    # «عايز» وحدها ليست طلب شراء — «عايز اتكلم مع موظف» طلب إنسان لا أوردر.
    ("order",      "اطلب طلب اوردر اشتري شراء احجزلي order buy"),
    ("order_status", "طلبي اوردري وصل الاوردر فين طلبي حالة الطلب tracking where is my order"),
    ("payment",    "دفع ادفع فودافون انستاباي تحويل فيزا كاش الدفع payment pay instapay"),
    ("booking",    "ميعاد معاد موعد حجز احجز مواعيد appointment booking slot"),
    ("hours",      "مواعيد العمل فاتح مفتوح بتقفلوا بتفتحوا العنوان فرع فروع مكانكم location address hours open"),
    ("complaint",  "شكوي مشكله مشكلة زعلان متضايق وحش زفت سيئ تاخير اتاخر مردتوش نصب استرجاع ارجاع refund complaint problem broken late"),
    ("human",      "موظف حد يكلمني بشري خدمه العملاء مسؤول اتكلم مع حد agent human support representative"),
    ("greeting",   "السلام عليكم صباح مساء اهلا هاي هلا مرحبا hi hello good morning"),
    ("thanks",     "شكرا متشكر تسلم ميرسي تمام ممتاز رائع جميل thanks thank you great"),
)
_INTENT_WORDS = tuple((k, set(v.split())) for k, v in INTENTS)

# الاسم المقروء لكل نيّة. الواجهة تترجم بنفسها، لكن الخلاصة تُرسل بالبريد
# وتليجرام حيث لا يوجد من يترجم مفتاحاً مثل `order_status`.
INTENT_NAMES = {
    "price": ("السعر", "price"), "shipping": ("الشحن", "shipping"),
    "stock": ("التوفّر", "availability"), "order": ("طلب شراء", "ordering"),
    "order_status": ("أين طلبي", "order status"), "payment": ("الدفع", "payment"),
    "booking": ("حجز موعد", "booking"), "hours": ("المواعيد والعنوان", "hours & address"),
    "complaint": ("شكوى", "complaints"), "human": ("طلب موظف", "asking for a human"),
    "greeting": ("تحية", "greetings"), "thanks": ("شكر", "thanks"),
    "other": ("أخرى", "other"),
}


def intent_name(key, lang="ar"):
    pair = INTENT_NAMES.get(key)
    return (pair[1] if lang == "en" else pair[0]) if pair else (key or "—")

_NEG = set("""مشكله مشكلة شكوي زعلان متضايق وحش زفت سيئ سيء تاخير اتاخر متاخر نصب
حرام غالي مرديتوش مردتوش مردوش مش عاجبني بطيء بطيئ زهقت تعبت اسوأ ندمت bad worst late
broken scam angry disappointed""".split())
_POS = set("""شكرا متشكر تسلم ميرسي تمام ممتاز رائع جميل حلو عظيم احسن افضل ريحتوني
بجد كويس perfect great excellent amazing good love""".split())


def classify(text):
    """نيّة الرسالة — مفتاح من `INTENTS` أو `other`."""
    ws = set(normalize(text).split())
    if not ws:
        return "other"
    for key, words in _INTENT_WORDS:
        if ws & words:
            return key
    return "other"


def sentiment(text):
    """`neg` أو `pos` أو `neutral` — إشارة خشنة تُقرأ مع العيّنة لا وحدها."""
    ws = set(normalize(text).split())
    n, p = len(ws & _NEG), len(ws & _POS)
    return "neg" if n > p else ("pos" if p > n else "neutral")


def is_question(text):
    """علامة استفهام صريحة، أو أداة سؤال في أول النصّ المُطبَّع."""
    raw = str(text or "")
    return "?" in raw or "؟" in raw or bool(_QUESTION.search(normalize(raw)))


def _top(counter, n=TOP, samples=None):
    out = []
    for k, v in sorted(counter.items(), key=lambda kv: -kv[1])[:n]:
        row = {"k": k, "v": v}
        if samples is not None:
            row["sample"] = samples.get(k, "")
        out.append(row)
    return out


def _clip(text):
    return redact(_WS.sub(" ", str(text or "")).strip())[:SAMPLE_LEN]


def _pct(x, y):
    return round(x * 100.0 / y, 1) if y else 0.0


def analyze(rows, truncated=False, now=None):
    """صفوف `database.conv_rows` ⇒ تقرير المحادثات الكامل.

    دالّة نقية: تأخذ الصفوف وترجّع القاموس — لا قاعدة ولا وقت نظام (إلا `now`
    الاختياري)، فتُختبر بمحادثة مكتوبة بالسطر."""
    now = int(now or time.time())
    out = {
        "messages": len(rows), "truncated": bool(truncated),
        "from": rows[0]["created_at"] if rows else None,
        "to": rows[-1]["created_at"] if rows else None,
    }
    if not rows:
        return dict(out, senders=[], kinds=[], intents=[], keywords=[], phrases=[], questions=[],
                    unanswered=[], response={}, hours=[], weekdays=[], bots=[], system=[],
                    negatives=[], waiting=[], customers=0, conversations=0, one_and_done=0,
                    repeat_customers=0, in_count=0, out_count=0, sentiment={})

    convs = {}                       # (bot, peer) -> [صفوف مرتّبة]
    senders, kinds, intents = {}, {}, {}
    words, phrases, phrase_sample = {}, {}, {}
    hours, weekdays = [0] * 24, [0] * 7
    sent = {"neg": 0, "pos": 0, "neutral": 0}
    system, negatives, neg_sample = {}, {}, {}
    bots = {}

    for r in rows:
        key = (r["bot_id"], r["peer"])
        convs.setdefault(key, []).append(r)
        senders[r["sender"]] = senders.get(r["sender"], 0) + 1
        kinds[r["kind"]] = kinds.get(r["kind"], 0) + 1
        b = bots.setdefault(r["bot_id"], {"bot_id": r["bot_id"], "name": r.get("bot_name") or "—",
                                          "msgs_in": 0, "msgs_out": 0, "customers": set(),
                                          "unanswered": 0, "waits": [], "intents": {}})
        if r["kind"] == "system":
            t = _clip(r["text"])
            if t:
                system[t] = system.get(t, 0) + 1
        if r["direction"] != "in":
            b["msgs_out"] += 1
            continue

        b["msgs_in"] += 1
        b["customers"].add(r["peer"])
        lt = time.localtime(r["created_at"])
        hours[lt.tm_hour] += 1
        weekdays[(lt.tm_wday + 2) % 7] += 1          # 0 = السبت (أول أيام الأسبوع عندنا)
        text = r["text"] or ""
        if not text.strip():
            continue
        it = classify(text)
        intents[it] = intents.get(it, 0) + 1
        b["intents"][it] = b["intents"].get(it, 0) + 1
        s = sentiment(text)
        sent[s] += 1
        norm = normalize(text)
        if s == "neg":
            # نفس الشكوى من عشرة عملاء خبرٌ واحد بعدّاد، لا عشرة أسطر متطابقة
            k = norm[:120]
            negatives[k] = negatives.get(k, 0) + 1
            neg_sample.setdefault(k, {"bot_id": r["bot_id"], "text": _clip(text)})
        if 2 <= len(norm) <= 120:
            phrases[norm] = phrases.get(norm, 0) + 1
            phrase_sample.setdefault(norm, _clip(text))
        for w in norm.split():
            if len(w) > 2 and w not in _STOP and not w.isdigit():
                words[w] = words.get(w, 0) + 1

    # ---- الردّ والانتظار: نمشي كل محادثة بترتيبها الزمني ----
    waits = {"bot": [], "ai": [], "human": []}
    unanswered, waiting = {}, []
    unanswered_sample, unanswered_bot = {}, {}
    one_and_done = repeat = 0
    for (bot_id, peer), msgs in convs.items():
        msgs.sort(key=lambda m: m["created_at"])
        ins = [m for m in msgs if m["direction"] == "in"]
        if len(ins) == 1:
            one_and_done += 1
        if len({time.strftime("%Y-%m-%d", time.localtime(m["created_at"])) for m in ins}) > 1:
            repeat += 1
        for i, m in enumerate(msgs):
            if m["direction"] != "in":
                continue
            nxt = next((x for x in msgs[i + 1:] if x["direction"] == "out"), None)
            gap = (nxt["created_at"] - m["created_at"]) if nxt else None
            if nxt and gap is not None and gap <= REPLY_WINDOW:
                waits.setdefault(nxt["sender"], []).append(gap)
                continue
            # بلا ردّ (أو ردّ بعد نافذة لا تُسمّى ردّاً): سؤال بلا إجابة
            txt = (m["text"] or "").strip()
            if txt and is_question(txt):
                k = normalize(txt)[:120]
                unanswered[k] = unanswered.get(k, 0) + 1
                unanswered_sample.setdefault(k, _clip(txt))
                unanswered_bot.setdefault(k, m["bot_id"])
                b = bots.get(m["bot_id"])
                if b:
                    b["unanswered"] += 1
        last = msgs[-1]
        if last["direction"] == "in" and now - last["created_at"] >= WAITING_AFTER:
            waiting.append({"bot_id": bot_id, "peer": peer, "since": last["created_at"],
                            "text": _clip(last["text"])})

    def stat(xs):
        if not xs:
            return None
        xs = sorted(xs)
        return {"n": len(xs), "avg": int(sum(xs) / len(xs)), "median": xs[len(xs) // 2],
                "p90": xs[min(len(xs) - 1, int(len(xs) * 0.9))]}

    in_count = sum(1 for r in rows if r["direction"] == "in")
    answered = sum(len(v) for v in waits.values())
    waiting.sort(key=lambda w: w["since"])
    bot_rows = []
    for b in bots.values():
        top_intent = max(b["intents"].items(), key=lambda kv: kv[1])[0] if b["intents"] else ""
        bot_rows.append({"bot_id": b["bot_id"], "name": b["name"], "msgs_in": b["msgs_in"],
                         "msgs_out": b["msgs_out"], "customers": len(b["customers"]),
                         "unanswered": b["unanswered"], "top_intent": top_intent,
                         "answer_rate": _pct(b["msgs_in"] - b["unanswered"], b["msgs_in"])})
    bot_rows.sort(key=lambda r: -r["msgs_in"])

    out.update({
        "in_count": in_count, "out_count": len(rows) - in_count,
        "conversations": len(convs), "customers": len({(r["bot_id"], r["peer"]) for r in rows}),
        "senders": _top(senders, 10), "kinds": _top(kinds, 10),
        "intents": [{"k": k, "v": v, "pct": _pct(v, sum(intents.values()))}
                    for k, v in sorted(intents.items(), key=lambda kv: -kv[1])],
        "keywords": _top(words, TOP),
        "phrases": [x for x in _top(phrases, TOP, phrase_sample) if x["v"] > 1],
        "unanswered": [dict(x, bot_id=unanswered_bot.get(x["k"]))
                       for x in _top(unanswered, TOP, unanswered_sample)],
        "unanswered_total": sum(unanswered.values()),
        "answer_rate": _pct(answered, in_count),
        "response": {"bot": stat(waits.get("bot")), "ai": stat(waits.get("ai")),
                     "human": stat(waits.get("human"))},
        "hours": [{"k": h, "v": n} for h, n in enumerate(hours)],
        "weekdays": [{"k": d, "v": n} for d, n in enumerate(weekdays)],
        "sentiment": dict(sent, neg_pct=_pct(sent["neg"], sum(sent.values()))),
        "negatives": [dict(neg_sample.get(x["k"], {}), count=x["v"])
                      for x in _top(negatives, TOP)],
        "system": _top(system, 10),
        "waiting": waiting[:TOP],
        "waiting_total": len(waiting),
        "one_and_done": one_and_done,
        "repeat_customers": repeat,
        "bots": bot_rows[:50],
    })
    return out


def headline(rep, lang="ar"):
    """سطور الخلاصة — ما يُقرأ أولاً في اللوحة وفي بريد التقرير."""
    en = lang == "en"
    out = []
    if not rep.get("messages"):
        return [("لا رسائل في هذه الفترة." if not en else "No messages in this period.")]
    ans = rep.get("answer_rate", 0)
    out.append(f"{rep['in_count']} رسالة من {rep['customers']} عميل في {rep['conversations']} محادثة."
               if not en else
               f"{rep['in_count']} customer messages from {rep['customers']} customers "
               f"in {rep['conversations']} conversations.")
    out.append((f"نسبة الرد {ans}%" if not en else f"Answer rate {ans}%") +
               (f" — {rep.get('unanswered_total', 0)} سؤال بلا إجابة." if not en else
                f" — {rep.get('unanswered_total', 0)} questions went unanswered."))
    r = (rep.get("response") or {}).get("bot")
    if r:
        out.append(f"وسيط رد البوت {r['median']} ثانية." if not en else
                   f"Median bot reply {r['median']}s.")
    if rep.get("intents"):
        top = rep["intents"][0]
        name = intent_name(top["k"], lang)
        out.append(f"أكثر ما يُسأل عنه: {name} ({top['pct']}%)." if not en else
                   f"Most asked about: {name} ({top['pct']}%).")
    if rep.get("waiting_total"):
        out.append(f"{rep['waiting_total']} محادثة آخر كلامها من العميل — ينتظر رداً."
                   if not en else
                   f"{rep['waiting_total']} conversations end on the customer — someone is waiting.")
    return out
