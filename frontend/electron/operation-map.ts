import { readFile } from "node:fs/promises";

import type { OperationDefinition, OperationMap } from "./runtime-contracts";
import { isRecord } from "./runtime-contracts";

const ALLOWED_METHODS = new Set(["GET", "POST", "PUT", "PATCH", "DELETE"]);

export async function loadOperationMap(path: string): Promise<OperationMap> {
  const document: unknown = JSON.parse(await readFile(path, "utf8"));
  if (!isRecord(document) || !isRecord(document.capabilities)) {
    throw new Error("Capability manifest does not contain an operation map");
  }
  const operations = Object.create(null) as Record<string, OperationDefinition>;
  for (const [operationId, candidate] of Object.entries(document.capabilities)) {
    if (
      !isRecord(candidate) ||
      typeof candidate.method !== "string" ||
      !ALLOWED_METHODS.has(candidate.method) ||
      typeof candidate.path !== "string" ||
      !candidate.path.startsWith("/api/v1/")
    ) {
      throw new Error(`Capability manifest operation ${operationId} is invalid`);
    }
    operations[operationId] = {
      method: candidate.method as OperationDefinition["method"],
      path: candidate.path,
    };
  }
  if (Object.keys(operations).length !== 68) {
    throw new Error("Capability manifest operation count does not match the frozen contract");
  }
  return Object.freeze(operations);
}
