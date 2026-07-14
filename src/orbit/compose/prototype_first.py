"""Prototype-first strategy (P2) — Fable 5 methodology.

WHY: Thariq "Brainstorm & Prototype" pattern — generate standalone HTML
with fake data BEFORE touching real code. Changing a button position costs
zero at prototype stage; after code is written, it's demolition.

Design:
  - PrototypeFirstGuide: generates HTML prototype → collects feedback → extracts design decisions
  - PrototypeResult: structured output (HTML + feedback + design decisions)
  - Sandbox-isolated: prototype runs in isolated HTML file, never touches real codebase
  - Design extraction: user feedback is parsed into structured constraints for the implement phase

Usage:
    from orbit.compose.prototype_first import PrototypeFirstGuide, Strategy

    guide = PrototypeFirstGuide(llm=client)
    result = await guide.run(task_description="dashboard with 4 charts")
    # result.html → standalone page to show user
    # result.feedback → after user review
    # result.design_decisions → inject into implementation context
"""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from orbit.gateway.client import LLMClient

import structlog

logger = structlog.get_logger("orbit.compose.prototype_first")


class Strategy(StrEnum):
    """Compose execution strategy.

    STANDARD: direct implementation (default)
    PROTOTYPE_FIRST: HTML prototype → feedback → implement
    """

    STANDARD = "standard"
    PROTOTYPE_FIRST = "prototype_first"


class PrototypeResult(BaseModel):
    """Result of a prototype-first iteration.

    html: standalone HTML page with fake data (ready to open in browser)
    feedback: user feedback text (filled after showing prototype)
    design_decisions: extracted constraints for implementation phase
    iteration: which round of feedback (starts at 0)
    """

    task_description: str = ""
    html: str = ""
    feedback: str = ""
    design_decisions: list[str] = Field(default_factory=list)
    iteration: int = 0


# Prompt for generating HTML prototype with fake data
PROTOTYPE_PROMPT = """You are a UI/UX designer. Create a STANDALONE HTML page for the following feature.

## Task
{task_description}

## Rules
1. Use ONLY HTML + inline CSS + minimal vanilla JS. No frameworks, no build tools.
2. Use FAKE/realistic data — do NOT reference any real API, database, or backend.
3. Dark theme (background #0d1117, text #c9d1d9, accent #58a6ff).
4. The page should look like a real app screen, not a wireframe.
5. Include ALL UI states: loading skeleton, empty state, error state, populated state.
6. Make it interactive — buttons, dropdowns, forms should work with fake data.
7. Max 500 lines of HTML.

Output ONLY the HTML, no explanation."""

# Prompt for extracting design decisions from user feedback
DESIGN_EXTRACT_PROMPT = """Extract structured design decisions from user feedback on a prototype.

## Original Task
{task_description}

## Prototype Feedback
{feedback}

## Rules
1. Each decision must be actionable: "Use X pattern for Y component"
2. Extract 3-7 decisions covering layout, interaction, data display
3. Ignore color/font nits — focus on structure and behavior
4. Format: one decision per line, imperative mood

Output a JSON array of strings: ["decision 1", "decision 2", ...]"""


