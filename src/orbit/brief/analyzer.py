"""项目目录分析——从目录结构推断技术栈+依赖+入口点。

从 brief/generator.py 拆分。
"""

from __future__ import annotations

import os
from pathlib import Path

import structlog

from orbit.brief.models import ProjectAnalysis

logger = structlog.get_logger("orbit.brief")


def analyze_directory(project_path: str) -> ProjectAnalysis:
    """扫描项目目录，提取语言、框架、文件统计信息。

    WHY 纯文件系统扫描: 不依赖 CodeGraph——在 CodeGraph 未构建时也能工作。
    CodeGraph 的详细符号分析由 BriefGenerator 调用方决定是否注入。

    检测规则:
    - Python: pyproject.toml / setup.py / requirements.txt
    - TypeScript: tsconfig.json / package.json
    - Rust: Cargo.toml
    - Go: go.mod
    """
    analysis = ProjectAnalysis()
    root = Path(project_path)

    if not root.is_dir():
        return analysis

    # 收集所有文件
    all_files: list[Path] = []
    ignore_dirs = {".git", "__pycache__", "node_modules", ".venv", "venv", "build", "dist",
                   ".orbit", "data", "Deliverables", "target", ".next", ".turbo"}

    for dirpath, dirnames, filenames in os.walk(project_path):
        # 跳过忽略目录
        dirnames[:] = [d for d in dirnames if d not in ignore_dirs]

        for fname in filenames:
            filepath = Path(dirpath) / fname
            all_files.append(filepath)

    analysis.file_count = len(all_files)

    # 按扩展名统计
    ext_map: dict[str, int] = {}
    for f in all_files:
        ext = f.suffix.lower()
        ext_map[ext] = ext_map.get(ext, 0) + 1

    analysis.python_files = ext_map.get(".py", 0)
    analysis.ts_files = ext_map.get(".ts", 0) + ext_map.get(".tsx", 0)
    analysis.js_files = ext_map.get(".js", 0) + ext_map.get(".jsx", 0)
    analysis.other_files = sum(
        n for ext, n in ext_map.items()
        if ext not in (".py", ".ts", ".tsx", ".js", ".jsx")
    )

    # 检测语言和框架
    file_names = {f.name for f in all_files}
    rel_paths = {str(f.relative_to(root)) for f in all_files}

    if "pyproject.toml" in file_names or "setup.py" in file_names:
        analysis.language = "python"
        analysis.framework = _detect_python_framework(file_names, rel_paths)
    elif "package.json" in file_names:
        analysis.language = "typescript" if analysis.ts_files > analysis.js_files else "javascript"
        analysis.framework = _detect_js_framework(file_names, rel_paths)
    elif "Cargo.toml" in file_names:
        analysis.language = "rust"
    elif "go.mod" in file_names:
        analysis.language = "go"

    # 检测依赖
    analysis.dependencies = _detect_dependencies(file_names, root)

    # 提取关键文件（非忽略目录下的顶层配置和入口文件）
    key_patterns = [
        "pyproject.toml", "package.json", "Cargo.toml", "go.mod",
        "README.md", "CLAUDE.md", "Makefile", "docker-compose.yml",
    ]
    analysis.key_files = [
        str(f.relative_to(root)) for f in all_files
        if f.name in key_patterns and str(f.relative_to(root)).count("/") <= 3
    ]

    # 生成目录树文本（前 80 行，避免 token 爆炸）
    tree_lines = _build_directory_tree(project_path, ignore_dirs, max_lines=80)
    analysis.directory_tree = "\n".join(tree_lines)

    return analysis


def _detect_python_framework(file_names: set[str], rel_paths: set[str] | None = None) -> str:
    """检测 Python 框架。"""
    # WHY 合并两个来源: file_names 来自依赖列表(如 fastapi==0.110.0),
    # rel_paths 来自目录扫描(如 src/api/routes/)。统一迭代做子串匹配。
    # set() 转换兼容测试传入 list/dict 的情况。
    all_paths = set(file_names) | (set(rel_paths) if rel_paths else set())
    frameworks: list[str] = []
    for path_str in all_paths:
        if "fastapi" in path_str.lower():
            frameworks.append("FastAPI")
            break
    for path_str in all_paths:
        if "django" in path_str.lower():
            frameworks.append("Django")
            break
    for path_str in all_paths:
        if "flask" in path_str.lower():
            frameworks.append("Flask")
            break
    # 检查是否有 SQLAlchemy 模型
    for path_str in all_paths:
        if "sqlalchemy" in path_str.lower() or "model" in path_str.lower():
            if "SQLAlchemy" not in frameworks:
                frameworks.append("SQLAlchemy")
            break
    return ", ".join(frameworks) if frameworks else ""


