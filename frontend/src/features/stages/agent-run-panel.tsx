import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import type {
  AgentRunSnapshot,
  AgentStreamFrame,
  BackendApi,
  ModelProfile,
  OrchestrationFrame,
} from "../../api/backend-api";
import { ApiErrorState } from "../../components/api-error-state";
import { Button } from "../../components/button";
import { useStageContext } from "./stage-context";

function streamTranscript(frames: AgentStreamFrame[]): string {
  const parts: string[] = [];
  for (const frame of frames) {
    if (frame.type === "call_started") {
      parts.push(`\n[${frame.role ?? "model"} · ${frame.phase ?? "phase"}]\n`);
    } else if (frame.type === "chunk" && frame.text !== null) {
      parts.push(frame.text);
    } else if (frame.type === "error") {
      parts.push(`\n[error · ${frame.error_code ?? "unknown"}]\n`);
    }
  }
  return parts.join("").trim();
}

export function AgentRunPanel({
  api,
  canRun,
  onReload,
}: {
  api: BackendApi;
  canRun: boolean;
  onReload: () => Promise<unknown>;
}) {
  const navigate = useNavigate();
  const { agentRuns, assignment, room, stageRun, workflow } = useStageContext();
  const [instruction, setInstruction] = useState("");
  const [formal, setFormal] = useState(true);
  const [profiles, setProfiles] = useState<ModelProfile[]>([]);
  const [primaryProfileId, setPrimaryProfileId] = useState("");
  const [reviewerAProfileId, setReviewerAProfileId] = useState("");
  const [reviewerBProfileId, setReviewerBProfileId] = useState("");
  const [assignmentBusy, setAssignmentBusy] = useState(false);
  const [activeRunId, setActiveRunId] = useState<string | null>(null);
  const [frames, setFrames] = useState<AgentStreamFrame[]>([]);
  const [orchestrationFrames, setOrchestrationFrames] = useState<OrchestrationFrame[]>([]);
  const [orchestrationRequestKey, setOrchestrationRequestKey] = useState<string | null>(null);
  const [snapshot, setSnapshot] = useState<AgentRunSnapshot | null>(null);
  const [output, setOutput] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [loadingRunId, setLoadingRunId] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<unknown>(null);

  useEffect(() => {
    setActiveRunId(null);
    setFrames([]);
    setOrchestrationFrames([]);
    setOrchestrationRequestKey(null);
    setSnapshot(null);
    setOutput(null);
    setNotice(null);
    setError(null);
  }, [room.id]);

  useEffect(() => {
    setPrimaryProfileId(assignment?.primary_profile_id ?? "");
    setReviewerAProfileId(assignment?.reviewer_a_profile_id ?? "");
    setReviewerBProfileId(assignment?.reviewer_b_profile_id ?? "");
  }, [assignment, room.id]);

  useEffect(() => {
    let active = true;
    void api.listModelProfiles().then(
      (result) => {
        if (active) {
          setProfiles([...result.profiles]);
        }
      },
      (profileError: unknown) => {
        if (active) {
          setError(profileError);
        }
      },
    );
    return () => {
      active = false;
    };
  }, [api, room.id]);

  const formalReady =
    assignment?.reviewer_a_profile_id !== null &&
    assignment?.reviewer_a_profile_id !== undefined &&
    assignment.reviewer_b_profile_id !== null &&
    assignment.reviewer_b_profile_id !== undefined;
  const formalRunnable = ["ready", "discussing", "producing", "needs_fix"].includes(stageRun.state);
  const blockedReason =
    assignment === null
      ? "必须先在设置页为当前 Room 保存模型分配"
      : formal && !formalRunnable
        ? "当前阶段状态不能启动正式编排"
      : !formal && !canRun
        ? "讨论运行只允许当前活动阶段处于 discussing、producing 或 p2r_reviewing"
        : formal && !formalReady
          ? "正式运行必须同时分配 Primary、Reviewer A 和 Reviewer B"
          : instruction.trim() === ""
            ? "请输入本次 AgentRun 指令"
            : null;
  const selectedProfileIds = [primaryProfileId, reviewerAProfileId, reviewerBProfileId];
  const enabledProfileIds = new Set(
    profiles.filter((profile) => profile.enabled).map((profile) => profile.id),
  );
  const assignmentReady =
    selectedProfileIds.every((profileId) => enabledProfileIds.has(profileId)) &&
    new Set(selectedProfileIds).size === selectedProfileIds.length;
  const transcript = useMemo(() => streamTranscript(frames), [frames]);
  const lastFrame = frames.at(-1) ?? null;

  const loadRun = async (runId: string) => {
    setLoadingRunId(runId);
    setError(null);
    try {
      const nextSnapshot = await api.getAgentRun(runId);
      setSnapshot(nextSnapshot);
      setActiveRunId(runId);
      if (nextSnapshot.run.final_output_ref !== null && nextSnapshot.run.final_output_ref !== undefined) {
        setOutput(await api.getAgentRunOutput(runId));
      } else {
        setOutput(null);
      }
    } catch (loadError) {
      setError(loadError);
    } finally {
      setLoadingRunId(null);
    }
  };

  const startRun = async () => {
    if (blockedReason !== null) {
      return;
    }
    setBusy(true);
    setError(null);
    setNotice(null);
    setFrames([]);
    setOrchestrationFrames([]);
    setSnapshot(null);
    setOutput(null);
    let streamedRunId: string | null = null;
    try {
      if (formal) {
        const requestKey =
          orchestrationRequestKey ?? `orchestration-${crypto.randomUUID()}`;
        setOrchestrationRequestKey(requestKey);
        setNotice("正式编排已提交，后端正在推进任务、双校、工具、产物与 Gate。 ");
        const terminalErrors: OrchestrationFrame[] = [];
        await api.streamOrchestration(workflow.workflow.id, instruction.trim(), requestKey, (frame) => {
          setOrchestrationFrames((current) => [...current, frame].slice(-500));
          if (frame.agent_run_id !== null) {
            streamedRunId = frame.agent_run_id;
            setActiveRunId(frame.agent_run_id);
          }
          const nested = frame.data.agent_frame;
          if (typeof nested === "object" && nested !== null && !Array.isArray(nested)) {
            setFrames((current) => [...current, nested as AgentStreamFrame].slice(-500));
          }
          if (frame.type === "error") {
            terminalErrors.push(frame);
          }
        });
        const failedFrame = terminalErrors.at(-1);
        if (failedFrame !== undefined) {
          setOrchestrationRequestKey(null);
          throw new Error(`${failedFrame.error_code ?? "orchestration.failed"}: ${failedFrame.text ?? "正式编排失败"}`);
        }
      } else {
        const creation = await api.createAgentRun(room.id, false);
        streamedRunId = creation.run.id;
        setActiveRunId(streamedRunId);
        setNotice(creation.created ? `已创建 ${streamedRunId}，正在接收流式帧。` : `复用 ${streamedRunId}。`);
        await api.streamAgentRun(streamedRunId, instruction.trim(), (frame) => {
          setFrames((current) => [...current, frame].slice(-500));
        });
      }
      if (streamedRunId === null) {
        throw new Error("后端编排没有返回 AgentRun ID");
      }
      const nextSnapshot = await api.getAgentRun(streamedRunId);
      setSnapshot(nextSnapshot);
      if (nextSnapshot.run.final_output_ref !== null && nextSnapshot.run.final_output_ref !== undefined) {
        setOutput(await api.getAgentRunOutput(streamedRunId));
      }
      setNotice(formal ? "正式编排已到达后端确认的终态。" : `AgentRun 已结束：${nextSnapshot.run.status}。`);
      if (formal) {
        setOrchestrationRequestKey(null);
      }
      await onReload();
    } catch (runError) {
      setError(runError);
      setNotice("运行未正常完成；后端已保留真实任务、调用和错误记录，可保留原指令重试。 ");
      await onReload().catch(() => undefined);
    } finally {
      setBusy(false);
    }
  };

  const saveAssignment = async () => {
    if (!assignmentReady) {
      return;
    }
    setAssignmentBusy(true);
    setError(null);
    setNotice(null);
    try {
      const receipt = await api.assignRoomModels({
        assignment,
        primaryProfileId,
        reviewerAProfileId,
        reviewerBProfileId,
        roomId: room.id,
      });
      setNotice(`当前阶段模型分配已保存：${receipt.payload.room_id}`);
      await onReload();
    } catch (assignmentError) {
      setError(assignmentError);
    } finally {
      setAssignmentBusy(false);
    }
  };

  const cancelRun = async () => {
    if (activeRunId === null) {
      return;
    }
    setError(null);
    try {
      const result = await api.cancelAgentRun(activeRunId);
      setOrchestrationRequestKey(null);
      setNotice(
        result.cancellation_requested
          ? `已向 ${activeRunId} 请求取消，等待流结束。`
          : `${activeRunId} 已处于 ${result.run.status}，无需再次取消。`,
      );
    } catch (cancelError) {
      setError(cancelError);
    }
  };

  return (
    <section className="data-panel agent-run-panel" aria-labelledby="agent-run-title">
      <header>
        <h2 id="agent-run-title">AgentRun</h2>
        <span>后端真实模型运行</span>
      </header>
      {notice !== null ? <div className="event-wait">{notice}</div> : null}
      {error !== null ? <ApiErrorState error={error} /> : null}

      <div className="agent-run-composer">
        <label>
          运行指令
          <textarea
            aria-label="AgentRun 指令"
            disabled={busy}
            maxLength={100000}
            onChange={(event) => { setInstruction(event.target.value); }}
            placeholder="说明当前阶段需要模型完成和审查的工作"
            rows={4}
            value={instruction}
          />
        </label>
        <label className="inline-check">
          <input
            aria-label="正式运行（一主双校）"
            checked={formal}
            disabled={busy}
            onChange={(event) => { setFormal(event.target.checked); }}
            type="checkbox"
          />
          正式编排（一主双校）
        </label>
        <div className="agent-assignment-editor">
          <div className="agent-assignment-fields">
            <label>
              Primary
              <select
                aria-label="当前阶段 Primary"
                disabled={busy || assignmentBusy}
                onChange={(event) => { setPrimaryProfileId(event.target.value); }}
                value={primaryProfileId}
              >
                <option value="">请选择</option>
                {profiles.map((profile) => (
                  <option disabled={!profile.enabled} key={profile.id} value={profile.id}>
                    {profile.name} · {profile.model}{profile.enabled ? "" : "（已禁用）"}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Reviewer A
              <select
                aria-label="当前阶段 Reviewer A"
                disabled={busy || assignmentBusy}
                onChange={(event) => { setReviewerAProfileId(event.target.value); }}
                value={reviewerAProfileId}
              >
                <option value="">请选择</option>
                {profiles.map((profile) => (
                  <option disabled={!profile.enabled} key={profile.id} value={profile.id}>
                    {profile.name} · {profile.model}{profile.enabled ? "" : "（已禁用）"}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Reviewer B
              <select
                aria-label="当前阶段 Reviewer B"
                disabled={busy || assignmentBusy}
                onChange={(event) => { setReviewerBProfileId(event.target.value); }}
                value={reviewerBProfileId}
              >
                <option value="">请选择</option>
                {profiles.map((profile) => (
                  <option disabled={!profile.enabled} key={profile.id} value={profile.id}>
                    {profile.name} · {profile.model}{profile.enabled ? "" : "（已禁用）"}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <div className="page-actions agent-assignment-actions">
            <Button
              disabled={busy || assignmentBusy || !assignmentReady}
              {...(!assignmentReady ? { disabledReason: "请选择三个不同且已启用的模型配置" } : {})}
              onClick={() => { void saveAssignment(); }}
            >
              {assignmentBusy ? "保存中" : "保存当前阶段分配"}
            </Button>
            {profiles.length === 0 ? (
              <Button onClick={() => { void navigate("/settings"); }}>创建模型配置</Button>
            ) : null}
          </div>
        </div>
        <div className="page-actions">
          <Button
            disabled={busy || blockedReason !== null}
            {...(blockedReason !== null ? { disabledReason: blockedReason } : {})}
            onClick={() => { void startRun(); }}
            tone="primary"
          >
            {busy ? "正在运行" : formal ? "运行并完成本阶段" : "开始讨论运行"}
          </Button>
          <Button disabled={!busy || activeRunId === null} onClick={() => { void cancelRun(); }}>
            取消运行
          </Button>
        </div>
      </div>

      {activeRunId !== null ? (
        <div className="agent-live-state">
          <div className="agent-live-heading">
            <strong>{activeRunId}</strong>
            <span>{lastFrame === null ? "等待首帧" : `${lastFrame.type} · #${String(lastFrame.sequence)}`}</span>
          </div>
          <pre aria-live="polite">{transcript || "流已建立，等待模型输出…"}</pre>
        </div>
      ) : null}

      {orchestrationFrames.length > 0 ? (
        <div className="orchestration-progress" aria-live="polite">
          {orchestrationFrames.slice(-8).map((frame) => (
            <span className={frame.type === "error" ? "state-error" : ""} key={frame.sequence}>
              {frame.type.replaceAll("_", " ")}{frame.text === null ? "" : ` · ${frame.text}`}
            </span>
          ))}
        </div>
      ) : null}

      <div className="agent-run-history">
        {agentRuns.map((run) => (
          <article key={run.id}>
            <div><strong>{run.status}</strong><span>{run.id} · {run.formal ? "formal" : "discussion"}</span></div>
            <Button disabled={loadingRunId !== null || busy} onClick={() => { void loadRun(run.id); }}>
              {loadingRunId === run.id ? "读取中" : "查看记录"}
            </Button>
          </article>
        ))}
        {agentRuns.length === 0 ? <p className="empty-copy">当前 Room 还没有 AgentRun。</p> : null}
      </div>

      {snapshot !== null ? (
        <div className="agent-run-result">
          <dl>
            <div><dt>状态</dt><dd>{snapshot.run.status}</dd></div>
            <div><dt>模型调用</dt><dd>{String(snapshot.calls.length)}</dd></div>
            <div><dt>总 Token</dt><dd>{String(snapshot.usage.reduce((total, item) => total + item.total_tokens, 0))}</dd></div>
            <div><dt>错误代码</dt><dd>{snapshot.run.error_code ?? "无"}</dd></div>
          </dl>
          <div className="agent-call-list">
            {snapshot.calls.map((call) => (
              <span key={call.id}>{call.role} · {call.phase} · {call.status}</span>
            ))}
          </div>
          {output !== null ? <pre className="agent-final-output">{output}</pre> : null}
        </div>
      ) : null}

      <p className="contract-note">正式运行严格要求三个不同且已启用的 Profile，并由后端自动推进 Task、ToolCall、ArtifactVersion、Quality Gate、Checkpoint 与 Handoff。讨论运行只产生模型对话。</p>
    </section>
  );
}
