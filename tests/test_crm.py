"""جهات الاتصال (CRM) — المرحلة 1: الربط التلقائي بالمحادثات · الملكية بالحساب · الباقة ·
أدوار الفريق · الحقول المخصّصة · الوسوم · الشرائح (بلا حقن SQL) · الاستيراد والتصدير.

    python tests/test_crm.py
"""
import io, json, os, secrets, sys, tempfile, unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_TMPDIR = tempfile.mkdtemp(prefix="botyalla-crm-")
os.environ["BOTYALLA_DB"] = os.path.join(_TMPDIR, "test.db")   # قبل استيراد database
os.environ["BOTYALLA_UPLOADS"] = _TMPDIR
os.environ["BOTYALLA_LOGS"] = os.path.join(_TMPDIR, "logs")
os.environ["ADMIN_USER"] = "admin"
os.environ["ADMIN_PASS"] = "Crm#" + secrets.token_hex(6)

import auth                                # noqa: E402
import crm as CRM                          # noqa: E402
import database as db                      # noqa: E402
import app as web                          # noqa: E402

PW = "Str0ng!Pass" + secrets.token_hex(3)


def _boot():
    db.init_db()
    web.seed_platform_defaults()
    web.contact_defaults()
    web.seed_default_admin()
    web.app.config["TESTING"] = True


def _user(name, plan=None):
    uid, err = db.create_account(name, auth.hash_password(PW), f"{name}@example.test",
                                 None, 30, "person", verify_required=False)
    assert not err, err
    db.mark_email_verified(uid)
    if plan:
        db.activate_subscription(uid, plan, 30)
    return uid


def _client(user_id=None):
    c = web.app.test_client()
    with c.session_transaction() as s:
        s["_csrf"] = "tk"
        if user_id:
            u = db.get_user(user_id)
            s.update(uid=user_id, uname=u["username"], role=u["role"], pwv=web._pw_stamp(u["pw_hash"]))
    return c


def post(c, url, body=None):
    return c.post(url, data=json.dumps(body or {}), content_type="application/json",
                  headers={"X-CSRF-Token": "tk"})


_boot()
ENT = _user("ent" + secrets.token_hex(3), "enterprise")
FREE = _user("free" + secrets.token_hex(3))
OTHER = _user("oth" + secrets.token_hex(3), "enterprise")
BOT = db.create_bot(ENT, "wa", f"wa:{secrets.randbelow(10**9)}", "store", {}, "whatsapp")
BOT2 = db.create_bot(ENT, "tg", f"T:{secrets.token_hex(5)}", "store", {})
OBOT = db.create_bot(OTHER, "wa2", f"wa:{secrets.randbelow(10**9)}", "store", {}, "whatsapp")


class PureLogicTests(unittest.TestCase):
    def test_phone_normalisation_covers_real_export_formats(self):
        for raw in ("+966501234567", "00966501234567", "966501234567", "0501234567", "050 123 4567",
                    "٠٥٠١٢٣٤٥٦٧", "966501234567.0".split(".")[0]):
            self.assertEqual(CRM.norm_phone(raw, "+966"), "+966501234567", raw)
        self.assertEqual(CRM.norm_phone("01012345678", "+20"), "+201012345678")
        self.assertIsNone(CRM.norm_phone("12", "+966"))
        self.assertIsNone(CRM.norm_phone("abc", "+966"))

    def test_field_values_are_typed_and_validated(self):
        sel = {"type": "select", "options": ["Hot", "Cold"]}
        self.assertEqual(CRM.clean_value(sel, "hot"), ("Hot", None))
        self.assertEqual(CRM.clean_value(sel, "warm")[1], "option")
        ms = {"type": "multi_select", "options": ["AR", "EN"]}
        self.assertEqual(CRM.clean_value(ms, "ar, EN")[0], ["AR", "EN"])
        self.assertEqual(CRM.clean_value({"type": "date"}, "26/09/2026")[0], "2026-09-26")
        self.assertEqual(CRM.clean_value({"type": "number"}, "1,500")[0], 1500)
        self.assertEqual(CRM.clean_value({"type": "switch"}, "نعم")[0], True)
        self.assertEqual(CRM.clean_value({"type": "user"}, 5, users={5})[0], 5)
        self.assertEqual(CRM.clean_value({"type": "user"}, 6, users={5})[1], "user")
        self.assertEqual(CRM.clean_value({"type": "text", "required": 1}, "")[1], "required")

    def test_rules_reject_unknown_fields_and_operators(self):
        f = {"stage": {"key": "stage", "type": "select", "options": ["A"]}}
        self.assertEqual(CRM.clean_rules([{"field": "password", "op": "is", "value": "x"}], f)[1], "field")
        self.assertEqual(CRM.clean_rules([{"field": "f:nope", "op": "is", "value": "x"}], f)[1], "field")
        self.assertEqual(CRM.clean_rules([{"field": "name", "op": "; DROP", "value": "x"}], f)[1], "op")
        self.assertEqual(CRM.clean_rules([{"field": "tags", "op": "has_any", "value": ["1 OR 1=1"]}], f)[1], "value")
        self.assertEqual(CRM.clean_rules([{}] * 21, f)[1], "rules")
        ok, err = CRM.clean_rules([{"field": "f:stage", "op": "is", "value": "A"}], f)
        self.assertIsNone(err)

    def test_field_keys_are_safe_identifiers(self):
        self.assertEqual(CRM.make_key("Lead Stage"), "lead_stage")
        self.assertTrue(CRM.KEY_RE.match(CRM.make_key("مرحلة العميل")))
        self.assertEqual(CRM.clean_field_def({"label": "x", "type": "text", "key": 'a"]'})[1], "key")
        self.assertEqual(CRM.clean_field_def({"label": "x", "type": "select", "options": []})[1], "options")


