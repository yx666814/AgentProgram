import {
  expect,
  test,
  type ElectronApplication,
  type Page,
  type TestInfo,
  _electron as electron,
} from "@playwright/test";
import { spawn } from "node:child_process";
import { createHash } from "node:crypto";
import {
  access,
  mkdir,
  mkdtemp,
  readFile,
  rm,
  writeFile,
} from "node:fs/promises";
import { tmpdir } from "node:os";
import { dirname, join, resolve, sep } from "node:path";
import { fileURLToPath } from "node:url";

import type {
  BackendOperationId,
  BackendReply,
} from "../../electron/desktop-port";

type JsonObject = Record<string, unknown>;
type Stage = "planner" | "designer" | "builder" | "reviewer" | "deployer";

const STAGES: readonly Stage[] = ["planner", "designer", "builder", "reviewer", "deployer"];
const STAGE_LABELS: Record<Stage, string> = {
  planner: "Planner",
  designer: "Designer",
  builder: "Builder",
  reviewer: "Reviewer",
  deployer: "Deployer",
};

function record(value: unknown, label: string): JsonObject {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    throw new Error(`${label} is not an object`);
  }
  return value as JsonObject;
}

function records(value: unknown, label: string): JsonObject[] {
  if (!Array.isArray(value)) {
    throw new Error(`${label} is not an array`);
  }
  return value.map((item, index) => record(item, `${label}[${String(index)}]`));
}

function text(value: unknown, label: string): string {
  if (typeof value !== "string") {
    throw new Error(`${label} is not a string`);
  }
  return value;
}

function integer(value: unknown, label: string): number {
  if (!Number.isInteger(value)) {
    throw new Error(`${label} is not an integer`);
  }
  return value as number;
}

function sha256(value: string): string {
  return createHash("sha256").update(value).digest("hex");
}

function correlation(name: string): string {
  return `stage9_${name}`.slice(0, 120);
}

async function exists(path: string): Promise<boolean> {
  try {
    await access(path);
    return true;
  } catch {
    return false;
  }
}

async function runProcess(
  executable: string,
  args: readonly string[],
  options: { cwd?: string; timeoutMs?: number } = {},
): Promise<{ stdout: string; stderr: string }> {
  return new Promise((resolveRun, rejectRun) => {
    const child = spawn(executable, args, {
      cwd: options.cwd,
      windowsHide: true,
      stdio: ["ignore", "pipe", "pipe"],
    });
    let stdout = "";
    let stderr = "";
    child.stdout.setEncoding("utf8");
    child.stderr.setEncoding("utf8");
    child.stdout.on("data", (chunk: string) => {
      stdout += chunk;
    });
    child.stderr.on("data", (chunk: string) => {
      stderr += chunk;
    });
    const timeout = setTimeout(() => {
      child.kill();
      rejectRun(new Error(`Process timed out: ${executable}`));
    }, options.timeoutMs ?? 180_000);
    child.once("error", (error) => {
      clearTimeout(timeout);
      rejectRun(error);
    });
    child.once("exit", (code) => {
      clearTimeout(timeout);
      if (code !== 0) {
        rejectRun(
          new Error(
            `Process failed (${String(code)}): ${executable}\n${stdout}\n${stderr}`,
          ),
        );
        return;
      }
      resolveRun({ stdout, stderr });
    });
  });
}

async function waitUntil(
  predicate: () => boolean | Promise<boolean>,
  timeoutMs: number,
  message: string,
): Promise<void> {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (await predicate()) {
      return;
    }
    await new Promise((resolveWait) => setTimeout(resolveWait, 250));
  }
  throw new Error(message);
}

class DesktopDriver {
  private requestSequence = 0;

  constructor(readonly page: Page) {}

  async request(
    kind: "query" | "command",
    operationId: BackendOperationId,
    parameters?: unknown,
    payload?: unknown,
    expectedStatus: number | readonly number[] = [200, 201],
  ): Promise<unknown> {
    this.requestSequence += 1;
    const reply = await this.page.evaluate(
      async (input): Promise<BackendReply> => {
        const desktop = window.desktop;
        const request = {
          operationId: input.operationId,
          requestId: input.requestId,
          ...(input.parameters === undefined ? {} : { parameters: input.parameters }),
          ...(input.payload === undefined ? {} : { payload: input.payload }),
        };
        return input.kind === "query"
          ? desktop.backend.query(request)
          : desktop.backend.command(request);
      },
      {
        kind,
        operationId,
        requestId: `stage9-${String(this.requestSequence)}`,
        parameters,
        payload,
      },
    );
    const accepted = Array.isArray(expectedStatus) ? expectedStatus : [expectedStatus];
    if (!accepted.includes(reply.statusCode)) {
      throw new Error(
        `${operationId} returned ${String(reply.statusCode)}: ${JSON.stringify(reply.payload)}`,
      );
    }
    return reply.payload;
  }

  query(operationId: BackendOperationId, parameters?: unknown): Promise<unknown> {
    return this.request("query", operationId, parameters);
  }

  command(
    operationId: BackendOperationId,
    parameters?: unknown,
    payload?: unknown,
    expectedStatus?: number | readonly number[],
  ): Promise<unknown> {
    return this.request("command", operationId, parameters, payload, expectedStatus);
  }

  async stream(
    operationId: BackendOperationId,
    parameters?: unknown,
    payload?: unknown,
    expectedStatus: number | readonly number[] = 200,
  ): Promise<unknown[]> {
    this.requestSequence += 1;
    const result = await this.page.evaluate(
      async (input) => {
        const request = {
          operationId: input.operationId,
          requestId: input.requestId,
          ...(input.parameters === undefined ? {} : { parameters: input.parameters }),
          ...(input.payload === undefined ? {} : { payload: input.payload }),
        };
        const frames: unknown[] = [];
        const reply = await window.desktop.backend.stream(request, (frame) => {
          frames.push(frame);
        });
        return { frames, reply };
      },
      {
        operationId,
        requestId: `stage9-stream-${String(this.requestSequence)}`,
        parameters,
        payload,
      },
    );
    const accepted = Array.isArray(expectedStatus) ? expectedStatus : [expectedStatus];
    if (!accepted.includes(result.reply.statusCode)) {
      throw new Error(
        `${operationId} returned ${String(result.reply.statusCode)}: ${JSON.stringify(result.reply.payload)}`,
      );
    }
    return result.frames;
  }

  async storeSecret(value: string, label: string): Promise<JsonObject> {
    return record(
      await this.page.evaluate(
        async (input) => {
          const desktop = window.desktop;
          return desktop.secrets.store(input);
        },
        { value, label },
      ),
      "stored secret reference",
    );
  }

  async snapshot(workflowId: string): Promise<JsonObject> {
    return record(
      await this.query("get_workflow_api_v1_workflows__workflow_id__get", {
        path: { workflow_id: workflowId },
      }),
      "workflow snapshot",
    );
  }

