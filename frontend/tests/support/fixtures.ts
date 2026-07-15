import type {
  PreflightResult,
  ProjectRegistration,
  WorkflowSnapshot,
} from "../../src/api/backend-api";

const timestamp = "2026-07-15T08:00:00Z";

export function projectRegistration(
  status: ProjectRegistration["project"]["status"] = "preflight_required",
  version = 1,
): ProjectRegistration {
  return {
    schema_version: 1,
    project: {
      schema_version: 1,
      id: "project_demo",
      name: "示例项目",
      goal: "验证真实项目主线",
      status,
      version,
      created_at: timestamp,
      updated_at: timestamp,
    },
    workspace: {
      schema_version: 1,
      id: "workspace_demo",
      project_id: "project_demo",
      mode: "direct",
      root_path: "D:\\Work\\demo",
      canonical_root_path: "D:\\Work\\demo",
      created_at: timestamp,
    },
  };
}

export function preflightResult(status: PreflightResult["status"]): PreflightResult {
  return {
    schema_version: 1,
    id: "preflight_demo",
    project_id: "project_demo",
    manifest_version: 1,
    status,
    checks: [
      {
        code: "workspace.boundary",
        message: status === "warning" ? "Workspace is safe with a warning" : "Workspace is safe",
        status,
        evidence: { canonical_root: "D:\\Work\\demo" },
      },
    ],
    started_at: timestamp,
    completed_at: timestamp,
  };
}

export function workflowSnapshot(
  status: WorkflowSnapshot["workflow"]["status"] = "created",
  version = 1,
): WorkflowSnapshot {
  const stages = ["planner", "designer", "builder", "reviewer", "deployer"] as const;
  return {
    schema_version: 1,
    workflow: {
      schema_version: 1,
      id: "workflow_demo",
      project_id: "project_demo",
      title: "首个工作流",
      status,
      execution_mode: "manual",
      current_stage: "planner",
      version,
      created_at: timestamp,
      updated_at: timestamp,
    },
    stage_runs: stages.map((stage, index) => ({
      schema_version: 1 as const,
      id: `stagerun_${stage}`,
      workflow_id: "workflow_demo",
      stage,
      attempt: 1,
      state: index === 0 ? "ready" : "locked",
      version: 1,
      created_at: timestamp,
    })),
    rooms: stages.map((stage) => ({
      schema_version: 1 as const,
      id: `room_${stage}`,
      workflow_id: "workflow_demo",
      stage_run_id: `stagerun_${stage}`,
      stage,
      status: "active" as const,
      next_sequence: 1,
      version: 1,
      created_at: timestamp,
      updated_at: timestamp,
    })),
  };
}

export function projectManifest() {
  return {
    schema_version: 1 as const,
    project_id: "project_demo",
    manifest_version: 1,
    source_paths: [] as string[],
    instruction_paths: [] as string[],
    excluded_paths: [] as string[],
    build_commands: [],
    test_commands: [],
    typecheck_commands: [],
  };
}
