# 星协 V1 阶段 9 全产品 E2E 与发布验收记录 v1

> 建立日期：2026-07-16
> 最近更新：2026-07-29
> 当前分支：`codex/rc1-manual-acceptance-guide`
> 实现提交：`6be04be feat(release): add installed product verification`
> CI 修复提交：`d242079 fix(ci): stabilize Windows release gates`
> Sidecar 恢复提交：`383c3d2 fix(desktop): recover sidecar after launch failure`
> Windows 短路径提交：`98a7be4 fix(windows): accept safe short path aliases`
> 契约元数据提交：`8d00df6 chore(contracts): refresh backend snapshot metadata`
> 自动编排提交：`1c20a17`、`cc0df5c`、`1070bee`、`2efbeb8`
> Warning 恢复提交：`3f58d6a`
> 双模式 UI 提交：`2e079b3`
> 契约变更：`FRONTEND-CONTRACT-CHANGE-REQUEST-v7.md`
> 状态：自动编排本地与当前 PR 三项产品门禁通过；真实模型、物理桌面和独立审查待完成；RC1 未签名风险已由用户接受，不宣称 V1 已发布

## 1. 验收结论

阶段 9 已建立可在 Windows CI 重复执行的正式安装版产品链路：NSIS 安装器安装到中文空格路径，启动真实 Electron Main/Preload、固定 CPython 3.12 onedir Sidecar、真实 SQLite 和 DPAPI SecretStore，并使用冻结 `fake` Provider 完成 Planner 到 Deployer。本轮在该基线上补齐后端高层自动编排，正式 Stage 页面不再由测试驱动逐条调用 Task、AgentRun、Tool、Artifact 和 Gate 底层命令。

本地 product E2E 已通过，且不是浏览器 Fixture：

- Managed Workspace 和 Direct Workspace 均真实创建、预检和启动；
- 五个 Room 均配置 Primary、Reviewer A、Reviewer B；
- Manual 和 Autonomous 均由项目主页正式 UI 实际切换并运行；
- Stage 正式运行通过高层 `orchestration/stream` NDJSON 命令完成一主双校、工具、产物、Gate 和交接；
- Warning 阻断、ChangeRequest、返工和再次审批均保留历史；
- CapabilityRequest 批准、拒绝和永久禁止 403 均由后端返回；
- ArtifactVersion、Quality Gate、Approval、Checkpoint、Handoff 和审计记录均持久化；
- 三方冲突、保护性 Checkpoint 恢复、应用/Backend/运行中 ToolCall 强杀和恢复均通过；
- 重启后通过真实 WebSocket Ticket/事件流收到持久事件重放；
- 卸载后 Direct Workspace 和隔离数据根保留，重装后已完成工作流可读取；
- Windows 8.3 短路径（本地复现 `AGENTP~1`、Runner 使用 `RUNNER~1`）下，日志、Managed/Direct Workspace 和 Checkpoint 均按真实目录校验，不把安全短名误判为 link/reparse point；
- S00-S09 页面从真实后端读取状态，页面中不存在 `fixtureDesktopPort`。

