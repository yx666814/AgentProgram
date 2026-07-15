# 星协 V1 正式前端 Implementation Plan v1

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 严格依据 `PROJECT-PLAN.md`，在阶段 5 冻结的后端契约上，依次完成开发前端母版和正式前端，实现与草案母版逐页一致、无假成功和无死控件的 Windows Electron Renderer。

**Architecture:** 阶段 7 的 Renderer 只依赖类型化 `DesktopPort`，不直接取得 Token、文件系统、Shell 或 SecretStore。阶段 8 才由 Electron Main/Preload 把该端口接到动态本地端口、临时 Session Token、REST、WebSocket 和 Desktop Control Channel。后端是业务状态唯一权威；Renderer 使用事件驱动读模型，不直接推断审批、Gate、阶段完成、恢复或冲突结果。

**Tech Stack:** Electron、React、TypeScript strict、Vite、Vitest、Testing Library、Playwright、CSS Custom Properties、FastAPI OpenAPI 生成类型。

---

> 对齐基线：`docs/PROJECT-PLAN.md` at `ab0d204c4132a075408b8c2cfe5376a15bdb5a22`
>
> 基线 SHA-256：`E55F6238A2AD4DAA165B20AF7361B0AC591DE4A9838C121537C25F7B7912EC8C`
>
> 状态：已由用户确认并锁定。后续修改新增 v2，不覆盖 v1。

## 0. 对齐基线与执行前硬门禁

当前后端只有 `GET /api/v1/health`、`GET /api/v1/readiness` 和 `GET /api/v1/system/info`。除 S00 和 S09 的基础诊断外，本计划现在不得进入正式业务实现。

开始 Task 1 前必须同时具备：

- 阶段 5 已冻结 REST OpenAPI Schema。
- 阶段 5 已冻结 WebSocket Event Envelope 和事件类型。
- 阶段 5 已冻结 Application Command、Query、Permission 和错误代码。
- 阶段 5 已冻结 Electron Desktop Control Contract。
- 用户已确认 `FRONTEND-DRAFT-MASTER-v1.md` 或更新版本。
- 28 张单页参考图已逐页确认。

任一条件缺失时，停止执行，不创建正式前端业务代码。

### 0.1 阶段顺序

本计划严格遵守：

```text
阶段 6 用户批准草案母版
-> 阶段 7A 开发前端母版
-> 阶段 7B 正式开发前端
-> 阶段 8 Electron/Sidecar/Windows 集成与打包
-> 阶段 9 安装后全产品 E2E 与发布
```

- Task 1-5 属于阶段 7A。
- Task 6-11 属于阶段 7B。
- 本文不执行阶段 8 或阶段 9，只定义交接门禁。
- 阶段 7 不启动后端进程、不持有临时 Token、不实现 SecretStore Bridge、不生成安装包。
- 阶段 8 不得在 Task 11 的阶段 7 门禁通过前开始。

### 0.2 目录解释

`PROJECT-PLAN.md` 第 10 章“新代码只写入 backend/”位于禁止迁移 `agent-orchestrator/` 和 `agent-tools/` 的上下文中。若将其解释为整个仓库永远禁止前端目录，将与阶段 7、阶段 8 的 Electron 交付直接冲突。

本执行文档采用以下唯一可执行解释：

- 后端新代码只写入 `backend/`，不复用 `agent-orchestrator/` 或 `agent-tools/` 形成第二套后端。
- 阶段 7 正式前端代码写入独立 `frontend/`。
- 跨边界共享内容只允许使用阶段 5 冻结的 Schema 和生成类型，不复制后端领域实现。
- 用户锁定 v1 即确认该解释；若不确认，阶段 7 保持阻塞并先修改 `PROJECT-PLAN.md`。

### 0.3 V1 明确非目标

前端不得出现以下入口、页面或隐藏功能：

- 云托管、多用户、团队和组织权限。
- 任意 DAG 工作流编辑器。
- Agent 自动创建角色、插件市场或多机器并行。
- 真实生产环境自动部署、应用商店和计费。
- 产品内 Git 操作、分支、提交、推送或 PR 控件。

未来新增上述能力必须先版本化修改 `PROJECT-PLAN.md`，再重新生成草案母版和执行文档。

### 0.4 PROJECT-PLAN 追踪矩阵

| 规划条款 | 前端执行落点 | 验收证据 |
| --- | --- | --- |
| 1.1 V1 必须包含 | Task 6-11 覆盖项目、五阶段、模型、工具、审批、恢复、诊断 | 页面测试、契约测试、阶段 7 E2E |
| 1.2 V1 不包含 | 0.3 非目标与静态导航清单测试 | `non-goals.test.ts` |
| 2.1 基线风险 | Task 1 检查迁移版本、错误分类、事件元数据；Task 12 交接动态端口/Token/Watchdog | 契约哈希、事件 envelope 测试、阶段 8 交接清单 |
| 3 统一架构 | Task 2 `DesktopPort`、Task 4 API/Event Adapter | 依赖方向测试、Renderer 禁止 Node/Token 测试 |
| 3.1 职责边界 | Renderer 只投影后端状态，不写领域状态、不操作文件/Shell | `authority-boundary.test.ts` |
| 3.2 共享协议内核 | Task 1 只从冻结 Schema 生成 Stage、StageContract、事件和引用类型 | Schema SHA-256、生成类型 diff |
| 4 核心领域与数据 | Task 4 标准化读模型，Task 6-9 按实体边界分 feature | selector 和 projection 测试 |
| 4.1 数据不变量 | Task 4、7、8、9 覆盖不可变消息/产物/交接、Hash、credential_ref、Direct 文件保护 | 不变量参数化测试 |
| 5.1 Workflow 状态 | Task 4 完整状态映射，Task 6 页面呈现 | 12 状态参数化测试 |
| 5.2 StageRun 状态 | Task 4 完整状态映射，Task 7 阶段工作区呈现 | 16 状态参数化测试 |
| 5.3 阶段完成链 | Task 8 按双 Reviewer、Gate、审批、Checkpoint、Artifact、Handoff 顺序投影 | completion-chain E2E |
| 5.4 返工和 Warning | Task 8 覆盖 MANUAL/AUTONOMOUS、返工归属、下游失效 | warning/rewrite 测试 |
| 6.0-6.5 前端设计 | `FRONTEND-DRAFT-MASTER-v1.md` 与 28 张参考图 | 用户批准记录、图像清单 |
| 7 前端开发 | 7A Task 1-5，7B Task 6-11 | 两个独立 PR 和各自门禁报告 |
| 8 桌面集成与打包 | Task 12 只提供交接合同，不在阶段 7 实现 | 阶段 8 输入清单 |
| 9 全产品 E2E | Task 12 定义安装后 Fake Model 验收输入 | 阶段 9 报告，不作为阶段 7 假证据 |
| 7 测试策略 | 测试目录严格分类；Task 11 运行前后端全门禁 | unit/integration/contract/security/process/migration/e2e 报告 |
| 8 安全隐私 | Task 2、4、9、11 覆盖 Token、Secret、外部模型范围、脱敏诊断 | security 测试和诊断包扫描 |
| 9 前端规划规则 | 冻结契约、Change Request、阶段顺序 | PR 模板与版本记录 |
| 10 旧实现关系 | 不读取或迁移旧 UI、agent-orchestrator、agent-tools | staged path 和依赖扫描 |
| 11 PR/版本治理 | 7A/7B 独立 `codex/` 分支与 PR | PR 描述、回滚和审查记录 |
| 12 V1 完成定义 | Task 12 把阶段 7 证据交给阶段 8/9，不提前宣称 V1 完成 | 总需求追踪矩阵 |

