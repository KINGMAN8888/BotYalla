/* باني الفلو المرئي — المرحلة 5 من docs/ENTERPRISE_PLAN.md (المحرك في flow_graph.py).
   قائمة فلوهات البوت (مشغّل · تفعيل · إحصاءات) ومحرّر كانفس: سحب البطاقات وتوصيلها، لوحة خصائص،
   تراجع، وخريطة تسرّب من الجلسات الحقيقية. المسودة تُحفظ كما هي؛ التحقق الكامل عند النشر في الخادم.
   الكانفس بلا مكتبة: هندسة البطاقات ثابتة (ارتفاعات محسوبة) فتُرسم التوصيلات دون قياس DOM. */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { BY, P, bi, AR, Icon, Card, Btn, Field, Input, Textarea, Select, Pill, Empty, PageHead, num, Modal, Toggle, zoomOf } from "../kit.jsx";
import { AssetPicker } from "../media.jsx";

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
const pct = (a, b) => (b ? Math.round((a / b) * 100) : 0);

/* ------------------------------------------------------------ البطاقات */
const TYPES = {
  text:      { icon: "chat",      g: "msg",   c: "#22d3ee", l: ["رسالة نصية", "Text message"] },
  media:     { icon: "image",     g: "msg",   c: "#22d3ee", l: ["صورة / فيديو / صوت", "Image / video / audio"] },
  products:  { icon: "cart",      g: "msg",   c: "#22d3ee", l: ["منتجات الكتالوج", "Catalog products"], wa: true },
  form:      { icon: "ticket",    g: "msg",   c: "#7c6cf6", l: ["نموذج واتساب (Form)", "WhatsApp form"], wa: true },
  payment:   { icon: "card",      g: "msg",   c: "#2dd4a7", l: ["طلب دفع", "Request payment"] },
  buttons:   { icon: "menu",      g: "msg",   c: "#7c6cf6", l: ["أزرار اختيار", "Buttons"] },
  ask:       { icon: "edit",      g: "msg",   c: "#7c6cf6", l: ["سؤال", "Question"] },
  ask_media: { icon: "clip",      g: "msg",   c: "#7c6cf6", l: ["طلب ملف", "Ask for a file"] },
  location:  { icon: "globe",     g: "msg",   c: "#22d3ee", l: ["موقع على الخريطة", "Location pin"] },
  template:  { icon: "mail",      g: "msg",   c: "#22d3ee", l: ["قالب واتساب", "WhatsApp template"], wa: true },
  ai:        { icon: "sparkles",  g: "msg",   c: "#b9afff", l: ["رد بالذكاء الاصطناعي", "AI answers"] },
  tag:       { icon: "tag",       g: "act",   c: "#2dd4a7", l: ["إضافة وسم", "Add tag"] },
  set_field: { icon: "user",      g: "act",   c: "#2dd4a7", l: ["تحديث حقل", "Update field"] },
  set_var:   { icon: "key",       g: "act",   c: "#2dd4a7", l: ["تعيين متغيّر", "Set variable"] },
  save_lead: { icon: "download",  g: "act",   c: "#2dd4a7", l: ["حفظ البيانات", "Save data"] },
  notify:    { icon: "bolt",      g: "act",   c: "#2dd4a7", l: ["تنبيه الفريق", "Notify team"] },
  goal:      { icon: "crown",     g: "act",   c: "#2dd4a7", l: ["هدف / تحويل", "Goal"] },
  sequence:  { icon: "clock",     g: "act",   c: "#2dd4a7", l: ["إضافة لتسلسل متابعة", "Add to sequence"] },
  delay:     { icon: "clock",     g: "act",   c: "#2dd4a7", l: ["انتظار", "Delay"] },
  condition: { icon: "filter",    g: "logic", c: "#f59e0b", l: ["شرط", "Condition"] },
  switch:    { icon: "menu",      g: "logic", c: "#f59e0b", l: ["تفرّع حسب القيمة", "Switch"] },
  hours:     { icon: "calendar",  g: "logic", c: "#f59e0b", l: ["ساعات العمل", "Business hours"] },
  jump:      { icon: "arrow",     g: "logic", c: "#f59e0b", l: ["انتقال لفلو", "Go to flow"] },
  api:       { icon: "link",      g: "int",   c: "#60a5fa", l: ["طلب API", "API request"] },
  sheets:    { icon: "grid",      g: "int",   c: "#60a5fa", l: ["Google Sheets", "Google Sheets"] },
  assign:    { icon: "user",      g: "end",   c: "#f87171", l: ["إسناد لموظف", "Assign to member"] },
  handoff:   { icon: "users",     g: "end",   c: "#f87171", l: ["تحويل لموظف", "Hand off to agent"] },
  resolve:   { icon: "check",     g: "end",   c: "#f87171", l: ["إغلاق المحادثة", "Resolve conversation"] },
  end:       { icon: "stop",      g: "end",   c: "#f87171", l: ["إنهاء", "End"] },
};
const GROUPS = [["msg", ["رسائل", "Messages"]], ["act", ["إجراءات", "Actions"]], ["logic", ["منطق", "Logic"]],
  ["int", ["تكاملات", "Integrations"]], ["end", ["الفريق والإنهاء", "Team & finish"]]];
const BRANCHING = ["buttons", "condition", "hours", "handoff", "jump", "end", "switch", "resolve"];
const TWO_WAY = ["template", "api", "ai", "products", "form", "payment"];   // «نجح» في next و«فشل» في fail
const METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE"];
const SHEETS_SCRIPT = `function doPost(e) {
  var sheet = SpreadsheetApp.getActiveSpreadsheet().getSheets()[0];
  var row = JSON.parse(e.postData.contents);
  var head = sheet.getRange(1, 1, 1, Math.max(sheet.getLastColumn(), 1)).getValues()[0].filter(String);
  Object.keys(row).forEach(function (k) { if (head.indexOf(k) < 0) { head.push(k); sheet.getRange(1, head.length).setValue(k); } });
  sheet.appendRow(head.map(function (k) { return row[k] === undefined ? "" : row[k]; }));
  return ContentService.createTextOutput("ok");
}`;
const DEFAULTS = {
  text: { text: "" }, media: { asset: null, caption: "" },
  buttons: { text: "", var: "", options: [{ label: "", next: null }] },
  ask: { text: "", var: "", validate: "text", error: "" }, ask_media: { text: "", var: "" },
  tag: { tags: [] }, set_field: { field: "name", value: "" }, set_var: { var: "", value: "" }, save_lead: {},
  notify: { text: "" }, goal: { name: "" }, delay: { seconds: 2 },
  condition: { var: "", op: "eq", value: "", yes: null, no: null },
  hours: { start: 9, end: 17, tz: 3, days: [0, 1, 2, 3, 6], open: null, closed: null },
  jump: { flow: "" }, handoff: { text: "", reason: "" }, end: { text: "" },
  location: { lat: "", lng: "", name: "", address: "" },
  template: { name: "", lang: "ar", vars: [], fail: null },
  ai: { text: "", turns: 5, exit: [], fail: null },
  api: { method: "GET", url: "https://", headers: [], body: "", save: [], status_var: "", fail: null },
  sheets: { url: "", fields: [] },
  assign: { mode: "least", member: null, text: "" },
  switch: { var: "", cases: [{ value: "", next: null }], other: null },
  resolve: { text: "" }, sequence: { sequence: null },
  products: { catalog: "", items: [], header: "", text: "", fail: null },
  form: { flow_id: "", screen: "", cta: "", text: "", header: "", prefix: "", fail: null },
  payment: { amount: "", currency: "", description: "", text: "", button: "", minutes: 60, var: "", fail: null },
};
const OPS = [["eq", ["يساوي", "equals"]], ["neq", ["لا يساوي", "not equal"]], ["contains", ["يحتوي", "contains"]],
  ["gt", ["أكبر من", "greater than"]], ["lt", ["أصغر من", "less than"]], ["empty", ["فارغ", "is empty"]], ["not_empty", ["غير فارغ", "is not empty"]]];
const VALIDATE = [["text", ["أي نص", "Any text"]], ["number", ["رقم", "Number"]], ["email", ["بريد إلكتروني", "Email"]],
  ["phone", ["رقم هاتف", "Phone"]], ["date", ["تاريخ", "Date"]], ["url", ["رابط", "URL"]]];
// ترقيم Python لأيام الأسبوع (0 الاثنين) — المحرك يقارن weekday() مباشرة
const DAYS = [[5, ["سبت", "Sat"]], [6, ["أحد", "Sun"]], [0, ["إثنين", "Mon"]], [1, ["ثلاثاء", "Tue"]], [2, ["أربعاء", "Wed"]], [3, ["خميس", "Thu"]], [4, ["جمعة", "Fri"]]];

const ERR = {
  name: ["اكتب اسماً للفلو", "Give the flow a name"], limit: ["وصلت للحد الأقصى من الفلوهات", "Flow limit reached"],
  role: ["التعديل للمالك ومديري الفريق", "Editing is for owners and team admins"], plan: ["الميزة في باقة الشركات", "Available on the Enterprise plan"],
  not_published: ["انشر الفلو أولاً", "Publish the flow first"], in_use: ["فلو منشور آخر ينتقل إليه — عدّله أولاً", "Another published flow jumps to it — change that first"],
  "flow:size": ["الفلو فارغ أو أكبر من الحد", "Flow is empty or too large"], "flow:start": ["حدّد بطاقة البداية", "Choose a start card"],
  "flow:ids": ["معرّفات بطاقات غير صالحة", "Invalid card ids"], "flow:keywords": ["أضف كلمة مفتاحية واحدة على الأقل", "Add at least one keyword"],
  "flow:timeout": ["مدة الإغلاق يجب أن تكون أطول من التذكير", "Close time must be longer than the reminder"],
  "flow:remind_text": ["اكتب نص التذكير في إعدادات الفلو", "Write the reminder text in flow settings"],
  "flow:links": ["اختر رابط تتبّع واحداً على الأقل", "Pick at least one tracking link"],
  network: ["تعذّر الاتصال", "Connection failed"],
};
const NODE_ERR = {
  text: ["النص مطلوب", "Text is required"], var: ["اسم متغيّر غير صالح — حروف وأرقام و _ بلا مسافات", "Invalid variable name — letters, digits and _ only"],
  options: ["من زر واحد إلى 10 أزرار", "Between 1 and 10 buttons"], option_label: ["كل زر يحتاج اسماً مختلفاً (حتى 20 حرفاً)", "Each button needs a unique label (max 20 chars)"],
  asset: ["اختر ملفاً من مكتبتك", "Pick a file from your library"], tags: ["أضف وسماً واحداً على الأقل", "Add at least one tag"],
  field: ["اختر حقلاً", "Choose a field"], flow: ["اختر الفلو المنتقَل إليه", "Choose the target flow"],
  hours: ["ساعات غير صالحة", "Invalid hours"], seconds: ["مدة غير صالحة", "Invalid duration"],
  next: ["توصيلة غير صالحة", "Invalid connection"], type: ["نوع بطاقة غير معروف", "Unknown card type"],
  location: ["إحداثيات غير صالحة", "Invalid coordinates"], template: ["اختر قالباً معتمداً", "Choose an approved template"],
  url: ["رابط HTTPS صالح، والمضيف نص ثابت بلا متغيّرات", "A valid HTTPS URL with a fixed host (no variables)"],
  headers: ["ترويسة غير مسموحة", "Header not allowed"], save: ["مسار أو اسم متغيّر غير صالح", "Invalid path or variable name"],
  status_var: ["اسم متغيّر غير صالح", "Invalid variable name"], sheets: ["الصق رابط Web App من Apps Script (ينتهي بـ /exec)", "Paste the Apps Script Web App URL (ends with /exec)"],
  turns: ["عدد أسئلة غير صالح", "Invalid number of questions"], member: ["اختر موظفاً من فريقك", "Choose a member of your team"],
  cases: ["كل قيمة مطلوبة ومختلفة (حتى 10)", "Each value is required and unique (up to 10)"],
  catalog: ["معرّف كتالوج رقمي من Commerce Manager", "A numeric catalog ID from Commerce Manager"],
  items: ["من منتج إلى 30 بمعرّفاتها (Retailer ID)", "1 to 30 products by Retailer ID"],
  header: ["قائمة المنتجات تحتاج عنواناً ونصاً", "A product list needs a header and text"],
  flow_id: ["Flow ID رقمي من WhatsApp Manager", "A numeric Flow ID from WhatsApp Manager"],
  screen: ["اسم الشاشة بالإنجليزية الكبيرة مثل WELCOME", "Screen name in capitals, e.g. WELCOME"],
  prefix: ["بادئة غير صالحة", "Invalid prefix"], amount: ["اكتب المبلغ رقماً أو {{متغيّر}}", "Enter the amount as a number or {{variable}}"],
  currency: ["عملة غير مدعومة", "Unsupported currency"], minutes: ["مدة صلاحية غير صالحة", "Invalid validity period"], sequence: ["اختر تسلسلاً لهذه القناة", "Choose a sequence for this channel"], team: ["اختر فريقاً من فِرق الصندوق المشترك", "Choose a team from the Team inbox"],
};
const errText = (c, other) => {
  if (c === "trigger_taken") return bi(`فلو «${other}» نشط بنفس المشغّل — أوقفه أو غيّر المشغّل`, `“${other}” is active with the same trigger — pause it or change the trigger`);
  if (c && c.startsWith("node:")) {
    const why = c.split(":")[2];
    return bi(...(NODE_ERR[why] || NODE_ERR[["yes", "no", "open", "closed", "option", "fail", "case", "other"].includes(why) ? "next" : "type"]));
  }
  return ERR[c] ? bi(...ERR[c]) : bi("حدث خطأ", "Something went wrong") + (c ? ` (${c})` : "");
};

