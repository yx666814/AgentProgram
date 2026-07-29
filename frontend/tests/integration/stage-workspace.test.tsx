import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { expect, it } from "vitest";

import type { Stage } from "../../src/api/backend-api";
import { BackendProvider } from "../../src/api/backend-context";
import { StageWorkspacePage } from "../../src/features/stages/stage-workspace-page";
import { createStagePort, taskFixture } from "../support/stage-fixtures";
import { reply } from "../support/fake-desktop-port";

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

it("runs formal orchestration and renders embedded AgentRun frames", async () => {
  const user = userEvent.setup();
  const run = {
    schema_version: 1 as const,
    id: "agentrun_demo",
    workflow_id: "workflow_demo",
    room_id: "room_planner",
    request_key: "agent-run:integration-demo",
    formal: true,
    status: "succeeded" as const,
    version: 3,
    final_output_ref: "outputs/agentrun_demo.txt",
    final_output_hash: "a".repeat(64),
    final_output_bytes: 18,
    error_code: null,
    created_at: "2026-07-15T08:00:00Z",
    completed_at: "2026-07-15T08:01:00Z",
  };
  const data = {
    messages: [],
    tasks: [],
    agentRuns: [run],
    agentRunOutput: "最终模型输出",
    assignment: {
      schema_version: 1 as const,
      room_id: "room_planner",
      primary_profile_id: "profile_primary",
      reviewer_a_profile_id: "profile_reviewer_a",
      reviewer_b_profile_id: "profile_reviewer_b",
      version: 1,
      updated_at: "2026-07-15T08:00:00Z",
    },
    agentRunSnapshot: {
      schema_version: 1 as const,
      run,
      calls: [
        {
          schema_version: 1 as const,
          id: "modelcall_demo",
          agent_run_id: run.id,
          profile_id: "profile_primary",
          role: "primary" as const,
          phase: "p0" as const,
          status: "succeeded" as const,
          prompt_hash: "b".repeat(64),
          output_ref: "outputs/modelcall_demo.txt",
          output_hash: "c".repeat(64),
          output_bytes: 18,
          error_code: null,
          version: 2,
          started_at: "2026-07-15T08:00:00Z",
          completed_at: "2026-07-15T08:00:30Z",
        },
      ],
      usage: [
        {
          schema_version: 1 as const,
          model_call_id: "modelcall_demo",
          input_tokens: 10,
          output_tokens: 20,
          total_tokens: 30,
          recorded_at: "2026-07-15T08:00:30Z",
        },
      ],
    },
  };
  const { port } = createStagePort(
    "planner",
    "discussing",
    "active",
    data,
    (request) => { throw new Error(`Unexpected command ${request.operationId}`); },
    (request, emit) => {
      const agentBase = {
        run_id: run.id,
        role: null,
        phase: null,
        text: null,
        error_code: null,
        data: {},
      };
      const orchestrationBase = {
        workflow_id: "workflow_demo",
        stage_run_id: "stagerun_planner",
        agent_run_id: run.id,
        task_id: "task_formal",
        text: null,
        error_code: null,
      };
      emit({ ...orchestrationBase, type: "started", sequence: 1, agent_run_id: null, task_id: null, data: { stage: "planner" } });
      emit({ ...orchestrationBase, type: "agent_run_created", sequence: 2, data: { created: true } });
      emit({ ...orchestrationBase, type: "agent_frame", sequence: 3, data: { agent_frame: { ...agentBase, type: "run_started", sequence: 1, status: "running" } } });
      emit({ ...orchestrationBase, type: "agent_frame", sequence: 4, data: { agent_frame: { ...agentBase, type: "call_started", sequence: 2, role: "primary", phase: "p0", status: "streaming" } } });
      emit({ ...orchestrationBase, type: "agent_frame", sequence: 5, data: { agent_frame: { ...agentBase, type: "chunk", sequence: 3, role: "primary", phase: "p0", text: "实时输出", status: "streaming" } } });
      emit({ ...orchestrationBase, type: "completed", sequence: 6, data: { next_action: "approval" } });
      return { requestId: request.requestId, statusCode: 200, payload: null };
    },
  );
  render(
    <BackendProvider port={port}>
      <MemoryRouter initialEntries={["/projects/project_demo/stages/planner"]}>
        <Routes>
          <Route path="/projects/:projectId/stages/:stage" element={<StageWorkspacePage />} />
        </Routes>
      </MemoryRouter>
    </BackendProvider>,
  );

  await user.type(await screen.findByLabelText("AgentRun 指令"), "完成 Planner 正式产出");
  await user.click(screen.getByRole("button", { name: "运行并完成本阶段" }));

  expect(await screen.findByText(/实时输出/)).toBeVisible();
  expect(await screen.findByText("最终模型输出")).toBeVisible();
  expect(screen.getByText("30")).toBeVisible();
  expect(port.calls.streams[0]?.operationId).toBe(
    "orchestrate_workflow_stage_api_v1_workflows__workflow_id__orchestration_stream_post",
  );
});

