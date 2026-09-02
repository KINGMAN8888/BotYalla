import { useState, useRef, useEffect } from "react";
import { motion, AnimatePresence, useScroll, useSpring, useReducedMotion } from "motion/react";
import { BY, t, Icon, Reveal, Magnetic, GlassCard, useSpotlight } from "./ui.jsx";
import Backdrop from "./Backdrop.jsx";
import Hero from "./Hero.jsx";

/* الخلفية التفاعلية انتقلت إلى Backdrop.jsx — النسخة السابقة كانت تعتمد على
   أدوات inset سالبة لم تُطبَّق فانهارت الطبقة إلى 0×0 ولم يظهر منها شيء. */

/* ------------------------------------------------------ شريط تقدّم القراءة */
export function ReadBar() {
  const { scrollYProgress } = useScroll();
  const x = useSpring(scrollYProgress, { stiffness: 240, damping: 40, restDelta: 0.001 });
  const reduce = useReducedMotion();
  if (reduce) return null;
  return (
    <motion.div
      style={{ scaleX: x, transformOrigin: BY.dir === "rtl" ? "right" : "left" }}
      className="fixed inset-x-0 top-0 z-[300] h-0.5 bg-[linear-gradient(90deg,#7C6CF6,#22D3EE)]
                 shadow-[0_0_14px_rgb(34_211_238/0.85)]"
    />
  );
}


