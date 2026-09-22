import { useState, useEffect } from "react";
import { motion, AnimatePresence } from "motion/react";
import { BY, t, Icon, bi, Avatar } from "./kit.jsx";
import Backdrop from "../Backdrop.jsx";

/* ============================================================================
   قشرة اللوحة: شريط جانبي ثابت + شريط علوي + درج للجوال + إشعارات.
   ========================================================================== */

function NavLink({ item, active }) {
  return (
    <a href={item.u}
       className={
         "relative flex items-center gap-3 rounded-xl px-3 py-2.5 text-[14px] font-bold no-underline " +
         "transition-colors duration-300 " +
         (active ? "text-white" : "text-ink-2 hover:bg-white/[0.06] hover:text-ink")
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

function SideContent({ view }) {
  return (
    <>
      <a href={BY.urls.dashboard} className="mb-6 flex items-center gap-2.5 px-3 no-underline">
        <img src={BY.urls.logo} alt={BY.brand} className="h-9 w-auto" />
      </a>

      <div className="mb-1 px-3 text-[10.5px] font-extrabold uppercase tracking-[0.18em] text-ink-3/70">
        {bi("المنصة", "Workspace")}
      </div>
      <nav className="flex flex-col gap-1">
        {BY.nav.map((it) => <NavLink key={it.k} item={it} active={it.k === view} />)}
      </nav>

      {BY.adminNav.length > 0 && (
        <>
          <div className="mt-6 mb-1 px-3 text-[10.5px] font-extrabold uppercase tracking-[0.18em] text-ink-3/70">
            {bi("الإدارة", "Admin")}
          </div>
          <nav className="flex flex-col gap-1">
            {BY.adminNav.map((it) => <NavLink key={it.k} item={it} active={it.k === view} />)}
          </nav>
        </>
      )}

      <div className="mt-auto flex flex-col gap-1 pt-5 shadow-[inset_0_1px_0_rgb(255_255_255/0.07)]">
        <a href={BY.urls.account}
           className="flex items-center gap-3 rounded-xl px-2.5 py-2 no-underline transition-colors hover:bg-white/[0.06]">
          <Avatar src={BY.user.avatar} name={BY.user.name} size={34} />
          <span className="min-w-0 flex-1">
            <span className="block truncate text-[14px] font-bold text-ink" dir="auto">{BY.user.name}</span>
            <span className="block truncate text-[11.5px] text-ink-3">{t("account_title")}</span>
          </span>
        </a>
        {/* الخروج POST مع CSRF: رابط GET كان يُخرج المستخدم من أي موقع بـ <img src=".../logout"> */}
        <form method="post" action={BY.urls.logout} className="m-0">
          <input type="hidden" name="csrf_token" value={BY.csrf} />
          <button type="submit"
                  className="flex w-full cursor-pointer items-center gap-3 rounded-xl border-0 bg-transparent px-3 py-2.5
                             text-start text-[14px] font-bold text-ink-2 transition-colors hover:bg-white/[0.06] hover:text-ink">
            <Icon name="logout" size={18} className="text-ink-3" />
            {t("logout")}
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

export default function AppShell({ view, children }) {
  const [mobileOpen, setMobileOpen] = useState(false);
  const [desktopClosed, setDesktopClosed] = useState(false);

  useEffect(() => {
    document.body.style.overflow = mobileOpen ? "hidden" : "";
    const esc = (e) => { if (e.key === "Escape") setMobileOpen(false); };
    document.addEventListener("keydown", esc);
    return () => { document.removeEventListener("keydown", esc); document.body.style.overflow = ""; };
  }, [mobileOpen]);

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
              animate={{ width: 252, opacity: 1 }}
              exit={{ width: 0, opacity: 0 }}
              transition={{ type: "spring", stiffness: 400, damping: 40 }}
              className="sticky top-0 hidden h-screen shrink-0 flex-col overflow-y-auto overflow-x-hidden
                         bg-black/25 backdrop-blur-xl
                         shadow-[inset_-1px_0_0_rgb(255_255_255/0.07)] lg:flex"
              aria-label={bi("التنقّل الرئيسي", "Main navigation")}>
              <div className="flex min-h-full w-[252px] flex-col p-4">
                <SideContent view={view} />
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
                className="fixed inset-0 z-[190] bg-black/60 backdrop-blur-sm lg:hidden" />
              <motion.aside key="drawer"
                initial={{ x: BY.dir === "rtl" ? "100%" : "-100%" }}
                animate={{ x: 0 }}
                exit={{ x: BY.dir === "rtl" ? "100%" : "-100%" }}
                transition={{ type: "spring", stiffness: 380, damping: 38 }}
                className="fixed inset-y-0 z-[200] flex w-[280px] flex-col overflow-y-auto bg-ob-1 p-4
                           shadow-2xl lg:hidden start-0"
                aria-label={bi("التنقّل الرئيسي", "Main navigation")}>
                <SideContent view={view} />
              </motion.aside>
            </>
          )}
        </AnimatePresence>

        <div className="flex min-w-0 flex-1 flex-col">
          {/* الشريط العلوي */}
          <header className="sticky top-0 z-[150] bg-ob-0/70 backdrop-blur-xl backdrop-saturate-150
                             shadow-[inset_0_-1px_0_rgb(255_255_255/0.07)]">
            <div className="flex items-center gap-3 px-5 py-3.5">
              <button type="button" onClick={() => setMobileOpen((o) => !o)} aria-expanded={mobileOpen}
                      aria-label={bi("القائمة", "Menu")}
                      className="grid size-10 shrink-0 place-items-center rounded-xl text-ink
                                 shadow-[inset_0_0_0_1px_rgb(255_255_255/0.1)]
                                 transition-colors hover:bg-white/[0.06] lg:hidden">
                <span className="relative block h-0.5 w-[18px] rounded bg-current
                                 before:absolute before:-top-1.5 before:block before:h-0.5 before:w-[18px] before:rounded before:bg-current before:content-['']
                                 after:absolute after:top-1.5 after:block after:h-0.5 after:w-[18px] after:rounded after:bg-current after:content-['']" />
              </button>

              <button type="button" onClick={() => setDesktopClosed((c) => !c)} aria-expanded={!desktopClosed}
                      aria-label={bi("القائمة", "Menu")}
                      className="hidden size-10 shrink-0 place-items-center rounded-xl text-ink
                                 shadow-[inset_0_0_0_1px_rgb(255_255_255/0.1)]
                                 transition-colors hover:bg-white/[0.06] lg:grid">
                <span className="relative block h-0.5 w-[18px] rounded bg-current
                                 before:absolute before:-top-1.5 before:block before:h-0.5 before:w-[18px] before:rounded before:bg-current before:content-['']
                                 after:absolute after:top-1.5 after:block after:h-0.5 after:w-[18px] after:rounded after:bg-current after:content-['']" />
              </button>

              <a href={BY.urls.dashboard} className="no-underline lg:hidden">
                <img src={BY.urls.logo} alt={BY.brand} className="h-8 w-auto" />
              </a>

              <nav className="ms-auto flex items-center gap-2">
                <a href={BY.urls.lang}
                   className="inline-flex items-center gap-1.5 rounded-full px-3.5 py-2 text-[13px] font-bold
                              text-ink-2 no-underline shadow-[inset_0_0_0_1px_rgb(255_255_255/0.1)]
                              transition-colors hover:text-au-cyan">
                  <Icon name="globe" size={15} />{BY.lang === "ar" ? "EN" : "ع"}
                </a>
                {/* صورة الحساب في الشريط العلوي — تظهر على الموبايل أيضاً (الاسم من sm فأعلى) */}
                <a href={BY.urls.account} title={BY.user.name}
                   className="inline-flex items-center gap-2 rounded-full bg-white/[0.05] py-1 pe-1 ps-1 text-[13px]
                              font-bold text-ink-2 no-underline shadow-[inset_0_0_0_1px_rgb(255_255_255/0.1)]
                              transition-colors hover:text-ink sm:pe-3.5">
                  <Avatar src={BY.user.avatar} name={BY.user.name} size={30} />
                  <span className="hidden max-w-[160px] truncate sm:inline" dir="auto">{BY.user.name}</span>
                </a>
              </nav>
            </div>
          </header>

          <main className="mx-auto w-full max-w-[1180px] flex-1 px-5 py-8">{children}</main>
        </div>
      </div>
    </>
  );
}
