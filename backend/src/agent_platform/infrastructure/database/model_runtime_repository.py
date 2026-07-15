from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agent_platform.domain.model_runtime import (
    AgentRun,
    AgentRunSnapshot,
    AgentRunStatus,
    ConversationSummary,
    ModelCall,
    ModelCallStatus,
    ModelPhase,
    ModelProfile,
    ModelProvider,
    ModelRole,
    RoomModelAssignment,
    UsageRecord,
)
from agent_platform.domain.shared.errors import DomainError, ErrorCategory
from agent_platform.infrastructure.database.models import (
    AgentRunRow,
    ConversationSummaryRow,
    ModelCallRow,
    ModelProfileRow,
    RoomModelAssignmentRow,
    UsageRecordRow,
)


class SqlAlchemyModelRuntimeRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add_profile(self, profile: ModelProfile) -> None:
        self._session.add(_profile_row(profile))
        await self._session.flush()

    async def get_profile(self, profile_id: str) -> ModelProfile | None:
        row = await self._session.get(ModelProfileRow, profile_id)
        return _profile_from_row(row) if row is not None else None

    async def list_profiles(self) -> tuple[ModelProfile, ...]:
        statement = select(ModelProfileRow).order_by(
            ModelProfileRow.updated_at.desc(), ModelProfileRow.id
        )
        rows = (await self._session.scalars(statement)).all()
        return tuple(_profile_from_row(row) for row in rows)

    async def update_profile(
        self,
        profile: ModelProfile,
        *,
        expected_version: int,
    ) -> None:
        row = await self._require_profile_row(profile.id)
        _require_version("model_profile", row.version, expected_version)
        if profile.version != expected_version + 1:
            raise _version_error("model_profile", row.version)
        row.name = profile.name
        row.provider = profile.provider.value
        row.base_url = profile.base_url
        row.model = profile.model
        row.credential_ref = profile.credential_ref
        row.masked_hint = profile.masked_hint
        row.enabled = profile.enabled
        row.version = profile.version
        row.updated_at = profile.updated_at
        await self._session.flush()

    async def save_assignment(
        self,
        assignment: RoomModelAssignment,
        *,
        expected_version: int | None,
    ) -> None:
        row = await self._session.get(RoomModelAssignmentRow, assignment.room_id)
        if row is None:
            if expected_version is not None or assignment.version != 1:
                raise _version_error("room_model_assignment", 0)
            self._session.add(_assignment_row(assignment))
        else:
            if expected_version is None:
                raise _version_error("room_model_assignment", row.version)
            _require_version("room_model_assignment", row.version, expected_version)
            if assignment.version != expected_version + 1:
                raise _version_error("room_model_assignment", row.version)
            row.primary_profile_id = assignment.primary_profile_id
            row.reviewer_a_profile_id = assignment.reviewer_a_profile_id
            row.reviewer_b_profile_id = assignment.reviewer_b_profile_id
            row.version = assignment.version
            row.updated_at = assignment.updated_at
        await self._session.flush()

    async def get_assignment(self, room_id: str) -> RoomModelAssignment | None:
        row = await self._session.get(RoomModelAssignmentRow, room_id)
        return _assignment_from_row(row) if row is not None else None

    async def add_run(self, run: AgentRun) -> None:
        self._session.add(_run_row(run))
        await self._session.flush()

    async def get_run(self, run_id: str) -> AgentRun | None:
        row = await self._session.get(AgentRunRow, run_id)
        return _run_from_row(row) if row is not None else None

    async def get_run_by_request(self, room_id: str, request_key: str) -> AgentRun | None:
        statement = select(AgentRunRow).where(
            AgentRunRow.room_id == room_id,
            AgentRunRow.request_key == request_key,
        )
        row = await self._session.scalar(statement)
        return _run_from_row(row) if row is not None else None

    async def list_runs(self, room_id: str) -> tuple[AgentRun, ...]:
        statement = (
            select(AgentRunRow)
            .where(AgentRunRow.room_id == room_id)
            .order_by(AgentRunRow.created_at, AgentRunRow.id)
        )
        rows = (await self._session.scalars(statement)).all()
        return tuple(_run_from_row(row) for row in rows)

    async def find_active_run_for_room(self, room_id: str) -> AgentRun | None:
        statement = (
            select(AgentRunRow)
            .where(
                AgentRunRow.room_id == room_id,
                AgentRunRow.status.in_(
                    (AgentRunStatus.PENDING.value, AgentRunStatus.RUNNING.value)
                ),
            )
            .order_by(AgentRunRow.created_at, AgentRunRow.id)
            .limit(1)
        )
        row = await self._session.scalar(statement)
        return _run_from_row(row) if row is not None else None

    async def update_run(
        self,
        run_id: str,
        status: AgentRunStatus,
        *,
        expected_version: int,
        completed_at: datetime | None,
        output_ref: str | None = None,
        output_hash: str | None = None,
        output_bytes: int | None = None,
        error_code: str | None = None,
    ) -> AgentRun:
        row = await self._require_run_row(run_id)
        _require_version("agent_run", row.version, expected_version)
        row.status = status.value
        row.final_output_ref = output_ref
        row.final_output_hash = output_hash
        row.final_output_bytes = output_bytes
        row.error_code = error_code
        row.version += 1
        row.completed_at = completed_at
        await self._session.flush()
        return _run_from_row(row)

    async def add_call(self, call: ModelCall) -> None:
        self._session.add(_call_row(call))
        await self._session.flush()

    async def get_call(self, call_id: str) -> ModelCall | None:
        row = await self._session.get(ModelCallRow, call_id)
        return _call_from_row(row) if row is not None else None

    async def list_calls(self, run_id: str) -> tuple[ModelCall, ...]:
        statement = (
            select(ModelCallRow)
            .where(ModelCallRow.agent_run_id == run_id)
            .order_by(ModelCallRow.started_at, ModelCallRow.id)
        )
        rows = (await self._session.scalars(statement)).all()
        return tuple(_call_from_row(row) for row in rows)

    async def update_call(
        self,
        call_id: str,
        status: ModelCallStatus,
        *,
        expected_version: int,
        started_at: datetime | None,
        completed_at: datetime | None,
        output_ref: str | None = None,
        output_hash: str | None = None,
        output_bytes: int | None = None,
        error_code: str | None = None,
    ) -> ModelCall:
        row = await self._require_call_row(call_id)
        _require_version("model_call", row.version, expected_version)
        row.status = status.value
        row.started_at = started_at
        row.completed_at = completed_at
        row.output_ref = output_ref
        row.output_hash = output_hash
        row.output_bytes = output_bytes
        row.error_code = error_code
        row.version += 1
        await self._session.flush()
        return _call_from_row(row)

    async def record_usage(self, usage: UsageRecord) -> None:
        existing = await self._session.get(UsageRecordRow, usage.model_call_id)
        if existing is not None:
            raise DomainError(
                code="usage.already_recorded",
                message="Usage was already recorded for this model call",
                category=ErrorCategory.CONFLICT,
            )
        self._session.add(_usage_row(usage))
        await self._session.flush()

    async def get_usage(self, call_id: str) -> UsageRecord | None:
        row = await self._session.get(UsageRecordRow, call_id)
        return _usage_from_row(row) if row is not None else None

    async def get_snapshot(self, run_id: str) -> AgentRunSnapshot | None:
        run = await self.get_run(run_id)
        if run is None:
            return None
        calls = await self.list_calls(run_id)
        usage: list[UsageRecord] = []
        for call in calls:
            record = await self.get_usage(call.id)
            if record is not None:
                usage.append(record)
        return AgentRunSnapshot(
            schema_version=1,
            run=run,
            calls=calls,
            usage=tuple(usage),
        )

    async def add_summary(self, summary: ConversationSummary) -> None:
        self._session.add(_summary_row(summary))
        await self._session.flush()

    async def get_latest_summary(self, room_id: str) -> ConversationSummary | None:
        statement = (
            select(ConversationSummaryRow)
            .where(ConversationSummaryRow.room_id == room_id)
            .order_by(
                ConversationSummaryRow.through_sequence.desc(),
                ConversationSummaryRow.id.desc(),
            )
            .limit(1)
        )
        row = await self._session.scalar(statement)
        return _summary_from_row(row) if row is not None else None

    async def _require_profile_row(self, profile_id: str) -> ModelProfileRow:
        row = await self._session.get(ModelProfileRow, profile_id)
        if row is None:
            raise _not_found("model_profile", "Model profile was not found")
        return row

    async def _require_run_row(self, run_id: str) -> AgentRunRow:
        row = await self._session.get(AgentRunRow, run_id)
        if row is None:
            raise _not_found("agent_run", "Agent run was not found")
        return row

    async def _require_call_row(self, call_id: str) -> ModelCallRow:
        row = await self._session.get(ModelCallRow, call_id)
        if row is None:
            raise _not_found("model_call", "Model call was not found")
        return row


