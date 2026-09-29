# مصفوفة التكافؤ مع المنافس (Gallabox) — شرط العميل: «مثلها بالضبط أو أفضل»

> المصدر: مراجعة كاملة لموقعهم وصفحة الأسعار و**172 صفحة من توثيقهم الرسمي** (2026-09-26).
> التكافؤ = **نفس القدرات والسلوك** بهوية BotYalla وتصميمها — لا نسخ اسم أو شعار أو شاشات.
> الحالة: ✅ موجود · 🟡 جزئي · ❌ غير موجود. المرحلة = رقمها في [ENTERPRISE_PLAN.md](ENTERPRISE_PLAN.md).
> هذا الملف هو **قائمة القبول**: لا تُعلن مرحلة منتهية قبل أن تصبح كل بنودها ✅.

## 1) جهات الاتصال (Contacts) — المرحلة 1
> **✅ نُفّذت (2026-09-26):** كل بنود هذا القسم عدا: عمود Instagram ID (مع قناة إنستجرام، المرحلة 8) واستبدال المتغيّرات داخل القوالب/الفلو (المرحلتان 3 و5 — المفاتيح جاهزة `{{contact.field.key}}`). الترتيب بأسهم لا بالسحب.
| القدرة عندهم | BotYalla الآن | المرحلة |
|---|---|---|
| جدول جهات اتصال موحّد لكل الحساب (اسم · هاتف · بريد · Instagram ID · BSUID · المالك · أُنشئ/حُدّث · المنشئ) | 🟡 `bot_users`/`leads` لكل بوت | 1 |
| أعمدة قابلة للإضافة/الإخفاء في الجدول + بحث + فلتر + صفحات 20/50/100 | ❌ | 1 |
| إضافة جهة يدوياً · تعديل · حذف · عمليات جماعية | ❌ | 1 |
| **Companies** (شركات بحقولها وربط جهات الاتصال بها) | ❌ | 1 |
| حقول مخصّصة للجهة وللشركة: Text · Multi-text · Number · Select · Multi-select · Date · Switch · User — مع «نشط» و«إلزامي» وترتيب بالسحب | ❌ | 1 |
| **Marketing Opt-in** (مفتاح) يحكم البثّ التسويقي | 🟡 `opted_out` عبر STOP | 1 |
| **Contact Owner** (مسؤول الجهة من الفريق) | ❌ | 1 |
| **Tags**: إنشاء/إدارة، على الجهة وعلى المحادثة، تصنيفات `intent:`/`type:`… | ❌ | 1 |
| **Segments** ديناميكية: شروط AND على الحقول القياسية والمخصّصة والوسوم والتواريخ + «View count» + تحديث لحظي | ❌ | 1 |
| استيراد CSV/Excel بمطابقة أعمدة · تصدير | 🟡 تصدير CSV للبيانات | 1 |
| Variables: `{{contact.name}}` · `{{contact.field.x}}` · `{{user.name}}` · `{{company.x}}` في القوالب والفلو والتسلسلات | 🟡 متغيّرات الفلو فقط | 1 (+3/5) |

