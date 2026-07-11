from uuid import uuid4


def new_id(prefix: str) -> str:
    normalized = prefix.strip().lower()
    if not normalized or "_" in normalized:
        raise ValueError("prefix must be a non-empty token without underscores")
    return f"{normalized}_{uuid4().hex}"
