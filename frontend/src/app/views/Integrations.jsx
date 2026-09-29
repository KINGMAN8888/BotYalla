/* التكاملات — المرحلة 9: سلة · زد · Shopify · WooCommerce · Webhook (Zapier / Make / محرك الحجز).
   حدث من المتجر ⇒ قالب واتساب معتمد بمتغيّرات الطلب · وسوم · تسلسل متابعة. السرّ يُكتب ولا يُقرأ أبداً. */
import { useEffect, useState } from "react";
import { BY, P, bi, AR, Icon, Card, Btn, Field, Input, Select, Pill, Empty, PageHead, num, Modal, Toggle } from "../kit.jsx";

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
  name: bi("اكتب اسماً", "Enter a name"), bot: bi("اختر رقم واتساب", "Pick a WhatsApp number"), cc: bi("مفتاح دولة مثل +966", "A country code like +966"),
  secret: bi("السرّ طويل جداً", "Secret is too long"), limit: bi("وصلت للحد الأقصى (20)", "Limit reached (20)"), provider: bi("مزوّد غير معروف", "Unknown provider"),
  "rule:event": bi("اسم حدث غير صالح أو مكرّر", "Invalid or duplicate event name"), "rule:action": bi("كل قاعدة تحتاج إجراءً واحداً على الأقل (قالب أو وسم أو تسلسل)", "Each rule needs at least one action (template, tag or sequence)"),
  "rule:template": bi("اختر قالباً معتمداً", "Choose an approved template"), "rule:sequence": bi("التسلسل ليس على هذا الرقم", "That sequence is not on this number"),
  "rule:rules": bi("قواعد غير صالحة", "Invalid rules"),
  sheet: bi("تعذّر قراءة الجدول — تأكّد أن الرابط من Google Sheets ومشارك «لأي شخص لديه الرابط»", "Could not read the sheet — make sure it's a Google Sheets link shared with “Anyone with the link”"), role: bi("للمالك والمدير فقط", "Owners and admins only"), network: bi("تعذّر الاتصال", "Connection failed"),
};
const PAGE_ERR = { page_token: bi("التوكن غير صالح أو منتهٍ", "The token is invalid or expired"), page_page: bi("التوكن لا يصل لهذه الصفحة", "This token has no access to that Page"),
  page_subscribe: bi("رفضت Meta الاشتراك في نماذج العملاء — يحتاج التطبيق إذن leads_retrieval وأن تكون مسؤولاً عن الصفحة", "Meta refused the lead-form subscription — the app needs leads_retrieval and you must manage the Page") };
