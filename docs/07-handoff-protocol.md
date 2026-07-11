# 交接与变更协议

## 1. 目的

本文定义阶段之间传递正式结果的 `HandoffPacket`，以及下游发现上游问题时使用的 `ChangeRequest`。协议确保聊天室上下文隔离、项目版本稳定、产物可追踪和返工范围可计算。

## 2. 设计原则

- 不传递上游完整聊天历史。
- 只传递已锁定产物、项目检查点、正式决定和必要风险。
- 交接包是不可变版本对象。
- 被引用文件变化后交接包自动失效。
- 下游不能修改上游产物。
- 所有返工通过 ChangeRequest 和 Orchestrator 完成。

## 3. HandoffPacket

```text
HandoffPacket
├─ schema_version
├─ handoff_id
├─ project_id
├─ workflow_id
├─ source_stage_run_id
├─ source_stage
├─ target_stage
├─ stage_contract_version
├─ role_card_version
├─ project_checkpoint_ref
├─ deliverable_refs
├─ approved_decisions
├─ acceptance_criteria
├─ known_risks
├─ unresolved_non_blocking_items
├─ allowed_file_refs
├─ quality_gate_ref
├─ approval_ref
├─ created_at
├─ content_hash
└─ status
```

`status`：

```text
valid
invalidated
superseded
consumed
```

## 4. ProjectCheckpointRef

```text
ProjectCheckpointRef
├─ checkpoint_id
├─ root_hash
├─ git_head
├─ workspace_mode
├─ manifest_ref
├─ file_count
└─ created_at
```

HandoffPacket 不复制完整项目内容，只引用不可变检查点。接收阶段根据允许文件和 ProjectManifest 读取工作区内容。

## 5. DeliverableRef

```text
DeliverableRef
├─ artifact_id
├─ artifact_type
├─ artifact_version
├─ relative_path
├─ content_hash
├─ media_type
├─ created_by
└─ created_at
```

正式 Markdown 是人和 Agent 阅读的项目文档；Artifact 元数据由后端生成，Agent 不能直接伪造 approved、hash 或 version。

## 6. 创建流程

1. 当前阶段完成 Primary 草案。
2. 执行 Reviewer A/B 校正。
3. 执行确定性 Quality Gate。
4. 根据 MANUAL/AUTONOMOUS 完成阶段审批规则。
5. 创建不可变 ProjectCheckpoint。
6. 锁定 StageDeliverable 版本。
7. 后端生成 HandoffPacket。
8. 计算标准化 JSON 的 SHA-256。
9. 在同一事务中保存交接包、节点状态和 EventLog。
10. 解锁下一聊天室。

## 7. 接收验证

目标阶段开始前必须验证：

- HandoffPacket schema version 受支持。
- source/target 符合固定五阶段顺序。
- source Stage Run 已完成。
- Contract 和 RoleCard 版本存在。
- ProjectCheckpoint root hash 匹配。
- Deliverable 文件存在且 Hash 匹配。
- Quality Gate 允许交接。
- MANUAL 模式具有有效 approval_ref。
- HandoffPacket 状态为 `valid`。

任一失败时目标聊天室保持 `LOCKED`。

## 8. 允许上下文

目标阶段获得：

- 当前 RoleCard 和 StageContract。
- HandoffPacket 摘要。
- approved_decisions。
- acceptance_criteria。
- known_risks。
- deliverable_refs 指向的正式产物。
- allowed_file_refs 指向的必要项目文件。

不获得：

- 上游完整消息历史。
- 失败提案和未批准草稿。
- 次要模型内部上下文。
- API Key 和模型配置秘密。
- 未授权项目文件。

## 9. 失效规则

以下情况使 HandoffPacket 进入 `invalidated`：

- 被引用产物内容 Hash 变化。
- ProjectCheckpoint 被恢复或替换。
- 上游阶段重新打开。
- 合法 ChangeRequest 导致上游修订。
- 外部文件变化影响交接内容。
- Contract 或 RoleCard 明确迁移导致不兼容。

失效操作不删除旧包。新包生成后旧包进入 `superseded`。

## 10. ChangeRequest

```text
ChangeRequest
├─ schema_version
├─ change_request_id
├─ project_id
├─ workflow_id
├─ source_stage_run_id
├─ source_stage
├─ target_stage
├─ issue_type
├─ severity
├─ title
├─ description
├─ evidence_refs
├─ affected_requirements
├─ affected_artifacts
├─ affected_files
├─ requested_changes
├─ invalidation_scope
├─ created_at
└─ status
```

`status`：

```text
submitted
validated
rejected
applied
resolved
cancelled
```

## 11. ChangeRequest 路由

| 问题类型 | 目标阶段 |
|---|---|
| 目标、范围、需求、验收 | Planner |
| 架构、接口、数据、UI、任务设计 | Designer |
| 代码、测试、构建、实现 | Builder |
| 审查证据或 Verdict 自身错误 | Reviewer |
| 部署文档和部署配置 | Deployer |

请求不能跳过 Orchestrator 直接修改状态。

## 12. 请求处理

1. Source Stage 创建请求。
2. Orchestrator 验证目标是否为合法上游或当前阶段。
3. 验证 Evidence 和 affected items。
4. 计算最早失效阶段和下游范围。
5. 将目标阶段创建为新的 Stage Run。
6. 使目标阶段及下游 HandoffPacket 失效。
7. 将请求内容作为 revision feedback 交给目标阶段。
8. 目标阶段修订后重新 P2R、Gate 和交接。
9. 新包被目标下游消费后，请求进入 resolved。

## 13. 外部修改

文件监控发现外部修改时，后端创建系统型 ChangeRequest 或 ExternalChangeRecord。若修改与活动 Agent 写入冲突，先进入 `external_conflict`，不自动覆盖。

## 14. 版本兼容

- 所有协议对象具有 schema_version。
- 后端读取旧版本时使用显式迁移器。
- 不兼容字段不能静默忽略。
- 正在运行的工作流继续使用创建时版本。
- 用户明确迁移工作流时创建迁移事件和新检查点。

## 15. 安全规则

- HandoffPacket 由后端生成，不接受模型直接提供的 approved 状态。
- allowed_file_refs 必须是规范化项目相对路径。
- Hash 校验在读取实际文件后执行。
- 不允许符号链接逃逸项目根目录。
- Handoff 和 ChangeRequest 不包含密钥明文。
- 任何篡改都记录审计事件。

## 16. 验收标准

- 交接包能够引用完整项目检查点和多个正式产物。
- 目标阶段只获得允许上下文。
- 文件变化能自动使相关交接包失效。
- 下游问题只能通过 ChangeRequest 返回上游。
- 历史交接包可审计但不能再次被错误消费。
- 所有创建、验证、失效和解决操作均产生 EventLog。
