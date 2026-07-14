# Backend Stage 1B Execution Contracts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Freeze the versioned reference, idempotency, tool execution, and capability-request contracts that StageContract and later runtime services will share.

**Architecture:** Small immutable Pydantic models live in the domain contract layer and depend only on existing domain types. Shared scalar aliases enforce one identifier, capability-name, idempotency-key, hash, UTC, and project-relative-path vocabulary. This slice defines data and invariants only; it does not execute tools, grant permissions, persist idempotency records, expose APIs, or implement Git operations.

**Tech Stack:** Python 3.12, Pydantic v2, pytest, Ruff, mypy.

---

## File Map

```text
backend/src/agent_platform/domain/contracts/
|- base.py          # strict/frozen/extra-forbid versioned model base
|- scalars.py       # reusable identifier, name, key, UTC, and path validation
|- references.py    # ContentHash, ProjectCheckpointRef, ArtifactRef
|- tools.py         # ToolExecutionRequest, ToolResult, ToolFailure
|- capabilities.py  # CapabilityRequest and CapabilityRisk
`- __init__.py      # public contract exports

backend/tests/unit/test_execution_contracts.py
```

## Explicit Non-Goals

- No tool catalog, tool execution, shell process, path authorization, or permission decision.
- No idempotency database record, lock, replay cache, migration, API header, or retry loop.
- No StageContract capability calculation; StageContract consumes these types in the next slice.
- No ArtifactVersion persistence, checkpoint creation, Quality Gate, approval, or handoff behavior.
- No product Git capability, Git request type, or Git-specific field.

### Task 1: Define common contract scalars and versioned references

**Files:**
- Create: `backend/src/agent_platform/domain/contracts/base.py`
- Create: `backend/src/agent_platform/domain/contracts/scalars.py`
- Create: `backend/src/agent_platform/domain/contracts/references.py`
- Create: `backend/tests/unit/test_execution_contracts.py`
- Modify: `backend/src/agent_platform/domain/contracts/__init__.py`

- [ ] **Step 1: Write failing scalar and reference tests**

Cover:

- `VersionedContractModel` requires strict integer schema version `1`, is frozen, forbids extra fields, and hides submitted values from validation errors.
- Internal IDs are lowercase ASCII underscore-separated tokens, at most 80 characters.
- Contract names are lowercase dot-separated ASCII tokens such as `filesystem.read_project`.
- Idempotency keys are opaque printable ASCII tokens from 16 to 128 characters with no whitespace.
- `ContentHash` supports only `sha256` and exactly 64 lowercase hexadecimal characters.
- Reference versions are positive strict integers.
- `ProjectCheckpointRef` carries project/checkpoint identity and content hash.
- `ArtifactRef` carries project/artifact identity, owning `Stage`, positive version, and content hash.
- Models parse their enum/string forms from JSON but reject Python coercion, unknown fields, and mutation.

Use imports from `agent_platform.domain.contracts`; RED must be a missing export or module, not a malformed test.

Start the test module with concrete valid examples:

```python
from typing import Any

import pytest
from pydantic import ValidationError

from agent_platform.domain.contracts import (
    ArtifactRef,
    ContentHash,
    ProjectCheckpointRef,
    Stage,
)


def _content_hash() -> ContentHash:
    return ContentHash(algorithm="sha256", digest="a" * 64)


def test_checkpoint_reference_is_versioned_and_immutable() -> None:
    reference = ProjectCheckpointRef(
        schema_version=1,
        project_id="project_1",
        checkpoint_id="checkpoint_1",
        content_hash=_content_hash(),
    )

    assert reference.content_hash.digest == "a" * 64
    with pytest.raises(ValidationError):
        reference.checkpoint_id = "checkpoint_2"


def test_artifact_reference_requires_positive_version() -> None:
    with pytest.raises(ValidationError):
        ArtifactRef(
            schema_version=1,
            project_id="project_1",
            artifact_id="artifact_1",
            stage=Stage.PLANNER,
            version=0,
            content_hash=_content_hash(),
        )
```

- [ ] **Step 2: Verify RED**

Run:

```powershell
uv run pytest tests/unit/test_execution_contracts.py -v
```

Expected: collection fails because the new contract exports do not exist.

- [ ] **Step 3: Implement the strict model base and scalar vocabulary**

`base.py` defines:

```python
class FrozenContractModel(BaseModel):
    model_config = ConfigDict(
        strict=True,
        frozen=True,
        extra="forbid",
        hide_input_in_errors=True,
    )


class VersionedContractModel(FrozenContractModel):
    schema_version: Literal[1]

    @field_validator("schema_version", mode="before")
    @classmethod
    def validate_schema_version(cls, value: object) -> int:
        if type(value) is not int:
            raise ValueError("schema version must be integer 1")
        return value