const errOf = (r) => (PAGE_ERR[r.error] ? `${PAGE_ERR[r.error]}${r.message ? ` — ${r.message}` : ""}` : ERR[r.error] || bi("حدث خطأ", "Something went wrong"));
const copy = (s) => { try { navigator.clipboard.writeText(s); } catch { /* */ } };
const when = (ts) => (ts ? new Date(ts * 1000).toLocaleString(AR ? "ar-EG" : "en-GB", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" }) : "—");

const PROV = {
  salla: { name: bi("سلة", "Salla"), color: "#004956", sub: bi("طلبات المتجر وحالتها والسلات المتروكة", "Store orders, status and abandoned carts"),
    sig: bi("من لوحة شركاء سلة ← Webhooks ← «Signature»: الصق مفتاح التوقيع هنا", "Salla Partners → Webhooks → “Signature”: paste the signing key here"),
    steps: [bi("لوحة شركاء سلة ← تطبيقك ← Webhooks", "Salla Partners → your app → Webhooks"), bi("أضف الرابط أدناه للأحداث: order.created · order.status.updated · abandoned.cart", "Add the URL below for: order.created · order.status.updated · abandoned.cart"), bi("اختر الحماية «Signature» والصق مفتاحها في «سرّ التوقيع»", "Choose “Signature” security and paste its key in “Signing secret”")] },
  zid: { name: bi("زد", "Zid"), color: "#7c3aed", sub: bi("طلبات المتجر وحالتها", "Store orders and status"),
    sig: bi("اختياري — الرمز الذي تضعه في ترويسة الطلب (X-Zid-Token)", "Optional — the token you set as a request header (X-Zid-Token)"),
    steps: [bi("لوحة شركاء زد ← تطبيقك ← Webhooks", "Zid Partners → your app → Webhooks"), bi("اشترك في حدث تحديث الطلب وألصق الرابط أدناه", "Subscribe to the order update event and paste the URL below"), bi("الرابط سرّي — لا تشاركه", "The URL is secret — don't share it")] },
  shopify: { name: "Shopify", color: "#5a8e3a", sub: bi("طلب جديد · دُفع · شُحن · أُلغي", "New order · paid · fulfilled · cancelled"),
    sig: bi("Settings ← Notifications ← Webhooks: المفتاح الظاهر أسفل الصفحة «signed with…»", "Settings → Notifications → Webhooks: the key shown at the bottom (“signed with…”)"),
    steps: [bi("Settings ← Notifications ← Webhooks ← Create webhook", "Settings → Notifications → Webhooks → Create webhook"), bi("الأحداث: Order creation · Order payment · Order fulfillment · Order cancellation — بصيغة JSON", "Events: Order creation · payment · fulfillment · cancellation — JSON format"), bi("الصق الرابط أدناه، ثم انسخ مفتاح التوقيع إلى «سرّ التوقيع»", "Paste the URL below, then copy the signing key into “Signing secret”")] },
  woocommerce: { name: "WooCommerce", color: "#7f54b3", sub: bi("طلب جديد وتحديث حالته", "New order and status updates"),
    sig: bi("حقل «Secret» في إعداد الـ Webhook", "The “Secret” field of the webhook"),
    steps: [bi("WooCommerce ← Settings ← Advanced ← Webhooks ← Add", "WooCommerce → Settings → Advanced → Webhooks → Add"), bi("Topic: Order created، ثم Webhook ثانٍ Order updated — Delivery URL هو الرابط أدناه", "Topic: Order created, then a second one Order updated — Delivery URL is the URL below"), bi("اكتب قيمة Secret ونفسها هنا", "Set a Secret and paste the same value here")] },
  fb_leads: { name: "Facebook Lead Ads", color: "#1877f2", sub: bi("نماذج إعلانات فيسبوك وإنستجرام ⇒ واتساب خلال ثوانٍ", "Facebook & Instagram lead forms ⇒ WhatsApp in seconds"),
    sig: "",
    steps: [bi("Page ID من «حول» في صفحتك، وتوكن صفحة أو مستخدم من Graph API Explorer بأذونات leads_retrieval · pages_manage_metadata · pages_show_list", "Page ID from your Page's “About”, and a Page or user token from Graph API Explorer with leads_retrieval · pages_manage_metadata · pages_show_list"),
      bi("نشترك في نماذج الصفحة تلقائياً دون المساس برسائل ماسنجر", "We subscribe to the Page's lead forms automatically without touching Messenger"),
      bi("جرّب بـ Lead Ads Testing Tool من Meta: يصل العميل التجريبي هنا وفي سجل الأحداث", "Test with Meta's Lead Ads Testing Tool: the test lead shows up here and in the event log")] },
  sheets: { name: "Google Sheets", color: "#0f9d58", sub: bi("كل صف جديد (ردود Google Forms · جدول عملاء) ⇒ واتساب", "Every new row (Google Forms responses · leads sheet) ⇒ WhatsApp"),
    sig: "",
    steps: [bi("في الجدول: مشاركة ← «أي شخص لديه الرابط» (عارض)، أو ملف ← مشاركة ← النشر على الويب", "In the sheet: Share → “Anyone with the link” (viewer), or File → Share → Publish to web"),
      bi("الصق رابط الجدول. الصفوف الموجودة الآن لا تُراسَل — فقط ما يُضاف بعد الربط", "Paste the sheet link. Rows already there are never messaged — only rows added after connecting"),
      bi("نفحص الجدول كل دقيقتين؛ عمود الجوال يُكتشف تلقائياً أو تختاره", "We check the sheet every two minutes; the phone column is detected automatically or you pick it")] },
  webhook: { name: bi("Webhook عام", "Generic webhook"), color: "#0ea5e9", sub: bi("Zapier · Make · محرك الحجز · أي نظام", "Zapier · Make · booking engine · any system"),
    sig: bi("اختياري — لو ضبطته نتحقّق من X-BotYalla-Signature (HMAC-SHA256 hex للجسم)", "Optional — if set we verify X-BotYalla-Signature (HMAC-SHA256 hex of the body)"),
    steps: [bi("أرسل POST بصيغة JSON إلى الرابط أدناه من Zapier/Make (Webhooks by Zapier ← POST) أو من نظامك", "POST JSON to the URL below from Zapier/Make (Webhooks → POST) or your system"), bi("الحقول: event · id (لمنع التكرار) · phone · name · data {…متغيّراتك}", "Fields: event · id (dedupe) · phone · name · data {…your variables}"), bi("كل مفتاح في data يصير متغيّراً في القالب مثل {{hotel}}", "Every key in data becomes a template variable like {{hotel}}")] },
};
const EV = {
  order_created: [bi("طلب جديد", "New order"), bi("تأكيد الطلب فور إنشائه", "Confirm the order as soon as it's placed")],
  order_paid: [bi("تم الدفع / قيد التجهيز", "Paid / processing"), bi("إشعار استلام الدفع", "Payment received notice")],
  order_shipped: [bi("تم الشحن", "Shipped"), bi("رابط التتبّع للعميل", "Tracking link to the customer")],
  order_completed: [bi("تم التوصيل / اكتمل", "Delivered / completed"), bi("شكر وطلب تقييم", "Thank you and review request")],
  order_cancelled: [bi("أُلغي", "Cancelled"), bi("إشعار الإلغاء", "Cancellation notice")],
  row_added: [bi("صف جديد في الجدول", "New row in the sheet"), bi("كل صف يُضاف بعد الربط — أعمدته متغيّرات", "Every row added after connecting — its columns are variables")],
  cart_abandoned: [bi("سلة متروكة", "Abandoned cart"), bi("تذكير برابط إكمال الشراء — تسويقي: لمن وافق فقط", "Reminder with checkout link — marketing: consented customers only")],
};
const LEAD_L = { full_name: bi("الاسم", "Full name"), phone_number: bi("الجوال", "Phone"), email: bi("البريد", "Email"), city: bi("المدينة", "City"),
  form_id: bi("رقم النموذج", "Form ID"), ad_name: bi("اسم الإعلان", "Ad name"), campaign_name: bi("الحملة", "Campaign"), platform: bi("المنصة", "Platform") };
const VAR_L = { order_id: bi("رقم الطلب", "Order no."), order_total: bi("الإجمالي", "Total"), order_status: bi("الحالة", "Status"), order_items: bi("المنتجات", "Items"),
  order_url: bi("رابط الطلب/السلة", "Order/cart link"), tracking_url: bi("رابط التتبّع", "Tracking link"), customer_name: bi("اسم العميل", "Customer name"), store: bi("اسم التكامل", "Integration name") };
const SAMPLE = { order_id: "#10245", order_total: "1,350 SAR", order_status: bi("قيد التجهيز", "Processing"), order_items: bi("1× جناح ديلوكس", "1× Deluxe suite"),
  order_url: "https://store.example/o/10245", tracking_url: "https://track.example/AB123", customer_name: bi("عبدالله", "Abdullah"),
  "contact.name": bi("عبدالله", "Abdullah"), full_name: bi("نورة", "Noura"), phone_number: "+966507771234", email: "noura@example.com",
  city: bi("الرياض", "Riyadh"), ad_name: bi("عروض العمرة", "Umrah offers"), campaign_name: bi("رمضان", "Ramadan"), platform: "ig", hotel: bi("الفرسان مكة", "Alforsan Makkah"), checkin: "2026-10-12" };
const fill = (s, store) => String(s || "").replace(/\{\{\s*([\w.]+)\s*\}\}/g, (m, k) => (k === "store" ? store : SAMPLE[k] ?? m));
const ST = { sent: [bi("أُرسل", "Sent"), "on"], done: [bi("نُفّذ", "Done"), "on"], skipped: [bi("تُخطّي", "Skipped"), "warn"], failed: [bi("فشل", "Failed"), "off"],
  ignored: [bi("بلا قاعدة", "No rule"), "mute"], received: [bi("قيد التنفيذ", "Processing"), "mute"] };
const DETAIL = { no_phone: bi("لا رقم جوال في الطلب", "No phone on the order"), stopped: bi("العميل طلب الإيقاف (STOP)", "Customer opted out (STOP)"),
  no_optin: bi("قالب تسويقي والعميل لم يوافق على العروض", "Marketing template and the customer hasn't opted in"), category: bi("تعذّرت قراءة فئة القالب من Meta", "Could not read the template category from Meta"),
  send: bi("رفضت Meta الإرسال (رُدّت التكلفة)", "Meta refused the send (cost refunded)"), channel: bi("القناة غير متصلة", "Channel not connected"),
  no_rule: bi("لا قاعدة مفعّلة لهذا الحدث", "No active rule for this event"), paused: bi("التكامل متوقّف", "Integration paused"), bot: bi("القناة حُذفت", "Channel deleted") };

function Logo({ p, size = 40 }) {
  const m = PROV[p] || PROV.webhook;
  return <span className="grid shrink-0 place-items-center rounded-2xl text-[13px] font-extrabold text-white" style={{ width: size, height: size, background: m.color }}>
    {p === "webhook" ? <Icon name="link" size={18} /> : p === "fb_leads" ? "f" : m.name.slice(0, 2)}</span>;
}

function Connect({ provider, onClose, onDone }) {
  const bots = P.bots || [];
  const leads = provider === "fb_leads";
  const sheets = provider === "sheets";
  const [f, setF] = useState({ name: PROV[provider]?.name || "", bot: bots[0]?.id, cc: "+966", secret: "", page_id: "", token: "", sheet_url: "", phone_col: "" });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const save = async () => {
    setErr(""); setBusy(true);
    const r = await call("/api/integrations", { provider, ...f });
    setBusy(false);
    if (!r.ok) { setErr(errOf(r)); return; }
    onDone(r.items, r.id);
  };
  return (
    <Modal open onClose={onClose} title={bi(`ربط ${PROV[provider].name}`, `Connect ${PROV[provider].name}`)} icon="link"
           footer={<><Btn variant="ghost" onClick={onClose}>{bi("إلغاء", "Cancel")}</Btn><Btn onClick={save} disabled={!bots.length || busy}>{busy ? "…" : bi("إنشاء", "Create")}</Btn></>}>
      <div className="grid gap-3">
        {err && <div className="rounded-xl bg-red-400/10 px-3 py-2 text-[13px] font-bold text-red-400">{err}</div>}
        {!bots.length && <div className="rounded-xl bg-yellow-400/10 px-3 py-2 text-[12.5px] font-bold text-yellow-300">{bi("تحتاج رقم واتساب مربوطاً أولاً.", "You need a connected WhatsApp number first.")}</div>}
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label={bi("الاسم", "Name")}><Input dir="auto" maxLength={60} value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></Field>
          <Field label={bi("يُرسل من رقم", "Send from number")}>
            <Select value={String(f.bot || "")} onChange={(e) => setF({ ...f, bot: Number(e.target.value) })}>{bots.map((b) => <option key={b.id} value={String(b.id)}>{b.name}</option>)}</Select>
          </Field>
        </div>
        {leads ? <>
          <Field label="Page ID"><Input dir="ltr" inputMode="numeric" value={f.page_id} onChange={(e) => setF({ ...f, page_id: e.target.value.replace(/\D/g, "") })} /></Field>
          <Field label={bi("توكن الصفحة أو المستخدم", "Page or user token")} hint={PROV.fb_leads.steps[0]}>
            <Input dir="ltr" type="password" autoComplete="off" value={f.token} onChange={(e) => setF({ ...f, token: e.target.value.trim() })} />
          </Field>
        </> : sheets ? (
          <Field label={bi("رابط الجدول", "Sheet link")} hint={PROV.sheets.steps[0]}>
            <Input dir="ltr" value={f.sheet_url} placeholder="https://docs.google.com/spreadsheets/d/…" onChange={(e) => setF({ ...f, sheet_url: e.target.value.trim() })} />
          </Field>
        ) : (
          <Field label={bi("سرّ التوقيع", "Signing secret")} hint={PROV[provider].sig}>
            <Input dir="ltr" type="password" autoComplete="off" value={f.secret} onChange={(e) => setF({ ...f, secret: e.target.value.trim() })} />
          </Field>
        )}
        <Field label={bi("مفتاح الدولة الافتراضي", "Default country code")} hint={bi("لأرقام العملاء المكتوبة بلا مفتاح (مثل 055…)", "For customer numbers written without one (e.g. 055…)")}>
          <Input dir="ltr" value={f.cc} onChange={(e) => setF({ ...f, cc: e.target.value.trim() })} />
        </Field>
      </div>
    </Modal>
  );
}

function LeadEvent({ rule, onChange }) {
  const form = rule.event.startsWith("form_");
  return (
    <div className="flex flex-wrap items-center gap-2">
      <Select className="!w-auto" value={form ? "form" : "lead"} onChange={(e) => onChange({ ...rule, event: e.target.value === "form" ? "form_" : "lead" })}>
        <option value="lead">{bi("كل النماذج", "Any form")}</option><option value="form">{bi("نموذج بعينه", "A specific form")}</option>
      </Select>
      {form && <Input dir="ltr" inputMode="numeric" className="!w-44" placeholder="Form ID" value={rule.event.slice(5)}
                      onChange={(e) => onChange({ ...rule, event: "form_" + e.target.value.replace(/\D/g, "") })} />}
    </div>
  );
}

function RuleEditor({ rule, onChange, onRemove, tpls, seqs, custom, vars, store, leads }) {
  const t = rule.template;
  const setT = (x) => onChange({ ...rule, template: x });
  const [tagText, setTagText] = useState((rule.tags || []).join("، "));
  return (
    <div className="grid gap-3 rounded-2xl bg-ov/[0.035] p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        {leads ? <LeadEvent rule={rule} onChange={onChange} /> : custom ? (
          <Input dir="ltr" className="!w-60" value={rule.event} placeholder="booking_confirmed" onChange={(e) => onChange({ ...rule, event: e.target.value.toLowerCase().replace(/[^a-z0-9_.-]/g, "") })} />
        ) : <div><b className="text-[14px] text-ink">{EV[rule.event][0]}</b><span className="block text-[12px] text-ink-3">{EV[rule.event][1]}</span></div>}
        <span className="flex items-center gap-2">
          <Toggle checked={rule.active !== false} onChange={(v) => onChange({ ...rule, active: v })} label="" />
          {onRemove && <Btn sm variant="ghost" onClick={onRemove} aria-label={bi("حذف", "Delete")}><Icon name="trash" size={14} /></Btn>}
        </span>
      </div>
      <Field label={bi("قالب واتساب", "WhatsApp template")} hint={tpls === null ? bi("جارٍ جلب القوالب…", "Loading templates…") : !tpls.length ? bi("لا قوالب معتمدة بترويسة نصية على هذا الرقم", "No approved text-header templates on this number") : bi("التسويقية تُخصم من الرصيد ولمن وافق فقط؛ الخدمية (UTILITY) ضمن الباقة", "Marketing ones use the wallet and only reach consented customers; UTILITY ones are included")}>
        <Select value={t ? `${t.name}|${t.lang}` : ""} onChange={(e) => {
          if (!e.target.value) { setT(null); return; }
          const [name, lang] = e.target.value.split("|"); const tp = (tpls || []).find((x) => x.name === name && x.language === lang);
          setT({ name, lang, vars: (tp?.vars || []).map((_, i) => (t?.vars || [])[i] || "") });
        }}>
          <option value="">{bi("— بلا قالب —", "— no template —")}</option>
          {t && !(tpls || []).some((x) => x.name === t.name && x.language === t.lang) && <option value={`${t.name}|${t.lang}`}>{t.name} · {t.lang}</option>}
          {(tpls || []).map((x) => <option key={x.name + x.language} value={`${x.name}|${x.language}`}>{x.name} · {x.language} · {x.category}</option>)}
        </Select>
      </Field>
      {t && (t.vars || []).map((v, i) => (
        <Field key={i} label={`{{${i + 1}}}`}>
          <div className="grid gap-1.5">
            <Input dir="auto" value={v} onChange={(e) => setT({ ...t, vars: t.vars.map((x, j) => (j === i ? e.target.value : x)) })} />
            <div className="flex flex-wrap gap-1">{vars.map((k) => (
              <button key={k} type="button" onClick={() => setT({ ...t, vars: t.vars.map((x, j) => (j === i ? `${x}{{${k}}}` : x)) })}
                      className="cursor-pointer rounded-full border-0 bg-au-violet/15 px-2 py-0.5 text-[11px] font-bold text-ink-2 hover:bg-au-violet/25">{VAR_L[k] || LEAD_L[k] || k}</button>))}</div>
          </div>
        </Field>
      ))}
      {t && (t.vars || []).some(Boolean) && (
        <p className="m-0 rounded-xl bg-emerald-400/[0.07] px-3 py-2 text-[12px] leading-relaxed text-ink-2" dir="auto">
          <b className="text-emerald-400">{bi("مثال: ", "Example: ")}</b>{t.vars.map((v, i) => `{{${i + 1}}} = ${fill(v, store) || "—"}`).join(" · ")}
        </p>
      )}
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label={bi("وسوم على العميل", "Tags on the customer")} hint={bi("افصل بفاصلة", "Comma-separated")}>
          <Input dir="auto" value={tagText} onChange={(e) => { setTagText(e.target.value); onChange({ ...rule, tags: e.target.value.split(/[,،]/).map((s) => s.trim()).filter(Boolean).slice(0, 10) }); }} />
        </Field>
        <Field label={bi("تسلسل متابعة", "Follow-up sequence")}>
          <Select value={String(rule.sequence || "")} onChange={(e) => onChange({ ...rule, sequence: Number(e.target.value) || null })}>
            <option value="">{bi("— بلا —", "— none —")}</option>{seqs.map((s) => <option key={s.id} value={String(s.id)}>{s.name}</option>)}
          </Select>
        </Field>
      </div>
    </div>
  );
}

