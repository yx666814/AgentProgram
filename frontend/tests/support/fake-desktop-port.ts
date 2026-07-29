import type {
  BackendOperationId,
  BackendReply,
  BackendRequest,
  DesktopPort,
  PersistedEvent,
} from "../../electron/desktop-port";

type RequestHandler = (request: BackendRequest) => BackendReply | Promise<BackendReply>;
type StreamHandler = (
  request: BackendRequest,
  emit: (frame: unknown) => void,
) => BackendReply<null> | Promise<BackendReply<null>>;

export interface FakeDesktopPortOptions {
  command?: RequestHandler;
  confirmResult?: boolean;
  directory?: { cancelled: boolean; path?: string };
  query?: RequestHandler;
  stream?: StreamHandler;
}

export interface FakeDesktopPort extends DesktopPort {
  calls: {
    commands: BackendRequest[];
    confirms: Array<{ title: string; message: string; detail: string; confirmLabel: string }>;
    queries: BackendRequest[];
    replays: number[];
    streams: BackendRequest[];
    secretDeletes: string[];
    secretStores: Array<{ value: string; label: string }>;
    diagnosticsExports: Array<{ workflowId?: string; afterEventId?: number }>;
  };
  emit(event: PersistedEvent): void;
}

function unexpected(kind: string, operationId: BackendOperationId): never {
  throw new Error(`Unexpected ${kind}: ${operationId}`);
}

export function reply(request: BackendRequest, payload: unknown, statusCode = 200): BackendReply {
  return { requestId: request.requestId, statusCode, payload };
}

export function createFakeDesktopPort(options: FakeDesktopPortOptions = {}): FakeDesktopPort {
  const listeners = new Set<(event: PersistedEvent) => void>();
  const calls: FakeDesktopPort["calls"] = {
    commands: [],
    confirms: [],
    queries: [],
    replays: [],
    secretDeletes: [],
    secretStores: [],
    diagnosticsExports: [],
    streams: [],
  };

  return {
    calls,
    backend: {
      async query<T>(request: BackendRequest): Promise<BackendReply<T>> {
        calls.queries.push(request);
        const response = await (options.query?.(request) ?? unexpected("query", request.operationId));
        return response as BackendReply<T>;
      },
      async command<T>(request: BackendRequest): Promise<BackendReply<T>> {
        calls.commands.push(request);
        const response = await (options.command?.(request) ?? unexpected("command", request.operationId));
        return response as BackendReply<T>;
      },
      async stream(
        request: BackendRequest,
        listener: (frame: unknown) => void,
      ): Promise<BackendReply<null>> {
        calls.streams.push(request);
        return options.stream?.(request, listener) ??
          unexpected("stream", request.operationId);
      },
      subscribe(listener: (event: PersistedEvent) => void): () => void {
        listeners.add(listener);
        return () => {
          listeners.delete(listener);
        };
      },
      requestReplay(afterEventId: number): Promise<void> {
        calls.replays.push(afterEventId);
        return Promise.resolve();
      },
    },
    secrets: {
      store(input) {
        calls.secretStores.push(input);
        return Promise.resolve({
          credentialRef: "credential.xingxie.00000000000000000000000000000000",
          maskedHint:
            input.value.length <= 4
              ? "****"
              : `${input.value.slice(0, 3)}****${input.value.slice(-4)}`,
        });
      },
      delete(credentialRef) {
        calls.secretDeletes.push(credentialRef);
        return Promise.resolve();
      },
    },
    diagnostics: {
      export(input) {
        calls.diagnosticsExports.push(input);
        return Promise.resolve({ cancelled: false, path: "D:\\Temp\\xingxie-diagnostics.json" });
      },
    },
    selectDirectory() {
      return Promise.resolve(options.directory ?? { cancelled: true });
    },
    showNativeConfirm(input) {
      calls.confirms.push(input);
      return Promise.resolve(options.confirmResult ?? true);
    },
    async showSystemNotification() {},
    async openLocalLocation() {},
    getWindowState() {
      return Promise.resolve({ maximized: false, scaleFactor: 1 });
    },
    requestWindowClose() {
      return Promise.resolve({ allowed: true });
    },
    emit(event) {
      for (const listener of listeners) {
        listener(event);
      }
    },
  };
}
