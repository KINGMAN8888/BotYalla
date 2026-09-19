import { useEffect, useState } from "react";
import { BY, t, Icon, Magnetic, fill } from "./ui.jsx";
import Aurora from "./Aurora.jsx";
import { Nav, Footer, ReadBar, SkipLink, BotCards } from "./sections.jsx";

/* ============================================================================
   صفحات الموقع العام غير الرئيسية: الوثائق القانونية وصفحة 404.
   نفس القشرة (تنقّل وتذييل وخلفية هادئة) — لا قشرة لوحة التحكم بقائمتها
   الجانبية التي لا يستطيع الزائر استعمالها.
   المحتوى نفسه مرسوم في الخادم أيضاً (public.html) فيُفهرَس ويُقرأ بلا جافاسكربت.
   ========================================================================== */

export function LegalPublic() {
  const L = BY.legal || { sections: [] };
  const docs = BY.legalDocs || [];
  const [active, setActive] = useState(L.sections[0] && L.sections[0].id);

  // فهرس يتبع القسم الظاهر
  useEffect(() => {
    if (!("IntersectionObserver" in window)) return;
    const io = new IntersectionObserver(
      (es) => es.forEach((e) => { if (e.isIntersecting) setActive(e.target.id); }),
      { rootMargin: "-20% 0px -70% 0px" }
    );
    L.sections.forEach((s) => { const el = document.getElementById(s.id); if (el) io.observe(el); });
    return () => io.disconnect();
  }, [L.sections]);

  return (
    <>
      <SkipLink />
      <ReadBar />
      <Aurora quiet />
      <Nav />
      <main id="main" className="mx-auto max-w-[1180px] px-6 pb-24 pt-8">
        <nav aria-label={t("lp2_foot_legal")} className="mb-10 flex flex-wrap gap-2">
          {docs.map((d) => (
            <a key={d.id} href={d.url} aria-current={d.id === L.id ? "page" : undefined}
               className={"rounded-full px-4 py-2 text-[13px] font-bold no-underline transition-colors " +
                 (d.id === L.id
                   ? "bg-[linear-gradient(100deg,#8FE9FF,#B9AFFF)] text-[#07090F]"
                   : "bg-white/[0.04] text-ink-2 shadow-[inset_0_0_0_1px_rgb(255_255_255/0.09)] hover:text-ink")}>
              {d.title}
            </a>
          ))}
        </nav>

        <header className="mb-12 max-w-[780px]">
          <h1 className="display m-0 mb-3 text-[clamp(32px,5vw,58px)] font-extrabold text-ink">{L.title}</h1>
          <p className="m-0 mb-5 text-[13px] font-bold text-ink-3">{t("legal_updated")}: {L.updated}</p>
          <p className="m-0 text-[clamp(15px,1.35vw,17.5px)] leading-[1.85] text-ink-2">{L.intro}</p>
        </header>

        <div className="grid grid-cols-1 gap-10 lg:grid-cols-[250px_minmax(0,1fr)]">
          <aside className="hidden lg:block">
            <div className="sticky top-28">
              <div className="mb-3 text-[12px] font-extrabold text-ink-3">{t("lp2_legal_toc")}</div>
              <ol className="m-0 flex list-none flex-col gap-0.5 p-0">
                {L.sections.map((s) => (
                  <li key={s.id}>
                    <a href={"#" + s.id}
                       className={"block rounded-xl px-3 py-2 text-[13px] leading-snug no-underline transition-colors " +
                         (active === s.id ? "bg-white/[0.07] font-bold text-ink" : "text-ink-3 hover:text-ink-2")}>
                      {s.h}
                    </a>
                  </li>
                ))}
              </ol>
            </div>
          </aside>

          <article className="glass legal-prose rounded-[28px] p-[clamp(22px,4vw,52px)]">
            {L.sections.map((s) => (
              <section key={s.id} id={s.id} className="scroll-mt-28">
                <h2>{s.h}</h2>
                {s.body.map((b, i) =>
                  Array.isArray(b)
                    ? <ul key={i}>{b.map((x, j) => <li key={j}>{x}</li>)}</ul>
                    : <p key={i}>{b}</p>
                )}
              </section>
            ))}
          </article>
        </div>

        <div className="mt-10 flex flex-wrap items-center justify-between gap-4 rounded-[24px] bg-white/[0.03] p-6
                        shadow-[inset_0_0_0_1px_rgb(255_255_255/0.08)]">
          <div>
            <div className="text-[15px] font-extrabold text-ink">{t("lp2_legal_q")}</div>
            <div className="mt-1 text-[13.5px] text-ink-2">{fill(t("lp2_legal_q_d"), { email: BY.email || "" })}</div>
          </div>
          <a href={"mailto:" + (BY.email || "")}
             className="inline-flex items-center gap-2 rounded-full bg-white/[0.06] px-5 py-2.5 text-[13.5px] font-extrabold
                        text-ink no-underline shadow-[inset_0_0_0_1px_rgb(255_255_255/0.14)] hover:bg-white/10">
            <Icon name="link" size={15} />{BY.email}
          </a>
        </div>
      </main>
      <Footer />
    </>
  );
}

