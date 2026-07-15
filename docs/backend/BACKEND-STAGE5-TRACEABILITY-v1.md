# Backend Stage 5 Traceability v1

Status: complete

Stage 5 completes the local backend V1 on top of the merged Stage 0–4 project, workflow, event,
and model-runtime foundations. It does not implement product-internal Git operations, Electron
pages, or packaging.

## Delivered runtime

- Tool Catalog with stable tool names, capability ownership, operation type, path scope, mutation
  flag, and maximum timeout.
- PathGuard enforcement for StageContract capabilities, task-scoped approvals, excluded paths,
  protected `.agent` metadata, artifact ownership, source/test/build/generated/deployment scopes,
  and permanent prohibitions.
- Atomic UTF-8 project file read/write/create/delete tools with optimistic SHA-256 checks,
  symlink/reparse rejection, bounded file sizes, fsync, atomic replacement, and publish
  verification.
- Registered project command execution without a shell. Windows commands are atomically placed in
  a kill-on-close Job Object; timeout, cancellation, output limits, and shutdown kill the complete
  process tree.
- Persisted CapabilityRequest, Approval, and ToolCall audit. Grants expire when their task becomes
  terminal. Tool audit stores hashes, byte counts, exit status, and sanitized codes rather than raw
  content or credentials.
- Append-only Artifact and ArtifactVersion persistence with draft, locked, superseded, and
  invalidated states.
- Deterministic Quality Gate evaluation for artifact integrity, formal Primary + Reviewer A/B +
  P2R completion, terminal task state, open conflicts, and registered test commands.
- MANUAL approval and AUTONOMOUS policy. PASS can produce Checkpoint + locked ArtifactVersion +
  immutable HandoffPacket + next-stage unlock in one database transaction. FAIL and autonomous
  WARNING produce ChangeRequest and blocking stage state.
- Upstream reopen and ChangeRequest invalidation for downstream artifact versions and handoff
  packets while retaining history.
- Pause, resume, stop, abandon, Worker/Agent/Tool cancellation, direct-workspace preservation, and
  startup recovery records for interrupted tasks, model calls, agent runs, tools, workflows, and
  stage runs.
- Desktop Control Contract v1 with authenticated readiness/control discovery and graceful shutdown
  request handling.

## Persistence

Alembic revision `0009_stage5_governance` adds workflow execution mode plus:

- `capability_requests`
- `approvals`
- `tool_calls`
- `artifacts`
- `artifact_versions`
- `quality_gate_runs`
- `quality_gate_issues`
- `quality_gate_artifacts`
- `handoff_packets`
- `change_requests`
- `recovery_records`

The migration upgrades from and downgrades to `0008_model_runtime` cleanly.

## Frozen REST and control surface

- `GET /api/v1/tools/catalog`
- `POST/GET /api/v1/tasks/{task_id}/capability-requests` and workflow request listing
- `POST /api/v1/capability-requests/{request_id}/decision`
- `POST /api/v1/tasks/{task_id}/tool-calls`, workflow audit listing, and cancellation
- `POST /api/v1/workflows/{workflow_id}/mode`
- ArtifactVersion create and workflow artifact queries
- Quality Gate evaluate/list and Approval decide/list
- Handoff and ChangeRequest commands/queries
- Workflow pause/resume/stop/abandon
- Recovery list/resume/discard
- `GET /api/v1/system/control`
- `POST /api/v1/system/shutdown`

WebSocket event delivery remains on the Stage 3 replay/outbox contract. IPC remains protocol v1;
Stage 5 reuses the existing Worker shutdown and process ownership semantics rather than creating a
parallel protocol.

## Verification

Final full gate on 2026-07-15:

- `718 passed, 12 skipped`
- Ruff lint passed
- Ruff format check passed for 233 files
- Mypy strict passed for 136 source files

Dedicated coverage includes capability denial/approval/expiry, atomic optimistic writes, excluded
paths, Windows/POSIX process-tree timeout cleanup, MANUAL approval handoff, AUTONOMOUS warning
rewrite, migration upgrade/downgrade, pause/resume/stop, crash recovery, Desktop Control shutdown,
and a complete five-stage Fake-Model Primary + Reviewer A/B + P2R workflow ending in five locked
artifact versions and five immutable handoff packets.
