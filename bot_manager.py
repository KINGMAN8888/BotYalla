"""مدير BotYalla — يشغّل عدة بوتات في حلقة asyncio بخيط منفصل + بث جماعي."""
import asyncio, json, threading, logging, time as _time, datetime as _dt
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

def _wa_channel(row):
    """يبني قناة واتساب من صف البوت. التوكن مخزّن كـ wa:<phone_number_id>."""
    from channels.whatsapp import WhatsAppChannel
    cfg = json.loads(row["config_json"] or "{}")
    token = row["token"] or ""
    phone_id = token[3:] if token.startswith("wa:") else token
    return WhatsAppChannel(phone_id, cfg.get("wa_token", ""))

class BotManager:
    def __init__(self):
        self._loop = None; self._thread = None
        self._apps = {}; self._ready = threading.Event(); self._platform = None

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

    def start_bot(self, bot_id):
        if self.is_running(bot_id): return True, "يعمل بالفعل"
        row = db.get_bot(bot_id)
        if not row: return False, "البوت غير موجود"
        try:
            self._submit(self._start(row)); db.set_bot_active(bot_id, True)
            return True, "تم التشغيل ✅"
        except Exception as e:
            log.exception("start"); return False, f"فشل التشغيل: {e}"

    async def _start(self, row):
        if row.get("channel") == "whatsapp":
            self._apps[row["id"]] = {"type": "whatsapp"}
            return
            
        cfg = json.loads(row["config_json"] or "{}")
        app = Application.builder().token(row["token"]).build()
        app.bot_data["config"] = cfg; app.bot_data["bot_id"] = row["id"]
        tmpl = T.TEMPLATES.get(row["template"])
        if not tmpl: raise ValueError("قالب غير معروف")
        tmpl["build"](app)
        tg.register_common(app)
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
            if isinstance(app, dict) and app.get("type") == "whatsapp":
                return
            if app.updater and app.updater.running: await app.updater.stop()
            await app.stop(); await app.shutdown()

    def restart_bot(self, bot_id):
        self.stop_bot(bot_id); return self.start_bot(bot_id)

    def broadcast(self, bot_id, text):
        """إرسال رسالة لكل مشتركي البوت. يرجّع (تم, فشل)."""
        row = db.get_bot(bot_id)
        if not row: return 0, 0
        if (row.get("channel") or "telegram") == "whatsapp":
            # واتساب يمنع المراسلة الحرة بعد 24 ساعة من آخر رسالة للعميل،
            # والمخالفة تُقيّد الرقم. نبثّ داخل النافذة فقط.
            ids = db.list_bot_peers(bot_id, within_seconds=WA_WINDOW)
            skipped = len(db.list_bot_peers(bot_id)) - len(ids)
            if skipped:
                log.info("broadcast: skipped %s WhatsApp peers outside the 24h window", skipped)
        else:
            ids = db.list_bot_user_ids(bot_id)
        if not ids: return 0, 0
        try:
            return self._submit(self._broadcast(row, ids, text), timeout=max(30, len(ids)*0.5))
        except Exception as e:
            log.exception("broadcast"); return 0, len(ids)

    async def _broadcast(self, row, ids, text):
        if (row.get("channel") or "telegram") == "whatsapp":
            return await self._broadcast_wa(row, ids, text)

        app = self._apps.get(row["id"])
        bot = app.bot if app else Bot(row["token"])
        own = app is None
        if own: await bot.initialize()
        sent = failed = 0
        for uid in ids:
            try:
                await bot.send_message(uid, text); sent += 1
                await asyncio.sleep(0.05)   # احترام حدود المعدل
            except Exception:
                failed += 1
        if own: await bot.shutdown()
        return sent, failed

    async def _broadcast_wa(self, row, peers, text):
        channel = _wa_channel(row)
        sent = failed = 0
        for peer in peers:
            try:
                ok = await channel.send_text(peer, text)
                sent += 1 if ok else 0
                failed += 0 if ok else 1
                await asyncio.sleep(0.1)
            except Exception:
                failed += 1
        return sent, failed

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
        app = Application.builder().token(token).build()
        PB.register(app)
        await app.initialize(); await app.start()
        await app.updater.start_polling(drop_pending_updates=True)
        self._platform = app

    async def _stop_platform(self):
        app = self._platform; self._platform = None
        if app:
            if app.updater and app.updater.running: await app.updater.stop()
            await app.stop(); await app.shutdown()

    def platform_running(self):
        return self._platform is not None

    def notify_text(self, chat_id, text):
        """إرسال رسالة نصية للأدمن عبر بوت المنصة (best-effort).
        لا تُستدعى من داخل حلقة المدير نفسها — استخدم notify_text_async هناك."""
        if self._platform is None or not chat_id:
            return False
        try:
            self._submit(self._platform.bot.send_message(int(chat_id), text)); return True
        except Exception:
            log.exception("notify_text"); return False

    async def notify_text_async(self, chat_id, text):
        """نفس الغرض لكن من داخل حلقة asyncio (يتجنّب انتظار النتيجة على نفس الحلقة)."""
        if self._platform is None or not chat_id:
            return False
        try:
            await self._platform.bot.send_message(int(chat_id), text); return True
        except Exception:
            log.exception("notify_text_async"); return False

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
            except Exception:
                log.exception("chat_state purge error")
            _time.sleep(INTERVAL)

    def _send_reminder_cycle(self):
        """يفحص الاشتراكات ويرسل التذكيرات المناسبة.

        التسجيل في reminder_log يتم **فقط عند وصول رسالة فعلاً**. لو كان بوت
        المنصة متوقفاً فلا شيء يُسجَّل وتُعاد المحاولة في الدورة التالية —
        وإلا لأحرقت أول دورة كل التذكيرات نهائياً بسبب قيد UNIQUE.
        """
        admin_ids = db.admin_chat_ids()
        if not self.platform_running():
            log.info("reminders skipped: platform bot not running")
            return

        now = int(_time.time())

        def deliver(sub, kind, user_key, admin_key, **fmt):
            """يرسل للعميل وللأدمن. يرجّع True لو وصلت رسالة واحدة على الأقل."""
            lang = db.user_lang(sub["user_id"])
            plan_name = plans.plan_name(sub["plan"], lang)
            delivered = False

            tg_id = sub.get("tg_chat_id")
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

    async def _handle_wa_webhook(self, payload):
        try:
            val = payload["entry"][0]["changes"][0]["value"]
            if not val.get("messages"):
                return          # تحديث حالة تسليم أو ما شابه — ليس رسالة واردة

            phone_id = val["metadata"]["phone_number_id"]
            bot_row = db.get_bot_by_token(f"wa:{phone_id}")
            if not bot_row or not bot_row.get("is_active"):
                log.warning("WhatsApp message for unknown or inactive phone_id: %s", phone_id)
                return

            channel = _wa_channel(bot_row)
            msg = channel.normalize(payload)
            if msg:
                import flow_engine
                await flow_engine.handle_message(bot_row, channel, msg)
        except Exception:
            log.exception("Error handling WhatsApp webhook payload")

manager = BotManager()

