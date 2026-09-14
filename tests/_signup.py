"""نموذج تسجيل صالح للاختبارات — نظام الحساب يطلب كل الحقول وكلمة مرور قوية (accounts.py).

    from _signup import signup, STRONG_PW
    client.post("/register", data=signup("ahmed"))                 # csrf_token = "tk"
    client.post("/register", data=signup("ahmed", tok, email=""))  # تجاوز أي حقل

ليس ملف اختبار (لا يبدأ بـ test_) — run_tests.sh لا يشغّله وحده.
"""
import hashlib

STRONG_PW = "Yalla#Test2026"


def _h(name):
    return hashlib.sha1(name.encode("utf-8")).hexdigest()


def phone_for(name):
    """موبايل مصري صالح وفريد لكل اسم (010 + 8 أرقام)."""
    return "010" + str(int(_h(name), 16))[:8]


def signup(username, csrf="tk", **kw):
    d = {"username": username, "email": f"u{_h(username)[:10]}@example.com",
         "phone_cc": "+20", "phone": phone_for(username), "age": "30", "entity_type": "individual",
         "password": STRONG_PW, "password2": STRONG_PW, "terms": "1", "csrf_token": csrf}
    d.update(kw)
    return d
