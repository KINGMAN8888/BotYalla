/* Template Studio — المرحلة 4 من docs/ENTERPRISE_PLAN.md.
   قائمة القوالب من Meta (بحث · حالة · فئة · جودة) + محرّر لأربعة أنواع بمعاينة حيّة + نسخ + حذف
   + إرسال تجريبي. كل قاعدة تُفحص في الخادم (tpl_studio.py) قبل أن تصل Meta. */
import { useCallback, useEffect, useMemo, useState } from "react";
import { BY, P, t, bi, AR, Icon, Card, Btn, Field, Input, Textarea, Select, Pill, Empty, PageHead, Modal, Toggle } from "../kit.jsx";
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

const ERR = {
  name: ["الاسم: حروف إنجليزية صغيرة وأرقام و _ فقط (حتى 60)", "Name: lowercase letters, digits and _ only (max 60)"],
  language: ["اختر اللغة", "Choose a language"], category: ["اختر الفئة", "Choose a category"],
  required: ["حقل مطلوب فارغ", "A required field is empty"], too_long: ["نص أطول من المسموح", "Text is too long"],
  order: ["المتغيّرات بالترتيب {{1}} ثم {{2}} بلا فجوات", "Variables must go {{1}}, {{2}}… with no gaps"],
  edge_var: ["لا تبدأ الرسالة أو تنتهي بمتغيّر — Meta ترفض ذلك", "Don't start or end the message with a variable — Meta rejects it"],
  samples: ["أضف عيّنة لكل متغيّر (تراجعها Meta)", "Add a sample for every variable (Meta reviews them)"],
  one_var: ["متغيّر واحد فقط في الترويسة", "Only one variable in the header"],
  vars: ["لا متغيّرات في التذييل", "No variables in the footer"], media: ["اختر ملف العيّنة من المكتبة", "Pick the sample file from your library"],
  format: ["نوع ترويسة غير مسموح هنا", "Header type not allowed here"], limit: ["تجاوزت عدد هذا النوع من الأزرار", "Too many buttons of this type"],
  too_many: ["أزرار أكثر من المسموح", "Too many buttons"], url: ["رابط https فقط، ومتغيّر واحد في آخره", "https link only, one variable at its end"],
  url_example: ["مثال الرابط يجب أن يبدأ بنفس الرابط", "The example must start with the same link"],
  code: ["الكود حروف إنجليزية وأرقام حتى 15", "Code: letters/digits up to 15"], phone: ["رقم دولي مثل +9665…", "International number like +9665…"],
  url_required: ["زر رابط مطلوب في هذا النوع", "A URL button is required for this type"],
  code_required: ["زر الكوبون مطلوب مع العدّاد", "A coupon button is required with the countdown"],
  count: ["من 2 إلى 10 بطاقات", "2 to 10 cards"], shape: ["كل البطاقات بنفس الأزرار وترتيبها", "Every card needs the same buttons in the same order"],
  buttons: ["كل بطاقة تحتاج زراً واحداً على الأقل", "Each card needs at least one button"],
  coords: ["إحداثيات غير صالحة", "Invalid coordinates"], expiry: ["مدة الرمز من 1 إلى 90 دقيقة", "Code expiry 1–90 minutes"],
  no_waba: ["لم يُضبط WABA ID لهذا الرقم", "No WABA ID set for this number"], rate: ["محاولات كثيرة، انتظر قليلاً", "Too many requests, wait a bit"],
  meta: ["رفضت Meta الطلب", "Meta rejected the request"], network: ["تعذّر الاتصال", "Connection failed"],
};
const errText = (r) => {
  if (!r) return "";
  if (r.message) return r.message;
  const parts = String(r.error || "").split(":");
  const key = parts[parts.length - 1];
  const where = parts.length > 1 ? ` — ${parts.slice(0, -1).map((p) => (/^\d+$/.test(p) ? `#${Number(p) + 1}` : p)).join(" ")}` : "";
  return (ERR[key] ? bi(...ERR[key]) : bi("خطأ", "Error") + ` (${r.error})`) + where;
};

const KIND = {
  custom: [bi("مخصّص", "Custom"), bi("تسويق أو خدمة: ترويسة ونص وتذييل وأزرار", "Marketing or utility: header, body, footer, buttons"), "mail"],
  carousel: [bi("كاروسيل", "Carousel"), bi("رسالة ثم حتى 10 بطاقات صورة/فيديو", "A message, then up to 10 image/video cards"), "grid"],
  lto: [bi("عرض محدود المدة", "Limited-time offer"), bi("عدّاد تنازلي وكود خصم", "Countdown timer and offer code"), "clock"],
  auth: [bi("رمز تحقق", "Authentication"), bi("كود OTP بزر نسخ — Meta تكتب النص", "OTP with a copy button — WhatsApp writes the text"), "key"],
};
const STATUS_TONE = { APPROVED: "on", PENDING: "warn", REJECTED: "off", PAUSED: "off", DISABLED: "off" };
const BTN_LABEL = { QUICK_REPLY: bi("رد سريع", "Quick reply"), URL: bi("رابط", "URL"), PHONE_NUMBER: bi("اتصال", "Call phone"), COPY_CODE: bi("نسخ كود", "Copy code") };
const nextVar = (text) => { const n = (String(text || "").match(/\{\{(\d+)\}\}/g) || []).length; return `{{${n + 1}}}`; };
const ex0 = (e) => (Array.isArray(e) ? e[0] || "" : e || "");   // Meta تعيد المثال نصاً أو قائمة
const varCount = (text) => new Set((String(text || "").match(/\{\{(\d+)\}\}/g) || [])).size;

