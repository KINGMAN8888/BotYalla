/* التنقّل الذكي: مجموعات أم قابلة للطيّ · المفضلة المثبّتة · بحث في القائمة · وضع مضغوط · لوحة أوامر (Ctrl+K).
   المجموعات وشروط ظهورها من الخادم (ui.NAV) — الواجهة ترتّب وتعرض فقط. التفضيلات تُحفظ في الحساب (/api/ui/prefs). */
import { useEffect, useMemo, useRef, useState } from "react";
import { BY, bi, Icon } from "./kit.jsx";

/* ------------------------------------------------------------ التفضيلات */
let saveTimer = null;
export function prefs() { return (BY.ui && BY.ui.prefs) || {}; }
export function savePrefs(patch) {
  if (!BY.ui) return Promise.resolve(null);
  BY.ui.prefs = { ...prefs(), ...patch };
  clearTimeout(saveTimer);
  return new Promise((res) => {
    saveTimer = setTimeout(async () => {
      try {
        const r = await fetch("/api/ui/prefs", { method: "POST", headers: { "Content-Type": "application/json", "X-CSRF-Token": BY.csrf },
          body: JSON.stringify(patch) });
        const j = await r.json();
        if (j.ok) BY.ui.prefs = j.prefs;
        res(j.prefs || null);
      } catch { res(null); }
    }, 350);
  });
}

const norm = (s) => String(s || "").toLowerCase().replace(/[ً-ْـ]/g, "").replace(/[أإآ]/g, "ا").replace(/ة/g, "ه").replace(/ى/g, "ي");
const allItems = () => (BY.navGroups || []).flatMap((g) => g.items.map((it) => ({ ...it, group: g.l, admin: g.admin })));

/* ------------------------------------------------------------ عنصر */
function Item({ it, active, compact, pinned, onPin }) {
  return (
    <div className="group relative">
      <a href={it.u} title={compact ? it.l : undefined} aria-current={active ? "page" : undefined}
         className={`relative flex items-center gap-3 rounded-xl py-2 text-[13.5px] font-bold no-underline transition-colors
                     ${compact ? "justify-center px-0" : "px-3"}
                     ${active ? "bg-[linear-gradient(100deg,rgb(124_108_246/0.28),rgb(34_211_238/0.12))] text-ink shadow-[inset_0_0_0_1px_rgb(124_108_246/0.4)]"
                              : "text-ink-2 hover:bg-ov/[0.06] hover:text-ink"}`}>
        <Icon name={it.i} size={17} className={active ? "text-au-cyan" : "text-ink-3"} />
        {!compact && <span className="min-w-0 flex-1 truncate">{it.l}</span>}
      </a>
      {!compact && onPin && (
        <button type="button" onClick={() => onPin(it.k)} aria-label={pinned ? bi("إزالة من المفضلة", "Unpin") : bi("تثبيت في المفضلة", "Pin")}
                title={pinned ? bi("إزالة من المفضلة", "Unpin") : bi("تثبيت في المفضلة", "Pin to favourites")}
                className={`absolute end-1.5 top-1/2 grid size-7 -translate-y-1/2 cursor-pointer place-items-center rounded-lg border-0 bg-transparent
                            text-[13px] transition-opacity hover:bg-ov/[0.08] ${pinned ? "text-yellow-300 opacity-100" : "text-ink-3 opacity-0 focus:opacity-100 group-hover:opacity-100"}`}>
          {pinned ? "★" : "☆"}
        </button>
      )}
    </div>
  );
}

function Label({ children }) {
  return <div className="mb-1 mt-4 px-3 text-[10.5px] font-extrabold uppercase tracking-[0.16em] text-ink-3/70">{children}</div>;
}

