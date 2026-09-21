import { useState, useRef, useEffect } from "react";
import { motion } from "motion/react";
import {
  BY, P, t, bi, Icon, Card, Btn, Field, Input, Select, Form, Grid, Stat,
  Pill, Empty, PageHead, SectionTitle, Reveal, num,
} from "../kit.jsx";
import { postJSON } from "../media.jsx";

/* ============================================================================
   إنشاء بوت تليجرام بضغطة (Telegram Managed Bots) — بلا BotFather ولا توكن.
   الزر/QR يفتح بوت المنصة، وتليجرام يطلب تأكيداً واحداً، والصفحة تتابع
   الحالة وتفتح البوت الجديد وحدها. الإنشاء الفعلي في الخادم (managed_bots.py).
   ========================================================================== */
function OneTapCreate() {
  const [name, setName] = useState("");
  const [tpl, setTpl] = useState("customer_service");
  const [req, setReq] = useState(null);      // {id, link, qr, suggested}
  const [st, setSt] = useState(null);        // pending · linked · creating · created · failed · expired
  const [err, setErr] = useState(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!req) return;
    let alive = true, timer;
    const tick = async () => {
      try {
        const d = await (await fetch(`/bot/create/managed/${req.id}`)).json();
        if (!alive) return;
        setSt(d.status);
        if (d.status === "created" && d.url) { setTimeout(() => location.assign(d.url), 1100); return; }
        if (d.status === "failed" || d.status === "expired") {
          if (d.status === "failed") setErr({ error: d.error === "limit" ? t("mb_tg_limit") : t("onetap_failed") });
          return;
        }
      } catch { /* الشبكة — نعيد المحاولة */ }
      timer = setTimeout(tick, 2000);
    };
    tick();
    return () => { alive = false; clearTimeout(timer); };
  }, [req]);

  async function start(e) {
    e.preventDefault();
    setBusy(true); setErr(null);
    const d = await postJSON(BY.urls.botCreateManaged, { name: name.trim(), template: tpl });
    setBusy(false);
    if (d.ok) { setReq(d); setSt("pending"); } else setErr(d);
  }
  const reset = () => { setReq(null); setSt(null); setErr(null); };

  const STEPS = ["onetap_s1", "onetap_s2", "onetap_s3"];
  const stepIdx = st === "created" ? 3 : st === "creating" ? 2 : st === "linked" ? 1 : 0;
  const statusText = { pending: t("onetap_wait"), linked: t("onetap_linked"), creating: t("onetap_creating"),
                       created: t("onetap_done"), expired: t("onetap_expired"), failed: t("onetap_failed") }[st];

  return (
    <Card id="onetap" className="mb-6 bg-[linear-gradient(125deg,rgb(34_211_238/0.16),rgb(124_108_246/0.18))]
                                  shadow-[inset_0_0_0_1px_rgb(143_233_255/0.25)]">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 className="m-0 flex items-center gap-2.5 text-[19px] font-extrabold text-ink">
            <img src="/static/Telegram.svg.png" alt="" className="size-6 object-contain" />{t("onetap_title")}
          </h2>
          <p className="mt-1.5 mb-0 max-w-[560px] text-[13.5px] leading-relaxed text-ink-3">{t("onetap_sub")}</p>
        </div>
      </div>

      {!req ? (
        <form onSubmit={start} className="mt-5 grid grid-cols-1 gap-3 sm:grid-cols-[minmax(0,1fr)_220px_auto] sm:items-end">
          <Field label={t("biz_name")}>
            <Input value={name} onChange={(e) => setName(e.target.value)} required maxLength={60}
                   placeholder={t("eg_cafe")} />
          </Field>
          <Field label={t("bot_type")}>
            <Select value={tpl} onChange={(e) => setTpl(e.target.value)}>
              {BY.templates.map((x) => <option key={x.k} value={x.k}>{x.label}</option>)}
            </Select>
          </Field>
          <Btn icon="rocket" type="submit" disabled={busy || !name.trim()}>{busy ? "…" : t("onetap_btn")}</Btn>
        </form>
      ) : (
        <div className="mt-5 grid grid-cols-1 items-center gap-6 md:grid-cols-[200px_minmax(0,1fr)]">
          <div className="mx-auto hidden w-[200px] rounded-2xl bg-white p-3 md:block">
            <img src={req.qr} alt="QR" width="176" height="176" className="block size-full" />
            <div className="mt-1.5 text-center text-[11.5px] font-bold text-[#07090F]">{t("onetap_scan")}</div>
          </div>
          <div className="min-w-0">
            <ol className="m-0 mb-4 flex list-none flex-col gap-2.5 p-0">
              {STEPS.map((k, i) => (
                <li key={k} className="flex items-center gap-3 text-[14px]">
                  <span className={"grid size-7 shrink-0 place-items-center rounded-full text-[12.5px] font-extrabold " +
                                   (i < stepIdx ? "bg-au-teal text-[#04140E]"
                                     : i === stepIdx ? "bg-[linear-gradient(100deg,#8FE9FF,#B9AFFF)] text-[#07090F]"
                                     : "bg-white/[0.07] text-ink-3")}>
                    {i < stepIdx ? <Icon name="check" size={14} /> : i + 1}
                  </span>
                  <span className={i <= stepIdx ? "font-bold text-ink" : "text-ink-3"}>{t(k)}</span>
                </li>
              ))}
            </ol>
            <div className="flex flex-wrap items-center gap-3">
              <span className="text-[12.5px] text-ink-3 md:hidden">{t("onetap_or_tap")}</span>
              <Btn variant="green" icon="play" href={req.link} target="_blank" rel="noopener">{t("onetap_open")}</Btn>
              <Btn variant="ghost" sm type="button" onClick={reset}>{t("cancel")}</Btn>
            </div>
            {statusText && (
              <p role="status" aria-live="polite"
                 className={"mt-4 mb-0 flex items-center gap-2 text-[13.5px] font-bold " +
                            (st === "created" ? "text-au-teal" : st === "failed" || st === "expired" ? "text-red-300" : "text-ink-2")}>
                {(st === "pending" || st === "linked" || st === "creating") &&
                  <span className="size-4 animate-spin rounded-full border-2 border-white/15 border-t-au-cyan" />}
                {statusText}
                {(st === "failed" || st === "expired") &&
                  <Btn sm variant="ghost" type="button" onClick={reset}>{t("onetap_retry")}</Btn>}
              </p>
            )}
          </div>
        </div>
      )}

      {err && (
        <p role="alert" className="mt-4 mb-0 text-[13px] font-bold text-red-300">
          {err.error}{" "}
          {err.upgrade && <a href={BY.urls.pricing} className="text-au-cyan underline">{t("brain_upgrade")}</a>}
        </p>
      )}
    </Card>
  );
}

