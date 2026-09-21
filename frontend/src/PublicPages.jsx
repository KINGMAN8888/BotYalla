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
/* نموذج «الحالة المرجعية» لشرائح B2B (مصانع · شركات · وكالات).
   بعد الإرسال لا نرسل الملف لرقم العميل من الخادم: زرّ «استلمها على واتساب» يجعله هو من يبدأ
   المحادثة (سياسة Meta — بلا قالب ولا خطر على جودة الرقم الرسمي)، والبوت يرسل الـPDF فوراً.
   الحالة **نموذج محسوب** بأرقام سوق معلنة، لا نتائج عميل — والنص يقول ذلك صراحةً. */
function CaseStudyForm({ segment }) {
  const L = (ar, en) => (BY.lang === "en" ? en : ar);
  const [f, setF] = useState({ name: "", company: "", role: "", phone: "", consent: false });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);
  const [done, setDone] = useState(null);           // {wa, tg}
  const set = (k) => (e) => setF((x) => ({ ...x, [k]: k === "consent" ? e.target.checked : e.target.value }));
  const input = "w-full rounded-xl bg-black/30 px-4 py-3 text-[14.5px] text-ink placeholder:text-ink-4 " +
                "shadow-[inset_0_0_0_1px_rgb(255_255_255/0.12)] outline-none focus:shadow-[inset_0_0_0_2px_rgb(143_233_255/0.6)]";

  async function send(e) {
    e.preventDefault();
    setBusy(true); setErr(null);
    try {
      const r = await fetch("/case-study/lead", {
        method: "POST", credentials: "same-origin",
        headers: { "Content-Type": "application/json", "X-CSRF-Token": BY.csrf || "" },
        body: JSON.stringify({ ...f, segment }),
      });
      const d = await r.json();
      if (d.ok) setDone(d); else setErr(d.error);
    } catch {
      setErr(L("تعذّر الإرسال — جرّب تاني.", "Could not send — try again."));
    }
    setBusy(false);
  }

  return (
    <section id="case" aria-labelledby="case-t" className="scroll-mt-24 mx-auto max-w-[760px] px-4 pb-16 sm:px-6">
      <div className="rounded-[28px] bg-[linear-gradient(165deg,rgb(124_108_246/0.18),rgb(34_211_238/0.06))] p-7
                      shadow-[inset_0_0_0_1px_rgb(143_233_255/0.2)] sm:p-9">
        <h2 id="case-t" className="display m-0 mb-2 flex items-center gap-2.5 text-[clamp(22px,3vw,32px)] font-extrabold text-ink">
          <Icon name="download" size={24} className="text-au-cyan" />
          {L("احسبها بنفسك: الحالة المرجعية", "Run the numbers: the reference case")}
        </h2>
        <p className="m-0 mb-6 text-[14.5px] leading-[1.8] text-ink-2">
          {L("نموذج محسوب بأرقام سوق منشورة وافتراضات معلنة — مش نتايج عميل. بيوضح إزاي البوت بيوفّر ساعات الرد ويقفل طلبات أكتر. سيب بياناتك واستلمه على واتساب في ثانية.",
             "A calculated model built on published market figures and stated assumptions — not a customer's results. It shows how a bot saves reply hours and closes more orders. Leave your details and get it on WhatsApp in a second.")}
        </p>

        {done ? (
          <div role="status" className="text-center">
            <p className="m-0 mb-5 text-[15px] font-bold text-au-teal">
              {L("تمام! اضغط الزرار والبوت هيبعتلك الملف فوراً 👇", "Done! Tap the button and the bot sends you the file right away 👇")}
            </p>
            <div className="flex flex-wrap justify-center gap-3">
              {done.wa && (
                <a href={done.wa} target="_blank" rel="noopener"
                   className="inline-flex items-center gap-2 rounded-full bg-[#25D366] px-6 py-3.5 text-[15px] font-extrabold text-[#04140E] no-underline">
                  <Icon name="chat" size={17} />{L("استلمها على واتساب", "Get it on WhatsApp")}
                </a>
              )}
              {done.tg && (
                <a href={done.tg} target="_blank" rel="noopener"
                   className="inline-flex items-center gap-2 rounded-full bg-white/[0.08] px-6 py-3.5 text-[15px] font-extrabold text-ink no-underline shadow-[inset_0_0_0_1px_rgb(255_255_255/0.15)]">
                  <Icon name="chat" size={17} />{L("أو على تليجرام", "or on Telegram")}
                </a>
              )}
            </div>
          </div>
        ) : (
          <form onSubmit={send} className="grid gap-3 sm:grid-cols-2">
            <input className={input} value={f.name} onChange={set("name")} required maxLength={80}
                   placeholder={L("الاسم", "Name")} autoComplete="name" />
            <input className={input} value={f.company} onChange={set("company")} required maxLength={120}
                   placeholder={L("اسم الشركة / المصنع", "Company / factory")} autoComplete="organization" />
            <input className={input} value={f.role} onChange={set("role")} maxLength={80}
                   placeholder={L("المسمى الوظيفي", "Job title")} autoComplete="organization-title" />
            <input className={input} value={f.phone} onChange={set("phone")} required maxLength={25} dir="ltr"
                   inputMode="tel" placeholder={L("رقم الواتساب 2010…", "WhatsApp number 2010…")} autoComplete="tel" />
            <label className="flex cursor-pointer items-start gap-2.5 text-[13px] leading-[1.7] text-ink-2 sm:col-span-2">
              <input type="checkbox" checked={f.consent} onChange={set("consent")} required className="mt-1 size-4 accent-[#8FE9FF]" />
              {L("أوافق على تواصل BotYalla معي على واتساب بخصوص طلبي، ويمكنني إلغاء ذلك في أي وقت بكتابة «إلغاء».",
                 "I agree that BotYalla may contact me on WhatsApp about my request; I can opt out anytime by replying «stop».")}
            </label>
            {err && <p role="alert" className="m-0 text-[13px] font-bold text-red-300 sm:col-span-2">{err}</p>}
            <button type="submit" disabled={busy}
                    className="inline-flex items-center justify-center gap-2 rounded-full bg-[linear-gradient(100deg,#8FE9FF,#B9AFFF)] px-6 py-3.5 text-[15px] font-extrabold text-[#07090F] disabled:opacity-60 sm:col-span-2">
              <Icon name="download" size={17} />{busy ? "…" : L("ابعتهالي", "Send it to me")}
            </button>
          </form>
        )}
      </div>
    </section>
  );
}

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

        {S.caseStudy && <CaseStudyForm segment={S.code} />}

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
