"""إعداد مراقبة BotYalla على UptimeRobot بأمر واحد — تشغّله أنت بمفتاحك.

    UPTIMEROBOT_API_KEY=... python tools/uptimerobot_setup.py [https://botyalla.com]

المفتاح من UptimeRobot ← Integrations & API ← Main API key. يُقرأ من متغيّر البيئة فقط
ولا يُكتب في أي ملف. آمن للتكرار: أي مراقب موجود لنفس الرابط يُتخطّى.

ما يُنشأ (كل 5 دقائق — أقل فاصل في الخطة المجانية، وتنبيه لكل جهات الاتصال المسجّلة):
  1) /healthz — يفحص أن قاعدة البيانات تستجيب لا أن العملية حيّة فقط، ويرجّع 503 لو لا.
  2) الصفحة الرئيسية — ما يراه الزائر فعلاً (nginx + الشهادة + التطبيق).
الشرح الكامل وخطوات الواجهة اليدوية: docs/MONITORING.md
"""
import json
import os
import sys
import urllib.parse
import urllib.request

API = "https://api.uptimerobot.com/v2/"
INTERVAL = 300


def call(method, **params):
    data = urllib.parse.urlencode({"api_key": os.environ["UPTIMEROBOT_API_KEY"].strip(),
                                   "format": "json", **params}).encode()
    req = urllib.request.Request(API + method, data=data, method="POST",
                                 headers={"Content-Type": "application/x-www-form-urlencoded",
                                          "Cache-Control": "no-cache",
                                          "User-Agent": "BotYalla/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            out = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise SystemExit(f"HTTP 403 Error on {method}: {e.reason}\nResponse Body: {body}")
    
    if out.get("stat") != "ok":
        raise SystemExit(f"UptimeRobot {method} failed: {out.get('error') or out}")
    return out


def main():
    if not os.environ.get("UPTIMEROBOT_API_KEY", "").strip():
        raise SystemExit("Set UPTIMEROBOT_API_KEY first "
                         "(UptimeRobot → Integrations & API → Main API key).")
    base = (sys.argv[1] if len(sys.argv) > 1 else "https://botyalla.com").rstrip("/")
    if not base.startswith("https://"):
        raise SystemExit("Use the public https:// address of the site.")

    contacts = call("getAlertContacts").get("alert_contacts", [])
    if not contacts:
        print("! No alert contacts yet — monitors will be created, but nobody is notified.\n"
              "  Add your email (and Telegram) under My Settings → Alert Contacts, then rerun.")
    alerts = "-".join(f"{c['id']}_0_0" for c in contacts)   # id_threshold_recurrence

    existing = {str(m.get("url", "")).rstrip("/") for m in call("getMonitors").get("monitors", [])}
    wanted = [("BotYalla · health (database)", f"{base}/healthz"),
              ("BotYalla · homepage", f"{base}/")]
    for name, url in wanted:
        if url.rstrip("/") in existing:
            print(f"= exists   {name}  {url}")
            continue
        params = {"friendly_name": name, "url": url, "type": 1, "interval": INTERVAL}
        if alerts:
            params["alert_contacts"] = alerts
        res = call("newMonitor", **params)
        print(f"+ created  {name}  {url}  (id {res.get('monitor', {}).get('id')})")
    print("Done. Status page: https://dashboard.uptimerobot.com/monitors")


if __name__ == "__main__":
    main()
