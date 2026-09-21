import { useState } from "react";
import {
  BY, P, t, bi, Icon, Card, Btn, Field, Input, Select, Textarea, Form, Grid, Stat,
  Pill, Empty, PageHead, SectionTitle, Table, Tr, Td, num, fmtDate, daysLeft, Avatar,
} from "../kit.jsx";
import { UsernameField, PasswordField, PhoneField, EntityPicker, splitPhone, entityLabel,
         GoogleG, FacebookF } from "../auth.jsx";
import VipCall from "../../VipCall.jsx";

/* ------------------------------------------------- تذاكر الدعم (مشتركة مع الأدمن) */
export const TICKET_KIND = {
  support:   ["settings",  "دعم فني",   "Support"],
  complaint: ["megaphone", "شكوى",      "Complaint"],
  payment:   ["card",      "مشكلة دفع", "Payment issue"],
  other:     ["chat",      "أخرى",      "Other"],
  // يُفتح من «سيبها علينا» في خطوة واتساب وحدها — لا يظهر ضمن أنواع نموذج الدعم
  wa_setup:  ["phone",     "ربط واتساب", "WhatsApp setup"],
  // يُفتح من «احجز مكالمة» في كارت باقة راحة البال وحده
  vip_call:  ["crown",     "مكالمة راحة البال", "Peace of Mind call"],
};
const FORM_KINDS = new Set(["support", "complaint", "payment", "other"]);   // ما يختاره العميل في نموذج الدعم
const TICKET_TONE = { open: "warn", answered: "on", closed: "mute" };
const ticketLabel = (s) => ({ open: bi("مفتوحة", "Open"), answered: bi("اتردّ عليها", "Answered"),
                              closed: bi("مقفولة", "Closed") }[s] || s);

export function TicketHead({ tk, who = false }) {
  const k = TICKET_KIND[tk.kind] || TICKET_KIND.other;
  return (
    <div className="mb-4 flex flex-wrap items-center gap-2">
      <span className="tnum text-[12px] font-bold text-ink-3">#T{tk.id}</span>
      <b className="text-[15px] text-ink">{tk.subject}</b>
      <Pill tone="mute"><Icon name={k[0]} size={12} className="me-1 align-[-2px]" />{bi(k[1], k[2])}</Pill>
      <Pill tone={TICKET_TONE[tk.status] || "mute"}>{ticketLabel(tk.status)}</Pill>
      {who && (
        <span className="text-[12.5px] text-ink-3">
          <Icon name="user" size={12} className="me-1 align-[-2px]" />{tk.username}
        </span>
      )}
      <span className="ms-auto tnum text-[12px] text-ink-3">{fmtDate(tk.updated_at)}</span>
    </div>
  );
}

/* الرسائل كفقاعات: رسائلك على جهة، والطرف الآخر على الجهة المقابلة */
export function TicketThread({ tk, staffView = false }) {
  return (
    <div className="flex flex-col gap-2.5">
      {(tk.msgs || []).map((m) => {
        const mine = staffView ? m.sender === "staff" : m.sender === "user";
        return (
          <div key={m.id}
               className={`max-w-[85%] whitespace-pre-wrap rounded-2xl px-4 py-2.5 text-[13.5px] leading-relaxed
                           shadow-[inset_0_0_0_1px_rgb(255_255_255/0.07)]
                           ${mine ? "self-end bg-au-cyan/[0.12] text-ink" : "self-start bg-white/[0.05] text-ink-2"}`}>
            <div className="mb-1 flex flex-wrap items-center gap-1.5 text-[11px] font-bold text-ink-3">
              <Icon name={m.sender === "staff" ? "shield" : "user"} size={12} />
              {m.sender === "staff" ? bi("فريق BotYalla", "BotYalla team") : (tk.username || bi("العميل", "Customer"))}
              {m.via === "telegram" && <span>· Telegram</span>}
              <span className="tnum">· {fmtDate(m.created_at)}</span>
            </div>
            {m.body}
          </div>
        );
      })}
    </div>
  );
}

function ContactButtons({ plat }) {
  if (!plat.support_email && !plat.support_whatsapp && !plat.support_telegram) return null;
  return (
    <Card>
      <SectionTitle icon="phone">{t("or_contact_now")}</SectionTitle>
      <div className="flex flex-wrap gap-3">
        {plat.support_email && (
          <Btn variant="ghost" icon="inbox" target="_blank" rel="noopener"
               href={`mailto:${plat.support_email}`}>{t("contact_email")}</Btn>
        )}
        {plat.support_whatsapp && (
          <Btn variant="green" icon="phone" target="_blank" rel="noopener"
               href={`https://wa.me/${plat.support_whatsapp}`}>{t("contact_whatsapp")}</Btn>
        )}
        {plat.support_telegram && (
          <Btn variant="ghost" icon="link" target="_blank" rel="noopener"
               href={`https://t.me/${plat.support_telegram}`}>{t("contact_telegram")}</Btn>
        )}
      </div>
    </Card>
  );
}

/* --------------------------------------------------------- الدعم والشكاوى */
export function Support() {
  const { tickets = [], plat = {} } = P;
  const [kind, setKind] = useState("support");
  return (
    <>
      <PageHead icon="help" title={t("nav_support")}
        sub={bi("اكتب مشكلتك أو شكوتك — بتوصل لفريقنا فوراً، والرد بيظهر هنا.",
                "Tell us what's wrong — it reaches our team instantly, and the reply shows up here.")} />

      <Card className="mb-6">
        <Form action="">
          <div className="mb-4 flex flex-wrap gap-2" role="group" aria-label={bi("نوع الرسالة", "Message type")}>
            {Object.entries(TICKET_KIND).filter(([k]) => FORM_KINDS.has(k)).map(([k, [ic, ar, en]]) => (
              <button key={k} type="button" onClick={() => setKind(k)} aria-pressed={kind === k}
                className={`inline-flex items-center gap-1.5 rounded-xl px-3.5 py-2 text-[13px] font-bold transition
                  ${kind === k ? "bg-au-cyan/15 text-ink shadow-[inset_0_0_0_1px_rgb(143_233_255/0.45)]"
                               : "text-ink-3 shadow-[inset_0_0_0_1px_rgb(255_255_255/0.1)] hover:text-ink"}`}>
                <Icon name={ic} size={15} />{bi(ar, en)}
              </button>
            ))}
          </div>
          <input type="hidden" name="kind" value={kind} />
          <Field label={bi("العنوان", "Subject")}>
            <Input name="subject" maxLength={120}
                   placeholder={bi("مثال: البوت مش بيرد على العملاء", "e.g. My bot isn't replying")} />
          </Field>
          <div className="mt-4">
            <Field label={bi("التفاصيل", "Details")}>
              <Textarea name="body" required minLength={10} maxLength={3000} className="min-h-[130px]"
                placeholder={kind === "payment"
                  ? bi("رقم الدفعة، المبلغ، وسيلة الدفع، واللي حصل…", "Payment #, amount, method, and what happened…")
                  : bi("اشرح اللي حصل بالتفصيل…", "Describe what happened…")} />
            </Field>
          </div>
          <div className="mt-5"><Btn icon="chat" type="submit">{bi("ابعت", "Send")}</Btn></div>
        </Form>
      </Card>

      <SectionTitle icon="inbox">{bi("رسائلك", "Your tickets")}</SectionTitle>
      {tickets.length ? tickets.map((tk) => (
        <Card key={tk.id} id={`t${tk.id}`} className="mb-4">
          <TicketHead tk={tk} />
          <TicketThread tk={tk} />
          <Form action={`/support/${tk.id}/reply`} className="mt-4 flex flex-col gap-2 sm:flex-row sm:items-end">
            <Textarea name="body" required minLength={2} maxLength={3000} className="min-h-[52px] flex-1"
              placeholder={tk.status === "closed"
                ? bi("اكتب لو المشكلة رجعت — التذكرة هتتفتح تاني", "Write if it's back — the ticket reopens")
                : bi("اكتب ردّك…", "Write a reply…")} />
            <Btn sm icon="chat" type="submit">{bi("رد", "Reply")}</Btn>
          </Form>
        </Card>
      )) : <Card className="mb-6"><Empty icon="chat" title={bi("مفيش رسائل لسه", "No tickets yet")} /></Card>}

      <div className="mt-6"><ContactButtons plat={plat} /></div>
    </>
  );
}