## 1. 文件边界

正式实施时创建以下结构：

```text
frontend/
├─ package.json
├─ package-lock.json
├─ tsconfig.json
├─ vite.config.ts
├─ electron/
│  ├─ preload.ts
│  └─ desktop-port.ts
├─ contracts/
│  ├─ openapi.json
│  ├─ events.schema.json
│  └─ capabilities.json
├─ scripts/
│  ├─ generate-api-types.mjs
│  └─ verify-contract-coverage.mjs
├─ src/
│  ├─ app/
│  │  ├─ App.tsx
│  │  ├─ routes.tsx
│  │  └─ app-shell.tsx
│  ├─ api/
│  │  ├─ generated.ts
│  │  ├─ client.ts
│  │  ├─ errors.ts
│  │  └─ transport.ts
│  ├─ events/
│  │  ├─ event-stream.ts
│  │  ├─ event-reducer.ts
│  │  └─ replay-cursor.ts
│  ├─ state/
│  │  ├─ read-model.ts
│  │  ├─ selectors.ts
│  │  └─ command-state.ts
│  ├─ theme/
│  │  ├─ tokens.css
│  │  ├─ theme-provider.tsx
│  │  └─ interaction.css
│  ├─ components/
│  │  ├─ button.tsx
│  │  ├─ status.tsx
│  │  ├─ async-boundary.tsx
│  │  ├─ evidence-panel.tsx
│  │  └─ native-confirm.ts
│  └─ features/
│     ├─ startup/
│     ├─ projects/
│     ├─ preflight/
│     ├─ overview/
│     ├─ stages/
│     ├─ artifacts/
│     ├─ approvals/
│     ├─ recovery/
│     ├─ settings/
│     └─ diagnostics/
└─ tests/
   ├─ unit/
   │  ├─ components/
   │  └─ features/
   ├─ integration/
   ├─ contract/
   ├─ security/
   ├─ process/
   ├─ migration/
   └─ e2e/
      └─ visual/
```

每个 feature 只拥有自己的页面、读模型投影和命令适配；共享领域状态只存在于 `state/` 和生成契约中。

除明确写出 `cd backend` 的命令外，所有 `npm`、TypeScript、Vitest 和 Playwright 命令都从 `frontend/` 执行。依赖安装必须使用 `--save-exact` 并提交 `package-lock.json`；后续 CI 只使用 `npm ci`。

## 2. 页面文件与契约归属

| 页面 | Route | 页面文件 | 后端契约 |
| --- | --- | --- | --- |
| S00 | `/startup` | `src/features/startup/startup-page.tsx` | Health、Readiness、SystemInfo、Recovery |
| S01 | `/projects` | `src/features/projects/projects-page.tsx` | ProjectList/Create/Open |
| S02 | `/projects/:projectId/preflight` | `src/features/preflight/preflight-page.tsx` | ProjectPreflight、WorkflowStart |
| S03 | `/projects/:projectId` | `src/features/overview/project-overview-page.tsx` | ProjectOverview、Workflow、Checkpoint、Conflict |
| S04 | `/projects/:projectId/stages/:stage` | `src/features/stages/stage-workspace-page.tsx` | Room、Message、Task、StageReopen |
| S05 | `/projects/:projectId/artifacts` | `src/features/artifacts/artifacts-page.tsx` | Artifact、Gate、Approval、Handoff、ChangeRequest |
| S06 | `/projects/:projectId/approvals` | `src/features/approvals/approvals-page.tsx` | Approval、CapabilityRequest |
| S07 | `/projects/:projectId/recovery` | `src/features/recovery/recovery-page.tsx` | Conflict、Checkpoint |
| S08 | `/settings` | `src/features/settings/settings-page.tsx` | Settings、ModelProfile、SecretReference |
| S09 | `/diagnostics` | `src/features/diagnostics/diagnostics-page.tsx` | Event、Replay、Diagnostics |

S04 只实现一个页面组件，通过后端 `Stage` 枚举渲染 Planner、Designer、Builder、Reviewer 和 Deployer，禁止复制五套状态逻辑。

## Task 1: 建立契约覆盖门禁

**Files:**

- Create: `frontend/package.json`
- Create: `frontend/package-lock.json`
- Create: `frontend/tsconfig.json`
- Create: `frontend/vite.config.ts`
- Create: `frontend/contracts/openapi.json`
- Create: `frontend/contracts/events.schema.json`
- Create: `frontend/contracts/capabilities.json`
- Create: `frontend/scripts/verify-contract-coverage.mjs`
- Create: `frontend/tests/contract/contract-coverage.test.ts`

- [ ] **Step 1: 建立并锁定前端工具链**

```powershell
New-Item -ItemType Directory -Force frontend | Out-Null
cd frontend
npm init -y
npm install --save-exact react react-dom
npm install --save-dev --save-exact electron vite typescript vitest playwright openapi-typescript eslint @testing-library/react @testing-library/jest-dom
```

`package.json` 必须提供 `lint`、`typecheck`、`test`、`test:visual`、`test:e2e` 和 `build` 脚本。`tsconfig.json` 启用 `strict`、`noUncheckedIndexedAccess`、`exactOptionalPropertyTypes` 和 `useUnknownInCatchVariables`。

- [ ] **Step 2: 从阶段 5 交付物复制冻结契约**

三个文件必须来自后端阶段 5 的已提交构建产物，禁止手写路由或事件类型。复制后记录 SHA-256：

```powershell
Get-FileHash frontend/contracts/openapi.json -Algorithm SHA256
Get-FileHash frontend/contracts/events.schema.json -Algorithm SHA256
Get-FileHash frontend/contracts/capabilities.json -Algorithm SHA256
```

