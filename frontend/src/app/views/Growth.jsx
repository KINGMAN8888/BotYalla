/* النمو والإعلانات — المرحلة 7: روابط التتبّع وQR · تقرير إعلانات Click-to-WhatsApp و Conversions API ·
   ودجت الموقع (زر واتساب + محادثة ويب مع البوت). الإحصاءات من الخادم؛ الأسرار (رمز CAPI) لا تعود أبداً. */
import { useState } from "react";
import { BY, P, bi, AR, Icon, Card, Btn, Field, Input, Textarea, Select, Pill, Empty, PageHead, num, Modal, Tabs, Kpi, Toggle } from "../kit.jsx";

async function call(url, body, method = "POST") {
  try {
    const r = await fetch(url, method === "GET" ? { headers: { Accept: "application/json" } } : {
      method, headers: { "Content-Type": "application/json", "X-CSRF-Token": BY.csrf }, body: JSON.stringify(body || {}),
    });
    const j = await r.json().catch(() => ({ ok: false, error: "network" }));
    return { status: r.status, ...j };
  } catch { return { ok: false, error: "network" }; }
}
const ERR = {
  name: bi("اكتب اسماً", "Enter a name"), bot_link: bi("القناة بلا رقم/اسم مستخدم معروف بعد — أكمل ربطها أولاً", "This channel has no known number/username yet — finish connecting it first"),
  limit: bi("وصلت للحد الأقصى", "Limit reached"), color: bi("لون غير صالح", "Invalid color"), domains: bi("نطاق غير صالح", "Invalid domain"),
  bot: bi("اختر البوت الذي يرد في محادثة الموقع", "Pick the bot that answers website chat"), wa_bot: bi("اختر رقم واتساب لزر واتساب", "Pick a WhatsApp number for the WhatsApp button"),
  dataset: bi("Dataset ID أرقام فقط", "Dataset ID must be digits"), token: bi("رمز وصول غير صالح", "Invalid access token"), role: bi("للمالك والمدير فقط", "Owners and admins only"),
  network: bi("تعذّر الاتصال", "Connection failed"),
};
const errOf = (r) => ERR[r.error] || bi("حدث خطأ", "Something went wrong");
const pct = (a, b) => (b ? Math.round((a / b) * 100) : 0);
const fmt = (ts) => (ts ? new Date(ts * 1000).toLocaleDateString(AR ? "ar-EG" : "en-GB", { day: "2-digit", month: "short" }) : "—");
const copy = (s) => { try { navigator.clipboard.writeText(s); } catch { /* */ } };


