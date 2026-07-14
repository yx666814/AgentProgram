# Backend Stage 1H Reliable Outbox Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist every frozen `EventEnvelope` field and deliver transactionally snapshotted Outbox targets at least once through lease-safe, retryable, dead-lettered, idempotent processing.

**Architecture:** One immutable Alembic revision upgrades legacy `event_log`/`outbox_events`, creates per-target `outbox_deliveries` and the payload-free `local_audit_events` projection, and deterministically backfills legacy rows. Event creation inserts the EventLog row, aggregate Outbox row, and immutable target rows in one Unit of Work; an application dispatcher claims short leases, publishes outside the claim transaction, and uses the lease token for conditional confirmation. Stage 1 registers only `local_audit_v1`; it inserts its idempotent projection and marks its delivery complete in the same SQLite transaction. No WebSocket, replay API, or Stage 3 delivery target is introduced.

**Tech Stack:** Python 3.12, Pydantic v2, SQLAlchemy 2 async, SQLite WAL, Alembic, asyncio, pytest, Ruff, Mypy strict.

**Process override:** The user explicitly requested implementation-first testing for Stage 1E–1I. Each task therefore implements the approved behavior first, then adds focused automated tests and runs the stated regression commands.

**Command convention:** Every command block runs from `D:\AgentProgram\.worktrees\backend-stage1\backend`. Git commands use `git -C ..` so repository-root paths remain exact.

---

## File map

- Create `backend/src/agent_platform/domain/events/outbox.py`: closed Outbox aggregate/delivery/error enums and deterministic retry calculation.
- Create `backend/src/agent_platform/ports/event_publishing.py`: immutable delivery claim and publisher protocol.
- Modify `backend/src/agent_platform/ports/unit_of_work.py`: accept a validated `EventEnvelope`; remove the separately callable re-enqueue path.
- Modify `backend/src/agent_platform/domain/events/models.py`: align event/context identifier bounds with persisted column sizes.
- Modify `backend/src/agent_platform/config/settings.py`: bounded lease, retry, polling, drain, and cleanup policy.
- Modify `backend/src/agent_platform/infrastructure/database/schema.py`: immutable Stage 1H revision and required-table set.
- Modify `backend/src/agent_platform/infrastructure/database/models.py`: complete EventLog columns, aggregate Outbox row, per-target delivery row, and local audit projection.
- Modify `backend/src/agent_platform/infrastructure/database/repositories.py`: transactional EventLog + aggregate + immutable target insertion and envelope reconstruction.
- Modify `backend/src/agent_platform/infrastructure/database/unit_of_work.py`: expose only the revised event repository.
- Create `backend/src/agent_platform/infrastructure/database/outbox_store.py`: claim, lease recovery, conditional failure, aggregate refresh, and delivered-row cleanup.
- Create `backend/src/agent_platform/infrastructure/database/local_audit.py`: idempotent local side effect plus conditional coordinator receipt in one transaction.
- Create `backend/src/agent_platform/application/events/outbox_dispatcher.py`: polling coordinator, fixed publisher registry, safe failure categories, and stop/drain control.
- Create `backend/src/agent_platform/application/__init__.py` and `backend/src/agent_platform/application/events/__init__.py`: package markers and intended public exports.
- Create `backend/migrations/versions/0002_reliable_outbox.py`: immutable upgrade/backfill/downgrade revision; never edit `0001_foundation.py`.
- Modify `backend/migrations/env.py`: include all four mapped tables in migration metadata checks.
- Modify `backend/src/agent_platform/bootstrap/lifespan.py`: start Dispatcher after Stage 1G maintenance and bounded-drain it between maintenance cancellation and final checkpoint.
- Modify `backend/tests/integration/test_event_unit_of_work.py`: full envelope persistence and atomic target snapshot.
- Create `backend/tests/integration/test_outbox_store.py`: races, leases, retry, dead letter, recovery, aggregate state, and cleanup.
- Create `backend/tests/integration/test_local_audit_publisher.py`: payload-free idempotent side effect and lease-token confirmation.
- Create `backend/tests/unit/test_outbox_policy.py`: retry and Settings boundary tests.
- Modify `backend/tests/unit/test_event_contracts.py`: verify persisted identifier length bounds.
- Create `backend/tests/unit/test_outbox_dispatcher.py`: registry/failure/cancellation/stop behavior without timing-heavy database setup.
- Create `backend/tests/process/test_outbox_fail_stop.py`: production second-deadline fail-stop and next-start recovery.
- Create `backend/tests/migration/test_reliable_outbox_migration.py`: foundation-to-head legacy upgrade, downgrade, and re-upgrade.
- Modify `backend/tests/integration/test_application_lifespan.py`: Dispatcher startup and bounded shutdown order.
- Modify `backend/tests/migration/test_foundation_migration.py`: preserve immutable foundation assertions while expecting current revision to advance.

### Task 1: Freeze Outbox contracts, policy, schema, and ORM rows

**Files:**
- Create: `backend/src/agent_platform/domain/events/outbox.py`
- Create: `backend/src/agent_platform/ports/event_publishing.py`
- Modify: `backend/src/agent_platform/config/settings.py`
- Modify: `backend/src/agent_platform/domain/events/models.py`
- Modify: `backend/src/agent_platform/infrastructure/database/schema.py`
- Modify: `backend/src/agent_platform/infrastructure/database/models.py`
- Modify: `backend/src/agent_platform/domain/events/__init__.py`
- Test: `backend/tests/unit/test_outbox_policy.py`
- Test: `backend/tests/unit/test_event_contracts.py`

- [ ] **Step 1: Add closed states and deterministic retry policy**

Create `outbox.py` with exact values; `attempt_count` is one-based after a successful claim:

