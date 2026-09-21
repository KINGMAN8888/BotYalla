import { useEffect, useMemo, useState } from "react";
import { BY, P, t, bi, AR, Icon, Card, Btn, Field, Input, Select, Form } from "./kit.jsx";
import { Flashes } from "./AppShell.jsx";

/* ============================================================================
   نظام الحساب: الدخول · التسجيل · تأكيد البريد · إكمال حساب جوجل/فيسبوك
   القواعد هنا **مرآة** لـ accounts.py للتوجيه الحيّ فقط — الخادم هو الحكم،
   وأي تعديل في القواعد يُنسخ في الملفين معاً.
   ========================================================================== */

/* ------------------------------------------------------------ اسم المستخدم */
const U_RE = /^[A-Za-z0-9_.\-ؠ-ي٠-٩ٱ-ۓ]{3,32}$/;
const LETTER = /[A-Za-zؠ-يٱ-ۓ]/;

export function usernameLocal(u) {
  if (u.length < 3 || u.length > 32) return bi("من 3 إلى 32 حرفاً.", "3–32 characters.");
  if (!U_RE.test(u)) return bi("حروف وأرقام و _ . - فقط — بلا مسافات.", "Letters, digits and _ . - only — no spaces.");
  if (!LETTER.test(u)) return bi("لازم يكون فيه حروف — مش أرقام بس.", "It can't be digits only.");
  if (!LETTER.test(u[0])) return bi("لازم يبدأ بحرف.", "It must start with a letter.");
  if ("._-".includes(u[u.length - 1])) return bi("لا ينتهي بـ . أو _ أو -.", "It can't end with . _ or -.");
  if (/[._-]{2}/.test(u)) return bi("لا تكرر الرموز . _ - ورا بعض.", "Don't repeat . _ - in a row.");
  return null;
}

/* ------------------------------------------------------------ كلمة المرور */
export const PW_RULES = [
  ["len",    bi("8 أحرف على الأقل", "At least 8 characters"),        (p) => p.length >= 8],
  ["upper",  bi("حرف إنجليزي كبير (A-Z)", "An uppercase letter (A-Z)"), (p) => /[A-Z]/.test(p)],
  ["lower",  bi("حرف إنجليزي صغير (a-z)", "A lowercase letter (a-z)"),  (p) => /[a-z]/.test(p)],
  ["digit",  bi("رقم (0-9)", "A number (0-9)"),                        (p) => /\d/.test(p)],
  ["symbol", bi("رمز مثل ! @ # $ %", "A symbol like ! @ # $ %"),       (p) => /[^A-Za-z0-9]/.test(p)],
];
const COMMON = new Set(["12345678", "123456789", "1234567890", "password", "password1", "password123",
  "qwerty123", "qwertyuiop", "11111111", "00000000", "abc12345", "abcd1234", "iloveyou", "admin123",
  "welcome1", "p@ssw0rd", "passw0rd", "1q2w3e4r", "1qaz2wsx", "zaq12wsx", "qwe12345", "aa123456",
  "asdf1234", "asdfghjkl", "letmein1", "botyalla"]);
const CORE = new Set(["password", "passwd", "pass", "qwerty", "qwertyuiop", "asdf", "asdfgh", "admin",
  "welcome", "botyalla", "iloveyou", "letmein", "abc", "abcd", "abcdef", "azerty", "monkey", "dragon",
  "football", "master", "sunshine", "princess", "test", "user"]);

export function pwCheck(p, username = "", email = "") {
  const rules = PW_RULES.map(([k, label, f]) => ({ k, label, ok: f(p) }));
  const low = p.toLowerCase();
  const common = !!p && (COMMON.has(low) || CORE.has(low.replace(/[^a-z]/g, "")));
  const u = (username || "").toLowerCase();
  const local = ((email || "").split("@")[0] || "").toLowerCase();
  const personal = !!p && ((u.length >= 3 && low.includes(u)) || (local.length >= 4 && low.includes(local)));
  const passed = rules.filter((r) => r.ok).length;
  let score = passed <= 2 ? 0 : passed === 3 ? 1 : passed === 4 ? 2 : p.length >= 12 ? 4 : 3;
  if (common || personal) score = Math.min(score, 1);
  return { rules, common, personal, score, valid: passed === 5 && !common && !personal && p.length <= 128 };
}

const EyeIcon = ({ off }) => (
  <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.7"
       strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12z" />
    <circle cx="12" cy="12" r="3" />
    {off && <path d="M4 4l16 16" />}
  </svg>
);

