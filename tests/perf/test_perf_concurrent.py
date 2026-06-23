"""并发任务性能基准。"""

import asyncio
import time
from typing import Any

import pytest


@pytest.mark.perf
@pytest.mark.asyncio(loop_scope="function")
async def test_perf_concurrent_3_tasks(e2e_app: Any) -> None:
    """并发 3 任务——验证调度器并发能力。

    P95 阈值: <20s（CI 环境放宽）。
    """
    scheduler = getattr(e2e_app, "_scheduler", None)
    assert scheduler is not None

    async def run_concurrent() -> Any:
        tasks = [
            scheduler.run_task(f"perf-concurrent-{i:032d}", f"并发任务 #{i}") for i in range(3)
        ]
        return await asyncio.gather(*tasks)

    t0 = time.perf_counter()
    states = await asyncio.wait_for(run_concurrent(), timeout=30)
    elapsed = time.perf_counter() - t0

    assert len(states) == 3
    for s in states:
        assert s is not None
    assert elapsed < 20.0, f"并发 3 任务耗时 {elapsed:.1f}s 超过阈值 20s"
