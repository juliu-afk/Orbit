"""多级降级路径 (Step 7.3 ResourceGuard).

WHY 4 级降级而非二元 pass/fail:
- L1 备用模型: 自动切 GLM-4.7 Flash（免费），用户无感知
- L2 规则引擎: 预定义模板响应, 不需要 LLM
- L3 缓存数据: 返回上次成功结果 (标记 stale), 有数据可用
- L4 人工挂起: 前 3 级全失败时安全兜底, 不丢任务

各级独立验证——降级失败自动跳下一级。

P2-4: L3 stale cache SQLite 持久化——替代 Redis，不可用时降级内存。
"""

from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class DegradationResult:
    """降级执行结果。"""

    path: str  # L1_BACKUP_MODEL | L2_RULE_ENGINE | L3_STALE_CACHE | L4_HUMAN
    level: int  # 1-4
    data: dict[str, Any]  # 降级响应数据
    stale: bool = False  # 数据是否陈旧（L3 缓存标记）


class DegradationPath:
    """4 级降级路径执行器。

    用法:
        dp = DegradationPath()
        result = dp.execute(level=1)  # L1 备用模型
        # 各级独立调用, 调用方根据 result.path 判断成功与否
    """

    # 降级响应模板——L2 规则引擎用
    RULE_TEMPLATES: dict[str, str] = {
        "unknown": "无法处理此请求。请稍后重试或联系管理员。",
        "code_gen": "代码生成请求已降级。请检查需求描述是否清晰，或尝试拆分任务。",
        "over_budget": "Token 消耗已超过预算上限。建议优化提示词或增加预算。",
    }

    def execute(self, level: int, context: dict[str, Any] | None = None) -> DegradationResult:
        """执行指定级别的降级路径。

        context: 可选上下文 (task_id, error_type 等)
        """
        ctx = context or {}
        if level == 1:
            return self._l1_backup_model(ctx)
        elif level == 2:
            return self._l2_rule_engine(ctx)
        elif level == 3:
            return self._l3_stale_cache(ctx)
        else:
            return self._l4_human_escalation(ctx)

    def _l1_backup_model(self, ctx: dict[str, Any]) -> DegradationResult:
        """L1: 切换备用模型。

        返回备用模型配置, 调用方用返回的 model 重新发起 LLM 请求。
        """
        return DegradationResult(
            path="L1_BACKUP_MODEL",
            level=1,
            data={
                "action": "switch_model",
                "model": "openai/glm-4.7-flash",
                "original_model": ctx.get("model", "unknown"),
            },
        )

    def _l2_rule_engine(self, ctx: dict[str, Any]) -> DegradationResult:
        """L2: 本地规则引擎——返回预定义响应模板。

        不需要 LLM, 基于错误类型返回预定义消息。
        """
        error_type = ctx.get("error_type", "unknown")
        message = self.RULE_TEMPLATES.get(error_type, self.RULE_TEMPLATES["unknown"])
        return DegradationResult(
            path="L2_RULE_ENGINE",
            level=2,
            data={"action": "template_response", "message": message, "error_type": error_type},
        )

    # P2-4: SQLite 缓存数据库路径
    _CACHE_DB: str | None = None  # 类级别，延迟初始化

    @classmethod
    def _get_cache_db(cls) -> str:
        """获取 SQLite 缓存路径——延迟初始化，不可写时降级内存."""
        if cls._CACHE_DB is not None:
            return cls._CACHE_DB
        cache_dir = Path.home() / ".orbit" / "cache"
        try:
            cache_dir.mkdir(parents=True, exist_ok=True)
            db_path = str(cache_dir / "degradation_cache.db")
            # 初始化表
            with sqlite3.connect(db_path) as conn:
                conn.execute(
                    "CREATE TABLE IF NOT EXISTS stale_cache ("
                    "  key TEXT PRIMARY KEY,"
                    "  response TEXT,"
                    "  cached_at REAL"
                    ")"
                )
                conn.commit()
            cls._CACHE_DB = db_path
            return db_path
        except (OSError, PermissionError):
            cls._CACHE_DB = ""  # 空字符串 = 不可用
            return ""

    def _l3_stale_cache(self, ctx: dict[str, Any]) -> DegradationResult:
        """L3: 缓存数据——返回上次成功结果（标记 stale）。

        P2-4: SQLite 持久化缓存，不可写时降级到传入的 ctx cached_response。
        """
        task_id = ctx.get("task_id", "")
        db_path = self._get_cache_db()

        # 尝试从 SQLite 读取缓存
        cached_response = ""
        cached_at = ""
        if db_path:
            try:
                with sqlite3.connect(db_path) as conn:
                    row = conn.execute(
                        "SELECT response, cached_at FROM stale_cache WHERE key=?",
                        (task_id,),
                    ).fetchone()
                    if row:
                        cached_response = row[0]
                        cached_at = str(row[1])
            except sqlite3.Error:
                pass

        # SQLite 未命中 → 使用 ctx 传入的缓存
        if not cached_response:
            cached_response = ctx.get("cached_response", "")
            cached_at = ctx.get("cached_at", "")

        return DegradationResult(
            path="L3_STALE_CACHE",
            level=3,
            data={
                "action": "stale_cache",
                "cached_response": cached_response,
                "cached_at": cached_at,
                "task_id": task_id,
            },
            stale=True,
        )

    def cache_result(self, key: str, response: str) -> None:
        """P2-4: 写入成功结果到 L3 缓存——供后续降级读取."""
        db_path = self._get_cache_db()
        if not db_path:
            return
        try:
            with sqlite3.connect(db_path) as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO stale_cache (key, response, cached_at)"
                    " VALUES (?, ?, ?)",
                    (key, response, time.time()),
                )
                conn.commit()
        except sqlite3.Error:
            pass

    def _l4_human_escalation(self, ctx: dict[str, Any]) -> DegradationResult:
        """L4: 转人工挂起——任务状态设为 SUSPENDED。

        前 3 级全失败后的安全兜底。
        """
        return DegradationResult(
            path="L4_HUMAN",
            level=4,
            data={
                "action": "suspend",
                "task_id": ctx.get("task_id", ""),
                "message": "任务已挂起，等待人工介入处理。",
            },
        )
