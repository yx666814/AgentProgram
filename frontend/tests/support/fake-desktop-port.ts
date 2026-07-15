import type {
  BackendOperationId,
  BackendReply,
  BackendRequest,
  DesktopPort,
  PersistedEvent,
} from "../../electron/desktop-port";

type RequestHandler = (request: BackendRequest) => BackendReply | Promise<BackendReply>;

export interface FakeDesktopPortOptions {
  command?: RequestHandler;
  confirmResult?: boolean;
  directory?: { cancelled: boolean; path?: string };
  query?: RequestHandler;
}

export interface FakeDesktopPort extends DesktopPort {
  calls: {
    commands: BackendRequest[];
    confirms: Array<{ title: string; message: string; detail: string; confirmLabel: string }>;
    queries: BackendRequest[];
    replays: number[];
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
