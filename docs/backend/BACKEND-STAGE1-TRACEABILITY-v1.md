# Backend Stage 1 Traceability

> Status: completed and verified. This record is the Stage 1 requirement-to-code-to-test index.

| Requirement | Implementation | Verification |
| --- | --- | --- |
| Shared contracts and identifiers | `backend/src/agent_platform/domain/contracts/`, `backend/src/agent_platform/domain/shared/ids.py` | `backend/tests/unit/test_execution_contracts.py`, `test_domain_shared.py` |
| EventEnvelope and error categories | `backend/src/agent_platform/domain/events/`, `backend/src/agent_platform/domain/shared/errors.py` | `backend/tests/unit/test_event_contracts.py`, `test_domain_shared.py`, `backend/tests/contract/test_system_api.py` |
| RoleCard resources and StageContract | `backend/src/agent_platform/domain/contracts/`, `backend/src/agent_platform/resources/roles/v1/` | `backend/tests/contract/test_role_card_resources.py`, `test_stage_role_alignment.py`, `backend/tests/unit/test_stage_contracts.py`, `test_stage_contract_kernel.py` |
| Version, schema, launcher, and Watchdog | `backend/src/agent_platform/version.py`, `infrastructure/database/schema.py`, `main.py`, `bootstrap/lifespan.py` | `backend/tests/unit/test_version.py`, `test_main.py`, migration tests, `backend/tests/integration/test_application_lifespan.py` |
| Durable diagnostics | `backend/src/agent_platform/infrastructure/redaction.py`, `infrastructure/logging/`, `infrastructure/workers/stderr.py` | `backend/tests/unit/test_redaction.py`, `test_log_redaction.py`, `test_worker_stderr.py`, `backend/tests/process/test_worker_supervisor.py` |
| Bounded bidirectional IPC replay | `backend/src/agent_platform/interfaces/ipc/replay.py`, `infrastructure/workers/supervisor.py`, `workers/main.py` | `backend/tests/unit/test_ipc_replay.py`, `test_ipc_framing.py`, `backend/tests/process/test_worker_protocol.py`, `test_worker_supervisor.py` |
| SQLite resilience | `backend/src/agent_platform/infrastructure/database/instance_lock.py`, `integrity.py`, `backup.py`, `maintenance.py` | `backend/tests/unit/test_database_instance_lock.py`, `test_database_integrity.py`, `backend/tests/integration/test_database_backup.py`, `test_database_maintenance.py`, `test_database_bootstrap.py` |
| Durable EventLog and reliable Outbox | `backend/src/agent_platform/infrastructure/database/repositories.py`, `unit_of_work.py`, `outbox_store.py`, `local_audit.py`, `backend/src/agent_platform/application/events/outbox_dispatcher.py` | `backend/tests/migration/test_reliable_outbox_migration.py`, `backend/tests/integration/test_event_unit_of_work.py`, `test_outbox_dispatcher.py`, `test_local_audit_publisher.py` |
| Complete runtime closure | `backend/src/agent_platform/bootstrap/lifespan.py` | `backend/tests/integration/test_stage1_runtime_closure.py`, complete Backend quality gate |

## Deliberate deferrals

- Stage 2 owns Project, Workspace, Managed/Direct mode, Preflight, checkpoints, restore, external-change detection, and FileConflict handling.
- Stage 3 owns workflow state machines, rooms, tasks, WebSocket delivery, tickets, and event replay.
- Electron owns desktop token and port process control after the frontend contract is frozen.
- Product Git operations remain an optional future adapter boundary and are not implemented in V1 now.
- Automatic Worker restart remains deferred; Stage 1 provides supervision and deterministic cleanup only.
