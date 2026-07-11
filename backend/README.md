# Agent Platform Backend

Windows-first local backend for the contract-driven five-stage multi-agent workflow.

## Development

```powershell
uv sync --group dev
uv run pytest
uv run ruff check .
uv run mypy src
```
