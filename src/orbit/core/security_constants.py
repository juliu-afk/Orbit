"""安全基线常量——shell 元字符、命令白名单等。

WHY 统一常量: Issue #126 PR#130 review——terminal_routes 和 verifier 各自定义
_SHELL_META，内容不一致（一个有 "&" 一个有 ">"），抽取消除歧义。
"""

from __future__ import annotations

# shell 元字符——禁止在命令参数中出现，防止命令拼接和代码注入
# WHY frozenset: 仅用于成员检测，不可变保证不会被意外修改
SHELL_METACHARACTERS: frozenset[str] = frozenset(
    {";", "|", "&", "&&", "||", "$(", "`", ">"}
)
