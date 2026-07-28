from __future__ import annotations

import asyncio
import json
import os
import stat
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from agent_platform.application.model_runtime.context import (
    ContextBuilder,
    ContextWindow,
    PromptComposer,
    RollingSummaryBuilder,
)
from agent_platform.config.settings import Settings
from agent_platform.domain.contracts import Stage, StageRunState
from agent_platform.domain.events import ActorRef, ActorType, EventEnvelope, EventSource
from agent_platform.domain.model_runtime import (
    AgentRun,
    AgentRunSnapshot,
    AgentRunStatus,
    AgentStreamFrame,
    ModelCall,
    ModelCallStatus,
    ModelPhase,
    ModelProfile,
    ModelRole,
    RoomModelAssignment,
    StreamFrameType,
    UsageRecord,
)
from agent_platform.domain.shared.errors import DomainError, ErrorCategory
from agent_platform.domain.shared.ids import new_id
from agent_platform.domain.workflows import Message, MessageAuthor, MessageKind, RoomStatus
from agent_platform.infrastructure.async_cleanup import await_cancellation_resistant
from agent_platform.infrastructure.database.session import Database
from agent_platform.infrastructure.database.unit_of_work import SqlAlchemyUnitOfWork
from agent_platform.infrastructure.model_runtime import ModelOutputStore, StoredModelOutput
from agent_platform.infrastructure.projects.paths import validate_direct_workspace_root
from agent_platform.ports.event_publishing import LOCAL_AUDIT_CONSUMER, WEBSOCKET_CONSUMER
from agent_platform.ports.model_runtime import ModelAdapter, ModelAdapterError
from agent_platform.ports.secrets import SecretStore

_WINDOWS_REPARSE_POINT = 0x400


@dataclass(frozen=True, slots=True)
class RunCreation:
    run: AgentRun
    created: bool


@dataclass(slots=True)
class _CallOutcome:
    call: ModelCall | None = None
    output: StoredModelOutput | None = None
    content: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    error_code: str | None = None


class AgentRunRegistry:
    def __init__(self) -> None:
        self._cancellations: dict[str, asyncio.Event] = {}
        self._lock = asyncio.Lock()

    async def register(self, run_id: str) -> asyncio.Event:
        async with self._lock:
            if run_id in self._cancellations:
                raise DomainError(
                    code="agent_run.already_executing",
                    message="Agent run is already executing",
                    category=ErrorCategory.CONFLICT,
                )
            cancellation = asyncio.Event()
            self._cancellations[run_id] = cancellation
            return cancellation

    async def cancel(self, run_id: str) -> bool:
        async with self._lock:
            cancellation = self._cancellations.get(run_id)
            if cancellation is None:
                return False
            cancellation.set()
            return True

    async def unregister(self, run_id: str) -> None:
        async with self._lock:
            self._cancellations.pop(run_id, None)


