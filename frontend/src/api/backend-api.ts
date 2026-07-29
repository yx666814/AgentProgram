import type { DesktopPort } from "../../electron/desktop-port";
import type { components } from "./generated";
import { ApiClient } from "./client";
import { createDesktopTransport } from "./transport";

export type HealthResponse = Record<string, "ok">;
export type ReadinessResponse = Record<string, "ready">;
export type SystemInfo = Omit<components["schemas"]["SystemInfoResponse"], "protocol_version"> & {
  protocol_version: number;
};
export type RecoveryList = components["schemas"]["RecoveryListResponse"];
export type RecoveryRecord = components["schemas"]["RecoveryRecord"];
export type ProjectList = components["schemas"]["ProjectListResponse"];
export type ProjectRegistration = components["schemas"]["ProjectRegistration"];
export type ProjectCreateInput = Omit<
  components["schemas"]["ProjectCreateRequest"],
  "correlation_id"
>;
export type ProjectCreateResult = components["schemas"]["ProjectCreateResponse"];
export type Project = components["schemas"]["Project"];
export type PreflightResult = components["schemas"]["ProjectPreflightResult"];
export type PreflightExecution = components["schemas"]["PreflightResponse"];
export type Workflow = components["schemas"]["Workflow"];
export type WorkflowList = components["schemas"]["WorkflowListResponse"];
export type WorkflowSnapshot = components["schemas"]["WorkflowSnapshot"];
export type WorkflowAction = "pause" | "resume" | "stop" | "abandon";
export type ExecutionMode = components["schemas"]["ExecutionMode"];
export type Stage = components["schemas"]["Stage"];
export type StageRunState = components["schemas"]["StageRunState"];
export type StageTransitionResult = components["schemas"]["StageTransitionResponse"];
export type Message = components["schemas"]["Message"];
export type MessageList = components["schemas"]["MessageListResponse"];
export type MessageAppendResult = components["schemas"]["MessageAppendResponse"];
export type Task = components["schemas"]["WorkflowTask"];
export type TaskList = components["schemas"]["TaskListResponse"];
export type ToolCallList = components["schemas"]["ToolCallList"];
export type AgentRun = components["schemas"]["AgentRun"];
export type AgentRunList = components["schemas"]["AgentRunListResponse"];
export type AgentRunCreateResult = components["schemas"]["AgentRunCreateResponse"];
export type AgentRunSnapshot = components["schemas"]["AgentRunSnapshot"];
export type AgentRunCancelResult = components["schemas"]["AgentRunCancelResponse"];
export type AgentRunStatus = components["schemas"]["AgentRunStatus"];
export type ModelCallStatus = components["schemas"]["ModelCallStatus"];
export type ModelPhase = components["schemas"]["ModelPhase"];
export type ModelRole = components["schemas"]["ModelRole"];
export type RoomModelAssignment = components["schemas"]["RoomModelAssignment"];
export type ModelProfile = components["schemas"]["ModelProfile"];
export type ModelProfileList = components["schemas"]["ModelProfileListResponse"];
export type ModelProfileCreateInput = Omit<
  components["schemas"]["ModelProfileCreateRequest"],
  "correlation_id"
>;
export type ModelProfileUpdateInput = Omit<
  components["schemas"]["ModelProfileUpdateRequest"],
  "correlation_id" | "expected_version"