## 2) البثّ (Broadcast) — المراحل 2 و3
> **✅ المرحلة 3 نُفّذت (2026-09-28):** المعالج بثلاث خطوات، الجمهور من الشرائح/كل الجهات/المشتركين، سياسة الموافقة، الجدولة، Smart Retry وإحصاءاته، حدّ التكلفة قبل الإرسال، جدول الحملات بالحالات ودوائر النسب، أسباب الفشل، Retarget من 6 حالات، التصدير. **باقٍ:** عرض حدّ الإرسال اليومي (Messaging tier) من Meta · Reactions/Clicks منفصلة عن Replied · البث من Google Sheets (المرحلة 9).
> **✅ المرحلة 2 نُفّذت (2026-09-28):** تسجيل كل رسالة صادرة وتحديث حالاتها Sent/Delivered/Read/Failed وأنواع الفشل (Not in WhatsApp · Frequency limit · Unsubscribed · قالب · حدود المعدّل · الحساب). العرض في شاشات المرحلة 3.
| القدرة | الآن | المرحلة |
|---|---|---|
| إنشاء: اسم · قناة · جمهور (Segments/وسوم/رفع ملف) · قالب + تعبئة متغيّرات · الآن/جدولة | 🟡 إرسال فوري لكل المشتركين | 3 |
| **Smart Retry** (تلقائي حتى وقت محدد) / Manual retry + إحصاءاتها | ❌ | 3 |
| حدّ الإرسال اليومي (Messaging tier) ظاهر + سياسة Opt-in + إسناد الردود لموظف/فريق | ❌ | 3 |
| حالات: Sent · Delivered · Read · Delivered-not-replied · Replied · Failed · Unsubscribed · Frequency Limit · Not in WhatsApp | ❌ (لا معالجة `statuses`) | 2 |
| تفاعل: Replied · Reactions · Clicks · Form replied | ❌ | 2–3 |
| أنواع الفشل: رقم غير صالح · حظر الأعمال · قالب مرفوض · تجاوز الحدّ اليومي | ❌ | 2 |
| بطاقات ملخّص + جدول كل الحملات بدوائر النِسب + فلترة بالتاريخ | 🟡 | 3 |
| **Retargeting** من أي حالة (قرأ ولم يرد…) | ❌ | 3 |
| تصدير بيانات الحملة | ❌ | 3 |
| بثّ من Google Sheets | ❌ | 8 |

## 3) قوالب واتساب — المرحلة 4
> **✅ نُفّذت (2026-09-28):** Custom marketing/utility بترويسة نص/صورة/فيديو/موقع وتذييل STOP · Carousel · Limited Time Offer · Authentication (Copy code) · أزرار رد ×10 · رابط ×2 بمتغيّر · اتصال · نسخ كود · معاينة حيّة · مزامنة وحالة وجودة وسبب الرفض · نسخ · حذف · إرسال تجريبي — والبث يرسل كل ذلك. **باقٍ:** زر Form (7) · Product marketing (9) · Smart check وAI Rewrite · ترويسة مستند · One/Zero-tap.
| القدرة | الآن | المرحلة |
|---|---|---|
| Custom marketing (هيدر · جسم · Footer STOP · كوبون · أزرار) | 🟡 إنشاء أساسي | 4 |
| Custom utility + **Smart check** قبل الإرسال للاعتماد | 🟡 | 4 |
| **Carousel** (حتى 10 بطاقات صورة/فيديو) | ❌ | 4 |
| **Limited Time Offer** (عدّاد تنازلي + كود) | ❌ | 4 |
| Product marketing (الكتالوج/منتجات مختارة) | ❌ | 4 (+9) |
| Authentication (Zero-tap / One-tap / Copy code) | ❌ | 4 |
| أزرار: Quick reply · URL (2) · Phone (1) · Coupon (1) · Form | 🟡 | 4 |
| معاينة واتساب حيّة · مزامنة · نسخ · اختبار · توجيه ردود القالب لفلو | ❌ | 4 |

## 4) البوتات والفلو — المرحلة 5
> **✅ نُفّذ الأساس (2026-09-28):** قائمة فلوهات لكل بوت (مشغّل أي رسالة/كلمات/بداية · تفعيل · Sessions/Completed/Dropped/Handoff) · كانفس سحب وتوصيل بمسودة ونشر وتحقق كامل وتراجع · 17 بطاقة: نص · ملف · أزرار/قائمة · سؤال بتحقق (نص/رقم/بريد/هاتف/تاريخ/رابط) · طلب ملف · وسم · تحديث حقل جهة/الاسم/البريد · متغيّر · حفظ البيانات · تنبيه الفريق · هدف · تأخير · شرط · ساعات العمل · انتقال لفلو · تحويل لموظف · إنهاء — **وخريطة تسرّب على الكانفس**. **ثم (نفس اليوم):** Test on WhatsApp · موقع · قالب واتساب · رد بالذكاء (GPT) · API Call · Google Sheets · Assign · مهلة الرد والتذكير. **ثم:** منتجات الكتالوج (منتج/قائمة + الطلب) · Form (WhatsApp Flows) · صوت · Switch · Resolve. **خارج يدنا:** WhatsApp Payment (Meta لا تتيحه في مصر والسعودية).