- [ ] **Step 3: 写覆盖失败测试**

```ts
import { describe, expect, it } from "vitest";
import capabilities from "../../contracts/capabilities.json";

const required = [
  "BackendHealthQuery", "RecoveryListQuery", "RecoveryResumeCommand",
  "RecoveryDiscardCommand", "ProjectListQuery", "ProjectCreateCommand",
  "ProjectOpenCommand", "ProjectCloseCommand", "StageViewQuery",
  "ProjectPreflightCommand", "ProjectPreflightQuery", "WorkflowStartCommand",
  "ProjectOverviewQuery", "WorkflowPauseCommand", "WorkflowResumeCommand",
  "WorkflowStopCommand", "WorkflowAbandonCommand", "RoomQuery",
  "RoomHistoryQuery", "MessageSendCommand",
  "TaskCancelCommand", "TaskQueueQuery", "StageReopenCommand", "ArtifactQuery",
  "ArtifactVersionQuery", "QualityGateQuery", "ApprovalDecideCommand",
  "HandoffQuery", "ChangeRequestCreateCommand", "ApprovalQuery",
  "CapabilityRequestQuery",
  "CapabilityDecideCommand", "ConflictQuery", "ConflictResolveCommand",
  "CheckpointListQuery", "CheckpointRestoreCommand", "SettingsQuery",
  "ModelProfileListQuery", "ModelProfileCreateCommand",
  "ModelProfileUpdateCommand", "ModelProfileTestCommand",
  "RoomModelAssignmentCommand", "SecretReferenceCommand", "EventQuery",
  "EventReplayQuery", "DiagnosticsQuery", "DiagnosticsExportCommand"
] as const;

describe("frontend contract coverage", () => {
  it.each(required)("contains %s", (id) => {
    expect(capabilities.capabilities).toHaveProperty(id);
  });
});
```

- [ ] **Step 4: 运行测试并确认缺失契约会失败**

`ProjectCloseCommand` 和 `WorkflowAbandonCommand` 来自 V1 目标与阶段 5 交付语义；如果阶段 5 使用不同 ID，必须先通过版本化 Change Request 修改本清单，前端不得自行别名兼容。

Run: `npm test -- tests/contract/contract-coverage.test.ts`

Expected: 当前阶段 5 交付物缺少任何 ID 时 FAIL，并打印缺失 ID。

- [ ] **Step 5: 生成 TypeScript API 类型**

```js
import fs from "node:fs/promises";
import openapiTS from "openapi-typescript";

const schema = JSON.parse(await fs.readFile("contracts/openapi.json", "utf8"));
const output = await openapiTS(schema);
await fs.writeFile("src/api/generated.ts", output);
```

Run: `node scripts/generate-api-types.mjs`

Expected: `src/api/generated.ts` 被创建，`tsc --noEmit` 通过。

- [ ] **Step 6: 验证共享协议内核完整性**

生成类型必须包含且只能引用阶段 5 冻结定义：`Stage`、Workflow/StageRun 状态、`StageContract`、RoleCard 版本与内容 Hash、Event Envelope、错误代码、命令关联/因果/幂等字段、`ToolExecutionRequest`、`ToolResult`、`CapabilityRequest`、`ProjectCheckpointRef`、`ArtifactRef` 和 API/WebSocket/IPC schema version。

RoleCard 未完成版本/Hash/权限校验、Schema version 不兼容或协议类型重复定义时，构建失败；前端不得手写第二份枚举补过类型错误。

- [ ] **Step 7: 提交**

```powershell
git add frontend/package.json frontend/package-lock.json frontend/tsconfig.json frontend/vite.config.ts frontend/contracts frontend/scripts frontend/tests/contract frontend/src/api/generated.ts
git commit -m "feat(frontend): add frozen backend contract gate"
```

## Task 2: 建立 Renderer 与 Preload 的无 Token 边界

**Files:**

- Create: `frontend/electron/preload.ts`
- Create: `frontend/electron/desktop-port.ts`
- Create: `frontend/src/app/App.tsx`
- Test: `frontend/tests/contract/desktop-port.test.ts`
- Test: `frontend/tests/security/preload-boundary.test.ts`

- [ ] **Step 1: 写 Renderer 不可获得 Token 的安全测试**

```ts
import { expect, it } from "vitest";
import type { DesktopPort } from "../../electron/desktop-port";

it("exposes no session token, filesystem, shell or secret capability", () => {
  const keys: Array<keyof DesktopPort> = [
    "backend", "selectDirectory", "showNativeConfirm",
    "showSystemNotification", "openLocalLocation",
    "getWindowState", "requestWindowClose"
  ];
  expect(keys.join(" ")).not.toMatch(/token|secret|shell|filesystem/i);
});
```

- [ ] **Step 2: 定义只包含业务语义的桌面端口**

```ts
export interface BackendRequest {
  capabilityId: string;
  requestId: string;
  payload: unknown;
}

export interface BackendReply<T = unknown> {
  requestId: string;
  correlationId: string;
  payload: T;
}

export interface PersistedEvent {
  schemaVersion: number;
  sequence: number;
  eventId: string;
  correlationId: string;
  causationId?: string;
  actor: string;
  source: string;
  eventType: string;
  payload: unknown;
}

export interface DesktopPort {
  backend: {
    query<T>(request: BackendRequest): Promise<BackendReply<T>>;
    command(request: BackendRequest): Promise<BackendReply<{ accepted: true }>>;
    subscribe(listener: (event: PersistedEvent) => void): () => void;
    requestReplay(afterSequence: number): Promise<void>;
  };
  selectDirectory(): Promise<{ cancelled: boolean; path?: string }>;
  showNativeConfirm(input: {
    title: string;
    message: string;
    detail: string;
    confirmLabel: string;
  }): Promise<boolean>;
  showSystemNotification(input: { title: string; body: string; recordId: string }): Promise<void>;
  openLocalLocation(path: string): Promise<void>;
  getWindowState(): Promise<{ maximized: boolean; scaleFactor: number }>;
  requestWindowClose(): Promise<{ allowed: boolean }>;
}
```

- [ ] **Step 3: 在阶段 7 只实现可替换的 Preload Adapter**

`preload.ts` 使用 `contextBridge.exposeInMainWorld("desktop", port)` 暴露白名单方法。阶段 7 测试使用内存 `DesktopPort` 驱动 Renderer；阶段 8 才把这些方法接到 Electron Main 的 IPC、动态端口、临时 Token、REST 和 WebSocket。

Preload 不得暴露：

