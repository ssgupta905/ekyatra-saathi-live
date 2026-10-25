import react from "@vitejs/plugin-react";
import { defineConfig, type UserConfig } from "vite";

/**
 * What every app's Vite config has in common.
 *
 * Each app has its own port, set by `SAATHI_<APP>_PORT` and failing loudly if it
 * is taken: the demo stage frames the other apps by fixed address, so an app that
 * quietly moved to the next free port would leave a blank frame. `/api` is
 * proxied to the FastAPI service, which keeps the browser on one origin in
 * development so no CORS preflight is needed.
 */
export function appConfig(name: string, defaultPort: number): UserConfig {
  const key = `SAATHI_${name.toUpperCase().replace(/-/g, "_")}_PORT`;
  const port = Number(process.env[key] ?? defaultPort);
  const api = `http://localhost:${process.env.SAATHI_API_PORT ?? 8000}`;

  return defineConfig({
    plugins: [react()],
    server: { port, strictPort: true, proxy: { "/api": api } },
    preview: { port, strictPort: true, proxy: { "/api": api } },
  });
}
