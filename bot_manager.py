"""مدير BotYalla — يشغّل عدة بوتات في حلقة asyncio بخيط منفصل + بث جماعي."""
import asyncio, concurrent.futures, json, threading, logging, time as _time, datetime as _dt
from telegram import Bot
from telegram.ext import Application
import database as db
import templates_bot as T
import tg_helpers as tg
import platform_bot as PB
import plans
import i18n

log = logging.getLogger("bot_manager")

WA_WINDOW = 24 * 3600     # نافذة خدمة العملاء في واتساب

def _split_wa_payload(payload):
    """يفكّ الـ payload إلى (phone_number_id, entry_id, [رسائل موحّدة]).
    الدفعة الواحدة قد تحمل رسائل لأكثر من رقم — معالجة الأولى فقط تفقد الباقي.
    entry_id مرشّح لـ WABA ID (لا يُوثق صراحةً، فلا نستعمله قبل التحقق منه)."""
    from channels.whatsapp import WhatsAppChannel
    out = []
    try:
        for entry in (payload or {}).get("entry", []):
            entry_id = str(entry.get("id") or "")
            for change in entry.get("changes", []):
                val = change.get("value") or {}
                if not val.get("messages"):
                    continue
                phone_id = (val.get("metadata") or {}).get("phone_number_id")
                if not phone_id:
                    continue
                msgs = WhatsAppChannel(phone_id, "").normalize_all(
                    {"entry": [{"changes": [{"value": val}]}]})
                if msgs:
                    out.append((phone_id, entry_id, msgs))
    except (AttributeError, TypeError):
        log.exception("malformed WhatsApp payload")
    return out

_ECHO_LABEL = {"image": "[صورة]", "video": "[فيديو]", "audio": "[صوت]", "voice": "[صوت]",
               "document": "[ملف]", "sticker": "[ملصق]", "location": "[موقع]", "contacts": "[جهة اتصال]"}


def _split_wa_echoes(payload):
    """ردود صاحب الرقم من تطبيق WhatsApp Business (وضع التعايش — حقل smb_message_echoes)
    ← [(phone_number_id, [{id, peer, text}])]. `to` هو العميل، فالمحادثة wa:<to>."""
    out = []
    try:
        for entry in (payload or {}).get("entry", []):
            for change in entry.get("changes", []):
                val = change.get("value") or {}
                echoes = val.get("message_echoes") or []
                phone_id = (val.get("metadata") or {}).get("phone_number_id")
                if not (echoes and phone_id):
                    continue
                items = []
                for m in echoes:
                    to = str(m.get("to") or "").lstrip("+")
                    if not to.isdigit():
                        continue
                    kind = m.get("type") or "text"
                    text = ((m.get("text") or {}).get("body") or "") if kind == "text" else \
                        ((m.get(kind) or {}).get("caption") or _ECHO_LABEL.get(kind, f"[{kind}]"))
                    items.append({"id": m.get("id") or "", "peer": f"wa:{to}", "text": text[:4000]})
                if items:
                    out.append((str(phone_id), items))
    except (AttributeError, TypeError):
        log.exception("malformed WhatsApp echo payload")
    return out


def record_wa_echoes(payload):
    """صاحب النشاط ردّ من موبايله: نسجّل الرد في صندوق المحادثات كرد بشري ونُسكت البوت في
    المحادثة دي (نفس «التولّي» — يرجع للبوت تلقائياً بعد HUMAN_IDLE). لبوتات التعايش وحدها."""
    n = 0
    for phone_id, items in _split_wa_echoes(payload):
        bot_row = db.get_bot_by_token(f"wa:{phone_id}")
        if not bot_row:
            continue
        cfg = json.loads(bot_row["config_json"] or "{}")
        if not cfg.get("wa_coexist"):
            continue
        for e in items:
            if e["id"] and not db.mark_msg_seen(e["id"]):
                continue
            db.log_message(bot_row["id"], e["peer"], "out", "human", e["text"])
            db.set_conversation_mode(bot_row["id"], e["peer"], "human")
            n += 1
    return n


def _remember_waba_hint(bot_row, entry_id):
    """يخزّن entry.id كـ«مرشّح» لـ WABA ID ليقترحه على صاحب البوت.
    Meta لا توثّق أن entry.id هو WABA ID، فلا نستعمله إلا بعد تحقق فعلي
    في صفحة القوالب. مجرد اقتراح يوفّر على العميل البحث عنه."""
    if not entry_id or not entry_id.isdigit():
        return
    cfg = json.loads(bot_row["config_json"] or "{}")
    if cfg.get("wa_waba_id") or cfg.get("wa_waba_hint") == entry_id:
        return
    cfg["wa_waba_hint"] = entry_id
    db.update_bot_config(bot_row["id"], cfg)

def wa_limit_for(owner_id):
    """حدّ الرسائل الصادرة شهرياً لصاحب البوت. None = بلا حدّ (الأدمن والدعم)."""
    u = db.get_user(owner_id)
    if u and u.get("role") in ("admin", "support"):
        return None
    sub = db.get_subscription(owner_id)
    pid = sub["plan"] if sub and sub.get("status") == "active" else "free"
    return plans.wa_limit(pid)

def _wa_channel(row):
    """يبني قناة واتساب من صف البوت. التوكن مخزّن كـ wa:<phone_number_id>.
    كل إرسال يمرّ بعدّاد الاستهلاك أولاً — واتساب مدفوع لكل رسالة."""
    from channels.whatsapp import WhatsAppChannel
    cfg = json.loads(row["config_json"] or "{}")
    token = row["token"] or ""
    phone_id = token[3:] if token.startswith("wa:") else token
    bot_id, owner_id = row["id"], row["owner_id"]
    limit = wa_limit_for(owner_id)

    async def guard():
        if db.try_consume_msg(bot_id, owner_id, limit):
            return True
        await manager._warn_wa_limit(row, owner_id, limit)
        return False

    return WhatsAppChannel(phone_id, cfg.get("wa_token", ""), on_send=guard)

