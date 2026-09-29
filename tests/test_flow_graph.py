"""باني الفلو المرئي — المرحلة 5: المحرك الخطّي لا يتأثّر · التشغيل البياني (أزرار · أسئلة بتحقق ·
شرط · وسم · حقل · تحويل) · المشغّلات والتبديل · الجلسات والتسرّب · النشر بتحقق كامل · الصلاحيات.

    python tests/test_flow_graph.py
"""
import asyncio, json, os, secrets, sys, tempfile, unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_TMPDIR = tempfile.mkdtemp(prefix="botyalla-fg-")
os.environ["BOTYALLA_DB"] = os.path.join(_TMPDIR, "test.db")   # قبل استيراد database
os.environ["BOTYALLA_UPLOADS"] = _TMPDIR
os.environ["BOTYALLA_LOGS"] = os.path.join(_TMPDIR, "logs")
os.environ["ADMIN_USER"] = "admin"
os.environ["ADMIN_PASS"] = "Fg#" + secrets.token_hex(6)

import auth                                # noqa: E402
import database as db                      # noqa: E402
import flow_engine as FE                   # noqa: E402
import flow_graph as FG                    # noqa: E402
import app as web                          # noqa: E402

PW = "Str0ng!Pass" + secrets.token_hex(3)


class Ch:
    """قناة وهمية تسجّل ما يُرسل."""
    phone_id = page_id = None

    def __init__(self):
        self.out = []

    async def send_text(self, peer, text):
        self.out.append(("text", text)); return True

    async def remove_keyboard(self, peer, text):
        self.out.append(("text", text)); return True

    async def send_buttons(self, peer, text, options):
        self.out.append(("buttons", text, list(options))); return True

    async def send_media(self, peer, asset, bot_id, caption=None, options=None):
        self.out.append(("media", asset["id"], caption)); return True

    async def send_image(self, peer, url, caption=None):
        self.out.append(("image", url)); return True

    async def fetch_media(self, media):
        return None, None


def _boot():
    db.init_db(); web.seed_platform_defaults(); web.contact_defaults(); web.seed_default_admin()
    web.app.config["TESTING"] = True
    FE.notify_owner = _fake_notify


NOTES = []


async def _fake_notify(bot_row, channel, text):
    NOTES.append(text)


def _user(name, plan="enterprise"):
    uid, err = db.create_account(name, auth.hash_password(PW), f"{name}@example.test", None, 30, "person",
                                 verify_required=False)
    assert not err, err
    db.mark_email_verified(uid)
    if plan:
        db.activate_subscription(uid, plan, 30)
    return uid


def _client(user_id):
    c = web.app.test_client()
    with c.session_transaction() as s:
        u = db.get_user(user_id)
        s.update(_csrf="tk", uid=user_id, uname=u["username"], role=u["role"], pwv=web._pw_stamp(u["pw_hash"]))
    return c


def post(c, url, body=None):
    return c.post(url, data=json.dumps(body or {}), content_type="application/json", headers={"X-CSRF-Token": "tk"})


def say(bot_id, peer, text, kind="text"):
    ch = Ch()
    asyncio.run(FE.handle_message(db.get_bot(bot_id), ch, {"peer": peer, "kind": kind, "text": text, "name": "Ali"}))
    return ch.out


_boot()
OWNER = _user("fg" + secrets.token_hex(3))
C = _client(OWNER)
db.save_field(OWNER, "contact", {"label": "Budget", "key": "budget", "type": "number", "options": [],
                                 "active": 1, "required": 0})

BOOKING = {"start": "hi", "nodes": {
    "hi": {"type": "text", "text": "أهلاً {{contact.name}} 👋", "next": "menu"},
    "menu": {"type": "buttons", "text": "اختر:", "var": "choice",
             "options": [{"label": "حجز", "next": "guests"}, {"label": "موظف", "next": "human"}]},
    "guests": {"type": "ask", "text": "كم شخص؟", "var": "guests", "validate": "number", "next": "cond"},
    "cond": {"type": "condition", "var": "guests", "op": "gt", "value": "4", "yes": "vip", "no": "save"},
    "vip": {"type": "tag", "tags": ["مجموعات"], "next": "save"},
    "save": {"type": "set_field", "field": "budget", "value": "{{guests}}", "next": "bye"},
    "bye": {"type": "end", "text": "تم ✅ {{choice}} لـ {{guests}}"},
    "human": {"type": "handoff", "text": "سأحوّلك لفريقنا", "reason": "طلب موظف"},
}}


def new_bot(owner=OWNER):
    return db.create_bot(owner, "WA", f"wa:{secrets.randbelow(10**12)}", "flow", {}, "whatsapp")


