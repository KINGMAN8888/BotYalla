import { useState, useEffect, useRef } from "react";
import { motion, AnimatePresence } from "motion/react";
import {
  BY, P, t, bi, Icon, Card, Btn, Field, Input, Textarea, Select, Form,
  Grid, Stat, Pill, Empty, PageHead, SectionTitle, num,
} from "../kit.jsx";
import { Flashes } from "../AppShell.jsx";
import { AssetPicker } from "../media.jsx";

/* ---------------------------------------------------------- باني الفلو */
export function FlowBuilder() {
  const { bot, flow: initial } = P;
  const [start, setStart] = useState(initial.start_message || "");
  const [end, setEnd] = useState(initial.end_message || "");
  const [steps, setSteps] = useState(
    (initial.steps || []).map((s) => ({
      type: s.type || "question", prompt: s.prompt || "",
      var: s.var || "", options: (s.options || []).join(", "),
      asset: s.asset ? String(s.asset) : "", optional: !!s.optional,
    }))
  );

  const set = (i, k, v) => setSteps(steps.map((s, j) => (j === i ? { ...s, [k]: v } : s)));
  const add = () => setSteps([...steps, { type: "question", prompt: "", var: "", options: "", asset: "", optional: false }]);
  const del = (i) => setSteps(steps.filter((_, j) => j !== i));
  const move = (i, d) => {
    const j = i + d;
    if (j < 0 || j >= steps.length) return;
    const c = [...steps]; [c[i], c[j]] = [c[j], c[i]]; setSteps(c);
  };

  const TYPES = [
    { v: "question", l: t("step_q") },
    { v: "buttons",  l: t("step_b") },
    { v: "media",    l: t("step_f") },
    { v: "show",     l: t("step_show") },
    { v: "message",  l: t("step_m") },
  ];

  return (
    <>
      <PageHead icon="flow" title={t("flow_title")} sub={t("flow_sub")}
        actions={<Btn variant="ghost" sm icon="back" href={`/bot/${bot.id}`}>{t("back")}</Btn>} />

      <Form action="">
        <Card className="mb-5">
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label={t("flow_welcome")}>
              <Textarea name="start_message" value={start} onChange={(e) => setStart(e.target.value)} />
            </Field>
            <Field label={t("flow_end")}>
              <Textarea name="end_message" value={end} onChange={(e) => setEnd(e.target.value)} />
            </Field>
          </div>
        </Card>

        <Card className="mb-5">
          <SectionTitle icon="flow" extra={<span className="text-[13px] text-ink-3">{steps.length}</span>}>
            {t("flow_steps")}
          </SectionTitle>
          <p className="mt-0 mb-5 text-[13px] text-ink-3">{t("flow_steps_desc")}</p>

          <AnimatePresence initial={false}>
            {steps.map((s, i) => (
              <motion.div key={i} layout
                initial={{ opacity: 0, y: -8 }} animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, height: 0, marginBottom: 0 }}
                transition={{ duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
                className="mb-3 rounded-2xl bg-black/20 p-5 shadow-[inset_0_0_0_1px_rgb(255_255_255/0.08)]">
                <div className="mb-4 flex items-center justify-between gap-3">
                  <span className="grid size-7 place-items-center rounded-lg text-[12.5px] font-extrabold
                                   text-au-cyan bg-au-violet/20">{i + 1}</span>
                  <div className="flex gap-1.5">
                    <Btn sm variant="ghost" type="button" onClick={() => move(i, -1)} disabled={i === 0}
                         aria-label={bi("لأعلى", "Move up")}>↑</Btn>
                    <Btn sm variant="ghost" type="button" onClick={() => move(i, 1)}
                         disabled={i === steps.length - 1} aria-label={bi("لأسفل", "Move down")}>↓</Btn>
                    <Btn sm variant="red" type="button" icon="trash" onClick={() => del(i)}
                         aria-label={bi("حذف الخطوة", "Delete step")} />
                  </div>
                </div>

                <div className="grid gap-4 sm:grid-cols-[160px_1fr]">
                  <Field label={t("step_type")}>
                    <Select name="s_type" value={s.type} onChange={(e) => set(i, "type", e.target.value)}>
                      {TYPES.map((x) => <option key={x.v} value={x.v}>{x.l}</option>)}
                    </Select>
                  </Field>
                  <Field label={t("step_prompt")}>
                    <Input name="s_prompt" value={s.prompt} onChange={(e) => set(i, "prompt", e.target.value)} required />
                  </Field>
                </div>

                <div className="mt-4 grid gap-4 sm:grid-cols-2">
                  <Field label={t("field_name")}>
                    <Input name="s_var" value={s.var} onChange={(e) => set(i, "var", e.target.value)}
                           disabled={s.type === "message"} />
                  </Field>
                  <Field label={t("btn_options")}>
                    <Input name="s_options" value={s.options} onChange={(e) => set(i, "options", e.target.value)}
                           disabled={s.type !== "buttons" && s.type !== "show"} placeholder="A, B, C" />
                  </Field>
                </div>
                {/* حقلان لكل خطوة دائماً (ولو فارغين) — القوائم تُقرأ بالترتيب في الخادم */}
                <input type="hidden" name="s_asset" value={s.type === "show" ? s.asset : ""} />
                <input type="hidden" name="s_optional" value={s.type === "media" && s.optional ? "1" : ""} />
                {s.type === "media" && (
                  <>
                    <p className="mt-3 mb-0 text-[12.5px] leading-relaxed text-ink-3">
                      <Icon name="image" size={13} className="me-1 inline align-[-2px] text-au-cyan" />
                      {t("step_f_hint")}
                    </p>
                    <label className="mt-3 flex cursor-pointer items-center gap-2 text-[13px] text-ink-2">
                      <input type="checkbox" checked={s.optional} onChange={(e) => set(i, "optional", e.target.checked)} />
                      {t("step_optional")}
                    </label>
                  </>
                )}
                {s.type === "show" && (
                  <div className="mt-4 rounded-xl bg-white/[0.03] p-3.5 shadow-[inset_0_0_0_1px_rgb(255_255_255/0.07)]">
                    <AssetPicker value={s.asset} onChange={(v) => set(i, "asset", v)} />
                    <p className="mt-2.5 mb-0 text-[12px] leading-relaxed text-ink-3">{t("step_show_hint")}</p>
                  </div>
                )}
              </motion.div>
            ))}
          </AnimatePresence>

          {!steps.length && <Empty icon="flow" title={t("flow_steps_desc")} />}

          <div className="mt-4"><Btn variant="ghost" icon="plus" type="button" onClick={add}>{t("add_step")}</Btn></div>
        </Card>

        <Btn icon="check" type="submit">{t("save_flow")}</Btn>
      </Form>
    </>
  );
}

