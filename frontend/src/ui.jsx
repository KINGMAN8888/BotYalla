import { useRef, useEffect, useState, useCallback } from "react";
import { motion, useInView, useReducedMotion, animate } from "motion/react";

/* البيانات كلها تأتي من الخادم (i18n.py) — لا نصّ مكتوب داخل الكود */
export const BY = window.BY || { t: {}, urls: {}, icons: {}, demos: [], lang: "ar", dir: "rtl" };
export const t = (k) => (BY.t[k] != null ? BY.t[k] : k);
export const isRTL = BY.dir === "rtl";

/* ---------------------------------------------------------------- أيقونة */
export function Icon({ name, size = 18, className = "" }) {
  const svg = BY.icons[name];
  if (!svg) return null;
  return (
    <span
      aria-hidden="true"
      className={"inline-flex shrink-0 items-center justify-center " + className}
      style={{ width: size, height: size }}
      dangerouslySetInnerHTML={{ __html: svg }}
    />
  );
}

/* --------------------------------- ظهور تدريجي عند التمرير (CSS-first)
   المحتوى ظاهر افتراضياً؛ الإخفاء مشروط بـ html.js والحركة بانتقال CSS.
   لو تعطّل JS أو تجمّدت حلقة الرسوم يبقى المحتوى مقروءاً — لا صفحة سوداء. */
export function Reveal({ children, delay = 0, className = "" }) {
  const ref = useRef(null);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const show = () => el.classList.add("in");
    if (!("IntersectionObserver" in window)) { show(); return; }

    const io = new IntersectionObserver(
      (es) => es.forEach((e) => { if (e.isIntersecting) { show(); io.unobserve(el); } }),
      { threshold: 0.12, rootMargin: "0px 0px -60px 0px" }
    );
    io.observe(el);

    // شبكة أمان: لو لم يطلق IntersectionObserver إطلاقاً (بيئات مدمجة/تبويب مخفي)
    // أظهر المحتوى بعد مهلة قصيرة. لا يجوز أن يبقى النص غير مرئي بسبب حركة.
    const safety = setTimeout(() => {
      if (!el.classList.contains("in")) { show(); io.unobserve(el); }
    }, 2000);

    return () => { clearTimeout(safety); io.disconnect(); };
  }, []);
  return (
    <div ref={ref} className={"rv " + className} style={{ transitionDelay: delay + "s" }}>
      {children}
    </div>
  );
}

/* ------------------------------------------------- بقعة ضوء تتبع المؤشّر */
export function useSpotlight() {
  return useCallback((e) => {
    const el = e.currentTarget;
    const r = el.getBoundingClientRect();
    el.style.setProperty("--mx", `${e.clientX - r.left}px`);
    el.style.setProperty("--my", `${e.clientY - r.top}px`);
  }, []);
}