/* ------------------------------------------------------------- حسابي
   ملف شخصي أعلى الصفحة (الهوية + التحقق + اكتمال الحساب)، ثم عمودان بمسافات ثابتة:
   النماذج (الدخول والأمان · بيانات النشاط) والحالة (التحقق · طرق الدخول · التنبيهات ·
   البريد) — ويصيران عموداً واحداً على الشاشات الأصغر. */
const ROW = "flex flex-wrap items-center gap-3 rounded-xl bg-white/[0.03] px-3.5 py-3 " +
            "shadow-[inset_0_0_0_1px_rgb(255_255_255/0.07)]";
const NOTE = "m-0 text-[12.5px] leading-relaxed text-ink-3";

/* الصورة الشخصية / اللوجو: الملف يُرسل فور اختياره، والخادم يعيد رسمه مربعاً نظيفاً (Pillow) */
function AvatarUpload({ name, entity }) {
  const src = BY.user.avatar;
  const biz = entity === "company" || entity === "institution";
  const hint = biz ? bi("ارفع لوجو شركتك", "Upload your company logo") : bi("ارفع صورتك الشخصية", "Upload your photo");
  return (
    <div className="flex shrink-0 flex-col items-center gap-1.5">
      <Form action="/account/avatar" encType="multipart/form-data" className="group relative">
        <label className="relative block cursor-pointer" title={`${hint} — JPG · PNG · WebP (3MB)`}>
          <Avatar src={src} name={name} size={80}
                  className="!rounded-2xl shadow-[0_12px_30px_-12px_rgb(124_108_246/0.9)] transition-[filter] group-hover:brightness-90" />
          <span className="absolute -bottom-1.5 -end-1.5 grid size-8 place-items-center rounded-full bg-[#0B1020] text-au-cyan
                           shadow-[0_0_0_2px_rgb(124_108_246/0.6)] transition-transform duration-300 group-hover:scale-110">
            <Icon name="camera" size={15} />
          </span>
          <input type="file" name="avatar" accept="image/png,image/jpeg,image/webp" className="sr-only"
                 aria-label={hint} onChange={(e) => e.target.files?.length && e.target.form.requestSubmit()} />
        </label>
      </Form>
      {src ? (
        <Form action="/account/avatar/remove" confirm={bi("حذف الصورة؟", "Remove the picture?")}>
          <button type="submit" className="cursor-pointer border-0 bg-transparent p-0 text-[11.5px] text-ink-3 hover:text-red-300">
            {bi("حذف الصورة", "Remove")}
          </button>
        </Form>
      ) : <span className="text-[11px] text-ink-3">{biz ? bi("لوجو الشركة", "Company logo") : bi("صورتك", "Your photo")}</span>}
    </div>
  );
}

function VerifyBadge({ ok }) {
  return ok ? <Pill tone="on" dot>{bi("مؤكَّد", "Verified")}</Pill>
            : <Pill tone="warn">{bi("غير مؤكَّد", "Not verified")}</Pill>;
}

