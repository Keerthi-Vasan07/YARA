import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const targetUrl = env.VITE_GLORYS_API_BASE_URL || "http://127.0.0.1:8001";

  return {
    plugins: [react()],
    server: {
      port: 5173,
      proxy: {
        "/api": {
          target: targetUrl,
          changeOrigin: true,
        },
      },
    },
  };
});
