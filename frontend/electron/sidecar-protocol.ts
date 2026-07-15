import type { SidecarConnection } from "./runtime-contracts";
import { isRecord } from "./runtime-contracts";

export const READY_PREFIX = "AGENT_PLATFORM_READY ";
export const MAX_READY_FRAME_BYTES = 4096;

export interface ReadyFrame {
  protocol_version: 1;
  status: "ready";
  host: "127.0.0.1";
  port: number;
  pid: number;
}

export function parseReadyFrame(line: string): ReadyFrame {
  if (Buffer.byteLength(line, "utf8") > MAX_READY_FRAME_BYTES || !line.startsWith(READY_PREFIX)) {
    throw new Error("Sidecar emitted an invalid ready control frame");
  }
  const value: unknown = JSON.parse(line.slice(READY_PREFIX.length));
  if (
    !isRecord(value) ||
    value.protocol_version !== 1 ||
    value.status !== "ready" ||
    value.host !== "127.0.0.1" ||
    typeof value.port !== "number" ||
    !Number.isInteger(value.port) ||
    value.port < 1 ||
    value.port > 65535 ||
    typeof value.pid !== "number" ||
    !Number.isInteger(value.pid) ||
    value.pid < 1
  ) {
    throw new Error("Sidecar ready control frame does not match protocol v1");
  }
  return value as unknown as ReadyFrame;
}

export function connectionFromReady(frame: ReadyFrame, sessionToken: string): SidecarConnection {
  return {
    host: frame.host,
    port: frame.port,
    pid: frame.pid,
    sessionToken,
    origin: `http://${frame.host}:${String(frame.port)}`,
  };
}

