"""CI 性能阈值检查——解析 pytest-benchmark JSON 输出。

读取 benchmarks 的 P50/P95 并比对阈值。全部非阻塞——超标记 warning，
不返回非零退出码（不阻断 merge）。
"""

import json
import sys
from pathlib import Path

# 阈值（CI 环境）
THRESHOLDS_MS = {
    "test_perf_single_task_e2e": {"p95": 12000},        # 单任务 P95 < 12s
    "test_perf_concurrent_3_tasks": {"p95": 20000},     # 并发 3 P95 < 20s
    "test_perf_single_task_roundtrip": {"p95": 500},    # API 往返 P95 < 500ms
    "test_perf_eventbus_throughput": {"mean": 100},     # 1000 事件 < 100ms
    "test_perf_eventbus_pubsub_roundtrip": {"p95": 10}, # pub-sub < 10ms
}

THRESHOLDS_EVENTS_PER_SEC = {
    "test_perf_eventbus_throughput": 5000,
}


def main() -> int:
    perf_json = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("perf.json")
    if not perf_json.exists():
        print(f"⚠️  性能报告 {perf_json} 不存在，跳过阈值检查")
        return 0

    data = json.loads(perf_json.read_text())
    warnings = 0

    for bench in data.get("benchmarks", []):
        name = bench.get("name", "unknown")
        stats = bench.get("stats", {})
        thresholds = THRESHOLDS_MS.get(name, {})

        for metric, limit_ms in thresholds.items():
            actual_ms = stats.get(metric, 0) * 1000  # pytest-benchmark 单位是秒
            if actual_ms > limit_ms:
                print(
                    f"⚠️  WARNING: {name} {metric}={actual_ms:.0f}ms "
                    f"(阈值 {limit_ms}ms)"
                )
                warnings += 1
            else:
                print(f"✅ {name} {metric}={actual_ms:.0f}ms OK")

        # 检查吞吐量
        if name in THRESHOLDS_EVENTS_PER_SEC:
            min_rate = THRESHOLDS_EVENTS_PER_SEC[name]
            ops = stats.get("ops", 0)
            if ops < min_rate:
                print(
                    f"⚠️  WARNING: {name} throughput={ops:.0f} events/s "
                    f"(阈值 {min_rate})"
                )
                warnings += 1

    if warnings:
        print(f"\n⚠️  {warnings} 项性能指标超标——不阻断 merge，请人工审查")
    else:
        print("\n✅ 所有性能指标达标")

    return 0  # 非阻塞


if __name__ == "__main__":
    sys.exit(main())