>;
export type ModelProvider = components["schemas"]["ModelProvider"];
export type EventReplay = components["schemas"]["EventReplayResponse"];
export type ArtifactInventory = components["schemas"]["ArtifactInventoryResponse"];
export type GateList = components["schemas"]["GateListResponse"];
export type ApprovalList = components["schemas"]["ApprovalListResponse"];
export type Approval = components["schemas"]["Approval"];
export type ApprovalDecision = components["schemas"]["ApprovalDecisionResponse"];
export type HandoffList = components["schemas"]["HandoffListResponse"];
export type ChangeRequestList = components["schemas"]["ChangeRequestListResponse"];
export type CapabilityRequestList = components["schemas"]["CapabilityRequestList"];
export type CapabilityRequest = components["schemas"]["CapabilityRequestRecord"];
export type ConflictList = components["schemas"]["ConflictListResponse"];
export type FileConflict = components["schemas"]["FileConflict"];
export type ConflictResolution = components["schemas"]["ConflictResolution"];
export type ConflictResolutionResult = components["schemas"]["ConflictResolveResponse"];
export type CheckpointList = components["schemas"]["CheckpointListResponse"];
export type ProjectCheckpoint = components["schemas"]["ProjectCheckpoint"];
export type RestorePlan = components["schemas"]["RestorePlanResponse"];
export type RestoreResult = components["schemas"]["CheckpointRestoreResponse"];
export type ExternalChangeList = components["schemas"]["ExternalChangeListResponse"];

export type AgentStreamFrameType =
  | "run_started"
  | "call_started"
  | "chunk"
  | "call_completed"
  | "run_completed"
  | "error";

export interface AgentStreamFrame {
  data: Record<string, unknown>;
  error_code: string | null;
  phase: ModelPhase | null;
  role: ModelRole | null;
  run_id: string;
  sequence: number;
  status: AgentRunStatus | ModelCallStatus | null;
  text: string | null;
  type: AgentStreamFrameType;
}

export type OrchestrationFrameType =
  | "started"
  | "stage_transitioned"
  | "task_started"
  | "agent_run_created"
  | "agent_frame"
  | "plan_validated"
  | "tool_completed"
  | "task_completed"
  | "artifact_created"
  | "gate_evaluated"
  | "approval_required"
  | "handoff_created"
  | "completed"
  | "error";

export interface OrchestrationFrame {
  agent_run_id: string | null;
  data: Record<string, unknown>;
  error_code: string | null;
  sequence: number;
  stage_run_id: string;
  task_id: string | null;
  text: string | null;
  type: OrchestrationFrameType;
  workflow_id: string;
}

const agentStreamFrameTypes = new Set<AgentStreamFrameType>([
  "run_started",
  "call_started",
  "chunk",
  "call_completed",
  "run_completed",
  "error",
]);
const modelRoles = new Set<ModelRole>(["primary", "reviewer_a", "reviewer_b"]);
const modelPhases = new Set<ModelPhase>(["p0", "p1", "p2r"]);
const streamStatuses = new Set<AgentRunStatus | ModelCallStatus>([
  "pending",
  "running",
  "succeeded",
  "partial_failure",
  "failed",
  "cancelled",
  "streaming",
]);

function parseAgentStreamFrame(value: unknown): AgentStreamFrame {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    throw new Error("AgentRun stream frame must be an object");
  }
  const frame = value as Record<string, unknown>;
  if (
    typeof frame.type !== "string" ||
    !agentStreamFrameTypes.has(frame.type as AgentStreamFrameType) ||
    typeof frame.run_id !== "string" ||
    !/^agentrun_[a-z0-9]+$/.test(frame.run_id) ||
    typeof frame.sequence !== "number" ||
    !Number.isSafeInteger(frame.sequence) ||
    frame.sequence < 1 ||
    typeof frame.data !== "object" ||
    frame.data === null ||
    Array.isArray(frame.data)
  ) {
    throw new Error("AgentRun stream frame violates the frozen backend contract");
  }
  const role = frame.role;
  const phase = frame.phase;
  const status = frame.status;
  const text = frame.text;
  const errorCode = frame.error_code;
  if (
    !(role === null || (typeof role === "string" && modelRoles.has(role as ModelRole))) ||
    !(phase === null || (typeof phase === "string" && modelPhases.has(phase as ModelPhase))) ||
    !(status === null || (typeof status === "string" && streamStatuses.has(status as AgentRunStatus | ModelCallStatus))) ||
    !(text === null || typeof text === "string") ||
    !(errorCode === null || typeof errorCode === "string")
  ) {
    throw new Error("AgentRun stream frame contains an invalid optional field");
  }
  return {
    data: frame.data as Record<string, unknown>,
    error_code: errorCode,
    phase: phase as ModelPhase | null,
    role: role as ModelRole | null,
    run_id: frame.run_id,
    sequence: frame.sequence,
    status: status as AgentRunStatus | ModelCallStatus | null,
    text,
    type: frame.type as AgentStreamFrameType,
  };
}

