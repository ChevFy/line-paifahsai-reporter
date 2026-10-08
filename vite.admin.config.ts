import { fileURLToPath } from "node:url";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

const projectRoot = fileURLToPath(new URL(".", import.meta.url));
const backend = "http://127.0.0.1:8000";

// The admin dashboard is a separate site from the LIFF app. It must be served
// from the same origin as the backend API because the admin_session cookie is
// SameSite=Strict with Path=/admin, so page routes must never start with /admin.
//
// The proxy below only exists in dev/preview. In production, serve dist-admin/
// behind the same reverse proxy as the backend: forward /admin/* and /districts
// to the backend and fall back every other path to index.html.
export default defineConfig({
  root: fileURLToPath(new URL("./src/app", import.meta.url)),
  envDir: projectRoot,
  publicDir: fileURLToPath(new URL("./public", import.meta.url)),
  plugins: [react()],
  server: {
    port: 5174,
    proxy: {
      "/admin": backend,
      "/districts": backend,
    },
  },
  preview: {
    port: 4174,
  },
  build: {
    outDir: fileURLToPath(new URL("./dist-admin", import.meta.url)),
    emptyOutDir: true,
  },
});
