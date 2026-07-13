from typing import Literal

from alembic.autogenerate.api import AutogenContext

from agent_platform.infrastructure.database.types import UTCDateTime


def render_item(
    type_: str,
    obj: object,
    _autogen_context: AutogenContext,
) -> str | Literal[False]:
    if type_ == "type" and isinstance(obj, UTCDateTime):
        return "sa.DateTime()"
    return False
