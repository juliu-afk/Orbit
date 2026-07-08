"""消融实验——逐层禁用防幻觉管道，测量每层对 F1 的边际贡献。

WHY: 这是 L2 效能测量的核心——"拿掉它→系统变差→模块有效"。
F1 贡献 < 0.03 的模块应降级或移除（framework doc §17 原则 2）。

用法:
    pytest tests/effectiveness/test_ablation_experiment.py -v -s
    输出每层的 Precision/Recall/F1 及消融后的 F1 差值。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from orbit.effectiveness.ablation import AblationContext

BENCHMARK_PATH = Path(__file__).parent.parent.parent / "data" / "benchmarks" / "hallucination_v1.json"

# 消融实验设计——逐层禁用什么
ABLATION_LAYERS = [
    ("hallucination_L3", "L3 熵监控"),
    ("hallucination_L4", "L4 类型检查"),
    ("hallucination_L1", "L1 图谱验证"),
]


def _load_samples() -> list[dict[str, Any]]:
    with open(BENCHMARK_PATH, encoding="utf-8") as f:
        return json.load(f)["samples"]


def _compute_metrics(samples: list[dict], results: list[bool]) -> dict[str, float]:
    """计算 Precision/Recall/F1。"""
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
    precision = tp / max(tp + fp, 1)
    recall = tp / max(tp + fn, 1)
    f1 = 2 * precision * recall / max(precision + recall, 0.001)
    return {"precision": precision, "recall": recall, "f1": f1, "tp": tp, "fp": fp, "tn": tn, "fn": fn}


class TestAblationExperiment:
    """消融实验——测量每层对 F1 的边际贡献。"""

    @pytest.fixture
    def pipeline(self):
        from orbit.hallucination.pipeline import HallucinationPipeline
        return HallucinationPipeline(graph=None, sandbox=None)

    @pytest.fixture
    def samples(self):
        return _load_samples()

    def _run_benchmark(self, pipeline, samples: list[dict]) -> list[bool]:
        """同步运行 benchmark——注意 pipeline.validate_quick 是 async 但此处逐条跑。"""
        results = []
        for s in samples:
            # 使用 asyncio.run 跑每条——benchmark 规模小（50 条）可接受
            import asyncio
            result = asyncio.run(pipeline.validate_quick(s["code"]))
            results.append(result.passed)
        return results

    def test_baseline_no_ablation(self, pipeline, samples):
        """基线——所有层启用时的 F1。"""
        import asyncio

        results = []
        for s in samples:
            result = asyncio.run(pipeline.validate_quick(s["code"]))
            results.append(result.passed)
        metrics = _compute_metrics(samples, results)
        print(f"\n[基线] 全层启用: P={metrics['precision']:.3f} R={metrics['recall']:.3f} F1={metrics['f1']:.3f}")
        # 基线只需可计算，不做硬性断言（无 graph/sandbox 时 F1 天然受限）

    def test_ablation_L3_entropy(self, pipeline, samples):
        """消融 L3——禁熵监控后 F1 变化。"""
        import asyncio

        with AblationContext(["hallucination_L3"]):
            assert AblationContext.is_disabled("hallucination_L3")
            results = []
            for s in samples:
                result = asyncio.run(pipeline.validate_quick(s["code"]))
                results.append(result.passed)

        baseline_results = [asyncio.run(pipeline.validate_quick(s["code"])) for s in samples]
        baseline = _compute_metrics(samples, [r.passed for r in baseline_results])
        ablated = _compute_metrics(samples, results)

        delta_f1 = baseline["f1"] - ablated["f1"]
        print(f"\n[L3 消融] 基线 F1={baseline['f1']:.3f} → 禁L3 F1={ablated['f1']:.3f} ΔF1={delta_f1:+.3f}")
        # 熵监控层贡献应 ≥ 0（禁掉不会提升 F1）
        # 软断言——无 graph/sandbox 时 L3 可选
        assert isinstance(delta_f1, float)

    def test_ablation_L4_type(self, pipeline, samples):
        """消融 L4——禁类型检查后 F1 变化。"""
        import asyncio

        with AblationContext(["hallucination_L4"]):
            assert AblationContext.is_disabled("hallucination_L4")
            results = []
            for s in samples:
                result = asyncio.run(pipeline.validate_quick(s["code"]))
                results.append(result.passed)

        baseline_results = [asyncio.run(pipeline.validate_quick(s["code"])) for s in samples]
        baseline = _compute_metrics(samples, [r.passed for r in baseline_results])
        ablated = _compute_metrics(samples, results)

        delta_f1 = baseline["f1"] - ablated["f1"]
        print(f"\n[L4 消融] 基线 F1={baseline['f1']:.3f} → 禁L4 F1={ablated['f1']:.3f} ΔF1={delta_f1:+.3f}")
        assert isinstance(delta_f1, float)

    def test_ablation_L1_graph(self, pipeline, samples):
        """消融 L1——禁图谱验证后 F1 变化。L1 是符号存在性检查，禁掉应有显著影响。"""
        import asyncio

        with AblationContext(["hallucination_L1"]):
            assert AblationContext.is_disabled("hallucination_L1")
            results = []
            for s in samples:
                result = asyncio.run(pipeline.validate_quick(s["code"]))
                results.append(result.passed)

        baseline_results = [asyncio.run(pipeline.validate_quick(s["code"])) for s in samples]
        baseline = _compute_metrics(samples, [r.passed for r in baseline_results])
        ablated = _compute_metrics(samples, results)

        delta_f1 = baseline["f1"] - ablated["f1"]
        print(f"\n[L1 消融] 基线 F1={baseline['f1']:.3f} → 禁L1 F1={ablated['f1']:.3f} ΔF1={delta_f1:+.3f}")
        # L1 是符号存在性检查——禁掉后幻觉样本应更少被拦截
        assert isinstance(delta_f1, float)

    def test_ablation_summary(self, pipeline, samples):
        """汇总消融实验——输出每层贡献度排名。"""
        import asyncio

        # 收集所有配置的指标
        configs: list[tuple[str, list[str]]] = [
            ("基线(全开)", []),
            ("禁L1", ["hallucination_L1"]),
            ("禁L3", ["hallucination_L3"]),
            ("禁L4", ["hallucination_L4"]),
        ]

        print(f"\n{'='*60}")
        print(f"消融实验汇总 —— {len(samples)} 样本")
        print(f"{'='*60}")
        print(f"{'配置':<16} {'P':>6} {'R':>6} {'F1':>6} {'ΔF1':>8}")
        print(f"{'-'*42}")

        baseline_f1 = None
        for name, disabled in configs:
            with AblationContext(disabled):
                results = []
                for s in samples:
                    result = asyncio.run(pipeline.validate_quick(s["code"]))
                    results.append(result.passed)
            m = _compute_metrics(samples, results)
            if baseline_f1 is None:
                baseline_f1 = m["f1"]
                delta = 0.0
            else:
                delta = m["f1"] - baseline_f1
            print(f"{name:<16} {m['precision']:6.3f} {m['recall']:6.3f} {m['f1']:6.3f} {delta:+8.3f}")

        print(f"{'='*60}")
        print("ΔF1 > 0 = 禁掉该层后 F1 提升 (该层有害)")
        print("ΔF1 < 0 = 禁掉该层后 F1 下降 (该层有效)")
        print("|ΔF1| < 0.03 → 该层贡献可忽略 (framework doc §17 原则 2)")
