import json
from datetime import UTC, datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from agent_platform.domain.contracts import (
    ArtifactRef,
    CapabilityRequest,
    CapabilityRisk,
    ContentHash,
    ContractId,
    ContractName,
    FrozenContractModel,
    IdempotencyKey,
    ProjectCheckpointRef,
    Stage,
    ToolExecutionRequest,
    ToolExecutionStatus,
    ToolFailure,
    ToolResult,
    VersionedContractModel,
    require_project_relative_path,
    require_utc,
)
from agent_platform.domain.events import ActorRef, ActorType
from agent_platform.domain.shared.errors import ErrorCategory


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


def _tool_request_data() -> dict[str, object]:
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


def test_tool_execution_request_preserves_complete_execution_intent() -> None:
    request = ToolExecutionRequest(**_tool_request_data())

    assert request.schema_version == 1
    assert request.request_id == "tool_request_1"
    assert request.correlation_id == "correlation_1"
    assert request.causation_id is None
    assert request.project_id == "project_1"
    assert request.workflow_id == "workflow_1"
    assert request.stage_run_id == "stage_run_1"
    assert request.task_id == "task_1"
    assert request.stage is Stage.BUILDER
    assert request.actor == ActorRef(type=ActorType.MODEL, id="model_1")
    assert request.tool_name == "filesystem.write_source"
    assert request.required_capability == "filesystem.write_source"
    assert request.idempotency_key == "tool-request-key-0001"
    assert request.timeout_seconds == 30
    assert request.arguments == {"path": "src/main.py", "content": "value"}


def test_tool_execution_request_parses_strict_wire_json() -> None:
    request = ToolExecutionRequest.model_validate_json(
        json.dumps(
            {
                "schema_version": 1,
                "request_id": "tool_request_1",
                "correlation_id": "correlation_1",
                "causation_id": "command_1",
                "project_id": "project_1",
                "workflow_id": "workflow_1",
                "stage_run_id": "stage_run_1",
                "task_id": "task_1",
                "stage": "builder",
                "actor": {"type": "model", "id": "model_1"},
                "tool_name": "filesystem.write_source",
                "required_capability": "filesystem.write_source",
                "idempotency_key": "tool-request-key-0001",
                "requested_at": "2026-07-14T00:00:00Z",
                "timeout_seconds": 30,
                "arguments": {"path": "src/main.py"},
            }
        )
    )

    assert request.causation_id == "command_1"
    assert request.stage is Stage.BUILDER
    assert request.actor.type is ActorType.MODEL
    assert request.requested_at.utcoffset() == timedelta(0)


@pytest.mark.parametrize(
    "requested_at",
    [
        datetime(2026, 7, 14),
        datetime(2026, 7, 14, tzinfo=timezone(timedelta(hours=8))),
    ],
)
def test_tool_execution_request_rejects_non_utc_timestamp(
    requested_at: datetime,
) -> None:
    data = _tool_request_data()
    data["requested_at"] = requested_at

    with pytest.raises(ValidationError):
        ToolExecutionRequest.model_validate(data)


@pytest.mark.parametrize("timeout_seconds", [0, 3601, True, 1.0, "30"])
def test_tool_execution_request_rejects_invalid_timeout(timeout_seconds: object) -> None:
    data = _tool_request_data()
    data["timeout_seconds"] = timeout_seconds

    with pytest.raises(ValidationError):
        ToolExecutionRequest.model_validate(data)


@pytest.mark.parametrize(
    "arguments",
    [
        pytest.param({"value": float("nan")}, id="nan"),
        pytest.param({"value": float("inf")}, id="infinity"),
        pytest.param({"value": (1, 2)}, id="tuple"),
        pytest.param({1: "value"}, id="non-string-key"),
    ],
)
def test_tool_execution_request_rejects_non_json_arguments(arguments: object) -> None:
    data = _tool_request_data()
    data["arguments"] = arguments

    with pytest.raises(ValidationError):
        ToolExecutionRequest.model_validate(data)


