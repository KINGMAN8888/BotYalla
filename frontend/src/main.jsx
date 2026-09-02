import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./sections.jsx";
import "./index.css";

const el = document.getElementById("landing-root");
if (el) {
  createRoot(el).render(
    <StrictMode>
      <App />
    </StrictMode>
  );
  document.documentElement.classList.add("react-on");
}
