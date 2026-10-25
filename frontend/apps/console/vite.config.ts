import { resolve } from "node:path";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Three entry points, because there are three audiences and they are not the
// same screen. The family's phone and the hospital's desk are separate
// applications that share a backend and nothing else; `stage` mounts both at
// once so a single recording can show one event moving through both.
export default defineConfig({
  plugins: [react()],
  build: {
    rollupOptions: {
      input: {
        hospital: resolve(__dirname, "index.html"),
        family: resolve(__dirname, "family.html"),
        stage: resolve(__dirname, "stage.html"),
      },
    },
  },
  server: {
    port: Number(process.env.SAATHI_CONSOLE_PORT ?? 5173),
    // The console talks to the FastAPI service; proxying keeps the browser
    // origin single so no CORS preflight is needed in development.
    // Port is configurable because 8000 is a popular address — another project
    // of yours may already own it, and killing whatever answers there is not a
    // reasonable way to free it up.
    proxy: {
      "/api": `http://localhost:${process.env.SAATHI_API_PORT ?? 8000}`,
    },
  },
});
