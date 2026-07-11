# 工具执行与安全边界

## 1. 目标

工具系统允许 Primary 在项目内完成文件、Git、构建和测试任务，同时确保角色职责、工作区和永久禁止规则不能被 Prompt、Worker 或 Shell 绕过。

第一版不设计插件系统。核心工具由 Python 实现，工具协议保持可扩展。

## 2. 权限计算

实际能力：

```text
角色默认能力
∩ Stage Contract
∩ Workspace Policy
∩ 当前 Stage Run 状态
∩ Model Slot Policy
∩ Tool Policy
```

Tool Policy 结果：

```text
ALLOW
REQUIRE_CAPABILITY_REQUEST
DENY
```

Reviewer A/B 直接 DENY 全部工具。

## 3. CapabilityRequest

默认能力之外但允许申请的操作生成结构化 CapabilityRequest，并在 MANUAL/AUTONOMOUS 两种模式下都弹窗由用户批准。

批准限制到：

- 当前 task_id。
- 明确 capability。
- 明确路径集合。
- 明确命令与参数。
- 明确有效期。

任务结束、取消或 Worker 重启后权限失效。

永久禁止能力不能申请，包括项目外访问、密钥读取、修改上游正式产物、修改系统安全策略和真实远程部署。

## 4. 工作区模式

### Managed Workspace

项目复制到软件管理目录。应用拥有工作副本和内部 Git/快照，最终支持导出。

### Direct Workspace

直接操作用户选择目录。启用时明确提示风险，但运行中不为默认允许操作重复弹窗。系统不污染用户分支，使用应用检查点。

两种模式都必须使用规范化项目根目录和 `.agentignore`。

## 5. 路径安全

每次路径操作：

1. 展开为绝对路径。
2. 解析 `.`、`..`、Windows drive 和 UNC。
3. 解析符号链接、junction 和 reparse point。
4. 使用大小写不敏感规则比较 Windows 路径。
5. 确认真实目标位于项目根目录。
6. 检查 Stage writable/readable patterns。
7. 检查 protected_patterns 和 `.agentignore`。

禁止通过软链接把项目内路径指向项目外。

## 6. MVP 工具目录

### 文件工具

```text
filesystem.read
filesystem.search
filesystem.list
filesystem.write
filesystem.create_directory
filesystem.move
filesystem.delete
filesystem.hash
filesystem.diff
```

写入使用临时文件、fsync 和原子 rename。覆盖前记录旧 Hash。删除前根据策略创建检查点。

### Git 工具

```text
git.status
git.diff
git.log
git.branch_info
git.hidden_checkpoint
```

MVP 不提供 git.push、远程仓库创建和发布。普通 commit 只在用户明确操作时创建。

### Shell 与验证

```text
shell.run_allowed
project.build
project.test
project.lint
project.typecheck
project.security_scan
```

优先使用 executable + argument list，不拼接整段 Shell 字符串。需要 PowerShell 语法时使用单独策略和参数转义。

## 7. Shell 策略

每次执行定义：

```text
executable
arguments
cwd
environment_policy
timeout
max_output_bytes
expected_effects
allowed_write_paths
```

禁止：

- cwd 在项目外。
- 修改注册表、服务和系统目录。
- 控制非项目进程。
- 读取 Credential Manager、SSH、浏览器和云凭据。
- 项目外递归删除或移动。
- 远程部署与发布。

环境变量采用 allowlist，移除 API Key 和无关敏感变量。模型 Provider 调用密钥不进入工具环境。

## 8. Tool Process

Shell、Git 和重型验证使用短生命周期子进程：

- 由 Main Process 创建。
- 记录 PID 和进程树。
- stdout/stderr 分开捕获。
- 支持实时有限流输出。
- 超时后终止整个进程树。
- 用户取消立即传播。
- 超大输出写入日志文件并返回引用。

## 9. 文件写入归属

Tool Supervisor 在写入前登记 planned write，File Watcher 因此可以区分 Agent 写入和外部写入。写入完成后登记实际 Hash 和 affected_files。

如果用户在同一时间修改目标文件：

- 取消或阻止 Agent 最终 rename。
- 保存 base、agent、user 三个版本。
- 创建 FileConflict。
- 进入 external_conflict。
- 等待用户选择或手动合并。

## 10. 快照与删除

重大覆盖、批量移动和删除前必须创建项目检查点或受影响文件快照。用户已批准 CapabilityRequest 也不能关闭快照保护。

Direct Workspace 永不因删除应用项目记录而自动删除用户项目文件。

## 11. 项目监控

使用 watchfiles 监控外部变化，并结合 Hash 判断真实变化。默认忽略：

```text
.git/
node_modules/
.venv/
__pycache__/
dist/
build/
.cache/
logs/
```

Stage Contract 可以把需要交付的生成目录显式纳入。

## 12. 工具审计

每次调用记录：

- 发起项目、阶段、Room、Task、Primary Profile。
- 原始参数的脱敏版本。
- 规范化参数。
- Policy Decision。
- CapabilityRequest。
- PID、开始结束时间、退出码。
- 输出引用和影响文件。
- 取消、超时和错误。

## 13. 角色默认边界

- Planner：读取项目与写需求；运行/额外修改需申请。
- Designer：读取项目与写设计；原型/运行需申请。
- Builder：默认代码、测试、构建工具；上游文件永久不可写。
- Reviewer：只读与受控验证；源码写入永久拒绝。
- Deployer：写部署文档和允许配置；第一版不运行验证和部署。

详细规则以 `docs/roles/` 为准。

## 14. 网络

模型 Provider 网络由 Model Adapter 管理，不属于 Agent 工具。MVP 不提供通用 network.request、浏览器自动化和任意下载工具。依赖安装超出项目默认策略时需要 CapabilityRequest。

## 15. 失败处理

- Policy DENY：返回结构化拒绝，不执行。
- 需要权限：创建请求并暂停当前 ToolCall。
- 工具失败：返回真实退出码和日志引用。
- Tool Process 崩溃：Task 不完成。
- 审计写入失败：不启动高风险工具。

## 16. 验收标准

- Shell 不能绕过文件和阶段权限。
- Reviewer 模型无法调用工具。
- CapabilityRequest 在所有模式下都要求用户决定。
- 项目外路径和符号链接逃逸被拒绝。
- 取消和超时清理完整进程树。
- 工具日志不包含 API Key。
- 并发文件修改不会静默覆盖。
