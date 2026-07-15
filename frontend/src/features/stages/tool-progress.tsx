import { useStageContext } from "./stage-context";

export function ToolProgress() {
  const { agentRuns, assignment, toolCalls } = useStageContext();
  return (
    <section className="data-panel runtime-panel" aria-labelledby="runtime-progress-title">
      <header><h2 id="runtime-progress-title">模型与受控工具</h2><span>只读审计</span></header>
      <dl className="status-list">
        <div><dt>Primary Profile</dt><dd>{assignment?.primary_profile_id ?? "未分配"}</dd></div>
        <div><dt>Reviewer A</dt><dd>{assignment?.reviewer_a_profile_id ?? "未分配"}</dd></div>
        <div><dt>Reviewer B</dt><dd>{assignment?.reviewer_b_profile_id ?? "未分配"}</dd></div>
      </dl>
      <div className="runtime-list">
        {agentRuns.map((run) => (
          <article key={run.id}><strong>AgentRun · {run.status}</strong><span>{run.id} · {run.formal ? "formal" : "discussion"}</span></article>
        ))}
        {toolCalls.map((call) => (
          <article key={call.id}><strong>{call.tool_name} · {call.status}</strong><span>{call.id} · {call.capability}</span></article>
        ))}
        {agentRuns.length === 0 && toolCalls.length === 0 ? <p className="empty-copy">没有 AgentRun 或后端已鉴权的 ToolCall。</p> : null}
      </div>
      <p className="contract-note">实时模型输出使用后端 NDJSON stream；当前 DesktopPort 未暴露流式方法，因此这里只显示持久状态，不伪造 model.delta。</p>
    </section>
  );
}