| القدرة | الآن | المرحلة |
|---|---|---|
| قائمة فلوهات لكل بوت: المشغّلات · آخر نشر · Sessions · Completed · Dropped · الحالة | ❌ فلو واحد | 5 |
| كانفس سحب وإفلات + مسودة/نشر + «Test on WhatsApp» | ❌ خطّي | 5 |
| **Send**: Text · Media · WhatsApp Template · Products · Collection · Reply Buttons · List · Location · Form · WhatsApp Payment · Voice | 🟡 نص/أزرار/صورة | 5 |
| **Ask**: Text · Email · Number · Phone · Request Phone · Date · URL · Reply Buttons · List · Keyword Options · Collections List · Address · File · Location · Form — مع تحقّق وحفظ في متغيّر وتفريع | 🟡 سؤال/أزرار | 5 |
| **Action**: Resolve · Assign · Unassign · Update Contact/Company fields · Update order status/payment · Update conversation fields · Push to sequence | 🟡 handoff | 5 |
| **Flow control**: Condition · Switch · Set Variable · Goal · Delay · Jump To · API Call · Connector · Google Sheets · Business Hours · Wait for Order · Add Note & Mention | ❌ | 5 |
| AI nodes: GPT Dialog · GPT Knowledge Base | 🟡 «عقل البوت» | 5 |
| مهلة انتظار الرد لكل فلو + تذكير قبل الإسقاط + ما يحدث عند الانتهاء | ❌ | 5 |
| تحليلات البوت | 🟡 | 5 |

## 5) الصندوق المشترك (Inbox) — المرحلة 6
> **✅ نُفّذت (2026-09-28):** صندوق موحّد لكل القنوات · Team views (فِرق) + Mine + Unassigned + Mentions + Pending + Resolved · إسناد/إلغاء/استلام · حالة المحادثة وإغلاق وإعادة فتح تلقائية · Private notes و@Mentions · Canned responses بمتغيّرات · لوحة جهة الاتصال · فِرق Round-robin/يدوية · رؤية «ما يخصّني» · ساعات العمل ورسالة خارج الدوام · Auto-resolve · **Sequences** كاملة (يدوي/وسم/فلو · نص/قالب · توقّف بالرد وSTOP · ساعات إرسال · تحليلات وأسباب التوقّف). **باقٍ:** أدوار مخصّصة · Push notifications · حقول المحادثة · AI Reply كمسودة للموظف · 2FA.

| القدرة | الآن | المرحلة |
|---|---|---|
| صندوق موحّد واتساب/إنستجرام/ويب | 🟡 واتساب/تليجرام | 6 (+7) |
| **Team views** و Custom views · Unassigned · Mine | ❌ | 6 |
| إسناد/إلغاء إسناد · Resolve · حالة المحادثة | 🟡 وضع bot/human | 6 |
| Private notes · @Mentions · Push notifications · اختصارات لوحة المفاتيح | ❌ | 6 |
| Canned responses بمتغيّرات | ❌ | 6 |
| **AI Reply** (مسودة من المؤلّف يراجعها الموظف) | 🟡 | 6 |
| لوحة جهة الاتصال بجانب المحادثة + حقول المحادثة | ❌ | 6 |

## 6) الفريق والإعدادات — المرحلة 6
| القدرة | الآن | المرحلة |
|---|---|---|
| Users (نشط/دعوات/محذوف + استرجاع) | ✅ فريق الحساب | — |
| أدوار: Owner · Admin · Member · **Team Admin · Team Member** + **أدوار مخصّصة** | 🟡 owner/admin/member | 6 |
| **Teams** بقاعدة توزيع: Round-robin (الافتراضي) / Unassign | ❌ | 6 |
| Webhooks عامة · API Keys | ✅ | — |
| Activity log · **2FA** · أمان الحساب | 🟡 | 6 |

## 7) إعدادات القناة (Channel configuration) — المرحلة 6
Business hours · Away message · Welcome message · Auto reply · Agent fallback · Re-engagement message · Auto-resolve · Failed-message email alert · Marketing opt-out messages · Image visibility · AI reply · Conversation-initiation template — **🟡 الترحيب/STOP موجودان، والباقي ❌.**

