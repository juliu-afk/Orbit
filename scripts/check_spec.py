"""PyInstaller spec 完整性验证。

检查项:
  1. 无重复 Analysis/EXE 定义（常见陷阱）
  2. THIRD_PARTY_DATAS 所有文件存在
  3. _HIDDEN_IMPORTS 所有模块可 import
  4. api.routes 文件 vs spec hiddenimports 交叉对比
  5. 关键依赖可 import

用法: python scripts/check_spec.py
退出码: 0=通过, 1=有缺失
"""

from __future__ import annotations

import ast
import importlib
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

EXIT = 0


def fail(msg: str) -> None:
    global EXIT
    print(f"  FAIL: {msg}")
    EXIT = 1


def ok(msg: str) -> None:
    print(f"  OK: {msg}")


def info(msg: str) -> None:
    print(f"  INFO: {msg}")


# ── 0. 检查重复的 Analysis/EXE 定义 ──
print("0. Structure check...")
spec_path = ROOT / "backend" / "orbit.spec"
spec_text = spec_path.read_text(encoding="utf-8")
tree = ast.parse(spec_text)

analysis_count = sum(1 for node in ast.walk(tree) if isinstance(node, ast.Call) and hasattr(node.func, 'id') and node.func.id == 'Analysis')  # type: ignore[arg-type]
exe_count = sum(1 for node in ast.walk(tree) if isinstance(node, ast.Call) and hasattr(node.func, 'id') and node.func.id == 'EXE')  # type: ignore[arg-type]
if analysis_count == 1:
    ok(f"Analysis 定义: {analysis_count} 个")
else:
    fail(f"Analysis count: {analysis_count} (expected 1 — duplicates cause missing files!)")
if exe_count == 1:
    ok(f"EXE count: {exe_count}")
else:
    fail(f"EXE count: {exe_count} (expected 1)")

# ── 在受控环境中 exec spec 提取列表 ──
# WHY exec 而非 import: spec 依赖 PyInstaller 的 SPECPATH/Analysis/PYZ/EXE 等符号
spec_globals: dict = {
    "__builtins__": __builtins__,
    "Path": Path,
    "os": os,
    "sys": sys,
}
spec_locals: dict = {}

class _FakeAnything:
    """通用假对象——接收任意参数，属性访问返回自身。"""
    def __init__(self, *args, **kwargs):
        pass
    def __getattr__(self, name):
        return self
    def __call__(self, *args, **kwargs):
        return self

_FakeAnalysis = _FakeAnything
_FakePYZ = _FakeAnything
_FakeEXE = _FakeAnything

spec_globals["Analysis"] = _FakeAnalysis
spec_globals["PYZ"] = _FakePYZ
spec_globals["EXE"] = _FakeEXE
spec_globals["SPECPATH"] = str(ROOT / "backend")  # SPECPATH = spec 所在目录, not file
spec_globals["certifi"] = __import__("certifi")
spec_globals["litellm"] = __import__("litellm")

try:
    exec(spec_text, spec_globals, spec_locals)
except Exception as e:
    fail(f"spec syntax error: {e}")
    sys.exit(1)

third_party_datas = spec_locals.get("THIRD_PARTY_DATAS", [])
hidden_imports = spec_locals.get("_HIDDEN_IMPORTS", [])

# ── 1. 数据文件存在性 ──
print("\n1. Third-party data files...")
if not third_party_datas:
    fail("THIRD_PARTY_DATAS 为空")
else:
    for src, dest in third_party_datas:
        if os.path.exists(src):
            ok(f"{Path(src).name} → {dest}")
        else:
            fail(f"file not found: {src}")

# ── 2. 重新运行 spec 自动发现逻辑，验证结果覆盖所有源文件 ──
print("\n2. Auto-discovery check...")
# 从 spec 的 exec 环境中取 _discover_orbit_modules 函数重新执行
_discover_fn = spec_locals.get("_discover_orbit_modules")
if _discover_fn is None:
    fail("_discover_orbit_modules not found in spec")
else:
    _src = ROOT / "src" / "orbit"
    _discovered = set(_discover_fn(_src))
    _spec_set = {m for m in hidden_imports if m.startswith("orbit.")}

    if _discovered != _spec_set:
        _missing = _discovered - _spec_set
        _stale = _spec_set - _discovered
        if _missing:
            for _m in sorted(_missing)[:10]:
                fail(f"missed by spec: {_m}")
            if len(_missing) > 10:
                fail(f"... and {len(_missing) - 10} more")
        if _stale:
            for _m in sorted(_stale)[:5]:
                info(f"stale (source gone): {_m}")
    else:
        ok(f"{len(_discovered)} orbit modules, 100%% auto-discovered")

