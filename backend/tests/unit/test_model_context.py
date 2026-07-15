from datetime import UTC, datetime

import pytest

from agent_platform.application.model_runtime import ContextBuilder, RollingSummaryBuilder
from agent_platform.domain.shared.errors import DomainError
from agent_platform.domain.workflows import Message, MessageAuthor, MessageKind


def _message(room_id: str, sequence: int, content: str) -> Message:
    return Message(
        schema_version=1,
        id=f"message_{sequence}",
        room_id=room_id,
        sequence=sequence,
        author=MessageAuthor.USER,
        kind=MessageKind.DISCUSSION,
        content=content,
        created_at=datetime.now(UTC),
    )


def test_context_builder_keeps_room_messages_isolated_and_ordered() -> None:
    builder = ContextBuilder(max_characters=10_000)

    context = builder.build(
        "room_one",
        (_message("room_one", 1, "first"), _message("room_one", 2, "second")),
        None,
    )

    assert [message.content for message in context.messages] == ["first", "second"]
    assert context.through_sequence == 2


def test_context_builder_rejects_cross_room_content() -> None:
    builder = ContextBuilder(max_characters=10_000)

    with pytest.raises(DomainError, match="another room"):
        builder.build("room_one", (_message("room_two", 1, "leak"),), None)


def test_rolling_summary_preserves_recent_messages_as_unsummarized_context() -> None:
    messages = tuple(
        _message("room_one", sequence, f"message-{sequence}-" + "x" * 400)
        for sequence in range(1, 7)
    )
    summary = RollingSummaryBuilder(
        trigger_characters=1000,
        max_summary_characters=800,
    ).build("room_one", messages, None)

    assert summary is not None
    assert summary.through_sequence == 4
    context = ContextBuilder(max_characters=5000).build("room_one", messages, summary)
    assert context.messages[0].role.value == "system"
    assert [message.content[:9] for message in context.messages[1:]] == [
        "message-5",
        "message-6",
    ]
