"""策略锚点上下文构建器——从 STRATEGY.md / brief.md 注入项目战略上下文。

对标 Compound STRATEGY.md 锚点机制: 所有 Agent 自动对齐项目目标。
Target Problem / Approach / Persona / Key Metrics / Tracks 五段结构。

接入点: PromptBuilder 组装 system prompt 时调用。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


class StrategyContextBuilder:
    """STRATEGY.md → Agent 上下文注入器。

    读取顺序:
    1. {project_root}/STRATEGY.md — 优先（手动编写或已缓存）
    2. {project_root}/.orbit/brief.md — 降级（从 brief 提取五段）
    3. 均不存在 → 返回空上下文（fail-open）

    注入位置: system prompt 顶部——确保 Agent 最先看到项目目标。
    """

    name = "strategy"
    MAX_CHARS = 3000  # 策略上下文截断上限——避免挤占其他上下文

    def build(self, inputs: dict[str, Any]) -> dict[str, Any]:
        """读取策略锚点文件并格式化。

        Args:
            inputs: 含 project_root 的上下文字典

        Returns:
            {"strategy_text": "## 项目策略锚点\\n..."}
            无可用文件时返回 {"strategy_text": ""}
        """
        project_root = inputs.get("project_root", ".")
        root_path = Path(project_root)

        content = self._read_strategy_md(root_path)
        if not content:
            content = self._extract_from_brief(root_path)

        if not content:
            return {"strategy_text": ""}

        truncated = content[: self.MAX_CHARS]
        if len(content) > self.MAX_CHARS:
            truncated += "\n\n...（策略锚点已截断，完整版见 STRATEGY.md）"

        return {"strategy_text": "## 项目策略锚点\n\n" + truncated}

    @staticmethod
    def _read_strategy_md(root: Path) -> str:
        """读取 STRATEGY.md——五段结构化战略文档。"""
        path = root / "STRATEGY.md"
        if path.exists():
            return path.read_text(encoding="utf-8", errors="replace")
        return ""

    @staticmethod
    def _extract_from_brief(root: Path) -> str:
        """从 .orbit/brief.md 提取策略相关段落。

        提取"摘要"段 + "边界"段作为策略锚点降级方案。
        WHY 提取而非全量: brief.md 含技术栈/目录结构等实现细节，
        策略锚点只需要"什么/谁/怎么衡量"。
        """
        brief_path = root / ".orbit" / "brief.md"
        if not brief_path.exists():
            return ""

        try:
            text = brief_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return ""

        # 提取 "摘要" 和 "边界" 段
        sections: list[str] = []
        for marker in ("## 1. 摘要", "## 6. 边界", "## 摘要", "## 边界"):
            if marker in text:
                idx = text.index(marker)
                # 取到下一个 ## 或文末
                end_idx = text.find("\n## ", idx + len(marker))
                section = text[idx:] if end_idx == -1 else text[idx:end_idx]
                sections.append(section.strip())

        return "\n\n".join(sections) if sections else ""
