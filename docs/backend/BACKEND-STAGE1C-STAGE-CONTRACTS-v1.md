# Backend Stage 1C StageContract Kernel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make StageContract the authoritative executable-permission and path-ownership policy for all five stages while preserving RoleCard as model guidance.

**Architecture:** Global runtime invariants and prompt precedence are immutable domain constants. StageContract combines a stage, role-card version, lifecycle entry state, capability sets, and semantic path scopes; its methods deny unknown/permanently forbidden capabilities and validate user-approved grants. A fixed registry contains exactly one versioned contract per stage, and contract tests prove its default capabilities match the packaged role cards before the superseded `docs/roles` copies are removed.

**Tech Stack:** Python 3.12, Pydantic v2, importlib.resources-backed RoleCard loader, pytest, Ruff, mypy.

---

## File Map

```text
backend/src/agent_platform/domain/contracts/
|- runtime_policy.py       # StageRunState, prompt precedence, global invariants
|- stage_contracts.py      # capability and path policy models/calculation
|- stage_registry.py       # five immutable authoritative StageContract values
|- scalars.py              # add shared SemanticVersion alias
`- __init__.py             # public exports

backend/tests/
|- unit/test_stage_contracts.py
`- contract/test_stage_role_alignment.py

docs/
|- PROJECT-PLAN.md         # record completed role-source conversion
`- roles/                  # delete only after runtime parity tests pass
```

## Explicit Boundaries

- RoleCard content guides model behavior and remains packaged under `backend/src/agent_platform/resources/roles/v1/`.
- StageContract is the only authority for executable capability IDs and semantic path scopes.
- Capability approval does not bypass project PathGuard, task scope, command scope, or permanent prohibitions.
- Unknown capabilities are denied; the registry never uses an allow-by-default fallback.
- This slice does not execute tools, decide an individual CapabilityRequest, implement PathGuard, transition StageRun state, or create Quality Gates.
- No product Git capability or Git-dependent checkpoint rule is introduced.

### Task 1: Freeze global runtime policy and stage states

**Files:**
- Create: `backend/src/agent_platform/domain/contracts/runtime_policy.py`
- Modify: `backend/src/agent_platform/domain/contracts/__init__.py`
- Create: `backend/tests/unit/test_stage_contracts.py`

- [ ] **Step 1: Write failing runtime-policy tests**

Start with exact public imports and values:

```python
from agent_platform.domain.contracts import (
    GLOBAL_RUNTIME_INVARIANTS,
    PRIMARY_MODEL_LIMIT,
    PROMPT_PRECEDENCE,
    SECONDARY_REVIEWER_LIMIT,
    PromptLayer,
    RuntimeInvariant,
    StageRunState,
)


def test_stage_run_state_values_are_fixed() -> None:
    assert tuple(state.value for state in StageRunState) == (
        "locked",
        "ready",
        "discussing",
        "producing",
        "p2r_reviewing",
        "quality_checking",
        "waiting_approval",
        "handoff_ready",
        "completed",
        "warning_blocked",
        "needs_fix",
        "external_conflict",
        "interrupted",
        "failed",
        "cancelled",
        "abandoned",
    )


def test_prompt_precedence_is_not_reorderable() -> None:
    assert PROMPT_PRECEDENCE == (
        PromptLayer.GLOBAL_CORE_POLICY,
        PromptLayer.ROLE_CARD,
        PromptLayer.STAGE_CONTRACT,
        PromptLayer.MODEL_SUBROLE_PROMPT,
        PromptLayer.PROJECT_INSTRUCTIONS,
        PromptLayer.RUNTIME_STATE,
        PromptLayer.USER_MESSAGE,
        PromptLayer.PROJECT_FILE_CONTENT,
    )


def test_model_slot_limits_match_global_policy() -> None:
    assert PRIMARY_MODEL_LIMIT == 1
    assert SECONDARY_REVIEWER_LIMIT == 2
```

Also assert `GLOBAL_RUNTIME_INVARIANTS` contains the exact thirteen values defined below in declaration order. RED must be a missing public export.

- [ ] **Step 2: Verify RED**

Run:

```powershell
uv run pytest tests/unit/test_stage_contracts.py -v
```

Expected: collection fails because `runtime_policy` exports do not exist.

- [ ] **Step 3: Implement immutable global policy values**

```python
class StageRunState(StrEnum):
    LOCKED = "locked"
    READY = "ready"
    DISCUSSING = "discussing"
    PRODUCING = "producing"
    P2R_REVIEWING = "p2r_reviewing"
    QUALITY_CHECKING = "quality_checking"
    WAITING_APPROVAL = "waiting_approval"
    HANDOFF_READY = "handoff_ready"
    COMPLETED = "completed"
    WARNING_BLOCKED = "warning_blocked"
    NEEDS_FIX = "needs_fix"
    EXTERNAL_CONFLICT = "external_conflict"
    INTERRUPTED = "interrupted"
    FAILED = "failed"
    CANCELLED = "cancelled"
    ABANDONED = "abandoned"


