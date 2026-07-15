# Backend Stage 2 Traceability

> Status: completed and verified on 2026-07-15. This is the requirement-to-code-to-test index for Stage 2.

## Delivery slices

| Slice | Implementation | Verification |
| --- | --- | --- |
| 2A Project registry | `domain/projects/models.py`, `ports/projects.py`, `infrastructure/database/project_repository.py`, migration `0003_project_registry.py` | `test_project_contracts.py`, `test_project_repository.py`, `test_project_registry_migration.py` |
| 2B Workspace boundary | `infrastructure/projects/paths.py`, `infrastructure/projects/metadata.py`, project manifest persistence, metadata atomic writes | `test_project_metadata.py`, path and manifest cases in `test_project_checkpoints.py`, full gate |
| 2C Preflight | `application/projects/preflight.py`, preflight repository methods, migration `0004_project_preflight.py` | `test_project_preflight.py`, `test_project_preflight_repository.py`, `test_project_preflight_migration.py` |
| 2D Checkpoints | `infrastructure/projects/checkpoints.py`, checkpoint repository, migration `0005_project_checkpoints.py` | `test_project_checkpoints.py`, `test_project_checkpoint_repository.py`, `test_project_checkpoint_migration.py` |
| 2E Changes and restore | `application/projects/changes.py`, safe restore and conflict persistence, migration `0006_project_conflicts.py` | `test_project_changes.py`, `test_project_conflict_repository.py`, `test_project_conflict_migration.py` |
| 2F API closure | `application/projects/service.py`, thin `interfaces/api/routes/projects.py`, lifecycle registration, shared database write serialization | `contract/test_project_api.py`, `integration/test_stage2_runtime_closure.py`, lifecycle and Outbox regression tests |

## Hard-rule coverage

| Rule | Enforcement |
| --- | --- |
| Direct workspace files are not silently deleted | Direct mode validates and operates in place; restore and conflict operations use explicit protected checkpoints and impact data. |
| Managed storage stays below the application data root | Managed workspace creation and cleanup enforce canonical parent containment and reject links/reparse points. |
| Paths are canonical project-relative paths | Manifest and checkpoint stores reject absolute, traversal, drive-qualified, and link-escaping paths. |
| Git is not required for correctness | Content-addressed checkpoints, external-change detection, and three-way conflicts use the project file index and hashes. |
| State and EventEnvelope/Outbox commit atomically | Project writes use the write UnitOfWork and shared application write lock; event and outbox rows share the transaction. |
| Filesystem publication is durable and verified | Checkpoint blobs and metadata use temporary files, fsync, atomic replace, and post-write hash checks. |

## Runtime closure

The authenticated API exposes project registration, open/close, preflight, checkpoint creation/listing, restore planning and confirmation, external-change scans, conflict queries, and conflict resolution. `ProjectApplicationService` owns all SQLAlchemy, filesystem, checkpoint, and event orchestration; route handlers only validate/convert requests and responses. The application lifespan registers and clears the service together with the database, and the Outbox/audit publishers share the same database write lock.

The complete Backend quality gate passed with `688 passed, 12 skipped`.