/* ------------------------------------------------------------ روابط التتبّع */
function Links() {
  const [links, setLinks] = useState(P.links || []);
  const [edit, setEdit] = useState(null);
  const [err, setErr] = useState("");
  const [copied, setCopied] = useState(null);
  const bots = (P.bots || []).filter((b) => b.linkable);
  const save = async () => {
    setErr("");
    const r = edit.id ? await call(`/api/growth/links/${edit.id}/save`, edit) : await call("/api/growth/links", edit);
    if (!r.ok) { setErr(errOf(r)); return; }
    setLinks(r.links); setEdit(null);
  };
  const del = async (l) => {
    if (!window.confirm(bi(`حذف «${l.name}»؟ الرابط المطبوع يتوقّف.`, `Delete “${l.name}”? Printed links stop working.`))) return;
    const r = await call(`/api/growth/links/${l.id}/delete`); if (r.ok) setLinks(r.links);
  };
  const tot = links.reduce((a, l) => ({ c: a.c + l.clicks, v: a.v + l.conversations, d: a.d + l.leads }), { c: 0, v: 0, d: 0 });
  return <>
    <div className="mb-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
      <Kpi icon="link" label={bi("روابط", "Links")} value={num(links.length)} />
      <Kpi icon="arrow" label={bi("نقرات", "Clicks")} value={num(tot.c)} />
      <Kpi icon="chat" label={bi("محادثات", "Conversations")} value={num(tot.v)} sub={`${pct(tot.v, tot.c)}% ${bi("من النقرات", "of clicks")}`} />
      <Kpi icon="download" label={bi("إدخالات", "Leads")} value={num(tot.d)} sub={`${pct(tot.d, tot.v)}% ${bi("من المحادثات", "of chats")}`} />
    </div>
    <Card>
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <b className="text-[15px] text-ink">{bi("روابط التتبّع", "Tracking links")}</b>
        {P.canManage && !!bots.length && <Btn sm icon="plus" onClick={() => setEdit({ bot: bots[0].id, name: "", text: "" })}>{bi("رابط جديد", "New link")}</Btn>}
      </div>
      {!links.length ? (
        <Empty icon="link" title={bi("لا روابط بعد", "No links yet")}
               text={bi("رابط لكل منشور أو حملة أو ملصق: يفتح المحادثة برسالة جاهزة، ويقول لك كم نقرة وكم محادثة وكم عميلاً جاء منه.", "One link per post, campaign or poster: it opens the chat with a ready message and tells you clicks, chats and leads.")} />
      ) : (
        <div className="grid gap-2">
          {links.map((l) => (
            <div key={l.id} className="flex min-w-0 flex-wrap items-center justify-between gap-3 rounded-2xl bg-ov/[0.035] px-4 py-3">
              <div className="min-w-0">
                <b className="block truncate text-ink" dir="auto">{l.name}</b>
                <span className="block truncate text-[12px] text-ink-3" dir="ltr">{l.url}</span>
                <span className="text-[11.5px] text-ink-3">{l.bot_name}{l.text && ` · «${l.text}»`}</span>
              </div>
              <div className="flex flex-wrap items-center gap-4 text-[12.5px]">
                {[[l.clicks, bi("نقرات", "Clicks")], [l.conversations, bi("محادثات", "Chats")], [l.leads, bi("إدخالات", "Leads")]].map(([v, t], i) => (
                  <span key={i} className="text-center"><b className="tnum block text-[16px] text-ink">{num(v)}</b><span className="text-ink-3">{t}</span></span>
                ))}
                <Btn sm variant="ghost" icon="copy" onClick={() => { copy(l.url); setCopied(l.id); setTimeout(() => setCopied(null), 1500); }}>{copied === l.id ? bi("نُسخ ✓", "Copied ✓") : bi("نسخ", "Copy")}</Btn>
                <Btn sm variant="ghost" icon="download" href={`${l.qr}?dl=1`}>QR</Btn>
                {P.canManage && <>
                  <Btn sm variant="ghost" icon="edit" onClick={() => setEdit({ id: l.id, name: l.name, text: l.text })} aria-label={bi("تعديل", "Edit")} />
                  <Btn sm variant="ghost" onClick={() => del(l)} aria-label={bi("حذف", "Delete")}><Icon name="trash" size={14} /></Btn>
                </>}
              </div>
            </div>
          ))}
        </div>
      )}
    </Card>
    <Modal open={!!edit} onClose={() => setEdit(null)} title={edit?.id ? bi("تعديل الرابط", "Edit link") : bi("رابط تتبّع جديد", "New tracking link")} icon="link"
           footer={<><Btn variant="ghost" onClick={() => setEdit(null)}>{bi("إلغاء", "Cancel")}</Btn><Btn onClick={save}>{bi("حفظ", "Save")}</Btn></>}>
      {edit && <div className="grid gap-3">
        {err && <div className="rounded-xl bg-red-400/10 px-3 py-2 text-[13px] font-bold text-red-400">{err}</div>}
        <Field label={bi("الاسم (لك فقط)", "Name (for you)")}><Input dir="auto" maxLength={80} value={edit.name} placeholder={bi("مثل: منشور إنستجرام — عروض رمضان", "e.g. Instagram post — Ramadan offers")} onChange={(e) => setEdit({ ...edit, name: e.target.value })} /></Field>
        {!edit.id && <Field label={bi("القناة", "Channel")}>
          <Select value={String(edit.bot)} onChange={(e) => setEdit({ ...edit, bot: Number(e.target.value) })}>{bots.map((b) => <option key={b.id} value={String(b.id)}>{b.name}</option>)}</Select>
        </Field>}
        <Field label={bi("الرسالة الجاهزة (واتساب)", "Pre-filled message (WhatsApp)")} hint={bi("يجدها العميل مكتوبة ويضغط إرسال. يُضاف في آخرها رمز قصير يُحذف تلقائياً قبل أن يراه البوت أو فريقك.", "The customer finds it typed and taps send. A short code is appended and removed automatically before the bot or your team see it.")}>
          <Input dir="auto" maxLength={300} value={edit.text} placeholder={bi("مرحبا، أريد عروض العمرة", "Hi, I'd like the Umrah offers")} onChange={(e) => setEdit({ ...edit, text: e.target.value })} />
        </Field>
        <p className="m-0 text-[12px] text-ink-3">{bi("تقدر تشغّل فلو خاص بهذا الرابط: في باني الفلو اختر المشغّل «رابط تتبّع بعينه».", "You can start a dedicated flow for this link: in the flow builder pick the “Specific tracking link” trigger.")}</p>
      </div>}
    </Modal>
  </>;
}