def make_flow(bot, draft, trigger=None, name="حجز", active=True):
    r = post(C, f"/api/bot/{bot}/flows", {"name": name, "trigger": trigger or {"type": "any"}}).get_json()
    fid = r["flow"]["id"]
    assert post(C, f"/api/bot/{bot}/flows/{fid}/save", {"draft": draft}).get_json()["ok"]
    pub = post(C, f"/api/bot/{bot}/flows/{fid}/publish").get_json()
    assert pub["ok"], pub
    if active:
        assert post(C, f"/api/bot/{bot}/flows/{fid}/toggle", {"active": True}).get_json()["ok"]
    return fid


class LegacyUntouchedTests(unittest.TestCase):
    def test_a_bot_without_visual_flows_runs_the_linear_engine(self):
        bot = new_bot()
        out = say(bot, "wa:966500000001", "مرحبا", "start")
        self.assertIn(("text", FE.DEFAULT_CS_FLOW["steps"][0]["prompt"]), out)
        self.assertEqual(db.get_chat_state(bot, "wa:966500000001")["step"], 0)

    def test_a_linear_conversation_finishes_linear_after_publishing(self):
        bot = new_bot()
        say(bot, "wa:966500000002", "مرحبا", "start")                  # بدأ على الخطّي
        make_flow(bot, BOOKING)
        out = say(bot, "wa:966500000002", "Ali")
        self.assertIn(("text", FE.DEFAULT_CS_FLOW["steps"][1]["prompt"]), out)


class RunTests(unittest.TestCase):
    def setUp(self):
        self.bot = new_bot()
        self.fid = make_flow(self.bot, BOOKING)
        self.peer = f"wa:9665{secrets.randbelow(10**8):08d}"

    def test_full_path_with_validation_condition_tag_and_field(self):
        out = say(self.bot, self.peer, "السلام عليكم")
        self.assertEqual(out[0], ("text", "أهلاً Ali 👋"))
        self.assertEqual(out[1], ("buttons", "اختر:", ["حجز", "موظف"]))
        self.assertEqual(say(self.bot, self.peer, "1")[0], ("text", "كم شخص؟"), "رقم القائمة يختار الخيار")
        self.assertIn("رقم", say(self.bot, self.peer, "كتير")[0][1])     # تحقق النوع
        out = say(self.bot, self.peer, "٦")                              # أرقام عربية
        self.assertEqual(out[-1], ("text", "تم ✅ حجز لـ 6"))
        cid = db.contact_id_for_peer(self.bot, self.peer)
        c = db.get_contact_by_id(cid)
        self.assertEqual(c["fields"]["budget"], 6)
        self.assertEqual([t["name"] for t in db.list_tags(OWNER) if t["id"] in c["tags"]], ["مجموعات"])
        self.assertIsNone(db.get_chat_state(self.bot, self.peer), "الفلو انتهى")
        st = db.flow_stats(self.bot, self.fid)
        self.assertEqual((st["sessions"], st["completed"]), (1, 1))
        self.assertEqual(st["visits"]["guests"], 1)
        leads = db.list_leads(self.bot, limit=None)
        self.assertEqual(leads[0]["data"], {"choice": "حجز", "guests": "6"})

    def test_wrong_button_reasks_and_state_survives(self):
        say(self.bot, self.peer, "hi")
        out = say(self.bot, self.peer, "شيء آخر")
        self.assertEqual(out[0][0], "buttons")
        self.assertEqual(db.get_chat_state(self.bot, self.peer)["step"], FG.GRAPH_STEP)

    def test_handoff_gives_the_chat_to_the_team(self):
        say(self.bot, self.peer, "hi")
        say(self.bot, self.peer, "موظف")
        self.assertEqual(db.get_conversation(self.bot, self.peer)["mode"], "human")
        self.assertEqual(db.flow_stats(self.bot, self.fid)["handoff"], 1)

    def test_keyword_flow_switch_marks_the_first_session_dropped(self):
        fid2 = make_flow(self.bot, {"start": "a", "nodes": {"a": {"type": "text", "text": "أسعار العمرة…"}}},
                         trigger={"type": "keywords", "keywords": ["أسعار"]}, name="أسعار")
        say(self.bot, self.peer, "hi")                                  # ينتظر عند الأزرار
        out = say(self.bot, self.peer, "عايز الاسعار")                   # كلمة مشغّل (بلا همزة)
        self.assertEqual(out[0], ("text", "أسعار العمرة…"))
        st = db.flow_stats(self.bot, self.fid)
        self.assertEqual((st["dropped"], st["drops"]), (1, {"menu": 1}), "خريطة التسرّب تعرف أين توقّف")
        self.assertEqual(db.flow_stats(self.bot, fid2)["completed"], 1)

    def test_loop_guard(self):
        bot = new_bot()
        make_flow(bot, {"start": "a", "nodes": {"a": {"type": "set_var", "var": "x", "value": "1", "next": "b"},
                                                "b": {"type": "set_var", "var": "y", "value": "2", "next": "a"}}})
        say(bot, "wa:966511111111", "hi")                               # لا يعلق
        self.assertIsNone(db.get_chat_state(bot, "wa:966511111111"))


