import { contextBridge } from "electron";

import type { DesktopPort } from "./desktop-port";

export function exposeDesktopPort(port: DesktopPort): void {
  contextBridge.exposeInMainWorld("desktop", Object.freeze(port));
}
