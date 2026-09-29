/* البث 2.0 — المرحلة 3 من docs/ENTERPRISE_PLAN.md.
   نظرة عامة بالحالات · جدول الحملات بدوائر النِّسب · معالج من 3 خطوات (قالب ← جمهور ← جدولة)
   · تفاصيل الحملة وإعادة الاستهداف. التكلفة المعروضة تقدير؛ الخادم يعيد حسابها من Meta عند الإطلاق. */
import { useCallback, useEffect, useMemo, useState } from "react";
import { BY, P, t, bi, AR, Icon, Card, Btn, Field, Input, Select, Pill, Empty, PageHead, num, Modal, Toggle, Kpi, Tabs } from "../kit.jsx";
import { AssetPicker } from "../media.jsx";
import { WaPreview, fromComponents } from "../wa_preview.jsx";

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
const egp = (q) => (Number(q || 0) / 100).toLocaleString("en-US", { maximumFractionDigits: 2 });
const pct = (a, b) => (b ? Math.round((a / b) * 100) : 0);
const fmt = (ts) => (ts ? new Date(ts * 1000).toLocaleString(AR ? "ar-EG" : "en-GB",
  { day: "2-digit", month: "short", year: "2-digit", hour: "2-digit", minute: "2-digit" }) : "—");

const ERR = {
  bot: ["اختر قناة واتساب", "Choose a WhatsApp channel"], template: ["القالب غير معتمد أو تعذّر جلبه من Meta", "Template not approved or couldn't be fetched from Meta"],
  vars_count: ["أكمل كل متغيّرات القالب", "Fill every template variable"], var_empty: ["متغيّر نصّي فارغ", "A text variable is empty"],
  var_field: ["حقل غير معروف في المتغيّرات", "Unknown field in variables"], vars: ["متغيّرات غير صالحة", "Invalid variables"],
  header_media: ["القالب يحتاج صورة ترويسة من مكتبتك", "This template needs a header image from your library"],
  audience: ["اختر الجمهور", "Choose an audience"], schedule: ["الموعد بين دقيقة و60 يوماً من الآن", "Schedule between 1 minute and 60 days from now"],
  user: ["الموظف ليس من فريقك", "Not on your team"], rate: ["محاولات كثيرة، انتظر قليلاً", "Too many requests, wait a bit"],
  role: ["الإرسال للمالك ومديري الفريق", "Sending is for owners and team admins"], state: ["لا يمكن ذلك في حالتها الحالية", "Not possible in its current state"],
  network: ["تعذّر الاتصال", "Connection failed"],
};
const err = (c, msg) => msg || (ERR[c] ? bi(...ERR[c]) : bi("حدث خطأ", "Something went wrong") + (c ? ` (${c})` : ""));

const STATUS = {
  draft: ["مسودة", "Draft", "mute"], scheduled: ["مجدولة", "Scheduled", "warn"], running: ["تُرسل الآن", "Sending", "on"],
  done: ["اكتملت", "Completed", "on"], cancelled: ["ملغاة", "Cancelled", "mute"], failed: ["فشلت", "Failed", "off"],
};
const FAIL = {
  not_on_whatsapp: ["ليس على واتساب / لم يُسلَّم", "Not on WhatsApp / undeliverable"], frequency_limit: ["حدّ التكرار من Meta", "Frequency limit"],
  unsubscribed: ["أوقف الرسائل التسويقية", "Unsubscribed"], template: ["مشكلة في القالب", "Template issue"],
  rate_limit: ["حدود المعدّل", "Rate limit"], account: ["مشكلة في الحساب/الرقم", "Account issue"], window_closed: ["خارج نافذة 24 ساعة", "Outside 24h window"],
  experiment: ["تجربة من Meta", "Meta experiment"], invalid_request: ["طلب غير صالح", "Invalid request"],
  meta_unavailable: ["خدمة Meta غير متاحة", "Meta unavailable"], other: ["أخرى", "Other"],
};
const RETARGET = [
  ["delivered_not_replied", ["وصلته ولم يرد", "Delivered, not replied"]], ["not_read", ["لم يقرأ", "Not read"]],
  ["read", ["قرأ", "Read"]], ["replied", ["ردّ", "Replied"]], ["failed", ["فشل", "Failed"]], ["delivered", ["وصلته", "Delivered"]],
];

/* دائرة نسبة صغيرة كجدول المنافس — الرقم تحتها والنسبة من المُرسَل */
function Ring({ value, of, tone = "#7c6cf6" }) {
  const p = pct(value, of);
  const r = 9, c = 2 * Math.PI * r;
  return (
    <span className="inline-flex items-center gap-2">
      <svg width="24" height="24" viewBox="0 0 24 24" aria-hidden="true">
        <circle cx="12" cy="12" r={r} fill="none" stroke="rgb(var(--ov-rgb)/0.12)" strokeWidth="3" />
        <circle cx="12" cy="12" r={r} fill="none" stroke={tone} strokeWidth="3" strokeLinecap="round"
                strokeDasharray={`${(p / 100) * c} ${c}`} transform="rotate(-90 12 12)" />
      </svg>
      <span className="leading-tight">
        <b className="tnum block text-[13px] text-ink">{num(value)}</b>
        <span className="tnum text-[11px] text-ink-3">{p}%</span>
      </span>
    </span>
  );
}

