import { expect, test } from "@playwright/test";

for (const viewport of [
  { width: 1280, height: 720 },
  { width: 1440, height: 900 },
] as const) {
  const viewportName = `${String(viewport.width)}x${String(viewport.height)}`;

  test(`desktop shell fits ${viewportName}`, async ({ page }) => {
    await page.setViewportSize(viewport);
    await page.goto("/projects");

    await expect(page.getByRole("link", { name: "设置" })).toBeVisible();
    await expect(page.locator(".workspace-panel")).toBeVisible();
    const panel = await page.locator(".workspace-panel").boundingBox();
    expect(panel).not.toBeNull();
    expect(panel?.x).toBeGreaterThanOrEqual(286);
    expect(panel?.width).toBeGreaterThan(900);
    await expect(page).toHaveScreenshot(`shell-${viewportName}.png`, {
      animations: "disabled",
    });
  });
}
