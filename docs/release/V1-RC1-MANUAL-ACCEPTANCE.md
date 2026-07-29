# 星协 1.0.0-rc.1 人工验收操作手册

> 适用版本：`1.0.0-rc.1`
> 日期：2026-07-29
> 范围：真实模型、物理 Windows 桌面、未签名安装器和发布前复核
> 原则：只在可丢弃的测试项目中验收，不使用生产密钥、生产目录或不可回滚数据

## 1. 验收记录

每次验收先记录：

| 项目 | 记录值 |
| --- | --- |
| Windows 版本 |  |
| 机器型号 |  |
| 显示器与分辨率 |  |
| 缩放比例 |  |
| 安装器 SHA-256 |  |
| OpenAI Compatible 服务/模型 |  |
| Anthropic 服务/模型 |  |
| 开始时间 |  |
| 验收人 |  |

不要在记录、截图或缺陷报告中填写 API Key、Authorization Header、完整模型响应中的敏感项目内容或用户目录下的秘密文件。

## 2. 安装器身份与安装

1. 将 `XingXie-1.0.0-rc.1-Setup.exe` 和同批 `V1-RC1-LOCAL-SHA256SUMS.txt` 放在同一目录。
2. 在 PowerShell 中运行：

```powershell
Get-FileHash .\XingXie-1.0.0-rc.1-Setup.exe -Algorithm SHA256
Get-AuthenticodeSignature .\XingXie-1.0.0-rc.1-Setup.exe | Select-Object Status
```

3. 当前本地候选的预期值是：

```text
SHA-256: FF227F57B4D22F0D6388D339519D8A5922E5C04A206DFD7777EE70AFB7BB7585
Status: NotSigned
```

4. 若哈希不同，停止安装；若安装器来自后续 CI 或发布构建，应使用该构建同批提供的新校验文件，不能使用本手册中的旧值。
5. 双击安装器。SmartScreen 显示“未知发布者”是当前未签名决策的已知结果；确认来源和哈希后再决定是否继续。
6. 安装到一个包含中文和空格的目录，例如 `D:\应用验收\星协 RC1`。
7. 启动后确认启动页显示后端健康、就绪，没有无限加载或残留错误提示。

通过标准：安装成功；启动后 Sidecar 就绪；任务管理器中不存在重复的星协或 Sidecar 进程。

## 3. 创建真实模型配置

正式编排要求当前 Room 的 Primary、Reviewer A、Reviewer B 使用三个不同且已启用的 Profile。三个 Profile 可以使用同一服务和同一模型，但 Profile ID 必须不同。

### 3.1 OpenAI Compatible

1. 打开“设置”。
2. 在“创建模型配置”中依次创建三个配置，例如 `OpenAI Primary`、`OpenAI Reviewer A`、`OpenAI Reviewer B`。
3. Provider 选择 `OpenAI Compatible`。
4. “模型 ID”填写服务实际支持的模型 ID。
5. “Base URL”填写 API 根路径，通常以 `/v1` 结尾；程序会在其后请求 `/chat/completions`。
6. “API Key”只在密码框输入，不粘贴到聊天、截图、缺陷描述或项目文件。
7. 点击“创建模型配置”，确认列表只显示 `credential_ref` 和脱敏提示，不回显完整 Key。

### 3.2 Anthropic

重复上述步骤创建三个 Anthropic Profile：

- Provider：`Anthropic`；
- 官方 Base URL：`https://api.anthropic.com/v1`；
- 程序会在其后请求 `/messages`；
- 模型 ID 必须是账户实际可用的 Anthropic 模型。

当前版本没有独立“测试连接”接口或按钮。真实连接必须通过 Stage 页的讨论运行或正式运行验证，不把“配置保存成功”当成“模型连接成功”。

## 4. 准备可丢弃的小项目

1. 新建包含中文和空格的目录，例如 `D:\星协验收\示例 Node 项目`。
2. 使用一个可以独立运行和测试的小项目副本。不要选择正在开发的真实仓库。
3. 项目至少应有明确的源码目录、测试命令和构建或启动命令；预检页显示的 Manifest 才是后端实际允许的路径和命令范围。
4. 在“项目”页点击“选择目录”，创建 Direct Workspace 或 Managed Workspace 测试项目。
5. 填写明确目标，例如“实现一个带输入校验的本地待办事项 CLI，并生成测试、构建报告和部署说明”。
6. 点击“创建并预检”。只有 PASS，或用户明确确认的 WARNING，才继续“创建并开始工作流”。

通过标准：项目主页显示五个固定阶段；Planner 为当前阶段；其余阶段按后端状态锁定。

## 5. OpenAI Compatible 五阶段验收

### 5.1 Planner：Manual

1. 在项目主页确认执行模式为 `Manual`；如不是，点击顶部执行模式分段控件中的 `Manual`。
2. 进入 Planner。
3. 保持“正式编排（一主双校）”选中。
4. 在当前阶段分配中选择三个不同的 OpenAI Compatible Profile，点击“保存当前阶段分配”。
5. 在“运行指令”填写本阶段要完成的真实需求分析任务。
6. 点击“运行并完成本阶段”。
7. 观察一主双校 Agent 帧、Task 和 ToolCall 状态；不得出现前端本地伪造的完成。
8. StageRun 进入 `waiting_approval` 后打开“审批与能力”，检查 Gate 问题，填写决定原因并点击“批准”或“要求重写”。
9. 批准后确认 Planner 完成，Designer 解锁，ArtifactVersion、Checkpoint 和 Handoff 可查询。

### 5.2 Designer 和 Builder：Autonomous

