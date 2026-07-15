# 星协 V1 阶段 7 正式前端验收记录 v1

> 日期：2026-07-15
> 分支：`codex/frontend-v1`
> 后端基线：`origin/master` at `bd249607886f68bef07be20e0fff8ae6ece61d40`
> 设计母版：`FRONTEND-DRAFT-MASTER-v1.md` 与 `reference-images/v1/`
> 执行文档：`FRONTEND-IMPLEMENTATION-EXECUTION-v1.md`
> 状态：阶段 7B Task 6-11 门禁通过，等待分支推送与 PR 审查

## 1. 交付范围

阶段 7B 已完成 S00-S09：

- S00 启动、健康、就绪与恢复记录；
- S01 项目列表、创建和打开；
- S02 项目预检与工作流开始；
- S03 项目主页和工作流控制；
- S04 Planner、Designer、Builder、Reviewer、Deployer 五阶段工作区；
- S05 Artifact、Quality Gate、Handoff 和 ChangeRequest 只读治理；
- S06 MANUAL/AUTONOMOUS 审批和 CapabilityRequest；
- S07 FileConflict、Checkpoint 和保护性恢复；
- S08 ModelProfile 和 Room 模型槽位；
- S09 system/info、事件重放、ToolCall 审计和恢复诊断。

所有业务动作均映射到冻结 OpenAPI operation 或 DesktopPort；不存在的 Settings、ModelProfileTest、SecretStore、DiagnosticsExport 等能力保持禁用并显示原因。

## 2. 契约基线与 Hash

| 文件 | SHA-256 |
| --- | --- |
| `frontend/contracts/openapi.json` | `F36C8E44C74059D039F67ED0FE321161039600FF80FD9F8A64EEA83556AA7D95` |
| `frontend/contracts/events.schema.json` | `B9247299BB0BC6CEE21D922E54B1B077DD725A46C7B517EC6E15D04642E0E959` |
| `frontend/contracts/capabilities.json` | `06763ACAC061D95E9BBFAC309A403D5092C4C8E676982353EBE9F30FCF2BA03A` |

覆盖验证：68 个 REST operation、41 个事件类型、5 个 StageContract、23 个 Tool Catalog 项。

实现期间发现的执行文档与实际契约差异分别保留在：

- `FRONTEND-CONTRACT-CHANGE-REQUEST-v1.md`；
- `FRONTEND-CONTRACT-CHANGE-REQUEST-v2.md`；
- `FRONTEND-CONTRACT-CHANGE-REQUEST-v3.md`；
- `FRONTEND-CONTRACT-CHANGE-REQUEST-v4.md`。

旧版本未覆盖或删除。

## 3. 前端门禁结果

完整命令：

```powershell
npm run lint
npm run typecheck
npm test
npm run test:visual
npm run test:e2e
npm run contracts:verify
npm run build
```

结果：

- ESLint：0 error，0 warning；
- TypeScript：0 error；
- Vitest：31 个测试文件，58 个测试全部通过；
- 视觉回归：34 个测试全部通过，其中 14 个主视图 × 浅/深主题共 28 张页面快照；
- Playwright E2E：58 个测试全部通过；
- 生产构建：61 个模块成功转换并输出 Renderer。

生产构建：

| 文件 | SHA-256 |
| --- | --- |
| `dist/renderer/assets/index-JKbWlOR3.js` | `086E2E7C5E3E44C9A690C1BBB1BFEAFC2457BF4B5CE6A6504814040DFF88A284` |
| `dist/renderer/assets/index-BvL3tYW3.css` | `879DB12E349682A3397D8BBABEFBE8997E7F57B7EDA3C584252B45109F600351` |

## 4. 视觉与可访问性证据

- 原 `docs/frontend/reference-images/v1/` 28 张单页母版保持不变；测试强制检查数量、名称和 1440×900 尺寸。
- 当前实现的 28 张独立渲染基线保存在 `frontend/tests/e2e/visual/pages.spec.ts-snapshots/`。
- 浅色和深色主题均覆盖 S00-S09。
- 1280×720、1440×900、1920×1080 全部通过。
- 100%、125%、150%、175%、200% DPI 模拟全部通过，共 15 组。
- 核心导航和诊断查询可仅用键盘完成。
- 焦点环、可访问名称、禁用原因关联和 reduced-motion 通过。
- 主要、次要、强调、Warning 和 Danger 语义文字在双主题达到至少 4.5:1 对比度。

视觉微调仅加深低对比的浅色次要文字、Warning/Danger 文字和深色 Danger 文字，不改变锁定布局、主色、圆角或柔和按压行为。

## 5. 安全与耦合证据

- Renderer 不获得 Token、Secret 明文、Node 文件系统、Shell、原始 IPC 或 NDJSON 认证信息。
- 生产 `src/` 与 `electron/` 不包含测试 Fake、Node builtin、`ipcRenderer`、`process.env` 或认证头。
- 控件矩阵通过静态扫描：每个静态/动态 Button 和 NavLink 均映射到后端 operation、DesktopPort、纯视图动作或明确不可用状态。
- Event payload 和 ToolCall 任意 result 不在诊断页渲染。
- 本地持久化只保留草稿和视图偏好；迁移会丢弃 Workflow、Approval、Token 等领域状态。
- Renderer 订阅卸载时释放监听器，重放从持久游标开始；重复和非连续全局 `event_id` 处理通过。

## 6. 后端零回归门禁

阶段 7B 未修改 `backend/`。在同一工作树执行：

```powershell
uv run ruff format --check .
uv run ruff check .
uv run mypy src
uv run pytest
```

结果：

- Ruff format：233 个文件已格式化；
- Ruff check：全部通过；
- Mypy：136 个源文件无问题；
- Pytest：`718 passed, 12 skipped`。

## 7. 明确未完成且不得在阶段 7 宣称通过的事项

以下属于阶段 8/9，不是本阶段缺陷掩盖项：

- Electron Main/Preload 的真实 IPC 适配和 Sidecar 生命周期；
- 动态本地端口、临时 Session Token、轮换与退出失效；
- WebSocket Ticket 的真实签发、过期和重连代理；
- SecretStore Bridge 和真实模型凭证写入；
- Worker/Tool 进程诊断、日志摘要和诊断包导出；
- Windows 安装器、固定 Python onedir、升级备份和恢复模式；
- 跨显示器、最小化/恢复、真实系统 DPI 切换；
- 安装后使用阶段 5 Fake Model 跑真实项目的全产品 E2E。

阶段 7 的 Playwright DesktopPort Fixture 只存在于 `frontend/tests/e2e/`，不会进入生产构建，也不被表述为已完成的桌面集成。

## 8. 版本历史

| 版本 | 日期 | 变更 |
| --- | --- | --- |
| v1 | 2026-07-15 | 记录阶段 7B Task 6-11 的页面范围、契约 Hash、前后端门禁、视觉/可访问性、安全证据和阶段 8/9 未完成边界。 |