/* حقل سرّي بزرّ إظهار — الغلاف ltr حتى يبقى الزر والحشوة في نفس الجهة */
export function SecretInput({ show, onToggle, className = "", ...p }) {
  return (
    <div className="relative" dir="ltr">
      <Input {...p} type={show ? "text" : "password"} className={`pe-11 ${className}`} />
      <button type="button" onClick={onToggle} tabIndex={-1}
        aria-label={show ? bi("إخفاء كلمة المرور", "Hide password") : bi("إظهار كلمة المرور", "Show password")}
        className="absolute inset-y-0 end-0 grid w-11 cursor-pointer place-items-center border-0 bg-transparent text-ink-3 hover:text-ink">
        <EyeIcon off={show} />
      </button>
    </div>
  );
}

const ErrLine = ({ children }) =>
  children ? <span className="mt-1.5 block text-[12px] leading-relaxed text-red-300">{children}</span> : null;

const STRENGTH = [["#F87171", bi("ضعيفة جداً", "Very weak")], ["#FB923C", bi("ضعيفة", "Weak")],
                  ["#FACC15", bi("مقبولة", "Fair")], ["#5EEAD4", bi("جيدة", "Good")],
                  ["#2DD4A7", bi("قوية جداً", "Very strong")]];

/* كلمة المرور + التأكيد: عدّاد قوة، والمتطلبات مكتوبة تحتها وتتعلّم وأنت تكتب */
export function PasswordField({ name = "password", confirmName = "password2", label, username = "", email = "",
                                optional = false, onValid, error, error2 }) {
  const [pw, setPw] = useState("");
  const [pw2, setPw2] = useState("");
  const [show, setShow] = useState(false);
  const c = useMemo(() => pwCheck(pw, username, email), [pw, username, email]);
  const match = !!pw2 && pw === pw2;
  const ok = optional && !pw ? true : c.valid && match;
  useEffect(() => { onValid && onValid(ok); }, [ok]);
  const [color, word] = STRENGTH[c.score];
  return (
    <div>
      <Field label={label || t("password")}>
        <SecretInput name={name} value={pw} onChange={(e) => setPw(e.target.value)} show={show}
                     onToggle={() => setShow(!show)} required={!optional} maxLength={128} autoComplete="new-password" />
      </Field>
      {pw && (
        <div className="mt-2.5 flex items-center gap-3">
          <div className="flex flex-1 gap-1.5" dir="ltr">
            {[0, 1, 2, 3].map((i) => (
              <span key={i} className="h-1.5 flex-1 rounded-full transition-colors duration-300"
                    style={{ background: i < Math.max(1, c.score) ? color : "rgb(255 255 255 / 0.08)" }} />
            ))}
          </div>
          <span className="text-[12px] font-bold" style={{ color }}>{word}</span>
        </div>
      )}
      <ul className="m-0 mt-3 grid list-none gap-x-4 gap-y-1.5 p-0 sm:grid-cols-2">
        {c.rules.map((r) => (
          <li key={r.k} className={`flex items-center gap-1.5 text-[12px] transition-colors ${r.ok ? "text-au-teal" : "text-ink-3"}`}>
            {r.ok ? <Icon name="check" size={13} /> : <span className="grid size-[13px] place-items-center"><i className="block size-1.5 rounded-full bg-current opacity-60" /></span>}
            {r.label}
          </li>
        ))}
      </ul>
      {c.common && <ErrLine>{bi("كلمة المرور دي شائعة وسهلة التخمين — اختار حاجة مختلفة.", "That password is too common — pick something different.")}</ErrLine>}
      {c.personal && <ErrLine>{bi("ما تحطش اسم المستخدم أو بريدك جوه كلمة المرور.", "Don't put your username or email in the password.")}</ErrLine>}
      <ErrLine>{error}</ErrLine>
      <Field label={bi("تأكيد كلمة المرور", "Confirm password")} className="mt-4">
        <SecretInput name={confirmName} value={pw2} onChange={(e) => setPw2(e.target.value)} show={show}
                     onToggle={() => setShow(!show)} required={!optional || !!pw} maxLength={128} autoComplete="new-password" />
      </Field>
      {pw2 && (
        <span className={`mt-1.5 flex items-center gap-1.5 text-[12px] ${match ? "text-au-teal" : "text-red-300"}`}>
          <Icon name={match ? "check" : "close"} size={13} />
          {match ? bi("متطابقتان", "Passwords match") : bi("غير متطابقتين", "Passwords don't match")}
        </span>
      )}
      <ErrLine>{error2}</ErrLine>
    </div>
  );
}

