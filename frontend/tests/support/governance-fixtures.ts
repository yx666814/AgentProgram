import type { components } from "../../src/api/generated";
import { projectRegistration, workflowSnapshot } from "./fixtures";

export const timestamp = "2026-07-15T08:00:00Z";

export function governanceScope(mode: components["schemas"]["ExecutionMode"] = "manual") {
  const snapshot = workflowSnapshot("waiting_user", 4);
  return {
    project: projectRegistration("ready", 3),
    workflow: { ...snapshot, workflow: { ...snapshot.workflow, execution_mode: mode } },
  };
}

export function gateFixture(
  status: components["schemas"]["GateStatus"] = "warning",
  resolution: components["schemas"]["GateResolution"] = "pending",
): components["schemas"]["QualityGateRun"] {
  return {
    schema_version: 1,
    id: "gate_demo",
    project_id: "project_demo",
    workflow_id: "workflow_demo",
    stage_run_id: "stagerun_planner",
    artifact_version_ids: ["artifactversion_demo"],
    status,
    issues: status === "pass" ? [] : [{ code: "gate.warning", message: "需要人工确认", severity: status === "fail" ? "error" : "warning" }],
    resolution,
    version: 1,
    evaluated_at: timestamp,
  };
}

export function approvalFixture(
  status: components["schemas"]["ApprovalStatus"] = "pending",
): components["schemas"]["Approval"] {
  return {
    schema_version: 1,
    id: "approval_demo",
    project_id: "project_demo",
    workflow_id: "workflow_demo",
    kind: "quality_gate",
    target_id: "gate_demo",
    status,
    version: status === "pending" ? 1 : 2,
    requested_at: timestamp,
    ...(status === "pending" ? {} : { decided_at: timestamp, reason: "已决定" }),
  };
}

export function artifactInventory(): components["schemas"]["ArtifactInventoryResponse"] {
  return {
    artifacts: [{
      schema_version: 1,
      id: "artifact_demo",
      project_id: "project_demo",
      workflow_id: "workflow_demo",
      stage: "planner",
      name: "需求规格",
      relative_path: "docs/requirements.md",
      created_at: timestamp,
    }],
    versions: [{
      schema_version: 1,
      id: "artifactversion_demo",
      artifact_id: "artifact_demo",
      stage_run_id: "stagerun_planner",
      version: 1,
      content_hash: "a".repeat(64),
      byte_size: 128,
      status: "locked",
      checkpoint_id: "checkpoint_demo",
      locked_at: timestamp,
      created_at: timestamp,
    }],
  };
}

export function handoffFixture(): components["schemas"]["HandoffPacket"] {
  return {
    schema_version: 1,
    id: "handoff_demo",
    project_id: "project_demo",
    workflow_id: "workflow_demo",
    from_stage_run_id: "stagerun_planner",
    from_stage: "planner",
    to_stage: "designer",
    artifact_version_ids: ["artifactversion_demo"],
    gate_run_id: "gate_demo",
    checkpoint_id: "checkpoint_demo",
    content_hash: "b".repeat(64),
    status: "active",
    created_at: timestamp,
  };
}

export function checkpointFixture(id = "checkpoint_demo"): components["schemas"]["ProjectCheckpoint"] {
  return {
    schema_version: 1,
    id,
    project_id: "project_demo",
    reason: "manual",
    manifest_version: 1,
    content_hash: "c".repeat(64),
    files: [{ relative_path: "src/app.ts", content_hash: "d".repeat(64), byte_size: 32 }],
    total_bytes: 32,
    created_at: timestamp,
  };
}