/* ------------------------------------------------------------ الهندسة */
const W = 252, HEAD = 38, BODY = 50, ROW = 30;
const outs = (n) => {
  if (n.type === "buttons") return (n.options || []).map((o, i) => ({ k: `o${i}`, label: o.label || `#${i + 1}`, to: o.next }));
  if (n.type === "condition") return [{ k: "yes", label: bi("نعم", "Yes"), to: n.yes }, { k: "no", label: bi("لا", "No"), to: n.no }];
  if (n.type === "hours") return [{ k: "open", label: bi("مفتوح", "Open"), to: n.open }, { k: "closed", label: bi("مغلق", "Closed"), to: n.closed }];
  if (n.type === "switch") return [...(n.cases || []).map((c, i) => ({ k: `c${i}`, label: c.value || `#${i + 1}`, to: c.next })),
                                   { k: "other", label: bi("غير ذلك", "Otherwise"), to: n.other }];
  if (TWO_WAY.includes(n.type)) {
    const okL = n.type === "ai" ? bi("انتهى الحوار", "Conversation done") : n.type === "form" ? bi("أُرسل النموذج", "Form submitted")
      : n.type === "payment" ? bi("دُفع ✓", "Paid ✓")
      : ["template", "products"].includes(n.type) ? bi("أُرسل", "Sent") : bi("نجح (2xx)", "Success (2xx)");
    const failL = n.type === "ai" ? bi("الذكاء غير متاح", "AI unavailable") : n.type === "payment" ? bi("لم يُدفع / أُلغي", "Not paid / cancelled") : bi("فشل", "Failed");
    return [{ k: "next", label: okL, to: n.next }, { k: "fail", label: failL, to: n.fail }];
  }
  if (BRANCHING.includes(n.type)) return [];
  return [{ k: "next", label: "", to: n.next }];
};
const setOut = (n, k, to) => {
  if (k === "next") return { ...n, next: to };
  if (/^c\d+$/.test(k)) { const i = +k.slice(1); return { ...n, cases: n.cases.map((c, j) => (j === i ? { ...c, next: to } : c)) }; }
  if (/^o\d+$/.test(k)) { const i = +k.slice(1); return { ...n, options: n.options.map((o, j) => (j === i ? { ...o, next: to } : o)) }; }
  return { ...n, [k]: to };
};
const heightOf = (n) => HEAD + BODY + Math.max(outs(n).length, 0) * ROW + 8;
const portPos = (n, i) => ({ x: n.x + W, y: n.y + HEAD + BODY + i * ROW + ROW / 2 });
const inPos = (n) => ({ x: n.x, y: n.y + HEAD / 2 });
const curve = (a, b) => {
  const dx = Math.max(50, Math.abs(b.x - a.x) / 2);
  return `M${a.x},${a.y} C${a.x + dx},${a.y} ${b.x - dx},${b.y} ${b.x},${b.y}`;
};
const newId = () => "n_" + Math.random().toString(36).slice(2, 8);
const clip = (s, n = 70) => { s = String(s || "").replace(/\s+/g, " ").trim(); return s.length > n ? s.slice(0, n) + "…" : s; };

function summary(n, others) {
  const op = (OPS.find((o) => o[0] === n.op) || OPS[0])[1];
  switch (n.type) {
    case "text": case "notify": return clip(n.text) || bi("اكتب الرسالة…", "Write the message…");
    case "media": return n.asset ? clip(n.caption) || bi("ملف من المكتبة", "Library file") : bi("اختر ملفاً…", "Pick a file…");
    case "buttons": case "ask_media": return clip(n.text) || bi("اكتب السؤال…", "Write the question…");
    case "ask": return (clip(n.text, 44) || bi("اكتب السؤال…", "Write the question…")) + (n.var ? `  → {{${n.var}}}` : "");
    case "tag": return (n.tags || []).length ? (n.tags || []).map((x) => "#" + x).join(" ") : bi("بلا وسوم بعد", "No tags yet");
    case "set_field": return `${n.field || "?"} = ${clip(n.value, 40) || "…"}`;
    case "set_var": return `{{${n.var || "?"}}} = ${clip(n.value, 40) || "…"}`;
    case "save_lead": return bi("يحفظ إجابات العميل في «الإدخالات»", "Saves answers to Entries");
    case "goal": return n.name ? `🎯 ${n.name}` : bi("سمِّ الهدف…", "Name the goal…");
    case "delay": return bi(`انتظر ${n.seconds || 2} ث`, `Wait ${n.seconds || 2}s`);
    case "condition": return n.var ? `${n.var} ${bi(...op)} ${["empty", "not_empty"].includes(n.op) ? "" : clip(n.value, 24)}` : bi("حدّد الشرط…", "Set the condition…");
    case "hours": return `${String(n.start).padStart(2, "0")}:00–${String(n.end).padStart(2, "0")}:00 · UTC${n.tz >= 0 ? "+" : ""}${n.tz}`;
    case "jump": { const f = others.find((x) => x.id === n.flow); return f ? `→ ${f.name}` : bi("اختر فلو…", "Choose a flow…"); }
    case "handoff": return clip(n.text) || bi("يحوّل المحادثة لصندوق الوارد", "Moves the chat to the inbox");
    case "end": return clip(n.text) || bi("نهاية المحادثة", "End of conversation");
    case "location": return n.name || (n.lat !== "" && n.lng !== "" ? `📍 ${n.lat}, ${n.lng}` : bi("حدّد الموقع…", "Set the location…"));
    case "template": return n.name ? `📄 ${n.name} (${n.lang})` : bi("اختر قالباً معتمداً…", "Pick an approved template…");
    case "ai": return (clip(n.text, 40) || bi("يجيب أسئلة العميل", "Answers customer questions")) + ` · ${bi("حتى", "up to")} ${n.turns || 5}`;
    case "api": return n.url && n.url !== "https://" ? `${n.method} ${clip(n.url.replace(/^https:\/\//, ""), 44)}` : bi("حدّد الرابط…", "Set the URL…");
    case "sheets": return n.url ? bi("يضيف صفاً في الجدول", "Appends a row") : bi("ألصق رابط Apps Script…", "Paste the Apps Script URL…");
    case "switch": return n.var ? `${n.var}: ${(n.cases || []).map((c) => c.value).filter(Boolean).join(" · ")}` : bi("اختر المتغيّر…", "Choose the variable…");
    case "resolve": return clip(n.text) || bi("يغلق المحادثة ويعيدها للبوت", "Closes the chat and returns it to the bot");
    case "sequence": { const s = (P.sequences || []).find((x) => x.id === n.sequence); return s ? `→ ${s.name}` : bi("اختر تسلسلاً…", "Choose a sequence…"); }
    case "products": return n.catalog ? bi(`${(n.items || []).length} منتج من الكتالوج`, `${(n.items || []).length} catalog product(s)`) : bi("حدّد الكتالوج والمنتجات…", "Set catalog and products…");
    case "form": return clip(n.text, 40) || bi("نموذج من WhatsApp Flows…", "A WhatsApp Flows form…");
    case "payment": return n.amount ? `💳 ${clip(n.amount, 20)} ${n.currency || P.pay?.currency || ""}${n.description ? " · " + clip(n.description, 30) : ""}` : bi("حدّد المبلغ…", "Set the amount…");
    case "assign": {
      if (n.mode === "team") { const tm = (P.teams || []).find((x) => x.id === n.team); return tm ? `→ ${bi("فريق", "Team")} ${tm.name}` : bi("اختر فريقاً…", "Choose a team…"); }
      const m = (P.members || []).find((x) => x.id === n.member);
      return n.mode === "least" ? bi("الأقل انشغالاً في الحساب", "Least busy teammate") : m ? `→ ${m.username}` : bi("اختر موظفاً…", "Choose a member…");
    }
    default: return "";
  }
}

/* ------------------------------------------------------------ المشغّل */
function TriggerFields({ value, onChange }) {
  const tr = value || { type: "any", keywords: [], match: "contains" };
  const [kw, setKw] = useState((tr.keywords || []).join("، "));
  useEffect(() => { setKw((tr.keywords || []).join("، ")); }, [tr.type]); // eslint-disable-line react-hooks/exhaustive-deps
  return (
    <div className="grid gap-3">
      <Field label={bi("يبدأ عندما", "Starts when")}>
        <Select value={tr.type} onChange={(e) => onChange({ ...tr, type: e.target.value })}>
          <option value="any">{bi("أي رسالة من العميل", "The customer sends any message")}</option>
          <option value="keywords">{bi("رسالة فيها كلمة مفتاحية", "A message has a keyword")}</option>
          <option value="start">{bi("أول رسالة / زر البدء", "First message / Start button")}</option>
          <option value="ad">{bi("نقرة إعلان Click-to-WhatsApp", "A Click-to-WhatsApp ad click")}</option>
          <option value="link">{bi("رابط تتبّع بعينه", "A specific tracking link")}</option>
        </Select>
      </Field>
      {tr.type === "ad" && (
        <Field label={bi("معرّفات الإعلانات (اختياري)", "Ad IDs (optional)")} hint={bi("فارغ = أي إعلان. المعرّف من مدير الإعلانات أو من تقرير «النمو والإعلانات».", "Empty = any ad. The ID is in Ads Manager or the Growth & ads report.")}>
          <Input dir="ltr" defaultValue={(tr.ads || []).join(", ")} onChange={(e) => onChange({ ...tr, ads: e.target.value.split(/[,\s]+/).filter(Boolean) })} />
        </Field>
      )}
      {tr.type === "link" && (
        <Field label={bi("الروابط", "Links")} hint={bi("أنشئ الروابط من «النمو والإعلانات».", "Create links in Growth & ads.")}>
          <div className="flex flex-wrap gap-1.5">
            {(P.links || []).map((l) => { const on = (tr.links || []).includes(l.code); return (
              <button key={l.code} type="button" onClick={() => onChange({ ...tr, links: on ? tr.links.filter((x) => x !== l.code) : [...(tr.links || []), l.code] })}
                      className={`cursor-pointer rounded-lg border-0 px-3 py-1.5 text-[12.5px] font-bold ${on ? "bg-au-teal/20 text-au-teal" : "bg-ov/5 text-ink-3"}`} dir="auto">{l.name}</button>); })}
            {!(P.links || []).length && <span className="text-[12.5px] text-ink-3">{bi("لا روابط لهذه القناة بعد.", "No links for this channel yet.")}</span>}
          </div>
        </Field>
      )}
      {tr.type === "keywords" && <>
        <Field label={bi("الكلمات المفتاحية", "Keywords")} hint={bi("افصل بفاصلة. الهمزات والتشكيل لا تفرق.", "Comma-separated. Accents and diacritics are ignored.")}>
          <Input value={kw} dir="auto" placeholder={bi("حجز، أسعار، menu", "booking, prices, menu")}
                 onChange={(e) => { setKw(e.target.value); onChange({ ...tr, keywords: e.target.value.split(/[,،]/).map((s) => s.trim()).filter(Boolean) }); }} />
        </Field>
        <Field label={bi("المطابقة", "Match")}>
          <Select value={tr.match || "contains"} onChange={(e) => onChange({ ...tr, match: e.target.value })}>
            <option value="contains">{bi("الرسالة تحتوي الكلمة", "Message contains the word")}</option>
            <option value="exact">{bi("الرسالة هي الكلمة بالضبط", "Message is exactly the word")}</option>
          </Select>
        </Field>
      </>}
    </div>
  );
}
const trigLabel = (tr) => (!tr || tr.type === "any") ? bi("أي رسالة", "Any message")
  : tr.type === "start" ? bi("البداية", "Start")
  : tr.type === "ad" ? bi("نقرة إعلان", "Ad click") + (tr.ads?.length ? ` (${tr.ads.length})` : "")
  : tr.type === "link" ? bi("رابط تتبّع", "Tracking link") + (tr.links?.length ? ` (${tr.links.length})` : "")
  : (tr.keywords || []).slice(0, 3).join("، ") + ((tr.keywords || []).length > 3 ? "…" : "");

