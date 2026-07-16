# 星协 V1 前端契约 Change Request v7

> 日期：2026-07-16
> 状态：阶段 9 DesktopPort v3 传输语义澄清与受限安装版验收入口
> 实现基线：`6be04beceb6f78addfb2b81563181a0b62914d08`
> 前一版本：`FRONTEND-CONTRACT-CHANGE-REQUEST-v6.md`（保留，不覆盖）
> 适用范围：Electron Main、真实 BackendClient、安装后 Windows product E2E

## 1. 变更原因

阶段 8 的 `BackendClient` 把所有非空响应都按 JSON document 解析，但冻结后端已有两个不同媒体类型：

- `stream_agent_run_api_v1_agent_runs__run_id__stream_post` 返回 `application/x-ndjson`；
- `get_agent_run_output_api_v1_agent_runs__run_id__output_get` 返回 `text/plain`；
- 其余冻结 REST operation 返回 JSON 或空响应。

浏览器 Fixture 不经过真实 Main 代理，因此不能证明以上响应可通过正式 `DesktopPort`。阶段 9 安装版首次执行真实 AgentRun 时暴露了该传输缺口。本变更只按后端声明的 `Content-Type` 保留真实响应语义，不增加业务 operation、不修改响应内容，也不把失败改写为成功。

阶段 9 同时需要在临时中文空格目录安装、隔离应用数据并预授权测试创建的真实 Workspace。Renderer 仍不能读取命令行、枚举文件系统或指定任意 IPC；因此增加只由显式 product E2E 标志开启的 Main 进程启动参数，不扩展 `DesktopPort` 方法。

## 2. DesktopPort 传输语义

`backend.query` 与 `backend.command` 的返回签名不变：

```ts
interface BackendReply<T = unknown> {
  requestId: string;
  statusCode: number;
  payload: T;
}
```

Main 根据响应媒体类型生成 `payload`：

| 后端媒体类型 | DesktopPort payload | 约束 |
| --- | --- | --- |
| `application/json` 或 JSON 兼容类型 | 已解析 JSON 值 | 保持阶段 8 行为 |
| `application/x-ndjson` | 按非空行解析的 frame 数组 | 任一行不是 JSON 时请求失败，不丢帧、不伪造完成帧 |
| `text/plain` | 原始 UTF-8 字符串 | 不再次执行 JSON 解析 |
| 空响应 | `null` | 保持阶段 8 行为 |

所有类型继续受 16 MiB 响应上限、30 秒 Main 请求超时、冻结 operationId 白名单和本地 Session Token 代理约束。非预期媒体内容、解析错误和 Sidecar 失败仍返回真实失败，不降级为 Fixture 数据。

本次没有新增或删除 `DesktopPort` 方法，因此接口仍为 v3，不进行无意义的 schema version 升级。

## 3. 受限 product E2E 启动参数

Main 新增以下进程参数：

```text
--stage9-product-e2e
--stage9-e2e-data-root=<absolute path>
--stage9-e2e-workspace=<absolute path>
```

约束：

- 数据根和 Workspace 参数只有在同时存在 `--stage9-product-e2e` 时才接受；
- 路径必须非空、为绝对路径，并由 Main 规范化；
- `data-root` 只覆盖本次进程的 Electron `userData`，用于隔离 SQLite、日志和 DPAPI SecretStore；
- `workspace` 可重复，仅调用既有 `LocalPathPolicy.allowSelectedRoot`；
- Renderer 不取得参数、路径枚举、Node API 或文件系统句柄；
- 未提供标志的正常启动仍使用 `%APPDATA%\星协` 和原生目录选择对话框；
- 参数不创建后端业务成功状态，只建立与用户通过原生对话框选择目录相同的 Main 白名单边界。

## 4. 阶段 9 后端运行时对齐

阶段 5 的冻结 `ModelProvider` 已包含 `fake`，但正式 lifespan 之前只注册 OpenAI Compatible 与 Anthropic Adapter。阶段 9 注册 `DeterministicFakeModelAdapter`：

