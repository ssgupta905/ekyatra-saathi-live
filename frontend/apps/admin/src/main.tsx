import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { loadRuntimeConfig } from "@saathi/api-client";
import "@saathi/ui-web/styles.css";
import { AuthGate } from "@saathi/auth";
import "@saathi/auth/auth.css";
import App from "./App";

// Read config.json first, so the very first request already goes to the right API.
loadRuntimeConfig().then(() => {
  createRoot(document.getElementById("root")!).render(
    <StrictMode>
      <AuthGate app="Admin" way="staff" roles={["admin"]}>
        <App />
      </AuthGate>
    </StrictMode>,
  );
});
