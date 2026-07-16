import { spawn, type ChildProcessWithoutNullStreams } from "node:child_process";
import { randomBytes } from "node:crypto";
import { join } from "node:path";

import { app } from "electron";

import type { SidecarConnection } from "./runtime-contracts";
import type { SecretBridgeConnection } from "./secret-bridge";
import {
  connectionFromReady,
  MAX_READY_FRAME_BYTES,
  parseReadyFrame,
} from "./sidecar-protocol";

const READY_TIMEOUT_MS = 30_000;
const SHUTDOWN_TIMEOUT_MS = 8_000;
const STDERR_LIMIT = 200;
const STARTUP_DIAGNOSTIC_LINES = 20;

interface SidecarCommand {
  command: string;
  args: string[];
  cwd: string;
}

function sidecarCommand(): SidecarCommand {
  if (app.isPackaged) {
    const executable = join(process.resourcesPath, "backend", "agent-platform-desktop-sidecar.exe");
    return { command: executable, args: [], cwd: join(process.resourcesPath, "backend") };
  }
  const backendRoot = join(app.getAppPath(), "..", "backend");
  return {
    command: "uv",
    args: ["run", "--project", backendRoot, "agent-platform-desktop-sidecar"],
    cwd: join(app.getAppPath(), ".."),
  };
}

function safeChildEnvironment(): NodeJS.ProcessEnv {
  return Object.fromEntries(
    Object.entries(process.env).filter(([name, value]) => {
      if (value === undefined || name.startsWith("AGENT_PLATFORM_")) {
        return false;
      }
      return !/(?:TOKEN|SECRET|PASSWORD|CREDENTIAL|API_KEY)/i.test(name);
    }),
  );
}

function waitForExit(child: ChildProcessWithoutNullStreams, timeoutMs: number): Promise<boolean> {
  if (child.exitCode !== null || child.signalCode !== null) {
    return Promise.resolve(true);
  }
  return new Promise((resolveExit) => {
    const timer = setTimeout(() => {
      cleanup();
      resolveExit(false);
    }, timeoutMs);
    const onExit = () => {
      cleanup();
      resolveExit(true);
    };
    const cleanup = () => {
      clearTimeout(timer);
      child.off("exit", onExit);
    };
    child.once("exit", onExit);
  });
}

export class SidecarManager {
  private child: ChildProcessWithoutNullStreams | null = null;
  private connectionPromise: Promise<SidecarConnection> | null = null;
  private sessionToken: string | null = null;
  private readonly stderrLines: string[] = [];

  constructor(private readonly secretBridge: SecretBridgeConnection) {}

  start(): Promise<SidecarConnection> {
    if (this.connectionPromise !== null) {
      return this.connectionPromise;
    }
    this.connectionPromise = this.spawnSidecar();
    return this.connectionPromise;
  }

  async connection(): Promise<SidecarConnection> {
    return this.start();
  }

  diagnostics(): readonly string[] {
    return this.stderrLines;
  }

  async publicState(): Promise<{ host: string; port: number; pid: number; status: "ready" }> {
    const connection = await this.connection();
    return {
      host: connection.host,
      port: connection.port,
      pid: connection.pid,
      status: "ready",
    };
  }

  async stop(): Promise<void> {
    const child = this.child;
    if (child === null) {
      return;
    }
    const connectionPromise = this.connectionPromise;
    let connection: SidecarConnection | null = null;
    try {
      connection = connectionPromise === null ? null : await connectionPromise;
    } catch {
      // A failed startup still needs process termination below.
    }
    if (connection !== null && child.exitCode === null) {
      try {
        await fetch(`${connection.origin}/api/v1/system/shutdown`, {
          method: "POST",
          headers: {
            Accept: "application/json",
            Authorization: `Bearer ${connection.sessionToken}`,
            "Content-Type": "application/json",
          },
          body: "{}",
          redirect: "error",
          signal: AbortSignal.timeout(3_000),
        });
      } catch {
        // The bounded process wait and forced termination remain authoritative.
      }
    }
    if (!(await waitForExit(child, SHUTDOWN_TIMEOUT_MS))) {
      child.kill();
      await waitForExit(child, 2_000);
    }
    this.child = null;
    this.connectionPromise = null;
    this.sessionToken = null;
  }