/* ------------------------------------------------------------ المعالج */
const FIELD_SRC = () => [
  ["text", bi("نص ثابت", "Fixed text")], ["name", bi("اسم العميل", "Contact name")],
  ["phone", bi("رقم العميل", "Contact phone")], ["email", bi("بريد العميل", "Contact email")],
  ...(P.fields || []).map((f) => ["f:" + f.key, f.label]),
];

function VarRow({ n, v, onChange }) {
  const src = v.src === "contact" ? v.field : "text";
  return (
    <div className="grid items-center gap-2 sm:grid-cols-[48px_1fr_1.3fr]">
      <code dir="ltr" className="text-[12.5px] text-au-cyan">{`{{${n}}}`}</code>
      <Select value={src} onChange={(e) => onChange(e.target.value === "text" ? { src: "text", text: "" } : { src: "contact", field: e.target.value, fallback: "" })}>
        {FIELD_SRC().map(([k, l]) => <option key={k} value={k}>{l}</option>)}
      </Select>
      {v.src === "contact"
        ? <Input value={v.fallback || ""} maxLength={200} placeholder={bi("بديل لو فارغ (مثلاً: عميلنا)", "Fallback if empty (e.g. dear customer)")} onChange={(e) => onChange({ ...v, fallback: e.target.value })} />
        : <Input value={v.text || ""} maxLength={1000} placeholder={bi("النص", "Text")} onChange={(e) => onChange({ ...v, text: e.target.value })} dir="auto" />}
    </div>
  );
}