- `baseUrl`、Bearer Token 或 WebSocket Ticket。
- Node `fs`、`child_process`、环境变量或原始 IPC。
- Shell 字符串执行、SecretStore 或任意路径读写。
- 未出现在阶段 5 Desktop Control Contract 中的方法。

- [ ] **Step 4: 验证安全配置和依赖方向**

Run: `npm test -- tests/contract/desktop-port.test.ts tests/security/preload-boundary.test.ts && npm run typecheck`

Expected: PASS；Renderer 只依赖 `DesktopPort` 类型，不依赖 Electron Main、Node builtin、Token 或后端内部模块。阶段 8 创建 BrowserWindow 时必须启用 `contextIsolation` 并禁用 `nodeIntegration`。

- [ ] **Step 5: 提交**

```powershell
git add frontend/electron frontend/src/app frontend/tests/contract frontend/tests/security
git commit -m "feat(frontend): establish tokenless renderer boundary"
```

## Task 3: 实现主题令牌和柔和点击组件

**Files:**

- Create: `frontend/src/theme/tokens.css`
- Create: `frontend/src/theme/interaction.css`
- Create: `frontend/src/theme/theme-provider.tsx`
- Create: `frontend/src/components/button.tsx`
- Test: `frontend/tests/unit/components/button.test.tsx`
- Test: `frontend/tests/e2e/visual/theme.spec.ts`

- [ ] **Step 1: 写按钮状态测试**

```tsx
import { render, screen } from "@testing-library/react";
import { Button } from "../../../src/components/button";

it("keeps a disabled reason", () => {
  render(<Button disabled disabledReason="等待 SettingsQuery">保存设置</Button>);
  expect(screen.getByRole("button", { name: "保存设置" })).toBeDisabled();
  expect(screen.getByText("等待 SettingsQuery")).toBeVisible();
});
```

- [ ] **Step 2: 写令牌**

`tokens.css` 必须逐项实现母版第 5 章色值；不得使用渐变、负字距或基于视口宽度缩放字体。

- [ ] **Step 3: 写点击反馈**

```css
.button {
  transition: background-color 110ms ease, border-color 110ms ease,
    color 110ms ease, box-shadow 90ms ease;
}
.button:active {
  box-shadow: inset 0 1px 3px var(--shadow-pressed);
}
@media (prefers-reduced-motion: reduce) {
  .button { transition-duration: 0.01ms; }
}
```

不得使用 `transform: scale(...)`、弹跳或涟漪。

- [ ] **Step 4: 验证两种主题**

Run: `npm test -- tests/unit/components/button.test.tsx && npm run test:visual -- theme.spec.ts`

Expected: 浅色、深色、键盘焦点、禁用原因和 reduced-motion 全部通过。

- [ ] **Step 5: 提交**

```powershell
git add frontend/src/theme frontend/src/components/button.tsx frontend/tests
git commit -m "feat(frontend): add dual theme and soft interaction system"
```

## Task 4: 建立类型化 API、错误和事件读模型

**Files:**

- Create: `frontend/src/api/client.ts`
- Create: `frontend/src/api/errors.ts`
- Create: `frontend/src/api/transport.ts`
- Create: `frontend/src/events/event-stream.ts`
- Create: `frontend/src/events/event-reducer.ts`
- Create: `frontend/src/events/replay-cursor.ts`
- Create: `frontend/src/state/read-model.ts`
- Create: `frontend/src/state/command-state.ts`
- Create: `frontend/src/state/domain-status.ts`
- Test: `frontend/tests/contract/api-client.test.ts`
- Test: `frontend/tests/contract/status-enums.test.ts`
- Test: `frontend/tests/integration/event-replay.test.ts`
- Test: `frontend/tests/security/local-state.test.ts`

- [ ] **Step 1: 写“请求不等于成功”测试**

```ts
it("does not mark a command complete before its persisted event", async () => {
  const state = createCommandState();
  state.accept({ commandId: "cmd-1", correlationId: "cor-1" });
  expect(state.get("cmd-1")?.phase).toBe("accepted");
  state.applyEvent({ type: "workflow.paused", correlationId: "cor-1", sequence: 41 });
  expect(state.get("cmd-1")?.phase).toBe("confirmed");
});
```

- [ ] **Step 2: 实现统一错误类型**

```ts
export interface PublicApiError {
  code: string;
  message: string;
  retryable: boolean;
  correlationId?: string;
  currentVersion?: string;
  details?: Record<string, unknown>;
}
```

- [ ] **Step 3: 完整映射后端状态枚举**

```ts
export const workflowStates = [
  "created", "preflight_failed", "running", "waiting_user",
  "warning_blocked", "paused", "external_conflict", "interrupted",
  "failed", "stopped", "abandoned", "completed"
] as const;

export const stageRunStates = [
  "locked", "ready", "discussing", "producing", "p2r_reviewing",
  "quality_checking", "waiting_approval", "handoff_ready", "completed",
  "warning_blocked", "needs_fix", "external_conflict", "interrupted",
  "failed", "cancelled", "abandoned"
] as const;
```

测试逐项断言每个枚举都有文案、图标、可访问名称、允许动作来源和错误/恢复呈现；未知值进入协议不兼容页，不回退成 `running`。

- [ ] **Step 4: 实现完整 Event Envelope、去重和重放游标**

读模型验证 `schema_version`、`sequence`、`event_id`、`correlation_id`、`causation_id`、`actor`、`source`、`event_type` 和 `idempotency_key`。只接受 `sequence > lastAppliedSequence` 的事件；重连通过 `DesktopPort.backend.requestReplay()` 使用 Electron Main 持有的 WebSocket Ticket 和游标，不让 Renderer 读取 Ticket，也不按本地时间猜测缺失事件。

- [ ] **Step 5: 限制前端本地状态**

Renderer 本地持久化只允许：

- 未提交输入草稿。
- light/dark 主题和视图密度偏好。
- 窗口内展开/折叠偏好。

加载、命令 accepted 和临时 `model.delta` 只保存在内存。Workflow、StageRun、Task、Approval、Gate、ArtifactVersion、Handoff、Conflict 和 Checkpoint 不得写入本地持久化。

- [ ] **Step 6: 验证认证、分页、幂等、版本冲突和事件恢复**

Run: `npm test -- tests/contract/api-client.test.ts tests/contract/status-enums.test.ts tests/integration/event-replay.test.ts tests/security/local-state.test.ts`

Expected: Renderer 不读取 Token；分页游标不丢失；幂等键随重试复用；版本冲突显示 `currentVersion`；重复事件不重复更新；乱序事件触发重新同步；Outbox 延迟恢复后不丢事件；断线保留命令关联 ID。

- [ ] **Step 7: 提交**

