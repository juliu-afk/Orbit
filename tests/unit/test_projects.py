"""NL交互 PR #1——项目注册表单元测试。"""

import os

from orbit.projects.registry import ProjectRegistry


class TestProjectRegistry:
    """项目 CRUD。"""

    def test_register_and_get(self) -> None:
        reg = ProjectRegistry()
        try:
            reg.register(
                "Orbit",
                repo_url="https://github.com/juliu-afk/Orbit",
                description="多Agent开发系统",
                tags=["agent", "python"],
            )
            p = reg.get("Orbit")
            assert p is not None
            assert p.name == "Orbit"
            assert p.repo_url == "https://github.com/juliu-afk/Orbit"
            assert "agent" in p.tags
        finally:
            reg.close()
            _cleanup()

    def test_register_update_existing(self) -> None:
        reg = ProjectRegistry()
        try:
            reg.register("X", description="v1")
            reg.register("X", description="v2")
            p = reg.get("X")
            assert p is not None
            assert p.description == "v2"
        finally:
            reg.close()
            _cleanup()

    def test_list_all(self) -> None:
        reg = ProjectRegistry()
        try:
            reg.register("A")
            reg.register("B")
            reg.register("C")
            assert reg.count() == 3
            assert len(reg.list_all()) == 3
        finally:
            reg.close()
            _cleanup()

    def test_deactivate(self) -> None:
        reg = ProjectRegistry()
        try:
            reg.register("Temp")
            assert reg.count() == 1
            reg.deactivate("Temp")
            assert reg.count() == 0
            assert reg.get("Temp") is not None  # 记录仍存在
            assert reg.get("Temp").is_active is False
        finally:
            reg.close()
            _cleanup()

    def test_search_by_name(self) -> None:
        reg = ProjectRegistry()
        try:
            reg.register("Orbit", description="多Agent")
            reg.register("Finite", description="财务系统")
            reg.register("Keshen", description="财务软件")
            results = reg.search("财务")
            assert len(results) == 2
            names = {r.name for r in results}
            assert "Finite" in names
            assert "Keshen" in names
        finally:
            reg.close()
            _cleanup()

    def test_search_by_tag(self) -> None:
        reg = ProjectRegistry()
        try:
            reg.register("Orbit", tags=["agent", "python"])
            reg.register("Other", tags=["web", "javascript"])
            results = reg.search("python")
            assert len(results) == 1
            assert results[0].name == "Orbit"
        finally:
            reg.close()
            _cleanup()

    def test_search_exact_name_first(self) -> None:
        """名称精确匹配排在标签匹配前面。"""
        reg = ProjectRegistry()
        try:
            reg.register("Python Utils", tags=["tools"])
            reg.register("Orbit", description="python agent framework", tags=["python"])
            results = reg.search("python")
            # Orbit has "python" in tags, Python Utils has it in name → 后者优先
            assert results[0].name == "Python Utils"
        finally:
            reg.close()
            _cleanup()

    def test_search_by_tags_method(self) -> None:
        reg = ProjectRegistry()
        try:
            reg.register("Orbit", tags=["agent", "python", "llm"])
            reg.register("WebApp", tags=["web", "react"])
            results = reg.search_by_tags(["python", "web"])
            assert len(results) == 2
        finally:
            reg.close()
            _cleanup()

    def test_issue_tracker_config(self) -> None:
        reg = ProjectRegistry()
        try:
            reg.register(
                "Orbit",
                issue_tracker="github",
                issue_tracker_config={"owner": "juliu-afk", "repo": "Orbit"},
            )
            p = reg.get("Orbit")
            assert p is not None
            assert p.issue_tracker == "github"
            assert p.issue_tracker_config["owner"] == "juliu-afk"
        finally:
            reg.close()
            _cleanup()


def _cleanup() -> None:
    if os.path.exists("data/projects.db"):
        os.remove("data/projects.db")