/* ------------------------------------------------------------- البث */
export function Broadcast() {
  const { bot, subs, isWa = false, reachable = subs, audience = reachable, waba = "",
          wallet = { balance: 0, price: 0 } } = P;
  const [text, setText] = useState("");
  const [asset, setAsset] = useState("");
  const [mode, setMode] = useState("text");
  const [tpls, setTpls] = useState(null);      // null = لم يُجلب بعد
  const [pick, setPick] = useState("");

  useEffect(() => {
    if (!isWa || !waba) return;
    let alive = true;
    fetch(`/api/bot/${bot.id}/templates`).then((r) => r.json())
      .then((d) => alive && setTpls((d.items || []).filter((x) => x.status === "APPROVED")))
      .catch(() => alive && setTpls([]));
    return () => { alive = false; };
  }, [bot.id, isWa, waba]);

  const chosen = (tpls || []).find((x) => x.name === pick);
  /* التكلفة تُعرض هنا للطمأنة فقط — الخادم يعيد حسابها وقت الإرسال ويقرأ فئة
     القالب من Meta، فتعديل أي شيء في هذه الصفحة لا يغيّر قرشاً. */
  const egp = (p) => Number(p || 0) / 100;
  const billable = !!chosen && (chosen.category || "").toUpperCase() === "MARKETING";
  // القالب يصل لكل المشتركين لا لنافذة الـ24 ساعة وحدها — فعليهم تُحسب التكلفة
  const cost = billable ? audience * (wallet.price || 0) : 0;
  const short = Math.max(0, cost - (wallet.balance || 0));
  const fill = (k, o) => Object.entries(o).reduce((a, [x, y]) => a.replace(`{${x}}`, y), t(k));

  return (
    <>
      <PageHead icon="megaphone" title={t("campaign_title")} sub={t("campaign_sub")}
        actions={<>
          {isWa && <Btn variant="ghost" sm icon="grid" href={`/bot/${bot.id}/templates`}>{t("wa_tpl_link")}</Btn>}
          <Btn variant="ghost" sm icon="back" href={`/bot/${bot.id}`}>{t("back")}</Btn>
        </>} />

      <Card className="max-w-[720px]">
        <div className="flex flex-wrap items-center gap-2">
          <Pill tone="mute"><Icon name="users" size={13} />{num(subs)} {t("subs_will_get")}</Pill>
          {isWa && (
            <Pill tone={reachable ? "on" : "off"}>
              {num(reachable)} {t("bc_reachable")}
            </Pill>
          )}
        </div>

        {isWa && (
          <>
            <p className="mt-4 mb-0 text-[12.5px] leading-relaxed text-ink-3">{t("bc_window_note")}</p>
            <div className="mt-4 flex flex-wrap gap-4">
              {[["text", t("bc_mode_text")], ["template", t("bc_mode_tpl")]].map(([v, label]) => (
                <label key={v} className="flex cursor-pointer items-center gap-2 text-[13.5px]">
                  <input type="radio" name="mode" value={v} checked={mode === v}
                         onChange={(e) => setMode(e.target.value)} />
                  {label}
                </label>
              ))}
            </div>
          </>
        )}

        {isWa && mode === "template" ? (
          <Form action="" className="mt-5"
                confirm={bi("إرسال القالب لكل المشتركين؟", "Send this template to all subscribers?")}>
            <input type="hidden" name="mode" value="template" />
            {!waba ? (
              <p className="m-0 text-[13px] text-ink-3">
                {bi("اربط حساب واتساب للأعمال أولاً من ", "Link your WhatsApp Business Account first from ")}
                <a href={`/bot/${bot.id}/templates`} className="text-au-cyan underline-offset-4 hover:underline">
                  {t("wa_tpl_link")}
                </a>
              </p>
            ) : tpls === null ? (
              <span className="text-[13px] text-ink-3">{bi("جاري الجلب من Meta…", "Fetching from Meta…")}</span>
            ) : tpls.length === 0 ? (
              <p className="m-0 text-[13px] text-ink-3">
                {bi("لا قوالب معتمدة بعد. ", "No approved templates yet. ")}
                <a href={`/bot/${bot.id}/templates`} className="text-au-cyan underline-offset-4 hover:underline">
                  {bi("أنشئ قالباً", "Create one")}
                </a>
              </p>
            ) : (
              <>
                <Field label={t("bc_mode_tpl")}>
                  <Select name="template" required value={pick} onChange={(e) => setPick(e.target.value)}>
                    <option value="">— {bi("اختر", "Choose")} —</option>
                    {tpls.map((x) => (
                      <option key={x.id || x.name} value={x.name}>{x.name} · {x.language}</option>
                    ))}
                  </Select>
                </Field>
                {chosen && (
                  <>
                    <input type="hidden" name="template_lang" value={chosen.language} />
                    <div className={"mt-4 rounded-xl p-4 " + (billable
                      ? (short ? "bg-red-500/10 shadow-[inset_0_0_0_1px_rgb(248_113_113/0.35)]"
                               : "bg-[linear-gradient(120deg,rgb(124_108_246/0.18),rgb(34_211_238/0.06))]")
                      : "bg-white/[0.03] shadow-[inset_0_0_0_1px_rgb(255_255_255/0.08)]")}>
                      <div className="flex items-center gap-2 text-[13px] font-extrabold text-ink">
                        <Icon name="wallet" size={15} className="text-au-cyan" />{t("camp_cost_title")}
                      </div>
                      {billable ? (
                        <>
                          <div className="mt-2 text-[14px] font-extrabold text-ink tnum">
                            {fill("camp_cost_calc", { n: num(audience), p: num(egp(wallet.price)),
                                                      c: num(egp(cost)) })}
                          </div>
                          <div className="mt-1 text-[12.5px] text-ink-3 tnum">
                            {fill("camp_after", { n: num(egp(Math.max(0, wallet.balance - cost))) })}
                          </div>
                          {short > 0 && (
                            <div className="mt-3 flex flex-wrap items-center gap-3">
                              <span className="text-[13px] font-extrabold text-red-300">
                                {fill("camp_short", { n: num(egp(short)) })}
                              </span>
                              <Btn variant="ghost" sm icon="plus" href={BY.urls.wallet}>
                                {t("wallet_topup")}
                              </Btn>
                            </div>
                          )}
                        </>
                      ) : (
                        <div className="mt-2 text-[12.5px] text-ink-3">{t("camp_cost_free")}</div>
                      )}
                      <div className="mt-3 text-[11.5px] text-ink-3">{t("camp_marketing_d")}</div>
                    </div>
                    <div className="mt-4 rounded-xl bg-white/[0.04] p-4 text-[13.5px] leading-relaxed text-ink-2">
                      {chosen.header && <div className="mb-2 font-extrabold text-ink">{chosen.header}</div>}
                      <div className="whitespace-pre-wrap">{chosen.body}</div>
                      {chosen.footer && <div className="mt-2 text-[12px] text-ink-3">{chosen.footer}</div>}
                    </div>
                    {chosen.vars.length > 0 && (
                      <div className="mt-4 grid gap-3 sm:grid-cols-2">
                        {chosen.vars.map((n) => (
                          <Field key={n} label={`{{${n}}}`}>
                            <Input name="var" required autoComplete="off"
                                   placeholder={bi("نفس القيمة لكل المستلمين", "same value for every recipient")} />
                          </Field>
                        ))}
                      </div>
                    )}
                  </>
                )}
                <div className="mt-5">
                  <Btn icon="rocket" type="submit" disabled={!pick || short > 0}>{t("send_campaign")}</Btn>
                </div>
              </>
            )}
          </Form>
        ) : (
          <Form action="" className="mt-5"
                confirm={bi("إرسال الحملة لكل المشتركين؟", "Send to all subscribers?")}>
            <input type="hidden" name="mode" value="text" />
            <Field label={t("msg_text")}>
              <Textarea name="text" required={!asset} value={text} onChange={(e) => setText(e.target.value)}
                        className="min-h-[140px]" />
            </Field>
            <div className="mt-3 text-[12.5px] text-ink-3">{text.length} / 4096</div>
            <div className="mt-4 rounded-xl bg-white/[0.03] p-3.5 shadow-[inset_0_0_0_1px_rgb(255_255_255/0.07)]">
              <span className="mb-2.5 block text-[12.5px] text-ink-3">{t("bc_media")}</span>
              <AssetPicker name="asset_id" value={asset} onChange={(v) => setAsset(v)} />
            </div>
            <div className="mt-5">
              <Btn icon="rocket" type="submit" disabled={!text.trim() && !asset}>{t("send_campaign")}</Btn>
            </div>
          </Form>
        )}
      </Card>
    </>
  );
}

