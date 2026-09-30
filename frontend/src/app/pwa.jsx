/* تطبيق الهاتف (PWA) + الإشعارات الفورية — AGENTS §75.
   - تسجيل عامل الخدمة (/sw.js) ومزامنة اشتراك هذا الجهاز مع الخادم.
   - «ثبّت التطبيق»: لوحة سفلية جذابة — زرّ تثبيت حقيقي على أندرويد/كروم/إيدج، وخطوات مصوّرة
     على آيفون (سفاري لا يملك نافذة تثبيت برمجية).
   - «فعّل التنبيهات»: طلب إذن ليّن بمعاينة إشعار متحركة — إذن المتصفح لا يُطلب أبداً عند
     التحميل (يُرفض تلقائياً ويُحرق للأبد)، فقط بضغطة المستخدم.
   - تنبيه داخل التطبيق حين يصل إشعار والصفحة أمامه: بطاقة منزلقة + نغمة + اهتزاز.
   لوحة واحدة فقط في المرة، وكلٌّ منهما تُؤجَّل أياماً عند «لاحقاً». */
import { useEffect, useRef, useState } from "react";
import { motion, AnimatePresence } from "motion/react";
import { BY, bi, Icon } from "./kit.jsx";

const LS = {
  get(k) { try { return localStorage.getItem(k); } catch { return null; } },
  set(k, v) { try { localStorage.setItem(k, v); } catch { /* وضع خاص */ } },
};
export const standalone = () => { try { return matchMedia("(display-mode: standalone)").matches || navigator.standalone === true; } catch { return false; } };
export const isIOS = () => /iPhone|iPad|iPod/.test(navigator.userAgent) || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
const isPhone = () => /Android|iPhone|iPad|iPod/.test(navigator.userAgent) || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
export const pushSupported = () => "serviceWorker" in navigator && "PushManager" in window && "Notification" in window;
const snoozed = (k, days) => { const t = Number(LS.get(k) || 0); return !!t && Date.now() - t < days * 864e5; };

/* ─────────────── حدث التثبيت (يصل مبكراً — يُلتقط عند تحميل الوحدة) ─────────────── */
let deferred = null;
const subs = new Set();
const emit = () => subs.forEach((f) => f());
if (typeof window !== "undefined") {
  window.addEventListener("beforeinstallprompt", (e) => { e.preventDefault(); deferred = e; emit(); });
  window.addEventListener("appinstalled", () => { deferred = null; LS.set("by:installed", String(Date.now())); emit(); });
}
function useTick() { const [, s] = useState(0); useEffect(() => { const f = () => s((n) => n + 1); subs.add(f); return () => subs.delete(f); }, []); }

/* ─────────────── عامل الخدمة والاشتراك ─────────────── */
let regP = null;
export function swReady() {
  if (!("serviceWorker" in navigator)) return Promise.resolve(null);
  if (!regP) regP = navigator.serviceWorker.register("/sw.js", { scope: "/" }).catch(() => null);
  return regP;
}
async function post(url, body) {
  try {
    const r = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json", "X-CSRF-Token": BY.csrf }, body: JSON.stringify(body || {}) });
    return await r.json();
  } catch { return { ok: false }; }
}
const keyBytes = (b64) => {
  const s = atob(b64.replace(/-/g, "+").replace(/_/g, "/") + "===".slice((b64.length + 3) % 4));
  return Uint8Array.from(s, (c) => c.charCodeAt(0));
};
const sameKey = (a, b) => { if (!a || !b) return false; const x = new Uint8Array(a); if (x.length !== b.length) return false; return x.every((v, i) => v === b[i]); };

async function subscribe(reg) {
  const k = await (await fetch("/api/push/key", { headers: { Accept: "application/json" } })).json();
  if (!k.ok) return false;
  const key = keyBytes(k.key);
  let sub = await reg.pushManager.getSubscription();
  if (sub && !sameKey(sub.options && sub.options.applicationServerKey, key)) { await sub.unsubscribe(); sub = null; }
  if (!sub) sub = await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: key });
  const j = sub.toJSON();
  return !!(await post("/api/push/subscribe", { endpoint: j.endpoint, keys: j.keys })).ok;
}

