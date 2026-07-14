# AgentProgram V1 总体实施规划

> 状态：准备阶段，当前重点为阶段 6 前端设计准备
>
> 目标版本：正式长期使用的 Windows 本地桌面 V1
>
> 本文件是 AgentProgram 后续实施的唯一总规划。旧规格、旧实施计划和旧 UI 材料全部删除；尚未代码化的五阶段角色卡暂时保留，转换为版本化运行时资源后再删除原文。前端尚未开始设计，本文件只固定前端的实施流程和进入条件，不预设页面方案。

## 1. 目标与交付边界

AgentProgram 是一个 Windows-first、单用户、本地运行的软件交付编排平台。用户选择一个本地项目目录，系统通过固定的五阶段工作流完成软件开发：

```text
Planner -> Designer -> Builder -> Reviewer -> Deployer
```

V1 的最终交付必须是可以安装、启动、恢复、审计和长期使用的桌面产品，而不只是可以演示的 API。

### 1.1 V1 必须包含

- 本地项目创建、打开、关闭和恢复。
- Managed Workspace 与 Direct Workspace。
- 项目预检、目录边界、ProjectManifest 和项目元数据。
- 内容寻址检查点、快照、外部文件变化和三方冲突记录。
- 五阶段固定工作流、阶段状态机、聊天室隔离和任务队列。
- 不可变消息、更正、正式产出物和完成后只读咨询。
- OpenAI 兼容接口与 Anthropic 接口。
- Primary、Reviewer A、Reviewer B 的一主双校运行模式。
- Prompt、上下文、摘要、流式输出、取消、超时、重试和用量记录。
- 文件、搜索、Shell、Build、Test 等受控工具。
- 阶段权限、路径沙箱、CapabilityRequest、进程树清理和工具审计。
- StageContract、ArtifactVersion、Quality Gate、Approval、HandoffPacket 和 ChangeRequest。
- Manual 与 Autonomous 两种审批模式。
- Worker、工具进程和应用异常退出后的恢复。
- REST、WebSocket 事件、断线重放和本地认证。
- 完整的 Electron Renderer、Preload 安全桥接和桌面交互功能。
- Electron Sidecar 控制协议、动态端口、SecretStore、Windows 打包和升级前备份。
- Windows 安装环境中的完整五阶段 Fake-Model E2E。
- CI、静态检查、类型检查、迁移检查、安全检查和回归矩阵。

### 1.2 V1 明确不包含

- 云端托管、多用户、团队和组织权限。
- 任意 DAG 工作流编辑器。
- Agent 自动创建角色或插件市场。
- 多机器并行执行。
- 真实生产环境自动部署。
- 应用商店发布和复杂计费体系。
- AgentProgram 产品内的 Git 操作。

产品内不实现 Git 操作，但保留通用工具扩展边界。检查点、恢复和状态正确性不得依赖 Git。Git 只用于维护 AgentProgram 源代码；未来若需要产品内 Git，作为新的 Tool Catalog 适配器和独立 PR 加入。

## 2. 现有后端基线

当前实现基线为 `master` 合并提交 `ed14dd055a8f9864b5af1377b992bef54781ee86`，代码位于 `backend/`。这部分不重写，后续模块必须在其上扩展。

基线已经提供：

- Python 3.12、FastAPI、Pydantic v2、SQLAlchemy Async、Alembic、SQLite、structlog、uv。
- Settings、应用目录、App Factory 和安全关闭生命周期。
- SQLite WAL、外键、UTC 时间、Unit of Work、EventLog 和 Outbox 写入。
- `/api/v1`、本地 Bearer Session Token、统一错误 envelope、health/readiness。
- Content-Length IPC v1、协议版本、消息序号、关联 ID、消息大小上限和重放防护。
- 一个项目一个 Project Worker、心跳、取消、超时和 Windows Job Object 进程树清理。
- 单元、集成、契约、迁移和进程测试。

基线验证结果：

```text
295 passed, 5 skipped
Ruff check: passed
Ruff format --check: passed
Mypy strict: passed for 43 source files
```

### 2.1 基线扩展前必须修正的风险

这些是对现有实现的加固，不是重写：

