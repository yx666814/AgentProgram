# 星协 V1 阶段 8/9 桌面交接包 v1

> 日期：2026-07-15
> 交接分支：`codex/desktop-integration-v1`
> 仓库基线：`origin/master` at `a6a025e`
> 后端最近代码提交：`b61ba13620cf90c4367826f3b4e717e5dbf4cc09`
> 后端 Tree：`4fbc4ba8f708898c654997f59cc416e939a56b0f`
> 设计母版：`FRONTEND-DRAFT-MASTER-v1.md` 与 `reference-images/v1/`
> 正式前端验收：`FRONTEND-STAGE7-ACCEPTANCE-v1.md`
> 状态：阶段 7 Renderer 已冻结；阶段 8 Electron/Sidecar/Windows 集成与阶段 9 安装后 E2E 尚未完成

## 1. 交接边界

本文件是阶段 7 Renderer 向阶段 8、阶段 9 的唯一桌面交接基线。它不把测试用 `DesktopPort` Fixture、浏览器预览、Vite 构建或后端已有进程能力描述为已经完成的桌面产品。

冻结边界如下：

- Renderer 只依赖类型化 `DesktopPort`，后端仍是业务状态唯一权威；
- Renderer 不得取得 Session Token、API Key、SecretStore 明文、原始 IPC、文件系统、Shell、后端进程句柄或 WebSocket Ticket；
- Electron Main/Preload 只能暴露本文件批准的窄接口，不得把 `ipcRenderer`、Node builtin 或任意通道转交 Renderer；
- 阶段 8 可以为真实桌面能力提出版本化 `DesktopPort` 变更，但必须先更新契约、类型、边界测试和变更历史，不得静默扩权；
- 阶段 9 必须使用安装后的真实程序，不得用浏览器 Fixture 代替安装包验收。

## 2. Renderer 冻结产物

### 2.1 构建命令与契约覆盖

在当前基线执行：

```powershell
cd frontend
npm ci
npm run contracts:export
npm run generate:api
npm run contracts:verify
npm run build
```

结果：68 个 REST operation、41 个事件类型、5 个 StageContract、23 个 Tool Catalog 项通过覆盖校验；Vite 转换 61 个模块并输出 `frontend/dist/renderer/`。

### 2.2 Renderer 构建 Hash

单文件 SHA-256：

| 相对路径 | 字节 | SHA-256 |
| --- | ---: | --- |
| `assets/index-BvL3tYW3.css` | 24,793 | `879DB12E349682A3397D8BBABEFBE8997E7F57B7EDA3C584252B45109F600351` |
| `assets/index-JKbWlOR3.js` | 357,567 | `086E2E7C5E3E44C9A690C1BBB1BFEAFC2457BF4B5CE6A6504814040DFF88A284` |
| `assets/index-JKbWlOR3.js.map` | 1,522,623 | `2D8A81F0FC3E29027C349B4BAD3027B54477E4708F5CB4D28CD41B772363DAF7` |
| `index.html` | 461 | `43864C3199A0B75F1EBB7D5423F97B15FFC8388E4DCAC2C9BFE7A04F09A72C48` |
| `xingxie-icon.svg` | 1,150 | `6765B8F03E28F0DC24790183DC06F88B541160AE3903C98538F0C43531A988E4` |

Renderer 总 Hash：`63E0268997F2D07D927D0ADFB031530DFB7C001FDDEA2D36FC304E2719D28D9F`。

计算规则：按 `/` 分隔的相对路径升序生成 `UPPERCASE_SHA256␠␠relative/path\n` 清单，再对该 UTF-8、无 BOM 清单计算 SHA-256。`dist/renderer/` 是可复现构建产物，继续由 `.gitignore` 忽略，不作为源码提交。

### 2.3 DesktopPort 类型交付

- 类型文件：`frontend/dist/contracts/desktop-port.d.ts`
- SHA-256：`FE90925890720EE9BF70DA82582E8F933797E08DAEF026A59185EC99AD53291C`
- 类型来源：`frontend/electron/desktop-port.ts`
- 验证：TypeScript strict、ES2023、Bundler module resolution 检查通过。

