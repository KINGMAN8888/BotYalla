"""مزامنة HubSpot / Zoho (المرحلة 9): جهات الاتصال والإدخالات ⇒ CRM خارجي، بمؤشّر، بلا تكرار، والأسرار مختومة.

خادم CRM محاكى داخل الاختبار — لا شبكة. القاعدة والملفات في مجلد مؤقت.
"""
import json, os, re, secrets, sys, tempfile, time, unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_TMPDIR = tempfile.mkdtemp(prefix="botyalla-crmsync-")
os.environ["BOTYALLA_DB"] = os.path.join(_TMPDIR, "test.db")   # قبل استيراد database
os.environ["BOTYALLA_UPLOADS"] = _TMPDIR
os.environ["BOTYALLA_LOGS"] = os.path.join(_TMPDIR, "logs")
os.environ["ADMIN_USER"] = "admin"
os.environ["ADMIN_PASS"] = "Cs#" + secrets.token_hex(6)

import auth                                # noqa: E402
import crm_sync as CS                      # noqa: E402
import database as db                      # noqa: E402
import app as web                          # noqa: E402

PW = "Str0ng!Pass" + secrets.token_hex(3)
db.init_db(); web.seed_platform_defaults(); web.contact_defaults(); web.seed_default_admin()
web.app.config["TESTING"] = True
HS_TOKEN = "pat-na1-" + secrets.token_hex(16)


class R:
    def __init__(self, code, body=None):
        self.status_code, self._b = code, body
        self.content = b"" if body is None else json.dumps(body).encode()
        self.text = self.content.decode()

    def json(self):
        return self._b


class FakeCRM:
    """HubSpot و Zoho معاً — مخزن جهات بسيط يكفي لسلوك البحث/الإنشاء/التحديث/الملاحظات."""
    def __init__(self):
        self.contacts, self.notes, self.calls, self.fail = {}, [], [], None
        self.token_calls = 0
        self._clock = int(time.time() * 1000)

    def tick(self):
        """ساعة الـ CRM: كل كتابة بعد سابقتها بمللي ثانية على الأقل (lastmodifieddate)."""
        self._clock = max(self._clock + 1, int(time.time() * 1000))
        return self._clock

    def edit(self, cid, **props):
        """تعديل من داخل الـ CRM نفسه (موظف المبيعات)."""
        self.contacts[cid].update(props, _mod=self.tick())

    def close(self):
        pass

    def _find(self, key, value):
        return [cid for cid, c in self.contacts.items() if value and c.get(key) == value]

    def post(self, url, params=None, **k):
        self.token_calls += 1                                  # نقطة توكن Zoho
        if params.get("refresh_token") != "1000.refresh":
            return R(400, {"error": "invalid_code"})
        return R(200, {"access_token": "zat", "api_domain": "https://www.zohoapis.sa", "expires_in": 3600})

    def request(self, method, url, headers=None, json=None, params=None):
        self.calls.append((method, url))
        if self.fail:
            return R(self.fail)
        auth = (headers or {}).get("Authorization", "")
        if "hubapi" in url:
            if auth != f"Bearer {HS_TOKEN}":
                return R(401, {"message": "bad token"})
            if url.endswith("/contacts/search"):
                f = json["filterGroups"][0]["filters"][0]
                if f["propertyName"] == "lastmodifieddate":
                    rows = sorted(((i, c) for i, c in self.contacts.items() if c.get("_mod", 0) > int(f["value"])),
                                  key=lambda x: x[1]["_mod"])
                    return R(200, {"results": [{"id": i, "properties": dict(
                        {k: v for k, v in c.items() if not k.startswith("_")},
                        lastmodifieddate=time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(c["_mod"] / 1000)) + f".{c['_mod'] % 1000:03d}Z")}
                        for i, c in rows]})
                key = {"email": "email", "phone": "phone"}[f["propertyName"]]
                return R(200, {"results": [{"id": i} for i in self._find(key, f["value"])][:1]})
            if url.endswith("/objects/contacts") and method == "POST":
                cid = str(len(self.contacts) + 101)
                self.contacts[cid] = dict(json["properties"], _mod=self.tick())
                return R(201, {"id": cid})
            m = re.search(r"/objects/contacts/(\d+)$", url)
            if m and method == "PATCH":
                self.contacts[m.group(1)].update(json["properties"], _mod=self.tick())
                return R(200, {"id": m.group(1)})
            if url.endswith("/objects/notes"):
                self.notes.append((json["associations"][0]["to"]["id"], json["properties"]["hs_note_body"]))
                return R(201, {"id": "n1"})
            return R(200, {"results": []})
        # Zoho
        if auth != "Zoho-oauthtoken zat":
            return R(401, {"code": "INVALID_TOKEN"})
        if url.endswith("/Contacts/search"):
            key, value = next(iter(params.items()))
            ids = self._find({"email": "Email", "phone": "Phone"}[key], value)
            return R(200, {"data": [{"id": i} for i in ids]}) if ids else R(204)
        if url.endswith("/Contacts") and method == "GET":
            since = headers.get("If-Modified-Since", "")
            rows = [dict({k: v for k, v in c.items() if not k.startswith("_")}, id=i,
                         Modified_Time=time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime(c["_mod"] / 1000)))
                    for i, c in sorted(self.contacts.items(), key=lambda x: x[1].get("_mod", 0))
                    if c.get("_mod") and time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime(c["_mod"] / 1000)) >= since]
            return R(200, {"data": rows}) if rows else R(304)
        if url.endswith("/Contacts") and method == "POST":
            cid = str(len(self.contacts) + 9001)
            self.contacts[cid] = dict(json["data"][0], _mod=self.tick())
            return R(201, {"data": [{"status": "success", "details": {"id": cid}}]})
        if url.endswith("/Contacts") and method == "PUT":
            rec = dict(json["data"][0])
            self.contacts[rec.pop("id")].update(rec, _mod=self.tick())
            return R(200, {"data": [{"status": "success"}]})
        if url.endswith("/Notes"):
            self.notes.append((json["data"][0]["Parent_Id"], json["data"][0]["Note_Content"]))
            return R(201, {"data": [{"status": "success"}]})
        return R(200, {"users": []})


