import type {
  BackendOperationId,
  BackendReply,
  BackendRequest,
  DesktopPort,
  PersistedEvent,
} from "../../electron/desktop-port";

export interface ApiTransport {
  query<T>(request: BackendRequest): Promise<BackendReply<T>>;
  command<T>(request: BackendRequest): Promise<BackendReply<T>>;
  stream(request: BackendRequest, listener: (frame: unknown) => void): Promise<BackendReply<null>>;
  subscribe(listener: (event: PersistedEvent) => void): () => void;
  requestReplay(afterEventId: number): Promise<void>;
}

export function createDesktopTransport(port: DesktopPort): ApiTransport {
  return {
    query: <T>(request: BackendRequest) => port.backend.query<T>(request),
    command: <T>(request: BackendRequest) => port.backend.command<T>(request),
    stream: (request: BackendRequest, listener: (frame: unknown) => void) =>
      port.backend.stream(request, listener),
    subscribe: (listener) => port.backend.subscribe(listener),
    requestReplay: (afterEventId) => port.backend.requestReplay(afterEventId),
  };
}

export interface ApiRequestOptions {
  requestId?: string;
  correlationId?: string;
  parameters?: unknown;
  payload?: unknown;
}

export interface ApiResponse<T> extends BackendReply<T> {
  operationId: BackendOperationId;
}