class PromptLayer(StrEnum):
    GLOBAL_CORE_POLICY = "global_core_policy"
    ROLE_CARD = "role_card"
    STAGE_CONTRACT = "stage_contract"
    MODEL_SUBROLE_PROMPT = "model_subrole_prompt"
    PROJECT_INSTRUCTIONS = "project_instructions"
    RUNTIME_STATE = "runtime_state"
    USER_MESSAGE = "user_message"
    PROJECT_FILE_CONTENT = "project_file_content"


PROMPT_PRECEDENCE: Final[tuple[PromptLayer, ...]] = tuple(PromptLayer)
PRIMARY_MODEL_LIMIT: Final = 1
SECONDARY_REVIEWER_LIMIT: Final = 2
```

Define `RuntimeInvariant` and `GLOBAL_RUNTIME_INVARIANTS` in this exact order:

```text
room_context_isolated
handoff_required_to_unlock
upstream_artifacts_immutable
one_primary_two_reviewers
primary_only_tool_calls
dual_review_required
deterministic_quality_gate_required
manual_approval_by_mode
capability_approval_always_user
temporary_grants_task_scoped
forbidden_capabilities_never_grantable
orchestrator_only_completion
chat_consensus_artifact_separated
```

Export all public values from `domain.contracts`.

- [ ] **Step 4: Verify GREEN and commit**

Run:

```powershell
uv run pytest tests/unit/test_stage_contracts.py -v
uv run ruff check src/agent_platform/domain/contracts tests/unit/test_stage_contracts.py
uv run mypy src
```

Commit:

```powershell
git add backend/src/agent_platform/domain/contracts backend/tests/unit/test_stage_contracts.py
git commit -m "feat: freeze stage runtime policy"
```

### Task 2: Define StageContract capability and path calculation

**Files:**
- Modify: `backend/src/agent_platform/domain/contracts/scalars.py`
- Create: `backend/src/agent_platform/domain/contracts/stage_contracts.py`
- Modify: `backend/src/agent_platform/domain/contracts/__init__.py`
- Modify: `backend/tests/unit/test_stage_contracts.py`

- [ ] **Step 1: Write failing StageContract model tests**

Use a minimal valid contract fixture:

```python
def _stage_contract() -> StageContract:
    return StageContract(
        schema_version=1,
        contract_version="1.0.0",
        stage=Stage.PLANNER,
        role_card_version="1.0.0",
        initial_state=StageRunState.READY,
        default_capabilities=("project.search",),
        requestable_capabilities=("shell.test",),
        forbidden_capabilities=("remote.deploy",),
        path_policy=StagePathPolicy(
            read_scopes=(StagePathScope.PROJECT_NON_SENSITIVE,),
            write_scopes=(StagePathScope.PLANNER_ARTIFACT,),
            delete_scopes=(),
        ),
    )
```

Cover:

- Strict schema version and semantic versions matching `^[0-9]+\.[0-9]+\.[0-9]+$`.
- Frozen/extra-forbid models and JSON parsing.
- Unique capability entries; default/requestable may overlap for scoped escalation, but neither may overlap forbidden.
- Unique path scopes and `delete_scopes` must be a subset of `write_scopes`.
- Default capability returns `CapabilityAccess.DEFAULT`.
- Non-default requestable capability returns `CapabilityAccess.REQUIRES_APPROVAL`.
- Explicit forbidden and unknown capabilities return `CapabilityAccess.FORBIDDEN`.
- `can_request_capability()` is true only for requestable, non-forbidden IDs.
- `effective_capabilities(approved)` returns defaults plus approved requestable capabilities.
- Approval of an unknown or forbidden capability raises sanitized `DomainError` code `stage_contract.capability_not_requestable`, category `permission`, and details containing only the stage.

Representative tests:

```python
def test_unknown_capability_is_denied() -> None:
    contract = _stage_contract()
    assert contract.capability_access("unknown.capability") is CapabilityAccess.FORBIDDEN


