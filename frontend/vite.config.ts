import { fileURLToPath, URL } from "node:url"
import react from "@vitejs/plugin-react"
import tailwindcss from "@tailwindcss/vite"
import { defineConfig } from "vite"

const backend = process.env.BACKEND_ORIGIN || "http://127.0.0.1:8000"
const proxy = Object.fromEntries(
  ["/enroll", "/students", "/exams", "/health"].map((path) => [
    path,
    { target: backend, changeOrigin: true },
  ]),
)

export default defineConfig({
  base: "./",
  plugins: [
    react(),
    tailwindcss(),
    {
      name: "runtime-config",
      transformIndexHtml: {
        order: "post",
        handler: () => [{ tag: "script", attrs: { src: "./config.js" }, injectTo: "head-prepend" }],
      },
    },
  ],
  resolve: { alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) } },
  server: {
    host: "0.0.0.0",
    port: 5173,
    strictPort: true,
    allowedHosts: [".e2b.app"],
    proxy,
  },
  preview: {
    host: "0.0.0.0",
    port: 4173,
    strictPort: true,
    allowedHosts: [".e2b.app"],
    proxy,
  },
})
