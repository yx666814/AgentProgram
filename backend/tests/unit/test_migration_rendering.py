from alembic.autogenerate.api import AutogenContext
from alembic.autogenerate.render import _repr_type
from alembic.migration import MigrationContext

from agent_platform.infrastructure.database.migration_rendering import render_item
from agent_platform.infrastructure.database.types import UTCDateTime


def test_alembic_renders_utc_datetime_as_plain_sqlalchemy_datetime() -> None:
    migration_context = MigrationContext.configure(
        dialect_name="sqlite",
        opts={
            "alembic_module_prefix": "op.",
            "render_item": render_item,
            "sqlalchemy_module_prefix": "sa.",
            "user_module_prefix": None,
        },
    )
    autogen_context = AutogenContext(migration_context)

    rendered_type = _repr_type(UTCDateTime(), autogen_context)

    assert rendered_type == "sa.DateTime()"
    assert "agent_platform" not in rendered_type
    assert autogen_context.imports == set()
