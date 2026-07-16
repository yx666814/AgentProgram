import { contextBridge, ipcRenderer } from "electron";

import type { BackendReply, BackendRequest, DesktopPort, PersistedEvent } from "./desktop-port";
import { IPC_CHANNELS } from "./ipc-channels";

export function createDesktopPort(): DesktopPort {
  const backend = Object.freeze({
    query<T>(request: BackendRequest): Promise<BackendReply<T>> {
      return ipcRenderer.invoke(IPC_CHANNELS.backendQuery, request) as Promise<BackendReply<T>>;
    },
    command<T>(request: BackendRequest): Promise<BackendReply<T>> {
      return ipcRenderer.invoke(IPC_CHANNELS.backendCommand, request) as Promise<BackendReply<T>>;
    },
    subscribe(listener: (event: PersistedEvent) => void): () => void {
      const receive = (_event: Electron.IpcRendererEvent, event: PersistedEvent) => {
        listener(event);
      };
      ipcRenderer.on(IPC_CHANNELS.backendEvent, receive);
      return () => {
        ipcRenderer.removeListener(IPC_CHANNELS.backendEvent, receive);
      };
    },
    requestReplay(afterEventId: number): Promise<void> {
      return ipcRenderer.invoke(IPC_CHANNELS.backendReplay, afterEventId) as Promise<void>;
    },
  });
  return Object.freeze({
    backend,
    secrets: Object.freeze({
      store: (input: Parameters<DesktopPort["secrets"]["store"]>[0]) =>
        ipcRenderer.invoke(IPC_CHANNELS.secretStore, input) as ReturnType<
          DesktopPort["secrets"]["store"]
        >,
      delete: (credentialRef: string) =>
        ipcRenderer.invoke(IPC_CHANNELS.secretDelete, credentialRef) as ReturnType<
          DesktopPort["secrets"]["delete"]
        >,
    }),
    diagnostics: Object.freeze({
      export: (input: Parameters<DesktopPort["diagnostics"]["export"]>[0]) =>
        ipcRenderer.invoke(IPC_CHANNELS.diagnosticsExport, input) as ReturnType<
          DesktopPort["diagnostics"]["export"]
        >,
    }),
    selectDirectory: () =>
      ipcRenderer.invoke(IPC_CHANNELS.selectDirectory) as ReturnType<DesktopPort["selectDirectory"]>,
    showNativeConfirm: (input: Parameters<DesktopPort["showNativeConfirm"]>[0]) =>
      ipcRenderer.invoke(IPC_CHANNELS.showConfirm, input) as ReturnType<
        DesktopPort["showNativeConfirm"]
      >,
    showSystemNotification: (input: Parameters<DesktopPort["showSystemNotification"]>[0]) =>
      ipcRenderer.invoke(IPC_CHANNELS.showNotification, input) as ReturnType<
        DesktopPort["showSystemNotification"]
      >,
    openLocalLocation: (path: string) =>
      ipcRenderer.invoke(IPC_CHANNELS.openLocalLocation, path) as ReturnType<
        DesktopPort["openLocalLocation"]
      >,
    getWindowState: () =>
      ipcRenderer.invoke(IPC_CHANNELS.getWindowState) as ReturnType<DesktopPort["getWindowState"]>,
    requestWindowClose: () =>
      ipcRenderer.invoke(IPC_CHANNELS.requestWindowClose) as ReturnType<
        DesktopPort["requestWindowClose"]
      >,
  });
}

export function exposeDesktopPort(): void {
  contextBridge.exposeInMainWorld("desktop", createDesktopPort());
}

exposeDesktopPort();
