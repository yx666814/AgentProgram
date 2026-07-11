# 后端总体架构

## 1. 目标

后端服务于 Windows-first 单用户桌面应用，负责五阶段工作流、隔离聊天室、多模型协作、项目文件操作、检查点、质量门和恢复。第一版不提供在线 Web 服务、多租户、插件系统和真实部署。

## 2. 技术栈

```text
Python 3.12
FastAPI + Uvicorn
Pydantic v2
pydantic-settings
SQLAlchemy 2.x + aiosqlite
Alembic
asyncio / AnyIO
OpenAI SDK + Anthropic SDK
watchfiles + psutil
zstandard
structlog
pytest + pytest-asyncio
Ruff + mypy
uv
```

## 3. 进程结构

```text
Electron Main Process
        │
        ├─ REST / WebSocket
        ▼
Backend Main Process
├─ API
├─ Application Services
├─ Workflow Orchestrator
├─ Tool Policy / Tool Supervisor
├─ Event Hub
├─ SQLite Repository
├─ Snapshot Store
├─ File Watcher
└─ Worker Supervisor
        │ framed IPC
        ▼
Project Worker Process
├─ Agent Runtime
├─ Context Builder
├─ P2R Controller
├─ Model Adapters
└─ Task Executor
        │ tool request
        ▼
Backend Main Process
        │
        ▼
Short-lived Tool Process
```

## 4. 主进程职责

Backend Main Process 是唯一状态权威：

- 接收桌面端 API 和 WebSocket。
- 验证本地会话令牌。
- 维护项目、工作流、节点和聊天室状态。
- 执行数据库事务和 EventLog。
- 启动、监控、取消和关闭 Project Worker。
- 重新计算每个工具请求的权限。
- 执行文件、Git、Shell、构建和测试工具。
- 创建项目检查点与快照。
- 监控外部文件变化和冲突。
- 广播持久化后的事件。

主进程不能把模型或 Worker 声称的完成状态直接写入数据库，必须重新验证 Stage Contract 和后端证据。

## 5. Project Worker 职责

一个活动项目最多拥有一个 Project Worker。Worker 负责：

- 构造模型上下文。
- 调用 Primary 和两个 Reviewer。
- 执行 P0/P1/P2R 调度。
- 解析模型工具调用。
- 向主进程发送 ToolExecutionRequest。
- 处理流式模型响应。
- 生成阶段草案、校正和任务结果。
- 响应取消、心跳和关闭命令。

Worker 不得：

- 直接打开 SQLite。
- 直接修改项目文件。
- 直接运行 Shell、Git 或构建工具。
- 直接读取系统安全存储。
- 直接设置工作流完成状态。

## 6. 工具执行

只有主进程 Tool Policy Engine 可以批准工具。简单文件读取、搜索和 Hash 可以由受控主进程服务执行；Shell、Git、构建和测试使用短生命周期子进程。

所有进程具有：

- 项目内 cwd。
- 脱敏环境变量。
- 超时和取消。
- 输出大小限制。
- 进程树清理。
- 结构化审计日志。

## 7. Worker IPC

主进程通过 stdin/stdout 启动 Python Worker，不开放网络端口。协议使用 UTF-8 JSON 和长度帧：

```text
Content-Length: <bytes>\r\n
Protocol-Version: 1\r\n
\r\n
<json payload>
```

消息类型：

```text
command
response
event
ack
heartbeat
cancel
shutdown
```

通用字段：

```text
protocol_version
message_id
correlation_id
sequence
project_id
task_id
type
timestamp
payload
```

stdout 只用于协议，stderr 只用于 Worker 日志。大型文件、模型长输出和构建日志通过 storage_uri 与 Hash 引用，不直接塞入单个 IPC 帧。

重要事件必须收到主进程 ACK。主进程先持久化状态与事件，再返回 persisted_event_id。Worker 崩溃时，未确认消息不算已完成。

## 8. 心跳与监督

