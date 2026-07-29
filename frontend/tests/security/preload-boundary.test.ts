// @vitest-environment node

import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { expect, it } from "vitest";

it("keeps the preload bridge on the explicit DesktopPort boundary", () => {
  const source = readFileSync(resolve(process.cwd(), "electron/preload.ts"), "utf8");

  expect(source).toContain('contextBridge.exposeInMainWorld("desktop"');
  expect(source).toContain("ipcRenderer.invoke(IPC_CHANNELS.");
  expect(source).toContain("ipcRenderer.on(IPC_CHANNELS.backendEvent");
  expect(source).toContain("ipcRenderer.on(IPC_CHANNELS.backendStreamFrame");
  expect(source).not.toMatch(/ipcRenderer\.(?:send|sendSync|postMessage)|node:fs|child_process|process\.env|session.?token/i);
  expect(source).not.toMatch(/exposeInMainWorld\([^,]+,\s*ipcRenderer/u);
});
