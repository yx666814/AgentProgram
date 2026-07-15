import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./tests/e2e",
  webServer: {
    command: "npm run dev -- --host 127.0.0.1 --port 4173",
    url: "http://127.0.0.1:4173",
    reuseExistingServer: true,
  },
  use: {
    baseURL: "http://127.0.0.1:4173",
    viewport: { width: 900, height: 560 },
    colorScheme: "light",
  },
});
