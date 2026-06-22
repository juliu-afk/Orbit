"""Step 0.1 章程测试（PRD+ADR 原子化用例）。

验证 docs/charter.md 的 frontmatter 可被解析，度量指标存在。
"""

from __future__ import annotations

import pathlib

import pytest

CHARTER = pathlib.Path(__file__).resolve().parents[2] / "docs" / "charter.md"


def _read_frontmatter() -> dict:
    """解析 charter.md 的 YAML frontmatter。"""
    pytest.importorskip("yaml")
    import yaml

    content = CHARTER.read_text(encoding="utf-8")
    parts = content.split("---", 2)
    assert len(parts) >= 3, "charter.md 缺少 frontmatter"
    return yaml.safe_load(parts[1])


def test_charter_exists():
    assert CHARTER.exists(), f"章程文件不存在：{CHARTER}"


def test_charter_metrics_exist():
    data = _read_frontmatter()
    assert "metrics" in data, "缺少 metrics 段"
    metrics = data["metrics"]
    # 调度延迟硬约束（Token 指标暂缓，不在此断言）
    assert metrics["max_schedule_latency_ms"] <= 1500
    assert metrics["hallucination_rate_threshold"] <= 0.05
    assert metrics["ci_coverage_gate"] >= 0.80


def test_charter_scope_out_time_series():
    """时序图谱必须明确在 scope_out（Step 0.1 技术约束）。"""
    data = _read_frontmatter()
    assert "time_series_graph" in data["scope_out"]


def test_charter_risks_count():
    """风险登记册至少 5 条（Step 0.1 需求描述④）。"""
    data = _read_frontmatter()
    assert len(data["risks"]) >= 5