1. 回到项目主页，点击 `Autonomous`；确认选中态来自刷新后的工作流状态。
2. 进入 Designer，为当前 Room 保存三个不同的 OpenAI Compatible Profile。
3. 正式运行 Designer。PASS 应自动创建 Handoff 并解锁 Builder，不出现人工审批按钮。
4. 进入 Builder，保存三个 Profile 并正式运行。
5. 若 Gate 为 WARNING，工作流必须进入 `warning_blocked`，不能自动批准。
6. 点击“返回讨论”，确认 StageRun 变为 `discussing`、工作流恢复为 `running`。

### 5.3 Builder 返工、Reviewer 和 Deployer：Manual

1. 回到项目主页切换为 `Manual`。
2. 重新进入 Builder，使用后端给出的 ChangeRequest/Warning 信息填写返工指令。
3. 正式运行并在“审批与能力”中完成 Gate 决定。
4. 对 Reviewer 和 Deployer 分别保存三个 Profile、正式运行并完成审批。
5. 最终确认工作流状态为 `completed`。
6. 在“产出与交接”核对五阶段产物版本、Gate、Checkpoint 和 Handoff 历史。
7. 在“事件与诊断”输入 Workflow ID，点击“读取审计”，核对 AgentRun、ToolCall、Gate、审批和交接记录。
8. 在项目目录外部运行项目自带测试和启动命令，确认生成代码确实可测试、可加载或可运行。

通过标准：普通用户只通过正式 UI 完成双模式五阶段链；没有手工调用 REST、修改 SQLite 或使用测试驱动命令。

## 6. Anthropic 五阶段验收

新建第二个可丢弃项目，重复第 5 节，但每个 Room 使用三个不同的 Anthropic Profile。不要在已完成的 OpenAI 项目中替换历史模型分配来缩短验收。

重点检查：

- `/messages` 流式响应可以持续显示；
- Primary、Reviewer A、Reviewer B 和 P2R 共四次模型调用都有终态；
- Manual/Autonomous 语义与 Provider 无关；
- 模型错误不会生成虚假的 Artifact、Gate 或 Handoff；
- 最终产物仍通过本地测试和启动验证。

## 7. 取消、错误与恢复

这些场景使用第三个可丢弃项目，避免破坏前两条完成证据。

1. 讨论运行开始流式输出后点击“取消运行”，确认 AgentRun 为 `cancelled`，界面可继续操作。
2. 临时创建一个 Base URL 错误的 Profile，发起讨论运行，确认显示后端错误且没有虚假完成；随后编辑为正确 URL，API Key 留空以保留现有凭证，再次运行。
3. 正式运行过程中关闭整个星协应用，重新启动。
4. 启动页出现待恢复记录时点击“继续恢复”。
5. 确认运行中的 Task、AgentRun、ToolCall 被记录为中断，StageRun 回到可继续讨论状态，历史审计仍保留。
6. 使用新指令重新运行，不复用已结束请求的本地成功状态。

## 8. 密钥与诊断复核

1. 设置页不得显示完整 API Key；编辑现有 Profile 时 API Key 留空应保留现有凭证。
2. 打开“事件与诊断”，点击“导出诊断包”。
3. 检查诊断包只包含版本、契约 Hash、健康/就绪、恢复记录、Sidecar 状态和脱敏日志摘要。
4. 检查诊断包不包含源码、完整聊天、模型正文、Tool 参数/结果正文、Authorization Header 或完整 API Key。
5. `%APPDATA%\星协\secrets\credentials.v1.json` 可以存在，但其中凭证必须是 Windows DPAPI 加密数据，不得出现可读明文 Key。
6. 截图只截应用状态和错误码；截图前遮盖用户路径、模型内容和脱敏提示中不希望公开的部分。

发现任何明文 Key 后立即停止分发、吊销该 Key、保留不含秘密的最小复现信息，并按 P0 处理。

## 9. 物理桌面矩阵

每一行至少检查启动页、项目主页、一个 Stage 页、审批页和设置页：

| 场景 | 浅色 | 深色 | 键盘焦点 | 无遮挡/溢出 | 结果 |
| --- | --- | --- | --- | --- | --- |
| 1080p / 100% |  |  |  |  |  |
| 1080p / 125% |  |  |  |  |  |
| 2K / 150% |  |  |  |  |  |
| 4K / 200% |  |  |  |  |  |
| 多显示器相同缩放 |  |  |  |  |  |
| 多显示器混合缩放 |  |  |  |  |  |

额外操作：

1. 仅用键盘访问主导航、Manual/Autonomous、模型槽位、运行、取消和审批按钮。
2. 在浅色/深色之间切换，确认焦点、选中态、Warning 和错误状态可辨认。
3. 将窗口在不同缩放比例的显示器之间移动，确认文字不重叠、按钮不裁切、布局不跳变。
4. 打开系统目录选择和诊断保存对话框，确认主窗口不会冻结或丢失焦点。
5. 最小化、恢复、关闭、重新启动，确认没有残留 Sidecar 或工具进程。

## 10. 卸载、重装与结论

1. 记录一个已完成 Workflow ID 和 Direct Workspace 文件 Hash。
2. 从 Windows 卸载星协，确认安装目录删除、Direct Workspace 保留、没有残留进程。
3. 重装同一个已校验安装器。
4. 确认应用数据仍可读取，已完成工作流仍为 `completed`，Direct Workspace 文件 Hash 未改变。
5. 将结果写回 `V1-RC1-RELEASE-CHECKLIST.md`；缺陷按 P0/P1/P2 分类，不以口头“基本可用”替代证据。

只有真实模型、物理桌面、独立审查和实际分发文件哈希复核全部完成，才申请创建 Tag、GitHub Release 或公开上传安装器。当前 PR CI 已由 Run `30400155883` 验证通过；当前手册不授予这些发布操作权限。
