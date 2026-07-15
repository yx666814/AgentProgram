import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { expect, it } from "vitest";

import { BackendProvider } from "../../src/api/backend-context";
import { RecoveryPage } from "../../src/features/recovery/recovery-page";
import { createFakeDesktopPort, reply } from "../support/fake-desktop-port";
import { checkpointFixture } from "../support/governance-fixtures";
import { projectRegistration } from "../support/fixtures";

it("does not send restore when the native confirmation is cancelled", async () => {
  const user = userEvent.setup();
  const checkpoint = checkpointFixture();
  const protection = checkpointFixture("checkpoint_protection");
  const port = createFakeDesktopPort({
    confirmResult: false,
    query(request) {
      switch (request.operationId) {
        case "get_project_api_v1_projects__project_id__get": return reply(request, projectRegistration("ready", 3));
        case "list_conflicts_api_v1_projects__project_id__conflicts_get": return reply(request, { conflicts: [] });
        case "list_checkpoints_api_v1_projects__project_id__checkpoints_get": return reply(request, { checkpoints: [checkpoint] });
        case "list_external_changes_api_v1_projects__project_id__external_changes_get": return reply(request, { changes: [] });
        default: throw new Error(`Unexpected query ${request.operationId}`);
      }
    },
    command(request) {
      if (request.operationId === "plan_restore_api_v1_projects__project_id__checkpoints__checkpoint_id__restore_plan_post") {
        return reply(request, { plan: { schema_version: 1, target_checkpoint_id: checkpoint.id, current_checkpoint_id: protection.id, overwrite_paths: ["src/app.ts"], preserved_extra_paths: [] }, protection_checkpoint: protection });
      }
      throw new Error(`Unexpected command ${request.operationId}`);
    },
  });
  render(<BackendProvider port={port}><MemoryRouter initialEntries={["/projects/project_demo/recovery"]}><Routes><Route path="/projects/:projectId/recovery" element={<RecoveryPage />} /></Routes></MemoryRouter></BackendProvider>);
  await user.click(await screen.findByRole("button", { name: "规划并恢复" }));
  expect(port.calls.commands.map(({ operationId }) => operationId)).toEqual([
    "plan_restore_api_v1_projects__project_id__checkpoints__checkpoint_id__restore_plan_post",
  ]);
  expect(screen.getByText(/保护检查点 checkpoint_protection/)).toBeVisible();
});
