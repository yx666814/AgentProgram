import json
from datetime import UTC, datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from agent_platform.domain.contracts import (
    ArtifactRef,
    ContentHash,
    ContractId,
    ContractName,
    FrozenContractModel,
    IdempotencyKey,
    ProjectCheckpointRef,
    Stage,
    VersionedContractModel,
    require_project_relative_path,
    require_utc,
)


class _VersionedProbe(VersionedContractModel):
    resource_id: ContractId


class _ScalarProbe(FrozenContractModel):
    resource_id: ContractId
    contract_name: ContractName
    idempotency_key: IdempotencyKey


def _content_hash() -> ContentHash:
    return ContentHash(algorithm="sha256", digest="a" * 64)


def _checkpoint_data() -> dict[str, object]:
    return {
        "schema_version": 1,
        "project_id": "project_1",
        "checkpoint_id": "checkpoint_1",
        "content_hash": _content_hash(),
    }


def _artifact_data() -> dict[str, object]:
    return {
        "schema_version": 1,
        "project_id": "project_1",
        "artifact_id": "artifact_1",
        "stage": Stage.PLANNER,
        "version": 1,
        "content_hash": _content_hash(),
    }


@pytest.mark.parametrize("schema_version", [True, 1.0, "1", 2])
def test_versioned_contract_rejects_non_strict_or_unsupported_schema_version(
    schema_version: object,
) -> None:
    with pytest.raises(ValidationError):
        _VersionedProbe(schema_version=schema_version, resource_id="resource_1")


def test_versioned_contract_requires_schema_version() -> None:
    with pytest.raises(ValidationError):
        _VersionedProbe(resource_id="resource_1")


def test_contract_models_are_frozen_and_forbid_extra_fields() -> None:
    probe = _VersionedProbe(schema_version=1, resource_id="resource_1")

    with pytest.raises(ValidationError):
        probe.resource_id = "resource_2"

    with pytest.raises(ValidationError):
        _VersionedProbe.model_validate(
            {
                "schema_version": 1,
                "resource_id": "resource_1",
                "unexpected": "value",
            }
        )


def test_contract_validation_errors_hide_submitted_values() -> None:
    marker = "INVALID-CONTRACT-ID-SECRET"

    with pytest.raises(ValidationError) as error:
        _VersionedProbe(schema_version=1, resource_id=marker)

    assert marker not in str(error.value)
    assert marker not in repr(error.value)


def test_shared_contract_scalars_accept_canonical_values() -> None:
    probe = _ScalarProbe(
        resource_id="resource_1",
        contract_name="filesystem.read_project",
        idempotency_key="request-key-00000001",
    )

    assert probe.resource_id == "resource_1"
    assert probe.contract_name == "filesystem.read_project"
    assert probe.idempotency_key == "request-key-00000001"


@pytest.mark.parametrize(
    "resource_id",
    [
        "resource",
        "Resource_1",
        "resource-1",
        "resource__1",
        "1_resource",
        "référence_1",
        f"resource_{'a' * 80}",
    ],
)
def test_contract_id_rejects_noncanonical_values(resource_id: str) -> None:
    with pytest.raises(ValidationError):
        _ScalarProbe(
            resource_id=resource_id,
            contract_name="filesystem.read_project",
            idempotency_key="request-key-00000001",
        )


@pytest.mark.parametrize(
    "contract_name",
    [
        "filesystem",
        "Filesystem.read_project",
        "filesystem.Read_project",
        ".filesystem",
        "filesystem.",
        "filesystem..read_project",
        "filesystem-read_project",
        "filesystem.1read",
        "filesystem.读取",
    ],
)
def test_contract_name_rejects_noncanonical_values(contract_name: str) -> None:
    with pytest.raises(ValidationError):
        _ScalarProbe(
            resource_id="resource_1",
            contract_name=contract_name,
            idempotency_key="request-key-00000001",
        )


@pytest.mark.parametrize(
    "idempotency_key",
    [
        "too-short",
        " request-key-0001",
        "request key 0001",
        "request-key-0001/",
        "请求-key-00000001",
        "x" * 129,
    ],
)
def test_idempotency_key_rejects_invalid_values(idempotency_key: str) -> None:
    with pytest.raises(ValidationError):
        _ScalarProbe(
            resource_id="resource_1",
            contract_name="filesystem.read_project",
            idempotency_key=idempotency_key,
        )


@pytest.mark.parametrize(
    ("algorithm", "digest"),
    [
        ("sha1", "a" * 64),
        ("sha256", "A" * 64),
        ("sha256", "a" * 63),
        ("sha256", "g" * 64),
    ],
)
def test_content_hash_rejects_unknown_algorithm_or_invalid_digest(
    algorithm: str,
    digest: str,
) -> None:
    with pytest.raises(ValidationError):
        ContentHash.model_validate({"algorithm": algorithm, "digest": digest})


def test_checkpoint_reference_is_versioned_and_immutable() -> None:
    reference = ProjectCheckpointRef(**_checkpoint_data())

    assert reference.content_hash.digest == "a" * 64
    with pytest.raises(ValidationError):
        reference.checkpoint_id = "checkpoint_2"


@pytest.mark.parametrize("version", [0, -1, True, 1.0, "1"])
def test_artifact_reference_requires_positive_strict_version(version: object) -> None:
    data = _artifact_data()
    data["version"] = version

    with pytest.raises(ValidationError):
        ArtifactRef.model_validate(data)


def test_reference_models_parse_strict_wire_json() -> None:
    reference = ArtifactRef.model_validate_json(
        json.dumps(
            {
                "schema_version": 1,
                "project_id": "project_1",
                "artifact_id": "artifact_1",
                "stage": "builder",
                "version": 3,
                "content_hash": {"algorithm": "sha256", "digest": "b" * 64},
            }
        )
    )

    assert reference.stage is Stage.BUILDER
    assert reference.version == 3
    assert reference.content_hash == ContentHash(digest="b" * 64)


@pytest.mark.parametrize(
    "path",
    [
        "",
        " /outside",
        "/outside",
        "C:/outside",
        "../outside",
        "src/../outside",
        "./src/main.py",
        "src/./main.py",
        "src\\main.py",
        "src//main.py",
        "src/main.py ",
        "src/\x00main.py",
    ],
)
def test_project_relative_path_rejects_noncanonical_values(path: str) -> None:
    with pytest.raises(ValueError, match="^path must be a canonical project-relative path$"):
        require_project_relative_path(path)


def test_project_relative_path_allows_unicode_names() -> None:
    assert require_project_relative_path("文档/需求.md") == "文档/需求.md"


@pytest.mark.parametrize(
    "value",
    [datetime(2026, 7, 14), datetime(2026, 7, 14, tzinfo=timezone(timedelta(hours=8)))],
)
def test_require_utc_rejects_naive_or_non_utc_datetime(value: datetime) -> None:
    with pytest.raises(ValueError, match="^occurred_at must use UTC$"):
        require_utc(value, field_name="occurred_at")


def test_require_utc_preserves_utc_datetime() -> None:
    value = datetime(2026, 7, 14, tzinfo=UTC)

    assert require_utc(value, field_name="occurred_at") is value
