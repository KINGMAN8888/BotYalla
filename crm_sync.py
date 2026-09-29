"""مزامنة CRM الخارجي — المرحلة 9: جهات اتصال BotYalla وإدخالات الفلو ⇒ HubSpot أو Zoho CRM.

اتجاه واحد (BotYalla ⇒ CRM) بمؤشّر لكل حساب: كل جهة اتصال أُنشئت أو تغيّرت منذ آخر مزامنة تُطابَق
في الـ CRM (بالبريد ثم الهاتف) فتُحدَّث أو تُنشأ، وكل «إدخال» جديد (إجابات نموذج/فلو) يصبح **ملاحظة**
على جهة الاتصال هناك. الربط محفوظ (`crm_links`) فلا يُبحث عن الجهة كل مرة.

القواعد (AGENTS §70):
  · الأسرار مختومة (`db.seal`) ولا تصل المتصفح؛ لا شيء يُحذف في الـ CRM أبداً.
  · فشل الـ CRM (حدّ طلبات · توكن منتهٍ) يوقف الدفعة ويُعاد لاحقاً من نفس المؤشّر — لا تخطٍّ صامت.
  · دفعة محدودة لكل حساب في الدورة (`BATCH`) احتراماً لحدود المزوّد.
"""
import hashlib
import json
import logging
import time
from datetime import datetime, timezone

import httpx

import database as db

log = logging.getLogger("crm_sync")
PROVIDERS = ("hubspot", "zoho")
ZOHO_DC = ("com", "sa", "eu", "in", "com.au", "jp", "ca")
CFG_KEY = "crm_sync"
BATCH = 100
TIMEOUT = 20
HUBSPOT = "https://api.hubapi.com"
_ZOHO_TOKENS = {}                 # owner ⇒ (access_token, api_domain, expires_at) في الذاكرة فقط
HOOKS = {"gate": lambda owner_id: True}      # app.py: بوابة باقة الشركات (_owner_crm)


class SyncError(Exception):
    pass


# ─────────────────────────── الإعداد ───────────────────────────
def _raw(owner_id):
    try:
        return json.loads(db.get_setting(owner_id, CFG_KEY) or "{}")
    except ValueError:
        return {}


def config(owner_id):
    """الإعداد بأسراره مفتوحة — للخادم فقط."""
    c = _raw(owner_id)
    if c.get("provider") not in PROVIDERS:
        return None
    out = {k: c.get(k) for k in ("provider", "dc", "enabled", "notes", "two_way")}
    for k in ("token", "client_id", "client_secret", "refresh_token"):
        out[k] = db.unseal(c[k]) if c.get(k) else ""
    return out


def public_config(owner_id):
    c = _raw(owner_id)
    return {"provider": c.get("provider") or "", "dc": c.get("dc") or "com", "enabled": bool(c.get("enabled")),
            "notes": c.get("notes", True) is not False, "connected": bool(c.get("token") or c.get("refresh_token")),
            "last_at": c.get("last_at"), "last_error": c.get("last_error") or "", "synced": c.get("synced") or 0,
            "client_id": c.get("client_id_hint") or "", "two_way": bool(c.get("two_way")), "pulled": c.get("pulled") or 0}


def save_config(owner_id, provider, *, token=None, client_id=None, client_secret=None, refresh_token=None,
                dc="com", enabled=True, notes=True, two_way=False):
    old = _raw(owner_id)
    same = old.get("provider") == provider
    c = {"provider": provider, "dc": dc if dc in ZOHO_DC else "com", "enabled": bool(enabled), "notes": bool(notes),
         # السحب من الـ CRM: من لحظة تفعيله فقط (ما عُدّل هناك بعدها) — الجهات القديمة تصل عبر الدفع الأول والمطابقة
         "two_way": bool(two_way), "pulled": old.get("pulled", 0) if same else 0,
         "pull_cursor": old.get("pull_cursor") if same and old.get("two_way") else int(time.time() * 1000),
         # جهات الاتصال: مزامنة أولى كاملة. الملاحظات: من الآن فقط — لا نغرق الـ CRM بإدخالات السنين الماضية
         "cursor": old.get("cursor", 0) if same else 0,
         "lead_cursor": old.get("lead_cursor", 0) if same else db.max_lead_id(owner_id),
         "synced": old.get("synced", 0) if same else 0, "last_at": old.get("last_at") if same else None}
    for k, v in (("token", token), ("client_id", client_id), ("client_secret", client_secret), ("refresh_token", refresh_token)):
        c[k] = db.seal(v) if v else (old.get(k) if same else None)
    c["client_id_hint"] = (client_id[:6] + "…") if client_id else (old.get("client_id_hint") if same else "")
    if not same:
        with db.get_conn() as conn:                             # مزوّد جديد = روابط جديدة
            conn.execute("DELETE FROM crm_links WHERE owner_id=?", (owner_id,))
    _ZOHO_TOKENS.pop(owner_id, None)
    db.set_setting(owner_id, CFG_KEY, json.dumps(c))


