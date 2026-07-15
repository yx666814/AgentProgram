from pathlib import Path

import pytest

from agent_platform.domain.shared.errors import DomainError
from agent_platform.infrastructure.model_runtime import ModelOutputStore


def test_model_output_store_is_content_addressed_and_verified(tmp_path: Path) -> None:
    store = ModelOutputStore(tmp_path / "outputs", max_output_bytes=1024)

    first = store.write("same output")
    second = store.write("same output")

    assert first == second
    assert store.read(first.reference, first.content_hash) == "same output"
    assert len(list((tmp_path / "outputs").glob("??/*.txt"))) == 1


def test_model_output_store_rejects_tampering(tmp_path: Path) -> None:
    root = tmp_path / "outputs"
    store = ModelOutputStore(root, max_output_bytes=1024)
    stored = store.write("verified output")
    (root / stored.reference).write_text("tampered", encoding="utf-8")

    with pytest.raises(DomainError, match="verified"):
        store.read(stored.reference, stored.content_hash)
