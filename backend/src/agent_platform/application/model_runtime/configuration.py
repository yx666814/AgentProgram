from __future__ import annotations

from datetime import UTC, datetime

from agent_platform.domain.events import ActorRef, ActorType, EventEnvelope, EventSource
from agent_platform.domain.model_runtime import (
    ModelProfile,
    ModelProvider,
    RoomModelAssignment,
)
from agent_platform.domain.shared.errors import DomainError, ErrorCategory
from agent_platform.domain.shared.ids import new_id
from agent_platform.infrastructure.database.session import Database
from agent_platform.infrastructure.database.unit_of_work import SqlAlchemyUnitOfWork
from agent_platform.ports.event_publishing import LOCAL_AUDIT_CONSUMER, WEBSOCKET_CONSUMER


class ModelConfigurationService:
    def __init__(self, database: Database) -> None:
        self._database = database

    async def create_profile(
        self,
        *,
        name: str,
        provider: ModelProvider,
        base_url: str,
        model: str,
        credential_ref: str,
        masked_hint: str,
        correlation_id: str,
    ) -> ModelProfile:
        now = datetime.now(UTC)
        profile = ModelProfile(
            schema_version=1,
            id=new_id("profile"),
            name=name.strip(),
            provider=provider,
            base_url=base_url.strip(),
            model=model.strip(),
            credential_ref=credential_ref,
            masked_hint=masked_hint.strip(),
            enabled=True,
            version=1,
            created_at=now,
            updated_at=now,
        )
        async with self._write_uow() as uow:
            await uow.model_runtime.add_profile(profile)
            await _append_event(
                uow,
                event_type="model_profile.created",
                correlation_id=correlation_id,
                occurred_at=now,
                aggregate_id=profile.id,
                payload={"provider": profile.provider.value, "model": profile.model},
            )
            await uow.commit()
        return profile

    async def list_profiles(self) -> tuple[ModelProfile, ...]:
        async with SqlAlchemyUnitOfWork(self._database.sessions) as uow:
            return await uow.model_runtime.list_profiles()

    async def get_profile(self, profile_id: str) -> ModelProfile:
        async with SqlAlchemyUnitOfWork(self._database.sessions) as uow:
            profile = await uow.model_runtime.get_profile(profile_id)
        if profile is None:
            raise _not_found("model_profile", "Model profile was not found")
        return profile

    async def update_profile(
        self,
        profile_id: str,
        *,
        name: str,
        provider: ModelProvider,
        base_url: str,
        model: str,
        credential_ref: str,
        masked_hint: str,
        enabled: bool,
        expected_version: int,
        correlation_id: str,
    ) -> ModelProfile:
        now = datetime.now(UTC)
        async with self._write_uow() as uow:
            current = await uow.model_runtime.get_profile(profile_id)
            if current is None:
                raise _not_found("model_profile", "Model profile was not found")
            updated = ModelProfile(
                schema_version=1,
                id=current.id,
                name=name.strip(),
                provider=provider,
                base_url=base_url.strip(),
                model=model.strip(),
                credential_ref=credential_ref,
                masked_hint=masked_hint.strip(),
                enabled=enabled,
                version=expected_version + 1,
                created_at=current.created_at,
                updated_at=now,
            )
            await uow.model_runtime.update_profile(updated, expected_version=expected_version)
            await _append_event(
                uow,
                event_type="model_profile.updated",
                correlation_id=correlation_id,
                occurred_at=now,
                aggregate_id=profile_id,
                payload={"enabled": enabled, "provider": provider.value},
            )
            await uow.commit()
        return updated

    async def assign_room(
        self,
        room_id: str,
        *,
        primary_profile_id: str,
        reviewer_a_profile_id: str | None,
        reviewer_b_profile_id: str | None,
        expected_version: int | None,
        correlation_id: str,
    ) -> RoomModelAssignment:
        now = datetime.now(UTC)
        async with self._workflow_write_uow() as uow:
            room = await uow.workflows.get_room(room_id)
            if room is None:
                raise _not_found("room", "Room was not found")
            profile_ids = tuple(
                profile_id
                for profile_id in (
                    primary_profile_id,
                    reviewer_a_profile_id,
                    reviewer_b_profile_id,
                )
                if profile_id is not None
            )
            for profile_id in profile_ids:
                profile = await uow.model_runtime.get_profile(profile_id)
                if profile is None:
                    raise _not_found("model_profile", "Assigned model profile was not found")
                if not profile.enabled:
                    raise DomainError(
                        code="model_profile.disabled",
                        message="Disabled model profiles cannot be assigned",
                        category=ErrorCategory.CONFLICT,
                        details={"profile_id": profile_id},
                    )
            assignment = RoomModelAssignment(
                schema_version=1,
                room_id=room_id,
                primary_profile_id=primary_profile_id,
                reviewer_a_profile_id=reviewer_a_profile_id,
                reviewer_b_profile_id=reviewer_b_profile_id,
                version=1 if expected_version is None else expected_version + 1,
                updated_at=now,
            )
            await uow.model_runtime.save_assignment(
                assignment,
                expected_version=expected_version,
            )
            workflow = await uow.workflows.get(room.workflow_id)
            if workflow is None:
                raise RuntimeError("room workflow is missing")
            await _append_event(
                uow,
                event_type="room_model_assignment.updated",
                correlation_id=correlation_id,
                occurred_at=now,
                aggregate_id=room_id,
                project_id=workflow.project_id,
                workflow_id=workflow.id,
                room_id=room_id,
                payload={
                    "primary_profile_id": primary_profile_id,
                    "reviewer_count": sum(
                        value is not None
                        for value in (reviewer_a_profile_id, reviewer_b_profile_id)
                    ),
                },
            )
            await uow.commit()
        return assignment

    async def get_assignment(self, room_id: str) -> RoomModelAssignment:
        async with SqlAlchemyUnitOfWork(self._database.sessions) as uow:
            assignment = await uow.model_runtime.get_assignment(room_id)
        if assignment is None:
            raise _not_found("room_model_assignment", "Room model assignment was not found")
        return assignment

    def _write_uow(self) -> SqlAlchemyUnitOfWork:
        return SqlAlchemyUnitOfWork(
            self._database.sessions,
            write=True,
            write_lock=self._database.write_lock,
        )

    def _workflow_write_uow(self) -> SqlAlchemyUnitOfWork:
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
    aggregate_id: str,
    payload: dict[str, object],
    project_id: str | None = None,
    workflow_id: str | None = None,
    room_id: str | None = None,
) -> None:
    await uow.events.append(
        envelope=EventEnvelope(
            schema_version=1,
            event_type=event_type,
            correlation_id=correlation_id,
            actor=ActorRef(type=ActorType.USER, id="user_local"),
            source=EventSource.BACKEND,
            occurred_at=occurred_at,
            project_id=project_id,
            workflow_id=workflow_id,
            room_id=room_id,
            payload=payload,
        ),
        aggregate_type="model_profile" if workflow_id is None else "workflow",
        aggregate_id=aggregate_id,
    )


def _not_found(code: str, message: str) -> DomainError:
    return DomainError(
        code=f"{code}.not_found",
        message=message,
        category=ErrorCategory.NOT_FOUND,
    )
