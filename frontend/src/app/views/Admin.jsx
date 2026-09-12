import { useEffect, useRef, useState } from "react";
import {
  BY, P, t, bi, Icon, Card, Btn, Field, Input, Select, Form, Grid, Stat,
  Pill, Empty, PageHead, SectionTitle, Table, Tr, Td, num, fmtDate, daysLeft,
} from "../kit.jsx";

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
              <Field label={t("password")}><Input type="password" name="password" required minLength={6} /></Field>
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
        <Table head={["#", t("username"), t("role"), t("col_plan2"), t("col_bots"), t("col_status"), ""]}>
          {users.map((u) => (
            <Tr key={u.id}>
              <Td className="tnum">{u.id}</Td>
              <Td>
                <span className="font-bold text-ink">{u.username}</span>
                {u.is_blocked ? <span className="ms-2"><Pill tone="off">{t("blocked")}</Pill></span> : null}
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
export function AdminPayments() {
  const { pays = [], names = {} } = P;
  const isAdmin = BY.user.role === "admin";
  const tone = { pending: "warn", approved: "on", rejected: "off" };
  const label = { pending: t("status_pending"), approved: t("status_approved"), rejected: t("status_rejected") };

  return (
    <>
      <PageHead icon="card" title={t("admin_payments_t")}
        actions={<Btn variant="ghost" sm icon="back" href="/admin">{t("back")}</Btn>} />

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

/* -------------------------------------------------------------- المنصة */
export function AdminPlatform() {
  const { plat = {}, running, capacity = null, managed = {} } = P;
  const F = ({ name, label, ph }) => (
    <Field label={label}><Input name={name} defaultValue={plat[name] || ""} placeholder={ph} /></Field>
  );
  return (
    <>
      <PageHead icon="shield" title={t("platform_title")} sub={t("platform_sub")} />
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
            <F name="wa_app_secret" label="App Secret" ph="Meta → App settings → Basic" />
          </div>
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
            <F name="support_email" label={t("plat_email")} ph="info@youssefalsherief.tech" />
            <F name="support_whatsapp" label={t("plat_whatsapp")} ph="201097585951" />
            <F name="support_telegram" label={t("plat_telegram")} ph="username" />
          </div>
          <div className="mt-6"><Btn icon="check" type="submit">{t("save")}</Btn></div>
        </Card>
      </Form>
    </>
  );
}