class AutoLinkTests(unittest.TestCase):
    """أي عميل يراسل بوتاً يصبح جهة اتصال للحساب — والحسابات لا تختلط."""

    def test_a_whatsapp_customer_becomes_a_contact(self):
        db.add_bot_user(BOT, 966500000001, "Ahmed", peer="wa:966500000001")
        rows, _ = db.query_contacts(ENT, q="966500000001")
        self.assertEqual(len(rows), 1)
        self.assertEqual((rows[0]["phone"], rows[0]["name"], rows[0]["source"]), ("+966500000001", "Ahmed", "chat"))

    def test_the_same_customer_on_two_bots_is_one_contact(self):
        db.add_bot_user(BOT, 966500000002, "", peer="wa:966500000002")
        other_bot = db.create_bot(ENT, "wa-b", f"wa:{secrets.randbelow(10**9)}", "store", {}, "whatsapp")
        db.add_bot_user(other_bot, 966500000002, "Sara", peer="wa:966500000002")
        rows, total = db.query_contacts(ENT, q="966500000002")
        self.assertEqual(total, 1)
        self.assertEqual(rows[0]["name"], "Sara", "الاسم الفارغ يُملأ لاحقاً")
        self.assertEqual(len(db.contact_channels(rows[0]["id"])), 2)

    def test_accounts_never_share_contacts(self):
        db.add_bot_user(OBOT, 966500000003, "X", peer="wa:966500000003")
        self.assertEqual(db.query_contacts(ENT, q="966500000003")[1], 0)
        self.assertEqual(db.query_contacts(OTHER, q="966500000003")[1], 1)

    def test_telegram_and_username_peers(self):
        db.add_bot_user(BOT2, 777001, "TG", peer="tg:777001")
        db.add_bot_user(BOT, -5, "", peer="wa:SA.998877")
        with db.get_conn() as c:
            self.assertTrue(c.execute("SELECT 1 FROM contacts WHERE owner_id=? AND tg_id=777001", (ENT,)).fetchone())
            self.assertTrue(c.execute("SELECT 1 FROM contacts WHERE owner_id=? AND bsuid='SA.998877'", (ENT,)).fetchone())

    def test_stop_revokes_marketing_consent_on_the_contact(self):
        db.add_bot_user(BOT, 966500000004, "", peer="wa:966500000004")
        db.set_optin(BOT, "wa:966500000004", True)
        self.assertEqual(db.query_contacts(ENT, q="966500000004")[0][0]["optin"], 1)
        db.set_opt_out(BOT, "wa:966500000004", True)
        self.assertEqual(db.query_contacts(ENT, q="966500000004")[0][0]["optin"], 0)

    def test_backfill_links_existing_customers_once(self):
        with db.get_conn() as c:
            c.execute("INSERT INTO bot_users(bot_id,tg_user_id,first_name,created_at,peer) VALUES(?,?,?,?,?)",
                      (BOT, 966500000099, "Old", 1, "wa:966500000099"))
            c.execute("DELETE FROM platform WHERE key='crm_backfill_v1'")
            db._crm_tables(c)
            db._crm_tables(c)                        # مرة ثانية لا تكرّر شيئاً
        self.assertEqual(db.query_contacts(ENT, q="966500000099")[1], 1)


