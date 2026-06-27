"""BashValidators——Shell 命令安全校验。

对标 Claude Code 23 Bash validators + AST-level shell parsing。
Orbit 简化版: 白名单 + 危险模式检测 + 命令长度限制。
"""

from __future__ import annotations

import re


class BashValidators:
    """Shell 命令安全检查器。

    规则:
    1. 白名单模式——允许的命令前缀
    2. 黑名单模式——禁止的危险操作
    3. 结构限制——管道/重定向检测
    4. 长度限制——防止命令注入
    """

    # 允许的命令白名单（对标 Claude Code）
    ALLOWED_COMMANDS = {
        "git",
        "pytest",
        "python",
        "python3",
        "pnpm",
        "uv",
        "poetry",
        "ls",
        "cat",
        "grep",
        "find",
        "head",
        "tail",
        "wc",
        "echo",
        "mkdir",
        "touch",
        "cp",
        "mv",
        "rm",
        "pip",
        "npm",
        "node",
        "cargo",
        "make",
        "curl",
        "docker",
        "kubectl",
    }

    # 危险模式——始终拒绝
    DANGEROUS_PATTERNS = [
        (r"rm\s+-rf\s+/", "删除根目录"),
        (r"rm\s+-rf\s+~", "删除 home 目录"),
        (r">\s*/dev/[hs]d[a-z]", "覆盖磁盘设备"),
        (r"mkfs\.", "格式化文件系统"),
        (r"dd\s+if=", "磁盘直接读写"),
        (r":\(\)\s*\{\s*:\|:&\s*\};:", "fork bomb"),
        (r"chmod\s+777", "危险权限设置"),
        (r"wget.*\|.*sh", "下载并执行脚本"),
        (r"curl.*\|.*bash", "curl 管道 bash"),
        (r"eval\s+", "eval 动态执行"),
        (r"sudo\s+", "提权操作"),
        (r"su\s+-", "切换用户"),
    ]

    # 命令最大长度
    MAX_COMMAND_LENGTH = 4000

    @classmethod
    def validate(cls, command: str) -> str:
        """验证 shell 命令安全性。

        Args:
            command: 要执行的命令字符串

        Returns:
            通过验证的命令（trim 后）

        Raises:
            ValueError: 命令不安全
        """
        cmd = command.strip()

        # 1. 长度检查
        if len(cmd) > cls.MAX_COMMAND_LENGTH:
            raise ValueError(f"命令过长 ({len(cmd)} > {cls.MAX_COMMAND_LENGTH})——拒绝执行")

        # 2. 空命令
        if not cmd:
            raise ValueError("空命令——拒绝执行")

        # 3. 危险模式检测
        for pattern, desc in cls.DANGEROUS_PATTERNS:
            if re.search(pattern, cmd):
                raise ValueError(f"安全拒绝——{desc}: {cmd[:100]}")

        # 4. 白名单检查——取命令的第一个词
        first_word = cmd.split()[0] if cmd.split() else ""
        # 去掉路径前缀（/usr/bin/git → git）
        base_cmd = first_word.rsplit("/", 1)[-1] if "/" in first_word else first_word

        if base_cmd not in cls.ALLOWED_COMMANDS:
            raise ValueError(f"命令不在白名单中: {base_cmd}。允许: {sorted(cls.ALLOWED_COMMANDS)}")

        return cmd
