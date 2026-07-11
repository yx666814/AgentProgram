import re
from uuid import uuid4

_PREFIX_PATTERN = re.compile(r"^[a-z][a-z0-9]*$", flags=re.ASCII)


def new_id(prefix: str) -> str:
    normalized = prefix.strip().lower()
    if _PREFIX_PATTERN.fullmatch(normalized) is None:
        raise ValueError("prefix must be an ASCII alphanumeric token starting with a letter")
    return f"{normalized}_{uuid4().hex}"