```python
from datetime import timedelta
from enum import StrEnum


class OutboxAggregateState(StrEnum):
    PENDING = "pending"
    DELIVERED = "delivered"
    DEAD_LETTER = "dead_letter"


class OutboxDeliveryState(StrEnum):
    PENDING = "pending"
    LEASED = "leased"
    RETRY_WAIT = "retry_wait"
    DELIVERED = "delivered"
    DEAD_LETTER = "dead_letter"


class DeliveryErrorCategory(StrEnum):
    LEASE_EXPIRED = "lease_expired"
    PUBLISHER_UNAVAILABLE = "publisher_unavailable"
    PUBLISHER_TIMEOUT = "publisher_timeout"
    PUBLISHER_FAILURE = "publisher_failure"


def retry_delay(
    attempt_count: int,
    *,
    base_seconds: float,
    maximum_seconds: float,
) -> timedelta:
    if attempt_count < 1:
        raise ValueError("attempt_count must be positive")
    seconds = min(maximum_seconds, base_seconds * (2 ** (attempt_count - 1)))
    return timedelta(seconds=seconds)
```

- [ ] **Step 2: Define the publisher boundary and immutable claim**

Create `event_publishing.py`; every publisher owns conditional confirmation so an external publisher can later preserve at-least-once semantics, while `local_audit_v1` can confirm atomically with its local side effect:

```python
from dataclasses import dataclass
from datetime import datetime
from typing import Final, Protocol

from agent_platform.domain.events.models import EventEnvelope

LOCAL_AUDIT_CONSUMER: Final[str] = "local_audit_v1"


@dataclass(frozen=True, slots=True)
class ClaimedDelivery:
    delivery_id: str
    event_id: int
    consumer_name: str
    lease_token: str
    attempt_count: int
    envelope: EventEnvelope


class EventPublisher(Protocol):
    @property
    def consumer_name(self) -> str: ...

    async def publish(
        self,
        envelope: EventEnvelope,
        *,
        idempotency_key: int,
        delivery_id: str,
        lease_token: str,
        delivered_at: datetime,
    ) -> None: ...
```

Align the frozen event contract with the database before adding persistence:

```python
EventType = Annotated[
    str,
    Field(max_length=120, pattern=r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+$"),
]
EventContextId = Annotated[str, Field(min_length=1, max_length=120)]
EventEntityId = Annotated[str, Field(min_length=1, max_length=80)]
```

Use `EventContextId` for correlation/causation IDs and `EventEntityId` for actor/project/workflow/room/task IDs. Extend existing event-contract tests with exact maximum and over-limit cases.

- [ ] **Step 3: Add bounded Settings fields**

Extend `Settings` without replacing Stage 1E/1G fields:

```python
outbox_poll_interval_seconds: float = 0.25
outbox_lease_seconds: float = 60.0
outbox_publish_timeout_seconds: float = 30.0
outbox_max_attempts: int = Field(default=8, ge=1, le=100)
outbox_backoff_base_seconds: float = 1.0
outbox_backoff_max_seconds: float = 300.0
outbox_shutdown_drain_seconds: float = 5.0
outbox_cleanup_interval_seconds: float = 3_600.0
outbox_delivered_retention_days: int = Field(default=30, ge=1, le=3650)
outbox_cleanup_batch_size: int = Field(default=100, ge=1, le=10_000)
outbox_recovery_batch_size: int = Field(default=100, ge=1, le=10_000)
```

Validate every float with `math.isfinite(value) and value > 0`, then add a model validator requiring:

```python
if self.outbox_poll_interval_seconds >= self.outbox_lease_seconds:
    raise ValueError("outbox poll interval must be shorter than lease duration")
if self.outbox_publish_timeout_seconds >= self.outbox_lease_seconds:
    raise ValueError("outbox publish timeout must be shorter than lease duration")
if self.outbox_backoff_base_seconds > self.outbox_backoff_max_seconds:
    raise ValueError("outbox backoff base must not exceed maximum")
```

- [ ] **Step 4: Advance shared schema constants without changing foundation**

Use:

```python
FOUNDATION_DATABASE_REVISION: Final[str] = "0001_foundation"
RELIABLE_OUTBOX_DATABASE_REVISION: Final[str] = "0002_reliable_outbox"
CURRENT_DATABASE_REVISION: Final[str] = RELIABLE_OUTBOX_DATABASE_REVISION
REQUIRED_DATABASE_TABLES: Final[frozenset[str]] = frozenset(
    {
        "alembic_version",
        "event_log",
        "outbox_events",
        "outbox_deliveries",
        "local_audit_events",
    }
)
```

- [ ] **Step 5: Replace ORM shape with the frozen Stage 1H schema**

Keep aggregate type/ID on `EventLogRow`; rename `created_at` to `occurred_at`. Add `schema_version`, correlation/causation, actor type/ID, and source. Remodel `OutboxEventRow` as aggregate-only, and add these exact rows:

```python
class OutboxDeliveryRow(Base):
    __tablename__ = "outbox_deliveries"
    __table_args__ = (
        UniqueConstraint(
            "event_log_id", "consumer_name", name="uq_outbox_delivery_event_consumer"
        ),
        CheckConstraint("attempt_count >= 0", name="ck_outbox_delivery_attempt_nonnegative"),
        Index(
            "ix_outbox_delivery_eligibility",
            "delivery_state",
            "next_attempt_at",
            "lease_expires_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    event_log_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("outbox_events.event_log_id", ondelete="CASCADE"),
        nullable=False,
    )
    consumer_name: Mapped[str] = mapped_column(String(80), nullable=False)
    delivery_state: Mapped[str] = mapped_column(String(20), nullable=False)
    lease_owner: Mapped[str | None] = mapped_column(String(80), nullable=True)
    lease_token: Mapped[str | None] = mapped_column(String(80), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    next_attempt_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error_category: Mapped[str | None] = mapped_column(String(40), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    delivered_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    dead_lettered_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)


class LocalAuditEventRow(Base):
    __tablename__ = "local_audit_events"

    event_log_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("event_log.event_id", ondelete="CASCADE"),
        primary_key=True,
    )
    event_type: Mapped[str] = mapped_column(String(120), nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(120), nullable=False)
    causation_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    project_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    workflow_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    room_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    task_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    delivered_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
```

