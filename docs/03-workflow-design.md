# 五阶段工作流设计

## 1. 总体结构

MVP 使用固定线性工作流：

```text
Planner
   ↓ Requirements Handoff
Designer
   ↓ Design Handoff
Builder
   ↓ Build Handoff
Reviewer
   ↓ Approved Handoff
Deployer
```

正常路径是线性的，返工路径可以从 Reviewer 或质量门返回上游阶段。

## 2. 编排器职责

`Orchestrator` 是后端控制平面，负责：

- 保存项目和工作流状态。
- 决定哪个阶段可以运行。
- 启动、暂停、恢复和取消任务。
- 调用阶段质量门。
- 创建和验证交接包。
- 管理用户审批。
- 执行返工路由。
- 持久化状态和事件。
- 防止同一项目并发执行多个工作流任务。

`Orchestrator` 不参与业务讨论，不生成需求、设计、代码、审查或交付内容。

## 3. 工作流状态

工作流使用以下状态：

| 状态 | 含义 |
|---|---|
| `created` | 已创建，尚未启动 |
| `running` | 正在执行当前阶段 |
| `waiting_user` | 等待用户输入或审批 |
| `paused` | 已暂停，不得启动新任务 |
| `revising` | 正在执行返工阶段 |
| `failed` | 因不可恢复错误或超过返工上限停止 |
| `stopped` | 用户主动停止 |
| `completed` | 五个阶段全部完成 |

## 4. 阶段节点状态

每个阶段节点使用以下状态：

| 状态 | 含义 |
|---|---|
| `locked` | 上游尚未完成，不能进入 |
| `ready` | 输入已就绪，可以开始 |
| `discussing` | 用户和 Agent 正在讨论 |
| `producing` | 正在生成或修改正式产出物 |
| `quality_checking` | 正在执行自动质量门 |
| `waiting_approval` | 等待用户决定 |
| `handoff_ready` | 已通过检查，可以生成或发送交接包 |
| `completed` | 阶段及交接已经完成 |
| `needs_fix` | 需要本阶段或上游返工 |
| `failed` | 阶段执行失败 |
| `cancelled` | 阶段任务被取消 |

## 5. 正常阶段流程

每个阶段遵循同一生命周期：

1. 验证上游 `HandoffPacket`。
2. 将允许内容载入当前聊天室上下文。
3. 用户与一个或多个 Agent 讨论。
4. 形成正式阶段产出物。
5. 执行自动质量门。
6. 如果策略要求，创建用户审批。
7. 用户批准后锁定本次产出版本。
8. 生成目标明确的 `HandoffPacket`。
9. 将当前阶段标记为 `completed`。
10. 解锁下一阶段。

任何步骤失败都不能跳过门禁直接推进。

## 6. 阶段交接包

`HandoffPacket` 至少包含：

```text
id
project_id
workflow_id
source_stage
target_stage
artifact_versions
summary
approved_decisions
acceptance_criteria
known_risks
unresolved_non_blocking_issues
allowed_files
gate_result
user_approval
created_at
checksum
```

约束：

- `source_stage` 必须是当前已通过阶段。
- `target_stage` 必须符合工作流边关系。
- `artifact_versions` 必须引用已锁定版本。
- `allowed_files` 必须是项目目录内的规范化相对路径。
- `gate_result` 必须允许放行。
- 需要人工审批的阶段必须包含批准记录。
- 修改任何被引用产出物后，旧交接包不能继续用于新的下游执行。

## 7. 上下文隔离规则

下游阶段可以读取：

- 当前阶段系统提示词。
- 用户在当前聊天室的消息。
- 当前聊天室 Agent 的消息。
- 上游正式交接包。
- 交接包允许的正式产出物和项目文件。
- 当前阶段已经产生的工具结果和决策。

下游阶段默认不能读取：

- 上游完整聊天历史。
- 上游失败提案和未批准草稿。
- 其他阶段的模型密钥或内部配置。
- 未列入 `allowed_files` 的敏感文件。

如果用户需要引用上游讨论，应先把必要信息整理成正式决定或补充交接包。

## 8. 质量门结果

| 结果 | 行为 |
|---|---|
| `PASS` | 可以进入审批或交接 |
| `WARNING` | 记录风险，由策略或用户决定是否放行 |
| `NEEDS_FIX` | 阻止交接，执行返工 |
| `FAIL` | 阻止交接并将阶段或工作流标记为失败 |

## 9. 返工路由

### 9.1 Planner 返工

适用于需求缺失、验收标准不可执行或用户目标发生变化。Planner 返工后，Designer 及其下游结果全部失效。

### 9.2 Designer 返工

适用于架构、接口、数据模型、交互或任务拆分问题。Designer 返工后，Builder 及其下游结果全部失效。

### 9.3 Builder 返工

适用于代码、测试、构建和实现偏差。Builder 返工后，Reviewer 与 Deployer 结果失效。

### 9.4 Deployer 自身重试

仅当问题属于打包命令、交付说明或可重复的环境操作时，Deployer 可以在本阶段重试。代码或构建配置问题应返回 Builder。

## 10. 暂停、继续和停止

### 暂停 `pause`

- 不再启动新的模型或工具任务。
- 已执行中的任务收到取消或安全暂停信号。
- 当前持久化状态保持可恢复。
- 用户审批仍可记录，但在恢复前不启动下游执行。

### 继续 `resume`

- 重新验证项目目录和所需产出物。
- 检查是否存在中断任务。
- 从最后一个一致状态继续。

### 停止 `stop`

- 取消活动任务。
- 关闭当前执行实例。
- 保留聊天、产出物和审计记录。
- 后续重新执行必须由用户明确发起。

## 11. 并发规则

- 一个项目同一时刻只能有一个改变工作流状态的执行器。
- 同一聊天室可以并行调用多个参与模型。
- 协调模型必须等待参与提案结束、失败或超时后再汇总。
- 工具调用是否并行由工具风险和文件冲突策略决定。
- 对同一文件的写入必须串行化或通过版本冲突检查。

## 12. 完成条件

工作流只有在以下条件全部满足时才能进入 `completed`：

- 五个阶段均为 `completed`。
- Reviewer 最终结论为 `PASS`。
- Deployer 的交付质量门通过。
- 最终产出物、校验值和交付说明存在。
- 所有阻断审批已经完成。
