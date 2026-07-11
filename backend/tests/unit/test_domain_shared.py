from agent_platform.domain.shared.errors import DomainError
from agent_platform.domain.shared.ids import new_id


def test_new_id_contains_prefix_and_unique_suffix() -> None:
    first = new_id("evt")
    second = new_id("evt")

    assert first.startswith("evt_")
    assert first != second


def test_domain_error_exposes_stable_code() -> None:
    error = DomainError(code="workflow.invalid_state", message="invalid")

    assert error.code == "workflow.invalid_state"
    assert str(error) == "invalid"
