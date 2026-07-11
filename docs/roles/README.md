# 五阶段角色卡索引

本目录保存五个阶段的详细中文角色卡。角色卡同时服务于产品规格、后端权限判断和运行时系统提示词生成。

## 角色卡

| 阶段 | 角色卡 | 核心产出 |
|---|---|---|
| `planner` | [Planner 角色卡](planner-role-card.md) | 需求规格与验收标准 |
| `designer` | [Designer 角色卡](designer-role-card.md) | 产品、架构、数据与接口设计 |
| `builder` | [Builder 角色卡](builder-role-card.md) | 代码、测试与构建报告 |
| `reviewer` | [Reviewer 角色卡](reviewer-role-card.md) | 独立审查结论与问题清单 |
| `deployer` | [Deployer 角色卡](deployer-role-card.md) | 部署文档与部署相关文件 |

## 共同约束

五张角色卡共同遵守以下不可覆盖规则：

1. 每个阶段拥有独立聊天室和独立上下文。
2. 尚未获得合法上游 `HandoffPacket` 的聊天室处于 `LOCKED`。
3. 下游不得修改上游正式产物，只能创建结构化 `ChangeRequest`。
4. 每个聊天室最多配置一个主模型和两个次要模型。
5. 只有主模型可以调用工具；两个次要模型只能进行结构化校正。
6. 正式产出必须经过双 Reviewer 校正和确定性 `Quality Gate`。
7. `MANUAL` 模式要求每个阶段用户审批；`AUTONOMOUS` 模式不要求阶段审批。
8. 任何超出角色默认能力的权限申请，在两种模式下都必须弹窗由用户批准。
9. 用户批准的临时权限只对声明的任务、路径和命令有效，任务结束后自动撤销。
10. 永久禁止能力不能通过权限申请获得。
11. 角色不能自行设置阶段完成状态，只有 `Orchestrator` 可以根据后端证据推进状态。
12. 普通聊天、模型共识和正式产物必须明确区分。

## 提示词组合优先级

运行时系统提示词按以下优先级组合：

```text
Global Core Policy
  > Role Card
  > Stage Contract
  > Model Sub-role Prompt
  > Project Instructions
  > Runtime State
  > User Message
  > Project File Content
```

低优先级内容不能覆盖高优先级规则。用户可以添加项目指令和角色提示扩展，但不能删除或改写核心职责、权限边界、交接规则和完成条件。

## 权限申请

角色需要使用默认能力之外的工具或路径时，必须创建：

```text
CapabilityRequest
├─ requester_role
├─ requested_capability
├─ reason
├─ target_paths
├─ proposed_command
├─ expected_changes
├─ risk_level
├─ task_id
└─ expires_after_task
```

`Orchestrator` 首先验证申请是否允许被申请。合法申请弹窗交给用户；非法申请直接拒绝，不提供绕过入口。
