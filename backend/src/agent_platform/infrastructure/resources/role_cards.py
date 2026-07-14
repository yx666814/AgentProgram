from __future__ import annotations

import re
from hashlib import sha256
from importlib.resources import files
from typing import Final, Literal, cast

from pydantic import ValidationError

from agent_platform.domain.contracts.role_cards import RoleCard
from agent_platform.domain.contracts.stages import STAGE_ORDER, Stage
from agent_platform.domain.shared.errors import DomainError

_ROLE_CARD_VERSION: Final = "1.0.0"
_ROLE_CARD_PACKAGE: Final = "agent_platform.resources.roles.v1"
_METADATA_PATTERN: Final = re.compile(
    r"^## 1\. 元数据\r?\n\r?\n```text\r?\n(?P<body>.*?)\r?\n```",
    flags=re.MULTILINE | re.DOTALL,
)
_EXPECTED_METADATA_KEYS: Final = frozenset(
    {"role_id", "stage_id", "display_name", "role_card_version", "language"}
)


class PackageRoleCardLoader:
    def __init__(self, package: str = _ROLE_CARD_PACKAGE) -> None:
        self._package = package

    def load(self, stage: Stage, *, version: str) -> RoleCard:
        if version != _ROLE_CARD_VERSION:
            raise DomainError(
                code="role_card.version_not_found",
                message="Role card version is not available",
                details={"stage": stage.value, "version": version},
            )

        try:
            raw_content = files(self._package).joinpath(f"{stage.value}-role-card.md").read_bytes()
            content = raw_content.decode("utf-8", errors="strict")
            metadata = _parse_metadata(content)
            role_id = Stage(metadata["role_id"])
            stage_id = Stage(metadata["stage_id"])
            if role_id is not stage or stage_id is not stage:
                raise ValueError("role card stage metadata does not match requested stage")
            language = metadata["language"]
            if language != "zh-CN":
                raise ValueError("role card language is not supported")
            return RoleCard(
                schema_version=1,
                role_id=role_id,
                stage_id=stage_id,
                display_name=metadata["display_name"],
                role_card_version=metadata["role_card_version"],
                language=cast(Literal["zh-CN"], language),
                content=content,
                content_hash=sha256(raw_content).hexdigest(),
            )
        except DomainError:
            raise
        except (KeyError, OSError, UnicodeError, ValueError, ValidationError) as exc:
            raise DomainError(
                code="role_card.resource_invalid",
                message="Role card resource is invalid",
                details={"stage": stage.value, "version": version},
            ) from exc

    def load_all(self, *, version: str = _ROLE_CARD_VERSION) -> tuple[RoleCard, ...]:
        return tuple(self.load(stage, version=version) for stage in STAGE_ORDER)


def _parse_metadata(content: str) -> dict[str, str]:
    matched = _METADATA_PATTERN.search(content)
    if matched is None:
        raise ValueError("role card metadata block is missing")

    metadata: dict[str, str] = {}
    for line in matched.group("body").splitlines():
        key, separator, value = line.partition(":")
        key = key.strip()
        value = value.strip()
        if separator == "" or not key or not value or key in metadata:
            raise ValueError("role card metadata is malformed")
        metadata[key] = value

    if metadata.keys() != _EXPECTED_METADATA_KEYS:
        raise ValueError("role card metadata keys are invalid")
    return metadata