const orchestrationFrameTypes = new Set<OrchestrationFrameType>([
  "started",
  "stage_transitioned",
  "task_started",
  "agent_run_created",
  "agent_frame",
  "plan_validated",
  "tool_completed",
  "task_completed",
  "artifact_created",
  "gate_evaluated",
  "approval_required",
  "handoff_created",
  "completed",
  "error",
]);

function parseOrchestrationFrame(value: unknown): OrchestrationFrame {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    throw new Error("Orchestration stream frame must be an object");
  }
  const frame = value as Record<string, unknown>;
  if (
    typeof frame.type !== "string" ||
    !orchestrationFrameTypes.has(frame.type as OrchestrationFrameType) ||
    typeof frame.workflow_id !== "string" ||
    !/^workflow_[a-z0-9]+$/.test(frame.workflow_id) ||
    typeof frame.stage_run_id !== "string" ||
    !/^stagerun_[a-z0-9]+$/.test(frame.stage_run_id) ||
    typeof frame.sequence !== "number" ||
    !Number.isSafeInteger(frame.sequence) ||
    frame.sequence < 1 ||
    typeof frame.data !== "object" ||
    frame.data === null ||
    Array.isArray(frame.data)
  ) {
    throw new Error("Orchestration stream frame violates the backend contract");
  }
  const agentRunId = frame.agent_run_id;
  const taskId = frame.task_id;
  const text = frame.text;
  const errorCode = frame.error_code;
  if (
    !(agentRunId === null || (typeof agentRunId === "string" && /^agentrun_[a-z0-9]+$/.test(agentRunId))) ||
    !(taskId === null || (typeof taskId === "string" && /^task_[a-z0-9]+$/.test(taskId))) ||
    !(text === null || typeof text === "string") ||
    !(errorCode === null || typeof errorCode === "string")
  ) {
    throw new Error("Orchestration stream frame contains an invalid optional field");
  }
  return {
    agent_run_id: agentRunId,
    data: frame.data as Record<string, unknown>,
    error_code: errorCode,
    sequence: frame.sequence,
    stage_run_id: frame.stage_run_id,
    task_id: taskId,
    text,
    type: frame.type as OrchestrationFrameType,
    workflow_id: frame.workflow_id,
  };
}

export interface CommandReceipt<T> {
  correlationId: string;
  payload: T;
}

export type CorrelationIdFactory = () => string;

function defaultCorrelationIdFactory(): string {
  return crypto.randomUUID();
}

export class BackendApi {
  private readonly client: ApiClient;

  constructor(
    port: DesktopPort,
    private readonly correlationIdFactory: CorrelationIdFactory = defaultCorrelationIdFactory,
  ) {
    this.client = new ApiClient(createDesktopTransport(port));
  }

  async health(): Promise<HealthResponse> {
    return (await this.client.query<HealthResponse>("health_api_v1_health_get")).payload;
  }

  async readiness(): Promise<ReadinessResponse> {
    return (await this.client.query<ReadinessResponse>("readiness_api_v1_readiness_get")).payload;
  }

  async systemInfo(): Promise<SystemInfo> {
    return (await this.client.query<SystemInfo>("system_info_api_v1_system_info_get")).payload;
  }

  async listRecoveries(): Promise<RecoveryList> {
    return (await this.client.query<RecoveryList>("list_recoveries_api_v1_recovery_get")).payload;
  }

