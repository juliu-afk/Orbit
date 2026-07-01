from orbit.stream.cancellation import CancellationToken
import asyncio
def test_init_not_cancelled():
    t = CancellationToken()
    assert t.is_cancelled is False
def test_cancel():
    t = CancellationToken()
    t.cancel()
    assert t.is_cancelled is True
