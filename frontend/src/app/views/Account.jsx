import { useState } from "react";
import {
  BY, P, t, bi, Icon, Card, Btn, Field, Input, Select, Textarea, Form, Grid, Stat,
  Pill, Empty, PageHead, SectionTitle, Table, Tr, Td, num, fmtDate, daysLeft,
} from "../kit.jsx";

/* ------------------------------------------------------------- حسابي */
export function Account() {
  const me = P.me || {};
  const [link, setLink] = useState(null);
  const [err, setErr] = useState(null);

  async function linkTelegram() {
    setErr(null);
    try {
      const r = await fetch("/account/link-telegram", {
        method: "POST", headers: { "X-CSRF-Token": BY.csrf },
      });
      const d = await r.json();
      if (d.ok) setLink(d.link); else setErr(d.error);
    } catch { setErr(null); }
  }

  return (
    <>
      <PageHead icon="settings" title={t("account_title")} />
      <Card className="max-w-[560px]">
        <Pill tone="mute"><Icon name="shield" size={13} />{t("role_" + (me.role || "user"))}</Pill>
        <Form action="" className="mt-5">
          <Field label={t("username")} className="mb-4">
            <Input name="username" defaultValue={me.username} required minLength={3} autoComplete="username" />
          </Field>
          <Field label={t("new_password")} className="mb-5">
            <Input type="password" name="new_password" placeholder="••••••" minLength={6} autoComplete="new-password" />
          </Field>
          <div className="my-5 h-px bg-white/10" />
          <Field label={t("current_password")}
                 hint={bi("مطلوبة لتأكيد أي تعديل.", "Required to confirm any change.")}>
            <Input type="password" name="current_password" required autoComplete="current-password" />
          </Field>
          <div className="mt-6"><Btn icon="check" type="submit">{t("update_account")}</Btn></div>
        </Form>
      </Card>

      {/* قناة تنبيهات الاشتراك — بدونها لا يعلم العميل بانتهاء اشتراكه */}
      <Card className="max-w-[560px]">
        <SectionTitle icon="bot"
          extra={P.tgLinked ? <Pill tone="on" dot>{t("tg_link_ok")}</Pill>
               : P.tgFallback ? <Pill tone="warn">{t("aff_active")}</Pill>
               : <Pill tone="off">{t("tg_not_synced")}</Pill>}>
          {t("tg_link_title")}
        </SectionTitle>
        <p className="mt-0 mb-4 text-[13px] leading-relaxed text-ink-3">
          {P.tgLinked ? t("tg_link_desc")
            : P.tgFallback ? t("tg_link_via_bot")
            : t("tg_link_none")}
        </p>
        {!P.tgLinked && (
          link ? (
            <Btn variant="green" icon="play" href={link} target="_blank" rel="noopener">
              {t("tg_link_open")}
            </Btn>
          ) : (
            <Btn icon="link" type="button" onClick={linkTelegram} disabled={!P.hasPlatformBot}>
              {t("tg_link_btn")}
            </Btn>
          )
        )}
        {!P.hasPlatformBot && (
          <p className="mt-3 mb-0 text-[12.5px] text-ink-3">{t("tg_link_no_bot")}</p>
        )}
        {err && <p className="mt-3 mb-0 text-[13px] font-bold text-red-300">{err}</p>}
      </Card>
    </>
  );
}

/* ---------------------------------------------------------- إعدادات الـ AI */
export function Settings() {
  return (
    <>
      <PageHead icon="sparkles" title={t("ai_settings")} sub={t("ai_settings_sub")} />
      <Card className="mb-6 max-w-[640px]">
        <SectionTitle icon="key">{t("api_key")}</SectionTitle>
        <Form action="">
          <Field label={t("provider")} className="mb-4">
            <Select name="ai_provider" defaultValue={P.aiProvider}>
              <option value="gemini">Google Gemini 2.5 Flash</option>
              <option value="groq">Groq — Llama 3.3</option>
            </Select>
          </Field>
          <Field label={t("api_key")}
                 hint={bi("يُحفظ لكل المنصة ويُستخدم لتوليد إعدادات بوتات جميع المستخدمين. اتركه فارغاً لاستخدام المولّد الاحتياطي المجاني.",
                          "Saved platform-wide and used to generate bot settings for all users. Leave empty for the free fallback generator.")}>
            <Input name="ai_key" defaultValue={P.aiKey} placeholder={t("paste_key")} autoComplete="off" />
          </Field>
          <div className="mt-6"><Btn icon="check" type="submit">{t("save")}</Btn></div>
        </Form>
      </Card>

      <Card className="max-w-[640px]">
        <SectionTitle icon="globe">{t("how_free_key")}</SectionTitle>
        <ul className="flex flex-col gap-3 text-[14px] text-ink-2">
          <li>
            <b className="text-au-cyan">Google Gemini:</b>{" "}
            <a href="https://aistudio.google.com/apikey" target="_blank" rel="noopener"
               className="text-au-cyan underline-offset-4 hover:underline">Google AI Studio ↗</a>
            {" — "}{bi("1500 طلب/يوم مجاناً", "1,500 req/day free")}
          </li>
          <li>
            <b className="text-au-cyan">Groq:</b>{" "}
            <a href="https://console.groq.com/keys" target="_blank" rel="noopener"
               className="text-au-cyan underline-offset-4 hover:underline">console.groq.com ↗</a>
          </li>
        </ul>
      </Card>
    </>
  );
}

