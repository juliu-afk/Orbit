# PRD+ADR · Step 3.4 外挂领域知识图谱

## Step 3.4 外挂领域知识图谱

---

## PRD（产品需求文档）

| PRD · 领域知识图谱模块 | |
| --- | --- |
| **背景** | 系统需要处理会计、金融、法律等专业性任务，通用LLM的专业知识不足且存在幻觉风险。需构建外挂式领域知识图谱，通过"精确查询+语义检索"双模架构，为Agent提供权威、可验证的专业知识。 |
| **用户故事** | 作为DeveloperAgent，我在编写财务计算代码时，通过MCP调用`query_knowledge(domain="finance", concept="CurrentRatio", mode="exact")`获取流动比率的准确定义和公式；同时通过`query_knowledge(mode="semantic")`检索相关的监管要求全文。 |
| **需求描述** | ① 三层知识架构（通用层→领域层→实例层）。<br>② 支持会计/金融/法律三个领域的本体设计。<br>③ 实现五级来源筛选流程。<br>④ 通过MCP协议暴露 `query_knowledge` 工具，支持 exact/semantic/hybrid 三种模式。<br>⑤ 每次知识查询记录到审计表（task_audit_trail）。<br>⑥ 提供合规验证工具 `validate_compliance`。 |
| **范围 Do/Don't** | **Do：**会计/金融/法律三个领域的本体设计+实例层注入；Neo4j+向量库双存储；MCP协议集成；零Token精确查询。<br>**Don't：**不支持领域知识的自动演进（仍需人工审核）；不支持Agent自动更新知识库（只读）。 |
| **数据契约** | `query_knowledge(domain: str, concept: str, mode: Literal["exact", "semantic", "hybrid"]) -> QueryResult`<br>`QueryResult`包含：`content: str`, `source_uri: str`, `confidence: float`, `mode_used: str`<br>`validate_compliance(domain: str, content: str) -> ValidationResult` |
| **异常定义** | **Neo4jQueryError：** Neo4j查询执行失败（连接超时、Cypher语法错误、实体不存在），返回空结果并记录审计日志。<br>**VectorStoreError：** 向量库检索失败（Milvus/Qdrant连接超时、索引不存在），降级为精确模式重试。<br>**KnowledgeNotFoundError：** 精确模式下实体不存在，返回空结果（不触发LLM补充）。<br>**SourceValidationError：** 来源筛选未通过（五级来源全部不达标），拒绝返回结果并告警。<br>**EmbeddingModelError：** 语义向量化失败（模型加载失败、文本超长），降级为精确模式。<br>**MCPConnectionError：** MCP协议通信失败（Agent无法调用知识图谱），触发降级告警。 |
| **成功标准→验收** | **SC1: 精确查询零Token** → **AC1:** MCP调用 `mode="exact"`，返回确定结果，耗时<50ms，无LLM调用。<br>**SC2: MCP协议兼容** → **AC2:** Agent通过标准化MCP工具调用知识图谱，工具注册到MCP Server。<br>**SC3: 来源可追溯** → **AC3:** 每个知识点返回`source_uri`，格式为`{来源类型}://{来源标识}/{条目ID}`（如`standard://cas/ifrs_ias_1`）。<br>**SC4: 三层架构** → **AC4:** 通用层覆盖编程语言标准库；领域层覆盖会计/金融/法律本体；实例层注入具体企业数据（只读）。<br>**SC5: 五级来源筛选** → **AC5:** 每条知识必须经过"国际标准→国家法规→行业规范→地方规章→企业内部"的五级筛选，缺一不可。 |
| **待定决策（已决议）** | **Q:** 向量库选Milvus还是Qdrant？ → **决议：** Qdrant（Rust实现、性能更优、支持更丰富的过滤条件），但保留切换接口以备切换。<br>**Q:** 语义向量化模型用哪个？ → **决议：** SentenceTransformers `all-MiniLM-L6-v2`（速度快、维度低384），精确场景用`exact`模式绕过向量化。<br>**Q:** 知识库更新频率？ → **决议：** 实例层（企业数据）每季度人工审核更新；领域层（法规/准则）每月增量同步；通用层随系统版本更新。 |

---

## ADR（架构决策记录）

