# 后端测试与验收策略

## 1. 目标

测试必须证明工作流状态、角色权限、产物交接、工具安全、恢复和桌面生命周期真实有效。模型输出不可预测，因此核心状态和安全规则必须能够使用 Fake Model 与确定性工具测试。

## 2. 测试目录

```text
tests/
├─ unit/
├─ integration/
├─ contract/
├─ security/
├─ process/
├─ migration/
└─ e2e/
```

## 3. Unit Tests

纯领域测试，不启动 FastAPI、SQLite、Worker 和真实模型：

- Workflow 状态转换。
- Stage Run 状态转换。
- Manual/Autonomous 规则。
- Warning Blocked 行为。
- ChangeRequest 路由与失效范围。
- HandoffPacket 验证和 Hash。
- RoleCard/StageContract 权限计算。
- CapabilityRequest 生命周期。
- P2R Verdict 合并规则。
- 外部文件变化归属。
- 消息不可变和更正规则。

## 4. Repository Integration Tests

使用临时 SQLite：

- Repository CRUD 与事务回滚。
- 外键、唯一约束和并发版本。
- EventLog 与 Outbox 原子写入。
- 单项目 running workflow 约束。
- 单 Room active task 约束。
- Artifact Version 不可覆盖。
- 数据库 WAL 与 busy timeout 配置。

临时目录必须位于测试可写路径，不依赖系统不可访问目录。

## 5. API Contract Tests

使用 FastAPI ASGITransport：

- 本地认证和错误格式。
- 项目、工作流、Room、Task API。
- Idempotency-Key。
- Version Conflict。
- CapabilityRequest 在两种模式下都要求用户决定。
- Warning rewrite/open_room/abandon。
- Message correction/hide/pin。
- API 不返回 API Key。

OpenAPI Schema 变化需要显式审阅。

## 6. WebSocket Tests

- Ticket 单次使用和过期。
- 未认证连接拒绝。
- event_id 单调递增。
- after 重放。
- 重连去重。
- Outbox 未发送事件恢复。
- model.delta 临时流与最终 message.created。
- 桌面断线不影响后端任务。

## 7. Worker IPC Tests

- Content-Length 分帧和部分读取。
- JSON 包含换行和 Unicode。
- ACK 与重发。
- sequence 缺失和重复检测。
- heartbeat 超时。
- Worker 非正常退出。
- cancel/shutdown。
- stdout 协议与 stderr 日志隔离。
- 大型数据只发送 storage_uri。
- Worker 不能直接访问数据库和工具实现。

## 8. Agent Runtime Tests

使用 Scripted/Fake Model：

- P0 只调用 Primary。
- P1 只调用一个 Reviewer。
- 正式产物强制 P2。
- Reviewer A/B 并行且无工具。
- Primary 处理 PASS/REVISE/BLOCK。
- 两个 BLOCK 阻止正式提交。
- 工具调用经过主进程。
- 重复工具调用检测。
- 上下文摘要保留核心决定。
- completed consultation 不注入工具。
- 任务中用户消息进入队列。
- 取消传播到模型和工具请求。

真实模型只用于可选手工验收，不作为 CI 稳定性基础。

## 9. Stage Contract Tests

每个角色建立合法与非法案例：

- Planner 不能默认写源码。
- Designer 不能修改需求。
- Builder 可以写代码但不能写上游产物。
- Reviewer 永远不能写代码。
- Deployer 可以写允许部署文件但不能运行部署验证。
- 临时权限不能突破永久禁止规则。
- Handoff 目标阶段和路径合法。
- 外部修改使正确阶段失效。

## 10. Quality Gate Tests

### Planner

- 需求编号唯一。
- 核心需求有验收标准。
- 阻断性开放问题会失败。

### Designer

- 需求映射完整。
- API/数据/状态定义一致。
- Builder 任务可执行。

### Builder

