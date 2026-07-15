# Backend Stage 2 Implementation

> Status: completed and verified. This is the single Stage 2 execution baseline.

## Goal

Implement project/workspace ownership, project-relative manifests, preflight, content-addressed checkpoints, safe restore, external-change detection, and three-way file conflicts without relying on Git.

## Fixed delivery order

| Slice | Delivery | Completion gate |
| --- | --- | --- |
| 2A Project registry | Project and Workspace domain records, Managed/Direct mode, persistence, atomic EventLog/Outbox changes | create/read/list/rollback, duplicate workspace, migration upgrade/downgrade |
| 2B Workspace boundary | safe root validation, `.agent/` metadata, canonical ProjectManifest, atomic metadata writes | illegal path, unreadable path, symlink/reparse escape, canonical relative paths, concurrent write |
| 2C Preflight | manifest/dependency/command/test discovery and PASS/WARNING/NEEDS_FIX/FAIL evidence | new/existing/no-test projects and non-bypassable failure states |
| 2D Checkpoints | content-addressed blobs, project checkpoints, file index, protected checkpoint before mutation/restore | hash verification, deduplication, atomic publication, retention protection |
| 2E Changes and restore | external changes, three-way FileConflict, safe restore with impact report | user-data protection, concurrent changes, conflict resolution, failed restore recovery |
| 2F API closure | project/preflight/checkpoint/conflict queries and commands plus Stage 2 runtime closure | authenticated contract tests, events, restart, full Backend gates |

## Non-negotiable rules

- Direct Workspace files are never silently deleted.
- Managed Workspace storage stays under the application data root.
- Manifest and checkpoint paths are canonical project-relative paths.
- No checkpoint, restore, or correctness rule depends on Git.
- Project state and its EventEnvelope/Outbox records commit in one SQLite transaction.
- Filesystem publication uses temporary files, fsync, atomic replace, and post-publication hash verification.

## Completion evidence

- Traceability index: `docs/backend/BACKEND-STAGE2-TRACEABILITY-v1.md`.
- Full Backend gate: Ruff format check passed; Ruff lint passed; Mypy passed for 95 source files; `688 passed, 12 skipped`.
- API closure and restart closure are covered by the authenticated project contract tests and `test_stage2_runtime_closure.py`.
