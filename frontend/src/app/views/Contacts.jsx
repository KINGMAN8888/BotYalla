/* جهات الاتصال (CRM) — المرحلة 1 من docs/ENTERPRISE_PLAN.md.
   تبويبات: الجهات · الشرائح · الشركات · الحقول · الوسوم. البيانات عبر /api/crm/* (JSON + X-CSRF-Token)
   والخادم هو من يتحقّق من كل شيء — تفعيل الأزرار هنا راحة لا أمان. */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { BY, P, t, bi, AR, Icon, Card, Btn, Field, Input, Textarea, Select, Pill, Empty, PageHead, num, Modal, Tabs, Toggle } from "../kit.jsx";

/* ------------------------------------------------------------ شبكة */
async function call(url, body, method = "POST") {
  try {
    const r = await fetch(url, method === "GET" ? { headers: { Accept: "application/json" } } : {
      method, headers: { "Content-Type": "application/json", "X-CSRF-Token": BY.csrf },
      body: JSON.stringify(body || {}),
    });
    const j = await r.json().catch(() => ({ ok: false, error: "network" }));
    return { status: r.status, ...j };
  } catch {
    return { ok: false, error: "network" };
  }
}
const get = (url) => call(url, null, "GET");

const ERR = {
  required: ["مطلوب", "Required"], phone: ["رقم هاتف غير صالح", "Invalid phone number"],
  phone_taken: ["الرقم مسجّل لجهة أخرى", "This number belongs to another contact"],
  email: ["بريد غير صالح", "Invalid email"], option: ["اختيار غير موجود", "Not one of the options"],
  number: ["رقم غير صالح", "Not a number"], date: ["تاريخ غير صالح", "Invalid date"],
  switch: ["نعم أو لا", "Yes or no"], user: ["ليس من فريقك", "Not on your team"],
  company: ["شركة غير موجودة", "Unknown company"], key_taken: ["المفتاح مستخدم", "Key already used"],
  taken: ["الاسم مستخدم", "Name already used"], name: ["الاسم مطلوب", "Name is required"],
  label: ["الاسم مطلوب", "Label is required"], key: ["مفتاح غير صالح (حروف إنجليزية صغيرة وأرقام و _)", "Invalid key (a-z, 0-9, _)"],
  options: ["أضف خياراً واحداً على الأقل", "Add at least one option"], limit: ["وصلت للحد الأقصى", "Limit reached"],
  rules: ["شروط غير صالحة", "Invalid conditions"], field: ["حقل غير معروف", "Unknown field"],
  op: ["شرط غير صالح", "Invalid operator"], value: ["أكمل قيمة الشرط", "Complete the condition value"],
  rate: ["محاولات كثيرة، انتظر قليلاً", "Too many requests, wait a moment"],
  ext: ["الملف يجب أن يكون CSV أو XLSX", "File must be CSV or XLSX"], file: ["اختر ملفاً", "Choose a file"],
  too_big: ["الملف أكبر من 8MB", "File is over 8MB"], empty: ["الملف فارغ", "The file is empty"],
  too_many: ["أكثر من 20,000 صف — قسّم الملف", "Over 20,000 rows — split the file"],
  no_phone: ["اربط عموداً برقم الهاتف", "Map a column to Phone"], expired: ["انتهت الجلسة، ارفع الملف مجدداً", "Session expired, upload again"],
  bad_file: ["تعذّرت قراءة الملف", "Couldn't read the file"], xlsx_unavailable: ["Excel غير متاح، استخدم CSV", "Excel unavailable, use CSV"],
  role: ["لا تملك صلاحية هذا الإجراء", "You don't have permission"], plan: ["غير متاح في باقتك", "Not in your plan"],
  segment_stale: ["الشريحة تستخدم حقلاً محذوفاً — عدّلها", "Segment uses a deleted field — edit it"],
  not_found: ["غير موجود", "Not found"], network: ["تعذّر الاتصال، حاول مجدداً", "Connection failed, try again"],
};
const err = (code) => (ERR[code] ? bi(...ERR[code]) : bi("حدث خطأ", "Something went wrong") + (code ? ` (${code})` : ""));

const TAG_TONE = {
  cyan: "bg-cyan-400/15 text-cyan-200", teal: "bg-teal-400/15 text-teal-200", violet: "bg-violet-400/15 text-violet-200",
  amber: "bg-amber-400/15 text-amber-200", rose: "bg-rose-400/15 text-rose-200", sky: "bg-sky-400/15 text-sky-200",
  lime: "bg-lime-400/15 text-lime-200", slate: "bg-slate-400/15 text-slate-200",
};
const DOT = {
  cyan: "bg-cyan-400", teal: "bg-teal-400", violet: "bg-violet-400", amber: "bg-amber-400",
  rose: "bg-rose-400", sky: "bg-sky-400", lime: "bg-lime-400", slate: "bg-slate-400",
};

const TYPE_LABEL = {
  text: ["نص", "Text"], multi_text: ["نص متعدد", "Multi text"], number: ["رقم", "Number"],
  select: ["اختيار واحد", "Select"], multi_select: ["اختيار متعدد", "Multi select"], date: ["تاريخ", "Date"],
  switch: ["مفتاح (نعم/لا)", "Switch"], user: ["موظف", "User"],
};
const SYS_LABEL = {
  name: ["الاسم", "Name"], phone: ["الهاتف", "Phone"], email: ["البريد", "Email"],
  optin: ["موافقة تسويقية", "Marketing opt-in"], tags: ["الوسوم", "Tags"],
  created_at: ["تاريخ الإضافة", "Created at"], updated_at: ["آخر تحديث", "Updated at"],
  last_seen_at: ["آخر تفاعل", "Last active"], assignee: ["مسؤول الجهة", "Contact owner"],
  company: ["الشركة", "Company"], source: ["المصدر", "Source"],
};
const OP_LABEL = {
  is: ["يساوي", "is"], is_not: ["لا يساوي", "is not"], contains: ["يحتوي", "contains"],
  not_contains: ["لا يحتوي", "doesn't contain"], starts_with: ["يبدأ بـ", "starts with"],
  empty: ["فارغ", "is empty"], not_empty: ["غير فارغ", "is not empty"], eq: ["=", "="], neq: ["≠", "≠"],
  gt: ["أكبر من", "greater than"], lt: ["أصغر من", "less than"], on: ["في يوم", "on"],
  before: ["قبل", "before"], after: ["بعد", "after"], last_days: ["خلال آخر (أيام)", "in the last (days)"],
  any_of: ["أيٌّ من", "any of"], has_any: ["فيه أيٌّ من", "has any of"], has_all: ["فيه كل", "has all of"],
  has_none: ["ليس فيه", "has none of"],
};
const SOURCE_LABEL = { chat: ["محادثة", "Chat"], manual: ["يدوي", "Manual"], import: ["استيراد", "Import"], api: ["API", "API"] };

const fmtDay = (ts) => (ts ? new Date(ts * 1000).toLocaleDateString(AR ? "ar-EG" : "en-GB",
  { year: "numeric", month: "short", day: "numeric" }) : "—");
const store = {
  get(k, d) { try { const v = localStorage.getItem(k); return v ? JSON.parse(v) : d; } catch { return d; } },
  set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch { /* تخزين محجوب — الافتراضي يكفي */ } },
};

/* ------------------------------------------------------------ عناصر صغيرة */
const ErrLine = ({ children }) => (children ? <span className="mt-1 block text-[12px] text-red-300">{children}</span> : null);

