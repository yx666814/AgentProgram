import { type SyntheticEvent, useCallback, useEffect, useState } from "react";

import type {
  BackendApi,
  ModelProfile,
  ModelProfileCreateInput,
  ModelProfileUpdateInput,
  ModelProvider,
  RoomModelAssignment,
} from "../../api/backend-api";
import { useBackend } from "../../api/backend-context";
import { ApiErrorState } from "../../components/api-error-state";
import { Button } from "../../components/button";
import { useAsyncResource } from "../../components/use-async-resource";
import type { EventReadModel } from "../../events/event-reducer";

interface ProfileFormState {
  baseUrl: string;
  credentialRef: string;
  enabled: boolean;
  maskedHint: string;
  model: string;
  name: string;
  provider: ModelProvider;
}

interface PendingConfirmation {
  correlationId: string;
  eventType: "model_profile.created" | "model_profile.updated" | "room_model_assignment.updated";
}

const emptyProfileForm: ProfileFormState = {
  baseUrl: "",
  credentialRef: "",
  enabled: true,
  maskedHint: "",
  model: "",
  name: "",
  provider: "openai_compatible",
};

function providerLabel(provider: ModelProvider): string {
  return {
    anthropic: "Anthropic",
    fake: "Fake（测试）",
    openai_compatible: "OpenAI Compatible",
  }[provider];
}

function formFromProfile(profile: ModelProfile): ProfileFormState {
  return {
    baseUrl: profile.base_url,
    credentialRef: profile.credential_ref,
    enabled: profile.enabled,
    maskedHint: profile.masked_hint,
    model: profile.model,
    name: profile.name,
    provider: profile.provider,
  };
}

function profileCreateInput(form: ProfileFormState): ModelProfileCreateInput {
  return {
    base_url: form.baseUrl.trim(),
    credential_ref: form.credentialRef.trim(),
    masked_hint: form.maskedHint.trim(),
    model: form.model.trim(),
    name: form.name.trim(),
    provider: form.provider,
  };
}

function profileUpdateInput(form: ProfileFormState): ModelProfileUpdateInput {
  return { ...profileCreateInput(form), enabled: form.enabled };
}

function SettingsUnavailable() {
  return (
    <section className="settings-page" aria-labelledby="settings-title">
      <div className="eyebrow">本地应用设置</div>
      <h1 id="settings-title">设置</h1>
      <p>设置入口始终可见，但只呈现后端已经冻结的能力。</p>
      <div className="settings-card">
        <dl className="status-list">
          <div><dt>显示名称</dt><dd>星协</dd></div>
          <div><dt>系统信息</dt><dd>可通过 system/info 读取</dd></div>
          <div><dt>设置契约</dt><dd>后端未提供 SettingsQuery 或设置写入接口</dd></div>
        </dl>
        <Button disabled disabledReason="桌面后端尚未连接">保存设置</Button>
      </div>
    </section>
  );
}

