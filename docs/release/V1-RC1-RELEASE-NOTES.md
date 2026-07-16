# 星协 1.0.0-rc.1 发布候选说明

> 发布状态：Release Candidate，尚不是正式 `1.0.0`
> 目标平台：Windows 桌面端
> 分发方式：未签名安装器
> 候选产物来源：[GitHub Actions Run 29492919058](https://github.com/yx666814/AgentProgram/actions/runs/29492919058)

## 1. 版本定位

星协是 Windows-first、单用户、本地运行的软件交付编排平台。它围绕固定的五阶段流程组织本地项目：

```text
Planner -> Designer -> Builder -> Reviewer -> Deployer
```

`1.0.0-rc.1` 用于发布前验收。它已经通过自动化质量门禁和安装后 Fake Model 全产品 E2E，但真实 OpenAI Compatible/Anthropic 服务与物理桌面环境仍需人工验收，因此不得描述为正式 V1。

## 2. 本候选版已经覆盖

- 本地项目创建、打开、关闭和恢复，以及 Managed Workspace 与 Direct Workspace。
- 项目预检、路径边界、检查点、外部文件变化和冲突处理。
- Planner、Designer、Builder、Reviewer、Deployer 五阶段固定工作流。
- Manual 与 Autonomous 审批、Quality Gate、ArtifactVersion、HandoffPacket、返工和 ChangeRequest。
- Agent 运行、流式状态、取消、重试、受控工具、CapabilityRequest 和工具审计。
- 应用、Worker 和工具进程异常后的恢复，以及事件重放和检查点恢复。
- OpenAI Compatible 与 Anthropic 模型配置能力；真实服务人工验收仍在进行。
- Electron 桌面壳、Sidecar 动态端口、本地 SecretStore 桥接、诊断导出和 Windows NSIS 安装器。

安装后产品 E2E 已验证五个阶段、6 次正式 Agent Run、6 次 Quality Gate、5 个锁定产物版本、5 次交接、Manual/Autonomous、Warning 返工、Capability 允许/拒绝/越权阻断、冲突解决、检查点恢复、崩溃恢复、重启事件重放、卸载重装恢复和 Direct Workspace 保留。

## 3. 下载文件身份

以下信息只对应 GitHub Actions Run `29492919058` 中的 `windows-product-evidence` artifact：

| 文件 | 字节 | SHA-256 | Authenticode |
| --- | ---: | --- | --- |
| `XingXie-1.0.0-rc.1-Setup.exe` | 121318449 | `D10CD232BCE9EDFAE4F22934C2EF1772D6EA9A775AC40B2ED20A585ADEC0DE66` | `NotSigned` |

安装器构建不是字节级可复现的；不同 CI Run 或本地重建的文件可能具有不同大小和哈希。只能使用与实际下载文件一起发布的校验值，不能用其他构建的哈希替代。

PowerShell 校验命令：

```powershell
Get-FileHash .\XingXie-1.0.0-rc.1-Setup.exe -Algorithm SHA256
```

输出必须与上表完全一致。若不一致，请不要运行该文件。

## 4. 未签名安装提示

本候选版暂不购买或配置 Authenticode 证书。Windows SmartScreen 可能显示“未知发布者”，杀毒软件也可能产生信誉型告警。

仅在以下条件全部满足时继续安装：

1. 安装器来自项目提供的可信下载位置。
2. 文件名和字节数与本说明一致。
3. SHA-256 校验与本说明一致。
4. SmartScreen 中确认文件无异常后，选择“更多信息 → 仍要运行”。

未签名状态必须始终如实披露，不得将本候选版描述为“已验证发布者”。自签名证书也不能替代面向普通 Windows 用户的可信 Authenticode 身份。

## 5. 安装、卸载与回滚

- 安装包不依赖系统 Python。
- 安装路径可以包含中文和空格。
- 卸载程序会删除程序目录，但设计上保留应用数据和 Direct Workspace 文件。
- 重装后可读取已保留的数据；重要项目仍应在测试和升级前自行备份。
- 如需回滚，先退出星协并备份应用数据和项目目录，再卸载 RC，安装此前已验证的版本。不要在没有备份的情况下依赖跨版本数据兼容性。

## 6. 当前已知限制和发布前待验收项

- 安装器、主程序和 Sidecar 未进行 Authenticode 签名。
- OpenAI Compatible 真实服务的连接、流式、取消、重试、错误和五阶段流程尚待人工验收。
- Anthropic 真实服务的连接、流式、取消、重试、错误和五阶段流程尚待人工验收。
- API Key 不进入数据库、日志、事件、诊断包或截图的真实服务人工复核尚待完成。
- 100%、125%、150%、200% DPI，1080p/2K/4K 和多显示器混合缩放尚待物理桌面验收。
- RC 版本可能仍包含尚未发现的问题，不建议替代正式版本用于不可回滚的生产工作。

## 7. V1 不包含的功能

- 云端托管、多用户、团队和组织权限。
- 任意 DAG 工作流编辑器。
- Agent 自动创建角色、插件市场和多机器并行执行。
- 真实生产环境自动部署。
- 应用商店发布、复杂计费和产品内 Git 操作。

## 8. 自动化证据

GitHub Actions Run `29492919058` 的 `backend`、`frontend`、`windows-product` 均为 `success`。Windows job 已完成安装器构建、安装后产品 E2E 和 artifact 上传。

正式 `1.0.0`、`v1.0.0` Tag、GitHub Release 或公开安装器上传均不在本说明授权范围内，必须在剩余人工验收完成后另行确认。
