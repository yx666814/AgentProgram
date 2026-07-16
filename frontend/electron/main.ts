import { stat } from "node:fs/promises";
import { join } from "node:path";
import { randomUUID } from "node:crypto";

import {
  app,
  BrowserWindow,
  dialog,
  ipcMain,
  type IpcMainInvokeEvent,
  Notification,
  screen,
  session,
  shell,
} from "electron";

import { BackendClient } from "./backend-client";
import { DiagnosticsExporter } from "./diagnostics-export";
import { EventProxy } from "./event-proxy";
import { IPC_CHANNELS } from "./ipc-channels";
import { LocalPathPolicy } from "./local-path-policy";
import { loadOperationMap } from "./operation-map";
import type { RuntimeBackendRequest } from "./runtime-contracts";
import { isRecord } from "./runtime-contracts";
import { SecretBridgeServer, type SecretBridgeConnection } from "./secret-bridge";
import { EncryptedSecretStore } from "./secret-store";
import { SidecarManager } from "./sidecar";

const MAX_NATIVE_TEXT = 4_096;
let activeSidecar: SidecarManager | null = null;
let activeSecretBridge: SecretBridgeServer | null = null;

app.setName("星协");
app.setPath("userData", join(app.getPath("appData"), "星协"));

function boundedText(value: unknown, field: string): string {
  if (typeof value !== "string" || value.length === 0 || value.length > MAX_NATIVE_TEXT) {
    throw new Error(`${field} is invalid`);
  }
  return value;
}

function backendRequest(value: unknown): RuntimeBackendRequest {
  if (
    !isRecord(value) ||
    typeof value.operationId !== "string" ||
    typeof value.requestId !== "string"
  ) {
    throw new Error("Backend request does not match the desktop contract");
  }
  const request: RuntimeBackendRequest = {
    operationId: value.operationId,
    requestId: value.requestId,
  };
  if (value.parameters !== undefined) {
    request.parameters = value.parameters;
  }
  if (value.payload !== undefined) {
    request.payload = value.payload;
  }
  return request;
}

function assertTrustedSender(event: IpcMainInvokeEvent, window: BrowserWindow): void {
  if (
    event.sender !== window.webContents ||
    event.senderFrame !== window.webContents.mainFrame ||
    event.sender.isDestroyed()
  ) {
    throw new Error("Desktop IPC call did not originate from the main renderer frame");
  }
}

function createWindow(showWhenReady: boolean): BrowserWindow {
  const window = new BrowserWindow({
    width: 1440,
    height: 900,
    minWidth: 1080,
    minHeight: 680,
    show: false,
    backgroundColor: "#f4f4f2",
    title: "星协",
    titleBarStyle: "hidden",
    titleBarOverlay: {
      color: "#f4f4f2",
      symbolColor: "#202326",
      height: 34,
    },
    webPreferences: {
      preload: join(app.getAppPath(), "dist", "electron", "preload.cjs"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      webSecurity: true,
      allowRunningInsecureContent: false,
      spellcheck: false,
    },
  });
  window.webContents.setWindowOpenHandler(() => ({ action: "deny" }));
  window.webContents.on("will-navigate", (event) => {
    event.preventDefault();
  });
  window.webContents.on("will-attach-webview", (event) => {
    event.preventDefault();
  });
  if (showWhenReady) {
    window.once("ready-to-show", () => {
      window.show();
    });
  }
  return window;
}

async function loadRenderer(window: BrowserWindow): Promise<void> {
  await window.loadFile(join(app.getAppPath(), "dist", "renderer", "index.html"));
}

async function runDesktopSmoke(
  window: BrowserWindow,
  secretBridge: SecretBridgeConnection,
): Promise<void> {
  const smokeSecret = `smoke-${randomUUID()}`;
  const result: unknown = await window.webContents.executeJavaScript(`Promise.all([
    window.desktop.backend.query({ operationId: "health_api_v1_health_get", requestId: "smoke-health" }),
    window.desktop.backend.query({ operationId: "readiness_api_v1_readiness_get", requestId: "smoke-readiness" }),
    window.desktop.backend.query({ operationId: "desktop_control_api_v1_system_control_get", requestId: "smoke-control" }),
    window.desktop.getWindowState(),
    window.desktop.secrets.store({ value: ${JSON.stringify(smokeSecret)}, label: "Desktop smoke" })
  ]).then(([health, readiness, control, windowState, secretReference]) => ({
    health,
    readiness,
    control,
    windowState,
    route: window.location.hash,
    secretReference
  }))`);
  if (!isRecord(result)) {
    throw new Error("Desktop smoke result is invalid");
  }
  for (const name of ["health", "readiness", "control"] as const) {
    const reply = result[name];
    if (!isRecord(reply) || reply.statusCode !== 200) {
      throw new Error(`Desktop smoke ${name} request failed: ${JSON.stringify(reply)}`);
    }
  }
  const secretReference = result.secretReference;
  if (!isRecord(secretReference) || typeof secretReference.credentialRef !== "string") {
    throw new Error("Desktop smoke secret write failed");
  }
  try {
    const bridgeResponse = await fetch(`${secretBridge.origin}/v1/resolve`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${secretBridge.token}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ credential_ref: secretReference.credentialRef }),
    });
    const bridgePayload: unknown = await bridgeResponse.json();
    if (!isRecord(bridgePayload) || bridgePayload.value !== smokeSecret) {
      throw new Error("Desktop smoke secret bridge resolution failed");
    }
  } finally {
    await window.webContents.executeJavaScript(
      `window.desktop.secrets.delete(${JSON.stringify(secretReference.credentialRef)})`,
    );
  }
  process.stdout.write(`XINGXIE_DESKTOP_SMOKE ${JSON.stringify(result)}\n`);
}

