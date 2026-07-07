"""Agent 测试自循环模块 —— 将测试从人类手动执行升级为 Agent 内建质量闭环。

五层内循环：意图理解 → 测试生成 → 代码生成(TDD) → 沙箱执行 → 反馈闭环。
"""

from __future__ import annotations
