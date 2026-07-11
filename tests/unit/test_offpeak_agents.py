import pytest
from datetime import datetime, UTC
class TestOffpeak:
    def test_cap(self):
        from orbit.scheduler.offpeak_scheduler import estimate_window_capacity
        now=datetime.now(UTC); later=datetime(now.year,now.month,now.day,23,59,59,tzinfo=UTC)
        assert estimate_window_capacity(now,later,[])==0
class TestClarifier:
    def test_c(self):
        from orbit.agents.clarifier.constants import MAX_CLARIFY_QUESTIONS
        assert MAX_CLARIFY_QUESTIONS>0
class TestL10:
    def test_v(self):
        from orbit.hallucination.l10_separation import L10SeparationValidator
        assert L10SeparationValidator() is not None
