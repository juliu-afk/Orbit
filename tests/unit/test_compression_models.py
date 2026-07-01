"""Compression models 单元测试。"""
from orbit.compression.models import CompressionAction, CompressionResult

def test_compression_action_enum():
    assert CompressionAction.SKIP.value == "skip"
    assert CompressionAction.WARN.value == "warn"
    assert CompressionAction.FORCE.value == "force"
    assert CompressionAction.FORK.value == "fork"

def test_compression_result():
    r = CompressionResult(action=CompressionAction.SKIP, original_tokens=100, compressed_tokens=100, ratio=0.0)
    assert r.action == CompressionAction.SKIP
    assert r.ratio == 0.0
