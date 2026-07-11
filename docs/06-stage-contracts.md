# 五阶段契约

## 1. 目的

阶段契约（`Stage Contract`）是五阶段工作流的机器可执行边界。它规定每一层能接收什么、能读取和写入什么、必须产生什么、使用哪些默认能力、如何检查质量以及何时允许交接。

角色卡描述模型应该如何工作；阶段契约决定后端实际上允许什么。提示词不能覆盖阶段契约。

## 2. 核心对象

### ProjectWorkspace

完整项目工作区，包括前端、后端、测试、配置、规格和部署文件。项目结构不写死为固定目录。

### ProjectManifest

描述完整项目结构和可验证命令：

```text
ProjectManifest
├─ schema_version
├─ project_type
├─ components
├─ entrypoints
├─ source_roots
├─ test_roots
├─ dependency_files
├─ build_commands
├─ test_commands
├─ lint_commands
├─ runtime_commands
├─ environment_files
├─ generated_paths
└─ protected_paths
```

MVP 的契约保持项目类型通用，端到端验收重点覆盖 Web 全栈项目。

### StageDeliverable

某个阶段对完整项目作出的正式贡献，包括文件集合、文档、结果和证据。

### ProjectCheckpoint

阶段交接时锁定的完整项目版本。检查点使用内容寻址增量快照，记录 Git HEAD、文件清单、Hash 和工作区模式，不在用户当前 Git 分支自动创建普通 commit。

## 3. 通用 StageContract 结构

```text
StageContract
├─ contract_id
├─ stage
├─ version
├─ role_card_version
├─ predecessor
├─ successor
├─ required_handoff_type
├─ allowed_inputs
├─ required_outputs
├─ readable_paths
├─ writable_paths
├─ immutable_paths
├─ default_capabilities
├─ requestable_capabilities
├─ permanently_denied_capabilities
├─ p2r_policy
├─ quality_checks
├─ external_change_ownership
└─ completion_requirements
```

契约版本在工作流创建时固定。软件升级不能静默改变正在运行的阶段契约。

## 4. 项目预检契约

新工作流开始前必须执行 `Project Preflight Gate`。

### 必须检查

- 工作区存在且位于允许路径。
- Managed/Direct Workspace 配置有效。
- `.agent/project.json` 和 ProjectManifest 可读取或可创建。
- 项目关键入口和依赖文件不存在明显损坏。
- 已声明的构建命令执行成功。
- 已存在的测试命令执行成功。
- 已声明的强制类型检查或 lint 命令执行成功。
- 不存在未解决的 `external_conflict`。
- 不存在路径逃逸、敏感目录映射和非法符号链接。

### 没有测试体系

已有项目没有测试命令时允许进入 MVP 工作流，但必须在 Planner/Designer 交接中记录，并由 Builder 把建立必要测试列为强制任务。

### 失败行为

任一已有强制检查失败时进入 `project_preflight_failed`，拒绝启动正式工作流。预检只报告证据，不让正式 Agent 顺手修复原本损坏的项目。

## 5. 通用阶段生命周期

```text
LOCKED
→ READY
→ DISCUSSING
→ PRODUCING
→ P2R_REVIEWING
→ QUALITY_CHECKING
→ WAITING_APPROVAL / HANDOFF_READY
→ COMPLETED
```

异常状态：

```text
WARNING_BLOCKED
NEEDS_FIX
EXTERNAL_CONFLICT
INTERRUPTED
FAILED
ABANDONED
```

只有获得合法上游 HandoffPacket 的下一聊天室才能从 `LOCKED` 进入 `READY`。

## 6. 通用质量结果

| 结果 | `MANUAL` | `AUTONOMOUS` |
|---|---|---|
| `PASS` | 等待用户阶段审批 | 自动锁定并交接 |
| `WARNING` | 用户可批准或要求重写 | 进入 `warning_blocked` 等待用户选择 |
| `NEEDS_FIX` | 返回对应阶段处理 | 自动执行结构化返工路由 |
| `FAIL` | 停止工作流 | 停止工作流 |

`AUTONOMOUS` 的 Warning 不允许忽略继续。用户只能选择重写、进入聊天室补充要求或放弃工作流。重写次数不设固定上限，每次均保存版本和原因。

## 7. Planner Contract

### 输入

- 用户项目目标。
- Planner 聊天室消息。
- 新项目说明或已有项目结构摘要。
- Project Preflight 结果。

### 正式输出

- `specs/requirements.md` 或 `specs/requirements/**`。
- 需求编号、验收标准、范围、非目标、风险和决策记录。
- 面向 Designer 的 StageDeliverable。

### 默认可写

- Planner 规格路径。
- Planner 草稿目录。

### 默认不可写

- 业务代码、测试、设计、审查和部署正式产物。

### 可申请能力

Planner 可以为理解现有项目申请临时运行或项目内修改能力。所有合法申请都必须弹窗由用户批准，且不能替代 Builder 实现正式功能。

### Gate

