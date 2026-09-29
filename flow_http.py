"""طلبات HTTP الصادرة من بطاقتي «API» و«Google Sheets» في الفلو المرئي (المرحلة 5).

الرابط يكتبه صاحب البوت، فهو مدخل غير موثوق من جهة الخادم (SSRF): HTTPS على 443 فقط، والمضيف
يُحلّ ويُرفض لو أيٌّ من عناوينه داخلي، والاتصال مثبّت على العنوان المفحوص (لا DNS rebinding) —
نفس حماية asset_store.fetch_url. لا تحويلات إلا لـ Google Sheets (Apps Script يحوّل دائماً)،
وكل قفزة تُفحص من جديد. الرد محدود الحجم والمهلة: الفلو لا ينتظر خادماً بطيئاً إلى الأبد.
"""
import json
import logging
import ssl
import urllib.parse

import asset_store as AS

log = logging.getLogger("flow_http")

TIMEOUT = 8
MAX_BODY = 256 * 1024
MAX_HOPS = 3
UA = "BotYalla-Flow/1.0"


def request(method, url, headers=None, body=None, follow=False):
    """(status, payload) — payload JSON محلول لو أمكن وإلا نص. (0, سبب) عند الرفض أو الفشل."""
    ctx = ssl.create_default_context()
    for _ in range(MAX_HOPS if follow else 1):
        u, err = AS._check_url(url)
        if err:
            return 0, "url"
        ip = AS._public_ip(u.hostname)
        if not ip:
            return 0, "host"
        path = (u.path or "/") + (f"?{u.query}" if u.query else "")
        h = {"User-Agent": UA, "Accept": "application/json, text/plain;q=0.9, */*;q=0.1"}
        h.update(headers or {})
        data = None
        if body is not None:
            data = body.encode("utf-8") if isinstance(body, str) else body
            h.setdefault("Content-Type", "application/json")
        conn = AS._PinnedHTTPS(u.hostname, ip, timeout=TIMEOUT, context=ctx)
        try:
            conn.request(method, path, body=data, headers=h)
            r = conn.getresponse()
            if follow and r.status in (301, 302, 303, 307, 308) and r.getheader("Location"):
                url = urllib.parse.urljoin(url, r.getheader("Location"))
                if r.status in (301, 302, 303):
                    method, body = "GET", None          # كما يفعل المتصفح — Apps Script يتوقّعه
                    headers = {k: v for k, v in (headers or {}).items() if k.lower() != "content-type"}
                continue
            raw = r.read(MAX_BODY + 1)
            if len(raw) > MAX_BODY:
                return r.status, "too_large"
            text = raw.decode("utf-8", "replace")
            try:
                return r.status, json.loads(text)
            except ValueError:
                return r.status, text
        except Exception as e:
            log.info("flow http %s %s failed: %s", method, u.hostname, str(e)[:200])
            return 0, "network"
        finally:
            conn.close()
    return 0, "redirects"


def pick(payload, path):
    """قيمة من رد JSON بمسار نقطي: `data.items.0.name`. None لو لم توجد."""
    cur = payload
    for part in (path or "").split("."):
        if isinstance(cur, dict):
            cur = cur.get(part)
        elif isinstance(cur, list) and part.lstrip("-").isdigit() and -len(cur) <= int(part) < len(cur):
            cur = cur[int(part)]
        else:
            return None
        if cur is None:
            return None
    return cur