/* ------------------------------------------------------------ لوحة الخصائص */
function Props({ id, node, isStart, others, vars, tpls, onChange, onStart, onDelete, onDup, onClose, error }) {
  const up = (patch) => onChange({ ...node, ...patch });
  const meta = TYPES[node.type];
  const varHint = bi("في النص: {{اسم_المتغيّر}} أو {{contact.name}}", "In text: {{variable}} or {{contact.name}}");
  const text = (label, key = "text", rows = 4) => (
    <Field label={label} hint={varHint}>
      <Textarea dir="auto" rows={rows} value={node[key] || ""} onChange={(e) => up({ [key]: e.target.value })} />
    </Field>
  );
  const varField = (label, required = true) => (
    <Field label={label} hint={required ? bi("مثل: city أو المدينة — بلا مسافات", "e.g. city — no spaces") : bi("اختياري — لحفظ الاختيار في متغيّر", "Optional — store the choice in a variable")}>
      <Input dir="auto" value={node.var || ""} onChange={(e) => up({ var: e.target.value.replace(/\s/g, "_") })} />
    </Field>
  );
  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-between gap-2 border-b border-ov/10 px-4 py-3">
        <b className="flex items-center gap-2 text-[14px] text-ink">
          <span className="grid size-7 place-items-center rounded-lg" style={{ background: meta.c + "26", color: meta.c }}><Icon name={meta.icon} size={15} /></span>
          {bi(...meta.l)}
        </b>
        <Btn sm variant="ghost" onClick={onClose} aria-label={bi("إغلاق", "Close")}><Icon name="close" size={14} /></Btn>
      </div>
      <div className="grid flex-1 content-start gap-4 overflow-y-auto p-4">
        {error && <div className="rounded-xl bg-red-400/10 px-3 py-2 text-[12.5px] font-bold text-red-400">{error}</div>}
        {node.type === "text" && text(bi("الرسالة", "Message"))}
        {node.type === "notify" && text(bi("نص التنبيه (يصلك أنت وفريقك)", "Alert text (sent to you and your team)"))}
        {node.type === "media" && <>
          <Field label={bi("الملف", "File")} hint={bi("صورة أو فيديو أو صوت (OGG يصل رسالةً صوتية)", "Image, video or audio (OGG arrives as a voice note)")}>
            <AssetPicker value={node.asset || ""} kinds={["image", "video", "audio"]} onChange={(v) => up({ asset: v ? Number(v) : null })} />
          </Field>
          {text(bi("تعليق (اختياري)", "Caption (optional)"), "caption", 3)}
        </>}
        {node.type === "buttons" && <>
          {text(bi("السؤال", "Question"), "text", 3)}
          <div>
            <span className="mb-1.5 block text-[13px] font-bold text-ink-2">{bi("الأزرار", "Buttons")}</span>
            <div className="grid gap-2">
              {(node.options || []).map((o, i) => (
                <div key={i} className="flex items-center gap-2">
                  <Input dir="auto" maxLength={20} value={o.label} placeholder={bi(`زر ${i + 1}`, `Button ${i + 1}`)}
                         onChange={(e) => up({ options: node.options.map((x, j) => (j === i ? { ...x, label: e.target.value } : x)) })} />
                  <Btn sm variant="ghost" disabled={node.options.length <= 1} aria-label={bi("حذف", "Remove")}
                       onClick={() => up({ options: node.options.filter((_, j) => j !== i) })}><Icon name="trash" size={14} /></Btn>
                </div>
              ))}
            </div>
            {(node.options || []).length < 10 &&
              <Btn sm variant="ghost" icon="plus" className="mt-2" onClick={() => up({ options: [...(node.options || []), { label: "", next: null }] })}>{bi("زر", "Button")}</Btn>}
            <p className="mb-0 mt-2 text-[12px] leading-relaxed text-ink-3">{bi("واتساب يعرض حتى 3 أزرار، وأكثر منها كقائمة. حتى 20 حرفاً للزر.", "WhatsApp shows up to 3 buttons, more as a list. Max 20 characters each.")}</p>
          </div>
          {varField(bi("حفظ الاختيار في متغيّر", "Save choice to variable"), false)}
        </>}
        {node.type === "ask" && <>
          {text(bi("السؤال", "Question"), "text", 3)}
          {varField(bi("حفظ الإجابة في متغيّر", "Save answer to variable"))}
          <Field label={bi("نوع الإجابة", "Answer type")}>
            <Select value={node.validate || "text"} onChange={(e) => up({ validate: e.target.value })}>
              {VALIDATE.map(([k, l]) => <option key={k} value={k}>{bi(...l)}</option>)}
            </Select>
          </Field>
          <Field label={bi("رسالة الخطأ (اختياري)", "Error message (optional)")} hint={bi("تُرسل عند إجابة لا تناسب النوع، ويُعاد السؤال", "Sent when the answer doesn't fit; the question waits again")}>
            <Input dir="auto" value={node.error || ""} onChange={(e) => up({ error: e.target.value })} />
          </Field>
        </>}
        {node.type === "ask_media" && <>
          {text(bi("الطلب", "Request"), "text", 3)}
          {varField(bi("حفظ الملف في متغيّر", "Save file to variable"))}
        </>}
        {node.type === "tag" && (
          <Field label={bi("الوسوم", "Tags")} hint={bi("افصل بفاصلة. الوسم الجديد يُنشأ تلقائياً على جهة الاتصال.", "Comma-separated. New tags are created on the contact.")}>
            <Input dir="auto" defaultValue={(node.tags || []).join("، ")}
                   onChange={(e) => up({ tags: e.target.value.split(/[,،]/).map((s) => s.trim()).filter(Boolean) })} />
          </Field>
        )}
        {node.type === "set_field" && <>
          <Field label={bi("الحقل", "Field")}>
            <Select value={node.field || "name"} onChange={(e) => up({ field: e.target.value })}>
              <option value="name">{bi("الاسم", "Name")}</option>
              <option value="email">{bi("البريد", "Email")}</option>
              {(P.fields || []).map((f) => <option key={f.key} value={f.key}>{f.label}</option>)}
            </Select>
          </Field>
          <Field label={bi("القيمة", "Value")} hint={bi("مثل {{email}} من سؤال سابق", "e.g. {{email}} from an earlier question")}>
            <Input dir="auto" value={node.value || ""} onChange={(e) => up({ value: e.target.value })} />
          </Field>
        </>}
        {node.type === "set_var" && <>
          {varField(bi("المتغيّر", "Variable"))}
          <Field label={bi("القيمة", "Value")} hint={varHint}><Input dir="auto" value={node.value || ""} onChange={(e) => up({ value: e.target.value })} /></Field>
        </>}
        {node.type === "save_lead" && <p className="m-0 text-[13px] leading-relaxed text-ink-3">{bi("يحفظ كل إجابات العميل حتى هذه النقطة في «الإدخالات» ويرفق ملفاته. الفلو يحفظها تلقائياً عند نهايته أيضاً.", "Saves every answer so far to Entries with the customer's files. The flow also saves automatically when it ends.")}</p>}
        {node.type === "goal" && <>
          <Field label={bi("اسم الهدف", "Goal name")} hint={bi("يُحتسب في التحليلات كلما وصل عميل لهذه البطاقة", "Counted in analytics every time a customer reaches this card")}>
            <Input value={node.name || ""} onChange={(e) => up({ name: e.target.value })} />
          </Field>
          {P.channel === "whatsapp" && <>
            <Field label={bi("تحويل لـ Meta (Conversions API)", "Meta conversion (Conversions API)")}
                   hint={P.capi ? bi("يُرسل لمن جاء من إعلان خلال 7 أيام — يحسّن استهداف إعلاناتك.", "Sent for customers who came from an ad within 7 days — improves your ad targeting.")
                                : bi("اضبط Conversions API من «النمو والإعلانات» ← الإعلانات.", "Set up the Conversions API in Growth & ads → Ads.")}>
              <Select value={node.event || ""} onChange={(e) => up({ event: e.target.value })}>
                <option value="">{bi("— لا شيء —", "— none —")}</option>
                {(P.capiEvents || []).map((ev) => <option key={ev} value={ev}>{ev}</option>)}
              </Select>
            </Field>
            {node.event === "Purchase" && (
              <div className="grid grid-cols-[1fr_90px] gap-2">
                <Field label={bi("القيمة", "Value")} hint={bi("رقم أو متغيّر مثل {{total}}", "A number or a variable like {{total}}")}><Input dir="ltr" value={node.value || ""} onChange={(e) => up({ value: e.target.value })} /></Field>
                <Field label={bi("العملة", "Currency")}><Input dir="ltr" maxLength={3} value={node.currency || "SAR"} onChange={(e) => up({ currency: e.target.value.toUpperCase() })} /></Field>
              </div>
            )}
          </>}
        </>}
        {node.type === "delay" && (
          <Field label={bi("مدة الانتظار (ثوانٍ)", "Wait (seconds)")} hint={bi(`من 1 إلى ${P.limits?.delay || 30} ثانية`, `1 to ${P.limits?.delay || 30} seconds`)}>
            <Input type="number" min={1} max={P.limits?.delay || 30} value={node.seconds || 2} onChange={(e) => up({ seconds: Number(e.target.value) || 1 })} />
          </Field>
        )}
        {node.type === "condition" && <>
          <Field label={bi("المتغيّر", "Variable")} hint={bi("متغيّر من سؤال، أو contact.name / contact.حقل", "A question variable, or contact.name / contact.field")}>
            <Input dir="auto" list="flow-vars" value={node.var || ""} onChange={(e) => up({ var: e.target.value.trim() })} />
          </Field>
          <Field label={bi("الشرط", "Operator")}>
            <Select value={node.op || "eq"} onChange={(e) => up({ op: e.target.value })}>
              {OPS.map(([k, l]) => <option key={k} value={k}>{bi(...l)}</option>)}
            </Select>
          </Field>
          {!["empty", "not_empty"].includes(node.op) &&
            <Field label={bi("القيمة", "Value")}><Input dir="auto" value={node.value || ""} onChange={(e) => up({ value: e.target.value })} /></Field>}
          <datalist id="flow-vars">{vars.map((v) => <option key={v} value={v} />)}</datalist>
        </>}
        {node.type === "hours" && <>
          <div className="grid grid-cols-3 gap-2">
            <Field label={bi("من", "From")}><Input type="number" min={0} max={23} value={node.start} onChange={(e) => up({ start: Number(e.target.value) })} /></Field>
            <Field label={bi("إلى", "To")}><Input type="number" min={1} max={24} value={node.end} onChange={(e) => up({ end: Number(e.target.value) })} /></Field>
            <Field label="UTC ±"><Input type="number" step="0.5" min={-12} max={14} value={node.tz} onChange={(e) => up({ tz: Number(e.target.value) })} /></Field>
          </div>
          <div className="flex flex-wrap gap-1.5">
            {DAYS.map(([d, l]) => {
              const on = (node.days || []).includes(d);
              return <button key={d} type="button" onClick={() => up({ days: on ? node.days.filter((x) => x !== d) : [...(node.days || []), d] })}
                             className={`cursor-pointer rounded-lg border-0 px-2.5 py-1.5 text-[12px] font-bold ${on ? "bg-au-teal/20 text-au-teal" : "bg-ov/5 text-ink-3"}`}>{bi(...l)}</button>;
            })}
          </div>
          <p className="m-0 text-[12px] text-ink-3">{bi("مصر UTC+2 أو +3 صيفاً · السعودية UTC+3", "Egypt UTC+2 (+3 summer) · Saudi UTC+3")}</p>
        </>}
        {node.type === "jump" && (
          <Field label={bi("الانتقال إلى", "Go to")} hint={bi("الفلو المستهدف يجب أن يكون منشوراً", "The target flow must be published")}>
            <Select value={node.flow || ""} onChange={(e) => up({ flow: e.target.value })}>
              <option value="">{bi("— اختر —", "— choose —")}</option>
              {others.map((f) => <option key={f.id} value={f.id}>{f.name}</option>)}
            </Select>
          </Field>
        )}
        {node.type === "handoff" && <>
          {text(bi("رسالة للعميل (اختياري)", "Message to the customer (optional)"), "text", 3)}
          <Field label={bi("سبب التحويل (يظهر لفريقك)", "Reason (shown to your team)")}><Input dir="auto" value={node.reason || ""} onChange={(e) => up({ reason: e.target.value })} /></Field>
          <Field label={bi("إلى فريق", "To team")} hint={bi("فارغ = فريق القناة الافتراضي من إعدادات الصندوق المشترك. التالي بالتناوب يستلمها.", "Empty = the channel's default team (Team inbox settings). The next member in turn gets it.")}>
            <Select value={String(node.team || "")} onChange={(e) => up({ team: Number(e.target.value) || null })}>
              <option value="">{bi("— الافتراضي —", "— Default —")}</option>
              {(P.teams || []).map((tm) => <option key={tm.id} value={String(tm.id)}>{tm.name}</option>)}
            </Select>
          </Field>
        </>}
        {node.type === "end" && text(bi("رسالة ختامية (اختياري)", "Closing message (optional)"), "text", 3)}
        {node.type === "location" && <>
          <div className="grid grid-cols-2 gap-2">
            <Field label={bi("خط العرض", "Latitude")}><Input dir="ltr" inputMode="decimal" value={node.lat} placeholder="21.4225" onChange={(e) => up({ lat: e.target.value })} /></Field>
            <Field label={bi("خط الطول", "Longitude")}><Input dir="ltr" inputMode="decimal" value={node.lng} placeholder="39.8262" onChange={(e) => up({ lng: e.target.value })} /></Field>
          </div>
          <Field label={bi("لصق من خرائط جوجل", "Paste from Google Maps")} hint={bi("انسخ الإحداثيات من خرائط جوجل (مثل 21.4225, 39.8262) والصقها هنا", "Copy coordinates from Google Maps (e.g. 21.4225, 39.8262) and paste here")}>
            <Input dir="ltr" placeholder="21.4225, 39.8262" onChange={(e) => { const m = e.target.value.match(/(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)/); if (m) up({ lat: m[1], lng: m[2] }); }} />
          </Field>
          <Field label={bi("الاسم", "Name")}><Input dir="auto" maxLength={100} value={node.name || ""} onChange={(e) => up({ name: e.target.value })} /></Field>
          <Field label={bi("العنوان", "Address")}><Input dir="auto" maxLength={200} value={node.address || ""} onChange={(e) => up({ address: e.target.value })} /></Field>
          <p className="m-0 text-[12px] text-ink-3">{bi("واتساب: دبّوس خريطة. القنوات الأخرى: رابط خرائط جوجل.", "WhatsApp: a map pin. Other channels: a Google Maps link.")}</p>
        </>}
        {node.type === "template" && <>
          {P.channel !== "whatsapp" && <div className="rounded-xl bg-yellow-400/10 px-3 py-2 text-[12.5px] font-bold text-yellow-300">{bi("القوالب لواتساب فقط — في القنوات الأخرى يذهب لفرع «فشل».", "Templates are WhatsApp-only — other channels take the “Failed” branch.")}</div>}
          <Field label={bi("القالب", "Template")} hint={tpls === null ? bi("جارٍ جلب القوالب المعتمدة…", "Loading approved templates…") : !tpls.length ? bi("لا قوالب معتمدة — أنشئها من «القوالب»", "No approved templates — create one in Templates") : bi("المعتمدة فقط. التسويقية تُخصم من الرصيد كالبث، وتُردّ لو رفضتها Meta.", "Approved only. Marketing ones are charged like broadcasts and refunded if Meta refuses.")}>
            <Select value={node.name ? `${node.name}|${node.lang}` : ""} onChange={(e) => {
              const [name, lang] = e.target.value.split("|"); const tp = (tpls || []).find((x) => x.name === name && x.language === lang);
              up({ name, lang, vars: (tp?.vars || []).map((_, i) => (node.vars || [])[i] || "") });
            }}>
              <option value="">{bi("— اختر —", "— choose —")}</option>
              {(tpls || []).map((x) => <option key={x.name + x.language} value={`${x.name}|${x.language}`}>{x.name} · {x.language} · {x.category}</option>)}
            </Select>
          </Field>
          {(node.vars || []).map((v, i) => (
            <Field key={i} label={`{{${i + 1}}}`} hint={i === 0 ? varHint : null}>
              <Input dir="auto" value={v} onChange={(e) => up({ vars: node.vars.map((x, j) => (j === i ? e.target.value : x)) })} />
            </Field>
          ))}
        </>}
        {node.type === "ai" && <>
          {text(bi("رسالة البداية (اختياري)", "Opening message (optional)"), "text", 3)}
          <Field label={bi("عدد الأسئلة قبل المتابعة", "Questions before continuing")} hint={bi("يجيب «عقل البوت» من معرفة البوت ثم يكمل الفلو. بالحصة الشهرية ثم الرصيد.", "The bot brain answers from the bot's knowledge, then the flow continues. Uses the monthly allowance, then the wallet.")}>
            <Input type="number" min={1} max={20} value={node.turns || 5} onChange={(e) => up({ turns: Number(e.target.value) || 1 })} />
          </Field>
          <Field label={bi("كلمات الخروج", "Exit words")} hint={bi("افصل بفاصلة. فارغ = خلاص، شكرا، القائمة، menu", "Comma-separated. Empty = خلاص, شكرا, القائمة, menu")}>
            <Input dir="auto" defaultValue={(node.exit || []).join("، ")} onChange={(e) => up({ exit: e.target.value.split(/[,،]/).map((s) => s.trim()).filter(Boolean) })} />
          </Field>
        </>}
        {node.type === "api" && <>
          <div className="grid grid-cols-[96px_1fr] gap-2">
            <Field label={bi("الطريقة", "Method")}>
              <Select value={node.method || "GET"} onChange={(e) => up({ method: e.target.value })}>{METHODS.map((m) => <option key={m} value={m}>{m}</option>)}</Select>
            </Field>
            <Field label={bi("الرابط", "URL")}><Input dir="ltr" value={node.url || ""} onChange={(e) => up({ url: e.target.value })} /></Field>
          </div>
          <p className="m-0 text-[12px] leading-relaxed text-ink-3">{bi("HTTPS فقط. المتغيّرات مسموحة في المسار والاستعلام لا في اسم المضيف: https://api.site.com/rooms?city={{city}}", "HTTPS only. Variables allowed in path/query, not the host: https://api.site.com/rooms?city={{city}}")}</p>
          <div>
            <span className="mb-1.5 block text-[13px] font-bold text-ink-2">{bi("الترويسات", "Headers")}</span>
            {(node.headers || []).map((h, i) => (
              <div key={i} className="mb-2 flex gap-2">
                <Input dir="ltr" className="!w-[40%]" placeholder="Authorization" value={h.k} onChange={(e) => up({ headers: node.headers.map((x, j) => (j === i ? { ...x, k: e.target.value } : x)) })} />
                <Input dir="ltr" placeholder="Bearer …" value={h.v} onChange={(e) => up({ headers: node.headers.map((x, j) => (j === i ? { ...x, v: e.target.value } : x)) })} />
                <Btn sm variant="ghost" onClick={() => up({ headers: node.headers.filter((_, j) => j !== i) })} aria-label={bi("حذف", "Remove")}><Icon name="trash" size={14} /></Btn>
              </div>
            ))}
            {(node.headers || []).length < 5 && <Btn sm variant="ghost" icon="plus" onClick={() => up({ headers: [...(node.headers || []), { k: "", v: "" }] })}>{bi("ترويسة", "Header")}</Btn>}
          </div>
          {node.method !== "GET" && (
            <Field label={bi("الجسم", "Body")} hint={bi('JSON مثل {"name": "{{name}}"} — القيم تُهرَّب تلقائياً', 'JSON like {"name": "{{name}}"} — values are escaped automatically')}>
              <Textarea dir="ltr" rows={4} className="font-mono !text-[12.5px]" value={node.body || ""} onChange={(e) => up({ body: e.target.value })} />
            </Field>
          )}
          <div>
            <span className="mb-1.5 block text-[13px] font-bold text-ink-2">{bi("احفظ من الرد", "Save from response")}</span>
            {(node.save || []).map((m, i) => (
              <div key={i} className="mb-2 flex gap-2">
                <Input dir="ltr" className="!w-[45%]" placeholder="data.price" value={m.path} onChange={(e) => up({ save: node.save.map((x, j) => (j === i ? { ...x, path: e.target.value } : x)) })} />
                <Input dir="auto" placeholder={bi("متغيّر", "variable")} value={m.var} onChange={(e) => up({ save: node.save.map((x, j) => (j === i ? { ...x, var: e.target.value.replace(/\s/g, "_") } : x)) })} />
                <Btn sm variant="ghost" onClick={() => up({ save: node.save.filter((_, j) => j !== i) })} aria-label={bi("حذف", "Remove")}><Icon name="trash" size={14} /></Btn>
              </div>
            ))}
            {(node.save || []).length < 10 && <Btn sm variant="ghost" icon="plus" onClick={() => up({ save: [...(node.save || []), { path: "", var: "" }] })}>{bi("قيمة", "Value")}</Btn>}
          </div>
          <Field label={bi("حفظ رمز الحالة في متغيّر (اختياري)", "Save status code to variable (optional)")}>
            <Input dir="auto" value={node.status_var || ""} onChange={(e) => up({ status_var: e.target.value.replace(/\s/g, "_") })} />
          </Field>
        </>}
        {node.type === "sheets" && <>
          <Field label={bi("رابط Web App", "Web App URL")} hint="https://script.google.com/macros/s/…/exec">
            <Input dir="ltr" value={node.url || ""} onChange={(e) => up({ url: e.target.value.trim() })} />
          </Field>
          <Field label={bi("الأعمدة (المتغيّرات)", "Columns (variables)")} hint={bi("افصل بفاصلة. فارغ = كل إجابات العميل. يُضاف دائماً: الهاتف والفلو والوقت.", "Comma-separated. Empty = all answers. Always added: phone, flow and time.")}>
            <Input dir="auto" defaultValue={(node.fields || []).join("، ")} onChange={(e) => up({ fields: e.target.value.split(/[,،]/).map((s) => s.trim()).filter(Boolean) })} />
          </Field>
          <details className="rounded-xl bg-ov/[0.04] p-3 text-[12.5px] text-ink-2">
            <summary className="cursor-pointer font-bold">{bi("طريقة الربط (دقيقتان)", "How to connect (2 minutes)")}</summary>
            <ol className="mb-2 mt-2 ps-5 leading-relaxed">
              <li>{bi("افتح الجدول ← Extensions ← Apps Script", "Open the sheet → Extensions → Apps Script")}</li>
              <li>{bi("الصق الكود بالأسفل واحفظ", "Paste the code below and save")}</li>
              <li>{bi("Deploy ← New deployment ← Web app، الوصول: Anyone", "Deploy → New deployment → Web app, access: Anyone")}</li>
              <li>{bi("انسخ رابط /exec والصقه أعلاه", "Copy the /exec URL and paste it above")}</li>
            </ol>
            <pre dir="ltr" className="m-0 max-h-[160px] overflow-auto rounded-lg bg-sink/40 p-2 text-[11px] leading-snug">{SHEETS_SCRIPT}</pre>
            <Btn sm variant="ghost" icon="copy" className="mt-2" onClick={() => { try { navigator.clipboard.writeText(SHEETS_SCRIPT); } catch { /* */ } }}>{bi("نسخ الكود", "Copy code")}</Btn>
          </details>
        </>}
        {node.type === "switch" && <>
          <Field label={bi("المتغيّر", "Variable")} hint={bi("مثل city أو contact.city — كل قيمة تذهب لفرعها", "e.g. city or contact.city — each value takes its own branch")}>
            <Input dir="auto" list="flow-vars" value={node.var || ""} onChange={(e) => up({ var: e.target.value.trim() })} />
          </Field>
          <datalist id="flow-vars">{vars.map((v) => <option key={v} value={v} />)}</datalist>
          <div>
            <span className="mb-1.5 block text-[13px] font-bold text-ink-2">{bi("القيم", "Values")}</span>
            {(node.cases || []).map((c, i) => (
              <div key={i} className="mb-2 flex gap-2">
                <Input dir="auto" maxLength={100} value={c.value} placeholder={bi(`قيمة ${i + 1}`, `Value ${i + 1}`)}
                       onChange={(e) => up({ cases: node.cases.map((x, j) => (j === i ? { ...x, value: e.target.value } : x)) })} />
                <Btn sm variant="ghost" disabled={node.cases.length <= 1} onClick={() => up({ cases: node.cases.filter((_, j) => j !== i) })} aria-label={bi("حذف", "Remove")}><Icon name="trash" size={14} /></Btn>
              </div>
            ))}
            {(node.cases || []).length < 10 && <Btn sm variant="ghost" icon="plus" onClick={() => up({ cases: [...(node.cases || []), { value: "", next: null }] })}>{bi("قيمة", "Value")}</Btn>}
            <p className="mb-0 mt-2 text-[12px] text-ink-3">{bi("المطابقة لا تفرّق بين الهمزات والتشكيل وحالة الأحرف. ما لا يطابق يذهب إلى «غير ذلك».", "Matching ignores accents, diacritics and case. Anything else goes to “Otherwise”.")}</p>
          </div>
        </>}
        {node.type === "sequence" && (
          <Field label={bi("التسلسل", "Sequence")} hint={bi("يُسجَّل العميل فتصله خطوات المتابعة في مواعيدها — والفلو يكمل. أنشئ التسلسلات من صفحة «التسلسلات».", "The customer is enrolled and gets the follow-up steps on schedule — the flow continues. Create sequences on the Sequences page.")}>
            <Select value={String(node.sequence || "")} onChange={(e) => up({ sequence: Number(e.target.value) || null })}>
              <option value="">{bi("— اختر —", "— choose —")}</option>
              {(P.sequences || []).map((s) => <option key={s.id} value={String(s.id)}>{s.name}{s.active ? "" : bi(" (متوقّف)", " (paused)")}</option>)}
            </Select>
          </Field>
        )}
        {node.type === "resolve" && <>
          {text(bi("رسالة ختامية (اختياري)", "Closing message (optional)"), "text", 3)}
          <p className="m-0 text-[12px] leading-relaxed text-ink-3">{bi("ينهي الفلو ويغلق المحادثة: تعود للبوت لو كان موظف يتولّاها، وتُعلَّم مقروءة في صندوق الوارد.", "Ends the flow and closes the chat: it returns to the bot if an agent had it, and is marked read in the inbox.")}</p>
        </>}
        {node.type === "products" && <>
          {P.channel !== "whatsapp" && <div className="rounded-xl bg-yellow-400/10 px-3 py-2 text-[12.5px] font-bold text-yellow-300">{bi("لواتساب فقط — القنوات الأخرى تذهب لفرع «فشل».", "WhatsApp only — other channels take “Failed”.")}</div>}
          <Field label={bi("معرّف الكتالوج (Catalog ID)", "Catalog ID")} hint={bi("من Commerce Manager — الكتالوج المربوط برقم واتساب", "From Commerce Manager — the catalog linked to the WhatsApp number")}>
            <Input dir="ltr" inputMode="numeric" value={node.catalog || ""} onChange={(e) => up({ catalog: e.target.value.replace(/\D/g, "") })} />
          </Field>
          <Field label={bi("المنتجات (Retailer ID)", "Products (Retailer ID)")} hint={bi("افصل بفاصلة — حتى 30. منتج واحد = بطاقة منتج، أكثر = قائمة.", "Comma-separated — up to 30. One = product card, more = a list.")}>
            <Input dir="ltr" defaultValue={(node.items || []).join(", ")} onChange={(e) => up({ items: e.target.value.split(/[,،\s]+/).map((s) => s.trim()).filter(Boolean) })} />
          </Field>
          {(node.items || []).length > 1 && <Field label={bi("عنوان القائمة", "List header")}><Input dir="auto" maxLength={60} value={node.header || ""} onChange={(e) => up({ header: e.target.value })} /></Field>}
          {text(bi("النص", "Text"), "text", 2)}
          <p className="m-0 text-[12px] leading-relaxed text-ink-3">{bi("العميل يضيف للسلة ويرسل الطلب من واتساب — يصل للفلو وصندوق الوارد نصاً (🛒 الكمية × المنتج — السعر).", "The customer adds to cart and sends the order in WhatsApp — it reaches the flow and inbox as text (🛒 qty × product — price).")}</p>
        </>}
        {node.type === "form" && <>
          {P.channel !== "whatsapp" && <div className="rounded-xl bg-yellow-400/10 px-3 py-2 text-[12.5px] font-bold text-yellow-300">{bi("لواتساب فقط — القنوات الأخرى تذهب لفرع «فشل».", "WhatsApp only — other channels take “Failed”.")}</div>}
          <div className="grid grid-cols-2 gap-2">
            <Field label="Flow ID"><Input dir="ltr" inputMode="numeric" value={node.flow_id || ""} onChange={(e) => up({ flow_id: e.target.value.replace(/\D/g, "") })} /></Field>
            <Field label={bi("الشاشة الأولى", "First screen")}><Input dir="ltr" value={node.screen || ""} placeholder="WELCOME" onChange={(e) => up({ screen: e.target.value.toUpperCase().replace(/[^A-Z0-9_]/g, "") })} /></Field>
          </div>
          <Field label={bi("عنوان (اختياري)", "Header (optional)")}><Input dir="auto" maxLength={60} value={node.header || ""} onChange={(e) => up({ header: e.target.value })} /></Field>
          {text(bi("النص", "Text"), "text", 2)}
          <Field label={bi("نص الزر", "Button text")}><Input dir="auto" maxLength={20} value={node.cta || ""} placeholder={bi("احجز الآن", "Book now")} onChange={(e) => up({ cta: e.target.value })} /></Field>
          <Field label={bi("بادئة المتغيّرات (اختياري)", "Variable prefix (optional)")} hint={bi("كل حقل في النموذج يُحفظ متغيّراً باسمه، مثل {{form_date}} مع البادئة form", "Every form field becomes a variable by its name, e.g. {{form_date}} with prefix form")}>
            <Input dir="auto" value={node.prefix || ""} onChange={(e) => up({ prefix: e.target.value.replace(/\s/g, "_") })} />
          </Field>
          <p className="m-0 text-[12px] leading-relaxed text-ink-3">{bi("أنشئ النموذج وانشره من WhatsApp Manager ← Flows، ثم انسخ الـ Flow ID واسم الشاشة الأولى.", "Build and publish the form in WhatsApp Manager → Flows, then copy its Flow ID and first screen name.")}</p>
        </>}
        {node.type === "payment" && <>
          {!P.pay && <div className="rounded-xl bg-yellow-400/10 px-3 py-2 text-[12.5px] font-bold text-yellow-300">
            {bi("لم تُربط بوابة دفع بعد — ", "No payment gateway connected yet — ")}<a href="/payments" className="underline">{bi("اربطها من صفحة المدفوعات", "connect one on the Payments page")}</a>{bi("، وإلى ذلك الحين يذهب العميل لفرع «لم يُدفع».", ". Until then customers take “Not paid”.")}</div>}
          <div className="grid grid-cols-[1fr_130px] gap-2">
            <Field label={bi("المبلغ", "Amount")} hint={bi("رقم مثل 450 أو متغيّر مثل {{total}}", "A number like 450 or a variable like {{total}}")}>
              <Input dir="ltr" list="flow-vars" value={node.amount || ""} placeholder="450" onChange={(e) => up({ amount: e.target.value })} />
            </Field>
            <Field label={bi("العملة", "Currency")}>
              <Select value={node.currency || ""} onChange={(e) => up({ currency: e.target.value })}>
                <option value="">{bi("الافتراضية", "Default")}{P.pay?.currency ? ` (${P.pay.currency})` : ""}</option>
                {(P.pay?.currencies || ["SAR", "EGP", "AED", "KWD", "BHD", "QAR", "OMR", "USD"]).map((c) => <option key={c} value={c}>{c}</option>)}
              </Select>
            </Field>
          </div>
          <Field label={bi("الوصف (يظهر للعميل وفي البوابة)", "Description (shown to the customer and in the gateway)")} hint={varHint}>
            <Input dir="auto" maxLength={200} value={node.description || ""} placeholder={bi("حجز {{room}} — {{nights}} ليالٍ", "{{room}} booking — {{nights}} nights")} onChange={(e) => up({ description: e.target.value })} />
          </Field>
          {text(bi("الرسالة مع زر الدفع (اختياري)", "Message with the pay button (optional)"), "text", 2)}
          <div className="grid grid-cols-2 gap-2">
            <Field label={bi("نص الزر", "Button text")}><Input dir="auto" maxLength={20} value={node.button || ""} placeholder={bi("ادفع الآن", "Pay now")} onChange={(e) => up({ button: e.target.value })} /></Field>
            <Field label={bi("صلاحية الرابط", "Link valid for")}>
              <Select value={String(node.minutes || 60)} onChange={(e) => up({ minutes: Number(e.target.value) })}>
                {[[15, bi("15 دقيقة", "15 min")], [30, bi("30 دقيقة", "30 min")], [60, bi("ساعة", "1 hour")], [180, bi("3 ساعات", "3 hours")], [360, bi("6 ساعات", "6 hours")], [1440, bi("24 ساعة", "24 hours")]].map(([v, l]) => <option key={v} value={String(v)}>{l}</option>)}
              </Select>
            </Field>
          </div>
          {varField(bi("حفظ حالة الدفع في متغيّر", "Save the payment status in a variable"), false)}
          <p className="m-0 text-[12px] leading-relaxed text-ink-3">{bi("يصل العميل زر «ادفع الآن» من بوابتك (مدى · Apple Pay · بطاقة) والفلو ينتظر. عند الدفع: إيصال تلقائي ويكمل من «دُفع» ومعه {{payment_ref}}. إن انتهت المدة أو كتب «إلغاء»: فرع «لم يُدفع».", "The customer gets a “Pay now” button from your gateway (mada · Apple Pay · card) and the flow waits. When paid: an automatic receipt and it continues from “Paid” with {{payment_ref}}. If it expires or they type “cancel”: the “Not paid” branch.")}</p>
        </>}
        {node.type === "assign" && <>
          <Field label={bi("إسناد إلى", "Assign to")}>
            <Select value={node.mode === "least" ? "least" : node.mode === "team" ? `t${node.team || ""}` : String(node.member || "")}
                    onChange={(e) => { const v = e.target.value; up(v === "least" ? { mode: "least", member: null, team: null }
                      : v[0] === "t" ? { mode: "team", team: Number(v.slice(1)) || null, member: null } : { mode: "member", member: Number(v) || null, team: null }); }}>
              <option value="least">{bi("الأقل انشغالاً في الحساب", "Least busy teammate")}</option>
              {(P.teams || []).map((tm) => <option key={"t" + tm.id} value={`t${tm.id}`}>{bi("فريق: ", "Team: ")}{tm.name}</option>)}
              {(P.members || []).map((m) => <option key={m.id} value={String(m.id)}>{m.username}</option>)}
            </Select>
          </Field>
          {text(bi("رسالة للعميل (اختياري)", "Message to the customer (optional)"), "text", 2)}
          <p className="m-0 text-[12px] leading-relaxed text-ink-3">{bi("يصير الموظف مسؤول جهة الاتصال (يظهر في جهات الاتصال وصندوق الوارد)، والفلو يكمل. للتحويل الفوري لإنسان استخدم «تحويل لموظف».", "The member becomes the contact owner (shown in Contacts and Inbox) and the flow continues. For an immediate human takeover use “Hand off”.")}</p>
        </>}
      </div>
      <div className="flex flex-wrap gap-2 border-t border-ov/10 p-3">
        <Btn sm variant="ghost" icon="play" disabled={isStart} onClick={() => onStart(id)}>{isStart ? bi("بطاقة البداية", "Start card") : bi("اجعلها البداية", "Set as start")}</Btn>
        <Btn sm variant="ghost" icon="copy" onClick={() => onDup(id)}>{bi("نسخ", "Duplicate")}</Btn>
        <Btn sm variant="red" icon="trash" onClick={() => onDelete(id)}>{bi("حذف", "Delete")}</Btn>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------ البطاقة على الكانفس */
function NodeCard({ id, n, isStart, selected, error, others, stat, onDown, onPort, linking }) {
  const meta = TYPES[n.type] || TYPES.text;
  const os = outs(n);
  const heat = stat && stat.drop ? Math.min(1, stat.drop / Math.max(stat.maxDrop, 1)) : 0;
  return (
    <div data-node={id} onPointerDown={(e) => onDown(e, id)}
         className={`absolute select-none rounded-2xl bg-[rgb(var(--menu-rgb))] text-start transition-shadow
                     ${selected ? "shadow-[0_0_0_2px_#7c6cf6,0_12px_32px_-12px_rgb(0_0_0/0.5)]" : error ? "shadow-[0_0_0_2px_#f87171]" : "shadow-[inset_0_0_0_1px_rgb(var(--ov-rgb)/0.12),0_10px_28px_-14px_rgb(0_0_0/0.55)]"}
                     ${linking ? "hover:shadow-[0_0_0_2px_#2dd4a7]" : ""}`}
         style={{ left: n.x, top: n.y, width: W, height: heightOf(n) }}>
      <span className="absolute -start-[7px] top-[12px] size-3.5 rounded-full border-2 border-[rgb(var(--menu-rgb))] bg-ink-3" style={{ left: -7 }} />
      <div className="flex items-center gap-2 px-3" style={{ height: HEAD }}>
        <span className="grid size-6 shrink-0 place-items-center rounded-lg" style={{ background: meta.c + "26", color: meta.c }}><Icon name={meta.icon} size={13} /></span>
        <b className="min-w-0 flex-1 truncate text-[12.5px] text-ink">{bi(...meta.l)}</b>
        {isStart && <span className="rounded-full bg-au-teal/20 px-2 py-0.5 text-[10px] font-extrabold text-au-teal">{bi("البداية", "START")}</span>}
        {stat && <span className="tnum rounded-full bg-ov/10 px-2 py-0.5 text-[10.5px] font-extrabold text-ink-2" title={bi("زيارات", "Visits")}>{num(stat.visits)}</span>}
      </div>
      <div className="overflow-hidden px-3 text-[12px] leading-snug text-ink-3" dir="auto" style={{ height: BODY }}>
        {summary(n, others)}
        {stat && stat.drop > 0 && (
          <div className="mt-1 inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-[10.5px] font-extrabold text-red-300"
               style={{ background: `rgb(248 113 113 / ${0.12 + heat * 0.35})` }}>
            ↓ {num(stat.drop)} {bi("توقّفوا هنا", "dropped here")}
          </div>
        )}
      </div>
      {os.map((o, i) => (
        <div key={o.k} className="relative flex items-center justify-end border-t border-ov/[0.07] px-3 text-[11.5px] font-bold text-ink-2" style={{ height: ROW }}>
          <span className="truncate" dir="auto">{o.label || (o.to ? "" : bi("التالي", "Next"))}</span>
          <span data-port={`${id}:${o.k}`} onPointerDown={(e) => onPort(e, id, o.k)}
                className={`absolute size-3.5 cursor-crosshair rounded-full border-2 border-[rgb(var(--menu-rgb))] ${o.to ? "bg-au-cyan" : "bg-ov/40 hover:bg-au-cyan"}`}
                style={{ right: -7, top: ROW / 2 - 7 }} />
        </div>
      ))}
    </div>
  );
}

/* ------------------------------------------------------------ المحرّر */
function Editor({ botId, fid, onClose, onChanged }) {
  const [flow, setFlow] = useState(null);
  const [draft, setDraft] = useState(null);
  const [name, setName] = useState("");
  const [trig, setTrig] = useState(null);
  const [others, setOthers] = useState([]);
  const [stats, setStats] = useState(null);
  const [view, setView] = useState({ x: 40, y: 40, k: 1 });
  const [sel, setSel] = useState(null);            // {node} | {edge:[from,k]}
  const [dirty, setDirty] = useState(false);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState(null);           // {ok, text}
  const [errs, setErrs] = useState({});           // node → نص
  const [heat, setHeat] = useState(false);
  const [trigOpen, setTrigOpen] = useState(false);
  const [timeout, setTimeoutCfg] = useState({});
  const [tpls, setTpls] = useState(null);
  const [test, setTest] = useState(null);          // {code, link, minutes, running}
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [link, setLink] = useState(null);         // {from, k, x, y}
  const box = useRef(null);
  const hist = useRef([]);
  const drag = useRef(null);
  const draftRef = useRef(null);
  draftRef.current = draft;
  const can = !!P.canManage;

  useEffect(() => {
    (async () => {
      const r = await get(`/api/bot/${botId}/flows/${fid}`);
      if (!r.ok) { setMsg({ ok: false, text: errText(r.error) }); return; }
      setFlow(r.flow); setDraft(r.flow.draft); setName(r.flow.name); setTrig(r.flow.trigger);
      setOthers(r.others || []); setStats(r.stats); setTimeoutCfg(r.flow.timeout || {});
      requestAnimationFrame(() => fit(r.flow.draft));
    })();
  }, [botId, fid]); // eslint-disable-line react-hooks/exhaustive-deps

  // القوالب المعتمدة لبطاقة «قالب واتساب» — مرة واحدة عند أول حاجة إليها
  const needTpls = !!draft && Object.values(draft.nodes || {}).some((n) => n.type === "template");
  useEffect(() => {
    if (!needTpls || tpls !== null) return;
    if (P.channel !== "whatsapp") { setTpls([]); return; }
    get(`/api/templates?bot=${botId}`).then((r) => setTpls(r.ok ? (r.items || []).filter((x) => x.status === "APPROVED") : []));
  }, [needTpls, tpls, botId]);

  const flash = (ok, text) => { setMsg({ ok, text }); setTimeout(() => setMsg((m) => (m && m.text === text ? null : m)), 4000); };
  const commit = useCallback((next, keepHist) => {
    if (!keepHist) { hist.current.push(draftRef.current); if (hist.current.length > 60) hist.current.shift(); }
    setDraft(next); setDirty(true);
  }, []);
  const undo = () => { const p = hist.current.pop(); if (p) { setDraft(p); setDirty(true); setSel(null); } };

  const fit = (d = draftRef.current) => {
    const el = box.current; const ns = Object.values((d || {}).nodes || {});
    if (!el || !ns.length) return;
    const x0 = Math.min(...ns.map((n) => n.x)), y0 = Math.min(...ns.map((n) => n.y));
    const x1 = Math.max(...ns.map((n) => n.x + W)), y1 = Math.max(...ns.map((n) => n.y + heightOf(n)));
    const z = zoomOf(), R = el.getBoundingClientRect(), r = { width: R.width / z, height: R.height / z };   // «حجم العرض»
    const k = Math.max(0.35, Math.min(1.1, Math.min((r.width - 80) / (x1 - x0 || 1), (r.height - 80) / (y1 - y0 || 1))));
    setView({ k, x: (r.width - (x1 - x0) * k) / 2 - x0 * k, y: (r.height - (y1 - y0) * k) / 2 - y0 * k });
  };
  const toCanvas = (cx, cy) => {
    const r = box.current.getBoundingClientRect(), z = zoomOf();
    return { x: ((cx - r.left) / z - view.x) / view.k, y: ((cy - r.top) / z - view.y) / view.k };
  };

  // تكبير بعجلة الماوس حول المؤشّر — مستمع غير سلبي لنمنع تمرير الصفحة
  useEffect(() => {
    const el = box.current; if (!el) return undefined;
    const onWheel = (e) => {
      e.preventDefault();
      const r = el.getBoundingClientRect(), z = zoomOf(); const mx = (e.clientX - r.left) / z, my = (e.clientY - r.top) / z;
      setView((v) => {
        const k = Math.max(0.3, Math.min(1.8, v.k * (1 - e.deltaY * 0.0015)));
        return { k, x: mx - (mx - v.x) * (k / v.k), y: my - (my - v.y) * (k / v.k) };
      });
    };
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel);
  }, [draft === null]); // eslint-disable-line react-hooks/exhaustive-deps

  // السحب: تحريك الكانفس · تحريك بطاقة · رسم توصيلة
  useEffect(() => {
    const move = (e) => {
      const d = drag.current; if (!d) return;
      const z = zoomOf();
      if (d.kind === "pan") setView((v) => ({ ...v, x: d.vx + (e.clientX - d.sx) / z, y: d.vy + (e.clientY - d.sy) / z }));
      else if (d.kind === "node") {
        const dx = (e.clientX - d.sx) / z / view.k, dy = (e.clientY - d.sy) / z / view.k;
        if (!d.moved && Math.abs(dx) + Math.abs(dy) < 3) return;
        if (!d.moved) { d.moved = true; hist.current.push(draftRef.current); }
        const cur = draftRef.current;
        setDraft({ ...cur, nodes: { ...cur.nodes, [d.id]: { ...cur.nodes[d.id], x: Math.round(d.nx + dx), y: Math.round(d.ny + dy) } } });
        setDirty(true);
      } else if (d.kind === "link") {
        const p = toCanvas(e.clientX, e.clientY); setLink((l) => l && { ...l, x: p.x, y: p.y });
      }
    };
    const up = (e) => {
      const d = drag.current; drag.current = null; if (!d) return;
      if (d.kind === "link") {
        setLink(null);
        const hit = document.elementFromPoint(e.clientX, e.clientY)?.closest?.("[data-node]");
        const to = hit ? hit.getAttribute("data-node") : null;
        const cur = draftRef.current;
        if (to && to !== d.id) commit({ ...cur, nodes: { ...cur.nodes, [d.id]: setOut(cur.nodes[d.id], d.k, to) } });
        else if (!to) commit({ ...cur, nodes: { ...cur.nodes, [d.id]: setOut(cur.nodes[d.id], d.k, null) } });
      }
    };
    window.addEventListener("pointermove", move); window.addEventListener("pointerup", up);
    return () => { window.removeEventListener("pointermove", move); window.removeEventListener("pointerup", up); };
  }, [view, commit]); // eslint-disable-line react-hooks/exhaustive-deps

  const onBgDown = (e) => {
    if (e.button !== 0 || e.target.closest("[data-node]")) return;
    setSel(null);
    drag.current = { kind: "pan", sx: e.clientX, sy: e.clientY, vx: view.x, vy: view.y };
  };
  const onNodeDown = (e, id) => {
    if (e.button !== 0 || e.target.closest("[data-port]")) return;
    e.stopPropagation(); setSel({ node: id });
    if (!can) return;
    const n = draft.nodes[id];
    drag.current = { kind: "node", id, sx: e.clientX, sy: e.clientY, nx: n.x, ny: n.y, moved: false };
  };
  const onPort = (e, id, k) => {
    if (!can) return;
    e.stopPropagation(); e.preventDefault();
    const p = toCanvas(e.clientX, e.clientY);
    drag.current = { kind: "link", id, k }; setLink({ from: id, k, x: p.x, y: p.y });
  };

  const add = (type, at) => {
    if (Object.keys(draft.nodes).length >= (P.limits?.nodes || 200)) { flash(false, bi("وصلت للحد الأقصى من البطاقات", "Card limit reached")); return; }
    const el = box.current.getBoundingClientRect();
    const p = at || toCanvas(el.left + el.width / 2 - (W / 2) * zoomOf() * view.k, el.top + el.height / 3);
    const id = newId();
    const n = { type, x: Math.round(p.x), y: Math.round(p.y), ...JSON.parse(JSON.stringify(DEFAULTS[type])) };
    if (!BRANCHING.includes(type)) n.next = null;
    // البطاقة المحدّدة بلا «التالي» تتصل بالجديدة تلقائياً — بناء الفلو بالنقر المتتالي
    const nodes = { ...draft.nodes, [id]: n };
    const s = sel && sel.node && nodes[sel.node];
    if (s && !BRANCHING.includes(s.type) && !s.next && !at) {
      nodes[sel.node] = { ...s, next: id };
      n.x = s.x; n.y = s.y + heightOf(s) + 40;
    }
    // لا تُسقَط البطاقة فوق أخرى: تنزل حتى أول مكان فارغ
    const hits = () => Object.entries(nodes).some(([k, o]) => k !== id && n.x < o.x + W && n.x + W > o.x && n.y < o.y + heightOf(o) && n.y + heightOf(n) > o.y);
    for (let i = 0; i < 40 && hits(); i++) n.y += 40;
    commit({ ...draft, start: draft.start && draft.nodes[draft.start] ? draft.start : id, nodes });
    setSel({ node: id }); setPaletteOpen(false);
  };
  const remove = (id) => {
    const nodes = {};
    for (const [k, n] of Object.entries(draft.nodes)) {
      if (k === id) continue;
      let m = n;
      outs(n).forEach((o) => { if (o.to === id) m = setOut(m, o.k, null); });
      nodes[k] = m;
    }
    commit({ ...draft, start: draft.start === id ? Object.keys(nodes)[0] || null : draft.start, nodes });
    setSel(null);
  };
  const dup = (id) => {
    const n = draft.nodes[id]; const nid = newId();
    let c = { ...JSON.parse(JSON.stringify(n)), x: n.x + 40, y: n.y + 40 };
    outs(c).forEach((o) => { c = setOut(c, o.k, null); });
    commit({ ...draft, nodes: { ...draft.nodes, [nid]: c } }); setSel({ node: nid });
  };
  const unlinkEdge = ([from, k]) => { commit({ ...draft, nodes: { ...draft.nodes, [from]: setOut(draft.nodes[from], k, null) } }); setSel(null); };

  const save = async (quiet) => {
    if (!can) return false;
    setBusy(true);
    const r = await call(`/api/bot/${botId}/flows/${fid}/save`, { draft, name, trigger: trig, timeout });
    setBusy(false);
    if (!r.ok) { flash(false, errText(r.error)); return false; }
    setDirty(false); onChanged({ id: fid, name, trigger: trig, dirty: r.dirty });
    if (!quiet) flash(true, bi("حُفظت المسودة", "Draft saved"));
    return true;
  };
  const showErr = (r) => {
    const c = r.error || "";
    if (c.startsWith("node:")) {
      const nid = c.split(":")[1];
      setErrs({ [nid]: errText(c) }); setSel({ node: nid });
      const n = draft.nodes[nid];
      if (n && box.current) { const z = zoomOf(), b = box.current.getBoundingClientRect(); setView((v) => ({ ...v, x: b.width / z / 2 - (n.x + W / 2) * v.k, y: b.height / z / 3 - n.y * v.k })); }
    }
    flash(false, errText(c, r.other));
  };
  const tryIt = async () => {
    if (!(await save(true))) return;
    setBusy(true);
    const r = await call(`/api/bot/${botId}/flows/${fid}/test`);
    setBusy(false);
    if (!r.ok) { showErr(r); return; }
    setErrs({}); setTest(r);
  };
  const publish = async () => {
    if (!(await save(true))) return;
    setBusy(true);
    const r = await call(`/api/bot/${botId}/flows/${fid}/publish`);
    setBusy(false);
    if (!r.ok) { showErr(r); return; }
    setErrs({}); onChanged(r.flow);
    const g = await get(`/api/bot/${botId}/flows/${fid}`);
    if (g.ok) { setDraft(g.flow.draft); setFlow(g.flow); }
    flash(true, r.flow.active ? bi("نُشر — يعمل الآن مع العملاء", "Published — live for customers now") : bi("نُشر. فعّله من القائمة ليبدأ العمل", "Published. Turn it on from the list to go live"));
  };

  // اختصارات: Delete · Ctrl+S · Ctrl+Z
  useEffect(() => {
    const k = (e) => {
      const typing = /^(INPUT|TEXTAREA|SELECT)$/.test(e.target.tagName) || e.target.isContentEditable;
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "s") { e.preventDefault(); save(); return; }
      if (typing || !can) return;
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "z") { e.preventDefault(); undo(); return; }
      if ((e.key === "Delete" || e.key === "Backspace") && sel) {
        e.preventDefault();
        if (sel.node) remove(sel.node); else if (sel.edge) unlinkEdge(sel.edge);
      }
    };
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  });
  useEffect(() => {
    if (!dirty) return undefined;
    const b = (e) => { e.preventDefault(); e.returnValue = ""; };
    window.addEventListener("beforeunload", b);
    return () => window.removeEventListener("beforeunload", b);
  }, [dirty]);

  const vars = useMemo(() => {
    const s = new Set(["contact.name", "contact.email", "contact.phone", ...(P.fields || []).map((f) => "contact." + f.key)]);
    Object.values(draft?.nodes || {}).forEach((n) => { if (n.var && n.type !== "condition") s.add(n.var); });
    return [...s];
  }, [draft]);
  const nodeStats = useMemo(() => {
    if (!heat || !stats) return null;
    const drops = stats.drops || {};
    const maxDrop = Math.max(0, ...Object.values(drops));
    const o = {};
    Object.keys(draft?.nodes || {}).forEach((id) => { o[id] = { visits: (stats.visits || {})[id] || 0, drop: drops[id] || 0, maxDrop }; });
    return o;
  }, [heat, stats, draft]);

  const close = () => { if (dirty && !window.confirm(bi("تغييرات غير محفوظة — الخروج بدون حفظ؟", "Unsaved changes — leave without saving?"))) return; onClose(); };

  if (!draft) {
    return (
      <div className="fixed inset-0 z-[355] grid place-items-center bg-[rgb(var(--sink-rgb))]">
        <div className="text-center text-ink-3">{msg ? <><p>{msg.text}</p><Btn variant="ghost" onClick={onClose}>{bi("رجوع", "Back")}</Btn></> : bi("جارٍ التحميل…", "Loading…")}</div>
      </div>
    );
  }
  const nodes = draft.nodes;
  const edges = [];
  Object.entries(nodes).forEach(([id, n]) => outs(n).forEach((o, i) => { if (o.to && nodes[o.to]) edges.push({ from: id, k: o.k, a: portPos(n, i), b: inPos(nodes[o.to]) }); }));
  const selNode = sel && sel.node && nodes[sel.node];
  const linkFrom = link && nodes[link.from];
  const published = !!(flow && flow.published);

  const palette = (
    <div className="grid gap-4">
      {GROUPS.map(([g, gl]) => (
        <div key={g}>
          <div className="mb-1.5 px-1 text-[10.5px] font-extrabold uppercase tracking-wider text-ink-3">{bi(...gl)}</div>
          <div className="grid gap-1">
            {Object.entries(TYPES).filter(([, m]) => m.g === g).map(([k, m]) => (
              <button key={k} type="button" draggable onClick={() => add(k)}
                      onDragStart={(e) => e.dataTransfer.setData("text/by-node", k)}
                      className="flex cursor-grab items-center gap-2 rounded-xl border-0 bg-transparent px-2 py-1.5 text-start text-[12.5px] font-bold text-ink-2 hover:bg-ov/[0.06] active:cursor-grabbing">
                <span className="grid size-6 shrink-0 place-items-center rounded-lg" style={{ background: m.c + "26", color: m.c }}><Icon name={m.icon} size={13} /></span>
                {bi(...m.l)}
              </button>
            ))}
          </div>
        </div>
      ))}
    </div>
  );

  return (
    <div className="fixed inset-0 z-[355] flex flex-col bg-[rgb(var(--sink-rgb))]">
      {/* الشريط العلوي */}
      <div className="flex flex-wrap items-center gap-2 border-b border-ov/10 bg-[rgb(var(--menu-rgb))] px-3 py-2">
        <Btn sm variant="ghost" onClick={close} aria-label={bi("رجوع", "Back")}><Icon name="back" size={15} /></Btn>
        <Input className="!w-[200px] !py-1.5" dir="auto" value={name} disabled={!can} onChange={(e) => { setName(e.target.value); setDirty(true); }} />
        <button type="button" onClick={() => setTrigOpen(true)} className="flex cursor-pointer items-center gap-1.5 rounded-xl border-0 bg-ov/[0.06] px-3 py-1.5 text-[12.5px] font-bold text-ink-2 hover:bg-ov/10">
          <Icon name="bolt" size={13} className="text-au-cyan" />{trigLabel(trig)}
        </button>
        {published ? (dirty || JSON.stringify(draft) !== JSON.stringify(flow.published)
          ? <Pill tone="warn">{bi("تغييرات غير منشورة", "Unpublished changes")}</Pill>
          : <Pill tone={flow.active ? "on" : "mute"} dot={flow.active}>{flow.active ? bi("يعمل", "Live") : bi("منشور · متوقّف", "Published · off")}</Pill>)
          : <Pill tone="mute">{bi("مسودة", "Draft")}</Pill>}
        <div className="ms-auto flex flex-wrap items-center gap-2">
          {msg && <span className={`text-[12.5px] font-bold ${msg.ok ? "text-au-teal" : "text-red-400"}`}>{msg.text}</span>}
          <Btn sm variant={heat ? "primary" : "ghost"} icon="chart" onClick={() => setHeat(!heat)}>{bi("خريطة التسرّب", "Drop-off map")}</Btn>
          {can && <>
            <Btn sm variant="ghost" icon="return" disabled={!hist.current.length} onClick={undo}>{bi("تراجع", "Undo")}</Btn>
            <Btn sm variant="ghost" disabled={busy || !dirty} onClick={() => save()}>{bi("حفظ", "Save")}</Btn>
            <Btn sm variant="ghost" icon="phone" disabled={busy} onClick={tryIt}>{P.channel === "whatsapp" ? bi("جرّب على واتساب", "Test on WhatsApp") : bi("جرّب", "Test")}</Btn>
            <Btn sm variant="green" icon="rocket" disabled={busy} onClick={publish}>{bi("نشر", "Publish")}</Btn>
          </>}
        </div>
      </div>

      <div className="relative flex min-h-0 flex-1">
        {can && <aside className="hidden w-[196px] shrink-0 overflow-y-auto border-e border-ov/10 bg-[rgb(var(--menu-rgb))] p-3 md:block">{palette}</aside>}

        {/* الكانفس — LTR دائماً لتبقى الإحداثيات ثابتة؛ النصوص داخل البطاقات dir=auto */}
        <div ref={box} dir="ltr" onPointerDown={onBgDown}
             onDragOver={(e) => e.preventDefault()}
             onDrop={(e) => { const k = e.dataTransfer.getData("text/by-node"); if (k && TYPES[k] && can) { e.preventDefault(); add(k, toCanvas(e.clientX - W / 2, e.clientY - 20)); } }}
             className="relative min-w-0 flex-1 cursor-grab overflow-hidden active:cursor-grabbing"
             style={{ backgroundImage: "radial-gradient(rgb(var(--ov-rgb)/0.13) 1px, transparent 1px)",
                      backgroundSize: `${22 * view.k}px ${22 * view.k}px`, backgroundPosition: `${view.x}px ${view.y}px`, touchAction: "none" }}>
          <div className="absolute left-0 top-0 origin-top-left" style={{ transform: `translate(${view.x}px,${view.y}px) scale(${view.k})` }}>
            <svg className="pointer-events-none absolute left-0 top-0 overflow-visible" width="1" height="1">
              {edges.map((ed) => {
                const on = sel && sel.edge && sel.edge[0] === ed.from && sel.edge[1] === ed.k;
                return (
                  <g key={ed.from + ed.k}>
                    <path d={curve(ed.a, ed.b)} fill="none" stroke="transparent" strokeWidth="14" className="pointer-events-auto cursor-pointer"
                          onPointerDown={(e) => { e.stopPropagation(); setSel({ edge: [ed.from, ed.k] }); }} />
                    <path d={curve(ed.a, ed.b)} fill="none" stroke={on ? "#7c6cf6" : "rgb(var(--ov-rgb)/0.35)"} strokeWidth={on ? 2.5 : 2} />
                    <circle cx={ed.b.x} cy={ed.b.y} r="3.5" fill={on ? "#7c6cf6" : "rgb(var(--ov-rgb)/0.5)"} />
                  </g>
                );
              })}
              {linkFrom && (() => { const i = outs(linkFrom).findIndex((o) => o.k === link.k); return <path d={curve(portPos(linkFrom, i), { x: link.x, y: link.y })} fill="none" stroke="#2dd4a7" strokeWidth="2" strokeDasharray="6 4" />; })()}
            </svg>
            {Object.entries(nodes).map(([id, n]) => (
              <NodeCard key={id} id={id} n={n} isStart={draft.start === id} selected={sel && sel.node === id} error={errs[id]}
                        others={others} stat={nodeStats && nodeStats[id]} onDown={onNodeDown} onPort={onPort} linking={!!link} />
            ))}
            {sel && sel.edge && can && (() => {
              const ed = edges.find((x) => x.from === sel.edge[0] && x.k === sel.edge[1]); if (!ed) return null;
              return <button type="button" onPointerDown={(e) => e.stopPropagation()} onClick={() => unlinkEdge(sel.edge)}
                             className="absolute grid size-6 cursor-pointer place-items-center rounded-full border-0 bg-red-400 text-[#2A0A0A]"
                             style={{ left: (ed.a.x + ed.b.x) / 2 - 12, top: (ed.a.y + ed.b.y) / 2 - 12 }} aria-label={bi("حذف التوصيلة", "Remove connection")}><Icon name="close" size={12} /></button>;
            })()}
          </div>

          {/* أدوات العرض */}
          <div className="absolute bottom-3 left-3 flex gap-1.5" onPointerDown={(e) => e.stopPropagation()}>
            {[["plus", () => setView((v) => ({ ...v, k: Math.min(1.8, v.k * 1.2) }))], ["close", null], ["grid", () => fit()]].map(([ic, fn], i) => (
              i === 1 ? <button key={i} type="button" onClick={() => setView((v) => ({ ...v, k: Math.max(0.3, v.k / 1.2) }))}
                                className="grid size-8 cursor-pointer place-items-center rounded-lg border-0 bg-[rgb(var(--menu-rgb))] text-[18px] font-bold text-ink shadow-[inset_0_0_0_1px_rgb(var(--ov-rgb)/0.12)]">−</button>
                     : <button key={i} type="button" onClick={fn} className="grid size-8 cursor-pointer place-items-center rounded-lg border-0 bg-[rgb(var(--menu-rgb))] text-ink shadow-[inset_0_0_0_1px_rgb(var(--ov-rgb)/0.12)]"><Icon name={ic} size={15} /></button>
            ))}
            <span className="tnum grid h-8 place-items-center rounded-lg bg-[rgb(var(--menu-rgb))] px-2 text-[11.5px] font-bold text-ink-3">{Math.round(view.k * 100)}%</span>
          </div>
          {can && <button type="button" onPointerDown={(e) => e.stopPropagation()} onClick={() => setPaletteOpen(!paletteOpen)}
                          className="absolute bottom-3 right-3 grid size-12 cursor-pointer place-items-center rounded-full border-0 bg-[linear-gradient(100deg,#8FE9FF,#B9AFFF)] text-[#07090F] shadow-lg md:hidden"
                          aria-label={bi("إضافة بطاقة", "Add card")}><Icon name="plus" size={20} /></button>}
          {paletteOpen && <div onPointerDown={(e) => e.stopPropagation()} className="absolute bottom-16 right-3 max-h-[60%] w-[220px] overflow-y-auto rounded-2xl bg-[rgb(var(--menu-rgb))] p-3 shadow-2xl md:hidden">{palette}</div>}

          {heat && stats && (
            <div className="absolute left-3 top-3 flex flex-wrap gap-2 rounded-2xl bg-[rgb(var(--menu-rgb))] p-3 text-[12px] shadow-lg" dir={AR ? "rtl" : "ltr"} onPointerDown={(e) => e.stopPropagation()}>
              {[["sessions", bi("جلسات", "Sessions")], ["completed", bi("اكتملت", "Completed")], ["handoff", bi("تحويل لموظف", "Handed off")], ["dropped", bi("تسرّبت", "Dropped")], ["active", bi("جارية", "In progress")]].map(([k, l]) => (
                <div key={k} className="rounded-xl bg-ov/[0.05] px-3 py-1.5">
                  <div className="text-[10.5px] font-extrabold uppercase text-ink-3">{l}</div>
                  <b className="tnum text-[15px] text-ink">{num(stats[k])}</b>
                  {k !== "sessions" && <span className="tnum ms-1 text-[11px] text-ink-3">{pct(stats[k], stats.sessions)}%</span>}
                </div>
              ))}
            </div>
          )}
          {!Object.keys(nodes).length && (
            <div className="pointer-events-none absolute inset-0 grid place-items-center text-[14px] text-ink-3">{bi("اسحب بطاقة من اليسار لتبدأ", "Drag a card from the palette to start")}</div>
          )}
        </div>

        {selNode && (
          <aside className="absolute inset-x-0 bottom-0 z-10 max-h-[60%] overflow-hidden rounded-t-2xl bg-[rgb(var(--menu-rgb))] shadow-2xl md:static md:max-h-none md:w-[340px] md:shrink-0 md:rounded-none md:border-s md:border-ov/10 md:shadow-none">
            {can ? (
              <Props id={sel.node} node={selNode} isStart={draft.start === sel.node} others={others} vars={vars} tpls={tpls} error={errs[sel.node]}
                     onChange={(n) => { commit({ ...draft, nodes: { ...nodes, [sel.node]: n } }, true); if (errs[sel.node]) setErrs({}); }}
                     onStart={(id) => commit({ ...draft, start: id })} onDelete={remove} onDup={dup} onClose={() => setSel(null)} />
            ) : (
              <div className="p-4 text-[13px] text-ink-2" dir="auto"><b className="mb-2 block text-ink">{bi(...TYPES[selNode.type].l)}</b>{summary(selNode, others)}</div>
            )}
          </aside>
        )}
      </div>

      <Modal open={trigOpen} onClose={() => setTrigOpen(false)} title={bi("إعدادات الفلو", "Flow settings")} icon="settings"
             footer={<Btn onClick={() => setTrigOpen(false)}>{bi("تم", "Done")}</Btn>}>
        <TriggerFields value={trig} onChange={(v) => { if (!can) return; setTrig(v); setDirty(true); }} />
        <p className="mb-0 mt-3 text-[12.5px] leading-relaxed text-ink-3">{bi("الكلمات المفتاحية لها الأولوية، ثم «البداية»، ثم «أي رسالة». فلو نشط واحد فقط لكل من «أي رسالة» و«البداية».", "Keywords win first, then Start, then Any message. Only one active flow each for Any message and Start.")}</p>
        <div className="mt-5 border-t border-ov/10 pt-4">
          <b className="mb-1 block text-[14px] text-ink">{bi("مهلة الرد", "Reply timeout")}</b>
          <p className="mb-3 mt-0 text-[12.5px] leading-relaxed text-ink-3">{bi("حين ينتظر الفلو إجابة ولا يرد العميل: تذكير مرة واحدة، ثم إغلاق الجلسة (تُحسب «متسرّبة» عند آخر بطاقة). 0 = معطّل.", "When the flow waits and the customer goes quiet: one reminder, then the session closes (counted as dropped at the last card). 0 = off.")}</p>
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label={bi("التذكير بعد (دقائق)", "Remind after (minutes)")} hint={bi("حتى 1380 (23 ساعة — نافذة واتساب)", "Up to 1380 (23h — WhatsApp window)")}>
              <Input type="number" min={0} max={1380} disabled={!can} value={timeout.remind || 0} onChange={(e) => { setTimeoutCfg({ ...timeout, remind: Number(e.target.value) || 0 }); setDirty(true); }} />
            </Field>
            <Field label={bi("الإغلاق بعد (دقائق)", "Close after (minutes)")} hint={bi("أكبر من مدة التذكير", "Longer than the reminder")}>
              <Input type="number" min={0} max={10080} disabled={!can} value={timeout.end || 0} onChange={(e) => { setTimeoutCfg({ ...timeout, end: Number(e.target.value) || 0 }); setDirty(true); }} />
            </Field>
          </div>
          {!!timeout.remind && <Field className="mt-3" label={bi("نص التذكير", "Reminder text")}>
            <Input dir="auto" disabled={!can} value={timeout.remind_text || ""} placeholder={bi("ما زلنا بانتظار ردك 😊", "Still here when you're ready 😊")} onChange={(e) => { setTimeoutCfg({ ...timeout, remind_text: e.target.value }); setDirty(true); }} />
          </Field>}
          {!!timeout.end && <Field className="mt-3" label={bi("رسالة الإغلاق (اختياري)", "Closing message (optional)")}>
            <Input dir="auto" disabled={!can} value={timeout.end_text || ""} onChange={(e) => { setTimeoutCfg({ ...timeout, end_text: e.target.value }); setDirty(true); }} />
          </Field>}
        </div>
      </Modal>

      <Modal open={!!test} onClose={() => setTest(null)} title={bi("جرّب الفلو", "Test the flow")} icon="phone"
             footer={<Btn onClick={() => setTest(null)}>{bi("تم", "Done")}</Btn>}>
        {test && <div className="grid gap-3 text-[13.5px] leading-relaxed text-ink-2">
          <p className="m-0">{bi(`المسودة الحالية تعمل لمن يرسل هذا الرمز فقط، لمدة ${test.minutes} دقيقة — لا تؤثّر على العملاء ولا تُحتسب في الإحصاءات.`,
                                 `The current draft runs only for whoever sends this code, for ${test.minutes} minutes — customers aren't affected and stats aren't counted.`)}</p>
          <div className="flex items-center justify-between gap-2 rounded-xl bg-ov/[0.05] px-3 py-2.5">
            <b dir="ltr" className="font-mono text-[15px] text-ink">{test.code}</b>
            <Btn sm variant="ghost" icon="copy" onClick={() => { try { navigator.clipboard.writeText(test.code); } catch { /* */ } }}>{bi("نسخ", "Copy")}</Btn>
          </div>
          {test.link ? <Btn icon="phone" href={test.link} target="_blank" rel="noopener">{bi("افتح المحادثة على هاتفك", "Open the chat on your phone")}</Btn>
                     : <p className="m-0 text-ink-3">{bi("أرسل الرمز للبوت من هاتفك.", "Send the code to the bot from your phone.")}</p>}
          {!test.running && <div className="rounded-xl bg-yellow-400/10 px-3 py-2 text-[12.5px] font-bold text-yellow-300">{bi("البوت متوقّف — شغّله من صفحته أولاً ليرد.", "The bot is stopped — start it from its page so it replies.")}</div>}
        </div>}
      </Modal>
    </div>
  );
}

