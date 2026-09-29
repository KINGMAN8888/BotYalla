/* الرئيسية — مركز القيادة: أهم ما يخص هذا المستخدم الآن، حسب دوره (مالك · موظف · أدمن · دعم) وباقته
   وما يستعمله فعلاً. الأدوات قابلة للترتيب والإخفاء، والاختصارات يختارها المستخدم؛ كلها تُحفظ في حسابه. */
import { useState } from "react";
import { P, BY, bi, AR, Icon, Card, Btn, Pill, num, Kpi } from "../kit.jsx";
import { savePrefs } from "../nav.jsx";

const PERSONA_SUB = {
  owner: bi("هذا ما يحدث في نشاطك الآن — وما يحتاج قرارك.", "Here's what's happening in your business — and what needs you."),
  basic: bi("بوتاتك ونتائجها وخطوتك التالية في مكان واحد.", "Your bots, their results and your next step in one place."),
  member: bi("محادثاتك والمسند إليك — ابدأ من الأهم.", "Your conversations and assignments — start with what matters."),
  admin: bi("صحة المنصة وطوابير المراجعة وأرقام اليوم.", "Platform health, review queues and today's numbers."),
  support: bi("ما ينتظر فريق الدعم الآن.", "What's waiting for the support team right now."),
};
const WIDGET_L = {
  kpis: bi("أرقام اليوم", "Today's numbers"), attention: bi("يحتاج انتباهك", "Needs your attention"), actions: bi("اختصاراتك", "Your shortcuts"),
  frequent: bi("الأكثر استخداماً", "Most used"), inbox: bi("آخر المحادثات", "Recent conversations"), activity: bi("النشاط — 14 يوماً", "Activity — 14 days"),
  bots: bi("بوتاتي", "My bots"), journey: bi("خطوتك التالية", "Your next step"), member_kpis: bi("محادثاتي", "My conversations"),
  admin_kpis: bi("المنصة اليوم", "Platform today"), admin_queues: bi("طوابير المراجعة", "Review queues"), support_queues: bi("طوابير الدعم", "Support queues"),
  admin_chart: bi("الإيراد والتسجيلات — 14 يوماً", "Revenue & signups — 14 days"), signups: bi("أحدث المسجّلين", "Latest signups"),
  insights: bi("اقتراحات لك", "Suggestions for you"), admin_revenue: bi("الإيراد والاشتراكات", "Revenue & subscriptions"),
  support_kpis: bi("أداء الدعم", "Support performance"),
};
const ago = (s) => (s == null ? "—" : s < 3600 ? bi(`${Math.max(1, Math.round(s / 60))} د`, `${Math.max(1, Math.round(s / 60))}m`)
  : s < 86400 ? bi(`${Math.round(s / 3600)} س`, `${Math.round(s / 3600)}h`) : bi(`${Math.round(s / 86400)} يوم`, `${Math.round(s / 86400)}d`));
const INS_TONE = { warn: "from-yellow-400/15", bad: "from-red-400/15", on: "from-au-teal/15", info: "from-au-violet/15" };
const ATT = {
  unassigned: [bi("محادثات تنتظر موظفاً", "Conversations waiting for an agent"), "inbox"],
  mentions: [bi("إشارات لك في الملاحظات", "Mentions for you in notes"), "chat"],
  pay_pending: [bi("روابط دفع بانتظار العميل", "Payment links awaiting the customer"), "card"],
  integ_failed: [bi("أحداث تكاملات فشلت اليوم", "Integration events failed today"), "link"],
  bots_stopped: [bi("بوتات متوقّفة", "Bots stopped"), "bot"],
  renew: [bi("يوم على انتهاء اشتراكك", "days until your plan ends"), "crown"],
};
const TONE = { warn: "bg-yellow-400/12 text-yellow-300", bad: "bg-red-400/12 text-red-300", info: "bg-au-cyan/12 text-au-cyan" };
const hhmm = (ts) => {
  if (!ts) return "";
  const d = new Date(ts * 1000);
  return d.toDateString() === new Date().toDateString() ? d.toTimeString().slice(0, 5) : d.toLocaleDateString(AR ? "ar-EG" : "en-GB", { day: "2-digit", month: "short" });
};
const money = (amount, cur) => `${(amount / (["KWD", "BHD", "OMR"].includes(cur) ? 1000 : 100)).toLocaleString(AR ? "ar-EG" : "en-US", { maximumFractionDigits: 2 })} ${cur}`;


