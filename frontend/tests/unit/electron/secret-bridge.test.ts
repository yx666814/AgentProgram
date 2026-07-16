// @vitest-environment node

import { expect, it } from "vitest";

import { SecretBridgeServer } from "../../../electron/secret-bridge";
import type { EncryptedSecretStore } from "../../../electron/secret-store";

it("resolves secrets only over the authenticated loopback bridge", async () => {
  const secrets = {
    resolve: (credentialRef: string) =>
      Promise.resolve(credentialRef === "credential.xingxie.primary" ? "api-key" : null),
  } as EncryptedSecretStore;
  const bridge = new SecretBridgeServer(secrets);
  const connection = await bridge.start();
  try {
    const unauthorized = await fetch(`${connection.origin}/v1/resolve`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ credential_ref: "credential.xingxie.primary" }),
    });
    expect(await unauthorized.json()).toEqual({ value: null });

    const authorized = await fetch(`${connection.origin}/v1/resolve`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${connection.token}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ credential_ref: "credential.xingxie.primary" }),
    });
    expect(authorized.status).toBe(200);
    expect(await authorized.json()).toEqual({ value: "api-key" });
  } finally {
    await bridge.stop();
  }
});
