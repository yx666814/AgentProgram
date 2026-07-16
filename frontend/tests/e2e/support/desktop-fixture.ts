import type { Page } from "@playwright/test";

const timestamp = "2026-07-15T08:00:00Z";

const fixture = {
  project: {
    schema_version: 1,
    project: { schema_version: 1, id: "project_demo", name: "示例项目", goal: "从真实后端契约完成五阶段交付", status: "ready", version: 3, created_at: timestamp, updated_at: timestamp },
    workspace: { schema_version: 1, id: "workspace_demo", project_id: "project_demo", mode: "direct", root_path: "D:\\Work\\demo", canonical_root_path: "D:\\Work\\demo", created_at: timestamp },
  },
  preflight: {
    schema_version: 1,
    id: "preflight_demo",
    project_id: "project_demo",
    manifest_version: 1,
    status: "pass",
    checks: [
      { code: "workspace.boundary", message: "工作区边界有效", status: "pass", evidence: { canonical_root: "D:\\Work\\demo" } },
      { code: "commands.detected", message: "已读取构建与测试命令", status: "pass", evidence: { build: "npm run build", test: "npm test" } },
    ],
    started_at: timestamp,
    completed_at: timestamp,
  },
  manifest: { schema_version: 1, project_id: "project_demo", manifest_version: 1, source_paths: ["src"], instruction_paths: ["AGENTS.md"], excluded_paths: [".env"], build_commands: [], test_commands: [], typecheck_commands: [] },
  artifact: {
    artifacts: [{ schema_version: 1, id: "artifact_demo", project_id: "project_demo", workflow_id: "workflow_demo", stage: "planner", name: "需求规格", relative_path: "docs/requirements.md", created_at: timestamp }],
    versions: [{ schema_version: 1, id: "artifactversion_demo", artifact_id: "artifact_demo", stage_run_id: "stagerun_planner", version: 1, content_hash: "a".repeat(64), byte_size: 128, status: "locked", checkpoint_id: "checkpoint_demo", locked_at: timestamp, created_at: timestamp }],
  },
  gate: { schema_version: 1, id: "gate_demo", project_id: "project_demo", workflow_id: "workflow_demo", stage_run_id: "stagerun_planner", artifact_version_ids: ["artifactversion_demo"], status: "warning", issues: [{ code: "gate.warning", message: "需要人工确认风险", severity: "warning" }], resolution: "pending", version: 1, evaluated_at: timestamp },
  approval: { schema_version: 1, id: "approval_demo", project_id: "project_demo", workflow_id: "workflow_demo", kind: "quality_gate", target_id: "gate_demo", status: "pending", version: 1, requested_at: timestamp },
  handoff: { schema_version: 1, id: "handoff_demo", project_id: "project_demo", workflow_id: "workflow_demo", from_stage_run_id: "stagerun_planner", from_stage: "planner", to_stage: "designer", artifact_version_ids: ["artifactversion_demo"], gate_run_id: "gate_demo", checkpoint_id: "checkpoint_demo", content_hash: "b".repeat(64), status: "active", created_at: timestamp },
  capability: { schema_version: 1, id: "capability_demo", project_id: "project_demo", workflow_id: "workflow_demo", stage_run_id: "stagerun_builder", task_id: "task_builder", stage: "builder", capability: "workspace.write", reason: "更新实现文件", risk_level: "medium", target_paths: ["src/**"], command: null, status: "pending", version: 1, idempotency_key: "capability-demo-0001", requested_at: timestamp },
  checkpoint: { schema_version: 1, id: "checkpoint_demo", project_id: "project_demo", reason: "manual", manifest_version: 1, content_hash: "c".repeat(64), files: [{ relative_path: "src/app.ts", content_hash: "d".repeat(64), byte_size: 32 }], total_bytes: 32, created_at: timestamp },
  conflict: { schema_version: 1, id: "conflict_demo", project_id: "project_demo", relative_path: "src/app.ts", baseline_content_hash: "1".repeat(64), user_content_hash: "2".repeat(64), agent_content_hash: "3".repeat(64), status: "open", resolution: null, version: 1, created_at: timestamp, resolved_at: null },
  profile: { schema_version: 1, id: "profile_primary", name: "主模型", provider: "openai_compatible", base_url: "https://models.example/v1", model: "gpt-primary", credential_ref: "vault:model.primary", masked_hint: "key-****42", enabled: true, version: 1, created_at: timestamp, updated_at: timestamp },
  recovery: { schema_version: 1, id: "recovery_demo", project_id: "project_demo", workflow_id: "workflow_demo", stage_run_id: "stagerun_builder", status: "resumed", interrupted_agent_runs: 1, interrupted_tasks: 2, interrupted_tool_calls: 1, detected_at: timestamp, resolved_at: timestamp },
};

