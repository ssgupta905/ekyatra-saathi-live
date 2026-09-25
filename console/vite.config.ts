import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    // The console talks to the FastAPI service; proxying keeps the browser
    // origin single so no CORS preflight is needed in development.
    proxy: { "/api": "http://localhost:8000" },
  },
});
