import {
  P, t, bi, Icon, Card, Btn, Form, Grid, Select, Pill, Empty, PageHead, SectionTitle,
  Table, Tr, Td, num, fmtDate,
} from "../kit.jsx";

/* ============================================================================
   التقرير الأسبوعي · تحليل المحادثات — صفحتا المالك.

   القاعدة هنا: لا رقم بلا معناه. كل مقياس معه مقارنته بالفترة السابقة، وكل
   ملاحظة معها إجراؤها، وكل تنبؤ معه درجة ثقته. الرسوم بعناصر CSS بسيطة لا
   بمكتبة رسم: الصفحة طويلة أصلاً، وتحميل Chart.js لأعمدة سبعة إسراف.
   ========================================================================= */

const AR = { risk: "عاجل", warn: "انتبه", good: "جيد", info: "معلومة" };
const EN = { risk: "Urgent", warn: "Attention", good: "Good", info: "Info" };
const TONE = { risk: "text-red-300", warn: "text-amber-200", good: "text-au-teal", info: "text-ink-3" };
const BAR = {
  risk: "bg-red-400/70", warn: "bg-amber-300/70", good: "bg-au-teal/70", info: "bg-white/25",
};

const pct = (x, y) => (y ? Math.round((x / y) * 100) : 0);

/* نيّات الرسائل — المفاتيح من conv_insights.INTENTS */
const INTENT = {
  price: ["السعر", "Price"], shipping: ["الشحن", "Shipping"], stock: ["التوفّر", "Availability"],
  order: ["طلب شراء", "Ordering"], order_status: ["أين طلبي", "Order status"],
  payment: ["الدفع", "Payment"], booking: ["حجز موعد", "Booking"], hours: ["المواعيد والعنوان", "Hours & address"],
  complaint: ["شكوى", "Complaint"], human: ["يريد موظفاً", "Wants a human"],
  confused: ["محتار — «مش فاهم»", "Confused"], earn: ["سؤال عن الربح", "Earning money"],
  signup: ["التسجيل والتفعيل", "Signup & verification"],
  subscribe: ["الباقات والاشتراك", "Plans & subscription"],
  whatsapp: ["واتساب", "WhatsApp"], howto: ["كيف أبدأ", "How do I start"],
  greeting: ["تحية", "Greeting"], thanks: ["شكر", "Thanks"], other: ["أخرى", "Other"],
};
const intentLabel = (k) => (INTENT[k] ? bi(INTENT[k][0], INTENT[k][1]) : k || "—");

/* أسباب التعثّر — المفاتيح من database.PROBLEM_KINDS */
const PROBLEM = {
  verify_stuck: ["لم يؤكّد بريده", "Email not confirmed"],
  receipt_refused: ["إيصال مرفوض آلياً", "Receipt auto-refused"],
  payment_rejected: ["دفعة مرفوضة", "Payment rejected"],
  payment_waiting: ["دفعة تنتظرنا", "Payment waiting on us"],
  ticket_open: ["تذكرة مفتوحة", "Open ticket"],
  bot_never_started: ["بوت لم يُشغَّل", "Bot never started"],
  bot_silent: ["بوت بلا عميل", "Bot with no customer"],
  no_bot: ["بلا بوت", "No bot at all"],
  blocked: ["حساب محظور", "Blocked account"],
};
const problemLabel = (k) => (PROBLEM[k] ? bi(PROBLEM[k][0], PROBLEM[k][1]) : k);

const REFUSAL = {
  not_receipt: ["الصورة ليست إيصالاً", "Not a receipt"],
  wrong_recipient: ["مستلم آخر", "Wrong recipient"],
  amount_mismatch: ["مبلغ مختلف", "Amount mismatch"],
  duplicate: ["إيصال مستخدم", "Duplicate receipt"],
};

const CONF = {
  high: ["ثقة عالية", "High confidence"], medium: ["متوسطة", "Medium"],
  low: ["منخفضة", "Low"], none: ["بيانات غير كافية", "Not enough data"],
};

function Delta({ d }) {
  if (!d) return null;
  const c = d.change;
  if (c === null || c === undefined)
    return <span className="text-[12px] font-bold text-au-teal">{bi("جديد", "new")}</span>;
  if (!c) return <span className="text-[12px] text-ink-3">{bi("بلا تغيير", "no change")}</span>;
  const up = c > 0;
  return (
    <span className={`tnum text-[12px] font-bold ${up ? "text-au-teal" : "text-red-300"}`}>
      {up ? "▲" : "▼"} {Math.abs(c)}%
    </span>
  );
}

function Kpi({ label, value, hint, delta, cls = "text-ink" }) {
  return (
    <Card className="!p-5">
      <div className="text-[12.5px] font-bold text-ink-3">{label}</div>
      <div className="mt-1 flex flex-wrap items-baseline gap-2">
        <span className={`tnum text-[26px] font-extrabold ${cls}`}>{value}</span>
        <Delta d={delta} />
      </div>
      {hint && <div className="mt-1 text-[12px] leading-relaxed text-ink-3">{hint}</div>}
    </Card>
  );
}

function Bars({ rows, pick, label }) {
  const max = Math.max(1, ...rows.map(pick));
  return (
    <div className="flex h-32 items-end gap-1" dir="ltr">
      {rows.map((r) => (
        <div key={r.day} title={`${r.day} · ${pick(r)} ${label}`}
             className="flex-1 rounded-t bg-au-cyan/55 hover:bg-au-cyan"
             style={{ height: `${Math.max(3, (pick(r) / max) * 100)}%` }} />
      ))}
    </div>
  );
}

function Rank({ items, empty, fmt }) {
  if (!items || !items.length) return <Empty icon="chart" title={empty || bi("لا بيانات", "No data")} />;
  const max = Math.max(1, ...items.map((x) => x.v));
  return (
    <div className="flex flex-col gap-2.5">
      {items.map((x, i) => (
        <div key={`${x.k}-${i}`}>
          <div className="mb-1 flex items-center gap-3 text-[13px]">
            <span className="min-w-0 flex-1 truncate text-ink-2">{fmt ? fmt(x) : x.k}</span>
            <span className="tnum font-bold text-ink">{num(x.v)}</span>
          </div>
          <div className="h-1.5 overflow-hidden rounded-full bg-white/[0.07]">
            <div className="h-full rounded-full bg-[linear-gradient(90deg,#8FE9FF,#B9AFFF)]"
                 style={{ width: `${(x.v / max) * 100}%` }} />
          </div>
        </div>
      ))}
    </div>
  );
}