```

`scalars.py` defines these annotated aliases:

```python
ContractId = Annotated[
    str,
    Field(
        min_length=3,
        max_length=80,
        pattern=r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)+$",
    ),
]
ContractName = Annotated[
    str,
    Field(
        max_length=120,
        pattern=r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+$",
    ),
]
IdempotencyKey = Annotated[
    str,
    Field(
        min_length=16,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$",
    ),
]
PositiveVersion = Annotated[int, Field(gt=0)]
```

Also define:

```python
def require_utc(value: datetime, *, field_name: str) -> datetime:
    if value.utcoffset() != timedelta(0):
        raise ValueError(f"{field_name} must use UTC")
    return value


def require_project_relative_path(value: object) -> str:
    if type(value) is not str:
        raise ValueError("path must be a canonical project-relative path")
    path = value
    parts = path.split("/")
    if (
        not path
        or path != path.strip()
        or path.startswith("/")
        or "\\" in path
        or ":" in path
        or "\x00" in path
        or any(part in {"", ".", ".."} for part in parts)
    ):
        raise ValueError("path must be a canonical project-relative path")
    return path
```

Full Windows path legality and symlink containment remain Stage 2 PathGuard responsibilities.

- [ ] **Step 4: Implement versioned reference models**

`references.py` defines:

```python
class ContentHash(FrozenContractModel):
    algorithm: Literal["sha256"] = "sha256"
    digest: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class ProjectCheckpointRef(VersionedContractModel):
    project_id: ContractId
    checkpoint_id: ContractId
    content_hash: ContentHash


class ArtifactRef(VersionedContractModel):
    project_id: ContractId
    artifact_id: ContractId
    stage: Stage
    version: PositiveVersion
    content_hash: ContentHash
```

Export the scalar aliases and reference models from `domain.contracts`.

- [ ] **Step 5: Verify GREEN and commit**

Run:

```powershell
uv run pytest tests/unit/test_execution_contracts.py -v
uv run ruff check src/agent_platform/domain/contracts tests/unit/test_execution_contracts.py
uv run mypy src
```

Expected: all reference tests pass and static checks exit 0.

Commit:

```powershell
git add backend/src/agent_platform/domain/contracts backend/tests/unit/test_execution_contracts.py
git commit -m "feat: define shared execution references"
```

### Task 2: Define tool request and result contracts

**Files:**
- Create: `backend/src/agent_platform/domain/contracts/tools.py`
- Modify: `backend/src/agent_platform/domain/contracts/__init__.py`
- Modify: `backend/tests/unit/test_execution_contracts.py`

- [ ] **Step 1: Write failing tool request tests**

Define a valid request fixture and cover:

- Explicit schema version `1`.
- Required request/correlation/project/workflow/stage-run/task IDs.
- Canonical `Stage`, `ActorRef`, tool name, required capability, and idempotency key.
- UTC-only `requested_at` and strict timeout range `1..3600` seconds.
- Strict JSON arguments, including nested values, non-finite numbers, cycles, non-string keys, and non-JSON objects.
- Frozen fields, forbidden extras, JSON wire parsing, and validation errors that do not echo invalid argument values.

RED must fail because `ToolExecutionRequest` is absent.

Use this exact valid fixture and a representative strictness test before implementation:

```python
from datetime import UTC, datetime

from agent_platform.domain.contracts import Stage, ToolExecutionRequest
from agent_platform.domain.events import ActorRef, ActorType


def _tool_request_data() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "request_id": "tool_request_1",
        "correlation_id": "correlation_1",
        "project_id": "project_1",
        "workflow_id": "workflow_1",
        "stage_run_id": "stage_run_1",
        "task_id": "task_1",
        "stage": Stage.BUILDER,
        "actor": ActorRef(type=ActorType.MODEL, id="model_1"),
        "tool_name": "filesystem.write_source",
        "required_capability": "filesystem.write_source",
        "idempotency_key": "tool-request-key-0001",
        "requested_at": datetime(2026, 7, 14, tzinfo=UTC),
        "timeout_seconds": 30,
        "arguments": {"path": "src/main.py", "content": "value"},
    }


def test_tool_execution_request_preserves_strict_json_arguments() -> None:
    request = ToolExecutionRequest(**_tool_request_data())
    assert request.arguments == {"path": "src/main.py", "content": "value"}


def test_tool_execution_request_rejects_non_json_arguments() -> None:
    data = _tool_request_data()
    data["arguments"] = {"invalid": (1, 2)}
    with pytest.raises(ValidationError):
        ToolExecutionRequest.model_validate(data)
