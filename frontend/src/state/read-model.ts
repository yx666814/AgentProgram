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