class AgentRuntimeService:
    def __init__(
        self,
        database: Database,
        settings: Settings,
        secret_store: SecretStore,
        adapters: tuple[ModelAdapter, ...],
        output_store: ModelOutputStore,
        prompt_composer: PromptComposer,
        context_builder: ContextBuilder,
        summary_builder: RollingSummaryBuilder,
        registry: AgentRunRegistry,
    ) -> None:
        self._database = database
        self._settings = settings
        self._secret_store = secret_store
        self._adapters = {adapter.provider: adapter for adapter in adapters}
        if len(self._adapters) != len(adapters):
            raise ValueError("model adapter providers must be unique")
        self._output_store = output_store
        self._prompt_composer = prompt_composer
        self._context_builder = context_builder
        self._summary_builder = summary_builder
        self._registry = registry

    async def create_run(
        self,
        room_id: str,
        *,
        request_key: str,
        formal: bool,
        correlation_id: str,
    ) -> RunCreation:
        now = datetime.now(UTC)
        async with self._write_uow() as uow:
            existing = await uow.model_runtime.get_run_by_request(room_id, request_key)
            if existing is not None:
                if existing.formal != formal:
                    raise DomainError(
                        code="agent_run.idempotency_conflict",
                        message="Request key was already used with different parameters",
                        category=ErrorCategory.CONFLICT,
                    )
                return RunCreation(run=existing, created=False)
            active = await uow.model_runtime.find_active_run_for_room(room_id)
            if active is not None:
                raise DomainError(
                    code="agent_run.room_busy",
                    message="Room already has an active agent run",
                    category=ErrorCategory.CONFLICT,
                    details={"agent_run_id": active.id},
                )
            room = await uow.workflows.get_room(room_id)
            if room is None:
                raise _not_found("room", "Room was not found")
            workflow = await uow.workflows.get(room.workflow_id)
            run = await uow.workflows.get_stage_run(room.stage_run_id)
            current = await uow.workflows.get_current_stage_run(room.workflow_id, room.stage)
            if workflow is None or run is None:
                raise RuntimeError("room workflow graph is incomplete")
            if (
                room.status is not RoomStatus.ACTIVE
                or current is None
                or current.id != run.id
                or run.state
                not in {
                    StageRunState.DISCUSSING,
                    StageRunState.PRODUCING,
                    StageRunState.P2R_REVIEWING,
                }
            ):
                raise DomainError(
                    code="agent_run.room_not_active",
                    message="Agent runs require the active current stage room",
                    category=ErrorCategory.CONFLICT,
                )
            assignment = await uow.model_runtime.get_assignment(room_id)
            if assignment is None:
                raise DomainError(
                    code="agent_run.assignment_required",
                    message="Room model assignment is required",
                    category=ErrorCategory.CONFLICT,
                )
            if formal and (
                assignment.reviewer_a_profile_id is None or assignment.reviewer_b_profile_id is None
            ):
                raise DomainError(
                    code="agent_run.dual_review_required",
                    message="Formal runs require Reviewer A and Reviewer B",
                    category=ErrorCategory.CONFLICT,
                )
            agent_run = AgentRun(
                schema_version=1,
                id=new_id("agentrun"),
                workflow_id=workflow.id,
                room_id=room_id,
                request_key=request_key,
                formal=formal,
                status=AgentRunStatus.PENDING,
                version=1,
                created_at=now,
            )
            await uow.model_runtime.add_run(agent_run)
            await _append_event(
                uow,
                event_type="agent_run.created",
                correlation_id=correlation_id,
                occurred_at=now,
                project_id=workflow.project_id,
                workflow_id=workflow.id,
                room_id=room_id,
                payload={"agent_run_id": agent_run.id, "formal": formal},
                actor_type=ActorType.USER,
                source=EventSource.BACKEND,
            )
            await uow.commit()
        return RunCreation(run=agent_run, created=True)

    async def get_run(self, run_id: str) -> AgentRunSnapshot:
        async with SqlAlchemyUnitOfWork(self._database.sessions) as uow:
            snapshot = await uow.model_runtime.get_snapshot(run_id)
        if snapshot is None:
            raise _not_found("agent_run", "Agent run was not found")
        return snapshot

    async def list_runs(self, room_id: str) -> tuple[AgentRun, ...]:
        async with SqlAlchemyUnitOfWork(self._database.sessions) as uow:
            if await uow.workflows.get_room(room_id) is None:
                raise _not_found("room", "Room was not found")
            return await uow.model_runtime.list_runs(room_id)

    async def get_output(self, run_id: str) -> str:
        async with SqlAlchemyUnitOfWork(self._database.sessions) as uow:
            run = await uow.model_runtime.get_run(run_id)
        if run is None:
            raise _not_found("agent_run", "Agent run was not found")
        if run.final_output_ref is None or run.final_output_hash is None:
            raise DomainError(
                code="agent_run.output_not_available",
                message="Agent run output is not available",
                category=ErrorCategory.NOT_FOUND,
            )
        return await asyncio.to_thread(
            self._output_store.read,
            run.final_output_ref,
            run.final_output_hash,
        )

    async def cancel_run(self, run_id: str) -> AgentRun:
        if await self._registry.cancel(run_id):
            async with SqlAlchemyUnitOfWork(self._database.sessions) as uow:
                run = await uow.model_runtime.get_run(run_id)
            if run is None:
                raise _not_found("agent_run", "Agent run was not found")
            return run
        async with self._write_uow() as uow:
            run = await uow.model_runtime.get_run(run_id)
            if run is None:
                raise _not_found("agent_run", "Agent run was not found")
            if run.status is not AgentRunStatus.PENDING:
                raise DomainError(
                    code="agent_run.not_cancellable",
                    message="Agent run is not cancellable",
                    category=ErrorCategory.CONFLICT,
                )
            cancelled = await uow.model_runtime.update_run(
                run_id,
                AgentRunStatus.CANCELLED,
                expected_version=run.version,
                completed_at=datetime.now(UTC),
                error_code="agent_run.cancelled",
            )
            await uow.commit()
        return cancelled

    async def stream_run(
        self,
        run_id: str,
        *,
        instruction: str,
        correlation_id: str,
        execution_contract: str | None = None,
        project_file_content: str = "",
    ) -> AsyncIterator[AgentStreamFrame]:
        cancellation = await self._registry.register(run_id)
        sequence = 0
        try:
            (
                run,
                assignment,
                profiles,
                context,
                project_instructions,
                stage,
            ) = await self._prepare_run(
                run_id,
                instruction=instruction,
                correlation_id=correlation_id,
            )
            sequence += 1
            yield AgentStreamFrame(
                type=StreamFrameType.RUN_STARTED,
                run_id=run_id,
                sequence=sequence,
                status=AgentRunStatus.RUNNING,
            )
            primary = profiles[assignment.primary_profile_id]
            p0 = _CallOutcome()
            async for frame in self._stream_call(
                run,
                primary,
                ModelRole.PRIMARY,
                ModelPhase.P0,
                stage=stage,
                context=context,
                instruction=instruction,
                runtime_state=_runtime_state("primary_initial_draft", execution_contract),
                project_instructions=project_instructions,
                project_file_content=project_file_content,
                review_material=None,
                cancellation=cancellation,
                starting_sequence=sequence,
                outcome=p0,
            ):
                sequence = frame.sequence
                yield frame
            if p0.content is None:
                final = await self._finish_run_failure(
                    run_id,
                    error_code=p0.error_code or "agent_run.primary_failed",
                    correlation_id=correlation_id,
                )
                sequence += 1
                yield _run_completed_frame(final, sequence)
                return

            reviews: list[tuple[ModelRole, _CallOutcome]] = []
            for role, profile_id in (
                (ModelRole.REVIEWER_A, assignment.reviewer_a_profile_id),
                (ModelRole.REVIEWER_B, assignment.reviewer_b_profile_id),
            ):
                if profile_id is None:
                    continue
                outcome = _CallOutcome()
                async for frame in self._stream_call(
                    run,
                    profiles[profile_id],
                    role,
                    ModelPhase.P1,
                    stage=stage,
                    context=context,
                    instruction=instruction,
                    runtime_state=_runtime_state("independent_review", execution_contract),
                    project_instructions=project_instructions,
                    project_file_content=project_file_content,
                    review_material=p0.content,
                    cancellation=cancellation,
                    starting_sequence=sequence,
                    outcome=outcome,
                ):
                    sequence = frame.sequence
                    yield frame
                reviews.append((role, outcome))

            failed_reviews = [outcome for _, outcome in reviews if outcome.content is None]
            if run.formal and failed_reviews:
                final = await self._finish_run(
                    run_id,
                    status=AgentRunStatus.PARTIAL_FAILURE,
                    output=p0.output,
                    error_code="agent_run.reviewer_failed",
                    correlation_id=correlation_id,
                )
                sequence += 1
                yield _run_completed_frame(final, sequence)
                return

            successful_reviews = [
                {"role": role.value, "review": outcome.content}
                for role, outcome in reviews
                if outcome.content is not None
            ]
            final_output = p0.output
            final_content = p0.content
            if successful_reviews:
                material = json.dumps(
                    {"draft": p0.content, "reviews": successful_reviews},
                    ensure_ascii=False,
                    sort_keys=True,
                )
                p2r = _CallOutcome()
                async for frame in self._stream_call(
                    run,
                    primary,
                    ModelRole.PRIMARY,
                    ModelPhase.P2R,
                    stage=stage,
                    context=context,
                    instruction=instruction,
                    runtime_state=_runtime_state("review_reconciliation", execution_contract),
                    project_instructions=project_instructions,
                    project_file_content=project_file_content,
                    review_material=material,
                    cancellation=cancellation,
                    starting_sequence=sequence,
                    outcome=p2r,
                ):
                    sequence = frame.sequence
                    yield frame
                if p2r.content is None:
                    final = await self._finish_run(
                        run_id,
                        status=AgentRunStatus.PARTIAL_FAILURE,
                        output=p0.output,
                        error_code=p2r.error_code or "agent_run.reconciliation_failed",
                        correlation_id=correlation_id,
                    )
                    sequence += 1
                    yield _run_completed_frame(final, sequence)
                    return
                final_output = p2r.output
                final_content = p2r.content

            if final_output is None or final_content is None:
                raise RuntimeError("successful pipeline output is missing")
            status = AgentRunStatus.PARTIAL_FAILURE if failed_reviews else AgentRunStatus.SUCCEEDED
            final = await self._finish_run(
                run_id,
                status=status,
                output=final_output,
                error_code="agent_run.reviewer_failed" if failed_reviews else None,
                correlation_id=correlation_id,
                append_content=final_content,
            )
            sequence += 1
            yield _run_completed_frame(final, sequence)
        except asyncio.CancelledError:
            cancellation.set()
            await await_cancellation_resistant(
                self._finish_run_cancelled(run_id, correlation_id=correlation_id)
            )
            raise
        except DomainError as error:
            final = await self._finish_run_failure(
                run_id,
                error_code=error.code,
                correlation_id=correlation_id,
            )
            sequence += 1
            yield AgentStreamFrame(
                type=StreamFrameType.ERROR,
                run_id=run_id,
                sequence=sequence,
                status=final.status,
                error_code=error.code,
            )
            sequence += 1
            yield _run_completed_frame(final, sequence)
        except Exception:
            await await_cancellation_resistant(
                self._finish_run_failure(
                    run_id,
                    error_code="agent_run.internal_failure",
                    correlation_id=correlation_id,
                )
            )
            raise
        finally:
            await self._registry.unregister(run_id)

    async def _prepare_run(
        self,
        run_id: str,
        *,
        instruction: str,
        correlation_id: str,
    ) -> tuple[
        AgentRun,
        RoomModelAssignment,
        dict[str, ModelProfile],
        ContextWindow,
        tuple[str, ...],
        Stage,
    ]:
        now = datetime.now(UTC)
        async with self._write_uow() as uow:
            run = await uow.model_runtime.get_run(run_id)
            if run is None:
                raise _not_found("agent_run", "Agent run was not found")
            if run.status is not AgentRunStatus.PENDING:
                raise DomainError(
                    code="agent_run.not_pending",
                    message="Only pending agent runs can execute",
                    category=ErrorCategory.CONFLICT,
                )
            room = await uow.workflows.get_room(run.room_id)
            if room is None:
                raise RuntimeError("agent run room is missing")
            stage_run = await uow.workflows.get_stage_run(room.stage_run_id)
            assignment = await uow.model_runtime.get_assignment(room.id)
            if stage_run is None or assignment is None:
                raise RuntimeError("agent run configuration is incomplete")
            profile_ids = tuple(
                profile_id
                for profile_id in (
                    assignment.primary_profile_id,
                    assignment.reviewer_a_profile_id,
                    assignment.reviewer_b_profile_id,
                )
                if profile_id is not None
            )
            profiles: dict[str, ModelProfile] = {}
            for profile_id in profile_ids:
                profile = await uow.model_runtime.get_profile(profile_id)
                if profile is None or not profile.enabled:
                    raise DomainError(
                        code="agent_run.profile_unavailable",
                        message="Assigned model profile is unavailable",
                        category=ErrorCategory.UNAVAILABLE,
                        details={"profile_id": profile_id},
                    )
                profiles[profile_id] = profile
            messages = await uow.workflows.list_messages(room.id, after_sequence=0, limit=10_000)
            summary = await uow.model_runtime.get_latest_summary(room.id)
            new_summary = self._summary_builder.build(room.id, messages, summary)
            if new_summary is not None:
                await uow.model_runtime.add_summary(new_summary)
                summary = new_summary
            user_message = Message(
                schema_version=1,
                id=new_id("message"),
                room_id=room.id,
                sequence=room.next_sequence,
                author=MessageAuthor.USER,
                kind=MessageKind.DISCUSSION,
                content=instruction.strip(),
                created_at=now,
            )
            await uow.workflows.append_message(
                user_message,
                expected_room_version=room.version,
                updated_at=now,
            )
            updated = await uow.model_runtime.update_run(
                run_id,
                AgentRunStatus.RUNNING,
                expected_version=run.version,
                completed_at=None,
            )
            workflow = await uow.workflows.get(run.workflow_id)
            if workflow is None:
                raise RuntimeError("agent run workflow is missing")
            await _append_event(
                uow,
                event_type="message.appended",
                correlation_id=correlation_id,
                occurred_at=now,
                project_id=workflow.project_id,
                workflow_id=run.workflow_id,
                room_id=run.room_id,
                payload={
                    "message_id": user_message.id,
                    "sequence": user_message.sequence,
                    "kind": user_message.kind.value,
                },
                actor_type=ActorType.USER,
                source=EventSource.BACKEND,
            )
            await _append_event(
                uow,
                event_type="agent_run.started",
                correlation_id=correlation_id,
                occurred_at=now,
                project_id=workflow.project_id,
                workflow_id=run.workflow_id,
                room_id=run.room_id,
                payload={"agent_run_id": run_id},
            )
            registration = await uow.projects.get(workflow.project_id)
            manifest = await uow.projects.get_manifest(workflow.project_id)
            await uow.commit()
        if registration is None or manifest is None:
            raise RuntimeError("agent run project context is missing")
        project_instructions = await asyncio.to_thread(
            _load_project_instructions,
            Path(registration.workspace.root_path),
            manifest.manifest.instruction_paths,
            self._settings.project_instruction_max_bytes,
        )
        context = self._context_builder.build(run.room_id, messages, summary)
        return updated, assignment, profiles, context, project_instructions, stage_run.stage

    async def _stream_call(
        self,
        run: AgentRun,
        profile: ModelProfile,
        role: ModelRole,
        phase: ModelPhase,
        *,
        stage: Stage,
        context: ContextWindow,
        instruction: str,
        runtime_state: str,
        project_instructions: tuple[str, ...],
        project_file_content: str,
        review_material: str | None,
        cancellation: asyncio.Event,
        starting_sequence: int,
        outcome: _CallOutcome,
    ) -> AsyncIterator[AgentStreamFrame]:
        invocation, prompt_hash = self._prompt_composer.compose(
            stage=stage,
            role=role,
            phase=phase,
            context=context,
            instruction=instruction,
            runtime_state=runtime_state,
            project_instructions=project_instructions,
            project_file_content=project_file_content,
            review_material=review_material,
            model=profile.model,
            max_output_tokens=self._settings.model_max_output_tokens,
        )
        now = datetime.now(UTC)
        call = ModelCall(
            schema_version=1,
            id=new_id("modelcall"),
            agent_run_id=run.id,
            profile_id=profile.id,
            role=role,
            phase=phase,
            status=ModelCallStatus.PENDING,
            prompt_hash=prompt_hash,
            version=1,
        )
        async with self._write_uow() as uow:
            await uow.model_runtime.add_call(call)
            call = await uow.model_runtime.update_call(
                call.id,
                ModelCallStatus.STREAMING,
                expected_version=1,
                started_at=now,
                completed_at=None,
            )
            await uow.commit()
        sequence = starting_sequence + 1
        yield AgentStreamFrame(
            type=StreamFrameType.CALL_STARTED,
            run_id=run.id,
            sequence=sequence,
            role=role,
            phase=phase,
            status=ModelCallStatus.STREAMING,
        )
        outcome.call = call
        adapter = self._adapters.get(profile.provider)
        secret = await self._secret_store.resolve(profile.credential_ref)
        if adapter is None:
            outcome.error_code = "model.adapter_unavailable"
        elif secret is None:
            outcome.error_code = "model.credential_unavailable"
        else:
            pieces: list[str] = []
            encoded_size = 0
            try:
                async for chunk in adapter.stream(
                    invocation,
                    base_url=profile.base_url,
                    api_key=secret,
                    cancellation=cancellation,
                ):
                    if cancellation.is_set():
                        raise asyncio.CancelledError
                    if chunk.input_tokens is not None:
                        outcome.input_tokens += chunk.input_tokens
                    if chunk.output_tokens is not None:
                        outcome.output_tokens += chunk.output_tokens
                    if chunk.text:
                        encoded_size += len(chunk.text.encode("utf-8"))
                        if encoded_size > self._settings.model_output_max_bytes:
                            raise ModelAdapterError("model.output_too_large")
                        pieces.append(chunk.text)
                        sequence += 1
                        yield AgentStreamFrame(
                            type=StreamFrameType.CHUNK,
                            run_id=run.id,
                            sequence=sequence,
                            role=role,
                            phase=phase,
                            text=chunk.text,
                        )
                content = "".join(pieces).strip()
                output = await asyncio.to_thread(self._output_store.write, content)
                outcome.output = output
                outcome.content = content
            except asyncio.CancelledError:
                await await_cancellation_resistant(self._cancel_call(call))
                raise
            except ModelAdapterError as error:
                outcome.error_code = error.code
            except DomainError as error:
                outcome.error_code = error.code
        if outcome.content is None:
            await self._fail_call(call, outcome.error_code or "model.call_failed")
            sequence += 1
            yield AgentStreamFrame(
                type=StreamFrameType.ERROR,
                run_id=run.id,
                sequence=sequence,
                role=role,
                phase=phase,
                status=ModelCallStatus.FAILED,
                error_code=outcome.error_code or "model.call_failed",
            )
        else:
            assert outcome.output is not None
            await self._complete_call(call, outcome)
            sequence += 1
            yield AgentStreamFrame(
                type=StreamFrameType.CALL_COMPLETED,
                run_id=run.id,
                sequence=sequence,
                role=role,
                phase=phase,
                status=ModelCallStatus.SUCCEEDED,
                data={
                    "input_tokens": outcome.input_tokens,
                    "output_tokens": outcome.output_tokens,
                },
            )

    async def _complete_call(self, call: ModelCall, outcome: _CallOutcome) -> None:
        assert outcome.output is not None
        now = datetime.now(UTC)
        async with self._write_uow() as uow:
            await uow.model_runtime.update_call(
                call.id,
                ModelCallStatus.SUCCEEDED,
                expected_version=call.version,
                started_at=call.started_at,
                completed_at=now,
                output_ref=outcome.output.reference,
                output_hash=outcome.output.content_hash,
                output_bytes=outcome.output.byte_size,
            )
            await uow.model_runtime.record_usage(
                UsageRecord(
                    schema_version=1,
                    model_call_id=call.id,
                    input_tokens=outcome.input_tokens,
                    output_tokens=outcome.output_tokens,
                    total_tokens=outcome.input_tokens + outcome.output_tokens,
                    recorded_at=now,
                )
            )
            await uow.commit()

    async def _fail_call(self, call: ModelCall, error_code: str) -> None:
        async with self._write_uow() as uow:
            await uow.model_runtime.update_call(
                call.id,
                ModelCallStatus.FAILED,
                expected_version=call.version,
                started_at=call.started_at,
                completed_at=datetime.now(UTC),
                error_code=error_code,
            )
            await uow.commit()

    async def _cancel_call(self, call: ModelCall) -> None:
        async with self._write_uow() as uow:
            current = await uow.model_runtime.get_call(call.id)
            if current is not None and current.status is ModelCallStatus.STREAMING:
                await uow.model_runtime.update_call(
                    call.id,
                    ModelCallStatus.CANCELLED,
                    expected_version=current.version,
                    started_at=current.started_at,
                    completed_at=datetime.now(UTC),
                    error_code="model.call_cancelled",
                )
                await uow.commit()

    async def _finish_run_failure(
        self,
        run_id: str,
        *,
        error_code: str,
        correlation_id: str,
    ) -> AgentRun:
        return await self._finish_run(
            run_id,
            status=AgentRunStatus.FAILED,
            output=None,
            error_code=error_code,
            correlation_id=correlation_id,
        )

    async def _finish_run_cancelled(self, run_id: str, *, correlation_id: str) -> AgentRun:
        async with SqlAlchemyUnitOfWork(self._database.sessions) as uow:
            current = await uow.model_runtime.get_run(run_id)
        if current is None:
            raise _not_found("agent_run", "Agent run was not found")
        if current.status in {
            AgentRunStatus.SUCCEEDED,
            AgentRunStatus.PARTIAL_FAILURE,
            AgentRunStatus.FAILED,
            AgentRunStatus.CANCELLED,
        }:
            return current
        return await self._finish_run(
            run_id,
            status=AgentRunStatus.CANCELLED,
            output=None,
            error_code="agent_run.cancelled",
            correlation_id=correlation_id,
        )

    async def _finish_run(
        self,
        run_id: str,
        *,
        status: AgentRunStatus,
        output: StoredModelOutput | None,
        error_code: str | None,
        correlation_id: str,
        append_content: str | None = None,
    ) -> AgentRun:
        now = datetime.now(UTC)
        async with self._write_uow() as uow:
            current = await uow.model_runtime.get_run(run_id)
            if current is None:
                raise _not_found("agent_run", "Agent run was not found")
            finished = await uow.model_runtime.update_run(
                run_id,
                status,
                expected_version=current.version,
                completed_at=now,
                output_ref=output.reference if output else None,
                output_hash=output.content_hash if output else None,
                output_bytes=output.byte_size if output else None,
                error_code=error_code,
            )
            room = await uow.workflows.get_room(current.room_id)
            workflow = await uow.workflows.get(current.workflow_id)
            if room is None or workflow is None:
                raise RuntimeError("agent run graph is incomplete")
            if append_content is not None:
                message = Message(
                    schema_version=1,
                    id=new_id("message"),
                    room_id=room.id,
                    sequence=room.next_sequence,
                    author=MessageAuthor.AGENT,
                    kind=MessageKind.DISCUSSION,
                    content=append_content,
                    created_at=now,
                )
                await uow.workflows.append_message(
                    message,
                    expected_room_version=room.version,
                    updated_at=now,
                )
            await _append_event(
                uow,
                event_type="agent_run.completed",
                correlation_id=correlation_id,
                occurred_at=now,
                project_id=workflow.project_id,
                workflow_id=workflow.id,
                room_id=room.id,
                payload={
                    "agent_run_id": run_id,
                    "status": status.value,
                    "error_code": error_code,
                },
            )
            await uow.commit()
        return finished

    def _write_uow(self) -> SqlAlchemyUnitOfWork:
        return SqlAlchemyUnitOfWork(
            self._database.sessions,
            delivery_targets=(LOCAL_AUDIT_CONSUMER, WEBSOCKET_CONSUMER),
            write=True,
            write_lock=self._database.write_lock,
        )


