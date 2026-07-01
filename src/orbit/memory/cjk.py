"""CJK 分词器 (Phase 2 AC9 + 5B.2 jieba 增强).

5B.2: jieba 精确分词优先，bigram 回退。
"""

from __future__ import annotations

import re

try:
    import jieba

    _JIEBA_AVAILABLE = True
except ImportError:
    _JIEBA_AVAILABLE = False

# Unicode CJK 范围
CJK_RANGES = [
    (0x4E00, 0x9FFF),  # CJK Unified Ideographs
    (0x3400, 0x4DBF),  # CJK Unified Ideographs Extension A
    (0x20000, 0x2A6DF),  # CJK Unified Ideographs Extension B
    (0xF900, 0xFAFF),  # CJK Compatibility Ideographs
    (0x3040, 0x309F),  # Hiragana
    (0x30A0, 0x30FF),  # Katakana
    (0xAC00, 0xD7AF),  # Hangul Syllables
]


def _is_cjk(char: str) -> bool:
    """判断单个字符是否在 CJK 范围内."""
    cp = ord(char)
    return any(lo <= cp <= hi for lo, hi in CJK_RANGES)


# 用于分割英文单词 + CJK 字符的混合文本
_TOKENIZE_RE = re.compile(
    r"([a-zA-Z0-9_]+(?:[.'\-][a-zA-Z0-9_]+)*)"  # 英文词/数字/标识符
    r"|([一-鿿㐀-䶿぀-ゟ゠-ヿ가-힯])"  # CJK字符
    r"|([^\s])"  # 其他非空字符
)


def tokenize_for_fts(text: str) -> str:
    """将文本转成 FTS5 可搜索的 token 序列.

    CJK 字符 → bigram 切割（"上下文" → "上下 下文"）
    英文单词 → 保留原词
    混合文本 → 逐段处理

    Args:
        text: 原始文本

    Returns:
        FTS5 MATCH 查询用的 token 字符串
    """
    if not text:
        return ""

    tokens: list[str] = []
    cjk_buffer: list[str] = []
    last_was_cjk = False

    def _flush_cjk() -> None:
        """将 CJK buffer 中的字符转成 bigram 并添加到 tokens."""
        nonlocal last_was_cjk
        if len(cjk_buffer) == 1:
            tokens.append(cjk_buffer[0])
        elif len(cjk_buffer) >= 2:
            for i in range(len(cjk_buffer) - 1):
                tokens.append(cjk_buffer[i] + cjk_buffer[i + 1])
        cjk_buffer.clear()
        last_was_cjk = False

    for match in _TOKENIZE_RE.finditer(text):
        eng, cjk, other = match.groups()
        if cjk:
            # 累积连续 CJK 字符，不立即 flush
            cjk_buffer.append(cjk)
            last_was_cjk = True
        else:
            # 非 CJK → 先排空 CJK buffer
            _flush_cjk()
            if eng:
                tokens.append(eng.lower())
            elif other and not other.isspace():
                tokens.append(other)

    _flush_cjk()  # 排空末尾 CJK buffer

    return " ".join(tokens)


def _tokenize_cjk_jieba(text: str) -> str:
    """jieba 精确分词 (5B.2)."""
    if not text:
        return ""
    if _JIEBA_AVAILABLE:
        tokens = jieba.lcut(text)
        return " ".join(t for t in tokens if t.strip())
    return tokenize_for_fts(text)


# P1 LOG-8: FTS5 特殊字符——需转义防止查询语法注入
# P2-1 (PR#139): 补遗漏的 " (phrase) 和 : (column filter)
_FTS5_SPECIAL = re.compile(r'([*"():~&|!^])')


def _escape_fts5(text: str) -> str:
    """转义 FTS5 特殊字符——防止用户输入被解释为查询运算符。"""
    return _FTS5_SPECIAL.sub(r'\\\1', text)


def build_fts_query(raw_query: str) -> str:
    """构建 FTS5 MATCH 查询——jieba 优先，bigram 回退.

    P1 LOG-8: 用户输入先经 FTS5 转义防止特殊字符注入。
    """
    safe = _escape_fts5(raw_query)
    return _tokenize_cjk_jieba(safe)