- ProjectManifest 引用真实文件。
- 已声明构建与测试命令通过。
- 缺少测试体系允许进入，但必须创建测试任务。
- 已存在测试失败使 Preflight 拒绝。
- 占位实现和虚假报告被阻止。

### Reviewer

- Verdict 枚举严格。
- Blocking Finding 必须有证据和目标阶段。
- PASS 与阻断问题不能同时存在。

### Deployer

- 部署文档与生成文件完整。
- 真实凭据检测。
- 未验证内容必须标记。
- 远程部署声明被阻止。

## 11. Tool Security Tests

- `..`、绝对路径、UNC 和盘符逃逸。
- 符号链接、junction、reparse point 逃逸。
- Windows 大小写路径。
- Shell 参数注入。
- PowerShell 特殊字符。
- 环境变量脱敏。
- 输出大小和超时。
- 取消后进程树清理。
- 项目外删除和移动拒绝。
- ToolCall 审计完整。
- Reviewer 工具请求直接拒绝。
- CapabilityRequest 过期和任务结束撤销。

## 12. Snapshot Tests

- 相同内容对象去重。
- 增量 Manifest。
- 原子写和临时文件恢复。
- Root Hash 验证。
- `.agentignore`。
- Managed/Direct Workspace。
- 恢复前保护快照。
- 不移动用户 Git 分支。
- 外部并发修改创建三方冲突。

## 13. Recovery Tests

- FastAPI 运行时 Worker 崩溃。
- Tool Process 崩溃和部分写入。
- Pause 真实停止活动任务。
- 重复 Start 不创建并发执行。
- 后端异常退出后的 interrupted 恢复。
- Outbox 重发。
- Migration 失败恢复备份。
- SQLite integrity_check 失败进入恢复模式。
- ModelProfile 失效时不自动切换模型。

## 14. Desktop Process Tests

- 动态端口和 Ready 握手。
- Session Token 验证。
- 父 Electron PID 消失后安全关闭。
- 安装路径含空格和中文。
- 用户无需系统 Python。
- 退出后没有残留 Worker/Tool Process。
- 更新前创建数据库备份。

## 15. E2E 场景

### 新 Web 全栈项目

从 Planner 到 Deployer 完整运行，Builder 产生前后端、测试和 ProjectManifest，Reviewer PASS，Deployer 生成文档和部署文件。

### Existing Project

- 已有构建和测试通过，允许进入。
- 没有测试，允许进入并强制 Builder 创建测试任务。
- 已有构建或测试失败，Preflight 拒绝。

### Manual

五阶段均等待审批；CapabilityRequest 弹窗；Warning 可批准或重写。

### Autonomous

PASS 自动交接；Warning 阻断等待用户；CapabilityRequest 仍弹窗；无阶段审批。

### ChangeRequest

Reviewer 发现设计问题，返回 Designer；Designer 和下游旧包失效；重新交接后继续。

### External Conflict

用户与 Builder 同时改文件，进入 conflict，解决后重新 Gate。

### Restart

模型任务期间强制关闭应用，重启后任务为 interrupted，聊天与检查点完整。

## 16. 测试工具

```text
pytest
pytest-asyncio
pytest-cov
httpx ASGITransport
hypothesis（适用于状态机和路径）
```

文件系统和进程测试使用真实临时目录与受控短命令，不 Mock 掉全部关键安全边界。

## 17. CI 门禁

虽然产品为桌面端，仓库 CI 至少执行：

```text
ruff format --check
ruff check
mypy
pytest tests/unit
pytest tests/integration
pytest tests/contract
pytest tests/security
```

Windows 专属进程、路径和打包测试在 Windows Runner 执行。

## 18. 完成定义

后端 MVP 不能只以“API 能启动”作为完成。必须满足：

- 所有领域和契约测试通过。
- 权限绕过测试通过。
- Worker 崩溃和恢复测试通过。
- Manual/Autonomous E2E 通过。
- 无 API Key 泄漏。
- Windows 安装包内后端可以启动和安全关闭。
- 一个完整 Web 全栈示例项目跑通五阶段。
