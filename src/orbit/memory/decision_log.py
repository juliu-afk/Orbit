"""决策日志——业务层减熵 US-B5.

WHY JSONL: 追加写无锁争用、人可读、每行独立、便于 grep 审计。
与 memory/store.py 的 DecisionRecord/markdown 方案正交：
  DecisionLog 面向 Agent 运行时记录+检索，JSONL 格式；
  DecisionRecord 面向调度器决策，markdown 格式。
"""

from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class Decision:
    """Agent 设计决策——序列化到 JSONL.

    WHY 新 dataclass 而非复用 DecisionRecord:
      decision_log 需要 question/answer 语义（"用什么缓存"→"Redis"），
      与调度器层的 choice/why 正交。
    """

    question: str  # 被决策的问题
    answer: str  # 选中的方案
    alternatives: list[str]  # 其他考虑过的方案
    rationale: str  # 为什么选这个方案
    agent: str  # 决策 Agent 角色名
    task_id: str  # 所在 Task ID
    timestamp: float  # epoch 秒


class DecisionLog:
    """JSONL 决策日志——线程安全追加写 + 关键词检索 + 冲突检测.

    Usage:
        log = DecisionLog()
        log.record(Decision(question="用什么缓存", answer="Redis", ...))
        results = log.query(["Redis", "SQLite"])
        conflicts = log.find_conflicts("用什么缓存")
        recent = log.recent(10)
    """

    def __init__(self, storage_dir: str | Path | None = None) -> None:
        """初始化决策日志.

        Args:
            storage_dir: JSONL 文件目录，默认 .orbit/memory/ 在工作目录下.
        """
        self._lock = threading.Lock()
        if storage_dir is None:
            storage_dir = Path.cwd() / ".orbit" / "memory"
        self._path = Path(storage_dir) / "decisions.jsonl"
        self._path.parent.mkdir(parents=True, exist_ok=True)

    # ── 写 ─────────────────────────────────────────────

    def record(self, decision: Decision) -> None:
        """追加一条决策记录——线程安全."""
        raw = {
            "question": decision.question,
            "answer": decision.answer,
            "alternatives": decision.alternatives,
            "rationale": decision.rationale,
            "agent": decision.agent,
            "task_id": decision.task_id,
            "timestamp": decision.timestamp,
        }
        with self._lock, open(self._path, "a", encoding="utf-8") as f:
            f.write(json.dumps(raw, ensure_ascii=False) + "\n")

    # ── 检索 ───────────────────────────────────────────

    def query(self, keywords: list[str], max_results: int = 10) -> list[Decision]:
        """按任意关键词检索——子字符串匹配，大小写不敏感，按时间倒序.

        Args:
            keywords: 关键词列表（OR 逻辑——匹配任一即命中）
            max_results: 最大返回条数

        Returns:
            匹配的决策列表，按时间倒序.
        """
        if not keywords:
            return []
        decisions = self._load_all()
        matched: list[Decision] = []
        for d in decisions:
            for kw in keywords:
                kw_lower = kw.lower()
                if (
                    kw_lower in d.question.lower()
                    or kw_lower in d.answer.lower()
                    or kw_lower in d.rationale.lower()
                    or any(kw_lower in a.lower() for a in d.alternatives)
                ):
                    matched.append(d)
                    break
        matched.sort(key=lambda d: d.timestamp, reverse=True)
        return matched[:max_results]

    def find_conflicts(self, question: str, threshold: float = 0.7) -> list[list[Decision]]:
        """查找相似问题但答案不同的决策组.

        用 Jaccard 词重叠度衡量问题相似度。
        返回值中每组（list[Decision]）代表同一问题（或高度相似问题）
        的不同答案——需要人工裁决。

        Args:
            question: 待查问题
            threshold: Jaccard 相似度阈值（0.0-1.0）

        Returns:
            冲突组列表，每组内至少有两个不同答案.
        """
        all_decisions = self._load_all()
        if not all_decisions:
            return []

        query_words = set(question.lower().split())

        # 1. 按 Jaccard 相似度筛选
        similar: dict[str, list[Decision]] = {}
        for d in all_decisions:
            d_words = set(d.question.lower().split())
            if not query_words and not d_words:
                continue
            union = len(query_words | d_words)
            if union == 0:
                continue
            overlap = len(query_words & d_words)
            jaccard = overlap / union
            if jaccard >= threshold:
                similar.setdefault(d.question, []).append(d)

        # 2. 筛选组内答案不同的组
        conflicts: list[list[Decision]] = []
        for _q, ds in similar.items():
            unique_answers = {d.answer for d in ds}
            if len(unique_answers) > 1:
                conflicts.append(ds)

        return conflicts

    def recent(self, n: int = 20) -> list[Decision]:
        """最近 n 条决策——按记录时间倒序."""
        decisions = self._load_all()
        decisions.sort(key=lambda d: d.timestamp, reverse=True)
        return decisions[:n]

    # ── 内部 ──────────────────────────────────────────

    def _load_all(self) -> list[Decision]:
        """读取全部 JSONL 记录——线程安全."""
        if not self._path.exists():
            return []
        with self._lock:
            try:
                raw = self._path.read_text(encoding="utf-8")
            except (OSError, PermissionError):
                return []
        decisions: list[Decision] = []
        for line in raw.strip().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj: dict[str, Any] = json.loads(line)
                decisions.append(
                    Decision(
                        question=obj.get("question", ""),
                        answer=obj.get("answer", ""),
                        alternatives=obj.get("alternatives", []),
                        rationale=obj.get("rationale", ""),
                        agent=obj.get("agent", ""),
                        task_id=obj.get("task_id", ""),
                        timestamp=obj.get("timestamp", 0.0),
                    )
                )
            except (json.JSONDecodeError, KeyError):
                continue  # 损坏行跳过，不阻断
        return decisions