- 必需章节完整。
- 核心需求编号唯一。
- 每个核心需求具有可验证验收标准。
- MVP 与非目标明确。
- 阻断性开放问题为零。
- P2R 无未处理 BLOCK。

## 8. Designer Contract

### 输入

- Planner HandoffPacket。
- 已锁定需求产物。
- Designer 聊天室消息和项目指令。

### 正式输出

- `specs/design.md`。
- `specs/api.md`。
- `specs/data-model.md`。
- `specs/build-tasks.md`。
- 可选 `specs/design/**` 分项设计。

### Gate

- 每项核心需求具有设计映射。
- 模块、数据、接口、事件、错误和安全边界明确。
- Builder 任务包含目标、依赖、文件范围和测试要求。
- 没有未经批准的需求变化。
- P2R 无未处理 BLOCK。

Designer 发现需求问题只能向 Planner 创建 ChangeRequest。

## 9. Builder Contract

### 输入

- Designer HandoffPacket。
- 已批准需求和设计。
- 构建任务、返工反馈与当前 ProjectCheckpoint。

### 正式输出

- 完整项目代码，包括适用的前端、后端、共享模块、测试、配置和迁移。
- 更新后的 ProjectManifest。
- `specs/build-report.md`。
- Builder ProjectCheckpoint。

### 默认能力

- 项目内源代码、测试和构建配置读写。
- 受控 Shell、构建、测试、lint、格式化。
- Git 状态、差异和内部检查点。

### Gate

- ProjectManifest 可解析且引用真实文件和命令。
- 声明实现文件存在。
- 所有已声明构建命令通过。
- 所有已存在或新建立测试命令通过。
- 强制静态检查通过。
- 不存在关键占位实现。
- 不存在未经批准的上游契约偏差。
- 构建报告与工具证据一致。
- P2R 无未处理 BLOCK。

Builder 发现需求或设计问题只能创建 ChangeRequest，不得修改上游产物。

## 10. Reviewer Contract

### 输入

- Builder HandoffPacket。
- Builder ProjectCheckpoint。
- 已批准需求、设计、构建报告、代码和测试。

### 正式输出

- `specs/review.md`。
- 独立工具验证证据。
- `PASS`、`NEEDS_FIX` 或 `FAIL` Verdict。
- 必要的 ChangeRequest。

### 默认权限

- 项目、产物和 Git 只读。
- 运行后端批准的构建、测试、lint、类型检查和安全扫描。
- 只写 Reviewer 产物。

Reviewer 永久不能修改需求、设计、生产代码、测试和 Builder 产物，即使用户批准能力申请也不能突破。

### Gate

- 审查范围明确。
- 核心需求具有实现和验证证据。
- 所有命令结果真实记录。
- 每个阻断问题具有严重度、证据和目标阶段。
- Verdict 与发现一致。
- P2R 无未处理 BLOCK。

只有 `PASS` 可以创建 Deployer HandoffPacket。

## 11. Deployer Contract

### 输入

- Reviewer `PASS` HandoffPacket。
- Reviewer 批准的完整项目检查点。
- 所有已批准上游产物。

### 正式输出

- `specs/deployment/**` 文档。
- Stage Contract 允许的 Dockerfile、Compose、CI、脚本、服务和代理配置草案。
- 最终部署准备 StageDeliverable。

### MVP 限制

- 不运行 Docker build。
- 不执行打包验证。
- 不连接远程系统。
- 不 push、publish 或真实部署。
- 不修改业务源代码。

### Gate

- 部署计划、环境、启动、停止、健康检查、日志、备份和回滚说明完整。
- 所有生成部署文件被正式报告引用。
- 不包含真实凭据。
- 未验证假设明确标记。
- 不存在虚假部署或验证声明。
- P2R 无未处理 BLOCK。

## 12. 外部文件变化归属

用户可以在外部编辑器修改项目文件。后端按路径归属使最早阶段及其下游失效：

| 文件变化 | 最早失效阶段 |
|---|---|
| 需求与验收文件 | Planner |
| 架构、API、数据与设计文件 | Designer |
| 源码、测试、构建与迁移 | Builder |
| 审查报告 | Reviewer |
| 部署文档与部署配置 | Deployer |

如果用户和 Agent 同时修改同一文件，进入 `external_conflict`，停止 Agent 写入并保存基线、用户版本和 Agent 版本，由用户处理。

## 13. 已完成聊天室

已完成聊天室允许只读咨询，不允许工具和正式产物修改。用户必须明确选择“重新打开阶段”才能创建新 Stage Run，并使该阶段及下游结果失效。

## 14. 验收标准

- 五个 StageContract 均可由 Pydantic Schema 表达并验证。
- 后端能够根据 Contract 计算实际读写与工具能力。
- 任一阶段不能直接修改上游正式产物。
- Formal Deliverable 必须引用 ProjectCheckpoint。
- Manual/Autonomous 的 PASS、WARNING、NEEDS_FIX、FAIL 行为符合本文。
- 外部修改可以正确映射到最早失效阶段。