class PublishTests(unittest.TestCase):
    def setUp(self):
        self.bot = new_bot()
        self.fid = post(C, f"/api/bot/{self.bot}/flows", {"name": "x"}).get_json()["flow"]["id"]

    def publish(self, draft):
        post(C, f"/api/bot/{self.bot}/flows/{self.fid}/save", {"draft": draft})
        return post(C, f"/api/bot/{self.bot}/flows/{self.fid}/publish").get_json()

    def test_invalid_graphs_never_publish(self):
        self.assertEqual(self.publish({"start": "a", "nodes": {"a": {"type": "ask", "text": "", "var": "n"}}})["error"], "node:a:text")
        self.assertEqual(self.publish({"start": "a", "nodes": {"a": {"type": "text", "text": "x", "next": "ghost"}}})["error"], "node:a:next")
        self.assertEqual(self.publish({"start": "a", "nodes": {"a": {"type": "evil_exec", "text": "x"}}})["error"], "node:a:type")
        self.assertEqual(self.publish({"start": "a", "nodes": {"a": {"type": "jump", "flow": self.fid}}})["error"], "node:a:flow")
        self.assertEqual(self.publish({"start": "z", "nodes": {"a": {"type": "text", "text": "x"}}})["error"], "flow:start")
        other = _user("ot" + secrets.token_hex(3))
        foreign = db.add_asset(other, "image", "image/jpeg", 10, "x.jpg")
        self.assertEqual(self.publish({"start": "a", "nodes": {"a": {"type": "media", "asset": foreign}}})["error"], "node:a:asset")
        self.assertEqual(self.publish({"start": "a", "nodes": {"a": {"type": "set_field", "field": "pw_hash", "value": "x"}}})["error"], "node:a:field")

    def test_one_catch_all_flow_per_bot(self):
        make_flow(self.bot, {"start": "a", "nodes": {"a": {"type": "text", "text": "A"}}}, name="A")
        self.publish({"start": "a", "nodes": {"a": {"type": "text", "text": "B"}}})
        r = post(C, f"/api/bot/{self.bot}/flows/{self.fid}/toggle", {"active": True}).get_json()
        self.assertEqual((r["error"], r["other"]), ("trigger_taken", "A"))

    def test_other_accounts_and_members_are_refused(self):
        other = _user("oo" + secrets.token_hex(3))
        self.assertEqual(post(_client(other), f"/api/bot/{self.bot}/flows/{self.fid}/publish").status_code, 404)
        m = _user("mm" + secrets.token_hex(3), plan=None)
        self.assertEqual(db.join_team(OWNER, m, "member"), "")
        self.assertEqual(post(_client(m), f"/api/bot/{self.bot}/flows/{self.fid}/publish").status_code, 403)
        self.assertEqual(_client(m).get(f"/api/bot/{self.bot}/flows/{self.fid}").status_code, 200, "الموظف يرى")


class WaCh(Ch):
    """قناة واتساب وهمية: قالب يُقبل أو يُرفض، ودبّوس موقع."""
    phone_id = "1"

    def __init__(self, accept=True):
        super().__init__(); self.accept = accept

    async def send_template(self, peer, name, lang="ar", components=None):
        self.out.append(("template", name, components))
        return {"messages": [{"id": "wamid.t1"}]} if self.accept else None

    async def send_location(self, peer, lat, lng, name="", address=""):
        self.out.append(("location", lat, lng, name)); return {"messages": [{"id": "wamid.l"}]}


def say_on(ch, bot_id, peer, text, kind="text"):
    asyncio.run(FE.handle_message(db.get_bot(bot_id), ch, {"peer": peer, "kind": kind, "text": text, "name": "Ali"}))
    return ch.out


def peer():
    return f"wa:9665{secrets.randbelow(10**8):08d}"


