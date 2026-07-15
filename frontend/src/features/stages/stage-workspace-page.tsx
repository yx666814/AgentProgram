import { useCallback, useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import type { StageRunState, Task, Workflow } from "../../api/backend-api";
import { useBackend } from "../../api/backend-context";
import { ApiRequestError } from "../../api/errors";
import { ApiErrorState } from "../../components/api-error-state";
import { Button } from "../../components/button";
import { useAsyncResource } from "../../components/use-async-resource";
import { stageRunStatusPresentation } from "../../state/domain-status";
import { MessageStream } from "./message-stream";
import { isStage, type Stage, stageContract, stageCopy, stageOrder } from "./stage-copy";
import { StageContextProvider, type StageWorkspaceData } from "./stage-context";
import { TaskQueue } from "./task-queue";
import { ToolProgress } from "./tool-progress";

const terminalWorkflowStates = new Set(["completed", "stopped", "abandoned"]);

const nextStageAction: Partial<Record<StageRunState, { label: string; target: StageRunState }>> = {
  ready: { label: "开始讨论", target: "discussing" },
  discussing: { label: "进入产出", target: "producing" },
  producing: { label: "提交双校审查", target: "p2r_reviewing" },
  needs_fix: { label: "开始返工", target: "producing" },
  warning_blocked: { label: "返回讨论", target: "discussing" },
  external_conflict: { label: "冲突处理后继续讨论", target: "discussing" },
  interrupted: { label: "恢复讨论", target: "discussing" },
};

function chooseWorkflow(workflows: Workflow[]): Workflow | null {
  const ordered = [...workflows].sort((left, right) => right.updated_at.localeCompare(left.updated_at));
  return ordered.find(({ status }) => !terminalWorkflowStates.has(status)) ?? ordered[0] ?? null;
}

function eventPayloadId(payload: Record<string, unknown>, key: string): string | null {
  const value = payload[key];
  return typeof value === "string" ? value : null;
}

export function StageWorkspacePage() {
  const { projectId = "", stage: stageParam = "" } = useParams();
  const { api, events, port } = useBackend();
  const navigate = useNavigate();
  const [commandError, setCommandError] = useState<unknown>(null);
  const [pendingMessageId, setPendingMessageId] = useState<string | null>(null);
  const [pendingTask, setPendingTask] = useState<{ id: string; eventType: string } | null>(null);
  const [pendingStage, setPendingStage] = useState<{ id: string; eventType: string } | null>(null);

  const loadStage = useCallback(async (): Promise<StageWorkspaceData> => {
    if (api === null) {
      throw new Error("桌面桥未接入，无法读取阶段工作区");
    }
    if (!isStage(stageParam)) {
      throw new Error("阶段参数不属于后端 Stage 枚举");
    }
    const [project, workflows] = await Promise.all([
      api.getProject(projectId),
      api.listWorkflows(projectId),
    ]);
    const selected = chooseWorkflow([...workflows.workflows]);
    if (selected === null) {
      throw new Error("项目没有可读取的工作流");
    }
    const workflow = await api.getWorkflow(selected.id);
    const stageRun = workflow.stage_runs.find((candidate) => candidate.stage === stageParam);
    if (stageRun === undefined) {
      throw new Error(`工作流缺少 ${stageParam} StageRun`);
    }
    const room = workflow.rooms.find((candidate) => candidate.stage_run_id === stageRun.id);
    if (room === undefined) {
      throw new Error(`工作流缺少 ${stageParam} Room`);
    }
    const [messages, taskList, toolList, agentRunList] = await Promise.all([
      api.listMessages(room.id),
      api.listTasks(workflow.workflow.id),
      api.listToolCalls(workflow.workflow.id),
      api.listAgentRuns(room.id),
    ]);
    let assignment = null;
    try {
      assignment = await api.getRoomAssignment(room.id);
    } catch (error) {
      if (!(error instanceof ApiRequestError) || error.statusCode !== 404) {
        throw error;
      }
    }
    return {
      agentRuns: agentRunList.runs,
      assignment,
      contract: stageContract(stageParam),
      messages: messages.messages,
      project,
      room,
      stage: stageParam,
      stageRun,
      tasks: taskList.tasks.filter((task) => task.room_id === room.id),
      toolCalls: toolList.calls.filter((call) => call.stage_run_id === stageRun.id),
      workflow,
    };
  }, [api, projectId, stageParam]);
  const { resource, reload } = useAsyncResource(loadStage);

  useEffect(() => {
    let confirmed = false;
    if (pendingMessageId !== null) {
      confirmed = events.recentEvents.some(
        (event) =>
          event.event_type === "message.appended" &&
          eventPayloadId(event.payload, "message_id") === pendingMessageId,
      );
      if (confirmed) {
        setPendingMessageId(null);
      }
    }
    if (pendingTask !== null) {
      const taskConfirmed = events.recentEvents.some(
        (event) => event.event_type === pendingTask.eventType && event.task_id === pendingTask.id,
      );
      if (taskConfirmed) {
        setPendingTask(null);
        confirmed = true;
      }
    }
    if (pendingStage !== null) {
      const stageConfirmed = events.recentEvents.some((event) => {
        if (event.event_type !== pendingStage.eventType) {
          return false;
        }
        return pendingStage.eventType === "stage_run.reopened"
          ? eventPayloadId(event.payload, "stage") === pendingStage.id
          : eventPayloadId(event.payload, "stage_run_id") === pendingStage.id;
      });
      if (stageConfirmed) {
        setPendingStage(null);
        confirmed = true;
      }
    }
    if (confirmed) {
      void reload();
    }
  }, [events.recentEvents, pendingMessageId, pendingStage, pendingTask, reload]);

  const sendMessage = async (content: string, correctionOfId: string | null) => {
    if (api === null || resource.phase !== "ready") {
      return;
    }
    setCommandError(null);
    try {
      const appended = await api.appendMessage(
        resource.data.room.id,
        content,
        resource.data.room.version,
        correctionOfId,
      );
      setPendingMessageId(appended.message.id);
    } catch (error) {
      setCommandError(error);
    }
  };

  const enqueueTask = async (title: string) => {
    if (api === null || resource.phase !== "ready") {
      return;
    }
    setCommandError(null);
    try {
      const task = await api.enqueueTask(resource.data.room.id, title);
      setPendingTask({ id: task.id, eventType: "task.queued" });
    } catch (error) {
      setCommandError(error);
    }
  };

  const startTask = async (task: Task) => {
    if (api === null) {
      return;
    }
    setCommandError(null);
    try {
      const started = await api.startTask(task.id, task.version);
      setPendingTask({ id: started.id, eventType: "task.started" });
    } catch (error) {
      setCommandError(error);
    }
  };

  const cancelTask = async (task: Task) => {
    if (api === null) {
      return;
    }
    setCommandError(null);
    try {
      const cancelled = await api.cancelTask(task.id, task.version);
      setPendingTask({ id: cancelled.id, eventType: "task.cancelled" });
    } catch (error) {
      setCommandError(error);
    }
  };

  const transitionStage = async (stage: Stage, target: StageRunState) => {
    if (api === null || resource.phase !== "ready") {
      return;
    }
    setCommandError(null);
    try {
      const transitioned = await api.transitionStage(
        resource.data.workflow.workflow.id,
        stage,
        target,
        resource.data.workflow.workflow.version,
        resource.data.stageRun.version,
      );
      setPendingStage({ id: transitioned.stage_run.id, eventType: "stage_run.transitioned" });
    } catch (error) {
      setCommandError(error);
    }
  };

  const reopenStage = async (stage: Stage) => {
    if (api === null || port === null || resource.phase !== "ready") {
      return;
    }
    const downstream = stageOrder.slice(stageOrder.indexOf(stage) + 1).join("、") || "无";
    const confirmed = await port.showNativeConfirm({
      title: `重新打开 ${stageCopy[stage].displayName}`,
      message: "将创建新的 StageRun 尝试，历史记录保持只读。",
      detail: `后端会使该阶段及下游 Artifact/Handoff 引用失效。下游阶段：${downstream}`,
      confirmLabel: "重新打开",
    });
    if (!confirmed) {
      return;
    }
    setCommandError(null);
    try {
      await api.reopenStage(resource.data.workflow.workflow.id, stage, resource.data.workflow.workflow.version);
      setPendingStage({ id: stage, eventType: "stage_run.reopened" });
    } catch (error) {
      setCommandError(error);
    }
  };

  if (resource.phase === "loading") {
    return <p className="page-loading" role="status">正在读取阶段、Room、任务与工具状态…</p>;
  }
  if (resource.phase === "error") {
    return <ApiErrorState error={resource.error} onRetry={() => {
      void reload();
    }} />;
  }

  const data = resource.data;
  const activeCurrentStage =
    data.workflow.workflow.status === "running" &&
    data.workflow.workflow.current_stage === data.stage &&
    data.room.status === "active";
  const canWrite = data.room.status === "consultation" || (activeCurrentStage && !["locked", "completed", "failed", "cancelled", "abandoned"].includes(data.stageRun.state));
  const canQueue = activeCurrentStage && canWrite;
  const nextAction = nextStageAction[data.stageRun.state];

  return (
    <StageContextProvider value={data}>
      <section className="feature-page stage-workspace" data-stage={data.stage} data-testid="stage-workspace">
        <header className="feature-heading">
          <div><span className="eyebrow">{data.project.project.name} · {stageRunStatusPresentation[data.stageRun.state].label}</span><h1>{stageCopy[data.stage].displayName}</h1><p>{stageCopy[data.stage].goal}</p></div>
          <div className="inline-actions">
            <Button onClick={() => {
              void navigate(`/projects/${projectId}`);
            }}>项目主页</Button>
            {nextAction !== undefined ? <Button disabled={pendingStage !== null} onClick={() => void transitionStage(data.stage, nextAction.target)} tone="primary">{nextAction.label}</Button> : null}
            {data.stageRun.state === "completed" ? <Button disabled={pendingStage !== null} onClick={() => void reopenStage(data.stage)}>重新打开</Button> : null}
          </div>
        </header>

        {commandError !== null ? <ApiErrorState error={commandError} /> : null}
        {pendingStage !== null ? <div className="event-wait global-wait">等待 {pendingStage.eventType}</div> : null}

        <div className="stage-summary-grid">
          <article><span>StageRun</span><strong>{data.stageRun.state}</strong><small>{data.stageRun.id} · attempt {String(data.stageRun.attempt)}</small></article>
          <article><span>Room</span><strong>{data.room.status}</strong><small>{data.room.id} · version {String(data.room.version)}</small></article>
          <article><span>可请求能力</span><strong>{String(data.contract.requestable_capabilities.length)}</strong><small>永久禁止 {String(data.contract.forbidden_capabilities.length)} 项</small></article>
        </div>

        <section className="data-panel stage-scope-panel" aria-labelledby="stage-scope-title">
          <header><h2 id="stage-scope-title">阶段上下文与权限</h2><span>StageContract {data.contract.contract_version}</span></header>
          <div className="stage-scope-grid">
            <div><h3>正式记录结构</h3>{stageCopy[data.stage].sections.map((section) => <span key={section}>{section}</span>)}</div>
            <div><h3>默认能力</h3>{data.contract.default_capabilities.map((capability) => <code key={capability}>{capability}</code>)}</div>
            <div><h3>可申请能力</h3>{data.contract.requestable_capabilities.map((capability) => <code key={capability}>{capability}</code>)}</div>
          </div>
        </section>

        <div className="stage-main-grid">
          <MessageStream canWrite={canWrite} onSend={sendMessage} pendingMessageId={pendingMessageId} />
          <div className="stage-side-stack">
            <TaskQueue canQueue={canQueue} onCancel={cancelTask} onEnqueue={enqueueTask} onStart={startTask} pendingTask={pendingTask} />
            <ToolProgress />
          </div>
        </div>
      </section>
    </StageContextProvider>
  );
}
