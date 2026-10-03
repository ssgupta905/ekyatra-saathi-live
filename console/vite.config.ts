import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
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
