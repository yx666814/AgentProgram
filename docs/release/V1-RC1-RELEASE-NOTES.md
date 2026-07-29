# 星协 1.0.0-rc.1 发布候选说明

> 发布状态：Release Candidate，尚不是正式 `1.0.0`
> 目标平台：Windows 桌面端
> 分发方式：未签名安装器
> 当前身份：2026-07-29 本地验收候选，尚未公开上传

## 1. 版本定位

星协是 Windows-first、单用户、本地运行的软件交付编排平台。它围绕固定的五阶段流程组织本地项目：

```text
Planner -> Designer -> Builder -> Reviewer -> Deployer
```

`1.0.0-rc.1` 用于正式发布前验收。自动编排层和安装后 Fake Model 全产品闭环已经完成；真实 OpenAI Compatible/Anthropic 服务、物理桌面和独立审查仍需人工验收，因此不得描述为正式 V1。

## 2. 本候选版已经覆盖

- 本地项目创建、打开、关闭和恢复，以及 Managed Workspace 与 Direct Workspace。
- 项目预检、路径边界、检查点、外部文件变化和冲突处理。
- Planner、Designer、Builder、Reviewer、Deployer 五阶段固定工作流。
- Manual 与 Autonomous、Quality Gate、ArtifactVersion、Approval/Policy、Checkpoint、Handoff 和 ChangeRequest。
- 用户从 Stage 页面发起的高层自动编排，不需要手工操作 Task、Tool、Artifact 或 Gate 底层命令。
- 一主双校正式 AgentRun、结构化 `StageExecutionPlan v1`、受控 ToolCall、正式产物和阶段交接。
- Agent 运行、NDJSON 流式状态、取消、失败重跑和应用重启恢复。
- Tool Catalog、StageContract、PathGuard、CapabilityRequest、当前文件 Hash 与 Manifest 命令索引的逐层校验。
- Electron 桌面壳、Sidecar 动态端口、本地 SecretStore 桥接、诊断导出和 Windows NSIS 安装器。
- 安装版启动页、侧栏和 Windows 快捷方式统一使用透明圆角品牌图标。

最终安装版产品 E2E 已从用户可见 UI 验证：

```text
Planner Manual + UI 审批
Designer Autonomous 自动交接
Builder Autonomous Warning 阻断
UI 返回讨论
Builder Manual 返工 + UI 审批
Reviewer Manual + UI 审批
Deployer Manual + UI 审批
```

报告包含 12 次正式 AgentRun、12 次 Quality Gate、10 个锁定 ArtifactVersion、10 次 Handoff、8 次人工审批、2 次自动交接，并覆盖 Capability 允许/拒绝/越权阻断、冲突解决、检查点恢复、崩溃恢复、事件重放、卸载重装恢复和 Direct Workspace 保留。

## 3. 当前本地候选文件身份

以下信息只对应 2026-07-29 完成最终安装版 product E2E 的本地文件。该文件尚未上传 GitHub Release，也没有获得公开分发授权。

| 文件 | 字节 | SHA-256 | Authenticode |
| --- | ---: | --- | --- |
| `XingXie-1.0.0-rc.1-Setup.exe` | 122294271 | `4D830304D516EA87F01332AA7C45B4D7E849652BD09DA0D5A1C81ACD58684192` | `NotSigned` |

PowerShell 校验命令：

```powershell
Get-FileHash .\XingXie-1.0.0-rc.1-Setup.exe -Algorithm SHA256
```

安装器构建不是字节级可复现的。未来 CI 或发布环境重新构建后，必须使用实际上传文件的新大小和新校验值，不能沿用本表。

## 4. 未签名安装提示

本候选版暂不购买或配置 Authenticode 证书。Windows SmartScreen 可能显示“未知发布者”，杀毒软件也可能产生信誉型告警。

仅在以下条件全部满足时继续安装：

1. 安装器来自项目提供的可信位置。
2. 文件名和字节数与同批说明一致。
3. SHA-256 与同批校验文件一致。
4. 确认 SmartScreen 展示的信息符合预期后，再决定是否选择“更多信息 → 仍要运行”。

未签名状态必须始终如实披露，不得将本候选版描述为“已验证发布者”。自签名证书不能替代面向普通 Windows 用户的可信 Authenticode 身份。

## 5. 安装、卸载与回滚

- 安装包不依赖系统 Python。
- 安装路径可以包含中文和空格。
- 卸载程序删除程序目录，但设计上保留应用数据和 Direct Workspace 文件。
- 重装后可以读取保留的数据；重要项目仍应在测试和升级前独立备份。
- 回滚前先退出星协，备份应用数据和项目目录，再卸载 RC 并安装此前验证过的版本。
- 不要在没有备份的情况下依赖跨版本数据兼容性。

## 6. 当前已知限制和发布前待验收项

- 安装器、主程序和 Sidecar 未进行 Authenticode 签名。
- OpenAI Compatible 真实服务的连接、流式、取消、错误恢复和五阶段流程尚待人工验收。
- Anthropic 真实服务的连接、流式、取消、错误恢复和五阶段流程尚待人工验收。
- API Key 不进入数据库、日志、事件、诊断包或截图的真实服务复核尚待完成。
- 100%、125%、150%、200% DPI，1080p/2K/4K 和多显示器混合缩放尚待物理桌面验收。
- 当前 PR 三个 GitHub Actions job 已全绿；独立 PR 审查仍待完成。
- RC 版本可能包含尚未发现的问题，不建议替代正式版本用于不可回滚的生产工作。

## 7. V1 不包含的功能

- 云端托管、多用户、团队和组织权限。
- 任意 DAG 工作流编辑器。
- Agent 自动创建角色、插件市场和多机器并行执行。
- 真实生产环境自动部署。
- 应用商店发布、复杂计费和产品内 Git 操作。

## 8. 自动化证据

当前本地门禁结果：

- 69 REST operations / 41 events / 5 StageContracts / 23 tools；
- Ruff format/check 通过；
- Mypy strict：144 个源文件通过；
- Pytest：733 passed / 12 skipped；
- Vitest：39 个文件、75 个测试通过；
- Playwright：58 passed；
- 最终安装器 product E2E：1 passed。

GitHub Actions Run [`30445226287`](https://github.com/yx666814/AgentProgram/actions/runs/30445226287) 在提交 `db0cc2a` 上完成，`backend`、`frontend`、`windows-product` 均为 `success`；Windows job 的安装器构建、安装版 product E2E（`1 passed`）和证据摘要成功。仓库历史 artifact 已占满配额，因此本 Run 没有生成可下载 artifact；本地候选安装器身份仍以上文和同批校验文件为准。

历史 Run `29492919058` 只证明合并前阶段 9 基线，不包含本轮自动编排实现。

正式 `1.0.0`、`v1.0.0` Tag、GitHub Release 或公开安装器上传均不在当前授权范围内，必须在剩余人工验收完成后另行确认。
