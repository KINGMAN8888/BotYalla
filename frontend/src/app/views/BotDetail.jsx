import { useState, useEffect, useRef } from "react";
import {
  BY, P, t, bi, Icon, Card, Btn, Field, Input, Textarea, Select, Form, Grid, Stat,
  Pill, Empty, PageHead, SectionTitle, Table, Tr, Td, num, fmtDate,
} from "../kit.jsx";
import { AssetPicker, postJSON } from "../media.jsx";

const fill = (k, o) => Object.entries(o).reduce((a, [x, y]) => a.replace(`{${x}}`, y), t(k));

/* شعار القناة (صور المالك في static/) */
const ChannelLogo = ({ isWa }) => (isWa
  ? <img src="/static/whatsapp.png" alt="WhatsApp" className="size-[12px] object-contain inline-block" />
  : <img src="/static/Telegram.svg.png" alt="Telegram" className="size-[12px] object-contain inline-block" />);

/* ============================================================== قائمة «المزيد»
   رأس الصفحة كان صفّاً من ستة أزرار ينكسر على الموبايل. الأساسي ظاهر،
   والباقي في قائمة واحدة. <details> تعمل بلا جافاسكربت وتُغلق بالنقر خارجها. */
function MoreMenu({ children }) {
  const ref = useRef(null);
  useEffect(() => {
    const close = (e) => { if (ref.current && !ref.current.contains(e.target)) ref.current.open = false; };
    document.addEventListener("click", close);
    return () => document.removeEventListener("click", close);
  }, []);
  return (
    <details ref={ref} className="relative">
      <summary className="list-none [&::-webkit-details-marker]:hidden">
        <span className="inline-flex cursor-pointer items-center gap-2 rounded-[10px] bg-white/[0.04] px-3 py-2 text-[13px]
                         font-bold text-ink shadow-[inset_0_0_0_1px_rgb(255_255_255/0.1)] hover:bg-white/[0.09]">
          <span aria-hidden="true" className="text-[16px] leading-none">⋯</span>{t("more_actions")}
        </span>
      </summary>
      <div className="glass absolute end-0 z-30 mt-2 flex min-w-[220px] flex-col gap-1 rounded-2xl p-2">
        {children}
      </div>
    </details>
  );
}

const MENU_ROW = "flex w-full items-center gap-2.5 rounded-xl border-0 bg-transparent px-3 py-2.5 text-start " +
                 "text-[13.5px] font-bold text-ink no-underline cursor-pointer hover:bg-white/[0.07]";

/* ======================================================== «بوتك جاهز للعملاء» */
function LiveCard({ bot, links, isNew }) {
  const [copied, setCopied] = useState(false);
  const isWa = (bot.channel || "telegram") === "whatsapp";

  if (!links) {
    return (
      <Card className="mb-6">
        <SectionTitle icon="link">{t("live_title")}</SectionTitle>
        <p className="m-0 text-[13px] text-ink-3">{t("live_no_user")}</p>
        {!isWa && (
          <Form action={`/bot/${bot.id}/sync-telegram`} className="mt-4">
            <Btn variant="ghost" sm icon="link" type="submit">{t("tg_sync_btn")}</Btn>
          </Form>
        )}
      </Card>
    );
  }

  async function copy() {
    try { await navigator.clipboard.writeText(links.plain); setCopied(true); setTimeout(() => setCopied(false), 1800); }
    catch { window.prompt(t("live_copy"), links.plain); }
  }
  async function share() {
    if (navigator.share) {
      try { await navigator.share({ title: bot.name, url: links.share || links.plain }); return; } catch { /* أُلغي */ }
    }
    copy();
  }

  return (
    <Card className={"mb-6 " + (isNew ? "bg-[linear-gradient(120deg,rgb(45_212_167/0.16),rgb(124_108_246/0.12))] " +
                                         "shadow-[inset_0_0_0_1px_rgb(45_212_167/0.35)]" : "")}>
      {isNew && (
        <div role="status" className="mb-4 rounded-xl bg-au-teal/15 px-4 py-2.5 text-[14px] font-extrabold text-au-teal">
          {t("live_new")}
        </div>
      )}
      <div className="grid grid-cols-1 items-center gap-6 sm:grid-cols-[170px_minmax(0,1fr)]">
        <a href={links.poster} target="_blank" rel="noopener" title={t("live_poster")}
           className="mx-auto block w-[170px] rounded-2xl bg-white p-2.5 shadow-[0_18px_40px_-18px_rgb(124_108_246/0.8)]
                      transition-transform duration-300 hover:-translate-y-1">
          <img src={links.qr} alt={`QR ${links.handle}`} width="150" height="150" className="block size-full" />
        </a>
        <div className="min-w-0 text-center sm:text-start">
          <SectionTitle icon="rocket">{t("live_title")}</SectionTitle>
          <div dir="ltr" className="-mt-2 mb-2 truncate text-[22px] font-extrabold tracking-tight text-ink sm:text-start">
            {links.handle}
          </div>
          <p className="mt-0 mb-4 text-[13px] leading-relaxed text-ink-3">{t("live_sub")}</p>
          <div className="flex flex-wrap justify-center gap-2 sm:justify-start">
            <Btn variant="green" sm icon="play" href={links.open} target="_blank" rel="noopener">{t("live_open")}</Btn>
            <Btn variant="ghost" sm icon={copied ? "check" : "copy"} type="button" onClick={copy}>{copied ? t("live_copied") : t("live_copy")}</Btn>
            <Btn variant="ghost" sm icon="link" type="button" onClick={share}>{t("live_share")}</Btn>
            <Btn variant="ghost" sm icon="image" href={links.poster} target="_blank" rel="noopener">{t("live_poster")}</Btn>
            <Btn variant="ghost" sm icon="download" href={`${links.qr}?dl=1`}>{t("live_qr_dl")}</Btn>
          </div>
        </div>
      </div>
    </Card>
  );
}

/* ======================================================= وكيل الإعداد الذكي */
const FIELD_LABEL = {
  business_name: "biz_name", welcome: "welcome_msg", thanks: "thanks_msg", flow: "flow_builder",
  kb: "ai_kb", products: "products", menu_items: "menu_items_t", service_name: "service_name",
  open_hour: "open_hour", close_hour: "close_hour", slot_minutes: "slot_minutes", days_ahead: "days_ahead",
};

function show(v) {
  if (v == null || v === "") return "—";
  if (typeof v === "string" || typeof v === "number") return String(v);
  if (Array.isArray(v)) return `${v.length}`;
  if (v.steps) return fill("ai_steps_n", { n: (v.steps || []).length });
  return Object.values(v).filter((x) => typeof x === "string").join(" · ") || "✓";
}