function DayTabs({ days, options, base = "" }) {
  return (
    <div className="flex gap-2">
      {(options || [7, 14, 30]).map((d) => (
        <Btn key={d} sm variant={days === d ? "primary" : "ghost"} href={`?days=${d}${base}`}>
          {bi(`${d} يوم`, `${d}d`)}
        </Btn>
      ))}
    </div>
  );
}

/* ======================================================= التقرير الأسبوعي */
export function WeeklyReport() {
  const r = P.r || {};
  const n = r.now || {}, d = r.delta || {}, logs = r.logs || {}, conv = r.conv || {};
  const p = r.period || {};
  const f = n.funnel || {};
  const steps = [
    ["signup", bi("سجّلوا", "Signed up")],
    ["bot_created", bi("أنشأوا بوتاً", "Created a bot")],
    ["bot_live", bi("شغّلوا البوت", "Bot went live")],
    ["first_message", bi("وصلتهم أول رسالة عميل", "Got a first customer message")],
    ["paid", bi("اشتراك مدفوع", "Paid subscription")],
  ];

  return (
    <>
      <PageHead icon="chart" title={t("adm_report")}
        sub={bi(`${p.label} — مقارنةً بـ ${p.prev_label}`, `${p.label} — compared with ${p.prev_label}`)}
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <DayTabs days={P.days} options={P.options} />
            <Btn sm variant="ghost" icon="chat" href={P.convUrl}>{t("adm_convo")}</Btn>
            <Btn sm variant="ghost" icon="download" href={P.csvUrl}>{bi("تصدير CSV", "CSV")}</Btn>
            <Btn sm variant="ghost" icon="copy" href={P.mdUrl}>{bi("ملف ماركداون", "Markdown")}</Btn>
          </div>} />

      {/* ---------- الخلاصة ---------- */}
      <Card className="mb-6">
        <SectionTitle icon="sparkles"
          extra={<span className="text-[12px] text-ink-3">
            {bi(`أُنشئ ${fmtDate(p.generated_at)}`, `Generated ${fmtDate(p.generated_at)}`)}</span>}>
          {bi("الخلاصة", "The short version")}
        </SectionTitle>
        <ul className="m-0 flex list-none flex-col gap-2 p-0 text-[13.5px] leading-relaxed text-ink-2">
          {(r.summary || []).map((s, i) => (
            <li key={i} className="flex items-start gap-2.5">
              <span className="mt-1.5 size-1.5 shrink-0 rounded-full bg-au-cyan" />{s}
            </li>
          ))}
        </ul>
      </Card>

      {/* ---------- ما يحتاج تدخّلك ---------- */}
      <Card className="mb-6">
        <SectionTitle icon="bolt">{bi("يحتاج تدخّلك", "Needs you")}</SectionTitle>
        {(r.findings || []).length ? (
          <div className="flex flex-col gap-3">
            {r.findings.map((x, i) => (
              <div key={i} className="rounded-xl bg-white/[0.03] p-4
                                      shadow-[inset_0_0_0_1px_rgb(255_255_255/0.06)]">
                <div className="mb-1.5 flex flex-wrap items-center gap-2">
                  <span className={`h-2 w-2 rounded-full ${BAR[x.level] || BAR.info}`} />
                  <b className={`text-[14px] ${TONE[x.level] || ""}`}>{x.title}</b>
                  <span className="ms-auto text-[11.5px] font-bold text-ink-3">
                    {bi(AR[x.level], EN[x.level])}
                  </span>
                </div>
                {x.detail && <p className="m-0 text-[12.5px] leading-relaxed text-ink-3">{x.detail}</p>}
                {x.action && (
                  <p className="mt-2 mb-0 text-[12.5px] font-bold leading-relaxed text-ink-2">
                    ← {x.action}
                  </p>
                )}
              </div>
            ))}
          </div>
        ) : <Empty icon="shield" title={bi("لا شيء عاجل", "Nothing urgent")}
                   text={bi("كل المؤشرات في وضع طبيعي هذه الفترة.",
                            "Everything looks normal this period.")} />}
      </Card>

      {/* ---------- المقاييس ---------- */}
      <Grid cols={4} className="mb-6">
        <Kpi label={bi("تسجيلات جديدة", "New signups")} value={num(n.signups)} delta={d.signups}
             hint={bi(`${num(n.signups_verified)} أكّدوا بريدهم`, `${num(n.signups_verified)} confirmed email`)} />
        <Kpi label={bi("بوتات جديدة", "New bots")} value={num(n.bots_new)} delta={d.bots_new}
             hint={bi(`${num(n.bots_new_active)} شغّال`, `${num(n.bots_new_active)} live`)} />
        <Kpi label={bi("رسائل عملاء", "Customer messages")} value={num(n.msgs_in)} delta={d.msgs_in}
             hint={bi(`${num(n.customers_active)} عميل نشط`, `${num(n.customers_active)} active customers`)} />
        <Kpi label={bi("إيراد معتمد", "Approved revenue")} value={num(n.revenue)} delta={d.revenue}
             hint={bi(`${num(n.pay_approved)} دفعة معتمدة`, `${num(n.pay_approved)} approved payments`)} />
        <Kpi label={bi("زوار", "Visitors")} value={num(n.visitors)} delta={d.visitors}
             hint={bi(`${num(n.pricing_visitors)} زاروا الأسعار`, `${num(n.pricing_visitors)} saw pricing`)} />
        <Kpi label={bi("طلبات العملاء", "Customer orders")} value={num(n.orders)} delta={d.orders}
             hint={bi(`بقيمة ${num(n.orders_value)} ج.م`, `worth ${num(n.orders_value)} EGP`)} />
        <Kpi label={bi("بيانات مجمّعة", "Leads")} value={num(n.leads)} delta={d.leads}
             hint={bi(`${num(n.bookings)} حجز`, `${num(n.bookings)} bookings`)} />
        <Kpi label={bi("تذاكر دعم", "Support tickets")} value={num(n.tickets_new)} delta={d.tickets_new}
             cls={n.tickets_unanswered ? "text-amber-200" : "text-ink"}
             hint={bi(`${num(n.tickets_unanswered)} بلا ردّ`, `${num(n.tickets_unanswered)} unanswered`)} />
      </Grid>

      <Grid cols={2} className="mb-6">
        <Card>
          <SectionTitle icon="chart">{bi("رسائل العملاء يومياً", "Customer messages per day")}</SectionTitle>
          {(r.daily || []).length ? <Bars rows={r.daily} pick={(x) => x.msgs_in}
                                          label={bi("رسالة", "messages")} />
            : <Empty icon="chart" title={bi("لا بيانات", "No data")} />}
        </Card>
        <Card>
          <SectionTitle icon="users">{bi("تسجيلات يومياً", "Signups per day")}</SectionTitle>
          {(r.daily || []).length ? <Bars rows={r.daily} pick={(x) => x.signups}
                                          label={bi("تسجيل", "signups")} />
            : <Empty icon="chart" title={bi("لا بيانات", "No data")} />}
        </Card>
      </Grid>

      {/* ---------- من توقّف وأين ---------- */}
      <Card className="mb-6">
        <SectionTitle icon="flow">{bi("أين يتوقّف الناس", "Where people stall")}</SectionTitle>
        <div className="mb-5 flex flex-col gap-3">
          {steps.map(([k, lbl], i) => {
            const v = f[k] || 0, prev = i ? f[steps[i - 1][0]] || 0 : v;
            return (
              <div key={k}>
                <div className="mb-1 flex flex-wrap items-center gap-2 text-[13px]">
                  <span className="font-bold text-ink">{lbl}</span>
                  <span className="ms-auto tnum text-ink-2">{num(v)}</span>
                  {i > 0 && <span className="tnum text-[12px] text-ink-3">
                    · {pct(v, prev)}% {bi("من السابقة", "of previous")}</span>}
                </div>
                <div className="h-2 overflow-hidden rounded-full bg-white/[0.07]">
                  <div className="h-full rounded-full bg-[linear-gradient(90deg,#8FE9FF,#B9AFFF)]"
                       style={{ width: `${pct(v, f.signup || 0)}%` }} />
                </div>
              </div>
            );
          })}
        </div>
        <Grid cols={4}>
          <Kpi label={bi("سجّلوا ولم ينشئوا بوتاً", "Signed up, no bot")} value={num(n.signups_no_bot)}
               delta={d.signups_no_bot} />
          <Kpi label={bi("أنشأوا ولم يشغّلوا", "Created, never started")} value={num(n.bots_never_started)}
               delta={d.bots_never_started} cls={n.bots_never_started ? "text-amber-200" : "text-ink"} />
          <Kpi label={bi("شغّالة بلا عميل واحد", "Live, zero customers")} value={num(n.bots_started_silent)}
               delta={d.bots_started_silent} cls={n.bots_started_silent ? "text-amber-200" : "text-ink"} />
          <Kpi label={bi("بوتات صامتة هذه الفترة", "Silent bots this period")}
               value={num(n.silent_active_bots)}
               hint={bi(`من ${num(n.bots_active)} بوت شغّال`, `of ${num(n.bots_active)} live bots`)} />
        </Grid>
      </Card>

      {/* ---------- التنبؤ ---------- */}
      <Card className="mb-6">
        <SectionTitle icon="sparkles">{bi("المتوقّع للفترة القادمة", "Next period forecast")}</SectionTitle>
        <p className="mt-0 mb-4 text-[12.5px] leading-relaxed text-ink-3">
          {bi("خطّ اتجاه (انحدار خطّي) على آخر أربعة أسابيع — تقدير لا وعد. كلما قلّت البيانات أو زاد تذبذبها قلّت الثقة.",
              "A linear trend over the last four weeks — an estimate, not a promise. Less or noisier data means lower confidence.")}
        </p>
        <Table head={[bi("المقياس", "Metric"), bi("المتوقّع", "Expected"),
                      bi("الفترة الماضية", "Last period"), bi("الثقة", "Confidence")]}>
          {Object.entries(r.forecast || {}).map(([k, v]) => (
            <Tr key={k}>
              <Td>{bi({ signups: "تسجيلات", msgs_in: "رسائل عملاء", orders: "طلبات",
                        revenue: "إيراد (ج.م)", visitors: "زوار" }[k] || k,
                      { signups: "Signups", msgs_in: "Customer messages", orders: "Orders",
                        revenue: "Revenue (EGP)", visitors: "Visitors" }[k] || k)}</Td>
              <Td className="tnum font-bold text-ink">{num(Math.round(v.expected))}</Td>
              <Td className="tnum">{num(Math.round(v.last_period))}</Td>
              <Td><Pill tone={v.confidence === "high" ? "on" : v.confidence === "none" ? "mute" : "warn"}>
                {bi(CONF[v.confidence]?.[0] || v.confidence, CONF[v.confidence]?.[1] || v.confidence)}
              </Pill></Td>
            </Tr>
          ))}
        </Table>
        {(r.expiring || []).length > 0 && (
          <p className="mt-4 mb-0 rounded-xl bg-yellow-400/[0.07] p-3 text-[12.5px] leading-relaxed
                        text-amber-200 shadow-[inset_0_0_0_1px_rgb(250_204_21/0.25)]">
            {bi(`${r.expiring.length} اشتراكاً ينتهي خلال 7 أيام — قيمة تجديدها بسعر القائمة ≈ ${num(r.renewal_value)} ج.م: `,
                `${r.expiring.length} subscriptions expire within 7 days — list-price renewal value ≈ ${num(r.renewal_value)} EGP: `)}
            <span dir="ltr">{r.expiring.slice(0, 12).map((x) => x.username).join(" · ")}</span>
          </p>
        )}
      </Card>

      {/* ---------- المال ---------- */}
      <Grid cols={2} className="mb-6">
        <Card>
          <SectionTitle icon="wallet">{bi("المال", "Money")}</SectionTitle>
          <Table head={[bi("البند", "Item"), bi("الفترة", "This period"), bi("السابقة", "Previous")]}>
            {[["revenue", bi("إيراد معتمد (ج.م)", "Approved revenue (EGP)")],
              ["pay_sent", bi("دفعات وصلت", "Payments received")],
              ["pay_approved", bi("دفعات معتمدة", "Payments approved")],
              ["refusals", bi("إيصالات مرفوضة آلياً", "Auto-refused receipts")]].map(([k, lbl]) => (
              <Tr key={k}>
                <Td>{lbl}</Td>
                <Td className="tnum font-bold text-ink">{num(d[k]?.now)}</Td>
                <Td className="tnum">{num(d[k]?.prev)}</Td>
              </Tr>
            ))}
            <Tr>
              <Td>{bi("دفعات تنتظر قرارك", "Awaiting your decision")}</Td>
              <Td className={`tnum font-bold ${n.pay_pending_late ? "text-red-300" : "text-ink"}`}>
                {num(n.pay_pending)}
              </Td>
              <Td className="text-[12px] text-ink-3">
                {n.pay_pending_late ? bi(`${n.pay_pending_late} متأخرة`, `${n.pay_pending_late} late`) : "—"}
              </Td>
            </Tr>
            <Tr>
              <Td>{bi("مشتركون يدفعون الآن", "Paying subscribers now")}</Td>
              <Td className="tnum font-bold text-ink">{num(n.paying_now)}</Td>
              <Td className="text-[12px] text-ink-3">
                {bi(`${num(n.addons_sold)} إضافة · ${num(n.wallet_topups)} شحن`,
                    `${num(n.addons_sold)} add-ons · ${num(n.wallet_topups)} top-ups`)}
              </Td>
            </Tr>
          </Table>
        </Card>
        <Card>
          <SectionTitle icon="shield">{bi("أسباب رفض الإيصالات", "Receipt refusal reasons")}</SectionTitle>
          <Rank items={n.refusals_by_reason} empty={bi("لا إيصال مرفوض", "No refused receipts")}
                fmt={(x) => bi(REFUSAL[x.k]?.[0] || x.k, REFUSAL[x.k]?.[1] || x.k)} />
          <div className="mt-5">
            <SectionTitle icon="users">{bi("مصادر التسجيل", "Signup sources")}</SectionTitle>
            <Rank items={n.signup_sources} empty={bi("لا تسجيلات", "No signups")} />
          </div>
        </Card>
      </Grid>

      {/* ---------- كل بوت ---------- */}
      <Card className="mb-6">
        <SectionTitle icon="bot"
          extra={<span className="text-[12px] text-ink-3">{bi("مرتّب بالأكثر حركة", "Busiest first")}</span>}>
          {bi("نتائج كل بوت", "Per-bot results")}
        </SectionTitle>
        {(r.bots || []).length ? (
          <Table head={[bi("البوت", "Bot"), bi("المالك", "Owner"), bi("وارد", "In"), bi("صادر", "Out"),
                        bi("عملاء", "Customers"), bi("جدد", "New"), bi("بيانات", "Leads"),
                        bi("طلبات", "Orders"), bi("قيمة", "Value"), bi("الحالة", "State")]}>
            {r.bots.map((b) => (
              <Tr key={b.id}>
                <Td><b className="text-ink">{b.name}</b>
                  <div className="text-[11.5px] text-ink-3">{b.template} · {b.channel}</div></Td>
                <Td dir="ltr">{b.owner}</Td>
                <Td className="tnum">{num(b.msgs_in)}</Td>
                <Td className="tnum">{num(b.msgs_out)}</Td>
                <Td className="tnum">{num(b.customers)}</Td>
                <Td className="tnum">{num(b.new_customers)}</Td>
                <Td className="tnum">{num(b.leads)}</Td>
                <Td className="tnum">{num(b.orders)}</Td>
                <Td className="tnum">{num(b.orders_value)}</Td>
                <Td>{b.is_active
                  ? (b.msgs_in ? <Pill tone="on" dot>{bi("نشط", "Active")}</Pill>
                               : <Pill tone="warn">{bi("صامت", "Silent")}</Pill>)
                  : <Pill tone="mute">{bi("متوقف", "Stopped")}</Pill>}</Td>
              </Tr>
            ))}
          </Table>
        ) : <Empty icon="bot" title={bi("لا بوتات", "No bots")} />}
      </Card>

      {/* ---------- من تعثّر ---------- */}
      <Card className="mb-6">
        <SectionTitle icon="help"
          extra={<Btn sm variant="ghost" icon="users" href={P.usersUrl}>{bi("المستخدمون", "Users")}</Btn>}>
          {bi("من حدثت معه مشكلة", "Who ran into trouble")}
        </SectionTitle>
        <p className="mt-0 mb-4 text-[12.5px] leading-relaxed text-ink-3">
          {bi("«مشكلة» هنا حدث ملموس لا انطباع: إيصال مرفوض، دفعة تنتظرنا، تذكرة مفتوحة، بريد لم يُؤكَّد، بوت لم يُشغَّل.",
              "“Trouble” here means a concrete event: a refused receipt, a payment waiting on us, an open ticket, an unconfirmed email, a bot never started.")}
        </p>
        {(r.problems || []).length ? (
          <Table head={[bi("المستخدم", "User"), bi("الباقة", "Plan"), bi("سجّل في", "Signed up"),
                        bi("ما حدث", "What happened")]}>
            {r.problems.map((u) => (
              <Tr key={u.user_id}>
                <Td dir="ltr"><b className="text-ink">{u.username}</b></Td>
                <Td>{u.plan}</Td>
                <Td className="text-[12px] text-ink-3">{fmtDate(u.created_at)}</Td>
                <Td>
                  <div className="flex flex-wrap gap-1.5">
                    {Object.entries(u.problems || {}).map(([k, v]) => (
                      <span key={k} className="rounded-full bg-white/[0.06] px-2.5 py-1 text-[11.5px] text-ink-2">
                        {problemLabel(k)}{v > 1 ? ` ×${v}` : ""}
                      </span>
                    ))}
                  </div>
                </Td>
              </Tr>
            ))}
          </Table>
        ) : <Empty icon="shield" title={bi("لا أحد تعثّر", "Nobody got stuck")} />}
      </Card>

      {/* ---------- البريد ---------- */}
      <Card className="mb-6">
        <SectionTitle icon="mail"
          extra={<span className="text-[12px] text-ink-3">
            {bi(`${num(n.emails_sent)} وصلت · ${num(n.emails_failed)} فشلت · ${num(n.verify_emails)} كود تأكيد`,
                `${num(n.emails_sent)} sent · ${num(n.emails_failed)} failed · ${num(n.verify_emails)} verification codes`)}
          </span>}>
          {bi("نتائج رسائل البريد", "Email results")}
        </SectionTitle>
        {(r.emails?.campaigns || []).length ? (
          <Table head={[bi("الحملة", "Campaign"), bi("النوع", "Kind"), bi("الجمهور", "Audience"),
                        bi("وصلت", "Sent"), bi("فشلت", "Failed"), bi("تُخطّيت", "Skipped"),
                        bi("الحالة", "Status")]}>
            {r.emails.campaigns.map((c) => (
              <Tr key={c.id}>
                <Td><b className="text-ink">{c.subject || `#${c.id}`}</b>
                  <div className="text-[11.5px] text-ink-3">{fmtDate(c.created_at)}</div></Td>
                <Td>{c.kind === "news" ? bi("أخبار", "News") : bi("خدمة", "Service")}</Td>
                <Td dir="ltr">{c.audience}</Td>
                <Td className="tnum font-bold text-ink">{num(c.sent)}</Td>
                <Td className={`tnum ${c.failed ? "text-red-300" : ""}`}>{num(c.failed)}</Td>
                <Td className="tnum">{num(c.skipped)}</Td>
                <Td>{c.status === "done" ? <Pill tone="on">{bi("انتهت", "Done")}</Pill>
                  : c.status === "stopped" ? <Pill tone="mute">{bi("متوقفة", "Stopped")}</Pill>
                  : <Pill tone="warn" dot>{bi("جارية", "Sending")}</Pill>}</Td>
              </Tr>
            ))}
          </Table>
        ) : <Empty icon="mail" title={bi("لا حملات بريد في الفترة", "No email campaigns this period")}
                   text={bi("الأرقام أعلاه تشمل رسائل النظام (تأكيد البريد والإيصالات والتذكيرات).",
                            "The numbers above include system emails (verification, receipts, reminders).")} />}
        {(r.emails?.failed_users || []).length > 0 && (
          <p className="mt-4 mb-0 text-[12.5px] leading-relaxed text-ink-3">
            {bi("لم تصلهم: ", "Delivery failed for: ")}
            <span dir="ltr">{r.emails.failed_users.map((x) => `${x.username} (${x.n})`).join(" · ")}</span>
          </p>
        )}
      </Card>

      {/* ---------- سجل الخادم ---------- */}
      <Card className="mb-6">
        <SectionTitle icon="shield"
          extra={logs.available
            ? <span className="text-[12px] text-ink-3">
                {bi(`${num(logs.lines)} سطراً من ${(logs.files || []).length} ملف`,
                    `${num(logs.lines)} lines from ${(logs.files || []).length} files`)}
                {logs.truncated ? bi(" · قُرئ الأحدث فقط", " · newest part only") : ""}
              </span>
            : <Pill tone="mute">{bi("غير متاح", "Unavailable")}</Pill>}>
          {bi("سجل الخادم", "Server log")}
        </SectionTitle>
        {logs.available ? (
          <>
            <Grid cols={4} className="mb-5">
              <Kpi label={bi("أخطاء", "Errors")} value={num(logs.errors)}
                   cls={logs.errors ? "text-red-300" : "text-au-teal"} />
              <Kpi label={bi("تحذيرات", "Warnings")} value={num(logs.warnings)}
                   cls={logs.warnings ? "text-amber-200" : "text-ink"} />
              <Kpi label={bi("أخطاء 500", "HTTP 500s")} value={num(logs.signals?.http_500)} />
              <Kpi label={bi("رسائل بريد فشلت", "Mail failures")} value={num(logs.signals?.mail_failed)} />
            </Grid>
            <p className="mt-0 mb-4 text-[12.5px] leading-relaxed text-ink-3">
              {bi("السطور المتشابهة مجمّعة في عطل واحد، وكل ما يشبه سرّاً (توكن · بريد · هاتف) محجوب قبل العرض.",
                  "Similar lines are grouped into one fault, and anything resembling a secret (token, email, phone) is redacted before display.")}
            </p>
            {(logs.groups || []).length ? (
              <Table head={[bi("العطل", "Fault"), bi("مرات", "Count"), bi("أول ظهور", "First"),
                            bi("آخر ظهور", "Last")]}>
                {logs.groups.slice(0, 12).map((g, i) => (
                  <Tr key={i}>
                    <Td>
                      <b className={g.level === "WARNING" ? "text-amber-200" : "text-red-300"}>{g.logger}</b>
                      <div className="mt-1 max-w-[540px] break-words text-[12px] leading-relaxed text-ink-2"
                           dir="ltr">{g.trace || g.sample}</div>
                    </Td>
                    <Td className="tnum font-bold text-ink">{num(g.count)}</Td>
                    <Td className="text-[12px] text-ink-3">{fmtDate(g.first)}</Td>
                    <Td className="text-[12px] text-ink-3">{fmtDate(g.last)}</Td>
                  </Tr>
                ))}
              </Table>
            ) : <Empty icon="shield" title={bi("لا أخطاء في الفترة", "No errors this period")} />}
            {(logs.paths || []).length > 0 && (
              <div className="mt-5">
                <SectionTitle icon="flow">{bi("المسارات التي انهارت", "Failing routes")}</SectionTitle>
                <Rank items={logs.paths} />
              </div>
            )}
          </>
        ) : (
          <Empty icon="shield" title={bi("لا يمكن قراءة السجل هنا", "The log cannot be read here")}
                 text={bi(`على الخادم يُكتب في logs/botyalla.log ويُقرأ تلقائياً. المسار: ${logs.dir || "—"}`,
                          `On the server it lives in logs/botyalla.log and is read automatically. Path: ${logs.dir || "—"}`)} />
        )}
      </Card>

      {/* ---------- المحادثات ---------- */}
      <Card className="mb-6">
        <SectionTitle icon="chat"
          extra={<Btn sm variant="ghost" icon="chat" href={P.convUrl}>
            {bi("التحليل الكامل", "Full analysis")}</Btn>}>
          {bi("ماذا قال العملاء", "What customers said")}
        </SectionTitle>
        {conv.messages ? (
          <>
            <Grid cols={4} className="mb-5">
              <Kpi label={bi("رسائل عملاء", "Customer messages")} value={num(conv.in_count)} />
              <Kpi label={bi("نسبة الرد", "Answer rate")} value={`${conv.answer_rate || 0}%`}
                   cls={(conv.answer_rate || 0) < 85 ? "text-amber-200" : "text-au-teal"} />
              <Kpi label={bi("أسئلة بلا إجابة", "Unanswered questions")} value={num(conv.unanswered_total)}
                   cls={conv.unanswered_total ? "text-amber-200" : "text-ink"} />
              <Kpi label={bi("ينتظرون رداً الآن", "Waiting right now")} value={num(conv.waiting_total)}
                   cls={conv.waiting_total ? "text-red-300" : "text-ink"} />
            </Grid>
            <Grid cols={2}>
              <div>
                <SectionTitle icon="grid">{bi("عمّ يسألون", "What they ask about")}</SectionTitle>
                <Rank items={(conv.intents || []).slice(0, 8)} fmt={(x) => intentLabel(x.k)} />
              </div>
              <div>
                <SectionTitle icon="help">{bi("أكثر الأسئلة بلا إجابة", "Top unanswered")}</SectionTitle>
                {(conv.unanswered || []).length ? (
                  <ul className="m-0 flex list-none flex-col gap-2 p-0 text-[13px] leading-relaxed text-ink-2">
                    {conv.unanswered.slice(0, 6).map((q, i) => (
                      <li key={i} className="flex items-start gap-2">
                        <span className="tnum shrink-0 font-bold text-au-cyan">{q.v}×</span>
                        <span className="min-w-0">{q.sample || q.k}</span>
                      </li>
                    ))}
                  </ul>
                ) : <Empty icon="shield" title={bi("كل سؤال وجد إجابة", "Everything got answered")} />}
              </div>
            </Grid>
          </>
        ) : <Empty icon="chat" title={bi("لا رسائل في الفترة", "No messages this period")} />}
      </Card>

      {/* ---------- رسائل التفعيل ---------- */}
      <Card className="mb-6">
        <SectionTitle icon="bolt"
          extra={<Pill tone={P.nudges ? "on" : "mute"} dot={P.nudges}>
            {P.nudges ? bi("شغّالة", "On") : bi("متوقفة", "Off")}</Pill>}>
          {bi("رسائل التفعيل — من توقّف في منتصف الطريق", "Activation nudges — people who stalled")}
        </SectionTitle>
        <p className="mt-0 mb-4 text-[12.5px] leading-relaxed text-ink-3">
          {bi("رسالة واحدة (تليجرام أو بريد) لمن سجّل ولم ينشئ بوتاً، أو أنشأه ولم يشغّله، أو شغّله ولم تصله رسالة عميل، أو لم يؤكّد بريده. رسالة واحدة لكل حالة، ولا تُرسل بين 10م و9ص.",
              "One message (Telegram or email) to whoever signed up without a bot, created one without starting it, started one that got no customers, or never confirmed their email. One message per case, never between 10pm and 9am.")}
        </p>
        {(r.nudges || []).length ? (
          <Table head={[bi("الرسالة", "Nudge"), bi("أُرسلت", "Sent"), bi("تقدّم بعدها", "Moved on"),
                        bi("النسبة", "Rate")]}>
            {r.nudges.map((n) => (
              <Tr key={n.k}>
                <Td>{n.k}</Td>
                <Td className="tnum font-bold text-ink">{num(n.v)}</Td>
                <Td className="tnum">{num(n.advanced)}</Td>
                <Td className="tnum">{pct(n.advanced, n.v)}%</Td>
              </Tr>
            ))}
          </Table>
        ) : <Empty icon="bolt" title={bi("لم تُرسل رسائل تفعيل في الفترة", "No nudges sent this period")}
                   text={bi("إما لا أحد توقّف، أو الميزة متوقفة.", "Either nobody stalled, or the feature is off.")} />}
        <div className="mt-4">
          <Form action={P.nudgesUrl}>
            <input type="hidden" name="on" value={P.nudges ? "0" : "1"} />
            <Btn sm variant="ghost" icon={P.nudges ? "shield" : "bolt"} type="submit">
              {P.nudges ? bi("أوقف رسائل التفعيل", "Turn nudges off")
                        : bi("شغّل رسائل التفعيل", "Turn nudges on")}
            </Btn>
          </Form>
        </div>
      </Card>

      {/* ---------- الإرسال ---------- */}
      <Card>
        <SectionTitle icon="mail">{bi("إرسال التقرير", "Sending the report")}</SectionTitle>
        <p className="mt-0 mb-4 text-[12.5px] leading-relaxed text-ink-3">
          {bi("يُرسل تلقائياً مرة كل أسبوع إلى بريد الإدارة وإلى تليجرام (خلاصته وأهم ما يحتاج تدخّلك).",
              "It is sent automatically once a week to the admin email and to Telegram (summary plus what needs you).")}
          {P.lastSent ? bi(` آخر إرسال: ${fmtDate(P.lastSent)}.`, ` Last sent: ${fmtDate(P.lastSent)}.`) : ""}
          {!P.smtp && bi(" ⚠️ SMTP غير مضبوط — سيصل على تليجرام وحده.",
                         " ⚠️ SMTP is not configured — Telegram only.")}
        </p>
        <div className="flex flex-wrap items-center gap-3">
          <Form action={P.sendUrl}>
            <Btn icon="mail" type="submit">{bi("أرسله الآن", "Send it now")}</Btn>
          </Form>
          <Form action={P.autoUrl}>
            <input type="hidden" name="on" value={P.auto ? "0" : "1"} />
            <Btn variant="ghost" icon={P.auto ? "shield" : "bolt"} type="submit">
              {P.auto ? bi("أوقف الإرسال الأسبوعي", "Turn weekly sending off")
                      : bi("شغّل الإرسال الأسبوعي", "Turn weekly sending on")}
            </Btn>
          </Form>
          <Pill tone={P.auto ? "on" : "mute"} dot={P.auto}>
            {P.auto ? bi("الإرسال الأسبوعي مفعّل", "Weekly sending is on")
                    : bi("الإرسال الأسبوعي متوقف", "Weekly sending is off")}
          </Pill>
        </div>
      </Card>
    </>
  );
}