/* ------------------------------------------------------------ اسم المستخدم (فحص حيّ) */
export function UsernameField({ defaultValue = "", current = "", error, onValid, onChange, label }) {
  const [v, setV] = useState(defaultValue);
  const [st, setSt] = useState({ s: "idle" });
  useEffect(() => {
    const u = v.trim();
    onChange && onChange(u);
    if (!u) { setSt({ s: "idle" }); return; }
    if (current && u === current) { setSt({ s: "ok", same: true }); return; }   // اسمك الحالي
    const local = usernameLocal(u);
    if (local) { setSt({ s: "bad", msg: local }); return; }
    setSt({ s: "checking" });
    const ctl = new AbortController();
    const h = setTimeout(async () => {
      try {
        const r = await fetch(`${BY.urls.checkUsername || "/api/check-username"}?u=${encodeURIComponent(u)}`,
                              { signal: ctl.signal });
        const d = await r.json();
        setSt(d.ok ? { s: "ok" } : { s: "bad", msg: d.error, sug: d.suggestions || [] });
      } catch (e) { if (e.name !== "AbortError") setSt({ s: "idle" }); }
    }, 400);
    return () => { clearTimeout(h); ctl.abort(); };
  }, [v]);
  useEffect(() => { onValid && onValid(st.s === "ok"); }, [st.s]);
  const ring = st.s === "ok" && !st.same ? "shadow-[inset_0_0_0_1px_rgb(45_212_167/0.7)]"
             : st.s === "bad" ? "shadow-[inset_0_0_0_1px_rgb(248_113_113/0.7)]" : "";
  return (
    <Field label={label || t("username")}>
      <div className="relative">
        <Input name="username" value={v} onChange={(e) => setV(e.target.value.replace(/\s/g, ""))} required
               minLength={3} maxLength={32} autoComplete="username" dir="auto" className={`pe-10 ${ring}`} />
        <span className="pointer-events-none absolute inset-y-0 end-0 grid w-10 place-items-center">
          {st.s === "checking" && <i className="block size-4 animate-spin rounded-full border-2 border-ink-3 border-t-transparent" />}
          {st.s === "ok" && !st.same && <Icon name="check" size={16} className="text-au-teal" />}
          {st.s === "bad" && <Icon name="close" size={16} className="text-red-300" />}
        </span>
      </div>
      {st.s === "ok" && !st.same && <span className="mt-1.5 block text-[12px] text-au-teal">{bi("الاسم متاح ✓", "Available ✓")}</span>}
      {st.s === "bad" && <ErrLine>{st.msg}</ErrLine>}
      {st.s === "bad" && st.sug && st.sug.length > 0 && (
        <span className="mt-2 flex flex-wrap items-center gap-1.5 text-[12px] text-ink-3">
          {bi("جرّب:", "Try:")}
          {st.sug.map((s) => (
            <button key={s} type="button" onClick={() => setV(s)} dir="auto"
              className="cursor-pointer rounded-full border-0 bg-white/[0.06] px-2.5 py-1 text-[12px] font-bold text-ink hover:bg-au-violet/25">{s}</button>
          ))}
        </span>
      )}
      {st.s === "idle" && !error && (
        <span className="mt-1.5 block text-[12px] leading-relaxed text-ink-3">
          {bi("يبدأ بحرف · حروف وأرقام و _ . - · بلا مسافات — مثال: nour_store", "Starts with a letter · letters, digits and _ . - · no spaces — e.g. nour_store")}
        </span>
      )}
      {st.s === "idle" && <ErrLine>{error}</ErrLine>}
    </Field>
  );
}

/* ------------------------------------------------------------ الهاتف */
export function splitPhone(full, countries) {
  const list = [...(countries || [])].sort((a, b) => b[1].length - a[1].length);
  const hit = full && list.find((c) => full.startsWith(c[1]));
  return hit ? [hit[1], full.slice(hit[1].length)] : ["+20", ""];
}

export function PhoneField({ cc = "+20", value = "", error, hint, label }) {
  const list = P.countries || [];
  return (
    <Field label={label || bi("رقم الموبايل", "Mobile number")}>
      <div className="flex gap-2" dir="ltr">
        <div className="w-[46%] max-w-[190px] shrink-0">
          <Select name="phone_cc" defaultValue={cc}>
            {list.map(([code, dial, ar, en]) => <option key={code} value={dial}>{`${dial} ${AR ? ar : en}`}</option>)}
          </Select>
        </div>
        <Input name="phone" type="tel" inputMode="tel" autoComplete="tel-national" required defaultValue={value}
               placeholder="10 1234 5678" dir="ltr" className="min-w-0 flex-1" />
      </div>
      {hint && !error && <span className="mt-1.5 block text-[12px] leading-relaxed text-ink-3">{hint}</span>}
      <ErrLine>{error}</ErrLine>
    </Field>
  );
}

/* ------------------------------------------------------------ نوع الحساب */
const ENTITIES = [
  ["individual", "user", ["فرد", "Individual"], ["نشاط باسمك", "Your own business"]],
  ["company", "store", ["شركة", "Company"], ["شركة أو براند", "A company or brand"]],
  ["institution", "bank", ["مؤسسة", "Institution"], ["جمعية · مدرسة · جهة", "NGO · school · body"]],
];
export const entityLabel = (k) => { const e = ENTITIES.find((x) => x[0] === k); return e ? bi(...e[2]) : "—"; };

