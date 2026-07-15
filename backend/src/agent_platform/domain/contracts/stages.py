from enum import StrEnum
from typing import Final


class Stage(StrEnum):
    PLANNER = "planner"
    DESIGNER = "designer"
    BUILDER = "builder"
    REVIEWER = "reviewer"
    DEPLOYER = "deployer"


STAGE_ORDER: Final[tuple[Stage, ...]] = (
    Stage.PLANNER,
    Stage.DESIGNER,
    Stage.BUILDER,
    Stage.REVIEWER,
    Stage.DEPLOYER,
)
_STAGE_INDEX: Final[dict[Stage, int]] = {stage: index for index, stage in enumerate(STAGE_ORDER)}


def predecessor(stage: Stage) -> Stage | None:
    index = _STAGE_INDEX[stage]
    return None if index == 0 else STAGE_ORDER[index - 1]


def successor(stage: Stage) -> Stage | None:
    index = _STAGE_INDEX[stage]
    return None if index == len(STAGE_ORDER) - 1 else STAGE_ORDER[index + 1]
