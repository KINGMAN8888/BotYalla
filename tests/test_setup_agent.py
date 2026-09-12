"""وكيل الإعداد (TESTER_FEEDBACK_PLAN §3): أسئلة ← تصميم ← معاينة ← تطبيق ← تراجع.
المختبِر كتب «بنعمل ملابس تفصيل و انت بوت خدمة عملاء واضبط الاعدادات» فظهرت
الجملة نفسها في رسالة الترحيب. هذه الاختبارات تمنع عودة ذلك.
    python tests/test_setup_agent.py
"""
import json, os, sys, tempfile, unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_TMP = tempfile.mkdtemp(prefix="botyalla-agent-")
os.environ["BOTYALLA_DB"] = os.path.join(_TMP, "t.db")        # قبل أي استيراد
os.environ["BOTYALLA_UPLOADS"] = _TMP
os.environ["BOTYALLA_LOGS"] = _TMP

import database as db          # noqa: E402
import ai_agent as ai          # noqa: E402
import tg_helpers as tg        # noqa: E402
import app as A                # noqa: E402

TESTER = "بنعمل ملابس تفصيل و انت بوت خدمة عملاء واضبط الاعدادات"


class _Resp:
    def __init__(self, d): self.d = json.dumps(d).encode()
    def read(self): return self.d
    def __enter__(self): return self
    def __exit__(self, *a): return False


class OfflineDesignerTests(unittest.TestCase):
    """المصمّم الاحتياطي — ما يراه كل من لا مفتاح له أو تعطّل مزوّده."""

    def test_tester_prompt_is_understood_not_echoed(self):
        turns = [{"role": "owner", "text": TESTER}]
        r1 = ai.setup_step(turns, template="customer_service", current_name="رغد")
        self.assertEqual(r1["status"], "questions")
        self.assertEqual(r1["source"], "offline")
        self.assertIn("service", [q["id"] for q in r1["questions"]], "لم يتعرّف على نشاط التفصيل")
        turns += [{"role": "agent", "questions": r1["questions"]},
                  {"role": "owner", "answers": [q["options"][0] for q in r1["questions"]]}]
        r2 = ai.setup_step(turns, template="customer_service", current_name="رغد")
        self.assertEqual(r2["status"], "proposal")
        p = r2["proposal"]
        blob = json.dumps(p, ensure_ascii=False)
        self.assertNotIn(TESTER, blob)
        self.assertNotIn(TESTER[:40], p["welcome"], "الترحيب ينسخ أول 40 حرفاً من الوصف")
        self.assertIn("رغد", p["welcome"], "اسم النشاط الحالي لم يُستعمل")
        vars_ = [s.get("var") for s in p["flow"]["steps"]]
        self.assertIn("المقاسات", vars_, "فلو التفصيل بلا خطوة مقاسات")
        media = [s for s in p["flow"]["steps"] if s["type"] == "media"]
        self.assertTrue(media and media[0].get("optional"), "صورة التصميم يجب أن تكون اختيارية")
        # خدمة عملاء: خيارات متابعة الطلب والشكوى حاضرة
        btn = [s for s in p["flow"]["steps"] if s["type"] == "buttons"][0]
        self.assertTrue(any("متابعة" in o for o in btn["options"]))

    def test_unknown_business_asks_type_first(self):
        r = ai.setup_step([{"role": "owner", "text": "عندي شغل صغير وعايز بوت"}], template="flow")
        self.assertEqual(r["status"], "questions")
        self.assertEqual(r["questions"][0]["id"], "cat")

    def test_rounds_are_capped(self):
        turns = [{"role": "owner", "text": "حاجة"}]
        for _ in range(3):
            r = ai.setup_step(turns, template="flow")
            if r["status"] == "proposal":
                break
            turns += [{"role": "agent", "questions": r["questions"]},
                      {"role": "owner", "answers": [""] * len(r["questions"])}]
        self.assertEqual(r["status"], "proposal", "الوكيل لا يتوقف عن السؤال")

    def test_english_description_gets_english_texts(self):
        turns = [{"role": "owner", "text": "We run a pizza restaurant with delivery"}]
        r = ai.setup_step(turns, template="flow", max_rounds=0)
        self.assertEqual(r["status"], "proposal")
        self.assertIn("Welcome", r["proposal"]["welcome"])

    def test_legacy_fallback_never_echoes(self):
        patch, src = ai.generate_bot_config(TESTER, "customer_service", current_name="رغد")
        self.assertEqual(src, "fallback")
        self.assertNotIn(TESTER[:30], patch["welcome"])


