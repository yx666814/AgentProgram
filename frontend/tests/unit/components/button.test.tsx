import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";

import { Button } from "../../../src/components/button";

it("keeps a visible disabled reason", () => {
  render(
    <Button disabled disabledReason="等待 SettingsQuery">
      保存设置
    </Button>,
  );

  const button = screen.getByRole("button", { name: "保存设置" });
  const reason = screen.getByText("等待 SettingsQuery");
  expect(button).toBeDisabled();
  expect(reason).toBeVisible();
  expect(button).toHaveAttribute("aria-describedby", reason.id);
});

it("does not turn a disabled control into a clickable placeholder", async () => {
  const onClick = vi.fn();
  const user = userEvent.setup();
  render(
    <Button disabled disabledReason="后端能力不可用" onClick={onClick}>
      执行
    </Button>,
  );

  await user.click(screen.getByRole("button", { name: "执行" }));
  expect(onClick).not.toHaveBeenCalled();
});

it("uses a stable tone attribute without changing button semantics", () => {
  render(<Button tone="danger">放弃工作流</Button>);
  expect(screen.getByRole("button", { name: "放弃工作流" })).toHaveAttribute(
    "data-tone",
    "danger",
  );
});