def test_effective_capabilities_add_only_approved_requestable_values() -> None:
    contract = _stage_contract()
    assert contract.effective_capabilities({"shell.test"}) == frozenset(
        {"project.search", "shell.test"}
    )


def test_forbidden_capability_cannot_be_approved() -> None:
    with pytest.raises(DomainError) as captured:
        _stage_contract().effective_capabilities({"remote.deploy"})
    assert captured.value.code == "stage_contract.capability_not_requestable"
    assert captured.value.category is ErrorCategory.PERMISSION
    assert captured.value.details == {"stage": "planner"}
```

- [ ] **Step 2: Verify RED**

Run:

```powershell
uv run pytest tests/unit/test_stage_contracts.py -k "stage_contract or path_policy or capability" -v
```

Expected: collection fails because StageContract types are absent.

- [ ] **Step 3: Add reusable semantic version and policy enums**

Add to `scalars.py`:

```python
SemanticVersion = Annotated[
    str,
    Field(pattern=r"^[0-9]+\.[0-9]+\.[0-9]+$"),
]
```

Define:

```python
class CapabilityAccess(StrEnum):
    DEFAULT = "default"
    REQUIRES_APPROVAL = "requires_approval"
    FORBIDDEN = "forbidden"


class StagePathScope(StrEnum):
    PROJECT_NON_SENSITIVE = "project_non_sensitive"
    PLANNER_ARTIFACT = "planner_artifact"
    DESIGNER_ARTIFACT = "designer_artifact"
    BUILDER_ARTIFACT = "builder_artifact"
    REVIEWER_ARTIFACT = "reviewer_artifact"
    DEPLOYER_ARTIFACT = "deployer_artifact"
    PROJECT_SOURCE = "project_source"
    PROJECT_TEST = "project_test"
    PROJECT_BUILD_CONFIG = "project_build_config"
    GENERATED = "generated"
    DEPLOYMENT_CONFIG = "deployment_config"
    DEPLOYMENT_SCRIPT = "deployment_script"
    STAGE_DRAFT = "stage_draft"
```

- [ ] **Step 4: Implement path and capability invariants**

```python
class StagePathPolicy(FrozenContractModel):
    read_scopes: tuple[StagePathScope, ...]
    write_scopes: tuple[StagePathScope, ...]
    delete_scopes: tuple[StagePathScope, ...]


class StageContract(VersionedContractModel):
    contract_version: SemanticVersion
    stage: Stage
    role_card_version: SemanticVersion
    initial_state: StageRunState
    default_capabilities: tuple[ContractName, ...]
    requestable_capabilities: tuple[ContractName, ...]
    forbidden_capabilities: tuple[ContractName, ...]
    path_policy: StagePathPolicy
```

Use after-model validators to enforce tuple uniqueness, forbidden disjointness, and delete-scope containment. Implement:

```python
def capability_access(self, capability: str) -> CapabilityAccess: ...
def can_request_capability(self, capability: str) -> bool: ...
def effective_capabilities(self, approved: Collection[str] = ()) -> frozenset[str]: ...
```

Unknown IDs and explicit forbidden IDs are never requestable. Raise the sanitized DomainError described in Step 1 before returning an effective set containing an invalid approval.

- [ ] **Step 5: Verify GREEN and commit**

Run:

```powershell
uv run pytest tests/unit/test_stage_contracts.py -v
uv run ruff check src/agent_platform/domain/contracts tests/unit/test_stage_contracts.py
uv run mypy src
```

Commit:

```powershell
git add backend/src/agent_platform/domain/contracts backend/tests/unit/test_stage_contracts.py
git commit -m "feat: define stage contract policy"
```

### Task 3: Register all five authoritative stage contracts

**Files:**
- Create: `backend/src/agent_platform/domain/contracts/stage_registry.py`
- Modify: `backend/src/agent_platform/domain/contracts/__init__.py`
- Create: `backend/tests/contract/test_stage_role_alignment.py`

- [ ] **Step 1: Write failing registry and role-alignment tests**

Test exact registry behavior:

```python
def test_stage_contract_registry_preserves_fixed_stage_order() -> None:
    assert tuple(contract.stage for contract in load_stage_contracts()) == STAGE_ORDER


@pytest.mark.parametrize("stage", STAGE_ORDER)
def test_stage_contract_matches_packaged_role_card_defaults(stage: Stage) -> None:
    contract = get_stage_contract(stage)
    role_card = PackageRoleCardLoader().load(stage, version=contract.role_card_version)
    assert contract.default_capabilities == _extract_default_capabilities(role_card.content)