/* ------------------------------------------------------------ الشريط الجانبي */
export function SideNav({ view, compact, onPalette }) {
  const groups = BY.navGroups || [];
  const [pins, setPins] = useState(() => prefs().pins || []);
  const [collapsed, setCollapsed] = useState(() => prefs().collapsed || []);
  const [q, setQ] = useState("");
  const items = useMemo(allItems, []);
  const byKey = useMemo(() => Object.fromEntries(items.map((it) => [it.k, it])), [items]);
  const activeGroup = groups.find((g) => g.items.some((it) => it.k === view))?.k;

  const togglePin = (k) => { const p = pins.includes(k) ? pins.filter((x) => x !== k) : [...pins, k].slice(0, 12); setPins(p); savePrefs({ pins: p }); };
  const toggleGroup = (k) => { const c = collapsed.includes(k) ? collapsed.filter((x) => x !== k) : [...collapsed, k]; setCollapsed(c); savePrefs({ collapsed: c }); };

  if (q.trim()) {
    const n = norm(q);
    const hits = items.filter((it) => norm(it.l).includes(n) || norm(it.group).includes(n));
    return (
      <>
        <SearchBox q={q} setQ={setQ} onPalette={onPalette} first={hits[0]} />
        <nav className="mt-2 flex flex-col gap-0.5" aria-label={bi("نتائج البحث", "Search results")}>
          {hits.map((it) => <Item key={it.k} it={it} active={it.k === view} />)}
          {!hits.length && <p className="px-3 text-[12.5px] text-ink-3">{bi("لا نتائج", "No results")}</p>}
        </nav>
      </>
    );
  }
  const userGroups = groups.filter((g) => !g.admin), adminGroups = groups.filter((g) => g.admin);
  const renderGroup = (g) => {
    if (g.k === "home") return <div key={g.k} className="flex flex-col gap-0.5">{g.items.map((it) => <Item key={it.k} it={it} active={it.k === view} compact={compact} />)}</div>;
    const open = compact || g.k === activeGroup || !collapsed.includes(g.k);
    return (
      <div key={g.k} className={compact ? "mt-2 flex flex-col gap-0.5 border-t border-ov/[0.06] pt-2" : "mt-1"}>
        {!compact && (
          <button type="button" onClick={() => toggleGroup(g.k)} aria-expanded={open}
                  className="flex w-full cursor-pointer items-center gap-2 rounded-lg border-0 bg-transparent px-3 py-1.5 text-start text-[11.5px] font-extrabold text-ink-3 hover:text-ink-2">
            <span className="flex-1 truncate">{g.l}</span>
            <span className={`text-[10px] transition-transform ${open ? "" : BY.dir === "rtl" ? "rotate-90" : "-rotate-90"}`}>▾</span>
          </button>
        )}
        {open && <div className="flex flex-col gap-0.5">{g.items.map((it) => <Item key={it.k} it={it} active={it.k === view} compact={compact} pinned={pins.includes(it.k)} onPin={togglePin} />)}</div>}
      </div>
    );
  };
  const favs = pins.map((k) => byKey[k]).filter(Boolean);
  return (
    <>
      {!compact && <SearchBox q={q} setQ={setQ} onPalette={onPalette} />}
      {favs.length > 0 && !compact && <>
        <Label>{bi("المفضلة", "Favourites")}</Label>
        <div className="flex flex-col gap-0.5">{favs.map((it) => <Item key={"p" + it.k} it={it} active={false} pinned onPin={togglePin} />)}</div>
      </>}
      {!compact && <Label>{bi("المنصة", "Workspace")}</Label>}
      <nav className="flex flex-col" aria-label={bi("التنقّل الرئيسي", "Main navigation")}>{userGroups.map(renderGroup)}</nav>
      {adminGroups.length > 0 && <>
        {compact ? <div className="mt-3 border-t border-au-violet/30" /> : <Label>{bi("الإدارة", "Admin")}</Label>}
        <nav className="flex flex-col" aria-label={bi("الإدارة", "Admin")}>{adminGroups.map(renderGroup)}</nav>
      </>}
    </>
  );
}

