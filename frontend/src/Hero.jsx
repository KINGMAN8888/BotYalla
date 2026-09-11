import { useRef, useEffect, useState } from "react";
import { motion, useScroll, useTransform, useReducedMotion } from "motion/react";
import { BY, t, Icon, Magnetic } from "./ui.jsx";
import LiveDemo from "./LiveDemo.jsx";

/* ============================================================================
   البطل: عنوان تحريري ضخم بجانب منتج حيّ.

   العرض الحيّ هو الحجة لا الزينة: الزائر يبدّل بين تليجرام وواتساب فيرى نفس
   البوت يتكلم بلغة كل قناة. الدخول مبني على انتقالات CSS لا حلقة رسوم — المحتوى
   ظاهر افتراضياً والإخفاء مشروط بـ html.js، فلا يختفي البطل لو تعثّرت الحركة.
   ========================================================================== */

function useEnter(rootRef) {
  useEffect(() => {
    const root = rootRef.current;
    if (!root) return;
    const play = () => root.querySelectorAll(".kw,.hr-in,.hr-side").forEach((el) => el.classList.add("in"));
    const id = setTimeout(play, 40);
    const safety = setTimeout(play, 1800);          // شبكة أمان مهما حدث
    return () => { clearTimeout(id); clearTimeout(safety); };
  }, [rootRef]);
}

/* عنوان يظهر كلمة كلمة */
function Kinetic({ text, from = 0, step = 0.07, accent = false }) {
  const words = String(text || "").split(/\s+/).filter(Boolean);
  return words.map((word, i) => (
    <span key={i} className="inline-block overflow-hidden pb-[0.08em] align-bottom">
      <span className={"kw " + (accent ? "hue serif-accent" : "")}
            style={{ transitionDelay: `${from + i * step}s` }}>
        {word}
      </span>
      {i < words.length - 1 ? " " : null}
    </span>
  ));
}

function ChannelSwitch({ value, onChange }) {
  const opts = [["telegram", t("lp2_ch_tg"), "#2AABEE"], ["whatsapp", t("lp2_ch_wa"), "#25D366"]];
  return (
    <div className="mb-5 flex flex-wrap items-center justify-center gap-3">
      <span className="text-[13px] font-bold text-ink-3">{t("lp2_see_on")}</span>
      <div role="tablist" aria-label={t("lp2_see_on")}
           className="inline-flex rounded-full bg-black/30 p-1 shadow-[inset_0_0_0_1px_rgb(255_255_255/0.1)]">
        {opts.map(([id, label, color]) => (
          <button key={id} type="button" role="tab" aria-selected={value === id} onClick={() => onChange(id)}
                  className={"relative inline-flex items-center gap-2 rounded-full px-4 py-2 text-[13px] font-extrabold " +
                    "transition-colors duration-300 " + (value === id ? "text-white" : "text-ink-3 hover:text-ink-2")}>
            {value === id && (
              <motion.span layoutId="ch-pill"
                className="absolute inset-0 rounded-full bg-white/10 shadow-[inset_0_0_0_1px_rgb(255_255_255/0.18)]"
                transition={{ type: "spring", stiffness: 400, damping: 32 }} />
            )}
            <i className="relative block size-2 rounded-full" style={{ background: color }} />
            <span className="relative">{label}</span>
          </button>
        ))}
      </div>
    </div>
  );
}

export default function Hero() {
  const ref = useRef(null);
  const reduce = useReducedMotion();
  const [channel, setChannel] = useState("telegram");
  useEnter(ref);

  const { scrollYProgress } = useScroll({ target: ref, offset: ["start start", "end start"] });
  const y = useTransform(scrollYProgress, [0, 1], [0, reduce ? 0 : -80]);
  const fade = useTransform(scrollYProgress, [0, 0.9], [1, reduce ? 1 : 0.15]);

  const aWords = String(t("lp2_h1a")).split(/\s+/).filter(Boolean).length;
  const authed = !!(BY.auth && BY.auth.in);

  return (
    <section ref={ref} aria-labelledby="hero-t"
             className="relative mx-auto max-w-[1320px] px-6 pt-[clamp(28px,4.5vw,72px)] pb-[clamp(40px,6vw,88px)]">
      <div className="grid items-center gap-x-12 gap-y-14 lg:grid-cols-[minmax(0,1.02fr)_minmax(0,1fr)]">
        <motion.div style={{ y, opacity: fade }} className="relative z-10 max-w-[680px]">
          <span className="hr-in mb-7 inline-flex items-center gap-2.5 rounded-full bg-white/[0.05] px-4 py-2
                           text-[12.5px] font-extrabold text-ink-2
                           shadow-[inset_0_0_0_1px_rgb(255_255_255/0.12)] backdrop-blur-md">
            <span className="relative flex size-1.5">
              <span className="absolute inline-flex size-full animate-ping rounded-full bg-au-teal opacity-75" />
              <span className="relative inline-flex size-1.5 rounded-full bg-au-teal" />
            </span>
            {t("lp2_badge")}
          </span>

          <h1 id="hero-t" className="display m-0 mb-7 text-[clamp(40px,6.2vw,84px)] font-extrabold text-ink">
            <Kinetic text={t("lp2_h1a")} from={0.1} />{" "}
            <Kinetic text={t("lp2_h1b")} from={0.1 + aWords * 0.07} accent />
          </h1>

          <p className="hr-in m-0 mb-9 max-w-[56ch] text-[clamp(15.5px,1.35vw,18.5px)] leading-[1.85] text-ink-2"
             style={{ transitionDelay: "0.5s" }}>
            {t("lp2_sub")}
          </p>

          <div className="hr-in flex flex-wrap gap-3.5" style={{ transitionDelay: "0.62s" }}>
            <Magnetic href={authed ? BY.urls.dashboard : BY.urls.register} icon="rocket">
              {authed ? t("lp2_nav_dashboard") : t("get_started_free")}
            </Magnetic>
            <Magnetic href={BY.urls.home + "#pricing"} variant="ghost" icon="tag">{t("lp2_cta_secondary")}</Magnetic>
          </div>

          <ul className="hr-in mt-9 grid list-none grid-cols-1 gap-x-6 gap-y-2.5 p-0 text-[13.5px] text-ink-3 sm:grid-cols-2"
              style={{ transitionDelay: "0.74s" }}>
            {["lp2_trust_1", "lp2_trust_2", "lp2_trust_3", "lp2_trust_4"].map((k) => (
              <li key={k} className="inline-flex items-center gap-2">
                <Icon name="check" size={15} className="text-au-teal" />{t(k)}
              </li>
            ))}
          </ul>
        </motion.div>

        <div className="hr-side relative z-0 lg:-me-6"
             style={{ "--side-from": BY.dir === "rtl" ? "-60px" : "60px", transitionDelay: "0.25s" }}>
          <ChannelSwitch value={channel} onChange={setChannel} />
          <LiveDemo channel={channel} />
        </div>
      </div>
    </section>
  );
}
