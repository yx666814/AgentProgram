import type { components, operations } from "../src/api/generated";

export type BackendOperationId = keyof operations;
export type PersistedEvent = components["schemas"]["EventEnvelope"];

export interface BackendRequest {
  operationId: BackendOperationId;
  requestId: string;
  parameters?: unknown;
  payload?: unknown;
}

export interface BackendReply<T = unknown> {
  requestId: string;
  statusCode: number;
  payload: T;
}

export interface DesktopPort {
  backend: {
    query<T>(request: BackendRequest): Promise<BackendReply<T>>;
    command<T>(request: BackendRequest): Promise<BackendReply<T>>;
    subscribe(listener: (event: PersistedEvent) => void): () => void;
    requestReplay(afterEventId: number): Promise<void>;
  };
  selectDirectory(): Promise<{ cancelled: boolean; path?: string }>;
  showNativeConfirm(input: {
    title: string;
    message: string;
    detail: string;
    confirmLabel: string;
  }): Promise<boolean>;
  showSystemNotification(input: {
    title: string;
    body: string;
    recordId: string;
  }): Promise<void>;
  openLocalLocation(path: string): Promise<void>;
  getWindowState(): Promise<{ maximized: boolean; scaleFactor: number }>;
  requestWindowClose(): Promise<{ allowed: boolean }>;
}

declare global {
  interface Window {
    desktop: DesktopPort;
  }
}