FAKE = FakeCRM()
CS.httpx.Client = lambda *a, **k: FAKE


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


def post(c, url, body=None):
    return c.post(url, data=json.dumps(body or {}), content_type="application/json", headers={"X-CSRF-Token": "tk"})


def contact(owner, name, phone, email=None):
    cid, _ = db.upsert_contact_by_phone(owner, phone, name, email, source="manual")
    return cid


class HubSpotTests(unittest.TestCase):
    def setUp(self):
        global FAKE
        FAKE = FakeCRM()
        CS.httpx.Client = lambda *a, **k: FAKE

    def test_contacts_sync_update_match_and_lead_notes(self):
        owner = user("hs")
        c = client(owner)
        FAKE.contacts["55"] = {"email": "old@example.test", "phone": "+966500000009"}   # موجود مسبقاً في HubSpot
        a = contact(owner, "نورة القحطاني", "+966500000001", "noura@example.test")
        b = contact(owner, "عميل قديم", "+966500000009")
        contact(owner, "", "+966500000002")
        self.assertEqual(post(c, "/api/crm-sync/settings", {"provider": "hubspot", "token": "bad"}).get_json()["error"], "token")
        r = post(c, "/api/crm-sync/settings", {"provider": "hubspot", "token": HS_TOKEN}).get_json()
        self.assertTrue(r["ok"] and r["config"]["connected"] and r["config"]["enabled"], r)
        self.assertNotIn(HS_TOKEN, c.get("/integrations").get_data(as_text=True))
        self.assertNotIn(HS_TOKEN, db.get_setting(owner, CS.CFG_KEY), "مختوم في القاعدة")
        n, _ = CS.sync_owner(owner)
        self.assertEqual(n, 3)
        self.assertEqual(db.crm_link(owner, b, "hubspot"), "55", "طابق الجهة الموجودة بالهاتف بدل التكرار")
        hs_a = db.crm_link(owner, a, "hubspot")
        self.assertEqual({k: v for k, v in FAKE.contacts[hs_a].items() if not k.startswith("_")},
                         {"firstname": "نورة", "lastname": "القحطاني", "phone": "+966500000001", "email": "noura@example.test"})
        self.assertEqual(CS.sync_owner(owner), (0, 0), "لا شيء تغيّر = لا طلبات")
        time.sleep(1.1)
        db.set_contact_value(owner, a, "name", "نورة محمد")
        calls = len(FAKE.calls)
        self.assertEqual(CS.sync_owner(owner)[0], 1)
        self.assertEqual(FAKE.contacts[hs_a]["lastname"], "محمد")
        self.assertEqual([m for m, _ in FAKE.calls[calls:]], ["PATCH"], "الرابط المحفوظ = تحديث مباشر بلا بحث")
        # إدخال فلو ⇒ ملاحظة على جهة HubSpot
        bot = db.create_bot(owner, "WA", f"wa:{secrets.randbelow(10**12)}", "flow", {}, "whatsapp")
        db.link_contact(bot, "wa:966500000001", "نورة")
        db.add_lead(bot, 966500000001, {"room": "جناح", "nights": "3"})
        self.assertEqual(CS.sync_owner(owner)[1], 1)
        self.assertEqual(FAKE.notes[-1][0], hs_a)
        self.assertIn("room: جناح", FAKE.notes[-1][1])
        self.assertEqual(CS.sync_owner(owner)[1], 0, "الملاحظة مرة واحدة")

    def test_failure_keeps_cursor_and_bad_key_disables(self):
        owner = user("hs")
        c = client(owner)
        post(c, "/api/crm-sync/settings", {"provider": "hubspot", "token": HS_TOKEN})
        contact(owner, "أ", "+966511111111")
        FAKE.fail = 429
        self.assertEqual(CS.sync_owner(owner), (0, 0))
        self.assertEqual(CS.public_config(owner)["last_error"], "rate")
        FAKE.fail = None
        self.assertEqual(CS.sync_owner(owner)[0], 1, "أُعيدت من نفس المؤشّر")
        self.assertEqual(CS.public_config(owner)["last_error"], "")
        other = user("hs2")
        r = post(client(other), "/api/crm-sync/settings", {"provider": "hubspot", "token": "pat-na1-" + "x" * 30})
        self.assertEqual((r.status_code, r.get_json()["error"]), (400, "crm_auth"))
        self.assertFalse(CS.public_config(other)["enabled"], "مفتاح لم يثبت = لا مزامنة")

    def test_history_leads_not_flooded_and_plan_gate(self):
        owner = user("hs")
        bot = db.create_bot(owner, "WA", f"wa:{secrets.randbelow(10**12)}", "flow", {}, "whatsapp")
        db.add_lead(bot, 966500000077, {"old": "1"})
        post(client(owner), "/api/crm-sync/settings", {"provider": "hubspot", "token": HS_TOKEN})
        self.assertEqual(CS.sync_owner(owner)[1], 0, "الإدخالات السابقة للربط لا تُرسل")
        free = user("free", plan=None)
        CS.save_config(free, "hubspot", token=HS_TOKEN)
        cid = contact(free, "x", "+966522222222")
        self.assertIs(CS.HOOKS["gate"], web._owner_crm, "app.py يضبط بوابة الباقة")
        CS.tick()
        self.assertIsNone(db.crm_link(free, cid, "hubspot"), "حساب بلا باقة الشركات لا يُزامَن")
        self.assertIsNotNone(db.crm_link(owner, db.contacts_changed_since(owner, 0)[0]["id"], "hubspot") if
                             db.contacts_changed_since(owner, 0) else "none", "حساب الشركات يُزامَن في الدورة نفسها")