export async function installDesktopFixture(page: Page): Promise<void> {
  await page.addInitScript(({ data, now }) => {
    const listeners = new Set<(event: Record<string, unknown>) => void>();
    const calls = { commands: [] as Array<Record<string, unknown>>, queries: [] as Array<Record<string, unknown>>, replays: [] as number[], confirms: [] as Array<Record<string, unknown>> };
    let nextEventId = 100;

    function selectedStage(): string {
      return /^\/projects\/[^/]+\/stages\/([^/]+)/.exec(window.location.pathname)?.[1] ?? "planner";
    }

    function workflowSnapshot() {
      const stages = ["planner", "designer", "builder", "reviewer", "deployer"];
      const stage = selectedStage();
      const activeIndex = stages.indexOf(stage);
      const governance = /\/(artifacts|approvals)$/.test(window.location.pathname);
      return {
        schema_version: 1,
        workflow: { schema_version: 1, id: "workflow_demo", project_id: "project_demo", title: "V1 正式工作流", status: governance ? "waiting_user" : "running", execution_mode: "manual", current_stage: stage, version: 4, created_at: now, updated_at: now },
        stage_runs: stages.map((value, index) => ({ schema_version: 1, id: `stagerun_${value}`, workflow_id: "workflow_demo", stage: value, attempt: 1, state: index < activeIndex ? "completed" : index === activeIndex ? "discussing" : "locked", version: 1, created_at: now, ...(index < activeIndex ? { started_at: now, completed_at: now } : {}) })),
        rooms: stages.map((value) => ({ schema_version: 1, id: `room_${value}`, workflow_id: "workflow_demo", stage_run_id: `stagerun_${value}`, stage: value, status: "active", next_sequence: 3, version: 2, created_at: now, updated_at: now })),
      };
    }

    function auditEvent() {
      return { schema_version: 1, event_id: 45, event_type: "workflow.paused", correlation_id: "correlation_audit", causation_id: "correlation_parent", actor: { type: "user", id: "user_local" }, source: "backend", occurred_at: now, project_id: "project_demo", workflow_id: "workflow_demo", room_id: "room_planner", task_id: "task_demo", payload: { stage: "planner", status: "paused" } };
    }

    function toolCall() {
      return { schema_version: 1, id: "toolcall_demo", project_id: "project_demo", workflow_id: "workflow_demo", stage_run_id: `stagerun_${selectedStage()}`, task_id: "task_demo", tool_name: "Read", capability: "workspace.read", idempotency_key: "tool-call-demo-0001", arguments_hash: "e".repeat(64), status: "succeeded", result: {}, error_code: null, started_at: now, completed_at: now };
    }

    function emit(eventType: string, correlationId: string, extra: Record<string, unknown> = {}) {
      nextEventId += 1;
      const event = { schema_version: 1, event_id: nextEventId, event_type: eventType, correlation_id: correlationId, actor: { type: "user", id: "user_local" }, source: "backend", occurred_at: now, project_id: "project_demo", workflow_id: "workflow_demo", payload: {}, ...extra };
      for (const listener of listeners) listener(event);
    }

    function reply(request: { requestId: string }, payload: unknown, statusCode = 200) {
      return Promise.resolve({ requestId: request.requestId, statusCode, payload });
    }

    function queryPayload(operationId: string) {
      const snapshot = workflowSnapshot();
      const stage = selectedStage();
      const room = snapshot.rooms.find((item) => item.stage === stage);
      const roomId = room?.id ?? `room_${stage}`;
      switch (operationId) {
        case "health_api_v1_health_get": return { status: "ok" };
        case "readiness_api_v1_readiness_get": return { status: "ready", database: "ready" };
        case "system_info_api_v1_system_info_get": return { backend_version: "0.1.0", protocol_version: 1 };
        case "list_recoveries_api_v1_recovery_get": return { recoveries: [data.recovery] };
        case "list_projects_api_v1_projects_get": return { projects: [data.project] };
        case "get_project_api_v1_projects__project_id__get": return data.project;
        case "get_preflight_api_v1_projects__project_id__preflight_get": return data.preflight;
        case "list_workflows_api_v1_projects__project_id__workflows_get": return { workflows: [snapshot.workflow] };
        case "get_workflow_api_v1_workflows__workflow_id__get": return snapshot;
        case "list_messages_api_v1_rooms__room_id__messages_get": return { messages: [
          { schema_version: 1, id: `message_${stage}_1`, room_id: roomId, sequence: 1, author: "user", kind: "message", content: "请严格依据后端契约完成当前阶段。", correction_of_id: null, created_at: now },
          { schema_version: 1, id: `message_${stage}_2`, room_id: roomId, sequence: 2, author: "agent", kind: "message", content: "已读取 StageContract，等待下一项明确任务。", correction_of_id: null, created_at: now },
        ] };
        case "list_tasks_api_v1_workflows__workflow_id__tasks_get": return { tasks: [{ schema_version: 1, id: "task_demo", workflow_id: "workflow_demo", stage_run_id: `stagerun_${stage}`, room_id: roomId, title: "核对阶段交付", status: "queued", payload: {}, version: 1, created_at: now }] };
        case "list_tool_calls_api_v1_workflows__workflow_id__tool_calls_get": return { calls: [toolCall()] };
        case "list_agent_runs_api_v1_rooms__room_id__agent_runs_get": return { runs: [{ schema_version: 1, id: "agentrun_demo", workflow_id: "workflow_demo", room_id: roomId, request_key: "agent-run-demo-0001", formal: false, status: "running", version: 1, created_at: now }] };
        case "get_room_assignment_api_v1_rooms__room_id__model_assignment_get": return { schema_version: 1, room_id: roomId, primary_profile_id: "profile_primary", reviewer_a_profile_id: null, reviewer_b_profile_id: null, version: 1, updated_at: now };
        case "list_artifacts_api_v1_workflows__workflow_id__artifacts_get": return data.artifact;
        case "list_quality_gates_api_v1_workflows__workflow_id__quality_gates_get": return { gates: [data.gate] };
        case "list_approvals_api_v1_workflows__workflow_id__approvals_get": return { approvals: [data.approval] };
        case "list_handoffs_api_v1_workflows__workflow_id__handoffs_get": return { handoffs: [data.handoff] };
        case "list_change_requests_api_v1_workflows__workflow_id__change_requests_get": return { change_requests: [] };
        case "list_capability_requests_api_v1_workflows__workflow_id__capability_requests_get": return { requests: [data.capability] };
        case "list_conflicts_api_v1_projects__project_id__conflicts_get": return { conflicts: [data.conflict] };
        case "list_checkpoints_api_v1_projects__project_id__checkpoints_get": return { checkpoints: [data.checkpoint] };
        case "list_external_changes_api_v1_projects__project_id__external_changes_get": return { changes: [{ schema_version: 1, id: "change_demo", project_id: "project_demo", relative_path: "src/app.ts", change_type: "modified", baseline_content_hash: "1".repeat(64), current_content_hash: "2".repeat(64), status: "open", detected_at: now }] };
        case "list_profiles_api_v1_model_profiles_get": return { profiles: [data.profile] };
        case "replay_events_api_v1_events_replay_get": return { events: [auditEvent()] };
        default: throw new Error(`Unexpected fixture query: ${operationId}`);
      }
    }

    function commandPayload(request: { operationId: string; payload?: Record<string, unknown> }) {
      const correlationId = typeof request.payload?.correlation_id === "string" ? request.payload.correlation_id : "correlation_fixture";
      const snapshot = workflowSnapshot();
      switch (request.operationId) {
        case "open_project_api_v1_projects__project_id__open_post": return data.project;
        case "create_project_api_v1_projects_post": return { registration: data.project, manifest: data.manifest, preflight_required: true };
        case "run_preflight_api_v1_projects__project_id__preflight_post": return { project: data.project.project, result: data.preflight };
        case "create_workflow_api_v1_projects__project_id__workflows_post": return snapshot;
        case "start_workflow_api_v1_workflows__workflow_id__start_post": return snapshot;
        case "append_message_api_v1_rooms__room_id__messages_post": {
          const content = typeof request.payload?.content === "string" ? request.payload.content : "";
          const message = { schema_version: 1, id: "message_created", room_id: `room_${selectedStage()}`, sequence: 3, author: "user", kind: "message", content, correction_of_id: null, created_at: now };
          setTimeout(() => { emit("message.appended", correlationId, { room_id: message.room_id, payload: { message_id: message.id } }); }, 0);
          return { message, room: snapshot.rooms.find((item) => item.id === message.room_id) };
        }
        case "enqueue_task_api_v1_rooms__room_id__tasks_post": return { schema_version: 1, id: "task_created", workflow_id: "workflow_demo", stage_run_id: `stagerun_${selectedStage()}`, room_id: `room_${selectedStage()}`, title: typeof request.payload?.title === "string" ? request.payload.title : "任务", status: "queued", payload: {}, version: 1, created_at: now };
        case "start_task_api_v1_tasks__task_id__start_post": return { schema_version: 1, id: "task_demo", workflow_id: "workflow_demo", stage_run_id: `stagerun_${selectedStage()}`, room_id: `room_${selectedStage()}`, title: "核对阶段交付", status: "running", payload: {}, version: 2, created_at: now, started_at: now };
        case "cancel_task_api_v1_tasks__task_id__cancel_post": return { schema_version: 1, id: "task_demo", workflow_id: "workflow_demo", stage_run_id: `stagerun_${selectedStage()}`, room_id: `room_${selectedStage()}`, title: "核对阶段交付", status: "cancelled", payload: {}, version: 2, created_at: now, completed_at: now };
        case "decide_gate_approval_api_v1_approvals__approval_id__decision_post": {
          setTimeout(() => { emit("approval.decided", correlationId, { payload: { approval_id: data.approval.id, status: "approved" } }); }, 0);
          return { approval: { ...data.approval, status: "approved", version: 2, decided_at: now }, gate: { ...data.gate, resolution: "approved" }, handoff: data.handoff, change_request: null };
        }
        case "decide_capability_api_v1_capability_requests__request_id__decision_post": {
          setTimeout(() => { emit("capability.decided", correlationId, { payload: { request_id: data.capability.id, status: "approved" } }); }, 0);
          return { ...data.capability, status: "approved", version: 2, decided_at: now, decision_reason: "fixture" };
        }
        case "create_profile_api_v1_model_profiles_post": return data.profile;
        case "update_profile_api_v1_model_profiles__profile_id__put": return { ...data.profile, version: 2 };
        case "assign_room_models_api_v1_rooms__room_id__model_assignment_put": return { schema_version: 1, room_id: `room_${selectedStage()}`, primary_profile_id: "profile_primary", reviewer_a_profile_id: null, reviewer_b_profile_id: null, version: 1, updated_at: now };
        case "plan_restore_api_v1_projects__project_id__checkpoints__checkpoint_id__restore_plan_post": return { plan: { schema_version: 1, current_checkpoint_id: "checkpoint_current", target_checkpoint_id: data.checkpoint.id, overwrite_paths: ["src/app.ts"], preserved_extra_paths: ["notes.txt"] }, protection_checkpoint: { ...data.checkpoint, id: "checkpoint_protection", reason: "pre_restore" } };
        case "restore_checkpoint_api_v1_projects__project_id__checkpoints__checkpoint_id__restore_post": return { result: { schema_version: 1, restored_checkpoint_id: data.checkpoint.id, protection_checkpoint_id: "checkpoint_protection", restored_file_count: 1 }, project: { ...data.project.project, status: "preflight_required", version: 4 } };
        default: return snapshot;
      }
    }

    const port = {
      backend: {
        query(request: { operationId: string; requestId: string }) { calls.queries.push(request); return reply(request, queryPayload(request.operationId)); },
        command(request: { operationId: string; requestId: string; payload?: Record<string, unknown> }) { calls.commands.push(request); return reply(request, commandPayload(request)); },
        subscribe(listener: (event: Record<string, unknown>) => void) { listeners.add(listener); return () => listeners.delete(listener); },
        requestReplay(afterEventId: number) { calls.replays.push(afterEventId); return Promise.resolve(); },
      },
      secrets: {
        store(input: { value: string }) { return Promise.resolve({ credentialRef: "credential.xingxie.00000000000000000000000000000000", maskedHint: input.value.length <= 4 ? "****" : `${input.value.slice(0, 3)}****${input.value.slice(-4)}` }); },
        delete() { return Promise.resolve(); },
      },
      diagnostics: {
        export() { return Promise.resolve({ cancelled: false, path: "D:\\Temp\\xingxie-diagnostics.json" }); },
      },
      selectDirectory() { return Promise.resolve({ cancelled: false, path: "D:\\Work\\demo" }); },
      showNativeConfirm(input: Record<string, unknown>) { calls.confirms.push(input); return Promise.resolve(true); },
      showSystemNotification() { return Promise.resolve(); },
      openLocalLocation() { return Promise.resolve(); },
      getWindowState() { return Promise.resolve({ maximized: false, scaleFactor: 1 }); },
      requestWindowClose() { return Promise.resolve({ allowed: true }); },
    };
    Reflect.set(window, "desktop", port);
    Reflect.set(window, "__desktopTest", { calls, emit });
  }, { data: fixture, now: timestamp });
}