async def _append_event(
    uow: SqlAlchemyUnitOfWork,
    *,
    event_type: str,
    correlation_id: str,
    occurred_at: datetime,
    project_id: str,
    workflow_id: str,
    room_id: str,
    payload: dict[str, object],
    actor_type: ActorType = ActorType.MODEL,
    source: EventSource = EventSource.MODEL,
) -> None:
    await uow.events.append(
        envelope=EventEnvelope(
            schema_version=1,
            event_type=event_type,
            correlation_id=correlation_id,
            actor=ActorRef(
                type=actor_type,
                id="user_local" if actor_type is ActorType.USER else "model_runtime",
            ),
            source=source,
            occurred_at=occurred_at,
            project_id=project_id,
            workflow_id=workflow_id,
            room_id=room_id,
            payload=payload,
        ),
        aggregate_type="workflow",
        aggregate_id=workflow_id,
    )


def _run_completed_frame(run: AgentRun, sequence: int) -> AgentStreamFrame:
    return AgentStreamFrame(
        type=StreamFrameType.RUN_COMPLETED,
        run_id=run.id,
        sequence=sequence,
        status=run.status,
        error_code=run.error_code,
        data={
            "output_ref": run.final_output_ref,
            "output_hash": run.final_output_hash,
            "output_bytes": run.final_output_bytes,
        },
    )


