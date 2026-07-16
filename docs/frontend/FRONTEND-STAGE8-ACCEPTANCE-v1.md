# 星协 V1 阶段 8 桌面集成与 Windows 打包验收记录 v1

> 日期：2026-07-16
> 分支：`codex/desktop-integration-v1`
> 阶段 7 交接提交：`45ede6e docs(frontend): hand off renderer to desktop integration`
> 阶段 8 实现提交：`72edead feat(desktop): integrate secure Windows runtime`
> 契约变更：`FRONTEND-CONTRACT-CHANGE-REQUEST-v5.md`、`FRONTEND-CONTRACT-CHANGE-REQUEST-v6.md`
> 状态：阶段 8 规划门禁通过；阶段 9 尚未完成，不代表星协 V1 已发布

## 1. 交付范围

阶段 8 已完成：

- Electron Main、Preload 和冻结 `DesktopPort` 的真实适配；
- 后端 Sidecar 动态 `127.0.0.1` 端口、临时 Session Token、专用 Ready 控制帧和正常 Shutdown；
- REST operationId 白名单映射、WebSocket Ticket、事件代理、重连、重放和去重；
- `contextIsolation: true`、`nodeIntegration: false`、`sandbox: true`、Renderer `connect-src 'none'`；
- 导航、窗口创建、权限请求、IPC channel 和本地路径白名单；
- Windows `safeStorage` / DPAPI 加密 SecretStore，以及后端独立 loopback Secret Bridge；
- S08 API Key 一次写入、引用持久化、失败回滚和旧引用清理；
- S09 原生保存对话框与脱敏诊断包导出；
- 固定 CPython 3.12 的 PyInstaller onedir Sidecar；
- electron-builder + NSIS 安装器、中文空格安装路径、卸载保留应用数据；
- 启动自动迁移、迁移前备份、迁移失败恢复和 Windows SQLite 文件句柄修复；
- Electron 父进程消失时 Sidecar 自动退出。

阶段 8 没有新增任何后端业务 operation。SecretStore 和诊断导出均通过版本化 DesktopPort Change Request 批准；后端仍是业务状态唯一权威。

## 2. 契约基线与 Hash

契约快照由阶段 8 实现提交 `72edeada9e982d6b09577682775e37d85d8dccda` 导出，backend tree 为 `ea693dbcd91ffeadfc7d4ab48aab98b11eca1fce`。

| 文件 | SHA-256 |
| --- | --- |
| `frontend/contracts/openapi.json` | `C0DCD6C4179ACAAEE47B2D4541651076E67425F10E093568BFCDECD8652DD9D5` |
| `frontend/contracts/events.schema.json` | `C53BA93C1230DBD80BDB5A55264597C9ED9606BC95ECD7C3C9D1AEA35089E5D6` |
| `frontend/contracts/capabilities.json` | `FF1F8DF2D702A08388B3B088EFC7B901AF35CA489C62E6DA8F7B31481008CD6D` |
| `frontend/contracts/SHA256SUMS.json` | `DFB1F560DBF3A0B3222529717770BCC250B29BF16944C91CA142D587840A7D67` |

覆盖验证仍为：68 个 REST operation、41 个事件类型、5 个 StageContract、23 个 Tool Catalog 项。没有增加前端别名、伪 operation 或不存在的 Settings/ModelProfileTest 成功状态。

最终 `app.asar` 内的 `contracts/SHA256SUMS.json` 已提取核对，与上述 backend commit、tree 和三类契约 Hash 完全一致。

## 3. 前端门禁结果

执行：

```powershell
npm run lint
npm run typecheck
npm test
npm run test:e2e
npm run contracts:verify
npm run build:desktop
```

结果：

- ESLint：0 error，0 warning；
- TypeScript：0 error；
- Vitest：37 个文件、67 个测试全部通过；
- Playwright：58 个测试全部通过；
- S00-S09 浅色/深色页面快照全部通过，S08/S09 不需要更新实现快照；
- 1280×720、1440×900、1920×1080 与 100%–200% DPI 模拟继续通过；
- Renderer 生产构建：61 个模块；
- 运行时加载的 HTML、JS、CSS 中，认证材料、Node builtin、原始 IPC 和测试 Fixture 定向扫描为 0；
- `app.asar` 中没有测试、Playwright 报告或 Testing Library 路径。

锁定的 `docs/frontend/reference-images/v1/` 未修改。

## 4. 后端门禁结果

执行：

```powershell
uv run ruff format --check .
uv run ruff check .
uv run mypy src
uv run pytest -q
```

结果：

- Ruff format：238 个文件通过；
- Ruff check：全部通过；
- Mypy：138 个源文件无问题；
- Pytest：`727 passed, 12 skipped`；
- 桌面数据库、Secret Bridge 和 Main 定向测试：12 个通过；
- 迁移失败恢复测试确认 revision 回到 `0008_model_runtime`，部分迁移标记被清除；
- `_database_revision()` 显式关闭 SQLite 只读连接，避免 Windows 文件句柄阻止备份恢复覆盖。

## 5. 安全与隐私证据

