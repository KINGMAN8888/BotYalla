"""تكامل كامل: POST موقّع على /wh/whatsapp → المحرك → «Meta» وهمية.
يثبت: التوقيع، عدم التكرار، حفظ lead، احترام حدّ الباقة."""
import hashlib, hmac, json, os, sys, tempfile, time

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)
os.chdir(_ROOT)
os.environ["BOTYALLA_DB"] = os.path.join(tempfile.mkdtemp(prefix="wa-e2e-"), "t.db")
os.environ.setdefault("SECRET_KEY", "e2e")

import database as db
import bot_manager
import app as web
from channels.whatsapp import WhatsAppChannel

SECRET = "app-secret"
SENT = []

# «Meta» وهمية: نعترض طبقة النقل وحدها، فيبقى كل ما فوقها حقيقياً
async def fake_post(self, payload):
    if self.on_send is not None and (await self.on_send()) is False:
        return None
    SENT.append(payload)
    return {"messages": [{"id": "out"}]}
WhatsAppChannel._post = fake_post

fails = []
def check(label, cond, extra=""):
    print(("PASS " if cond else "FAIL ") + label + ("" if cond else f"  <- {extra}"))
    if not cond: fails.append(label)

db.init_db()
db.set_platform("wa_app_secret", SECRET)
db.set_platform("wa_verify_token", "vt")
with db.get_conn() as c:
    c.execute("INSERT INTO users(id,username,pw_hash,role,created_at)"
              " VALUES(7,'shop','x','user',0)")
db.activate_subscription(7, "pro", days=30)
bot_id = db.create_bot(7, "WA Shop", "wa:5550001", "flow",
                       {"business_name": "متجري", "owner_chat_id": ""}, channel="whatsapp")
db.set_bot_active(bot_id, True)

bot_manager.manager.start()
time.sleep(0.5)
client = web.app.test_client()

def post(msgs, phone="5550001"):
    body = json.dumps({"entry": [{"changes": [{"value": {
        "metadata": {"phone_number_id": phone},
        "contacts": [{"profile": {"name": "أحمد"}}],
        "messages": msgs}}]}]}).encode()
    sig = "sha256=" + hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()
    r = client.post("/wh/whatsapp", data=body,
                    headers={"X-Hub-Signature-256": sig, "Content-Type": "application/json"})
    time.sleep(0.35)          # المعالجة غير محجوبة عمداً
    return r

def txt(mid, body):
    return {"id": mid, "from": "201009998877", "type": "text", "text": {"body": body}}

# 1) بدء المحادثة
r = post([txt("m1", "مرحبا")])
check("webhook returns 200", r.status_code == 200, r.status_code)
check("bot replied to the greeting", len(SENT) >= 1, len(SENT))
check("state created", db.get_chat_state(bot_id, "wa:201009998877") is not None)

# 2) إعادة إرسال نفس الرسالة (Meta تُعيد عند أي تأخّر)
before = len(SENT)
post([txt("m1", "مرحبا")])
check("duplicate message ignored", len(SENT) == before, f"{before} -> {len(SENT)}")

# 3) إكمال الفلو
post([txt("m2", "أحمد")])
post([txt("m3", "01000000000")])
post([txt("m4", "عايز أستفسر")])
with db.get_conn() as c:
    lead = c.execute("SELECT data_json FROM leads WHERE bot_id=?", (bot_id,)).fetchone()
check("lead saved end-to-end", lead is not None and "أحمد" in lead["data_json"],
      lead["data_json"] if lead else None)
check("state cleared after finish", db.get_chat_state(bot_id, "wa:201009998877") is None)

# 4) العدّاد
u = db.owner_usage(7)
check("outbound counted", u["sent"] == len(SENT), f'{u["sent"]} vs {len(SENT)}')
check("inbound counted", u["received"] == 4, u["received"])

# 5) صورة لا تتقدّم بالفلو
post([txt("m5", "مرحبا")])
step = db.get_chat_state(bot_id, "wa:201009998877")["step"]
post([{"id": "m6", "from": "201009998877", "type": "image", "image": {"id": "i"}}])
st = db.get_chat_state(bot_id, "wa:201009998877")
check("media keeps the same step", st and st["step"] == step, st)

# 6) رقم غير معروف يُتجاهل بلا انهيار
before = len(SENT)
r = post([txt("m7", "مرحبا")], phone="9999999")
check("unknown phone_id ignored, still 200", r.status_code == 200 and len(SENT) == before)

# 7) الحدّ الشهري
with db.get_conn() as c:
    c.execute("UPDATE usage_msgs SET sent=? WHERE bot_id=?", (1000, bot_id))
before = len(SENT)
post([txt("m8", "مرحبا")])
check("sending stops at the plan limit", len(SENT) == before, f"{before} -> {len(SENT)}")

print("\n" + ("ALL PASS" if not fails else f"{len(fails)} FAILED: {fails}"))


def test_wa_integration():
    """يجعل الملف صالحاً لـ pytest أيضاً. `sys.exit` على مستوى الوحدة كان
    يُسقط pytest بـ INTERNALERROR فلا يعمل أي اختبار في المجلد كله."""
    assert not fails, fails


if __name__ == "__main__":
    sys.exit(1 if fails else 0)
