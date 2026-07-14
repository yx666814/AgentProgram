# Backend Stage 1A Role Contract Kernel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the canonical five-stage enum and package the approved role cards as versioned, hashed backend runtime resources without introducing product Git capabilities.

**Architecture:** Domain models define stage order and immutable role-card metadata. A port exposes role-card lookup, while an infrastructure loader reads UTF-8 Markdown resources through `importlib.resources`, validates metadata, and returns a content hash. StageContract remains the future authority for executable permissions; RoleCard content guides model behavior only.

**Tech Stack:** Python 3.12, Pydantic v2, importlib.resources, hashlib, pytest, Ruff, mypy.

---

## File Map

```text
backend/src/agent_platform/
├─ domain/contracts/{__init__.py,stages.py,role_cards.py}
├─ ports/role_cards.py
├─ infrastructure/resources/{__init__.py,role_cards.py}
└─ resources/roles/v1/{__init__.py,*-role-card.md}

backend/tests/
├─ unit/test_stage_contract_kernel.py
└─ contract/test_role_card_resources.py
```

### Task 1: Normalize the retained role-card sources

**Files:**
- Modify: `docs/roles/planner-role-card.md`
- Modify: `docs/roles/designer-role-card.md`
- Modify: `docs/roles/builder-role-card.md`
- Modify: `docs/roles/reviewer-role-card.md`
- Modify: `docs/roles/deployer-role-card.md`

- [ ] **Step 1: Replace product Git inputs and capabilities**

Use non-Git equivalents:

```text
Git status/diff/history -> workspace change summary / checkpoint history
git.inspect_*           -> project.inspect_changes / checkpoint.inspect_history
git.create_checkpoint   -> checkpoint.create
git.commit/git.push     -> permanently absent from V1 capabilities
```

- [ ] **Step 2: Verify all retained cards follow the V1 boundary**

Run:

```powershell
rg -n "Git|git\." docs/roles
```

Expected: no matches.

### Task 2: Define the canonical stage and role-card models

**Files:**
- Create: `backend/src/agent_platform/domain/contracts/__init__.py`
- Create: `backend/src/agent_platform/domain/contracts/stages.py`
- Create: `backend/src/agent_platform/domain/contracts/role_cards.py`
- Test: `backend/tests/unit/test_stage_contract_kernel.py`

- [ ] **Step 1: Write failing stage-order and role-card validation tests**

```python
def test_stage_order_is_fixed() -> None:
    assert STAGE_ORDER == (
        Stage.PLANNER,
        Stage.DESIGNER,
        Stage.BUILDER,
        Stage.REVIEWER,
        Stage.DEPLOYER,
    )


def test_role_card_requires_matching_role_and_stage() -> None:
    with pytest.raises(ValidationError):
        make_role_card(role_id=Stage.PLANNER, stage_id=Stage.BUILDER)
```

- [ ] **Step 2: Run the tests and verify RED**

Run:

```powershell
uv run pytest tests/unit/test_stage_contract_kernel.py -v
```

Expected: collection fails because `agent_platform.domain.contracts` does not exist.

- [ ] **Step 3: Implement immutable domain models**

```python
class Stage(StrEnum):
    PLANNER = "planner"
    DESIGNER = "designer"
    BUILDER = "builder"
    REVIEWER = "reviewer"
    DEPLOYER = "deployer"


STAGE_ORDER: Final[tuple[Stage, ...]] = tuple(Stage)


class RoleCard(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    role_id: Stage
    stage_id: Stage
    display_name: Annotated[str, Field(min_length=1)]
    role_card_version: Annotated[str, Field(pattern=r"^[0-9]+\.[0-9]+\.[0-9]+$")]
    language: Literal["zh-CN"]
    content: Annotated[str, Field(min_length=1)]
    content_hash: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
```

Add a model validator that rejects `role_id != stage_id`. Add `predecessor(stage)` and `successor(stage)` helpers that return `None` at the boundaries.

- [ ] **Step 4: Run unit tests and verify GREEN**

Run:

```powershell
uv run pytest tests/unit/test_stage_contract_kernel.py -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit the domain kernel**

```powershell
git add backend/src/agent_platform/domain/contracts backend/tests/unit/test_stage_contract_kernel.py
git commit -m "feat: define stage and role card contracts"
```

### Task 3: Package and load the five role cards

**Files:**
- Create: `backend/src/agent_platform/ports/role_cards.py`
- Create: `backend/src/agent_platform/infrastructure/resources/__init__.py`
- Create: `backend/src/agent_platform/infrastructure/resources/role_cards.py`
- Create: `backend/src/agent_platform/resources/__init__.py`
- Create: `backend/src/agent_platform/resources/roles/__init__.py`
- Create: `backend/src/agent_platform/resources/roles/v1/__init__.py`
- Create: `backend/src/agent_platform/resources/roles/v1/planner-role-card.md`
- Create: `backend/src/agent_platform/resources/roles/v1/designer-role-card.md`
- Create: `backend/src/agent_platform/resources/roles/v1/builder-role-card.md`
- Create: `backend/src/agent_platform/resources/roles/v1/reviewer-role-card.md`
- Create: `backend/src/agent_platform/resources/roles/v1/deployer-role-card.md`
- Test: `backend/tests/contract/test_role_card_resources.py`

- [ ] **Step 1: Write failing loader contract tests**

```python
@pytest.mark.parametrize("stage", STAGE_ORDER)
def test_every_role_card_loads_with_hash(stage: Stage) -> None:
    card = PackageRoleCardLoader().load(stage, version="1.0.0")
    assert card.role_id is stage
    assert card.stage_id is stage
    assert len(card.content_hash) == 64
    assert re.search(r"(?im)^\s*git\.", card.content) is None
    assert re.search(r"\bGit\b", card.content) is None


def test_load_all_preserves_stage_order() -> None:
    assert tuple(card.stage_id for card in PackageRoleCardLoader().load_all()) == STAGE_ORDER
```

- [ ] **Step 2: Run the tests and verify RED**

Run:

```powershell
uv run pytest tests/contract/test_role_card_resources.py -v
```

Expected: collection fails because the loader and package resources do not exist.

- [ ] **Step 3: Define the port and loader**

```python
class RoleCardRepository(Protocol):
    def load(self, stage: Stage, *, version: str) -> RoleCard: ...
    def load_all(self, *, version: str = "1.0.0") -> tuple[RoleCard, ...]: ...
```

`PackageRoleCardLoader` must:

- Read from `agent_platform.resources.roles.v1` with `importlib.resources.files`.
- Decode UTF-8 strictly.
- Parse the five metadata keys from the first `## 1. 元数据` fenced block; `schema_version` is fixed by the packaged loader.
- Reject missing, duplicate, or unknown metadata keys.
- Verify `role_id == stage_id == requested stage` and the requested version.
- Hash the exact packaged bytes with SHA-256.
- Raise sanitized `DomainError` codes without leaking filesystem paths.

- [ ] **Step 4: Copy the normalized role resources into the package**

Copy the five retained Markdown role cards byte-for-byte after Task 1 normalization. The package resources become runtime inputs; `docs/roles` remain until StageContract integration confirms full coverage.

- [ ] **Step 5: Run loader tests and verify GREEN**

Run:

```powershell
uv run pytest tests/contract/test_role_card_resources.py -v
```

Expected: five resources load, hashes are stable, stage order is fixed, and no product Git capability remains.

- [ ] **Step 6: Commit the loader and resources**

```powershell
git add docs/roles backend/src/agent_platform/ports/role_cards.py backend/src/agent_platform/infrastructure/resources backend/src/agent_platform/resources backend/tests/contract/test_role_card_resources.py
git commit -m "feat: package versioned role card resources"
```

### Task 4: Verify package inclusion and compatibility

**Files:**
- Modify: `backend/tests/contract/test_role_card_resources.py`

- [ ] **Step 1: Add resource integrity and failure tests**

Cover invalid version, missing resource, malformed metadata, UTF-8 failure, role/stage mismatch, unknown metadata, and deterministic SHA-256. Use temporary package fixtures only for malformed-resource cases; production code receives no test-only methods.

- [ ] **Step 2: Build the wheel and inspect packaged resources**

Run:

```powershell
uv build
uv run python -m zipfile -l dist\agent_platform_backend-0.1.0-py3-none-any.whl | Select-String "resources/roles/v1"
```

Expected: all five Markdown resources and package markers are present.

- [ ] **Step 3: Run the complete backend gate**

```powershell
uv run ruff format --check .
uv run ruff check .
uv run mypy src
uv run pytest
```

Expected: all commands exit 0 and the existing 295-test baseline has no regression.

- [ ] **Step 4: Commit final compatibility coverage**

```powershell
git add backend/tests/contract/test_role_card_resources.py
git commit -m "test: verify packaged role card compatibility"
```
