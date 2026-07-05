# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec——Orbit 桌面版。

前端 static/ 作为数据目录打包，FastAPI 启动后自动 serve。

⚠️ 修改本文件后运行 python scripts/check_spec.py 验证完整性。
"""

import os
import sys
from pathlib import Path

import certifi  # noqa: E402  # WHY: 获取 cacert.pem 路径，打包进 exe
import litellm  # noqa: E402  # WHY: 获取 model_prices JSON 路径，打包进 exe

# 项目根目录 (spec 在 backend/, 根目录是其父目录)
ROOT = Path(SPECPATH).resolve().parent

# ---- 第三方库数据文件（PyInstaller 不自动收集）----
# WHY: HTTPS 需要 CA 证书；litellm 启动时加载 model_prices JSON
_CERTIFI_DIR = Path(certifi.where()).parent
_LITELLM_DIR = Path(litellm.__file__).parent

THIRD_PARTY_DATAS: list[tuple[str, str]] = [
    (str(_CERTIFI_DIR / "cacert.pem"), "certifi"),
    (str(_LITELLM_DIR / "model_prices_and_context_window_backup.json"), "litellm"),
]

# ---- 自动发现所有 orbit 模块 ----
# WHY 自动扫描: 手动维护 hiddenimports 容易漏，每次新增模块都会忘记加。
# PyInstaller 冗余 hiddenimports 无害（只是多 import 一次），遗漏则 ModuleNotFoundError。
def _discover_orbit_modules(src_dir: Path) -> list[str]:
    """递归扫描 src/orbit/ 下所有 .py 文件，返回模块名列表。"""
    mods: list[str] = []
    for py in sorted(src_dir.rglob("*.py")):
        # 跳过 __pycache__、测试文件、.venv
        if "__pycache__" in str(py) or ".venv" in str(py):
            continue
        if py.stem.startswith("test_") or py.stem.startswith("_"):
            continue
        rel = py.relative_to(src_dir).with_suffix("")
        mod = "orbit." + ".".join(rel.parts)
        if mod.endswith(".__init__"):
            mod = mod[:-9]  # strip .__init__
        mods.append(mod)
    return sorted(set(mods))

_ORBIT_MODULES = _discover_orbit_modules(ROOT / "src" / "orbit")

# 基础设施 + 第三方隐式依赖（PyInstaller 静态分析发现不了）
_INFRA_IMPORTS: list[str] = [
    "uvicorn",
    "uvicorn.loops",
    "uvicorn.protocols",
    "aiosqlite",
    # tiktoken 命名空间包（litellm 依赖，PyInstaller 不自动发现）
    "tiktoken_ext",
    "tiktoken_ext.openai_public",
    # Phase A+B+C: 新包——auto-discover 跳过 __init__.py, PyInstaller 需显式声明
    "orbit.metacognition",
    "orbit.metacognition.monitor",
    "orbit.metacognition.triggers",
    "orbit.metacognition.classifier",
    "orbit.metacognition.hitl",
    "orbit.evolution",
    "orbit.evolution.distill",
    "orbit.evolution.anchor",
    "orbit.agents.reflection",
    "orbit.memory.episodic",
    "orbit.memory.profile",
    "orbit.observability.trajectory",
    "orbit.hallucination.pipeline",
    "orbit.context.builders", "orbit.context.prebuilders", "orbit.context.scanners",
    # PR#201: auto-discover 跳过 test_ 前缀模块——需显式声明
    "orbit.context.builders.test_builder",
    "orbit.context.scanners.test_coverage",
    "orbit.agents.preact", "orbit.agents.mcts",
    "orbit.memory.agentic", "orbit.metacognition.vigil", "orbit.tools.mcp_server",
]

_HIDDEN_IMPORTS = _INFRA_IMPORTS + _ORBIT_MODULES

a = Analysis(
    [str(ROOT / "src" / "orbit" / "launcher.py")],
    pathex=[str(ROOT / "src")],
    binaries=[],
    datas=[
        (str(ROOT / "backend" / "static"), "static"),
    ] + THIRD_PARTY_DATAS,
    hiddenimports=_HIDDEN_IMPORTS,
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
    icon=str(ROOT / "frontend" / "public" / "favicon.ico")
    if os.path.exists(str(ROOT / "frontend" / "public" / "favicon.ico"))
    else None,
)
