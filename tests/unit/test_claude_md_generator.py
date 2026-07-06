"""ClaudeMdGenerator unit tests."""
from __future__ import annotations

import pytest


class TestClaudeMdGenerator:
    def test_init(self):
        from unittest.mock import MagicMock
        from orbit.knowledge.claude_md_generator import ClaudeMdGenerator
        g = ClaudeMdGenerator(MagicMock())
        assert g is not None

    def test_sections(self):
        from orbit.knowledge.claude_md_generator import ClaudeMdGenerator
        assert len(ClaudeMdGenerator.SECTIONS) >= 6

    @pytest.mark.asyncio
    async def test_generate_with_mock(self):
        from unittest.mock import MagicMock
        from orbit.knowledge.claude_md_generator import ClaudeMdGenerator
        mock = MagicMock()
        mock.config = MagicMock()
        mock.code = MagicMock()
        mock.knowledge = MagicMock()
        g = ClaudeMdGenerator(mock)
        content = await g.generate()
        assert isinstance(content, str)
        assert len(content) > 0

    @pytest.mark.asyncio
    async def test_extract_overview(self):
        from unittest.mock import MagicMock
        from orbit.knowledge.claude_md_generator import ClaudeMdGenerator
        g = ClaudeMdGenerator(MagicMock())
        result = await g._extract_overview()
        assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_extract_tech_stack(self):
        from unittest.mock import MagicMock
        from orbit.knowledge.claude_md_generator import ClaudeMdGenerator
        g = ClaudeMdGenerator(MagicMock())
        result = await g._extract_tech_stack()
        assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_extract_structure(self):
        from unittest.mock import MagicMock
        from orbit.knowledge.claude_md_generator import ClaudeMdGenerator
        g = ClaudeMdGenerator(MagicMock())
        result = await g._extract_structure()
        assert isinstance(result, str)