- `provider` 严格为冻结枚举 `fake`；
- 输出完全本地、确定性生成，不发起网络请求；
- 不新增 ModelProfile、AgentRun 或模型测试 operation；
- 仍通过真实 SecretStore 引用、Room ModelAssignment、AgentRun、NDJSON stream、持久输出和用量记录链路；
- 真实 OpenAI Compatible 与 Anthropic Adapter 保持不变。

Direct Workspace 默认 Manifest 同时识别已存在的 `src`、`app`、`lib` 目录为 `source_paths`。这使 Builder 通过现有 `filesystem.write_source` 权限写入真实源码目录，不扩大到项目外路径，也不修改冻结 API schema。

## 5. 契约冻结结果

实现提交后重新执行：

```powershell
npm run contracts:export
npm run generate:api
npm run contracts:verify
```

结果：68 个 REST operation、41 个事件类型、5 个 StageContract、23 个 Tool Catalog 项全部通过。仅后端提交/tree 元数据和由其派生的文件 Hash 更新；OpenAPI 路径、方法、Schema、事件集合和工具集合没有功能性变化。

| 文件 | SHA-256 |
| --- | --- |
| `frontend/contracts/openapi.json` | `7B9C17BBBB8CAA4B1A2B7CCEEF85282EA097D84A88215854912F35C6E98D363E` |
| `frontend/contracts/events.schema.json` | `081B63399C8200FA197A0D41AC308C2602812FD216E1341CC6F60799689AF886` |
| `frontend/contracts/capabilities.json` | `5F6867BCA050957B0988341A9670160016EBE6E36A5739A4933F797279EEB152` |
| `frontend/contracts/SHA256SUMS.json` | `1A9A75942F49BB10AB7B890BCD4D45295AA4EEB2D844096305DB7D814FB9814A` |

冻结元数据：

- backend commit：`6be04beceb6f78addfb2b81563181a0b62914d08`；
- backend tree：`3557af3e91470bfb78f375edb4db64189248f841`。

## 6. 验证与回滚

自动验证包括：

- BackendClient NDJSON frame 数组和 `text/plain` 字符串定向测试；
- Main/Preload 安全边界、operationId 白名单和本地路径策略回归；
- Fake Adapter 无网络确定性输出测试；
- Direct Workspace `source_paths` 契约测试；
- 安装后的五阶段 product E2E，通过真实 Main、Preload、Sidecar、SQLite、SecretStore、REST 和 WebSocket；
- product E2E 退出时卸载程序并只删除操作系统临时目录内的测试根。

回滚时可以移除确定性 Fake Adapter 注册、Content-Type 分支和三个阶段 9 参数，但必须同时移除 product E2E 与 CI product job。不能只恢复全 JSON 解析而保留 AgentRun 安装版验收，否则会重新引入真实传输失败。

## 7. 不变约束

- 后端继续是业务状态唯一权威；
- Renderer 继续不持有 Session Token、WebSocket Ticket、Secret Bridge 信息、API Key 明文或 Node 文件系统权限；
- 没有新增 Settings、ModelProfileTest、数据库版本或 Worker 列表等不存在的 operation；
- Fake Model 只用于稳定 CI 和产品验收，不冒充外部真实模型；
- v1-v6 文档、阶段 7/8 验收记录和锁定参考图全部保留。

## 8. 版本历史

| 版本 | 日期 | 变更 |
| --- | --- | --- |
| v1 | 2026-07-15 | 冻结阶段 5 静态契约、实际 operationId 与全局事件游标。 |
| v2 | 2026-07-15 | 补充消息、模型流、StageContract 和 Rolling Summary 边界。 |
| v3 | 2026-07-15 | 补充 FileConflict、三方 Hash 和 restore-plan 边界。 |
| v4 | 2026-07-15 | 补充设置、诊断、全局事件投递和 SecretStore 缺口。 |
| v5 | 2026-07-15 | 批准 DesktopPort v2 只写 SecretStore 和 Windows DPAPI Bridge。 |
| v6 | 2026-07-15 | 批准 DesktopPort v3 受控诊断导出和安全投影。 |
| v7 | 2026-07-16 | 保留 v1-v6；澄清 NDJSON/text 传输语义，记录受限 product E2E 参数、正式 Fake Adapter 和 Direct source path 对齐。 |
