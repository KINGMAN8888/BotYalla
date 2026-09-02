# AGENTS.md — دليل عمل الوكيل الذكي على مشروع BotYalla

> **اقرأ هذا الملف بالكامل قبل تعديل أي سطر.** هذا المشروع منصة SaaS حقيقية فيها **دفع ومستخدمون وأدوار وبوتات تليجرام**. الأخطاء هنا تكلّف مالاً وثقة عملاء. اتبع الأنماط الموجودة حرفياً ولا تعِد اختراع أي شيء.

---

## 0) القاعدة الذهبية
- **لا تكسر ما يعمل.** غيّر أقل قدر ممكن، وبنفس أسلوب الكود الموجود.
- **بعد أي تعديل: شغّل الاختبارات** (قسم «الاختبار» أدناه). لا تسلّم كوداً لم يمرّ الاختبار.
- **لو مش متأكد:** اقرأ ملف مشابه موجود وقلّده، لا تبتكر نمطاً جديداً.
- كل شيء عن الملكية والتواصل باسم **Youssef Alsherief** (info@youssefalsherief.tech · 201097585951). لا تُدخل أي اسم شركة آخر.

---

## 1) نظرة سريعة على البنية
- **اللغة/الإطار:** Python + **Flask** + **SQLite** + **python-telegram-bot 21.6**. لا مكتبات ثقيلة، لا ORM.
- **بدون build step:** كل شيء server-rendered بقوالب Jinja2. الواجهة CSS خام في `static/app.css`.
- **التشغيل:** `python app.py` (تطوير) ينادي `bootstrap()`. الإنتاج عبر `wsgi.py` + gunicorn.

| الملف | المسؤولية — لا تخلط بينها |
|---|---|
| `app.py` | كل مسارات Flask، الجلسات، CSRF، فرض الأدوار/الباقات، منطق الويب |
| `database.py` | **كل** وصول لـ SQLite (استعلامات + دوال). لا تكتب SQL خارج هذا الملف |
| `auth.py` | تشفير كلمات المرور (Werkzeug) |
| `plans.py` | تعريف الباقات وحدودها |
| `payments.py` | فحص إيصالات الدفع (صورة/بصمة تكرار/OCR اختياري) + ملخص الفحص |
| `platform_bot.py` | بوت المنصة: تنبيه الأدمن + أزرار موافقة/رفض + أوامر `/stats` `/pending` `/users` |
| `bot_manager.py` | تشغيل عدة بوتات + بوت المنصة في خيط asyncio + البث + الإشعارات |
| `flow_engine.py` | محرك المحادثات العام (No-Code) + `send_intro` + التكامل الرسمي مع تليجرام (`configure_bot_profile`) في `tg_helpers` |
| `templates_bot.py` | قوالب البوتات: `build_flow` / `build_store` / `build_booking` / `build_menu` + `PRESET_FLOWS` + `TEMPLATES` |
| `tg_helpers.py` | التحقق من التوكن (getMe) + ربط الأدمن + أوامر مشتركة + `configure_bot_profile`/`setMy*` |
| `ai_agent.py` | وكيل الـ AI (Gemini/Groq) + مولّد احتياطي. يُستدعى بمفتاح **المنصة** فقط |
| `i18n.py` | قاموس الترجمة عربي/إنجليزي + `t()` |
| `icons.py` | مجموعة أيقونات SVG (خطية). `icon('name', size)` |

## 2) قاعدة البيانات (جداول SQLite)
`users` · `settings` · `bots` · `bot_users` · `leads` · `orders` · `bookings` · `subscriptions` · `payments` · `platform` · `bot_requests` · `events`

- **الهجرات (Migrations):** تتم داخل `database._migrate(c)` المستدعى في نهاية `init_db()`. لأي عمود جديد على جدول قائم: أضِفه في تعريف `CREATE TABLE` **و** أضِف `ALTER TABLE ... ADD COLUMN` داخل `_migrate` (احرس بـ `if "col" not in cols`). هكذا لا تنكسر قواعد البيانات القديمة.
- **المستخدم رقم 1 = admin دائماً** (مقفول، لا يُخفّض).

---

