"""ودجت الموقع ومحادثة الويب — المرحلة 7: الإعداد والتحقق · السكربت والإعداد العام وCORS · هوية الزائر
الموقَّعة · الرسالة تمرّ بالفلو والرد يُستطلع · الموظف يرد من الصندوق المشترك · تقييد النطاق والباقة ·
روابط الوسائط الموقَّعة · زر واتساب.

    python tests/test_widget.py
"""
import asyncio, json, os, secrets, sys, tempfile, time, unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_TMPDIR = tempfile.mkdtemp(prefix="botyalla-wg-")
os.environ["BOTYALLA_DB"] = os.path.join(_TMPDIR, "test.db")   # قبل استيراد database
os.environ["BOTYALLA_UPLOADS"] = _TMPDIR
os.environ["BOTYALLA_LOGS"] = os.path.join(_TMPDIR, "logs")
os.environ["ADMIN_USER"] = "admin"
os.environ["ADMIN_PASS"] = "Wg#" + secrets.token_hex(6)

import auth                                # noqa: E402
import database as db                      # noqa: E402
import app as web                          # noqa: E402

PW = "Str0ng!Pass" + secrets.token_hex(3)
db.init_db(); web.seed_platform_defaults(); web.contact_defaults(); web.seed_default_admin()
web.app.config["TESTING"] = True


def user(name, plan="enterprise"):
    uid, err = db.create_account(name + secrets.token_hex(3), auth.hash_password(PW), f"{name}{secrets.token_hex(3)}@example.test",
                                 None, 30, "person", verify_required=False)
    assert not err, err
    db.mark_email_verified(uid)
    if plan:
        db.activate_subscription(uid, plan, 30)
    return uid


def client(user_id):
    c = web.app.test_client()
    with c.session_transaction() as s:
        u = db.get_user(user_id)
        s.update(_csrf="tk", uid=user_id, uname=u["username"], role=u["role"], pwv=web._pw_stamp(u["pw_hash"]))
    return c


def post(c, url, body=None, **kw):
    return c.post(url, data=json.dumps(body or {}), content_type="application/json", headers={"X-CSRF-Token": "tk"}, **kw)


class Acct:
    def __init__(self, plan="enterprise"):
        self.owner = user("own", plan)
        self.c = client(self.owner)
        self.wa = db.create_bot(self.owner, "WA", f"wa:{secrets.randbelow(10**12)}", "flow", {"bot_username": "966500000777"}, "whatsapp")
        fid = post(self.c, f"/api/bot/{self.wa}/flows", {"name": "ترحيب"}).get_json()["flow"]["id"]
        post(self.c, f"/api/bot/{self.wa}/flows/{fid}/save", {"draft": {"start": "b", "nodes": {
            "b": {"type": "buttons", "text": "أهلاً بك في موقعنا 👋 كيف نساعدك؟", "var": "c",
                  "options": [{"label": "الأسعار", "next": "p"}, {"label": "موظف", "next": "h"}]},
            "p": {"type": "text", "text": "الأسعار تبدأ من 250 ريال"}, "h": {"type": "handoff", "text": "نحوّلك لفريقنا"}}}})
        post(self.c, f"/api/bot/{self.wa}/flows/{fid}/publish"); post(self.c, f"/api/bot/{self.wa}/flows/{fid}/toggle", {"active": True})

    def widget(self, **settings):
        s = dict({"mode": "both", "color": "#123456", "title": "فنادق الفرسان", "welcome": "مرحباً!", "icebreakers": ["الأسعار"]}, **settings)
        r = post(self.c, "/api/growth/widgets/save", {"name": "الموقع", "bot": self.wa, "wa_bot": self.wa, "settings": s}).get_json()
        assert r["ok"], r
        return r["widgets"][0]


def visitor(c, key):
    return post(c, f"/wg/{key}/hello").get_json()


