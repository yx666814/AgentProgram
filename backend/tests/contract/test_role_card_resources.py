import re
from hashlib import sha256

import pytest

from agent_platform.domain.contracts.stages import STAGE_ORDER, Stage
from agent_platform.domain.shared.errors import DomainError
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