# قنوات تصلها الرسائل بالويبهوك (لا polling): تُسجَّل «مشغّلة» بلا عملية، والإرسال عبر Graph.
WEBHOOK_CHANNELS = ("whatsapp", "messenger", "instagram")
META_PAGE_CHANNELS = {"messenger": "fb", "instagram": "ig"}      # القناة ← بادئة التوكن والـpeer


def _meta_channel(row):
    """قناة ماسنجر/إنستجرام من صف البوت. توكن الصفحة مختوم في الإعداد (`db.seal`) — Meta
    لا تحاسب على رسائل الصفحات فلا عدّاد استهلاك هنا (بخلاف واتساب)."""
    from channels.messenger import MessengerChannel
    cfg = json.loads(row["config_json"] or "{}")
    pfx = META_PAGE_CHANNELS.get(row.get("channel") or "", "fb")
    own_id = (row["token"] or "").split(":", 1)[-1]
    return MessengerChannel(pfx, own_id, db.unseal(cfg.get("page_token", "")))


def _our_app_id():
    import os
    return os.getenv("META_APP_ID", "").strip()


def meta_side_events(row, entry, pfx):
    """كل ما ليس رسالة جديدة من العميل في حدث صفحة — يُتصرَّف فيه أو يُسجَّل للأدمن.

    * **صدى من إنسان** (`message.is_echo` بلا app_id تطبيقنا): صاحب الصفحة ردّ من Meta Business
      Suite/الموبايل ← يُسجَّل رداً بشرياً ويسكت البوت في المحادثة (نفس «التولّي»).
    * **تسليم المحادثة** (handover): الصفحة أخذت المحادثة ← وضع بشري؛ أعادتها لتطبيقنا ← البوت.
    * **standby**: رسائل وصلت والمحادثة ليست معنا ← تُسجَّل في الصندوق بلا رد.
    * **إلغاء الرسائل** (optin STOP) ← لا بث لهذا العميل.
    * الباقي (قراءة · تسليم · تفاعل · تعديل · تعليقات · سياسات · عملاء محتملون) ← سجل الأحداث."""
    bot_id, account = row["id"], f"{pfx}:{entry.get('id')}"
    own = str(entry.get("id"))
    ours = _our_app_id()
    for ev in entry.get("messaging") or []:
        sender = str((ev.get("sender") or {}).get("id") or "")
        recipient = str((ev.get("recipient") or {}).get("id") or "")
        cust = recipient if sender == own else sender
        peer = f"{pfx}:{cust}" if cust else None
        m = ev.get("message") or {}
        if m.get("is_echo"):
            if ours and str(m.get("app_id") or "") == ours:
                continue                                # ردّ البوت نفسه — مسجَّل عند إرساله
            if peer and (m.get("text") or m.get("attachments")) and db.mark_msg_seen("echo:" + str(m.get("mid"))):
                db.log_message(bot_id, peer, "out", "human", m.get("text") or "📎",
                               kind="text" if m.get("text") else "media")
                db.set_conversation_mode(bot_id, peer, "human")
            continue
        if "pass_thread_control" in ev or "take_thread_control" in ev or "request_thread_control" in ev:
            p = ev.get("pass_thread_control") or {}
            back_to_us = bool(p) and str(p.get("new_owner_app_id") or "") == ours
            if peer and "request_thread_control" not in ev:
                db.set_conversation_mode(bot_id, peer, "bot" if back_to_us else "human")
            db.log_meta_event(account, "handover", "للبوت" if back_to_us else "للصفحة (إنسان)",
                              bot_id=bot_id, peer=peer)
            continue
        opt = ev.get("optin") or {}
        status = str(opt.get("notification_messages_status") or "").upper()
        if status in ("STOP_NOTIFICATIONS", "RESUME_NOTIFICATIONS") and peer:
            num = int(cust) if cust.isdigit() else 0
            if status.startswith("STOP"):
                db.add_bot_user(bot_id, num, "", peer=peer)
                db.set_opt_out(bot_id, num)
            db.log_meta_event(account, "optout" if status.startswith("STOP") else "optin", status,
                              bot_id=bot_id, peer=peer)
            continue
        for k, label in (("read", "قراءة"), ("delivery", "تسليم"), ("reaction", "تفاعل"),
                         ("message_edit", "تعديل رسالة"), ("account_linking", "ربط حساب"),
                         ("policy_enforcement", "تنفيذ سياسة"), ("feedback", "تقييم"),
                         ("messaging_feedback", "تقييم")):
            if k in ev:
                v = ev.get(k) or {}
                extra = v.get("emoji") or v.get("reaction") or v.get("text") or v.get("action") or v.get("reason") or ""
                if k in ("read", "delivery"):
                    extra = ""
                db.log_meta_event(account, k, f"{label} {extra}".strip(), bot_id=bot_id, peer=peer)
                break
    for ev in entry.get("standby") or []:              # المحادثة مع تطبيق/إنسان آخر: سجّل فقط
        m = ev.get("message") or {}
        cust = str((ev.get("sender") or {}).get("id") or "")
        if m and not m.get("is_echo") and cust and cust != own:
            if db.mark_msg_seen("sb:" + str(m.get("mid"))):
                db.log_message(bot_id, f"{pfx}:{cust}", "in", "customer", m.get("text") or "📎",
                               kind="text" if m.get("text") else "media")
    for ch in entry.get("changes") or []:              # feed · inbox_labels · lead forms · سياسات
        v = ch.get("value") or {}
        field = ch.get("field") or "change"
        label = v.get("label") if isinstance(v.get("label"), dict) else {}
        summary = (v.get("message") or label.get("page_label_name") or
                   " ".join(str(x) for x in (v.get("item"), v.get("verb")) if x) or "")
        who = (v.get("from") or {}).get("name") or ""
        db.log_meta_event(account, field, f"{who}: {summary}".strip(": ") if who else str(summary),
                          bot_id=bot_id)


