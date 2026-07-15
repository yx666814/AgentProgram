import { createContext, type PropsWithChildren, useContext } from "react";

import type {
  AgentRunList,
  MessageList,
  ProjectRegistration,
  RoomModelAssignment,
  TaskList,
  ToolCallList,
  WorkflowSnapshot,
} from "../../api/backend-api";
import type { components } from "../../api/generated";
import type { Stage, StageContract } from "./stage-copy";

export interface StageWorkspaceData {
  agentRuns: AgentRunList["runs"];
  assignment: RoomModelAssignment | null;
  contract: StageContract;
  messages: MessageList["messages"];
  project: ProjectRegistration;
  room: components["schemas"]["Room"];
  stage: Stage;
  stageRun: components["schemas"]["StageRun"];
  tasks: TaskList["tasks"];
  toolCalls: ToolCallList["calls"];
  workflow: WorkflowSnapshot;
}

const StageContext = createContext<StageWorkspaceData | null>(null);

export function StageContextProvider({
  children,
  value,
}: PropsWithChildren<{ value: StageWorkspaceData }>) {
  return <StageContext.Provider value={value}>{children}</StageContext.Provider>;
}

export function useStageContext(): StageWorkspaceData {
  const context = useContext(StageContext);
  if (context === null) {
    throw new Error("useStageContext must be used inside StageContextProvider");
  }
  return context;
}
