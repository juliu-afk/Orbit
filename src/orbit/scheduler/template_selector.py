"""模板选择器——业务层减熵 P1.

Agent 任务 → 关键词匹配模板清单 → 注入最佳模板到上下文.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml  # type: ignore[import-untyped]


@dataclass
class TemplateMatch:
    """模板匹配结果."""

    name: str
    file: str
    description: str
    confidence: float  # 0.0-1.0
    parameters: dict[str, str]


class TemplateSelector:
    """根据任务描述匹配最佳代码模板.

    用法:
        selector = TemplateSelector(templates_dir="/path/to/templates")
        matches = selector.select("新增一个查询任务的 API")
        # → [TemplateMatch(name="api_route_get", confidence=0.8, ...), ...]
    """

    def __init__(self, templates_dir: str | Path | None = None) -> None:
        if templates_dir is None:
            templates_dir = Path(__file__).resolve().parent.parent / "knowledge" / "templates"
        self._dir = Path(templates_dir)
        self._manifest: dict = {}
        self._load_manifest()
        # P1-5: 缓存 Jinja2 Environment
        from jinja2 import Environment, FileSystemLoader

        self._jinja_env = Environment(loader=FileSystemLoader(str(self._dir)))

    def select(self, task_description: str, top_n: int = 3) -> list[TemplateMatch]:
        """匹配任务到模板，按置信度降序返回 Top-N."""
        task_lower = task_description.lower()
        matches: list[TemplateMatch] = []

        for t in self._manifest.get("templates", []):
            score = self._match_score(task_lower, t)
            if score > 0:
                matches.append(
                    TemplateMatch(
                        name=t["name"],
                        file=t["file"],
                        description=t["description"],
                        confidence=round(min(score, 1.0), 2),
                        parameters={
                            p["name"]: p.get("example", "") for p in t.get("parameters", [])
                        },
                    )
                )

        matches.sort(key=lambda m: m.confidence, reverse=True)
        return matches[:top_n]

    def render(self, match: TemplateMatch, extra_params: dict[str, str] | None = None) -> str:
        """渲染命中的模板——填充参数."""
        # P1-5: 复用缓存的 Environment 避免每次新建
        template = self._jinja_env.get_template(match.file)
        params = {**match.parameters, **(extra_params or {})}
        return template.render(**params)

    # ── 内部 ─────────────────────────────────────────────

    def _load_manifest(self) -> None:
        manifest_path = self._dir / "MANIFEST.yaml"
        if not manifest_path.exists():
            self._manifest = {"templates": []}
            return
        with open(manifest_path, encoding="utf-8") as f:
            self._manifest = yaml.safe_load(f) or {"templates": []}

    @staticmethod
    def _match_score(task_lower: str, template: dict) -> float:
        """关键词匹配打分——每个 applicable_when 命中 +0.3."""
        score = 0.0
        for condition in template.get("applicable_when", []):
            cond_lower = condition.lower()
            if cond_lower in task_lower:
                score += 0.5  # 精确匹配
                continue
            # 分词匹配: "新增查询类 API" 的每个词在任务中出现
            tokens = cond_lower.replace(" ", "").split("/")
            for token in tokens:
                if len(token) >= 2 and token in task_lower:
                    score += 0.2
        return score
