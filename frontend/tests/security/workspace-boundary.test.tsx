import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { expect, it } from "vitest";

import { BackendProvider } from "../../src/api/backend-context";
import { ProjectOverviewPage } from "../../src/features/overview/project-overview-page";
import { createFakeDesktopPort, reply } from "../support/fake-desktop-port";
import { projectRegistration, workflowSnapshot } from "../support/fixtures";

it("closes a Direct Workspace through the backend without implying file deletion", async () => {
  const user = userEvent.setup();
  const registration = projectRegistration("ready", 3);
  const snapshot = workflowSnapshot("running", 2);
  const port = createFakeDesktopPort({
    confirmResult: true,
    query(request) {
      switch (request.operationId) {
        case "get_project_api_v1_projects__project_id__get":
          return reply(request, registration);
        case "list_workflows_api_v1_projects__project_id__workflows_get":
          return reply(request, { workflows: [snapshot.workflow] });
        case "get_workflow_api_v1_workflows__workflow_id__get":
          return reply(request, snapshot);
        default:
          throw new Error(`Unexpected query ${request.operationId}`);
      }
    },
    command(request) {
      if (request.operationId === "close_project_api_v1_projects__project_id__close_post") {
        return reply(request, { project: { ...registration.project, status: "closed", version: 4 } });
      }
      throw new Error(`Unexpected command ${request.operationId}`);
    },
  });

  render(
    <BackendProvider port={port}>
      <MemoryRouter initialEntries={["/projects/project_demo"]}>
        <Routes>
          <Route path="/projects/:projectId" element={<ProjectOverviewPage />} />
          <Route path="/projects" element={<div>项目列表</div>} />
        </Routes>
      </MemoryRouter>
    </BackendProvider>,
  );

  await user.click(await screen.findByRole("button", { name: "关闭项目" }));
  expect(await screen.findByText("项目列表")).toBeVisible();
  expect(port.calls.confirms[0]?.detail).toContain("不会被删除");
  expect(port.calls.commands[0]).toMatchObject({
    operationId: "close_project_api_v1_projects__project_id__close_post",
    parameters: { path: { project_id: "project_demo" } },
  });
});
