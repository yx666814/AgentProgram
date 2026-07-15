# 星协 V1 前端契约 Change Request v3

> 日期：2026-07-15
> 状态：阶段 7B Task 8 受控执行记录
> 后端基线：`origin/master` at `bd249607886f68bef07be20e0fff8ae6ece61d40`
> 前一版本：`FRONTEND-CONTRACT-CHANGE-REQUEST-v2.md`（保留，不覆盖）
> 适用范围：`FRONTEND-IMPLEMENTATION-EXECUTION-v1.md` Task 8

## 1. 目的

本版本保留 v1、v2 的全部冻结契约约束，并记录 S05-S07 治理、冲突与恢复页面实现时，执行文档目标字段和阶段 5 实际后端契约之间的差异。前端继续以 OpenAPI、`events.schema.json`、Capability Manifest 和后端源码行为为权威，不用展示性字段补造后端不存在的数据。

## 2. FileConflict 只提供三方 Hash

执行文档要求冲突页同时显示三方文件正文、最早受影响阶段、失效产出物和下游阶段。阶段 5 实际 `FileConflict` 契约只提供：

- `id`、`project_id`、`relative_path`；
- `baseline_content_hash`、`user_content_hash`、`agent_content_hash`；
- `status`、`resolution`、`version`、创建和解决时间。

它没有文件正文、文本差异、最早受影响阶段、失效 Artifact 或下游 Stage 字段。因此 Task 8 采用以下唯一真实行为：

- 冲突卡只显示相对路径和后端返回的三方 Hash；
- 不读取工作区文件，不在 Renderer 暴露文件系统；
- 不从路径或时间推断受影响阶段和产出物；
- 明确显示当前契约限制，不伪造三方文本 diff；
- 若后续需要完整三方正文和影响链，必须先由后端新增版本化查询契约。

## 3. 冲突解决使用实际枚举和前置条件

阶段 5 冻结的冲突解决枚举只有：

```text
keep_user
keep_agent
manual_merge
```

前端据此执行：

- `keep_user` 不提交 Agent Checkpoint 或合并 Hash；
- `keep_agent` 必须提交后端已存在的 Agent Checkpoint ID；
- `manual_merge` 必须提交 64 位 SHA-256 `merged_content_hash`，而不是在 Renderer 中写入文件正文；
- 决定使用冲突版本和项目版本进行并发控制；
- command 返回后等待实际 `file_conflict.resolved`，不把 HTTP 响应投影为持久完成；
- 后端返回的项目状态为 `preflight_required` 时，引导重新预检和 Gate，不直接显示完成。

## 4. restore-plan 是有副作用的 Command

执行文档把“恢复前展示计划”描述为恢复命令前的准备步骤。实际端点为：

```text
POST /api/v1/projects/{project_id}/checkpoints/{checkpoint_id}/restore-plan
```

该操作不是只读查询。后端会：

1. 为当前工作区创建 `pre_restore` 保护检查点；
2. 持久化该保护检查点；
3. 发布 `project.restore_planned`；
4. 返回覆盖路径、保留的额外路径和保护检查点。

因此 Task 8 的恢复流程固定为：

1. 用户点击“规划并恢复”后调用真实 restore-plan；
2. 使用返回的覆盖范围、保留范围和保护检查点显示原生确认；
3. 用户取消时不调用 restore command，但已由后端创建的保护检查点和 `project.restore_planned` 事件必须保留；
4. 用户确认后，把该保护检查点 ID 和项目版本提交给 restore command；
5. command 返回后等待实际 `project.checkpoint_restored`，失败时保留保护检查点和错误证据。

前端不得把“取消确认”描述为完全没有后端写入；它只保证没有执行最终恢复。

## 5. 不可变治理投影

- ArtifactVersion、HandoffPacket 和历史 Gate 结果只读，不提供覆盖编辑。
- MANUAL WARNING 只提供批准或要求重写；AUTONOMOUS WARNING 不提供人工批准捷径。
- CapabilityRequest 只有 `pending` 状态显示决定入口。
- 完成链只根据实际 Artifact、Reviewer、Gate、Approval/Policy、Checkpoint 和 Handoff 数据投影。
- 缺失的 Reviewer、Gate、审批、Checkpoint、Artifact 或 Handoff 不得由前端补齐为成功。
- 所有 command 的 HTTP 返回与持久事件确认保持分离。

## 6. 不变约束

- 不修改后端代码。
- 不在 Renderer 暴露 Token、Secret、文件系统、Shell、NDJSON 认证信息或原始 IPC。
- 不创建后端不存在的冲突正文、影响阶段、影响产出物、审批捷径或恢复成功状态。
- 不把 restore-plan 当作无副作用查询。
- 后续扩展 FileConflict 详情或恢复计划语义时，必须新增 Change Request 并重新生成契约快照。

## 7. 版本历史

| 版本 | 日期 | 变更 |
| --- | --- | --- |
| v1 | 2026-07-15 | 记录阶段 5 静态契约导出、实际 operationId、全局事件游标与冻结拼写。 |
| v2 | 2026-07-15 | 保留 v1；补充 Task 7 的 `message.appended`、NDJSON 模型流、StageContract 边界和缺失 Rolling Summary 契约。 |
| v3 | 2026-07-15 | 保留 v1/v2；补充 Task 8 的 FileConflict 三方 Hash 边界、冲突解决前置条件和 restore-plan 创建保护检查点的副作用。 |
