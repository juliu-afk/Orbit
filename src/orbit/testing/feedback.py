"""测试反馈闭环 —— 失败模式入库 knowledge/，驱动后续生成策略优化。

WHY feedback: 测试不是终点——每次失败的根因应沉淀到知识图谱，
下次同类任务 Agent 预判路径，不犯相同错误。这是复利机制的核心。
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class FailureFeedback:
    """失败模式收集 + 知识图谱入库。

    每次测试失败后调用 record()，将失败模式写入 knowledge/。
    后续任务通过 intention.py 的 knowledge 检索注入 Prompt。
    """

    def __init__(self, knowledge=None):
        self._knowledge = knowledge

    async def record(
        self,
        module: str,
        error_type: str,
        error_detail: str,
        repair_successful: bool = False,
    ) -> str | None:
        """记录一条失败模式到知识图谱。

        Args:
            module: 失败模块，如 "scheduler.state_machine"
            error_type: 错误类型，如 "NullPointerError" / "TypeMismatch" / "TimeoutError"
            error_detail: 错误详情（截断到 500 字符）
            repair_successful: 是否修复成功（影响权重）

        Returns:
            pattern_id | None: 入库成功返回 ID，知识图谱不可用时返回 None
        """
        if not self._knowledge:
            logger.debug("feedback_no_knowledge——跳过入库")
            return None

        # 生成稳定的 pattern_id——同模块同错误类型去重
        fingerprint = hashlib.blake2b(
            f"{module}:{error_type}:{error_detail[:200]}".encode(),
            digest_size=8,
        ).hexdigest()

        entry = {
            "type": "test_failure_pattern",
            "pattern_id": fingerprint,
            "module": module,
            "error_type": error_type,
            "error_detail": error_detail[:500],
            "repaired": repair_successful,
            "frequency": 1,  # 首次记录
            "last_seen": datetime.now(timezone.utc).isoformat(),
        }

        try:
            # 通过 knowledge/ 的通用存储接口入库
            # WHY 不直接写 SQL: knowledge/ 可能用 SQLite/Redis/BGE——统一走其接口
            await self._knowledge.store_pattern(fingerprint, entry)
            logger.info("feedback_pattern_stored", pattern_id=fingerprint, module=module)
            return fingerprint
        except Exception as e:
            logger.warning("feedback_store_failed", error=str(e), exc_info=True)
            return None

    async def query(self, module: str, limit: int = 5) -> list[dict]:
        """查询某模块的历史失败模式。

        Returns:
            按频率降序排列的失败模式列表
        """
        if not self._knowledge:
            return []

        try:
            results = await self._knowledge.query_patterns(
                module=module,
                pattern_type="test_failure_pattern",
                limit=limit,
            )
            return results or []
        except Exception:
            return []

    def build_prompt_injection(self, patterns: list[dict]) -> str:
        """将历史失败模式转为 Prompt 注入文本。

        Returns:
            一段可注入到代码生成 Prompt 的警告文本
        """
        if not patterns:
            return ""

        lines = ["\n## 历史失败模式（请预判并避免）\n"]
        for p in patterns:
            module = p.get("module", "unknown")
            error_type = p.get("error_type", "unknown")
            error_detail = p.get("error_detail", "")[:100]
            frequency = p.get("frequency", 1)
            lines.append(
                f"- **{module}** ({error_type}, {frequency}次): {error_detail}"
            )
        return "\n".join(lines)