该契约允许：类型化 REST Query/Command、持久事件订阅与重放、目录选择、原生确认、系统通知、打开本地位置、窗口状态和受控关闭请求。该契约不允许：Token、Secret 读取、任意文件读写、任意 Shell、任意 IPC、任意 URL 请求或直接 WebSocket 连接。

## 3. 冻结后端契约

| 契约 | SHA-256 |
| --- | --- |
| `frontend/contracts/openapi.json` | `F36C8E44C74059D039F67ED0FE321161039600FF80FD9F8A64EEA83556AA7D95` |
| `frontend/contracts/events.schema.json` | `B9247299BB0BC6CEE21D922E54B1B077DD725A46C7B517EC6E15D04642E0E959` |
| `frontend/contracts/capabilities.json` | `06763ACAC061D95E9BBFAC309A403D5092C4C8E676982353EBE9F30FCF2BA03A` |

阶段 8 不得在 Electron 适配层猜测字段、伪造成功状态或增加后端不存在的业务 operation。若真实集成发现缺口，必须增加新的契约变更文档并保留 v1-v4 历史。

## 4. 设计、测试和浏览器资源清单

### 4.1 设计与视觉母版

- 文字与组件母版：`docs/frontend/FRONTEND-DRAFT-MASTER-v1.md`；
- 页面参考图：`docs/frontend/reference-images/v1/`；
- 参考图共 30 张：14 个页面 × 浅/深主题共 28 张，另有浅/深总览各 1 张；
- 正式渲染基线：`frontend/tests/e2e/visual/pages.spec.ts-snapshots/`；
- 布局基线：黑白与冷灰蓝、浅/深双主题、Codex 类桌面分栏、柔和按压反馈。

### 4.2 阶段 7 测试报告

正式结果记录在 `docs/frontend/FRONTEND-STAGE7-ACCEPTANCE-v1.md`：

- ESLint：0 error，0 warning；
- TypeScript：0 error；
- Vitest：31 个文件、58 个测试通过；
- Visual：34 个测试通过，含 14 个页面 × 浅/深主题；
- Playwright E2E：58 个测试通过；
- 后端：Ruff、Mypy 通过，Pytest `718 passed, 12 skipped`；
- 后端源码在阶段 7 零修改。

阶段 8 修改 Renderer、Preload 或 DesktopPort 后，必须重新运行上述前端门禁；修改后端时必须同时运行完整后端门禁。

### 4.3 浏览器资源清单

生产 Renderer 仅装载：

- 本地 `index.html`；
- 本地单一 JavaScript bundle 与 sourcemap；
- 本地单一 CSS bundle；
- 本地 `xingxie-icon.svg`；
- Electron Preload 注入的 `window.desktop`。

没有 CDN、远程字体、远程脚本、远程样式、iframe、Web Worker、Service Worker、媒体资源或 Renderer 直连后端的运行时资源。bundle 中的 `https://provider.example/v1` 只是设置表单占位文案；React/React Router 错误帮助 URL和 W3C namespace 是库常量，不是批准的网络目标。

针对生产 bundle 的定向扫描结果均为 0：`frontend-contract-export`、`Authorization`、`Bearer `、`session_token`、`api_key`、`credential_value`、`node:fs`、`node:child_process`、`ipcRenderer`、`require(`、`FakeDesktopPort`、`fixtureDesktopPort`、`mockSuccess`。

### 4.4 CSP

冻结的阶段 7 `index.html` 尚未声明 CSP，因此 CSP 门禁当前状态是“阶段 8 待实现”，不能记为通过。阶段 8 加载本地 Renderer 时必须落实并自动测试以下最低策略：

```text
default-src 'self';
script-src 'self';
style-src 'self';
img-src 'self' data:;
font-src 'self';
connect-src 'none';
object-src 'none';
base-uri 'none';
frame-ancestors 'none';
frame-src 'none';
worker-src 'none';
media-src 'none';
form-action 'none'
```

`connect-src 'none'` 是强制边界：所有 REST/WebSocket 流量由 Electron Main 代理，Renderer 不直接访问动态端口。开发服务器可以使用独立、非生产 CSP，但不得带入安装包。

## 5. 阶段 8 实现责任

### 5.1 Electron Main 与 Preload

