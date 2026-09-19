"""شرائح التسويق: صفحة هبوط لكل نشاط (`/for/<code>`) + روابط إعلانات Click-to-WhatsApp /
Telegram تتبّع مصدرها + ترحيب مخصّص في بوت المنصة الرسمي + سياق للذكاء الاصطناعي.

الرابط هو الموافقة: العميل هو من يضغط الإعلان ويبدأ المحادثة (سياسة Meta)، والرمز
`#<code>` في الرسالة الأولى (واتساب) أو `?start=seg-<code>` (تليجرام) يقول من أي شريحة جاء
— فيُحتسب حدث `src_seg_<code>` في التحليلات ويرحّب البوت بلغة نشاطه.

**لا وعود غير حقيقية** (AGENTS.md §3.26): كل ما هنا وصف لما تفعله المنصة فعلاً — قوالب
المتجر والحجز والأسئلة الشائعة · عقل البوت · صندوق الوارد · البث · تحصيل المدفوعات.
لا أرقام عملاء ولا شهادات ولا نتائج مضمونة."""
import re

CODE_RE = re.compile(r"^[a-z]{2,15}$")

SEGMENTS = {
    "market": {
        "icon": "cart",
        "ar": {
            "name": "السوبر ماركت والبقالة",
            "h1": "زباينك يطلبوا من السوبر ماركت على واتساب — والبوت ياخد الأوردر",
            "sub": "بدل ما التليفون يرن طول اليوم: البوت يعرض المنتجات والأسعار، ياخد الأوردر بالعنوان، ويبعتهولك جاهز.",
            "pains": ["مكالمات وأوردرات بتضيع وقت الزحمة", "أسئلة متكررة عن الأسعار والتوصيل", "أوردرات مكتوبة غلط أو ناقصة"],
            "wins": ["متجر على الشات: منتجات بصورها وأسعارها", "أوردر كامل بالاسم والعنوان يوصلك فوراً", "رد ذكي على «عندكم كذا؟» و«بتوصلوا فين؟»", "عروض للمشتركين اللي وافقوا بضغطة"],
            "demo": [(True, "عندكم زيت ذرة 2 لتر؟ وبتوصلوا مدينة نصر؟"),
                     (False, "أيوه متوفر، وبنوصل مدينة نصر. تحب أضيفه للأوردر؟")],
            "welcome": "أهلاً بيك 👋 شايف إنك صاحب سوبر ماركت — BotYalla بيخلّي زباينك يطلبوا على واتساب والبوت ياخد الأوردر كامل ويبعتهولك.\nمحتاج إيه النهارده؟ 👇",
            "ai": "The customer owns a supermarket/grocery. Stress: store template (products, prices, orders with address), AI answers about availability and delivery, broadcasts to opted-in customers.",
        },
        "en": {
            "name": "Supermarkets & groceries",
            "h1": "Customers order from your supermarket on WhatsApp — the bot takes the order",
            "sub": "Instead of the phone ringing all day: the bot shows products and prices, takes the order with the address, and sends it to you ready.",
            "pains": ["Calls and orders lost at rush hour", "The same price and delivery questions", "Orders written down wrong or incomplete"],
            "wins": ["A store in the chat: products with photos and prices", "Complete orders with name and address, instantly", "Smart answers to “do you have…?” and “do you deliver to…?”", "One-tap offers to customers who opted in"],
            "demo": [(True, "Do you have 2L corn oil? Do you deliver to Nasr City?"),
                     (False, "Yes, in stock, and we deliver to Nasr City. Add it to your order?")],
            "welcome": "Welcome 👋 You run a supermarket — BotYalla lets your customers order on WhatsApp while the bot takes the full order for you.\nWhat do you need today? 👇",
        },
    },
    "gold": {
        "icon": "tag",
        "ar": {
            "name": "محلات الذهب والمجوهرات",
            "h1": "رد فوري على «سعر الجرام كام؟» — والزبون يحجز زيارته للمحل",
            "sub": "البوت يرد على أسئلة الموديلات والعيارات والمصنعية من معلوماتك، ويعرض صور القطع، ويحجز للزبون ميعاد يعدّي على المحل.",
            "pains": ["نفس السؤال عن السعر مئات المرات", "زباين بتسأل وتختفي من غير متابعة", "صور الموديلات متفرّقة على الموبايل"],
            "wins": ["كتالوج صور للموديلات داخل المحادثة", "حجز زيارة للمحل بالميعاد", "كل الأسئلة والعملاء في صندوق وارد واحد", "تحويل الزبون الجاد لك فوراً على تليجرام"],
            "demo": [(True, "عندكم دبل عيار 21؟ وممكن أشوف موديلات؟"),
                     (False, "أيوه متوفر 👌 دي أحدث الموديلات — تحب أحجزلك ميعاد تعدّي على المحل؟")],
            "welcome": "أهلاً بيك 👋 شايف إنك في تجارة الذهب والمجوهرات — BotYalla بيرد على زباينك فوراً ويعرض موديلاتك ويحجزلهم زيارة للمحل.\nمحتاج إيه النهارده؟ 👇",
            "ai": "The customer is a gold/jewelry trader. Stress: FAQ about karats and workmanship from their own info (never quote live gold prices yourself), product photos catalog, booking store visits, instant handoff for serious buyers. Price answers come from the owner's data only.",
        },
        "en": {
            "name": "Gold & jewelry shops",
            "h1": "Instant answers to “what's the price per gram?” — and customers book a store visit",
            "sub": "The bot answers questions on designs, karats and workmanship from your info, shows item photos, and books the customer a visit to your shop.",
            "pains": ["The same price question hundreds of times", "Customers who ask and vanish without follow-up", "Design photos scattered on your phone"],
            "wins": ["A photo catalog of designs inside the chat", "Store-visit bookings with a time", "All questions and customers in one inbox", "Serious buyers handed to you on Telegram instantly"],
            "demo": [(True, "Do you have 21K wedding bands? Can I see designs?"),
                     (False, "Yes, in stock 👌 Here are the latest designs — shall I book you a visit?")],
            "welcome": "Welcome 👋 You're in the gold & jewelry trade — BotYalla answers your customers instantly, shows your designs and books their store visits.\nWhat do you need today? 👇",
        },
    },
    "factory": {
        "icon": "truck",
        "ar": {
            "name": "المصانع والتوريدات",
            "h1": "طلبات عروض الأسعار توصلك منظّمة — من غير ما حد يرد على كل رسالة",
            "sub": "البوت يسأل العميل عن المنتج والكمية والمواصفات والمدينة، ويبعتلك طلب عرض سعر كامل، ويرد على الأسئلة الفنية المتكررة من معلوماتك.",
            "pains": ["استفسارات تجار ناقصة البيانات", "وقت المبيعات بيضيع في أسئلة متكررة", "طلبات بتضيع بين الواتساب والتليفون"],
            "wins": ["نموذج طلب عرض سعر كامل داخل الشات", "إجابات فنية عن المنتجات من ملفك", "كل الطلبات في لوحة واحدة وتصدير Excel/CSV", "تحويل الطلبات الكبيرة لمدير المبيعات فوراً"],
            "demo": [(True, "محتاج عرض سعر 500 كرتونة مقاس 40×30"),
                     (False, "تمام. الكرتون طبقتين ولا تلاتة؟ والتسليم في أي مدينة؟")],
            "welcome": "أهلاً بيك 👋 شايف إنك صاحب مصنع أو شركة توريدات — BotYalla بيجمع طلبات عروض الأسعار كاملة ويرد على الأسئلة الفنية بدل فريقك.\nمحتاج إيه النهارده؟ 👇",
            "ai": "The customer owns a factory/supplier. Stress: quote-request flows (product, quantity, specs, city), technical FAQ from their data, leads dashboard and export, handoff of big orders to sales.",
        },
        "en": {
            "name": "Factories & suppliers",
            "h1": "Quote requests arrive organised — without anyone answering every message",
            "sub": "The bot asks for product, quantity, specs and city, sends you a complete quote request, and answers recurring technical questions from your info.",
            "pains": ["Trader enquiries with missing details", "Sales time lost on repeated questions", "Requests lost between WhatsApp and phone"],
            "wins": ["A full quote-request form inside the chat", "Technical product answers from your file", "All requests in one dashboard, CSV export", "Big orders handed to your sales lead instantly"],
            "demo": [(True, "I need a quote for 500 boxes, 40×30"),
                     (False, "Sure. Double or triple wall? And delivery to which city?")],
            "welcome": "Welcome 👋 You run a factory or supply business — BotYalla collects complete quote requests and answers technical questions for your team.\nWhat do you need today? 👇",
        },
    },
    "company": {
        "icon": "users",
        "ar": {
            "name": "الشركات والخدمات",
            "h1": "خدمة عملاء شركتك شغّالة 24 ساعة — على واتساب وتليجرام",
            "sub": "البوت يرد على استفسارات العملاء من معلومات شركتك، يسجّل العملاء المحتملين، يفتح تذاكر الدعم، ويحوّل للموظف المناسب لما يلزم.",
            "pains": ["استفسارات بعد مواعيد العمل من غير رد", "فريق الدعم غرقان في نفس الأسئلة", "عملاء محتملين بيضيعوا من غير متابعة"],
            "wins": ["رد ذكي بالعامية من معلومات شركتك", "تسجيل العملاء المحتملين والتذاكر تلقائياً", "صندوق وارد واحد للفريق مع تولّي المحادثة", "حملات لعملائك الموافقين بقوالب Meta المعتمدة"],
            "demo": [(True, "عايز أعرف تفاصيل الخدمة والأسعار"),
                     (False, "أكيد 👌 قولي حجم شركتك وأنا أقولك الأنسب ليك في رسالة واحدة.")],
            "welcome": "أهلاً بيك 👋 BotYalla بيشغّل خدمة عملاء شركتك 24 ساعة على واتساب وتليجرام — يرد ويسجّل العملاء ويحوّل للموظف لما يلزم.\nمحتاج إيه النهارده؟ 👇",
            "ai": "The customer owns a company/service business. Stress: 24/7 AI customer service from their data, lead capture, support tickets, team inbox with takeover, template campaigns to opted-in customers.",
        },
        "en": {
            "name": "Companies & services",
            "h1": "Your company's customer service, running 24/7 — on WhatsApp and Telegram",
            "sub": "The bot answers customers from your company info, captures leads, opens support tickets, and hands off to the right person when needed.",
            "pains": ["After-hours enquiries go unanswered", "Support drowning in the same questions", "Leads lost without follow-up"],
            "wins": ["Smart replies in dialect from your company info", "Leads and tickets captured automatically", "One team inbox with conversation takeover", "Campaigns to opted-in customers with approved Meta templates"],
            "demo": [(True, "I'd like details on your service and pricing"),
                     (False, "Sure 👌 Tell me your company size and I'll suggest the best fit in one message.")],
            "welcome": "Welcome 👋 BotYalla runs your company's customer service 24/7 on WhatsApp and Telegram — it answers, captures leads and hands off when needed.\nWhat do you need today? 👇",
        },
    },
    "center": {
        "icon": "calendar",
        "ar": {
            "name": "المراكز والعيادات",
            "h1": "الحجز بقى من الشات — والمواعيد منظّمة من غير سكرتارية طول اليوم",
            "sub": "لمراكز التدريب والتجميل والعيادات والجيم: البوت يعرض الخدمات، يحجز الميعاد المتاح، يفكّر العميل، ويرد على الأسئلة المتكررة.",
            "pains": ["تليفون الحجز مشغول دايماً", "مواعيد بتتكرر أو بتتنسي", "نفس الأسئلة عن الأسعار والعناوين"],
            "wins": ["حجز مواعيد داخل الشات بأيام وساعات عملك", "إشعار فوري لك بكل حجز جديد", "رد ذكي عن الخدمات والأسعار والعنوان", "كل الحجوزات في لوحة واحدة"],
            "demo": [(True, "عايز أحجز كشف يوم الخميس"),
                     (False, "تمام 👌 المتاح الخميس: 5:00 أو 6:30 — تختار أنهي ميعاد؟")],
            "welcome": "أهلاً بيك 👋 شايف إنك صاحب مركز أو عيادة — BotYalla بيحجز المواعيد من الشات ويرد على أسئلة عملائك 24 ساعة.\nمحتاج إيه النهارده؟ 👇",
            "ai": "The customer owns a center/clinic/gym/salon. Stress: booking template with working days and hours, instant booking alerts, AI answers about services, prices and location from their data. No medical advice.",
        },
        "en": {
            "name": "Centers & clinics",
            "h1": "Bookings happen in the chat — organised, without a receptionist all day",
            "sub": "For training centers, salons, clinics and gyms: the bot shows services, books an available slot, and answers recurring questions.",
            "pains": ["The booking line is always busy", "Double-booked or forgotten appointments", "The same questions on prices and location"],
            "wins": ["In-chat bookings on your working days and hours", "Instant alert to you for every booking", "Smart answers on services, prices and address", "All bookings in one dashboard"],
            "demo": [(True, "I'd like to book on Thursday"),
                     (False, "Sure 👌 Thursday has 5:00 or 6:30 — which one?")],
            "welcome": "Welcome 👋 You run a center or clinic — BotYalla books appointments in the chat and answers your customers 24/7.\nWhat do you need today? 👇",
        },
    },
    "brand": {
        "icon": "bag",
        "ar": {
            "name": "البراندات والمتاجر الأونلاين",
            "h1": "رسايل الإعلانات تتحوّل أوردرات — البوت يبيع وأنت نايم",
            "sub": "كل رسالة من إعلاناتك يرد عليها البوت فوراً: المقاسات والألوان والأسعار، ويقفل الأوردر بالعنوان — وتحصيل فودافون كاش وانستاباي كإضافة.",
            "pains": ["رسايل الإعلانات بتستنى ساعات فتضيع", "سؤال «المقاس ده متاح؟» مليون مرة", "أوردرات بتتقفل من غير بيانات كاملة"],
            "wins": ["رد فوري على رسايل الإعلانات 24 ساعة", "كتالوج بالصور والأسعار والمقاسات", "أوردر كامل بالعنوان يوصلك فوراً", "تحصيل فودافون كاش وانستاباي (إضافة لبوت المتجر)"],
            "demo": [(True, "الهودي الأسود متاح مقاس L؟ وبكام؟"),
                     (False, "متاح L 👌 سعره في الكتالوج تحت — أكمّلك الأوردر؟")],
            "welcome": "أهلاً بيك 👋 شايف إنك صاحب براند أو متجر أونلاين — BotYalla بيرد على رسايل إعلاناتك فوراً ويقفل الأوردر بالعنوان.\nمحتاج إيه النهارده؟ 👇",
            "ai": "The customer owns a brand/online store. Stress: instant replies to ad messages 24/7, catalog with sizes/colors/prices, complete orders with address, Vodafone Cash / InstaPay collection add-on for Telegram store bots.",
        },
        "en": {
            "name": "Brands & online stores",
            "h1": "Ad messages turn into orders — the bot sells while you sleep",
            "sub": "Every message from your ads gets an instant reply: sizes, colors and prices, then the order is closed with the address — with Vodafone Cash & InstaPay collection as an add-on.",
            "pains": ["Ad messages wait hours and go cold", "“Is this size available?” a million times", "Orders closed without complete details"],
            "wins": ["Instant 24/7 replies to ad messages", "A catalog with photos, prices and sizes", "Complete orders with address, instantly", "Vodafone Cash & InstaPay collection (store bot add-on)"],
            "demo": [(True, "Is the black hoodie available in L? How much?"),
                     (False, "L is available 👌 The price is in the catalog below — shall I complete your order?")],
            "welcome": "Welcome 👋 You run a brand or online store — BotYalla replies to your ad messages instantly and closes the order with the address.\nWhat do you need today? 👇",
        },
    },
}
ORDER = ("market", "gold", "factory", "company", "center", "brand")
_TAG = re.compile(r"(?:#|seg-)([a-z]{2,15})\b")


def get(code):
    return SEGMENTS.get(code) if isinstance(code, str) and CODE_RE.fullmatch(code) else None


def text(code, lang="ar"):
    """نصوص الشريحة باللغة المطلوبة (الإنجليزية ترث حقل ai من العربية)."""
    s = get(code)
    if not s:
        return None
    base = dict(s["ar"])
    if lang == "en":
        base.update(s["en"])
    return base


def code_in(text_):
    """رمز الشريحة من رسالة بداية («مرحبا #market» · «/start seg-market») — أو None."""
    m = _TAG.search((text_ or "").lower())
    return m.group(1) if m and m.group(1) in SEGMENTS else None


def wa_text(code, lang="ar"):
    """النص المكتوب مسبقاً في رابط واتساب: كلمة بدء + الرمز (يُطابقه `WhatsAppChannel._one`)."""
    return f"{'مرحبا' if lang == 'ar' else 'hello'} #{code}"