class IntegrationCardTests(unittest.TestCase):
    def test_location_pin_and_text_fallback(self):
        bot = new_bot()
        make_flow(bot, {"start": "l", "nodes": {"l": {"type": "location", "lat": 21.42, "lng": 39.82,
                                                      "name": "فندق الفرسان", "address": "مكة"}}})
        self.assertEqual(say_on(WaCh(), bot, peer(), "hi")[0], ("location", 21.42, 39.82, "فندق الفرسان"))
        out = say(bot, peer(), "hi")                                      # قناة بلا دبّوس
        self.assertIn("maps.google.com/?q=21.42,39.82", out[0][1])

    def test_api_call_renders_safely_saves_and_branches(self):
        import flow_http
        calls, reply = [], {"status": 200}
        orig = flow_http.request

        def fake(method, url, headers=None, body=None, follow=False):
            calls.append((method, url, headers, body))
            return reply["status"], {"data": {"rooms": [{"price": 450}]}}
        flow_http.request = fake
        try:
            bot = new_bot()
            make_flow(bot, {"start": "q", "nodes": {
                "q": {"type": "ask", "text": "المدينة؟", "var": "city", "next": "api"},
                "api": {"type": "api", "method": "POST", "url": "https://api.hotel.test/rooms?city={{city}}",
                        "headers": [{"k": "X-Key", "v": "abc"}], "body": '{"city": "{{city}}"}',
                        "save": [{"var": "price", "path": "data.rooms.0.price"}], "status_var": "code",
                        "next": "ok", "fail": "bad"},
                "ok": {"type": "end", "text": "السعر {{price}} ({{code}})"},
                "bad": {"type": "end", "text": "تعذّر الآن"}}})
            p = peer()
            say(bot, p, "hi")
            out = say(bot, p, 'مكة "الحرم"&x=1')
            m, url, headers, body = calls[0]
            self.assertEqual(url, "https://api.hotel.test/rooms?city=%D9%85%D9%83%D8%A9%20%22%D8%A7%D9%84%D8%AD%D8%B1%D9%85%22%26x%3D1",
                             "قيمة المتغيّر مرمَّزة — لا تحقن معاملات")
            self.assertEqual(json.loads(body), {"city": 'مكة "الحرم"&x=1'}, "علامة التنصيص لا تكسر JSON")
            self.assertEqual(headers["X-Key"], "abc")
            self.assertEqual(out[-1], ("text", "السعر 450 (200)"))
            reply["status"] = 500
            p = peer()
            say(bot, p, "hi")
            self.assertEqual(say(bot, p, "جدة")[-1], ("text", "تعذّر الآن"))
        finally:
            flow_http.request = orig

    def test_api_and_sheets_urls_are_locked_down(self):
        bot = new_bot()
        fid = post(C, f"/api/bot/{bot}/flows", {"name": "x"}).get_json()["flow"]["id"]

        def pub(node):
            post(C, f"/api/bot/{bot}/flows/{fid}/save", {"draft": {"start": "a", "nodes": {"a": node}}})
            return post(C, f"/api/bot/{bot}/flows/{fid}/publish").get_json().get("error")
        self.assertEqual(pub({"type": "api", "url": "http://api.test/x"}), "node:a:url")
        self.assertEqual(pub({"type": "api", "url": "https://{{host}}.evil.test/"}), "node:a:url", "المضيف لا يكون متغيّراً")
        self.assertEqual(pub({"type": "api", "url": "https://user@api.test/"}), "node:a:url")
        self.assertEqual(pub({"type": "api", "url": "https://api.test/", "headers": [{"k": "Host", "v": "x"}]}), "node:a:headers")
        self.assertEqual(pub({"type": "sheets", "url": "https://evil.test/macros/s/abcdefghijk/exec"}), "node:a:sheets")
        import flow_http
        self.assertEqual(flow_http.request("GET", "https://127.0.0.1/admin"), (0, "host"), "لا عناوين داخلية")
        self.assertEqual(flow_http.request("GET", "https://localhost/"), (0, "host"))
        self.assertEqual(flow_http.pick({"a": [{"b": 1}]}, "a.0.b"), 1)

    def test_sheets_posts_a_row_and_follows_apps_script_redirect(self):
        import flow_http
        calls = []
        orig = flow_http.request
        flow_http.request = lambda m, u, h=None, b=None, follow=False: calls.append((m, u, b, follow)) or (200, "ok")
        try:
            bot = new_bot()
            url = "https://script.google.com/macros/s/AKfycbx_TEST_123456/exec"
            make_flow(bot, {"start": "q", "nodes": {
                "q": {"type": "ask", "text": "اسمك؟", "var": "name", "next": "s"},
                "s": {"type": "sheets", "url": url, "fields": ["name"], "next": "e"},
                "e": {"type": "end", "text": "تم"}}})
            p = peer()
            say(bot, p, "hi")
            self.assertEqual(say(bot, p, "منى")[-1], ("text", "تم"))
            m, u, b, follow = calls[0]
            row = json.loads(b)
            self.assertEqual((m, u, follow, row["name"], row["_phone"]), ("POST", url, True, "منى", p[3:]))
        finally:
            flow_http.request = orig

    def test_template_card_charges_before_and_refunds_when_meta_refuses(self):
        import broadcasts as BC
        orig = dict(BC._HOOKS)
        BC.configure(category=lambda bot, name, lang: "MARKETING")
        try:
            owner = _user("tp" + secrets.token_hex(3))
            db.wallet_topup(owner, 1000)
            bot = db.create_bot(owner, "WA", f"wa:{secrets.randbelow(10**12)}", "flow", {}, "whatsapp")
            c = _client(owner)
            fid = post(c, f"/api/bot/{bot}/flows", {"name": "t"}).get_json()["flow"]["id"]
            post(c, f"/api/bot/{bot}/flows/{fid}/save", {"draft": {"start": "t", "nodes": {
                "t": {"type": "template", "name": "umrah_offer", "lang": "ar", "vars": ["{{contact.name}}"],
                      "next": "ok", "fail": "no"},
                "ok": {"type": "end", "text": "أرسلنا العرض"}, "no": {"type": "end", "text": "لاحقاً"}}}})
            self.assertTrue(post(c, f"/api/bot/{bot}/flows/{fid}/publish").get_json()["ok"])
            post(c, f"/api/bot/{bot}/flows/{fid}/toggle", {"active": True})
            price = web.mkt_price()
            out = say_on(WaCh(accept=True), bot, peer(), "hi")
            self.assertEqual(out[0][0:2], ("template", "umrah_offer"))
            self.assertEqual(out[0][2][0]["parameters"][0]["text"], "Ali")
            self.assertEqual(out[-1], ("text", "أرسلنا العرض"))
            self.assertEqual(db.wallet_balance(owner), 1000 - price, "خُصم سعر رسالة تسويقية واحدة")
            out = say_on(WaCh(accept=False), bot, peer(), "hi")
            self.assertEqual(out[-1], ("text", "لاحقاً"))
            self.assertEqual(db.wallet_balance(owner), 1000 - price, "رفض Meta = ردّ كامل")
            BC.configure(category=lambda bot, name, lang: None)                 # الفئة مجهولة
            before = db.wallet_balance(owner)
            self.assertEqual(say_on(WaCh(), bot, peer(), "hi")[-1], ("text", "لاحقاً"))
            self.assertEqual(db.wallet_balance(owner), before, "لا إرسال ولا خصم قبل معرفة الفئة")
        finally:
            BC._HOOKS.clear(); BC._HOOKS.update(orig)

    def test_ai_card_turns_exit_words_and_fallback(self):
        asked, ok = [], {"v": True}
        orig = FE._ai_answer

        async def fake(bot_row, cfg, raw, p, text, extra=None):
            asked.append(text); return ok["v"]
        FE._ai_answer = fake
        try:
            bot = new_bot()
            make_flow(bot, {"start": "ai", "nodes": {
                "ai": {"type": "ai", "text": "اسألني عن الفندق", "turns": 2, "next": "e", "fail": "f"},
                "e": {"type": "end", "text": "سعدنا بخدمتك"}, "f": {"type": "handoff", "text": "نحوّلك لموظف"}}})
            p = peer()
            self.assertEqual(say(bot, p, "hi")[0], ("text", "اسألني عن الفندق"))
            self.assertEqual(say(bot, p, "فيه إفطار؟"), [])                  # الذكاء ردّ (المحاكاة)
            self.assertEqual(say(bot, p, "والمواقف؟")[-1], ("text", "سعدنا بخدمتك"), "بعد سؤالين يكمل")
            self.assertEqual(asked, ["فيه إفطار؟", "والمواقف؟"])
            p = peer()
            say(bot, p, "hi")
            self.assertEqual(say(bot, p, "شكرا")[-1], ("text", "سعدنا بخدمتك"), "كلمة خروج")
            ok["v"] = False
            p = peer()
            say(bot, p, "hi")
            self.assertEqual(say(bot, p, "سؤال")[-1], ("text", "نحوّلك لموظف"), "الذكاء غير متاح ⇒ فرع الفشل")
        finally:
            FE._ai_answer = orig

    def test_assign_to_member_or_least_busy(self):
        owner = _user("as" + secrets.token_hex(3))
        m1, m2 = _user("m1" + secrets.token_hex(3), None), _user("m2" + secrets.token_hex(3), None)
        db.join_team(owner, m1, "member"); db.join_team(owner, m2, "member")
        c = _client(owner)
        bot = db.create_bot(owner, "WA", f"wa:{secrets.randbelow(10**12)}", "flow", {}, "whatsapp")
        fid = post(c, f"/api/bot/{bot}/flows", {"name": "a"}).get_json()["flow"]["id"]
        stranger = _user("st" + secrets.token_hex(3))

        def pub(node):
            post(c, f"/api/bot/{bot}/flows/{fid}/save", {"draft": {"start": "a", "nodes": {"a": node}}})
            return post(c, f"/api/bot/{bot}/flows/{fid}/publish").get_json()
        self.assertEqual(pub({"type": "assign", "mode": "member", "member": stranger})["error"], "node:a:member",
                         "لا إسناد لمن ليس في الفريق")
        self.assertTrue(pub({"type": "assign", "mode": "member", "member": m2, "text": "معك فريق الحجوزات"})["ok"])
        post(c, f"/api/bot/{bot}/flows/{fid}/toggle", {"active": True})
        p = peer()
        self.assertEqual(say(bot, p, "hi")[0], ("text", "معك فريق الحجوزات"))
        self.assertEqual(db.get_contact_by_id(db.contact_id_for_peer(bot, p))["assignee_id"], m2)
        self.assertEqual(db.least_loaded_assignee(owner, [owner, m1, m2]), owner, "صاحب الحساب والأول بلا جهات")


