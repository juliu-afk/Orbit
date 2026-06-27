"""检查点边界算法测试 (Phase 2 AC11b)."""

from __future__ import annotations

from orbit.checkpoint.boundary import (
    compute_checkpoint_boundary,
    erase_compressible,
    should_protect,
)


class TestTextProtections:
    def test_protect_error_message(self):
        assert should_protect("Error: something went wrong")

    def test_protect_file_path(self):
        assert should_protect("src/orbit/main.py")

    def test_protect_line_number(self):
        assert should_protect("error at line 42")

    def test_protect_config_value(self):
        assert should_protect("api_key: sk-123456")

    def test_no_protect_normal_text(self):
        assert not should_protect("hello world")


class TestEraseCompressible:
    def test_erase_large_code_block(self):
        text = "before\n```\n" + "x" * 500 + "\n```\nafter"
        result, erased = erase_compressible(text)
        assert erased > 0
        assert "可压缩" in result
        assert "before" in result

    def test_no_erase_small_content(self):
        text = "small text"
        result, erased = erase_compressible(text)
        assert erased == 0
        assert result == text


class TestCheckpointBoundary:
    def test_tail_selection(self):
        msgs = [{"role": "system", "content": "sys"}] + [
            {"role": "user", "content": "x" * 500} for _ in range(50)
        ]
        tail, meta = compute_checkpoint_boundary(
            msgs,
            tail_token_target=1000,
            min_tail_tokens=100,
            max_tail_tokens=2000,
        )
        assert len(tail) < len(msgs)
        assert meta["kept_tokens"] > 0
        assert meta["total_messages"] == len(msgs)

    def test_small_messages_kept_fully(self):
        msgs = [{"role": "user", "content": "hi"}]
        tail, meta = compute_checkpoint_boundary(msgs)
        assert len(tail) == 1
        assert meta["kept_messages"] == 1