/* معاينة المحادثة كما سيراها العميل — قبل أي حفظ */
function ChatPreview({ proposal }) {
  const f = proposal.flow;
  const bubbles = [];
  const say = (text, extra) => bubbles.push({ text, extra });
  if (f) {
    if (f.start_message) say(f.start_message);
    (f.steps || []).forEach((s) => {
      if (s.type === "buttons") say(s.prompt, { options: s.options });
      else if (s.type === "media") say(s.prompt, { media: true, optional: s.optional });
      else say(s.prompt);
    });
    if (f.end_message) say(f.end_message);
  } else {
    if (proposal.welcome) say(proposal.welcome);
    if (proposal.thanks) say(proposal.thanks);
  }
  return (
    <div className="mx-auto w-full max-w-[380px] rounded-[26px] bg-black/40 p-3 shadow-[inset_0_0_0_1px_rgb(255_255_255/0.1)]">
      <div className="flex max-h-[420px] flex-col gap-2 overflow-y-auto p-1">
        {bubbles.map((b, i) => (
          <div key={i} className="max-w-[88%] rounded-2xl rounded-es-md bg-white/[0.08] px-3 py-2 text-[13px] leading-relaxed text-ink">
            <div className="whitespace-pre-wrap">{b.text}</div>
            {b.extra?.options && (
              <div className="mt-2 flex flex-wrap gap-1.5">
                {b.extra.options.map((o) => (
                  <span key={o} className="rounded-lg bg-au-violet/25 px-2 py-1 text-[12px] font-bold text-white">{o}</span>
                ))}
              </div>
            )}
            {b.extra?.media && (
              <div className="mt-1.5 flex items-center gap-1 text-[11.5px] text-au-cyan">
                <Icon name="clip" size={12} />{b.extra.optional ? t("step_optional") : t("step_f")}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

function AiAgent({ bot, ai }) {
  const [stage, setStage] = useState("idle");        // idle · thinking · questions · proposal · applied
  const [desc, setDesc] = useState("");
  const [sid, setSid] = useState(null);
  const [qs, setQs] = useState([]);
  const [answers, setAnswers] = useState([]);
  const [more, setMore] = useState("");
  const [res, setRes] = useState(null);
  const [err, setErr] = useState(null);
  const [used, setUsed] = useState((ai.setups || {}).used || 0);
  const s = { ...(ai.setups || {}), used };

  function take(d) {
    if (!d.ok) { setErr(d); setStage(sid ? "questions" : "idle"); return; }
    if (!sid) setUsed((n) => n + 1);          // جلسة جديدة احتُسبت من الحصة
    setErr(null); setSid(d.sid);
    if (d.status === "questions") { setQs(d.questions); setAnswers(d.questions.map(() => "")); setMore(""); setStage("questions"); }
    else { setRes(d); setStage("proposal"); }
  }
  async function start() {
    if (!desc.trim()) { setErr({ error: t("ai_need_desc") }); return; }
    setStage("thinking");
    take(await postJSON(`/bot/${bot.id}/ai/session`, { description: desc }));
  }
  async function reply() {
    setStage("thinking");
    take(await postJSON(`/bot/${bot.id}/ai/session/${sid}/reply`, { answers, text: more }));
  }
  async function apply() {
    setStage("thinking");
    const d = await postJSON(`/bot/${bot.id}/ai/session/${sid}/apply`);
    if (d.ok) { setStage("applied"); setTimeout(() => location.reload(), 1400); }
    else { setErr(d); setStage("proposal"); }
  }
  async function discard() {
    if (sid) await postJSON(`/bot/${bot.id}/ai/session/${sid}/discard`);
    setStage("idle"); setSid(null); setRes(null); setQs([]);
  }

  const quota = s.limit == null ? t("ai_agent_quota_unl") : fill("ai_agent_quota", { a: s.used || 0, b: s.limit });

  return (
    <Card className="mb-6 bg-[linear-gradient(120deg,rgb(124_108_246/0.16),rgb(34_211_238/0.05))]">
      <SectionTitle icon="sparkles"
        extra={<Pill tone={s.limit != null && s.used >= s.limit ? "off" : "mute"}>{quota}</Pill>}>
        {t("ai_agent_title")}
      </SectionTitle>

      {(stage === "idle" || (stage === "thinking" && !sid)) && (
        <>
          <p className="mt-0 mb-4 text-[13px] leading-relaxed text-ink-3">{t("ai_agent_desc")}</p>
          <Textarea value={desc} onChange={(e) => setDesc(e.target.value)} placeholder={t("ai_agent_ph")}
                    maxLength={2000} aria-label={t("ai_agent_title")} />
          <div className="mt-4 flex flex-wrap items-center gap-3">
            <Btn icon="sparkles" type="button" onClick={start} disabled={stage === "thinking"}>
              {stage === "thinking" ? t("ai_agent_thinking") : t("ai_agent_start")}
            </Btn>
            {BY.user.role === "admin" && <Btn variant="ghost" sm icon="key" href="/settings">{t("ai_key_btn")}</Btn>}
          </div>
        </>
      )}

      {stage === "thinking" && sid && (
        <div role="status" className="flex items-center gap-3 py-6 text-[14px] font-bold text-ink-3">
          <span className="size-5 animate-spin rounded-full border-2 border-white/15 border-t-au-cyan" />
          {t("ai_agent_thinking")}
        </div>
      )}

      {stage === "questions" && (
        <div>
          <h3 className="mt-0 mb-4 text-[15px] font-extrabold text-ink">{t("ai_agent_q_title")}</h3>
          <div className="flex flex-col gap-5">
            {qs.map((q, i) => (
              <fieldset key={q.id} className="m-0 border-0 p-0">
                <legend className="mb-2.5 text-[14px] font-bold text-ink">{q.q}</legend>
                <div className="flex flex-wrap gap-2">
                  {(q.options || []).map((o) => (
                    <button key={o} type="button" onClick={() => setAnswers(answers.map((a, j) => (j === i ? o : a)))}
                            aria-pressed={answers[i] === o}
                            className={"cursor-pointer rounded-xl border-0 px-3.5 py-2 text-[13px] font-bold transition-colors " +
                                       (answers[i] === o ? "bg-au-violet/40 text-white shadow-[inset_0_0_0_1px_rgb(124_108_246/0.9)]"
                                                         : "bg-white/[0.05] text-ink-2 shadow-[inset_0_0_0_1px_rgb(255_255_255/0.1)] hover:bg-white/[0.1]")}>
                      {o}
                    </button>
                  ))}
                </div>
                <Input className="mt-2.5" value={(q.options || []).includes(answers[i]) ? "" : answers[i]}
                       onChange={(e) => setAnswers(answers.map((a, j) => (j === i ? e.target.value : a)))}
                       placeholder={t("ai_agent_answer_ph")} />
              </fieldset>
            ))}
            <Textarea value={more} onChange={(e) => setMore(e.target.value)} placeholder={t("ai_agent_more_ph")}
                      className="!min-h-[70px]" />
          </div>
          <div className="mt-5 flex flex-wrap gap-3">
            <Btn icon="sparkles" type="button" onClick={reply}>{t("ai_agent_send")}</Btn>
            <Btn variant="ghost" type="button" onClick={discard}>{t("ai_agent_discard")}</Btn>
          </div>
        </div>
      )}

      {stage === "proposal" && res && (
        <div>
          <div className="mb-4 flex flex-wrap items-center gap-2">
            <h3 className="m-0 text-[15px] font-extrabold text-ink">{t("ai_agent_proposal")}</h3>
            <Pill tone="mute"><Icon name="sparkles" size={11} />{res.source === "ai" ? t("ai_agent_live") : t("ai_agent_offline")}</Pill>
          </div>
          {res.summary && <p className="mt-0 mb-4 text-[13.5px] leading-relaxed text-ink-2">{res.summary}</p>}
          <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
            <div>
              <div className="mb-2 text-[12.5px] font-extrabold uppercase tracking-wider text-ink-3">{t("ai_agent_preview")}</div>
              <ChatPreview proposal={res.proposal} />
            </div>
            <div>
              <div className="mb-2 text-[12.5px] font-extrabold uppercase tracking-wider text-ink-3">{t("ai_agent_changes")}</div>
              <ul className="m-0 flex list-none flex-col gap-2.5 p-0">
                {Object.keys(res.proposal).map((k) => (
                  <li key={k} className="rounded-xl bg-black/20 px-3.5 py-3 shadow-[inset_0_0_0_1px_rgb(255_255_255/0.07)]">
                    <div className="mb-1.5 text-[13px] font-extrabold text-ink">{t(FIELD_LABEL[k] || k)}</div>
                    <div className="grid grid-cols-1 gap-1 text-[12.5px] sm:grid-cols-2">
                      <span className="text-ink-3"><b>{t("ai_before")}:</b> <span className="line-clamp-2">{show(res.before?.[k])}</span></span>
                      <span className="text-au-teal"><b>{t("ai_after")}:</b> <span className="line-clamp-3">{show(res.proposal[k])}</span></span>
                    </div>
                  </li>
                ))}
              </ul>
              {res.notes?.length > 0 && (
                <div className="mt-3 rounded-xl bg-yellow-400/10 px-3.5 py-3 text-[12.5px] text-yellow-200">
                  <b>{t("ai_agent_notes")}:</b> {res.notes.join(" · ")}
                </div>
              )}
            </div>
          </div>
          <div className="mt-5 flex flex-wrap gap-3">
            <Btn icon="check" type="button" onClick={apply}>{t("ai_agent_apply")}</Btn>
            <Btn variant="ghost" type="button" onClick={discard}>{t("ai_agent_discard")}</Btn>
          </div>
        </div>
      )}

      {stage === "applied" && (
        <div role="status" className="rounded-xl bg-au-teal/15 px-4 py-3 text-[14px] font-extrabold text-au-teal">
          {t("ai_agent_applied")}
        </div>
      )}

      {err && (
        <p role="alert" className="mt-4 mb-0 text-[13px] font-bold text-red-300">
          {err.error || bi("تعذّر التوليد.", "Generation failed.")}{" "}
          {err.upgrade && <a href={BY.urls.pricing} className="text-au-cyan underline">{t("brain_upgrade")}</a>}
        </p>
      )}
    </Card>
  );
}

/* ============================================================ النسخ السابقة */
function Versions({ bot, versions }) {
  if (!versions?.length) return null;
  const reason = (r) => (r === "ai_apply" ? t("versions_ai_apply") : r === "restore" ? t("versions_restore_r") : r || "—");
  return (
    <Card className="mb-6">
      <SectionTitle icon="clock" extra={<Pill tone="mute">{versions.length}</Pill>}>{t("versions_title")}</SectionTitle>
      <ul className="m-0 flex list-none flex-col gap-2 p-0">
        {versions.slice(0, 6).map((v) => (
          <li key={v.id} className="flex flex-wrap items-center justify-between gap-3 rounded-xl bg-white/[0.03] px-3.5 py-2.5">
            <span className="text-[13px] text-ink-2">
              <b className="tnum text-ink">{new Date(v.created_at * 1000).toLocaleString(BY.lang === "ar" ? "ar-EG" : "en-GB",
                { dateStyle: "medium", timeStyle: "short" })}</b> · {reason(v.reason)}
            </span>
            <Form action={`/bot/${bot.id}/config/restore/${v.id}`} confirm={t("versions_confirm")}>
              <Btn sm variant="ghost" icon="back" type="submit">{t("versions_restore")}</Btn>
            </Form>
          </li>
        ))}
      </ul>
    </Card>
  );
}

/* ================================================ طريقة الرد / عقل البوت */
function BrainCard({ bot, ai, cfg }) {
  const [mode, setMode] = useState(cfg.response_mode || "flow");
  const [faqs, setFaqs] = useState(((cfg.kb || {}).faqs || []).length ? cfg.kb.faqs : [{ q: "", a: "" }]);
  const kb = cfg.kb || {};
  const locked = !ai.modeAllowed;
  const r = ai.replies || {};
  const egp = (p) => (Number(p || 0) / 100).toLocaleString("en-US", { maximumFractionDigits: 2 });
  const needConsent = mode !== "flow" && !cfg.ai_consent_at;

  const MODES = [
    { v: "flow", title: t("brain_mode_flow"), d: t("brain_mode_flow_d"), icon: "flow", paid: false },
    { v: "hybrid", title: t("brain_mode_hybrid"), d: t("brain_mode_hybrid_d"), icon: "bolt", paid: true },
    { v: "ai", title: t("brain_mode_ai"), d: t("brain_mode_ai_d"), icon: "sparkles", paid: true },
  ];

  return (
    <Card className="mb-6" id="brain">
      <SectionTitle icon="bot">{t("brain_title")}</SectionTitle>
      <p className="mt-0 mb-5 text-[13px] leading-relaxed text-ink-3">{t("brain_sub")}</p>
      <Form action={`/bot/${bot.id}/brain`}>
        <div className="grid grid-cols-1 gap-3 md:grid-cols-3" role="radiogroup" aria-label={t("brain_title")}>
          {MODES.map((m) => {
            const off = m.paid && (locked || !ai.engine);
            return (
              <label key={m.v}
                     className={"relative flex flex-col gap-2 rounded-2xl p-4 transition-colors " +
                                (off ? "cursor-not-allowed opacity-70 " : "cursor-pointer ") +
                                (mode === m.v ? "bg-au-violet/20 shadow-[inset_0_0_0_1.5px_rgb(124_108_246/0.85)]"
                                              : "bg-white/[0.03] shadow-[inset_0_0_0_1px_rgb(255_255_255/0.1)] hover:bg-white/[0.06]")}>
                <input type="radio" name="response_mode" value={m.v} className="sr-only" disabled={off}
                       checked={mode === m.v} onChange={() => setMode(m.v)} />
                <span className="flex items-center justify-between gap-2">
                  <span className="flex items-center gap-2 text-[14px] font-extrabold text-ink">
                    <Icon name={off ? "lock" : m.icon} size={16} className="text-au-cyan" />{m.title}
                  </span>
                  {m.paid && <Pill tone="warn">{t("brain_paid")}</Pill>}
                </span>
                <span className="text-[12.5px] leading-relaxed text-ink-3">{m.d}</span>
                {m.paid && (
                  <a href={BY.urls.requestBot} onClick={(e) => e.stopPropagation()}
                     className="mt-auto inline-flex w-fit items-center gap-1.5 rounded-full bg-au-teal/12 px-2.5 py-1
                                text-[11.5px] font-extrabold text-au-teal no-underline hover:bg-au-teal/20">
                    <Icon name="sparkles" size={11} />{t("brain_custom")}
                  </a>
                )}
              </label>
            );
          })}
        </div>

        <div className="mt-4 flex flex-wrap items-center gap-3 text-[12.5px] text-ink-3">
          {!ai.engine && <span className="font-bold text-yellow-200">{t("brain_not_engine")}</span>}
          {locked && ai.engine && (
            <span className="font-bold">
              {t("brain_locked")}{" "}
              <a href={BY.urls.pricing} className="text-au-cyan underline-offset-4 hover:underline">{t("brain_upgrade")}</a>
            </span>
          )}
          {!locked && (
            <span>{r.limit == null ? fill("brain_usage_unl", { a: num(r.used) })
                                     : fill("brain_usage", { a: num(r.used), b: num(r.limit) })}
              {r.limit != null && <> · {fill("brain_over", { p: egp(ai.price), w: egp(ai.wallet) })}</>}
            </span>
          )}
          {!ai.hasKey && mode !== "flow" && <span className="font-bold text-yellow-200">{t("brain_nokey")}</span>}
        </div>

        {ai.canOfficial && (
          <label className="mt-5 flex cursor-pointer items-start gap-3 rounded-2xl bg-au-teal/10 p-4
                            shadow-[inset_0_0_0_1px_rgb(45_212_191/0.35)]">
            <input type="checkbox" name="platform_kb" value="1" defaultChecked={!!cfg.platform_kb} className="mt-1" />
            <span className="flex flex-col gap-1">
              <span className="flex items-center gap-2 text-[14px] font-extrabold text-ink">
                <Icon name="sparkles" size={15} className="text-au-teal" />{t("brain_official")}
              </span>
              <span className="text-[12.5px] leading-relaxed text-ink-3">{t("brain_official_d")}</span>
            </span>
          </label>
        )}

        <details className="mt-5 rounded-2xl bg-black/20 p-4 shadow-[inset_0_0_0_1px_rgb(255_255_255/0.07)]" open={mode !== "flow"}>
          <summary className="cursor-pointer text-[14px] font-extrabold text-ink">{t("brain_welcome_t")}</summary>
          <p className="mt-2 mb-4 text-[12.5px] leading-relaxed text-ink-3">{t("brain_welcome_hint")}</p>
          <Field label={t("brain_welcome_t")}>
            <Textarea name="ai_welcome" defaultValue={cfg.ai_welcome || ""} maxLength={900}
                      placeholder={t("brain_welcome_ph")} className="!min-h-[96px]" />
          </Field>
          <span className="mt-4 mb-2 block text-[13px] font-bold text-ink-2">{t("brain_starters")}</span>
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
            {[0, 1, 2].map((i) => (
              <Input key={i} name="ai_starter" defaultValue={(cfg.ai_starters || [])[i] || ""}
                     placeholder={t("brain_starter_ph")} maxLength={20} />
            ))}
          </div>
          <p className="mt-4 mb-0 flex items-start gap-2 text-[12px] leading-relaxed text-ink-3">
            <Icon name="shield" size={14} className="mt-0.5 shrink-0 text-au-teal" />{t("brain_policy")}
          </p>
        </details>

        <details className="mt-5 rounded-2xl bg-black/20 p-4 shadow-[inset_0_0_0_1px_rgb(255_255_255/0.07)]" open={mode !== "flow"}>
          <summary className="cursor-pointer text-[14px] font-extrabold text-ink">{t("brain_kb_title")}</summary>
          <p className="mt-2 mb-4 text-[12.5px] leading-relaxed text-ink-3">{t("brain_kb_hint")}</p>
          <Field label={t("brain_kb_about")}><Textarea name="kb_about" defaultValue={kb.about || ""} maxLength={800} /></Field>
          <div className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2">
            <Field label={t("brain_kb_hours")}><Input name="kb_hours" defaultValue={kb.hours || ""} maxLength={200} /></Field>
            <Field label={t("brain_kb_location")}><Input name="kb_location" defaultValue={kb.location || ""} maxLength={200} /></Field>
            <Field label={t("brain_kb_delivery")}><Input name="kb_delivery" defaultValue={kb.delivery || ""} maxLength={300} /></Field>
            <Field label={t("brain_kb_payment")}><Input name="kb_payment" defaultValue={kb.payment || ""} maxLength={200} /></Field>
          </div>
          <div className="mt-4"><Field label={t("brain_kb_policies")}><Input name="kb_policies" defaultValue={kb.policies || ""} maxLength={600} /></Field></div>
          <div className="mt-5">
            <span className="mb-2 block text-[13px] font-bold text-ink-2">{t("brain_kb_faq")}</span>
            <div className="flex flex-col gap-2.5">
              {faqs.map((f, i) => (
                <div key={i} className="grid grid-cols-1 gap-2 sm:grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)]">
                  <Input name="kb_q" value={f.q} placeholder={t("brain_kb_q")} maxLength={200}
                         onChange={(e) => setFaqs(faqs.map((x, j) => (j === i ? { ...x, q: e.target.value } : x)))} />
                  <Input name="kb_a" value={f.a} placeholder={t("brain_kb_a")} maxLength={600}
                         onChange={(e) => setFaqs(faqs.map((x, j) => (j === i ? { ...x, a: e.target.value } : x)))} />
                </div>
              ))}
            </div>
            {faqs.length < 12 && (
              <Btn className="mt-3" sm variant="ghost" icon="plus" type="button"
                   onClick={() => setFaqs([...faqs, { q: "", a: "" }])}>{t("brain_kb_add")}</Btn>
            )}
          </div>
          <div className="mt-5">
            <Field label={t("brain_persona")}>
              <Textarea name="ai_persona" defaultValue={cfg.ai_persona || ""} maxLength={600}
                        placeholder={t("brain_persona_ph")} className="!min-h-[70px]" />
            </Field>
          </div>
        </details>

        {needConsent && (
          <label className="mt-4 flex cursor-pointer items-start gap-3 rounded-xl bg-au-violet/10 p-3.5 text-[12.5px]
                            leading-relaxed text-ink-2 shadow-[inset_0_0_0_1px_rgb(124_108_246/0.35)]">
            <input type="checkbox" name="ai_consent" value="1" required className="mt-1" />
            <span>{t("brain_consent")}</span>
          </label>
        )}
        <div className="mt-5"><Btn icon="check" type="submit">{t("brain_save")}</Btn></div>
      </Form>
    </Card>
  );
}

/* ------------------------------------------------------------- ربط الأدمن */
function LinkOwner({ bot }) {
  const cfg = bot.config || {};
  const [link, setLink] = useState(null);
  const [busy, setBusy] = useState(false);

  async function gen() {
    setBusy(true);
    try {
      const r = await fetch(`/bot/${bot.id}/gen-owner-link`, {
        method: "POST", headers: { "X-CSRF-Token": BY.csrf },
      });
      const d = await r.json();
      if (d.ok) setLink(d.link);
    } catch { /* تجاهل */ }
    setBusy(false);
  }

  if (cfg.owner_chat_id)
    return <Pill tone="on"><Icon name="crown" size={13} />{t("admin_linked")}: {cfg.owner_chat_id}</Pill>;

  return (
    <div>
      <p className="mt-0 mb-3 text-[12.5px] leading-relaxed text-ink-3">{t("link_admin_desc")}</p>
      {link ? (
        <Btn variant="green" sm icon="play" href={link} target="_blank" rel="noopener">
          {t("open_tg_start")}
        </Btn>
      ) : (
        <Btn sm icon="link" onClick={gen} disabled={busy} type="button">{t("link_admin_btn")}</Btn>
      )}
    </div>
  );
}

/* -------------------------------------------------------- محرّرات المحتوى */
function ProductsEditor({ products }) {
  const [rows, setRows] = useState(products.length ? products : [{ name: "", price: "", image: "" }]);
  const set = (i, k, v) => setRows(rows.map((r, j) => (j === i ? { ...r, [k]: v } : r)));
  return (
    <>
      <SectionTitle icon="store">{t("products")}</SectionTitle>
      <div className="flex flex-col gap-4">
        {rows.map((r, i) => (
          <div key={i} className="rounded-2xl bg-black/15 p-3 shadow-[inset_0_0_0_1px_rgb(255_255_255/0.06)]">
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-[minmax(0,1fr)_120px_minmax(0,1fr)]">
              <Input name="p_name"  value={r.name}  onChange={(e) => set(i, "name", e.target.value)}  placeholder={t("product")} />
              <Input name="p_price" value={r.price} onChange={(e) => set(i, "price", e.target.value)} placeholder={t("price_egp")} inputMode="decimal" />
              <Input name="p_image" value={r.image || ""} onChange={(e) => set(i, "image", e.target.value)} placeholder={t("image_url_opt")} />
            </div>
            <div className="mt-2.5 flex flex-wrap items-center gap-2 text-[12px] text-ink-3">
              <span>{t("product_media")}:</span>
              <AssetPicker compact name="p_asset" value={r.asset || ""} kinds={["image"]}
                           onChange={(v) => set(i, "asset", v)} />
            </div>
          </div>
        ))}
      </div>
      <div className="mt-3">
        <Btn variant="ghost" sm icon="plus" type="button"
             onClick={() => setRows([...rows, { name: "", price: "", image: "" }])}>
          {t("new_product")}
        </Btn>
      </div>
    </>
  );
}

function MenuEditor({ items }) {
  const [rows, setRows] = useState(items.length ? items : [{ q: "", a: "" }]);
  const set = (i, k, v) => setRows(rows.map((r, j) => (j === i ? { ...r, [k]: v } : r)));
  return (
    <>
      <SectionTitle icon="grid">{t("menu_items_t")}</SectionTitle>
      <div className="flex flex-col gap-3">
        {rows.map((r, i) => (
          <div key={i} className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <Input name="m_q" value={r.q} onChange={(e) => set(i, "q", e.target.value)} placeholder={t("menu_q")} />
            <Input name="m_a" value={r.a} onChange={(e) => set(i, "a", e.target.value)} placeholder={t("menu_a")} />
          </div>
        ))}
      </div>
      <div className="mt-3">
        <Btn variant="ghost" sm icon="plus" type="button" onClick={() => setRows([...rows, { q: "", a: "" }])}>
          {t("new_item")}
        </Btn>
      </div>
    </>
  );
}

function BookingEditor({ cfg }) {
  const days = [
    bi("الإثنين", "Mon"), bi("الثلاثاء", "Tue"), bi("الأربعاء", "Wed"),
    bi("الخميس", "Thu"), bi("الجمعة", "Fri"), bi("السبت", "Sat"), bi("الأحد", "Sun"),
  ];
  const active = cfg.working_days;
  return (
    <>
      <SectionTitle icon="calendar">{t("booking_settings")}</SectionTitle>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <Field label={t("service_name")}><Input name="service_name" defaultValue={cfg.service_name || ""} /></Field>
        <Field label={t("days_ahead")}><Input name="days_ahead" type="number" defaultValue={cfg.days_ahead ?? 7} /></Field>
        <Field label={t("slot_minutes")}><Input name="slot_minutes" type="number" defaultValue={cfg.slot_minutes ?? 60} /></Field>
        <Field label={t("open_hour")}><Input name="open_hour" type="number" min="0" max="23" defaultValue={cfg.open_hour ?? 10} /></Field>
        <Field label={t("close_hour")}><Input name="close_hour" type="number" min="0" max="23" defaultValue={cfg.close_hour ?? 22} /></Field>
      </div>
      <div className="mt-4">
        <span className="mb-2 block text-[13px] font-bold text-ink-2">{t("working_days")}</span>
        <div className="flex flex-wrap gap-2">
          {days.map((d, i) => (
            <label key={i} className="cursor-pointer">
              <input type="checkbox" name="working_days" value={i} className="peer sr-only"
                     defaultChecked={active ? active.includes(i) : true} />
              <span className="inline-flex rounded-xl px-3.5 py-2 text-[13px] font-bold text-ink-3
                               shadow-[inset_0_0_0_1px_rgb(255_255_255/0.1)] transition-colors
                               peer-checked:bg-au-violet/25 peer-checked:text-white
                               peer-checked:shadow-[inset_0_0_0_1px_rgb(124_108_246/0.6)]">{d}</span>
            </label>
          ))}
        </div>
      </div>
    </>
  );
}

/* -------------------------------------------------- ملف أرسله العميل */
/* صورة بروفايل البوت: رفع واحد (الضغط على الصورة) يُزامَن فوراً مع قناة البوت */
function BotPhotoCard({ bot, cfg, isWa }) {
  const has = !!cfg.bot_photo;
  const sync = cfg.bot_photo_sync || null;
  const ver = has ? String(cfg.bot_photo).split("_").pop().split(".")[0] : "";
  const ch = isWa ? "WhatsApp" : "Telegram";
  return (
    <Card className="mb-6">
      <SectionTitle icon="camera"
        extra={has ? (sync && sync.ok ? <Pill tone="on" dot>{bi(`متزامنة مع ${isWa ? "واتساب" : "تليجرام"}`, `Synced to ${ch}`)}</Pill>
                                     : <Pill tone="warn">{bi("لم تُزامَن بعد", "Not synced yet")}</Pill>) : null}>
        {bi("صورة البوت", "Bot profile photo")}
      </SectionTitle>
      <div className="flex flex-col gap-5 sm:flex-row sm:items-center">
        <Form action={`/bot/${bot.id}/photo`} encType="multipart/form-data" className="group relative shrink-0 self-center">
          <label className="relative block cursor-pointer" title={bi("اضغط لرفع صورة جديدة", "Click to upload a new photo")}>
            {has ? (
              <img src={`/bot/${bot.id}/photo?v=${ver}`} alt=""
                   className="size-24 rounded-full object-cover shadow-[0_0_0_3px_rgb(124_108_246/0.45),0_12px_30px_-12px_rgb(124_108_246/0.8)] transition-[filter] group-hover:brightness-90" />
            ) : (
              <span className="grid size-24 place-items-center rounded-full bg-white/[0.04] text-ink-3
                               shadow-[inset_0_0_0_1.5px_rgb(255_255_255/0.14)] transition-colors group-hover:text-au-cyan">
                <Icon name="camera" size={28} />
              </span>
            )}
            <span className="absolute bottom-0 end-0 grid size-8 place-items-center rounded-full bg-[#0B1020] text-au-cyan
                             shadow-[0_0_0_2px_rgb(124_108_246/0.6)] transition-transform duration-300 group-hover:scale-110">
              <Icon name="upload" size={15} />
            </span>
            <input type="file" name="photo" accept="image/png,image/jpeg,image/webp" className="sr-only"
                   aria-label={bi("رفع صورة البوت", "Upload bot photo")}
                   onChange={(e) => e.target.files?.length && e.target.form.requestSubmit()} />
          </label>
        </Form>
        <div className="min-w-0 flex-1">
          <p className="m-0 text-[13.5px] leading-relaxed text-ink-2">
            {isWa ? bi("الصورة اللي عملاؤك بيشوفوها على رقم واتساب للأعمال بتاعك.", "The picture your customers see on your WhatsApp Business number.")
                  : bi("الصورة اللي بتظهر لعملائك في محادثة البوت وفي قائمة محادثات تليجرام.", "The picture customers see in the bot chat and their Telegram chat list.")}
          </p>
          <p className="mb-0 mt-1 text-[12px] leading-relaxed text-ink-3">
            {bi(`اضغط على الصورة واختار صورة أو لوجو (JPG · PNG · WebP حتى 5MB) — بنقصّها مربعة ونظبطها، وبتتحدث على ${isWa ? "واتساب" : "تليجرام"} فوراً.`,
                `Click the picture and pick a photo or logo (JPG · PNG · WebP up to 5MB) — we crop it square and it updates on ${ch} right away.`)}
          </p>
          {sync && !sync.ok && (
            <p className="mb-0 mt-2 text-[12.5px] leading-relaxed text-amber-200">
              {bi("آخر مزامنة فشلت:", "The last sync failed:")} <span dir="ltr">{sync.err === "app_id" ? "App ID" : sync.err}</span>
            </p>
          )}
          {has && (
            <div className="mt-3 flex flex-wrap gap-2">
              <Form action={`/bot/${bot.id}/photo/sync`} className="inline">
                <Btn sm variant="ghost" icon="refresh" type="submit">{bi("إعادة المزامنة", "Sync again")}</Btn>
              </Form>
              <Form action={`/bot/${bot.id}/photo/remove`} className="inline"
                    confirm={isWa ? bi("حذف الصورة من المنصة؟ (على واتساب تفضل لحد ما ترفع غيرها)", "Remove from the platform? (WhatsApp keeps it until you upload another)")
                                  : bi("حذف صورة البوت من المنصة وتليجرام؟", "Remove the bot photo from the platform and Telegram?")}>
                <Btn sm variant="ghost" icon="trash" type="submit">{bi("إزالة", "Remove")}</Btn>
              </Form>
            </div>
          )}
        </div>
      </div>
    </Card>
  );
}

function MediaChip({ m, botId }) {
  const url = `/bot/${botId}/media/${m.id}`;
  const kb = m.size > 1024 * 1024
    ? `${(m.size / 1024 / 1024).toFixed(1)} MB`
    : `${Math.max(1, Math.round(m.size / 1024))} KB`;

  if (m.kind === "image") {
    return (
      <a href={url} target="_blank" rel="noopener"
         className="group relative block size-14 overflow-hidden rounded-lg no-underline
                    shadow-[inset_0_0_0_1px_rgb(255_255_255/0.12)]"
         title={m.caption || kb}>
        <img src={url} alt={m.caption || t("media_kind_image")}
             className="size-full object-cover transition-transform duration-500
                        group-hover:scale-110" loading="lazy" />
      </a>
    );
  }

  if (m.kind === "audio") {
    // الصوت يُسمع في مكانه: تحميله ثم فتحه لسماع رسالة عميل احتكاك بلا داعٍ
    return (
      <span className="inline-flex items-center gap-2 rounded-lg bg-white/5 px-2 py-1"
            title={m.caption || ""}>
        <audio controls preload="none" src={url} className="h-8 max-w-[190px]" />
        <span className="text-[11px] text-ink-3">{kb}</span>
      </span>
    );
  }

  const label = t(`media_kind_${m.kind}`) || t("media_kind_document");
  return (
    <a href={url} target="_blank" rel="noopener"
       className="inline-flex items-center gap-1.5 rounded-lg bg-white/5 px-2.5 py-1
                  text-[12px] text-ink no-underline hover:bg-white/10"
       title={m.caption || ""}>
      <Icon name={m.kind === "video" ? "play" : "download"} size={13} className="text-au-cyan" />
      {label} · <span className="text-ink-3">{kb}</span>
    </a>
  );
}

/* ------------------------------------------------------------ واتساب */
function WhatsAppPanel({ bot, usage }) {
  const cfg = bot.config || {};
  const phone = (bot.token || "").replace(/^wa:/, "");
  const limit = usage ? usage.limit : 0;
  // null = بلا حد (الأدمن) · 0 = الباقة لا تتيح واتساب. الفرق بينهما ليس تجميلياً.
  const unlimited = limit === null || limit === undefined;
  const blocked = !unlimited && limit <= 0;
  const used = (usage && usage.sent) || 0;
  const pct = unlimited || blocked ? 0 : Math.min(100, Math.round((used / limit) * 100));
  const near = !unlimited && !blocked && used >= limit * 0.8;

  return (
    <Card className="mb-6">
      <SectionTitle icon="phone"
        extra={<Pill tone="mute">Phone ID {phone}</Pill>}>
        WhatsApp Cloud API
      </SectionTitle>

      <div className="mb-4">
        <div className="flex items-baseline justify-between gap-3 text-[13px]">
          <span className="font-bold">{bi("الرسائل الصادرة هذا الشهر", "Outbound messages this month")}</span>
          <span className={near || blocked ? "font-bold text-red-300" : "font-bold text-ink-3"}>
            {num(used)}
            {unlimited ? ` — ${bi("بلا حد", "unlimited")}`
                       : blocked ? ` — ${bi("الإرسال متوقف", "sending stopped")}`
                                 : ` / ${num(limit)}`}
          </span>
        </div>
        {!unlimited && !blocked && (
          <div className="mt-2 h-2 w-full overflow-hidden rounded-full bg-white/10">
            <div className={"h-full rounded-full " + (near ? "bg-red-400" : "bg-au-teal")}
                 style={{ width: pct + "%" }} />
          </div>
        )}
        {blocked ? (
          <p className="mt-2 mb-0 text-[12.5px] font-bold text-red-300">
            {bi("باقتك الحالية لا تتيح رسائل واتساب — هذا البوت لن يردّ على أحد. ",
                "Your current plan has no WhatsApp allowance — this bot will not reply to anyone. ")}
            <a href={BY.urls.pricing} className="underline underline-offset-4">
              {bi("ترقية الباقة", "Upgrade")}
            </a>
          </p>
        ) : (
          <p className="mt-2 mb-0 text-[12.5px] text-ink-3">
            {bi("كل رسالة صادرة على واتساب مدفوعة من Meta. عند بلوغ الحدّ يتوقف الإرسال حتى الشهر التالي أو ترقية الباقة.",
                "Every outbound WhatsApp message is billed by Meta. At the limit sending stops until next month or an upgrade.")}
          </p>
        )}
      </div>

      <div className="rounded-xl bg-white/[0.04] p-4 text-[12.5px] leading-relaxed text-ink-3">
        <div className="mb-2 font-bold text-white">{bi("عنوان الويبهوك في Meta", "Webhook URL in Meta")}</div>
        <code className="block overflow-x-auto rounded bg-white/10 px-2 py-1.5">
          {(usage && usage.webhook) || "/wh/whatsapp"}
        </code>
        <p className="mt-3 mb-0">
          {bi("اشترك في حقل messages، واستخدم نفس Verify Token المضبوط في إعدادات المنصة.",
              "Subscribe to the messages field, using the same Verify Token set in platform settings.")}
        </p>
      </div>

      <p className="mt-4 mb-2 text-[12.5px] leading-relaxed text-ink-3">
        {bi("بعد 24 ساعة من آخر رسالة للعميل لا يصله نص حر — القالب المعتمد وحده يصل. ",
            "After 24 hours from a customer's last message only an approved template reaches them. ")}
        <a href={`/bot/${bot.id}/templates`} className="text-au-cyan underline-offset-4 hover:underline">
          {t("wa_tpl_link")}
        </a>
      </p>

      <p className="mt-4 mb-0 text-[12.5px] leading-relaxed text-ink-3">
        {bi("إشعارات العملاء الجدد تصلك على تليجرام — اربط حسابك من ",
            "New-lead notifications arrive on Telegram — link your account from ")}
        <a href="/account" className="text-au-cyan underline-offset-4 hover:underline">
          {bi("«حسابي»", "Account")}
        </a>
        {cfg.owner_chat_id ? ` (${bi("مربوط", "linked")}: ${cfg.owner_chat_id})` : "."}
      </p>
    </Card>
  );
}

/* زرّ «محادثة» بجانب كل عميل — يفتح صندوق الوارد على محادثته */
function ChatBtn({ botId, peer }) {
  if (!peer) return null;
  return (
    <Btn sm variant="ghost" icon="inbox" href={`/bot/${botId}/inbox?peer=${encodeURIComponent(peer)}`}>
      {t("lead_chat")}
    </Btn>
  );
}

/* --------------------------------------------------------------- الصفحة */
export default function BotDetail() {
  const { bot, plan = {}, leads = [], orders = [], bookings = [], usage = null,
          links = null, isNew = false, unread = 0, versions = [], ai = {}, pay = null } = P;
  const cfg = bot.config || {};
  const meta = BY.templates.find((x) => x.k === bot.template) || { icon: "bot", label: bot.template };
  const isFlow = ["flow", "customer_service", "feedback", "support"].includes(bot.template);
  const isWa = (bot.channel || "telegram") === "whatsapp";

  return (
    <>
      <PageHead
        icon={meta.icon}
        title={bot.name}
        sub={meta.label}
        actions={
          <>
            {bot.running ? (
              <Form action={`/bot/${bot.id}/stop`} className="inline">
                <Btn variant="ghost" sm icon="stop" type="submit">{t("stop")}</Btn>
              </Form>
            ) : (
              <Form action={`/bot/${bot.id}/start`} className="inline">
                <Btn variant="green" sm icon="play" type="submit">{t("start")}</Btn>
              </Form>
            )}
            <Btn variant="ghost" sm icon="inbox" href={`/bot/${bot.id}/inbox`}>
              {t("inbox_open")}
              {unread > 0 && (
                <span className="grid min-w-5 place-items-center rounded-full bg-au-teal px-1.5 text-[11px] font-extrabold text-[#04140E]">
                  {unread}
                </span>
              )}
            </Btn>
            {isFlow && <Btn variant="ghost" sm icon="flow" href={`/bot/${bot.id}/flow`}>{t("flow_builder")}</Btn>}
            <MoreMenu>
              <a className={MENU_ROW} href={`/bot/${bot.id}/analytics`}><Icon name="chart" size={16} className="text-au-cyan" />{t("analytics")}</a>
              {plan.broadcast
                ? <a className={MENU_ROW} href={`/bot/${bot.id}/broadcast`}><Icon name="megaphone" size={16} className="text-au-cyan" />{t("campaign")}</a>
                : <a className={MENU_ROW} href={BY.urls.pricing} title={t("upgrade_req")}><Icon name="lock" size={16} className="text-ink-3" />{t("campaign")}</a>}
              {isWa && <a className={MENU_ROW} href={`/bot/${bot.id}/templates`}><Icon name="grid" size={16} className="text-au-cyan" />{t("wa_tpl_link")}</a>}
              <a className={MENU_ROW} href={BY.urls.media}><Icon name="image" size={16} className="text-au-cyan" />{t("media_nav")}</a>
              <Form action={`/bot/${bot.id}/delete`} confirm={bi("حذف البوت نهائياً؟", "Delete this bot permanently?")}>
                <button type="submit" className={MENU_ROW + " !text-red-300"}>
                  <Icon name="trash" size={16} />{bi("حذف البوت", "Delete bot")}
                </button>
              </Form>
            </MoreMenu>
          </>
        }
      />

      <div className="mb-6 flex flex-wrap items-center gap-2">
        {bot.running ? <Pill tone="on" dot>{t("running")}</Pill> : <Pill tone="off">{t("stopped")}</Pill>}
        <Pill tone="mute">
          <ChannelLogo isWa={isWa} />
          {isWa ? "WhatsApp" : "Telegram"}
        </Pill>
        {cfg.bot_username && (
          <Pill tone="mute">
            <ChannelLogo isWa={isWa} />
            {isWa ? cfg.bot_username : `@${cfg.bot_username}`}
          </Pill>
        )}
        {unread > 0 && (
          <a href={`/bot/${bot.id}/inbox`} className="no-underline">
            <Pill tone="warn"><Icon name="inbox" size={12} />{fill("inbox_unread", { n: unread })}</Pill>
          </a>
        )}
      </div>

      <LiveCard bot={bot} links={links} isNew={isNew} />

      <Grid cols={4} className="mb-7">
        <Stat icon="users"  value={bot.stats.subscribers} label={t("stat_subs")} />
        <Stat icon="inbox"  value={bot.stats.leads}       label={t("stat_leads")} />
        <Stat icon="store"  value={bot.stats.orders}      label={t("stat_orders")} />
        <Stat icon="wallet" value={bot.stats.revenue}     label={t("stat_revenue")} />
      </Grid>

      <AiAgent bot={bot} ai={ai} />
      <BrainCard bot={bot} ai={ai} cfg={cfg} />
      <Versions bot={bot} versions={versions} />

      {isWa ? (
        <WhatsAppPanel bot={bot} usage={usage} />
      ) : (
        <div className="mb-6 grid grid-cols-1 gap-4 lg:grid-cols-2">
          <Card>
            <SectionTitle icon="bolt">{t("quick_setup")}</SectionTitle>
            <LinkOwner bot={bot} />
            <p className="mt-4 mb-0 text-[12.5px] leading-relaxed text-ink-3">{t("id_hint")}</p>
          </Card>
          <Card>
            <SectionTitle icon="link"
              extra={cfg.tg_synced_at ? <Pill tone="on">{t("tg_synced")}</Pill> : <Pill tone="mute">{t("tg_not_synced")}</Pill>}>
              {t("tg_official")}
            </SectionTitle>
            <p className="mt-0 mb-4 text-[12.5px] leading-relaxed text-ink-3">{t("tg_sync_desc")}</p>
            <Form action={`/bot/${bot.id}/sync-telegram`}>
              <Btn variant="ghost" sm icon="link" type="submit">{t("tg_sync_btn")}</Btn>
            </Form>
          </Card>
        </div>
      )}

      <BotPhotoCard bot={bot} cfg={cfg} isWa={isWa} />

      {/* الإعدادات */}
      <Card className="mb-6">
        <SectionTitle icon="settings">{t("settings_title")}</SectionTitle>
        <Form action={`/bot/${bot.id}/config`}>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <Field label={t("biz_name")}><Input name="business_name" defaultValue={cfg.business_name || ""} /></Field>
            <Field label={t("owner_id_lbl")} hint={t("owner_id_tip")}>
              <Input name="owner_chat_id" defaultValue={cfg.owner_chat_id || ""} placeholder="123456789" />
            </Field>
          </div>
          {isWa && (
            <div className="mt-4">
              <Field label="WhatsApp Access Token"
                     hint={bi("توكنات Meta المؤقتة تنتهي خلال 24 ساعة — الصق توكناً جديداً هنا عند توقّف البوت. اتركه فارغاً للإبقاء على الحالي.",
                              "Meta temporary tokens expire in 24 hours — paste a new one here when the bot stops. Leave empty to keep the current one.")}>
                <Input name="wa_token" defaultValue="" autoComplete="off" placeholder="EAAG…" />
              </Field>
              <Field label="WhatsApp App ID" className="mt-4"
                     hint={bi("اختياري — بنعرفه تلقائياً من التوكن. محتاجينه بس لو مزامنة صورة البوت فشلت (Meta ← App settings ← Basic).",
                              "Optional — we read it from the token. Only needed if the bot photo sync fails (Meta → App settings → Basic).")}>
                <Input name="wa_app_id" defaultValue={cfg.wa_app_id || ""} inputMode="numeric" dir="ltr" placeholder="1234567890" />
              </Field>
            </div>
          )}
          <div className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2">
            <Field label={t("welcome_msg")}><Textarea name="welcome" defaultValue={cfg.welcome || ""} /></Field>
            <Field label={t("thanks_msg")}><Textarea name="thanks" defaultValue={cfg.thanks || ""} /></Field>
          </div>
          <div className="mt-5 rounded-2xl bg-black/15 p-4 shadow-[inset_0_0_0_1px_rgb(255_255_255/0.06)]">
            <span className="block text-[13px] font-bold text-ink-2">{t("welcome_media")}</span>
            <span className="mt-1 mb-3 block text-[12px] text-ink-3">{t("welcome_media_h")}</span>
            <AssetPicker name="welcome_asset" value={cfg.welcome_asset || ""} />
            <div className="mt-4">
              <Field label={t("welcome_img_url")}>
                <Input name="welcome_image" defaultValue={cfg.welcome_image || ""} placeholder="https://..." dir="ltr" />
              </Field>
            </div>
          </div>

          {bot.template === "store" && (
            <div className="mt-7 pt-6 shadow-[inset_0_1px_0_rgb(255_255_255/0.07)]">
              <ProductsEditor products={cfg.products || []} />
            </div>
          )}
          {bot.template === "faq" && (
            <div className="mt-7 pt-6 shadow-[inset_0_1px_0_rgb(255_255_255/0.07)]">
              <MenuEditor items={cfg.menu_items || []} />
            </div>
          )}
          {bot.template === "booking" && (
            <div className="mt-7 pt-6 shadow-[inset_0_1px_0_rgb(255_255_255/0.07)]">
              <BookingEditor cfg={cfg} />
            </div>
          )}

          <div className="mt-6"><Btn icon="check" type="submit">{t("save_settings")}</Btn></div>
        </Form>
      </Card>

      <PaymentsCard bot={bot} pay={pay} />

      {/* البيانات المُجمّعة — وبجانب كل عميل زرّ المحادثة */}
      {bot.template === "store" && (
        <DataCard icon="store" title={t("orders_h")} empty={t("no_orders")} rows={orders}
                  exportUrl={`/bot/${bot.id}/export/orders`}
                  head={[t("col_customer"), t("col_phone"), t("col_address"), t("col_total"),
                         bi("الدفع", "Payment"), t("col_date"), ""]}
                  render={(o) => [o.customer, o.phone, o.address, `${num(o.total)} ${t("egp")}`,
                                  <OrderPay s={o.pay_status} />, fmtDate(o.created_at),
                                  <ChatBtn botId={bot.id} peer={o.peer} />]} />
      )}
      {bot.template === "booking" && (
        <DataCard icon="calendar" title={t("bookings_h")} empty={t("no_bookings")} rows={bookings}
                  exportUrl={`/bot/${bot.id}/export/bookings`}
                  head={[t("col_customer"), t("col_phone"), t("col_slot"), t("col_status"), ""]}
                  render={(b) => [b.customer, b.phone, b.slot, <Pill tone="on">{b.status}</Pill>,
                                  <ChatBtn botId={bot.id} peer={b.peer} />]} />
      )}
      {isFlow && (
        <DataCard icon="inbox" title={t("customers")} empty={t("no_customers")} rows={leads}
                  exportUrl={`/bot/${bot.id}/export/leads`}
                  head={[t("field_name"), t("col_date"), ""]}
                  render={(l) => [
                    <div className="flex flex-wrap items-center gap-2">
                      {Object.entries(l.data || {})
                        .filter(([, v]) => !String(v).startsWith("media:"))
                        .map(([k, v]) => (
                          <span key={k} className="rounded-lg bg-white/5 px-2.5 py-1 text-[12px]">
                            <b className="text-ink-3">{k}:</b> {String(v)}
                          </span>
                        ))}
                      {(l.media || []).map((m) => <MediaChip key={m.id} m={m} botId={bot.id} />)}
                    </div>, fmtDate(l.created_at), <ChatBtn botId={bot.id} peer={l.peer} />]} />
      )}
    </>
  );
}

/* ======================================================= تحصيل مدفوعات العملاء
   إضافة مدفوعة لكل بوت (متجر تليجرام): بعد تأكيد الطلب يطلب البوت من العميل التحويل على
   حسابات **صاحب البوت** ويستلم صورة الإيصال، فيفحصها بمحرك إيصالات المنصة ويرفض ما ليس
   إيصالاً أو على حساب آخر أو بمبلغ آخر — وما يمرّ يصل هنا وعلى تليجرام بزرّي تأكيد/رفض. */
const ORDER_PAY = {
  awaiting: ["warn", "ينتظر الإيصال", "Awaiting receipt"],
  pending:  ["warn", "إيصال للمراجعة", "Receipt to review"],
  paid:     ["on",   "مدفوع", "Paid"],
  rejected: ["off",  "مرفوض", "Rejected"],
  cancelled: ["mute", "ألغاه العميل", "Cancelled by customer"],
};
const OrderPay = ({ s }) => {
  const x = ORDER_PAY[s];
  return x ? <Pill tone={x[0]}>{bi(x[1], x[2])}</Pill> : <span className="text-ink-3">—</span>;
};
const PAY_ROW = { pending: ["warn", "للمراجعة", "Pending"], approved: ["on", "مؤكدة", "Confirmed"],
                  rejected: ["off", "مرفوضة", "Rejected"] };

function PaymentsCard({ bot, pay }) {
  if (!pay || !pay.eligible) return null;
  const m = pay.methods || {};
  const hasMethod = ["vodafone", "instapay", "bank_account", "bank_iban"].some((k) => m[k]);
  const M = ({ k, label, ph, ltr = true }) => (
    <Field label={label}>
      <Input name={`pay_${k}`} defaultValue={m[k] || ""} placeholder={ph} autoComplete="off"
             dir={ltr ? "ltr" : undefined} />
    </Field>
  );
  return (
    <Card className="mb-6" id="pay">
      <SectionTitle icon="wallet"
        extra={pay.staff
          ? <Pill tone="on" dot>{bi("مفتوحة لحساب الإدارة", "Included for admin")}</Pill>
          : pay.active
          ? <Pill tone="on" dot>{bi(`مفعّلة حتى ${fmtDate(pay.expires)}`, `Active until ${fmtDate(pay.expires)}`)}</Pill>
          : <Pill tone="mute">{bi("غير مفعّلة", "Not active")}</Pill>}>
        {bi("تحصيل مدفوعات العملاء", "Customer payments")}
      </SectionTitle>
      <p className="mt-0 mb-4 text-[13px] leading-relaxed text-ink-2">
        {bi("بعد تأكيد الطلب يطلب البوت من العميل التحويل على حساباتك أنت (فودافون كاش · انستاباي · بنك) ويستلم صورة الإيصال. يفحصها آلياً ويرفض ما ليس إيصالاً أو على حساب آخر أو بمبلغ آخر، وما يمرّ يصلك هنا وعلى تليجرام بزرّي تأكيد/رفض — والعميل يُبلَّغ بقرارك.",
            "After an order is confirmed, the bot asks the customer to transfer to your own accounts (Vodafone Cash · InstaPay · bank) and receives the receipt photo. It checks it automatically and refuses anything that isn't a receipt, went to another account or has another amount; the rest reaches you here and on Telegram with Confirm/Reject — and the customer is told your decision.")}
      </p>
      {!pay.active ? (
        <div className="flex flex-wrap items-center gap-3 rounded-xl p-4
                        bg-[linear-gradient(120deg,rgb(124_108_246/0.18),rgb(34_211_238/0.06))]">
          <div className="min-w-0 flex-1">
            <b className="block tnum text-[15px] text-ink">
              {bi(`${num(pay.price)} ج.م شهرياً لهذا البوت`, `${num(pay.price)} EGP / month for this bot`)}
            </b>
            <span className="text-[12.5px] text-ink-3">
              {bi("إضافة منفصلة عن باقتك — تُدفع لكل بوت.", "Separate from your plan — paid per bot.")}
            </span>
          </div>
          <Btn icon="card" href={`/bot/${bot.id}/addon/pay`}>{bi("فعّل الإضافة", "Activate the add-on")}</Btn>
        </div>
      ) : (
        <>
          <Form action={`/bot/${bot.id}/pay-settings`}>
            <span className="mb-3 block text-[13px] font-bold text-ink-2">
              {bi("حساباتك التي يحوّل عليها العملاء", "Your accounts customers pay into")}
            </span>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <M k="vodafone" label={t("pay_vodafone")} ph="010xxxxxxxx" />
              <M k="instapay" label={`${t("pay_instapay")} — ${t("pay_handle")}`} ph="name@instapay" />
              <M k="instapay_link" label={`${t("pay_instapay")} — ${t("pay_open_link")}`} ph="https://ipn.eg/…" />
              <M k="bank_holder" label={t("pay_holder")} ltr={false} />
              <M k="bank_name" label={t("pay_bankname")} ltr={false} />
              <M k="bank_account" label={t("pay_account")} />
              <M k="bank_iban" label={t("pay_iban")} />
            </div>
            {!hasMethod && (
              <p className="mt-3 mb-0 text-[12.5px] font-bold text-amber-200">
                {bi("أضف وسيلة استلام واحدة على الأقل — بدونها لا يطلب البوت دفعاً من العملاء.",
                    "Add at least one receiving method — without it the bot doesn't ask customers to pay.")}
              </p>
            )}
            <div className="mt-4 flex flex-wrap items-center gap-3">
              <Btn sm icon="check" type="submit">{bi("احفظ الحسابات", "Save accounts")}</Btn>
              {!pay.staff && (
                <Btn sm variant="ghost" icon="card" href={`/bot/${bot.id}/addon/pay`}>{bi("جدّد الإضافة", "Renew the add-on")}</Btn>
              )}
            </div>
          </Form>
          <div className="mt-6">
            {(pay.payments || []).length ? (
              <Table head={["#", t("col_customer"), bi("الطلب", "Order"), t("col_amount"), t("col_status"),
                            t("col_date"), ""]}>
                {pay.payments.map((x) => {
                  const st = PAY_ROW[x.status] || ["mute", x.status, x.status];
                  return (
                    <Tr key={x.id}>
                      <Td className="tnum">{x.id}</Td>
                      <Td>{x.customer || "—"}</Td>
                      <Td className="tnum">{x.order_id ? `#${x.order_id}` : "—"}</Td>
                      <Td className="tnum font-bold">{num(x.amount)} {t("egp")}</Td>
                      <Td><Pill tone={st[0]}>{bi(st[1], st[2])}</Pill></Td>
                      <Td className="text-ink-3">{fmtDate(x.created_at)}</Td>
                      <Td>
                        <div className="flex flex-wrap items-center gap-2">
                          <Btn sm variant="ghost" icon="image" href={`/bot/${bot.id}/payments/${x.id}/receipt`}
                               target="_blank" rel="noopener">{bi("الإيصال", "Receipt")}</Btn>
                          {x.status === "pending" && (
                            <>
                              <Form action={`/bot/${bot.id}/payments/${x.id}/approve`} className="inline">
                                <Btn sm variant="green" icon="check" type="submit">{bi("تأكيد", "Confirm")}</Btn>
                              </Form>
                              <Form action={`/bot/${bot.id}/payments/${x.id}/reject`} className="inline"
                                    confirm={bi("رفض الدفعة وإبلاغ العميل؟", "Reject and notify the customer?")}>
                                <Btn sm variant="red" icon="close" type="submit">{bi("رفض", "Reject")}</Btn>
                              </Form>
                            </>
                          )}
                        </div>
                      </Td>
                    </Tr>
                  );
                })}
              </Table>
            ) : <Empty icon="wallet" title={bi("لا مدفوعات من العملاء بعد", "No customer payments yet")} />}
          </div>
        </>
      )}
    </Card>
  );
}

/* شراء/تجديد إضافة «تحصيل المدفوعات» — نفس مسار الدفع للمنصة: إيصال ← فحص آلي ← موافقة الأدمن.
   المبلغ يعرضه الخادم ويفرضه (لا يُرسل من هنا). */
export function AddonPay() {
  const { bot = {}, price = 0, expires = null, plat = {}, qr, action } = P;
  const [copied, setCopied] = useState("");
  const active = expires && expires * 1000 > Date.now();
  const copy = (v, k) => {
    navigator.clipboard?.writeText(v).then(() => { setCopied(k); setTimeout(() => setCopied(""), 1400); });
  };
  const CopyRow = ({ v, k }) => (
    <div className="mt-2 flex items-center gap-2">
      <code className="flex-1 overflow-x-auto rounded-lg bg-black/30 px-3 py-2 text-[13px] text-au-cyan
                       shadow-[inset_0_0_0_1px_rgb(255_255_255/0.08)]">{v}</code>
      <Btn variant="ghost" sm type="button" onClick={() => copy(v, k)} aria-label={t("copy")}>
        <Icon name={copied === k ? "check" : "copy"} size={13} />
      </Btn>
    </div>
  );
  return (
    <>
      <PageHead icon="wallet" title={t("addon_pay_title")} sub={bot.name}
        actions={<Btn variant="ghost" sm icon="back" href={`/bot/${bot.id}`}>{t("back")}</Btn>} />
      <Card className="mb-6 bg-[linear-gradient(120deg,rgb(124_108_246/0.18),rgb(34_211_238/0.06))]">
        <div className="text-[14px] text-ink-2">{t("pay_amount")}</div>
        <div className="mt-1 tnum text-[32px] font-extrabold text-ink">
          {num(price)} {t("egp")}<span className="ms-2 text-[15px] font-bold text-ink-3">{t("per_month")}</span>
        </div>
        <p className="mt-3 mb-0 max-w-[640px] text-[12.5px] leading-relaxed text-ink-3">
          {bi(`تحصيل مدفوعات عملاء «${bot.name}» لمدة 30 يوماً — العملاء يحوّلون على حساباتك أنت، والبوت يفحص الإيصالات ويرسلها لك للتأكيد.`,
              `Collect payments from «${bot.name}» customers for 30 days — they pay into your own accounts, and the bot checks receipts and sends them to you to confirm.`)}
          {active && " " + bi(`مفعّلة حتى ${fmtDate(expires)} — الدفع الآن يمدّها 30 يوماً من هذا التاريخ.`,
                              `Active until ${fmtDate(expires)} — paying now extends it by 30 days from that date.`)}
        </p>
      </Card>

      <Card>
        <SectionTitle icon="card">{t("pay_method")}</SectionTitle>
        <div className="mb-5 grid gap-4 lg:grid-cols-3">
          <div className="rounded-2xl bg-white/[0.03] p-5 shadow-[inset_0_0_0_1px_rgb(255_255_255/0.08)]">
            <div className="flex items-center gap-2 font-extrabold text-[#FF6B6B]"><Icon name="phone" size={16} />{t("pay_vodafone")}</div>
            <CopyRow v={plat.vodafone_number} k="vf" />
          </div>
          <div className="rounded-2xl bg-white/[0.03] p-5 shadow-[inset_0_0_0_1px_rgb(255_255_255/0.08)]">
            <div className="flex items-center gap-2 font-extrabold text-au-violet"><Icon name="card" size={16} />{t("pay_instapay")}</div>
            {qr && <img src={qr} alt="InstaPay QR" className="mx-auto my-3 w-[112px] rounded-xl bg-white p-1" />}
            <CopyRow v={plat.instapay_handle} k="ip" />
          </div>
          <div className="rounded-2xl bg-white/[0.03] p-5 shadow-[inset_0_0_0_1px_rgb(255_255_255/0.08)]">
            <div className="flex items-center gap-2 font-extrabold text-au-cyan"><Icon name="bank" size={16} />{t("pay_bank")}</div>
            <CopyRow v={plat.bank_account} k="acc" />
            <CopyRow v={plat.bank_iban} k="iban" />
          </div>
        </div>
        <Form action={action} encType="multipart/form-data">
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
          <div className="mt-3 text-[12.5px] text-ink-3">{t("pay_secure_note")}</div>
          <div className="mt-5"><Btn icon="shield" type="submit">{t("pay_submit")}</Btn></div>
        </Form>
      </Card>
    </>
  );
}

function DataCard({ icon, title, rows, head, render, empty, exportUrl }) {
  return (
    <Card className="mb-6">
      <SectionTitle icon={icon}
        extra={rows.length > 0 && (
          <Btn variant="ghost" sm icon="download" href={exportUrl}>CSV</Btn>
        )}>
        {title}
      </SectionTitle>
      {rows.length ? (
        <Table head={head}>
          {rows.map((r, i) => (
            <Tr key={i}>{render(r).map((c, j) => <Td key={j}>{c}</Td>)}</Tr>
          ))}
        </Table>
      ) : <Empty icon={icon} title={empty} />}
    </Card>
  );
}
