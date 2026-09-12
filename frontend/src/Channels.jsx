import { useState } from "react";
import { motion } from "motion/react";
import { BY, t, Icon, Reveal, GlassCard } from "./ui.jsx";
import LiveDemo from "./LiveDemo.jsx";

/* القناتان جنباً إلى جنب — تليجرام باب الدخول المجاني، وواتساب القناة الرسمية.
   لون كل قناة هو لونها المعروف: يتعرّف عليها الزائر قبل أن يقرأ.
   وتحتهما العرض الحيّ: الزائر يبدّل القناة فيرى نفس البوت يتكلم بلغة كل منهما. */
const SKIN = {
  telegram: { dot: "#2AABEE", bg: "rgb(42 171 238 / 0.14)", ring: "rgb(42 171 238 / 0.35)" },
  whatsapp: { dot: "#25D366", bg: "rgb(37 211 102 / 0.14)", ring: "rgb(37 211 102 / 0.35)" },
};

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

export default function Channels() {
  const chans = BY.channels || [];
  const waPlans = (BY.plans || []).filter((p) => p.whatsapp).map((p) => p.name).join(" · ");
  const [channel, setChannel] = useState("telegram");
  return (
    <section aria-labelledby="ch-t" className="mx-auto max-w-[1240px] px-6 py-[clamp(64px,10vw,120px)]">
      <Reveal className="mb-12 max-w-[70ch]">
        <h2 id="ch-t" className="display m-0 mb-4 text-[clamp(28px,4.2vw,52px)] font-extrabold text-ink">
          {t("lp2_ch_t")}
        </h2>
        <p className="m-0 text-[clamp(14px,1.3vw,17px)] leading-[1.8] text-ink-2">{t("lp2_ch_sub")}</p>
      </Reveal>

      <div className="grid grid-cols-1 gap-5 md:grid-cols-2">
        {chans.map((c, i) => {
          const s = SKIN[c.id] || SKIN.telegram;
          return (
            <Reveal key={c.id} delay={i * 0.1} className="h-full">
              <GlassCard className="flex h-full flex-col rounded-[30px] p-[clamp(24px,3vw,38px)]">
                <div aria-hidden="true" className="pointer-events-none absolute -top-24 -end-24 size-64 rounded-full blur-3xl"
                     style={{ background: s.bg }} />
                <div className="relative flex items-center gap-4">
                  <span className="grid size-14 shrink-0 place-items-center rounded-2xl"
                        style={{ background: s.bg, color: s.dot, boxShadow: `inset 0 0 0 1px ${s.ring}` }}>
                    {c.id === "telegram" ? (
                      <img src="/static/Telegram.svg.png" alt="Telegram" className="size-8 object-contain" />
                    ) : c.id === "whatsapp" ? (
                      <img src="/static/whatsapp.png" alt="WhatsApp" className="size-8 object-contain" />
                    ) : (
                      <Icon name={c.icon} size={26} />
                    )}
                  </span>
                  <div>
                    <h3 className="m-0 text-[22px] font-extrabold text-ink">{c.t}</h3>
                    <p className="m-0 mt-1 text-[14px] leading-relaxed text-ink-2">{c.d}</p>
                  </div>
                </div>
                <ul className="relative mt-7 flex list-none flex-col gap-3 p-0">
                  {c.b.map((b, j) => (
                    <li key={j} className="flex items-start gap-3 text-[14.5px] leading-[1.7] text-ink-2">
                      <span className="mt-1 grid size-5 shrink-0 place-items-center rounded-full"
                            style={{ background: s.bg, color: s.dot }}>
                        <Icon name="check" size={12} />
                      </span>
                      {b}
                    </li>
                  ))}
                </ul>
                {c.id === "whatsapp" && waPlans && (
                  <p className="relative mt-auto pt-6 text-[12.5px] font-bold text-ink-3">
                    {t("lp2_wa_plans")} <span className="text-ink-2">{waPlans}</span>
                  </p>
                )}
              </GlassCard>
            </Reveal>
          );
        })}
      </div>

      <Reveal className="mx-auto mt-16 max-w-[1040px]">
        <ChannelSwitch value={channel} onChange={setChannel} />
        <LiveDemo channel={channel} />
      </Reveal>
    </section>
  );
}
