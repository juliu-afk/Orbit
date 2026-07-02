"""Orbit CLI 命令实现。"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from orbit.brief.package_library import DEFAULT_LIBRARY_PATH, INDEX_FILE, PackageLibrary

# ── 内置模板数据 ─────────────────────────────────────────
# WHY 内置: 首次安装 Orbit 时无需联网即可初始化。
# 三个最小模板覆盖 Python 后端 / 前端 / CLI 三种常见场景。

BUILTIN_TEMPLATES: dict[str, dict[str, str]] = {
    "python-fastapi-minimal": {
        "manifest.yaml": (
            "id: python-fastapi-minimal\n"
            "language: python\n"
            "framework: fastapi\n"
            "features:\n"
            "  - async\n"
            "  - pydantic\n"
            "  - sqlalchemy\n"
            "  - uv\n"
            'description: "FastAPI 最小后端模板"\n'
            "format: cookiecutter\n"
        ),
        "template/{{project_slug}}/pyproject.toml": (
            "[project]\n"
            "name = \"{{project_slug}}\"\n"
            "version = \"0.1.0\"\n"
            "requires-python = \">=3.11\"\n"
            "dependencies = [\n"
            '    "fastapi>=0.110",\n'
            '    "uvicorn[standard]",\n'
            '    "sqlalchemy[asyncio]>=2.0",\n'
            '    "pydantic>=2.0",\n'
            '    "python-dotenv",\n'
            '    "structlog",\n'
            "]\n"
        ),
        "template/{{project_slug}}/src/__init__.py": "",
        "template/{{project_slug}}/src/main.py": (
            '"""FastAPI 应用入口。"""\n\n'
            "from fastapi import FastAPI\n\n"
            'app = FastAPI(title="{{project_slug}}", version="0.1.0")\n\n\n'
            "@app.get(\"/health\")\n"
            "async def health():\n"
            '    return {"status": "ok"}\n'
        ),
        "template/{{project_slug}}/tests/test_health.py": (
            '"""健康检查端点测试。"""\n\n'
            "import pytest\n"
            "from httpx import ASGITransport, AsyncClient\n\n\n"
            "@pytest.fixture\n"
            "async def client():\n"
            "    from src.main import app\n"
            '    transport = ASGITransport(app=app)\n'
            '    async with AsyncClient(transport=transport, base_url="http://test") as ac:\n'
            "        yield ac\n\n\n"
            "@pytest.mark.asyncio\n"
            "async def test_health(client):\n"
            '    resp = await client.get("/health")\n'
            "    assert resp.status_code == 200\n"
            '    assert resp.json() == {"status": "ok"}\n'
        ),
    },
    "react-vite-minimal": {
        "manifest.yaml": (
            "id: react-vite-minimal\n"
            "language: typescript\n"
            "framework: react\n"
            "features:\n"
            "  - vite\n"
            "  - react-router\n"
            "  - strict\n"
            "  - vitest\n"
            'description: "React + Vite 最小前端模板"\n'
            "format: cookiecutter\n"
        ),
        "template/{{project_slug}}/package.json": (
            "{\n"
            '  "name": "{{project_slug}}",\n'
            '  "private": true,\n'
            '  "version": "0.1.0",\n'
            '  "type": "module",\n'
            '  "scripts": {\n'
            '    "dev": "vite",\n'
            '    "build": "tsc && vite build",\n'
            '    "test": "vitest run"\n'
            "  },\n"
            '  "dependencies": {"react": "^18.3", "react-dom": "^18.3"},\n'
            '  "devDependencies": {\n'
            '    "typescript": "^5.4",\n'
            '    "vite": "^5.0",\n'
            '    "vitest": "^1.0"\n'
            "  }\n"
            "}\n"
        ),
        "template/{{project_slug}}/tsconfig.json": (
            "{\n"
            '  "compilerOptions": {\n'
            '    "target": "ES2020",\n'
            '    "module": "ESNext",\n'
            '    "moduleResolution": "bundler",\n'
            '    "jsx": "react-jsx",\n'
            '    "strict": true,\n'
            '    "noEmit": true\n'
            "  },\n"
            '  "include": ["src"]\n'
            "}\n"
        ),
    },
    "python-cli-minimal": {
        "manifest.yaml": (
            "id: python-cli-minimal\n"
            "language: python\n"
            "framework: click\n"
            "features:\n"
            "  - cli\n"
            "  - uv\n"
            "  - pytest\n"
            'description: "Python CLI 最小模板"\n'
            "format: cookiecutter\n"
        ),
        "template/{{project_slug}}/pyproject.toml": (
            "[project]\n"
            "name = \"{{project_slug}}\"\n"
            "version = \"0.1.0\"\n"
            "requires-python = \">=3.11\"\n"
            "dependencies = [\"click>=8.0\"]\n\n"
            "[project.scripts]\n"
            "cli = \"src.cli:main\"\n"
        ),
        "template/{{project_slug}}/src/cli.py": (
            '"""CLI 入口。"""\n\n'
            "import click\n\n\n"
            "@click.command()\n"
            '@click.option("--name", default="World")\n'
            "def main(name: str) -> None:\n"
            '    click.echo(f"Hello, {name}!")\n\n\n'
            'if __name__ == "__main__":\n'
            "    main()\n"
        ),
    },
}

# index.json 内容
BUILTIN_INDEX = [
    {
        "id": "python-fastapi-minimal",
        "language": "python",
        "framework": "fastapi",
        "features": ["async", "pydantic", "sqlalchemy", "uv"],
        "description": "FastAPI 最小后端模板——含异步路由、Pydantic 模型、SQLAlchemy 异步会话、pytest 测试骨架",
        "file_count": 6,
        "estimated_tokens": 1800,
        "cookiecutter_compat": True,
        "path": "python-fastapi-minimal/",
    },
    {
        "id": "react-vite-minimal",
        "language": "typescript",
        "framework": "react",
        "features": ["vite", "react-router", "strict", "vitest"],
        "description": "React + Vite 最小前端模板——TypeScript strict 模式、React Router、Vitest 测试",
        "file_count": 3,
        "estimated_tokens": 1500,
        "cookiecutter_compat": True,
        "path": "react-vite-minimal/",
    },
    {
        "id": "python-cli-minimal",
        "language": "python",
        "framework": "click",
        "features": ["cli", "uv", "pytest"],
        "description": "Python CLI 最小模板——Click 命令解析、uv 包管理、pytest 测试",
        "file_count": 2,
        "estimated_tokens": 800,
        "cookiecutter_compat": True,
        "path": "python-cli-minimal/",
    },
]


def cmd_init_packages() -> None:
    """初始化基础代码包库——写入 3 个内置模板到 ~/.orbit/base-packages/。

    WHY 内置而非远程拉取: 离线可用，零网络依赖。
    如果库已存在（index.json 非空），询问是否覆盖。
    """
    lib_dir = DEFAULT_LIBRARY_PATH
    index_path = os.path.join(lib_dir, INDEX_FILE)

    # 检查是否已初始化
    if os.path.isfile(index_path):
        try:
            import json
            existing = json.loads(Path(index_path).read_text(encoding="utf-8"))
            if existing:
                print(f"基础代码包库已存在: {lib_dir}")
                print(f"已有 {len(existing)} 个模板。")
                try:
                    answer = input("覆盖现有模板？[y/N] ")
                    if answer.lower() != "y":
                        print("跳过初始化。")
                        return
                except EOFError:
                    # 非交互模式——跳过
                    print("非交互模式，跳过覆盖。使用 --force 强制覆盖。")
                    return
        except (json.JSONDecodeError, OSError):
            pass  # 索引损坏，继续初始化

    # 写入模板文件
    os.makedirs(lib_dir, exist_ok=True)
    total_files = 0
    for pkg_id, files in BUILTIN_TEMPLATES.items():
        pkg_dir = os.path.join(lib_dir, pkg_id)
        for rel_path, content in files.items():
            abs_path = os.path.join(pkg_dir, rel_path)
            os.makedirs(os.path.dirname(abs_path), exist_ok=True)
            Path(abs_path).write_text(content, encoding="utf-8")
            total_files += 1

    # 写入 index.json
    import json
    Path(index_path).write_text(
        json.dumps(BUILTIN_INDEX, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"初始化完成: {lib_dir}")
    print(f"  {len(BUILTIN_TEMPLATES)} 个模板, {total_files} 个文件")


def cmd_brief_check(path: str) -> None:
    """检查/生成项目说明书。无 API 依赖，直接用 LLMClient。

    Usage:
        orbit brief check /path/to/project
    """
    # 验证路径
    project_path = os.path.abspath(path)
    if not os.path.isdir(project_path):
        print(f"错误: 路径不存在或不是目录: {project_path}")
        sys.exit(1)

    from orbit.brief.checker import check_brief

    status = check_brief(project_path)

    print(f"项目: {project_path}")
    print(f"  .orbit/brief.md:     {'存在' if status.has_brief else '缺失'}")
    print(f"  .orbit/boundaries/:  {'存在' if status.has_boundaries else '缺失'}")
    print(f"  .orbit/base/:        {'存在' if status.has_base_package else '缺失'}")

    if status.has_brief:
        print("\n现有说明书内容（前 500 字符）:")
        from orbit.brief.storage import read_brief
        brief = read_brief(project_path)
        if brief:
            for s in brief.sections[:3]:
                print(f"\n## {s.title}")
                print(s.content[:150])
        return

    # 无说明书——尝试生成
    print("\n说明书不存在。正在用 GLM-5.2 生成...")

    # 初始化 LLMClient
    from orbit.core.config import settings
    from orbit.gateway.client import MODEL_GLM5, LLMClient

    if not settings.ZAI_API_KEY or settings.ZAI_API_KEY == "sk-dummy":
        print("错误: 未配置 ZAI_API_KEY（智谱 API 密钥），无法调用 GLM-5.2。")
        print("请在 .env 文件设置 ZAI_API_KEY 后重试。")
        sys.exit(1)

    import asyncio

    async def _gen() -> None:
        llm = LLMClient(default_model=MODEL_GLM5)
        from orbit.brief.boundaries import BoundaryEngine
        from orbit.brief.generator import BriefGenerator, analyze_directory
        from orbit.brief.storage import write_boundaries, write_brief

        gen = BriefGenerator(llm)
        analysis = analyze_directory(project_path)
        brief = await gen.generate(project_path, analysis=analysis)
        write_brief(project_path, brief)

        engine = BoundaryEngine()
        write_boundaries(project_path, engine.generate_rules_yaml())

        # CONTEXT.md
        await gen.generate_all_context_md(project_path, brief, min_subdirs=2)

        print(f"\n生成完成!")
        print(f"  语言: {analysis.language}")
        print(f"  框架: {analysis.framework or '未检测到'}")
        print(f"  段落数: {len(brief.sections)}")
        print(f"  生成模型: {brief.generated_by}")

    asyncio.run(_gen())
