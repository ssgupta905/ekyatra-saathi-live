import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { loadRuntimeConfig } from "@saathi/api-client";
import "@saathi/ui-web/base.css";
import "./family.css";
import App from "./App";

// Read config.json first, so the very first request already goes to the right API.
loadRuntimeConfig().then(() => {
  createRoot(document.getElementById("root")!).render(
    <StrictMode>
      <App />
    </StrictMode>,
  );
});