# 验证基础设施导入
_infra = [m for m in hidden_imports if not m.startswith("orbit.")]
for _m in _infra:
    try:
        importlib.import_module(_m)
    except ModuleNotFoundError as e:
        fail(f"infra import failed: {_m} ({e})")
if _infra:
    ok(f"{len(_infra)} infra imports OK")

# ── 3. api.routes 交叉对比 ──
print("\n3. api.routes cross-check...")
spec_routes = {r for r in hidden_imports if r.startswith("orbit.api.routes.")}
routes_dir = ROOT / "src" / "orbit" / "api" / "routes"
actual_routes = set()
if routes_dir.is_dir():
    for f in routes_dir.glob("*.py"):
        if f.stem.startswith("_"):
            continue
        actual_routes.add(f"orbit.api.routes.{f.stem}")

# route file exists but not in spec
for r in sorted(actual_routes - spec_routes):
    fail(f"missing from spec: {r}")
# in spec but file doesn't exist
for r in sorted(spec_routes - actual_routes):
    fail(f"stale spec entry (file gone): {r}")
if not (actual_routes - spec_routes) and not (spec_routes - actual_routes):
    ok(f"{len(actual_routes)} route modules, all covered")

# ── 4. PyInstaller hooks 完整性 ──
# WHY: 第三方库（litellm/tiktoken 等）有隐式子模块+数据文件，
# PyInstaller 静态分析发现不了。hook 文件负责收集。
print("\n4. PyInstaller hooks...")
_hooks_dir = ROOT / "backend" / "hooks"
KNOWN_HOOKS: dict[str, int] = {
    # package_name → expected_min_modules (hook should collect at least this many)
    "litellm": 1500,  # 1727 actual — hook must collect vast majority
}
for _pkg, _min_modules in KNOWN_HOOKS.items():
    _hook_file = _hooks_dir / f"hook-{_pkg}.py"
    if not _hook_file.exists():
        fail(f"hook missing: {_hook_file}")
        continue
    try:
        _hook_spec = importlib.util.spec_from_file_location(f"hook_{_pkg}", _hook_file)
        _hook = importlib.util.module_from_spec(_hook_spec)
        _hook_spec.loader.exec_module(_hook)  # type: ignore[union-attr]
        _n_mods = len(getattr(_hook, "hiddenimports", []))
        _n_datas = len(getattr(_hook, "datas", []))
        if _n_mods >= _min_modules:
            ok(f"hook-{_pkg}: {_n_mods} modules, {_n_datas} data files")
        else:
            fail(f"hook-{_pkg}: only {_n_mods} modules (expected >= {_min_modules})")
        # 验证 datas 所有文件存在
        for _src, _dest in getattr(_hook, "datas", []):
            if not os.path.exists(_src):
                fail(f"hook-{_pkg} datas file not found: {_src}")
    except Exception as e:
        fail(f"hook-{_pkg} execution failed: {e}")

# ── 4.5 已知命名空间包 ──
# WHY: 命名空间包（如 tiktoken_ext）无 __init__.py，PyInstaller 不自动发现
print("\n4.5 Known namespace packages...")
_NAMESPACE_PACKAGES = ["tiktoken_ext", "tiktoken_ext.openai_public"]
for _ns in _NAMESPACE_PACKAGES:
    try:
        importlib.import_module(_ns)
        if _ns in hidden_imports:
            ok(f"namespace: {_ns}")
        else:
            fail(f"namespace '{_ns}' importable but NOT in hiddenimports")
    except ModuleNotFoundError:
        # 命名空间包可能不存在（未安装对应依赖）
        info(f"namespace '{_ns}' not installed, skipping")

# ── 5. 关键依赖 ──
print("\n5. Key dependencies...")
KEY_DEPS = ["certifi", "litellm", "dotenv", "pydantic", "structlog", "fastapi"]
for dep in KEY_DEPS:
    try:
        importlib.import_module(dep)
        ok(dep)
    except ModuleNotFoundError:
        fail(f"依赖缺失: {dep}")

print(f"\n{'='*40}")
if EXIT == 0:
    print("PASS: all checks passed")
else:
    print(f"FAIL: {EXIT} check(s) failed, fix before build")
sys.exit(EXIT)