Worker 周期性发送 heartbeat，包含 worker_id、active_task、last_sequence 和状态摘要。心跳超时后：

1. 主进程停止接收该 Worker 新结果。
2. 活动任务进入 `interrupted`。
3. 终止 Worker 及其子进程树。
4. 保留最后一个已确认事件。
5. 用户可重试，主进程创建新 Worker。

## 9. 代码目录

```text
backend/
├─ pyproject.toml
├─ uv.lock
├─ alembic.ini
├─ migrations/
├─ src/agent_platform/
│  ├─ bootstrap/
│  ├─ config/
│  ├─ domain/
│  │  ├─ projects/
│  │  ├─ workflows/
│  │  ├─ rooms/
│  │  ├─ roles/
│  │  ├─ discussions/
│  │  ├─ artifacts/
│  │  ├─ checkpoints/
│  │  ├─ quality_gates/
│  │  ├─ change_requests/
│  │  └─ capability_requests/
│  ├─ application/
│  │  ├─ commands/
│  │  ├─ queries/
│  │  ├─ services/
│  │  └─ dto/
│  ├─ ports/
│  ├─ infrastructure/
│  │  ├─ database/
│  │  ├─ models/
│  │  ├─ filesystem/
│  │  ├─ snapshots/
│  │  ├─ workers/
│  │  ├─ tools/
│  │  ├─ secrets/
│  │  └─ logging/
│  ├─ interfaces/
│  │  ├─ api/
│  │  ├─ ipc/
│  │  └─ cli/
│  └─ workers/
└─ tests/
```

## 10. 依赖规则

```text
domain → 标准库
application → domain + ports
infrastructure → domain + application + ports + third-party
interfaces → application + DTO
bootstrap → 全部实现装配
workers → domain/application contracts + model adapters，不依赖 FastAPI/SQLAlchemy
```

Domain 不导入 FastAPI、SQLAlchemy、模型 SDK 或操作系统实现。

## 11. Ports

第一版至少定义：

```text
UnitOfWork
ModelProvider
WorkspaceStore
SnapshotStore
SecretStore
WorkerController
ToolExecutor
EventPublisher
FileWatcher
Clock
IdGenerator
```

只有真实外部边界建立 Port，避免为了形式制造无用接口。

## 12. 后端生命周期

启动：

1. 加载本地启动配置和临时令牌。
2. 初始化结构化日志。
3. 检查应用数据目录。
4. 备份并执行数据库迁移。
5. 打开 SQLite 并检查完整性。
6. 恢复当前状态和未完成任务。
7. 启动文件监控、Event Outbox 和 Worker Supervisor。
8. 启动 FastAPI。
9. 向 Electron 返回 ready 握手。

关闭：

1. 停止接受新任务。
2. 广播 backend_stopping。
3. 取消或中断活动模型任务。
4. 终止 Tool Process。
5. 请求 Worker 安全关闭，超时后强制终止。
6. 刷新 Event Outbox 和日志。
7. 关闭数据库。

## 13. 配置

使用 `pydantic-settings`。优先级：

```text
启动参数
> Electron 传入环境
> 应用配置文件
> 内置默认值
```

模型配置来自数据库的 ModelProfile，API Key 来自 SecretStore，不写入普通配置文件。

## 14. MVP 非目标

- 微服务。
- Redis/Celery。
- PostgreSQL。
- 远程 Worker。
- 插件运行时。
- 容器沙箱。
- 多用户认证。
- 在线 Web 后端。

## 15. 验收标准

- 长时间模型和工具任务不阻塞 FastAPI 健康接口。
- Worker 崩溃不会破坏主进程和 SQLite。
- Worker 不能直接执行工具或写数据库。
- IPC 支持 ACK、序号、取消和大型数据引用。
- 业务逻辑可以脱离 FastAPI、SQLAlchemy 单元测试。
- 后端能够在 Windows 桌面环境安全启动和关闭进程树。
