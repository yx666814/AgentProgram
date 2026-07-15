import { useCallback, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import type { Workflow, WorkflowAction, WorkflowSnapshot } from "../../api/backend-api";
import { useBackend } from "../../api/backend-context";
import { ApiErrorState } from "../../components/api-error-state";
import { Button } from "../../components/button";
import { useAsyncResource } from "../../components/use-async-resource";
import { stageRunStatusPresentation, workflowStatusPresentation } from "../../state/domain-status";

const terminalWorkflowStates = new Set(["completed", "stopped", "abandoned"]);

function chooseWorkflow(workflows: Workflow[]): Workflow | null {
  const ordered = [...workflows].sort((left, right) => right.updated_at.localeCompare(left.updated_at));
  return ordered.find(({ status }) => !terminalWorkflowStates.has(status)) ?? ordered[0] ?? null;
}

export function ProjectOverviewPage() {
  const { projectId = "" } = useParams();
  const { api, events, port } = useBackend();
  const navigate = useNavigate();
  const [commandError, setCommandError] = useState<unknown>(null);
  const [command, setCommand] = useState<WorkflowAction | "close" | null>(null);

  const loadPage = useCallback(async () => {
    if (api === null) {
      throw new Error("桌面桥未接入，无法读取项目主页");
    }
    const [project, list] = await Promise.all([api.getProject(projectId), api.listWorkflows(projectId)]);
    const selected = chooseWorkflow([...list.workflows]);
    const snapshot: WorkflowSnapshot | null = selected === null ? null : await api.getWorkflow(selected.id);
    return { project, snapshot };
  }, [api, projectId]);
  const { resource, reload } = useAsyncResource(loadPage);

  const confirmWorkflowAction = async (action: "stop" | "abandon"): Promise<boolean> => {
    if (port === null) {
      return false;
    }
    return port.showNativeConfirm({
      title: action === "stop" ? "停止工作流" : "放弃工作流",
      message: action === "stop" ? "运行中与排队任务将被取消。" : "工作流将进入不可继续的放弃状态。",
      detail: "操作不会删除 Direct Workspace 中的用户文件。",
      confirmLabel: action === "stop" ? "停止" : "放弃",
    });
  };

  const controlWorkflow = async (action: WorkflowAction) => {
    if (api === null || resource.phase !== "ready" || resource.data.snapshot === null) {
      return;
    }
    if ((action === "stop" || action === "abandon") && !(await confirmWorkflowAction(action))) {
      return;
    }
    setCommand(action);
    setCommandError(null);
    try {
      await api.controlWorkflow(
        resource.data.snapshot.workflow.id,
        action,
        resource.data.snapshot.workflow.version,
      );
      await reload();
    } catch (error) {
      setCommandError(error);
    } finally {
      setCommand(null);
    }
  };

  const closeProject = async () => {
    if (api === null || port === null || resource.phase !== "ready") {
      return;
    }
    const confirmed = await port.showNativeConfirm({
      title: "关闭项目",
      message: "星协将关闭当前项目上下文。",
      detail: "项目注册信息会保留，Direct Workspace 与 Managed Workspace 文件都不会被删除。",
      confirmLabel: "关闭项目",
    });
    if (!confirmed) {
      return;
    }
    setCommand("close");
    setCommandError(null);
    try {
      await api.closeProject(projectId, resource.data.project.project.version);
      void navigate("/projects");
    } catch (error) {
      setCommandError(error);
    } finally {
      setCommand(null);
    }
  };

  if (resource.phase === "loading") {
    return <p className="page-loading" role="status">正在读取项目和工作流…</p>;
  }
  if (resource.phase === "error") {
    return <ApiErrorState error={resource.error} onRetry={() => {
      void reload();
    }} />;
  }

  const { project, snapshot } = resource.data;
  const projectEvents = events.recentEvents
    .filter((event) => event.project_id === projectId)
    .slice(-6)
    .reverse();

  return (
    <section className="feature-page overview-page" aria-labelledby="overview-title">
      <header className="feature-heading">
        <div><span className="eyebrow">项目主页</span><h1 id="overview-title">{project.project.name}</h1><p>{project.project.goal}</p></div>
        <div className="inline-actions">
          <Button disabled={command !== null} onClick={() => void closeProject()}>关闭项目</Button>
          {snapshot?.workflow.status === "paused" ? <Button disabled={command !== null} onClick={() => void controlWorkflow("resume")}>继续</Button> : null}
          {snapshot !== null && ["running", "waiting_user", "warning_blocked"].includes(snapshot.workflow.status) ? <Button disabled={command !== null} onClick={() => void controlWorkflow("pause")}>暂停</Button> : null}
          {snapshot !== null && !terminalWorkflowStates.has(snapshot.workflow.status) ? (
            <>
              <Button disabled={command !== null} onClick={() => void controlWorkflow("stop")}>停止</Button>
              <Button disabled={command !== null} onClick={() => void controlWorkflow("abandon")} tone="danger">放弃</Button>
            </>
          ) : null}
        </div>
      </header>

      {commandError !== null ? <ApiErrorState error={commandError} /> : null}

      {snapshot === null ? (
        <div className="truthful-state">
          <strong>当前项目没有工作流。</strong>
          <p>先运行预检；只有 PASS 或明确确认的 WARNING 才能创建工作流。</p>
          <Button onClick={() => {
            void navigate(`/projects/${projectId}/preflight`);
          }} tone="primary">前往预检</Button>
        </div>
      ) : (
        <>
          <div className="overview-metrics">
            <article><span>工作流</span><strong>{snapshot.workflow.title}</strong><small>{workflowStatusPresentation[snapshot.workflow.status].label}</small></article>
            <article><span>当前阶段</span><strong>{snapshot.workflow.current_stage}</strong><small>版本 {String(snapshot.workflow.version)}</small></article>
            <article><span>Workspace</span><strong>{project.workspace.mode}</strong><small title={project.workspace.root_path}>{project.workspace.root_path}</small></article>
          </div>

          <section className="data-panel stage-timeline" aria-labelledby="stage-timeline-title">
            <header><h2 id="stage-timeline-title">五阶段工作流</h2><span>后端固定顺序</span></header>
            <div className="stage-track">
              {snapshot.stage_runs.map((stageRun) => (
                <article className={stageRun.stage === snapshot.workflow.current_stage ? "current" : ""} key={stageRun.id}>
                  <strong>{stageRun.stage}</strong>
                  <span>{stageRunStatusPresentation[stageRun.state].label}</span>
                  <small>尝试 {String(stageRun.attempt)}</small>
                </article>
              ))}
            </div>
          </section>

          <div className="overview-grid">
            <section className="data-panel" aria-labelledby="project-state-title">
              <header><h2 id="project-state-title">当前状态</h2><span>权威查询</span></header>
              <dl className="status-list">
                <div><dt>项目状态</dt><dd>{project.project.status}</dd></div>
                <div><dt>工作流状态</dt><dd>{snapshot.workflow.status}</dd></div>
                <div><dt>执行模式</dt><dd>{snapshot.workflow.execution_mode}</dd></div>
                <div><dt>当前阶段</dt><dd>{snapshot.workflow.current_stage}</dd></div>
              </dl>
            </section>
            <section className="data-panel" aria-labelledby="recent-events-title">
              <header><h2 id="recent-events-title">最近事件</h2><span>持久化事件</span></header>
              {projectEvents.length === 0 ? <p className="empty-copy">当前连接尚未收到该项目的事件。</p> : null}
              <div className="event-list">
                {projectEvents.map((event) => (
                  <article key={event.event_id ?? `${event.event_type}-${event.occurred_at}`}>
                    <strong>{event.event_type}</strong>
                    <span>event #{event.event_id === null || event.event_id === undefined ? "—" : String(event.event_id)}</span>
                  </article>
                ))}
              </div>
            </section>
          </div>
        </>
      )}
    </section>
  );
}
