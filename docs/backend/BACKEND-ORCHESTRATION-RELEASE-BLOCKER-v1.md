# AgentProgram V1 自动编排层与发布阻塞说明

> 文档版本：v1
> 状态：实施基线
> 适用版本：`1.0.0-rc.1` 及后续 RC
> 依据：`docs/PROJECT-PLAN.md`、Stage 0-5 冻结领域规则与桌面端安装版验收结果

## 1. 结论

`1.0.0-rc.1` 在自动编排闭环完成前不得作为完整桌面 V1 发布。现有后端已经分别实现工作流、AgentRun、ToolCall、ArtifactVersion、Quality Gate、Approval、Checkpoint 与 Handoff，但安装版产品测试仍由测试驱动逐条调用底层命令。普通用户只操作 Renderer 时无法完成同一条五阶段路径。

本阻塞项不重写 Stage 0-5。新增的 Orchestration Application Service 只负责按既有领域规则协调现有服务，Backend Main Process 仍是状态、权限、文件与审计的唯一权威。

## 2. 用户级闭环

正式阶段运行固定为：

```text
用户提交阶段指令
 -> StageRun 进入 discussing / producing
 -> 创建并启动 WorkflowTask
 -> 创建正式 AgentRun（一主双校）
 -> Primary 输出结构化执行计划
 -> Reviewer A / Reviewer B 独立检查
 -> Primary P2R 返回校正后的结构化执行计划
 -> Orchestrator 解析并验证计划
 -> ToolApplicationService 逐项重新鉴权并执行
 -> 写入该阶段正式草案
 -> WorkflowTask 终态
 -> ArtifactVersion
 -> p2r_reviewing / quality_checking
 -> Quality Gate
 -> MANUAL Approval 或 AUTONOMOUS Policy
 -> Checkpoint + Artifact Lock + Handoff
 -> 下一阶段解锁或工作流完成
```

讨论运行继续使用现有 AgentRun，不创建 ArtifactVersion、Gate、Checkpoint 或 Handoff。

## 3. 职责边界

### 3.1 Orchestration Application Service

- 接收一个用户级正式阶段运行请求并产生 NDJSON 进度帧。
- 根据后端快照推进合法 StageRun 转换，不直接赋值状态。
- 使用请求键关联 WorkflowTask 与 AgentRun，避免网络重试重复执行。
- 为模型构建有大小上限、排除敏感目录且带内容 Hash 的工作区上下文。
- 验证模型返回的 `StageExecutionPlan v1`，拒绝自由文本冒充执行成功。
- 只通过现有 Workflow、Agent Runtime、Tooling 和 Governance Application Service 执行业务动作。
- 失败时保留真实终态、错误代码和已审计 ToolCall；不得伪造 Artifact、Gate 或 Handoff。

### 3.2 Agent Runtime

- 继续负责 P0、Reviewer A、Reviewer B、P2R、流式输出、取消、超时、重试和用量。
- 正式编排运行接收只读项目文件上下文和结构化输出契约。
- 不直接访问项目文件、ToolService 或数据库外的业务状态。

### 3.3 Tooling 与 Governance

- 模型计划不是授权。每个计划动作仍经过 Tool Catalog、StageContract、PathGuard、CapabilityRequest、原子写和进程控制。
- Orchestrator 不自动批准需要用户授权的 CapabilityRequest。
- ArtifactVersion、Gate、Approval、Checkpoint、Handoff 继续由 GovernanceApplicationService 创建。

## 4. `StageExecutionPlan v1`

正式模型输出必须是一个 JSON 对象：

```json
{
  "schema_version": 1,
  "summary": "本次阶段工作的简要说明",
  "artifact_content": "该阶段正式产物的完整 UTF-8 文本",
  "actions": [
    {
      "tool_name": "filesystem.write_source",
      "arguments": {
        "path": "src/example.ts",
        "content": "export const example = true;\n",
        "expected_hash": null
      },
      "timeout_seconds": 30
    },
    {
      "tool_name": "shell.test",
      "arguments": { "command_index": 0 },
      "timeout_seconds": 900
    }
  ]
}
```

约束：

- `artifact_content` 必须存在；正式产物路径由后端按 Stage 固定，模型不能选择其他阶段路径。
- `actions` 最多 64 项，按顺序执行；重复写同一路径被拒绝。
- 文件覆盖必须携带工作区上下文中对应的 `expected_hash`；新文件使用 `null`。
- 命令只能引用 ProjectManifest 已登记的命令索引；模型不能提交任意 Shell 字符串。
- ToolService 返回非 `succeeded` 时立即停止，任务记为失败，不进入 Gate。
- JSON 解析或 Schema 验证失败时不得降级为“把自由文本当成已完成”。

## 5. API 与事件

新增用户级命令：

```text
POST /api/v1/workflows/{workflow_id}/orchestration/stream
Content-Type: application/json
Accept: application/x-ndjson
```

请求包含 `request_key`、`instruction`、`correlation_id`。响应帧覆盖准备、Stage 转换、Task、AgentRun、Agent 子帧、ToolCall、ArtifactVersion、Gate、Approval/Handoff、完成与错误。Renderer 只根据后端帧和重新查询的权威快照更新界面。

现有底层 REST 命令保留用于模块测试、诊断和受控恢复，但正式桌面主路径不得再由 Renderer 手工拼接这些命令。

## 6. 幂等与恢复

- 同一个 `request_key` 在同一 StageRun 中只能对应一个任务和一个正式 AgentRun。
- AgentRun 与 ToolCall 使用派生的稳定幂等键；断线重试不得重复写文件或重复运行命令。
- 应用退出时，Stage 5 恢复逻辑继续把运行中的 Task、AgentRun 与 ToolCall 标为中断并创建 RecoveryRecord。
- 用户确认恢复后，StageRun 回到 `discussing`；新请求键基于当前文件 Hash 重新规划。历史任务、调用、产物和错误全部保留。
- 如果崩溃发生在 ArtifactVersion 创建之后，编排服务从权威快照继续后续合法转换，不重复创建相同内容版本。
- `waiting_approval`、`warning_blocked`、`external_conflict` 不被后台静默越过，必须走现有用户审批、返工或冲突恢复路径。

## 7. 发布验收

解除阻塞必须同时满足：

1. 普通用户从 Stage 页面提交正式运行，不需要操作 Task、Tool、Artifact 或 Gate 的底层调试按钮。
2. 安装版 Fake Model E2E 从用户可见 UI 发起并完成 Planner 到 Deployer。
3. 至少验证 MANUAL Approval、AUTONOMOUS、工具失败、非法路径、模型计划无效、取消、应用重启恢复和外部冲突。
4. Renderer 不直接暴露内部 Event Ticket、Shutdown、Desktop Control 或未映射命令。
5. OpenAPI、前端类型、Preload 白名单、契约覆盖、安全测试与发布文档同步更新。
6. Windows 安装包重新构建，记录新的 SHA-256 与未签名状态。

完成上述证据前，产品只能标记为 API 驱动技术预览，不能标记为完整桌面 V1。
