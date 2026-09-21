import { useState } from "react";
import {
  BY, P, t, bi, Icon, Card, Btn, Field, Input, Select, Form,
  Grid, Stat, Pill, Empty, PageHead, SectionTitle, Table, Tr, Td, num, fmtDate,
} from "../kit.jsx";

const EGP = () => t("egp");

/* ======================================================= الأسعار والخصومات */
export function AdminPricing() {
  const plans = P.plans || [];
  // معاينة حيّة: يرى المالك السعر النهائي قبل الحفظ
  const [draft, setDraft] = useState(
    Object.fromEntries(plans.map((p) => [p.id, { price: p.list_price, disc: p.discount_pct }]))
  );
  const set = (id, k, v) => setDraft((d) => ({ ...d, [id]: { ...d[id], [k]: v } }));
  const final = (id) => {
    const d = draft[id] || {};
    const price = parseFloat(d.price);
    const disc = Math.min(90, Math.max(0, parseFloat(d.disc) || 0));
    if (!isFinite(price)) return null;
    return Math.round(price * (1 - disc / 100) * 100) / 100;
  };

  return (
    <>
      <PageHead icon="tag" title={t("adm_pricing")} sub={t("adm_pricing_sub")} />
      <Form action="">
        <div className="grid gap-4 lg:grid-cols-2">
          {plans.filter((p) => p.id !== "free").map((p) => {
            const f = final(p.id);
            const has = f !== null && f < parseFloat(draft[p.id]?.price);
            return (
              <Card key={p.id} spot>
                <SectionTitle icon={p.id === "pro" ? "bolt" : "crown"}>{p.name}</SectionTitle>
                <div className="grid gap-4 sm:grid-cols-2">
                  <Field label={`${t("list_price")} (${EGP()})`} hint={t("price_hint")}>
                    <Input name={`price_${p.id}`} inputMode="decimal" defaultValue={p.list_price}
                           onChange={(e) => set(p.id, "price", e.target.value)} />
                  </Field>
                  <Field label={t("discount_pct")}>
                    <Input name={`disc_${p.id}`} inputMode="decimal" min="0" max="90"
                           defaultValue={p.discount_pct}
                           onChange={(e) => set(p.id, "disc", e.target.value)} />
                  </Field>
                </div>
                <div className="mt-5 flex items-center justify-between gap-3 rounded-2xl bg-black/25 px-5 py-4
                                shadow-[inset_0_0_0_1px_rgb(255_255_255/0.08)]">
                  <span className="text-[13px] text-ink-3">{t("final_price")}</span>
                  <span className="flex items-baseline gap-2.5">
                    {has && (
                      <span className="text-[15px] text-ink-3 line-through">{num(draft[p.id].price)}</span>
                    )}
                    <b className="text-[26px] font-extrabold text-ink tnum">{f === null ? "—" : num(f)}</b>
                    <span className="text-[13px] text-ink-3">{EGP()}</span>
                    {has && <Pill tone="on">-{Math.round(draft[p.id].disc)}%</Pill>}
                  </span>
                </div>
              </Card>
            );
          })}
        </div>
        <div className="mt-6"><Btn icon="check" type="submit">{t("save_pricing")}</Btn></div>
      </Form>
    </>
  );
}

