"""حملات البريد: أخبار وعروض وإشعارات خدمة للمشتركين — من لوحة الأدمن («رسائل البريد»).

نوعان لا يختلطان:
- **news** (أخبار وعروض): لمن وافق صراحةً فقط (`settings.email_news = '1'` — من التسجيل أو
  «حسابي»). في كل رسالة رابط إلغاء بضغطة + ترويسة `List-Unsubscribe` (RFC 8058) التي
  يشترطها Gmail وYahoo للرسائل الجماعية. بلا PUBLIC_URL لا رابط إلغاء ⇒ لا تُرسل أصلاً.
- **service** (إشعار خدمة): تغيير في الشروط أو صيانة أو أمر يخص الحساب — لكل من له إيميل.
  ليس للتسويق: سياسة الخصوصية تَعِد «لا رسائل تسويقية دون موافقتك».

الإرسال في خيط خلفي، رسالة كل `INTERVAL` ثانية، وبسقف يومي (`email_daily_cap`) لأن مزوّد
SMTP يحدّ الإرسال اليومي (Brevo المجاني 300) وتجاوزه يوقف حساب الإرسال كله — ومعه إيميلات
الاسترجاع والإيصالات. عند بلوغ السقف تنتظر الحملة لليوم التالي وتكمل وحدها.

كل مستلم يُسجَّل في `email_sends` بمفتاح (الحملة، المستخدم): الاستئناف بعد إيقاف أو إعادة
تشغيل لا يكرر رسالة لأحد، والرسائل التي فشلت تُعاد محاولتها عند الاستئناف.
"""
import datetime as _dt
import json, logging, threading, time

import database as db
import mailer

log = logging.getLogger("email_campaigns")

SYNC = False            # الاختبارات: الإرسال في نفس الخيط وبلا انتظار
INTERVAL = 1.0          # ثانية بين رسالتين — لا دفعات تثير فلاتر المزوّد
DEFAULT_CAP = 250       # تحت حدّ Brevo المجاني (300) بهامش لإيميلات التشغيل
FAIL_STREAK = 5         # فشل متتالٍ ⇒ SMTP معطّل: أوقف بدل حرق القائمة كلها فشلاً

_lock = threading.Lock()
_threads = {}           # cid -> Thread
_stop = set()


def daily_cap():
    try:
        v = int(db.get_platform("email_daily_cap", "") or DEFAULT_CAP)
    except (TypeError, ValueError):
        v = DEFAULT_CAP
    return max(1, min(v, 100000))


def running(cid):
    t = _threads.get(cid)
    return bool(t and t.is_alive())


def start(cid):
    """يبدأ (أو يستأنف) إرسال حملة حالتها sending. خيط واحد لكل حملة."""
    with _lock:
        if running(cid):
            return False
        _stop.discard(cid)
        if not SYNC:
            t = threading.Thread(target=_run, args=(cid,), daemon=True, name=f"mail-campaign-{cid}")
            _threads[cid] = t
            t.start()
            return True
    _run(cid)
    return True


def stop(cid):
    _stop.add(cid)
    db.set_email_campaign(cid, status="stopped", note=None)


def resume_pending():
    """عند الإقلاع: كل حملة كانت تُرسل تكمل من حيث توقفت (email_sends يمنع التكرار)."""
    for c in db.list_email_campaigns(status="sending"):
        log.info("resuming email campaign #%s", c["id"])
        start(c["id"])


def _run(cid):
    try:
        _send_all(cid)
    except Exception:
        log.exception("email campaign #%s crashed", cid)
        db.set_email_campaign(cid, status="stopped", note="error")
    finally:
        with _lock:
            _threads.pop(cid, None)


def _wait_for_quota(cid):
    """True لو يمكن الإرسال الآن. عند بلوغ السقف: تنتظر (فحص كل دقيقة) حتى يتجدد اليوم."""
    waited = False
    while db.email_sends_today() >= daily_cap():
        if not waited:
            db.set_email_campaign(cid, note="cap_wait")
            log.info("email campaign #%s waiting: daily cap %s reached", cid, daily_cap())
            waited = True
        if SYNC or cid in _stop:
            return False
        time.sleep(60)
    if waited:
        db.set_email_campaign(cid, note=None)
    return True


def _send_all(cid):
    camp = db.get_email_campaign(cid)
    if not camp or camp["status"] != "sending":
        return
    content = json.loads(camp["content"] or "{}")
    news = camp["kind"] == "news"
    done = db.email_done_ids(cid)
    todo = [r for r in db.email_audience(camp["audience"], camp["kind"]) if r["id"] not in done]
    db.set_email_campaign(cid, total=len(done) + len(todo))
    streak = 0
    for r in todo:
        if cid in _stop:
            return
        if not _wait_for_quota(cid):
            return
        if news and not db.email_news_on(r["id"]):
            db.record_email_send(cid, r["id"], "skipped")        # ألغى الاشتراك أثناء الحملة
            continue
        unsub = mailer.unsub_url(r["id"]) if news else None
        if news and not unsub:                                   # PUBLIC_URL أُزيلت — افشل مغلقاً
            db.set_email_campaign(cid, status="stopped", note="no_public_url")
            return
        subject, html, text = mailer.campaign_email(content, r["lang"], r["username"], camp["kind"],
                                                    unsub=unsub, campaign_id=cid)
        headers = {"X-BotYalla-Campaign": str(cid)}
        if unsub:
            headers["List-Unsubscribe"] = f"<{unsub}>"
            headers["List-Unsubscribe-Post"] = "List-Unsubscribe=One-Click"
        ok = mailer.send_mail(r["email"], subject, html, text, headers=headers)
        db.record_email_send(cid, r["id"], "sent" if ok else "failed")
        streak = 0 if ok else streak + 1
        if streak >= FAIL_STREAK:
            log.error("email campaign #%s stopped: %s failures in a row", cid, streak)
            db.set_email_campaign(cid, status="stopped", note="smtp_error")
            return
        if INTERVAL and not SYNC:
            time.sleep(INTERVAL)
    if cid not in _stop:
        db.set_email_campaign(cid, status="done", note=None, finished_at=int(time.time()))
        log.info("email campaign #%s done", cid)
