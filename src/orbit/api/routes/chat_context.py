"""Chat 端点——后台 CONTEXT.md 自动刷新。

从 chat.py 拆分。
"""

from __future__ import annotations

import time

import structlog as _sl

logger = _sl.get_logger("orbit.chat.context_sync")

_CONTEXT_SYNC_INTERVAL = 300  # 5 分钟节流
_last_context_sync: dict[str, float] = {}

def _schedule_context_sync(project_name: str, registry=None) -> None:
    """如果项目已注册且超时，后台异步刷新 CONTEXT.md。

    节流 5 分钟——防止每次输入都触发 LLM 调用。
    registry: ProjectRegistry 实例——从调用方传入（避免循环导入）。
    """
    import time

    if not project_name or registry is None:
        return

    now = time.time()
    last = _last_context_sync.get(project_name, 0)
    if now - last < _CONTEXT_SYNC_INTERVAL:
        return

    _last_context_sync[project_name] = now

    proj = registry.get(project_name)
    if proj is None or not proj.local_path:
        return

    # 检查 brief 是否存在——不存在则跳过（等首次生成）
    from orbit.brief.checker import check_brief
    status = check_brief(proj.local_path)
    if not status.has_brief:
        return

    # 后台异步刷新
    import asyncio as _async

    _async.create_task(_refresh_context_bg(proj.local_path, project_name))


async def _refresh_context_bg(project_path: str, project_name: str) -> None:
    """后台任务——重新扫描目录结构并更新 CONTEXT.md。"""
    import structlog as _sl
    logger = _sl.get_logger("orbit.chat.context_sync")

    try:
        from orbit.brief.generator import BriefGenerator, analyze_directory
        from orbit.brief.storage import read_brief

        brief = read_brief(project_path)
        if brief is None:
            return

        # 只在目录结构变化时才调用 LLM
        analysis = analyze_directory(project_path)
        if analysis.file_count < 5:
            return  # 项目太小，不生成

        # 需要 LLM——在后台获取
        llm = None
        try:
            from orbit.api.main import _llm_glm5
            llm = _llm_glm5
        except Exception:
            pass

        if llm is None:
            return

        gen = BriefGenerator(llm)
        written = await gen.generate_all_context_md(project_path, brief, min_subdirs=2)
        if written:
            logger.info("context_auto_refreshed", project=project_name, files=len(written))
    except Exception:
        logger.exception("context_auto_refresh_failed", project=project_name)
