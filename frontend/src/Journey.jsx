import { useEffect, useRef, useState } from "react";
import { motion, AnimatePresence, useScroll, useMotionValueEvent, useReducedMotion } from "motion/react";
import { BY, t, Icon } from "./ui.jsx";

/* ============================================================================
   قصة التمرير: «من أول رسالة لأول طلب».

   على الشاشات الواسعة القسم أطول من الشاشة، والمحتوى لاصق في منتصفها؛ كل
   مرحلة تأخذ نفس المسافة من التمرير: زبون يسأل ← البوت يرد ← الطلب يتسجّل ←
   تنبيه لصاحب النشاط ← وصاحب النشاط يتدخّل بنفسه من صندوق الوارد. الهاتف على
   الجانب يتقدّم معها رسالةً رسالة.

   على الجوال أو مع تقليل الحركة: لا تمرير مخطوف — كل المراحل ظاهرة والهاتف
   مكتمل. القصة تُقرأ، لا تُفرض.
   ========================================================================== */

function useWide() {
  const q = "(min-width: 1024px)";
  const [wide, setWide] = useState(() => typeof window !== "undefined" && window.matchMedia(q).matches);
  useEffect(() => {
    const m = window.matchMedia(q);
    const on = () => setWide(m.matches);
    m.addEventListener("change", on);
    return () => m.removeEventListener("change", on);
  }, []);
  return wide;
}

export default function Journey() {
  const J = BY.journey || { stages: [], msgs: [], notify: null };
  const n = Math.max(1, J.stages.length);
  const ref = useRef(null);
  const reduce = useReducedMotion();
  const wide = useWide();
  const scrolly = wide && !reduce;
  const [stage, setStage] = useState(0);

  const { scrollYProgress } = useScroll({ target: ref, offset: ["start start", "end end"] });
  useMotionValueEvent(scrollYProgress, "change", (v) => {
    if (scrolly) setStage(Math.min(n - 1, Math.max(0, Math.floor(v * n))));
  });
  const shown = scrolly ? stage : n - 1;

  return (
    <section id="story" ref={ref} aria-labelledby="story-t"
             // overflow-x-clip لا hidden: يقصّ وهج الهاتف دون أن ينشئ حاوية تمرير
             // (hidden كان سيكسر position:sticky للمحتوى اللاصق)
             className="relative overflow-x-clip"
             // ‏75vh من التمرير لكل مرحلة — القسم يتمدّد مع عددها
             style={scrolly ? { height: `${n * 75}vh` } : undefined}>
      <div className={scrolly ? "sticky top-0 flex h-screen items-center" : ""}>
        <div className="mx-auto grid w-full max-w-[1240px] grid-cols-1 items-center gap-12 px-5 sm:px-6
                        py-[clamp(64px,10vw,120px)] lg:grid-cols-[minmax(0,1fr)_minmax(0,400px)] lg:py-0">
          <div>
            <h2 id="story-t"
                className="display m-0 mb-4 max-w-[18ch] text-[clamp(30px,4.4vw,56px)] font-extrabold text-ink">
              {t("lp2_j_t")}
            </h2>
            <p className="m-0 max-w-[56ch] text-[clamp(15px,1.3vw,17px)] leading-[1.8] text-ink-2">
              {t("lp2_j_sub")}
            </p>

            <ol className="mt-10 flex list-none flex-col gap-3 p-0">
              {J.stages.map((s, i) => {
                const reached = i <= shown;
                const current = scrolly && i === shown;
                return (
                  <li key={i}
                      className={"relative flex gap-4 rounded-[22px] p-5 transition-all duration-700 " +
                        "ease-[cubic-bezier(0.16,1,0.3,1)] " +
                        (current ? "glass" : "") + (reached ? "" : " opacity-40")}>
                    <span className={"grid size-10 shrink-0 place-items-center rounded-[13px] text-[15px] font-extrabold " +
                                     "transition-colors duration-500 " +
                                     (reached ? "bg-[linear-gradient(130deg,#8FE9FF,#B9AFFF)] text-[#07090F]"
                                              : "bg-white/[0.06] text-ink-3")}>
                      {i + 1}
                    </span>
                    <div>
                      <h3 className="m-0 mb-1 text-[17px] font-extrabold text-ink">{s.t}</h3>
                      <p className="m-0 text-[14px] leading-[1.75] text-ink-2">{s.d}</p>
                    </div>
                  </li>
                );
              })}
            </ol>
          </div>

          <Phone J={J} stage={shown} reduce={reduce} />
        </div>
      </div>
    </section>
  );
}

