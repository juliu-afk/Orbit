"""基础代码包库 单元测试。"""

import json
import tempfile
from pathlib import Path

import pytest

from orbit.brief.models import BasePackage, PackageDecision
from orbit.brief.package_library import PackageLibrary


class TestPackageLibrary:
    @pytest.fixture
    def lib(self) -> PackageLibrary:
        """创建临时库用于测试。"""
        tmpdir = tempfile.mkdtemp()
        lib = PackageLibrary(library_path=tmpdir)
        # 注册两个测试包
        lib.register(
            package_id="test-py",
            language="python",
            framework="flask",
            features=["web", "sync"],
            description="Flask 测试包",
            template_files={"app.py": "from flask import Flask", "test.py": "def test(): pass"},
        )
        lib.register(
            package_id="test-ts",
            language="typescript",
            framework="react",
            features=["web", "spa"],
            description="React 测试包",
            template_files={"index.tsx": "export {}", "test.ts": "import {}"},
        )
        return lib

    def test_search_by_language(self, lib: PackageLibrary) -> None:
        results = lib.search(language="python")
        assert len(results) == 1
        assert results[0].id == "test-py"

    def test_search_by_framework(self, lib: PackageLibrary) -> None:
        results = lib.search(language="typescript", framework="react")
        assert len(results) == 1
        assert results[0].id == "test-ts"

    def test_search_no_match(self, lib: PackageLibrary) -> None:
        results = lib.search(language="rust")
        assert len(results) == 0

    def test_search_with_features(self, lib: PackageLibrary) -> None:
        # 用 test-py 独有的 "sync" feature 搜索
        results = lib.search(features=["sync"])
        assert len(results) == 1
        assert results[0].id == "test-py"

    def test_get_template_files(self, lib: PackageLibrary) -> None:
        files = lib.get_template_files("test-py")
        assert "app.py" in files
        assert files["app.py"] == "from flask import Flask"

    def test_get_skeleton(self, lib: PackageLibrary) -> None:
        skeleton = lib.get_skeleton("test-py")
        assert "app.py" in skeleton
        assert "test.py" in skeleton

    def test_get_template_files_nonexistent(self, lib: PackageLibrary) -> None:
        files = lib.get_template_files("nonexistent")
        assert files == {}

    def test_register_duplicate(self, lib: PackageLibrary) -> None:
        """重复注册应返回已有包。"""
        pkg = lib.register(
            package_id="test-py",
            language="python",
            description="重复注册",
        )
        assert pkg.description == "Flask 测试包"  # 旧值保留

    def test_default_path_is_home_dir(self) -> None:
        """验证默认路径使用用户目录——跨平台兼容。"""
        import os
        lib = PackageLibrary()
        assert ".orbit" in lib.library_path
        assert "base-packages" in lib.library_path

    def test_explicit_path_respected(self) -> None:
        """验证显式路径优先于默认。"""
        lib = PackageLibrary(library_path="D:/OrbitBasePackages")
        index = lib._load_index()
        # 真实 D 盘库应有至少 3 个初始包
        ids = {p.id for p in index}
        assert "python-fastapi-minimal" in ids
        assert "react-vite-minimal" in ids
        assert "python-cli-minimal" in ids
        # 检查字段完整性
        for pkg in index:
            assert pkg.id
            assert pkg.language
            assert pkg.file_count > 0
            assert pkg.estimated_tokens > 0

    @pytest.mark.asyncio
    async def test_decide_injection_full(self) -> None:
        """LLM 决策——空项目应 full 注入。"""
        # 使用 D:盘真实库以获取候选包
        lib = PackageLibrary(library_path="D:/OrbitBasePackages")
        candidates = lib.search(language="python", framework="fastapi")

        # Mock LLM 返回 full
        class MockResponse:
            content = '{"decision": "full", "package_ids": ["python-fastapi-minimal"], "reason": "项目为空，需要模板引导"}'
            model = "openai/glm-5.2"

        class MockLLM:
            async def generate(self, req, task_id, agent_name=""):
                return MockResponse()

        decision = await lib.decide_injection(
            MockLLM(),  # type: ignore[arg-type]
            language="python",
            framework="fastapi",
            features=["async"],
            project_file_count=0,
            candidate_packages=candidates,
        )
        assert decision.decision == "full"
        assert "python-fastapi-minimal" in decision.package_ids

    @pytest.mark.asyncio
    async def test_decide_injection_skip_large_project(self) -> None:
        """LLM 决策——大项目应 skip。"""
        lib = PackageLibrary(library_path="D:/OrbitBasePackages")
        candidates = lib.search(language="python", framework="fastapi")

        class MockResponse:
            content = '{"decision": "skip", "package_ids": [], "reason": "已有大量代码"}'
            model = "openai/glm-5.2"

        class MockLLM:
            async def generate(self, req, task_id, agent_name=""):
                return MockResponse()

        decision = await lib.decide_injection(
            MockLLM(),  # type: ignore[arg-type]
            language="python",
            framework="fastapi",
            features=[],
            project_file_count=50,
            candidate_packages=candidates,
        )
        assert decision.decision == "skip"
        assert decision.package_ids == []

    @pytest.mark.asyncio
    async def test_decide_injection_fallback_on_parse_error(self) -> None:
        """LLM 返回无法解析的响应时降级到简单规则。"""
        lib = PackageLibrary(library_path="D:/OrbitBasePackages")
        candidates = lib.search(language="python", framework="fastapi")

        class MockResponse:
            content = "garbage response not json"
            model = "openai/glm-5.2"

        class MockLLM:
            async def generate(self, req, task_id, agent_name=""):
                return MockResponse()

        # 文件数少 → 降级 full
        decision = await lib.decide_injection(
            MockLLM(),  # type: ignore[arg-type]
            language="python",
            framework="fastapi",
            features=[],
            project_file_count=2,
            candidate_packages=candidates,
        )
        assert decision.decision == "full"
        assert "降级规则" in decision.reason

    @pytest.mark.asyncio
    async def test_decide_injection_no_candidates(self) -> None:
        """无候选包时直接 skip。"""
        lib = PackageLibrary()

        class MockLLM:
            async def generate(self, req, task_id, agent_name=""):
                pass

        decision = await lib.decide_injection(
            MockLLM(),  # type: ignore[arg-type]
            language="rust",
            framework="",
            features=[],
            project_file_count=0,
            candidate_packages=[],
        )
        assert decision.decision == "skip"
        assert "无匹配" in decision.reason

    # ── 覆盖缺口 ──

    def test_save_index_before_load(self) -> None:
        """_save_index 在未加载 index 时直接返回（line 97）。"""
        lib = PackageLibrary()
        lib._index = None
        # 不应崩——直接 return
        lib._save_index()

    def test_get_skeleton_nonexistent(self) -> None:
        """不存在的包→空字符串（line 254）。"""
        lib = PackageLibrary()
        result = lib.get_skeleton("nonexistent-pkg-12345")
        assert result == ""

    @pytest.mark.asyncio
    async def test_decide_injection_fallback_skip_large(self) -> None:
        """LLM 解析失败 + 大项目（file_count≥5）→ 降级 skip（line 365）。"""
        lib = PackageLibrary(library_path="D:/OrbitBasePackages")
        candidates = lib.search(language="python", framework="fastapi")

        class MockResponse:
            content = "totally broken response!!!"
            model = "openai/glm-5.2"

        class MockLLM:
            async def generate(self, req, task_id, agent_name=""):
                return MockResponse()

        decision = await lib.decide_injection(
            MockLLM(),  # type: ignore[arg-type]
            language="python",
            framework="fastapi",
            features=[],
            project_file_count=10,
            candidate_packages=candidates,
        )
        assert decision.decision == "skip"
        assert "降级规则" in decision.reason


class TestBasePackageModel:
    def test_to_dict_roundtrip(self) -> None:
        orig = BasePackage(
            id="test",
            language="python",
            framework="django",
            features=["orm", "admin"],
            description="Test package",
            file_count=3,
            estimated_tokens=500,
            cookiecutter_compat=True,
            path="test/",
        )
        d = orig.to_dict()
        restored = BasePackage.from_dict(d)
        assert restored.id == orig.id
        assert restored.language == orig.language
        assert restored.framework == orig.framework
        assert restored.features == orig.features
        assert restored.cookiecutter_compat is True
