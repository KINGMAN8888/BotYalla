"""مكتبة وسائط صاحب النشاط — صور وفيديوهات يرسلها البوت (ترحيب · منتجات · خطوات · حملات).

منفصلة عمداً عن `media_store` (وسائط العملاء الواردة): تلك خاصة وتُحذف يتيمةً بعد
7 أيام، وهذه محتوى صاحب النشاط يعيش ما شاء. ثلاثة قيود تحكم كل ما هنا:

· **النوع من البايتات** (`media_store._sniff`) — لا من الترويسة ولا من الامتداد.
· **أضيق حدود القناتين:** صورة JPEG/PNG حتى 5MB وفيديو MP4 حتى 16MB هي حدود
  واتساب؛ تليجرام يقبل أكبر منها، فالملف المقبول هنا يصلح للقناتين معاً.
· **الرابط يُنزَّل مرة ويُحفظ نسخة** — رابط يختفي لاحقاً لا يكسر البوت — مع حماية
  SSRF: https على المنفذ 443 فقط، والعنوان يُحلّ ويُفحص ثم **يُتصل بالعنوان المفحوص
  نفسه** (لا حلّ ثانٍ يمكن أن يعيد عنواناً داخلياً — DNS rebinding)، وكل تحويل
  (redirect) يُفحص من جديد.
"""
import http.client
import ipaddress
import logging
import os
import secrets
import socket
import ssl
import time
import urllib.parse

log = logging.getLogger("asset_store")

BASE_DIR = os.path.join(
    os.environ.get("BOTYALLA_UPLOADS",
                   os.path.join(os.path.dirname(os.path.abspath(__file__)), "uploads")),
    "assets")

ALLOWED = {"image/jpeg": ".jpg", "image/png": ".png", "video/mp4": ".mp4"}
MAX_BYTES = {"image": 5 * 1024 * 1024, "video": 16 * 1024 * 1024}
MAX_ANY = max(MAX_BYTES.values())
MIN_BYTES = 64
FETCH_TIMEOUT = 15
MAX_REDIRECTS = 3


def path_of(fname):
    return os.path.join(BASE_DIR, fname)


def validate(data):
    """{'ok':True,'mime','kind'} أو {'ok':False,'reason'}. يفشل مغلقاً."""
    from media_store import _sniff, kind_of
    if not data or len(data) < MIN_BYTES:
        return {"ok": False, "reason": "too_small"}
    mime = _sniff(data[:16])
    # QuickTime (.mov) يحمل ftyp أيضاً فيراه `_sniff` فيديو — لكن واتساب يرفضه
    if mime == "video/mp4" and data[8:12] == b"qt  ":
        mime = None
    if mime not in ALLOWED:
        return {"ok": False, "reason": "type"}
    kind = kind_of(mime)
    if len(data) > MAX_BYTES[kind]:
        return {"ok": False, "reason": "too_large", "limit": MAX_BYTES[kind]}
    return {"ok": True, "mime": mime, "kind": kind}


def quota_ok(owner_id, role, plan_id, size):
    """هل تتسع المساحة؟ الأدمن والدعم بلا حد."""
    import database as db, plans
    if role in ("admin", "support"):
        return True
    return db.assets_bytes(owner_id) + int(size) <= plans.asset_bytes_limit(plan_id)


def save(owner_id, data, name="", source_url=None):
    """يتحقق ثم يكتب ثم يسجّل. يرجّع {'ok':True,'id',...} أو {'ok':False,'reason'}."""
    import database as db
    v = validate(data)
    if not v["ok"]:
        return v
    fname = f"a{owner_id}_{int(time.time())}_{secrets.token_hex(8)}{ALLOWED[v['mime']]}"
    os.makedirs(BASE_DIR, exist_ok=True)
    try:
        with open(path_of(fname), "wb") as f:
            f.write(data)
    except OSError:
        log.exception("could not write asset for owner #%s", owner_id)
        return {"ok": False, "reason": "disk"}
    aid = db.add_asset(owner_id, v["kind"], v["mime"], len(data), fname, name, source_url)
    return {"ok": True, "id": aid, "kind": v["kind"], "mime": v["mime"], "size": len(data)}


def delete_file(fname):
    try:
        os.remove(path_of(fname))
    except FileNotFoundError:
        pass
    except OSError:
        log.exception("could not delete asset file %s", fname)


# ------------------------------------------------------------- جلب رابط (SSRF)
def _public_ip(host):
    """أول عنوان عام يُحلّ إليه الاسم، أو None لو أيٌّ منها داخلي/محلي/محجوز.
    رفض الكل عند وجود عنوان داخلي واحد: اسم يُحلّ إلى عام وداخلي معاً فخّ معروف."""
    try:
        infos = socket.getaddrinfo(host, 443, proto=socket.IPPROTO_TCP)
    except (socket.gaierror, UnicodeError):
        return None
    ips = []
    for info in infos:
        try:
            a = ipaddress.ip_address(info[4][0].split("%")[0])
        except ValueError:
            return None
        if (a.is_private or a.is_loopback or a.is_link_local or a.is_multicast
                or a.is_reserved or a.is_unspecified
                or (a.version == 6 and a.ipv4_mapped is not None
                    and not a.ipv4_mapped.is_global)):
            return None
        ips.append(str(a))
    return ips[0] if ips else None


class _PinnedHTTPS(http.client.HTTPSConnection):
    """اتصال HTTPS بعنوان IP مفحوص مسبقاً، مع التحقق من الشهادة باسم المضيف."""
    def __init__(self, host, ip, **kw):
        super().__init__(host, 443, **kw)
        self._pinned_ip = ip

    def connect(self):
        sock = socket.create_connection((self._pinned_ip, 443), self.timeout)
        self.sock = self._context.wrap_socket(sock, server_hostname=self.host)


def _check_url(url):
    try:
        u = urllib.parse.urlsplit((url or "").strip())
    except ValueError:
        return None, "url"
    if u.scheme != "https" or not u.hostname or u.username or u.password:
        return None, "url"
    if u.port not in (None, 443):
        return None, "url"
    return u, None


def fetch_url(url):
    """ينزّل ملفاً من رابط عام. يرجّع (bytes, None) أو (None, reason)."""
    ctx = ssl.create_default_context()
    for _ in range(MAX_REDIRECTS + 1):
        u, err = _check_url(url)
        if err:
            return None, err
        ip = _public_ip(u.hostname)
        if not ip:
            return None, "host"
        path = (u.path or "/") + (f"?{u.query}" if u.query else "")
        conn = _PinnedHTTPS(u.hostname, ip, timeout=FETCH_TIMEOUT, context=ctx)
        try:
            conn.request("GET", path, headers={"User-Agent": "BotYalla-Media/1.0",
                                               "Accept": "image/jpeg,image/png,video/mp4,*/*;q=0.5"})
            resp = conn.getresponse()
            if resp.status in (301, 302, 303, 307, 308):
                loc = resp.getheader("Location") or ""
                url = urllib.parse.urljoin(url, loc)
                continue
            if resp.status != 200:
                return None, "download"
            length = resp.getheader("Content-Length")
            if length and length.isdigit() and int(length) > MAX_ANY:
                return None, "too_large"
            data = resp.read(MAX_ANY + 1)
            if len(data) > MAX_ANY:
                return None, "too_large"
            return data, None
        except (OSError, http.client.HTTPException, ssl.SSLError):
            log.info("asset fetch failed for host %s", u.hostname)
            return None, "download"
        finally:
            conn.close()
    return None, "download"
