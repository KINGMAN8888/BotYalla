import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// مدخلان: صفحة الهبوط، ولوحة التحكم (كل صفحات المنصة).
// المدخلان وstyle.css بأسماء ثابتة تُطلب دائماً بإصدار ?v=<تاريخ التعديل> (static_v في
// app.py)، والقطع المشتركة بـ hash في الاسم — فيصحّ لـ nginx تخزينها سنة كاملة
// (immutable): أي تغيير يعني رابطاً جديداً، ولا يعلق زائر على نسخة قديمة.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  build: {
    outDir: "../static/dist",
    emptyOutDir: true,
    target: "es2022",
    rollupOptions: {
      input: {
        landing: "src/main.jsx",
        console: "src/console-main.jsx",
      },
      output: {
        format: "es",
        entryFileNames: "[name].js",
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
