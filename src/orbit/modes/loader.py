"""ModeLoader——读取/校验/缓存 mode.yaml，按需加载 references/.

WHY 缓存: mode.yaml 启动时加载一次，运行时不变化（热加载 P2 远期）。
WHY 降级: 任何加载失败 → 日志警告 → 返回 None，不影响 Agent 运行。

Usage:
    loader = ModeLoader()
    mode = loader.load("clarify")
    if mode:
        agent._mode = mode
    # references 按需加载:
    qtree = loader.load_reference("clarify", "question-tree.md")
"""

from __future__ import annotations

import functools
from pathlib import Path
from typing import TYPE_CHECKING

import structlog
import yaml

from orbit.modes.schemas import BehaviorConfig, ModeConfig, QuestionStrategy

if TYPE_CHECKING:
    pass

logger = structlog.get_logger("orbit.modes.loader")

# 默认 modes 目录——相对 src/orbit/modes/
_DEFAULT_MODES_DIR = Path(__file__).resolve().parent


class ModeLoadError(Exception):
    """模式加载失败——非致命，上游降级到默认行为."""


class ModeLoader:
    """模式文件加载器——读取 YAML → Pydantic 校验 → 缓存.

    WHY 非单例: 允许测试中用临时目录替换 modes_dir。
    """

    def __init__(self, modes_dir: str | Path | None = None) -> None:
        self._modes_dir = Path(modes_dir) if modes_dir else _DEFAULT_MODES_DIR
        self._cache: dict[str, ModeConfig] = {}

    # ── 公共 API ──────────────────────────────────

    def load(self, mode_name: str) -> ModeConfig | None:
        """加载 mode.yaml → ModeConfig.

        解析失败返回 None（不抛异常）——上游降级到硬编码默认行为。
        """
        if mode_name in self._cache:
            return self._cache[mode_name]

        yaml_path = self._modes_dir / mode_name / "mode.yaml"
        if not yaml_path.exists():
            logger.warning("mode_file_missing", mode=mode_name, path=str(yaml_path))
            return None

        try:
            raw = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
            if raw is None:
                raise ModeLoadError(f"{yaml_path} is empty")
            # BehaviorConfig 可能缺省——用默认值填充
            if "behavior" in raw and isinstance(raw["behavior"], dict):
                raw["behavior"] = BehaviorConfig(**raw["behavior"])
            config = ModeConfig(**raw)
            self._cache[mode_name] = config
            logger.debug("mode_loaded", mode=mode_name, version=config.version)
            return config
        except (yaml.YAMLError, ValueError, TypeError) as e:
            logger.warning("mode_parse_failed", mode=mode_name, error=str(e))
            return None

    def load_reference(self, mode_name: str, ref_name: str) -> str:
        """按需加载 references/ 下的文件.

        WHY ≤200 行限制: 防止 references 变成第二个全量上下文。
        """
        ref_path = self._modes_dir / mode_name / "references" / ref_name
        if not ref_path.exists():
            logger.debug("reference_missing", mode=mode_name, ref=ref_name)
            return ""

        try:
            text = ref_path.read_text(encoding="utf-8")
            lines = text.split("\n")
            if len(lines) > 200:
                logger.warning(
                    "reference_too_large",
                    mode=mode_name,
                    ref=ref_name,
                    lines=len(lines),
                    limit=200,
                )
                text = "\n".join(lines[:200]) + f"\n... [truncated {len(lines) - 200} lines]"
            return text
        except (OSError, UnicodeDecodeError) as e:
            logger.warning("reference_read_failed", mode=mode_name, ref=ref_name, error=str(e))
            return ""

    @functools.lru_cache(maxsize=1)  # noqa: B019
    def list_modes(self) -> list[str]:
        """列出所有可用 mode 名（扫描 modes_dir 下的子目录）."""
        modes: list[str] = []
        try:
            for child in self._modes_dir.iterdir():
                if child.is_dir() and (child / "mode.yaml").exists():
                    modes.append(child.name)
        except OSError:
            pass
        return sorted(modes)

    def resolve_for_state(self, state: str) -> ModeConfig | None:
        """根据状态机阶段自动匹配 mode.

        WHY 不缓存: 扫描所有 mode 的 applies_to 字段，O(n) 可接受（n≤10）。
        """
        for mode_name in self.list_modes():
            config = self.load(mode_name)
            if config and state in config.applies_to:
                return config
        return None
