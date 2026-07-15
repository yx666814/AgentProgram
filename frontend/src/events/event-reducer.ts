import type { PersistedEvent } from "../../electron/desktop-port";

export interface EventReadModel {
  lastAppliedEventId: number;
  lastEvent: PersistedEvent | null;
  appliedEventIds: readonly number[];
  recentEvents: readonly PersistedEvent[];
  protocolIssue: "invalid_event" | "incompatible_schema" | null;
}

export function createEventReadModel(): EventReadModel {
  return {
    lastAppliedEventId: 0,
    lastEvent: null,
    appliedEventIds: [],
    recentEvents: [],
    protocolIssue: null,
  };
}

export function applyPersistedEvent(model: EventReadModel, event: PersistedEvent): EventReadModel {
  const eventId = event.event_id;
  if (eventId === null || eventId === undefined) {
    return { ...model, protocolIssue: "invalid_event" };
  }
  return {
    lastAppliedEventId: eventId,
    lastEvent: event,
    appliedEventIds: [...model.appliedEventIds, eventId],
    recentEvents: [...model.recentEvents, event].slice(-100),
    protocolIssue: null,
  };
}
