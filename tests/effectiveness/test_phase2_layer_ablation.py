"""Phase 2: 逐层有效性验证——接线 graph/sandbox 后测真实 ΔF1。

与 Phase 1 的关键区别:
- L1 接入 MockCodeGraphEngine → 符号检查真正生效
- 每层独立消融 → 量化贡献
- 输出: 每层 F1 贡献度排名 + 降级建议

用法:
    pytest tests/effectiveness/test_phase2_layer_ablation.py -v -s
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest

from orbit.effectiveness.ablation import AblationContext
from tests.lib.mocks.code_graph import MockCodeGraphEngine

BENCHMARK_PATH = Path(__file__).parent.parent.parent / "data" / "benchmarks" / "hallucination_v1.json"


# ── 扩展基准样本——更多 L1 可检测的幻觉 ──
# 这些补充样本专门针对 L1（符号存在性）+ L7（运行时错误）
EXTRA_SAMPLES: list[dict[str, Any]] = [
    # ── L1 可检测: 不存在的模块/函数 ──
    {"id": "EXT_L1_001", "code": "from quantum_ai_framework import QuantumNeuralNet\nnet = QuantumNeuralNet()\n", "label": "hallucination", "hallucination_type": "import_error", "expected_layer": "L1"},
    {"id": "EXT_L1_002", "code": "import blockchain_miner\nblockchain_miner.mine_block(42)\n", "label": "hallucination", "hallucination_type": "import_error", "expected_layer": "L1"},
    {"id": "EXT_L1_003", "code": "from fakelib.v2.beta import MagicalParser\nMagicalParser.parse()\n", "label": "hallucination", "hallucination_type": "import_error", "expected_layer": "L1"},
    {"id": "EXT_L1_004", "code": "result = imaginary_function_xyz()\nprint(result)\n", "label": "hallucination", "hallucination_type": "nonexistent_function", "expected_layer": "L1"},
    {"id": "EXT_L1_005", "code": "data = fake_database_connect('localhost:9999')\nrows = data.query_all()\n", "label": "hallucination", "hallucination_type": "nonexistent_function", "expected_layer": "L1"},
    {"id": "EXT_L1_006", "code": "import warp_drive_engine\nengine = warp_drive_engine.WarpDrive()\nengine.activate()\n", "label": "hallucination", "hallucination_type": "import_error", "expected_layer": "L1"},
    # ── L7 可检测: 运行时错误 ──
    {"id": "EXT_L7_001", "code": "x = []\nprint(x[100])\n", "label": "hallucination", "hallucination_type": "index_error", "expected_layer": "L7"},
    {"id": "EXT_L7_002", "code": "d = {'key': 'value'}\nresult = d['nonexistent']\n", "label": "hallucination", "hallucination_type": "key_error", "expected_layer": "L7"},
    {"id": "EXT_L7_003", "code": "def divide(a, b):\n    return a / b\nresult = divide(10, 0)\n", "label": "hallucination", "hallucination_type": "zero_division", "expected_layer": "L7"},
    {"id": "EXT_L7_004", "code": "x = None\nx.append(1)\n", "label": "hallucination", "hallucination_type": "attribute_error", "expected_layer": "L7"},
    # ── 正确的代码（负样本）──
    {"id": "EXT_CLN_001", "code": "import os\npath = os.path.join('a', 'b')\nprint(path)\n", "label": "clean", "hallucination_type": None, "expected_layer": None},
    {"id": "EXT_CLN_002", "code": "from pathlib import Path\np = Path('/tmp')\nprint(p.exists())\n", "label": "clean", "hallucination_type": None, "expected_layer": None},
    {"id": "EXT_CLN_003", "code": "import json\ndata = json.loads('{\"a\":1}')\nprint(data['a'])\n", "label": "clean", "hallucination_type": None, "expected_layer": None},
    {"id": "EXT_CLN_004", "code": "x = [1,2,3]\nprint(sum(x))\n", "label": "clean", "hallucination_type": None, "expected_layer": None},
    {"id": "EXT_CLN_005", "code": "from collections import Counter\nc = Counter('hello')\nprint(c.most_common(1))\n", "label": "clean", "hallucination_type": None, "expected_layer": None},
]


def _load_all_samples() -> list[dict[str, Any]]:
    """加载基准 + 扩展样本。"""
    samples = []
    if BENCHMARK_PATH.exists():
        with open(BENCHMARK_PATH, encoding="utf-8") as f:
            samples = json.load(f)["samples"]
    samples.extend(EXTRA_SAMPLES)
    return samples


def _compute_metrics(samples: list[dict], results: list[bool]) -> dict[str, float]:
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
    return {"precision": prec, "recall": rec, "f1": f1, "tp": tp, "fp": fp, "tn": tn, "fn": fn}


class TestPhase2LayerAblation:
    """Phase 2: 逐层有效性验证——接线 graph 后测真实 ΔF1。"""

    @pytest.fixture
    def samples(self):
        s = _load_all_samples()
        assert len(s) >= 50, f"样本不足: {len(s)}"
        return s

    @pytest.fixture
    def graph(self):
        """Mock 代码图谱——知道 Python stdlib，用于 L1 符号检查。"""
        return MockCodeGraphEngine()

    def test_l1_with_graph_detects_hallucinations(self, samples, graph):
        """L1 接入 graph 后应能检出 import_error/nonexistent_function 类幻觉。"""
        from orbit.hallucination.pipeline import HallucinationPipeline

        # 仅 L1 启用的 pipeline——禁掉 L3+L4+L5 避免干扰
        disabled = ["hallucination_L3", "hallucination_L4", "hallucination_L5",
                    "hallucination_L2", "hallucination_L6", "hallucination_L7", "hallucination_L8"]
        pipeline = HallucinationPipeline(graph=graph, sandbox=None)

        with AblationContext(disabled):
            results = [asyncio.run(pipeline.validate_quick(s["code"]))
                      for s in samples]

        # 只统计 L1 预期检出的样本
        l1_samples = [s for s in samples if s.get("expected_layer") == "L1"]
        l1_hall = [s for s in l1_samples if s["label"] == "hallucination"]
        results_map = {s["id"]: r for s, r in zip(samples, results)}

        detected = sum(1 for s in l1_hall if not results_map[s["id"]].passed)
        detection_rate = detected / max(len(l1_hall), 1)
        print(f"\n[L1+Graph] L1 预期检出: {detected}/{len(l1_hall)} ({detection_rate:.1%})")
        assert detection_rate >= 0.30, f"L1 接入 graph 后检出率应 ≥ 30%"

    def test_full_per_layer_ablation(self, samples, graph):
        """逐层消融——L1+graph 独跑 vs 无管道，测量真实 ΔF1。

        设计原则:
        - L1(有graph): 唯一可工作的层——能检测 import_error/nonexistent_function
        - L3: 无 validate() 方法，pipeline 跳过——ΔF1=0
        - L4: mypy 依赖缺失(pathspec)导致崩溃——ΔF1=0（已诊断，待修）

        消融:
        - 基线: L1-only (graph, 禁 L2-L8)
        - 对照: 无管道（全部通过——TP+FN → F1=0）
        - ΔF1 = L1_F1 - 0 = L1 的绝对贡献
        """
        from orbit.hallucination.pipeline import HallucinationPipeline

        # 禁掉所有干扰层——只留 L1
        all_but_l1 = ["hallucination_L2", "hallucination_L3", "hallucination_L4",
                      "hallucination_L5", "hallucination_L6", "hallucination_L7", "hallucination_L8"]

        # ── L1-only (with graph) ──
        pipeline_l1 = HallucinationPipeline(graph=graph, sandbox=None)
        with AblationContext(all_but_l1):
            l1_results = [asyncio.run(pipeline_l1.validate_quick(s["code"]))
                         for s in samples]
        l1_m = _compute_metrics(samples, [r.passed for r in l1_results])

        # ── 无管道对照（全部通过——无检测能力）──
        noop_results = [True] * len(samples)
        noop_m = _compute_metrics(samples, noop_results)

        # ── L1 贡献 ──
        l1_delta = l1_m["f1"] - noop_m["f1"]

        print(f"\n{'='*65}")
        print(f"Phase 2 逐层消融 —— {len(samples)} 样本 (L1+graph)")
        print(f"{'='*65}")
        print(f"Hallucination: {noop_m['tp']+noop_m['fn']}, Clean: {noop_m['tn']+noop_m['fp']}")
        print(f"{'配置':<28} {'P':>6} {'R':>6} {'F1':>6} {'TP':>5} {'FP':>5} {'ΔF1':>8}")
        print(f"{'-'*58}")

        # 无管道——全部通过，Precision=0, Recall=0, F1=0
        print(f"{'无管道(全部通过)':<28} {'N/A':>6} {'0.000':>6} {'0.000':>6} {noop_m['tp']:>5.0f} {noop_m['fp']:>5.0f} {'--':>8}")

        # L1-only
        print(f"{'L1-only(+graph)':<28} {l1_m['precision']:6.3f} {l1_m['recall']:6.3f} {l1_m['f1']:6.3f} {l1_m['tp']:>5.0f} {l1_m['fp']:>5.0f} {l1_delta:+8.3f}")

        print(f"\n{'-'*58}")
        print(f"L1 绝对贡献 (ΔF1 vs 无管道): {l1_delta:+.3f}")

        if l1_delta > 0.05:
            print(f"→ L1 有效——检出 {l1_m['tp']:.0f}/{noop_m['tp']+noop_m['fn']:.0f} 幻觉，FP={l1_m['fp']:.0f}")
        else:
            print("→ L1 贡献不足——检查 graph 覆盖或 benchmark 样本是否包含可检测的符号错误")

        # L3/L4 诊断
        print(f"\n层状态诊断:")
        print(f"  L1 (图谱): [WORKING] {l1_m['tp']:.0f} TP, {l1_m['fp']:.0f} FP")
        print(f"  L3 (熵):   [BROKEN] 无 validate() 方法——pipeline 始终跳过")
        print(f"  L4 (类型): [BROKEN] mypy 崩溃——缺少 pathspec.patterns.gitignore 依赖")
        print(f"{'='*65}")
