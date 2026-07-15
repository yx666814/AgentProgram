import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { expect, it } from "vitest";

import type { Stage } from "../../src/api/backend-api";
import { BackendProvider } from "../../src/api/backend-context";
import { StageWorkspacePage } from "../../src/features/stages/stage-workspace-page";
import { createStagePort } from "../support/stage-fixtures";

function renderPermissionStage(stage: Stage, state: "discussing" | "locked" | "completed" = "discussing") {
  const roomStatus = state === "completed" ? "consultation" : "active";
  const { port } = createStagePort(stage, state, roomStatus);
  render(
    <BackendProvider port={port}>
      <MemoryRouter initialEntries={[`/projects/project_demo/stages/${stage}`]}>
        <Routes>
          <Route path="/projects/:projectId/stages/:stage" element={<StageWorkspacePage />} />
        </Routes>
      </MemoryRouter>
    </BackendProvider>,
  );
}

it("shows only the selected StageContract capabilities", async () => {
  renderPermissionStage("planner");
  await screen.findByTestId("stage-workspace");
  expect(screen.getAllByText("filesystem.write_planner_artifact").length).toBeGreaterThan(0);
  expect(screen.queryByText("filesystem.write_source")).not.toBeInTheDocument();
});

it("keeps locked stages non-writable", async () => {
  renderPermissionStage("designer", "locked");
  await screen.findByTestId("stage-workspace");
  expect(screen.getByLabelText("阶段消息")).toBeDisabled();
  expect(screen.getByRole("button", { name: "加入队列" })).toBeDisabled();
});

it("separates completed-stage consultation from the explicit reopen action", async () => {
  renderPermissionStage("planner", "completed");
  await screen.findByTestId("stage-workspace");
  expect(screen.getByLabelText("阶段消息")).toBeEnabled();
  expect(screen.getByRole("button", { name: "加入队列" })).toBeDisabled();
  expect(screen.getByRole("button", { name: "重新打开" })).toBeVisible();
});
