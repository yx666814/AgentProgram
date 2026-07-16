import { NavLink, Outlet, useLocation } from "react-router-dom";

import { useBackend } from "../api/backend-context";
import { Button } from "../components/button";
import { useTheme } from "../theme/theme-provider";

const stageLabels = ["Planner", "Designer", "Builder", "Reviewer", "Deployer"] as const;

function pageTitle(pathname: string): string {
  if (/^\/projects\/[^/]+\/stages\/[^/]+$/.test(pathname)) {
    return "阶段工作区";
  }
  if (pathname.endsWith("/artifacts")) {
    return "产出与交接";
  }
  if (pathname.endsWith("/approvals")) {
    return "审批与能力";
  }
  if (pathname.endsWith("/recovery")) {
    return "冲突与恢复";
  }
  if (pathname.endsWith("/preflight")) {
    return "项目预检";
  }
  if (/^\/projects\/[^/]+$/.test(pathname)) {
    return "项目主页";
  }
  return { "/projects": "项目", "/diagnostics": "事件与诊断", "/settings": "设置" }[
    pathname
  ] ?? "星协";
}

function navigationClass({ isActive }: { isActive: boolean }): string {
  return isActive ? "nav-link nav-link-active" : "nav-link";
}

export function AppShell() {
  const location = useLocation();
  const { port } = useBackend();
  const { theme, toggleTheme } = useTheme();
  const title = pageTitle(location.pathname);
  const projectMatch = /^\/projects\/([^/]+)/.exec(location.pathname);
  const projectId = projectMatch?.[1] ?? null;

  return (
    <div className="app-window">
      <header className="window-titlebar">
        <span>星协</span>
        <span className="window-titlebar-context">Windows 本地桌面</span>
      </header>
      <div className="app-body">
        <aside className="sidebar" aria-label="主导航">
          <div className="brand-block">
            <img alt="" className="brand-icon" src="/xingxie-icon.svg" />
            <div>
              <strong>星协</strong>
              <span>AgentProgram V1</span>
            </div>
          </div>

          <nav className="workspace-navigation" aria-label="工作区导航">
            <NavLink className={navigationClass} to="/projects">
              项目
            </NavLink>
            {projectId !== null ? (
              <NavLink className={navigationClass} end to={`/projects/${projectId}`}>
                当前工作流
              </NavLink>
            ) : null}
            <div className="nav-section-label">五阶段</div>
            {stageLabels.map((stage) => (
              projectId === null ? (
                <div aria-disabled="true" className="nav-link nav-link-disabled" key={stage} title="先打开项目并创建工作流">
                  <span>{stage}</span><span className="nav-lock">锁定</span>
                </div>
              ) : (
                <NavLink className={navigationClass} key={stage} to={`/projects/${projectId}/stages/${stage.toLowerCase()}`}>
                  <span>{stage}</span><span className="nav-lock">查询</span>
                </NavLink>
              )
            ))}
            {projectId !== null ? (
              <>
                <div className="nav-section-label">治理</div>
                <NavLink className={navigationClass} to={`/projects/${projectId}/artifacts`}>产出与交接</NavLink>
                <NavLink className={navigationClass} to={`/projects/${projectId}/approvals`}>审批与能力</NavLink>
                <NavLink className={navigationClass} to={`/projects/${projectId}/recovery`}>冲突与恢复</NavLink>
              </>
            ) : null}
            <div className="nav-section-label">记录</div>
            <NavLink className={navigationClass} to="/diagnostics">
              事件与诊断
            </NavLink>
          </nav>

          <div className="sidebar-footer">
            <NavLink className={navigationClass} to="/settings">
              设置
            </NavLink>
          </div>
        </aside>

        <main className="workspace-panel">
          <header className="workspace-header">
            <div>
              <span className="workspace-kicker">星协</span>
              <h2>{title}</h2>
            </div>
            <div className="workspace-actions">
              <NavLink className="header-link" to="/diagnostics">
                通知
              </NavLink>
              <Button aria-label={theme === "light" ? "切换为深色模式" : "切换为浅色模式"} onClick={toggleTheme} tone="ghost">
                {theme === "light" ? "深色" : "浅色"}
              </Button>
            </div>
          </header>

          <div className="workspace-content">
            <Outlet />
          </div>

          <footer className="workspace-statusbar">
            <span className="status-dot" aria-hidden="true" />
            <span>V1 Windows 本地桌面</span>
            <span className="status-separator">·</span>
            <span>{port === null ? "桌面桥未接入" : "桌面桥已接入"}</span>
          </footer>
        </main>
      </div>
    </div>
  );
}
