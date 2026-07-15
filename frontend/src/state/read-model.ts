import type { Theme } from "../theme/theme-provider";

export type ViewDensity = "comfortable" | "compact";

export interface LocalPersistedState {
  version: 1;
  drafts: Record<string, string>;
  preferences: {
    theme: Theme;
    density: ViewDensity;
    expanded: Record<string, boolean>;
  };
}

export function createLocalPersistedState(): LocalPersistedState {
  return {
    version: 1,
    drafts: {},
    preferences: {
      theme: "light",
      density: "comfortable",
      expanded: {},
    },
  };
}

export function serializeLocalPersistedState(state: LocalPersistedState): string {
  return JSON.stringify(state);
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function stringRecord(value: unknown): Record<string, string> {
  if (!isRecord(value)) {
    return {};
  }
  return Object.fromEntries(
    Object.entries(value).filter((entry): entry is [string, string] => typeof entry[1] === "string"),
  );
}

function booleanRecord(value: unknown): Record<string, boolean> {
  if (!isRecord(value)) {
    return {};
  }
  return Object.fromEntries(
    Object.entries(value).filter((entry): entry is [string, boolean] => typeof entry[1] === "boolean"),
  );
}

function readTheme(value: unknown): Theme {
  return value === "dark" ? "dark" : "light";
}

function readDensity(value: unknown): ViewDensity {
  return value === "compact" ? "compact" : "comfortable";
}

export function parseLocalPersistedState(serialized: string): LocalPersistedState {
  let parsed: unknown;
  try {
    parsed = JSON.parse(serialized) as unknown;
  } catch {
    return createLocalPersistedState();
  }
  if (!isRecord(parsed)) {
    return createLocalPersistedState();
  }
  if (parsed.version === 0) {
    return {
      version: 1,
      drafts: stringRecord(parsed.drafts),
      preferences: {
        theme: readTheme(parsed.theme),
        density: readDensity(parsed.density),
        expanded: booleanRecord(parsed.expanded),
      },
    };
  }
  if (parsed.version !== 1 || !isRecord(parsed.preferences)) {
    return createLocalPersistedState();
  }
  return {
    version: 1,
    drafts: stringRecord(parsed.drafts),
    preferences: {
      theme: readTheme(parsed.preferences.theme),
      density: readDensity(parsed.preferences.density),
      expanded: booleanRecord(parsed.preferences.expanded),
    },
  };
}