const blank = (kind = "custom") => ({
  kind, name: "", language: "ar", category: "MARKETING",
  header: { format: "NONE", text: "", samples: [], asset_id: "", location: { lat: "", lng: "", name: "", address: "" } },
  body: "", samples: [], footer: kind === "custom" ? (P.stop?.ar || "") : "", buttons: [],
  offer_text: "", has_expiration: true, card_format: "IMAGE", cardButtons: ["QUICK_REPLY"],
  cards: [{ asset_id: "", body: "", samples: [], buttons: [{}] }, { asset_id: "", body: "", samples: [], buttons: [{}] }],
  code_expiration_minutes: 10, security_recommendation: true, button_text: "Copy code",
});

/* قالب من Meta ⇒ حالة المحرّر (للنسخ). ما لا يُنسخ (عيّنات الوسائط) يُختار من جديد. */
function fromMeta(tp) {
  const d = blank(tp.spec?.kind === "auth" ? "auth" : tp.spec?.kind || "custom");
  d.name = `${tp.name}_v2`.slice(0, 60); d.language = tp.language; d.category = tp.category === "UTILITY" ? "UTILITY" : "MARKETING";
  for (const c of tp.components || []) {
    const ty = (c.type || "").toUpperCase();
    if (ty === "HEADER") d.header = { ...d.header, format: (c.format || "TEXT").toUpperCase(), text: c.text || "", samples: c.example?.header_text || [] };
    else if (ty === "BODY") { d.body = c.text || ""; d.samples = c.example?.body_text?.[0] || []; }
    else if (ty === "FOOTER") d.footer = c.text || "";
    else if (ty === "LIMITED_TIME_OFFER") { d.offer_text = c.limited_time_offer?.text || ""; d.has_expiration = !!c.limited_time_offer?.has_expiration; }
    else if (ty === "BUTTONS") d.buttons = (c.buttons || []).filter((b) => b.type !== "OTP").map((b) => ({ type: b.type, text: b.text || "", url: b.url || "", example: ex0(b.example), phone: b.phone_number || "" }));
    else if (ty === "CAROUSEL") {
      d.cards = (c.cards || []).map((cd) => {
        const f = fromComponents(cd.components);
        const btns = (cd.components.find((x) => x.type === "BUTTONS")?.buttons || []);
        return { asset_id: "", body: f.body, samples: cd.components.find((x) => x.type === "BODY")?.example?.body_text?.[0] || [],
                 buttons: btns.map((b) => ({ text: b.text || "", url: b.url || "", phone: b.phone_number || "", example: ex0(b.example) })) };
      });
      d.cardButtons = (c.cards?.[0]?.components.find((x) => x.type === "BUTTONS")?.buttons || []).map((b) => b.type);
      d.card_format = (c.cards?.[0]?.components.find((x) => x.type === "HEADER")?.format || "IMAGE").toUpperCase();
    }
  }
  if (d.kind === "carousel") d.header = { ...d.header, format: "NONE" };
  return d;
}

function Samples({ text, values, onChange, label }) {
  const n = varCount(text);
  if (!n) return null;
  return (
    <div className="mt-2 grid gap-2 sm:grid-cols-2">
      {Array.from({ length: n }).map((_, i) => (
        <Input key={i} value={values[i] || ""} placeholder={`${label || bi("عيّنة", "Sample")} {{${i + 1}}}`} dir="auto"
               onChange={(e) => { const v = [...values]; v[i] = e.target.value; onChange(v); }} />
      ))}
    </div>
  );
}

function ButtonRow({ b, onChange, onRemove, fixedType }) {
  const type = fixedType || b.type;
  return (
    <div className="grid items-start gap-2 rounded-xl bg-ov/[0.03] p-2.5 sm:grid-cols-[110px_1fr_auto]">
      <span className="pt-2.5 text-[12px] font-bold text-ink-3">{BTN_LABEL[type]}</span>
      <div className="grid gap-2 sm:grid-cols-2">
        {type !== "COPY_CODE" && <Input value={b.text || ""} maxLength={25} placeholder={bi("نص الزر", "Button text")} onChange={(e) => onChange({ ...b, text: e.target.value })} dir="auto" />}
        {type === "URL" && <Input dir="ltr" value={b.url || ""} placeholder="https://site.com/book/{{1}}" onChange={(e) => onChange({ ...b, url: e.target.value })} />}
        {type === "URL" && (b.url || "").includes("{{1}}") && <Input dir="ltr" value={b.example || ""} placeholder={bi("مثال كامل للرابط", "Full example URL")} onChange={(e) => onChange({ ...b, example: e.target.value })} />}
        {type === "PHONE_NUMBER" && <Input dir="ltr" value={b.phone || ""} placeholder="+9665xxxxxxxx" onChange={(e) => onChange({ ...b, phone: e.target.value })} />}
        {type === "COPY_CODE" && <Input dir="ltr" value={b.example || ""} maxLength={15} placeholder={bi("كود عيّنة (مثلاً UMRAH20)", "Sample code (e.g. UMRAH20)")} onChange={(e) => onChange({ ...b, example: e.target.value })} />}
      </div>
      {onRemove && <Btn sm variant="ghost" type="button" onClick={onRemove} aria-label={bi("حذف", "Remove")}><Icon name="trash" size={15} /></Btn>}
    </div>
  );
}

