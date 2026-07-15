import type { PersistedEvent } from "../../electron/desktop-port";
import type { PublicApiError } from "../api/errors";

export type CommandPhase = "submitting" | "accepted" | "confirmed" | "failed";

export interface CommandRecord {
  commandId: string;
  correlationId: string;
  expectedEventTypes: readonly string[];
  phase: CommandPhase;
  error?: PublicApiError;
  confirmedEventId?: number;
}

export class CommandState {
  private readonly records = new Map<string, CommandRecord>();

  begin(input: Omit<CommandRecord, "phase" | "error" | "confirmedEventId">): void {
    this.records.set(input.commandId, { ...input, phase: "submitting" });
  }

  accept(commandId: string): void {
    const record = this.require(commandId);
    this.records.set(commandId, { ...record, phase: "accepted" });
  }

  fail(commandId: string, error: PublicApiError): void {
    const record = this.require(commandId);
    this.records.set(commandId, { ...record, phase: "failed", error });
  }

  applyEvent(event: PersistedEvent): void {
    if (event.event_id === null || event.event_id === undefined) {
      return;
    }
    for (const [commandId, record] of this.records) {
      if (
        record.phase === "accepted" &&
        record.correlationId === event.correlation_id &&
        record.expectedEventTypes.includes(event.event_type)
      ) {
        this.records.set(commandId, {
          ...record,
          phase: "confirmed",
          confirmedEventId: event.event_id,
        });
      }
    }
  }

  get(commandId: string): CommandRecord | undefined {
    return this.records.get(commandId);
  }

  private require(commandId: string): CommandRecord {
    const record = this.records.get(commandId);
    if (record === undefined) {
      throw new Error(`Unknown command: ${commandId}`);
    }
    return record;
  }
}

export function createCommandState(): CommandState {
  return new CommandState();
}
