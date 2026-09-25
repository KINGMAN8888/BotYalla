/* صفحة المطوّر: كل ما يحتاجه خادم الشريك ليبعث ويستقبل من رقم واحد.

   مبدآن يحكمان الصفحة:
   1. الأسرار لا تصل مع حمولة الصفحة أبداً (`app._SECRET_CFG`) — تُطلب بنداء مستقلّ
      بعد إعادة إدخال كلمة المرور، فلا تلتقطها لقطة شاشة ولا سجلّ متصفح.
   2. الإرسال والاستقبال بنية Meta حرفياً — الشريك يغيّر عنوان الأساس وحده. */
import { useState } from "react";
import {
  BY, P, t, bi, Icon, Card, Btn, Field, Input, Select, Form,
  Pill, Empty, PageHead, SectionTitle,
} from "../kit.jsx";

function when(ts) {
  if (!ts) return t("dev_key_never");
  return new Date(ts * 1000).toLocaleDateString(BY.lang === "en" ? "en-GB" : "ar-EG",
    { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

function Copy({ value, sm = true }) {
  const [done, setDone] = useState(false);
  return (
    <Btn sm={sm} variant="ghost" icon={done ? "check" : "copy"}
         onClick={() => navigator.clipboard?.writeText(value).then(() => {
           setDone(true); setTimeout(() => setDone(false), 1800);
         })}>
      {done ? t("dev_copied") : t("dev_copy")}
    </Btn>
  );
}

/* سطر بيان: القيمة قابلة للتحديد بالكامل والنسخ بضغطة */
function Row({ label, value, mono = true }) {
  return (
    <div className="flex flex-wrap items-center gap-2 py-2.5">
      <div className="min-w-[150px] text-[13px] font-bold text-ink-2">{label}</div>
      <code dir="ltr" className={`min-w-[200px] flex-1 select-all overflow-x-auto rounded-xl
                                  bg-ink-9/5 px-3 py-2 text-ink-1
                                  ${mono ? "text-[12.5px]" : "text-[13px]"}`}>
        {value || "—"}
      </code>
      {value && <Copy value={value} />}
    </div>
  );
}

/* ---------------------------------------- بوابة كلمة المرور قبل أي سرّ */
function Secrets() {
  const [state, setState] = useState({ open: !!P.sudo, token: "", relay: "", err: "", busy: false });
  const [pw, setPw] = useState("");

  async function reveal(e) {
    e.preventDefault();
    setState((s) => ({ ...s, busy: true, err: "" }));
    try {
      const r = await fetch(P.revealUrl, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRF-Token": BY.csrf },
        body: JSON.stringify({ password: pw }),
      });
      const d = await r.json().catch(() => ({}));
      setPw("");
      if (!r.ok || !d.ok) {
        setState((s) => ({ ...s, busy: false, err: d.error || t("sudo_bad") }));
        return;
      }
      setState({ open: true, token: d.token || "", relay: d.relaySecret || "", err: "", busy: false });
    } catch {
      setState((s) => ({ ...s, busy: false, err: t("sudo_bad") }));
    }
  }

  if (state.token || state.relay) {
    return (
      <>
        <Row label="WHATSAPP_ACCESS_TOKEN" value={state.token} />
        {state.relay && <Row label={t("dev_relay_secret")} value={state.relay} />}
        <p className="mt-2 mb-0 text-[12.5px] text-ink-3">
          <Icon name="lock" size={13} className="me-1 inline align-[-2px] text-au-cyan" />
          {t("sudo_open")}
        </p>
      </>
    );
  }

  return (
    <div className="mt-3 rounded-2xl bg-ink-9/5 p-4">
      <div className="mb-1 text-[13.5px] font-bold text-ink-1">
        <Icon name="lock" size={14} className="me-1.5 inline align-[-2px] text-au-cyan" />
        {t("sudo_title")}
      </div>
      <p className="mt-0 mb-3 text-[12.5px] leading-relaxed text-ink-3">{t("sudo_why")}</p>
      <form onSubmit={reveal} className="flex flex-wrap items-end gap-3">
        <div className="min-w-[200px] flex-1">
          <Input type="password" autoComplete="current-password" value={pw}
                 onChange={(e) => setPw(e.target.value)}
                 placeholder={bi("كلمة مرورك", "Your password")} />
        </div>
        <Btn icon="key" type="submit" disabled={state.busy || !pw}>{t("dev_reveal")}</Btn>
      </form>
      {state.err && <p className="mt-2 mb-0 text-[12.5px] text-red-300">{state.err}</p>}
    </div>
  );
}

function Credentials() {
  return (
    <Card className="mb-6">
      <SectionTitle icon="key">{t("dev_creds")}</SectionTitle>
      <div className="divide-y divide-ink-9/10">
        <Row label="WHATSAPP_WABA_ID" value={P.wabaId} />
        <Row label="WHATSAPP_PHONE_NUMBER_ID" value={P.phoneId} />
      </div>
      {P.hasToken ? <Secrets /> : (
        <p className="mt-3 mb-0 text-[12.5px] text-ink-3">
          {bi("الرقم لسه مش مربوط بالكامل.", "This number isn't fully connected yet.")}
        </p>
      )}
    </Card>
  );
}

/* ---------------------------------------- الإرسال: بنية Cloud API حرفياً */
function Sending() {
  const url = String(P.apiBase || "").replace("__PID__", P.phoneId || "PHONE_NUMBER_ID");
  const snippet =
    `curl -X POST '${url}' \\\n` +
    `  -H 'Authorization: Bearer YOUR_BOTYALLA_KEY' \\\n` +
    `  -H 'Content-Type: application/json' \\\n` +
    `  -d '{"messaging_product":"whatsapp","to":"2010xxxxxxx",\n` +
    `       "type":"text","text":{"body":"Hello"}}'`;
  return (
    <Card className="mb-6">
      <SectionTitle icon="bolt">{t("dev_send_title")}</SectionTitle>
      <p className="mt-0 mb-3 text-[13px] leading-relaxed text-ink-3">{t("dev_send_hint")}</p>
      <div className="relative">
        <pre dir="ltr" className="overflow-x-auto rounded-2xl bg-ink-9/5 p-4 text-[12px]
                                  leading-relaxed text-ink-1"><code>{snippet}</code></pre>
        <div className="mt-2 flex justify-end"><Copy value={snippet} /></div>
      </div>
    </Card>
  );
}

/* ---------------------------------------- المفاتيح: تُعرض مرة واحدة */
function Keys() {
  const keys = P.keys || [];
  return (
    <Card className="mb-6">
      <SectionTitle icon="key">{t("dev_keys")}</SectionTitle>

      {P.newKey && (
        <div className="mb-4 rounded-2xl bg-au-cyan/10 p-4
                        shadow-[inset_0_0_0_1px_rgb(143_233_255/0.35)]">
          <div className="mb-2 text-[13px] font-bold text-ink-1">{t("dev_key_once")}</div>
          <div className="flex flex-wrap items-center gap-2">
            <code dir="ltr" className="min-w-[240px] flex-1 select-all overflow-x-auto rounded-xl
                                       bg-ink-9/10 px-3 py-2 text-[12.5px] text-ink-1">
              {P.newKey}
            </code>
            <Copy value={P.newKey} sm={false} />
          </div>
        </div>
      )}

      <Form action={P.keyUrl}>
        <div className="flex flex-wrap items-end gap-3">
          <div className="min-w-[200px] flex-1">
            <Field label={t("dev_key_name")}>
              <Input name="name" autoComplete="off"
                     placeholder={bi("مثلاً: خادم الشركة", "e.g. company server")} />
            </Field>
          </div>
          <div className="min-w-[180px]">
            <Field label={bi("النطاق", "Scope")}>
              <Select name="scope" defaultValue="bot">
                <option value="bot">{t("dev_key_scope")}</option>
                <option value="all">{bi("كل بوتات الحساب", "All bots in the account")}</option>
              </Select>
            </Field>
          </div>
          <Btn icon="plus" type="submit">{t("dev_key_new")}</Btn>
        </div>
      </Form>

      {!keys.length ? (
        <p className="mt-4 mb-0 text-[12.5px] text-ink-3">{t("dev_key_none")}</p>
      ) : (
        <div className="mt-4 divide-y divide-ink-9/10">
          {keys.map((k) => (
            <div key={k.id} className="flex flex-wrap items-center gap-3 py-3">
              <div className="min-w-[180px] flex-1">
                <div className="text-[13.5px] font-semibold text-ink-1">
                  {k.name || bi("بلا اسم", "Unnamed")}
                </div>
                <code dir="ltr" className="text-[12px] text-ink-3">{k.prefix}…</code>
              </div>
              <Pill tone="mute">{k.bot_name || bi("كل البوتات", "All bots")}</Pill>
              <div className="text-[12px] text-ink-3">
                {t("dev_key_used")}: {when(k.last_used_at)}
              </div>
              <Form action={`/bot/${P.bot.id}/keys/${k.id}/revoke`}
                    confirm={bi("إلغاء المفتاح ده؟ أي خادم بيستخدمه هيقف فوراً.",
                                "Revoke this key? Any server using it stops immediately.")}>
                <Btn sm variant="red" icon="trash" type="submit">{t("dev_revoke")}</Btn>
              </Form>
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}

/* ---------------------------------------- الاستقبال: تمرير الوارد للشريك */
function Relay() {
  return (
    <Card>
      <SectionTitle icon="inbox">{t("dev_relay")}</SectionTitle>
      <p className="mt-0 mb-1 text-[13px] leading-relaxed text-ink-3">{t("dev_relay_hint")}</p>
      <p className="mt-0 mb-4 text-[12.5px] leading-relaxed text-ink-3">
        <Icon name="shield" size={13} className="me-1 inline align-[-2px] text-au-cyan" />
        {t("dev_relay_why")}
      </p>
      <Form action={P.relaySaveUrl}>
        <div className="flex flex-wrap items-end gap-3">
          <div className="min-w-[240px] flex-1">
            <Field label="Webhook URL" hint={t("dev_relay_verify")}>
              <Input name="relay_url" type="url" dir="ltr" autoComplete="off"
                     defaultValue={P.relayUrl || ""}
                     placeholder="https://your-server.com/webhooks/whatsapp" />
            </Field>
          </div>
          <Btn icon="check" type="submit">{t("dev_save")}</Btn>
        </div>
      </Form>
      {P.hasRelaySecret && (
        <Form action={P.relaySaveUrl} className="mt-3"
              confirm={bi("تغيير السرّ هيوقف التحقق على خادمك لحد ما تحدّثه. تمام؟",
                          "Rotating the secret breaks verification on your server until you update it. OK?")}>
          <input type="hidden" name="relay_url" value={P.relayUrl || ""} />
          <input type="hidden" name="rotate" value="1" />
          <Btn sm variant="ghost" icon="refresh" type="submit">{t("dev_relay_rotate")}</Btn>
        </Form>
      )}
    </Card>
  );
}

export default function Developer() {
  if (!P.isWa) {
    return (
      <>
        <PageHead icon="key" title={t("dev_title")} sub={t("dev_intro")} />
        <Empty icon="key" title={t("dev_not_wa")} text={t("dev_intro")} />
      </>
    );
  }
  return (
    <>
      <PageHead icon="key" title={t("dev_title")} sub={t("dev_intro")} />
      <Credentials />
      <Sending />
      <Keys />
      <Relay />
    </>
  );
}
