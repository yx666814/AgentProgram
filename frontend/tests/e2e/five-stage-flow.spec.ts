import { expect, test } from "@playwright/test";

import { installDesktopFixture } from "./support/desktop-fixture";

test.beforeEach(async ({ page }) => {
  await installDesktopFixture(page);
});

test("walks the project and all five stage renderer views", async ({ page }) => {
  await page.goto("/projects");
  await expect(page.getByText("示例项目", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "打开" }).click();
  await expect(page).toHaveURL(/\/projects\/project_demo$/);
  await expect(page.getByRole("heading", { name: "示例项目" })).toBeVisible();

  for (const stage of ["planner", "designer", "builder", "reviewer", "deployer"] as const) {
    await page.goto(`/projects/project_demo/stages/${stage}`);
    await expect(page.getByTestId("stage-workspace")).toHaveAttribute("data-stage", stage);
    await expect(page.getByText("已读取 StageContract，等待下一项明确任务。")).toBeVisible();
    await expect(page.getByText("核对阶段交付")).toBeVisible();
  }

  await page.goto("/projects/project_demo/artifacts");
  await expect(page.getByRole("heading", { name: "产出、Gate 与交接" })).toBeVisible();
  await page.goto("/projects/project_demo/approvals");
  await expect(page.getByRole("heading", { name: "审批、能力与风险" })).toBeVisible();
  await page.goto("/projects/project_demo/recovery");
  await expect(page.getByRole("heading", { name: "冲突、检查点与恢复" })).toBeVisible();
});

test("sends a room message through the DesktopPort and waits for message.appended", async ({ page }) => {
  await page.goto("/projects/project_demo/stages/planner");
  await page.getByLabel("阶段消息").fill("请继续核对契约");
  await page.getByRole("button", { name: "发送" }).click();
  await expect(page.getByText(/等待 message\.appended/)).toBeHidden();
  const commandIds = await page.evaluate(() => (Reflect.get(window, "__desktopTest") as { calls: { commands: Array<{ operationId: string }> } }).calls.commands.map(({ operationId }) => operationId));
  expect(commandIds).toContain("append_message_api_v1_rooms__room_id__messages_post");
});