export function EntityPicker({ name = "entity_type", defaultValue = "", error, onChange }) {
  const [v, setV] = useState(defaultValue || "");
  useEffect(() => { onChange && onChange(v); }, [v]);
  return (
    <Field label={bi("نوع الحساب", "Account type")}>
      <input type="hidden" name={name} value={v} />
      <div className="grid grid-cols-3 gap-2" role="radiogroup">
        {ENTITIES.map(([k, ic, l, d]) => {
          const on = v === k;
          return (
            <button key={k} type="button" role="radio" aria-checked={on} onClick={() => setV(k)}
              className={`flex cursor-pointer flex-col items-center gap-1 rounded-xl border-0 px-2 py-3 text-center transition-all duration-300
                ${on ? "bg-[linear-gradient(150deg,rgb(124_108_246/0.25),rgb(34_211_238/0.1))] text-ink shadow-[inset_0_0_0_1.5px_rgb(124_108_246/0.8)]"
                     : "bg-white/[0.03] text-ink-3 shadow-[inset_0_0_0_1px_rgb(255_255_255/0.08)] hover:bg-white/[0.06] hover:text-ink-2"}`}>
              <Icon name={ic} size={19} className={on ? "text-au-cyan" : ""} />
              <b className="text-[13px]">{bi(...l)}</b>
              <span className="hidden text-[10.5px] leading-tight opacity-80 sm:block">{bi(...d)}</span>
            </button>
          );
        })}
      </div>
      <ErrLine>{error}</ErrLine>
    </Field>
  );
}

/* ------------------------------------------------------------ موافقات */
export function Consent({ error, onChange }) {
  return (
    <>
      <label className="flex cursor-pointer items-start gap-2.5 text-[12.5px] leading-relaxed text-ink-2">
        <input type="checkbox" name="terms" value="1" required onChange={(e) => onChange && onChange(e.target.checked)}
               className="mt-1 size-4 shrink-0 accent-[#7C6CF6]" />
        <span>
          {bi("أوافق على ", "I agree to the ")}
          <a href={BY.urls.terms} target="_blank" rel="noopener" className="font-bold text-au-cyan">{bi("الشروط والأحكام", "Terms")}</a>
          {bi(" و", " and ")}
          <a href={BY.urls.privacy} target="_blank" rel="noopener" className="font-bold text-au-cyan">{bi("سياسة الخصوصية", "Privacy Policy")}</a>
          {bi("، وعمري 18 سنة أو أكثر.", ", and I'm 18 or older.")}
        </span>
      </label>
      <ErrLine>{error}</ErrLine>
      {/* موافقة صريحة على الأخبار — غير محددة افتراضياً */}
      <label className="mt-3 flex cursor-pointer items-start gap-2.5 text-[12.5px] leading-relaxed text-ink-3">
        <input type="checkbox" name="email_news" value="1" className="mt-1 size-4 shrink-0 accent-[#7C6CF6]" />
        <span>{bi("ابعتولي أخبار BotYalla وعروضها على إيميلي — أقدر ألغيها في أي وقت.",
                  "Email me BotYalla news and offers — I can unsubscribe anytime.")}</span>
      </label>
    </>
  );
}

/* ------------------------------------------------------------ جوجل وفيسبوك */
export const GoogleG = () => (
  <svg viewBox="0 0 48 48" width="19" height="19" aria-hidden="true">
    <path fill="#FFC107" d="M43.6 20.1H42V20H24v8h11.3C33.7 32.7 29.2 36 24 36c-6.6 0-12-5.4-12-12s5.4-12 12-12c3.1 0 5.8 1.2 8 3l5.7-5.7C34 6.1 29.3 4 24 4 13 4 4 13 4 24s9 20 20 20 20-9 20-20c0-1.3-.1-2.6-.4-3.9z" />
    <path fill="#FF3D00" d="m6.3 14.7 6.6 4.8C14.7 15.1 19 12 24 12c3.1 0 5.8 1.2 8 3l5.7-5.7C34 6.1 29.3 4 24 4 16.3 4 9.7 8.3 6.3 14.7z" />
    <path fill="#4CAF50" d="M24 44c5.2 0 9.9-2 13.4-5.2l-6.2-5.2A11.9 11.9 0 0 1 24 36c-5.2 0-9.6-3.3-11.3-7.9l-6.5 5C9.5 39.6 16.2 44 24 44z" />
    <path fill="#1976D2" d="M43.6 20.1H42V20H24v8h11.3a12 12 0 0 1-4.1 5.6l6.2 5.2C37 39.2 44 34 44 24c0-1.3-.1-2.6-.4-3.9z" />
  </svg>
);
export const FacebookF = () => (
  <svg viewBox="0 0 24 24" width="19" height="19" fill="#fff" aria-hidden="true">
    <path d="M24 12.07C24 5.41 18.63 0 12 0S0 5.4 0 12.07C0 18.1 4.39 23.1 10.13 24v-8.44H7.08v-3.49h3.04V9.41c0-3.02 1.8-4.7 4.54-4.7 1.31 0 2.68.24 2.68.24v2.97h-1.5c-1.5 0-1.96.93-1.96 1.89v2.26h3.33l-.53 3.49h-2.8V24C19.62 23.1 24 18.1 24 12.07" />
  </svg>
);
const SOCIAL = "flex w-full items-center justify-center gap-2.5 rounded-xl px-4 py-3 text-[14px] font-bold no-underline " +
               "transition-transform duration-300 hover:-translate-y-0.5";

