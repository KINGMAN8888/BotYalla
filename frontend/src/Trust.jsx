import { BY, t, Icon, Reveal } from "./ui.jsx";

/* الثقة بالحقائق لا بالشعارات: كل بند هنا شيء تفعله المنصة فعلاً ويمكن
   التحقق منه في الكود والاختبارات — لا شهادات مختلقة ولا أرقام عملاء وهمية. */
export default function Trust() {
  const items = BY.trust || [];
  return (
    <section id="trust" aria-labelledby="tr-t" className="mx-auto max-w-[1240px] px-6 py-[clamp(64px,10vw,120px)]">
      <Reveal className="mb-12 max-w-[64ch]">
        <h2 id="tr-t" className="display m-0 mb-4 text-[clamp(28px,4.2vw,52px)] font-extrabold text-ink">
          {t("lp2_trust_t")}
        </h2>
        <p className="m-0 text-[clamp(14px,1.3vw,17px)] leading-[1.8] text-ink-2">{t("lp2_trust_sub")}</p>
      </Reveal>
      <div className="grid grid-cols-1 gap-px overflow-hidden rounded-[28px] bg-white/[0.07] sm:grid-cols-2 lg:grid-cols-3">
        {items.map((x, i) => (
          <Reveal key={i} delay={(i % 3) * 0.07} className="h-full">
            <div className="group h-full bg-ob-0/85 p-7 transition-colors duration-500 hover:bg-ob-1/90">
              <span className="grid size-11 place-items-center rounded-[14px] text-au-cyan
                               bg-[linear-gradient(150deg,rgb(124_108_246/0.25),rgb(34_211_238/0.1))]
                               shadow-[inset_0_0_0_1px_rgb(255_255_255/0.08)]
                               transition-transform duration-500 group-hover:-rotate-6">
                <Icon name={x.icon} size={20} />
              </span>
              <h3 className="m-0 mt-5 mb-2 text-[17px] font-extrabold text-ink">{x.t}</h3>
              <p className="m-0 text-[14px] leading-[1.75] text-ink-2">{x.d}</p>
            </div>
          </Reveal>
        ))}
      </div>
    </section>
  );
}
