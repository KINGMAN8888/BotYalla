import { useEffect, useState } from "react";
import { BY, t, Icon, Magnetic, fill } from "./ui.jsx";
import Aurora from "./Aurora.jsx";
import { Nav, Footer, ReadBar, SkipLink } from "./sections.jsx";

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