function Editor({ item, onClose, onSaved }) {
  const leads = item.provider === "fb_leads";
  const sheet = item.provider === "sheets";
  const store = !["webhook", "fb_leads", "sheets"].includes(item.provider);
  const [tab, setTab] = useState("rules");
  const [f, setF] = useState({ name: item.name, bot: item.bot_id, cc: item.cc, active: item.active, secret: "", clear_secret: false, token: "",
    sheet_url: item.sheet_url || "", phone_col: item.phone_col || "" });
  const [rules, setRules] = useState(() => store
    ? P.storeEvents.map((ev) => item.rules.find((r) => r.event === ev) || { event: ev, active: false, template: null, tags: [], sequence: null, _new: true })
    : item.rules.length ? item.rules
      : leads ? [{ event: "lead", active: true, template: null, tags: ["Lead Ads"], sequence: null }]
      : sheet ? [{ event: "row_added", active: true, template: null, tags: [], sequence: null }] : item.rules);
  const [tpls, setTpls] = useState(null);
  const [err, setErr] = useState("");
  const [copied, setCopied] = useState(false);
  const [url, setUrl] = useState(item.url);
  useEffect(() => {
    setTpls(null);
    call(`/api/templates?bot=${f.bot}`, null, "GET").then((r) => setTpls(r.ok ? (r.items || []).filter((x) => x.status === "APPROVED"
      && (!x.header_format || x.header_format === "TEXT") && !(x.header_vars || []).length) : []));
  }, [f.bot]);
  const seqs = (P.sequences || []).filter((s) => s.bot_id === f.bot);
  const vars = store ? P.storeVars : leads ? ["full_name", "phone_number", "email", "city", "ad_name", "campaign_name"]
    : sheet ? [...(item.headers || []), "customer_name"] : ["customer_name", "store"];
  const save = async () => {
    setErr("");
    // حدث متجر بلا أي إجراء = غير مستعمل؛ لا يُحفظ (الخادم يرفض قاعدة بلا إجراء)
    const keep = rules.filter((r) => !store || r.template || (r.tags || []).length || r.sequence).map(({ _new, ...r }) => r);
    const r = await call(`/api/integrations/${item.id}/save`, { ...f, rules: keep });
    if (!r.ok) { setErr(errOf(r)); return; }
    onSaved(r.items); onClose();
  };
  const rotate = async () => {
    if (!window.confirm(bi("إنشاء رابط جديد؟ القديم يتوقّف فوراً ويجب تحديثه في المتجر.", "Create a new URL? The old one stops immediately and must be updated in the store."))) return;
    const r = await call(`/api/integrations/${item.id}/rotate`);
    if (r.ok) { const x = r.items.find((i) => i.id === item.id); setUrl(x.url); onSaved(r.items); }
  };
  const m = PROV[item.provider];
  return (
    <Modal open wide onClose={onClose} title={item.name} icon="link"
           footer={<><Btn variant="ghost" onClick={onClose}>{bi("إلغاء", "Cancel")}</Btn>{P.canManage && <Btn onClick={save}>{bi("حفظ", "Save")}</Btn>}</>}>
      <div className="mb-3 flex gap-1.5">
        {[["rules", bi("القواعد", "Rules")], ["setup", bi("الربط", "Setup")]].map(([k, l]) => (
          <button key={k} type="button" onClick={() => setTab(k)} className={`cursor-pointer rounded-xl border-0 px-3.5 py-2 text-[13px] font-bold ${tab === k ? "bg-au-violet/20 text-ink" : "bg-ov/[0.04] text-ink-3"}`}>{l}</button>
        ))}
      </div>
      {err && <div className="mb-3 rounded-xl bg-red-400/10 px-3 py-2 text-[13px] font-bold text-red-400">{err}</div>}
      {tab === "setup" && <div className="grid gap-3">
        {sheet ? (
          <div className="grid gap-3 rounded-2xl bg-ov/[0.035] p-3">
            <ol className="m-0 grid gap-1 ps-5 text-[12.5px] leading-relaxed text-ink-3">{m.steps.map((x, i) => <li key={i}>{x}</li>)}</ol>
            <Field label={bi("رابط الجدول", "Sheet link")} hint={bi(`عولج ${num(item.rows_seen || 0)} صفاً حتى الآن. تغيير الرابط يبدأ من آخر صفوف الجدول الجديد.`, `${num(item.rows_seen || 0)} rows processed so far. Changing the link starts from the new sheet's last row.`)}>
              <Input dir="ltr" value={f.sheet_url} onChange={(e) => setF({ ...f, sheet_url: e.target.value.trim() })} />
            </Field>
            <Field label={bi("عمود رقم الجوال", "Phone column")}>
              <Select value={f.phone_col} onChange={(e) => setF({ ...f, phone_col: e.target.value })}>
                <option value="">{bi("تلقائي (جوال · phone · mobile · واتساب…)", "Automatic (phone · mobile · whatsapp…)")}</option>
                {(item.headers || []).map((h) => <option key={h} value={h}>{h}</option>)}
              </Select>
            </Field>
          </div>
        ) : leads ? (
          <div className="rounded-2xl bg-ov/[0.035] p-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span><b className="text-ink">{item.page_name || item.page_id}</b> <span className="text-[12px] text-ink-3" dir="ltr">· {item.page_id}</span></span>
              {item.has_token ? <Pill tone="on" dot>{bi("مشترك في النماذج", "Subscribed to forms")}</Pill> : <Pill tone="off">{bi("غير مربوط", "Not connected")}</Pill>}
            </div>
            <ol className="mb-0 mt-3 grid gap-1 ps-5 text-[12.5px] leading-relaxed text-ink-3">{m.steps.map((x, i) => <li key={i}>{x}</li>)}</ol>
            <Field label={bi("توكن جديد (لإعادة الربط فقط)", "New token (to reconnect only)")}>
              <Input dir="ltr" type="password" autoComplete="off" value={f.token} onChange={(e) => setF({ ...f, token: e.target.value.trim() })} />
            </Field>
          </div>
        ) : <div className="rounded-2xl bg-ov/[0.035] p-3">
          <div className="mb-1 text-[12px] font-bold text-ink-2">{bi("رابط الاستقبال (سرّي)", "Receiving URL (secret)")}</div>
          <div className="flex items-center gap-2">
            <code dir="ltr" className="min-w-0 flex-1 truncate rounded-lg bg-sink/40 px-2.5 py-1.5 text-[11.5px] text-ink-2">{url}</code>
            <Btn sm variant="ghost" icon="copy" onClick={() => { copy(url); setCopied(true); setTimeout(() => setCopied(false), 1500); }}>{copied ? bi("نُسخ ✓", "Copied ✓") : bi("نسخ", "Copy")}</Btn>
            {P.canManage && <Btn sm variant="ghost" icon="refresh" onClick={rotate} aria-label={bi("رابط جديد", "New URL")} />}
          </div>
          <ol className="mb-0 mt-3 grid gap-1 ps-5 text-[12.5px] leading-relaxed text-ink-3">{m.steps.map((s, i) => <li key={i}>{s}</li>)}</ol>
          {!store && <pre dir="ltr" className="mb-0 mt-3 overflow-x-auto rounded-lg bg-sink/40 p-2.5 text-[11.5px] text-ink-2">{`POST ${url}
{"event": "booking_confirmed", "id": "BK-1042",
 "phone": "+966551234567", "name": "Abdullah",
 "data": {"hotel": "Makkah", "checkin": "2026-10-12", "nights": "3"}}`}</pre>}
        </div>}
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label={bi("الاسم", "Name")}><Input dir="auto" maxLength={60} value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></Field>
          <Field label={bi("يُرسل من رقم", "Send from number")}>
            <Select value={String(f.bot)} onChange={(e) => setF({ ...f, bot: Number(e.target.value) })}>{(P.bots || []).map((b) => <option key={b.id} value={String(b.id)}>{b.name}</option>)}</Select>
          </Field>
          {!leads && !sheet && <Field label={bi("سرّ التوقيع", "Signing secret")} hint={item.has_secret && !f.clear_secret ? bi("محفوظ ولا يُعرض — اتركه فارغاً للإبقاء عليه", "Saved and never shown — leave empty to keep it") : m.sig}>
            <Input dir="ltr" type="password" autoComplete="off" value={f.secret} onChange={(e) => setF({ ...f, secret: e.target.value.trim(), clear_secret: false })} />
          </Field>}
          <Field label={bi("مفتاح الدولة الافتراضي", "Default country code")}><Input dir="ltr" value={f.cc} onChange={(e) => setF({ ...f, cc: e.target.value.trim() })} /></Field>
        </div>
        <div className="flex flex-wrap gap-5 text-[13px] text-ink-2">
          <label className="flex items-center gap-2"><Toggle checked={f.active} onChange={(v) => setF({ ...f, active: v })} label="" />{bi("التكامل يعمل", "Integration active")}</label>
          {item.has_secret && <label className="flex items-center gap-2"><Toggle checked={f.clear_secret} onChange={(v) => setF({ ...f, clear_secret: v, secret: "" })} label="" />{bi("إزالة السرّ", "Remove the secret")}</label>}
        </div>
      </div>}
      {tab === "rules" && <div className="grid gap-2.5">
        <p className="m-0 text-[12.5px] leading-relaxed text-ink-3">{sheet
          ? bi("كل صف يُضاف للجدول بعد الربط يصل صاحبه بقالب واتساب ويدخل جهات الاتصال. كل عمود متغيّر باسمه (المسافات تصير _).", "Every row added after connecting reaches that person as a WhatsApp template and lands in Contacts. Every column is a variable by its name (spaces become _).")
          : leads
          ? bi("كل عميل يملأ نموذج إعلانك يصله قالب واتساب خلال ثوانٍ ويدخل جهات الاتصال. قاعدة «نموذج بعينه» تتقدّم على «كل النماذج». كل سؤال في النموذج متغيّر باسمه، مثل {{full_name}} و{{city}} وأسئلتك المخصّصة.", "Everyone who fills your ad's form gets a WhatsApp template within seconds and lands in Contacts. A “specific form” rule wins over “any form”. Every form question is a variable by its name, like {{full_name}}, {{city}} and your custom questions.")
          : store
          ? bi("فعّل الأحداث التي تريدها واختر لكل حدث قالباً معتمداً ومتغيّراته من الطلب. نفس الطلب لا يصل العميل مرتين، ومن طلب الإيقاف لا يصله شيء.", "Enable the events you want and pick an approved template with order variables for each. The same order never reaches a customer twice, and opted-out customers get nothing.")
          : bi("لكل حدث يرسله نظامك قاعدة باسمه. مفاتيح data تصير متغيّرات: {{hotel}}، ومعها {{customer_name}} و{{contact.name}}.", "One rule per event name your system sends. Keys in data become variables: {{hotel}}, plus {{customer_name}} and {{contact.name}}.")}</p>
        {rules.map((r, i) => (
          <RuleEditor key={store ? r.event : i} rule={r} tpls={tpls} seqs={seqs} custom={!store && !sheet} leads={leads} vars={vars} store={f.name}
                      onChange={(x) => setRules(rules.map((y, j) => (j === i
                        ? { ...x, active: y._new && x.active === y.active ? true : x.active, _new: false } : y)))}
                      onRemove={store ? null : () => setRules(rules.filter((_, j) => j !== i))} />
        ))}
        {!store && !sheet && rules.length < 20 && <Btn sm icon="plus" className="justify-self-start" onClick={() => setRules([...rules, { event: leads ? "form_" : "", active: true, template: null, tags: [], sequence: null }])}>{bi("قاعدة جديدة", "New rule")}</Btn>}
      </div>}
    </Modal>
  );
}