```powershell
git add frontend/src/api frontend/src/events frontend/src/state frontend/tests/contract frontend/tests/integration frontend/tests/security
git commit -m "feat(frontend): add authoritative api and event read model"
```

## Task 5: 实现 Codex 式应用壳和固定设置入口

**Files:**

- Create: `frontend/src/app/app-shell.tsx`
- Create: `frontend/src/app/routes.tsx`
- Create: `frontend/src/components/evidence-panel.tsx`
- Create: `frontend/src/features/settings/settings-page.tsx`
- Test: `frontend/tests/unit/features/app-shell.test.tsx`
- Test: `frontend/tests/unit/features/settings-page.test.tsx`
- Test: `frontend/tests/contract/global-navigation.test.tsx`
- Test: `frontend/tests/security/non-goals.test.tsx`

- [ ] **Step 1: 写固定设置入口测试**

```tsx
it.each(["/projects", "/projects/p1", "/diagnostics"])(
  "shows settings on %s",
  async (route) => {
    renderApp({ route });
    expect(screen.getByRole("link", { name: "设置" })).toBeVisible();
  }
);
```

- [ ] **Step 2: 实现布局**

应用壳必须包含 Windows 菜单栏、276px 左侧导航、右侧圆角主工作区、页面页头、按需证据面板和底部连接状态。不得恢复永久右侧栏。

`PROJECT-PLAN.md` 文字基线把设置列在顶部；用户批准的 Codex 式母版把设置移动到左侧底部。该变化只调整布局位置，不改变“全局始终可见”和 `SettingsQuery -> settings.loaded` 语义。

- [ ] **Step 3: 实现全局交互映射**

| UI | Query/Command | 确认事件 | 失败行为 |
| --- | --- | --- | --- |
| 切换项目 | `ProjectListQuery`、`ProjectOpenCommand` | `project.opened` | 保留当前页和输入草稿 |
| 切换阶段 | `StageViewQuery` | `stage.loaded` | 显示锁定或权限原因 |
| 打开通知 | `EventQuery` | `event.read` | 显示断线和重试状态 |
| 查看设置 | `SettingsQuery` | `settings.loaded` | 显示 capability unavailable |
| 取消任务 | `TaskCancelCommand` | `task.cancelled` / `task.interrupted` | 显示未取消原因 |

Windows 系统通知只包含摘要和 `recordId`，点击后回到应用内对应记录；通知不承载完整审批或危险操作。

- [ ] **Step 4: 实现设置空状态**

当 `SettingsQuery` 不在 capability manifest 中时，页面只显示：显示名称、`system/info`、缺失契约说明和禁用的保存按钮。纯导航不得写入后端状态。

- [ ] **Step 5: 验证非目标和最小窗口**

Run: `npm test -- tests/unit/features/app-shell.test.tsx tests/unit/features/settings-page.test.tsx tests/contract/global-navigation.test.tsx tests/security/non-goals.test.tsx`

Expected: 1440×900 与 1280×720 均无重叠；设置入口始终可见；空状态无假表单；不存在 Git、插件市场、团队、云端、计费、DAG 或真实生产部署导航。

- [ ] **Step 6: 提交**

```powershell
git add frontend/src/app frontend/src/components/evidence-panel.tsx frontend/src/features/settings frontend/tests/unit/features frontend/tests/contract frontend/tests/security
git commit -m "feat(frontend): add desktop shell and truthful settings entry"
```

## 阶段 7A 门禁：开发前端母版

Task 1-5 必须在 `codex/frontend-master-v1` 分支和独立 PR 中完成。该 PR 只交付：

- Renderer/Preload 工程边界和无 Token `DesktopPort`。
- 设计令牌、基础组件、路由和 Codex 式应用壳。
- 类型化契约、API/Event Adapter 和权威读模型。
- 组件、状态、Contract、安全和视觉骨架测试。

阶段 7A 不实现 S01-S09 的可成功业务流程，不连接真实 Electron Main，不启动 Sidecar，不打包。

PR 描述必须列出规划条款、契约 SHA-256、测试命令、已知限制和回滚方式。通过独立审查并合并后，才能从最新 `master` 创建 `codex/frontend-v1` 执行 Task 6-11。

## Task 6: 实现 S00-S03 项目主线

**Files:**

- Create: `frontend/src/features/startup/startup-page.tsx`
- Create: `frontend/src/features/projects/projects-page.tsx`
- Create: `frontend/src/features/preflight/preflight-page.tsx`
- Create: `frontend/src/features/overview/project-overview-page.tsx`
- Test: `frontend/tests/unit/features/startup.test.tsx`
- Test: `frontend/tests/integration/project-flow.test.tsx`
- Test: `frontend/tests/security/workspace-boundary.test.tsx`

- [ ] **Step 1: 先实现 S00 的三个真实接口**

测试 health、readiness 和 system/info 的 loading、ready、503、数据库版本、迁移不兼容、协议不兼容与重试。显示可恢复项目、遗留任务、内容寻址检查点、快照 Hash 和错误证据；`RecoveryResumeCommand` / `RecoveryDiscardCommand` 缺失时对应控件禁用。

- [ ] **Step 2: 实现项目创建到预检链路**

实现创建、打开、关闭和恢复；创建表单覆盖项目名称、目标、本地目录、Managed/Direct。`ProjectCreateCommand` 成功后必须进入 `ProjectPreflightCommand`；禁止直接显示“项目可运行”。`ProjectCloseCommand` 只关闭项目上下文，不删除用户文件。

路径非法、重复、权限不足、目录不可读、项目外路径、符号链接逃逸和 Manifest 非规范相对路径全部显示后端错误。Direct Workspace 的 stop、abandon、关闭、卸载提示和恢复都不得暗示会删除用户文件。

- [ ] **Step 3: 实现预检门禁**

页面显示目录边界、Manifest、依赖文件、构建、测试、类型检查和外部冲突证据。PASS 可开始；允许的 WARNING 需要用户确认；NEEDS_FIX 和 FAIL 不渲染可绕过按钮。

- [ ] **Step 4: 实现项目主页事件投影**

工作流、阶段、任务、外部变化和待处理数量只从查询结果及 `workflow.*`、`stage.*`、`task.*`、`external_change.*` 持久化事件更新。开始、继续、暂停、停止和放弃严格使用后端允许动作；停止和放弃显示影响范围并走原生确认。

- [ ] **Step 5: 运行主线测试并提交**

Run: `npm test -- tests/unit/features/startup.test.tsx tests/integration/project-flow.test.tsx tests/security/workspace-boundary.test.tsx`