/* بطاقة بوت */
function BotCard({ b, i }) {
  const meta = BY.templates.find((x) => x.k === b.template) || { icon: "bot", label: b.template };
  return (
    <Reveal delay={i * 0.05}>
      <Card spot as="a" href={`/bot/${b.id}`}
            className="group block h-full no-underline transition-transform duration-500
                       ease-[cubic-bezier(0.16,1,0.3,1)] hover:-translate-y-1">
        <div className="flex items-center justify-between gap-3">
          <div className="flex min-w-0 items-center gap-3">
            <span className="grid size-11 shrink-0 place-items-center rounded-xl text-au-cyan
                             bg-[linear-gradient(150deg,rgb(124_108_246/0.28),rgb(34_211_238/0.12))]
                             shadow-[inset_0_0_0_1px_rgb(255_255_255/0.09)]
                             transition-transform duration-500 ease-[cubic-bezier(0.175,0.885,0.32,1.275)]
                             group-hover:-rotate-6 group-hover:scale-110">
              <Icon name={meta.icon} size={21} />
            </span>
            <div className="min-w-0">
              <div className="truncate text-[15px] font-extrabold text-ink">{b.name}</div>
              <div className="truncate text-[12px] text-ink-3">{meta.label}</div>
            </div>
          </div>
          <div className="flex shrink-0 items-center gap-1.5">
            {(b.channel || "telegram") === "whatsapp" && (
              <Pill tone="mute"><img src="/static/whatsapp.png" alt="WhatsApp" className="size-[11px] object-contain inline-block" />WA</Pill>
            )}
            {b.channel === "messenger" && <Pill tone="mute"><Icon name="chat" size={11} />Messenger</Pill>}
            {b.channel === "instagram" && <Pill tone="mute"><Icon name="camera" size={11} />Instagram</Pill>}
            {b.running ? <Pill tone="on" dot>{t("running")}</Pill> : <Pill tone="off">{t("stopped")}</Pill>}
          </div>
        </div>

        <div className="mt-5 flex flex-wrap gap-x-5 gap-y-2 text-[13px] text-ink-3">
          {[["users", b.stats.subscribers], ["store", b.stats.orders],
            ["calendar", b.stats.bookings], ["wallet", b.stats.revenue]].map(([ic, v]) => (
            <span key={ic} className="inline-flex items-center gap-1.5">
              <Icon name={ic} size={14} className="text-ink-3/70" />
              <b className="tnum text-ink">{num(v)}</b>
            </span>
          ))}
        </div>
      </Card>
    </Reveal>
  );
}

/* «اربط رقمك بضغطة» — WhatsApp Embedded Signup (BotYalla مزوّد خدمة تقنية معتمد من Meta).

   نافذة منبثقة على رابط حوار Meta يبنيه الخادم (/whatsapp/es/start)، لا FB.login من الـSDK:
   Chrome يحوّل نداء الـSDK إلى مسار FedCM فيسقط config_id ويطلب scope=openid وحده، فترد
   Meta بـ«هذا التطبيق يحتاج إلى supported permission واحد على الأقل». والنافذة تعمل كذلك
   مع مانعات الإعلانات التي تحجب سكربت فيسبوك.

   Meta تُعيد العميل إلى /whatsapp/es/return (نفس أصلنا) فيُرسل الكود لهذه الصفحة ويقفل نفسه،
   ثم الخادم وحده يبدّل ويكتشف الحساب من التوكن ويتحقّق ويسجّل. لا سرّ ولا توكن في المتصفح. */

/* منطق الربط بضغطة — fields() تُرجع {name, template, coexist} لحظة الضغط. */
function useWaSignup(cfg, fields) {
  const [state, setState] = useState({ busy: false, msg: null, ok: null });
  const session = useRef(null);      // معلومات نافذة Meta إن وصلت (waba_id/phone_number_id)
  const done = useRef(false);        // كود واحد لكل نافذة

  useEffect(() => {
    const onMsg = (ev) => {
      let d = ev.data;
      try { if (typeof d === "string") d = JSON.parse(d); } catch { return; }
      if (!d) return;
      if (ev.origin === window.location.origin && d.type === "BY_WA_ES") {
        if (done.current) return;
        done.current = true;
        if (d.code) finish(d.code);
        else setState({ busy: false, ok: false, msg: d.error === "state"
          ? bi("الجلسة اتغيّرت — حدّث الصفحة وجرّب تاني.", "The session changed — refresh the page and try again.")
          : bi("اتلغى الربط من نافذة Meta.", "The connection was cancelled in the Meta window.") });
        return;
      }
      let host = "";
      try { host = new URL(ev.origin).hostname; } catch { return; }
      if (!/(^|\.)facebook\.com$/.test(host)) return;          // رسائل نافذة Meta وحدها
      if (d.type !== "WA_EMBEDDED_SIGNUP") return;
      if (String(d.event || "").startsWith("FINISH")) session.current = d.data || {};
      else if (d.event === "ERROR") session.current = { error: (d.data && d.data.error_message) || "error" };
    };
    window.addEventListener("message", onMsg);
    return () => window.removeEventListener("message", onMsg);
  }, []);

  async function finish(code) {
    const s = session.current || {};
    const f = fields();
    setState({ busy: true, ok: null, msg: bi("بنربط رقمك ونجهّز البوت…", "Connecting your number and preparing the bot…") });
    try {
      const r = await fetch("/whatsapp/es/finish", {
        method: "POST", credentials: "same-origin",
        headers: { "Content-Type": "application/json", "X-CSRF-Token": BY.csrf },
        body: JSON.stringify({ code, waba_id: s.waba_id || "", phone_id: s.phone_number_id || "",
                               name: f.name, template: f.template, coexist: !!f.coexist }),
      });
      let d = null;
      try { d = await r.json(); } catch { /* صفحة خطأ */ }
      if (d && d.ok) {
        setState({ busy: true, ok: true, msg: bi("تم! بنفتح البوت…", "Done! Opening your bot…") });
        window.location.href = d.url; return;
      }
      setState({ busy: false, ok: false, msg: (d && d.error) || `HTTP ${r.status}`, upgrade: d && d.upgrade });
    } catch {
      setState({ busy: false, ok: false, msg: bi("مفيش اتصال بالسيرفر — جرّب تاني.", "No connection to the server — try again.") });
    }
  }

  async function start() {
    session.current = null; done.current = false;
    // النافذة تُفتح داخل الضغطة نفسها وإلا حجبها المتصفح — ثم نوجّهها بعد رد الخادم
    const w = window.open("", "by_wa_es", "width=600,height=760,menubar=no,toolbar=no");
    setState({ busy: true, ok: null, msg: bi("بنفتح نافذة Meta…", "Opening the Meta window…") });
    let d = null;
    try {
      const r = await fetch("/whatsapp/es/start", {
        method: "POST", credentials: "same-origin",
        headers: { "Content-Type": "application/json", "X-CSRF-Token": BY.csrf },
        body: JSON.stringify({ coexist: !!fields().coexist }),
      });
      d = await r.json();
    } catch { /* الشبكة */ }
    if (!d || !d.ok || !d.url) {
      if (w) w.close();
      return setState({ busy: false, ok: false, msg: (d && d.error)
        || bi("مفيش اتصال بالسيرفر — جرّب تاني.", "No connection to the server — try again.") });
    }
    if (!w) {
      return setState({ busy: false, ok: false, msg: bi(
        "المتصفح منع النافذة — اسمح بالنوافذ المنبثقة للموقع ده وجرّب تاني.",
        "Your browser blocked the popup — allow popups for this site and try again.") });
    }
    w.location.href = d.url;
    setState({ busy: true, ok: null, msg: bi("كمّل الخطوات في نافذة Meta…", "Finish the steps in the Meta window…") });
  }
  return { state, start };
}

