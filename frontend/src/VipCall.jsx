import { useState } from "react";

/* باقة «راحة البال» (VIP): كارت عريض تحت شبكة الباقات بزرّ «احجز مكالمة» بدل الدفع المباشر.
   مشترك بين صفحة الأسعار العامة وصفحة الباقات في اللوحة — لذلك `Icon` و`BY` يُمرَّران ولا
   يُستوردان من أحد الطقمين (ui.jsx / kit.jsx). الطلب يذهب إلى /vip/request: تذكرة vip_call
   للمسجَّل، أو عميل محتمل في البوت الرسمي للزائر، وتنبيه فوري للمبيعات. بلا Calendly. */
export default function VipCall({ plan, BY, Icon }) {
  const L = (ar, en) => (BY.lang === "en" ? en : ar);
  const feats = plan.features || (BY.lang === "en" ? plan.features_en : plan.features_ar) || [];
  const [open, setOpen] = useState(false);
  const [f, setF] = useState({ name: "", company: "", phone: "", notes: "", consent: false });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);
  const [done, setDone] = useState(false);
  const set = (k) => (e) => setF((x) => ({ ...x, [k]: k === "consent" ? e.target.checked : e.target.value }));
  const input = "w-full rounded-xl bg-black/30 px-4 py-3 text-[14px] text-ink placeholder:text-ink-4 " +
                "shadow-[inset_0_0_0_1px_rgb(255_255_255/0.12)] outline-none focus:shadow-[inset_0_0_0_2px_rgb(143_233_255/0.6)]";
  const num = (v) => Number(v || 0).toLocaleString("en-US");

  async function send(e) {
    e.preventDefault();
    setBusy(true); setErr(null);
    try {
      const r = await fetch("/vip/request", {
        method: "POST", credentials: "same-origin",
        headers: { "Content-Type": "application/json", "X-CSRF-Token": BY.csrf || "" },
        body: JSON.stringify(f),
      });
      const d = await r.json();
      if (d.ok) setDone(true); else setErr(d.error);
    } catch {
      setErr(L("تعذّر الإرسال — جرّب تاني.", "Could not send — try again."));
    }
    setBusy(false);
  }

  return (
    <div className="mt-6 rounded-[28px] bg-[linear-gradient(120deg,rgb(250_204_21/0.12),rgb(124_108_246/0.14)_60%,transparent)]
                    p-7 shadow-[inset_0_0_0_1px_rgb(250_204_21/0.3)] sm:p-9">
      <div className="grid gap-7 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)] lg:items-center">
        <div className="min-w-0">
          <div className="mb-2 flex flex-wrap items-center gap-2.5">
            <Icon name="crown" size={22} className="text-yellow-300" />
            <h3 className="m-0 text-[22px] font-extrabold text-ink">{plan.name || plan.name_ar}</h3>
            <span className="rounded-full bg-yellow-300/15 px-3 py-1 text-[11.5px] font-extrabold text-yellow-200">
              {L("المصانع وكبار التجار", "Factories & large merchants")}
            </span>
          </div>
          <p className="m-0 mb-4 text-[14.5px] leading-[1.8] text-ink-2">
            {L("مش فاضي تبني البوت؟ فريقنا يعمله ويشغّله بالكامل — من الردود والكتالوج لحد ربط واتساب ومراجعة الأداء كل شهر.",
               "No time to build it? Our team builds and runs the whole bot — from replies and catalog to the WhatsApp connection and a monthly performance review.")}
          </p>
          <ul className="m-0 grid list-none gap-2 p-0 sm:grid-cols-2">
            {feats.map((x, i) => (
              <li key={i} className="flex items-start gap-2 text-[13px] leading-[1.6] text-ink-2">
                <Icon name="check" size={14} className="mt-0.5 text-yellow-300" />{x}
              </li>
            ))}
          </ul>
          {plan.annual_price > 0 && (
            <p className="mt-4 mb-0 text-[13px] font-bold text-ink-3">
              {L("من", "From")} <span className="text-[17px] text-ink">{num(plan.annual_price)}</span>{" "}
              {L("ج / سنوياً", "EGP / year")}
              {plan.annual_monthly_equiv ? ` · ${L("يعادل", "≈")} ${num(plan.annual_monthly_equiv)} ${L("ج شهرياً", "EGP/month")}` : ""}
            </p>
          )}
        </div>

        <div className="min-w-0">
          {done ? (
            <p role="status" className="m-0 rounded-2xl bg-black/25 p-5 text-center text-[14.5px] font-bold text-au-teal">
              {L("وصلنا طلبك ✅ فريقنا هيتواصل معاك على واتساب قريباً.", "Got it ✅ Our team will reach you on WhatsApp soon.")}
            </p>
          ) : !open ? (
            <button type="button" onClick={() => setOpen(true)}
                    className="inline-flex w-full items-center justify-center gap-2 rounded-full bg-yellow-300 px-6 py-4 text-[15px] font-extrabold text-[#1a1400]">
              <Icon name="phone" size={17} />{L("احجز مكالمة مع فريقنا", "Book a call with our team")}
            </button>
          ) : (
            <form onSubmit={send} className="grid gap-3">
              <input className={input} value={f.name} onChange={set("name")} required maxLength={80}
                     placeholder={L("الاسم", "Name")} autoComplete="name" />
              <input className={input} value={f.company} onChange={set("company")} required maxLength={120}
                     placeholder={L("اسم الشركة / المصنع", "Company / factory")} autoComplete="organization" />
              <input className={input} value={f.phone} onChange={set("phone")} required maxLength={25} dir="ltr"
                     inputMode="tel" placeholder={L("رقم الواتساب 2010…", "WhatsApp number 2010…")} autoComplete="tel" />
              <textarea className={input + " min-h-[80px]"} value={f.notes} onChange={set("notes")} maxLength={600}
                        placeholder={L("عايز البوت يعمل إيه؟ (اختياري)", "What should the bot do? (optional)")} />
              <label className="flex cursor-pointer items-start gap-2.5 text-[12.5px] leading-[1.7] text-ink-2">
                <input type="checkbox" checked={f.consent} onChange={set("consent")} required className="mt-1 size-4 accent-yellow-300" />
                {L("أوافق على تواصل BotYalla معي على واتساب بخصوص طلبي.", "I agree that BotYalla may contact me on WhatsApp about my request.")}
              </label>
              {err && <p role="alert" className="m-0 text-[13px] font-bold text-red-300">{err}</p>}
              <button type="submit" disabled={busy}
                      className="inline-flex items-center justify-center gap-2 rounded-full bg-yellow-300 px-6 py-3.5 text-[15px] font-extrabold text-[#1a1400] disabled:opacity-60">
                <Icon name="phone" size={16} />{busy ? "…" : L("اطلب المكالمة", "Request the call")}
              </button>
            </form>
          )}
        </div>
      </div>
    </div>
  );
}