/* ------------------------------------------------------------ القائمة */
function NewFlow({ open, onClose, onDone }) {
  const [name, setName] = useState("");
  const [trig, setTrig] = useState({ type: "keywords", keywords: [], match: "contains" });
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => { if (open) { setName(""); setErr(""); setTrig({ type: (P.flows || []).length ? "keywords" : "any", keywords: [], match: "contains" }); } }, [open]);
  const go = async () => {
    setBusy(true);
    const r = await call(`/api/bot/${P.bot.id}/flows`, { name, trigger: trig });
    setBusy(false);
    if (!r.ok) { setErr(errText(r.error)); return; }
    onDone(r.flow);
  };
  return (
    <Modal open={open} onClose={onClose} title={bi("فلو جديد", "New flow")} icon="flow"
           footer={<><Btn variant="ghost" onClick={onClose}>{bi("إلغاء", "Cancel")}</Btn><Btn disabled={busy || !name.trim()} onClick={go}>{bi("إنشاء وفتح المحرّر", "Create & open editor")}</Btn></>}>
      <div className="grid gap-3">
        <Field label={bi("اسم الفلو", "Flow name")}><Input dir="auto" autoFocus maxLength={80} value={name} placeholder={bi("مثل: حجز غرفة", "e.g. Room booking")} onChange={(e) => setName(e.target.value)} /></Field>
        <TriggerFields value={trig} onChange={setTrig} />
        {err && <div className="text-[13px] font-bold text-red-400">{err}</div>}
      </div>
    </Modal>
  );
}

