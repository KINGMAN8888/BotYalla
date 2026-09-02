import { StrictMode, Component } from "react";
import { createRoot } from "react-dom/client";
import AppShell from "./app/AppShell.jsx";
import { BY } from "./app/kit.jsx";
import "./index.css";

import Dashboard from "./app/views/Dashboard.jsx";
import BotDetail from "./app/views/BotDetail.jsx";
import { Account, Settings, Billing, Pricing, Subscribe, RequestBot } from "./app/views/Account.jsx";
import { AdminOverview, AdminUsers, AdminPayments, AdminRequests, AdminPlatform } from "./app/views/Admin.jsx";
import { FlowBuilder, Broadcast, Analytics, Auth } from "./app/views/Tools.jsx";

/* خريطة العرض ← المكوّن. Flask يحدّد العرض عبر data-view. */
const VIEWS = {
  dashboard:      Dashboard,
  bot_detail:     BotDetail,
  flow:           FlowBuilder,
  broadcast:      Broadcast,
  analytics:      Analytics,
  account:        Account,
  settings:       Settings,
  billing:        Billing,
  pricing:        Pricing,
  subscribe:      Subscribe,
  request_bot:    RequestBot,
  admin_overview: AdminOverview,
  admin_users:    AdminUsers,
  admin_payments: AdminPayments,
  admin_requests: AdminRequests,
  admin_platform: AdminPlatform,
};

/* صفحات المصادقة بلا قشرة لوحة */
const BARE = { login: () => <Auth mode="login" />, register: () => <Auth mode="register" /> };

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

const el = document.getElementById("root");
if (el) {
  const view = el.dataset.view;
  const Bare = BARE[view];
  const View = VIEWS[view];

  const tree = Bare ? <Bare />
    : View ? <AppShell view={view}><Boundary><View /></Boundary></AppShell>
    : <AppShell view={view}><div className="text-ink-3">Unknown view: {view}</div></AppShell>;

  createRoot(el).render(<StrictMode><Boundary>{tree}</Boundary></StrictMode>);
  document.documentElement.classList.add("react-on");
}
