// @vitest-environment node

import { readFile, rm } from "node:fs/promises";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { randomUUID } from "node:crypto";

import { afterEach, expect, it, vi } from "vitest";

const roots: string[] = [];

vi.mock("electron", () => ({
  safeStorage: {
    isEncryptionAvailable: () => true,
    encryptString: (value: string) => Buffer.from(`encrypted:${value}`, "utf8"),
    decryptString: (value: Buffer) => value.toString("utf8").replace(/^encrypted:/u, ""),
  },
}));

afterEach(async () => {
  await Promise.all(roots.splice(0).map((root) => rm(root, { force: true, recursive: true })));
});

it("stores only encrypted bytes and never offers a list or read API to the renderer", async () => {
  const root = join(tmpdir(), `xingxie-secret-test-${randomUUID()}`);
  roots.push(root);
  const file = join(root, "credentials.v1.json");
  const { EncryptedSecretStore } = await import("../../../electron/secret-store");
  const store = new EncryptedSecretStore(file);

  const reference = await store.store("sk-test-12345678", "Primary model");

  expect(reference.credentialRef).toMatch(/^credential\.xingxie\.[a-f0-9]{32}$/u);
  expect(reference.maskedHint).toBe("sk-****5678");
  expect(await store.resolve(reference.credentialRef)).toBe("sk-test-12345678");
  expect(await readFile(file, "utf8")).not.toContain("sk-test-12345678");

  await store.delete(reference.credentialRef);
  expect(await store.resolve(reference.credentialRef)).toBeNull();
});

