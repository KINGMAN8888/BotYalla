import { Fragment, useEffect, useMemo, useRef, useState } from "react";
import { motion, AnimatePresence, useInView, useReducedMotion } from "motion/react";
import { BY, t, Icon, Magnetic, useAnimEnabled } from "./ui.jsx";

/* ============================================================================
   البطل: النافذة أولاً، والكلام تحتها.

   نافذة محادثة واحدة كبيرة في أول الصفحة هي المنتج نفسه: شاشة إنشاء البوت
   تطلع من أسفل النافذة كما في تليجرام (الاسم يُكتب واليوزر جاهز ثم «إنشاء»)،
   فتنزل ويبدأ البوت يرد. تبويبات أعلى النافذة تبدّل النشاط، والعرض يدور وحده
   حتى يتدخّل الزائر أو تخرج النافذة من الشاشة.
   تحتها عنوان وجملة وزرّان — بلا زخارف ولا دوائر.

   تقليل الحركة أو حلقة رسوم ميتة: المحادثة مكتملة بلا تسلسل ولا دوران.
   ========================================================================== */

function useEnter(rootRef) {
  useEffect(() => {
    const root = rootRef.current;
    if (!root) return;
    const play = () => root.querySelectorAll(".kw,.hr-in").forEach((el) => el.classList.add("in"));
    const id = setTimeout(play, 40);
    const safety = setTimeout(play, 1800);          // شبكة أمان مهما حدث
    return () => { clearTimeout(id); clearTimeout(safety); };
  }, [rootRef]);
}

/* عنوان يظهر كلمة كلمة. المسافة خارج غلاف الكلمة: المتصفح يحذف المسافة في آخر
   صندوق inline-block فكانت الكلمات تلتصق. */
function Kinetic({ text, from = 0, step = 0.08, accent = false }) {
  const words = String(text || "").split(/\s+/).filter(Boolean);
  return words.map((word, i) => (
    <Fragment key={i}>
      <span className="inline-block overflow-hidden pb-[0.1em] align-bottom">
        <span className={"kw " + (accent ? "hue serif-accent" : "")}
              style={{ transitionDelay: `${from + i * step}s` }}>
          {word}
        </span>
      </span>
      {i < words.length - 1 ? " " : null}
    </Fragment>
  ));
}

/* QR حقيقي من الخادم (segno): مسار SVG واحد، بلا innerHTML */
export function QR({ rows, size = 60, label }) {
  const d = useMemo(() => {
    let s = "";
    rows.forEach((r, y) => {
      for (let x = 0; x < r.length; x++) if (r[x] === "1") s += `M${x} ${y}h1v1h-1z`;
    });
    return s;
  }, [rows]);
  const n = rows.length + 4;
  return (
    <svg viewBox={`-2 -2 ${n} ${n}`} width={size} height={size} role="img" aria-label={label}
         shapeRendering="crispEdges" className="block shrink-0">
      <rect x="-2" y="-2" width={n} height={n} rx="2" fill="#fff" />
      <path d={d} fill="#07090F" />
    </svg>
  );
}

/* نصّ يُكتب حرفاً حرفاً — كأن تليجرام يملأ الخانة */
function Typed({ text, still }) {
  const [n, setN] = useState(still ? text.length : 0);
  useEffect(() => {
    if (still) { setN(text.length); return; }
    setN(0);
    let i = 0;
    const id = setInterval(() => { i += 1; setN(i); if (i >= text.length) clearInterval(id); }, 42);
    return () => clearInterval(id);
  }, [text, still]);
  return (
    <>
      {text.slice(0, n)}
      {!still && n < text.length && <span aria-hidden="true" className="caret" />}
    </>
  );
}

