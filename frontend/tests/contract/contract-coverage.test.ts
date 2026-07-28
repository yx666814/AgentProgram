// @vitest-environment node

import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

const contractsDirectory = resolve(process.cwd(), "contracts");

interface OpenApiOperation {
  operationId?: string;
}

interface OpenApiSnapshot {
  paths: Record<string, Record<string, OpenApiOperation>>;
}

interface CapabilitySnapshot {
  capabilities: Record<string, { method: string; path: string }>;
  websocket: {
    schemaVersion: number;
    path: string;
    ticketOperationId: string;
    replayOperationId: string;
  };
  workflowStates: string[];
  stageRunStates: string[];
  stages: string[];
  stageContracts: Array<{
    stage: string;
    contract_version: string;
    role_card_version: string;
  }>;
  roleCards: Array<{
    role_id: string;
    role_card_version: string;
    content_hash: string;
  }>;
  tools: Array<{ name: string; capability: string }>;
  errorCodes: string[];
}

interface EventSnapshot {
  envelopeSchema: { required?: string[] };
  eventTypes: string[];
}

const requiredEventTypes = [
  "agent_run.completed",
  "agent_run.created",
  "agent_run.started",
  "approval.decided",
  "artifact.version_created",
  "capability.decided",
  "capability.requested",
  "change_request.created",
  "external_change.scanned",
  "file_conflict.resolved",
  "handoff.created",
  "message.appended",
  "model_profile.created",
  "model_profile.updated",
  "project.checkpoint_created",
  "project.checkpoint_restored",
  "project.closed",
  "project.created",
  "project.opened",
  "project.preflight_completed",
  "project.restore_planned",
  "quality_gate.evaluated",
  "recovery.detected",
  "recovery.discarded",
  "recovery.resumed",
  "room_model_assignment.updated",
  "stage_run.reopened",
  "stage_run.transitioned",
  "task.cancelled",
  "task.completed",
  "task.queued",
  "task.started",
  "tool.completed",
  "tool.started",
  "workflow.abandond",
  "workflow.created",
  "workflow.mode_changed",
  "workflow.paused",
  "workflow.resumed",
  "workflow.started",
  "workflow.stopped",
] as const;

function readJson(fileName: string): unknown {
  return JSON.parse(readFileSync(resolve(contractsDirectory, fileName), "utf8")) as unknown;
}

describe("frozen backend contract snapshots", () => {
  it.each(["openapi.json", "events.schema.json", "capabilities.json"])(
    "exports %s from the backend authority",
    (fileName) => {
      expect(existsSync(resolve(contractsDirectory, fileName)), `${fileName} is missing`).toBe(true);
    },
  );

  it("mirrors every frozen REST operation without frontend aliases", () => {
    const openapi = readJson("openapi.json") as OpenApiSnapshot;
    const capabilitySnapshot = readJson("capabilities.json") as CapabilitySnapshot;
    const operations = Object.entries(openapi.paths).flatMap(([path, pathItem]) =>
      Object.entries(pathItem)
        .filter(([method]) => ["get", "post", "put", "patch", "delete"].includes(method))
        .map(([method, operation]) => ({
          operationId: operation.operationId,
          method: method.toUpperCase(),
          path,
        })),
    );

    expect(operations).toHaveLength(69);
    for (const operation of operations) {
      expect(operation.operationId).toBeTypeOf("string");
      expect(capabilitySnapshot.capabilities[operation.operationId ?? ""]).toEqual({
        method: operation.method,
        path: operation.path,
      });
    }
    expect(Object.keys(capabilitySnapshot.capabilities)).toHaveLength(operations.length);
  });

  it("exports the persisted event envelope and every backend event type", () => {
    const eventSnapshot = readJson("events.schema.json") as EventSnapshot;

    expect(eventSnapshot.envelopeSchema.required).toEqual(
      expect.arrayContaining([
        "schema_version",
        "event_type",
        "correlation_id",
        "actor",
        "source",
        "occurred_at",
        "payload",
      ]),
    );
    expect(eventSnapshot.eventTypes).toEqual(requiredEventTypes);
  });

  it("exports the complete state, stage, tool, error and websocket authority", () => {
    const snapshot = readJson("capabilities.json") as CapabilitySnapshot;

    expect(snapshot.workflowStates).toEqual([
      "created",
      "preflight_failed",
      "running",
      "waiting_user",
      "warning_blocked",
      "paused",
      "external_conflict",
      "interrupted",
      "failed",
      "stopped",
      "abandoned",
      "completed",
    ]);
    expect(snapshot.stageRunStates).toEqual([
      "locked",
      "ready",
      "discussing",
      "producing",
      "p2r_reviewing",
      "quality_checking",
      "waiting_approval",
      "handoff_ready",
      "completed",
      "warning_blocked",
      "needs_fix",
      "external_conflict",
      "interrupted",
      "failed",
      "cancelled",
      "abandoned",
    ]);
    expect(snapshot.stages).toEqual(["planner", "designer", "builder", "reviewer", "deployer"]);
    expect(snapshot.stageContracts.map(({ stage }) => stage)).toEqual(snapshot.stages);
    expect(snapshot.stageContracts).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ contract_version: "1.0.0", role_card_version: "1.0.0" }),
      ]),
    );
    expect(snapshot.roleCards.map(({ role_id }) => role_id)).toEqual(snapshot.stages);
    expect(snapshot.roleCards.every(({ content_hash }) => /^[0-9a-f]{64}$/.test(content_hash))).toBe(
      true,
    );
    expect(snapshot.tools).toHaveLength(23);
    expect(snapshot.tools.every(({ name, capability }) => name === capability)).toBe(true);
    expect(snapshot.errorCodes).toEqual(
      expect.arrayContaining([
        "auth.invalid_session",
        "project.version_conflict",
        "workflow.not_found",
        "stage_run.invalid_transition",
        "tool.approval_required",
        "readiness.unavailable",
      ]),
    );
    expect(snapshot.websocket).toEqual(
      expect.objectContaining({
        schemaVersion: 1,
        path: "/api/v1/events/ws",
        ticketOperationId: "issue_event_ticket_api_v1_events_tickets_post",
        replayOperationId: "replay_events_api_v1_events_replay_get",
      }),
    );
  });
});