| ADR · 知识图谱采用"精确查询 + 语义检索"双模架构 | |
| --- | --- |
| **决策** | 知识图谱模块同时支持两种查询模式：<br>1. **精确模式：** 通过Neo4j Cypher查询，返回确定性结果（零Token，<50ms）。<br>2. **语义模式：** 通过向量检索，返回相关性排序的文档片段。<br>3. **混合模式：** 图谱锚定 + 向量扩展，联合检索。 |
| **理由** | 精确查询解决"是什么"（概念定义、法规条文、公式验证）。<br>语义检索解决"还有什么"（开放探索、全文检索、上下文扩展）。<br>两者通过统一的MCP接口暴露，Agent无需感知底层差异。 |
| **技术栈** | Neo4j 5.x（结构化知识存储）；Milvus/Qdrant（向量检索）；SentenceTransformers（语义向量化）；MCP Python SDK（协议集成）。 |
| **架构位置** | `/src/knowledge_graph/` 目录，包含：`neo4j_store.py`（图谱存储）、`vector_store.py`（向量检索）、`query_engine.py`（统一查询引擎）、`mcp_server.py`（MCP协议暴露）、`ontology/`（领域本体定义）。 |
| **实施细节** | ① **第1周：** 部署Neo4j + Qdrant，设计会计/金融/法律本体Cypher Schema。<br>② **第2周：** 实现双模查询引擎（精确+语义+混合），MCP Server开发。<br>③ **第3周：** Agent集成（工具注册、审计表记录），五级来源筛选实现。<br>④ **第4周：** 端到端测试，性能调优（目标<50ms），知识库增量更新机制。 |
| **风险与缓解** | **风险1：** Neo4j/Qdrant单点故障导致知识查询不可用。<br>**缓解：** Qdrant支持副本机制；Neo4j集群版部署；降级策略：向量库不可用时仅用精确模式，Neo4j不可用时返回缓存结果（标记为STALE）。<br><br>**风险2：** 语义检索返回结果质量依赖embedding模型。<br>**缓解：** 精确模式作为兜底；语义检索结果附带confidence分数，低于阈值时自动降级；定期评估模型效果并更换。<br><br>**风险3：** 领域本体设计不完整导致新概念无法建模。<br>**缓解：** 采用"核心本体+扩展槽"设计，预留`custom_properties`字段；人工审核流程确保新概念注入质量。 |
| **需求错位** | 若未来需要支持更多专业领域（如医疗、专利），当前三层架构可扩展。只需增加新的本体文件，无需修改引擎。 |
| **技术约束** | 知识库为只读，不允许Agent直接写入。更新需通过人工审核的CI流程。 |
| **环境配置** | `KNOWLEDGE_GRAPH_NEO4J_URI=bolt://localhost:7687`<br>`KNOWLEDGE_GRAPH_NEO4J_USER=neo4j`<br>`KNOWLEDGE_GRAPH_NEO4J_PASSWORD=<secure>`<br>`KNOWLEDGE_GRAPH_VECTOR_URL=http://localhost:6333`<br>`KNOWLEDGE_GRAPH_EMBEDDING_MODEL=all-MiniLM-L6-v2` |
| **依赖链** | Neo4j → 存储结构化知识；Qdrant → 存储向量索引；SentenceTransformers → 生成embedding；MCP Python SDK → 协议暴露。 |

---

## 🧪 原子化测试用例（pytest）

```python
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

class TestStep34ExternalKnowledgeGraph:
    """Step 3.4 外挂领域知识图谱 - 验收测试"""

    def test_exact_query_zero_token(self):
        """SC1: 精确查询零Token，耗时<50ms"""
        # 验证 exact 模式不调用 LLM，直接通过 Neo4j Cypher 返回结果
        pass

    def test_mcp_protocol_compatibility(self):
        """SC2: Agent通过MCP工具调用知识图谱"""
        # 验证 query_knowledge 工具已注册到 MCP Server
        # 验证 Agent 可以通过 MCP 协议调用
        pass

    def test_source_traceability(self):
        """SC3: 每个知识点返回source_uri"""
        # 验证返回结果包含 source_uri 字段
        # 验证 source_uri 格式正确
        pass

    def test_triple_layer_knowledge_architecture(self):
        """三层知识架构正确性验证"""
        # 验证通用层（编程语言标准库）可查询
        # 验证领域层（会计/金融/法律本体）可查询
        # 验证实例层（企业数据）可查询（只读）
        pass

    def test_five_level_source_filtering(self):
        """五级来源筛选机制"""
        # 验证每个知识点经过五级筛选
        # 验证来源等级：国际标准 > 国家法规 > 行业规范 > 地方规章 > 企业内部
        pass

    def test_hybrid_query_mode(self):
        """混合查询模式：图谱锚定+向量扩展"""
        # 验证 hybrid 模式先查图谱确定实体
        # 验证再用向量检索扩展相关文档
        pass

    def test_audit_integration(self):
        """知识查询记录到 task_audit_trail"""
        # 验证每次 query_knowledge 调用都写入审计表
        # 验证审计记录包含：query params, result hash, latency, source_uri
        pass

    def test_validate_compliance_tool(self):
        """合规验证工具 validate_compliance"""
        # 验证给定内容通过合规检查
        # 验证不合规内容返回错误详情
        pass

    def test_neo4j_query_error_handling(self):
        """Neo4j查询异常处理"""
        # 验证连接超时时返回空结果并记录审计
        # 验证Cypher语法错误时返回有意义的错误信息
        pass

    def test_vector_store_fallback(self):
        """向量库降级策略"""
        # 验证向量库不可用时降级到精确模式
        # 验证降级后仍返回有效结果
        pass

    def test_knowledge_not_found_exact_mode(self):
        """精确模式下知识不存在"""
        # 验证精确模式查不到时返回空结果（不触发LLM补充）
        pass

    def test_semantic_search_confidence_threshold(self):
        """语义检索置信度阈值"""
        # 验证置信度低于阈值时自动降级或告警
        pass
```

