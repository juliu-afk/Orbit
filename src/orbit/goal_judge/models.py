"""Goal Judge 数据模型——对标 MiMo Code Verdict schema.

{ok, impossible, reason}——简单三元判定。
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class Verdict(BaseModel):
    """Goal Judge 判定结果。

    fail-open: judge 出错 → ok=true（不困住用户）。
    Phase 1 CRAG: not_ok 时附带 memory 检索的建议（suggestions）。
    """

    ok: bool = Field(..., description="目标是否已完成")
    impossible: bool = Field(False, description="目标是否不可完成")
    reason: str = Field("", description="判定理由")
    suggestions: list[str] = Field(default_factory=list, description="CRAG: 相似经验建议")


class Goal(BaseModel):
    """用户设置的目标。"""

    description: str = Field(..., min_length=1, description="目标描述")
    react_count: int = Field(0, ge=0, description="当前 react 计数")
    MAX_REACT: int = Field(12, ge=1, description="硬上限——对标 MiMo MAX_GOAL_REACT")


JUDGE_SYSTEM_PROMPT = """你是停止条件评估裁判。判断 Agent 是否已完成目标。

返回 JSON 格式（仅 JSON，不要其他文本）:
- 已完成: {"ok": true, "reason": "<已完成的证据>"}
- 未完成: {"ok": false, "reason": "<还缺什么>"}
- 不可完成: {"ok": false, "impossible": true, "reason": "<为什么无法完成>"}

评估原则:
1. 只根据 transcript 中的实际证据判断，不要猜测
2. 目标部分完成 ≠ 全部完成——检查每个子任务
3. 如果 Agent 尝试了多种方式都失败，标记为 impossible
4. 不确定 → ok=false（宁可多跑一轮，不要漏掉完成条件）
"""
