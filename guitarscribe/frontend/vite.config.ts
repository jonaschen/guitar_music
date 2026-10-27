import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { alphaTab } from "@coderline/alphatab-vite";

const proxy = {
  "/backend": {
    target: process.env.GUITARSCRIBE_API_TARGET || "http://127.0.0.1:8000",
    changeOrigin: true,
    rewrite: (path: string) => path.replace(/^\/backend/, ""),
  },
};
export default defineConfig({
  plugins: [react(), alphaTab()],
  server: { port: 5173, host: "0.0.0.0", proxy },
  preview: { proxy },
});