function Bars({ data, keys }) {
  const max = Math.max(1, ...data.flatMap((d) => keys.map(([k]) => d[k] || 0)));
  return (
    <div>
      <div className="flex h-36 items-end gap-1.5" dir="ltr">
        {data.map((d, i) => (
          <div key={i} className="group relative flex h-full flex-1 items-end gap-0.5" title={keys.map(([k, l]) => `${l}: ${d[k] || 0}`).join(" · ")}>
            {keys.map(([k, , c]) => <span key={k} className="flex-1 rounded-t-md" style={{ height: `${Math.max(2, ((d[k] || 0) / max) * 100)}%`, background: c }} />)}
          </div>
        ))}
      </div>
      <div className="mt-2 flex flex-wrap gap-4 text-[11.5px] text-ink-3">
        {keys.map(([k, l, c]) => <span key={k} className="flex items-center gap-1.5"><i className="inline-block size-2.5 rounded-sm" style={{ background: c }} />{l}</span>)}
      </div>
    </div>
  );
}

function Empty({ text }) {
  return <p className="m-0 rounded-xl bg-ov/[0.03] px-3 py-4 text-center text-[13px] text-ink-3">{text}</p>;
}

/* ------------------------------------------------------------ الأدوات */
function W({ k, actions, setActions, edit }) {
  const m = P.metrics || {}, c = (P.inbox || {}).counts || {};
  const all = (BY.ui && BY.ui.actions) || [];
  switch (k) {
    case "kpis": {
      if (P.persona === "basic") {
        const t = P.total || {};
        return <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          <Kpi icon="users" label={bi("مشتركون", "Subscribers")} value={num(t.subscribers || 0)} sub={bi(`+${num(m.new_subs_week || 0)} هذا الأسبوع`, `+${num(m.new_subs_week || 0)} this week`)} />
          <Kpi icon="chat" label={bi("محادثات اليوم", "Chats today")} value={num(m.chats_today || 0)} sub={bi(`${num(m.msgs_today || 0)} رسالة`, `${num(m.msgs_today || 0)} messages`)} />
          <Kpi icon="cart" label={bi("طلبات", "Orders")} value={num(t.orders || 0)} />
          <Kpi icon="download" label={bi("إدخالات", "Leads")} value={num(t.leads || 0)} sub={bi(`${num(m.leads_week || 0)} هذا الأسبوع`, `${num(m.leads_week || 0)} this week`)} />
        </div>;
      }
      const paid = (m.paid_week || [])[0];
      return <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
        <Kpi icon="chat" label={bi("محادثات اليوم", "Chats today")} value={num(m.chats_today || 0)} sub={bi(`${num(m.msgs_today || 0)} رسالة واردة`, `${num(m.msgs_today || 0)} incoming`)} href="/inbox" />
        <Kpi icon="inbox" label={bi("تنتظر موظفاً", "Waiting for agent")} value={num(c.unassigned || 0)} tone={c.unassigned ? "text-yellow-300" : "text-au-teal"} href="/inbox" />
        <Kpi icon="download" label={bi("إدخالات 7 أيام", "Leads · 7 days")} value={num(m.leads_week || 0)} sub={bi(`${num(m.contacts_week || 0)} جهة جديدة`, `${num(m.contacts_week || 0)} new contacts`)} href="/contacts" />
        <Kpi icon="card" label={bi("المحصّل 7 أيام", "Collected · 7 days")} value={paid ? money(paid.total, paid.currency) : "0"} sub={paid ? bi(`${num(paid.n)} دفعة`, `${num(paid.n)} payments`) : null} href="/payments" tone="text-au-teal" />
        <Kpi icon="bot" label={bi("بوتات تعمل", "Bots live")} value={`${num(m.bots_live || 0)}/${num(m.bots || 0)}`} href="/dashboard" />
      </div>;
    }
    case "member_kpis":
      return <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Kpi icon="user" label={bi("مسندة إليّ", "Assigned to me")} value={num(c.mine || 0)} href="/inbox" />
        <Kpi icon="inbox" label={bi("تنتظر موظفاً", "Unassigned")} value={num(c.unassigned || 0)} tone={c.unassigned ? "text-yellow-300" : "text-au-teal"} href="/inbox" />
        <Kpi icon="chat" label={bi("إشاراتي", "Mentions")} value={num(c.mentions || 0)} href="/inbox" />
        <Kpi icon="clock" label={bi("كل المفتوحة", "All open")} value={num(c.open || 0)} href="/inbox" />
      </div>;
    case "attention": {
      const list = P.attention || [];
      if (!list.length) return <Empty text={bi("✓ كل شيء تحت السيطرة — لا شيء ينتظرك الآن.", "✓ All clear — nothing is waiting for you.")} />;
      return <div className="grid gap-2 sm:grid-cols-2">{list.map((a) => (
        <a key={a.k} href={a.u} className="flex items-center gap-3 rounded-2xl bg-ov/[0.035] px-4 py-3 no-underline transition-colors hover:bg-ov/[0.06]">
          <span className={`grid size-10 shrink-0 place-items-center rounded-xl ${TONE[a.tone]}`}><Icon name={ATT[a.k][1]} size={17} /></span>
          <span className="min-w-0 flex-1"><b className="tnum me-1.5 text-[18px] text-ink">{num(a.n)}</b><span className="text-[13px] text-ink-2">{ATT[a.k][0]}</span></span>
          <span className="text-ink-3">{BY.dir === "rtl" ? "←" : "→"}</span>
        </a>))}</div>;
    }
    case "actions": {
      const shown = actions.map((a) => all.find((x) => x.k === a)).filter(Boolean);
      return <>
        <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-3 lg:grid-cols-6">{shown.map((a) => (
          <a key={a.k} href={a.u} className="group flex flex-col items-center gap-2 rounded-2xl bg-ov/[0.035] px-2 py-4 text-center no-underline transition-all hover:-translate-y-0.5 hover:bg-au-violet/15">
            <span className="grid size-11 place-items-center rounded-2xl bg-[linear-gradient(135deg,rgb(124_108_246/0.25),rgb(34_211_238/0.18))] text-au-cyan transition-transform group-hover:scale-105"><Icon name={a.i} size={19} /></span>
            <span className="text-[12.5px] font-bold leading-tight text-ink">{a.l}</span>
          </a>))}</div>
        {edit && <div className="mt-3 rounded-2xl bg-ov/[0.03] p-3">
          <div className="mb-2 text-[12px] font-bold text-ink-2">{bi("اختر اختصاراتك (حتى 12):", "Pick your shortcuts (up to 12):")}</div>
          <div className="flex flex-wrap gap-1.5">{all.map((a) => { const on = actions.includes(a.k); return (
            <button key={a.k} type="button" onClick={() => setActions(on ? actions.filter((x) => x !== a.k) : [...actions, a.k].slice(0, 12))}
                    className={`flex cursor-pointer items-center gap-1.5 rounded-lg border-0 px-2.5 py-1.5 text-[12px] font-bold ${on ? "bg-au-teal/20 text-au-teal" : "bg-ov/5 text-ink-3"}`}>
              <Icon name={a.i} size={12} />{a.l}</button>); })}</div>
        </div>}
      </>;
    }
    case "frequent":
      return (P.frequent || []).length ? <div className="flex flex-wrap gap-2">{P.frequent.map((f) => (
        <a key={f.k} href={f.u} className="flex items-center gap-2 rounded-xl bg-ov/[0.04] px-3.5 py-2 text-[13px] font-bold text-ink no-underline hover:bg-ov/[0.07]">
          <Icon name={f.i} size={14} className="text-au-cyan" />{f.l}</a>))}</div>
        : <Empty text={bi("نتعلّم من استخدامك — الصفحات التي تفتحها كثيراً تظهر هنا تلقائياً.", "We learn from how you work — pages you open often appear here automatically.")} />;
    case "inbox": {
      const rows = (P.inbox || {}).rows || [];
      return rows.length ? <div className="grid gap-1">{rows.map((r) => (
        <a key={r.bot_id + r.peer} href={`/inbox?bot=${r.bot_id}&peer=${encodeURIComponent(r.peer)}`}
           className="flex items-center gap-3 rounded-xl px-2.5 py-2 no-underline hover:bg-ov/[0.05]">
          <span className="grid size-9 shrink-0 place-items-center rounded-full bg-au-violet/20 text-[13px] font-extrabold text-ink">{(r.name || "?").slice(0, 1)}</span>
          <span className="min-w-0 flex-1"><b className="block truncate text-[13.5px] text-ink" dir="auto">{r.name || r.peer.replace(/^[a-z]+:/, "")}</b>
            <span className="block truncate text-[12px] text-ink-3" dir="auto">{r.last_text}</span></span>
          <span className="shrink-0 text-end text-[11px] text-ink-3">{hhmm(r.last_at)}{r.unread > 0 && <b className="ms-1.5 rounded-full bg-au-cyan px-1.5 text-[10px] text-ob-0">{r.unread}</b>}</span>
        </a>))}</div> : <Empty text={bi("لا محادثات مفتوحة.", "No open conversations.")} />;
    }
    case "activity":
      return <Bars data={(m.activity || []).map((d) => ({ ...d }))} keys={[["in", bi("وارد", "Incoming"), "rgb(34 211 238 / .85)"], ["out", bi("صادر", "Outgoing"), "rgb(124 108 246 / .75)"]]} />;
    case "bots":
      return (P.bots || []).length ? <div className="grid gap-2 sm:grid-cols-2">{P.bots.map((b) => (
        <a key={b.id} href={b.url} className="flex items-center gap-3 rounded-xl bg-ov/[0.035] px-3 py-2.5 no-underline hover:bg-ov/[0.06]">
          <i className={`size-2.5 shrink-0 rounded-full ${b.running ? "bg-au-teal shadow-[0_0_8px_rgb(45_212_167/.8)]" : "bg-ink-3/50"}`} />
          <b className="min-w-0 flex-1 truncate text-[13.5px] text-ink" dir="auto">{b.name}</b>
          <span className="text-[11.5px] text-ink-3">{b.channel}</span>
        </a>))}</div> : <Empty text={bi("لا بوتات بعد.", "No bots yet.")} />;
    case "journey": {
      const j = P.journey || {};
      const L = { create: bi("اعمل بوتك", "Create your bot"), teach: bi("عرّف البوت بنشاطك", "Teach it your business"), run: bi("شغّل البوت", "Run it"),
        try: bi("جرّبه بنفسك", "Try it yourself"), share: bi("وصّله لعملائك", "Share with customers"), sale: bi("أول طلب أو عميل مهتم", "First order or lead"), grow: bi("كبّر أرباحك", "Grow your profits") };
      const done = (j.steps || []).filter((s) => s.done).length;
      return <div>
        <div className="mb-3 h-2 overflow-hidden rounded-full bg-ov/[0.06]"><i className="block h-full rounded-full bg-[linear-gradient(90deg,#22d3ee,#7c6cf6)]" style={{ width: `${(done / 7) * 100}%` }} /></div>
        <div className="flex flex-wrap gap-1.5">{(j.steps || []).map((s) => <Pill key={s.k} tone={s.done ? "on" : s.k === j.current ? "warn" : "mute"}>{s.done ? "✓ " : ""}{L[s.k]}</Pill>)}</div>
        {j.current && <Btn className="mt-3" icon="arrow" href={j.current === "grow" ? "/pricing" : "/dashboard"}>{bi("كمّل: ", "Continue: ")}{L[j.current]}</Btn>}
      </div>;
    }
    case "admin_kpis": {
      const s = P.stats || {};
      return <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
        <Kpi icon="users" label={bi("المستخدمون", "Users")} value={num(s.users || 0)} href="/admin/users" />
        <Kpi icon="crown" label={bi("مشتركون مدفوعون", "Paying")} value={num(s.paying || 0)} tone="text-au-teal" />
        <Kpi icon="bot" label={bi("بوتات تعمل", "Bots live")} value={`${num(s.active_bots || 0)}/${num(s.bots || 0)}`} />
        <Kpi icon="coins" label={bi("إيراد معتمد", "Approved revenue")} value={num(s.revenue || 0)} tone="text-au-teal" />
        <Kpi icon="wallet" label={bi("مدفوعات بانتظار المراجعة", "Payments to review")} value={num(s.pending || 0)} tone={s.pending ? "text-yellow-300" : "text-au-teal"} href="/admin/payments" />
      </div>;
    }
    case "admin_queues": case "support_queues": {
      const q = P.queues || {};
      const items = [["payments", bi("مدفوعات للمراجعة", "Payments to review"), "wallet", "/admin/payments"], ["tickets", bi("تذاكر مفتوحة", "Open tickets"), "chat", "/admin/tickets"],
        ["requests", bi("طلبات بوت جديدة", "New bot requests"), "inbox", "/admin/requests"],
        ...(P.persona === "admin" ? [["webhook_bad", bi("رفض توقيع ويبهوك (ساعة)", "Webhook signature rejects (1h)"), "shield", "/admin/meta"]] : [])];
      return <div className="grid gap-2 sm:grid-cols-2">{items.map(([k, l, i, u]) => (
        <a key={k} href={u} className="flex items-center gap-3 rounded-2xl bg-ov/[0.035] px-4 py-3 no-underline hover:bg-ov/[0.06]">
          <span className={`grid size-10 place-items-center rounded-xl ${q[k] ? TONE.warn : "bg-au-teal/12 text-au-teal"}`}><Icon name={i} size={17} /></span>
          <b className="tnum text-[20px] text-ink">{num(q[k] || 0)}</b><span className="flex-1 text-[13px] text-ink-2">{l}</span>
        </a>))}</div>;
    }
    case "admin_chart": {
      const ch = P.chart || { labels: [] };
      return <Bars data={ch.labels.map((l, i) => ({ rev: ch.revenue[i], users: ch.new_users[i] }))}
                   keys={[["rev", bi("إيراد", "Revenue"), "rgb(45 212 167 / .8)"], ["users", bi("تسجيلات", "Signups"), "rgb(124 108 246 / .75)"]]} />;
    }
    case "insights": {
      const list = P.insights || [];
      if (!list.length) return <Empty text={bi("✨ لا اقتراحات الآن — نراقب أرقامك ونخبرك حين نجد فرصة أو مشكلة.", "✨ No suggestions right now — we watch your numbers and tell you when we spot an opportunity or a problem.")} />;
      return <div className="grid gap-2.5 lg:grid-cols-3">{list.map((x) => (
        <div key={x.k} className={`flex flex-col gap-3 rounded-2xl bg-gradient-to-br ${INS_TONE[x.tone] || INS_TONE.info} to-transparent p-4 shadow-[inset_0_0_0_1px_rgb(var(--ov-rgb)/0.08)]`}>
          <div className="flex gap-3"><span className="grid size-9 shrink-0 place-items-center rounded-xl bg-ov/[0.08] text-au-cyan"><Icon name={x.i} size={16} /></span>
            <p className="m-0 text-[13px] leading-relaxed text-ink-2" dir="auto">{x.text}</p></div>
          <Btn sm variant="ghost" className="self-start" href={x.u}>{x.cta} {BY.dir === "rtl" ? "←" : "→"}</Btn>
        </div>))}</div>;
    }
    case "admin_revenue": {
      const r = P.revenue || {};
      return <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
        <Kpi icon="coins" label={bi("إيراد شهري متكرّر (تقديري)", "MRR (estimated)")} value={num(r.mrr || 0)} tone="text-au-teal" />
        <Kpi icon="crown" label={bi("اشتراكات مدفوعة فعّالة", "Active paid")} value={num(r.active_paid || 0)} />
        <Kpi icon="plus" label={bi("مشتركون جدد (30 يوماً)", "New paying (30d)")} value={num(r.new_30 || 0)} tone="text-au-teal" />
        <Kpi icon="clock" label={bi("اشتراكات انتهت (30 يوماً)", "Ended (30d)")} value={num(r.ended_30 || 0)} tone={r.ended_30 ? "text-yellow-300" : "text-au-teal"} />
        <Kpi icon="wallet" label={bi("معتمد (30 يوماً)", "Approved (30d)")} value={num(r.approved_30 || 0)} href="/admin/payments" />
      </div>;
    }
    case "support_kpis": {
      const s = P.support || {};
      return <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Kpi icon="chat" label={bi("تذاكر مفتوحة", "Open tickets")} value={num(s.open || 0)} href="/admin/tickets" />
        <Kpi icon="clock" label={bi("تنتظر +4 ساعات", "Waiting 4h+")} value={num(s.waiting || 0)} tone={s.waiting ? "text-red-300" : "text-au-teal"} href="/admin/tickets" />
        <Kpi icon="bolt" label={bi("متوسط أول رد", "Avg first reply")} value={ago(s.avg_first)} sub={bi("آخر 7 أيام", "Last 7 days")} />
        <Kpi icon="check" label={bi("خلال ساعة", "Within 1h")} value={s.within_hour == null ? "—" : `${s.within_hour}%`} tone="text-au-teal" />
      </div>;
    }
    case "signups":
      return <div className="grid gap-1">{(P.signups || []).map((u) => (
        <div key={u.id} className="flex flex-wrap items-center gap-3 rounded-xl px-2.5 py-2 hover:bg-ov/[0.04]">
          <b className="min-w-0 flex-1 truncate text-[13.5px] text-ink" dir="auto">{u.username}</b>
          <Pill tone={u.plan === "free" ? "mute" : "on"}>{u.plan}</Pill>
          <span className="text-[11.5px] text-ink-3">{bi(`${u.bots} بوت`, `${u.bots} bots`)} · {u.verified ? "✓" : bi("غير مؤكد", "unverified")} · {hhmm(u.created_at)}</span>
        </div>))}</div>;
    default:
      return null;
  }
}

