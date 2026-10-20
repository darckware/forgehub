// defineConfig from vitest/config: since Vitest 4 the triple-slash reference
// no longer adds `test` to Vite's config type, and the Docker build (a clean
// install, no local tsbuildinfo cache) fails on it.
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import path from "node:path";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    host: true,
    port: 5173,
    // Match nginx's production same-origin contract while developing. The
    // SPA always calls /api on its current origin; without this proxy Vite's
    // history fallback returns index.html for API requests and every
    // dashboard query fails while appearing to be a backend outage.
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
        ws: true,
      },
    },
  },
  test: {
    globals: true,
    environment: "jsdom",
    setupFiles: "./src/test/setup.ts",
    // scripts/*.test.mjs são testes do `node --test` (ver "test:scripts"), não do Vitest.
    include: ["src/**/*.test.{ts,tsx}"],
  },
});