/** بضغطة المستخدم فقط ⇒ "granted" | "denied" | "default" | "unsupported" | "error" */
export async function enablePush() {
  if (!pushSupported()) return "unsupported";
  let perm = Notification.permission;
  if (perm !== "granted") perm = await Notification.requestPermission();
  if (perm !== "granted") return perm;
  try {
    const reg = await swReady();
    if (!reg) return "error";
    await navigator.serviceWorker.ready;
    return (await subscribe(await navigator.serviceWorker.ready)) ? "granted" : "error";
  } catch { return "error"; }
}
export async function disablePush() {
  try {
    const reg = await navigator.serviceWorker.getRegistration("/");
    const sub = reg && await reg.pushManager.getSubscription();
    if (sub) { await post("/api/push/unsubscribe", { endpoint: sub.endpoint }); await sub.unsubscribe(); }
  } catch { /* */ }
}
export async function pushState() {
  if (!pushSupported()) return isIOS() && !standalone() ? "ios-install" : "unsupported";
  if (Notification.permission === "denied") return "denied";
  if (Notification.permission !== "granted") return "off";
  try {
    const reg = await navigator.serviceWorker.getRegistration("/");
    return reg && await reg.pushManager.getSubscription() ? "on" : "off";
  } catch { return "off"; }
}

/* عند كل تحميل: التسجيل + مزامنة اشتراك موجود (قد يتجدد من المتصفح) مرة يومياً + تعليم
   الإشعار الذي فُتح منه التطبيق مقروءاً + عدّاد أيقونة التطبيق. */
let booted = false;
export function bootPwa() {
  if (booted || typeof window === "undefined") return;
  booted = true;
  const u = new URL(location.href);
  const n = u.searchParams.get("by_n");
  if (n && /^\d+$/.test(n)) {
    post("/api/notifications/read", { ids: [Number(n)] });
    u.searchParams.delete("by_n");
    history.replaceState(null, "", u);
  }
  if (u.searchParams.get("source") === "pwa") { u.searchParams.delete("source"); history.replaceState(null, "", u); }
  try { const c = (BY.ui && BY.ui.unread) || 0; if (navigator.setAppBadge) (c ? navigator.setAppBadge(c) : navigator.clearAppBadge()).catch(() => {}); } catch { /* */ }
  if (!("serviceWorker" in navigator) || !BY.ui) return;
  swReady().then(async (reg) => {
    if (!reg || !pushSupported() || Notification.permission !== "granted") return;
    // دخول جديد (الخروج حذف اشتراك الجهاز) أو مرة يومياً لتجديد يقوم به المتصفح
    if (BY.ui.push && snoozed("by:push:sync", 1)) return;
    try { if (await subscribe(await navigator.serviceWorker.ready)) LS.set("by:push:sync", String(Date.now())); } catch { /* */ }
  });
  navigator.serviceWorker.addEventListener("message", (e) => {
    const m = e.data || {};
    if (m.type === "by:push") { toast(m.d || {}); window.dispatchEvent(new CustomEvent("by:notif")); }
    if (m.type === "by:go" && typeof m.u === "string" && m.u.startsWith(location.origin)) location.href = m.u;
  });
}

/* ─────────────── تنبيه داخل التطبيق ─────────────── */
const KIND = {
  call: ["phone", "from-emerald-400 to-teal-500", true],
  attention: ["chat", "from-au-cyan to-au-violet", false],
  assigned: ["user", "from-au-violet to-fuchsia-500", false],
  mention: ["chat", "from-au-violet to-fuchsia-500", false],
  paid: ["card", "from-emerald-400 to-au-cyan", false],
  integ_failed: ["link", "from-rose-500 to-orange-400", false],
  ticket_new: ["help", "from-au-cyan to-sky-500", false],
  ticket_user: ["help", "from-au-cyan to-sky-500", false],
  ticket_reply: ["help", "from-au-cyan to-sky-500", false],
  test: ["bell", "from-au-violet to-au-cyan", false],
};
const toasts = new Set();
function toast(d) { toasts.forEach((f) => f(d)); }

let actx = null;
function chime(urgent) {
  try {
    actx = actx || new (window.AudioContext || window.webkitAudioContext)();
    if (actx.state === "suspended") actx.resume();
    const notes = urgent ? [784, 1047, 784, 1047] : [880, 1319];
    notes.forEach((f, i) => {
      const o = actx.createOscillator(), g = actx.createGain(), t0 = actx.currentTime + i * 0.16;
      o.type = "sine"; o.frequency.value = f;
      g.gain.setValueAtTime(0.0001, t0); g.gain.exponentialRampToValueAtTime(0.16, t0 + 0.02); g.gain.exponentialRampToValueAtTime(0.0001, t0 + 0.5);
      o.connect(g).connect(actx.destination); o.start(t0); o.stop(t0 + 0.55);
    });
  } catch { /* الصوت ممنوع قبل أول تفاعل — لا بأس */ }
  try { navigator.vibrate && navigator.vibrate(urgent ? [240, 90, 240, 90, 480] : [120, 60, 120]); } catch { /* */ }
}

