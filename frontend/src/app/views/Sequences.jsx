/* التسلسلات — المرحلة 6: متابعة آلية على خطوات بتأخير لكل عميل مسجَّل.
   قائمة بإحصاءات (مسجَّلون · جارية · اكتملت · توقّفت) ومحرّر خطوات (نص داخل نافذة 24 ساعة أو قالب
   واتساب في أي وقت) · المشغّل (يدوي/وسم) · التوقّف عند الرد · ساعات الإرسال. المنطق والمال في sequences.py. */
import { useEffect, useState } from "react";
import { BY, P, bi, Icon, Card, Btn, Field, Input, Textarea, Select, Pill, Empty, PageHead, num, Modal, Toggle } from "../kit.jsx";

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
  name: bi("اكتب اسماً", "Enter a name"), steps: bi("من خطوة إلى 10 خطوات", "1 to 10 steps"), trigger: bi("اختر وسماً موجوداً", "Pick an existing tag"),
  hours: bi("ساعات الإرسال غير صالحة", "Invalid send hours"), template_channel: bi("القوالب لقنوات واتساب فقط", "Templates are WhatsApp-only"),
  limit: bi("وصلت للحد الأقصى (50)", "Limit reached (50)"), role: bi("للمالك والمدير فقط", "Owners and admins only"), network: bi("تعذّر الاتصال", "Connection failed"),
};
const errOf = (c) => {
  if (c && c.startsWith("step:")) {
    const [, i, why] = c.split(":");
    return bi(`الخطوة ${+i + 1}: `, `Step ${+i + 1}: `) + ({ text: bi("اكتب النص", "write the text"), template: bi("اختر قالباً صحيحاً", "pick a valid template"), delay: bi("مدة غير صالحة", "invalid delay") }[why] || why);
  }
  return ERR[c] || bi("حدث خطأ", "Something went wrong");
};
const REASONS = { replied: bi("ردّ العميل", "Replied"), opted_out: bi("طلب الإيقاف", "Opted out"), human: bi("تولّاه موظف", "Agent took over"),
  window: bi("خارج نافذة 24 ساعة", "Outside 24h window"), manual: bi("أوقفه موظف", "Stopped by agent"), deleted: bi("حُذف", "Deleted") };
const UNITS = [[1, bi("دقيقة", "minutes")], [60, bi("ساعة", "hours")], [1440, bi("يوم", "days")]];
const splitDelay = (m) => { const u = [...UNITS].reverse().find(([k]) => m && m % k === 0) || UNITS[0]; return [m / u[0], u[0]]; };
const DAYS = [[5, bi("سبت", "Sat")], [6, bi("أحد", "Sun")], [0, bi("إثنين", "Mon")], [1, bi("ثلاثاء", "Tue")], [2, bi("أربعاء", "Wed")], [3, bi("خميس", "Thu")], [4, bi("جمعة", "Fri")]];

