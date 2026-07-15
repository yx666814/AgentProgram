import contractSnapshot from "../../../contracts/capabilities.json";

import { Button } from "../../components/button";

const operations = Object.values(contractSnapshot.capabilities);
const hasSettingsQuery = operations.some(({ method, path }) => method === "GET" && path === "/api/v1/settings");
const hasSystemInfo = operations.some(
  ({ method, path }) => method === "GET" && path === "/api/v1/system/info",
);

export function SettingsPage() {
  return (
    <section className="settings-page" aria-labelledby="settings-title">
      <div className="eyebrow">本地应用设置</div>
      <h1 id="settings-title">设置</h1>
      <p>设置入口始终可见，但只呈现后端已经冻结的能力。</p>

      <div className="settings-card">
        <dl>
          <div>
            <dt>显示名称</dt>
            <dd>星协</dd>
          </div>
          <div>
            <dt>系统信息</dt>
            <dd>{hasSystemInfo ? "可通过 system/info 读取" : "接口不可用"}</dd>
          </div>
          <div>
            <dt>设置契约</dt>
            <dd>{hasSettingsQuery ? "已冻结" : "后端未提供 SettingsQuery 或设置写入接口"}</dd>
          </div>
        </dl>
        <Button
          disabled={!hasSettingsQuery}
          {...(!hasSettingsQuery ? { disabledReason: "后端未提供设置保存契约" } : {})}
        >
          保存设置
        </Button>
      </div>
    </section>
  );
}