class MoreCardTests(unittest.TestCase):
    def test_switch_routes_by_value_and_otherwise(self):
        bot = new_bot()
        make_flow(bot, {"start": "q", "nodes": {
            "q": {"type": "ask", "text": "المدينة؟", "var": "city", "next": "s"},
            "s": {"type": "switch", "var": "city", "cases": [{"value": "مكة", "next": "m"}, {"value": "المدينة", "next": "d"}],
                  "other": "o"},
            "m": {"type": "end", "text": "فرع مكة"}, "d": {"type": "end", "text": "فرع المدينة"},
            "o": {"type": "end", "text": "فرع آخر"}}})
        for ans, want in (("مكه", "فرع مكة"), ("المدينه", "فرع المدينة"), ("جدة", "فرع آخر")):
            p = peer()
            say(bot, p, "hi")
            self.assertEqual(say(bot, p, ans)[-1], ("text", want), ans)

    def test_resolve_returns_the_chat_to_the_bot(self):
        bot = new_bot()
        make_flow(bot, {"start": "r", "nodes": {"r": {"type": "resolve", "text": "أغلقنا طلبك ✅"}}})
        p = peer()
        db.log_message(bot, p, "in", "customer", "x", name="Ali")
        db.set_conversation_mode(bot, p, "human")
        db.set_conversation_mode(bot, p, "bot")
        self.assertEqual(say(bot, p, "hi")[-1], ("text", "أغلقنا طلبك ✅"))
        conv = db.get_conversation(bot, p)
        self.assertEqual((conv["mode"], conv["unread"]), ("bot", 0))

    def test_products_single_and_list(self):
        class P(WaCh):
            async def send_products(self, peer, catalog, items, header="", body=""):
                self.out.append(("products", catalog, list(items), header)); return {"messages": [{"id": "w"}]}
        bot = new_bot()
        fid = post(C, f"/api/bot/{bot}/flows", {"name": "p"}).get_json()["flow"]["id"]

        def pub(node):
            post(C, f"/api/bot/{bot}/flows/{fid}/save", {"draft": {"start": "a", "nodes": {"a": node}}})
            return post(C, f"/api/bot/{bot}/flows/{fid}/publish").get_json()
        self.assertEqual(pub({"type": "products", "catalog": "abc", "items": ["r1"]})["error"], "node:a:catalog")
        self.assertEqual(pub({"type": "products", "catalog": "123456", "items": ["r1", "r2"]})["error"], "node:a:header")
        self.assertEqual(pub({"type": "products", "catalog": "123456", "items": ["bad id!"]})["error"], "node:a:items")
        self.assertTrue(pub({"type": "products", "catalog": "123456", "items": ["room-1", "room-2"],
                             "header": "غرفنا", "text": "اختر غرفتك"})["ok"])
        post(C, f"/api/bot/{bot}/flows/{fid}/toggle", {"active": True})
        self.assertEqual(say_on(P(), bot, peer(), "hi")[0], ("products", "123456", ["room-1", "room-2"], "غرفنا"))

    def test_whatsapp_form_sends_waits_and_saves_answers(self):
        class F(WaCh):
            sent = []

            async def send_flow(self, peer, flow_id, screen, cta, body, header="", token=""):
                F.sent.append(token); self.out.append(("flow", flow_id, screen, cta)); return {"messages": [{"id": "w"}]}
        bot = new_bot()
        make_flow(bot, {"start": "f", "nodes": {
            "f": {"type": "form", "flow_id": "1234567890", "screen": "BOOKING", "cta": "احجز", "text": "املأ بيانات الحجز",
                  "prefix": "b", "next": "e", "fail": "x"},
            "e": {"type": "end", "text": "حجز {{b_room}} يوم {{b_date}}"}, "x": {"type": "end", "text": "بدون نموذج"}}})
        p = peer()
        self.assertEqual(say_on(F(), bot, p, "hi")[0], ("flow", "1234567890", "BOOKING", "احجز"))
        out = say_on(F(), bot, p, "نص عادي")
        self.assertIn("النموذج", out[0][1], "ينتظر النموذج لا النص")
        ch = F()
        asyncio.run(FE.handle_message(db.get_bot(bot), ch, {"peer": p, "kind": "form", "text": "", "name": "Ali",
                                                              "form": {"flow_token": "forged", "room": "x"}}))
        self.assertIn("النموذج", ch.out[0][1], "رمز مزوَّر لا يُقبل")
        ch = F()
        asyncio.run(FE.handle_message(db.get_bot(bot), ch, {"peer": p, "kind": "form", "text": "", "name": "Ali",
                                                              "form": {"flow_token": F.sent[-1], "room": "جناح", "date": "2026-10-01"}}))
        self.assertEqual(ch.out[-1], ("text", "حجز جناح يوم 2026-10-01"))
        self.assertEqual(say(bot, peer(), "hi")[-1], ("text", "بدون نموذج"), "قناة بلا نماذج ⇒ فرع الفشل")

    def test_whatsapp_parses_form_replies_and_orders(self):
        from channels.whatsapp import WhatsAppChannel
        ch = WhatsAppChannel("1", "t")
        m = ch._one({"from": "201000000001", "id": "w1", "type": "interactive", "interactive": {
            "type": "nfm_reply", "nfm_reply": {"response_json": '{"flow_token": "abc", "room": "suite"}'}}}, "Ali")
        self.assertEqual((m["kind"], m["form"]), ("form", {"flow_token": "abc", "room": "suite"}))
        m = ch._one({"from": "201000000001", "id": "w2", "type": "order", "order": {"catalog_id": "1", "product_items": [
            {"product_retailer_id": "room-1", "quantity": 2, "item_price": 450, "currency": "SAR"}]}}, "Ali")
        self.assertEqual(m["kind"], "text")
        self.assertIn("2× room-1 — 450 SAR", m["text"])

    def test_audio_is_accepted_only_where_asked(self):
        import asset_store
        ogg = b"OggS" + b"\x00" * 100
        v = asset_store.validate(ogg)
        self.assertEqual((v["ok"], v["kind"]), (True, "audio"))
        aid = asset_store.save(OWNER, ogg, "welcome.ogg")["id"]
        with web.app.test_request_context():
            from flask import session
            session["uid"] = OWNER
            self.assertIsNone(web._own_asset_id(aid), "الترحيب والمنتجات والحملات: صور وفيديو فقط")
            self.assertEqual(web._own_asset_id(aid, ("image", "video", "audio")), aid)
        bot = new_bot()
        make_flow(bot, {"start": "v", "nodes": {"v": {"type": "media", "asset": aid, "caption": "رسالة صوتية"}}})
        self.assertEqual(say(bot, peer(), "hi")[0], ("media", aid, "رسالة صوتية"))

    def test_whatsapp_audio_payload(self):
        from channels.whatsapp import WhatsAppChannel
        sent = []

        class W(WhatsAppChannel):
            async def _post(self, p):
                sent.append(p); return {"messages": [{"id": "x"}]}
        ch = W("1", "t")
        orig = db.get_asset_ref
        db.get_asset_ref = lambda a, b: "MID"
        try:
            asyncio.run(ch.send_media("wa:2010", {"id": 1, "kind": "audio", "mime": "audio/ogg", "fname": "x.ogg"}, 1,
                                      caption="اسمع العرض"))
        finally:
            db.get_asset_ref = orig
        self.assertEqual(sent[0]["type"], "audio")
        self.assertEqual(sent[0]["audio"], {"id": "MID"})
        self.assertEqual(sent[1]["text"]["body"], "اسمع العرض", "التعليق رسالة تالية")