class TwoWayTests(unittest.TestCase):
    def setUp(self):
        global FAKE
        FAKE = FakeCRM()
        CS.httpx.Client = lambda *a, **k: FAKE

    def test_crm_edits_flow_back_without_echo(self):
        owner = user("tw")
        c = client(owner)
        a = contact(owner, "نورة", "+966500000031")
        self.assertTrue(post(c, "/api/crm-sync/settings", {"provider": "hubspot", "token": HS_TOKEN, "two_way": True}).get_json()["ok"])
        CS.sync_owner(owner)
        ext = db.crm_link(owner, a, "hubspot")
        # موظف المبيعات يعدّل الاسم في HubSpot ويضيف عميلاً جديداً هناك
        FAKE.edit(ext, firstname="نورة", lastname="العتيبي", email="noura@example.test")
        FAKE.contacts["900"] = {"firstname": "فيصل", "lastname": "", "phone": "0551230000", "_mod": FAKE.tick()}
        calls = len(FAKE.calls)
        CS.sync_owner(owner)
        ct = db.get_contact(owner, a)
        self.assertEqual((ct["name"], ct["email"]), ("نورة العتيبي", "noura@example.test"))
        new = db.contact_by_phone(owner, "+966551230000")
        self.assertTrue(new, "العميل المضاف في الـ CRM صار جهة اتصال")
        self.assertEqual(db.get_contact(owner, new)["name"], "فيصل")
        self.assertEqual([m for m, u in FAKE.calls[calls:] if m != "POST" or not u.endswith("/search")], [],
                         "لا دفع للقيم التي سحبناها للتوّ (لا صدى)")
        calls = len(FAKE.calls)
        CS.sync_owner(owner)
        self.assertEqual(len(FAKE.calls) - calls, 1, "دورة هادئة = استعلام تغييرات واحد فقط")
        self.assertEqual(CS.public_config(owner)["pulled"], 2)

    def test_phone_taken_by_another_contact_is_kept(self):
        owner = user("tw")
        c = client(owner)
        a = contact(owner, "أ", "+966500000041")
        b = contact(owner, "ب", "+966500000042")
        post(c, "/api/crm-sync/settings", {"provider": "hubspot", "token": HS_TOKEN, "two_way": True})
        CS.sync_owner(owner)
        FAKE.edit(db.crm_link(owner, a, "hubspot"), phone="+966500000042")
        CS.sync_owner(owner)
        self.assertEqual(db.get_contact(owner, a)["phone"], "+966500000041")
        self.assertEqual(db.get_contact(owner, b)["phone"], "+966500000042")

    def test_one_way_never_pulls(self):
        owner = user("tw")
        post(client(owner), "/api/crm-sync/settings", {"provider": "hubspot", "token": HS_TOKEN})
        FAKE.contacts["77"] = {"firstname": "x", "phone": "0559990000", "_mod": FAKE.tick()}
        CS.sync_owner(owner)
        self.assertIsNone(db.contact_by_phone(owner, "+966559990000"))


