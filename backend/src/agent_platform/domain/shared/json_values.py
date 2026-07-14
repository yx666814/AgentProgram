from math import isfinite
from typing import Any, cast

_MAX_JSON_DEPTH = 64


def _ensure_json_value(
    value: object,
    active_container_ids: set[int],
    depth: int,
) -> None:
    if depth > _MAX_JSON_DEPTH:
        raise ValueError("payload must contain only JSON values")
    value_type = type(value)
    if value is None or value_type in {bool, int, str}:
        return
    if value_type is float:
        if isfinite(cast(float, value)):
            return
        raise ValueError("payload must contain only JSON values")
    if value_type is list:
        container_id = id(value)
        if container_id in active_container_ids:
            raise ValueError("payload must contain only JSON values")
        active_container_ids.add(container_id)
        try:
            for item in cast(list[object], value):
                _ensure_json_value(item, active_container_ids, depth + 1)
        finally:
            active_container_ids.remove(container_id)
        return
    if value_type is dict:
        container_id = id(value)
        if container_id in active_container_ids:
            raise ValueError("payload must contain only JSON values")
        active_container_ids.add(container_id)
        try:
            for key, item in cast(dict[object, object], value).items():
                if type(key) is not str:
                    raise ValueError("payload must contain only JSON values")
                _ensure_json_value(item, active_container_ids, depth + 1)
        finally:
            active_container_ids.remove(container_id)
        return
    raise ValueError("payload must contain only JSON values")


def validate_json_payload(value: object) -> dict[str, Any]:
    if type(value) is not dict:
        raise ValueError("payload must contain only JSON values")
    _ensure_json_value(value, set(), 0)
    return cast(dict[str, Any], value)