  async transition(workflowId: string, stage: Stage, targetState: string): Promise<JsonObject> {
    const snapshot = await this.snapshot(workflowId);
    const workflow = record(snapshot.workflow, "workflow");
    const stageRun = records(snapshot.stage_runs, "stage runs").find(
      (candidate) => candidate.stage === stage && candidate.state !== "completed",
    );
    if (stageRun === undefined) {
      throw new Error(`Active ${stage} stage run was not found`);
    }
    return record(
      await this.command(
        "transition_stage_api_v1_workflows__workflow_id__stages__stage__transition_post",
        { path: { workflow_id: workflowId, stage } },
        {
          target_state: targetState,
          expected_workflow_version: integer(workflow.version, "workflow version"),
          expected_stage_version: integer(stageRun.version, "stage version"),
          correlation_id: correlation(`${stage}_${targetState}_${String(Date.now())}`),
        },
      ),
      "stage transition",
    );
  }

  async setMode(workflowId: string, mode: "manual" | "autonomous"): Promise<void> {
    const snapshot = await this.snapshot(workflowId);
    const workflow = record(snapshot.workflow, "workflow");
    await this.command(
      "set_workflow_mode_api_v1_workflows__workflow_id__mode_post",
      { path: { workflow_id: workflowId } },
      {
        mode,
        expected_version: integer(workflow.version, "workflow version"),
        correlation_id: correlation(`mode_${mode}`),
      },
    );
  }

  async control(workflowId: string, action: "pause" | "resume" | "stop"): Promise<void> {
    const snapshot = await this.snapshot(workflowId);
    const workflow = record(snapshot.workflow, "workflow");
    await this.command(
      "control_workflow_api_v1_workflows__workflow_id___action__post",
      { path: { workflow_id: workflowId, action } },
      {
        expected_version: integer(workflow.version, "workflow version"),
        correlation_id: correlation(`control_${action}_${workflowId}`),
      },
    );
  }

  async navigate(path: string): Promise<void> {
    await this.page.evaluate((target) => {
      window.location.hash = target;
    }, `#${path}`);
    await this.page.waitForLoadState("domcontentloaded");
  }
}

async function launchInstalled(
  executablePath: string,
  dataRoot: string,
  workspaces: readonly string[],
): Promise<{ app: ElectronApplication; driver: DesktopDriver }> {
  const app = await electron.launch({
    executablePath,
    args: [
      "--stage9-product-e2e",
      `--stage9-e2e-data-root=${dataRoot}`,
      ...workspaces.map((path) => `--stage9-e2e-workspace=${path}`),
    ],
    timeout: 60_000,
  });
  let desktopStderr = "";
  const stderr = app.process().stderr;
  stderr?.setEncoding("utf8");
  stderr?.on("data", (chunk: string) => {
    desktopStderr = (desktopStderr + chunk).slice(-32_768);
  });
  const page = await app.firstWindow();
  await page.waitForLoadState("domcontentloaded");
  await expect(page.getByRole("heading", { name: "启动星协" })).toBeVisible();
  const enterProjects = page.getByRole("button", { name: "进入项目" });
  let latestStatus = "系统状态尚未呈现";
  for (let attempt = 0; attempt < 6; attempt += 1) {
    await expect(page.getByText("数据库就绪", { exact: true })).toBeVisible({
      timeout: 45_000,
    });
    latestStatus = await page.locator(".status-list").innerText();
    if (await enterProjects.isEnabled()) {
      return { app, driver: new DesktopDriver(page) };
    }
    if (attempt < 5) {
      await page.getByRole("button", { name: "重新检查" }).click();
      await page.waitForTimeout(1_000);
      await expect(page.getByRole("heading", { name: "启动星协" })).toBeVisible({
        timeout: 45_000,
      });
    }
  }
  throw new Error(
    `Installed desktop did not become ready:\n${latestStatus}\nElectron stderr:\n${desktopStderr || "—"}`,
  );
}

async function relaunchAfterCrash(
  executablePath: string,
  dataRoot: string,
  workspaces: readonly string[],
): Promise<{ app: ElectronApplication; driver: DesktopDriver }> {
  let lastError: unknown = null;
  for (let attempt = 0; attempt < 10; attempt += 1) {
    try {
      return await launchInstalled(executablePath, dataRoot, workspaces);
    } catch (error) {
      lastError = error;
      await new Promise((resolveWait) => setTimeout(resolveWait, 1_000));
    }
  }
  throw lastError instanceof Error
    ? lastError
    : new Error("Installed desktop did not restart after the crash");
}

async function createProject(
  driver: DesktopDriver,
  input: { name: string; goal: string; path: string; mode: "managed" | "direct" },
): Promise<JsonObject> {
  return record(
    await driver.command(
      "create_project_api_v1_projects_post",
      undefined,
      {
        name: input.name,
        goal: input.goal,
        local_working_directory: input.path,
        workspace_mode: input.mode,
        correlation_id: correlation(`create_${input.mode}_${input.name}`),
      },
      201,
    ),
    `${input.mode} project creation`,
  );
}

async function getProject(driver: DesktopDriver, projectId: string): Promise<JsonObject> {
  return record(
    await driver.query("get_project_api_v1_projects__project_id__get", {
      path: { project_id: projectId },
    }),
    "project registration",
  );
}

async function preflight(driver: DesktopDriver, projectId: string): Promise<JsonObject> {
  const registration = await getProject(driver, projectId);
  const project = record(registration.project, "project");
  return record(
    await driver.command(
      "run_preflight_api_v1_projects__project_id__preflight_post",
      { path: { project_id: projectId } },
      {
        expected_version: integer(project.version, "project version"),
        correlation_id: correlation(`preflight_${projectId}`),
      },
    ),
    "preflight response",
  );
}

async function createWorkflow(
  driver: DesktopDriver,
  projectId: string,
  title: string,
): Promise<JsonObject> {
  const created = record(
    await driver.command(
      "create_workflow_api_v1_projects__project_id__workflows_post",
      { path: { project_id: projectId } },
      { title, correlation_id: correlation(`workflow_${projectId}`) },
      201,
    ),
    "workflow creation",
  );
  const workflow = record(created.workflow, "workflow");
  return record(
    await driver.command(
      "start_workflow_api_v1_workflows__workflow_id__start_post",
      { path: { workflow_id: workflow.id } },
      {
        expected_version: integer(workflow.version, "workflow version"),
        correlation_id: correlation(`start_${text(workflow.id, "workflow id")}`),
      },
    ),
    "started workflow",
  );
}

async function writeWithTool(
  driver: DesktopDriver,
  taskId: string,
  toolName: string,
  path: string,
  content: string,
  expectedHash: string | null = null,
): Promise<string> {
  const execution = record(
    await driver.command(
      "execute_tool_api_v1_tasks__task_id__tool_calls_post",
      { path: { task_id: taskId } },
      {
        tool_name: toolName,
        idempotency_key: `stage9-${toolName}-${taskId}-${sha256(content).slice(0, 16)}`,
        arguments: { path, content, expected_hash: expectedHash },
        timeout_seconds: 30,
        correlation_id: correlation(`tool_${toolName}_${taskId}`),
      },
    ),
    "tool execution",
  );
  const call = record(execution.call, "tool call");
  expect(call.status).toBe("succeeded");
  return text(record(execution.output, "tool output").content_hash, "tool content hash");
}

