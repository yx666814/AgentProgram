import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { expect, it } from "vitest";

import { BackendProvider } from "../../../src/api/backend-context";
import { StartupPage } from "../../../src/features/startup/startup-page";
import { createFakeDesktopPort, reply } from "../../support/fake-desktop-port";

function renderStartup(readinessStatus = 200) {
  const port = createFakeDesktopPort({
    query(request) {
      switch (request.operationId) {
        case "health_api_v1_health_get":
          return reply(request, { status: "ok" });
        case "readiness_api_v1_readiness_get":
          return readinessStatus === 200
            ? reply(request, { status: "ready", database: "ready" })
            : reply(
                request,
                {
                  error: {
                    code: "readiness.unavailable",
                    message: "Service not ready",
                    retryable: true,
                    details: {},
                  },
                },
                503,
              );
        case "system_info_api_v1_system_info_get":
          return reply(request, { backend_version: "1.0.0", protocol_version: 1 });
        case "list_recoveries_api_v1_recovery_get":
          return reply(request, { recoveries: [] });
        default:
          throw new Error(`Unexpected query ${request.operationId}`);
      }
    },
  });
  render(
    <BackendProvider port={port}>
      <MemoryRouter>
        <StartupPage />
      </MemoryRouter>
    </BackendProvider>,
  );
  return port;
}

it("renders the three real startup endpoints and enables project entry only when ready", async () => {
  renderStartup();
  expect(await screen.findByText("protocol 1")).toBeVisible();
  expect(screen.getByText("1.0.0")).toBeVisible();
  expect(screen.getByRole("button", { name: "进入项目" })).toBeEnabled();
});

it("keeps project entry disabled and exposes the backend readiness code on 503", async () => {
  renderStartup(503);
  expect(await screen.findByText("readiness.unavailable")).toBeVisible();
  expect(screen.getByRole("button", { name: "进入项目" })).toBeDisabled();
});
