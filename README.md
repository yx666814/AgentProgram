# 星协（XingXie）

> 面向本地软件交付的契约驱动、多 Agent、可恢复工作流桌面平台。

星协不是一个“让模型自由发挥”的聊天窗口，也不是把几个 API 串起来的演示项目。它把软件交付拆成可验证、可审批、可审计、可恢复的五个阶段，让 Agent 的每一次行动都落在明确的权限、文件、产物和状态边界内。

```text
Planner -> Designer -> Builder -> Reviewer -> Deployer
```

## 为什么星协不一样

- **五阶段交付链**：需求、设计、实现、审查、交付各自拥有独立上下文、阶段契约和完成条件。
- **后端是真正的状态权威**：前端不猜状态、不补成功、不伪造产物；页面只呈现后端已经确认的工作流、任务、事件、Gate 和交接结果。
- **一主双校（P2R）**：Primary Agent 负责推进，Reviewer A/B 负责交叉审查，减少单一模型把错误一路传递到交付环节的风险。
- **产物不可悄悄覆盖**：ArtifactVersion、Quality Gate、Approval、Checkpoint、HandoffPacket 和 ChangeRequest 组成可追踪的交付证据链。
- **安全边界是系统能力，不是提示词约定**：StageContract、CapabilityRequest、PathGuard、工具授权、文件 Hash、进程树清理和 ToolCall 审计共同限制 Agent 能做什么。
- **失败优先设计**：支持取消、超时、失败重跑、外部文件冲突、Worker 异常退出、应用重启恢复、事件重放和断线恢复。
- **真实桌面产品闭环**：Electron Renderer、Preload 安全桥、动态本地端口、Sidecar、SecretStore、Windows 安装器和安装后五阶段 E2E 都属于交付范围。

## 工作流不是黑盒

每个阶段都经过同一条可观察链路：

```text
用户目标
   ↓
StageRun / Task
   ↓
Primary Agent + Reviewer A/B
   ↓
受控 ToolCall（文件、搜索、Shell、Build、Test）
   ↓
ArtifactVersion + Quality Gate
   ↓
Approval / Policy
   ↓
Checkpoint + HandoffPacket
   ↓
下一阶段或可审计的返工路径
```

系统不会因为某个按钮被点击、某段文本看起来像成功，就把阶段标记为完成。完成状态必须来自后端持久化状态和对应证据。

## 技术架构

```text
┌─────────────────────────────────────────────────────────────┐
│ Windows Desktop                                             │
│  Electron Renderer → typed Preload Bridge → Electron Main   │
└──────────────────────────────┬──────────────────────────────┘
                               │ REST / Events / Control IPC
                               ▼
┌─────────────────────────────────────────────────────────────┐
│ Backend Main Process                                        │
│ API · Orchestrator · SQLite · EventLog/Outbox · Policy       │
│ Workspace/Checkpoint · Tool Supervisor · Worker Supervisor   │
└──────────────────────────────┬──────────────────────────────┘
                               │ framed IPC v1
                               ▼
┌─────────────────────────────────────────────────────────────┐
│ Project Worker                                               │
│ Agent Runtime · Prompt/Context · Model Adapters · P2R        │
└─────────────────────────────────────────────────────────────┘
```

核心原则是：数据库、工作流、权限、文件和工具状态由 Backend 统一负责；Renderer 不直接获得 Token、文件系统、Shell 或 SecretStore 能力。

## 已覆盖的能力

### 交付编排

- Planner、Designer、Builder、Reviewer、Deployer 五阶段固定流程
- Manual 与 Autonomous 两种运行模式
- 阶段暂停、继续、停止、放弃、返工和 Warning 阻断恢复
- OpenAI Compatible 与 Anthropic 模型适配边界
- Prompt、上下文、滚动摘要、流式输出、取消、超时、重试和用量记录

### 可信产物

- Managed Workspace 与 Direct Workspace
- ProjectManifest、目录边界和外部文件变化检测
- 内容寻址 Checkpoint 与三方冲突记录
- 不可变 ArtifactVersion 和 HandoffPacket
- Quality Gate、Approval/Policy、ChangeRequest 全链路追踪

### 安全与恢复

- StageContract 和 CapabilityRequest 权限模型
- PathGuard 路径沙箱与文件 Hash 校验
- 受控 Shell、Build、Test、Search 和文件工具
- ToolCall 审计、进程树清理和 Windows Job Object 边界
- 本地 Bearer Session、动态端口、DPAPI-backed SecretStore
- EventLog、Outbox、断线重放、取消和重启恢复
- API Key 不进入数据库、日志、事件、诊断包或截图

## 项目状态

当前目标是 Windows-first、单用户、本地运行的 V1 桌面产品。RC1 已完成自动编排、正式前端、Electron 桌面集成、Windows NSIS 安装器和安装版产品闭环；真实模型服务、物理桌面矩阵和正式分发仍按发布清单进行人工验收。

已完成的自动化验证包括：

```text
Backend：733 passed, 12 skipped
Frontend：39 test files, 75 tests passed
Playwright：58 E2E passed
Installed product：1 complete install/uninstall/reinstall E2E passed
Contracts：69 REST operations, 41 events, 5 StageContracts, 23 tools
```

## 快速开始

### 后端开发环境

要求：Windows、Python 3.12、[uv](https://docs.astral.sh/uv/)。

```powershell
cd backend
uv sync --group dev

$env:AGENT_PLATFORM_SESSION_TOKEN = "change-me-for-local-development"
$env:AGENT_PLATFORM_DATA_ROOT = "$env:LOCALAPPDATA\AgentProgram"

uv run alembic upgrade head
uv run uvicorn agent_platform.bootstrap.app_factory:dev_app --factory
```

### 桌面前端

```powershell
cd frontend
npm ci
npm run desktop:start
```

构建 Windows 安装器：

```powershell
npm run build:package
```

### 验证

```powershell
# backend
cd backend
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy src

# frontend
cd ..\frontend
npm run contracts:verify
npm run lint
npm run typecheck
npm run test
npm run test:e2e
npm run test:product
```

## 设计与工程文档

- [总体实施规划](docs/PROJECT-PLAN.md)
- [前端正式执行文档](docs/frontend/FRONTEND-IMPLEMENTATION-EXECUTION-v1.md)
- [前端设计母版](docs/frontend/FRONTEND-DRAFT-MASTER-v1.md)
- [角色卡与阶段职责](docs/roles/README.md)
- [后端开发说明](backend/README.md)

## 产品边界

星协 V1 专注于本地、单用户、Windows 桌面交付编排，不包含云端托管、多用户组织权限、任意 DAG 编辑器、Agent 自创角色市场、多机器并行或产品内 Git 操作。这些边界是为了保持状态、权限、恢复和审计的确定性，而不是功能缺失。

## 安全提醒

开发环境中的 Session Token 只是占位值，部署或分发前必须替换。不要把真实 API Key 写入命令历史、配置文件、Issue、日志或截图；模型凭证应通过桌面 SecretStore 和 `credential_ref` 流程管理。

---

星协的目标很简单：让 Agent 不只是“能生成代码”，而是能在明确的工程规则里，留下可验证的过程、可恢复的状态和可交付的结果。