## 3) 🔒 ثوابت أمنية — لا تُكسر أبداً
1. **CSRF على كل POST.** كل `<form>` **يجب** أن يحتوي `{{ csrf_field() }}`. كل `fetch(... method:'POST')` **يجب** أن يرسل ترويسة `'X-CSRF-Token': CSRF` (وCSRF معرّف من `<meta name=csrf-token>`). أي POST بدون توكن يُرفض بـ 400.
   - **لا مسار يغيّر الحالة عبر GET إطلاقاً.** فحص CSRF يشمل `POST/PUT/PATCH/DELETE` فقط، فأي إجراء يعدّل شيئاً (تشغيل/إيقاف/حذف بوت · حظر مستخدم · بتّ دفعة · تغيير حالة طلب) **يجب** أن يكون `methods=["POST"]` وزرّه داخل `<form method="post">` فيه `{{ csrf_field() }}` — لا `<a href>`. القيم المسموحة في المسار تُقيَّد بمحوّل `<any(...)>` حتى لا تُقبل قيمة غير متوقّعة ولا يتضارب المسار مع جاره.
2. **الأدوار (RBAC):** استخدم `@require_roles("admin")` أو `@require_roles("admin","support")` أو `@login_required`. لا تنشئ آلية صلاحيات جديدة.
   - `admin` = تحكم كامل · `support` = مشاهدة (لا يغيّر أدواراً/إعدادات منصة/يبتّ مدفوعات) · `user` = عميل.
   - **مصدر الدور والحظر هو قاعدة البيانات لا الجلسة.** `_revalidate_identity` (before_request) يعيد قراءة المستخدم كل طلب، ينهي الجلسة فوراً لو حُذف الحساب أو حُظر، ويزامن `session["role"]`. اقرأ الدور بـ `current_role()` دائماً — لا `session["role"]` مباشرة — وإلا عاد تأخّر سريان الحظر/التخفيض.
3. **الدفع — التحقق المزدوج:**
   - **لا تفعيل تلقائي للاشتراك إطلاقاً.** التفعيل فقط عبر `db.finalize_payment(pid,"approved")` من موافقة الأدمن (زر تليجرام أو `/admin/payments/<id>/approve`).
   - **المبلغ من جهة الخادم** (`plans.plan(plan_id)["price"]`) — لا تثق أبداً في مبلغ من الفورم.
   - `finalize_payment` **ذرّي** (يرجّع None لو سبق البتّ) — لا تلتفّ حوله.
   - **صور الإيصالات خاصة:** تُقدَّم فقط عبر `/admin/payments/<id>/screenshot` (admin/support). لا تضعها في `static/`.
4. **مفتاح الـ AI للأدمن فقط:** يُخزّن في `platform` (`db.get_platform("ai_key")`) ويُدار من `/settings` (admin only). العميل يستخدم الوكيل بمفتاح المنصة ولا يرى الإعدادات.
5. **ملكية البوت:** استخدم `_owned(bot_id)` (يرمي 404 لغير المالك) في أي مسار خاص ببوت.
6. **SQL دائماً بمعاملات `?`** — ممنوع دمج نصوص في الاستعلامات.
7. **رفع الملفات:** تحقّق من الامتداد (`pay.ALLOWED_EXT`) والتوقيع، واستخدم `secure_filename`. الأسماء تُولَّد داخلياً.
8. **الأدمن غير محدود:** فرض حد الباقة يتخطّى `admin`/`support` (`if current_role() not in ("admin","support")`).

---

## 4) أنماط يجب اتّباعها حرفياً

### إضافة نوع بوت جديد (شائع + قالب ثابت)
1. **بوت محادثة (أسئلة/أزرار):** أضِف فلو افتراضي في `templates_bot.PRESET_FLOWS["نوعك"]`، وسجّله في `TEMPLATES` بـ `"build": build_flow`.
2. **بوت قائمة/FAQ:** استخدم `"build": build_menu` وأضِف عناصر افتراضية (`DEFAULT_MENU_ITEMS`) تُحقَن في `cfg["menu_items"]` عند الإنشاء (في `app.bot_create`).
3. في `app.py`:
   - `bot_create`: يحقن `PRESET_FLOWS`/`menu_items` تلقائياً (الكود موجود — قلّده).
   - أضِف النوع لقائمة الإتاحة إن كان يجمع بيانات: `bot_detail` (leads) و`flow_builder` guard.
4. الترجمة: أضِف `tmpl_<key>` في `i18n.py`، وأضِف النوع في:
   - `app.py` context processor: `tmpl_label` و`tmpl_icon`.
   - `templates_web/dashboard.html`: قائمة `for k in [...]`.
5. **اختبر** إنشاء بوت من النوع الجديد ورندر صفحته.

### إضافة مفتاح ترجمة
- أضِف سطراً في `i18n.T` بالشكل: `"key": {"ar": "...", "en": "..."},`
- استخدمه في القوالب: `{{ t('key') }}`. لا تكتب نصاً عربياً/إنجليزياً مباشراً في القالب إلا للأشياء الصغيرة جداً (نمط `{{ '...' if lang=='ar' else '...' }}` مقبول للجُمل النادرة).

