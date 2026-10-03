import { useState, useEffect } from "react";
import { motion, AnimatePresence } from "motion/react";
import { BY, t, Icon, bi, Avatar, Logo } from "./kit.jsx";
import Backdrop from "../Backdrop.jsx";
import { SideNav, CommandPalette, prefs, savePrefs } from "./nav.jsx";
import Bell from "./bell.jsx";
import { PwaLayer, standalone } from "./pwa.jsx";

/* ============================================================================
   قشرة اللوحة: شريط جانبي ثابت + شريط علوي + درج للجوال + إشعارات.
   ========================================================================== */

/* مبدّل المظهر: يقلب <html data-theme> فوراً (لا انتظار للخادم) ثم يحفظ التفضيل.
   لو فشل الحفظ يعود كما كان — لا يبقى المستخدم على مظهر لن يجده في الصفحة التالية. */
function ThemeToggle() {
  const [theme, setTheme] = useState(() => document.documentElement.dataset.theme || "dark");
  const flip = async () => {
    const next = theme === "light" ? "dark" : "light";
    const apply = (v) => {
      document.documentElement.dataset.theme = v;
      document.querySelector('meta[name="theme-color"]')?.setAttribute("content", v === "light" ? "#F3F5FA" : "#05070D");
      setTheme(v);
    };
    apply(next);
    try {
      const r = await fetch("/account/theme", {
        method: "POST", headers: { "Content-Type": "application/json", "X-CSRF-Token": BY.csrf },
        body: JSON.stringify({ theme: next }),
      });
      if (!r.ok) apply(theme);
    } catch { apply(theme); }
  };
  const light = theme === "light";
  const label = light ? bi("المظهر الداكن", "Dark mode") : bi("المظهر الفاتح", "Light mode");
  return (
    <button type="button" onClick={flip} aria-label={label} title={label}
            className="grid size-10 shrink-0 cursor-pointer place-items-center rounded-full border-0 bg-transparent text-ink-2
                       shadow-[inset_0_0_0_1px_rgb(var(--ov-rgb)/0.1)] transition-colors hover:text-au-cyan">
      <Icon name={light ? "moon" : "sun"} size={17} />
    </button>
  );
}

function NavLink({ item, active }) {
  return (
    <a href={item.u}
       className={
         "relative flex items-center gap-3 rounded-xl px-3 py-2.5 text-[14px] font-bold no-underline " +
         "transition-colors duration-300 " +
         (active ? "text-ink" : "text-ink-2 hover:bg-ov/[0.06] hover:text-ink")
       }>
      {active && (
        <motion.span layoutId="nav-active"
          className="absolute inset-0 rounded-xl bg-[linear-gradient(100deg,rgb(124_108_246/0.28),rgb(34_211_238/0.12))]
                     shadow-[inset_0_0_0_1px_rgb(124_108_246/0.4)]"
          transition={{ type: "spring", stiffness: 400, damping: 34 }} />
      )}
      <Icon name={item.i} size={18} className={"relative " + (active ? "text-au-cyan" : "text-ink-3")} />
      <span className="relative truncate">{item.l}</span>
    </a>
  );
}

const SCALES = [90, 100, 110, 125];
/* حجم العرض لكل مستخدم (يُحفظ في حسابه) — تكبير الواجهة كلها لا الخط وحده، فلا تنكسر التخطيطات */
function applyScale(s) { document.documentElement.style.zoom = s && s !== 100 ? String(s / 100) : ""; }
function ScaleControl({ compact }) {
  const [s, setS] = useState(() => prefs().scale || 100);
  const step = (d) => { const i = Math.min(SCALES.length - 1, Math.max(0, SCALES.indexOf(s) + d)); const v = SCALES[i]; setS(v); applyScale(v); savePrefs({ scale: v }); };
  if (compact) return null;
  return (
    <div className="flex items-center gap-2 px-3 py-1.5 text-[12.5px] font-bold text-ink-3">
      <span className="flex-1">{bi("حجم العرض", "Display size")}</span>
      <button type="button" onClick={() => step(-1)} disabled={s === SCALES[0]} aria-label={bi("تصغير", "Smaller")}
              className="grid size-7 cursor-pointer place-items-center rounded-lg border-0 bg-ov/[0.06] text-ink-2 disabled:opacity-40">A−</button>
      <span className="tnum w-10 text-center text-ink-2">{s}%</span>
      <button type="button" onClick={() => step(1)} disabled={s === SCALES[SCALES.length - 1]} aria-label={bi("تكبير", "Larger")}
              className="grid size-7 cursor-pointer place-items-center rounded-lg border-0 bg-ov/[0.06] text-ink-2 disabled:opacity-40">A+</button>
    </div>
  );
}

