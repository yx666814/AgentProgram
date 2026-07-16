import type {
  OperationDefinition,
  OperationMap,
  RuntimeBackendRequest,
} from "./runtime-contracts";
import { isRecord } from "./runtime-contracts";

const REQUEST_ID_PATTERN = /^[A-Za-z0-9._:-]{1,160}$/;
const PATH_PARAMETER_PATTERN = /\{([^{}]+)\}/g;

export class BackendRequestValidationError extends Error {
  constructor(
    readonly code: string,
    message: string,
  ) {
    super(message);
    this.name = "BackendRequestValidationError";
  }
}

export interface BackendFetchRequest {
  operation: OperationDefinition;
  url: URL;
  init: RequestInit;
}

function parameterGroup(
  parameters: unknown,
  name: "path" | "query",
): Record<string, unknown> {
  if (parameters === undefined) {
    return {};
  }
  if (!isRecord(parameters)) {
    throw new BackendRequestValidationError(
      "desktop.invalid_parameters",
      "Backend request parameters must be an object",
    );
  }
  for (const key of Object.keys(parameters)) {
    if (key !== "path" && key !== "query") {
      throw new BackendRequestValidationError(
        "desktop.invalid_parameters",
        "Backend request parameters contain an unsupported group",
      );
    }
  }
  const group = parameters[name];
  if (group === undefined) {
    return {};
  }
  if (!isRecord(group)) {
    throw new BackendRequestValidationError(
      "desktop.invalid_parameters",
      `Backend ${name} parameters must be an object`,
    );
  }
  return group;
}

function scalar(value: unknown, field: string): string {
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  throw new BackendRequestValidationError(
    "desktop.invalid_parameters",
    `${field} must be a scalar value`,
  );
}

function buildPath(template: string, pathParameters: Record<string, unknown>): string {
  const used = new Set<string>();
  const path = template.replace(PATH_PARAMETER_PATTERN, (_, name: string) => {
    if (!(name in pathParameters)) {
      throw new BackendRequestValidationError(
        "desktop.missing_path_parameter",
        `Backend path parameter ${name} is missing`,
      );
    }
    used.add(name);
    return encodeURIComponent(scalar(pathParameters[name], `Path parameter ${name}`));
  });
  if (Object.keys(pathParameters).some((name) => !used.has(name))) {
    throw new BackendRequestValidationError(
      "desktop.unused_path_parameter",
      "Backend request contains a path parameter not present in the frozen operation",
    );
  }
  return path;
}

function appendQuery(url: URL, query: Record<string, unknown>): void {
  for (const [name, value] of Object.entries(query)) {
    if (value === null || value === undefined) {
      continue;
    }
    if (Array.isArray(value)) {
      for (const item of value) {
        url.searchParams.append(name, scalar(item, `Query parameter ${name}`));
      }
      continue;
    }
    url.searchParams.set(name, scalar(value, `Query parameter ${name}`));
  }
}

export function buildBackendFetchRequest(input: {
  request: RuntimeBackendRequest;
  kind: "query" | "command";
  operations: OperationMap;
  origin: string;
  sessionToken: string;
  timeoutSignal: AbortSignal;
}): BackendFetchRequest {
  const { kind, operations, origin, request, sessionToken, timeoutSignal } = input;
  if (!REQUEST_ID_PATTERN.test(request.requestId)) {
    throw new BackendRequestValidationError(
      "desktop.invalid_request_id",
      "Backend request id is invalid",
    );
  }
  if (!Object.hasOwn(operations, request.operationId)) {
    throw new BackendRequestValidationError(
      "desktop.unknown_operation",
      "Backend operation is not present in the frozen capability manifest",
    );
  }
  const operation = operations[request.operationId];
  if (operation === undefined) {
    throw new BackendRequestValidationError(
      "desktop.unknown_operation",
      "Backend operation is not present in the frozen capability manifest",
    );
  }
  if ((kind === "query") !== (operation.method === "GET")) {
    throw new BackendRequestValidationError(
      "desktop.operation_kind_mismatch",
      "Backend operation does not match the requested query/command channel",
    );
  }
  const pathParameters = parameterGroup(request.parameters, "path");
  const queryParameters = parameterGroup(request.parameters, "query");
  const url = new URL(buildPath(operation.path, pathParameters), origin);
  appendQuery(url, queryParameters);
  const headers = new Headers({
    Accept: "application/json",
    Authorization: `Bearer ${sessionToken}`,
    "X-Desktop-Request-Id": request.requestId,
  });
  const init: RequestInit = {
    method: operation.method,
    headers,
    redirect: "error",
    signal: timeoutSignal,
  };
  if (operation.method !== "GET") {
    headers.set("Content-Type", "application/json");
    init.body = JSON.stringify(request.payload ?? {});
  } else if (request.payload !== undefined) {
    throw new BackendRequestValidationError(
      "desktop.query_payload_forbidden",
      "GET operations cannot contain a request payload",
    );
  }
  return { operation, url, init };
}