```

The test-only `_extract_default_capabilities` uses a strict regex for the `## 9. 默认能力` `Primary 默认拥有` text block, rejects a missing/duplicate block, strips blank lines, and returns the capability tuple in source order.

Also cover:

- Exactly five contracts; missing or duplicate stages are impossible.
- Every contract has schema version `1`, contract version `1.0.0`, role-card version `1.0.0`.
- Planner initial state is `ready`; all downstream stages start `locked`.
- Each role-card default capability appears exactly once.
- Representative requestable/forbidden rules match role text: Planner may request `shell.test` but never `filesystem.write_source`; Builder may request `dependency.install` but never `remote.deploy`; Reviewer never writes source; Deployer has no shell requestable capability.
- Path policies equal the exact table below.

RED must fail because registry exports are absent.

- [ ] **Step 2: Implement registry constants**

Use `MappingProxyType` for the stage lookup and expose:

```python
def get_stage_contract(stage: Stage) -> StageContract:
    return _STAGE_CONTRACTS[stage]


def load_stage_contracts() -> tuple[StageContract, ...]:
    return tuple(_STAGE_CONTRACTS[stage] for stage in STAGE_ORDER)
```

Default capabilities must exactly copy the packaged role-card blocks:

| Stage | Default capability count |
| --- | ---: |
| Planner | 10 |
| Designer | 10 |
| Builder | 21 |
| Reviewer | 16 |
| Deployer | 12 |

Use these requestable capability tuples:

```python
PLANNER_REQUESTABLE = (
    "filesystem.read_project",
    "filesystem.write_planner_artifact",
    "shell.run",
    "shell.test",
)
DESIGNER_REQUESTABLE = (
    "filesystem.read_project",
    "filesystem.write_designer_artifact",
    "shell.run",
    "shell.test",
    "dependency.inspect",
)
BUILDER_REQUESTABLE = (
    "filesystem.write_source",
    "filesystem.write_test",
    "filesystem.write_build_config",
    "filesystem.write_builder_artifact",
    "shell.run_project_command",
    "dependency.install",
)
REVIEWER_REQUESTABLE = (
    "filesystem.read_project",
    "shell.build",
    "shell.test",
    "shell.lint",
    "shell.typecheck",
    "shell.security_scan",
    "shell.run_project_command",
    "log.read_project",
)
DEPLOYER_REQUESTABLE = (
    "filesystem.read_project",
    "filesystem.write_deployment_document",
    "filesystem.write_deployment_config",
    "filesystem.write_deployment_script",
)
```

Use permanent forbidden capability tuples derived from each role card's non-requestable boundaries:

```python
PLANNER_FORBIDDEN = (
    "filesystem.write_source",
    "filesystem.delete",
    "filesystem.write_outside_project",
    "shell.build",
    "dependency.install",
    "network.request",
    "remote.deploy",
    "credential.read",
    "system.modify",
)
DESIGNER_FORBIDDEN = (
    "filesystem.write_source",
    "filesystem.modify_planner_artifact",
    "filesystem.delete",
    "filesystem.write_outside_project",
    "shell.build",
    "dependency.install",
    "network.request",
    "remote.deploy",
    "credential.read",
    "system.modify",
)
BUILDER_FORBIDDEN = (
    "filesystem.modify_planner_artifact",
    "filesystem.modify_designer_artifact",
    "filesystem.modify_reviewer_artifact",
    "filesystem.modify_deployer_artifact",
    "filesystem.write_outside_project",
    "remote.deploy",
    "system.modify",
    "credential.read",
)
REVIEWER_FORBIDDEN = (
    "filesystem.write_source",
    "filesystem.modify_upstream_artifact",
    "filesystem.delete",
    "dependency.install",
    "checkpoint.restore",
    "remote.deploy",
    "credential.read",
)
DEPLOYER_FORBIDDEN = (
    "shell.run",
    "shell.build",
    "shell.test",
    "docker.build",
    "package.build",
    "dependency.install",
    "checkpoint.restore",
    "remote.publish",
    "network.request",
    "remote.deploy",
    "credential.read",
    "filesystem.write_source",
)
```

Path scopes must equal:

