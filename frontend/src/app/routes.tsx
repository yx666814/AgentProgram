import { Navigate, Route, Routes } from "react-router-dom";

import { ProjectOverviewPage } from "../features/overview/project-overview-page";
import { PreflightPage } from "../features/preflight/preflight-page";
import { ProjectsPage } from "../features/projects/projects-page";
import { SettingsPage } from "../features/settings/settings-page";
import { StartupPage } from "../features/startup/startup-page";
import { AppShell } from "./app-shell";

function UnavailablePage() {
  return (
    <section className="foundation-page" aria-labelledby="unavailable-title">
      <div className="eyebrow">路由不可用</div>
      <h1 id="unavailable-title">页面不存在</h1>
      <p>该地址不属于当前已锁定的前端路由。</p>
    </section>
  );
}

export function AppRoutes() {
  return (
    <Routes>
      <Route index element={<Navigate replace to="/startup" />} />
      <Route path="startup" element={<StartupPage />} />
      <Route element={<AppShell />}>
        <Route path="projects" element={<ProjectsPage />} />
        <Route path="projects/:projectId/preflight" element={<PreflightPage />} />
        <Route path="projects/:projectId" element={<ProjectOverviewPage />} />
        <Route path="settings" element={<SettingsPage />} />
        <Route path="diagnostics" element={<UnavailablePage />} />
        <Route path="*" element={<UnavailablePage />} />
      </Route>
    </Routes>
  );
}
