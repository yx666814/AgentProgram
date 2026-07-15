import { useCallback, useState } from "react";

import packageJson from "../../../package.json";
import type { BackendApi, EventReplay, ToolCallList } from "../../api/backend-api";
import { useBackend } from "../../api/backend-context";
import { ApiErrorState } from "../../components/api-error-state";
import { Button } from "../../components/button";
import { useAsyncResource } from "../../components/use-async-resource";
import type { EventReadModel } from "../../events/event-reducer";

interface AuditResult {
  replay: EventReplay;
  toolCalls: ToolCallList;
}

function payloadText(payload: Record<string, unknown>, keys: string[]): string {
  for (const key of keys) {
    const value = payload[key];
    if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
      return String(value);
    }
  }
  return "未提供";
}

function DiagnosticsUnavailable() {
  return (
    <section className="foundation-page" aria-labelledby="diagnostics-title">
      <div className="eyebrow">事件与诊断</div>
      <h1 id="diagnostics-title">桌面后端未连接</h1>
      <p>连接后可读取 system/info、工作流事件重放、ToolCall 审计和恢复记录，并通过桌面桥导出脱敏诊断包。</p>
    </section>
  );
}

function EventTable({ replay }: { replay: EventReplay }) {
  return (
    <div className="diagnostic-event-list">
      {replay.events.map((event, index) => (
        <article key={`${String(event.event_id ?? "none")}-${String(index)}`}>
          <header><div><strong>{event.event_type}</strong><span>{new Date(event.occurred_at).toLocaleString()} · event {String(event.event_id ?? "未分配")}</span></div><span className="state-badge">{event.source}</span></header>
          <dl>
            <div><dt>项目</dt><dd>{event.project_id ?? "未提供"}</dd></div>
            <div><dt>工作流</dt><dd>{event.workflow_id ?? "未提供"}</dd></div>
            <div><dt>阶段</dt><dd>{payloadText(event.payload, ["stage", "target_stage"])}</dd></div>
            <div><dt>任务</dt><dd>{event.task_id ?? "未提供"}</dd></div>
            <div><dt>Room</dt><dd>{event.room_id ?? "未提供"}</dd></div>
            <div><dt>Actor</dt><dd>{event.actor.type}{event.actor.id ? ` · ${event.actor.id}` : ""}</dd></div>
            <div><dt>结果</dt><dd>{payloadText(event.payload, ["status", "result", "resolution", "error_code"])}</dd></div>
            <div><dt>Correlation</dt><dd>{event.correlation_id}</dd></div>
            <div><dt>Causation</dt><dd>{event.causation_id ?? "未提供"}</dd></div>
          </dl>
        </article>
      ))}
      {replay.events.length === 0 ? <p className="empty-copy">该游标之后没有持久事件。</p> : null}
    </div>
  );
}

