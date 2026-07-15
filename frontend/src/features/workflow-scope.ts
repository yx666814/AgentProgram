import { type BackendApi, type Workflow, type WorkflowSnapshot } from "../api/backend-api";

const terminalWorkflowStates = new Set(["completed", "stopped", "abandoned"]);

export async function loadWorkflowScope(api: BackendApi, projectId: string) {
  const [project, list] = await Promise.all([api.getProject(projectId), api.listWorkflows(projectId)]);
  const ordered: Workflow[] = [...list.workflows].sort((left, right) =>
    right.updated_at.localeCompare(left.updated_at),
  );
  const selected = ordered.find(({ status }) => !terminalWorkflowStates.has(status)) ?? ordered[0];
  if (selected === undefined) {
    throw new Error("项目没有可读取的工作流");
  }
  const workflow: WorkflowSnapshot = await api.getWorkflow(selected.id);
  return { project, workflow };
}