class TestLinkTests(unittest.TestCase):
    def test_draft_runs_for_the_code_only_without_stats_or_leads(self):
        bot = new_bot()
        fid = post(C, f"/api/bot/{bot}/flows", {"name": "مسودة"}).get_json()["flow"]["id"]
        post(C, f"/api/bot/{bot}/flows/{fid}/save", {"draft": {"start": "q", "nodes": {
            "q": {"type": "ask", "text": "اسمك؟", "var": "n", "next": "e"}, "e": {"type": "end", "text": "أهلاً {{n}}"}}}})
        r = post(C, f"/api/bot/{bot}/flows/{fid}/test").get_json()
        self.assertTrue(r["ok"] and r["code"].startswith("test-"), r)
        p = peer()
        out = say(bot, p, "مرحبا", "start")
        self.assertNotIn(("text", "اسمك؟"), out, "غير المنشور لا يعمل لغير المختبِر")
        db.clear_chat_state(bot, p)
        out = say(bot, p, r["code"])
        self.assertEqual(out[-1], ("text", "اسمك؟"))
        self.assertEqual(say(bot, p, "منى")[-1], ("text", "أهلاً منى"))
        st = db.flow_stats(bot, fid)
        self.assertEqual((st["sessions"], st["visits"]), (0, {}), "التجربة لا تُحتسب")
        self.assertEqual(db.list_leads(bot, limit=None), [], "ولا تُحفظ كإدخال")
        post(C, f"/api/bot/{bot}/flows/{fid}/save", {"draft": {"start": "q", "nodes": {"q": {"type": "ask", "text": ""}}}})
        self.assertEqual(post(C, f"/api/bot/{bot}/flows/{fid}/test").get_json()["error"], "node:q:text",
                         "التجربة تمرّ بالتحقق نفسه")


