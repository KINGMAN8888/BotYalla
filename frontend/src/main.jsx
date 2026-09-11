import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./sections.jsx";
import { LegalPublic, NotFound } from "./PublicPages.jsx";
import { BY } from "./ui.jsx";
import "./index.css";

/* الموقع العام: الرئيسية والوثائق القانونية وصفحة 404 — Flask يحدّد الصفحة في BY.page */
const PAGES = { home: App, legal: LegalPublic, notfound: NotFound };

const el = document.getElementById("landing-root");
if (el) {
  const Page = PAGES[BY.page] || App;
  createRoot(el).render(
    <StrictMode>
      <Page />
    </StrictMode>
  );
  document.documentElement.classList.add("react-on");
}
