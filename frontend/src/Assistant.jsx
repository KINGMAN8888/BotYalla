import { useEffect, useRef, useState } from "react";
import { motion, AnimatePresence } from "motion/react";

/* ============================================================================
   «مساعد BotYalla» — فقاعة محادثة ذكية على صفحة الهبوط وكل صفحات اللوحة.
   نفس عقل بوت الدعم (site_assistant.py): يعرف الصفحة التي يقف عليها المستخدم وحالة
   حسابه، ويشرح بخطوات بأسماء الأزرار الفعلية. الروابط تأتي من الخادم وحده.
   الأيقونات مرسومة هنا (لا تعتمد على BY.icons — الموقع العام يحمل جزءاً منها فقط).
   ========================================================================== */

const BY = window.BY || {};
const AR = BY.lang !== "en";
const bi = (a, e) => (AR ? a : e);
const BOOT = BY.assistant || null;
/* المحادثة محفوظة لكل حساب على حدة — جهاز مشترك لا يُظهر محادثة حساب لحساب آخر */
const KEY = "by-assistant-v1:" + ((BY.user && BY.user.name) || (BY.auth && BY.auth.name) || "guest");

const load = () => {
  try { return JSON.parse(sessionStorage.getItem(KEY) || "[]"); } catch { return []; }
};
const save = (msgs) => {
  try { sessionStorage.setItem(KEY, JSON.stringify(msgs.slice(-30))); } catch { /* تصفح خاص */ }
};

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
const Svg = ({ d, size = 18, className = "", fill = "none" }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill={fill} stroke="currentColor" strokeWidth="1.9"
       strokeLinecap="round" strokeLinejoin="round" className={className} aria-hidden="true">{d}</svg>
);
const IcSend = (p) => <Svg {...p} d={<path d="M4 12l16-8-6 16-2.5-6.5L4 12z" />} />;
const IcClose = (p) => <Svg {...p} d={<path d="M6.5 6.5l11 11M17.5 6.5l-11 11" />} />;
const IcReset = (p) => <Svg {...p} d={<><path d="M4 12a8 8 0 1 0 2.6-5.9" /><path d="M4 4v4h4" /></>} />;
const IcArrow = (p) => <Svg {...p} d={<path d={AR ? "M15 6l-6 6 6 6" : "M9 6l6 6-6 6"} />} />;
const IcHuman = (p) => <Svg {...p} d={<><circle cx="12" cy="8.5" r="3.5" /><path d="M5 20c1.2-3.6 3.8-5.4 7-5.4s5.8 1.8 7 5.4" /></>} />;
const IcBulb = (p) => <Svg {...p} d={<><path d="M9 18h6M10 21h4" /><path d="M12 3a6 6 0 0 0-3.6 10.8c.8.6 1.1 1.3 1.1 2.2h5c0-.9.3-1.6 1.1-2.2A6 6 0 0 0 12 3z" /></>} />;

/* وجه المساعد: مدار متدرّج بعينين — هوية واحدة للزر والرأس والرسائل */
function Face({ size = 40, live = false }) {
  return (
    <span className="relative inline-grid shrink-0 place-items-center rounded-full"
          style={{ width: size, height: size,
                   background: "conic-gradient(from 200deg, #7c6cf6, #22d3ee, #2dd4a7, #7c6cf6)" }}>
      <span className="grid place-items-center rounded-full bg-[#0b0f1a]"
            style={{ width: size - 4, height: size - 4 }}>
        <svg width={size * 0.56} height={size * 0.56} viewBox="0 0 24 24" aria-hidden="true">
          <rect x="3.5" y="6" width="17" height="12.5" rx="5" fill="none" stroke="url(#byg)" strokeWidth="1.8" />
          <circle cx="9.2" cy="12.2" r="1.55" fill="#8FE9FF" />
          <circle cx="14.8" cy="12.2" r="1.55" fill="#B9AFFF" />
          <path d="M12 3.2v2.6" stroke="#8FE9FF" strokeWidth="1.8" strokeLinecap="round" />
          <defs><linearGradient id="byg" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0" stopColor="#8FE9FF" /><stop offset="1" stopColor="#B9AFFF" /></linearGradient></defs>
        </svg>
      </span>
      {live && <span className="absolute bottom-0 end-0 size-3 rounded-full bg-[#2dd4a7] ring-2 ring-[#0b0f1a]" />}
    </span>
  );
}

