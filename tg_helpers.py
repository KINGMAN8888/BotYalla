"""تكامل تليجرام الآمن:
- validate_token: يتحقق من صحة التوكن عبر getMe ويرجّع اسم/يوزر البوت.
- try_claim_owner: ربط الأدمن بضغطة عبر رابط deep-link يحمل كود لمرة واحدة.
- register_common: يضيف /id (معرفة المعرّف) و /owner CODE (ربط يدوي) لأي بوت.
لا يجمع أي بيانات دخول حسابات — يعتمد فقط على توكن البوت الرسمي."""
import secrets
import json as _json
import urllib.request
import urllib.error
from telegram import Update
from telegram.ext import CommandHandler, ContextTypes
import database as db

TG_API = "https://api.telegram.org"

def validate_token(token: str, timeout=10) -> dict:
    """يرجّع {'ok':True,'username':..,'name':..,'id':..} أو {'ok':False,'error':..}."""
    token = (token or "").strip()
    if ":" not in token or len(token) < 20:
        return {"ok": False, "error": "صيغة التوكن غير صحيحة"}
    try:
        url = f"{TG_API}/bot{token}/getMe"
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            data = _json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        # تليجرام يرجّع 401/404 مع جسم JSON للتوكن الخاطئ
        try:
            data = _json.loads(e.read().decode("utf-8"))
        except Exception:
            return {"ok": False, "error": "التوكن غير صالح أو مرفوض"}
    except Exception as e:
        return {"ok": False, "error": f"تعذّر الاتصال بتليجرام: {e}"}
    if not data.get("ok"):
        return {"ok": False, "error": "التوكن غير صالح أو مرفوض"}
    res = data["result"]
    return {"ok": True, "id": res.get("id"),
            "username": res.get("username"), "name": res.get("first_name")}

def gen_owner_code() -> str:
    return secrets.token_hex(4)   # 8 hex chars

def owner_deep_link(bot_username: str, code: str) -> str:
    return f"https://t.me/{bot_username}?start=owner-{code}"

async def try_claim_owner(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> bool:
    """يُستدعى في بداية أي بوت: لو رابط الدخول يحمل كود الأدمن الصحيح يربط الحساب."""
    args = getattr(ctx, "args", None) or []
    cfg = ctx.application.bot_data.get("config", {})
    code = cfg.get("pending_owner_code")
    if args and code and args[0] == f"owner-{code}":
        u = update.effective_user
        cfg["owner_chat_id"] = str(u.id)
        cfg["pending_owner_code"] = None
        db.update_bot_config(ctx.application.bot_data["bot_id"], cfg)
        await update.message.reply_text(
            f"✅ تم ربط حسابك كأدمن بنجاح!\n🆔 معرّفك: `{u.id}`\n"
            "سيصلك الآن إشعار بكل الطلبات على هذا البوت.",
            parse_mode="Markdown")
        return True
    return False

def register_common(app):
    """يضيف أوامر عامة لكل بوت."""
    async def id_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        u = update.effective_user
        await update.message.reply_text(
            f"🆔 معرّفك في تليجرام هو:\n`{u.id}`\n\nانسخه والصقه في لوحة التحكم.",
            parse_mode="Markdown")

    async def owner_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        # ربط يدوي: /owner CODE
        cfg = ctx.application.bot_data.get("config", {})
        code = cfg.get("pending_owner_code")
        args = ctx.args or []
        if code and args and args[0] == code:
            u = update.effective_user
            cfg["owner_chat_id"] = str(u.id); cfg["pending_owner_code"] = None
            db.update_bot_config(ctx.application.bot_data["bot_id"], cfg)
            await update.message.reply_text(f"✅ تم ربط حسابك كأدمن! معرّفك: {u.id}")
        else:
            await update.message.reply_text("⚠️ كود غير صحيح أو منتهٍ. أنشئ رابط ربط جديد من لوحة التحكم.")

    app.add_handler(CommandHandler("id", id_cmd))
    app.add_handler(CommandHandler("owner", owner_cmd))
