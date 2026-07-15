import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it } from "vitest";

import { ThemeProvider, useTheme } from "../../src/theme/theme-provider";

function ThemeProbe() {
  const { theme, toggleTheme } = useTheme();
  return <button onClick={toggleTheme}>{theme}</button>;
}

it("switches only between the locked light and dark themes", async () => {
  const user = userEvent.setup();
  render(
    <ThemeProvider initialTheme="dark">
      <ThemeProbe />
    </ThemeProvider>,
  );

  expect(document.documentElement).toHaveAttribute("data-theme", "dark");
  await user.click(screen.getByRole("button", { name: "dark" }));
  expect(document.documentElement).toHaveAttribute("data-theme", "light");
});
