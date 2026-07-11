import pickle
import re

import pytest

from agent_platform.domain.shared.errors import DomainError
from agent_platform.domain.shared.ids import new_id


def test_new_id_contains_prefix_and_unique_suffix() -> None:
    first = new_id("evt")
    second = new_id("evt")

    assert first.startswith("evt_")
    assert first != second


def test_new_id_normalizes_prefix_and_has_lowercase_hex_suffix() -> None:
    generated = new_id("EVT")

    assert re.fullmatch(r"evt_[0-9a-f]{32}", generated) is not None


def test_new_id_accepts_alphanumeric_prefix() -> None:
    assert new_id("stage2").startswith("stage2_")


@pytest.mark.parametrize(
    "prefix",
    [
        "",
        "   ",
        "_",
        "evt_id",
        "ev t",
        "ev\nt",
        "evt/path",
        "evt\\path",
        "evt-",
        "evt!",
        "événement",
        "事件",
        "2stage",
    ],
)
def test_new_id_rejects_invalid_prefix_tokens(prefix: str) -> None:
    with pytest.raises(ValueError):
        new_id(prefix)


def test_domain_error_exposes_stable_code() -> None:
    error = DomainError(code="workflow.invalid_state", message="invalid")

    assert error.code == "workflow.invalid_state"
    assert str(error) == "invalid"


def test_domain_error_initializes_exception_args() -> None:
    details = {"state": "x"}
    error = DomainError(
        code="workflow.invalid_state",
        message="invalid",
        details=details,
        retryable=True,
    )

    assert error.args == ("workflow.invalid_state", "invalid", details, True)


def test_domain_error_round_trips_through_pickle() -> None:
    error = DomainError(
        code="workflow.invalid_state",
        message="invalid",
        details={"state": "x"},
        retryable=True,
    )

    restored = pickle.loads(pickle.dumps(error))

    assert restored.code == "workflow.invalid_state"
    assert restored.message == "invalid"
    assert restored.details == {"state": "x"}
    assert restored.retryable is True
    assert str(restored) == "invalid"
