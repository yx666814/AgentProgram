import type {
  ModelProfile,
  RecoveryRecord,
  ToolCallList,
} from "../../src/api/backend-api";
import type { PersistedEvent } from "../../electron/desktop-port";

const timestamp = "2026-07-15T08:00:00Z";

export function modelProfile(
  id = "profile_primary",
  provider: ModelProfile["provider"] = "openai_compatible",
): ModelProfile {
  return {
    schema_version: 1,
    id,
    name: id === "profile_primary" ? "主模型" : "评审模型",
    provider,
    base_url: provider === "anthropic" ? "https://api.anthropic.com" : "https://models.example/v1",
    model: provider === "anthropic" ? "claude-review" : "gpt-primary",
    credential_ref: `vault:${id}`,
    masked_hint: "key-****42",
    enabled: true,
    version: 1,
    created_at: timestamp,
    updated_at: timestamp,
  };
}

export function auditEvent(payload: Record<string, unknown> = {}): PersistedEvent {
  return {
    schema_version: 1,
    event_id: 45,
    event_type: "workflow.paused",
    correlation_id: "correlation_audit",
    causation_id: "correlation_parent",
    actor: { type: "user", id: "user_local" },
    source: "backend",
    occurred_at: timestamp,
    project_id: "project_demo",
    workflow_id: "workflow_demo",
    room_id: "room_planner",
    task_id: "task_demo",
    payload: { stage: "planner", status: "paused", ...payload },
  };
}

export function toolCallList(result: Record<string, unknown> = {}): ToolCallList {
  return {
    calls: [
      {
        schema_version: 1,
        id: "toolcall_demo",
        project_id: "project_demo",
        workflow_id: "workflow_demo",
        stage_run_id: "stagerun_planner",
        task_id: "task_demo",
        tool_name: "Read",
        capability: "workspace.read",
        idempotency_key: "tool-call-demo-0001",
        arguments_hash: "a".repeat(64),
        status: "succeeded",
        result,
        error_code: null,
        started_at: timestamp,
        completed_at: timestamp,
      },
    ],
  };
}

export function recoveryRecord(): RecoveryRecord {
  return {
    schema_version: 1,
    id: "recovery_demo",
    project_id: "project_demo",
    workflow_id: "workflow_demo",
    stage_run_id: "stagerun_planner",
    status: "resumed",
    interrupted_agent_runs: 1,
    interrupted_tasks: 2,
    interrupted_tool_calls: 1,
    detected_at: timestamp,
    resolved_at: timestamp,
  };
}
