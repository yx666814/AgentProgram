import { randomUUID } from "node:crypto";

import {
  BackendRequestValidationError,
  buildBackendFetchRequest,
} from "./backend-request";
import { LocalPathPolicy } from "./local-path-policy";
import type {
  OperationMap,
  RuntimeBackendReply,
  RuntimeBackendRequest,
} from "./runtime-contracts";
import { isRecord } from "./runtime-contracts";
import type { SidecarManager } from "./sidecar";

const RESPONSE_LIMIT_BYTES = 16 * 1024 * 1024;
const REQUEST_TIMEOUT_MS = 30_000;
const STREAM_TIMEOUT_MS = 15 * 60_000;
const ORCHESTRATION_STREAM_TIMEOUT_MS = 4 * 60 * 60_000;
const STREAM_OPERATIONS = new Set([
  "stream_agent_run_api_v1_agent_runs__run_id__stream_post",
  "orchestrate_workflow_stage_api_v1_workflows__workflow_id__orchestration_stream_post",
]);
const WORKFLOW_ID_PATTERN = /^workflow_[a-z0-9]+$/;

function errorPayload(code: string, message: string, retryable: boolean): unknown {
  return { error: { code, message, retryable, details: {} } };
}

function errorReply(
  requestId: string,
  statusCode: number,
  code: string,
  message: string,
  retryable = false,
): RuntimeBackendReply {
  return { requestId, statusCode, payload: errorPayload(code, message, retryable) };
}

function pathWorkflowId(parameters: unknown): string | null {
  if (!isRecord(parameters) || !isRecord(parameters.path)) {
    return null;
  }
  const workflowId = parameters.path.workflow_id;
  return typeof workflowId === "string" && WORKFLOW_ID_PATTERN.test(workflowId)
    ? workflowId
    : null;
}

function responseWorkflowId(payload: unknown): string | null {
  if (!isRecord(payload)) {
    return null;
  }
  const direct = payload.id;
  if (typeof direct === "string" && WORKFLOW_ID_PATTERN.test(direct)) {
    return direct;
  }
  if (isRecord(payload.workflow)) {
    const workflow = payload.workflow;
    if (typeof workflow.id === "string" && WORKFLOW_ID_PATTERN.test(workflow.id)) {
      return workflow.id;
    }
    if (
      isRecord(workflow.workflow) &&
      typeof workflow.workflow.id === "string" &&
      WORKFLOW_ID_PATTERN.test(workflow.workflow.id)
    ) {
      return workflow.workflow.id;
    }
  }
  return null;
}

async function responsePayload(response: Response): Promise<unknown> {
  const declared = Number(response.headers.get("content-length") ?? "0");
  if (Number.isFinite(declared) && declared > RESPONSE_LIMIT_BYTES) {
    throw new Error("Backend response exceeded the desktop response size limit");
  }
  const bytes = new Uint8Array(await response.arrayBuffer());
  if (bytes.byteLength > RESPONSE_LIMIT_BYTES) {
    throw new Error("Backend response exceeded the desktop response size limit");
  }
  if (bytes.byteLength === 0) {
    return null;
  }
  const content = new TextDecoder().decode(bytes);
  const contentType = response.headers.get("content-type")?.split(";", 1)[0]?.trim().toLowerCase();
  if (contentType === "application/x-ndjson") {
    return content
      .split(/\r?\n/u)
      .filter((line) => line.trim() !== "")
      .map((line) => JSON.parse(line) as unknown);
  }
  if (contentType === "text/plain") {
    return content;
  }
  return JSON.parse(content);
}