Use `CheckConstraint` values from the closed enums for event schema version, actor/source, aggregate state, and delivery state. `OutboxEventRow` keeps `id`, unique `event_log_id`, `delivery_state`, `created_at`, `delivered_at`, and `dead_lettered_at`; it no longer owns lease or attempt fields.

- [ ] **Step 6: Add implementation-after tests and run focused checks**

Test retry values `1, 2, 4, capped`, invalid attempt zero, all Settings boundaries, event identifier maximum lengths, and exact enum values.

Run from `backend/`:

```powershell
uv run pytest tests/unit/test_outbox_policy.py tests/unit/test_event_contracts.py -q
uv run ruff check src/agent_platform/domain/events src/agent_platform/ports/event_publishing.py src/agent_platform/config/settings.py src/agent_platform/infrastructure/database/models.py tests/unit/test_outbox_policy.py tests/unit/test_event_contracts.py
uv run mypy src
```

Expected: focused tests pass; Ruff and Mypy exit 0.

- [ ] **Step 7: Commit**

```powershell
git -C .. add backend/src/agent_platform/domain/events backend/src/agent_platform/ports/event_publishing.py backend/src/agent_platform/config/settings.py backend/src/agent_platform/infrastructure/database/schema.py backend/src/agent_platform/infrastructure/database/models.py backend/tests/unit/test_outbox_policy.py backend/tests/unit/test_event_contracts.py
git -C .. commit -m "feat: define reliable outbox contracts"
```

### Task 2: Add immutable migration and deterministic legacy backfill

**Files:**
- Create: `backend/migrations/versions/0002_reliable_outbox.py`
- Modify: `backend/migrations/env.py`
- Create: `backend/tests/migration/test_reliable_outbox_migration.py`
- Modify: `backend/tests/migration/test_foundation_migration.py`

- [ ] **Step 1: Create revision `0002_reliable_outbox`**

Set `revision = RELIABLE_OUTBOX_DATABASE_REVISION` and `down_revision = FOUNDATION_DATABASE_REVISION`. Never modify `0001_foundation.py`. Upgrade in this order:

1. Before any rename or schema mutation, scan every legacy EventLog/Outbox row through a pure migration preflight validator. It must enforce the Stage 1H event-type grammar, exact identifier length/non-empty rules, aggregate bounds, dictionary JSON payload shape, parseable UTC timestamp, valid Outbox identity/relationship, at most one existing Outbox aggregate per EventLog, and every invariant required to reconstruct the future strict `EventEnvelope`. SQLite `String(N)` declarations are not treated as validation. An EventLog with no legacy Outbox is valid and is recorded for deterministic repair; an Outbox without its EventLog or any duplicate/invalid relationship is rejected. If any row is invalid, abort with one stable sanitized migration error containing counts/categories only; do not echo values, partially normalize data, or mutate the `0001` database.
2. Rename `event_log.created_at` to `occurred_at` and add nullable envelope columns.
3. Backfill every preflight-approved legacy row with `schema_version=1`, `correlation_id='legacy:event:' || event_id`, `actor_type='system'`, `actor_id=NULL`, `source='backend'`, preserving `occurred_at` and all old identifiers/payloads.
4. Rebuild `event_log` with non-null and closed-value constraints.
5. Rebuild `outbox_events` as aggregate-only, preserving every valid existing aggregate. For each EventLog that had no aggregate, insert exactly one deterministic pending aggregate with ID `out_legacy_<event_id>` and `created_at=occurred_at`; preflight must prove the generated ID cannot collide with a preserved aggregate.
6. Create `outbox_deliveries` and `local_audit_events`.
7. Insert exactly one pending `local_audit_v1` delivery for every Outbox aggregate, including deterministically repaired missing aggregates, and reset legacy aggregates to pending. Do not infer that an old generic `delivered` flag proves the new target ran.

Use SQL equivalent to:

```python
connection = op.get_bind()
connection.execute(
    sa.text(
        """
        UPDATE event_log
        SET schema_version = 1,
            correlation_id = 'legacy:event:' || CAST(event_id AS TEXT),
            actor_type = 'system',
            actor_id = NULL,
            source = 'backend'
        """
    )
)
connection.execute(
    sa.text(
        """
        INSERT INTO outbox_events (
            id, event_log_id, delivery_state, created_at
        )
        SELECT 'out_legacy_' || CAST(e.event_id AS TEXT),
               e.event_id,
               'pending',
               e.occurred_at
        FROM event_log AS e
        LEFT JOIN outbox_events AS o ON o.event_log_id = e.event_id
        WHERE o.event_log_id IS NULL
        """
    )
)
connection.execute(
    sa.text(
        """
        INSERT INTO outbox_deliveries (
            id, event_log_id, consumer_name, delivery_state,
            next_attempt_at, attempt_count, created_at
        )
        SELECT 'delivery_legacy_' || CAST(event_log_id AS TEXT),
               event_log_id,
               'local_audit_v1',
               'pending',
               created_at,
               0,
               created_at
        FROM outbox_events
        """
    )
)
```

