import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { expect, it } from "vitest";

import { AppShell } from "../../src/app/app-shell";
import { ThemeProvider } from "../../src/theme/theme-provider";

it("exposes only pure navigation when no project context exists", () => {
  render(
    <ThemeProvider>
      <MemoryRouter initialEntries={["/projects"]}>
        <Routes>
          <Route element={<AppShell />}>
            <Route path="*" element={<div />} />
          </Route>
        </Routes>
      </MemoryRouter>
    </ThemeProvider>,
  );

  expect(screen.getByRole("link", { name: "项目" })).toHaveAttribute("href", "/projects");
  expect(screen.getByRole("link", { name: "事件与诊断" })).toHaveAttribute(
    "href",
    "/diagnostics",
  );
  expect(screen.getByRole("link", { name: "设置" })).toHaveAttribute("href", "/settings");
  expect(screen.queryByRole("button", { name: /开始|暂停|停止|审批|恢复/ })).not.toBeInTheDocument();
});
