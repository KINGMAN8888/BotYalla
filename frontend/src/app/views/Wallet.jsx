import { useState } from "react";
import {
  BY, P, t, Icon, Card, Btn, Field, Input, Select, Form,
  Pill, Empty, PageHead, SectionTitle, Table, Tr, Td, num, fmtDate,
} from "../kit.jsx";

/* رصيد الرسائل التسويقية (L-16).

   الرسالة التسويقية على واتساب تكلفة حقيقية لكل رسالة تدفعها المنصة لـMeta،
   فإدراجها داخل باقة ثابتة نزيف مضمون. الرصيد منفصل، والتكلفة تُعرض دائماً
   قبل الإرسال — والصفحة كلها عرضٌ فقط: كل خصم وشحن يجري في الخادم. */

const egp = (piastres) => (Number(piastres || 0) / 100);

export default function Wallet() {
  const { balance = 0, price = 0, ledger = [], plat = {}, qr,
          min = 50, max = 50000, presets = [], action } = P;
  const [amount, setAmount] = useState(presets[1] || min);
  const [copied, setCopied] = useState("");

  const canSend = price > 0 ? Math.floor(balance / price) : 0;
  const kinds = { topup: ["wallet_k_topup", "on"], spend: ["wallet_k_spend", "mute"],
                  refund: ["wallet_k_refund", "on"], adjust: ["wallet_k_adjust", "warn"] };

  const copy = (v, k) => {
    navigator.clipboard?.writeText(v).then(() => {
      setCopied(k); setTimeout(() => setCopied(""), 1400);
    });
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
      <PageHead icon="wallet" title={t("wallet_title")} />

      <Card className="mb-6 bg-[linear-gradient(120deg,rgb(124_108_246/0.18),rgb(34_211_238/0.06))]">
        <div className="flex flex-wrap items-end justify-between gap-5">
          <div>
            <div className="text-[13px] text-ink-3">{t("wallet_balance")}</div>
            <div className="mt-1 text-[38px] font-extrabold leading-none text-ink tnum">
              {num(egp(balance))}
              <span className="ms-2 text-[16px] font-bold text-ink-3">{t("egp")}</span>
            </div>
            <div className="mt-2 text-[13px] font-bold text-au-teal">
              {t("wallet_can_send").replace("{n}", num(canSend))}
            </div>
          </div>
          <div className="text-end">
            <div className="text-[12.5px] text-ink-3">{t("wallet_price")}</div>
            <div className="text-[18px] font-extrabold text-ink tnum">
              {num(egp(price))} {t("egp")}
            </div>
          </div>
        </div>
        <p className="mt-5 mb-0 max-w-[640px] text-[12.5px] leading-relaxed text-ink-3">
          {t("wallet_why")}
        </p>
      </Card>

      <Card className="mb-6">
        <SectionTitle icon="plus">{t("wallet_topup")}</SectionTitle>

        <div className="mb-5 grid gap-4 lg:grid-cols-3">
          <div className="rounded-2xl bg-white/[0.03] p-5 shadow-[inset_0_0_0_1px_rgb(255_255_255/0.08)]">
            <div className="flex items-center gap-2 font-extrabold text-[#FF6B6B]">
              <Icon name="phone" size={16} />{t("pay_vodafone")}
            </div>
            <CopyRow v={plat.vodafone_number} k="vf" />
          </div>
          <div className="rounded-2xl bg-white/[0.03] p-5 shadow-[inset_0_0_0_1px_rgb(255_255_255/0.08)]">
            <div className="flex items-center gap-2 font-extrabold text-au-violet">
              <Icon name="card" size={16} />{t("pay_instapay")}
            </div>
            {qr && <img src={qr} alt="InstaPay QR"
                        className="mx-auto my-3 w-[112px] rounded-xl bg-white p-1" />}
            <CopyRow v={plat.instapay_handle} k="ip" />
          </div>
          <div className="rounded-2xl bg-white/[0.03] p-5 shadow-[inset_0_0_0_1px_rgb(255_255_255/0.08)]">
            <div className="flex items-center gap-2 font-extrabold text-au-cyan">
              <Icon name="bank" size={16} />{t("pay_bank")}
            </div>
            <CopyRow v={plat.bank_account} k="acc" />
            <CopyRow v={plat.bank_iban} k="iban" />
          </div>
        </div>

        <Form action={action} encType="multipart/form-data">
          <div className="mb-4 flex flex-wrap gap-2">
            {presets.map((v) => (
              <button key={v} type="button" onClick={() => setAmount(v)}
                      className={"rounded-full px-4 py-1.5 text-[13px] font-extrabold transition-colors " +
                        (Number(amount) === v
                          ? "bg-[linear-gradient(100deg,#8FE9FF,#B9AFFF)] text-[#07090F]"
                          : "bg-white/[0.06] text-ink-2 hover:text-ink")}>
                {num(v)} {t("egp")}
              </button>
            ))}
          </div>
          <div className="grid gap-4 sm:grid-cols-3">
            <Field label={t("wallet_amount")}
                   hint={t("wallet_range").replace("{a}", num(min)).replace("{b}", num(max))}>
              <Input name="amount" type="number" min={min} max={max} required inputMode="numeric"
                     value={amount} onChange={(e) => setAmount(e.target.value)} />
            </Field>
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
          <div className="mt-3 text-[12.5px] text-ink-3">
            {/* الرصيد يُضاف بعد موافقة الأدمن — لا لحظة الرفع */}
            {t("pay_secure_note")}
          </div>
          <div className="mt-5"><Btn icon="shield" type="submit">{t("pay_submit")}</Btn></div>
        </Form>
      </Card>

      <Card>
        <SectionTitle icon="clock">{t("wallet_history")}</SectionTitle>
        {ledger.length ? (
          <Table head={["#", t("col_status"), t("col_amount"), t("wallet_balance"), t("col_date")]}>
            {ledger.map((x) => {
              const [label, tone] = kinds[x.kind] || [x.kind, "mute"];
              const up = x.delta > 0;
              return (
                <Tr key={x.id}>
                  <Td className="tnum">{x.id}</Td>
                  <Td><Pill tone={tone}>{t(label)}</Pill></Td>
                  <Td className={"tnum font-extrabold " + (up ? "text-au-teal" : "text-ink-2")}>
                    {up ? "+" : "−"}{num(Math.abs(egp(x.delta)))} {t("egp")}
                  </Td>
                  <Td className="tnum text-ink-3">{num(egp(x.balance_after))}</Td>
                  <Td className="text-ink-3">{fmtDate(x.created_at)}</Td>
                </Tr>
              );
            })}
          </Table>
        ) : <Empty icon="wallet" title={t("wallet_empty")} />}
      </Card>
    </>
  );
}