function Wizard({ open, onClose, onDone, preset }) {
  const [step, setStep] = useState(1);
  const [botId, setBotId] = useState(P.bots?.[0]?.id || "");
  const [tpls, setTpls] = useState(null);
  const [tplKey, setTplKey] = useState("");
  const [vars, setVars] = useState([]);
  const [hvars, setHvars] = useState([]);
  const [urlVars, setUrlVars] = useState({});       // المرحلة 4: متغيّر زر الرابط · الكوبون · العدّاد · البطاقات
  const [coupon, setCoupon] = useState("");
  const [expireAt, setExpireAt] = useState("");
  const [cards, setCards] = useState([]);
  const [asset, setAsset] = useState("");
  const [aud, setAud] = useState({ type: "segment", id: P.segments?.[0]?.id || "" });
  const [policy, setPolicy] = useState(true);
  const [est, setEst] = useState(null);
  const [name, setName] = useState("");
  const [when, setWhen] = useState("now");
  const [at, setAt] = useState("");
  const [retry, setRetry] = useState(false);
  const [hours, setHours] = useState(24);
  const [assign, setAssign] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!open) return;
    setStep(1); setError(""); setEst(null); setName(""); setWhen("now"); setRetry(false);
    if (preset) setAud(preset);
  }, [open, preset]);
  useEffect(() => {
    if (!open || !botId) return;
    setTpls(null); setTplKey("");
    // رموز التحقق لا تُبثّ — تُرسل من نظام العميل عبر الـAPI
    get(`/api/templates?bot=${botId}`).then((r) => setTpls(r.ok ? (r.items || []).filter((x) => x.status === "APPROVED" && x.spec?.kind !== "auth") : { error: r.error || "template" }));
  }, [open, botId]);
  const tpl = useMemo(() => (Array.isArray(tpls) ? tpls.find((x) => `${x.name}|${x.language}` === tplKey) : null), [tpls, tplKey]);
  useEffect(() => {
    setVars((tpl?.vars || []).map(() => ({ src: "text", text: "" })));
    setHvars((tpl?.header_vars || []).map(() => ({ src: "text", text: "" })));
    setAsset("");
    const sp = tpl?.spec || {};
    setUrlVars(Object.fromEntries((sp.buttons || []).filter((b) => b.url_var).map((b) => [String(b.index), { src: "text", text: "" }])));
    setCoupon(""); setExpireAt("");
    setCards((sp.cards || []).map((c) => ({ asset_id: "", vars: Array.from({ length: c.body_vars || 0 }).map(() => ({ src: "text", text: "" })) })));
  }, [tpl]);
  const estimate = useCallback(async () => {
    if (!botId || !tpl) return;
    const r = await call("/api/broadcasts/estimate", { bot_id: botId, template: tpl.name, lang: tpl.language, audience: aud, policy_optin: policy });
    setEst(r.ok ? r : { error: r.error });
  }, [botId, tpl, aud, policy]);
  useEffect(() => { if (open && step >= 2) { const s = setTimeout(estimate, 250); return () => clearTimeout(s); } return undefined; }, [open, step, estimate]);

  const media = tpl && ["IMAGE", "VIDEO"].includes(tpl.header_format);
  const spec = tpl?.spec || {};
  const filled = (v) => (v.src === "text" ? (v.text || "").trim() : v.field);
  const needCoupon = (spec.buttons || []).some((b) => b.type === "COPY_CODE");
  const needExpiry = !!spec.lto?.has_expiration;
  const varsOk = [...vars, ...hvars, ...Object.values(urlVars), ...cards.flatMap((c) => c.vars)].every(filled)
    && (!media || asset) && (!needCoupon || /^[A-Za-z0-9_-]{1,15}$/.test(coupon)) && (!needExpiry || expireAt)
    && cards.every((c) => c.asset_id);
  const audOk = aud.type !== "segment" || aud.id;
  const submit = async () => {
    setBusy(true); setError("");
    let scheduled = null;
    if (when === "later") {
      const ms = Date.parse(at);
      if (!at || Number.isNaN(ms)) { setBusy(false); setError("schedule"); return; }
      scheduled = Math.floor(ms / 1000);
    }
    const r = await call("/api/broadcasts", {
      bot_id: botId, template: tpl.name, lang: tpl.language, vars, header: media ? { asset_id: asset } : { vars: hvars },
      url: urlVars, coupon, expire_at: expireAt ? Math.floor(Date.parse(expireAt) / 1000) : null, cards,
      audience: aud, policy_optin: policy, name, scheduled_at: scheduled, retry, retry_hours: hours, assign_to: assign || null,
    });
    setBusy(false);
    if (r.ok) { onDone(); onClose(); } else setError(r.message || r.error);
  };

  const Steps = () => (
    <div className="mb-5 flex items-center gap-2 text-[12.5px] font-bold">
      {[bi("القالب", "Template"), bi("الجمهور", "Audience"), bi("الجدولة", "Schedule")].map((l, i) => (
        <span key={i} className="flex items-center gap-2">
          {i > 0 && <span className="h-px w-6 bg-ov/20" />}
          <span className={`grid size-6 place-items-center rounded-full text-[11px] ${step > i + 1 ? "bg-au-teal text-white" : step === i + 1 ? "bg-au-violet text-white" : "bg-ov/10 text-ink-3"}`}>
            {step > i + 1 ? "✓" : i + 1}
          </span>
          <span className={step === i + 1 ? "text-ink" : "text-ink-3"}>{l}</span>
        </span>
      ))}
    </div>
  );

  return (
    <Modal open={open} onClose={onClose} icon="megaphone" wide title={bi("بث جديد", "New broadcast")}
           footer={<>
             {step > 1 && <Btn variant="ghost" type="button" onClick={() => setStep(step - 1)}>{bi("رجوع", "Back")}</Btn>}
             {step < 3 && <Btn type="button" icon="arrow" disabled={step === 1 ? !(tpl && varsOk) : !(audOk && est?.count)} onClick={() => setStep(step + 1)}>{bi("التالي", "Next")}</Btn>}
             {step === 3 && <Btn type="button" icon={when === "now" ? "rocket" : "clock"} disabled={busy || (when === "later" && !at) || (est && est.billable && !est.enough && when === "now")} onClick={submit}>
               {when === "now" ? bi("أرسل الآن", "Send broadcast now") : bi("جدولة", "Schedule broadcast")}</Btn>}
           </>}>
      <Steps />
      {step === 1 && (
        <div className="grid gap-5 lg:grid-cols-[1.25fr_1fr]">
          <div className="flex flex-col gap-4">
            {(P.bots || []).length > 1 && (
              <Field label={bi("القناة", "Channel")}>
                <Select value={String(botId)} onChange={(e) => setBotId(Number(e.target.value))}>
                  {P.bots.map((b) => <option key={b.id} value={String(b.id)}>{b.name}</option>)}
                </Select>
              </Field>
            )}
            <Field label={bi("القالب المعتمد", "Approved template")}>
              {tpls === null ? <span className="text-[13px] text-ink-3">{bi("جارٍ الجلب من Meta…", "Fetching from Meta…")}</span>
                : tpls.error ? <span className="text-[13px] text-red-300">{err(tpls.error)}</span>
                : (
                  <Select value={tplKey} onChange={(e) => setTplKey(e.target.value)}>
                    <option value="">{bi("اختر قالباً…", "Choose a template…")}</option>
                    {tpls.map((x) => <option key={`${x.name}|${x.language}`} value={`${x.name}|${x.language}`}>{`${x.name} · ${x.language} · ${x.category}`}</option>)}
                  </Select>
                )}
            </Field>
            {media && (
              <Field label={bi("صورة/فيديو الترويسة", "Header media")}>
                <AssetPicker value={asset} kinds={[tpl.header_format === "VIDEO" ? "video" : "image"]} onChange={(id) => setAsset(id)} />
              </Field>
            )}
            {hvars.length > 0 && <div className="flex flex-col gap-2"><b className="text-[13px] text-ink-2">{bi("متغيّرات الترويسة", "Header variables")}</b>
              {hvars.map((v, i) => <VarRow key={i} n={i + 1} v={v} onChange={(nv) => setHvars(hvars.map((x, j) => (j === i ? nv : x)))} />)}</div>}
            {Object.keys(urlVars).length > 0 && <div className="flex flex-col gap-2"><b className="text-[13px] text-ink-2">{bi("نهاية رابط الزر لكل عميل", "Button link ending per contact")}</b>
              {Object.entries(urlVars).map(([k, v]) => <VarRow key={k} n={1} v={v} onChange={(nv) => setUrlVars({ ...urlVars, [k]: nv })} />)}</div>}
            {needCoupon && (
              <Field label={bi("كود الخصم الحيّ", "Live offer code")} hint={bi("يصل لكل مستلم بزر «نسخ الكود». حروف إنجليزية وأرقام حتى 15.", "Sent to every recipient behind the copy button. Letters/digits, max 15.")}>
                <Input dir="ltr" maxLength={15} value={coupon} placeholder="UMRAH20" onChange={(e) => setCoupon(e.target.value)} />
              </Field>
            )}
            {needExpiry && (
              <Field label={bi("ينتهي العرض في", "Offer expires at")} hint={bi("العدّاد التنازلي على هاتف العميل — بعد موعد الإرسال بربع ساعة على الأقل.", "The countdown on the customer's phone — at least 15 minutes after sending.")}>
                <Input type="datetime-local" dir="ltr" value={expireAt} onChange={(e) => setExpireAt(e.target.value)} />
              </Field>
            )}
            {cards.map((c, i) => (
              <div key={i} className="rounded-2xl bg-ov/[0.03] p-3">
                <b className="mb-2 block text-[13px] text-ink-2">{bi(`بطاقة ${i + 1}`, `Card ${i + 1}`)}</b>
                <AssetPicker compact value={c.asset_id} kinds={[spec.cards[i]?.format === "VIDEO" ? "video" : "image"]} onChange={(id) => setCards(cards.map((x, j) => (j === i ? { ...x, asset_id: id } : x)))} />
                {c.vars.map((v, k) => <div key={k} className="mt-2"><VarRow n={k + 1} v={v} onChange={(nv) => setCards(cards.map((x, j) => (j === i ? { ...x, vars: x.vars.map((y, m) => (m === k ? nv : y)) } : x)))} /></div>)}
              </div>
            ))}
            {vars.length > 0 && <div className="flex flex-col gap-2"><b className="text-[13px] text-ink-2">{bi("متغيّرات الرسالة — خصّصها لكل عميل", "Message variables — personalise per contact")}</b>
              {vars.map((v, i) => <VarRow key={i} n={i + 1} v={v} onChange={(nv) => setVars(vars.map((x, j) => (j === i ? nv : x)))} />)}</div>}
          </div>
          <WaPreview m={tpl ? fromComponents(tpl.components) : null} empty={bi("اختر قالباً لمعاينته", "Pick a template to preview it")}
                     fill={(s) => String(s || "").replace(/\{\{(\d+)\}\}/g, (m, i) => { const v = vars[Number(i) - 1]; return v?.src === "contact" ? `[${(FIELD_SRC().find((x) => x[0] === v.field) || [0, "…"])[1]}]` : v?.text || m; })} />
        </div>
      )}
      {step === 2 && (
        <div className="flex flex-col gap-4">
          <div className="grid gap-2 sm:grid-cols-3">
            {[["segment", bi("شريحة", "Segment"), "filter"], ["all", bi("كل جهات الاتصال", "All contacts"), "users"], ["subscribers", bi("مشتركو البوت", "Bot subscribers"), "bot"]].map(([k, l, i]) => (
              <button key={k} type="button" onClick={() => setAud(k === "segment" ? { type: k, id: P.segments?.[0]?.id || "" } : { type: k })}
                      aria-pressed={aud.type === k}
                      className={`flex cursor-pointer items-center gap-2 rounded-2xl border-0 p-3 text-start text-[13.5px] font-bold transition-colors
                                  ${aud.type === k ? "bg-au-violet/20 text-ink shadow-[inset_0_0_0_1.5px_rgb(124_108_246/0.8)]" : "bg-ov/[0.04] text-ink-2 hover:bg-ov/[0.07]"}`}>
                <Icon name={i} size={16} className="text-au-cyan" />{l}
              </button>
            ))}
          </div>
          {aud.type === "retarget" && (
            <div className="rounded-2xl bg-au-cyan/10 px-4 py-3 text-[13px] text-ink-2">
              {bi("إعادة استهداف من حملة سابقة: ", "Retargeting a previous campaign: ")}
              <b className="text-ink">{bi(...(RETARGET.find((x) => x[0] === aud.state) || [0, ["", ""]])[1])}</b>
            </div>
          )}
          {aud.type === "segment" && (
            (P.segments || []).length ? (
              <Field label={bi("الشريحة", "Segment")}>
                <Select value={String(aud.id || "")} onChange={(e) => setAud({ type: "segment", id: Number(e.target.value) })}>
                  {P.segments.map((s) => <option key={s.id} value={String(s.id)}>{s.name}</option>)}
                </Select>
              </Field>
            ) : <p className="m-0 text-[13px] text-ink-3">{bi("لا شرائح بعد — أنشئها من ", "No segments yet — create one in ")}<a href={P.contactsUrl + "?tab=segments"} className="text-au-cyan">{bi("جهات الاتصال", "Contacts")}</a></p>
          )}
          <label className="flex items-start gap-3 rounded-2xl bg-ov/[0.03] p-3 text-[13px] leading-relaxed text-ink-2">
            <Toggle checked={policy} onChange={setPolicy} label="policy" />
            <span><b className="text-ink">{bi("اتّبع سياسة واتساب للأعمال", "Follow WhatsApp Business Policy")}</b><br />
              {bi("نرسل التسويق لمن وافق صراحةً فقط. من طلب الإيقاف (STOP) مستبعد دائماً في كل الأحوال.",
                  "Marketing goes only to contacts who opted in. Anyone who sent STOP is always excluded, either way.")}</span>
          </label>
          <div className="grid gap-3 sm:grid-cols-3">
            <div className="rounded-2xl bg-ov/[0.04] p-4"><div className="text-[12px] text-ink-3">{bi("سيصلهم", "Recipients")}</div>
              <div className="tnum text-[24px] font-extrabold text-ink">{est ? num(est.count || 0) : "…"}</div></div>
            <div className="rounded-2xl bg-ov/[0.04] p-4"><div className="text-[12px] text-ink-3">{bi("التكلفة التقديرية", "Estimated cost")}</div>
              <div className="tnum text-[24px] font-extrabold text-ink">{est?.category == null ? "…" : est.billable ? `${egp(est.cost)} ${bi("ج.م", "EGP")}` : bi("مجانية", "Free")}</div>
              {est?.category && <div className="text-[11.5px] text-ink-3">{est.category}</div>}</div>
            <div className="rounded-2xl bg-ov/[0.04] p-4"><div className="text-[12px] text-ink-3">{bi("رصيدك", "Your balance")}</div>
              <div className="tnum text-[24px] font-extrabold text-ink">{egp(est?.balance ?? P.wallet?.balance)} {bi("ج.م", "EGP")}</div>
              {est?.billable && !est.enough && <a href={P.wallet.topupUrl} className="text-[12px] font-bold text-red-300">{bi(`ينقصك ${egp(est.short)} — اشحن`, `Short by ${egp(est.short)} — top up`)}</a>}</div>
          </div>
          {est && est.count === 0 && <p className="m-0 text-[13px] text-amber-200">{bi("لا أحد في هذا الجمهور يمكن مراسلته.", "Nobody in this audience can be messaged.")}</p>}
        </div>
      )}
      {step === 3 && (
        <div className="flex flex-col gap-4">
          <Field label={bi("اسم الحملة (اختياري)", "Broadcast name (optional)")}>
            <Input value={name} maxLength={80} placeholder={tpl ? `${tpl.name}` : ""} onChange={(e) => setName(e.target.value)} dir="auto" />
          </Field>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label={bi("موعد الإرسال", "Send broadcast")}>
              <Select value={when} onChange={(e) => setWhen(e.target.value)}>
                <option value="now">{bi("أرسل فوراً", "Send immediately")}</option>
                <option value="later">{bi("جدولة لوقت لاحق", "Schedule for later")}</option>
              </Select>
            </Field>
            {when === "later" && <Field label={bi("التاريخ والوقت", "Date & time")}><Input type="datetime-local" dir="ltr" value={at} onChange={(e) => setAt(e.target.value)} /></Field>}
          </div>
          <div className="rounded-2xl bg-ov/[0.03] p-4">
            <label className="flex items-center gap-3 text-[13.5px] font-bold text-ink">
              <Toggle checked={retry} onChange={setRetry} label="retry" />{bi("إعادة المحاولة الذكية", "Smart retry")}
              <Pill tone="on">{bi("موصى بها", "Recommended")}</Pill>
            </label>
            <p className="mb-0 mt-2 text-[12.5px] leading-relaxed text-ink-3">
              {bi("نعيد الإرسال تلقائياً كل 6 ساعات لمن فشل فشلاً مؤقتاً فقط (حدّ التكرار من Meta · حدود المعدّل · تعطّل Meta) — لا لمن ليس على واتساب أو أوقف الرسائل. كل محاولة تُحاسَب على من تُرسل إليهم وحدهم.",
                  "We automatically resend every 6 hours only to temporary failures (Meta frequency limit · rate limits · Meta outages) — never to numbers not on WhatsApp or who unsubscribed. Each retry is billed only for the contacts it resends to.")}
            </p>
            {retry && (
              <Field label={bi("حتى", "Retry until")} className="mt-3">
                <Select value={String(hours)} onChange={(e) => setHours(Number(e.target.value))}>
                  {[6, 12, 24, 48, 72].map((h) => <option key={h} value={String(h)}>{bi(`${h} ساعة بعد الإرسال`, `${h} hours after sending`)}</option>)}
                </Select>
              </Field>
            )}
          </div>
          <Field label={bi("إسناد الردود إلى (اختياري)", "Assign replies to (optional)")} hint={bi("يُحفظ مع الحملة ويُطبَّق عند تفعيل توجيه الفرق.", "Saved with the broadcast; applied once team routing is enabled.")}>
            <Select value={String(assign)} onChange={(e) => setAssign(e.target.value)}>
              <option value="">—</option>{(P.members || []).map((m) => <option key={m.id} value={String(m.id)}>{m.username}</option>)}
            </Select>
          </Field>
          <div className="rounded-2xl bg-au-violet/10 p-4 text-[13px] leading-relaxed text-ink-2">
            <b className="text-ink">{bi("الملخّص:", "Summary:")}</b>{" "}
            {bi(`القالب «${tpl?.name}» إلى ${num(est?.count || 0)} جهة`, `Template "${tpl?.name}" to ${num(est?.count || 0)} contacts`)}
            {est?.billable ? bi(` — يُحجز ${egp(est.cost)} ج.م ${when === "now" ? "الآن" : "عند موعد الإرسال"}، ويُردّ تلقائياً ما لا تقبله Meta.`,
                                 ` — ${egp(est.cost)} EGP reserved ${when === "now" ? "now" : "at send time"}; anything Meta rejects is refunded automatically.`) : "."}
          </div>
        </div>
      )}
      {error && <div className="mt-4 rounded-xl bg-red-400/10 px-3 py-2 text-[13px] text-red-200">{err(error, ERR[error] ? null : error)}</div>}
    </Modal>
  );
}