function SideContent({ view, compact = false, onCompact, onPalette }) {
  const home = BY.navGroups?.length ? (BY.navGroups[0].items[0]?.u || BY.urls.dashboard) : BY.urls.dashboard;
  return (
    <>
      <a href={home} className={`mb-4 flex items-center gap-2.5 no-underline ${compact ? "justify-center" : "px-3"}`}>
        <Logo className={compact ? "h-8 w-auto" : "h-9 w-auto"} />
      </a>

      {BY.navGroups?.length ? <SideNav view={view} compact={compact} onPalette={onPalette} /> : <>
        <nav className="flex flex-col gap-1">
          {BY.nav.map((it) => <NavLink key={it.k} item={it} active={it.k === view} />)}
        </nav>
        {BY.adminNav.length > 0 && <nav className="mt-6 flex flex-col gap-1">{BY.adminNav.map((it) => <NavLink key={it.k} item={it} active={it.k === view} />)}</nav>}
      </>}

      <div className="mt-auto flex flex-col gap-1 pt-5 shadow-[inset_0_1px_0_rgb(var(--ov-rgb)/0.07)]">
        {/* على الهاتف: المظهر واللغة وتثبيت التطبيق هنا (الشريط العلوي مزدحم) */}
        {BY.ui && (
          <div className="flex items-center gap-2 px-2 pb-2 sm:hidden">
            <ThemeToggle />
            <a href={BY.urls.lang} className="inline-flex h-10 items-center gap-1.5 rounded-full px-3.5 text-[13px] font-bold text-ink-2 no-underline shadow-[inset_0_0_0_1px_rgb(var(--ov-rgb)/0.1)]">
              <Icon name="globe" size={15} />{BY.lang === "ar" ? "English" : "العربية"}
            </a>
            {!standalone() && <button type="button" onClick={() => window.dispatchEvent(new CustomEvent("by:install"))}
                    className="ms-auto inline-flex h-10 cursor-pointer items-center gap-1.5 rounded-full border-0 bg-au-violet/20 px-3.5 text-[12.5px] font-bold text-ink">
              <Icon name="download" size={14} />{bi("التطبيق", "App")}
            </button>}
          </div>
        )}
        {BY.ui && <ScaleControl compact={compact} />}
        {onCompact && (
          <button type="button" onClick={onCompact} title={compact ? bi("توسيع القائمة", "Expand menu") : bi("قائمة مضغوطة", "Compact menu")}
                  className={`flex cursor-pointer items-center gap-3 rounded-xl border-0 bg-transparent py-2 text-[13px] font-bold text-ink-3 hover:bg-ov/[0.06] hover:text-ink ${compact ? "justify-center" : "px-3"}`}>
            <span className="text-[15px]">{compact ? (BY.dir === "rtl" ? "«" : "»") : (BY.dir === "rtl" ? "»" : "«")}</span>
            {!compact && bi("قائمة مضغوطة", "Compact menu")}
          </button>
        )}
        <a href={BY.urls.account} title={compact ? BY.user.name : undefined}
           className={`flex items-center gap-3 rounded-xl py-2 no-underline transition-colors hover:bg-ov/[0.06] ${compact ? "justify-center" : "px-2.5"}`}>
          <Avatar src={BY.user.avatar} name={BY.user.name} size={compact ? 30 : 34} />
          {!compact && <span className="min-w-0 flex-1">
            <span className="block truncate text-[14px] font-bold text-ink" dir="auto">{BY.user.name}</span>
            <span className="block truncate text-[11.5px] text-ink-3">{t("account_title")}</span>
          </span>}
        </a>
        {/* الخروج POST مع CSRF: رابط GET كان يُخرج المستخدم من أي موقع بـ <img src=".../logout"> */}
        <form method="post" action={BY.urls.logout} className="m-0">
          <input type="hidden" name="csrf_token" value={BY.csrf} />
          <button type="submit" title={compact ? t("logout") : undefined}
                  className={`flex w-full cursor-pointer items-center gap-3 rounded-xl border-0 bg-transparent py-2.5
                             text-start text-[14px] font-bold text-ink-2 transition-colors hover:bg-ov/[0.06] hover:text-ink ${compact ? "justify-center" : "px-3"}`}>
            <Icon name="logout" size={18} className="text-ink-3" />
            {!compact && t("logout")}
          </button>
        </form>
      </div>
    </>
  );
}

