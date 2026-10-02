import { useEffect, useRef, useState } from "react";
import { motion, AnimatePresence, useInView, useReducedMotion } from "motion/react";
import { BY, t, Icon, Reveal, Magnetic, useAnimEnabled, isRTL } from "./ui.jsx";

/* ============================================================================
   «ماسنجر وإنستجرام بضغطة» — القسم الذي يفرّقنا عن المنافسين: هم يطلبون تطبيق
   مطوّرين وتوكنات، ونحن نعرض الربط كاملاً أمام الزائر في ثلاث لقطات حيّة تدور وحدها:
   متابعة بفيسبوك ← اختيار الصفحة ← البوت يرد. الخطوات بجانبها تتزامن مع اللقطة.
   الأسماء والمحادثة أمثلة معلنة (لا صفحات حقيقية). تقليل الحركة أو حلقة رسوم ميتة:
   اللقطة الأخيرة ثابتة والخطوات كلها مكتملة.
   ========================================================================== */
const SCENES = [3400, 3800, 6400];               // مدة كل لقطة (مللي ثانية)

const FbMark = ({ size = 18 }) => (
  <svg viewBox="0 0 24 24" width={size} height={size} aria-hidden="true">
    <circle cx="12" cy="12" r="12" fill="#fff" />
    <path fill="#1877F2" d="M15.1 12.6h-2.2V20h-3v-7.4H8.4v-2.6h1.5V8.3c0-2 1-3.3 3.4-3.3h2v2.6h-1.3c-.9 0-1.1.4-1.1 1.1v1.3h2.4z" />
  </svg>
);

/* مؤشّر يتحرك إلى الزر ويضغطه — يقول للزائر «هذا كل ما ستفعله» */
function Pointer({ to, press }) {
  return (
    <motion.span aria-hidden="true" className="pointer-events-none absolute z-20 block"
                 initial={{ left: "82%", top: "88%", opacity: 0 }}
                 animate={{ left: to[0], top: to[1], opacity: 1, scale: press ? [1, 0.82, 1] : 1 }}
                 transition={{ duration: 1.1, ease: [0.16, 1, 0.3, 1], scale: { delay: 1.2, duration: 0.35 } }}>
      <svg width="26" height="26" viewBox="0 0 24 24" className="drop-shadow-[0_4px_10px_rgb(0_0_0/0.5)]">
        <path d="M5 3l13 8.2-6 1.3 3.4 6.6-2.6 1.3-3.4-6.6L5 18z" fill="#fff" stroke="#0b0f1a" strokeWidth="1.2" strokeLinejoin="round" />
      </svg>
    </motion.span>
  );
}

function SceneLogin() {
  return (
    <motion.div key="login" className="absolute inset-0 flex flex-col"
                initial={{ opacity: 0, scale: 0.97 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0, scale: 0.98 }}
                transition={{ duration: 0.45, ease: [0.16, 1, 0.3, 1] }}>
      <div className="flex items-center gap-2 bg-[#1877F2] px-5 py-3 text-[15px] font-extrabold tracking-tight text-white">
        <FbMark size={20} />facebook
      </div>
      <div className="flex flex-1 flex-col items-center justify-center gap-5 bg-[#F0F2F5] px-6 text-center text-[#1C1E21]">
        <div className="flex items-center gap-3">
          <img src="/static/brand/icon-192.png" alt="" className="size-14 rounded-2xl shadow-md" />
          <span className="text-[22px] text-[#8A8D91]">⇄</span>
          <span className="grid size-14 place-items-center rounded-2xl bg-white shadow-md"><FbMark size={30} /></span>
        </div>
        <div>
          <b className="block text-[16px]">BotYalla</b>
          <span className="mt-1 block max-w-[30ch] text-[12.5px] leading-relaxed text-[#65676B]">{t("lp2_mt_s1d")}</span>
        </div>
        <motion.span className="inline-flex h-11 w-full max-w-[260px] items-center justify-center rounded-lg bg-[#1877F2] text-[14px] font-bold text-white"
                     animate={{ scale: [1, 1, 0.96, 1] }} transition={{ duration: 2.4, times: [0, 0.55, 0.62, 0.7] }}>
          {t("lp2_mt_s1")}
        </motion.span>
      </div>
      <Pointer to={["50%", "73%"]} press />
    </motion.div>
  );
}

