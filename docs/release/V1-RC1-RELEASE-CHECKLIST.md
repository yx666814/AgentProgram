# 星协 V1.0.0-rc.1 发布候选检查表

> 建立日期：2026-07-16
> 最近更新：2026-07-29
> 发布分支：`codex/rc1-manual-acceptance-guide`
> 合并基线：`f060239be993bd2a880619032cdf317048cd9ab1`
> 编排实现提交：`3f58d6a19d35fe849764202fec095fd906137372`
> 双模式 UI 提交：`2e079b3024c967900b015ebe13a510ec2cb13f50`
> 状态：自动编排发布阻塞与当前 PR CI 已解除；真实模型、物理桌面与独立审查仍待完成，因此不是正式 V1 发布。

## 1. 版本锁定

| 产物 | 版本 |
| --- | --- |
| Electron/npm 应用 | `1.0.0-rc.1` |
| Python 后端包（PEP 440） | `1.0.0rc1` |
| RC 安装器 | `XingXie-1.0.0-rc.1-Setup.exe` |
| 正式目标版本 | `1.0.0` |
| 正式目标 Tag | `v1.0.0` |

`1.0.0rc1` 与 `1.0.0-rc.1` 表示同一个发布候选版本；差异只来自 Python PEP 440 与 npm SemVer 的格式要求。

## 2. 自动编排闭环

- [x] 新增高层 `POST /api/v1/workflows/{workflow_id}/orchestration/stream` NDJSON 命令。
- [x] 正式运行由后端协调 StageRun、Task、Primary/Reviewer A/Reviewer B/P2R AgentRun、ToolCall、ArtifactVersion、Gate、Approval/Policy、Checkpoint 与 Handoff。
- [x] 模型只提交 `StageExecutionPlan v1`；模型不能直接读取文件、执行 Shell 或选择正式产物路径。
- [x] 文件覆盖要求当前 SHA-256，命令只允许引用 Manifest 中的 `command_index`。
- [x] 失败、取消和应用重启保留真实 Task、AgentRun、ToolCall 与恢复记录。
- [x] `warning_blocked` 必须由用户点击“返回讨论”恢复，不被后台静默越过。
- [x] Stage 页面使用真实 ModelProfile 和当前 Room 三槽位分配发起正式编排。
- [x] 安装版用户可见五阶段编排、Manual/Autonomous、Warning 返工和审批闭环通过。

最终安装版产品报告：

```text
12 formal AgentRuns
12 quality gate evaluations
10 locked ArtifactVersions
10 Handoffs
8 manual approvals
2 autonomous Handoffs
userVisibleOrchestration = true
```

## 3. 自动化门禁

- [x] 后端版本源和 `uv.lock` 已更新。
- [x] 前端版本源和 `package-lock.json` 已更新。
- [x] 冻结契约已重新导出：69 REST / 41 events / 5 StageContracts / 23 tools。
- [x] 契约元数据指向后端提交 `3f58d6a` 和 backend tree `19df7dea8f4b76815712544f10b766dc09df30b8`。
- [x] Ruff format：246 个文件通过。
- [x] Ruff check：通过。
- [x] Mypy strict：144 个源文件通过。
- [x] Pytest：733 passed / 12 skipped。
- [x] Vitest：39 个文件 / 75 个测试通过。
- [x] Playwright：58 个测试通过。
- [x] RC1 NSIS 安装器重新构建通过。
- [x] 当前安装器的用户可见编排 product E2E：1 passed。
- [x] 既有阶段 9 基线的普通 TEMP、Windows 8.3 短路径、卸载重装与恢复门禁保持通过。
- [x] 当前分支 PR 的 backend/frontend/windows-product CI 全绿；Run `30400155883` 的 Job Summary 保留安装器 Hash 和产品报告关键计数，测试证据 artifact 因历史存储配额未实际生成。

