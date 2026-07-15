# 星协 V1 前端契约 Change Request v2

> 日期：2026-07-15
> 状态：阶段 7B Task 7 受控执行记录
> 前一版本：`FRONTEND-CONTRACT-CHANGE-REQUEST-v1.md`（保留，不覆盖）
> 适用范围：`FRONTEND-IMPLEMENTATION-EXECUTION-v1.md` Task 7

## 1. 目的

本版本保留 v1 的全部冻结契约约束，并记录五阶段工作区实现时发现的执行文档术语与阶段 5 实际契约差异。前端继续以 OpenAPI、`events.schema.json`、Capability Manifest 和后端源码行为为权威，不为满足旧术语创建第二套事件或桌面协议。

## 2. 实际消息确认事件

执行文档 Task 7 使用 `message.created` 表述持久化消息确认；阶段 5 实际发布事件为：

```text
message.appended
```

前端因此采用以下唯一行为：

- `POST /api/v1/rooms/{room_id}/messages` 返回后，界面显示“等待 `message.appended`”。
- 只有收到同一 `message_id` 的持久化事件后，才重新查询该 Room 的消息历史。
- 消息不提供编辑或删除；更正使用 `correction_of_id` 创建新的不可变消息。
- 切换阶段重新按目标 `room_id` 查询，禁止复用其他 Room 的消息或草稿上下文。

## 3. 模型流并非持久化事件

执行文档提到的 `model.delta` 不在阶段 5 的 41 个实际事件类型中。后端真实模型输出接口为：

```text
POST /api/v1/agent-runs/{run_id}/stream
Content-Type: application/x-ndjson
```

当前已冻结 `DesktopPort` 仅提供 `query`、`command`、事件订阅和 replay，没有流式 AgentRun 方法。Renderer 因此不得：

- 伪造 `model.delta` 事件；
- 把普通 command payload 假装成 NDJSON 流；
- 绕过 Preload 直接请求带认证的流式端点；
- 显示不存在的实时模型成功状态。

Task 7 只显示 `AgentRunListResponse`、`AgentRunSnapshot` 和 `ToolCallList` 中已经持久化的状态、调用 ID、用量引用与错误代码。若阶段 8 需要实时流，必须版本化扩展 `DesktopPort`，并增加认证代理、取消、背压、断线和脱敏测试。

## 4. StageContract 的边界

阶段 5 `StageContract` 描述工具能力、路径范围、默认能力、可申请能力和永久禁止能力；它不是第二套 UI Command 列表。前端采取以下规则：

- 工具卡只呈现后端查询返回的 ToolCall，不直接执行文件、Shell、Build 或 Test。
- UI 的消息、任务、阶段转换和 reopen 只调用实际 OpenAPI operation。
- 锁定、完成、Room consultation 和 Workflow 状态由后端快照决定，前端不在本地解锁。
- `Rolling Summary` 和独立决策查询当前不存在，界面不生成假摘要或假决策记录。

## 5. Task 7 受控验收映射

| 设计语义 | 实际后端契约 | 前端行为 |
| --- | --- | --- |
| 消息确认 | `message.appended` | 等待事件后重查 Room |
| 模型临时流 | NDJSON stream，非 EventEnvelope | 当前只显示持久 AgentRun 状态 |
| 任务排队/启动/取消 | `task.queued` / `task.started` / `task.cancelled` | command 返回后等待对应事件 |
| 阶段切换 | `stage_run.transitioned` | 等待目标 StageRun 事件 |
| 完成后修改 | `stage_run.reopened` | 原生确认失效范围后等待事件 |
| 工具执行 | ToolCall Query + 后端鉴权 | Renderer 只读展示 |

## 6. 不变约束

- 不修改后端代码。
- 不在 Renderer 暴露 Token、Secret、文件系统、Shell、NDJSON 认证信息或原始 IPC。
- 不把 HTTP 返回当作持久事件确认。
- 不创建后端不存在的 `message.created`、`model.delta`、Rolling Summary Query 或本地工具执行器。
- 后续扩展实时模型流必须新增 Change Request 和 DesktopPort 契约版本。

## 7. 版本历史

| 版本 | 日期 | 变更 |
| --- | --- | --- |
| v1 | 2026-07-15 | 记录阶段 5 静态契约导出、实际 operationId、全局事件游标与冻结拼写。 |
| v2 | 2026-07-15 | 保留 v1；补充 Task 7 的 `message.appended`、NDJSON 模型流、StageContract 边界和缺失 Rolling Summary 契约。 |
