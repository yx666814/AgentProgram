import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it } from "vitest";

import { BackendProvider } from "../../src/api/backend-context";
import { SettingsPage } from "../../src/features/settings/settings-page";
import { createFakeDesktopPort, reply } from "../support/fake-desktop-port";
import { modelProfile } from "../support/settings-diagnostics-fixtures";

it("creates a real ModelProfile and waits for its persisted event", async () => {
  const user = userEvent.setup();
  const profiles = [] as ReturnType<typeof modelProfile>[];
  const port = createFakeDesktopPort({
    query(request) {
      switch (request.operationId) {
        case "system_info_api_v1_system_info_get":
          return reply(request, { backend_version: "0.1.0", protocol_version: 1 });
        case "list_profiles_api_v1_model_profiles_get":
          return reply(request, { profiles });
        default:
          throw new Error(`Unexpected query ${request.operationId}`);
      }
    },
    command(request) {
      if (request.operationId !== "create_profile_api_v1_model_profiles_post") {
        throw new Error(`Unexpected command ${request.operationId}`);
      }
      const profile = modelProfile();
      profiles.push(profile);
      return reply(request, profile, 201);
    },
  });

  render(<BackendProvider port={port}><SettingsPage /></BackendProvider>);
  await screen.findByRole("heading", { name: "创建模型配置" });
  await user.type(screen.getByLabelText("配置名称"), "主模型");
  await user.type(screen.getByLabelText("模型 ID"), "gpt-primary");
  await user.type(screen.getByLabelText("Base URL"), "https://models.example/v1");
  await user.type(screen.getByLabelText("凭证引用"), "vault:model.primary");
  await user.type(screen.getByLabelText("脱敏提示"), "key-****42");
  await user.click(screen.getByRole("button", { name: "创建模型配置" }));

  expect(await screen.findByText(/等待 model_profile\.created/)).toBeVisible();
  const command = port.calls.commands[0];
  expect(command?.payload).toMatchObject({
    credential_ref: "vault:model.primary",
    masked_hint: "key-****42",
    provider: "openai_compatible",
  });
  expect(JSON.stringify(command?.payload)).not.toMatch(/api[_-]?key|secret_value|token/i);

  const correlationId = (command?.payload as { correlation_id: string }).correlation_id;
  port.emit({
    schema_version: 1,
    event_id: 51,
    event_type: "model_profile.created",
    correlation_id: correlationId,
    actor: { type: "user", id: "user_local" },
    source: "backend",
    occurred_at: "2026-07-15T08:01:00Z",
    payload: { provider: "openai_compatible", model: "gpt-primary" },
  });
  expect(await screen.findByText("已收到 model_profile.created 持久事件。")).toBeVisible();
});

it("sends the backend RoomModelAssignment shape with distinct slots", async () => {
  const user = userEvent.setup();
  const profiles = [modelProfile(), modelProfile("profile_reviewer", "anthropic")];
  const port = createFakeDesktopPort({
    query(request) {
      switch (request.operationId) {
        case "system_info_api_v1_system_info_get": return reply(request, { backend_version: "0.1.0", protocol_version: 1 });
        case "list_profiles_api_v1_model_profiles_get": return reply(request, { profiles });
        case "get_room_assignment_api_v1_rooms__room_id__model_assignment_get": return reply(request, { schema_version: 1, room_id: "room_planner", primary_profile_id: "profile_primary", reviewer_a_profile_id: "profile_reviewer", reviewer_b_profile_id: null, version: 1, updated_at: "2026-07-15T08:00:00Z" });
        default: throw new Error(`Unexpected query ${request.operationId}`);
      }
    },
    command(request) {
      if (request.operationId !== "assign_room_models_api_v1_rooms__room_id__model_assignment_put") {
        throw new Error(`Unexpected command ${request.operationId}`);
      }
      return reply(request, { schema_version: 1, room_id: "room_planner", primary_profile_id: "profile_primary", reviewer_a_profile_id: "profile_reviewer", reviewer_b_profile_id: null, version: 1, updated_at: "2026-07-15T08:00:00Z" });
    },
  });

  render(<BackendProvider port={port}><SettingsPage /></BackendProvider>);
  await user.type(await screen.findByLabelText("Room ID"), "room_planner");
  await user.click(screen.getByRole("button", { name: "准备新分配" }));
  await user.selectOptions(screen.getByLabelText("Primary"), "profile_primary");
  await user.selectOptions(screen.getByLabelText("Reviewer A"), "profile_reviewer");
  await user.click(screen.getByRole("button", { name: "保存 Room 分配" }));

  expect(port.calls.commands[0]?.payload).toMatchObject({
    primary_profile_id: "profile_primary",
    reviewer_a_profile_id: "profile_reviewer",
    reviewer_b_profile_id: null,
    expected_version: null,
  });
  expect(await screen.findByText(/等待持久事件确认/)).toBeVisible();
});