function TagChip({ tag, onRemove }) {
  if (!tag) return null;
  return (
    <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11.5px] font-bold ${TAG_TONE[tag.color] || TAG_TONE.cyan}`}>
      {tag.name}
      {onRemove && (
        <button type="button" onClick={onRemove} aria-label={bi("إزالة", "Remove")}
                className="cursor-pointer border-0 bg-transparent p-0 leading-none text-current opacity-70 hover:opacity-100">×</button>
      )}
    </span>
  );
}

/* اختيار عدّة قيم كرقائق — للوسوم والاختيار المتعدد */
function Chips({ options, value, onChange, render }) {
  const set = new Set(value || []);
  return (
    <div className="flex flex-wrap gap-1.5">
      {options.map((o) => {
        const on = set.has(o.value);
        return (
          <button key={o.value} type="button" aria-pressed={on}
                  onClick={() => onChange(on ? (value || []).filter((x) => x !== o.value) : [...(value || []), o.value])}
                  className={`cursor-pointer rounded-full border-0 px-2.5 py-1 text-[12px] font-bold transition-colors
                              ${on ? "bg-au-violet/80 text-white" : "bg-ov/[0.06] text-ink-2 hover:bg-ov/10"}`}>
            {render ? render(o, on) : o.label}
          </button>
        );
      })}
      {!options.length && <span className="text-[12px] text-ink-3">{bi("لا خيارات بعد", "No options yet")}</span>}
    </div>
  );
}

/* ------------------------------------------------------------ قيمة حقل مخصّص حسب نوعه */
function FieldInput({ f, value, onChange, members }) {
  const v = value ?? "";
  switch (f.type) {
    case "number":
      return <Input type="number" dir="ltr" value={v} onChange={(e) => onChange(e.target.value)} />;
    case "date":
      return <Input type="date" dir="ltr" value={v} onChange={(e) => onChange(e.target.value)} />;
    case "switch":
      return <Toggle checked={!!value} onChange={onChange} label={f.label} />;
    case "select":
      return (
        <Select value={v} onChange={(e) => onChange(e.target.value)}>
          <option value="">—</option>
          {f.options.map((o) => <option key={o} value={o}>{o}</option>)}
        </Select>
      );
    case "multi_select":
      return <Chips options={f.options.map((o) => ({ value: o, label: o }))} value={value || []} onChange={onChange} />;
    case "multi_text":
      return <Input value={Array.isArray(value) ? value.join(", ") : v}
                    placeholder={bi("قيم مفصولة بفاصلة", "Comma-separated values")}
                    onChange={(e) => onChange(e.target.value.split(",").map((x) => x.trim()).filter(Boolean))} />;
    case "user":
      return (
        <Select value={String(v)} onChange={(e) => onChange(e.target.value ? Number(e.target.value) : "")}>
          <option value="">—</option>
          {members.map((m) => <option key={m.id} value={String(m.id)}>{m.username}</option>)}
        </Select>
      );
    default:
      return <Input value={v} onChange={(e) => onChange(e.target.value)} />;
  }
}

function fieldText(f, v, members) {
  if (v == null || v === "") return "—";
  if (Array.isArray(v)) return v.join("، ");
  if (f.type === "switch") return v ? bi("نعم", "Yes") : bi("لا", "No");
  if (f.type === "user") return (members.find((m) => m.id === v) || {}).username || "—";
  return String(v);
}

/* ------------------------------------------------------------ اختيار/إنشاء وسوم */
function TagPicker({ meta, setMeta, value, onChange }) {
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const add = async () => {
    const n = name.trim();
    if (!n) return;
    const hit = meta.tags.find((x) => x.name.toLowerCase() === n.toLowerCase());
    if (hit) { if (!value.includes(hit.id)) onChange([...value, hit.id]); setName(""); return; }
    setBusy(true);
    const r = await call("/api/crm/tags", { name: n });
    setBusy(false);
    if (r.ok) { setMeta(r); onChange([...value, r.id]); setName(""); }
  };
  return (
    <div>
      <Chips options={meta.tags.map((x) => ({ value: x.id, label: x.name, color: x.color }))} value={value} onChange={onChange}
             render={(o) => (<span className="inline-flex items-center gap-1.5"><i className={`size-1.5 rounded-full ${DOT[o.color] || DOT.cyan}`} />{o.label}</span>)} />
      <div className="mt-2 flex gap-2">
        <Input value={name} placeholder={bi("وسم جديد…", "New tag…")} onChange={(e) => setName(e.target.value)}
               onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); add(); } }} maxLength={50} />
        <Btn sm variant="ghost" type="button" icon="plus" onClick={add} disabled={busy || !name.trim()}>{bi("أضف", "Add")}</Btn>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------ نموذج جهة الاتصال */
function ContactModal({ open, contact, meta, setMeta, onClose, onSaved }) {
  const blank = { name: "", phone: "", cc: "+966", email: "", company_id: "", assignee_id: "", optin: "", tags: [], fields: {} };
  const [d, setD] = useState(blank);
  const [errs, setErrs] = useState({});
  const [busy, setBusy] = useState(false);
  const [channels, setChannels] = useState([]);
  useEffect(() => {
    if (!open) return;
    setErrs({});
    if (contact) {
      setD({ ...blank, ...contact, cc: "+966", company_id: contact.company_id || "", assignee_id: contact.assignee_id || "",
             optin: contact.optin == null ? "" : String(contact.optin), tags: contact.tags || [], fields: { ...(contact.fields || {}) } });
      get(`/api/crm/contacts/${contact.id}`).then((r) => setChannels(r.channels || []));
    } else {
      setD(blank); setChannels([]);
    }
  }, [open, contact]);  // eslint-disable-line react-hooks/exhaustive-deps

  const set = (k, v) => setD((x) => ({ ...x, [k]: v }));
  const setF = (k, v) => setD((x) => ({ ...x, fields: { ...x.fields, [k]: v } }));
  const fields = meta.fields.filter((f) => f.active);
  const save = async () => {
    setBusy(true);
    const r = await call("/api/crm/contacts", {
      id: contact?.id, name: d.name, phone: d.phone, cc: d.cc, email: d.email,
      company_id: d.company_id || null, assignee_id: d.assignee_id || null,
      optin: d.optin === "" ? null : Number(d.optin), tags: d.tags,
      fields: Object.fromEntries(fields.map((f) => [f.key, d.fields[f.key] === "" ? null : d.fields[f.key]])),
    });
    setBusy(false);
    if (r.ok) { onSaved(r.contact); onClose(); } else setErrs(r.fields && Object.keys(r.fields).length ? r.fields : { _: r.error });
  };
  const phoneIsFull = (d.phone || "").startsWith("+");
  return (
    <Modal open={open} onClose={onClose} icon="user" wide
           title={contact ? bi("تعديل جهة اتصال", "Edit contact") : bi("إضافة جهة اتصال", "Add contact")}
           footer={<>
             <Btn variant="ghost" type="button" onClick={onClose}>{t("cancel")}</Btn>
             <Btn type="button" icon="check" onClick={save} disabled={busy}>{bi("حفظ", "Save")}</Btn>
           </>}>
      {errs._ && <div className="mb-4 rounded-xl bg-red-400/10 px-3 py-2 text-[13px] text-red-200">{err(errs._)}</div>}
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label={bi("الاسم", "Name")}>
          <Input value={d.name} maxLength={120} onChange={(e) => set("name", e.target.value)} dir="auto" />
        </Field>
        <Field label={bi("الهاتف (واتساب)", "Phone (WhatsApp)")}>
          <div className="flex gap-2" dir="ltr">
            {!phoneIsFull && (
              <Select className="!w-[110px] shrink-0" value={d.cc} onChange={(e) => set("cc", e.target.value)}>
                {(P.countries || []).map((c) => <option key={c[0]} value={c[1]}>{c[1]}</option>)}
              </Select>
            )}
            <Input value={d.phone || ""} inputMode="tel" placeholder="05xxxxxxxx" onChange={(e) => set("phone", e.target.value)} />
          </div>
          <ErrLine>{errs.phone && err(errs.phone)}</ErrLine>
        </Field>
        <Field label={bi("البريد", "Email")}>
          <Input type="email" dir="ltr" value={d.email || ""} onChange={(e) => set("email", e.target.value)} />
          <ErrLine>{errs.email && err(errs.email)}</ErrLine>
        </Field>
        <Field label={bi("موافقة تسويقية", "Marketing opt-in")}>
          <Select value={d.optin} onChange={(e) => set("optin", e.target.value)}>
            <option value="">{bi("غير معروفة", "Unknown")}</option>
            <option value="1">{bi("موافق", "Opted in")}</option>
            <option value="0">{bi("غير موافق", "Opted out")}</option>
          </Select>
        </Field>
        <Field label={bi("الشركة", "Company")}>
          <Select value={String(d.company_id || "")} onChange={(e) => set("company_id", e.target.value)}>
            <option value="">—</option>
            {meta.companies.map((c) => <option key={c.id} value={String(c.id)}>{c.name}</option>)}
          </Select>
        </Field>
        <Field label={bi("مسؤول الجهة", "Contact owner")}>
          <Select value={String(d.assignee_id || "")} onChange={(e) => set("assignee_id", e.target.value)}>
            <option value="">—</option>
            {meta.members.map((m) => <option key={m.id} value={String(m.id)}>{m.username}</option>)}
          </Select>
          <ErrLine>{errs.assignee_id && err(errs.assignee_id)}</ErrLine>
        </Field>
      </div>
      <Field label={bi("الوسوم", "Tags")} className="mt-4">
        <TagPicker meta={meta} setMeta={setMeta} value={d.tags} onChange={(v) => set("tags", v)} />
      </Field>
      {fields.length > 0 && (
        <div className="mt-5 grid gap-4 rounded-2xl bg-ov/[0.03] p-4 sm:grid-cols-2">
          {fields.map((f) => (
            <Field key={f.key} label={<>{f.label}{f.required ? <span className="text-red-300"> *</span> : null}</>}>
              <FieldInput f={f} value={d.fields[f.key]} onChange={(v) => setF(f.key, v)} members={meta.members} />
              <ErrLine>{errs["f:" + f.key] && err(errs["f:" + f.key])}</ErrLine>
            </Field>
          ))}
        </div>
      )}
      {channels.length > 0 && (
        <div className="mt-5 text-[12.5px] text-ink-3">
          <b className="text-ink-2">{bi("تواصل عبر:", "Reached through:")}</b>{" "}
          {channels.map((c) => `${c.bot_name} (${c.channel === "whatsapp" ? "WhatsApp" : "Telegram"})`).join(" · ")}
        </div>
      )}
    </Modal>
  );
}

/* ------------------------------------------------------------ منشئ الشروط (Segments) */
function kindOf(field, meta) {
  if (field.startsWith("f:")) return (meta.fields.find((f) => "f:" + f.key === field) || {}).type;
  return (P.systemFields || {})[field];
}

function RuleValue({ rule, kind, meta, onChange }) {
  const { op, field, value } = rule;
  if (["empty", "not_empty"].includes(op)) return null;
  if (op === "last_days") return <Input type="number" min="0" dir="ltr" value={value ?? ""} onChange={(e) => onChange(e.target.value)} />;
  if (kind === "date" || kind === "ts") return <Input type="date" dir="ltr" value={value ?? ""} onChange={(e) => onChange(e.target.value)} />;
  if (kind === "switch") {
    return (
      <Select value={value === false || value === "false" ? "false" : "true"} onChange={(e) => onChange(e.target.value === "true")}>
        <option value="true">{bi("نعم", "Yes")}</option><option value="false">{bi("لا", "No")}</option>
      </Select>
    );
  }
  if (kind === "tags") {
    return <Chips options={meta.tags.map((x) => ({ value: x.id, label: x.name }))} value={value || []} onChange={onChange} />;
  }
  const fdef = field.startsWith("f:") ? meta.fields.find((f) => "f:" + f.key === field) : null;
  if (kind === "multi_select" || (kind === "select" && op === "any_of")) {
    return <Chips options={(fdef?.options || []).map((o) => ({ value: o, label: o }))} value={value || []} onChange={onChange} />;
  }
  if (kind === "select") {
    return (
      <Select value={value ?? ""} onChange={(e) => onChange(e.target.value)}>
        <option value="">—</option>{(fdef?.options || []).map((o) => <option key={o} value={o}>{o}</option>)}
      </Select>
    );
  }
  if (kind === "user") {
    return (
      <Select value={String(value ?? "")} onChange={(e) => onChange(Number(e.target.value))}>
        <option value="">—</option>{meta.members.map((m) => <option key={m.id} value={String(m.id)}>{m.username}</option>)}
      </Select>
    );
  }
  if (kind === "company") {
    return (
      <Select value={String(value ?? "")} onChange={(e) => onChange(Number(e.target.value))}>
        <option value="">—</option>{meta.companies.map((c) => <option key={c.id} value={String(c.id)}>{c.name}</option>)}
      </Select>
    );
  }
  if (kind === "source") {
    return (
      <Select value={value ?? "chat"} onChange={(e) => onChange(e.target.value)}>
        {Object.entries(SOURCE_LABEL).map(([k, l]) => <option key={k} value={k}>{bi(...l)}</option>)}
      </Select>
    );
  }
  return <Input type={kind === "number" ? "number" : "text"} dir="auto" value={value ?? ""} onChange={(e) => onChange(e.target.value)} />;
}

function RuleBuilder({ rules, setRules, meta }) {
  const fieldOpts = [
    ...Object.keys(P.systemFields || {}).map((k) => ({ v: k, l: bi(...SYS_LABEL[k]) })),
    ...meta.fields.map((f) => ({ v: "f:" + f.key, l: f.label })),
  ];
  const upd = (i, patch) => setRules(rules.map((r, j) => (j === i ? { ...r, ...patch } : r)));
  return (
    <div className="flex flex-col gap-3">
      {rules.map((r, i) => {
        const kind = kindOf(r.field, meta);
        const ops = (P.ops || {})[kind] || [];
        return (
          <div key={i} className="rounded-2xl bg-ov/[0.035] p-3">
            {i > 0 && <div className="-mt-1 mb-2 text-[11px] font-extrabold uppercase tracking-wider text-au-cyan">{bi("و", "AND")}</div>}
            <div className="grid gap-2 sm:grid-cols-[1fr_1fr_auto]">
              <Select value={r.field} onChange={(e) => {
                const k = kindOf(e.target.value, meta);
                upd(i, { field: e.target.value, op: ((P.ops || {})[k] || [])[0], value: null });
              }}>
                {fieldOpts.map((o) => <option key={o.v} value={o.v}>{o.l}</option>)}
              </Select>
              <Select value={r.op} onChange={(e) => upd(i, { op: e.target.value, value: null })}>
                {ops.map((o) => <option key={o} value={o}>{bi(...(OP_LABEL[o] || [o, o]))}</option>)}
              </Select>
              <Btn sm variant="ghost" type="button" onClick={() => setRules(rules.filter((_, j) => j !== i))}
                   aria-label={bi("حذف الشرط", "Remove condition")}><Icon name="trash" size={15} /></Btn>
            </div>
            <div className="mt-2"><RuleValue rule={r} kind={kind} meta={meta} onChange={(v) => upd(i, { value: v })} /></div>
          </div>
        );
      })}
      <div>
        <Btn sm variant="ghost" type="button" icon="plus" disabled={rules.length >= 20}
             onClick={() => setRules([...rules, { field: "tags", op: "has_any", value: [] }])}>
          {bi("أضف شرطاً", "Add condition")}
        </Btn>
      </div>
    </div>
  );
}

function SegmentModal({ open, seg, meta, setMeta, onClose }) {
  const [name, setName] = useState("");
  const [rules, setRules] = useState([]);
  const [count, setCount] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    if (!open) return;
    setName(seg?.name || ""); setRules(seg?.rules || [{ field: "tags", op: "has_any", value: [] }]);
    setCount(null); setError("");
  }, [open, seg]);
  const view = async () => {
    const r = await call("/api/crm/segments/count", { rules });
    if (r.ok) { setCount(r.count); setError(""); } else setError(r.error);
  };
  const save = async () => {
    setBusy(true);
    const r = await call("/api/crm/segments", { id: seg?.id, name, rules });
    setBusy(false);
    if (r.ok) { setMeta(r); onClose(); } else setError(r.error);
  };
  return (
    <Modal open={open} onClose={onClose} icon="filter" wide
           title={seg ? bi("تعديل شريحة", "Edit segment") : bi("شريحة جديدة", "New segment")}
           footer={<>
             <Btn variant="ghost" type="button" icon="users" onClick={view}>
               {count == null ? bi("عرض العدد", "View count") : `${num(count)} ${bi("جهة", "contacts")}`}
             </Btn>
             <Btn type="button" icon="check" onClick={save} disabled={busy || !name.trim()}>{bi("حفظ", "Save")}</Btn>
           </>}>
      <p className="mt-0 text-[13px] leading-relaxed text-ink-3">
        {bi("الشريحة تتحدّث تلقائياً: أي جهة تنطبق عليها كل الشروط تدخلها فوراً، ومن لم تعد تنطبق عليه يخرج — وقت الإرسال هو ما يُحسب.",
            "Segments update themselves: any contact matching every condition joins instantly, and leaves when it stops matching — what counts is the moment you send.")}
      </p>
      <Field label={bi("اسم الشريحة", "Segment name")} className="mb-4">
        <Input value={name} maxLength={80} placeholder={bi("مثلاً: مهتمّون بالعمرة", "e.g. Umrah leads")} onChange={(e) => setName(e.target.value)} />
      </Field>
      <RuleBuilder rules={rules} setRules={(v) => { setRules(v); setCount(null); }} meta={meta} />
      {error && <div className="mt-3 rounded-xl bg-red-400/10 px-3 py-2 text-[13px] text-red-200">{err(error)}</div>}
    </Modal>
  );
}

/* ------------------------------------------------------------ الاستيراد */
function ImportModal({ open, meta, setMeta, onClose, onDone }) {
  const [step, setStep] = useState(1);
  const [cc, setCc] = useState("+966");
  const [prev, setPrev] = useState(null);
  const [mapping, setMapping] = useState({});
  const [update, setUpdate] = useState(true);
  const [res, setRes] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const fileRef = useRef(null);
  useEffect(() => { if (open) { setStep(1); setPrev(null); setRes(null); setError(""); } }, [open]);

  const upload = async () => {
    const f = fileRef.current?.files?.[0];
    if (!f) { setError("file"); return; }
    setBusy(true); setError("");
    const fd = new FormData(); fd.append("file", f);
    let r;
    try {
      const resp = await fetch("/api/crm/import/preview", { method: "POST", headers: { "X-CSRF-Token": BY.csrf }, body: fd });
      r = await resp.json();
    } catch { r = { ok: false, error: "network" }; }
    setBusy(false);
    if (!r.ok) { setError(r.error); return; }
    setPrev(r); setMapping(r.guess); setStep(2);
  };
  const run = async () => {
    setBusy(true); setError("");
    const r = await call("/api/crm/import/run", { token: prev?.token, mapping, cc, update });
    setBusy(false);
    if (!r.ok) { setError(r.error); return; }
    setMeta(r); setRes(r); setStep(3); onDone();
  };

  const targets = [
    ["skip", bi("تجاهل", "Skip")], ["name", bi("الاسم", "Name")], ["phone", bi("الهاتف", "Phone")],
    ["email", bi("البريد", "Email")], ["tags", bi("الوسوم", "Tags")], ["optin", bi("موافقة تسويقية", "Marketing opt-in")],
    ["company", bi("الشركة", "Company")], ...meta.fields.filter((f) => f.active).map((f) => ["f:" + f.key, f.label]),
  ];
  return (
    <Modal open={open} onClose={onClose} icon="upload" wide title={bi("استيراد جهات الاتصال", "Import contacts")}
           footer={step === 1 ? <Btn type="button" icon="upload" onClick={upload} disabled={busy}>{bi("رفع ومعاينة", "Upload & preview")}</Btn>
             : step === 2 ? <>
                 <Btn variant="ghost" type="button" onClick={() => setStep(1)}>{bi("رجوع", "Back")}</Btn>
                 <Btn type="button" icon="check" onClick={run} disabled={busy}>{bi(`استيراد ${num(prev?.rows)} صف`, `Import ${num(prev?.rows)} rows`)}</Btn>
               </>
             : <Btn type="button" onClick={onClose}>{bi("تم", "Done")}</Btn>}>
      {step === 1 && (
        <div className="flex flex-col gap-4">
          <p className="m-0 text-[13.5px] leading-relaxed text-ink-3">
            {bi("ارفع ملف CSV أو Excel (حتى 20,000 صف). الصف الأول عناوين الأعمدة. الرقم هو مفتاح المطابقة: الجهة الموجودة تُحدَّث ولا تتكرّر.",
                "Upload a CSV or Excel file (up to 20,000 rows) with column headers in the first row. The phone number is the match key: existing contacts are updated, never duplicated.")}
          </p>
          <input ref={fileRef} type="file" accept=".csv,.xlsx,.txt"
                 className="block w-full cursor-pointer rounded-xl bg-sink/25 p-3 text-[13px] text-ink-2 file:me-3 file:cursor-pointer file:rounded-lg file:border-0 file:bg-au-violet/80 file:px-3 file:py-1.5 file:font-bold file:text-white" />
          <Field label={bi("مفتاح الدولة للأرقام المحلية (05…)", "Country code for local numbers (05…)")}>
            <Select value={cc} onChange={(e) => setCc(e.target.value)}>
              {(P.countries || []).map((c) => <option key={c[0]} value={c[1]}>{`${c[1]} — ${AR ? c[2] : c[3]}`}</option>)}
            </Select>
          </Field>
        </div>
      )}
      {step === 2 && prev && (
        <div>
          <p className="mt-0 text-[13px] text-ink-3">{bi("اربط كل عمود بالحقل المناسب — خمّنّا الربط من العناوين.", "Map each column to a field — we guessed from the headers.")}</p>
          <div className="flex flex-col gap-2">
            {prev.headers.map((h, i) => (
              <div key={i} className="grid items-center gap-2 rounded-xl bg-ov/[0.035] p-2.5 sm:grid-cols-[1fr_1.2fr_1fr]">
                <b className="truncate text-[13.5px] text-ink">{h || `#${i + 1}`}</b>
                <span className="truncate text-[12.5px] text-ink-3" dir="auto">{prev.sample.map((r) => r[i]).filter(Boolean).slice(0, 3).join(" · ") || "—"}</span>
                <Select value={mapping[String(i)] || "skip"} onChange={(e) => setMapping({ ...mapping, [String(i)]: e.target.value })}>
                  {targets.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                </Select>
              </div>
            ))}
          </div>
          <label className="mt-4 flex items-center gap-3 text-[13.5px] text-ink-2">
            <Toggle checked={update} onChange={setUpdate} label="update" />
            {bi("حدّث بيانات الجهات الموجودة (بدونها تُتخطّى)", "Update existing contacts (otherwise they're skipped)")}
          </label>
        </div>
      )}
      {step === 3 && res && (
        <div>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            {[["created", bi("جديدة", "Created"), "text-au-teal"], ["updated", bi("محدّثة", "Updated"), "text-au-cyan"],
              ["skipped", bi("متخطّاة", "Skipped"), "text-ink-2"], ["errors", bi("أخطاء", "Errors"), "text-red-300"]].map(([k, l, c]) => (
              <div key={k} className="rounded-2xl bg-ov/[0.04] p-4 text-center">
                <div className={`text-[24px] font-extrabold ${c}`}>{num(res.stats[k])}</div>
                <div className="text-[12px] text-ink-3">{l}</div>
              </div>
            ))}
          </div>
          {res.errors.length > 0 && (
            <div className="mt-4 max-h-[200px] overflow-y-auto rounded-xl bg-red-400/5 p-3 text-[12.5px] text-ink-2">
              {res.errors.map((e) => <div key={e.row}>{bi("صف", "Row")} {e.row}: {e.reason.startsWith("phone") ? err("phone") : e.reason}</div>)}
            </div>
          )}
        </div>
      )}
      {error && <div className="mt-3 rounded-xl bg-red-400/10 px-3 py-2 text-[13px] text-red-200">{err(error)}</div>}
    </Modal>
  );
}

