import { useState, useEffect } from "react";
import { motion, useInView, useReducedMotion } from "motion/react";
import { useRef } from "react";
import { BY, t, Icon, Counter, useSpotlight, useAnimEnabled } from "./ui.jsx";

/* ============================================================================
   العرض الحيّ: يختار الزائر نوع البوت فتتبدّل المحادثة والأرقام أمامه مباشرة.
   يعرض قوّة المنصة الفعلية بدل صورة ثابتة.
   ========================================================================== */
export default function LiveDemo({ channel = "telegram" }) {
  const wa = channel === "whatsapp";
  const demos = BY.demos || [];
  const [idx, setIdx] = useState(0);
  const [auto, setAuto] = useState(true);
  const ref = useRef(null);
  const inView = useInView(ref, { once: false, amount: 0.35 });
  const animOk = useAnimEnabled();
  // عطّل حركة الدخول لو كانت حلقة الرسوم ميتة — الظهور أهم من الحركة
  const reduce = useReducedMotion() || !animOk;
  const onMove = useSpotlight();

  // تدوير تلقائي حتى يتدخّل الزائر
  useEffect(() => {
    if (!auto || reduce || !inView || demos.length < 2) return;
    const id = setTimeout(() => setIdx((i) => (i + 1) % demos.length), 6500);
    return () => clearTimeout(id);
  }, [auto, idx, inView, reduce, demos.length]);

  const d = demos[idx] || { msgs: [], kbd: [], metrics: [], handle: "" };

  return (
    <div ref={ref} className="[perspective:1900px] [perspective-origin:50%_22%]">
      <motion.div
        initial={reduce ? false : { opacity: 0, rotateX: 16, scale: 0.97 }}
        animate={inView || reduce ? { opacity: 1, rotateX: 0, scale: 1 } : {}}
        transition={{ duration: 1.2, ease: [0.16, 1, 0.3, 1] }}
        className="[transform-style:preserve-3d]"
      >
        <div
          onMouseMove={onMove}
          className="glass spot relative overflow-hidden rounded-[26px]"
        >
          {/* شريط النافذة */}
          <div className="flex items-center gap-2 bg-white/[0.03] px-5 py-4 shadow-[inset_0_1px_0_rgb(255_255_255/0.09)]">
            <i className="block size-[11px] rounded-full bg-[#FF5F57]" />
            <i className="block size-[11px] rounded-full bg-[#FEBC2E]" />
            <i className="block size-[11px] rounded-full bg-[#28C840]" />
            <span className="ms-3.5 rounded-full bg-black/35 px-4 py-1 text-[11.5px] tracking-wide text-ink-3 shadow-[inset_0_0_0_1px_rgb(255_255_255/0.09)]">
              {wa ? "wa.me/20 10•• ••• ••••" : `t.me/${d.handle}`}
            </span>
            <span className="ms-auto inline-flex items-center gap-1.5 rounded-full bg-au-teal/15 px-3 py-1 text-[11px] font-extrabold text-au-teal">
              <i className="block size-1.5 rounded-full bg-current blip" />
              {t("lp_live")}
            </span>
          </div>

          <div className="grid gap-5 p-6 lg:grid-cols-[1.05fr_0.95fr]">
            {/* المحادثة */}
            <div className="flex min-h-[300px] flex-col gap-2.5 rounded-2xl bg-black/35 p-5 shadow-[inset_0_0_0_1px_rgb(255_255_255/0.09)]">
              <div key={`${idx}-${animOk}-${channel}`} className="flex flex-1 flex-col gap-2.5">
                  {d.msgs.map((m, i) => (
                    <motion.div
                      key={i}
                      initial={reduce ? false : { opacity: 0, y: 14, scale: 0.96 }}
                      animate={{ opacity: 1, y: 0, scale: 1 }}
                      transition={{
                        delay: reduce ? 0 : 0.15 + i * 0.55,
                        duration: 0.6,
                        ease: [0.175, 0.885, 0.32, 1.275],
                      }}
                      className={
                        "max-w-[84%] rounded-[19px] px-4 py-2.5 text-[13.5px] leading-relaxed " +
                        (m.me && wa
                          ? "self-end rounded-ee-[6px] bg-[linear-gradient(115deg,#25D366,#1DAA61)] font-bold text-[#04130A] shadow-[0_8px_22px_-10px_rgb(37_211_102/0.8)]"
                          : m.me
                          ? "self-end rounded-ee-[6px] bg-[linear-gradient(115deg,#7C6CF6,#22D3EE)] font-bold text-[#08111C] shadow-[0_8px_22px_-10px_rgb(34_211_238/0.9)]"
                          : "self-start rounded-es-[6px] bg-white/[0.07] text-ink shadow-[inset_0_0_0_1px_rgb(255_255_255/0.09)]")
                      }
                    >
                      {m.text}
                    </motion.div>
                  ))}

                  {/* مؤشّر الكتابة */}
                  {!reduce && (
                    <motion.div
                      initial={{ opacity: 0, y: 10 }}
                      animate={{ opacity: [0, 1, 1, 0], y: [10, 0, 0, -6] }}
                      transition={{
                        delay: 0.15 + d.msgs.length * 0.55,
                        duration: 2.4,
                        times: [0, 0.15, 0.8, 1],
                      }}
                      className="inline-flex w-fit gap-1.5 self-start rounded-[19px] bg-white/[0.07] px-4 py-3.5 shadow-[inset_0_0_0_1px_rgb(255_255_255/0.09)]"
                    >
                      {[0, 1, 2].map((i) => (
                        <span
                          key={i}
                          className="block size-1.5 rounded-full bg-ink-3 blip"
                          style={{ animationDelay: `${i * 0.18}s` }}
                        />
                      ))}
                    </motion.div>
                  )}
                </div>

              {/* لوحة أزرار البوت */}
              <div className="mt-auto flex flex-wrap gap-1.5 pt-3">
                {(d.kbd || []).map((b, i) => (
                  <motion.b
                    key={`${idx}-${i}-${animOk}`}
                    initial={reduce ? false : { opacity: 0, y: 8 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: reduce ? 0 : 0.5 + i * 0.09, duration: 0.5 }}
                    whileHover={reduce ? {} : { y: -3 }}
                    className="cursor-default rounded-xl bg-white/[0.05] px-3.5 py-2 text-xs font-bold text-ink-2
                               shadow-[inset_0_0_0_1px_rgb(255_255_255/0.09)] transition-colors
                               hover:bg-au-violet/20 hover:text-white"
                  >
                    {b}
                  </motion.b>
                ))}
              </div>
            </div>

            {/* الأرقام */}
            <div>
              <div className="grid grid-cols-2 gap-3">
                {(d.metrics || []).map((m, i) => (
                  <motion.div
                    key={`${idx}-${i}-${animOk}`}
                    initial={reduce ? false : { opacity: 0, y: 12 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: reduce ? 0 : i * 0.08, duration: 0.6 }}
                    whileHover={reduce ? {} : { y: -3 }}
                    className="rounded-2xl bg-white/[0.035] p-4 shadow-[inset_0_0_0_1px_rgb(255_255_255/0.09)]
                               transition-colors hover:bg-white/[0.07]"
                  >
                    <div className="wide-cap text-[10.5px] font-extrabold text-ink-3">{m.k}</div>
                    <div className="mt-1.5 text-[27px] font-extrabold leading-tight tracking-tight text-ink">
                      <Counter value={m.v} decimals={m.v % 1 !== 0 ? 1 : 0} />
                    </div>
                    {m.d && <div className="mt-0.5 text-[11.5px] font-bold text-au-teal">{m.d}</div>}
                  </motion.div>
                ))}
              </div>

              {/* رسم بياني */}
              <div className="mt-3 rounded-2xl bg-white/[0.035] p-4 shadow-[inset_0_0_0_1px_rgb(255_255_255/0.09)]">
                <div className="wide-cap text-[10.5px] font-extrabold text-ink-3">
                  {t("daily_activity")}
                </div>
                <div className="mt-3.5 flex h-[74px] items-end gap-1.5">
                  {[38, 55, 44, 70, 58, 84, 72].map((h, i) => (
                    <motion.i
                      key={`${idx}-${i}-${animOk}`}
                      initial={reduce ? false : { scaleY: 0, opacity: 0 }}
                      animate={{ scaleY: 1, opacity: 1 }}
                      transition={{
                        delay: reduce ? 0 : 0.2 + i * 0.07,
                        duration: 0.75,
                        ease: [0.175, 0.885, 0.32, 1.275],
                      }}
                      style={{ height: `${h}%`, transformOrigin: "bottom" }}
                      className="block flex-1 rounded-t-[5px] bg-[linear-gradient(180deg,#22D3EE,rgb(124_108_246/0.28))]"
                    />
                  ))}
                </div>
              </div>
            </div>
          </div>
        </div>
      </motion.div>

      {/* منتقي القوالب — يبدّل كل ما سبق فوراً */}
      <div className="mt-6 flex flex-wrap justify-center gap-2">
        {demos.map((x, i) => (
          <button
            key={i}
            type="button"
            aria-pressed={i === idx}
            onClick={() => { setAuto(false); setIdx(i); }}
            className={
              "relative inline-flex items-center gap-2 rounded-full px-4 py-2.5 text-[13px] font-bold " +
              "transition-colors duration-300 " +
              (i === idx
                ? "text-white"
                : "text-ink-3 hover:text-ink-2 shadow-[inset_0_0_0_1px_rgb(255_255_255/0.08)]")
            }
          >
            {i === idx && (
              <motion.span
                layoutId="picker-pill"
                className="absolute inset-0 rounded-full bg-au-violet/25 shadow-[inset_0_0_0_1px_rgb(124_108_246/0.55)]"
                transition={{ type: "spring", stiffness: 380, damping: 32 }}
              />
            )}
            <Icon name={x.icon} size={15} className="relative text-au-cyan" />
            <span className="relative">{x.name}</span>
          </button>
        ))}
      </div>
    </div>
  );
}
