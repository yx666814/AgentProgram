# 星协 V1 前端契约对齐 Change Request v1

> 状态：已接受
>
> 日期：2026-07-15
>
> 后端基线：`origin/master` at `057e2612489c99a3b93cc103d911e2530362dc38`
>
> 适用范围：`FRONTEND-IMPLEMENTATION-EXECUTION-v1.md` Task 1 Steps 2–6

## 1. 变更原因

阶段 5 已冻结并实现 68 个 REST 操作、WebSocket replay/outbox 协议、统一
`EventEnvelope`、五阶段 `StageContract`、Tool Catalog、错误代码和 Desktop Control v1。
后端完整门禁在本机复现为 `718 passed, 12 skipped`，Ruff、格式检查和 Mypy 通过。

实际交付没有提交以下静态构建文件：

- `openapi.json`
- `events.schema.json`
- `capabilities.json`

后端也没有定义 `BackendHealthQuery`、`ProjectListQuery` 等独立 Capability ID；权威标识是
FastAPI OpenAPI `operationId`、HTTP method/path、WebSocket contract、实际事件类型、
StageContract capability 和 Tool Catalog 名称。前端不得为满足旧清单自行创造别名。

## 2. 受控执行方式

Task 1 改为由前端拥有的只读导出器从冻结后端代码生成三份快照：

1. `openapi.json` 由 `create_app(Settings).openapi()` 生成。
2. `events.schema.json` 由 `EventEnvelope.model_json_schema()` 和后端 application service
   中实际发布的事件类型生成。
3. `capabilities.json` 由 OpenAPI operation、WebSocket discovery、`load_stage_contracts()`、
   `ToolCatalog` 和后端公开错误代码生成。

导出器只读取 `backend/`，不得写入或修改后端源码、迁移、测试或运行数据。生成文件必须记录：

- 后端 Git commit；
- Schema version；
- 生成来源；
- 稳定排序后的内容；
- SHA-256。

## 3. 前端门禁调整

契约覆盖测试不再寻找虚构 Query/Command ID，而是验证：

- OpenAPI 中的全部 REST operation 都存在于 capability snapshot；
- UI 所需 method/path 直接对应后端 operationId；
- WebSocket ticket、replay 和 `/api/v1/events/ws` 均被记录；
- Workflow 12 状态、StageRun 16 状态、五阶段 StageContract 全部来自后端 Schema；
- Tool Catalog、Stage capability、错误代码和实际事件类型没有手写第二份运行时定义；
- 重新导出后存在 diff 时，前端构建失败并要求显式审查。

## 4. 不变约束

- 不修改后端代码。
- 不在 Renderer 暴露 Token、Secret、文件系统、Shell 或原始 IPC。
- 不把 HTTP accepted 当作业务 completed。
- 不创建后端不存在的页面动作、成功状态或可点击控件。
- 后续后端契约变化必须重新生成快照、记录 Hash 并通过契约测试。

## 5. 接受依据

用户已于 2026-07-15 确认阶段 0–5 完成并要求继续下一阶段，同时要求检查后端但不修改后端代码。
本 Change Request 只调整冻结契约的交付形式，不改变阶段 6 已锁定的页面、视觉或交互设计。
