from __future__ import annotations

import hashlib
import json
import os
import stat
from dataclasses import dataclass
from pathlib import Path

from agent_platform.domain.projects import PersistedProjectManifest, ProjectRegistration

_WINDOWS_REPARSE_POINT = 0x400
_ALWAYS_EXCLUDED = frozenset({".agent", ".git", ".venv", "node_modules"})
_TEXT_FILE_BYTES = 64 * 1024
_STRUCTURE_FILE_LIMIT = 2000


@dataclass(frozen=True, slots=True)
class ProjectContextSnapshot:
    text: str
    included_hashes: dict[str, str]


def build_project_context(
    registration: ProjectRegistration,
    persisted_manifest: PersistedProjectManifest,
    *,
    max_characters: int,
) -> ProjectContextSnapshot:
    root = Path(registration.workspace.root_path).resolve(strict=True)
    manifest = persisted_manifest.manifest
    excluded = tuple({*_ALWAYS_EXCLUDED, *manifest.excluded_paths})
    files = _workspace_files(root, excluded)
    manifest_text = json.dumps(
        manifest.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        indent=2,
    )
    header = (
        f"Project name: {registration.project.name}\n"
        f"Project goal: {registration.project.goal}\n"
        f"Workspace mode: {registration.workspace.mode.value}\n"
        f"ProjectManifest:\n{manifest_text}\n\n"
        "Workspace structure (project-relative paths):\n"
    )
    structure = "\n".join(path for path, _ in files[:_STRUCTURE_FILE_LIMIT])
    if len(files) > _STRUCTURE_FILE_LIMIT:
        structure += f"\n... {len(files) - _STRUCTURE_FILE_LIMIT} additional files omitted"
    parts = [header, structure, "\n\nUTF-8 file contents and current SHA-256 values:\n"]
    used = sum(len(part) for part in parts)
    included_hashes: dict[str, str] = {}
    for relative_path, path in _prioritize(files, manifest.source_paths):
        if used >= max_characters:
            break
        try:
            metadata = path.lstat()
            if metadata.st_size > _TEXT_FILE_BYTES or _is_link_or_reparse(metadata):
                continue
            payload = path.read_bytes()
            if b"\x00" in payload:
                continue
            content = payload.decode("utf-8")
        except (OSError, UnicodeError):
            continue
        digest = hashlib.sha256(payload).hexdigest()
        section = f"\n--- {relative_path} sha256={digest}\n{content}\n"
        remaining = max_characters - used
        if len(section) > remaining:
            continue
        parts.append(section)
        included_hashes[relative_path] = digest
        used += len(section)
    return ProjectContextSnapshot(text="".join(parts).strip(), included_hashes=included_hashes)


def _workspace_files(root: Path, excluded: tuple[str, ...]) -> list[tuple[str, Path]]:
    found: list[tuple[str, Path]] = []
    for directory, names, filenames in os.walk(root, topdown=True, followlinks=False):
        current = Path(directory)
        names[:] = [
            name
            for name in sorted(names)
            if not _excluded(_relative(root, current / name), excluded)
            and not _unsafe_directory(current / name)
        ]
        for name in sorted(filenames):
            path = current / name
            relative = _relative(root, path)
            if _excluded(relative, excluded):
                continue
            try:
                metadata = path.lstat()
            except OSError:
                continue
            if stat.S_ISREG(metadata.st_mode) and not _is_link_or_reparse(metadata):
                found.append((relative, path))
    return found


def _prioritize(
    files: list[tuple[str, Path]],
    source_paths: tuple[str, ...],
) -> list[tuple[str, Path]]:
    def priority(item: tuple[str, Path]) -> tuple[int, str]:
        relative = item[0]
        if relative.startswith("artifacts/"):
            return (0, relative)
        if any(relative == prefix or relative.startswith(f"{prefix}/") for prefix in source_paths):
            return (1, relative)
        if _looks_like_project_code(relative):
            return (2, relative)
        return (3, relative)

    return sorted(files, key=priority)


def _looks_like_project_code(path: str) -> bool:
    name = path.rsplit("/", maxsplit=1)[-1]
    return name in {
        "package.json",
        "pyproject.toml",
        "requirements.txt",
        "tsconfig.json",
        "vite.config.ts",
        "Cargo.toml",
        "go.mod",
    } or name.endswith(
        (
            ".c",
            ".cpp",
            ".css",
            ".go",
            ".h",
            ".html",
            ".java",
            ".js",
            ".json",
            ".jsx",
            ".md",
            ".py",
            ".rs",
            ".toml",
            ".ts",
            ".tsx",
            ".yaml",
            ".yml",
        )
    )


def _excluded(path: str, excluded: tuple[str, ...]) -> bool:
    return any(path == prefix or path.startswith(f"{prefix}/") for prefix in excluded)


def _relative(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def _unsafe_directory(path: Path) -> bool:
    try:
        metadata = path.lstat()
    except OSError:
        return True
    return not stat.S_ISDIR(metadata.st_mode) or _is_link_or_reparse(metadata)


def _is_link_or_reparse(metadata: os.stat_result) -> bool:
    return stat.S_ISLNK(metadata.st_mode) or bool(
        getattr(metadata, "st_file_attributes", 0) & _WINDOWS_REPARSE_POINT
    )
