"""CronParser——间隔/cron 表达式解析。

支持格式:
- 纯数字+单位: 30s, 5m, 1h, 2d
- Cron 5字段: "0 9 * * *"
- 英文简写: hourly, daily, weekly
"""

from __future__ import annotations

import re


class CronParseError(ValueError):
    """Cron 解析错误。"""

    pass


class CronParser:
    """间隔/cron 解析器。

    Usage:
        parser = CronParser()
        seconds = parser.parse("5m")     # 300
        seconds = parser.parse("1h")     # 3600
        seconds = parser.parse("hourly")  # 3600
    """

    # 单位 → 秒
    UNIT_MAP: dict[str, int] = {
        "s": 1,
        "sec": 1,
        "second": 1,
        "m": 60,
        "min": 60,
        "minute": 60,
        "h": 3600,
        "hr": 3600,
        "hour": 3600,
        "d": 86400,
        "day": 86400,
    }

    # 英文简写 → 秒
    SHORTHAND_MAP: dict[str, int] = {
        "hourly": 3600,
        "daily": 86400,
        "weekly": 604800,
    }

    def parse(self, expression: str) -> int:
        """解析间隔表达式为秒数。

        Args:
            expression: "30s" | "5m" | "1h" | "0 9 * * *" | "hourly"

        Returns:
            秒数

        Raises:
            CronParseError: 无法解析
        """
        expr = expression.strip().lower()

        # 纯数字?
        if expr.isdigit():
            return int(expr)

        # 英文简写?
        if expr in self.SHORTHAND_MAP:
            return self.SHORTHAND_MAP[expr]

        # 纯数字+单位?
        match = re.match(r"^(\d+)\s*([a-zA-Z]+)$", expr)
        if match:
            num = int(match.group(1))
            unit = match.group(2)
            if unit in self.UNIT_MAP:
                return num * self.UNIT_MAP[unit]
            raise CronParseError(f"未知单位: {unit}")

        # Cron 5字段? (简化——只处理固定频率的 cron)
        parts = expr.split()
        if len(parts) == 5:
            # 检查是否为简单的固定间隔 cron
            return self._parse_cron_minute_hour(parts)

        raise CronParseError(f"无法解析间隔表达式: {expression}")

    def _parse_cron_minute_hour(self, parts: list[str]) -> int:
        """解析最简单的 cron 模式——每小时/每天。

        不实现完整 cron 引擎——只支持 "每小时" 和 "每天" 的常见模式。
        """
        minute, hour, dom, month, dow = parts

        # "0 * * * *" → 每小时
        if minute == "0" and hour == "*":
            return 3600
        # "*/N * * * *" → 每 N 分钟
        if minute.startswith("*/"):
            try:
                n = int(minute[2:])
                return n * 60
            except ValueError:
                raise CronParseError(f"无效的 cron 分钟: {minute}")
        # "0 <H> * * *" → 每天 H 点
        if minute == "0" and hour.isdigit() and dom == "*":
            return 86400  # 每天一次

        raise CronParseError(f"不支持的 cron 模式: {' '.join(parts)}")