const WA_CARD = "mb-6 bg-[linear-gradient(125deg,rgb(37_211_102/0.16),rgb(34_211_238/0.08))] " +
                "shadow-[inset_0_0_0_1px_rgb(37_211_102/0.35)]";

function WaHead({ locked }) {
  return (
    <div className="min-w-0">
      <h2 className="m-0 flex flex-wrap items-center gap-2.5 text-[19px] font-extrabold text-ink">
        <img src="/static/whatsapp.png" alt="" className="size-6 object-contain" />
        {bi("أنشئ بوتك على واتساب بضغطة", "Create your WhatsApp bot in one tap")}
        {locked
          ? <Pill tone="mute"><Icon name="lock" size={11} />{bi("باقات واتساب", "WhatsApp plans")}</Pill>
          : <Pill tone="on">{bi("موصى به", "Recommended")}</Pill>}
      </h2>
      <p className="mt-1.5 mb-0 max-w-[620px] text-[13.5px] leading-relaxed text-ink-3">
        {bi("بدون لوحة مطوّرين ولا توكنات — نافذة Meta الرسمية بتفتح، تختار نشاطك ورقمك، والبوت بيتعمل ويتربط لوحده. BotYalla مزوّد خدمة تقنية معتمد من Meta.",
            "No developer console, no tokens — the official Meta window opens, you pick your business and number, and the bot is created and connected automatically. BotYalla is a Meta-approved Tech Provider.")}
      </p>
    </div>
  );
}

/* كارت علوي: ربط واتساب بضغطة (لمن تتيح باقته واتساب) */
/* تحذيرات وضع التعايش — تظهر قبل الربط ولازم العميل يأكّد إنه قرأها */
const COEXIST_NOTES = [
  ["لازم يكون تطبيق WhatsApp Business (مش واتساب العادي) ومحدّث لآخر إصدار، والرقم شغّال عليه من فترة — Meta بترفض الأرقام الجديدة على التطبيق.",
   "It must be the WhatsApp Business app (not regular WhatsApp), updated to the latest version, and the number must have been active on it for a while — Meta refuses brand-new ones."],
  ["الميزة دي من Meta ومش متاحة لكل الدول والأرقام. لو رفضت، اربط رقم جديد أو اطلب «سيبها علينا».",
   "This Meta feature isn't available for every country and number. If it's refused, connect a new number or use «Leave it to us»."],
  ["افتح تطبيق WhatsApp Business على موبايلك مرة كل 14 يوم على الأقل — لو اتقفل أكتر من كده Meta بتفصل الربط.",
   "Open the WhatsApp Business app on your phone at least once every 14 days — otherwise Meta disconnects it."],
  ["البوت بيرد فوراً. لو رديت انت من الموبايل، البوت بيسكت في المحادثة دي لحد 12 ساعة، وردّك بيظهر في صندوق المحادثات.",
   "The bot replies instantly. When you reply from your phone, the bot goes quiet in that chat for up to 12 hours, and your reply shows in the inbox."],
  ["بعض مزايا التطبيق ممكن تتقفل أو تتغيّر بعد الربط (زي قوايم البث) — Meta بتعرض التفاصيل في النافذة قبل ما توافق.",
   "Some app features may be limited after connecting (such as broadcast lists) — Meta shows the details in the window before you agree."],
  ["المحادثات القديمة بتفضل على موبايلك ومش بتتنقل للمنصة. رسايل البوت بتتحاسب على حسابك في Meta، ورسايلك من الموبايل مجانية.",
   "Old chats stay on your phone and aren't copied to the platform. Bot messages are billed to your Meta account; messages you send from the phone are free."],
];

function WaOneTapTop({ cfg }) {
  const [name, setName] = useState("");
  const [tpl, setTpl] = useState("customer_service");
  const [coexist, setCoexist] = useState(false);
  const [agree, setAgree] = useState(false);
  const cur = useRef(null);
  cur.current = { name: name.trim(), template: tpl, coexist };
  const { state, start } = useWaSignup(cfg, () => cur.current);
  const MODES = [
    [false, bi("رقم جديد للبوت", "A new number for the bot")],
    [true, bi("رقمي شغّال على واتساب بزنس", "My number is on WhatsApp Business")],
  ];

  return (
    <Card id="wa-onetap" className={WA_CARD}>
      <WaHead />
      <div role="radiogroup" aria-label={bi("نوع الرقم", "Number type")}
           className="mt-4 inline-flex flex-wrap gap-1 rounded-xl bg-black/25 p-1
                      shadow-[inset_0_0_0_1px_rgb(255_255_255/0.08)]">
        {MODES.map(([v, label]) => (
          <button key={String(v)} type="button" role="radio" aria-checked={coexist === v}
                  onClick={() => { setCoexist(v); setAgree(false); }}
                  className={"rounded-lg px-3.5 py-2 text-[13px] font-bold transition-colors " +
                             (coexist === v ? "bg-[#25D366]/20 text-ink shadow-[inset_0_0_0_1px_rgb(37_211_102/0.5)]"
                                            : "text-ink-3 hover:text-ink")}>
            {label}
          </button>
        ))}
      </div>

      {coexist && (
        <div className="mt-4 rounded-xl bg-yellow-400/[0.06] p-4 shadow-[inset_0_0_0_1px_rgb(250_204_21/0.28)]">
          <b className="flex items-center gap-2 text-[13.5px] text-ink">
            <Icon name="shield" size={15} className="text-yellow-300" />
            {bi("الرقم هيفضل شغّال على موبايلك والبوت يرد معاك — اقرأ دول الأول:",
                "Your number keeps working on your phone while the bot replies — read these first:")}
          </b>
          <ul className="mt-2.5 mb-0 flex list-none flex-col gap-1.5 p-0">
            {COEXIST_NOTES.map(([ar, en], i) => (
              <li key={i} className="flex items-start gap-2 text-[12.5px] leading-relaxed text-ink-2">
                <span className="mt-[7px] size-1.5 shrink-0 rounded-full bg-yellow-300/80" />
                {bi(ar, en)}
              </li>
            ))}
          </ul>
          <label className="mt-3 flex cursor-pointer items-center gap-2 text-[13px] font-bold text-ink">
            <input type="checkbox" checked={agree} onChange={(e) => setAgree(e.target.checked)}
                   className="size-4 accent-[#25D366]" />
            {bi("قريت وفاهم", "I've read and understood")}
          </label>
        </div>
      )}

      <form onSubmit={(e) => { e.preventDefault(); start(); }}
            className="mt-5 grid grid-cols-1 gap-3 sm:grid-cols-[minmax(0,1fr)_220px_auto] sm:items-end">
        <Field label={t("biz_name")}>
          <Input value={name} onChange={(e) => setName(e.target.value)} required maxLength={60}
                 placeholder={t("eg_cafe")} />
        </Field>
        <Field label={t("bot_type")}>
          <Select value={tpl} onChange={(e) => setTpl(e.target.value)}>
            {BY.templates.map((x) => <option key={x.k} value={x.k}>{x.label}</option>)}
          </Select>
        </Field>
        <Btn variant="green" icon="link" type="submit"
             disabled={state.busy || !name.trim() || (coexist && !agree)}>
          {state.busy ? bi("جارٍ الربط…", "Connecting…") : bi("اربط رقمي الآن", "Connect my number")}
        </Btn>
      </form>
      {!coexist && (
        <p className="mt-3 mb-0 text-[12px] leading-relaxed text-ink-3">
          <Icon name="shield" size={12} className="me-1 align-[-2px]" />
          {bi("الرقم لازم يكون مش شغّال على أي تطبيق واتساب. رقمك شغّال على واتساب بزنس ومش عايز تسيبه؟ اختار «رقمي شغّال على واتساب بزنس». رسايل رقمك بتتحاسب على حسابك في Meta مباشرة.",
              "The number must not be active on any WhatsApp app. Your number is on WhatsApp Business and you want to keep it? Choose «My number is on WhatsApp Business». Your number's messages are billed to your own Meta account.")}
        </p>
      )}
      {state.msg && (
        <p role="status" aria-live="polite"
           className={"mt-3 mb-0 text-[13px] font-bold " +
                      (state.ok === false ? "text-red-300" : state.ok ? "text-au-teal" : "text-ink-2")}>
          {state.msg}{" "}
          {state.upgrade && <a href={BY.urls.pricing} className="text-au-cyan underline">{t("brain_upgrade")}</a>}
        </p>
      )}
    </Card>
  );
}