/* ------------------------------------------------------------ التفاصيل */
function Details({ id, onClose, onRetarget, reload }) {
  const [d, setD] = useState(null);
  useEffect(() => { if (id) get(`/api/broadcasts/${id}`).then((r) => setD(r.ok ? r.campaign : null)); }, [id]);
  if (!id) return null;
  const s = d?.stats;
  const stopRetry = async () => { const r = await call(`/api/broadcasts/${id}/stop-retry`); if (r.ok) { reload(); onClose(); } };
  return (
    <Modal open={!!id} onClose={onClose} icon="chart" wide title={d ? d.name : "…"}
           footer={d && <Btn variant="ghost" icon="download" href={`/broadcasts/${id}/export.csv`}>{bi("تصدير المستلمين", "Export recipients")}</Btn>}>
      {!d ? <div className="py-10 text-center text-ink-3">…</div> : (
        <div className="flex flex-col gap-5">
          <div className="flex flex-wrap gap-2 text-[12.5px] text-ink-3">
            <Pill tone={STATUS[d.status][2]}>{bi(STATUS[d.status][0], STATUS[d.status][1])}</Pill>
            <span>{d.template} · {d.bot_name}</span><span>·</span><span>{fmt(d.started_at || d.scheduled_at)}</span>
            {d.charged > 0 && <span>· {bi(`المخصوم ${egp(d.charged)} ج.م (رُدّ ${egp(d.refunded)})`, `Charged ${egp(d.charged)} EGP (refunded ${egp(d.refunded)})`)}</span>}
          </div>
          {d.error && <div className="rounded-xl bg-red-400/10 px-3 py-2 text-[13px] text-red-200">{d.error}</div>}
          {s && (
            <>
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                {[["recipients", bi("المستلمون", "Recipients"), null], ["sent", bi("أُرسلت", "Sent"), "recipients"], ["delivered", bi("وصلت", "Delivered"), "sent"],
                  ["read", bi("قُرئت", "Read"), "sent"], ["replied", bi("ردّوا", "Replied"), "sent"], ["delivered_not_replied", bi("وصلت بلا رد", "Delivered, no reply"), "sent"],
                  ["failed", bi("فشلت", "Failed"), "recipients"], ["pending", bi("قيد الإرسال", "Pending"), "recipients"]].map(([k, l, of]) => (
                  <div key={k} className="rounded-2xl bg-ov/[0.04] p-3.5">
                    <div className="text-[12px] text-ink-3">{l}</div>
                    <div className="tnum text-[22px] font-extrabold text-ink">{num(s[k])}</div>
                    {of && <div className="tnum text-[11.5px] text-ink-3">{pct(s[k], s[of])}%</div>}
                  </div>
                ))}
              </div>
              {Object.keys(s.failures).length > 0 && (
                <div>
                  <b className="mb-2 block text-[13px] text-ink-2">{bi("أسباب الفشل", "Failure reasons")}</b>
                  <div className="flex flex-col gap-1.5">
                    {Object.entries(s.failures).sort((a, b) => b[1] - a[1]).map(([k, n]) => (
                      <div key={k} className="flex items-center justify-between rounded-xl bg-red-400/5 px-3 py-2 text-[13px]">
                        <span className="text-ink-2">{bi(...(FAIL[k] || FAIL.other))}</span><b className="tnum text-ink">{num(n)}</b>
                      </div>
                    ))}
                  </div>
                </div>
              )}
              {P.canManage && (
                <div>
                  <b className="mb-2 block text-[13px] text-ink-2">{bi("أعد الاستهداف", "Retarget")}</b>
                  <div className="flex flex-wrap gap-2">
                    {RETARGET.map(([k, l]) => <Btn key={k} sm variant="ghost" icon="refresh" onClick={() => onRetarget({ type: "retarget", campaign_id: id, state: k })}>{bi(...l)}</Btn>)}
                  </div>
                </div>
              )}
            </>
          )}
          {d.retry_until && d.retry_until * 1000 > Date.now() && (
            <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl bg-au-cyan/10 px-4 py-3 text-[13px] text-ink-2">
              <span>{bi(`إعادة المحاولة الذكية مفعّلة حتى ${fmt(d.retry_until)} · محاولات: ${d.retries}`, `Smart retry on until ${fmt(d.retry_until)} · retries: ${d.retries}`)}</span>
              {P.canManage && <Btn sm variant="ghost" onClick={stopRetry}>{bi("أوقفها", "Stop")}</Btn>}
            </div>
          )}
        </div>
      )}
    </Modal>
  );
}