/* ======================================================= تحليل المحادثات */
export function ConvInsights() {
  const c = P.c || {}, tot = P.totals || {};
  const res = c.response || {};
  const maxHour = Math.max(1, ...(c.hours || []).map((h) => h.v));
  const DAYS = [["السبت", "Sat"], ["الأحد", "Sun"], ["الاثنين", "Mon"], ["الثلاثاء", "Tue"],
                ["الأربعاء", "Wed"], ["الخميس", "Thu"], ["الجمعة", "Fri"]];
  const secs = (s) => (s == null ? "—" : s < 60 ? bi(`${s} ثانية`, `${s}s`)
    : s < 3600 ? bi(`${Math.round(s / 60)} دقيقة`, `${Math.round(s / 60)}m`)
    : bi(`${(s / 3600).toFixed(1)} ساعة`, `${(s / 3600).toFixed(1)}h`));

  return (
    <>
      <PageHead icon="chat" title={t("adm_convo")}
        sub={bi(`${P.label} — كل رسالة بين العميل والبوت والذكاء الاصطناعي وصاحب النشاط.`,
                `${P.label} — every message between customers, the bot, the AI and the business owner.`)}
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <DayTabs days={P.days} options={P.options} base={P.botId ? `&bot=${P.botId}` : ""} />
            <Btn sm variant="ghost" icon="chart" href={P.reportUrl}>{t("adm_report")}</Btn>
            <Btn sm variant="ghost" icon="download" href={P.csvUrl}>{bi("تصدير", "Export")}</Btn>
          </div>} />

      <Card className="mb-6">
        <form method="get" className="flex flex-wrap items-end gap-3">
          <input type="hidden" name="days" value={P.days} />
          <div className="min-w-[240px] flex-1">
            <Select name="bot" defaultValue={String(P.botId || "")}
                    onChange={(e) => e.target.form.submit()}>
              <option value="">{bi("كل البوتات", "All bots")}</option>
              {(P.bots || []).map((b) => (
                <option key={b.id} value={b.id}>{b.name} — {b.owner}</option>
              ))}
            </Select>
          </div>
          <ul className="m-0 flex min-w-[240px] flex-1 list-none flex-col gap-1.5 p-0
                         text-[13px] leading-relaxed text-ink-2">
            {(P.head || []).map((h, i) => (
              <li key={i} className="flex items-start gap-2">
                <span className="mt-1.5 size-1.5 shrink-0 rounded-full bg-au-cyan" />{h}
              </li>
            ))}
          </ul>
        </form>
      </Card>

      <Grid cols={4} className="mb-6">
        <Kpi label={bi("كل الرسائل", "All messages")} value={num(c.messages)}
             hint={bi(`${num(c.in_count)} واردة · ${num(c.out_count)} صادرة`,
                      `${num(c.in_count)} in · ${num(c.out_count)} out`)} />
        <Kpi label={bi("محادثات", "Conversations")} value={num(c.conversations)}
             hint={bi(`${num(c.one_and_done)} رسالة واحدة فقط`, `${num(c.one_and_done)} one-message only`)} />
        <Kpi label={bi("نسبة الرد", "Answer rate")} value={`${c.answer_rate || 0}%`}
             cls={(c.answer_rate || 0) < 85 ? "text-amber-200" : "text-au-teal"}
             hint={bi(`${num(c.unanswered_total)} سؤال بلا إجابة`, `${num(c.unanswered_total)} unanswered`)} />
        <Kpi label={bi("ينتظرون رداً", "Waiting for a reply")} value={num(c.waiting_total)}
             cls={c.waiting_total ? "text-red-300" : "text-ink"}
             hint={bi(`${num(c.repeat_customers)} عميل عاد أكثر من يوم`,
                      `${num(c.repeat_customers)} customers came back another day`)} />
      </Grid>

      {c.truncated && (
        <Card className="mb-6 !bg-yellow-400/[0.06]">
          <p className="m-0 text-[13px] leading-relaxed text-amber-200">
            {bi("الرسائل أكثر من سقف التحليل، فحُلِّل الأحدث منها فقط — قلّل عدد الأيام أو اختر بوتاً بعينه لتحليل أدقّ.",
                "There are more messages than the analysis cap, so only the newest were analysed — narrow the period or pick one bot.")}
          </p>
        </Card>
      )}

      {/* ---------- الأسئلة بلا إجابة: أهم قائمة في الصفحة ---------- */}
      <Card className="mb-6">
        <SectionTitle icon="help">{bi("أسئلة سألها العملاء ولم تجد إجابة", "Questions customers asked that got no answer")}</SectionTitle>
        <p className="mt-0 mb-4 text-[12.5px] leading-relaxed text-ink-3">
          {bi("رسالة عميل لم يتبعها ردّ خلال 6 ساعات. كل سطر هنا ردٌّ جاهز ينقص البوت — وأسرع تحسين ممكن.",
              "A customer message with no reply within 6 hours. Every line here is a missing canned answer — the fastest improvement available.")}
        </p>
        {(c.unanswered || []).length ? (
          <Table head={[bi("السؤال", "Question"), bi("تكرّر", "Times"), bi("البوت", "Bot")]}>
            {c.unanswered.map((q, i) => (
              <Tr key={i}>
                <Td>{q.sample || q.k}</Td>
                <Td className="tnum font-bold text-ink">{q.v}</Td>
                <Td className="text-[12px] text-ink-3">#{q.bot_id}</Td>
              </Tr>
            ))}
          </Table>
        ) : <Empty icon="shield" title={bi("كل سؤال وجد إجابة", "Every question got an answer")} />}
      </Card>

      <Grid cols={2} className="mb-6">
        <Card>
          <SectionTitle icon="grid">{bi("نيّة الرسائل", "Message intent")}</SectionTitle>
          <Rank items={c.intents} fmt={(x) => `${intentLabel(x.k)} — ${x.pct}%`}
                empty={bi("لا رسائل", "No messages")} />
        </Card>
        <Card>
          <SectionTitle icon="chat">{bi("عبارات تتكرر حرفياً", "Repeated phrases")}</SectionTitle>
          <Rank items={c.phrases} fmt={(x) => x.sample || x.k}
                empty={bi("لا عبارة تكررت", "Nothing repeated yet")} />
        </Card>
      </Grid>

      <Grid cols={2} className="mb-6">
        <Card>
          <SectionTitle icon="bolt">{bi("سرعة الرد", "Reply speed")}</SectionTitle>
          <Table head={[bi("من يردّ", "Responder"), bi("ردود", "Replies"), bi("الوسيط", "Median"),
                        bi("أبطأ 10%", "Slowest 10%")]}>
            {[["bot", bi("البوت (فلو)", "Bot (flow)")], ["ai", bi("عقل البوت", "AI brain")],
              ["human", bi("صاحب النشاط", "Business owner")]].map(([k, lbl]) => (
              <Tr key={k}>
                <Td>{lbl}</Td>
                <Td className="tnum">{res[k] ? num(res[k].n) : "—"}</Td>
                <Td className="tnum font-bold text-ink">{res[k] ? secs(res[k].median) : "—"}</Td>
                <Td className="tnum">{res[k] ? secs(res[k].p90) : "—"}</Td>
              </Tr>
            ))}
          </Table>
          <p className="mt-4 mb-0 text-[12px] leading-relaxed text-ink-3">
            {bi("الوسيط أصدق من المتوسط هنا: ردّ واحد متأخر ساعتين يرفع المتوسط ويخفي أن الباقي فوري.",
                "The median beats the average here: one two-hour reply skews the mean and hides that the rest were instant.")}
          </p>
        </Card>
        <Card>
          <SectionTitle icon="sparkles">{bi("نبرة الرسائل", "Tone")}</SectionTitle>
          <Grid cols={3} className="mb-4">
            <Kpi label={bi("سلبية", "Negative")} value={num(c.sentiment?.neg)}
                 cls={c.sentiment?.neg ? "text-red-300" : "text-ink"}
                 hint={`${c.sentiment?.neg_pct || 0}%`} />
            <Kpi label={bi("إيجابية", "Positive")} value={num(c.sentiment?.pos)} cls="text-au-teal" />
            <Kpi label={bi("محايدة", "Neutral")} value={num(c.sentiment?.neutral)} />
          </Grid>
          {(c.negatives || []).length ? (
            <ul className="m-0 flex list-none flex-col gap-2 p-0 text-[13px] leading-relaxed text-ink-2">
              {c.negatives.slice(0, 5).map((x, i) => (
                <li key={i} className="flex items-start gap-2 rounded-lg bg-red-400/[0.07] px-3 py-2">
                  {x.count > 1 && <b className="tnum shrink-0 text-red-300">{x.count}×</b>}
                  <span className="min-w-0">{x.text}</span>
                </li>
              ))}
            </ul>
          ) : <Empty icon="sparkles" title={bi("لا شكاوى ظاهرة", "No visible complaints")} />}
        </Card>
      </Grid>

      <Grid cols={2} className="mb-6">
        <Card>
          <SectionTitle icon="calendar">{bi("ساعات ذروة الرسائل", "Peak hours")}</SectionTitle>
          <div className="flex h-28 items-end gap-[3px]" dir="ltr">
            {(c.hours || []).map((h) => (
              <div key={h.k} title={`${h.k}:00 · ${h.v}`}
                   className="flex-1 rounded-t bg-au-violet/60 hover:bg-au-violet"
                   style={{ height: `${Math.max(3, (h.v / maxHour) * 100)}%` }} />
            ))}
          </div>
          <div className="mt-2 flex justify-between text-[11px] text-ink-3" dir="ltr">
            <span>00</span><span>06</span><span>12</span><span>18</span><span>23</span>
          </div>
        </Card>
        <Card>
          <SectionTitle icon="calendar">{bi("أيام الأسبوع", "Days of the week")}</SectionTitle>
          <Rank items={(c.weekdays || []).map((w) => ({ k: bi(DAYS[w.k][0], DAYS[w.k][1]), v: w.v }))}
                empty={bi("لا رسائل", "No messages")} />
        </Card>
      </Grid>

      <Grid cols={2} className="mb-6">
        <Card>
          <SectionTitle icon="grid">{bi("أكثر الكلمات", "Most used words")}</SectionTitle>
          {(c.keywords || []).length ? (
            <div className="flex flex-wrap gap-2">
              {c.keywords.map((w) => (
                <span key={w.k} className="rounded-full bg-white/[0.06] px-3 py-1.5 text-[13px] text-ink-2">
                  {w.k} <b className="tnum text-au-cyan">{w.v}</b>
                </span>
              ))}
            </div>
          ) : <Empty icon="grid" title={bi("لا كلمات", "No words")} />}
        </Card>
        <Card>
          <SectionTitle icon="settings">{bi("رسائل النظام", "System messages")}</SectionTitle>
          <Rank items={c.system} empty={bi("لا رسائل نظام", "No system messages")} />
        </Card>
      </Grid>

      <Card className="mb-6">
        <SectionTitle icon="bot">{bi("كل بوت", "Per bot")}</SectionTitle>
        {(c.bots || []).length ? (
          <Table head={[bi("البوت", "Bot"), bi("وارد", "In"), bi("صادر", "Out"), bi("عملاء", "Customers"),
                        bi("بلا إجابة", "Unanswered"), bi("نسبة الرد", "Answer rate"),
                        bi("أكثر نيّة", "Top intent")]}>
            {c.bots.map((b) => (
              <Tr key={b.bot_id}>
                <Td><b className="text-ink">{b.name}</b></Td>
                <Td className="tnum">{num(b.msgs_in)}</Td>
                <Td className="tnum">{num(b.msgs_out)}</Td>
                <Td className="tnum">{num(b.customers)}</Td>
                <Td className={`tnum ${b.unanswered ? "text-amber-200" : ""}`}>{num(b.unanswered)}</Td>
                <Td className="tnum font-bold text-ink">{b.answer_rate}%</Td>
                <Td>{intentLabel(b.top_intent)}</Td>
              </Tr>
            ))}
          </Table>
        ) : <Empty icon="bot" title={bi("لا بيانات", "No data")} />}
      </Card>

      {(c.waiting || []).length > 0 && (
        <Card>
          <SectionTitle icon="help">{bi("محادثات تنتظر رداً الآن", "Conversations waiting right now")}</SectionTitle>
          <Table head={[bi("البوت", "Bot"), bi("العميل", "Customer"), bi("آخر رسالة", "Last message"),
                        bi("منذ", "Since")]}>
            {c.waiting.map((w, i) => (
              <Tr key={i}>
                <Td className="text-[12px] text-ink-3">#{w.bot_id}</Td>
                <Td dir="ltr" className="text-[12px]">{w.peer}</Td>
                <Td>{w.text}</Td>
                <Td className="text-[12px] text-ink-3">{fmtDate(w.since)}</Td>
              </Tr>
            ))}
          </Table>
        </Card>
      )}
    </>
  );
}