/* نفس الكارت مقفولاً لمن باقته بلا واتساب: معاينة مموّهة غير تفاعلية + دعوة للترقية.
   لا يحمل أي إعدادات Meta — الخادم لا يرسلها أصلاً لهذه الباقات. */
function WaOneTapLocked() {
  const ghost = "h-[46px] rounded-xl bg-white/[0.06] shadow-[inset_0_0_0_1px_rgb(255_255_255/0.1)]";
  return (
    <Card id="wa-onetap" className={WA_CARD}>
      <WaHead locked />
      <div className="relative mt-5 overflow-hidden rounded-2xl">
        {/* المعاينة المموّهة: نفس شكل النموذج الحقيقي، غير تفاعلية */}
        <div aria-hidden="true"
             className="pointer-events-none grid select-none grid-cols-1 gap-3 p-1 blur-[4px]
                        sm:grid-cols-[minmax(0,1fr)_220px_170px] sm:items-end">
          <div>
            <div className="mb-1.5 h-3 w-24 rounded bg-white/25" />
            <div className={ghost} />
          </div>
          <div>
            <div className="mb-1.5 h-3 w-16 rounded bg-white/25" />
            <div className={ghost} />
          </div>
          <div className="h-[46px] rounded-xl bg-[linear-gradient(100deg,#5EEAD4,#2DD4A7)] opacity-80" />
        </div>
        <div className="absolute inset-0 flex flex-wrap items-center justify-center gap-3 p-2 text-center
                        bg-[rgb(7_9_15/0.45)] backdrop-blur-[1px]">
          <span className="grid size-10 shrink-0 place-items-center rounded-full bg-white/10 text-ink
                           shadow-[inset_0_0_0_1px_rgb(255_255_255/0.2)]">
            <Icon name="lock" size={18} />
          </span>
          <span className="text-[13.5px] font-bold text-ink">
            {bi("متاحة في باقات واتساب — رقّي باقتك وابدأ في دقيقة", "Included in WhatsApp plans — upgrade and start in a minute")}
          </span>
          <Btn sm variant="green" icon="crown" href={BY.urls.pricing}>{bi("شوف باقات واتساب", "See WhatsApp plans")}</Btn>
        </div>
      </div>
    </Card>
  );
}

/* «سيبها علينا»: خطوات Meta صعبة على غير التقنيين، والربط مشمول في باقات واتساب.
   يُرسل بـ fetch لا بنموذج لأنه داخل نموذج الإنشاء (النماذج لا تتداخل) — ولذلك حقوله
   بلا name ولا required: لا تُرسَل مع البوت ولا تعطّل إنشاءه، وEnter فيها لا يُنشئ بوتاً. */
function WaAssist() {
  const [open, setOpen] = useState(false);
  const [f, setF] = useState({ business: "", number: "", meta: "unsure", contact: "", notes: "" });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);
  const [done, setDone] = useState(P.waAssist && P.waAssist.open
    ? { id: P.waAssist.open, existing: true } : null);
  const set = (k) => (e) => setF((x) => ({ ...x, [k]: e.target.value }));
  const noEnter = (e) => { if (e.key === "Enter") e.preventDefault(); };

  async function send() {
    setErr(null);
    if (!f.business.trim() || f.number.replace(/\D/g, "").length < 8) {
      setErr(bi("اكتب اسم النشاط ورقم واتساب صحيح.", "Enter your business name and a valid WhatsApp number."));
      return;
    }
    setBusy(true);
    try {
      const r = await fetch("/whatsapp/assist", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRF-Token": BY.csrf },
        body: JSON.stringify(f),
      });
      const d = await r.json();
      if (d.ok) setDone({ id: d.id, existing: d.existing }); else setErr(d.error);
    } catch {
      setErr(bi("تعذّر الإرسال الآن — جرّب تاني.", "Could not send right now — try again."));
    }
    setBusy(false);
  }

  const box = "mb-5 rounded-xl p-4 bg-[linear-gradient(120deg,rgb(45_212_167/0.14),rgb(34_211_238/0.05))] " +
              "shadow-[inset_0_0_0_1px_rgb(45_212_167/0.35)]";
  if (done) {
    return (
      <div className={box} role="status">
        <b className="flex items-center gap-2 text-[14px] text-ink">
          <Icon name="check" size={16} className="text-au-teal" />
          {done.existing ? bi(`طلب الربط #T${done.id} مفتوح عند فريقنا`, `Your setup request #T${done.id} is open with our team`)
                         : bi(`وصل طلبك #T${done.id} لفريقنا`, `Request #T${done.id} reached our team`)}
        </b>
        <p className="mt-2 mb-3 text-[12.5px] leading-relaxed text-ink-2">
          {bi("هنكلمك في «الدعم والشكاوى» ونكمّل الخطوات معاك هناك. لما البوت يجهز هيظهر في «بوتاتي» ويوصلك إشعار — مش محتاج تكمّل الخطوات اللي تحت.",
              "We'll reach you in «Support» and finish the steps with you there. When the bot is ready it shows up in «My bots» and you get notified — no need to fill in the steps below.")}
        </p>
        <Btn sm variant="ghost" icon="chat" href={`/support#t${done.id}`}>{bi("تابع المحادثة", "Open the conversation")}</Btn>
      </div>
    );
  }
  return (
    <div className={box}>
      <b className="flex items-center gap-2 text-[14px] text-ink">
        <Icon name="users" size={16} className="text-au-teal" />
        {bi("خطوات واتساب صعبة؟ سيبها علينا", "WhatsApp steps look hard? Leave them to us")}
      </b>
      <p className="mt-2 mb-0 text-[12.5px] leading-relaxed text-ink-2">
        {bi("مشمولة في باقتك: فريقنا يربط رقمك بـ Meta بنفسه ويسلّمك البوت جاهز في «بوتاتي». هتحتاج سجل تجاري وبطاقة ضريبية ورقم للبوت.",
            "Included in your plan: our team connects your number to Meta and hands you the bot ready in «My bots». You'll need a commercial register, a tax card and a number for the bot.")}
      </p>
      <p className="mt-2 mb-0 text-[12px] leading-relaxed text-ink-3">
        <Icon name="shield" size={12} className="me-1 align-[-2px]" />
        {bi("عمرنا ما هنطلب كلمة سر فيسبوك أو كود تحقق — هنطلب بس تضيف فريقنا مسؤولاً على حساب Meta Business بتاعك، وتقدر تشيله بعد الربط.",
            "We'll never ask for your Facebook password or a verification code — only that you add our team as an admin on your Meta Business account, which you can remove afterwards.")}
      </p>
      {!open ? (
        <Btn sm icon="users" type="button" className="mt-3" onClick={() => setOpen(true)}>
          {bi("اطلب الربط من فريقنا", "Ask our team to connect it")}
        </Btn>
      ) : (
        <div className="mt-4 grid gap-3 sm:grid-cols-2">
          <Field label={bi("اسم النشاط", "Business name")}>
            <Input value={f.business} onChange={set("business")} onKeyDown={noEnter} maxLength={80}
                   placeholder={t("eg_cafe")} />
          </Field>
          <Field label={bi("رقم واتساب اللي البوت هيرد منه", "Number the bot will answer from")}>
            <Input value={f.number} onChange={set("number")} onKeyDown={noEnter} inputMode="tel" dir="ltr"
                   maxLength={20} placeholder="+20 10 0000 0000" />
          </Field>
          <Field label={bi("عندك حساب Meta Business؟", "Do you have a Meta Business account?")}>
            <Select value={f.meta} onChange={set("meta")}>
              <option value="yes">{bi("أيوه", "Yes")}</option>
              <option value="no">{bi("لأ", "No")}</option>
              <option value="unsure">{bi("مش متأكد", "Not sure")}</option>
            </Select>
          </Field>
          <Field label={`${bi("أفضل وسيلة أو وقت للتواصل", "Best way or time to reach you")} (${t("optional")})`}>
            <Input value={f.contact} onChange={set("contact")} onKeyDown={noEnter} maxLength={60} />
          </Field>
          <Field label={`${bi("ملاحظات", "Notes")} (${t("optional")})`} className="sm:col-span-2">
            <Input value={f.notes} onChange={set("notes")} onKeyDown={noEnter} maxLength={1000}
                   placeholder={bi("مثلاً: الرقم شغال حالياً على تطبيق واتساب", "e.g. the number is on the WhatsApp app today")} />
          </Field>
          {err && <p role="alert" className="m-0 text-[12.5px] font-bold text-red-300 sm:col-span-2">{err}</p>}
          <div className="flex flex-wrap gap-2 sm:col-span-2">
            <Btn sm icon="rocket" type="button" disabled={busy} onClick={send}>
              {busy ? "…" : bi("ابعت الطلب", "Send request")}
            </Btn>
            <Btn sm variant="ghost" type="button" onClick={() => setOpen(false)}>{bi("إلغاء", "Cancel")}</Btn>
          </div>
        </div>
      )}
    </div>
  );
}