```

- [ ] **Step 2: Implement `ToolExecutionRequest`**

```python
class ToolExecutionRequest(VersionedContractModel):
    request_id: ContractId
    correlation_id: ContractId
    causation_id: ContractId | None = None
    project_id: ContractId
    workflow_id: ContractId
    stage_run_id: ContractId
    task_id: ContractId
    stage: Stage
    actor: ActorRef
    tool_name: ContractName
    required_capability: ContractName
    idempotency_key: IdempotencyKey
    requested_at: AwareDatetime
    timeout_seconds: Annotated[int, Field(ge=1, le=3600)]
    arguments: dict[str, Any] = Field(default_factory=dict)
```

Use `require_utc` for `requested_at` and `validate_json_payload` for `arguments`.

- [ ] **Step 3: Verify request GREEN**

Run:

```powershell
uv run pytest tests/unit/test_execution_contracts.py -k tool_execution_request -v
```

Expected: request tests pass.

- [ ] **Step 4: Write failing result and failure tests**

Freeze these status values:

```text
succeeded
failed
cancelled
timed_out
```

Cover:

- `ToolFailure` has a contract-name code, `ErrorCategory`, non-empty public message, strict JSON details, and retryable flag.
- Successful results cannot carry a failure.
- Failed, cancelled, and timed-out results must carry a failure.
- `completed_at` cannot precede `started_at`; both timestamps must be UTC.
- Output is strict JSON and defaults independently.
- Request ID and idempotency key remain present for replay matching.

Run the focused test and observe RED because result types are absent.

Add concrete outcome tests before implementing the result models:

```python
from agent_platform.domain.contracts import (
    ToolExecutionStatus,
    ToolFailure,
    ToolResult,
)
from agent_platform.domain.shared.errors import ErrorCategory


def _tool_failure() -> ToolFailure:
    return ToolFailure(
        code="tool.execution_failed",
        category=ErrorCategory.CONFLICT,
        message="Tool execution failed",
        details={},
        retryable=False,
    )


def test_successful_tool_result_rejects_failure() -> None:
    with pytest.raises(ValidationError):
        ToolResult(
            schema_version=1,
            request_id="tool_request_1",
            idempotency_key="tool-request-key-0001",
            status=ToolExecutionStatus.SUCCEEDED,
            started_at=datetime(2026, 7, 14, tzinfo=UTC),
            completed_at=datetime(2026, 7, 14, 0, 0, 1, tzinfo=UTC),
            failure=_tool_failure(),
        )


@pytest.mark.parametrize(
    "status",
    [
        ToolExecutionStatus.FAILED,
        ToolExecutionStatus.CANCELLED,
        ToolExecutionStatus.TIMED_OUT,
    ],
)
def test_unsuccessful_tool_result_requires_failure(status: ToolExecutionStatus) -> None:
    with pytest.raises(ValidationError):
        ToolResult(
            schema_version=1,
            request_id="tool_request_1",
            idempotency_key="tool-request-key-0001",
            status=status,
            started_at=datetime(2026, 7, 14, tzinfo=UTC),
            completed_at=datetime(2026, 7, 14, 0, 0, 1, tzinfo=UTC),
        )
```

- [ ] **Step 5: Implement result invariants**

```python
class ToolExecutionStatus(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"


class ToolFailure(FrozenContractModel):
    code: ContractName
    category: ErrorCategory
    message: Annotated[str, Field(min_length=1, max_length=1000)]
    details: dict[str, Any] = Field(default_factory=dict)
    retryable: bool = False


class ToolResult(VersionedContractModel):
    request_id: ContractId
    idempotency_key: IdempotencyKey
    status: ToolExecutionStatus
    started_at: AwareDatetime
    completed_at: AwareDatetime
    output: dict[str, Any] = Field(default_factory=dict)
    failure: ToolFailure | None = None
```

Add validators for strict JSON, UTC timestamps, timestamp order, and status/failure consistency. Export all tool contract types.

- [ ] **Step 6: Verify tool GREEN and commit**

Run:

```powershell
uv run pytest tests/unit/test_execution_contracts.py -v
uv run ruff check src/agent_platform/domain/contracts tests/unit/test_execution_contracts.py
uv run mypy src
```

Commit:

```powershell
git add backend/src/agent_platform/domain/contracts backend/tests/unit/test_execution_contracts.py
git commit -m "feat: define tool execution contracts"
```

### Task 3: Define capability request intent

**Files:**
- Create: `backend/src/agent_platform/domain/contracts/capabilities.py`
- Modify: `backend/src/agent_platform/domain/contracts/__init__.py`
- Modify: `backend/tests/unit/test_execution_contracts.py`

- [ ] **Step 1: Write failing capability request tests**

Freeze risk values `low`, `medium`, and `high`. Cover all fields retained from the approved role-card contract:

```text
requester_role
requested_capability
reason
target_paths
proposed_command
expected_changes
risk_level
task_id
expires_after_task
```

Also require request/correlation/project/workflow/stage-run IDs, UTC `requested_at`, and an idempotency key. Test:

- `expires_after_task` is always `true` and cannot be disabled.
- Target paths are canonical project-relative strings; absolute paths, backslashes, traversal, dot segments, empty segments, surrounding whitespace, and NUL are rejected.
- Unicode project-relative names are allowed.
- `proposed_command`, when present, is a non-empty tuple of non-empty argument strings; it is intent data only and is never executed by this model.
- Empty reason or expected changes are rejected.
- Models are strict, frozen, extra-forbid, and parse valid JSON wire values.

RED must fail because `CapabilityRequest` is absent.

Use a valid request plus explicit path and expiry failures:

```python
from agent_platform.domain.contracts import CapabilityRequest, CapabilityRisk


def _capability_request_data() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "request_id": "capability_request_1",
        "correlation_id": "correlation_1",
        "project_id": "project_1",
        "workflow_id": "workflow_1",
        "stage_run_id": "stage_run_1",
        "task_id": "task_1",
        "requester_role": Stage.BUILDER,
        "requested_capability": "shell.run_project_command",
        "reason": "Run the project migration check",
        "target_paths": ("migrations/versions",),
        "proposed_command": ("python", "-m", "alembic", "check"),
        "expected_changes": "No project files should change",
        "risk_level": CapabilityRisk.MEDIUM,
        "idempotency_key": "capability-key-0001",
        "requested_at": datetime(2026, 7, 14, tzinfo=UTC),
        "expires_after_task": True,
    }


