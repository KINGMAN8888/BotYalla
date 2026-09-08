import { useEffect, useState } from "react";
import {
  BY, P, t, bi, Icon, Card, Btn, Field, Input, Textarea, Select, Form,
  Pill, Empty, PageHead, SectionTitle,
} from "../kit.jsx";

const LANGS = [
  ["ar", "العربية — ar"], ["ar_EG", "العربية (مصر) — ar_EG"],
  ["en", "English — en"], ["en_US", "English (US) — en_US"],
];

const CAT_LABEL = {
  UTILITY: bi("خدمية — تأكيد طلب، تذكير، تحديث حالة", "Utility — order confirmations, reminders, updates"),
  MARKETING: bi("تسويقية — عروض وإعلانات (الأغلى، وتحتاج موافقة العميل)",
                "Marketing — offers and announcements (priciest, needs opt-in)"),
  AUTHENTICATION: bi("مصادقة — أكواد تحقق فقط", "Authentication — verification codes only"),
};

const STATUS = {
  APPROVED: { tone: "on", label: () => t("wa_tpl_approved") },
  PENDING:  { tone: "mute", label: () => t("wa_tpl_pending") },
  IN_APPEAL: { tone: "mute", label: () => t("wa_tpl_pending") },
  REJECTED: { tone: "off", label: () => t("wa_tpl_rejected") },
  PAUSED:   { tone: "off", label: () => bi("موقوف", "Paused") },
  DISABLED: { tone: "off", label: () => bi("معطّل", "Disabled") },
};

/* ------------------------------------------------- ربط حساب واتساب للأعمال */
function WabaSetup({ bot, hint }) {
  return (
    <Card className="mb-6">
      <SectionTitle icon="link">{t("wa_waba_title")}</SectionTitle>
      <p className="mt-0 mb-4 text-[13px] leading-relaxed text-ink-3">{t("wa_waba_hint")}</p>
      <Form action={`/bot/${bot.id}/templates/waba`}>
        <div className="flex flex-wrap items-end gap-3">
          <div className="min-w-[240px] flex-1">
            <Field label="WhatsApp Business Account ID">
              <Input name="waba_id" required inputMode="numeric" autoComplete="off"
                     defaultValue={hint || ""} placeholder="102290129340398" />
            </Field>
          </div>
          <Btn icon="check" type="submit">{t("wa_waba_save")}</Btn>
        </div>
      </Form>
      {hint && (
        <p className="mt-3 mb-0 text-[12.5px] text-ink-3">
          <Icon name="sparkles" size={13} className="me-1 inline align-[-2px] text-au-cyan" />
          {t("wa_waba_guess")}
        </p>
      )}
      <p className="mt-4 mb-0 text-[12.5px] text-ink-3">
        <a href="https://business.facebook.com/settings/whatsapp-business-accounts"
           target="_blank" rel="noopener"
           className="text-au-cyan underline-offset-4 hover:underline">
          {bi("افتح إعدادات حسابات واتساب في Meta ↗", "Open WhatsApp accounts in Meta ↗")}
        </a>
      </p>
    </Card>
  );
}