- 创建唯一 BrowserWindow，生产模式从冻结 Renderer 构建加载；
- `contextIsolation: true`、`nodeIntegration: false`、`sandbox: true`，禁止 `webviewTag`、远程模块、任意导航和新窗口；
- Preload 只暴露冻结或经版本化批准的 `DesktopPort`；
- IPC 通道逐个白名单、逐个校验参数、逐个绑定调用方 frame；
- 关闭、确认、目录选择、通知、打开位置和窗口状态走受控 Main handler；
- `openLocalLocation` 必须限制为后端已返回并经策略确认的本地路径，不得退化为任意 URL/Shell 打开器；
- Renderer 崩溃、Preload 失败和 Main 未处理异常必须进入诊断记录并触发安全关闭。

### 5.2 Sidecar Ready/Shutdown

- Main 启动固定 Python 3.12 onedir 后端，不依赖系统 Python 或用户 PATH；
- 后端只监听 `127.0.0.1`，使用 `port=0` 获取动态端口；
- 使用受控 Ready channel 返回实际端口、协议版本和进程身份，不能解析不可信普通日志猜端口；
- Ready 超时、提前退出、协议不匹配时保持启动页错误/恢复状态，不进入项目页；
- 正常退出先调用 `/api/v1/system/control` shutdown，再等待、超时终止进程树；
- Main、Backend、Project Worker、Tool 子进程的父子归属必须可审计，强杀后无残留进程。

### 5.3 临时 Session Token

- Token 由 Electron 会话生成，使用密码学安全随机源，禁止空值；
- 只通过继承句柄、受控启动参数或等价的非日志通道交给后端；
- Token 不进入 Renderer、命令日志、诊断包、数据库、事件、崩溃报告或安装器日志；
- Main 给 REST 请求加认证，Renderer 的 `BackendRequest` 不含认证字段；
- 应用重启轮换 Token，退出后旧 Token 失效；认证失败不得自动伪造重试成功。

### 5.4 REST 与 WebSocket

- `operationId` 必须从冻结 `capabilities.json` 解析为 method/path；禁止 Renderer 传入任意 URL；
- Main 负责参数编码、请求体、超时、取消、错误 envelope 和响应大小上限；
- WebSocket Ticket 通过冻结 ticket operation 获取，由 Main 使用并保持在 Main 内存中；
- Ticket 过期、断线、重复事件、非连续 `event_id` 和 replay 从持久游标恢复；
- Renderer 只收到验证过的 `EventEnvelope`，不得收到原始 socket、Ticket 或认证 header。

### 5.5 SecretStore Bridge

- 使用 Windows Credential Manager 或同等 OS SecretStore；数据库和后端契约只保存 `credential_ref` 与 `masked_hint`；
- Renderer 可以提交用户刚输入的密钥用于一次受控写入，但不能读取、枚举或回显明文；
- 当前 `DesktopPort v1` 未包含 SecretStore 写入方法，因此启用设置页保存/测试前必须先建立版本化契约变更和边界测试；在此之前相关控件继续禁用并显示真实原因；
- Main 只在后端发起已鉴权模型调用时短时提供密钥，禁止进入 Prompt、日志、事件、普通 IPC 或诊断包；
- 删除、覆盖、失败回滚和孤儿 credential 清理必须有明确语义与测试。

### 5.6 生命周期、诊断与恢复

- 接入后端 Watchdog、Worker/Tool 进程状态、stderr 脱敏摘要和异常退出恢复记录；
- 诊断导出必须先展示包含项/排除项，默认排除源代码、完整聊天、模型明文输出和密钥；
- 导出由 Main 使用受控保存对话框和后端诊断能力完成，Renderer 不获得任意文件写权限；
- 启动前检查单实例锁、数据库完整性、迁移状态、上次异常退出和恢复记录；
- 最小化、恢复、重启、Renderer reload 和 Main 崩溃不得造成虚假完成或重复命令。

### 5.7 onedir、安装器与升级恢复

- 固定 CPython 3.12 与所有后端依赖为 onedir sidecar；
- 安装包包含 Electron、Renderer、Preload、Main、onedir 后端、许可证和版本清单；
- 安装/卸载不得删除 Direct Workspace 用户文件；应用数据删除必须是单独、明确确认的操作；
- 升级前执行数据库在线备份、WAL checkpoint、完整性检查并记录版本；
- 升级失败进入恢复模式，可回滚程序版本并恢复兼容备份；
- 应用版本、后端版本、数据库迁移版本和契约 Hash 在诊断页可追踪。

