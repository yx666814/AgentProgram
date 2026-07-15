from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from agent_platform.domain.contracts import (
    GLOBAL_RUNTIME_INVARIANTS,
    PROMPT_PRECEDENCE,
    PromptLayer,
    Stage,
    get_stage_contract,
)
from agent_platform.domain.model_runtime import (
    ConversationSummary,
    ModelInvocation,
    ModelMessage,
    ModelMessageRole,
    ModelPhase,
    ModelRole,
)
from agent_platform.domain.shared.errors import DomainError, ErrorCategory
from agent_platform.domain.shared.ids import new_id
from agent_platform.domain.workflows import Message, MessageAuthor
from agent_platform.ports.role_cards import RoleCardRepository

_GLOBAL_POLICY = "\n".join(invariant.value for invariant in GLOBAL_RUNTIME_INVARIANTS)
_SUBROLE_PROMPTS = {
    (ModelRole.PRIMARY, ModelPhase.P0): (
        "Produce the strongest direct response for the current stage and user request."
    ),
    (ModelRole.REVIEWER_A, ModelPhase.P1): (
        "Review the primary draft independently. Identify concrete correctness gaps and fixes."
    ),
    (ModelRole.REVIEWER_B, ModelPhase.P1): (
        "Review the primary draft independently from a second perspective. Check omissions, "
        "risks, and internal consistency."
    ),
    (ModelRole.PRIMARY, ModelPhase.P2R): (
        "Reconcile the original draft with both independent reviews. Return only the corrected "
        "final response; do not claim a reviewer concern was handled unless it was actually fixed."
    ),
}


@dataclass(frozen=True, slots=True)
class ContextWindow:
    messages: tuple[ModelMessage, ...]
    through_sequence: int


class ContextBuilder:
    def __init__(self, *, max_characters: int, recent_message_limit: int = 64) -> None:
        if max_characters < 1000 or recent_message_limit < 1:
            raise ValueError("context limits are invalid")
        self._max_characters = max_characters
        self._recent_message_limit = recent_message_limit

    def build(
        self,
        room_id: str,
        messages: tuple[Message, ...],
        summary: ConversationSummary | None,
    ) -> ContextWindow:
        if any(message.room_id != room_id for message in messages):
            raise DomainError(
                code="context.room_isolation_violation",
                message="Context contains a message from another room",
                category=ErrorCategory.PERMISSION,
            )
        if summary is not None and summary.room_id != room_id:
            raise DomainError(
                code="context.room_isolation_violation",
                message="Context summary belongs to another room",
                category=ErrorCategory.PERMISSION,
            )
        after_sequence = summary.through_sequence if summary is not None else 0
        candidates = [message for message in messages if message.sequence > after_sequence]
        candidates = candidates[-self._recent_message_limit :]
        selected: list[Message] = []
        remaining = self._max_characters - (len(summary.content) if summary is not None else 0)
        for message in reversed(candidates):
            if selected and len(message.content) > remaining:
                break
            selected.append(message)
            remaining -= len(message.content)
            if remaining <= 0:
                break
        selected.reverse()
        context: list[ModelMessage] = []
        if summary is not None:
            context.append(
                ModelMessage(
                    role=ModelMessageRole.SYSTEM,
                    content=f"Conversation summary through message {summary.through_sequence}:\n"
                    f"{summary.content}",
                )
            )
        context.extend(_model_message(message) for message in selected)
        through = selected[-1].sequence if selected else after_sequence
        return ContextWindow(messages=tuple(context), through_sequence=through)


class RollingSummaryBuilder:
    def __init__(self, *, trigger_characters: int, max_summary_characters: int) -> None:
        if trigger_characters < 1000 or max_summary_characters < 500:
            raise ValueError("summary limits are invalid")
        self._trigger_characters = trigger_characters
        self._max_summary_characters = max_summary_characters

    def build(
        self,
        room_id: str,
        messages: tuple[Message, ...],
        current: ConversationSummary | None,
    ) -> ConversationSummary | None:
        if any(message.room_id != room_id for message in messages):
            raise DomainError(
                code="context.room_isolation_violation",
                message="Summary input contains a message from another room",
                category=ErrorCategory.PERMISSION,
            )
        after = current.through_sequence if current is not None else 0
        pending = [message for message in messages if message.sequence > after]
        if (
            len(pending) < 4
            or sum(len(message.content) for message in pending) < self._trigger_characters
        ):
            return None
        summarized = pending[:-2]
        if not summarized:
            return None
        prefix = f"Previous summary:\n{current.content}\n\n" if current is not None else ""
        lines = [
            f"[{message.sequence} {message.author.value}] {message.content}"
            for message in summarized
        ]
        content = (prefix + "\n".join(lines))[-self._max_summary_characters :].strip()
        digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
        return ConversationSummary(
            schema_version=1,
            id=new_id("summary"),
            room_id=room_id,
            through_sequence=summarized[-1].sequence,
            content=content,
            content_hash=digest,
            created_at=summarized[-1].created_at,
        )


class PromptComposer:
    def __init__(self, role_cards: RoleCardRepository) -> None:
        self._role_cards = role_cards

    def compose(
        self,
        *,
        stage: Stage,
        role: ModelRole,
        phase: ModelPhase,
        context: ContextWindow,
        instruction: str,
        runtime_state: str,
        project_instructions: tuple[str, ...] = (),
        review_material: str | None = None,
        model: str,
        max_output_tokens: int,
    ) -> tuple[ModelInvocation, str]:
        role_card = self._role_cards.load(stage, version="1.0.0")
        stage_contract = get_stage_contract(stage)
        layer_content = {
            PromptLayer.GLOBAL_CORE_POLICY: _GLOBAL_POLICY,
            PromptLayer.ROLE_CARD: role_card.content,
            PromptLayer.STAGE_CONTRACT: stage_contract.model_dump_json(),
            PromptLayer.MODEL_SUBROLE_PROMPT: _SUBROLE_PROMPTS[(role, phase)],
            PromptLayer.PROJECT_INSTRUCTIONS: "\n\n".join(project_instructions),
            PromptLayer.RUNTIME_STATE: runtime_state,
            PromptLayer.USER_MESSAGE: instruction,
            PromptLayer.PROJECT_FILE_CONTENT: "",
        }
        system_sections = [
            f"[{layer.value}]\n{layer_content[layer]}"
            for layer in PROMPT_PRECEDENCE
            if layer not in {PromptLayer.USER_MESSAGE, PromptLayer.PROJECT_FILE_CONTENT}
            and layer_content[layer]
        ]
        messages = [
            ModelMessage(
                role=ModelMessageRole.SYSTEM,
                content="\n\n".join(system_sections),
            ),
            *context.messages,
        ]
        user_content = instruction
        if review_material is not None:
            user_content = f"{instruction}\n\nMaterial to evaluate or reconcile:\n{review_material}"
        messages.append(ModelMessage(role=ModelMessageRole.USER, content=user_content))
        invocation = ModelInvocation(
            model=model,
            messages=tuple(messages),
            max_output_tokens=max_output_tokens,
        )
        canonical = json.dumps(
            invocation.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return invocation, hashlib.sha256(canonical).hexdigest()


def _model_message(message: Message) -> ModelMessage:
    role = {
        MessageAuthor.USER: ModelMessageRole.USER,
        MessageAuthor.AGENT: ModelMessageRole.ASSISTANT,
        MessageAuthor.SYSTEM: ModelMessageRole.SYSTEM,
    }[message.author]
    return ModelMessage(role=role, content=message.content)
