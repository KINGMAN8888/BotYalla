import { Fragment, useEffect, useMemo, useRef, useState } from "react";
import { motion, AnimatePresence, useReducedMotion } from "motion/react";
import { canListen, createListener, createSpeaker, yesNo } from "./assistant/voice.js";

/* ============================================================================
   «مساعد BotYalla» — وكيل ذكي على كل صفحات الموقع واللوحة.
   - يفهم الصفحة التي يقف عليها المستخدم وحالة حسابه (site_assistant.py)، ويشرح أو **ينفّذ**:
     ينقلك لأي صفحة فوراً، وأي تغيير في حسابك يظهر كبطاقة «نفّذ» لا يحدث قبل موافقتك
     (ضغطة أو «اه نفّذ» بصوتك). التنفيذ نفسه في الخادم بصلاحياتك وحدود باقتك.
   - محادثة صوتية كاملة: يسمعك (المتصفح، وإلا الخادم) ويرد بصوت (assistant/voice.js).
   - ثلاث هيئات: زر عائم · لوحة · صفحة كاملة — ويُخفى الزر بلسان صغير على حافة الشاشة.
   الأيقونات مرسومة هنا (الموقع العام لا يحمل BY.icons كاملة). الروابط من الخادم وحده.
   ========================================================================== */

const BY = window.BY || {};
const AR = BY.lang !== "en";
const LANG = AR ? "ar" : "en";
const bi = (a, e) => (AR ? a : e);
const BOOT = BY.assistant || null;
const WHO = (BY.user && BY.user.name) || (BY.auth && BY.auth.name) || "";
const SIGNED = !!WHO || !!(BY.auth && BY.auth.in) || !!(BOOT && BOOT.signed);
/* المحادثة محفوظة لكل حساب على حدة — جهاز مشترك لا يُظهر محادثة حساب لحساب آخر */
const KEY = "by-assistant-v1:" + (WHO || "guest");
const LEVEL = { v: 0 };                               // مستوى الصوت الحيّ (0..1) — تقرؤه الكرة بلا إعادة رسم

const store = (s) => ({
  get(k, d) { try { const v = s().getItem(k); return v === null ? d : v; } catch { return d; } },
  set(k, v) { try { s().setItem(k, v); } catch { /* تصفح خاص */ } },
});
const LS = store(() => localStorage);
const SS = store(() => sessionStorage);

const load = () => {
  try {
    return (JSON.parse(sessionStorage.getItem(KEY) || "[]") || []).map((m) =>
      (m.go && !m.go.state ? { ...m, go: { ...m.go, state: "done" } } : m));
  } catch { return []; }
};
const save = (msgs) => { try { sessionStorage.setItem(KEY, JSON.stringify(msgs.slice(-40))); } catch { /* */ } };

async function post(url, body) {
  try {
    const r = await fetch(url, {
      method: "POST", credentials: "same-origin",
      headers: { "Content-Type": "application/json", "X-CSRF-Token": BY.csrf || "" },
      body: JSON.stringify(body),
    });
    const d = await r.json().catch(() => ({}));
    if (!r.ok && !d.error) d.error = bi("حصلت مشكلة في الاتصال — جرّب تاني.", "Connection problem — try again.");
    return d;
  } catch {
    return { ok: false, error: bi("مفيش اتصال بالإنترنت — جرّب تاني.", "You're offline — try again.") };
  }
}

/* ---------------------------------------------------------------- أيقونات */
const Svg = ({ children, size = 18, className = "", sw = 1.9 }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={sw}
       strokeLinecap="round" strokeLinejoin="round" className={className} aria-hidden="true">{children}</svg>
);
const I = {
  send: <path d="M4 12l16-8-6 16-2.5-6.5L4 12z" />,
  close: <path d="M6.5 6.5l11 11M17.5 6.5l-11 11" />,
  reset: <><path d="M4 12a8 8 0 1 0 2.6-5.9" /><path d="M4 4v4h4" /></>,
  arrow: <path d={AR ? "M15 6l-6 6 6 6" : "M9 6l6 6-6 6"} />,
  human: <><circle cx="12" cy="8.5" r="3.5" /><path d="M5 20c1.2-3.6 3.8-5.4 7-5.4s5.8 1.8 7 5.4" /></>,
  bulb: <><path d="M9 18h6M10 21h4" /><path d="M12 3a6 6 0 0 0-3.6 10.8c.8.6 1.1 1.3 1.1 2.2h5c0-.9.3-1.6 1.1-2.2A6 6 0 0 0 12 3z" /></>,
  mic: <><rect x="9" y="3" width="6" height="11" rx="3" /><path d="M5.5 11a6.5 6.5 0 0 0 13 0M12 17.5V21" /></>,
  micOff: <><path d="M15 9.4V6a3 3 0 0 0-5.7-1.3M9 9v2a3 3 0 0 0 4.6 2.5" /><path d="M5.5 11a6.5 6.5 0 0 0 10.9 4.8M18.5 11c0 .8-.1 1.5-.4 2.2M12 17.5V21M3 3l18 18" /></>,
  wave: <path d="M4 10v4M8 7v10M12 4v16M16 7v10M20 10v4" />,
  expand: <path d="M14 4h6v6M10 20H4v-6M20 4l-7 7M4 20l7-7" />,
  shrink: <path d="M20 4l-6 6M14 5v5h5M4 20l6-6M10 19v-5H5" />,
  dots: <><circle cx="5" cy="12" r="1.3" /><circle cx="12" cy="12" r="1.3" /><circle cx="19" cy="12" r="1.3" /></>,
  speaker: <><path d="M4 9.5h3.5L12 5.5v13l-4.5-4H4z" /><path d="M16 9a4 4 0 0 1 0 6M18.6 6.5a7.5 7.5 0 0 1 0 11" /></>,
  mute: <><path d="M4 9.5h3.5L12 5.5v13l-4.5-4H4z" /><path d="M16.5 9.5l5 5M21.5 9.5l-5 5" /></>,
  eyeOff: <><path d="M3 3l18 18" /><path d="M10.6 5.1A10 10 0 0 1 12 5c5 0 9 4.5 10 7-.4 1-1.2 2.3-2.4 3.5M6.6 6.7C4.5 8 3 10 2 12c1 2.5 5 7 10 7 1.7 0 3.3-.5 4.6-1.3" /><path d="M9.9 9.9a3 3 0 0 0 4.2 4.2" /></>,
  copy: <><rect x="8" y="8" width="12" height="12" rx="2.5" /><path d="M16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2" /></>,
  check: <path d="M5 12.5l4.5 4.5L19 7.5" />,
  play: <path d="M8 5.5v13l11-6.5z" />,
  pause: <path d="M8 5v14M16 5v14" />,
  compass: <><circle cx="12" cy="12" r="9" /><path d="M15.5 8.5l-2 5-5 2 2-5z" /></>,
  plus: <path d="M12 5v14M5 12h14" />,
  wand: <><path d="M4 20L15 9M14 4v2M19 9h2M17.5 5.5l1.5-1.5M13 7l4 4" /></>,
  chat: <path d="M5 18.5V7a3 3 0 0 1 3-3h8a3 3 0 0 1 3 3v6a3 3 0 0 1-3 3H8.5z" />,
  info: <><circle cx="12" cy="12" r="9" /><path d="M12 11v5.5M12 7.6v.1" /></>,
  help: <><circle cx="12" cy="12" r="9" /><path d="M9.6 9.3a2.5 2.5 0 1 1 3.6 2.3c-.8.4-1.2 1-1.2 1.9M12 16.6v.1" /></>,
  bag: <><path d="M5 8h14l-1 12H6z" /><path d="M9 8V6.5a3 3 0 0 1 6 0V8" /></>,
  share: <><circle cx="6" cy="12" r="2.5" /><circle cx="17" cy="6" r="2.5" /><circle cx="17" cy="18" r="2.5" /><path d="M8.3 10.8l6.4-3.6M8.3 13.2l6.4 3.6" /></>,
  bolt: <path d="M13 3L5 13.5h6L10 21l8-10.5h-6z" />,
  chart: <path d="M4 20V10M10 20V4M16 20v-7M22 20H2" />,
  keyboard: <><rect x="2.5" y="6" width="19" height="12" rx="2.5" /><path d="M6.5 10h.1M10 10h.1M13.5 10h.1M17 10h.1M7.5 14h9" /></>,
};
const Ic = ({ n, ...p }) => <Svg {...p}>{I[n]}</Svg>;
const ACT_ICON = {
  navigate: "compass", create_telegram_bot: "plus", design_bot: "wand", set_welcome: "chat", update_info: "info",
  add_faq: "help", add_product: "bag", ai_replies: "bolt", start_bot: "play", stop_bot: "pause", share_bot: "share",
  team_help: "human",
};

/* علامة المساعد: شرارتان بتدرّج — بدل وجه الروبوت الكرتوني */
function Spark({ size = 22, id = "bys" }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" aria-hidden="true">
      <defs>
        <linearGradient id={id} x1="3" y1="2" x2="21" y2="22" gradientUnits="userSpaceOnUse">
          <stop offset="0" stopColor="#E4F9FF" /><stop offset=".45" stopColor="#8FE9FF" /><stop offset="1" stopColor="#B9AFFF" />
        </linearGradient>
      </defs>
      <path fill={`url(#${id})`} d="M10.2 3.2c.3-.9 1.5-.9 1.8 0l1.2 3.6a5 5 0 0 0 3.2 3.2l3.6 1.2c.9.3.9 1.5 0 1.8l-3.6 1.2a5 5 0 0 0-3.2 3.2L12 20c-.3.9-1.5.9-1.8 0L9 16.4a5 5 0 0 0-3.2-3.2L2.2 12c-.9-.3-.9-1.5 0-1.8l3.6-1.2A5 5 0 0 0 9 5.8z" />
      <path fill={`url(#${id})`} opacity=".85" d="M18.6 1.6c.1-.4.7-.4.8 0l.4 1.2c.2.6.6 1 1.2 1.2l1.2.4c.4.1.4.7 0 .8l-1.2.4c-.6.2-1 .6-1.2 1.2l-.4 1.2c-.1.4-.7.4-.8 0l-.4-1.2a1.9 1.9 0 0 0-1.2-1.2l-1.2-.4c-.4-.1-.4-.7 0-.8l1.2-.4c.6-.2 1-.6 1.2-1.2z" />
    </svg>
  );
}