1. readiness 不再硬编码 Alembic `0001_foundation`，改为读取统一迁移版本。
2. 启动器实际消费 `Settings.host`、`Settings.port`，正式运行使用动态本机端口。
3. 将 Worker `watch_once()` 接入生命周期后台 Watchdog。
4. 保存并脱敏 Backend 和 Worker stderr，完成日志和诊断链路。
5. 为 Outbox 增加领取、至少一次投递、重试、死信、幂等消费和清理。
6. 事件补齐 `schema_version`、`correlation_id`、`causation_id`、`actor`、`source` 和幂等关联。
7. 将静态 Session Token 改为 Electron 会话生成、轮换和退出失效的临时 Token。
8. 为长寿命 Worker 的入站消息去重增加有界窗口或会话轮换。
9. 建立稳定的 HTTP 错误分类，不把所有领域错误都映射为 `409`。
10. 统一后端版本来源，避免 `__init__` 和 App Factory 漂移。
11. 增加 SQLite 单实例锁、在线备份、WAL checkpoint、完整性检查和保留策略。

## 3. 统一架构

```text
Electron Desktop
    |- Renderer UI
    |- Preload typed bridge
    `- Electron Main
           | REST / WebSocket / Control Channel
           v
Backend Main Process
    |- API and application services
    |- Workflow Orchestrator
    |- SQLite repositories and Unit of Work
    |- EventLog and Outbox dispatcher
    |- Workspace, Checkpoint and File Watcher
    |- Tool Policy and Tool Supervisor
    `- Worker Supervisor
             | framed IPC v1
             v
        Project Worker
             |- Agent Runtime
             |- Prompt and Context Builder
             |- Model Adapters
             `- P2R Controller
```

### 3.1 职责边界

- Backend Main Process 是数据库、工作流、权限、文件和工具状态的唯一权威。
- Project Worker 只负责模型上下文、模型调用、P0/P1/P2R 和任务结果，不直接访问 SQLite、项目文件、Shell、Git 或 SecretStore。
- 所有工具请求返回 Backend Main Process 重新鉴权；模型输出不能伪造审批、Hash、版本或完成状态。
- API 路由只转换请求和响应，不能直接编排 SQLAlchemy、Worker 或文件系统。
- 依赖方向固定为 `domain -> ports -> application -> infrastructure/interfaces -> bootstrap`。
- 领域层不依赖 Electron、Windows GUI 或任何具体模型 SDK。

### 3.2 共享协议内核

在业务模块前先冻结下列共享类型，所有后续代码只能引用这一份定义：

- `Stage`、固定顺序、阶段路径归属和状态枚举。
- `StageContract` 基础结构、版本、能力计算和角色版本。
- `RoleCard` Schema、版本化资源、内容 Hash 和运行时加载规则。
- Event Envelope、错误代码、命令关联、因果关联和幂等键。
- `ToolExecutionRequest`、`ToolResult`、`CapabilityRequest`。
- `ProjectCheckpointRef`、`ArtifactRef`、版本和 Hash 类型。
- API、WebSocket 和 IPC 的 schema version。

该内核不实现 Git 工具，不实现完整 Quality Gate，不包含桌面页面。

## 4. 核心领域与数据

SQLite 是 V1 的权威状态存储。大文件、模型流、构建日志和快照内容写入应用数据目录；数据库只保存引用、Hash、版本、索引和审计元数据。

核心实体按模块归属如下：

| 模块 | 主要实体 |
| --- | --- |
| 项目 | `projects`, `workspaces`, `project_manifests`, `project_instructions` |
| 工作流 | `workflows`, `stage_runs`, `tasks`, `rooms`, `messages`, `conversation_summaries`, `decisions` |
| 模型 | `model_profiles`, `room_model_assignments`, `model_calls`, `usage_records` |
| Worker/IPC | `workers`, `ipc_messages` |
| 产物 | `artifacts`, `artifact_versions`, `project_checkpoints`, `checkpoint_files` |
| 门禁/交接 | `quality_gate_runs`, `quality_gate_issues`, `approvals`, `handoff_packets`, `change_requests` |
| 工具/安全 | `capability_requests`, `tool_calls`, `external_changes`, `file_conflicts`, `idempotency_records` |
| 事件 | `event_log`, `outbox_events` |

### 4.1 数据不变量

- 所有持久化时间使用 UTC aware datetime。
- 状态、EventLog 和 Outbox 在同一个 Unit of Work 事务中提交。
- 正式 ArtifactVersion 不可覆盖，只能新增版本并标记失效或替代。
- HandoffPacket 不可变，引用文件 Hash 改变时自动失效。
- 消息不可直接修改或物理删除；更正创建引用原消息的新记录。
- API Key 只保存 `credential_ref` 和 `masked_hint`，密钥值不进入数据库、日志、事件或普通 IPC payload。
- ProjectManifest 中的路径全部是项目根目录内的规范化相对路径。
- Direct Workspace 不因 stop、abandon、卸载或恢复而静默删除用户文件。

## 5. 状态与工作流规则

### 5.1 Workflow 状态

```text
created
preflight_failed
running
waiting_user
warning_blocked
paused
external_conflict
interrupted
failed
stopped
abandoned
completed
```

### 5.2 StageRun 状态

```text
locked
ready
discussing
producing
p2r_reviewing
quality_checking
waiting_approval
handoff_ready
completed
warning_blocked
needs_fix
external_conflict
interrupted
failed
cancelled
abandoned
```

状态只能通过 Application Command 和 Domain Rule 转换。API 路由、Worker 和模型不能直接赋值。

### 5.3 阶段完成链

```text
草案
 -> Reviewer A/B 校正
 -> 确定性 Quality Gate
 -> MANUAL 用户审批或 AUTONOMOUS 策略
 -> Project Checkpoint
 -> ArtifactVersion 锁定
 -> HandoffPacket 生成
 -> 状态、EventLog、Outbox 同事务提交
 -> 解锁下一阶段