class TimeoutTests(unittest.TestCase):
    def test_reminder_then_end_after_silence(self):
        import time as _t
        bot = new_bot()
        fid = post(C, f"/api/bot/{bot}/flows", {"name": "مهلة"}).get_json()["flow"]["id"]
        draft = {"start": "q", "nodes": {"q": {"type": "ask", "text": "كم ليلة؟", "var": "n", "next": None}}}
        self.assertEqual(post(C, f"/api/bot/{bot}/flows/{fid}/save",
                              {"draft": draft, "timeout": {"remind": 5}}).get_json()["error"], "flow:remind_text")
        self.assertTrue(post(C, f"/api/bot/{bot}/flows/{fid}/save", {"draft": draft, "timeout": {
            "remind": 5, "remind_text": "ما زلنا بانتظار ردك {{contact.name}}", "end": 10, "end_text": "أغلقنا الطلب"}}).get_json()["ok"])
        post(C, f"/api/bot/{bot}/flows/{fid}/publish"); post(C, f"/api/bot/{bot}/flows/{fid}/toggle", {"active": True})
        p = peer()
        say(bot, p, "hi")
        now = int(_t.time())
        self.assertEqual([a for *_, a in FG.due_timeouts(now + 60)], [])
        due = FG.due_timeouts(now + 6 * 60)
        self.assertEqual([a for *_, a in due], ["remind"])
        ch = Ch()
        b, s, f, a = due[0]
        asyncio.run(FG.apply_timeout(b, ch, s, f, a))
        self.assertEqual(ch.out, [("text", "ما زلنا بانتظار ردك Ali")])
        self.assertEqual([a for *_, a in FG.due_timeouts(now + 7 * 60)], [], "تذكير واحد فقط")
        due = FG.due_timeouts(now + 11 * 60)
        self.assertEqual([a for *_, a in due], ["end"])
        ch = Ch()
        asyncio.run(FG.apply_timeout(*due[0][:1], ch, *due[0][1:]))
        self.assertEqual(ch.out, [("text", "أغلقنا الطلب")])
        self.assertIsNone(db.get_chat_state(bot, p))
        self.assertEqual(db.flow_stats(bot, fid)["drops"], {"q": 1})

    def test_reply_resets_the_clock_and_human_takeover_silences(self):
        import time as _t
        bot = new_bot()
        fid = post(C, f"/api/bot/{bot}/flows", {"name": "م"}).get_json()["flow"]["id"]
        post(C, f"/api/bot/{bot}/flows/{fid}/save", {"draft": {"start": "q", "nodes": {
            "q": {"type": "ask", "text": "1؟", "var": "a", "next": "r"}, "r": {"type": "ask", "text": "2؟", "var": "b"}}},
            "timeout": {"remind": 5, "remind_text": "تذكير"}})
        post(C, f"/api/bot/{bot}/flows/{fid}/publish"); post(C, f"/api/bot/{bot}/flows/{fid}/toggle", {"active": True})
        p = peer()
        say(bot, p, "hi")
        say(bot, p, "x")                                                  # ردّ ⇒ موعد جديد عند السؤال الثاني
        due = [d for d in FG.due_timeouts(int(_t.time()) + 6 * 60) if d[1]["peer"] == p]
        self.assertEqual(len(due), 1)
        db.set_conversation_mode(bot, p, "human")
        ch = Ch()
        asyncio.run(FG.apply_timeout(due[0][0], ch, due[0][1], due[0][2], due[0][3]))
        self.assertEqual(ch.out, [], "المحادثة مع موظف — لا تذكير آلي")


if __name__ == "__main__":
    unittest.main(verbosity=2)