/* الكرة: هوية المساعد في الرأس وفي الوضع الصوتي. تتنفّس وحدها، وتنبض بمستوى الصوت الحيّ (LEVEL). */
const ORB_TINT = {
  listening: ["#22d3ee", "#2dd4a7"], speaking: ["#7c6cf6", "#c084fc"], thinking: ["#7c6cf6", "#22d3ee"],
  idle: ["#7c6cf6", "#22d3ee"],
};
function Orb({ size = 40, state = "idle", live = false, spark = true }) {
  const core = useRef(null);
  const halo = useRef(null);
  const reduce = useReducedMotion();
  useEffect(() => {
    if (!live || reduce) return undefined;
    let raf, cur = 0;
    const tick = (t) => {
      const target = state === "thinking" ? 0.18 + 0.12 * Math.sin(t / 260) : LEVEL.v;
      cur += (target - cur) * 0.22;
      if (core.current) core.current.style.transform = `scale(${1 + cur * 0.22})`;
      if (halo.current) { halo.current.style.opacity = String(0.35 + cur * 0.65); halo.current.style.transform = `scale(${1.05 + cur * 0.45})`; }
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [live, state, reduce]);
  const [a, b] = ORB_TINT[state] || ORB_TINT.idle;
  const spin = reduce ? "none" : `by-orb-spin ${state === "thinking" ? 1.6 : 7}s linear infinite`;
  return (
    <span className="relative inline-grid shrink-0 place-items-center" style={{ width: size, height: size }}>
      <span ref={halo} aria-hidden="true" className="absolute inset-0 rounded-full blur-xl transition-colors duration-500"
            style={{ background: `radial-gradient(closest-side, ${a}, transparent)`, opacity: 0.35 }} />
      <span ref={core} className="relative grid size-full place-items-center rounded-full transition-transform duration-75">
        <span aria-hidden="true" className="absolute inset-0 rounded-full"
              style={{ background: `conic-gradient(from 0deg, ${a}, ${b}, #8FE9FF, ${a})`, animation: spin }} />
        <span aria-hidden="true" className="absolute rounded-full bg-[#0a0e19]"
              style={{ inset: Math.max(2, size * 0.06) }} />
        <span aria-hidden="true" className="absolute rounded-full opacity-90 blur-[6px]"
              style={{ inset: size * 0.2, background: `radial-gradient(circle at 35% 30%, #ffffff55, transparent 45%), radial-gradient(circle, ${b}cc, ${a}55 60%, transparent 75%)`,
                       animation: reduce ? "none" : `by-orb-spin ${state === "thinking" ? 2.2 : 9}s linear infinite reverse` }} />
        {spark && <span className="relative"><Spark size={size * 0.46} id={`bys${size}`} /></span>}
      </span>
    </span>
  );
}

function Typing({ label }) {
  return (
    <div className="flex items-center gap-2.5 ps-0.5">
      <Orb size={26} state="thinking" live spark={false} />
      <div className="flex items-center gap-2 text-[12.5px] font-semibold text-[#8b97b8]">
        <span className="by-shimmer">{label}</span>
      </div>
    </div>
  );
}

function Chip({ children, onClick, href, tone = "ghost", external, icon }) {
  const cls = "inline-flex max-w-full items-center gap-1.5 rounded-full px-3.5 py-2 text-[12.5px] font-bold no-underline " +
    "transition-all duration-200 hover:-translate-y-px cursor-pointer border-0 focus-visible:outline-2 focus-visible:outline-[#8FE9FF] " +
    (tone === "go"
      ? "bg-[linear-gradient(100deg,#8FE9FF,#B9AFFF)] text-[#07090F] shadow-[0_6px_20px_-8px_rgb(143_233_255/0.7)]"
      : tone === "wa"
        ? "bg-[#25D366]/15 text-[#5BE38F] shadow-[inset_0_0_0_1px_rgb(37_211_102/0.4)] hover:bg-[#25D366]/25"
        : "bg-white/[0.05] text-[#dfe6f7] shadow-[inset_0_0_0_1px_rgb(255_255_255/0.1)] hover:bg-white/[0.09]");
  if (href) {
    return <a href={href} className={cls} {...(external ? { target: "_blank", rel: "noopener" } : {})}>
      {icon && <Ic n={icon} size={14} />}<span className="truncate">{children}</span><Ic n="arrow" size={13} /></a>;
  }
  return <button type="button" onClick={onClick} className={cls}>{icon && <Ic n={icon} size={14} />}<span className="truncate">{children}</span></button>;
}

function IconBtn({ n, label, onClick, active, className = "", size = 17 }) {
  return (
    <button type="button" onClick={onClick} title={label} aria-label={label} aria-pressed={active === undefined ? undefined : !!active}
      className={"grid size-9 shrink-0 cursor-pointer place-items-center rounded-xl border-0 transition-colors " +
        "focus-visible:outline-2 focus-visible:outline-[#8FE9FF] " +
        (active ? "bg-[#8FE9FF]/15 text-[#BFF3FF] " : "bg-transparent text-[#9aa6c4] hover:bg-white/[0.07] hover:text-white ") + className}>
      <Ic n={n} size={size} />
    </button>
  );
}

/* ---------------------------------------------------------------- نص الرد */
function Inline({ text }) {
  return String(text).split(/(«[^»\n]{1,70}»)/g).map((p, i) =>
    p.length > 2 && p.startsWith("«") && p.endsWith("»")
      ? <span key={i} dir="auto" className="mx-px whitespace-nowrap rounded-md bg-[#8FE9FF]/[0.11] px-1.5 py-px font-bold text-[#C7F5FF]">{p.slice(1, -1)}</span>
      : <Fragment key={i}>{p}</Fragment>);
}
/* أسطر مرقّمة ⇒ خطوات · «•»/«-» ⇒ نقاط · غير ذلك فقرات — بلا Markdown خام */
function Rich({ text }) {
  const blocks = [];
  for (const raw of String(text || "").split("\n")) {
    const line = raw.trim();
    if (!line) continue;
    const num = line.match(/^(\d{1,2})[.)\-]\s*(.+)$/);
    const dot = !num && line.match(/^[•\-–·]\s*(.+)$/);
    const kind = num ? "ol" : dot ? "ul" : "p";
    const body = num ? num[2] : dot ? dot[1] : line;
    const last = blocks[blocks.length - 1];
    if (kind !== "p" && last && last.kind === kind) last.items.push(body); else blocks.push({ kind, items: [body] });
  }
  return (
    <div className="flex flex-col gap-2">
      {blocks.map((b, i) => b.kind === "p"
        ? <p key={i} className={"m-0 " + (b.items[0].length <= 30 && !/[.!?؟:،,]$/.test(b.items[0]) && blocks[i + 1] && blocks[i + 1].kind !== "p"
              ? "mt-1 font-extrabold text-white" : "")}><Inline text={b.items[0]} /></p>
        : b.kind === "ol"
          ? <ol key={i} className="m-0 flex list-none flex-col gap-1.5 p-0">
              {b.items.map((it, j) => (
                <li key={j} className="flex gap-2.5">
                  <span className="mt-[3px] grid size-[20px] shrink-0 place-items-center rounded-full bg-[#8FE9FF]/[0.13] text-[11px] font-extrabold text-[#8FE9FF]">{j + 1}</span>
                  <span className="min-w-0"><Inline text={it} /></span>
                </li>))}
            </ol>
          : <ul key={i} className="m-0 flex list-none flex-col gap-1 p-0">
              {b.items.map((it, j) => (
                <li key={j} className="flex gap-2"><span className="mt-[9px] block size-1.5 shrink-0 rounded-full bg-[#B9AFFF]" /><span className="min-w-0"><Inline text={it} /></span></li>))}
            </ul>)}
    </div>
  );
}

/* ---------------------------------------------------------------- بطاقات الوكيل */
function ActionCard({ m, onDo, onSkip, voice }) {
  const a = m.action;
  const st = m.actState;                       // undefined=بانتظار موافقتك · run · done · fail · skip
  const [title, ...rest] = String(a.label || "").split("\n");
  return (
    <motion.div initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }}
      className={"mt-2.5 overflow-hidden rounded-2xl p-3.5 shadow-[inset_0_0_0_1px_rgb(143_233_255/0.26)] " +
        (st === "skip" ? "opacity-55 " : "") +
        "bg-[linear-gradient(135deg,rgb(124_108_246/0.18),rgb(34_211_238/0.07))]"}>
      <div className="flex items-start gap-3">
        <span className="grid size-9 shrink-0 place-items-center rounded-xl bg-[#8FE9FF]/[0.12] text-[#8FE9FF]">
          <Ic n={ACT_ICON[a.type] || "bolt"} size={18} />
        </span>
        <div className="min-w-0 flex-1">
          <div className="mb-0.5 flex items-center gap-1.5 text-[10.5px] font-extrabold uppercase tracking-[0.08em] text-[#8FE9FF]">
            {st === "run" ? bi("جاري التنفيذ…", "Working on it…") : st === "done" ? bi("تم التنفيذ", "Done")
              : st === "fail" ? bi("ما اتنفّذش", "Not done") : st === "skip" ? bi("اتلغى", "Skipped")
              : bi("مهمة بانتظار موافقتك", "Task awaiting your OK")}
            {st === "run" && <span className="size-3 animate-spin rounded-full border-2 border-[#8FE9FF]/30 border-t-[#8FE9FF]" />}
            {st === "done" && <Ic n="check" size={13} sw={2.6} />}
          </div>
          <div dir="auto" className="text-[14px] font-bold leading-relaxed text-white">{title}</div>
          {rest.length > 0 && <div dir="auto" className="mt-1 whitespace-pre-wrap text-[12.5px] leading-relaxed text-[#c9d3ea]">{rest.join("\n")}</div>}
          {a.warn && !st && <div dir="auto" className="mt-1.5 text-[12px] leading-relaxed text-[#aeb9d4]">⚠️ {a.warn}</div>}
        </div>
      </div>
      {!st && (
        <>
          <div className="mt-3 flex gap-2">
            <button type="button" onClick={onDo}
              className="flex flex-1 cursor-pointer items-center justify-center gap-1.5 rounded-xl border-0 bg-[linear-gradient(100deg,#8FE9FF,#B9AFFF)] px-4 py-2.5
                         text-[13.5px] font-extrabold text-[#07090F] transition-transform hover:-translate-y-px focus-visible:outline-2 focus-visible:outline-white">
              <Ic n="check" size={15} sw={2.6} />{bi("نفّذ", "Do it")}</button>
            <button type="button" onClick={onSkip}
              className="cursor-pointer rounded-xl border-0 bg-white/[0.06] px-4 py-2.5 text-[13px] font-bold text-[#dfe6f7]
                         shadow-[inset_0_0_0_1px_rgb(255_255_255/0.1)] hover:bg-white/[0.1]">{bi("مش دلوقتي", "Not now")}</button>
          </div>
          {voice && <div className="mt-2 text-center text-[11.5px] text-[#8b97b8]">{bi("أو قول «نفّذ» أو «لأ»", "or just say “do it” or “no”")}</div>}
        </>
      )}
    </motion.div>
  );
}