## 8) التسلسلات (Sequences) — المرحلة 6
مشغّل (وسم/حقل/فلو/API) · خطوات قوالب بتأخير · شروط لكل خطوة · تفضيل وقت الإرسال · أهداف بدء/إيقاف · تحليلات — **❌**.

## 9) النمو والإعلانات — المرحلة 7
> **✅ نُفّذت (2026-09-28):** Link generator (روابط تتبّع بنقرات ومحادثات وإدخالات) + QR لكل رابط · Website widget (زر واتساب مخصّص + كود تضمين + قيد نطاقات) · **Web chat** بالبوت نفسه (فلوهات وذكاء وتحويل لموظف) + Ice breakers + تحويل لواتساب + إحصاءات الزيارات · **CTWA**: التقاط نقرات الإعلانات · تقرير لكل إعلان · مشغّل فلو للإعلان · **CAPI** (Purchase/Lead…) · Forms (المرحلة 5). **باقٍ:** إنفاق/وصول الإعلان من Marketing API (يحتاج ربط حساب الإعلانات).

| القدرة | الآن | المرحلة |
|---|---|---|
| WhatsApp QR · Link generator (Magic link) | 🟡 QR للبوت | 7 |
| **Website widget** (زر واتساب قابل للتخصيص + كود تضمين) | ❌ | 7 |
| **Web chat** بوكيل AI + Ice breakers/CTAs + تحليلات الزوار + التحويل لواتساب | 🟡 مساعد الموقع | 7 |
| **CTWA**: ربط حساب الإعلانات · أداء الإعلان (إنفاق/وصول/محادثات) · CTWA Leads · **CAPI** (إرسال التحويلات لـ Meta) · نافذة الإعلان المجانية | ❌ | 7 |
| Forms (WhatsApp Flows) | ❌ | 7 |

## 10) قنوات إضافية — المرحلة 8
| القدرة | الآن | ملاحظة صريحة |
|---|---|---|
| Instagram DMs + **أتمتة التعليقات** (منشورات ونوايا) | ✅ (2026-09-29) | DMs من قبل؛ التعليقات: كلمة ⇒ رد علني + رسالة خاصة، فيسبوك وإنستجرام، قاعدة لكل منشور. يحتاج صلاحيات التعليقات من Meta |
| **WhatsApp Coexistence** (تطبيق الأعمال + المنصة على نفس الرقم) | ✅ | Embedded Signup بوضع coexistence + ردود الموبايل تُسجَّل ويسكت البوت |
| WhatsApp Groups | ❌ | Groups API من Meta (محدود) — لم يُطلب |
| **WhatsApp Calling** وارد/صادر | ✅ (2026-09-29) | المكالمة ترنّ في الصندوق ويرد الموظف من المتصفح (WebRTC)، فائتة ⇒ رسالة. والصادر: طلب إذن الاتصال ثم زر «اتصال» من الصندوق. لم يُجرَّب على رقم حقيقي مفعّل عليه Calling |
| AI Voice (واتساب/هاتف) | ❌ | يحتاج مزوّد اتصالات + نموذج صوت — آخر الأولويات |

## 11) التجارة والمدفوعات — المرحلة 9
> **✅ نُفّذ (2026-09-29) — الدفع داخل المحادثة:** ربط بوابة صاحب النشاط (**Moyasar / Tap**، المال لحسابه مباشرة) · بطاقة «طلب دفع» في الفلو (المبلغ رقم أو متغيّر، زر «ادفع الآن»، الفلو ينتظر ويكمل من «دُفع» أو «لم يُدفع») · زر «طلب دفع» في الصندوق المشترك · تأكيد تلقائي (ويبهوك + صفحة عودة + «دفعت» + مسح دوري) وإيصال للعميل · تنبيه الفريق · حدث Purchase لـ Meta · صفحة المدفوعات (الحالات ومجاميع 30 يوماً). بطاقة «منتجات الكتالوج» وقراءة الطلب (🛒) من المرحلة 5. **HyperPay** (صفحة دفع عندنا، مدى بكيان منفصل). حالة الطلب من سلة/زد/Shopify عبر التكاملات.