```

正式 P2 必须具备 Reviewer A 和 Reviewer B 的有效结果。Reviewer 槽位可以不配置用于普通讨论，但缺任一 Reviewer 时不能正式交付。

### 5.4 返工和 Warning

- 重写次数不设固定上限，但每次重写必须记录原因、输入版本、产物版本和 Gate 结果。
- `NEEDS_FIX` 和 `FAIL` 阻断交接并创建结构化返工目标。
- `MANUAL` 的 `WARNING` 由用户批准或要求重写。
- `AUTONOMOUS` 的 `WARNING` 进入 `warning_blocked`，只允许 rewrite、open_room 或 abandon。
- Planner 问题返回 Planner，设计/API/数据问题返回 Designer，代码/测试/构建问题返回 Builder，部署资料问题留在 Deployer。
- 上游重新运行会使目标阶段及所有下游交接包、产物引用和结果失效，但历史记录保留。

## 6. 分阶段实施路线

每个阶段都必须有独立分支、独立 PR、专属测试和完成门禁。前端不是后端完成后的附注，而是 V1 的正式实施阶段；桌面集成和打包只能在正式前端完成后开始。

### 阶段 0：后端基础（已完成）

保留当前 `backend/` 实现。不得回退 Worker 进程清理、IPC v1、认证、事务和迁移约束。

### 阶段 1：后端共享协议与基础加固（已完成）

交付：共享类型、StageContract 内核、RoleCard Schema/Loader、五张版本化角色资源、错误分类、事件元数据、幂等协议、Alembic 版本、Watchdog、文件日志、Outbox Dispatcher、SQLite 备份基础。

门禁：五张角色卡内容完成规则对照并通过加载、版本、Hash、权限和 Prompt 优先级契约测试；共享 Schema、迁移升级/回滚、Outbox 重试/幂等和 Worker Watchdog 测试通过。完成代码化并确认无信息缺失后，删除 `docs/roles` 原文。

### 阶段 2：后端项目、工作区与检查点

交付：Project/Workspace、Managed/Direct、ProjectManifest、`.agent/` 元数据、路径边界、Preflight、内容寻址快照、恢复、外部变化和 FileConflict。

门禁：新项目、已有项目、无测试项目、非法路径、符号链接、原子写、Hash 校验、并发写入和用户数据保护测试。

### 阶段 3：后端工作流、聊天室与实时事件

交付：Workflow/StageRun/Room/Task 状态机、五阶段锁定、消息不可变、任务队列、取消、完成后咨询、显式 reopen、REST API、WebSocket Ticket 和事件重放。

门禁：状态转换、条件更新并发、重复 start、消息序号、断线重连、事件去重和 reopen 失效测试。

### 阶段 4：后端模型与 Agent Runtime

交付：ModelProfile、SecretStore Port、OpenAI 兼容适配器、Anthropic 适配器、Prompt Composer、Context Builder、Rolling Summary、P0/P1/P2R、流式输出、取消和用量。

门禁：密钥不落盘、独立 credential_ref、Fake Model 一主双校、局部失败、上下文隔离、重复调用检测和取消传播测试。

### 阶段 5：后端工具、门禁、交接与恢复

交付：Tool Catalog、PathGuard、原子文件工具、受控 Shell/Build/Test、CapabilityRequest、ToolCall 审计、ArtifactVersion、五阶段 Gate、Approval、HandoffPacket、ChangeRequest、Pause/Resume/Stop/Abandon、崩溃恢复、后端 Ready/Shutdown 协议。

不交付：Git 工具、Electron 页面、Windows 安装包。

门禁：工具越权与进程树测试、MANUAL/AUTONOMOUS、Warning、返工、历史包校验、Worker/Tool 强杀、数据库恢复、完整 Fake-Model 后端五阶段 E2E。通过后冻结 REST、WebSocket、IPC 和 Desktop Control Contract，后端功能进入 V1 完成状态。

### 阶段 6：前端设计

严格按顺序完成：

```text
文字排版
-> 草案
-> 草案母版
```

文字排版先定义全部页面、信息层级、状态、动作、错误、空状态、加载状态和恢复流程；草案验证布局与工作流；草案母版是用户批准的唯一视觉与交互基准。该阶段不编写正式前端业务代码，也不参考已删除的旧 UI 材料。

门禁：五阶段主流程、项目管理、模型配置、审批、冲突、恢复、设置和诊断场景都有经过用户批准的母版；所有后端状态和错误都有明确前端呈现。

#### 阶段 6.0：前端设计准备清单

阶段 6 开始时不写前端代码，先完成以下准备：

1. 从阶段 5 已冻结的 REST、WebSocket、错误、分页、认证和 Desktop Control Contract 建立前端能力清单。
2. 为每个后端状态建立前端状态表：正常、加载、空数据、失败、权限拒绝、等待审批、暂停、恢复、冲突、过期和不可用。
3. 固定用户主线：首次启动、创建项目、项目预检、Planner 到 Deployer、审批、返工、暂停/恢复、外部冲突、诊断和设置。
4. 固定五个阶段聊天室的职责、输入、正式产出、允许动作和不可用动作；界面不能创造角色卡之外的新权限。
5. 固定信息架构和导航关系，确保用户能从项目、工作流、阶段、聊天室、任务、产物、事件和诊断之间往返。
6. 固定所有危险操作的确认、取消、失败恢复和撤销路径；不能只设计成功路径。
7. 固定后端事件到界面读模型的映射，明确哪些事件实时显示、哪些事件持久化后显示、哪些事件需要重新拉取。
8. 固定模型、SecretStore、工具审批、文件冲突和恢复模式的用户可见信息；不展示密钥明文和内部敏感字段。
9. 固定 Windows 桌面约束：窗口生命周期、系统通知、目录选择、关闭确认、异常重启和诊断导出。

#### 阶段 6.1：文字排版产物

文字排版阶段只描述内容和动作，不决定颜色、图形和最终组件。每个页面/视图必须写清：

- 目的、进入条件和离开路径。
- 标题、说明、主要信息和次要信息。
- 主操作、次操作、危险操作及其确认文案。
- 加载、空、错误、权限、暂停、冲突和恢复文案。
- 对应 API、事件、命令和数据字段。
- 用户操作后的状态变化和可撤销范围。

必须覆盖项目入口、项目详情、五个阶段工作区、消息/任务、阶段产出、Gate/Approval、模型配置、CapabilityRequest、冲突恢复、诊断和设置。

#### 阶段 6.2：草案产物

草案阶段验证完整流程和信息层级：

- 从首次启动到最终交付的主线可走通。
- 每个异常状态都能回到明确的处理路径。
- 阶段权限和只读状态在页面结构上可理解。
- 事件流、任务队列、审批和返工不会互相遮挡或丢失上下文。
- 用户不需要依赖模型输出猜测系统状态。

草案阶段仍不进入正式前端工程，不绑定具体 CSS、组件库或视觉资产。

#### 阶段 6.3：草案母版产物

草案母版是正式开发唯一允许使用的设计基准，必须冻结：

- 页面和视图清单。
- 路由、导航和窗口层级。
- 组件状态和交互状态。
- API/事件/命令映射。
- 错误、权限、恢复和审计信息的展示规则。
- 键盘操作、可访问性、缩放和 Windows 常用窗口尺寸。

阶段 6 的退出条件是用户批准草案母版。未批准前，阶段 7 不创建正式前端代码；阶段 8 不进行桌面打包。

#### 阶段 6.4：前后端功能耦合验收

文字排版和草案母版必须建立前后端功能矩阵。每一项前端交互至少对应：

```text
UI 控件或导航
 -> API 查询 / Application Command
 -> 请求参数和权限
 -> 成功响应或持久化事件
 -> 前端状态更新
 -> 错误、取消、重试和恢复行为
