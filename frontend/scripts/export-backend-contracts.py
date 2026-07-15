from __future__ import annotations

import ast
import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Any, get_args, get_type_hints

from pydantic import BaseModel

from agent_platform.bootstrap.app_factory import create_app
from agent_platform.config.settings import Settings
from agent_platform.domain.contracts import (
    ArtifactRef,
    CapabilityRequest,
    ProjectCheckpointRef,
    RoleCard,
    Stage,
    StageContract,
    StageRunState,
    ToolExecutionRequest,
    ToolResult,
    load_stage_contracts,
)
from agent_platform.domain.events import EventEnvelope
from agent_platform.domain.workflows import WorkflowStatus
from agent_platform.infrastructure.resources.role_cards import PackageRoleCardLoader
from agent_platform.infrastructure.tooling.catalog import ToolCatalog
from agent_platform.interfaces.api.routes.events import EventTicketResponse
from agent_platform.interfaces.api.routes.stage5 import control_workflow

FRONTEND_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = FRONTEND_ROOT.parent
CONTRACTS_ROOT = FRONTEND_ROOT / "contracts"
EVENT_TYPE_PATTERN = re.compile(r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+$")
ERROR_HELPERS = {"_conflict", "_not_found", "_permission", "_unavailable", "_validation"}


def _git(*arguments: str) -> str:
    return subprocess.check_output(
        ["git", *arguments],
        cwd=REPOSITORY_ROOT,
        text=True,
        encoding="utf-8",
    ).strip()


def _metadata() -> dict[str, object]:
    return {
        "schemaVersion": 1,
        "backendCommit": _git("log", "-1", "--format=%H", "--", "backend"),
        "backendTree": _git("rev-parse", "HEAD:backend"),
        "generator": "frontend/scripts/export-backend-contracts.py",
    }


def _write_json(file_name: str, document: dict[str, Any]) -> None:
    CONTRACTS_ROOT.mkdir(parents=True, exist_ok=True)
    target = CONTRACTS_ROOT / file_name
    target.write_text(
        json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _constant_event_types(expression: ast.expr) -> set[str]:
    if isinstance(expression, ast.Constant) and isinstance(expression.value, str):
        if EVENT_TYPE_PATTERN.fullmatch(expression.value):
            return {expression.value}
        return set()
    if isinstance(expression, ast.IfExp):
        return _constant_event_types(expression.body) | _constant_event_types(expression.orelse)
    return set()


def _collect_event_types() -> list[str]:
    event_types: set[str] = set()
    application_root = REPOSITORY_ROOT / "backend" / "src" / "agent_platform" / "application"
    for source_path in application_root.rglob("*.py"):
        tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
        for node in ast.walk(tree):
            if isinstance(node, ast.keyword) and node.arg == "event_type":
                event_types.update(_constant_event_types(node.value))
            elif isinstance(node, ast.Assign) and any(
                isinstance(target, ast.Name) and target.id == "event_type"
                for target in node.targets
            ):
                event_types.update(_constant_event_types(node.value))

    control_action = get_type_hints(control_workflow, include_extras=True)["action"]
    for action in get_args(control_action):
        if not isinstance(action, str):
            continue
        event_types.add("workflow.stopped" if action == "stop" else f"workflow.{action}d")
    return sorted(event_types)


def _called_name(call: ast.Call) -> str | None:
    if isinstance(call.func, ast.Name):
        return call.func.id
    if isinstance(call.func, ast.Attribute):
        return call.func.attr
    return None


def _collect_error_codes() -> list[str]:
    error_codes: set[str] = set()
    backend_source = REPOSITORY_ROOT / "backend" / "src"
    for source_path in backend_source.rglob("*.py"):
        tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
        for node in ast.walk(tree):
            if isinstance(node, ast.keyword) and node.arg in {"code", "error_code"}:
                error_codes.update(_constant_event_types(node.value))
            elif isinstance(node, ast.Assign) and any(
                isinstance(target, ast.Name) and target.id == "error_code"
                for target in node.targets
            ):
                error_codes.update(_constant_event_types(node.value))
            elif isinstance(node, ast.Call) and _called_name(node) in ERROR_HELPERS and node.args:
                error_codes.update(_constant_event_types(node.args[0]))
    return sorted(error_codes)


def _operation_id(capabilities: dict[str, dict[str, str]], method: str, path: str) -> str:
    matches = [
        operation_id
        for operation_id, operation in capabilities.items()
        if operation == {"method": method, "path": path}
    ]
    if len(matches) != 1:
        raise RuntimeError(f"Expected one operation for {method} {path}, found {len(matches)}")
    return matches[0]


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def _inject_shared_contract_schemas(openapi: dict[str, Any]) -> None:
    components = openapi.setdefault("components", {}).setdefault("schemas", {})
    shared_models: tuple[type[BaseModel], ...] = (
        StageContract,
        RoleCard,
        EventEnvelope,
        ToolExecutionRequest,
        ToolResult,
        CapabilityRequest,
        ProjectCheckpointRef,
        ArtifactRef,
    )
    for model in shared_models:
        schema = model.model_json_schema(ref_template="#/components/schemas/{model}")
        definitions = schema.pop("$defs", {})
        for name, definition in definitions.items():
            components.setdefault(name, definition)
        components.setdefault(model.__name__, schema)


def main() -> None:
    metadata = _metadata()
    app = create_app(
        Settings(
            session_token="frontend-contract-export",
            data_root=REPOSITORY_ROOT / ".runtime" / "frontend-contract-export",
        )
    )
    openapi = app.openapi()
    _inject_shared_contract_schemas(openapi)
    openapi["x-agentprogram-contract"] = metadata
    capabilities: dict[str, dict[str, str]] = {}
    for path, path_item in openapi["paths"].items():
        for method, operation in path_item.items():
            if method not in {"get", "post", "put", "patch", "delete"}:
                continue
            operation_id = operation.get("operationId")
            if not isinstance(operation_id, str) or not operation_id:
                raise RuntimeError(
                    f"REST operation is missing operationId: {method.upper()} {path}"
                )
            capabilities[operation_id] = {
                "method": method.upper(),
                "path": path,
            }

    _write_json("openapi.json", openapi)
    _write_json(
        "events.schema.json",
        {
            **metadata,
            "envelopeSchema": EventEnvelope.model_json_schema(),
            "eventTypes": _collect_event_types(),
        },
    )
    _write_json(
        "capabilities.json",
        {
            **metadata,
            "capabilities": capabilities,
            "websocket": {
                "schemaVersion": 1,
                "path": EventTicketResponse.model_fields["websocket_path"].default,
                "ticketOperationId": _operation_id(capabilities, "POST", "/api/v1/events/tickets"),
                "replayOperationId": _operation_id(capabilities, "GET", "/api/v1/events/replay"),
                "readyMessageType": "ready",
                "eventMessageType": "event",
            },
            "workflowStates": [state.value for state in WorkflowStatus],
            "stageRunStates": [state.value for state in StageRunState],
            "stages": [stage.value for stage in Stage],
            "stageContracts": [
                contract.model_dump(mode="json") for contract in load_stage_contracts()
            ],
            "roleCards": [
                {
                    "schema_version": role_card.schema_version,
                    "role_id": role_card.role_id.value,
                    "stage_id": role_card.stage_id.value,
                    "display_name": role_card.display_name,
                    "role_card_version": role_card.role_card_version,
                    "language": role_card.language,
                    "content_hash": role_card.content_hash,
                }
                for role_card in PackageRoleCardLoader().load_all()
            ],
            "tools": [tool.model_dump(mode="json") for tool in ToolCatalog().list()],
            "errorCodes": _collect_error_codes(),
        },
    )
    _write_json(
        "SHA256SUMS.json",
        {
            **metadata,
            "files": {
                file_name: _file_sha256(CONTRACTS_ROOT / file_name)
                for file_name in (
                    "openapi.json",
                    "events.schema.json",
                    "capabilities.json",
                )
            },
        },
    )


if __name__ == "__main__":
    main()
