import { useEffect, useRef, useState } from "react";
import {
  BY, P, t, bi, Icon, Card, Btn, Field, Input, Select, Textarea, Form, Pill, PageHead,
  SectionTitle, Table, Tr, Td, Empty, num, fmtDate,
} from "../kit.jsx";
import { Flashes } from "../AppShell.jsx";

/* ============================================================================
   رسائل البريد — حملات الأدمن (email_campaigns.py)
   اكتب ← عاين كما تصل ← جرّب على إيميلك ← أرسل. الإرسال في الخادم (خيط خلفي،
   سقف يومي، لا تكرار عند الاستئناف)؛ هنا فقط التحرير والمتابعة.
   ========================================================================== */

const blank = () => ({ subject: "", preheader: "", title: "", body: "", cta: "" });

async function post(url, body) {
  const r = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-CSRF-Token": BY.csrf },
    body: JSON.stringify(body || {}),
  });
  return r.json();
}

/* قوالب بداية — نقاط «…» يكملها الأدمن. لا أرقام ولا أكواد مخترعة. */
const PRESETS = [
  { k: "feature", icon: "sparkles", label: bi("ميزة جديدة", "New feature"), kind: "news", audience: "all",
    url: "/dashboard",
    ar: { subject: "جديد في BotYalla: …", preheader: "ميزة جديدة توفّر عليك وقت…", title: "",
          body: "أهلاً {name}،\n\nأضفنا ميزة جديدة لبوتك: **…**\n\n- ماذا تفعل: …\n- لمن تفيد: …\n- كيف تجرّبها: …\n\nجرّبها من لوحتك وقولنا رأيك بالرد على هذه الرسالة.",
          cta: "جرّبها الآن" } },
  { k: "offer", icon: "tag", label: bi("عرض خصم", "Discount offer"), kind: "news", audience: "free",
    url: "/pricing",
    ar: { subject: "عرض لفترة محدودة على باقات BotYalla", preheader: "خصم خاص لمشتركينا — ينتهي قريباً", title: "",
          body: "أهلاً {name}،\n\nجهّزنا لك خصماً خاصاً على أي باقة مدفوعة:\n\n- ردود ذكاء اصطناعي أكثر لعملائك\n- صندوق وارد ترد منه بنفسك\n- حملات ترسلها لكل عملائك\n\nالعرض ساري حتى **…**.",
          cta: "اختر باقتك" } },
  { k: "maint", icon: "settings", label: bi("صيانة مجدولة", "Maintenance"), kind: "service", audience: "all",
    url: "",
    ar: { subject: "صيانة مجدولة يوم … من … إلى …", preheader: "قد تتوقف البوتات دقائق معدودة", title: "",
          body: "أهلاً {name}،\n\nسنُجري تحديثاً للخوادم يوم **…** من الساعة … إلى …\n\n- قد تتوقف البوتات عن الرد دقائق معدودة\n- لا تحتاج أن تفعل أي شيء — كل بوت يعود للعمل تلقائياً\n\nشكراً لصبرك.",
          cta: "" } },
  { k: "activate", icon: "rocket", label: bi("فعّل بوتك", "Activate your bot"), kind: "news", audience: "no_bot",
    url: "/dashboard",
    ar: { subject: "بوتك على بُعد ضغطة واحدة", preheader: "أنشئ بوتك على تليجرام في دقيقة", title: "",
          body: "أهلاً {name}،\n\nلسه ما أنشأتش أول بوت ليك — والموضوع بقى أسهل من أي وقت:\n\n- اضغط «أنشئ بوتك على تليجرام بضغطة»\n- اكتب اسم نشاطك\n- اضغط «إنشاء» في تليجرام — وخلاص\n\nوقفت في أي خطوة؟ ردّ على الرسالة دي ونساعدك.",
          cta: "أنشئ بوتي الآن" } },
];

