import { type SyntheticEvent, useCallback, useState } from "react";
import { useNavigate } from "react-router-dom";

import type { ProjectRegistration } from "../../api/backend-api";
import { useBackend } from "../../api/backend-context";
import { ApiErrorState } from "../../components/api-error-state";
import { Button } from "../../components/button";
import { useAsyncResource } from "../../components/use-async-resource";

function projectDestination(registration: ProjectRegistration): string {
  return registration.project.status === "ready"
    ? `/projects/${registration.project.id}`
    : `/projects/${registration.project.id}/preflight`;
}

export function ProjectsPage() {
  const { api, port } = useBackend();
  const navigate = useNavigate();
  const [name, setName] = useState("");
  const [goal, setGoal] = useState("");
  const [directory, setDirectory] = useState("");
  const [workspaceMode, setWorkspaceMode] = useState<"managed" | "direct">("managed");
  const [commandError, setCommandError] = useState<unknown>(null);
  const [submitting, setSubmitting] = useState(false);
  const [openingId, setOpeningId] = useState<string | null>(null);

  const loadProjects = useCallback(async () => {
    if (api === null) {
      throw new Error("桌面桥未接入，无法读取项目");
    }
    return api.listProjects();
  }, [api]);
  const { resource, reload } = useAsyncResource(loadProjects);

  const chooseDirectory = async () => {
    if (port === null) {
      return;
    }
    const result = await port.selectDirectory();
    if (!result.cancelled && result.path !== undefined) {
      setDirectory(result.path);
    }
  };

  const createProject = async (event: SyntheticEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (api === null || name.trim() === "" || goal.trim() === "" || directory === "") {
      return;
    }
    setSubmitting(true);
    setCommandError(null);
    try {
      const created = await api.createProject({
        name: name.trim(),
        goal: goal.trim(),
        local_working_directory: directory,
        workspace_mode: workspaceMode,
      });
      void navigate(`/projects/${created.registration.project.id}/preflight`);
    } catch (error) {
      setCommandError(error);
    } finally {
      setSubmitting(false);
    }
  };

  const openProject = async (registration: ProjectRegistration) => {
    if (api === null) {
      return;
    }
    setOpeningId(registration.project.id);
    setCommandError(null);
    try {
      const opened = await api.openProject(registration.project.id, registration.project.version);
      void navigate(projectDestination(opened));
    } catch (error) {
      setCommandError(error);
    } finally {
      setOpeningId(null);
    }
  };

  return (
    <section className="feature-page project-list-page" aria-labelledby="projects-title">
      <header className="feature-heading">
        <div><span className="eyebrow">本地项目</span><h1 id="projects-title">项目</h1><p>创建、打开并按后端状态进入预检或项目主页。</p></div>
        <Button onClick={() => void reload()}>刷新列表</Button>
      </header>

      {commandError !== null ? <ApiErrorState error={commandError} /> : null}

      <div className="project-grid">
        <section className="data-panel" aria-labelledby="local-projects-title">
          <header><h2 id="local-projects-title">本地项目</h2><span>{resource.phase === "ready" ? `${String(resource.data.projects.length)} 个` : "读取中"}</span></header>
          {resource.phase === "loading" ? <p className="empty-copy" role="status">正在读取项目…</p> : null}
          {resource.phase === "error" ? <ApiErrorState error={resource.error} onRetry={() => void reload()} /> : null}
          {resource.phase === "ready" && resource.data.projects.length === 0 ? <p className="empty-copy">还没有已注册项目。</p> : null}
          {resource.phase === "ready" ? (
            <div className="project-table" role="list">
              {resource.data.projects.map((registration) => (
                <article className="project-row" key={registration.project.id} role="listitem">
                  <div className="project-identity">
                    <strong>{registration.project.name}</strong>
                    <span title={registration.workspace.root_path}>{registration.workspace.root_path}</span>
                  </div>
                  <span>{registration.workspace.mode === "managed" ? "Managed" : "Direct"}</span>
                  <span className={`state-badge state-${registration.project.status}`}>{registration.project.status}</span>
                  <Button disabled={openingId === registration.project.id} onClick={() => void openProject(registration)}>打开</Button>
                </article>
              ))}
            </div>
          ) : null}
        </section>

        <form className="data-panel create-project-form" onSubmit={(event) => {
          void createProject(event);
        }}>
          <header><h2>创建项目</h2><span>后端校验目录边界</span></header>
          <label>项目名称<input maxLength={120} onChange={(event) => {
            setName(event.target.value);
          }} required value={name} /></label>
          <label>项目目标<textarea maxLength={10000} onChange={(event) => {
            setGoal(event.target.value);
          }} required rows={4} value={goal} /></label>
          <label>
            本地工作目录
            <span className="directory-control">
              <input aria-label="本地工作目录" readOnly value={directory} />
              <Button disabled={port === null} onClick={() => void chooseDirectory()}>选择目录</Button>
            </span>
          </label>
          <fieldset>
            <legend>Workspace</legend>
            <label className="choice-card"><input checked={workspaceMode === "managed"} name="workspace" onChange={() => {
              setWorkspaceMode("managed");
            }} type="radio" />Managed<span>由星协管理工作区副本</span></label>
            <label className="choice-card"><input checked={workspaceMode === "direct"} name="workspace" onChange={() => {
              setWorkspaceMode("direct");
            }} type="radio" />Direct<span>直接使用用户目录，关闭不会删除文件</span></label>
          </fieldset>
          <footer className="page-actions">
            <Button disabled={submitting || name.trim() === "" || goal.trim() === "" || directory === ""} tone="primary" type="submit">创建并预检</Button>
          </footer>
        </form>
      </div>
    </section>
  );
}
