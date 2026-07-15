import { Navigate, Route, Routes } from "react-router-dom";

import { ApprovalsPage } from "../features/approvals/approvals-page";
import { ArtifactsPage } from "../features/artifacts/artifacts-page";
import { ProjectOverviewPage } from "../features/overview/project-overview-page";
import { PreflightPage } from "../features/preflight/preflight-page";
import { ProjectsPage } from "../features/projects/projects-page";
import { RecoveryPage } from "../features/recovery/recovery-page";
import { SettingsPage } from "../features/settings/settings-page";
import { StartupPage } from "../features/startup/startup-page";
import { StageWorkspacePage } from "../features/stages/stage-workspace-page";
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
        <Route path="projects/:projectId/stages/:stage" element={<StageWorkspacePage />} />
        <Route path="projects/:projectId/artifacts" element={<ArtifactsPage />} />
        <Route path="projects/:projectId/approvals" element={<ApprovalsPage />} />
        <Route path="projects/:projectId/recovery" element={<RecoveryPage />} />
        <Route path="projects/:projectId" element={<ProjectOverviewPage />} />
        <Route path="settings" element={<SettingsPage />} />
        <Route path="diagnostics" element={<UnavailablePage />} />
        <Route path="*" element={<UnavailablePage />} />
      </Route>
    </Routes>
  );
}