def test_tool_execution_request_rejects_cyclic_arguments_without_leaking_input() -> None:
    marker = "TOOL-ARGUMENT-SECRET"
    arguments: dict[str, object] = {"marker": marker}
    arguments["cycle"] = arguments
    data = _tool_request_data()
    data["arguments"] = arguments

    with pytest.raises(ValidationError) as error:
        ToolExecutionRequest.model_validate(data)

    assert marker not in str(error.value)
    assert marker not in repr(error.value)


def test_tool_execution_request_defaults_are_independent_and_fields_are_frozen() -> None:
    first_data = _tool_request_data()
    second_data = _tool_request_data()
    del first_data["arguments"]
    del second_data["arguments"]
    first = ToolExecutionRequest(**first_data)
    second = ToolExecutionRequest(**second_data)

    first.arguments["changed"] = True

    assert second.arguments == {}
    with pytest.raises(ValidationError):
        first.tool_name = "filesystem.read_project"


def test_tool_execution_request_forbids_extra_fields() -> None:
    data = _tool_request_data()
    data["unexpected"] = "value"

    with pytest.raises(ValidationError):
        ToolExecutionRequest.model_validate(data)


def _tool_failure() -> ToolFailure:
    return ToolFailure(
        code="tool.execution_failed",
        category=ErrorCategory.CONFLICT,
        message="Tool execution failed",
        details={"phase": "write"},
        retryable=False,
    )


def _tool_result_data() -> dict[str, object]:
    return {
        "schema_version": 1,
        "request_id": "tool_request_1",
        "idempotency_key": "tool-request-key-0001",
        "status": ToolExecutionStatus.SUCCEEDED,
        "started_at": datetime(2026, 7, 14, tzinfo=UTC),
        "completed_at": datetime(2026, 7, 14, 0, 0, 1, tzinfo=UTC),
        "output": {"changed_paths": ["src/main.py"]},
    }


def test_tool_execution_status_values_are_stable() -> None:
    assert {status.value for status in ToolExecutionStatus} == {
        "succeeded",
        "failed",
        "cancelled",
        "timed_out",
    }


def test_tool_failure_preserves_structured_public_error() -> None:
    failure = _tool_failure()

    assert failure.code == "tool.execution_failed"
    assert failure.category is ErrorCategory.CONFLICT
    assert failure.message == "Tool execution failed"
    assert failure.details == {"phase": "write"}
    assert failure.retryable is False


def test_tool_failure_rejects_empty_message_and_non_json_details() -> None:
    with pytest.raises(ValidationError):
        ToolFailure(
            code="tool.execution_failed",
            category=ErrorCategory.CONFLICT,
            message="",
        )

    marker = "TOOL-FAILURE-DETAIL-SECRET"
    with pytest.raises(ValidationError) as error:
        ToolFailure(
            code="tool.execution_failed",
            category=ErrorCategory.CONFLICT,
            message="Tool execution failed",
            details={"invalid": (marker,)},
        )

    assert marker not in str(error.value)
    assert marker not in repr(error.value)


def test_successful_tool_result_preserves_output_without_failure() -> None:
    result = ToolResult(**_tool_result_data())

    assert result.status is ToolExecutionStatus.SUCCEEDED
    assert result.output == {"changed_paths": ["src/main.py"]}
    assert result.failure is None


def test_successful_tool_result_rejects_failure() -> None:
    data = _tool_result_data()
    data["failure"] = _tool_failure()

    with pytest.raises(ValidationError):
        ToolResult.model_validate(data)


@pytest.mark.parametrize(
    "status",
    [
        ToolExecutionStatus.FAILED,
        ToolExecutionStatus.CANCELLED,
        ToolExecutionStatus.TIMED_OUT,
    ],
)
def test_unsuccessful_tool_result_requires_failure(status: ToolExecutionStatus) -> None:
    data = _tool_result_data()
    data["status"] = status

    with pytest.raises(ValidationError):
        ToolResult.model_validate(data)


