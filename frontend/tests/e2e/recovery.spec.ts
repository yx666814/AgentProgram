import { expect, test } from "@playwright/test";

import { installDesktopFixture } from "./support/desktop-fixture";

test("plans a protection checkpoint before restore and waits for the persisted restore event", async ({ page }) => {
  await installDesktopFixture(page);
  await page.goto("/projects/project_demo/recovery");
  await page.getByRole("button", { name: "规划并恢复" }).click();
  await expect(page.getByText(/等待 project\.checkpoint_restored/)).toBeVisible();
  const evidence = page.locator(".restore-evidence");
  await expect(evidence).toContainText("checkpoint_protection");

  const calls = await page.evaluate(() => (Reflect.get(window, "__desktopTest") as { calls: { commands: Array<{ operationId: string }>; confirms: unknown[] } }).calls);
  expect(calls.commands.map(({ operationId }) => operationId)).toEqual([
    "plan_restore_api_v1_projects__project_id__checkpoints__checkpoint_id__restore_plan_post",
    "restore_checkpoint_api_v1_projects__project_id__checkpoints__checkpoint_id__restore_post",
  ]);
  expect(calls.confirms).toHaveLength(1);
  await page.evaluate(() => {
    const hook = Reflect.get(window, "__desktopTest") as { emit: (type: string, correlation: string, extra: Record<string, unknown>) => void };
    hook.emit("project.checkpoint_restored", "correlation_restore", { payload: { checkpoint_id: "checkpoint_demo" }, project_id: "project_demo" });
  });
  await expect(page.getByText(/等待 project\.checkpoint_restored/)).toBeHidden();
});