  async resolveRecovery(recoveryId: string, action: "resume" | "discard"): Promise<RecoveryRecord> {
    return (
      await this.client.command<RecoveryRecord>(
        "resolve_recovery_api_v1_recovery__recovery_id___action__post",
        {
          parameters: { path: { recovery_id: recoveryId, action } },
          payload: { correlation_id: this.correlationIdFactory() },
        },
      )
    ).payload;
  }

  async listProjects(): Promise<ProjectList> {
    return (await this.client.query<ProjectList>("list_projects_api_v1_projects_get")).payload;
  }

  async createProject(input: ProjectCreateInput): Promise<ProjectCreateResult> {
    return (
      await this.client.command<ProjectCreateResult>("create_project_api_v1_projects_post", {
        payload: { ...input, correlation_id: this.correlationIdFactory() },
      })
    ).payload;
  }

  async getProject(projectId: string): Promise<ProjectRegistration> {
    return (
      await this.client.query<ProjectRegistration>("get_project_api_v1_projects__project_id__get", {
        parameters: { path: { project_id: projectId } },
      })
    ).payload;
  }

  async openProject(projectId: string, expectedVersion: number): Promise<ProjectRegistration> {
    return (
      await this.client.command<ProjectRegistration>(
        "open_project_api_v1_projects__project_id__open_post",
        {
          parameters: { path: { project_id: projectId } },
          payload: {
            expected_version: expectedVersion,
            correlation_id: this.correlationIdFactory(),
          },
        },
      )
    ).payload;
  }

  async closeProject(projectId: string, expectedVersion: number): Promise<Project> {
    const response = await this.client.command<{ project: Project }>(
      "close_project_api_v1_projects__project_id__close_post",
      {
        parameters: { path: { project_id: projectId } },
        payload: {
          expected_version: expectedVersion,
          correlation_id: this.correlationIdFactory(),
        },
      },
    );
    return response.payload.project;
  }

  async getPreflight(projectId: string): Promise<PreflightResult> {
    return (
      await this.client.query<PreflightResult>(
        "get_preflight_api_v1_projects__project_id__preflight_get",
        { parameters: { path: { project_id: projectId } } },
      )
    ).payload;
  }

  async runPreflight(projectId: string, expectedVersion: number): Promise<PreflightExecution> {
    return (
      await this.client.command<PreflightExecution>(
        "run_preflight_api_v1_projects__project_id__preflight_post",
        {
          parameters: { path: { project_id: projectId } },
          payload: {
            expected_version: expectedVersion,
            correlation_id: this.correlationIdFactory(),
          },
        },
      )
    ).payload;
  }

  async listWorkflows(projectId: string): Promise<WorkflowList> {
    return (
      await this.client.query<WorkflowList>(
        "list_workflows_api_v1_projects__project_id__workflows_get",
        { parameters: { path: { project_id: projectId } } },
      )
    ).payload;
  }

  async createWorkflow(projectId: string, title: string): Promise<WorkflowSnapshot> {
    return (
      await this.client.command<WorkflowSnapshot>(
        "create_workflow_api_v1_projects__project_id__workflows_post",
        {
          parameters: { path: { project_id: projectId } },
          payload: { title, correlation_id: this.correlationIdFactory() },
        },
      )
    ).payload;
  }

  async getWorkflow(workflowId: string): Promise<WorkflowSnapshot> {
    return (
      await this.client.query<WorkflowSnapshot>(
        "get_workflow_api_v1_workflows__workflow_id__get",
        { parameters: { path: { workflow_id: workflowId } } },
      )
    ).payload;
  }

  async startWorkflow(workflowId: string, expectedVersion: number): Promise<WorkflowSnapshot> {
    return (
      await this.client.command<WorkflowSnapshot>(
        "start_workflow_api_v1_workflows__workflow_id__start_post",
        {
          parameters: { path: { workflow_id: workflowId } },
          payload: {
            expected_version: expectedVersion,
            correlation_id: this.correlationIdFactory(),
          },
        },
      )
    ).payload;
  }