/* ---------------------------------------------------------- التحليلات */
export function Analytics() {
  const { bot } = P;
  const [d, setD] = useState(null);
  const actRef = useRef(null), revRef = useRef(null);

  useEffect(() => {
    fetch(`/api/bot/${bot.id}/stats`).then((r) => r.json()).then(setD).catch(() => {});
  }, [bot.id]);

  useEffect(() => {
    if (!d || !window.Chart) return;
    const C = window.Chart;
    C.defaults.color = "#7B87A8";
    C.defaults.borderColor = "rgba(255,255,255,.08)";
    C.defaults.font.family = BY.lang === "en" ? "Inter,sans-serif" : "Cairo,sans-serif";
    const L = d.daily.labels.map((x) => x.slice(5));
    const a = new C(actRef.current, {
      type: "line",
      data: { labels: L, datasets: [
        { label: t("stat_subs"), data: d.daily.starts, borderColor: "#7C6CF6",
          backgroundColor: "rgba(124,108,246,.15)", tension: .35, fill: true },
        { label: t("stat_orders"), data: d.daily.orders, borderColor: "#22D3EE",
          backgroundColor: "rgba(34,211,238,.12)", tension: .35, fill: true },
        { label: t("stat_bookings"), data: d.daily.bookings, borderColor: "#FFD23F",
          backgroundColor: "rgba(255,210,63,.12)", tension: .35, fill: true }] },
      options: { plugins: { legend: { position: "bottom" } },
                 scales: { y: { beginAtZero: true, ticks: { precision: 0 } } } },
    });
    const b = new C(revRef.current, {
      type: "bar",
      data: { labels: L, datasets: [{ data: d.daily.revenue, backgroundColor: "rgba(45,212,167,.55)", borderRadius: 7 }] },
      options: { plugins: { legend: { display: false } }, scales: { y: { beginAtZero: true } } },
    });
    return () => { a.destroy(); b.destroy(); };
  }, [d]);

  const s = d?.summary || {};
  return (
    <>
      <PageHead icon="chart" title={`${t("analytics_of")} ${bot.name}`} sub={t("analytics_sub")}
        actions={<Btn variant="ghost" sm icon="back" href={`/bot/${bot.id}`}>{t("back")}</Btn>} />

      <Grid cols={4} className="mb-6">
        <Stat icon="users"  value={s.subscribers} label={t("stat_subs")} />
        <Stat icon="inbox"  value={s.leads}       label={t("stat_leads")} />
        <Stat icon="store"  value={s.orders}      label={t("stat_orders")} />
        <Stat icon="wallet" value={s.revenue}     label={t("stat_revenue")} />
      </Grid>

      <div className="grid gap-4 md:grid-cols-2">
        <Card><SectionTitle icon="chart">{t("daily_activity")}</SectionTitle>
          <canvas ref={actRef} height="220" /></Card>
        <Card><SectionTitle icon="wallet">{t("daily_revenue")}</SectionTitle>
          <canvas ref={revRef} height="220" /></Card>
      </div>

      {/* من أين دخل العملاء — روابط البوت تحمل مصدرها (QR · رابط · ملصق · مشاركة) */}
      <Card className="mt-4">
        <SectionTitle icon="link">{t("src_title")}</SectionTitle>
        {d && Object.values(d.sources || {}).some(Boolean) ? (
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            {[["qr", "grid"], ["link", "link"], ["poster", "image"], ["share", "users"]].map(([k, ic]) => (
              <div key={k} className="rounded-2xl bg-white/[0.03] p-4 shadow-[inset_0_0_0_1px_rgb(255_255_255/0.08)]">
                <Icon name={ic} size={18} className="text-au-cyan" />
                <div className="mt-2 text-[24px] font-extrabold text-ink tnum">{num((d.sources || {})[k] || 0)}</div>
                <div className="text-[12.5px] text-ink-3">{t(`src_${k}`)}</div>
              </div>
            ))}
          </div>
        ) : <p className="m-0 text-[13px] text-ink-3">{t("src_none")}</p>}
      </Card>
    </>
  );
}