async function streamPayload(
  response: Response,
  onFrame: (frame: unknown) => void,
): Promise<void> {
  const contentType = response.headers.get("content-type")?.split(";", 1)[0]?.trim().toLowerCase();
  if (contentType !== "application/x-ndjson" || response.body === null) {
    throw new Error("Backend stream response is not NDJSON");
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffered = "";
  let receivedBytes = 0;

  const emitLines = (final: boolean) => {
    const lines = buffered.split(/\r?\n/u);
    buffered = final ? "" : (lines.pop() ?? "");
    for (const line of lines) {
      if (line.trim() !== "") {
        onFrame(JSON.parse(line) as unknown);
      }
    }
  };

  for (;;) {
    const { done, value } = await reader.read();
    if (done) {
      buffered += decoder.decode();
      emitLines(true);
      return;
    }
    receivedBytes += value.byteLength;
    if (receivedBytes > RESPONSE_LIMIT_BYTES) {
      await reader.cancel("Backend stream exceeded the desktop response size limit");
      throw new Error("Backend stream exceeded the desktop response size limit");
    }
    buffered += decoder.decode(value, { stream: true });
    emitLines(false);
  }
}

export class BackendClient {
  private workflowObserver: ((workflowId: string) => void) | null = null;

  constructor(
    private readonly sidecar: SidecarManager,
    private readonly operations: OperationMap,
    private readonly localPaths: LocalPathPolicy,
  ) {}

  setWorkflowObserver(observer: (workflowId: string) => void): void {
    this.workflowObserver = observer;
  }

  execute(
    request: RuntimeBackendRequest,
    kind: "query" | "command",
  ): Promise<RuntimeBackendReply> {
    return this.executeRequest(request, kind);
  }

  async executeStream(
    request: RuntimeBackendRequest,
    onFrame: (frame: unknown) => void,
  ): Promise<RuntimeBackendReply> {
    if (!STREAM_OPERATIONS.has(request.operationId)) {
      return errorReply(
        request.requestId,
        400,
        "desktop.stream_operation_forbidden",
        "Only frozen AgentRun and orchestration operations may use the stream channel",
      );
    }
    try {
      const connection = await this.sidecar.connection();
      const fetchRequest = buildBackendFetchRequest({
        request,
        kind: "command",
        operations: this.operations,
        origin: connection.origin,
        sessionToken: connection.sessionToken,
        timeoutSignal: AbortSignal.timeout(
          request.operationId ===
            "orchestrate_workflow_stage_api_v1_workflows__workflow_id__orchestration_stream_post"
            ? ORCHESTRATION_STREAM_TIMEOUT_MS
            : STREAM_TIMEOUT_MS,
        ),
      });
      const response = await fetch(fetchRequest.url, fetchRequest.init);
      if (!response.ok) {
        return {
          requestId: request.requestId,
          statusCode: response.status,
          payload: await responsePayload(response),
        };
      }
      await streamPayload(response, (frame) => {
        this.localPaths.observeBackendPayload(frame);
        onFrame(frame);
      });
      return { requestId: request.requestId, statusCode: response.status, payload: null };
    } catch (error) {
      if (error instanceof BackendRequestValidationError) {
        return errorReply(request.requestId, 400, error.code, error.message);
      }
      return errorReply(
        request.requestId,
        503,
        "desktop.backend_stream_failed",
        "Desktop backend stream failed",
        true,
      );
    }
  }

  async executeInternal(
    operationId: string,
    parameters?: unknown,
    payload?: unknown,
  ): Promise<RuntimeBackendReply> {
    const operation = this.operations[operationId];
    if (operation === undefined) {
      throw new Error("Internal desktop operation is missing from the frozen manifest");
    }
    const request: RuntimeBackendRequest = { operationId, requestId: randomUUID() };
    if (parameters !== undefined) {
      request.parameters = parameters;
    }
    if (payload !== undefined) {
      request.payload = payload;
    }
    return this.executeRequest(request, operation.method === "GET" ? "query" : "command");
  }

  private async executeRequest(
    request: RuntimeBackendRequest,
    kind: "query" | "command",
  ): Promise<RuntimeBackendReply> {
    try {
      const connection = await this.sidecar.connection();
      const fetchRequest = buildBackendFetchRequest({
        request,
        kind,
        operations: this.operations,
        origin: connection.origin,
        sessionToken: connection.sessionToken,
        timeoutSignal: AbortSignal.timeout(REQUEST_TIMEOUT_MS),
      });
      const response = await fetch(fetchRequest.url, fetchRequest.init);
      const payload = await responsePayload(response);
      this.localPaths.observeBackendPayload(payload);
      if (response.ok) {
        const workflowId = pathWorkflowId(request.parameters) ?? responseWorkflowId(payload);
        if (workflowId !== null) {
          this.workflowObserver?.(workflowId);
        }
      }
      return { requestId: request.requestId, statusCode: response.status, payload };
    } catch (error) {
      if (error instanceof BackendRequestValidationError) {
        return errorReply(request.requestId, 400, error.code, error.message);
      }
      return errorReply(
        request.requestId,
        503,
        "desktop.backend_unavailable",
        "Desktop backend is unavailable",
        true,
      );
    }
  }
}