/* ---------------------------------------------------------------- الفواتير */
export function Billing() {
  const { sub = {}, pays = [], planName, names = {} } = P;
  const isAdmin = BY.user.role === "admin";
  const dl = daysLeft(sub.expires_at);
  const tone = { pending: "warn", approved: "on", rejected: "off" };
  const label = { pending: t("status_pending"), approved: t("status_approved"), rejected: t("status_rejected") };

  return (
    <>
      <PageHead icon="card" title={t("billing_title")} />

      <Card className="mb-6 flex flex-wrap items-center justify-between gap-5">
        <div>
          <div className="text-[13px] text-ink-3">{t("current_plan")}</div>
          <div className="mt-1.5 flex flex-wrap items-center gap-3 text-[24px] font-extrabold text-ink">
            {isAdmin ? <span className="hue">{t("owner_unlimited")}</span> : (
              <>
                {planName}
                {sub.status === "active"  && <Pill tone="on" dot>{t("status_active")}</Pill>}
                {sub.status === "expired" && <Pill tone="off">{t("status_expired")}</Pill>}
              </>
            )}
          </div>
          {!isAdmin && sub.expires_at && sub.plan !== "free" && (
            <div className="mt-2 flex flex-wrap items-center gap-2 text-[13px] text-ink-3">
              <Icon name="clock" size={13} />
              {t("expires_on")}: <b className="text-ink-2">{fmtDate(sub.expires_at)}</b>
              {sub.status === "active" && (
                <span className={dl <= 5 ? "text-red-300" : "text-au-teal"}>({dl} {t("days_left")})</span>
              )}
              <span>· {t("renews_monthly")}</span>
            </div>
          )}
        </div>
        <Btn icon="bolt" href={BY.urls.pricing}>{t("nav_pricing")}</Btn>
      </Card>

      <Card>
        <SectionTitle icon="clock">{t("payment_history")}</SectionTitle>
        {pays.length ? (
          <Table head={["#", t("col_plan"), t("col_amount"), t("col_method"), t("col_status")]}>
            {pays.map((x) => (
              <Tr key={x.id}>
                <Td className="tnum">{x.id}</Td>
                <Td>{names[x.plan] || x.plan}</Td>
                <Td className="tnum">{num(x.amount)} {t("egp")}</Td>
                <Td>{x.method}</Td>
                <Td><Pill tone={tone[x.status]}>{label[x.status]}</Pill></Td>
              </Tr>
            ))}
          </Table>
        ) : <Empty icon="card" title={t("no_payments")} />}
      </Card>
    </>
  );
}