function ConnectedDiagnosticsPage({
  api,
  events,
  exportDiagnostics,
  requestReplay,
}: {
  api: BackendApi;
  events: EventReadModel;
  exportDiagnostics: (input: { workflowId?: string; afterEventId?: number }) => Promise<{ cancelled: boolean; path?: string }>;
  requestReplay: (afterEventId: number) => Promise<void>;
}) {
  const loadSummary = useCallback(async () => {
    const [health, readiness, system, recoveries] = await Promise.all([
      api.health(),
      api.readiness(),
      api.systemInfo(),
      api.listRecoveries(),
    ]);
    return { health, readiness, recoveries: recoveries.recoveries, system };
  }, [api]);
  const { reload, resource } = useAsyncResource(loadSummary);
  const [workflowId, setWorkflowId] = useState("");
  const [afterEventId, setAfterEventId] = useState("0");
  const [audit, setAudit] = useState<AuditResult | null>(null);
  const [loadingAudit, setLoadingAudit] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [exporting, setExporting] = useState(false);

  const loadAudit = async () => {
    const normalizedWorkflowId = workflowId.trim();
    const normalizedCursor = Number(afterEventId);
    if (!/^workflow_[a-z0-9]+$/.test(normalizedWorkflowId)) {
      setError(new Error("Workflow ID 必须符合后端 workflow_[a-z0-9]+ 契约"));
      return;
    }
    if (!Number.isSafeInteger(normalizedCursor) || normalizedCursor < 0) {
      setError(new Error("after_event_id 必须是大于或等于 0 的整数"));
      return;
    }
    setLoadingAudit(true);
    setError(null);
    try {
      const [replay, toolCalls] = await Promise.all([
        api.replayWorkflowEvents(normalizedWorkflowId, normalizedCursor),
        api.listToolCalls(normalizedWorkflowId),
      ]);
      setAudit({ replay, toolCalls });
      setNotice(`已从后端读取 ${String(replay.events.length)} 个持久事件和 ${String(toolCalls.calls.length)} 个 ToolCall。`);
    } catch (loadError) {
      setError(loadError);
    } finally {
      setLoadingAudit(false);
    }
  };

  const syncCurrentStream = async () => {
    setError(null);
    try {
      await requestReplay(events.lastAppliedEventId);
      setNotice(`已请求从全局游标 ${String(events.lastAppliedEventId)} 继续重放；事件到达后由持久事件流更新。`);
    } catch (replayError) {
      setError(replayError);
    }
  };

  const exportPackage = async () => {
    const normalizedWorkflowId = workflowId.trim();
    const normalizedCursor = Number(afterEventId);
    if (normalizedWorkflowId !== "" && !/^workflow_[a-z0-9]+$/.test(normalizedWorkflowId)) {
      setError(new Error("导出时 Workflow ID 必须为空或符合后端 workflow_[a-z0-9]+ 契约"));
      return;
    }
    if (!Number.isSafeInteger(normalizedCursor) || normalizedCursor < 0) {
      setError(new Error("导出游标必须是大于或等于 0 的整数"));
      return;
    }
    setExporting(true);
    setError(null);
    try {
      const input: { workflowId?: string; afterEventId?: number } = {
        afterEventId: normalizedCursor,
      };
      if (normalizedWorkflowId !== "") {
        input.workflowId = normalizedWorkflowId;
      }
      const result = await exportDiagnostics(input);
      setNotice(
        result.cancelled
          ? "已取消诊断导出。"
          : `脱敏诊断包已导出到 ${result.path ?? "用户选择的位置"}。`,
      );
    } catch (exportError) {
      setError(exportError);
    } finally {
      setExporting(false);
    }
  };

  if (resource.phase === "loading") {
    return <div className="page-loading">正在读取诊断摘要…</div>;
  }
  if (resource.phase === "error") {
    return <ApiErrorState error={resource.error} onRetry={() => { void reload(); }} />;
  }

  return (
    <section className="feature-page diagnostics-page" aria-labelledby="diagnostics-title">
      <header className="feature-heading"><div><span className="eyebrow">事件、审计与诊断</span><h1 id="diagnostics-title">诊断</h1><p>事件和工具记录按真实工作流查询；敏感结果正文、源码、完整聊天和密钥不进入诊断视图。</p></div><div className="inline-actions"><Button onClick={() => { void reload(); }}>刷新摘要</Button><Button onClick={() => { void syncCurrentStream(); }}>同步当前事件流</Button></div></header>
      {notice !== null ? <div className="event-wait global-wait">{notice}</div> : null}
      {error !== null ? <ApiErrorState error={error} /> : null}
      {events.protocolIssue !== null ? <div className="api-error-state" role="alert"><strong>事件协议异常</strong><code>{events.protocolIssue}</code></div> : null}

      <div className="diagnostic-summary-grid">
        <article><span>前端包版本</span><strong>{packageJson.version}</strong><small>{packageJson.name}</small></article>
        <article><span>后端版本</span><strong>{resource.data.system.backend_version}</strong><small>protocol v{String(resource.data.system.protocol_version)}</small></article>
        <article><span>Health</span><strong>{resource.data.health.status ?? "未提供"}</strong><small>GET /health</small></article>
        <article><span>Readiness</span><strong>{resource.data.readiness.status ?? "未提供"}</strong><small>database {resource.data.readiness.database ?? "未提供"}</small></article>
        <article><span>当前事件游标</span><strong>{String(events.lastAppliedEventId)}</strong><small>最近缓存 {String(events.recentEvents.length)} 项</small></article>
      </div>

      <section className="data-panel audit-query-panel" aria-labelledby="audit-query-title">
        <header><h2 id="audit-query-title">工作流审计查询</h2><span>Event Replay + ToolCall</span></header>
        <div className="audit-query-form"><label>Workflow ID<input placeholder="workflow_demo" value={workflowId} onChange={(event) => { setWorkflowId(event.target.value); }} /></label><label>after_event_id<input inputMode="numeric" value={afterEventId} onChange={(event) => { setAfterEventId(event.target.value); }} /></label><Button disabled={loadingAudit} tone="primary" onClick={() => { void loadAudit(); }}>读取审计</Button></div>
        <p className="contract-note">`event_id` 是全局单调游标，不要求单个工作流内连续；查询只请求指定游标之后的事件。</p>
      </section>

      {audit !== null ? <div className="diagnostics-main-grid">
        <section className="data-panel" aria-labelledby="event-audit-title"><header><h2 id="event-audit-title">持久事件</h2><span>{String(audit.replay.events.length)} 项</span></header><EventTable replay={audit.replay} /></section>
        <section className="data-panel" aria-labelledby="tool-audit-title"><header><h2 id="tool-audit-title">ToolCall 审计</h2><span>{String(audit.toolCalls.calls.length)} 项</span></header><div className="tool-audit-list">{audit.toolCalls.calls.map((call) => <article key={call.id}><header><div><strong>{call.tool_name}</strong><span>{call.capability}</span></div><span className={`state-badge ${call.status === "succeeded" ? "state-ready" : call.status === "running" ? "state-running" : "state-closed"}`}>{call.status}</span></header><dl><div><dt>Call ID</dt><dd>{call.id}</dd></div><div><dt>任务</dt><dd>{call.task_id}</dd></div><div><dt>阶段运行</dt><dd>{call.stage_run_id}</dd></div><div><dt>Arguments Hash</dt><dd>{call.arguments_hash}</dd></div><div><dt>错误代码</dt><dd>{call.error_code ?? "无"}</dd></div><div><dt>时间</dt><dd>{new Date(call.started_at).toLocaleString()}</dd></div></dl></article>)}</div>{audit.toolCalls.calls.length === 0 ? <p className="empty-copy">该工作流没有 ToolCall 记录。</p> : null}<p className="contract-note">ToolCall `result` 是任意 JSON，可能包含项目内容；诊断页只显示 Hash、状态和错误代码，不渲染结果正文。</p></section>
      </div> : null}

      <div className="diagnostics-lower-grid">
        <section className="data-panel" aria-labelledby="recovery-audit-title"><header><h2 id="recovery-audit-title">恢复记录</h2><span>{String(resource.data.recoveries.length)} 项</span></header><div className="recovery-audit-list">{resource.data.recoveries.map((record) => <article key={record.id}><header><strong>{record.status}</strong><span>{record.id}</span></header><dl><div><dt>项目</dt><dd>{record.project_id}</dd></div><div><dt>工作流</dt><dd>{record.workflow_id}</dd></div><div><dt>阶段运行</dt><dd>{record.stage_run_id ?? "未提供"}</dd></div><div><dt>中断任务</dt><dd>{String(record.interrupted_tasks)}</dd></div><div><dt>中断 ToolCall</dt><dd>{String(record.interrupted_tool_calls)}</dd></div><div><dt>检测时间</dt><dd>{new Date(record.detected_at).toLocaleString()}</dd></div></dl></article>)}</div>{resource.data.recoveries.length === 0 ? <p className="empty-copy">后端没有恢复记录。</p> : null}</section>
        <section className="data-panel" aria-labelledby="diagnostic-capability-title"><header><h2 id="diagnostic-capability-title">诊断能力边界</h2><span>DesktopPort 脱敏导出</span></header><dl className="status-list"><div><dt>包含</dt><dd>版本、契约 Hash、健康/就绪、恢复记录、Sidecar 状态、脱敏日志摘要</dd></div><div><dt>可选工作流</dt><dd>安全投影的 Event 与 ToolCall 元数据</dd></div><div><dt>排除</dt><dd>源码、完整聊天、模型正文、密钥、Token、Tool 参数与结果正文</dd></div><div><dt>数据库版本</dt><dd>system/info 未提供，仍不推断</dd></div></dl><div className="unavailable-capability"><Button disabled={exporting} tone="primary" onClick={() => { void exportPackage(); }}>导出诊断包</Button><p>文件由 Electron Main 通过原生保存对话框写入；Renderer 不获得任意文件系统权限。</p></div></section>
      </div>
    </section>
  );
}

export function DiagnosticsPage() {
  const { api, events, port } = useBackend();
  if (api === null || port === null) {
    return <DiagnosticsUnavailable />;
  }
  return <ConnectedDiagnosticsPage api={api} events={events} exportDiagnostics={(input) => port.diagnostics.export(input)} requestReplay={(afterEventId) => port.backend.requestReplay(afterEventId)} />;
}
