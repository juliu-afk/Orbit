"""搜索意图路由 (V15.2).

根据查询内容判断意图类型 → 选择最优数据源组合。
用 LLM 做意图分类（轻量 prompt，~50 tokens 输出）。

WHY LLM 而非关键词: "查一下这个公司的股权结构" vs "这个API怎么用" ——
关键词无法区分"企业查询"和"代码查询"，LLM 能。
"""

from __future__ import annotations

from enum import StrEnum


class SearchIntent(StrEnum):
    """搜索意图类型——决定走哪些数据源。"""

    CODE = "code"            # 代码/API/库/框架
    WEB = "web"              # 通用信息/新闻/文档
    ACADEMIC = "academic"    # 论文/学术
    ENTERPRISE = "enterprise"  # 企业/工商/金融
    MIXED = "mixed"          # 无法明确→全源并行


# 意图 → 数据源映射表
INTENT_SOURCES: dict[SearchIntent, list[str]] = {
    SearchIntent.CODE: ["code", "web"],
    SearchIntent.WEB: ["web"],
    SearchIntent.ACADEMIC: ["web"],  # MVP 阶段用通用搜索替代
    SearchIntent.ENTERPRISE: ["web", "code"],
    SearchIntent.MIXED: ["web", "code"],
}

# LLM 意图分类 prompt（轻量）
INTENT_PROMPT = """判断以下查询的意图类型。只返回一个单词。
类型: code（代码/API/库/编程）/ web（通用信息/新闻/文档）/ academic（论文/学术）/ enterprise（企业/工商/金融）/ mixed（无法判断）

查询: {query}
意图:"""


class IntentRouter:
    """LLM 驱动的意图路由器。

    Usage:
        router = IntentRouter(llm_client)
        intent = await router.route("Python async 最佳实践")
        sources = router.sources_for(intent)  # → ["code", "web"]
    """

    def __init__(self, llm_client: object = None) -> None:
        """初始化路由器。

        Args:
            llm_client: LLM 客户端——需支持 generate(prompt) 方法。
                        传入 None 时默认返回 MIXED（全源搜索）。
        """
        self._llm = llm_client

    async def route(self, query: str) -> SearchIntent:
        """分析查询意图——返回意图类型。"""
        if self._llm is None:
            return SearchIntent.MIXED

        try:
            prompt = INTENT_PROMPT.format(query=query[:500])
            response = await self._llm.generate(prompt)
            raw = response.strip().lower() if isinstance(response, str) else "mixed"

            for intent in SearchIntent:
                if intent.value in raw:
                    return intent
            return SearchIntent.MIXED

        except Exception:
            # LLM 调用失败→安全回退到全源搜索
            return SearchIntent.MIXED

    def sources_for(self, intent: SearchIntent) -> list[str]:
        """返回该意图应使用的数据源名称列表。"""
        return INTENT_SOURCES.get(intent, ["web", "code"])

    def route_sync(self, query: str) -> SearchIntent:
        """同步版路由——仅做关键词启发式判断，不调用 LLM。

        WHY 同步版: 某些同步上下文（如 MemoryStore.search）无法 await LLM。
        """
        query_lower = query.lower()
        code_keywords = [
            "代码", "code", "api", "函数", "python", "js", "rust", "go",
            "库", "library", "框架", "framework", "报错", "error", "bug",
            "import", "async", "class", "function", "github",
        ]
        enterprise_keywords = [
            "公司", "企业", "股权", "工商", "财务", "上市", "融资",
            "估值", "年报", "招股书",
        ]

        if any(kw in query_lower for kw in enterprise_keywords):
            return SearchIntent.ENTERPRISE
        if any(kw in query_lower for kw in code_keywords):
            return SearchIntent.CODE
        return SearchIntent.MIXED
