import type { Stage, Task } from "../../src/api/backend-api";
import type { components } from "../../src/api/generated";
import { createFakeDesktopPort, reply, type FakeDesktopPort } from "./fake-desktop-port";
import { projectRegistration, workflowSnapshot } from "./fixtures";

export type StageRunState = components["schemas"]["StageRunState"];

export interface StagePortState {
  messages: components["schemas"]["Message"][];
  tasks: Task[];
}

export function stageSnapshot(
  stage: Stage,
  state: StageRunState = "discussing",
  roomStatus: components["schemas"]["RoomStatus"] = "active",
) {
  const snapshot = workflowSnapshot("running", 2);
  return {
    ...snapshot,
    workflow: { ...snapshot.workflow, current_stage: stage },
    stage_runs: snapshot.stage_runs.map((run) =>
      run.stage === stage
        ? {
            ...run,
            state,
            ...(state === "completed"
              ? { started_at: "2026-07-15T08:00:00Z", completed_at: "2026-07-15T08:10:00Z" }
              : {}),
          }
        : run,
    ),
    rooms: snapshot.rooms.map((room) =>
      room.stage === stage ? { ...room, status: roomStatus } : room,
    ),
  };
}

export function createStagePort(
  stage: Stage,
  state: StageRunState = "discussing",
  roomStatus: components["schemas"]["RoomStatus"] = "active",
  data: StagePortState = { messages: [], tasks: [] },
  command?: NonNullable<Parameters<typeof createFakeDesktopPort>[0]>["command"],
): { port: FakeDesktopPort; snapshot: ReturnType<typeof stageSnapshot>; data: StagePortState } {
  const snapshot = stageSnapshot(stage, state, roomStatus);
  const port = createFakeDesktopPort({
    ...(command !== undefined ? { command } : {}),
    query(request) {
      switch (request.operationId) {
        case "get_project_api_v1_projects__project_id__get":
          return reply(request, projectRegistration("ready", 2));
        case "list_workflows_api_v1_projects__project_id__workflows_get":
          return reply(request, { workflows: [snapshot.workflow] });
        case "get_workflow_api_v1_workflows__workflow_id__get":
          return reply(request, snapshot);
        case "list_messages_api_v1_rooms__room_id__messages_get":
          return reply(request, { messages: data.messages });
        case "list_tasks_api_v1_workflows__workflow_id__tasks_get":
          return reply(request, { tasks: data.tasks });
        case "list_tool_calls_api_v1_workflows__workflow_id__tool_calls_get":
          return reply(request, { calls: [] });
        case "list_agent_runs_api_v1_rooms__room_id__agent_runs_get":
          return reply(request, { runs: [] });
        case "get_room_assignment_api_v1_rooms__room_id__model_assignment_get":
          return reply(request, {
            schema_version: 1,
            room_id: `room_${stage}`,
            primary_profile_id: "profile_primary",
            reviewer_a_profile_id: null,
            reviewer_b_profile_id: null,
            version: 1,
            updated_at: "2026-07-15T08:00:00Z",
          });
        default:
          throw new Error(`Unexpected query ${request.operationId}`);
      }
    },
  });
  return { port, snapshot, data };
}

export function taskFixture(
  id: string,
  roomId: string,
  status: Task["status"] = "queued",
  version = 1,
): Task {
  return {
    schema_version: 1,
    id,
    workflow_id: "workflow_demo",
    stage_run_id: roomId.replace("room_", "stagerun_"),
    room_id: roomId,
    title: `任务 ${id}`,
    status,
    payload: {},
    version,
    created_at: "2026-07-15T08:00:00Z",
  };
}