def _detect_js_framework(file_names: set[str], rel_paths: set[str] | None = None) -> str:
    """检测 JS/TS 框架。"""
    # set() 转换兼容测试传入 list/dict 的情况。
    all_paths = set(file_names) | (set(rel_paths) if rel_paths else set())
    frameworks: list[str] = []
    for path_str in all_paths:
        if "next.config" in path_str:
            frameworks.append("Next.js")
            break
    for path_str in all_paths:
        if "vite.config" in path_str:
            frameworks.append("Vite")
            break
    for path_str in all_paths:
        if "react" in path_str.lower():
            frameworks.append("React")
            break
    for path_str in all_paths:
        if "vue" in path_str.lower():
            frameworks.append("Vue")
            break
    return ", ".join(frameworks) if frameworks else ""


def _detect_dependencies(file_names: set[str], root: Path) -> list[str]:
    """从包管理文件中提取依赖列表（前 30 个）。"""
    deps: list[str] = []
    # Python
    pyproject = root / "pyproject.toml"
    if pyproject.is_file():
        try:
            content = pyproject.read_text(encoding="utf-8")
            in_deps = False
            for line in content.split("\n"):
                stripped = line.strip()
                if stripped.startswith("[") and "dependencies" in stripped.lower():
                    in_deps = True
                    continue
                if in_deps and stripped.startswith("["):
                    break
                if in_deps and "=" in stripped and not stripped.startswith("#"):
                    dep_name = stripped.split("=")[0].strip().strip('"').strip("'")
                    if dep_name and dep_name != "python":
                        deps.append(dep_name)
        except Exception:
            pass

    # Node
    pkg_json = root / "package.json"
    if pkg_json.is_file():
        try:
            import json
            data = json.loads(pkg_json.read_text(encoding="utf-8"))
            for dep_type in ("dependencies", "devDependencies"):
                deps.extend(list(data.get(dep_type, {}).keys()))
        except Exception:
            pass

    return deps[:30]  # 最多 30 个，避免 token 爆炸


def _extract_section(text: str, section_title: str) -> str:
    """从 markdown 文本中提取指定段落内容。

    WHY 简单字符串操作: brief.md 是 LLM 生成的固定格式，
    不需要完整 markdown 解析器。
    """
    # 支持 "## N. 标题" 和 "## 标题" 两种格式
    for prefix in (f"## {section_title}", f"##{section_title}"):
        if prefix in text:
            idx = text.index(prefix)
            start = idx + len(prefix)
            # 取到下一个 ## 或文末
            end_idx = text.find("\n## ", start)
            section = text[start:] if end_idx == -1 else text[start:end_idx]
            return section.strip()
    return ""


def _build_directory_tree(
    project_path: str, ignore_dirs: set[str], max_lines: int = 80
) -> list[str]:
    """生成缩进目录树文本。

    WHY 限制行数: 大项目的目录树本身就能占 2000+ token，对说明书没有边际收益。
    """
    lines: list[str] = []
    root = Path(project_path)

    def _walk(current: Path, indent: str = "") -> None:
        if len(lines) >= max_lines:
            return
        try:
            entries = sorted(current.iterdir(), key=lambda e: (not e.is_dir(), e.name.lower()))
        except PermissionError:
            return
        for entry in entries:
            if len(lines) >= max_lines:
                return
            if entry.name.startswith(".") or entry.name in ignore_dirs:
                continue
            if entry.is_dir():
                lines.append(f"{indent}├── {entry.name}/")
                _walk(entry, indent + "│   ")
            else:
                lines.append(f"{indent}├── {entry.name}")

    lines.append(f"{root.name}/")
    _walk(root, "")
    return lines


