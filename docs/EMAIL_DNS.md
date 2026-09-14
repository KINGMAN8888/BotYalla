# ✉️ إيميلات تصل للـ Inbox لا للـ Spam — SPF · DKIM · DMARC

المنصة ترسل: إيصالات الاشتراك، روابط استرجاع كلمة المرور، ردود تذاكر الدعم. بدون السجلات
الثلاثة يعاملها Gmail وOutlook كمنتحلة لدومينك فتذهب للـ Spam — وعميل لا يستطيع استرجاع حسابه
عميل خسرته.

| السجل | ماذا يقول لخوادم البريد |
|---|---|
| **SPF** | «هذه الخدمات مسموح لها ترسل باسم botyalla.com» |
| **DKIM** | توقيع رقمي على كل إيميل يثبت أنه لم يُعدَّل وأنه من خدمتك فعلاً |
| **DMARC** | «لو فشل الفحصان، افعل كذا» (راقب · اعزل · ارفض) |

**الوضع الحالي (فحصته):** DNS الدومين عند Hostinger، ولا يوجد أيٌّ من الثلاثة، ولا MX.

## 1) اختر خدمة الإرسال (مرة واحدة)
- **Brevo** (مقترحة للإيميلات الآلية): مجانية حتى 300 إيميل يومياً، وتعطيك السجلات جاهزة.
- **Zoho Mail**: لو تريد أيضاً صندوق بريد حقيقي على `@botyalla.com`.

## 2) Brevo — الخطوات
1. سجّل في brevo.com ← **Senders, Domains & Dedicated IPs** ← **Domains** ← **Add a domain** ← `botyalla.com`.
2. ستعرض Brevo 3–4 سجلات (تحقق · DKIM · DMARC). **انسخ كل قيمة كما تظهر حرفياً.**
3. في Hostinger: **hPanel ← Domains ← botyalla.com ← DNS / Nameservers ← DNS records** ← لكل سجل:
   اختر النوع (TXT أو CNAME) ← الاسم (Name) ← القيمة ← TTL الافتراضي ← **Add record**.
4. **SPF** (سجل TXT واحد فقط للدومين كله — لو وُجد سجل يبدأ بـ `v=spf1` عدّله ولا تضف ثانياً):
   - Name: `@`  ·  Value: `v=spf1 include:spf.brevo.com ~all`
5. **DMARC** — ابدأ بالمراقبة فقط:
   - Name: `_dmarc`  ·  Value: `v=DMARC1; p=none; adkim=r; aspf=r`
   - بعد أسبوعين بلا مشاكل في الإرسال غيّرها إلى `p=quarantine`.
6. ارجع لـ Brevo واضغط **Authenticate / Verify** — قد يأخذ DNS من دقائق إلى ساعات.
7. **مفتاح SMTP:** Brevo ← **SMTP & API** ← **Generate a new SMTP key**. ثم على السيرفر في `/opt/botyalla/.env`:
   ```
   SMTP_HOST=smtp-relay.brevo.com
   SMTP_PORT=587
   SMTP_TLS=starttls
   SMTP_USER=اسم دخول SMTP كما تعرضه Brevo
   SMTP_PASS=مفتاح SMTP (لا كلمة مرور حسابك)
   SMTP_FROM=BotYalla <no-reply@botyalla.com>
   PUBLIC_URL=https://botyalla.com
   ```
   ثم: `sudo systemctl restart botyalla`

> **Zoho بدلاً منها:** نفس الفكرة — Zoho تعطيك سجلات MX وSPF (`include:zoho.com`) وDKIM من لوحة
> الإدارة، وSMTP هو `smtp.zoho.com` (أو `smtppro.zoho.com` لحسابات المؤسسات) على المنفذ 587.
> لا تجمع خدمتين في سجلي SPF — ضع الاثنين في سجل واحد: `v=spf1 include:spf.brevo.com include:zoho.com ~all`.

## 3) تحقّق
```bash
nslookup -type=TXT botyalla.com          # يظهر v=spf1 ...
nslookup -type=TXT _dmarc.botyalla.com   # يظهر v=DMARC1 ...
```
ثم افتح [mail-tester.com](https://www.mail-tester.com)، انسخ العنوان الذي يعطيه، واطلب «نسيت كلمة
المرور» من الموقع بحساب إيميله هذا العنوان — الهدف **9/10 أو أكثر**. التقرير يقول بالضبط ما ينقص.
