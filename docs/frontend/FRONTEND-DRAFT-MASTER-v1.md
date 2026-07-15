# 星协 V1 前端草案母版 v1

> 状态：已由用户确认并锁定
>
> 创建日期：2026-07-14
>
> 上游基线：`../FRONTEND-DRAFT.md`、`../PROJECT-PLAN.md`
>
> 后续版本规则：本文件锁定后保持不变；修改时新增 `FRONTEND-DRAFT-MASTER-v2.md`，不覆盖 v1。

## 1. 母版目标

本母版是正式前端开发前的最后一版完整设计基准。它冻结以下内容：

- 产品显示名称为“星协”，使用 `星协Logo/` 中的现有品牌资产。
- Windows 桌面端采用固定左侧导航和右侧圆角主工作区。
- 页面布局只参考 Codex 的区域关系，不复制 Codex 的品牌、功能、文字或具体组件。
- 采用 C 方案冷灰蓝配色，提供浅色和深色两种模式。
- 点击反馈柔和，无缩放、无弹跳，只改变背景、边框、文字对比和内阴影。
- 技术实现保持与后端 Query、Application Command、Event、Permission 和错误契约耦合。
- S00-S09 共 10 个页面模板；S04 展开五个阶段后，共 14 个用户可见主视图。

本母版不是正式前端代码，不包含可提交业务数据的原型，也不表示未实现后端能力已经可用。

## 2. 后端真实性边界

### 2.1 当前真实实现

截至 2026-07-14，后端代码中只存在以下 HTTP 接口：

| 接口 | 当前用途 | 可驱动页面 |
| --- | --- | --- |
| `GET /api/v1/health` | 后端进程存活 | S00、S09 |
| `GET /api/v1/readiness` | 数据库和迁移 Ready | S00、S09 |
| `GET /api/v1/system/info` | 后端版本、协议版本 | S00、S08、S09 |

除这三个接口外，图片中出现的业务内容属于 `PROJECT-PLAN.md` 已批准的阶段 2-5 目标契约。正式前端不得在对应契约实现前启用业务按钮。

### 2.2 控件门禁

每个业务控件必须满足以下链路后才能启用：

```text
UI 控件或导航
-> 已冻结 Query / Application Command
-> 请求参数与 Permission
-> 成功响应或持久化 Event
-> 前端读模型更新
-> 真实错误、取消、重试与恢复路径
```

缺少其中任一项时：

- 业务动作隐藏或禁用。
- 不显示假成功、假进度或假完成。
- 禁用状态显示真实原因和依赖的后端契约。
- 纯前端视图导航可以存在，但不得改变任何权威业务状态。

## 3. 品牌规范

### 3.1 名称

- 产品显示名称：星协。
- 当前内部 Python 包名：`agent_platform`，本母版不修改。
- 当前应用数据目录名：`AgentProgram`，是否迁移必须单独评审，不能仅因显示名称变化而直接修改。

### 3.2 Logo 资产

| 用途 | SVG | PNG |
| --- | --- | --- |
| 应用图标 | [xingxie-icon.svg](星协Logo/xingxie-icon.svg) | [xingxie-icon.png](星协Logo/xingxie-icon.png) |
| 横向 Logo | [xingxie-logo.svg](星协Logo/xingxie-logo.svg) | [xingxie-logo.png](星协Logo/xingxie-logo.png) |

应用壳优先使用图标加“星协”文字，不在窄侧栏中压缩横向 Logo。深色模式使用反色显示，但不得改变图形比例或重新绘制结构。

## 4. 全局布局

### 4.1 布局结构

```text
Windows 菜单栏与窗口控制
├─ 左侧固定导航
│  ├─ 星协品牌
│  ├─ 工作区导航
│  ├─ 五阶段状态
│  └─ 固定设置按钮
└─ 右侧圆角主工作区
   ├─ 页面标题与真实状态
   ├─ 页面内容
   ├─ 按需浮动上下文/证据面板
   └─ 底部契约与连接状态
```

### 4.2 Codex 布局参考边界

保留的布局特征：

- 左侧导航与右侧工作区明确分离。
- 右侧工作区拥有独立页头、边框和圆角。
- 阅读型内容限制最大宽度，避免宽屏时行长失控。
- 主要输入或当前操作保持稳定位置。
- 设置固定在左侧底部。

不复制的内容：

- ChatGPT/Codex 名称、图标、菜单和任务功能。
- Codex 的具体字号、颜色值、按钮造型和品牌紫色。
- Codex 的任务模型、插件入口、Git 功能或云端功能。