/* ------------------------------------------------------------ المصادقة */
export function Auth({ mode }) {
  const isLogin = mode === "login";
  return (
    <div className="mx-auto flex min-h-screen max-w-[440px] flex-col justify-center px-5 py-16">
      <Flashes />
      <a href={BY.urls.landing} className="mb-6 flex justify-center no-underline">
        <img src={BY.urls.logo} alt={BY.brand} className="h-11 w-auto" />
      </a>
      <Card className="!p-8">
        <h1 className="m-0 text-center text-[24px] font-extrabold tracking-tight text-ink">
          {isLogin ? t("login") : t("register")}
        </h1>
        <p className="mb-7 mt-2 text-center text-[14px] text-ink-3">
          {isLogin ? t("login_sub") : t("register_sub")}
        </p>
        <Form action="">
          <Field label={t("username")} className="mb-4">
            <Input name="username" required autoFocus autoComplete="username"
                   minLength={isLogin ? undefined : 3} />
          </Field>
          {!isLogin && (
            <Field label={`${t("email")} (${t("optional")})`} hint={t("email_hint")} className="mb-4">
              <Input type="email" name="email" autoComplete="email" dir="ltr" />
            </Field>
          )}
          <Field label={t("password")}
                 hint={isLogin ? undefined : t("pw_hint")}>
            <Input type="password" name="password" required minLength={isLogin ? undefined : 6}
                   autoComplete={isLogin ? "current-password" : "new-password"} />
          </Field>
          <div className="mt-6">
            <Btn block icon={isLogin ? "lock" : "rocket"} type="submit">
              {isLogin ? t("login") : t("register")}
            </Btn>
          </div>
        </Form>

        {isLogin && (
          <p className="mt-4 text-center text-[13px]">
            <a href={BY.urls.forgot} className="text-ink-3 underline-offset-4 hover:text-ink hover:underline">
              {t("forgot_link")}
            </a>
          </p>
        )}

        {!isLogin && (
          <div className="mt-5 flex flex-wrap justify-center gap-x-5 gap-y-2 text-[12px] text-ink-3">
            <span className="inline-flex items-center gap-1.5">
              <Icon name="check" size={13} className="text-au-teal" />{t("lp_trust_1")}</span>
            <span className="inline-flex items-center gap-1.5">
              <Icon name="check" size={13} className="text-au-teal" />{t("free_forever")}</span>
          </div>
        )}

        <p className="mt-6 text-center text-[13px] text-ink-3">
          {isLogin ? t("no_account") : t("have_account")}{" "}
          <a href={isLogin ? BY.urls.register : BY.urls.login}
             className="font-bold text-au-cyan underline-offset-4 hover:underline">
            {isLogin ? t("signup_link") : t("signin_link")}
          </a>
        </p>
      </Card>
    </div>
  );
}

