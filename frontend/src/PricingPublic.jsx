import { useState } from "react";
import { motion } from "motion/react";
import { BY, t, Icon, Reveal, GlassCard, fill, num } from "./ui.jsx";

/* ============================================================================
   الأسعار العامة. كل رقم هنا من الخادم (`priced_plans`): تجاوزات المالك وخصم
   الباقة وسعر السنة — لا رقم مكتوب في الواجهة. المبدّل عرضٌ فقط؛ المبلغ الذي
   يُدفع يعيد الخادم حسابه عند الاشتراك (AGENTS.md §3.3).
   ========================================================================== */

export default function PricingPublic() {
  const plans = BY.plans || [];
  const [cycle, setCycle] = useState("monthly");
  const annual = cycle === "annual";
  const top = plans.reduce((m, p) => Math.max(m, p.annual_saving_pct || 0), 0);
  const authed = !!(BY.auth && BY.auth.in);

  const href = (p) => {
    if (p.id === "free") return authed ? BY.urls.dashboard : BY.urls.register;
    return authed ? `${BY.urls.subscribe}${p.id}?cycle=${cycle}` : BY.urls.register;
  };

  return (
    <section id="pricing" aria-labelledby="pr-t"
             className="scroll-mt-24 mx-auto max-w-[1320px] px-6 py-[clamp(64px,10vw,120px)]">
      <Reveal className="mx-auto mb-10 max-w-[64ch] text-center">
        <h2 id="pr-t" className="display m-0 mb-4 text-[clamp(28px,4.2vw,52px)] font-extrabold text-ink">
          {t("lp2_pr_t")}
        </h2>
        <p className="m-0 text-[clamp(14px,1.3vw,17px)] leading-[1.8] text-ink-2">{t("lp2_pr_sub")}</p>
      </Reveal>

      <div className="mb-12 flex flex-col items-center gap-3">
        <div role="tablist" aria-label={t("lp2_pr_t")}
             className="inline-flex rounded-full bg-black/30 p-1 shadow-[inset_0_0_0_1px_rgb(255_255_255/0.1)]">
          {["monthly", "annual"].map((c) => (
            <button key={c} type="button" role="tab" aria-selected={cycle === c} onClick={() => setCycle(c)}
                    className={"relative rounded-full px-6 py-2.5 text-[14px] font-extrabold transition-colors " +
                      (cycle === c ? "text-[#07090F]" : "text-ink-3 hover:text-ink-2")}>
              {cycle === c && (
                <motion.span layoutId="cyc-pill"
                  className="absolute inset-0 rounded-full bg-[linear-gradient(100deg,#8FE9FF,#B9AFFF)]"
                  transition={{ type: "spring", stiffness: 420, damping: 34 }} />
              )}
              <span className="relative">{t(c === "annual" ? "lp2_annual" : "lp2_monthly")}</span>
            </button>
          ))}
        </div>
        {top > 0 && (
          <span className="text-[13px] font-bold text-au-teal">{fill(t("lp2_save"), { n: top })}</span>
        )}
      </div>

      <div className="grid items-stretch gap-5 md:grid-cols-2 xl:grid-cols-4">
        {plans.map((p, i) => {
          const price = annual ? p.annual_price : p.price;
          const list = annual ? p.annual_list_price : p.list_price;
          const disc = annual ? p.annual_has_discount : p.has_discount;
          return (
            <Reveal key={p.id} delay={i * 0.07} className="h-full">
              <GlassCard className={"flex h-full flex-col rounded-[28px] p-7 " +
                  (p.hot ? "bg-[linear-gradient(165deg,rgb(124_108_246/0.22),rgb(34_211_238/0.07)_55%,transparent)] " +
                           "shadow-[0_30px_80px_-30px_rgb(124_108_246/0.75)]" : "")}>
                <div className="flex items-center justify-between gap-3">
                  <h3 className="m-0 text-[20px] font-extrabold text-ink">{p.name}</h3>
                  {p.hot && (
                    <span className="rounded-full bg-[linear-gradient(100deg,#8FE9FF,#B9AFFF)] px-3 py-1
                                     text-[11.5px] font-extrabold text-[#07090F]">{t("lp2_popular")}</span>
                  )}
                </div>

                <div className="mt-6 min-h-[92px]">
                  {!price ? (
                    <div className="display text-[42px] font-extrabold leading-none text-ink">{t("lp2_free_price")}</div>
                  ) : (
                    <>
                      {disc && <s className="block text-[15px] text-ink-4">{num(list)} {t("lp2_egp")}</s>}
                      <div className="flex items-baseline gap-1.5">
                        <span className="display tnum text-[44px] font-extrabold leading-none text-ink">{num(price)}</span>
                        <span className="text-[14px] font-bold text-ink-3">
                          {t("lp2_egp")}{annual ? t("lp2_per_year") : t("lp2_per_month")}
                        </span>
                      </div>
                      <div className="mt-2 min-h-[20px] text-[12.5px] font-bold text-au-teal">
                        {annual && p.annual_monthly_equiv
                          ? `${fill(t("lp2_equiv"), { n: num(p.annual_monthly_equiv) })}` +
                            (p.annual_saving_pct ? ` · ${fill(t("lp2_save"), { n: p.annual_saving_pct })}` : "")
                          : ""}
                      </div>
                    </>
                  )}
                </div>

                <ul className="mt-5 mb-8 flex list-none flex-col gap-2.5 p-0">
                  {(p.features || []).map((f, j) => (
                    <li key={j} className="flex items-start gap-2.5 text-[13.5px] leading-[1.6] text-ink-2">
                      <Icon name="check" size={15} className="mt-0.5 text-au-teal" />{f}
                    </li>
                  ))}
                </ul>

                <a href={href(p)}
                   className={"mt-auto inline-flex items-center justify-center gap-2 rounded-full px-6 py-3.5 " +
                     "text-[14.5px] font-extrabold no-underline transition-transform duration-300 hover:-translate-y-0.5 " +
                     (p.hot || p.id === "free"
                       ? "bg-[linear-gradient(100deg,#8FE9FF,#B9AFFF)] text-[#07090F] shadow-[0_12px_30px_-10px_rgb(124_108_246/0.8)]"
                       : "bg-white/[0.06] text-ink shadow-[inset_0_0_0_1px_rgb(255_255_255/0.14)] hover:bg-white/10")}>
                  <Icon name={p.id === "free" ? "rocket" : "card"} size={16} />
                  {p.id === "free" ? t("get_started_free") : t("lp2_choose")}
                </a>
              </GlassCard>
            </Reveal>
          );
        })}
      </div>

      {/* ثلاث ضمانات تجيب على «وإيه كمان؟» قبل أن تُسأل */}
      <div className="mt-10 grid gap-4 md:grid-cols-3">
        <Note icon="wallet" title={t("lp2_carry_t")} text={t("lp2_carry_d")} />
        <Note icon="megaphone" title={t("lp2_wallet_t")}
              text={fill(t("lp2_wallet_d"), { price: num(BY.mktPrice) })} />
        <Note icon="card" title={t("lp2_pay_t")} text={t("lp2_pay_note")}>
          <div className="mt-3 flex flex-wrap gap-2">
            {[t("lp2_pay_vf"), t("lp2_pay_ip"), t("lp2_pay_bank")].map((m, i) => (
              <span key={i} className="rounded-full bg-white/[0.06] px-3 py-1 text-[12px] font-bold text-ink-2
                                       shadow-[inset_0_0_0_1px_rgb(255_255_255/0.1)]">{m}</span>
            ))}
          </div>
        </Note>
      </div>
    </section>
  );
}

function Note({ icon, title, text, children }) {
  return (
    <Reveal className="h-full">
      <div className="h-full rounded-[22px] bg-white/[0.03] p-6 shadow-[inset_0_0_0_1px_rgb(255_255_255/0.08)]">
        <div className="flex items-center gap-2.5">
          <Icon name={icon} size={18} className="text-au-cyan" />
          <h3 className="m-0 text-[15px] font-extrabold text-ink">{title}</h3>
        </div>
        <p className="m-0 mt-2.5 text-[13.5px] leading-[1.75] text-ink-2">{text}</p>
        {children}
      </div>
    </Reveal>
  );
}
