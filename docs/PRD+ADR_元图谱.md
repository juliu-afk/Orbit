## Step 8：元图谱——图谱之间的关联关系

| PRD · 元图谱设计 |  |
| --- | --- |
| **背景** | 五图谱（代码、数据库、配置、知识、推理链）各自独立，但描述的是同一软件系统的不同侧面。它们之间的交叉引用关系（如"哪个函数读写了哪张表"）未被显式记录，导致Agent无法进行跨图谱的影响面分析。 |
| **用户故事** | 作为DeveloperAgent，我在修改代码前，能通过元图谱查询"这个函数影响哪些数据库表、依赖哪些配置项、源自哪个需求决策"；作为ArchitectAgent，我能通过元图谱检测架构腐化。 |
| **需求描述** | ① 定义跨图谱关系类型（READS_FROM、WRITES_TO、DEPENDS_ON、REFERENCES、PRODUCED_BY、DECIDED_AT、CONNECTS_TO）。② 在Neo4j中存储这些关系，形成"元图谱"。③ 提供统一查询接口 `query_cross_graph()`。④ Agent在编码/规划时可主动查询元图谱进行影响面分析。⑤ 定期运行架构腐化检测查询。 |
| **范围 (Do/Don't)** | **Do：**跨图谱关系建模、元图谱存储架构、影响面分析查询、架构腐化检测。**Don't：**不修改五图谱各自的Schema（只做扩展关联）；不引入新的存储后端。 |
| **数据契约** | 关系类型标签：`READS_FROM`、`WRITES_TO`、`DELETES_FROM`、`DEPENDS_ON`、`OVERRIDES`、`REFERENCES`、`COMPLIES_WITH`、`PRODUCED_BY`、`MODIFIED_BY`、`DECIDED_AT`、`CONNECTS_TO`、`USED_IN`。 |
| **异常定义** | 若某代码节点无任何跨图谱关联，元图谱查询返回空列表而非报错；若Neo4j查询超时，返回 `{"error": "timeout", "node_id": "..."}`。 |
| **SC→AC** | **SC1:** 影响面查询 → **AC1:** 查询 `PaymentService.process`，返回关联的数据库表、配置项、推理链。<br>**SC2:** 架构腐化检测 → **AC2:** 定期查询返回跨层依赖告警。<br>**SC3:** 变更追溯 → **AC3:** 配置变更后查询受影响的代码列表。 |
| **待定决策** | **Q:** 元图谱与五图谱共用同一Neo4j实例还是独立实例？ → **决议：**共用同一实例，通过标签和关系类型逻辑隔离（避免引入新运维复杂度）。 |

| ADR · 元图谱存储策略 |  |
| --- | --- |
| **决策** | 元图谱与五图谱**共享同一Neo4j实例**，通过标签和关系类型实现逻辑隔离。<br>① 五图谱节点使用独立标签（`CodeNode`、`DbNode`、`ConfigNode`、`KnowledgeNode`、`ReasoningStep`）。<br>② 跨图谱关系使用特殊关系类型（`:READS_FROM`、`:DEPENDS_ON` 等）。<br>③ 元图谱的查询通过 `query_cross_graph()` 统一入口。 |
| **理由** | ① 避免引入新的数据源，降低运维复杂度。<br>② 跨图谱查询可在单次Cypher中完成，性能最优。<br>③ 与现有MCP协议栈无缝集成。 |
| **技术栈版本** | Neo4j 5.x（与五图谱共用实例），Cypher查询语言。 |
| **架构位置** | 图谱层 `/src/graph/meta_query.py`，MCP工具暴露 `/src/mcp/servers/meta_mcp_server.py`。 |
| **实施细节** | **AC1（影响面查询）：** |
| | ``代码块-1`` |
| | **AC2（架构腐化检测）：** |
| | ``代码块-2`` |
| | **AC3（变更追溯）：** |
| | ``代码块-3`` |
| **风险与缓解** | 风险：跨图谱关系数量快速增长导致查询延迟。缓解：建立定期清理机制，删除超过90天未访问的元关系。 |
| **需求错位** | 若未来需要图谱级别的访问控制（如某些元关系仅对ArchitectAgent可见），当前设计通过Neo4j标签权限可扩展支持。 |
| **技术约束** | 不引入新的图数据库；所有元关系必须可从五图谱节点推导，不允许手动录入（保证一致性）。 |
| **环境配置** | 复用现有Neo4j连接配置，无需新增环境变量。 |
| **依赖链** | 依赖五图谱（Step 1.2/3.2/3.4/审计补丁）先行完成Schema定义。 |

### ✅ 验收测试 · pytest

```python
import pytest
from src.graph.meta_query import MetaGraphQuery
from src.graph.neo4j_client import Neo4jClient

@pytest.fixture
def meta_graph():
    neo4j = Neo4jClient()
    return MetaGraphQuery(neo4j)

# SC1 → AC1: 影响面查询
@pytest.mark.asyncio
async def test_impact_analysis_returns_related_databases(meta_graph):
    result = await meta_graph.impact_analysis("PaymentService.process")
    assert "databases" in result
    assert "configs" in result
    assert "reasoning" in result
    assert isinstance(result["databases"], list)

# SC1 → AC1: 查询不存在的节点返回空而非报错
@pytest.mark.asyncio
async def test_impact_analysis_nonexistent_node_returns_empty(meta_graph):
    result = await meta_graph.impact_analysis("NonExistent.func")
    assert result["databases"] == []
    assert result["configs"] == []

# SC2 → AC2: 架构腐化检测
@pytest.mark.asyncio
async def test_architecture_health_check_returns_violations(meta_graph):
    violations = await meta_graph.architecture_health_check()
    assert isinstance(violations, list)
    # 若返回空列表说明无腐化（正常）
    for v in violations:
        assert "controller" in v or "config_key" in v

# SC3 → AC3: 配置变更追溯
@pytest.mark.asyncio
async def test_config_change_trace(meta_graph):
    result = await meta_graph.config_impact_trace("PAYMENT_TIMEOUT")
    assert "affected_code" in result
    assert "affected_tasks" in result
```
