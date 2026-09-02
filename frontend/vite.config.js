import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// مدخلان: صفحة الهبوط، ولوحة التحكم (كل صفحات المنصة).
// أسماء ثابتة داخل static/dist ليقدّمها Flask مباشرة بلا manifest.
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
        chunkFileNames: "chunk-[name].js",
        // كلا المدخلين يشتركان في نفس CSS → ملف واحد باسم ثابت
        assetFileNames: (info) =>
          (info.names || [info.name]).some((n) => n && n.endsWith(".css"))
            ? "style.css"
            : "[name].[ext]",
      },
    },
  },
});