/* تنقّل الوكيل: يفتح الصفحة بعد لحظة (تقدر تلغيه) — والمحادثة تكمل في الصفحة الجديدة */
const GO_MS = 1600;
function GoCard({ go, onNow, onCancel }) {
  return (
    <div className="mt-2.5 overflow-hidden rounded-2xl bg-white/[0.04] shadow-[inset_0_0_0_1px_rgb(143_233_255/0.22)]">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2 p-3">
        <span className="grid size-9 shrink-0 place-items-center rounded-xl bg-[#8FE9FF]/[0.12] text-[#8FE9FF]"><Ic n="compass" size={18} /></span>
        <div className="min-w-[140px] flex-1">
          <div className="whitespace-nowrap text-[10.5px] font-extrabold uppercase tracking-[0.08em] text-[#8FE9FF]">
            {go.state === "cancel" ? bi("اتلغى", "Cancelled") : go.state === "done" ? bi("اتفتحت", "Opened") : bi("بفتحلك الصفحة…", "Opening the page…")}
          </div>
          <div dir="auto" className="truncate text-[14px] font-bold text-white">{go.label}</div>
        </div>
        {!go.state && (
          <div className="ms-auto flex shrink-0 gap-1.5">
            <button type="button" onClick={onNow} className="cursor-pointer rounded-lg border-0 bg-[#8FE9FF] px-3 py-1.5 text-[12px] font-extrabold text-[#07090F]">{bi("افتح", "Open")}</button>
            <button type="button" onClick={onCancel} className="cursor-pointer rounded-lg border-0 bg-white/[0.07] px-3 py-1.5 text-[12px] font-bold text-[#dfe6f7]">{bi("إلغاء", "Cancel")}</button>
          </div>
        )}
        {go.state === "done" && <a href={go.url} className="shrink-0 text-[12px] font-bold text-[#8FE9FF] no-underline hover:underline">{bi("افتحها تاني", "Open again")}</a>}
      </div>
      {!go.state && go.auto && (
        <motion.div className="h-[3px] origin-[0%] bg-[linear-gradient(90deg,#8FE9FF,#B9AFFF)] rtl:origin-[100%]"
          initial={{ scaleX: 0 }} animate={{ scaleX: 1 }} transition={{ duration: GO_MS / 1000, ease: "linear" }} />
      )}
    </div>
  );
}