class WidgetTests(unittest.TestCase):
    def test_validation_and_embed(self):
        a = Acct()
        r = post(a.c, "/api/growth/widgets/save", {"name": "x", "bot": a.wa, "wa_bot": a.wa, "settings": {"color": "red"}}).get_json()
        self.assertEqual(r["error"], "color")
        r = post(a.c, "/api/growth/widgets/save", {"name": "x", "settings": {"mode": "chat"}}).get_json()
        self.assertEqual(r["error"], "bot")
        tg = db.create_bot(a.owner, "TG", "tg-x", "flow", {}, "telegram")
        r = post(a.c, "/api/growth/widgets/save", {"name": "x", "bot": tg, "wa_bot": tg, "settings": {"mode": "both"}}).get_json()
        self.assertEqual(r["error"], "wa_bot", "زر واتساب يحتاج قناة واتساب")
        w = a.widget()
        self.assertRegex(w["key"], r"^[a-f0-9]{16}$")
        self.assertIn(f'/wg/{w["key"]}.js" async></script>', w["embed"])
        m = user("mem", None); db.join_team(a.owner, m, "member")
        self.assertEqual(post(client(m), "/api/growth/widgets/save", {"name": "y"}).status_code, 403)

    def test_script_and_public_config(self):
        a = Acct()
        w = a.widget(domains=[], wa_text="أريد الحجز")
        pub = web.app.test_client()
        r = pub.get(f"/wg/{w['key']}.js")
        self.assertEqual((r.status_code, r.mimetype, r.headers["Access-Control-Allow-Origin"]), (200, "application/javascript", "*"))
        js = r.get_data(as_text=True)
        self.assertIn(json.dumps(w["key"]), js)
        self.assertNotIn("__KEY__", js)
        cfg = pub.get(f"/wg/{w['key']}/config").get_json()
        self.assertEqual((cfg["mode"], cfg["wa"], cfg["settings"]["title"]), ("both", True, "فنادق الفرسان"))
        self.assertNotIn("domains", cfg["settings"])
        self.assertEqual(pub.get("/wg/0000000000000000.js").status_code, 404)
        r = pub.get(f"/wg/{w['key']}/wa")
        self.assertEqual(r.headers["Location"], "https://wa.me/966500000777?text=" + __import__("urllib.parse").parse.quote("أريد الحجز"))
        self.assertEqual(db.get_widget(key=w["key"])["wa_clicks"], 1)

    def test_signed_visitor_identity(self):
        a = Acct()
        w = a.widget()
        pub = web.app.test_client()
        v = visitor(pub, w["key"])
        self.assertRegex(v["vid"], r"^8\d{15}$")
        again = post(pub, f"/wg/{w['key']}/hello", {"vid": v["vid"], "sig": v["sig"]}).get_json()
        self.assertEqual(again["vid"], v["vid"], "الهوية الصحيحة تبقى")
        forged = post(pub, f"/wg/{w['key']}/hello", {"vid": "8" + "1" * 15, "sig": "x"}).get_json()
        self.assertNotEqual(forged["vid"], "8" + "1" * 15, "هوية بلا توقيع صحيح = زائر جديد")
        self.assertEqual(post(pub, f"/wg/{w['key']}/send", {"vid": v["vid"], "sig": "0" * 32, "text": "x"}).status_code, 403)
        self.assertEqual(pub.get(f"/wg/{w['key']}/poll?vid={v['vid']}&sig=bad").status_code, 403)
        other = a.widget()
        self.assertEqual(post(pub, f"/wg/{other['key']}/send", {"vid": v["vid"], "sig": v["sig"], "text": "x"}).status_code, 403,
                         "توقيع ودجت لا يصلح لآخر")

    def test_visitor_chats_with_the_bot_and_an_agent_replies_from_the_inbox(self):
        a = Acct()
        w = a.widget()
        pub = web.app.test_client()
        v = visitor(pub, w["key"])
        self.assertTrue(post(pub, f"/wg/{w['key']}/send", dict(v, text="السلام عليكم")).get_json()["ok"])
        items = pub.get(f"/wg/{w['key']}/poll?vid={v['vid']}&sig={v['sig']}").get_json()["items"]
        self.assertEqual(items[0], dict(items[0], me=1, text="السلام عليكم"))
        self.assertEqual((items[1]["text"], items[1]["buttons"]), ("أهلاً بك في موقعنا 👋 كيف نساعدك؟", ["الأسعار", "موظف"]))
        post(pub, f"/wg/{w['key']}/send", dict(v, text="الأسعار"))
        items = pub.get(f"/wg/{w['key']}/poll?vid={v['vid']}&sig={v['sig']}&after={items[-1]['id']}").get_json()["items"]
        self.assertEqual(items[-1]["text"], "الأسعار تبدأ من 250 ريال")
        self.assertEqual(db.get_widget(key=w["key"])["chats"], 1)
        peer = f"wb:{v['vid']}"
        row = next(x for x in a.c.get("/api/inbox?view=open").get_json()["rows"] if x["peer"] == peer)
        self.assertEqual(row["bot_id"], a.wa)
        # الموظف يرد من الصندوق المشترك ⇒ يصل للزائر (لا نافذة 24 ساعة لمحادثة الويب)
        orig = web.manager.send_to_peer
        web.manager.send_to_peer = lambda bot_id, p, text=None, asset=None: asyncio.run(web.manager._send_to_peer(db.get_bot(bot_id), p, text, asset))
        try:
            r = post(a.c, "/api/inbox/send", {"bot": a.wa, "peer": peer, "text": "أهلاً، معك سارة من الحجوزات"}).get_json()
        finally:
            web.manager.send_to_peer = orig
        self.assertTrue(r["ok"], r)
        items = pub.get(f"/wg/{w['key']}/poll?vid={v['vid']}&sig={v['sig']}").get_json()["items"]
        self.assertEqual(items[-1]["text"], "أهلاً، معك سارة من الحجوزات")

    def test_domain_lock_and_plan(self):
        a = Acct()
        w = a.widget(domains=["alforsan.sa"])
        pub = web.app.test_client()
        self.assertEqual(pub.post(f"/wg/{w['key']}/hello", headers={"Origin": "https://evil.test"}).status_code, 403)
        self.assertEqual(pub.post(f"/wg/{w['key']}/hello", headers={"Origin": "https://www.alforsan.sa"}).status_code, 200)
        db.activate_subscription(a.owner, "merchant", 30)
        self.assertEqual(pub.get(f"/wg/{w['key']}.js").status_code, 404, "الباقة بلا الميزة ⇒ الودجت يتوقّف")

    def test_signed_media_links(self):
        import asset_store
        from channels.web import WebChannel
        a = Acct()
        aid = asset_store.save(a.owner, b"\xff\xd8\xff" + b"0" * 100, "room.jpg")["id"]
        with web.app.test_request_context():
            ch = WebChannel(a.wa)
            asyncio.run(ch.send_media("wb:8000000000000001", db.get_asset(aid), a.wa, caption="الغرفة"))
        item = db.web_pull(a.wa, "wb:8000000000000001")[-1]
        url = item["media"]["url"]
        pub = web.app.test_client()
        path = url.split("://", 1)[1].split("/", 1)[1]
        self.assertEqual(pub.get("/" + path).status_code, 200)
        self.assertEqual(pub.get("/" + path.replace("s=", "s=0")).status_code, 403, "توقيع معدَّل")
        exp = int(time.time()) - 5
        self.assertEqual(pub.get(f"/wg/asset/{aid}?e={exp}&s={web._wg_asset_sig(aid, exp)}").status_code, 403, "منتهي")


if __name__ == "__main__":
    unittest.main(verbosity=2)
