# REST、WebSocket 与事件协议

## 1. 范围

后端仅服务本机 Electron 桌面端，默认监听 `127.0.0.1` 的随机可用端口。API 使用 `/api/v1`，WebSocket 使用同一服务。

## 2. 本地认证

Electron 启动后端时生成高强度随机 session token，通过受保护启动环境传入。REST 使用：

```text
Authorization: Bearer <local-session-token>
```

浏览器 WebSocket API 不能自由设置 Authorization Header，因此先申请一次性 Ticket：

```text
POST /api/v1/auth/ws-ticket
```

返回短时、单次使用的 `ticket`，连接：

```text
ws://127.0.0.1:<port>/api/v1/events?ticket=<ticket>&after=<event_id>
```

Ticket 使用后立即失效。后端校验 Origin、进程会话和过期时间。

## 3. 通用响应

成功：

```json
{
  "data": {},
  "meta": {
    "request_id": "req-..."
  }
}
```

错误：

```json
{
  "error": {
    "code": "workflow.invalid_state",
    "message": "当前工作流不能启动",
    "details": {},
    "retryable": false
  },
  "meta": {
    "request_id": "req-..."
  }
}
```

错误消息不得包含 API Key、Authorization、完整环境变量和项目外绝对路径。

## 4. 幂等与并发

创建任务、启动工作流、重写、审批、冲突解决等命令支持：

```text
Idempotency-Key: <uuid>
```

资源更新使用 `version` 或 ETag。过期版本返回 `409 resource.version_conflict`。

## 5. 健康与生命周期

```text
GET  /api/v1/health
GET  /api/v1/readiness
POST /api/v1/system/shutdown
GET  /api/v1/system/info
```

`readiness` 只有数据库、迁移、事件系统和 Worker Supervisor 就绪后才成功。

## 6. 项目与工作区

```text
GET    /api/v1/projects
POST   /api/v1/projects
GET    /api/v1/projects/{project_id}
PATCH  /api/v1/projects/{project_id}
DELETE /api/v1/projects/{project_id}

POST /api/v1/projects/{project_id}/preflight
GET  /api/v1/projects/{project_id}/preflight/latest
GET  /api/v1/projects/{project_id}/manifest
PUT  /api/v1/projects/{project_id}/manifest
GET  /api/v1/projects/{project_id}/workspace/status
```

原生目录选择由 Electron Main Process 完成，后端不弹出 GUI 对话框。

## 7. 工作流

```text
POST /api/v1/projects/{project_id}/workflows
GET  /api/v1/workflows/{workflow_id}
POST /api/v1/workflows/{workflow_id}/start
POST /api/v1/workflows/{workflow_id}/pause
POST /api/v1/workflows/{workflow_id}/resume
POST /api/v1/workflows/{workflow_id}/stop
POST /api/v1/workflows/{workflow_id}/abandon
```

审批模式在创建 Workflow 时确定：

```text
approval_mode: manual | autonomous
```

运行中切换模式必须先 pause，并使用专门命令记录事件：

```text
POST /api/v1/workflows/{workflow_id}/approval-mode
```

## 8. 阶段与重写

```text
GET  /api/v1/workflows/{workflow_id}/stages
GET  /api/v1/stage-runs/{stage_run_id}
POST /api/v1/stage-runs/{stage_run_id}/rewrite
POST /api/v1/stage-runs/{stage_run_id}/open-room
POST /api/v1/stage-runs/{stage_run_id}/reopen
```

`warning_blocked` 状态允许：

```text
rewrite
open_room
abandon
```

不提供 ignore-and-continue。

## 9. 聊天室和消息

```text
GET  /api/v1/projects/{project_id}/rooms
GET  /api/v1/rooms/{room_id}
GET  /api/v1/rooms/{room_id}/messages
POST /api/v1/rooms/{room_id}/messages
POST /api/v1/messages/{message_id}/correct
POST /api/v1/messages/{message_id}/pin
DELETE /api/v1/messages/{message_id}/pin
POST /api/v1/messages/{message_id}/hide
POST /api/v1/rooms/{room_id}/consultations
```

消息不能 PATCH 修改。更正创建新消息。已参与正式决定、产物或交接的消息不能隐藏。

同一 Room 同时只能有一个活动 Primary Task。任务运行中发送的新消息进入队列。

## 10. 任务

```text
GET  /api/v1/tasks/{task_id}
POST /api/v1/tasks/{task_id}/cancel
GET  /api/v1/rooms/{room_id}/task-queue
DELETE /api/v1/rooms/{room_id}/task-queue/{message_id}
```

取消只停止未完成执行，不删除已经持久化的消息、事件和工具记录。

## 11. 模型档案与聊天室槽位