export function SocialButtons({ mode = "login", link = false }) {
  const o = P.oauth || {};
  if (!o.google && !o.facebook) return null;
  const q = link ? "?link=1" : "";
  return (
    <>
      <div className="flex flex-col gap-2.5">
        {o.google && (
          <a href={`/auth/google${q}`} className={`${SOCIAL} bg-white text-[#1F2937] shadow-[0_6px_20px_-8px_rgb(255_255_255/0.35)]`}>
            <GoogleG />{link ? bi("اربط حساب جوجل", "Link Google") : bi("المتابعة بحساب جوجل", "Continue with Google")}
          </a>
        )}
        {o.facebook && (
          <a href={`/auth/facebook${q}`} className={`${SOCIAL} bg-[#1877F2] text-white shadow-[0_6px_20px_-8px_rgb(24_119_242/0.6)]`}>
            <FacebookF />{link ? bi("اربط حساب فيسبوك", "Link Facebook") : bi("المتابعة بحساب فيسبوك", "Continue with Facebook")}
          </a>
        )}
      </div>
      {!link && (
        <div className="my-6 flex items-center gap-3 text-[12px] text-ink-3">
          <span className="h-px flex-1 bg-white/10" />
          {mode === "register" ? bi("أو سجّل بالبريد", "or sign up with email") : bi("أو بكلمة المرور", "or with your password")}
          <span className="h-px flex-1 bg-white/10" />
        </div>
      )}
    </>
  );
}

/* ------------------------------------------------------------ الغلاف */
function Shell({ wide, children }) {
  return (
    <div className={`mx-auto flex min-h-screen flex-col justify-center px-5 py-14 ${wide ? "max-w-[540px]" : "max-w-[440px]"}`}>
      <Flashes />
      <a href={BY.urls.landing} className="mb-6 flex justify-center no-underline">
        <img src={BY.urls.logo} alt={BY.brand} className="h-11 w-auto" />
      </a>
      {children}
    </div>
  );
}

