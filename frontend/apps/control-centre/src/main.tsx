import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { loadRuntimeConfig } from "@saathi/api-client";
import "@saathi/ui-web/styles.css";
import "@saathi/auth/auth.css";
import "./legacy.css";
import "./control.css";
import { PersonaGate } from "./session";
import { WorldProvider } from "./world";
import App from "./App";

// Read config.json first, so the very first request already goes to the right API.
loadRuntimeConfig().then(() => {
  createRoot(document.getElementById("root")!).render(
    <StrictMode>
      <PersonaGate>
        <WorldProvider>
          <App />
        </WorldProvider>
      </PersonaGate>
    </StrictMode>,
  );
});