```text
GET    /api/v1/model-profiles
POST   /api/v1/model-profiles
GET    /api/v1/model-profiles/{profile_id}
PATCH  /api/v1/model-profiles/{profile_id}
DELETE /api/v1/model-profiles/{profile_id}
POST   /api/v1/model-profiles/{profile_id}/test

GET /api/v1/rooms/{room_id}/models
PUT /api/v1/rooms/{room_id}/models
```

PUT assignments 最多包含 primary、reviewer_a、reviewer_b；Primary 必须存在。同一 Room 不能重复使用 ModelProfile 或 credential_ref，保证每个槽位独立 API Key。API 只返回 masked_hint，不返回 API Key。

## 12. 阶段审批和权限申请

```text
GET  /api/v1/approvals
POST /api/v1/approvals/{approval_id}/decision

GET  /api/v1/capability-requests
GET  /api/v1/capability-requests/{request_id}
POST /api/v1/capability-requests/{request_id}/approve
POST /api/v1/capability-requests/{request_id}/reject
```

阶段审批只存在于 MANUAL。CapabilityRequest 在 MANUAL 和 AUTONOMOUS 中都可能出现并必须由用户处理。

## 13. Gate、ChangeRequest 和 Handoff

```text
GET  /api/v1/stage-runs/{stage_run_id}/quality-gates
GET  /api/v1/quality-gates/{gate_run_id}

GET  /api/v1/change-requests
GET  /api/v1/change-requests/{request_id}
POST /api/v1/change-requests/{request_id}/cancel

GET /api/v1/handoffs/{handoff_id}
GET /api/v1/stage-runs/{stage_run_id}/handoff
```

HandoffPacket 由后端生成，无直接创建或修改 API。

## 14. 产物和检查点

```text
GET  /api/v1/projects/{project_id}/artifacts
GET  /api/v1/artifacts/{artifact_id}
GET  /api/v1/artifacts/{artifact_id}/versions
GET  /api/v1/artifact-versions/{version_id}/content

GET  /api/v1/projects/{project_id}/checkpoints
GET  /api/v1/checkpoints/{checkpoint_id}
POST /api/v1/checkpoints/{checkpoint_id}/restore
```

恢复前必须创建保护检查点并检查外部冲突。

## 15. 外部修改和冲突

```text
GET  /api/v1/projects/{project_id}/external-changes
GET  /api/v1/file-conflicts/{conflict_id}
POST /api/v1/file-conflicts/{conflict_id}/resolve
```

解决方式：

```text
keep_user
keep_agent
manual_merge
```

后端不提供静默自动覆盖。

## 16. 用量与审计

```text
GET /api/v1/projects/{project_id}/usage
GET /api/v1/rooms/{room_id}/usage
GET /api/v1/model-profiles/{profile_id}/usage
GET /api/v1/projects/{project_id}/events
GET /api/v1/projects/{project_id}/tool-calls
```

模型费用只统计，不限制。

## 17. WebSocket Event Envelope

```json
{
  "schema_version": 1,
  "event_id": 1284,
  "event_type": "task.model.delta",
  "project_id": "...",
  "workflow_id": "...",
  "room_id": "...",
  "task_id": "...",
  "timestamp": "...",
  "payload": {}
}
```

客户端提供 `after`，服务端从 event_id 之后重放。UI 必须按 event_id 去重，不用本地接收时间覆盖服务端时间。

## 18. 事件分类

```text
system.ready
system.stopping
project.created
project.preflight_completed
workflow.started
workflow.paused
workflow.resumed
workflow.stopped
workflow.abandoned
stage.state_changed
stage.warning_blocked
stage.reopened
room.state_changed
message.created
message.corrected
task.queued
task.started
task.cancelled
task.completed
task.failed
model.started
model.delta
model.completed
p2r.review_completed
tool.requested
tool.authorization_required
tool.started
tool.completed
tool.failed
artifact.version_created
checkpoint.created
checkpoint.invalidated
quality_gate.completed
approval.requested
approval.decided
capability.requested
capability.decided
change_request.created
handoff.created
handoff.invalidated
external_change.detected
file_conflict.created
file_conflict.resolved
worker.started
worker.interrupted
```

## 19. 流式模型输出

`model.delta` 仅用于临时 UI 展示，不逐 token 写数据库。任务完成后将最终消息作为 `message.created` 原子持久化。任务失败时可以保存明确标记的 partial content，但不能成为正式产物。

## 20. 分页

消息、事件、工具调用和用量使用 cursor 分页，不使用大 offset：

```text
?after=<sequence>&limit=100
```

## 21. 验收标准

- 未认证本机请求不能访问 REST/WebSocket。
- WebSocket 可以从 event_id 可靠重放和去重。
- 重复 Idempotency-Key 不会重复启动任务。
- API 不返回密钥明文。
- Worker 或工具失败能映射为稳定错误代码。
- 所有改变工作流状态的 API 都经过应用服务和事务，而不是路由直接修改数据库。