/* ------------------------------------------------------------ الدخول والتسجيل */
export function Auth({ mode }) {
  const isLogin = mode === "login";
  const v = P.values || {};
  const e = P.errors || {};
  const [cc, phone] = [v.phone_cc || "+20", v.phone || ""];
  const [uOk, setUOk] = useState(false);
  const [pwOk, setPwOk] = useState(false);
  const [ent, setEnt] = useState(v.entity_type || "");
  const [terms, setTerms] = useState(false);
  const [uname, setUname] = useState(v.username || "");
  const [email, setEmail] = useState(v.email || "");
  const [show, setShow] = useState(false);
  const ready = uOk && pwOk && ent && terms;

  if (isLogin) {
    return (
      <Shell>
        <Card className="!p-8">
          <h1 className="m-0 text-center text-[24px] font-extrabold tracking-tight text-ink">{t("login")}</h1>
          <p className="mb-7 mt-2 text-center text-[14px] text-ink-3">{t("login_sub")}</p>
          <SocialButtons mode="login" />
          <Form action="">
            <Field label={bi("اسم المستخدم أو البريد الإلكتروني", "Username or email")} className="mb-4">
              <Input name="username" required autoFocus autoComplete="username" dir="auto" />
            </Field>
            <Field label={
              <span className="flex items-center justify-between gap-2">
                {t("password")}
                <a href={BY.urls.forgot} className="text-[12px] font-normal text-au-cyan underline-offset-4 hover:underline">{t("forgot_link")}</a>
              </span>}>
              <SecretInput name="password" required autoComplete="current-password" show={show} onToggle={() => setShow(!show)} />
            </Field>
            <div className="mt-6"><Btn block icon="lock" type="submit">{t("login")}</Btn></div>
          </Form>
          <p className="mt-6 text-center text-[13px] text-ink-3">
            {t("no_account")}{" "}
            <a href={BY.urls.register} className="font-bold text-au-cyan underline-offset-4 hover:underline">{t("signup_link")}</a>
          </p>
        </Card>
      </Shell>
    );
  }

  return (
    <Shell wide>
      <Card className="!p-7 sm:!p-8">
        <h1 className="m-0 text-center text-[24px] font-extrabold tracking-tight text-ink">{t("register")}</h1>
        <p className="mb-7 mt-2 text-center text-[14px] text-ink-3">{t("register_sub")}</p>
        {P.invite && (
          <div className="mb-6 flex items-start gap-3 rounded-2xl bg-[linear-gradient(120deg,rgb(45_212_191/0.16),rgb(124_108_246/0.1))]
                          px-4 py-3.5 text-[13.5px] leading-relaxed text-ink-2 shadow-[inset_0_0_0_1px_rgb(45_212_191/0.3)]">
            <Icon name="check" size={18} className="mt-0.5 shrink-0 text-au-teal" />
            <span>
              <b className="text-ink">{bi("رابط تسجيل سهل من فريق BotYalla", "An easy sign-up link from the BotYalla team")}</b><br />
              {bi("املأ البيانات وادخل على طول — مش هنطلب منك كود على الإيميل.",
                  "Fill in your details and go straight in — no email code needed.")}
            </span>
          </div>
        )}
        <SocialButtons mode="register" />
        <Form action="" noValidate={false}>
          <div className="flex flex-col gap-5">
            <EntityPicker defaultValue={v.entity_type} error={e.entity_type} onChange={setEnt} />
            <UsernameField defaultValue={v.username || ""} error={e.username} onValid={setUOk} onChange={setUname} />
            <div className="grid gap-5 sm:grid-cols-[1fr_120px]">
              <Field label={t("email")} hint={!e.email && (P.invite
                  ? bi("اكتبه صح — عليه بترجع كلمة المرور لو نسيتها.", "Type it carefully — it's how you reset a forgotten password.")
                  : bi("هنبعتلك كود تأكيد عليه.", "We'll send a confirmation code to it."))}>
                <Input type="email" name="email" required autoComplete="email" dir="ltr" defaultValue={v.email || ""}
                       onChange={(ev) => setEmail(ev.target.value)} />
                <ErrLine>{e.email}</ErrLine>
              </Field>
              <Field label={bi("السن", "Age")}>
                <Input type="number" name="age" required min="18" max="100" inputMode="numeric" dir="ltr" defaultValue={v.age || ""} />
                <ErrLine>{e.age}</ErrLine>
              </Field>
            </div>
            <PhoneField cc={cc} value={phone} error={e.phone}
                        hint={bi("تقدر تأكده بعد التسجيل بضغطة عن طريق تليجرام.", "You can verify it after signing up with one tap via Telegram.")} />
            <PasswordField username={uname} email={email} onValid={setPwOk} error={e.password} error2={e.password2} />
            <Consent error={e.terms} onChange={setTerms} />
          </div>
          <div className="mt-6">
            <Btn block icon="rocket" type="submit" disabled={!ready}>{t("register")}</Btn>
            {!ready && (
              <span className="mt-2 block text-center text-[11.5px] text-ink-3">
                {bi("الزر هيتفعّل لما كل البيانات تبقى سليمة.", "The button unlocks once everything checks out.")}
              </span>
            )}
          </div>
        </Form>
        <div className="mt-5 flex flex-wrap justify-center gap-x-5 gap-y-2 text-[12px] text-ink-3">
          <span className="inline-flex items-center gap-1.5"><Icon name="check" size={13} className="text-au-teal" />{t("lp_trust_1")}</span>
          <span className="inline-flex items-center gap-1.5"><Icon name="check" size={13} className="text-au-teal" />{t("free_forever")}</span>
        </div>
        <p className="mt-6 text-center text-[13px] text-ink-3">
          {t("have_account")}{" "}
          <a href={BY.urls.login} className="font-bold text-au-cyan underline-offset-4 hover:underline">{t("signin_link")}</a>
        </p>
      </Card>
    </Shell>
  );
}

/* ------------------------------------------------------------ تأكيد البريد */
/* خطوات مصوّرة بالكلام لمن لا يعرف أين يبحث عن الرسالة — وطريق بشري لو لم يصل */
const FIND_STEPS = [
  ["افتح تطبيق الإيميل (Gmail مثلاً) على نفس البريد المكتوب فوق.", "Open your email app (e.g. Gmail) on the address shown above."],
  ["اكتب في البحث: BotYalla — الرسالة عنوانها فيه «كود التأكيد».", "Search for: BotYalla — the subject mentions your confirmation code."],
  ["مش ظاهرة؟ افتح «Spam / الرسائل غير المرغوب فيها» و«العروض / Promotions».", "Not there? Open “Spam” and “Promotions”."],
  ["جوه الرسالة: اضغط الزرار «تأكيد» مرة واحدة، أو انسخ الـ6 أرقام واكتبها هنا.", "Inside it: tap the “Confirm” button once, or copy the 6 digits here."],
];