async function completeStage(
  driver: DesktopDriver,
  workflowId: string,
  stage: Stage,
  options: {
    expectedGate: "pass" | "warning";
    expectedResolution: "automatic" | "pending" | "rewrite_required";
    artifactExpectedHash?: string | null;
    capabilityApproval?: boolean;
  },
): Promise<{ artifactHash: string; gate: JsonObject }> {
  await driver.transition(workflowId, stage, "discussing");
  const snapshot = await driver.snapshot(workflowId);
  const stageRun = records(snapshot.stage_runs, "stage runs").find(
    (candidate) => candidate.stage === stage && candidate.state === "discussing",
  );
  if (stageRun === undefined) {
    throw new Error(`Discussing ${stage} stage was not found`);
  }
  const room = records(snapshot.rooms, "rooms").find(
    (candidate) => candidate.stage_run_id === stageRun.id,
  );
  if (room === undefined) {
    throw new Error(`${stage} room was not found`);
  }
  const task = record(
    await driver.command(
      "enqueue_task_api_v1_rooms__room_id__tasks_post",
      { path: { room_id: room.id } },
      {
        title: `${STAGE_LABELS[stage]} installed deliverable`,
        payload: {},
        correlation_id: correlation(`task_${stage}_${String(Date.now())}`),
      },
      201,
    ),
    "workflow task",
  );
  const taskId = text(task.id, "task id");
  await driver.command(
    "start_task_api_v1_tasks__task_id__start_post",
    { path: { task_id: taskId } },
    { expected_version: 1, correlation_id: correlation(`task_start_${stage}`) },
  );

  if (options.capabilityApproval === true) {
    const approvedCapability = record(
      await driver.command(
        "request_capability_api_v1_tasks__task_id__capability_requests_post",
        { path: { task_id: taskId } },
        {
          capability: "shell.test",
          reason: "Validate the generated project in the installed product E2E",
          target_paths: [],
          command: ["node", "--test"],
          risk_level: "medium",
          idempotency_key: `stage9-capability-${taskId}`,
          correlation_id: correlation("capability_request"),
        },
        201,
      ),
      "capability request",
    );
    await driver.command(
      "decide_capability_api_v1_capability_requests__request_id__decision_post",
      { path: { request_id: approvedCapability.id } },
      {
        approved: true,
        expected_version: integer(approvedCapability.version, "capability version"),
        reason: "Stage 9 installed E2E approval",
        correlation_id: correlation("capability_approved"),
      },
    );

    const rejectedCapability = record(
      await driver.command(
        "request_capability_api_v1_tasks__task_id__capability_requests_post",
        { path: { task_id: taskId } },
        {
          capability: "shell.test",
          reason: "Verify an explicit user rejection in the installed product E2E",
          target_paths: [],
          command: ["node", "--test"],
          risk_level: "medium",
          idempotency_key: `stage9-capability-rejected-${taskId}`,
          correlation_id: correlation("capability_request_rejected"),
        },
        201,
      ),
      "rejected capability request",
    );
    const rejectedDecision = record(
      await driver.command(
        "decide_capability_api_v1_capability_requests__request_id__decision_post",
        { path: { request_id: rejectedCapability.id } },
        {
          approved: false,
          expected_version: integer(rejectedCapability.version, "rejected capability version"),
          reason: "Stage 9 installed E2E rejection",
          correlation_id: correlation("capability_rejected"),
        },
      ),
      "rejected capability decision",
    );
    expect(rejectedDecision.status).toBe("rejected");

    const forbiddenResponse = record(
      await driver.command(
        "request_capability_api_v1_tasks__task_id__capability_requests_post",
        { path: { task_id: taskId } },
        {
          capability: "remote.deploy",
          reason: "Verify that a permanently forbidden capability cannot be requested",
          target_paths: [],
          command: null,
          risk_level: "high",
          idempotency_key: `stage9-capability-forbidden-${taskId}`,
          correlation_id: correlation("capability_request_forbidden"),
        },
        403,
      ),
      "forbidden capability response",
    );
    expect(record(forbiddenResponse.error, "forbidden capability error").code).toBe(
      "capability_request.forbidden",
    );
  }

  const artifactPath = `artifacts/${stage}/${stage}-deliverable.md`;
  const artifactContent =
    stage === "deployer"
      ? "# Release\n\nInstall: run the NSIS installer.\nRun: launch 星协.\nRollback: uninstall the program and preserve user data.\nKnown issue: Authenticode signing is pending.\n"
      : `# ${STAGE_LABELS[stage]}\n\nGenerated through the installed desktop ToolCall path.\n`;
  const artifactHash = await writeWithTool(
    driver,
    taskId,
    {
      planner: "filesystem.write_planner_artifact",
      designer: "filesystem.write_designer_artifact",
      builder: "filesystem.write_builder_artifact",
      reviewer: "filesystem.write_reviewer_artifact",
      deployer: "filesystem.write_deployment_document",
    }[stage],
    artifactPath,
    artifactContent,
    options.artifactExpectedHash ?? null,
  );

  if (stage === "builder" && options.artifactExpectedHash === undefined) {
    await writeWithTool(
      driver,
      taskId,
      "filesystem.write_source",
      "src/index.js",
      "function add(left, right) { return left + right; }\nmodule.exports = { add };\n",
    );
    await writeWithTool(
      driver,
      taskId,
      "filesystem.write_test",
      "tests/index.test.js",
      "const test = require('node:test');\nconst assert = require('node:assert/strict');\nconst { add } = require('../src/index.js');\ntest('add', () => assert.equal(add(2, 3), 5));\n",
    );
    await writeWithTool(
      driver,
      taskId,
      "filesystem.write_build_config",
      "package.json",
      JSON.stringify({
        name: "xingxie-stage9-output",
        private: true,
        scripts: {
          build: "node -e \"require('./src/index.js')\"",
          test: "node --test",
        },
      }) + "\n",
    );
  }
  if (stage === "deployer") {
    await writeWithTool(
      driver,
      taskId,
      "filesystem.write_deployment_config",
      "deploy/config/release.json",
      '{"application":"星协阶段9样例","version":1}\n',
    );
    await writeWithTool(
      driver,
      taskId,
      "filesystem.write_deployment_script",
      "deploy/scripts/run.cmd",
      "@echo off\r\nnode src\\index.js\r\n",
    );
  }

  await driver.command(
    "complete_task_api_v1_tasks__task_id__complete_post",
    { path: { task_id: taskId } },
    {
      expected_version: 2,
      succeeded: true,
      result: { artifact: artifactPath },
      correlation_id: correlation(`task_complete_${stage}`),
    },
  );
  const runCreation = record(
    await driver.command(
      "create_agent_run_api_v1_rooms__room_id__agent_runs_post",
      { path: { room_id: room.id } },
      {
        request_key: `stage9-${stage}-${String(Date.now())}-formal`,
        formal: true,
        correlation_id: correlation(`agent_run_${stage}`),
      },
    ),
    "agent run creation",
  );
  const agentRun = record(runCreation.run, "agent run");
  const runId = text(agentRun.id, "agent run id");
  const frames = await driver.stream(
    "stream_agent_run_api_v1_agent_runs__run_id__stream_post",
    { path: { run_id: runId } },
    {
      instruction: `Produce and review the ${stage} deliverable for the installed product E2E.`,
      correlation_id: correlation(`agent_stream_${stage}`),
    },
  );
  expect(Array.isArray(frames)).toBe(true);
  const runSnapshot = record(
    await driver.query("get_agent_run_api_v1_agent_runs__run_id__get", {
      path: { run_id: runId },
    }),
    "agent run snapshot",
  );
  expect(record(runSnapshot.run, "persisted agent run").status).toBe("succeeded");
  expect(records(runSnapshot.calls, "persisted model calls").length).toBeGreaterThanOrEqual(3);
  expect(
    records(runSnapshot.usage, "persisted usage").every(
      (usage) => integer(usage.total_tokens, "usage total tokens") > 0,
    ),
  ).toBe(true);
  const persistedOutput = await driver.query(
    "get_agent_run_output_api_v1_agent_runs__run_id__output_get",
    { path: { run_id: runId } },
  );
  expect(text(persistedOutput, "persisted agent output")).toContain("[Fake Model]");

  await driver.transition(workflowId, stage, "producing");
  const versionCreation = record(
    await driver.command(
      "create_artifact_version_api_v1_stage_runs__stage_run_id__artifact_versions_post",
      { path: { stage_run_id: stageRun.id } },
      {
        name: `${STAGE_LABELS[stage]} installed deliverable`,
        relative_path: artifactPath,
        correlation_id: correlation(`artifact_${stage}_${String(Date.now())}`),
      },
      201,
    ),
    "artifact version creation",
  );
  const version = record(versionCreation.version, "artifact version");
  await driver.transition(workflowId, stage, "p2r_reviewing");
  await driver.transition(workflowId, stage, "quality_checking");
  const gateResponse = record(
    await driver.command(
      "evaluate_quality_gate_api_v1_stage_runs__stage_run_id__quality_gates_post",
      { path: { stage_run_id: stageRun.id } },
      {
        artifact_version_ids: [version.id],
        correlation_id: correlation(`gate_${stage}_${String(Date.now())}`),
      },
      201,
    ),
    "gate evaluation",
  );
  const gate = record(gateResponse.gate, "quality gate");
  expect(gate.status).toBe(options.expectedGate);
  expect(gate.resolution).toBe(options.expectedResolution);
  if (options.expectedResolution === "pending") {
    const approval = record(gateResponse.approval, "gate approval");
    const decision = record(
      await driver.command(
        "decide_gate_approval_api_v1_approvals__approval_id__decision_post",
        { path: { approval_id: approval.id } },
        {
          approved: true,
          expected_version: integer(approval.version, "approval version"),
          reason: "Approved by the installed Stage 9 E2E",
          correlation_id: correlation(`approval_${stage}`),
        },
      ),
      "approval decision",
    );
    expect(record(decision.approval, "approved record").status).toBe("approved");
    expect(decision.handoff).not.toBeNull();
  } else if (options.expectedResolution === "automatic") {
    expect(gateResponse.handoff).not.toBeNull();
  } else {
    expect(gateResponse.change_request).not.toBeNull();
    expect(gateResponse.handoff).toBeNull();
  }
  expect(version.content_hash).toBe(artifactHash);
  return { artifactHash, gate };
}