function audiences(plans) {
  return [
    ["all", bi("كل المشتركين", "Everyone")],
    ["paid", bi("المشتركون المدفوعون", "Paying members")],
    ["free", bi("غير المشتركين (مجاني)", "Not paying (free)")],
    ["no_bot", bi("سجّلوا ولم ينشئوا بوتاً", "Signed up, no bot yet")],
    ["expiring", bi("ينتهي اشتراكهم خلال 7 أيام", "Expiring within 7 days")],
    ["lapsed", bi("انتهى اشتراكهم", "Lapsed subscribers")],
    ...(plans || []).map((p) => [`plan:${p.id}`, bi(`باقة ${p.name}`, `${p.name} plan`)]),
  ];
}

function StatusPill({ c }) {
  if (c.status === "sending")
    return c.note === "cap_wait"
      ? <Pill tone="warn">{bi("تكمل غداً (السقف اليومي)", "Resumes tomorrow (daily cap)")}</Pill>
      : <Pill tone="on" dot>{bi("جارٍ الإرسال", "Sending")}</Pill>;
  if (c.status === "done") return <Pill tone="on">{bi("اكتملت", "Done")}</Pill>;
  const why = { smtp_error: bi("خطأ SMTP", "SMTP error"), no_public_url: "PUBLIC_URL",
                error: bi("خطأ", "Error") }[c.note];
  return <Pill tone={why ? "off" : "mute"}>{bi("متوقفة", "Stopped")}{why ? ` · ${why}` : ""}</Pill>;
}

function KindCard({ active, onClick, icon, title, desc, count }) {
  return (
    <button type="button" onClick={onClick}
      className={`flex w-full cursor-pointer items-start gap-3 rounded-2xl border-0 p-4 text-start transition-all duration-300
        ${active ? "bg-[linear-gradient(150deg,rgb(124_108_246/0.22),rgb(34_211_238/0.08))] shadow-[inset_0_0_0_1.5px_rgb(124_108_246/0.75)]"
                 : "bg-white/[0.03] shadow-[inset_0_0_0_1px_rgb(255_255_255/0.08)] hover:bg-white/[0.06]"}`}>
      <span className={`grid size-10 shrink-0 place-items-center rounded-xl ${active ? "bg-au-violet/30 text-ink" : "bg-white/5 text-ink-3"}`}>
        <Icon name={icon} size={20} />
      </span>
      <span className="min-w-0">
        <span className="flex items-center gap-2 text-[14.5px] font-extrabold text-ink">
          {title}<span className="tnum rounded-full bg-white/10 px-2 py-0.5 text-[11.5px] text-ink-2">{num(count)}</span>
        </span>
        <span className="mt-1 block text-[12.5px] leading-relaxed text-ink-3">{desc}</span>
      </span>
    </button>
  );
}

