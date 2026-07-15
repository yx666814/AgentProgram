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
}
