import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { expect, it } from "vitest";

import type { Stage } from "../../src/api/backend-api";
import { BackendProvider } from "../../src/api/backend-context";
import { StageWorkspacePage } from "../../src/features/stages/stage-workspace-page";
import { createStagePort, taskFixture } from "../support/stage-fixtures";

function renderStage(stage: Stage) {
  const data = { messages: [], tasks: [
    taskFixture("task_one", `room_${stage}`),
    taskFixture("task_two", `room_${stage}`),
  ] };
  const { port } = createStagePort(stage, "discussing", "active", data);
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

it.each(["planner", "designer", "builder", "reviewer", "deployer"] as const)(
  "renders %s from the backend Stage enum",
  async (stage) => {
    renderStage(stage);
    expect(await screen.findByTestId("stage-workspace")).toHaveAttribute("data-stage", stage);
    expect(screen.getByText(/队列 1/)).toBeVisible();
    expect(screen.getByText(/队列 2/)).toBeVisible();
  },
);