function FindCode() {
  const [open, setOpen] = useState(false);
  const wa = (P.supportWa || "").replace(/\D/g, "");
  const msg = bi(`محتاج مساعدة في تأكيد حسابي على BotYalla — الإيميل: ${P.email || ""}`,
                 `I need help verifying my BotYalla account — email: ${P.email || ""}`);
  return (
    <div className="mt-5 rounded-2xl bg-white/[0.04] p-4 text-start shadow-[inset_0_0_0_1px_rgb(255_255_255/0.08)]">
      <button type="button" onClick={() => setOpen(!open)} aria-expanded={open}
        className="flex w-full cursor-pointer items-center justify-between gap-2 border-0 bg-transparent p-0 text-[13.5px] font-extrabold text-ink">
        <span className="inline-flex items-center gap-2"><Icon name="help" size={16} className="text-au-cyan" />
          {bi("مش لاقي الكود؟ خطوة بخطوة", "Can't find the code? Step by step")}</span>
        <span className="text-ink-3">{open ? "−" : "+"}</span>
      </button>
      {open && (
        <ol className="m-0 mt-3 flex list-none flex-col gap-2.5 p-0">
          {FIND_STEPS.map((s, i) => (
            <li key={i} className="flex gap-2.5 text-[13px] leading-relaxed text-ink-2">
              <span className="grid size-6 shrink-0 place-items-center rounded-full bg-au-cyan/15 text-[12px] font-extrabold text-au-cyan">{i + 1}</span>
              <span>{bi(...s)}</span>
            </li>
          ))}
          <li className="text-[12.5px] text-ink-3">{bi("الرسالة ممكن تتأخر دقيقة أو اتنين. الكود صالح ساعة.", "It can take a minute or two. The code is valid for an hour.")}</li>
        </ol>
      )}
      {wa && (
        <a href={`https://wa.me/${wa}?text=${encodeURIComponent(msg)}`} target="_blank" rel="noopener"
           className="mt-3 flex items-center justify-center gap-2 rounded-xl bg-[#25D366]/15 px-4 py-2.5 text-[13px] font-extrabold
                      text-[#5BE38F] no-underline shadow-[inset_0_0_0_1px_rgb(37_211_102/0.35)] hover:bg-[#25D366]/25">
          {bi("لسه مش عارف؟ كلّمنا على واتساب ونفعّلك", "Still stuck? Message us on WhatsApp and we'll activate you")}
        </a>
      )}
    </div>
  );
}

export function VerifyEmail() {
  const [wait, setWait] = useState(P.wait || 0);
  const [edit, setEdit] = useState(false);
  const [show, setShow] = useState(false);
  useEffect(() => {
    if (wait <= 0) return undefined;
    const h = setTimeout(() => setWait(wait - 1), 1000);
    return () => clearTimeout(h);
  }, [wait]);
  return (
    <Shell>
      <Card className="!p-8 text-center">
        <span className="mx-auto mb-4 grid size-14 place-items-center rounded-2xl text-au-cyan
                         bg-[linear-gradient(150deg,rgb(124_108_246/0.25),rgb(34_211_238/0.1))]">
          <Icon name="mail" size={26} />
        </span>
        <h1 className="m-0 text-[22px] font-extrabold tracking-tight text-ink">{bi("أكّد بريدك الإلكتروني", "Verify your email")}</h1>
        <p className="mb-6 mt-3 text-[14px] leading-relaxed text-ink-3">
          {P.sent ? bi("بعتنا كود من 6 أرقام على", "We sent a 6-digit code to") : bi("هنبعت كود من 6 أرقام على", "We'll send a 6-digit code to")}
          <br /><b className="text-ink" dir="ltr">{P.email}</b>
          {P.gated && <><br />{bi("أكّده عشان تبدأ تستخدم حسابك.", "Confirm it to start using your account.")}</>}
        </p>
        {P.sent && (
          <Form action={BY.urls.verify || "/verify-email"}>
            <Input name="code" required autoFocus inputMode="numeric" autoComplete="one-time-code" maxLength={6}
                   pattern="[0-9٠-٩]{6}" dir="ltr" placeholder="••••••"
                   className="!py-3.5 text-center font-mono !text-[28px] font-extrabold tracking-[0.45em]" />
            <div className="mt-4"><Btn block icon="check" type="submit">{bi("تأكيد", "Verify")}</Btn></div>
          </Form>
        )}
        <Form action="/verify-email/resend" className="mt-3">
          <Btn block variant={P.sent ? "ghost" : "primary"} icon="mail" type="submit" disabled={wait > 0}>
            {P.sent ? (wait > 0 ? bi(`ابعت كود جديد (${wait})`, `Send a new code (${wait})`) : bi("ابعت كود جديد", "Send a new code"))
                    : bi("ابعت كود التأكيد", "Send the code")}
          </Btn>
        </Form>
        <FindCode />
        <div className="mt-5 border-t border-white/10 pt-5 text-start">
          {!edit ? (
            <button type="button" onClick={() => setEdit(true)}
              className="w-full cursor-pointer border-0 bg-transparent text-center text-[13px] font-bold text-au-cyan hover:underline">
              {bi("البريد مكتوب غلط؟ غيّره", "Wrong email? Change it")}
            </button>
          ) : (
            <Form action="/verify-email/change" className="flex flex-col gap-3">
              <Field label={bi("البريد الصحيح", "The right email")}>
                <Input type="email" name="email" required dir="ltr" autoComplete="email" />
              </Field>
              <Field label={bi("كلمة المرور (للتأكيد)", "Password (to confirm)")}>
                <SecretInput name="password" required autoComplete="current-password" show={show} onToggle={() => setShow(!show)} />
              </Field>
              <Btn variant="ghost" icon="check" type="submit">{bi("غيّر وابعت كود", "Change and send a code")}</Btn>
            </Form>
          )}
        </div>
        <Form action={BY.urls.logout} className="mt-5">
          <button type="submit" className="cursor-pointer border-0 bg-transparent text-[12.5px] text-ink-3 hover:text-ink">
            {bi("تسجيل الخروج", "Sign out")}
          </button>
        </Form>
      </Card>
    </Shell>
  );
}

/* ------------------------------------------------------------ إكمال حساب جوجل/فيسبوك */
export function CompleteProfile() {
  const pend = P.pending || {};
  const v = P.values || {};
  const e = P.errors || {};
  const prov = pend.provider === "facebook" ? "Facebook" : "Google";
  const [uOk, setUOk] = useState(false);
  const [ent, setEnt] = useState(v.entity_type || "");
  const [terms, setTerms] = useState(false);
  const ready = uOk && ent && terms;
  return (
    <Shell wide>
      <Card className="!p-7 sm:!p-8">
        <span className="mx-auto mb-3 flex w-fit items-center gap-2 rounded-full bg-white/[0.06] px-3 py-1.5 text-[12px] font-bold text-ink-2">
          {pend.provider === "facebook" ? <FacebookF /> : <GoogleG />}{bi(`متصل بحساب ${prov}`, `Connected with ${prov}`)}
        </span>
        <h1 className="m-0 text-center text-[23px] font-extrabold tracking-tight text-ink">
          {pend.name ? bi(`أهلاً ${pend.name} — خطوة أخيرة`, `Hi ${pend.name} — one last step`) : bi("خطوة أخيرة", "One last step")}
        </h1>
        <p className="mb-7 mt-2 text-center text-[14px] text-ink-3">
          {bi("كمّل البيانات دي عشان نجهّز حسابك.", "Fill these in so we can set up your account.")}
        </p>
        <Form action="">
          <div className="flex flex-col gap-5">
            <EntityPicker defaultValue={v.entity_type} error={e.entity_type} onChange={setEnt} />
            <UsernameField defaultValue={v.username || (P.suggestions || [])[0] || ""} error={e.username} onValid={setUOk} />
            {pend.email ? (
              <Field label={t("email")}>
                <Input value={pend.email} disabled dir="ltr" />
                <span className="mt-1.5 flex items-center gap-1.5 text-[12px] text-au-teal">
                  <Icon name="check" size={13} />{bi(`مؤكَّد من ${prov}`, `Verified by ${prov}`)}
                </span>
              </Field>
            ) : (
              <Field label={t("email")} hint={!e.email && bi("هنبعتلك كود تأكيد عليه.", "We'll send a confirmation code to it.")}>
                <Input type="email" name="email" required dir="ltr" autoComplete="email" defaultValue={v.email || ""} />
                <ErrLine>{e.email}</ErrLine>
              </Field>
            )}
            <div className="grid gap-5 sm:grid-cols-[120px_1fr]">
              <Field label={bi("السن", "Age")}>
                <Input type="number" name="age" required min="18" max="100" inputMode="numeric" dir="ltr" defaultValue={v.age || ""} />
                <ErrLine>{e.age}</ErrLine>
              </Field>
              <PhoneField cc={v.phone_cc || "+20"} value={v.phone || ""} error={e.phone} />
            </div>
            <Consent error={e.terms} onChange={setTerms} />
          </div>
          <div className="mt-6"><Btn block icon="rocket" type="submit" disabled={!ready}>{bi("أنشئ حسابي", "Create my account")}</Btn></div>
        </Form>
        <p className="mb-0 mt-5 text-center text-[12.5px] text-ink-3">
          <a href={BY.urls.register} className="text-ink-3 underline-offset-4 hover:text-ink hover:underline">
            {bi("إلغاء والتسجيل بالبريد بدلاً من ذلك", "Cancel and sign up with email instead")}
          </a>
        </p>
      </Card>
    </Shell>
  );
}
