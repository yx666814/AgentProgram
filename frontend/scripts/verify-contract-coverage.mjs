import { createHash } from "node:crypto";
import { execFileSync } from "node:child_process";
import fs from "node:fs";

const contractFiles = ["openapi.json", "events.schema.json", "capabilities.json"];
const readJson = (fileName) =>
  JSON.parse(fs.readFileSync(new URL(`../contracts/${fileName}`, import.meta.url), "utf8"));
const sha256 = (fileName) =>
  createHash("sha256")
    .update(fs.readFileSync(new URL(`../contracts/${fileName}`, import.meta.url)))
    .digest("hex")
    .toUpperCase();

const openapi = readJson("openapi.json");
const snapshot = readJson("capabilities.json");
const events = readJson("events.schema.json");
const hashes = readJson("SHA256SUMS.json");
const backendTree = execFileSync("git", ["rev-parse", "HEAD:backend"], {
  cwd: new URL("../..", import.meta.url),
  encoding: "utf8",
}).trim();

if (snapshot.backendTree !== backendTree || events.backendTree !== backendTree) {
  throw new Error("Contract snapshots do not match the current backend tree");
}

for (const fileName of contractFiles) {
  if (hashes.files[fileName] !== sha256(fileName)) {
    throw new Error(`SHA-256 mismatch for ${fileName}`);
  }
}

const operations = Object.entries(openapi.paths).flatMap(([path, pathItem]) =>
  Object.entries(pathItem)
    .filter(([method]) => ["get", "post", "put", "patch", "delete"].includes(method))
    .map(([method, operation]) => [operation.operationId, method.toUpperCase(), path]),
);

if (operations.length !== 68) {
  throw new Error(`Expected 68 frozen REST operations, found ${operations.length}`);
}
for (const [operationId, method, path] of operations) {
  const capability = snapshot.capabilities[operationId];
  if (!capability || capability.method !== method || capability.path !== path) {
    throw new Error(`Missing capability mapping for ${method} ${path}`);
  }
}
if (Object.keys(snapshot.capabilities).length !== operations.length) {
  throw new Error("Capability snapshot contains frontend-only aliases");
}
if (snapshot.workflowStates.length !== 12 || snapshot.stageRunStates.length !== 16) {
  throw new Error("Workflow or StageRun state coverage is incomplete");
}
if (snapshot.stageContracts.length !== 5 || snapshot.tools.length !== 23) {
  throw new Error("StageContract or Tool Catalog coverage is incomplete");
}
if (events.eventTypes.length !== 41) {
  throw new Error(`Expected 41 backend event types, found ${events.eventTypes.length}`);
}

console.log(
  `Verified ${operations.length} REST operations, ${events.eventTypes.length} events, ` +
    `${snapshot.stageContracts.length} stage contracts, and ${snapshot.tools.length} tools.`,
);
