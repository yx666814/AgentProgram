import json
from datetime import UTC, datetime, timedelta, timezone
from typing import Any

import pytest
from pydantic import ValidationError

from agent_platform.domain.events import ActorRef, ActorType, EventEnvelope, EventSource
from agent_platform.domain.shared.json_values import validate_json_payload


def _nested_payload(depth: int) -> dict[str, Any]:
    root: dict[str, Any] = {}
    current = root
    for _ in range(depth):
        child: dict[str, Any] = {}
        current["nested"] = child
        current = child
    current["value"] = "leaf"
    return root


def test_json_payload_validator_preserves_strict_nested_json() -> None:
    payload = {
        "none": None,
        "boolean": True,
        "integer": 7,
        "float": 2.5,
        "string": "value",
        "list": [None, False, 3, 4.5, "nested", {"items": [1, 2]}],
    }

    assert validate_json_payload(payload) is payload


@pytest.mark.parametrize(
    "value",
    [
        pytest.param(None, id="none"),
        pytest.param([], id="list"),
        pytest.param("value", id="string"),
    ],
)
def test_json_payload_validator_requires_a_dictionary(value: object) -> None:
    with pytest.raises(ValueError, match="^payload must contain only JSON values$"):
        validate_json_payload(value)


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param({"value": float("nan")}, id="nan"),
        pytest.param({"value": float("inf")}, id="positive-infinity"),
        pytest.param({"value": float("-inf")}, id="negative-infinity"),
        pytest.param({1: "value"}, id="non-string-root-key"),
        pytest.param({"nested": {1: "value"}}, id="non-string-nested-key"),
    ],
)
def test_json_payload_validator_rejects_non_json_values(payload: object) -> None:
    with pytest.raises(ValueError, match="^payload must contain only JSON values$"):
        validate_json_payload(payload)


@pytest.mark.parametrize("cycle_kind", ["dict", "list"])
def test_json_payload_validator_rejects_cycles(cycle_kind: str) -> None:
    if cycle_kind == "dict":
        payload: dict[str, Any] = {}
        payload["cycle"] = payload
    else:
        cyclic_list: list[Any] = []
        cyclic_list.append(cyclic_list)
        payload = {"cycle": cyclic_list}

    with pytest.raises(ValueError, match="^payload must contain only JSON values$"):
        validate_json_payload(payload)


def test_json_payload_validator_enforces_depth_limit_without_recursion_error() -> None:
    assert validate_json_payload(_nested_payload(63))

    with pytest.raises(ValueError, match="^payload must contain only JSON values$"):
        validate_json_payload(_nested_payload(64))


def _event_data() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "event_type": "workflow.started",
        "correlation_id": "correlation_1",
        "actor": ActorRef(type=ActorType.SYSTEM),
        "source": EventSource.BACKEND,
        "occurred_at": datetime(2026, 7, 14, tzinfo=UTC),
        "payload": {"stage": "planner"},
    }


def test_event_actor_and_source_values_are_stable() -> None:
    assert {actor_type.value for actor_type in ActorType} == {
        "system",
        "user",
        "worker",
        "model",
        "tool",
    }
    assert {source.value for source in EventSource} == {
        "backend",
        "desktop",
        "worker",
        "model",
        "tool",
    }


def test_event_envelope_has_explicit_version_and_optional_identifier_defaults() -> None:
    event = EventEnvelope(**_event_data())

    assert event.schema_version == 1
    assert event.event_id is None
    assert event.causation_id is None
    assert event.project_id is None
    assert event.workflow_id is None
    assert event.room_id is None
    assert event.task_id is None


def test_event_envelope_parses_strict_wire_json() -> None:
    event = EventEnvelope.model_validate_json(
        json.dumps(
            {
                "schema_version": 1,
                "event_id": 7,
                "event_type": "stage_run.completed",
                "correlation_id": "correlation_1",
                "causation_id": "command_1",
                "actor": {"type": "worker", "id": "worker_1"},
                "source": "worker",
                "occurred_at": "2026-07-14T00:00:00Z",
                "project_id": "project_1",
                "workflow_id": "workflow_1",
                "room_id": "room_1",
                "task_id": "task_1",
                "payload": {"result": "completed"},
            }
        )
    )

    assert event.event_id == 7
    assert event.actor == ActorRef(type=ActorType.WORKER, id="worker_1")
    assert event.source is EventSource.WORKER
    assert event.occurred_at.utcoffset() == timedelta(0)


@pytest.mark.parametrize("schema_version", [True, 1.0, "1", 2])
def test_event_envelope_rejects_non_strict_or_unsupported_schema_version(
    schema_version: object,
) -> None:
    data = _event_data()
    data["schema_version"] = schema_version

    with pytest.raises(ValidationError):
        EventEnvelope.model_validate(data)


def test_event_envelope_requires_schema_version() -> None:
    data = _event_data()
    del data["schema_version"]

    with pytest.raises(ValidationError):
        EventEnvelope.model_validate(data)


@pytest.mark.parametrize("event_id", [0, -1, True, 1.0, "1"])
def test_event_envelope_rejects_invalid_persisted_event_id(event_id: object) -> None:
    data = _event_data()
    data["event_id"] = event_id

    with pytest.raises(ValidationError):
        EventEnvelope.model_validate(data)


@pytest.mark.parametrize(
    "event_type",
    [
        "workflow",
        "Workflow.started",
        "workflow.Started",
        ".workflow",
        "workflow.",
        "workflow..started",
        "workflow-started",
        "workflow.1started",
        "workflow.已开始",
    ],
)
def test_event_envelope_rejects_invalid_event_type(event_type: str) -> None:
    data = _event_data()
    data["event_type"] = event_type

    with pytest.raises(ValidationError):
        EventEnvelope.model_validate(data)


@pytest.mark.parametrize(
    "field",
    [
        "correlation_id",
        "causation_id",
        "project_id",
        "workflow_id",
        "room_id",
        "task_id",
    ],
)
def test_event_envelope_rejects_empty_identifiers(field: str) -> None:
    data = _event_data()
    data[field] = ""

    with pytest.raises(ValidationError):
        EventEnvelope.model_validate(data)


def test_actor_reference_rejects_empty_id_and_extra_fields() -> None:
    with pytest.raises(ValidationError):
        ActorRef(type=ActorType.USER, id="")

    with pytest.raises(ValidationError):
        ActorRef.model_validate({"type": ActorType.USER, "unexpected": "value"})


@pytest.mark.parametrize(
    "occurred_at",
    [
        datetime(2026, 7, 14),
        datetime(2026, 7, 14, tzinfo=timezone(timedelta(hours=1))),
    ],
)
def test_event_envelope_rejects_non_utc_timestamps(occurred_at: datetime) -> None:
    data = _event_data()
    data["occurred_at"] = occurred_at

    with pytest.raises(ValidationError):
        EventEnvelope.model_validate(data)


def test_event_envelope_rejects_non_json_payload() -> None:
    data = _event_data()
    data["payload"] = {"invalid": (1, 2)}

    with pytest.raises(ValidationError):
        EventEnvelope.model_validate(data)


def test_event_models_are_frozen_and_reject_extra_fields() -> None:
    actor = ActorRef(type=ActorType.SYSTEM)
    event = EventEnvelope(**_event_data())

    with pytest.raises(ValidationError):
        actor.id = "system_1"
    with pytest.raises(ValidationError):
        event.event_type = "workflow.completed"

    data = _event_data()
    data["unexpected"] = "value"
    with pytest.raises(ValidationError):
        EventEnvelope.model_validate(data)