/* ============================================================ أكواد الخصم */
export function AdminPromos() {
  const promos = P.promos || [];
  const plans = P.plans || [];
  const [kind, setKind] = useState("percent");

  return (
    <>
      <PageHead icon="bolt" title={t("adm_promos")} sub={t("adm_promos_sub")} />

      <Card className="mb-6">
        <SectionTitle icon="plus">{t("promo_create")}</SectionTitle>
        <Form action="">
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <Field label={t("promo_code")}>
              <Input name="code" required placeholder="RAMADAN25"
                     className="uppercase" autoComplete="off" />
            </Field>
            <Field label={t("promo_kind")}>
              <Select name="kind" value={kind} onChange={(e) => setKind(e.target.value)}>
                <option value="percent">{t("promo_percent")}</option>
                <option value="fixed">{t("promo_fixed")}</option>
              </Select>
            </Field>
            <Field label={`${t("promo_value")} ${kind === "percent" ? "(%)" : `(${EGP()})`}`}>
              <Input name="value" required inputMode="decimal"
                     max={kind === "percent" ? 90 : undefined} />
            </Field>
            <Field label={t("promo_plan")}>
              <Select name="plan" defaultValue="">
                <option value="">{t("promo_all_plans")}</option>
                {plans.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
              </Select>
            </Field>
            <Field label={t("promo_max_uses")}>
              <Input name="max_uses" inputMode="numeric" placeholder={t("unlimited_uses")} />
            </Field>
            <Field label={t("promo_expires")}>
              <Input name="expires_at" type="date" />
            </Field>
            <label className="flex cursor-pointer items-center gap-2.5 self-end pb-2.5">
              <input type="checkbox" name="per_user_once" defaultChecked className="peer sr-only" />
              <span className="grid size-5 place-items-center rounded-md text-transparent
                               shadow-[inset_0_0_0_1px_rgb(255_255_255/0.2)] transition-colors
                               peer-checked:bg-au-violet peer-checked:text-white">
                <Icon name="check" size={13} />
              </span>
              <span className="text-[13px] font-bold text-ink-2">{t("promo_once")}</span>
            </label>
          </div>
          <div className="mt-5"><Btn icon="plus" type="submit">{t("promo_create")}</Btn></div>
        </Form>
      </Card>

      <Card>
        {promos.length ? (
          <Table head={[t("promo_code"), t("promo_kind"), t("promo_plan"), t("promo_uses"),
                        t("promo_saved"), t("promo_expires"), t("col_status"), ""]}>
            {promos.map((p) => {
              const expired = p.expires_at && p.expires_at * 1000 < Date.now();
              const exhausted = p.max_uses != null && p.used >= p.max_uses;
              return (
                <Tr key={p.id}>
                  <Td><code className="rounded-lg bg-black/30 px-2.5 py-1 font-bold text-au-cyan">{p.code}</code></Td>
                  <Td>{p.kind === "percent" ? `${num(p.value)}%` : `${num(p.value)} ${EGP()}`}</Td>
                  <Td>{p.plan ? (plans.find((x) => x.id === p.plan)?.name || p.plan) : t("promo_all_plans")}</Td>
                  <Td className="tnum">{num(p.used)}{p.max_uses != null ? ` / ${num(p.max_uses)}` : ""}</Td>
                  <Td className="tnum">{num(p.saved)} {EGP()}</Td>
                  <Td>{p.expires_at ? fmtDate(p.expires_at) : "—"}</Td>
                  <Td>
                    {!p.is_active ? <Pill tone="mute">{t("aff_paused")}</Pill>
                      : expired ? <Pill tone="off">{t("status_expired")}</Pill>
                      : exhausted ? <Pill tone="warn">{t("promo_exhausted")}</Pill>
                      : <Pill tone="on" dot>{t("status_active")}</Pill>}
                  </Td>
                  <Td>
                    <div className="flex gap-2">
                      <Form action={`/admin/promos/${p.id}/${p.is_active ? "off" : "on"}`} className="inline">
                        <Btn sm variant="ghost" type="submit">
                          {p.is_active ? t("aff_paused") : t("aff_active")}
                        </Btn>
                      </Form>
                      <Form action={`/admin/promos/${p.id}/delete`} className="inline"
                            confirm={bi("حذف الكود نهائياً؟", "Delete this code permanently?")}>
                        <Btn sm variant="red" icon="trash" type="submit"
                             aria-label={bi("حذف", "Delete")} />
                      </Form>
                    </div>
                  </Td>
                </Tr>
              );
            })}
          </Table>
        ) : <Empty icon="bolt" title={t("no_promos")} />}
      </Card>
    </>
  );
}

/* ================================================================ الأفيليت */
export function AdminAffiliates() {
  const rows = P.affiliates || [];
  const totals = rows.reduce((a, r) => ({
    earned: a.earned + (r.total_earned || 0),
    due: a.due + (r.due || 0),
    conv: a.conv + (r.conversions || 0),
  }), { earned: 0, due: 0, conv: 0 });

  return (
    <>
      <PageHead icon="users" title={t("adm_affiliates")} sub={t("adm_affiliates_sub")} />

      <Grid cols={4} className="mb-6">
        <Stat icon="users"  value={rows.length}   label={t("adm_affiliates")} />
        <Stat icon="check"  value={totals.conv}   label={t("aff_conversions")} />
        <Stat icon="wallet" value={totals.earned} label={`${t("aff_earned")} (${EGP()})`} decimals={2} />
        <Stat icon="card"   value={totals.due}    label={`${t("aff_due")} (${EGP()})`} decimals={2} />
      </Grid>

      <Card className="mb-6">
        <SectionTitle icon="settings">{t("aff_default_rate")}</SectionTitle>
        <Form action="" className="flex flex-wrap items-end gap-4">
          <Field label={`${t("aff_rate")} (%)`} className="max-w-[200px]">
            <Input name="default_rate" inputMode="decimal" defaultValue={P.defaultRate} />
          </Field>
          <Btn icon="check" type="submit">{t("save")}</Btn>
        </Form>
      </Card>

      <Card>
        {rows.length ? (
          <Table head={[t("username"), t("aff_code"), t("aff_rate"), t("aff_signups"),
                        t("aff_conversions"), t("aff_earned"), t("aff_due"), t("col_status"), ""]}>
            {rows.map((a) => (
              <Tr key={a.user_id}>
                <Td className="font-bold text-ink">{a.username}</Td>
                <Td><code className="rounded-lg bg-black/30 px-2.5 py-1 text-au-cyan">{a.code}</code></Td>
                <Td>
                  <Form action={`/admin/affiliates/${a.user_id}/rate`} className="flex items-center gap-1.5">
                    <Input name="rate_pct" defaultValue={a.rate_pct} inputMode="decimal"
                           className="!w-[70px] !py-1.5 !text-[13px]" />
                    <Btn sm variant="ghost" icon="check" type="submit"
                         aria-label={bi("حفظ النسبة", "Save rate")} />
                  </Form>
                </Td>
                <Td className="tnum">{num(a.signups)}</Td>
                <Td className="tnum">{num(a.conversions)}</Td>
                <Td className="tnum">{num(a.total_earned)} {EGP()}</Td>
                <Td className="tnum font-bold text-au-teal">{num(a.due)} {EGP()}</Td>
                <Td>{a.is_active ? <Pill tone="on" dot>{t("aff_active")}</Pill>
                                 : <Pill tone="mute">{t("aff_paused")}</Pill>}</Td>
                <Td>
                  <div className="flex flex-wrap items-center gap-2">
                    {a.due > 0 && (
                      <Form action={`/admin/affiliates/${a.user_id}/payout`}
                            className="flex items-center gap-1.5"
                            confirm={bi("تأكيد صرف العمولة؟", "Confirm this payout?")}>
                        <Input name="amount" defaultValue={a.due} inputMode="decimal"
                               className="!w-[86px] !py-1.5 !text-[13px]" />
                        <Btn sm variant="green" type="submit">{t("aff_payout")}</Btn>
                      </Form>
                    )}
                    <Form action={`/admin/affiliates/${a.user_id}/toggle`} className="inline">
                      <Btn sm variant="ghost" type="submit">
                        {a.is_active ? t("aff_paused") : t("aff_active")}
                      </Btn>
                    </Form>
                  </div>
                </Td>
              </Tr>
            ))}
          </Table>
        ) : <Empty icon="users" title={t("aff_none")} />}
      </Card>
    </>
  );
}

/* ================================================= لوحة الشريك (للمستخدم) */
export function Affiliate() {
  const { aff, summary = {}, link, defaultRate } = P;
  const [copied, setCopied] = useState(false);

  if (!aff) {
    return (
      <>
        <PageHead icon="crown" title={t("aff_title")} sub={t("aff_sub")} />
        <Card className="max-w-[620px] text-center">
          <Icon name="crown" size={32} className="mx-auto text-au-cyan" />
          <p className="mx-auto mt-4 mb-6 max-w-[46ch] text-[14px] leading-relaxed text-ink-2">
            {t("aff_how")}
          </p>
          <Pill tone="mute">{t("aff_rate")}: {defaultRate}%</Pill>
          <Form action="" className="mt-6">
            <Btn icon="rocket" type="submit">{t("aff_join")}</Btn>
          </Form>
        </Card>
      </>
    );
  }

  return (
    <>
      <PageHead icon="crown" title={t("aff_title")} sub={t("aff_sub")} />

      <Grid cols={4} className="mb-6">
        <Stat icon="users"  value={summary.signups}     label={t("aff_signups")} />
        <Stat icon="check"  value={summary.conversions} label={t("aff_conversions")} />
        <Stat icon="wallet" value={aff.total_earned}    label={`${t("aff_earned")} (${EGP()})`} decimals={2} />
        <Stat icon="card"   value={(aff.total_earned || 0) - (aff.paid_out || 0)}
              label={`${t("aff_due")} (${EGP()})`} decimals={2} />
      </Grid>

      {/* العمولة المتكررة (سقف 12 شهراً): «المتوقع» تقدير من الاشتراكات النشطة، لا مبلغ مضمون */}
      <Grid cols={3} className="mb-6">
        <Stat icon="refresh" value={summary.renewals || 0} label={`${t("aff_renewals")} (${EGP()})`} decimals={2} />
        <Stat icon="users"   value={summary.active || 0}   label={t("aff_active_refs")} />
        <Stat icon="chart"   value={summary.expected_monthly || 0}
              label={`${t("aff_expected")} (${EGP()})`} decimals={2} />
      </Grid>

      <Card className="mb-6">
        <SectionTitle icon="link"
          extra={<Pill tone="on">{t("aff_rate")}: {aff.rate_pct}%</Pill>}>
          {t("aff_link")}
        </SectionTitle>
        <div className="flex flex-wrap items-center gap-2.5">
          <code className="min-w-0 flex-1 overflow-x-auto rounded-xl bg-black/30 px-4 py-3 text-[13px]
                           text-au-cyan shadow-[inset_0_0_0_1px_rgb(255_255_255/0.08)]">{link}</code>
          <Btn variant="ghost" icon={copied ? "check" : "copy"} type="button"
               onClick={() => navigator.clipboard?.writeText(link).then(() => {
                 setCopied(true); setTimeout(() => setCopied(false), 1500);
               })}>
            {copied ? t("copied") : t("copy")}
          </Btn>
        </div>
        <p className="mt-4 mb-0 text-[12.5px] leading-relaxed text-ink-3">{t("aff_how")}</p>
      </Card>

      <Card className="max-w-[420px]">
        <SectionTitle icon="key">{t("aff_code")}</SectionTitle>
        <div className="text-[28px] font-extrabold tracking-wider text-ink">{aff.code}</div>
      </Card>
    </>
  );
}
