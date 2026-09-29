/* الدفع داخل المحادثة — المرحلة 9: بوابة صاحب الحساب (Moyasar/Tap) · سجل الروابط وحالاتها · مجاميع 30 يوماً.
   المفتاح السرّي يُكتب ولا يُقرأ أبداً (مختوم في الخادم)؛ المال يذهب مباشرة لحساب النشاط في البوابة. */
import { useState } from "react";
import { BY, P, bi, AR, Icon, Card, Btn, Field, Input, Select, Pill, Empty, PageHead, num, Modal } from "../kit.jsx";

async function call(url, body, method = "POST") {
  try {
    const r = await fetch(url, method === "GET" ? { headers: { Accept: "application/json" } } : {
      method, headers: { "Content-Type": "application/json", "X-CSRF-Token": BY.csrf }, body: JSON.stringify(body || {}),
    });
    const j = await r.json().catch(() => ({ ok: false, error: "network" }));
    return { status: r.status, ...j };
  } catch { return { ok: false, error: "network" }; }
}
export const PAY_ERR = {
  provider: bi("اختر البوابة", "Pick a gateway"), currency: bi("عملة غير مدعومة", "Unsupported currency"),
  secret: bi("المفتاح غير صالح (Moyasar/Tap: sk_test_ أو sk_live_ · HyperPay: Access Token)", "Invalid key (Moyasar/Tap: sk_test_ or sk_live_ · HyperPay: Access Token)"),
  entity: bi("Entity ID من HyperPay: 32 حرفاً (0-9 a-f)", "HyperPay Entity ID: 32 characters (0-9 a-f)"),
  not_configured: bi("اربط بوابة الدفع أولاً من صفحة المدفوعات", "Connect a payment gateway first on the Payments page"),
  amount: bi("مبلغ غير صالح", "Invalid amount"), window: bi("انتهت نافذة الـ24 ساعة — أرسل قالباً أولاً", "The 24-hour window is closed — send a template first"),
  rate: bi("طلبات كثيرة، انتظر قليلاً", "Too many requests, wait a bit"), readonly: bi("صلاحيتك قراءة فقط", "You have read-only access"),
  role: bi("للمالك والمدير فقط", "Owners and admins only"), network: bi("تعذّر الاتصال", "Connection failed"),
  send: bi("تعذّر إيصال الرسالة للعميل — تحقّق من ربط القناة", "The message could not be delivered — check the channel connection"),
  no_base: bi("عنوان الموقع العام (PUBLIC_URL) غير مضبوط في الخادم", "The server's public address (PUBLIC_URL) is not set"),
  gateway_auth: bi("البوابة رفضت المفتاح — تأكّد منه", "The gateway rejected the key — check it"),
  gateway_rejected: bi("البوابة رفضت الطلب", "The gateway rejected the request"),
  gateway_network: bi("تعذّر الوصول للبوابة", "Could not reach the gateway"),
  gateway_bad_response: bi("ردّ غير متوقّع من البوابة", "Unexpected gateway response"),
};
export const payErr = (r) => PAY_ERR[r.error] || bi("حدث خطأ", "Something went wrong");