/* ------------------------------------------------------------ قالب واحد */
function TemplateCard({ tpl, bot }) {
  const s = STATUS[tpl.status] || { tone: "mute", label: () => tpl.status };
  return (
    <Card className="mb-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-[15px] font-extrabold text-ink">{tpl.name}</span>
            <Pill tone={s.tone} dot={tpl.status === "APPROVED"}>{s.label()}</Pill>
            <Pill tone="mute">{tpl.language}</Pill>
            <Pill tone="mute">{tpl.category}</Pill>
            {/* نعرض المتغيّرات نفسها لا عددها — أنفع للقارئ، ويتجنّب «1 متغيّرات» */}
            {tpl.vars.length > 0 && (
              <Pill tone="mute">{tpl.vars.map((n) => `{{${n}}}`).join(" ")}</Pill>
            )}
          </div>
        </div>
        <Form action={`/bot/${bot.id}/templates/delete`} className="inline"
              confirm={bi(`حذف القالب «${tpl.name}» من Meta نهائياً؟`,
                          `Delete template «${tpl.name}» from Meta permanently?`)}>
          <input type="hidden" name="name" value={tpl.name} />
          <Btn variant="red" sm icon="trash" type="submit"
               aria-label={bi("حذف القالب", "Delete template")} />
        </Form>
      </div>

      <div className="mt-4 rounded-xl bg-white/[0.04] p-4">
        {tpl.header && <div className="mb-2 text-[13.5px] font-extrabold text-ink">{tpl.header}</div>}
        <div className="whitespace-pre-wrap text-[13.5px] leading-relaxed text-ink-2">{tpl.body}</div>
        {tpl.footer && <div className="mt-2 text-[12px] text-ink-3">{tpl.footer}</div>}
        {tpl.buttons.length > 0 && (
          <div className="mt-3 flex flex-wrap gap-2">
            {tpl.buttons.map((b, i) => (
              <span key={i} className="rounded-lg px-3 py-1.5 text-[12.5px] font-bold text-au-cyan
                                       shadow-[inset_0_0_0_1px_rgb(255_255_255/0.12)]">{b}</span>
            ))}
          </div>
        )}
      </div>

      {tpl.status === "REJECTED" && tpl.rejected_reason && (
        <p className="mt-3 mb-0 text-[12.5px] font-bold text-red-300">
          {bi("سبب الرفض من Meta: ", "Meta's rejection reason: ")}{tpl.rejected_reason}
        </p>
      )}
    </Card>
  );
}

