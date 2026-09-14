# 🔐 الدخول بجوجل وفيسبوك — الإعداد (مرة واحدة، مجاناً)

الأزرار **لا تظهر** في صفحتي الدخول والتسجيل إلا بعد ضبط مفاتيح المزوّد في `.env` على السيرفر
(ومعها `PUBLIC_URL`). كل مزوّد مستقل: تقدر تفعّل جوجل وحده الآن وفيسبوك لاحقاً.

**عنوان الرجوع (Redirect URI)** — يُكتب عند المزوّد حرفياً:
- جوجل: `https://botyalla.com/auth/google/callback`
- فيسبوك: `https://botyalla.com/auth/facebook/callback`

## 1) جوجل (Google Cloud Console)
1. [console.cloud.google.com](https://console.cloud.google.com) ← أنشئ مشروعاً باسم `BotYalla`.
2. **APIs & Services ← OAuth consent screen** ← User type: **External** ← الاسم `BotYalla`، إيميل الدعم
   `info@botyalla.com`، اللوجو، روابط: `https://botyalla.com` · `https://botyalla.com/privacy` ·
   `https://botyalla.com/terms` ← Scopes: `openid` · `email` · `profile` (الأساسية — لا تحتاج مراجعة).
3. اضغط **Publish app** (من Testing إلى In production) — وإلا يدخل فقط من تضيفهم كـ Test users.
4. **Credentials ← Create credentials ← OAuth client ID** ← Application type: **Web application** ←
   Authorized redirect URIs: `https://botyalla.com/auth/google/callback` ← **Create**.
5. انسخ **Client ID** و**Client secret** إلى `/opt/botyalla/.env`:
   ```
   GOOGLE_CLIENT_ID=....apps.googleusercontent.com
   GOOGLE_CLIENT_SECRET=GOCSPX-....
   ```

## 2) فيسبوك (Meta for Developers)
1. [developers.facebook.com/apps](https://developers.facebook.com/apps) ← **Create app** ← Use case:
   **Authenticate and request data from users with Facebook Login** ← الاسم `BotYalla`.
2. **App settings ← Basic**: Privacy Policy URL `https://botyalla.com/privacy` · Terms of Service
   `https://botyalla.com/terms` · User data deletion: **Data deletion instructions URL** ←
   `https://botyalla.com/privacy` · App icon · Category: Business ← **Save**.
3. **Facebook Login ← Settings** ← Valid OAuth Redirect URIs:
   `https://botyalla.com/auth/facebook/callback` ← **Save**.
4. **Permissions**: `email` و`public_profile` فقط (متاحتان بلا App Review).
5. بدّل وضع التطبيق من **Development** إلى **Live** (أعلى الصفحة) — وإلا يدخل المطوّرون فقط.
6. انسخ **App ID** و**App Secret** (App settings ← Basic) إلى `.env`:
   ```
   FACEBOOK_APP_ID=1234567890
   FACEBOOK_APP_SECRET=....
   ```

ثم: `sudo systemctl restart botyalla` — الأزرار تظهر فوراً.

## كيف يعمل (للمراجعة)
- **حساب جديد:** البريد يأتي مؤكَّداً من جوجل (فلا كود)، والعميل يكمل: اسم المستخدم · نوع الحساب · السن ·
  الهاتف · الموافقة على الشروط. فيسبوك قد لا يرسل بريداً (حساب مسجّل بالهاتف) — عندها يكتبه العميل ويؤكّده بكود.
- **حساب قائم بنفس البريد:** يُربط تلقائياً **فقط** لو بريده مؤكَّد عندنا — وإلا يُطلب منه الدخول بكلمة المرور
  وتأكيد بريده ثم الربط من «حسابي» (يمنع الاستيلاء على حساب سجّله أحد ببريد غيره).
- **الأمان:** `state` عشوائي لكل محاولة + PKCE (جوجل) + مهلة 10 دقائق، والتبادل من السيرفر مباشرة (السرّ لا يصل
  المتصفح). لا نطلب إلا المعرّف والبريد والاسم، ولا ننشر شيئاً باسم العميل.
- **حساب بجوجل/فيسبوك بلا كلمة مرور:** يضبطها وقتما يشاء من «نسيت كلمة المرور».
- الكود: `app.py` (`_OAUTH` · `oauth_start` · `oauth_callback` · `register_complete`) — `tests/test_accounts.py::OAuthTests`.
