// @vitest-environment node

import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, resolve } from "node:path";

import { expect, it } from "vitest";

function sourceFiles(root: string): string[] {
  return readdirSync(root).flatMap((entry) => {
    const path = join(root, entry);
    return statSync(path).isDirectory() ? sourceFiles(path) : /\.(?:ts|tsx)$/.test(path) ? [path] : [];
  });
}

it("keeps test fakes, Node capabilities and authentication material out of production renderer sources", () => {
  const files = [...sourceFiles(resolve(process.cwd(), "src")), ...sourceFiles(resolve(process.cwd(), "electron"))];
  const source = files.map((path) => readFileSync(path, "utf8")).join("\n");
  expect(source).not.toMatch(/from\s+["']node:|child_process|ipcRenderer|process\.env/);
  expect(source).not.toMatch(/createFakeDesktopPort|settings-diagnostics-fixtures|governance-fixtures|stage-fixtures|mockServiceWorker/);
  expect(source).not.toMatch(/Authorization\s*:|Bearer\s+[A-Za-z0-9]|session[_-]?token\s*[:=]/i);
});
