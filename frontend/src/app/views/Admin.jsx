import { useEffect, useRef, useState } from "react";
import {
  BY, P, t, bi, Icon, Card, Btn, Field, Input, Select, Textarea, Form, Grid, Stat,
  Pill, Empty, PageHead, SectionTitle, Table, Tr, Td, num, fmtDate, daysLeft,
} from "../kit.jsx";
import { TicketHead, TicketThread } from "./Account.jsx";
import { entityLabel } from "../auth.jsx";
import { postJSON } from "../media.jsx";

/* رسم Chart.js — المكتبة محمّلة من القالب عند الحاجة فقط.
   `enabled` إلزامي: بدونه يُستدعى build() قبل وصول البيانات من fetch
   فينهار الرسم على قيمة null ويُسقط شجرة React كلها (صفحة فارغة). */
function useChart(ref, build, deps, enabled) {
  useEffect(() => {
    if (!enabled || !ref.current || !window.Chart) return;
    const C = window.Chart;
    C.defaults.color = "#7B87A8";
    C.defaults.borderColor = "rgba(255,255,255,.08)";
    C.defaults.font.family = BY.lang === "en" ? "Inter,sans-serif" : "Cairo,sans-serif";
    const chart = new C(ref.current, build(C));
    return () => chart.destroy();
  }, deps);
}

/* ------------------------------------------------------------ نظرة عامة */
export function AdminOverview() {
  const s = P.stats || {};
  const [daily, setDaily] = useState(null);
  const revRef = useRef(null), usrRef = useRef(null);

  useEffect(() => {
    fetch("/api/admin/stats").then((r) => r.json()).then((d) => setDaily(d.daily)).catch(() => {});
  }, []);

  const labels = daily ? daily.labels.map((x) => x.slice(5)) : [];
  useChart(revRef, () => ({
    type: "bar",
    data: { labels, datasets: [{ data: daily.revenue, backgroundColor: "rgba(45,212,167,.55)", borderRadius: 7 }] },
    options: { plugins: { legend: { display: false } }, scales: { y: { beginAtZero: true } } },
  }), [daily], !!daily);
  useChart(usrRef, () => ({
    type: "line",
    data: { labels, datasets: [{ data: daily.new_users, borderColor: "#7C6CF6",
             backgroundColor: "rgba(124,108,246,.16)", tension: .35, fill: true }] },
    options: { plugins: { legend: { display: false } }, scales: { y: { beginAtZero: true, ticks: { precision: 0 } } } },
  }), [daily], !!daily);

  return (
    <>
      <PageHead icon="shield" title={t("admin_overview")}
        sub={bi("تحكّم كامل ومراقبة حية لكل شيء على المنصة.",
                "Full control and live monitoring of everything on the platform.")} />

      <Grid cols={4} className="mb-5">
        <Stat icon="users"  value={s.users}   label={t("st_users")} />
        <Stat icon="bot"    value={s.bots}    label={t("st_bots")} />
        <Stat icon="crown"  value={s.paying}  label={t("st_paying")} />
        <Stat icon="wallet" value={s.revenue} label={`${t("st_total_rev")} (${t("egp")})`} />
      </Grid>

      <div className="mb-6 grid gap-4 md:grid-cols-2">
        <Card spot as="a" href="/admin/users"
              className="flex items-center justify-between no-underline transition-transform duration-500 hover:-translate-y-1">
          <span className="flex items-center gap-3 font-extrabold text-ink">
            <Icon name="users" size={22} className="text-au-cyan" />{t("admin_users_t")}
          </span>
          <span className="tnum text-ink-3">{num(s.users)}</span>
        </Card>
        <Card spot as="a" href="/admin/payments"
              className="flex items-center justify-between no-underline transition-transform duration-500 hover:-translate-y-1">
          <span className="flex items-center gap-3 font-extrabold text-ink">
            <Icon name="card" size={22} className="text-au-cyan" />{t("admin_payments_t")}
          </span>
          {s.pending ? <Pill tone="warn" dot>{num(s.pending)} {t("st_pending")}</Pill>
                     : <span className="tnum text-ink-3">0</span>}
        </Card>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <Card><SectionTitle icon="wallet">{t("chart_revenue")}</SectionTitle>
          <canvas ref={revRef} height="200" /></Card>
        <Card><SectionTitle icon="users">{t("chart_newusers")}</SectionTitle>
          <canvas ref={usrRef} height="200" /></Card>
      </div>
    </>
  );
}

