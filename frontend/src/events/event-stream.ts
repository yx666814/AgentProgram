import type { DesktopPort, PersistedEvent } from "../../electron/desktop-port";
import { applyPersistedEvent, createEventReadModel, type EventReadModel } from "./event-reducer";
import { ReplayCursor } from "./replay-cursor";

export type EventStreamListener = (model: EventReadModel) => void;

export class EventStream {
  private readonly cursor = new ReplayCursor();
  private model = createEventReadModel();
  private unsubscribe: (() => void) | null = null;

  constructor(
    private readonly port: DesktopPort,
    private readonly listener: EventStreamListener,
  ) {}

  start(): void {
    if (this.unsubscribe !== null) {
      return;
    }
    this.unsubscribe = this.port.backend.subscribe((event) => {
      this.receive(event);
    });
  }

  stop(): void {
    this.unsubscribe?.();
    this.unsubscribe = null;
  }

  async requestReplay(): Promise<void> {
    await this.port.backend.requestReplay(this.cursor.value);
  }

  getSnapshot(): EventReadModel {
    return this.model;
  }

  private receive(event: PersistedEvent): void {
    const decision = this.cursor.evaluate(event);
    if (decision === "duplicate") {
      return;
    }
    if (decision === "incompatible") {
      this.model = { ...this.model, protocolIssue: "incompatible_schema" };
      this.listener(this.model);
      return;
    }
    if (decision === "invalid") {
      this.model = { ...this.model, protocolIssue: "invalid_event" };
      this.listener(this.model);
      return;
    }
    this.model = applyPersistedEvent(this.model, event);
    this.listener(this.model);
  }
}