function PushToasts() {
  const [list, setList] = useState([]);
  useEffect(() => {
    const f = (d) => {
      const id = `${d.id || 0}-${Date.now()}`;
      const urgent = !!d.ri || d.k === "call";
      setList((l) => [{ id, d, urgent }, ...l].slice(0, 3));
      chime(urgent);
      setTimeout(() => setList((l) => l.filter((x) => x.id !== id)), urgent ? 16000 : 8000);
    };
    toasts.add(f);
    return () => toasts.delete(f);
  }, []);
  const open = (x) => {
    const u = new URL(x.d.u || "/home", location.origin);
    if (u.origin !== location.origin) return;
    if (x.d.id) u.searchParams.set("by_n", String(x.d.id));
    location.href = u.pathname + u.search;
  };
  return (
    <div className="pointer-events-none fixed inset-x-0 z-[400] flex flex-col items-center gap-2.5 px-3"
         style={{ top: "calc(env(safe-area-inset-top) + 12px)" }} aria-live="assertive">
      <AnimatePresence initial={false}>
        {list.map((x) => {
          const [icon, grad] = KIND[x.d.k] || KIND.test;
          return (
            <motion.div key={x.id} layout
              initial={{ opacity: 0, y: -40, scale: 0.92 }} animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: -24, scale: 0.95, transition: { duration: 0.2 } }}
              transition={{ type: "spring", stiffness: 420, damping: 30 }}
              drag="y" dragConstraints={{ top: 0, bottom: 0 }} dragElastic={0.4}
              onDragEnd={(_, i) => { if (i.offset.y < -40) setList((l) => l.filter((y) => y.id !== x.id)); }}
              role="alert"
              className="pointer-events-auto relative w-full max-w-[440px] overflow-hidden rounded-[22px] p-[1.5px]
                         shadow-[0_18px_50px_-12px_rgb(0_0_0/0.6),0_0_0_1px_rgb(var(--ov-rgb)/0.06)]">
              <span className={`absolute inset-0 bg-gradient-to-r ${grad} opacity-80`} aria-hidden="true" />
              <div className="relative flex items-start gap-3 rounded-[21px] bg-[rgb(var(--menu-rgb)/0.95)] p-3.5 backdrop-blur-xl">
                <button type="button" onClick={() => open(x)} className="flex min-w-0 flex-1 cursor-pointer items-start gap-3 border-0 bg-transparent p-0 text-start">
                  <span className="relative mt-0.5 grid size-11 shrink-0 place-items-center">
                    {x.urgent && <span className={`absolute inset-0 animate-ping rounded-2xl bg-gradient-to-br ${grad} opacity-40`} />}
                    <span className={`relative grid size-11 place-items-center rounded-2xl bg-gradient-to-br ${grad} text-white shadow-lg`}>
                      <Icon name={icon} size={20} />
                    </span>
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="flex items-center gap-2">
                      <b className="truncate text-[14px] text-ink" dir="auto">{x.d.t}</b>
                      <span className="ms-auto shrink-0 text-[11px] text-ink-3">{bi("الآن", "now")}</span>
                    </span>
                    {x.d.b && <span className="mt-0.5 line-clamp-2 block whitespace-pre-line text-[12.5px] leading-relaxed text-ink-2" dir="auto">{x.d.b}</span>}
                    <span className="mt-1.5 inline-flex items-center gap-1 text-[11.5px] font-bold text-au-cyan">{bi("اضغط للفتح", "Tap to open")} ›</span>
                  </span>
                </button>
                <button type="button" onClick={() => setList((l) => l.filter((y) => y.id !== x.id))} aria-label={bi("إغلاق", "Close")}
                        className="grid size-7 shrink-0 cursor-pointer place-items-center rounded-full border-0 bg-ov/[0.06] text-ink-3 hover:text-ink">
                  <Icon name="close" size={13} />
                </button>
                <motion.span className={`absolute bottom-0 start-0 h-[3px] bg-gradient-to-r ${grad}`}
                             initial={{ width: "100%" }} animate={{ width: "0%" }}
                             transition={{ duration: x.urgent ? 16 : 8, ease: "linear" }} />
              </div>
            </motion.div>
          );
        })}
      </AnimatePresence>
    </div>
  );
}

