import { t, P, BY } from "../kit.jsx";

/* ===============================================================
   صفحات قانونية: شروط الاستخدام (Terms) وسياسة الخصوصية (Privacy)
   المحتوى يأتي من مفاتيح i18n — لا نص مكتوب داخل React.
   ============================================================= */

function Section({ titleKey, bodyKey, email }) {
  const body = t(bodyKey).replace("{email}", email || "");
  return (
    <section className="mb-8">
      <h2 className="text-[17px] font-bold text-ink mb-2">{t(titleKey)}</h2>
      <p className="text-[14.5px] leading-[1.85] text-ink-3">{body}</p>
    </section>
  );
}

function LegalPage({ titleKey, introKey, sections, email }) {
  return (
    <div className="mx-auto max-w-[720px] px-4 py-10">
      <h1 className="text-[26px] font-extrabold text-ink mb-2">{t(titleKey)}</h1>
      <p className="text-[13px] text-ink-4 mb-8">
        {t("legal_updated")}: {P.updated}
      </p>
      <p className="text-[15px] leading-[1.85] text-ink-2 mb-10">
        {t(introKey)}
      </p>
      {sections.map(([tk, bk], i) => (
        <Section key={i} titleKey={tk} bodyKey={bk} email={email} />
      ))}
    </div>
  );
}

export function Terms() {
  const email = P.email || "info@botyalla.com";
  return (
    <LegalPage
      titleKey="terms_title"
      introKey="terms_intro"
      email={email}
      sections={[
        ["terms_s1_t", "terms_s1"],
        ["terms_s2_t", "terms_s2"],
        ["terms_s3_t", "terms_s3"],
        ["terms_s4_t", "terms_s4"],
        ["terms_s5_t", "terms_s5"],
        ["terms_s6_t", "terms_s6"],
        ["terms_s7_t", "terms_s7"],
      ]}
    />
  );
}

export function Privacy() {
  const email = P.email || "info@botyalla.com";
  return (
    <LegalPage
      titleKey="privacy_title"
      introKey="privacy_intro"
      email={email}
      sections={[
        ["privacy_s1_t", "privacy_s1"],
        ["privacy_s2_t", "privacy_s2"],
        ["privacy_s3_t", "privacy_s3"],
        ["privacy_s4_t", "privacy_s4"],
        ["privacy_s5_t", "privacy_s5"],
        ["privacy_s6_t", "privacy_s6"],
        ["privacy_s7_t", "privacy_s7"],
      ]}
    />
  );
}