/* ------------------------------------------------------------ الصفحة */
export default function Broadcasts() {
  const [data, setData] = useState({ rows: [], total: 0, overview: null, counts: {} });
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState("");
  const pickStatus = (k) => { setStatus(k === "all" ? "" : k); setPage(1); };
  const [days, setDays] = useState(7);
  const [wiz, setWiz] = useState(false);
  const [preset, setPreset] = useState(null);
  const [detail, setDetail] = useState(null);
  const per = 20;
  const load = useCallback(async () => {
    const r = await get(`/api/broadcasts?page=${page}&per=${per}&days=${days}${status ? `&status=${status}` : ""}`);
    if (r.ok) setData(r);
  }, [page, days, status]);
  useEffect(() => { load(); }, [load]);
  // حملة تُرسل الآن: تحديث كل 4 ثوانٍ حتى تكتمل
  useEffect(() => {
    if (!data.rows.some((x) => x.status === "running")) return undefined;
    const s = setInterval(load, 4000);
    return () => clearInterval(s);
  }, [data, load]);
  const cancel = async (id) => {
    if (!window.confirm(bi("إلغاء هذه الحملة المجدولة؟", "Cancel this scheduled broadcast?"))) return;
    const r = await call(`/api/broadcasts/${id}/cancel`); if (r.ok) load();
  };
  const o = data.overview;
  const noBots = !(P.bots || []).length;
  return (
    <>
      <PageHead icon="megaphone" title={t("bc_title")}
                sub={bi("حملات قوالب واتساب لشرائح جهات اتصالك — فورية أو مجدولة، بتحليلات كل حالة.",
                        "WhatsApp template campaigns to your contact segments — instant or scheduled, with analytics for every state.")}
                actions={P.canManage && !noBots && <Btn icon="plus" onClick={() => { setPreset(null); setWiz(true); }}>{bi("بث جديد", "New broadcast")}</Btn>} />
      {noBots && (
        <Card className="mb-5"><Empty icon="megaphone" title={bi("اربط رقم واتساب أولاً", "Connect a WhatsApp number first")}
          text={bi("البث يُرسل من رقم واتساب الرسمي المربوط بحسابك.", "Broadcasts are sent from the official WhatsApp number connected to your account.")} /></Card>
      )}
      <Card className="mb-5">
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <b className="text-[15px] text-ink">{bi("نظرة عامة", "Overview")}</b>
          <Select className="!w-auto" value={String(days)} onChange={(e) => setDays(Number(e.target.value))}>
            {[7, 30, 90].map((d) => <option key={d} value={String(d)}>{bi(`آخر ${d} يوماً`, `Past ${d} days`)}</option>)}
          </Select>
        </div>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
          {[["recipients", bi("المستلمون", "Recipients"), "users", "text-au-cyan"], ["sent", bi("أُرسلت", "Sent"), "arrow", "text-au-violet"],
            ["delivered", bi("وصلت", "Delivered"), "check", "text-au-cyan"], ["read", bi("قُرئت", "Read"), "mail", "text-au-teal"],
            ["replied", bi("ردّوا", "Replied"), "chat", "text-amber-300"], ["failed", bi("فشلت", "Failed"), "close", "text-red-300"]].map(([k, l, i, tone]) => (
            <Kpi key={k} icon={i} tone={tone} label={l} value={o ? num(o[k]) : "…"}
                 sub={o && k !== "recipients" ? `${pct(o[k], k === "sent" || k === "failed" ? o.recipients : o.sent)}%` : null} />
          ))}
        </div>
      </Card>
      <Card>
        <b className="mb-3 block text-[15px] text-ink">{bi("الحملات", "Broadcasts")}</b>
        {Object.keys(data.counts || {}).length > 0 && (() => {
          const cn = data.counts || {};
          const all = Object.values(cn).reduce((a, b) => a + b, 0);
          return <Tabs size="sm" value={status || "all"} onChange={pickStatus} items={[
            ["all", bi("الكل", "All"), null, all],
            ...["scheduled", "running", "done", "failed", "cancelled"].filter((k) => cn[k] || status === k)
              .map((k) => [k, bi(STATUS[k][0], STATUS[k][1]), null, cn[k] || 0]),
          ]} />;
        })()}
        {!data.rows.length ? (
          status ? <Empty icon="megaphone" title={bi("لا حملات بهذه الحالة", "No broadcasts in this state")} text={bi("اختر تبويباً آخر.", "Pick another tab.")} />
          : <Empty icon="megaphone" title={bi("لا حملات بعد", "No broadcasts yet")}
                 text={bi("أنشئ أول حملة: اختر قالباً معتمداً، ثم شريحة، ثم أرسل أو جدول.", "Create your first: pick an approved template, a segment, then send or schedule.")} />
        ) : (
          <div className="-mx-2 overflow-x-auto px-2">
            <table className="w-full border-collapse text-[13px]">
              <thead><tr>{[bi("الحملة", "Broadcast"), bi("الحالة", "Status"), bi("المستلمون", "Recipients"), bi("أُرسلت", "Sent"), bi("وصلت", "Delivered"),
                bi("قُرئت", "Read"), bi("ردّوا", "Replied"), bi("فشلت", "Failed"), bi("أنشأها", "Created by"), ""].map((h, i) => (
                <th key={i} className="whitespace-nowrap px-3 py-3 text-start text-[11px] font-extrabold uppercase tracking-wider text-ink-3 shadow-[inset_0_-1px_0_rgb(var(--ov-rgb)/0.08)]">{h}</th>))}</tr></thead>
              <tbody>
                {data.rows.map((r) => {
                  const s = r.stats;
                  const st = STATUS[r.status] || STATUS.draft;
                  return (
                    <tr key={r.id} className="cursor-pointer hover:bg-ov/[0.035]" onClick={() => setDetail(r.id)}>
                      <td className="px-3 py-3 shadow-[inset_0_-1px_0_rgb(var(--ov-rgb)/0.05)]">
                        <b className="block max-w-[220px] truncate text-ink" dir="auto">{r.name}</b>
                        <span className="text-[11.5px] text-ink-3">{r.template} · {fmt(r.started_at || r.scheduled_at || r.created_at)}</span>
                      </td>
                      <td className="px-3 py-3 shadow-[inset_0_-1px_0_rgb(var(--ov-rgb)/0.05)]"><Pill tone={st[2]} dot={r.status === "running"}>{bi(st[0], st[1])}</Pill></td>
                      <td className="tnum px-3 py-3 shadow-[inset_0_-1px_0_rgb(var(--ov-rgb)/0.05)]">{num(s ? s.recipients : r.total)}</td>
                      {s ? <>
                        <td className="px-3 py-3 shadow-[inset_0_-1px_0_rgb(var(--ov-rgb)/0.05)]"><Ring value={s.sent} of={s.recipients} /></td>
                        <td className="px-3 py-3 shadow-[inset_0_-1px_0_rgb(var(--ov-rgb)/0.05)]"><Ring value={s.delivered} of={s.sent} tone="#22d3ee" /></td>
                        <td className="px-3 py-3 shadow-[inset_0_-1px_0_rgb(var(--ov-rgb)/0.05)]"><Ring value={s.read} of={s.sent} tone="#2dd4a7" /></td>
                        <td className="px-3 py-3 shadow-[inset_0_-1px_0_rgb(var(--ov-rgb)/0.05)]"><Ring value={s.replied} of={s.sent} tone="#f59e0b" /></td>
                        <td className="px-3 py-3 shadow-[inset_0_-1px_0_rgb(var(--ov-rgb)/0.05)]"><Ring value={s.failed} of={s.recipients} tone="#f87171" /></td>
                      </> : <td colSpan={5} className="px-3 py-3 text-[12px] text-ink-3 shadow-[inset_0_-1px_0_rgb(var(--ov-rgb)/0.05)]">{r.status === "scheduled" ? bi(`تُرسل ${fmt(r.scheduled_at)}`, `Sends ${fmt(r.scheduled_at)}`) : r.error || "—"}</td>}
                      <td className="px-3 py-3 text-ink-2 shadow-[inset_0_-1px_0_rgb(var(--ov-rgb)/0.05)]">{r.creator || "—"}</td>
                      <td className="px-3 py-3 text-end shadow-[inset_0_-1px_0_rgb(var(--ov-rgb)/0.05)]" onClick={(e) => e.stopPropagation()}>
                        {r.status === "scheduled" && P.canManage
                          ? <Btn sm variant="ghost" onClick={() => cancel(r.id)}>{bi("إلغاء", "Cancel")}</Btn>
                          : s && P.canManage && <Btn sm variant="ghost" icon="refresh" onClick={() => { setPreset({ type: "retarget", campaign_id: r.id, state: "delivered_not_replied" }); setWiz(true); }}>{bi("إعادة استهداف", "Retarget")}</Btn>}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
        {data.total > per && (
          <div className="mt-4 flex items-center justify-end gap-2 text-[12.5px] text-ink-3">
            <span className="tnum">{bi(`صفحة ${page} من ${Math.ceil(data.total / per)}`, `Page ${page} of ${Math.ceil(data.total / per)}`)}</span>
            <Btn sm variant="ghost" disabled={page <= 1} onClick={() => setPage(page - 1)}>{bi("السابق", "Previous")}</Btn>
            <Btn sm variant="ghost" disabled={page * per >= data.total} onClick={() => setPage(page + 1)}>{bi("التالي", "Next")}</Btn>
          </div>
        )}
      </Card>
      <Wizard open={wiz} preset={preset} onClose={() => setWiz(false)} onDone={load} />
      <Details id={detail} onClose={() => setDetail(null)} reload={load}
               onRetarget={(p) => { setDetail(null); setPreset(p); setWiz(true); }} />
    </>
  );
}
