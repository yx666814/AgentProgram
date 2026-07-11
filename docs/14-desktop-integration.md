# Windows 桌面端与后端集成

## 1. 范围

MVP 为 Windows-first Electron 桌面应用。本文只规定后端需要提供的启动、认证、目录、密钥、更新和关闭契约；前端页面设计不在本文范围。

## 2. 进程关系

```text
Electron Main
├─ Electron Renderer (React)
└─ Python Backend Sidecar
    ├─ FastAPI Main Process
    ├─ Project Workers
    └─ Tool Processes
```

Renderer 不直接访问 Node、文件系统、Shell 和系统密钥。

Electron Main/Preload 与 Python Backend 之间除 REST/WebSocket 外，保留一个继承 stdio 的长度帧 Control Channel，用于 ready、shutdown 和 SecretStore 请求。该通道不对 Renderer 和其他本机进程开放。

## 3. 后端启动

Electron Main：

1. 取得单实例应用锁。
2. 生成随机 local session token。
3. 创建受保护启动配置文件或环境句柄。
4. 选择随机本机端口。
5. 启动打包后的 Python Backend。
6. 读取后端 ready 握手。
7. 调用 readiness。
8. 创建 Renderer Window。

后端只绑定 `127.0.0.1`，不绑定 `0.0.0.0`。

## 4. Ready 握手

后端通过启动管道或受控 stdout 输出一次结构化 Ready 信息：

```text
protocol_version
backend_version
pid
port
session_id
database_version
ready
```

普通日志写 stderr 或日志文件，不能污染握手协议。

## 5. 本地令牌

- 每次 Electron 启动生成新 token。
- Token 只存在于 Electron Main/Preload 和 Backend 当前会话内存。
- Renderer 不直接获得 token，只调用 contextBridge 暴露的窄 API。
- Preload 发起 REST Bearer Token 请求并管理 WebSocket 一次性 Ticket。
- 后端关闭后 token 失效。
- 不把 token 写入普通日志和 LocalStorage。

## 6. 原生能力归属

Electron Main 负责：

- 选择项目目录。
- 打开文件资源管理器。
- 桌面通知。
- 系统托盘和窗口管理。
- 自动更新。
- 操作系统 Keychain/Safe Storage。
- 请求退出。

FastAPI 不创建 tkinter 或其他原生对话框。

## 7. SecretStore

后端定义 SecretStore Port，Electron Main 提供系统安全存储桥接。数据库只保存 credential_ref 和 masked_hint。

后端请求密钥时：

- 指定 credential_ref。
- Electron Main 验证当前 session。
- 返回到受控调用链，不传给 Renderer。
- 密钥不进入日志、数据库、IPC 审计 payload 和工具环境。

第一版可在 Electron Main 使用 Windows DPAPI/Electron safeStorage 封装本地密钥文件，具体实现需有独立测试。

## 8. 应用目录

```text
%LOCALAPPDATA%/AgentProgram/
├─ data/
├─ snapshots/
├─ logs/
├─ cache/
├─ backups/
├─ runtime/
└─ managed-workspaces/
```

安装目录只包含程序文件，不写用户运行数据。

## 9. Python 运行时

正式安装包包含固定 Python 3.12 运行时和锁定依赖，用户无需预装 Python。后端不能依赖开发机虚拟环境和全局 PATH。

MVP 使用 PyInstaller `onedir` 打包 Python Sidecar。`onedir` 比单文件模式启动更快，也更容易定位依赖和减少运行时临时解压问题。后端代码使用 `importlib.resources` 和显式应用目录，不能依赖源码相对路径。

## 10. 端口与实例

- 优先随机端口并通过握手告知 Electron。
- 不使用写死的 8000/5173。
- 单 Electron 实例对应一个 Backend Main Process。
- 检测残留旧进程时先验证 session 和父进程，不误杀无关 Python。
- 后端可记录 parent PID，父进程消失后进入安全关闭。

## 11. 前端资源

生产模式 React 静态资源由 Electron 本地加载。Preload 获得运行时 API Base URL 和 session token，通过 contextBridge 暴露项目、聊天、任务和事件等窄接口。Renderer 不获得原始 token，localhost 端口不能编译写死。

## 12. 自动更新

更新流程：

1. 通知后端准备关闭。
2. 停止新任务并处理活动 Worker。
3. 创建数据库备份。
4. 退出后端。
5. Electron 安装更新。
6. 新版本启动并执行 Alembic migration。
7. Migration/完整性失败时进入恢复模式。

程序更新与用户数据目录分离。

## 13. 安全关闭

Electron 请求 `/system/shutdown`：

- 后端停止接受新任务。
- 取消模型与工具。
- 终止 Worker 和进程树。
- 刷新 Outbox 和日志。
- 关闭数据库。
- 返回 shutdown complete 后退出。

超时后 Electron 可以强制终止，但下次启动必须执行异常退出恢复。

## 14. 日志与诊断

- 后端日志写应用日志目录。
- Renderer 不能读取任意日志路径，只通过诊断 API 获取脱敏摘要。
- 提供“导出诊断包”，默认排除项目源码、聊天全文、API Key 和凭据。
- 用户明确选择后才附加指定日志或项目信息。

## 15. Windows-first 边界

MVP 正式支持 Windows 10/11。代码保留：

- Path/Process/SecretStore 接口。
- 不在领域层写 Windows 专用代码。
- 不承诺第一版 macOS 签名、Keychain 和 Linux 包。

## 16. 开发模式

开发时允许：

```text
Electron/Vite Dev Server
独立 uv run backend
```

仍使用动态端口、认证和同样 API，不为开发模式关闭安全边界。

## 17. 验收标准

- 用户无需安装 Python 即可启动后端。
- Renderer 不能直接访问系统能力和 API Key。
- 后端只监听 loopback 并要求 token。
- 端口不写死。
- Electron 退出后无遗留 Worker/Tool 进程。
- 升级前数据库自动备份。
- Direct Workspace 不因卸载软件被删除。
