"""BotYalla — النصوص القانونية (شروط · خصوصية · استرداد · استخدام مقبول).

نصوص طويلة لا مفاتيح واجهة، فهي هنا لا في i18n.py. كل وثيقة: عنوان ومقدمة
وأقسام، وكل قسم فقرات (نص) أو قوائم (list). العناصر النائبة تُملأ عند العرض:
    {email} · {whatsapp} · {updated} · {site}

⚠️ هذه صياغة تشغيلية مبنية على ما تفعله المنصة فعلاً (راجع AGENTS.md). ليست
استشارة قانونية — راجعها مع محامٍ قبل الإطلاق العام، خصوصاً ما يخص قانون حماية
البيانات الشخصية رقم 151 لسنة 2020 ولائحته التنفيذية (قرار 816 لسنة 2025).
"""

ORDER = ("terms", "privacy", "refund", "aup")

DOCS = {
# ============================================================================
"terms": {
 "title": {"ar": "شروط الاستخدام", "en": "Terms of Service"},
 "intro": {
  "ar": "تحكم هذه الشروط استخدامك لمنصة BotYalla. بإنشائك حساباً أو استخدامك للمنصة فإنك توافق عليها، فاقرأها بعناية. إن كنت لا توافق على أي جزء منها فلا تستخدم المنصة.",
  "en": "These terms govern your use of BotYalla. By creating an account or using the platform you agree to them, so please read them carefully. If you do not agree with any part, do not use the platform."},
 "sections": [
  {"id": "definitions", "h": {"ar": "1. التعريفات والقبول", "en": "1. Definitions and acceptance"},
   "body": {
    "ar": ["«المنصة» أو «الخدمة»: BotYalla وموقعها {site} وكل ما تتيحه من أدوات. «نحن»: يوسف الشريف (Youssef Alsherief)، مشغّل المنصة. «أنت» أو «العميل»: صاحب الحساب. «العميل النهائي»: كل من يتواصل مع بوتك.",
           "يجب أن يكون عمرك 18 عاماً على الأقل وأن تتمتع بالأهلية القانونية للتعاقد، وأن تستخدم المنصة لأغراض نشاطك التجاري أو المهني."],
    "en": ["“Platform” or “Service”: BotYalla, its website {site}, and every tool it provides. “We”: Youssef Alsherief, the operator of the platform. “You” or “Customer”: the account holder. “End customer”: anyone who communicates with your bot.",
           "You must be at least 18 and legally able to enter into contracts, and you must use the platform for your business or professional purposes."]}},
  {"id": "service", "h": {"ar": "2. وصف الخدمة", "en": "2. The service"},
   "body": {
    "ar": ["تتيح المنصة إنشاء بوتات محادثة وإدارتها على تليجرام، وعلى واتساب عبر WhatsApp Cloud API الرسمي من Meta، دون برمجة: باني محادثات، قوالب جاهزة، إعداد بمساعدة الذكاء الاصطناعي، استقبال الطلبات والحجوزات وبيانات العملاء، حملات، وتحليلات.",
           ["بوت تليجرام تنشئه بضغطة عبر ميزة Managed Bots الرسمية من تليجرام — يطلب منك تليجرام نفسه تأكيد الإنشاء، والبوت ملكك في تليجرام وتشغّله المنصة بتوكنه — أو تنشئه يدوياً من BotFather وتربط توكنه. لا نطلب أبداً رقمك أو رمز الدخول لحسابك في تليجرام.",
            "قناة واتساب تتطلب حساب Meta Business ورقماً مخصصاً لنشاطك، وقد تطلب Meta مستندات مثل السجل التجاري والبطاقة الضريبية. قبول Meta لحسابك قرارها وحدها.",
            "تعمل المنصة فوق خدمات أطراف ثالثة (تليجرام، Meta، مزوّدي الذكاء الاصطناعي). أي تغيير أو قيد تفرضه هذه الأطراف قد يؤثر على الخدمة دون أن يكون لنا تحكم فيه."]],
    "en": ["The platform lets you build and manage chatbots on Telegram, and on WhatsApp through Meta’s official WhatsApp Cloud API, without code: a conversation builder, ready-made templates, AI-assisted setup, orders, bookings and customer data, campaigns, and analytics.",
           ["You create a Telegram bot in one tap through Telegram’s official Managed Bots feature — Telegram itself asks you to confirm, the bot is yours on Telegram and the platform runs it with its token — or manually through BotFather and connect its token. We never ask for your Telegram number or login code.",
            "The WhatsApp channel requires a Meta Business account and a number dedicated to your business; Meta may require documents such as a commercial register and tax card. Whether Meta accepts your account is Meta’s decision alone.",
            "The platform runs on third-party services (Telegram, Meta, AI providers). Any change or restriction they impose may affect the service without our control."]]}},
  {"id": "account", "h": {"ar": "3. الحساب والأمان", "en": "3. Your account and security"},
   "body": {
    "ar": ["أنت مسؤول عن صحة بياناتك وعن سرية كلمة مرورك وعن كل ما يحدث من خلال حسابك. أضف بريداً إلكترونياً صحيحاً ليمكنك استرجاع حسابك. أبلغنا فوراً عن أي استخدام غير مصرّح به.",
           "يحق لنا تعليق الحساب مؤقتاً إن رصدنا نشاطاً يهدد أمنك أو أمن المنصة أو غيرك من العملاء."],
    "en": ["You are responsible for the accuracy of your details, the secrecy of your password, and everything done through your account. Add a valid email so you can recover your account. Tell us immediately about any unauthorised use.",
           "We may temporarily suspend an account if we detect activity that threatens you, the platform, or other customers."]}},
  {"id": "plans", "h": {"ar": "4. الباقات والدفع والتجديد", "en": "4. Plans, payment and renewal"},
   "body": {
    "ar": ["الأسعار بالجنيه المصري وتظهر في صفحة الأسعار، ويحسبها الخادم وحده عند الدفع. الدفع بالوسائل المحلية المتاحة (فودافون كاش، انستاباي، تحويل بنكي) مع رفع إثبات الدفع، ويُفعَّل الاشتراك بعد مراجعته والموافقة عليه.",
           ["الاشتراك الشهري 30 يوماً، والسنوي 365 يوماً من تاريخ التفعيل.",
            "لا يوجد أي خصم أو تجديد تلقائي: التجديد يحدث فقط حين تدفع بنفسك، ونرسل لك تذكيراً قبل الانتهاء.",
            "التجديد المبكر على نفس الباقة يُضاف إلى المدة المتبقية ولا يلغيها.",
            "عند الانتقال إلى باقة مختلفة تتحوّل قيمة الأيام المدفوعة المتبقية إلى أيام في الباقة الجديدة: قيمة المتبقي بسعر ما دفعته فعلاً عن اليوم، مقسومةً على السعر اليومي للباقة الجديدة. يظهر لك الرقم التقديري قبل الدفع.",
            "أكواد الخصم تخضع لشروطها (المدة، عدد الاستخدامات، الباقات المشمولة) وتُستهلك عند اعتماد الدفعة فقط.",
            "تغيير الأسعار لا يسري على مدة دفعت ثمنها بالفعل.",
            "عقل البوت (AI Brain) ميزة تسحب من رصيد ردود منفصل خاص بباقتك، وتتطلب تفعيلك الصريح لها."]],
    "en": ["Prices are in Egyptian pounds, shown on the pricing page, and computed by our server alone at checkout. You pay through the available local methods (Vodafone Cash, InstaPay, bank transfer) and upload proof of payment; the subscription is activated after we review and approve it.",
           ["A monthly subscription lasts 30 days and an annual one 365 days from activation.",
            "There is no automatic charge or renewal of any kind: renewal happens only when you pay yourself, and we remind you before expiry.",
            "Renewing the same plan early is added to the remaining period, not lost.",
            "When you move to a different plan, the value of your remaining paid days becomes days on the new plan: the remaining value at the rate you actually paid per day, divided by the new plan’s daily rate. You see the estimate before paying.",
            "Promo codes are subject to their own conditions (validity, number of uses, eligible plans) and are only consumed when a payment is approved.",
            "Price changes never apply to a period you have already paid for.",
            "The AI Brain feature consumes a separate replies allowance based on your plan, and requires your explicit activation."]]}},
  {"id": "wallet", "h": {"ar": "5. الرسائل التسويقية ورصيد المحفظة", "en": "5. Marketing messages and wallet credit"},
   "body": {
    "ar": ["Meta تحاسب على كل رسالة تسويقية على واتساب، لذلك لا تدخل الرسائل التسويقية في أي باقة: تُخصم من رصيد مسبق الدفع بالسعر المعلن للرسالة وقت الإرسال.",
           ["تُعرض تكلفة الحملة قبل تأكيد إرسالها، وفئة القالب (تسويقي أو خدمي) تُقرأ من Meta لا مما تدخله أنت.",
            "يُخصم ثمن الرسائل التي وصلت فعلاً فقط؛ ما فشل إرساله أو لم يُرسل يُردّ إلى رصيدك تلقائياً بنفس السعر.",
            "يُشحن الرصيد بنفس مسار الدفع والمراجعة، ولا يدرّ عائداً ولا يُحوَّل لحساب آخر.",
            "قد نعدّل سعر الرسالة تبعاً لأسعار Meta وسعر الصرف، ويسري السعر الجديد على الإرسال اللاحق فقط."]],
    "en": ["Meta charges for every WhatsApp marketing message, so marketing messages are not included in any plan: they are paid from prepaid credit at the published per-message price at the time of sending.",
           ["A campaign’s cost is shown before you confirm it, and the template category (marketing or utility) is read from Meta, not from what you enter.",
            "Only delivered messages are paid for; anything that failed or was not sent is refunded to your credit automatically at the same price.",
            "Credit is topped up through the same payment and review process, earns no interest, and cannot be transferred to another account.",
            "We may adjust the per-message price with Meta’s rates and the exchange rate; a new price applies only to later sends."]]}},
  {"id": "limits", "h": {"ar": "6. حدود الباقات والاستخدام العادل", "en": "6. Plan limits and fair use"},
   "body": {
    "ar": ["لكل باقة حدودها المعلنة (عدد البوتات، رسائل الخدمة الشهرية على واتساب، ملفات الوسائط). عند بلوغ الحد يتوقف الجزء المعني حتى بداية الشهر التالي أو حتى الترقية. ويحق لنا الحد من أي استخدام يثقل الخادم على حساب باقي العملاء."],
    "en": ["Every plan has published limits (number of bots, monthly WhatsApp service messages, media files). When a limit is reached, that part pauses until the next month or an upgrade. We may limit any use that overloads the server at other customers’ expense."]}},
  {"id": "use", "h": {"ar": "7. الاستخدام المقبول ومسؤولية المحتوى", "en": "7. Acceptable use and your content"},
   "body": {
    "ar": ["تلتزم بسياسة الاستخدام المقبول وبشروط تليجرام وسياسات واتساب للأعمال. أنت المسؤول عن محتوى بوتاتك ورسائلك، وعن الحصول على موافقة عملائك قبل مراسلتهم تسويقياً، وعن صحة ما تبيعه أو تقدمه عبرها."],
    "en": ["You must follow our Acceptable Use Policy, Telegram’s terms, and WhatsApp’s business policies. You are responsible for your bots’ content and messages, for obtaining your customers’ consent before marketing to them, and for what you sell or offer through them."]}},
  {"id": "data", "h": {"ar": "8. بيانات عملائك", "en": "8. Your customers’ data"},
   "body": {
    "ar": ["بالنسبة لبيانات عملائك النهائيين (الرسائل، الطلبات، الحجوزات، أرقام التواصل، الوسائط) أنت المتحكم فيها ونحن نعالجها نيابةً عنك ولغرض تشغيل بوتك فقط، كما تبيّن سياسة الخصوصية. يلزمك أن يكون لك أساس قانوني لجمعها وأن تُعلم عملاءك بذلك. يمكنك تصدير هذه البيانات أو حذفها من لوحتك."],
    "en": ["For your end customers’ data (messages, orders, bookings, contact numbers, media) you are the controller and we process it on your behalf, solely to run your bot, as the Privacy Policy explains. You must have a legal basis to collect it and inform your customers. You can export or delete this data from your dashboard."]}},
  {"id": "ip", "h": {"ar": "9. الملكية الفكرية", "en": "9. Intellectual property"},
   "body": {
    "ar": ["المنصة وعلامتها وتصميمها وكودها ملك لنا. محتواك ملك لك، وتمنحنا ترخيصاً محدوداً لاستضافته ومعالجته بالقدر اللازم لتقديم الخدمة لك فقط."],
    "en": ["The platform, its brand, design and code belong to us. Your content belongs to you; you grant us a limited licence to host and process it only as needed to provide the service to you."]}},
  {"id": "availability", "h": {"ar": "10. التوفر والتغييرات", "en": "10. Availability and changes"},
   "body": {
    "ar": ["نبذل جهداً معقولاً لإبقاء الخدمة متاحة، لكننا لا نضمن عملها دون انقطاع؛ قد تتوقف للصيانة أو لأسباب خارجة عن إرادتنا. قد نطوّر الميزات أو نغيّرها، ولن نسحب ميزة مدفوعة من مدة دفعت ثمنها دون تعويض عادل."],
    "en": ["We make reasonable efforts to keep the service available but do not guarantee uninterrupted operation; it may pause for maintenance or reasons beyond our control. We may improve or change features, and we will not remove a paid feature from a period you paid for without fair compensation."]}},
  {"id": "liability", "h": {"ar": "11. إخلاء المسؤولية وحدودها", "en": "11. Disclaimer and limitation of liability"},
   "body": {
    "ar": ["تُقدَّم الخدمة «كما هي». وفي الحدود التي يسمح بها القانون: لا نتحمل الأضرار غير المباشرة أو التبعية أو فوات الربح، ولا المسؤولية عن إجراءات تتخذها تليجرام أو Meta تجاه حسابك أو رقمك بسبب طريقة استخدامك، ولا يتجاوز إجمالي مسؤوليتنا ما دفعته لنا خلال الأشهر الثلاثة السابقة للمطالبة. لا يخلّ ذلك بأي حق لا يجوز التنازل عنه قانوناً."],
    "en": ["The service is provided “as is”. To the extent the law allows: we are not liable for indirect or consequential damages or lost profits, nor for actions Telegram or Meta take against your account or number because of how you used them, and our total liability does not exceed what you paid us in the three months before the claim. Nothing here limits any right that cannot be waived by law."]}},
  {"id": "termination", "h": {"ar": "12. الإيقاف وإنهاء الحساب", "en": "12. Suspension and termination"},
   "body": {
    "ar": ["يمكنك التوقف عن الاستخدام في أي وقت، ولحذف حسابك راسلنا. يحق لنا تعليق بوت أو حملة أو حساب أو إنهاؤه عند مخالفة هذه الشروط أو سياسة الاستخدام المقبول، أو عند الاحتيال، أو بأمر من جهة مختصة. بعد الإنهاء نتيح تصدير بياناتك لمدة 30 يوماً ثم نحذفها، عدا ما يلزمنا القانون بالاحتفاظ به."],
    "en": ["You may stop using the service at any time; to delete your account, contact us. We may suspend or terminate a bot, campaign or account for breach of these terms or the Acceptable Use Policy, fraud, or an order from a competent authority. After termination we allow you to export your data for 30 days and then delete it, except what the law requires us to keep."]}},
  {"id": "changes", "h": {"ar": "13. تعديل الشروط", "en": "13. Changes to these terms"},
   "body": {
    "ar": ["سنُعلمك بأي تعديل جوهري عبر المنصة أو البريد الإلكتروني قبل سريانه بـ14 يوماً على الأقل. استمرارك في الاستخدام بعد السريان يعني قبولك للتعديل."],
    "en": ["We will tell you about any material change through the platform or by email at least 14 days before it takes effect. Continuing to use the service after that means you accept the change."]}},
  {"id": "law", "h": {"ar": "14. القانون الواجب التطبيق", "en": "14. Governing law"},
   "body": {
    "ar": ["تخضع هذه الشروط لقوانين جمهورية مصر العربية. نسعى أولاً لحل أي خلاف ودياً، فإن تعذّر يُحال إلى المحاكم المصرية المختصة."],
    "en": ["These terms are governed by the laws of the Arab Republic of Egypt. We will first try to resolve any dispute amicably; failing that, it goes to the competent Egyptian courts."]}},
  {"id": "contact", "h": {"ar": "15. التواصل", "en": "15. Contact"},
   "body": {
    "ar": ["لأي سؤال عن هذه الشروط: {email} · واتساب {whatsapp}."],
    "en": ["For any question about these terms: {email} · WhatsApp {whatsapp}."]}},
 ]},

# ============================================================================
"privacy": {
 "title": {"ar": "سياسة الخصوصية", "en": "Privacy Policy"},
 "intro": {
  "ar": "نوضح هنا ما البيانات التي نجمعها، ولماذا، ومع من نشاركها، وكم نحتفظ بها، وكيف تمارس حقوقك وفق قانون حماية البيانات الشخصية المصري رقم 151 لسنة 2020. نجمع أقل قدر يلزم لتقديم الخدمة، ولا نبيع بياناتك لأحد.",
  "en": "This explains what data we collect, why, who we share it with, how long we keep it, and how to exercise your rights under Egypt’s Personal Data Protection Law No. 151 of 2020. We collect the minimum needed to provide the service, and we never sell your data."},
 "sections": [
  {"id": "who", "h": {"ar": "1. من نحن", "en": "1. Who we are"},
   "body": {
    "ar": ["المتحكم في البيانات هو يوسف الشريف (Youssef Alsherief)، مشغّل منصة BotYalla ({site}). للتواصل في كل ما يخص بياناتك: {email}."],
    "en": ["The data controller is Youssef Alsherief, operator of BotYalla ({site}). For anything about your data: {email}."]}},
  {"id": "collect", "h": {"ar": "2. البيانات التي نجمعها", "en": "2. What we collect"},
   "body": {
    "ar": [["بيانات الحساب: اسم المستخدم، البريد الإلكتروني ورقم الهاتف (وحالة تأكيدهما)، السن، نوع الحساب (فرد · شركة · مؤسسة)، كلمة المرور مخزّنة مشفّرة لا نصاً، تفضيل اللغة. ولو سجّلت بجوجل أو فيسبوك: معرّف حسابك لديهما وبريدك واسمك فقط — لا نرى كلمة مرورك عندهما ولا ننشر شيئاً باسمك.",
            "بيانات الدفع: الباقة والدورة والمبلغ، وسيلة الدفع ورقمها المرجعي، صورة إيصال التحويل، ونتيجة الفحص الآلي للإيصال. لا نجمع أي بيانات بطاقات بنكية.",
            "بيانات البوتات: الإعدادات والنصوص والقوالب، وتوكن البوت اللازم لتشغيله.",
            "بيانات عملائك النهائيين: ما يرسلونه لبوتك (رسائل، طلبات، حجوزات، أسماء، أرقام تواصل، صور، رسائل صوتية).",
            "بيانات تقنية: عنوان IP ومسار الطلب ووقته ورسائل الأخطاء في سجلات الخادم.",
            "مراسلاتك معنا عبر البريد أو واتساب."]],
    "en": [["Account data: username, email and phone number (and whether they are verified), age, account type (individual · company · institution), your password stored hashed never in plain text, language preference. If you sign up with Google or Facebook: only your account ID there, your email and your name — we never see your password there and never post on your behalf.",
            "Payment data: plan, cycle and amount, payment method and reference, the transfer receipt image, and the result of the automatic receipt check. We never collect bank card data.",
            "Bot data: settings, texts and templates, and the bot token needed to run it.",
            "Your end customers’ data: what they send your bot (messages, orders, bookings, names, contact numbers, images, voice notes).",
            "Technical data: IP address, request path and time, and error messages in server logs.",
            "Your correspondence with us by email or WhatsApp."]]}},
  {"id": "role", "h": {"ar": "3. دورنا في بيانات عملائك", "en": "3. Our role for your customers’ data"},
   "body": {
    "ar": ["في بيانات عملائك النهائيين أنت المتحكم ونحن معالج نيابةً عنك: نعالجها لتشغيل بوتك وعرضها لك فقط، ولا نستخدمها لأي غرض آخر ولا نراسل عملاءك من تلقاء أنفسنا. يلزمك إعلامهم بجمع بياناتهم والحصول على موافقتهم حيث يشترطها القانون.",
           "إن فعّلت الرد بالذكاء الاصطناعي («هجين» أو «عقل البوت») فيلزمك إعلام عملائك أن الردود آلية وقد تخطئ. لا يُفعَّل إلا بموافقتك الصريحة، ويمكنك إيقافه والعودة للفلو في أي وقت، والتدخّل في أي محادثة والرد بنفسك من صندوق الوارد."],
    "en": ["For your end customers’ data you are the controller and we are a processor acting for you: we process it only to run your bot and show it to you, never for any other purpose, and we never contact your customers on our own. You must inform them and obtain their consent where the law requires it.",
           "If you enable AI replies (“Hybrid” or “AI Brain”), you must tell your customers that replies are automated and may be wrong. It is only enabled with your explicit consent, you can switch back to the flow at any time, and you can step into any conversation and reply yourself from the inbox."]}},
  {"id": "purposes", "h": {"ar": "4. لماذا نستخدمها", "en": "4. Why we use it"},
   "body": {
    "ar": [["تقديم الخدمة وتشغيل بوتاتك وتنفيذ اشتراكك — لتنفيذ العقد بيننا.",
            "مراجعة المدفوعات وحفظ السجلات المحاسبية — التزاماً قانونياً.",
            "حماية المنصة ومنع الاحتيال والإساءة وتحديد المحاولات — مصلحة مشروعة.",
            "رسائل تشغيلية بالبريد (استرجاع كلمة المرور، إيصالات الدفع، الترحيب، تذكير انتهاء الاشتراك، ردود الدعم) وإشعارات خدمة مهمة (تغيير في الشروط أو صيانة). لا نرسل أخباراً أو عروضاً إلا لمن وافق صراحةً عند التسجيل أو من صفحة «حسابي»، وفي كل رسالة منها رابط إلغاء بضغطة واحدة."]],
    "en": [["Providing the service, running your bots and fulfilling your subscription — to perform our contract.",
            "Reviewing payments and keeping accounting records — a legal obligation.",
            "Protecting the platform, preventing fraud and abuse, rate limiting — a legitimate interest.",
            "Operational emails (password reset, payment receipts, welcome, expiry reminders, support replies) and important service notices (changes to the terms, maintenance). We send news and offers only if you opt in — at signup or on your Account page — and every such email has a one-click unsubscribe link."]]}},
  {"id": "sharing", "h": {"ar": "5. مع من نشاركها", "en": "5. Who we share it with"},
   "body": {
    "ar": ["لا نبيع بياناتك ولا نؤجرها. نشاركها فقط مع من يلزم لتشغيل الخدمة:",
           ["تليجرام — لتشغيل بوتاتك عبر Bot API، ولتأكيد رقم هاتفك لو اخترت مشاركته مع بوت المنصة.",
            "جوجل وفيسبوك — فقط لو اخترت الدخول بأيٍّ منهما: يرسلان لنا معرّف حسابك وبريدك واسمك لتسجيل دخولك.",
            "Meta (واتساب) — لإرسال رسائل بوتك واستقبالها عبر WhatsApp Cloud API.",
            "مزوّدو الذكاء الاصطناعي (Google Gemini أو Groq) — حين تستخدم الإعداد بالذكاء الاصطناعي (نرسل وصف نشاطك)، أو حين تفعّل ميزة «عقل البوت» (تُرسل رسائل عملائك ليتمكن من الرد عليها).",
            "مزوّد الاستضافة الذي يعمل عليه الخادم، ومزوّد البريد الإلكتروني الذي يوصل رسائلنا إليك.",
            "Google Fonts — يُحمَّل منه خط الموقع، فيصل عنوان IP الخاص بك إلى Google عند التحميل.",
            "الجهات المختصة — إذا ألزمنا القانون أو أمر قضائي بذلك."]],
    "en": ["We do not sell or rent your data. We share it only with those needed to run the service:",
           ["Telegram — to run your bots through the Bot API, and to verify your phone number if you choose to share it with the platform bot.",
            "Google and Facebook — only if you choose to sign in with one of them: they send us your account ID, email and name to sign you in.",
            "Meta (WhatsApp) — to send and receive your bot’s messages through the WhatsApp Cloud API.",
            "AI providers (Google Gemini or Groq) — when you use AI setup (we send your business description), or when you enable the 'AI Brain' feature (we send your customers' messages so the AI can answer them).",
            "The hosting provider running our server, and the email provider that delivers our emails to you.",
            "Google Fonts — the site’s font loads from it, so your IP address reaches Google when it loads.",
            "Competent authorities — where the law or a court order requires it."]]}},
  {"id": "transfers", "h": {"ar": "6. النقل خارج مصر", "en": "6. Transfers outside Egypt"},
   "body": {
    "ar": ["بعض هذه الجهات (تليجرام، Meta، مزوّدو الذكاء الاصطناعي، وقد يكون مزوّد الاستضافة) تعالج البيانات خارج مصر. نلتزم في ذلك بالشروط التي يقررها القانون ولائحته التنفيذية، بما فيها التراخيص والموافقات المطلوبة."],
    "en": ["Some of these parties (Telegram, Meta, AI providers, and possibly the hosting provider) process data outside Egypt. We follow the conditions set by the law and its executive regulations for such transfers, including any required licences and consent."]}},
  {"id": "retention", "h": {"ar": "7. مدة الاحتفاظ", "en": "7. How long we keep it"},
   "body": {
    "ar": [["بيانات الحساب والبوتات: طوال بقاء الحساب، وتُحذف خلال 30 يوماً من طلب الحذف أو إنهاء الحساب.",
            "سجلات المدفوعات وإيصالاتها: 5 سنوات، وهي المدة التي تقتضيها السجلات المحاسبية والضريبية.",
            "بيانات عملائك النهائيين: حتى تحذفها أنت أو يُحذف البوت أو الحساب. الوسائط التي لم ترتبط بطلب مكتمل أو محادثة تُحذف تلقائياً بعد 7 أيام.",
            "رسائل المحادثات في صندوق الوارد: 12 شهراً من تاريخ كل رسالة ثم تُحذف تلقائياً.",
            "صورك وفيديوهاتك في مكتبة الوسائط: حتى تحذفها أنت أو يُحذف الحساب.",
            "روابط استرجاع كلمة المرور: ساعة واحدة وتُستخدم مرة واحدة، ونخزّن تجزئتها لا الرابط نفسه.",
            "سجلات الخادم: ملفات دوّارة بحجم محدود تُستبدل تلقائياً، وعادةً لا تتجاوز أسابيع.",
            "النسخ الاحتياطية: 14 يوماً ثم تُحذف."]],
    "en": [["Account and bot data: for as long as the account exists, deleted within 30 days of a deletion request or account termination.",
            "Payment records and receipts: 5 years, as accounting and tax records require.",
            "Your end customers’ data: until you delete it or the bot or account is deleted. Media not attached to a completed request or a conversation is deleted automatically after 7 days.",
            "Inbox conversation messages: 12 months from each message, then deleted automatically.",
            "Your photos and videos in the media library: until you delete them or the account is deleted.",
            "Password reset links: one hour, single use; we store only a hash of the link.",
            "Server logs: size-capped rotating files replaced automatically, usually within weeks.",
            "Backups: 14 days, then deleted."]]}},
  {"id": "security", "h": {"ar": "8. كيف نحميها", "en": "8. How we protect it"},
   "body": {
    "ar": [["اتصال مشفّر (HTTPS)، وكلمات مرور مخزّنة بتجزئة أحادية الاتجاه.",
            "صلاحيات تُقرأ من قاعدة البيانات في كل طلب، وكل صاحب نشاط يرى بيانات بوتاته فقط.",
            "إيصالات الدفع ووسائط العملاء خارج الملفات العامة ولا تُعرض إلا لمن يملكها.",
            "تغيير كلمة المرور يُخرج كل الجلسات الأخرى تلقائياً.",
            "حماية من تزوير الطلبات (CSRF) وسياسة أمان محتوى (CSP) وتحديد للمحاولات.",
            "نسخ احتياطي يومي يُفحص سلامته فور أخذه."]],
    "en": [["Encrypted connections (HTTPS), and passwords stored with a one-way hash.",
            "Permissions read from the database on every request; each business sees only its own bots’ data.",
            "Payment receipts and customer media are kept outside public files and shown only to their owner.",
            "Changing your password signs out every other session automatically.",
            "Protection against request forgery (CSRF), a Content Security Policy, and rate limiting.",
            "Daily backups whose integrity is checked as soon as they are taken."]]}},
  {"id": "rights", "h": {"ar": "9. حقوقك", "en": "9. Your rights"},
   "body": {
    "ar": ["يكفل لك القانون رقم 151 لسنة 2020:",
           ["العلم بالبيانات التي نحتفظ بها عنك والاطلاع عليها والحصول على نسخة منها.",
            "تصحيحها أو تحديثها أو استكمالها.",
            "محوها أو حجبها متى انتهى الغرض منها.",
            "العدول عن موافقتك في أي وقت.",
            "تقييد المعالجة في نطاق محدد، والاعتراض على ما يخالف حقوقك.",
            "العلم بأي خرق يمس بياناتك."],
           "يمكنك تعديل بياناتك الأساسية من صفحة «حسابي»، ولممارسة باقي الحقوق راسلنا على {email} — قد نطلب ما يثبت هويتك قبل التنفيذ حمايةً لك. ويحق لك تقديم شكوى إلى مركز حماية البيانات الشخصية."],
    "en": ["Law No. 151 of 2020 gives you the right to:",
           ["Know what data we hold about you, access it and obtain a copy.",
            "Correct, update or complete it.",
            "Have it erased or blocked once its purpose has ended.",
            "Withdraw your consent at any time.",
            "Restrict processing to a specific scope and object to processing that breaches your rights.",
            "Be informed of any breach affecting your data."],
           "You can edit your basic details on the Account page; for the other rights write to {email}. We may ask you to prove your identity first, to protect you. You also have the right to complain to the Personal Data Protection Centre."]}},
  {"id": "cookies", "h": {"ar": "10. ملفات تعريف الارتباط", "en": "10. Cookies"},
   "body": {
    "ar": ["نستخدم كوكي جلسة واحداً ضرورياً فقط: يُبقيك مسجّل الدخول ويحفظ لغتك ورمز الحماية من تزوير الطلبات. لا نستخدم كوكيز تحليلات أو تتبّع أو إعلانات."],
    "en": ["We use a single, strictly necessary session cookie: it keeps you signed in and stores your language and anti-forgery token. We use no analytics, tracking or advertising cookies."]}},
  {"id": "children", "h": {"ar": "11. الأطفال", "en": "11. Children"},
   "body": {
    "ar": ["المنصة موجهة لأصحاب الأنشطة وليست لمن هم دون 18 عاماً، ولا نجمع بياناتهم عن علم. إن كان بوتك يخاطب أطفالاً فأنت مسؤول عن الحصول على موافقة أولياء أمورهم."],
    "en": ["The platform is for businesses and not for anyone under 18; we do not knowingly collect their data. If your bot addresses children, you are responsible for obtaining their guardians’ consent."]}},
  {"id": "breach", "h": {"ar": "12. خرق البيانات", "en": "12. Data breaches"},
   "body": {
    "ar": ["إذا وقع خرق يمس بياناتك نُخطر مركز حماية البيانات الشخصية خلال 72 ساعة من علمنا به كما يقرر القانون، ونُخطرك دون تأخير غير مبرر بما حدث وما اتخذناه من إجراءات."],
    "en": ["If a breach affects your data we notify the Personal Data Protection Centre within 72 hours of becoming aware of it, as the law requires, and tell you without undue delay what happened and what we have done."]}},
  {"id": "changes", "h": {"ar": "13. تعديل السياسة", "en": "13. Changes to this policy"},
   "body": {
    "ar": ["نُعلمك بأي تعديل جوهري عبر المنصة أو البريد قبل سريانه، ويظهر تاريخ آخر تحديث أعلى الصفحة."],
    "en": ["We tell you about any material change through the platform or by email before it takes effect; the last-updated date appears at the top of this page."]}},
  {"id": "contact", "h": {"ar": "14. التواصل", "en": "14. Contact"},
   "body": {
    "ar": ["لأي طلب أو سؤال عن بياناتك: {email} · واتساب {whatsapp}."],
    "en": ["For any request or question about your data: {email} · WhatsApp {whatsapp}."]}},
 ]},

# ============================================================================
"refund": {
 "title": {"ar": "سياسة الاسترداد", "en": "Refund Policy"},
 "intro": {
  "ar": "الدفع على BotYalla يدوي بالوسائل المحلية، ولا يوجد أي خصم تلقائي إطلاقاً. توضح هذه السياسة متى تسترد أموالك وكيف.",
  "en": "Payment on BotYalla is manual through local methods, and there is never any automatic charge. This policy explains when and how you get your money back."},
 "sections": [
  {"id": "before", "h": {"ar": "1. قبل تفعيل الاشتراك", "en": "1. Before activation"},
   "body": {
    "ar": [["إذا لم نتمكن من اعتماد دفعتك (مبلغ غير مطابق أو إيصال غير واضح) وثبت وصول المبلغ إلينا، نعيده كاملاً بنفس وسيلة الدفع خلال 7 أيام عمل من طلبك، أو نعتمده بعد استكمال الناقص إن فضّلت.",
            "الدفع المكرر بالخطأ يُعاد كاملاً، أو يُضاف كمدة أو رصيد حسب اختيارك."]],
    "en": [["If we cannot approve your payment (mismatched amount or unclear receipt) and the money is confirmed as received, we return it in full through the same method within 7 business days of your request, or approve it once the missing part is completed if you prefer.",
            "An accidental duplicate payment is refunded in full, or added as time or credit, as you choose."]]}},
  {"id": "after", "h": {"ar": "2. بعد التفعيل", "en": "2. After activation"},
   "body": {
    "ar": [["لا نسترد نقداً قيمة مدة اشتراك بدأت، لأن الخدمة تكون متاحة لك طوالها.",
            "لكن قيمة ما دفعته لا تضيع: الانتقال إلى باقة أخرى ينقل قيمة الأيام المتبقية إليها، والتجديد المبكر يُضاف إلى المتبقي.",
            "إذا توقفت الخدمة بالكامل بسبب من جانبنا أكثر من 72 ساعة متصلة، نعوّضك بتمديد اشتراكك بمدة مساوية، أو برد قيمة تلك المدة إن طلبت."]],
    "en": [["We do not refund in cash a subscription period that has started, because the service is available to you throughout it.",
            "But what you paid is not lost: moving to another plan carries the value of your remaining days over, and renewing early is added to the remaining time.",
            "If the service is fully unavailable for more than 72 consecutive hours because of us, we extend your subscription by the same period, or refund that period’s value if you ask."]]}},
  {"id": "wallet", "h": {"ar": "3. رصيد الرسائل التسويقية", "en": "3. Marketing message credit"},
   "body": {
    "ar": [["الرسائل التي لم تصل تُردّ قيمتها إلى رصيدك تلقائياً فور انتهاء الحملة.",
            "خطأ الشحن (مبلغ مختلف أو شحن مكرر) يُصحّح أو يُعاد.",
            "الرصيد غير المستخدم لا يُسترد نقداً، إلا إذا أوقفنا نحن قناة واتساب أو أنهينا حسابك دون مخالفة منك، فنعيد الرصيد المتبقي كاملاً."]],
    "en": [["The value of undelivered messages returns to your credit automatically when the campaign finishes.",
            "A top-up error (different amount or duplicate top-up) is corrected or refunded.",
            "Unused credit is not refunded in cash, unless we discontinue the WhatsApp channel or terminate your account without any breach on your part, in which case we refund the remaining credit in full."]]}},
  {"id": "how", "h": {"ar": "4. كيف تطلب الاسترداد", "en": "4. How to request a refund"},
   "body": {
    "ar": ["راسلنا على {email} أو واتساب {whatsapp} برقم الدفعة ووسيلة الدفع ورقمها المرجعي. نرد خلال 3 أيام عمل، ونُنفّذ الاسترداد المستحق خلال 7 أيام عمل من الموافقة."],
    "en": ["Write to {email} or WhatsApp {whatsapp} with the payment number, method and reference. We reply within 3 business days and complete any refund due within 7 business days of approval."]}},
  {"id": "exceptions", "h": {"ar": "5. حالات لا استرداد فيها", "en": "5. When no refund applies"},
   "body": {
    "ar": ["لا يُسترد ما دُفع عن حساب أُنهي بسبب احتيال أو مخالفة لسياسة الاستخدام المقبول. ولا يخلّ شيء في هذه السياسة بحقوقك التي يقررها قانون حماية المستهلك رقم 181 لسنة 2018."],
    "en": ["Nothing is refunded for an account terminated for fraud or breach of the Acceptable Use Policy. Nothing in this policy limits your rights under Consumer Protection Law No. 181 of 2018."]}},
 ]},

# ============================================================================
"aup": {
 "title": {"ar": "سياسة الاستخدام المقبول", "en": "Acceptable Use Policy"},
 "intro": {
  "ar": "بوتك يتحدث باسم نشاطك مع أناس حقيقيين. هذه القواعد تحمي عملاءك وتحمي رقمك وحسابك من الحظر لدى تليجرام وMeta، وتحمي باقي عملاء المنصة.",
  "en": "Your bot speaks for your business to real people. These rules protect your customers, keep your number and account from being banned by Telegram and Meta, and protect every other customer of the platform."},
 "sections": [
  {"id": "prohibited", "h": {"ar": "1. محظور تماماً", "en": "1. Strictly prohibited"},
   "body": {
    "ar": [["الرسائل المزعجة، ومراسلة أي شخص تسويقياً دون موافقته المسبقة.",
            "بيع أو ترويج ما يجرّمه القانون: المخدرات، الأسلحة، البضائع المقلدة، القمار، أو أي نشاط غير مرخّص.",
            "الاحتيال والتصيّد، وطلب كلمات المرور أو أكواد التحقق أو بيانات البطاقات البنكية أو الأرقام القومية عبر البوت.",
            "انتحال صفة شخص أو جهة أو علامة تجارية.",
            "المحتوى الإباحي، أو المحرّض على الكراهية أو العنف، أو المسيء أو التحرش.",
            "نشر برمجيات خبيثة أو روابط ضارة، أو التعدي على حقوق الملكية الفكرية للغير.",
            "محاولة تجاوز حدود الباقات أو أنظمة الحماية، أو إرهاق الخادم عمداً، أو جمع بيانات المنصة آلياً."]],
    "en": [["Spam, and sending marketing messages to anyone without their prior consent.",
            "Selling or promoting anything illegal: drugs, weapons, counterfeit goods, gambling, or any unlicensed activity.",
            "Fraud and phishing, and asking for passwords, verification codes, bank card details or national ID numbers through a bot.",
            "Impersonating a person, organisation or brand.",
            "Pornographic content, content inciting hatred or violence, abuse or harassment.",
            "Spreading malware or harmful links, or infringing others’ intellectual property.",
            "Trying to bypass plan limits or security controls, deliberately overloading the server, or scraping the platform."]]}},
  {"id": "whatsapp", "h": {"ar": "2. قواعد واتساب", "en": "2. WhatsApp rules"},
   "body": {
    "ar": [["الالتزام بسياسة WhatsApp Business Messaging وسياسة التجارة لدى Meta.",
            "مراسلة من وافق على تلقي رسائلك فقط، واحترام طلب التوقف فوراً.",
            "خارج نافذة الـ24 ساعة لا تُرسل إلا قوالب اعتمدتها Meta — والمنصة تفرض ذلك تلقائياً.",
            "انخفاض تقييم جودة رقمك لدى Meta قد يقيّد إرسالك؛ الشكاوى المتكررة من عملائك تعرّض رقمك للحظر."]],
    "en": [["Follow Meta’s WhatsApp Business Messaging Policy and Commerce Policy.",
            "Message only people who agreed to hear from you, and honour stop requests immediately.",
            "Outside the 24-hour window, send only Meta-approved templates — the platform enforces this automatically.",
            "A drop in your number’s quality rating at Meta can restrict sending; repeated complaints from customers put your number at risk of a ban."]]}},
  {"id": "telegram", "h": {"ar": "3. قواعد تليجرام", "en": "3. Telegram rules"},
   "body": {
    "ar": ["الالتزام بشروط خدمة تليجرام وقواعد منصة البوتات لديه. البوت لا يبدأ محادثة مع أحد لم يتواصل معه أولاً، ولا يُستخدم للرسائل الجماعية المزعجة."],
    "en": ["Follow Telegram’s Terms of Service and Bot Platform rules. A bot never starts a conversation with someone who has not contacted it first, and is never used for bulk spam."]}},
  {"id": "marketing", "h": {"ar": "4. الحملات التسويقية المسؤولة", "en": "4. Responsible campaigns"},
   "body": {
    "ar": [["عرّف باسم نشاطك بوضوح في كل رسالة.",
            "اجعل إيقاف الرسائل سهلاً وواضحاً.",
            "لا تُكثر من الإرسال — الرسالة المفيدة في وقتها أنجح من عشر رسائل مزعجة."]],
    "en": [["Identify your business clearly in every message.",
            "Make stopping messages easy and obvious.",
            "Don’t over-send — one useful message at the right time beats ten annoying ones."]]}},
  {"id": "enforcement", "h": {"ar": "5. ماذا نفعل عند المخالفة", "en": "5. What we do about violations"},
   "body": {
    "ar": ["حسب جسامة المخالفة: تنبيه، أو إيقاف بوت أو حملة، أو تعليق الحساب أو إنهاؤه، مع التعاون مع الجهات المختصة حين يلزم القانون. قد نزيل محتوى مخالفاً دون إشعار مسبق إذا كان يسبب ضرراً فورياً."],
    "en": ["Depending on severity: a warning, stopping a bot or campaign, or suspending or terminating the account, cooperating with authorities where the law requires. We may remove violating content without notice if it causes immediate harm."]}},
  {"id": "report", "h": {"ar": "6. الإبلاغ عن إساءة", "en": "6. Reporting abuse"},
   "body": {
    "ar": ["إذا صادفت بوتاً يعمل على منصتنا ويخالف هذه السياسة، أبلغنا على {email} مع اسم البوت ووصف المخالفة."],
    "en": ["If you come across a bot on our platform that breaks this policy, report it to {email} with the bot’s name and a description."]}},
 ]},
}


def _pick(v, lang):
    return v.get(lang) or v.get("ar") if isinstance(v, dict) else v


def title(doc, lang="ar"):
    return _pick(DOCS[doc]["title"], lang)


def render(doc, lang="ar", ctx=None):
    """الوثيقة جاهزة للعرض بلغة واحدة والعناصر النائبة مملوءة.
    يرجّع {id, title, intro, updated, sections:[{id, h, body:[str | [str]]}]}."""
    ctx = ctx or {}

    def fill(s):
        for k, v in ctx.items():
            s = s.replace("{" + k + "}", str(v))
        return s

    d = DOCS[doc]
    return {
        "id": doc,
        "title": fill(_pick(d["title"], lang)),
        "intro": fill(_pick(d["intro"], lang)),
        "updated": ctx.get("updated", ""),
        "sections": [
            {"id": s["id"], "h": fill(_pick(s["h"], lang)),
             "body": [[fill(x) for x in b] if isinstance(b, list) else fill(b)
                      for b in _pick(s["body"], lang)]}
            for s in d["sections"]
        ],
    }