function SceneSwitch({ on, delay }) {
  return (
    <motion.span className="relative block h-5 w-9 rounded-full" initial={{ backgroundColor: "rgb(255 255 255 / 0.15)" }}
                 animate={{ backgroundColor: on ? "rgb(45 212 167 / 1)" : "rgb(255 255 255 / 0.15)" }} transition={{ delay }}>
      <motion.span className="absolute start-0.5 top-0.5 block size-4 rounded-full bg-white shadow"
                   initial={{ x: 0 }} animate={{ x: on ? (isRTL ? -16 : 16) : 0 }} transition={{ delay, type: "spring", stiffness: 500, damping: 30 }} />
    </motion.span>
  );
}

function ScenePick() {
  const pages = [["lp2_mt_page1", "lp2_mt_cat1", "from-amber-300 to-orange-500", "oasis"], ["lp2_mt_page2", "lp2_mt_cat2", "from-pink-300 to-rose-500", "sukkar"]];
  return (
    <motion.div key="pick" className="absolute inset-0 flex flex-col gap-3 p-5"
                initial={{ opacity: 0, x: 24 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -24 }}
                transition={{ duration: 0.45, ease: [0.16, 1, 0.3, 1] }}>
      <b className="text-[14px] text-ink">{t("lp2_mt_pick")}</b>
      {pages.map(([n, c, g, h], i) => (
        <motion.div key={n} className="flex items-center gap-3 rounded-2xl p-3"
                    initial={{ backgroundColor: "rgb(255 255 255 / 0.04)", boxShadow: "inset 0 0 0 1px rgb(255 255 255 / 0.08)" }}
                    animate={i === 0 ? { backgroundColor: "rgb(124 108 246 / 0.16)", boxShadow: "inset 0 0 0 2px rgb(124 108 246 / 0.7)" } : {}}
                    transition={{ delay: 0.7 }}>
          <span className={`grid size-10 shrink-0 place-items-center rounded-xl bg-gradient-to-br ${g} text-[15px] font-extrabold text-white`}>{t(n).charAt(0)}</span>
          <span className="min-w-0 flex-1 text-start">
            <b className="block truncate text-[13.5px] text-ink">{t(n)}</b>
            <span className="flex items-center gap-1.5 text-[11px] text-ink-3">{t(c)}
              <span className="inline-flex items-center gap-1 rounded-full bg-[#E1306C]/15 px-1.5 text-[#F58BB0]"><img src="/static/instagram.svg" alt="" className="size-2.5" />@{h}</span>
            </span>
          </span>
        </motion.div>
      ))}
      <div className="mt-1 grid grid-cols-2 gap-2">
        {[["/static/messenger.svg", "Messenger", 1.2], ["/static/instagram.svg", "Instagram", 1.6]].map(([logo, name, d]) => (
          <div key={name} className="flex items-center gap-2 rounded-xl bg-white/[0.04] px-3 py-2.5 shadow-[inset_0_0_0_1px_rgb(255_255_255/0.08)]">
            <img src={logo} alt="" className="size-5" /><span className="flex-1 text-[12px] font-bold text-ink-2">{name}</span>
            <SceneSwitch on delay={d} />
          </div>
        ))}
      </div>
      <motion.span className="mt-auto inline-flex h-11 items-center justify-center gap-2 rounded-xl text-[13.5px] font-extrabold text-[#0B1020]
                              bg-[linear-gradient(100deg,#8FE9FF,#B3A6FF)]"
                   animate={{ scale: [1, 1, 0.96, 1] }} transition={{ duration: 3.2, times: [0, 0.78, 0.84, 0.9] }}>
        <Icon name="bolt" size={15} />{t("lp2_mt_connect")}
      </motion.span>
      <Pointer to={["50%", "86%"]} />
    </motion.div>
  );
}

function SceneLive() {
  const msgs = [["me", "lp2_mt_q", 0.5], ["bot", "lp2_mt_a", 1.5], ["me", "lp2_mt_q2", 3.0], ["bot", "lp2_mt_a2", 4.0]];
  return (
    <motion.div key="live" className="absolute inset-0 flex flex-col"
                initial={{ opacity: 0, y: 18 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}
                transition={{ duration: 0.45, ease: [0.16, 1, 0.3, 1] }}>
      <div className="flex items-center gap-3 px-5 py-3 shadow-[0_1px_0_rgb(255_255_255/0.07)]">
        <span className="rounded-full bg-[linear-gradient(45deg,#F77737,#E1306C,#833AB4)] p-[2px]">
          <span className="grid size-9 place-items-center rounded-full bg-[#0D1220] text-[14px] font-extrabold text-amber-300">{t("lp2_mt_page1").charAt(0)}</span>
        </span>
        <span className="min-w-0 flex-1">
          <b className="block truncate text-[13.5px] text-ink">{t("lp2_mt_page1")}</b>
          <span className="flex items-center gap-1 text-[11px] font-bold text-au-teal"><i className="block size-1.5 rounded-full bg-current" />AI</span>
        </span>
        <img src="/static/instagram.svg" alt="Instagram" className="size-5" />
        <img src="/static/messenger.svg" alt="Messenger" className="size-5" />
      </div>
      <div className="flex flex-1 flex-col justify-end gap-2 px-4 pb-4">
        {msgs.map(([who, k, d]) => (
          <motion.span key={k} initial={{ opacity: 0, y: 10, scale: 0.95 }} animate={{ opacity: 1, y: 0, scale: 1 }}
                       transition={{ delay: d, type: "spring", stiffness: 380, damping: 26 }}
                       className={"max-w-[82%] rounded-[18px] px-3.5 py-2 text-[12.5px] leading-relaxed " +
                         (who === "me" ? "self-end rounded-ee-[6px] bg-[linear-gradient(115deg,#833AB4,#E1306C_60%,#F77737)] font-bold text-white"
                                       : "self-start rounded-es-[6px] bg-white/[0.08] text-ink shadow-[inset_0_0_0_1px_rgb(255_255_255/0.08)]")}>
            {t(k)}
          </motion.span>
        ))}
      </div>
      <motion.div className="absolute inset-x-4 top-16 flex items-center gap-2 rounded-2xl bg-[#0F1A14]/95 px-3.5 py-2.5 text-[12px] font-extrabold text-au-teal
                             shadow-[0_12px_30px_-10px_rgb(0_0_0/0.7),inset_0_0_0_1px_rgb(45_212_167/0.35)]"
                  initial={{ opacity: 0, y: -12 }} animate={{ opacity: [0, 1, 1, 0], y: [-12, 0, 0, -8] }}
                  transition={{ duration: 2.6, times: [0, 0.12, 0.8, 1] }}>
        <span className="grid size-6 place-items-center rounded-full bg-au-teal text-[#04140E]"><Icon name="check" size={13} /></span>
        {t("lp2_mt_live")}
      </motion.div>
    </motion.div>
  );
}

export default function MetaShowcase() {
  const ref = useRef(null);
  const inView = useInView(ref, { amount: 0.35 });
  const animOk = useAnimEnabled();
  const still = useReducedMotion() || !animOk;
  const [scene, setScene] = useState(still ? 2 : 0);
  useEffect(() => {
    if (still) { setScene(2); return undefined; }
    if (!inView) return undefined;
    const id = setTimeout(() => setScene((s) => (s + 1) % SCENES.length), SCENES[scene]);
    return () => clearTimeout(id);
  }, [scene, inView, still]);

  const authed = !!(BY.auth && BY.auth.in);
  const steps = [["lp2_mt_s1", "lp2_mt_s1d"], ["lp2_mt_s2", "lp2_mt_s2d"], ["lp2_mt_s3", "lp2_mt_s3d"]];
  return (
    <section ref={ref} id="messenger-instagram" aria-labelledby="mt-t"
             className="relative mx-auto max-w-[1240px] px-6 py-[clamp(64px,10vw,120px)]">
      <div className="grid items-center gap-[clamp(36px,6vw,80px)] lg:grid-cols-[minmax(0,1fr)_minmax(0,0.95fr)]">
        <div>
          <Reveal>
            <span className="inline-flex items-center gap-2 rounded-full bg-white/[0.05] py-1.5 pe-3.5 ps-1.5 text-[12.5px] font-extrabold text-ink-2
                             shadow-[inset_0_0_0_1px_rgb(255_255_255/0.1)]">
              <span className="flex -space-x-1.5 rtl:space-x-reverse">
                <img src="/static/messenger.svg" alt="" className="size-6 rounded-full bg-[#0D1220] p-0.5 ring-2 ring-[#0D1220]" />
                <img src="/static/instagram.svg" alt="" className="size-6 rounded-full bg-[#0D1220] p-0.5 ring-2 ring-[#0D1220]" />
              </span>
              {t("lp2_mt_kicker")}
            </span>
            <h2 id="mt-t" className="display mt-5 mb-4 text-[clamp(28px,4.2vw,52px)] font-extrabold leading-[1.15] text-ink">{t("lp2_mt_t")}</h2>
            <p className="m-0 max-w-[56ch] text-[clamp(14px,1.3vw,17px)] leading-[1.8] text-ink-2">{t("lp2_mt_sub")}</p>
          </Reveal>

          <ol className="mt-9 mb-0 flex list-none flex-col gap-2 p-0">
            {steps.map(([a, b], i) => {
              const on = still || scene === i, done = !still && scene > i;
              return (
                <li key={a}>
                  <button type="button" onClick={() => setScene(i)} aria-current={on ? "step" : undefined}
                          className={"flex w-full cursor-pointer items-start gap-4 rounded-2xl border-0 p-4 text-start transition-colors duration-300 " +
                                     "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/30 " +
                                     (on && !still ? "bg-white/[0.06] shadow-[inset_0_0_0_1px_rgb(255_255_255/0.1)]" : "bg-transparent hover:bg-white/[0.03]")}>
                    <span className={"tnum grid size-9 shrink-0 place-items-center rounded-full text-[14px] font-extrabold transition-colors duration-300 " +
                                     (done || still ? "bg-au-teal text-[#04140E]" : on ? "bg-white text-[#0B1020]" : "bg-white/[0.07] text-ink-3")}>
                      {done || still ? <Icon name="check" size={15} /> : i + 1}
                    </span>
                    <span className="min-w-0 flex-1">
                      <b className={"block text-[16px] transition-colors " + (on || done ? "text-ink" : "text-ink-2")}>{t(a)}</b>
                      <span className="mt-0.5 block text-[13.5px] leading-relaxed text-ink-3">{t(b)}</span>
                      {on && !still && (
                        <span className="mt-3 block h-[3px] overflow-hidden rounded-full bg-white/[0.08]">
                          <motion.span key={`bar-${scene}`} className="block h-full rounded-full bg-[linear-gradient(90deg,#0A7CFF,#E1306C)]"
                                       initial={{ width: "0%" }} animate={{ width: inView ? "100%" : "0%" }}
                                       transition={{ duration: SCENES[i] / 1000, ease: "linear" }} />
                        </span>
                      )}
                    </span>
                  </button>
                </li>
              );
            })}
          </ol>

          <div className="mt-8 flex flex-wrap items-center gap-4">
            <Magnetic href={authed ? BY.urls.dashboard + "#meta-onetap" : BY.urls.register} icon="link">{t("lp2_mt_cta")}</Magnetic>
            <span className="inline-flex items-center gap-1.5 text-[13px] font-bold text-ink-3">
              <Icon name="clock" size={15} className="text-au-cyan" />{t("lp2_mt_time")}
            </span>
          </div>
        </div>

        <Reveal delay={0.1}>
          <div className="relative mx-auto w-full max-w-[400px]">
            <div aria-hidden="true" className="pointer-events-none absolute -inset-10 rounded-[60px] blur-3xl
                 bg-[radial-gradient(closest-side,rgb(10_124_255/0.22),transparent),radial-gradient(closest-side_at_80%_80%,rgb(225_48_108/0.2),transparent)]" />
            <div role="img" aria-label={t("lp2_mt_t")}
                 className="relative aspect-[4/5] overflow-hidden rounded-[34px] bg-[#0B0F1A]
                            shadow-[0_40px_90px_-30px_rgb(0_0_0/0.9),inset_0_0_0_1px_rgb(255_255_255/0.1)]">
              <AnimatePresence mode="wait" initial={false}>
                {scene === 0 && <SceneLogin key="s0" />}
                {scene === 1 && <ScenePick key="s1" />}
                {scene === 2 && <SceneLive key={`s2-${inView}`} />}
              </AnimatePresence>
            </div>
          </div>
        </Reveal>
      </div>
    </section>
  );
}