/* معالج إنشاء البوت — التوكن أولاً لأنه أصعب خطوة على غير التقنيين */
function CreateWizard({ collapsed = false }) {
  // مغلق افتراضياً: حمولة بلا الحقل لا تفتح ميزة مدفوعة (والخادم يرفض على أي حال)
  const waAllowed = P.waAllowed === true;
  const [channel, setChannel] = useState("telegram");
  const [status, setStatus] = useState(null);   // {ok, text}
  const timer = useRef(null);

  function checkToken(e) {
    const v = e.target.value.trim();
    clearTimeout(timer.current);
    if (!v) return setStatus(null);
    if (v.length < 20) return setStatus({ ok: null, text: bi("الصق التوكن كامل زي ما BotFather بعته", "Paste the full token exactly as BotFather sent it") });
    setStatus({ ok: null, text: bi("جاري التحقق…", "Checking…") });
    timer.current = setTimeout(async () => {
      try {
        const r = await fetch("/api/validate-token", {
          method: "POST",
          headers: { "Content-Type": "application/json", "X-CSRF-Token": BY.csrf },
          body: JSON.stringify({ token: v }),
        });
        const d = await r.json();
        setStatus(d.ok ? { ok: true, text: `@${d.username} — ${d.name}` } : { ok: false, text: d.error });
      } catch {
        setStatus({ ok: null, text: bi("تعذّر التحقق الآن — تقدر تكمّل عادي", "Could not verify now — you can still continue") });
      }
    }, 600);
  }

  const steps = [
    {
      n: 1, title: bi("اختر المنصة", "Platform"),
      body: (
        <>
          <div className="flex flex-wrap gap-4">
            <label className="flex cursor-pointer items-center gap-2 text-[14px]">
              <input type="radio" name="channel" value="telegram" checked={channel === "telegram"}
                     onChange={(e) => setChannel(e.target.value)} />
              <img src="/static/Telegram.svg.png" alt="Telegram" className="size-4 object-contain inline-block" /> Telegram
            </label>
            <label className={"flex items-center gap-2 text-[14px] " +
                              (waAllowed ? "cursor-pointer" : "cursor-not-allowed text-ink-3")}
                   title={waAllowed ? undefined : bi("ميزة مدفوعة — رقّي باقتك", "Paid feature — upgrade your plan")}>
              <input type="radio" name="channel" value="whatsapp" disabled={!waAllowed}
                     checked={channel === "whatsapp"} onChange={(e) => setChannel(e.target.value)} />
              <img src="/static/whatsapp.png" alt="WhatsApp"
                   className={"size-4 object-contain inline-block " + (waAllowed ? "" : "opacity-50 grayscale")} /> WhatsApp
              {!waAllowed && (
                <span className="inline-flex items-center gap-1 rounded-full bg-amber-400/15 px-2 py-0.5
                                 text-[11.5px] font-extrabold text-amber-200">
                  <Icon name="lock" size={12} />{bi("مدفوعة", "Paid")}
                </span>
              )}
            </label>
          </div>
          {!waAllowed && (
            <div role="note" className="mt-4 flex flex-wrap items-center gap-3 rounded-xl bg-amber-400/10 p-4
                                        shadow-[inset_0_0_0_1px_rgb(251_191_36/0.35)]">
              <Icon name="lock" size={18} className="shrink-0 text-amber-200" />
              <div className="min-w-0 flex-1">
                <b className="block text-[13.5px] text-ink">{bi("واتساب ميزة مدفوعة", "WhatsApp is a paid feature")}</b>
                <span className="text-[12.5px] leading-relaxed text-ink-3">
                  {bi("Meta بتحاسب على كل رسالة واتساب، عشان كده القناة متاحة في باقة «واتساب» فأعلى — ومعاها فريقنا يربطه لك بنفسه.",
                      "Meta bills every WhatsApp message, so the channel starts at the «WhatsApp» plan — and with it our team connects it for you.")}
                </span>
              </div>
              <Btn sm icon="crown" href={BY.urls.pricing}>{bi("رقّي باقتك", "Upgrade your plan")}</Btn>
            </div>
          )}
        </>
      )
    },
    {
      n: 2, title: channel === "telegram" ? t("lp_step1") : bi("بيانات واتساب", "WhatsApp Credentials"),
      desc: channel === "telegram" ? t("lp_step1_d") : bi("أدخل Phone Number ID و Access Token المؤقت من لوحة مطوري Meta", "Enter Phone Number ID and temporary Access Token from Meta Developer Console"),
      body: channel === "telegram" ? (
        <>
          <Btn variant="ghost" sm icon="link" href="https://t.me/BotFather" target="_blank" rel="noopener">
            {t("open_botfather")}
          </Btn>
          <div className="mt-4">
            <Field label={t("bot_token")}>
              <Input name="token" required autoComplete="off" spellCheck="false"
                     placeholder="123456789:AAE-xxxxxxxxxxxxxxxxxxxx" onChange={checkToken} />
            </Field>
            {status && (
              <div role="status" aria-live="polite"
                   className={"mt-2 text-[12.5px] font-bold " +
                     (status.ok === true ? "text-au-teal" : status.ok === false ? "text-red-300" : "text-ink-3")}>
                <span className="inline-flex items-center gap-1.5">
                  <Icon name={status.ok === true ? "check" : status.ok === false ? "close" : "pending"} size={14} />
                  {status.text}
                </span>
              </div>
            )}
          </div>
        </>
      ) : (
        <>
          {/* الربط بضغطة أولاً (Embedded Signup) — ثم «سيبها علينا» ثم اليدوي للمطورين */}
          {P.waEs && (
            <a href="#wa-onetap"
               className="mb-5 flex items-center gap-3 rounded-xl p-4 text-[13.5px] font-bold text-ink no-underline
                          bg-[linear-gradient(120deg,rgb(37_211_102/0.16),rgb(34_211_238/0.06))]
                          shadow-[inset_0_0_0_1px_rgb(37_211_102/0.4)]">
              <img src="/static/whatsapp.png" alt="" className="size-5 object-contain" />
              {bi("أسهل: اربط رقمك بضغطة من الكارت اللي فوق", "Easier: connect your number in one tap from the card above")}
            </a>
          )}
          {/* مشمولة في باقات واتساب: الفريق يربطها بدل العميل (باقته هو، لا صلاحية الفريق) */}
          {P.waPlan && <WaAssist />}
          {(() => {
            const manual = (
              <>
                <Btn variant="ghost" sm icon="link" href="https://developers.facebook.com/apps"
                     target="_blank" rel="noopener">
                  {bi("افتح لوحة مطوري Meta", "Open Meta developers")}
                </Btn>
                <div className="mt-4 grid gap-4 sm:grid-cols-2">
                  {/* بلا required حين يوجد الربط بضغطة: الحقول داخل قسم مطوي، والخادم يتحقق */}
                  <Field label="Phone Number ID">
                    <Input name="wa_phone_id" required={!P.waEs} autoComplete="off" spellCheck="false"
                           inputMode="numeric" placeholder="123456789012345" />
                  </Field>
                  <Field label="Access Token">
                    <Input name="wa_token" required={!P.waEs} autoComplete="off" spellCheck="false"
                           placeholder="EAAG…" />
                  </Field>
                </div>
                <p className="mt-3 text-[12.5px] text-ink-3">
                  {bi("بعد الإنشاء اضبط Webhook في Meta على العنوان أسفل، ثم شغّل البوت.",
                      "After creating it, point the Meta webhook to the URL below, then start the bot.")}
                  {" "}
                  <code className="rounded bg-white/10 px-1.5 py-0.5">
                    {typeof window !== "undefined" ? window.location.origin : ""}/wh/whatsapp
                  </code>
                </p>
              </>
            );
            return P.waEs ? (
              <details className="rounded-xl bg-black/20 p-4 shadow-[inset_0_0_0_1px_rgb(255_255_255/0.07)]">
                <summary className="cursor-pointer text-[13px] font-bold text-ink-2">
                  {bi("ربط يدوي بـ Phone Number ID و Token (للمطورين)", "Manual connection with Phone Number ID & token (developers)")}
                </summary>
                <div className="mt-4">{manual}</div>
              </details>
            ) : manual;
          })()}
        </>
      ),
    },
    {
      n: 3, title: t("lp_step2"),
      body: (
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label={t("biz_name")}>
            <Input name="name" required placeholder={t("eg_cafe")} />
          </Field>
          <Field label={t("bot_type")}>
            <Select name="template" required defaultValue="flow">
              {BY.templates.map((x) => <option key={x.k} value={x.k}>{x.label}</option>)}
            </Select>
          </Field>
        </div>
      ),
    },
    {
      n: 4, title: t("owner_id_lbl"), desc: t("owner_id_tip"), optional: true,
      body: (
        <div className="flex flex-wrap items-center gap-2.5">
          <Input name="owner_chat_id" placeholder="123456789" inputMode="numeric"
                 autoComplete="off" className="max-w-[240px]" />
          <Btn variant="ghost" sm icon="link" href="https://t.me/userinfobot" target="_blank" rel="noopener">
            {t("get_my_id")}
          </Btn>
        </div>
      ),
    },
  ];

  const form = (
      <Form action={BY.urls.botCreate}>
        {steps.map((s, i) => (
          <div key={s.n}
               className={"flex gap-4 py-6 " + (i ? "shadow-[inset_0_1px_0_rgb(255_255_255/0.07)]" : "pt-0")}>
            <span className="grid size-9 shrink-0 place-items-center rounded-xl text-[15px] font-extrabold text-au-cyan
                             bg-[linear-gradient(150deg,rgb(124_108_246/0.25),rgb(34_211_238/0.1))]
                             shadow-[inset_0_0_0_1px_rgb(255_255_255/0.09)]">{s.n}</span>
            <div className="min-w-0 flex-1">
              <h3 className="m-0 text-[15px] font-extrabold text-ink">
                {s.title}
                {s.optional && <span className="ms-2 text-[12.5px] font-bold text-ink-3">({t("optional")})</span>}
              </h3>
              {s.desc && <p className="mt-1.5 mb-3.5 text-[12.5px] leading-relaxed text-ink-3">{s.desc}</p>}
              <div className={s.desc ? "" : "mt-3.5"}>{s.body}</div>
            </div>
          </div>
        ))}
        <div className="pt-2">
          <Btn icon="sparkles" type="submit">{t("create_btn")}</Btn>
        </div>
      </Form>
  );

  /* مع الإنشاء بضغطة يصير النموذج اليدوي (توكن BotFather) خياراً ثانياً مطويّاً —
     ويبقى الطريق الوحيد لواتساب وللحالات التي لا يعمل فيها الإنشاء بضغطة. */
  if (collapsed) {
    return (
      <Card id="create">
        <details>
          <summary className="flex cursor-pointer list-none items-center gap-2 text-[15px] font-extrabold text-ink
                              [&::-webkit-details-marker]:hidden">
            <Icon name="plus" size={17} className="text-au-cyan" />{t("onetap_manual")}
            <span className="ms-auto text-[12px] font-bold text-ink-3">WhatsApp · BotFather</span>
          </summary>
          <div className="mt-5">{form}</div>
        </details>
      </Card>
    );
  }
  return (
    <Card id="create">
      <SectionTitle icon="plus">{t("create_bot")}</SectionTitle>
      {form}
    </Card>
  );
}

