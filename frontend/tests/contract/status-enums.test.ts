// @vitest-environment node

import { expect, it } from "vitest";

import {
  isStageRunState,
  isWorkflowState,
  stageRunStates,
  stageRunStatusPresentation,
  workflowStates,
  workflowStatusPresentation,
} from "../../src/state/domain-status";

it("covers every frozen workflow and stage state with accessible presentation", () => {
  expect(workflowStates).toHaveLength(12);
  expect(stageRunStates).toHaveLength(16);
  for (const state of workflowStates) {
    expect(workflowStatusPresentation[state]).toEqual(
      expect.objectContaining({ actionSource: "backend" }),
    );
    expect(workflowStatusPresentation[state].accessibleName).not.toBe("");
  }
  for (const state of stageRunStates) {
    expect(stageRunStatusPresentation[state]).toEqual(
      expect.objectContaining({ actionSource: "backend" }),
    );
    expect(stageRunStatusPresentation[state].accessibleName).not.toBe("");
  }
});

it("rejects unknown protocol states instead of treating them as running", () => {
  expect(isWorkflowState("future_state")).toBe(false);
  expect(isStageRunState("future_state")).toBe(false);
});
