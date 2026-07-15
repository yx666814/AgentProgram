import { useCallback, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import type { PreflightResult, ProjectRegistration, Workflow } from "../../api/backend-api";
import { useBackend } from "../../api/backend-context";
import { ApiRequestError } from "../../api/errors";
import { ApiErrorState } from "../../components/api-error-state";
import { Button } from "../../components/button";
import { useAsyncResource } from "../../components/use-async-resource";

interface PreflightPageData {
  project: ProjectRegistration;
  preflight: PreflightResult | null;
  workflows: Workflow[];
}

const terminalWorkflowStates = new Set(["completed", "stopped", "abandoned"]);

function evidenceText(evidence: Record<string, unknown> | undefined): string | null {
  if (evidence === undefined || Object.keys(evidence).length === 0) {
    return null;
  }
  return JSON.stringify(evidence, null, 2);
}

export function PreflightPage() {
  const { projectId = "" } = useParams();
  const { api } = useBackend();
  const navigate = useNavigate();
  const [warningAccepted, setWarningAccepted] = useState(false);
  const [workflowTitle, setWorkflowTitle] = useState("首个工作流");
  const [commandError, setCommandError] = useState<unknown>(null);
  const [running, setRunning] = useState(false);
  const [starting, setStarting] = useState(false);

  const loadPage = useCallback(async (): Promise<PreflightPageData> => {
    if (api === null) {
      throw new Error("桌面桥未接入，无法读取项目预检");
    }
    const [project, workflows] = await Promise.all([
      api.getProject(projectId),
      api.listWorkflows(projectId),
    ]);
    let preflight: PreflightResult | null = null;
    try {
      preflight = await api.getPreflight(projectId);
    } catch (error) {
      if (!(error instanceof ApiRequestError) || error.code !== "project.preflight_not_found") {
        throw error;
      }
    }
    return { project, preflight, workflows: [...workflows.workflows] };
  }, [api, projectId]);
  const { resource, reload } = useAsyncResource(loadPage);

  const runPreflight = async () => {
    if (api === null || resource.phase !== "ready") {
      return;
    }
    setRunning(true);
    setCommandError(null);
    setWarningAccepted(false);
    try {
      await api.runPreflight(projectId, resource.data.project.project.version);
      await reload();
    } catch (error) {
      setCommandError(error);
    } finally {
      setRunning(false);
    }
  };

  const startWorkflow = async () => {
    if (api === null || resource.phase !== "ready" || resource.data.preflight === null) {
      return;
    }
    setStarting(true);
    setCommandError(null);
    try {
      const active = resource.data.workflows.find(({ status }) => !terminalWorkflowStates.has(status));
      if (active !== undefined && active.status !== "created") {
        void navigate(`/projects/${projectId}`);
        return;
      }
      const snapshot =
        active === undefined
          ? await api.createWorkflow(projectId, workflowTitle.trim())
          : await api.getWorkflow(active.id);
      const started = await api.startWorkflow(snapshot.workflow.id, snapshot.workflow.version);
      void navigate(`/projects/${projectId}`, { state: { workflowId: started.workflow.id } });
    } catch (error) {
      setCommandError(error);
    } finally {
      setStarting(false);
    }
  };

  if (resource.phase === "loading") {
    return <p className="page-loading" role="status">正在读取项目与预检结果…</p>;
  }
  if (resource.phase === "error") {
    return <ApiErrorState error={resource.error} onRetry={() => {
      void reload();
    }} />;
  }

  const { preflight, project } = resource.data;
  const canStart =
    preflight?.status === "pass" || (preflight?.status === "warning" && warningAccepted);
  const startBlockedReason =
    preflight === null
      ? "必须先运行项目预检"
      : preflight.status === "warning" && !warningAccepted
        ? "需要明确确认预检警告"
        : preflight.status === "needs_fix" || preflight.status === "fail"
          ? "后端预检结果不允许开始工作流"
          : null;

  return (
    <section className="feature-page preflight-page" aria-labelledby="preflight-title">
      <header className="feature-heading">
        <div><span className="eyebrow">{project.project.name}</span><h1 id="preflight-title">项目预检</h1><p>确认目录边界、Manifest、命令与冲突证据。</p></div>
        <div className="inline-actions">
          <Button onClick={() => {
            void navigate("/projects");
          }}>返回项目</Button>
          <Button disabled={running} onClick={() => void runPreflight()}>重新预检</Button>
        </div>
      </header>

      {commandError !== null ? <ApiErrorState error={commandError} /> : null}

      <div className="preflight-grid">
        <section className="data-panel" aria-labelledby="preflight-results-title">
          <header><h2 id="preflight-results-title">预检结果</h2><span>{preflight === null ? "尚未运行" : preflight.status.toUpperCase()}</span></header>
          {preflight === null ? <p className="empty-copy">当前项目还没有预检记录。运行预检后，后端会返回逐项结果和证据。</p> : null}
          {preflight?.checks.map((check) => {
            const evidence = evidenceText(check.evidence);
            return (
              <article className={`preflight-check check-${check.status}`} key={check.code}>
                <div><strong>{check.code}</strong><span>{check.message}</span>{evidence !== null ? <pre>{evidence}</pre> : null}</div>
                <span className="state-badge">{check.status.toUpperCase()}</span>
              </article>
            );
          })}
        </section>

        <aside className="data-panel" aria-labelledby="preflight-evidence-title">
          <header><h2 id="preflight-evidence-title">项目证据</h2><span>后端返回</span></header>
          <dl className="status-list">
            <div><dt>根目录</dt><dd title={project.workspace.canonical_root_path}>{project.workspace.canonical_root_path}</dd></div>
            <div><dt>Workspace</dt><dd>{project.workspace.mode}</dd></div>
            <div><dt>项目状态</dt><dd>{project.project.status}</dd></div>
            <div><dt>项目版本</dt><dd>{String(project.project.version)}</dd></div>
            <div><dt>Manifest 版本</dt><dd>{preflight === null ? "—" : String(preflight.manifest_version)}</dd></div>
          </dl>
          {preflight?.status === "warning" ? (
            <label className="warning-confirmation">
              <input checked={warningAccepted} onChange={(event) => {
                setWarningAccepted(event.target.checked);
              }} type="checkbox" />
              我已阅读后端返回的 WARNING，仍要创建并开始工作流。
            </label>
          ) : null}
          <label className="stacked-field">
            工作流标题
            <input maxLength={200} onChange={(event) => {
              setWorkflowTitle(event.target.value);
            }} value={workflowTitle} />
          </label>
          <Button
            disabled={!canStart || starting || workflowTitle.trim() === ""}
            {...(startBlockedReason !== null ? { disabledReason: startBlockedReason } : {})}
            onClick={() => void startWorkflow()}
            tone="primary"
          >
            创建并开始工作流
          </Button>
        </aside>
      </div>
    </section>
  );
}
