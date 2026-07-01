from orbit.compression.models import CompressionAction, CompressionResult
def test_enum():
    assert CompressionAction.SKIP.value == "skip"
    assert CompressionAction.FORCE.value == "force"
def test_result():
    r = CompressionResult(action=CompressionAction.SKIP, original_tokens=100, compressed_tokens=100, ratio=0.0)
    assert r.ratio == 0.0
