import { useEffect, useRef } from "react";
import { useReducedMotion } from "motion/react";

/* ============================================================================
   الخلفية التفاعلية.

   ثلاث طبقات فوق بعضها:
   1) كانفاس: كُرات ضوء تنجرف في حقل تدفّق وتتفاعل مع المؤشّر (تنفر منه).
   2) شبكة هندسية تضيء حول المؤشّر فقط — تُكشف بقناع شعاعي يتبعه.
   3) حبيبات فيلمية ثابتة تكسر نعومة التدرّجات.

   المواضع مكتوبة كـ inline styles لا كأدوات Tailwind: النسخة السابقة استعملت
   `-inset-x-[10%]` فلم تُطبَّق أبداً وانهارت الطبقة إلى 0×0 ولم يظهر شيء.
   ========================================================================== */

const ORBS = [
  { h: 262, s: 0.42, r: 0.42 },   // بنفسجي
  { h: 190, s: 0.30, r: 0.34 },   // سماوي
  { h: 168, s: 0.20, r: 0.38 },   // أخضر مائي
  { h: 275, s: 0.16, r: 0.26 },
  { h: 200, s: 0.14, r: 0.22 },
];

export default function Backdrop({ dense = true }) {
  const canvasRef = useRef(null);
  const glowRef = useRef(null);
  const reduce = useReducedMotion();

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d", { alpha: true });
    if (!ctx) return;

    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    let w = 0, h = 0, raf = 0, running = true;
    const pointer = { x: -9999, y: -9999, tx: -9999, ty: -9999, active: false };

    // حالة كل كُرة: موضع، سرعة، طور للتذبذب
    const orbs = ORBS.slice(0, dense ? ORBS.length : 3).map((o, i) => ({
      ...o,
      x: Math.random(), y: Math.random(),
      vx: (Math.random() - 0.5) * 0.00016,
      vy: (Math.random() - 0.5) * 0.00016,
      ph: Math.random() * Math.PI * 2,
      ox: 0, oy: 0,               // إزاحة ناتجة عن المؤشّر
      seed: i,
    }));

    function resize() {
      w = canvas.clientWidth; h = canvas.clientHeight;
      canvas.width = Math.round(w * dpr);
      canvas.height = Math.round(h * dpr);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    }

    function paint(t) {
      ctx.clearRect(0, 0, w, h);
      ctx.globalCompositeOperation = "lighter";   // مزج جمعي: الضوء يتراكم

      // المؤشّر يتبع بسلاسة (lerp) بدل القفز
      pointer.x += (pointer.tx - pointer.x) * 0.06;
      pointer.y += (pointer.ty - pointer.y) * 0.06;

      for (const o of orbs) {
        // انجراف بطيء + تذبذب جيبي يمنع المسار الخطّي الميكانيكي
        o.x += o.vx; o.y += o.vy;
        if (o.x < -0.25 || o.x > 1.25) o.vx *= -1;
        if (o.y < -0.25 || o.y > 1.25) o.vy *= -1;

        const wobX = Math.sin(t * 0.00007 + o.ph) * 0.05;
        const wobY = Math.cos(t * 0.00009 + o.ph * 1.4) * 0.05;

        let cx = (o.x + wobX) * w;
        let cy = (o.y + wobY) * h;

        // نفور من المؤشّر — كلما اقترب دفعها أبعد
        if (pointer.active) {
          const dx = cx - pointer.x, dy = cy - pointer.y;
          const d2 = dx * dx + dy * dy;
          const R = Math.min(w, h) * 0.55;
          if (d2 < R * R) {
            const d = Math.max(Math.sqrt(d2), 1);
            const push = (1 - d / R) * 90;
            o.ox += ((dx / d) * push - o.ox) * 0.08;
            o.oy += ((dy / d) * push - o.oy) * 0.08;
          } else {
            o.ox += (0 - o.ox) * 0.05;
            o.oy += (0 - o.oy) * 0.05;
          }
        } else {
          o.ox += (0 - o.ox) * 0.05;
          o.oy += (0 - o.oy) * 0.05;
        }
        cx += o.ox; cy += o.oy;

        const rad = o.r * Math.max(w, h);
        const g = ctx.createRadialGradient(cx, cy, 0, cx, cy, rad);
        g.addColorStop(0, `hsla(${o.h}, 90%, 62%, ${o.s})`);
        g.addColorStop(0.45, `hsla(${o.h}, 90%, 56%, ${o.s * 0.28})`);
        g.addColorStop(1, `hsla(${o.h}, 90%, 50%, 0)`);
        ctx.fillStyle = g;
        ctx.beginPath();
        ctx.arc(cx, cy, rad, 0, Math.PI * 2);
        ctx.fill();
      }
      ctx.globalCompositeOperation = "source-over";
    }

    function frame(t) {
      if (!running) return;
      paint(t);
      raf = requestAnimationFrame(frame);
    }

    function onMove(e) {
      pointer.tx = e.clientX; pointer.ty = e.clientY; pointer.active = true;
      // قناع الشبكة يتبع المؤشّر عبر متغيّرات CSS
      const gl = glowRef.current;
      if (gl) {
        gl.style.setProperty("--px", e.clientX + "px");
        gl.style.setProperty("--py", e.clientY + "px");
        gl.style.opacity = "1";
      }
    }
    function onLeave() {
      pointer.active = false;
      if (glowRef.current) glowRef.current.style.opacity = "0";
    }
    // أوقف الرسم عندما تكون الصفحة مخفية — لا نحرق بطارية بلا داعٍ
    function onVis() {
      if (document.hidden) { running = false; cancelAnimationFrame(raf); }
      else if (!reduce) { running = true; raf = requestAnimationFrame(frame); }
    }

    resize();
    const ro = new ResizeObserver(() => { resize(); paint(performance.now()); });
    ro.observe(canvas);

    // ارسم إطاراً أولاً **بشكل متزامن**، لا عبر requestAnimationFrame.
    // لو كان التبويب مخفياً أو الحلقة مخنوقة فلن يُستدعى rAF إطلاقاً،
    // وكانت الخلفية تبقى سوداء تماماً. الآن هي موجودة قبل أي حركة.
    paint(performance.now());

    if (!reduce) {
      raf = requestAnimationFrame(frame);
      window.addEventListener("pointermove", onMove, { passive: true });
      window.addEventListener("pointerleave", onLeave, { passive: true });
      document.addEventListener("visibilitychange", onVis);
    }

    return () => {
      running = false;
      cancelAnimationFrame(raf);
      ro.disconnect();
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerleave", onLeave);
      document.removeEventListener("visibilitychange", onVis);
    };
  }, [reduce, dense]);

  const fixed = { position: "fixed", inset: 0, pointerEvents: "none" };

  return (
    <>
      {/* 1) حقل الضوء المتفاعل */}
      <canvas ref={canvasRef} aria-hidden="true"
              style={{ ...fixed, zIndex: -40, width: "100%", height: "100%" }} />

      {/* 2) شبكة تضيء حول المؤشّر فقط */}
      <div ref={glowRef} aria-hidden="true"
           style={{
             ...fixed, zIndex: -30, opacity: 0,
             transition: "opacity .6s cubic-bezier(.16,1,.3,1)",
             backgroundImage:
               "linear-gradient(to right, rgba(255,255,255,.10) 1px, transparent 1px)," +
               "linear-gradient(to bottom, rgba(255,255,255,.10) 1px, transparent 1px)",
             backgroundSize: "54px 54px",
             WebkitMaskImage:
               "radial-gradient(260px circle at var(--px,50%) var(--py,50%), #000 0%, transparent 70%)",
             maskImage:
               "radial-gradient(260px circle at var(--px,50%) var(--py,50%), #000 0%, transparent 70%)",
           }} />

      {/* 3) شبكة خافتة ثابتة تعطي إحساس منتج هندسي */}
      <div aria-hidden="true"
           style={{
             ...fixed, zIndex: -25,
             backgroundImage:
               "linear-gradient(to right, rgba(255,255,255,.022) 1px, transparent 1px)," +
               "linear-gradient(to bottom, rgba(255,255,255,.022) 1px, transparent 1px)",
             backgroundSize: "54px 54px",
             WebkitMaskImage: "radial-gradient(ellipse 85% 55% at 50% 0%, #000 15%, transparent 75%)",
             maskImage: "radial-gradient(ellipse 85% 55% at 50% 0%, #000 15%, transparent 75%)",
           }} />

      {/* 4) حبيبات فيلمية */}
      <div aria-hidden="true" className="grain"
           style={{ ...fixed, zIndex: -20, opacity: 0.15 }} />

      {/* 5) تعتيم سفلي يثبّت النص فوق الضوء */}
      <div aria-hidden="true"
           style={{
             ...fixed, zIndex: -15,
             background: "linear-gradient(180deg, transparent 0%, rgba(5,7,13,.35) 55%, rgba(5,7,13,.8) 100%)",
           }} />
    </>
  );
}
