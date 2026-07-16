import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./tests/product-e2e",
  fullyParallel: false,
  workers: 1,
  timeout: 15 * 60 * 1000,
  expect: { timeout: 20_000 },
  reporter: [["list"]],
  outputDir: "test-results/product-e2e",
});
