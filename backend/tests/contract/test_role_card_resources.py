import re
from hashlib import sha256
from pathlib import Path

import pytest

from agent_platform.domain.contracts.stages import STAGE_ORDER, Stage
from agent_platform.domain.shared.errors import DomainError
from agent_platform.infrastructure.resources import role_cards as role_card_module
from agent_platform.infrastructure.resources.role_cards import PackageRoleCardLoader

EXPECTED_DISPLAY_NAMES = {
    Stage.PLANNER: "策划者",
    Stage.DESIGNER: "设计者",
    Stage.BUILDER: "构建者",
    Stage.REVIEWER: "审查者",
    Stage.DEPLOYER: "部署准备者",
}


@pytest.mark.parametrize("stage", STAGE_ORDER)
def test_every_role_card_loads_with_verified_metadata(stage: Stage) -> None:
    card = PackageRoleCardLoader().load(stage, version="1.0.0")

    assert card.schema_version == 1
    assert card.role_id is stage
    assert card.stage_id is stage
    assert card.display_name == EXPECTED_DISPLAY_NAMES[stage]
    assert card.role_card_version == "1.0.0"
    assert card.language == "zh-CN"
    assert card.content_hash == sha256(card.content.encode("utf-8")).hexdigest()
    assert re.search(r"(?im)^\s*git\.", card.content) is None
    assert re.search(r"\bGit\b", card.content) is None
    assert "P2R" in card.content
    assert "Quality Gate" in card.content
    assert "CapabilityRequest" in card.content


def test_load_all_preserves_fixed_stage_order() -> None:
    cards = PackageRoleCardLoader().load_all()

    assert tuple(card.stage_id for card in cards) == STAGE_ORDER


def test_unknown_role_card_version_has_stable_error() -> None:
    with pytest.raises(DomainError) as captured:
        PackageRoleCardLoader().load(Stage.PLANNER, version="2.0.0")

    assert captured.value.code == "role_card.version_not_found"
    assert captured.value.details == {"stage": "planner", "version": "2.0.0"}
    assert captured.value.retryable is False


def write_role_resource(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    content: bytes,
) -> PackageRoleCardLoader:
    (tmp_path / "planner-role-card.md").write_bytes(content)
    monkeypatch.setattr(role_card_module, "files", lambda _: tmp_path)
    return PackageRoleCardLoader(package="tests.role_cards")


def role_resource_bytes(*, version: str = "1.0.0", extra_metadata: str = "") -> bytes:
    return (
        "# Planner 角色卡\n\n"
        "## 1. 元数据\n\n"
        "```text\n"
        "role_id: planner\n"
        "stage_id: planner\n"
        "display_name: 策划者\n"
        f"role_card_version: {version}\n"
        "language: zh-CN\n"
        f"{extra_metadata}"
        "```\n\n"
        "P2R Quality Gate CapabilityRequest\n"
    ).encode()


def test_resource_metadata_version_must_match_requested_version(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    loader = write_role_resource(
        tmp_path,
        monkeypatch,
        role_resource_bytes(version="1.1.0"),
    )

    with pytest.raises(DomainError) as captured:
        loader.load(Stage.PLANNER, version="1.0.0")

    assert captured.value.code == "role_card.resource_invalid"
    assert captured.value.details == {"stage": "planner", "version": "1.0.0"}


@pytest.mark.parametrize(
    "content",
    [
        b"\xff",
        b"# no metadata",
        role_resource_bytes(extra_metadata="unknown: value\n"),
        role_resource_bytes(extra_metadata="role_id: planner\n"),
    ],
)
def test_malformed_resource_has_sanitized_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    content: bytes,
) -> None:
    loader = write_role_resource(tmp_path, monkeypatch, content)

    with pytest.raises(DomainError) as captured:
        loader.load(Stage.PLANNER, version="1.0.0")

    assert captured.value.code == "role_card.resource_invalid"
    assert captured.value.details == {"stage": "planner", "version": "1.0.0"}
    assert str(tmp_path) not in str(captured.value)


def test_missing_resource_has_sanitized_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(role_card_module, "files", lambda _: tmp_path)

    with pytest.raises(DomainError) as captured:
        PackageRoleCardLoader(package="tests.role_cards").load(
            Stage.PLANNER,
            version="1.0.0",
        )

    assert captured.value.code == "role_card.resource_invalid"
    assert str(tmp_path) not in str(captured.value)