def _require_version(entity: str, current: int, expected: int) -> None:
    if current != expected:
        raise _version_error(entity, current)


def _version_error(entity: str, current: int) -> DomainError:
    return DomainError(
        code=f"{entity}.version_conflict",
        message=f"{entity.replace('_', ' ').title()} version has changed",
        category=ErrorCategory.CONFLICT,
        details={"current_version": current},
    )


def _not_found(code: str, message: str) -> DomainError:
    return DomainError(
        code=f"{code}.not_found",
        message=message,
        category=ErrorCategory.NOT_FOUND,
    )


def _profile_row(profile: ModelProfile) -> ModelProfileRow:
    return ModelProfileRow(
        id=profile.id,
        schema_version=profile.schema_version,
        name=profile.name,
        provider=profile.provider.value,
        base_url=profile.base_url,
        model=profile.model,
        credential_ref=profile.credential_ref,
        masked_hint=profile.masked_hint,
        enabled=profile.enabled,
        version=profile.version,
        created_at=profile.created_at,
        updated_at=profile.updated_at,
    )


def _assignment_row(assignment: RoomModelAssignment) -> RoomModelAssignmentRow:
    return RoomModelAssignmentRow(
        room_id=assignment.room_id,
        schema_version=assignment.schema_version,
        primary_profile_id=assignment.primary_profile_id,
        reviewer_a_profile_id=assignment.reviewer_a_profile_id,
        reviewer_b_profile_id=assignment.reviewer_b_profile_id,
        version=assignment.version,
        updated_at=assignment.updated_at,
    )


