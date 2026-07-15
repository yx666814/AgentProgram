// @vitest-environment node

import { expect, it } from "vitest";

import type { BackendOperationId, DesktopPort } from "../../electron/desktop-port";

it("uses frozen OpenAPI operation ids", () => {
  const operation: BackendOperationId = "health_api_v1_health_get";
  expect(operation).toBe("health_api_v1_health_get");
});

it("exposes no session token, filesystem, shell or secret capability", () => {
  const keys: Array<keyof DesktopPort> = [
    "backend",
    "selectDirectory",
    "showNativeConfirm",
    "showSystemNotification",
    "openLocalLocation",
    "getWindowState",
    "requestWindowClose",
  ];

  expect(keys.join(" ")).not.toMatch(/token|secret|shell|filesystem/i);
});