class AccessTests(unittest.TestCase):
    def test_free_plan_is_locked_out(self):
        c = _client(FREE)
        self.assertEqual(c.get("/contacts").status_code, 302)
        self.assertEqual(c.get("/api/crm/contacts").status_code, 403)

    def test_enterprise_and_platform_admin_get_in(self):
        self.assertEqual(_client(ENT).get("/contacts").status_code, 200)
        admin = db.get_user_by_login("admin")["id"]
        self.assertEqual(_client(admin).get("/api/crm/contacts").status_code, 200)

    def test_nav_link_only_where_allowed(self):
        self.assertIn("/contacts", _client(ENT).get("/dashboard").get_data(as_text=True))
        self.assertNotIn('"/contacts"', _client(FREE).get("/dashboard").get_data(as_text=True))

    def test_post_without_csrf_is_rejected(self):
        c = _client(ENT)
        r = c.post("/api/crm/contacts", data=json.dumps({"phone": "0501111111"}), content_type="application/json")
        self.assertEqual(r.status_code, 400)

    def test_another_account_cannot_read_or_touch_my_contacts(self):
        cid, _ = db.save_contact(ENT, {"name": "Mine", "phone": "+966511111111"})
        o = _client(OTHER)
        self.assertEqual(o.get(f"/api/crm/contacts/{cid}").status_code, 404)
        self.assertEqual(post(o, "/api/crm/contacts", {"id": cid, "name": "Hacked"}).status_code, 404)
        self.assertEqual(post(o, "/api/crm/contacts/bulk", {"action": "delete", "ids": [cid]}).get_json()["count"], 0)
        self.assertEqual(db.get_contact(ENT, cid)["name"], "Mine")

    def test_team_member_works_contacts_but_cannot_manage(self):
        m = _user("mem" + secrets.token_hex(3))
        self.assertEqual(db.join_team(ENT, m, "member"), "")
        c = _client(m)
        r = post(c, "/api/crm/contacts", {"name": "By member", "phone": "0512222222", "cc": "+966"})
        self.assertTrue(r.get_json()["ok"], r.get_json())
        self.assertEqual(post(c, "/api/crm/segments", {"name": "x", "rules": []}).status_code, 403)
        self.assertEqual(post(c, "/api/crm/fields", {"label": "x", "type": "text"}).status_code, 403)
        cid = r.get_json()["contact"]["id"]
        self.assertEqual(post(c, "/api/crm/contacts/bulk", {"action": "delete", "ids": [cid]}).status_code, 403)


class ContactAndFieldTests(unittest.TestCase):
    def setUp(self):
        self.c = _client(ENT)

    def _field(self, **d):
        r = post(self.c, "/api/crm/fields", d)
        self.assertTrue(r.get_json()["ok"], r.get_json())
        return r.get_json()["id"]

    def test_custom_fields_validate_and_merge(self):
        self._field(label="Lead Stage", type="select", options=["New", "Won"], key="lead_stage_t")
        r = post(self.c, "/api/crm/contacts", {"phone": "0533333333", "fields": {"lead_stage_t": "Maybe"}})
        self.assertEqual(r.get_json()["fields"], {"f:lead_stage_t": "option"})
        r = post(self.c, "/api/crm/contacts", {"phone": "0533333333", "fields": {"lead_stage_t": "won"}})
        cid = r.get_json()["contact"]["id"]
        self.assertEqual(db.get_contact(ENT, cid)["fields"]["lead_stage_t"], "Won")

    def test_duplicate_phone_is_refused(self):
        post(self.c, "/api/crm/contacts", {"phone": "0544444444"})
        r = post(self.c, "/api/crm/contacts", {"phone": "+966544444444"})
        self.assertEqual(r.get_json()["error"], "phone_taken")

    def test_key_and_type_are_frozen_after_creation(self):
        fid = self._field(label="Budget", type="number", key="budget_t")
        post(self.c, "/api/crm/fields", {"id": fid, "label": "Budget SAR", "type": "text", "key": "hack"})
        f = next(x for x in db.list_fields(ENT) if x["id"] == fid)
        self.assertEqual((f["label"], f["type"], f["key"]), ("Budget SAR", "number", "budget_t"))

    def test_deleting_a_field_wipes_its_values(self):
        self._field(label="Temp", type="text", key="temp_t")
        cid = post(self.c, "/api/crm/contacts", {"phone": "0555555555", "fields": {"temp_t": "v"}}).get_json()["contact"]["id"]
        fid = next(x["id"] for x in db.list_fields(ENT) if x["key"] == "temp_t")
        post(self.c, f"/api/crm/fields/{fid}/delete")
        self.assertNotIn("temp_t", db.get_contact(ENT, cid)["fields"])

    def test_assignee_must_be_on_the_team(self):
        r = post(self.c, "/api/crm/contacts", {"phone": "0566666666", "assignee_id": OTHER})
        self.assertEqual(r.get_json()["fields"], {"assignee_id": "user"})


class SegmentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.owner = _user("seg" + secrets.token_hex(3), "enterprise")
        o = cls.owner
        db.save_field(o, "contact", {"label": "Lang", "key": "lang", "type": "multi_select",
                                     "options": ["AR", "EN"], "active": 1, "required": 0})
        db.save_field(o, "contact", {"label": "Stage", "key": "stage", "type": "select",
                                     "options": ["Hot", "Cold"], "active": 1, "required": 0})
        db.save_field(o, "contact", {"label": "Trip", "key": "trip", "type": "date",
                                     "options": [], "active": 1, "required": 0})
        cls.vip, _ = db.save_tag(o, "VIP")
        cls.umrah, _ = db.save_tag(o, "Umrah")
        cls.a, _ = db.save_contact(o, {"name": "A 100%", "phone": "+966500000101", "optin": 1, "tags": [cls.vip, cls.umrah],
                                       "fields": {"lang": ["AR", "EN"], "stage": "Hot", "trip": "2026-12-01"}})
        cls.b, _ = db.save_contact(o, {"name": "B", "phone": "+966500000102", "tags": [cls.vip],
                                       "fields": {"lang": ["AR"], "stage": "Cold"}})
        cls.cc, _ = db.save_contact(o, {"name": "C", "phone": "+966500000103"})
        cls.fields = db.fields_map(o, "contact", active_only=False)

    def ids(self, rules):
        clean, err = CRM.clean_rules(rules, self.fields)
        self.assertIsNone(err, err)
        return {r["id"] for r in db.query_contacts(self.owner, clean, self.fields, limit=None)[0]}

    def test_tag_operators(self):
        self.assertEqual(self.ids([{"field": "tags", "op": "has_any", "value": [self.vip]}]), {self.a, self.b})
        self.assertEqual(self.ids([{"field": "tags", "op": "has_all", "value": [self.vip, self.umrah]}]), {self.a})
        self.assertEqual(self.ids([{"field": "tags", "op": "has_none", "value": [self.vip]}]), {self.cc})

    def test_custom_fields_and_and_logic(self):
        self.assertEqual(self.ids([{"field": "f:stage", "op": "is", "value": "hot"}]), {self.a})
        self.assertEqual(self.ids([{"field": "f:lang", "op": "has_all", "value": ["AR", "EN"]}]), {self.a})
        self.assertEqual(self.ids([{"field": "f:lang", "op": "has_any", "value": ["AR"]},
                                   {"field": "optin", "op": "is", "value": True}]), {self.a})
        self.assertEqual(self.ids([{"field": "f:trip", "op": "after", "value": "2026-11-30"}]), {self.a})
        self.assertEqual(self.ids([{"field": "f:stage", "op": "empty"}]), {self.cc})

    def test_like_wildcards_are_literal(self):
        self.assertEqual(self.ids([{"field": "name", "op": "contains", "value": "100%"}]), {self.a})
        self.assertEqual(self.ids([{"field": "name", "op": "contains", "value": "%"}]), {self.a})

    def test_injection_through_a_value_stays_a_value(self):
        self.assertEqual(self.ids([{"field": "name", "op": "is", "value": "x' OR '1'='1"}]), set())

    def test_count_and_saved_segment_over_http(self):
        c = _client(self.owner)
        rules = [{"field": "tags", "op": "has_any", "value": [self.vip]}]
        self.assertEqual(post(c, "/api/crm/segments/count", {"rules": rules}).get_json()["count"], 2)
        sid = post(c, "/api/crm/segments", {"name": "VIPs", "rules": rules}).get_json()["id"]
        r = c.get(f"/api/crm/contacts?segment={sid}").get_json()
        self.assertEqual(r["total"], 2)
        self.assertEqual(post(c, "/api/crm/segments/count", {"rules": [{"field": "pw_hash", "op": "is", "value": "x"}]})
                         .status_code, 400)


class ImportExportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.owner = _user("imp" + secrets.token_hex(3), "enterprise")
        db.save_field(cls.owner, "contact", {"label": "Remarks", "key": "remarks", "type": "text",
                                             "options": [], "active": 1, "required": 0})

    def _preview(self, c, data, name="contacts.csv"):
        return c.post("/api/crm/import/preview", data={"file": (io.BytesIO(data), name)},
                      headers={"X-CSRF-Token": "tk"}, content_type="multipart/form-data")

    def test_csv_import_guesses_columns_creates_updates_and_reports(self):
        c = _client(self.owner)
        csv_ = ("الاسم,Phone,Tags,Marketing Optin,remarks\n"
                "Ali,966500000201,\"VIP, Umrah\",true,first\n"
                "Mona,0500000202,,no,\n"
                "Bad,12,,yes,\n").encode("utf-8-sig")
        r = self._preview(c, csv_).get_json()
        self.assertEqual(r["rows"], 3)
        self.assertEqual(r["guess"], {"0": "name", "1": "phone", "2": "tags", "3": "optin", "4": "f:remarks"})
        run = post(c, "/api/crm/import/run", {"token": session_token(c), "mapping": r["guess"], "cc": "+966"}).get_json()
        self.assertEqual(run["stats"], {"created": 2, "updated": 0, "skipped": 0, "errors": 1})
        self.assertEqual(run["errors"], [{"row": 4, "reason": "phone"}])
        ali = db.query_contacts(self.owner, q="966500000201")[0][0]
        self.assertEqual((ali["optin"], ali["fields"]["remarks"], len(ali["tags"])), (1, "first", 2))
        # إعادة الاستيراد تحدّث ولا تكرّر
        self._preview(c, "Phone,remarks\n+966500000201,second\n".encode())
        run = post(c, "/api/crm/import/run", {"token": session_token(c), "mapping": {"0": "phone", "1": "f:remarks"}}).get_json()
        self.assertEqual(run["stats"]["updated"], 1)
        self.assertEqual(db.query_contacts(self.owner, q="966500000201")[0][0]["fields"]["remarks"], "second")

    def test_xlsx_import(self):
        import openpyxl
        wb = openpyxl.Workbook(); ws = wb.active
        ws.append(["Name", "Mobile"]); ws.append(["X", 966500000301])
        buf = io.BytesIO(); wb.save(buf)
        c = _client(self.owner)
        r = self._preview(c, buf.getvalue(), "c.xlsx").get_json()
        run = post(c, "/api/crm/import/run", {"token": session_token(c), "mapping": r["guess"]}).get_json()
        self.assertEqual(run["stats"]["created"], 1)
        self.assertEqual(db.query_contacts(self.owner, q="966500000301")[1], 1)

    def test_import_token_is_bound_to_the_session(self):
        c = _client(self.owner)
        self._preview(c, b"Phone\n966500000401\n")
        tok = session_token(c)
        other = _client(self.owner)                 # جلسة أخرى لنفس الحساب
        self.assertEqual(post(other, "/api/crm/import/run", {"token": tok, "mapping": {"0": "phone"}}).get_json()["error"], "expired")

    def test_mapping_without_phone_is_refused(self):
        c = _client(self.owner)
        self._preview(c, b"Name\nX\n")
        self.assertEqual(post(c, "/api/crm/import/run", {"token": session_token(c), "mapping": {"0": "name"}})
                         .get_json()["error"], "no_phone")

    def test_export_neutralises_formulas(self):
        db.save_contact(self.owner, {"name": "=HYPERLINK(\"http://x\")", "phone": "+966500000501"})
        body = _client(self.owner).get("/contacts/export.csv").get_data(as_text=True)
        self.assertIn("'=HYPERLINK", body)
        self.assertNotIn(",=HYPERLINK", body)


def session_token(c):
    with c.session_transaction() as s:
        return (s.get("crm_import") or {}).get("token")


if __name__ == "__main__":
    unittest.main(verbosity=2)