Downgrade drops the two new tables, restores the foundation Outbox columns with safe defaults, removes new envelope columns, and renames `occurred_at` to `created_at`. Data introduced only by Stage 1H may be lost on downgrade, but the resulting schema must be a valid `0001_foundation` database and must re-upgrade cleanly.

- [ ] **Step 2: Update migration metadata coverage**

Change `_MODEL_TABLES` in `migrations/env.py` to include:

```python
_MODEL_TABLES = (
    models.EventLogRow.__table__,
    models.OutboxEventRow.__table__,
    models.OutboxDeliveryRow.__table__,
    models.LocalAuditEventRow.__table__,
)
```

- [ ] **Step 3: Add migration tests after implementation**

The new migration test must:

- upgrade a fresh database to `0001_foundation`;
- insert at least one legacy EventLog/Outbox pair directly with SQLite;
- upgrade to `head` and assert exact revision/table/column/constraint shape;
- reconstruct `EventEnvelope` values including the stable legacy correlation ID and preserved UTC timestamp;
- assert one pending `local_audit_v1` target and no fabricated audit receipt;
- insert a valid legacy EventLog without an Outbox and assert migration deterministically creates one pending `out_legacy_<event_id>` aggregate plus exactly one `local_audit_v1` target without altering the EventLog payload/timestamp;
- insert separate legacy cases with an empty/overlong entity ID, overlong or non-dotted `event_type`, non-dictionary JSON payload, invalid timestamp, overlong aggregate/Outbox ID, and broken Outbox relationship; assert each upgrade is rejected before schema mutation, the database remains at `0001_foundation`, raw values are absent from the exception, and all original rows remain byte-for-byte equivalent when read back;
- downgrade to `0001_foundation`, assert foundation shape, re-upgrade to head, and assert the target exists exactly once;
- upgrade/downgrade an empty database and run `PRAGMA foreign_key_check`.

Run:

```powershell
uv run pytest tests/migration/test_foundation_migration.py tests/migration/test_reliable_outbox_migration.py -q
uv run alembic upgrade head --sql | Out-Null
uv run ruff check migrations tests/migration
```

Expected: all migration tests pass; offline rendering and Ruff exit 0.

- [ ] **Step 4: Commit**

```powershell
git -C .. add backend/migrations backend/tests/migration
git -C .. commit -m "feat: migrate durable events and outbox targets"
```

### Task 3: Persist validated envelopes and immutable target snapshots atomically

**Files:**
- Modify: `backend/src/agent_platform/ports/unit_of_work.py`
- Modify: `backend/src/agent_platform/infrastructure/database/repositories.py`
- Modify: `backend/src/agent_platform/infrastructure/database/unit_of_work.py`
- Modify: `backend/tests/integration/test_event_unit_of_work.py`

- [ ] **Step 1: Replace loose event parameters and remove supported re-enqueue**

Use this port:

```python
class EventRepository(Protocol):
    async def append(
        self,
        *,
        envelope: EventEnvelope,
        aggregate_type: str,
        aggregate_id: str,
    ) -> int: ...


class UnitOfWork(Protocol):
    @property
    def events(self) -> EventRepository: ...
```

Remove `OutboxRepository` and `UnitOfWork.outbox`. `SqlAlchemyUnitOfWork` receives an immutable `delivery_targets` tuple at construction (defaulting to `(LOCAL_AUDIT_CONSUMER,)`) and passes it into `EventLogRepository`; callers cannot omit the reliable target or choose a per-call target set. This makes enqueueing an already persisted event unsupported after delivered aggregate cleanup; every supported enqueue occurs only while creating its EventLog row.

- [ ] **Step 2: Insert EventLog, aggregate, and targets in one session**

`EventLogRepository.__init__()` validates the configured target tuple once, rejecting an empty tuple, duplicate names, names not matching `^[a-z][a-z0-9_]{0,79}$`, and any tuple that omits `LOCAL_AUDIT_CONSUMER`. Stage 1 production wiring passes exactly `(LOCAL_AUDIT_CONSUMER,)`; the parameter remains an internal future-extension seam rather than a way for a caller to bypass the required audit target. `append()` rejects a supplied `event_id`, an empty/non-ASCII/over-80 aggregate ID, and an aggregate type that is not an ASCII lowercase token of at most 80 characters. Then persist using `self._delivery_targets`:

```python
if envelope.event_id is not None:
    raise ValueError("new events must not provide event_id")

event = EventLogRow(
    schema_version=envelope.schema_version,
    event_type=envelope.event_type,
    correlation_id=envelope.correlation_id,
    causation_id=envelope.causation_id,
    actor_type=envelope.actor.type.value,
    actor_id=envelope.actor.id,
    source=envelope.source.value,
    occurred_at=envelope.occurred_at,
    project_id=envelope.project_id,
    workflow_id=envelope.workflow_id,
    room_id=envelope.room_id,
    task_id=envelope.task_id,
    aggregate_type=aggregate_type,
    aggregate_id=aggregate_id,
    payload=deepcopy(envelope.payload),
)
self._session.add(event)
await self._session.flush()

created_at = datetime.now(UTC)
self._session.add(
    OutboxEventRow(
        id=new_id("out"),
        event_log_id=event.event_id,
        delivery_state=OutboxAggregateState.PENDING.value,
        created_at=created_at,
    )
)
for consumer_name in self._delivery_targets:
    self._session.add(
        OutboxDeliveryRow(
            id=new_id("delivery"),
            event_log_id=event.event_id,
            consumer_name=consumer_name,
            delivery_state=OutboxDeliveryState.PENDING.value,
            next_attempt_at=created_at,
            attempt_count=0,
            created_at=created_at,
        )
    )
await self._session.flush()
return event.event_id
```

Add `get(event_id) -> EventEnvelope | None` and reconstruct with `ActorRef`, `ActorType`, and `EventSource`; Pydantic strict validation is the final guard against corrupt persisted data.

