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


# ============================================================
# التكامل الرسمي مع Telegram Bot API — تهيئة بروفايل البوت
# المصدر: https://core.telegram.org/bots/api  (setMyName/Description/Commands)
# ملاحظة: تيليجرام لا يوفّر API لإنشاء بوت (BotFather يدوي)، لكنه يوفّر
# رسمياً تهيئة البوت الموجود بالكامل. هذه الدوال تستخدم ذلك.
# ============================================================
def _tg_post(token, method, payload, timeout=15):
    url = f"{TG_API}/bot{token}/{method}"
    data = _json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data,
                                 headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = _json.loads(resp.read().decode("utf-8"))
            return bool(body.get("ok")), body.get("description", "")
    except urllib.error.HTTPError as e:
        try:
            body = _json.loads(e.read().decode("utf-8"))
            return False, body.get("description", f"HTTP {e.code}")
        except Exception:
            return False, f"HTTP {e.code}"
    except Exception as e:
        return False, str(e)


def configure_bot_profile(token, name=None, short_description=None,
                          description=None, commands=None):
    """تهيئة بروفايل البوت رسمياً عبر Telegram Bot API.
    يرجّع dict بنتيجة كل خطوة: {name, short, desc, commands, errors:[]}."""
    result = {"name": None, "short": None, "desc": None, "commands": None, "errors": []}
    if name:
        ok, err = _tg_post(token, "setMyName", {"name": name[:64]})
        result["name"] = ok
        if not ok: result["errors"].append(f"name: {err}")
    if short_description is not None:
        ok, err = _tg_post(token, "setMyShortDescription",
                           {"short_description": short_description[:120]})
        result["short"] = ok
        if not ok: result["errors"].append(f"short: {err}")
    if description is not None:
        ok, err = _tg_post(token, "setMyDescription",
                           {"description": description[:512]})
        result["desc"] = ok
        if not ok: result["errors"].append(f"desc: {err}")
    if commands:
        ok, err = _tg_post(token, "setMyCommands", {"commands": commands})
        result["commands"] = ok
        if not ok: result["errors"].append(f"commands: {err}")
    result["ok"] = not result["errors"]
    return result


def _tg_multipart(token, method, fields, files, timeout=20):
    """طلب multipart لرفع ملف (صورة البروفايل) — نفس شكل نتيجة `_tg_post`: (ok, وصف الخطأ)."""
    boundary = "----BotYalla" + secrets.token_hex(12)
    parts = []
    for k, v in fields.items():
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode("utf-8"))
    for k, (fname, data, ctype) in files.items():
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"; filename="{fname}"\r\n'
                     f'Content-Type: {ctype}\r\n\r\n'.encode("utf-8") + data + b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode("utf-8"))
    req = urllib.request.Request(f"{TG_API}/bot{token}/{method}", data=b"".join(parts), method="POST",
                                 headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = _json.loads(resp.read().decode("utf-8"))
            return bool(body.get("ok")), body.get("description", "")
    except urllib.error.HTTPError as e:
        try:
            return False, _json.loads(e.read().decode("utf-8")).get("description", f"HTTP {e.code}")
        except Exception:
            return False, f"HTTP {e.code}"
    except Exception as e:
        return False, str(e)


def set_bot_photo(token, jpeg):
    """صورة بروفايل البوت نفسه (Bot API 9.4 · setMyProfilePhoto). الثابتة JPG فقط، ولا تُعاد
    صورة سابقة — تُرفع ملفاً جديداً كل مرة (InputProfilePhotoStatic + attach://)."""
    return _tg_multipart(token, "setMyProfilePhoto",
                         {"photo": _json.dumps({"type": "static", "photo": "attach://botphoto"})},
                         {"botphoto": ("photo.jpg", jpeg, "image/jpeg")})


def remove_bot_photo(token):
    return _tg_post(token, "removeMyProfilePhoto", {})


def default_commands(template):
    """أوامر البوت الافتراضية حسب النوع (تظهر في قائمة الأوامر بتليجرام)."""
    cmds = [{"command": "start", "description": "ابدأ / Start"}]
    if template == "store":
        # إدارة المنتجات من داخل البوت (إضافة مدفوعة) — الأمر ظاهر للكل ليجده صاحب
        # المتجر بلا شرح، والبوت يردّ على أي شخص آخر بسطر واحد أنه لصاحب المتجر.
        cmds.append({"command": "products", "description": "إدارة المنتجات (لصاحب المتجر)"})
    return cmds


def build_profile_from_config(cfg, template):
    """يشتق اسم/وصف احترافي من إعدادات البوت لإرساله لتليجرام."""
    biz = (cfg.get("business_name") or "").strip()
    name = biz[:64] if biz else None
    short = (f"بوت {biz} — خدمة عملاء وطلبات على مدار الساعة." if biz else None)
    welcome = (cfg.get("welcome") or "").strip()
    if welcome:
        desc = welcome[:512]
    elif biz:
        desc = f"مرحباً بك في {biz}! اضغط ابدأ للتعامل مع البوت."
    else:
        desc = None
    return {"name": name, "short_description": short, "description": desc,
            "commands": default_commands(template)}
