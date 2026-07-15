import { useCallback, useState } from "react";
import { useNavigate } from "react-router-dom";

import {
  type HealthResponse,
  type ReadinessResponse,
  type RecoveryList,
  type SystemInfo,
} from "../../api/backend-api";
import { useBackend } from "../../api/backend-context";
import { ApiRequestError } from "../../api/errors";
import { ApiErrorState } from "../../components/api-error-state";
import { Button } from "../../components/button";
import { useAsyncResource } from "../../components/use-async-resource";

type OperationResult<T> = { ok: true; value: T } | { ok: false; error: unknown };

interface StartupSnapshot {
  health: OperationResult<HealthResponse>;
  readiness: OperationResult<ReadinessResponse>;
  systemInfo: OperationResult<SystemInfo>;
  recoveries: OperationResult<RecoveryList>;
}

async function capture<T>(request: Promise<T>): Promise<OperationResult<T>> {
  try {
    return { ok: true, value: await request };
  } catch (error) {
    return { ok: false, error };
  }
}

function resultLabel(result: OperationResult<unknown>, success: string): string {
  if (result.ok) {
    return success;
  }
  return result.error instanceof ApiRequestError ? result.error.code : "不可用";
}

export function StartupPage() {
  const { api, port } = useBackend();
  const navigate = useNavigate();
  const [actionError, setActionError] = useState<unknown>(null);
  const [resolvingId, setResolvingId] = useState<string | null>(null);

  const loadStartup = useCallback(async (): Promise<StartupSnapshot> => {
    if (api === null) {
      throw new Error("桌面桥未接入，无法访问后端");
    }
    const [health, readiness, systemInfo, recoveries] = await Promise.all([
      capture(api.health()),
      capture(api.readiness()),
      capture(api.systemInfo()),
      capture(api.listRecoveries()),
    ]);
    return { health, readiness, systemInfo, recoveries };
  }, [api]);
  const { resource, reload } = useAsyncResource(loadStartup);

  const resolveRecovery = async (recoveryId: string, action: "resume" | "discard") => {
    if (api === null || port === null) {
      return;
    }
    if (action === "discard") {
      const confirmed = await port.showNativeConfirm({
        title: "放弃恢复记录",
        message: "工作流将停止，未完成任务会保持取消状态。",
        detail: "该操作不会删除 Direct Workspace 中的用户文件。",
        confirmLabel: "放弃恢复",
      });
      if (!confirmed) {
        return;
      }
    }
    setResolvingId(recoveryId);
    setActionError(null);
    try {
      await api.resolveRecovery(recoveryId, action);
      await reload();
    } catch (error) {
      setActionError(error);
    } finally {
      setResolvingId(null);
    }
  };

  if (resource.phase === "loading") {
    return <div className="startup-loading" role="status">正在检查后端与恢复状态…</div>;
  }
  if (resource.phase === "error") {
    return (
      <main className="startup-screen">
        <section className="startup-card">
          <h1>启动星协</h1>
          <ApiErrorState error={resource.error} onRetry={() => void reload()} />
        </section>
      </main>
    );
  }

  const snapshot = resource.data;
  const protocolReady = snapshot.systemInfo.ok && snapshot.systemInfo.value.protocol_version === 1;
  const backendReady = snapshot.health.ok && snapshot.readiness.ok && protocolReady;
  const pendingRecoveries = snapshot.recoveries.ok
    ? snapshot.recoveries.value.recoveries.filter(({ status }) => status === "pending")
    : [];

  return (
    <main className="startup-screen">
      <section className="startup-card" aria-labelledby="startup-title">
        <header className="startup-heading">
          <img alt="" src="/xingxie-icon.svg" />
          <div>
            <h1 id="startup-title">启动星协</h1>
            <p>本地后端与恢复检查</p>
          </div>
        </header>

        <div className="startup-grid">
          <section className="data-panel" aria-labelledby="system-status-title">
            <header><h2 id="system-status-title">系统状态</h2><span>真实接口</span></header>
            <dl className="status-list">
              <div><dt>后端健康</dt><dd>{resultLabel(snapshot.health, "ok")}</dd></div>
              <div><dt>数据库就绪</dt><dd>{resultLabel(snapshot.readiness, "ready")}</dd></div>
              <div>
                <dt>协议版本</dt>
                <dd>{snapshot.systemInfo.ok ? `protocol ${String(snapshot.systemInfo.value.protocol_version)}` : resultLabel(snapshot.systemInfo, "")}</dd>
              </div>
              <div>
                <dt>后端版本</dt>
                <dd>{snapshot.systemInfo.ok ? snapshot.systemInfo.value.backend_version : "—"}</dd>
              </div>
            </dl>
          </section>

          <section className="data-panel" aria-labelledby="recovery-title">
            <header><h2 id="recovery-title">可恢复内容</h2><span>{String(pendingRecoveries.length)} 项</span></header>
            {!snapshot.recoveries.ok ? <ApiErrorState error={snapshot.recoveries.error} /> : null}
            {snapshot.recoveries.ok && pendingRecoveries.length === 0 ? (
              <p className="empty-copy">没有待处理的恢复记录。</p>
            ) : null}
            {pendingRecoveries.map((recovery) => (
              <article className="recovery-row" key={recovery.id}>
                <div>
                  <strong>{recovery.workflow_id}</strong>
                  <span>任务 {String(recovery.interrupted_tasks)} · Agent {String(recovery.interrupted_agent_runs)} · 工具 {String(recovery.interrupted_tool_calls)}</span>
                </div>
                <div className="inline-actions">
                  <Button disabled={resolvingId === recovery.id} onClick={() => void resolveRecovery(recovery.id, "discard")}>放弃</Button>
                  <Button disabled={resolvingId === recovery.id} onClick={() => void resolveRecovery(recovery.id, "resume")} tone="primary">继续恢复</Button>
                </div>
              </article>
            ))}
          </section>
        </div>

        {actionError !== null ? <ApiErrorState error={actionError} /> : null}

        <footer className="page-actions">
          <Button disabled={port === null} onClick={() => void port?.requestWindowClose()}>退出</Button>
          <Button onClick={() => void reload()}>重新检查</Button>
          <Button
            disabled={!backendReady}
            {...(!backendReady ? { disabledReason: "后端健康、数据库就绪和协议版本必须全部通过" } : {})}
            onClick={() => {
              void navigate("/projects");
            }}
            tone="primary"
          >
            进入项目
          </Button>
        </footer>
      </section>
    </main>
  );
}