- [ ] **Step 3: Add post-implementation integration coverage**

Update tests to build a complete `EventEnvelope`, construct the UoW with `(LOCAL_AUDIT_CONSUMER,)`, call `uow.events.append(...)`, commit once, and assert every field round-trips. Also prove:

- exception and no-commit paths leave zero rows in all three Outbox/Event tables;
- duplicate/empty/invalid configured targets and any tuple omitting `LOCAL_AUDIT_CONSUMER` fail before entering a transaction;
- `event_id` input is rejected;
- mutating the caller's payload after append does not mutate the stored JSON;
- there is no `uow.outbox.enqueue` supported path.

Run:

```powershell
uv run pytest tests/integration/test_event_unit_of_work.py -q
uv run ruff check src/agent_platform/ports/unit_of_work.py src/agent_platform/infrastructure/database/repositories.py src/agent_platform/infrastructure/database/unit_of_work.py tests/integration/test_event_unit_of_work.py
uv run mypy src
```

Expected: all focused tests pass; Ruff and Mypy exit 0.

- [ ] **Step 4: Commit**

```powershell
git -C .. add backend/src/agent_platform/ports/unit_of_work.py backend/src/agent_platform/infrastructure/database/repositories.py backend/src/agent_platform/infrastructure/database/unit_of_work.py backend/tests/integration/test_event_unit_of_work.py
git -C .. commit -m "feat: persist complete event envelopes atomically"
```

### Task 4: Implement lease-safe claims, recovery, retry, dead letter, and cleanup

**Files:**
- Create: `backend/src/agent_platform/infrastructure/database/outbox_store.py`
- Create: `backend/tests/integration/test_outbox_store.py`

- [ ] **Step 1: Implement conditional claim outside publish work**

Create `SqlAlchemyOutboxStore(session_factory, lease_owner, lease_seconds, max_attempts, backoff_base_seconds, backoff_max_seconds, recovery_batch_size)`. `claim_next(now)` opens one short transaction and performs candidate selection plus lease acquisition in one SQLite write statement. A deferred `SELECT` followed by `UPDATE` is forbidden because competing WAL readers can fail with `SQLITE_BUSY_SNAPSHOT` instead of observing an empty conditional update.

```python
lease_token = new_id("lease")
lease_expires_at = now + timedelta(seconds=self._lease_seconds)
candidate_id = (
    select(OutboxDeliveryRow.id)
    .where(
        OutboxDeliveryRow.delivery_state.in_(
            (OutboxDeliveryState.PENDING.value, OutboxDeliveryState.RETRY_WAIT.value)
        ),
        OutboxDeliveryRow.next_attempt_at <= now,
        OutboxDeliveryRow.attempt_count < self._max_attempts,
    )
    .order_by(
        OutboxDeliveryRow.next_attempt_at,
        OutboxDeliveryRow.created_at,
        OutboxDeliveryRow.id,
    )
    .limit(1)
    .scalar_subquery()
)
statement = (
    update(OutboxDeliveryRow)
    .where(
        OutboxDeliveryRow.id == candidate_id,
        OutboxDeliveryRow.delivery_state.in_(
            (OutboxDeliveryState.PENDING.value, OutboxDeliveryState.RETRY_WAIT.value)
        ),
        OutboxDeliveryRow.next_attempt_at <= now,
        OutboxDeliveryRow.attempt_count < self._max_attempts,
    )
    .values(
        delivery_state=OutboxDeliveryState.LEASED.value,
        lease_owner=self._lease_owner,
        lease_token=lease_token,
        lease_expires_at=lease_expires_at,
        attempt_count=OutboxDeliveryRow.attempt_count + 1,
        last_error_category=None,
    )
    .returning(
        OutboxDeliveryRow.id,
        OutboxDeliveryRow.event_log_id,
        OutboxDeliveryRow.consumer_name,
        OutboxDeliveryRow.attempt_count,
    )
)
```

If `RETURNING` yields no row, commit nothing and return no claim. Load and reconstruct the `EventEnvelope` in the same transaction, commit, and return `ClaimedDelivery`. Publishing never occurs while this transaction is open. Catch only SQLite's classified `SQLITE_BUSY`/`SQLITE_BUSY_SNAPSHOT` operational codes, roll back, and perform a small fixed number of bounded claim retries before returning no claim; never retry unknown database errors and never terminate the Dispatcher merely because another valid claimer won the write race.

- [ ] **Step 2: Implement conditional retry/dead-letter transitions**

`record_failure(claim, category, now)` must update only a row still in `leased` with the same `lease_token`. For `claim.attempt_count >= max_attempts`, set `dead_letter`, `dead_lettered_at`, clear lease fields, and refresh aggregate state. Otherwise set `retry_wait`, clear lease fields, and set:

```python
next_attempt_at = now + retry_delay(
    claim.attempt_count,
    base_seconds=self._backoff_base_seconds,
    maximum_seconds=self._backoff_max_seconds,
)
```

Store only `DeliveryErrorCategory.value`; never store exception messages, payloads, paths, or credentials. Return `False` when the token no longer owns the row.

- [ ] **Step 3: Recover expired leases and refresh aggregate state**

`recover_expired_leases(now)` reads at most `recovery_batch_size` expired leased rows, builds claims from persisted token/attempt data, and passes each through the same conditional failure path with `LEASE_EXPIRED`. Aggregate refresh rules are exact:

```text
any target dead_letter -> aggregate dead_letter
else every target delivered -> aggregate delivered with delivered_at
else -> aggregate pending with terminal timestamps cleared
```

No dead-letter EventLog or delivery row is deleted automatically.