async function completeStageThroughUi(
  driver: DesktopDriver,
  projectId: string,
  workflowId: string,
  stage: Stage,
  expectedGate: "pass" | "warning",
  expectedResolution: "automatic" | "pending" | "rewrite_required",
): Promise<void> {
  await driver.navigate(`/projects/${projectId}`);
  await driver.navigate(`/projects/${projectId}/stages/${stage}`);
  await expect(
    driver.page.getByRole("heading", { name: STAGE_LABELS[stage], exact: true }),
  ).toBeVisible();
  const returnToDiscussion = driver.page.getByRole("button", { name: "返回讨论" });
  if (await returnToDiscussion.isVisible()) {
    await returnToDiscussion.click();
    await expect(
      driver.page.locator(".stage-summary-grid article").first().getByText(
        "discussing",
        { exact: true },
      ),
    ).toBeVisible();
  }
  await driver.page.getByLabel("AgentRun 指令").fill(
    `Complete the ${stage} stage through the installed user-visible orchestration path.`,
  );
  const runButton = driver.page.getByRole("button", { name: "运行并完成本阶段" });
  await expect(runButton).toBeEnabled();
  await runButton.click();
  const expectedStageState =
    expectedResolution === "pending"
      ? "waiting_approval"
      : expectedResolution === "rewrite_required"
        ? expectedGate === "warning"
          ? "warning_blocked"
          : "needs_fix"
        : "completed";
  await expect(
    driver.page.locator(".stage-summary-grid article").first().getByText(
      expectedStageState,
      { exact: true },
    ),
  ).toBeVisible({ timeout: 180_000 });

  const snapshot = await driver.snapshot(workflowId);
  const stageRun = records(snapshot.stage_runs, "orchestrated stage runs").find(
    (candidate) => candidate.stage === stage,
  );
  if (stageRun === undefined) {
    throw new Error(`Orchestrated ${stage} StageRun was not found`);
  }
  const room = records(snapshot.rooms, "orchestrated rooms").find(
    (candidate) => candidate.stage_run_id === stageRun.id,
  );
  if (room === undefined) {
    throw new Error(`Orchestrated ${stage} Room was not found`);
  }
  const runList = record(
    await driver.query("list_agent_runs_api_v1_rooms__room_id__agent_runs_get", {
      path: { room_id: room.id },
    }),
    "orchestrated AgentRun list",
  );
  const formalRuns = records(runList.runs, "orchestrated AgentRuns").filter(
    (run) => run.formal === true,
  );
  const formalRun = formalRuns.at(-1);
  if (formalRun === undefined) {
    throw new Error(`Orchestrated ${stage} formal AgentRun was not found`);
  }
  expect(formalRun.status).toBe("succeeded");
  const runId = text(formalRun.id, "orchestrated AgentRun id");
  const runSnapshot = record(
    await driver.query("get_agent_run_api_v1_agent_runs__run_id__get", {
      path: { run_id: runId },
    }),
    "orchestrated AgentRun snapshot",
  );
  expect(records(runSnapshot.calls, "orchestrated model calls")).toHaveLength(4);
  const output = await driver.query(
    "get_agent_run_output_api_v1_agent_runs__run_id__output_get",
    { path: { run_id: runId } },
  );
  expect(text(output, "orchestrated AgentRun output")).toContain('"schema_version":1');

  const gateList = record(
    await driver.query("list_quality_gates_api_v1_workflows__workflow_id__quality_gates_get", {
      path: { workflow_id: workflowId },
    }),
    "orchestrated gate list",
  );
  const gate = records(gateList.gates, "orchestrated gates")
    .filter((candidate) => candidate.stage_run_id === stageRun.id)
    .at(-1);
  if (gate === undefined) {
    throw new Error(`Orchestrated ${stage} gate was not found`);
  }
  expect(gate.status).toBe(expectedGate);
  expect(gate.resolution).toBe(expectedResolution);

  if (expectedResolution === "pending") {
    await driver.navigate(`/projects/${projectId}/approvals`);
    await expect(driver.page.getByRole("heading", { name: "审批、能力与风险" })).toBeVisible();
    await driver.page.getByLabel("决定原因（可选）").fill(
      `Approved from the installed UI for ${stage}.`,
    );
    const approveButton = driver.page.getByRole("button", { name: "批准" }).last();
    await expect(approveButton).toBeEnabled();
    await approveButton.click();
    await waitUntil(async () => {
      const updated = await driver.snapshot(workflowId);
      const updatedRun = records(updated.stage_runs, "approved stage runs").find(
        (candidate) => candidate.id === stageRun.id,
      );
      return updatedRun?.state === "completed";
    }, 30_000, `The installed UI did not approve the ${stage} gate`);
  }
}

