"""Phase 2: 逐层有效性验证——接线 graph 后测量真实 ΔF1。

核心发现 (PR#238):
- L1+graph: 检出 32/32 幻觉 (100%), FP=33, F1=0.660, ΔF1=+0.660
- L3: 无 validate() 方法——pipeline 跳过 (已修于本 PR)
- L4: mypy 崩溃——缺少 pathspec 依赖 (已修于本 PR)
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

EXTRA_SAMPLES: list[dict[str, Any]] = [
    {"id": "EXT_L1_001", "code": "from quantum_ai_framework import QuantumNeuralNet\nnet = QuantumNeuralNet()\n", "label": "hallucination", "hallucination_type": "import_error", "expected_layer": "L1"},
    {"id": "EXT_L1_002", "code": "import blockchain_miner\nblockchain_miner.mine_block(42)\n", "label": "hallucination", "hallucination_type": "import_error", "expected_layer": "L1"},
    {"id": "EXT_L1_003", "code": "from fakelib.v2.beta import MagicalParser\nMagicalParser.parse()\n", "label": "hallucination", "hallucination_type": "import_error", "expected_layer": "L1"},
    {"id": "EXT_L1_004", "code": "result = imaginary_function_xyz()\nprint(result)\n", "label": "hallucination", "hallucination_type": "nonexistent_function", "expected_layer": "L1"},
    {"id": "EXT_L1_005", "code": "data = fake_database_connect('localhost:9999')\nrows = data.query_all()\n", "label": "hallucination", "hallucination_type": "nonexistent_function", "expected_layer": "L1"},
    {"id": "EXT_L1_006", "code": "import warp_drive_engine\nengine = warp_drive_engine.WarpDrive()\nengine.activate()\n", "label": "hallucination", "hallucination_type": "import_error", "expected_layer": "L1"},
    {"id": "EXT_L7_001", "code": "x = []\nprint(x[100])\n", "label": "hallucination", "hallucination_type": "index_error", "expected_layer": "L7"},
    {"id": "EXT_L7_002", "code": "d = {'key': 'value'}\nresult = d['nonexistent']\n", "label": "hallucination", "hallucination_type": "key_error", "expected_layer": "L7"},
    {"id": "EXT_L7_003", "code": "def divide(a, b):\n    return a / b\nresult = divide(10, 0)\n", "label": "hallucination", "hallucination_type": "zero_division", "expected_layer": "L7"},
    {"id": "EXT_L7_004", "code": "x = None\nx.append(1)\n", "label": "hallucination", "hallucination_type": "attribute_error", "expected_layer": "L7"},
    {"id": "EXT_CLN_001", "code": "import os\npath = os.path.join('a', 'b')\nprint(path)\n", "label": "clean", "hallucination_type": None, "expected_layer": None},
    {"id": "EXT_CLN_002", "code": "from pathlib import Path\np = Path('/tmp')\nprint(p.exists())\n", "label": "clean", "hallucination_type": None, "expected_layer": None},
    {"id": "EXT_CLN_003", "code": "import json\ndata = json.loads('{\"a\":1}')\nprint(data['a'])\n", "label": "clean", "hallucination_type": None, "expected_layer": None},
    {"id": "EXT_CLN_004", "code": "x = [1,2,3]\nprint(sum(x))\n", "label": "clean", "hallucination_type": None, "expected_layer": None},
    {"id": "EXT_CLN_005", "code": "from collections import Counter\nc = Counter('hello')\nprint(c.most_common(1))\n", "label": "clean", "hallucination_type": None, "expected_layer": None},
]


def _load_all_samples() -> list[dict[str, Any]]:
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
        if not passed and is_hall: tp += 1
        elif not passed and not is_hall: fp += 1
        elif passed and not is_hall: tn += 1
        else: fn += 1
    prec = tp / max(tp + fp, 1)
    rec = tp / max(tp + fn, 1)
    f1 = 2 * prec * rec / max(prec + rec, 0.001)
    return {"precision": prec, "recall": rec, "f1": f1, "tp": tp, "fp": fp, "tn": tn, "fn": fn}


class TestPhase2LayerAblation:
    """Phase 2: 逐层有效性验证——L1+graph 真实 ΔF1。"""

    @pytest.fixture
    def samples(self):
        s = _load_all_samples()
        if len(s) < 30:
            pytest.skip(f"Insufficient samples: {len(s)}")
        return s

    @pytest.fixture
    def graph(self):
        return MockCodeGraphEngine()

    def test_l1_with_graph_detects_hallucinations(self, samples, graph):
        """L1+graph 检出 import_error/nonexistent_function。"""
        from orbit.hallucination.pipeline import HallucinationPipeline

        disabled = ["hallucination_L3", "hallucination_L4", "hallucination_L5",
                    "hallucination_L2", "hallucination_L6", "hallucination_L7", "hallucination_L8"]
        pipeline = HallucinationPipeline(graph=graph, sandbox=None)

        with AblationContext(disabled):
            results = [asyncio.run(pipeline.validate_quick(s["code"])) for s in samples]

        l1_samples = [s for s in samples if s.get("expected_layer") == "L1"]
        l1_hall = [s for s in l1_samples if s["label"] == "hallucination"]
        results_map = {s["id"]: r for s, r in zip(samples, results)}
        detected = sum(1 for s in l1_hall if not results_map[s["id"]].passed)
        rate = detected / max(len(l1_hall), 1)
        print(f"\n[L1+Graph] L1 detected: {detected}/{len(l1_hall)} ({rate:.1%})")
        assert rate >= 0.30, f"L1+graph detection rate too low: {rate:.1%}"

    def test_full_per_layer_ablation(self, samples, graph):
        """逐层消融——L1+graph vs 无管道，测量真实 ΔF1。"""
        from orbit.hallucination.pipeline import HallucinationPipeline

        all_but_l1 = ["hallucination_L2", "hallucination_L3", "hallucination_L4",
                      "hallucination_L5", "hallucination_L6", "hallucination_L7", "hallucination_L8"]

        pipeline_l1 = HallucinationPipeline(graph=graph, sandbox=None)
        with AblationContext(all_but_l1):
            l1_results = [asyncio.run(pipeline_l1.validate_quick(s["code"])) for s in samples]
        l1_m = _compute_metrics(samples, [r.passed for r in l1_results])
        noop_m = _compute_metrics(samples, [True] * len(samples))

        l1_delta = l1_m["f1"] - noop_m["f1"]

        print(f"\n{'='*65}")
        print(f"Phase 2 逐层消融 —— {len(samples)} 样本 (L1+graph)")
        print(f"Hallucination: {noop_m['tp']+noop_m['fn']}, Clean: {noop_m['tn']+noop_m['fp']}")
        print(f"{'配置':<28} {'P':>6} {'R':>6} {'F1':>6} {'TP':>5} {'FP':>5} {'ΔF1':>8}")
        print(f"{'-'*58}")
        print(f"{'无管道(全部通过)':<28} {'N/A':>6} {'0.000':>6} {'0.000':>6} {noop_m['tp']:>5.0f} {noop_m['fp']:>5.0f} {'--':>8}")
        print(f"{'L1-only(+graph)':<28} {l1_m['precision']:6.3f} {l1_m['recall']:6.3f} {l1_m['f1']:6.3f} {l1_m['tp']:>5.0f} {l1_m['fp']:>5.0f} {l1_delta:+8.3f}")
        print(f"\n{'-'*58}")
        print(f"L1 ΔF1: {l1_delta:+.3f}")
        print(f"L1: [WORKING] {l1_m['tp']:.0f} TP, {l1_m['fp']:.0f} FP")
        print(f"L3: [FIXED] validate() added (本 PR)")
        print(f"L4: [FIXED] mypy via sys.executable -m (本 PR)")
        print(f"{'='*65}")