export function AdminEmails() {
  const [draft, setDraft] = useState({ kind: "news", audience: "all", ar: blank(), en: blank(), url: "", code: "" });
  const [tab, setTab] = useState("ar");
  const [hasEn, setHasEn] = useState(false);
  const [pl, setPl] = useState("ar");                 // لغة المعاينة
  const [device, setDevice] = useState("desktop");
  const [prev, setPrev] = useState(null);
  const [msg, setMsg] = useState(null);
  const [busy, setBusy] = useState(false);
  const [st, setSt] = useState({ campaigns: P.campaigns || [], today: P.today || 0, cap: P.cap || 250 });
  const [cap, setCap] = useState(String(P.cap || 250));
  const topRef = useRef(null);

  const counts = (P.counts || {})[draft.kind] || {};
  const n = counts[draft.audience] || 0;
  const payload = () => ({ ...draft, en: hasEn ? draft.en : blank() });
  const setPart = (k, v) => setDraft((d) => ({ ...d, [tab]: { ...d[tab], [k]: v } }));
  const set = (k, v) => setDraft((d) => ({ ...d, [k]: v }));

  /* معاينة حيّة من الخادم — نفس دالة القالب التي ترسل فعلاً */
  useEffect(() => {
    const h = setTimeout(async () => {
      try { setPrev(await post("/admin/emails/preview", { ...payload(), lang: pl })); } catch { /* تبقى المعاينة السابقة */ }
    }, 450);
    return () => clearTimeout(h);
  }, [draft, pl, hasEn]);

  /* متابعة التقدّم أثناء الإرسال */
  const sending = st.campaigns.some((c) => c.status === "sending");
  useEffect(() => {
    if (!sending) return;
    const iv = setInterval(async () => {
      try { const r = await fetch("/admin/emails/status"); setSt(await r.json()); } catch { /* المحاولة التالية */ }
    }, 4000);
    return () => clearInterval(iv);
  }, [sending]);

  function preset(p) {
    setDraft({ kind: p.kind, audience: p.audience, ar: { ...p.ar }, en: blank(), url: p.url, code: "" });
    setHasEn(false); setTab("ar"); setPl("ar"); setMsg(null);
  }

  function reuse(c) {
    const ct = c.content || {};
    const base = BY.urls.landing ? window.location.origin : "";
    let url = ct.url || "";
    if (base && url.startsWith(base)) url = url.slice(base.length) || "/";
    setDraft({ kind: c.kind, audience: c.audience, ar: { ...blank(), ...(ct.ar || {}) },
               en: { ...blank(), ...(ct.en || {}) }, url, code: ct.code || "" });
    setHasEn(!!(ct.en && ct.en.subject)); setTab("ar"); setPl("ar");
    setMsg({ tone: "ok", text: bi("تم تحميل الحملة كقالب — عدّلها وأرسلها من جديد.", "Campaign loaded as a template — edit and send again.") });
    topRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  async function testSend() {
    setBusy(true); setMsg(null);
    try {
      const r = await post("/admin/emails/test", { ...payload(), lang: pl });
      setMsg(r.ok ? { tone: "ok", text: bi(`اتبعتت نسخة تجربة لـ ${r.to} — لو ما وصلتش خلال دقيقة راجع Spam وإعدادات SMTP.`,
                                             `A test copy went to ${r.to} — not there in a minute? Check spam and SMTP settings.`) }
                  : { tone: "err", text: r.error });
    } catch { setMsg({ tone: "err", text: bi("تعذّر الاتصال بالخادم.", "Couldn't reach the server.") }); }
    setBusy(false);
  }

  async function send() {
    const who = draft.kind === "news" ? bi("مشترك وافق على الأخبار", "opted-in members") : bi("مشترك", "members");
    if (!window.confirm(bi(`الرسالة هتتبعت لـ ${num(n)} ${who}. متأكد؟`, `This goes to ${num(n)} ${who}. Send it?`))) return;
    setBusy(true); setMsg(null);
    try {
      const r = await post("/admin/emails/send", payload());
      if (r.ok) {
        setSt(r);
        setMsg({ tone: "ok", text: bi(`بدأ الإرسال (#${r.id}) — تابع التقدّم في «الحملات» تحت.`, `Sending started (#${r.id}) — follow it under “Campaigns”.`) });
      } else setMsg({ tone: "err", text: r.error });
    } catch { setMsg({ tone: "err", text: bi("تعذّر الاتصال بالخادم.", "Couldn't reach the server.") }); }
    setBusy(false);
  }

  async function act(c, action) {
    if (action === "stop" && !window.confirm(bi("إيقاف الحملة؟ تقدر تستأنفها بعدين من نفس المكان.", "Stop this campaign? You can resume it later from where it stopped."))) return;
    const r = await post(`/admin/emails/${c.id}/${action}`);
    setSt(r);
    if (!r.ok && r.error) setMsg({ tone: "err", text: r.error });
  }

  async function saveCap() {
    const r = await post("/admin/emails/settings", { cap: Number(cap) });
    if (r.ok) { setSt(r); setMsg({ tone: "ok", text: bi("تم حفظ السقف اليومي.", "Daily cap saved.") }); }
    else setMsg({ tone: "err", text: r.error });
  }

  const part = draft[tab];
  const auds = audiences(P.plans);
  const audLabel = Object.fromEntries(auds);
  const canSend = P.smtp && n > 0 && !sending && (draft.kind === "service" || P.publicUrl);

  return (
    <>
      <div ref={topRef} />
      <PageHead icon="mail" title={t("adm_emails")}
        sub={bi("أخبار وعروض وإشعارات لمشتركيك على الإيميل — بتصميم BotYalla، ومعاينة كما تصل بالضبط، وإرسال آمن بسقف يومي.",
                "News, offers and notices to your members by email — BotYalla-branded, previewed exactly as delivered, sent safely under a daily cap.")} />

      {!P.smtp && (
        <Card className="mb-5 !border-0 shadow-[inset_0_0_0_1px_rgb(248_113_113/0.4)]">
          <p className="m-0 text-[13.5px] leading-relaxed text-red-200">
            <b>{bi("SMTP غير مضبوط على الخادم — لا شيء سيُرسل.", "SMTP isn't configured on the server — nothing will be sent.")}</b>{" "}
            {bi("اضبط SMTP_HOST وSMTP_FROM في .env (الخطوات في docs/EMAIL_DNS.md). التحرير والمعاينة يعملان الآن.",
                "Set SMTP_HOST and SMTP_FROM in .env (steps in docs/EMAIL_DNS.md). Editing and preview work now.")}
          </p>
        </Card>
      )}

      <div className="mb-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {[[bi("لهم إيميل", "Have an email"), P.reach?.with_email, "users"],
          [bi("وافقوا على الأخبار", "Opted in to news"), P.reach?.opted_in, "check"],
          [bi("اتبعت النهارده", "Sent today"), `${num(st.today)} / ${num(st.cap)}`, "chart"]].map(([l, v, ic]) => (
          <Card key={l} className="!p-5">
            <Icon name={ic} size={19} className="text-au-cyan" />
            <div className="mt-2 tnum text-[24px] font-extrabold text-ink">{typeof v === "number" ? num(v) : v}</div>
            <div className="mt-1 text-[12.5px] text-ink-3">{l}</div>
          </Card>
        ))}
        <Card className="!p-5">
          <div className="text-[12.5px] font-bold text-ink-2">{bi("السقف اليومي", "Daily cap")}</div>
          <div className="mt-2 flex gap-2">
            <Input type="number" min="1" max="100000" dir="ltr" value={cap} onChange={(e) => setCap(e.target.value)} className="!py-2" />
            <Btn sm variant="ghost" icon="check" type="button" onClick={saveCap}>{bi("حفظ", "Save")}</Btn>
          </div>
          <div className="mt-1.5 text-[11.5px] leading-relaxed text-ink-3">
            {bi("تحت حدّ مزوّدك (Brevo المجاني 300/يوم). الباقي يكمل غداً وحده.", "Below your provider's limit (Brevo free: 300/day). The rest goes out tomorrow.")}
          </div>
        </Card>
      </div>

      <div className="mb-6 grid items-start gap-5 xl:grid-cols-2">
        {/* ------------------------------------------------ المحرّر */}
        <Card>
          <SectionTitle icon="chat">{bi("اكتب رسالتك", "Write your message")}</SectionTitle>
          <div className="mb-5 flex flex-wrap gap-2">
            <span className="self-center text-[12px] font-bold text-ink-3">{bi("ابدأ من:", "Start from:")}</span>
            {PRESETS.map((p) => <Btn key={p.k} sm variant="ghost" icon={p.icon} type="button" onClick={() => preset(p)}>{p.label}</Btn>)}
          </div>

          <div className="mb-4 grid gap-3 sm:grid-cols-2">
            <KindCard active={draft.kind === "news"} onClick={() => set("kind", "news")} icon="megaphone"
              title={bi("أخبار وعروض", "News & offers")} count={P.reach?.opted_in || 0}
              desc={bi("للموافقين على الأخبار فقط، وفيها رابط إلغاء بضغطة.", "Opted-in members only, with one-click unsubscribe.")} />
            <KindCard active={draft.kind === "service"} onClick={() => set("kind", "service")} icon="shield"
              title={bi("إشعار خدمة", "Service notice")} count={P.reach?.with_email || 0}
              desc={bi("لكل من له إيميل — للأمور المهمة فقط (صيانة، تغيير في الشروط). ممنوع التسويق.",
                       "Everyone with an email — important matters only (maintenance, terms). No marketing.")} />
          </div>
          {draft.kind === "news" && !P.publicUrl && (
            <p className="mb-4 mt-0 text-[12.5px] text-amber-200">
              {bi("رسائل الأخبار تحتاج PUBLIC_URL في .env لرابط إلغاء الاشتراك.", "News emails need PUBLIC_URL in .env for the unsubscribe link.")}
            </p>
          )}

          <Field label={bi("الجمهور", "Audience")} className="mb-5">
            <Select value={draft.audience} onChange={(e) => set("audience", e.target.value)}>
              {auds.map(([k, l]) => <option key={k} value={k}>{`${l} · ${num(counts[k] || 0)}`}</option>)}
            </Select>
          </Field>

          <div className="mb-4 flex items-center gap-2">
            {["ar", ...(hasEn ? ["en"] : [])].map((L) => (
              <Btn key={L} sm type="button" variant={tab === L ? "primary" : "ghost"}
                   onClick={() => { setTab(L); setPl(L); }}>{L === "ar" ? "العربية" : "English"}</Btn>
            ))}
            {hasEn ? (
              <button type="button" onClick={() => { setHasEn(false); setTab("ar"); setPl("ar"); }}
                className="ms-auto cursor-pointer border-0 bg-transparent text-[12px] text-ink-3 hover:text-red-300">
                {bi("احذف النسخة الإنجليزية", "Remove English version")}
              </button>
            ) : (
              <button type="button" onClick={() => { setHasEn(true); setTab("en"); setPl("en"); }}
                className="ms-auto cursor-pointer border-0 bg-transparent text-[12.5px] font-bold text-au-cyan hover:underline">
                + {bi("نسخة إنجليزية (اختياري)", "English version (optional)")}
              </button>
            )}
          </div>

          <div dir={tab === "en" ? "ltr" : "rtl"}>
            <Field label={bi("عنوان الرسالة (Subject)", "Subject")} className="mb-4">
              <Input value={part.subject} maxLength={150} onChange={(e) => setPart("subject", e.target.value)} />
            </Field>
            <Field label={bi("سطر المعاينة", "Preview line")} className="mb-4"
                   hint={bi("السطر الرمادي بجانب العنوان في صندوق الوارد — يرفع نسبة الفتح.", "The grey line next to the subject in the inbox — lifts open rates.")}>
              <Input value={part.preheader} maxLength={150} onChange={(e) => setPart("preheader", e.target.value)} />
            </Field>
            <Field label={bi("العنوان داخل الرسالة (اختياري)", "Headline inside the email (optional)")} className="mb-4">
              <Input value={part.title} maxLength={150} placeholder={part.subject} onChange={(e) => setPart("title", e.target.value)} />
            </Field>
            <Field label={bi("نص الرسالة", "Message")} className="mb-4"
                   hint={bi("سطر فارغ = فقرة جديدة · سطر يبدأ بـ «- » = نقطة · **عريض** · {name} = اسم المشترك · روابط https تتحول تلقائياً.",
                            "Blank line = new paragraph · line starting with “- ” = bullet · **bold** · {name} = member's name · https links become clickable.")}>
              <Textarea value={part.body} rows={11} maxLength={6000} className="min-h-[240px] leading-relaxed"
                        onChange={(e) => setPart("body", e.target.value)} />
            </Field>
            <Field label={bi("نص الزر", "Button label")} className="mb-4">
              <Input value={part.cta} maxLength={40} placeholder={tab === "en" ? "Open" : "افتح"} onChange={(e) => setPart("cta", e.target.value)} />
            </Field>
          </div>

          <div className="grid gap-4 sm:grid-cols-2">
            <Field label={bi("رابط الزر", "Button link")} hint={bi("مسار داخلي مثل /pricing أو رابط https://", "An internal path like /pricing or an https:// link")}>
              <Input value={draft.url} dir="ltr" maxLength={500} placeholder="/pricing" onChange={(e) => set("url", e.target.value)} />
            </Field>
            <Field label={bi("كود خصم (اختياري)", "Promo code (optional)")} hint={bi("يظهر في صندوق كوبون مميز — أنشئه أولاً من «أكواد الخصم».", "Shown in a coupon box — create it first under “Promo codes”.")}>
              <Input value={draft.code} dir="ltr" maxLength={32} className="uppercase tracking-widest" onChange={(e) => set("code", e.target.value.toUpperCase())} />
            </Field>
          </div>

          {msg && (
            <p className={`mb-0 mt-5 rounded-xl px-3.5 py-3 text-[13px] leading-relaxed ${msg.tone === "ok" ? "bg-au-teal/10 text-au-teal" : "bg-red-400/10 text-red-200"}`}>
              {msg.text}
            </p>
          )}
          <div className="mt-5 flex flex-wrap gap-3">
            <Btn icon="rocket" type="button" disabled={busy || !canSend} onClick={send}>
              {bi(`أرسل لـ ${num(n)} مشترك`, `Send to ${num(n)} members`)}
            </Btn>
            <Btn variant="ghost" icon="mail" type="button" disabled={busy || !P.smtp || !P.myEmail} onClick={testSend}>
              {bi("جرّبها على إيميلي", "Send me a test")}
            </Btn>
          </div>
          {!P.myEmail && (
            <p className="mb-0 mt-2 text-[12px] text-ink-3">
              {bi("لتجربة الرسالة أضف إيميلك من ", "To test, add your email on ")}
              <a href={BY.urls.account} className="text-au-cyan">{t("account_title")}</a>.
            </p>
          )}
          {sending && <p className="mb-0 mt-2 text-[12px] text-amber-200">{bi("فيه حملة بتتبعت دلوقتي — الإرسال الجديد بعد ما تخلص.", "A campaign is sending — new sends wait until it finishes.")}</p>}
        </Card>

        {/* ------------------------------------------------ المعاينة */}
        <div className="xl:sticky xl:top-6">
          <Card>
            <SectionTitle icon="image"
              extra={<div className="flex gap-1.5">
                {[["desktop", bi("كمبيوتر", "Desktop")], ["mobile", bi("موبايل", "Mobile")]].map(([k, l]) => (
                  <Btn key={k} sm type="button" variant={device === k ? "primary" : "ghost"} onClick={() => setDevice(k)}>{l}</Btn>))}
              </div>}>
              {bi("كما تصل للمشترك", "As your member sees it")}
            </SectionTitle>

            {hasEn && (
              <div className="mb-3 flex gap-1.5">
                {[["ar", bi("مشترك عربي", "Arabic reader")], ["en", bi("مشترك إنجليزي", "English reader")]].map(([k, l]) => (
                  <Btn key={k} sm type="button" variant={pl === k ? "primary" : "ghost"} onClick={() => setPl(k)}>{l}</Btn>))}
              </div>
            )}
            {!hasEn && <p className="mb-3 mt-0 text-[12px] text-ink-3">{bi("بلا نسخة إنجليزية، يستلم الكل النسخة العربية.", "Without an English version, everyone gets the Arabic one.")}</p>}

            {/* سطر صندوق الوارد */}
            <div className="mb-3 flex items-center gap-3 rounded-xl bg-white px-3.5 py-3 text-[#1F2937]" dir={pl === "en" ? "ltr" : "rtl"}>
              <span className="grid size-9 shrink-0 place-items-center rounded-full bg-[#0B1020]">
                <img src="/static/brand/email-mark.png" alt="" className="h-6 w-auto" />
              </span>
              <span className="min-w-0 flex-1">
                <span className="flex items-baseline gap-2">
                  <b className="truncate text-[13.5px]">{P.sender?.name || "BotYalla"}</b>
                  <span className="ms-auto shrink-0 text-[11px] text-[#6B7280]">{bi("الآن", "now")}</span>
                </span>
                <span className="block truncate text-[13px]">
                  <b>{prev?.subject || "…"}</b>
                  {prev?.preheader && <span className="text-[#6B7280]"> — {prev.preheader}</span>}
                </span>
              </span>
            </div>

            <div className="overflow-hidden rounded-xl bg-[#EEF1F7]">
              {prev?.html ? (
                <iframe title="email preview" srcDoc={prev.html} sandbox="allow-popups allow-popups-to-escape-sandbox"
                  className="mx-auto block h-[760px] border-0 bg-[#EEF1F7] transition-[width] duration-300"
                  style={{ width: device === "mobile" ? 390 : "100%", maxWidth: "100%" }} />
              ) : <div className="grid h-[300px] place-items-center text-[13px] text-[#6B7280]">{bi("جارٍ تجهيز المعاينة…", "Preparing preview…")}</div>}
            </div>
          </Card>
        </div>
      </div>

      {/* ------------------------------------------------ الحملات */}
      <Card>
        <SectionTitle icon="megaphone">{bi("الحملات", "Campaigns")}</SectionTitle>
        {st.campaigns.length ? (
          <Table head={["#", bi("الموضوع", "Subject"), bi("النوع", "Type"), bi("الجمهور", "Audience"),
                        bi("التقدّم", "Progress"), bi("الحالة", "Status"), bi("التاريخ", "Date"), ""]}>
            {st.campaigns.map((c) => {
              const done = (c.sent || 0) + (c.failed || 0) + (c.skipped || 0);
              const pct = c.total ? Math.min(100, Math.round((done / c.total) * 100)) : 0;
              return (
                <Tr key={c.id}>
                  <Td className="tnum text-ink-3">#{c.id}</Td>
                  <Td className="max-w-[260px]"><span className="block truncate font-bold text-ink">{c.content?.ar?.subject || "—"}</span></Td>
                  <Td>{c.kind === "news" ? <Pill tone="mute">{bi("أخبار", "News")}</Pill> : <Pill tone="mute">{bi("خدمة", "Service")}</Pill>}</Td>
                  <Td className="whitespace-nowrap text-[13px]">{audLabel[c.audience] || c.audience}</Td>
                  <Td className="min-w-[170px]">
                    <div className="mb-1 flex gap-2 text-[12px]">
                      <span className="tnum text-ink">{num(c.sent)} / {num(c.total)}</span>
                      {c.failed > 0 && <span className="tnum text-red-300">· {num(c.failed)} {bi("فشل", "failed")}</span>}
                      {c.skipped > 0 && <span className="tnum text-ink-3">· {num(c.skipped)} {bi("ألغوا", "opted out")}</span>}
                    </div>
                    <div className="h-1.5 overflow-hidden rounded-full bg-white/[0.08]">
                      <div className="h-full rounded-full bg-[linear-gradient(90deg,#8FE9FF,#B9AFFF)] transition-[width] duration-700" style={{ width: `${pct}%` }} />
                    </div>
                  </Td>
                  <Td><StatusPill c={c} /></Td>
                  <Td className="whitespace-nowrap text-[12.5px]">{fmtDate(c.created_at)}</Td>
                  <Td>
                    <div className="flex gap-1.5">
                      {c.status === "sending" && <Btn sm variant="ghost" icon="stop" type="button" onClick={() => act(c, "stop")}>{bi("إيقاف", "Stop")}</Btn>}
                      {c.status === "stopped" && <Btn sm variant="ghost" icon="play" type="button" onClick={() => act(c, "resume")}>{bi("استئناف", "Resume")}</Btn>}
                      <Btn sm variant="ghost" icon="copy" type="button" onClick={() => reuse(c)}>{bi("كقالب", "Reuse")}</Btn>
                    </div>
                  </Td>
                </Tr>
              );
            })}
          </Table>
        ) : <Empty icon="mail" title={bi("لا حملات بعد", "No campaigns yet")}
                   text={bi("اختر قالب بداية فوق، عاين الرسالة، جرّبها على إيميلك، ثم أرسلها.", "Pick a starter above, preview it, send yourself a test, then send.")} />}
        <p className="mb-0 mt-4 text-[12px] leading-relaxed text-ink-3">
          {bi("الإرسال رسالة كل ثانية تقريباً وتحت السقف اليومي. الإيقاف ثم الاستئناف لا يكرر رسالة لأحد، والرسائل التي فشلت تُعاد عند الاستئناف. روابط موقعك في الحملة تحمل utm_source=email فتظهر في «إحصائيات الزوار».",
              "Roughly one email per second, under the daily cap. Stop/resume never sends anyone a duplicate, and failed ones are retried on resume. Links to your site carry utm_source=email, so they show up in Visitor analytics.")}
        </p>
      </Card>
    </>
  );
}