## 6. 阶段 8 Windows 门禁

以下门禁必须在 Windows Runner 或真实 Windows 主机完成，浏览器测试不能替代：

| 门禁 | 必须证明的结果 |
| --- | --- |
| 无系统 Python | 清空/隔离 PATH 后仍可安装、启动、运行和卸载 |
| 中文与空格路径 | 安装目录、用户数据目录、项目目录均覆盖中文和空格 |
| 动态端口 | 多次启动端口可变化，只监听 `127.0.0.1`，冲突不失败 |
| 临时 Token | 每次会话轮换，旧 Token 失效，Renderer/日志/诊断无泄漏 |
| 安装/卸载 | 正常升级、覆盖安装、卸载和重装；用户项目不被删除 |
| 窗口与 DPI | 100%-200% DPI、跨显示器、最小化、恢复、重启 |
| 父进程消失 | Electron Main 被强杀后 Backend/Worker/Tool 全部退出 |
| 子进程强杀 | Backend、Worker、Tool 分别被强杀后状态可恢复且不虚假完成 |
| 无残留进程 | 正常退出、超时退出、崩溃、卸载后均无残留进程树 |
| 升级恢复 | 备份成功、迁移失败、程序回滚、数据库恢复模式完整覆盖 |
| 密钥不泄漏 | DB、日志、事件、IPC、崩溃报告、诊断包和安装日志扫描为零 |
| 安全边界 | CSP、导航限制、IPC 白名单、参数校验、无 Node/Token 暴露 |

阶段 8 完成证据至少包含：Windows Runner 日志、安装器 Hash、版本清单、进程树前后快照、端口监听证据、密钥泄漏扫描、升级恢复报告和重新运行的阶段 7 全量前端门禁。

## 7. 阶段 9 安装后 Fake Model E2E

阶段 9 使用正式安装包、真实 Electron Main/Preload、真实 onedir 后端、真实 SQLite 和阶段 5 Fake Model。测试项目必须位于包含中文与空格的真实目录，从 Planner 运行至 Deployer，并至少覆盖：

1. 创建 Managed Workspace 和 Direct Workspace，预检并开始工作流；
2. Manual 模式：双校、Quality Gate、用户审批、Checkpoint、Artifact、Handoff；
3. Autonomous 模式：允许项自动前进，Warning 进入 `warning_blocked`；
4. `NEEDS_FIX` 返工，回到正确上游阶段并保留历史；
5. CapabilityRequest 的申请、批准、拒绝与永久禁止能力；
6. 外部修改、三方冲突、保护性恢复和 Checkpoint 恢复；
7. WebSocket 断线、应用重启、Backend/Worker/Tool 异常退出与事件重放；
8. 前端 S00-S09 对真实后端状态的展示，不出现 Fixture 或伪造成功；
9. Deployer 生成可验证的代码、测试、构建报告、安装/运行/回滚和已知问题说明；
10. 卸载后 Direct Workspace 保持不变，重新安装可安全恢复应用数据。

真实模型只用于人工验收，不进入 CI 稳定性基线。阶段 9 只有在安装包全回归、零已知 P0/P1、需求追踪全部有证据、CI 全绿后才可宣称 V1 完成。

## 8. 总需求追踪矩阵

### 8.1 `PROJECT-PLAN.md` 1.1 V1 必须包含