const MINOR = { KWD: 1000, BHD: 1000, OMR: 1000 };
export const money = (amount, cur) => {
  const f = MINOR[cur] || 100;
  return `${(amount / f).toLocaleString(AR ? "ar-EG" : "en-US", { maximumFractionDigits: f === 1000 ? 3 : 2 })} ${cur}`;
};
const when = (ts) => (ts ? new Date(ts * 1000).toLocaleString(AR ? "ar-EG" : "en-GB", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" }) : "—");
const copy = (s) => { try { navigator.clipboard.writeText(s); } catch { /* */ } };
const GW_NAME = { moyasar: "Moyasar", tap: "Tap Payments", hyperpay: "HyperPay" };
const ST = {
  pending: [bi("بانتظار الدفع", "Awaiting payment"), "warn"], paid: [bi("مدفوعة", "Paid"), "on"],
  failed: [bi("فشلت", "Failed"), "off"], expired: [bi("انتهت", "Expired"), "mute"], cancelled: [bi("أُلغيت", "Cancelled"), "mute"],
};

function Stat({ label, value, sub }) {
  return (
    <div className="rounded-2xl bg-ov/[0.04] px-4 py-3 shadow-[inset_0_0_0_1px_rgb(var(--ov-rgb)/0.06)]">
      <div className="text-[11px] font-extrabold uppercase tracking-wider text-ink-3">{label}</div>
      <div className="tnum mt-1 text-[22px] font-extrabold text-ink">{value}</div>
      {sub && <div className="tnum text-[11.5px] text-ink-3">{sub}</div>}
    </div>
  );
}

function Gateway({ cfg, setCfg }) {
  const [edit, setEdit] = useState(null);
  const [err, setErr] = useState("");
  const [test, setTest] = useState(null);
  const [copied, setCopied] = useState("");
  const connected = cfg.provider && cfg.hasSecret;
  const save = async () => {
    setErr("");
    const r = await call("/api/pay/settings", edit);
    if (!r.ok) { setErr(payErr(r)); return; }
    setCfg(r.config); setEdit(null); setTest(null);
  };
  const clear = async () => {
    if (!window.confirm(bi("فصل البوابة؟ الفلوهات التي فيها بطاقة دفع تذهب لفرع «لم يُدفع».", "Disconnect the gateway? Flows with a payment card will take the “Not paid” branch."))) return;
    const r = await call("/api/pay/settings", { clear: true }); if (r.ok) { setCfg(r.config); setTest(null); }
  };
  const runTest = async () => { setTest("…"); const r = await call("/api/pay/test"); setTest(r.ok ? "ok" : payErr(r)); };
  const hook = (P.webhooks || {})[edit?.provider || cfg.provider];
  return <>
    <Card className="mb-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex min-w-0 items-center gap-3">
          <span className="grid size-11 shrink-0 place-items-center rounded-2xl bg-au-violet/15 text-au-violet"><Icon name="card" size={20} /></span>
          <div className="min-w-0">
            <b className="block text-[15px] text-ink">{bi("بوابة الدفع", "Payment gateway")}</b>
            <span className="text-[12.5px] text-ink-3">{connected
              ? <>{GW_NAME[cfg.provider]} · {cfg.currency}</>
              : bi("اربط حسابك في Moyasar أو Tap — المال يصل لحسابك مباشرة، ونحن لا نلمسه.", "Connect your Moyasar or Tap account — money goes straight to you; we never touch it.")}</span>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {connected ? <Pill tone="on" dot>{bi("متصلة", "Connected")}</Pill> : <Pill tone="mute">{bi("غير متصلة", "Not connected")}</Pill>}
          {connected && P.canManage && <Btn sm variant="ghost" icon="check" onClick={runTest}>{bi("فحص المفتاح", "Test key")}</Btn>}
          {P.canManage && <Btn sm icon="settings" onClick={() => { setErr(""); setEdit({ provider: cfg.provider || "moyasar", currency: cfg.currency || "SAR", secret: "", webhook_secret: "", entity: cfg.entity || "", entity_mada: cfg.entity_mada || "", test: cfg.provider ? !!cfg.test : true }); }}>
            {connected ? bi("تعديل", "Edit") : bi("ربط البوابة", "Connect gateway")}</Btn>}
          {connected && P.canManage && <Btn sm variant="ghost" onClick={clear} aria-label={bi("فصل", "Disconnect")}><Icon name="trash" size={14} /></Btn>}
        </div>
      </div>
      {test && <div className={`mt-3 rounded-xl px-3 py-2 text-[13px] font-bold ${test === "ok" ? "bg-emerald-400/10 text-emerald-400" : test === "…" ? "bg-ov/[0.04] text-ink-3" : "bg-red-400/10 text-red-400"}`}>
        {test === "ok" ? bi("✓ المفتاح صالح — البوابة جاهزة", "✓ Key is valid — the gateway is ready") : test === "…" ? bi("جارٍ الفحص…", "Testing…") : test}</div>}
      {connected && cfg.provider === "hyperpay" && (
        <p className="mb-0 mt-3 rounded-xl bg-ov/[0.035] px-3 py-2.5 text-[12px] text-ink-3">{cfg.test ? bi("🧪 وضع الاختبار (eu-test.oppwa.com) — بطاقات HyperPay التجريبية فقط.", "🧪 Test mode (eu-test.oppwa.com) — HyperPay test cards only.")
          : bi("وضع الإنتاج — مدفوعات حقيقية.", "Live mode — real payments.")} {bi("لا يحتاج رابط إشعارات: نتأكّد عند عودة العميل أو كتابته «دفعت» أو كل دقيقتين.", "No webhook needed: we confirm when the customer returns, says “paid”, or every two minutes.")}</p>
      )}
      {connected && hook && cfg.provider !== "hyperpay" && (
        <div className="mt-3 rounded-xl bg-ov/[0.035] px-3 py-2.5">
          <div className="mb-1 text-[12px] font-bold text-ink-2">{bi("رابط الإشعارات (Webhook) — الصقه في لوحة البوابة", "Webhook URL — paste it in your gateway dashboard")}</div>
          <div className="flex items-center gap-2">
            <code dir="ltr" className="min-w-0 flex-1 truncate rounded-lg bg-sink/40 px-2.5 py-1.5 text-[11.5px] text-ink-2">{hook}</code>
            <Btn sm variant="ghost" icon="copy" onClick={() => { copy(hook); setCopied("hook"); setTimeout(() => setCopied(""), 1500); }}>{copied === "hook" ? bi("نُسخ ✓", "Copied ✓") : bi("نسخ", "Copy")}</Btn>
          </div>
          <p className="mb-0 mt-1.5 text-[11.5px] text-ink-3">{bi("اختياري لكنه أسرع: بدونه نتأكّد من الدفع عند عودة العميل أو كتابته «دفعت» أو كل دقيقتين.", "Optional but faster: without it we confirm when the customer returns, says “paid”, or every two minutes.")}</p>
        </div>
      )}
    </Card>
    <Modal open={!!edit} onClose={() => setEdit(null)} title={bi("ربط بوابة الدفع", "Connect payment gateway")} icon="card"
           footer={<><Btn variant="ghost" onClick={() => setEdit(null)}>{bi("إلغاء", "Cancel")}</Btn><Btn onClick={save}>{bi("حفظ", "Save")}</Btn></>}>
      {edit && <div className="grid gap-3">
        {err && <div className="rounded-xl bg-red-400/10 px-3 py-2 text-[13px] font-bold text-red-400">{err}</div>}
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label={bi("البوابة", "Gateway")}>
            <Select value={edit.provider} onChange={(e) => setEdit({ ...edit, provider: e.target.value,
              test: e.target.value === "hyperpay" && cfg.provider !== "hyperpay" ? true : edit.test })}>{(P.providers || []).map((p) => <option key={p} value={p}>{GW_NAME[p] || p}</option>)}</Select>
          </Field>
          <Field label={bi("العملة الافتراضية", "Default currency")}>
            <Select value={edit.currency} onChange={(e) => setEdit({ ...edit, currency: e.target.value })}>{(P.currencies || []).map((c) => <option key={c} value={c}>{c}</option>)}</Select>
          </Field>
        </div>
        <Field label={edit.provider === "hyperpay" ? "Access Token" : bi("المفتاح السرّي (Secret key)", "Secret key")}
               hint={cfg.hasSecret && edit.provider === cfg.provider ? bi("محفوظ ولا يُعرض — اتركه فارغاً للإبقاء عليه", "Saved and never shown — leave empty to keep it")
                 : edit.provider === "hyperpay" ? bi("من لوحة HyperPay (أو من فريقهم عند فتح الحساب): Access Token و Entity ID.", "From the HyperPay dashboard (or their team at onboarding): Access Token and Entity ID.")
                 : bi("من لوحة البوابة ← الإعدادات ← مفاتيح API. ابدأ بمفتاح sk_test_ للتجربة.", "From your gateway dashboard → Settings → API keys. Start with an sk_test_ key to try it.")}>
          <Input dir="ltr" type="password" autoComplete="off" placeholder={edit.provider === "hyperpay" ? "OGE4Mjk0…" : "sk_test_…"} value={edit.secret} onChange={(e) => setEdit({ ...edit, secret: e.target.value.trim() })} />
        </Field>
        {edit.provider === "hyperpay" && <>
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label={bi("Entity ID (البطاقات)", "Entity ID (cards)")}><Input dir="ltr" value={edit.entity} onChange={(e) => setEdit({ ...edit, entity: e.target.value.trim().toLowerCase() })} /></Field>
            <Field label={bi("Entity ID لمدى (إن كان منفصلاً)", "mada Entity ID (if separate)")}><Input dir="ltr" value={edit.entity_mada} onChange={(e) => setEdit({ ...edit, entity_mada: e.target.value.trim().toLowerCase() })} /></Field>
          </div>
          <label className="flex items-center gap-2 text-[13px] text-ink-2"><input type="checkbox" checked={!!edit.test} onChange={(e) => setEdit({ ...edit, test: e.target.checked })} />
            {bi("وضع الاختبار (eu-test.oppwa.com) — أزِله عند استلام مفاتيح الإنتاج", "Test mode (eu-test.oppwa.com) — untick when you get live keys")}</label>
        </>}
        {edit.provider === "moyasar" && (
          <Field label={bi("رمز سرّ الإشعارات (اختياري)", "Webhook secret token (optional)")} hint={bi("نفس القيمة التي تضعها في إعداد الـ Webhook في Moyasar.", "The same value you set on the webhook in Moyasar.")}>
            <Input dir="ltr" type="password" autoComplete="off" value={edit.webhook_secret} onChange={(e) => setEdit({ ...edit, webhook_secret: e.target.value.trim() })} />
          </Field>
        )}
        <p className="m-0 flex gap-2 rounded-xl bg-ov/[0.035] px-3 py-2 text-[12px] leading-relaxed text-ink-3"><Icon name="lock" size={14} className="mt-0.5" />
          {bi("يُحفظ المفتاح مشفّراً ولا يعود للمتصفح أبداً. كل مبلغ يذهب لحسابك في البوابة مباشرة — المنصة لا تأخذ عمولة ولا تمرّ بها الأموال.", "The key is stored encrypted and never returned to the browser. Every payment goes straight to your gateway account — no platform commission, the money never passes through us.")}</p>
      </div>}
    </Modal>
  </>;
}

export default function ChatPayments() {
  const [cfg, setCfg] = useState(P.config || {});
  const [items, setItems] = useState(P.items || []);
  const [totals, setTotals] = useState(P.totals || []);
  const [st, setSt] = useState("");
  const [copied, setCopied] = useState(null);
  const load = async (s) => {
    setSt(s);
    const r = await call(`/api/pay/list${s ? `?status=${s}` : ""}`, null, "GET");
    if (r.ok) { setItems(r.items); setTotals(r.totals); }
  };
  const paid = totals.filter((t) => t.status === "paid");
  const count = (s) => totals.filter((t) => t.status === s).reduce((a, t) => a + t.n, 0);
  const all = totals.reduce((a, t) => a + t.n, 0);
  const paidN = count("paid");
  return (
    <>
      <PageHead icon="card" title={bi("الدفع داخل المحادثة", "In-chat payments")}
                sub={bi("احجز وادفع دون مغادرة واتساب: رابط دفع بزر من الفلو أو من الصندوق المشترك، تأكيد تلقائي وإيصال للعميل.", "Book and pay without leaving WhatsApp: a pay button from a flow or the Team inbox, automatic confirmation and a receipt.")} />
      <Gateway cfg={cfg} setCfg={setCfg} />
      <div className="mb-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Stat label={bi("المحصّل (30 يوماً)", "Collected (30 days)")} value={paid.length ? money(paid[0].total, paid[0].currency) : "0"}
              sub={paid.slice(1).map((t) => money(t.total, t.currency)).join(" · ") || null} />
        <Stat label={bi("دفعات ناجحة", "Paid")} value={num(paidN)} />
        <Stat label={bi("بانتظار الدفع", "Awaiting")} value={num(count("pending"))} />
        <Stat label={bi("نسبة الإتمام", "Completion rate")} value={`${all ? Math.round((paidN / all) * 100) : 0}%`} sub={bi(`من ${num(all)} رابط`, `of ${num(all)} links`)} />
      </div>
      <Card>
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <b className="text-[15px] text-ink">{bi("روابط الدفع", "Payment links")}</b>
          <Select className="!w-auto" value={st} onChange={(e) => load(e.target.value)}>
            <option value="">{bi("كل الحالات", "All statuses")}</option>
            {Object.entries(ST).map(([k, [l]]) => <option key={k} value={k}>{l}</option>)}
          </Select>
        </div>
        {!items.length ? (
          <Empty icon="card" title={st ? bi("لا شيء بهذه الحالة", "Nothing with this status") : bi("لا روابط دفع بعد", "No payment links yet")}
                 text={bi("أضف بطاقة «دفع» في باني الفلو (مثلاً بعد اختيار الغرفة وعدد الليالي)، أو اضغط «طلب دفع» في الصندوق المشترك. العميل يدفع بمدى أو Apple Pay أو البطاقة، والفلو يكمل وحده.", "Add a “Payment” card in the flow builder (e.g. after the room and nights are chosen), or press “Request payment” in the Team inbox. The customer pays by mada, Apple Pay or card and the flow carries on by itself.")} />
        ) : (
          <div className="-mx-2 overflow-x-auto px-2">
            <table className="w-full border-collapse text-[13px]">
              <thead><tr>{["#", bi("العميل", "Customer"), bi("الوصف", "Description"), bi("المبلغ", "Amount"), bi("الحالة", "Status"), bi("المصدر", "Source"), bi("التاريخ", "Date"), ""].map((h, i) => (
                <th key={i} className="whitespace-nowrap px-3 py-2.5 text-start text-[11px] font-extrabold uppercase tracking-wider text-ink-3 shadow-[inset_0_-1px_0_rgb(var(--ov-rgb)/0.08)]">{h}</th>))}</tr></thead>
              <tbody>{items.map((p) => {
                const [label, tone] = ST[p.status] || [p.status, "mute"];
                const td = "px-3 py-2.5 shadow-[inset_0_-1px_0_rgb(var(--ov-rgb)/0.05)]";
                return (
                  <tr key={p.id}>
                    <td className={`${td} tnum text-ink-3`}>{p.id}</td>
                    <td className={td}><b className="block max-w-[180px] truncate text-ink" dir="auto">{p.customer || p.peer.replace(/^[a-z]+:/, "")}</b><span className="text-[11.5px] text-ink-3">{p.bot_name}</span></td>
                    <td className={`${td} max-w-[220px] truncate text-ink-2`} dir="auto">{p.description || "—"}</td>
                    <td className={`${td} tnum whitespace-nowrap font-bold text-ink`}>{money(p.amount, p.currency)}</td>
                    <td className={td}><Pill tone={tone} dot>{label}</Pill></td>
                    <td className={`${td} whitespace-nowrap text-ink-3`}>{p.flow_id ? bi("فلو", "Flow") : bi("موظف", "Agent")} · {GW_NAME[p.provider] || p.provider}</td>
                    <td className={`${td} whitespace-nowrap text-ink-3`}>{when(p.paid_at || p.created_at)}</td>
                    <td className={`${td} whitespace-nowrap`}>
                      <Btn sm variant="ghost" icon="inbox" href={`/inbox?bot=${p.bot_id}&peer=${encodeURIComponent(p.peer)}`} aria-label={bi("المحادثة", "Conversation")} />
                      {p.status === "pending" && p.url && <Btn sm variant="ghost" icon="copy" onClick={() => { copy(p.url); setCopied(p.id); setTimeout(() => setCopied(null), 1500); }}
                                                             aria-label={bi("نسخ الرابط", "Copy link")}>{copied === p.id ? "✓" : null}</Btn>}
                    </td>
                  </tr>
                );
              })}</tbody>
            </table>
          </div>
        )}
      </Card>
    </>
  );
}
