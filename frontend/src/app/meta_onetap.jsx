/* «اربط ماسنجر وإنستجرام بضغطة» — للعملاء (AGENTS §76).
   1) متابعة بفيسبوك ← نافذة فيسبوك (تُفتح داخل الضغطة نفسها وإلا حجبها المتصفح)
   2) /meta/login/return يسلّم الكود هنا (postMessage من نفس الأصل) ← /meta/login/pages
   3) مُنتقي الصفحات: الصفحة + القنوات + نوع البوت ← /meta/login/finish ← صفحة البوت.
   توكن فيسبوك لا يصل المتصفح أبداً — الخادم يحفظه مختوماً دقائق معدودة. */
import { useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { motion, AnimatePresence } from "motion/react";
import { BY, bi, t, Icon, Card, Btn, Input, Pill, Modal, Toggle } from "./kit.jsx";

async function api(url, body) {
  try {
    const r = await fetch(url, { method: "POST", credentials: "same-origin",
      headers: { "Content-Type": "application/json", "X-CSRF-Token": BY.csrf }, body: JSON.stringify(body || {}) });
    let d = null;
    try { d = await r.json(); } catch { /* صفحة خطأ */ }
    return d || { ok: false, error: `HTTP ${r.status}` };
  } catch {
    return { ok: false, error: bi("مفيش اتصال بالسيرفر — جرّب تاني.", "No connection to the server — try again.") };
  }
}

const FbGlyph = ({ size = 20 }) => (
  <svg viewBox="0 0 24 24" width={size} height={size} aria-hidden="true">
    <circle cx="12" cy="12" r="12" fill="#fff" />
    <path fill="#1877F2" d="M15.1 12.6h-2.2V20h-3v-7.4H8.4v-2.6h1.5V8.3c0-2 1-3.3 3.4-3.3h2v2.6h-1.3c-.9 0-1.1.4-1.1 1.1v1.3h2.4z" />
  </svg>
);

/* شعارا القناتين متراكبان — هوية الكارت قبل أن يُقرأ */
const Logos = ({ size = 44 }) => (
  <span className="relative inline-flex shrink-0" style={{ width: size * 1.62, height: size }}>
    <span className="absolute start-0 top-0 grid place-items-center rounded-2xl bg-[#0A7CFF]/12 ring-1 ring-[#0A7CFF]/30"
          style={{ width: size, height: size }}>
      <img src="/static/messenger.svg" alt="Messenger" className="object-contain" style={{ width: size * 0.56, height: size * 0.56 }} />
    </span>
    <span className="absolute end-0 top-0 grid place-items-center rounded-2xl bg-[#E1306C]/12 ring-1 ring-[#E1306C]/30 backdrop-blur"
          style={{ width: size, height: size }}>
      <img src="/static/instagram.svg" alt="Instagram" className="object-contain" style={{ width: size * 0.56, height: size * 0.56 }} />
    </span>
  </span>
);

const STEPS = [
  ["user", bi("سجّل دخولك بفيسبوك", "Sign in with Facebook")],
  ["grid", bi("اختار صفحتك", "Pick your Page")],
  ["bolt", bi("البوت يرد فوراً", "The bot replies instantly")],
];

function Stepper({ at }) {
  return (
    <ol className="m-0 flex list-none flex-wrap items-center gap-x-2 gap-y-2 p-0" aria-label={bi("الخطوات", "Steps")}>
      {STEPS.map(([icon, label], i) => {
        const done = i < at, cur = i === at;
        return (
          <li key={i} className="flex items-center gap-2" aria-current={cur ? "step" : undefined}>
            <span className={`grid size-7 shrink-0 place-items-center rounded-full text-[12px] font-extrabold transition-colors
                             ${done ? "bg-au-teal text-[#04140E]" : cur ? "bg-ov/15 text-ink ring-1 ring-ov/30" : "bg-ov/[0.06] text-ink-3"}`}>
              {done ? <Icon name="check" size={13} /> : <Icon name={icon} size={13} />}
            </span>
            <span className={`text-[12.5px] font-bold ${cur || done ? "text-ink" : "text-ink-3"}`}>{label}</span>
            {i < STEPS.length - 1 && <span aria-hidden="true" className="mx-1 hidden h-px w-6 bg-ov/15 sm:block" />}
          </li>
        );
      })}
    </ol>
  );
}

const TYPES = [
  ["customer_service", "sparkles", bi("خدمة عملاء ذكية", "Smart customer service"), bi("يرد على الأسئلة بالذكاء ويحوّل لك عند الحاجة", "Answers questions with AI and hands over when needed")],
  ["store", "store", bi("متجر وطلبات", "Store & orders"), bi("كتالوج وسلة وطلبات من المحادثة", "Catalog, cart and orders in chat")],
  ["booking", "calendar", bi("حجوزات ومواعيد", "Bookings"), bi("يحجز المواعيد ويؤكدها تلقائياً", "Books and confirms appointments")],
];

function PageAvatar({ p }) {
  const [bad, setBad] = useState(false);
  return p.picture && !bad
    ? <img src={p.picture} alt="" onError={() => setBad(true)} className="size-11 shrink-0 rounded-xl object-cover ring-1 ring-ov/10" />
    : <span className="grid size-11 shrink-0 place-items-center rounded-xl bg-[#1877F2]/15 text-[16px] font-extrabold text-[#5AA2FF]">
        {(p.name || "?").trim().charAt(0).toUpperCase()}
      </span>;
}

function Picker({ open, data, onClose, onRelogin }) {
  const pages = data.pages || [];
  const [q, setQ] = useState("");
  const [sel, setSel] = useState(null);
  const [fb, setFb] = useState(true);
  const [ig, setIg] = useState(true);
  const [type, setType] = useState("customer_service");
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);
  const page = pages.find((p) => p.id === sel) || null;

  useEffect(() => {                                  // اختيار تلقائي لصفحة وحيدة
    if (open && pages.length === 1 && !sel) setSel(pages[0].id);
  }, [open, pages, sel]);
  useEffect(() => {
    if (!page) return;
    setName(page.name.slice(0, 60));
    setFb(page.linked.messenger !== "taken");
    setIg(!!page.ig && page.linked.instagram !== "taken");
    setErr(null);
  }, [sel]);                                         // eslint-disable-line react-hooks/exhaustive-deps

  const shown = useMemo(() => {
    const n = q.trim().toLowerCase();
    return n ? pages.filter((p) => p.name.toLowerCase().includes(n) || (p.ig && p.ig.username.toLowerCase().includes(n))) : pages;
  }, [pages, q]);
  const newBots = page ? (fb && page.linked.messenger !== "mine" ? 1 : 0) + (ig && page.linked.instagram !== "mine" ? 1 : 0) : 0;
  const over = newBots > (data.slots ?? 99);
  const can = page && (fb || ig) && name.trim() && !busy && !over;

  const finish = async () => {
    setBusy(true); setErr(null);
    const d = await api("/meta/login/finish", { page_id: page.id, messenger: fb, instagram: ig, template: type, name: name.trim() });
    if (d.ok) { window.location.href = d.url; return; }
    setBusy(false);
    setErr(d.error === "expired"
      ? { m: bi("انتهت صلاحية تسجيل الدخول — سجّل دخولك مرة أخرى.", "Your sign-in expired — please sign in again."), relogin: true }
      : { m: d.error || bi("تعذّر الربط.", "Couldn't connect."), upgrade: d.upgrade });
  };

  return (
    <Modal open={open} onClose={busy ? () => {} : onClose} wide icon="link"
           title={bi("اختار الصفحة اللي البوت هيرد عليها", "Choose the Page your bot will answer")}
           footer={<>
             <Btn variant="ghost" type="button" onClick={onClose} disabled={busy}>{t("cancel")}</Btn>
             <Btn icon="bolt" type="button" onClick={finish} disabled={!can}>
               {busy ? bi("جارٍ الربط والتشغيل…", "Connecting and starting…") : bi("اربط وشغّل البوت", "Connect and start the bot")}
             </Btn>
           </>}>
      {!pages.length ? (
        <div className="py-8 text-center">
          <span className="mx-auto mb-4 grid size-14 place-items-center rounded-2xl bg-ov/[0.06] text-ink-3"><Icon name="search" size={24} /></span>
          <b className="block text-[15px] text-ink">{bi("ما وصلناش لأي صفحة", "We couldn't see any Page")}</b>
          <p className="mx-auto mt-1.5 mb-5 max-w-[420px] text-[13px] leading-relaxed text-ink-3">
            {bi("غالباً ما اخترتش صفحاتك في نافذة فيسبوك. سجّل دخولك تاني واختر «كل الصفحات» أو الصفحة المطلوبة. ولازم تكون أدمن على الصفحة.",
                "You probably didn't select your Pages in the Facebook window. Sign in again and choose «All Pages» or the one you need. You must be an admin of the Page.")}
          </p>
          <Btn icon="refresh" type="button" onClick={onRelogin}>{bi("سجّل دخولك مرة أخرى", "Sign in again")}</Btn>
        </div>
      ) : (
        <div className="grid gap-5 lg:grid-cols-[minmax(0,1.1fr)_minmax(0,1fr)]">
          <section aria-label={bi("صفحاتك", "Your Pages")}>
            {pages.length > 5 && (
              <div className="relative mb-3">
                <Icon name="search" size={15} className="pointer-events-none absolute start-3 top-1/2 -translate-y-1/2 text-ink-3" />
                <Input value={q} onChange={(e) => setQ(e.target.value)} className="!ps-9" placeholder={bi("ابحث في صفحاتك", "Search your Pages")} />
              </div>
            )}
            <div role="radiogroup" aria-label={bi("الصفحة", "Page")} className="flex max-h-[46vh] flex-col gap-2 overflow-y-auto pe-1">
              {shown.map((p) => {
                const on = p.id === sel;
                const blocked = p.linked.messenger === "taken" && (!p.ig || p.linked.instagram === "taken");
                return (
                  <button key={p.id} type="button" role="radio" aria-checked={on} disabled={blocked} onClick={() => setSel(p.id)}
                          className={`flex w-full cursor-pointer items-center gap-3 rounded-2xl border-0 p-3 text-start transition-all
                                      focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-au-cyan disabled:cursor-not-allowed disabled:opacity-45
                                      ${on ? "bg-au-violet/15 ring-2 ring-au-violet/60" : "bg-ov/[0.04] ring-1 ring-ov/[0.07] hover:bg-ov/[0.07]"}`}>
                    <PageAvatar p={p} />
                    <span className="min-w-0 flex-1">
                      <b className="block truncate text-[14px] text-ink" dir="auto">{p.name}</b>
                      <span className="mt-1 flex flex-wrap items-center gap-1.5 text-[11.5px] text-ink-3">
                        {p.category && <span className="truncate">{p.category}</span>}
                        {p.ig ? <span className="inline-flex items-center gap-1 rounded-full bg-[#E1306C]/12 px-2 py-0.5 font-bold text-[#F58BB0]">
                                  <img src="/static/instagram.svg" alt="" className="size-3" />@{p.ig.username}</span>
                              : <span className="rounded-full bg-ov/[0.06] px-2 py-0.5">{bi("بلا إنستجرام", "No Instagram")}</span>}
                        {(p.linked.messenger === "mine" || p.linked.instagram === "mine") && <Pill tone="on">{bi("مربوطة عندك", "Connected")}</Pill>}
                        {blocked && <Pill tone="off">{bi("مربوطة عند حساب آخر", "Used by another account")}</Pill>}
                      </span>
                    </span>
                    <span className={`grid size-5 shrink-0 place-items-center rounded-full ring-2 ${on ? "bg-au-violet ring-au-violet" : "ring-ov/25"}`}>
                      {on && <Icon name="check" size={11} className="text-white" />}
                    </span>
                  </button>
                );
              })}
            </div>
            <button type="button" onClick={onRelogin}
                    className="mt-3 cursor-pointer border-0 bg-transparent p-0 text-[12.5px] font-bold text-au-cyan hover:underline">
              {bi("صفحتك مش ظاهرة؟ سجّل دخولك واختر صفحات أكثر", "Page missing? Sign in again and select more Pages")}
            </button>
          </section>

          <section aria-label={bi("إعداد البوت", "Bot setup")} className={page ? "" : "pointer-events-none opacity-40"}>
            <span className="mb-2 block text-[12px] font-extrabold uppercase tracking-wider text-ink-3">{bi("القنوات", "Channels")}</span>
            <div className="flex flex-col gap-2">
              {[["messenger", "/static/messenger.svg", "Messenger", fb, setFb, page && page.linked.messenger === "taken", ""],
                ["instagram", "/static/instagram.svg", "Instagram", ig, setIg, !page || !page.ig || page.linked.instagram === "taken",
                 page && !page.ig ? bi("اربط حساب إنستجرام احترافي بالصفحة من إعداداتها أولاً", "Link an Instagram professional account to the Page first") : ""],
              ].map(([k, logo, label, val, set, dis, hint]) => (
                <div key={k} className="flex items-center gap-3 rounded-2xl bg-ov/[0.04] p-3 ring-1 ring-ov/[0.07]">
                  <img src={logo} alt="" className="size-7 shrink-0" />
                  <span className="min-w-0 flex-1">
                    <b className="block text-[13.5px] text-ink">{label}</b>
                    <span className="text-[11.5px] text-ink-3">
                      {hint || (page && page.linked[k] === "mine" ? bi("مربوط — سيُحدَّث الربط", "Connected — will refresh")
                        : k === "instagram" && page && page.ig ? `@${page.ig.username}` : bi("الرسائل الخاصة", "Direct messages"))}
                    </span>
                  </span>
                  <Toggle checked={val && !dis} disabled={dis} onChange={set} label={label} />
                </div>
              ))}
            </div>

            <span className="mt-5 mb-2 block text-[12px] font-extrabold uppercase tracking-wider text-ink-3">{bi("البوت هيعمل إيه؟", "What will the bot do?")}</span>
            <div role="radiogroup" aria-label={bi("نوع البوت", "Bot type")} className="grid gap-2">
              {TYPES.map(([k, icon, label, desc]) => (
                <button key={k} type="button" role="radio" aria-checked={type === k} onClick={() => setType(k)}
                        className={`flex cursor-pointer items-center gap-3 rounded-2xl border-0 p-3 text-start transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-au-cyan
                                    ${type === k ? "bg-au-cyan/10 ring-2 ring-au-cyan/50" : "bg-ov/[0.04] ring-1 ring-ov/[0.07] hover:bg-ov/[0.07]"}`}>
                  <span className={`grid size-9 shrink-0 place-items-center rounded-xl ${type === k ? "bg-au-cyan/20 text-au-cyan" : "bg-ov/[0.06] text-ink-3"}`}><Icon name={icon} size={17} /></span>
                  <span className="min-w-0"><b className="block text-[13.5px] text-ink">{label}</b><span className="text-[11.5px] text-ink-3">{desc}</span></span>
                </button>
              ))}
            </div>

            <label className="mt-5 block">
              <span className="mb-1.5 block text-[12px] font-extrabold uppercase tracking-wider text-ink-3">{bi("اسم النشاط", "Business name")}</span>
              <Input value={name} onChange={(e) => setName(e.target.value)} maxLength={60} />
            </label>

            {page && (
              <p className={`mt-4 mb-0 flex items-center gap-2 text-[12.5px] ${over ? "text-amber-300" : "text-ink-3"}`}>
                <Icon name={over ? "lock" : "bot"} size={14} />
                {over ? bi(`الربط يحتاج ${newBots} بوت وباقتك فيها ${data.slots} فقط`, `This needs ${newBots} bots and your plan has ${data.slots} left`)
                      : newBots ? bi(`سيُنشأ ${newBots} بوت ويبدأ الرد فوراً`, `${newBots} bot(s) will be created and start replying`)
                                : bi("سيُحدَّث الربط الحالي", "The existing connection will be refreshed")}
                {over && <a href={BY.urls.pricing} className="font-bold text-au-cyan underline">{bi("رقّي الباقة", "Upgrade")}</a>}
              </p>
            )}
            {err && (
              <p role="alert" className="mt-3 mb-0 rounded-xl bg-red-500/10 p-3 text-[12.5px] leading-relaxed text-red-200 ring-1 ring-red-400/25">
                {err.m}{" "}
                {err.relogin && <button type="button" onClick={onRelogin} className="cursor-pointer border-0 bg-transparent p-0 font-bold text-au-cyan underline">{bi("سجّل الدخول", "Sign in")}</button>}
                {err.upgrade && <a href={BY.urls.pricing} className="font-bold text-au-cyan underline">{bi("رقّي الباقة", "Upgrade")}</a>}
              </p>
            )}
          </section>
        </div>
      )}
    </Modal>
  );
}