function SearchBox({ q, setQ, onPalette, first }) {
  return (
    <div className="relative mb-1">
      <Icon name="search" size={14} className="pointer-events-none absolute start-3 top-1/2 -translate-y-1/2 text-ink-3" />
      <input value={q} onChange={(e) => setQ(e.target.value)} placeholder={bi("ابحث في القائمة…", "Search menu…")} aria-label={bi("ابحث في القائمة", "Search menu")}
             onKeyDown={(e) => { if (e.key === "Enter" && first) location.href = first.u; if (e.key === "Escape") setQ(""); }}
             className="w-full rounded-xl border-0 bg-ov/[0.05] py-2 pe-12 ps-9 text-[13px] text-ink outline-none shadow-[inset_0_0_0_1px_rgb(var(--ov-rgb)/0.08)] focus:shadow-[inset_0_0_0_1px_rgb(124_108_246/0.7)]" />
      <button type="button" onClick={onPalette} title={bi("لوحة الأوامر", "Command palette")}
              className="absolute end-2 top-1/2 -translate-y-1/2 cursor-pointer rounded-md border-0 bg-ov/[0.08] px-1.5 py-0.5 font-mono text-[10.5px] text-ink-3">Ctrl K</button>
    </div>
  );
}

/* ------------------------------------------------------------ لوحة الأوامر */
export function CommandPalette({ open, onClose }) {
  const [q, setQ] = useState("");
  const [sel, setSel] = useState(0);
  const box = useRef(null);
  useEffect(() => { if (open) { setQ(""); setSel(0); setTimeout(() => box.current?.focus(), 30); } }, [open]);
  const entries = useMemo(() => [
    ...((BY.ui && BY.ui.actions) || []).map((a) => ({ ...a, kind: bi("إجراء", "Action") })),
    ...allItems().map((it) => ({ ...it, kind: it.group })),
  ], []);
  const n = norm(q);
  const list = (n ? entries.filter((e) => norm(e.l).includes(n) || norm(e.kind).includes(n)) : entries).slice(0, 12);
  if (!open) return null;
  const go = (e) => { if (e) location.href = e.u; };
  return (
    <div className="fixed inset-0 z-[400] flex items-start justify-center bg-sink/60 px-4 pt-[12vh] backdrop-blur-sm" onMouseDown={onClose} role="dialog" aria-modal="true" aria-label={bi("لوحة الأوامر", "Command palette")}>
      <div className="w-full max-w-[560px] overflow-hidden rounded-2xl bg-[rgb(var(--menu-rgb))] shadow-2xl ring-1 ring-ov/10" onMouseDown={(e) => e.stopPropagation()}>
        <div className="flex items-center gap-2 border-b border-ov/10 px-4">
          <Icon name="search" size={16} className="text-ink-3" />
          <input ref={box} value={q} onChange={(e) => { setQ(e.target.value); setSel(0); }} placeholder={bi("إلى أين؟ اكتب اسم صفحة أو إجراء…", "Where to? Type a page or action…")}
                 onKeyDown={(e) => {
                   if (e.key === "ArrowDown") { e.preventDefault(); setSel((s) => Math.min(s + 1, list.length - 1)); }
                   else if (e.key === "ArrowUp") { e.preventDefault(); setSel((s) => Math.max(s - 1, 0)); }
                   else if (e.key === "Enter") go(list[sel]);
                   else if (e.key === "Escape") onClose();
                 }}
                 className="min-w-0 flex-1 border-0 bg-transparent py-4 text-[15px] text-ink outline-none" />
          <kbd className="rounded-md bg-ov/[0.08] px-1.5 py-0.5 font-mono text-[10.5px] text-ink-3">Esc</kbd>
        </div>
        <div className="max-h-[50vh] overflow-y-auto p-2" role="listbox">
          {list.map((e, i) => (
            <button key={e.kind + e.k} type="button" role="option" aria-selected={i === sel} onMouseEnter={() => setSel(i)} onClick={() => go(e)}
                    className={`flex w-full cursor-pointer items-center gap-3 rounded-xl border-0 px-3 py-2.5 text-start ${i === sel ? "bg-au-violet/20" : "bg-transparent"}`}>
              <span className="grid size-8 shrink-0 place-items-center rounded-lg bg-ov/[0.06] text-au-cyan"><Icon name={e.i} size={15} /></span>
              <span className="min-w-0 flex-1 truncate text-[14px] font-bold text-ink">{e.l}</span>
              <span className="shrink-0 text-[11.5px] text-ink-3">{e.kind}</span>
            </button>
          ))}
          {!list.length && <p className="m-0 px-3 py-6 text-center text-[13px] text-ink-3">{bi("لا نتائج", "No results")}</p>}
        </div>
      </div>
    </div>
  );
}
