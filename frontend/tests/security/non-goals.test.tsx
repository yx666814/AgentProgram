import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { expect, it } from "vitest";

import { AppShell } from "../../src/app/app-shell";
import { ThemeProvider } from "../../src/theme/theme-provider";

it("contains no V1 non-goal navigation", () => {
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

  expect(screen.queryByText(/Git|插件市场|团队|组织|云端|计费|DAG|生产部署/)).not.toBeInTheDocument();
});