function Avatar({ b, size = 44 }) {
  return (
    <span aria-hidden="true"
          className="grid shrink-0 place-items-center rounded-full text-[#07090F]
                     bg-[linear-gradient(140deg,#8FE9FF,#B9AFFF_55%,#7C6CF6)] shadow-[inset_0_1px_0_rgb(255_255_255/0.6)]"
          style={{ width: size, height: size }}>
      <Icon name={b.icon} size={Math.round(size * 0.52)} />
    </span>
  );
}

function Slot({ label, children }) {
  return (
    <div className="rounded-2xl bg-white/[0.05] px-4 py-2.5 shadow-[inset_0_0_0_1px_rgb(255_255_255/0.08)]">
      <div className="text-[11.5px] font-bold text-ink-3">{label}</div>
      <div className="min-h-[1.55em] truncate text-[15px] font-extrabold text-ink">{children}</div>
    </div>
  );
}

/* شاشة الإنشاء (Bottom sheet): ما يعرضه تليجرام للمستخدم — الاسم واليوزر جاهزان، وزر واحد */
function Sheet({ b, still }) {
  const later = (delay) => (still ? {} : {
    initial: { opacity: 0, y: 8 }, animate: { opacity: 1, y: 0 },
    transition: { delay, duration: 0.4, ease: [0.16, 1, 0.3, 1] },
  });
  return (
    <div className="mx-auto w-full max-w-[460px] rounded-t-[28px] bg-[#0D1220]/95 p-5 pb-6 backdrop-blur-xl
                    shadow-[0_-24px_60px_-20px_rgb(0_0_0/0.85),inset_0_1px_0_rgb(255_255_255/0.1)]">
      <span aria-hidden="true" className="mx-auto mb-4 block h-1 w-10 rounded-full bg-white/20" />
      <div className="flex items-center gap-3">
        <Avatar b={b} size={42} />
        <div className="text-[16px] font-extrabold text-ink">{t("lp2_hx_new")}</div>
      </div>
      <div className="mt-4 grid gap-2">
        <Slot label={t("lp2_hx_name")}><Typed text={b.name} still={still} /></Slot>
        <motion.div {...later(0.6)}>
          <Slot label={t("lp2_hx_user")}><span dir="ltr">@{b.handle}</span></Slot>
        </motion.div>
      </div>
      {/* الزر «يُضغط» وحده في آخر المشهد: هذه هي الضغطة الوحيدة المطلوبة */}
      <motion.div
        {...(still ? {} : {
          initial: { opacity: 0, y: 8 },
          animate: { opacity: 1, y: 0, scale: [1, 1, 0.94, 1] },
          transition: { opacity: { delay: 0.85 }, y: { delay: 0.85 },
                        scale: { delay: 1.4, duration: 0.42, times: [0, 0.1, 0.55, 1] } },
        })}
        className="mt-4 rounded-2xl bg-[#2AABEE] py-3 text-center text-[15px] font-extrabold text-white
                   shadow-[0_10px_26px_-10px_rgb(42_171_238/0.9)]">
        {t("lp2_hx_create")}
      </motion.div>
    </div>
  );
}

/* رسائل البوت الشغّال — بنفس لغة النشاط، وأزراره تحت ردّه كما في تليجرام */
function Messages({ b, still }) {
  const pop = (i) => (still ? {} : {
    initial: { opacity: 0, y: 14, scale: 0.96 }, animate: { opacity: 1, y: 0, scale: 1 },
    transition: { delay: 0.25 + i * 0.6, duration: 0.5, ease: [0.175, 0.885, 0.32, 1.275] },
  });
  return (
    <>
      <motion.p {...pop(0)}
                className="m-0 max-w-[78%] self-end rounded-[20px] rounded-ee-[6px] px-4 py-2.5 text-[15px] font-bold
                           leading-relaxed text-[#08111C] bg-[linear-gradient(115deg,#7C6CF6,#22D3EE)]
                           shadow-[0_10px_26px_-12px_rgb(34_211_238/0.8)]">
        {b.q}
      </motion.p>
      <motion.div {...pop(1)} className="flex w-full max-w-[380px] flex-col gap-1.5 self-start">
        <p className="m-0 rounded-[20px] rounded-es-[6px] bg-white/[0.08] px-4 py-2.5 text-[15px] leading-relaxed text-ink
                      shadow-[inset_0_0_0_1px_rgb(255_255_255/0.06)]">
          {b.a}
        </p>
        <div className="grid grid-cols-2 gap-1.5">
          {(b.kbd || []).map((k, i) => (
            <span key={i}
                  className="inline-flex items-center justify-center gap-1.5 rounded-xl bg-white/[0.06] px-3 py-2
                             text-[13px] font-bold text-ink-2 shadow-[inset_0_0_0_1px_rgb(255_255_255/0.1)]">
              <Icon name={k.i} size={14} className="text-au-cyan" />{k.t}
            </span>
          ))}
        </div>
      </motion.div>
    </>
  );
}

/* النافذة: sheet (شاشة الإنشاء) ← live (البوت يرد) ← النشاط التالي */
function Window() {
  const bizs = BY.hero || [];
  const reduce = useReducedMotion();
  const animOk = useAnimEnabled();
  const still = !!reduce || !animOk;
  const [biz, setBiz] = useState(0);
  const [phase, setPhase] = useState(() => (reduce ? "live" : "sheet"));
  const timers = useRef([]);
  const touched = useRef(false);        // الزائر اختار بنفسه — نوقف الدوران التلقائي
  const ref = useRef(null);
  const inView = useInView(ref, { amount: 0.3 });

  const clear = () => { timers.current.forEach(clearTimeout); timers.current = []; };
  const run = (i) => {
    clear();
    setBiz(i);
    if (still) { setPhase("live"); return; }
    setPhase("sheet");
    timers.current.push(setTimeout(() => setPhase("live"), 2200));
  };

  useEffect(() => {
    if (!reduce) run(0);
    return clear;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  useEffect(() => { if (still) { clear(); setPhase("live"); } }, [still]);

  // دوران تلقائي بين الأنشطة — يتوقف لو الزائر اختار، أو النافذة خارج الشاشة
  useEffect(() => {
    if (still || touched.current || !inView || phase !== "live" || bizs.length < 2) return;
    const id = setTimeout(() => run((biz + 1) % bizs.length), 6000);
    return () => clearTimeout(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [phase, biz, inView, still]);

  const pick = (i) => { touched.current = true; run(i); };
  const b = bizs[biz];
  if (!b) return null;
  const live = phase === "live";

  return (
    <div ref={ref} className="relative mx-auto w-full max-w-[880px]">
      {/* وهج ناعم تحت النافذة يرفعها عن الخلفية — ضوء لا شكل */}
      <div aria-hidden="true"
           className="pointer-events-none absolute inset-x-[6%] -bottom-12 top-[20%] -z-10 blur-3xl
                      bg-[radial-gradient(60%_60%_at_50%_60%,rgb(124_108_246/0.45),rgb(34_211_238/0.12)_55%,transparent_75%)]" />

      <div className="glass overflow-hidden rounded-[30px] shadow-[0_60px_140px_-50px_rgb(124_108_246/0.7)]">
        {/* شريط النافذة: الأنشطة · الرابط · إعادة */}
        <div className="flex items-center gap-2 bg-white/[0.03] px-3 py-2.5 shadow-[inset_0_-1px_0_rgb(255_255_255/0.07)] sm:px-4">
          <div role="group" aria-label={t("lp2_hx_pick")}
               className="flex min-w-0 flex-1 gap-1 overflow-x-auto [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
            {bizs.map((x, i) => (
              <button key={i} type="button" aria-pressed={i === biz} onClick={() => pick(i)}
                      className={"relative inline-flex shrink-0 cursor-pointer items-center gap-2 rounded-xl bg-transparent " +
                        "px-3 py-2 text-[13px] font-bold transition-colors duration-300 " +
                        (i === biz ? "text-white" : "text-ink-3 hover:text-ink-2")}>
                {i === biz && (
                  <motion.span layoutId="biz-tab"
                               className="absolute inset-0 rounded-xl bg-white/[0.08] shadow-[inset_0_0_0_1px_rgb(255_255_255/0.12)]"
                               transition={{ type: "spring", stiffness: 380, damping: 32 }} />
                )}
                <Icon name={x.icon} size={16} className={"relative " + (i === biz ? "text-au-cyan" : "")} />
                <span className="relative whitespace-nowrap">{x.label}</span>
              </button>
            ))}
          </div>
          <span dir="ltr"
                className="hidden shrink-0 items-center gap-1.5 rounded-full bg-black/35 px-3 py-1.5 text-[11.5px] font-bold
                           text-ink-3 shadow-[inset_0_0_0_1px_rgb(255_255_255/0.08)] md:inline-flex">
            <Icon name="link" size={13} className="text-au-cyan" />t.me/{b.handle}
          </span>
          <button type="button" onClick={() => pick(biz)} aria-label={t("lp2_hx_again")} title={t("lp2_hx_again")}
                  className="grid size-9 shrink-0 cursor-pointer place-items-center rounded-full bg-transparent text-ink-2
                             shadow-[inset_0_0_0_1px_rgb(255_255_255/0.12)] transition-colors hover:bg-white/10 hover:text-ink">
            <Icon name="refresh" size={16} />
          </button>
        </div>

        {/* المحادثة */}
        <div className="relative flex h-[clamp(400px,46vw,470px)] flex-col">
          <div className="flex items-center gap-3 px-5 py-3.5 shadow-[0_1px_0_rgb(255_255_255/0.06)] sm:px-7">
            <Avatar b={b} size={42} />
            <div className="min-w-0">
              <div className="truncate text-[16px] font-extrabold text-ink">{b.name}</div>
              <div className="flex items-center gap-1.5 text-[12px] font-bold text-au-teal">
                <i className="block size-1.5 rounded-full bg-current" />{live ? t("lp2_hx_live") : t("lp2_hx_new")}
              </div>
            </div>
          </div>

          <div key={`${biz}-${live}`} className="flex flex-1 flex-col justify-end gap-3 overflow-hidden px-5 pb-4 sm:px-7">
            {live && <Messages b={b} still={still} />}
          </div>

          <div aria-hidden="true"
               className="mx-4 mb-4 flex items-center gap-3 rounded-2xl bg-black/30 px-4 py-2.5
                          shadow-[inset_0_0_0_1px_rgb(255_255_255/0.07)] sm:mx-6">
            <span className="flex-1 truncate text-[14px] text-ink-4">{t("lp2_hx_type")}</span>
            <span className="grid size-8 place-items-center rounded-full text-[#07090F] bg-[linear-gradient(130deg,#8FE9FF,#B9AFFF)]">
              <Icon name="arrow" size={15} className="rtl:-scale-x-100" />
            </span>
          </div>

          {/* شاشة الإنشاء تطلع من أسفل النافذة كما في تليجرام، ثم تنزل ويبدأ البوت */}
          <AnimatePresence>
            {!live && (
              <motion.div key={`sheet-${biz}`}
                          className="absolute inset-0 z-10 flex flex-col justify-end bg-black/45 backdrop-blur-[2px]"
                          initial={still ? false : { opacity: 0 }} animate={{ opacity: 1 }}
                          exit={{ opacity: 0, transition: { duration: 0.35, delay: 0.1 } }}>
                <motion.div className="px-3 sm:px-0"
                            initial={still ? false : { y: "100%" }} animate={{ y: 0 }}
                            exit={{ y: "100%", transition: { duration: 0.35, ease: [0.4, 0, 1, 1] } }}
                            transition={{ type: "spring", stiffness: 260, damping: 30 }}>
                  <Sheet b={b} still={still} />
                </motion.div>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </div>
    </div>
  );
}

export default function Hero() {
  const ref = useRef(null);
  useEnter(ref);
  const authed = !!(BY.auth && BY.auth.in);
  const aWords = String(t("lp2_h1a")).split(/\s+/).filter(Boolean).length;
  const qr = BY.heroQr || [];

  return (
    <section ref={ref} aria-labelledby="hero-t"
             className="relative mx-auto max-w-[1240px] px-4 pt-[clamp(8px,2vw,28px)] pb-[clamp(48px,7vw,96px)] sm:px-6">
      {/* النافذة أولاً: أول ما يراه الزائر هو المنتج نفسه */}
      <div className="hr-in" style={{ transitionDelay: "0.05s" }}>
        <Window />
      </div>

      <div className="relative z-10 mx-auto mt-[clamp(36px,5vw,64px)] max-w-[1000px] text-center">
        <h1 id="hero-t" className="display m-0 text-[clamp(40px,6.2vw,84px)] font-extrabold text-ink">
          <span className="block lg:inline"><Kinetic text={t("lp2_h1a")} from={0.3} /></span>{" "}
          <span className="block lg:inline"><Kinetic text={t("lp2_h1b")} from={0.3 + aWords * 0.08} accent /></span>
        </h1>

        <p className="hr-in mx-auto mt-5 mb-8 max-w-[46ch] text-[clamp(16px,1.5vw,19px)] leading-[1.75] text-ink-2"
           style={{ transitionDelay: "0.6s" }}>
          {t("lp2_sub")}
        </p>

        <div className="hr-in flex flex-col items-center justify-center gap-4 sm:flex-row"
             style={{ transitionDelay: "0.7s" }}>
          <Magnetic href={authed ? BY.urls.dashboard : BY.urls.register} icon="rocket" className="w-full sm:w-auto">
            {authed ? t("lp2_nav_dashboard") : t("get_started_free")}
          </Magnetic>
          <a href={BY.urls.home + "#pricing"}
             className="group inline-flex items-center gap-2 px-2 py-2 text-[15px] font-extrabold text-ink-2 no-underline
                        transition-colors hover:text-ink">
            {t("lp2_cta_secondary")}
            <Icon name="arrow" size={17}
                  className="transition-transform duration-300 rtl:-scale-x-100 group-hover:translate-x-1
                             rtl:group-hover:-translate-x-1" />
          </a>
          {/* على الكمبيوتر: QR حقيقي — الزائر يكمّل من موبايله حيث تليجرام */}
          {qr.length > 0 && (
            <div className="hidden items-center gap-3 border-s border-white/10 ps-5 lg:flex">
              <QR rows={qr} label={t("lp2_hx_qr")} />
              <p className="m-0 max-w-[18ch] text-start text-[12.5px] font-bold leading-relaxed text-ink-3">
                {t("lp2_hx_scan")}
              </p>
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
