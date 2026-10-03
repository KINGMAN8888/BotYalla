import { useEffect, useRef, useState } from "react";
import { useReducedMotion } from "motion/react";

/* ============================================================================
   فيديو خلفية البطل — دوّامة رسايل حوالين نواة البوت (فوضى ← نظام).

   لوب 20 ثانية متصل بلا قطع، صامت، بألوان الشفق نفسها. يقعد تحت المحتوى
   (z-index:-20: فوق الشفق -40 وشبكته -30) ويذوب في الصفحة بقناع من فوق وتحت.

   التكلفة محسوبة:
   · 1080p ≈ 6MB للكمبيوتر و720p ≈ 3MB للشاشات الصغيرة (<source media>).
   · بيقف لما يخرج من الشاشة أو التبويب يتخبّى — مفيش فك ترميز في الخلفية.
   · تقليل الحركة أو «توفير البيانات» ⇒ صورة ثابتة (poster) بدل الفيديو.
   الأسماء فيها v1: nginx بيخزّن /static/ 30 يوم immutable، فأي نسخة جديدة = اسم جديد.
   ========================================================================== */

const BASE = "/static/hero/botyalla-hero-v1";

const MASK =
  "linear-gradient(to bottom, transparent 0%, #000 12%, #000 58%, transparent 100%)";

export default function HeroVideo() {
  const ref = useRef(null);
  const reduce = useReducedMotion();
  const [still] = useState(() =>
    typeof navigator !== "undefined" && !!(navigator.connection && navigator.connection.saveData));
  const staticOnly = reduce || still;

  useEffect(() => {
    const v = ref.current;
    if (!v || staticOnly) return;
    let visible = true;
    const sync = () => {
      if (visible && !document.hidden) { const p = v.play(); if (p && p.catch) p.catch(() => {}); }
      else v.pause();
    };
    const io = new IntersectionObserver(([e]) => { visible = e.isIntersecting; sync(); }, { threshold: 0.01 });
    io.observe(v);
    document.addEventListener("visibilitychange", sync);
    return () => { io.disconnect(); document.removeEventListener("visibilitychange", sync); };
  }, [staticOnly]);

  const box = {
    position: "absolute", left: "50%", top: "-110px", width: "100vw", height: "calc(100% + 110px)",
    transform: "translateX(-50%)", zIndex: -20, pointerEvents: "none", overflow: "hidden",
    WebkitMaskImage: MASK, maskImage: MASK,
  };
  const fill = { width: "100%", height: "100%", objectFit: "cover", opacity: 0.78 };

  return (
    <div aria-hidden="true" style={box}>
      {staticOnly ? (
        <picture>
          <source srcSet={`${BASE}-poster.webp`} type="image/webp" />
          <img src={`${BASE}-poster.jpg`} alt="" style={fill} decoding="async" />
        </picture>
      ) : (
        <video ref={ref} style={fill} autoPlay muted loop playsInline preload="auto"
               poster={`${BASE}-poster.webp`} disablePictureInPicture disableRemotePlayback>
          <source src={`${BASE}-720.mp4`} type="video/mp4" media="(max-width: 900px)" />
          <source src={`${BASE}-1080.mp4`} type="video/mp4" />
        </video>
      )}
      {/* تعتيم خفيف تحت العنوان عشان الكلام يفضل مقروء فوق أي إطار */}
      <div style={{ position: "absolute", inset: 0,
                    background: "radial-gradient(60% 45% at 50% 72%, rgba(5,7,13,.55), rgba(5,7,13,0) 70%)" }} />
    </div>
  );
}