function Log({ item, onClose }) {
  const [ev, setEv] = useState(null);
  useEffect(() => { call(`/api/integrations/${item.id}/events`, null, "GET").then((r) => setEv(r.ok ? r.events : [])); }, [item.id]);
  return (
    <Modal open wide onClose={onClose} title={bi(`سجل الأحداث — ${item.name}`, `Event log — ${item.name}`)} icon="clock"
           footer={<Btn variant="ghost" onClick={onClose}>{bi("إغلاق", "Close")}</Btn>}>
      {ev === null ? <div className="p-6 text-center text-ink-3">…</div> : !ev.length
        ? <Empty icon="clock" title={bi("لم يصل أي حدث بعد", "No events yet")} text={bi("أنشئ طلباً تجريبياً في متجرك وسيظهر هنا خلال ثوانٍ.", "Place a test order in your store and it shows up here within seconds.")} />
        : <div className="-mx-2 overflow-x-auto px-2"><table className="w-full border-collapse text-[13px]">
          <thead><tr>{[bi("الوقت", "Time"), bi("الحدث", "Event"), bi("العميل", "Customer"), bi("النتيجة", "Result")].map((h, i) => (
            <th key={i} className="whitespace-nowrap px-3 py-2 text-start text-[11px] font-extrabold uppercase tracking-wider text-ink-3 shadow-[inset_0_-1px_0_rgb(var(--ov-rgb)/0.08)]">{h}</th>))}</tr></thead>
          <tbody>{ev.map((e) => { const [l, tone] = ST[e.status] || [e.status, "mute"]; const td = "px-3 py-2 shadow-[inset_0_-1px_0_rgb(var(--ov-rgb)/0.05)]"; return (
            <tr key={e.id}>
              <td className={`${td} whitespace-nowrap text-ink-3`}>{when(e.created_at)}</td>
              <td className={td}><b className="text-ink">{EV[e.event]?.[0] || e.event}</b>{e.summary && <span className="block text-[11.5px] text-ink-3" dir="auto">{e.summary}</span>}</td>
              <td className={`${td} whitespace-nowrap text-ink-2`} dir="ltr">{e.phone || "—"}</td>
              <td className={td}><Pill tone={tone} dot>{l}</Pill>{e.detail && <span className="mt-1 block text-[11.5px] text-ink-3">{DETAIL[e.detail] || e.detail}</span>}</td>
            </tr>); })}</tbody>
        </table></div>}
    </Modal>
  );
}