  async controlWorkflow(
    workflowId: string,
    action: WorkflowAction,
    expectedVersion: number,
  ): Promise<Workflow> {
    return (
      await this.client.command<Workflow>(
        "control_workflow_api_v1_workflows__workflow_id___action__post",
        {
          parameters: { path: { workflow_id: workflowId, action } },
          payload: {
            expected_version: expectedVersion,
            correlation_id: this.correlationIdFactory(),
          },
        },
      )
    ).payload;
  }

  async setWorkflowMode(
    workflowId: string,
    mode: ExecutionMode,
    expectedVersion: number,
  ): Promise<Workflow> {
    return (
      await this.client.command<Workflow>(
        "set_workflow_mode_api_v1_workflows__workflow_id__mode_post",
        {
          parameters: { path: { workflow_id: workflowId } },
          payload: {
            mode,
            expected_version: expectedVersion,
            correlation_id: this.correlationIdFactory(),
          },
        },
      )
    ).payload;
  }

  async listMessages(roomId: string): Promise<MessageList> {
    return (
      await this.client.query<MessageList>("list_messages_api_v1_rooms__room_id__messages_get", {
        parameters: { path: { room_id: roomId }, query: { after_sequence: 0, limit: 100 } },
      })
    ).payload;
  }

  async appendMessage(
    roomId: string,
    content: string,
    expectedRoomVersion: number,
    correctionOfId: string | null = null,
  ): Promise<MessageAppendResult> {
    return (
      await this.client.command<MessageAppendResult>(
        "append_message_api_v1_rooms__room_id__messages_post",
        {
          parameters: { path: { room_id: roomId } },
          payload: {
            content,
            correction_of_id: correctionOfId,
            expected_room_version: expectedRoomVersion,
            correlation_id: this.correlationIdFactory(),
          },
        },
      )
    ).payload;
  }

  async listTasks(workflowId: string): Promise<TaskList> {
    return (
      await this.client.query<TaskList>("list_tasks_api_v1_workflows__workflow_id__tasks_get", {
        parameters: { path: { workflow_id: workflowId }, query: {} },
      })
    ).payload;
  }

  async enqueueTask(roomId: string, title: string): Promise<Task> {
    return (
      await this.client.command<Task>("enqueue_task_api_v1_rooms__room_id__tasks_post", {
        parameters: { path: { room_id: roomId } },
        payload: { title, payload: {}, correlation_id: this.correlationIdFactory() },
      })
    ).payload;
  }

  async startTask(taskId: string, expectedVersion: number): Promise<Task> {
    return (
      await this.client.command<Task>("start_task_api_v1_tasks__task_id__start_post", {
        parameters: { path: { task_id: taskId } },
        payload: {
          expected_version: expectedVersion,
          correlation_id: this.correlationIdFactory(),
        },
      })
    ).payload;
  }

  async cancelTask(taskId: string, expectedVersion: number): Promise<Task> {
    return (
      await this.client.command<Task>("cancel_task_api_v1_tasks__task_id__cancel_post", {
        parameters: { path: { task_id: taskId } },
        payload: {
          expected_version: expectedVersion,
          correlation_id: this.correlationIdFactory(),
        },
      })
    ).payload;
  }

  async listToolCalls(workflowId: string): Promise<ToolCallList> {
    return (
      await this.client.query<ToolCallList>(
        "list_tool_calls_api_v1_workflows__workflow_id__tool_calls_get",
        { parameters: { path: { workflow_id: workflowId } } },
      )
    ).payload;
  }

  async listAgentRuns(roomId: string): Promise<AgentRunList> {
    return (
      await this.client.query<AgentRunList>("list_agent_runs_api_v1_rooms__room_id__agent_runs_get", {
        parameters: { path: { room_id: roomId } },
      })
    ).payload;
  }

