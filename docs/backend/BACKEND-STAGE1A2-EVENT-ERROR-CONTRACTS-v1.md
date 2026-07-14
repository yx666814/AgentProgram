# Backend Stage 1A2 Event and Error Contracts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Freeze a versioned event envelope and stable public error categories while preserving the existing IPC JSON and API behavior contracts.

**Architecture:** JSON-value validation moves into the shared domain foundation so IPC and events use one implementation. Immutable domain event models define actor/source/correlation metadata without changing persistence yet. DomainError gains an explicit category, and the API maps categories to stable HTTP statuses.

**Tech Stack:** Python 3.12, Pydantic v2, FastAPI, pytest, Ruff, mypy.

---

### Task 1: Share strict JSON payload validation

**Files:**
- Create: `backend/src/agent_platform/domain/shared/json_values.py`
- Modify: `backend/src/agent_platform/interfaces/ipc/messages.py`
- Test: `backend/tests/unit/test_event_contracts.py`

- [ ] **Step 1: Write failing shared-validator tests**

Test strict dictionaries, nested JSON, NaN/Infinity, cycles, non-string keys and depth limits. Import from `agent_platform.domain.shared.json_values` so RED is a missing module.

- [ ] **Step 2: Verify RED**

Run: `uv run pytest tests/unit/test_event_contracts.py -v`

Expected: missing shared JSON module.

- [ ] **Step 3: Move the existing validator without behavior changes**

Move `_ensure_json_value`, `_MAX_JSON_DEPTH`, and `validate_json_payload` from IPC messages into the shared module. IPC imports the function; existing IPC tests must remain green.

- [ ] **Step 4: Verify GREEN and IPC compatibility**

Run: `uv run pytest tests/unit/test_event_contracts.py tests/unit/test_ipc_framing.py -q`

Expected: all pass.

### Task 2: Define immutable event contracts

**Files:**
- Create: `backend/src/agent_platform/domain/events/__init__.py`
- Create: `backend/src/agent_platform/domain/events/models.py`
- Modify: `backend/tests/unit/test_event_contracts.py`

- [ ] **Step 1: Write failing EventEnvelope tests**

Cover strict schema version 1, UTC-only aware timestamps, lowercase dot-separated event types, actor/source, non-empty correlation/causation IDs, optional project/workflow/room/task IDs that default to `None`, positive persisted event IDs, immutable fields and strict JSON payloads.

- [ ] **Step 2: Implement the minimal models**

```python
class ActorType(StrEnum):
    SYSTEM = "system"
    USER = "user"
    WORKER = "worker"
    MODEL = "model"
    TOOL = "tool"


class EventSource(StrEnum):
    BACKEND = "backend"
    DESKTOP = "desktop"
    WORKER = "worker"
    MODEL = "model"
    TOOL = "tool"


class ActorRef(BaseModel):
    type: ActorType
    id: str | None = None


class EventEnvelope(BaseModel):
    schema_version: Literal[1]
    event_id: int | None = None
    event_type: str
    correlation_id: str
    causation_id: str | None = None
    actor: ActorRef
    source: EventSource
    occurred_at: AwareDatetime
    project_id: str | None = None
    workflow_id: str | None = None
    room_id: str | None = None
    task_id: str | None = None
    payload: dict[str, Any]
```

Use strict, frozen, extra-forbid config. Optional identifiers reject empty strings when supplied. Event type must be lowercase dot-separated ASCII tokens. Persisted events require a positive strict-integer `event_id`; pre-persistence envelopes may use `None`. Reject non-UTC offsets explicitly because `AwareDatetime` alone only guarantees timezone awareness.

- [ ] **Step 3: Run event tests**

Run: `uv run pytest tests/unit/test_event_contracts.py -v`

Expected: all pass.

### Task 3: Add stable DomainError categories and HTTP mapping

**Files:**
- Modify: `backend/src/agent_platform/domain/shared/errors.py`
- Modify: `backend/src/agent_platform/interfaces/api/errors.py`
- Modify: `backend/tests/unit/test_domain_shared.py`
- Modify: `backend/tests/contract/test_system_api.py`

- [ ] **Step 1: Write failing category tests**

Cover `invalid_input -> 400`, `permission -> 403`, `not_found -> 404`, `conflict -> 409`, `rate_limited -> 429`, `unavailable -> 503`. Existing DomainError construction defaults to conflict for backward compatibility.

- [ ] **Step 2: Verify RED**

Run the focused unit/API tests and confirm all new categories currently return 409.

- [ ] **Step 3: Implement the enum and mapping**

```python
class ErrorCategory(StrEnum):
    INVALID_INPUT = "invalid_input"
    PERMISSION = "permission"
    NOT_FOUND = "not_found"
    CONFLICT = "conflict"
    RATE_LIMITED = "rate_limited"
    UNAVAILABLE = "unavailable"
```

Add `category: ErrorCategory = ErrorCategory.CONFLICT` to DomainError without exposing category in the public error body. Preserve existing Exception args and pickle behavior. API mapping is an exhaustive constant dictionary.

- [ ] **Step 4: Verify GREEN**

Run focused unit and contract tests; confirm details remain sanitized and retryable remains unchanged.

### Task 4: Complete compatibility verification

- [ ] **Step 1: Run focused compatibility tests**

```powershell
uv run pytest tests/unit/test_event_contracts.py tests/unit/test_ipc_framing.py tests/unit/test_domain_shared.py tests/contract/test_system_api.py -q
```

- [ ] **Step 2: Run the full gate**

```powershell
uv run ruff format --check .
uv run ruff check .
uv run mypy src
uv run pytest
```

- [ ] **Step 3: Commit**

```powershell
git add backend/src backend/tests docs/backend/BACKEND-STAGE1A2-EVENT-ERROR-CONTRACTS-v1.md
git commit -m "feat: define event and error contracts"
```
