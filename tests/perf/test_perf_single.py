"""单任务全链路性能基准。

用 time.perf_counter 手动计时（benchmark fixture 与 session-scope async 冲突）。
"""

import asyncio
import time
from typing import Any

import pytest


@pytest.mark.perf
@pytest.mark.asyncio(loop_scope="function")
async def test_perf_single_task_e2e(e2e_app: Any) -> None:
    """单任务 IDLE→DONE 全链路延迟。

    P95 阈值: <12s（CI）/ <8s（预发布）。
    """
    scheduler = getattr(e2e_app, "_scheduler", None)
    assert scheduler is not None

    task_id = "perf-single-00000000000000000000000000"

    t0 = time.perf_counter()
    state = await asyncio.wait_for(
        scheduler.run_task(task_id, "性能测试——单任务全链路"),
        timeout=30,
    )
    elapsed = time.perf_counter() - t0

    assert state is not None
    assert elapsed < 12.0, f"单任务耗时 {elapsed:.1f}s 超过阈值 12s"


@pytest.mark.perf
@pytest.mark.asyncio(loop_scope="function")
async def test_perf_single_task_roundtrip(e2e_app: Any) -> None:
    """API 往返延迟——POST→GET 3 次取平均。

    P95 阈值: <500ms。
    """
    times = []
    for _ in range(3):
        t0 = time.perf_counter()
        resp = await e2e_app.post(
            "/api/v1/tasks",
            json={
                "prd": "性能测试——API 往返延迟测试验证",
                "language": "python",
            },
        )
        assert resp.status_code == 200
        task_id = resp.json()["task_id"]
        await e2e_app.get(f"/api/v1/tasks/{task_id}")
        times.append(time.perf_counter() - t0)

    avg = sum(times) / len(times)
    assert avg < 0.5, f"API 往返平均 {avg*1000:.0f}ms 超过阈值 500ms"