const CARD = "relative mb-6 overflow-hidden " +
  "bg-[linear-gradient(125deg,rgb(10_124_255/0.12),rgb(225_48_108/0.08)_60%,rgb(124_108_246/0.06))] " +
  "shadow-[inset_0_0_0_1px_rgb(10_124_255/0.28)]";

export default function MetaOneTap({ cfg }) {
  const [phase, setPhase] = useState(0);            // 0 جاهز · 1 نافذة فيسبوك مفتوحة · 2 المُنتقي
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState(null);
  const [data, setData] = useState({ pages: [], slots: 0 });
  const done = useRef(false);
  const win = useRef(null);

  useEffect(() => {
    const onMsg = async (ev) => {
      if (ev.origin !== window.location.origin) return;
      const d = ev.data || {};
      if (d.type !== "BY_META" || done.current) return;
      done.current = true;
      if (!d.code) {
        setBusy(false); setPhase(0);
        setMsg({ bad: true, m: d.error === "state"
          ? bi("الجلسة اتغيّرت — حدّث الصفحة وجرّب تاني.", "The session changed — refresh the page and try again.")
          : bi("اتلغى تسجيل الدخول من نافذة فيسبوك.", "Sign-in was cancelled in the Facebook window.") });
        return;
      }
      setMsg({ m: bi("بنجيب صفحاتك…", "Loading your Pages…") });
      const r = await api("/meta/login/pages", { code: d.code });
      setBusy(false);
      if (!r.ok) { setPhase(0); setMsg({ bad: true, m: r.error || bi("تعذّر تسجيل الدخول.", "Sign-in failed.") }); return; }
      setData(r); setMsg(null); setPhase(2);
    };
    window.addEventListener("message", onMsg);
    return () => window.removeEventListener("message", onMsg);
  }, []);

  // النافذة أُغلقت يدوياً بلا نتيجة ⇒ نعيد الزر بدل «جارٍ…» للأبد
  useEffect(() => {
    if (phase !== 1) return undefined;
    const t = setInterval(() => {
      if (win.current && win.current.closed && !done.current) { setBusy(false); setPhase(0); setMsg(null); clearInterval(t); }
    }, 800);
    return () => clearInterval(t);
  }, [phase]);

  const start = async () => {
    done.current = false; setMsg(null);
    const w = window.open("", "by_meta_login", "width=620,height=760,menubar=no,toolbar=no");
    win.current = w;
    setBusy(true);
    const d = await api("/meta/login/start");
    if (!d.ok || !d.url) {
      if (w) w.close();
      setBusy(false);
      setMsg({ bad: true, m: d.error || bi("تعذّر فتح نافذة فيسبوك.", "Couldn't open the Facebook window."), upgrade: d.upgrade });
      return;
    }
    if (!w) {
      setBusy(false);
      setMsg({ bad: true, m: bi("المتصفح منع النافذة — اسمح بالنوافذ المنبثقة للموقع وجرّب تاني.", "Your browser blocked the popup — allow popups and try again.") });
      return;
    }
    w.location.href = d.url;
    setPhase(1);
  };

  const locked = !cfg.allowed;
  return (
    <Card id="meta-onetap" className={CARD}>
      <div aria-hidden="true" className="pointer-events-none absolute -top-28 -end-24 size-72 rounded-full bg-[#E1306C]/10 blur-3xl" />
      <div aria-hidden="true" className="pointer-events-none absolute -bottom-32 -start-24 size-72 rounded-full bg-[#0A7CFF]/10 blur-3xl" />
      <div className="relative flex flex-col gap-5 lg:flex-row lg:items-center lg:justify-between">
        <div className="flex min-w-0 items-start gap-4">
          <Logos />
          <div className="min-w-0">
            <h2 className="m-0 flex flex-wrap items-center gap-2 text-[19px] font-extrabold tracking-tight text-ink">
              {bi("اربط ماسنجر وإنستجرام بضغطة", "Connect Messenger & Instagram in one tap")}
              {locked ? <Pill tone="mute"><Icon name="lock" size={11} />{bi("باقة تاجر فأعلى", "Merchant plan +")}</Pill>
                      : <Pill tone="on">{bi("جديد", "New")}</Pill>}
            </h2>
            <p className="mt-1.5 mb-0 max-w-[600px] text-[13.5px] leading-relaxed text-ink-3">
              {bi("سجّل دخولك بفيسبوك واختار صفحتك — والبوت يرد على رسائل ماسنجر وإنستجرام فوراً، 24 ساعة. بدون توكنات ولا لوحة مطوّرين.",
                  "Sign in with Facebook and pick your Page — your bot answers Messenger and Instagram DMs instantly, 24/7. No tokens, no developer console.")}
            </p>
          </div>
        </div>
        {locked ? (
          <div className="flex shrink-0 flex-col items-start gap-2 lg:items-end">
            {cfg.upgrade ? <Btn icon="crown" href={cfg.pricing || BY.urls.pricing}>{bi("رقّي باقتك وابدأ", "Upgrade and start")}</Btn>
                         : <span className="text-[12.5px] text-ink-3">{cfg.reason}</span>}
          </div>
        ) : (
          <button type="button" onClick={start} disabled={busy}
                  className="inline-flex h-12 shrink-0 cursor-pointer items-center justify-center gap-2.5 rounded-xl border-0 bg-[#1877F2] px-5
                             text-[15px] font-bold text-white shadow-[0_10px_24px_-10px_rgb(24_119_242/0.8)] transition-all
                             hover:bg-[#166FE5] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#5AA2FF] focus-visible:ring-offset-2
                             focus-visible:ring-offset-transparent active:scale-[0.98] disabled:cursor-wait disabled:opacity-70">
            <FbGlyph />
            {busy ? (phase === 1 ? bi("كمّل في نافذة فيسبوك…", "Continue in the Facebook window…") : bi("لحظة…", "One moment…"))
                  : bi("متابعة بفيسبوك", "Continue with Facebook")}
          </button>
        )}
      </div>
      <div className="relative mt-5 flex flex-wrap items-center justify-between gap-3 border-t border-ov/[0.07] pt-4">
        <Stepper at={phase === 2 ? 1 : phase} />
        <span className="inline-flex items-center gap-1.5 text-[11.5px] text-ink-3">
          <Icon name="shield" size={12} />{bi("لا نحفظ كلمة سرّك ولا ننشر شيئاً باسمك", "We never see your password or post as you")}
        </span>
      </div>
      <AnimatePresence>
        {msg && (
          <motion.p initial={{ opacity: 0, y: -4 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} role="status" aria-live="polite"
                    className={`relative mt-3 mb-0 text-[13px] font-bold ${msg.bad ? "text-red-300" : "text-ink-2"}`}>
            {msg.m}{" "}{msg.upgrade && <a href={BY.urls.pricing} className="text-au-cyan underline">{bi("رقّي الباقة", "Upgrade")}</a>}
          </motion.p>
        )}
      </AnimatePresence>
      {/* بوابة إلى body: الكارت زجاجي (backdrop-filter) فيصير حاوية لأي fixed داخله ويقصّ النافذة */}
      {createPortal(<Picker open={phase === 2} data={data} onClose={() => setPhase(0)}
                            onRelogin={() => { setPhase(0); start(); }} />, document.body)}
    </Card>
  );
}