```

硬性规则：

- 后端没有真实能力的功能不得出现在前端中，不得用空按钮、假弹窗或“稍后实现”的可点击交互占位。
- 后端能力未完成时，前端只能隐藏该功能，或以明确的非交互状态说明依赖的后端阶段；不能伪造成功。
- 权威状态来自后端 API 和事件，前端本地状态只保存输入草稿、视图偏好和临时加载状态。
- 命令只有收到后端确认后才能显示成功；失败必须显示真实错误和可执行的恢复动作。
- 每个按钮、表单提交、菜单项、快捷操作和导航目标都必须有 API、事件、权限和错误映射。
- 五阶段界面只能显示对应 RoleCard 和 StageContract 允许的操作。
- 审批、返工、冲突解决、恢复和危险操作必须真正调用后端状态机，不能只改变页面文字。
- 设计评审必须逐项检查“有交互但无后端实现”的死控件，发现一项就不能通过阶段 6。

#### 阶段 6.5：最终文字排版基线

以下文字结构是正式草案的输入基线。它只定义信息顺序、页面职责和后端映射，不定义颜色、组件样式、图标、动效或最终视觉资产。

后端阶段 5 冻结的是 Application Command、Query、Event 和权限语义；前端文字排版引用这些稳定的契约 ID。具体 REST 路径、WebSocket 订阅和类型化 Client 在阶段 5 的 API Schema 中冻结，禁止前端自行创造接口。

##### 全局应用壳

```text
顶部：AgentProgram | 当前项目 | 后端连接状态 | 工作流状态 | 通知 | 设置
左侧：项目 | 当前工作流 | 五阶段 | 产出物 | 事件与审计 | 诊断
主区：当前页面的主要工作内容
上下文区：当前阶段、任务、Gate、审批、风险和正式产出物
底部：当前任务状态、取消、重试或恢复动作
```

全局交互映射：

| 交互 | 后端契约 | 成功事件 | 失败处理 |
| --- | --- | --- | --- |
| 切换项目 | `ProjectListQuery`、`ProjectOpenCommand` | `project.opened` | 保留当前页面，显示真实错误 |
| 切换阶段 | `StageViewQuery` | `stage.loaded` | 显示锁定原因或权限错误 |
| 打开通知 | `EventQuery` | `event.read` | 显示重试和断线状态 |
| 查看设置 | `SettingsQuery` | `settings.loaded` | 显示不可用项的后端原因 |
| 取消当前任务 | `TaskCancelCommand` | `task.cancelled` 或 `task.interrupted` | 显示未取消原因和下一步 |

##### S00 启动与恢复

```text
标题：启动 AgentProgram
内容：后端状态、数据库版本、迁移状态、可恢复项目、遗留任务
主操作：继续恢复、查看详情
次操作：放弃本次恢复、退出
```

交互映射：`BackendHealthQuery`、`RecoveryListQuery`、`RecoveryResumeCommand`、`RecoveryDiscardCommand`；成功事件为 `system.ready`、`recovery.resumed` 或 `recovery.discarded`。恢复失败必须显示检查点、错误证据和可重试动作，不能只显示“启动失败”。

##### S01 项目列表与创建

```text
标题：项目
内容：项目名称、路径、Workspace 模式、当前阶段、工作流状态、最后更新时间、待处理事项
主操作：创建项目、打开项目
```

创建表单：

```text
项目名称
项目目标
本地工作目录
Workspace 模式：Managed / Direct
```

交互映射：`ProjectListQuery`、`ProjectCreateCommand`、`ProjectOpenCommand`。创建成功必须进入 `ProjectPreflightCommand`，不能在未预检时显示“项目可运行”。路径非法、重复登记、权限不足和目录不可读必须显示后端错误。

##### S02 项目预检

```text
标题：项目预检
内容：目录边界、Manifest、依赖文件、构建命令、测试命令、类型检查、外部冲突
结果：通过 / 有警告 / 需要修复 / 失败
主操作：开始工作流
次操作：查看证据、重新预检、返回项目
```

交互映射：`ProjectPreflightCommand`、`ProjectPreflightQuery`、`WorkflowStartCommand`。只有 `PASS` 或用户明确批准的允许 `WARNING` 才能显示开始工作流；`NEEDS_FIX` 和 `FAIL` 不显示可绕过的继续按钮。

##### S03 项目主页

```text
标题：项目名称
内容：项目目标、工作流状态、五阶段进度、当前阶段、当前任务、待用户处理、最近产出、最近事件
主操作：开始、继续、暂停、停止、查看当前阶段
次操作：查看检查点、查看冲突、查看事件
```

交互映射：`ProjectOverviewQuery`、`WorkflowStartCommand`、`WorkflowPauseCommand`、`WorkflowResumeCommand`、`WorkflowStopCommand`、`CheckpointListQuery`、`ConflictListQuery`。页面状态必须由 `workflow.*`、`stage.*`、`task.*` 和 `external_change.*` 事件驱动，不能只依赖本地计时器。

##### S04 阶段工作区

```text
阶段标题与目标
当前状态与允许操作
上游 Handoff 摘要
用户与 Agent 消息
当前任务和工具进度
正式产出物
质量门与审批摘要
输入区与任务队列
```

交互映射：`RoomQuery`、`RoomHistoryQuery`、`MessageSendCommand`、`TaskCancelCommand`、`TaskQueueQuery`、`StageReopenCommand`。消息发送成功只在收到 `message.created` 后确认；模型流只显示临时 `model.delta`，最终内容必须等待持久化事件。已完成阶段只读，修改必须经过 `StageReopenCommand`。

阶段专属文字：

```text
Planner：项目目标、用户、场景、需求、范围、非目标、验收、风险、开放问题、决策
Designer：架构、模块、数据、API、事件、错误、安全、技术约束、构建任务
Builder：实现范围、文件、测试、构建结果、限制、偏差、剩余问题
Reviewer：审查范围、证据、阻断问题、重要问题、建议、PASS/NEEDS_FIX/FAIL、返工目标
Deployer：版本、环境、前置条件、配置、安装、启动、停止、健康检查、日志、回滚、已知问题
```

##### S05 正式产出、Gate 与交接

```text
标题：阶段产出物
内容：名称、版本、阶段、Hash、检查点、Gate 结果、审批结果、交接状态、失效原因
操作：查看证据、批准、驳回、要求修改、打开交接包
```

交互映射：`ArtifactQuery`、`ArtifactVersionQuery`、`QualityGateQuery`、`ApprovalDecideCommand`、`HandoffQuery`、`ChangeRequestCreateCommand`。批准、交接和返工必须由后端状态机完成；前端不能用本地状态将阶段标记为完成。

##### S06 审批、能力申请与风险

```text
申请角色
申请能力
申请原因
目标路径
拟执行命令
预期修改
风险等级
所属任务
有效期
```

交互映射：`ApprovalQuery`、`ApprovalDecideCommand`、`CapabilityRequestQuery`、`CapabilityDecideCommand`。永久禁止能力、过期任务和未授权路径不显示批准入口；用户决定必须产生 `approval.decided` 或 `capability.decided` 事件。

##### S07 冲突、检查点与恢复

```text
冲突文件
基线版本
用户版本
Agent 版本
最早受影响阶段
受影响产出物和下游阶段
```

操作：保留用户版本、保留 Agent 版本、手动合并、取消处理、查看保护检查点、恢复检查点。

交互映射：`ConflictQuery`、`ConflictResolveCommand`、`CheckpointListQuery`、`CheckpointRestoreCommand`。恢复前必须显示会失效的内容；解决成功后等待后端 `file_conflict.resolved` 和重新 Gate，不直接刷新为“已完成”。

##### S08 模型、权限与设置

```text
模型名称
提供商
模型 ID
能力探测
Primary / Reviewer A / Reviewer B 槽位
credential_ref 脱敏提示
最近调用状态
用量统计
```

交互映射：`ModelProfileListQuery`、`ModelProfileCreateCommand`、`ModelProfileUpdateCommand`、`ModelProfileTestCommand`、`RoomModelAssignmentCommand`、`SecretReferenceCommand`。不显示 API Key 明文；没有对应 SecretStore 能力时不显示保存或测试成功状态。

##### S09 事件、审计与诊断

```text
时间
事件类型
项目
工作流
阶段
任务
来源
结果
关联事件
```

诊断内容：AgentProgram 版本、后端版本、数据库版本、Worker 状态、最近错误、恢复记录、进程状态和脱敏日志摘要。交互映射：`EventQuery`、`EventReplayQuery`、`DiagnosticsQuery`、`DiagnosticsExportCommand`。导出前必须显示包含项和排除项，默认排除源码、完整聊天和密钥。

##### 文字排版的最终检查表

阶段 6.1 通过前逐项确认：

- 每个页面都有进入条件、退出路径、加载、空、错误、权限、暂停、冲突和恢复文本。
- 每个按钮、表单、菜单、快捷操作和导航都有后端 Query/Command/Event/Permission 映射。
- 每个成功状态都来自后端确认事件，前端不伪造完成。
- 每个失败状态都有真实错误、影响范围和可执行恢复动作。
- 五阶段操作严格服从 RoleCard 和 StageContract。
- 没有 Git 交互、没有未实现功能占位、没有 Mock 成功路径。
- 文字排版覆盖后端已经规划的所有 V1 能力，不新增未批准功能。

只有这份文字排版通过用户确认，才进入阶段 6.2 草案；草案母版确认前不进入前端开发。

### 阶段 7：前端开发

严格按顺序完成：

```text
开发前端母版
-> 正式开发前端
```

开发前端母版建立 Electron Renderer/Preload 工程、设计令牌、基础组件、类型化 API Client、事件状态层、路由和应用壳；正式开发前端在母版上实现全部页面、状态、键盘/可访问性、错误处理和恢复流程。

门禁：组件测试、状态测试、API Contract 测试、WebSocket 重连测试、视觉回归、键盘操作、缩放和 Windows 常用分辨率验证全部通过；所有可交互元素均有真实后端映射，生产模式不包含 Mock 成功、假数据提交或未接线按钮。

### 阶段 8：桌面集成与 Windows 打包

在正式前端完成后，接入 Electron Main/Preload、动态端口、临时 Session Token、SecretStore Bridge、后端进程生命周期、诊断导出、固定 Python 3.12 onedir、安装器、升级前备份和恢复模式。

门禁：无系统 Python、中文和空格路径、动态端口、安装/卸载、父进程消失、无残留进程、升级失败恢复和密钥不泄漏测试。

### 阶段 9：全产品 E2E 与 V1 发布

使用安装后的真实桌面程序和 Fake Model，让一个真实小型项目从 Planner 运行到 Deployer，覆盖 Manual、Autonomous、返工、审批、冲突、重启、恢复、前端展示和交付资料生成。

门禁：Windows 安装包完整回归、零已知 P0/P1、所有需求追踪项有界面/代码/测试/证据、CI 全绿。

## 7. 测试与质量策略

测试目录固定为：

```text
tests/unit
tests/integration
tests/contract
tests/security
tests/process
tests/migration
tests/e2e
```

测试必须覆盖：

- 纯领域状态、权限、Gate、Handoff、ChangeRequest 和 Hash。
- SQLite 事务、约束、版本冲突、EventLog/Outbox 原子性。
- REST 认证、错误、幂等、分页、版本冲突和脱敏。
- WebSocket Ticket、过期、重放、去重和 Outbox 恢复。
- IPC 分帧、ACK、序号、心跳、取消和 Worker 异常退出。
- Fake Model 的 P0/P1/P2R、局部失败、上下文隔离和取消。
- 工具路径、Shell、环境、超时、进程树、审计和 CapabilityRequest。
- 快照、外部修改、冲突、恢复和数据库损坏。
- Windows Sidecar、动态端口、Token、安装、升级和无残留进程。

真实模型只作为手工验收，不作为 CI 稳定性基础。

每个 PR 至少通过：

```text
uv run ruff format --check .
uv run ruff check .
uv run mypy src
uv run pytest
```

Windows 专属进程、路径、SecretStore 和打包测试必须在 Windows Runner 执行。

## 8. 安全、隐私和数据处理

- 后端默认只监听 `127.0.0.1`，所有 REST/WebSocket 请求需要当前会话认证。
- Renderer 不直接获得 Token、文件系统、Shell 或 SecretStore 能力。
- API Key 通过 SecretStore 按 `credential_ref` 短时提供，不进入 Prompt、日志、DB、事件或诊断包。
- 项目文件、聊天内容和模型输出视为不可信数据，不能扩大 Agent 权限。
- 用户发送给外部模型前需要明确 Provider 和数据范围，敏感路径可以从 Manifest 排除。
- 消息不可删除，但对误贴凭据等安全红线提供受控脱敏和安全事件记录，不允许通过隐藏操作破坏审计链。
- 诊断包默认只包含脱敏日志、版本、状态摘要和错误证据，不包含源码、完整聊天和密钥。
- SQLite、快照、日志和事件需要配置大小、保留和清理策略，清理前必须保护仍被正式产物引用的数据。

## 9. 前端规划规则

前端是 V1 的正式组成部分，但目前尚未开始设计。本文件只固定流程、依赖和门禁，不预设页面、颜色、组件或交互方案。后端阶段 5 完成并冻结 API/Event/Control Contract 后，启动前端：

```text
文字排版
→ 草案
→ 草案母版
→ 开发前端母版
→ 正式开发前端
```

每一步都必须单独评审和确认。前端设计可以提出后端契约缺口，但不能静默修改已冻结的后端状态和安全边界；必要变化通过版本化 Change Request 评审后实施。桌面集成和打包必须等待正式前端完成。

## 10. 旧文档、旧原型和新规划的关系

- `docs/` 中的旧规格、旧计划和旧 UI 材料全部删除，不再作为实现或设计输入；当前保留的本文件、`docs/backend` 阶段实施计划和 `docs/frontend` 已批准资料均属于本轮新规划。
- `docs/roles` 原始角色卡已在阶段 1 完成代码化并删除。运行时角色资源位于 `backend/src/agent_platform/resources/roles/v1/`；StageContract、全局运行时约束和 Prompt 优先级由后端领域契约提供，后续实现不得重新创建第二份角色规格。
- 旧的 2026-07-08 和 2026-07-11 设计/计划不纳入新系统。
- `agent-orchestrator/` 和 `agent-tools/` 不迁移为第二套实现；只保留已经提取进本文件的行为要求和测试向量。新代码只写入 `backend/`。
- 如果未来需要 Git 操作，只新增独立 Git Tool 设计和 PR，不修改本规划中检查点和状态的非 Git 依赖原则。

## 11. PR、版本和变更治理

- 每个新分支从最新 `master` 创建，使用 `codex/` 前缀。
- 一个 PR 只解决一个能力边界；已合并分支不继续承载新功能。
- 迁移、代码、测试和协议变更必须在同一 PR 中保持一致。
- PR 描述必须列出规划任务、需求编号、测试命令、已知限制和回滚方式。
- 不允许未经批准改变上游需求、设计、StageContract、API、事件或 IPC Schema。
- 重要协议变化必须增加 schema version、迁移器、兼容测试和回滚说明。
- 只有完成当前里程碑门禁并通过独立审查，才能进入下一里程碑。

## 12. V1 完成定义

只有以下条件全部满足，AgentProgram V1 才算完成：

1. 阶段 0–9 全部通过各自门禁。
2. 五阶段在 Manual 和 Autonomous 模式均能完整运行。
3. 需求、设计、代码、测试、产物、交接和审计记录可追踪。
4. 权限、路径、模型、工具、SecretStore 和进程边界没有已知绕过。
5. Worker、Tool 和应用强杀后无虚假完成、无残留进程且可恢复。
6. API Key、项目外路径和敏感环境变量不会进入数据库、日志、事件或诊断包。
7. Windows 安装包不依赖系统 Python，支持动态端口、升级前备份和失败恢复。
8. 一个真实小型项目可以生成可验证、可运行的代码、测试、构建报告和交付说明。
9. 零已知 P0/P1 阻断缺陷，完整测试和 CI 通过。
10. 正式前端、Electron 集成和 Windows 安装包已经完成，不以仅后端或仅界面演示代替产品交付。
11. 前端所有可用功能均由后端真实能力驱动，不存在没有功能实现的可点击交互。

“无 Bug”在工程上以以上可验证条件表达，不承诺不可证明的绝对零缺陷。
