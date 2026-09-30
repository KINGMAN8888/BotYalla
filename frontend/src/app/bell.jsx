/* مركز الإشعارات: جرس في الشريط العلوي — محادثة أُسندت إليك · إشارة لك · دفعة وصلت · تكامل فشل · تذاكر.
   الإشعار مخزَّن بنوعه وبياناته، والنص هنا بلغة المستخدم. استطلاع كل 45 ثانية والصفحة ظاهرة فقط. */
import { useEffect, useRef, useState } from "react";
import { BY, bi, Icon } from "./kit.jsx";
import { PushToggle } from "./pwa.jsx";

const KIND = {
  assigned: ["user", (d) => bi(`أُسندت إليك محادثة ${d.name || ""}`, `A conversation with ${d.name || ""} was assigned to you`)],
  mention: ["chat", (d) => bi(`${d.by || "زميل"} أشار إليك في ${d.name || "محادثة"}: «${d.text || ""}»`, `${d.by || "A teammate"} mentioned you in ${d.name || "a chat"}: “${d.text || ""}”`)],
  paid: ["card", (d) => bi(`💳 دفعة جديدة ${d.amount || ""}${d.name ? ` من ${d.name}` : ""}${d.desc ? ` — ${d.desc}` : ""}`, `💳 New payment ${d.amount || ""}${d.name ? ` from ${d.name}` : ""}${d.desc ? ` — ${d.desc}` : ""}`)],
  integ_failed: ["link", (d) => bi(`تعذّر تنفيذ حدث في تكامل «${d.name || ""}» — افتح السجل`, `An event failed in the “${d.name || ""}” integration — open the log`)],
  ticket_new: ["help", (d) => bi(`تذكرة جديدة من ${d.user || ""}: ${d.subject || ""}`, `New ticket from ${d.user || ""}: ${d.subject || ""}`)],
  ticket_user: ["chat", (d) => bi(`${d.user || "العميل"} ردّ على تذكرة: ${d.subject || ""}`, `${d.user || "The customer"} replied on a ticket: ${d.subject || ""}`)],
  ticket_reply: ["help", (d) => bi(`فريق الدعم ردّ على تذكرتك: ${d.subject || ""}`, `Support replied to your ticket: ${d.subject || ""}`)],
  call: ["phone", (d) => bi(`📞 مكالمة واتساب واردة من ${d.name || "عميل"}`, `📞 Incoming WhatsApp call from ${d.name || "a customer"}`)],
  attention: ["chat", (d) => {
    const who = [d.name, d.bot].filter(Boolean).join(" · ");
    const head = { needs_support: bi("🙋 عميل يحتاج مساعدتك", "🙋 A customer needs you"), handoff: bi("🚨 محادثة تحتاج تدخّلك", "🚨 A conversation needs you"),
                   bad_rating: bi("⚠️ تقييم سلبي", "⚠️ Negative rating"), human_msg: bi("💬 رسالة جديدة", "💬 New message") }[d.why] || bi("💬 عميل ينتظر ردّك", "💬 A customer is waiting");
    return `${head}${who ? ` — ${who}` : ""}${d.text ? `: «${d.text}»` : ""}`;
  }],
};
const since = (ts) => {
  const s = Math.max(0, Math.floor(Date.now() / 1000) - ts);
  return s < 60 ? bi("الآن", "now") : s < 3600 ? bi(`${Math.floor(s / 60)} د`, `${Math.floor(s / 60)}m`)
    : s < 86400 ? bi(`${Math.floor(s / 3600)} س`, `${Math.floor(s / 3600)}h`) : bi(`${Math.floor(s / 86400)} يوم`, `${Math.floor(s / 86400)}d`);
};
async function api(url, body) {
  try {
    const r = await fetch(url, body ? { method: "POST", headers: { "Content-Type": "application/json", "X-CSRF-Token": BY.csrf }, body: JSON.stringify(body) }
      : { headers: { Accept: "application/json" } });
    return await r.json();
  } catch { return { ok: false }; }
}

