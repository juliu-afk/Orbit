#!/usr/bin/env python3
"""幻觉基准数据集生成脚本。

从真实 Orbit 代码提取函数片段，对正确代码注入 11 种幻觉类型，生成标注 JSON。

用法:
    python scripts/generate_benchmark.py --output data/benchmarks/hallucination_v2.json --samples 200
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from pathlib import Path
from typing import Any

# ── 幻觉注入策略 ─────────────────────────────
# 每种策略: (hallucination_type, expected_layer, injection_fn)

INJECTION_STRATEGIES: list[dict[str, Any]] = [
    {
        "type": "import_error",
        "layer": "L1",
        "description": "替换 import 目标为不存在的模块",
        "apply": lambda code: code.replace("import os", "import nonexistent_os_module_xyz"),
    },
    {
        "type": "nonexistent_attribute",
        "layer": "L1",
        "description": "替换方法调用为不存在的方法",
        "apply": lambda code: code.replace("model_dump()", "model_to_fake_dict()"),
    },
    {
        "type": "type_mismatch",
        "layer": "L4",
        "description": "将 str 赋值给 int 类型变量",
        "apply": lambda code: code.replace(": int =", ": str ="),
    },
    {
        "type": "name_error",
        "layer": "L7",
        "description": "引用未定义变量",
        "apply": lambda code: code + "\nundefined_reference_xyz\n",
    },
    {
        "type": "runtime_error",
        "layer": "L7",
        "description": "添加除零路径",
        "apply": lambda code: code + "\n_zero = 0\ndivision = 1 / _zero\n",
    },
    {
        "type": "config_drift",
        "layer": "L8",
        "description": "引用不存在的环境变量",
        "apply": lambda code: code.replace(
            'os.environ.get("', 'os.environ["MISSING_VAR_XYZ_'
        ).replace('os.getenv("', 'os.environ["MISSING_VAR_XYZ_'),
    },
    {
        "type": "contract_violation",
        "layer": "L6",
        "description": "修改返回类型与声明不符",
        "apply": lambda code: code.replace(
            "-> str:", "-> int:"
        ).replace("-> str:", "-> int:"),
    },
]


def extract_function_bodies(root_dir: Path, max_functions: int = 50) -> list[str]:
    """从 Python 文件中提取函数体片段。"""
    snippets: list[str] = []
    py_files = list(root_dir.rglob("*.py"))
    for pf in py_files[:200]:  # 最多扫描 200 个文件
        try:
            tree = ast.parse(pf.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                # 获取函数源码行
                try:
                    lines = pf.read_text(encoding="utf-8").splitlines()
                    start = node.lineno - 1
                    end = node.end_lineno if node.end_lineno else start + 1
                    body = "\n".join(lines[start:end])
                    if 3 <= len(body.splitlines()) <= 30:
                        snippets.append(body)
                except Exception:
                    continue
            if len(snippets) >= max_functions:
                break
        if len(snippets) >= max_functions:
            break
    return snippets


def generate_samples(
    clean_snippets: list[str],
    num_hallucination: int = 50,
    num_clean: int = 50,
) -> list[dict[str, Any]]:
    """生成标注数据集——正确代码 + 注入幻觉的代码。"""
    samples: list[dict[str, Any]] = []

    # 正确样本
    for i, snippet in enumerate(clean_snippets[:num_clean]):
        samples.append({
            "id": f"CLEAN_{i:04d}",
            "code": snippet,
            "label": "clean",
            "hallucination_type": None,
            "expected_layer": None,
            "source": "extracted_from_orbit",
            "description": f"从 Orbit 代码提取的正确函数 #{i}",
        })

    # 幻觉样本——对正确代码注入幻觉
    import itertools

    strategy_cycle = itertools.cycle(INJECTION_STRATEGIES)
    for i in range(num_hallucination):
        if i >= len(clean_snippets):
            break
        strategy = next(strategy_cycle)
        original = clean_snippets[i % len(clean_snippets)]
        try:
            mutated = strategy["apply"](original)
            if mutated != original:  # 确保注入成功
                samples.append({
                    "id": f"HALL_{i:04d}",
                    "code": mutated,
                    "label": "hallucination",
                    "hallucination_type": strategy["type"],
                    "expected_layer": strategy["layer"],
                    "source": "auto_generated",
                    "description": f"{strategy['description']} (from CLEAN_{i % len(clean_snippets):04d})",
                })
        except Exception:
            continue

    return samples


def main():
    parser = argparse.ArgumentParser(description="生成幻觉基准数据集")
    parser.add_argument("--output", default="data/benchmarks/hallucination_v1.json",
                       help="输出 JSON 路径")
    parser.add_argument("--samples", type=int, default=200,
                       help="总样本数（正确+幻觉各半）")
    parser.add_argument("--source", default="src/orbit",
                       help="提取正确代码的源目录")
    args = parser.parse_args()

    source_dir = Path(args.source)
    if not source_dir.exists():
        print(f"源目录不存在: {source_dir}", file=sys.stderr)
        sys.exit(1)

    half = max(args.samples // 2, 1)
    print(f"从 {source_dir} 提取函数片段...")
    snippets = extract_function_bodies(source_dir, max_functions=half * 2)

    if not snippets:
        print("未提取到函数片段——使用内建示例", file=sys.stderr)
        snippets = [
            "def hello():\n    return 'world'\n",
            "def add(a: int, b: int) -> int:\n    return a + b\n",
        ] * half

    print(f"提取了 {len(snippets)} 个函数片段")
    print(f"生成 {half} 正确样本 + {half} 幻觉样本...")
    samples = generate_samples(snippets, num_hallucination=half, num_clean=half)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "version": "1.0",
        "created": "2026-07-08",
        "description": "自动生成的防幻觉管道基准数据集",
        "total_samples": len(samples),
        "samples": samples,
    }
    output_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"已写入 {len(samples)} 条样本到 {output_path}")


if __name__ == "__main__":
    main()
