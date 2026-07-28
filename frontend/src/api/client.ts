import type { BackendOperationId, BackendReply, BackendRequest } from "../../electron/desktop-port";
import { parseApiError } from "./errors";
import type { ApiRequestOptions, ApiResponse, ApiTransport } from "./transport";

export type RequestIdFactory = () => string;

function defaultRequestIdFactory(): string {
  return crypto.randomUUID();
}

function buildRequest(operationId: BackendOperationId, options: ApiRequestOptions): BackendRequest {
  const request: BackendRequest = {
    operationId,
    requestId: options.requestId ?? defaultRequestIdFactory(),
  };
  if (options.parameters !== undefined) {
    request.parameters = options.parameters;
  }
  if (options.payload !== undefined) {
    request.payload = options.payload;
  }
  return request;
}

export class ApiClient {
  constructor(
    private readonly transport: ApiTransport,
    private readonly requestIdFactory: RequestIdFactory = defaultRequestIdFactory,
  ) {}

  async query<T>(
    operationId: BackendOperationId,
    options: ApiRequestOptions = {},
  ): Promise<ApiResponse<T>> {
    return this.execute(operationId, options, "query");
  }

  async command<T>(
    operationId: BackendOperationId,
    options: ApiRequestOptions = {},
  ): Promise<ApiResponse<T>> {
    return this.execute(operationId, options, "command");
  }

  async stream(
    operationId: BackendOperationId,
    options: ApiRequestOptions,
    listener: (frame: unknown) => void,
  ): Promise<ApiResponse<null>> {
    const request = buildRequest(operationId, {
      ...options,
      requestId: options.requestId ?? this.requestIdFactory(),
    });
    const reply = await this.transport.stream(request, listener);
    if (reply.statusCode < 200 || reply.statusCode >= 300) {
      throw parseApiError(reply.statusCode, reply.payload, options.correlationId);
    }
    return { ...reply, operationId };
  }

  private async execute<T>(
    operationId: BackendOperationId,
    options: ApiRequestOptions,
    kind: "query" | "command",
  ): Promise<ApiResponse<T>> {
    const request = buildRequest(operationId, {
      ...options,
      requestId: options.requestId ?? this.requestIdFactory(),
    });
    const reply: BackendReply<T> = await this.transport[kind]<T>(request);
    if (reply.statusCode < 200 || reply.statusCode >= 300) {
      throw parseApiError(reply.statusCode, reply.payload, options.correlationId);
    }
    return { ...reply, operationId };
  }
}