/* ------------------------------------------------------- زرّ مغناطيسي */
export function Magnetic({ href, children, icon, variant = "solid", strength = 0.3 }) {
  const ref = useRef(null);
  const reduce = useReducedMotion();

  useEffect(() => {
    const el = ref.current;
    if (!el || reduce || window.matchMedia("(hover:none)").matches) return;
    const move = (e) => {
      const r = el.getBoundingClientRect();
      const dx = e.clientX - (r.left + r.width / 2);
      const dy = e.clientY - (r.top + r.height / 2);
      el.style.transform = `translate(${dx * strength}px, ${dy * strength * 0.7}px)`;
    };
    const leave = () => { el.style.transform = "translate(0,0)"; };
    el.addEventListener("pointermove", move);
    el.addEventListener("pointerleave", leave);
    return () => {
      el.removeEventListener("pointermove", move);
      el.removeEventListener("pointerleave", leave);
    };
  }, [reduce, strength]);

  const base =
    "group relative inline-flex items-center justify-center gap-2.5 overflow-hidden " +
    "rounded-full px-8 py-4 text-[15px] font-extrabold no-underline whitespace-nowrap " +
    "transition-[transform,box-shadow,background-position] duration-500 will-change-transform " +
    "active:scale-[0.965]";

  const skin =
    variant === "ghost"
      ? "bg-white/5 text-ink shadow-[inset_0_0_0_1px_rgb(255_255_255/0.1)] backdrop-blur-lg " +
        "hover:bg-white/10 hover:text-white hover:shadow-[inset_0_0_0_1px_rgb(255_255_255/0.22),0_16px_40px_-14px_rgb(0_0_0/0.9)]"
      : "text-[#07090F] bg-[linear-gradient(100deg,#8FE9FF,#B9AFFF_52%,#8FE9FF)] bg-[length:200%_100%] " +
        "shadow-[0_10px_34px_-8px_rgb(124_108_246/0.75),inset_0_1px_0_rgb(255_255_255/0.5)] " +
        "hover:bg-right hover:shadow-[0_20px_50px_-10px_rgb(124_108_246/0.9),inset_0_1px_0_rgb(255_255_255/0.6)]";

  return (
    <a ref={ref} href={href} className={`${base} ${skin}`}>
      {variant !== "ghost" && (
        <span
          aria-hidden="true"
          className="pointer-events-none absolute inset-0 -translate-x-[120%] bg-[linear-gradient(115deg,transparent_25%,rgb(255_255_255/0.75)_50%,transparent_75%)]
                     transition-transform duration-1000 ease-[cubic-bezier(0.16,1,0.3,1)] group-hover:translate-x-[120%]"
        />
      )}
      {icon && <Icon name={icon} size={17} />}
      <span className="relative">{children}</span>
    </a>
  );
}

/* --------------------------------------------------------- عدّاد رقمي */
export function Counter({ value, decimals = 0 }) {
  const ref = useRef(null);
  const inView = useInView(ref, { once: true, amount: 0.5 });
  const reduce = useReducedMotion();
  const [n, setN] = useState(reduce ? value : 0);

  useEffect(() => {
    if (!inView || reduce) {
      // شبكة أمان: لو لم يطلق useInView إطلاقاً لا يجوز أن يبقى الرقم صفراً.
      const safety = setTimeout(() => setN(value), reduce ? 0 : 2000);
      return () => clearTimeout(safety);
    }
    const controls = animate(0, value, {
      duration: 1.5,
      ease: [0.16, 1, 0.3, 1],
      onUpdate: (v) => setN(v),
    });
    return () => controls.stop();
  }, [inView, value, reduce]);

  const shown = decimals
    ? n.toFixed(decimals)
    : Math.round(n).toLocaleString("en-US");

  return <span ref={ref} className="tnum">{shown}</span>;
}

/* --------------------------------------------------------- بطاقة زجاجية */
export function GlassCard({ children, className = "", spot = true, ...rest }) {
  const onMove = useSpotlight();
  return (
    <div
      onMouseMove={spot ? onMove : undefined}
      className={`glass ${spot ? "spot" : ""} relative overflow-hidden ${className}`}
      {...rest}
    >
      {children}
    </div>
  );
}

/* ----------------------------------------------- هل حلقة الرسوم تعمل أصلاً؟
   Motion يضع opacity:0 فوراً عند التركيب ثم يحتاج requestAnimationFrame ليرفعها.
   لو لم تُستدعَ rAF إطلاقاً (تبويب مخفي · بيئة مدمجة · خنق شديد) يبقى المحتوى
   غير مرئي للأبد. هذا الخطّاف يكتشف ذلك خلال 700ms ويُعيد false، فتُمرَّر
   `initial={false}` وتظهر العناصر بلا حركة بدل ألا تظهر أبداً. */
export function useAnimEnabled() {
  const [ok, setOk] = useState(true);
  useEffect(() => {
    let fired = false;
    const r = requestAnimationFrame(() => { fired = true; });
    const id = setTimeout(() => { if (!fired) setOk(false); }, 700);
    return () => { cancelAnimationFrame(r); clearTimeout(id); };
  }, []);
  return ok;
}