it("saves the current Room model assignment from the stage workspace", async () => {
  const user = userEvent.setup();
  const assignment = {
    schema_version: 1 as const,
    room_id: "room_planner",
    primary_profile_id: "profile_primary",
    reviewer_a_profile_id: null,
    reviewer_b_profile_id: null,
    version: 3,
    updated_at: "2026-07-15T08:00:00Z",
  };
  const { port } = createStagePort(
    "planner",
    "discussing",
    "active",
    { messages: [], tasks: [], assignment },
    (request) => {
      if (request.operationId !== "assign_room_models_api_v1_rooms__room_id__model_assignment_put") {
        throw new Error(`Unexpected command ${request.operationId}`);
      }
      return reply(request, {
        ...assignment,
        reviewer_a_profile_id: "profile_reviewer_a",
        reviewer_b_profile_id: "profile_reviewer_b",
        version: 4,
      });
    },
  );
  render(
    <BackendProvider port={port}>
      <MemoryRouter initialEntries={["/projects/project_demo/stages/planner"]}>
        <Routes>
          <Route path="/projects/:projectId/stages/:stage" element={<StageWorkspacePage />} />
        </Routes>
      </MemoryRouter>
    </BackendProvider>,
  );

  expect(
    await screen.findAllByRole("option", { name: "reviewer a · fake-reviewer_a" }),
  ).toHaveLength(3);
  await user.selectOptions(screen.getByLabelText("当前阶段 Reviewer A"), "profile_reviewer_a");
  await user.selectOptions(screen.getByLabelText("当前阶段 Reviewer B"), "profile_reviewer_b");
  await user.click(screen.getByRole("button", { name: "保存当前阶段分配" }));

  expect(port.calls.commands[0]).toMatchObject({
    operationId: "assign_room_models_api_v1_rooms__room_id__model_assignment_put",
    parameters: { path: { room_id: "room_planner" } },
    payload: {
      primary_profile_id: "profile_primary",
      reviewer_a_profile_id: "profile_reviewer_a",
      reviewer_b_profile_id: "profile_reviewer_b",
      expected_version: 3,
    },
  });
  expect(await screen.findByText("当前阶段模型分配已保存：room_planner")).toBeVisible();
});

it("cancels an active streamed AgentRun through the backend cancel operation", async () => {
  const user = userEvent.setup();
  let finishStream: (() => void) | undefined;
  const streamFinished = new Promise<void>((resolve) => { finishStream = resolve; });
  const run = {
    schema_version: 1 as const,
    id: "agentrun_cancel",
    workflow_id: "workflow_demo",
    room_id: "room_planner",
    request_key: "agent-run:cancel-demo",
    formal: false,
    status: "cancelled" as const,
    version: 3,
    final_output_ref: null,
    final_output_hash: null,
    final_output_bytes: null,
    error_code: null,
    created_at: "2026-07-15T08:00:00Z",
    completed_at: "2026-07-15T08:01:00Z",
  };
  const data = {
    messages: [],
    tasks: [],
    agentRuns: [run],
    assignment: {
      schema_version: 1 as const,
      room_id: "room_planner",
      primary_profile_id: "profile_primary",
      reviewer_a_profile_id: null,
      reviewer_b_profile_id: null,
      version: 1,
      updated_at: "2026-07-15T08:00:00Z",
    },
    agentRunSnapshot: { schema_version: 1 as const, run, calls: [], usage: [] },
  };
  const { port } = createStagePort(
    "planner",
    "discussing",
    "active",
    data,
    (request) => {
      if (request.operationId === "create_agent_run_api_v1_rooms__room_id__agent_runs_post") {
        return reply(request, { run: { ...run, status: "pending", version: 1 }, created: true });
      }
      if (request.operationId === "cancel_agent_run_api_v1_agent_runs__run_id__cancel_post") {
        finishStream?.();
        return reply(request, { run, cancellation_requested: true });
      }
      throw new Error(`Unexpected command ${request.operationId}`);
    },
    async (request, emit) => {
      emit({
        type: "run_started",
        run_id: run.id,
        sequence: 1,
        role: null,
        phase: null,
        text: null,
        status: "running",
        error_code: null,
        data: {},
      });
      await streamFinished;
      emit({
        type: "run_completed",
        run_id: run.id,
        sequence: 2,
        role: null,
        phase: null,
        text: null,
        status: "cancelled",
        error_code: null,
        data: {},
      });
      return { requestId: request.requestId, statusCode: 200, payload: null };
    },
  );
  render(
    <BackendProvider port={port}>
      <MemoryRouter initialEntries={["/projects/project_demo/stages/planner"]}>
        <Routes>
          <Route path="/projects/:projectId/stages/:stage" element={<StageWorkspacePage />} />
        </Routes>
      </MemoryRouter>
    </BackendProvider>,
  );

  await user.click(await screen.findByLabelText("正式运行（一主双校）"));
  await user.type(screen.getByLabelText("AgentRun 指令"), "运行后取消");
  await user.click(screen.getByRole("button", { name: "开始讨论运行" }));
  const cancel = await screen.findByRole("button", { name: "取消运行" });
  await user.click(cancel);

  expect(await screen.findByText("AgentRun 已结束：cancelled。")).toBeVisible();
  expect(port.calls.commands.some((request) =>
    request.operationId === "cancel_agent_run_api_v1_agent_runs__run_id__cancel_post"
  )).toBe(true);
});