| ID | V1 条款 | 界面 | 代码/契约 | 测试与证据 | 状态/后续门禁 |
| --- | --- | --- | --- | --- | --- |
| R01 | 本地项目创建、打开、关闭和恢复 | S00、S01、S07 | `application/projects`、`routes/projects.py`、`projects-page.tsx`、`recovery-page.tsx` | `test_project_api.py`、`project-flow.test.tsx`、`recovery.spec.ts` | 后端/Renderer 已覆盖；真实目录对话框与安装后恢复归阶段 8/9 |
| R02 | Managed 与 Direct Workspace | S01、S02 | 项目/Workspace 契约、`workspace-boundary.test.tsx` | `test_workspace_paths.py`、`test_project_api.py` | 后端/Renderer 已覆盖；中文空格路径与卸载保护归阶段 8 |
| R03 | 预检、目录边界、Manifest、元数据 | S02 | `application/projects`、`project_preflight`、`preflight-page.tsx` | `test_project_preflight.py`、`test_project_metadata.py`、`project-flow.test.tsx` | 已覆盖；安装后真实路径归阶段 9 |
| R04 | 内容寻址检查点、快照、外部变化、冲突 | S07 | 项目 checkpoint/conflict 模块、`recovery-page.tsx` | `test_project_checkpoints.py`、`test_project_changes.py`、`recovery.test.tsx` | 已覆盖；进程异常与升级恢复归阶段 8/9 |
| R05 | 五阶段、状态机、Room 隔离、任务队列 | S03、S04 | `application/workflows`、`stage-workspace-page.tsx` | `test_workflow_state_machine.py`、`room-isolation.test.tsx`、`five-stage-flow.spec.ts` | 后端/Renderer 已覆盖；安装后全链归阶段 9 |
| R06 | 不可变消息、更正、Artifact、只读咨询 | S04、S05 | workflows/governance 模块、message/artifact 页面 | `test_workflow_api.py`、`completion-chain.test.tsx`、`governance.test.tsx` | 已覆盖；安装后验收归阶段 9 |
| R07 | OpenAI Compatible 与 Anthropic | S08、S04、S09 | model adapters、ModelProfile 契约、设置页 | `test_model_adapters.py`、`test_agent_runtime.py`、`settings-contract.test.tsx` | 后端已覆盖；SecretStore 真实凭证桥和人工真实模型验收待阶段 8/9 |
| R08 | Primary、Reviewer A/B 一主双校 | S08、S04 | model runtime assignment、StageContract | `test_agent_runtime.py`、`test_stage5_five_stage_e2e.py`、`stage-workspace.test.tsx` | 后端/Renderer 已覆盖；安装后全链归阶段 9 |
| R09 | Prompt、上下文、摘要、流式、取消、超时、重试、用量 | S04、S09 | `application/model_runtime`、NDJSON/usage 契约 | `test_model_context.py`、`test_agent_runtime.py`、诊断与阶段页测试 | 后端已覆盖；当前 DesktopPort 不暴露 model.delta，真实桌面流式边界须阶段 8 版本化决定 |
| R10 | 文件、搜索、Shell、Build、Test 工具 | S04、S09 | tooling catalog/supervisor、ToolCall 审计 | `test_stage5_tooling.py`、`test_stage5_five_stage_e2e.py`、`diagnostics.test.tsx` | 后端/Renderer 审计已覆盖；真实进程树与安装后运行归阶段 8/9 |
| R11 | 权限、沙箱、CapabilityRequest、进程清理、审计 | S06、S07、S09 | StageContract、tool policy、worker/tool supervisor | `test_stage_contracts.py`、`test_worker_supervisor.py`、`stage-permissions.test.tsx` | 业务边界已覆盖；Windows 强杀/残留门禁待阶段 8 |
| R12 | StageContract、ArtifactVersion、Gate、Approval、Handoff、ChangeRequest | S05、S06 | governance 模块、artifact/approval 页面 | `test_stage5_api.py`、`test_stage5_five_stage_e2e.py`、`completion-chain.test.tsx` | 后端/Renderer 已覆盖；安装后全链归阶段 9 |
| R13 | Manual 与 Autonomous | S02、S06 | workflow policy、approval 页面 | `test_stage5_five_stage_e2e.py`、`warning-policy.test.tsx`、`five-stage-flow.spec.ts` | 后端/Renderer 已覆盖；安装后双模式归阶段 9 |
| R14 | Worker、Tool、应用异常退出恢复 | S00、S07、S09 | workers、tool supervisor、recovery records | worker/process 测试、`test_stage5_recovery.py`、`recovery.spec.ts` | 后端基础已覆盖；Electron 父进程与安装后恢复待阶段 8/9 |
| R15 | REST、WebSocket、重放、本地认证 | S00、S09、全局数据层 | 冻结 OpenAPI/Event/Capability、`client.ts`、`event-stream.ts` | API contract、event stream、`reconnect-replay.spec.ts` | 契约/Renderer 已覆盖；Main 代理、动态端口、临时 Token 待阶段 8 |
| R16 | Renderer、Preload 安全桥、桌面交互 | S00-S09 | `frontend/src`、`electron/desktop-port.ts`、`preload.ts` | 阶段 7 验收、preload/security 测试 | Renderer 完成；真实 Main/Preload、CSP、原生窗口待阶段 8 |
| R17 | Sidecar、动态端口、SecretStore、Windows 包、升级备份 | S00、S08、S09 | 后端 health/control/backup 基础；阶段 8 待建 Main/packaging | 后端 backup/settings/system 测试；本文件第 6 节 | 未完成，全部属于阶段 8 阻断门禁 |
| R18 | 安装环境五阶段 Fake Model E2E | S00-S09 | 正式安装包 + 阶段 5 Fake Model | 本文件第 7 节 | 未完成，属于阶段 9 阻断门禁 |
| R19 | CI、静态、类型、迁移、安全、回归矩阵 | S09 证据入口 | 前后端脚本、测试目录、后续 Windows workflow | 阶段 7 验收与后端追踪文档 | 当前代码门禁通过；桌面打包/安装 CI 待阶段 8/9 |

