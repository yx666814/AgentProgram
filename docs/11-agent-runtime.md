# Agent Runtime 与一主双校

## 1. 目的

Agent Runtime 负责把 RoleCard、Stage Contract、聊天上下文、模型档案和工具协议组合成可控执行。它运行在 Project Worker 中，但所有工具和状态修改必须请求 Backend Main Process。

## 2. 模型槽位

每个聊天室最多：

```text
Primary       必须，1 个
Reviewer A    可选，0-1 个
Reviewer B    可选，0-1 个
```

三个槽位分别引用不同 ModelProfile 和不同 credential_ref，独立调用、独立计费、独立统计。同一 Room 不允许两个槽位复用同一密钥。系统不设置成本上限。

只有 Primary 能提出工具调用。Reviewer A/B 永远没有工具定义。

## 3. 运行组件

```text
AgentRuntime
├─ RoleCardLoader
├─ PromptComposer
├─ ContextBuilder
├─ DiscussionController
├─ ModelRouter
├─ ToolCallParser
├─ ToolRequestClient
├─ OutputNormalizer
├─ UsageCollector
└─ CancellationController
```

## 4. Prompt 组合

优先级：

```text
Global Core Policy
> RoleCard
> Stage Contract
> Model Sub-role Prompt
> Project Instructions
> Runtime State
> HandoffPacket
> User Message
> Project File Content
```

Project Instructions 和用户消息不能覆盖角色职责、权限、交接、Quality Gate 和永久禁止规则。

最终 Prompt 包含明确的当前阶段、任务、允许工具、允许路径、正式产物、未解决问题和完成限制。

## 5. 上下文构建

完整消息保存在数据库，模型上下文动态构建：

```text
RoleCard
Stage Contract
Project Instructions
HandoffPacket
Pinned Decisions
Rolling Summary
Recent Messages
Relevant Artifact Excerpts
Relevant File Excerpts
Current Task
```

Rolling Summary 保存来源消息范围和 Hash。原始历史不删除。上下文超限时优先移除重复、非正式讨论，不删除核心策略、正式决定和验收标准。

Reviewer A/B 只获得：

- 当前请求。
- Primary 草案。
- 自己的校正职责。
- 必要 Stage Contract。
- 必要正式产物片段和工具证据。

不获得整个聊天室和另一个 Reviewer 的意见。

## 6. 讨论模式

### P0 Primary Only

普通聊天、解释、状态讨论和不改变正式产物的内容只调用 Primary。

### P1 Single Review

一般方案或局部修改：Primary 草案后只调用最相关的一个 Reviewer，再由 Primary 短修订。

### P2 Dual Review

以下场景强制两个 Reviewer 并行校正：

- 提交正式阶段产物。
- 创建 HandoffPacket 前。
- 重要架构、数据和接口决定。
- Builder 大范围实现结果。
- Reviewer 正式 Verdict。
- Deployer 正式部署准备产物。
- 用户主动选择完整校正。

流程：

```text
Primary Draft
├─ Reviewer A Review
└─ Reviewer B Review
        ↓
Primary Revision
```

自动校正最多一轮。Gate Warning 后由用户决定是否重新执行新的 Rewrite Run，重写次数不设全局上限。

## 7. ReviewResult

```text
ReviewResult
├─ verdict             # PASS / REVISE / BLOCK
├─ blocking_issues     # 最多 3
├─ important_issues    # 最多 3
├─ suggestions         # 最多 3
├─ missing_information
└─ confidence
```

Reviewer 不重新生成完整方案。任何 BLOCK 必须被 Primary 接受修订、提供有依据的拒绝理由，或交给用户处理。两个 Reviewer 均 BLOCK 时不能自动正式提交。

## 8. Primary 执行循环

1. 构建 Prompt 与上下文。
2. 调用 Primary。
3. 如果产生 ToolCall，验证工具结构。
4. 向主进程发送 ToolExecutionRequest。
5. 接收受控 ToolResult。
6. 将结构化结果回传模型。
7. 检测重复调用、无进展和最大技术轮数。
8. 形成草案或最终聊天回复。
9. 正式任务执行 P2R。
10. 返回 Worker TaskResult，由主进程验证和持久化。