function Phone({ J, stage, reduce }) {
  const msgs = (J.msgs || []).filter((m) => m.at <= stage);
  const showNote = J.notify && stage >= J.notify.at;
  return (
    <div className="relative mx-auto w-full max-w-[380px]" aria-hidden="true">
      <div className="absolute -inset-6 -z-10 rounded-full lg:-inset-10
                      bg-[radial-gradient(closest-side,rgb(124_108_246/0.35),transparent)] blur-2xl" />
      <div className="glass rounded-[44px] p-2.5 shadow-[0_40px_120px_-40px_rgb(124_108_246/0.7)]">
        <div className="relative flex h-[min(560px,72vh)] flex-col overflow-hidden rounded-[36px] bg-[#070A12]">
          <div className="flex items-center gap-3 px-5 pt-6 pb-3.5 shadow-[0_1px_0_rgb(255_255_255/0.06)]">
            <span className="grid size-10 place-items-center rounded-full text-au-cyan
                             bg-[linear-gradient(150deg,rgb(124_108_246/0.35),rgb(34_211_238/0.15))]">
              <img src="/static/Telegram.svg.png" alt="Telegram" className="size-[19px] object-contain" />
            </span>
            <div className="min-w-0">
              <div className="truncate text-[14px] font-extrabold text-ink">{t("lp_preview_bot")}</div>
              <div className="flex items-center gap-1.5 text-[11.5px] font-bold text-au-teal">
                <i className="block size-1.5 rounded-full bg-current" />{t("lp_live")}
              </div>
            </div>
          </div>

          <div className="flex flex-1 flex-col justify-end gap-2.5 px-4 pb-5">
            <AnimatePresence initial={false}>
              {msgs.map((m) => (
                <motion.div
                  key={m.text}
                  layout={!reduce}
                  initial={reduce ? false : { opacity: 0, y: 18, scale: 0.95 }}
                  animate={{ opacity: 1, y: 0, scale: 1 }}
                  exit={reduce ? {} : { opacity: 0, y: 10 }}
                  transition={{ duration: 0.55, ease: [0.175, 0.885, 0.32, 1.275] }}
                  className={"max-w-[86%] rounded-[19px] px-4 py-2.5 text-[13.5px] leading-relaxed " +
                    (m.me
                      ? "self-end rounded-ee-[6px] bg-[linear-gradient(115deg,#7C6CF6,#22D3EE)] font-bold text-[#08111C]"
                      : m.who === "human"
                      ? "self-start rounded-es-[6px] bg-au-teal/15 text-ink shadow-[inset_0_0_0_1px_rgb(45_212_167/0.4)]"
                      : "self-start rounded-es-[6px] bg-white/[0.08] text-ink")}>
                  {m.who === "human" && (
                    <span className="mb-0.5 flex items-center gap-1 text-[11px] font-extrabold text-au-teal">
                      <Icon name="user" size={12} />{t("lp2_j_you")}
                    </span>
                  )}
                  {m.text}
                </motion.div>
              ))}
            </AnimatePresence>
          </div>

          <AnimatePresence>
            {showNote && (
              <motion.div
                key="note"
                initial={reduce ? false : { opacity: 0, y: -40, scale: 0.96 }}
                animate={{ opacity: 1, y: 0, scale: 1 }}
                exit={reduce ? {} : { opacity: 0, y: -30 }}
                transition={{ type: "spring", stiffness: 320, damping: 26 }}
                className="glass absolute inset-x-3 top-3 z-10 flex gap-3 rounded-[20px] p-3.5">
                <span className="grid size-9 shrink-0 place-items-center rounded-xl bg-au-teal/20 text-au-teal">
                  <Icon name="bolt" size={17} />
                </span>
                <div className="min-w-0">
                  <div className="text-[13px] font-extrabold text-ink">{J.notify.t}</div>
                  <div className="truncate text-[12px] text-ink-2">{J.notify.d}</div>
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </div>
    </div>
  );
}