  async createAgentRun(roomId: string, formal: boolean): Promise<AgentRunCreateResult> {
    const correlationId = this.correlationIdFactory();
    return (
      await this.client.command<AgentRunCreateResult>(
        "create_agent_run_api_v1_rooms__room_id__agent_runs_post",
        {
          correlationId,
          parameters: { path: { room_id: roomId } },
          payload: {
            request_key: `agent-run:${crypto.randomUUID()}`,
            formal,
            correlation_id: correlationId,
          },
        },
      )
    ).payload;
  }

  async streamAgentRun(
    runId: string,
    instruction: string,
    listener: (frame: AgentStreamFrame) => void,
  ): Promise<void> {
    const correlationId = this.correlationIdFactory();
    await this.client.stream(
      "stream_agent_run_api_v1_agent_runs__run_id__stream_post",
      {
        correlationId,
        parameters: { path: { run_id: runId } },
        payload: { instruction, correlation_id: correlationId },
      },
      (frame) => { listener(parseAgentStreamFrame(frame)); },
    );
  }

  async streamOrchestration(
    workflowId: string,
    instruction: string,
    requestKey: string,
    listener: (frame: OrchestrationFrame) => void,
  ): Promise<void> {
    const correlationId = this.correlationIdFactory();
    await this.client.stream(
      "orchestrate_workflow_stage_api_v1_workflows__workflow_id__orchestration_stream_post",
      {
        parameters: { path: { workflow_id: workflowId } },
        payload: {
          request_key: requestKey,
          instruction,
          correlation_id: correlationId,
        },
      },
      (frame) => { listener(parseOrchestrationFrame(frame)); },
    );
  }

  async cancelAgentRun(runId: string): Promise<AgentRunCancelResult> {
    return (
      await this.client.command<AgentRunCancelResult>(
        "cancel_agent_run_api_v1_agent_runs__run_id__cancel_post",
        { parameters: { path: { run_id: runId } } },
      )
    ).payload;
  }

  async getAgentRun(runId: string): Promise<AgentRunSnapshot> {
    return (
      await this.client.query<AgentRunSnapshot>(
        "get_agent_run_api_v1_agent_runs__run_id__get",
        { parameters: { path: { run_id: runId } } },
      )
    ).payload;
  }

  async getAgentRunOutput(runId: string): Promise<string> {
    return (
      await this.client.query<string>(
        "get_agent_run_output_api_v1_agent_runs__run_id__output_get",
        { parameters: { path: { run_id: runId } } },
      )
    ).payload;
  }

  async getRoomAssignment(roomId: string): Promise<RoomModelAssignment> {
    return (
      await this.client.query<RoomModelAssignment>(
        "get_room_assignment_api_v1_rooms__room_id__model_assignment_get",
        { parameters: { path: { room_id: roomId } } },
      )
    ).payload;
  }

  async listModelProfiles(): Promise<ModelProfileList> {
    return (
      await this.client.query<ModelProfileList>("list_profiles_api_v1_model_profiles_get")
    ).payload;
  }

  async createModelProfile(
    input: ModelProfileCreateInput,
  ): Promise<CommandReceipt<ModelProfile>> {
    const correlationId = this.correlationIdFactory();
    const response = await this.client.command<ModelProfile>(
      "create_profile_api_v1_model_profiles_post",
      {
        correlationId,
        payload: { ...input, correlation_id: correlationId },
      },
    );
    return { correlationId, payload: response.payload };
  }

  async updateModelProfile(
    profile: ModelProfile,
    input: ModelProfileUpdateInput,
  ): Promise<CommandReceipt<ModelProfile>> {
    const correlationId = this.correlationIdFactory();
    const response = await this.client.command<ModelProfile>(
      "update_profile_api_v1_model_profiles__profile_id__put",
      {
        correlationId,
        parameters: { path: { profile_id: profile.id } },
        payload: {
          ...input,
          expected_version: profile.version,
          correlation_id: correlationId,
        },
      },
    );
    return { correlationId, payload: response.payload };
  }

