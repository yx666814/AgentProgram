# 数据模型与持久化

## 1. 技术选择

```text
SQLite
SQLAlchemy 2.x Async
aiosqlite
Alembic
Pydantic v2
Repository + UnitOfWork
```

数据库不做整体加密，依赖操作系统用户目录权限。API Key 只保存在系统安全存储，数据库保存 credential_ref 和脱敏提示。

## 2. 数据位置

```text
%LOCALAPPDATA%/AgentProgram/
├─ data/agent.db
├─ snapshots/
├─ logs/
├─ workers/
├─ cache/
└─ backups/
```

项目目录保存：

```text
.agent/
├─ project.json
├─ project-manifest.json
├─ contracts.json
└─ .agentignore
```

聊天、事件、快照和密钥不写入项目仓库。

## 3. SQLite 配置

```sql
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;
PRAGMA synchronous = NORMAL;
PRAGMA busy_timeout = 5000;
PRAGMA temp_store = MEMORY;
```

只有 Backend Main Process 写数据库。Worker 不持有数据库连接。

## 4. 核心实体

### projects

```text
id
name
description
workspace_id
current_workflow_id
state
created_at
updated_at
deleted_at
```

### workspaces

```text
id
project_id
mode                 # managed / direct
root_path
manifest_version
current_checkpoint_id
watch_state
created_at
```

### workflows

```text
id
project_id
approval_mode        # manual / autonomous
state
contract_set_version
role_card_set_version
current_stage
created_at
started_at
completed_at
```

### stage_runs

每次重新打开或返工创建新的 Stage Run，而不是覆盖历史。

```text
id
workflow_id
stage
run_number
state
room_id
input_handoff_id
output_handoff_id
revision_count
started_at
completed_at
failure_reason
```

### rooms

```text
id
project_id
stage
state                # locked / ready / active / completed / consultation
active_stage_run_id
created_at
```

### messages

```text
id
room_id
stage_run_id
sequence
message_type
sender_type
sender_id
content
reply_to_id
correction_of_id
is_pinned
is_hidden_in_ui
created_at
```

消息不可修改。更正通过 correction_of_id 创建新消息。隐藏只影响 UI，不删除审计数据。

### conversation_summaries

```text
id
room_id
from_sequence
to_sequence
summary
source_hash
version
created_at
```

## 5. 模型实体

### model_profiles

```text
id
display_name
provider
model
base_url
credential_ref
masked_hint
capabilities_json
context_limit
default_parameters_json
enabled
created_at
updated_at
```

### room_model_assignments

```text
id
room_id
slot                 # primary / reviewer_a / reviewer_b
profile_id
room_parameters_json
enabled
```

每个 Room 的 slot 唯一，Primary 必须存在，Reviewer 可选。同一 Room 的启用槽位必须引用不同 ModelProfile，且 credential_ref 必须互不相同，保证三个模型独立密钥和独立计费。

### model_calls

```text
id
task_id
room_id
slot
profile_id
provider_request_id
input_tokens
output_tokens
cached_input_tokens
estimated_cost
duration_ms
status
error_type
started_at
completed_at
```

成本只记录展示，不设置费用上限。

## 6. 任务与 Worker

### tasks

```text
id
project_id
room_id
stage_run_id
task_type
state
requested_by
active_worker_id
queued_message_id
created_at
started_at
completed_at
cancel_requested_at
error_json
```

每个 Room 同时只允许一个活动 Primary Task。

### workers

```text
id
project_id
pid
state
protocol_version
last_heartbeat_at
active_task_id
started_at
stopped_at
```

### ipc_messages

只保存需要审计或重放的重要 IPC 元数据，不保存所有流式 chunk。

```text
id
worker_id
message_id
correlation_id
sequence
message_type
status
persisted_event_id
created_at
```

## 7. 产物与检查点

### artifacts

```text
id
project_id
stage
artifact_type
current_version_id
created_at
```

### artifact_versions

```text
id
artifact_id
version
relative_path
content_hash
media_type
size
status
stage_run_id
created_by
created_at
```

### project_checkpoints

```text
id
project_id
workflow_id
stage_run_id
workspace_mode
root_hash
git_head
manifest_uri
file_count
total_size
status
created_at
```

### checkpoint_files

```text
checkpoint_id
relative_path
content_hash
object_uri
size
file_mode
modified_at
```

文件内容存入快照对象存储，SQLite 只保存引用。