export function Account() {
  const me = P.me || {};
  const [link, setLink] = useState(null);
  const [err, setErr] = useState(null);
  const [phoneLink, setPhoneLink] = useState(null);
  const [phoneErr, setPhoneErr] = useState(null);
  const [changePw, setChangePw] = useState(false);
  const [pcc, pnum] = splitPhone(me.phone, P.countries);
  const oauthOn = P.oauth && (P.oauth.google || P.oauth.facebook);
  const ids = P.identities || [];
  const lastMethod = P.pwSet === false && ids.length <= 1;   // آخر طريقة دخول — لا تُفك

  /* اكتمال الحساب: كل خطوة ناقصة رابط لمكانها في الصفحة */
  const steps = [
    [!!me.email_verified_at, bi("أكّد بريدك", "Verify your email"), "#verify"],
    [!!me.phone, bi("أضف رقم موبايلك", "Add your mobile"), "#business"],
    [!!me.phone_verified_at, bi("أكّد رقمك", "Verify your number"), "#verify"],
    [!!(me.entity_type && me.age), bi("أكمل بيانات النشاط", "Complete business details"), "#business"],
    [!!P.tgLinked, bi("اربط تليجرام للتنبيهات", "Link Telegram alerts"), "#alerts"],
  ];
  const pct = Math.round((steps.filter((s) => s[0]).length / steps.length) * 100);

  /* تأكيد الهاتف مجاناً: رابط لبوت المنصة، والعميل يضغط «شارك رقمي» */
  async function verifyPhone() {
    setPhoneErr(null);
    try {
      const r = await fetch("/account/verify-phone", { method: "POST", headers: { "X-CSRF-Token": BY.csrf } });
      const d = await r.json();
      if (d.ok) setPhoneLink(d.link); else setPhoneErr(d.error);
    } catch { setPhoneErr(bi("تعذّر الاتصال بالخادم.", "Couldn't reach the server.")); }
  }

  async function linkTelegram() {
    setErr(null);
    try {
      const r = await fetch("/account/link-telegram", {
        method: "POST", headers: { "X-CSRF-Token": BY.csrf },
      });
      const d = await r.json();
      if (d.ok) setLink(d.link); else setErr(d.error);
    } catch { setErr(null); }
  }

  return (
    <>
      <PageHead icon="settings" title={t("account_title")}
        sub={bi("بياناتك، وأمان حسابك، وطرق وصولنا ليك — في مكان واحد.",
                "Your details, account security and how we reach you — in one place.")} />

      {/* ------------------------------------------------ الملف الشخصي */}
      <Card className="mb-5">
        <div className="flex flex-col gap-6 lg:flex-row lg:items-center">
          <div className="flex min-w-0 flex-1 items-center gap-4">
            <AvatarUpload name={me.username} entity={me.entity_type} />
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <h2 className="m-0 truncate text-[21px] font-extrabold tracking-tight text-ink" dir="auto">{me.username}</h2>
                <Pill tone="mute"><Icon name="shield" size={12} />{t("role_" + (me.role || "user"))}</Pill>
                {me.entity_type && <Pill tone="mute">{entityLabel(me.entity_type)}</Pill>}
              </div>
              <div className="mt-2 flex flex-wrap gap-x-5 gap-y-1.5 text-[13px] text-ink-3">
                <span className="inline-flex min-w-0 items-center gap-1.5">
                  <Icon name="mail" size={14} />
                  <span className="truncate" dir="ltr">{me.email || bi("بلا بريد", "No email")}</span>
                  {me.email_verified_at && <Icon name="check" size={13} className="text-au-teal" />}
                </span>
                {me.phone && (
                  <span className="inline-flex items-center gap-1.5">
                    <Icon name="phone" size={14} /><span dir="ltr">{me.phone}</span>
                    {me.phone_verified_at && <Icon name="check" size={13} className="text-au-teal" />}
                  </span>
                )}
                {me.created_at && (
                  <span className="inline-flex items-center gap-1.5">
                    <Icon name="clock" size={14} />{bi("عضو منذ", "Member since")} <span className="tnum">{fmtDate(me.created_at)}</span>
                  </span>
                )}
              </div>
            </div>
          </div>

          <div className="w-full lg:w-[320px]">
            <div className="mb-2 flex items-baseline justify-between gap-3 text-[13px]">
              <span className="font-bold text-ink-2">{bi("اكتمال الحساب", "Account completion")}</span>
              <span className={`tnum text-[16px] font-extrabold ${pct === 100 ? "text-au-teal" : "text-ink"}`}>{pct}%</span>
            </div>
            <div className="h-2 overflow-hidden rounded-full bg-white/[0.08]">
              <div className="h-full rounded-full bg-[linear-gradient(90deg,#8FE9FF,#B9AFFF)] transition-[width] duration-700"
                   style={{ width: `${pct}%` }} />
            </div>
            {pct < 100 ? (
              <div className="mt-3 flex flex-wrap gap-1.5">
                {steps.filter((s) => !s[0]).map(([, label, href]) => (
                  <a key={label} href={href}
                     className="rounded-full bg-white/[0.05] px-2.5 py-1 text-[11.5px] font-bold text-ink-2 no-underline
                                transition-colors hover:bg-au-violet/25 hover:text-ink">+ {label}</a>
                ))}
              </div>
            ) : (
              <p className="mb-0 mt-3 text-[12.5px] font-bold text-au-teal">
                {bi("حسابك مكتمل وموثَّق ✓", "Your account is complete and verified ✓")}
              </p>
            )}
          </div>
        </div>
      </Card>

      <div className="grid items-start gap-5 xl:grid-cols-[minmax(0,1.25fr)_minmax(0,1fr)]">
        {/* ============================================ العمود الأول: النماذج */}
        <div className="flex min-w-0 flex-col gap-5">
          <Card id="login" className="scroll-mt-24">
            <SectionTitle icon="key">{bi("بيانات الدخول والأمان", "Sign-in & security")}</SectionTitle>
            <Form action="">
              <div className="grid gap-5 md:grid-cols-2">
                <UsernameField defaultValue={me.username} current={me.username} />
                <Field label={
                  <span className="flex items-center justify-between gap-2">
                    {t("email")}{me.email && <VerifyBadge ok={!!me.email_verified_at} />}
                  </span>}
                  hint={me.email ? bi("تغيير البريد يرسل كود تأكيد للبريد الجديد.", "Changing it sends a code to the new address.")
                                 : t("email_hint")}>
                  <Input type="email" name="email" defaultValue={me.email || ""} autoComplete="email" dir="ltr" />
                </Field>
              </div>

              <div className="mt-5 rounded-2xl bg-white/[0.025] p-4 shadow-[inset_0_0_0_1px_rgb(255_255_255/0.07)]">
                {changePw ? (
                  <>
                    <PasswordField name="new_password" confirmName="new_password2" label={t("new_password")} optional
                                   username={me.username} email={me.email || ""} />
                    <button type="button" onClick={() => setChangePw(false)}
                      className="mt-4 cursor-pointer border-0 bg-transparent p-0 text-[12.5px] text-ink-3 hover:text-ink">
                      {bi("إلغاء تغيير كلمة المرور", "Cancel password change")}
                    </button>
                  </>
                ) : (
                  <div className="flex flex-wrap items-center gap-3">
                    <span className="grid size-10 shrink-0 place-items-center rounded-xl bg-au-violet/15 text-au-cyan">
                      <Icon name="lock" size={18} />
                    </span>
                    <div className="min-w-0 flex-1">
                      <b className="block text-[14px] text-ink">{t("password")}</b>
                      <span className="text-[12.5px] text-ink-3">
                        {P.pwSet === false
                          ? bi("حسابك مسجّل بجوجل/فيسبوك ولسه ملوش كلمة مرور.", "You signed up with Google/Facebook and have no password yet.")
                          : bi("8+ أحرف فيها حرف كبير وصغير ورقم ورمز.", "8+ characters with upper, lower, a number and a symbol.")}
                      </span>
                    </div>
                    {P.pwSet === false
                      ? <Btn sm variant="ghost" icon="key" href={BY.urls.forgot}>{bi("اضبط كلمة مرور", "Set a password")}</Btn>
                      : <Btn sm variant="ghost" icon="key" type="button" onClick={() => setChangePw(true)}>{bi("تغيير كلمة المرور", "Change password")}</Btn>}
                  </div>
                )}
              </div>

              {P.pwSet === false ? (
                <p className={`${NOTE} mt-4`}>
                  {bi("عشان تعدّل اسم المستخدم أو البريد، اضبط كلمة مرور الأول من ", "To edit your username or email, first set a password via ")}
                  <a href={BY.urls.forgot} className="font-bold text-au-cyan">{t("forgot_link")}</a>.
                </p>
              ) : (
                <div className="mt-5 border-t border-white/10 pt-5">
                  <div className="grid items-end gap-3 sm:grid-cols-[minmax(0,1fr)_auto]">
                    <Field label={t("current_password")}>
                      <Input type="password" name="current_password" required autoComplete="current-password" />
                    </Field>
                    <Btn icon="check" type="submit">{t("update_account")}</Btn>
                  </div>
                  <p className={`${NOTE} mt-2`}>{bi("مطلوبة لتأكيد أي تعديل في البيانات دي.", "Required to confirm any change here.")}</p>
                </div>
              )}
            </Form>
          </Card>

          {/* بيانات النشاط — بلا كلمة مرور: ليست بيانات دخول */}
          <Card id="business" className="scroll-mt-24">
            <SectionTitle icon="user">{bi("بيانات النشاط", "Business details")}</SectionTitle>
            <Form action="/account/profile" className="flex flex-col gap-5">
              <EntityPicker defaultValue={me.entity_type || ""} />
              <div className="grid gap-5 md:grid-cols-[130px_minmax(0,1fr)]">
                <Field label={bi("السن", "Age")}>
                  <Input type="number" name="age" required min="18" max="100" inputMode="numeric" dir="ltr"
                         defaultValue={me.age || ""} />
                </Field>
                <PhoneField cc={pcc} value={pnum}
                            hint={me.phone_verified_at ? bi("تغيير الرقم يلغي تأكيده.", "Changing the number removes its verification.") : null} />
              </div>
              <div><Btn icon="check" type="submit">{t("save")}</Btn></div>
            </Form>
          </Card>
        </div>

        {/* ============================================ العمود الثاني: الحالة والتواصل */}
        <div className="flex min-w-0 flex-col gap-5">
          <Card id="verify" className="scroll-mt-24">
            <SectionTitle icon="shield">{bi("التحقق من الحساب", "Account verification")}</SectionTitle>
            <div className="flex flex-col gap-2.5">
              <div className={ROW}>
                <Icon name="mail" size={17} className="text-au-cyan" />
                <span className="min-w-0 flex-1">
                  <b className="block text-[13px] text-ink">{t("email")}</b>
                  <span className="block truncate text-[12.5px] text-ink-3" dir="ltr">{me.email || "—"}</span>
                </span>
                {me.email && (me.email_verified_at
                  ? <VerifyBadge ok />
                  : <Form action="/verify-email/resend" className="inline">
                      <Btn sm variant="ghost" icon="mail" type="submit">{bi("أكّد البريد", "Verify")}</Btn>
                    </Form>)}
              </div>
              <div className={ROW}>
                <Icon name="phone" size={17} className="text-au-cyan" />
                <span className="min-w-0 flex-1">
                  <b className="block text-[13px] text-ink">{bi("رقم الموبايل", "Mobile number")}</b>
                  <span className="block truncate text-[12.5px] text-ink-3" dir="ltr">{me.phone || "—"}</span>
                </span>
                {!me.phone ? (
                  <Btn sm variant="ghost" icon="plus" href="#business">{bi("أضف رقمك", "Add number")}</Btn>
                ) : me.phone_verified_at ? <VerifyBadge ok /> : phoneLink ? (
                  <Btn sm variant="green" icon="play" href={phoneLink} target="_blank" rel="noopener">{bi("افتح تليجرام", "Open Telegram")}</Btn>
                ) : (
                  <Btn sm variant="ghost" icon="phone" type="button" onClick={verifyPhone} disabled={!P.hasPlatformBot}>
                    {bi("أكّد عبر تليجرام", "Verify via Telegram")}
                  </Btn>
                )}
              </div>
            </div>
            {phoneErr && <p className="mb-0 mt-3 text-[12.5px] text-red-300">{phoneErr}</p>}
            {phoneLink && !me.phone_verified_at && (
              <p className="mb-0 mt-3 text-[12.5px] leading-relaxed text-au-teal">
                {bi("في البوت اضغط «شارك رقمي» — وبعدها حدّث الصفحة.", "In the bot tap “Share my number”, then refresh this page.")}
              </p>
            )}
            <p className={`${NOTE} mt-3`}>
              {bi("تأكيد الهاتف مجاني: بتضغط «شارك رقمي» في بوت المنصة، وتليجرام بيبعت رقم حسابك نفسه — لازم يطابق الرقم المسجّل.",
                  "Phone verification is free: tap “Share my number” in the platform bot — Telegram sends your own number, which must match the one here.")}
            </p>
          </Card>

          {oauthOn && (
            <Card id="signin" className="scroll-mt-24">
              <SectionTitle icon="link">{bi("طرق الدخول", "Sign-in methods")}</SectionTitle>
              <div className="flex flex-col gap-2.5">
                {["google", "facebook"].filter((p) => P.oauth[p]).map((p) => {
                  const name = p === "google" ? "Google" : "Facebook";
                  const linked = ids.includes(p);
                  return (
                    <div key={p} className={ROW}>
                      <span className={`grid size-9 shrink-0 place-items-center rounded-xl ${p === "google" ? "bg-white" : "bg-[#1877F2]"}`}>
                        {p === "google" ? <GoogleG /> : <FacebookF />}
                      </span>
                      <span className="min-w-0 flex-1">
                        <b className="block text-[13.5px] text-ink">{name}</b>
                        <span className="text-[12px] text-ink-3">
                          {linked ? bi("تقدر تدخل بيه بضغطة", "One-tap sign-in is on") : bi("غير مربوط", "Not linked")}
                        </span>
                      </span>
                      {linked ? (
                        <Form action={`/account/unlink/${p}`} className="inline"
                              confirm={bi(`فك ربط ${name}؟ مش هتقدر تدخل بيه لحد ما تربطه تاني.`,
                                          `Unlink ${name}? You won't be able to sign in with it until you link it again.`)}>
                          <Btn sm variant="ghost" icon="close" type="submit" disabled={lastMethod}>{bi("فك الربط", "Unlink")}</Btn>
                        </Form>
                      ) : <Btn sm variant="ghost" icon="link" href={`/auth/${p}?link=1`}>{bi("اربط", "Link")}</Btn>}
                    </div>
                  );
                })}
              </div>
              {lastMethod && ids.length > 0 && (
                <p className="mb-0 mt-3 text-[12.5px] leading-relaxed text-amber-200">
                  {bi("ده طريق الدخول الوحيد لحسابك — اضبط كلمة مرور الأول عشان تقدر تفك الربط.",
                      "This is your only way to sign in — set a password first to unlink it.")}
                </p>
              )}
            </Card>
          )}

          {/* قناة تنبيهات الاشتراك — بدونها لا يعلم العميل بانتهاء اشتراكه */}
          <Card id="alerts" className="scroll-mt-24">
            <SectionTitle icon="bot"
              extra={P.tgLinked ? <Pill tone="on" dot>{t("tg_link_ok")}</Pill>
                   : P.tgFallback ? <Pill tone="warn">{t("aff_active")}</Pill>
                   : <Pill tone="off">{t("tg_not_synced")}</Pill>}>
              {t("tg_link_title")}
            </SectionTitle>
            <p className={`${NOTE} mb-4`}>
              {P.tgLinked ? t("tg_link_desc") : P.tgFallback ? t("tg_link_via_bot") : t("tg_link_none")}
            </p>
            {!P.tgLinked && (
              link ? (
                <Btn variant="green" icon="play" href={link} target="_blank" rel="noopener">{t("tg_link_open")}</Btn>
              ) : (
                <Btn icon="link" type="button" onClick={linkTelegram} disabled={!P.hasPlatformBot}>{t("tg_link_btn")}</Btn>
              )
            )}
            {!P.hasPlatformBot && <p className={`${NOTE} mt-3`}>{t("tg_link_no_bot")}</p>}
            {err && <p className="mb-0 mt-3 text-[13px] font-bold text-red-300">{err}</p>}
          </Card>

          {/* أخبار وعروض بالبريد — موافقة صريحة، ورسائل الحساب المهمة لا تتأثر */}
          <Card id="news" className="scroll-mt-24">
            <SectionTitle icon="mail"
              extra={P.emailNews ? <Pill tone="on" dot>{bi("مفعّلة", "On")}</Pill> : <Pill tone="mute">{bi("متوقفة", "Off")}</Pill>}>
              {bi("أخبار وعروض بالبريد", "News & offers by email")}
            </SectionTitle>
            <p className={`${NOTE} mb-4`}>
              {bi("ميزات جديدة وعروض خصم ونصائح لبوتك — مرة أو اثنتين في الشهر على الأكثر. رسائل حسابك المهمة (الإيصالات، استرجاع كلمة المرور، تذكير الاشتراك) تصلك في كل الأحوال.",
                  "New features, discounts and tips for your bot — once or twice a month at most. Important account emails (receipts, password reset, renewal reminders) reach you either way.")}
            </p>
            <Form action="/account/email-prefs">
              <input type="hidden" name="email_news" value={P.emailNews ? "0" : "1"} />
              <Btn variant={P.emailNews ? "ghost" : "primary"} icon="mail" type="submit" disabled={!me.email && !P.emailNews}>
                {P.emailNews ? bi("أوقف الأخبار والعروض", "Turn off news & offers") : bi("فعّل الأخبار والعروض", "Turn on news & offers")}
              </Btn>
            </Form>
            {!me.email && <p className={`${NOTE} mt-2`}>{bi("أضف بريدك في «بيانات الدخول» أولاً.", "Add your email under “Sign-in” first.")}</p>}
          </Card>
        </div>
      </div>
    </>
  );
}

