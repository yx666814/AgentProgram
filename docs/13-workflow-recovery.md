# 工作流控制、并发与恢复

## 1. 目标

工作流必须在模型超时、工具失败、Worker 崩溃、桌面退出、外部文件修改和数据库迁移后保持一致，不能只修改显示状态。

## 2. 工作流状态

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

## 3. Stage Run 状态

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

状态转换只能通过 Application Command 和 Domain Rule，不能由 API 路由、Worker 或模型直接赋值。

## 4. 单执行器规则

- 一个项目最多一个 running workflow。
- 一个 Room 最多一个活动 Primary Task。
- 同一项目只有当前活动阶段拥有写能力。
- P2R 的 Reviewer A/B 可以并行。
- 文件写入按路径锁或版本检查串行化。
- Workflow Command 使用数据库版本号与项目级 async lock。

数据库唯一约束是最终防线，进程内锁仅用于减少冲突。

## 5. Start

启动前：

1. 验证 Idempotency-Key。
2. 检查没有其他 running workflow。
3. 执行 Project Preflight。
4. 验证当前 Stage Contract 和 RoleCard 版本。
5. 创建或恢复 Project Worker。
6. 在事务中更新状态并追加 workflow.started。

重复 start 返回已有执行结果，不创建第二个任务。

## 6. Pause

Pause 不是标签修改：

1. 工作流状态进入 pause_requested。
2. 不再启动新模型和工具任务。
3. 当前模型请求收到取消信号。
4. 当前 Tool Process 安全终止。
5. 保存已确认消息、工具记录和中断点。
6. Task 进入 interrupted 或 cancelled。
7. 状态最终进入 paused。

CapabilityRequest 和阶段审批可以在 paused 时记录，但恢复前不推进阶段。

## 7. Resume

恢复前：

- 检查工作区存在。
- 检查文件 Hash 和外部修改。
- 检查未解决冲突。
- 检查 HandoffPacket 和 Checkpoint 仍有效。
- 检查 ModelProfile 可用。
- 创建新 Worker。

恢复从最后一个数据库一致状态开始，不尝试继续半个模型响应或半个 ToolCall。

## 8. Stop 与 Abandon

### stop

- 取消活动任务。
- 保留项目、聊天、产物和检查点。
- 工作流可以由用户明确重新启动或复制。

### abandon

- 表示用户放弃该工作流结果。
- 保留全部历史和项目文件。
- 不再允许继续当前 Workflow ID。
- 用户可从某个检查点创建新工作流。

Direct Workspace 文件不会随 stop/abandon 删除。

## 9. Warning Blocked

AUTONOMOUS 遇到 WARNING：

- 不锁定产物。
- 不生成 HandoffPacket。
- 状态进入 warning_blocked。
- 等待用户选择 rewrite、open_room 或 abandon。
- 不提供 ignore-and-continue。

Rewrite 次数无限制但完整记录。连续相同 Warning 时提示无进展，不自动停止用户继续重写。

## 10. ChangeRequest 返工

合法请求由 Orchestrator：

1. 计算最早目标阶段。
2. 创建新的 Stage Run。
3. 使目标阶段和下游 HandoffPacket 失效。
4. 保留历史 Stage Run 和产物版本。
5. 将结构化反馈送入目标聊天室。
6. 目标阶段完成后生成新交接链。

下游不能直接编辑上游产物。

## 11. 已完成阶段重开

Completed Room 默认只读咨询。用户显式 reopen：

- 创建新 Stage Run。
- 目标及下游进入 invalidated/revision path。
- 恢复目标阶段默认工具。
- 旧结果保留可审计。

## 12. Worker 崩溃

主进程根据 heartbeat 检测：

- 标记 Worker unavailable。
- 停止接受其后续输出。
- 终止残留进程树。
- 活动 Task 进入 interrupted。
- 保留最后 ACK 的 sequence。
- 广播 worker.interrupted。
- 用户重试时启动新 Worker。

没有 ACK 的 Worker “完成”不能写入正式状态。

## 13. Tool Process 崩溃

- 保存退出码、stderr 和受影响文件 Hash。
- 检查是否发生部分写入。
- 原子写工具不会暴露半文件。
- 非原子外部命令可能修改项目时，创建检查点差异并标记需要检查。
- ToolCall failed，Primary 获得真实错误。

## 14. 应用异常退出

下次启动：

1. 检查数据库完整性和 migration。
2. 将遗留 running Task/Worker 标记 interrupted。
3. 清理已不存在的 PID lease。
4. 检查快照临时文件和未完成 manifest。
5. 恢复 Event Outbox。
6. 检查工作区外部变化。
7. 向用户展示可恢复项目。

不自动重新执行模型和工具任务。

## 15. EventLog 与 Outbox

状态更新、EventLog 和 Outbox 同一事务。Outbox Dispatcher 发送成功后标记 delivered。桌面断开不会丢事件，重连使用 event_id 重放。

## 16. 外部文件变化

非冲突变化：

- 创建 ExternalChangeRecord。
- 计算最早 owner stage。
- 使该阶段及下游结果失效。
- 当前工作流暂停到 waiting_user 或 external_conflict。

同文件并发变化：

- 停止 Agent 最终写入。
- 保存 base/agent/user 版本。
- 创建 FileConflict。
- 用户选择 keep_user、keep_agent 或 manual_merge。
- 解决后重新 Gate。

## 17. 检查点恢复

恢复前创建保护检查点。恢复是显式用户操作：

- 不移动 Direct Workspace 用户 Git 分支。
- 不覆盖未解决外部冲突。
- 恢复后验证 root_hash。
- 根据检查点阶段重建工作流可用状态。
- 旧的未来阶段结果全部失效。

## 18. 数据库故障

- 每次正式桌面升级前 SQLite Backup。
- Migration 失败恢复备份。
- integrity_check 失败拒绝正常启动，进入恢复模式。
- 不在损坏数据库上继续运行 Agent。

## 19. 模型不可用

- Primary 不可用：当前 Task 失败，等待用户修复 ModelProfile 或重试。
- 单个 Reviewer 不可用：正式 P2R 不能通过；普通 P0 不受影响。
- API Key 失效：只报告 Profile，错误内容脱敏。
- 不自动切换到未配置模型。

## 20. 验收标准

- Pause 会真实停止任务和进程树。
- 重复 Start 不创建并发工作流。
- Worker 崩溃后不产生虚假完成。
- 应用重启后可以恢复到最后一致状态。
- Warning、ChangeRequest、外部修改和重开阶段具有明确失效范围。
- 事件在桌面断线时不丢失。