- [ ] **Step 4: Implement delivered-only cleanup**

`cleanup_delivered(cutoff, limit)` selects aggregate IDs whose state is `delivered` and `delivered_at <= cutoff`, deletes at most `limit`, and relies on the delivery foreign key cascade. It must not delete EventLog rows, local audit rows, pending/retry/leased rows, or dead letters. Since Task 3 removed the supported re-enqueue API, removing a delivered aggregate cannot cause supported code to enqueue that historical EventLog again.

- [ ] **Step 5: Add concurrency and state-machine tests**

Tests must prove:

- two concurrent claimers cannot both own one target and neither leaks an uncaught busy/snapshot error;
- a forced classified busy path performs only the fixed bounded retry count, while an unclassified database error propagates;
- a stale lease token cannot confirm or fail a newer lease;
- attempts are bounded and backoff timestamps are exact;
- expiry becomes retry or dead letter according to the attempt bound;
- one delivered target does not complete a multi-target aggregate;
- one dead target marks the aggregate dead letter while retaining every row;
- cleanup deletes only old fully delivered aggregate/target rows and preserves EventLog/local audit/dead letters;
- database restart recovers an expired lease.

Run:

```powershell
uv run pytest tests/integration/test_outbox_store.py -q
uv run ruff check src/agent_platform/infrastructure/database/outbox_store.py tests/integration/test_outbox_store.py
uv run mypy src
```

Expected: focused tests pass; Ruff and Mypy exit 0.

- [ ] **Step 6: Commit**

```powershell
git -C .. add backend/src/agent_platform/infrastructure/database/outbox_store.py backend/tests/integration/test_outbox_store.py
git -C .. commit -m "feat: add lease safe outbox state machine"
```

### Task 5: Add transactional `local_audit_v1` and the Dispatcher

**Files:**
- Create: `backend/src/agent_platform/infrastructure/database/local_audit.py`
- Create: `backend/src/agent_platform/application/__init__.py`
- Create: `backend/src/agent_platform/application/events/__init__.py`
- Create: `backend/src/agent_platform/application/events/outbox_dispatcher.py`
- Create: `backend/tests/integration/test_local_audit_publisher.py`
- Create: `backend/tests/unit/test_outbox_dispatcher.py`

- [ ] **Step 1: Implement one-transaction local audit publication and receipt**

`LocalAuditPublisher.consumer_name` returns `LOCAL_AUDIT_CONSUMER`. Its `publish()` verifies `envelope.event_id == idempotency_key`, opens one database transaction, inserts a payload-free projection with SQLite `ON CONFLICT(event_log_id) DO NOTHING`, then conditionally marks the leased target delivered:

```python
insert_statement = sqlite_insert(LocalAuditEventRow).values(
    event_log_id=idempotency_key,
    event_type=envelope.event_type,
    correlation_id=envelope.correlation_id,
    causation_id=envelope.causation_id,
    project_id=envelope.project_id,
    workflow_id=envelope.workflow_id,
    room_id=envelope.room_id,
    task_id=envelope.task_id,
    occurred_at=envelope.occurred_at,
    delivered_at=delivered_at,
).on_conflict_do_nothing(index_elements=["event_log_id"])

confirmation = await session.execute(
    update(OutboxDeliveryRow)
    .where(
        OutboxDeliveryRow.id == delivery_id,
        OutboxDeliveryRow.event_log_id == idempotency_key,
        OutboxDeliveryRow.consumer_name == LOCAL_AUDIT_CONSUMER,
        OutboxDeliveryRow.delivery_state == OutboxDeliveryState.LEASED.value,
        OutboxDeliveryRow.lease_token == lease_token,
    )
    .values(
        delivery_state=OutboxDeliveryState.DELIVERED.value,
        lease_owner=None,
        lease_token=None,
        lease_expires_at=None,
        delivered_at=delivered_at,
        dead_lettered_at=None,
        last_error_category=None,
    )
)
if confirmation.rowcount != 1:
    raise DeliveryLeaseLostError()
await refresh_outbox_aggregate(session, idempotency_key, delivered_at)
```

Raising on a stale token rolls back the attempted audit insert and confirmation together. Retrying an already inserted event is logically idempotent because event ID is the projection primary key.

- [ ] **Step 2: Implement Dispatcher registry and loop**

`OutboxDispatcher` constructor accepts one `SqlAlchemyOutboxStore`, an iterable of `EventPublisher`, poll interval, publish timeout, cleanup interval/cutoff policy, and UTC plus monotonic clocks. Reject duplicate publisher names. Its loop recovers expired leases at startup and on every cleanup deadline, then:

```python
await self._store.recover_expired_leases(self._clock())
while not self._stop_requested.is_set():
    claim = await self._store.claim_next(self._clock())
    if claim is None:
        await self._wait_for_stop_or_timeout()
        continue

    publisher = self._publishers.get(claim.consumer_name)
    if publisher is None:
        await self._store.record_failure(
            claim, DeliveryErrorCategory.PUBLISHER_UNAVAILABLE, self._clock()
        )
        continue

    try:
        async with asyncio.timeout(self._publish_timeout_seconds):
            await publisher.publish(
                claim.envelope,
                idempotency_key=claim.event_id,
                delivery_id=claim.delivery_id,
                lease_token=claim.lease_token,
                delivered_at=self._clock(),
            )
    except asyncio.CancelledError:
        raise
    except TimeoutError:
        await self._store.record_failure(
            claim, DeliveryErrorCategory.PUBLISHER_TIMEOUT, self._clock()
        )
    except Exception:
        await self._store.record_failure(
            claim, DeliveryErrorCategory.PUBLISHER_FAILURE, self._clock()
        )
```