function StepEditor({ st, i, n, isWa, tpls, onChange, onRemove, onMove }) {
  const [amount, unit] = splitDelay(st.delay || 0);
  const up = (p) => onChange({ ...st, ...p });
  const tp = st.template || { name: "", lang: "ar", vars: [] };
  return (
    <div className="rounded-2xl bg-ov/[0.04] p-3 shadow-[inset_0_0_0_1px_rgb(var(--ov-rgb)/0.07)]">
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <b className="flex items-center gap-2 text-[13px] text-ink"><span className="grid size-6 place-items-center rounded-full bg-au-violet/25 text-[11px]">{i + 1}</span>
          {bi(i ? "بعد الخطوة السابقة بـ" : "بعد التسجيل بـ", i ? "After the previous step by" : "After enrollment by")}</b>
        <span className="flex gap-1">
          <Btn sm variant="ghost" disabled={!i} onClick={() => onMove(-1)} aria-label="↑">↑</Btn>
          <Btn sm variant="ghost" disabled={i === n - 1} onClick={() => onMove(1)} aria-label="↓">↓</Btn>
          <Btn sm variant="ghost" disabled={n <= 1} onClick={onRemove} aria-label={bi("حذف", "Remove")}><Icon name="trash" size={14} /></Btn>
        </span>
      </div>
      <div className="mb-3 grid grid-cols-[90px_130px_1fr] gap-2">
        <Input type="number" min={0} value={amount} onChange={(e) => up({ delay: Math.max(0, Number(e.target.value) || 0) * unit })} />
        <Select value={String(unit)} onChange={(e) => up({ delay: amount * Number(e.target.value) })}>
          {UNITS.map(([k, l]) => <option key={k} value={String(k)}>{l}</option>)}
        </Select>
        <Select value={st.kind || "text"} onChange={(e) => up({ kind: e.target.value })}>
          <option value="text">{bi("رسالة نصية", "Text message")}</option>
          {isWa && <option value="template">{bi("قالب واتساب", "WhatsApp template")}</option>}
        </Select>
      </div>
      {(st.kind || "text") === "text" ? <>
        <Textarea dir="auto" rows={3} value={st.text || ""} placeholder={bi("مثل: أهلاً {{contact.name}}، هل ما زلت مهتماً بالحجز؟", "e.g. Hi {{contact.name}}, still interested in booking?")} onChange={(e) => up({ text: e.target.value })} />
        {isWa && (
          <Field className="mt-2" label={bi("إن مرّت 24 ساعة على آخر رسالة من العميل", "If 24h passed since the customer's last message")}>
            <Select value={st.closed || "skip"} onChange={(e) => up({ closed: e.target.value })}>
              <option value="skip">{bi("تخطَّ هذه الخطوة وأكمل", "Skip this step and continue")}</option>
              <option value="stop">{bi("أوقف التسلسل", "Stop the sequence")}</option>
            </Select>
          </Field>
        )}
      </> : <>
        <Select value={tp.name ? `${tp.name}|${tp.lang}` : ""} onChange={(e) => {
          const [name, lang] = e.target.value.split("|"); const x = (tpls || []).find((t) => t.name === name && t.language === lang);
          up({ template: { name, lang, vars: (x?.vars || []).map((_, j) => tp.vars?.[j] || "") } });
        }}>
          <option value="">{tpls === null ? bi("جارٍ جلب القوالب…", "Loading templates…") : bi("— اختر قالباً معتمداً —", "— Pick an approved template —")}</option>
          {(tpls || []).map((x) => <option key={x.name + x.language} value={`${x.name}|${x.language}`}>{x.name} · {x.language} · {x.category}</option>)}
        </Select>
        {(tp.vars || []).map((v, j) => (
          <Input key={j} className="mt-2" dir="auto" value={v} placeholder={`{{${j + 1}}} — ${bi("مثل {{contact.name}}", "e.g. {{contact.name}}")}`}
                 onChange={(e) => up({ template: { ...tp, vars: tp.vars.map((x, k) => (k === j ? e.target.value : x)) } })} />
        ))}
        <p className="mb-0 mt-2 text-[12px] text-ink-3">{bi("يصل في أي وقت. التسويقي يُخصم من الرصيد كالبث ويُردّ لو رفضته Meta.", "Delivered any time. Marketing ones are charged like broadcasts and refunded if Meta refuses.")}</p>
      </>}
    </div>
  );
}

