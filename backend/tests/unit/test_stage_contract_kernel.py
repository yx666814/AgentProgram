import pytest
from pydantic import ValidationError

from agent_platform.domain.contracts.role_cards import RoleCard
from agent_platform.domain.contracts.stages import STAGE_ORDER, Stage, predecessor, successor


def make_role_card(
    *,
    role_id: Stage = Stage.PLANNER,
    stage_id: Stage = Stage.PLANNER,
) -> RoleCard:
    return RoleCard(
        schema_version=1,
        role_id=role_id,
        stage_id=stage_id,
        display_name="策划者",
        role_card_version="1.0.0",
        language="zh-CN",
        content="# Planner 角色卡",
        content_hash="a" * 64,
    )


def test_stage_order_is_fixed() -> None:
    assert STAGE_ORDER == (
        Stage.PLANNER,
        Stage.DESIGNER,
        Stage.BUILDER,
        Stage.REVIEWER,
        Stage.DEPLOYER,
    )


@pytest.mark.parametrize(
    ("stage", "expected_predecessor", "expected_successor"),
    [
        (Stage.PLANNER, None, Stage.DESIGNER),
        (Stage.DESIGNER, Stage.PLANNER, Stage.BUILDER),
        (Stage.BUILDER, Stage.DESIGNER, Stage.REVIEWER),
        (Stage.REVIEWER, Stage.BUILDER, Stage.DEPLOYER),
        (Stage.DEPLOYER, Stage.REVIEWER, None),
    ],
)
def test_stage_neighbors_follow_fixed_order(
    stage: Stage,
    expected_predecessor: Stage | None,
    expected_successor: Stage | None,
) -> None:
    assert predecessor(stage) is expected_predecessor
    assert successor(stage) is expected_successor


def test_role_card_requires_matching_role_and_stage() -> None:
    with pytest.raises(ValidationError):
        make_role_card(role_id=Stage.PLANNER, stage_id=Stage.BUILDER)


def test_role_card_is_immutable() -> None:
    card = make_role_card()

    with pytest.raises(ValidationError):
        card.display_name = "changed"


@pytest.mark.parametrize(
    ("version", "content_hash"),
    [
        ("1", "a" * 64),
        ("1.0", "a" * 64),
        ("v1.0.0", "a" * 64),
        ("1.0.0", "A" * 64),
        ("1.0.0", "a" * 63),
    ],
)
def test_role_card_rejects_invalid_version_or_hash(version: str, content_hash: str) -> None:
    with pytest.raises(ValidationError):
        RoleCard(
            schema_version=1,
            role_id=Stage.PLANNER,
            stage_id=Stage.PLANNER,
            display_name="策划者",
            role_card_version=version,
            language="zh-CN",
            content="# Planner 角色卡",
            content_hash=content_hash,
        )