function ResultExtra({ r }) {
  if (!r) return null;
  return (
    <div className="mt-2 flex flex-col gap-2">
      {r.qr && (
        <div className="flex items-center gap-3 rounded-2xl bg-white/[0.05] p-3 shadow-[inset_0_0_0_1px_rgb(255_255_255/0.08)]">
          <img src={r.qr} alt="" className="size-24 rounded-lg bg-white p-1" />
          <span className="text-[12px] leading-relaxed text-[#aeb9d4]">{bi("من الموبايل: امسح الكود بالكاميرا", "On your phone: scan with the camera")}</span>
        </div>
      )}
      <div className="flex flex-wrap gap-1.5">
        {r.link && /^https:\/\/t\.me\//.test(r.link) && <Chip href={r.link} tone="go" external>{bi("افتح تليجرام", "Open Telegram")}</Chip>}
        {r.share && /^https:\/\//.test(r.share) && <Chip href={r.share} tone="go" external>{bi("رابط البوت", "Bot link")}</Chip>}
        {r.poster && <Chip href={r.poster} external>{bi("الملصق للطباعة", "Printable poster")}</Chip>}
        {r.url && <Chip href={r.url}>{bi("افتح صفحة البوت", "Open bot page")}</Chip>}
      </div>
    </div>
  );
}

function MsgTools({ text, onSpeak }) {
  const [copied, setCopied] = useState(false);
  return (
    <div className="mt-1 flex gap-0.5 opacity-0 transition-opacity group-hover:opacity-100 group-focus-within:opacity-100 max-sm:opacity-60">
      <button type="button" aria-label={bi("نسخ", "Copy")} title={bi("نسخ", "Copy")}
        onClick={() => { try { navigator.clipboard.writeText(text); setCopied(true); setTimeout(() => setCopied(false), 1400); } catch { /* */ } }}
        className="grid size-7 cursor-pointer place-items-center rounded-lg border-0 bg-transparent text-[#6f7b9c] hover:bg-white/[0.06] hover:text-white">
        <Ic n={copied ? "check" : "copy"} size={14} />
      </button>
      {onSpeak && (
        <button type="button" aria-label={bi("اسمعها", "Read aloud")} title={bi("اسمعها", "Read aloud")} onClick={onSpeak}
          className="grid size-7 cursor-pointer place-items-center rounded-lg border-0 bg-transparent text-[#6f7b9c] hover:bg-white/[0.06] hover:text-white">
          <Ic n="speaker" size={14} />
        </button>
      )}
    </div>
  );
}

function Bubble({ m, last, busy, voice, onPick, onHandoff, onAct, onSkip, onGo, onGoCancel, onSpeak }) {
  if (m.me) {
    return (
      <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="flex justify-end">
        <div dir="auto" className="max-w-[84%] whitespace-pre-wrap break-words rounded-[20px] rounded-ee-md px-4 py-2.5 text-[14.5px]
                        leading-relaxed text-[#07090F] bg-[linear-gradient(120deg,#8FE9FF,#B9AFFF)] shadow-[0_8px_24px_-14px_rgb(143_233_255/0.8)]">
          {m.spoken && <Ic n="mic" size={12} className="me-1 inline-block align-[-1px] opacity-60" />}{m.text}
        </div>
      </motion.div>
    );
  }
  return (
    <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="group flex items-start gap-2.5">
      <span className="mt-0.5"><Orb size={26} /></span>
      <div className="min-w-0 flex-1">
        <div dir="auto" className={"break-words text-[14.5px] leading-[1.8] " +
             (m.err ? "rounded-2xl bg-red-400/10 px-3.5 py-2.5 text-red-200 shadow-[inset_0_0_0_1px_rgb(248_113_113/0.3)]" : "pt-0.5 text-[#e8edf9]")}>
          <Rich text={m.text} />
        </div>
        {m.detail && (
          <div dir="auto" className="mt-2.5 rounded-2xl bg-white/[0.035] p-4 text-[13.5px] leading-[1.75] text-[#dfe6f7]
                          shadow-[inset_0_0_0_1px_rgb(143_233_255/0.18)]">
            <div className="mb-2 flex items-center gap-1.5 text-[10.5px] font-extrabold uppercase tracking-[0.08em] text-[#8FE9FF]">
              <Ic n="chart" size={13} />{bi("التقرير", "Report")}
            </div>
            <Rich text={m.detail} />
          </div>
        )}
        <ResultExtra r={m.result} />
        {m.go && <GoCard go={m.go} onNow={() => onGo(m)} onCancel={() => onGoCancel(m)} />}
        {m.action && <ActionCard m={m} voice={voice} onDo={() => onAct(m)} onSkip={() => onSkip(m)} />}
        {(m.links?.length > 0 || m.wa) && (
          <div className="mt-2.5 flex flex-wrap gap-1.5">
            {(m.links || []).map((l) => <Chip key={l.k} href={l.url} tone="go">{l.label}</Chip>)}
            {m.wa && <Chip href={m.wa} tone="wa" external>{bi("افتح واتساب", "Open WhatsApp")}</Chip>}
          </div>
        )}
        {last && !busy && m.handoff && !m.handed && (
          <div className="mt-2"><Chip onClick={onHandoff} icon="human">{bi("كلّم فريق الدعم", "Talk to support")}</Chip></div>
        )}
        {last && !busy && m.suggestions?.length > 0 && (
          <div className="mt-2.5 flex flex-wrap gap-1.5">
            {m.suggestions.map((s) => <Chip key={s} onClick={() => onPick(s)}>{s}</Chip>)}
          </div>
        )}
        {!m.err && <MsgTools text={m.detail ? m.text + "\n\n" + m.detail : m.text} onSpeak={onSpeak ? () => onSpeak(m.text) : null} />}
      </div>
    </motion.div>
  );
}

/* ---------------------------------------------------------------- الترحيب */
const TASKS = SIGNED ? [
  ["plus", bi("اعملّي بوت جديد", "Make me a new bot"), bi("اعملّي بوت تليجرام جديد لنشاطي", "Create a new Telegram bot for my business")],
  ["chart", bi("أرقامي النهارده", "My numbers today"), bi("قولّي أرقامي النهارده والأسبوع ده", "Tell me my numbers for today and this week")],
  ["chat", bi("غيّر رسالة الترحيب", "Change the welcome"), bi("عايز أغيّر رسالة الترحيب في البوت", "I want to change my bot's welcome message")],
  ["bolt", bi("شغّل الردود الذكية", "Turn on AI replies"), bi("شغّل الردود الذكية في البوت بتاعي", "Turn on smart replies for my bot")],
  ["compass", bi("ودّيني صندوق الوارد", "Take me to the inbox"), bi("ودّيني صندوق الوارد", "Take me to the inbox")],
  ["wand", bi("جهّز البوت لنشاطي", "Set up my bot"), bi("صمّملي البوت على نشاطي", "Design my bot for my business")],
] : [
  ["info", bi("إيه هي BotYalla؟", "What is BotYalla?"), bi("إيه هي BotYalla؟", "What is BotYalla?")],
  ["chart", bi("أنهي باقة تناسبني؟", "Which plan fits me?"), bi("أنهي باقة تناسبني؟", "Which plan fits me?")],
  ["plus", bi("إزاي أبدأ؟", "How do I start?"), bi("إزاي أبدأ؟", "How do I start?")],
  ["chat", bi("بتشتغل على واتساب؟", "Does it do WhatsApp?"), bi("بتشتغل على واتساب الرسمي؟", "Does it work on official WhatsApp?")],
];

function PageGuide() {
  if (!(BOOT?.tips?.length > 0)) return null;
  return (
    <div className="rounded-2xl bg-[linear-gradient(135deg,rgb(124_108_246/0.14),rgb(34_211_238/0.05))] p-4 shadow-[inset_0_0_0_1px_rgb(124_108_246/0.25)]">
      <div className="mb-2 flex items-center gap-2 text-[11.5px] font-extrabold uppercase tracking-wider text-[#B9AFFF]">
        <Ic n="bulb" size={15} />{bi("الصفحة دي", "This page")} · <span className="normal-case text-[#dfe6f7]">{BOOT.title}</span>
      </div>
      <ul className="m-0 flex list-none flex-col gap-1.5 p-0">
        {BOOT.tips.map((t, i) => (
          <li key={i} dir="auto" className="flex gap-2 text-[13px] leading-relaxed text-[#c9d3ea]">
            <span className="mt-2 block size-1.5 shrink-0 rounded-full bg-[#8FE9FF]" />{t}
          </li>
        ))}
      </ul>
    </div>
  );
}

function Welcome({ onPick, onVoice, voiceOk, wide }) {
  const hour = new Date().getHours();
  const hi = AR ? (hour < 12 ? "صباح الخير" : "مساء الخير") : (hour < 12 ? "Good morning" : hour < 18 ? "Good afternoon" : "Good evening");
  return (
    <div className="flex flex-col gap-5">
      <div className={"flex flex-col items-center text-center " + (wide ? "pt-6" : "pt-1")}>
        <Orb size={wide ? 84 : 64} live />
        <h2 className={"mb-1 mt-4 font-extrabold tracking-tight text-white " + (wide ? "text-[28px]" : "text-[21px]")}>
          {hi}{WHO ? (AR ? "، " : ", ") + WHO : ""} 👋
        </h2>
        <p dir="auto" className="m-0 max-w-[400px] text-[13.5px] leading-relaxed text-[#9aa6c4]">
          {SIGNED
            ? bi("أنا مساعدك الذكي — قولّي عايز إيه بالكلام أو بالصوت، وأنا أعمله بدالك في حسابك أو أشرحهولك خطوة بخطوة.",
                 "I'm your AI agent — tell me what you need, by text or voice, and I'll do it in your account or walk you through it.")
            : bi("اسألني عن أي حاجة في BotYalla — أشرحلك، أرشّحلك الباقة، وأساعدك تبدأ في دقيقة.",
                 "Ask me anything about BotYalla — I'll explain, suggest a plan and help you start in a minute.")}
        </p>
        {voiceOk && (
          <button type="button" onClick={onVoice}
            className="mt-4 inline-flex cursor-pointer items-center gap-2 rounded-full border-0 bg-white/[0.06] px-4 py-2.5 text-[13px] font-bold text-white
                       shadow-[inset_0_0_0_1px_rgb(143_233_255/0.35)] transition-all hover:-translate-y-px hover:bg-white/[0.1]">
            <span className="grid size-6 place-items-center rounded-full bg-[linear-gradient(120deg,#8FE9FF,#B9AFFF)] text-[#07090F]"><Ic n="wave" size={13} sw={2.4} /></span>
            {bi("كلّمني بصوتك", "Talk to me")}
          </button>
        )}
      </div>
      <div>
        <div className="mb-2 px-0.5 text-[11.5px] font-extrabold uppercase tracking-wider text-[#6f7b9c]">
          {SIGNED ? bi("أقدر أعملك", "I can do") : bi("ابدأ من هنا", "Start here")}
        </div>
        <div className={"grid gap-2 " + (wide ? "grid-cols-3" : "grid-cols-2")}>
          {TASKS.map(([icon, label, q]) => (
            <button key={label} type="button" onClick={() => onPick(q)}
              className="group flex cursor-pointer flex-col items-start gap-2 rounded-2xl border-0 bg-white/[0.035] p-3 text-start
                         shadow-[inset_0_0_0_1px_rgb(255_255_255/0.07)] transition-all duration-200 hover:-translate-y-0.5 hover:bg-white/[0.07]
                         hover:shadow-[inset_0_0_0_1px_rgb(143_233_255/0.35)] focus-visible:outline-2 focus-visible:outline-[#8FE9FF]">
              <span className="grid size-8 place-items-center rounded-xl bg-[#8FE9FF]/[0.1] text-[#8FE9FF] transition-colors group-hover:bg-[#8FE9FF]/20">
                <Ic n={icon} size={16} /></span>
              <span dir="auto" className="text-[13px] font-bold leading-snug text-[#e8edf9]">{label}</span>
            </button>
          ))}
        </div>
      </div>
      {!wide && <PageGuide />}
      {BOOT?.starters?.length > 0 && (
        <div className="flex flex-wrap justify-center gap-1.5">
          {BOOT.starters.map((s) => <Chip key={s} onClick={() => onPick(s)}>{s}</Chip>)}
        </div>
      )}
    </div>
  );
}

/* ---------------------------------------------------------------- الوضع الصوتي */
const V_LABEL = {
  listening: bi("بسمعك… اتكلّم براحتك", "Listening… go ahead"),
  thinking: bi("ثانية بفكّر…", "Thinking…"),
  speaking: bi("بتكلّم — المس الكرة عشان تقاطعني", "Speaking — tap the orb to interrupt"),
  idle: bi("المس الكرة وابدأ الكلام", "Tap the orb and start talking"),
};
function VoiceStage({ state, interim, caption, muted, error, pending, wide, onOrb, onMute, onEnd, onKeyboard, onDo, onSkip }) {
  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
      className="relative flex min-h-0 flex-1 flex-col items-center justify-between px-5 pb-5 pt-4">
      <div aria-hidden="true" className="pointer-events-none absolute inset-0 bg-[radial-gradient(60%_45%_at_50%_42%,rgb(124_108_246/0.22),transparent)]" />
      <div className="relative rounded-full bg-white/[0.05] px-3.5 py-1.5 text-[12px] font-bold text-[#c9d3ea] shadow-[inset_0_0_0_1px_rgb(255_255_255/0.08)]"
           role="status" aria-live="polite">
        {error || (muted ? bi("المايك مقفول", "Mic muted") : V_LABEL[state] || V_LABEL.idle)}
      </div>
      <button type="button" onClick={onOrb} aria-label={V_LABEL[state] || V_LABEL.idle}
        className="relative my-4 cursor-pointer rounded-full border-0 bg-transparent p-6 focus-visible:outline-2 focus-visible:outline-[#8FE9FF]">
        <Orb size={wide ? 220 : 168} state={state || "idle"} live />
      </button>
      <div className="relative flex min-h-[86px] w-full max-w-[560px] flex-col items-center justify-start gap-2 text-center">
        <AnimatePresence mode="wait">
          {state === "listening" && interim && (
            <motion.p key="in" dir="auto" initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}
              className="m-0 text-[17px] font-semibold leading-relaxed text-white">{interim}</motion.p>
          )}
          {state !== "listening" && caption && (
            <motion.p key={"c" + caption.slice(0, 20)} dir="auto" initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}
              className="m-0 line-clamp-4 text-[15px] leading-relaxed text-[#c9d3ea]">{caption}</motion.p>
          )}
        </AnimatePresence>
        {pending && (
          <div className="mt-1 w-full rounded-2xl bg-white/[0.05] p-3 text-start shadow-[inset_0_0_0_1px_rgb(143_233_255/0.3)]">
            <div dir="auto" className="text-[13px] font-bold text-white">{String(pending.action.label).split("\n")[0]}</div>
            <div className="mt-2 flex gap-2">
              <button type="button" onClick={onDo} className="flex-1 cursor-pointer rounded-xl border-0 bg-[linear-gradient(100deg,#8FE9FF,#B9AFFF)] py-2 text-[13px] font-extrabold text-[#07090F]">{bi("نفّذ", "Do it")}</button>
              <button type="button" onClick={onSkip} className="cursor-pointer rounded-xl border-0 bg-white/[0.07] px-4 py-2 text-[13px] font-bold text-[#dfe6f7]">{bi("لأ", "No")}</button>
            </div>
          </div>
        )}
      </div>
      <div className="relative mt-3 flex items-center gap-4">
        <button type="button" onClick={onKeyboard} aria-label={bi("ارجع للكتابة", "Back to typing")} title={bi("ارجع للكتابة", "Back to typing")}
          className="grid size-12 cursor-pointer place-items-center rounded-full border-0 bg-white/[0.07] text-[#dfe6f7] hover:bg-white/[0.12]"><Ic n="keyboard" size={20} /></button>
        <button type="button" onClick={onMute} aria-pressed={muted} aria-label={muted ? bi("افتح المايك", "Unmute") : bi("اقفل المايك", "Mute")}
          className={"grid size-14 cursor-pointer place-items-center rounded-full border-0 transition-colors " +
            (muted ? "bg-red-500/20 text-red-300 shadow-[inset_0_0_0_1px_rgb(248_113_113/0.5)]" : "bg-white/[0.1] text-white hover:bg-white/[0.16]")}>
          <Ic n={muted ? "micOff" : "mic"} size={22} /></button>
        <button type="button" onClick={onEnd} aria-label={bi("إنهاء المحادثة الصوتية", "End voice chat")} title={bi("إنهاء", "End")}
          className="grid size-12 cursor-pointer place-items-center rounded-full border-0 bg-red-500 text-white shadow-[0_10px_30px_-10px_rgb(239_68_68/0.8)] hover:bg-red-400">
          <Ic n="close" size={20} sw={2.4} /></button>
      </div>
    </motion.div>
  );
}

/* ================================================================== المكوّن */
export default function Assistant() {
  const reduce = useReducedMotion();
  const [open, setOpen] = useState(() => SS.get(KEY + ":open", "") === "1");
  const [dock, setDock] = useState(() => LS.get("by-asst:dock", "show"));
  const [size, setSize] = useState(() => LS.get("by-asst:size", "panel"));
  const [speakOn, setSpeakOn] = useState(() => LS.get("by-asst:speak", "0") === "1");
  const [msgs, setMsgs] = useState(load);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [teaser, setTeaser] = useState(false);
  const [menu, setMenu] = useState(false);
  const [dictating, setDictating] = useState(false);
  const [vstate, setVstateS] = useState(null);       // null = الصوت مقفول
  const [interim, setInterim] = useState("");
  const [caption, setCaption] = useState("");
  const [muted, setMuted] = useState(false);
  const [verr, setVerr] = useState("");
  const [toast, setToast] = useState("");
  const scroller = useRef(null);
  const input = useRef(null);
  const msgsRef = useRef(msgs);
  const vRef = useRef(null);
  const listener = useRef(null);
  const dictator = useRef(null);
  const goTimer = useRef(null);
  const empties = useRef(0);
  const voiceOk = !!BOOT && canListen(BOOT);
  const speaker = useMemo(() => (BOOT ? createSpeaker({ boot: BOOT, csrf: BY.csrf, lang: LANG, onLevel: (v) => { LEVEL.v = v; } }) : null), []);
  const full = size === "full";

  const setV = (s) => { vRef.current = s; setVstateS(s); };
  const commit = (fn) => setMsgs((l) => { const n = fn(l); msgsRef.current = n; return n; });

  useEffect(() => { save(msgs); msgsRef.current = msgs; }, [msgs]);
  useEffect(() => { SS.set(KEY + ":open", open ? "1" : ""); }, [open]);
  useEffect(() => { LS.set("by-asst:dock", dock); }, [dock]);
  useEffect(() => { LS.set("by-asst:size", size); }, [size]);
  useEffect(() => { LS.set("by-asst:speak", speakOn ? "1" : "0"); }, [speakOn]);
  useEffect(() => {
    const el = scroller.current;
    if (el) el.scrollTo({ top: msgs.length ? el.scrollHeight : 0, behavior: reduce || !msgs.length ? "auto" : "smooth" });
  }, [msgs, busy, open, vstate, reduce]);
  useEffect(() => {
    if (!open) return undefined;
    setTeaser(false);
    const id = setTimeout(() => input.current?.focus({ preventScroll: true }), 260);
    return () => clearTimeout(id);
  }, [open, size]);
  /* الصفحة الكاملة تقفل تمرير ما خلفها */
  useEffect(() => {
    if (!(open && full)) return undefined;
    const prev = document.documentElement.style.overflow;
    document.documentElement.style.overflow = "hidden";
    return () => { document.documentElement.style.overflow = prev; };
  }, [open, full]);
  useEffect(() => {
    if (!toast) return undefined;
    const id = setTimeout(() => setToast(""), 3200);
    return () => clearTimeout(id);
  }, [toast]);
  /* تلميح لطيف مرة واحدة لكل صفحة — لا يتكرر بعد إغلاقه، ولا يظهر والزر مخفي */
  useEffect(() => {
    let seen = true;
    try { seen = localStorage.getItem(KEY + ":t:" + BOOT?.view) === "1"; } catch { /* */ }
    if (seen || load().length || dock === "hidden") return undefined;
    const id = setTimeout(() => setTeaser(true), 8000);
    return () => clearTimeout(id);
  }, [dock]);
  const hideTeaser = () => {
    setTeaser(false);
    try { localStorage.setItem(KEY + ":t:" + BOOT?.view, "1"); } catch { /* */ }
  };

  const history = () => msgsRef.current.filter((m) => !m.err && m.text).slice(-12)
    .map((m) => ({ role: m.me ? "user" : "bot", text: m.text }));

  /* ---------------------------------------------------------- الإرسال */
  const send = async (q, opts = {}) => {
    const body = String(q ?? text).trim();
    if (!body || busy) return null;
    if (!opts.voice) setText("");
    if (input.current) input.current.style.height = "";
    const hist = history();
    commit((l) => [...l.map((m) => (m.action && !m.actState ? { ...m, actState: "skip" } : m)), { me: true, text: body, spoken: !!opts.voice }]);
    setBusy(true);
    const r = await post(BOOT.api, { text: body, history: hist, view: BOOT.view, voice: !!opts.voice });
    setBusy(false);
    const reply = r.ok
      ? { text: r.reply, detail: r.detail || "", links: r.links, suggestions: r.suggestions, handoff: r.handoff || false, action: r.action || null,
          go: r.go && r.go.url ? { ...r.go, auto: !opts.voice } : null }
      : { text: r.error || bi("حصلت مشكلة — جرّب تاني.", "Something went wrong — try again."), err: true };
    reply.id = Date.now();
    commit((l) => [...l, reply]);
    if (reply.go && !opts.voice) scheduleGo(reply);
    if (!opts.voice && speakOn && speaker && !reply.err) speaker.say(reply.text);
    return reply;
  };

  const navigate = (url) => {
    SS.set(KEY + ":open", "1");                      // المحادثة تكمل مفتوحة في الصفحة الجديدة
    window.location.assign(url);
  };
  const markGo = (id, state) => commit((l) => l.map((m) => (m.id === id && m.go ? { ...m, go: { ...m.go, state } } : m)));
  const scheduleGo = (m) => {
    clearTimeout(goTimer.current);
    goTimer.current = setTimeout(() => { markGo(m.id, "done"); navigate(m.go.url); }, GO_MS);
  };
  const goNow = (m) => { clearTimeout(goTimer.current); markGo(m.id, "done"); navigate(m.go.url); };
  const goCancel = (m) => { clearTimeout(goTimer.current); markGo(m.id, "cancel"); };

  const handoff = async () => {
    setBusy(true);
    const r = await post(BOOT.handoff, { history: history(), view: BOOT.view });
    setBusy(false);
    commit((l) => [...l.map((m) => ({ ...m, handed: true })), r.ok
      ? { text: r.msg, wa: r.kind === "whatsapp" && /^https:\/\/wa\.me\//.test(r.url || "") ? r.url : null,
          links: r.kind === "ticket" ? [{ k: "support", label: bi("افتح التذكرة", "Open the ticket"), url: r.url }] : [] }
      : { text: r.error, err: true }]);
  };

  const setAct = (token, actState) => commit((l) => l.map((m) => (m.action && m.action.token === token ? { ...m, actState } : m)));
  const act = async (m) => {
    const a = m.action;
    setAct(a.token, "run");
    setBusy(true);
    const r = await post(BOOT.act, { token: a.token });
    setBusy(false);
    setAct(a.token, r.ok ? "done" : "fail");
    const out = r.ok
      ? { text: r.msg || bi("تم ✅", "Done ✅"), result: { link: r.link, qr: r.qr, share: r.share, poster: r.poster, url: r.url } }
      : { text: r.error || bi("مقدرتش أنفّذها — جرّب تاني.", "Couldn't do it — try again."), err: true,
          links: r.upgrade ? [{ k: "pricing", label: bi("الباقات", "Plans"), url: (BY.urls && BY.urls.pricing) || "/pricing" }] : [] };
    commit((l) => [...l, out]);
    if (!vRef.current && speakOn && speaker) speaker.say(out.text);
    return out;
  };
  const skip = (m) => setAct(m.action.token, "skip");
  const pendingAction = () => {
    const l = msgsRef.current;
    const m = l[l.length - 1];
    return m && m.action && !m.actState ? m : null;
  };

  /* ---------------------------------------------------------- الصوت */
  const VERR = {
    denied: bi("محتاج إذن المايك — اسمح بيه من القفل جنب عنوان الموقع.", "Microphone permission needed — allow it from the lock icon by the address bar."),
    unsupported: bi("المتصفح ده مش بيدعم الكلام — جرّب Chrome أو Edge.", "This browser doesn't support voice — try Chrome or Edge."),
    network: bi("التعرّف على الصوت محتاج إنترنت — جرّب تاني.", "Voice recognition needs a connection — try again."),
  };
  const say = async (t) => {
    if (!vRef.current || !speaker) return;
    setCaption(t);
    setV("speaking");
    await speaker.say(t);
  };
  const listen = () => {
    if (!vRef.current || !BOOT) return;
    listener.current?.abort();
    setInterim("");
    setVerr("");
    setV("listening");
    const l = createListener({
      lang: LANG, boot: BOOT, csrf: BY.csrf,
      onInterim: setInterim,
      onLevel: (v) => { LEVEL.v = v; },
      onState: (s) => { if (vRef.current && listener.current === l) setV(s); },
      onFinal: (t) => { if (listener.current === l) heard(t); },
      onEnd: () => {
        if (!vRef.current || listener.current !== l) return;
        empties.current += 1;
        if (empties.current < 2) listen(); else setV("idle");
      },
      onError: (e) => {
        if (listener.current !== l) return;
        setV("idle");
        setVerr(VERR[e] || (typeof e === "string" && e.length > 12 ? e : bi("مسمعتش كويس — المس الكرة وجرّب تاني.", "Didn't catch that — tap the orb and try again.")));
      },
    });
    listener.current = l;
    l.start();
  };
  const afterSpeech = (reply) => {
    if (!vRef.current) return;
    if (reply && reply.go) { markGo(reply.id, "done"); SS.set(KEY + ":voice", "1"); navigate(reply.go.url); return; }
    if (vRef.current === "speaking") listen();
  };
  const heard = async (t) => {
    empties.current = 0;
    setInterim(t);
    const pend = pendingAction();
    const yn = pend ? yesNo(t) : null;
    if (yn === "yes") {
      commit((l) => [...l, { me: true, text: t, spoken: true }]);
      setV("thinking");
      const out = await act(pend);
      await say(out.text);
      return afterSpeech(null);
    }
    if (yn === "no") {
      commit((l) => [...l, { me: true, text: t, spoken: true }]);
      skip(pend);
      await say(bi("تمام، مش هعمل حاجة. محتاج إيه تاني؟", "Okay, I won't. Anything else?"));
      return afterSpeech(null);
    }
    setV("thinking");
    const reply = await send(t, { voice: true });
    if (!reply) { listen(); return; }
    await say(reply.text);
    afterSpeech(reply);
  };
  const startVoice = () => {
    if (!voiceOk) { setToast(VERR.unsupported); return; }
    stopDictation();
    speaker?.unlock();
    empties.current = 0;
    setMuted(false);
    setCaption("");
    setOpen(true);
    vRef.current = "listening";
    listen();
  };
  const endVoice = () => {
    vRef.current = null;
    listener.current?.abort();
    listener.current = null;
    speaker?.stop();
    setV(null);
    setInterim("");
    LEVEL.v = 0;
  };
  const tapOrb = () => {
    if (muted) return;
    if (vRef.current === "speaking") { speaker?.stop(); listen(); }
    else if (vRef.current === "listening") listener.current?.stop();
    else if (vRef.current === "idle") { speaker?.unlock(); empties.current = 0; listen(); }
  };
  const toggleMute = () => {
    if (muted) { setMuted(false); empties.current = 0; listen(); }
    else { setMuted(true); listener.current?.abort(); listener.current = null; speaker?.stop(); setV("idle"); }
  };

  /* إملاء في خانة الكتابة: الكلام يتكتب، وانت تراجعه وتبعته */
  function stopDictation() { dictator.current?.stop(); }
  const toggleDictation = () => {
    if (dictating) { stopDictation(); return; }
    if (!voiceOk) { setToast(VERR.unsupported); return; }
    const base = text ? text.replace(/\s+$/, "") + " " : "";
    const d = createListener({
      lang: LANG, boot: BOOT, csrf: BY.csrf,
      onInterim: (t) => setText(base + t),
      onFinal: (t) => { setText(base + t); setDictating(false); input.current?.focus(); },
      onEnd: () => setDictating(false),
      onError: (e) => { setDictating(false); setToast(VERR[e] || bi("مسمعتش كويس — جرّب تاني.", "Didn't catch that — try again.")); },
    });
    dictator.current = d;
    setDictating(true);
    d.start();
  };

  /* ---------------------------------------------------------- الهيئة */
  const close = () => { endVoice(); stopDictation(); setMenu(false); setOpen(false); };
  const hideLauncher = () => {
    setDock("hidden"); close(); hideTeaser();
    setToast(bi("الزر اتخفى — هتلاقيه على حافة الشاشة، أو اضغط Ctrl + /", "Hidden — find it on the screen edge, or press Ctrl + /"));
  };
  const reset = () => { endVoice(); commit(() => []); setText(""); setMenu(false); };

  /* رجعنا من تنقّل أثناء محادثة صوتية: الوضع الصوتي جاهز وضغطة واحدة تكمل
     (المتصفح لا يسمح بالنطق في صفحة جديدة قبل لمسة من المستخدم) */
  useEffect(() => {
    if (SS.get(KEY + ":voice", "") !== "1" || !voiceOk) return;
    SS.set(KEY + ":voice", "");
    vRef.current = "idle";
    setV("idle");
    setCaption(bi("فتحتلك الصفحة ✓ — المس الكرة ونكمل كلامنا.", "Page opened ✓ — tap the orb to keep talking."));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  /* باقي الصفحة (رحلة النجاح في اللوحة) تفتح المساعد بطلب جاهز: window.BYAssistant.open("…") */
  useEffect(() => {
    window.BYAssistant = {
      open: (q) => { setOpen(true); if (q) setTimeout(() => send(q), 350); },
      voice: () => startVoice(),
    };
    return () => { delete window.BYAssistant; };
  });
  useEffect(() => {
    const key = (e) => {
      if ((e.ctrlKey || e.metaKey) && (e.key === "/" || e.code === "Slash")) {
        e.preventDefault();
        if (open) close(); else { setDock("show"); setOpen(true); }
        return;
      }
      if (e.key === "Escape" && open) {
        if (menu) setMenu(false);
        else if (vRef.current) endVoice();
        else if (full) setSize("panel");
        else close();
      }
    };
    document.addEventListener("keydown", key);
    return () => document.removeEventListener("keydown", key);
  });
  useEffect(() => () => { listener.current?.abort(); dictator.current?.abort(); speaker?.stop(); clearTimeout(goTimer.current); }, [speaker]);

  if (!BOOT) return null;
  const last = msgs.length - 1;
  const inVoice = vstate !== null;
  const status = inVoice ? (muted ? bi("المايك مقفول", "Mic muted") : V_LABEL[vstate]?.split("—")[0].split("…")[0] + "…")
    : busy ? bi("بشتغل على طلبك…", "Working on it…") : bi("متصل · جاهز ينفّذ لك", "Online · ready to act");
  const pend = inVoice ? (msgs[last] && msgs[last].action && !msgs[last].actState ? msgs[last] : null) : null;

  const panelCls = full
    ? "inset-0 rounded-none"
    : "inset-x-0 bottom-0 h-[92dvh] rounded-t-[28px] sm:inset-x-auto sm:bottom-5 sm:end-5 sm:h-[min(720px,calc(100dvh-40px))] sm:w-[430px] sm:rounded-[28px]";

  return (
    <div dir={AR ? "rtl" : "ltr"} className="font-[inherit]">
      {/* تنبيه صغير */}
      <AnimatePresence>
        {toast && (
          <motion.div role="status" initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: 8 }}
            className="fixed bottom-6 start-1/2 z-[400] w-[min(92vw,420px)] -translate-x-1/2 rounded-2xl bg-[#0b0f1a]/95 px-4 py-3 text-center text-[13px]
                       font-semibold text-white shadow-[0_18px_50px_-12px_rgb(0_0_0/0.7),inset_0_0_0_1px_rgb(143_233_255/0.25)] backdrop-blur-xl rtl:translate-x-1/2">
            {toast}
          </motion.div>
        )}
      </AnimatePresence>

      {/* التلميح */}
      <AnimatePresence>
        {teaser && !open && dock !== "hidden" && (
          <motion.div initial={{ opacity: 0, y: 10, scale: 0.95 }} animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 6, scale: 0.97 }}
            className="by-fab-hint fixed bottom-[96px] end-5 z-[340] w-[262px] rounded-2xl bg-[#0b0f1a]/95 p-3.5 pe-8 text-[13px] leading-relaxed
                       text-[#dfe6f7] shadow-[0_18px_50px_-12px_rgb(0_0_0/0.7),inset_0_0_0_1px_rgb(143_233_255/0.25)] backdrop-blur-xl">
            <button type="button" onClick={hideTeaser} aria-label={bi("إغلاق", "Close")}
              className="absolute end-2 top-2 grid size-6 cursor-pointer place-items-center rounded-full border-0 bg-transparent text-[#7b87a8] hover:text-white">
              <Ic n="close" size={14} />
            </button>
            <button type="button" onClick={() => { hideTeaser(); setOpen(true); }}
              className="cursor-pointer border-0 bg-transparent p-0 text-start text-inherit">
              <b className="text-white">{SIGNED ? bi("خلّيني أعملها بدالك ✨", "Let me do it for you ✨") : bi("محتاج مساعدة؟", "Need a hand?")}</b><br />
              {SIGNED ? bi("قولّي عايز إيه — بالكتابة أو بصوتك.", "Tell me what you need — by text or voice.")
                : bi(`اسألني عن «${BOOT.title}» وأنا أشرحلك.`, `Ask me about “${BOOT.title}”.`)}
            </button>
          </motion.div>
        )}
      </AnimatePresence>

      {/* الزر العائم — أو لسان صغير على الحافة لو مخفي */}
      <AnimatePresence>
        {!open && dock !== "hidden" && (
          <motion.div key="fab" initial={{ scale: 0, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} exit={{ scale: 0, opacity: 0 }}
            transition={{ type: "spring", stiffness: 420, damping: 26 }}
            className="by-fab group fixed bottom-5 end-5 z-[340]">
            <button type="button" onClick={() => setOpen(true)}
              aria-label={bi("افتح مساعد BotYalla (Ctrl + /)", "Open BotYalla assistant (Ctrl + /)")}
              className="relative flex h-[60px] cursor-pointer items-center gap-0 overflow-hidden rounded-full border-0 bg-[#0a0e19]/90 p-0 ps-[3px] pe-[3px]
                         shadow-[0_16px_44px_-12px_rgb(124_108_246/0.85),inset_0_0_0_1px_rgb(255_255_255/0.08)] backdrop-blur-xl
                         transition-[gap,padding] duration-300 hover:gap-2.5 hover:pe-5 focus-visible:gap-2.5 focus-visible:pe-5
                         focus-visible:outline-2 focus-visible:outline-[#8FE9FF]">
              <Orb size={54} live />
              <span className="max-w-0 overflow-hidden whitespace-nowrap text-[14px] font-extrabold text-white transition-[max-width] duration-300
                               group-hover:max-w-[180px] group-focus-within:max-w-[180px]">
                {SIGNED ? bi("اطلب من مساعدك", "Ask your agent") : bi("اسأل المساعد", "Ask the assistant")}
              </span>
            </button>
            <button type="button" onClick={hideLauncher} aria-label={bi("إخفاء زر المساعد", "Hide the assistant button")}
              title={bi("إخفاء", "Hide")}
              className="absolute -top-1.5 -start-1.5 grid size-6 cursor-pointer place-items-center rounded-full border-0 bg-[#1a2033] text-[#aeb9d4]
                         opacity-0 shadow-[0_4px_12px_rgb(0_0_0/0.5),inset_0_0_0_1px_rgb(255_255_255/0.12)] transition-opacity
                         hover:text-white group-hover:opacity-100 focus-visible:opacity-100 max-sm:hidden">
              <Ic n="close" size={12} sw={2.4} />
            </button>
          </motion.div>
        )}
        {!open && dock === "hidden" && (
          <motion.button key="tab" type="button" onClick={() => { setDock("show"); setOpen(true); }}
            initial={{ x: AR ? -40 : 40 }} animate={{ x: 0 }} exit={{ x: AR ? -40 : 40 }}
            aria-label={bi("أظهر مساعد BotYalla", "Show BotYalla assistant")} title={bi("المساعد (Ctrl + /)", "Assistant (Ctrl + /)")}
            className="by-fab fixed bottom-24 end-0 z-[340] grid h-14 w-7 cursor-pointer place-items-center rounded-s-2xl border-0 bg-[#0a0e19]/90 p-0
                       shadow-[0_10px_30px_-10px_rgb(124_108_246/0.8),inset_0_0_0_1px_rgb(255_255_255/0.1)] backdrop-blur-xl
                       transition-[width] duration-200 hover:w-10">
            <Spark size={16} id="bys-tab" />
          </motion.button>
        )}
      </AnimatePresence>

      {/* اللوحة / الصفحة الكاملة */}
      <AnimatePresence>
        {open && (
          <>
            <motion.div key="scrim" onClick={close} initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
              className={"fixed inset-0 z-[345] bg-[#03050a]/55 backdrop-blur-[3px] " + (full ? "" : "sm:hidden")} />
            <motion.section key="panel" layout={!reduce} role="dialog" aria-modal="true" aria-label={bi("مساعد BotYalla", "BotYalla assistant")}
              initial={{ opacity: 0, y: 28, scale: 0.96 }} animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: 20, scale: 0.97 }} transition={{ type: "spring", stiffness: 360, damping: 34 }}
              style={{ transformOrigin: AR ? "bottom left" : "bottom right" }}
              className={"fixed z-[350] flex flex-col overflow-hidden [overflow:clip] bg-[#070a12]/[0.97] text-[#f2f5fc] backdrop-blur-2xl " +
                         "shadow-[0_30px_100px_-20px_rgb(0_0_0/0.9),inset_0_0_0_1px_rgb(255_255_255/0.08)] " + panelCls}>
              <div aria-hidden="true" className="pointer-events-none absolute -top-28 inset-x-0 mx-auto h-56 w-full rounded-full
                                                  bg-[radial-gradient(closest-side,rgb(124_108_246/0.32),transparent)]" />
              {!full && <div aria-hidden="true" className="mx-auto mt-2 h-1 w-10 rounded-full bg-white/15 sm:hidden" />}

              {/* الرأس */}
              <header className={"relative flex items-center gap-3 pb-3 pt-3.5 shadow-[inset_0_-1px_0_rgb(255_255_255/0.06)] " + (full ? "px-5 sm:px-8" : "px-4")}>
                <Orb size={40} state={inVoice ? vstate : busy ? "thinking" : "idle"} live={busy || inVoice} />
                <div className="min-w-0 flex-1">
                  <div className="flex min-w-0 items-center gap-2 text-[15.5px] font-extrabold tracking-tight">
                    <span className="truncate" dir="auto">{bi("مساعد BotYalla", "BotYalla Agent")}</span>
                    <span className="shrink-0 rounded-md bg-[linear-gradient(100deg,#8FE9FF,#B9AFFF)] px-1.5 py-px text-[9.5px] max-[420px]:hidden font-black uppercase tracking-wider text-[#07090F]">AI</span>
                  </div>
                  <div className="flex items-center gap-1.5 text-[11.5px] text-[#7b87a8]" aria-live="polite">
                    <span className={"block size-1.5 rounded-full " + (inVoice || busy ? "animate-pulse bg-[#8FE9FF]" : "bg-[#2dd4a7]")} />
                    <span className="truncate">{status}</span>
                  </div>
                </div>
                {voiceOk && !inVoice && <IconBtn n="wave" label={bi("محادثة صوتية", "Voice chat")} onClick={startVoice} className="max-sm:hidden" />}
                <div className="relative">
                  <IconBtn n="dots" label={bi("خيارات", "Options")} onClick={() => setMenu((x) => !x)} active={menu} />
                  <AnimatePresence>
                    {menu && (
                      <motion.div initial={{ opacity: 0, y: -4, scale: 0.97 }} animate={{ opacity: 1, y: 0, scale: 1 }} exit={{ opacity: 0, y: -4 }}
                        role="menu" className="absolute end-0 top-11 z-10 w-[230px] rounded-2xl bg-[#0f1424] p-1.5 shadow-[0_20px_50px_-10px_rgb(0_0_0/0.8),inset_0_0_0_1px_rgb(255_255_255/0.1)]">
                        {[
                          ["speaker", speakOn ? bi("إيقاف قراءة الردود", "Stop reading replies") : bi("اقرأ الردود بصوت", "Read replies aloud"),
                            () => { setSpeakOn((x) => !x); if (speakOn) speaker?.stop(); }],
                          ["reset", bi("محادثة جديدة", "New chat"), reset],
                          ["human", bi("كلّم إنسان من الفريق", "Talk to a human"), () => { setMenu(false); handoff(); }],
                          ["eyeOff", bi("إخفاء زر المساعد", "Hide the launcher"), hideLauncher],
                        ].map(([icon, label, fn]) => (
                          <button key={label} type="button" role="menuitem" onClick={() => { fn(); if (icon !== "speaker") setMenu(false); }}
                            className="flex w-full cursor-pointer items-center gap-2.5 rounded-xl border-0 bg-transparent px-3 py-2.5 text-start text-[13px] font-semibold text-[#dfe6f7] hover:bg-white/[0.07]">
                            <Ic n={icon} size={16} className="text-[#8FE9FF]" />{label}
                            {icon === "speaker" && <span className={"ms-auto block size-2 rounded-full " + (speakOn ? "bg-[#2dd4a7]" : "bg-white/20")} />}
                          </button>
                        ))}
                      </motion.div>
                    )}
                  </AnimatePresence>
                </div>
                <IconBtn n={full ? "shrink" : "expand"} label={full ? bi("تصغير", "Collapse") : bi("صفحة كاملة", "Full screen")}
                  onClick={() => setSize(full ? "panel" : "full")} />
                <IconBtn n="close" label={bi("إغلاق (Esc)", "Close (Esc)")} onClick={close} size={18} />
              </header>

              <div className="relative flex min-h-0 flex-1">
                <div className="relative flex min-w-0 flex-1 flex-col">
                  <AnimatePresence mode="wait">
                    {inVoice ? (
                      <VoiceStage key="voice" state={vstate} interim={interim} caption={caption} muted={muted} error={verr}
                        pending={pend} wide={full}
                        onOrb={tapOrb} onMute={toggleMute} onEnd={endVoice} onKeyboard={endVoice}
                        onDo={async () => { if (!pend) return; setV("thinking"); listener.current?.abort(); const out = await act(pend); await say(out.text); afterSpeech(null); }}
                        onSkip={() => { if (pend) skip(pend); }} />
                    ) : (
                      <motion.div key="chat" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="flex min-h-0 flex-1 flex-col">
                        <div ref={scroller} className="relative flex-1 overflow-y-auto overscroll-contain" aria-live="polite">
                          <div className={"mx-auto flex flex-col gap-5 py-5 " + (full ? "max-w-[760px] px-5 sm:px-8" : "px-4")}>
                            {msgs.length === 0
                              ? <Welcome onPick={send} onVoice={startVoice} voiceOk={voiceOk} wide={full} />
                              : msgs.map((m, i) => (
                                <Bubble key={m.id || i} m={m} last={i === last} busy={busy} voice={false}
                                  onPick={send} onHandoff={handoff} onAct={act} onSkip={skip} onGo={goNow} onGoCancel={goCancel}
                                  onSpeak={speaker ? (t) => speaker.say(t) : null} />
                              ))}
                            {busy && <Typing label={bi("بشتغل على طلبك…", "Working on it…")} />}
                          </div>
                        </div>

                        <form onSubmit={(e) => { e.preventDefault(); send(); }}
                          className={"relative mx-auto w-full pb-3 pt-2 " + (full ? "max-w-[760px] px-5 sm:px-8" : "px-3")}>
                          <div className={"flex items-end gap-1.5 rounded-[22px] bg-white/[0.045] p-1.5 ps-4 transition-shadow " +
                                          (dictating ? "shadow-[inset_0_0_0_1.5px_rgb(248_113_113/0.6)]"
                                            : "shadow-[inset_0_0_0_1px_rgb(255_255_255/0.1)] focus-within:shadow-[inset_0_0_0_1.5px_rgb(143_233_255/0.55)]")}>
                            <textarea ref={input} value={text} rows={1} maxLength={1200} dir="auto"
                              onChange={(e) => { setText(e.target.value); e.target.style.height = "auto"; e.target.style.height = Math.min(e.target.scrollHeight, 140) + "px"; }}
                              onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); send(); } }}
                              placeholder={dictating ? bi("بسمعك… اتكلّم", "Listening… speak") : SIGNED ? bi("قولّي عايز تعمل إيه…", "Tell me what to do…") : bi("اكتب سؤالك…", "Ask anything…")}
                              aria-label={bi("رسالتك", "Your message")}
                              className="max-h-[140px] min-h-[42px] flex-1 resize-none border-0 bg-transparent py-2.5 text-[14.5px] leading-relaxed
                                         text-white outline-none placeholder:text-[#5c6683] focus:outline-none" />
                            {voiceOk && (
                              <button type="button" onClick={toggleDictation} aria-pressed={dictating}
                                aria-label={dictating ? bi("وقف الإملاء", "Stop dictation") : bi("اكتب بصوتك", "Dictate")}
                                title={dictating ? bi("وقف", "Stop") : bi("اكتب بصوتك", "Dictate")}
                                className={"relative grid size-[42px] shrink-0 cursor-pointer place-items-center rounded-2xl border-0 transition-colors " +
                                  (dictating ? "bg-red-500/20 text-red-300" : "bg-transparent text-[#9aa6c4] hover:bg-white/[0.07] hover:text-white")}>
                                {dictating && <span className="absolute inset-1 animate-ping rounded-2xl bg-red-400/20" />}
                                <Ic n="mic" size={19} />
                              </button>
                            )}
                            {text.trim() || !voiceOk ? (
                              <button type="submit" disabled={busy || !text.trim()} aria-label={bi("إرسال", "Send")}
                                className="grid size-[42px] shrink-0 cursor-pointer place-items-center rounded-2xl border-0 text-[#07090F]
                                           bg-[linear-gradient(120deg,#8FE9FF,#B9AFFF)] transition-opacity disabled:cursor-default disabled:opacity-35">
                                <Ic n="send" size={18} className={AR ? "-scale-x-100" : ""} />
                              </button>
                            ) : (
                              <button type="button" onClick={startVoice} aria-label={bi("محادثة صوتية", "Voice chat")} title={bi("محادثة صوتية", "Voice chat")}
                                className="grid size-[42px] shrink-0 cursor-pointer place-items-center rounded-2xl border-0 text-[#07090F]
                                           bg-[linear-gradient(120deg,#8FE9FF,#B9AFFF)] transition-transform hover:scale-105">
                                <Ic n="wave" size={18} sw={2.3} />
                              </button>
                            )}
                          </div>
                          <div className="mt-2 flex items-center justify-between gap-2 px-1.5 text-[10.5px] text-[#5c6683]">
                            <span>{SIGNED ? bi("مفيش حاجة بتتغيّر في حسابك من غير موافقتك.", "Nothing in your account changes without your OK.")
                              : bi("متبعتش كلمات سر أو أكواد هنا.", "Never share passwords or codes here.")}</span>
                            <button type="button" onClick={handoff} disabled={busy}
                              className="inline-flex shrink-0 cursor-pointer items-center gap-1 border-0 bg-transparent p-0 text-[11px] font-bold text-[#8FE9FF] hover:underline">
                              <Ic n="human" size={12} />{bi("كلّم إنسان", "Talk to a human")}
                            </button>
                          </div>
                        </form>
                      </motion.div>
                    )}
                  </AnimatePresence>
                </div>

                {/* عمود جانبي في الصفحة الكاملة على الشاشات الواسعة */}
                {full && (
                  <aside className="hidden w-[310px] shrink-0 flex-col gap-4 overflow-y-auto p-5 shadow-[inset_1px_0_0_rgb(255_255_255/0.06)] lg:flex rtl:shadow-[inset_-1px_0_0_rgb(255_255_255/0.06)]">
                    <PageGuide />
                    <div className="rounded-2xl bg-white/[0.03] p-4 shadow-[inset_0_0_0_1px_rgb(255_255_255/0.07)]">
                      <div className="mb-2.5 text-[11.5px] font-extrabold uppercase tracking-wider text-[#6f7b9c]">{bi("إزاي أشتغل", "How I work")}</div>
                      <ul className="m-0 flex list-none flex-col gap-2.5 p-0 text-[12.5px] leading-relaxed text-[#c9d3ea]">
                        <li className="flex gap-2"><Ic n="compass" size={15} className="mt-0.5 shrink-0 text-[#8FE9FF]" />{bi("أنقلك لأي صفحة فوراً.", "I open any page for you instantly.")}</li>
                        <li className="flex gap-2"><Ic n="check" size={15} className="mt-0.5 shrink-0 text-[#8FE9FF]" />{bi("أي تغيير في حسابك بيظهر كبطاقة — مفيش حاجة بتتنفّذ قبل «نفّذ».", "Every change shows as a card — nothing runs before “Do it”.")}</li>
                        <li className="flex gap-2"><Ic n="reset" size={15} className="mt-0.5 shrink-0 text-[#8FE9FF]" />{bi("تعديلات البوت ليها نسخة قديمة ترجّعها بضغطة.", "Bot edits keep the old version — one-tap undo.")}</li>
                        <li className="flex gap-2"><Ic n="wave" size={15} className="mt-0.5 shrink-0 text-[#8FE9FF]" />{bi("كلّمني بصوتك وقول «نفّذ» للموافقة.", "Talk to me and say “do it” to approve.")}</li>
                      </ul>
                    </div>
                    <div className="rounded-2xl bg-white/[0.03] p-4 text-[12px] text-[#8b97b8] shadow-[inset_0_0_0_1px_rgb(255_255_255/0.07)]">
                      <div className="mb-2 text-[11.5px] font-extrabold uppercase tracking-wider text-[#6f7b9c]">{bi("اختصارات", "Shortcuts")}</div>
                      <div className="flex justify-between py-1"><span>{bi("فتح/قفل المساعد", "Toggle assistant")}</span><kbd className="rounded-md bg-white/[0.08] px-1.5 font-mono text-[11px] text-white">Ctrl /</kbd></div>
                      <div className="flex justify-between py-1"><span>{bi("رجوع/قفل", "Back / close")}</span><kbd className="rounded-md bg-white/[0.08] px-1.5 font-mono text-[11px] text-white">Esc</kbd></div>
                      <div className="flex justify-between py-1"><span>{bi("سطر جديد", "New line")}</span><kbd className="rounded-md bg-white/[0.08] px-1.5 font-mono text-[11px] text-white">Shift ↵</kbd></div>
                    </div>
                  </aside>
                )}
              </div>
            </motion.section>
          </>
        )}
      </AnimatePresence>
    </div>
  );
}

/* يركّب المساعد في عنصر مستقل خارج شجرة الصفحة — خطأ فيه لا يُسقط الصفحة */
export function mountAssistant(createRoot) {
  if (!BOOT || document.getElementById("by-assistant")) return;
  const host = document.createElement("div");
  host.id = "by-assistant";
  document.body.appendChild(host);
  try { createRoot(host).render(<Assistant />); } catch (e) { console.error("assistant", e); }
}