def _run_row(run: AgentRun) -> AgentRunRow:
    return AgentRunRow(
        id=run.id,
        workflow_id=run.workflow_id,
        room_id=run.room_id,
        schema_version=run.schema_version,
        request_key=run.request_key,
        formal=run.formal,
        status=run.status.value,
        final_output_ref=run.final_output_ref,
        final_output_hash=run.final_output_hash,
        final_output_bytes=run.final_output_bytes,
        error_code=run.error_code,
        version=run.version,
        created_at=run.created_at,
        completed_at=run.completed_at,
    )


def _call_row(call: ModelCall) -> ModelCallRow:
    return ModelCallRow(
        id=call.id,
        agent_run_id=call.agent_run_id,
        profile_id=call.profile_id,
        schema_version=call.schema_version,
        role=call.role.value,
        phase=call.phase.value,
        status=call.status.value,
        prompt_hash=call.prompt_hash,
        output_ref=call.output_ref,
        output_hash=call.output_hash,
        output_bytes=call.output_bytes,
        error_code=call.error_code,
        version=call.version,
        started_at=call.started_at,
        completed_at=call.completed_at,
    )


def _usage_row(usage: UsageRecord) -> UsageRecordRow:
    return UsageRecordRow(
        model_call_id=usage.model_call_id,
        schema_version=usage.schema_version,
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        total_tokens=usage.total_tokens,
        recorded_at=usage.recorded_at,
    )


def _summary_row(summary: ConversationSummary) -> ConversationSummaryRow:
    return ConversationSummaryRow(
        id=summary.id,
        room_id=summary.room_id,
        schema_version=summary.schema_version,
        through_sequence=summary.through_sequence,
        content=summary.content,
        content_hash=summary.content_hash,
        created_at=summary.created_at,
    )


def _profile_from_row(row: ModelProfileRow) -> ModelProfile:
    return ModelProfile(
        schema_version=1,
        id=row.id,
        name=row.name,
        provider=ModelProvider(row.provider),
        base_url=row.base_url,
        model=row.model,
        credential_ref=row.credential_ref,
        masked_hint=row.masked_hint,
        enabled=row.enabled,
        version=row.version,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _assignment_from_row(row: RoomModelAssignmentRow) -> RoomModelAssignment:
    return RoomModelAssignment(
        schema_version=1,
        room_id=row.room_id,
        primary_profile_id=row.primary_profile_id,
        reviewer_a_profile_id=row.reviewer_a_profile_id,
        reviewer_b_profile_id=row.reviewer_b_profile_id,
        version=row.version,
        updated_at=row.updated_at,
    )


def _run_from_row(row: AgentRunRow) -> AgentRun:
    return AgentRun(
        schema_version=1,
        id=row.id,
        workflow_id=row.workflow_id,
        room_id=row.room_id,
        request_key=row.request_key,
        formal=row.formal,
        status=AgentRunStatus(row.status),
        final_output_ref=row.final_output_ref,
        final_output_hash=row.final_output_hash,
        final_output_bytes=row.final_output_bytes,
        error_code=row.error_code,
        version=row.version,
        created_at=row.created_at,
        completed_at=row.completed_at,
    )


def _call_from_row(row: ModelCallRow) -> ModelCall:
    return ModelCall(
        schema_version=1,
        id=row.id,
        agent_run_id=row.agent_run_id,
        profile_id=row.profile_id,
        role=ModelRole(row.role),
        phase=ModelPhase(row.phase),
        status=ModelCallStatus(row.status),
        prompt_hash=row.prompt_hash,
        output_ref=row.output_ref,
        output_hash=row.output_hash,
        output_bytes=row.output_bytes,
        error_code=row.error_code,
        version=row.version,
        started_at=row.started_at,
        completed_at=row.completed_at,
    )


def _usage_from_row(row: UsageRecordRow) -> UsageRecord:
    return UsageRecord(
        schema_version=1,
        model_call_id=row.model_call_id,
        input_tokens=row.input_tokens,
        output_tokens=row.output_tokens,
        total_tokens=row.total_tokens,
        recorded_at=row.recorded_at,
    )


def _summary_from_row(row: ConversationSummaryRow) -> ConversationSummary:
    return ConversationSummary(
        schema_version=1,
        id=row.id,
        room_id=row.room_id,
        through_sequence=row.through_sequence,
        content=row.content,
        content_hash=row.content_hash,
        created_at=row.created_at,
    )
