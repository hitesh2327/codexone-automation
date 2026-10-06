import path from "node:path";
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Dev: the browser talks only to Vite (localhost:5173); /api is proxied to FastAPI, so
// the session cookie is same-origin exactly like in production.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: { alias: { "@": path.resolve(__dirname, "./src") } },
  server: {
    port: 5173,
    host: true,
    proxy: { "/api": { target: process.env.API_PROXY_TARGET ?? "http://localhost:8001", changeOrigin: false } },
  },
});