---

## MCP Server 代码示例

```python
# /src/knowledge_graph/mcp_server.py
from mcp.server import Server
from mcp.types import Tool, TextContent
from pydantic import BaseModel
from typing import Literal, Optional

app = Server()

class QueryKnowledgeParams(BaseModel):
    domain: Literal["accounting", "finance", "legal"]
    concept: str
    mode: Literal["exact", "semantic", "hybrid"] = "exact"

class QueryResult(BaseModel):
    content: str
    source_uri: str
    confidence: float
    mode_used: str

@app.list_tools()
async def list_tools():
    return [
        Tool(
            name="query_knowledge",
            description="查询领域知识图谱，支持精确查询和语义检索",
            inputSchema={
                "type": "object",
                "properties": {
                    "domain": {"type": "string", "enum": ["accounting", "finance", "legal"]},
                    "concept": {"type": "string"},
                    "mode": {"type": "string", "enum": ["exact", "semantic", "hybrid"]}
                }
            }
        ),
        Tool(
            name="validate_compliance",
            description="验证内容是否符合领域合规要求",
            inputSchema={
                "type": "object",
                "properties": {
                    "domain": {"type": "string"},
                    "content": {"type": "string"}
                }
            }
        )
    ]

@app.call_tool()
async def call_tool(name: str, arguments: dict):
    if name == "query_knowledge":
        params = QueryKnowledgeParams(**arguments)
        result = await query_engine.query(
            domain=params.domain,
            concept=params.concept,
            mode=params.mode
        )
        return [TextContent(type="text", text=result.json())]
    elif name == "validate_compliance":
        # 合规验证逻辑
        pass
```

---

## 领域本体设计（会计/金融/法律）

### 会计领域本体（Cypher Schema片段）

```cypher
// 会计领域本体
CREATE CONSTRAINT accounting_concept IF NOT EXISTS
FOR (c:AccountingConcept) REQUIRE c.id IS UNIQUE;

CREATE (c:AccountingConcept {
    id: "ifrs_ias_1",
    name: "IAS 1 - 财务报表呈报",
    definition: "整套财务报表的呈报要求",
    source_uri: "standard://ifrs/ias_1_2024",
    source_level: "international"
});

// 财务比率概念
CREATE (r:FinancialRatio {
    id: "current_ratio",
    name: "流动比率",
    formula: "流动资产 / 流动负债",
    standard_range: "1.5-2.0",
    source_uri: "concept://finance/ratio/current_ratio"
});
```

### 金融领域本体（Cypher Schema片段）

```cypher
// 金融领域本体
CREATE (r:Regulation {
    id: "basel_iii_liquidity",
    name: "巴塞尔III流动性覆盖率",
    full_text: "...",
    effective_date: date("2015-01-01"),
    source_uri: "standard://basel/iii_liquidity"
});
```

### 法律领域本体（Cypher Schema片段）

```cypher
// 法律领域本体
CREATE (l:LegalReference {
    id: "company_law_2024_art_76",
    name: "公司法2024第七十六条",
    content: "股份有限公司的设立条件...",
    source_uri: "law://cn/company_law/2024/art_76"
});
```

---

## 来源筛选五级流程

```
┌─────────────────────────────────────────┐
│          知识条目注入申请               │
└─────────────────┬─────────────────────┘
                  ▼
┌─────────────────────────────────────────┐
│ L1. 国际标准（IAS/IFRS/ISO/联合国公约） │
│     → 通过：标记 source_level="INTL"    │
└─────────────────┬─────────────────────┘
                  ▼ (不通过)
┌─────────────────────────────────────────┐
│ L2. 国家法规（法律/行政法规/部门规章）   │
│     → 通过：标记 source_level="NAT"    │
└─────────────────┬─────────────────────┘
                  ▼ (不通过)
┌─────────────────────────────────────────┐
│ L3. 行业规范（行业标准/自律规则）        │
│     → 通过：标记 source_level="IND"    │
└─────────────────┬─────────────────────┘
                  ▼ (不通过)
┌─────────────────────────────────────────┐
│ L4. 地方规章（地方性法规/地方政府规章） │
│     → 通过：标记 source_level="REG"    │
└─────────────────┬─────────────────────┘
                  ▼ (不通过)
┌─────────────────────────────────────────┐
│ L5. 企业内部（内部规程/内部案例）        │
│     → 通过：标记 source_level="CORP"   │
└─────────────────┬─────────────────────┘
                  ▼ (全部不通过)
┌─────────────────────────────────────────┐
│        ❌ 拒绝注入，告警通知审核员       │
└─────────────────────────────────────────┘
```

---

**文档版本：** V14.1 · Step 3.4 · 2026年6月22日<br>
**状态：** 已定稿<br>
**影响Step：** Phase 3（第5-6周）