function Editor({ open, bot, initial, onClose, onDone }) {
  const [d, setD] = useState(blank());
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);
  const [lang, setLang] = useState("ar");
  useEffect(() => { if (open) { setD(initial || blank()); setErr(null); } }, [open, initial]);
  const set = (patch) => setD((x) => ({ ...x, ...patch }));
  const setH = (patch) => setD((x) => ({ ...x, header: { ...x.header, ...patch } }));
  const kind = d.kind;
  const headerFormats = kind === "lto" ? ["NONE", "IMAGE", "VIDEO"] : ["NONE", "TEXT", "IMAGE", "VIDEO", "LOCATION"];
  const addButton = (type) => set({ buttons: [...d.buttons, { type, text: "", url: "", example: "", phone: "" }] });
  const countOf = (type) => d.buttons.filter((b) => b.type === type).length;
  const LIMITS = kind === "lto" ? { URL: 1, COPY_CODE: 1 } : { QUICK_REPLY: 10, URL: 2, PHONE_NUMBER: 1, COPY_CODE: 1 };

  const payload = () => {
    const out = { ...d, bot_id: bot };
    if (kind === "carousel") out.cards = d.cards.map((c) => ({ ...c, buttons: d.cardButtons.map((ty, i) => ({ ...(c.buttons[i] || {}), type: ty })) }));
    if (d.header.format === "LOCATION") out.header = { ...d.header, location: { ...d.header.location } };
    return out;
  };
  const submit = async () => {
    setBusy(true); setErr(null);
    const r = await call("/api/templates", payload());
    setBusy(false);
    if (r.ok) { onDone(r); onClose(); } else setErr(r);
  };
  const preview = useMemo(() => {
    const fill = (s, samples) => String(s || "").replace(/\{\{(\d+)\}\}/g, (m, i) => samples?.[Number(i) - 1] || m);
    if (kind === "auth") return { body: bi("{{1}} هو رمز التحقق الخاص بك.", "{{1}} is your verification code.") + (d.security_recommendation ? bi(" لا تشاركه مع أحد.", " For your security, do not share this code.") : ""), footer: bi(`ينتهي خلال ${d.code_expiration_minutes} دقائق`, `This code expires in ${d.code_expiration_minutes} minutes.`), buttons: [{ type: "COPY_CODE", text: d.button_text }] };
    return {
      header: d.header.format === "NONE" || kind === "carousel" ? null : { format: d.header.format, text: fill(d.header.text, d.header.samples) },
      body: fill(d.body, d.samples), footer: kind === "custom" ? d.footer : "",
      lto: kind === "lto" ? { text: d.offer_text } : null,
      buttons: kind === "carousel" ? [] : d.buttons.map((b) => ({ type: b.type, text: b.type === "COPY_CODE" ? (kind === "lto" ? bi("نسخ كود العرض", "Copy offer code") : bi("نسخ الكود", "Copy code")) : b.text })),
      cards: kind === "carousel" ? d.cards.map((c) => ({ header: { format: d.card_format }, body: fill(c.body, c.samples), buttons: d.cardButtons.map((ty, i) => ({ type: ty, text: c.buttons[i]?.text })) })) : [],
    };
  }, [d, kind]);

  return (
    <Modal open={open} onClose={onClose} icon="mail" wide title={bi("قالب جديد", "New template")}
           footer={<><Btn variant="ghost" type="button" onClick={onClose}>{t("cancel")}</Btn>
             <Btn type="button" icon="check" disabled={busy} onClick={submit}>{busy ? bi("جارٍ الإرسال…", "Submitting…") : bi("أرسل للاعتماد", "Submit for approval")}</Btn></>}>
      <div className="mb-5 grid gap-2 sm:grid-cols-4">
        {Object.entries(KIND).map(([k, [l, s, i]]) => (
          <button key={k} type="button" aria-pressed={kind === k} onClick={() => setD({ ...blank(k), name: d.name, language: d.language })}
                  className={`cursor-pointer rounded-2xl border-0 p-3 text-start transition-colors ${kind === k ? "bg-au-violet/20 shadow-[inset_0_0_0_1.5px_rgb(124_108_246/0.8)]" : "bg-ov/[0.04] hover:bg-ov/[0.07]"}`}>
            <span className="flex items-center gap-2 text-[13.5px] font-extrabold text-ink"><Icon name={i} size={15} className="text-au-cyan" />{l}</span>
            <span className="mt-1 block text-[11.5px] leading-snug text-ink-3">{s}</span>
          </button>
        ))}
      </div>
      <div className="grid gap-6 lg:grid-cols-[1.35fr_1fr]">
        <div className="flex flex-col gap-4">
          <div className="grid gap-3 sm:grid-cols-3">
            <Field label={bi("اسم القالب", "Template name")} className="sm:col-span-1">
              <Input dir="ltr" value={d.name} maxLength={60} placeholder="umrah_offer_1448" onChange={(e) => set({ name: e.target.value.toLowerCase().replace(/\s+/g, "_") })} />
            </Field>
            <Field label={bi("اللغة", "Language")}>
              <Select value={d.language} onChange={(e) => set({ language: e.target.value })}>
                {(P.langs || []).map(([k, l]) => <option key={k} value={k}>{l}</option>)}
              </Select>
            </Field>
            {kind === "custom" && (
              <Field label={bi("الفئة", "Category")}>
                <Select value={d.category} onChange={(e) => set({ category: e.target.value, footer: e.target.value === "MARKETING" ? (d.footer || P.stop?.[d.language.slice(0, 2)] || P.stop?.en) : d.footer })}>
                  <option value="MARKETING">{bi("تسويق", "Marketing")}</option><option value="UTILITY">{bi("خدمة", "Utility")}</option>
                </Select>
              </Field>
            )}
          </div>

          {kind === "auth" ? (
            <div className="flex flex-col gap-3 rounded-2xl bg-ov/[0.03] p-4">
              <p className="m-0 text-[12.5px] leading-relaxed text-ink-3">{bi("واتساب يكتب نص رسالة التحقق بنفسه. تختار أنت مدة صلاحية الرمز وتوصية الأمان ونص الزر. زرّا «ملء تلقائي» يتطلّبان تطبيق أندرويد خاصاً بك — المتاح هنا «نسخ الكود» ويعمل على كل الأجهزة.", "WhatsApp writes the verification text itself. You pick the code expiry, the security note and the button text. Autofill buttons need your own Android app — Copy code works on every device.")}</p>
              <label className="flex items-center gap-3 text-[13px] text-ink-2"><Toggle checked={d.security_recommendation} label="sec" onChange={(v) => set({ security_recommendation: v })} />{bi("أضف توصية الأمان", "Add security recommendation")}</label>
              <div className="grid gap-3 sm:grid-cols-2">
                <Field label={bi("صلاحية الرمز (دقائق)", "Code expiry (minutes)")}><Input type="number" min="1" max="90" dir="ltr" value={d.code_expiration_minutes} onChange={(e) => set({ code_expiration_minutes: e.target.value })} /></Field>
                <Field label={bi("نص الزر", "Button text")}><Input value={d.button_text} maxLength={25} onChange={(e) => set({ button_text: e.target.value })} /></Field>
              </div>
            </div>
          ) : (
            <>
              {kind !== "carousel" && (
                <Field label={bi("الترويسة (اختيارية)", "Header (optional)")}>
                  <div className="flex flex-wrap gap-1.5">
                    {headerFormats.map((f) => (
                      <button key={f} type="button" aria-pressed={d.header.format === f} onClick={() => setH({ format: f })}
                              className={`cursor-pointer rounded-full border-0 px-3 py-1.5 text-[12px] font-bold ${d.header.format === f ? "bg-au-violet text-white" : "bg-ov/[0.06] text-ink-2 hover:bg-ov/10"}`}>
                        {{ NONE: bi("بلا", "None"), TEXT: bi("نص", "Text"), IMAGE: bi("صورة", "Image"), VIDEO: bi("فيديو", "Video"), LOCATION: bi("موقع", "Location") }[f]}
                      </button>
                    ))}
                  </div>
                  {d.header.format === "TEXT" && (<>
                    <div className="mt-2 flex gap-2"><Input value={d.header.text} maxLength={60} dir="auto" placeholder={bi("مثلاً: عرض {{1}}", "e.g. Offer for {{1}}")} onChange={(e) => setH({ text: e.target.value })} />
                      <Btn sm variant="ghost" type="button" disabled={varCount(d.header.text) >= 1} onClick={() => setH({ text: `${d.header.text} {{1}}` })}>{"{{x}}"}</Btn></div>
                    <Samples text={d.header.text} values={d.header.samples} onChange={(v) => setH({ samples: v })} />
                  </>)}
                  {["IMAGE", "VIDEO"].includes(d.header.format) && <div className="mt-2"><AssetPicker value={d.header.asset_id} kinds={[d.header.format === "VIDEO" ? "video" : "image"]} onChange={(id) => setH({ asset_id: id })} /><span className="mt-1 block text-[11.5px] text-ink-3">{bi("عيّنة تراجعها Meta — عند الإرسال تختار الملف الفعلي.", "A sample for Meta's review — you pick the real file when sending.")}</span></div>}
                  {d.header.format === "LOCATION" && (
                    <div className="mt-2 grid gap-2 sm:grid-cols-2">
                      {[["name", bi("اسم المكان", "Place name")], ["address", bi("العنوان", "Address")], ["lat", bi("خط العرض", "Latitude")], ["lng", bi("خط الطول", "Longitude")]].map(([k, l]) => (
                        <Input key={k} dir={k === "lat" || k === "lng" ? "ltr" : "auto"} placeholder={l} value={d.header.location[k]} onChange={(e) => setH({ location: { ...d.header.location, [k]: e.target.value } })} />
                      ))}
                      <span className="text-[11.5px] text-ink-3 sm:col-span-2">{bi("الدبّوس يُحفظ عندنا ويُرسل مع كل رسالة من هذا القالب.", "The pin is saved with us and sent with every message from this template.")}</span>
                    </div>
                  )}
                </Field>
              )}
              {kind === "lto" && (
                <div className="grid gap-3 rounded-2xl bg-ov/[0.03] p-4 sm:grid-cols-2">
                  <Field label={bi("سطر العرض (حتى 16 حرفاً)", "Offer line (max 16)")}><Input value={d.offer_text} maxLength={16} placeholder={bi("ينتهي قريباً!", "Expiring offer!")} onChange={(e) => set({ offer_text: e.target.value })} /></Field>
                  <label className="flex items-center gap-3 self-end pb-2 text-[13px] text-ink-2"><Toggle checked={d.has_expiration} label="exp" onChange={(v) => set({ has_expiration: v })} />{bi("عدّاد تنازلي (موعد يُحدَّد عند الإرسال)", "Countdown (date set when sending)")}</label>
                </div>
              )}
              <Field label={kind === "carousel" ? bi("الرسالة فوق البطاقات", "Message above the cards") : bi("نص الرسالة", "Message body")}>
                <Textarea value={d.body} maxLength={1024} dir="auto" onChange={(e) => set({ body: e.target.value })}
                          placeholder={bi("مرحباً {{1}}، أسعار موسم العمرة 1448هـ متاحة الآن…", "Hello {{1}}, our Umrah season rates are now available…")} />
                <div className="mt-1 flex items-center justify-between text-[11.5px] text-ink-3">
                  <Btn sm variant="ghost" type="button" onClick={() => set({ body: `${d.body} ${nextVar(d.body)} ` })}>{bi("+ متغيّر", "+ Variable")}</Btn>
                  <span className="tnum">{d.body.length}/1024</span>
                </div>
                <Samples text={d.body} values={d.samples} onChange={(v) => set({ samples: v })} />
              </Field>
              {kind === "custom" && (
                <Field label={bi("التذييل (اختياري)", "Footer (optional)")} hint={d.category === "MARKETING" ? bi("أبقِ سطر الإيقاف STOP — Meta ترفض التسويق بدونه.", "Keep the STOP line — Meta rejects marketing without an opt-out.") : null}>
                  <Input value={d.footer} maxLength={60} dir="auto" onChange={(e) => set({ footer: e.target.value })} />
                </Field>
              )}
              {kind === "carousel" ? (
                <div className="flex flex-col gap-3">
                  <div className="grid gap-3 sm:grid-cols-2">
                    <Field label={bi("نوع البطاقات", "Card media")}>
                      <Select value={d.card_format} onChange={(e) => set({ card_format: e.target.value })}>
                        <option value="IMAGE">{bi("صور", "Images")}</option><option value="VIDEO">{bi("فيديو", "Videos")}</option>
                      </Select>
                    </Field>
                    <Field label={bi("أزرار كل بطاقة (نفسها للكل)", "Buttons per card (same for all)")}>
                      <div className="flex gap-2">
                        {[0, 1].map((i) => (
                          <Select key={i} value={d.cardButtons[i] || ""} onChange={(e) => { const v = [...d.cardButtons]; if (e.target.value) v[i] = e.target.value; else v.splice(i, 1); set({ cardButtons: v.filter(Boolean) }); }}>
                            {i === 1 && <option value="">—</option>}
                            {["QUICK_REPLY", "URL", "PHONE_NUMBER"].map((ty) => <option key={ty} value={ty}>{BTN_LABEL[ty]}</option>)}
                          </Select>
                        ))}
                      </div>
                    </Field>
                  </div>
                  {d.cards.map((c, i) => (
                    <div key={i} className="rounded-2xl bg-ov/[0.03] p-3">
                      <div className="mb-2 flex items-center justify-between"><b className="text-[13px] text-ink">{bi(`بطاقة ${i + 1}`, `Card ${i + 1}`)}</b>
                        {d.cards.length > 2 && <Btn sm variant="ghost" type="button" onClick={() => set({ cards: d.cards.filter((_, j) => j !== i) })}><Icon name="trash" size={14} /></Btn>}</div>
                      <AssetPicker compact value={c.asset_id} kinds={[d.card_format === "VIDEO" ? "video" : "image"]} onChange={(id) => set({ cards: d.cards.map((x, j) => (j === i ? { ...x, asset_id: id } : x)) })} />
                      <Textarea className="mt-2 !min-h-[64px]" maxLength={160} value={c.body} dir="auto" placeholder={bi("نص البطاقة", "Card text")} onChange={(e) => set({ cards: d.cards.map((x, j) => (j === i ? { ...x, body: e.target.value } : x)) })} />
                      <Samples text={c.body} values={c.samples} onChange={(v) => set({ cards: d.cards.map((x, j) => (j === i ? { ...x, samples: v } : x)) })} />
                      <div className="mt-2 flex flex-col gap-2">
                        {d.cardButtons.map((ty, k) => <ButtonRow key={k} fixedType={ty} b={c.buttons[k] || {}} onChange={(nb) => set({ cards: d.cards.map((x, j) => (j === i ? { ...x, buttons: Object.assign([...x.buttons], { [k]: nb }) } : x)) })} />)}
                      </div>
                    </div>
                  ))}
                  {d.cards.length < 10 && <Btn sm variant="ghost" type="button" icon="plus" onClick={() => set({ cards: [...d.cards, { asset_id: "", body: "", samples: [], buttons: [] }] })}>{bi("بطاقة", "Add card")}</Btn>}
                </div>
              ) : (
                <div className="flex flex-col gap-2">
                  <b className="text-[13px] text-ink-2">{bi("الأزرار (اختيارية)", "Buttons (optional)")}</b>
                  {d.buttons.map((b, i) => <ButtonRow key={i} b={b} onChange={(nb) => set({ buttons: d.buttons.map((x, j) => (j === i ? nb : x)) })} onRemove={() => set({ buttons: d.buttons.filter((_, j) => j !== i) })} />)}
                  <div className="flex flex-wrap gap-1.5">
                    {Object.keys(LIMITS).map((ty) => (
                      <Btn key={ty} sm variant="ghost" type="button" icon="plus" disabled={countOf(ty) >= LIMITS[ty] || d.buttons.length >= 10} onClick={() => addButton(ty)}>{BTN_LABEL[ty]}</Btn>
                    ))}
                  </div>
                  {d.buttons.length > 3 && <span className="text-[11.5px] text-ink-3">{bi("أكثر من 3 أزرار تظهر كقائمة في واتساب.", "More than 3 buttons show as a list in WhatsApp.")}</span>}
                </div>
              )}
            </>
          )}
        </div>
        <div className="lg:sticky lg:top-0 lg:self-start">
          <b className="mb-2 block text-[12.5px] text-ink-3">{bi("معاينة", "Preview")}</b>
          <WaPreview m={preview} />
        </div>
      </div>
      {err && <div className="mt-4 rounded-xl bg-red-400/10 px-3 py-2 text-[13px] text-red-200">{errText(err)}</div>}
    </Modal>
  );
}