### 8.2 `PROJECT-PLAN.md` 第 12 章 V1 完成定义

| ID | 完成定义 | 关联需求/证据 | 当前结论 |
| --- | --- | --- | --- |
| G01 | 阶段 0-9 全部门禁通过 | 后端阶段追踪文档、阶段 7 验收、本文件 | 阶段 8/9 未完成，V1 未完成 |
| G02 | 五阶段 Manual/Autonomous 完整运行 | R05、R12、R13、阶段 9 E2E | 浏览器与后端证据已有；安装后证据缺失 |
| G03 | 需求、设计、代码、测试、产物、交接、审计可追踪 | 本矩阵、设计母版、阶段验收和契约 Hash | 阶段 7 以前可追踪；阶段 8/9 继续补证据 |
| G04 | 权限、路径、模型、工具、SecretStore、进程无已知绕过 | R02、R07、R10、R11、R17 | SecretStore 与 Electron/Windows 进程边界未验收 |
| G05 | 强杀无虚假完成、无残留且可恢复 | R14、第 6 节 Windows 门禁 | 后端测试已有；真实桌面父子进程门禁未完成 |
| G06 | 密钥和敏感数据不进入 DB/日志/事件/诊断 | R07、R11、R17、密钥泄漏扫描 | 后端脱敏已有；真实 SecretStore/安装包未验收 |
| G07 | 安装包不依赖系统 Python，支持动态端口和升级恢复 | R17、第 6 节 | 未完成，阶段 8 阻断项 |
| G08 | 真实项目生成可验证代码、测试、构建和交付说明 | R10、R12、R18、第 7 节 | 后端 Fake Model 证据已有；安装后真实项目未完成 |
| G09 | 零已知 P0/P1，完整测试和 CI 通过 | R19 | 阶段 7 门禁通过；阶段 8/9 CI 与缺陷结论缺失 |
| G10 | 正式前端、Electron 集成和 Windows 安装包完成 | R16、R17 | 正式前端完成；Electron/安装包未完成 |
| G11 | 所有可用前端功能由真实后端驱动 | 控件矩阵、冻结契约、阶段 7 验收 | Renderer 已通过；阶段 8 新增控件仍必须逐项映射 |

## 9. 提交与后续变更规则

- 本次 Task 12 只提交本文件与 `frontend/dist/contracts/desktop-port.d.ts`；
- `frontend/dist/renderer/` 保持忽略，只用 Hash 冻结，不提交二进制构建；
- 阶段 8 实现提交不得重写或删除本文件；契约或责任变化新建 v2；
- `DesktopPort` 发生兼容性变化时同步更新源码、`dist/contracts`、Preload 边界测试、Renderer 使用方和版本历史；
- 阶段 8/9 未通过前，界面与文档不得显示“V1 已完成”或“桌面集成已完成”。

## 10. 版本历史

| 版本 | 日期 | 变更 |
| --- | --- | --- |
| v1 | 2026-07-15 | 冻结 Renderer/契约 Hash，记录设计和测试证据、资源与 CSP，定义阶段 8/9 责任、Windows 门禁、安装后 Fake Model E2E 和总需求追踪矩阵。 |