async function setModeThroughUi(
  driver: DesktopDriver,
  projectId: string,
  mode: "manual" | "autonomous",
): Promise<void> {
  await driver.navigate(`/projects/${projectId}`);
  const group = driver.page.getByRole("group", { name: "执行模式" });
  const label = mode === "manual" ? "Manual" : "Autonomous";
  const button = group.getByRole("button", { name: label });
  await expect(button).toBeEnabled();
  await button.click();
  await expect(button).toHaveAttribute("aria-pressed", "true");
}

async function captureInstalledViews(
  driver: DesktopDriver,
  projectId: string,
  workflowId: string,
  testInfo: TestInfo,
): Promise<void> {
  const routes: Array<[string, string, string]> = [
    ["S00-startup", "/startup", "启动星协"],
    ["S01-projects", "/projects", "本地项目"],
    ["S02-preflight", `/projects/${projectId}/preflight`, "项目预检"],
    ["S03-overview", `/projects/${projectId}`, "项目主页"],
    ...STAGES.map(
      (stage): [string, string, string] => [
        `S04-${stage}`,
        `/projects/${projectId}/stages/${stage}`,
        STAGE_LABELS[stage],
      ],
    ),
    ["S05-artifacts", `/projects/${projectId}/artifacts`, "产出、Gate 与交接"],
    ["S06-approvals", `/projects/${projectId}/approvals`, "审批、能力与风险"],
    ["S07-recovery", `/projects/${projectId}/recovery`, "冲突、检查点与恢复"],
    ["S08-settings", "/settings", "设置"],
    ["S09-diagnostics", "/diagnostics", "诊断"],
  ];
  for (const [name, route, expectedText] of routes) {
    await driver.navigate(route);
    await expect(driver.page.getByText(expectedText, { exact: false }).first()).toBeVisible();
    const screenshotPath = testInfo.outputPath(`${name}.png`);
    await driver.page.screenshot({ fullPage: true, path: screenshotPath });
    await testInfo.attach(name, {
      path: screenshotPath,
      contentType: "image/png",
    });
  }
  await driver.navigate("/settings");
  await expect(driver.page.getByText(/Fake Model Primary/).first()).toBeVisible();
  await driver.navigate("/diagnostics");
  await driver.page.getByLabel("Workflow ID").fill(workflowId);
  await driver.page.getByRole("button", { name: "读取审计" }).click();
  await expect(
    driver.page.getByText("filesystem.write_builder_artifact", { exact: true }).first(),
  ).toBeVisible();
  await expect(driver.page.locator("body")).not.toContainText("fixtureDesktopPort");
}

