"""记忆数据模型 (Phase 2 AC9).

MEMORY.md / checkpoint.md / progress.md / notes.md 的文件模型.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class MemoryFileType(StrEnum):
    """记忆文件类型——对标 MiMo Code memory/ 6 files."""

    EPISODIC = "MEMORY.md"  # 情节记忆：洞察、决策、教训
    CHECKPOINT = "checkpoint.md"  # 消息级检查点：turn 状态、token 快照
    PROGRESS = "progress.md"  # 任务进度：已完成/进行中/下一步/产出物
    NOTES = "notes.md"  # 自由格式笔记：带 tag 索引
    DECISIONS = "decisions.md"  # P1: 设计决策日志——Agent 不可逆选择


@dataclass
class MemoryFile:
    """单个记忆文件——YAML frontmatter + markdown body.

    WHY checksum: 双向同步时需要检测文件是否已被外部修改。
    """

    path: str
    file_type: MemoryFileType
    frontmatter: dict = field(default_factory=dict)
    body: str = ""
    checksum_sha256: str = ""
    updated_at: float = 0.0


@dataclass
class MemorySearchQuery:
    """记忆搜索请求."""

    query: str
    max_results: int = 10
    file_type: MemoryFileType | None = None


@dataclass
class MemorySearchResult:
    """记忆搜索结果.

    Phase 1: score 字段复用为质量评分——检索时偏爱高质量记忆。
    """

    path: str
    score: float  # BM25 评分 + 质量评分加成
    snippet: str  # 高亮片段
    line_number: int = 0
    entry_score: float = 1.0  # Phase 1: 记忆条目的质量评分


@dataclass
class MemoryConfig:
    """项目级记忆配置——对标 MiMo Code memory config."""

    project_root: str = ""
    memory_dir: str = ".orbit/memory"
    max_memory_file_size: int = 50_000  # 50KB per file


@dataclass
class DecisionRecord:
    """Agent 做出的不可逆设计决策——业务层减熵 P1.

    持久化到 decisions.md，调度时注入 context 避免 Agent 重选.
    """

    id: str  # "DD-20260629-042"
    choice: str  # 选择描述，如 "PostgreSQL over MySQL"
    why: str  # 理由
    constraints: list[str] = field(default_factory=list)  # 决策时约束
    alternatives: list[str] = field(default_factory=list)  # 考虑过的替代方案
    made_by: str = ""  # AgentRole
    scope: list[str] = field(default_factory=list)  # 影响范围
    timestamp: str = ""  # ISO 8601