/* ----------------------------------------------------------------- الباقات */
export function Pricing() {
  const { plans = [], sub = {} } = P;
  const icons = { free: "bot", pro: "bolt", business: "crown" };
  return (
    <>
      <div className="mb-10 text-center">
        <h1 className="m-0 text-[clamp(26px,4vw,40px)] font-extrabold tracking-tight text-ink">
          {t("pricing_title")}
        </h1>
        <p className="mx-auto mt-3 max-w-[520px] text-[15px] text-ink-3">{t("pricing_sub")}</p>
      </div>

      <div className="grid items-start gap-5 lg:grid-cols-3">
        {plans.map((p) => {
          const current = sub.plan === p.id && sub.status === "active";
          const hot = p.id === "pro";
          const feats = BY.lang === "ar" ? p.features_ar : p.features_en;
          return (
            <Card key={p.id} spot
                  className={"!overflow-visible text-center transition-transform duration-500 hover:-translate-y-1 " +
                    (hot ? "shadow-[inset_0_0_0_1px_rgb(124_108_246/0.55),0_30px_70px_-30px_rgb(0_0_0/0.9)]" : "")}>
              {hot && (
                <span className="absolute -top-3 start-1/2 -translate-x-1/2 rounded-full px-4 py-1 text-[11.5px]
                                 font-extrabold text-[#07090F] rtl:translate-x-1/2
                                 bg-[linear-gradient(100deg,#8FE9FF,#B9AFFF)]
                                 shadow-[0_8px_20px_-6px_rgb(124_108_246/0.8)]">
                  {t("most_popular")}
                </span>
              )}
              <Icon name={icons[p.id] || "bot"} size={28} className="mx-auto text-au-cyan" />
              <h2 className="mt-3 mb-3 text-[19px] font-extrabold text-ink">
                {p.name}
              </h2>
              <div className="mb-6">
                {p.price === 0 ? (
                  <span className="hue text-[22px] font-extrabold">{t("free_forever")}</span>
                ) : (
                  <>
                    {p.has_discount && (
                      <div className="mb-1 flex items-center justify-center gap-2">
                        <span className="text-[16px] text-ink-3 line-through">{p.list_price}</span>
                        <Pill tone="on">-{Math.round(p.discount_pct)}%</Pill>
                      </div>
                    )}
                    <div className="text-[34px] font-extrabold leading-none text-ink">
                      {p.price}
                      <span className="text-[15px] font-bold text-ink-3">{t("egp")}{t("per_month")}</span>
                    </div>
                  </>
                )}
              </div>
              <ul className="mb-7 flex flex-col gap-2.5 text-start">
                {feats.map((f, i) => (
                  <li key={i} className="flex items-start gap-2.5 text-[14px] text-ink-2">
                    <Icon name="check" size={16} className="mt-0.5 text-au-teal" />{f}
                  </li>
                ))}
              </ul>
              {current ? <Pill tone="on" dot>{t("current_plan")}</Pill>
                : p.id === "free" ? <span className="text-[13px] text-ink-3">{t("free_forever")}</span>
                : <Btn block icon="card" href={`/subscribe/${p.id}`}>{t("subscribe_btn")}</Btn>}
            </Card>
          );
        })}
      </div>

      <p className="mt-10 flex items-center justify-center gap-2 text-[13px] text-ink-3">
        <Icon name="shield" size={14} />{t("pay_secure_note")}
      </p>
    </>
  );
}

/* ---------------------------------------------------------------- الاشتراك */
export function Subscribe() {
  const { plan = {}, plat = {}, qr, action, planId } = P;
  const [copied, setCopied] = useState("");
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);
  // التسعيرة الابتدائية من الخادم؛ تُحدَّث عند تطبيق كود
  const [q, setQ] = useState({
    listPrice: plan.list_price ?? plan.price,
    total: plan.price,
    planDiscountPct: plan.discount_pct || 0,
    promoCode: null, promoCut: 0,
  });

  async function check() {
    setBusy(true); setErr(null);
    try {
      const r = await fetch("/api/promo/check", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRF-Token": BY.csrf },
        body: JSON.stringify({ plan: planId, code }),
      });
      const d = await r.json();
      if (d.ok) {
        setQ({ listPrice: d.listPrice, total: d.total, planDiscountPct: d.planDiscountPct,
               promoCode: d.promoCode, promoCut: d.promoCut });
        setErr(d.error || null);
      }
    } catch { setErr(null); }
    setBusy(false);
  }

  const copy = (v, k) => {
    navigator.clipboard?.writeText(v).then(() => {
      setCopied(k); setTimeout(() => setCopied(""), 1400);
    });
  };
  const CopyRow = ({ v, k }) => (
    <div className="mt-2 flex items-center gap-2">
      <code className="flex-1 overflow-x-auto rounded-lg bg-black/30 px-3 py-2 text-[13px] text-au-cyan
                       shadow-[inset_0_0_0_1px_rgb(255_255_255/0.08)]">{v}</code>
      <Btn variant="ghost" sm type="button" onClick={() => copy(v, k)}
           aria-label={t("copy")}>
        <Icon name={copied === k ? "check" : "copy"} size={13} />
      </Btn>
    </div>
  );

  return (
    <>
      <PageHead icon="card" title={t("pay_title")}
        sub={`${BY.lang === "ar" ? plan.name_ar : plan.name_en} — ${plan.price} ${t("egp")}${t("per_month")}`}
        actions={<Btn variant="ghost" sm icon="back" href={BY.urls.pricing}>{t("back")}</Btn>} />

      <Card className="mb-6 bg-[linear-gradient(120deg,rgb(124_108_246/0.18),rgb(34_211_238/0.06))]">
        <div className="text-[14px] text-ink-2">{t("pay_amount")}</div>
        <div className="mt-1 flex flex-wrap items-baseline gap-3">
          {(q.listPrice > q.total) && (
            <span className="text-[18px] text-ink-3 line-through">{num(q.listPrice)}</span>
          )}
          <span className="text-[32px] font-extrabold text-ink tnum">{num(q.total)} {t("egp")}</span>
          {q.planDiscountPct > 0 && <Pill tone="on">-{Math.round(q.planDiscountPct)}%</Pill>}
          {q.promoCode && <Pill tone="on" dot>{q.promoCode}</Pill>}
        </div>
        <div className="mt-2 text-[12.5px] text-ink-3">{t("pay_secure_note")}</div>
      </Card>

      {/* كود الخصم — التسعيرة تُحسب في الخادم، والحقل يُرسَل مع النموذج */}
      <Card className="mb-6 max-w-[560px]">
        <SectionTitle icon="bolt">{t("promo_have")}</SectionTitle>
        <div className="flex flex-wrap items-center gap-2.5">
          <Input value={code} onChange={(e) => setCode(e.target.value.toUpperCase())}
                 placeholder="RAMADAN25" autoComplete="off"
                 className="max-w-[220px] uppercase" />
          <Btn variant="ghost" type="button" onClick={check} disabled={busy}>
            {t("promo_apply")}
          </Btn>
          {q.promoCode && (
            <span className="inline-flex items-center gap-1.5 text-[13px] font-bold text-au-teal">
              <Icon name="check" size={14} />{t("promo_applied")} — {num(q.promoCut)} {t("egp")}
            </span>
          )}
          {err && <span className="text-[13px] font-bold text-red-300">{err}</span>}
        </div>
      </Card>

      <Card className="mb-6">
        <SectionTitle icon="wallet">{t("pay_method")}</SectionTitle>
        <div className="grid gap-4 lg:grid-cols-3">
          <div className="rounded-2xl bg-white/[0.03] p-5 shadow-[inset_0_0_0_1px_rgb(255_255_255/0.08)]">
            <div className="flex items-center gap-2 font-extrabold text-[#FF6B6B]">
              <Icon name="phone" size={16} />{t("pay_vodafone")}
            </div>
            <div className="mt-2 text-[12.5px] text-ink-3">{t("pay_number")}</div>
            <CopyRow v={plat.vodafone_number} k="vf" />
          </div>

          <div className="rounded-2xl bg-white/[0.03] p-5 shadow-[inset_0_0_0_1px_rgb(255_255_255/0.08)]">
            <div className="flex items-center gap-2 font-extrabold text-au-violet">
              <Icon name="card" size={16} />{t("pay_instapay")}
            </div>
            <div className="mt-2 text-[12.5px] text-ink-3">{t("pay_scan_qr")}</div>
            <img src={qr} alt="InstaPay QR"
                 className="mx-auto my-3 w-[136px] rounded-xl bg-white p-1" />
            <CopyRow v={plat.instapay_handle} k="ip" />
            {plat.instapay_link && (
              <Btn variant="ghost" sm block icon="link" href={plat.instapay_link}
                   target="_blank" rel="noopener" className="mt-2">{t("pay_open_link")}</Btn>
            )}
          </div>

          <div className="rounded-2xl bg-white/[0.03] p-5 shadow-[inset_0_0_0_1px_rgb(255_255_255/0.08)]">
            <div className="flex items-center gap-2 font-extrabold text-au-cyan">
              <Icon name="bank" size={16} />{t("pay_bank")}
            </div>
            <div className="mt-3 flex flex-col gap-1 text-[12.5px] text-ink-3">
              <span>{t("pay_holder")}: <b className="text-ink-2">{plat.bank_holder}</b></span>
              <span>{t("pay_bankname")}: {plat.bank_name}</span>
            </div>
            <CopyRow v={plat.bank_account} k="acc" />
            <CopyRow v={plat.bank_iban} k="iban" />
          </div>
        </div>
      </Card>

      <Card>
        <SectionTitle icon="upload">{t("pay_upload")}</SectionTitle>
        <ol className="mb-5 flex list-decimal flex-col gap-1.5 ps-5 text-[13px] leading-relaxed text-ink-3">
          <li>{t("pay_step1")}</li><li>{t("pay_step2")}</li><li>{t("pay_step3")}</li>
        </ol>
        <Form action={action} encType="multipart/form-data">
          <input type="hidden" name="promo" value={q.promoCode || ""} />
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label={t("pay_method")}>
              <Select name="method" defaultValue="vodafone">
                <option value="vodafone">{t("pay_vodafone")}</option>
                <option value="instapay">{t("pay_instapay")}</option>
                <option value="bank">{t("pay_bank")}</option>
              </Select>
            </Field>
            <Field label={t("pay_ref")}><Input name="ref" placeholder="#..." /></Field>
          </div>
          <div className="mt-4">
            <Field label={t("pay_upload")}>
              <input type="file" name="screenshot" accept="image/*" required
                     className="w-full cursor-pointer rounded-xl bg-black/25 p-2.5 text-[13px] text-ink-3
                                shadow-[inset_0_0_0_1px_rgb(255_255_255/0.1)]
                                file:me-3 file:rounded-lg file:border-0 file:bg-au-violet/25
                                file:px-3 file:py-1.5 file:text-[13px] file:font-bold file:text-white" />
            </Field>
          </div>
          <div className="mt-6"><Btn icon="shield" type="submit">{t("pay_submit")}</Btn></div>
        </Form>
      </Card>
    </>
  );
}

/* ------------------------------------------------------------- بوت مخصّص */
export function RequestBot() {
  const { plat = {}, sent } = P;
  return (
    <>
      <PageHead icon="sparkles" title={t("req_title")} sub={t("req_sub")}
        actions={<Btn variant="ghost" sm icon="back" href={BY.urls.dashboard}>{t("back")}</Btn>} />

      {sent ? (
        <Card className="mb-6 text-center bg-[linear-gradient(120deg,rgb(45_212_167/0.16),transparent)]">
          <Icon name="check" size={32} className="mx-auto text-au-teal" />
          <h2 className="mt-3 mb-0 text-[19px] font-extrabold text-ink">{t("req_sent")}</h2>
        </Card>
      ) : (
        <Card className="mb-6">
          <Form action="">
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label={t("req_business")}><Input name="business" placeholder={t("eg_cafe")} /></Field>
              <Field label={t("req_budget")}><Input name="budget" placeholder="—" /></Field>
            </div>
            <div className="mt-4">
              <Field label={t("req_desc")}>
                <Textarea name="description" required className="min-h-[130px]"
                  placeholder={bi("مثال: عايز بوت يستقبل حجوزات + يبعت تذكير قبل الموعد بيوم…",
                                  "e.g. I need a bot that takes bookings and sends a reminder a day before…")} />
              </Field>
            </div>
            <div className="mt-4">
              <Field label={t("req_contact")}><Input name="contact" placeholder="01xxxxxxxxx / you@email.com" /></Field>
            </div>
            <div className="mt-6"><Btn icon="rocket" type="submit">{t("req_submit")}</Btn></div>
          </Form>
        </Card>
      )}

      <Card>
        <SectionTitle icon="phone">{t("or_contact_now")}</SectionTitle>
        <div className="flex flex-wrap gap-3">
          {plat.support_email && (
            <Btn variant="ghost" icon="inbox" target="_blank" rel="noopener"
                 href={`mailto:${plat.support_email}?subject=${encodeURIComponent(bi("طلب بوت مخصص - BotYalla", "Custom bot request - BotYalla"))}`}>
              {t("contact_email")}
            </Btn>
          )}
          {plat.support_whatsapp && (
            <Btn variant="green" icon="phone" target="_blank" rel="noopener"
                 href={`https://wa.me/${plat.support_whatsapp}?text=${encodeURIComponent(bi("مرحباً، أريد بوت مخصص من BotYalla", "Hi, I want a custom bot from BotYalla"))}`}>
              {t("contact_whatsapp")}
            </Btn>
          )}
          {plat.support_telegram && (
            <Btn variant="ghost" icon="link" target="_blank" rel="noopener"
                 href={`https://t.me/${plat.support_telegram}`}>{t("contact_telegram")}</Btn>
          )}
        </div>
      </Card>
    </>
  );
}
