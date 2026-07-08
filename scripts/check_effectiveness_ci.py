#!/usr/bin/env python3
"""持续效能回归 CI 脚本——每次 PR 跑效能基准，下降 > 5% → 红灯。

Phase 3 模块效能框架的自动化门禁（framework doc §16.2 任务 16）。

用法:
    python scripts/check_effectiveness_ci.py --threshold 0.05

Exit codes:
    0 = 效能无明显下降
    1 = 效能下降超过阈值
    2 = 基准数据缺失
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
BENCHMARK_PATH = PROJECT_ROOT / "data" / "benchmarks" / "hallucination_v1.json"
BASELINE_PATH = PROJECT_ROOT / ".benchmarks" / "effectiveness_baseline.json"


def load_baseline() -> dict | None:
    """加载上次记录的基线效能数据。"""
    if not BASELINE_PATH.exists():
        return None
    with open(BASELINE_PATH, encoding="utf-8") as f:
        return json.load(f)


def save_baseline(data: dict) -> None:
    """保存当前效能数据为基线。"""
    BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(BASELINE_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def run_benchmark() -> dict:
    """运行效能基准——返回当前指标。

    Returns:
        dict with keys: f1, precision, recall, sample_count, timestamp
    """
    import asyncio

    if not BENCHMARK_PATH.exists():
        print(f"ERROR: Benchmark not found: {BENCHMARK_PATH}", file=sys.stderr)
        sys.exit(2)

    from orbit.hallucination.pipeline import HallucinationPipeline
    from tests.lib.mocks.code_graph import MockCodeGraphEngine

    with open(BENCHMARK_PATH, encoding="utf-8") as f:
        samples = json.load(f)["samples"]

    pipeline = HallucinationPipeline(graph=MockCodeGraphEngine(), sandbox=None)

    async def _run():
        results = []
        for s in samples:
            r = await pipeline.validate_quick(s["code"])
            results.append(r.passed)
        return results

    results = asyncio.run(_run())

    tp = fp = tn = fn = 0
    for s, passed in zip(samples, results):
        is_hall = s["label"] == "hallucination"
        if not passed and is_hall:
            tp += 1
        elif not passed and not is_hall:
            fp += 1
        elif passed and not is_hall:
            tn += 1
        else:
            fn += 1

    prec = tp / max(tp + fp, 1)
    rec = tp / max(tp + fn, 1)
    f1 = 2 * prec * rec / max(prec + rec, 0.001)

    from datetime import UTC, datetime
    return {
        "f1": round(f1, 4),
        "precision": round(prec, 4),
        "recall": round(rec, 4),
        "sample_count": len(samples),
        "tp": tp, "fp": fp, "tn": tn, "fn": fn,
        "timestamp": datetime.now(UTC).isoformat(),
    }


def main():
    parser = argparse.ArgumentParser(description="效能回归 CI 门禁")
    parser.add_argument("--threshold", type=float, default=0.05,
                       help="F1 下降容忍阈值（默认 5%）")
    parser.add_argument("--save-baseline", action="store_true",
                       help="保存当前结果为基线（首次运行或手动重置）")
    args = parser.parse_args()

    current = run_benchmark()
    print(f"Current: F1={current['f1']:.4f} P={current['precision']:.4f} "
          f"R={current['recall']:.4f} N={current['sample_count']}")

    baseline = load_baseline()
    if baseline is None or args.save_baseline:
        save_baseline(current)
        print("Baseline saved (first run or --save-baseline)")
        sys.exit(0)

    delta = baseline["f1"] - current["f1"]
    print(f"Baseline F1={baseline['f1']:.4f} → Current F1={current['f1']:.4f} "
          f"Δ={delta:+.4f}")

    if delta > args.threshold:
        print(f"FAIL: F1 dropped by {delta:.4f} > threshold {args.threshold}")
        print(f"  TP: {baseline['tp']}→{current['tp']} "
              f"FP: {baseline['fp']}→{current['fp']}")
        sys.exit(1)
    else:
        print(f"PASS: F1 change {delta:+.4f} within threshold ±{args.threshold}")
        # 更新基线——如果当前更好
        if delta < 0:  # 负数 = 提升
            save_baseline(current)
            print(f"Baseline updated (improvement: {-delta:+.4f})")
        sys.exit(0)


if __name__ == "__main__":
    main()
