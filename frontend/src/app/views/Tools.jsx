import { useState, useEffect, useRef } from "react";
import { motion, AnimatePresence } from "motion/react";
import {
  BY, P, t, bi, Icon, Card, Btn, Field, Input, Textarea, Select, Form,
  Grid, Stat, Pill, Empty, PageHead, SectionTitle, num,
} from "../kit.jsx";

/* ---------------------------------------------------------- باني الفلو */
export function FlowBuilder() {
  const { bot, flow: initial } = P;
  const [start, setStart] = useState(initial.start_message || "");
  const [end, setEnd] = useState(initial.end_message || "");
  const [steps, setSteps] = useState(
    (initial.steps || []).map((s) => ({
      type: s.type || "question", prompt: s.prompt || "",
      var: s.var || "", options: (s.options || []).join(", "),
    }))
  );

  const set = (i, k, v) => setSteps(steps.map((s, j) => (j === i ? { ...s, [k]: v } : s)));
  const add = () => setSteps([...steps, { type: "question", prompt: "", var: "", options: "" }]);
  const del = (i) => setSteps(steps.filter((_, j) => j !== i));
  const move = (i, d) => {
    const j = i + d;
    if (j < 0 || j >= steps.length) return;
    const c = [...steps]; [c[i], c[j]] = [c[j], c[i]]; setSteps(c);
  };

  const TYPES = [
    { v: "question", l: t("step_q") },
    { v: "buttons",  l: t("step_b") },
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
                           disabled={s.type !== "buttons"} placeholder="A, B, C" />
                  </Field>
                </div>
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
  const { bot, subs } = P;
  const [text, setText] = useState("");
  return (
    <>
      <PageHead icon="megaphone" title={t("campaign_title")} sub={t("campaign_sub")}
        actions={<Btn variant="ghost" sm icon="back" href={`/bot/${bot.id}`}>{t("back")}</Btn>} />
      <Card className="max-w-[720px]">
        <Pill tone="mute"><Icon name="users" size={13} />{num(subs)} {t("subs_will_get")}</Pill>
        <Form action="" className="mt-5"
              confirm={bi("إرسال الحملة لكل المشتركين؟", "Send to all subscribers?")}>
          <Field label={t("msg_text")}>
            <Textarea name="text" required value={text} onChange={(e) => setText(e.target.value)}
                      className="min-h-[140px]" />
          </Field>
          <div className="mt-3 text-[12.5px] text-ink-3">{text.length} / 4096</div>
          <div className="mt-5">
            <Btn icon="rocket" type="submit" disabled={!text.trim()}>{t("send_campaign")}</Btn>
          </div>
        </Form>
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
    </>
  );
}

/* ------------------------------------------------------------ المصادقة */
export function Auth({ mode }) {
  const isLogin = mode === "login";
  return (
    <div className="mx-auto flex min-h-screen max-w-[440px] flex-col justify-center px-5 py-16">
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