export function NotFound() {
  return (
    <>
      <SkipLink />
      <Aurora />
      <Nav />
      <main id="main" className="mx-auto flex min-h-[72vh] max-w-[760px] flex-col items-center justify-center px-6 py-16 text-center">
        <div aria-hidden="true" className="display hue text-[clamp(110px,24vw,240px)] font-extrabold leading-none">404</div>
        <h1 className="display m-0 mt-4 mb-4 text-[clamp(26px,4vw,40px)] font-extrabold text-ink">{t("lp2_nf_t")}</h1>
        <p className="m-0 mb-9 max-w-[48ch] text-[16px] leading-[1.8] text-ink-2">{t("lp2_nf_d")}</p>
        <div className="flex flex-wrap justify-center gap-3.5">
          <Magnetic href={BY.urls.home} icon="back">{t("lp2_nf_home")}</Magnetic>
          <Magnetic href={BY.urls.home + "#pricing"} variant="ghost" icon="tag">{t("lp2_nav_pricing")}</Magnetic>
        </div>
      </main>
      <Footer />
    </>
  );
}

/* ------------------------------------------------------------ صفحة شريحة
   وجهة إعلانات كل نشاط (/for/<code>): المشكلة ← ما يفعله البوت ← المحادثة كما تبدو ←
   جرّبه الآن (البوت الرسمي برمز الشريحة) ← ابدأ مجاناً. كلها من segments.py في الخادم. */
