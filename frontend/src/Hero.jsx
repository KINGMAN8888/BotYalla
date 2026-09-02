import { useRef, useEffect } from "react";
import { motion, useScroll, useTransform, useReducedMotion } from "motion/react";
import { BY, t, Icon, Magnetic } from "./ui.jsx";
import LiveDemo from "./LiveDemo.jsx";

/* ============================================================================
   البطل: تقسيم غير متماثل — كتلة نصّ ضخمة بجانب نافذة المنتج الحيّة،
   لا العمود التقليدي (شارة ← عنوان ← وصف ← زرّان) فوق بعضه.

   الدخول مبني على انتقالات CSS لا على حلقة رسوم JS: المحتوى ظاهر افتراضياً
   والإخفاء مشروط بـ html.js، فلا يختفي البطل أبداً لو تعثّرت الحركة.
   ========================================================================== */

/* يشغّل الدخول بعد التركيب مباشرة (بلا rAF ولا IntersectionObserver —
   هذا محتوى فوق الطيّة، لا ننتظر به شيئاً) */
function useEnter(rootRef) {
  useEffect(() => {
    const root = rootRef.current;
    if (!root) return;
    const play = () => root.querySelectorAll(".kw,.hr-in,.hr-side")
      .forEach((el) => el.classList.add("in"));
    const id = setTimeout(play, 40);          // إطار واحد ليُطبَّق وضع البداية
    const safety = setTimeout(play, 1800);    // شبكة أمان مهما حدث
    return () => { clearTimeout(id); clearTimeout(safety); };
  }, [rootRef]);
}

/* عنوان يظهر كلمة كلمة: كل كلمة لها تأخيرها الخاص */
function Kinetic({ text, from = 0, step = 0.07, accent = false }) {
  const words = String(text || "").split(/\s+/).filter(Boolean);
  return words.map((word, i) => (
    <span key={i} className="inline-block overflow-hidden align-bottom">
      <span className={"kw " + (accent ? "hue" : "")}
            style={{ transitionDelay: `${from + i * step}s` }}>
        {word}
      </span>
      {i < words.length - 1 ? " " : null}
    </span>
  ));
}

export default function Hero() {
  const ref = useRef(null);
  const reduce = useReducedMotion();
  useEnter(ref);

  const { scrollYProgress } = useScroll({ target: ref, offset: ["start start", "end start"] });
  const y = useTransform(scrollYProgress, [0, 1], [0, reduce ? 0 : -80]);
  const fade = useTransform(scrollYProgress, [0, 0.9], [1, reduce ? 1 : 0.15]);

  const aWords = String(t("hero_title_a")).split(/\s+/).filter(Boolean).length;

  return (
    <header ref={ref}
            className="relative mx-auto max-w-[1320px] px-6 pt-[clamp(36px,5vw,76px)] pb-[clamp(40px,6vw,80px)]">
      <div className="grid items-center gap-x-12 gap-y-14 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.05fr)]">

        {/* عمود النصّ */}
        <motion.div style={{ y, opacity: fade }} className="relative z-10 max-w-[640px]">
          <span className="hr-in mb-7 inline-flex items-center gap-2.5 rounded-full bg-white/[0.05] px-4 py-2
                           text-[12px] font-extrabold text-ink-2
                           shadow-[inset_0_0_0_1px_rgb(255_255_255/0.12)] backdrop-blur-md">
            <span className="relative flex size-1.5">
              <span className="absolute inline-flex size-full animate-ping rounded-full bg-au-teal opacity-75" />
              <span className="relative inline-flex size-1.5 rounded-full bg-au-teal" />
            </span>
            {t("lp_badge")}
          </span>

          <h1 className="tight m-0 mb-7 text-[clamp(38px,5.6vw,74px)] font-extrabold text-ink">
            <Kinetic text={t("hero_title_a")} from={0.1} />{" "}
            <Kinetic text={t("hero_title_b")} from={0.1 + aWords * 0.07} accent />
          </h1>

          <p className="hr-in m-0 mb-9 max-w-[54ch] text-[clamp(15px,1.35vw,18px)] leading-[1.8] text-ink-2"
             style={{ transitionDelay: "0.5s" }}>
            {t("hero_sub")}
          </p>

          <div className="hr-in flex flex-wrap gap-3.5" style={{ transitionDelay: "0.62s" }}>
            <Magnetic href={BY.urls.register} icon="rocket">{t("get_started_free")}</Magnetic>
            <Magnetic href={BY.urls.pricing} variant="ghost" icon="tag">{t("lp_cta_demo")}</Magnetic>
          </div>

          <ul className="hr-in mt-9 flex flex-wrap gap-x-6 gap-y-2.5 p-0 text-[13px] text-ink-3"
              style={{ transitionDelay: "0.74s" }}>
            {[t("lp_trust_1"), t("lp_trust_2"), t("lp_trust_3")].map((x, i) => (
              <li key={i} className="inline-flex items-center gap-2">
                <Icon name="check" size={14} className="text-au-teal" />{x}
              </li>
            ))}
          </ul>
        </motion.div>

        {/* عمود المنتج الحيّ */}
        <div className="hr-side relative z-0 lg:-me-6"
             style={{ "--side-from": BY.dir === "rtl" ? "-60px" : "60px", transitionDelay: "0.25s" }}>
          <LiveDemo />
        </div>
      </div>
    </header>
  );
}