```powershell
git add frontend/src/features/startup frontend/src/features/projects frontend/src/features/preflight frontend/src/features/overview frontend/tests/unit/features frontend/tests/integration frontend/tests/security
git commit -m "feat(frontend): implement startup and project workflow pages"
```

## Task 7: 实现 S04 五阶段工作区

**Files:**

- Create: `frontend/src/features/stages/stage-workspace-page.tsx`
- Create: `frontend/src/features/stages/stage-copy.ts`
- Create: `frontend/src/features/stages/message-stream.tsx`
- Create: `frontend/src/features/stages/task-queue.tsx`
- Create: `frontend/src/features/stages/tool-progress.tsx`
- Create: `frontend/src/features/stages/stage-context.tsx`
- Test: `frontend/tests/integration/stage-workspace.test.tsx`
- Test: `frontend/tests/integration/room-isolation.test.tsx`
- Test: `frontend/tests/security/stage-permissions.test.tsx`

- [ ] **Step 1: 写五阶段参数化测试**

```tsx
it.each(["planner", "designer", "builder", "reviewer", "deployer"] as const)(
  "renders %s from the backend Stage enum",
  (stage) => {
    renderStage({ stage });
    expect(screen.getByTestId("stage-workspace")).toHaveAttribute("data-stage", stage);
  }
);
```

- [ ] **Step 2: 区分临时流和持久化消息**

`model.delta` 只进入临时区域；只有 `message.created` 进入历史并标记用户消息已发送。

- [ ] **Step 3: 实现不可变消息、更正和聊天室隔离**

消息不提供编辑或删除。更正通过后端命令创建引用原消息的新记录；误贴凭据只走受控脱敏和安全事件。五阶段 Room、摘要、决策和上下文互相隔离，切换阶段必须重新执行 `StageViewQuery` / `RoomQuery`。

- [ ] **Step 4: 完整呈现阶段上下文**

每个阶段都显示：目标、当前状态、后端允许动作、上游 Handoff、Prompt/上下文范围、Rolling Summary、消息、任务队列、受控工具进度、正式产出、Gate、审批、模型调用与用量、输入区。

- Planner：目标、用户、场景、需求、范围、非目标、验收、风险、开放问题、决策。
- Designer：架构、模块、数据、API、事件、错误、安全、技术约束、构建任务。
- Builder：实现范围、文件、测试、构建结果、限制、偏差、剩余问题。
- Reviewer：审查范围、证据、阻断/重要问题、建议、结论和返工目标。
- Deployer：版本、环境、前置条件、配置、安装、启动、停止、健康检查、日志、回滚、已知问题。

工具卡只呈现 Backend 已鉴权的 File/Search/Shell/Build/Test 请求、进度、结果和 ToolCall 审计 ID；Renderer 不直接执行工具。

- [ ] **Step 5: 实现取消、超时、重试和完成后只读**

取消后等待 `task.cancelled` 或 `task.interrupted`；超时和模型局部失败保留输入、调用 ID、用量与后端允许的重试动作。已完成阶段允许只读咨询但不能修改正式记录；修改必须调用 `StageReopenCommand`，并显示被重新打开后将失效的下游引用。

- [ ] **Step 6: 验证 StageContract 权限和队列**

Run: `npm test -- tests/integration/stage-workspace.test.tsx tests/integration/room-isolation.test.tsx tests/security/stage-permissions.test.tsx`

Expected: 五阶段只显示 RoleCard/StageContract 允许动作；活跃任务期间新消息显示队列位置；取消排队和任务取消等待后端事件；完成后咨询与 reopen 使用不同入口。

- [ ] **Step 7: 提交**

```powershell
git add frontend/src/features/stages frontend/tests/integration frontend/tests/security
git commit -m "feat(frontend): implement five-stage workspace"
```

## Task 8: 实现 S05-S07 门禁、审批、冲突和恢复

**Files:**

- Create: `frontend/src/features/artifacts/artifacts-page.tsx`
- Create: `frontend/src/features/approvals/approvals-page.tsx`
- Create: `frontend/src/features/recovery/recovery-page.tsx`
- Create: `frontend/src/components/native-confirm.ts`
- Test: `frontend/tests/integration/governance.test.tsx`
- Test: `frontend/tests/integration/recovery.test.tsx`
- Test: `frontend/tests/integration/completion-chain.test.tsx`
- Test: `frontend/tests/integration/warning-policy.test.tsx`

- [ ] **Step 1: 实现不可变 ArtifactVersion 与 Gate 证据**

前端不提供覆盖版本；ArtifactVersion 和 HandoffPacket 只读且不可变。引用文件 Hash 改变时显示后端失效事件和替代版本，不在本地改写。正式版本的时间按后端 UTC 时间显示为本地时区，但保留原始 UTC 值用于复制和审计。

- [ ] **Step 2: 严格投影阶段完成链**

界面按以下后端事件顺序显示：草案 -> Reviewer A/B -> 确定性 Quality Gate -> MANUAL 审批或 AUTONOMOUS 策略 -> Checkpoint -> ArtifactVersion 锁定 -> HandoffPacket -> 同事务状态/EventLog/Outbox -> 下一阶段解锁。

正式 P2 缺少任一 Reviewer 有效结果时不显示可交付状态。只有后端同一事务提交状态、EventLog 和 Outbox 后，Renderer 才更新完成链。任何一步 accepted 都不等于 completed；刷新、断线和重放后必须得到相同结果。

- [ ] **Step 3: 实现 MANUAL/AUTONOMOUS、Warning 和返工规则**

- MANUAL WARNING：只显示批准或要求重写。
- AUTONOMOUS WARNING：显示 `warning_blocked`，只允许后端返回的 rewrite、open_room 或 abandon。
- NEEDS_FIX / FAIL：阻断交接并显示结构化返工目标。
- 返工次数不设前端上限，每次显示原因、输入版本、产物版本和 Gate 结果。
- Planner 问题回 Planner；设计/API/数据回 Designer；代码/测试/构建回 Builder；部署资料留 Deployer。
- 上游重新运行时，明确显示目标阶段和全部下游 Handoff、Artifact 引用与结果失效，历史记录仍可审计。

- [ ] **Step 4: 实现能力申请限制**

永久禁止能力、过期任务和未授权路径不显示批准入口；决定必须关联 `approval.decided` 或 `capability.decided`。

- [ ] **Step 5: 实现冲突三方比较**

同时展示基线、用户版本、Agent 版本、最早受影响阶段、失效产出物和下游阶段。

- [ ] **Step 6: 实现原生恢复确认**

恢复前通过 `DesktopPort.showNativeConfirm()` 显示失效范围和保护检查点；取消确认不得发送 `CheckpointRestoreCommand`。解决冲突后等待 `file_conflict.resolved` 和重新 Gate，不直接刷新成完成。恢复失败保留检查点、错误证据、关联 ID 和可重试动作。