function registerIpc(input: {
  window: BrowserWindow;
  backend: BackendClient;
  events: EventProxy;
  localPaths: LocalPathPolicy;
  secrets: EncryptedSecretStore;
  diagnostics: DiagnosticsExporter;
}): void {
  const { backend, diagnostics, events, localPaths, secrets, window } = input;
  const handle = (
    channel: string,
    listener: (event: IpcMainInvokeEvent, args: readonly unknown[]) => unknown,
  ) => {
    ipcMain.handle(channel, (event, ...args: unknown[]) => {
      assertTrustedSender(event, window);
      return listener(event, args);
    });
  };
  handle(IPC_CHANNELS.backendQuery, (_event, args) =>
    backend.execute(backendRequest(args[0]), "query"),
  );
  handle(IPC_CHANNELS.backendCommand, (_event, args) =>
    backend.execute(backendRequest(args[0]), "command"),
  );
  handle(IPC_CHANNELS.backendReplay, (_event, args) => {
    const afterEventId = args[0];
    if (typeof afterEventId !== "number") {
      throw new Error("Replay cursor is invalid");
    }
    return events.requestReplay(afterEventId);
  });
  handle(IPC_CHANNELS.secretStore, (_event, args) => {
    const value = args[0];
    if (!isRecord(value)) {
      throw new Error("Secret write input is invalid");
    }
    return secrets.store(
      boundedText(value.value, "Secret value"),
      boundedText(value.label, "Secret label"),
    );
  });
  handle(IPC_CHANNELS.secretDelete, (_event, args) =>
    secrets.delete(boundedText(args[0], "Credential reference")),
  );
  handle(IPC_CHANNELS.diagnosticsExport, async (_event, args) => {
    const value = args[0];
    if (!isRecord(value)) {
      throw new Error("Diagnostics export input is invalid");
    }
    const result = await dialog.showSaveDialog(window, {
      title: "导出脱敏诊断包",
      defaultPath: join(
        app.getPath("documents"),
        `xingxie-diagnostics-${new Date().toISOString().replace(/[:.]/gu, "-")}.json`,
      ),
      filters: [{ name: "JSON", extensions: ["json"] }],
      properties: ["createDirectory", "showOverwriteConfirmation"],
    });
    if (result.canceled || result.filePath === "") {
      return { cancelled: true };
    }
    const exportInput: { workflowId?: string; afterEventId?: number } = {};
    if (typeof value.workflowId === "string" && value.workflowId.trim() !== "") {
      exportInput.workflowId = value.workflowId;
    }
    if (typeof value.afterEventId === "number") {
      exportInput.afterEventId = value.afterEventId;
    }
    await diagnostics.write(result.filePath, exportInput);
    return { cancelled: false, path: result.filePath };
  });
  handle(IPC_CHANNELS.selectDirectory, async () => {
    const result = await dialog.showOpenDialog(window, {
      title: "选择本地项目目录",
      properties: ["openDirectory", "createDirectory"],
    });
    const path = result.filePaths[0];
    if (result.canceled || path === undefined) {
      return { cancelled: true };
    }
    localPaths.allowSelectedRoot(path);
    return { cancelled: false, path };
  });
  handle(IPC_CHANNELS.showConfirm, async (_event, args) => {
    const value = args[0];
    if (!isRecord(value)) {
      throw new Error("Native confirmation input is invalid");
    }
    const result = await dialog.showMessageBox(window, {
      type: "warning",
      title: boundedText(value.title, "Confirmation title"),
      message: boundedText(value.message, "Confirmation message"),
      detail: boundedText(value.detail, "Confirmation detail"),
      buttons: [boundedText(value.confirmLabel, "Confirmation label"), "取消"],
      defaultId: 1,
      cancelId: 1,
      noLink: true,
    });
    return result.response === 0;
  });
  const notificationRecords = new Set<string>();
  handle(IPC_CHANNELS.showNotification, (_event, args) => {
    const value = args[0];
    if (!isRecord(value)) {
      throw new Error("System notification input is invalid");
    }
    const recordId = boundedText(value.recordId, "Notification record id");
    if (!notificationRecords.has(recordId) && Notification.isSupported()) {
      notificationRecords.add(recordId);
      new Notification({
        title: boundedText(value.title, "Notification title"),
        body: boundedText(value.body, "Notification body"),
      }).show();
    }
  });
  handle(IPC_CHANNELS.openLocalLocation, async (_event, args) => {
    const value = args[0];
    const path = localPaths.assertAllowed(boundedText(value, "Local path"));
    const info = await stat(path);
    if (info.isFile()) {
      shell.showItemInFolder(path);
      return;
    }
    const error = await shell.openPath(path);
    if (error !== "") {
      throw new Error("The local location could not be opened");
    }
  });
  handle(IPC_CHANNELS.getWindowState, () => ({
    maximized: window.isMaximized(),
    scaleFactor: screen.getDisplayMatching(window.getBounds()).scaleFactor,
  }));
  handle(IPC_CHANNELS.requestWindowClose, () => {
    setImmediate(() => {
      app.quit();
    });
    return { allowed: true };
  });
}

