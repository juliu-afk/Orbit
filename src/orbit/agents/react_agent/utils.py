"""ReActAgent 工具函数——从 react_agent.py 拆分."""


def _truncate_output(text: str, max_chars: int = 10000) -> str:
    """截断超长输出——头尾 + 摘要。对标 Claude Code Tool Output Truncation。"""
    if len(text) <= max_chars:
        return text
    half = max_chars // 2
    cut = len(text) - max_chars
    return text[:half] + f"\n\n... [截断 {cut} 字符] ...\n\n" + text[-half:]
