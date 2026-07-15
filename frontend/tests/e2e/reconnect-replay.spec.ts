import { expect, test } from "@playwright/test";

import { installDesktopFixture } from "./support/desktop-fixture";

test("requests replay without exposing WebSocket tickets and ignores duplicate event ids", async ({ page }) => {
  await installDesktopFixture(page);
  await page.goto("/projects/project_demo");
  const initial = await page.evaluate(() => (Reflect.get(window, "__desktopTest") as { calls: { replays: number[] } }).calls.replays);
  expect(initial.length).toBeGreaterThanOrEqual(1);
  expect(initial.every((cursor) => cursor === 0)).toBe(true);

  await page.evaluate(() => {
    const hook = Reflect.get(window, "__desktopTest") as { emit: (type: string, correlation: string, extra: Record<string, unknown>) => void };
    hook.emit("workflow.paused", "correlation_41", { event_id: 41, project_id: "project_demo" });
    hook.emit("workflow.resumed", "correlation_45", { event_id: 45, project_id: "project_demo" });
    hook.emit("workflow.resumed", "correlation_45", { event_id: 45, project_id: "project_demo" });
  });

  await expect(page.getByText("event #45")).toHaveCount(1);
  await expect(page.getByText("event #41")).toHaveCount(1);
  const rendererText = await page.locator("html").innerText();
  expect(rendererText).not.toMatch(/websocket ticket|authorization|bearer/i);
});
