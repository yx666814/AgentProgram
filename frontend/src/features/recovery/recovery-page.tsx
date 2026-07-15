import { useCallback, useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import type {
  ConflictResolution,
  FileConflict,
  ProjectCheckpoint,
  RestorePlan,
} from "../../api/backend-api";
import { useBackend } from "../../api/backend-context";
import { ApiErrorState } from "../../components/api-error-state";
import { Button } from "../../components/button";
import { requireNativeConfirm } from "../../components/native-confirm";
import { useAsyncResource } from "../../components/use-async-resource";

function ConflictCard({
  conflict,
  checkpoints,
  disabled,
  onResolve,
}: {
  conflict: FileConflict;
  checkpoints: ProjectCheckpoint[];
  disabled: boolean;
  onResolve: (
    conflict: FileConflict,
    resolution: ConflictResolution,
    agentCheckpointId: string | null,
    mergedContentHash: string | null,
  ) => Promise<void>;
}) {
  const [resolution, setResolution] = useState<ConflictResolution>("keep_user");
  const [agentCheckpointId, setAgentCheckpointId] = useState("");
  const [mergedContentHash, setMergedContentHash] = useState("");
  const missingInput =
    (resolution === "keep_agent" && agentCheckpointId === "") ||
    (resolution === "manual_merge" && !/^[0-9a-f]{64}$/.test(mergedContentHash));

  return (
    <article className="conflict-card">
      <header><strong>{conflict.relative_path}</strong><span className="state-badge">{conflict.status}</span></header>
      <div className="hash-compare">
        <div><span>基线</span><code>{conflict.baseline_content_hash ?? "不存在"}</code></div>
        <div><span>用户版本</span><code>{conflict.user_content_hash ?? "已删除"}</code></div>
        <div><span>Agent 版本</span><code>{conflict.agent_content_hash ?? "已删除"}</code></div>
      </div>
      <label>解决方式<select onChange={(event) => {
        setResolution(event.target.value as ConflictResolution);
      }} value={resolution}><option value="keep_user">保留用户版本</option><option value="keep_agent">使用 Agent 版本</option><option value="manual_merge">已手工合并</option></select></label>
      {resolution === "keep_agent" ? <label>Agent Checkpoint<select onChange={(event) => {
        setAgentCheckpointId(event.target.value);
      }} value={agentCheckpointId}><option value="">选择检查点</option>{checkpoints.map((checkpoint) => <option key={checkpoint.id} value={checkpoint.id}>{checkpoint.id}</option>)}</select></label> : null}
      {resolution === "manual_merge" ? <label>合并后 SHA-256<input maxLength={64} onChange={(event) => {
        setMergedContentHash(event.target.value.trim());
      }} value={mergedContentHash} /></label> : null}
      <div className="page-actions"><Button disabled={disabled || missingInput} onClick={() => void onResolve(conflict, resolution, agentCheckpointId || null, mergedContentHash || null)} tone="primary">提交解决方案</Button></div>
    </article>
  );
}

export function RecoveryPage() {
  const { projectId = "" } = useParams();
  const { api, events, port } = useBackend();
  const navigate = useNavigate();
  const [pending, setPending] = useState<{ eventType: string; id: string } | null>(null);
  const [commandError, setCommandError] = useState<unknown>(null);
  const [restorePlan, setRestorePlan] = useState<RestorePlan | null>(null);

  const loadPage = useCallback(async () => {
    if (api === null) {
      throw new Error("桌面桥未接入，无法读取冲突与检查点");
    }
    const [project, conflicts, checkpoints, changes] = await Promise.all([
      api.getProject(projectId),
      api.listConflicts(projectId),
      api.listCheckpoints(projectId),
      api.listExternalChanges(projectId),
    ]);
    return { project, conflicts, checkpoints, changes };
  }, [api, projectId]);
  const { resource, reload } = useAsyncResource(loadPage);

  useEffect(() => {
    if (pending === null) {
      return;
    }
    const confirmed = events.recentEvents.some((event) => {
      if (event.event_type !== pending.eventType) {
        return false;
      }
      const key = pending.eventType === "file_conflict.resolved" ? "conflict_id" : "checkpoint_id";
      return event.payload[key] === pending.id;
    });
    if (confirmed) {
      setPending(null);
      void reload();
    }
  }, [events.recentEvents, pending, reload]);

  const resolveConflict = async (
    conflict: FileConflict,
    resolution: ConflictResolution,
    agentCheckpointId: string | null,
    mergedContentHash: string | null,
  ) => {
    if (api === null || resource.phase !== "ready") {
      return;
    }
    const confirmed = await requireNativeConfirm(port, {
      title: "解决文件冲突",
      message: `${conflict.relative_path} 将按“${resolution}”处理。`,
      detail: "后端会验证版本和 Hash；解决后项目回到 preflight_required，不会直接标记阶段完成。",
      confirmLabel: "提交解决方案",
    });
    if (!confirmed) {
      return;
    }
    setCommandError(null);
    try {
      const resolved = await api.resolveConflict({
        agentCheckpointId,
        conflict,
        expectedProjectVersion: resource.data.project.project.version,
        mergedContentHash,
        resolution,
      });
      setPending({ eventType: "file_conflict.resolved", id: resolved.conflict.id });
    } catch (error) {
      setCommandError(error);
    }
  };

  const restoreCheckpoint = async (checkpoint: ProjectCheckpoint) => {
    if (api === null || resource.phase !== "ready") {
      return;
    }
    setCommandError(null);
    try {
      const planning = await api.planRestore(projectId, checkpoint.id);
      setRestorePlan(planning);
      const confirmed = await requireNativeConfirm(port, {
        title: "恢复项目检查点",
        message: `恢复到 ${checkpoint.id}`,
        detail: `覆盖 ${String(planning.plan.overwrite_paths.length)} 个路径；保留 ${String(planning.plan.preserved_extra_paths.length)} 个额外路径；保护检查点 ${planning.protection_checkpoint.id}。`,
        confirmLabel: "执行恢复",
      });
      if (!confirmed) {
        return;
      }
      const restored = await api.restoreCheckpoint(
        projectId,
        checkpoint.id,
        planning.protection_checkpoint.id,
        resource.data.project.project.version,
      );
      setPending({ eventType: "project.checkpoint_restored", id: restored.result.restored_checkpoint_id });
    } catch (error) {
      setCommandError(error);
    }
  };

  if (resource.phase === "loading") {
    return <p className="page-loading" role="status">正在读取冲突、外部变化和检查点…</p>;
  }
  if (resource.phase === "error") {
    return <ApiErrorState error={resource.error} onRetry={() => {
      void reload();
    }} />;
  }

  const data = resource.data;
  return (
    <section className="feature-page recovery-page" aria-labelledby="recovery-page-title">
      <header className="feature-heading"><div><span className="eyebrow">{data.project.project.name}</span><h1 id="recovery-page-title">冲突、检查点与恢复</h1><p>所有写入由后端版本、Hash 和保护检查点约束。</p></div><div className="inline-actions"><Button onClick={() => {
        void navigate(`/projects/${projectId}/preflight`);
      }}>前往预检</Button><Button onClick={() => void reload()}>刷新</Button></div></header>
      {commandError !== null ? <ApiErrorState error={commandError} /> : null}
      {pending !== null ? <div className="event-wait global-wait">等待 {pending.eventType} · {pending.id}</div> : null}
      {restorePlan !== null ? <div className="restore-evidence"><strong>最近恢复计划</strong><code>{restorePlan.plan.current_checkpoint_id} → {restorePlan.plan.target_checkpoint_id}</code><span>保护检查点 {restorePlan.protection_checkpoint.id}</span></div> : null}

      <div className="recovery-grid">
        <section className="data-panel conflict-list" aria-labelledby="conflict-list-title">
          <header><h2 id="conflict-list-title">三方冲突 Hash</h2><span>{String(data.conflicts.conflicts.length)} 项</span></header>
          {data.conflicts.conflicts.map((conflict) => <ConflictCard checkpoints={data.checkpoints.checkpoints} conflict={conflict} disabled={pending !== null} key={conflict.id} onResolve={resolveConflict} />)}
          {data.conflicts.conflicts.length === 0 ? <p className="empty-copy">没有开放的文件冲突。</p> : null}
          <p className="contract-note">当前 FileConflict 契约只提供基线、用户和 Agent Hash，不提供文件正文或最早受影响阶段；前端不伪造三方文本差异。</p>
        </section>

        <div className="recovery-side-stack">
          <section className="data-panel" aria-labelledby="checkpoint-list-title">
            <header><h2 id="checkpoint-list-title">检查点</h2><span>{String(data.checkpoints.checkpoints.length)} 项</span></header>
            <div className="record-list compact-records">{data.checkpoints.checkpoints.map((checkpoint) => <article key={checkpoint.id}><header><strong>{checkpoint.reason}</strong><span>{checkpoint.id}</span></header><code>{checkpoint.content_hash}</code><small>{String(checkpoint.files.length)} 文件 · {String(checkpoint.total_bytes)} bytes</small><div className="page-actions"><Button disabled={pending !== null} onClick={() => void restoreCheckpoint(checkpoint)}>规划并恢复</Button></div></article>)}</div>
          </section>
          <section className="data-panel" aria-labelledby="external-change-title">
            <header><h2 id="external-change-title">外部变化</h2><span>{String(data.changes.changes.length)} 项</span></header>
            <div className="record-list compact-records">{data.changes.changes.map((change) => <article key={change.id}><header><strong>{change.relative_path}</strong><span className="state-badge">{change.change_type}</span></header><small>{change.status} · {change.detected_at}</small></article>)}{data.changes.changes.length === 0 ? <p className="empty-copy">没有开放的外部变化。</p> : null}</div>
          </section>
        </div>
      </div>
    </section>
  );
}