@pytest.mark.parametrize(
    "path",
    ["/outside", "C:/outside", "../outside", "src\\main.py", "src//main.py"],
)
def test_capability_request_rejects_noncanonical_target_path(path: str) -> None:
    data = _capability_request_data()
    data["target_paths"] = (path,)
    with pytest.raises(ValidationError):
        CapabilityRequest.model_validate(data)


def test_capability_request_cannot_outlive_task() -> None:
    data = _capability_request_data()
    data["expires_after_task"] = False
    with pytest.raises(ValidationError):
        CapabilityRequest.model_validate(data)
```

- [ ] **Step 2: Implement the request model**

```python
class CapabilityRisk(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class CapabilityRequest(VersionedContractModel):
    request_id: ContractId
    correlation_id: ContractId
    project_id: ContractId
    workflow_id: ContractId
    stage_run_id: ContractId
    task_id: ContractId
    requester_role: Stage
    requested_capability: ContractName
    reason: Annotated[str, Field(min_length=1, max_length=2000)]
    target_paths: tuple[str, ...] = ()
    proposed_command: Annotated[
        tuple[Annotated[str, Field(min_length=1)], ...],
        Field(min_length=1),
    ] | None = None
    expected_changes: Annotated[str, Field(min_length=1, max_length=2000)]
    risk_level: CapabilityRisk
    idempotency_key: IdempotencyKey
    requested_at: AwareDatetime
    expires_after_task: Literal[True] = True
```

Validate each target with `require_project_relative_path`, validate `requested_at` with `require_utc`, and reject duplicate target paths so UI and audit records have deterministic intent.

- [ ] **Step 3: Verify capability GREEN and commit**

Run:

```powershell
uv run pytest tests/unit/test_execution_contracts.py -v
uv run ruff check src/agent_platform/domain/contracts tests/unit/test_execution_contracts.py
uv run mypy src
```

Commit:

```powershell
git add backend/src/agent_platform/domain/contracts backend/tests/unit/test_execution_contracts.py
git commit -m "feat: define capability request contracts"
```

### Task 4: Complete compatibility verification

- [ ] **Step 1: Verify contract exports and forbidden scope**

Run:

```powershell
uv run python -c "from agent_platform.domain.contracts import ArtifactRef, CapabilityRequest, ProjectCheckpointRef, ToolExecutionRequest, ToolResult; print('execution-contracts-ok')"
rg -n "Git|git\." backend/src/agent_platform/domain/contracts
```

Expected: import prints `execution-contracts-ok`; the Git search has no matches.

- [ ] **Step 2: Run the complete backend gate**

```powershell
uv run ruff format --check .
uv run ruff check .
uv run mypy src
uv run pytest
```

Expected: all commands exit 0 with no regression to existing role, event, error, IPC, database, process, or API contracts.

- [ ] **Step 3: Review and commit plan completion**

Check `git diff --check`, dependency direction, public exports, validation error sanitization, and exact plan coverage. Commit any final compatibility-only changes as:

```powershell
git add backend/src backend/tests docs/backend/BACKEND-STAGE1B-EXECUTION-CONTRACTS-v1.md
git commit -m "test: verify execution contract compatibility"
```
