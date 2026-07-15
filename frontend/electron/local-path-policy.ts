import { resolve, sep } from "node:path";

import { isRecord } from "./runtime-contracts";

const TRUSTED_PATH_KEYS = new Set([
  "canonical_root_path",
  "data_root",
  "log_root",
  "backup_root",
  "snapshot_root",
  "model_output_root",
]);

export class LocalPathPolicy {
  private readonly roots = new Set<string>();

  allowSelectedRoot(path: string): void {
    this.roots.add(resolve(path));
  }

  observeBackendPayload(payload: unknown): void {
    this.walk(payload);
  }

  assertAllowed(path: string): string {
    const candidate = resolve(path);
    for (const root of this.roots) {
      if (candidate === root || candidate.startsWith(root + sep)) {
        return candidate;
      }
    }
    throw new Error("Local location was not returned by the backend or selected by the user");
  }

  private walk(value: unknown): void {
    if (Array.isArray(value)) {
      for (const item of value) {
        this.walk(item);
      }
      return;
    }
    if (!isRecord(value)) {
      return;
    }
    for (const [key, item] of Object.entries(value)) {
      if (TRUSTED_PATH_KEYS.has(key) && typeof item === "string") {
        this.roots.add(resolve(item));
      } else {
        this.walk(item);
      }
    }
  }
}