/* ------------------------------------------------------------ الإعلانات و Conversions API */
function Ads() {
  const [ads, setAds] = useState(P.ads || []);
  const [log, setLog] = useState(P.capiLog || []);
  const [days, setDays] = useState(30);
  const [bots, setBots] = useState(P.bots || []);
  const [capi, setCapi] = useState(null);
  const [err, setErr] = useState("");
  const load = async (d) => { setDays(d); const r = await call(`/api/growth/ads?days=${d}`, null, "GET"); if (r.ok) { setAds(r.ads); setLog(r.capiLog); } };
  const saveCapi = async () => {
    setErr("");
    const r = await call("/api/growth/capi", capi);
    if (!r.ok) { setErr(errOf(r)); return; }
    setBots(r.bots); setCapi(null);
  };
  const tot = ads.reduce((a, x) => ({ p: a.p + x.people, l: a.l + x.leads, c: a.c + x.conversions }), { p: 0, l: 0, c: 0 });
  const wa = bots.filter((b) => b.capi);
  return <>
    <div className="mb-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
      <Kpi icon="megaphone" label={bi("إعلانات جلبت محادثات", "Ads with chats")} value={num(ads.length)} />
      <Kpi icon="users" label={bi("عملاء من الإعلانات", "Customers from ads")} value={num(tot.p)} />
      <Kpi icon="download" label={bi("إدخالات", "Leads")} value={num(tot.l)} sub={`${pct(tot.l, tot.p)}%`} />
      <Kpi icon="bolt" label={bi("تحويلات أُرسلت لـ Meta", "Conversions sent to Meta")} value={num(tot.c)} />
    </div>
    <Card className="mb-4">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <b className="text-[15px] text-ink">{bi("أداء إعلانات Click-to-WhatsApp", "Click-to-WhatsApp ad performance")}</b>
        <Select className="!w-auto" value={String(days)} onChange={(e) => load(Number(e.target.value))}>
          {[7, 30, 90].map((d) => <option key={d} value={String(d)}>{bi(`آخر ${d} يوماً`, `Past ${d} days`)}</option>)}
        </Select>
      </div>
      {!ads.length ? (
        <Empty icon="megaphone" title={bi("لا نقرات إعلانات بعد", "No ad clicks yet")}
               text={bi("أي إعلان على فيسبوك/إنستجرام بزر «إرسال رسالة واتساب» لرقمك يظهر هنا تلقائياً: كم عميلاً جاء منه وكم أصبح إدخالاً. وتقدر تبدأ له فلو خاص بمشغّل «نقرة إعلان».", "Any Facebook/Instagram ad with a “Send WhatsApp message” button to your number shows up here automatically: how many customers it brought and how many became leads. You can also start a dedicated flow with the “Ad click” trigger.")} />
      ) : (
        <div className="-mx-2 overflow-x-auto px-2">
          <table className="w-full border-collapse text-[13px]">
            <thead><tr>{[bi("الإعلان", "Ad"), bi("القناة", "Channel"), bi("عملاء", "Customers"), bi("إدخالات", "Leads"), bi("تحويلات", "Conversions"), bi("آخر نقرة", "Last click")].map((h, i) => (
              <th key={i} className="whitespace-nowrap px-3 py-2.5 text-start text-[11px] font-extrabold uppercase tracking-wider text-ink-3 shadow-[inset_0_-1px_0_rgb(var(--ov-rgb)/0.08)]">{h}</th>))}</tr></thead>
            <tbody>{ads.map((x) => (
              <tr key={x.bot_id + x.source_id}>
                <td className="px-3 py-2.5 shadow-[inset_0_-1px_0_rgb(var(--ov-rgb)/0.05)]">
                  <b className="block max-w-[260px] truncate text-ink" dir="auto">{x.headline || bi("بلا عنوان", "Untitled")}</b>
                  <span className="text-[11.5px] text-ink-3" dir="ltr">{x.source_type} · {x.source_id}</span>
                  {/^https:\/\//.test(x.source_url || "") && <a href={x.source_url} target="_blank" rel="noopener noreferrer" className="ms-2 text-[11.5px] text-au-cyan">↗</a>}
                </td>
                <td className="px-3 py-2.5 text-ink-2 shadow-[inset_0_-1px_0_rgb(var(--ov-rgb)/0.05)]">{x.bot_name}</td>
                <td className="tnum px-3 py-2.5 shadow-[inset_0_-1px_0_rgb(var(--ov-rgb)/0.05)]">{num(x.people)}</td>
                <td className="tnum px-3 py-2.5 shadow-[inset_0_-1px_0_rgb(var(--ov-rgb)/0.05)]">{num(x.leads)} <span className="text-ink-3">{pct(x.leads, x.people)}%</span></td>
                <td className="tnum px-3 py-2.5 shadow-[inset_0_-1px_0_rgb(var(--ov-rgb)/0.05)]">{num(x.conversions)}</td>
                <td className="px-3 py-2.5 text-ink-3 shadow-[inset_0_-1px_0_rgb(var(--ov-rgb)/0.05)]">{fmt(x.last_at)}</td>
              </tr>))}</tbody>
          </table>
        </div>
      )}
    </Card>
    <Card>
      <b className="mb-1 block text-[15px] text-ink">Conversions API</b>
      <p className="mb-3 mt-0 text-[12.5px] leading-relaxed text-ink-3">{bi("نرسل لـ Meta من تحوّل من عملاء الإعلانات (إدخال أو شراء) فيتعلّم الإعلان إيجاد عملاء مثلهم ويخفض تكلفتك. يُرسل فقط لمن جاء من إعلان خلال 7 أيام. التحويل يُحدَّد في بطاقة «هدف» بالفلو، والإدخال يُرسل تلقائياً لو فعّلته.", "We tell Meta which ad customers converted (lead or purchase) so the ad learns to find more like them and lowers your cost. Only for customers who came from an ad within 7 days. Conversions are set on a flow's “Goal” card; leads are sent automatically if you enable it.")}</p>
      {wa.map((b) => (
        <div key={b.id} className="mb-2 flex flex-wrap items-center justify-between gap-2 rounded-xl bg-ov/[0.035] px-3 py-2.5">
          <span className="text-[13px] text-ink" dir="auto">{b.name}</span>
          <span className="flex items-center gap-2">
            {b.capi.dataset ? <Pill tone="on" dot>{bi("متصل", "Connected")} · {b.capi.dataset}{b.capi.lead ? bi(" · الإدخالات", " · leads") : ""}</Pill> : <Pill tone="mute">{bi("غير متصل", "Not connected")}</Pill>}
            {P.canManage && <Btn sm variant="ghost" icon="settings" onClick={() => setCapi({ bot: b.id, dataset: b.capi.dataset, token: "", lead: b.capi.lead, hasToken: b.capi.token })}>{bi("إعداد", "Set up")}</Btn>}
          </span>
        </div>
      ))}
      {!!log.length && (
        <details className="mt-3 text-[12.5px]">
          <summary className="cursor-pointer font-bold text-ink-2">{bi("آخر ما أُرسل", "Recent events")}</summary>
          <div className="mt-2 grid gap-1">{log.map((e) => (
            <div key={e.id} className="flex flex-wrap justify-between gap-2 rounded-lg bg-ov/[0.03] px-2.5 py-1.5">
              <span>{e.ok ? "✅" : "⚠️"} {e.event}{e.value ? ` · ${e.value} ${e.currency}` : ""} · {e.bot_name}</span>
              <span className="text-ink-3">{e.error || fmt(e.created_at)}</span>
            </div>))}</div>
        </details>
      )}
    </Card>
    <Modal open={!!capi} onClose={() => setCapi(null)} title="Conversions API" icon="settings"
           footer={<><Btn variant="ghost" onClick={() => setCapi(null)}>{bi("إلغاء", "Cancel")}</Btn><Btn onClick={saveCapi}>{bi("حفظ", "Save")}</Btn></>}>
      {capi && <div className="grid gap-3">
        {err && <div className="rounded-xl bg-red-400/10 px-3 py-2 text-[13px] font-bold text-red-400">{err}</div>}
        <Field label="Dataset ID" hint={bi("من Events Manager ← مصدر البيانات المرتبط بحساب واتساب للأعمال. فارغ = إيقاف ومسح الإعداد.", "From Events Manager → the dataset linked to your WhatsApp Business account. Empty = turn off and clear.")}>
          <Input dir="ltr" inputMode="numeric" value={capi.dataset} onChange={(e) => setCapi({ ...capi, dataset: e.target.value.replace(/\D/g, "") })} />
        </Field>
        <Field label={bi("رمز الوصول (Access token)", "Access token")} hint={capi.hasToken ? bi("محفوظ ولا يُعرض — اتركه فارغاً للإبقاء عليه", "Saved and never shown — leave empty to keep it") : bi("رمز System User بصلاحية الإعلانات", "A System User token with ads permissions")}>
          <Input dir="ltr" type="password" autoComplete="off" value={capi.token} onChange={(e) => setCapi({ ...capi, token: e.target.value.trim() })} />
        </Field>
        <label className="flex items-center gap-2 text-[13px] text-ink-2"><Toggle checked={!!capi.lead} onChange={(v) => setCapi({ ...capi, lead: v })} label="" />{bi("أرسل «LeadSubmitted» تلقائياً عند حفظ إدخال", "Send “LeadSubmitted” automatically when a lead is saved")}</label>
      </div>}
    </Modal>
  </>;
}

/* ------------------------------------------------------------ ودجت الموقع */
const WDEF = { mode: "both", color: "#25D366", position: "right", label: "", greeting: "", greeting_delay: 3, title: "", subtitle: "",
  welcome: "", wa_text: "", lang: AR ? "ar" : "en", icebreakers: [], domains: [], show_mobile: true, show_desktop: true };

function WidgetPreview({ s }) {
  const side = s.position === "left" ? "left-3" : "right-3";
  return (
    <div className="relative h-[330px] overflow-hidden rounded-2xl bg-[linear-gradient(160deg,#eef2f7,#dfe6ee)]" dir={s.lang === "en" ? "ltr" : "rtl"}>
      <div className="p-4 text-[12px] text-slate-500">{bi("معاينة موقعك", "Your website preview")}</div>
      {s.mode !== "whatsapp" && (
        <div className={`absolute bottom-[72px] ${side} w-[250px] overflow-hidden rounded-2xl bg-white text-slate-900 shadow-xl`}>
          <div className="px-3 py-2.5 text-white" style={{ background: s.color }}><b className="block text-[13px]">{s.title || bi("اسم نشاطك", "Your business")}</b><small className="text-[11px] opacity-90">{s.subtitle}</small></div>
          <div className="grid gap-1.5 bg-slate-100 p-2.5 text-[12px]">
            {s.welcome && <div className="max-w-[85%] justify-self-start rounded-xl bg-white px-2.5 py-1.5">{s.welcome}</div>}
            <div className="flex flex-wrap gap-1">{(s.icebreakers || []).map((x) => <span key={x} className="rounded-full border px-2 py-0.5 text-[11px]" style={{ borderColor: s.color, color: s.color }}>{x}</span>)}</div>
          </div>
        </div>
      )}
      {s.greeting && s.mode === "whatsapp" && <div className={`absolute bottom-[72px] ${side} w-[200px] rounded-xl bg-white px-3 py-2 text-[12px] text-slate-900 shadow-lg`}>{s.greeting}</div>}
      <div className={`absolute bottom-3 ${side} grid size-12 place-items-center rounded-full text-white shadow-lg`} style={{ background: s.color }}><Icon name={s.mode === "whatsapp" ? "phone" : "chat"} size={22} /></div>
    </div>
  );
}

function Widgets() {
  const [items, setItems] = useState(P.widgets || []);
  const [edit, setEdit] = useState(null);
  const [err, setErr] = useState("");
  const [copied, setCopied] = useState(null);
  const bots = P.bots || [];
  const waBots = bots.filter((b) => b.channel === "whatsapp");
  const s = edit?.settings || WDEF;
  const setS = (p) => setEdit({ ...edit, settings: { ...s, ...p } });
  const save = async () => {
    setErr("");
    const r = await call("/api/growth/widgets/save", { id: edit.id, name: edit.name, bot: edit.bot, wa_bot: edit.wa_bot, settings: s });
    if (!r.ok) { setErr(errOf(r)); return; }
    setItems(r.widgets); setEdit(null);
  };
  const del = async (w) => {
    if (!window.confirm(bi(`حذف «${w.name}»؟ يختفي من موقعك فوراً.`, `Delete “${w.name}”? It disappears from your site immediately.`))) return;
    const r = await call("/api/growth/widgets/delete", { id: w.id }); if (r.ok) setItems(r.widgets);
  };
  const MODES = [["both", bi("محادثة مع البوت + زر واتساب", "Chat with the bot + WhatsApp button")], ["chat", bi("محادثة مع البوت فقط", "Bot chat only")], ["whatsapp", bi("زر واتساب فقط", "WhatsApp button only")]];
  return <>
    <Card>
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <b className="text-[15px] text-ink">{bi("ودجت الموقع", "Website widget")}</b>
        {P.canManage && !!bots.length && <Btn sm icon="plus" onClick={() => setEdit({ name: bi("موقعي", "My website"), bot: bots[0]?.id, wa_bot: waBots[0]?.id, settings: { ...WDEF } })}>{bi("ودجت جديد", "New widget")}</Btn>}
      </div>
      {!items.length ? (
        <Empty icon="globe" title={bi("لا ودجت بعد", "No widget yet")}
               text={bi("سطر واحد في موقعك: زر واتساب، أو محادثة مباشرة مع بوتك (نفس الفلوهات والذكاء) تصل للصندوق المشترك، ويقدر الزائر يكمل على واتساب.", "One line on your site: a WhatsApp button, or a live chat with your bot (same flows and AI) that lands in the Team inbox — and visitors can continue on WhatsApp.")} />
      ) : (
        <div className="grid gap-2">
          {items.map((w) => (
            <div key={w.id} className="min-w-0 rounded-2xl bg-ov/[0.035] px-4 py-3">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div className="min-w-0"><b className="block text-ink" dir="auto">{w.name}</b>
                  <span className="text-[12px] text-ink-3">{MODES.find((m) => m[0] === (w.settings.mode || "both"))?.[1]}{w.settings.domains?.length ? ` · ${w.settings.domains.join("، ")}` : ""}</span></div>
                <div className="flex flex-wrap items-center gap-4 text-[12.5px]">
                  {[[w.views, bi("زيارات", "Visits")], [w.chats, bi("محادثات ويب", "Web chats")], [w.wa_clicks, bi("نقرات واتساب", "WhatsApp clicks")]].map(([v, t], i) => (
                    <span key={i} className="text-center"><b className="tnum block text-[16px] text-ink">{num(v)}</b><span className="text-ink-3">{t}</span></span>
                  ))}
                  {P.canManage && <>
                    <Btn sm variant="ghost" icon="edit" onClick={() => setEdit({ id: w.id, name: w.name, bot: w.bot_id, wa_bot: w.wa_bot_id, settings: { ...WDEF, ...w.settings } })}>{bi("تعديل", "Edit")}</Btn>
                    <Btn sm variant="ghost" onClick={() => del(w)} aria-label={bi("حذف", "Delete")}><Icon name="trash" size={14} /></Btn>
                  </>}
                </div>
              </div>
              <div className="mt-2 flex items-center gap-2">
                <code dir="ltr" className="min-w-0 flex-1 truncate rounded-lg bg-sink/40 px-2.5 py-1.5 text-[11.5px] text-ink-2">{w.embed}</code>
                <Btn sm variant="ghost" icon="copy" onClick={() => { copy(w.embed); setCopied(w.id); setTimeout(() => setCopied(null), 1500); }}>{copied === w.id ? bi("نُسخ ✓", "Copied ✓") : bi("نسخ الكود", "Copy code")}</Btn>
              </div>
            </div>
          ))}
        </div>
      )}
    </Card>
    <Modal open={!!edit} wide onClose={() => setEdit(null)} title={edit?.id ? bi("تعديل الودجت", "Edit widget") : bi("ودجت جديد", "New widget")} icon="globe"
           footer={<><Btn variant="ghost" onClick={() => setEdit(null)}>{bi("إلغاء", "Cancel")}</Btn><Btn onClick={save}>{bi("حفظ", "Save")}</Btn></>}>
      {edit && <div className="grid gap-4 md:grid-cols-[1fr_280px]">
        <div className="grid content-start gap-3">
          {err && <div className="rounded-xl bg-red-400/10 px-3 py-2 text-[13px] font-bold text-red-400">{err}</div>}
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label={bi("الاسم", "Name")}><Input dir="auto" maxLength={60} value={edit.name} onChange={(e) => setEdit({ ...edit, name: e.target.value })} /></Field>
            <Field label={bi("النوع", "Type")}><Select value={s.mode} onChange={(e) => setS({ mode: e.target.value })}>{MODES.map(([k, l]) => <option key={k} value={k}>{l}</option>)}</Select></Field>
            {s.mode !== "whatsapp" && <Field label={bi("البوت الذي يرد", "Bot that answers")}>
              <Select value={String(edit.bot || "")} onChange={(e) => setEdit({ ...edit, bot: Number(e.target.value) })}>{bots.map((b) => <option key={b.id} value={String(b.id)}>{b.name}</option>)}</Select>
            </Field>}
            {s.mode !== "chat" && <Field label={bi("رقم واتساب", "WhatsApp number")}>
              <Select value={String(edit.wa_bot || "")} onChange={(e) => setEdit({ ...edit, wa_bot: Number(e.target.value) })}>
                <option value="">{bi("— اختر —", "— choose —")}</option>{waBots.map((b) => <option key={b.id} value={String(b.id)}>{b.name}</option>)}
              </Select>
            </Field>}
            <Field label={bi("اللون", "Color")}><div className="flex gap-2"><input type="color" value={s.color} onChange={(e) => setS({ color: e.target.value })} className="h-10 w-12 cursor-pointer rounded-lg border-0 bg-transparent" /><Input dir="ltr" value={s.color} onChange={(e) => setS({ color: e.target.value })} /></div></Field>
            <Field label={bi("المكان واللغة", "Position & language")}><div className="flex gap-2">
              <Select value={s.position} onChange={(e) => setS({ position: e.target.value })}><option value="right">{bi("يمين", "Right")}</option><option value="left">{bi("يسار", "Left")}</option></Select>
              <Select value={s.lang} onChange={(e) => setS({ lang: e.target.value })}><option value="ar">العربية</option><option value="en">English</option></Select>
            </div></Field>
          </div>
          {s.mode !== "whatsapp" && <>
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label={bi("العنوان", "Title")}><Input dir="auto" maxLength={60} value={s.title} onChange={(e) => setS({ title: e.target.value })} /></Field>
              <Field label={bi("سطر تحته", "Subtitle")}><Input dir="auto" maxLength={80} value={s.subtitle} placeholder={bi("نرد عادةً خلال دقائق", "We usually reply in minutes")} onChange={(e) => setS({ subtitle: e.target.value })} /></Field>
            </div>
            <Field label={bi("رسالة الترحيب في النافذة", "Welcome message in the window")}><Textarea dir="auto" rows={2} maxLength={500} value={s.welcome} onChange={(e) => setS({ welcome: e.target.value })} /></Field>
            <Field label={bi("أزرار البداية (حتى 4)", "Starter buttons (up to 4)")} hint={bi("افصل بفاصلة — ضغطها يرسل نصها للبوت", "Comma-separated — tapping sends the text to the bot")}>
              <Input dir="auto" defaultValue={(s.icebreakers || []).join("، ")} onChange={(e) => setS({ icebreakers: e.target.value.split(/[,،]/).map((x) => x.trim()).filter(Boolean).slice(0, 4) })} />
            </Field>
          </>}
          <Field label={bi("فقاعة ترحيب فوق الزر (اختياري)", "Greeting bubble above the button (optional)")}><Input dir="auto" maxLength={200} value={s.greeting} onChange={(e) => setS({ greeting: e.target.value })} /></Field>
          {s.mode !== "chat" && <Field label={bi("رسالة واتساب الجاهزة", "Pre-filled WhatsApp message")}><Input dir="auto" maxLength={300} value={s.wa_text} onChange={(e) => setS({ wa_text: e.target.value })} /></Field>}
          <Field label={bi("النطاقات المسموح بها (اختياري)", "Allowed domains (optional)")} hint={bi("مثل alforsan.sa — يمنع نسخ الكود واستعماله في موقع آخر", "e.g. alforsan.sa — stops the code being reused on another site")}>
            <Input dir="ltr" defaultValue={(s.domains || []).join(", ")} onChange={(e) => setS({ domains: e.target.value.split(/[,\s]+/).map((x) => x.trim()).filter(Boolean) })} />
          </Field>
          <div className="flex flex-wrap gap-5 text-[13px] text-ink-2">
            <label className="flex items-center gap-2"><Toggle checked={s.show_desktop !== false} onChange={(v) => setS({ show_desktop: v })} label="" />{bi("الكمبيوتر", "Desktop")}</label>
            <label className="flex items-center gap-2"><Toggle checked={s.show_mobile !== false} onChange={(v) => setS({ show_mobile: v })} label="" />{bi("الجوال", "Mobile")}</label>
          </div>
        </div>
        <div><span className="mb-1.5 block text-[13px] font-bold text-ink-2">{bi("معاينة", "Preview")}</span><WidgetPreview s={s} /></div>
      </div>}
    </Modal>
  </>;
}

/* ------------------------------------------------------------ أتمتة التعليقات (المرحلة 8) */
const CERR = { "rule:keywords": bi("اكتب كلمة واحدة على الأقل، أو اختر «أي تعليق»", "Add at least one keyword, or choose “any comment”"),
  "rule:action": bi("اكتب رداً علنياً أو رسالة خاصة", "Write a public reply or a private message"), "rule:posts": bi("معرّف منشور غير صالح", "Invalid post ID"),
  "rule:id": bi("قاعدة مكرّرة", "Duplicate rule"), "rule:rules": bi("قواعد غير صالحة", "Invalid rules"), role: bi("للمالك والمدير فقط", "Owners and admins only") };
const MATCH = [["contains", bi("يحتوي كلمة", "Contains a keyword")], ["exact", bi("الكلمة وحدها", "Exactly the keyword")], ["any", bi("أي تعليق", "Any comment")]];

function CommentRule({ rule, onSave, onClose }) {
  const [r, setR] = useState(rule);
  const [kw, setKw] = useState((rule.keywords || []).join("، "));
  const [posts, setPosts] = useState((rule.posts || []).join(", "));
  const [pub, setPub] = useState((rule.public || []).join("\n"));
  const save = () => onSave({ ...r, keywords: kw.split(/[,،]/).map((s) => s.trim()).filter(Boolean),
    posts: posts.split(/[,\s]+/).map((s) => s.trim()).filter(Boolean), public: pub.split("\n").map((s) => s.trim()).filter(Boolean) });
  return (
    <Modal open wide onClose={onClose} title={rule.name || bi("قاعدة تعليقات", "Comment rule")} icon="chat"
           footer={<><Btn variant="ghost" onClick={onClose}>{bi("إلغاء", "Cancel")}</Btn><Btn onClick={save}>{bi("تم", "Done")}</Btn></>}>
      <div className="grid gap-3">
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label={bi("الاسم (لك فقط)", "Name (for you)")}><Input dir="auto" maxLength={60} value={r.name || ""} onChange={(e) => setR({ ...r, name: e.target.value })} /></Field>
          <Field label={bi("يعمل عند", "Triggers on")}>
            <Select value={r.match} onChange={(e) => setR({ ...r, match: e.target.value })}>{MATCH.map(([k, l]) => <option key={k} value={k}>{l}</option>)}</Select>
          </Field>
        </div>
        {r.match !== "any" && <Field label={bi("الكلمات", "Keywords")} hint={bi("افصل بفاصلة — لا يهم التشكيل والهمزات", "Comma-separated — diacritics and hamza variants are ignored")}>
          <Input dir="auto" value={kw} placeholder={bi("سعر، كم، price", "price, how much")} onChange={(e) => setKw(e.target.value)} /></Field>}
        <Field label={bi("منشورات بعينها (اختياري)", "Specific posts (optional)")} hint={bi("معرّفات المنشورات مفصولة بفاصلة — فارغ = كل المنشورات. قاعدة المنشور تتقدّم على العامة.", "Post IDs, comma-separated — empty = all posts. A post rule wins over a general one.")}>
          <Input dir="ltr" value={posts} onChange={(e) => setPosts(e.target.value)} /></Field>
        <Field label={bi("الرد العلني (سطر لكل صيغة — نختار واحدة عشوائياً)", "Public reply (one variant per line — we pick one at random)")} hint={bi("{{name}} = اسم المعلّق الأول. اتركه فارغاً لرسالة خاصة فقط.", "{{name}} = the commenter's first name. Leave empty for a private message only.")}>
          <Textarea dir="auto" rows={3} value={pub} placeholder={bi("أرسلنا لك التفاصيل في الخاص 🌙\nتفقّد رسائلك يا {{name}} ✨", "Sent you the details in DM 🌙\nCheck your inbox {{name}} ✨")} onChange={(e) => setPub(e.target.value)} /></Field>
        <Field label={bi("الرسالة الخاصة", "Private message")} hint={bi("رسالة واحدة لكل تعليق (قاعدة Meta). ردّ العميل عليها يفتح المحادثة ويكمل البوت بفلوهاته.", "One per comment (Meta's rule). When the customer replies, the chat opens and your bot's flows take over.")}>
          <Textarea dir="auto" rows={3} maxLength={900} value={r.private || ""} onChange={(e) => setR({ ...r, private: e.target.value })} /></Field>
        <div className="flex flex-wrap gap-5 text-[13px] text-ink-2">
          <label className="flex items-center gap-2"><Toggle checked={r.once !== false} onChange={(v) => setR({ ...r, once: v })} label="" />{bi("مرة واحدة لكل شخص في المنشور", "Once per person per post")}</label>
          <label className="flex items-center gap-2"><Toggle checked={r.active !== false} onChange={(v) => setR({ ...r, active: v })} label="" />{bi("القاعدة تعمل", "Rule active")}</label>
        </div>
      </div>
    </Modal>
  );
}

function Comments() {
  const [bots, setBots] = useState(P.social || []);
  const [edit, setEdit] = useState(null);          // {bot, idx}
  const [err, setErr] = useState("");
  const [log, setLog] = useState({});
  const save = async (b, config) => {
    setErr("");
    const r = await call(`/api/comments/${b.id}/save`, config);
    if (!r.ok) { setErr(CERR[r.error] || bi("حدث خطأ", "Something went wrong")); return false; }
    setBots(r.bots); return true;
  };
  const loadLog = async (b) => { const r = await call(`/api/comments/${b.id}/recent`, null, "GET"); if (r.ok) setLog({ ...log, [b.id]: r.items }); };
  if (!bots.length) return <Card><Empty icon="chat" title={bi("لا قناة ماسنجر أو إنستجرام بعد", "No Messenger or Instagram channel yet")}
    text={bi("اربط صفحتك أو حساب إنستجرام من «بوتاتي»، ثم ارجع هنا: كل من يعلّق بكلمة مثل «سعر» يصله رد علني ورسالة خاصة تلقائياً.", "Connect your Page or Instagram account from “My bots”, then come back: anyone who comments a word like “price” gets a public reply and a DM automatically.")} /></Card>;
  return <>
    {err && <div className="mb-3 rounded-xl bg-red-400/10 px-3 py-2 text-[13px] font-bold text-red-400">{err}</div>}
    {bots.map((b) => {
      const cfg = b.config || { enabled: false, rules: [] };
      const tot = Object.values(b.stats || {}).reduce((a, s) => ({ n: a.n + s.n, dm: a.dm + s.dm }), { n: 0, dm: 0 });
      return (
        <Card key={b.id} className="mb-4">
          <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
            <div className="flex min-w-0 items-center gap-2">
              <Icon name={b.channel === "instagram" ? "camera" : "chat"} size={16} className="text-au-cyan" />
              <b className="truncate text-[15px] text-ink" dir="auto">{b.name}</b>
              <span className="text-[12px] text-ink-3">{b.channel === "instagram" ? "Instagram" : "Facebook"} · {bi(`${num(tot.n)} تعليق · ${num(tot.dm)} رسالة خاصة (30 يوماً)`, `${num(tot.n)} comments · ${num(tot.dm)} DMs (30 days)`)}</span>
            </div>
            {P.canManage && <label className="flex items-center gap-2 text-[13px] text-ink-2"><Toggle checked={!!cfg.enabled} onChange={(v) => save(b, { ...cfg, enabled: v })} label="" />{bi("مفعّلة", "Enabled")}</label>}
          </div>
          {!b.connected && <p className="mb-3 mt-0 rounded-xl bg-yellow-400/10 px-3 py-2 text-[12.5px] font-bold text-yellow-300">{bi("القناة بلا توكن صفحة — أعد ربطها أولاً.", "This channel has no Page token — reconnect it first.")}</p>}
          <div className="grid gap-2">
            {(cfg.rules || []).map((r, i) => { const s = (b.stats || {})[r.id] || { n: 0, pub: 0, dm: 0, bad: 0 }; return (
              <div key={r.id} className="flex min-w-0 flex-wrap items-center justify-between gap-3 rounded-2xl bg-ov/[0.035] px-4 py-3">
                <div className="min-w-0">
                  <b className="block truncate text-ink" dir="auto">{r.name || (r.match === "any" ? bi("أي تعليق", "Any comment") : r.keywords.join("، "))}</b>
                  <span className="text-[12px] text-ink-3">{MATCH.find((m) => m[0] === r.match)?.[1]}{r.posts?.length ? bi(` · ${r.posts.length} منشور`, ` · ${r.posts.length} post(s)`) : bi(" · كل المنشورات", " · all posts")}
                    {r.public?.length ? bi(" · رد علني", " · public reply") : ""}{r.private ? bi(" · رسالة خاصة", " · DM") : ""}{r.active === false ? bi(" · متوقّفة", " · paused") : ""}</span>
                </div>
                <div className="flex flex-wrap items-center gap-4 text-[12.5px]">
                  {[[s.n, bi("تعليقات", "Comments")], [s.dm, bi("رسائل خاصة", "DMs")], [s.bad, bi("إخفاقات", "Failed")]].map(([v, t], k) => (
                    <span key={k} className="text-center"><b className="tnum block text-[16px] text-ink">{num(v)}</b><span className="text-ink-3">{t}</span></span>))}
                  {P.canManage && <>
                    <Btn sm variant="ghost" icon="edit" onClick={() => setEdit({ bot: b, idx: i })} aria-label={bi("تعديل", "Edit")} />
                    <Btn sm variant="ghost" onClick={() => save(b, { ...cfg, rules: cfg.rules.filter((_, j) => j !== i) })} aria-label={bi("حذف", "Delete")}><Icon name="trash" size={14} /></Btn>
                  </>}
                </div>
              </div>); })}
            {!cfg.rules?.length && <p className="m-0 text-[12.5px] text-ink-3">{bi("مثال: من يكتب «سعر» تحت منشور العرض ⇒ «أرسلنا لك التفاصيل في الخاص 🌙» + رسالة خاصة بالأسعار.", "Example: whoever comments “price” under the offer post ⇒ “Sent you the details 🌙” + a DM with prices.")}</p>}
            <div className="flex flex-wrap gap-2">
              {P.canManage && (cfg.rules || []).length < 30 && <Btn sm icon="plus" onClick={() => setEdit({ bot: b, idx: -1 })}>{bi("قاعدة جديدة", "New rule")}</Btn>}
              <Btn sm variant="ghost" icon="clock" onClick={() => loadLog(b)}>{bi("آخر التعليقات", "Recent comments")}</Btn>
            </div>
            {log[b.id] && (log[b.id].length ? <div className="grid gap-1 text-[12.5px]">{log[b.id].map((x) => (
              <div key={x.id} className="flex flex-wrap justify-between gap-2 rounded-lg bg-ov/[0.03] px-2.5 py-1.5">
                <span dir="auto"><b className="text-ink">{x.user_name || "—"}</b>: {x.text}</span>
                <span className="text-ink-3">{x.public_ok === 1 ? "💬✓ " : x.public_ok === 0 ? "💬✗ " : ""}{x.private_ok === 1 ? "✉️✓" : x.private_ok === 0 ? "✉️✗" : ""} {x.error ? `· ${x.error.slice(0, 60)}` : ""}</span>
              </div>))}</div> : <p className="m-0 text-[12.5px] text-ink-3">{bi("لا تعليقات مطابقة بعد.", "No matching comments yet.")}</p>)}
          </div>
        </Card>
      );
    })}
    {edit && <CommentRule rule={edit.idx >= 0 ? edit.bot.config.rules[edit.idx] : { id: "r" + Date.now().toString(36).slice(-6), name: "", match: "contains", keywords: [], posts: [], public: [], private: "", once: true, active: true }}
                          onClose={() => setEdit(null)}
                          onSave={async (rule) => {
                            const cfg = edit.bot.config || { enabled: true, rules: [] };
                            const rules = edit.idx >= 0 ? cfg.rules.map((x, j) => (j === edit.idx ? rule : x)) : [...(cfg.rules || []), rule];
                            if (await save(edit.bot, { enabled: edit.idx >= 0 ? cfg.enabled : true, rules })) setEdit(null);
                          }} />}
  </>;
}

export default function Growth() {
  const [tab, setTab] = useState(() => new URLSearchParams(location.search).get("tab") || "links");
  const tabs = [["links", bi("روابط وQR", "Links & QR"), "link"], ["ads", bi("الإعلانات", "Ads"), "megaphone"],
    ["comments", bi("أتمتة التعليقات", "Comment automation"), "chat"], ["widget", bi("ودجت الموقع", "Website widget"), "globe"]];
  return (
    <>
      <PageHead icon="rocket" title={bi("النمو والإعلانات", "Growth & ads")}
                sub={bi("اعرف من أين يأتي عملاؤك: روابط وQR لكل حملة، أداء إعلانات واتساب، وودجت لموقعك.", "Know where customers come from: a link and QR per campaign, WhatsApp ad performance, and a widget for your website.")} />
      <Tabs items={tabs} value={tab} onChange={setTab} sync />
      {tab === "links" && <Links />}
      {tab === "ads" && <Ads />}
      {tab === "comments" && <Comments />}
      {tab === "widget" && <Widgets />}
    </>
  );
}
