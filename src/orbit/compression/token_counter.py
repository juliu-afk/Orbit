"""Token 计数器——tiktoken 精确计数 + chars/4 回退 (5B.1)."""

from __future__ import annotations
import structlog

logger = structlog.get_logger(__name__)

try:
    import tiktoken

    _TIKTOKEN_AVAILABLE = True
except ImportError:
    _TIKTOKEN_AVAILABLE = False

_encoder_cache = {}
_DEFAULT_ENCODING = "o200k_base"


class TokenCounter:
    CHARS_PER_TOKEN = 4

    def __init__(self, encoding: str | None = None):
        self._encoding_name = encoding or _DEFAULT_ENCODING
        self._encoder = None
        if _TIKTOKEN_AVAILABLE:
            try:
                enc = tiktoken.get_encoding(self._encoding_name)
                _encoder_cache[self._encoding_name] = enc
                self._encoder = enc
            except Exception:
                pass

    @property
    def use_tiktoken(self):
        return self._encoder is not None

    def count(self, text):
        if not text:
            return 0
        if self._encoder is not None:
            return len(self._encoder.encode(text))
        return max(1, len(text) // self.CHARS_PER_TOKEN)


_counter = None


def get_token_counter():
    global _counter
    if _counter is None:
        _counter = TokenCounter()
    return _counter


def count_tokens(text):
    return get_token_counter().count(text)
