# Backend MVP Implementation Roadmap

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement each plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 以可独立验证的阶段逐步实现 Windows 桌面版五阶段多 Agent 后端，避免一次性重写旧原型。

**Architecture:** 在仓库中新建 `backend/`，采用 Python 3.12 模块化单体主进程、SQLite 单写者、每活动项目一个 Project Worker、主进程统一工具执行。旧 `agent-orchestrator/` 只作为参考，完成新链路验证前不删除。

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2.x, aiosqlite, Alembic, asyncio, structlog, pytest, Ruff, mypy, uv.

---

## 实施原则

- 每个阶段拥有独立计划、测试和提交序列。
- 严格 TDD：失败测试 → 最小实现 → 通过 → 提交。
- 新代码写入 `backend/`，不继续扩大旧版 `engine.py`、`rest.py` 和 `persistence.py`。
- 每个阶段结束必须得到可启动、可测试的工作软件。
- 不在 Foundation 阶段提前实现模型、工具或完整工作流。
- 不在 MVP 中实现 Web 在线版、插件、PostgreSQL、Redis、真实部署和多用户。

## Plan 1：Backend Foundation

文档：[Backend Foundation](2026-07-11-backend-foundation.md)

交付：

- Python 3.12/uv 项目。
- Settings、应用目录和结构化日志。
- SQLite/Alembic。
- EventLog/Outbox 与 UnitOfWork。
- FastAPI App Factory、本地认证、health/readiness。
- 长度帧 IPC。
- 最小 Worker Supervisor、心跳与关闭。

验收：`uv run pytest`、Ruff、mypy 全部通过，FastAPI 可以启动并拉起/关闭最小 Worker。

## Plan 2：Projects, Workspaces and Checkpoints

文档：[Projects, Workspaces and Checkpoints](2026-07-11-project-workspace-checkpoints.md)

交付：

- Project/Workspace/ProjectManifest。
- Managed 与 Direct Workspace。
- `.agent/` 元数据。
- Project Preflight Gate。
- `.agentignore`。
- 内容寻址增量快照、Manifest、恢复。
- watchfiles 外部修改记录。
- FileConflict 三方版本。

验收：新项目、健康已有项目、无测试项目、失败已有项目、外部修改和恢复场景通过。

## Plan 3：Workflow, Rooms and Persistent Chat

文档：[Workflow, Rooms and Persistent Chat](2026-07-11-workflow-rooms-chat.md)

交付：

- Workflow/StageRun/Room 状态机。
- 固定五阶段与聊天室锁定。
- MANUAL/AUTONOMOUS。
- Message 不可变、更正、Pin、Hide。
- 单活动 Primary Task 与消息队列。
- 完成后咨询、显式 Reopen。
- REST 与 WebSocket Event Replay。

验收：状态转换、并发启动、消息不可篡改、断线重放和重开失效测试通过。

## Plan 4：Model Profiles and Agent Runtime

文档：[Model Profiles and Agent Runtime](2026-07-11-models-agent-runtime.md)

交付：

- 全局 ModelProfile 与独立 credential_ref。
- OpenAI Compatible 与 Anthropic Adapter。
- 模型能力探测和用量记录。
- RoleCard/StageContract Prompt 组合。
- Context Builder 与 Rolling Summary。
- P0/P1/P2R。
- Primary 工具请求、Reviewer 无工具。
- 流式消息、取消和技术错误分类。

验收：Fake Model 可稳定验证一主双校、上下文隔离、独立密钥和取消。

## Plan 5：Tool Security and Capability Requests

文档：[Tool Security and Capability Requests](2026-07-11-tool-security.md)

交付：

- Tool Catalog 和 Tool Policy Engine。
- 主进程工具执行。
- 文件路径、Windows junction/symlink 防逃逸。
- Shell/Git/Build/Test Tool Process。
- CapabilityRequest 弹窗状态流。
- planned write、外部冲突、进程树清理和审计。

验收：Shell 不能绕过阶段权限，Reviewer 无工具，项目外路径和注入测试通过。

## Plan 6：Stage Contracts, Gates and Handoffs

文档：[Stage Contracts, Gates and Handoffs](2026-07-11-stage-gates-handoffs.md)

交付：

- 五个 StageContract 的 Pydantic 定义。
- Planner/Designer/Builder/Reviewer/Deployer Gate。
- StageDeliverable 与 ProjectCheckpointRef。
- HandoffPacket。
- ChangeRequest 与下游失效。
- Warning Blocked、Rewrite、Abandon。
- MANUAL 阶段审批。

验收：完整 Fake Workflow 可以从 Planner 走到 Deployer，并覆盖返工和 Warning 场景。

## Plan 7：Recovery, Desktop Contract and E2E

文档：[Recovery, Desktop Contract and E2E](2026-07-11-recovery-desktop-e2e.md)

交付：

- Worker crash、Tool crash、异常退出恢复。
- Pause/Resume/Stop/Abandon。
- Outbox 恢复。
- Electron Sidecar ready/control 协议。
- SecretStore Port。
- PyInstaller onedir 配置。
- Windows 进程树和动态端口。
- 桌面应用驱动一个完整 Web 全栈示例项目的五阶段 E2E；Web 只是被开发的示例项目类型，不是本产品的在线 Web 端。

验收：安装包环境中无需系统 Python，重启恢复、无残留进程、无密钥泄漏，五阶段 E2E 通过。

## 完成顺序

```text
Foundation
→ Workspace/Checkpoint
→ Workflow/Chat
→ Model Runtime
→ Tool Security
→ Gates/Handoffs
→ Recovery/Desktop/E2E
```

后续计划不能跳过上游验收。每份详细计划生成前重新核对 00-15 规格和角色卡。

## 规格覆盖矩阵

| 规格 | 主要实施计划 |
|---|---|
| 06 阶段契约 | Stage Contracts, Gates and Handoffs |
| 07 交接协议 | Stage Contracts, Gates and Handoffs；Workflow, Rooms and Persistent Chat |
| 08 后端架构 | Backend Foundation；Model Profiles and Agent Runtime；Tool Security |
| 09 数据模型 | Foundation 以及各业务计划对应迁移任务 |
| 10 API 与事件 | Projects；Workflow；Models；Tools；Gates；Recovery |
| 11 Agent Runtime | Model Profiles and Agent Runtime |
| 12 工具安全 | Tool Security and Capability Requests；Projects/Checkpoints |
| 13 恢复机制 | Workflow, Rooms and Persistent Chat；Recovery, Desktop Contract and E2E |
| 14 桌面集成 | Backend Foundation；Recovery, Desktop Contract and E2E |
| 15 测试策略 | 每份计划的 TDD 任务与最终 Windows E2E |