- [ ] **Step 7: 运行治理与恢复测试**

Run: `npm test -- tests/integration/governance.test.tsx tests/integration/recovery.test.tsx tests/integration/completion-chain.test.tsx tests/integration/warning-policy.test.tsx`

Expected: 两种审批模式、双 Reviewer、Warning/NEEDS_FIX/FAIL、返工归属、Hash 失效、三方冲突、确认取消和恢复失败全部由后端事件驱动。

- [ ] **Step 8: 提交**

```powershell
git add frontend/src/features/artifacts frontend/src/features/approvals frontend/src/features/recovery frontend/src/components/native-confirm.ts frontend/tests/integration
git commit -m "feat(frontend): implement governance conflict and recovery pages"
```

## Task 9: 完成 S08 设置和 S09 诊断

**Files:**

- Modify: `frontend/src/features/settings/settings-page.tsx`
- Create: `frontend/src/features/diagnostics/diagnostics-page.tsx`
- Test: `frontend/tests/integration/settings-contract.test.tsx`
- Test: `frontend/tests/integration/diagnostics.test.tsx`
- Test: `frontend/tests/security/model-data-scope.test.tsx`
- Test: `frontend/tests/security/diagnostics-redaction.test.tsx`

- [ ] **Step 1: 契约存在后启用设置能力**

展示模型名称、Provider、模型 ID、能力探测、Primary/Reviewer A/Reviewer B 槽位、`credential_ref` 脱敏提示、最近调用状态和用量。支持 OpenAI 兼容与 Anthropic 仅来自后端 ModelProfile 枚举；模型槽位只能使用后端允许分配。

创建、更新、测试和槽位分配分别调用 `ModelProfileCreateCommand`、`ModelProfileUpdateCommand`、`ModelProfileTestCommand` 和 `RoomModelAssignmentCommand`。只有收到后端确认事件后显示成功。

- [ ] **Step 2: 实现 Provider 与数据范围确认**

发送外部模型前明确显示 Provider、项目、阶段和数据范围；被 ProjectManifest 排除的敏感路径不显示为可发送内容。项目文件、聊天和模型输出按不可信内容呈现，不得扩大 Agent 权限。

Renderer 只显示 `credential_ref` 和 `masked_hint`；API Key 明文不得进入 Renderer 状态、Prompt 预览、日志、事件、数据库或诊断包。

- [ ] **Step 3: 实现完整事件、工具审计和诊断**

S09 显示时间、事件类型、项目、工作流、阶段、任务、来源、结果、关联/因果事件，以及 ToolCall 审计。诊断摘要包含星协版本、后端版本、数据库版本、Worker/Tool 进程、最近错误、恢复记录、进程状态和脱敏日志。

- [ ] **Step 4: 实现诊断导出确认**

导出前展示包含项和排除项；默认排除源码、完整聊天和密钥。

- [ ] **Step 5: 验证接口不可用和保留策略状态**

Settings、SecretStore、Worker、Tool 或 Diagnostics 不可用时，页面显示后端错误和恢复路径，不伪造保存与导出。SQLite、快照、日志和事件的大小、保留与清理只展示后端配置；仍被正式产物引用的数据必须显示受保护且不可清理。

- [ ] **Step 6: 运行模型与诊断安全测试**

Run: `npm test -- tests/integration/settings-contract.test.tsx tests/integration/diagnostics.test.tsx tests/security/model-data-scope.test.tsx tests/security/diagnostics-redaction.test.tsx`

Expected: Provider/范围明确；双 Reviewer 槽位规则正确；密钥、源码和完整聊天不进入诊断包；事件、ToolCall 和恢复记录可按关联 ID 追踪。

- [ ] **Step 7: 提交**

```powershell
git add frontend/src/features/settings frontend/src/features/diagnostics frontend/tests/integration frontend/tests/security
git commit -m "feat(frontend): complete settings and diagnostics pages"
```

## Task 10: 完成 28 张参考图视觉回归

**Files:**

- Create: `frontend/tests/e2e/visual/pages.spec.ts`
- Create: `frontend/tests/e2e/visual/reference-manifest.ts`
- Reference: `docs/frontend/reference-images/v1/*.png`

- [ ] **Step 1: 建立参考图清单**

清单必须包含 14 个视图的 light/dark 组合，共 28 项；缺少任一项测试直接失败。

- [ ] **Step 2: 在固定环境截图**

```ts
test.use({ viewport: { width: 1440, height: 900 }, colorScheme: "light" });
```

深色用例显式切换主题。关闭动画，等待字体、查询和事件读模型稳定后截图。

- [ ] **Step 3: 运行视觉回归**

Run: `npm run test:visual`

Expected: 28 个用例全部通过；差异必须由新母版版本批准，不能直接更新基线掩盖回归。

- [ ] **Step 4: 提交**

```powershell
git add frontend/tests/e2e/visual
git commit -m "test(frontend): cover all master pages with visual regression"
```

## Task 11: 完成正式前端、可访问性和阶段 7 端到端验收

**Files:**

- Create: `frontend/tests/e2e/five-stage-flow.spec.ts`
- Create: `frontend/tests/e2e/reconnect-replay.spec.ts`
- Create: `frontend/tests/e2e/recovery.spec.ts`
- Create: `frontend/tests/e2e/accessibility.spec.ts`
- Create: `frontend/tests/security/dead-controls.test.ts`
- Create: `frontend/tests/process/renderer-lifecycle-contract.test.ts`
- Create: `frontend/tests/migration/view-preferences.test.ts`

- [ ] **Step 1: 使用阶段 5 Fake Model 跑完整五阶段流**

使用阶段 5 Fake Model 后端和测试 `DesktopPort` 覆盖创建、打开、关闭、恢复、预检、Planner、Designer、Builder、Reviewer、Deployer、Gate、MANUAL/AUTONOMOUS、审批、交接和最终只读。测试端口在测试进程中持有认证，Token 不注入页面。

- [ ] **Step 2: 覆盖异常主线**

覆盖断线重放、Ticket 过期、重复/乱序事件、Outbox 延迟恢复、命令幂等、版本冲突、模型局部失败、命令超时、任务取消、Warning、返工、能力拒绝、工具越权、外部冲突、数据库不可用和检查点恢复。

- [ ] **Step 3: 覆盖 Renderer 尺寸、缩放和偏好迁移**

验证 1280×720、1440×900、1920×1080，以及 100%、125%、150%、175%、200% DPI 模拟。验证主题、密度和折叠偏好的版本迁移；不把 Workflow、Stage、Task 或审批状态写入偏好存储。

