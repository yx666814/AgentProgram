import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./tests/e2e",
  use: {
    viewport: { width: 900, height: 560 },
    colorScheme: "light",
  },
});
