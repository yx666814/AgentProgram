import { randomUUID } from "node:crypto";
import { mkdir, readFile, rename, rm, writeFile } from "node:fs/promises";
import { dirname } from "node:path";

import { safeStorage } from "electron";

import { isRecord } from "./runtime-contracts";

const CREDENTIAL_REF_PATTERN = /^credential\.xingxie\.[a-f0-9]{32}$/;
const MAX_SECRET_LENGTH = 16_384;

interface StoredSecretRecord {
  encrypted: string;
  label: string;
  updatedAt: string;
}

interface SecretDocument {
  version: 1;
  records: Record<string, StoredSecretRecord>;
}

export interface StoredSecretReference {
  credentialRef: string;
  maskedHint: string;
}

function validRecord(value: unknown): value is StoredSecretRecord {
  return (
    isRecord(value) &&
    typeof value.encrypted === "string" &&
    typeof value.label === "string" &&
    typeof value.updatedAt === "string"
  );
}

function maskedHint(value: string): string {
  if (value.length <= 4) {
    return "****";
  }
  const prefix = value.slice(0, Math.min(3, value.length - 4));
  return `${prefix}****${value.slice(-4)}`;
}

export class EncryptedSecretStore {
  private document: SecretDocument | null = null;
  private mutationTail: Promise<void> = Promise.resolve();

  constructor(private readonly filePath: string) {}

  store(value: string, label: string): Promise<StoredSecretReference> {
    return this.mutate(async () => {
      this.requireEncryption();
      if (value.length === 0 || value.length > MAX_SECRET_LENGTH) {
        throw new Error("Secret value is empty or exceeds the desktop limit");
      }
      const normalizedLabel = label.trim();
      if (normalizedLabel.length === 0 || normalizedLabel.length > 120) {
        throw new Error("Secret label is invalid");
      }
      const document = await this.load();
      const credentialRef = `credential.xingxie.${randomUUID().replaceAll("-", "")}`;
      document.records[credentialRef] = {
        encrypted: safeStorage.encryptString(value).toString("base64"),
        label: normalizedLabel,
        updatedAt: new Date().toISOString(),
      };
      await this.persist(document);
      return { credentialRef, maskedHint: maskedHint(value) };
    });
  }

  delete(credentialRef: string): Promise<void> {
    return this.mutate(async () => {
      if (!CREDENTIAL_REF_PATTERN.test(credentialRef)) {
        return;
      }
      const document = await this.load();
      if (!(credentialRef in document.records)) {
        return;
      }
      document.records = Object.fromEntries(
        Object.entries(document.records).filter(([key]) => key !== credentialRef),
      );
      await this.persist(document);
    });
  }

  async resolve(credentialRef: string): Promise<string | null> {
    await this.mutationTail;
    this.requireEncryption();
    if (!CREDENTIAL_REF_PATTERN.test(credentialRef)) {
      return null;
    }
    const document = await this.load();
    const record = document.records[credentialRef];
    if (record === undefined) {
      return null;
    }
    try {
      return safeStorage.decryptString(Buffer.from(record.encrypted, "base64"));
    } catch {
      return null;
    }
  }

  private mutate<T>(operation: () => Promise<T>): Promise<T> {
    const result = this.mutationTail.then(operation, operation);
    this.mutationTail = result.then(
      () => undefined,
      () => undefined,
    );
    return result;
  }

  private requireEncryption(): void {
    if (!safeStorage.isEncryptionAvailable()) {
      throw new Error("Windows secret encryption is unavailable");
    }
  }

  private async load(): Promise<SecretDocument> {
    if (this.document !== null) {
      return this.document;
    }
    try {
      const value: unknown = JSON.parse(await readFile(this.filePath, "utf8"));
      if (!isRecord(value) || value.version !== 1 || !isRecord(value.records)) {
        throw new Error("Encrypted secret document is invalid");
      }
      const records: Record<string, StoredSecretRecord> = {};
      for (const [credentialRef, record] of Object.entries(value.records)) {
        if (!CREDENTIAL_REF_PATTERN.test(credentialRef) || !validRecord(record)) {
          throw new Error("Encrypted secret record is invalid");
        }
        records[credentialRef] = record;
      }
      this.document = { version: 1, records };
    } catch (error) {
      const code = isRecord(error) ? error.code : undefined;
      if (code !== "ENOENT") {
        throw error;
      }
      this.document = { version: 1, records: {} };
    }
    return this.document;
  }

  private async persist(document: SecretDocument): Promise<void> {
    await mkdir(dirname(this.filePath), { recursive: true });
    const temporary = `${this.filePath}.${randomUUID()}.tmp`;
    try {
      await writeFile(temporary, JSON.stringify(document), { encoding: "utf8", flag: "wx" });
      await rename(temporary, this.filePath);
      this.document = document;
    } finally {
      await rm(temporary, { force: true });
    }
  }
}