历史 CI 基线：GitHub Actions Run [`29492919058`](https://github.com/yx666814/AgentProgram/actions/runs/29492919058) 曾验证合并前阶段 9 安装版链路。该 Run 不包含本轮自动编排实现，不能作为当前候选安装器的分发身份。

当前 PR 证据：GitHub Actions Run [`30400155883`](https://github.com/yx666814/AgentProgram/actions/runs/30400155883) 在提交 `600c8a7` 上完成，`backend`、`frontend`、`windows-product` 均为 `success`；安装器构建和安装版 product E2E（`1 passed`）通过。仓库历史 artifact 配额已满，本 Run 没有可下载 artifact，不能把 Job Summary 中的 CI 安装器身份当成公开下载项。

## 4. 当前本地 RC1 产物证据

以下值只对应 2026-07-29 在 `3f58d6a` 后端实现和最新冻结契约上构建、并通过最终 product E2E 的本地文件：

| 产物 | 字节 | SHA-256 | 签名 |
| --- | ---: | --- | --- |
| `frontend/release/XingXie-1.0.0-rc.1-Setup.exe` | 122294271 | `4D830304D516EA87F01332AA7C45B4D7E849652BD09DA0D5A1C81ACD58684192` | `NotSigned` |
| `frontend/release/win-unpacked/星协.exe` | 225485824 | `A896AADE45A44352CE9EA59E8B4E27B6A1B4CD23AE7BE51FCF625644D57A70B7` | `NotSigned` |
| `frontend/release/win-unpacked/resources/backend/agent-platform-desktop-sidecar.exe` | 13047226 | `4523EECEE70A5A3959C1831218B131F759BF94B49C47875CC172554027C163B2` | `NotSigned` |
| `frontend/release/win-unpacked/resources/app.asar` | 13975463 | `C3904D5C7ADDD87E9E203D532A9D6EB6D7181FA3FF2452A231F52F130E824ED2` | 不适用 |

本地安装器校验文件：`docs/release/V1-RC1-LOCAL-SHA256SUMS.txt`。本地安装器尚未获得公开上传授权，不是 GitHub Release 下载项。

冻结契约：

| 文件 | SHA-256 |
| --- | --- |
| `frontend/contracts/openapi.json` | `47E838C0B27269D2AD83D49CFF2C752BD82A7C4817AF5B8A8C5CDA1CE0CFC47E` |
| `frontend/contracts/events.schema.json` | `57C07FC9ABF8FFE793EC4228C6A4ADF547E08F93F680CA47EA2B99EC3C755F62` |
| `frontend/contracts/capabilities.json` | `1EF9F820D4D4F89D7D54B2AE59B12368B4834A8BA786E1254DC4461E78367520` |
| `frontend/contracts/SHA256SUMS.json` | `938E6EC4C40FB544618A86025338CCD18CB38657478B0E922DD978FFCD64BA06` |

安装器构建不是字节级可复现的。对外分发时必须重新计算实际上传文件的大小、SHA-256 和签名状态，不能复用其他本地构建或历史 CI Run 的值。

## 5. 用户必须完成的发布验收

### 未签名分发决策

- [x] 用户确认 RC1 暂不购买或配置 Authenticode 签名。
- [x] 接受 Windows SmartScreen 可能显示“未知发布者”。
- [x] 安装器、主程序和 Sidecar 的 `NotSigned` 状态已如实记录。
- [x] Release Notes 明确说明未签名风险和校验方式。
- [ ] 对外上传前重新计算实际文件 SHA-256，并生成同批校验文件。

可信 Authenticode 签名已延期，不是本次 RC1 的硬门禁；未来若启用，凭据只能保存在受保护的签名服务或 GitHub Actions Secrets 中。

### 真实模型

- [ ] OpenAI Compatible：连接、流式、取消、错误恢复和五阶段人工验收。
- [ ] Anthropic：连接、流式、取消、错误恢复和五阶段人工验收。
- [ ] 确认 API Key 不进入数据库、日志、事件、诊断包或截图。

### 物理桌面

- [ ] 100%、125%、150%、200% DPI。
- [ ] 1080p、2K、4K（硬件可用时）。
- [ ] 多显示器与不同缩放比例切换。
- [ ] 浅色/深色、键盘焦点、系统文件对话框。
- [ ] 中文空格路径安装、卸载、重装和无残留进程。

### 审查与分发

- [x] 当前 PR 的三个 CI job 全绿（Run `30400155883`）。
- [ ] PR 由独立审查者确认。
- [x] 当前零已知 P0/P1。
- [ ] Release Notes、已知问题和回滚步骤与实际上传文件一致。

详细操作见 `docs/release/V1-RC1-MANUAL-ACCEPTANCE.md`。

## 6. 正式发布边界

当前自动编排实现和 Fake Model 安装版闭环已经完成，但真实模型、物理桌面和独立审查仍是 RC1 人工验收项。创建 `v1.0.0` Tag、GitHub Release 或上传公开安装器前，必须取得用户明确授权；在此之前不得宣称正式 V1 已发布。
