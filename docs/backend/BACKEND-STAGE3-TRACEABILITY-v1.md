# Backend Stage 3 Traceability

> Status: completed and verified on 2026-07-15. This is the requirement-to-code-to-test index for Stage 3.

## Delivery

| Requirement | Implementation | Verification |
| --- | --- | --- |
| Workflow and five-stage state machine | `domain/workflows/models.py`, `state_machine.py`, frozen `Stage`/`STAGE_ORDER`/`StageRunState` contracts | `test_workflow_state_machine.py`, workflow API contract test |
| Durable Workflow/StageRun/Room/Message/Task graph | migration `0007_workflows.py`, `workflow_repository.py`, UnitOfWork integration | workflow migration, restart closure, foundation migration tests |
| Conditional commands and atomic events | `application/workflows/service.py`, shared database write lock, EventLog/Outbox transaction | duplicate start, concurrent transition, stale-version and regression tests |
| Immutable chat and consultation | sequenced append-only messages, correction references, active/consultation/archived rooms | message sequence, correction, pagination, completed-room consultation tests |
| Task queue and cancellation | ordered queued/running/terminal transitions with optimistic versions | out-of-order start, single running task, completion, cancellation, reopen invalidation tests |
| Explicit reopen | new stage attempts and rooms, archived prior rooms, cancelled affected work, retained history | reopen history and downstream invalidation contract test |
| Authenticated real-time events | one-time ticket store, durable replay query, subscribe-before-replay broker, `websocket_v1` Outbox publisher | ticket reuse/expiry, replay order, live delivery, reconnect cursor, dedup tests |
| Runtime closure | lifecycle-owned workflow/event services and restart-safe SQLite state | `test_stage3_runtime_closure.py`, lifecycle/Outbox/Stage 2 regressions |

## Invariants

- Planner starts `ready`; Designer, Builder, Reviewer, and Deployer start `locked` and unlock only after the predecessor reaches `completed`.
- State changes pass the domain transition graph and compare both Workflow and StageRun versions.
- Messages have a gap-free per-room sequence and are never updated or deleted; corrections append a new referenced message.
- Completed rooms accept consultation only. Reopen creates new attempts and rooms while preserving prior history.
- Tasks execute in queue order, permit at most one running task per workflow, and use versioned terminal transitions.
- State, EventEnvelope, local audit delivery, and WebSocket delivery targets are created in one write transaction.
- WebSocket subscription is established before replay; overlapping live/replayed events are suppressed by `event_id`.

## Verification

- Ruff format: 190 files formatted.
- Ruff lint: passed.
- Mypy strict: 106 source files passed.
- Pytest: `696 passed, 12 skipped`.
- One non-failing third-party warning remains: FastAPI's current `TestClient` imports a Starlette compatibility wrapper that is deprecated in favor of `httpx2`.