When the monotonic cleanup deadline is due, call `recover_expired_leases(now)` and `cleanup_delivered(now - delivered_retention, cleanup_batch_size)`, then advance the deadline by `cleanup_interval_seconds`. Cleanup is bounded and never runs inside a publish transaction.

The dispatcher exposes synchronous `request_stop()` which sets an `asyncio.Event`. Once set, it claims no new rows; a currently publishing row may finish. Cancellation leaves the lease recoverable after expiry. Missing runtime publishers retry/dead-letter their immutable target and never silently remove or deliver it.

- [ ] **Step 3: Add post-implementation publisher and loop tests**

Prove projection fields exclude payload/actor secrets, duplicate publication creates one audit row, stale-token failure creates neither side effect nor receipt, confirmation completes the one-target aggregate, missing publisher retries, publish timeout records only the stable timeout category, raw exception text is absent from storage, periodic recovery/cleanup is bounded, delivered targets are skipped, cancellation propagates, and stop prevents the next claim.

Run:

```powershell
uv run pytest tests/integration/test_local_audit_publisher.py tests/unit/test_outbox_dispatcher.py -q
uv run ruff check src/agent_platform/application src/agent_platform/infrastructure/database/local_audit.py tests/integration/test_local_audit_publisher.py tests/unit/test_outbox_dispatcher.py
uv run mypy src
```

Expected: all focused tests pass; Ruff and Mypy exit 0.

- [ ] **Step 4: Commit**

```powershell
git -C .. add backend/src/agent_platform/application backend/src/agent_platform/infrastructure/database/local_audit.py backend/tests/integration/test_local_audit_publisher.py backend/tests/unit/test_outbox_dispatcher.py
git -C .. commit -m "feat: dispatch events to transactional local audit"
```

### Task 6: Wire startup and bounded shutdown drain

**Files:**
- Modify: `backend/src/agent_platform/bootstrap/lifespan.py`
- Modify: `backend/tests/integration/test_application_lifespan.py`
- Create: `backend/tests/process/test_outbox_fail_stop.py`

- [ ] **Step 1: Construct Dispatcher after Stage 1G maintenance**

After Stage 1G creates `DatabaseMaintenance` and its task, construct:

```python
outbox_store = SqlAlchemyOutboxStore(
    database.sessions,
    lease_owner=new_id("dispatcher"),
    lease_seconds=settings.outbox_lease_seconds,
    max_attempts=settings.outbox_max_attempts,
    backoff_base_seconds=settings.outbox_backoff_base_seconds,
    backoff_max_seconds=settings.outbox_backoff_max_seconds,
    recovery_batch_size=settings.outbox_recovery_batch_size,
)
outbox_dispatcher = OutboxDispatcher(
    store=outbox_store,
    publishers=(LocalAuditPublisher(database.sessions),),
    poll_interval_seconds=settings.outbox_poll_interval_seconds,
    publish_timeout_seconds=settings.outbox_publish_timeout_seconds,
    cleanup_interval_seconds=settings.outbox_cleanup_interval_seconds,
    delivered_retention=timedelta(days=settings.outbox_delivered_retention_days),
    cleanup_batch_size=settings.outbox_cleanup_batch_size,
)
outbox_dispatcher_task = asyncio.create_task(outbox_dispatcher.run())
```

Expose `app.state.outbox_dispatcher` and `app.state.outbox_dispatcher_task` only after successful startup. Startup remains:

```text
directories -> instance lock -> secret registration -> logging -> database/probe/quick_check
-> Worker supervisor/watchdog -> database maintenance -> Outbox Dispatcher -> app state
```

- [ ] **Step 2: Add bounded drain helper**

Use shielding so both graceful drain and cancellation cleanup have explicit independent bounds. `_OUTBOX_CANCELLATION_GRACE_SECONDS` is a small fixed internal constant; it is not added to the public Settings surface. Reuse Stage 1G's internal `FatalShutdownRequired` signal and `_fatal_process_exit()` mechanism; do not create an Outbox-specific duplicate:

```python
async def _bounded_stop_outbox_dispatcher(
    dispatcher: OutboxDispatcher,
    task: asyncio.Task[None],
    timeout_seconds: float,
) -> None:
    dispatcher.request_stop()
    try:
        await asyncio.wait_for(asyncio.shield(task), timeout=timeout_seconds)
    except TimeoutError:
        cancellation_requested_by_shutdown = not task.done() and task.cancelling() == 0
        if cancellation_requested_by_shutdown:
            task.cancel()
        try:
            await asyncio.wait_for(
                asyncio.shield(task),
                timeout=_OUTBOX_CANCELLATION_GRACE_SECONDS,
            )
        except TimeoutError:
            raise FatalShutdownRequired from None
        except asyncio.CancelledError:
            if cancellation_requested_by_shutdown and task.cancelled():
                return
            raise
```

The second timeout is an invariant breach, not a recoverable cleanup error. `_shutdown_resources()` must catch `FatalShutdownRequired` before its broad `except BaseException`, re-raise it immediately, and skip every later cleanup slot. The outer lifespan uses the Stage 1G handler before primary-error preservation, sets its fail-stop flag, and calls `_fatal_process_exit()` (`os._exit(70)` in production). The outer `finally` must not clear app ownership state. If the injected test callback returns, raise a fixed `AssertionError`; tests normally inject a sentinel exception and verify it is not swallowed by any cleanup accumulator.

A task that still runs may hold a SQLite transaction or emit logs, so the Backend must not checkpoint, dispose the engine, close logging, unregister secrets, clear ownership state, or release the instance lock in-process. Production therefore performs fail-stop process termination and lets the OS release handles; the next normal startup performs Stage 1G integrity/WAL recovery and lease expiry recovery. Do not detach the task and continue cleanup. A real subprocess test proves the production callback exits within the combined drain-plus-grace deadline.

