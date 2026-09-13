import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// 开发期把 /api 与 /healthz 代理到本地 service：生产由 Caddy 同源承担（Module/07 §3），
// 因此**不要求 service 提供 CORS**（service 目前也没有 CORS 中间件）。
const target = process.env["ZACE_WEB_API"] ?? "http://127.0.0.1:8787";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": { target, changeOrigin: false },
      "/healthz": { target, changeOrigin: false },
    },
  },
  build: { outDir: "dist", sourcemap: true },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    include: ["src/**/*.test.{ts,tsx}"],
  },
});