test("installed desktop completes and recovers the V1 product workflow", async ({ browserName }, testInfo) => {
  expect(browserName).toBe("chromium");
  test.skip(process.platform !== "win32", "The installed product gate is Windows-only");
  const frontendRoot = resolve(dirname(fileURLToPath(import.meta.url)), "../..");
  const installer = join(frontendRoot, "release", "XingXie-1.0.0-rc.1-Setup.exe");
  expect(await exists(installer), "Build the NSIS installer before product E2E").toBe(true);

  const root = await mkdtemp(join(tmpdir(), "星协 阶段9 "));
  const safeTempRoot = resolve(tmpdir()) + sep;
  if (!resolve(root).startsWith(safeTempRoot)) {
    throw new Error("Product E2E root escaped the OS temporary directory");
  }
  const installDir = join(root, "中文 空格", "星协安装");
  const dataRoot = join(root, "应用 数据");
  const directWorkspace = join(root, "真实 Direct 项目");
  const orchestratedWorkspace = join(root, "真实 UI 编排项目");
  const managedSource = join(root, "Managed 导入源");
  const recoveryWorkspace = join(root, "崩溃 恢复项目");
  const directTracked = join(directWorkspace, "conflict.txt");
  await Promise.all([
    mkdir(join(directWorkspace, "src"), { recursive: true }),
    mkdir(orchestratedWorkspace, { recursive: true }),
    mkdir(managedSource, { recursive: true }),
    mkdir(recoveryWorkspace, { recursive: true }),
  ]);
  await Promise.all([
    writeFile(join(directWorkspace, "README.md"), "# Installed Stage 9 project\n", "utf8"),
    writeFile(
      join(orchestratedWorkspace, "README.md"),
      "# Installed user-visible orchestration project\n",
      "utf8",
    ),
    writeFile(directTracked, "baseline\n", "utf8"),
    writeFile(join(managedSource, "README.md"), "# Managed import\n", "utf8"),
    writeFile(join(recoveryWorkspace, "README.md"), "# Recovery project\n", "utf8"),
    writeFile(
      join(recoveryWorkspace, "package.json"),
      JSON.stringify({
        name: "stage9-crash-recovery",
        private: true,
        scripts: { test: "node -e \"setTimeout(() => {}, 60000)\"" },
      }) + "\n",
      "utf8",
    ),
  ]);

  let installed: ElectronApplication | null = null;
  try {
    await runProcess(installer, ["/S", `/D=${installDir}`]);
    const installedExe = join(installDir, "星协.exe");
    expect(await exists(installedExe)).toBe(true);
    let launched = await launchInstalled(installedExe, dataRoot, [
      directWorkspace,
      orchestratedWorkspace,
      managedSource,
      recoveryWorkspace,
    ]);
    installed = launched.app;
    let driver = launched.driver;

    const managedCreation = await createProject(driver, {
      name: "阶段9 Managed 项目",
      goal: "验证安装版 Managed Workspace",
      path: managedSource,
      mode: "managed",
    });
    const managedRegistration = record(managedCreation.registration, "managed registration");
    const managedProject = record(managedRegistration.project, "managed project");
    const managedProjectId = text(managedProject.id, "managed project id");
    const managedPreflight = await preflight(driver, managedProjectId);
    expect(record(managedPreflight.result, "managed preflight").status).not.toBe("fail");
    const managedWorkflow = await createWorkflow(
      driver,
      managedProjectId,
      "Managed 安装版控制流",
    );
    const managedWorkflowId = text(record(managedWorkflow.workflow, "managed workflow").id, "managed workflow id");
    await driver.transition(managedWorkflowId, "planner", "discussing");
    for (const action of ["pause", "resume", "stop"] as const) {
      await driver.control(managedWorkflowId, action);
    }

    const directCreation = await createProject(driver, {
      name: "阶段9 Direct 五阶段项目",
      goal: "从 Planner 到 Deployer 生成可验证交付",
      path: directWorkspace,
      mode: "direct",
    });
    const directRegistration = record(directCreation.registration, "direct registration");
    const directProject = record(directRegistration.project, "direct project");
    const directProjectId = text(directProject.id, "direct project id");

    const baseline = record(
      await driver.command(
        "create_checkpoint_api_v1_projects__project_id__checkpoints_post",
        { path: { project_id: directProjectId } },
        { reason: "manual", correlation_id: correlation("conflict_baseline") },
        201,
      ),
      "baseline checkpoint",
    );
    await writeFile(directTracked, "agent version\n", "utf8");
    const agentCheckpoint = record(
      await driver.command(
        "create_checkpoint_api_v1_projects__project_id__checkpoints_post",
        { path: { project_id: directProjectId } },
        { reason: "pre_mutation", correlation_id: correlation("conflict_agent") },
        201,
      ),
      "agent checkpoint",
    );
    await writeFile(directTracked, "user version\n", "utf8");
    const scan = record(
      await driver.command(
        "scan_external_changes_api_v1_projects__project_id__external_changes_scan_post",
        { path: { project_id: directProjectId } },
        {
          baseline_checkpoint_id: baseline.id,
          agent_checkpoint_id: agentCheckpoint.id,
          correlation_id: correlation("conflict_scan"),
        },
      ),
      "external change scan",
    );
    const conflict = records(scan.conflicts, "file conflicts")[0];
    if (conflict === undefined) {
      throw new Error("The installed E2E did not produce a three-way conflict");
    }
    const conflictResolution = record(
      await driver.command(
      "resolve_conflict_api_v1_projects__project_id__conflicts__conflict_id__resolve_post",
      { path: { project_id: directProjectId, conflict_id: conflict.id } },
      {
        resolution: "keep_agent",
        expected_conflict_version: integer(conflict.version, "conflict version"),
        expected_project_version: integer(directProject.version, "direct project version"),
        agent_checkpoint_id: agentCheckpoint.id,
        merged_content_hash: null,
        correlation_id: correlation("conflict_resolve"),
      },
      ),
      "conflict resolution",
    );
    expect(await readFile(directTracked, "utf8")).toBe("agent version\n");

    await writeFile(directTracked, "post-conflict drift\n", "utf8");
    const restorePlanning = record(
      await driver.command(
        "plan_restore_api_v1_projects__project_id__checkpoints__checkpoint_id__restore_plan_post",
        { path: { project_id: directProjectId, checkpoint_id: agentCheckpoint.id } },
        { correlation_id: correlation("checkpoint_restore_plan") },
      ),
      "checkpoint restore plan",
    );
    const protectionCheckpoint = record(
      restorePlanning.protection_checkpoint,
      "restore protection checkpoint",
    );
    const restored = record(
      await driver.command(
        "restore_checkpoint_api_v1_projects__project_id__checkpoints__checkpoint_id__restore_post",
        { path: { project_id: directProjectId, checkpoint_id: agentCheckpoint.id } },
        {
          protection_checkpoint_id: protectionCheckpoint.id,
          expected_project_version: integer(
            record(conflictResolution.project, "resolved conflict project").version,
            "resolved conflict project version",
          ),
          correlation_id: correlation("checkpoint_restore"),
        },
      ),
      "checkpoint restore result",
    );
    expect(integer(record(restored.result, "restore result").restored_file_count, "restored file count")).toBeGreaterThan(0);
    expect(await readFile(directTracked, "utf8")).toBe("agent version\n");
    const directPreflight = await preflight(driver, directProjectId);
    expect(record(directPreflight.result, "direct preflight").status).not.toBe("fail");

    const workflowSnapshot = await createWorkflow(
      driver,
      directProjectId,
      "安装版五阶段正式交付",
    );
    const workflow = record(workflowSnapshot.workflow, "direct workflow");
    const workflowId = text(workflow.id, "direct workflow id");

    const profileIds: string[] = [];
    for (const role of ["Primary", "Reviewer A", "Reviewer B"] as const) {
      const secret = await driver.storeSecret(`stage9-${role}-credential`, `Fake Model ${role}`);
      const profile = record(
        await driver.command(
          "create_profile_api_v1_model_profiles_post",
          undefined,
          {
            name: `Fake Model ${role}`,
            provider: "fake",
            base_url: "https://fake.invalid/v1",
            model: `stage9-${role.toLowerCase().replaceAll(" ", "-")}`,
            credential_ref: secret.credentialRef,
            masked_hint: secret.maskedHint,
            correlation_id: correlation(`profile_${role}`),
          },
          201,
        ),
        "model profile",
      );
      profileIds.push(text(profile.id, "profile id"));
    }
    for (const room of records(workflowSnapshot.rooms, "workflow rooms")) {
      await driver.command(
        "assign_room_models_api_v1_rooms__room_id__model_assignment_put",
        { path: { room_id: room.id } },
        {
          primary_profile_id: profileIds[0],
          reviewer_a_profile_id: profileIds[1],
          reviewer_b_profile_id: profileIds[2],
          expected_version: null,
          correlation_id: correlation(`assignment_${text(room.stage, "room stage")}`),
        },
      );
    }

    const orchestratedCreation = await createProject(driver, {
      name: "阶段9 UI 自动编排项目",
      goal: "仅通过安装版可见页面完成 Planner 到 Deployer",
      path: orchestratedWorkspace,
      mode: "direct",
    });
    const orchestratedRegistration = record(
      orchestratedCreation.registration,
      "orchestrated registration",
    );
    const orchestratedProject = record(
      orchestratedRegistration.project,
      "orchestrated project",
    );
    const orchestratedProjectId = text(orchestratedProject.id, "orchestrated project id");
    await preflight(driver, orchestratedProjectId);
    const orchestratedSnapshot = await createWorkflow(
      driver,
      orchestratedProjectId,
      "安装版用户可见自动编排",
    );
    const orchestratedWorkflowId = text(
      record(orchestratedSnapshot.workflow, "orchestrated workflow").id,
      "orchestrated workflow id",
    );
    for (const room of records(orchestratedSnapshot.rooms, "orchestrated workflow rooms")) {
      await driver.command(
        "assign_room_models_api_v1_rooms__room_id__model_assignment_put",
        { path: { room_id: room.id } },
        {
          primary_profile_id: profileIds[0],
          reviewer_a_profile_id: profileIds[1],
          reviewer_b_profile_id: profileIds[2],
          expected_version: null,
          correlation_id: correlation(`ui_assignment_${text(room.stage, "room stage")}`),
        },
      );
    }

    await completeStageThroughUi(
      driver,
      orchestratedProjectId,
      orchestratedWorkflowId,
      "planner",
      "pass",
      "pending",
    );
    await setModeThroughUi(driver, orchestratedProjectId, "autonomous");
    await completeStageThroughUi(
      driver,
      orchestratedProjectId,
      orchestratedWorkflowId,
      "designer",
      "pass",
      "automatic",
    );
    await completeStageThroughUi(
      driver,
      orchestratedProjectId,
      orchestratedWorkflowId,
      "builder",
      "warning",
      "rewrite_required",
    );
    await setModeThroughUi(driver, orchestratedProjectId, "manual");
    await completeStageThroughUi(
      driver,
      orchestratedProjectId,
      orchestratedWorkflowId,
      "builder",
      "warning",
      "pending",
    );
    await completeStageThroughUi(
      driver,
      orchestratedProjectId,
      orchestratedWorkflowId,
      "reviewer",
      "warning",
      "pending",
    );
    await completeStageThroughUi(
      driver,
      orchestratedProjectId,
      orchestratedWorkflowId,
      "deployer",
      "pass",
      "pending",
    );
    const orchestratedCompleted = await driver.snapshot(orchestratedWorkflowId);
    expect(record(orchestratedCompleted.workflow, "orchestrated completed workflow").status).toBe(
      "completed",
    );
    expect(
      records(orchestratedCompleted.stage_runs, "orchestrated completed stages").every(
        (run) => run.state === "completed",
      ),
    ).toBe(true);
    await runProcess(process.execPath, ["--test"], {
      cwd: orchestratedWorkspace,
      timeoutMs: 60_000,
    });
    await runProcess(process.execPath, ["-e", "require('./src/index.js')"], {
      cwd: orchestratedWorkspace,
      timeoutMs: 60_000,
    });

    await completeStage(driver, workflowId, "planner", {
      expectedGate: "pass",
      expectedResolution: "pending",
      capabilityApproval: true,
    });
    await driver.setMode(workflowId, "autonomous");
    await completeStage(driver, workflowId, "designer", {
      expectedGate: "pass",
      expectedResolution: "automatic",
    });
    const firstBuilder = await completeStage(driver, workflowId, "builder", {
      expectedGate: "warning",
      expectedResolution: "rewrite_required",
    });
    const blocked = await driver.snapshot(workflowId);
    expect(record(blocked.workflow, "blocked workflow").status).toBe("warning_blocked");
    await driver.setMode(workflowId, "manual");
    await driver.control(workflowId, "pause");
    await driver.control(workflowId, "resume");
    await completeStage(driver, workflowId, "builder", {
      expectedGate: "warning",
      expectedResolution: "pending",
      artifactExpectedHash: firstBuilder.artifactHash,
    });
    await completeStage(driver, workflowId, "reviewer", {
      expectedGate: "warning",
      expectedResolution: "pending",
    });
    await completeStage(driver, workflowId, "deployer", {
      expectedGate: "pass",
      expectedResolution: "pending",
    });

    const completed = await driver.snapshot(workflowId);
    expect(record(completed.workflow, "completed workflow").status).toBe("completed");
    expect(records(completed.stage_runs, "completed stage runs").every((run) => run.state === "completed")).toBe(true);
    const artifacts = record(
      await driver.query("list_artifacts_api_v1_workflows__workflow_id__artifacts_get", {
        path: { workflow_id: workflowId },
      }),
      "artifact inventory",
    );
    expect(records(artifacts.versions, "artifact versions").filter((version) => version.status === "locked")).toHaveLength(5);
    const handoffs = record(
      await driver.query("list_handoffs_api_v1_workflows__workflow_id__handoffs_get", {
        path: { workflow_id: workflowId },
      }),
      "handoff inventory",
    );
    expect(records(handoffs.handoffs, "handoffs")).toHaveLength(5);
    const changes = record(
      await driver.query("list_change_requests_api_v1_workflows__workflow_id__change_requests_get", {
        path: { workflow_id: workflowId },
      }),
      "change request inventory",
    );
    expect(records(changes.change_requests, "change requests").length).toBeGreaterThan(0);

    await runProcess(process.execPath, ["--test"], {
      cwd: directWorkspace,
      timeoutMs: 60_000,
    });
    await runProcess(process.execPath, ["-e", "require('./src/index.js')"], {
      cwd: directWorkspace,
      timeoutMs: 60_000,
    });
    await captureInstalledViews(driver, directProjectId, workflowId, testInfo);

    const recoveryCreation = await createProject(driver, {
      name: "阶段9 崩溃恢复项目",
      goal: "验证安装版异常退出恢复",
      path: recoveryWorkspace,
      mode: "direct",
    });
    const recoveryRegistration = record(recoveryCreation.registration, "recovery registration");
    const recoveryProject = record(recoveryRegistration.project, "recovery project");
    const recoveryProjectId = text(recoveryProject.id, "recovery project id");
    await preflight(driver, recoveryProjectId);
    const recoverySnapshot = await createWorkflow(
      driver,
      recoveryProjectId,
      "安装版异常退出恢复",
    );
    const recoveryWorkflow = record(recoverySnapshot.workflow, "recovery workflow");
    const recoveryWorkflowId = text(recoveryWorkflow.id, "recovery workflow id");
    await driver.transition(recoveryWorkflowId, "planner", "discussing");
    const activeRecovery = await driver.snapshot(recoveryWorkflowId);
    const recoveryRoom = records(activeRecovery.rooms, "recovery rooms")[0];
    if (recoveryRoom === undefined) {
      throw new Error("Recovery room was not found");
    }
    const recoveryTask = record(
      await driver.command(
        "enqueue_task_api_v1_rooms__room_id__tasks_post",
        { path: { room_id: recoveryRoom.id } },
        {
          title: "Crash interrupted task",
          payload: {},
          correlation_id: correlation("recovery_task"),
        },
        201,
      ),
      "recovery task",
    );
    await driver.command(
      "start_task_api_v1_tasks__task_id__start_post",
      { path: { task_id: recoveryTask.id } },
      { expected_version: 1, correlation_id: correlation("recovery_task_start") },
    );

    await driver.command(
      "assign_room_models_api_v1_rooms__room_id__model_assignment_put",
      { path: { room_id: recoveryRoom.id } },
      {
        primary_profile_id: profileIds[0],
        reviewer_a_profile_id: profileIds[1],
        reviewer_b_profile_id: profileIds[2],
        expected_version: null,
        correlation_id: correlation("recovery_assignment"),
      },
    );
    const interruptedAgentRun = record(
      await driver.command(
        "create_agent_run_api_v1_rooms__room_id__agent_runs_post",
        { path: { room_id: recoveryRoom.id } },
        {
          request_key: `stage9-recovery-${String(Date.now())}-pending`,
          formal: true,
          correlation_id: correlation("recovery_agent_run"),
        },
      ),
      "recovery agent run creation",
    );
    expect(record(interruptedAgentRun.run, "pending recovery agent run").status).toBe("pending");

    const recoveryCapability = record(
      await driver.command(
        "request_capability_api_v1_tasks__task_id__capability_requests_post",
        { path: { task_id: recoveryTask.id } },
        {
          capability: "shell.test",
          reason: "Run a long-lived test command to verify crash interruption",
          target_paths: [],
          command: ["npm", "run", "test"],
          risk_level: "medium",
          idempotency_key: `stage9-recovery-tool-${String(recoveryTask.id)}`,
          correlation_id: correlation("recovery_tool_capability"),
        },
        201,
      ),
      "recovery tool capability",
    );
    await driver.command(
      "decide_capability_api_v1_capability_requests__request_id__decision_post",
      { path: { request_id: recoveryCapability.id } },
      {
        approved: true,
        expected_version: integer(recoveryCapability.version, "recovery capability version"),
        reason: "Approve the isolated Stage 9 crash command",
        correlation_id: correlation("recovery_tool_approved"),
      },
    );
    const pendingToolExecution = driver
      .command(
        "execute_tool_api_v1_tasks__task_id__tool_calls_post",
        { path: { task_id: recoveryTask.id } },
        {
          tool_name: "shell.test",
          idempotency_key: `stage9-recovery-running-tool-${String(recoveryTask.id)}`,
          arguments: { command_index: 0 },
          timeout_seconds: 120,
          correlation_id: correlation("recovery_running_tool"),
        },
      )
      .catch(() => null);
    await waitUntil(async () => {
      const toolCalls = record(
        await driver.query("list_tool_calls_api_v1_workflows__workflow_id__tool_calls_get", {
          path: { workflow_id: recoveryWorkflowId },
        }),
        "recovery tool calls",
      );
      return records(toolCalls.calls, "recovery tool call list").some(
        (call) => call.status === "running",
      );
    }, 20_000, "The recovery ToolCall did not enter running state");

    const crashedPid = installed.process().pid;
    if (crashedPid === undefined) {
      throw new Error("Electron main process id is unavailable");
    }
    await runProcess("taskkill.exe", ["/PID", String(crashedPid), "/T", "/F"], {
      timeoutMs: 30_000,
    });
    await pendingToolExecution;
    installed = null;
    await waitUntil(
      () => {
        try {
          process.kill(crashedPid, 0);
          return false;
        } catch {
          return true;
        }
      },
      20_000,
      "The crashed Electron main process did not exit",
    );
    await new Promise((resolveWait) => setTimeout(resolveWait, 2_500));

    launched = await relaunchAfterCrash(installedExe, dataRoot, [
      directWorkspace,
      orchestratedWorkspace,
      managedSource,
      recoveryWorkspace,
    ]);
    installed = launched.app;
    driver = launched.driver;
    await driver.navigate("/startup");
    await expect(driver.page.getByText(recoveryWorkflowId)).toBeVisible();
    const recoveries = record(
      await driver.query("list_recoveries_api_v1_recovery_get"),
      "recovery list",
    );
    const pendingRecovery = records(recoveries.recoveries, "recoveries").find(
      (candidate) => candidate.workflow_id === recoveryWorkflowId && candidate.status === "pending",
    );
    if (pendingRecovery === undefined) {
      throw new Error("Pending recovery record was not created after the crash");
    }
    expect(pendingRecovery.interrupted_tasks).toBe(1);
    expect(pendingRecovery.interrupted_agent_runs).toBe(1);
    expect(pendingRecovery.interrupted_tool_calls).toBe(1);
    await driver.command(
      "resolve_recovery_api_v1_recovery__recovery_id___action__post",
      { path: { recovery_id: pendingRecovery.id, action: "resume" } },
      { correlation_id: correlation("recovery_resume") },
    );

    const replayedEvent = driver.page.evaluate(
      (expectedWorkflowId) =>
        new Promise<{ eventId: number; eventType: string }>((resolveEvent, rejectEvent) => {
          const timeout = window.setTimeout(() => {
            unsubscribe();
            rejectEvent(new Error("Timed out waiting for the persisted event replay"));
          }, 15_000);
          const unsubscribe = window.desktop.backend.subscribe((event) => {
            if (
              event.workflow_id !== expectedWorkflowId ||
              typeof event.event_id !== "number" ||
              !Number.isInteger(event.event_id) ||
              typeof event.event_type !== "string"
            ) {
              return;
            }
            window.clearTimeout(timeout);
            unsubscribe();
            resolveEvent({ eventId: event.event_id, eventType: event.event_type });
          });
          void window.desktop.backend.requestReplay(0).catch((error: unknown) => {
            window.clearTimeout(timeout);
            unsubscribe();
            rejectEvent(error instanceof Error ? error : new Error("Event replay failed"));
          });
        }),
      recoveryWorkflowId,
    );
    const resumed = await driver.snapshot(recoveryWorkflowId);
    const replayEvidence = await replayedEvent;
    expect(replayEvidence.eventId).toBeGreaterThan(0);
    expect(replayEvidence.eventType.length).toBeGreaterThan(0);
    expect(record(resumed.workflow, "resumed workflow").status).toBe("running");
    expect(records(resumed.stage_runs, "resumed stage runs")[0]?.state).toBe("discussing");
    const resumedWorkflow = record(resumed.workflow, "resumed workflow");
    await driver.command(
      "control_workflow_api_v1_workflows__workflow_id___action__post",
      { path: { workflow_id: recoveryWorkflowId, action: "stop" } },
      {
        expected_version: integer(resumedWorkflow.version, "resumed workflow version"),
        correlation_id: correlation("recovery_stop"),
      },
    );
    await installed.close();
    installed = null;

    const uninstaller = join(installDir, "Uninstall 星协.exe");
    await runProcess(uninstaller, ["/S"]);
    await waitUntil(
      async () => !(await exists(installDir)),
      30_000,
      "NSIS did not remove the installed program directory",
    );
    expect(await exists(dataRoot)).toBe(true);
    expect(await readFile(directTracked, "utf8")).toBe("agent version\n");

    await runProcess(installer, ["/S", `/D=${installDir}`]);
    launched = await launchInstalled(join(installDir, "星协.exe"), dataRoot, [
      directWorkspace,
      orchestratedWorkspace,
      managedSource,
      recoveryWorkspace,
    ]);
    installed = launched.app;
    driver = launched.driver;
    const persisted = await driver.snapshot(workflowId);
    expect(record(persisted.workflow, "reinstalled workflow").status).toBe("completed");
    const persistedOrchestration = await driver.snapshot(orchestratedWorkflowId);
    expect(record(persistedOrchestration.workflow, "reinstalled orchestration workflow").status).toBe(
      "completed",
    );
    await driver.navigate(`/projects/${directProjectId}`);
    await expect(driver.page.getByText("安装版五阶段正式交付")).toBeVisible();

    const report = {
      schemaVersion: 1,
      projectId: directProjectId,
      workflowId,
      orchestratedProjectId,
      orchestratedWorkflowId,
      recoveryWorkflowId,
      managedProjectId,
      stages: STAGES,
      formalAgentRuns: 12,
      qualityGateEvaluations: 12,
      lockedArtifactVersions: 10,
      handoffs: 10,
      manualApprovals: 8,
      autonomousHandoffs: 2,
      userVisibleOrchestration: true,
      warningRework: true,
      capabilityApproved: true,
      capabilityRejected: true,
      forbiddenCapabilityBlocked: true,
      conflictResolved: true,
      checkpointRestored: true,
      crashRecovery: true,
      interruptedTasks: 1,
      interruptedAgentRuns: 1,
      interruptedToolCalls: 1,
      eventReplayAfterRestart: true,
      reinstallRecovery: true,
      directWorkspacePreserved: true,
    };
    const reportPath = testInfo.outputPath("stage9-product-report.json");
    await writeFile(reportPath, JSON.stringify(report, null, 2) + "\n", "utf8");
    await testInfo.attach("stage9-product-report", {
      path: reportPath,
      contentType: "application/json",
    });
  } catch (error) {
    const page = installed?.windows()[0];
    if (page !== undefined && !page.isClosed()) {
      const pageText = await page.locator("body").innerText().catch(() => "页面文本不可用");
      await testInfo.attach("desktop-failure-page", {
        body: pageText,
        contentType: "text/plain",
      });
      const screenshotPath = testInfo.outputPath("desktop-failure.png");
      await page.screenshot({ fullPage: true, path: screenshotPath }).catch(() => undefined);
      if (await exists(screenshotPath)) {
        await testInfo.attach("desktop-failure-screenshot", {
          path: screenshotPath,
          contentType: "image/png",
        });
      }
    }
    const backendLog = join(dataRoot, "logs", "backend.jsonl");
    if (await exists(backendLog)) {
      await testInfo.attach("desktop-backend-log", {
        path: backendLog,
        contentType: "application/x-ndjson",
      });
    }
    throw error;
  } finally {
    if (installed !== null) {
      await installed.close().catch(() => undefined);
    }
    const uninstaller = join(installDir, "Uninstall 星协.exe");
    if (await exists(uninstaller)) {
      await runProcess(uninstaller, ["/S"]).catch(() => undefined);
      await waitUntil(async () => !(await exists(installDir)), 30_000, "uninstall cleanup").catch(
        () => undefined,
      );
    }
    const resolvedRoot = resolve(root);
    if (resolvedRoot.startsWith(resolve(tmpdir()) + sep)) {
      await rm(resolvedRoot, { recursive: true, force: true });
    }
  }
});
