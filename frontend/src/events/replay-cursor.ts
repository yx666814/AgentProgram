import type { PersistedEvent } from "../../electron/desktop-port";

export type CursorDecision = "apply" | "duplicate" | "invalid" | "incompatible";
export type IncomingPersistedEvent = Omit<PersistedEvent, "schema_version"> & {
  schema_version: number;
};

export class ReplayCursor {
  private lastEventId = 0;

  get value(): number {
    return this.lastEventId;
  }

  evaluate(event: IncomingPersistedEvent): CursorDecision {
    if (event.schema_version !== 1) {
      return "incompatible";
    }
    const eventId = event.event_id;
    if (eventId === null || eventId === undefined || !Number.isInteger(eventId) || eventId <= 0) {
      return "invalid";
    }
    if (eventId <= this.lastEventId) {
      return "duplicate";
    }
    this.lastEventId = eventId;
    return "apply";
  }
}
