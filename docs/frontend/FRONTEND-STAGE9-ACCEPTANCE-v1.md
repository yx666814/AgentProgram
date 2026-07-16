# 星协 V1 阶段 9 全产品 E2E 与发布验收记录 v1

> 日期：2026-07-16
> 分支：`codex/stage9-product-e2e`
> 实现提交：`6be04be feat(release): add installed product verification`
> CI 修复提交：`d242079 fix(ci): stabilize Windows release gates`
> 契约变更：`FRONTEND-CONTRACT-CHANGE-REQUEST-v7.md`
> 状态：本地安装版全产品 E2E 通过；PR CI、独立审查与 Authenticode 签名尚未完成，不宣称 V1 已发布

## 1. 验收结论

阶段 9 已建立可在 Windows CI 重复执行的正式安装版产品链路：NSIS 安装器安装到中文空格路径，启动真实 Electron Main/Preload、固定 CPython 3.12 onedir Sidecar、真实 SQLite 和 DPAPI SecretStore，并使用冻结 `fake` Provider 完成 Planner 到 Deployer。

本地 product E2E 已通过，且不是浏览器 Fixture：

- Managed Workspace 和 Direct Workspace 均真实创建、预检和启动；
- 五个 Room 均配置 Primary、Reviewer A、Reviewer B；
- Manual 和 Autonomous 均实际运行；
- Warning 阻断、ChangeRequest、返工和再次审批均保留历史；
- CapabilityRequest 批准、拒绝和永久禁止 403 均由后端返回；
- ArtifactVersion、Quality Gate、Approval、Checkpoint、Handoff 和审计记录均持久化；
- 三方冲突、保护性 Checkpoint 恢复、应用/Backend/运行中 ToolCall 强杀和恢复均通过；
- 重启后通过真实 WebSocket Ticket/事件流收到持久事件重放；
- 卸载后 Direct Workspace 和隔离数据根保留，重装后已完成工作流可读取；
- S00-S09 页面从真实后端读取状态，页面中不存在 `fixtureDesktopPort`。

当前安装器 `Get-AuthenticodeSignature` 结果仍为 `NotSigned`。PR 的 GitHub Actions 也只有在推送后才能产生独立 Windows Runner 结果。因此本文件记录“阶段 9 本地产品门禁通过”，不是“星协 V1 已正式发布”。

## 2. 交接清单逐项结果

| 阶段 8/9 交接要求 | 安装版执行证据 | 结果 |
| --- | --- | --- |
| Managed / Direct、预检、开始工作流 | 两类项目均调用真实 create/preflight/start operation；Managed 另走 pause/resume/stop | 通过 |
| Manual 双校、Gate、审批、Checkpoint、Artifact、Handoff | 五阶段正式 AgentRun；4 次人工 Gate 批准；5 个锁定 ArtifactVersion；5 个 Handoff | 通过 |
| Autonomous 自动前进与 Warning 阻断 | Designer 自动 Handoff；首次 Builder Warning 进入 `warning_blocked` | 通过 |
| `NEEDS_FIX` 返工与历史保留 | Builder 产生 ChangeRequest，切回 Manual 后以既有 Artifact Hash 创建新版本并重新 Gate | 通过 |
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

本地结果：`1 passed`。证据写入忽略目录 `frontend/test-results/product-e2e/`，不提交用户数据、SQLite、日志或截图二进制；PR 的 `windows-product-evidence` artifact 上传安装器、14 张 PNG 和 `stage9-product-report.json`。

报告的稳定断言字段：