export default function Bell() {
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState(null);
  const [unread, setUnread] = useState((BY.ui && BY.ui.unread) || 0);
  const box = useRef(null);
  const base = useRef(document.title.replace(/^\(\d+\)\s*/, ""));

  const load = async () => { const r = await api("/api/notifications"); if (r.ok) { setItems(r.items); setUnread(r.unread); } };
  useEffect(() => {
    const tick = () => { if (document.visibilityState === "visible") load(); };
    const t = setInterval(tick, 45000);
    document.addEventListener("visibilitychange", tick);
    window.addEventListener("by:notif", load);             // وصل إشعار فوري — حدّث العدّاد فوراً
    return () => { clearInterval(t); document.removeEventListener("visibilitychange", tick); window.removeEventListener("by:notif", load); };
  }, []);
  useEffect(() => {
    document.title = (unread ? `(${unread}) ` : "") + base.current;
    try { if (navigator.setAppBadge) (unread ? navigator.setAppBadge(unread) : navigator.clearAppBadge()).catch(() => {}); } catch { /* */ }
  }, [unread]);
  useEffect(() => {
    if (!open) return undefined;
    load();
    const out = (e) => { if (box.current && !box.current.contains(e.target)) setOpen(false); };
    const esc = (e) => { if (e.key === "Escape") setOpen(false); };
    document.addEventListener("mousedown", out); document.addEventListener("keydown", esc);
    return () => { document.removeEventListener("mousedown", out); document.removeEventListener("keydown", esc); };
  }, [open]);

  const go = async (n) => {
    if (!n.read_at) { await api("/api/notifications/read", { ids: [n.id] }); setUnread((u) => Math.max(0, u - 1)); }
    if (n.url) location.href = n.url;
  };
  const readAll = async () => {
    await api("/api/notifications/read", { all: true });
    setUnread(0); setItems((l) => (l || []).map((n) => ({ ...n, read_at: n.read_at || 1 })));
  };
  return (
    <div className="relative" ref={box}>
      <button type="button" onClick={() => setOpen(!open)} aria-expanded={open} aria-haspopup="true"
              aria-label={unread ? bi(`الإشعارات — ${unread} غير مقروءة`, `Notifications — ${unread} unread`) : bi("الإشعارات", "Notifications")}
              className="relative grid size-10 shrink-0 cursor-pointer place-items-center rounded-full border-0 bg-transparent text-ink-2
                         shadow-[inset_0_0_0_1px_rgb(var(--ov-rgb)/0.1)] transition-colors hover:text-au-cyan">
        <Icon name="bell" size={17} />
        {unread > 0 && <span className="tnum absolute -end-0.5 -top-0.5 grid min-w-[18px] place-items-center rounded-full bg-red-500 px-1 text-[10.5px] font-extrabold leading-[18px] text-white">{unread > 99 ? "99+" : unread}</span>}
      </button>
      {open && (
        <div className="fixed inset-x-3 top-[calc(env(safe-area-inset-top)+68px)] z-[300] overflow-hidden rounded-2xl sm:absolute sm:inset-x-auto sm:end-0 sm:top-12 sm:w-[380px] bg-[rgb(var(--menu-rgb))] shadow-2xl ring-1 ring-ov/10" role="dialog" aria-label={bi("الإشعارات", "Notifications")}>
          <div className="flex items-center justify-between gap-2 border-b border-ov/10 px-4 py-3">
            <b className="text-[14px] text-ink">{bi("الإشعارات", "Notifications")}</b>
            {unread > 0 && <button type="button" onClick={readAll} className="cursor-pointer border-0 bg-transparent text-[12px] font-bold text-au-cyan">{bi("تعليم الكل كمقروء", "Mark all read")}</button>}
          </div>
          <div className="max-h-[60vh] overflow-y-auto">
            {items === null ? <p className="m-0 p-6 text-center text-[13px] text-ink-3">…</p>
              : !items.length ? <p className="m-0 p-8 text-center text-[13px] text-ink-3">{bi("لا إشعارات بعد — سنخبرك هنا بكل ما يخصّك.", "No notifications yet — we'll tell you here about everything that concerns you.")}</p>
              : items.map((n) => {
                const [icon, text] = KIND[n.kind] || ["bell", () => n.kind];
                return (
                  <button key={n.id} type="button" onClick={() => go(n)}
                          className={`flex w-full cursor-pointer items-start gap-3 border-0 px-4 py-3 text-start transition-colors hover:bg-ov/[0.05] ${n.read_at ? "bg-transparent" : "bg-au-violet/[0.08]"}`}>
                    <span className="mt-0.5 grid size-8 shrink-0 place-items-center rounded-xl bg-ov/[0.06] text-au-cyan"><Icon name={icon} size={15} /></span>
                    <span className="min-w-0 flex-1"><span className="line-clamp-2 block text-[13px] leading-relaxed text-ink" dir="auto">{text(n.data || {})}</span>
                      <span className="text-[11px] text-ink-3">{since(n.created_at)}</span></span>
                    {!n.read_at && <i className="mt-2 size-2 shrink-0 rounded-full bg-au-cyan" aria-label={bi("غير مقروء", "Unread")} />}
                  </button>
                );
              })}
          </div>
          <PushToggle />
        </div>
      )}
    </div>
  );
}
