# BotYalla — الواجهة (React)

كل واجهة المنصة صارت **React 19 + Vite 8 + Tailwind v4 + Motion 13**.
الخادم يبقى Flask + Jinja: هو المسؤول عن التوجيه والصلاحيات والنماذج،
و React مسؤول عن الرسم فقط.

## المعمارية: جزر React لا SPA

- Flask يرسم قالباً واحداً (`templates_web/react_app.html`) يحمل `data-view`
  وحمولة `window.BY`، ثم `console.js` يركّب المكوّن المناسب.
- **النماذج تبقى `POST` حقيقية إلى Flask** مع `csrf_token` مخفي
  (المكوّن `<Form>` في `src/app/kit.jsx`). لا API جديدة، ولا تغيير
  في CSRF أو الأدوار أو منطق الدفع.
- ما يحتاج تفاعلاً فورياً فقط يستخدم `fetch` مع ترويسة `X-CSRF-Token`
  (التحقق من التوكن · ضبط الـ AI · رابط الأدمن · الرسوم البيانية).

## البناء

```bash
cd frontend
npm install        # أول مرة فقط
npm run build      # يُخرج static/dist/
```

`npm run watch` يعيد البناء تلقائياً أثناء التطوير.

المخرجات في `static/dist/`:

| الملف | الاستخدام |
|---|---|
| `landing.js` | صفحة الهبوط `/landing` |
| `console.js` | كل صفحات اللوحة |
| `chunk-src.js` | React + Motion (مشترك بين المدخلين) |
| `style.css` | Tailwind (مشترك) |

## مهم قبل النشر

`static/dist/` هو ما يقدّمه Flask فعلياً — **شغّل `npm run build` قبل أي نشر**
بعد أي تعديل في `frontend/src`. لا يوجد بناء على السيرفر، فارفع `static/dist/`
إلى Git.

## النصوص

لا نصّ مكتوب داخل React. كل الترجمات تُحقن من `i18n.py` عبر `app.react_page()`
في `window.BY.t` — فالعربي/الإنجليزي من نفس مصدر بقية المنصة.

## البنية

```
src/
  main.jsx            مدخل صفحة الهبوط
  console-main.jsx    مدخل اللوحة (خريطة view ← مكوّن)
  index.css           توكنز Tailwind + المرافق (زجاج/شفق/حبيبات)
  ui.jsx, sections.jsx, LiveDemo.jsx      صفحة الهبوط
  app/
    kit.jsx           عناصر مشتركة (Card/Btn/Field/Table/Form/Stat…)
    AppShell.jsx      الشريط الجانبي + العلوي + الدرج + الإشعارات
    views/            صفحة لكل عرض
```