function ModelProfileForm({
  busy,
  form,
  selectedProfile,
  setForm,
  onCancel,
  onSubmit,
}: {
  busy: boolean;
  form: ProfileFormState;
  selectedProfile: ModelProfile | null;
  setForm: (form: ProfileFormState) => void;
  onCancel: () => void;
  onSubmit: (event: SyntheticEvent<HTMLFormElement>) => void;
}) {
  const incomplete = [
    form.name,
    form.baseUrl,
    form.model,
    form.credentialRef,
    form.maskedHint,
  ].some((value) => value.trim().length === 0);

  return (
    <form className="model-profile-form" onSubmit={onSubmit}>
      <div className="form-grid">
        <label>配置名称<input value={form.name} onChange={(event) => { setForm({ ...form, name: event.target.value }); }} /></label>
        <label>Provider<select value={form.provider} onChange={(event) => { setForm({ ...form, provider: event.target.value as ModelProvider }); }}><option value="openai_compatible">OpenAI Compatible</option><option value="anthropic">Anthropic</option><option value="fake">Fake（测试）</option></select></label>
        <label>模型 ID<input value={form.model} onChange={(event) => { setForm({ ...form, model: event.target.value }); }} /></label>
        <label>Base URL<input placeholder="https://provider.example/v1" value={form.baseUrl} onChange={(event) => { setForm({ ...form, baseUrl: event.target.value }); }} /></label>
        <label>凭证引用<input aria-label="凭证引用" placeholder="secret:model.primary" value={form.credentialRef} onChange={(event) => { setForm({ ...form, credentialRef: event.target.value }); }} /></label>
        <label>脱敏提示<input aria-label="脱敏提示" placeholder="sk-****1234" value={form.maskedHint} onChange={(event) => { setForm({ ...form, maskedHint: event.target.value }); }} /></label>
      </div>
      {selectedProfile !== null ? <label className="inline-check"><input checked={form.enabled} type="checkbox" onChange={(event) => { setForm({ ...form, enabled: event.target.checked }); }} />启用此配置</label> : null}
      <p className="contract-note settings-contract-note">这里只提交 `credential_ref` 和已经脱敏的提示，不接收 API Key 明文。SecretStore Bridge 尚未实现。</p>
      <div className="page-actions settings-form-actions">
        {selectedProfile !== null ? <Button disabled={busy} onClick={onCancel}>取消编辑</Button> : null}
        <Button disabled={busy || incomplete} {...(incomplete ? { disabledReason: "请填写后端 ModelProfile 契约要求的全部字段" } : {})} tone="primary" type="submit">{selectedProfile === null ? "创建模型配置" : "保存模型配置"}</Button>
        <Button disabled disabledReason="后端未提供 ModelProfileTest operation">测试连接</Button>
      </div>
    </form>
  );
}