/* ------------------------------------------------------------ مزامنة HubSpot / Zoho */
const CRM_ERR = { crm_auth: bi("رفض الـ CRM المفتاح — تأكّد منه وأعد المحاولة", "The CRM rejected the key — check it and try again"),
  crm_network: bi("تعذّر الوصول للـ CRM", "Could not reach the CRM"), crm_rate: bi("حدّ طلبات الـ CRM — نعيد تلقائياً", "CRM rate limit — we retry automatically"),
  token: bi("توكن HubSpot Private App يبدأ بـ pat-", "A HubSpot Private App token starts with pat-"), secret: bi("أكمل بيانات الربط", "Complete the connection details"),
  dc: bi("مركز بيانات غير معروف", "Unknown data center"), rate: bi("انتظر قليلاً قبل مزامنة أخرى", "Wait a bit before another sync") };
const CRM_NAME = { hubspot: "HubSpot", zoho: "Zoho CRM" };

function CrmSync() {
  const [cfg, setCfg] = useState(P.crm || {});
  const [edit, setEdit] = useState(null);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(null);
  const errText = (e) => CRM_ERR[e] || (String(e || "").startsWith("hubspot") || String(e || "").startsWith("zoho") ? e : bi("حدث خطأ", "Something went wrong"));
  const save = async (body) => {
    setErr(""); setBusy(true);
    const r = await call("/api/crm-sync/settings", body);
    setBusy(false);
    if (r.config) setCfg(r.config);
    if (!r.ok) { setErr(errText(r.error)); return false; }
    return true;
  };
  const syncNow = async () => { setBusy(true); const r = await call("/api/crm-sync/now"); setBusy(false); if (r.ok) { setCfg(r.config); setDone(r); } else setErr(errText(r.error)); };
  const open = (provider) => { setErr(""); setEdit({ provider, token: "", client_id: "", client_secret: "", refresh_token: "", dc: cfg.provider === provider ? cfg.dc : "sa", notes: cfg.notes !== false, enabled: true, two_way: cfg.provider === provider && !!cfg.two_way }); };
  const on = cfg.provider && cfg.connected;
  return (
    <Card className="mb-4">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <div><b className="block text-[15px] text-ink">{bi("مزامنة CRM", "CRM sync")}</b>
          <span className="text-[12.5px] text-ink-3">{bi("كل جهة اتصال جديدة أو معدّلة تصل HubSpot أو Zoho تلقائياً (كل دقيقة)، وإجابات الفلو ملاحظةً على العميل هناك.", "Every new or updated contact reaches HubSpot or Zoho automatically (every minute), and flow answers become a note on the customer there.")}</span></div>
        {on && <div className="flex flex-wrap items-center gap-2">
          {cfg.enabled ? <Pill tone={cfg.last_error ? "warn" : "on"} dot>{CRM_NAME[cfg.provider]}</Pill> : <Pill tone="mute">{bi("متوقّفة", "Paused")}</Pill>}
          {P.canManage && <Btn sm variant="ghost" icon="refresh" disabled={busy} onClick={syncNow}>{bi("زامن الآن", "Sync now")}</Btn>}
        </div>}
      </div>
      {err && <div className="mb-3 rounded-xl bg-red-400/10 px-3 py-2 text-[13px] font-bold text-red-400">{err}</div>}
      {on && <div className="mb-3 flex flex-wrap gap-4 rounded-xl bg-ov/[0.035] px-3 py-2.5 text-[12.5px] text-ink-3">
        <span>{bi("جهات مُزامَنة", "Contacts synced")}: <b className="tnum text-ink">{num(cfg.synced || 0)}</b></span>
        {cfg.two_way && <span>{bi("وصل من الـ CRM", "From the CRM")}: <b className="tnum text-ink">{num(cfg.pulled || 0)}</b></span>}
        <span>{bi("آخر مزامنة", "Last sync")}: <b className="text-ink">{when(cfg.last_at)}</b></span>
        {cfg.last_error && <span className="text-yellow-300">{errText(cfg.last_error)}</span>}
        {done && <span className="text-emerald-400">{bi(`✓ ${done.contacts} جهة · ${done.notes} ملاحظة`, `✓ ${done.contacts} contacts · ${done.notes} notes`)}</span>}
      </div>}
      {P.canManage && <div className="grid gap-3 sm:grid-cols-2">
        {["hubspot", "zoho"].map((p) => (
          <button key={p} type="button" onClick={() => open(p)}
                  className={`flex cursor-pointer items-center gap-3 rounded-2xl border-0 p-3 text-start shadow-[inset_0_0_0_1px_rgb(var(--ov-rgb)/0.06)] hover:bg-ov/[0.07] ${cfg.provider === p && on ? "bg-au-violet/15" : "bg-ov/[0.04]"}`}>
            <span className="grid size-10 shrink-0 place-items-center rounded-2xl text-[13px] font-extrabold text-white" style={{ background: p === "hubspot" ? "#ff7a59" : "#e42527" }}>{p === "hubspot" ? "Hs" : "Zo"}</span>
            <span><b className="block text-[14px] text-ink">{CRM_NAME[p]}</b><span className="text-[11.5px] text-ink-3">{cfg.provider === p && on ? bi("متصل — اضغط للتعديل", "Connected — click to edit") : bi("اضغط للربط", "Click to connect")}</span></span>
          </button>
        ))}
      </div>}
      {edit && (
        <Modal open onClose={() => setEdit(null)} title={bi(`ربط ${CRM_NAME[edit.provider]}`, `Connect ${CRM_NAME[edit.provider]}`)} icon="users"
               footer={<>{cfg.provider === edit.provider && on && <Btn variant="ghost" onClick={async () => { if (window.confirm(bi("فصل المزامنة؟ لا يُحذف شيء من الـ CRM.", "Disconnect sync? Nothing is deleted from the CRM."))) { await save({ clear: true }); setEdit(null); } }}>{bi("فصل", "Disconnect")}</Btn>}
                 <Btn variant="ghost" onClick={() => setEdit(null)}>{bi("إلغاء", "Cancel")}</Btn>
                 <Btn disabled={busy} onClick={async () => { if (await save(edit)) setEdit(null); }}>{busy ? bi("نتحقّق…", "Checking…") : bi("حفظ وتحقّق", "Save & verify")}</Btn></>}>
          <div className="grid gap-3">
            {err && <div className="rounded-xl bg-red-400/10 px-3 py-2 text-[13px] font-bold text-red-400">{err}</div>}
            {edit.provider === "hubspot" ? (
              <Field label="Private App token" hint={cfg.provider === "hubspot" && on ? bi("محفوظ ولا يُعرض — اتركه فارغاً للإبقاء عليه", "Saved and never shown — leave empty to keep it")
                : bi("HubSpot ← Settings ← Integrations ← Private Apps ← Create: صلاحيات crm.objects.contacts.read/write", "HubSpot → Settings → Integrations → Private Apps → Create: scopes crm.objects.contacts.read/write")}>
                <Input dir="ltr" type="password" autoComplete="off" placeholder="pat-na1-…" value={edit.token} onChange={(e) => setEdit({ ...edit, token: e.target.value.trim() })} />
              </Field>
            ) : <>
              <p className="m-0 text-[12.5px] leading-relaxed text-ink-3">{bi("من api-console.zoho.sa ← Self Client: انسخ Client ID و Client Secret، ثم ولّد رمزاً بالنطاق ZohoCRM.modules.contacts.ALL,ZohoCRM.modules.notes.CREATE,ZohoCRM.users.READ وبدّله بـ Refresh Token.", "From api-console.zoho.sa → Self Client: copy the Client ID and Secret, then generate a code with scope ZohoCRM.modules.contacts.ALL,ZohoCRM.modules.notes.CREATE,ZohoCRM.users.READ and exchange it for a Refresh Token.")}</p>
              <div className="grid gap-3 sm:grid-cols-2">
                <Field label="Client ID"><Input dir="ltr" autoComplete="off" placeholder={cfg.provider === "zoho" ? cfg.client_id : ""} value={edit.client_id} onChange={(e) => setEdit({ ...edit, client_id: e.target.value.trim() })} /></Field>
                <Field label={bi("مركز البيانات", "Data center")}>
                  <Select value={edit.dc} onChange={(e) => setEdit({ ...edit, dc: e.target.value })}>{(P.zohoDc || []).map((d) => <option key={d} value={d}>zoho.{d}</option>)}</Select>
                </Field>
              </div>
              <Field label="Client Secret"><Input dir="ltr" type="password" autoComplete="off" value={edit.client_secret} onChange={(e) => setEdit({ ...edit, client_secret: e.target.value.trim() })} /></Field>
              <Field label="Refresh Token" hint={cfg.provider === "zoho" && on ? bi("محفوظة ولا تُعرض — اتركها فارغة للإبقاء عليها", "Saved and never shown — leave empty to keep them") : null}>
                <Input dir="ltr" type="password" autoComplete="off" value={edit.refresh_token} onChange={(e) => setEdit({ ...edit, refresh_token: e.target.value.trim() })} />
              </Field>
            </>}
            <div className="flex flex-wrap gap-5 text-[13px] text-ink-2">
              <label className="flex items-center gap-2"><Toggle checked={edit.enabled} onChange={(v) => setEdit({ ...edit, enabled: v })} label="" />{bi("المزامنة تعمل", "Sync active")}</label>
              <label className="flex items-center gap-2"><Toggle checked={edit.notes} onChange={(v) => setEdit({ ...edit, notes: v })} label="" />{bi("إجابات الفلو كملاحظات", "Flow answers as notes")}</label>
              <label className="flex items-center gap-2"><Toggle checked={!!edit.two_way} onChange={(v) => setEdit({ ...edit, two_way: v })} label="" />{bi("باتجاهين: تعديلات الـ CRM تصل جهات الاتصال", "Two-way: CRM edits flow back to Contacts")}</label>
            </div>
            {edit.two_way && <p className="m-0 text-[12px] leading-relaxed text-ink-3">{bi("الاسم والهاتف والبريد لكل جهة عُدّلت أو أُضيفت في الـ CRM بعد التفعيل تصل هنا (كل دقيقة). الهاتف المسجَّل لجهة أخرى عندنا لا يُستبدل.", "Name, phone and email of every contact edited or added in the CRM after enabling arrive here (every minute). A phone already used by another contact here is never overwritten.")}</p>}
            <p className="m-0 flex gap-2 rounded-xl bg-ov/[0.035] px-3 py-2 text-[12px] leading-relaxed text-ink-3"><Icon name="lock" size={14} className="mt-0.5" />
              {bi("المفاتيح تُحفظ مشفّرة ولا تعود للمتصفح. لا حذف في أي طرف أبداً. أول ربط يرسل كل جهاتك الحالية على دفعات.", "Keys are stored encrypted and never returned to the browser. Nothing is ever deleted on either side. The first connection sends all your existing contacts in batches.")}</p>
          </div>
        </Modal>
      )}
    </Card>
  );
}

