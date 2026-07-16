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
