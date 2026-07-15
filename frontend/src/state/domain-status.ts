import contractSnapshot from "../../contracts/capabilities.json";
import type { components } from "../api/generated";

export type WorkflowState = components["schemas"]["WorkflowStatus"];
export type StageRunState = components["schemas"]["StageRunState"];

export interface StatusPresentation {
  label: string;
  icon: string;
  accessibleName: string;
  actionSource: "backend";
  recovery: "none" | "inspect" | "retry" | "resume" | "resolve" | "readonly";
}

export const workflowStates = Object.freeze([
  ...contractSnapshot.workflowStates,
]) as readonly WorkflowState[];
export const stageRunStates = Object.freeze([
  ...contractSnapshot.stageRunStates,
]) as readonly StageRunState[];

export const workflowStatusPresentation: Record<WorkflowState, StatusPresentation> = {
  created: status("已创建", "circle", "工作流已创建", "none"),
  preflight_failed: status("预检失败", "error", "工作流预检失败", "inspect"),
  running: status("运行中", "play", "工作流运行中", "none"),
  waiting_user: status("等待处理", "person", "工作流等待用户处理", "inspect"),
  warning_blocked: status("警告阻断", "warning", "工作流因警告阻断", "resolve"),
  paused: status("已暂停", "pause", "工作流已暂停", "resume"),
  external_conflict: status("外部冲突", "conflict", "工作流存在外部冲突", "resolve"),
  interrupted: status("已中断", "interrupted", "工作流已中断", "resume"),
  failed: status("失败", "error", "工作流执行失败", "retry"),
  stopped: status("已停止", "stop", "工作流已停止", "readonly"),
  abandoned: status("已放弃", "archive", "工作流已放弃", "readonly"),
  completed: status("已完成", "check", "工作流已完成", "readonly"),
};

export const stageRunStatusPresentation: Record<StageRunState, StatusPresentation> = {
  locked: status("已锁定", "lock", "阶段已锁定", "inspect"),
  ready: status("就绪", "circle", "阶段已就绪", "none"),
  discussing: status("讨论中", "message", "阶段讨论中", "none"),
  producing: status("产出中", "edit", "阶段产出中", "none"),
  p2r_reviewing: status("双校审查", "review", "阶段正在双校审查", "none"),
  quality_checking: status("质量检查", "checklist", "阶段正在质量检查", "none"),
  waiting_approval: status("等待审批", "person", "阶段等待审批", "inspect"),
  handoff_ready: status("可交接", "handoff", "阶段已可交接", "none"),
  completed: status("已完成", "check", "阶段已完成", "readonly"),
  warning_blocked: status("警告阻断", "warning", "阶段因警告阻断", "resolve"),
  needs_fix: status("需要返工", "repair", "阶段需要返工", "resolve"),
  external_conflict: status("外部冲突", "conflict", "阶段存在外部冲突", "resolve"),
  interrupted: status("已中断", "interrupted", "阶段已中断", "resume"),
  failed: status("失败", "error", "阶段执行失败", "retry"),
  cancelled: status("已取消", "cancel", "阶段已取消", "readonly"),
  abandoned: status("已放弃", "archive", "阶段已放弃", "readonly"),
};

function status(
  label: string,
  icon: string,
  accessibleName: string,
  recovery: StatusPresentation["recovery"],
): StatusPresentation {
  return { label, icon, accessibleName, actionSource: "backend", recovery };
}

export function isWorkflowState(value: string): value is WorkflowState {
  return (workflowStates as readonly string[]).includes(value);
}

export function isStageRunState(value: string): value is StageRunState {
  return (stageRunStates as readonly string[]).includes(value);
}
