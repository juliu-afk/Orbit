"""测验生成器 (P1)——Fable 5 方法论落地。

WHY: Thariq "Quiz Yourself" 模式——代码写完，AI 出题测你理解程度。
全对方可标记任务完成。这是 merge 前最后一道防线。

设计:
  - LLM 生成 5 道判断题（正选/反选/归因各 1-2 道）
  - Jinja2 渲染 HTML 测验报告
  - 仅核心模块改动触发
  - LLM 失败时降级为静态模板（不阻塞任务完成）

用法:
    from orbit.modes.quiz_generator import QuizGenerator, QuizQuestion, QuizResult

    gen = QuizGenerator(llm=llm_client)
    questions = await gen.generate(diff_text=diff, impl_notes=notes, task_id="task_1")
    html = gen.render_html(questions, task_id="task_1")
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from orbit.gateway.client import LLMClient

import structlog

logger = structlog.get_logger("orbit.modes.quiz")

# 核心模块列表——仅这些模块改动时触发测验
CORE_MODULES = [
    "scheduler/", "graph/", "hallucination/", "checkpoint/",
    "agents/", "gateway/", "compliance/", "evolution/",
    "metacognition/", "sandbox/", "memory/", "compose/",
    "communication/", "knowledge/", "context/",
]

# 测验生成 Prompt
QUIZ_GENERATION_PROMPT = """You are reviewing a code change. Generate 5 True/False quiz questions to test whether someone truly understands what was changed and WHY.

## Change Diff
{diff_text}

## Implementation Notes
{impl_notes}

## Rules
1. Each question must test UNDERSTANDING, not memorization. The answer should NOT be findable by just reading the diff.
2. Mix question types:
   - 正选 (True statements): Correct things the change does
   - 反选 (False statements): Common misunderstandings about what the change does
   - 归因 (Attribution): "The purpose of X change is Y"
3. Every question must include an explanation that cites specific code paths.
4. Questions must cover at least 3 different files from the change.
5. Output JSON array of 5 objects:

```json
[
  {{
    "id": 1,
    "statement": "The new deviation_log field causes an extra PG query during checkpoint save",
    "answer": false,
    "explanation": "deviation_log is a JSON field serialized within the same orjson.dumps() call in CheckpointManager.save(). No additional query is made.",
    "source_files": ["checkpoint/manager.py"],
    "category": "反选"
  }}
]
```