/* --------------------------------------------------------- شريط منزلق */
export function Marquee() {
  const items = BY.templates || [];
  const doubled = [...items, ...items];
  return (
    <section className="py-10">
      <div className="marquee-wrap relative overflow-hidden
                      [mask-image:linear-gradient(90deg,transparent,#000_12%,#000_88%,transparent)]">
        <div className="marquee-row flex w-max gap-3.5">
          {doubled.map((x, i) => (
            <a
              key={i}
              href={BY.urls.register}
              className="inline-flex items-center gap-2.5 whitespace-nowrap rounded-full bg-white/[0.04]
                         px-6 py-3.5 text-sm font-bold text-ink-2 no-underline
                         shadow-[inset_0_0_0_1px_rgb(255_255_255/0.09)]
                         transition-all duration-500 ease-[cubic-bezier(0.175,0.885,0.32,1.275)]
                         hover:-translate-y-0.5 hover:bg-au-violet/20 hover:text-white
                         hover:shadow-[inset_0_0_0_1px_rgb(124_108_246/0.45)]"
            >
              <Icon name={x.icon} size={16} className="text-au-cyan" />
              {x.name}
            </a>
          ))}
        </div>
      </div>
    </section>
  );
}

/* ------------------------------------------------------ بينتو غير متماثل */
export function Bento() {
  const cards = BY.bento || [];
  const spans = [
    "md:col-span-7 md:row-span-2",
    "md:col-span-5 md:row-span-2",
    "md:col-span-4",
    "md:col-span-4",
    "md:col-span-4",
  ];
  return (
    <section className="mx-auto max-w-[1240px] px-6 py-[clamp(64px,10vw,120px)]">
      <Reveal className="mb-14 max-w-[70ch]">
        <h2 className="tight m-0 mb-4 text-[clamp(28px,4.2vw,52px)] font-extrabold text-ink">
          {t("lp_feats_t")}
        </h2>
        <p className="m-0 text-[clamp(14px,1.3vw,17px)] leading-relaxed text-ink-2">
          {t("lp_feats_sub")}
        </p>
      </Reveal>

      <div className="grid auto-rows-[minmax(126px,auto)] grid-cols-1 gap-4 md:grid-cols-12">
        {cards.map((c, i) => (
          <Reveal key={i} delay={(i % 3) * 0.09} className={spans[i] || "md:col-span-4"}>
            <GlassCard className="group flex h-full flex-col justify-end gap-3 rounded-[26px] p-8
                                  transition-transform duration-700 ease-[cubic-bezier(0.16,1,0.3,1)]
                                  hover:-translate-y-1.5">
              <span aria-hidden="true"
                    className="pointer-events-none absolute -top-6 -end-1.5 text-[150px] font-extrabold
                               leading-none tracking-tighter text-white/[0.028]">
                0{i + 1}
              </span>
              <span className="mb-auto grid size-[46px] place-items-center rounded-[14px] text-au-cyan
                               bg-[linear-gradient(150deg,rgb(124_108_246/0.28),rgb(34_211_238/0.12))]
                               shadow-[inset_0_0_0_1px_rgb(255_255_255/0.09)]
                               transition-transform duration-600 ease-[cubic-bezier(0.175,0.885,0.32,1.275)]
                               group-hover:-rotate-6 group-hover:scale-110">
                <Icon name={c.icon} size={22} />
              </span>
              <h3 className="m-0 text-xl font-extrabold tracking-tight text-ink">{c.t}</h3>
              <p className="m-0 text-[14.5px] leading-relaxed text-ink-2">{c.d}</p>
            </GlassCard>
          </Reveal>
        ))}
      </div>
    </section>
  );
}

/* ---------------------------------------------------- الخطوات (سكة لاصقة) */
export function Steps() {
  const steps = BY.steps || [];
  return (
    <section className="mx-auto max-w-[1240px] px-6 py-[clamp(64px,10vw,120px)]">
      <div className="grid items-start gap-14 lg:grid-cols-2">
        <Reveal className="lg:sticky lg:top-28">
          <h2 className="tight m-0 mb-4 text-[clamp(28px,4.2vw,52px)] font-extrabold text-ink">
            {t("lp_how_t")}
          </h2>
          <p className="m-0 text-[clamp(14px,1.3vw,17px)] leading-relaxed text-ink-2">
            {t("lp_how_sub")}
          </p>
          <div className="mt-8">
            <Magnetic href={BY.urls.register} icon="rocket">{t("get_started_free")}</Magnetic>
          </div>
        </Reveal>

        <div>
          {steps.map((s, i) => (
            <Reveal key={i} delay={i * 0.09}>
              <GlassCard className="mb-5 rounded-[26px] p-8">
                <span className="wide-cap mb-3.5 block text-[12px] font-extrabold text-au-cyan">
                  {BY.lang === "ar" ? `خطوة ${i + 1}` : `Step ${i + 1}`}
                </span>
                <h3 className="m-0 mb-3 text-[23px] font-extrabold tracking-tight text-ink">{s.t}</h3>
                <p className="m-0 text-[15px] leading-[1.72] text-ink-2">{s.d}</p>
              </GlassCard>
            </Reveal>
          ))}
        </div>
      </div>
    </section>
  );
}

/* --------------------------------------------------------- الأسئلة الشائعة */
export function FAQ() {
  const qa = BY.faq || [];
  const [open, setOpen] = useState(-1);
  const reduce = useReducedMotion();

  return (
    <section className="mx-auto max-w-[900px] px-6 py-[clamp(64px,10vw,120px)]">
      <Reveal className="mb-14 text-center">
        <h2 className="tight m-0 text-[clamp(28px,4.2vw,52px)] font-extrabold text-ink">
          {t("lp_faq_t")}
        </h2>
      </Reveal>

      {qa.map((x, i) => {
        const isOpen = open === i;
        return (
          <Reveal key={i} delay={Math.min(i, 4) * 0.06}>
            <div
              className={
                "mb-3 overflow-hidden rounded-[20px] shadow-[inset_0_0_0_1px_rgb(255_255_255/0.09)] " +
                "transition-colors duration-500 " +
                (isOpen ? "bg-white/[0.05]" : "bg-white/[0.028]")
              }
            >
              <button
                type="button"
                aria-expanded={isOpen}
                onClick={() => setOpen(isOpen ? -1 : i)}
                className="flex w-full cursor-pointer items-center justify-between gap-5 bg-transparent
                           px-7 py-6 text-start text-[16.5px] font-bold text-ink"
              >
                <span>{x.q}</span>
                <motion.span
                  aria-hidden="true"
                  animate={{ rotate: isOpen ? -135 : 45 }}
                  transition={{ duration: 0.5, ease: [0.175, 0.885, 0.32, 1.275] }}
                  className="block size-[13px] shrink-0 border-b-2 border-e-2 border-au-cyan"
                />
              </button>

              <AnimatePresence initial={false}>
                {isOpen && (
                  <motion.div
                    key="a"
                    initial={reduce ? false : { height: 0, opacity: 0 }}
                    animate={{ height: "auto", opacity: 1 }}
                    exit={reduce ? {} : { height: 0, opacity: 0 }}
                    transition={{ duration: 0.45, ease: [0.16, 1, 0.3, 1] }}
                    className="overflow-hidden"
                  >
                    <p className="m-0 max-w-[78ch] px-7 pb-7 text-[15px] leading-[1.78] text-ink-2">
                      {x.a}
                    </p>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          </Reveal>
        );
      })}
    </section>
  );
}

/* ------------------------------------------------------------ نداء ختامي */
export function Finale() {
  return (
    <section className="mx-auto max-w-[1240px] px-6 pb-[clamp(64px,10vw,120px)]">
      <Reveal>
        <GlassCard
          spot={false}
          className="rounded-[34px] px-8 py-[clamp(56px,9vw,104px)] text-center"
        >
          <div aria-hidden="true"
               className="pointer-events-none absolute inset-0
                          bg-[radial-gradient(70%_130%_at_50%_0%,rgb(124_108_246/0.30),transparent_62%),radial-gradient(50%_100%_at_82%_100%,rgb(34_211_238/0.20),transparent_60%)]" />
          <div className="relative">
            <h2 className="tight m-0 mb-5 text-[clamp(30px,5vw,60px)] font-extrabold text-ink">
              {t("lp_final_t")}
            </h2>
            <p className="mx-auto mb-9 max-w-[52ch] text-[clamp(15px,1.5vw,19px)] leading-[1.75] text-ink-2">
              {t("lp_final_sub")}
            </p>
            <div className="flex flex-wrap justify-center gap-3.5">
              <Magnetic href={BY.urls.register} icon="rocket">{t("get_started_free")}</Magnetic>
              <Magnetic href={BY.urls.login} variant="ghost">{t("signin_link")}</Magnetic>
            </div>
          </div>
        </GlassCard>
      </Reveal>
    </section>
  );
}

/* ------------------------------------------------------------- التطبيق */
export default function App() {
  return (
    <>
      <ReadBar />
      <Backdrop />
      <Nav />
      <Hero />
      <Marquee />
      <Bento />
      <Steps />
      <FAQ />
      <Finale />
      <Footer />
    </>
  );
}

/* ------------------------------------------------------------ شريط التنقّل */
export function Nav() {
  const [solid, setSolid] = useState(false);
  useEffect(() => {
    const onScroll = () => setSolid(window.scrollY > 24);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  return (
    <header
      className={
        "sticky top-0 z-[200] transition-all duration-500 " +
        (solid
          ? "bg-ob-0/75 backdrop-blur-xl backdrop-saturate-150 shadow-[0_1px_0_rgb(255_255_255/0.07)]"
          : "bg-transparent")
      }
    >
      <div className="mx-auto flex max-w-[1240px] items-center gap-4 px-6 py-4">
        <a href={BY.urls.home} className="flex items-center gap-2.5 no-underline">
          <img src={BY.urls.logo} alt={BY.brand} className="h-9 w-auto" />
        </a>

        <nav className="ms-auto flex items-center gap-1.5">
          <a
            href={BY.urls.pricing}
            className="hidden rounded-full px-4 py-2 text-sm font-bold text-ink-2 no-underline
                       transition-colors hover:bg-white/5 hover:text-ink sm:inline-flex"
          >
            {t("nav_pricing")}
          </a>
          <a
            href={BY.urls.lang}
            className="inline-flex items-center gap-1.5 rounded-full px-3.5 py-2 text-sm font-bold
                       text-ink-2 no-underline shadow-[inset_0_0_0_1px_rgb(255_255_255/0.1)]
                       transition-colors hover:text-au-cyan"
          >
            <Icon name="globe" size={15} />
            {BY.lang === "ar" ? "EN" : "ع"}
          </a>
          <a
            href={BY.urls.login}
            className="rounded-full px-4 py-2 text-sm font-bold text-ink-2 no-underline
                       transition-colors hover:bg-white/5 hover:text-ink"
          >
            {t("login")}
          </a>
          <a
            href={BY.urls.register}
            className="inline-flex items-center gap-2 rounded-full bg-[linear-gradient(100deg,#8FE9FF,#B9AFFF)]
                       px-5 py-2.5 text-sm font-extrabold text-[#07090F] no-underline
                       shadow-[0_8px_24px_-8px_rgb(124_108_246/0.8)] transition-transform duration-300
                       hover:-translate-y-0.5"
          >
            <Icon name="rocket" size={15} />
            <span className="hidden sm:inline">{t("get_started_free")}</span>
          </a>
        </nav>
      </div>
    </header>
  );
}

/* ------------------------------------------------------------------ التذييل */
export function Footer() {
  return (
    <footer className="mt-10 shadow-[inset_0_1px_0_rgb(255_255_255/0.07)]">
      <div className="mx-auto max-w-[1240px] px-6 py-14">
        <div className="grid gap-10 md:grid-cols-[2fr_1fr_1fr]">
          <div>
            <img src={BY.urls.logo} alt={BY.brand} className="h-9 w-auto" />
            <p className="mt-3.5 max-w-[320px] text-sm leading-relaxed text-ink-3">
              {t("brand_tag")}
            </p>
          </div>
          <div>
            <h4 className="mb-3 text-[13px] font-extrabold text-ink">
              {BY.lang === "ar" ? "المنتج" : "Product"}
            </h4>
            {[
              { h: BY.urls.pricing, l: t("nav_pricing") },
              { h: BY.urls.register, l: t("get_started_free") },
              { h: BY.urls.login, l: t("login") },
            ].map((x, i) => (
              <a key={i} href={x.h}
                 className="block py-1 text-sm text-ink-3 no-underline transition-colors hover:text-au-cyan">
                {x.l}
              </a>
            ))}
          </div>
          <div>
            <h4 className="mb-3 text-[13px] font-extrabold text-ink">
              {BY.lang === "ar" ? "تواصل" : "Contact"}
            </h4>
            {(BY.contact || []).map((c, i) => (
              <a key={i} href={c.h} target="_blank" rel="noopener"
                 className="block py-1 text-sm text-ink-3 no-underline transition-colors hover:text-au-cyan">
                {c.l}
              </a>
            ))}
          </div>
        </div>

        <div className="mt-10 flex flex-wrap items-center justify-between gap-4 pt-6
                        text-[13px] text-ink-3 shadow-[inset_0_1px_0_rgb(255_255_255/0.07)]">
          <span>© {BY.brand} — {BY.lang === "ar" ? "جميع الحقوق محفوظة" : "All rights reserved"}</span>
          <a href="https://youssefalsherief.tech/" target="_blank" rel="noopener"
             className="text-ink-3 no-underline transition-colors hover:text-au-cyan">
            Youssef Alsherief
          </a>
        </div>
      </div>
    </footer>
  );
}
