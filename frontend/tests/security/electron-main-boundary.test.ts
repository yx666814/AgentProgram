// @vitest-environment node

import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { expect, it } from "vitest";

it("keeps Electron Main on the frozen local desktop boundary", () => {
  const main = readFileSync(resolve(process.cwd(), "electron/main.ts"), "utf8");
  const sidecar = readFileSync(resolve(process.cwd(), "electron/sidecar.ts"), "utf8");
  const indexBuild = readFileSync(resolve(process.cwd(), "vite.config.ts"), "utf8");

  expect(main).toMatch(/contextIsolation:\s*true/u);
  expect(main).toMatch(/nodeIntegration:\s*false/u);
  expect(main).toMatch(/sandbox:\s*true/u);
  expect(main).toContain('setWindowOpenHandler(() => ({ action: "deny" }))');
  expect(main).toContain("setPermissionRequestHandler");
  expect(main).toContain("setPermissionCheckHandler");
  expect(sidecar).toContain('port: 0');
  expect(sidecar).toContain("child.stdin.end(startupFrame");
  expect(sidecar).not.toMatch(/AGENT_PLATFORM_SESSION_TOKEN/u);
  expect(indexBuild).toContain("connect-src 'none'");
});