/* ─────────────── لوحة سفلية مشتركة ─────────────── */
function Sheet({ open, onClose, children, label }) {
  useEffect(() => {
    if (!open) return undefined;
    const esc = (e) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("keydown", esc);
    return () => document.removeEventListener("keydown", esc);
  }, [open, onClose]);
  return (
    <AnimatePresence>
      {open && (
        <>
          <motion.div key="scrim" className="fixed inset-0 z-[410] bg-sink/55 backdrop-blur-[3px]"
                      initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={onClose} />
          <motion.div key="sheet" role="dialog" aria-modal="true" aria-label={label}
            initial={{ y: "105%" }} animate={{ y: 0 }} exit={{ y: "105%" }}
            transition={{ type: "spring", stiffness: 360, damping: 36 }}
            drag="y" dragConstraints={{ top: 0, bottom: 0 }} dragElastic={{ top: 0, bottom: 0.6 }}
            onDragEnd={(_, i) => { if (i.offset.y > 90 || i.velocity.y > 600) onClose(); }}
            className="fixed inset-x-0 bottom-0 z-[420] mx-auto w-full max-w-[480px] overflow-hidden rounded-t-[30px]
                       bg-[rgb(var(--menu-rgb))] shadow-[0_-20px_60px_-10px_rgb(0_0_0/0.6)] ring-1 ring-ov/10
                       sm:bottom-6 sm:rounded-[30px]"
            style={{ paddingBottom: "calc(env(safe-area-inset-bottom) + 18px)" }}>
            <div aria-hidden="true" className="pointer-events-none absolute inset-x-0 top-0 h-48
                 bg-[radial-gradient(420px_200px_at_50%_-20%,rgb(124_108_246/0.35),transparent_70%)]" />
            <div className="relative mx-auto mt-2.5 mb-1 h-1.5 w-11 rounded-full bg-ov/20" />
            <div className="relative px-6 pt-3">{children}</div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}

const Benefit = ({ icon, title, text }) => (
  <li className="flex items-start gap-3">
    <span className="grid size-9 shrink-0 place-items-center rounded-xl bg-ov/[0.06] text-au-cyan"><Icon name={icon} size={17} /></span>
    <span><b className="block text-[13.5px] text-ink">{title}</b><span className="text-[12.5px] leading-relaxed text-ink-3">{text}</span></span>
  </li>
);
const ShareGlyph = () => (
  <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M12 15V3M8 7l4-4 4 4" /><path d="M6 11H5a2 2 0 0 0-2 2v6a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-6a2 2 0 0 0-2-2h-1" />
  </svg>
);
const AddGlyph = () => (
  <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" aria-hidden="true">
    <rect x="3.5" y="3.5" width="17" height="17" rx="4" /><path d="M12 8v8M8 12h8" />
  </svg>
);
const primary = "flex h-[52px] w-full cursor-pointer items-center justify-center gap-2 rounded-2xl border-0 text-[15.5px] font-extrabold text-[#0B1020] " +
  "bg-[linear-gradient(100deg,#8FE9FF,#B3A6FF)] shadow-[0_12px_30px_-8px_rgb(143_233_255/0.5)] active:scale-[0.98] transition-transform";
const ghost = "mt-2 flex h-11 w-full cursor-pointer items-center justify-center rounded-2xl border-0 bg-transparent text-[14px] font-bold text-ink-3 hover:text-ink";

function InstallSheet({ open, onClose, onInstalled }) {
  useTick();
  const ios = isIOS();
  const install = async () => {
    if (!deferred) return;
    deferred.prompt();
    const r = await deferred.userChoice.catch(() => ({}));
    deferred = null;
    if (r && r.outcome === "accepted") onInstalled(); else onClose();
  };
  return (
    <Sheet open={open} onClose={onClose} label={bi("تثبيت التطبيق", "Install the app")}>
      <div className="flex flex-col items-center text-center">
        <motion.div className="relative mb-4" initial={{ scale: 0.6, rotate: -8 }} animate={{ scale: 1, rotate: 0 }}
                    transition={{ type: "spring", stiffness: 300, damping: 16, delay: 0.1 }}>
          <span className="absolute -inset-3 rounded-[30px] bg-[conic-gradient(from_90deg,#7c6cf6,#22d3ee,#2dd4a7,#7c6cf6)] opacity-40 blur-xl" />
          <img src="/static/brand/icon-192.png" alt="" className="relative size-[76px] rounded-[22px] shadow-2xl" />
        </motion.div>
        <h2 className="m-0 text-[21px] font-extrabold text-ink">{bi("ثبّت BotYalla على هاتفك", "Install BotYalla on your phone")}</h2>
        <p className="mt-1.5 mb-5 text-[13.5px] leading-relaxed text-ink-3">
          {bi("افتحه بلمسة من الشاشة الرئيسية — كتطبيق حقيقي، بلا متجر ولا تحميل.", "Open it with one tap from your home screen — a real app, no store, no download.")}
        </p>
      </div>
      {ios && !deferred ? (
        <ol className="m-0 mb-5 flex list-none flex-col gap-3 p-0">
          {[[<ShareGlyph key="s" />, bi("اضغط زر المشاركة", "Tap the Share button"), bi("في شريط سفاري بالأسفل (أو أعلى الشاشة على آيباد)", "In Safari's bottom bar (top on iPad)")],
            [<AddGlyph key="a" />, bi("اختر «إضافة إلى الشاشة الرئيسية»", "Choose “Add to Home Screen”"), bi("مرّر القائمة للأسفل إن لم تجده", "Scroll the menu down if you don't see it")],
            [<Icon key="c" name="check" size={17} />, bi("اضغط «إضافة»", "Tap “Add”"), bi("وستجد BotYalla بجانب تطبيقاتك", "BotYalla will sit next to your apps")]].map(([g, a, b], i) => (
            <li key={i} className="flex items-center gap-3 rounded-2xl bg-ov/[0.04] p-3 shadow-[inset_0_0_0_1px_rgb(var(--ov-rgb)/0.06)]">
              <span className="tnum grid size-7 shrink-0 place-items-center rounded-full bg-au-violet/25 text-[12px] font-extrabold text-ink">{i + 1}</span>
              <span className="grid size-9 shrink-0 place-items-center rounded-xl bg-[#0A84FF]/15 text-[#4DA3FF]">{g}</span>
              <span className="min-w-0 text-start"><b className="block text-[13.5px] text-ink">{a}</b><span className="text-[12px] text-ink-3">{b}</span></span>
            </li>
          ))}
        </ol>
      ) : !deferred ? (
        /* متصفح بلا نافذة تثبيت برمجية (فايرفوكس · سامسونج أحياناً · تثبيت سابق رُفض): الخطوات يدوياً */
        <ol className="m-0 mb-5 flex list-none flex-col gap-3 p-0">
          {[["more", bi("افتح قائمة المتصفح", "Open the browser menu"), bi("النقاط الثلاث ⋮ أعلى الشاشة أو أسفلها", "The three dots ⋮ at the top or bottom")],
            ["download", bi("اختر «تثبيت التطبيق»", "Choose “Install app”"), bi("أو «إضافة إلى الشاشة الرئيسية»", "or “Add to Home screen”")],
            ["check", bi("أكّد الإضافة", "Confirm"), bi("وستجد BotYalla بجانب تطبيقاتك", "BotYalla will sit next to your apps")]].map(([ic, a, b], i) => (
            <li key={i} className="flex items-center gap-3 rounded-2xl bg-ov/[0.04] p-3 shadow-[inset_0_0_0_1px_rgb(var(--ov-rgb)/0.06)]">
              <span className="tnum grid size-7 shrink-0 place-items-center rounded-full bg-au-violet/25 text-[12px] font-extrabold text-ink">{i + 1}</span>
              <span className="grid size-9 shrink-0 place-items-center rounded-xl bg-au-cyan/15 text-au-cyan"><Icon name={ic} size={17} /></span>
              <span className="min-w-0 text-start"><b className="block text-[13.5px] text-ink">{a}</b><span className="text-[12px] text-ink-3">{b}</span></span>
            </li>
          ))}
        </ol>
      ) : (
        <ul className="m-0 mb-6 flex list-none flex-col gap-3.5 p-0">
          <Benefit icon="bell" title={bi("تنبيهات فورية", "Instant alerts")} text={bi("كل عميل جديد ومكالمة ودفعة تصلك على الهاتف — حتى والتطبيق مغلق", "Every new customer, call and payment reaches your phone — even when closed")} />
          <Benefit icon="bolt" title={bi("أسرع وبملء الشاشة", "Faster, full screen")} text={bi("يفتح مباشرة بلا شريط المتصفح", "Opens straight in, no browser bar")} />
          <Benefit icon="shield" title={bi("خفيف وآمن", "Light and secure")} text={bi("أقل من 1 ميجا، ويتحدّث تلقائياً", "Under 1 MB, updates itself")} />
        </ul>
      )}
      {deferred ? <button type="button" className={primary} onClick={install}><Icon name="download" size={18} />{bi("تثبيت التطبيق", "Install app")}</button>
        : <button type="button" className={primary} onClick={onClose}>{bi("فهمت", "Got it")}</button>}
      <button type="button" className={ghost} onClick={onClose}>{bi("لاحقاً", "Later")}</button>
      {ios && !deferred && (
        <motion.div aria-hidden="true" className="pointer-events-none fixed bottom-1 left-1/2 z-[430] -translate-x-1/2 text-[#4DA3FF] sm:hidden"
                    animate={{ y: [0, 8, 0] }} transition={{ repeat: Infinity, duration: 1.3 }}>
          <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round"><path d="M12 4v15M6 13l6 6 6-6" /></svg>
        </motion.div>
      )}
    </Sheet>
  );
}

/* معاينة إشعار متحركة — «هكذا سيصلك» */
function NotifPreview() {
  const samples = [
    ["chat", "from-au-cyan to-au-violet", bi("🙋 عميل يحتاج مساعدتك", "🙋 A customer needs you"), bi("أحمد: أبغى أحجز غرفة لليلتين", "Ahmed: I'd like to book a room for 2 nights")],
    ["phone", "from-emerald-400 to-teal-500", bi("📞 مكالمة واتساب واردة", "📞 Incoming WhatsApp call"), bi("سارة تتصل الآن — اضغط للرد", "Sara is calling — tap to answer")],
    ["card", "from-emerald-400 to-au-cyan", bi("💳 دفعة جديدة وصلت", "💳 New payment received"), bi("1,250 ر.س · حجز جناح", "SAR 1,250 · Suite booking")],
  ];
  const [i, setI] = useState(0);
  useEffect(() => { const t = setInterval(() => setI((n) => (n + 1) % samples.length), 2600); return () => clearInterval(t); }, []);
  const [icon, grad, title, body] = samples[i];
  return (
    <div className="relative mx-auto mb-5 h-[92px] w-full max-w-[360px]">
      <AnimatePresence mode="popLayout">
        <motion.div key={i} initial={{ opacity: 0, y: -26, scale: 0.94 }} animate={{ opacity: 1, y: 0, scale: 1 }}
                    exit={{ opacity: 0, y: 18, scale: 0.94 }} transition={{ type: "spring", stiffness: 380, damping: 28 }}
                    className="absolute inset-x-0 top-0 flex items-center gap-3 rounded-[20px] bg-ov/[0.07] p-3 text-start backdrop-blur
                               shadow-[0_14px_40px_-12px_rgb(0_0_0/0.6),inset_0_0_0_1px_rgb(var(--ov-rgb)/0.1)]">
          <span className={`grid size-11 shrink-0 place-items-center rounded-2xl bg-gradient-to-br ${grad} text-white`}><Icon name={icon} size={20} /></span>
          <span className="min-w-0 flex-1">
            <span className="flex items-center gap-2"><b className="truncate text-[13.5px] text-ink">{title}</b>
              <span className="ms-auto text-[10.5px] text-ink-3">BotYalla · {bi("الآن", "now")}</span></span>
            <span className="block truncate text-[12.5px] text-ink-2">{body}</span>
          </span>
        </motion.div>
      </AnimatePresence>
    </div>
  );
}

function PushSheet({ open, onClose }) {
  const [state, setState] = useState("ask");       // ask | busy | on | denied | error
  const go = async () => {
    setState("busy");
    const r = await enablePush();
    if (r === "granted") { setState("on"); post("/api/push/test"); setTimeout(onClose, 2600); }
    else if (r === "denied") setState("denied");
    else if (r === "default") onClose();
    else setState("error");
  };
  return (
    <Sheet open={open} onClose={onClose} label={bi("تفعيل التنبيهات", "Enable notifications")}>
      {state === "on" ? (
        <div className="flex flex-col items-center py-4 text-center">
          <motion.span initial={{ scale: 0 }} animate={{ scale: 1 }} transition={{ type: "spring", stiffness: 300, damping: 14 }}
                       className="mb-4 grid size-20 place-items-center rounded-full bg-[linear-gradient(135deg,#2dd4a7,#22d3ee)] text-[#04140E] shadow-[0_12px_40px_-8px_rgb(45_212_167/0.6)]">
            <Icon name="check" size={38} />
          </motion.span>
          <h2 className="m-0 text-[20px] font-extrabold text-ink">{bi("التنبيهات مفعّلة!", "Notifications are on!")}</h2>
          <p className="mt-1.5 mb-2 text-[13.5px] text-ink-3">{bi("أرسلنا لك تنبيه تجربة الآن 🎉", "We just sent you a test alert 🎉")}</p>
        </div>
      ) : state === "denied" ? (
        <div className="py-2 text-center">
          <h2 className="m-0 text-[19px] font-extrabold text-ink">{bi("التنبيهات محظورة في المتصفح", "Notifications are blocked")}</h2>
          <p className="mt-2 mb-5 text-[13.5px] leading-relaxed text-ink-3">
            {bi("افتح إعدادات الموقع (رمز القفل بجانب العنوان) ← الإشعارات ← سماح، ثم أعد تحميل الصفحة.",
                "Open site settings (the lock next to the address) → Notifications → Allow, then reload.")}
          </p>
          <button type="button" className={primary} onClick={onClose}>{bi("حسناً", "OK")}</button>
        </div>
      ) : (
        <>
          <div className="mb-1 flex justify-center">
            <motion.span className="relative grid size-16 place-items-center rounded-[20px] bg-[linear-gradient(135deg,#7c6cf6,#22d3ee)] text-white shadow-[0_14px_40px_-10px_rgb(124_108_246/0.7)]"
                         animate={{ rotate: [0, -14, 12, -8, 6, 0] }} transition={{ repeat: Infinity, repeatDelay: 1.6, duration: 0.9 }}>
              <Icon name="bell" size={30} />
              <span className="absolute -end-1 -top-1 grid size-5 place-items-center rounded-full bg-red-500 text-[11px] font-extrabold ring-2 ring-[rgb(var(--menu-rgb))]">3</span>
            </motion.span>
          </div>
          <h2 className="mt-3 mb-1.5 text-center text-[21px] font-extrabold text-ink">{bi("لا تفوّت أي عميل بعد اليوم", "Never miss a customer again")}</h2>
          <p className="mt-0 mb-5 text-center text-[13.5px] leading-relaxed text-ink-3">
            {bi("فعّل التنبيهات الفورية لتصلك كل رسالة ومكالمة ودفعة على هذا الجهاز — حتى والتطبيق مغلق.",
                "Turn on instant alerts so every message, call and payment reaches this device — even when the app is closed.")}
          </p>
          <NotifPreview />
          {state === "error" && <p className="mt-0 mb-3 text-center text-[12.5px] text-red-300">{bi("تعذّر التفعيل — حاول مرة أخرى.", "Couldn't enable — please try again.")}</p>}
          <button type="button" className={primary} onClick={go} disabled={state === "busy"}>
            <Icon name="bell" size={18} />{state === "busy" ? bi("لحظة…", "One moment…") : bi("فعّل التنبيهات", "Turn on alerts")}
          </button>
          <button type="button" className={ghost} onClick={onClose}>{bi("ليس الآن", "Not now")}</button>
        </>
      )}
    </Sheet>
  );
}

/* ─────────────── المنسّق: لوحة واحدة في المرة ─────────────── */
export function PwaLayer() {
  useTick();
  const [sheet, setSheet] = useState(null);           // null | "install" | "push"
  const shown = useRef(false);
  useEffect(() => { bootPwa(); }, []);
  useEffect(() => {
    const openInstall = () => setSheet("install");
    const openPush = () => setSheet("push");
    window.addEventListener("by:install", openInstall);
    window.addEventListener("by:push-ask", openPush);
    return () => { window.removeEventListener("by:install", openInstall); window.removeEventListener("by:push-ask", openPush); };
  }, []);
  useEffect(() => {
    if (shown.current || !BY.ui) return undefined;
    const pickSheet = () => {
      const inApp = standalone();
      const canInstall = !inApp && (deferred || (isIOS() && isPhone())) && !snoozed("by:install:later", 3);
      const canPush = pushSupported() && Notification.permission === "default" && !snoozed("by:push:later", 4)
        && (inApp || !isIOS());
      if (inApp && canPush) return "push";
      if (canInstall && isPhone()) return "install";
      if (canPush) return "push";
      if (canInstall) return "install";
      return null;
    };
    // لا فوق نافذة أخرى مفتوحة (جولة الترحيب · تأكيد · محرّر) — ننتظر حتى تُغلق
    let t;
    const attempt = (delay) => {
      t = setTimeout(() => {
        if (document.querySelector('[role="dialog"], [aria-modal="true"]')) { attempt(4000); return; }
        const s = pickSheet();
        if (s) { shown.current = true; setSheet(s); }
      }, delay);
    };
    attempt(3500);
    return () => clearTimeout(t);
  }, [deferred]);
  const close = (key) => () => { LS.set(key, String(Date.now())); setSheet(null); };
  return (
    <>
      <PushToasts />
      <InstallSheet open={sheet === "install"} onClose={close("by:install:later")}
                    onInstalled={() => setSheet(pushSupported() && Notification.permission === "default" ? "push" : null)} />
      <PushSheet open={sheet === "push"} onClose={close("by:push:later")} />
    </>
  );
}

/* ─────────────── مفتاح «تنبيهات هذا الجهاز» (في لوحة الجرس) ─────────────── */
export function PushToggle() {
  const [st, setSt] = useState("…");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  useEffect(() => { pushState().then(setSt); }, []);
  const flip = async () => {
    setBusy(true); setMsg("");
    if (st === "on") { await disablePush(); setSt("off"); }
    else {
      const r = await enablePush();
      setSt(r === "granted" ? "on" : r === "denied" ? "denied" : await pushState());
      if (r === "error") setMsg(bi("تعذّر التفعيل", "Couldn't enable"));
    }
    setBusy(false);
  };
  const test = async () => {
    const r = await post("/api/push/test");
    setMsg(r.ok ? (r.sent ? bi(`أُرسل لـ ${r.sent} جهاز ✓`, `Sent to ${r.sent} device(s) ✓`) : bi("لا أجهزة مفعّلة", "No devices on")) : bi("انتظر قليلاً ثم أعد", "Wait a bit and retry"));
  };
  if (st === "unsupported") return null;
  return (
    <div className="border-t border-ov/10 px-4 py-3">
      {st === "ios-install" ? (
        <button type="button" onClick={() => window.dispatchEvent(new CustomEvent("by:install"))}
                className="flex w-full cursor-pointer items-center gap-3 border-0 bg-transparent p-0 text-start">
          <span className="grid size-8 place-items-center rounded-xl bg-au-violet/20 text-au-cyan"><Icon name="download" size={15} /></span>
          <span className="flex-1 text-[12.5px] leading-relaxed text-ink-2">{bi("ثبّت التطبيق على الشاشة الرئيسية لتصلك التنبيهات على آيفون", "Add the app to your Home Screen to get alerts on iPhone")}</span>
        </button>
      ) : (
        <div className="flex items-center gap-3">
          <span className={`grid size-8 place-items-center rounded-xl ${st === "on" ? "bg-au-teal/15 text-au-teal" : "bg-ov/[0.06] text-ink-3"}`}><Icon name="bell" size={15} /></span>
          <span className="min-w-0 flex-1">
            <b className="block text-[12.5px] text-ink">{bi("تنبيهات فورية على هذا الجهاز", "Instant alerts on this device")}</b>
            <span className="text-[11.5px] text-ink-3">
              {msg || (st === "on" ? bi("مفعّلة — تصلك والتطبيق مغلق", "On — even when closed") : st === "denied" ? bi("محظورة من إعدادات المتصفح", "Blocked in browser settings") : bi("متوقفة", "Off"))}
            </span>
          </span>
          {st === "on" && <button type="button" onClick={test} className="cursor-pointer rounded-lg border-0 bg-ov/[0.06] px-2.5 py-1 text-[11.5px] font-bold text-ink-2 hover:text-ink">{bi("تجربة", "Test")}</button>}
          {st !== "denied" && (
            <button type="button" role="switch" aria-checked={st === "on"} disabled={busy} onClick={flip}
                    aria-label={bi("تنبيهات هذا الجهاز", "Alerts on this device")}
                    className={`relative h-6 w-11 shrink-0 cursor-pointer rounded-full border-0 transition-colors ${st === "on" ? "bg-au-teal" : "bg-ov/15"}`}>
              <span className={`absolute top-0.5 size-5 rounded-full bg-white shadow transition-all ${st === "on" ? "start-[22px]" : "start-0.5"}`} />
            </button>
          )}
        </div>
      )}
    </div>
  );
}