def _runtime_state(state: str, execution_contract: str | None) -> str:
    if execution_contract is None:
        return state
    return f"{state}\n\n{execution_contract}"


def _load_project_instructions(
    workspace_root: Path,
    relative_paths: tuple[str, ...],
    max_bytes: int,
) -> tuple[str, ...]:
    root, _ = validate_direct_workspace_root(workspace_root)
    remaining = max_bytes
    contents: list[str] = []
    for relative_path in relative_paths:
        path = root.joinpath(*relative_path.split("/"))
        try:
            metadata = path.lstat()
            if _is_link_or_reparse(metadata) or not stat.S_ISREG(metadata.st_mode):
                raise OSError
            resolved = path.resolve(strict=True)
            if not resolved.is_relative_to(root) or metadata.st_size > remaining:
                raise OSError
            data = path.read_bytes()
            if len(data) != metadata.st_size:
                raise OSError
            contents.append(data.decode("utf-8", errors="strict"))
            remaining -= len(data)
        except (OSError, UnicodeError):
            raise DomainError(
                code="context.project_instruction_unavailable",
                message="Project instruction file is unavailable or unsafe",
                category=ErrorCategory.UNAVAILABLE,
                details={"relative_path": relative_path},
            ) from None
    return tuple(contents)


def _is_link_or_reparse(metadata: os.stat_result) -> bool:
    return stat.S_ISLNK(metadata.st_mode) or bool(
        getattr(metadata, "st_file_attributes", 0) & _WINDOWS_REPARSE_POINT
    )


def _not_found(code: str, message: str) -> DomainError:
    return DomainError(
        code=f"{code}.not_found",
        message=message,
        category=ErrorCategory.NOT_FOUND,
    )