Output ONLY the JSON array, no other text."""


class QuizQuestion(BaseModel):
    """单道测验题。"""
    id: int = Field(..., ge=1, le=5)
    statement: str = Field(..., min_length=1, description="判断陈述")
    answer: bool = Field(..., description="True=正确, False=错误")
    explanation: str = Field(..., min_length=1, description="为什么对/错")
    source_files: list[str] = Field(default_factory=list)
    category: str = Field(default="归因", description="正选|反选|归因")


class QuizResult(BaseModel):
    """测验结果——含答题历史。"""
    task_id: str
    questions: list[QuizQuestion] = Field(default_factory=list)
    user_answers: list[bool] = Field(default_factory=list)
    score: int = 0
    total: int = 5
    passed: bool = False
    attempt: int = 1
    generated_at: str = Field(
        default_factory=lambda: datetime.now(UTC).isoformat()
    )
    error: str = ""


class QuizGenerator:
    """测验生成器。

    WHY 独立类: 与 ModeLoader 解耦——QuizGenerator 是运行时组件，
    ModeLoader 是配置加载器。测验模式只用 mode.yaml 做行为配置，
    实际生成逻辑在这里。
    """

    _template_path: Path | None = None

    def __init__(self, llm: LLMClient | None = None) -> None:
        """初始化生成器。

        Args:
            llm: LLM 客户端（None 时只能生成静态模板，不阻塞任务）
        """
        self._llm = llm
        # 模板路径——指向 modes/quiz/references/template.html.j2
        self._template_path = (
            Path(__file__).resolve().parent / "quiz" / "references" / "template.html.j2"
        )

    @classmethod
    def should_trigger(cls, changed_files: list[str], quiz_enabled: bool | None = None) -> bool:
        """判断是否应触发测验。

        WHY 类方法: 不依赖实例状态，可在 verifier 中直接调用。

        Args:
            changed_files: 改动的文件路径列表
            quiz_enabled: 用户配置——True 强制开启，False 强制关闭，None 自动判断

        Returns:
            True 如果应触发测验
        """
        if quiz_enabled is False:
            return False
        if quiz_enabled is True:
            return True
        # 自动判断——任一改动文件在核心模块下
        return any(
            any(f.startswith(mod) or f"/{mod}" in f for mod in CORE_MODULES)
            for f in changed_files
        )

    async def generate(
        self, diff_text: str, impl_notes: str = "", task_id: str = "",
    ) -> list[QuizQuestion]:
        """LLM 生成 5 道判断题。

        WHY 异步: LLM 调用可能耗时 2-5s。

        Args:
            diff_text: git diff 文本
            impl_notes: 实现笔记（DeviationLogger.render_markdown() 的输出）
            task_id: 任务 ID

        Returns:
            5 道 QuizQuestion 列表。LLM 失败时返回空列表（降级）。
        """
        if self._llm is None or not diff_text.strip():
            return []

        prompt = QUIZ_GENERATION_PROMPT.format(
            diff_text=diff_text[:8000],   # 限制长度——防止 token 爆炸
            impl_notes=impl_notes[:4000] or "无实现笔记",
        )

        try:
            from orbit.gateway.schemas import LLMRequest

            req = LLMRequest(
                prompt=prompt,
                system_prompt="Output JSON array only. No other text.",
                task_type="structured_output",
            )
            result = await self._llm.generate(req, task_id=f"quiz_gen_{task_id}")
            raw = result.content.strip()

            # 解析 JSON——处理可能的 markdown 包裹
            if raw.startswith("```"):
                raw = raw.split("```json")[1].split("```")[0] if "```json" in raw else raw.split("```")[1].split("```")[0]

            data = json.loads(raw)
            if not isinstance(data, list):
                return []

            questions = [QuizQuestion(**q) for q in data[:5]]
            logger.info(
                "quiz_generated",
                task_id=task_id,
                question_count=len(questions),
                categories=[q.category for q in questions],
            )
            return questions

        except Exception:
            logger.error("quiz_generation_failed", task_id=task_id, exc_info=True)
            return []

    def render_html(
        self, questions: list[QuizQuestion], task_id: str = "",
        attempt: int = 1,
    ) -> str:
        """渲染 HTML 测验报告。

        WHY Jinja2: 与 grill-me 模式一致——模式文件用模板生成，
        与 Python 代码解耦。但为减少依赖，内置简单模板。

        Args:
            questions: 测验题列表
            task_id: 任务 ID
            attempt: 当前尝试次数

        Returns:
            HTML 字符串
        """
        if not questions:
            return self.render_fallback(task_id)

        # 用 Jinja2 渲染（如果可用）
        if self._template_path and self._template_path.exists():
            try:
                import jinja2

                env = jinja2.Environment(
                    loader=jinja2.FileSystemLoader(str(self._template_path.parent)),
                    autoescape=True,
                )
                template = env.get_template("template.html.j2")
                return template.render(
                    task_id=task_id,
                    generated_at=datetime.now(UTC).isoformat(),
                    file_count=len(set(f for q in questions for f in q.source_files)),
                    questions=[q.model_dump() for q in questions],
                    correct_answers={q.id: q.answer for q in questions},
                )
            except Exception:
                logger.warning("quiz_jinja2_render_failed", task_id=task_id)

        # 降级——直接拼 HTML
        return self._render_inline(questions, task_id, attempt)

    @staticmethod
    def _render_inline(
        questions: list[QuizQuestion], task_id: str, attempt: int,
    ) -> str:
        """内置 HTML 渲染——不依赖 Jinja2。

        WHY 降级路径: 避免 Jinja2 可用性影响测验功能。
        """
        q_html = ""
        for q in questions:
            q_html += f"""
            <div style="background:#161b22;border:1px solid #30363d;border-radius:8px;padding:1rem;margin:0.8rem 0">
              <h4>第 {q.id} 题 — {q.category}</h4>
              <p>{q.statement}</p>
              <p style="color:#8b949e;font-size:0.8rem">涉及: {', '.join(q.source_files)}</p>
            </div>"""

        return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="UTF-8"><title>测验 — {task_id}</title></head>
<body style="background:#0d1117;color:#c9d1d9;font-family:sans-serif;max-width:800px;margin:0 auto;padding:2rem">
<h1>📝 改动理解测验</h1>
<p>任务: {task_id} | 尝试: {attempt}/3 | 规则: 全对方可标记完成</p>
{q_html}
<p style="color:#8b949e;margin-top:2rem">提示: 请联系 Claude Code 调用 /quiz 进行交互式测验。</p>
</body></html>"""

    def render_fallback(self, task_id: str = "") -> str:
        """LLM 生成失败时的降级 HTML——不阻塞任务完成。

        WHY: 默认放行比阻塞更安全。用户可手动审查 diff 替代测验。
        """
        return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="UTF-8"><title>测验降级 — {task_id}</title></head>
<body style="background:#0d1117;color:#c9d1d9;font-family:sans-serif;max-width:800px;margin:0 auto;padding:2rem">
<h1>⚠️ 测验生成失败</h1>
<p>LLM 未能生成测验题。请改为手动审查以下内容：</p>
<ol>
  <li>检查 git diff 中每处改动的目的</li>
  <li>确认改动未引入副作用</li>
  <li>运行相关测试确保通过</li>
</ol>
<p style="color:#8b949e">此降级页面不阻塞任务完成。手动审查后可直接标记完成。</p>
</body></html>"""
