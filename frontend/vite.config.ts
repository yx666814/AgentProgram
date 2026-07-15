import react from "@vitejs/plugin-react";
import { configDefaults, defineConfig } from "vitest/config";

export default defineConfig({
  base: "./",
  plugins: [
    react(),
    {
      name: "desktop-production-csp",
      apply: "build",
      transformIndexHtml: {
        order: "pre",
        handler() {
          return [
            {
              tag: "meta",
              attrs: {
                "http-equiv": "Content-Security-Policy",
                content:
                  "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; " +
                  "font-src 'self'; connect-src 'none'; object-src 'none'; base-uri 'none'; " +
                  "frame-ancestors 'none'; frame-src 'none'; worker-src 'none'; media-src 'none'; " +
                  "form-action 'none'",
              },
              injectTo: "head",
            },
          ];
        },
      },
    },
  ],
  build: {
    outDir: "dist/renderer",
    sourcemap: true,
  },
  test: {
    environment: "jsdom",
    exclude: [...configDefaults.exclude, "tests/e2e/**"],
    globals: true,
    setupFiles: ["./tests/setup.ts"],
  },
});