/* إشعارات flash القادمة من Flask. مُصدَّرة لأن صفحات المصادقة بلا قشرة
   (BARE) تحتاجها أيضاً — بدونها لا يرى المستخدم «بيانات دخول غير صحيحة». */
export function Flashes() {
  const [list, setList] = useState(BY.flashes || []);
  useEffect(() => {
    if (!list.length) return;
    const id = setTimeout(() => setList((l) => l.slice(1)), 5000);
    return () => clearTimeout(id);
  }, [list]);
  if (!list.length) return null;
  return (
    <div className="pointer-events-none fixed inset-x-0 top-4 z-[300] flex flex-col items-center gap-2 px-4">
      <AnimatePresence>
        {list.map((f, i) => (
          <motion.div key={f.m + i}
            initial={{ opacity: 0, y: -16, scale: 0.96 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -10, scale: 0.96 }}
            transition={{ type: "spring", stiffness: 400, damping: 30 }}
            role="alert"
            className={
              "glass pointer-events-auto max-w-[min(560px,92vw)] rounded-2xl px-5 py-3.5 text-[14px] font-bold " +
              (f.c === "error" ? "text-red-200" : "text-au-teal")
            }>
            {f.m}
          </motion.div>
        ))}
      </AnimatePresence>
    </div>
  );
}

/* لافتة «أنت داخل حساب عميل بإذنه» — ظاهرة طول جلسة المساعدة ولا تُخفى */
function AssistBanner() {
  const a = BY.assist;
  if (!a) return null;
  const until = a.until ? new Date(a.until * 1000).toLocaleDateString(BY.lang === "en" ? "en-GB" : "ar-EG") : "";
  return (
    <div className="sticky top-0 z-[250] flex flex-wrap items-center justify-center gap-3 bg-[linear-gradient(90deg,#b45309,#d97706)]
                    px-4 py-2 text-[13px] font-bold text-white shadow-lg">
      <Icon name="users" size={16} />
      <span>{bi(`أنت شغال جوه حساب «${a.user}» بإذنه (لحد ${until}) — البوتات بس، وكل تعديل بيتسجّل ويشوفه العميل.`,
                `You're working inside “${a.user}”'s account with permission (until ${until}) — bots only; every change is logged for the customer.`)}</span>
      <form method="post" action={a.exit} className="m-0">
        <input type="hidden" name="csrf_token" value={BY.csrf} />
        <button type="submit" className="cursor-pointer rounded-full border-0 bg-white px-3.5 py-1 text-[12.5px] font-extrabold text-[#92400e]">
          {bi("خروج من الحساب", "Exit account")}
        </button>
      </form>
    </div>
  );
}

/* ============================================================ شريط التطبيق السفلي (الهاتف)
   مثل التطبيقات الأصلية: أهم 4 وجهات لنوع المستخدم + «المزيد» يفتح القائمة الكاملة. عائم
   فوق المحتوى بزجاج مموّه، ويحترم منطقة الإيماءات أسفل آيفون (safe-area). */
