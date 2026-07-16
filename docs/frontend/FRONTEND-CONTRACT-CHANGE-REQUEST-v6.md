# 星协 V1 前端契约 Change Request v6

> 日期：2026-07-15
> 状态：阶段 8 DesktopPort v3 受控变更记录
> 仓库基线：`origin/master` at `a6a025e`
> 前一版本：`FRONTEND-CONTRACT-CHANGE-REQUEST-v5.md`（保留，不覆盖）
> 适用范围：Electron Main/Preload、S09 诊断页与脱敏诊断包导出

## 1. 变更原因

阶段 5 OpenAPI 没有 `DiagnosticsExport` operation，阶段 7 因而按真实契约保持“导出诊断包”禁用。`PROJECT-PLAN.md` 阶段 8 和 `STAGE-8-DESKTOP-HANDOFF-v1.md` 要求由 Electron Main 使用原生保存对话框完成诊断导出，同时禁止 Renderer 获得任意文件系统权限。

本版本在 v5 的只写 SecretStore 基础上，新增一个受限的桌面诊断导出方法。该方法不是后端业务接口别名，也不产生虚假的后端成功状态；Main 只汇总真实后端 Query、Sidecar 公共状态、冻结契约 Hash 和脱敏日志投影。

## 2. DesktopPort v3 新增能力

```ts
interface DiagnosticsExportInput {
  workflowId?: string;
  afterEventId?: number;
}

interface DesktopPort {
  diagnostics: {
    export(
      input: DiagnosticsExportInput,
    ): Promise<{ cancelled: boolean; path?: string }>;
  };
}
```

约束：

- `workflowId` 可省略；提供时必须符合后端冻结的 `workflow_<lowercase alphanumeric>` 标识格式；
- `afterEventId` 默认 `0`，必须是非负安全整数；
- 返回 `cancelled: true` 只表示用户取消原生保存对话框，不表示导出失败或成功；
- 只有文件完整写入后才返回 `cancelled: false`；异常直接拒绝 Promise，由 S09 显示真实错误；
- Renderer 不能指定任意 IPC channel、读取文件、覆盖导出内容或绕过原生保存对话框。

## 3. 真实数据来源

Main 仅调用已存在的冻结 operation：

| 内容 | operationId | 使用方式 |
| --- | --- | --- |
| 后端版本与协议版本 | `system_info_api_v1_system_info_get` | 必选 |
| 后端与数据库就绪状态 | `readiness_api_v1_readiness_get` | 必选 |
| 恢复记录 | `list_recoveries_api_v1_recovery_get` | 必选，安全字段投影 |
| 工作流事件 | `replay_events_api_v1_events_replay_get` | 仅提供 `workflowId` 时查询 |
| ToolCall 审计 | `list_tool_calls_api_v1_workflows__workflow_id__tool_calls_get` | 仅提供 `workflowId` 时查询 |

同时包含：

- Electron、Node、Chrome 运行时版本；
- Sidecar 的公开状态；
- 打包进入应用的 `contracts/SHA256SUMS.json`；
- Sidecar 最近最多 100 条经过二次脱敏的诊断行。

不把 `health`、`readiness` 或 Sidecar 状态改称为不存在的数据库迁移版本、Worker 列表或完整进程诊断。单个后端 Query 非 200 时，只写入状态码、公共错误码和 `retryable`，不伪造成功 payload。

## 4. 安全投影与排除项

事件只保留信封元数据，以及 payload 中经过白名单允许的简单状态字段：

- `stage`、`target_stage`、`status`、`result`、`resolution`、`error_code`；
- 值只允许字符串、数字或布尔值；
- 其他任意 Event payload 字段全部丢弃。

ToolCall 只保留：

- ID、项目/工作流/阶段/任务引用；
- 工具名、能力、`arguments_hash`、状态、错误代码和时间；
- 不包含 arguments、result 或输出正文。

恢复记录只保留标识、关联范围、状态、中断计数、检测/解决时间和 resolution。导出包明确排除：

