/* الصندوق المشترك — المرحلة 6 من docs/ENTERPRISE_PLAN.md.
   كل محادثات الحساب (كل البوتات والقنوات) لفريق واحد: عروض (المفتوحة · لي · تنتظر موظفاً · مع البوت ·
   إشاراتي · معلّقة · مغلقة · الفِرق) · مسؤول وفريق وحالة · ردّ أو ملاحظة داخلية بـ@إشارة · ردود جاهزة بـ«/» ·
   لوحة جهة الاتصال. الإرسال والتولّي بمسارات صندوق البوت نفسها في الخادم؛ التحديث بالاستطلاع. */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { BY, P, t, bi, AR, Icon, Card, Btn, Field, Input, Textarea, Select, Pill, Empty, PageHead, num, Modal } from "../kit.jsx";
import { AssetPicker } from "../media.jsx";
import { payErr } from "./ChatPayments.jsx";
import { CallBar } from "../calls.jsx";

async function call(url, body, method = "POST") {
  try {
    const r = await fetch(url, method === "GET" ? { headers: { Accept: "application/json" } } : {
      method, headers: { "Content-Type": "application/json", "X-CSRF-Token": BY.csrf }, body: JSON.stringify(body || {}),
    });
    const j = await r.json().catch(() => ({ ok: false, error: "network" }));
    return { status: r.status, ...j };
  } catch { return { ok: false, error: "network" }; }
}
const get = (u) => call(u, null, "GET");

const hhmm = (ts) => {
  if (!ts) return "";
  const d = new Date(ts * 1000), now = new Date();
  return d.toDateString() === now.toDateString() ? d.toTimeString().slice(0, 5)
    : d.toLocaleDateString(AR ? "ar-EG" : "en-GB", { day: "2-digit", month: "short" });
};