function Editor({ item, onClose, onSaved }) {
  const [d, setD] = useState(null);
  const [err, setErr] = useState("");
  const [tpls, setTpls] = useState(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    if (!item) return;
    setErr("");
    setD(item.id ? { id: item.id, name: item.name, bot: item.bot_id, active: item.active, ...item.spec, hoursOn: !!item.spec.hours }
      : { name: "", bot: (P.bots || [])[0]?.id, active: true, steps: [{ delay: 60, kind: "text", text: "", closed: "skip" }],
          trigger: { type: "manual" }, stop_on_reply: true, hours: { start: 9, end: 21, tz: 3, days: [0, 1, 2, 3, 4, 5, 6] }, hoursOn: false });
  }, [item]);
  const bot = (P.bots || []).find((b) => b.id === d?.bot);
  const isWa = bot?.channel === "whatsapp";
  useEffect(() => {
    setTpls(null);
    if (!d?.bot || !isWa) return;
    call(`/api/templates?bot=${d.bot}`, null, "GET").then((r) => setTpls(r.ok ? (r.items || []).filter((x) => x.status === "APPROVED") : []));
  }, [d?.bot, isWa]);
  if (!item || !d) return null;
  const set = (p) => setD({ ...d, ...p });
  const steps = d.steps || [];
  const save = async () => {
    setBusy(true); setErr("");
    const spec = { steps, trigger: d.trigger, stop_on_reply: d.stop_on_reply, hours: d.hoursOn ? d.hours : null };
    const r = await call("/api/sequences/save", { id: d.id, name: d.name, bot: d.bot, active: d.active, spec });
    setBusy(false);
    if (!r.ok) { setErr(errOf(r.error)); return; }
    onSaved(r.item);
  };
  return (
    <Modal open wide onClose={onClose} title={d.id ? bi("تعديل التسلسل", "Edit sequence") : bi("تسلسل جديد", "New sequence")} icon="clock"
           footer={<><Btn variant="ghost" onClick={onClose}>{bi("إلغاء", "Cancel")}</Btn><Btn disabled={busy} onClick={save}>{bi("حفظ", "Save")}</Btn></>}>
      <div className="grid gap-4">
        {err && <div className="rounded-xl bg-red-400/10 px-3 py-2 text-[13px] font-bold text-red-400">{err}</div>}
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label={bi("الاسم", "Name")}><Input dir="auto" maxLength={80} value={d.name} placeholder={bi("مثل: متابعة من لم يُكمل الحجز", "e.g. Follow up unfinished bookings")} onChange={(e) => set({ name: e.target.value })} /></Field>
          <Field label={bi("القناة", "Channel")}>
            <Select value={String(d.bot || "")} onChange={(e) => set({ bot: Number(e.target.value) })}>
              {(P.bots || []).map((b) => <option key={b.id} value={String(b.id)}>{b.name}</option>)}
            </Select>
          </Field>
          <Field label={bi("يبدأ عندما", "Starts when")}>
            <Select value={d.trigger?.type || "manual"} onChange={(e) => set({ trigger: e.target.value === "tag" ? { type: "tag", tag: (P.tags || [])[0] || "" } : { type: "manual" } })}>
              <option value="manual">{bi("يسجّله موظف أو بطاقة في الفلو", "An agent or a flow card enrolls the customer")}</option>
              <option value="tag">{bi("يُضاف وسم لجهة الاتصال", "A tag is added to the contact")}</option>
            </Select>
          </Field>
          {d.trigger?.type === "tag" && (
            <Field label={bi("الوسم", "Tag")}>
              <Select value={d.trigger.tag || ""} onChange={(e) => set({ trigger: { type: "tag", tag: e.target.value } })}>
                {(P.tags || []).map((t) => <option key={t} value={t}>#{t}</option>)}
              </Select>
            </Field>
          )}
        </div>
        <div className="flex flex-wrap gap-5">
          <label className="flex items-center gap-2 text-[13px] text-ink-2"><Toggle checked={d.stop_on_reply !== false} onChange={(v) => set({ stop_on_reply: v })} label="" />{bi("يتوقّف إذا ردّ العميل", "Stop when the customer replies")}</label>
          <label className="flex items-center gap-2 text-[13px] text-ink-2"><Toggle checked={!!d.hoursOn} onChange={(v) => set({ hoursOn: v })} label="" />{bi("أرسل في ساعات محدّدة فقط", "Only send during set hours")}</label>
          <label className="flex items-center gap-2 text-[13px] text-ink-2"><Toggle checked={!!d.active} onChange={(v) => set({ active: v })} label="" />{bi("مفعّل", "Active")}</label>
        </div>
        {d.hoursOn && (
          <div className="grid gap-2 rounded-2xl bg-ov/[0.03] p-3">
            <div className="grid grid-cols-3 gap-2">
              <Field label={bi("من", "From")}><Input type="number" min={0} max={23} value={d.hours.start} onChange={(e) => set({ hours: { ...d.hours, start: Number(e.target.value) } })} /></Field>
              <Field label={bi("إلى", "To")}><Input type="number" min={1} max={24} value={d.hours.end} onChange={(e) => set({ hours: { ...d.hours, end: Number(e.target.value) } })} /></Field>
              <Field label="UTC ±"><Input type="number" step="0.5" value={d.hours.tz} onChange={(e) => set({ hours: { ...d.hours, tz: Number(e.target.value) } })} /></Field>
            </div>
            <div className="flex flex-wrap gap-1.5">
              {DAYS.map(([k, l]) => { const on = (d.hours.days || []).includes(k); return (
                <button key={k} type="button" onClick={() => set({ hours: { ...d.hours, days: on ? d.hours.days.filter((x) => x !== k) : [...(d.hours.days || []), k] } })}
                        className={`cursor-pointer rounded-lg border-0 px-2.5 py-1.5 text-[12px] font-bold ${on ? "bg-au-teal/20 text-au-teal" : "bg-ov/5 text-ink-3"}`}>{l}</button>); })}
            </div>
            <p className="m-0 text-[12px] text-ink-3">{bi("خطوة يحلّ موعدها خارج هذه الساعات تنتظر لبدايتها التالية.", "A step due outside these hours waits for the next opening.")}</p>
          </div>
        )}
        <div className="grid gap-3">
          {steps.map((st, i) => (
            <StepEditor key={i} st={st} i={i} n={steps.length} isWa={isWa} tpls={tpls}
                        onChange={(x) => set({ steps: steps.map((y, j) => (j === i ? x : y)) })}
                        onRemove={() => set({ steps: steps.filter((_, j) => j !== i) })}
                        onMove={(dir) => { const s2 = [...steps]; [s2[i], s2[i + dir]] = [s2[i + dir], s2[i]]; set({ steps: s2 }); }} />
          ))}
          {steps.length < (P.limits?.steps || 10) && <Btn variant="ghost" icon="plus" className="justify-self-start" onClick={() => set({ steps: [...steps, { delay: 1440, kind: "text", text: "", closed: "skip" }] })}>{bi("خطوة", "Step")}</Btn>}
        </div>
      </div>
    </Modal>
  );
}

export default function Sequences() {
  const [items, setItems] = useState(P.items || []);
  const [edit, setEdit] = useState(null);
  const botName = (id) => (P.bots || []).find((b) => b.id === id)?.name || "—";
  const toggle = async (s, on) => { const r = await call("/api/sequences/toggle", { id: s.id, active: on }); if (r.ok) setItems(items.map((x) => (x.id === s.id ? { ...x, active: on } : x))); };
  const del = async (s) => {
    if (!window.confirm(bi(`حذف «${s.name}»؟ يتوقّف لكل المسجَّلين فيه.`, `Delete “${s.name}”? It stops for everyone enrolled.`))) return;
    const r = await call("/api/sequences/delete", { id: s.id }); if (r.ok) setItems(items.filter((x) => x.id !== s.id));
  };
  return (
    <>
      <PageHead icon="clock" title={bi("التسلسلات", "Sequences")}
                sub={bi("رسائل متابعة آلية على مراحل: تتوقّف إذا ردّ العميل أو طلب الإيقاف، وتحترم نافذة واتساب.", "Automatic multi-step follow-ups that stop when the customer replies or opts out, and respect the WhatsApp window.")}
                actions={P.canManage && !!(P.bots || []).length && <Btn icon="plus" onClick={() => setEdit({})}>{bi("تسلسل جديد", "New sequence")}</Btn>} />
      <Card>
        {!items.length ? (
          <Empty icon="clock" title={bi("لا تسلسلات بعد", "No sequences yet")}
                 text={bi("مثال: من سأل عن السعر ولم يحجز — تذكير بعد ساعة، ثم عرض بعد يوم بقالب واتساب.", "Example: asked for a price but didn't book — a reminder after an hour, then an offer a day later via a WhatsApp template.")} />
        ) : (
          <div className="grid gap-2">
            {items.map((s) => {
              const st = s.stats || {};
              return (
                <div key={s.id} className="flex flex-wrap items-center justify-between gap-3 rounded-2xl bg-ov/[0.035] px-4 py-3">
                  <div className="min-w-0">
                    <b className="block truncate text-[14.5px] text-ink" dir="auto">{s.name}</b>
                    <span className="text-[12px] text-ink-3">
                      {botName(s.bot_id)} · {bi(`${s.spec.steps.length} خطوات`, `${s.spec.steps.length} steps`)} · {s.spec.trigger?.type === "tag" ? `#${s.spec.trigger.tag}` : bi("يدوي/فلو", "Manual/flow")}
                      {s.spec.stop_on_reply !== false && ` · ${bi("يتوقّف بالرد", "stops on reply")}`}
                    </span>
                  </div>
                  <div className="flex flex-wrap items-center gap-4 text-[12.5px]">
                    {[["enrolled", bi("مسجَّلون", "Enrolled")], ["active", bi("جارية", "Active")], ["done", bi("اكتملت", "Completed")], ["stopped", bi("توقّفت", "Stopped")]].map(([k, l]) => (
                      <span key={k} className="text-center"><b className="tnum block text-[16px] text-ink">{num(st[k])}</b><span className="text-ink-3">{l}</span></span>
                    ))}
                    {!!Object.keys(st.reasons || {}).length && (
                      <span className="max-w-[220px] text-[11.5px] text-ink-3">{Object.entries(st.reasons).map(([k, v]) => `${REASONS[k] || k}: ${v}`).join(" · ")}</span>
                    )}
                    <Toggle checked={s.active} disabled={!P.canManage} onChange={(v) => toggle(s, v)} label={bi("تفعيل", "Active")} />
                    {P.canManage && <>
                      <Btn sm variant="ghost" icon="edit" onClick={() => setEdit(s)}>{bi("تعديل", "Edit")}</Btn>
                      <Btn sm variant="ghost" onClick={() => del(s)} aria-label={bi("حذف", "Delete")}><Icon name="trash" size={14} /></Btn>
                    </>}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </Card>
      {edit && <Editor item={edit} onClose={() => setEdit(null)}
                       onSaved={(it) => { setItems(items.some((x) => x.id === it.id) ? items.map((x) => (x.id === it.id ? it : x)) : [it, ...items]); setEdit(null); }} />}
    </>
  );
}
