import { StrictMode, Component } from "react";
import { createRoot } from "react-dom/client";
import AppShell from "./app/AppShell.jsx";
import { BY } from "./app/kit.jsx";
import { mountAssistant } from "./Assistant.jsx";
import "./index.css";

/* كل عرض في قطعة JS مستقلة تُحمَّل وحدها: صفحة الدخول لا تنزّل محرّر التدفّق ولوحة الأدمن
   وإعدادات البوت (كانت ~290KB تُحلَّل مع كل صفحة، والجوال الضعيف يدفع ثمنها في كل نقرة).
   الهيكل (#boot في react_app.html) يبقى ظاهراً حتى تصل قطعة العرض فلا يظهر هيكلان. */
const dashboard = () => import("./app/views/Dashboard.jsx");
const botDetail = () => import("./app/views/BotDetail.jsx");
const account   = () => import("./app/views/Account.jsx");
const admin     = () => import("./app/views/Admin.jsx");
const tools     = () => import("./app/views/Tools.jsx");
const auth      = () => import("./app/auth.jsx");
const revenue   = () => import("./app/views/Revenue.jsx");
const legal     = () => import("./app/views/Legal.jsx");
const emails    = () => import("./app/views/Emails.jsx");
const waTpl     = () => import("./app/views/WaTemplates.jsx");
const wallet    = () => import("./app/views/Wallet.jsx");
const inbox     = () => import("./app/views/Inbox.jsx");
const media     = () => import("./app/media.jsx");
const reports   = () => import("./app/views/Reports.jsx");

/* خريطة العرض ← [وحدته، اسم المكوّن المصدَّر]. Flask يحدّد العرض عبر data-view. */
const VIEWS = {
  dashboard:      [dashboard, "default"],
  bot_detail:     [botDetail, "default"],
  flow:           [tools, "FlowBuilder"],
  broadcast:      [tools, "Broadcast"],
  analytics:      [tools, "Analytics"],
  account:        [account, "Account"],
  settings:       [account, "Settings"],
  billing:        [account, "Billing"],
  pricing:        [account, "Pricing"],
  subscribe:      [account, "Subscribe"],
  request_bot:    [account, "RequestBot"],
  support:        [account, "Support"],
  admin_overview: [admin, "AdminOverview"],
  admin_users:    [admin, "AdminUsers"],
  admin_payments: [admin, "AdminPayments"],
  admin_requests: [admin, "AdminRequests"],
  admin_tickets:  [admin, "AdminTickets"],
  admin_platform: [admin, "AdminPlatform"],
  admin_analytics: [admin, "AdminAnalytics"],
  admin_report:    [reports, "WeeklyReport"],
  admin_convo:     [reports, "ConvInsights"],
  admin_growth:    [admin, "AdminGrowth"],
  admin_meta:      [admin, "AdminMeta"],
  admin_emails:    [emails, "AdminEmails"],
  addon_pay:       [botDetail, "AddonPay"],
  admin_pricing:    [revenue, "AdminPricing"],
  admin_promos:     [revenue, "AdminPromos"],
  admin_affiliates: [revenue, "AdminAffiliates"],
  affiliate:        [revenue, "Affiliate"],
  terms:            [legal, "Terms"],
  privacy:          [legal, "Privacy"],
  wa_templates:     [waTpl, "default"],
  wallet:           [wallet, "default"],
  inbox:            [inbox, "default"],
  media:            [media, "MediaLibrary"],
};

/* صفحات المصادقة بلا قشرة لوحة: [وحدته، المكوّن، خصائصه] */
const BARE = {
  login:    [auth, "Auth", { mode: "login" }],
  register: [auth, "Auth", { mode: "register" }],
  forgot:   [tools, "Recover", { mode: "forgot" }],
  reset:    [tools, "Recover", { mode: "reset" }],
  unsubscribe:      [emails, "Unsubscribe"],
  verify_email:     [auth, "VerifyEmail"],
  complete_profile: [auth, "CompleteProfile"],
};

/* حاجز أخطاء: خطأ في عرض واحد لا يجوز أن يترك الصفحة سوداء فارغة.
   يعرض رسالة مفهومة وطريق خروج بدل انهيار صامت. */
class Boundary extends Component {
  constructor(p) { super(p); this.state = { err: null }; }
  static getDerivedStateFromError(err) { return { err }; }
  componentDidCatch(err, info) { console.error("BotYalla view crashed:", err, info); }
  render() {
    if (!this.state.err) return this.props.children;
    const ar = BY.lang === "ar";
    return (
      <div className="mx-auto max-w-[560px] px-6 py-20 text-center">
        <h1 className="m-0 mb-3 text-[22px] font-extrabold text-ink">
          {ar ? "حصلت مشكلة في عرض هذه الصفحة" : "Something went wrong rendering this page"}
        </h1>
        <p className="mb-7 text-[14px] leading-relaxed text-ink-3">
          {ar ? "باقي المنصة يعمل طبيعي. جرّب تحديث الصفحة، ولو تكررت المشكلة تواصل معنا."
              : "The rest of the platform is fine. Try reloading; if it repeats, contact us."}
        </p>
        <div className="flex flex-wrap justify-center gap-3">
          <a href={location.href}
             className="rounded-xl bg-[linear-gradient(100deg,#8FE9FF,#B9AFFF)] px-5 py-2.5
                        text-[14px] font-extrabold text-[#07090F] no-underline">
            {ar ? "تحديث" : "Reload"}
          </a>
          <a href={BY.urls.dashboard}
             className="rounded-xl px-5 py-2.5 text-[14px] font-bold text-ink no-underline
                        shadow-[inset_0_0_0_1px_rgb(255_255_255/0.14)]">
            {ar ? "الرجوع للوحة" : "Back to dashboard"}
          </a>
        </div>
        <pre className="mt-8 overflow-x-auto rounded-xl bg-black/40 p-4 text-start text-[11.5px] text-ink-3">
          {String(this.state.err?.message || this.state.err)}
        </pre>
      </div>
    );
  }
}

/* فشل تنزيل قطعة العرض (انقطاع شبكة، أو نشر جديد حذف القطعة القديمة) يُعرض عبر الحاجز نفسه */
function LoadFailed({ err }) { throw err; }

const el = document.getElementById("root");
if (el) {
  const view = el.dataset.view;
  const bare = BARE[view];
  const spec = bare || VIEWS[view];
  const mount = (tree) => {
    createRoot(el).render(<StrictMode><Boundary>{tree}</Boundary></StrictMode>);
    document.documentElement.classList.add("react-on");
    mountAssistant(createRoot);   // «مساعد BotYalla» في اللوحة وصفحات الدخول والتأكيد
  };

  if (!spec) {
    mount(<AppShell view={view}><div className="text-ink-3">Unknown view: {view}</div></AppShell>);
  } else {
    const [load, name, props] = spec;
    load().then((mod) => {
      const View = mod[name];
      mount(bare ? <View {...props} />
                 : <AppShell view={view}><Boundary><View /></Boundary></AppShell>);
    }, (err) => {
      // قطعة من نشر سابق لم تعد موجودة ← تحديث واحد يجلب الروابط الجديدة، بلا حلقة تحديث
      const key = "by-chunk-reload";
      let again = false;
      try { again = sessionStorage.getItem(key) === view; sessionStorage.setItem(key, view); } catch { again = true; }
      if (!again) { location.reload(); return; }
      mount(<LoadFailed err={err} />);
    });
  }
}
