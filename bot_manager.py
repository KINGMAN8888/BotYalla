"""مدير BotYalla — يشغّل عدة بوتات في حلقة asyncio بخيط منفصل + بث جماعي."""
import asyncio, json, threading, logging
from telegram import Bot
from telegram.ext import Application
import database as db
import templates_bot as T
import tg_helpers as tg
import platform_bot as PB

log = logging.getLogger("bot_manager")

class BotManager:
    def __init__(self):
        self._loop = None; self._thread = None
        self._apps = {}; self._ready = threading.Event(); self._platform = None

    def start(self):
        if self._thread and self._thread.is_alive(): return
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start(); self._ready.wait(timeout=10)

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
            if app.updater and app.updater.running: await app.updater.stop()
            await app.stop(); await app.shutdown()

    def restart_bot(self, bot_id):
        self.stop_bot(bot_id); return self.start_bot(bot_id)

    def broadcast(self, bot_id, text):
        """إرسال رسالة لكل مشتركي البوت. يرجّع (تم, فشل)."""
        ids = db.list_bot_user_ids(bot_id)
        if not ids: return 0, 0
        row = db.get_bot(bot_id)
        try:
            return self._submit(self._broadcast(row, ids, text), timeout=max(30, len(ids)*0.5))
        except Exception as e:
            log.exception("broadcast"); return 0, len(ids)

    async def _broadcast(self, row, ids, text):
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
        """إرسال رسالة نصية للأدمن عبر بوت المنصة (best-effort)."""
        if self._platform is None or not chat_id:
            return False
        try:
            self._submit(self._platform.bot.send_message(int(chat_id), text)); return True
        except Exception:
            log.exception("notify_text"); return False

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

manager = BotManager()