/* ------------------------------------------------------------------ البدء */
/* لوحة فارغة بلا إرشاد هي أكبر سبب لتوقّف المستخدم الجديد: أصعب خطوة (التوكن)
   تحدث خارج المنصة بالكامل، فلا تكفي أن تُشرح داخل النموذج بعد أن يصل إليه.
   لذلك تسبق هذه البطاقة كل شيء، وتختفي وحدها حين تكتمل الخطوات. */
function FirstBotGuide() {
  const steps = [
    { k: "ob_s1", d: "ob_s1_d", icon: "link", extra: (
        <>
          <Btn variant="ghost" sm icon="link" href="https://t.me/BotFather"
               target="_blank" rel="noopener" className="mt-3">{t("open_botfather")}</Btn>
          <div className="mt-3 text-[12px] text-ink-3">
            {t("ob_s1_hint")}{" "}
            <code className="rounded bg-black/30 px-1.5 py-0.5 text-au-cyan" dir="ltr">
              123456789:AAE-xxxxxxxx
            </code>
          </div>
        </>
      ) },
    { k: "ob_s2", d: "ob_s2_d", icon: "key" },
    { k: "ob_s3", d: "ob_s3_d", icon: "play" },
  ];
  return (
    <Card className="mb-6 bg-[linear-gradient(120deg,rgb(124_108_246/0.18),rgb(34_211_238/0.06))]">
      <div className="mb-6 text-center">
        <h2 className="m-0 text-[20px] font-extrabold text-ink">{t("ob_title")}</h2>
        <p className="mx-auto mt-2 mb-0 max-w-[420px] text-[13.5px] text-ink-3">{t("ob_sub")}</p>
      </div>
      <div className="grid gap-5 md:grid-cols-3">
        {steps.map((s, i) => (
          <div key={s.k}
               className="rounded-2xl bg-white/[0.03] p-5 shadow-[inset_0_0_0_1px_rgb(255_255_255/0.08)]">
            <div className="flex items-center gap-2.5">
              <span className="grid size-8 shrink-0 place-items-center rounded-xl text-[14px] font-extrabold
                               text-[#07090F] bg-[linear-gradient(100deg,#8FE9FF,#B9AFFF)]">{i + 1}</span>
              <Icon name={s.icon} size={16} className="text-au-cyan" />
            </div>
            <h3 className="mt-3 mb-1.5 text-[14.5px] font-extrabold text-ink">{t(s.k)}</h3>
            <p className="m-0 text-[12.5px] leading-relaxed text-ink-3">{t(s.d)}</p>
            {s.extra}
          </div>
        ))}
      </div>
      <div className="mt-6 text-center">
        <Btn icon="plus" href="#create">{t("ob_start_here")}</Btn>
      </div>
    </Card>
  );
}

/* بعد أول بوت: بوت موجود ≠ بوت يعمل. هذه الثلاث هي الفجوة بينهما. */
function FirstRunChecklist({ ob }) {
  // بوت الفلو يحيّي من «باني المحادثة» لا من الإعدادات — الإرشاد يقول أين بالضبط
  const map = { greeting: ["ob_greeting", ob.flowBot ? "ob_greeting_flow_d" : "ob_greeting_d"],
                run: ["ob_run", "ob_run_d"],
                try: ["ob_try", "ob_try_d"] };
  const steps = ob.steps || [];
  const done = steps.filter((s) => s.done).length;
  return (
    <Card className="mb-6">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="m-0 flex items-center gap-2 text-[17px] font-extrabold text-ink">
            <Icon name="rocket" size={18} className="text-au-cyan" />{t("ob_next_title")}
          </h2>
          <p className="mt-1.5 mb-0 text-[13px] text-ink-3">
            {t("ob_next_sub").replace("{n}", ob.botName || "")}
          </p>
        </div>
        <Pill tone="mute">
          {t("ob_progress").replace("{a}", done).replace("{b}", steps.length)}
        </Pill>
      </div>

      <div className="mb-5 h-1.5 w-full overflow-hidden rounded-full bg-white/10"
           role="progressbar" aria-valuenow={done} aria-valuemin={0} aria-valuemax={steps.length}>
        <div className="h-full rounded-full bg-[linear-gradient(90deg,#8FE9FF,#B9AFFF)]
                        transition-[width] duration-700 ease-[cubic-bezier(0.16,1,0.3,1)]"
             style={{ width: `${steps.length ? (done / steps.length) * 100 : 0}%` }} />
      </div>

      <ul className="m-0 flex list-none flex-col gap-3 p-0">
        {steps.map((s) => {
          const [title, desc] = map[s.k] || [s.k, s.k];
          return (
            <li key={s.k} className="flex items-start gap-3">
              <span className={"mt-0.5 grid size-6 shrink-0 place-items-center rounded-full " +
                (s.done ? "bg-au-teal/20 text-au-teal"
                        : "bg-white/[0.06] text-ink-3 shadow-[inset_0_0_0_1px_rgb(255_255_255/0.12)]")}>
                <Icon name={s.done ? "check" : "clock"} size={13} />
              </span>
              <div className="min-w-0 flex-1">
                <div className={"text-[14px] font-extrabold " +
                                (s.done ? "text-ink-3 line-through" : "text-ink")}>{t(title)}</div>
                {!s.done && <div className="mt-0.5 text-[12.5px] text-ink-3">{t(desc)}</div>}
                {/* «جرّبه بنفسك» يفتح البوت مباشرة بدل البحث عنه في تليجرام */}
                {!s.done && s.k === "try" && ob.botUsername && ob.channel !== "whatsapp" && (
                  <Btn className="mt-2" variant="green" sm icon="play" target="_blank" rel="noopener"
                       href={`https://t.me/${ob.botUsername}?start=src-link`}>{t("live_open")}</Btn>
                )}
              </div>
              {s.done && <span className="text-[12px] font-bold text-au-teal">{t("ob_step_done")}</span>}
            </li>
          );
        })}
      </ul>

      <div className="mt-5">
        <Btn variant="ghost" sm icon="settings" href={`/bot/${ob.botId}`}>{t("ob_open_bot")}</Btn>
      </div>
    </Card>
  );
}

/* ماسنجر + إنستجرام — المرحلة الأولى للفريق وحده (/meta/connect يفرض الدور في الخادم).
   Page ID + توكن (صفحة، أو مستخدم من Graph API Explorer يُحوَّل لتوكن صفحة دائم في الخادم).
   التوكن يُرسل مرة ولا يعود للمتصفح. الطرح للعملاء = نافذة Meta بضغطة مثل واتساب لاحقاً. */
function MetaConnect() {
  const [f, setF] = useState({ page_id: "", token: "", name: "", template: "customer_service",
                               messenger: true, instagram: true });
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState(null);
  const set = (k) => (e) => setF((x) => ({ ...x, [k]: e.target.type === "checkbox" ? e.target.checked : e.target.value }));

  async function send(e) {
    e.preventDefault();
    setBusy(true); setMsg(null);
    try {
      const r = await fetch("/meta/connect", {
        method: "POST", credentials: "same-origin",
        headers: { "Content-Type": "application/json", "X-CSRF-Token": BY.csrf },
        body: JSON.stringify(f),
      });
      const d = await r.json();
      if (d.ok) { window.location.href = d.url; return; }
      setMsg(d.error || `HTTP ${r.status}`);
    } catch {
      setMsg(bi("مفيش اتصال بالسيرفر — جرّب تاني.", "No connection to the server — try again."));
    }
    setBusy(false);
  }

  return (
    <Card className="mb-6 bg-[linear-gradient(125deg,rgb(0_132_255/0.14),rgb(225_48_108/0.12))]
                     shadow-[inset_0_0_0_1px_rgb(0_132_255/0.3)]">
      <h2 className="m-0 flex flex-wrap items-center gap-2.5 text-[19px] font-extrabold text-ink">
        <Icon name="chat" size={22} className="text-[#4DA3FF]" />
        {bi("بوت ماسنجر وإنستجرام", "Messenger & Instagram bot")}
        <Pill tone="mute">{bi("تجريبي — للفريق فقط", "Beta — team only")}</Pill>
      </h2>
      <p className="mt-1.5 mb-4 max-w-[680px] text-[13px] leading-relaxed text-ink-3">
        {bi("الصق Page ID وتوكن الصفحة (أو توكن مستخدم من Graph API Explorer — السيرفر يحوّله لتوكن صفحة دائم). بيتعمل بوت لماسنجر و/أو لحساب إنستجرام الاحترافي المربوط بالصفحة، بنفس عقل البوت وصندوق الوارد.",
            "Paste the Page ID and a Page token (or a user token from Graph API Explorer — the server turns it into a permanent Page token). A bot is created for Messenger and/or the Instagram professional account linked to the Page, with the same bot brain and inbox.")}
      </p>
      <form onSubmit={send} className="grid gap-3 sm:grid-cols-2">
        <Field label="Page ID">
          <Input value={f.page_id} onChange={set("page_id")} required inputMode="numeric" dir="ltr"
                 autoComplete="off" spellCheck="false" placeholder="1234567890" />
        </Field>
        <Field label={bi("التوكن", "Token")}>
          <Input type="password" value={f.token} onChange={set("token")} required dir="ltr"
                 autoComplete="off" spellCheck="false" placeholder="EAA…" />
        </Field>
        <Field label={t("biz_name")}>
          <Input value={f.name} onChange={set("name")} maxLength={60} placeholder={bi("اسم الصفحة لو فاضي", "Page name if empty")} />
        </Field>
        <Field label={t("bot_type")}>
          <Select value={f.template} onChange={set("template")}>
            {BY.templates.map((x) => <option key={x.k} value={x.k}>{x.label}</option>)}
          </Select>
        </Field>
        <div className="flex flex-wrap items-center gap-5 sm:col-span-2">
          {[["messenger", "Messenger"], ["instagram", "Instagram"]].map(([k, label]) => (
            <label key={k} className="flex cursor-pointer items-center gap-2 text-[13.5px] font-bold text-ink">
              <input type="checkbox" checked={f[k]} onChange={set(k)} className="size-4 accent-[#4DA3FF]" />{label}
            </label>
          ))}
          <Btn icon="link" type="submit" className="ms-auto" disabled={busy || !f.page_id || !f.token}>
            {busy ? bi("جارٍ الربط…", "Connecting…") : bi("اربط الصفحة", "Connect the Page")}
          </Btn>
        </div>
      </form>
      {msg && <p role="alert" className="mt-3 mb-0 text-[13px] font-bold text-red-300">{msg}</p>}
      <p className="mt-3 mb-0 text-[12px] leading-relaxed text-ink-3">
        <Icon name="shield" size={12} className="me-1 align-[-2px]" />
        {bi("ماسنجر وإنستجرام بيسمحوا بالرد الحر لمدة 24 ساعة بعد آخر رسالة من العميل بس — البث والرد اليدوي بيلتزموا بده تلقائياً.",
            "Messenger and Instagram allow free replies only within 24 hours of the customer's last message — broadcasts and manual replies follow this automatically.")}
      </p>
    </Card>
  );
}

export default function Dashboard() {
  const { bots = [], total = {}, onboarding = {}, oneTap = {} } = P;
  const stage = onboarding.stage;
  const fresh = stage === "first_bot";
  const quick = !!oneTap.available;
  return (
    <>
      <PageHead
        title={`${t("welcome_user")} ${BY.user.name}`}
        sub={t("dash_sub")}
        actions={<Btn icon="plus" href={quick ? "#onetap" : "#create"}>{t("create_bot")}</Btn>}
      />

      {/* الإنشاء بضغطة أولاً — أسهل طريق لغير التقنيين. واتساب في الأول: مفتوح لباقات واتساب،
          ومقفول بتمويه لغيرها كدعوة للترقية */}
      {P.waEs && <WaOneTapTop cfg={P.waEs} />}
      {!P.waEs && P.waEsLocked && <WaOneTapLocked />}
      {quick && <OneTapCreate />}
      {P.metaConnect && <MetaConnect />}
      {!quick && BY.user.role === "admin" && (
        <Card className="mb-6 flex items-start gap-3 bg-yellow-400/[0.06] shadow-[inset_0_0_0_1px_rgb(250_204_21/0.25)]">
          <Icon name="bolt" size={18} className="mt-0.5 text-yellow-300" />
          <p className="m-0 text-[13px] leading-relaxed text-ink-2">{t("onetap_admin_hint")}</p>
        </Card>
      )}

      {/* بلا إيميل لا استرجاع للحساب ولا إيصالات — مطالبة لطيفة لا إجبار */}
      {BY.user.hasEmail === false && (
        <Card className="mb-6 flex flex-wrap items-center justify-between gap-4">
          <span className="flex items-center gap-2 text-[14px] text-ink">
            <Icon name="shield" size={16} className="text-au-cyan" />{t("email_prompt")}
          </span>
          <Btn sm variant="ghost" icon="settings" href={BY.urls.account}>{t("add_email")}</Btn>
        </Card>
      )}

      {fresh && !quick && <FirstBotGuide />}
      {stage === "first_run" && <FirstRunChecklist ob={onboarding} />}

      {/* أربعة أصفار في وجه من لم ينشئ بوتاً بعد ليست معلومة — هي إحباط. */}
      {!fresh && (
        <Grid cols={4} className="mb-7">
          <Stat icon="users"    value={total.subscribers} label={t("stat_subs")} />
          <Stat icon="store"    value={total.orders}      label={t("stat_orders")} />
          <Stat icon="calendar" value={total.bookings}    label={t("stat_bookings")} />
          <Stat icon="wallet"   value={total.revenue}     label={t("stat_revenue")} />
        </Grid>
      )}

      {!fresh && (
        <Card className="mb-6">
          <SectionTitle icon="bot" extra={<span className="text-[13px] text-ink-3">{bots.length}</span>}>
            {t("my_bots")}
          </SectionTitle>
          {bots.length ? (
            <div className="grid gap-4 md:grid-cols-2">
              {bots.map((b, i) => <BotCard key={b.id} b={b} i={i} />)}
            </div>
          ) : (
            <Empty icon="bot" title={t("no_bots")} text={t("lp_step1_d")}
                   action={<Btn icon="plus" href="#create">{t("create_bot")}</Btn>} />
          )}
        </Card>
      )}

      <div className="mb-6"><CreateWizard collapsed={quick} /></div>

      <Card className="flex flex-wrap items-center justify-between gap-4
                       bg-[linear-gradient(120deg,rgb(124_108_246/0.16),rgb(34_211_238/0.06))]">
        <div>
          <h2 className="m-0 flex items-center gap-2 text-[17px] font-extrabold text-ink">
            <Icon name="sparkles" size={18} className="text-au-cyan" />{t("custom_bot")}
          </h2>
          <p className="mt-1.5 mb-0 text-[13px] text-ink-3">{t("custom_bot_desc")}</p>
        </div>
        <Btn icon="rocket" href={BY.urls.requestBot}>{t("request_custom")}</Btn>
      </Card>
    </>
  );
}
