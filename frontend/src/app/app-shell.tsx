import { NavLink, Outlet, useLocation } from "react-router-dom";

import { Button } from "../components/button";
import { useTheme } from "../theme/theme-provider";

const stageLabels = ["Planner", "Designer", "Builder", "Reviewer", "Deployer"] as const;

const pageTitles: Record<string, string> = {
  "/projects": "项目",
  "/diagnostics": "事件与诊断",
  "/settings": "设置",
};

function navigationClass({ isActive }: { isActive: boolean }): string {
  return isActive ? "nav-link nav-link-active" : "nav-link";
}

export function AppShell() {
  const location = useLocation();
  const { theme, toggleTheme } = useTheme();
  const pageTitle = pageTitles[location.pathname] ?? "星协";

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
            <div className="nav-section-label">五阶段</div>
            {stageLabels.map((stage) => (
              <div
                aria-disabled="true"
                className="nav-link nav-link-disabled"
                key={stage}
                title="先打开项目并创建工作流"
              >
                <span>{stage}</span>
                <span className="nav-lock">锁定</span>
              </div>
            ))}
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
              <h2>{pageTitle}</h2>
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
            <span>阶段 7A 前端母版</span>
            <span className="status-separator">·</span>
            <span>后端桥接将在阶段 8 接入</span>
          </footer>
        </main>
      </div>
    </div>
  );
}
