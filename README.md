<div align="center">
  <img src="static/logo.svg" alt="BotYalla" height="70">

  # BotYalla — منصة بوتات تليجرام للأنشطة
  ### The Telegram Bots Platform for Businesses

  أنشئ بوت خدمة عملاء أو متجر أو حجوزات — **بدون أي برمجة**. وكيل ذكاء اصطناعي، تحليلات، حملات، ونظام اشتراكات ودفع محلي كامل.

  `Python` · `Flask` · `SQLite` · `python-telegram-bot` · عربي/English
</div>

---

## ✨ المميزات
- 🧩 **باني محادثات No-Code** — صمّم ردود بوتك بالخطوات، بدون كود.
- 🤖 **وكيل ذكاء اصطناعي** — يظبط البوت كاملاً من وصف نشاطك (Gemini / Groq + مولّد احتياطي مجاني).
- 🛍️ **قوالب جاهزة** — متجر · حجوزات · خدمة عملاء · باني مخصص.
- 📊 **تحليلات حية** + 📢 **حملات Broadcast** + 🖼️ **دعم الصور** + ⬇️ **تصدير CSV**.
- 🌐 **عربي / إنجليزي** بالكامل مع مبدّل لغة (RTL/LTR).
- 💳 **نظام SaaS ربحي** — باقات + دفع محلي (فودافون كاش/انستاباي/بنكي) + تحقق مزدوج آمن.

## 🚀 التشغيل السريع (محلياً)
```bash
pip install -r requirements.txt
python app.py
# افتح http://127.0.0.1:5000  — أول حساب تسجّله = مالك المنصة
```

## ☁️ النشر على سيرفر (تلقائي)
```bash
sudo bash deploy/deploy.sh https://github.com/USERNAME/botyalla.git botyalla.com
```
التفاصيل الكاملة في **[docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)**.

## 🔒 الأمان
CSRF · تشفير كلمات المرور · تحديد محاولات الدخول · عزل صلاحيات · تحقق دفع مزدوج (لا تفعيل تلقائي).
التفاصيل في **[docs/SECURITY.md](docs/SECURITY.md)**.

## 📚 التوثيق
| الدليل | الوصف |
|---|---|
| [دليل الاستخدام](docs/USER_GUIDE.md) | للمالك والعملاء |
| [دليل النشر](docs/DEPLOYMENT.md) | GitHub + سيرفر + HTTPS |
| [البنية التقنية](docs/ARCHITECTURE.md) | المكوّنات ونموذج البيانات |
| [الأمان](docs/SECURITY.md) | الضوابط الأمنية |

## 💰 الباقات (افتراضية — عدّلها في `plans.py`)
| الباقة | السعر | الحدود |
|---|---|---|
| مجانية | 0 | بوت واحد |
| احترافية | 199 ج/شهر | 5 بوتات + AI + حملات |
| الأعمال | 499 ج/شهر | بوتات غير محدودة |

---
<div align="center">
صُنع بواسطة <b>Reca Tech</b> · info@reca-tech.com · botyalla.com
</div>