# ── [DECISION] 标记解析 ────────────────────────────────
# WHY 独立函数: 测试和 react_agent 共用，无需 import DecisionLog。
# 格式:
#   [DECISION] Q: 用什么缓存
#   A: Redis
#   Alternatives: SQLite, Memcached
#   Rationale: 需要持久化+高可用


def parse_decision_marker(text: str) -> Decision | None:
    """从 Agent 输出中解析 [DECISION] 标记.

    标记格式：
        [DECISION] Q: <问题>
        A: <答案>
        Alternatives: <备选1>, <备选2>
        Rationale: <理由>

    只解析第一条 [DECISION] 标记，解析完后跳出。
    agent 和 task_id 由调用方填充（parse 时未知）。
    """
    if "[DECISION]" not in text:
        return None

    lines = text.splitlines()
    q = a = alt = rat = ""
    in_decision = False

    for line in lines:
        stripped = line.strip()
        if "[DECISION]" in stripped:
            in_decision = True
            # 支持 [DECISION] 与 Q: 在同一行
            idx = stripped.index("]")
            rest = stripped[idx + 1 :].strip()
            if rest.startswith("Q:"):
                q = rest[2:].strip()
            continue
        if not in_decision:
            continue
        if stripped.startswith("Q:") and not q:
            q = stripped[2:].strip()
        elif stripped.startswith("A:") and not a:
            a = stripped[2:].strip()
        elif stripped.startswith("Alternatives:"):
            alt = stripped[len("Alternatives:") :].strip()
        elif stripped.startswith("Rationale:"):
            rat = stripped[len("Rationale:") :].strip()
        elif not stripped:
            # 空行结束标记段落
            break

    if q and a:
        return Decision(
            question=q,
            answer=a,
            alternatives=[x.strip() for x in alt.split(",") if x.strip()] if alt else [],
            rationale=rat,
            agent="",
            task_id="",
            timestamp=time.time(),
        )
    return None