function TestSend({ bot, tp, onClose }) {
  const [phones, setPhones] = useState("");
  const [vals, setVals] = useState({});
  const [cards, setCards] = useState([]);
  const [res, setRes] = useState(null);
  const [busy, setBusy] = useState(false);
  const spec = tp?.spec || {};
  useEffect(() => { setPhones(""); setVals({}); setRes(null); setCards((spec.cards || []).map(() => ({ asset_id: "", vars: [] }))); }, [tp]); // eslint-disable-line
  if (!tp) return null;
  const txt = (s) => ({ src: "text", text: s || "-" });
  const send = async () => {
    setBusy(true);
    const url = {};
    (spec.buttons || []).filter((b) => b.url_var).forEach((b) => { url[String(b.index)] = txt(vals[`u${b.index}`]); });
    const r = await call("/api/templates/test", {
      bot_id: bot, template: tp.name, lang: tp.language, phones: phones.split(/[,\s]+/).filter(Boolean),
      vars: Array.from({ length: spec.body_vars || 0 }).map((_, i) => txt(vals[`b${i}`])),
      header: spec.header_format === "TEXT" ? { vars: Array.from({ length: spec.header_vars || 0 }).map((_, i) => txt(vals[`h${i}`])) } : { asset_id: vals.media },
      url, coupon: vals.coupon, expire_at: vals.exp ? Math.floor(Date.parse(vals.exp) / 1000) : null,
      cards: cards.map((c, i) => ({ asset_id: c.asset_id, vars: Array.from({ length: spec.cards[i].body_vars }).map((_, k) => txt(c.vars[k])) })),
    });
    setBusy(false); setRes(r);
  };
  // دالة لا مكوّن: مكوّن معرَّف داخل الرسم يُعاد إنشاؤه كل ضغطة فيفقد الحقل تركيزه
  const In = ({ k, ph, ltr }) => <Input key={k} dir={ltr ? "ltr" : "auto"} placeholder={ph} value={vals[k] || ""} onChange={(e) => setVals({ ...vals, [k]: e.target.value })} />;
  return (
    <Modal open={!!tp} onClose={onClose} icon="rocket" title={bi(`إرسال تجريبي: ${tp.name}`, `Test: ${tp.name}`)}
           footer={<Btn type="button" icon="rocket" disabled={busy || !phones.trim()} onClick={send}>{bi("أرسل", "Send test")}</Btn>}>
      <div className="flex flex-col gap-3">
        <Field label={bi("حتى 5 أرقام (مفصولة بفاصلة)", "Up to 5 numbers (comma-separated)")} hint={bi("رسالة التسويق التجريبية تُحاسَب كأي رسالة وتُردّ لو لم تُقبل.", "A marketing test is billed like any message and refunded if not accepted.")}>
          <Input dir="ltr" value={phones} placeholder="0501234567, +201001234567" onChange={(e) => setPhones(e.target.value)} />
        </Field>
        {Array.from({ length: spec.header_vars || 0 }).map((_, i) => In({ k: `h${i}`, ph: `${bi("الترويسة", "Header")} {{${i + 1}}}` }))}
        {["IMAGE", "VIDEO"].includes(spec.header_format) && <AssetPicker value={vals.media} kinds={[spec.header_format === "VIDEO" ? "video" : "image"]} onChange={(id) => setVals({ ...vals, media: id })} />}
        {Array.from({ length: spec.body_vars || 0 }).map((_, i) => In({ k: `b${i}`, ph: `{{${i + 1}}}` }))}
        {(spec.buttons || []).filter((b) => b.url_var).map((b) => In({ k: `u${b.index}`, ltr: true, ph: bi(`نهاية رابط «${b.text}»`, `End of "${b.text}" link`) }))}
        {(spec.buttons || []).some((b) => b.type === "COPY_CODE") && In({ k: "coupon", ltr: true, ph: bi("الكود الحيّ", "Live code") })}
        {spec.lto?.has_expiration && <Input type="datetime-local" dir="ltr" value={vals.exp || ""} onChange={(e) => setVals({ ...vals, exp: e.target.value })} />}
        {(spec.cards || []).map((c, i) => (
          <div key={i} className="rounded-xl bg-ov/[0.03] p-2.5">
            <b className="text-[12.5px] text-ink-2">{bi(`بطاقة ${i + 1}`, `Card ${i + 1}`)}</b>
            <div className="mt-1.5"><AssetPicker compact value={cards[i]?.asset_id} kinds={[c.format === "VIDEO" ? "video" : "image"]} onChange={(id) => setCards(cards.map((x, j) => (j === i ? { ...x, asset_id: id } : x)))} /></div>
            {Array.from({ length: c.body_vars }).map((_, k) => <Input key={k} className="mt-1.5" placeholder={`{{${k + 1}}}`} value={cards[i]?.vars[k] || ""} onChange={(e) => setCards(cards.map((x, j) => (j === i ? { ...x, vars: Object.assign([...x.vars], { [k]: e.target.value }) } : x)))} />)}
          </div>
        ))}
        {res && (res.ok ? <div className="rounded-xl bg-au-teal/10 px-3 py-2 text-[13px] text-ink-2">{bi("أُرسل — تابع النتيجة في «البث».", "Sent — follow the result under Broadcasts.")}</div>
                        : <div className="rounded-xl bg-red-400/10 px-3 py-2 text-[13px] text-red-200">{res.message || errText(res)}</div>)}
      </div>
    </Modal>
  );
}