/* ---------------------------------------------------------- إعدادات الـ AI */
/* مزوّدون مجانيون في سلسلة واحدة: الأساسي أولاً ثم كل من له مفتاح — لو نفدت حصة مزوّد
   ينتقل الرد للتالي تلقائياً. «اختبر المفاتيح» يكتشف نماذج كل مزوّد المتاحة الآن ويحفظها. */
const AI_FREE = {
  groq:       { url: "https://console.groq.com/keys", host: "console.groq.com",
                note: ["مجاني بلا بطاقة · أسرع مزوّد (ثانية تقريباً) · حدود في الدقيقة", "Free, no card · fastest (~1s) · per-minute limits"] },
  cerebras:   { url: "https://cloud.cerebras.ai/platform", host: "cloud.cerebras.ai",
                note: ["مجاني بلا بطاقة · سريع جداً · حصة يومية كبيرة", "Free, no card · very fast · large daily quota"] },
  gemini:     { url: "https://aistudio.google.com/apikey", host: "aistudio.google.com",
                note: ["طبقة مجانية بحدود في الدقيقة", "Free tier with per-minute limits"] },
  openrouter: { url: "https://openrouter.ai/keys", host: "openrouter.ai",
                note: ["نماذج :free مجانية (DeepSeek · Gemma · Nemotron) · حد يومي", "Free :free models (DeepSeek · Gemma · Nemotron) · daily cap"] },
  nvidia:     { url: "https://build.nvidia.com/settings/api-keys", host: "build.nvidia.com",
                note: ["رصيد مجاني للتجربة · DeepSeek · Kimi · GLM", "Free trial credits · DeepSeek · Kimi · GLM"] },
};

