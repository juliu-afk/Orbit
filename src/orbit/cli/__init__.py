"""Orbit CLI——命令行工具入口。

Usage:
  orbit init-packages             初始化基础代码包库
  orbit brief check <path>        检查/生成项目说明书

WHY argparse 而非 click: 零依赖，stdlib 够用。
"""

from __future__ import annotations

import os
import sys

from .commands import cmd_brief_check, cmd_init_packages


def main() -> None:
    """CLI 主入口。"""
    if len(sys.argv) < 2:
        _print_usage()
        sys.exit(1)

    command = sys.argv[1]

    if command == "init-packages":
        cmd_init_packages()
    elif command == "brief":
        if len(sys.argv) < 4 or sys.argv[2] != "check":
            _print_usage()
            sys.exit(1)
        cmd_brief_check(sys.argv[3])
    else:
        print(f"未知命令: {command}")
        _print_usage()
        sys.exit(1)


def _print_usage() -> None:
    print("Orbit CLI")
    print("  orbit init-packages             初始化基础代码包库（3 个模板）")
    print("  orbit brief check <path>        检查/生成项目说明书")