const TAB_KEYS = {
  staff: ["home", "admin_tickets", "admin_users", "admin_overview", "admin_convo"],
  user: ["home", "shared_inbox", "dashboard", "contacts", "broadcasts", "chat_payments"],
};
const TAB_SHORT = {
  home: ["الرئيسية", "Home"], shared_inbox: ["الوارد", "Inbox"], dashboard: ["البوتات", "Bots"], contacts: ["العملاء", "Contacts"],
  broadcasts: ["البث", "Broadcasts"], chat_payments: ["المدفوعات", "Payments"], admin_tickets: ["الدعم", "Support"],
  admin_users: ["المستخدمون", "Users"], admin_overview: ["الإدارة", "Admin"], admin_convo: ["المحادثات", "Chats"],
};
function tabItems() {
  const all = (BY.navGroups || []).flatMap((g) => g.items);
  const staff = ["admin", "support"].includes(BY.ui && BY.ui.persona);
  return TAB_KEYS[staff ? "staff" : "user"].map((k) => all.find((x) => x.k === k)).filter(Boolean).slice(0, 4);
}
function MobileTabBar({ view, onMore, moreOpen }) {
  const items = tabItems();
  const on = moreOpen ? "__more" : items.some((x) => x.k === view) ? view : "__more";
  const Tab = ({ k, icon, label, href, onClick }) => {
    const active = on === k;
    const inner = (
      <>
        <span className="relative grid h-8 w-12 place-items-center">
          {active && <motion.span layoutId="tab-active" transition={{ type: "spring", stiffness: 500, damping: 36 }}
                                  className="absolute inset-0 rounded-full bg-[linear-gradient(100deg,rgb(124_108_246/0.9),rgb(34_211_238/0.75))] shadow-[0_6px_18px_-6px_rgb(124_108_246/0.8)]" />}
          <Icon name={icon} size={20} className={`relative ${active ? "text-white" : "text-ink-3"}`} />
        </span>
        <span className={`max-w-full truncate text-[10.5px] font-bold ${active ? "text-ink" : "text-ink-3"}`}>{label}</span>
      </>
    );
    const cls = "flex min-w-0 flex-1 cursor-pointer flex-col items-center gap-0.5 border-0 bg-transparent py-1.5 no-underline active:scale-95 transition-transform";
    return href ? <a href={href} className={cls} aria-current={active ? "page" : undefined}>{inner}</a>
      : <button type="button" onClick={onClick} className={cls} aria-expanded={moreOpen}>{inner}</button>;
  };
  return (
    <nav aria-label={bi("التنقّل السريع", "Quick navigation")}
         className="fixed inset-x-2.5 z-[180] flex items-stretch rounded-[26px] bg-ob-1/80 px-1.5 backdrop-blur-2xl backdrop-saturate-150
                    shadow-[0_14px_40px_-10px_rgb(0_0_0/0.7),inset_0_0_0_1px_rgb(var(--ov-rgb)/0.09)] lg:hidden"
         style={{ bottom: "calc(env(safe-area-inset-bottom) + 8px)" }}>
      {items.map((x) => <Tab key={x.k} k={x.k} icon={x.i} label={(TAB_SHORT[x.k] || [x.l, x.l])[BY.lang === "en" ? 1 : 0]} href={x.u} />)}
      <Tab k="__more" icon="more" label={bi("المزيد", "More")} onClick={onMore} />
    </nav>
  );
}

/* صفحات تطبيقية تحتاج عرض الشاشة كله (أعمدة متجاورة) — باقي الصفحات تبقى بعرض القراءة */
const WIDE = new Set(["shared_inbox"]);

