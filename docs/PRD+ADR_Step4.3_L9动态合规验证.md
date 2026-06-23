## Step 4.3：L9动态合规验证层

| PRD · L9动态合规验证层 |  |
| --- | --- |
| **背景** | LLM生成内容所依据的专业知识（法规、会计准则、行业合规要求）存在时效性问题——"僵尸知识"（过时5年以上的法规条文、已被替代的准则条款）被当作权威引用，导致合规风险。L1-L8层主要防御代码/配置类幻觉，对"过时知识被当作正确知识使用"这一类问题无能为力。 |
| **用户故事** | 作为合规审计Agent，当我需要引用具体法规条款或会计准则时，系统应自动验证该知识点的时效性——查询最新法规库，判断是否存在新版本或修正案，并提示我使用最新版本。 |
| **需求描述** | ① 知识时效性判断：对于每个被引用的专业知识点，自动查询最新来源（法规库、准则官网），判断是否存在更新版本。<br>② 动态合规验证：支持自定义合规规则（如"2024年起 IFRS 16 变更"），在知识被使用时自动触发验证。<br>③ 过期知识告警：当引用内容已被更新时，输出显式告警（⚠️ 过期知识），说明"当前引用 vs 最新版本的差异"。<br>④ 降级策略：当合规验证服务不可用时，不阻塞Agent运行，仅标记"未验证"状态。<br>⑤ 审计集成：每次合规验证事件（通过/不通过/未验证）记录到 task_audit_trail。 |
| **范围 (Do/Don't)** | **Do：**知识时效性查询；版本差异提示；合规规则自定义；与审计表集成。<br>**Don't：**不替代人工合规判断（仅提供参考信息）；不自动更新知识库（只读）。 |
| **数据契约** | **ComplianceCheckRequest:** `{ knowledge_point_id, reference_text, reference_date, source_type(法规/准则/行业标准), metadata }`<br>**ComplianceCheckResponse:** `{ status(pass/warning/error/unverified), latest_version, version_diff, warning_message, checked_at, source_url }`<br>**ComplianceRule:** `{ rule_id, name, condition(date_range/version_constraint), severity(INFO/WARNING/CRITICAL), message }` |
| **异常定义** | `ComplianceServiceUnavailableError`（外部API不可用）；`KnowledgeNotFoundError`（知识库中未找到该知识点）；`RuleParseError`（DSL规则解析失败）。 |
| **SC→AC** | **SC1:** 时效性判断准确率 ≥95% → **AC1:** 对100个测试知识点（新旧版本对），正确识别 ≥95个。<br>**SC2:** 合规告警误报率 ≤5% → **AC2:** 人工抽检100条告警，误报 ≤5条。<br>**SC3:** 验证延迟 <200ms → **AC3:** 单次验证 P99延迟 <200ms，不阻塞Agent主流程。 |
| **待定决策** | **Q:** 外部API查询频率如何控制避免限流？ → **决议：** 本地缓存TTL=1小时，后台任务轮询更新，Phase 1阶段规则数≥50。 |

| ADR · L9动态合规验证架构 |  |
| --- | --- |
| **决策** | L9动态合规验证层采用**"外部合规库实时查询 + 本地缓存"**架构，而非内嵌知识库。 |
| **理由** | ① 专业知识（法规、准则）更新频繁，内嵌知识库存在"再次过时"风险。<br>② 外部权威来源（财政部官网、IFRS官网）是最可信赖的"最新版本"判断依据。<br>③ 本地缓存避免每次验证都查询外部API（降延迟+降费用）。<br>④ 降级模式确保外部服务不可用时系统不崩溃。 |
| **备选方案** | ① 内嵌知识库（定期更新）→ 存在"更新窗口期"内引用过时知识的风险 → 放弃。<br>② 仅依赖用户手动标记 → 无法覆盖隐性过时知识 → 放弃。 |
| **技术栈版本** | 合规查询API：财政部会计准则委员会API / 国家税务总局法规库API（选其一）；本地缓存：SQLite + Redis TTL（1小时更新一次）；规则引擎：内嵌DSL，支持自定义合规规则。 |
| **架构位置** | 合规层 `/src/compliance/validator.py`（验证器）+ `/src/compliance/rule_engine.py`（DSL规则引擎）+ `/src/compliance/cache_manager.py`（缓存管理）。 |
| **实施细节** | **缓存更新：** 后台任务每小时轮询外部API，更新本地SQLite。<br>**版本比对：** 提取法规编号+发布日期，与缓存版本对比。<br>**规则匹配：** DSL规则引擎支持日期条件判断（如 date > 2024-01-01 → 触发更新告警）。<br>**MCP协议暴露：** `validate_compliance` 工具供Agent调用。 |
| **风险与缓解** | 风险：外部API不可用（网络问题、API变更）。缓解：降级为"未验证"状态，不阻塞主流程。<br>风险：合规规则覆盖率不足。缓解：Phase 1补充规则，目标规则数≥50。 |
| **依赖链** | 依赖Step 4.1（审计表集成）；依赖MCP协议（Step 5.2已定义）。 |

---

## Step 4.3 补充：L9动态合规验证层实施路线

| 里程碑 | 内容 | 交付物 |
| --- | --- | --- |
| M1 | 核心验证器实现 | `validator.py` - 支持知识时效性查询和版本比对 |
| M2 | DSL规则引擎 | `rule_engine.py` - 支持自定义合规规则定义与匹配 |
| M3 | 缓存管理层 | `cache_manager.py` - SQLite + Redis TTL缓存实现 |
| M4 | MCP工具暴露 | `validate_compliance` 工具注册到ToolRegistry |
| M5 | 审计集成 | 合规验证事件写入 task_audit_trail |
| M6 | 降级模式 | 外部API不可用时的 graceful degradation |

---

🧪 原子化测试用例 (pytest)：

```python
import pytest, asyncio
from src.compliance.validator import ComplianceValidator, ComplianceCheckRequest, ComplianceCheckResponse
from src.compliance.rule_engine import ComplianceRuleEngine, ComplianceRule
from src.compliance.cache_manager import ComplianceCacheManager

# ── Step 4.3 L9动态合规验证层 ──
class TestStep43L9Compliance:
    """Step 4.3 L9动态合规验证层 - 验收测试"""

    def test_knowledge_timeliness_check(self):
        """SC1: 时效性判断准确率 ≥95%"""
        # 使用100个测试知识点（新旧版本对），正确识别 ≥95个
        # 验证：validator.check_timeliness() 对新旧版本对返回正确的status
        pass

    def test_compliance_alert_false_positive_rate(self):
        """SC2: 告警误报率 ≤5%"""
        # 人工抽检100条告警，误报 ≤5条
        # 验证：warning类型告警中，真实误报比例 ≤5%
        pass

    def test_validation_latency(self):
        """SC3: 验证延迟 <200ms"""
        # P99延迟 <200ms
        # 验证：单次验证 P99延迟 < 200ms
        pass

    def test_degradation_when_external_api_unavailable(self):
        """降级模式：外部服务不可用时不阻塞主流程"""
        # 验证：外部API不可用时，返回 status=unverified，不抛出异常
        pass

    def test_audit_integration(self):
        """验证事件记录到 task_audit_trail"""
        # 验证：每次 ComplianceCheckResponse 都写入 task_audit_trail
        pass

    def test_version_diff_message(self):
        """过期知识告警包含版本差异说明"""
        # 验证：当 reference_date < latest_version 时，返回 warning 并附带 version_diff
        pass

    def test_rule_engine_date_condition(self):
        """DSL规则引擎支持日期条件判断"""
        # 验证：rule_engine.evaluate() 能正确解析 date > 2024-01-01 条件
        pass

    def test_cache_hit_reduces_latency(self):
        """缓存命中时验证延迟显著降低"""
        # 验证：缓存命中时 P99延迟 < 50ms
        pass

    def test_custom_compliance_rule(self):
        """支持自定义合规规则（如 IFRS 16 2024年变更）"""
        # 验证：用户可定义规则并在验证时触发
        pass
```
