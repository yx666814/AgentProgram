import { render, screen } from "@testing-library/react";
import { expect, it } from "vitest";

import { SettingsPage } from "../../../src/features/settings/settings-page";

it("shows a truthful unavailable state without a fake settings form", () => {
  render(<SettingsPage />);

  expect(screen.getByText("星协")).toBeVisible();
  expect(screen.getByText("可通过 system/info 读取")).toBeVisible();
  expect(screen.getByText("后端未提供 SettingsQuery 或设置写入接口")).toBeVisible();
  expect(screen.getByRole("button", { name: "保存设置" })).toBeDisabled();
  expect(screen.queryByLabelText(/API Key|密钥|Secret/i)).not.toBeInTheDocument();
});