function usePoll(fn, ms, deps) {
  useEffect(() => {
    let alive = true, timer = null;
    const tick = async () => {
      if (!alive) return;
      if (!document.hidden) { try { await fn(); } catch { /* الشبكة — نعيد لاحقاً */ } }
      if (alive) timer = setTimeout(tick, ms);
    };
    tick();
    return () => { alive = false; clearTimeout(timer); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
}

const CH = { whatsapp: ["WA", "#2dd4a7"], telegram: ["TG", "#22d3ee"], messenger: ["FB", "#60a5fa"], instagram: ["IG", "#f472b6"] };
const peerLabel = (peer) => {
  const tail = (peer || "").replace(/^(tg|wa|fb|ig):/, "");
  if (/^wa:[A-Z]{2}\./.test(peer || "")) return bi("رقم مخفي", "Hidden number");
  if (/^wb:/.test(peer || "")) return bi("زائر الموقع", "Website visitor") + " #" + tail.slice(-4);
  return /^wa:/.test(peer || "") ? "+" + tail : "id " + tail;
};
const STATUS = { open: [bi("مفتوحة", "Open"), "on"], pending: [bi("معلّقة", "Pending"), "warn"], resolved: [bi("مغلقة", "Resolved"), "mute"] };
const ERR = {
  user: bi("الموظف ليس في حسابك", "Not a member of your account"), team: bi("فريق غير موجود", "Team not found"),
  duplicate: bi("الاسم مستخدم من قبل", "That name is already used"), name: bi("اكتب اسماً", "Enter a name"),
  shortcut: bi("اختصار غير صالح", "Invalid shortcut"), body: bi("اكتب نص الرد", "Write the reply text"),
  limit: bi("وصلت للحد الأقصى", "Limit reached"), role: bi("للمالك والمدير فقط", "Owners and admins only"),
  empty: bi("اكتب شيئاً", "Write something"), rate: bi("محاولات كثيرة — انتظر قليلاً", "Too many attempts — wait a bit"),
  readonly: bi("الرد اليدوي غير متاح في باقتك", "Manual replies aren't in your plan"), network: bi("تعذّر الاتصال", "Connection failed"),
};
const errOf = (r) => r.error && ERR[r.error] ? ERR[r.error] : (typeof r.error === "string" && r.error.length > 12 ? r.error : bi("حدث خطأ", "Something went wrong"));
const memberName = (id) => (P.members || []).find((m) => m.id === id)?.username || "—";
const fill = (body, conv, contact) => body
  .replace(/\{\{\s*contact\.name\s*\}\}/g, contact?.name || conv?.name || "")
  .replace(/\{\{\s*contact\.phone\s*\}\}/g, contact?.phone || "")
  .replace(/\{\{\s*agent\.name\s*\}\}/g, P.me?.username || "");

/* ------------------------------------------------------------ القائمة */
function Row({ c, active, onOpen }) {
  const name = c.name || peerLabel(c.peer);
  const ch = /^wb:/.test(c.peer) ? ["WEB", "#f59e0b"] : (CH[c.bot_channel] || CH.telegram);
  return (
    <button type="button" onClick={() => onOpen(c)}
            className={"flex w-full cursor-pointer items-start gap-3 rounded-2xl border-0 px-3 py-2.5 text-start transition-colors " +
                       (active ? "bg-au-violet/20 shadow-[inset_0_0_0_1px_rgb(124_108_246/0.5)]" : "bg-transparent hover:bg-ov/[0.05]")}>
      <span className="relative grid size-10 shrink-0 place-items-center rounded-full bg-[linear-gradient(140deg,#8FE9FF,#B9AFFF)] text-[15px] font-extrabold text-[#07090F]">
        {(name || "?").trim().charAt(0).toUpperCase()}
        <span className="absolute -bottom-0.5 -end-0.5 rounded-md px-1 text-[8.5px] font-extrabold text-[#07090F]" style={{ background: ch[1] }}>{ch[0]}</span>
      </span>
      <span className="min-w-0 flex-1">
        <span className="flex items-center justify-between gap-2">
          <span className="truncate text-[13.5px] font-extrabold text-ink" dir="auto">{name}</span>
          <span className="tnum shrink-0 text-[11px] text-ink-3">{hhmm(c.last_at)}</span>
        </span>
        <span className="mt-0.5 flex items-center justify-between gap-2">
          <span className="truncate text-[12.5px] text-ink-3" dir="auto">{c.last_text || "—"}</span>
          {c.unread > 0 && <span className="grid min-w-5 shrink-0 place-items-center rounded-full bg-au-teal px-1.5 text-[11px] font-extrabold text-[#04140E]">{c.unread}</span>}
        </span>
        <span className="mt-1 flex flex-wrap items-center gap-1.5 text-[10.5px] font-bold text-ink-3">
          <span className="truncate">{c.bot_name}</span>
          {c.team_name && <span className="rounded-md bg-ov/[0.07] px-1.5 py-0.5">{c.team_name}</span>}
          {c.assignee_name ? <span className="rounded-md bg-au-violet/15 px-1.5 py-0.5 text-au-cyan">@{c.assignee_name}</span>
            : c.mode === "human" && c.status !== "resolved" ? <span className="rounded-md bg-yellow-400/15 px-1.5 py-0.5 text-yellow-300">{bi("ينتظر موظفاً", "Waiting")}</span> : null}
          {c.status === "pending" && <span className="rounded-md bg-yellow-400/15 px-1.5 py-0.5 text-yellow-300">{STATUS.pending[0]}</span>}
        </span>
      </span>
    </button>
  );
}

/* ------------------------------------------------------------ الرسائل */
function Bubble({ m, botId }) {
  if (m.direction === "note") {
    return (
      <div className="mx-auto w-full max-w-[88%] rounded-2xl bg-yellow-400/10 px-3.5 py-2.5 shadow-[inset_0_0_0_1px_rgb(250_204_21/0.25)]">
        <div className="mb-1 flex items-center gap-1.5 text-[11px] font-extrabold text-yellow-300"><Icon name="lock" size={12} />{bi("ملاحظة داخلية", "Internal note")} · {memberName(m.user_id)}</div>
        <div className="whitespace-pre-wrap break-words text-[13.5px] leading-relaxed text-ink" dir="auto">
          {(m.text || "").split(/(@[\w.\-]{2,40})/g).map((s, i) => (s.startsWith("@") ? <b key={i} className="text-au-cyan">{s}</b> : s))}
        </div>
        <div className="tnum mt-1 text-[10.5px] text-ink-3">{hhmm(m.created_at)}</div>
      </div>
    );
  }
  const mine = m.direction === "out";
  const who = m.sender === "human" ? (m.user_id ? memberName(m.user_id) : t("inbox_you")) : m.sender === "ai" ? t("inbox_ai") : m.sender === "bot" ? t("inbox_bot") : "";
  const skin = !mine ? "bg-ov/[0.07] text-ink rounded-es-md"
    : m.sender === "human" ? "text-[#07090F] bg-[linear-gradient(120deg,#8FE9FF,#B9AFFF)] rounded-ee-md"
    : m.sender === "ai" ? "bg-au-violet/25 text-ink shadow-[inset_0_0_0_1px_rgb(124_108_246/0.45)] rounded-ee-md"
    : "bg-ov/[0.035] text-ink-2 shadow-[inset_0_0_0_1px_rgb(var(--ov-rgb)/0.08)] rounded-ee-md";
  return (
    <div className={"flex " + (mine ? "justify-end" : "justify-start")}>
      <div className={"max-w-[80%] rounded-2xl px-3.5 py-2.5 " + skin}>
        {m.media_id ? (
          <a href={`/bot/${botId}/media/${m.media_id}`} target="_blank" rel="noopener" className="mb-1.5 block overflow-hidden rounded-xl">
            <img src={`/bot/${botId}/media/${m.media_id}`} alt="" loading="lazy" className="max-h-56 w-full object-cover" />
          </a>
        ) : m.kind === "media" ? <span className="mb-1 flex items-center gap-1.5 text-[12px] opacity-80"><Icon name="clip" size={13} /></span> : null}
        {m.text && <div className="whitespace-pre-wrap break-words text-[14px] leading-relaxed" dir="auto">{m.text}</div>}
        <div className={"mt-1 flex items-center gap-1.5 text-[10.5px] " + (m.sender === "human" ? "text-[#07090F]/70" : "text-ink-3")}>
          {who && <span className="font-bold">{who}</span>}<span className="tnum">{hhmm(m.created_at)}</span>
        </div>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------ الكاتب: ردّ · ملاحظة · «/» · «@» */
function Composer({ conv, contact, canned, windowClosed, onSend, onNote }) {
  const [mode, setMode] = useState("reply");
  const [text, setText] = useState("");
  const [asset, setAsset] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [pick, setPick] = useState(0);
  const box = useRef(null);
  useEffect(() => { setText(""); setAsset(""); setErr(""); }, [conv?.bot_id, conv?.peer]);
  const slash = mode === "reply" && /^\/[^\s]*$/.test(text) ? text.slice(1).toLowerCase() : null;
  const atm = mode === "note" ? (text.match(/@([\w.\-]*)$/) || [])[1] : undefined;
  const suggestions = slash !== null
    ? canned.filter((c) => c.shortcut.includes(slash) || (c.title || "").toLowerCase().includes(slash)).slice(0, 8)
    : atm !== undefined ? (P.members || []).filter((m) => m.username.toLowerCase().startsWith(atm.toLowerCase()) && m.id !== P.me?.id).slice(0, 6) : [];
  const choose = (s) => {
    if (slash !== null) setText(fill(s.body, conv, contact));
    else setText(text.replace(/@([\w.\-]*)$/, "@" + s.username + " "));
    setPick(0); box.current?.focus();
  };
  const submit = async (e) => {
    e && e.preventDefault();
    if (busy || (!text.trim() && !asset)) return;
    setBusy(true); setErr("");
    const r = mode === "note" ? await onNote(text.trim()) : await onSend(text.trim(), asset);
    setBusy(false);
    if (!r.ok) { setErr(r.window ? t("inbox_wa_window") : errOf(r)); return; }
    setText(""); setAsset("");
  };
  const onKey = (e) => {
    if (suggestions.length) {
      if (e.key === "ArrowDown") { e.preventDefault(); setPick((pick + 1) % suggestions.length); return; }
      if (e.key === "ArrowUp") { e.preventDefault(); setPick((pick - 1 + suggestions.length) % suggestions.length); return; }
      if (e.key === "Enter" || e.key === "Tab") { e.preventDefault(); choose(suggestions[Math.min(pick, suggestions.length - 1)]); return; }
      if (e.key === "Escape") { setText(text + " "); return; }
    }
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); submit(); }
  };
  const note = mode === "note";
  const blocked = !note && (windowClosed || !P.canReply);
  return (
    <form onSubmit={submit} className="relative px-3 pb-3 pt-2 shadow-[inset_0_1px_0_rgb(var(--ov-rgb)/0.08)]">
      <div className="mb-2 flex gap-1">
        {[["reply", bi("ردّ على العميل", "Reply"), "chat"], ["note", bi("ملاحظة داخلية", "Internal note"), "lock"]].map(([k, l, i]) => (
          <button key={k} type="button" onClick={() => setMode(k)}
                  className={`flex cursor-pointer items-center gap-1.5 rounded-lg border-0 px-3 py-1.5 text-[12.5px] font-bold ${mode === k ? (k === "note" ? "bg-yellow-400/15 text-yellow-300" : "bg-au-violet/20 text-ink") : "bg-transparent text-ink-3 hover:bg-ov/[0.05]"}`}>
            <Icon name={i} size={13} />{l}
          </button>
        ))}
      </div>
      {!note && windowClosed && (
        <p className="mb-2 mt-0 rounded-xl bg-yellow-400/10 px-3 py-2 text-[12.5px] text-yellow-200">{t("inbox_wa_window")}</p>
      )}
      {!note && !P.canReply && <p className="mb-2 mt-0 flex items-center gap-2 text-[12.5px] text-ink-3"><Icon name="lock" size={13} />{t("inbox_readonly")}</p>}
      {suggestions.length > 0 && (
        <div className="absolute inset-x-3 bottom-full z-10 mb-1 overflow-hidden rounded-xl bg-[rgb(var(--menu-rgb))] shadow-2xl">
          {suggestions.map((s, i) => (
            <button key={s.id} type="button" onMouseDown={(e) => { e.preventDefault(); choose(s); }}
                    className={`flex w-full cursor-pointer items-start gap-2 border-0 px-3 py-2 text-start ${i === pick ? "bg-au-violet/20" : "bg-transparent hover:bg-ov/[0.06]"}`}>
              {slash !== null ? <>
                <b className="shrink-0 font-mono text-[12px] text-au-cyan">/{s.shortcut}</b>
                <span className="min-w-0 text-[12.5px] text-ink-2"><b className="text-ink">{s.title}</b> <span className="line-clamp-1 text-ink-3" dir="auto">{s.body}</span></span>
              </> : <b className="text-[13px] text-ink">@{s.username}</b>}
            </button>
          ))}
        </div>
      )}
      <div className="flex items-end gap-2">
        <textarea ref={box} value={text} onChange={(e) => { setText(e.target.value); setPick(0); }} onKeyDown={onKey} rows={2} dir="auto"
                  disabled={busy || blocked}
                  placeholder={note ? bi("ملاحظة لا يراها العميل — @ لذكر زميل", "Not visible to the customer — @ to mention a teammate")
                                    : bi("اكتب ردك… «/» للردود الجاهزة", "Type a reply… “/” for canned replies")}
                  className={`min-h-[46px] w-full flex-1 resize-none rounded-xl px-3.5 py-2.5 text-[14px] text-ink outline-none
                              ${note ? "bg-yellow-400/[0.06] shadow-[inset_0_0_0_1px_rgb(250_204_21/0.3)]" : "bg-sink/25 shadow-[inset_0_0_0_1px_rgb(var(--ov-rgb)/0.1)] focus:shadow-[inset_0_0_0_1px_rgb(124_108_246/0.8)]"}`} />
        <Btn type="submit" icon={note ? "lock" : "rocket"} disabled={busy || blocked || (!text.trim() && !asset)}>{note ? bi("حفظ", "Save") : t("inbox_send")}</Btn>
      </div>
      {!note && P.canReply && <div className="mt-2"><AssetPicker compact value={asset} onChange={(v) => setAsset(v)} /></div>}
      {err && <p role="alert" className="mb-0 mt-2 text-[12.5px] font-bold text-red-300">{err}</p>}
    </form>
  );
}

/* ------------------------------------------------------------ اتصال صادر (المرحلة 8) */
function CallButton({ cur, name, windowClosed }) {
  const [st, setSt] = useState(null);                // {enabled, status}
  const [sent, setSent] = useState("");
  useEffect(() => {
    setSt(null); setSent("");
    if (!P.callsOn || !cur.peer.startsWith("wa:")) return;
    get(`/api/calls/permission?bot=${cur.bot_id}&peer=${encodeURIComponent(cur.peer)}`).then((r) => r.ok && setSt(r));
  }, [cur.bot_id, cur.peer]);
  if (!st || !st.enabled || !P.canReply) return null;
  if (st.status === "granted") {
    return <Btn sm variant="green" icon="phone" onClick={() => window.dispatchEvent(new CustomEvent("by:dial", { detail: { bot_id: cur.bot_id, peer: cur.peer, name } }))}>{bi("اتصال", "Call")}</Btn>;
  }
  if (windowClosed) return null;                     // الطلب رسالة تفاعلية — داخل النافذة فقط
  return <Btn sm variant="ghost" icon="phone" disabled={!!sent} title={st.status === "declined" ? bi("رفض العميل سابقاً", "The customer declined before") : ""}
              onClick={async () => { const r = await call("/api/calls/permission", { bot: cur.bot_id, peer: cur.peer }); setSent(r.ok ? "ok" : "err"); }}>
    {sent === "ok" ? bi("أُرسل طلب الإذن ✓", "Permission requested ✓") : sent === "err" ? bi("تعذّر الإرسال", "Could not send") : bi("طلب إذن الاتصال", "Request to call")}</Btn>;
}

/* ------------------------------------------------------------ طلب دفع (المرحلة 9) */
function PayRequest({ open, onClose, cur, onSent }) {
  const [f, setF] = useState(null);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => { if (open) { setErr(""); setF({ amount: "", currency: P.pay?.currency || "SAR", description: "", minutes: 60 }); } }, [open]);
  const send = async () => {
    if (busy) return;
    setBusy(true); setErr("");
    const r = await call("/api/pay/request", { bot: cur.bot_id, peer: cur.peer, ...f });
    setBusy(false);
    if (!r.ok) { setErr(payErr(r)); return; }
    onSent(); onClose();
  };
  return (
    <Modal open={open && !!f} onClose={onClose} title={bi("طلب دفع من العميل", "Request a payment")} icon="card"
           footer={<><Btn variant="ghost" onClick={onClose}>{bi("إلغاء", "Cancel")}</Btn><Btn icon="card" disabled={busy || !f?.amount} onClick={send}>{busy ? "…" : bi("إرسال الرابط", "Send link")}</Btn></>}>
      {f && <div className="grid gap-3">
        {err && <div className="rounded-xl bg-red-400/10 px-3 py-2 text-[13px] font-bold text-red-400">{err}</div>}
        <div className="grid grid-cols-[1fr_120px] gap-3">
          <Field label={bi("المبلغ", "Amount")}><Input dir="ltr" inputMode="decimal" autoFocus value={f.amount} placeholder="450" onChange={(e) => setF({ ...f, amount: e.target.value })} /></Field>
          <Field label={bi("العملة", "Currency")}><Select value={f.currency} onChange={(e) => setF({ ...f, currency: e.target.value })}>{(P.pay?.currencies || [f.currency]).map((c) => <option key={c} value={c}>{c}</option>)}</Select></Field>
        </div>
        <Field label={bi("الوصف (يراه العميل)", "Description (the customer sees it)")}>
          <Input dir="auto" maxLength={200} value={f.description} placeholder={bi("حجز غرفة مزدوجة — 3 ليالٍ", "Double room booking — 3 nights")} onChange={(e) => setF({ ...f, description: e.target.value })} />
        </Field>
        <Field label={bi("صلاحية الرابط", "Link valid for")}>
          <Select value={String(f.minutes)} onChange={(e) => setF({ ...f, minutes: Number(e.target.value) })}>
            {[[30, bi("30 دقيقة", "30 minutes")], [60, bi("ساعة", "1 hour")], [360, bi("6 ساعات", "6 hours")], [1440, bi("24 ساعة", "24 hours")]].map(([v, l]) => <option key={v} value={String(v)}>{l}</option>)}
          </Select>
        </Field>
        <p className="m-0 text-[12px] leading-relaxed text-ink-3">{bi("يصل العميل زر «ادفع الآن» (مدى · Apple Pay · بطاقة). عند الدفع يصله إيصال تلقائياً ويظهر لك في صفحة المدفوعات.", "The customer gets a “Pay now” button (mada · Apple Pay · card). Once paid they get a receipt automatically and it shows on the Payments page.")}</p>
      </div>}
    </Modal>
  );
}

/* ------------------------------------------------------------ التسلسلات للعميل */
function SeqPanel({ conv }) {
  const [d, setD] = useState(null);
  const [pick, setPick] = useState("");
  const [msg, setMsg] = useState("");
  const key = conv ? `${conv.bot_id}|${conv.peer}` : "";
  useEffect(() => {
    setD(null); setMsg("");
    if (!conv?.bot_id) return;
    get(`/api/sequences/peer?bot=${conv.bot_id}&peer=${encodeURIComponent(conv.peer)}`).then((r) => r.ok && setD(r));
  }, [key]); // eslint-disable-line react-hooks/exhaustive-deps
  if (!d) return null;
  const enroll = async () => {
    const r = await call("/api/sequences/enroll", { bot: conv.bot_id, peer: conv.peer, sequence: Number(pick) });
    if (r.ok) { setD({ ...d, items: r.items }); setMsg(""); }
    else setMsg({ already: bi("مسجَّل فيه بالفعل", "Already enrolled"), opted_out: bi("طلب العميل الإيقاف", "Customer opted out"), inactive: bi("التسلسل متوقّف", "Sequence is paused") }[r.error] || errOf(r));
  };
  const stop = async (id) => { const r = await call("/api/sequences/stop", { bot: conv.bot_id, peer: conv.peer, enrollment: id }); if (r.ok) setD({ ...d, items: r.items }); };
  const active = d.items.filter((e) => e.status === "active");
  return (
    <div className="border-t border-ov/10 pt-4">
      <div className="mb-2 text-[10.5px] font-extrabold uppercase tracking-wider text-ink-3">{bi("التسلسلات", "Sequences")}</div>
      {active.map((e) => (
        <div key={e.id} className="mb-1.5 flex items-center justify-between gap-2 rounded-lg bg-ov/[0.05] px-2.5 py-1.5">
          <span className="min-w-0 truncate text-[12.5px] text-ink" dir="auto">{e.name} <span className="text-ink-3">· {bi("خطوة", "step")} {e.step + 1}</span></span>
          <Btn sm variant="ghost" onClick={() => stop(e.id)}>{bi("إيقاف", "Stop")}</Btn>
        </div>
      ))}
      {d.available.length > 0 ? (
        <div className="mt-2 flex gap-1.5">
          <Select value={pick} onChange={(e) => setPick(e.target.value)}>
            <option value="">{bi("— أضِف لتسلسل —", "— Add to sequence —")}</option>
            {d.available.map((s) => <option key={s.id} value={String(s.id)}>{s.name}</option>)}
          </Select>
          <Btn sm disabled={!pick} onClick={enroll}>{bi("أضِف", "Add")}</Btn>
        </div>
      ) : !active.length && <p className="m-0 text-[12px] text-ink-3">{bi("لا تسلسلات نشطة لهذه القناة.", "No active sequences for this channel.")}</p>}
      {msg && <p className="mb-0 mt-1.5 text-[12px] font-bold text-yellow-300">{msg}</p>}
    </div>
  );
}

/* ------------------------------------------------------------ لوحة جهة الاتصال */
function ContactPanel({ conv, contact, teams, onAssign, onStatus }) {
  if (!conv) return null;
  return (
    <div className="grid gap-4 p-4 text-[13px]">
      <div>
        <div className="mb-1 text-[10.5px] font-extrabold uppercase tracking-wider text-ink-3">{bi("المحادثة", "Conversation")}</div>
        <Field label={bi("الحالة", "Status")}>
          <Select value={conv.status || "open"} onChange={(e) => onStatus(e.target.value)}>
            {Object.entries(STATUS).map(([k, [l]]) => <option key={k} value={k}>{l}</option>)}
          </Select>
        </Field>
        <Field className="mt-3" label={bi("المسؤول", "Assignee")}>
          <Select value={String(conv.assignee_id || "")} onChange={(e) => onAssign({ user: Number(e.target.value) || null, team: conv.team_id || null })}>
            <option value="">{bi("— بلا مسؤول —", "— Unassigned —")}</option>
            {(P.members || []).map((m) => <option key={m.id} value={String(m.id)}>{m.username}{m.id === P.me?.id ? bi(" (أنا)", " (me)") : ""}</option>)}
          </Select>
        </Field>
        <Field className="mt-3" label={bi("الفريق", "Team")}>
          <Select value={String(conv.team_id || "")} onChange={(e) => onAssign({ user: conv.assignee_id || null, team: Number(e.target.value) || null })}>
            <option value="">{bi("— بلا فريق —", "— No team —")}</option>
            {(teams || []).map((tm) => <option key={tm.id} value={String(tm.id)}>{tm.name}</option>)}
          </Select>
        </Field>
        {!!conv.team_id && !conv.assignee_id && (
          <Btn sm variant="ghost" icon="refresh" className="mt-2" onClick={() => onAssign({ user: null, team: conv.team_id, route: true })}>{bi("وزّع بالتناوب", "Auto-assign (round robin)")}</Btn>
        )}
      </div>
      <div className="border-t border-ov/10 pt-4">
        <div className="mb-2 text-[10.5px] font-extrabold uppercase tracking-wider text-ink-3">{bi("جهة الاتصال", "Contact")}</div>
        {contact?.source && (
          <div className="mb-2 rounded-lg bg-au-violet/15 px-2.5 py-1.5 text-[12px] text-ink" dir="auto">
            <b className="text-au-cyan">{contact.source.kind === "ad" ? bi("جاء من إعلان: ", "From ad: ") : bi("جاء من رابط: ", "From link: ")}</b>
            {/^https:\/\//.test(contact.source.url || "") ? <a href={contact.source.url} target="_blank" rel="noopener noreferrer" className="text-ink underline-offset-2 hover:underline">{contact.source.name}</a> : contact.source.name}
          </div>
        )}
        {contact?.id ? <>
          <b className="block text-[15px] text-ink" dir="auto">{contact.name || "—"}</b>
          <div className="mt-1 text-ink-3" dir="ltr">{contact.phone}</div>
          {contact.email && <div className="text-ink-3">{contact.email}</div>}
          {!!contact.tags?.length && <div className="mt-2 flex flex-wrap gap-1">{contact.tags.map((x) => <span key={x} className="rounded-md bg-au-teal/15 px-1.5 py-0.5 text-[11px] font-bold text-au-teal">#{x}</span>)}</div>}
          {Object.entries(contact.fields || {}).filter(([, v]) => v !== "" && v != null).slice(0, 12).map(([k, v]) => (
            <div key={k} className="mt-1.5 flex justify-between gap-2"><span className="text-ink-3">{k}</span><span className="truncate text-ink" dir="auto">{Array.isArray(v) ? v.join(", ") : String(v)}</span></div>
          ))}
          <Btn sm variant="ghost" icon="users" className="mt-3" href="/contacts">{bi("جهات الاتصال", "Contacts")}</Btn>
        </> : <p className="m-0 text-ink-3">{bi("لم تُربط بجهة اتصال بعد.", "Not linked to a contact yet.")}</p>}
      </div>
      <SeqPanel conv={conv} />
    </div>
  );
}

/* ------------------------------------------------------------ الإعدادات: الفرق · الردود الجاهزة · التوجيه */
function Settings({ open, onClose, teams, setTeams, canned, setCanned }) {
  const [tab, setTab] = useState("teams");
  const [edit, setEdit] = useState(null);
  const [err, setErr] = useState("");
  const [scope, setScope] = useState(P.scope || "all");
  const [routes, setRoutes] = useState(P.routes || {});
  const [chans, setChans] = useState(P.channelCfg || {});
  const setChan = (id, p) => setChans({ ...chans, [id]: { ...(chans[id] || {}), ...p } });
  const [msg, setMsg] = useState("");
  useEffect(() => { setEdit(null); setErr(""); setMsg(""); }, [tab, open]);
  const saveTeam = async () => {
    const r = await call("/api/inbox/teams/save", edit);
    if (!r.ok) { setErr(errOf(r)); return; }
    setTeams(r.teams); setEdit(null);
  };
  const delTeam = async (tm) => {
    if (!window.confirm(bi(`حذف فريق «${tm.name}»؟ المحادثات تبقى بلا فريق.`, `Delete team “${tm.name}”? Its conversations lose the team.`))) return;
    const r = await call("/api/inbox/teams/delete", { id: tm.id });
    if (r.ok) setTeams(r.teams);
  };
  const saveCanned = async () => {
    const r = await call("/api/canned/save", edit);
    if (!r.ok) { setErr(errOf(r)); return; }
    setCanned(r.items); setEdit(null);
  };
  const delCanned = async (c) => {
    if (!window.confirm(bi(`حذف «/${c.shortcut}»؟`, `Delete “/${c.shortcut}”?`))) return;
    const r = await call("/api/canned/delete", { id: c.id });
    if (r.ok) setCanned(r.items);
  };
  const saveRouting = async () => {
    const r = await call("/api/inbox/settings", { scope, routes, channels: chans });
    setMsg(r.ok ? bi("حُفظ ✓", "Saved ✓")
      : r.error === "away_text" ? bi("اكتب رسالة خارج الدوام للقناة التي حدّدت ساعاتها", "Write an away message for the channel with hours set")
      : r.error === "hours" ? bi("ساعات العمل غير صالحة", "Invalid working hours") : errOf(r));
  };
  const [calls, setCalls] = useState(P.callCfg || {});
  const saveCalls = async (b) => {
    const cc = calls[b.id] || {};
    const r = await call("/api/calls/settings", { bot: b.id, enabled: !!cc.enabled, missed_text: cc.missed_text || "" });
    setMsg(r.ok ? bi("حُفظ ✓ — زر الاتصال محدَّث عند Meta", "Saved ✓ — call button updated at Meta")
      : bi("رفضت Meta: ", "Meta refused: ") + (r.message || r.error || ""));
  };
  const tabs = [["teams", bi("الفرق", "Teams")], ["canned", bi("الردود الجاهزة", "Canned replies")], ["routing", bi("التوجيه والرؤية", "Routing & visibility")],
    ...((P.bots || []).some((b) => b.channel === "whatsapp") ? [["calls", bi("المكالمات", "Calls")]] : [])];
  return (
    <Modal open={open} onClose={onClose} wide title={bi("إعدادات الصندوق", "Inbox settings")} icon="settings">
      <div className="mb-4 flex flex-wrap gap-1">
        {tabs.map(([k, l]) => <button key={k} type="button" onClick={() => setTab(k)} className={`cursor-pointer rounded-lg border-0 px-3 py-1.5 text-[13px] font-bold ${tab === k ? "bg-au-violet/20 text-ink" : "bg-transparent text-ink-3 hover:bg-ov/[0.05]"}`}>{l}</button>)}
      </div>
      {err && <div className="mb-3 rounded-xl bg-red-400/10 px-3 py-2 text-[13px] font-bold text-red-400">{err}</div>}

      {tab === "teams" && (edit ? (
        <div className="grid gap-3">
          <Field label={bi("اسم الفريق", "Team name")}><Input dir="auto" maxLength={60} value={edit.name} onChange={(e) => setEdit({ ...edit, name: e.target.value })} /></Field>
          <Field label={bi("التوزيع", "Assignment")}>
            <Select value={edit.rule} onChange={(e) => setEdit({ ...edit, rule: e.target.value })}>
              <option value="round_robin">{bi("بالتناوب — كل محادثة جديدة للتالي", "Round robin — each new chat to the next member")}</option>
              <option value="manual">{bi("يدوي — تبقى على الفريق حتى يستلمها أحد", "Manual — stays on the team until someone picks it")}</option>
            </Select>
          </Field>
          <div>
            <span className="mb-1.5 block text-[13px] font-bold text-ink-2">{bi("الأعضاء", "Members")}</span>
            <div className="flex flex-wrap gap-1.5">
              {(P.members || []).map((m) => {
                const on = edit.members.includes(m.id);
                return <button key={m.id} type="button" onClick={() => setEdit({ ...edit, members: on ? edit.members.filter((x) => x !== m.id) : [...edit.members, m.id] })}
                               className={`cursor-pointer rounded-lg border-0 px-3 py-1.5 text-[12.5px] font-bold ${on ? "bg-au-teal/20 text-au-teal" : "bg-ov/5 text-ink-3"}`}>{m.username}</button>;
              })}
            </div>
          </div>
          <div className="flex gap-2"><Btn onClick={saveTeam}>{bi("حفظ", "Save")}</Btn><Btn variant="ghost" onClick={() => setEdit(null)}>{bi("إلغاء", "Cancel")}</Btn></div>
        </div>
      ) : (
        <div className="grid gap-2">
          {teams.map((tm) => (
            <div key={tm.id} className="flex items-center justify-between gap-3 rounded-xl bg-ov/[0.04] px-3 py-2.5">
              <span className="min-w-0"><b className="text-ink" dir="auto">{tm.name}</b>
                <span className="block text-[12px] text-ink-3">{tm.rule === "round_robin" ? bi("بالتناوب", "Round robin") : bi("يدوي", "Manual")} · {tm.members.map(memberName).join("، ") || bi("بلا أعضاء", "No members")}</span></span>
              <span className="flex shrink-0 gap-1.5">
                <Btn sm variant="ghost" icon="edit" onClick={() => setEdit({ id: tm.id, name: tm.name, rule: tm.rule, members: tm.members })}>{bi("تعديل", "Edit")}</Btn>
                <Btn sm variant="ghost" onClick={() => delTeam(tm)} aria-label={bi("حذف", "Delete")}><Icon name="trash" size={14} /></Btn>
              </span>
            </div>
          ))}
          {!teams.length && <p className="m-0 text-[13px] text-ink-3">{bi("مثل: الحجوزات · الشركات · العمرة. المحادثة المحوّلة لفريق يستلمها التالي بالتناوب.", "e.g. Bookings · Corporate · Umrah. A chat routed to a team goes to the next member in turn.")}</p>}
          <Btn icon="plus" className="justify-self-start" onClick={() => setEdit({ name: "", rule: "round_robin", members: [] })}>{bi("فريق جديد", "New team")}</Btn>
        </div>
      ))}

      {tab === "canned" && (edit ? (
        <div className="grid gap-3">
          <div className="grid grid-cols-[140px_1fr] gap-2">
            <Field label={bi("الاختصار", "Shortcut")}><Input dir="ltr" value={edit.shortcut} placeholder="umrah" onChange={(e) => setEdit({ ...edit, shortcut: e.target.value })} /></Field>
            <Field label={bi("العنوان", "Title")}><Input dir="auto" maxLength={80} value={edit.title} onChange={(e) => setEdit({ ...edit, title: e.target.value })} /></Field>
          </div>
          <Field label={bi("النص", "Text")} hint={bi("متغيّرات: {{contact.name}} · {{contact.phone}} · {{agent.name}}", "Variables: {{contact.name}} · {{contact.phone}} · {{agent.name}}")}>
            <Textarea dir="auto" rows={5} value={edit.body} onChange={(e) => setEdit({ ...edit, body: e.target.value })} />
          </Field>
          <div className="flex gap-2"><Btn onClick={saveCanned}>{bi("حفظ", "Save")}</Btn><Btn variant="ghost" onClick={() => setEdit(null)}>{bi("إلغاء", "Cancel")}</Btn></div>
        </div>
      ) : (
        <div className="grid gap-2">
          {canned.map((c) => (
            <div key={c.id} className="flex items-start justify-between gap-3 rounded-xl bg-ov/[0.04] px-3 py-2.5">
              <span className="min-w-0"><b className="font-mono text-[12.5px] text-au-cyan">/{c.shortcut}</b> <b className="text-ink">{c.title}</b>
                <span className="mt-0.5 line-clamp-2 block text-[12.5px] text-ink-3" dir="auto">{c.body}</span></span>
              <span className="flex shrink-0 gap-1.5">
                <Btn sm variant="ghost" icon="edit" onClick={() => setEdit({ id: c.id, shortcut: c.shortcut, title: c.title, body: c.body })}>{bi("تعديل", "Edit")}</Btn>
                <Btn sm variant="ghost" onClick={() => delCanned(c)} aria-label={bi("حذف", "Delete")}><Icon name="trash" size={14} /></Btn>
              </span>
            </div>
          ))}
          {!canned.length && <p className="m-0 text-[13px] text-ink-3">{bi("اكتب «/» في مربع الرد لاستدعائها.", "Type “/” in the reply box to use them.")}</p>}
          <Btn icon="plus" className="justify-self-start" onClick={() => setEdit({ shortcut: "", title: "", body: "" })}>{bi("رد جاهز جديد", "New canned reply")}</Btn>
        </div>
      ))}

      {tab === "routing" && (
        <div className="grid gap-4">
          <Field label={bi("ما يراه الموظف", "What members see")}>
            <Select value={scope} onChange={(e) => setScope(e.target.value)}>
              <option value="all">{bi("كل محادثات الحساب", "Every conversation in the account")}</option>
              <option value="own">{bi("المسندة إليه + غير المسندة + محادثات فِرقه", "Assigned to them + unassigned + their teams'")}</option>
            </Select>
          </Field>
          <div>
            <span className="mb-1.5 block text-[13px] font-bold text-ink-2">{bi("إعدادات كل قناة", "Per-channel settings")}</span>
            <p className="mb-2 mt-0 text-[12px] text-ink-3">{bi("حين يطلب العميل موظفاً (أو يحوّله البوت) تذهب المحادثة لهذا الفريق — بطاقة التحويل في الفلو يمكنها تحديد فريق آخر.", "When a customer asks for a human (or the bot hands off), the chat goes to this team — a flow's handoff card can pick another.")}</p>
            {(P.bots || []).map((b) => {
              const cc = chans[b.id] || {};
              const h = cc.hours;
              return (
                <div key={b.id} className="mb-3 rounded-2xl bg-ov/[0.035] p-3">
                  <div className="grid grid-cols-[1fr_200px] items-center gap-2">
                    <b className="truncate text-[13px] text-ink" dir="auto">{b.name} <span className="font-normal text-ink-3">· {(CH[b.channel] || CH.telegram)[0]}</span></b>
                    <Select value={String(routes[b.id] || "")} onChange={(e) => setRoutes({ ...routes, [b.id]: Number(e.target.value) || null })}>
                      <option value="">{bi("— بلا فريق —", "— No team —")}</option>
                      {teams.map((tm) => <option key={tm.id} value={String(tm.id)}>{tm.name}</option>)}
                    </Select>
                  </div>
                  <div className="mt-3 grid gap-2 sm:grid-cols-2">
                    <label className="flex items-center gap-2 text-[12.5px] text-ink-2">
                      <input type="checkbox" checked={!!h} onChange={(e) => setChan(b.id, { hours: e.target.checked ? { start: 9, end: 17, tz: 3, days: [0, 1, 2, 3, 6] } : null })} />
                      {bi("ساعات عمل الفريق + رسالة خارج الدوام", "Team hours + away message")}
                    </label>
                    <label className="flex items-center gap-2 text-[12.5px] text-ink-2">
                      {bi("إغلاق آلي بعد", "Auto-resolve after")}
                      <Input type="number" min={0} max={720} className="!w-[80px] !py-1.5" value={cc.auto_resolve || 0} onChange={(e) => setChan(b.id, { auto_resolve: Number(e.target.value) || 0 })} />
                      {bi("ساعة خمول (0 = لا)", "idle hours (0 = off)")}
                    </label>
                  </div>
                  {h && <div className="mt-2 grid gap-2">
                    <div className="grid grid-cols-3 gap-2">
                      <Field label={bi("من الساعة", "From")}><Input type="number" min={0} max={23} value={h.start} onChange={(e) => setChan(b.id, { hours: { ...h, start: Number(e.target.value) } })} /></Field>
                      <Field label={bi("إلى الساعة", "To")}><Input type="number" min={1} max={24} value={h.end} onChange={(e) => setChan(b.id, { hours: { ...h, end: Number(e.target.value) } })} /></Field>
                      <Field label={bi("المنطقة (UTC±)", "Time zone (UTC±)")}><Input type="number" step="0.5" value={h.tz} onChange={(e) => setChan(b.id, { hours: { ...h, tz: Number(e.target.value) } })} /></Field>
                    </div>
                    <div className="flex flex-wrap gap-1.5">
                      {[[5, bi("سبت", "Sat")], [6, bi("أحد", "Sun")], [0, bi("إثنين", "Mon")], [1, bi("ثلاثاء", "Tue")], [2, bi("أربعاء", "Wed")], [3, bi("خميس", "Thu")], [4, bi("جمعة", "Fri")]].map(([k, l]) => {
                        const on = (h.days || []).includes(k);
                        return <button key={k} type="button" onClick={() => setChan(b.id, { hours: { ...h, days: on ? h.days.filter((x) => x !== k) : [...(h.days || []), k] } })}
                                       className={`cursor-pointer rounded-lg border-0 px-2.5 py-1 text-[12px] font-bold ${on ? "bg-au-teal/20 text-au-teal" : "bg-ov/5 text-ink-3"}`}>{l}</button>;
                      })}
                    </div>
                    <Textarea dir="auto" rows={2} value={cc.away_text || ""} onChange={(e) => setChan(b.id, { away_text: e.target.value })}
                              placeholder={bi("مثل: فريقنا متاح من 9 صباحاً حتى 5 مساءً، وسنرد عليك أول ما نبدأ 🌙", "e.g. Our team is available 9am–5pm; we'll reply as soon as we're back 🌙")} />
                  </div>}
                </div>
              );
            })}
          </div>
          <div className="flex items-center gap-3"><Btn onClick={saveRouting}>{bi("حفظ", "Save")}</Btn>{msg && <span className="text-[13px] font-bold text-au-teal">{msg}</span>}</div>
        </div>
      )}

      {tab === "calls" && (
        <div className="grid gap-3">
          <p className="m-0 text-[12.5px] leading-relaxed text-ink-3">{bi("يظهر زر الاتصال للعملاء في محادثة واتساب. المكالمة ترنّ هنا عند كل من يرى المحادثة، ويرد أول موظف من المتصفح بالميكروفون. الفائتة تصل العميل برسالتك وتظهر في الصندوق.", "Customers see a call button in the WhatsApp chat. The call rings here for everyone who can see the conversation, and the first agent answers from the browser with their microphone. Missed calls get your message and show in the inbox.")}</p>
          {msg && <span className="text-[13px] font-bold text-au-teal">{msg}</span>}
          {(P.bots || []).filter((b) => b.channel === "whatsapp").map((b) => {
            const cc = calls[b.id] || {};
            return (
              <div key={b.id} className="grid gap-2 rounded-2xl bg-ov/[0.035] p-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <b className="text-[13px] text-ink" dir="auto">{b.name}</b>
                  <label className="flex items-center gap-2 text-[13px] text-ink-2"><input type="checkbox" checked={!!cc.enabled} onChange={(e) => setCalls({ ...calls, [b.id]: { ...cc, enabled: e.target.checked } })} />{bi("استقبال المكالمات", "Receive calls")}</label>
                </div>
                <Textarea dir="auto" rows={2} maxLength={500} value={cc.missed_text || ""} onChange={(e) => setCalls({ ...calls, [b.id]: { ...cc, missed_text: e.target.value } })}
                          placeholder={bi("رسالة المكالمة الفائتة (اختياري): فاتتنا مكالمتك 🙏 اكتب لنا هنا وسنرد فوراً", "Missed-call message (optional): Sorry we missed your call 🙏 write to us here and we'll reply right away")} />
                <Btn sm className="justify-self-start" onClick={() => saveCalls(b)}>{bi("حفظ", "Save")}</Btn>
              </div>
            );
          })}
        </div>
      )}
    </Modal>
  );
}

/* ------------------------------------------------------------ الصفحة */
export default function SharedInbox() {
  const [view, setView] = useState("open");
  const [bot, setBot] = useState("");
  const [q, setQ] = useState("");
  const [data, setData] = useState({ rows: [], counts: {} });
  const [cur, setCur] = useState(null);           // {bot_id, peer}
  const [msgs, setMsgs] = useState([]);
  const [conv, setConv] = useState(null);
  const [contact, setContact] = useState(null);
  const [lastIn, setLastIn] = useState(0);
  const [now, setNow] = useState(Math.floor(Date.now() / 1000));
  const [teams, setTeams] = useState(P.allTeams || []);
  const [canned, setCanned] = useState(P.canned || []);
  const [settings, setSettings] = useState(false);
  const [side, setSide] = useState(true);
  const [payOpen, setPayOpen] = useState(false);
  const lastId = useRef(0);
  const scroller = useRef(null);

  const loadList = useCallback(async () => {
    const r = await get(`/api/inbox?view=${encodeURIComponent(view)}&bot=${bot}&q=${encodeURIComponent(q)}`);
    if (r.ok) setData(r);
  }, [view, bot, q]);
  const loadThread = useCallback(async (fresh) => {
    if (!cur) return;
    const r = await get(`/api/inbox/thread?bot=${cur.bot_id}&peer=${encodeURIComponent(cur.peer)}&after=${fresh ? 0 : lastId.current}`);
    if (!r.ok) { if (r.status === 404) setCur(null); return; }
    setConv(r.conv); setLastIn(r.lastIn || 0); setNow(r.now);
    if (fresh) { setMsgs(r.messages || []); setContact(r.contact ? { ...r.contact, source: r.source } : (r.source ? { source: r.source } : null)); }
    else if (r.messages?.length) setMsgs((x) => [...x, ...r.messages]);
    const all = r.messages || [];
    if (all.length) lastId.current = all[all.length - 1].id;
  }, [cur]);

  usePoll(loadList, 6000, [loadList]);
  useEffect(() => { lastId.current = 0; setMsgs([]); setContact(null); if (cur) loadThread(true); }, [cur, loadThread]);
  usePoll(() => loadThread(false), 3500, [loadThread]);
  useEffect(() => { const el = scroller.current; if (el) el.scrollTop = el.scrollHeight; }, [msgs.length, cur]);
  useEffect(() => {  // رابط قابل للمشاركة: ?bot=&peer=
    const u = new URLSearchParams(location.search);
    if (u.get("bot") && u.get("peer")) setCur({ bot_id: Number(u.get("bot")), peer: u.get("peer") });
  }, []);
  useEffect(() => {
    const url = new URL(location.href);
    if (cur) { url.searchParams.set("bot", cur.bot_id); url.searchParams.set("peer", cur.peer); }
    else { url.searchParams.delete("bot"); url.searchParams.delete("peer"); }
    history.replaceState(null, "", url);
  }, [cur]);

  const after = (r) => { if (r.ok && r.conv) setConv(r.conv); loadList(); return r; };
  const body = () => ({ bot: cur.bot_id, peer: cur.peer });
  const send = async (text, asset) => { const r = await call("/api/inbox/send", { ...body(), text, asset_id: asset || undefined }); if (r.ok) loadThread(false); return after(r); };
  const note = async (text) => { const r = await call("/api/inbox/note", { ...body(), text }); if (r.ok) loadThread(false); return r; };
  const assign = async (x) => after(await call("/api/inbox/assign", { ...body(), ...x }));
  const status = async (s) => after(await call("/api/inbox/status", { ...body(), status: s }));
  const mode = async (m) => after(await call("/api/inbox/mode", { ...body(), mode: m }));

  const row = data.rows.find((c) => cur && c.bot_id === cur.bot_id && c.peer === cur.peer);
  const title = conv?.name || row?.name || (cur ? peerLabel(cur.peer) : "");
  const isMeta = cur && /^(wa|fb|ig):/.test(cur.peer);
  const windowClosed = Boolean(isMeta && lastIn && now - lastIn > (P.windowSec || 86400));
  const c = data.counts || {};
  const views = useMemo(() => [
    ["open", bi("كل المفتوحة", "All open"), "inbox"], ["mine", bi("لي", "Mine"), "user"],
    ["unassigned", bi("تنتظر موظفاً", "Unassigned"), "clock"], ["bot", bi("مع البوت", "With the bot"), "bot"],
    ["mentions", bi("إشاراتي", "Mentions"), "chat"], ["pending", bi("معلّقة", "Pending"), "pending"],
    ["resolved", bi("مغلقة", "Resolved"), "check"],
  ], []);

  return (
    <>
      <PageHead icon="inbox" title={bi("الصندوق المشترك", "Team inbox")}
                sub={bi("كل محادثات قنواتك لفريقك: إسناد وفِرق بالتناوب، ملاحظات داخلية، وردود جاهزة.", "Every channel's conversations for your team: assignment, round-robin teams, internal notes and canned replies.")}
                actions={P.canManage && <Btn variant="ghost" sm icon="settings" onClick={() => setSettings(true)}>{bi("الإعدادات", "Settings")}</Btn>} />
      <div className="grid gap-3 lg:grid-cols-[300px_minmax(0,1fr)] xl:grid-cols-[190px_300px_minmax(0,1fr)] 2xl:grid-cols-[190px_310px_minmax(0,1fr)_280px]">
        {/* العروض — عمود في الشاشات العريضة، وقائمة منسدلة فوق المحادثات فيما دونها */}
        <Card className="hidden !p-2 xl:block">
          <nav className="flex gap-1 overflow-x-auto lg:flex-col">
            {[...views, ...(P.teams || []).map((tm) => [`team:${tm.id}`, tm.name, "users"])].map(([k, l, i]) => (
              <button key={k} type="button" onClick={() => { setView(k); setCur(null); }}
                      className={`flex shrink-0 cursor-pointer items-center justify-between gap-2 rounded-xl border-0 px-3 py-2 text-start text-[13px] font-bold ${view === k ? "bg-au-violet/20 text-ink" : "bg-transparent text-ink-2 hover:bg-ov/[0.05]"}`}>
                <span className="flex min-w-0 items-center gap-2"><Icon name={i} size={14} className="shrink-0 text-au-cyan" /><span className="truncate" dir="auto">{l}</span></span>
                {c[k] > 0 && <span className="tnum text-[11.5px] text-ink-3">{num(c[k])}</span>}
              </button>
            ))}
          </nav>
        </Card>

        {/* القائمة */}
        <Card className={"flex flex-col !p-2 " + (cur ? "hidden lg:flex" : "")}>
          <div className="grid gap-2 p-1">
            <Select className="xl:hidden" value={view} onChange={(e) => { setView(e.target.value); setCur(null); }}>
              {[...views, ...(P.teams || []).map((tm) => [`team:${tm.id}`, tm.name])].map(([k, l]) => (
                <option key={k} value={k}>{l}{c[k] ? ` (${c[k]})` : ""}</option>
              ))}
            </Select>
            <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder={bi("بحث بالاسم أو الرقم أو النص", "Search name, number or text")} className="!py-2" />
            {(P.bots || []).length > 1 && (
              <Select value={bot} onChange={(e) => setBot(e.target.value)}>
                <option value="">{bi("كل القنوات", "All channels")}</option>
                {P.bots.map((b) => <option key={b.id} value={String(b.id)}>{b.name}</option>)}
              </Select>
            )}
          </div>
          <div className="mt-1 flex max-h-[68vh] flex-col gap-0.5 overflow-y-auto">
            {data.rows.map((x) => <Row key={x.bot_id + x.peer} c={x} active={cur && cur.bot_id === x.bot_id && cur.peer === x.peer} onOpen={(r) => setCur({ bot_id: r.bot_id, peer: r.peer })} />)}
            {!data.rows.length && <Empty icon="inbox" title={bi("لا محادثات هنا", "No conversations here")} />}
          </div>
        </Card>

        {/* المحادثة */}
        <Card className={"flex min-h-[70vh] flex-col !p-0 " + (cur ? "" : "hidden lg:flex")}>
          {!cur ? <div className="grid flex-1 place-items-center p-8"><Empty icon="inbox" title={t("inbox_pick")} /></div> : <>
            <div className="flex flex-wrap items-center justify-between gap-2 px-4 py-3 shadow-[inset_0_-1px_0_rgb(var(--ov-rgb)/0.08)]">
              <div className="flex min-w-0 items-center gap-2">
                <Btn sm variant="ghost" icon="back" className="lg:hidden" onClick={() => setCur(null)} aria-label={t("inbox_back")} />
                <div className="min-w-0">
                  <div className="truncate text-[15px] font-extrabold text-ink" dir="auto">{title}</div>
                  <div className="text-[11.5px] text-ink-3"><span dir="ltr">{peerLabel(cur.peer)}</span>{row && ` · ${row.bot_name}`}</div>
                </div>
              </div>
              <div className="flex flex-wrap items-center gap-1.5">
                {conv && <Pill tone={STATUS[conv.status || "open"][1]}>{STATUS[conv.status || "open"][0]}</Pill>}
                {conv?.mode === "human" ? <Btn sm variant="ghost" icon="bot" onClick={() => mode("bot")}>{t("inbox_return")}</Btn>
                  : P.canReply && <Btn sm variant="ghost" icon="users" onClick={() => mode("human")}>{t("inbox_takeover")}</Btn>}
                <CallButton cur={cur} name={title} windowClosed={windowClosed} />
                {P.pay && P.canReply && !windowClosed && cur.peer !== "wa:" && <Btn sm variant="ghost" icon="card" onClick={() => setPayOpen(true)}>{bi("طلب دفع", "Request payment")}</Btn>}
                {conv?.assignee_id !== P.me?.id && <Btn sm variant="ghost" icon="user" onClick={() => assign({ user: P.me.id, team: conv?.team_id || null })}>{bi("استلمها", "Take it")}</Btn>}
                {conv?.status !== "resolved"
                  ? <Btn sm variant="green" icon="check" onClick={() => status("resolved")}>{bi("إغلاق", "Resolve")}</Btn>
                  : <Btn sm variant="ghost" icon="refresh" onClick={() => status("open")}>{bi("إعادة فتح", "Reopen")}</Btn>}
                <Btn sm variant="ghost" className="hidden 2xl:inline-flex" onClick={() => setSide(!side)} aria-label={bi("لوحة جهة الاتصال", "Contact panel")}><Icon name="user" size={14} /></Btn>
              </div>
            </div>
            <div ref={scroller} className="flex flex-1 flex-col gap-2.5 overflow-y-auto px-4 py-4" style={{ maxHeight: "56vh" }} aria-live="polite">
              {msgs.map((m) => <Bubble key={m.id} m={m} botId={cur.bot_id} />)}
              {!msgs.length && <div className="m-auto text-[13px] text-ink-3">…</div>}
            </div>
            {cur.peer !== "wa:" && <Composer conv={{ ...conv, bot_id: cur.bot_id, peer: cur.peer }} contact={contact} canned={canned} windowClosed={windowClosed} onSend={send} onNote={note} />}
            <details className="border-t border-ov/10 2xl:hidden">
              <summary className="cursor-pointer px-4 py-2.5 text-[13px] font-bold text-ink-2">{bi("الحالة والإسناد وجهة الاتصال", "Status, assignment & contact")}</summary>
              <ContactPanel conv={conv} contact={contact} teams={teams} onAssign={assign} onStatus={status} />
            </details>
          </>}
        </Card>

        {/* لوحة جهة الاتصال (الشاشات الواسعة) */}
        {cur && side && <Card className="hidden !p-0 2xl:block"><ContactPanel conv={conv} contact={contact} teams={teams} onAssign={assign} onStatus={status} /></Card>}
      </div>
      {P.callsOn && <CallBar onOpen={(c) => setCur(c)} />}
      {cur && <PayRequest open={payOpen} onClose={() => setPayOpen(false)} cur={cur} onSent={() => loadThread(false)} />}
      {P.canManage && <Settings open={settings} onClose={() => setSettings(false)} teams={teams} setTeams={setTeams} canned={canned} setCanned={setCanned} />}
    </>
  );
}
