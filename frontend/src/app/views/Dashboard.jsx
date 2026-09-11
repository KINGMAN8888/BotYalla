import { useState, useRef } from "react";
import { motion } from "motion/react";
import {
  BY, P, t, bi, Icon, Card, Btn, Field, Input, Select, Form, Grid, Stat,
  Pill, Empty, PageHead, SectionTitle, Reveal, num,
} from "../kit.jsx";

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
              <Pill tone="mute"><Icon name="phone" size={11} />WA</Pill>
            )}
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

/* معالج إنشاء البوت — التوكن أولاً لأنه أصعب خطوة على غير التقنيين */
function CreateWizard() {
  const waAllowed = P.waAllowed !== false;
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
              <Icon name="bot" size={16} className="text-au-cyan" /> Telegram
            </label>
            <label className={"flex items-center gap-2 text-[14px] " +
                              (waAllowed ? "cursor-pointer" : "cursor-not-allowed opacity-50")}>
              <input type="radio" name="channel" value="whatsapp" disabled={!waAllowed}
                     checked={channel === "whatsapp"} onChange={(e) => setChannel(e.target.value)} />
              <Icon name="phone" size={16} className="text-au-teal" /> WhatsApp
            </label>
          </div>
          {!waAllowed && (
            <p className="mt-3 mb-0 text-[12.5px] text-ink-3">
              {bi("واتساب مدفوع لكل رسالة من Meta، فهو متاح من الباقة الاحترافية فأعلى.",
                  "WhatsApp is billed per message by Meta, so it starts at the Pro plan.")}{" "}
              <a href={BY.urls.pricing} className="text-au-cyan underline-offset-4 hover:underline">
                {bi("عرض الباقات", "See plans")}
              </a>
            </p>
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
                {status.ok === true ? "✓ " : status.ok === false ? "✕ " : "⏳ "}{status.text}
              </div>
            )}
          </div>
        </>
      ) : (
        <>
          <Btn variant="ghost" sm icon="link" href="https://developers.facebook.com/apps"
               target="_blank" rel="noopener">
            {bi("افتح لوحة مطوري Meta", "Open Meta developers")}
          </Btn>
          <div className="mt-4 grid gap-4 sm:grid-cols-2">
            <Field label="Phone Number ID">
              <Input name="wa_phone_id" required autoComplete="off" spellCheck="false"
                     inputMode="numeric" placeholder="123456789012345" />
            </Field>
            <Field label="Access Token">
              <Input name="wa_token" required autoComplete="off" spellCheck="false"
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

  return (
    <Card id="create">
      <SectionTitle icon="plus">{t("create_bot")}</SectionTitle>
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
  const map = { greeting: ["ob_greeting", "ob_greeting_d"], run: ["ob_run", "ob_run_d"],
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

export default function Dashboard() {
  const { bots = [], total = {}, onboarding = {} } = P;
  const stage = onboarding.stage;
  const fresh = stage === "first_bot";
  return (
    <>
      <PageHead
        title={`${t("welcome_user")} ${BY.user.name}`}
        sub={t("dash_sub")}
        actions={<Btn icon="plus" href="#create">{t("create_bot")}</Btn>}
      />

      {fresh && <FirstBotGuide />}
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

      <div className="mb-6"><CreateWizard /></div>

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