/* ------------------------------------------------------------ تبويب الجهات */
const BASE_COLS = ["phone", "email", "tags", "optin", "company", "assignee", "source", "created", "seen"];
const COL_LABEL = {
  phone: ["الهاتف", "Phone"], email: ["البريد", "Email"], tags: ["الوسوم", "Tags"], optin: ["الموافقة", "Opt-in"],
  company: ["الشركة", "Company"], assignee: ["المسؤول", "Owner"], source: ["المصدر", "Source"],
  created: ["أُضيف", "Created"], seen: ["آخر تفاعل", "Last active"],
};

function ContactsTab({ meta, setMeta, segment, setSegment }) {
  const [q, setQ] = useState("");
  const [qDeb, setQDeb] = useState("");
  const [sort, setSort] = useState("new");
  const [per, setPer] = useState(() => store.get("crm_per", 20));
  const [page, setPage] = useState(1);
  const [data, setData] = useState({ rows: [], total: 0 });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [sel, setSel] = useState([]);
  const [edit, setEdit] = useState(null);           // null مغلق · {} جديد · جهة
  const [imp, setImp] = useState(false);
  const [cols, setCols] = useState(() => store.get("crm_cols", ["phone", "email", "tags", "optin", "created"]));
  const [colMenu, setColMenu] = useState(false);
  const [bulkTag, setBulkTag] = useState("");

  useEffect(() => { const s = setTimeout(() => setQDeb(q), 300); return () => clearTimeout(s); }, [q]);
  useEffect(() => { setPage(1); }, [qDeb, sort, per, segment]);
  const load = useCallback(async () => {
    setLoading(true);
    const u = new URLSearchParams({ q: qDeb, sort, per, page });
    if (segment) u.set("segment", segment);
    const r = await get("/api/crm/contacts?" + u);
    setLoading(false);
    if (r.ok) { setData(r); setError(""); } else setError(r.error);
  }, [qDeb, sort, per, page, segment]);
  useEffect(() => { load(); }, [load]);
  useEffect(() => { setSel([]); }, [data]);

  const tagById = useMemo(() => Object.fromEntries(meta.tags.map((x) => [x.id, x])), [meta.tags]);
  const custom = meta.fields.filter((f) => f.active);
  const toggleCol = (c) => { const n = cols.includes(c) ? cols.filter((x) => x !== c) : [...cols, c]; setCols(n); store.set("crm_cols", n); };
  const bulk = async (action, extra = {}) => {
    if (action === "delete" && !window.confirm(bi(`حذف ${sel.length} جهة نهائياً؟`, `Permanently delete ${sel.length} contacts?`))) return;
    const r = await call("/api/crm/contacts/bulk", { action, ids: sel, ...extra });
    if (r.ok) { load(); get("/api/crm/meta").then((m) => m.ok && setMeta(m)); } else setError(r.error);
  };
  const exportUrl = P.exportUrl + "?" + new URLSearchParams({ q: qDeb, ...(segment ? { segment } : {}) });
  const from = data.total ? (page - 1) * per + 1 : 0;
  const to = Math.min(page * per, data.total);

  const cell = (r, c) => {
    switch (c) {
      case "phone": return <span dir="ltr" className="tnum">{r.phone || (r.tg_id ? `Telegram ${r.tg_id}` : r.bsuid || "—")}</span>;
      case "email": return r.email || "—";
      case "tags": return <div className="flex max-w-[260px] flex-wrap gap-1">{r.tags.map((id) => <TagChip key={id} tag={tagById[id]} />)}{!r.tags.length && "—"}</div>;
      case "optin": return r.optin === 1 ? <Pill tone="on">{bi("موافق", "Yes")}</Pill> : r.optin === 0 ? <Pill tone="off">{bi("لا", "No")}</Pill> : <Pill tone="mute">—</Pill>;
      case "company": return r.company_name || "—";
      case "assignee": return r.assignee_name || "—";
      case "source": return bi(...(SOURCE_LABEL[r.source] || [r.source, r.source]));
      case "created": return fmtDay(r.created_at);
      case "seen": return fmtDay(r.last_seen_at);
      default: {
        const f = custom.find((x) => "f:" + x.key === c);
        return f ? fieldText(f, r.fields[f.key], meta.members) : "—";
      }
    }
  };
  const shown = [...BASE_COLS.filter((c) => cols.includes(c)), ...custom.map((f) => "f:" + f.key).filter((c) => cols.includes(c))];

  return (
    <>
      <Card className="!p-4 sm:!p-5">
        <div className="flex flex-wrap items-center gap-2">
          <div className="relative min-w-[200px] flex-1">
            <Icon name="search" size={16} className="pointer-events-none absolute start-3 top-1/2 -translate-y-1/2 text-ink-3" />
            <Input value={q} onChange={(e) => setQ(e.target.value)} className="!ps-9"
                   placeholder={bi("ابحث بالاسم أو الرقم أو البريد", "Search name, phone or email")} />
          </div>
          <Select className="!w-auto min-w-[170px]" value={String(segment || "")} onChange={(e) => setSegment(e.target.value ? Number(e.target.value) : null)}>
            <option value="">{bi("كل الجهات", "All contacts")}</option>
            {meta.segments.map((s) => <option key={s.id} value={String(s.id)}>{s.name}</option>)}
          </Select>
          <Select className="!w-auto" value={sort} onChange={(e) => setSort(e.target.value)}>
            <option value="new">{bi("الأحدث", "Newest")}</option>
            <option value="seen">{bi("آخر تفاعل", "Last active")}</option>
            <option value="name">{bi("الاسم", "Name")}</option>
            <option value="updated">{bi("آخر تحديث", "Recently updated")}</option>
          </Select>
          <div className="relative">
            <Btn sm variant="ghost" type="button" icon="settings" onClick={() => setColMenu(!colMenu)} aria-expanded={colMenu}>{bi("الأعمدة", "Columns")}</Btn>
            {colMenu && (
              <div className="glass absolute end-0 top-full z-30 mt-2 w-[240px] rounded-2xl p-3" onMouseLeave={() => setColMenu(false)}>
                {[...BASE_COLS.map((c) => [c, bi(...COL_LABEL[c])]), ...custom.map((f) => ["f:" + f.key, f.label])].map(([c, l]) => (
                  <label key={c} className="flex cursor-pointer items-center gap-2 rounded-lg px-2 py-1.5 text-[13px] text-ink-2 hover:bg-ov/5">
                    <input type="checkbox" checked={cols.includes(c)} onChange={() => toggleCol(c)} className="accent-[#7c6cf6]" />{l}
                  </label>
                ))}
              </div>
            )}
          </div>
          <Btn sm variant="ghost" icon="download" href={exportUrl}>{bi("تصدير", "Export")}</Btn>
          {P.canManage && <Btn sm variant="ghost" type="button" icon="upload" onClick={() => setImp(true)}>{bi("استيراد", "Import")}</Btn>}
          <Btn sm type="button" icon="plus" onClick={() => setEdit({})}>{bi("جهة اتصال", "Add contact")}</Btn>
        </div>

        {sel.length > 0 && (
          <div className="mt-3 flex flex-wrap items-center gap-2 rounded-2xl bg-au-violet/10 px-3 py-2.5 text-[13px]">
            <b className="text-ink">{bi(`${num(sel.length)} محدّدة`, `${num(sel.length)} selected`)}</b>
            <Select className="!w-auto min-w-[150px] !py-1.5" value={bulkTag} onChange={(e) => setBulkTag(e.target.value)}>
              <option value="">{bi("اختر وسماً…", "Choose a tag…")}</option>
              {meta.tags.map((x) => <option key={x.id} value={String(x.id)}>{x.name}</option>)}
            </Select>
            <Btn sm variant="ghost" type="button" icon="tag" disabled={!bulkTag} onClick={() => bulk("tag", { tags: [Number(bulkTag)] })}>{bi("وسم", "Tag")}</Btn>
            <Btn sm variant="ghost" type="button" disabled={!bulkTag} onClick={() => bulk("untag", { tags: [Number(bulkTag)] })}>{bi("إزالة الوسم", "Untag")}</Btn>
            <Select className="!w-auto min-w-[150px] !py-1.5" value="" onChange={(e) => e.target.value && bulk("assign", { assignee_id: e.target.value === "none" ? null : Number(e.target.value) })}>
              <option value="">{bi("إسناد إلى…", "Assign to…")}</option>
              <option value="none">{bi("بلا مسؤول", "Nobody")}</option>
              {meta.members.map((m) => <option key={m.id} value={String(m.id)}>{m.username}</option>)}
            </Select>
            {P.canManage && <Btn sm variant="ghost" type="button" icon="trash" onClick={() => bulk("delete")}>{bi("حذف", "Delete")}</Btn>}
          </div>
        )}
        {error && <div className="mt-3 rounded-xl bg-red-400/10 px-3 py-2 text-[13px] text-red-200">{err(error)}</div>}

        <div className="-mx-2 mt-4 overflow-x-auto px-2">
          <table className="w-full border-collapse text-[13.5px]">
            <thead>
              <tr>
                <th className="w-8 px-2 py-3 shadow-[inset_0_-1px_0_rgb(var(--ov-rgb)/0.08)]">
                  <input type="checkbox" aria-label={bi("تحديد الكل", "Select all")} className="accent-[#7c6cf6]"
                         checked={!!data.rows.length && sel.length === data.rows.length}
                         onChange={(e) => setSel(e.target.checked ? data.rows.map((r) => r.id) : [])} />
                </th>
                {[bi("الاسم", "Name"), ...shown.map((c) => (c.startsWith("f:") ? (custom.find((f) => "f:" + f.key === c) || {}).label : bi(...COL_LABEL[c])))].map((h, i) => (
                  <th key={i} className="whitespace-nowrap px-3 py-3 text-start text-[11.5px] font-extrabold uppercase tracking-wider text-ink-3 shadow-[inset_0_-1px_0_rgb(var(--ov-rgb)/0.08)]">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody className={loading ? "opacity-50 transition-opacity" : "transition-opacity"}>
              {data.rows.map((r) => (
                <tr key={r.id} className="cursor-pointer transition-colors duration-200 hover:bg-ov/[0.035]" onClick={() => setEdit(r)}>
                  <td className="px-2 py-3 shadow-[inset_0_-1px_0_rgb(var(--ov-rgb)/0.05)]" onClick={(e) => e.stopPropagation()}>
                    <input type="checkbox" aria-label={r.name || r.phone} className="accent-[#7c6cf6]" checked={sel.includes(r.id)}
                           onChange={(e) => setSel(e.target.checked ? [...sel, r.id] : sel.filter((x) => x !== r.id))} />
                  </td>
                  <td className="px-3 py-3 shadow-[inset_0_-1px_0_rgb(var(--ov-rgb)/0.05)]">
                    <span className="flex items-center gap-2.5">
                      <span className="grid size-8 shrink-0 place-items-center rounded-full bg-au-violet/20 text-[12px] font-extrabold text-au-violet">
                        {(r.name || r.phone || "?").replace("+", "").slice(0, 1).toUpperCase()}
                      </span>
                      <b className="max-w-[200px] truncate font-bold text-ink" dir="auto">{r.name || bi("بلا اسم", "No name")}</b>
                    </span>
                  </td>
                  {shown.map((c) => <td key={c} className="whitespace-nowrap px-3 py-3 text-ink-2 shadow-[inset_0_-1px_0_rgb(var(--ov-rgb)/0.05)]">{cell(r, c)}</td>)}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {!loading && !data.rows.length && (
          <Empty icon="users" title={qDeb || segment ? bi("لا نتائج", "No matches") : bi("لا جهات اتصال بعد", "No contacts yet")}
                 text={qDeb || segment ? bi("جرّب بحثاً أو شريحة أخرى.", "Try another search or segment.")
                   : bi("كل عميل يراسل بوتاتك يظهر هنا تلقائياً. أضف جهات يدوياً أو استوردها من ملف.",
                        "Every customer who messages your bots appears here automatically. Add contacts by hand or import a file.")} />
        )}
        <div className="mt-4 flex flex-wrap items-center justify-between gap-3 text-[12.5px] text-ink-3">
          <span className="flex items-center gap-2">
            {bi("صفوف في الصفحة", "Rows per page")}
            <Select className="!w-[80px] !py-1.5" value={String(per)} onChange={(e) => { const n = Number(e.target.value); setPer(n); store.set("crm_per", n); }}>
              {[20, 50, 100].map((n) => <option key={n} value={String(n)}>{n}</option>)}
            </Select>
          </span>
          <span className="flex items-center gap-2">
            <span className="tnum">{bi(`${num(from)}–${num(to)} من ${num(data.total)}`, `${num(from)}–${num(to)} of ${num(data.total)}`)}</span>
            <Btn sm variant="ghost" type="button" disabled={page <= 1} onClick={() => setPage(page - 1)}>{bi("السابق", "Previous")}</Btn>
            <Btn sm variant="ghost" type="button" disabled={to >= data.total} onClick={() => setPage(page + 1)}>{bi("التالي", "Next")}</Btn>
          </span>
        </div>
      </Card>
      <ContactModal open={edit !== null} contact={edit && edit.id ? edit : null} meta={meta} setMeta={setMeta}
                    onClose={() => setEdit(null)} onSaved={() => load()} />
      <ImportModal open={imp} meta={meta} setMeta={setMeta} onClose={() => setImp(false)} onDone={load} />
    </>
  );
}

/* ------------------------------------------------------------ تبويب الشرائح */
function SegmentsTab({ meta, setMeta, openSegment }) {
  const [edit, setEdit] = useState(null);
  const [counts, setCounts] = useState({});
  const count = async (s) => {
    const r = await call("/api/crm/segments/count", { rules: s.rules });
    setCounts((c) => ({ ...c, [s.id]: r.ok ? r.count : "!" }));
  };
  const del = async (s) => {
    if (!window.confirm(bi(`حذف الشريحة «${s.name}»؟ الجهات نفسها لا تُحذف.`, `Delete segment "${s.name}"? Contacts are kept.`))) return;
    const r = await call(`/api/crm/segments/${s.id}/delete`);
    if (r.ok) setMeta(r);
  };
  return (
    <Card>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <p className="m-0 max-w-[620px] text-[13.5px] leading-relaxed text-ink-3">
          {bi("الشريحة مجموعة ديناميكية تُبنى من شروط (الوسوم · الحقول · التواريخ · الموافقة) — تستهدفها بالبث مباشرةً.",
              "A segment is a dynamic group built from conditions (tags · fields · dates · opt-in) — target it straight from a broadcast.")}
        </p>
        {P.canManage && <Btn sm type="button" icon="plus" onClick={() => setEdit({})}>{bi("شريحة جديدة", "New segment")}</Btn>}
      </div>
      {!meta.segments.length ? (
        <Empty icon="filter" title={bi("لا شرائح بعد", "No segments yet")}
               text={bi("مثال: «وسم = عمرة» و«موافقة تسويقية = نعم» — كل من ينطبق عليه يدخل تلقائياً.",
                        "Example: \"Tag = Umrah\" and \"Marketing opt-in = Yes\" — anyone matching joins automatically.")} />
      ) : (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {meta.segments.map((s) => (
            <div key={s.id} className="rounded-2xl bg-ov/[0.035] p-4 shadow-[inset_0_0_0_1px_rgb(var(--ov-rgb)/0.06)]">
              <div className="flex items-start justify-between gap-2">
                <b className="text-[15px] text-ink" dir="auto">{s.name}</b>
                <span className="text-[12px] text-ink-3">{bi(`${s.rules.length} شرط`, `${s.rules.length} conditions`)}</span>
              </div>
              <div className="mt-3 flex flex-wrap items-center gap-2">
                <Btn sm variant="ghost" type="button" icon="users" onClick={() => count(s)}>
                  {counts[s.id] == null ? bi("عرض العدد", "View count") : counts[s.id] === "!" ? "!" : num(counts[s.id])}
                </Btn>
                <Btn sm variant="ghost" type="button" icon="arrow" onClick={() => openSegment(s.id)}>{bi("الجهات", "Contacts")}</Btn>
                {P.canManage && <>
                  <Btn sm variant="ghost" type="button" onClick={() => setEdit(s)} aria-label={bi("تعديل", "Edit")}><Icon name="edit" size={15} /></Btn>
                  <Btn sm variant="ghost" type="button" onClick={() => del(s)} aria-label={bi("حذف", "Delete")}><Icon name="trash" size={15} /></Btn>
                </>}
              </div>
            </div>
          ))}
        </div>
      )}
      <SegmentModal open={edit !== null} seg={edit && edit.id ? edit : null} meta={meta} setMeta={setMeta} onClose={() => setEdit(null)} />
    </Card>
  );
}

/* ------------------------------------------------------------ تبويب الشركات */
function CompaniesTab({ meta, setMeta }) {
  const [rows, setRows] = useState(null);
  const [q, setQ] = useState("");
  const [edit, setEdit] = useState(null);
  const [d, setD] = useState({ name: "", fields: {} });
  const [error, setError] = useState("");
  const load = useCallback(() => get("/api/crm/companies?q=" + encodeURIComponent(q)).then((r) => setRows(r.rows || [])), [q]);
  useEffect(() => { const s = setTimeout(load, 250); return () => clearTimeout(s); }, [load]);
  useEffect(() => { if (edit) { setD({ name: edit.name || "", fields: { ...(edit.fields || {}) } }); setError(""); } }, [edit]);
  const cfields = meta.companyFields.filter((f) => f.active);
  const save = async () => {
    const r = await call("/api/crm/companies", { id: edit?.id, name: d.name, fields: d.fields });
    if (r.ok) { setMeta(r); setEdit(null); load(); } else setError(r.error);
  };
  const del = async (co) => {
    if (!window.confirm(bi(`حذف «${co.name}»؟ جهاتها تبقى بلا شركة.`, `Delete "${co.name}"? Its contacts stay, without a company.`))) return;
    const r = await call(`/api/crm/companies/${co.id}/delete`);
    if (r.ok) { setMeta(r); load(); }
  };
  return (
    <Card>
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <div className="relative min-w-[200px] flex-1">
          <Icon name="search" size={16} className="pointer-events-none absolute start-3 top-1/2 -translate-y-1/2 text-ink-3" />
          <Input value={q} onChange={(e) => setQ(e.target.value)} className="!ps-9" placeholder={bi("ابحث عن شركة", "Search companies")} />
        </div>
        <Btn sm type="button" icon="plus" onClick={() => setEdit({})}>{bi("شركة", "Add company")}</Btn>
      </div>
      {rows && !rows.length ? (
        <Empty icon="store" title={bi("لا شركات بعد", "No companies yet")}
               text={bi("اربط جهات الاتصال بشركاتها — مفيد لعروض الشركات والحجوزات الجماعية.", "Link contacts to their companies — handy for corporate offers and group bookings.")} />
      ) : (
        <div className="-mx-2 overflow-x-auto px-2">
          <table className="w-full border-collapse text-[13.5px]">
            <thead><tr>{[bi("الشركة", "Company"), bi("جهات", "Contacts"), ...cfields.map((f) => f.label), bi("أُضيفت", "Created"), ""].map((h, i) => (
              <th key={i} className="whitespace-nowrap px-3 py-3 text-start text-[11.5px] font-extrabold uppercase tracking-wider text-ink-3 shadow-[inset_0_-1px_0_rgb(var(--ov-rgb)/0.08)]">{h}</th>))}</tr></thead>
            <tbody>
              {(rows || []).map((co) => (
                <tr key={co.id} className="hover:bg-ov/[0.035]">
                  <td className="px-3 py-3 font-bold text-ink shadow-[inset_0_-1px_0_rgb(var(--ov-rgb)/0.05)]" dir="auto">{co.name}</td>
                  <td className="px-3 py-3 tnum shadow-[inset_0_-1px_0_rgb(var(--ov-rgb)/0.05)]">{num(co.contacts)}</td>
                  {cfields.map((f) => <td key={f.key} className="px-3 py-3 text-ink-2 shadow-[inset_0_-1px_0_rgb(var(--ov-rgb)/0.05)]">{fieldText(f, co.fields[f.key], meta.members)}</td>)}
                  <td className="px-3 py-3 text-ink-3 shadow-[inset_0_-1px_0_rgb(var(--ov-rgb)/0.05)]">{fmtDay(co.created_at)}</td>
                  <td className="px-3 py-3 text-end shadow-[inset_0_-1px_0_rgb(var(--ov-rgb)/0.05)]">
                    <Btn sm variant="ghost" type="button" onClick={() => setEdit(co)} aria-label={bi("تعديل", "Edit")}><Icon name="edit" size={15} /></Btn>
                    {P.canManage && <Btn sm variant="ghost" type="button" onClick={() => del(co)} aria-label={bi("حذف", "Delete")}><Icon name="trash" size={15} /></Btn>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <Modal open={edit !== null} onClose={() => setEdit(null)} icon="store" title={edit?.id ? bi("تعديل شركة", "Edit company") : bi("شركة جديدة", "New company")}
             footer={<><Btn variant="ghost" type="button" onClick={() => setEdit(null)}>{t("cancel")}</Btn>
               <Btn type="button" icon="check" onClick={save} disabled={!d.name.trim()}>{bi("حفظ", "Save")}</Btn></>}>
        <Field label={bi("اسم الشركة", "Company name")}><Input value={d.name} maxLength={120} dir="auto" onChange={(e) => setD({ ...d, name: e.target.value })} /></Field>
        {cfields.map((f) => (
          <Field key={f.key} label={f.label} className="mt-4">
            <FieldInput f={f} value={d.fields[f.key]} members={meta.members} onChange={(v) => setD({ ...d, fields: { ...d.fields, [f.key]: v } })} />
          </Field>
        ))}
        {error && <div className="mt-3 rounded-xl bg-red-400/10 px-3 py-2 text-[13px] text-red-200">{err(error)}</div>}
      </Modal>
    </Card>
  );
}

/* ------------------------------------------------------------ تبويب الحقول */
function FieldsTab({ meta, setMeta }) {
  const [entity, setEntity] = useState("contact");
  const [edit, setEdit] = useState(null);
  const [d, setD] = useState({});
  const [error, setError] = useState("");
  const list = entity === "contact" ? meta.fields : meta.companyFields;
  useEffect(() => {
    if (!edit) return;
    setError("");
    setD(edit.id ? { ...edit, optionsText: (edit.options || []).join("\n") }
      : { label: "", key: "", type: "text", optionsText: "", active: 1, required: 0 });
  }, [edit]);
  const payload = (x) => ({ entity, id: x.id, label: x.label, key: x.key || undefined, type: x.type,
    options: (x.optionsText ?? (x.options || []).join("\n")).split("\n").map((s) => s.trim()).filter(Boolean),
    active: !!x.active, required: !!x.required });
  const save = async (x = d) => {
    const r = await call("/api/crm/fields", payload(x));
    if (r.ok) { setMeta(r); setEdit(null); } else setError(r.error);
    return r;
  };
  const quick = async (f, patch) => { const r = await call("/api/crm/fields", payload({ ...f, ...patch })); if (r.ok) setMeta(r); };
  const move = async (i, dir) => {
    const ids = list.map((f) => f.id);
    const j = i + dir;
    if (j < 0 || j >= ids.length) return;
    [ids[i], ids[j]] = [ids[j], ids[i]];
    const r = await call("/api/crm/fields/reorder", { entity, ids });
    if (r.ok) setMeta(r);
  };
  const del = async (f) => {
    if (!window.confirm(bi(`حذف الحقل «${f.label}»؟ ستُمسح قيمه من كل الجهات.`, `Delete field "${f.label}"? Its values are erased from every contact.`))) return;
    const r = await call(`/api/crm/fields/${f.id}/delete`);
    if (r.ok) setMeta(r);
  };
  const isNew = !d.id;
  return (
    <Card>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div className="inline-flex rounded-xl bg-sink/25 p-1">
          {[["contact", bi("جهات الاتصال", "Contacts")], ["company", bi("الشركات", "Companies")]].map(([k, l]) => (
            <button key={k} type="button" onClick={() => setEntity(k)} aria-pressed={entity === k}
                    className={`cursor-pointer rounded-lg border-0 px-4 py-1.5 text-[13px] font-bold ${entity === k ? "bg-au-violet/80 text-white" : "bg-transparent text-ink-3 hover:text-ink"}`}>{l}</button>
          ))}
        </div>
        <Btn sm type="button" icon="plus" onClick={() => setEdit({})}>{bi("حقل جديد", "Add field")}</Btn>
      </div>
      <div className="mb-4 rounded-2xl bg-ov/[0.03] p-3 text-[12.5px] leading-relaxed text-ink-3">
        {bi("الحقول القياسية ثابتة: الاسم · الهاتف · البريد · الموافقة التسويقية · الوسوم · مسؤول الجهة · الشركة. كل حقل مخصّص متاح كمتغيّر في القوالب والفلو: ",
            "Standard fields are built in: name · phone · email · marketing opt-in · tags · contact owner · company. Every custom field is a variable in templates and flows: ")}
        <code dir="ltr" className="text-au-cyan">{`{{${entity}.field.key}}`}</code>
      </div>
      {!list.length ? (
        <Empty icon="settings" title={bi("لا حقول مخصّصة بعد", "No custom fields yet")}
               text={bi("أمثلة لفندق: مرحلة العميل (اختيار) · موعد الوصول (تاريخ) · اللغة المفضلة (اختيار متعدد) · ملاحظات.",
                        "Hotel examples: Lead stage (select) · Arrival date (date) · Preferred language (multi select) · Remarks.")} />
      ) : (
        <div className="-mx-2 overflow-x-auto px-2">
          <table className="w-full border-collapse text-[13.5px]">
            <thead><tr>{["", bi("الاسم", "Label"), bi("المتغيّر", "Variable"), bi("النوع", "Type"), bi("نشط", "Active"), bi("إلزامي", "Mandatory"), ""].map((h, i) => (
              <th key={i} className="whitespace-nowrap px-3 py-3 text-start text-[11.5px] font-extrabold uppercase tracking-wider text-ink-3 shadow-[inset_0_-1px_0_rgb(var(--ov-rgb)/0.08)]">{h}</th>))}</tr></thead>
            <tbody>
              {list.map((f, i) => (
                <tr key={f.id} className="hover:bg-ov/[0.035]">
                  <td className="w-16 px-2 py-2.5 shadow-[inset_0_-1px_0_rgb(var(--ov-rgb)/0.05)]">
                    <span className="flex flex-col">
                      <button type="button" disabled={!i} onClick={() => move(i, -1)} aria-label={bi("لأعلى", "Move up")} className="cursor-pointer border-0 bg-transparent p-0 text-ink-3 hover:text-ink disabled:opacity-30">▲</button>
                      <button type="button" disabled={i === list.length - 1} onClick={() => move(i, 1)} aria-label={bi("لأسفل", "Move down")} className="cursor-pointer border-0 bg-transparent p-0 text-ink-3 hover:text-ink disabled:opacity-30">▼</button>
                    </span>
                  </td>
                  <td className="px-3 py-2.5 font-bold text-ink shadow-[inset_0_-1px_0_rgb(var(--ov-rgb)/0.05)]" dir="auto">{f.label}</td>
                  <td className="px-3 py-2.5 shadow-[inset_0_-1px_0_rgb(var(--ov-rgb)/0.05)]"><code dir="ltr" className="text-[12px] text-au-cyan">{f.key}</code></td>
                  <td className="px-3 py-2.5 text-ink-2 shadow-[inset_0_-1px_0_rgb(var(--ov-rgb)/0.05)]">{bi(...TYPE_LABEL[f.type])}</td>
                  <td className="px-3 py-2.5 shadow-[inset_0_-1px_0_rgb(var(--ov-rgb)/0.05)]"><Toggle checked={!!f.active} label={bi("نشط", "Active")} onChange={(v) => quick(f, { active: v })} /></td>
                  <td className="px-3 py-2.5 shadow-[inset_0_-1px_0_rgb(var(--ov-rgb)/0.05)]"><Toggle checked={!!f.required} label={bi("إلزامي", "Mandatory")} onChange={(v) => quick(f, { required: v })} /></td>
                  <td className="px-3 py-2.5 text-end shadow-[inset_0_-1px_0_rgb(var(--ov-rgb)/0.05)]">
                    <Btn sm variant="ghost" type="button" onClick={() => setEdit(f)} aria-label={bi("تعديل", "Edit")}><Icon name="edit" size={15} /></Btn>
                    <Btn sm variant="ghost" type="button" onClick={() => del(f)} aria-label={bi("حذف", "Delete")}><Icon name="trash" size={15} /></Btn>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <Modal open={edit !== null} onClose={() => setEdit(null)} icon="settings" title={isNew ? bi("حقل جديد", "New field") : bi("تعديل حقل", "Edit field")}
             footer={<><Btn variant="ghost" type="button" onClick={() => setEdit(null)}>{t("cancel")}</Btn>
               <Btn type="button" icon="check" onClick={() => save()} disabled={!(d.label || "").trim()}>{bi("حفظ", "Save")}</Btn></>}>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label={bi("الاسم الظاهر", "Label")}><Input value={d.label || ""} maxLength={60} dir="auto" onChange={(e) => setD({ ...d, label: e.target.value })} /></Field>
          <Field label={bi("النوع", "Type")} hint={!isNew && bi("النوع ثابت بعد الإنشاء", "Type is fixed after creation")}>
            <Select value={d.type || "text"} disabled={!isNew} onChange={(e) => setD({ ...d, type: e.target.value })}>
              {(P.types || []).map((x) => <option key={x} value={x}>{bi(...TYPE_LABEL[x])}</option>)}
            </Select>
          </Field>
          <Field label={bi("المتغيّر (بالإنجليزية)", "Variable key")} hint={isNew ? bi("يُولَّد من الاسم لو تركته فارغاً", "Generated from the label if left empty") : bi("ثابت بعد الإنشاء", "Fixed after creation")}>
            <Input dir="ltr" value={d.key || ""} disabled={!isNew} placeholder="lead_stage" maxLength={40}
                   onChange={(e) => setD({ ...d, key: e.target.value.toLowerCase().replace(/[^a-z0-9_]/g, "_") })} />
          </Field>
          <div className="flex flex-col justify-end gap-3 pb-1">
            <label className="flex items-center gap-3 text-[13.5px] text-ink-2"><Toggle checked={!!d.active} label="active" onChange={(v) => setD({ ...d, active: v })} />{bi("نشط", "Active")}</label>
            <label className="flex items-center gap-3 text-[13.5px] text-ink-2"><Toggle checked={!!d.required} label="required" onChange={(v) => setD({ ...d, required: v })} />{bi("إلزامي عند الإضافة اليدوية", "Mandatory when adding by hand")}</label>
          </div>
        </div>
        {["select", "multi_select"].includes(d.type) && (
          <Field label={bi("الخيارات — كل خيار في سطر", "Options — one per line")} className="mt-4">
            <Textarea value={d.optionsText || ""} onChange={(e) => setD({ ...d, optionsText: e.target.value })} dir="auto" />
          </Field>
        )}
        {error && <div className="mt-3 rounded-xl bg-red-400/10 px-3 py-2 text-[13px] text-red-200">{err(error)}</div>}
      </Modal>
    </Card>
  );
}

/* ------------------------------------------------------------ تبويب الوسوم */
function TagsTab({ meta, setMeta }) {
  const [name, setName] = useState("");
  const [color, setColor] = useState("cyan");
  const [edit, setEdit] = useState(null);
  const [error, setError] = useState("");
  const add = async () => {
    const r = await call("/api/crm/tags", { name, color });
    if (r.ok) { setMeta(r); setName(""); setError(""); } else setError(r.error);
  };
  const save = async () => {
    const r = await call("/api/crm/tags", edit);
    if (r.ok) { setMeta(r); setEdit(null); } else setError(r.error);
  };
  const del = async (x) => {
    if (!window.confirm(bi(`حذف الوسم «${x.name}» من ${x.contacts} جهة؟`, `Remove tag "${x.name}" from ${x.contacts} contacts?`))) return;
    const r = await call(`/api/crm/tags/${x.id}/delete`);
    if (r.ok) setMeta(r);
  };
  const ColorPick = ({ value, onChange }) => (
    <div className="flex gap-1.5">
      {(P.tagColors || []).map((c) => (
        <button key={c} type="button" onClick={() => onChange(c)} aria-label={c} aria-pressed={value === c}
                className={`size-6 cursor-pointer rounded-full border-0 ${DOT[c]} ${value === c ? "ring-2 ring-white ring-offset-2 ring-offset-transparent" : "opacity-70"}`} />
      ))}
    </div>
  );
  return (
    <Card>
      <p className="mt-0 text-[13.5px] leading-relaxed text-ink-3">
        {bi("الوسوم تصنيف سريع للجهات (VIP · عمرة · شركات · مهتم بالسعر…) — استخدمها في الفلترة والشرائح والبث. نصيحة: بادئة موحّدة مثل «نية:» أو «نوع:».",
            "Tags label contacts fast (VIP · Umrah · Corporate · price-sensitive…) — use them in filters, segments and broadcasts. Tip: consistent prefixes like \"intent:\" or \"type:\".")}
      </p>
      <div className="flex flex-wrap items-center gap-3 rounded-2xl bg-ov/[0.03] p-3">
        <Input className="!w-auto min-w-[200px] flex-1" value={name} maxLength={50} placeholder={bi("اسم الوسم", "Tag name")}
               onChange={(e) => setName(e.target.value)} onKeyDown={(e) => e.key === "Enter" && name.trim() && add()} />
        <ColorPick value={color} onChange={setColor} />
        <Btn sm type="button" icon="plus" onClick={add} disabled={!name.trim()}>{bi("أضف", "Add")}</Btn>
      </div>
      {error && <div className="mt-3 rounded-xl bg-red-400/10 px-3 py-2 text-[13px] text-red-200">{err(error)}</div>}
      <div className="mt-5 flex flex-col gap-2">
        {meta.tags.map((x) => (
          <div key={x.id} className="flex flex-wrap items-center gap-3 rounded-xl bg-ov/[0.03] px-3 py-2.5">
            {edit?.id === x.id ? (
              <>
                <Input className="!w-auto min-w-[180px] flex-1 !py-1.5" value={edit.name} maxLength={50} onChange={(e) => setEdit({ ...edit, name: e.target.value })} />
                <ColorPick value={edit.color} onChange={(c) => setEdit({ ...edit, color: c })} />
                <Btn sm type="button" icon="check" onClick={save}>{bi("حفظ", "Save")}</Btn>
                <Btn sm variant="ghost" type="button" onClick={() => setEdit(null)}>{t("cancel")}</Btn>
              </>
            ) : (
              <>
                <TagChip tag={x} />
                <span className="flex-1 text-[12.5px] text-ink-3">{bi(`${num(x.contacts)} جهة`, `${num(x.contacts)} contacts`)}</span>
                {P.canManage && <>
                  <Btn sm variant="ghost" type="button" onClick={() => setEdit({ id: x.id, name: x.name, color: x.color })} aria-label={bi("تعديل", "Edit")}><Icon name="edit" size={15} /></Btn>
                  <Btn sm variant="ghost" type="button" onClick={() => del(x)} aria-label={bi("حذف", "Delete")}><Icon name="trash" size={15} /></Btn>
                </>}
              </>
            )}
          </div>
        ))}
        {!meta.tags.length && <Empty icon="tag" title={bi("لا وسوم بعد", "No tags yet")} />}
      </div>
    </Card>
  );
}

/* ------------------------------------------------------------ الصفحة */
export default function Contacts() {
  const [meta, setMetaRaw] = useState({
    fields: P.fields || [], companyFields: P.companyFields || [], tags: P.tags || [],
    segments: P.segments || [], companies: P.companies || [], members: P.members || [],
  });
  // أي رد من /api/crm/* يحمل البيانات الوصفية المحدّثة — نأخذ منها ما يخصّنا فقط
  const setMeta = useCallback((r) => setMetaRaw((m) => ({
    fields: r.fields ?? m.fields, companyFields: r.companyFields ?? m.companyFields, tags: r.tags ?? m.tags,
    segments: r.segments ?? m.segments, companies: r.companies ?? m.companies, members: r.members ?? m.members,
  })), []);
  const tabs = [
    ["contacts", bi("جهات الاتصال", "Contacts"), "users"],
    ["segments", bi("الشرائح", "Segments"), "filter"],
    ["companies", bi("الشركات", "Companies"), "store"],
    ...(P.canManage ? [["fields", bi("الحقول", "Fields"), "settings"]] : []),
    ["tags", bi("الوسوم", "Tags"), "tag"],
  ];
  const [tab, setTab] = useState(tabs.some((x) => x[0] === P.tab) ? P.tab : "contacts");
  const [segment, setSegment] = useState(null);
  const go = (k) => {
    setTab(k);
    try { const u = new URL(window.location.href); u.searchParams.set("tab", k); window.history.replaceState(null, "", u); } catch { /* لا شيء */ }
  };
  return (
    <>
      <PageHead icon="users" title={t("contacts_title")}
                sub={bi("كل عملائك من كل القنوات في مكان واحد — صنّفهم بالوسوم والحقول، واستهدفهم بالشرائح.",
                        "Every customer from every channel in one place — label them with tags and fields, target them with segments.")} />
      <Tabs items={tabs} value={tab} onChange={go} />
      {tab === "contacts" && <ContactsTab meta={meta} setMeta={setMeta} segment={segment} setSegment={setSegment} />}
      {tab === "segments" && <SegmentsTab meta={meta} setMeta={setMeta} openSegment={(id) => { setSegment(id); go("contacts"); }} />}
      {tab === "companies" && <CompaniesTab meta={meta} setMeta={setMeta} />}
      {tab === "fields" && P.canManage && <FieldsTab meta={meta} setMeta={setMeta} />}
      {tab === "tags" && <TagsTab meta={meta} setMeta={setMeta} />}
    </>
  );
}
