# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules, copy_metadata


backend_root = Path(SPECPATH).parent
datas = collect_data_files("agent_platform") + copy_metadata("agent-platform-backend")
datas += [
    (str(backend_root / "alembic.ini"), "."),
    (str(backend_root / "migrations"), "migrations"),
]
hiddenimports = sorted(
    set(
        collect_submodules("alembic")
        + collect_submodules("agent_platform")
        + collect_submodules("aiosqlite")
        + collect_submodules("sqlalchemy.dialects.sqlite")
        + collect_submodules("uvicorn")
    )
)

a = Analysis(
    [str(backend_root / "packaging" / "desktop_sidecar_entry.py")],
    pathex=[str(backend_root / "src")],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["pytest", "mypy", "ruff"],
    noarchive=False,
    optimize=1,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="agent-platform-desktop-sidecar",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="agent-platform-desktop-sidecar",
)