def clear_config(owner_id):
    _ZOHO_TOKENS.pop(owner_id, None)
    with db.get_conn() as conn:
        conn.execute("DELETE FROM crm_links WHERE owner_id=?", (owner_id,))
    db.set_setting(owner_id, CFG_KEY, "")


def _update_state(owner_id, **kw):
    c = _raw(owner_id)
    if not c:
        return
    c.update(kw)
    db.set_setting(owner_id, CFG_KEY, json.dumps(c))


def _ms(iso):
    """تاريخ ISO من الـ CRM ⇒ مللي ثانية UTC (0 لو غير مفهوم)."""
    try:
        return int(datetime.fromisoformat(str(iso).replace("Z", "+00:00")).timestamp() * 1000)
    except (TypeError, ValueError):
        return 0


def fingerprint(name, phone, email):
    """بصمة القيم المتزامنة — إن تطابقت مع المحفوظة فلا شيء تغيّر فعلاً (لا صدى بين الطرفين)."""
    import crm as CRM
    p = CRM.norm_phone(phone, "+966") if phone else ""
    raw = "|".join((" ".join(str(name or "").split()), p or "", str(email or "").strip().lower()))
    return hashlib.sha256(raw.encode()).hexdigest()[:24]


def _split(name):
    parts = str(name or "").strip().split()
    if not parts:
        return "", ""
    return parts[0], " ".join(parts[1:])


# ─────────────────────────── HubSpot ───────────────────────────
class HubSpot:
    def __init__(self, cfg, http):
        self.h = {"Authorization": f"Bearer {cfg['token']}", "Content-Type": "application/json"}
        self.http = http

    def _req(self, method, path, body=None):
        r = self.http.request(method, HUBSPOT + path, headers=self.h, json=body)
        if r.status_code == 401:
            raise SyncError("auth")
        if r.status_code == 429:
            raise SyncError("rate")
        if r.status_code >= 400:
            raise SyncError(f"hubspot {r.status_code}: {r.text[:200]}")
        return r.json() if r.content else {}

    def test(self):
        self._req("GET", "/crm/v3/objects/contacts?limit=1")

    def _find(self, prop, value):
        if not value:
            return None
        res = self._req("POST", "/crm/v3/objects/contacts/search", {
            "filterGroups": [{"filters": [{"propertyName": prop, "operator": "EQ", "value": value}]}], "limit": 1})
        rows = res.get("results") or []
        return str(rows[0]["id"]) if rows else None

    def upsert(self, ct, ext_id):
        first, last = _split(ct.get("name"))
        props = {k: v for k, v in {"firstname": first, "lastname": last, "phone": ct.get("phone"),
                                   "email": ct.get("email")}.items() if v}
        ext_id = ext_id or self._find("email", ct.get("email")) or self._find("phone", ct.get("phone"))
        if ext_id:
            self._req("PATCH", f"/crm/v3/objects/contacts/{ext_id}", {"properties": props})
            return ext_id
        return str(self._req("POST", "/crm/v3/objects/contacts", {"properties": props})["id"])

    def changed(self, since_ms):
        """جهات عُدّلت في HubSpot بعد المؤشّر، الأقدم أولاً."""
        res = self._req("POST", "/crm/v3/objects/contacts/search", {
            "filterGroups": [{"filters": [{"propertyName": "lastmodifieddate", "operator": "GT", "value": str(int(since_ms))}]}],
            "sorts": [{"propertyName": "lastmodifieddate", "direction": "ASCENDING"}],
            "properties": ["firstname", "lastname", "phone", "email", "lastmodifieddate"], "limit": 100})
        out = []
        for r in res.get("results") or []:
            p = r.get("properties") or {}
            out.append({"ext": str(r["id"]), "name": " ".join(x for x in (p.get("firstname"), p.get("lastname")) if x),
                        "phone": p.get("phone"), "email": p.get("email"),
                        "ts": _ms(p.get("lastmodifieddate") or r.get("updatedAt"))})
        return out

    def note(self, ext_id, text, ts):
        self._req("POST", "/crm/v3/objects/notes", {
            "properties": {"hs_timestamp": int(ts) * 1000, "hs_note_body": text},
            "associations": [{"to": {"id": ext_id},
                              "types": [{"associationCategory": "HUBSPOT_DEFINED", "associationTypeId": 202}]}]})


