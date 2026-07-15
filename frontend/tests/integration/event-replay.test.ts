// @vitest-environment node

import { expect, it, vi } from "vitest";

import type { DesktopPort, PersistedEvent } from "../../electron/desktop-port";
import { EventStream } from "../../src/events/event-stream";
import { createCommandState } from "../../src/state/command-state";

function event(eventId: number, eventType = "workflow.paused"): PersistedEvent {
  return {
    schema_version: 1,
    event_id: eventId,
    event_type: eventType,
    correlation_id: "correlation-1",
    actor: { type: "system", id: "backend" },
    source: "backend",
    occurred_at: "2026-07-15T00:00:00Z",
    payload: {},
  };
}

function eventPort() {
  let listener: ((value: PersistedEvent) => void) | null = null;
  const requestReplay = vi.fn(() => Promise.resolve());
  const port = {
    backend: {
      query: vi.fn(),
      command: vi.fn(),
      subscribe: (next: (value: PersistedEvent) => void) => {
        listener = next;
        return () => {
          listener = null;
        };
      },
      requestReplay,
    },
  } as unknown as DesktopPort;
  return {
    port,
    requestReplay,
    emit: (value: PersistedEvent) => listener?.(value),
  };
}

it("accepts non-contiguous global event ids and ignores duplicates", async () => {
  const harness = eventPort();
  const updates = vi.fn();
  const stream = new EventStream(harness.port, updates);
  stream.start();

  harness.emit(event(41));
  harness.emit(event(45, "workflow.resumed"));
  harness.emit(event(45, "workflow.resumed"));

  expect(stream.getSnapshot().appliedEventIds).toEqual([41, 45]);
  await stream.requestReplay();
  expect(harness.requestReplay).toHaveBeenCalledWith(45);
});

it("does not mark an accepted command complete before its persisted event", () => {
  const state = createCommandState();
  state.begin({
    commandId: "command-1",
    correlationId: "correlation-1",
    expectedEventTypes: ["workflow.paused"],
  });
  state.accept("command-1");
  expect(state.get("command-1")?.phase).toBe("accepted");

  state.applyEvent(event(41));
  expect(state.get("command-1")).toMatchObject({ phase: "confirmed", confirmedEventId: 41 });
});

it("surfaces an incompatible event schema instead of applying it", () => {
  const harness = eventPort();
  const stream = new EventStream(harness.port, () => undefined);
  stream.start();

  harness.emit({ ...event(42), schema_version: 2 } as unknown as PersistedEvent);

  expect(stream.getSnapshot()).toMatchObject({
    lastAppliedEventId: 0,
    protocolIssue: "incompatible_schema",
  });
});
