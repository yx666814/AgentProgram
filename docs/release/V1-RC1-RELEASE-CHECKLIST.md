# 星协 V1.0.0-rc.1 发布候选检查表

> 建立日期：2026-07-16
> 发布分支：`codex/v1-release-prep`
> 基线：`c851db0918806f02f1156e291bbbf7aa06671eba`
> 状态：发布候选版本已锁定；尚未签名、尚未完成真实模型与物理桌面人工验收，不是正式 V1 发布。

## 1. 版本锁定

| 产物 | 版本 |
| --- | --- |
| Electron/npm 应用 | `1.0.0-rc.1` |
| Python 后端包（PEP 440） | `1.0.0rc1` |
| RC 安装器 | `XingXie-1.0.0-rc.1-Setup.exe` |
| 正式目标版本 | `1.0.0` |
| 正式目标 Tag | `v1.0.0` |

`1.0.0rc1` 与 `1.0.0-rc.1` 表示同一个发布候选版本；差异只来自 Python PEP 440 与 npm SemVer 的格式要求。

## 2. 自动化门禁

- [x] 后端版本源和 `uv.lock` 已更新。
- [x] 前端版本源和 `package-lock.json` 已更新。
- [x] CI 安装器 artifact 路径已更新。
- [x] 安装版产品 E2E 安装器文件名已更新。
- [x] 冻结契约已重新导出，仍为 68 REST / 41 events / 5 StageContracts / 23 tools。
- [x] Ruff format/check 通过。
- [x] Mypy 138 个源文件通过。
- [x] Pytest 732 passed / 12 skipped。
- [x] Vitest 39 个文件 / 70 个测试通过。
- [x] Playwright 58 个测试通过。
- [x] RC1 NSIS 安装器构建通过。
- [x] RC1 安装版 product E2E 在普通 TEMP 与 Windows 8.3 短路径 TEMP 下通过。
- [x] 发布准备 PR 的 backend/frontend/windows-product CI 全绿。

CI 证据：GitHub Actions Run [`29491244086`](https://github.com/yx666814/AgentProgram/actions/runs/29491244086) 于 2026-07-16 完成，`backend`、`frontend`、`windows-product` 均为 `success`；其中 Windows 安装器构建、安装后产品 E2E 与 artifact 上传全部通过。

## 3. RC1 本地产物证据

| 产物 | 字节 | SHA-256 | 签名 |
| --- | ---: | --- | --- |
| `frontend/release/XingXie-1.0.0-rc.1-Setup.exe` | 122297237 | `99379C6C0A2289E3285C9C2132932BF4AA8E49B2E9E8462D78743A7B082628A9` | `NotSigned` |
| `frontend/release/win-unpacked/星协.exe` | 225486336 | `50F20B0B2717971652574CF50BED01566BD10DE16CEBC9E1C7DD7851ED66E0C0` | `NotSigned` |
| `frontend/release/win-unpacked/resources/app.asar` | 13851496 | `14FDB8C9114BF9B0FBB76D1E17C1348A1AECB8D987CD0515EF88976A906CC551` | 不适用 |
| `agent-platform-desktop-sidecar.exe` | 13019335 | `6EDC761270755761B8D3646A1DD8F74A9EE4B547C944C1CB71DC01B116A38CCC` | `NotSigned` |

冻结 `frontend/contracts/SHA256SUMS.json` 的 SHA-256 为 `86C8868D2AF6D6682D47651210A9AF853AAFEAEE4CDDD1B3CD07EC0FB8F89C30`。

## 4. 用户必须完成的发布验收

### Authenticode

- [ ] 选择 PFX 或云端签名方案。
- [ ] 在 GitHub Actions Secrets 中配置签名凭据，不向聊天或仓库提供明文。
- [ ] 安装器、`星协.exe`、Sidecar 和卸载程序签名状态均为 `Valid`。
- [ ] 可信时间戳验证通过。

### 真实模型

- [ ] OpenAI Compatible 连接、流式、取消、重试、错误和五阶段人工验收。
- [ ] Anthropic 连接、流式、取消、重试、错误和五阶段人工验收。
- [ ] 确认 API Key 不进入数据库、日志、事件、诊断包或截图。

### 物理桌面

- [ ] 100%、125%、150%、200% DPI。
- [ ] 1080p、2K、4K（硬件可用时）。
- [ ] 多显示器与不同缩放比例切换。
- [ ] 浅色/深色、键盘焦点、系统文件对话框。
- [ ] 中文空格路径安装、卸载、重装和无残留进程。

### 独立审查

- [ ] 发布准备 PR 由独立审查者确认。
- [ ] 零已知 P0/P1。
- [ ] Release Notes、已知问题和回滚步骤与真实实现一致。

## 5. 正式发布边界

只有本表全部完成，才能把版本从 `1.0.0-rc.1` 更新为 `1.0.0`。创建 `v1.0.0` Tag、GitHub Release 或上传公开安装器前，必须取得用户明确授权。
