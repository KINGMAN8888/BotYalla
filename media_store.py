"""تخزين وسائط العملاء (صور/صوت/فيديو/ملفات) القادمة من البوتات.

الملف على القرص والسجل في جدول `media`. ثلاثة قيود تحكم كل ما هنا:
· **القرص مورد محدود** على سيرفر صغير — حدّ لحجم الملف وحصة شهرية لكل حساب.
· **لا نثق في نوع الملف المُعلَن** — نتحقق من البايتات الأولى (magic bytes)،
  فامتداد صورة على ملف تنفيذي لا يجعله صورة.
· **الاسم يُولَّد داخلياً** — اسم العميل لا يلمس القرص إطلاقاً.

الملفات خارج `static/` وتُقدَّم فقط عبر مسار يفرض ملكية البوت."""
import logging, os, secrets, time

log = logging.getLogger("media_store")

BASE_DIR = os.path.join(
    os.environ.get("BOTYALLA_UPLOADS",
                   os.path.join(os.path.dirname(os.path.abspath(__file__)), "uploads")),
    "media")

# حدود Meta للوارد: صورة 5MB · صوت وفيديو 16MB · ملف 100MB.
# نحن أضيق منها عمداً: الوارد الحقيقي أصغر بكثير، والسقف الواسع بابُ إغراق للقرص.
MAX_BYTES = {"image": 6 * 1024 * 1024, "audio": 16 * 1024 * 1024,
             "video": 16 * 1024 * 1024, "document": 10 * 1024 * 1024}
MIN_BYTES = 64

# ما نقبله فعلاً. أي شيء آخر يُرفض ولا يُكتب على القرص.
EXT = {
    "image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp", "image/gif": ".gif",
    "audio/ogg": ".ogg", "audio/mpeg": ".mp3", "audio/mp4": ".m4a", "audio/aac": ".aac",
    "audio/amr": ".amr", "audio/wav": ".wav", "audio/x-wav": ".wav",
    "video/mp4": ".mp4", "video/3gpp": ".3gp",
    "application/pdf": ".pdf",
}


def _sniff(head):
    """نوع الملف من بايتاته الأولى — لا من ترويسة يرسلها الطرف الآخر."""
    if head[:3] == b"\xff\xd8\xff":                            return "image/jpeg"
    if head[:8] == b"\x89PNG\r\n\x1a\n":                       return "image/png"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":          return "image/webp"
    if head[:6] in (b"GIF87a", b"GIF89a"):                     return "image/gif"
    if head[:4] == b"OggS":                                    return "audio/ogg"
    if head[:3] == b"ID3" or head[:2] in (b"\xff\xfb", b"\xff\xf3", b"\xff\xf2"):
        return "audio/mpeg"
    if head[:2] in (b"\xff\xf1", b"\xff\xf9"):                 return "audio/aac"
    if head[:5] == b"#!AMR":                                   return "audio/amr"
    if head[:4] == b"RIFF" and head[8:12] == b"WAVE":          return "audio/wav"
    if head[4:8] == b"ftyp":
        brand = head[8:12]
        if brand[:3] == b"3gp":                                return "video/3gpp"
        if brand in (b"M4A ", b"M4B "):                        return "audio/mp4"
        return "video/mp4"                                     # mp42/isom/qt وغيرها
    if head[:5] == b"%PDF-":                                   return "application/pdf"
    return None


def kind_of(mime):
    mime = (mime or "").split(";")[0].strip().lower()
    if mime.startswith("image/"): return "image"
    if mime.startswith("audio/"): return "audio"
    if mime.startswith("video/"): return "video"
    return "document"


def path_of(fname):
    return os.path.join(BASE_DIR, fname)


def quota_left(owner_id, role, plan_id):
    """None = بلا حد. الرقم = ما تبقّى من ملفات هذا الشهر."""
    import database as db, plans
    if role in ("admin", "support"):
        return None
    return max(0, plans.media_limit(plan_id) - db.media_count_this_month(owner_id))


def save(bot_row, peer, data, declared_mime="", caption="", quota=None):
    """يحفظ ملفاً وارداً ويرجّع dict فيه media_id، أو {'ok':False,'reason':...}.

    quota: عدد الملفات المتبقية هذا الشهر (None = بلا حد)."""
    import database as db

    if quota is not None and quota <= 0:
        return {"ok": False, "reason": "quota"}
    if not data:
        return {"ok": False, "reason": "empty"}
    if len(data) < MIN_BYTES:
        return {"ok": False, "reason": "too_small"}

    # التوقيع وحده يحدّد النوع. النوع المُعلَن يتحكم فيه المُرسِل، فالرجوع إليه
    # عند فشل الكشف يُلغي الفحص كله: ملف تنفيذي مُعلَن كصورة يُحفظ بامتداد .jpg
    # ثم يُقدَّم لاحقاً. نفشل مغلقين.
    mime = _sniff(data[:16])
    if not mime or mime not in EXT:
        return {"ok": False, "reason": "type", "declared": declared_mime}

    kind = kind_of(mime)
    if len(data) > MAX_BYTES.get(kind, MAX_BYTES["document"]):
        return {"ok": False, "reason": "too_large", "limit": MAX_BYTES.get(kind)}

    bot_id = bot_row["id"]
    fname = f"{bot_id}_{int(time.time())}_{secrets.token_hex(8)}{EXT[mime]}"
    os.makedirs(BASE_DIR, exist_ok=True)
    dest = path_of(fname)
    try:
        with open(dest, "wb") as f:
            f.write(data)
    except OSError:
        log.exception("could not write media for bot #%s", bot_id)
        return {"ok": False, "reason": "disk"}

    mid = db.add_media(bot_id, bot_row["owner_id"], peer, kind, mime,
                       len(data), fname, (caption or "")[:500])
    return {"ok": True, "id": mid, "kind": kind, "mime": mime, "size": len(data)}


def delete_files(rows):
    """يحذف الملفات من القرص. يُستدعى مع تنظيف السجلات اليتيمة."""
    gone = 0
    for r in rows:
        try:
            os.remove(path_of(r["fname"]))
            gone += 1
        except FileNotFoundError:
            gone += 1                      # السجل باقٍ بلا ملف — يُحذف أيضاً
        except OSError:
            log.exception("could not delete media file %s", r.get("fname"))
    return gone
