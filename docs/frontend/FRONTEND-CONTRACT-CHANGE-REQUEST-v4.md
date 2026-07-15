# 星协 V1 前端契约 Change Request v4

> 日期：2026-07-15
> 状态：阶段 7B Task 9 受控执行记录
> 后端基线：`origin/master` at `bd249607886f68bef07be20e0fff8ae6ece61d40`
> 前一版本：`FRONTEND-CONTRACT-CHANGE-REQUEST-v3.md`（保留，不覆盖）
> 适用范围：`FRONTEND-IMPLEMENTATION-EXECUTION-v1.md` Task 9

## 1. 目的

本版本保留 v1-v3 的全部冻结契约约束，并记录 S08 设置与 S09 诊断实现时，阶段 6 文档中的目标 Query/Command 与阶段 5 实际 OpenAPI、事件投递和 Schema 之间的差异。前端只启用真实存在且能够通过 DesktopPort 安全访问的能力。

## 2. 设置能力的实际范围

后端已经提供：

- `GET /api/v1/model-profiles`；
- `POST /api/v1/model-profiles`；
- `PUT /api/v1/model-profiles/{profile_id}`；
- `GET /api/v1/rooms/{room_id}/model-assignment`；
- `PUT /api/v1/rooms/{room_id}/model-assignment`；
- `GET /api/v1/system/info`。

后端没有：

- 全局 `SettingsQuery` 或应用设置写入接口；
- `ModelProfileTestCommand` 或能力探测接口；
- SecretStore Query/Command 或 Renderer 可用的 Secret Reference 创建桥；
- 按 Profile 聚合的最近调用状态或用量统计查询。

因此 S08 只实现 ModelProfile 列表、创建、更新和现有 Room 的三槽位分配。全局保存、模型测试、SecretStore、最近调用和聚合用量保持禁用或明确标注不可用，不显示假成功状态。

## 3. ModelProfile 不接收明文密钥

实际 ModelProfile 请求只包含：名称、Provider、Base URL、模型 ID、`credential_ref`、`masked_hint`，更新时另有启用状态和版本。

前端固定执行：

- 只提交已有凭证引用和已经脱敏的提示；
- 不提供 API Key、Token、密码或 Secret 明文输入框；
- 不把凭证明文写入 Renderer 状态、事件、日志、诊断视图或本地持久化；
- Provider 选项严格来自实际枚举：`openai_compatible`、`anthropic`、`fake`；
- Room 的 Primary、Reviewer A、Reviewer B 必须使用不同且已启用的 Profile。

## 4. ModelProfile 事件当前无法由工作流事件通道确认

后端创建和更新 ModelProfile 时会在同一事务写入：

```text
model_profile.created
model_profile.updated
```

但这两类事件没有 `workflow_id`，相关写入单元也没有配置 WebSocket delivery target。当前事件 replay 接口必须指定 `workflow_id`，DesktopPort 没有全局配置事件重放方法。因此 Renderer 当前无法可靠接收或重放这两类全局配置事件。

Task 9 采用受控降级：

1. command 返回后不显示“事件已确认完成”；
2. 重新调用 ModelProfile 列表查询，展示后端实际持久实体；
3. 明确显示仍等待 `model_profile.created` 或 `model_profile.updated`；
4. 若当前订阅意外收到相同 correlation 的真实事件，则升级为事件确认；
5. 阶段 8 若要完成严格实时确认，必须扩展全局事件投递或增加可重放的配置事件通道。

Room 分配使用 `_workflow_write_uow`，事件 `room_model_assignment.updated` 带 `workflow_id`、`room_id` 和 WebSocket delivery target，继续按持久事件确认。

## 5. 诊断能力的实际范围

后端已经提供：

- `GET /api/v1/health`；
- `GET /api/v1/readiness`；
- `GET /api/v1/system/info`；
- `GET /api/v1/events/replay?workflow_id=...&after_event_id=...`；
- `GET /api/v1/workflows/{workflow_id}/tool-calls`；
- `GET /api/v1/recovery`。

后端没有 Diagnostics Summary、Diagnostics Export、日志摘要、数据库版本、Worker/Tool 进程状态、保留策略或清理策略接口。`system/info` 只返回 `backend_version` 和 `protocol_version`；readiness 只证明服务与数据库当前 Ready，不提供数据库版本。

因此 S09 只展示真实健康状态、版本、工作流事件重放、ToolCall 元数据、恢复记录和当前 Renderer 事件游标。缺失能力保持禁用并显示具体原因。

## 6. 事件和 ToolCall 的脱敏投影

实际 `EventEnvelope` 没有独立 `stage` 或 `result` 字段。前端只在 payload 明确包含 `stage`、`target_stage`、`status`、`result`、`resolution` 或 `error_code` 标量时展示对应值，不从事件类型推断业务结果，也不渲染完整 payload。

ToolCall 的 `result` 是任意 JSON，可能包含项目内容。诊断页只展示：

- Tool 名称和 Capability；
- 项目、工作流、StageRun、Task 和 Call ID；
- `arguments_hash`；
- 状态、错误代码和时间。

诊断页不渲染任意 Event payload、ToolCall result、源码、完整聊天、密钥或 Token。由于没有 DiagnosticsExport operation，“导出诊断包”保持禁用。

## 7. 不变约束

- 不修改后端代码。
- 不为缺失的 Settings、SecretStore、ModelProfileTest、Diagnostics 或 Export 创建第二套前端协议。
- 不把 ModelProfile command 返回或 read-after-write 伪称为持久事件已确认。
- 不把 readiness 伪称为数据库版本或完整进程诊断。
- 不展示任意事件 payload 或工具结果正文。
- 后续增加全局配置事件通道、SecretStore、模型测试或诊断导出时，必须新增 Change Request 并重新生成契约快照。

## 8. 版本历史

| 版本 | 日期 | 变更 |
| --- | --- | --- |
| v1 | 2026-07-15 | 记录阶段 5 静态契约导出、实际 operationId、全局事件游标与冻结拼写。 |
| v2 | 2026-07-15 | 保留 v1；补充 Task 7 的 `message.appended`、NDJSON 模型流、StageContract 边界和缺失 Rolling Summary 契约。 |
| v3 | 2026-07-15 | 保留 v1/v2；补充 Task 8 的 FileConflict 三方 Hash 边界、冲突解决前置条件和 restore-plan 副作用。 |
| v4 | 2026-07-15 | 保留 v1-v3；补充 Task 9 的实际设置/诊断能力、ModelProfile 全局事件投递缺口和诊断脱敏边界。 |