跨显示器移动、最小化、恢复、重启和真实 DPI 切换属于阶段 8 Electron 集成，记录到 Task 12 交接清单，不在阶段 7 宣称通过。

- [ ] **Step 4: 覆盖键盘与可访问性**

所有核心流程仅用键盘可完成；焦点顺序、焦点环、名称、错误关联、对比度和 reduced-motion 通过检查。

- [ ] **Step 5: 逐控件检查后端耦合**

从路由和组件树导出所有 button、link、menuitem、表单提交和快捷操作。每一项必须在 `capabilities.json` 中映射 Query/Command/Event/Permission/Error，或被标记为不改变业务状态的纯前端视图导航。发现无映射可用控件，测试失败。

- [ ] **Step 6: 运行阶段 7 完整门禁**

```powershell
npm run lint
npm run typecheck
npm test
npm run test:visual
npm run test:e2e
```

同时从仓库根目录运行后端门禁：

```powershell
cd backend
uv run ruff format --check .
uv run ruff check .
uv run mypy src
uv run pytest
```

Expected: 全部退出码为 0；生产 Renderer 不包含 Mock 成功、假数据提交、未接线业务按钮、未批准接口、Token、Node builtin 或 Secret 明文。

- [ ] **Step 7: 提交**

```powershell
git add frontend/tests/e2e
git commit -m "test(frontend): verify renderer workflow and recovery end to end"
```

## 阶段 7B 门禁：正式开发前端

Task 6-11 必须在 `codex/frontend-v1` 独立 PR 中完成。只有以下证据齐全才能合并：

- S00-S09 全页面、全部状态和异常路径。
- 28 张参考图视觉回归。
- 前后端功能矩阵无死控件。
- REST、Event、错误、分页、认证代理、幂等、版本冲突和恢复测试。
- 键盘、可访问性、窗口尺寸和 DPI 模拟。
- 后端既有门禁无回归。

合并阶段 7B 只表示正式前端完成，不表示 Electron 集成、安装包或 V1 完成。

## Task 12: 生成阶段 8/9 交接包，不在阶段 7 实现桌面集成

**Files:**

- Create: `docs/frontend/STAGE-8-DESKTOP-HANDOFF-v1.md`
- Produce: `frontend/dist/renderer/`
- Produce: `frontend/dist/contracts/desktop-port.d.ts`
- Reference: `docs/PROJECT-PLAN.md` 阶段 8、阶段 9

- [ ] **Step 1: 冻结 Renderer 交付物**

记录构建 Hash、OpenAPI/Event/Capability Hash、设计母版版本、测试报告、浏览器资源清单和 CSP。Renderer 构建不得包含 Token、Secret、后端 Python、Node builtin 或测试 Fake 数据。

- [ ] **Step 2: 明确阶段 8 集成责任**

交接文档逐项要求阶段 8 实现：Electron Main/Preload 真实适配、Sidecar Ready/Shutdown、后端只监听 `127.0.0.1` 的动态端口、临时 Token 生成/轮换/退出失效、WebSocket Ticket、SecretStore Bridge、后端/Worker 进程生命周期、诊断导出、固定 Python 3.12 onedir、安装器、升级前备份和恢复模式。

- [ ] **Step 3: 明确阶段 8 Windows 门禁**

阶段 8 必须在 Windows Runner 验证无系统 Python、中文和空格路径、动态端口、安装/卸载、跨显示器与 DPI、最小化/恢复/重启、父进程消失、Worker/Tool 强杀、无残留进程、升级失败恢复和密钥不泄漏。

- [ ] **Step 4: 明确阶段 9 安装后 E2E**

使用安装后的真实桌面程序和 Fake Model，让真实小项目从 Planner 到 Deployer，覆盖 Manual、Autonomous、返工、审批、冲突、重启、恢复、前端展示和交付资料。真实模型只做手工验收，不进入 CI 稳定性基础。

- [ ] **Step 5: 生成总需求追踪矩阵**

每个 `PROJECT-PLAN.md` V1 条款必须关联界面、代码、测试和证据。只有阶段 0-9 全部门禁通过、零已知 P0/P1、CI 全绿，才能宣称 V1 完成。

- [ ] **Step 6: 提交交接包**

```powershell
git add docs/frontend/STAGE-8-DESKTOP-HANDOFF-v1.md frontend/dist/contracts
git commit -m "docs(frontend): hand off renderer to desktop integration"
```

## 3. 阶段 7 正式验收证据

正式前端完成时必须附带：

- 28 张视觉回归结果和差异报告。
- 前后端功能矩阵，覆盖每个按钮、菜单、表单、快捷操作和导航。
- OpenAPI、Event Schema、Capability Manifest 的 SHA-256。
- REST 契约、DesktopPort、WebSocket 代理、重连重放、事件去重和错误映射测试结果。
- Workflow 12 状态和 StageRun 16 状态的完整呈现测试。
- 不可变消息/Artifact/Handoff、完成链、Manual/Autonomous、Warning、返工和下游失效测试。
- Provider 数据范围、Secret、诊断脱敏和非目标入口扫描。
- 1280×720 和 1440×900 的浅色/深色截图。
- Renderer DPI 模拟、键盘、屏幕阅读器和 reduced-motion 验收结果。
- Fake Model 五阶段端到端报告。
- 无死控件、无假弹窗、无 Mock 成功、无未批准接口的静态检查结果。
- 阶段 8/9 明确未完成项和交接文档。

## 4. 变更规则

- 参考图微调：新增 `FRONTEND-DRAFT-MASTER-v2.md` 和 `reference-images/v2/`，保留已锁定的 v1。
- 后端契约变化：更新冻结契约文件、SHA-256 和契约测试，不在组件内兼容猜测字段。
- 新页面或新业务动作：必须先进入 `PROJECT-PLAN.md` 和后端阶段契约，再进入前端母版。
- 正式实现不得直接覆盖本执行文档；修改时新增 `FRONTEND-IMPLEMENTATION-EXECUTION-v2.md`。
- 重要协议变化必须增加 schema version、迁移器、兼容测试、Change Request 和回滚说明。
- 阶段 7A、7B、8、9 使用独立 `codex/` 分支和独立 PR；已合并分支不继续承载新能力。

## 5. v1 锁定历史

| 版本 | 日期 | 变更 |
| --- | --- | --- |
| v1 | 2026-07-14 | 用户锁定版。对齐 `PROJECT-PLAN.md` 全文；移除 Renderer Token；拆分阶段 7A/7B/8/9；补齐状态机、不变量、安全、模型、工具、恢复、测试目录和治理矩阵。 |
