import type { WebContents } from "electron";

import type { BackendClient } from "./backend-client";
import { IPC_CHANNELS } from "./ipc-channels";
import { isRecord } from "./runtime-contracts";
import type { SidecarManager } from "./sidecar";

const TICKET_OPERATION = "issue_event_ticket_api_v1_events_tickets_post";
const MAX_RECONNECT_DELAY_MS = 5_000;

function eventEnvelope(value: unknown): Record<string, unknown> | null {
  if (
    !isRecord(value) ||
    value.schema_version !== 1 ||
    typeof value.event_id !== "number" ||
    !Number.isInteger(value.event_id) ||
    value.event_id < 1 ||
    typeof value.event_type !== "string"
  ) {
    return null;
  }
  return value;
}

export class EventProxy {
  private activeWorkflowId: string | null = null;
  private lastEventId = 0;
  private socket: WebSocket | null = null;
  private generation = 0;
  private reconnectAttempt = 0;
  private reconnectTimer: NodeJS.Timeout | null = null;
  private stopped = false;

  constructor(
    private readonly backend: BackendClient,
    private readonly sidecar: SidecarManager,
    private readonly target: WebContents,
  ) {}

  observeWorkflow(workflowId: string): void {
    if (this.activeWorkflowId === workflowId) {
      return;
    }
    this.activeWorkflowId = workflowId;
    this.reconnectAttempt = 0;
    this.restart();
  }

  requestReplay(afterEventId: number): Promise<void> {
    if (!Number.isInteger(afterEventId) || afterEventId < 0) {
      return Promise.reject(new Error("Replay cursor must be a non-negative integer"));
    }
    this.lastEventId = Math.max(this.lastEventId, afterEventId);
    if (this.activeWorkflowId !== null && this.socket === null) {
      this.restart();
    }
    return Promise.resolve();
  }

  stop(): void {
    this.stopped = true;
    this.generation += 1;
    if (this.reconnectTimer !== null) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    this.socket?.close(1000, "desktop shutdown");
    this.socket = null;
  }

  private restart(): void {
    this.generation += 1;
    const generation = this.generation;
    if (this.reconnectTimer !== null) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    this.socket?.close(1000, "workflow changed");
    this.socket = null;
    if (!this.stopped) {
      void this.connect(generation);
    }
  }

  private async connect(generation: number): Promise<void> {
    const workflowId = this.activeWorkflowId;
    if (workflowId === null || generation !== this.generation || this.stopped) {
      return;
    }
    try {
      const [connection, ticketReply] = await Promise.all([
        this.sidecar.connection(),
        this.backend.executeInternal(TICKET_OPERATION, undefined, { workflow_id: workflowId }),
      ]);
      if (
        ticketReply.statusCode !== 201 ||
        !isRecord(ticketReply.payload) ||
        typeof ticketReply.payload.ticket !== "string" ||
        typeof ticketReply.payload.websocket_path !== "string" ||
        !ticketReply.payload.websocket_path.startsWith("/api/v1/")
      ) {
        throw new Error("Backend did not issue a valid event ticket");
      }
      if (generation !== this.generation) {
        return;
      }
      const url = new URL(ticketReply.payload.websocket_path, connection.origin);
      url.protocol = "ws:";
      url.searchParams.set("ticket", ticketReply.payload.ticket);
      url.searchParams.set("after_event_id", String(this.lastEventId));
      const socket = new WebSocket(url);
      this.socket = socket;
      socket.addEventListener("open", () => {
        this.reconnectAttempt = 0;
      });
      socket.addEventListener("message", (message) => {
        this.receive(message.data);
      });
      socket.addEventListener("error", () => {
        socket.close();
      });
      socket.addEventListener("close", () => {
        if (this.socket === socket) {
          this.socket = null;
          this.scheduleReconnect(generation);
        }
      });
    } catch {
      this.scheduleReconnect(generation);
    }
  }

  private receive(data: unknown): void {
    if (typeof data !== "string") {
      this.socket?.close(1003, "event frame must be text");
      return;
    }
    let message: unknown;
    try {
      message = JSON.parse(data);
    } catch {
      this.socket?.close(1007, "event frame must be JSON");
      return;
    }
    if (!isRecord(message) || message.schema_version !== 1 || typeof message.type !== "string") {
      this.socket?.close(1007, "event frame is invalid");
      return;
    }
    if (message.type === "ready") {
      return;
    }
    if (message.type !== "event" || typeof message.event_id !== "number") {
      this.socket?.close(1007, "event frame type is invalid");
      return;
    }
    const event = eventEnvelope(message.event);
    if (event === null || event.event_id !== message.event_id) {
      this.socket?.close(1007, "event envelope is invalid");
      return;
    }
    if (message.event_id <= this.lastEventId) {
      return;
    }
    this.lastEventId = message.event_id;
    if (!this.target.isDestroyed()) {
      this.target.send(IPC_CHANNELS.backendEvent, event);
    }
  }

  private scheduleReconnect(generation: number): void {
    if (generation !== this.generation || this.stopped || this.reconnectTimer !== null) {
      return;
    }
    const delay = Math.min(250 * 2 ** this.reconnectAttempt, MAX_RECONNECT_DELAY_MS);
    this.reconnectAttempt += 1;
    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null;
      void this.connect(generation);
    }, delay);
  }
}