/* ---------------------------------------------------------- إنشاء قالب */
function CreateTemplate({ bot, cats, limits }) {
  const [body, setBody] = useState("");
  const [buttons, setButtons] = useState([""]);
  const vars = [...new Set((body.match(/\{\{(\d+)\}\}/g) || []))].sort();

  return (
    <Card>
      <SectionTitle icon="plus">{t("wa_tpl_new")}</SectionTitle>
      <Form action={`/bot/${bot.id}/templates/create`}>
        <div className="grid gap-4 sm:grid-cols-3">
          <Field label={t("wa_tpl_name")} hint={t("wa_tpl_name_hint")}>
            <Input name="name" required autoComplete="off" spellCheck="false"
                   pattern="[a-z0-9_]+" placeholder="order_ready" />
          </Field>
          <Field label={t("wa_tpl_lang")}>
            <Select name="language" defaultValue={BY.lang === "en" ? "en" : "ar"}>
              {LANGS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </Select>
          </Field>
          <Field label={t("wa_tpl_cat")}>
            <Select name="category" defaultValue="UTILITY">
              {cats.map((c) => <option key={c} value={c}>{c}</option>)}
            </Select>
          </Field>
        </div>

        <p className="mt-3 mb-0 text-[12.5px] leading-relaxed text-ink-3">
          {CAT_LABEL.UTILITY}<br />{CAT_LABEL.MARKETING}
        </p>

        <div className="mt-5">
          <Field label={t("wa_tpl_header")}>
            <Input name="header" maxLength={limits.header} autoComplete="off"
                   placeholder={bi("طلبك جاهز", "Your order is ready")} />
          </Field>
        </div>

        <div className="mt-4">
          <Field label={t("wa_tpl_body")} hint={t("wa_tpl_body_hint")}>
            <Textarea name="body" required maxLength={limits.body} value={body}
                      onChange={(e) => setBody(e.target.value)} className="min-h-[120px]"
                      placeholder={bi("أهلاً {{1}}، طلبك رقم {{2}} جاهز للاستلام.",
                                      "Hi {{1}}, your order {{2}} is ready for pickup.")} />
          </Field>
          <div className="mt-2 flex flex-wrap items-center justify-between gap-2 text-[12.5px] text-ink-3">
            <span>
              {vars.length > 0
                ? `${t("wa_tpl_vars")}: ${vars.join(" ")}`
                : bi("بلا متغيّرات — نفس النص للجميع", "No variables — same text for everyone")}
            </span>
            <span className="tnum">{body.length} / {limits.body}</span>
          </div>
        </div>

        <div className="mt-4">
          <Field label={t("wa_tpl_footer")}>
            <Input name="footer" maxLength={limits.footer} autoComplete="off"
                   placeholder={bi("شكراً لثقتك", "Thanks for your trust")} />
          </Field>
        </div>

        <div className="mt-4">
          <div className="mb-2 text-[13px] font-bold text-ink-2">{t("wa_tpl_buttons")}</div>
          <div className="grid gap-3 sm:grid-cols-3">
            {buttons.map((b, i) => (
              <Input key={i} name="button" maxLength={25} value={b} autoComplete="off"
                     onChange={(e) => setButtons(buttons.map((x, j) => (j === i ? e.target.value : x)))}
                     placeholder={bi("نعم", "Yes")} />
            ))}
          </div>
          {buttons.length < 3 && (
            <div className="mt-3">
              <Btn variant="ghost" sm icon="plus" type="button"
                   onClick={() => setButtons([...buttons, ""])}>
                {bi("زر آخر", "Another button")}
              </Btn>
            </div>
          )}
        </div>

        <div className="mt-6">
          <Btn icon="rocket" type="submit">{t("wa_tpl_submit")}</Btn>
        </div>
      </Form>
    </Card>
  );
}

/* --------------------------------------------------------------- الصفحة */
export default function WaTemplates() {
  const { bot, waba, wabaHint, cats = [], limits = {} } = P;
  const [state, setState] = useState({ loading: !!waba, items: [], error: null });

  useEffect(() => {
    if (!waba) return;
    let alive = true;
    fetch(`/api/bot/${bot.id}/templates`)
      .then((r) => r.json())
      .then((d) => alive && setState({ loading: false, items: d.items || [], error: d.ok ? null : d.error }))
      .catch(() => alive && setState({ loading: false, items: [],
        error: bi("تعذّر الوصول إلى Meta الآن.", "Could not reach Meta right now.") }));
    return () => { alive = false; };
  }, [bot.id, waba]);

  return (
    <>
      <PageHead icon="megaphone" title={t("wa_tpl_title")} sub={t("wa_tpl_sub")}
        actions={<Btn variant="ghost" sm icon="back" href={`/bot/${bot.id}`}>{t("back")}</Btn>} />

      {!waba ? (
        <WabaSetup bot={bot} hint={wabaHint} />
      ) : (
        <>
          {state.loading && (
            <Card className="mb-6"><span className="text-[13px] text-ink-3">
              {bi("جاري الجلب من Meta…", "Fetching from Meta…")}
            </span></Card>
          )}

          {state.error && (
            <Card className="mb-6">
              <p className="m-0 text-[13px] font-bold text-red-300">{state.error}</p>
              <p className="mt-2 mb-0 text-[12.5px] text-ink-3">
                {bi("لو انتهت صلاحية التوكن، جدّده من إعدادات البوت.",
                    "If the token expired, refresh it in the bot settings.")}
              </p>
            </Card>
          )}

          {!state.loading && !state.error && state.items.length === 0 && (
            <Card className="mb-6">
              <Empty icon="inbox" title={bi("لا قوالب بعد", "No templates yet")}
                     text={t("wa_tpl_none")} />
            </Card>
          )}

          {state.items.map((tpl) => <TemplateCard key={tpl.id || tpl.name} tpl={tpl} bot={bot} />)}

          <CreateTemplate bot={bot} cats={cats} limits={limits} />
        </>
      )}
    </>
  );
}