Insert it into Stage 1G `_shutdown_resources()` after cancel/await database maintenance and before `database_maintenance.final_checkpoint()`:

```text
cancel/await Worker Watchdog
-> stop Workers
-> cancel/await DatabaseMaintenance task
-> bounded drain Outbox Dispatcher
-> final WAL checkpoint
-> dispose database
-> close logging
-> close secret registration
-> release instance lock
```

Each ordinary step runs even after an earlier failure. Preserve the existing first-error rule and add only the sanitized `Additional cleanup failure occurred.` note for later failures. A first drain timeout is normal bounded recovery behavior only when shutdown itself initiated and retrieved the child-task cancellation; an already failed or already cancelling Dispatcher remains a cleanup error. The second timeout is the sole fail-stop exception to the continue-cleanup rule because later resource release would be unsafe.

- [ ] **Step 3: Extend state clearing and lifecycle tests**

Clear both Outbox state attributes on startup failure, body failure, cancellation, and every normal/recoverable exit. Tests must assert exact startup/shutdown order, successful drain, first-timeout cancellation followed by bounded task retrieval, expired-lease recoverability after cancellation, dispatcher failure remaining primary when it is first, later cleanup still running, and no task/result or app-state leakage. Add a non-cooperative cancellation case whose injected fatal callback raises a sentinel after the second deadline and proves the dedicated signal bypasses the generic error accumulator and that final checkpoint, database disposal, logging close, secret unregistration, state clearing, and instance-lock release were not attempted. In `tests/process/test_outbox_fail_stop.py`, start a purpose-built Backend subprocess with a non-cooperative Dispatcher, request shutdown, and assert the real `os._exit(70)` path completes within the combined bound, produces exit code 70, prints no traceback/raw payload/exception text, and leaves the database recoverable on the next normal startup.

Run:

```powershell
uv run pytest tests/integration/test_application_lifespan.py tests/process/test_outbox_fail_stop.py -q
uv run ruff check src/agent_platform/bootstrap/lifespan.py tests/integration/test_application_lifespan.py tests/process/test_outbox_fail_stop.py
uv run mypy src
```

Expected: focused lifecycle tests pass; Ruff and Mypy exit 0.

- [ ] **Step 4: Commit**

```powershell
git -C .. add backend/src/agent_platform/bootstrap/lifespan.py backend/tests/integration/test_application_lifespan.py backend/tests/process/test_outbox_fail_stop.py
git -C .. commit -m "feat: run outbox dispatcher in application lifespan"
```

### Task 7: Run Stage 1H regression, migration cycle, and full gate

**Files:**
- Modify only files required by failures attributable to Tasks 1–6.

- [ ] **Step 1: Run focused Stage 1H suite**

```powershell
uv run pytest tests/unit/test_outbox_policy.py tests/unit/test_outbox_dispatcher.py tests/process/test_outbox_fail_stop.py tests/integration/test_event_unit_of_work.py tests/integration/test_outbox_store.py tests/integration/test_local_audit_publisher.py tests/integration/test_application_lifespan.py tests/migration/test_foundation_migration.py tests/migration/test_reliable_outbox_migration.py -q
```

Expected: all selected tests pass with no warnings introduced by Stage 1H.

- [ ] **Step 2: Exercise real migration upgrade, rollback, and re-upgrade**

Use a disposable data root:

```powershell
$env:AGENT_PLATFORM_DATA_ROOT = Join-Path $env:TEMP "agent-platform-stage1h-migration"
uv run alembic upgrade head
uv run alembic downgrade 0001_foundation
uv run alembic upgrade head
Remove-Item Env:AGENT_PLATFORM_DATA_ROOT
```

Expected: all three Alembic commands exit 0. The migration test owns disposal of its own temporary roots; do not delete or alter the user's normal data root.

- [ ] **Step 3: Run complete backend quality gate**

```powershell
uv run ruff format --check .
uv run ruff check .
uv run mypy src
uv run pytest
```

Expected: every command exits 0; existing Stage 0 and Stage 1A–G behavior remains green.

- [ ] **Step 4: Perform plan-to-code acceptance audit**

Verify directly in code/tests that:

- every persisted row reconstructs a strict `EventEnvelope`;
- legacy backfill is deterministic and `0001_foundation.py` is byte-for-byte untouched;
- target names are snapshotted with the event transaction and runtime registry changes cannot erase them;
- publish work occurs outside claim transactions and all confirmation/failure writes match the lease token;
- retry is deterministic, attempt-bounded, dead letters survive, and cleanup touches delivered coordinator rows only;
- `local_audit_v1` is payload-free and side effect + receipt are one transaction;
- shutdown stops new claims, bounded-drains in-flight work, retrieves task results, and leaves timed-out leases recoverable;
- no WebSocket, replay endpoint, public administrative resolver, or Stage 3 target exists.

- [ ] **Step 5: Commit any gate-only corrections**

If Steps 1–4 required code changes, commit only those verified corrections:

```powershell
git -C .. add backend
git -C .. commit -m "test: close reliable outbox regression gaps"
```

If no files changed, do not create an empty commit.

---

## Stage 1H acceptance boundary

Stage 1H is complete only when the migration cycle and complete gate pass and all of these types are present with the exact roles above: `EventEnvelope`, `OutboxAggregateState`, `OutboxDeliveryState`, `DeliveryErrorCategory`, `ClaimedDelivery`, `EventPublisher`, `OutboxDeliveryRow`, `LocalAuditEventRow`, `SqlAlchemyOutboxStore`, `LocalAuditPublisher`, and `OutboxDispatcher`. The only registered immutable target is `local_audit_v1`; WebSocket delivery remains deferred to Stage 3.
