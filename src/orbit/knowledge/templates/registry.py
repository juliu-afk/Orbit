"""模板注册器——加载 .tmpl 模板文件，按关键词匹配，填充参数.

WHY 独立 registry: 模板库与加载逻辑分离，AgentFactory/system_prompt 只关心
match/fill 接口，不关心文件格式。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import structlog

logger = structlog.get_logger()


@dataclass
class Template:
    """模板数据模型.

    keywords 用于 match 检索，template_text 含 {{param}} 占位符，
    parameters 列出模板期望的所有参数名。
    """

    name: str
    description: str
    keywords: list[str] = field(default_factory=list)
    template_text: str = ""
    parameters: list[str] = field(default_factory=list)


# ── 内置兜底模板（无 .tmpl 文件时加载）───────────────────────

_FALLBACK_TEMPLATES: list[dict] = [
    {
        "name": "crud_endpoint",
        "description": "FastAPI CRUD endpoint with SQLAlchemy session",
        "keywords": ["crud", "endpoint", "api", "fastapi", "route", "create", "read", "update", "delete"],
        "parameters": ["model_name", "model_name_lower", "table_name", "schema_name"],
        "template_text": '''
@router.get("/{{table_name}}/", response_model=list[{{schema_name}}])
async def list_{{model_name_lower}}(db: Session = Depends(get_db)):
    """查询所有{{model_name}}记录。"""
    items = db.query({{model_name}}).all()
    return items


@router.post("/{{table_name}}/", response_model={{schema_name}}, status_code=201)
async def create_{{model_name_lower}}(
    data: {{schema_name}}Create, db: Session = Depends(get_db)
):
    """创建{{model_name}}记录。"""
    item = {{model_name}}(**data.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    return item
'''.strip(),
    },
    {
        "name": "pydantic_schema",
        "description": "Pydantic v2 request/response models",
        "keywords": ["pydantic", "schema", "request", "response", "validation", "model"],
        "parameters": ["model_name", "schema_name", "fields"],
        "template_text": '''
from pydantic import BaseModel, Field


class {{schema_name}}Create(BaseModel):
    """创建{{model_name}}请求体。"""

    {{fields}}


class {{schema_name}}Update(BaseModel):
    """更新{{model_name}}请求体。"""

    {{fields}}


class {{schema_name}}(BaseModel):
    """{{model_name}}响应体。"""

    id: int
    {{fields}}

    model_config = {"from_attributes": True}
'''.strip(),
    },
    {
        "name": "test_unit",
        "description": "pytest unit test with fixtures",
        "keywords": ["test", "unit", "pytest", "fixture", "unittest"],
        "parameters": ["module_name", "class_name", "test_case"],
        "template_text": '''
"""{{class_name}}单元测试."""

from __future__ import annotations

import pytest


@pytest.fixture
def {{module_name}}_fixture():
    """测试前置准备。"""
    return {}


class Test{{class_name}}:
    """{{class_name}}测试套件."""

    def test_{{test_case}}(self, {{module_name}}_fixture):
        """测试{{test_case}}。"""
        assert True
'''.strip(),
    },
]


class TemplateRegistry:
    """模板注册器——管理 .tmpl 模板的全生命周期.

    加载→解析→匹配→填充，不引入外部依赖（纯 pathlib + 手写 frontmatter 解析）。
    """

    def __init__(self, templates_dir: str | Path | None = None) -> None:
        """初始化注册器.

        Args:
            templates_dir: 模板目录路径。默认自动定位到本文件所在目录。
        """
        if templates_dir is None:
            templates_dir = Path(__file__).parent
        self._templates_dir = Path(templates_dir)
        self._templates: dict[str, Template] = {}
        self._loaded = False

    @property
    def templates(self) -> dict[str, Template]:
        """按名称索引的模板字典（懒加载）。"""
        if not self._loaded:
            self._load_all()
        return self._templates

    def _load_all(self) -> None:
        """扫描目录加载所有 .tmpl 文件.

        无 .tmpl 文件时加载内置兜底模板。
        """
        self._loaded = True
        tmpl_files = sorted(self._templates_dir.glob("*.tmpl"))

        if not tmpl_files:
            logger.warning("no .tmpl files found, loading fallback templates")
            for fb in _FALLBACK_TEMPLATES:
                tmpl = Template(
                    name=fb["name"],
                    description=fb["description"],
                    keywords=fb["keywords"],
                    template_text=fb["template_text"],
                    parameters=fb["parameters"],
                )
                self._templates[tmpl.name] = tmpl
            return

        for path in tmpl_files:
            try:
                tmpl = self.load_template(path)
                self._templates[tmpl.name] = tmpl
            except Exception:
                logger.exception("failed to load template", path=str(path))

    def load_template(self, path: str | Path) -> Template:
        """解析单个 .tmpl 文件.

        YAML 风格的 frontmatter（--- 分隔） + 模板正文。
        frontmatter 字段: name, description, keywords, parameters（均为字符串）。

        WHY 手写解析而非 yaml 库: 零依赖策略。模板 frontmatter 格式简单固定。
        """
        text = Path(path).read_text(encoding="utf-8")

        # 检查 frontmatter（--- 开头）
        if not text.startswith("---\n"):
            raise ValueError(f"模板文件缺少 frontmatter（需以 ---\\n 开头）: {path}")

        # 分割 frontmatter 与正文
        parts = text.split("---\n", 2)
        if len(parts) < 3:
            raise ValueError(f"模板文件 frontmatter 格式错误（需要 --- 闭合）: {path}")
        frontmatter_raw = parts[1]
        body = parts[2].strip()

        # 解析 frontmatter 键值对
        meta: dict[str, str] = {}
        for line in frontmatter_raw.strip().split("\n"):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if ":" not in line:
                continue
            key, _, value = line.partition(":")
            meta[key.strip()] = value.strip()

        name = meta.get("name", Path(path).stem)
        description = meta.get("description", "")
        keywords_raw = meta.get("keywords", "")
        parameters_raw = meta.get("parameters", "")

        keywords = [k.strip() for k in keywords_raw.split(",") if k.strip()]
        parameters = [p.strip() for p in parameters_raw.split(",") if p.strip()]

        return Template(
            name=name,
            description=description,
            keywords=keywords,
            template_text=body,
            parameters=parameters,
        )

    def match(self, keywords: list[str]) -> list[Template]:
        """按关键词匹配模板，按相关性降序返回.

        相关性 = 关键词交集大小 / 关键词并集大小（Jaccard 相似度）。
        分数 > 0 即返回（含排序），调用方自行决定阈值。
        """
        if not keywords:
            return []

        kw_set = {k.lower() for k in keywords}
        scored: list[tuple[float, Template]] = []

        for tmpl in self.templates.values():
            tmpl_kw_set = {k.lower() for k in tmpl.keywords}
            if not tmpl_kw_set:
                continue
            intersection = kw_set & tmpl_kw_set
            union = kw_set | tmpl_kw_set
            score = len(intersection) / len(union) if union else 0.0
            if score > 0:
                scored.append((score, tmpl))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [tmpl for _, tmpl in scored]

    def fill(self, template_name: str, params: dict[str, str]) -> str:
        """填充模板参数.

        Args:
            template_name: 模板名称（对应 name 字段）。
            params: 参数名→值的映射，替换 {{param}} 占位符。

        Returns:
            填充后的模板文本。

        Raises:
            KeyError: 模板不存在。
        """
        tmpl = self.templates.get(template_name)
        if tmpl is None:
            raise KeyError(f"模板不存在: {template_name}")

        result = tmpl.template_text
        for key, value in params.items():
            result = result.replace("{{" + key + "}}", value)
        return result

    def match_and_format(
        self, keywords: list[str], threshold: float = 0.5
    ) -> str:
        """便捷方法：匹配模板并格式化为提示语片段.

        Args:
            keywords: 任务关键词列表。
            threshold: 最低匹配分数（默认 0.5）。

        Returns:
            格式化的模板文本块（多模板用 "---" 分隔），无匹配时返回空字符串。
        """
        matched = self.match(keywords)
        above_threshold = [t for t in matched if self._score(keywords, t) >= threshold]
        if not above_threshold:
            return ""

        blocks = []
        for tmpl in above_threshold:
            header = f"## 模板: {tmpl.name} — {tmpl.description}"
            blocks.append(f"{header}\n```\n{tmpl.template_text}\n```")

        return "\n\n---\n\n".join(blocks)

    @staticmethod
    def _score(keywords: list[str], tmpl: Template) -> float:
        """计算单个模板与关键词的匹配分数."""
        kw_set = {k.lower() for k in keywords}
        tmpl_set = {k.lower() for k in tmpl.keywords}
        if not tmpl_set:
            return 0.0
        intersection = kw_set & tmpl_set
        union = kw_set | tmpl_set
        return len(intersection) / len(union) if union else 0.0


# ── 全局单例 ──────────────────────────────────────────────

_registry: TemplateRegistry | None = None


def get_registry() -> TemplateRegistry:
    """返回全局单例 TemplateRegistry."""
    global _registry
    if _registry is None:
        _registry = TemplateRegistry()
    return _registry