function AssignmentEditor({
  api,
  events,
  profiles,
  onPending,
}: {
  api: BackendApi;
  events: EventReadModel;
  profiles: ModelProfile[];
  onPending: (pending: PendingConfirmation | null, notice: string | null) => void;
}) {
  const [roomId, setRoomId] = useState("");
  const [assignment, setAssignment] = useState<RoomModelAssignment | null>(null);
  const [editing, setEditing] = useState(false);
  const [primary, setPrimary] = useState("");
  const [reviewerA, setReviewerA] = useState("");
  const [reviewerB, setReviewerB] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [pending, setPending] = useState<PendingConfirmation | null>(null);

  const fillAssignment = useCallback((next: RoomModelAssignment | null) => {
    setAssignment(next);
    setPrimary(next?.primary_profile_id ?? profiles.find((profile) => profile.enabled)?.id ?? "");
    setReviewerA(next?.reviewer_a_profile_id ?? "");
    setReviewerB(next?.reviewer_b_profile_id ?? "");
    setEditing(true);
  }, [profiles]);

  const loadAssignment = useCallback(async () => {
    if (!/^room_[a-z0-9]+$/.test(roomId.trim())) {
      setError(new Error("Room ID 必须符合后端 room_[a-z0-9]+ 契约"));
      return;
    }
    setBusy(true);
    setError(null);
    try {
      fillAssignment(await api.getRoomAssignment(roomId.trim()));
    } catch (loadError) {
      setError(loadError);
    } finally {
      setBusy(false);
    }
  }, [api, fillAssignment, roomId]);

  useEffect(() => {
    if (pending === null) {
      return;
    }
    const confirmed = events.recentEvents.some(
      (event) => event.event_type === pending.eventType && event.correlation_id === pending.correlationId,
    );
    if (confirmed) {
      setPending(null);
      onPending(null, `已收到 ${pending.eventType} 持久事件。`);
      void loadAssignment();
    }
  }, [events.recentEvents, loadAssignment, onPending, pending]);

  const saveAssignment = async () => {
    const values = [primary, reviewerA, reviewerB].filter(Boolean);
    if (primary.length === 0 || new Set(values).size !== values.length) {
      setError(new Error("Primary 必填，三个模型槽位必须使用不同的 Profile"));
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const receipt = await api.assignRoomModels({
        assignment,
        primaryProfileId: primary,
        reviewerAProfileId: reviewerA || null,
        reviewerBProfileId: reviewerB || null,
        roomId: roomId.trim(),
      });
      const nextPending: PendingConfirmation = {
        correlationId: receipt.correlationId,
        eventType: "room_model_assignment.updated",
      };
      setPending(nextPending);
      onPending(nextPending, "后端已返回 RoomModelAssignment 并重新读取；仍等待持久事件确认。");
      fillAssignment(await api.getRoomAssignment(roomId.trim()));
    } catch (saveError) {
      setError(saveError);
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="data-panel assignment-panel" aria-labelledby="assignment-title">
      <header><h2 id="assignment-title">Room 模型槽位</h2><span>真实 RoomModelAssignment</span></header>
      <div className="assignment-body">
        <label className="stacked-field">Room ID<input placeholder="room_planner" value={roomId} onChange={(event) => { setRoomId(event.target.value); setEditing(false); setAssignment(null); }} /></label>
        <div className="page-actions settings-form-actions"><Button disabled={busy} onClick={() => { void loadAssignment(); }}>读取当前分配</Button><Button disabled={busy || !/^room_[a-z0-9]+$/.test(roomId.trim())} onClick={() => { fillAssignment(null); }}>准备新分配</Button></div>
        {error !== null ? <ApiErrorState error={error} /> : null}
        {editing ? <div className="assignment-grid">
          <label>Primary<select aria-label="Primary" value={primary} onChange={(event) => { setPrimary(event.target.value); }}><option value="">请选择</option>{profiles.map((profile) => <option disabled={!profile.enabled} key={profile.id} value={profile.id}>{profile.name} · {profile.model}{profile.enabled ? "" : "（已禁用）"}</option>)}</select></label>
          <label>Reviewer A<select aria-label="Reviewer A" value={reviewerA} onChange={(event) => { setReviewerA(event.target.value); }}><option value="">不分配</option>{profiles.map((profile) => <option disabled={!profile.enabled} key={profile.id} value={profile.id}>{profile.name} · {profile.model}{profile.enabled ? "" : "（已禁用）"}</option>)}</select></label>
          <label>Reviewer B<select aria-label="Reviewer B" value={reviewerB} onChange={(event) => { setReviewerB(event.target.value); }}><option value="">不分配</option>{profiles.map((profile) => <option disabled={!profile.enabled} key={profile.id} value={profile.id}>{profile.name} · {profile.model}{profile.enabled ? "" : "（已禁用）"}</option>)}</select></label>
          <div className="page-actions"><Button disabled={busy || profiles.length === 0} tone="primary" onClick={() => void saveAssignment()}>保存 Room 分配</Button></div>
        </div> : null}
      </div>
      <p className="contract-note">Room 由现有工作流创建。此页面只按真实 Room ID 读取或更新三槽位，不创建 Room，也不绕过 Profile 启用状态。</p>
    </section>
  );
}

function ConnectedSettingsPage({ api, events }: { api: BackendApi; events: EventReadModel }) {
  const load = useCallback(async () => {
    const [system, profiles] = await Promise.all([api.systemInfo(), api.listModelProfiles()]);
    return { system, profiles: profiles.profiles };
  }, [api]);
  const { reload, resource } = useAsyncResource(load);
  const [selectedProfile, setSelectedProfile] = useState<ModelProfile | null>(null);
  const [form, setForm] = useState<ProfileFormState>(emptyProfileForm);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [pending, setPending] = useState<PendingConfirmation | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    if (pending === null) {
      return;
    }
    const confirmed = events.recentEvents.some(
      (event) => event.event_type === pending.eventType && event.correlation_id === pending.correlationId,
    );
    if (confirmed) {
      setNotice(`已收到 ${pending.eventType} 持久事件。`);
      setPending(null);
      void reload();
    }
  }, [events.recentEvents, pending, reload]);

  const submitProfile = async (event: SyntheticEvent<HTMLFormElement>) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const receipt = selectedProfile === null
        ? await api.createModelProfile(profileCreateInput(form))
        : await api.updateModelProfile(selectedProfile, profileUpdateInput(form));
      const eventType = selectedProfile === null ? "model_profile.created" : "model_profile.updated";
      setPending({ correlationId: receipt.correlationId, eventType });
      setNotice(`后端已返回 ${receipt.payload.id} 并重新读取；仍等待 ${eventType} 持久事件确认。`);
      setSelectedProfile(null);
      setForm(emptyProfileForm);
      await reload();
    } catch (submitError) {
      setError(submitError);
    } finally {
      setBusy(false);
    }
  };

  if (resource.phase === "loading") {
    return <div className="page-loading">正在读取 system/info 与 ModelProfile…</div>;
  }
  if (resource.phase === "error") {
    return <ApiErrorState error={resource.error} onRetry={() => { void reload(); }} />;
  }

  return (
    <section className="feature-page settings-workspace" aria-labelledby="settings-title">
      <header className="feature-heading"><div><span className="eyebrow">本地模型与权限</span><h1 id="settings-title">设置</h1><p>只配置阶段 5 已冻结的 ModelProfile 与 Room 模型槽位；应用级 SettingsQuery 仍不可用。</p></div><Button onClick={() => { void reload(); }}>刷新</Button></header>
      {notice !== null ? <div className="event-wait global-wait">{notice}{pending !== null ? ` correlation ${pending.correlationId}` : ""}</div> : null}
      {error !== null ? <ApiErrorState error={error} /> : null}

      <div className="settings-summary-grid">
        <article><span>后端版本</span><strong>{resource.data.system.backend_version}</strong><small>protocol v{String(resource.data.system.protocol_version)}</small></article>
        <article><span>模型配置</span><strong>{String(resource.data.profiles.length)}</strong><small>来自 GET /model-profiles</small></article>
        <article><span>SecretStore</span><strong>不可用</strong><small>Renderer 不接收 API Key</small></article>
        <article><span>模型测试</span><strong>不可用</strong><small>没有 Test operation</small></article>
      </div>

      <div className="settings-main-grid">
        <section className="data-panel" aria-labelledby="profile-list-title">
          <header><h2 id="profile-list-title">ModelProfile</h2><span>{String(resource.data.profiles.length)} 项</span></header>
          <div className="profile-list">{resource.data.profiles.map((profile) => <article key={profile.id}><header><div><strong>{profile.name}</strong><span>{providerLabel(profile.provider)} · {profile.model}</span></div><span className={`state-badge ${profile.enabled ? "state-ready" : "state-closed"}`}>{profile.enabled ? "enabled" : "disabled"}</span></header><dl><div><dt>Profile ID</dt><dd>{profile.id}</dd></div><div><dt>Base URL</dt><dd>{profile.base_url}</dd></div><div><dt>credential_ref</dt><dd>{profile.credential_ref}</dd></div><div><dt>脱敏提示</dt><dd>{profile.masked_hint}</dd></div><div><dt>版本</dt><dd>{String(profile.version)}</dd></div><div><dt>更新时间</dt><dd>{new Date(profile.updated_at).toLocaleString()}</dd></div></dl><div className="page-actions"><Button onClick={() => { setSelectedProfile(profile); setForm(formFromProfile(profile)); }}>编辑</Button></div></article>)}</div>
          {resource.data.profiles.length === 0 ? <p className="empty-copy">后端当前没有 ModelProfile。可在右侧创建只包含凭证引用的配置。</p> : null}
        </section>

        <section className="data-panel" aria-labelledby="profile-editor-title">
          <header><h2 id="profile-editor-title">{selectedProfile === null ? "创建模型配置" : `编辑 ${selectedProfile.id}`}</h2><span>无明文密钥</span></header>
          <ModelProfileForm busy={busy} form={form} selectedProfile={selectedProfile} setForm={setForm} onCancel={() => { setSelectedProfile(null); setForm(emptyProfileForm); }} onSubmit={(event) => { void submitProfile(event); }} />
        </section>
      </div>

      <AssignmentEditor api={api} events={events} profiles={resource.data.profiles} onPending={(nextPending, nextNotice) => { setPending(nextPending); setNotice(nextNotice); }} />

      <section className="data-panel unavailable-settings-panel" aria-labelledby="application-settings-title">
        <header><h2 id="application-settings-title">应用级设置</h2><span>契约缺失</span></header>
        <div className="unavailable-capability"><p>后端未提供 SettingsQuery 或应用设置写入接口；最近模型调用和聚合用量也没有全局查询契约。</p><Button disabled disabledReason="后端未提供设置保存契约">保存设置</Button></div>
      </section>
    </section>
  );
}

export function SettingsPage() {
  const { api, events } = useBackend();
  return api === null ? <SettingsUnavailable /> : <ConnectedSettingsPage api={api} events={events} />;
}
