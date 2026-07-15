import { randomUUID } from "node:crypto";
import { readFile, rename, rm, writeFile } from "node:fs/promises";

import type { BackendClient } from "./backend-client";
import { isRecord } from "./runtime-contracts";
import type { SidecarManager } from "./sidecar";

const WORKFLOW_ID_PATTERN = /^workflow_[a-z0-9]+$/;

export interface DiagnosticsExportInput {
  workflowId?: string;
  afterEventId?: number;
}

function safeError(reply: { statusCode: number; payload: unknown }): unknown {
  if (!isRecord(reply.payload) || !isRecord(reply.payload.error)) {
    return { statusCode: reply.statusCode, code: "invalid_error_envelope" };
  }
  return {
    statusCode: reply.statusCode,
    code: typeof reply.payload.error.code === "string" ? reply.payload.error.code : "unknown",
    retryable:
      typeof reply.payload.error.retryable === "boolean" ? reply.payload.error.retryable : false,
  };
}

function eventProjection(value: unknown): unknown[] {
  if (!isRecord(value) || !Array.isArray(value.events)) {
    return [];
  }
  return value.events.filter(isRecord).map((event) => {
    const payload = isRecord(event.payload) ? event.payload : {};
    const result: Record<string, unknown> = {
      schema_version: event.schema_version,
      event_id: event.event_id,
      event_type: event.event_type,
      project_id: event.project_id,
      workflow_id: event.workflow_id,
      stage_run_id: event.stage_run_id,
      room_id: event.room_id,
      task_id: event.task_id,
      correlation_id: event.correlation_id,
      causation_id: event.causation_id,
      actor: event.actor,
      source: event.source,
      occurred_at: event.occurred_at,
    };
    const safePayload: Record<string, unknown> = {};
    for (const key of ["stage", "target_stage", "status", "result", "resolution", "error_code"]) {
      const item = payload[key];
      if (typeof item === "string" || typeof item === "number" || typeof item === "boolean") {
        safePayload[key] = item;
      }
    }
    result.payload = safePayload;
    return result;
  });
}

function toolProjection(value: unknown): unknown[] {
  if (!isRecord(value) || !Array.isArray(value.calls)) {
    return [];
  }
  return value.calls.filter(isRecord).map((call) => ({
    id: call.id,
    project_id: call.project_id,
    workflow_id: call.workflow_id,
    stage_run_id: call.stage_run_id,
    task_id: call.task_id,
    tool_name: call.tool_name,
    capability: call.capability,
    arguments_hash: call.arguments_hash,
    status: call.status,
    error_code: call.error_code,
    started_at: call.started_at,
    completed_at: call.completed_at,
  }));
}

function recoveryProjection(value: unknown): unknown[] {
  if (!isRecord(value) || !Array.isArray(value.recoveries)) {
    return [];
  }
  return value.recoveries.filter(isRecord).map((record) => ({
    id: record.id,
    project_id: record.project_id,
    workflow_id: record.workflow_id,
    stage_run_id: record.stage_run_id,
    status: record.status,
    interrupted_tasks: record.interrupted_tasks,
    interrupted_tool_calls: record.interrupted_tool_calls,
    detected_at: record.detected_at,
    resolved_at: record.resolved_at,
    resolution: record.resolution,
  }));
}

function redactLine(value: string): string {
  return value
    .replace(/Bearer\s+[A-Za-z0-9._~+/-]+/giu, "Bearer [REDACTED]")
    .replace(/\bsk-[A-Za-z0-9_-]{8,}\b/gu, "[REDACTED]")
    .replace(/("(?:api_key|authorization|credential|password|secret|token)"\s*:\s*")[^"]+/giu, "$1[REDACTED]");
}

export class DiagnosticsExporter {
  constructor(
    private readonly backend: BackendClient,
    private readonly sidecar: SidecarManager,
    private readonly contractSumsPath: string,
  ) {}

  async write(path: string, input: DiagnosticsExportInput): Promise<void> {
    const workflowId = input.workflowId?.trim();
    if (workflowId !== undefined && workflowId !== "" && !WORKFLOW_ID_PATTERN.test(workflowId)) {
      throw new Error("Diagnostics workflow id is invalid");
    }
    const afterEventId = input.afterEventId ?? 0;
    if (!Number.isSafeInteger(afterEventId) || afterEventId < 0) {
      throw new Error("Diagnostics event cursor is invalid");
    }
    const [system, readiness, recoveries, sidecar, contracts] = await Promise.all([
      this.backend.executeInternal("system_info_api_v1_system_info_get"),
      this.backend.executeInternal("readiness_api_v1_readiness_get"),
      this.backend.executeInternal("list_recoveries_api_v1_recovery_get"),
      this.sidecar.publicState(),
      readFile(this.contractSumsPath, "utf8").then((content) => JSON.parse(content) as unknown),
    ]);
    let workflowAudit: unknown = null;
    if (workflowId !== undefined && workflowId !== "") {
      const [events, tools] = await Promise.all([
        this.backend.executeInternal("replay_events_api_v1_events_replay_get", {
          query: { workflow_id: workflowId, after_event_id: afterEventId },
        }),
        this.backend.executeInternal("list_tool_calls_api_v1_workflows__workflow_id__tool_calls_get", {
          path: { workflow_id: workflowId },
        }),
      ]);
      workflowAudit = {
        workflowId,
        afterEventId,
        events: events.statusCode === 200 ? eventProjection(events.payload) : safeError(events),
        toolCalls: tools.statusCode === 200 ? toolProjection(tools.payload) : safeError(tools),
      };
    }
    const document = {
      schemaVersion: 1,
      generatedAt: new Date().toISOString(),
      application: {
        electron: process.versions.electron,
        node: process.versions.node,
        chrome: process.versions.chrome,
      },
      contracts,
      sidecar,
      backend: {
        system: system.statusCode === 200 ? system.payload : safeError(system),
        readiness: readiness.statusCode === 200 ? readiness.payload : safeError(readiness),
        recoveries:
          recoveries.statusCode === 200
            ? recoveryProjection(recoveries.payload)
            : safeError(recoveries),
      },
      workflowAudit,
      logs: this.sidecar.diagnostics().slice(-100).map(redactLine),
      exclusions: [
        "session tokens and Secret Bridge credentials",
        "API keys and decrypted SecretStore values",
        "source code and arbitrary project file contents",
        "complete chat and model output content",
        "EventEnvelope arbitrary payload fields",
        "ToolCall arguments and result bodies",
      ],
    };
    const temporary = `${path}.${randomUUID()}.tmp`;
    try {
      await writeFile(temporary, JSON.stringify(document, null, 2) + "\n", {
        encoding: "utf8",
        flag: "wx",
      });
      await rename(temporary, path);
    } finally {
      await rm(temporary, { force: true });
    }
  }
}