Catalog · Orders · Wait for Order · حالة الطلب/الدفع · **WhatsApp Payments** (طلب دفع داخل المحادثة) — كان 🟡 (متجر تليجرام وتحصيل بالإيصال)؛ بوابات السعودية المقترحة: **Moyasar / Tap / HyperPay** بدل Razorpay/Cashfree الهندية.

## 12) التكاملات — المرحلة 9
> **✅ نُفّذ (2026-09-29):** صفحة «التكاملات» — **سلة · زد · Shopify · WooCommerce** (طلب جديد · دُفع · شُحن · اكتمل · أُلغي · سلة متروكة) و**Webhook عام** (Zapier · Make · محرك الحجز/PMS بأحداث مخصّصة مثل booking_confirmed ومتغيّرات حرّة). لكل حدث: قالب واتساب معتمد بمتغيّرات الطلب + وسوم + تسلسل متابعة، مع منع التكرار واحترام STOP والموافقة التسويقية، وسجل أحداث لكل تكامل. **Facebook Lead Ads** أصلياً (2026-09-29): نموذج إعلان فيسبوك/إنستجرام ⇒ قالب واتساب خلال ثوانٍ + جهة اتصال ووسوم وتسلسل، بقاعدة لكل نموذج. **مزامنة HubSpot و Zoho CRM** (2026-09-29): جهات الاتصال تلقائياً كل دقيقة + إجابات الفلو ملاحظاتٍ على العميل. و**باتجاهين** (تعديلات الـ CRM تصل جهات الاتصال) · **Google Sheets مصدراً** (كل صف جديد ⇒ واتساب). **باقٍ:** Conversation widget داخل CRM.

| عندهم | خطتنا |
|---|---|
| CRM: HubSpot · Zoho · Pipedrive · LeadSquared · Kylas · Odoo · Sangam | Webhooks + API (✅) ثم HubSpot/Zoho مباشرةً حسب طلب العميل |
| E-commerce: Shopify · WooCommerce · Shopflo (سلات متروكة) | Shopify/WooCommerce + **سلة/زد** (السوق السعودي) |
| أتمتة: Zapier · Pabbly · Make · Generic webhooks | Webhooks موجودة ← تطبيق Zapier/Make |
| Google Sheets · Calendly · Zoho Books · Facebook Leads | Google Sheets + Facebook Leads أولاً |
| Conversation widget (iFrame داخل CRM العميل) | 9 |

## 13) التحليلات — موزّعة
Conversation analytics (حجم · زمن الرد · الحلّ · القنوات · الوسوم · أداء الموظفين) · WhatsApp analytics (الفئات داخل/خارج النافذة) · Template analytics · Bot analytics · Failed messages · Notification messages · Conversation report (بحث/تصدير/إسناد) · Message reports (تصدير 30 يوماً) — 🟡 لدينا تقارير أسبوعية وتحليل محادثات.

## 14) الفوترة
| عندهم | خطتنا |
|---|---|
| باقات Basic/Essential/Advanced/Enterprise + مستخدم إضافي مدفوع | باقة Enterprise بمقاعد + مستخدم إضافي |
| **Message Credits** محفظة مسبقة + Rate card لكل دولة (USD) | أوضاع الفوترة الثلاثة (ENTERPRISE_PLAN) + جدول أسعار لكل رمز دولة |
| **AI Wallet** (رصيد شهري + شحن) | ✅ حصة AI + المحفظة (§29) |

## 15) خارج نطاق الكود (نقولها للعميل بصراحة)
SOC 2 Type II · On-prem/private cloud · SLA تعاقدي · SSO/SAML · IP whitelist — شهادات وبنية تحتية لا ميزات برمجية؛ نقدّم بدلها: تشفير التوكنات، CSP صارم، سجل نشاط، 2FA، نسخ احتياطي، واتفاقية معالجة بيانات.

## ما نتفوّق به (لا يوجد عندهم)
عربي أولاً RTL · **فلو كامل بالذكاء من وصف** · **قالب فنادق/عمرة** جاهز · خريطة التسرّب على الكانفس · تكلفة الحملة بعملة العميل قبل الإرسال · بوابات دفع سعودية · تكامل سلة/زد · تليجرام كقناة إضافية.