# ─────────────────────────── Zoho CRM ───────────────────────────
class Zoho:
    def __init__(self, cfg, http, owner_id):
        self.cfg, self.http, self.owner = cfg, http, owner_id

    def _token(self):
        tok = _ZOHO_TOKENS.get(self.owner)
        if tok and tok[2] > time.time() + 60:
            return tok
        r = self.http.post(f"https://accounts.zoho.{self.cfg.get('dc') or 'com'}/oauth/v2/token", params={
            "refresh_token": self.cfg["refresh_token"], "client_id": self.cfg["client_id"],
            "client_secret": self.cfg["client_secret"], "grant_type": "refresh_token"})
        body = r.json() if r.content else {}
        if r.status_code >= 400 or not body.get("access_token"):
            raise SyncError("auth")
        tok = (body["access_token"], body.get("api_domain") or f"https://www.zohoapis.{self.cfg.get('dc') or 'com'}",
               time.time() + int(body.get("expires_in") or 3600))
        _ZOHO_TOKENS[self.owner] = tok
        return tok

    def _req(self, method, path, body=None, params=None, headers=None):
        token, domain, _ = self._token()
        r = self.http.request(method, domain + path, params=params, json=body,
                              headers={"Authorization": f"Zoho-oauthtoken {token}", **(headers or {})})
        if r.status_code == 304:
            return {}
        if r.status_code == 401:
            _ZOHO_TOKENS.pop(self.owner, None)
            raise SyncError("auth")
        if r.status_code == 429:
            raise SyncError("rate")
        if r.status_code == 204:
            return {}
        if r.status_code >= 400:
            raise SyncError(f"zoho {r.status_code}: {r.text[:200]}")
        return r.json() if r.content else {}

    def test(self):
        self._req("GET", "/crm/v2/users", params={"type": "CurrentUser"})

    def _find(self, key, value):
        if not value:
            return None
        rows = self._req("GET", "/crm/v2/Contacts/search", params={key: value}).get("data") or []
        return str(rows[0]["id"]) if rows else None

    def upsert(self, ct, ext_id):
        first, last = _split(ct.get("name"))
        rec = {k: v for k, v in {"First_Name": first, "Last_Name": last or first or ct.get("phone") or "WhatsApp",
                                 "Phone": ct.get("phone"), "Email": ct.get("email"), "Lead_Source": "WhatsApp"}.items() if v}
        ext_id = ext_id or self._find("email", ct.get("email")) or self._find("phone", ct.get("phone"))
        if ext_id:
            self._req("PUT", "/crm/v2/Contacts", {"data": [dict(rec, id=ext_id)]})
            return ext_id
        res = self._req("POST", "/crm/v2/Contacts", {"data": [rec]})
        row = (res.get("data") or [{}])[0]
        if row.get("status") != "success":
            raise SyncError(f"zoho create: {row.get('message') or row}"[:200])
        return str(row["details"]["id"])

    def changed(self, since_ms):
        """جهات عُدّلت في Zoho بعد المؤشّر (If-Modified-Since بالثانية، ثم تصفية دقيقة بالمللي)."""
        since = datetime.fromtimestamp(since_ms / 1000, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")
        res = self._req("GET", "/crm/v2/Contacts", params={
            "fields": "First_Name,Last_Name,Phone,Email,Modified_Time", "sort_by": "Modified_Time", "sort_order": "asc",
            "per_page": 100}, headers={"If-Modified-Since": since})
        out = []
        for r in res.get("data") or []:
            ts = _ms(r.get("Modified_Time"))
            if ts > since_ms:
                out.append({"ext": str(r["id"]), "name": " ".join(x for x in (r.get("First_Name"), r.get("Last_Name")) if x),
                            "phone": r.get("Phone"), "email": r.get("Email"), "ts": ts})
        return out

    def note(self, ext_id, text, ts):
        self._req("POST", "/crm/v2/Notes", {"data": [{"Note_Title": "BotYalla", "Note_Content": text,
                                                      "Parent_Id": ext_id, "se_module": "Contacts"}]})


def client_for(cfg, http, owner_id):
    return HubSpot(cfg, http) if cfg["provider"] == "hubspot" else Zoho(cfg, http, owner_id)


# ─────────────────────────── الدورة ───────────────────────────
def _lead_text(lead):
    try:
        data = json.loads(lead.get("data_json") or "{}")
    except ValueError:
        data = {}
    lines = [f"{k}: {v}" for k, v in data.items() if not str(k).startswith("_")][:40]
    return "📝 BotYalla — " + (lead.get("bot_name") or "") + "\n" + "\n".join(lines)


def sync_owner(owner_id, http=None, now=None):
    """دفعة واحدة لحساب ⇒ (جهات, ملاحظات). خطأ الـ CRM يُسجَّل في الإعداد ويوقف الدفعة (المؤشّر لا يتقدّم)."""
    cfg = config(owner_id)
    if not cfg or not cfg.get("enabled"):
        return 0, 0
    raw = _raw(owner_id)
    own = http is None
    http = http or httpx.Client(timeout=TIMEOUT)
    done = notes = 0
    try:
        crm = client_for(cfg, http, owner_id)
        if cfg.get("two_way"):
            _pull(owner_id, crm, cfg["provider"], raw)            # قبل الدفع: تعديل الـ CRM الأحدث لا يُطمس
        cursor = raw.get("cursor") or 0
        for ct in db.contacts_changed_since(owner_id, cursor, BATCH):
            h = fingerprint(ct.get("name"), ct.get("phone"), ct.get("email"))
            if (ct.get("phone") or ct.get("email")) and db.crm_link_hash(owner_id, ct["id"], cfg["provider"]) != h:
                ext = crm.upsert(ct, db.crm_link(owner_id, ct["id"], cfg["provider"]))
                db.set_crm_link(owner_id, ct["id"], cfg["provider"], ext, h)
                done += 1
            cursor = [ct["updated_at"], ct["id"]]
            _update_state(owner_id, cursor=cursor, synced=(raw.get("synced") or 0) + done)
        if cfg.get("notes", True) is not False:
            for lead in db.leads_after(owner_id, raw.get("lead_cursor") or 0, BATCH):
                cid = db.lead_contact(lead)
                ext = db.crm_link(owner_id, cid, cfg["provider"]) if cid else None
                if cid and not ext:
                    ct = db.get_contact(owner_id, cid)
                    if ct and (ct.get("phone") or ct.get("email")):
                        ext = crm.upsert(ct, None)
                        db.set_crm_link(owner_id, cid, cfg["provider"], ext)
                if ext:
                    crm.note(ext, _lead_text(lead), lead["created_at"])
                    notes += 1
                _update_state(owner_id, lead_cursor=lead["id"])
        _update_state(owner_id, last_at=int(now or time.time()), last_error="")
    except SyncError as e:
        _update_state(owner_id, last_error=str(e)[:200], last_at=int(now or time.time()))
        log.info("crm sync owner=%s stopped: %s", owner_id, e)
    except httpx.HTTPError as e:
        _update_state(owner_id, last_error="network")
        log.info("crm sync owner=%s network: %s", owner_id, e)
    finally:
        if own:
            http.close()
    return done, notes


def _pull(owner_id, crm, provider, raw):
    """تعديلات الـ CRM ⇒ جهات BotYalla. جهة مربوطة بصمتها كما هي = لا شيء تغيّر (صدى دفعنا نحن)؛
    غير المربوطة تُطابَق بالهاتف ثم البريد، وإلا تُنشأ. المؤشّر يتقدّم بعد كل جهة."""
    import crm as CRM
    cursor = int(raw.get("pull_cursor") or int(time.time() * 1000))
    pulled = raw.get("pulled") or 0
    for rec in crm.changed(cursor):
        phone = CRM.norm_phone(rec.get("phone"), "+966") if rec.get("phone") else None
        email = CRM.norm_email(rec.get("email")) if rec.get("email") else None
        h = fingerprint(rec.get("name"), phone, email)
        cid, last = db.crm_contact_by_ext(owner_id, provider, rec["ext"])
        if not (cid and last == h) and (phone or email):
            cid = cid or (phone and db.contact_by_phone(owner_id, phone)) or (email and db.contact_by_email(owner_id, email))
            if cid:
                db.update_contact_from_crm(owner_id, cid, rec.get("name"), phone, email)
            else:
                cid = db.create_contact_from_crm(owner_id, rec.get("name"), phone, email)
            if cid:
                ct = db.get_contact(owner_id, cid) or {}
                # بصمة الجهة كما صارت عندنا (قد يبقى هاتفها القديم لو المأخوذ لجهة أخرى) — دفعنا التالي لا يعيدها
                db.set_crm_link(owner_id, cid, provider, rec["ext"], fingerprint(ct.get("name"), ct.get("phone"), ct.get("email")))
                pulled += 1
        cursor = max(cursor, rec["ts"])
        _update_state(owner_id, pull_cursor=cursor, pulled=pulled)


def tick(http=None):
    for owner_id in db.owners_with_setting(CFG_KEY):
        if not HOOKS["gate"](owner_id):
            continue
        try:
            sync_owner(owner_id, http=http)
        except Exception:
            log.exception("crm sync owner=%s", owner_id)


def test(owner_id, http=None):
    cfg = config(owner_id)
    if not cfg:
        raise SyncError("not_configured")
    own = http is None
    http = http or httpx.Client(timeout=TIMEOUT)
    try:
        client_for(cfg, http, owner_id).test()
    except httpx.HTTPError:
        raise SyncError("network")
    finally:
        if own:
            http.close()