/* سبب مفهوم لأي رد غير JSON من الخادم — بدل «تعذّر الاتصال» الصامتة */
function httpWhy(status) {
  if (status === 504 || status === 502) return bi("انتهت مهلة الخادم (nginx) — المزوّد بطيء أو لا يرد", "Server timeout (nginx) — the provider is slow or not responding");
  if (status === 400) return bi("رُفض الطلب (رمز الأمان) — حدّث الصفحة وجرّب تاني", "Request rejected (security token) — refresh the page and retry");
  if (status === 401 || status === 403 || status === 302) return bi("الجلسة انتهت — سجّل الدخول تاني", "Session expired — sign in again");
  if (status === 429) return bi("طلبات كتير — استنى دقيقتين", "Too many requests — wait two minutes");
  if (status >= 500) return bi("خطأ في الخادم — راجع سجل السيرفر", "Server error — check the server log");
  return "";
}

async function testOne(provider) {
  let r;
  try {
    r = await fetch("/settings/ai-test", {
      method: "POST", credentials: "same-origin", redirect: "manual",
      headers: { "Content-Type": "application/json", "X-CSRF-Token": BY.csrf },
      body: JSON.stringify({ provider }),
    });
  } catch (e) {
    return { provider, ok: false, msg: bi("مفيش اتصال بالسيرفر: ", "No connection to the server: ") + (e && e.message || "") };
  }
  const status = r.type === "opaqueredirect" ? 302 : r.status;
  let data = null;
  try { data = await r.json(); } catch { /* صفحة خطأ HTML من nginx/Flask */ }
  if (data && data.results && data.results.length) return data.results[0];
  if (data && data.msg) return { provider, ok: false, msg: `HTTP ${status} — ${data.msg}` };
  return { provider, ok: false, msg: `HTTP ${status} — ${httpWhy(status) || bi("رد غير متوقع من الخادم", "Unexpected server response")}` };
}

function AiKeyTest() {
  const provs = (P.aiProviders || []).filter((p) => (P.aiKeys || {})[p.id]);
  const [res, setRes] = useState({});
  const [busy, setBusy] = useState(false);
  const last = P.aiLastError || {};
  const when = (s) => (s ? new Date(s * 1000).toLocaleString() : "");
  const run = async () => {
    setBusy(true);
    setRes(Object.fromEntries(provs.map((p) => [p.id, null])));
    // بالتوازي: كل مزوّد طلب مستقل محدود الزمن — النتائج تظهر أولاً بأول
    await Promise.all(provs.map(async (p) => {
      const r = await testOne(p.id);
      setRes((old) => ({ ...old, [p.id]: r }));
    }));
    setBusy(false);
  };
  return (
    <div className="mt-6 border-t border-white/10 pt-5">
      <Btn variant="ghost" icon="bolt" type="button" onClick={run} disabled={busy || !provs.length}>
        {busy ? bi("جارٍ اختبار المزوّدين…", "Testing providers…") : bi("اختبر المفاتيح المحفوظة", "Test the saved keys")}
      </Btn>
      {!provs.length && (
        <p className="mt-3 mb-0 text-[13px] font-bold text-yellow-200">
          {bi("مفيش مفاتيح محفوظة — حط مفتاح واضغط «حفظ» الأول.", "No saved keys — add a key and press Save first.")}
        </p>
      )}
      {Object.keys(res).length > 0 && (
        <ul className="mt-3 mb-0 flex flex-col gap-2 p-0">
          {provs.filter((p) => p.id in res).map((p) => {
            const r = res[p.id];
            return (
              <li key={p.id} className="list-none rounded-xl bg-white/[0.03] px-3.5 py-2.5 text-[13px] leading-relaxed
                                        shadow-[inset_0_0_0_1px_rgb(255_255_255/0.07)]">
                {!r ? <span className="text-ink-3">⏳ {p.name} — {bi("جارٍ الاختبار…", "testing…")}</span>
                    : <>
                        <b className={r.ok ? "text-au-teal" : "text-red-300"}>{(r.ok ? "✓ " : "✗ ") + p.name}</b>
                        {r.ok ? <span className="text-ink-3"> · {r.model} · {((r.ms || 0) / 1000).toFixed(1)}s</span>
                              : <span dir="auto" className="block break-words text-ink-2">{r.msg}</span>}
                      </>}
              </li>
            );
          })}
        </ul>
      )}
      <p className="mt-3 mb-0 text-[12.5px] leading-relaxed text-ink-3">
        {P.aiLastOk ? bi("آخر رد ناجح: ", "Last successful reply: ") + when(P.aiLastOk) : bi("لا يوجد رد ناجح مسجّل بعد.", "No successful reply recorded yet.")}
        {last.msg && (last.at || 0) > (P.aiLastOk || 0) && (
          <><br /><span className="text-yellow-200">{bi("آخر خطأ: ", "Last error: ") + when(last.at) + " — " + last.msg}</span></>
        )}
      </p>
    </div>
  );
}

