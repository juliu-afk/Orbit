#!/usr/bin/env python3
"""OrbitBench 自动运行器——扫描模板目录，加载任务描述，跑 pipeline 验证。

Phase 3 效能闭环的最后一块拼图——让 OrbitBench 从"模板文件"变成"可自动执行的基准"。

用法:
    python scripts/run_orbitbench.py                    # 跑全部模板
    python scripts/run_orbitbench.py --level L0         # 仅 L0
    python scripts/run_orbitbench.py --list             # 列出模板

输出:
    每个模板的 passed/failed + 汇总通过率
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
BENCHMARK_DIR = PROJECT_ROOT / "data" / "benchmarks" / "orbitbench"

# 难度级别 → 目标通过率
LEVEL_TARGETS = {
    "L0_syntax_fix": 1.00,
    "L1_single_file": 0.90,
    "L2_multi_file": 0.80,
    "L3_cross_module": 0.60,
    "L4_new_feature": 0.50,
    "L5_system_level": 0.30,
}


def find_tasks(level: str | None = None) -> list[Path]:
    """扫描模板目录，返回所有 task_*.md 文件路径。"""
    levels = [level] if level else sorted(d.name for d in BENCHMARK_DIR.iterdir()
                                          if d.is_dir() and not d.name.startswith("."))
    tasks: list[Path] = []
    for lvl in levels:
        lvl_dir = BENCHMARK_DIR / lvl
        if lvl_dir.is_dir():
            tasks.extend(sorted(lvl_dir.glob("task_*.md")))
    return tasks


def load_task(task_path: Path) -> dict:
    """加载任务模板，提取描述和预期输出。"""
    content = task_path.read_text(encoding="utf-8")
    # 提取 ## Task 段落
    task_section = ""
    expected_section = ""
    in_task = in_expected = False
    for line in content.splitlines():
        if line.startswith("## Task"):
            in_task, in_expected = True, False
            continue
        elif line.startswith("## Expected"):
            in_task, in_expected = False, True
            continue
        elif line.startswith("## ") or line.startswith("# "):
            in_task = in_expected = False
        if in_task:
            task_section += line + "\n"
        elif in_expected:
            expected_section += line + "\n"

    return {
        "id": task_path.stem,
        "level": task_path.parent.name,
        "description": task_section.strip(),
        "expected": expected_section.strip(),
    }


async def validate_task(task: dict) -> dict:
    """用 hallucination pipeline 验证任务预期代码是否正确。"""
    from orbit.hallucination.pipeline import HallucinationPipeline
    from tests.lib.mocks.code_graph import MockCodeGraphEngine

    pipeline = HallucinationPipeline(graph=MockCodeGraphEngine(), sandbox=None)
    expected_code = task["expected"]

    if not expected_code:
        return {"id": task["id"], "level": task["level"], "passed": None,
                "reason": "no expected code in template"}

    # 提取代码块
    code = ""
    in_code = False
    for line in expected_code.splitlines():
        if line.strip().startswith("```"):
            if in_code:
                break
            in_code = True
            continue
        if in_code:
            code += line + "\n"

    if not code.strip():
        code = expected_code  # 无代码块标记，直接用全部内容

    result = await pipeline.validate_quick(code)
    return {
        "id": task["id"],
        "level": task["level"],
        "passed": result.passed,
        "errors": result.errors[:3] if not result.passed else [],
    }


def main():
    parser = argparse.ArgumentParser(description="OrbitBench 自动运行器")
    parser.add_argument("--level", help="仅跑指定级别 (L0_syntax_fix, L1_single_file, ...)")
    parser.add_argument("--list", action="store_true", help="列出所有模板")
    args = parser.parse_args()

    tasks_paths = find_tasks(args.level)
    if not tasks_paths:
        print("No tasks found.")
        sys.exit(0)

    tasks = [load_task(p) for p in tasks_paths]

    if args.list:
        for t in tasks:
            print(f"  [{t['level']}] {t['id']}: {t['description'][:80]}")
        return

    async def run_all():
        results = []
        for t in tasks:
            r = await validate_task(t)
            results.append(r)
            status = "PASS" if r["passed"] else ("SKIP" if r["passed"] is None else "FAIL")
            err = f" — {r['errors'][0][:60]}" if r["errors"] else ""
            print(f"  [{status}] {t['level']}/{t['id']}{err}")
        return results

    results = asyncio.run(run_all())
    passed = sum(1 for r in results if r["passed"])
    skipped = sum(1 for r in results if r["passed"] is None)
    failed = len(results) - passed - skipped
    total = len(results)

    print(f"\n{'='*50}")
    print(f"OrbitBench: {total} tasks, {passed} passed, {failed} failed, {skipped} skipped")
    if total > 0:
        print(f"Pass rate: {passed/max(total,1):.0%}")

    # 按级别汇总
    by_level: dict[str, list] = {}
    for r in results:
        by_level.setdefault(r["level"], []).append(r)
    for lvl, items in sorted(by_level.items()):
        lvl_passed = sum(1 for r in items if r["passed"])
        target = LEVEL_TARGETS.get(lvl, 0.5)
        status = "OK" if lvl_passed / max(len(items), 1) >= target else "BELOW"
        print(f"  {lvl}: {lvl_passed}/{len(items)} (target {target:.0%}) [{status}]")


if __name__ == "__main__":
    main()
