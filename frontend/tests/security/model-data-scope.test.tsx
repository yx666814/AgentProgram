import { render, screen } from "@testing-library/react";
import { expect, it } from "vitest";

import { BackendProvider } from "../../src/api/backend-context";
import { SettingsPage } from "../../src/features/settings/settings-page";
import { createFakeDesktopPort, reply } from "../support/fake-desktop-port";
import { modelProfile } from "../support/settings-diagnostics-fixtures";

it("renders only credential references and masked hints", async () => {
  const profile = modelProfile();
  const port = createFakeDesktopPort({
    query(request) {
      if (request.operationId === "system_info_api_v1_system_info_get") {
        return reply(request, { backend_version: "0.1.0", protocol_version: 1 });
      }
      if (request.operationId === "list_profiles_api_v1_model_profiles_get") {
        return reply(request, { profiles: [profile] });
      }
      throw new Error(`Unexpected query ${request.operationId}`);
    },
  });

  render(<BackendProvider port={port}><SettingsPage /></BackendProvider>);
  expect(await screen.findByText(profile.credential_ref)).toBeVisible();
  expect(screen.getByText(profile.masked_hint)).toBeVisible();
  expect(screen.queryByLabelText(/API Key|Secret|密钥/i)).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "测试连接" })).toBeDisabled();
});
