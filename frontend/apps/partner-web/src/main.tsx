import { StrictMode, useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import { loadRuntimeConfig } from "@saathi/api-client";
import "@saathi/ui-web/base.css";
import "./partner.css";
import { AuthGate } from "@saathi/auth";
import "@saathi/auth/auth.css";
import App from "./App";
import { Apply } from "./Apply";

/**
 * Applying to join has to work without an account, so it lives outside the
 * gate — reached by `#apply`, which is the whole router this app needs. The
 * hash is read rather than a path, so no server rewrite is required for the
 * static build.
 */
function Partner() {
  const [applying, setApplying] = useState(window.location.hash === "#apply");
  useEffect(() => {
    const read = () => setApplying(window.location.hash === "#apply");
    window.addEventListener("hashchange", read);
    return () => window.removeEventListener("hashchange", read);
  }, []);

  if (applying) return <Apply />;
  return (
    <AuthGate
      app="Partner"
      way="staff"
      roles={["partner"]}
      footer={
        <p className="auth-small">
          No account yet? <a href="#apply">Apply to join the network</a> — a
          person at the hospital reads every application.
        </p>
      }
    >
      <App />
    </AuthGate>
  );
}

// Read config.json first, so the very first request already goes to the right API.
loadRuntimeConfig().then(() => {
  createRoot(document.getElementById("root")!).render(
    <StrictMode>
      <Partner />
    </StrictMode>,
  );
});