export function SegmentPage() {
  const S = BY.segment || { pains: [], wins: [], demo: [], bots: {} };
  const reg = BY.urls.register + "?utm_source=seg_" + S.code;
  return (
    <>
      <SkipLink />
      <ReadBar />
      <Aurora quiet />
      <Nav />
      <main id="main">
        <section className="mx-auto max-w-[1100px] px-4 pb-16 pt-[clamp(20px,4vw,56px)] text-center sm:px-6">
          <span className="wide-cap inline-flex items-center gap-2 rounded-full bg-au-teal/12 px-3.5 py-1.5 text-[12.5px] font-extrabold text-au-teal">
            <Icon name={S.icon} size={14} />{t("lp2_seg_badge")} {S.name}
          </span>
          <h1 className="display mx-auto mt-5 mb-5 max-w-[26ch] text-[clamp(28px,4.4vw,54px)] font-extrabold text-ink">{S.h1}</h1>
          <p className="mx-auto m-0 max-w-[58ch] text-[clamp(15px,1.4vw,18px)] leading-[1.85] text-ink-2">{S.sub}</p>
          <div className="mt-8 flex flex-col items-center justify-center gap-3.5 sm:flex-row">
            <Magnetic href={reg} icon="rocket" className="w-full sm:w-auto">{t("get_started_free")}</Magnetic>
            {S.bots && S.bots.wa && (
              <a href={S.bots.wa.url} target="_blank" rel="noopener"
                 className="inline-flex w-full items-center justify-center gap-2 rounded-full bg-[#25D366] px-6 py-3.5 text-[15px] font-extrabold text-[#07130b] no-underline hover:bg-[#2fe271] sm:w-auto">
                <Icon name="chat" size={17} />{t("lp2_ob_open_wa")}
              </a>
            )}
          </div>
        </section>

        <section className="mx-auto grid max-w-[1100px] grid-cols-1 gap-5 px-4 pb-16 sm:px-6 lg:grid-cols-2">
          <div className="glass rounded-[26px] p-7">
            <h2 className="m-0 mb-5 text-[21px] font-extrabold text-ink">{t("lp2_seg_pains_t")}</h2>
            <ul className="m-0 flex list-none flex-col gap-3 p-0">
              {S.pains.map((x, i) => (
                <li key={i} className="flex items-start gap-3 text-[15px] leading-[1.7] text-ink-2">
                  <Icon name="close" size={16} className="mt-1 shrink-0 text-red-300" />{x}
                </li>
              ))}
            </ul>
          </div>
          <div className="glass rounded-[26px] p-7 shadow-[inset_0_0_0_1px_rgb(45_212_191/0.3)]">
            <h2 className="m-0 mb-5 text-[21px] font-extrabold text-ink">{t("lp2_seg_wins_t")}</h2>
            <ul className="m-0 flex list-none flex-col gap-3 p-0">
              {S.wins.map((x, i) => (
                <li key={i} className="flex items-start gap-3 text-[15px] leading-[1.7] text-ink-2">
                  <Icon name="check" size={16} className="mt-1 shrink-0 text-au-teal" />{x}
                </li>
              ))}
            </ul>
          </div>
        </section>

        <section aria-labelledby="seg-demo" className="mx-auto max-w-[640px] px-4 pb-16 sm:px-6">
          <h2 id="seg-demo" className="m-0 mb-5 text-center text-[21px] font-extrabold text-ink">{t("lp2_seg_demo_t")}</h2>
          <div className="glass flex flex-col gap-3 rounded-[26px] p-5">
            {S.demo.map((m, i) => (
              <div key={i} className={"max-w-[85%] rounded-2xl px-4 py-2.5 text-[14.5px] leading-[1.7] " +
                (m.me ? "self-start bg-[linear-gradient(100deg,#7C6CF6,#22D3EE)] text-white"
                      : "self-end bg-white/[0.06] text-ink shadow-[inset_0_0_0_1px_rgb(255_255_255/0.08)]")}>
                {m.text}
              </div>
            ))}
          </div>
        </section>

        {S.bots && (S.bots.wa || S.bots.tg) && (
          <section aria-labelledby="seg-try" className="mx-auto max-w-[1100px] px-4 pb-16 text-center sm:px-6">
            <h2 id="seg-try" className="display m-0 mb-3 text-[clamp(24px,3.4vw,40px)] font-extrabold text-ink">{t("lp2_seg_try_t")}</h2>
            <p className="mx-auto m-0 max-w-[56ch] text-[15px] leading-[1.8] text-ink-2">{t("lp2_seg_try_d")}</p>
            <BotCards bots={S.bots} className="mt-9" />
          </section>
        )}

        <section className="mx-auto max-w-[760px] px-4 pb-16 text-center sm:px-6">
          <h2 className="display m-0 mb-3 text-[clamp(24px,3.4vw,40px)] font-extrabold text-ink">{t("lp2_seg_start_t")}</h2>
          <p className="m-0 mb-7 text-[15px] leading-[1.8] text-ink-2">{t("lp2_seg_start_d")}</p>
          <Magnetic href={reg} icon="rocket">{t("get_started_free")}</Magnetic>
        </section>

        {(BY.others || []).length > 0 && (
          <nav aria-label={t("lp2_seg_others")} className="mx-auto max-w-[1100px] px-4 pb-20 text-center sm:px-6">
            <div className="mb-4 text-[13px] font-extrabold text-ink-3">{t("lp2_seg_others")}</div>
            <div className="flex flex-wrap justify-center gap-2.5">
              {BY.others.map((o) => (
                <a key={o.code} href={o.url}
                   className="inline-flex items-center gap-2 rounded-full bg-white/[0.04] px-4 py-2 text-[13.5px] font-bold text-ink-2 no-underline shadow-[inset_0_0_0_1px_rgb(255_255_255/0.09)] hover:text-ink">
                  <Icon name={o.icon} size={15} className="text-au-cyan" />{o.name}
                </a>
              ))}
            </div>
          </nav>
        )}
      </main>
      <Footer />
    </>
  );
}