function Typing() {
  return (
    <div className="flex items-end gap-2">
      <Face size={28} />
      <div className="flex gap-1 rounded-2xl rounded-es-md bg-white/[0.06] px-4 py-3.5 shadow-[inset_0_0_0_1px_rgb(255_255_255/0.08)]">
        {[0, 1, 2].map((i) => (
          <motion.span key={i} className="block size-1.5 rounded-full bg-[#8FE9FF]"
            animate={{ y: [0, -4, 0], opacity: [0.4, 1, 0.4] }}
            transition={{ duration: 0.9, repeat: Infinity, delay: i * 0.15 }} />
        ))}
      </div>
    </div>
  );
}

function Chip({ children, onClick, href, tone = "ghost", external }) {
  const cls = "inline-flex max-w-full items-center gap-1.5 rounded-full px-3.5 py-2 text-[12.5px] font-bold no-underline " +
    "transition-all duration-200 hover:-translate-y-px cursor-pointer border-0 " +
    (tone === "go"
      ? "bg-[linear-gradient(100deg,#8FE9FF,#B9AFFF)] text-[#07090F] shadow-[0_6px_20px_-8px_rgb(143_233_255/0.7)]"
      : tone === "wa"
        ? "bg-[#25D366]/15 text-[#5BE38F] shadow-[inset_0_0_0_1px_rgb(37_211_102/0.4)] hover:bg-[#25D366]/25"
        : "bg-white/[0.05] text-[#dfe6f7] shadow-[inset_0_0_0_1px_rgb(255_255_255/0.12)] hover:bg-white/[0.1]");
  if (href) {
    return <a href={href} className={cls} {...(external ? { target: "_blank", rel: "noopener" } : {})}>
      <span className="truncate">{children}</span><IcArrow size={13} /></a>;
  }
  return <button type="button" onClick={onClick} className={cls}><span className="truncate">{children}</span></button>;
}

