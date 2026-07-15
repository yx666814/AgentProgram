import { expect, test } from "@playwright/test";

import { installDesktopFixture } from "./support/desktop-fixture";

function relativeLuminance(hex: string): number {
  const channels = [1, 3, 5].map((index) => Number.parseInt(hex.slice(index, index + 2), 16) / 255);
  const linear = channels.map((value) => value <= 0.03928 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4);
  return 0.2126 * (linear[0] ?? 0) + 0.7152 * (linear[1] ?? 0) + 0.0722 * (linear[2] ?? 0);
}

function contrastRatio(foreground: string, background: string): number {
  const left = relativeLuminance(foreground);
  const right = relativeLuminance(background);
  return (Math.max(left, right) + 0.05) / (Math.min(left, right) + 0.05);
}

test("core navigation and controls have names, landmarks and visible keyboard focus", async ({ page }) => {
  await installDesktopFixture(page);
  await page.goto("/projects/project_demo/stages/planner");
  await expect(page.getByRole("navigation", { name: "工作区导航" })).toBeVisible();
  await expect(page.getByRole("main")).toBeVisible();

  const unnamed = await page.locator("html").evaluate((root) => {
    const elements = Array.from(root.querySelectorAll("button, a, input, textarea, select"));
    return elements.filter((element) => {
      const html = element as HTMLElement;
      const labelled = html.getAttribute("aria-label") ?? html.getAttribute("aria-labelledby") ?? html.textContent;
      return labelled.trim().length === 0 && !(html instanceof HTMLInputElement && html.type === "radio");
    }).length;
  });
  expect(unnamed).toBe(0);

  await page.keyboard.press("Tab");
  const focused = page.locator(":focus");
  await expect(focused).toBeVisible();
  const focusStyle = await focused.evaluate((element) => {
    const style = getComputedStyle(element);
    return { outlineStyle: style.outlineStyle, outlineWidth: style.outlineWidth };
  });
  expect(focusStyle.outlineStyle).not.toBe("none");
  expect(Number.parseFloat(focusStyle.outlineWidth)).toBeGreaterThanOrEqual(2);
});

test("keyboard alone can navigate and execute the diagnostics query", async ({ page }) => {
  await installDesktopFixture(page);
  await page.goto("/projects/project_demo/stages/planner");
  const diagnosticsLink = page.getByRole("link", { name: "事件与诊断" });
  await diagnosticsLink.focus();
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/\/diagnostics$/);
  await page.getByLabel("Workflow ID").fill("workflow_demo");
  const auditButton = page.getByRole("button", { name: "读取审计" });
  await auditButton.focus();
  await page.keyboard.press("Enter");
  await expect(page.getByText("workflow.paused")).toBeVisible();
});

test("reduced motion removes meaningful interaction transitions and disabled reasons are associated", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await installDesktopFixture(page);
  await page.goto("/settings");
  const disabled = page.getByRole("button", { name: "测试连接" });
  const describedBy = await disabled.getAttribute("aria-describedby");
  expect(describedBy).not.toBeNull();
  await expect(page.locator(`#${describedBy ?? "missing"}`)).toContainText("ModelProfileTest");
  const duration = await page.getByRole("button", { name: "刷新" }).evaluate((element) => getComputedStyle(element).transitionDuration);
  expect(Number.parseFloat(duration)).toBeLessThanOrEqual(0.00001);
});

for (const theme of ["light", "dark"] as const) {
  test(`${theme} semantic text tokens meet normal-text contrast`, async ({ page }) => {
    await page.emulateMedia({ colorScheme: theme });
    await installDesktopFixture(page);
    await page.goto("/settings");
    const colors = await page.locator("html").evaluate((element) => {
      const style = getComputedStyle(element);
      const read = (name: string) => style.getPropertyValue(name).trim();
      return {
        accent: read("--accent-default"),
        danger: read("--danger-default"),
        dangerSoft: read("--danger-soft"),
        muted: read("--text-muted"),
        panel: read("--surface-panel"),
        primary: read("--text-primary"),
        control: read("--surface-control"),
        warning: read("--warning-default"),
      };
    });
    expect(contrastRatio(colors.primary, colors.panel)).toBeGreaterThanOrEqual(4.5);
    expect(contrastRatio(colors.muted, colors.panel)).toBeGreaterThanOrEqual(4.5);
    expect(contrastRatio(colors.accent, colors.panel)).toBeGreaterThanOrEqual(4.5);
    expect(contrastRatio(colors.warning, colors.control)).toBeGreaterThanOrEqual(4.5);
    expect(contrastRatio(colors.danger, colors.dangerSoft)).toBeGreaterThanOrEqual(4.5);
  });
}

for (const viewport of [
  { width: 1280, height: 720 },
  { width: 1440, height: 900 },
  { width: 1920, height: 1080 },
] as const) {
  for (const deviceScaleFactor of [1, 1.25, 1.5, 1.75, 2] as const) {
    test(`fits ${String(viewport.width)}x${String(viewport.height)} at ${String(deviceScaleFactor * 100)}% DPI`, async ({ browser }) => {
      const context = await browser.newContext({ viewport, deviceScaleFactor });
      const page = await context.newPage();
      await installDesktopFixture(page);
      await page.goto("/projects/project_demo/stages/builder");
      const layout = await page.locator("html").evaluate((element) => ({ clientWidth: element.clientWidth, scrollWidth: element.scrollWidth, clientHeight: element.clientHeight, scrollHeight: element.scrollHeight }));
      expect(layout.scrollWidth).toBeLessThanOrEqual(layout.clientWidth);
      expect(layout.scrollHeight).toBeLessThanOrEqual(layout.clientHeight);
      await expect(page.locator(".workspace-panel")).toBeVisible();
      await context.close();
    });
  }
}
