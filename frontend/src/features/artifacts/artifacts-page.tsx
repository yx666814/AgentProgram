import { useCallback } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { useBackend } from "../../api/backend-context";
import { ApiErrorState } from "../../components/api-error-state";
import { Button } from "../../components/button";
import { useAsyncResource } from "../../components/use-async-resource";
import { loadWorkflowScope } from "../workflow-scope";

function localTime(value: string): string {
  return new Date(value).toLocaleString();
}

export function ArtifactsPage() {
  const { projectId = "" } = useParams();
  const { api } = useBackend();
  const navigate = useNavigate();

  const loadPage = useCallback(async () => {
    if (api === null) {
      throw new Error("桌面桥未接入，无法读取产出与 Gate");
    }
    const scope = await loadWorkflowScope(api, projectId);
    const workflowId = scope.workflow.workflow.id;
    const [artifacts, gates, approvals, handoffs, changeRequests] = await Promise.all([
      api.listArtifacts(workflowId),
      api.listQualityGates(workflowId),
      api.listApprovals(workflowId),
      api.listHandoffs(workflowId),
      api.listChangeRequests(workflowId),
    ]);
    return { ...scope, artifacts, gates, approvals, handoffs, changeRequests };
  }, [api, projectId]);
  const { resource, reload } = useAsyncResource(loadPage);

  if (resource.phase === "loading") {
    return <p className="page-loading" role="status">正在读取 ArtifactVersion、Gate 与 Handoff…</p>;
  }
  if (resource.phase === "error") {
    return <ApiErrorState error={resource.error} onRetry={() => {
      void reload();
    }} />;
  }

  const data = resource.data;
  return (
    <section className="feature-page governance-page" aria-labelledby="artifacts-title">
      <header className="feature-heading">
        <div><span className="eyebrow">{data.project.project.name}</span><h1 id="artifacts-title">产出、Gate 与交接</h1><p>ArtifactVersion 和 HandoffPacket 只读显示；历史版本不会被覆盖。</p></div>
        <div className="inline-actions">
          <Button onClick={() => {
            void navigate(`/projects/${projectId}/approvals`);
          }}>审批与能力</Button>
          <Button onClick={() => void reload()}>刷新</Button>
        </div>
      </header>

      <div className="governance-metrics">
        <article><span>Artifacts</span><strong>{String(data.artifacts.artifacts.length)}</strong><small>版本 {String(data.artifacts.versions.length)}</small></article>
        <article><span>Quality Gates</span><strong>{String(data.gates.gates.length)}</strong><small>只显示后端判定</small></article>
        <article><span>Handoffs</span><strong>{String(data.handoffs.handoffs.length)}</strong><small>active / invalidated</small></article>
        <article><span>Change Requests</span><strong>{String(data.changeRequests.change_requests.length)}</strong><small>历史可审计</small></article>
      </div>

      <div className="governance-grid">
        <section className="data-panel" aria-labelledby="artifact-list-title">
          <header><h2 id="artifact-list-title">不可变产出版本</h2><span>Hash 证据</span></header>
          {data.artifacts.versions.length === 0 ? <p className="empty-copy">当前工作流还没有 ArtifactVersion。</p> : null}
          <div className="record-list">
            {data.artifacts.versions.map((version) => {
              const artifact = data.artifacts.artifacts.find(({ id }) => id === version.artifact_id);
              return (
                <article key={version.id}>
                  <header><strong>{artifact?.name ?? version.artifact_id}</strong><span className="state-badge">{version.status}</span></header>
                  <code>{version.content_hash}</code>
                  <dl><div><dt>版本</dt><dd>{String(version.version)}</dd></div><div><dt>字节</dt><dd>{String(version.byte_size)}</dd></div><div><dt>本地时间</dt><dd>{localTime(version.created_at)}</dd></div><div><dt>UTC</dt><dd>{version.created_at}</dd></div></dl>
                  {version.invalidation_reason !== null && version.invalidation_reason !== undefined ? <p className="record-warning">失效：{version.invalidation_reason}</p> : null}
                </article>
              );
            })}
          </div>
        </section>

        <section className="data-panel" aria-labelledby="gate-chain-title">
          <header><h2 id="gate-chain-title">完成链</h2><span>不把 accepted 当 completed</span></header>
          {data.gates.gates.length === 0 ? <p className="empty-copy">当前工作流还没有 Quality Gate。</p> : null}
          <div className="record-list">
            {data.gates.gates.map((gate) => {
              const approval = data.approvals.approvals.find(({ target_id }) => target_id === gate.id);
              const handoff = data.handoffs.handoffs.find(({ gate_run_id }) => gate_run_id === gate.id);
              return (
                <article key={gate.id}>
                  <header><strong>{gate.status.toUpperCase()} · {gate.resolution}</strong><span>{gate.id}</span></header>
                  <div className="completion-chain">
                    <span data-complete={gate.artifact_version_ids.length > 0}>Artifact</span>
                    <span data-complete={gate.status === "pass" || gate.status === "warning"}>Gate</span>
                    <span data-complete={approval?.status === "approved" || gate.resolution === "automatic"}>Approval/Policy</span>
                    <span data-complete={handoff !== undefined}>Checkpoint + Handoff</span>
                  </div>
                  {gate.issues.map((issue) => <p className={`gate-issue issue-${issue.severity}`} key={issue.code}>{issue.code} · {issue.message}</p>)}
                </article>
              );
            })}
          </div>
        </section>

        <section className="data-panel" aria-labelledby="handoff-list-title">
          <header><h2 id="handoff-list-title">Handoff</h2><span>内容寻址</span></header>
          <div className="record-list compact-records">
            {data.handoffs.handoffs.map((handoff) => <article key={handoff.id}><header><strong>{handoff.from_stage} → {handoff.to_stage ?? "完成"}</strong><span className="state-badge">{handoff.status}</span></header><code>{handoff.content_hash}</code><small>Checkpoint {handoff.checkpoint_id}</small>{handoff.invalidation_reason !== null && handoff.invalidation_reason !== undefined ? <p className="record-warning">{handoff.invalidation_reason}</p> : null}</article>)}
            {data.handoffs.handoffs.length === 0 ? <p className="empty-copy">还没有 HandoffPacket。</p> : null}
          </div>
        </section>

        <section className="data-panel" aria-labelledby="change-request-title">
          <header><h2 id="change-request-title">返工与失效记录</h2><span>无前端次数上限</span></header>
          <div className="record-list compact-records">
            {data.changeRequests.change_requests.map((request) => <article key={request.id}><header><strong>返回 {request.target_stage}</strong><span className="state-badge">{request.status}</span></header><p>{request.reason}</p><small>{request.id} · 输入版本 {String(request.input_artifact_version_ids.length)}</small></article>)}
            {data.changeRequests.change_requests.length === 0 ? <p className="empty-copy">没有 ChangeRequest。</p> : null}
          </div>
        </section>
      </div>
    </section>
  );
}