@pytest.mark.parametrize(
    "status",
    [
        ToolExecutionStatus.FAILED,
        ToolExecutionStatus.CANCELLED,
        ToolExecutionStatus.TIMED_OUT,
    ],
)
def test_unsuccessful_tool_result_accepts_structured_failure(
    status: ToolExecutionStatus,
) -> None:
    data = _tool_result_data()
    data["status"] = status
    data["failure"] = _tool_failure()

    result = ToolResult.model_validate(data)

    assert result.status is status
    assert result.failure == _tool_failure()


@pytest.mark.parametrize("field", ["started_at", "completed_at"])
def test_tool_result_rejects_non_utc_timestamps(field: str) -> None:
    data = _tool_result_data()
    data[field] = datetime(2026, 7, 14, tzinfo=timezone(timedelta(hours=8)))

    with pytest.raises(ValidationError):
        ToolResult.model_validate(data)


def test_tool_result_rejects_completion_before_start() -> None:
    data = _tool_result_data()
    data["completed_at"] = datetime(2026, 7, 13, 23, 59, 59, tzinfo=UTC)

    with pytest.raises(ValidationError):
        ToolResult.model_validate(data)


def test_tool_result_rejects_non_json_output() -> None:
    data = _tool_result_data()
    data["output"] = {"invalid": (1, 2)}

    with pytest.raises(ValidationError):
        ToolResult.model_validate(data)


def test_tool_result_parses_strict_wire_json() -> None:
    result = ToolResult.model_validate_json(
        json.dumps(
            {
                "schema_version": 1,
                "request_id": "tool_request_1",
                "idempotency_key": "tool-request-key-0001",
                "status": "failed",
                "started_at": "2026-07-14T00:00:00Z",
                "completed_at": "2026-07-14T00:00:01Z",
                "output": {},
                "failure": {
                    "code": "tool.execution_failed",
                    "category": "unavailable",
                    "message": "Tool execution failed",
                    "details": {},
                    "retryable": True,
                },
            }
        )
    )

    assert result.status is ToolExecutionStatus.FAILED
    assert result.failure is not None
    assert result.failure.category is ErrorCategory.UNAVAILABLE
    assert result.failure.retryable is True


def test_tool_result_output_defaults_are_independent_and_fields_are_frozen() -> None:
    first_data = _tool_result_data()
    second_data = _tool_result_data()
    del first_data["output"]
    del second_data["output"]
    first = ToolResult(**first_data)
    second = ToolResult(**second_data)

    first.output["changed"] = True

    assert second.output == {}
    with pytest.raises(ValidationError):
        first.status = ToolExecutionStatus.FAILED


def _capability_request_data() -> dict[str, object]:
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


def test_capability_risk_values_are_stable() -> None:
    assert {risk.value for risk in CapabilityRisk} == {"low", "medium", "high"}


def test_capability_request_preserves_complete_bounded_intent() -> None:
    request = CapabilityRequest(**_capability_request_data())

    assert request.requester_role is Stage.BUILDER
    assert request.requested_capability == "shell.run_project_command"
    assert request.reason == "Run the project migration check"
    assert request.target_paths == ("migrations/versions",)
    assert request.proposed_command == ("python", "-m", "alembic", "check")
    assert request.expected_changes == "No project files should change"
    assert request.risk_level is CapabilityRisk.MEDIUM
    assert request.expires_after_task is True