  async assignRoomModels(input: {
    assignment: RoomModelAssignment | null;
    primaryProfileId: string;
    reviewerAProfileId: string | null;
    reviewerBProfileId: string | null;
    roomId: string;
  }): Promise<CommandReceipt<RoomModelAssignment>> {
    const correlationId = this.correlationIdFactory();
    const response = await this.client.command<RoomModelAssignment>(
      "assign_room_models_api_v1_rooms__room_id__model_assignment_put",
      {
        correlationId,
        parameters: { path: { room_id: input.roomId } },
        payload: {
          primary_profile_id: input.primaryProfileId,
          reviewer_a_profile_id: input.reviewerAProfileId,
          reviewer_b_profile_id: input.reviewerBProfileId,
          expected_version: input.assignment?.version ?? null,
          correlation_id: correlationId,
        },
      },
    );
    return { correlationId, payload: response.payload };
  }

  async replayWorkflowEvents(workflowId: string, afterEventId: number): Promise<EventReplay> {
    return (
      await this.client.query<EventReplay>("replay_events_api_v1_events_replay_get", {
        parameters: { query: { workflow_id: workflowId, after_event_id: afterEventId } },
      })
    ).payload;
  }

  async transitionStage(
    workflowId: string,
    stage: Stage,
    targetState: StageRunState,
    expectedWorkflowVersion: number,
    expectedStageVersion: number,
  ): Promise<StageTransitionResult> {
    return (
      await this.client.command<StageTransitionResult>(
        "transition_stage_api_v1_workflows__workflow_id__stages__stage__transition_post",
        {
          parameters: { path: { workflow_id: workflowId, stage } },
          payload: {
            target_state: targetState,
            expected_workflow_version: expectedWorkflowVersion,
            expected_stage_version: expectedStageVersion,
            correlation_id: this.correlationIdFactory(),
          },
        },
      )
    ).payload;
  }

  async reopenStage(
    workflowId: string,
    stage: Stage,
    expectedWorkflowVersion: number,
  ): Promise<WorkflowSnapshot> {
    return (
      await this.client.command<WorkflowSnapshot>(
        "reopen_stage_api_v1_workflows__workflow_id__stages__stage__reopen_post",
        {
          parameters: { path: { workflow_id: workflowId, stage } },
          payload: {
            expected_version: expectedWorkflowVersion,
            correlation_id: this.correlationIdFactory(),
          },
        },
      )
    ).payload;
  }

  async listArtifacts(workflowId: string): Promise<ArtifactInventory> {
    return (
      await this.client.query<ArtifactInventory>(
        "list_artifacts_api_v1_workflows__workflow_id__artifacts_get",
        { parameters: { path: { workflow_id: workflowId } } },
      )
    ).payload;
  }

  async listQualityGates(workflowId: string): Promise<GateList> {
    return (
      await this.client.query<GateList>(
        "list_quality_gates_api_v1_workflows__workflow_id__quality_gates_get",
        { parameters: { path: { workflow_id: workflowId } } },
      )
    ).payload;
  }

  async listApprovals(workflowId: string): Promise<ApprovalList> {
    return (
      await this.client.query<ApprovalList>(
        "list_approvals_api_v1_workflows__workflow_id__approvals_get",
        { parameters: { path: { workflow_id: workflowId }, query: {} } },
      )
    ).payload;
  }

  async decideApproval(
    approval: Approval,
    approved: boolean,
    reason: string | null,
  ): Promise<ApprovalDecision> {
    return (
      await this.client.command<ApprovalDecision>(
        "decide_gate_approval_api_v1_approvals__approval_id__decision_post",
        {
          parameters: { path: { approval_id: approval.id } },
          payload: {
            approved,
            expected_version: approval.version,
            reason,
            correlation_id: this.correlationIdFactory(),
          },
        },
      )
    ).payload;
  }

  async listHandoffs(workflowId: string): Promise<HandoffList> {
    return (
      await this.client.query<HandoffList>(
        "list_handoffs_api_v1_workflows__workflow_id__handoffs_get",
        { parameters: { path: { workflow_id: workflowId } } },
      )
    ).payload;
  }

