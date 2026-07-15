import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { expect, test } from "@playwright/test";

const tokens = readFileSync(resolve(process.cwd(), "src/theme/tokens.css"), "utf8");
const interaction = readFileSync(resolve(process.cwd(), "src/theme/interaction.css"), "utf8");

for (const theme of ["light", "dark"] as const) {
  test(`${theme} theme keeps the soft desktop interaction`, async ({ page }) => {
    await page.setContent(`
      <style>
        ${tokens}
        ${interaction}
        * { box-sizing: border-box; }
        body {
          margin: 0;
          padding: 48px;
          background: var(--surface-app);
          color: var(--text-primary);
          font-family: var(--font-ui);
        }
        .panel {
          width: 560px;
          padding: 28px;
          border: 1px solid var(--border-default);
          border-radius: var(--radius-panel);
          background: var(--surface-panel);
          box-shadow: var(--shadow-panel);
        }
        .actions { display: flex; align-items: flex-start; gap: 12px; margin-top: 24px; }
      </style>
      <body data-theme="${theme}">
        <main class="panel">
          <h1>星协</h1>
          <p>柔和、克制的 Windows 桌面交互。</p>
          <div class="actions">
            <button class="button" data-tone="primary">继续</button>
            <button class="button">查看证据</button>
            <button class="button" data-tone="danger">停止</button>
            <span class="button-field">
              <button class="button" disabled>保存设置</button>
              <span class="button-disabled-reason">等待 SettingsQuery</span>
            </span>
          </div>
        </main>
      </body>
    `);

    const bodyColors = await page.locator("body").evaluate((element) => {
      const style = getComputedStyle(element);
      return { background: style.backgroundColor, color: style.color };
    });
    expect(bodyColors).toEqual(
      theme === "light"
        ? { background: "rgb(246, 248, 249)", color: "rgb(37, 48, 54)" }
        : { background: "rgb(25, 28, 28)", color: "rgb(228, 231, 227)" },
    );
    await expect(page).toHaveScreenshot(`theme-${theme}.png`, { animations: "disabled" });
  });
}

test("interaction CSS contains no scale, gradient, bounce or ripple", () => {
  expect(interaction).not.toMatch(/transform\s*:\s*scale|gradient|bounce|ripple/i);
});
