# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec——Orbit 桌面版。

前端 static/ 作为数据目录打包，FastAPI 启动后自动 serve。
"""

import os
import sys
from pathlib import Path

# 项目根目录 (spec 在 backend/, 根目录是其父目录)
ROOT = Path(SPECPATH).resolve().parent

a = Analysis(
    [str(ROOT / "src" / "orbit" / "launcher.py")],
    pathex=[str(ROOT / "src")],
    binaries=[],
    datas=[
        (str(ROOT / "backend" / "static"), "static"),
    ],
    hiddenimports=[
        "uvicorn",
        "uvicorn.loops",
        "uvicorn.protocols",
        "orbit.agents",
        "orbit.agents.base",
        "orbit.agents.factory",
        "orbit.agents.context",
        "orbit.communication",
        "orbit.communication.protocol",
        "orbit.communication.message_bus",
        "orbit.tools",
        "orbit.tools.models",
        "orbit.tools.registry",
        "orbit.backup",
        "orbit.backup.models",
        "orbit.backup.snapshot",
        "orbit.backup.restore",
        "orbit.backup.integrity",
        "orbit.context",
        "orbit.context.matcher",
        "orbit.projects",
        "orbit.projects.models",
        "orbit.projects.registry",
        "orbit.sessions",                # Session PR
        "orbit.sessions.models",         # Session PR
        "orbit.sessions.registry",       # Session PR
        "orbit.api.routes.sessions",     # Session PR
        "orbit.api.routes.projects",     # Session PR
        "orbit.resource_guard",
        "orbit.resource_guard.models",
        "orbit.resource_guard.token_bucket",
        "orbit.resource_guard.budget_guard",
        "orbit.resource_guard.degradation",
        "orbit.resource_guard.resource_guard",
        "orbit.scheduler.resource_scheduler",
        "orbit.scheduler.clarifier",
        "orbit.versioning",
        "orbit.versioning.models",
        "orbit.versioning.registry",
        "orbit.graph.meta_graph",
        "orbit.observability.config",
        "orbit.observability.metrics",
        "orbit.observability.audit",
        "orbit.observability.alerts",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="Orbit",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # Tauri 壳提供窗口，后端静默运行
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(ROOT / "frontend" / "public" / "favicon.ico") if os.path.exists(str(ROOT / "frontend" / "public" / "favicon.ico")) else None,
)