### 4.3 上下文呈现

不使用永久右侧栏。上下文采用以下方式：

- 普通页面：内联摘要或按需浮动面板。
- 审批、冲突、恢复：浮动证据面板或侧面板。
- 危险操作：原生确认对话框。
- 通知：可返回对应后端记录的弹层。

## 5. 主题与交互

### 5.1 浅色主题

| 令牌 | 色值 | 用途 |
| --- | --- | --- |
| `surface.app` | `#F6F8F9` | 主背景 |
| `surface.sidebar` | `#EAF0F3` | 左侧导航 |
| `surface.panel` | `#FFFFFF` | 主工作区和面板 |
| `text.primary` | `#253036` | 主文字 |
| `text.muted` | `#6F7F85` | 次要文字 |
| `border.default` | `#D9E2E5` | 边界 |
| `accent.default` | `#39758B` | 当前项和普通强调 |
| `warning.default` | `#B8784C` | 风险、Warning |
| `danger.default` | `#A75F54` | 停止、放弃和破坏性确认 |

### 5.2 深色主题

| 令牌 | 色值 | 用途 |
| --- | --- | --- |
| `surface.app` | `#191C1C` | 主背景 |
| `surface.sidebar` | `#252B2A` | 左侧导航 |
| `surface.panel` | `#222625` | 主工作区和面板 |
| `text.primary` | `#E4E7E3` | 主文字 |
| `text.muted` | `#A2ADAB` | 次要文字 |
| `border.default` | `#384344` | 边界 |
| `accent.default` | `#69A7B9` | 当前项和普通强调 |
| `warning.default` | `#D09A70` | 风险、Warning |
| `danger.default` | `#D18478` | 停止、放弃和破坏性确认 |

### 5.3 点击反馈

| 状态 | 规则 |
| --- | --- |
| 默认 | 低对比背景和清晰文字，不使用立体高光 |
| 悬停 | 轻微提高背景和边框对比，100-140ms |
| 按下 | 背景降低一级、边框加强、增加轻微内阴影，80-100ms |
| 聚焦 | 显示 2px 可见焦点环，不依赖颜色表达状态 |
| 禁用 | 不可点击，保留真实禁用原因，不只降低透明度 |
| 减少动态 | 遵循 Windows `prefers-reduced-motion`，去除非必要过渡 |

禁止缩放、弹跳、发光渐变、橡皮筋动画和大面积涟漪。

## 6. 设置入口规则

设置按钮在所有非启动页面的左侧底部固定出现，即使设置业务尚未实现也不能从布局中消失。

当前后端没有 `SettingsQuery`，因此 S08 必须：

- 允许进入设置页面这一纯前端导航目标。
- 显示“设置能力尚未接入”的真实空状态。
- 允许读取已实现的 `system/info`。
- 不显示可编辑模型、API Key、SecretStore、保存或测试成功状态。
- “保存设置”保持禁用，并显示依赖 `SettingsQuery`、ModelProfile 和 SecretStore 契约。

正式后端实现相关契约后，才按 S08 目标设计启用配置控件。

## 7. 页面与参考图

每张原图为 1440×900 PNG。总览图只用于快速评审，正式实现以单页原图为准。

- [浅色总览](reference-images/v1/INDEX-light.png)
- [深色总览](reference-images/v1/INDEX-dark.png)

