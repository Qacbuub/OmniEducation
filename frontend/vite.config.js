import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// In development, /api calls are proxied to the Django server on :8000.
// In production, Nginx serves the built files and proxies /api to Gunicorn.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { "/api": "http://127.0.0.1:8000", "/media": "http://127.0.0.1:8000" },
  },
});