当前安装器 `Get-AuthenticodeSignature` 结果为 `NotSigned`，用户已确认 RC1 暂不购买或配置 Authenticode 签名并接受相应风险。签名因此不再是本次 RC1 的硬门禁，但未签名状态必须持续披露。[GitHub Actions Run `30400155883`](https://github.com/yx666814/AgentProgram/actions/runs/30400155883) 已在独立 Windows Runner 上验证当前实现的三个 job。本文件记录“阶段 9 自动化产品门禁通过”，不是“星协 V1 已正式发布”。

## 2. 交接清单逐项结果

| 阶段 8/9 交接要求 | 安装版执行证据 | 结果 |
| --- | --- | --- |
| Managed / Direct、预检、开始工作流 | 两类项目均调用真实 create/preflight/start operation；Managed 另走 pause/resume/stop | 通过 |
| 用户可见高层自动编排 | Stage 页面实际调用 `orchestration/stream`，模型只提交结构化计划，后端协调全部正式对象 | 通过 |
| Manual 双校、Gate、审批、Checkpoint、Artifact、Handoff | 当前完整报告共 12 个正式 AgentRun、8 次人工审批、10 个锁定 ArtifactVersion、10 个 Handoff | 通过 |
| Autonomous 自动前进与 Warning 阻断 | UI 切换 Autonomous；Designer 自动 Handoff；首次 Builder Warning 进入 `warning_blocked` | 通过 |
| `NEEDS_FIX` 返工与历史保留 | UI 切回 Manual 并点击“返回讨论”；Builder 保留 ChangeRequest/历史后重新编排、Gate 和审批 | 通过 |
| CapabilityRequest 批准、拒绝、永久禁止 | `shell.test` 各一次批准/拒绝；`remote.deploy` 返回 403 `capability_request.forbidden` | 通过 |
| 外部修改、三方冲突、保护性恢复、Checkpoint 恢复 | baseline/agent/user 三方内容冲突；`keep_agent`；restore-plan 创建保护检查点并恢复 agent checkpoint | 通过 |
| 断线、重启、Backend/Worker/Tool 异常与事件重放 | 强杀 Electron 完整进程树时保留 1 Task、1 Pending AgentRun、1 Running ToolCall；重启记录三类中断并重放事件；Worker 独立强杀由后端 process suite 覆盖 | 通过 |
| S00-S09 真实展示 | 14 张安装版截图：S00、S01、S02、S03、5 个 S04、S05-S09 | 通过 |
| 可验证代码、测试、构建和交付说明 | 生成 `src/index.js`、Node test、`package.json`、部署配置/脚本、安装/运行/回滚/已知问题文档；外部 Node 验证返回 0 | 通过 |
| 卸载保留 Direct Workspace，重装恢复数据 | NSIS 静默卸载删除安装目录；数据根、Direct 文件保留；重装读取 completed workflow | 通过 |

## 3. Product E2E 证据

执行命令：

```powershell
npm run test:product
```

本地结果：`1 passed`。证据写入忽略目录 `frontend/test-results/product-e2e/`，不提交用户数据、SQLite、日志或截图二进制。Windows CI 将提交、安装器字节数/SHA-256 和产品报告关键计数写入 Job Summary；`windows-product-evidence` artifact 只尽力上传测试证据目录并保留 7 天。Artifact 配额或传输失败不得掩盖 Build/Product E2E 的真实结论，也不得被描述成已上传的安装器。

当前最终报告的稳定断言字段：

```json
{
  "stages": ["planner", "designer", "builder", "reviewer", "deployer"],
  "formalAgentRuns": 12,
  "qualityGateEvaluations": 12,
  "lockedArtifactVersions": 10,
  "handoffs": 10,
  "manualApprovals": 8,
  "autonomousHandoffs": 2,
  "userVisibleOrchestration": true,
  "warningRework": true,
  "capabilityApproved": true,
  "capabilityRejected": true,
  "forbiddenCapabilityBlocked": true,
  "conflictResolved": true,
  "checkpointRestored": true,
  "interruptedTasks": 1,
  "interruptedAgentRuns": 1,
  "interruptedToolCalls": 1,
  "eventReplayAfterRestart": true,
  "reinstallRecovery": true,
  "directWorkspacePreserved": true
}
```

项目 ID 和工作流 ID 每次真实创建，不写死到文档或 Fixture。

## 4. 契约与后端耦合

冻结结果：69 个 REST operation、41 个事件、5 个 StageContract、23 个 Tool Catalog 项。新增的 REST operation 是用户级高层自动编排命令。product E2E 只使用生成类型允许的真实 operationId；没有新增前端别名或生产 Mock 成功。

| 文件 | SHA-256 |
| --- | --- |
| `frontend/contracts/openapi.json` | `47E838C0B27269D2AD83D49CFF2C752BD82A7C4817AF5B8A8C5CDA1CE0CFC47E` |
| `frontend/contracts/events.schema.json` | `57C07FC9ABF8FFE793EC4228C6A4ADF547E08F93F680CA47EA2B99EC3C755F62` |
| `frontend/contracts/capabilities.json` | `1EF9F820D4D4F89D7D54B2AE59B12368B4834A8BA786E1254DC4461E78367520` |
| `frontend/contracts/SHA256SUMS.json` | `938E6EC4C40FB544618A86025338CCD18CB38657478B0E922DD978FFCD64BA06` |

backend commit 为 `3f58d6a19d35fe849764202fec095fd906137372`，backend tree 为 `19df7dea8f4b76815712544f10b766dc09df30b8`。本轮新增 1 个用户级 REST operation；事件、StageContract、Tool Catalog 和冻结错误码目录未扩张。

## 5. 自动门禁

最终本地全量门禁已完成：

```powershell
uv run ruff format --check .
uv run ruff check .
uv run mypy src
uv run pytest -q
npm run contracts:verify
npm run lint
npm run typecheck
npm test
npm run test:e2e
npm run build:desktop
npm run build:sidecar
npx electron-builder --win nsis --config.electronDist="<cached Electron 43.1.1 ZIP>"
npm run test:product
```

结果：

- Ruff format：246 个文件通过；Ruff check：通过；
- Mypy strict：144 个 source file 无问题；
- Pytest：`733 passed, 12 skipped`；
- Vitest：39 个文件、75 个测试全部通过；
- Playwright：58 个测试全部通过；
- 安装版 product E2E：普通 TEMP 与 Windows 8.3 短路径 TEMP 均为 `1 passed`；
- 契约覆盖：69/41/5/23 通过。

远端 Run `30400155883`（提交 `600c8a7`）结果：`backend = success`、`frontend = success`、`windows-product = success`。Windows job 重新构建安装器并完成安装版 product E2E：`1 passed (1.8m)`；产品证据摘要步骤成功。仓库历史 artifact 占满配额，因此短期测试证据 artifact 没有实际生成；该传输告警不替代也不否定已成功的构建与产品测试。

本机 electron-builder 在线分发包获取没有进展，因此最终 NSIS 步骤使用本机已缓存且版本完全相同的 `electron-v43.1.1-win32-x64.zip`；electron-builder 明确输出 `using custom electronDist zip file`。CI 的全新 Windows Runner 仍执行 `npm run build:package`，用于独立验证在线构建路径。

生产包扫描：

- `app.asar` 共 279 个条目；测试、`test-results`、Playwright 报告和 Testing Library 路径为 0；
- `app.asar` 内置 `contracts/SHA256SUMS.json` SHA-256 为 `938E6EC4C40FB544618A86025338CCD18CB38657478B0E922DD978FFCD64BA06`，与源码冻结文件一致；
- Renderer 中 `fixtureDesktopPort`、测试密钥、Node `fs`、`ipcRenderer` 和 `__desktopTest` 定向扫描为 0；
- 最终安装器重建后重新执行 product E2E，结果仍为 `1 passed`。

## 6. 总需求追踪矩阵

| ID | V1 条款 | 界面 | 代码/契约 | 阶段 9 证据 | 当前结论 |
| --- | --- | --- | --- | --- | --- |
| R01 | 本地项目创建、打开、关闭和恢复 | S00、S01、S07 | Projects/Recovery operation | Managed/Direct、stop、崩溃恢复、重装读取 | 通过 |
| R02 | Managed 与 Direct Workspace | S01、S02 | WorkspaceMode、LocalPathPolicy | 中文空格真实目录、卸载后 Direct 保留 | 通过 |
| R03 | 预检、目录边界、Manifest、元数据 | S02 | Project preflight、默认 Manifest | Direct `src` 自动进入 source_paths；两类预检通过 | 通过 |
| R04 | 检查点、外部变化、三方冲突 | S07 | Checkpoint/Conflict/Restore operation | 三方冲突、保护检查点、restore-plan 和 restore | 通过 |
| R05 | 五阶段、状态机、Room、任务队列 | S03、S04 | Workflow/Room/Task/Orchestration operation | 安装版从 Stage UI 高层编排 Planner 到 Deployer 全链 | 通过 |
| R06 | 消息、Artifact、只读咨询 | S04、S05 | Workflow/Governance 契约 | 五个正式 ArtifactVersion 与历史读取 | 通过 |
| R07 | OpenAI Compatible、Anthropic、Fake | S08、S04、S09 | 三类 ModelAdapter、ModelProfile | 安装版 Fake 三 Profile；真实 Provider 继续由 adapter suite/人工验收 | 通过（真实模型人工项保留） |
| R08 | Primary、Reviewer A/B 一主双校 | S08、S04 | RoomModelAssignment | 五个 Room 均完成三 Profile 分配与 formal AgentRun | 通过 |
| R09 | Prompt、上下文、流式、取消、重试、用量 | S04、S09 | AgentRun/Orchestration NDJSON、ModelCall | 真实 DesktopPort NDJSON、嵌套 Agent 帧、取消、输出和用量持久化 | 通过 |
| R10 | 文件、搜索、Shell、Build、Test | S04、S09 | Tool Catalog/ToolCall | 真实文件工具、运行中 shell.test、Node test/build 验证 | 通过 |
| R11 | 权限、沙箱、Capability、进程、审计 | S06、S07、S09 | StageContract、LocalPathPolicy | 批准/拒绝/永久禁止、强杀、ToolCall 审计 | 通过 |
| R12 | Artifact、Gate、Approval、Handoff、ChangeRequest | S05、S06 | Governance operation | 10 个锁定 ArtifactVersion、12 次 Gate、10 个 Handoff、8 次人工批准、Builder 返工 | 通过 |
| R13 | Manual 与 Autonomous | S02、S06 | Workflow mode | 正式 UI 切换；Manual 完整审批；Autonomous 自动 Handoff/Warning 阻断 | 通过 |
| R14 | Worker、Tool、应用异常退出恢复 | S00、S07、S09 | RecoveryRecord、process supervisors | 安装版 Task/AgentRun/Tool 中断恢复；Worker process suite | 通过 |
| R15 | REST、WebSocket、重放、本地认证 | S00、S09 | 冻结契约、BackendClient、EventProxy | 动态本地认证、崩溃后真实持久事件重放 | 通过 |
| R16 | Renderer、Preload、安全桥、桌面交互 | S00-S09 | DesktopPort v3、CSP、IPC 白名单 | 安装版 14 张页面证据，无 Fixture 文案 | 通过 |
| R17 | Sidecar、动态端口、SecretStore、Windows 包、备份 | S00、S08、S09 | Main/Sidecar/DPAPI/NSIS | 中文空格安装、DPAPI Fake refs、卸载重装数据保留 | 通过 |
| R18 | 安装环境五阶段 Fake Model E2E | S00-S09 | 正式安装包 + Fake Adapter + Orchestration | `installed-five-stage.spec.ts`、普通/8.3 TEMP、用户可见自动编排与恢复 | 本地通过；Run `30400155883` 远端通过 |
| R19 | CI、静态、类型、安全、回归矩阵 | S09 | `.github/workflows/ci.yml` | backend/frontend/windows-product 三个 Windows job | Run `30400155883` 三项均通过 |

## 7. V1 完成定义追踪

| ID | 完成定义 | 当前证据 | 结论 |
| --- | --- | --- | --- |
| G01 | 阶段 0-9 全部门禁通过 | 阶段 0-8 已合并；阶段 9 本地普通/8.3 TEMP、自动编排 product E2E 与当前 PR CI 通过 | 真实模型、物理桌面和独立审查待完成 |
| G02 | Manual/Autonomous 五阶段完整运行 | 安装版正式 UI 切换、人工审批、自动 Handoff、Warning 阻断与返回讨论 | 通过 |
| G03 | 需求到审计可追踪 | PROJECT-PLAN、v1 设计、v1-v7 Change Request、阶段 7-9 验收 | 通过 |
| G04 | 权限、路径、模型、工具、SecretStore、进程无已知绕过 | 冻结 StageContract、DPAPI、LocalPathPolicy、短路径与 reparse 分离校验、强杀证据 | 本地通过 |
| G05 | Worker/Tool/应用强杀无虚假完成、无残留且可恢复 | 安装版活动 ToolCall 强杀和三类 interrupted 计数；后端 Worker suite | 本地通过 |
| G06 | 密钥和敏感数据不进入 DB/日志/事件/诊断 | 阶段 8 脱敏扫描、DPAPI、阶段 9隔离数据根 | 本地通过 |
| G07 | 安装包无系统 Python、动态端口、备份恢复 | 阶段 8安装门禁 + 阶段 9卸载重装 | 通过 |
| G08 | 真实小项目产出代码、测试、构建和交付说明 | ToolCall 生成并由外部 Node 验证 | 通过 |
| G09 | 零已知 P0/P1、完整测试和 CI | 当前无已知 P0/P1；本地全量与 Run `30400155883` 三项 CI 通过 | 通过 |
| G10 | 正式前端、Electron、Windows 安装包 | 安装版 S00-S09 和 NSIS 已完成；未签名状态已披露并由用户接受 | RC1 本地通过；公开分发未授权 |
| G11 | 所有可用前端功能由真实后端驱动 | 冻结 operationId、生产扫描、安装版无 Fixture、正式编排走后端高层命令 | 本地通过 |

## 8. 安装器与发布边界

| 产物 | 字节 | SHA-256 | 签名 |
| --- | ---: | --- | --- |
| `frontend/release/XingXie-1.0.0-rc.1-Setup.exe` | 122253379 | `26D0217BBCF8F8E040C9890A85B339E249BFCF8A6387DA74935C9A7F993D059B` | `NotSigned` |
| `frontend/release/win-unpacked/星协.exe` | 225485824 | `1DBAF7DF25F71F7682C4B1B18E053149322743306840450B8E9E2549AFADB3F8` | `NotSigned` |
| `frontend/release/win-unpacked/resources/backend/agent-platform-desktop-sidecar.exe` | 13047226 | `4523EECEE70A5A3959C1831218B131F759BF94B49C47875CC172554027C163B2` | `NotSigned` |
| `frontend/release/win-unpacked/resources/app.asar` | 13925302 | `8BEC7C7F12F7D6F03C235AAF31E0F08EF9B60EF47B28FBF5EFAC6D202913DE4F` | 不适用 |

当前剩余发布验收项：

- 完成 PR 独立审查并合并；
- 对外发布前按发布环境进行真实 OpenAI Compatible/Anthropic 手工验收；
- 多物理显示器移动和真实系统 DPI 切换保留为发布前人工桌面检查，不以浏览器缩放证据替代。

RC1 暂不购买或配置 Authenticode 签名；`NotSigned` 是已接受并必须披露的风险，不再列为本候选版硬门禁。以上剩余项目完成前，不使用“V1 已发布”或“全部完成”的结论。

## 9. 版本历史

| 版本 | 日期 | 变更 |
| --- | --- | --- |
| v1 | 2026-07-16 | 建立阶段 9 安装版五阶段 Fake Model E2E、崩溃恢复、事件重放、卸载重装、契约 Hash、总需求追踪与发布阻塞项。 |
| v1（更新） | 2026-07-29 | 保持正式文档版本 v1，追加高层自动编排、Warning 恢复、正式 UI 模式切换、当前测试计数、契约 Hash、安装包身份与未签名 RC1 决策。 |
| v1（CI 证据） | 2026-07-29 | 记录 Run `30400155883` 的 backend/frontend/windows-product 全绿、安装版 product E2E 与 artifact 配额边界。 |
