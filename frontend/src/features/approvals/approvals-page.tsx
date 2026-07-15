import { useCallback, useEffect, useState } from "react";
import { useParams } from "react-router-dom";

import type { Approval, CapabilityRequest } from "../../api/backend-api";
import { useBackend } from "../../api/backend-context";
import { ApiErrorState } from "../../components/api-error-state";
import { Button } from "../../components/button";
import { useAsyncResource } from "../../components/use-async-resource";
import { loadWorkflowScope } from "../workflow-scope";

export function ApprovalsPage() {
  const { projectId = "" } = useParams();
  const { api, events } = useBackend();
  const [reason, setReason] = useState("");
  const [pending, setPending] = useState<{ eventType: string; id: string } | null>(null);
  const [commandError, setCommandError] = useState<unknown>(null);

  const loadPage = useCallback(async () => {
    if (api === null) {
      throw new Error("桌面桥未接入，无法读取审批与能力申请");
    }
    const scope = await loadWorkflowScope(api, projectId);
    const workflowId = scope.workflow.workflow.id;
    const [approvals, capabilities, gates] = await Promise.all([
      api.listApprovals(workflowId),
      api.listCapabilityRequests(workflowId),
      api.listQualityGates(workflowId),
    ]);
    return { ...scope, approvals, capabilities, gates };
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
      const key = pending.eventType === "approval.decided" ? "approval_id" : "request_id";
      return event.payload[key] === pending.id;
    });
    if (confirmed) {
      setPending(null);
      setReason("");
      void reload();
    }
  }, [events.recentEvents, pending, reload]);

  const decideApproval = async (approval: Approval, approved: boolean) => {
    if (api === null) {
      return;
    }
    setCommandError(null);
    try {
      const decided = await api.decideApproval(approval, approved, reason.trim() || null);
      setPending({ eventType: "approval.decided", id: decided.approval.id });
    } catch (error) {
      setCommandError(error);
    }
  };

  const decideCapability = async (request: CapabilityRequest, approved: boolean) => {
    if (api === null) {
      return;
    }
    setCommandError(null);
    try {
      const decided = await api.decideCapability(request, approved, reason.trim() || null);
      setPending({ eventType: "capability.decided", id: decided.id });
    } catch (error) {
      setCommandError(error);
    }
  };

  if (resource.phase === "loading") {
    return <p className="page-loading" role="status">正在读取审批和能力申请…</p>;
  }
  if (resource.phase === "error") {
    return <ApiErrorState error={resource.error} onRetry={() => {
      void reload();
    }} />;
  }

  const data = resource.data;
  const pendingApprovals = data.approvals.approvals.filter(({ status }) => status === "pending");
  const pendingCapabilities = data.capabilities.requests.filter(({ status }) => status === "pending");

  return (
    <section className="feature-page governance-page" aria-labelledby="approvals-title">
      <header className="feature-heading"><div><span className="eyebrow">{data.project.project.name}</span><h1 id="approvals-title">审批、能力与风险</h1><p>决定只发送到后端，并等待持久化决定事件。</p></div><Button onClick={() => void reload()}>刷新</Button></header>
      {commandError !== null ? <ApiErrorState error={commandError} /> : null}
      {pending !== null ? <div className="event-wait global-wait">等待 {pending.eventType} · {pending.id}</div> : null}
      <label className="decision-reason">决定原因（可选）<textarea onChange={(event) => {
        setReason(event.target.value);
      }} rows={2} value={reason} /></label>

      <div className="approval-grid">
        <section className="data-panel" aria-labelledby="gate-approval-title">
          <header><h2 id="gate-approval-title">Quality Gate 审批</h2><span>{String(pendingApprovals.length)} 待处理</span></header>
          <div className="record-list">
            {data.approvals.approvals.map((approval) => {
              const gate = data.gates.gates.find(({ id }) => id === approval.target_id);
              const actionable = approval.status === "pending" && gate?.status !== "fail";
              return <article key={approval.id}><header><strong>{gate?.status.toUpperCase() ?? approval.kind}</strong><span className="state-badge">{approval.status}</span></header><p>{gate?.issues.map(({ message }) => message).join("；") || "无结构化问题"}</p><small>{approval.id} · Gate {approval.target_id}</small>{actionable ? <div className="inline-actions"><Button disabled={pending !== null} onClick={() => void decideApproval(approval, false)}>要求重写</Button><Button disabled={pending !== null} onClick={() => void decideApproval(approval, true)} tone="primary">批准</Button></div> : null}</article>;
            })}
            {data.approvals.approvals.length === 0 ? <p className="empty-copy">没有 Gate 审批。</p> : null}
          </div>
          {data.workflow.workflow.execution_mode === "autonomous" && data.gates.gates.some(({ status, resolution }) => status === "warning" && resolution === "pending") ? <p className="contract-note">AUTONOMOUS WARNING 由后端保持 warning_blocked；这里不提供人工批准捷径。</p> : null}
        </section>

        <section className="data-panel" aria-labelledby="capability-approval-title">
          <header><h2 id="capability-approval-title">能力申请</h2><span>{String(pendingCapabilities.length)} 待处理</span></header>
          <div className="record-list">
            {data.capabilities.requests.map((request) => <article key={request.id}><header><strong>{request.capability}</strong><span className="state-badge">{request.status}</span></header><p>{request.reason}</p><dl><div><dt>阶段</dt><dd>{request.stage}</dd></div><div><dt>风险</dt><dd>{request.risk_level}</dd></div><div><dt>目标路径</dt><dd>{request.target_paths.join("、") || "无"}</dd></div><div><dt>命令</dt><dd>{request.command?.join(" ") ?? "无"}</dd></div></dl>{request.status === "pending" ? <div className="inline-actions"><Button disabled={pending !== null} onClick={() => void decideCapability(request, false)}>拒绝</Button><Button disabled={pending !== null} onClick={() => void decideCapability(request, true)} tone="primary">批准</Button></div> : null}</article>)}
            {data.capabilities.requests.length === 0 ? <p className="empty-copy">没有能力申请。</p> : null}
          </div>
        </section>
      </div>
    </section>
  );
}
