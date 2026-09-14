# ✉️ إيميلات تصل للـ Inbox لا للـ Spam — SPF · DKIM · DMARC

المنصة ترسل: إيصالات الاشتراك، روابط استرجاع كلمة المرور، الترحيب، تذكير انتهاء الاشتراك، ردود
تذاكر الدعم، وحملات «رسائل البريد». بدون التوثيق يعاملها Gmail وOutlook كمنتحلة لدومينك فتذهب
للـ Spam — وعميل لا يستطيع استرجاع حسابه عميل خسرته.

| السجل | ماذا يقول لخوادم البريد |
|---|---|
| **SPF** | «هذه الخدمات مسموح لها ترسل باسم botyalla.com» |
| **DKIM** | توقيع رقمي على كل إيميل يثبت أنه لم يُعدَّل وأنه من خدمتك فعلاً |
| **DMARC** | «لو فشل الفحصان، افعل كذا» (راقب · اعزل · ارفض) |

## الترتيب المعتمد: Brevo يرسل · Hostinger يستقبل
```
المنصة ──SMTP──▶ Brevo ──▶ العميل        From: BotYalla <no-reply@botyalla.com>
العميل يضغط «رد» ─────────▶ info@botyalla.com (Hostinger Mail)     ← Reply-To
```
- **`no-reply@botyalla.com` لا يحتاج صندوقاً** — Brevo يرسل باسم أي عنوان على دومين موثَّق عنده. لا تكلفة إضافية.
- **كل رسالة تحمل `Reply-To: info@botyalla.com`** (من `SMTP_REPLY_TO`، وإلا إيميل الدعم في «إعدادات المنصة») — فردود العملاء تصل صندوقك الحقيقي.
- **الاثنان يعيشان معاً في DNS:** سجلات Hostinger (MX + DKIM `hostingermail-*`) للاستقبال، وسجلات Brevo للإرسال. **لا تحذف أياً منها.**

## الوضع الحالي (فحصته 2026-09-14)
| السجل | الموجود | الحالة |
|---|---|---|
| MX | `mx1.hostinger.com` · `mx2.hostinger.com` | ✅ استقبال info@ |
| DKIM Hostinger | `hostingermail-a/b/c._domainkey` | ✅ اتركها |
| **DKIM Brevo** | `brevo1/brevo2._domainkey` — **غير موجودة** | ❌ **هذا ما ينقص** |
| SPF | `v=spf1 include:_spf.mail.hostinger.com ~all` | ⚠️ يُضاف له Brevo |
| DMARC | `v=DMARC1; p=none` | ✅ مراقبة فقط |

بدون DKIM لـ Brevo، رسائل المنصة موقَّعة باسم Brevo لا باسم botyalla.com ⇒ Gmail قد يضعها في Spam أو يكتب «via brevo».

## 1) وثّق الدومين في Brevo (مرة واحدة، مجاناً)
1. brevo.com ← **Senders, Domains & Dedicated IPs** ← **Domains** ← **Add a domain** ← `botyalla.com`
   (لو كان مضافاً من قبل وحالته «Not authenticated» افتحه واضغط **Authenticate**).
2. اختر التوثيق اليدوي (**Authenticate yourself / manually**). ستعرض Brevo السجلات — عادةً:
   - **TXT** بالاسم `@` قيمته تبدأ بـ `brevo-code:` (إثبات ملكية)
   - **CNAME** بالاسم `brevo1._domainkey`
   - **CNAME** بالاسم `brevo2._domainkey`
   - (وقد تقترح سجل DMARC — **لا تضف ثانياً**، راجع الخطوة 4)
3. hPanel ← **Domains** ← botyalla.com ← **DNS / Nameservers** ← **DNS records** ← لكل سجل:
   النوع ← الاسم ← القيمة **منسوخة حرفياً من Brevo** ← **Add record**.
   في خانة الاسم اكتب `brevo1._domainkey` فقط — Hostinger يكمل `.botyalla.com` وحده.
4. **SPF — سجل واحد فقط للدومين كله.** لا تضف سجلاً جديداً؛ **عدّل** الموجود ليصبح:
   ```
   v=spf1 include:_spf.mail.hostinger.com include:spf.brevo.com ~all
   ```
   (سجلا SPF معاً = SPF باطل للاثنين، ويضيع بريد info@ أيضاً.)
5. **DMARC — سجل واحد فقط.** اترك الموجود، أو عدّله ليصلك تقرير أسبوعي:
   ```
   v=DMARC1; p=none; rua=mailto:info@botyalla.com
   ```
6. ارجع لـ Brevo واضغط **Authenticate / Verify** — DNS يأخذ من دقائق إلى ساعات. الهدف: ✅ أمام كل سجل.

## 2) إعداد السيرفر (`/opt/botyalla/.env`)
الموجود عندك يبقى كما هو (Brevo)، ويكفي التأكد من هذه القيم:
```
SMTP_HOST=smtp-relay.brevo.com
SMTP_PORT=587
SMTP_TLS=starttls
SMTP_USER=اسم دخول SMTP كما تعرضه Brevo
SMTP_PASS=مفتاح SMTP من Brevo ← SMTP & API (لا كلمة مرور حسابك)
SMTP_FROM=BotYalla <no-reply@botyalla.com>
SMTP_REPLY_TO=info@botyalla.com
PUBLIC_URL=https://botyalla.com
```
ثم: `sudo systemctl restart botyalla`. (`SMTP_REPLY_TO` اختياري — بدونه يُستخدم إيميل الدعم من
«إعدادات المنصة»، وهو `info@botyalla.com` تلقائياً بعد النشر.)

**السقف اليومي:** Brevo المجاني 300 رسالة/يوم لكل الإيميلات. سقف حملات «رسائل البريد» الافتراضي
250 — يترك 50 لإيميلات الاسترجاع والإيصالات. لا ترفعه فوق 280 على الباقة المجانية؛ تجاوز حدّ Brevo
يوقف الإرسال كله يومها.

## 3) شدّد DMARC بعد أسبوعين
لما تتأكد (من تقارير DMARC أو من الاختبار تحت) أن كل رسائلك تنجح:
`v=DMARC1; p=quarantine; rua=mailto:info@botyalla.com`

## 4) تحقّق
```bash
nslookup -type=CNAME brevo1._domainkey.botyalla.com   # يظهر ...brevo.com
nslookup -type=TXT botyalla.com                       # سجل v=spf1 واحد فيه hostinger و brevo
nslookup -type=TXT _dmarc.botyalla.com                # سجل v=DMARC1 واحد
```
ثم «رسائل البريد» ← اكتب أي رسالة ← **«جرّبها على إيميلي»** (إيميلك في «حسابي» على Gmail) ←
في Gmail افتح الرسالة ← ⋮ ← **Show original**: المطلوب **SPF: PASS · DKIM: PASS (botyalla.com) ·
DMARC: PASS**. أو [mail-tester.com](https://www.mail-tester.com) — الهدف 9/10 فأكثر.

> **بديل لو استغنيت عن Brevo:** الإرسال من صندوق Hostinger نفسه (`smtp.hostinger.com` · 465 · `ssl`)
> موثَّق فوراً، لكن `SMTP_FROM` لازم يكون نفس الصندوق الذي تسجّل به (مثلاً info@ نفسه).