### إضافة أيقونة
- أضِف مسار SVG في `icons._P["name"]` ثم استخدم `{{ icon('name', 16) }}`. تأخذ لون النص تلقائياً (`currentColor`). **تحقّق أن الاسم موجود** قبل استخدامه.

### إضافة مسار/صفحة
- استخدم الديكوريتر الصحيح (`@login_required` / `@require_roles(...)`).
- أضِف رابط تنقّل في `templates_web/base.html` بنفس نمط `{% if role... %}`.
- كل قالب جديد يمتدّ `base.html` ويستخدم `t()` و`icon()` و`{{ csrf_field() }}` في أي فورم.

---

## 5) الاختبار (إلزامي بعد أي تعديل)
- التطبيق يعمل بالكامل عبر **Flask test client** بدون تليجرام حقيقي. الأنماط جاهزة:
  - **stub لتليجرام getMe:** استبدل `tg_helpers.urllib.request.urlopen` بلامبدا تُرجع JSON فيه `{"ok":true,"result":{...}}`.
  - **stub لاستدعاءات إعداد البوت:** `tg._tg_post = lambda *a, **k: (True, "OK")`.
  - **stub للـ AI:** `ai_agent._call = lambda *a: json.dumps({...})`.
  - **CSRF في الاختبار:** اقرأ التوكن من الجلسة: `with c.session_transaction() as s: token = s.get("_csrf")` وأرسله في الفورم (`csrf_token`) أو الترويسة (`X-CSRF-Token`).
- **قالب اختبار سريع:**
  ```python
  import os, json, database as db, app as A, tg_helpers as tg
  if os.path.exists("botyalla.db"): os.remove("botyalla.db")
  A.bootstrap()
  c = A.app.test_client()
  def tk(cl):
      cl.get("/login")
      with cl.session_transaction() as s: return s.get("_csrf")
  c.post("/login", data={"username":"admin","password":"admin1234","csrf_token":tk(c)}, follow_redirects=True)
  # ... جرّب المسار الذي عدّلته، ثم أكّد النتيجة في قاعدة البيانات ...
  ```
- **حد أدنى قبل التسليم:** كل الصفحات ترندر 200 في اللغتين (`/lang/ar` ثم `/lang/en`) + السيناريو الذي عدّلته يعمل.
- **لا OCR محلياً على ويندوز** — طبيعي؛ الفحص الآلي يظهر «غير متاح، راجع الصورة يدوياً» (يعمل OCR على السيرفر لأن `server_setup.sh` يثبّت tesseract).

---

## 6) ممنوعات صريحة (لا تفعلها)
- ❌ **لا تنشئ بوت تليجرام عبر أي API.** تيليجرام لا يوفّر ذلك — BotFather يدوي فقط. لا تلمس هذه الفكرة.
- ❌ لا تجمع بيانات دخول حسابات تليجرام للمستخدمين (رقم/كود/2FA). خطر أمني ومخالف.
- ❌ لا تُفعّل اشتراكاً بدون موافقة أدمن، ولا تجعل المبلغ من الفورم.
- ❌ لا تضع مفاتيح/أسرار في الكود. الأسرار في `.env` (`FLASK_SECRET`, `ADMIN_USER/PASS`, `COOKIE_SECURE`).
- ❌ لا ترفع `.env` ولا `botyalla.db` ولا `uploads/pay_*` إلى Git (محميّة بـ `.gitignore`).
- ❌ لا تُشغّل `workers` أكثر من 1 في gunicorn — البوتات تعمل داخل العملية (حالة في الذاكرة). موضّح في `gunicorn_conf.py`.
- ❌ لا تحذف أعمدة/جداول، ولا تعيد تسمية دوال `database.py` المستخدمة في أماكن كثيرة.

---

## 7) النشر والمزامنة
- **محلياً:** `python app.py` → `http://127.0.0.1:5000` → دخول `admin/admin1234` (غيّرها من «حسابي»).
- **سيرفر Hostinger:** `deploy/deploy_hostinger.bat` (يرفع الملفات ويثبّت كل شيء).
- **GitHub:** `deploy/push_to_github.sh` أو `.ps1`.
- بعد أي تعديل تريد نشره: تأكّد أن الاختبارات مرّت ثم ادفع لـ Git.

---

## 8) عند الشك
اقرأ الكود المشابه الموجود (نفس نوع المسار/القالب/الدالة) وقلّده بدقّة. الاتساق أهم من الإبداع في هذا المشروع. راجع `PROJECT_MEMORY.md` لفهم ما تم إنجازه وما تبقّى.