/* ------------------------------------------------------------- المستخدمون */
export function AdminUsers() {
  const { users = [], plans = [] } = P;
  const isAdmin = BY.user.role === "admin";
  return (
    <>
      <PageHead icon="users" title={t("admin_users_t")}
        actions={<Btn variant="ghost" sm icon="back" href="/admin">{t("back")}</Btn>} />

      {isAdmin && (
        <Card className="mb-6">
          <SectionTitle icon="plus">{t("add_user")}</SectionTitle>
          <Form action="/admin/users/add">
            <div className="grid gap-4 sm:grid-cols-3">
              <Field label={t("username")}><Input name="username" required minLength={3} /></Field>
              <Field label={t("password")} hint={bi("8+ فيها حرف كبير وصغير ورقم ورمز", "8+ with upper, lower, number and symbol")}>
                <Input type="password" name="password" required minLength={8} autoComplete="new-password" />
              </Field>
              <Field label={t("role")}>
                <Select name="role" defaultValue="user">
                  <option value="user">{t("role_user")}</option>
                  <option value="support">{t("role_support")}</option>
                  <option value="admin">{t("role_admin")}</option>
                </Select>
              </Field>
            </div>
            <div className="mt-5"><Btn icon="plus" type="submit">{t("create_account_btn")}</Btn></div>
          </Form>
        </Card>
      )}

      <Card>
        <Table head={["#", t("username"), bi("التواصل", "Contact"), t("role"), t("col_plan2"), t("col_bots"), t("col_status"), ""]}>
          {users.map((u) => (
            <Tr key={u.id}>
              <Td className="tnum">{u.id}</Td>
              <Td>
                <span className="font-bold text-ink">{u.username}</span>
                {u.is_blocked ? <span className="ms-2"><Pill tone="off">{t("blocked")}</Pill></span> : null}
              </Td>
              <Td className="max-w-[230px] text-[12.5px] leading-relaxed">
                {u.email ? (
                  <div className="truncate" dir="ltr">
                    {u.email}{u.email_verified_at ? <span className="ms-1 text-au-teal">✓</span> : null}
                  </div>
                ) : <span className="text-ink-4">—</span>}
                {u.phone && (
                  <div className="text-ink-3" dir="ltr">
                    {u.phone}{u.phone_verified_at ? <span className="ms-1 text-au-teal">✓</span> : null}
                  </div>
                )}
                {u.entity_type && <div className="text-ink-3">{entityLabel(u.entity_type)}{u.age ? ` · ${u.age}` : ""}</div>}
              </Td>
              <Td>
                {isAdmin && u.id !== 1 ? (
                  <Form action={`/admin/users/${u.id}/role`} className="inline">
                    <Select name="role" defaultValue={u.role} onChange={(e) => e.target.form.submit()}
                            className="!w-auto !py-1.5 !text-[13px]">
                      <option value="user">{t("role_user")}</option>
                      <option value="support">{t("role_support")}</option>
                      <option value="admin">{t("role_admin")}</option>
                    </Select>
                  </Form>
                ) : <Pill tone="mute">{t("role_" + u.role)}</Pill>}
              </Td>
              <Td>
                {u.role === "admin" ? <span className="hue font-bold">{t("owner_unlimited")}</span> : (
                  <div>
                    <div>{u.plan}</div>
                    {u.expires_at && u.plan !== "free" && (
                      <div className="text-[11.5px] text-ink-3">
                        {fmtDate(u.expires_at)} · {daysLeft(u.expires_at)} {t("days_left")}
                      </div>
                    )}
                  </div>
                )}
              </Td>
              <Td className="tnum">{num(u.bots)}</Td>
              <Td>{u.sub_status === "active" && u.plan !== "free"
                ? <Pill tone="on">{t("status_active")}</Pill> : <span className="text-ink-3">—</span>}</Td>
              <Td>
                {isAdmin && u.id !== 1 && (
                  <div className="flex flex-wrap items-center gap-2">
                    <Form action={`/admin/users/${u.id}/plan`} className="inline">
                      <Select name="plan" defaultValue="" onChange={(e) => e.target.form.submit()}
                              className="!w-auto !py-1.5 !text-[12.5px]">
                        <option value="">{t("set_plan")}</option>
                        {plans.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
                      </Select>
                    </Form>
                    <Form action={`/admin/users/${u.id}/block/${u.is_blocked ? 0 : 1}`} className="inline">
                      <Btn sm type="submit" variant={u.is_blocked ? "green" : "red"}
                           icon={u.is_blocked ? "check" : "ban"}>
                        {u.is_blocked ? t("action_unblock") : t("action_block")}
                      </Btn>
                    </Form>
                  </div>
                )}
              </Td>
            </Tr>
          ))}
        </Table>
      </Card>
    </>
  );
}

/* -------------------------------------------------------------- المدفوعات */
const OCR_OFF = {
  no_module: ["مكتبة قراءة الإيصالات مش متثبّتة على السيرفر.", "The receipt-reading library isn't installed on the server."],
  no_binary: ["برنامج tesseract مش متاح للخدمة على السيرفر.", "tesseract isn't available to the service on the server."],
  no_lang:   ["لغات القراءة (عربي/إنجليزي) مش متثبّتة.", "The OCR languages (Arabic/English) aren't installed."],
  disabled:  ["القراءة متوقفة بالإعداد BOTYALLA_OCR=0.", "Reading is disabled by BOTYALLA_OCR=0."],
};
const REFUSED = {
  not_receipt:     ["مش إيصال", "Not a receipt"],
  duplicate:       ["إيصال مستخدم", "Reused receipt"],
  wrong_recipient: ["مستلم تاني", "Wrong recipient"],
  amount_mismatch: ["مبلغ مختلف", "Wrong amount"],
};

/* حالة الفحص الآلي: بدون قراءة الإيصالات لا يُرفض شيء آلياً — فالسبب والحل ظاهران */
function ReceiptEngine({ ocr = {}, refused24 = 0, refusals = [] }) {
  return (
    <>
      {!ocr.ok && (
        <Card className="mb-5 bg-[linear-gradient(120deg,rgb(248_113_113/0.14),transparent)]">
          <SectionTitle icon="ban">{bi("الفحص الآلي للإيصالات متوقف", "Automatic receipt checks are off")}</SectionTitle>
          <p className="m-0 text-[13px] leading-relaxed text-ink-2">
            {OCR_OFF[ocr.reason] ? bi(...OCR_OFF[ocr.reason]) + " " : ""}
            {bi("من غيره مفيش رفض آلي — كل صورة بتستنى مراجعتك. الحل على السيرفر:",
                "Without it nothing is refused automatically — every image waits for you. Fix it on the server:")}
          </p>
          <code dir="ltr" className="mt-3 block overflow-x-auto rounded-lg bg-black/40 px-3 py-2 text-[12.5px] text-ink">
            sudo bash /opt/botyalla/deploy/hostinger_deploy.sh --update
          </code>
        </Card>
      )}
      <Card className="mb-5">
        <SectionTitle icon="shield"
          extra={ocr.ok ? <Pill tone="on" dot>{bi("الفحص الآلي شغّال", "Auto-check on")}</Pill>
                        : <Pill tone="off">{bi("الفحص الآلي متوقف", "Auto-check off")}</Pill>}>
          {bi("رفض آلي — آخر 24 ساعة:", "Auto-refused — last 24h:")} <span className="tnum">{num(refused24)}</span>
        </SectionTitle>
        <p className="mt-0 mb-3 text-[12.5px] leading-relaxed text-ink-3">
          {bi("الصور اللي مش إيصال، أو إيصال لتحويل على رقم تاني أو بمبلغ تاني، أو إيصال مستخدم قبل كده — بتترفض قبل ما توصلك، والعميل بيعرف السبب فوراً. اللي بيعدّي بيستنى موافقتك دايماً.",
              "Images that aren't receipts, receipts for another account or amount, and reused receipts are refused before they reach you — the customer sees why at once. Whatever passes still waits for your approval.")}
          {ocr.ok && ocr.reason === "no_ara" && (
            <span className="mt-1 block text-yellow-300">
              {bi("القراءة شغّالة بالإنجليزي بس — ثبّت tesseract-ocr-ara عشان الكلمات العربية.",
                  "Reading works in English only — install tesseract-ocr-ara for Arabic words.")}
            </span>
          )}
        </p>
        {refusals.length > 0 && (
          <div className="flex flex-wrap gap-2">
            {refusals.map((r) => (
              <span key={r.id} className="rounded-lg bg-white/[0.04] px-2.5 py-1 text-[12px] text-ink-3">
                <b className="text-ink-2">{r.username || "?"}</b> · {REFUSED[r.reason] ? bi(...REFUSED[r.reason]) : r.reason}
                {" · "}<span className="tnum">{fmtDate(r.created_at)}</span>
              </span>
            ))}
          </div>
        )}
      </Card>
    </>
  );
}

export function AdminPayments() {
  const { pays = [], names = {} } = P;
  const isAdmin = BY.user.role === "admin";
  const tone = { pending: "warn", approved: "on", rejected: "off" };
  const label = { pending: t("status_pending"), approved: t("status_approved"), rejected: t("status_rejected") };

  return (
    <>
      <PageHead icon="card" title={t("admin_payments_t")}
        actions={<Btn variant="ghost" sm icon="back" href="/admin">{t("back")}</Btn>} />

      <ReceiptEngine ocr={P.ocr} refused24={P.refused24} refusals={P.refusals} />

      <Card>
        <p className="mt-0 mb-5 text-[13px] text-ink-3">
          {bi("صور الإيصالات تُرسل لك على تليجرام أيضاً مع أزرار الموافقة.",
              "Receipts are also sent to you on Telegram with approval buttons.")}
          {" · "}<b className="text-ink-2">{t("auto_note")}</b>
        </p>
        {pays.length ? (
          <Table head={["#", t("username"), t("col_plan2"), t("col_amount"), t("col_method"),
                        t("col_receipt"), t("auto_check_col"), t("col_status"), ""]}>
            {pays.map((x) => (
              <Tr key={x.id}>
                <Td className="tnum">{x.id}</Td>
                <Td className="font-bold text-ink">{x.uname}</Td>
                <Td>{names[x.plan] || x.plan}</Td>
                <Td className="tnum">{num(x.amount)} {t("egp")}</Td>
                <Td>{x.method}</Td>
                <Td>
                  {x.screenshot ? (
                    <a href={`/admin/payments/${x.id}/screenshot`} target="_blank" rel="noopener"
                       title={t("view_receipt")}>
                      <img src={`/admin/payments/${x.id}/screenshot`} alt="receipt"
                           className="size-[52px] rounded-lg bg-white object-cover
                                      shadow-[inset_0_0_0_1px_rgb(255_255_255/0.12)]" />
                    </a>
                  ) : <span className="text-ink-3">{t("no_receipt")}</span>}
                </Td>
                <Td className="min-w-[230px]">
                  <div className="flex flex-col gap-1 text-[12px] leading-relaxed">
                    {(x.checks || []).map((c, i) => (
                      <span key={i} className={c.ok === true ? "text-au-teal" : c.ok === false ? "text-red-300" : "text-yellow-300"}>
                        <Icon name={c.ok === true ? "check" : c.ok === false ? "close" : "pending"} size={13}
                              className="me-1 align-[-2px]" />{c.text}
                      </span>
                    ))}
                  </div>
                </Td>
                <Td><Pill tone={tone[x.status]}>{label[x.status]}</Pill></Td>
                <Td>
                  {x.status === "pending" && isAdmin && (
                    <div className="flex gap-2">
                      <Form action={`/admin/payments/${x.id}/approve`} className="inline"
                            confirm={bi("تأكيد الموافقة وتفعيل الاشتراك؟", "Approve and activate this subscription?")}>
                        <Btn sm variant="green" icon="check" type="submit">{t("approve")}</Btn>
                      </Form>
                      <Form action={`/admin/payments/${x.id}/reject`} className="inline">
                        <Btn sm variant="red" icon="ban" type="submit">{t("reject")}</Btn>
                      </Form>
                    </div>
                  )}
                </Td>
              </Tr>
            ))}
          </Table>
        ) : <Empty icon="card" title={t("no_payments")} />}
      </Card>
    </>
  );
}

/* ---------------------------------------------------------------- الطلبات */
export function AdminRequests() {
  const reqs = P.reqs || [];
  const isAdmin = BY.user.role === "admin";
  const tone = { new: "warn", in_progress: "mute", done: "on", rejected: "off" };
  const label = { new: t("req_status_new"), in_progress: t("req_status_in_progress"),
                  done: t("req_status_done"), rejected: t("req_status_rejected") };
  return (
    <>
      <PageHead icon="inbox" title={t("admin_requests_t")}
        actions={<Btn variant="ghost" sm icon="back" href="/admin">{t("back")}</Btn>} />
      <Card>
        {reqs.length ? (
          <Table head={["#", t("username"), t("col_business"), t("col_request"),
                        t("col_phone"), t("col_status"), ""]}>
            {reqs.map((r) => (
              <Tr key={r.id}>
                <Td className="tnum">{r.id}</Td>
                <Td className="font-bold text-ink">{r.username}</Td>
                <Td>{r.business || "—"}</Td>
                <Td className="max-w-[340px]">
                  <div>{r.description}</div>
                  {r.budget && <div className="mt-1 flex items-center gap-1 text-[12px] text-ink-3">
                    <Icon name="coins" size={13} />{r.budget}</div>}
                </Td>
                <Td>{r.contact || "—"}</Td>
                <Td><Pill tone={tone[r.status]}>{label[r.status]}</Pill></Td>
                <Td>
                  {isAdmin && (
                    <div className="flex flex-wrap gap-2">
                      {[["in_progress", "ghost", t("req_status_in_progress")],
                        ["done", "green", t("req_status_done")],
                        ["rejected", "red", t("req_status_rejected")]].map(([st, v, lb]) => (
                        <Form key={st} action={`/admin/requests/${r.id}/${st}`} className="inline">
                          <Btn sm variant={v} type="submit">{lb}</Btn>
                        </Form>
                      ))}
                    </div>
                  )}
                </Td>
              </Tr>
            ))}
          </Table>
        ) : <Empty icon="inbox" title={t("no_requests")} />}
      </Card>
    </>
  );
}

/* ربط واتساب نيابةً عن العميل — من تذكرة «ربط واتساب» وحدها. الخادم يُنشئ البوت في
   حساب العميل وبحدود باقته هو، والتوكن يُرسل مرة: لا يُعرض ولا يُكتب في التذكرة. */
function WaConnect({ tk }) {
  const w = tk.wa || {};
  const blocked = !w.ok || w.full;
  const origin = typeof window !== "undefined" ? window.location.origin : "";
  return (
    <details open={tk.status !== "closed"}
             className="mt-4 rounded-xl bg-white/[0.03] p-4 shadow-[inset_0_0_0_1px_rgb(45_212_167/0.3)]">
      <summary className="flex cursor-pointer list-none flex-wrap items-center gap-2 text-[14px] font-extrabold text-ink
                          [&::-webkit-details-marker]:hidden">
        <Icon name="phone" size={16} className="text-au-teal" />
        {bi("ربط واتساب للعميل", "Connect WhatsApp for the customer")}
        <Pill tone={w.ok ? "on" : "off"}>{w.plan}</Pill>
        <Pill tone={w.full ? "off" : "mute"}>
          {bi("البوتات", "Bots")} <span className="tnum">{w.bots}/{w.max >= 9999 ? "∞" : w.max}</span>
        </Pill>
        {w.waBots > 0 && <Pill tone="on">{bi(`عنده ${w.waBots} بوت واتساب`, `${w.waBots} WhatsApp bot(s)`)}</Pill>}
      </summary>
      <ol className="mt-3 mb-4 ps-5 text-[12.5px] leading-relaxed text-ink-2">
        <li>{bi("اطلب من العميل في الرد يضيفك مسؤولاً على حساب Meta Business بتاعه — ولا تطلب كلمة سره أو كود تحقق أبداً.",
                "Ask the customer (in a reply) to add you as an admin on their Meta Business account — never ask for a password or a code.")}</li>
        <li>{bi("من developers.facebook.com: تطبيق Business ← WhatsApp ← أضف رقمه ووثّقه، ثم System User بتوكن دائم (whatsapp_business_messaging و whatsapp_business_management).",
                "On developers.facebook.com: Business app → WhatsApp → add and verify the number, then a System User with a permanent token (whatsapp_business_messaging and whatsapp_business_management).")}</li>
        <li>
          Webhook: <code className="rounded bg-white/10 px-1.5 py-0.5" dir="ltr">{origin}/wh/whatsapp</code>
          {bi(" بالـ Verify token من إعدادات المنصة، واشترك في messages.",
              " with the Verify token from platform settings; subscribe to messages.")}
        </li>
        <li>{bi("الصق البيانات هنا — البوت يتنشأ في حساب العميل ويوصله إشعار في التذكرة.",
                "Paste the details here — the bot is created in the customer's account and they're notified in the ticket.")}</li>
      </ol>
      {!w.ok && (
        <p className="mt-0 mb-3 text-[12.5px] font-bold text-red-300">
          {bi("باقة العميل لا تشمل واتساب — اطلب منه الترقية أولاً.", "The customer's plan doesn't include WhatsApp — ask them to upgrade first.")}
        </p>
      )}
      {w.ok && w.full && (
        <p className="mt-0 mb-3 text-[12.5px] font-bold text-red-300">
          {bi("العميل وصل للحد الأقصى لبوتات باقته.", "The customer reached their plan's bot limit.")}
        </p>
      )}
      <Form action={`/admin/tickets/${tk.id}/wa-connect`}
            confirm={bi(`إنشاء بوت واتساب في حساب ${tk.username}؟`, `Create a WhatsApp bot in ${tk.username}'s account?`)}>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label={bi("اسم البوت", "Bot name")}>
            <Input name="name" required maxLength={60} defaultValue={w.biz || ""} />
          </Field>
          <Field label={bi("نوع البوت", "Bot type")}>
            <Select name="template" defaultValue="customer_service">
              {BY.templates.map((x) => <option key={x.k} value={x.k}>{x.label}</option>)}
            </Select>
          </Field>
          <Field label="Phone Number ID">
            <Input name="wa_phone_id" required inputMode="numeric" pattern="[0-9]+" autoComplete="off" dir="ltr" />
          </Field>
          <Field label={`WABA ID (${t("optional")})`}
                 hint={bi("لازم لقوالب Meta — تقدر تضيفه بعدين من صفحة القوالب.", "Needed for Meta templates — can be added later on the templates page.")}>
            <Input name="waba_id" inputMode="numeric" pattern="[0-9]*" autoComplete="off" dir="ltr" />
          </Field>
          <Field label="Access Token" className="sm:col-span-2">
            <Input type="password" name="wa_token" required autoComplete="off" spellCheck="false" dir="ltr"
                   placeholder="EAAG…" />
          </Field>
        </div>
        <div className="mt-4">
          <Btn sm icon="rocket" type="submit" disabled={blocked}>
            {bi("أنشئ البوت في حساب العميل", "Create the bot in the customer's account")}
          </Btn>
        </div>
      </Form>
    </details>
  );
}

/* ---------------------------------------------------------- تذاكر الدعم */
export function AdminTickets() {
  const tickets = P.tickets || [];
  const [show, setShow] = useState("open");
  const open = tickets.filter((x) => x.status !== "closed");
  const list = show === "open" ? open : show === "closed" ? tickets.filter((x) => x.status === "closed") : tickets;
  const tabs = [["open", bi("مفتوحة", "Open"), open.length],
                ["closed", bi("مقفولة", "Closed"), tickets.length - open.length],
                ["all", bi("الكل", "All"), tickets.length]];
  return (
    <>
      <PageHead icon="chat" title={t("nav_tickets")}
        sub={bi("كل تذكرة بتوصلك على بوت المنصة لحظة إرسالها — ردّ عليها بـ Reply في تليجرام أو من هنا.",
                "Every ticket reaches you on the platform bot the moment it's sent — answer with Reply in Telegram or here.")}
        actions={<Btn variant="ghost" sm icon="back" href="/admin">{t("back")}</Btn>} />
      <div className="mb-5 flex flex-wrap gap-2">
        {tabs.map(([k, l, n]) => (
          <button key={k} type="button" onClick={() => setShow(k)} aria-pressed={show === k}
            className={`rounded-xl px-3.5 py-2 text-[13px] font-bold transition
              ${show === k ? "bg-au-cyan/15 text-ink shadow-[inset_0_0_0_1px_rgb(143_233_255/0.45)]"
                           : "text-ink-3 shadow-[inset_0_0_0_1px_rgb(255_255_255/0.1)] hover:text-ink"}`}>
            {l} <span className="tnum opacity-70">{n}</span>
          </button>
        ))}
      </div>
      {list.length ? list.map((tk) => (
        <Card key={tk.id} id={`t${tk.id}`} className="mb-4">
          <TicketHead tk={tk} who />
          <TicketThread tk={tk} staffView />
          {tk.kind === "wa_setup" && <WaConnect tk={tk} />}
          <div className="mt-4 flex flex-col gap-3 lg:flex-row lg:items-end">
            <Form action={`/admin/tickets/${tk.id}/reply`} className="flex flex-1 flex-col gap-2 sm:flex-row sm:items-end">
              <Textarea name="body" required minLength={2} maxLength={3000} className="min-h-[52px] flex-1"
                        placeholder={bi("اكتب ردّك للعميل…", "Write your reply…")} />
              <Btn sm icon="chat" type="submit">{bi("رد", "Reply")}</Btn>
            </Form>
            <Form action={`/admin/tickets/${tk.id}/${tk.status === "closed" ? "open" : "close"}`} className="inline">
              <Btn sm variant={tk.status === "closed" ? "ghost" : "green"}
                   icon={tk.status === "closed" ? "refresh" : "check"} type="submit">
                {tk.status === "closed" ? bi("افتحها تاني", "Reopen") : bi("تم الحل", "Resolve")}
              </Btn>
            </Form>
          </div>
        </Card>
      )) : <Card><Empty icon="chat" title={bi("مفيش تذاكر هنا", "No tickets here")} /></Card>}
    </>
  );
}

/* ------------------------------------------------------ إحصائيات الزوار */
/* قياس داخل المنصة (لا سكربت خارجي ولا كوكي تتبّع): زوار الصفحات العامة ومصادرهم، وقمع
   التسجيل على دفعة من سجّلوا في الفترة. النسبة الحاكمة: مسجّل ← بوت شغّال — تحت 40% المشكلة
   في المنتج لا في التسويق، وفوق 60% الإنفاق على الإعلان مبرَّر. */
export function AdminAnalytics() {
  const a = P.a || {};
  const f = a.funnel || {};
  const pct = (x, y) => (y ? Math.round((x / y) * 100) : 0);
  const live = pct(f.bot_live || 0, f.signup || 0);
  const tone = !f.signup ? "text-ink-3" : live < 40 ? "text-red-300" : live < 60 ? "text-amber-200" : "text-au-teal";
  const maxDay = Math.max(1, ...(a.daily || []).map((d) => d.v));
  const steps = [
    ["signup", bi("سجّلوا", "Signed up")],
    ["bot_created", bi("أنشأوا بوتاً", "Created a bot")],
    ["bot_live", bi("شغّلوا البوت", "Bot is live")],
    ["first_message", bi("وصلتهم أول رسالة من عميل", "Got a first customer message")],
    ["payment_sent", bi("أرسلوا دفعة اشتراك", "Sent a subscription payment")],
    ["paid", bi("اشتراك معتمد", "Paid subscription")],
  ];
  const Kpi = ({ label, value, hint, cls = "text-ink" }) => (
    <Card className="!p-5">
      <div className="text-[12.5px] font-bold text-ink-3">{label}</div>
      <div className={`mt-1 tnum text-[26px] font-extrabold ${cls}`}>{value}</div>
      {hint && <div className="mt-1 text-[12px] leading-relaxed text-ink-3">{hint}</div>}
    </Card>
  );
  const List = ({ title, icon, items }) => (
    <Card>
      <SectionTitle icon={icon}>{title}</SectionTitle>
      {items && items.length ? (
        <div className="flex flex-col gap-2.5">
          {items.map((x) => (
            <div key={x.k} className="flex items-center gap-3 text-[13.5px]">
              <span className="min-w-0 flex-1 truncate text-ink-2" dir="ltr">{x.k}</span>
              <span className="tnum font-bold text-ink">{num(x.v)}</span>
            </div>
          ))}
        </div>
      ) : <Empty icon={icon} title={bi("لا بيانات بعد", "No data yet")} />}
    </Card>
  );
  return (
    <>
      <PageHead icon="chart" title={t("adm_analytics")}
        sub={bi("زوار الصفحات العامة ومصادرهم، وأين يتوقف المسجّلون — بلا كوكي تتبّع ولا سكربت خارجي.",
                "Public-page visitors and their sources, and where signups stall — no tracking cookie, no third-party script.")}
        actions={<div className="flex gap-2">{[7, 30, 90].map((d) => (
          <Btn key={d} sm variant={a.days === d ? "primary" : "ghost"} href={`?days=${d}`}>
            {bi(`${d} يوم`, `${d} days`)}
          </Btn>))}</div>} />

      <Grid cols={4} className="mb-6">
        <Kpi label={bi("زوار فريدون", "Unique visitors")} value={num(a.visitors)}
             hint={bi(`${num(a.views)} مشاهدة صفحة`, `${num(a.views)} page views`)} />
        <Kpi label={bi("زاروا صفحة الأسعار", "Viewed pricing")} value={num(a.pricing_visitors)}
             hint={bi(`${pct(a.pricing_visitors, a.visitors)}% من الزوار`, `${pct(a.pricing_visitors, a.visitors)}% of visitors`)} />
        <Kpi label={bi("تسجيلات", "Signups")} value={num(f.signup)}
             hint={bi(`${pct(f.signup, a.visitors)}% من الزوار`, `${pct(f.signup, a.visitors)}% of visitors`)} />
        <Kpi label={bi("مسجّل ← بوت شغّال", "Signup → live bot")} value={`${live}%`} cls={tone}
             hint={bi("تحت 40% راجع المنتج قبل الإعلان · فوق 60% الإعلان مبرَّر",
                      "Under 40%: fix the product first · above 60%: ads are justified")} />
      </Grid>

      <Card className="mb-6">
        <SectionTitle icon="users">{bi("القمع — من سجّلوا خلال الفترة", "Funnel — people who signed up in this period")}</SectionTitle>
        <div className="flex flex-col gap-3">
          {steps.map(([k, label], i) => {
            const n = f[k] || 0;
            const prev = i ? f[steps[i - 1][0]] || 0 : n;
            return (
              <div key={k}>
                <div className="mb-1 flex flex-wrap items-center gap-2 text-[13px]">
                  <span className="font-bold text-ink">{label}</span>
                  <span className="ms-auto tnum text-ink-2">{num(n)}</span>
                  {i > 0 && <span className="tnum text-[12px] text-ink-3">· {pct(n, prev)}% {bi("من السابقة", "of previous")}</span>}
                </div>
                <div className="h-2 overflow-hidden rounded-full bg-white/[0.07]">
                  <div className="h-full rounded-full bg-[linear-gradient(90deg,#8FE9FF,#B9AFFF)]"
                       style={{ width: `${pct(n, f.signup || 0)}%` }} />
                </div>
              </div>
            );
          })}
        </div>
      </Card>

      <Card className="mb-6">
        <SectionTitle icon="chart">{bi("الزوار يومياً", "Visitors per day")}</SectionTitle>
        {(a.daily || []).length ? (
          <div className="flex h-36 items-end gap-1" dir="ltr">
            {a.daily.map((d) => (
              <div key={d.day} title={`${d.day} · ${d.v}`} className="flex-1 rounded-t bg-au-cyan/60 hover:bg-au-cyan"
                   style={{ height: `${Math.max(3, (d.v / maxDay) * 100)}%` }} />
            ))}
          </div>
        ) : <Empty icon="chart" title={bi("لا زيارات بعد", "No visits yet")} />}
      </Card>

      <Grid cols={2} className="mb-6">
        <List icon="link" title={bi("مصادر الزيارات", "Traffic sources")} items={a.sources} />
        <List icon="users" title={bi("مصادر التسجيلات", "Signup sources")} items={a.signup_sources} />
        <List icon="grid" title={bi("أكثر الصفحات زيارة", "Top pages")} items={a.pages} />
        <List icon="phone" title={bi("الأجهزة", "Devices")} items={a.devices} />
      </Grid>
      <p className="m-0 text-[12px] leading-relaxed text-ink-3">
        {bi("المصدر من ?utm_source= في رابط الحملة (مثال: botyalla.com/?utm_source=tiktok)، أو دومين الموقع المُحيل. الزائر الفريد يُعدّ مرة لكل يوم.",
            "The source comes from ?utm_source= in the campaign link (e.g. botyalla.com/?utm_source=tiktok), or the referring site. A unique visitor is counted once per day.")}
      </p>
    </>
  );
}

/* -------------------------------------------------------------- المنصة */
export function AdminPlatform() {
  const { plat = {}, running, capacity = null, managed = {} } = P;
  const F = ({ name, label, ph }) => (
    <Field label={label}><Input name={name} defaultValue={plat[name] || ""} placeholder={ph} /></Field>
  );
  return (
    <>
      {/* خارج نموذج الحفظ — لا نماذج متداخلة */}
      <PageHead icon="shield" title={t("platform_title")} sub={t("platform_sub")}
        actions={<Form action="/admin/platform/test-notify" className="inline">
                   <Btn sm variant="ghost" icon="bolt" type="submit">{t("plat_test_btn")}</Btn>
                 </Form>} />
      <Form action="">
        <Card className="mb-5">
          <SectionTitle icon="wallet">{t("plat_payment")}</SectionTitle>
          <div className="grid gap-4 sm:grid-cols-2">
            <F name="vodafone_number" label={t("pay_vodafone")} />
            <F name="instapay_handle" label={`${t("pay_instapay")} — ${t("pay_handle")}`} />
          </div>
          <div className="mt-4"><F name="instapay_link" label={`${t("pay_instapay")} — ${t("pay_open_link")}`} /></div>
          <div className="mt-4 grid gap-4 sm:grid-cols-2">
            <F name="bank_holder" label={t("pay_holder")} />
            <F name="bank_name" label={t("pay_bankname")} />
            <F name="bank_account" label={t("pay_account")} />
            <F name="bank_iban" label={t("pay_iban")} />
          </div>
          <div className="mt-4 max-w-[360px]">
            <F name="addon_pay_price" ph="99"
               label={bi("سعر إضافة «تحصيل المدفوعات» (ج.م شهرياً لكل بوت)",
                         "Payments add-on price (EGP / month / bot)")} />
          </div>
          <p className="mt-4 mb-0 text-[12.5px] text-ink-3">
            {bi("صورة QR انستاباي محفوظة في static/instapay_qr.jpg — استبدلها بصورتك عند الحاجة.",
                "InstaPay QR is stored at static/instapay_qr.jpg — replace it with yours when needed.")}
          </p>
        </Card>

        <Card className="mb-5">
          <SectionTitle icon="bot"
            extra={running ? <Pill tone="on" dot>{t("plat_running")}</Pill> : <Pill tone="off">{t("plat_stopped")}</Pill>}>
            {t("plat_bot")}
          </SectionTitle>
          <p className="mt-0 mb-4 text-[13px] text-ink-3">{t("plat_bot_desc")}</p>
          {/* الإنشاء بضغطة يحتاج «Bot Management Mode» لبوت المنصة (can_manage_bots من getMe) */}
          <div className="mb-4 flex flex-wrap items-center gap-2 rounded-xl bg-white/[0.03] px-3.5 py-3
                          shadow-[inset_0_0_0_1px_rgb(255_255_255/0.07)]">
            <span className="text-[13px] font-bold text-ink">{t("plat_managed")}</span>
            {managed.can_manage
              ? <Pill tone="on" dot>{t("plat_managed_on")}{managed.username ? ` · @${managed.username}` : ""}</Pill>
              : <Pill tone="off">{t("plat_managed_off")}</Pill>}
            {!managed.can_manage && <p className="m-0 w-full text-[12px] leading-relaxed text-ink-3">{t("onetap_admin_hint")}</p>}
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <F name="platform_bot_token" label={t("plat_bot_token")} ph="123456:ABC-..." />
            <F name="admin_chat_id" label={t("plat_admin_id")} ph="123456789" />
          </div>
          <p className="mt-3 mb-0 text-[12.5px] text-ink-3">
            <a href="https://t.me/userinfobot" target="_blank" rel="noopener"
               className="text-au-cyan underline-offset-4 hover:underline">@userinfobot ↗</a>{" "}
            {bi("لمعرفة معرّفك.", "to get your ID.")}
          </p>
        </Card>

        <Card className="mb-5">
          <SectionTitle icon="phone">WhatsApp Cloud API</SectionTitle>
          <p className="mt-0 mb-4 text-[13px] text-ink-3">
            {bi("بدون هذين الحقلين يرفض الويبهوك كل الطلبات — بوتات واتساب لن تستقبل شيئاً.",
                "Without these two the webhook refuses everything — WhatsApp bots receive nothing.")}
          </p>
          <div className="grid gap-4 sm:grid-cols-2">
            <F name="wa_verify_token" label="Verify Token" ph={bi("نص من اختيارك تكرره في Meta", "any string, repeated in Meta")} />
            <F name="wa_app_secret" label={bi("App Secret — تطبيق رقم المنصة", "App Secret — platform number's app")}
               ph="Meta → App settings → Basic" />
            <F name="wa_es_app_secret"
               label={bi("App Secret — تطبيق Tech Provider (الربط بضغطة)", "App Secret — Tech Provider app (one-tap)")}
               ph={bi("لو نفس التطبيق سيبه فاضي", "leave empty if it's the same app")} />
          </div>
          <p className="mt-3 mb-0 text-[12.5px] leading-relaxed text-ink-3">
            {bi("الربط بضغطة بيستخدم سرّ تطبيق الـTech Provider (نفس META_APP_ID). والويبهوك بيقبل رسايل موقّعة بأي واحد من السرّين — فاضبط نفس عنوان الويبهوك ونفس Verify Token في التطبيقين.",
                "One-tap signup uses the Tech Provider app's secret (same app as META_APP_ID). The webhook accepts messages signed with either secret — set the same webhook URL and Verify Token in both apps.")}
          </p>
          <p className="mt-3 mb-0 text-[12.5px] text-ink-3">
            {bi("عنوان الويبهوك في Meta:", "Webhook URL in Meta:")}{" "}
            <code className="rounded bg-white/10 px-1.5 py-0.5">
              {typeof window !== "undefined" ? window.location.origin : ""}/wh/whatsapp
            </code>
          </p>
        </Card>

        {/* قيمتان تتغيّران مع السوق والخادم — تُعدَّلان هنا بلا نشر */}
        <Card className="mb-5">
          <SectionTitle icon="wallet">{t("plat_ops")}</SectionTitle>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label={t("plat_mkt_price")} hint={t("plat_mkt_price_h")}>
              <Input name="mkt_msg_price_egp" type="number" step="0.01" min="0.01" max="1000"
                     inputMode="decimal" dir="ltr" defaultValue={plat.mkt_msg_price_egp || ""} />
            </Field>
            <Field label={t("plat_ai_price")} hint={t("plat_ai_price_h")}>
              <Input name="ai_reply_price_egp" type="number" step="0.01" min="0.01" max="100"
                     inputMode="decimal" dir="ltr" defaultValue={plat.ai_reply_price_egp || ""} />
            </Field>
            <Field label={t("plat_capacity")}
                   hint={capacity ? t("plat_capacity_h").replace("{r}", capacity.running)
                                                        .replace("{c}", capacity.capacity) : ""}>
              <Input name="bot_capacity" type="number" step="1" min="1" inputMode="numeric" dir="ltr"
                     defaultValue={plat.bot_capacity || ""}
                     placeholder={capacity ? String(capacity.capacity) : ""} />
            </Field>
          </div>
        </Card>

        <Card>
          <SectionTitle icon="phone">{t("plat_contact")}</SectionTitle>
          <div className="grid gap-4 sm:grid-cols-3">
            <F name="support_email" label={t("plat_email")} ph="info@botyalla.com" />
            <F name="support_whatsapp" label={t("plat_whatsapp")} ph="201097585951" />
            <F name="support_telegram" label={t("plat_telegram")} ph="username" />
          </div>
          <div className="mt-6"><Btn icon="check" type="submit">{t("save")}</Btn></div>
        </Card>
      </Form>
    </>
  );
}

/* ------------------------------------------------------ روابط الحملات لكل شريحة
   كل ما يلزم لإطلاق إعلانات Click-to-WhatsApp/Telegram: صفحة الهبوط بـ utm، رابط البوت
   الرسمي برمز الشريحة (يُحتسب مصدره ويرحّب بلغة النشاط)، QR للتحميل، وعدد المحادثات. */
export function AdminGrowth() {
  const rows = P.rows || [];
  const o = P.optins || {};
  const [copied, setCopied] = useState("");
  const copy = (k, v) => navigator.clipboard?.writeText(v).then(() => { setCopied(k); setTimeout(() => setCopied(""), 1400); });
  const Link = ({ id, label, url, qr }) => url ? (
    <div className="flex flex-wrap items-center gap-2">
      <span className="w-[74px] shrink-0 text-[12px] font-extrabold text-ink-3">{label}</span>
      <code dir="ltr" className="min-w-0 flex-1 truncate rounded-lg bg-black/25 px-2.5 py-1.5 text-[12px] text-ink-2">{url}</code>
      <Btn sm variant="ghost" icon={copied === id ? "check" : "link"} type="button" onClick={() => copy(id, url)}>
        {copied === id ? bi("اتنسخ", "Copied") : bi("نسخ", "Copy")}
      </Btn>
      <Btn sm variant="ghost" icon="download" href={qr}>QR</Btn>
    </div>
  ) : null;
  return (
    <>
      <PageHead icon="megaphone" title={t("adm_growth")}
        sub={bi("لكل نشاط: صفحة هبوط للإعلانات، ورابط يفتح بوتنا الرسمي مباشرة (Click-to-WhatsApp / Telegram) — العميل هو اللي بيبدأ المحادثة فالتواصل مسموح ومجاني 72 ساعة من إعلانات Meta.",
                "Per segment: an ad landing page and a link that opens our official bot directly (Click-to-WhatsApp / Telegram) — the customer starts the chat, so messaging is allowed and free for 72h from Meta ads.")} />
      {!P.official && (
        <Card className="mb-6"><p className="m-0 text-[13.5px] font-bold text-yellow-200">
          {bi("فعّل «مساعد BotYalla الرسمي» و«عقل البوت» على بوت واتساب الإدارة أولاً — منه تُبنى روابط واتساب.",
              "Enable “Official BotYalla assistant” and “Bot brain” on the admin WhatsApp bot first — WhatsApp links are built from it.")}
        </p></Card>
      )}
      <Grid className="mb-6">
        <Stat label={bi("محادثات من الحملات", "Chats from campaigns")} value={rows.reduce((a, r) => a + (r.chats || 0), 0)} icon="chat" />
        <Stat label={bi("موافقين على العروض", "Opted in to offers")} value={o.optin || 0} icon="check" />
        <Stat label={bi("كل مشتركي البوت", "All bot subscribers")} value={o.total || 0} icon="users" />
      </Grid>
      {P.exportUrl && (o.optin || 0) > 0 && (
        <div className="mb-6"><Btn variant="ghost" icon="download" href={P.exportUrl}>{bi("صدّر الموافقين على العروض (CSV)", "Export opted-in list (CSV)")}</Btn></div>
      )}
      <div className="flex flex-col gap-4">
        {rows.map((r) => (
          <Card key={r.code}>
            <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
              <SectionTitle icon={r.icon}>{r.name}</SectionTitle>
              <Pill tone={r.chats ? "on" : "mute"}>{bi("محادثات", "Chats")}: {num(r.chats)}</Pill>
            </div>
            <div className="flex flex-col gap-2.5">
              <Link id={r.code + "p"} label={bi("صفحة الهبوط", "Landing")} url={r.page} qr={`/admin/growth/qr/${r.code}/page.svg`} />
              <Link id={r.code + "w"} label="WhatsApp" url={r.wa} qr={`/admin/growth/qr/${r.code}/wa.svg`} />
              <Link id={r.code + "t"} label="Telegram" url={r.tg} qr={`/admin/growth/qr/${r.code}/tg.svg`} />
            </div>
          </Card>
        ))}
      </div>
    </>
  );
}

/* ============================================================ ماسنجر وإنستجرام (للأدمن وحده)
   صفحة المنصة تُحفظ مرة (توكنها مختوم في الخادم ولا يعود للمتصفح) · حقول الاشتراك · بوتات
   المنصة الرسمية من التوكن المحفوظ · ربط صفحة لأي مستخدم · كل بوتات الصفحات · سجل الأحداث. */
export function AdminMeta() {
  const { page = {}, fields = [], defaults = [], bots = [], events = [], templates = [], webhook = "" } = P;
  const st = page.status || null;
  const [pg, setPg] = useState({ page_id: page.id || "1240480079158277", token: "" });
  const [sel, setSel] = useState(() => new Set(st && st.subscribed && st.fields.length ? st.fields : defaults));
  const [asg, setAsg] = useState({ username: "", page_id: "", token: "", name: "", template: "customer_service",
                                   messenger: true, instagram: true });
  const [out, setOut] = useState({});
  const [busy, setBusy] = useState("");
  const say = (k, v) => setOut((o) => ({ ...o, [k]: v }));

  async function run(k, url, body, reload = true) {
    setBusy(k); say(k, null);
    const d = await postJSON(url, body);
    setBusy("");
    say(k, d);
    if (d.ok && reload) setTimeout(() => location.reload(), 900);
    return d;
  }
  const groups = fields.reduce((m, f) => ((m[f.group] = m[f.group] || []).push(f), m), {});
  const toggle = (k) => setSel((s) => { const n = new Set(s); if (n.has(k)) n.delete(k); else n.add(k); return n; });
  const Msg = ({ d }) => !d ? null : (
    <p role="status" className={"mt-3 mb-0 text-[13px] font-bold " + (d.ok ? "text-au-teal" : "text-red-300")}>
      {d.ok ? bi("تم ✓", "Done ✓") : d.error}
      {d.warning ? <span className="block text-yellow-300">⚠ {d.warning}</span> : null}
      {d.rejected && Object.keys(d.rejected).length > 0 && (
        <span className="mt-1 block font-normal text-ink-3">
          {bi("مرفوضة من Meta (تحتاج أذونات إضافية): ", "Rejected by Meta (need extra permissions): ")}
          {Object.keys(d.rejected).join(" · ")}
        </span>
      )}
    </p>
  );

  return (
    <>
      <PageHead icon="chat" title={bi("ماسنجر وإنستجرام", "Messenger & Instagram")}
        sub={bi("تحكم كامل في صفحات فيسبوك وحسابات إنستجرام — للأدمن فقط.",
                "Full control of Facebook Pages and Instagram accounts — admins only.")} />

      <Card className="mb-5">
        <SectionTitle icon="link">{bi("عنوان الويبهوك في Meta", "Webhook URL in Meta")}</SectionTitle>
        <code className="block overflow-x-auto rounded-xl bg-black/30 px-4 py-3 text-[13px] text-au-cyan" dir="ltr">{webhook}</code>
        <p className="mt-2 mb-0 text-[12.5px] text-ink-3">
          {bi("حطه في إعدادات Messenger وInstagram في تطبيق Meta بنفس Verify Token بتاع واتساب.",
              "Set it in the Messenger and Instagram settings of the Meta app with the same Verify Token as WhatsApp.")}
        </p>
      </Card>

      <Card className="mb-5">
        <SectionTitle icon="shield"
          extra={page.configured ? <Pill tone={st && st.subscribed ? "on" : "warn"} dot>
            {st && st.subscribed ? bi("مشترك", "Subscribed") : bi("غير مشترك", "Not subscribed")}</Pill> : null}>
          {bi("صفحة المنصة", "Platform Page")}
        </SectionTitle>
        {page.configured && st && (
          <div className="mb-4 flex flex-wrap gap-2 text-[13px]">
            <Pill tone="mute">{st.name || page.id}</Pill>
            {st.ig_username && <Pill tone="mute"><Icon name="camera" size={11} />@{st.ig_username}</Pill>}
            <Pill tone="mute">{bi("حقول", "Fields")}: {st.fields.length}</Pill>
            {st.error && <Pill tone="warn">{st.error}</Pill>}
          </div>
        )}
        <div className="grid gap-3 sm:grid-cols-[1fr_1.4fr_auto] sm:items-end">
          <Field label="Page ID">
            <Input value={pg.page_id} onChange={(e) => setPg({ ...pg, page_id: e.target.value })} dir="ltr" inputMode="numeric" />
          </Field>
          <Field label={page.configured ? bi("توكن جديد (اختياري)", "New token (optional)") : bi("التوكن", "Token")}>
            <Input type="password" value={pg.token} onChange={(e) => setPg({ ...pg, token: e.target.value })} dir="ltr"
                   autoComplete="off" placeholder={page.configured ? bi("فاضي = نفس المحفوظ", "empty = keep saved") : "EAA…"} />
          </Field>
          <Btn icon="check" type="button" disabled={busy === "page" || (!page.configured && !pg.token)}
               onClick={() => run("page", "/admin/meta/page", pg)}>
            {page.configured ? bi("حدّث واشترك", "Update & subscribe") : bi("احفظ الصفحة", "Save Page")}
          </Btn>
        </div>
        <Msg d={out.page} />
        {page.configured && (
          <div className="mt-5 flex flex-wrap gap-2.5 border-t border-white/10 pt-4">
            <Btn icon="rocket" type="button" disabled={busy === "official"}
                 onClick={() => run("official", "/admin/meta/official", { messenger: true, instagram: true })}>
              {bi("شغّل المساعد الرسمي على ماسنجر وإنستجرام", "Run the official assistant on Messenger & Instagram")}
            </Btn>
            <Btn variant="ghost" icon="close" type="button" disabled={busy === "unsub"}
                 onClick={() => { if (confirm(bi("فصل التطبيق عن أحداث الصفحة؟", "Unsubscribe the app from the Page?")))
                                    run("unsub", "/admin/meta/unsubscribe", {}); }}>
              {bi("إلغاء الاشتراك", "Unsubscribe")}
            </Btn>
          </div>
        )}
        <Msg d={out.official || out.unsub} />
      </Card>

      {page.configured && (
        <Card className="mb-5">
          <SectionTitle icon="settings"
            extra={<div className="flex gap-2">
              <Btn sm variant="ghost" type="button" onClick={() => setSel(new Set(defaults))}>{bi("المقترح", "Recommended")}</Btn>
              <Btn sm variant="ghost" type="button" onClick={() => setSel(new Set(fields.map((f) => f.k)))}>{bi("الكل", "All")}</Btn>
            </div>}>
            {bi("حقول الاشتراك", "Subscription fields")}
          </SectionTitle>
          <div className="grid gap-4 md:grid-cols-2">
            {Object.entries(groups).map(([g, list]) => (
              <div key={g} className="rounded-xl bg-white/[0.03] p-3.5 shadow-[inset_0_0_0_1px_rgb(255_255_255/0.07)]">
                <div className="mb-2 text-[12.5px] font-extrabold text-ink-3">{g}</div>
                {list.map((f) => (
                  <label key={f.k} className="flex cursor-pointer items-center gap-2 py-1 text-[13px] text-ink" dir="ltr">
                    <input type="checkbox" checked={sel.has(f.k)} onChange={() => toggle(f.k)} className="size-4 accent-[#8FE9FF]" />
                    <span className="font-mono text-[12.5px]">{f.k}</span>
                    <span className={"ms-auto text-[11px] font-bold " + (f.handled ? "text-au-teal" : "text-ink-4")} dir="rtl">
                      {f.handled ? bi("يعالجه BotYalla", "Handled") : bi("سجل فقط", "Logged only")}
                    </span>
                  </label>
                ))}
              </div>
            ))}
          </div>
          <Btn className="mt-4" icon="check" type="button" disabled={busy === "fields"}
               onClick={() => run("fields", "/admin/meta/fields", { fields: [...sel] })}>
            {bi("احفظ الاشتراك", "Save subscription")} ({sel.size})
          </Btn>
          <Msg d={out.fields} />
        </Card>
      )}

      <Card className="mb-5">
        <SectionTitle icon="users">{bi("ربط صفحة لمستخدم", "Connect a Page for a user")}</SectionTitle>
        <p className="mt-0 mb-4 text-[12.5px] text-ink-3">
          {bi("البوتات بتتعمل في حساب المستخدم وتشتغل على طول، وتفضل شغالة لوحدها — توكن الصفحة المشتق من توكن مستخدم طويل مبينتهيش.",
              "Bots are created in the user's account and start right away — a Page token derived from a long-lived user token never expires.")}
        </p>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          <Field label={t("username")}><Input value={asg.username} onChange={(e) => setAsg({ ...asg, username: e.target.value })} /></Field>
          <Field label="Page ID"><Input value={asg.page_id} dir="ltr" inputMode="numeric" onChange={(e) => setAsg({ ...asg, page_id: e.target.value })} /></Field>
          <Field label={bi("التوكن", "Token")}><Input type="password" value={asg.token} dir="ltr" autoComplete="off"
                 onChange={(e) => setAsg({ ...asg, token: e.target.value })} /></Field>
          <Field label={t("biz_name")}><Input value={asg.name} maxLength={60} onChange={(e) => setAsg({ ...asg, name: e.target.value })} /></Field>
          <Field label={t("bot_type")}>
            <Select value={asg.template} onChange={(e) => setAsg({ ...asg, template: e.target.value })}>
              {templates.map((x) => <option key={x.k} value={x.k}>{x.l}</option>)}
            </Select>
          </Field>
          <div className="flex items-end gap-4 pb-2">
            {[["messenger", "Messenger"], ["instagram", "Instagram"]].map(([k, l]) => (
              <label key={k} className="flex items-center gap-2 text-[13.5px] font-bold text-ink">
                <input type="checkbox" checked={asg[k]} onChange={(e) => setAsg({ ...asg, [k]: e.target.checked })}
                       className="size-4 accent-[#8FE9FF]" />{l}
              </label>
            ))}
          </div>
        </div>
        <Btn className="mt-3" icon="link" type="button" disabled={busy === "assign" || !asg.username || !asg.page_id || !asg.token}
             onClick={() => run("assign", "/admin/meta/assign", asg)}>
          {bi("اربط للمستخدم", "Connect for user")}
        </Btn>
        <Msg d={out.assign} />
      </Card>

      <Card className="mb-5">
        <SectionTitle icon="bot">{bi("كل بوتات الصفحات", "All Page bots")} ({bots.length})</SectionTitle>
        {bots.length ? (
          <Table head={["#", bi("البوت", "Bot"), bi("المالك", "Owner"), bi("القناة", "Channel"),
                        bi("الحساب", "Account"), bi("الحالة", "Status"), ""]}>
            {bots.map((b) => (
              <Tr key={b.id}>
                <Td className="tnum">{b.id}</Td>
                <Td><a href={`/bot/${b.id}`} className="font-bold text-au-cyan no-underline">{b.name}</a></Td>
                <Td>{b.username}</Td>
                <Td>{b.channel === "instagram" ? "Instagram" : "Messenger"}</Td>
                <Td className="font-mono text-[12px]">{b.account}</Td>
                <Td>{b.is_active ? <Pill tone="on" dot>{t("running")}</Pill> : <Pill tone="off">{t("stopped")}</Pill>}</Td>
                <Td>
                  <Btn sm variant="ghost" type="button" disabled={busy === `bot_${b.id}`}
                       onClick={() => run(`bot_${b.id}`, `/admin/meta/bot/${b.id}/resubscribe`, {}, false)}>
                    {bi("إعادة الاشتراك", "Resubscribe")}
                  </Btn>
                  {out[`bot_${b.id}`] && (
                    <span className={"ms-2 text-[12px] font-bold " + (out[`bot_${b.id}`].ok ? "text-au-teal" : "text-red-300")}>
                      {out[`bot_${b.id}`].ok ? "✓" : "✗"}
                    </span>
                  )}
                </Td>
              </Tr>
            ))}
          </Table>
        ) : <Empty icon="bot" title={bi("مفيش بوتات صفحات لسه", "No Page bots yet")} />}
      </Card>

      <Card>
        <SectionTitle icon="clock">{bi("سجل الأحداث", "Event log")} ({events.length})</SectionTitle>
        {events.length ? (
          <Table head={[bi("الوقت", "Time"), bi("الحساب", "Account"), bi("النوع", "Kind"), bi("العميل", "Customer"), bi("التفاصيل", "Details")]}>
            {events.map((e) => (
              <Tr key={e.id}>
                <Td className="tnum text-[12px]">{fmtDate(e.created_at)}</Td>
                <Td className="font-mono text-[12px]">{e.account}</Td>
                <Td><Pill tone="mute">{e.kind}</Pill></Td>
                <Td className="font-mono text-[12px]">{e.peer || "—"}</Td>
                <Td className="text-[12.5px]">{e.summary}</Td>
              </Tr>
            ))}
          </Table>
        ) : <Empty icon="clock" title={bi("لسه مفيش أحداث", "No events yet")} />}
      </Card>
    </>
  );
}
