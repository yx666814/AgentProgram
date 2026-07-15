import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { expect, it } from "vitest";

import { AppShell } from "../../../src/app/app-shell";
import { ThemeProvider } from "../../../src/theme/theme-provider";

function renderShell(route: string) {
  render(
    <ThemeProvider>
      <MemoryRouter initialEntries={[route]}>
        <Routes>
          <Route element={<AppShell />}>
            <Route path="*" element={<div>页面内容</div>} />
          </Route>
        </Routes>
      </MemoryRouter>
    </ThemeProvider>,
  );
}

it.each(["/projects", "/projects/p1", "/diagnostics"])("shows settings on %s", (route) => {
  renderShell(route);
  expect(screen.getByRole("link", { name: "设置" })).toBeVisible();
});

it("keeps all five stages visible but locked without an active workflow", () => {
  renderShell("/projects");
  for (const stage of ["Planner", "Designer", "Builder", "Reviewer", "Deployer"]) {
    expect(screen.getByText(stage).closest("[aria-disabled='true']")).not.toBeNull();
  }
});