def test_capability_request_parses_strict_wire_json() -> None:
    request = CapabilityRequest.model_validate_json(
        json.dumps(
            {
                "schema_version": 1,
                "request_id": "capability_request_1",
                "correlation_id": "correlation_1",
                "project_id": "project_1",
                "workflow_id": "workflow_1",
                "stage_run_id": "stage_run_1",
                "task_id": "task_1",
                "requester_role": "reviewer",
                "requested_capability": "shell.security_scan",
                "reason": "Run the registered security scanner",
                "target_paths": ["src", "tests/安全"],
                "proposed_command": ["scanner", "--project", "."],
                "expected_changes": "Only a report should be created",
                "risk_level": "low",
                "idempotency_key": "capability-key-0001",
                "requested_at": "2026-07-14T00:00:00Z",
                "expires_after_task": True,
            }
        )
    )

    assert request.requester_role is Stage.REVIEWER
    assert request.risk_level is CapabilityRisk.LOW
    assert request.target_paths == ("src", "tests/安全")
    assert request.proposed_command == ("scanner", "--project", ".")
    assert request.requested_at.utcoffset() == timedelta(0)


@pytest.mark.parametrize(
    "path",
    [
        "",
        "/outside",
        "C:/outside",
        "../outside",
        "src/../outside",
        "./src/main.py",
        "src\\main.py",
        "src//main.py",
        "src/main.py ",
        "src/\x00main.py",
    ],
)
def test_capability_request_rejects_noncanonical_target_path(path: str) -> None:
    data = _capability_request_data()
    data["target_paths"] = (path,)

    with pytest.raises(ValidationError):
        CapabilityRequest.model_validate(data)


def test_capability_request_rejects_duplicate_target_paths() -> None:
    data = _capability_request_data()
    data["target_paths"] = ("src", "src")

    with pytest.raises(ValidationError):
        CapabilityRequest.model_validate(data)


def test_capability_request_allows_unicode_project_relative_paths() -> None:
    data = _capability_request_data()
    data["target_paths"] = ("文档/需求.md",)

    request = CapabilityRequest.model_validate(data)

    assert request.target_paths == ("文档/需求.md",)


@pytest.mark.parametrize(
    "proposed_command",
    [(), ("",), ["python", "-V"], "python -V"],
)
def test_capability_request_rejects_invalid_command_intent(
    proposed_command: object,
) -> None:
    data = _capability_request_data()
    data["proposed_command"] = proposed_command

    with pytest.raises(ValidationError):
        CapabilityRequest.model_validate(data)


@pytest.mark.parametrize("field", ["reason", "expected_changes"])
@pytest.mark.parametrize("value", ["", "   "])
def test_capability_request_rejects_blank_explanation_fields(
    field: str,
    value: str,
) -> None:
    data = _capability_request_data()
    data[field] = value

    with pytest.raises(ValidationError):
        CapabilityRequest.model_validate(data)


@pytest.mark.parametrize("expires_after_task", [False, 1, "true"])
def test_capability_request_cannot_outlive_task(expires_after_task: object) -> None:
    data = _capability_request_data()
    data["expires_after_task"] = expires_after_task

    with pytest.raises(ValidationError):
        CapabilityRequest.model_validate(data)


def test_capability_request_rejects_non_utc_timestamp() -> None:
    data = _capability_request_data()
    data["requested_at"] = datetime(
        2026,
        7,
        14,
        tzinfo=timezone(timedelta(hours=8)),
    )

    with pytest.raises(ValidationError):
        CapabilityRequest.model_validate(data)


def test_capability_request_defaults_are_bounded_and_fields_are_frozen() -> None:
    data = _capability_request_data()
    del data["target_paths"]
    del data["proposed_command"]
    del data["expires_after_task"]
    request = CapabilityRequest(**data)

    assert request.target_paths == ()
    assert request.proposed_command is None
    assert request.expires_after_task is True
    with pytest.raises(ValidationError):
        request.risk_level = CapabilityRisk.HIGH


def test_capability_request_forbids_extra_fields() -> None:
    data = _capability_request_data()
    data["approved"] = True

    with pytest.raises(ValidationError):
        CapabilityRequest.model_validate(data)
