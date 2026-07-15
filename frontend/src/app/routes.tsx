import { Navigate, Route, Routes } from "react-router-dom";

import { SettingsPage } from "../features/settings/settings-page";
import { AppShell } from "./app-shell";

function FoundationPage({ title, description }: { title: string; description: string }) {
  return (
    <section className="foundation-page" aria-labelledby="foundation-title">
      <div className="eyebrow">阶段 7A · 开发前端母版</div>
      <h1 id="foundation-title">{title}</h1>
      <p>{description}</p>
      <div className="truthful-state" role="status">
        当前只建立页面边界。业务控件将在对应后端 operation 接入时出现。
      </div>
    </section>
  );
}

export function AppRoutes() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route index element={<Navigate replace to="/projects" />} />
        <Route
          path="projects"
          element={
            <FoundationPage
              title="项目"
              description="项目列表、创建、打开和预检将在阶段 7B 使用已冻结 Project API 实现。"
            />
          }
        />
        <Route
          path="diagnostics"
          element={
            <FoundationPage
              title="事件与诊断"
              description="当前已冻结事件 replay 和系统信息接口；完整诊断导出接口尚不存在。"
            />
          }
        />
        <Route path="settings" element={<SettingsPage />} />
        <Route
          path="*"
          element={
            <FoundationPage title="页面不可用" description="该地址不属于当前已锁定的前端路由。" />
          }
        />
      </Route>
    </Routes>
  );
}