export default function Integrations() {
  const [items, setItems] = useState(P.items || []);
  const [connect, setConnect] = useState(null);
  const [edit, setEdit] = useState(null);
  const [log, setLog] = useState(null);
  const del = async (i) => {
    if (!window.confirm(bi(`حذف «${i.name}»؟ يتوقّف رابطه فوراً.`, `Delete “${i.name}”? Its URL stops immediately.`))) return;
    const r = await call(`/api/integrations/${i.id}/delete`); if (r.ok) setItems(r.items);
  };
  return (
    <>
      <PageHead icon="link" title={bi("التكاملات", "Integrations")}
                sub={bi("اربط متجرك أو نظام الحجز: كل طلب أو حجز يصل عميلك برسالة واتساب تلقائية بقالب معتمد، ويدخل جهات الاتصال بوسومه.", "Connect your store or booking system: every order or booking reaches your customer as an automatic WhatsApp template message and lands in Contacts with tags.")} />
      {P.canManage && <div className="mb-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {P.providers.map((p) => (
          <button key={p} type="button" onClick={() => setConnect(p)}
                  className="flex cursor-pointer items-center gap-3 rounded-2xl border-0 bg-ov/[0.04] p-3 text-start shadow-[inset_0_0_0_1px_rgb(var(--ov-rgb)/0.06)] hover:bg-ov/[0.07]">
            <Logo p={p} />
            <span className="min-w-0"><b className="block text-[14px] text-ink">{PROV[p].name}</b><span className="block text-[11.5px] leading-snug text-ink-3">{PROV[p].sub}</span></span>
          </button>
        ))}
      </div>}
      <Card>
        <b className="mb-3 block text-[15px] text-ink">{bi("التكاملات المربوطة", "Connected integrations")}</b>
        {!items.length ? (
          <Empty icon="link" title={bi("لا تكاملات بعد", "No integrations yet")}
                 text={bi("اختر متجرك أعلاه. للفنادق: «Webhook عام» يربط محرك الحجز أو Zapier فيصل تأكيد الحجز للنزيل على واتساب فوراً.", "Pick your store above. For hotels: “Generic webhook” connects the booking engine or Zapier so booking confirmations reach guests on WhatsApp instantly.")} />
        ) : (
          <div className="grid gap-2">
            {items.map((i) => {
              const on = i.rules.filter((r) => r.active).length;
              return (
                <div key={i.id} className="flex min-w-0 flex-wrap items-center justify-between gap-3 rounded-2xl bg-ov/[0.035] px-4 py-3">
                  <div className="flex min-w-0 items-center gap-3">
                    <Logo p={i.provider} size={36} />
                    <div className="min-w-0">
                      <b className="block truncate text-ink" dir="auto">{i.name}</b>
                      <span className="text-[12px] text-ink-3">{PROV[i.provider].name}{i.page_name ? ` (${i.page_name})` : ""} · {i.bot_name} · {bi(`${on} قاعدة مفعّلة`, `${on} active rule(s)`)}{i.last_at ? ` · ${bi("آخر حدث", "last event")} ${when(i.last_at)}` : ""}</span>
                    </div>
                  </div>
                  <div className="flex flex-wrap items-center gap-3 text-[12.5px]">
                    {[[i.n30, bi("أحداث 30 يوماً", "Events 30d")], [i.ok30, bi("نُفّذت", "Done")]].map(([v, t], k) => (
                      <span key={k} className="text-center"><b className="tnum block text-[16px] text-ink">{num(v)}</b><span className="text-ink-3">{t}</span></span>
                    ))}
                    {i.active ? <Pill tone="on" dot>{bi("يعمل", "Active")}</Pill> : <Pill tone="mute">{bi("متوقّف", "Paused")}</Pill>}
                    <Btn sm variant="ghost" icon="clock" onClick={() => setLog(i)}>{bi("السجل", "Log")}</Btn>
                    <Btn sm variant="ghost" icon="settings" onClick={() => setEdit(i)}>{P.canManage ? bi("تعديل", "Edit") : bi("عرض", "View")}</Btn>
                    {P.canManage && <Btn sm variant="ghost" onClick={() => del(i)} aria-label={bi("حذف", "Delete")}><Icon name="trash" size={14} /></Btn>}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </Card>
      <div className="mt-4"><CrmSync /></div>
      {connect && <Connect provider={connect} onClose={() => setConnect(null)}
                           onDone={(list, id) => { setItems(list); setConnect(null); const x = list.find((y) => y.id === id); if (x) setEdit(x); }} />}
      {edit && <Editor item={edit} onClose={() => setEdit(null)} onSaved={setItems} />}
      {log && <Log item={log} onClose={() => setLog(null)} />}
    </>
  );
}