def channel_for(row):
    """قناة الإرسال لأي بوت ويبهوك (واتساب · ماسنجر · إنستجرام) — None لتليجرام."""
    ch = row.get("channel") or "telegram"
    if ch == "whatsapp":
        return _wa_channel(row)
    if ch in META_PAGE_CHANNELS:
        return _meta_channel(row)
    return None


def _register_inbox_guard(app, bot_id):
    """لقوالب تليجرام التي لا تمرّ بمحرك الفلو (متجر · حجز · قائمة): يسجّل كل
    رسالة واردة في صندوق الوارد، وحين يتولّى صاحب النشاط المحادثة يوقف القالب
    عن الرد (ApplicationHandlerStop في المجموعة -1 يمنع وصولها لما بعدها)."""
    from telegram.ext import MessageHandler, filters, ApplicationHandlerStop
    import flow_engine

    async def guard(update, ctx):
        msg, user = update.message, update.effective_user
        if not msg or not user:
            return
        peer = f"tg:{user.id}"
        text = (msg.text or msg.caption or "").strip()
        db.log_message(bot_id, peer, "in", "customer", text,
                       kind="text" if msg.text else "media", name=user.first_name or "")
        conv = db.get_conversation(bot_id, peer)
        if flow_engine.human_active(bot_id, peer, conv):
            db.add_bot_user(bot_id, user.id, user.first_name or "", peer=peer)
            row = db.get_bot(bot_id)
            if row:
                from channels.telegram import TelegramChannel
                await flow_engine.notify_human_inbound(row, TelegramChannel(ctx.bot), peer,
                                                       text or "📎")
            raise ApplicationHandlerStop

    app.add_handler(MessageHandler(filters.ALL, guard), group=-1)


# سقف عدد البوتات العاملة في هذه العملية (L-11).
# `workers=1` وكل بوتات تليجرام تعمل داخل عملية الويب نفسها، فالسقف حقيقي لا
# نظري: تجاوزه لا يعطي خطأً واضحاً بل بطئاً يزحف على **كل** المستخدمين.
# الرقم يُقاس على الخادم بـ`tools/loadtest_bots.py` ثم يُضبط من لوحة الأدمن
# (`bot_capacity`) — والاحتياطي أدناه تقدير محافظ لا قياس.
CAPACITY_FALLBACK = 120
CAPACITY_WARN_AT = 0.80