  private forgetChild(child: ChildProcessWithoutNullStreams): void {
    if (this.child !== child) {
      return;
    }
    this.child = null;
    this.connectionPromise = null;
    this.sessionToken = null;
  }

  private reportStartupFailure(error: Error): void {
    process.stderr.write(
      `XINGXIE_SIDECAR_START_FAILED ${JSON.stringify({
        message: error.message,
        stderr: this.stderrLines.slice(-STARTUP_DIAGNOSTIC_LINES),
      })}\n`,
    );
  }

  private spawnSidecar(): Promise<SidecarConnection> {
    const command = sidecarCommand();
    const sessionToken = randomBytes(32).toString("base64url");
    this.sessionToken = sessionToken;
    const child = spawn(command.command, command.args, {
      cwd: command.cwd,
      env: safeChildEnvironment(),
      windowsHide: true,
      stdio: ["pipe", "pipe", "pipe"],
    });
    this.child = child;
    const startupFrame = JSON.stringify({
      protocol_version: 1,
      session_token: sessionToken,
      data_root: app.getPath("userData"),
      parent_pid: process.pid,
      secret_bridge_origin: this.secretBridge.origin,
      secret_bridge_token: this.secretBridge.token,
      host: "127.0.0.1",
      port: 0,
    });
    child.stdin.end(startupFrame + "\n", "utf8");
    child.stderr.setEncoding("utf8");
    child.stderr.on("data", (chunk: string) => {
      const redacted = chunk.replaceAll(sessionToken, "[REDACTED]");
      for (const line of redacted.split(/\r?\n/u).filter(Boolean)) {
        this.stderrLines.push(line.slice(0, 4096));
      }
      if (this.stderrLines.length > STDERR_LIMIT) {
        this.stderrLines.splice(0, this.stderrLines.length - STDERR_LIMIT);
      }
    });
    return new Promise<SidecarConnection>((resolveConnection, rejectConnection) => {
      let stdout = "";
      let settled = false;
      const finishReject = (error: Error) => {
        if (settled) {
          return;
        }
        settled = true;
        clearTimeout(timer);
        this.reportStartupFailure(error);
        this.forgetChild(child);
        rejectConnection(error);
      };
      const timer = setTimeout(() => {
        finishReject(new Error("Sidecar did not emit a ready frame before the startup deadline"));
        child.kill();
      }, READY_TIMEOUT_MS);
      child.stdout.setEncoding("utf8");
      child.stdout.on("data", (chunk: string) => {
        if (settled && chunk.trim() !== "") {
          child.kill();
          return;
        }
        stdout += chunk;
        if (Buffer.byteLength(stdout, "utf8") > MAX_READY_FRAME_BYTES + 1) {
          finishReject(new Error("Sidecar ready frame exceeded its size limit"));
          child.kill();
          return;
        }
        const newline = stdout.indexOf("\n");
        if (newline < 0) {
          return;
        }
        const line = stdout.slice(0, newline).replace(/\r$/u, "");
        const remainder = stdout.slice(newline + 1);
        if (remainder.trim() !== "") {
          finishReject(new Error("Sidecar stdout contained data outside the ready control frame"));
          child.kill();
          return;
        }
        try {
          const frame = parseReadyFrame(line);
          if (app.isPackaged && frame.pid !== child.pid) {
            throw new Error("Sidecar ready frame process id does not match the spawned process");
          }
          settled = true;
          clearTimeout(timer);
          resolveConnection(connectionFromReady(frame, sessionToken));
        } catch (error) {
          finishReject(error instanceof Error ? error : new Error("Sidecar ready frame is invalid"));
          child.kill();
        }
      });
      child.once("error", (error) => {
        finishReject(new Error(`Sidecar process could not start: ${error.message}`));
      });
      child.once("exit", (code, signal) => {
        if (!settled) {
          finishReject(
            new Error(
              `Sidecar exited before ready (code=${String(code)}, signal=${String(signal)})`,
            ),
          );
          return;
        }
        this.forgetChild(child);
      });
    });
  }
}
