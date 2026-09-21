"""الرقم الرسمي وحده للعملاء: لا يظهر الخط الشخصي في ردود البوت ولا في إعدادات التواصل.
    python tests/test_official_number.py
"""
import os, sys, tempfile, unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_TMP = tempfile.mkdtemp(prefix="botyalla-offnum-")
os.environ["BOTYALLA_DB"] = os.path.join(_TMP, "t.db")        # قبل أي استيراد
os.environ["BOTYALLA_UPLOADS"] = _TMP
os.environ["BOTYALLA_LOGS"] = _TMP

import database as db          # noqa: E402
import platform_kb             # noqa: E402
import app as A                # noqa: E402

PERSONAL = "1097585951"
OFFICIAL = "201281275886"


class OfficialNumberTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        db.init_db()

    def test_old_personal_default_is_replaced_once_custom_is_kept(self):
        db.set_platform("support_whatsapp", "201097585951")
        A.contact_defaults()
        self.assertEqual(db.get_platform("support_whatsapp"), OFFICIAL)
        db.set_platform("support_whatsapp", "201555000111")          # رقم اختاره الأدمن بنفسه
        A.contact_defaults()
        self.assertEqual(db.get_platform("support_whatsapp"), "201555000111")

    def test_bot_facts_never_carry_the_personal_line(self):
        db.set_platform("support_whatsapp", "201097585951")            # حتى لو بقي في الإعداد
        db.set_platform("vodafone_number", "01097585951")
        f = platform_kb.facts()
        self.assertEqual(f["support"]["whatsapp"], OFFICIAL)
        self.assertNotIn(PERSONAL, str(f))
        for intent_text in ("عايز أدفع", "عايز أكلم حد من الفريق", "رقم الواتساب"):
            reply = platform_kb.offline_reply(intent_text) if hasattr(platform_kb, "offline_reply") else ""
            self.assertNotIn(PERSONAL, str(reply), intent_text)

    def test_payment_page_still_shows_the_wallet(self):
        """رقم المحفظة مكانه صفحة الدفع — العميل يحتاجه ليحوّل."""
        db.set_platform("vodafone_number", "01097585951")
        self.assertEqual(A._public_plat()["vodafone_number"], "01097585951")


if __name__ == "__main__":
    unittest.main(verbosity=2)
