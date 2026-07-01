"""沙箱专用断言。

验证代码隔离执行结果。
"""

from __future__ import annotations

from typing import Any


def assert_execution_isolated(
    result: Any,
    msg: str = "",
) -> None:
    """验证沙箱执行结果为隔离成功。

    兼容多种结果类型：
    - dict: {"exit_code": 0, "stdout": "..."}
    - tuple: (exit_code, stdout, stderr)
    - str: stdout 字符串

    Args:
        result: 沙箱执行结果
        msg: 额外错误消息
    """
    exit_code = None
    stdout = ""

    if isinstance(result, dict):
        exit_code = result.get("exit_code", -1)
        stdout = result.get("stdout", "")
    elif isinstance(result, tuple) and len(result) >= 2:
        exit_code = result[0]
        stdout = result[1]
    elif isinstance(result, str):
        exit_code = 0
        stdout = result
    else:
        detail = f"结果类型: {type(result)}, 值: {result}"
        if msg:
            detail = f"{msg}\n{detail}"
        raise AssertionError(f"无法解析沙箱执行结果\n{detail}")

    detail = f"exit_code={exit_code}, stdout={stdout[:200]}"
    if msg:
        detail = f"{msg}\n{detail}"

    assert exit_code == 0, f"沙箱执行失败（exit_code={exit_code}）\n{detail}"
