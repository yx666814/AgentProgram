import { expect, it } from "vitest";

import { parseLocalPersistedState, serializeLocalPersistedState } from "../../src/state/read-model";

it("migrates legacy view preferences and drops domain state", () => {
  const migrated = parseLocalPersistedState(JSON.stringify({
    version: 0,
    drafts: { planner: "草稿" },
    theme: "dark",
    density: "compact",
    expanded: { evidence: true },
    workflowState: { status: "completed" },
    approvals: [{ id: "approval_secret" }],
    token: "must-not-survive",
  }));
  expect(migrated).toEqual({
    version: 1,
    drafts: { planner: "草稿" },
    preferences: { theme: "dark", density: "compact", expanded: { evidence: true } },
  });
  expect(serializeLocalPersistedState(migrated)).not.toMatch(/workflowState|approval_secret|must-not-survive/);
});

it("falls back safely for unknown or invalid preference versions", () => {
  expect(parseLocalPersistedState("not-json").preferences.theme).toBe("light");
  expect(parseLocalPersistedState(JSON.stringify({ version: 99, theme: "dark" })).preferences.theme).toBe("light");
});