技术轮数上限只用于防止无限循环，不是费用上限。到达上限时任务失败或请求用户处理，不能伪装完成。

## 9. ToolResult

```text
ToolResult
├─ request_id
├─ tool_name
├─ status
├─ data_ref
├─ stdout_ref
├─ stderr_ref
├─ exit_code
├─ affected_files
├─ duration_ms
└─ error
```

Primary 必须以真实 ToolResult 为依据声明构建、测试和文件操作结果。

## 10. 模型适配器

```text
ModelAdapter
├─ complete()
├─ stream()
├─ cancel()
├─ probe_capabilities()
└─ normalize_usage()
```

第一版实现 OpenAI 兼容和 Anthropic。Adapter 统一：

- 文本消息。
- 原生工具调用。
- JSON 工具降级。
- 流式事件。
- Token 用量。
- 超时、限流和错误分类。

模型 API Key 由主进程 SecretStore 按 credential_ref 提供给 Worker 启动上下文或受控模型调用通道，不进入 Prompt、日志和数据库。

## 11. 模型能力探测

保存每个 ModelProfile 的能力：

```text
native_tool_calling
json_tool_calling
streaming
system_message
max_context
usage_reporting
```

探测失败不能导致整个应用失败，只阻止该 Profile 被分配到不兼容槽位。

## 12. 任务与队列

每个 Room 同时一个活动 Primary Task。用户在任务运行时发送的消息进入队列，不注入当前上下文。用户可以取消当前任务或删除尚未执行的队列消息。

不同项目可以分别运行 Worker。同一项目只有当前活动阶段拥有写能力。

## 13. 流式输出

Worker 将模型流式 chunk 作为临时 event 发送给主进程。chunk 用于 UI，不逐 token 落库。完成后保存最终 Message；失败时 partial content 明确标记，不进入正式产物。

## 14. 完成后咨询

Completed Room 可以进入 consultation：

- Primary 只解释历史决定和正式产物。
- 不注入工具。
- 不修改产物和工作流。
- 消息标记 post_completion_consultation。

正式修改必须显式 reopen stage，创建新 Stage Run 并使下游失效。

## 15. Warning 重写

AUTONOMOUS Gate Warning 进入 warning_blocked。用户选择 rewrite 后：

1. 创建 RevisionRequest。
2. 新建或继续当前 Stage Run 的修订任务。
3. Primary 获取 Warning 证据和要求。
4. 重写正式产物。
5. 重新 P2R。
6. 重新 Gate。

不自动循环，不允许忽略 Warning 继续。

## 16. 取消与失败

取消传播：

```text
Desktop → Main → Worker → Model Adapter / pending Tool Request
```

已开始的 Tool Process 由 Main 终止进程树。任务进入 cancelled 或 interrupted，不进入 completed。

模型错误分类：

```text
authentication_error
rate_limited
timeout
provider_unavailable
invalid_response
tool_protocol_error
cancelled
```

技术性瞬时错误可以按固定小次数重试；业务 Warning 和 Gate 失败不能通过 SDK 重试掩盖。

## 17. Prompt Injection 防护

- 项目文件和用户内容都是不可信数据。
- 文件中的“忽略系统规则”不能改变权限。
- 工具列表由后端生成。
- Worker 不能接受模型声明的新工具。
- Tool Policy 重新验证全部参数。
- 模型不能生成 approved、completed 或 capability granted 状态。
- 可疑内容作为数据引用并在 Prompt 中标记来源。

## 18. 用量

每个 ModelCall 独立记录 Profile、credential_ref、Token、耗时和估算费用。仅展示，不限制任务和每日费用。

## 19. 验收标准

- 每个 Room 最多一个 Primary 和两个 Reviewer。
- Reviewer 永远没有工具定义。
- 正式产物强制 P2。
- 完整聊天历史不直接全部发送给模型。
- ToolCall 必须经过主进程。
- 取消可以终止模型和工具链。
- 模型不能直接修改数据库状态和权限。