export function Settings() {
  const provs = P.aiProviders || [];
  const keys = P.aiKeys || {};
  return (
    <>
      <PageHead icon="sparkles" title={t("ai_settings")} sub={t("ai_settings_sub")} />
      <Card className="mb-6 max-w-[720px]">
        <SectionTitle icon="key">{bi("مزوّدو الذكاء الاصطناعي (مجاناً)", "AI providers (free)")}</SectionTitle>
        <p className="mt-0 mb-5 text-[13px] leading-relaxed text-ink-3">
          {bi("حط مفتاح مجاني من مزوّد واحد أو أكتر. البوت بيبدأ بالأساسي، ولو حصته المجانية خلصت أو اتعطّل بينتقل للي بعده تلقائياً — فكل ما تزوّد مفاتيح، بيبقى أسرع وما يقفش. ننصح بـ Groq أو Cerebras كأساسي (الأسرع).",
              "Add a free key from one or more providers. The bot starts with the primary; if its free quota runs out or it fails, it moves to the next automatically — more keys, faster and never stuck. Groq or Cerebras make the best primary (fastest).")}
        </p>
        <Form action="">
          <Field label={bi("المزوّد الأساسي", "Primary provider")} className="mb-5">
            <Select name="ai_provider" defaultValue={P.aiProvider}>
              {provs.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
            </Select>
          </Field>
          <div className="flex flex-col gap-4">
            {provs.map((p) => {
              const f = AI_FREE[p.id] || {};
              return (
                <Field key={p.id} label={p.name}
                       hint={<>{bi(...(f.note || ["", ""]))} · <a href={f.url} target="_blank" rel="noopener"
                               className="text-au-cyan underline-offset-4 hover:underline">{f.host} ↗</a></>}>
                  <Input name={`ai_key_${p.id}`} defaultValue={keys[p.id] || ""} placeholder={t("paste_key")}
                         autoComplete="off" dir="ltr" />
                </Field>
              );
            })}
          </div>
          <div className="mt-6"><Btn icon="check" type="submit">{t("save")}</Btn></div>
        </Form>
        <AiKeyTest />
      </Card>
    </>
  );
}

/* ---------------------------------------------------------------- الفواتير */
export function Billing() {
  const { sub = {}, pays = [], planName, names = {} } = P;
  const isAdmin = BY.user.role === "admin";
  const dl = daysLeft(sub.expires_at);
  const tone = { pending: "warn", approved: "on", rejected: "off" };
  const label = { pending: t("status_pending"), approved: t("status_approved"), rejected: t("status_rejected") };

  return (
    <>
      <PageHead icon="card" title={t("billing_title")} />

      <Card className="mb-6 flex flex-wrap items-center justify-between gap-5">
        <div>
          <div className="text-[13px] text-ink-3">{t("current_plan")}</div>
          <div className="mt-1.5 flex flex-wrap items-center gap-3 text-[24px] font-extrabold text-ink">
            {isAdmin ? <span className="hue">{t("owner_unlimited")}</span> : (
              <>
                {planName}
                {sub.status === "active"  && <Pill tone="on" dot>{t("status_active")}</Pill>}
                {sub.status === "expired" && <Pill tone="off">{t("status_expired")}</Pill>}
              </>
            )}
          </div>
          {!isAdmin && sub.expires_at && sub.plan !== "free" && (
            <div className="mt-2 flex flex-wrap items-center gap-2 text-[13px] text-ink-3">
              <Icon name="clock" size={13} />
              {t("expires_on")}: <b className="text-ink-2">{fmtDate(sub.expires_at)}</b>
              {sub.status === "active" && (
                <span className={dl <= 5 ? "text-red-300" : "text-au-teal"}>({dl} {t("days_left")})</span>
              )}
              <span>· {t(sub.billing_cycle === "annual" ? "renews_annually" : "renews_monthly")}</span>
            </div>
          )}
        </div>
        <Btn icon="bolt" href={BY.urls.pricing}>{t("nav_pricing")}</Btn>
      </Card>

      <Card>
        <SectionTitle icon="clock">{t("payment_history")}</SectionTitle>
        {pays.length ? (
          <Table head={["#", t("col_plan"), t("col_amount"), t("col_method"), t("col_status")]}>
            {pays.map((x) => (
              <Tr key={x.id}>
                <Td className="tnum">{x.id}</Td>
                <Td>{names[x.plan] || x.plan}</Td>
                <Td className="tnum">{num(x.amount)} {t("egp")}</Td>
                <Td>{x.method}</Td>
                <Td><Pill tone={tone[x.status]}>{label[x.status]}</Pill></Td>
              </Tr>
            ))}
          </Table>
        ) : <Empty icon="card" title={t("no_payments")} />}
      </Card>
    </>
  );
}

/* ----------------------------------------------------------------- الباقات */
export function Pricing() {
  const { plans: all = [], sub = {} } = P;
  const plans = all.filter((p) => !p.by_call);          // «راحة البال» كارت عريض بزرّ مكالمة
  const vip = all.find((p) => p.by_call);
  // المعرّفات هنا لا بد أن تطابق `plans.ORDER` في الخادم — أي معرّف قديم يترك
  // البطاقة بأيقونة افتراضية والشارة معلّقة بلا أن يكسر شيئاً ظاهراً.
  const icons = { free: "bot", merchant: "store", whatsapp: "phone", agency: "crown" };
  const [cycle, setCycle] = useState("annual");         // السنوي افتراضياً — المعادل الشهري ظاهر
  const annual = cycle === "annual";
  const fill = (k, n) => t(k).replace("{n}", n);
  const topSave = plans.reduce((m, p) => Math.max(m, p.annual_saving_pct || 0), 0);

  return (
    <>
      <div className="mb-8 text-center">
        <h1 className="m-0 text-[clamp(26px,4vw,40px)] font-extrabold tracking-tight text-ink">
          {t("pricing_title")}
        </h1>
        <p className="mx-auto mt-3 max-w-[520px] text-[15px] text-ink-3">{t("pricing_sub")}</p>
      </div>

      {/* مبدّل الدورة — عرضٌ فقط: المبلغ المُحصَّل يُحسب في الخادم عند الدفع */}
      <div className="mb-10 flex flex-col items-center gap-2">
        <div role="tablist" aria-label={t("sub_cycle")}
             className="inline-flex rounded-full bg-black/25 p-1 shadow-[inset_0_0_0_1px_rgb(255_255_255/0.1)]">
          {["monthly", "annual"].map((c) => (
            <button key={c} type="button" role="tab" aria-selected={cycle === c}
                    onClick={() => setCycle(c)}
                    className={"rounded-full px-5 py-2 text-[13.5px] font-extrabold transition-colors duration-200 " +
                      (cycle === c
                        ? "bg-[linear-gradient(100deg,#8FE9FF,#B9AFFF)] text-[#07090F]"
                        : "text-ink-3 hover:text-ink-2")}>
              {t(c === "annual" ? "cycle_annual" : "cycle_monthly")}
              {c === "annual" && topSave > 0 && (
                <span className="ms-1.5 rounded-full bg-au-teal px-1.5 py-0.5 text-[10.5px] font-extrabold text-[#04140E]">
                  −{topSave}%
                </span>
              )}
            </button>
          ))}
        </div>
        {topSave > 0 && (
          <span className="text-[12.5px] font-bold text-au-teal">
            {annual ? fill("save_pct", topSave) : t("annual_hint")}
          </span>
        )}
      </div>

      <div className="grid items-start gap-5 md:grid-cols-2 xl:grid-cols-4">
        {plans.map((p) => {
          const current = sub.plan === p.id && sub.status === "active";
          const hot = p.id === "whatsapp";
          const feats = BY.lang === "ar" ? p.features_ar : p.features_en;
          const price = annual ? p.annual_price : p.price;
          const listPrice = annual ? p.annual_list_price : p.list_price;
          const hasDisc = annual ? p.annual_has_discount : p.has_discount;
          return (
            <Card key={p.id} spot
                  className={"!overflow-visible text-center transition-transform duration-500 hover:-translate-y-1 " +
                    (hot ? "shadow-[inset_0_0_0_1px_rgb(124_108_246/0.55),0_30px_70px_-30px_rgb(0_0_0/0.9)]" : "")}>
              {hot && (
                <span className="absolute -top-3 start-1/2 -translate-x-1/2 rounded-full px-4 py-1 text-[11.5px]
                                 font-extrabold text-[#07090F] rtl:translate-x-1/2
                                 bg-[linear-gradient(100deg,#8FE9FF,#B9AFFF)]
                                 shadow-[0_8px_20px_-6px_rgb(124_108_246/0.8)]">
                  {t("most_popular")}
                </span>
              )}
              <Icon name={icons[p.id] || "bot"} size={28} className="mx-auto text-au-cyan" />
              <h2 className="mt-3 mb-3 text-[19px] font-extrabold text-ink">
                {p.name}
              </h2>
              <div className="mb-6">
                {price === 0 ? (
                  <span className="hue text-[22px] font-extrabold">{t("free_forever")}</span>
                ) : (
                  <>
                    {hasDisc && (
                      <div className="mb-1 flex items-center justify-center gap-2">
                        <span className="text-[16px] text-ink-3 line-through">{listPrice}</span>
                        <Pill tone="on">-{Math.round(p.discount_pct)}%</Pill>
                      </div>
                    )}
                    <div className="text-[34px] font-extrabold leading-none text-ink tnum">
                      {num(price)}
                      <span className="text-[15px] font-bold text-ink-3">
                        {t("egp")}{annual ? t("per_year") : t("per_month")}
                      </span>
                    </div>
                    {/* السطر السنوي يُظهر المقابل الشهري حتى تبقى المقارنة عادلة */}
                    <div className="mt-2 min-h-[18px] text-[12.5px] font-bold text-au-teal">
                      {annual && p.annual_saving_pct > 0
                        ? `${fill("save_pct", p.annual_saving_pct)} · ${fill("equiv_per_month", num(p.annual_monthly_equiv))}`
                        : ""}
                    </div>
                  </>
                )}
              </div>
              <ul className="mb-7 flex flex-col gap-2.5 text-start">
                {feats.map((f, i) => (
                  <li key={i} className="flex items-start gap-2.5 text-[14px] text-ink-2">
                    <Icon name="check" size={16} className="mt-0.5 text-au-teal" />{f}
                  </li>
                ))}
              </ul>
              {current ? <Pill tone="on" dot>{t("current_plan")}</Pill>
                : p.id === "free" ? <span className="text-[13px] text-ink-3">{t("free_forever")}</span>
                : <Btn block icon="card" href={`/subscribe/${p.id}?cycle=${cycle}`}>{t("subscribe_btn")}</Btn>}
            </Card>
          );
        })}
      </div>

      {vip && (sub.plan === "vip" && sub.status === "active"
        ? <Card className="mt-6 text-center"><Pill tone="on" dot>{t("current_plan")}: {vip.name_ar && BY.lang === "ar" ? vip.name_ar : vip.name_en}</Pill></Card>
        : <VipCall plan={vip} BY={BY} Icon={Icon} />)}

      <p className="mt-10 flex items-center justify-center gap-2 text-[13px] text-ink-3">
        <Icon name="shield" size={14} />{t("pay_secure_note")}
      </p>
    </>
  );
}

/* ---------------------------------------------------------------- الاشتراك */
export function Subscribe() {
  const { plan = {}, plat = {}, qr, action, planId,
          cycle = "monthly", days = 30, annualSavingPct = 0, carry = null } = P;
  const annual = cycle === "annual";
  const [copied, setCopied] = useState("");
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);
  // التسعيرة الابتدائية من الخادم؛ تُحدَّث عند تطبيق كود
  const [q, setQ] = useState({
    listPrice: plan.list_price ?? plan.price,
    total: plan.price,
    planDiscountPct: plan.discount_pct || 0,
    promoCode: null, promoCut: 0,
  });

  async function check() {
    setBusy(true); setErr(null);
    try {
      const r = await fetch("/api/promo/check", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRF-Token": BY.csrf },
        // الدورة تُرسَل مع الكود: خصم نسبي على اشتراك سنوي ليس هو نفسه على شهري
        body: JSON.stringify({ plan: planId, code, cycle }),
      });
      const d = await r.json();
      if (d.ok) {
        setQ({ listPrice: d.listPrice, total: d.total, planDiscountPct: d.planDiscountPct,
               promoCode: d.promoCode, promoCut: d.promoCut });
        setErr(d.error || null);
      } else {
        // 429 (محاولات كثيرة) وغيرها: أظهر السبب بدل زرّ لا يفعل شيئاً
        setErr(d.error || null);
      }
    } catch { setErr(null); }
    setBusy(false);
  }

  const copy = (v, k) => {
    navigator.clipboard?.writeText(v).then(() => {
      setCopied(k); setTimeout(() => setCopied(""), 1400);
    });
  };
  const CopyRow = ({ v, k }) => (
    <div className="mt-2 flex items-center gap-2">
      <code className="flex-1 overflow-x-auto rounded-lg bg-black/30 px-3 py-2 text-[13px] text-au-cyan
                       shadow-[inset_0_0_0_1px_rgb(255_255_255/0.08)]">{v}</code>
      <Btn variant="ghost" sm type="button" onClick={() => copy(v, k)}
           aria-label={t("copy")}>
        <Icon name={copied === k ? "check" : "copy"} size={13} />
      </Btn>
    </div>
  );

  return (
    <>
      <PageHead icon="card" title={t("pay_title")}
        sub={`${BY.lang === "ar" ? plan.name_ar : plan.name_en} — ${plan.price} ${t("egp")}${annual ? t("per_year") : t("per_month")}`}
        actions={<Btn variant="ghost" sm icon="back" href={BY.urls.pricing}>{t("back")}</Btn>} />

      <Card className="mb-6 bg-[linear-gradient(120deg,rgb(124_108_246/0.18),rgb(34_211_238/0.06))]">
        <div className="text-[14px] text-ink-2">{t("pay_amount")}</div>
        <div className="mt-1 flex flex-wrap items-baseline gap-3">
          {(q.listPrice > q.total) && (
            <span className="text-[18px] text-ink-3 line-through">{num(q.listPrice)}</span>
          )}
          <span className="text-[32px] font-extrabold text-ink tnum">{num(q.total)} {t("egp")}</span>
          {q.planDiscountPct > 0 && <Pill tone="on">-{Math.round(q.planDiscountPct)}%</Pill>}
          {annual && <Pill tone="on">{t("billed_annually")}</Pill>}
          {annual && annualSavingPct > 0 && (
            <Pill tone="on" dot>{t("save_pct").replace("{n}", annualSavingPct)}</Pill>
          )}
          {q.promoCode && <Pill tone="on" dot>{q.promoCode}</Pill>}
        </div>
        <div className="mt-2 text-[12.5px] text-ink-3">
          {t("sub_cycle")}: {t(annual ? "cycle_annual" : "cycle_monthly")} ({days} {BY.lang === "ar" ? "يوم" : "days"}) · {t("pay_secure_note")}
          {/* السنوي افتراضي في صفحة الأسعار — فالتبديل متاح هنا أيضاً قبل الدفع، لا مفاجأة بالمبلغ.
              باقة سنوية إلزامياً (راحة البال) بلا رابط: الخادم يفرض السنة مهما طُلب */}
          {!plan.annual_only && " · "}
          {!plan.annual_only && <a href={`${BY.urls.subscribe}${planId}?cycle=${annual ? "monthly" : "annual"}`}
             className="font-bold text-au-cyan underline">
            {annual ? bi("ادفع شهرياً بدلاً من ذلك", "Pay monthly instead")
                    : bi("وفّر بالدفع السنوي", "Save with annual billing")}
          </a>}
        </div>
        {/* نقل الرصيد يُعرض قبل الدفع لا بعده — المشترك يعرف ما سيحدث لأيامه المدفوعة */}
        {carry && carry.credit > 0 && (
          <div className="mt-4 rounded-xl bg-au-teal/10 p-3.5 text-[13px] font-bold leading-relaxed text-au-teal
                          shadow-[inset_0_0_0_1px_rgb(45_212_191/0.3)]">
            <Icon name="check" size={14} className="me-1.5 inline" />
            {t("carry_note").replace("{r}", num(carry.remaining)).replace("{p}", carry.fromPlan)
                            .replace("{c}", num(carry.credit))}
          </div>
        )}
      </Card>

      {/* كود الخصم — التسعيرة تُحسب في الخادم، والحقل يُرسَل مع النموذج */}
      <Card className="mb-6 max-w-[560px]">
        <SectionTitle icon="bolt">{t("promo_have")}</SectionTitle>
        <div className="flex flex-wrap items-center gap-2.5">
          <Input value={code} onChange={(e) => setCode(e.target.value.toUpperCase())}
                 placeholder="RAMADAN25" autoComplete="off"
                 className="max-w-[220px] uppercase" />
          <Btn variant="ghost" type="button" onClick={check} disabled={busy}>
            {t("promo_apply")}
          </Btn>
          {q.promoCode && (
            <span className="inline-flex items-center gap-1.5 text-[13px] font-bold text-au-teal">
              <Icon name="check" size={14} />{t("promo_applied")} — {num(q.promoCut)} {t("egp")}
            </span>
          )}
          {err && <span className="text-[13px] font-bold text-red-300">{err}</span>}
        </div>
      </Card>

      <Card className="mb-6">
        <SectionTitle icon="wallet">{t("pay_method")}</SectionTitle>
        <div className="grid gap-4 lg:grid-cols-3">
          <div className="rounded-2xl bg-white/[0.03] p-5 shadow-[inset_0_0_0_1px_rgb(255_255_255/0.08)]">
            <div className="flex items-center gap-2 font-extrabold text-[#FF6B6B]">
              <Icon name="phone" size={16} />{t("pay_vodafone")}
            </div>
            <div className="mt-2 text-[12.5px] text-ink-3">{t("pay_number")}</div>
            <CopyRow v={plat.vodafone_number} k="vf" />
          </div>

          <div className="rounded-2xl bg-white/[0.03] p-5 shadow-[inset_0_0_0_1px_rgb(255_255_255/0.08)]">
            <div className="flex items-center gap-2 font-extrabold text-au-violet">
              <Icon name="card" size={16} />{t("pay_instapay")}
            </div>
            <div className="mt-2 text-[12.5px] text-ink-3">{t("pay_scan_qr")}</div>
            <img src={qr} alt="InstaPay QR"
                 className="mx-auto my-3 w-[136px] rounded-xl bg-white p-1" />
            <CopyRow v={plat.instapay_handle} k="ip" />
            {plat.instapay_link && (
              <Btn variant="ghost" sm block icon="link" href={plat.instapay_link}
                   target="_blank" rel="noopener" className="mt-2">{t("pay_open_link")}</Btn>
            )}
          </div>

          <div className="rounded-2xl bg-white/[0.03] p-5 shadow-[inset_0_0_0_1px_rgb(255_255_255/0.08)]">
            <div className="flex items-center gap-2 font-extrabold text-au-cyan">
              <Icon name="bank" size={16} />{t("pay_bank")}
            </div>
            <div className="mt-3 flex flex-col gap-1 text-[12.5px] text-ink-3">
              <span>{t("pay_holder")}: <b className="text-ink-2">{plat.bank_holder}</b></span>
              <span>{t("pay_bankname")}: {plat.bank_name}</span>
            </div>
            <CopyRow v={plat.bank_account} k="acc" />
            <CopyRow v={plat.bank_iban} k="iban" />
          </div>
        </div>
      </Card>

      <Card>
        <SectionTitle icon="upload">{t("pay_upload")}</SectionTitle>
        <ol className="mb-5 flex list-decimal flex-col gap-1.5 ps-5 text-[13px] leading-relaxed text-ink-3">
          <li>{t("pay_step1")}</li><li>{t("pay_step2")}</li><li>{t("pay_step3")}</li>
        </ol>
        <Form action={action} encType="multipart/form-data">
          <input type="hidden" name="promo" value={q.promoCode || ""} />
          {/* اسم الدورة فقط — السعر يُحسب في الخادم، وأي قيمة أخرى تسقط للشهرية */}
          <input type="hidden" name="cycle" value={cycle} />
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
          <div className="mt-6"><Btn icon="shield" type="submit">{t("pay_submit")}</Btn></div>
        </Form>
      </Card>
    </>
  );
}

/* ------------------------------------------------------------- بوت مخصّص */
export function RequestBot() {
  const { plat = {}, sent } = P;
  return (
    <>
      <PageHead icon="sparkles" title={t("req_title")} sub={t("req_sub")}
        actions={<Btn variant="ghost" sm icon="back" href={BY.urls.dashboard}>{t("back")}</Btn>} />

      {sent ? (
        <Card className="mb-6 text-center bg-[linear-gradient(120deg,rgb(45_212_167/0.16),transparent)]">
          <Icon name="check" size={32} className="mx-auto text-au-teal" />
          <h2 className="mt-3 mb-0 text-[19px] font-extrabold text-ink">{t("req_sent")}</h2>
        </Card>
      ) : (
        <Card className="mb-6">
          <Form action="">
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label={t("req_business")}><Input name="business" placeholder={t("eg_cafe")} /></Field>
              <Field label={t("req_budget")}><Input name="budget" placeholder="—" /></Field>
            </div>
            <div className="mt-4">
              <Field label={t("req_desc")}>
                <Textarea name="description" required className="min-h-[130px]"
                  placeholder={bi("مثال: عايز بوت يستقبل حجوزات + يبعت تذكير قبل الموعد بيوم…",
                                  "e.g. I need a bot that takes bookings and sends a reminder a day before…")} />
              </Field>
            </div>
            <div className="mt-4">
              <Field label={t("req_contact")}><Input name="contact" placeholder="01xxxxxxxxx / you@email.com" /></Field>
            </div>
            <div className="mt-6"><Btn icon="rocket" type="submit">{t("req_submit")}</Btn></div>
          </Form>
        </Card>
      )}

      <Card>
        <SectionTitle icon="phone">{t("or_contact_now")}</SectionTitle>
        <div className="flex flex-wrap gap-3">
          {plat.support_email && (
            <Btn variant="ghost" icon="inbox" target="_blank" rel="noopener"
                 href={`mailto:${plat.support_email}?subject=${encodeURIComponent(bi("طلب بوت مخصص - BotYalla", "Custom bot request - BotYalla"))}`}>
              {t("contact_email")}
            </Btn>
          )}
          {plat.support_whatsapp && (
            <Btn variant="green" icon="phone" target="_blank" rel="noopener"
                 href={`https://wa.me/${plat.support_whatsapp}?text=${encodeURIComponent(bi("مرحباً، أريد بوت مخصص من BotYalla", "Hi, I want a custom bot from BotYalla"))}`}>
              {t("contact_whatsapp")}
            </Btn>
          )}
          {plat.support_telegram && (
            <Btn variant="ghost" icon="link" target="_blank" rel="noopener"
                 href={`https://t.me/${plat.support_telegram}`}>{t("contact_telegram")}</Btn>
          )}
        </div>
      </Card>
    </>
  );
}
