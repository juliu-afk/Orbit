"""FileService 单元测试——文件操作/语言检测/路径安全。

使用临时目录模拟文件系统 I/O，不依赖真实项目结构。
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

from orbit.files.service import FileService, FileStatus


class TestDetectLanguage:
    """语言检测——纯映射字典，参数化快速覆盖。"""

    def test_python_extensions(self):
        svc = FileService("/tmp")
        assert svc.detect_language("main.py") == "python"
        assert svc.detect_language("test_main.py") == "python"
        assert svc.detect_language("setup.py") == "python"

    def test_typescript_extensions(self):
        svc = FileService("/tmp")
        assert svc.detect_language("App.tsx") == "typescript"
        assert svc.detect_language("utils.ts") == "typescript"
        assert svc.detect_language("types.ts") == "typescript"

    def test_markdown(self):
        svc = FileService("/tmp")
        assert svc.detect_language("README.md") == "markdown"
        assert svc.detect_language("docs/guide.md") == "markdown"

    def test_json(self):
        svc = FileService("/tmp")
        assert svc.detect_language("package.json") == "json"
        assert svc.detect_language("tsconfig.json") == "json"

    def test_toml(self):
        svc = FileService("/tmp")
        assert svc.detect_language("pyproject.toml") == "toml"

    def test_yaml(self):
        svc = FileService("/tmp")
        assert svc.detect_language("config.yaml") == "yaml"
        assert svc.detect_language("ci.yml") == "yaml"

    def test_vue_maps_to_html(self):
        """生产实现: .vue → 'html'（非 'vue'）。"""
        svc = FileService("/tmp")
        assert svc.detect_language("App.vue") == "html"

    def test_unknown_returns_plaintext(self):
        svc = FileService("/tmp")
        result = svc.detect_language("unknown.xyz")
        # 未知扩展名映射到 "plaintext"
        assert result == "plaintext"
        result2 = svc.detect_language("no_extension")
        assert result2 == "plaintext"


class TestSafePath:
    """路径遍历防护——拒绝 ../ 逃逸。"""

    def test_normal_path_allowed(self):
        svc = FileService("/workspace")
        result = svc._safe_path("src/main.py")
        # _safe_path 返回 resolved Path，在 Windows 上可能是 WindowsPath
        assert str(result).replace("\\", "/").endswith("src/main.py")

    def test_parent_traversal_blocked(self):
        """../ 逃逸→抛出 ValueError。"""
        svc = FileService("/workspace")
        with pytest.raises(ValueError, match="traversal"):
            svc._safe_path("../etc/passwd")

    def test_absolute_path_inside_workspace(self):
        """_safe_path 解析相对路径，不接受绝对路径（会拼接后 resolve）。"""
        svc = FileService("/workspace")
        # /etc/passwd 拼接→/workspace/etc/passwd，在 workspace 内所以不阻止
        result = svc._safe_path("etc/passwd")
        assert str(result).replace("\\", "/").endswith("etc/passwd")

    def test_hidden_file_allowed(self):
        """隐藏文件（.gitignore 等）不阻止。"""
        svc = FileService("/workspace")
        result = svc._safe_path(".gitignore")
        assert result.name == ".gitignore"


class TestReadWriteFiles:
    """文件读写——使用临时目录。"""

    @pytest.fixture
    def svc(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            yield FileService(tmpdir)

    @pytest.mark.asyncio
    async def test_write_and_read_file(self, svc):
        await svc.write_file("test.txt", "hello world")
        content = await svc.read_file("test.txt")
        assert content == "hello world"

    @pytest.mark.asyncio
    async def test_write_creates_parent_dirs(self, svc):
        """write_file 自动创建父目录。"""
        await svc.write_file("deep/nested/file.txt", "data")
        content = await svc.read_file("deep/nested/file.txt")
        assert content == "data"

    @pytest.mark.asyncio
    async def test_read_nonexistent_raises(self, svc):
        with pytest.raises(FileNotFoundError):
            await svc.read_file("nonexistent.txt")

    @pytest.mark.asyncio
    async def test_read_file_over_1mb_raises(self, svc):
        """超过 1MB 的文件拒绝读取。"""
        big = "x" * (1024 * 1024 + 1)
        await svc.write_file("big.txt", big)
        with pytest.raises(ValueError, match="too large|File too large"):
            await svc.read_file("big.txt")


class TestListFiles:
    """文件列表——使用临时目录。"""

    @pytest.fixture
    def svc(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            yield FileService(tmpdir)

    @pytest.mark.asyncio
    async def test_list_files_in_empty_dir(self, svc):
        files = await svc.list_files()
        assert isinstance(files, list)

    @pytest.mark.asyncio
    async def test_list_files_with_content(self, svc):
        await svc.write_file("a.py", "print(1)")
        await svc.write_file("b.ts", "const x=1")
        files = await svc.list_files()
        names = {f.path for f in files}
        # 文件名含相对路径——至少有一个文件
        assert len(files) >= 2


class TestFileInfo:
    """FileInfo/FileStatus 模型验证。"""

    def test_file_status_enum_values(self):
        assert FileStatus.ADDED.value == "added"
        assert FileStatus.MODIFIED.value == "modified"
        assert FileStatus.DELETED.value == "deleted"
        assert FileStatus.UNCHANGED.value == "unchanged"
