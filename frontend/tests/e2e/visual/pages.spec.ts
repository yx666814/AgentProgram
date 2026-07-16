import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { expect, test } from "@playwright/test";

import { installDesktopFixture } from "../support/desktop-fixture";
import { referenceThemes, referenceViews } from "./reference-manifest";

test.describe.configure({ mode: "serial" });

test("master reference manifest contains 14 views and 28 1440x900 images", () => {
  expect(referenceViews).toHaveLength(14);
  const paths = referenceViews.flatMap((view) => referenceThemes.map((theme) => resolve(process.cwd(), "../docs/frontend/reference-images/v1", `${view.reference}-${theme}.png`)));
  expect(new Set(paths).size).toBe(28);
  for (const path of paths) {
    const png = readFileSync(path);
    expect(png.subarray(1, 4).toString("ascii")).toBe("PNG");
    expect(png.readUInt32BE(16)).toBe(1440);
    expect(png.readUInt32BE(20)).toBe(900);
  }
});

for (const theme of referenceThemes) {
  for (const view of referenceViews) {
    test(`${view.id} ${theme}`, async ({ page }) => {
      await page.emulateMedia({ colorScheme: theme, reducedMotion: "reduce" });
      await installDesktopFixture(page);
      await page.goto(view.path);
      await expect(page.locator("html")).toHaveAttribute("data-theme", theme);
      if ("prepare" in view) {
        await page.getByLabel("Workflow ID").fill("workflow_demo");
        await page.getByRole("button", { name: "读取审计" }).click();
        await expect(page.getByText("workflow.paused")).toBeVisible();
      }
      await expect(page.locator("main").or(page.locator(".startup-screen"))).toBeVisible();
      await expect(page).toHaveScreenshot(`${view.id}-${theme}.png`, {
        animations: "disabled",
        caret: "hide",
        fullPage: false,
        maxDiffPixels: 100,
      });
    });
  }
}
