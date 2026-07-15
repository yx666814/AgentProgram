// @vitest-environment node

import { expect, it } from "vitest";

import {
  createLocalPersistedState,
  serializeLocalPersistedState,
} from "../../src/state/read-model";

it("persists only drafts and view preferences", () => {
  const state = createLocalPersistedState();
  state.drafts["planner-room"] = "未提交输入";
  state.preferences.theme = "dark";
  state.preferences.expanded.evidence = true;

  const document = JSON.parse(serializeLocalPersistedState(state)) as Record<string, unknown>;
  expect(Object.keys(document)).toEqual(["version", "drafts", "preferences"]);
  expect(JSON.stringify(document)).not.toMatch(
    /workflowState|stageRun|approval|gate|artifactVersion|handoff|conflict|checkpoint|token|secret/i,
  );
});