class BotManager:
    def __init__(self):
        self._loop = None; self._thread = None
        self._apps = {}; self._ready = threading.Event(); self._platform = None
        # يوزر بوت المنصة و«وضع إدارة البوتات» (can_manage_bots) — من getMe عند التشغيل
        self._platform_info = {}
        # الحملات تعمل في خيوط خلفية، حملة واحدة لكل بوت (start_campaign)
        self._campaigns = {}; self._campaign_lock = threading.Lock(); self._campaign_threads = []

    def start(self):
        if self._thread and self._thread.is_alive(): return
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start(); self._ready.wait(timeout=10)
        # خيط التذكيرات: daemon يعمل كل 6 ساعات
        t = threading.Thread(target=self._reminder_loop, daemon=True)
        t.start()

    def _run(self):
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._ready.set(); self._loop.run_forever()

    def _submit(self, coro, timeout=60):
        return asyncio.run_coroutine_threadsafe(coro, self._loop).result(timeout=timeout)

    def is_running(self, bot_id): return bot_id in self._apps

    def capacity(self):
        """السقف المضبوط. قيمة غير صالحة تسقط إلى الاحتياطي لا إلى بلا حدّ."""
        try:
            v = int(str(db.get_platform("bot_capacity", "") or "").strip() or 0)
        except (TypeError, ValueError):
            v = 0
        return v if v > 0 else CAPACITY_FALLBACK

    def capacity_status(self):
        """الحالة الحالية — يقرأها مسار التشغيل ولوحة الأدمن.
        `warn` تصير True عند 80% فما فوق، و`full` عند بلوغ السقف."""
        cap = self.capacity()
        # تليجرام وحده يستهلك السعة (polling داخل العملية). بوت واتساب مجرد
        # علامة في `_apps` — ويبهوك بلا أي حلقة — فعدّه كان يحجز مكاناً بلا تكلفة.
        n = sum(1 for v in self._apps.values() if not isinstance(v, dict))
        return {"running": n, "capacity": cap,
                "pct": int(round(n * 100.0 / cap)) if cap else 0,
                "warn": n >= cap * CAPACITY_WARN_AT, "full": n >= cap}

    def _capacity_refusal(self, row):
        """رسالة الرفض لو بلغ الخادم السقف، وإلا None.
        الرفض عند السقف مقصود: بوت إضافي يعمل ببطء أسوأ من بوت لا يعمل،
        لأن بطأه يصيب كل من يشاركه العملية لا صاحبه وحده."""
        st = self.capacity_status()
        if st["full"] and (row.get("channel") or "telegram") != "whatsapp":
            log.error("bot start refused — at capacity: %s/%s", st["running"], st["capacity"])
            return (f"بلغ الخادم سقف البوتات العاملة ({st['capacity']}). "
                    f"أوقف بوتاً غير مستخدم أو راسل الدعم.")
        return None

    def start_bot(self, bot_id):
        if self.is_running(bot_id): return True, "يعمل بالفعل"
        row = db.get_bot(bot_id)
        if not row: return False, "البوت غير موجود"
        refusal = self._capacity_refusal(row)
        if refusal:
            return False, refusal
        try:
            self._submit(self._start(row)); db.set_bot_active(bot_id, True)
            return True, "تم التشغيل ✅"
        except Exception as e:
            log.exception("start"); return False, f"فشل التشغيل: {e}"

    async def start_bot_async(self, bot_id):
        """نفس start_bot لكن من **داخل** حلقة المدير (بوت المنصة ينشئ بوتاً بضغطة).
        `_submit` من داخل الحلقة ينتظر نفسه فيتجمّد إلى الأبد — لذلك await مباشرة."""
        if self.is_running(bot_id): return True, "يعمل بالفعل"
        row = db.get_bot(bot_id)
        if not row: return False, "البوت غير موجود"
        refusal = self._capacity_refusal(row)
        if refusal:
            return False, refusal
        try:
            await self._start(row); db.set_bot_active(bot_id, True)
            return True, "تم التشغيل ✅"
        except Exception as e:
            log.exception("start (async)"); return False, f"فشل التشغيل: {e}"

    async def restart_bot_async(self, bot_id):
        await self._stop(bot_id)
        return await self.start_bot_async(bot_id)

    async def _start(self, row):
        if row.get("channel") in WEBHOOK_CHANNELS:
            self._apps[row["id"]] = {"type": row.get("channel")}
            return
            
        cfg = json.loads(row["config_json"] or "{}")
        app = Application.builder().token(row["token"]).build()
        app.bot_data["config"] = cfg; app.bot_data["bot_id"] = row["id"]
        tmpl = T.TEMPLATES.get(row["template"])
        if not tmpl: raise ValueError("قالب غير معروف")
        tmpl["build"](app)
        tg.register_common(app)
        if tmpl["build"] is not T.build_flow:
            # المتجر والحجز والقائمة لا تمرّ بمحرك الفلو — حارس الوارد يسجّل رسائلها
            # ويحترم «تولّي المحادثة» قبل أن يصلها القالب.
            _register_inbox_guard(app, row["id"])
        await app.initialize(); await app.start()
        await app.updater.start_polling(drop_pending_updates=True)
        self._apps[row["id"]] = app

    def stop_bot(self, bot_id):
        if not self.is_running(bot_id):
            db.set_bot_active(bot_id, False); return True, "متوقف بالفعل"
        try:
            self._submit(self._stop(bot_id)); db.set_bot_active(bot_id, False)
            return True, "تم الإيقاف ⏹️"
        except Exception as e:
            log.exception("stop"); return False, f"فشل الإيقاف: {e}"

    async def _stop(self, bot_id):
        app = self._apps.pop(bot_id, None)
        if app:
            if isinstance(app, dict) and app.get("type") in WEBHOOK_CHANNELS:
                return
            if app.updater and app.updater.running: await app.updater.stop()
            await app.stop(); await app.shutdown()

    def restart_bot(self, bot_id):
        self.stop_bot(bot_id); return self.start_bot(bot_id)

    # ---- البث الجماعي ----
    # كل حلقة إرسال تحدّث عدّاداً حيّاً (`prog`) بعد كل رسالة، ومنه وحده تُحسب النتيجة.
    @staticmethod
    def _progress(prog, total):
        """يهيّئ العدّاد. حالة الحملة نفسها تُمرَّر هنا فتعرض الصفحة التقدّم أثناء الإرسال."""
        p = prog if prog is not None else {}
        p.update(sent=0, failed=0, total=total, stop=False)
        return p

    @staticmethod
    def _tally(prog, ok):
        prog["sent" if ok else "failed"] += 1

    def _run_counted(self, coro, prog, total, timeout, what):
        """يشغّل حلقة إرسال ويرجّع (وصل, لم يصل) من العدّاد الحيّ لا من نتيجتها.

        `.result(timeout)` لا يلغي الكوروتين — يكفّ عن انتظاره فقط — فكانت المهلة تُعلن
        «فشل الكل» فيُردّ ثمن الحملة كاملاً بينما الرسائل تُرسل فعلاً. الآن عند المهلة
        نطلب التوقف (`stop`) فتتوقف الحلقة قبل الرسالة التالية، وننتظر الجارية حتى تكتمل
        (مهلة الطلب الواحد 15ث)، ثم نقرأ العدّاد: ما وصل يُحاسَب وما بقي يُردّ."""
        fut = asyncio.run_coroutine_threadsafe(coro, self._loop)
        try:
            fut.result(timeout=timeout)
        except concurrent.futures.TimeoutError:
            log.warning("%s: time budget reached at %s/%s — stopping", what, prog["sent"], total)
            prog["stop"] = True
            try:
                fut.result(timeout=20)
            except Exception:
                fut.cancel()
        except Exception:
            log.exception(what)
        return prog["sent"], total - prog["sent"]

    def broadcast(self, bot_id, text, asset=None, prog=None):
        """إرسال رسالة لكل مشتركي البوت — مع صورة/فيديو من المكتبة اختيارياً
        (والنص يصير تعليقه). يرجّع (وصل, لم يصل)."""
        row = db.get_bot(bot_id)
        if not row: return 0, 0
        if (row.get("channel") or "telegram") in WEBHOOK_CHANNELS:
            # واتساب وماسنجر وإنستجرام تمنع المراسلة الحرة بعد 24 ساعة من آخر رسالة
            # للعميل، والمخالفة تُقيّد الرقم/الصفحة. نبثّ داخل النافذة فقط.
            ids = db.list_bot_peers(bot_id, within_seconds=WA_WINDOW)
            skipped = len(db.list_bot_peers(bot_id)) - len(ids)
            if skipped:
                log.info("broadcast: skipped %s WhatsApp peers outside the 24h window", skipped)
        else:
            ids = db.list_bot_user_ids(bot_id)
        if not ids: return 0, 0
        prog = self._progress(prog, len(ids))
        per = 2.0 if asset else 1.0                    # الوسائط أبطأ (أول رفع خصوصاً)
        return self._run_counted(self._broadcast(row, ids, text, asset, prog), prog, len(ids),
                                 max(60, len(ids) * per), "broadcast")

    async def _broadcast(self, row, ids, text, asset, prog):
        if (row.get("channel") or "telegram") in WEBHOOK_CHANNELS:
            return await self._broadcast_wa(row, ids, text, asset, prog)

        from channels.telegram import TelegramChannel
        app = self._apps.get(row["id"])
        bot = app.bot if app else Bot(row["token"])
        own = app is None
        if own: await bot.initialize()
        ch = TelegramChannel(bot) if asset else None
        try:
            for uid in ids:
                if prog["stop"]:
                    break
                try:
                    if ch:
                        # أول إرسال يرفع الملف ويحفظ file_id — الباقي يعيد استعماله
                        await ch.send_media(f"tg:{uid}", asset, row["id"], caption=text or None)
                    else:
                        await bot.send_message(uid, text)
                    ok = True
                except Exception:
                    ok = False
                self._tally(prog, ok)
                await asyncio.sleep(0.05)   # احترام حدود المعدل
        finally:
            if own: await bot.shutdown()

    async def _broadcast_wa(self, row, peers, text, asset, prog):
        channel = channel_for(row)
        for peer in peers:
            if prog["stop"]:
                break
            try:
                ok = await (channel.send_media(peer, asset, row["id"], caption=text or None)
                            if asset else channel.send_text(peer, text))
            except Exception:
                ok = False
            self._tally(prog, bool(ok))
            await asyncio.sleep(0.1)

    def broadcast_template(self, bot_id, name, language, values=None, peers=None, prog=None):
        """بثّ بقالب معتمد. هذا هو ما يصل لمن خرج من نافذة الـ24 ساعة —
        النص الحر لا يصله، ومحاولة إرساله له تُقيّد الرقم.

        `peers`: القائمة التي حُسبت تكلفتها في المسار. تمريرها يضمن أن من
        حوسب عليه هو بالضبط من يُرسل له — لا مشترك جديد بين الحساب والإرسال."""
        row = db.get_bot(bot_id)
        if not row or (row.get("channel") or "telegram") != "whatsapp":
            return 0, 0
        if peers is None:
            peers = db.list_bot_peers(bot_id)
        if not peers:
            return 0, 0
        prog = self._progress(prog, len(peers))
        return self._run_counted(self._broadcast_template(row, peers, name, language, values, prog),
                                 prog, len(peers), max(60, len(peers) * 2.0), "broadcast_template")

    async def _broadcast_template(self, row, peers, name, language, values, prog):
        from channels.wa_templates import body_components
        channel = _wa_channel(row)
        comps = body_components(values)
        for peer in peers:
            if prog["stop"]:
                break
            try:
                ok = await channel.send_template(peer, name, language, comps)
            except Exception:
                ok = False
            self._tally(prog, bool(ok))
            await asyncio.sleep(0.1)

    def broadcast_direct(self, bot_id, text, category="utility", peers=None, prog=None):
        """بثّ بـ Direct Send API — بدون قالب مسبق.
        يدعم فقط utility و authentication."""
        row = db.get_bot(bot_id)
        if not row or (row.get("channel") or "telegram") != "whatsapp":
            return 0, 0
        if peers is None:
            peers = db.list_bot_peers(bot_id)
        if not peers:
            return 0, 0
        prog = self._progress(prog, len(peers))
        return self._run_counted(self._broadcast_direct(row, peers, text, category, prog),
                                 prog, len(peers), max(60, len(peers) * 2.0), "broadcast_direct")

    async def _broadcast_direct(self, row, peers, text, category, prog):
        channel = _wa_channel(row)
        for peer in peers:
            if prog["stop"]:
                break
            try:
                ok = await channel.send_direct(peer, text, category)
            except Exception:
                ok = False
            self._tally(prog, bool(ok))
            await asyncio.sleep(0.1)

    # ---- الحملات: في الخلفية، حملة واحدة لكل بوت ----
    def start_campaign(self, bot_id, job):
        """يشغّل `job(state)` في خيط خلفي، ويرجّع False لو حملة البوت نفسه ما زالت تعمل.

        الإرسال داخل الطلب كان يتجاوز مهلة nginx (60ث) مع ~110 مشترك: يرى صاحب البوت
        خطأً والخصم تمّ والإرسال مستمر، فيضغط «إرسال» ثانيةً — خصم مزدوج وحملة مكررة
        لعملائه. `state` هو العدّاد الحيّ نفسه؛ ما يرجّعه `job` يُدمج فيه عند الانتهاء."""
        with self._campaign_lock:
            cur = self._campaigns.get(bot_id)
            if cur and cur.get("state") == "running":
                return False
            state = {"state": "running", "sent": 0, "failed": 0, "total": 0,
                     "started_at": int(_time.time())}
            self._campaigns[bot_id] = state

        def run():
            try:
                state.update(job(state) or {})
            except Exception:
                log.exception("campaign bot=%s", bot_id)
                state["error"] = True
            finally:
                state["finished_at"] = int(_time.time())
                state["state"] = "done"

        t = threading.Thread(target=run, daemon=True, name=f"campaign-{bot_id}")
        self._campaign_threads = [x for x in self._campaign_threads if x.is_alive()] + [t]
        t.start()
        return True

    def campaign_status(self, bot_id):
        """آخر حملة للبوت منذ التشغيل (جارية أو منتهية) — للعرض. None = لا حملة."""
        cur = self._campaigns.get(bot_id)
        return {k: v for k, v in cur.items() if k != "stop"} if cur else None

    def join_campaigns(self, timeout=15):
        """ينتظر انتهاء الحملات الجارية (للاختبارات)."""
        for t in list(self._campaign_threads):
            t.join(timeout)

    # ---- بوت المنصة (تنبيهات الدفع) ----
    def start_platform_bot(self, token):
        if not token: return False, "لا يوجد توكن لبوت المنصة"
        if self._platform is not None:
            try: self._submit(self._stop_platform())
            except Exception: pass
        try:
            self._submit(self._start_platform(token)); return True, "بوت المنصة يعمل"
        except Exception as e:
            log.exception("platform start"); return False, f"فشل تشغيل بوت المنصة: {e}"

    async def _start_platform(self, token):
        import managed_bots
        app = Application.builder().token(token).build()
        PB.register(app)
        await app.initialize(); await app.start()
        me = app.bot.bot
        # can_manage_bots يصل من getMe فقط، وPTB 21.6 يضعه في api_kwargs
        self._platform_info = {
            "username": me.username,
            "can_manage": bool(getattr(me, "can_manage_bots", False)
                               or (me.api_kwargs or {}).get("can_manage_bots")),
        }
        # managed_bot لا يصل إلا لو طُلب صراحةً في allowed_updates
        await app.updater.start_polling(drop_pending_updates=True,
                                        allowed_updates=managed_bots.PLATFORM_UPDATES)
        self._platform = app
        # يوزر بوت المنصة محفوظاً — الصفحة الرئيسية تعرض رابطه وQR حتى لو توقف لحظياً
        if me.username:
            db.set_platform("platform_tg_username", me.username)
        # الوصف والأوامر في الخلفية: طلبات تليجرام لا تؤخّر التشغيل، وفشلها لا يوقفه
        t = asyncio.ensure_future(PB.brand(app.bot))
        self._brand_task = t

    async def _stop_platform(self):
        app = self._platform; self._platform = None; self._platform_info = {}
        if app:
            if app.updater and app.updater.running: await app.updater.stop()
            await app.stop(); await app.shutdown()

    def platform_running(self):
        return self._platform is not None

    def platform_info(self):
        """{'username','can_manage'} لبوت المنصة العامل، أو {} لو متوقف."""
        return dict(self._platform_info) if self._platform is not None else {}

    # ---- رد صاحب النشاط من صندوق الوارد ----
    def send_to_peer(self, bot_id, peer, text=None, asset=None):
        """يرسل رسالة من صاحب النشاط لعميل بعينه. يرجّع (ok, error_code).
        واتساب يمرّ بعدّاد الاستهلاك عبر `_wa_channel` كأي إرسال آخر."""
        row = db.get_bot(bot_id)
        if not row:
            return False, "bot"
        try:
            return self._submit(self._send_to_peer(row, peer, text, asset), timeout=45)
        except Exception:
            log.exception("send_to_peer"); return False, "send"

    async def _send_to_peer(self, row, peer, text=None, asset=None):
        from telegram.error import Forbidden
        from channels.telegram import TelegramChannel
        is_wa = (row.get("channel") or "telegram") in WEBHOOK_CHANNELS
        own = None
        if is_wa and peer.startswith("tg:"):
            # عميل كلّم بوت المنصة على تليجرام وسُجّل على صفّ المساعد الرسمي (بوت واتساب):
            # الرد يخرج من بوت المنصة نفسه — لا من رقم واتساب لا يعرف هذا العميل
            if self._platform is None:
                return False, "send"
            is_wa = False
            ch = TelegramChannel(self._platform.bot)
            ch.cache_refs = False
        elif is_wa:
            ch = channel_for(row)
        else:
            app = self._apps.get(row["id"])
            if app is not None and not isinstance(app, dict):
                ch = TelegramChannel(app.bot)
            else:
                own = Bot(row["token"]); await own.initialize()
                ch = TelegramChannel(own)
        try:
            if asset:
                res = await ch.send_media(peer, asset, row["id"], caption=text or None)
            else:
                res = await ch.send_text(peer, text)
            # واتساب يرجّع None عند الرفض (حدّ الباقة · توكن · نافذة)؛ تليجرام يرمي
            if is_wa and not res:
                return False, "send"
            return True, None
        except Forbidden:
            return False, "blocked"                     # العميل حظر البوت
        except Exception:
            log.exception("owner reply failed for bot #%s", row["id"])
            return False, "send"
        finally:
            if own is not None:
                await own.shutdown()

    def notify_text(self, chat_id, text, reply_markup=None):
        """إرسال رسالة نصية للأدمن عبر بوت المنصة (best-effort).
        لا تُستدعى من داخل حلقة المدير نفسها — استخدم notify_text_async هناك."""
        if self._platform is None or not chat_id:
            return False
        try:
            self._submit(self._platform.bot.send_message(int(chat_id), text,
                                                         reply_markup=reply_markup)); return True
        except Exception:
            log.exception("notify_text"); return False

    async def notify_text_async(self, chat_id, text, reply_markup=None):
        """نفس الغرض لكن من داخل حلقة asyncio (يتجنّب انتظار النتيجة على نفس الحلقة)."""
        if self._platform is None or not chat_id:
            return False
        try:
            await self._platform.bot.send_message(int(chat_id), text, reply_markup=reply_markup)
            return True
        except Exception:
            log.exception("notify_text_async"); return False

    def notify_probe(self, chat_id):
        """رسالة اختبار للأدمن ← (ok, error). تكشف سبب الفشل بدل ابتلاعه — أشهره أن
        الأدمن لم يضغط Start في بوت المنصة، فتليجرام يرفض أن يبدأ البوت المحادثة."""
        if self._platform is None:
            return False, "stopped"
        try:
            self._submit(self._platform.bot.send_message(
                int(chat_id), "✅ اختبار تنبيهات BotYalla — التنبيهات هتوصلك هنا.\n"
                              "BotYalla alerts test — alerts will arrive here."))
            return True, None
        except Exception as e:
            log.warning("notify probe to %s failed: %s", chat_id, e)
            return False, f"{type(e).__name__}: {e}"[:300]

    def bot_send(self, bot_id, chat_id, text):
        """رسالة لعميل عبر بوته الشغّال (قرار دفع اتخذه صاحبه من اللوحة) — وتُسجَّل في صندوق
        الوارد كأي رد. best-effort: البوت المتوقف لا يستطيع الإرسال."""
        app = self._apps.get(bot_id)
        if not app or isinstance(app, dict) or not chat_id:
            return False
        try:
            self._submit(app.bot.send_message(int(chat_id), text), timeout=20)
        except Exception:
            log.exception("bot_send bot=%s", bot_id)
            return False
        try:
            db.log_message(bot_id, f"tg:{int(chat_id)}", "out", "bot", text)
        except Exception:
            log.exception("bot_send log")
        return True

    def send_payment_alert(self, admin_id, payment, username, caption, screenshot_path):
        if self._platform is None:
            return None
        try:
            return self._submit(PB._send_alert_async(self._platform, admin_id, payment, username, caption, screenshot_path))
        except Exception as e:
            log.exception("payment alert"); return None

    def resume_active_bots(self):
        for b in db.all_active_bots():
            ok, msg = self.start_bot(b["id"]); log.info("resume %s: %s", b["id"], msg)

    # ---- تذكيرات انتهاء الاشتراك ----
    def _reminder_loop(self):
        """حلقة خلفية تعمل كل 6 ساعات لإرسال تذكيرات الاشتراك."""
        INTERVAL = 6 * 3600  # 6 ساعات
        _time.sleep(30)  # انتظر 30 ثانية عند الإطلاق ليكتمل التشغيل
        while True:
            try:
                self._send_reminder_cycle()
            except Exception:
                log.exception("reminder cycle error")
            try:
                n = db.purge_stale_chat_state()
                if n:
                    log.info("purged %s stale chat states", n)
                n = db.purge_seen_msgs()
                if n:
                    log.info("purged %s seen message ids", n)
                # مدة الاحتفاظ بالمحادثات المعلنة في سياسة الخصوصية: 12 شهراً
                n = db.purge_old_messages()
                if n:
                    log.info("purged %s messages older than the retention period", n)
                n = db.purge_old_events()
                if n:
                    log.info("purged %s analytics events older than a year", n)
                n = db.purge_old_page_views()
                if n:
                    log.info("purged %s page views older than 400 days", n)
                # ملفات محادثات لم تكتمل: لا lead يشير إليها، وتبقى على القرص للأبد
                import media_store
                orphans = db.orphan_media()
                if orphans:
                    media_store.delete_files(orphans)
                    db.drop_media([o["id"] for o in orphans])
                    log.info("purged %s orphan media files", len(orphans))
            except Exception:
                log.exception("housekeeping error")
            _time.sleep(INTERVAL)

    def _send_reminder_cycle(self):
        """يفحص الاشتراكات ويرسل التذكيرات المناسبة.

        التسجيل في reminder_log يتم **فقط عند وصول رسالة فعلاً**. لو كان بوت
        المنصة متوقفاً فلا شيء يُسجَّل وتُعاد المحاولة في الدورة التالية —
        وإلا لأحرقت أول دورة كل التذكيرات نهائياً بسبب قيد UNIQUE.
        """
        import mailer
        admin_ids = db.admin_chat_ids()
        tg_on, mail_on = self.platform_running(), mailer.configured()
        if not tg_on and not mail_on:
            log.info("reminders skipped: platform bot not running and SMTP not configured")
            return

        now = int(_time.time())

        def deliver(sub, kind, user_key, admin_key, **fmt):
            """يرسل للعميل (تليجرام + إيميل) وللأدمن. True لو وصلت رسالة واحدة على الأقل.
            الإيميل متزامن هنا عمداً: خيط التذكيرات ليس حلقة asyncio ولا داخل معاملة
            (AGENTS.md §15)، ونحتاج نتيجته الحقيقية قبل التسجيل في reminder_log."""
            lang = db.user_lang(sub["user_id"])
            plan_name = plans.plan_name(sub["plan"], lang)
            delivered = False

            if mail_on and sub.get("email"):
                date = fmt.get("date") or _dt.datetime.fromtimestamp(sub["expires_at"]).strftime("%Y-%m-%d")
                if mailer.send_mail(sub["email"], *mailer.expiry_email(
                        kind, plan_name, date, lang, mailer.site_url("/pricing"))):
                    delivered = True

            tg_id = sub.get("tg_chat_id") if tg_on else None
            if tg_id:
                msg = i18n.t(user_key, lang).format(plan=plan_name, **fmt)
                if self.notify_text(tg_id, msg):
                    delivered = True
                else:
                    log.warning("reminder %s: delivery to user #%s failed",
                                kind, sub["user_id"])
            else:
                log.info("reminder %s: user #%s has no telegram channel",
                         kind, sub["user_id"])

            admin_msg = i18n.t(admin_key, "ar").format(
                user=sub["username"], plan=plans.plan_name(sub["plan"], "ar"), **fmt)
            admin_ok = False
            for aid in admin_ids:
                if self.notify_text(aid, admin_msg):
                    admin_ok = True

            # سجّل فقط إن وصل شيء فعلاً — وإلا أعد المحاولة لاحقاً
            return delivered or admin_ok

        # 1) اشتراكات تنتهي خلال 3 أيام
        for sub in db.expiring_subscriptions(within_days=3):
            days = max(0, int((sub["expires_at"] - now) / 86400))
            kind = "pre1" if days <= 1 else "pre3"
            if db.reminder_sent(sub["user_id"], kind):
                continue
            exp_date = _dt.datetime.fromtimestamp(sub["expires_at"]).strftime("%Y-%m-%d")
            if deliver(sub, kind,
                       "sub_reminder_1d" if kind == "pre1" else "sub_reminder_3d",
                       "sub_admin_expiry", date=exp_date):
                db.log_reminder(sub["user_id"], kind)
                log.info("reminder %s sent for user #%s", kind, sub["user_id"])

        # 2) اشتراكات انتهت حديثاً
        for sub in db.recently_expired_subscriptions():
            if db.reminder_sent(sub["user_id"], "expired"):
                continue
            if deliver(sub, "expired", "sub_expired", "sub_admin_expired"):
                db.log_reminder(sub["user_id"], "expired")
                log.info("expired reminder sent for user #%s", sub["user_id"])

    # ---- تكامل واتساب ----
    async def _warn_wa_limit(self, row, owner_id, limit):
        """ينبّه صاحب البوت والأدمن مرة واحدة في الشهر عند نفاد الرصيد.
        بدون هذا يصمت البوت فجأة ولا يعرف أحد لماذا."""
        month = _time.strftime("%Y-%m")
        cfg = json.loads(row["config_json"] or "{}")
        if cfg.get("wa_limit_warned") == month:
            return
        cfg["wa_limit_warned"] = month
        db.update_bot_config(row["id"], cfg)
        msg = (f"⚠️ بوت واتساب «{row['name']}» توقّف عن الإرسال: "
               f"استهلكت {limit} رسالة هذا الشهر. رقّ باقتك أو انتظر الشهر القادم.")
        try:
            await self.notify_text_async(db.user_tg_channel(owner_id), msg)
        except Exception:
            log.exception("wa limit warning to owner")
        for aid in db.admin_chat_ids():
            try:
                await self.notify_text_async(aid, f"⚠️ حدّ واتساب: {msg}")
            except Exception:
                pass

    def process_wa_webhook(self, payload):
        """تُسلّم الـ payload لحلقة المدير بلا انتظار.
        Meta تتوقّع 200 فوراً وتُعيد الإرسال لو تأخّر الرد."""
        if self._loop is None:
            log.warning("WhatsApp webhook arrived before the manager loop started")
            return False
        try:
            asyncio.run_coroutine_threadsafe(self._handle_wa_webhook(payload), self._loop)
            return True
        except Exception:
            log.exception("Failed to dispatch WhatsApp webhook")
            return False

    async def _handle_meta_pages(self, payload):
        """ماسنجر (`object=page`) وإنستجرام (`object=instagram`): entry.id = الصفحة/الحساب،
        فالبوت هو صاحب التوكن `fb:<id>`/`ig:<id>`."""
        import flow_engine
        pfx = "fb" if payload.get("object") == "page" else "ig"
        for entry in payload.get("entry") or []:
            row = db.get_bot_by_token(f"{pfx}:{entry.get('id')}")
            if not row or not row.get("is_active"):
                # صفحة المنصة قبل إنشاء بوتها (أو بوت متوقف): يبقى الحدث ظاهراً في «/admin/meta»
                kinds = sorted({k for ev in entry.get("messaging") or [] for k in ev
                                if k not in ("sender", "recipient", "timestamp")} |
                               {c.get("field", "") for c in entry.get("changes") or []})
                db.log_meta_event(f"{pfx}:{entry.get('id')}", "unrouted",
                                  ("بوت متوقف · " if row else "بلا بوت · ") + ", ".join(k for k in kinds if k),
                                  bot_id=row["id"] if row else None)
                continue
            try:
                meta_side_events(row, entry, pfx)
            except Exception:
                log.exception("Meta side events failed for bot #%s", row["id"])
            ch = _meta_channel(row)
            for msg in ch.normalize_all({"entry": [entry]}):
                if not db.mark_msg_seen(msg.get("id")):
                    continue
                db.bump_received(row["id"], row["owner_id"])
                if not msg.get("name"):
                    # الاسم لصندوق الوارد — المحادثة المسمّاة لا تُسأل عنها Graph ثانيةً
                    conv = db.get_conversation(row["id"], msg["peer"]) or {}
                    msg["name"] = conv.get("name") or await ch.profile_name(msg["peer"])
                try:
                    await flow_engine.handle_message(row, ch, msg)
                except Exception:
                    log.exception("Meta %s message failed for bot #%s", pfx, row["id"])

    async def _handle_wa_webhook(self, payload):
        if (payload or {}).get("object") in ("page", "instagram"):
            try:
                await self._handle_meta_pages(payload)
            except Exception:
                log.exception("Error handling Messenger/Instagram webhook payload")
            return
        try:
            record_wa_echoes(payload)            # قبل الرسائل: رد الموبايل يُسكت البوت أولاً
        except Exception:
            log.exception("Error recording WhatsApp Business app echoes")
        try:
            import flow_engine
            for phone_id, entry_id, msgs in _split_wa_payload(payload):
                bot_row = db.get_bot_by_token(f"wa:{phone_id}")
                if not bot_row or not bot_row.get("is_active"):
                    log.warning("WhatsApp message for unknown or inactive phone_id: %s", phone_id)
                    continue
                _remember_waba_hint(bot_row, entry_id)
                channel = _wa_channel(bot_row)
                for msg in msgs:
                    # Meta تُعيد الإرسال عند أي تأخّر — بلا هذا يتقدّم الفلو مرتين
                    if not db.mark_msg_seen(msg.get("id")):
                        log.info("skipping duplicate WhatsApp message %s", msg.get("id"))
                        continue
                    db.bump_received(bot_row["id"], bot_row["owner_id"])
                    await flow_engine.handle_message(bot_row, channel, msg)
        except Exception:
            log.exception("Error handling WhatsApp webhook payload")

manager = BotManager()

