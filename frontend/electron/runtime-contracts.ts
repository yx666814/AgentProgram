export interface RuntimeBackendRequest {
  operationId: string;
  requestId: string;
  parameters?: unknown;
  payload?: unknown;
}

export interface RuntimeBackendReply<T = unknown> {
  requestId: string;
  statusCode: number;
  payload: T;
}

export interface OperationDefinition {
  method: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  path: string;
}

export type OperationMap = Readonly<Record<string, OperationDefinition>>;

export interface SidecarConnection {
  host: "127.0.0.1";
  port: number;
  pid: number;
  sessionToken: string;
  origin: string;
}

export function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