  async listChangeRequests(workflowId: string): Promise<ChangeRequestList> {
    return (
      await this.client.query<ChangeRequestList>(
        "list_change_requests_api_v1_workflows__workflow_id__change_requests_get",
        { parameters: { path: { workflow_id: workflowId } } },
      )
    ).payload;
  }

  async listCapabilityRequests(workflowId: string): Promise<CapabilityRequestList> {
    return (
      await this.client.query<CapabilityRequestList>(
        "list_capability_requests_api_v1_workflows__workflow_id__capability_requests_get",
        { parameters: { path: { workflow_id: workflowId }, query: {} } },
      )
    ).payload;
  }

  async decideCapability(
    request: CapabilityRequest,
    approved: boolean,
    reason: string | null,
  ): Promise<CapabilityRequest> {
    return (
      await this.client.command<CapabilityRequest>(
        "decide_capability_api_v1_capability_requests__request_id__decision_post",
        {
          parameters: { path: { request_id: request.id } },
          payload: {
            approved,
            expected_version: request.version,
            reason,
            correlation_id: this.correlationIdFactory(),
          },
        },
      )
    ).payload;
  }

  async listConflicts(projectId: string): Promise<ConflictList> {
    return (
      await this.client.query<ConflictList>(
        "list_conflicts_api_v1_projects__project_id__conflicts_get",
        { parameters: { path: { project_id: projectId } } },
      )
    ).payload;
  }

  async resolveConflict(input: {
    agentCheckpointId: string | null;
    conflict: FileConflict;
    expectedProjectVersion: number;
    mergedContentHash: string | null;
    resolution: ConflictResolution;
  }): Promise<ConflictResolutionResult> {
    return (
      await this.client.command<ConflictResolutionResult>(
        "resolve_conflict_api_v1_projects__project_id__conflicts__conflict_id__resolve_post",
        {
          parameters: {
            path: { project_id: input.conflict.project_id, conflict_id: input.conflict.id },
          },
          payload: {
            resolution: input.resolution,
            expected_conflict_version: input.conflict.version,
            expected_project_version: input.expectedProjectVersion,
            agent_checkpoint_id: input.agentCheckpointId,
            merged_content_hash: input.mergedContentHash,
            correlation_id: this.correlationIdFactory(),
          },
        },
      )
    ).payload;
  }

  async listCheckpoints(projectId: string): Promise<CheckpointList> {
    return (
      await this.client.query<CheckpointList>(
        "list_checkpoints_api_v1_projects__project_id__checkpoints_get",
        { parameters: { path: { project_id: projectId } } },
      )
    ).payload;
  }

  async planRestore(projectId: string, checkpointId: string): Promise<RestorePlan> {
    return (
      await this.client.command<RestorePlan>(
        "plan_restore_api_v1_projects__project_id__checkpoints__checkpoint_id__restore_plan_post",
        {
          parameters: { path: { project_id: projectId, checkpoint_id: checkpointId } },
          payload: { correlation_id: this.correlationIdFactory() },
        },
      )
    ).payload;
  }

  async restoreCheckpoint(
    projectId: string,
    checkpointId: string,
    protectionCheckpointId: string,
    expectedProjectVersion: number,
  ): Promise<RestoreResult> {
    return (
      await this.client.command<RestoreResult>(
        "restore_checkpoint_api_v1_projects__project_id__checkpoints__checkpoint_id__restore_post",
        {
          parameters: { path: { project_id: projectId, checkpoint_id: checkpointId } },
          payload: {
            protection_checkpoint_id: protectionCheckpointId,
            expected_project_version: expectedProjectVersion,
            correlation_id: this.correlationIdFactory(),
          },
        },
      )
    ).payload;
  }

  async listExternalChanges(projectId: string): Promise<ExternalChangeList> {
    return (
      await this.client.query<ExternalChangeList>(
        "list_external_changes_api_v1_projects__project_id__external_changes_get",
        { parameters: { path: { project_id: projectId } } },
      )
    ).payload;
  }
}