/* جولة أول استخدام — خطوات حسب الدور، مرة واحدة (تُحفظ في الحساب) وتُعاد من الرابط أسفل الرئيسية */
const TOUR_COMMON = [
  ["grid", bi("كل شيء في مكانه", "Everything in its place"), bi("القائمة الجانبية مقسّمة لمجموعات: المحادثات، البوتات، التسويق، المبيعات… اطوِ ما لا تحتاجه، وثبّت ما تستعمله يومياً بالنجمة ☆ ليظهر في «المفضلة».",
    "The side menu is grouped: conversations, bots, marketing, sales… collapse what you don't need, and pin what you use daily with ☆ so it shows in Favourites.")],
  ["search", bi("انتقل لأي مكان بثانية", "Jump anywhere in a second"), bi("اضغط Ctrl + K من أي صفحة واكتب ما تريد — صفحة أو إجراء — ثم Enter.", "Press Ctrl + K on any page, type what you want — a page or an action — then Enter.")],
  ["settings", bi("الرئيسية على مقاسك", "A home page that fits you"), bi("«تخصيص الرئيسية»: اسحب الأدوات لترتيبها، أخفِ ما لا يهمك، واختر اختصاراتك. ومن أسفل القائمة غيّر حجم العرض.",
    "“Customize”: drag widgets to reorder, hide what you don't need, and pick your shortcuts. Change the display size at the bottom of the menu.")],
];
const TOUR = {
  owner: [["sparkles", bi("أهلاً بك في مركز القيادة", "Welcome to your command center"), bi("هنا أرقام نشاطك اليوم، وما يحتاج قرارك، واقتراحات مبنية على أرقامك الحقيقية.", "Here are today's numbers, what needs your decision, and suggestions built on your real data.")],
    ...TOUR_COMMON, ["bell", bi("لن يفوتك شيء", "Never miss a thing"), bi("الجرس في الأعلى يخبرك بكل ما يخصّك: محادثة أُسندت إليك، إشارة، دفعة وصلت، تكامل تعثّر.", "The bell at the top tells you everything that concerns you: an assigned chat, a mention, a payment, an integration hiccup.")]],
  basic: [["sparkles", bi("أهلاً بك", "Welcome"), bi("هنا نتائج بوتاتك وخطوتك التالية نحو أول ربح.", "Here are your bots' results and your next step to your first profit.")], ...TOUR_COMMON],
  member: [["sparkles", bi("أهلاً بك في الفريق", "Welcome to the team"), bi("هنا محادثاتك المسندة إليك وإشاراتك — ابدأ من الأهم.", "Here are the conversations assigned to you and your mentions — start with what matters.")],
    ...TOUR_COMMON, ["bell", bi("الجرس", "The bell"), bi("يصلك إشعار حين تُسند إليك محادثة أو يذكرك زميل.", "You're notified when a chat is assigned to you or a teammate mentions you.")]],
  admin: [["shield", bi("لوحة الإدارة", "Admin command center"), bi("صحة المنصة، الإيراد، وطوابير المراجعة — والاقتراحات تنبّهك لما تأخّر.", "Platform health, revenue and review queues — suggestions flag anything overdue.")], ...TOUR_COMMON],
  support: [["help", bi("مركز الدعم", "Support center"), bi("طوابير الدعم وأداؤه هنا، وكل تذكرة في مركز الدعم بجانبها ملف العميل كاملاً.", "Support queues and performance live here; every ticket in the support center shows the customer's full profile.")], ...TOUR_COMMON],
};