## 8. 交接与质量

### handoff_packets

保存 07 文档定义的结构化字段、标准化 JSON 和 content_hash。

### quality_gate_runs

```text
id
stage_run_id
status
contract_version
started_at
completed_at
summary
```

### quality_gate_issues

```text
id
gate_run_id
severity
code
message
evidence_ref
affected_file
is_blocking
```

### approvals

只用于 MANUAL 阶段审批：

```text
id
stage_run_id
decision
feedback
created_at
decided_at
```

### change_requests

保存结构化问题、证据、路由、失效范围和解决状态。

### capability_requests

```text
id
project_id
stage_run_id
task_id
requester_role
requested_capability
reason
target_paths_json
proposed_command_json
expected_changes_json
risk_level
status
created_at
decided_at
expires_at
```

所有模式下均由用户弹窗决定合法 CapabilityRequest。

## 9. 工具、文件变化和冲突

### tool_calls

```text
id
task_id
request_id
tool_name
arguments_redacted_json
policy_decision
capability_request_id
status
exit_code
output_ref
affected_files_json
started_at
completed_at
```

### external_changes

```text
id
project_id
relative_path
old_hash
new_hash
owner_stage
detected_at
status
```

### file_conflicts

```text
id
project_id
task_id
relative_path
base_ref
agent_ref
user_ref
resolution
resolved_ref
created_at
resolved_at
```

## 10. EventLog 与 Outbox

### event_log

```text
id                   # 单调递增
project_id
workflow_id
room_id
task_id
event_type
aggregate_type
aggregate_id
payload_json
created_at
```

历史事件不可修改，只能追加纠正事件。

### outbox_events

```text
id
event_log_id
delivery_state
attempt_count
last_attempt_at
delivered_at
```

重要状态更新与 EventLog/Outbox 在同一事务提交。WebSocket 只广播已提交事件。

## 11. Repository

至少提供：

```text
ProjectRepository
WorkflowRepository
StageRunRepository
RoomRepository
MessageRepository
TaskRepository
EventRepository
ArtifactRepository
CheckpointRepository
HandoffRepository
GateRepository
ModelProfileRepository
ToolCallRepository
RequestRepository
```

Repository 返回领域对象或 DTO，不把 SQLAlchemy ORM Model 传入 API 和 Worker。

## 12. 事务边界

一个业务命令使用一个 UnitOfWork。例如完成阶段：

1. 验证 Stage Run 状态。
2. 保存 Artifact Version。
3. 保存 Gate Run。
4. 创建 Checkpoint。
5. 创建 HandoffPacket。
6. 更新 Stage/Workflow/Room 状态。
7. 追加 EventLog 与 Outbox。
8. 一次 commit。

任一步失败则整体 rollback。

## 13. 索引与约束

- `(project_id, state)` 工作流查询索引。
- `(room_id, sequence)` 唯一消息顺序。
- `(room_id, slot)` 唯一模型槽位。
- `(room_id, profile_id)` 唯一，Application Service 额外校验同一 Room credential_ref 不重复。
- 一个项目最多一个 running workflow。
- 一个 Room 最多一个 active task。
- `(worker_id, sequence)` IPC 唯一序号。
- Artifact Version 不允许覆盖。
- Handoff content_hash 唯一验证。
- 所有外键启用 ON DELETE 明确策略，不依赖默认级联。

## 14. 迁移与备份

桌面升级流程：

1. 停止 Worker。
2. 使用 SQLite Backup API 创建带版本备份。
3. 执行 Alembic migration。
4. 运行 foreign_key_check 和 integrity_check。
5. 成功后启动服务。
6. 失败时恢复备份并拒绝使用不一致数据库。

## 15. 数据删除

单条消息不物理删除。删除整个项目时用户可以选择：

- 仅从应用移除，保留工作区。
- 删除运行数据与快照，保留项目文件。
- 删除 Managed Workspace、运行数据和快照。

Direct Workspace 的用户项目文件默认永不随项目记录一起删除。

## 16. 验收标准

- Worker 无法直接访问数据库。
- 重要状态与 EventLog 原子提交。
- 消息和正式产物历史不可覆盖。
- 快照大文件不进入 SQLite。
- API Key 不出现在数据库和备份中。
- 数据库迁移失败可以恢复。
- 单项目活动工作流和单聊天室活动任务由数据库约束保证。
