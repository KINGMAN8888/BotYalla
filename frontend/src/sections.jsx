import { useState, useEffect } from "react";
import { motion, AnimatePresence, useScroll, useSpring, useReducedMotion } from "motion/react";
import { BY, t, Icon, Reveal, Magnetic, GlassCard, Counter, num } from "./ui.jsx";
import Aurora from "./Aurora.jsx";
import Hero, { QR } from "./Hero.jsx";
import Journey from "./Journey.jsx";
import Channels from "./Channels.jsx";
import PricingPublic from "./PricingPublic.jsx";
import Trust from "./Trust.jsx";

/* ============================================================================
   الصفحة الرئيسية. الترتيب يجيب على أسئلة الزائر بالتتابع:
   ماذا أحصل؟ (البطل) ← هل هو حقيقي؟ (أرقام المنتج) ← كيف يبدو يومي معه؟
   (القصة) ← ماذا يفعل؟ (المميزات · القنوات) ← كيف أبدأ؟ ← بكم؟ ← أأثق فيه؟
   ← أسئلتي ← ابدأ.
   ========================================================================== */

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

/* رابط تخطٍّ للمحتوى — أول ما يصله مستخدم لوحة المفاتيح وقارئ الشاشة */
export function SkipLink() {
  return (
    // ثابت فوق حافة الشاشة ويهبط عند التركيز — لا sr-only: هامشه ‎-1px‎ يدفع
    // صندوقه بكسلاً خارج الحافة في RTL فيصنع تمريراً أفقياً على الجوال.
    // العنصر الثابت لا يدخل في حساب التمرير، وقارئ الشاشة يراه كما هو.
    <a href="#main"
       className="fixed top-3 start-3 z-[400] -translate-y-[300%] rounded-full bg-au-cyan px-5 py-2.5
                  font-extrabold text-[#07090F] no-underline transition-transform duration-300
                  focus:translate-y-0">
      {t("lp2_skip")}
    </a>
  );
}

/* ------------------------------------------------ حقائق المنتج (لا وعود) */
export function Facts() {
  const facts = BY.facts || [];
  return (
    <section aria-label={t("lp2_facts_label")} className="mx-auto max-w-[1240px] px-6">
      <Reveal>
        {/* 5 عناصر: على عمودين يمتد الأخير بعرض الصف بدل خانة فارغة بجانبه */}
        <div className="glass grid grid-cols-2 gap-px overflow-hidden rounded-[26px] sm:grid-cols-3 lg:grid-cols-5
                        [&>*:last-child]:col-span-2 sm:[&>*:last-child]:col-span-1">
          {facts.map((f, i) => {
            const m = String(f.v).match(/^(\d+)(.*)$/);
            return (
              <div key={i} className="bg-ob-0/40 px-5 py-7 text-center">
                <div className="display text-[clamp(30px,3.6vw,46px)] font-extrabold leading-none text-ink">
                  {m ? <><Counter value={Number(m[1])} />{m[2]}</> : f.v}
                </div>
                <div className="mt-2.5 text-[13px] leading-snug text-ink-3">{f.l}</div>
              </div>
            );
          })}
        </div>
      </Reveal>
    </section>
  );
}

/* --------------------------------------------------------- شريط منزلق */
export function Marquee() {
  const items = BY.templates || [];
  const doubled = [...items, ...items];
  return (
    <section aria-label={t("lp_tmpl_t")} className="py-12">
      <div className="marquee-wrap relative overflow-hidden
                      [mask-image:linear-gradient(90deg,transparent,#000_12%,#000_88%,transparent)]">
        <div className="marquee-row flex w-max gap-3.5">
          {doubled.map((x, i) => (
            <a key={i} href={BY.urls.register} tabIndex={i >= items.length ? -1 : undefined}
               aria-hidden={i >= items.length ? "true" : undefined}
               className="inline-flex items-center gap-2.5 whitespace-nowrap rounded-full bg-white/[0.04]
                          px-6 py-3.5 text-sm font-bold text-ink-2 no-underline
                          shadow-[inset_0_0_0_1px_rgb(255_255_255/0.09)]
                          transition-all duration-500 ease-[cubic-bezier(0.175,0.885,0.32,1.275)]
                          hover:-translate-y-0.5 hover:bg-au-violet/20 hover:text-white">
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
    "md:col-span-7 md:row-span-2", "md:col-span-5 md:row-span-2",
    "md:col-span-4", "md:col-span-4", "md:col-span-4",
    "md:col-span-6", "md:col-span-6",
    "md:col-span-8", "md:col-span-4",
  ];
  return (
    <section id="features" aria-labelledby="ft-t"
             className="scroll-mt-24 mx-auto max-w-[1240px] px-6 py-[clamp(64px,10vw,120px)]">
      <Reveal className="mb-14 max-w-[70ch]">
        <h2 id="ft-t" className="display m-0 mb-4 text-[clamp(28px,4.2vw,52px)] font-extrabold text-ink">
          {t("lp2_feats_t")}
        </h2>
        <p className="m-0 text-[clamp(14px,1.3vw,17px)] leading-[1.8] text-ink-2">{t("lp2_feats_sub")}</p>
      </Reveal>

      <div className="grid auto-rows-[minmax(128px,auto)] grid-cols-1 gap-4 md:grid-cols-12">
        {cards.map((c, i) => (
          <Reveal key={i} delay={(i % 3) * 0.08} className={spans[i] || "md:col-span-4"}>
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
              <h3 className="m-0 text-xl font-extrabold text-ink">{c.t}</h3>
              <p className="m-0 text-[14.5px] leading-[1.75] text-ink-2">{c.d}</p>
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
  const authed = !!(BY.auth && BY.auth.in);
  return (
    <section id="how" aria-labelledby="how-t"
             className="scroll-mt-24 mx-auto max-w-[1240px] px-6 py-[clamp(64px,10vw,120px)]">
      <div className="grid grid-cols-1 items-start gap-14 lg:grid-cols-2">
        <Reveal className="lg:sticky lg:top-28">
          <h2 id="how-t" className="display m-0 mb-4 text-[clamp(28px,4.2vw,52px)] font-extrabold text-ink">
            {t("lp_how_t")}
          </h2>
          <p className="m-0 text-[clamp(14px,1.3vw,17px)] leading-[1.8] text-ink-2">{t("lp_how_sub")}</p>
          <p className="m-0 mt-5 flex items-start gap-2.5 text-[14px] leading-[1.75] text-ink-3">
            <img src="/static/whatsapp.png" alt="WhatsApp" className="mt-1 size-4 object-contain inline-block" />{t("lp2_how_wa")}
          </p>
          <div className="mt-8">
            <Magnetic href={authed ? BY.urls.dashboard : BY.urls.register} icon="rocket">
              {authed ? t("lp2_nav_dashboard") : t("get_started_free")}
            </Magnetic>
          </div>
        </Reveal>

        <ol className="m-0 list-none p-0">
          {steps.map((s, i) => (
            <li key={i}>
              <Reveal delay={i * 0.09}>
                <GlassCard className="mb-5 rounded-[26px] p-8">
                  <span className="wide-cap mb-3.5 block text-[12px] font-extrabold text-au-cyan">
                    {BY.lang === "ar" ? `خطوة ${i + 1}` : `Step ${i + 1}`}
                  </span>
                  <h3 className="m-0 mb-3 text-[23px] font-extrabold text-ink">{s.t}</h3>
                  <p className="m-0 text-[15px] leading-[1.8] text-ink-2">{s.d}</p>
                </GlassCard>
              </Reveal>
            </li>
          ))}
        </ol>
      </div>
    </section>
  );
}

/* --------------------------------------------------------- الأسئلة الشائعة */
export function FAQ() {
  const qa = BY.faq || [];
  const [open, setOpen] = useState(0);
  const reduce = useReducedMotion();

  return (
    <section id="faq" aria-labelledby="faq-t"
             className="scroll-mt-24 mx-auto max-w-[900px] px-6 py-[clamp(64px,10vw,120px)]">
      <Reveal className="mb-14 text-center">
        <h2 id="faq-t" className="display m-0 text-[clamp(28px,4.2vw,52px)] font-extrabold text-ink">
          {t("lp_faq_t")}
        </h2>
      </Reveal>

      {qa.map((x, i) => {
        const isOpen = open === i;
        return (
          <Reveal key={i} delay={Math.min(i, 4) * 0.05}>
            <div className={"mb-3 overflow-hidden rounded-[20px] shadow-[inset_0_0_0_1px_rgb(255_255_255/0.09)] " +
                            "transition-colors duration-500 " + (isOpen ? "bg-white/[0.05]" : "bg-white/[0.028]")}>
              <h3 className="m-0">
                <button type="button" aria-expanded={isOpen} aria-controls={`faq-a-${i}`}
                        onClick={() => setOpen(isOpen ? -1 : i)}
                        className="flex w-full cursor-pointer items-center justify-between gap-5 bg-transparent
                                   px-7 py-6 text-start text-[16.5px] font-bold text-ink">
                  <span>{x.q}</span>
                  <motion.span aria-hidden="true" animate={{ rotate: isOpen ? -135 : 45 }}
                               transition={{ duration: 0.5, ease: [0.175, 0.885, 0.32, 1.275] }}
                               className="block size-[13px] shrink-0 border-b-2 border-e-2 border-au-cyan" />
                </button>
              </h3>
              <AnimatePresence initial={false}>
                {isOpen && (
                  <motion.div key="a" id={`faq-a-${i}`}
                              initial={reduce ? false : { height: 0, opacity: 0 }}
                              animate={{ height: "auto", opacity: 1 }}
                              exit={reduce ? {} : { height: 0, opacity: 0 }}
                              transition={{ duration: 0.45, ease: [0.16, 1, 0.3, 1] }}
                              className="overflow-hidden">
                    <p className="m-0 max-w-[78ch] px-7 pb-7 text-[15px] leading-[1.85] text-ink-2">
                      {String(x.a).replace("{price}", num(BY.mktPrice))}
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
  const authed = !!(BY.auth && BY.auth.in);
  return (
    <section aria-labelledby="fin-t" className="mx-auto max-w-[1240px] px-6 pb-[clamp(64px,10vw,120px)]">
      <Reveal>
        <GlassCard spot={false} className="rounded-[34px] px-8 py-[clamp(56px,9vw,110px)] text-center">
          <div aria-hidden="true"
               className="pointer-events-none absolute inset-0
                          bg-[radial-gradient(70%_130%_at_50%_0%,rgb(124_108_246/0.32),transparent_62%),radial-gradient(50%_100%_at_82%_100%,rgb(34_211_238/0.2),transparent_60%)]" />
          <div className="relative">
            <h2 id="fin-t" className="display m-0 mx-auto mb-5 max-w-[20ch] text-[clamp(30px,5vw,62px)] font-extrabold text-ink">
              {t("lp2_final_t")}
            </h2>
            <p className="mx-auto mb-9 max-w-[52ch] text-[clamp(15px,1.5vw,19px)] leading-[1.8] text-ink-2">
              {t("lp2_final_sub")}
            </p>
            <div className="flex flex-wrap justify-center gap-3.5">
              {authed ? (
                <Magnetic href={BY.urls.dashboard} icon="rocket">{t("lp2_nav_dashboard")}</Magnetic>
              ) : (
                <>
                  <Magnetic href={BY.urls.register} icon="rocket">{t("get_started_free")}</Magnetic>
                  <Magnetic href={BY.urls.login} variant="ghost">{t("signin_link")}</Magnetic>
                </>
              )}
            </div>
            {/* الضمانات هنا لا في البطل: البطل للتجربة، والقرار يُتّخذ عند النداء الأخير */}
            <ul className="m-0 mt-8 flex list-none flex-wrap justify-center gap-2 p-0">
              {["lp2_trust_1", "lp2_trust_2", "lp2_trust_3", "lp2_trust_4"].map((k) => (
                <li key={k}
                    className="inline-flex items-center gap-1.5 rounded-full bg-white/[0.04] px-3 py-1.5 text-[12.5px]
                               font-bold text-ink-2 shadow-[inset_0_0_0_1px_rgb(255_255_255/0.08)]">
                  <Icon name="check" size={13} className="text-au-teal" />{t(k)}
                </li>
              ))}
            </ul>
          </div>
        </GlassCard>
      </Reveal>
    </section>
  );
}

/* ------------------------------------------------------------ شريط التنقّل
   على الجوال: الشعار واللغة وزرّ القائمة فقط — لا زرّ أيقونة غامض بلا نص.
   القائمة ورقة تحريرية مرقّمة، وفي آخرها «ابدأ مجاناً» بعرض الشاشة. */
export function Nav() {
  const [solid, setSolid] = useState(false);
  const [open, setOpen] = useState(false);
  const authed = !!(BY.auth && BY.auth.in);
  const home = BY.urls.home;
  const links = [["#features", "lp2_nav_features"], ["#how", "lp2_nav_how"],
                 ["#pricing", "lp2_nav_pricing"], ["#faq", "lp2_nav_faq"]]
    .map(([h, k]) => ({ h: home + h, l: t(k) }));

  useEffect(() => {
    const onScroll = () => setSolid(window.scrollY > 24);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);
  useEffect(() => {
    if (!open) return;
    const esc = (e) => { if (e.key === "Escape") setOpen(false); };
    document.addEventListener("keydown", esc);
    return () => document.removeEventListener("keydown", esc);
  }, [open]);

  return (
    <header className={"sticky top-0 z-[200] transition-colors duration-500 " +
      (solid || open ? "bg-ob-0/85 backdrop-blur-xl backdrop-saturate-150 shadow-[0_1px_0_rgb(255_255_255/0.07)]"
                     : "bg-transparent")}>
      <div className="mx-auto flex max-w-[1320px] items-center gap-3 px-5 py-3 sm:px-6 sm:py-4">
        <a href={home} className="flex shrink-0 items-center no-underline" aria-label={BY.brand}>
          <img src={BY.urls.logo} alt={BY.brand} className="h-8 w-auto sm:h-9" width="140" height="36" />
        </a>

        <nav aria-label={t("lp2_menu")} className="ms-6 hidden items-center gap-1 lg:flex">
          {links.map((x) => (
            <a key={x.h} href={x.h}
               className="rounded-full px-4 py-2 text-[14px] font-bold text-ink-2 no-underline transition-colors
                          hover:bg-white/5 hover:text-ink">
              {x.l}
            </a>
          ))}
        </nav>

        <div className="ms-auto flex items-center gap-2">
          <a href={BY.urls.lang} hrefLang={BY.lang === "ar" ? "en" : "ar"}
             className="inline-flex h-10 items-center gap-1.5 rounded-full px-3.5 text-[13px] font-extrabold text-ink-2
                        no-underline shadow-[inset_0_0_0_1px_rgb(255_255_255/0.1)] transition-colors hover:text-au-cyan">
            <Icon name="globe" size={15} />{BY.lang === "ar" ? "EN" : "ع"}
          </a>
          {authed ? (
            <a href={BY.urls.dashboard}
               className="hidden h-10 items-center gap-2 rounded-full bg-[linear-gradient(100deg,#8FE9FF,#B9AFFF)]
                          px-5 text-sm font-extrabold text-[#07090F] no-underline sm:inline-flex">
              <Icon name="grid" size={15} />{t("lp2_nav_dashboard")}
            </a>
          ) : (
            <>
              <a href={BY.urls.login}
                 className="hidden h-10 items-center rounded-full px-4 text-sm font-bold text-ink-2 no-underline
                            transition-colors hover:bg-white/5 hover:text-ink md:inline-flex">
                {t("login")}
              </a>
              <a href={BY.urls.register}
                 className="hidden h-10 items-center gap-2 rounded-full bg-[linear-gradient(100deg,#8FE9FF,#B9AFFF)]
                            px-5 text-sm font-extrabold text-[#07090F] no-underline
                            shadow-[0_8px_24px_-8px_rgb(124_108_246/0.8)] transition-transform duration-300
                            hover:-translate-y-0.5 sm:inline-flex">
                <Icon name="rocket" size={15} />{t("get_started_free")}
              </a>
            </>
          )}
          <button type="button" aria-expanded={open} aria-controls="mnav" onClick={() => setOpen(!open)}
                  aria-label={open ? t("lp2_close") : t("lp2_menu")}
                  className="grid size-10 place-items-center rounded-full text-ink
                             shadow-[inset_0_0_0_1px_rgb(255_255_255/0.1)] lg:hidden">
            <span className="relative block h-3 w-4">
              <i className={"absolute inset-x-0 top-0 block h-0.5 rounded bg-current transition-transform duration-300 " +
                            (open ? "translate-y-[5px] rotate-45" : "")} />
              <i className={"absolute inset-x-0 bottom-0 block h-0.5 rounded bg-current transition-transform duration-300 " +
                            (open ? "-translate-y-[5px] -rotate-45" : "")} />
            </span>
          </button>
        </div>
      </div>

      <AnimatePresence>
        {open && (
          <motion.div id="mnav"
                      initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }}
                      exit={{ opacity: 0, height: 0 }} transition={{ duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
                      className="overflow-hidden lg:hidden">
            <nav aria-label={t("lp2_menu")} className="mx-auto max-w-[1320px] px-5 pb-7 pt-1 sm:px-6">
              <ol className="m-0 list-none p-0">
                {links.map((x, i) => (
                  <li key={x.h} className="shadow-[inset_0_-1px_0_rgb(255_255_255/0.07)]">
                    <a href={x.h} onClick={() => setOpen(false)}
                       className="flex items-baseline gap-4 py-4 no-underline">
                      <span className="tnum text-[12px] font-extrabold text-au-cyan">0{i + 1}</span>
                      <span className="display text-[24px] font-extrabold text-ink">{x.l}</span>
                    </a>
                  </li>
                ))}
              </ol>
              <div className="mt-6 grid gap-2.5">
                <a href={authed ? BY.urls.dashboard : BY.urls.register}
                   className="flex items-center justify-center gap-2 rounded-2xl bg-[linear-gradient(100deg,#8FE9FF,#B9AFFF)]
                              py-3.5 text-[15px] font-extrabold text-[#07090F] no-underline">
                  <Icon name="rocket" size={17} />{authed ? t("lp2_nav_dashboard") : t("get_started_free")}
                </a>
                {!authed && (
                  <a href={BY.urls.login}
                     className="flex items-center justify-center rounded-2xl py-3.5 text-[15px] font-bold text-ink
                                no-underline shadow-[inset_0_0_0_1px_rgb(255_255_255/0.14)]">
                    {t("login")}
                  </a>
                )}
              </div>
            </nav>
          </motion.div>
        )}
      </AnimatePresence>
    </header>
  );
}

/* ------------------------------------------------------------------ التذييل
   التذييل محادثة — لأن المنتج نفسه محادثة. مساعد BotYalla يحيّي من وصل لآخر
   الصفحة، والروابط الأساسية أزرار «ردّ سريع» كلوحة أزرار البوت، ثم الروابط
   والسياسات كرقائق، ثم كلمة «BotYalla» عملاقة تذوب في الخلفية تختم الصفحة.
   كل شيء في المنتصف — على الجوال وعلى الشاشات الواسعة. */
export function Footer() {
  const home = BY.urls.home;
  const authed = !!(BY.auth && BY.auth.in);
  const contact = BY.contact || [];
  const wa = contact.find((c) => String(c.h).startsWith("https://wa.me/"));
  const mail = contact.find((c) => String(c.h).startsWith("mailto:"));
  const replies = [
    { h: authed ? BY.urls.dashboard : BY.urls.register, icon: "rocket", primary: true,
      l: authed ? t("lp2_nav_dashboard") : t("get_started_free") },
    wa && { h: wa.h, l: t("lp2_foot_wa"), icon: "phone", ext: true },
    mail && { h: mail.h, l: t("lp2_foot_mail"), icon: "link" },
    { h: home + "#pricing", l: t("lp2_cta_secondary"), icon: "tag" },
  ].filter(Boolean);
  const product = [[home + "#features", "lp2_nav_features"], [home + "#how", "lp2_nav_how"],
                   [home + "#pricing", "lp2_nav_pricing"], [home + "#faq", "lp2_nav_faq"],
                   [BY.urls.login, "login"]];

  return (
    <footer className="relative mt-20 overflow-hidden">
      <div aria-hidden="true"
           className="pointer-events-none absolute inset-x-0 top-0 h-px
                      bg-[linear-gradient(90deg,transparent,rgb(124_108_246/0.6),rgb(34_211_238/0.6),transparent)]" />
      <div aria-hidden="true"
           className="pointer-events-none absolute left-1/2 top-0 -z-10 h-[440px] w-[760px] max-w-[150vw] -translate-x-1/2
                      rounded-full bg-[radial-gradient(closest-side,rgb(124_108_246/0.22),transparent)] blur-2xl" />

      <div className="mx-auto flex max-w-[860px] flex-col items-center px-5 pt-20 text-center sm:px-6">
        <Reveal className="flex w-full flex-col items-center">
          <div className="relative">
            <span className="glass grid size-[68px] place-items-center rounded-[22px]">
              <img src={BY.urls.mark} alt="" className="h-10 w-auto" width="40" height="42" loading="lazy" />
            </span>
            <span className="absolute -bottom-0.5 -end-0.5 size-4 rounded-full border-[3px] border-ob-0 bg-au-teal" />
          </div>
          <div className="mt-3 text-[14px] font-extrabold text-ink">{t("lp2_foot_bot")}</div>
          <div className="mt-0.5 text-[12px] font-bold text-au-teal">{t("lp2_foot_online")}</div>

          <p className="glass mx-auto mt-5 mb-0 max-w-[440px] rounded-[24px] px-6 py-4 text-[15.5px] leading-[1.8] text-ink">
            {t("lp2_foot_hi")}
          </p>

          <div className="mt-5 flex max-w-[560px] flex-wrap justify-center gap-2.5">
            {replies.map((r, i) => (
              <a key={i} href={r.h} {...(r.ext ? { target: "_blank", rel: "noopener" } : {})}
                 className={"inline-flex items-center gap-2 rounded-full px-5 py-3 text-[14px] font-extrabold no-underline " +
                   "transition-transform duration-300 hover:-translate-y-0.5 " +
                   (r.primary
                     ? "bg-[linear-gradient(100deg,#8FE9FF,#B9AFFF)] text-[#07090F] shadow-[0_12px_30px_-10px_rgb(124_108_246/0.8)]"
                     : "bg-white/[0.05] text-ink shadow-[inset_0_0_0_1px_rgb(255_255_255/0.14)] hover:bg-white/10")}>
                <Icon name={r.icon} size={16} />{r.l}
              </a>
            ))}
          </div>
        </Reveal>

        <p className="mx-auto mt-14 mb-0 max-w-[46ch] text-[14px] leading-[1.85] text-ink-3">{t("lp2_foot_tag")}</p>

        <nav aria-label={t("lp2_foot_product")} className="mt-7 flex flex-wrap justify-center gap-x-1 gap-y-1.5">
          {product.map(([h, k]) => (
            <a key={h} href={h}
               className="rounded-full px-3.5 py-1.5 text-[14px] font-bold text-ink-2 no-underline transition-colors
                          hover:bg-white/5 hover:text-ink">
              {t(k)}
            </a>
          ))}
        </nav>

        <nav aria-label={t("lp2_foot_legal")} className="mt-4 flex flex-wrap justify-center gap-2">
          {(BY.legalDocs || []).map((d) => (
            <a key={d.id} href={d.url}
               className="rounded-full bg-white/[0.035] px-3.5 py-1.5 text-[12.5px] font-bold text-ink-3 no-underline
                          shadow-[inset_0_0_0_1px_rgb(255_255_255/0.08)] transition-colors hover:text-ink">
              {d.title}
            </a>
          ))}
        </nav>

        <div className="mt-10 flex flex-col items-center gap-1.5 text-[12.5px] text-ink-4">
          <span>© {BY.year} {BY.brand} — {t("lp2_foot_rights")}</span>
          <span>
            {t("lp2_foot_by")}{" "}
            <a href="https://youssefalsherief.tech/" target="_blank" rel="noopener"
               className="font-bold text-ink-3 no-underline transition-colors hover:text-au-cyan">Youssef Alsherief</a>
          </span>
        </div>
      </div>

      <div aria-hidden="true" dir="ltr" className="footer-mark mt-8 select-none text-center">BotYalla</div>
    </footer>
  );
}

/* زرّ ثابت على الجوال بعد البطل — النداء الأساسي لا يغيب عن الإبهام. ويختفي
   فور ظهور التذييل: هناك أزرار الردّ السريع، ولا معنى لنداءين فوق بعضهما. */
export function StickyCTA() {
  const [pastHero, setPastHero] = useState(false);
  const [footerIn, setFooterIn] = useState(false);
  const authed = !!(BY.auth && BY.auth.in);
  useEffect(() => {
    const on = () => setPastHero(window.scrollY > 640);
    on();
    window.addEventListener("scroll", on, { passive: true });
    let io = null;
    const f = document.querySelector("footer");
    if (f && "IntersectionObserver" in window) {
      io = new IntersectionObserver(([e]) => setFooterIn(e.isIntersecting));
      io.observe(f);
    }
    return () => { window.removeEventListener("scroll", on); if (io) io.disconnect(); };
  }, []);
  const show = pastHero && !footerIn;
  return (
    <AnimatePresence>
      {show && (
        <motion.div initial={{ y: 90, opacity: 0 }} animate={{ y: 0, opacity: 1 }} exit={{ y: 90, opacity: 0 }}
                    transition={{ type: "spring", stiffness: 380, damping: 34 }}
                    className="fixed inset-x-3 bottom-3 z-[250] md:hidden">
          <a href={authed ? BY.urls.dashboard : BY.urls.register}
             className="flex items-center justify-center gap-2 rounded-2xl bg-[linear-gradient(100deg,#8FE9FF,#B9AFFF)]
                        py-3.5 text-[15px] font-extrabold text-[#07090F] no-underline
                        shadow-[0_18px_40px_-12px_rgb(124_108_246/0.9)]">
            <Icon name="rocket" size={17} />{authed ? t("lp2_nav_dashboard") : t("get_started_free")}
          </a>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

/* ------------------------------------------------- البوتان الرسميان للمنصة
   رابط + QR لكل قناة من الخادم (`BY.officialBots`) — عرض حيّ للمنتج نفسه: الزائر يكلّم
   مساعدنا على واتساب/تليجرام قبل التسجيل. ما لم يُضبط بعد (بلا رقم أو يوزر) لا يُعرض. */
const OB_CH = {
  wa: { logo: "/static/whatsapp.png", title: "lp2_ob_wa_t", open: "lp2_ob_open_wa",
        ring: "shadow-[inset_0_0_0_1px_rgb(37_211_102/0.35)]", glow: "bg-[#25D366]/15",
        btn: "bg-[#25D366] text-[#07130b] hover:bg-[#2fe271]" },
  tg: { logo: "/static/Telegram.svg.png", title: "lp2_ob_tg_t", open: "lp2_ob_open_tg",
        ring: "shadow-[inset_0_0_0_1px_rgb(42_171_238/0.35)]", glow: "bg-[#2AABEE]/15",
        btn: "bg-[#2AABEE] text-[#04121b] hover:bg-[#45b8f2]" },
};

/* بطاقتا البوتين الرسميين (رابط + QR) — في الرئيسية وصفحات الشرائح بروابط الشريحة */
export function BotCards({ bots = {}, className = "mt-12" }) {
  const keys = ["wa", "tg"].filter((k) => bots[k]);
  if (!keys.length) return null;
  return (
      <div className={"mx-auto grid grid-cols-1 gap-5 " + className + " " + (keys.length > 1 ? "max-w-[980px] md:grid-cols-2" : "max-w-[480px]")}>
      {keys.map((k, i) => {
        const b = bots[k], c = OB_CH[k];
        return (
          <Reveal key={k} delay={i * 0.1}>
            <GlassCard className={"flex h-full flex-col items-center rounded-[28px] p-7 text-center " + c.ring}>
              <span aria-hidden className={"pointer-events-none absolute inset-x-0 -top-16 mx-auto size-48 rounded-full blur-3xl " + c.glow} />
              <img src={c.logo} alt="" className="relative size-12 object-contain" />
              <h3 className="relative m-0 mt-4 text-[21px] font-extrabold text-ink">{t(c.title)}</h3>
              <span dir="ltr" className="relative mt-1 text-[15px] font-bold text-ink-3">{b.handle}</span>
              {(b.qr || []).length > 0 && (
                <div className="relative mt-6 hidden flex-col items-center gap-2.5 sm:flex">
                  <div className="rounded-2xl bg-white p-2.5 shadow-[0_18px_40px_-18px_rgb(0_0_0/0.8)]">
                    <QR rows={b.qr} size={148} label={t(c.title)} />
                  </div>
                  <span className="text-[12.5px] font-bold text-ink-3">{t("lp2_ob_scan")}</span>
                </div>
              )}
              <a href={b.url} target="_blank" rel="noopener"
                 className={"relative mt-6 inline-flex w-full items-center justify-center gap-2 rounded-full px-6 py-3.5 " +
                            "text-[15.5px] font-extrabold no-underline transition-colors sm:w-auto " + c.btn}>
                <Icon name="chat" size={17} />{t(c.open)}
                <Icon name="arrow" size={16} className="rtl:-scale-x-100" />
              </a>
            </GlassCard>
          </Reveal>
        );
      })}
    </div>
  );
}

export function OfficialBots() {
  const bots = BY.officialBots || {};
  const keys = ["wa", "tg"].filter((k) => bots[k]);
  if (!keys.length) return null;
  // أيقونات المنصة لا إيموجي (قاعدة الواجهة) — كلها في _LANDING_ICONS
  const feats = [["lp2_ob_f1", "shield"], ["lp2_ob_f2", "chat"], ["lp2_ob_f3", "users"], ["lp2_ob_f4", "bolt"]];
  return (
    <section id="official" aria-labelledby="ob-t"
             className="scroll-mt-24 mx-auto max-w-[1240px] px-4 py-[clamp(56px,9vw,110px)] sm:px-6">
      <Reveal className="mx-auto max-w-[760px] text-center">
        <span className="wide-cap mb-3 inline-flex items-center gap-2 rounded-full bg-au-teal/12 px-3.5 py-1.5
                         text-[12px] font-extrabold text-au-teal">
          <Icon name="sparkles" size={13} />{t("lp2_ob_eyebrow")}
        </span>
        <h2 id="ob-t" className="display m-0 mb-4 text-[clamp(28px,4.2vw,50px)] font-extrabold text-ink">
          {t("lp2_ob_t")}
        </h2>
        <p className="m-0 text-[clamp(14px,1.3vw,17px)] leading-[1.8] text-ink-2">{t("lp2_ob_sub")}</p>
        <ul className="m-0 mt-6 flex list-none flex-wrap justify-center gap-2 p-0">
          {feats.map(([k, ic]) => (
            <li key={k} className="inline-flex items-center gap-1.5 rounded-full bg-white/[0.04] px-3.5 py-1.5
                                   text-[13px] font-bold text-ink-2 shadow-[inset_0_0_0_1px_rgb(255_255_255/0.08)]">
              <Icon name={ic} size={14} className="text-au-cyan" />{t(k)}
            </li>
          ))}
        </ul>
      </Reveal>

      <BotCards bots={bots} />
      {(BY.segments || []).length > 0 && (
        <nav aria-label={t("lp2_seg_for_you")} className="mt-10 text-center">
          <div className="mb-3.5 text-[13px] font-extrabold text-ink-3">{t("lp2_seg_for_you")}</div>
          <div className="flex flex-wrap justify-center gap-2.5">
            {BY.segments.map((o) => (
              <a key={o.code} href={o.url}
                 className="inline-flex items-center gap-2 rounded-full bg-white/[0.04] px-4 py-2 text-[13.5px] font-bold
                            text-ink-2 no-underline shadow-[inset_0_0_0_1px_rgb(255_255_255/0.09)] hover:text-ink">
                <Icon name={o.icon} size={15} className="text-au-cyan" />{o.name}
              </a>
            ))}
          </div>
        </nav>
      )}
    </section>
  );
}

/* ------------------------------------------------------------- التطبيق */
export default function App() {
  return (
    <>
      <SkipLink />
      <ReadBar />
      <Aurora />
      <Nav />
      <main id="main">
        <Hero />
        <Facts />
        <OfficialBots />
        <Marquee />
        <Journey />
        <Bento />
        <Channels />
        <Steps />
        <PricingPublic />
        <Trust />
        <FAQ />
        <Finale />
      </main>
      <Footer />
      <StickyCTA />
    </>
  );
}