async function bootstrap(): Promise<void> {
  const smokeMode = process.argv.includes("--desktop-smoke-test");
  app.setAppUserModelId("com.xingxie.agentprogram");
  session.defaultSession.setPermissionRequestHandler((_webContents, _permission, callback) => {
    callback(false);
  });
  session.defaultSession.setPermissionCheckHandler(() => false);
  const operationMap = await loadOperationMap(
    join(app.getAppPath(), "contracts", "capabilities.json"),
  );
  const secrets = new EncryptedSecretStore(
    join(app.getPath("userData"), "secrets", "credentials.v1.json"),
  );
  const secretBridge = new SecretBridgeServer(secrets);
  activeSecretBridge = secretBridge;
  const secretBridgeConnection = await secretBridge.start();
  const sidecar = new SidecarManager(secretBridgeConnection);
  activeSidecar = sidecar;
  const localPaths = new LocalPathPolicy();
  const backend = new BackendClient(sidecar, operationMap, localPaths);
  const diagnostics = new DiagnosticsExporter(
    backend,
    sidecar,
    join(app.getAppPath(), "contracts", "SHA256SUMS.json"),
  );
  const window = createWindow(!smokeMode);
  const events = new EventProxy(backend, sidecar, window.webContents);
  backend.setWorkflowObserver((workflowId) => {
    events.observeWorkflow(workflowId);
  });
  registerIpc({ window, backend, diagnostics, events, localPaths, secrets });
  void sidecar.start();

  let shutdownStarted = false;
  let allowQuit = false;
  const shutdown = async () => {
    if (shutdownStarted) {
      return;
    }
    shutdownStarted = true;
    events.stop();
    try {
      await sidecar.stop();
    } finally {
      await secretBridge.stop();
    }
  };
  app.on("before-quit", (event) => {
    if (allowQuit) {
      return;
    }
    event.preventDefault();
    void shutdown().finally(() => {
      allowQuit = true;
      app.quit();
    });
  });
  app.on("window-all-closed", () => {
    app.quit();
  });
  app.on("second-instance", () => {
    if (window.isMinimized()) {
      window.restore();
    }
    window.show();
    window.focus();
  });
  window.webContents.on("render-process-gone", () => {
    app.quit();
  });
  await loadRenderer(window);
  if (smokeMode) {
    try {
      await runDesktopSmoke(window, secretBridgeConnection);
    } catch (error) {
      process.exitCode = 1;
      process.stderr.write(
        `XINGXIE_DESKTOP_SMOKE_FAILED ${error instanceof Error ? error.message : "unknown error"}\n`,
      );
    } finally {
      app.quit();
    }
  }
}

const hasSingleInstanceLock = app.requestSingleInstanceLock();
if (!hasSingleInstanceLock) {
  app.quit();
} else {
  void app.whenReady().then(bootstrap).catch(() => {
    const cleanup = Promise.all([
      activeSidecar?.stop() ?? Promise.resolve(),
      activeSecretBridge?.stop() ?? Promise.resolve(),
    ]);
    void cleanup.finally(() => {
      app.exit(1);
    });
  });
}