export default function AppShell({ view, children }) {
  const [mobileOpen, setMobileOpen] = useState(false);
  const [desktopClosed, setDesktopClosed] = useState(false);
  const [compact, setCompact] = useState(() => !!prefs().compact);
  const [palette, setPalette] = useState(false);
  const smart = !!(BY.navGroups && BY.navGroups.length && BY.ui);
  const width = compact ? 76 : 264;
  // العناصر العائمة (المساعد · شريط المكالمة) ترتفع فوق الشريط السفلي عبر هذا الصنف (index.css)
  useEffect(() => {
    document.documentElement.classList.toggle("has-tabbar", smart);
    return () => document.documentElement.classList.remove("has-tabbar");
  }, [smart]);

  useEffect(() => {
    document.body.style.overflow = mobileOpen ? "hidden" : "";
    document.documentElement.classList.toggle("nav-open", mobileOpen);   // يُخفي زرّ المساعد فوق الدرج
    const esc = (e) => { if (e.key === "Escape") setMobileOpen(false); };
    document.addEventListener("keydown", esc);
    return () => { document.removeEventListener("keydown", esc); document.body.style.overflow = ""; };
  }, [mobileOpen]);
  useEffect(() => {                                   // Ctrl/⌘+K — لوحة الأوامر من أي صفحة
    if (!smart) return undefined;
    const key = (e) => { if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") { e.preventDefault(); setPalette((p) => !p); } };
    document.addEventListener("keydown", key);
    return () => document.removeEventListener("keydown", key);
  }, [smart]);
  const toggleCompact = () => { const c = !compact; setCompact(c); savePrefs({ compact: c }); };
  useEffect(() => { if (smart) applyScale(prefs().scale || 100); }, [smart]);

  return (
    <>
      {/* خلفية اللوحة — أهدأ من صفحة الهبوط، ومكتوبة بمواضع صريحة
          لأن أدوات inset السالبة السابقة لم تُطبَّق وتركت الطبقة 0×0. */}
      <Backdrop dense={false} />

      <Flashes />
      <AssistBanner />

      <div className="flex min-h-screen">
        {/* شريط جانبي — ثابت على سطح المكتب */}
        <AnimatePresence initial={false}>
          {!desktopClosed && (
            <motion.aside
              initial={{ width: 0, opacity: 0 }}
              animate={{ width, opacity: 1 }}
              exit={{ width: 0, opacity: 0 }}
              transition={{ type: "spring", stiffness: 400, damping: 40 }}
              className="sticky top-0 hidden h-screen shrink-0 flex-col overflow-y-auto overflow-x-hidden
                         bg-sink/25 backdrop-blur-xl
                         shadow-[inset_-1px_0_0_rgb(var(--ov-rgb)/0.07)] lg:flex"
              aria-label={bi("التنقّل الرئيسي", "Main navigation")}>
              <div className="flex min-h-full flex-col p-3" style={{ width }}>
                <SideContent view={view} compact={compact} onCompact={smart ? toggleCompact : null} onPalette={() => setPalette(true)} />
              </div>
            </motion.aside>
          )}
        </AnimatePresence>

        {/* درج الجوال */}
        <AnimatePresence>
          {mobileOpen && (
            <>
              <motion.div key="scrim" onClick={() => setMobileOpen(false)}
                initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
                className="fixed inset-0 z-[190] bg-sink/60 backdrop-blur-sm lg:hidden" />
              <motion.aside key="drawer"
                initial={{ x: BY.dir === "rtl" ? "100%" : "-100%" }}
                animate={{ x: 0 }}
                exit={{ x: BY.dir === "rtl" ? "100%" : "-100%" }}
                transition={{ type: "spring", stiffness: 380, damping: 38 }}
                className="fixed inset-y-0 z-[200] flex w-[290px] max-w-[86vw] flex-col overflow-y-auto bg-ob-1 p-4
                           shadow-2xl lg:hidden start-0"
                style={{ paddingTop: "calc(env(safe-area-inset-top) + 16px)", paddingBottom: "calc(env(safe-area-inset-bottom) + 16px)" }}
                aria-label={bi("التنقّل الرئيسي", "Main navigation")}>
                <SideContent view={view} onPalette={() => { setMobileOpen(false); setPalette(true); }} />
              </motion.aside>
            </>
          )}
        </AnimatePresence>

        <div className="flex min-w-0 flex-1 flex-col">
          {/* الشريط العلوي */}
          <header className="sticky top-0 z-[150] bg-ob-0/70 backdrop-blur-xl backdrop-saturate-150
                             shadow-[inset_0_-1px_0_rgb(var(--ov-rgb)/0.07)]"
                  style={{ paddingTop: "env(safe-area-inset-top)" }}>
            <div className="flex items-center gap-2 px-4 py-3 sm:gap-3 sm:px-5 sm:py-3.5">
              <button type="button" onClick={() => setMobileOpen((o) => !o)} aria-expanded={mobileOpen}
                      aria-label={bi("القائمة", "Menu")}
                      className={`${smart ? "hidden" : "grid"} size-10 shrink-0 place-items-center rounded-xl text-ink
                                 shadow-[inset_0_0_0_1px_rgb(var(--ov-rgb)/0.1)]
                                 transition-colors hover:bg-ov/[0.06] lg:hidden`}>
                <span className="relative block h-0.5 w-[18px] rounded bg-current
                                 before:absolute before:-top-1.5 before:block before:h-0.5 before:w-[18px] before:rounded before:bg-current before:content-['']
                                 after:absolute after:top-1.5 after:block after:h-0.5 after:w-[18px] after:rounded after:bg-current after:content-['']" />
              </button>

              <button type="button" onClick={() => setDesktopClosed((c) => !c)} aria-expanded={!desktopClosed}
                      aria-label={bi("القائمة", "Menu")}
                      className="hidden size-10 shrink-0 place-items-center rounded-xl text-ink
                                 shadow-[inset_0_0_0_1px_rgb(var(--ov-rgb)/0.1)]
                                 transition-colors hover:bg-ov/[0.06] lg:grid">
                <span className="relative block h-0.5 w-[18px] rounded bg-current
                                 before:absolute before:-top-1.5 before:block before:h-0.5 before:w-[18px] before:rounded before:bg-current before:content-['']
                                 after:absolute after:top-1.5 after:block after:h-0.5 after:w-[18px] after:rounded after:bg-current after:content-['']" />
              </button>

              <a href={BY.urls.dashboard} className="no-underline lg:hidden">
                <Logo className="h-8 w-auto" />
              </a>

              {smart && (
                <button type="button" onClick={() => setPalette(true)} aria-label={bi("بحث سريع", "Quick search")}
                        className="hidden cursor-pointer items-center gap-2 rounded-xl border-0 bg-ov/[0.05] px-3 py-2 text-[13px] text-ink-3
                                   shadow-[inset_0_0_0_1px_rgb(var(--ov-rgb)/0.08)] transition-colors hover:text-ink md:flex md:min-w-[260px]">
                  <Icon name="search" size={15} />
                  <span className="flex-1 text-start">{bi("ابحث أو انتقل إلى…", "Search or jump to…")}</span>
                  <kbd className="rounded-md bg-ov/[0.08] px-1.5 py-0.5 font-mono text-[10.5px]">Ctrl K</kbd>
                </button>
              )}
              <nav className="ms-auto flex items-center gap-2">
                {smart && <button type="button" onClick={() => setPalette(true)} aria-label={bi("بحث سريع", "Quick search")}
                                  className="grid size-10 shrink-0 cursor-pointer place-items-center rounded-full border-0 bg-transparent text-ink-2 shadow-[inset_0_0_0_1px_rgb(var(--ov-rgb)/0.1)] md:hidden">
                  <Icon name="search" size={16} /></button>}
                {smart && <Bell />}
                <span className={smart ? "hidden sm:contents" : "contents"}><ThemeToggle /></span>
                <a href={BY.urls.lang}
                   className={`${smart ? "hidden sm:inline-flex" : "inline-flex"} items-center gap-1.5 rounded-full px-3.5 py-2 text-[13px] font-bold
                              text-ink-2 no-underline shadow-[inset_0_0_0_1px_rgb(var(--ov-rgb)/0.1)]
                              transition-colors hover:text-au-cyan`}>
                  <Icon name="globe" size={15} />{BY.lang === "ar" ? "EN" : "ع"}
                </a>
                {/* صورة الحساب في الشريط العلوي — تظهر على الموبايل أيضاً (الاسم من sm فأعلى) */}
                <a href={BY.urls.account} title={BY.user.name}
                   className="inline-flex items-center gap-2 rounded-full bg-ov/[0.05] py-1 pe-1 ps-1 text-[13px]
                              font-bold text-ink-2 no-underline shadow-[inset_0_0_0_1px_rgb(var(--ov-rgb)/0.1)]
                              transition-colors hover:text-ink sm:pe-3.5">
                  <Avatar src={BY.user.avatar} name={BY.user.name} size={30} />
                  <span className="hidden max-w-[160px] truncate sm:inline" dir="auto">{BY.user.name}</span>
                </a>
              </nav>
            </div>
          </header>

          <main className={`mx-auto w-full ${WIDE.has(view) ? "max-w-[1760px] py-4 sm:py-4" : "max-w-[1180px] py-6 sm:py-8"} flex-1 px-4 sm:px-5 ${smart ? "pb-[calc(env(safe-area-inset-bottom)+104px)] lg:pb-8" : ""}`}>{children}</main>
          {smart && <CommandPalette open={palette} onClose={() => setPalette(false)} />}
          {smart && <MobileTabBar view={view} moreOpen={mobileOpen} onMore={() => setMobileOpen((o) => !o)} />}
          {BY.ui && <PwaLayer />}
        </div>
      </div>
    </>
  );
}