/* استرجاع كلمة المرور: طلب الرابط (forgot) ثم ضبط كلمة جديدة (reset).
   نموذج POST عادي إلى نفس المسار — Flask يتحقق ويحوّل ويعرض flash. */
export function Recover({ mode }) {
  const isReset = mode === "reset";
  return (
    <div className="mx-auto flex min-h-screen max-w-[440px] flex-col justify-center px-5 py-16">
      <Flashes />
      <a href={BY.urls.landing} className="mb-6 flex justify-center no-underline">
        <img src={BY.urls.logo} alt={BY.brand} className="h-11 w-auto" />
      </a>
      <Card className="!p-8">
        <h1 className="m-0 text-center text-[24px] font-extrabold tracking-tight text-ink">
          {isReset ? t("reset_title") : t("forgot_title")}
        </h1>
        <p className="mb-7 mt-2 text-center text-[14px] text-ink-3">
          {isReset ? t("reset_sub") : t("forgot_sub")}
        </p>
        <Form action="">
          {isReset ? (
            <Field label={t("password")} hint={t("pw_hint")}>
              <Input type="password" name="password" required minLength={6} autoFocus
                     autoComplete="new-password" />
            </Field>
          ) : (
            <Field label={t("email")}>
              <Input type="email" name="email" required autoFocus autoComplete="email" dir="ltr" />
            </Field>
          )}
          <div className="mt-6">
            <Btn block icon={isReset ? "lock" : "link"} type="submit">
              {isReset ? t("reset_save") : t("forgot_send")}
            </Btn>
          </div>
        </Form>
        {!isReset && (
          <p className="mb-0 mt-5 text-center text-[12px] text-ink-3">{t("forgot_no_email")}</p>
        )}
        <p className="mt-6 text-center text-[13px] text-ink-3">
          <a href={BY.urls.login} className="font-bold text-au-cyan underline-offset-4 hover:underline">
            {t("signin_link")}
          </a>
        </p>
      </Card>
    </div>
  );
}
