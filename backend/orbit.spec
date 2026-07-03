# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec——Orbit 桌面版。

前端 static/ 作为数据目录打包，FastAPI 启动后自动 serve。
"""

import os
import sys
from pathlib import Path

import certifi  # noqa: E402  # WHY: 获取 cacert.pem 路径，打包进 exe
import litellm  # noqa: E402  # WHY: 获取 model_prices JSON 路径，打包进 exe
from PyInstaller.utils.hooks import collect_submodules  # noqa: E402

# 项目根目录 (spec 在 backend/, 根目录是其父目录)
ROOT = Path(SPECPATH).resolve().parent

# certifi CA bundle——PyInstaller 不会自动收集 .pem 数据文件
# WHY: HTTPS 请求需要 CA 证书验证，漏打包导致 FileNotFoundError
_CERTIFI_DIR = Path(certifi.where()).parent
# litellm 数据文件——PyInstaller 不会自动收集 .json 数据文件
# WHY: litellm 启动时加载 model_prices JSON，漏打包导致 FileNotFoundError
_LITELLM_DIR = Path(litellm.__file__).parent

# WHY collect_submodules: litellm 有大量子模块（llms/, proxy/, litellm_core_utils/ 等），
# 手动枚举 hiddenimports 不现实。一次性收集所有子模块 + 数据文件。
_litellm_imports = collect_submodules("litellm")

a = Analysis(
    [str(ROOT / "src" / "orbit" / "launcher.py")],
    pathex=[str(ROOT / "src")],
    binaries=[],
    datas=[
        (str(ROOT / "backend" / "static"), "static"),
        (str(_CERTIFI_DIR / "cacert.pem"), "certifi"),
        (str(_LITELLM_DIR / "model_prices_and_context_window_backup.json"), "litellm"),
    ],
    hiddenimports=[
        "litellm",  # WHY: _do_completion 动态 import，PyInstaller 检测不到
        *_litellm_imports,  # WHY: 收集所有 litellm 子模块
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
        "orbit.goal",
        "orbit.goal.models",
        "orbit.goal.process_guard",
        "orbit.goal.meta_orchestrator",
        "orbit.loop",
        "orbit.loop.scheduler",
        "orbit.compression.cascade",
        "orbit.observability.alerts",
        "aiosqlite",  # P0: PyInstaller 漏打包——SQLAlchemy async SQLite 依赖
        # Part A: 项目说明书模块
        "orbit.brief",
        "orbit.brief.models",
        "orbit.brief.checker",
        "orbit.brief.generator",
        "orbit.brief.storage",
        "orbit.brief.injector",
        "orbit.brief.boundaries",
        "orbit.brief.package_library",
        # Part B: Ponytail 决策阶梯
        "orbit.prompt.ponytail_rules",
        "orbit.review.ponytail",
        "orbit.api.routes.ponytail_debt",
        # CLI 模块
        "orbit.cli",
        "orbit.cli.commands",
        # WHY tiktoken_ext 是命名空间包，PyInstaller 无法自动收集
        # tiktoken 编码注册依赖此模块，漏打包导致 "Unknown encoding cl100k_base"
        "tiktoken_ext.openai_public",
    ],
    hookspath=[str(ROOT / "backend" / "hooks")],
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
