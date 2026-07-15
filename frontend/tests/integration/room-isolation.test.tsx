import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { expect, it } from "vitest";

import { BackendProvider } from "../../src/api/backend-context";
import { StageWorkspacePage } from "../../src/features/stages/stage-workspace-page";
import { reply } from "../support/fake-desktop-port";
import { createStagePort, type StagePortState } from "../support/stage-fixtures";

it("queries only the selected Room and creates an immutable correction record", async () => {
  const user = userEvent.setup();
  const original = {
    schema_version: 1 as const,
    id: "message_designer",
    room_id: "room_designer",
    sequence: 1,
    author: "user" as const,
    kind: "discussion" as const,
    content: "Designer 专属消息",
    correction_of_id: null,
    created_at: "2026-07-15T08:00:00Z",
  };
  const data: StagePortState = { messages: [original], tasks: [] };
  const corrected = {
    ...original,
    id: "message_correction",
    sequence: 2,
    kind: "correction" as const,
    content: "更正后的设计说明",
    correction_of_id: original.id,
  };
  const { port } = createStagePort("designer", "discussing", "active", data, (request) => {
    if (request.operationId === "append_message_api_v1_rooms__room_id__messages_post") {
      data.messages = [original, corrected];
      return reply(request, {
        message: corrected,
        room: {
          schema_version: 1,
          id: "room_designer",
          workflow_id: "workflow_demo",
          stage_run_id: "stagerun_designer",
          stage: "designer",
          status: "active",
          next_sequence: 3,
          version: 2,
          created_at: "2026-07-15T08:00:00Z",
          updated_at: "2026-07-15T08:01:00Z",
        },
      }, 201);
    }
    throw new Error(`Unexpected command ${request.operationId}`);
  });

  render(
    <BackendProvider port={port}>
      <MemoryRouter initialEntries={["/projects/project_demo/stages/designer"]}>
        <Routes>
          <Route path="/projects/:projectId/stages/:stage" element={<StageWorkspacePage />} />
        </Routes>
      </MemoryRouter>
    </BackendProvider>,
  );

  expect(await screen.findByText("Designer 专属消息")).toBeVisible();
  expect(screen.queryByText("Planner 专属消息")).not.toBeInTheDocument();
  const messageQuery = port.calls.queries.find(
    ({ operationId }) => operationId === "list_messages_api_v1_rooms__room_id__messages_get",
  );
  expect(messageQuery?.parameters).toMatchObject({ path: { room_id: "room_designer" } });
  expect(screen.queryByRole("button", { name: /编辑|删除/ })).not.toBeInTheDocument();

  await user.click(screen.getByRole("button", { name: "更正此消息" }));
  await user.type(screen.getByLabelText("阶段消息"), corrected.content);
  await user.click(screen.getByRole("button", { name: "发送" }));
  expect(screen.getByText(/等待 message\.appended/)).toBeVisible();
  expect(port.calls.commands[0]?.payload).toMatchObject({ correction_of_id: original.id });

  port.emit({
    schema_version: 1,
    event_id: 10,
    event_type: "message.appended",
    correlation_id: "correlation_message",
    actor: { type: "user", id: "user_local" },
    source: "backend",
    occurred_at: "2026-07-15T08:01:00Z",
    project_id: "project_demo",
    workflow_id: "workflow_demo",
    room_id: "room_designer",
    payload: { message_id: corrected.id, sequence: 2, kind: "correction" },
  });
  expect(await screen.findByText(corrected.content)).toBeVisible();
});