function Tour({ onDone }) {
  const steps = TOUR[P.persona] || TOUR.owner;
  const [i, setI] = useState(0);
  const [icon, title, text] = steps[i];
  return (
    <div className="fixed inset-0 z-[350] grid place-items-center bg-sink/60 p-4 backdrop-blur-sm" role="dialog" aria-modal="true" aria-label={title}>
      <div className="w-full max-w-[440px] rounded-3xl bg-[rgb(var(--menu-rgb))] p-7 text-center shadow-2xl ring-1 ring-ov/10">
        <span className="mx-auto grid size-16 place-items-center rounded-3xl bg-[linear-gradient(135deg,rgb(124_108_246/0.35),rgb(34_211_238/0.25))] text-au-cyan"><Icon name={icon} size={28} /></span>
        <h2 className="mb-2 mt-4 text-[20px] font-extrabold text-ink">{title}</h2>
        <p className="m-0 min-h-[66px] text-[14px] leading-relaxed text-ink-2">{text}</p>
        <div className="my-5 flex justify-center gap-1.5">{steps.map((_, j) => <i key={j} className={`h-1.5 rounded-full transition-all ${j === i ? "w-6 bg-au-cyan" : "w-1.5 bg-ov/20"}`} />)}</div>
        <div className="flex items-center justify-between gap-2">
          <button type="button" onClick={onDone} className="cursor-pointer border-0 bg-transparent text-[13px] font-bold text-ink-3 hover:text-ink">{bi("تخطّي", "Skip")}</button>
          <div className="flex gap-2">
            {i > 0 && <Btn sm variant="ghost" onClick={() => setI(i - 1)}>{bi("السابق", "Back")}</Btn>}
            {i < steps.length - 1 ? <Btn sm onClick={() => setI(i + 1)}>{bi("التالي", "Next")}</Btn> : <Btn sm variant="green" icon="check" onClick={onDone}>{bi("ابدأ", "Let's go")}</Btn>}
          </div>
        </div>
      </div>
    </div>
  );
}