| Stage | Read | Write | Delete |
| --- | --- | --- | --- |
| Planner | project, planner artifact, stage draft | planner artifact, stage draft | stage draft |
| Designer | project, planner/designer artifacts, stage draft | designer artifact, stage draft | stage draft |
| Builder | project, planner/designer/builder artifacts, source, test, build config, generated, stage draft | builder artifact, source, test, build config, generated, stage draft | builder artifact, source, test, generated, stage draft |
| Reviewer | project, planner/designer/builder/reviewer artifacts, source, test, build config, generated, stage draft | reviewer artifact, stage draft | stage draft |
| Deployer | project, all five artifacts, source, test, build config, generated, deployment config/script, stage draft | deployer artifact, deployment config/script, stage draft | stage draft |

Use enum members in registry code, not the human labels in this table.

- [ ] **Step 3: Verify registry GREEN and commit**

Run:

```powershell
uv run pytest tests/unit/test_stage_contracts.py tests/contract/test_stage_role_alignment.py -v
uv run ruff check src/agent_platform/domain/contracts tests/unit/test_stage_contracts.py tests/contract/test_stage_role_alignment.py
uv run mypy src
```

Commit:

```powershell
git add backend/src/agent_platform/domain/contracts backend/tests/unit/test_stage_contracts.py backend/tests/contract/test_stage_role_alignment.py
git commit -m "feat: register five stage contracts"
```

### Task 4: Remove superseded role source copies

**Files:**
- Delete: `docs/roles/README.md`
- Delete: `docs/roles/planner-role-card.md`
- Delete: `docs/roles/designer-role-card.md`
- Delete: `docs/roles/builder-role-card.md`
- Delete: `docs/roles/reviewer-role-card.md`
- Delete: `docs/roles/deployer-role-card.md`
- Modify: `docs/PROJECT-PLAN.md`
- Modify: `backend/tests/contract/test_stage_role_alignment.py`

- [ ] **Step 1: Prove runtime resources and code cover the retained sources**

Before deletion, run a one-time byte comparison for all five role files:

```powershell
$stages = "planner", "designer", "builder", "reviewer", "deployer"
foreach ($stage in $stages) {
    $docsHash = (Get-FileHash -Algorithm SHA256 "docs/roles/$stage-role-card.md").Hash
    $resourceHash = (Get-FileHash -Algorithm SHA256 "backend/src/agent_platform/resources/roles/v1/$stage-role-card.md").Hash
    if ($docsHash -cne $resourceHash) { throw "$stage role resource differs" }
}
```

Run the role-alignment tests proving default capabilities, versions, prompt precedence, global invariants, and registry rules are codeized.

- [ ] **Step 2: Delete originals and update the authoritative plan**

Replace the temporary-retention paragraph in `docs/PROJECT-PLAN.md` with:

```text
- `docs/roles` 原始角色卡已在阶段 1 完成代码化并删除。运行时角色资源位于 `backend/src/agent_platform/resources/roles/v1/`；StageContract、全局运行时约束和 Prompt 优先级由后端领域契约提供，后续实现不得重新创建第二份角色规格。
```

Delete the six `docs/roles` files. Do not delete packaged runtime resources.

- [ ] **Step 3: Verify no stale dependency remains and commit**

Run:

```powershell
rg -n "docs/roles" backend/src backend/tests docs/PROJECT-PLAN.md
uv run pytest tests/contract/test_role_card_resources.py tests/contract/test_stage_role_alignment.py -v
```

Expected: only the historical conversion statement in `PROJECT-PLAN.md` references `docs/roles`; all runtime/contract tests pass without source copies.

Commit:

```powershell
git add docs backend/tests/contract/test_stage_role_alignment.py
git commit -m "docs: remove converted role card sources"
```

### Task 5: Complete Stage 1C compatibility verification

- [ ] **Step 1: Verify public exports and forbidden scope**

```powershell
uv run python -c "from agent_platform.domain.contracts import StageContract, get_stage_contract, load_stage_contracts; print(len(load_stage_contracts()))"
rg -n "Git|git\." backend/src/agent_platform/domain/contracts backend/src/agent_platform/resources/roles/v1
```

Expected: import prints `5`; Git search has no matches.

- [ ] **Step 2: Run the complete backend gate**

```powershell
uv run ruff format --check .
uv run ruff check .
uv run mypy src
uv run pytest
```

- [ ] **Step 3: Review and commit compatibility-only corrections**

Review `git diff --check`, dependency direction, exact capability parity, path ownership, prompt precedence, runtime invariants, sanitized errors, and deleted-source coverage. If verification requires corrections, commit only those corrections as:

```powershell
git add backend/src backend/tests docs
git commit -m "test: verify stage contract compatibility"
```