export default function Flows() {
  const bot = P.bot || {};
  const [flows, setFlows] = useState(P.flows || []);
  const [open, setOpen] = useState(() => new URLSearchParams(location.search).get("f"));
  const [creating, setCreating] = useState(false);
  const [msg, setMsg] = useState("");
  const patch = (f) => setFlows((xs) => xs.map((x) => (x.id === f.id ? { ...x, ...f } : x)));
  const edit = (id) => { setOpen(id); try { history.replaceState(null, "", `?f=${id}`); } catch { /* */ } };
  const closeEd = () => { setOpen(null); try { history.replaceState(null, "", location.pathname); } catch { /* */ } };
  const toggle = async (f, on) => {
    setMsg("");
    const r = await call(`/api/bot/${bot.id}/flows/${f.id}/toggle`, { active: on });
    if (r.ok) patch(r.flow); else setMsg(errText(r.error, r.other));
  };
  const del = async (f) => {
    if (!window.confirm(bi(`حذف «${f.name}» وإحصاءاته نهائياً؟`, `Delete “${f.name}” and its stats permanently?`))) return;
    const r = await call(`/api/bot/${bot.id}/flows/${f.id}/delete`);
    if (r.ok) setFlows((xs) => xs.filter((x) => x.id !== f.id)); else setMsg(errText(r.error));
  };
  return (
    <>
      <PageHead icon="flow" title={bi("باني الفلو", "Flow builder")}
                sub={bi(`فلوهات «${bot.name}» المرئية: ابنِ المحادثة بالسحب والتوصيل، وتابع أين يتوقّف العملاء.`,
                        `Visual flows for “${bot.name}”: build conversations by drag-and-connect, and see where customers drop off.`)}
                actions={<>
                  <Btn variant="ghost" sm icon="back" href={`/bot/${bot.id}`}>{bi("البوت", "Bot")}</Btn>
                  {P.canManage && <Btn icon="plus" onClick={() => setCreating(true)}>{bi("فلو جديد", "New flow")}</Btn>}
                </>} />
      {msg && <Card className="mb-4 !py-3 text-[13.5px] font-bold text-red-400">{msg}</Card>}
      <Card>
        {!flows.length ? (
          <Empty icon="flow" title={bi("لا فلوهات بعد", "No flows yet")}
                 text={bi("الفلو المرئي يحلّ محل الفلو البسيط لهذا البوت بمجرد نشره وتفعيله. المحادثات الجارية تكمل على ما بدأت عليه.",
                          "Once published and on, visual flows take over from the simple flow. Conversations in progress finish where they started.")}
                 action={P.canManage && <Btn icon="plus" onClick={() => setCreating(true)}>{bi("أنشئ أول فلو", "Create your first flow")}</Btn>} />
        ) : (
          <div className="-mx-2 overflow-x-auto px-2">
            <table className="w-full border-collapse text-[13px]">
              <thead><tr>{[bi("الفلو", "Flow"), bi("المشغّل", "Trigger"), bi("جلسات", "Sessions"), bi("اكتملت", "Completed"), bi("تسرّبت", "Dropped"), bi("تحويل", "Handoff"), bi("مفعّل", "On"), ""].map((h, i) => (
                <th key={i} className="whitespace-nowrap px-3 py-3 text-start text-[11px] font-extrabold uppercase tracking-wider text-ink-3 shadow-[inset_0_-1px_0_rgb(var(--ov-rgb)/0.08)]">{h}</th>))}</tr></thead>
              <tbody>
                {flows.map((f) => {
                  const s = f.stats || {};
                  return (
                    <tr key={f.id} className="cursor-pointer hover:bg-ov/[0.035]" onClick={() => edit(f.id)}>
                      <td className="px-3 py-3 shadow-[inset_0_-1px_0_rgb(var(--ov-rgb)/0.05)]">
                        <b className="block max-w-[240px] truncate text-ink" dir="auto">{f.name}</b>
                        <span className="text-[11.5px] text-ink-3">
                          {!f.published_at ? bi("مسودة — لم يُنشر", "Draft — not published") : f.dirty ? bi("تغييرات غير منشورة", "Unpublished changes") : bi("منشور", "Published")}
                        </span>
                      </td>
                      <td className="px-3 py-3 text-ink-2 shadow-[inset_0_-1px_0_rgb(var(--ov-rgb)/0.05)]" dir="auto">{trigLabel(f.trigger)}</td>
                      <td className="tnum px-3 py-3 shadow-[inset_0_-1px_0_rgb(var(--ov-rgb)/0.05)]">{num(s.sessions)}</td>
                      <td className="tnum px-3 py-3 shadow-[inset_0_-1px_0_rgb(var(--ov-rgb)/0.05)]">{num(s.completed)} <span className="text-ink-3">{pct(s.completed, s.sessions)}%</span></td>
                      <td className="tnum px-3 py-3 shadow-[inset_0_-1px_0_rgb(var(--ov-rgb)/0.05)]">{num(s.dropped)} <span className="text-ink-3">{pct(s.dropped, s.sessions)}%</span></td>
                      <td className="tnum px-3 py-3 shadow-[inset_0_-1px_0_rgb(var(--ov-rgb)/0.05)]">{num(s.handoff)}</td>
                      <td className="px-3 py-3 shadow-[inset_0_-1px_0_rgb(var(--ov-rgb)/0.05)]" onClick={(e) => e.stopPropagation()}>
                        <Toggle checked={f.active} disabled={!P.canManage || !f.published_at} onChange={(v) => toggle(f, v)} label={bi("تفعيل", "Active")} />
                      </td>
                      <td className="px-3 py-3 text-end shadow-[inset_0_-1px_0_rgb(var(--ov-rgb)/0.05)]" onClick={(e) => e.stopPropagation()}>
                        <span className="inline-flex gap-1.5">
                          <Btn sm variant="ghost" icon="edit" onClick={() => edit(f.id)}>{P.canManage ? bi("تحرير", "Edit") : bi("عرض", "View")}</Btn>
                          {P.canManage && <Btn sm variant="ghost" onClick={() => del(f)} aria-label={bi("حذف", "Delete")}><Icon name="trash" size={14} /></Btn>}
                        </span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Card>
      <NewFlow open={creating} onClose={() => setCreating(false)} onDone={(f) => { setFlows((xs) => [...xs, f]); setCreating(false); edit(f.id); }} />
      {open && <Editor key={open} botId={bot.id} fid={open} onClose={closeEd} onChanged={patch} />}
    </>
  );
}