export default function TemplateStudio() {
  const [bot, setBot] = useState(P.bots?.[0]?.id || "");
  const [items, setItems] = useState(null);
  const [error, setError] = useState(null);
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("");
  const [cat, setCat] = useState("");
  const [editor, setEditor] = useState(null);     // null مغلق · {initial}
  const [test, setTest] = useState(null);
  const [note, setNote] = useState("");
  const load = useCallback(async () => {
    if (!bot) return;
    setItems(null); setError(null);
    const r = await call(`/api/templates?bot=${bot}`, null, "GET");
    if (r.ok) setItems(r.items); else { setItems([]); setError(r); }
  }, [bot]);
  useEffect(() => { load(); }, [load]);
  const shown = useMemo(() => (items || []).filter((x) =>
    (!q || x.name.includes(q.toLowerCase())) && (!status || x.status === status) && (!cat || x.category === cat)), [items, q, status, cat]);
  const del = async (tp) => {
    if (!window.confirm(bi(`حذف «${tp.name}» من Meta بكل لغاته؟ لا يمكن إعادة استخدام الاسم 30 يوماً.`, `Delete "${tp.name}" from Meta in all languages? The name can't be reused for 30 days.`))) return;
    const r = await call("/api/templates/delete", { bot_id: bot, name: tp.name });
    if (r.ok) load(); else setError(r);
  };
  if (!(P.bots || []).length) {
    return (<><PageHead icon="mail" title={t("tpl_studio_title")} /><Card><Empty icon="mail" title={bi("اربط رقم واتساب أولاً", "Connect a WhatsApp number first")} /></Card></>);
  }
  return (
    <>
      <PageHead icon="mail" title={t("tpl_studio_title")}
                sub={bi("أنشئ قوالب واتساب بكل أنواعها، تابع اعتمادها وجودتها من Meta، واستخدمها في البث.", "Create every kind of WhatsApp template, track approval and quality from Meta, and use them in broadcasts.")}
                actions={P.canManage && <Btn icon="plus" onClick={() => setEditor({ initial: null })}>{bi("قالب جديد", "New template")}</Btn>} />
      {note && <div className="mb-4 rounded-2xl bg-au-teal/10 px-4 py-3 text-[13.5px] text-ink-2">{note}</div>}
      <Card className="mb-5 !p-4">
        <div className="flex flex-wrap items-center gap-2">
          {(P.bots || []).length > 1 && (
            <Select className="!w-auto" value={String(bot)} onChange={(e) => setBot(Number(e.target.value))}>
              {P.bots.map((b) => <option key={b.id} value={String(b.id)}>{b.name}</option>)}
            </Select>
          )}
          <div className="relative min-w-[180px] flex-1">
            <Icon name="search" size={16} className="pointer-events-none absolute start-3 top-1/2 -translate-y-1/2 text-ink-3" />
            <Input className="!ps-9" value={q} placeholder={bi("ابحث باسم القالب", "Search by name")} onChange={(e) => setQ(e.target.value)} />
          </div>
          <Select className="!w-auto" value={status} onChange={(e) => setStatus(e.target.value)}>
            <option value="">{bi("كل الحالات", "All statuses")}</option>
            {["APPROVED", "PENDING", "REJECTED", "PAUSED", "DISABLED"].map((s) => <option key={s} value={s}>{s}</option>)}
          </Select>
          <Select className="!w-auto" value={cat} onChange={(e) => setCat(e.target.value)}>
            <option value="">{bi("كل الفئات", "All categories")}</option>
            {["MARKETING", "UTILITY", "AUTHENTICATION"].map((s) => <option key={s} value={s}>{s}</option>)}
          </Select>
          <Btn sm variant="ghost" icon="refresh" onClick={load}>{bi("مزامنة من Meta", "Sync from Meta")}</Btn>
        </div>
      </Card>
      {error && <div className="mb-4 rounded-xl bg-red-400/10 px-3 py-2 text-[13px] text-red-200">{errText(error)}</div>}
      {items === null ? <Card><div className="py-10 text-center text-ink-3">{bi("جارٍ الجلب من Meta…", "Fetching from Meta…")}</div></Card>
        : !shown.length ? <Card><Empty icon="mail" title={bi("لا قوالب", "No templates")} text={bi("أنشئ أول قالب — يراجعه Meta عادةً خلال دقائق إلى 24 ساعة.", "Create your first — Meta usually reviews within minutes to 24 hours.")} /></Card>
        : (
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {shown.map((tp) => (
              <Card key={`${tp.name}|${tp.language}`} className="!p-4">
                <div className="mb-3 flex flex-wrap items-start justify-between gap-2">
                  <div className="min-w-0">
                    <b className="block truncate text-[14px] text-ink" dir="ltr">{tp.name}</b>
                    <span className="text-[11.5px] text-ink-3">{tp.language} · {tp.category}{tp.spec?.kind && tp.spec.kind !== "custom" ? ` · ${KIND[tp.spec.kind]?.[0]}` : ""}</span>
                  </div>
                  <span className="flex gap-1.5">
                    <Pill tone={STATUS_TONE[tp.status] || "mute"}>{tp.status}</Pill>
                    {tp.quality && tp.quality !== "UNKNOWN" && <Pill tone={tp.quality === "GREEN" ? "on" : tp.quality === "YELLOW" ? "warn" : "off"}>{tp.quality}</Pill>}
                  </span>
                </div>
                <WaPreview m={fromComponents(tp.components)} />
                {tp.rejected_reason && tp.rejected_reason !== "NONE" && <p className="mb-0 mt-2 text-[12px] text-red-300">{bi("سبب الرفض: ", "Rejected: ")}{tp.rejected_reason}</p>}
                <div className="mt-3 flex flex-wrap gap-1.5">
                  {P.canManage && tp.status === "APPROVED" && tp.spec?.kind !== "auth" && <Btn sm variant="ghost" icon="rocket" onClick={() => setTest(tp)}>{bi("تجربة", "Test")}</Btn>}
                  {tp.status === "APPROVED" && tp.spec?.kind !== "auth" && <Btn sm variant="ghost" icon="megaphone" href={P.broadcastsUrl}>{bi("بثّه", "Broadcast")}</Btn>}
                  {P.canManage && <Btn sm variant="ghost" icon="copy" onClick={() => setEditor({ initial: fromMeta(tp) })}>{bi("نسخ", "Duplicate")}</Btn>}
                  {P.canManage && <Btn sm variant="ghost" onClick={() => del(tp)} aria-label={bi("حذف", "Delete")}><Icon name="trash" size={15} /></Btn>}
                </div>
              </Card>
            ))}
          </div>
        )}
      <Editor open={!!editor} bot={bot} initial={editor?.initial} onClose={() => setEditor(null)}
              onDone={(r) => { setNote(bi(`أُرسل «${r.name}» للاعتماد — الحالة: ${r.status}. حدّث القائمة بعد قليل.`, `"${r.name}" submitted — status: ${r.status}. Refresh in a bit.`)); load(); }} />
      <TestSend bot={bot} tp={test} onClose={() => setTest(null)} />
    </>
  );
}