class ZohoTests(unittest.TestCase):
    def setUp(self):
        global FAKE
        FAKE = FakeCRM()
        CS.httpx.Client = lambda *a, **k: FAKE
        CS._ZOHO_TOKENS.clear()

    def test_zoho_refresh_token_flow_and_last_name_fallback(self):
        owner = user("zo")
        c = client(owner)
        body = {"provider": "zoho", "client_id": "1000.CLIENT", "client_secret": "sec", "refresh_token": "1000.refresh", "dc": "sa"}
        self.assertEqual(post(c, "/api/crm-sync/settings", dict(body, dc="xx")).get_json()["error"], "dc")
        self.assertTrue(post(c, "/api/crm-sync/settings", body).get_json()["ok"])
        page = c.get("/integrations").get_data(as_text=True)
        self.assertNotIn("1000.refresh", page)
        self.assertNotIn('"sec"', page)
        a = contact(owner, "", "+966533333333")
        contact(owner, "خالد", "+966544444444")
        self.assertEqual(CS.sync_owner(owner)[0], 2)
        z = FAKE.contacts[db.crm_link(owner, a, "zoho")]
        self.assertEqual((z["Last_Name"], z["Phone"], z["Lead_Source"]), ("+966533333333", "+966533333333", "WhatsApp"))
        self.assertTrue(all(u.startswith("https://www.zohoapis.sa") for _, u in FAKE.calls), "نطاق البيانات من ردّ التوكن")
        before = FAKE.token_calls
        time.sleep(1.1)
        db.set_contact_value(owner, a, "name", "سارة علي")
        CS.sync_owner(owner)
        self.assertEqual(FAKE.token_calls, before, "التوكن مخزّن حتى ينتهي")
        self.assertEqual(FAKE.contacts[db.crm_link(owner, a, "zoho")]["Last_Name"], "علي")
        r = post(c, "/api/crm-sync/settings", dict(body, refresh_token="1000.wrong"))
        self.assertEqual(r.get_json()["error"], "crm_auth")

    def test_zoho_two_way_pull(self):
        owner = user("zo")
        c = client(owner)
        body = {"provider": "zoho", "client_id": "1000.C", "client_secret": "s", "refresh_token": "1000.refresh", "dc": "sa", "two_way": True}
        self.assertTrue(post(c, "/api/crm-sync/settings", body).get_json()["ok"])
        a = contact(owner, "سعد", "+966500000051")
        CS.sync_owner(owner)
        time.sleep(1.1)                                     # Modified_Time في Zoho بالثانية
        FAKE.edit(db.crm_link(owner, a, "zoho"), First_Name="سعد", Last_Name="الدوسري", Email="saad@example.test")
        CS.sync_owner(owner)
        ct = db.get_contact(owner, a)
        self.assertEqual((ct["name"], ct["email"]), ("سعد الدوسري", "saad@example.test"))
        FAKE.calls.clear()
        CS.sync_owner(owner)
        self.assertEqual([m for m, _ in FAKE.calls], ["GET"], "لا صدى — استعلام التغييرات وحده")

    def test_switching_provider_resets_links(self):
        owner = user("zo")
        c = client(owner)
        post(c, "/api/crm-sync/settings", {"provider": "hubspot", "token": HS_TOKEN})
        a = contact(owner, "x", "+966555555555")
        CS.sync_owner(owner)
        self.assertTrue(db.crm_link(owner, a, "hubspot"))
        post(c, "/api/crm-sync/settings", {"provider": "zoho", "client_id": "1000.C", "client_secret": "s", "refresh_token": "1000.refresh"})
        self.assertIsNone(db.crm_link(owner, a, "hubspot"))
        self.assertEqual(CS.sync_owner(owner)[0], 1, "مزامنة أولى كاملة للمزوّد الجديد")
        self.assertTrue(post(c, "/api/crm-sync/settings", {"clear": True}).get_json()["ok"])
        self.assertEqual(CS.public_config(owner)["provider"], "")


if __name__ == "__main__":
    unittest.main(verbosity=2)