function Bubble({ m, onPick, onHandoff, last }) {
  if (m.me) {
    return (
      <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="flex justify-end">
        <div dir="auto" className="max-w-[82%] whitespace-pre-wrap break-words rounded-2xl rounded-ee-md px-4 py-2.5 text-[14px]
                        leading-relaxed text-[#07090F] bg-[linear-gradient(120deg,#8FE9FF,#B9AFFF)]">{m.text}</div>
      </motion.div>
    );
  }
  return (
    <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="flex items-end gap-2">
      <Face size={28} />
      <div className="min-w-0 max-w-[86%]">
        <div dir="auto" className={"whitespace-pre-wrap break-words rounded-2xl rounded-es-md px-4 py-3 text-[14px] leading-[1.75] " +
             (m.err ? "bg-red-400/10 text-red-200 shadow-[inset_0_0_0_1px_rgb(248_113_113/0.3)]"
                    : "bg-white/[0.06] text-[#e8edf9] shadow-[inset_0_0_0_1px_rgb(255_255_255/0.08)]")}>
          {m.text}
        </div>
        {(m.links?.length > 0 || m.wa) && (
          <div className="mt-2 flex flex-wrap gap-1.5">
            {(m.links || []).map((l) => <Chip key={l.k} href={l.url} tone="go">{l.label}</Chip>)}
            {m.wa && <Chip href={m.wa} tone="wa" external>{bi("افتح واتساب", "Open WhatsApp")}</Chip>}
          </div>
        )}
        {last && m.handoff && !m.handed && (
          <div className="mt-2"><Chip onClick={onHandoff}><IcHuman size={14} />{bi("كلّم فريق الدعم", "Talk to support")}</Chip></div>
        )}
        {last && m.suggestions?.length > 0 && (
          <div className="mt-2 flex flex-wrap gap-1.5">
            {m.suggestions.map((s) => <Chip key={s} onClick={() => onPick(s)}>{s}</Chip>)}
          </div>
        )}
      </div>
    </motion.div>
  );
}

function Welcome({ onPick }) {
  const signed = !!(BY.user && BY.user.name) || !!(BY.auth && BY.auth.in);
  const name = (BY.user && BY.user.name) || (BY.auth && BY.auth.name) || "";
  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-end gap-2">
        <Face size={28} />
        <div dir="auto" className="max-w-[86%] rounded-2xl rounded-es-md bg-white/[0.06] px-4 py-3 text-[14px] leading-[1.75]
                        text-[#e8edf9] shadow-[inset_0_0_0_1px_rgb(255_255_255/0.08)]">
          {signed
            ? bi(`أهلاً ${name} 👋 أنا مساعد BotYalla الذكي. اسألني عن أي حاجة في المنصة وأنا أشرحهالك خطوة بخطوة.`,
                 `Hi ${name} 👋 I'm BotYalla's AI assistant. Ask me anything about the platform and I'll walk you through it.`)
            : bi("أهلاً بيك 👋 أنا مساعد BotYalla الذكي. أقدر أشرحلك المنصة، أرشّحلك الباقة المناسبة، وأساعدك تبدأ في دقيقة.",
                 "Welcome 👋 I'm BotYalla's AI assistant. I can explain the platform, suggest the right plan and help you start in a minute.")}
        </div>
      </div>
      {BOOT?.tips?.length > 0 && (
        <div className="rounded-2xl bg-[linear-gradient(135deg,rgb(124_108_246/0.16),rgb(34_211_238/0.06))] p-4
                        shadow-[inset_0_0_0_1px_rgb(124_108_246/0.28)]">
          <div className="mb-2 flex items-center gap-2 text-[12px] font-extrabold uppercase tracking-wider text-[#B9AFFF]">
            <IcBulb size={15} />{bi("دليل الصفحة", "Page guide")} · <span className="normal-case text-[#dfe6f7]">{BOOT.title}</span>
          </div>
          <ul className="m-0 flex list-none flex-col gap-1.5 p-0">
            {BOOT.tips.map((t, i) => (
              <li key={i} dir="auto" className="flex gap-2 text-[13px] leading-relaxed text-[#c9d3ea]">
                <span className="mt-2 block size-1.5 shrink-0 rounded-full bg-[#8FE9FF]" />{t}
              </li>
            ))}
          </ul>
        </div>
      )}
      <div>
        <div className="mb-2 text-[12px] font-bold text-[#7b87a8]">{bi("أسئلة سريعة", "Quick questions")}</div>
        <div className="flex flex-wrap gap-1.5">
          {(BOOT?.starters || []).map((s) => <Chip key={s} onClick={() => onPick(s)}>{s}</Chip>)}
        </div>
      </div>
    </div>
  );
}

export default function Assistant() {
  const [open, setOpen] = useState(false);
  const [msgs, setMsgs] = useState(load);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [teaser, setTeaser] = useState(false);
  const scroller = useRef(null);
  const input = useRef(null);

  useEffect(() => { save(msgs); }, [msgs]);
  useEffect(() => {
    const el = scroller.current;
    if (el) el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
  }, [msgs, busy, open]);
  useEffect(() => {
    if (!open) return undefined;
    setTeaser(false);
    const id = setTimeout(() => input.current?.focus(), 250);
    const esc = (e) => { if (e.key === "Escape") setOpen(false); };
    document.addEventListener("keydown", esc);
    return () => { clearTimeout(id); document.removeEventListener("keydown", esc); };
  }, [open]);
  /* تلميح لطيف مرة واحدة لكل صفحة — لا يتكرر بعد إغلاقه */
  useEffect(() => {
    let seen = true;
    try { seen = localStorage.getItem(KEY + ":t:" + BOOT?.view) === "1"; } catch { /* */ }
    if (seen || load().length) return undefined;
    const id = setTimeout(() => setTeaser(true), 7000);
    return () => clearTimeout(id);
  }, []);
  const hideTeaser = () => {
    setTeaser(false);
    try { localStorage.setItem(KEY + ":t:" + BOOT?.view, "1"); } catch { /* */ }
  };

  if (!BOOT) return null;

  const send = async (q) => {
    const body = (q ?? text).trim();
    if (!body || busy) return;
    setText("");
    const history = msgs.filter((m) => !m.err).map((m) => ({ role: m.me ? "user" : "bot", text: m.text }));
    setMsgs((l) => [...l, { me: true, text: body }]);
    setBusy(true);
    const r = await post(BOOT.api, { text: body, history, view: BOOT.view });
    setBusy(false);
    setMsgs((l) => [...l, r.ok
      ? { text: r.reply, links: r.links, suggestions: r.suggestions, handoff: r.handoff || false }
      : { text: r.error || bi("حصلت مشكلة — جرّب تاني.", "Something went wrong — try again."), err: true }]);
  };

  const handoff = async () => {
    setBusy(true);
    const history = msgs.filter((m) => !m.err).map((m) => ({ role: m.me ? "user" : "bot", text: m.text }));
    const r = await post(BOOT.handoff, { history, view: BOOT.view });
    setBusy(false);
    setMsgs((l) => [...l.map((m) => ({ ...m, handed: true })), r.ok
      ? { text: r.msg, wa: r.kind === "whatsapp" && /^https:\/\/wa\.me\//.test(r.url || "") ? r.url : null,
          links: r.kind === "ticket" ? [{ k: "support", label: bi("افتح التذكرة", "Open the ticket"), url: r.url }] : [] }
      : { text: r.error, err: true }]);
  };

  const reset = () => { setMsgs([]); setText(""); };
  const last = msgs.length - 1;

  return (
    <div dir={AR ? "rtl" : "ltr"} className="font-[inherit]">
      {/* التلميح */}
      <AnimatePresence>
        {teaser && !open && (
          <motion.div initial={{ opacity: 0, y: 10, scale: 0.95 }} animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 6, scale: 0.97 }}
            className="fixed bottom-[92px] end-5 z-[340] w-[250px] rounded-2xl bg-[#0b0f1a]/95 p-3.5 pe-8 text-[13px] leading-relaxed
                       text-[#dfe6f7] shadow-[0_18px_50px_-12px_rgb(0_0_0/0.7),inset_0_0_0_1px_rgb(143_233_255/0.25)] backdrop-blur-xl">
            <button type="button" onClick={hideTeaser} aria-label={bi("إغلاق", "Close")}
              className="absolute end-2 top-2 grid size-6 cursor-pointer place-items-center rounded-full border-0 bg-transparent text-[#7b87a8] hover:text-white">
              <IcClose size={14} />
            </button>
            <button type="button" onClick={() => { hideTeaser(); setOpen(true); }}
              className="cursor-pointer border-0 bg-transparent p-0 text-start text-inherit">
              <b className="text-white">{bi("محتاج مساعدة؟", "Need a hand?")}</b><br />
              {bi(`اسألني عن «${BOOT.title}» وأنا أشرحلك خطوة بخطوة.`, `Ask me about “${BOOT.title}” — I'll walk you through it.`)}
            </button>
          </motion.div>
        )}
      </AnimatePresence>

      {/* زر الفتح */}
      <AnimatePresence>
        {!open && (
          <motion.button type="button" onClick={() => setOpen(true)}
            initial={{ scale: 0, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} exit={{ scale: 0, opacity: 0 }}
            whileHover={{ scale: 1.06 }} whileTap={{ scale: 0.94 }}
            transition={{ type: "spring", stiffness: 420, damping: 24 }}
            aria-label={bi("افتح مساعد BotYalla", "Open BotYalla assistant")}
            className="group fixed bottom-5 end-5 z-[340] grid size-[62px] cursor-pointer place-items-center rounded-full border-0 p-0
                       bg-transparent shadow-[0_14px_40px_-10px_rgb(124_108_246/0.85)]">
            <motion.span aria-hidden="true" className="absolute inset-0 rounded-full"
              style={{ background: "conic-gradient(from 0deg, #7c6cf6, #22d3ee, #2dd4a7, #7c6cf6)" }}
              animate={{ rotate: 360 }} transition={{ duration: 6, repeat: Infinity, ease: "linear" }} />
            <motion.span aria-hidden="true" className="absolute -inset-1 rounded-full bg-[#22d3ee]/25 blur-md"
              animate={{ opacity: [0.35, 0.8, 0.35] }} transition={{ duration: 2.6, repeat: Infinity }} />
            <span className="relative"><Face size={56} live /></span>
          </motion.button>
        )}
      </AnimatePresence>

      {/* اللوحة */}
      <AnimatePresence>
        {open && (
          <>
            <motion.div key="scrim" onClick={() => setOpen(false)} initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
              className="fixed inset-0 z-[345] bg-black/50 backdrop-blur-[2px] sm:hidden" />
            <motion.section key="panel" role="dialog" aria-modal="true" aria-label={bi("مساعد BotYalla", "BotYalla assistant")}
              initial={{ opacity: 0, y: 24, scale: 0.96 }} animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: 18, scale: 0.97 }} transition={{ type: "spring", stiffness: 380, damping: 32 }}
              style={{ transformOrigin: AR ? "bottom left" : "bottom right" }}
              className="fixed inset-x-0 bottom-0 z-[350] flex h-[88dvh] flex-col overflow-hidden rounded-t-[26px]
                         bg-[#080b14]/[0.97] text-[#f2f5fc] backdrop-blur-2xl
                         shadow-[0_30px_90px_-20px_rgb(0_0_0/0.85),inset_0_0_0_1px_rgb(255_255_255/0.09)]
                         sm:inset-x-auto sm:bottom-5 sm:end-5 sm:h-[min(640px,calc(100dvh-40px))] sm:w-[400px] sm:rounded-[26px]">
              {/* وهج علوي */}
              <div aria-hidden="true" className="pointer-events-none absolute -top-24 start-1/2 h-48 w-[130%] -translate-x-1/2 rounded-full
                                                  bg-[radial-gradient(closest-side,rgb(124_108_246/0.35),transparent)] rtl:translate-x-1/2" />
              <header className="relative flex items-center gap-3 px-4 pb-3 pt-4 shadow-[inset_0_-1px_0_rgb(255_255_255/0.07)]">
                <Face size={42} live />
                <div className="min-w-0 flex-1">
                  <div className="truncate text-[15.5px] font-extrabold tracking-tight">{bi("مساعد BotYalla", "BotYalla Assistant")}</div>
                  <div className="flex items-center gap-1.5 text-[11.5px] text-[#7b87a8]">
                    <span className="block size-1.5 rounded-full bg-[#2dd4a7]" />
                    {bi("ذكاء اصطناعي · بيرد فوراً · 24/7", "AI · instant replies · 24/7")}
                  </div>
                </div>
                {msgs.length > 0 && (
                  <button type="button" onClick={reset} title={bi("محادثة جديدة", "New chat")} aria-label={bi("محادثة جديدة", "New chat")}
                    className="grid size-9 cursor-pointer place-items-center rounded-xl border-0 bg-transparent text-[#aeb9d4] hover:bg-white/[0.07] hover:text-white">
                    <IcReset size={17} />
                  </button>
                )}
                <button type="button" onClick={() => setOpen(false)} aria-label={bi("إغلاق", "Close")}
                  className="grid size-9 cursor-pointer place-items-center rounded-xl border-0 bg-transparent text-[#aeb9d4] hover:bg-white/[0.07] hover:text-white">
                  <IcClose size={18} />
                </button>
              </header>

              <div ref={scroller} className="relative flex-1 overflow-y-auto overscroll-contain px-4 py-4" aria-live="polite">
                <div className="flex flex-col gap-3.5">
                  {msgs.length === 0 ? <Welcome onPick={send} /> : msgs.map((m, i) => (
                    <Bubble key={i} m={m} last={i === last && !busy} onPick={send} onHandoff={handoff} />
                  ))}
                  {busy && <Typing />}
                </div>
              </div>

              <form onSubmit={(e) => { e.preventDefault(); send(); }}
                className="relative px-3 pb-3 pt-2 shadow-[inset_0_1px_0_rgb(255_255_255/0.07)]">
                <div className="flex items-end gap-2 rounded-2xl bg-white/[0.05] p-1.5 ps-3.5 shadow-[inset_0_0_0_1px_rgb(255_255_255/0.1)]
                                focus-within:shadow-[inset_0_0_0_1px_rgb(143_233_255/0.5)]">
                  <textarea ref={input} value={text} rows={1} maxLength={1200} dir="auto"
                    onChange={(e) => { setText(e.target.value); e.target.style.height = "auto"; e.target.style.height = Math.min(e.target.scrollHeight, 120) + "px"; }}
                    onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); send(); } }}
                    placeholder={bi("اكتب سؤالك…", "Ask anything…")} aria-label={bi("سؤالك", "Your question")}
                    className="max-h-[120px] min-h-[40px] flex-1 resize-none border-0 bg-transparent py-2.5 text-[14px] leading-relaxed
                               text-white outline-none placeholder:text-[#5c6683] focus:outline-none" />
                  <button type="submit" disabled={busy || !text.trim()} aria-label={bi("إرسال", "Send")}
                    className="grid size-10 shrink-0 cursor-pointer place-items-center rounded-xl border-0 text-[#07090F]
                               bg-[linear-gradient(120deg,#8FE9FF,#B9AFFF)] transition-opacity disabled:cursor-default disabled:opacity-35">
                    <IcSend size={17} className={AR ? "-scale-x-100" : ""} />
                  </button>
                </div>
                <div className="mt-2 flex items-center justify-between gap-2 px-1 text-[10.5px] text-[#5c6683]">
                  <span>{bi("متبعتش كلمات سر أو أكواد هنا.", "Never share passwords or codes here.")}</span>
                  <button type="button" onClick={handoff} disabled={busy}
                    className="inline-flex cursor-pointer items-center gap-1 border-0 bg-transparent p-0 text-[11px] font-bold text-[#8FE9FF] hover:underline">
                    <IcHuman size={12} />{bi("كلّم إنسان", "Talk to a human")}
                  </button>
                </div>
              </form>
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