class LlmAgentTests(unittest.TestCase):
    """مسار النموذج بـ`_call` مستبدَل — لا شبكة."""

    def setUp(self):
        self._orig = ai._call

    def tearDown(self):
        ai._call = self._orig

    def test_questions_then_design(self):
        calls = []

        def fake(provider, key, system, user):
            calls.append(user)
            if len(calls) == 1:
                return json.dumps({"brief": {"goal": "orders"},
                                   "questions": [{"q": "بتوصّلوا؟", "options": ["أيوه", "لا"]}], "design": None})
            return json.dumps({"brief": {}, "questions": [], "summary": "تمام",
                               "design": {"business_name": "رغد", "welcome": "أهلاً في رغد 👗",
                                          "thanks": "شكراً!",
                                          "flow": {"steps": [
                                              {"type": "question", "prompt": "اسمك؟", "var": "الاسم"},
                                              {"type": "buttons", "prompt": "الخدمة؟", "var": "الخدمة",
                                               "options": ["تفصيل", "تعديل"]}]},
                                          "kb": {"delivery": "داخل القاهرة"}}})
        ai._call = fake
        turns = [{"role": "owner", "text": "محل تفصيل"}]
        r = ai.setup_step(turns, template="customer_service", api_key="k")
        self.assertEqual((r["status"], r["source"]), ("questions", "ai"))
        turns += [{"role": "agent", "questions": r["questions"]}, {"role": "owner", "answers": ["أيوه"]}]
        r = ai.setup_step(turns, template="customer_service", api_key="k")
        self.assertEqual(r["status"], "proposal")
        self.assertEqual(r["proposal"]["kb"]["delivery"], "داخل القاهرة")
        self.assertIn("OWNER ANSWERED: أيوه", calls[1], "الإجابات لم تصل للنموذج")

    def test_model_echo_is_replaced(self):
        ai._call = lambda *a: json.dumps({"questions": [], "design": {
            "welcome": f"👋 أهلاً بك في «{TESTER}»!", "flow": {"steps": [
                {"type": "question", "prompt": "اسمك؟", "var": "الاسم"}]}}})
        r = ai.setup_step([{"role": "owner", "text": TESTER}], template="customer_service",
                          api_key="k", max_rounds=0)
        self.assertEqual(r["status"], "proposal")
        self.assertNotIn(TESTER, r["proposal"]["welcome"])

    def test_invalid_design_is_repaired_then_falls_back(self):
        n = {"calls": 0}

        def bad(*a):
            n["calls"] += 1
            return json.dumps({"questions": [], "design": {"flow": {"steps": []}}})
        ai._call = bad
        r = ai.setup_step([{"role": "owner", "text": "محل تفصيل فساتين"}],
                          template="customer_service", api_key="k", max_rounds=0)
        self.assertEqual(n["calls"], 2, "لا محاولة إصلاح")
        self.assertEqual((r["status"], r["source"]), ("proposal", "offline"))
        self.assertTrue(r["proposal"]["flow"]["steps"])

    def test_config_is_sanitised(self):
        patch = ai._coerce_config({"flow": {"steps": [
            {"type": "exec", "prompt": "x", "var": "a"},
            {"type": "buttons", "prompt": "واحد؟", "var": "a", "options": ["فقط"]},
            {"type": "question", "prompt": "", "var": "b"}]},
            "products": [{"name": "فستان", "price": "-5"}], "evil": 1}, "customer_service")
        steps = patch["flow"]["steps"]
        self.assertEqual([s["type"] for s in steps], ["question", "question"])
        self.assertEqual(len({s["var"] for s in steps}), 2, "مفتاح مكرّر يمسح إجابة")
        self.assertNotIn("evil", patch)
        self.assertNotIn("products", patch, "منتجات على قالب ليس متجراً")


class RoutesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        tg.urllib.request.urlopen = lambda *a, **k: _Resp(
            {"ok": True, "result": {"id": 1, "username": "raghad_bot", "first_name": "R"}})
        tg._tg_post = lambda *a, **k: (True, "OK")
        db.init_db()
        cls.c = A.app.test_client()
        cls.c.get("/register")
        cls.c.post("/register", data={"username": "agentuser", "password": "secret123", "csrf_token": cls.tk()})
        cls.uid = db.get_user_by_name("agentuser")["id"]
        cls.c.post("/bot/create", data={"name": "رغد", "token": "123456:ABCDEFGHIJKLMNOPQRSTUV",
                                        "template": "customer_service", "csrf_token": cls.tk()})
        cls.bid = db.list_bots(cls.uid)[0]["id"]

    @classmethod
    def tk(cls):
        with cls.c.session_transaction() as s:
            if "_csrf" not in s:
                s["_csrf"] = "t" * 32
            return s["_csrf"]

    def post(self, url, body=None):
        return self.c.post(url, json=body or {}, headers={"X-CSRF-Token": self.tk()})

    def test_full_session_apply_and_restore(self):
        before = json.loads(db.get_bot(self.bid)["config_json"])
        d = self.post(f"/bot/{self.bid}/ai/session", {"description": TESTER}).get_json()
        self.assertEqual(d["status"], "questions")
        d = self.post(f"/bot/{self.bid}/ai/session/{d['sid']}/reply",
                      {"answers": [q["options"][0] for q in d["questions"]]}).get_json()
        self.assertEqual(d["status"], "proposal")
        self.assertIn("flow", d["before"], "الفرق «قبل» لا يُعرض")
        self.assertEqual(json.loads(db.get_bot(self.bid)["config_json"]), before,
                         "المعاينة كتبت في الإعدادات قبل الموافقة")
        self.assertTrue(self.post(f"/bot/{self.bid}/ai/session/{d['sid']}/apply").get_json()["ok"])
        self.assertEqual(self.post(f"/bot/{self.bid}/ai/session/{d['sid']}/apply").status_code, 404)
        after = json.loads(db.get_bot(self.bid)["config_json"])
        self.assertEqual(after["flow"], d["proposal"]["flow"])
        v = db.list_config_versions(self.bid)[0]
        self.c.post(f"/bot/{self.bid}/config/restore/{v['id']}", data={"csrf_token": self.tk()})
        self.assertEqual(json.loads(db.get_bot(self.bid)["config_json"]).get("flow"), before.get("flow"))

    def test_quota_on_free_plan(self):
        with db.get_conn() as c:
            c.execute("DELETE FROM ai_setup_sessions WHERE owner_id=?", (self.uid,))
        for _ in range(3):
            self.assertTrue(self.post(f"/bot/{self.bid}/ai/session", {"description": "مطعم"}).get_json()["ok"])
        d = self.post(f"/bot/{self.bid}/ai/session", {"description": "مطعم"}).get_json()
        self.assertFalse(d["ok"])
        self.assertTrue(d.get("upgrade"))

    def test_other_owner_cannot_touch_session(self):
        d = self.post(f"/bot/{self.bid}/ai/session", {"description": "صالون"}).get_json()
        other = A.app.test_client()
        other.get("/register")
        with other.session_transaction() as s:
            s["_csrf"] = "o" * 32
        other.post("/register", data={"username": "intruder", "password": "secret123", "csrf_token": "o" * 32})
        r = other.post(f"/bot/{self.bid}/ai/session/{d['sid']}/apply", headers={"X-CSRF-Token": "o" * 32})
        self.assertEqual(r.status_code, 404)

    def test_restore_keeps_operational_fields(self):
        cfg = json.loads(db.get_bot(self.bid)["config_json"])
        db.save_config_version(self.bid, dict(cfg, owner_chat_id="111"), "ai_apply")
        cfg["owner_chat_id"] = "999"
        db.update_bot_config(self.bid, cfg)
        v = db.list_config_versions(self.bid)[0]
        self.c.post(f"/bot/{self.bid}/config/restore/{v['id']}", data={"csrf_token": self.tk()})
        self.assertEqual(json.loads(db.get_bot(self.bid)["config_json"])["owner_chat_id"], "999",
                         "الاسترجاع أعاد ربط مالك قديم")


if __name__ == "__main__":
    unittest.main(verbosity=2)