```json
{
  "stages": ["planner", "designer", "builder", "reviewer", "deployer"],
  "formalAgentRuns": 6,
  "qualityGateEvaluations": 6,
  "lockedArtifactVersions": 5,
  "handoffs": 5,
  "manualApprovals": 4,
  "autonomousHandoffs": 1,
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

冻结结果：68 个 REST operation、41 个事件、5 个 StageContract、23 个 Tool Catalog 项。product E2E 只使用生成类型允许的真实 operationId；没有新增前端别名或生产 Mock 成功。

| 文件 | SHA-256 |
| --- | --- |
| `frontend/contracts/openapi.json` | `BC393FDDF78B363F67874D6656B9E308A7421FC8D30FFA29713470EA7BE83173` |
| `frontend/contracts/events.schema.json` | `34D8245F50A0A26FC4449F79B5BD9990F7BCD72F31B4AD0EA160FD22C0840E15` |
| `frontend/contracts/capabilities.json` | `42F234EE0ABD9A7A6461D371A6D27C76C9BE95B0B2B8524C2255082CA4D64E2C` |
| `frontend/contracts/SHA256SUMS.json` | `5F658133AE572BAFECC342EB2478EA1F0C2CD4C07FB4B9C68CA72B3D6DA4F51B` |

backend commit 为 `d242079aae9feddf8568f022322f8fd71b7a50f4`，backend tree 为 `eae9b0989393ea83233b646199458c104a11711d`。

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

- Ruff format：238 个文件通过；Ruff check：通过；
- Mypy：138 个 source file 无问题；
- Pytest：`728 passed, 12 skipped`；唯一 warning 来自 FastAPI TestClient 的第三方弃用提示；
- Vitest：38 个文件、69 个测试全部通过；
- Playwright：58 个测试全部通过；
- 安装版 product E2E：`1 passed`；
- 契约覆盖：68/41/5/23 通过。

本机 electron-builder 在线分发包获取没有进展，因此最终 NSIS 步骤使用本机已缓存且版本完全相同的 `electron-v43.1.1-win32-x64.zip`；electron-builder 明确输出 `using custom electronDist zip file`。CI 的全新 Windows Runner 仍执行 `npm run build:package`，用于独立验证在线构建路径。

生产包扫描：

- `app.asar` 共 279 个条目；测试、`test-results`、Playwright 报告和 Testing Library 路径为 0；
- `app.asar` 内 `contracts/SHA256SUMS.json` SHA-256 为 `5F658133AE572BAFECC342EB2478EA1F0C2CD4C07FB4B9C68CA72B3D6DA4F51B`，与源码冻结文件一致；
- Renderer 中 `fixtureDesktopPort`、测试密钥、Node `fs`、`ipcRenderer` 和 `__desktopTest` 定向扫描为 0；
- 最终安装器重建后重新执行 product E2E，结果仍为 `1 passed`。

## 6. 总需求追踪矩阵

| ID | V1 条款 | 界面 | 代码/契约 | 阶段 9 证据 | 当前结论 |
| --- | --- | --- | --- | --- | --- |
| R01 | 本地项目创建、打开、关闭和恢复 | S00、S01、S07 | Projects/Recovery operation | Managed/Direct、stop、崩溃恢复、重装读取 | 通过 |
| R02 | Managed 与 Direct Workspace | S01、S02 | WorkspaceMode、LocalPathPolicy | 中文空格真实目录、卸载后 Direct 保留 | 通过 |
| R03 | 预检、目录边界、Manifest、元数据 | S02 | Project preflight、默认 Manifest | Direct `src` 自动进入 source_paths；两类预检通过 | 通过 |
| R04 | 检查点、外部变化、三方冲突 | S07 | Checkpoint/Conflict/Restore operation | 三方冲突、保护检查点、restore-plan 和 restore | 通过 |
| R05 | 五阶段、状态机、Room、任务队列 | S03、S04 | Workflow/Room/Task operation | 安装版 Planner 到 Deployer 全链 | 通过 |
| R06 | 消息、Artifact、只读咨询 | S04、S05 | Workflow/Governance 契约 | 五个正式 ArtifactVersion 与历史读取 | 通过 |
| R07 | OpenAI Compatible、Anthropic、Fake | S08、S04、S09 | 三类 ModelAdapter、ModelProfile | 安装版 Fake 三 Profile；真实 Provider 继续由 adapter suite/人工验收 | 通过（真实模型人工项保留） |
| R08 | Primary、Reviewer A/B 一主双校 | S08、S04 | RoomModelAssignment | 五个 Room 均完成三 Profile 分配与 formal AgentRun | 通过 |
| R09 | Prompt、上下文、流式、取消、重试、用量 | S04、S09 | AgentRun NDJSON、ModelCall | 真实 DesktopPort NDJSON、输出和用量持久化 | 通过 |
| R10 | 文件、搜索、Shell、Build、Test | S04、S09 | Tool Catalog/ToolCall | 真实文件工具、运行中 shell.test、Node test/build 验证 | 通过 |
| R11 | 权限、沙箱、Capability、进程、审计 | S06、S07、S09 | StageContract、LocalPathPolicy | 批准/拒绝/永久禁止、强杀、ToolCall 审计 | 通过 |
| R12 | Artifact、Gate、Approval、Handoff、ChangeRequest | S05、S06 | Governance operation | 5 个锁定 ArtifactVersion、6 次 Gate、5 个 Handoff、4 次人工批准、Builder 返工 | 通过 |
| R13 | Manual 与 Autonomous | S02、S06 | Workflow mode | Manual 完整审批；Autonomous 自动 Handoff/Warning 阻断 | 通过 |
| R14 | Worker、Tool、应用异常退出恢复 | S00、S07、S09 | RecoveryRecord、process supervisors | 安装版 Task/AgentRun/Tool 中断恢复；Worker process suite | 通过 |
| R15 | REST、WebSocket、重放、本地认证 | S00、S09 | 冻结契约、BackendClient、EventProxy | 动态本地认证、崩溃后真实持久事件重放 | 通过 |
| R16 | Renderer、Preload、安全桥、桌面交互 | S00-S09 | DesktopPort v3、CSP、IPC 白名单 | 安装版 14 张页面证据，无 Fixture 文案 | 通过 |
| R17 | Sidecar、动态端口、SecretStore、Windows 包、备份 | S00、S08、S09 | Main/Sidecar/DPAPI/NSIS | 中文空格安装、DPAPI Fake refs、卸载重装数据保留 | 通过 |
| R18 | 安装环境五阶段 Fake Model E2E | S00-S09 | 正式安装包 + Fake Adapter | `installed-five-stage.spec.ts` 和 CI artifact | 本地通过，CI 待 PR |
| R19 | CI、静态、类型、安全、回归矩阵 | S09 | `.github/workflows/ci.yml` | backend/frontend/windows-product 三个 Windows job | 工作流已实现，远端结果待 PR |

## 7. V1 完成定义追踪

| ID | 完成定义 | 当前证据 | 结论 |
| --- | --- | --- | --- |
| G01 | 阶段 0-9 全部门禁通过 | 阶段 0-8 已合并；阶段 9 本地 product E2E 通过 | PR CI/审查/签名未完成 |
| G02 | Manual/Autonomous 五阶段完整运行 | 安装版五阶段、人工审批、自动 Handoff、Warning 阻断 | 通过 |
| G03 | 需求到审计可追踪 | PROJECT-PLAN、v1 设计、v1-v7 Change Request、阶段 7-9 验收 | 通过 |
| G04 | 权限、路径、模型、工具、SecretStore、进程无已知绕过 | 冻结 StageContract、DPAPI、LocalPathPolicy、强杀证据 | 本地通过 |
| G05 | Worker/Tool/应用强杀无虚假完成、无残留且可恢复 | 安装版活动 ToolCall 强杀和三类 interrupted 计数；后端 Worker suite | 本地通过 |
| G06 | 密钥和敏感数据不进入 DB/日志/事件/诊断 | 阶段 8 脱敏扫描、DPAPI、阶段 9隔离数据根 | 本地通过 |
| G07 | 安装包无系统 Python、动态端口、备份恢复 | 阶段 8安装门禁 + 阶段 9卸载重装 | 通过 |
| G08 | 真实小项目产出代码、测试、构建和交付说明 | ToolCall 生成并由外部 Node 验证 | 通过 |
| G09 | 零已知 P0/P1、完整测试和 CI | 当前无已知 P0/P1；本地全量已通过，远端 CI 待 PR | 待远端 CI |
| G10 | 正式前端、Electron、Windows 安装包 | 安装版 S00-S09 和 NSIS 已完成 | 对外发布仍缺 Authenticode |
| G11 | 所有可用前端功能由真实后端驱动 | 冻结 operationId、生产扫描、安装版无 Fixture | 本地通过 |

## 8. 安装器与发布边界

| 产物 | 字节 | SHA-256 | 签名 |
| --- | ---: | --- | --- |
| `frontend/release/XingXie-0.1.0-Setup.exe` | 122297459 | `3A5E80E877FA5E8860245C7DACED5EA3C13EF9DDF69BC9AF16B06F619BA07229` | `NotSigned` |
| `frontend/release/win-unpacked/星协.exe` | 225486336 | `2FF6CD0CAEE17193C985A8B32E3E4A0D5FB1B30406FA2BB6B5EAA5DB434BC875` | `NotSigned` |
| `frontend/release/win-unpacked/resources/app.asar` | 13845641 | `C370B9FA3EFAB4FC1F5D3FD9238155E80514CF955A9CC1CD74A06790E8F57E25` | 不适用 |
| `agent-platform-desktop-sidecar.exe` | 13018945 | `1795595AD36DAEC3762BE8FBE4AEC5FCE9C7DCA5FB61811A9BAD663F08A510E5` | `NotSigned` |

当前发布阻塞项：

- 配置可信 Authenticode 代码签名和时间戳，并验证安装器与主程序签名；
- 推送分支并取得 GitHub Actions backend、frontend、windows-product 三个 job 全绿；
- 完成 PR 独立审查并合并；
- 对外发布前按发布环境进行真实 OpenAI Compatible/Anthropic 手工验收；
- 多物理显示器移动和真实系统 DPI 切换保留为发布前人工桌面检查，不以浏览器缩放证据替代。

以上项目完成前，不使用“V1 已发布”或“全部完成”的结论。

## 9. 版本历史

| 版本 | 日期 | 变更 |
| --- | --- | --- |
| v1 | 2026-07-16 | 记录阶段 9 安装版五阶段 Fake Model E2E、崩溃恢复、事件重放、卸载重装、契约 Hash、总需求追踪与发布阻塞项。 |
