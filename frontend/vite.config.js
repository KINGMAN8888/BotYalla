import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// مدخلان: صفحة الهبوط، ولوحة التحكم (كل صفحات المنصة).
// كل JS بـ hash في اسمه (المدخلان أيضاً) وFlask يأخذ الاسم الفعلي من manifest (dist_entry
// في app.py) — لا ?v= على المدخل: قطع العروض تستورد المدخل باسمه المجرّد، ولو اختلف
// الرابط عمّا طلبته الصفحة لنفّذه المتصفح مرتين (وحدتان مختلفتان). style.css وحده باسم
// ثابت بإصدار ?v=<تاريخ التعديل>. فيصحّ لـ nginx تخزين الكل سنة كاملة (immutable).
export default defineConfig({
  plugins: [react(), tailwindcss()],
  // روابط القطع نسبية لملف JS نفسه (/static/dist/) لا لجذر الموقع — وإلا طلب محمّل العروض
  // /style.css و/chunk-*.js (404) فانهار العرض.
  base: "./",
  build: {
    // CSS واحد مشترك (style.css) تحمّله الصفحة نفسها بـ ?v= — لا يُنسب لقطع العروض، وإلا طلبه
    // محمّلها ثانيةً برابط بلا إصدار يعلق في ذاكرة nginx الطويلة فيغلب أنماط النشر الجديد.
    cssCodeSplit: false,
    outDir: "../static/dist",
    emptyOutDir: true,
    target: "es2022",
    // dist/.vite/manifest.json: منه يعرف Flask القطع المشتركة لكل مدخل فيطلبها مبكراً
    // (<link rel="modulepreload">) بالتوازي مع المدخل بدل انتظار تحليله أولاً.
    manifest: true,
    rollupOptions: {
      input: {
        landing: "src/main.jsx",
        console: "src/console-main.jsx",
      },
      output: {
        format: "es",
        entryFileNames: "[name]-[hash].js",
        chunkFileNames: "chunk-[name]-[hash].js",
        // كلا المدخلين يشتركان في نفس CSS → ملف واحد باسم ثابت
        assetFileNames: (info) =>
          (info.names || [info.name]).some((n) => n && n.endsWith(".css"))
            ? "style.css"
            : "[name]-[hash][extname]",
      },
    },
  },
});
