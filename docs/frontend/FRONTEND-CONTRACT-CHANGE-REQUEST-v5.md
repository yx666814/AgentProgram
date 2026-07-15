# 星协 V1 前端契约 Change Request v5

> 日期：2026-07-15
> 状态：阶段 8 DesktopPort v2 受控变更记录
> 仓库基线：`origin/master` at `a6a025e`
> 前一版本：`FRONTEND-CONTRACT-CHANGE-REQUEST-v4.md`（保留，不覆盖）
> 适用范围：Electron Main/Preload、SecretStore Bridge 与 S08 ModelProfile 凭证写入

## 1. 变更原因

阶段 7 的 `DesktopPort v1` 故意不提供 SecretStore 能力，因此 S08 只能让用户手工填写 `credential_ref` 和 `masked_hint`，不能建立真实模型凭证。`PROJECT-PLAN.md` 阶段 8 明确要求接入 SecretStore Bridge；`STAGE-8-DESKTOP-HANDOFF-v1.md` 同时规定，启用凭证保存前必须先完成版本化 DesktopPort 变更，不能静默扩权。

本版本只增加“密钥一次写入”和“本地引用删除”，不增加密钥读取、枚举、导出、回显或任意文件访问。

## 2. DesktopPort v2 新增能力

```ts
interface StoredSecretReference {
  credentialRef: string;
  maskedHint: string;
}

interface DesktopPort {
  secrets: {
    store(input: { value: string; label: string }): Promise<StoredSecretReference>;
    delete(credentialRef: string): Promise<void>;
  };
}
```

不增加以下方法：

- `get`、`read`、`resolve`、`list` 或 `export`；
- 任意 SecretStore 原始 IPC；
- Renderer 可见的 Secret Bridge 地址、Token 或加密文件路径；
- 后端不存在的 `ModelProfileTest` operation。

## 3. Windows SecretStore 实现

- Electron Main 使用 `safeStorage`，Windows 上由 DPAPI 提供 OS 账户边界加密；
- 加密记录写入应用数据目录 `secrets/credentials.v1.json`；文件只包含版本、随机 `credential_ref`、标签、更新时间和 DPAPI 密文；
- `credential_ref` 固定为 `credential.xingxie.<32 hex>`，符合后端现有 Schema；
- `masked_hint` 在 Main 内生成，Renderer 不自行截取或保存明文；
- 写入使用临时文件和替换，失败时不提交半写记录；
- 删除只接受星协拥有的引用，且是幂等操作。

## 4. Backend Secret Bridge

Electron Main 在 `127.0.0.1` 动态端口创建独立 Secret Bridge：

- Bridge Token 使用密码学安全随机源；
- Bridge Origin 与 Token 只通过 Sidecar stdin 启动帧传入后端；
- Renderer、普通 REST、WebSocket、事件、数据库和诊断页均不取得 Bridge 信息；
- 后端 `DesktopHttpSecretStore` 只允许按合法 `credential_ref` 调用 `/v1/resolve`；
- Bridge 只监听 IPv4 loopback，要求精确 Bearer Token，响应带 `Cache-Control: no-store`；
- 后端只在模型调用前短时解析密钥，ModelProfile 数据库记录仍只有引用和脱敏提示；
- Bridge、后端和 Electron 退出后临时 Token 失效。

## 5. S08 交互变化

创建 ModelProfile：

1. 用户输入名称、Provider、Model、Base URL 和 API Key；
2. Renderer 通过 `DesktopPort.secrets.store` 一次传给 Preload/Main；
3. Main 返回新 `credential_ref` 和 `masked_hint`；
4. Renderer 只把这两个值提交给真实 `POST /api/v1/model-profiles`；
5. 后端创建失败时删除刚写入的加密记录。

更新 ModelProfile：

- API Key 留空时保留原 `credential_ref`；
- 输入新值时先创建新引用，后端更新成功后删除旧的本地引用；
- 后端更新失败时删除新引用并保留旧引用；
- 后端已经成功但页面重新读取失败时，不删除新引用，避免生成引用失效的 Profile。

S08 仍然保持：

- `ModelProfileTest` 按钮禁用，因为后端没有对应 operation；
- 全局 Settings 保存禁用，因为后端没有 SettingsQuery/Command；
- ModelProfile 全局事件的可重放缺口沿用 v4，不伪称已收到持久事件。

## 6. 安全与测试门禁

- Preload 只能调用固定 Secret IPC channel，不暴露 `ipcRenderer`；
- `DesktopPort.secrets` 静态契约测试确认不存在读取/枚举方法；
- 加密存储测试确认文件不包含输入明文；
- Secret Bridge 测试确认未认证请求无法解析；
- 后端 HTTP SecretStore 测试确认非法引用、非法响应和不可用 Bridge 返回 `None`；
- Electron 冒烟测试完成 Renderer 写入、Main 加密、Bridge 解析和删除，退出后文件记录为空；
- 生产 bundle、日志、数据库、事件和诊断包继续执行密钥泄漏扫描。

## 7. 不变约束

- OpenAPI operation 数量和业务 Schema 不因本变更增加前端别名；
- API Key 不进入 ModelProfile payload、SQLite、EventEnvelope、普通日志或本地视图偏好；
- Renderer 不能调用 Secret Bridge，也不能读取 DPAPI 密文；
- 不因 SecretStore 已接入而启用后端不存在的模型测试、Provider 能力探测或设置保存成功状态；
- v1-v4 文档和阶段 7 验收记录全部保留。

## 8. 版本历史

| 版本 | 日期 | 变更 |
| --- | --- | --- |
| v1 | 2026-07-15 | 记录阶段 5 静态契约导出、实际 operationId、全局事件游标与冻结拼写。 |
| v2 | 2026-07-15 | 保留 v1；补充消息、模型流、StageContract 边界和 Rolling Summary 缺口。 |
| v3 | 2026-07-15 | 保留 v1-v2；补充 FileConflict、三方 Hash 和 restore-plan 边界。 |
| v4 | 2026-07-15 | 保留 v1-v3；补充设置/诊断实际能力、全局事件投递和 SecretStore 缺口。 |
| v5 | 2026-07-15 | 保留 v1-v4；批准 DesktopPort v2 只写 SecretStore、Windows DPAPI、后端本机解析桥和 S08 凭证事务。 |
