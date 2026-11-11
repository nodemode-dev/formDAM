import { defineConfig } from "vite";

export default defineConfig({
  server: {
    host: false,
    port: 5173,
    strictPort: true,
    proxy: { "/api": { target: "http://127.0.0.1:8000", changeOrigin: false } },
  },
  build: { target: "es2022" },
});
