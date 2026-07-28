import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { expect, it } from "vitest";

import { BackendProvider } from "../../src/api/backend-context";
import { ProjectOverviewPage } from "../../src/features/overview/project-overview-page";
import { PreflightPage } from "../../src/features/preflight/preflight-page";
import { ProjectsPage } from "../../src/features/projects/projects-page";
import { createFakeDesktopPort, reply } from "../support/fake-desktop-port";
import {
  preflightResult,
  projectManifest,
  projectRegistration,
  workflowSnapshot,
} from "../support/fixtures";

it("creates a project with the selected directory and enters preflight", async () => {
  const user = userEvent.setup();
  const registration = projectRegistration();
  const port = createFakeDesktopPort({
    directory: { cancelled: false, path: "D:\\Work\\demo" },
    query(request) {
      if (request.operationId === "list_projects_api_v1_projects_get") {
        return reply(request, { projects: [] });
      }
      throw new Error(`Unexpected query ${request.operationId}`);
    },
    command(request) {
      if (request.operationId === "create_project_api_v1_projects_post") {
        return reply(request, {
          registration,
          manifest: projectManifest(),
          preflight_required: true,
        }, 201);
      }
      throw new Error(`Unexpected command ${request.operationId}`);
    },
  });

  render(
    <BackendProvider port={port}>
      <MemoryRouter initialEntries={["/projects"]}>
        <Routes>
          <Route path="/projects" element={<ProjectsPage />} />
          <Route path="/projects/:projectId/preflight" element={<div>已进入项目预检</div>} />
        </Routes>
      </MemoryRouter>
    </BackendProvider>,
  );

  await screen.findByText("还没有已注册项目。");
  await user.type(screen.getByLabelText("项目名称"), "示例项目");
  await user.type(screen.getByLabelText("项目目标"), "验证真实项目主线");
  await user.click(screen.getByRole("button", { name: "选择目录" }));
  await user.click(screen.getByRole("radio", { name: /Direct/ }));
  await user.click(screen.getByRole("button", { name: "创建并预检" }));

  expect(await screen.findByText("已进入项目预检")).toBeVisible();
  const createCall = port.calls.commands.find(
    ({ operationId }) => operationId === "create_project_api_v1_projects_post",
  );
  expect(createCall?.payload).toMatchObject({
    local_working_directory: "D:\\Work\\demo",
    workspace_mode: "direct",
  });
});

it("requires explicit warning acknowledgement before creating and starting a workflow", async () => {
  const user = userEvent.setup();
  const registration = projectRegistration("ready", 2);
  const warning = preflightResult("warning");
  const created = workflowSnapshot("created", 1);
  const started = workflowSnapshot("running", 2);
  const port = createFakeDesktopPort({
    query(request) {
      switch (request.operationId) {
        case "get_project_api_v1_projects__project_id__get":
          return reply(request, registration);
        case "list_workflows_api_v1_projects__project_id__workflows_get":
          return reply(request, { workflows: [] });
        case "get_preflight_api_v1_projects__project_id__preflight_get":
          return reply(request, warning);
        default:
          throw new Error(`Unexpected query ${request.operationId}`);
      }
    },
    command(request) {
      if (request.operationId === "create_workflow_api_v1_projects__project_id__workflows_post") {
        return reply(request, created, 201);
      }
      if (request.operationId === "start_workflow_api_v1_workflows__workflow_id__start_post") {
        return reply(request, started);
      }
      throw new Error(`Unexpected command ${request.operationId}`);
    },
  });

  render(
    <BackendProvider port={port}>
      <MemoryRouter initialEntries={["/projects/project_demo/preflight"]}>
        <Routes>
          <Route path="/projects/:projectId/preflight" element={<PreflightPage />} />
          <Route path="/projects/:projectId" element={<div>已进入项目主页</div>} />
        </Routes>
      </MemoryRouter>
    </BackendProvider>,
  );

  const startButton = await screen.findByRole("button", { name: "创建并开始工作流" });
  expect(startButton).toBeDisabled();
  await user.click(screen.getByRole("checkbox"));
  expect(startButton).toBeEnabled();
  await user.click(startButton);

  expect(await screen.findByText("已进入项目主页")).toBeVisible();
  expect(port.calls.commands.map(({ operationId }) => operationId)).toEqual([
    "create_workflow_api_v1_projects__project_id__workflows_post",
    "start_workflow_api_v1_workflows__workflow_id__start_post",
  ]);
});

it("changes the workflow execution mode through the project overview", async () => {
  const user = userEvent.setup();
  const registration = projectRegistration("ready", 3);
  let current = workflowSnapshot("running", 2);
  const port = createFakeDesktopPort({
    query(request) {
      switch (request.operationId) {
        case "get_project_api_v1_projects__project_id__get":
          return reply(request, registration);
        case "list_workflows_api_v1_projects__project_id__workflows_get":
          return reply(request, { workflows: [current.workflow] });
        case "get_workflow_api_v1_workflows__workflow_id__get":
          return reply(request, current);
        default:
          throw new Error(`Unexpected query ${request.operationId}`);
      }
    },
    command(request) {
      if (request.operationId !== "set_workflow_mode_api_v1_workflows__workflow_id__mode_post") {
        throw new Error(`Unexpected command ${request.operationId}`);
      }
      current = {
        ...current,
        workflow: { ...current.workflow, execution_mode: "autonomous", version: 3 },
      };
      return reply(request, current.workflow);
    },
  });

  render(
    <BackendProvider port={port}>
      <MemoryRouter initialEntries={["/projects/project_demo"]}>
        <Routes>
          <Route path="/projects/:projectId" element={<ProjectOverviewPage />} />
        </Routes>
      </MemoryRouter>
    </BackendProvider>,
  );

  const mode = await screen.findByRole("group", { name: "执行模式" });
  const autonomous = screen.getByRole("button", { name: "Autonomous" });
  expect(mode).toContainElement(autonomous);
  expect(autonomous).toHaveAttribute("aria-pressed", "false");
  await user.click(autonomous);
  expect(autonomous).toHaveAttribute("aria-pressed", "true");
  expect(port.calls.commands[0]).toMatchObject({
    operationId: "set_workflow_mode_api_v1_workflows__workflow_id__mode_post",
    parameters: { path: { workflow_id: "workflow_demo" } },
    payload: { mode: "autonomous", expected_version: 2 },
  });
});