class PrototypeFirstGuide:
    """Prototype-first strategy guide.

    WHY standalone: prototype_first is a strategy, not a mode.
    It wraps the compose flow — generate prototype → collect feedback →
    extract decisions → feed into implementation. The orchestrator calls
    this when Spec.strategy == PROTOTYPE_FIRST.
    """

    def __init__(self, llm: LLMClient | None = None) -> None:
        self._llm = llm
        self._history: list[PrototypeResult] = []

    @property
    def iterations(self) -> int:
        return len(self._history)

    async def generate_prototype(self, task_description: str) -> PrototypeResult:
        """Generate standalone HTML prototype with fake data.

        Calls LLM to create the HTML. Falls back to static template if no LLM.
        """
        result = PrototypeResult(task_description=task_description, iteration=0)

        if self._llm is None:
            result.html = self._static_prototype(task_description)
            logger.info("prototype_static_fallback", task=task_description[:60])
            return result

        try:
            from orbit.gateway.schemas import LLMRequest

            req = LLMRequest(
                prompt=PROTOTYPE_PROMPT.format(task_description=task_description),
                system_prompt="Output HTML only. No markdown fences.",
                task_type="code_generation",
            )
            resp = await self._llm.generate(req, task_id="prototype_gen")
            html = resp.content.strip()
            if html.startswith("```"):
                html = html.split("```html")[1].split("```")[0] if "```html" in html else html.split("```")[1].split("```")[0]
            result.html = html
        except Exception:
            logger.error("prototype_llm_failed", exc_info=True)
            result.html = self._static_prototype(task_description)

        self._history.append(result)
        return result

    async def collect_feedback(self, result: PrototypeResult, feedback: str) -> PrototypeResult:
        """Process user feedback and extract design decisions.

        Returns the same result with feedback and design_decisions filled.
        """
        result.feedback = feedback

        # Extract structured design decisions from feedback
        if self._llm is not None and feedback.strip():
            try:
                import json
                from orbit.gateway.schemas import LLMRequest

                req = LLMRequest(
                    prompt=DESIGN_EXTRACT_PROMPT.format(
                        task_description=result.task_description,
                        feedback=feedback,
                    ),
                    system_prompt="Output JSON array only.",
                    task_type="structured_output",
                )
                resp = await self._llm.generate(req, task_id="prototype_extract")
                decisions = json.loads(resp.content.strip())
                if isinstance(decisions, list):
                    result.design_decisions = [str(d) for d in decisions]
            except Exception:
                logger.warning("design_extract_failed", exc_info=True)
                result.design_decisions = [feedback.strip()] if feedback.strip() else []

        logger.info(
            "prototype_feedback_collected",
            task=result.task_description[:60],
            decisions=len(result.design_decisions),
        )
        return result

    def iterate(self, feedback: str) -> PrototypeResult:
        """Start a new prototype iteration based on feedback.

        Shortcut for generate + collect_feedback in one call.
        Returns the NEW prototype result (iteration = previous + 1).
        """
        if not self._history:
            raise ValueError("No prototype generated yet — call generate_prototype first")

        prev = self._history[-1]
        result = PrototypeResult(
            task_description=prev.task_description,
            feedback=feedback,
            iteration=len(self._history),
        )
        self._history.append(result)
        return result

    def get_design_context(self) -> str:
        """Get all accumulated design decisions as a context block.

        Can be injected into the implementation phase's agent prompt.
        """
        all_decisions: list[str] = []
        for r in self._history:
            if r.design_decisions:
                all_decisions.extend(r.design_decisions)

        if not all_decisions:
            return ""

        lines = [
            "## Prototype Design Decisions (Prototype-First Strategy)",
            "",
            "These constraints were extracted from prototype feedback rounds:",
            "",
        ]
        for i, d in enumerate(all_decisions, 1):
            lines.append(f"{i}. {d}")
        return "\n".join(lines)

    @staticmethod
    def _static_prototype(task_description: str) -> str:
        """Static HTML fallback when no LLM available.

        WHY: Don't block the workflow — show a placeholder that the user can
        describe desired changes against.
        """
        return f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Prototype — {task_description[:40]}</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:-apple-system,sans-serif;background:#0d1117;color:#c9d1d9;padding:2rem}}
.card{{background:#161b22;border:1px solid #30363d;border-radius:8px;padding:1.5rem;margin:1rem 0}}
button{{background:#58a6ff;color:#000;border:none;padding:.5rem 1rem;border-radius:6px;cursor:pointer}}
.placeholder{{border:2px dashed #30363d;border-radius:8px;padding:3rem;text-align:center;color:#8b949e}}
</style></head>
<body>
<h1>Prototype</h1>
<p style="color:#8b949e;margin-bottom:2rem">{task_description}</p>
<div class="card"><h3>Getting Started</h3><p>This is a static placeholder. Describe what you want to see, and I'll generate the real prototype.</p></div>
<div class="placeholder"><p>Your content here — describe your desired layout</p><br><button onclick="alert('Add your interaction here')">Click Me</button></div>
</body></html>"""