- Session Token、Secret Bridge Origin/Token；
- API Key、SecretStore 明文和 DPAPI 密文；
- 源代码与任意项目文件正文；
- 完整聊天、Prompt、上下文、摘要和模型输出正文；
- EventEnvelope 任意 payload；
- ToolCall arguments 和 result 正文。

日志额外脱敏 Bearer Token、常见 `sk-` 密钥，以及 JSON 中的 `api_key`、`authorization`、`credential`、`password`、`secret`、`token` 值。

## 5. 文件写入边界

- Main 使用 `dialog.showSaveDialog`，默认文件名为带 UTC 时间的 `xingxie-diagnostics-*.json`；
- 只提供 JSON 文件过滤器，并启用覆盖确认；
- Renderer 不取得 Node `fs`、目录枚举或任意文件句柄；
- Main 先以 `wx` 写入随机临时文件，再原子重命名到用户选择的位置；
- 成功或失败后都清理临时文件；
- 文件格式当前为 `schemaVersion: 1`，后续不兼容变化必须再次新增 Change Request。

## 6. S09 交互变化

- “导出诊断包”从阶段 7 的明确不可用状态切换为真实 DesktopPort 动作；
- 页面已有合法 `workflowId` 时，同时导出该工作流的事件和 ToolCall 安全投影；没有工作流输入时只导出基础诊断；
- 页面把当前 `after_event_id` 作为可选审计游标传入；
- 用户取消时显示“已取消诊断导出”，不显示成功；
- 文件写入成功时显示 Main 返回的实际路径；
- 后端、Sidecar、契约文件或写入失败时显示真实错误，不生成假文件或假成功提示。

## 7. 安全与测试门禁

- DesktopPort 静态契约测试确认 `diagnostics.export` 是唯一诊断文件能力；
- Preload 只通过固定 `desktop:diagnostics:export` IPC 调用 Main；
- Main 校验可信 WebContents、输入对象、工作流 ID 和事件游标；
- 单元测试扫描导出文件，确认事件任意 payload、ToolCall result、API Key 和 Token 不存在；
- S09 集成测试确认用户输入映射到真实 replay/ToolCall operation，并把相同范围交给导出；
- 生产 Renderer 继续禁止 `node:fs`、`ipcRenderer`、认证材料和测试 Fixture；
- 打包桌面冒烟必须验证原生保存、文件存在、JSON 可解析和敏感标记扫描为零。

## 8. 不变约束

- OpenAPI operation 数量和业务 Schema 不因本变更增加前端别名；
- 后端仍是业务状态唯一权威，Main 只做桌面生命周期、安全代理和诊断汇总；
- Renderer 不获得 Session Token、WebSocket Ticket、Secret Bridge 信息或任意文件系统权限；
- 不因诊断导出接入而声称后端拥有不存在的 Settings、ModelProfileTest、数据库版本或完整 Worker 诊断接口；
- v1-v5 文档、阶段 7 验收记录和锁定参考图全部保留。

## 9. 版本历史

| 版本 | 日期 | 变更 |
| --- | --- | --- |
| v1 | 2026-07-15 | 记录阶段 5 静态契约导出、实际 operationId、全局事件游标与冻结拼写。 |
| v2 | 2026-07-15 | 保留 v1；补充消息、模型流、StageContract 边界和 Rolling Summary 缺口。 |
| v3 | 2026-07-15 | 保留 v1-v2；补充 FileConflict、三方 Hash 和 restore-plan 边界。 |
| v4 | 2026-07-15 | 保留 v1-v3；补充设置/诊断实际能力、全局事件投递和 SecretStore 缺口。 |
| v5 | 2026-07-15 | 保留 v1-v4；批准 DesktopPort v2 只写 SecretStore、Windows DPAPI、后端本机解析桥和 S08 凭证事务。 |
| v6 | 2026-07-15 | 保留 v1-v5；批准 DesktopPort v3 受控诊断导出、真实 Query 汇总、安全投影和原生文件写入边界。 |