- Renderer 不取得 Session Token、WebSocket Ticket、Secret Bridge Origin/Token、DPAPI 密文或 Node 文件系统；
- Session Token 和 Bridge Token 每次启动随机生成，只通过 Sidecar stdin 启动帧传递；
- REST、WebSocket 和 Bridge 只监听 IPv4 loopback；
- Preload 只暴露固定 DesktopPort 方法，Main 验证可信主 Frame；
- SecretStore 文件不包含 API Key 明文，Renderer 只能写入和删除引用，不能读取、枚举或导出；
- 打包桌面冒烟完成 Renderer 写入、Main DPAPI 加密、Bridge 解析和引用删除；
- 诊断导出排除源码、完整聊天、模型正文、密钥、Token、Event 任意 payload、Tool arguments 和 result 正文；
- ToolCall 只导出 ID、能力、Hash、状态、错误码和时间等安全投影；
- 日志额外脱敏 Bearer、`sk-` 和常见凭证字段；
- CSP 禁止 Renderer 直连后端或任意网络目标。

## 6. Windows Sidecar 与进程门禁

冻结 Sidecar 使用 Python `3.12.13`、PyInstaller `6.21.0` onedir 构建。真实 Windows 验证：

- 清空 `PATH`，移除 `PYTHONHOME` / `PYTHONPATH` 后可启动；
- 数据目录包含中文和空格；
- Ready 帧返回动态 `127.0.0.1` 端口；
- `health` 200、`readiness` 200、`shutdown` 202、进程退出码 0；
- Electron 父进程退出后 Sidecar 自动退出；
- 打包目录和安装后桌面冒烟退出后，`星协.exe` 与 Sidecar 残留进程均为 0。

## 7. 安装、卸载与产物

最终安装器：`frontend/release/XingXie-0.1.0-Setup.exe`。

安装器验收：

- 安装到工作树内唯一的中文空格目录；
- 安装后执行真实 Electron → Sidecar → REST → SecretStore Bridge 冒烟；
- 原生程序退出后无残留进程；
- 静默卸载返回 0，NSIS 延迟自清理在 30 秒内删除完整程序目录；
- `C:\Users\ye\AppData\Roaming\星协\data\agent.db` 保留；
- 没有手工删除安装目录来替代卸载器结果。

最终产物：

| 产物 | 字节 | SHA-256 |
| --- | ---: | --- |
| Renderer JS `index-CL3HPFz6.js` | 361279 | `05DA33479A48FD3C83A3C50D21D2AC17D8303A78F0B9AC4B9C306C6510897C90` |
| Renderer CSS `index-DKegUdeE.css` | 24910 | `E3C19F6A6845333C48B64E4B5C5250690CFE16EBFEDDCF418EE70A567FCAA862` |
| Sidecar EXE | 13018161 | `8D8B50C2504D6AF5104220F67A7ADE421EA7E22664F9283FE6879764F1C7EC20` |
| `app.asar` | 13842102 | `0913F51EE6E80E9B2DD4FB402F58A0EC308602857D45AEE7F3E2A7A25FD3F2EE` |
| NSIS 安装器 | 122294282 | `C8CC1872C78CB1451268ADD5D6BF52E28B4BE394B28B7785E09A2C945AD73B92` |

构建产物和运行时验收数据由 `.gitignore` 排除，不提交二进制、数据库、日志或临时安装目录。

## 8. 已知非阶段 8 阻塞项

- 安装器和主程序当前没有 Authenticode 证书签名；正式对外分发前应在阶段 9/发布流程配置可信代码签名；
- 后端没有数据库迁移版本 Query，S09 不推断或伪造数据库版本；诊断包记录真实 system/readiness、契约 Hash 和恢复信息；
- 后端没有 ModelProfileTest 或全局 Settings operation，相应按钮继续禁用并显示真实原因；
- ModelProfile 全局事件仍没有按工作流 replay 的可靠投递通道，沿用 v4 记录；
- 多物理显示器移动、真实系统 DPI 切换、最小化/恢复/重启组合，以及安装后完整五阶段 Fake Model 项目流程归阶段 9；
- PyInstaller 对可选 `tzdata`、`pysqlite2`、`MySQLdb` 的收集警告不影响 SQLite/UTC 桌面运行；真实构建和安装冒烟已通过。

## 9. 进入阶段 9 的边界

阶段 9 必须使用正式安装后的真实桌面程序和阶段 5 Fake Model，让真实中文空格路径项目从 Planner 运行到 Deployer，并覆盖 MANUAL/AUTONOMOUS、返工、审批、冲突、重启恢复、前端展示和交付资料。

在阶段 9 全产品 E2E、发布签名和最终需求追踪完成前，不得宣称星协 V1 已完成。

## 10. 版本历史

| 版本 | 日期 | 变更 |
| --- | --- | --- |
| v1 | 2026-07-16 | 记录阶段 8 Electron/Sidecar/SecretStore/诊断/打包交付、契约 Hash、前后端门禁、Windows 安装卸载证据、最终产物 Hash 和阶段 9 边界。 |