/* صفحة إلغاء الاشتراك (بلا قشرة) — من رابط أسفل رسائل الأخبار */
export function Unsubscribe() {
  const on = !!P.on;
  const done = P.done;
  const title = done === "off" ? bi("تم إلغاء اشتراكك", "You're unsubscribed")
    : done === "on" ? bi("رجعت للقائمة 🎉", "You're back on the list 🎉")
    : on ? bi("إلغاء رسائل الأخبار والعروض", "Unsubscribe from news & offers")
    : bi("أنت غير مشترك في الأخبار", "You're not subscribed to news");
  return (
    <div className="mx-auto flex min-h-screen max-w-[460px] flex-col justify-center px-5 py-16">
      <Flashes />
      <a href={BY.urls.landing} className="mb-6 flex justify-center no-underline">
        <img src={BY.urls.logo} alt={BY.brand} className="h-11 w-auto" />
      </a>
      <Card className="!p-8 text-center">
        <span className="mx-auto mb-4 grid size-14 place-items-center rounded-2xl text-au-cyan
                         bg-[linear-gradient(150deg,rgb(124_108_246/0.25),rgb(34_211_238/0.1))]">
          <Icon name="mail" size={26} />
        </span>
        <h1 className="m-0 text-[22px] font-extrabold tracking-tight text-ink">{title}</h1>
        <p className="mb-6 mt-3 text-[14px] leading-relaxed text-ink-3">
          {on ? bi("مش هتوصلك أخبار أو عروض بعد الإلغاء.", "You won't get news or offers after this.")
              : bi("مش هتوصلك أخبار أو عروض من BotYalla.", "You won't get news or offers from BotYalla.")}{" "}
          {bi("رسائل حسابك المهمة (الإيصالات، استرجاع كلمة المرور، تذكير الاشتراك) مستمرة — دي مش تسويق.",
              "Important account emails (receipts, password reset, renewal reminders) continue — they aren't marketing.")}
        </p>
        <Form action="">
          <input type="hidden" name="on" value={on ? "0" : "1"} />
          <Btn block variant={on ? "ghost" : "primary"} icon={on ? "close" : "check"} type="submit">
            {on ? bi("ألغِ اشتراكي في الأخبار", "Unsubscribe me") : bi("اشترك مرة تانية في الأخبار", "Subscribe me again")}
          </Btn>
        </Form>
        <p className="mb-0 mt-6 text-[13px]">
          <a href={BY.urls.landing} className="font-bold text-au-cyan underline-offset-4 hover:underline">
            {bi("الرجوع للموقع", "Back to the site")}
          </a>
        </p>
      </Card>
    </div>
  );
}
