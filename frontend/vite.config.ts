import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

/**
 * The FastAPI app serves `dist/` in production, so asset URLs stay absolute
 * (`/assets/...`). In development Vite serves the UI on :5173 and proxies
 * `/api` to uvicorn — a proxy rather than CORS, so the browser only ever talks
 * to one origin and the backend needs no cross-origin allowances.
 */
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    strictPort: false,
    proxy: {
      "/api": {
        target: process.env.DSOA_API_URL ?? "http://127.0.0.1:8001",
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: "dist",
    emptyOutDir: true,
    sourcemap: false,
  },
});
