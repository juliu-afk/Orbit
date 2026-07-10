"""offpeak/scheduler.py extended tests — DEFAULT_PEAK_CONFIGS.
Coverage sprint 3-2: 39% → >=50%.
"""
from __future__ import annotations

from orbit.scheduler.offpeak.scheduler import DEFAULT_PEAK_CONFIGS


# ── DEFAULT_PEAK_CONFIGS ──────────────────────────────────


class TestDefaultPeakConfigs:
    """Test DEFAULT_PEAK_CONFIGS constant."""

    def test_has_deepseek(self):
        assert "deepseek" in DEFAULT_PEAK_CONFIGS
        ds = DEFAULT_PEAK_CONFIGS["deepseek"]
        assert "peak_windows" in ds
        assert "offpeak_windows" in ds
        assert len(ds["peak_windows"]) > 0

    def test_has_anthropic(self):
        assert "anthropic" in DEFAULT_PEAK_CONFIGS
        ant = DEFAULT_PEAK_CONFIGS["anthropic"]
        assert ant["timezone"] == "America/Los_Angeles"
        assert ant["offpeak_price_multiplier"] < 1.0  # discount

    def test_deepseek_offpeak_discount(self):
        """Off-peak price multiplier < peak (cost saving)."""
        ds = DEFAULT_PEAK_CONFIGS["deepseek"]
        assert ds["offpeak_price_multiplier"] < ds["peak_price_multiplier"]

    def test_peak_windows_structure(self):
        """Each config has well-formed windows."""
        for provider, cfg in DEFAULT_PEAK_CONFIGS.items():
            for w in cfg["peak_windows"]:
                assert "days" in w
                assert "hours" in w
                assert isinstance(w["days"], list)
