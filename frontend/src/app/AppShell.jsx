import { useState, useEffect } from "react";
import { motion, AnimatePresence } from "motion/react";
import { BY, t, Icon, bi } from "./kit.jsx";

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
           className="flex items-center gap-3 rounded-xl px-3 py-2.5 text-[14px] font-bold text-ink-2
                      no-underline transition-colors hover:bg-white/[0.06] hover:text-ink">
          <Icon name="users" size={18} className="text-ink-3" />
          <span className="truncate">{BY.user.name}</span>
        </a>
        <a href={BY.urls.logout}
           className="flex items-center gap-3 rounded-xl px-3 py-2.5 text-[14px] font-bold text-ink-2
                      no-underline transition-colors hover:bg-white/[0.06] hover:text-ink">
          <Icon name="logout" size={18} className="text-ink-3" />
          {t("logout")}
        </a>
      </div>
    </>
  );
}

/* إشعارات flash القادمة من Flask */
function Flashes() {
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

export default function AppShell({ view, children }) {
  const [open, setOpen] = useState(false);

  useEffect(() => {
    document.body.style.overflow = open ? "hidden" : "";
    const esc = (e) => { if (e.key === "Escape") setOpen(false); };
    document.addEventListener("keydown", esc);
    return () => { document.removeEventListener("keydown", esc); document.body.style.overflow = ""; };
  }, [open]);

  return (
    <>
      {/* خلفية الشفق */}
      <div aria-hidden="true"
           className="pointer-events-none fixed -inset-x-[10%] -inset-y-[20%] -z-30 opacity-60 saturate-[1.2] [contain:layout_paint]">
        <i className="drift-a absolute -start-[10vw] -top-[10vw] block size-[44vw] rounded-full mix-blend-screen
                      bg-[radial-gradient(circle_at_30%_30%,rgb(124_108_246/0.7),transparent_62%)]" />
        <i className="drift-b absolute -end-[6vw] top-[6vw] block size-[36vw] rounded-full mix-blend-screen
                      bg-[radial-gradient(circle_at_60%_40%,rgb(34_211_238/0.45),transparent_60%)]" />
      </div>
      <div aria-hidden="true" className="veil pointer-events-none fixed inset-0 -z-20" />
      <div aria-hidden="true" className="grain pointer-events-none fixed inset-0 -z-10 opacity-[0.14]" />

      <Flashes />

      <div className="flex min-h-screen">
        {/* شريط جانبي — ثابت على سطح المكتب */}
        <aside className="sticky top-0 hidden h-screen w-[252px] shrink-0 flex-col overflow-y-auto
                          bg-black/25 p-4 backdrop-blur-xl
                          shadow-[inset_-1px_0_0_rgb(255_255_255/0.07)] lg:flex"
               aria-label={bi("التنقّل الرئيسي", "Main navigation")}>
          <SideContent view={view} />
        </aside>

        {/* درج الجوال */}
        <AnimatePresence>
          {open && (
            <>
              <motion.div key="scrim" onClick={() => setOpen(false)}
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
              <button type="button" onClick={() => setOpen((o) => !o)} aria-expanded={open}
                      aria-label={bi("القائمة", "Menu")}
                      className="grid size-10 shrink-0 place-items-center rounded-xl text-ink
                                 shadow-[inset_0_0_0_1px_rgb(255_255_255/0.1)]
                                 transition-colors hover:bg-white/[0.06] lg:hidden">
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
                <a href={BY.urls.account}
                   className="hidden items-center gap-2 rounded-full bg-white/[0.05] px-3.5 py-2 text-[13px]
                              font-bold text-ink-2 no-underline shadow-[inset_0_0_0_1px_rgb(255_255_255/0.1)]
                              transition-colors hover:text-ink sm:inline-flex">
                  <Icon name="users" size={14} className="text-au-cyan" />{BY.user.name}
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