| 页面 | 视图 | 浅色 | 深色 | 核心后端契约 |
| --- | --- | --- | --- | --- |
| S00 | 启动与恢复 | [Light](reference-images/v1/S00-startup-light.png) | [Dark](reference-images/v1/S00-startup-dark.png) | `BackendHealthQuery`、`RecoveryListQuery`、`RecoveryResumeCommand`、`RecoveryDiscardCommand` |
| S01 | 项目列表与创建 | [Light](reference-images/v1/S01-projects-light.png) | [Dark](reference-images/v1/S01-projects-dark.png) | `ProjectListQuery`、`ProjectCreateCommand`、`ProjectOpenCommand` |
| S02 | 项目预检 | [Light](reference-images/v1/S02-preflight-light.png) | [Dark](reference-images/v1/S02-preflight-dark.png) | `ProjectPreflightCommand`、`ProjectPreflightQuery`、`WorkflowStartCommand` |
| S03 | 项目主页 | [Light](reference-images/v1/S03-project-overview-light.png) | [Dark](reference-images/v1/S03-project-overview-dark.png) | `ProjectOverviewQuery`、Workflow Commands、Checkpoint/Conflict Queries |
| S04 | Planner 工作区 | [Light](reference-images/v1/S04-planner-light.png) | [Dark](reference-images/v1/S04-planner-dark.png) | Room、Message、Task、Stage Commands |
| S04 | Designer 工作区 | [Light](reference-images/v1/S04-designer-light.png) | [Dark](reference-images/v1/S04-designer-dark.png) | Room、Message、Task、Stage Commands |
| S04 | Builder 工作区 | [Light](reference-images/v1/S04-builder-light.png) | [Dark](reference-images/v1/S04-builder-dark.png) | Room、Message、Task、Stage Commands |
| S04 | Reviewer 工作区 | [Light](reference-images/v1/S04-reviewer-light.png) | [Dark](reference-images/v1/S04-reviewer-dark.png) | Room、Message、Task、Stage Commands |
| S04 | Deployer 工作区 | [Light](reference-images/v1/S04-deployer-light.png) | [Dark](reference-images/v1/S04-deployer-dark.png) | Room、Message、Task、Stage Commands |
| S05 | 正式产出、Gate 与交接 | [Light](reference-images/v1/S05-artifacts-gate-handoff-light.png) | [Dark](reference-images/v1/S05-artifacts-gate-handoff-dark.png) | Artifact、Gate、Approval、Handoff、ChangeRequest |
| S06 | 审批、能力申请与风险 | [Light](reference-images/v1/S06-approvals-capabilities-risk-light.png) | [Dark](reference-images/v1/S06-approvals-capabilities-risk-dark.png) | Approval、CapabilityRequest Queries/Commands |
| S07 | 冲突、检查点与恢复 | [Light](reference-images/v1/S07-conflicts-checkpoints-recovery-light.png) | [Dark](reference-images/v1/S07-conflicts-checkpoints-recovery-dark.png) | Conflict、Checkpoint Queries/Commands |
| S08 | 模型、权限与设置 | [Light](reference-images/v1/S08-settings-light.png) | [Dark](reference-images/v1/S08-settings-dark.png) | `SettingsQuery`、ModelProfile、SecretReference；当前仅 `system/info` 可用 |
| S09 | 事件、审计与诊断 | [Light](reference-images/v1/S09-events-audit-diagnostics-light.png) | [Dark](reference-images/v1/S09-events-audit-diagnostics-dark.png) | Event、Replay、Diagnostics Queries/Commands |

## 8. 页面状态覆盖

正式开发必须为每个页面覆盖：

- 首次加载和重新同步。
- 后端成功返回空集合。
- Bearer Session Token 失效。
- 权限拒绝和 StageContract 锁定。
- 后端、Worker、模型或 SecretStore 不可用。
- WebSocket 断线、重放、去重和版本落后。
- 命令超时、取消中、取消失败和恢复。
- 文件冲突、审批过期和对象失效。
- 完成后只读与显式 reopen。

所有状态必须包含真实错误代码、关联 ID、影响范围和后端允许的下一步。

## 9. 桌面适配

- 标准参考窗口：1440×900。
- 最小工作窗口：1280×720。
- 支持 Windows 100%、125%、150%、175% 和 200% 缩放。
- 窄窗口优先收起辅助上下文，不隐藏主操作和待处理状态。
- 文本不随视口宽度缩放字号。
- 主内容最大阅读宽度约 1040px，审计表格和差异比较允许扩展。
- 鼠标和键盘均可完成核心流程，焦点顺序服从视觉顺序。

## 10. 母版确认门禁

本版本只有在以下条件全部满足后才能作为正式前端开发输入：

1. 用户确认 14 个主视图的浅色和深色参考图。
2. 后端阶段 5 冻结 REST、WebSocket、错误、权限和 Desktop Control Contract。
3. 前后端功能矩阵中不存在无 Query/Command/Event 的业务控件。
4. 设置入口规则得到确认，且空状态不伪造配置能力。
5. 参考图、组件状态、键盘规则和窗口适配规则没有未解决冲突。
6. 正式开发只执行与 `PROJECT-PLAN.md` 完整对齐并经用户锁定的 `FRONTEND-IMPLEMENTATION-EXECUTION-v1.md` 或后续版本。

## 11. 版本历史

| 版本 | 日期 | 变更 |
| --- | --- | --- |
| v1 | 2026-07-14 | 用户锁定版。确定星协品牌、C 冷灰蓝双主题、Codex 式两列布局、固定设置与全局通知入口、14 个主视图和 28 张单页参考图；底部呈现任务、冲突、审批或同步状态；设计图不显示仅供开发使用的契约字符串。 |