const WIDE = new Set(["kpis", "member_kpis", "admin_kpis", "actions", "attention", "admin_queues", "support_queues", "insights", "admin_revenue", "support_kpis"]);

export default function Home() {
  const [order, setOrder] = useState(P.widgets || []);
  const [hidden, setHidden] = useState(P.hidden || []);
  const [actions, setActionsState] = useState(P.actions || []);
  const [edit, setEdit] = useState(false);
  const [tour, setTour] = useState(() => !(BY.ui && BY.ui.prefs && BY.ui.prefs.tour));
  const endTour = () => { setTour(false); savePrefs({ tour: true }); };
  const [drag, setDrag] = useState(null);             // مفتاح الأداة المسحوبة
  const [over, setOver] = useState(null);
  const setActions = (a) => { setActionsState(a); savePrefs({ actions: a }); };
  const dropOn = (target) => {                        // سحب وإفلات — والأسهم باقية للوحة المفاتيح وقارئات الشاشة
    if (!drag || drag === target) return;
    const o = order.filter((x) => x !== drag);
    o.splice(o.indexOf(target) + (order.indexOf(drag) < order.indexOf(target) ? 1 : 0), 0, drag);
    setOrder(o); savePrefs({ widgets: o });
  };
  const move = (k, d) => {
    const i = order.indexOf(k), j = i + d;
    if (j < 0 || j >= order.length) return;
    const o = [...order]; [o[i], o[j]] = [o[j], o[i]]; setOrder(o); savePrefs({ widgets: o });
  };
  const hide = (k) => { const h = [...hidden, k]; setHidden(h); savePrefs({ hidden: h }); };
  const show = (k) => { const h = hidden.filter((x) => x !== k); setHidden(h); savePrefs({ hidden: h }); };
  const reset = () => {
    setOrder(P.catalog); setHidden([]); savePrefs({ widgets: [], hidden: [], actions: [] }).then(() => location.reload());
  };
  const hr = new Date().getHours();
  const hello = hr < 12 ? bi("صباح الخير", "Good morning") : hr < 18 ? bi("مساء الخير", "Good afternoon") : bi("مساء النور", "Good evening");
  const visible = order.filter((k) => !hidden.includes(k));
  const today = new Date().toLocaleDateString(AR ? "ar-EG" : "en-GB", { weekday: "long", day: "numeric", month: "long" });
  return (
    <>
      <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
        <div className="min-w-0">
          <div className="text-[12.5px] font-bold text-ink-3">{today}</div>
          <h1 className="m-0 mt-1 text-[28px] font-extrabold leading-tight text-ink" dir="auto">{hello}، {BY.user.name} 👋</h1>
          <p className="m-0 mt-1.5 text-[14px] text-ink-3">{PERSONA_SUB[P.persona]}</p>
        </div>
        <div className="flex flex-wrap gap-2">
          {edit && <Btn variant="ghost" sm icon="refresh" onClick={reset}>{bi("الافتراضي", "Reset")}</Btn>}
          <Btn sm variant={edit ? "green" : "ghost"} icon={edit ? "check" : "settings"} onClick={() => setEdit(!edit)}>{edit ? bi("تم", "Done") : bi("تخصيص الرئيسية", "Customize")}</Btn>
        </div>
      </div>
      {edit && hidden.length > 0 && (
        <div className="mb-4 flex flex-wrap items-center gap-2 rounded-2xl bg-ov/[0.035] px-4 py-3">
          <span className="text-[12.5px] font-bold text-ink-2">{bi("أدوات مخفية:", "Hidden widgets:")}</span>
          {hidden.map((k) => <button key={k} type="button" onClick={() => show(k)} className="cursor-pointer rounded-lg border-0 bg-au-violet/15 px-2.5 py-1 text-[12px] font-bold text-ink">+ {WIDGET_L[k]}</button>)}
        </div>
      )}
      <div className="grid gap-4 lg:grid-cols-2">
        {visible.map((k) => (
          <Card key={k} draggable={edit} onDragStart={(e) => { setDrag(k); e.dataTransfer.effectAllowed = "move"; }}
                onDragOver={(e) => { if (edit && drag) { e.preventDefault(); setOver(k); } }} onDragLeave={() => setOver(null)}
                onDrop={(e) => { e.preventDefault(); dropOn(k); setDrag(null); setOver(null); }} onDragEnd={() => { setDrag(null); setOver(null); }}
                className={`${WIDE.has(k) ? "lg:col-span-2" : ""} ${edit ? "cursor-grab ring-1 ring-au-violet/40" : ""} ${over === k && drag !== k ? "ring-2 ring-au-cyan" : ""} ${drag === k ? "opacity-50" : ""}`}>
            <div className="mb-3 flex items-center justify-between gap-2">
              <b className="flex items-center gap-2 text-[14.5px] text-ink">{edit && <span className="text-ink-3" aria-hidden="true">⋮⋮</span>}{WIDGET_L[k]}</b>
              {edit && <span className="flex gap-1">
                <Btn sm variant="ghost" onClick={() => move(k, -1)} aria-label={bi("لأعلى", "Move up")}>↑</Btn>
                <Btn sm variant="ghost" onClick={() => move(k, 1)} aria-label={bi("لأسفل", "Move down")}>↓</Btn>
                <Btn sm variant="ghost" onClick={() => hide(k)} aria-label={bi("إخفاء", "Hide")}>✕</Btn>
              </span>}
            </div>
            <W k={k} actions={actions} setActions={setActions} edit={edit} />
          </Card>
        ))}
      </div>
      <p className="mt-6 text-center text-[12px] text-ink-3">{bi("💡 اضغط Ctrl + K من أي صفحة للانتقال السريع، و☆ بجانب أي صفحة في القائمة لتثبيتها في المفضلة. ", "💡 Press Ctrl + K anywhere to jump fast, and ☆ next to any menu page to pin it to favourites. ")}
        <button type="button" onClick={() => setTour(true)} className="cursor-pointer border-0 bg-transparent p-0 text-[12px] font-bold text-au-cyan underline">{bi("أعد الجولة التعريفية", "Replay the tour")}</button></p>
      {tour && <Tour onDone={endTour} />}
    </>
  );
}
