"""网页正文提取 (V15.2).

将搜索结果的 URL 转为 Markdown 结构化内容。
用 readability-lxml 做正文提取 + html2text 转 Markdown。

WHY 提取正文: 网页原始 HTML 含大量噪声（广告/导航/SEO），
Agent 读取成本高。提取后只保留核心内容。
"""

from __future__ import annotations

import structlog

logger = structlog.get_logger("orbit.knowledge.search.extractor")


class ContentExtractor:
    """网页正文提取器——HTML → 结构化 Markdown。

    Usage:
        extractor = ContentExtractor()
        markdown = await extractor.extract("https://example.com/article")
    """

    def __init__(self) -> None:
        self._client = None

    async def extract(self, url: str, timeout: float = 10.0) -> str:
        """从 URL 提取正文并转 Markdown。

        依赖 readability-lxml + html2text——首次调用时惰性导入，
        避免未安装时阻塞模块加载。
        """
        try:
            import httpx
        except ImportError:
            logger.warning("httpx_not_available", url=url[:80])
            return ""

        try:
            if self._client is None:
                self._client = httpx.AsyncClient(
                    timeout=httpx.Timeout(timeout),
                    headers={"User-Agent": "Orbit-Agent/1.0"},
                    follow_redirects=True,
                )

            resp = await self._client.get(url)
            resp.raise_for_status()
            html = resp.text

            return self._html_to_markdown(html, url)

        except Exception as e:
            logger.debug("extract_failed", url=url[:80], error=str(e)[:100])
            return ""

    def _html_to_markdown(self, html: str, url: str = "") -> str:
        """HTML → 正文 → Markdown 管线。"""
        # 1. 正文提取
        try:
            from readability import Document  # readability-lxml

            doc = Document(html)
            content_html = doc.summary()
        except ImportError:
            logger.warning_once("readability_not_installed", fallback="html2text")
            content_html = html
        except Exception:
            content_html = html

        # 2. HTML → Markdown
        try:
            import html2text

            converter = html2text.HTML2Text()
            converter.ignore_links = False
            converter.ignore_images = True
            converter.body_width = 0  # 不自动换行
            converter.skip_internal_links = True
            markdown = converter.handle(content_html)
        except ImportError:
            logger.warning_once("html2text_not_installed", fallback="raw_text")
            # 简单去标签 fallback
            import re
            markdown = re.sub(r"<[^>]+>", "", content_html)
            markdown = re.sub(r"\n\s*\n", "\n\n", markdown)
        except Exception:
            markdown = content_html

        # 3. 截断过长内容——Agent 上下文有限
        max_chars = 8000
        if len(markdown) > max_chars:
            markdown = markdown[:max_chars] + f"\n\n[内容已截断，原文 {len(markdown)} 字符]"

        return markdown.strip()

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None
