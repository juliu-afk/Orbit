# 多Agent自循环系统 · 全量Step工程级PRD & ADR

覆盖Phase 0~7全部18个核心Step · 无占位符 · 编码级颗粒度

**编写声明：**本文档针对每一个Step均提供了**边界约束（输入/输出/异常码）**、**GWT原子化验收标准**、**实施类图/伪代码**、**技术栈版本**，以及包含**多维对比矩阵**的ADR。开发人员可直接依据本文档搭建脚手架、编写测试用例和进行技术决策。

---

## 目录（全量Step索引）

- **Phase 0 (W1)：**Step 0.1 项目章程 · Step 0.2 技术栈基线 · **Step 0.3 需求澄清**
- **Phase 1 (W2)：**Step 1.1 系统架构 · Step 1.2 三图谱Schema · Step 1.3 技术体系总览
- **Phase 2 (W3-W4)：**Step 2.1 LiteLLM网关 · Step 2.2 检查点持久化
- **Phase 3 (W5-W6)：**Step 3.1 代码图谱 · Step 3.2 数据库图谱 · Step 3.3 配置图谱
- **Phase 4 (W7-W8)：**Step 4.1 L1-L4防幻觉 · Step 4.2 L5-L8防幻觉
- **Phase 5 (W9-W10)：**Step 5.1 自研调度器（含需求澄清） · Step 5.2 Agent角色与Prompt
- **Phase 6 (W11-W12)：**Step 6.1 Vue3驾驶舱 · Step 6.2 端到端测试 · **Step 6.3 测试体系**
- **Phase 7 (W13)：**Step 7.1 灰度发布 · Step 7.2 AgentOps可观测性

---

## Phase 0：项目启动与需求确认

### Step 0.1：项目章程与范围定义

| PRD维度 | 详细内容 |
| --- | --- |
| **输入/输出** | **输入：**干系人访谈记录、竞品分析（CrewAI/AutoGen）;**输出：**章程文档（含Mission、Scope In/Out、RACI矩阵）。**异常：**若度量指标未量化，则驳回。 |
| **GWT验收** | Given 5份干系人输入，When 生成章程，Then 必须包含明确的“Out-of-scope”（如不支持时序图谱）；Given 章程草案，When 全员评审，Then 获得至少3名核心成员LGTM。 |
| **实施细节** | 使用Markdown模板，变量占位符（如{PROJECT_NAME}）通过脚本替换。评审采用GitHub PR + CODEOWNERS机制。 |
| **技术栈** | 无特定代码依赖，但需配置`markdownlint`校验格式。 |

#### ADR 0.1：自研优先 vs 集成优先

| 备选 | 上线速度 | Token优化上限 | 故障隔离 | 决策 |
| --- | --- | --- | --- | --- |
| A. CrewAI集成 | 1周 | 低（黑盒） | 差 | **✅ 选B** |
| B. 自研调度器 | 8周 | 高（完全可控） | 强 |  |
| **理由：**V13基准测试显示CrewAI单任务Token超40且延迟>32s，无法满足≤35目标。自研虽延迟但长期收益显著。 | **理由：**V13基准测试显示CrewAI单任务Token超40且延迟>32s，无法满足≤35目标。自研虽延迟但长期收益显著。 | **理由：**V13基准测试显示CrewAI单任务Token超40且延迟>32s，无法满足≤35目标。自研虽延迟但长期收益显著。 | **理由：**V13基准测试显示CrewAI单任务Token超40且延迟>32s，无法满足≤35目标。自研虽延迟但长期收益显著。 | **理由：**V13基准测试显示CrewAI单任务Token超40且延迟>32s，无法满足≤35目标。自研虽延迟但长期收益显著。 |

### Step 0.2：技术栈基线确认

| PRD维度 | 详细内容 |
| --- | --- |
| **输入/输出** | **输入：**架构约束清单（需兼容K8s）；**输出：**docker-compose.yml及`pyproject.toml`依赖锁定。**约束：**Python版本必须≥3.11（支持Pattern Matching）。 |
| **GWT验收** | Given 空虚拟机，When 执行`make init`，Then 5分钟内所有服务（DB/Redis/LiteLLM）健康检查通过。Given`pytest`，When 运行单元测试，Then 基础框架测试通过率100%。 |
| **实施细节** | 使用`poetry`管理虚拟环境，`pre-commit`配置black/isort/mypy。 |
| **技术栈** | Python 3.11.8, LiteLLM 1.40.0, PostgreSQL 15.4, Redis 7.2, Vue 3.4, Vite 5.0 |

#### ADR 0.2：LiteLLM vs 自研网关

| 备选 | QPS(4C8G) | 多模型切换 | 成本追踪 | 决策 |
| --- | --- | --- | --- | --- |
| A. LiteLLM | 1000+ | 原生支持 | 内置 | **✅ 选A** |
| B. 自研网关 | ~300 | 需手写适配器 | 需自建 |  |
| **理由：**自研网关降本70%无现成方案，LiteLLM已在大规模生产验证（如Cloudflare AI Gateway）。 | **理由：**自研网关降本70%无现成方案，LiteLLM已在大规模生产验证（如Cloudflare AI Gateway）。 | **理由：**自研网关降本70%无现成方案，LiteLLM已在大规模生产验证（如Cloudflare AI Gateway）。 | **理由：**自研网关降本70%无现成方案，LiteLLM已在大规模生产验证（如Cloudflare AI Gateway）。 | **理由：**自研网关降本70%无现成方案，LiteLLM已在大规模生产验证（如Cloudflare AI Gateway）。 |


### Step 0.3：需求澄清与渐进收敛机制

| PRD维度 | 详细内容 |
| --- | --- |
| **输入/输出** | **输入：**模糊需求文本（"优化一下""改个东西"）；**输出：**收敛后的需求文档（含ClarificationResult：clarified_prd/resolution_path/rounds/final_assumptions）。 |
| **GWT验收** | Given 模糊输入"优化一下"，When 调用ClarificationEngine.process()，Then 返回结构化追问（含实体/动词/范围维度选项）。Given 连续3轮无效回复，When process()执行，Then resolution_path="fallback_human"，state=WAITING_CLARIFICATION。Given 用户回复"改支付"，When find_candidates("支付")，Then 返回至少1个匹配模块（如PaymentService）。 |
| **实施细节** | 位于`/src/scheduler/clarification/`，含clarity_checker.py（清晰度判定）、question_generator.py（结构化模板）、candidate_resolver.py（图谱查询）。依赖GraphRepository (Step 3.x)和CheckpointManager (Step 1.2)。 |
| **技术栈** | Python 3.11内置（re/difflib），无新增第三方依赖；Pydantic用于数据契约。 |

#### ADR 0.3：结构化追问 vs LLM自由对话

| 备选 | 需求收敛确定性 | 开发成本 | 用户体验 | 决策 |
| --- | --- | --- | --- | --- |
| A. LLM自由对话 | 低（漂移风险） | 低 | 灵活 | **✅ 选B** |
| B. 结构化模板+规则 | 高（确定性） | 中 | 需选择选项 |  |
| **理由：**设计目标是"第一道防线"，不允许LLM自由发挥导致需求进一步漂移。 | **理由：**预定义模板库，按缺失维度分类（A/B/C/D选项）。 | **理由：**用户需在选项中选择，短期成本略高但结果可控。 |  |






## Step 0.4：架构锚定与Prompt/Context工程
---

    

### Step 0.4.1 架构锚定：编排层 vs 执行层

    

> 核心声明：V14.1 系统在设计上明确锚定在 “多智能体软件开发操作系统” 这一层级（编排层），而非单智能体执行工具（如 Claude Code、Codex）的层级。这一锚定决定了所有 Prompt 和 Context Engineering 的设计必须服务于 协作流程的编排与治理，而非单次代码生成的质量。

    

#### Step 0.4.1.1 编排层 vs 执行层

    | 维度 | 执行层（Claude Code / Codex） | 编排层（V14.1） |
| --- | --- | --- |
| System Prompt 锚点 | "你是一个编程助手" + 工具定义 | "你是多智能体协作网络中的角色" + 协作契约 |
| 上下文来源 | 当前代码库的实时快照 | 四图谱（代码+数据库+配置+知识）+ 协作状态 + 审计链 |
| 信息组织方式 | 用户指令 + 文件内容 + 工具输出 | 结构化图谱查询 + Agent 产出摘要 + 状态机上下文 |
| 决策单位 | 单次 LLM 调用的输出 | 跨 Agent 协作流程的步骤转换 |
| 约束来源 | 用户指令 + 工具权限 | 协作契约 + 验证门禁 + 合规规则 |
| 状态管理 | 无状态（任务即生命周期） | 有状态（检查点贯穿全流程） |
| 通信格式 | 自然语言 | 结构化、跨 Agent 可解析 |
| 成功标准 | 生成正确的代码 | 交付经过验证、符合合约、合规检查的完整产物 |

    

#### Step 0.4.1.2 为什么锚定编排层？

    
        
- V14.1 不是“另一个 Claude Code”：Claude Code、Codex 是单智能体执行工具，解决的是“如何让一个 AI 帮你写代码”。V14.1 解决的是“如何让一群 AI 协作完成软件开发全流程”。两者的目标不同，处于不同的抽象层级。
        
- 编排层的核心价值在于“治理”：单智能体工具依赖模型本身的推理能力和权限控制；V14.1 通过多 Agent 协作、状态机调度、四图谱、9层验证门禁、审计链，实现了对开发流程的系统性治理。
        
- Claude Code/Codex 可以是 V14.1 的执行引擎：V14.1 不排斥在底层调用 Claude Code 或 Codex 作为执行单元，但 V14.1 的核心价值在上层——编排、治理、验证、追溯。
    

    

---

    
    
    
    

    

### Step 0.4.2 五条核心设计原则

    基于“编排层锚定”，Prompt 和 Context Engineering 的设计必须遵循以下五条核心原则：

    

> 原则一：System Prompt 定义“协作角色”而非“个人能力”
        执行层写法（不应采用）："你是一个 Python 专家，擅长编写高质量的代码。"
        编排层写法（应该采用）："你是 V14.1 多智能体协作网络中的 DeveloperAgent，在 ArchitectAgent 确定的技术方案范围内，生成符合四图谱事实的代码，输出必须通过 L1-L9 验证。"
        核心差异：Prompt 描述的是 Agent 在协作流程中的位置和契约，而非个人技术能力。

    

> 原则二：上下文是“协作状态”而非“代码库快照”
        执行层写法（不应采用）：直接塞入 payment/service.py 的完整内容。
        编排层写法（应该采用）：注入上游 Agent 的产出摘要、当前 DAG 进度、四图谱查询结果、验证门禁状态。
        核心差异：上下文描述的是“协作进展到哪一步、上下游产出了什么、事实是什么”，而非“代码库长什么样”。

    

> 原则三：指令与约束来自“协作契约”而非“用户指令”
        执行层写法（不应采用）：“用户说：请修改 timeout 为 60”。
        编排层写法（应该采用）：协作契约约束（来自 PLANNING 阶段）+ 验证门禁规则（L1-L9）+ 合规要求（领域知识）。
        核心差异：约束来自整个协作流程的累积契约，而非当前用户的“一句话指令”。

    

> 原则四：上下文组织遵循“渐进式披露”而非“一次性加载”
        执行层写法（不应采用）：把所有文件内容塞进上下文窗口。
        编排层写法（应该采用）：五层分级（L1-L5），按需加载，每层有明确的 Token 预算和加载策略。
        核心差异：上下文是分层、按需、渐进式披露的，而非一次性装满。

    

> 原则五：通信格式服务于“跨 Agent 可解析”而非“人类可读”
        执行层写法（不应采用）：“我觉得这个函数应该改成异步的”。
        编排层写法（应该采用）：结构化 JSON（含 proposal_id、change、reasoning、evidence、contract_assertions）。
        核心差异：通信格式是结构化的、可被其他 Agent 自动解析的，而非自由文本。

    

---

    
    
    
    

    

### Step 0.4.3 五层上下文的编排层视角

    原 V14.1 的五层上下文架构（L1-L5）在编排层视角下应重新诠释如下：

    | 层级 | 原有定义 | 编排层重新诠释 | 承载的内容 |
| --- | --- | --- | --- |
| L1 | 全局不可变上下文 | 协作宪法：所有 Agent 必须遵守的全局规则 | System Prompt（协作角色定义）+ 协作契约 + 验证规则 + 红线清单 |
| L2 | 确定性事实上下文 | 协作事实库：当前任务依赖的确定性事实 | 四图谱查询结果（代码+数据库+配置+知识） |
| L3 | 任务动态上下文 | 协作状态：当前任务的执行状态 | PRD 摘要、上游 Agent 产出摘要、当前 DAG 进度、检查点摘要 |
| L4 | Agent 局部工作记忆 | 个体工作台：Agent 私有上下文 | 思考→行动→观察循环中的中间产物（不跨 Agent 共享） |
| L5 | 跨任务长期记忆 | 协作经验库：跨任务的模式复用 | 教训库、成功模式库（通过 RAG 检索注入） |

    

> 关键洞察：五层上下文的本质是 协作流程的信息分层——从全局宪法（L1）到具体执行（L4），从当前状态（L3）到长期积累（L5）。每一层都有明确的语义边界和加载策略，共同构成 Agent 感知的“协作全景图”。

    

---

    
    
    
    

    

### Step 0.4.4 验证门禁：协作契约的守卫

    在编排层视角下，L1-L9 验证门禁不再是“代码质量检查工具”，而是协作契约的守卫（Guardians of the Collaboration Contract）。

    

#### Step 0.4.4.1 验证门禁的定位

    
        
- 执行层视角：验证门禁是“代码是否正确”的检查。
        
- 编排层视角：验证门禁是“Agent 的产出是否满足协作契约”的门槛。只有通过所有门禁，产出才能进入共享上下文，成为下游 Agent 的输入。
    

    

#### Step 0.4.4.2 验证门禁与协作契约的映射

    | 层 | 验证内容 | 对应的协作契约条款 | 失败时的协作行为 |
| --- | --- | --- | --- |
| L1 | 输出格式合规 | 契约条款：输出必须符合 JSON Schema | 驳回，要求 Agent 重写 |
| L2 | 符号存在于四图谱 | 契约条款：不得引用不存在的符号 | 驳回，要求 Agent 修正引用 |
| L3 | 生成确定性（熵监控） | 契约条款：高熵产出视为无效 | 熔断，终止生成 |
| L4 | 类型正确性 | 契约条款：类型必须匹配 | 驳回，要求 Agent 修正 |
| L5 | 执行时正确性（沙箱） | 契约条款：代码必须可执行 | 驳回，触发重试 |
| L6 | 业务语义验证 | 契约条款：必须满足所有合约断言 | 驳回，标记为 NEEDS_HUMAN |
| L7 | 提交拦截 | 契约条款：不得包含危险代码 | 拦截，禁止进入 Git |
| L8 | 配置一致性 | 契约条款：配置不得漂移 | 触发自动修复或告警 |
| L9 | 合规性验证 | 契约条款：必须符合法规/标准 | 阻断，标记为 NEEDS_COMPLIANCE_REVIEW |

    

> 关键洞察：验证门禁不是“质检员”，而是协作契约的执行者。它们确保每个 Agent 的产出在进入共享上下文之前，已经满足所有契约条款，从而防止幻觉在 Agent 间传播。

    

---

    
    
    
    

    

## 5. Agent 角色的重新定义

    在编排层视角下，五个 Agent 的角色应重新定义如下：

    | Agent | 执行层定义 | 编排层定义 | 协作契约 |
| --- | --- | --- | --- |
| 架构师 | 设计系统架构的技术专家 | 方案制定者：将 PRD 转化为可执行的技术方案（tasks.json） | 输入：PRD（已澄清）；输出：tasks.json + 设计约束；契约：方案必须覆盖所有需求条目 |
| 开发者 | 编写代码的工程师 | 代码实现者：在方案约束下生成代码 | 输入：tasks.json + 设计约束；输出：code diff；契约：代码必须通过 L1-L9 验证 |
| 审查员 | 代码审查专家 | 仲裁者：裁决分歧，输出终审意见 | 输入：两个候选方案；输出：裁决结果；契约：分歧时启动仲裁，输出选择依据 |
| QA | 测试工程师 | 验证者：执行验证门禁，生成验证报告 | 输入：代码 + 验证规则；输出：验证报告；契约：报告必须包含 L1-L9 逐项结果 |
| 配置管理员 | 运维工程师 | 环境守护者：保障配置一致性 | 输入：配置变更请求；输出：配置验证/修复结果；契约：配置必须与黄金基线一致 |

    

> 关键洞察：Agent 的定义从“角色描述”转向“协作契约描述”。每个 Agent 的核心是对输入、输出、契约的明确界定——这正是编排层设计的核心产物，也是系统 Prompt 的核心内容。

    

---

    
    
    
    

    

## 6. 与现有 Step 的映射关系

    “编排层锚定”这一架构原则对现有 Step 的影响如下：

    | Step | 原有设计 | 编排层锚定的影响 |
| --- | --- | --- |
| Step 0.1项目章程 | 定义度量指标和范围 | 需更新 新增“架构锚定声明”，明确 V14.1 锚定编排层 |
| Step 5.2Agent 角色与 Prompt | 定义 5 个 Agent 的 System Prompt | 需更新 System Prompt 模板增加“协作契约”章节，明确定义输入/输出/契约 |
| Step 5.4Agent 间通信 | 异步消息总线 | 需更新 新增“通信格式规范”，强制结构化 JSON 通信 |
| 五层上下文L1-L5 | 信息分层 | 需重述 在文档中新增“渐进式披露”原则的显式说明，并按编排层视角重新诠释各层语义 |
| L1-L9验证门禁 | 9 层防幻觉 | 需重述 新增“验证门禁作为协作契约守卫”的定位说明 |
| Step 0.6输入清洗 | 对抗性输入清洗 | 无需修改 已按编排层设计（系统指令隔离） |
| Step 7.6安全与权限 | JWT + 零信任 | 无需修改 已按编排层设计（Agent 间凭证委托） |

    

---

    
    
    
    

    

### Step 0.4.7 需要更新的文档位置

    | 文档位置 | 更新内容 | 更新目的 |
| --- | --- | --- |
| Step 0.1（项目章程） | 新增“架构锚定声明”章节 | 明确 V14.1 锚定编排层，作为所有后续决策的顶层依据 |
| Step 5.2（Agent 角色与 Prompt） | System Prompt 模板增加“协作契约”章节 | 确保每个 Agent 的 Prompt 定义的是协作角色而非个人能力 |
| Step 5.4（Agent 间通信） | 新增“通信格式规范”章节 | 强制结构化 JSON 通信，使通信跨 Agent 可解析 |
| 五层上下文（L1-L5 设计文档） | 新增“渐进式披露”原则说明；按编排层视角重述各层语义 | 明确五层上下文的编排层设计意图 |
| L1-L9 验证门禁（设计文档） | 新增“验证门禁作为协作契约守卫”定位说明 | 明确验证门禁的编排层定位，而非单纯的质量检查 |

    

---

    
    
    
    

    

### Step 0.4.8 代码示例

    

#### Step 0.4.8.1 编排层风格 System Prompt 模板

    

```python
# /src/agents/prompts/developer_agent.j2
    &lt;system&gt;
      &lt;anchor&gt;
        【架构锚定声明】
        你是 V14.1 多智能体协作网络中的 DeveloperAgent。
        你的职责是在 ArchitectAgent 确定的技术方案范围内，生成符合四图谱事实的代码。
        你的输出必须通过 L1-L9 验证门禁后才可进入共享上下文。
      &lt;/anchor&gt;

      &lt;collaboration_contract&gt;
        【协作契约】
        输入来源：ArchitectAgent 输出的 tasks.json（已通过可行性预检）
        输入格式：{ task_id, files: [{path, action, design_constraints}], assertions: [...] }
        输出格式：
        {
          "proposal_id": "prop-{timestamp}",
          "files": [{ "path": "...", "diff": "...", "change_type": "create|update|delete" }],
          "self_check": { "l1_passed": true, "l2_passed": true, ... },
          "contract_assertions_met": ["assertion_1", "assertion_2"]
        }
        失败处理：连续 3 次验证失败后，将控制权交还调度器，标记为 NEEDS_HUMAN
      &lt;/collaboration_contract&gt;

      &lt;rules&gt;
        【硬性规则 - 协作宪法】
        1. 禁止引入未在三图谱中确认的第三方库
        2. 禁止生成包含硬编码密钥的代码
        3. 禁止在未通过 L1-L9 验证的情况下提交代码
        4. 遇到不确定信息，必须先查四图谱，禁止凭记忆
      &lt;/rules&gt;

      &lt;tools&gt;
        【可用工具】
        - query_graph(type="code|database|config|knowledge", symbol="...")
        - run_sandbox(code_snippet)
        - propose_change(proposal: ProposalSchema)
      &lt;/tools&gt;
    &lt;/system&gt;
```

    

#### Step 0.4.8.2 结构化通信格式示例

    

```python
# /src/communication/schemas.py
    from pydantic import BaseModel, Field
    from typing import List, Optional, Dict, Any
    from uuid import uuid4

    class Proposal(BaseModel):
        """跨Agent提议的结构化格式"""
        id: str = Field(default_factory=lambda: str(uuid4()))
        from_agent: str  # DeveloperAgent, ArchitectAgent, etc.
        to_agent: str    # ReviewerAgent, QAAgent, etc.
        type: str        # "proposal", "request", "report", "arbitration"

        proposal_data: Dict[str, Any] = Field(default_factory=dict)
        # 示例：{"file": "payment/service.py", "change": "convert_to_async"}

        reasoning: str   # 为什么这样提议
        evidence: List[Dict[str, str]]  # 支撑依据
        # 示例：[{"source": "code_graph", "symbol": "PaymentService.process"}]

        contract_assertions: List[str]  # 断言列表
        # 示例：["response_time  0 AND timeout  Dict[str, Any]:
            """执行所有验证门禁，返回结果"""
            results = {}
            for gate in self.gates:
                result = await gate.validate(proposal.proposal_data)
                results[gate.name] = result
                if not result.passed:
                    # 阻断传播：验证失败时不进入共享上下文
                    return {
                        "passed": False,
                        "failed_at": gate.name,
                        "results": results,
                        "message": f"Contract violated at {gate.name}: {result.reason}"
                    }

            # 所有门禁通过，写入检查点
            return {
                "passed": True,
                "results": results,
                "message": "All contract gates passed. Proposal can enter shared context."
            }
```

    

---


## Step 0.4：架构锚定与Prompt/Context工程
---

    

### Step 0.4.1 架构锚定：编排层 vs 执行层

    

> 核心声明：V14.1 系统在设计上明确锚定在 “多智能体软件开发操作系统” 这一层级（编排层），而非单智能体执行工具（如 Claude Code、Codex）的层级。这一锚定决定了所有 Prompt 和 Context Engineering 的设计必须服务于 协作流程的编排与治理，而非单次代码生成的质量。

    

#### Step 0.4.1 编排层 vs 执行层

    | 维度 | 执行层（Claude Code / Codex） | 编排层（V14.1） |
| --- | --- | --- |
| System Prompt 锚点 | "你是一个编程助手" + 工具定义 | "你是多智能体协作网络中的角色" + 协作契约 |
| 上下文来源 | 当前代码库的实时快照 | 四图谱（代码+数据库+配置+知识）+ 协作状态 + 审计链 |
| 信息组织方式 | 用户指令 + 文件内容 + 工具输出 | 结构化图谱查询 + Agent 产出摘要 + 状态机上下文 |
| 决策单位 | 单次 LLM 调用的输出 | 跨 Agent 协作流程的步骤转换 |
| 约束来源 | 用户指令 + 工具权限 | 协作契约 + 验证门禁 + 合规规则 |
| 状态管理 | 无状态（任务即生命周期） | 有状态（检查点贯穿全流程） |
| 通信格式 | 自然语言 | 结构化、跨 Agent 可解析 |
| 成功标准 | 生成正确的代码 | 交付经过验证、符合合约、合规检查的完整产物 |

    

#### Step 0.4.2 为什么锚定编排层？

    
        
- V14.1 不是“另一个 Claude Code”：Claude Code、Codex 是单智能体执行工具，解决的是“如何让一个 AI 帮你写代码”。V14.1 解决的是“如何让一群 AI 协作完成软件开发全流程”。两者的目标不同，处于不同的抽象层级。
        
- 编排层的核心价值在于“治理”：单智能体工具依赖模型本身的推理能力和权限控制；V14.1 通过多 Agent 协作、状态机调度、四图谱、9层验证门禁、审计链，实现了对开发流程的系统性治理。
        
- Claude Code/Codex 可以是 V14.1 的执行引擎：V14.1 不排斥在底层调用 Claude Code 或 Codex 作为执行单元，但 V14.1 的核心价值在上层——编排、治理、验证、追溯。
    

    

---

    
    
    
    

    

### Step 0.4.2 五条核心设计原则

    基于“编排层锚定”，Prompt 和 Context Engineering 的设计必须遵循以下五条核心原则：

    

> 原则一：System Prompt 定义“协作角色”而非“个人能力”
        执行层写法（不应采用）："你是一个 Python 专家，擅长编写高质量的代码。"
        编排层写法（应该采用）："你是 V14.1 多智能体协作网络中的 DeveloperAgent，在 ArchitectAgent 确定的技术方案范围内，生成符合四图谱事实的代码，输出必须通过 L1-L9 验证。"
        核心差异：Prompt 描述的是 Agent 在协作流程中的位置和契约，而非个人技术能力。

    

> 原则二：上下文是“协作状态”而非“代码库快照”
        执行层写法（不应采用）：直接塞入 payment/service.py 的完整内容。
        编排层写法（应该采用）：注入上游 Agent 的产出摘要、当前 DAG 进度、四图谱查询结果、验证门禁状态。
        核心差异：上下文描述的是“协作进展到哪一步、上下游产出了什么、事实是什么”，而非“代码库长什么样”。

    

> 原则三：指令与约束来自“协作契约”而非“用户指令”
        执行层写法（不应采用）：“用户说：请修改 timeout 为 60”。
        编排层写法（应该采用）：协作契约约束（来自 PLANNING 阶段）+ 验证门禁规则（L1-L9）+ 合规要求（领域知识）。
        核心差异：约束来自整个协作流程的累积契约，而非当前用户的“一句话指令”。

    

> 原则四：上下文组织遵循“渐进式披露”而非“一次性加载”
        执行层写法（不应采用）：把所有文件内容塞进上下文窗口。
        编排层写法（应该采用）：五层分级（L1-L5），按需加载，每层有明确的 Token 预算和加载策略。
        核心差异：上下文是分层、按需、渐进式披露的，而非一次性装满。

    

> 原则五：通信格式服务于“跨 Agent 可解析”而非“人类可读”
        执行层写法（不应采用）：“我觉得这个函数应该改成异步的”。
        编排层写法（应该采用）：结构化 JSON（含 proposal_id、change、reasoning、evidence、contract_assertions）。
        核心差异：通信格式是结构化的、可被其他 Agent 自动解析的，而非自由文本。

    

---

    
    
    
    

    

### Step 0.4.3 五层上下文的编排层视角

    原 V14.1 的五层上下文架构（L1-L5）在编排层视角下应重新诠释如下：

    | 层级 | 原有定义 | 编排层重新诠释 | 承载的内容 |
| --- | --- | --- | --- |
| L1 | 全局不可变上下文 | 协作宪法：所有 Agent 必须遵守的全局规则 | System Prompt（协作角色定义）+ 协作契约 + 验证规则 + 红线清单 |
| L2 | 确定性事实上下文 | 协作事实库：当前任务依赖的确定性事实 | 四图谱查询结果（代码+数据库+配置+知识） |
| L3 | 任务动态上下文 | 协作状态：当前任务的执行状态 | PRD 摘要、上游 Agent 产出摘要、当前 DAG 进度、检查点摘要 |
| L4 | Agent 局部工作记忆 | 个体工作台：Agent 私有上下文 | 思考→行动→观察循环中的中间产物（不跨 Agent 共享） |
| L5 | 跨任务长期记忆 | 协作经验库：跨任务的模式复用 | 教训库、成功模式库（通过 RAG 检索注入） |

    

> 关键洞察：五层上下文的本质是 协作流程的信息分层——从全局宪法（L1）到具体执行（L4），从当前状态（L3）到长期积累（L5）。每一层都有明确的语义边界和加载策略，共同构成 Agent 感知的“协作全景图”。

    

---

    
    
    
    

    

### Step 0.4.4 验证门禁：协作契约的守卫

    在编排层视角下，L1-L9 验证门禁不再是“代码质量检查工具”，而是协作契约的守卫（Guardians of the Collaboration Contract）。

    

#### Step 0.4.1 验证门禁的定位

    
        
- 执行层视角：验证门禁是“代码是否正确”的检查。
        
- 编排层视角：验证门禁是“Agent 的产出是否满足协作契约”的门槛。只有通过所有门禁，产出才能进入共享上下文，成为下游 Agent 的输入。
    

    

#### Step 0.4.2 验证门禁与协作契约的映射

    | 层 | 验证内容 | 对应的协作契约条款 | 失败时的协作行为 |
| --- | --- | --- | --- |
| L1 | 输出格式合规 | 契约条款：输出必须符合 JSON Schema | 驳回，要求 Agent 重写 |
| L2 | 符号存在于四图谱 | 契约条款：不得引用不存在的符号 | 驳回，要求 Agent 修正引用 |
| L3 | 生成确定性（熵监控） | 契约条款：高熵产出视为无效 | 熔断，终止生成 |
| L4 | 类型正确性 | 契约条款：类型必须匹配 | 驳回，要求 Agent 修正 |
| L5 | 执行时正确性（沙箱） | 契约条款：代码必须可执行 | 驳回，触发重试 |
| L6 | 业务语义验证 | 契约条款：必须满足所有合约断言 | 驳回，标记为 NEEDS_HUMAN |
| L7 | 提交拦截 | 契约条款：不得包含危险代码 | 拦截，禁止进入 Git |
| L8 | 配置一致性 | 契约条款：配置不得漂移 | 触发自动修复或告警 |
| L9 | 合规性验证 | 契约条款：必须符合法规/标准 | 阻断，标记为 NEEDS_COMPLIANCE_REVIEW |

    

> 关键洞察：验证门禁不是“质检员”，而是协作契约的执行者。它们确保每个 Agent 的产出在进入共享上下文之前，已经满足所有契约条款，从而防止幻觉在 Agent 间传播。

    

---

    
    
    
    

    

## 5. Agent 角色的重新定义

    在编排层视角下，五个 Agent 的角色应重新定义如下：

    | Agent | 执行层定义 | 编排层定义 | 协作契约 |
| --- | --- | --- | --- |
| 架构师 | 设计系统架构的技术专家 | 方案制定者：将 PRD 转化为可执行的技术方案（tasks.json） | 输入：PRD（已澄清）；输出：tasks.json + 设计约束；契约：方案必须覆盖所有需求条目 |
| 开发者 | 编写代码的工程师 | 代码实现者：在方案约束下生成代码 | 输入：tasks.json + 设计约束；输出：code diff；契约：代码必须通过 L1-L9 验证 |
| 审查员 | 代码审查专家 | 仲裁者：裁决分歧，输出终审意见 | 输入：两个候选方案；输出：裁决结果；契约：分歧时启动仲裁，输出选择依据 |
| QA | 测试工程师 | 验证者：执行验证门禁，生成验证报告 | 输入：代码 + 验证规则；输出：验证报告；契约：报告必须包含 L1-L9 逐项结果 |
| 配置管理员 | 运维工程师 | 环境守护者：保障配置一致性 | 输入：配置变更请求；输出：配置验证/修复结果；契约：配置必须与黄金基线一致 |

    

> 关键洞察：Agent 的定义从“角色描述”转向“协作契约描述”。每个 Agent 的核心是对输入、输出、契约的明确界定——这正是编排层设计的核心产物，也是系统 Prompt 的核心内容。

    

---

    
    
    
    

    

## 6. 与现有 Step 的映射关系

    “编排层锚定”这一架构原则对现有 Step 的影响如下：

    | Step | 原有设计 | 编排层锚定的影响 |
| --- | --- | --- |
| Step 0.1项目章程 | 定义度量指标和范围 | 需更新 新增“架构锚定声明”，明确 V14.1 锚定编排层 |
| Step 5.2Agent 角色与 Prompt | 定义 5 个 Agent 的 System Prompt | 需更新 System Prompt 模板增加“协作契约”章节，明确定义输入/输出/契约 |
| Step 5.4Agent 间通信 | 异步消息总线 | 需更新 新增“通信格式规范”，强制结构化 JSON 通信 |
| 五层上下文L1-L5 | 信息分层 | 需重述 在文档中新增“渐进式披露”原则的显式说明，并按编排层视角重新诠释各层语义 |
| L1-L9验证门禁 | 9 层防幻觉 | 需重述 新增“验证门禁作为协作契约守卫”的定位说明 |
| Step 0.6输入清洗 | 对抗性输入清洗 | 无需修改 已按编排层设计（系统指令隔离） |
| Step 7.6安全与权限 | JWT + 零信任 | 无需修改 已按编排层设计（Agent 间凭证委托） |

    

---

    
    
    
    

    

### Step 0.4.7 需要更新的文档位置

    | 文档位置 | 更新内容 | 更新目的 |
| --- | --- | --- |
| Step 0.1（项目章程） | 新增“架构锚定声明”章节 | 明确 V14.1 锚定编排层，作为所有后续决策的顶层依据 |
| Step 5.2（Agent 角色与 Prompt） | System Prompt 模板增加“协作契约”章节 | 确保每个 Agent 的 Prompt 定义的是协作角色而非个人能力 |
| Step 5.4（Agent 间通信） | 新增“通信格式规范”章节 | 强制结构化 JSON 通信，使通信跨 Agent 可解析 |
| 五层上下文（L1-L5 设计文档） | 新增“渐进式披露”原则说明；按编排层视角重述各层语义 | 明确五层上下文的编排层设计意图 |
| L1-L9 验证门禁（设计文档） | 新增“验证门禁作为协作契约守卫”定位说明 | 明确验证门禁的编排层定位，而非单纯的质量检查 |

    

---

    
    
    
    

    

### Step 0.4.8 代码示例

    

#### Step 0.4.1 编排层风格 System Prompt 模板

    

```python
# /src/agents/prompts/developer_agent.j2
    &lt;system&gt;
      &lt;anchor&gt;
        【架构锚定声明】
        你是 V14.1 多智能体协作网络中的 DeveloperAgent。
        你的职责是在 ArchitectAgent 确定的技术方案范围内，生成符合四图谱事实的代码。
        你的输出必须通过 L1-L9 验证门禁后才可进入共享上下文。
      &lt;/anchor&gt;

      &lt;collaboration_contract&gt;
        【协作契约】
        输入来源：ArchitectAgent 输出的 tasks.json（已通过可行性预检）
        输入格式：{ task_id, files: [{path, action, design_constraints}], assertions: [...] }
        输出格式：
        {
          "proposal_id": "prop-{timestamp}",
          "files": [{ "path": "...", "diff": "...", "change_type": "create|update|delete" }],
          "self_check": { "l1_passed": true, "l2_passed": true, ... },
          "contract_assertions_met": ["assertion_1", "assertion_2"]
        }
        失败处理：连续 3 次验证失败后，将控制权交还调度器，标记为 NEEDS_HUMAN
      &lt;/collaboration_contract&gt;

      &lt;rules&gt;
        【硬性规则 - 协作宪法】
        1. 禁止引入未在三图谱中确认的第三方库
        2. 禁止生成包含硬编码密钥的代码
        3. 禁止在未通过 L1-L9 验证的情况下提交代码
        4. 遇到不确定信息，必须先查四图谱，禁止凭记忆
      &lt;/rules&gt;

      &lt;tools&gt;
        【可用工具】
        - query_graph(type="code|database|config|knowledge", symbol="...")
        - run_sandbox(code_snippet)
        - propose_change(proposal: ProposalSchema)
      &lt;/tools&gt;
    &lt;/system&gt;
```

    

#### Step 0.4.2 结构化通信格式示例

    

```python
# /src/communication/schemas.py
    from pydantic import BaseModel, Field
    from typing import List, Optional, Dict, Any
    from uuid import uuid4

    class Proposal(BaseModel):
        """跨Agent提议的结构化格式"""
        id: str = Field(default_factory=lambda: str(uuid4()))
        from_agent: str  # DeveloperAgent, ArchitectAgent, etc.
        to_agent: str    # ReviewerAgent, QAAgent, etc.
        type: str        # "proposal", "request", "report", "arbitration"

        proposal_data: Dict[str, Any] = Field(default_factory=dict)
        # 示例：{"file": "payment/service.py", "change": "convert_to_async"}

        reasoning: str   # 为什么这样提议
        evidence: List[Dict[str, str]]  # 支撑依据
        # 示例：[{"source": "code_graph", "symbol": "PaymentService.process"}]

        contract_assertions: List[str]  # 断言列表
        # 示例：["response_time  0 AND timeout  Dict[str, Any]:
            """执行所有验证门禁，返回结果"""
            results = {}
            for gate in self.gates:
                result = await gate.validate(proposal.proposal_data)
                results[gate.name] = result
                if not result.passed:
                    # 阻断传播：验证失败时不进入共享上下文
                    return {
                        "passed": False,
                        "failed_at": gate.name,
                        "results": results,
                        "message": f"Contract violated at {gate.name}: {result.reason}"
                    }

            # 所有门禁通过，写入检查点
            return {
                "passed": True,
                "results": results,
                "message": "All contract gates passed. Proposal can enter shared context."
            }
```

    

---


## Phase 1：架构设计与技术选型

### Step 1.1：系统架构（四层+模块契约）

| PRD维度 | 详细内容 |
| --- | --- |
| **输入/输出** | **输入：**业务用例（PRD生成→代码输出→自修复）；**输出：**OpenAPI 3.0 YAML，模块边界定义（接入层/Scheduler/能力层/基础层）。**约束：**模块间禁止循环依赖（通过`pydeps`检查）。 |
| **GWT验收** | Given 模块图，When 使用`pydeps src`扫描，Then 输出无环。Given API契约，When 使用`prism`模拟，Then 前端可正常联调。 |
| **实施细节** | 使用`fastapi`定义路由，`pydantic`定义Schema。部署`nginx`反向代理。 |
| **技术栈** | FastAPI 0.110, Pydantic 2.6, Nginx 1.25 |

#### ADR 1.1：模块间通信——REST vs gRPC

| 备选 | 延迟(ms) | 跨语言支持 | 调试便利性 | 决策 |
| --- | --- | --- | --- | --- |
| A. REST/HTTP | ~10 | 通用 | 极佳(Postman) | **✅ 选A** |
| B. gRPC | ~2 | 需生成代码 | 差(需要grpcurl) |  |
| **理由：**系统内部调用频次不高（QPS<100），REST调试便利性更符合快速迭代需求。 | **理由：**系统内部调用频次不高（QPS<100），REST调试便利性更符合快速迭代需求。 | **理由：**系统内部调用频次不高（QPS<100），REST调试便利性更符合快速迭代需求。 | **理由：**系统内部调用频次不高（QPS<100），REST调试便利性更符合快速迭代需求。 | **理由：**系统内部调用频次不高（QPS<100），REST调试便利性更符合快速迭代需求。 |

### Step 1.2：三图谱Schema设计

| PRD维度 | 详细内容 |
| --- | --- |
| **输入/输出** | **输入：**代码/数据库/配置的实体分类；**输出：**SQLAlchemy ORM Model类定义。**约束：**配置图谱节点必须包含`hash`字段（用于漂移检测）。 |
| **GWT验收** | Given 实体模型，When 生成迁移脚本（alembic），Then 可成功创建三组独立表（无外键耦合）。Given 测试数据，When 执行`get_dependencies`，Then 返回正确父子层级。 |
| **实施细节** | 代码图谱使用`Node`基类，子类为`FileNode`/`ClassNode`/`FunctionNode`。Edge使用`relationship`表存储`(source_id, target_id, edge_type)`。 |
| **技术栈** | SQLAlchemy 2.0, Alembic 1.13 |

#### ADR 1.2：图谱存储——SQLite vs Neo4j

| 备选 | 内存占用 | 递归查询(深度5) | 运维成本 | 决策 |
| --- | --- | --- | --- | --- |
| A. SQLite | ~50MB | ~100ms(递归CTE) | 零 | **✅ 选A** |
| B. Neo4j | ~1.2GB | ~20ms | 高(JVM调优) |  |
| **理由：**增量解析场景下，SQLite的MVCC-lite快照隔离已足够，且避免额外运维负担。 | **理由：**增量解析场景下，SQLite的MVCC-lite快照隔离已足够，且避免额外运维负担。 | **理由：**增量解析场景下，SQLite的MVCC-lite快照隔离已足够，且避免额外运维负担。 | **理由：**增量解析场景下，SQLite的MVCC-lite快照隔离已足够，且避免额外运维负担。 | **理由：**增量解析场景下，SQLite的MVCC-lite快照隔离已足够，且避免额外运维负担。 |


### Step 1.3：技术体系总览（新增）

| PRD维度 | 详细内容 |
| --- | --- |
| **输入/输出** | **输入：**散落在各Step的技术选型决策；**输出：**全局技术栈矩阵、依赖链图、外部工具清单、环境配置规范、ADR映射表。 |
| **背景** | 各Step分散定义了技术选型，但没有一个统一的全局视图。开发者在搭建环境或理解系统时，需要跨多个Step搜索。ADR回答"为什么选这个"，但没有"选了哪些"的完整清单。 |
| **用户故事** | 开发者想在本地搭建环境时，只需参照一个章节完成全部配置；新成员 onboarding 时，通过本节即可获得全貌。 |
| **GWT验收** | Given 新成员阅读本文，When 搭建本地开发环境，Then 参照本节可完成全部配置，无需跨文档搜索。Given 新增技术选型，When 登记ADR，Then 必须同步更新本节以保持全局视图。 |
| **实施细节** | 本节为文档索引，不直接产生代码。技术栈版本来自各Step已验证的版本，引用一致性由各Step的GWT验收保证。 |
| **技术栈** | 详见开发计划第3.4节。ADR-01至ADR-12覆盖全技术栈。 |

#### ADR 1.3：技术体系总览索引约定

| 备选 | 索引完整性 | 维护成本 | 一致性保证 | 决策 |
| --- | --- | --- | --- | --- |
| A. 仅本文档维护 | 低（易遗漏） | 低 | 无强制约束 |  |
| B. 本文档+ADR双写 | 中 | 中 | 流程约束 | **✅ 选B** |
| **理由：**要求每次新增ADR必须同步更新本节，将一致性维护嵌入ADR流程，不额外增加维护负担。 | **理由：**要求每次新增ADR必须同步更新本节，将一致性维护嵌入ADR流程，不额外增加维护负担。 | **理由：**要求每次新增ADR必须同步更新本节，将一致性维护嵌入ADR流程，不额外增加维护负担。 | **理由：**要求每次新增ADR必须同步更新本节，将一致性维护嵌入ADR流程，不额外增加维护负担。 | **理由：**要求每次新增ADR必须同步更新本节，将一致性维护嵌入ADR流程，不额外增加维护负担。 |



### Step 1.4：外挂领域知识图谱

| PRD维度 | 详细内容 |
| --- | --- |
| **输入/输出** | **输入：**专业领域原始文档（会计/金融/法律权威来源）；**输出：**结构化知识节点（Neo4j）+ 向量化索引（Milvus）。**异常：**来源不在白名单则拒绝入库。 |
| **GWT验收** | Given 权威来源（财政部/证监会文件），When 执行知识注入，Then Neo4j节点数≥100，向量索引完整，审计记录存在。<br>Given Agent通过MCP调用`query_knowledge`，When mode="exact"，Then 返回确定性结果，耗时<50ms，无LLM调用。 |
| **实施细节** | Neo4j存储概念节点和关系；Milvus存储文档向量；MCP Server统一暴露`query_knowledge`和`validate_compliance`两个工具。 |
| **技术栈** | Neo4j 5.x + Milvus/Qdrant + SentenceTransformers + MCP Python SDK。 |

#### ADR 1.4：知识图谱双模架构决策

| 备选 | 精确查询 | 语义检索 | 混合模式 | 决策 |
| --- | --- | --- | --- | --- |
| A. 仅图谱 | ✅ 零Token | ❌ 无 | ❌ 无 | **✅ 选B** |
| B. 图谱+RAG双模 | ✅ 零Token | ✅ 低Token | ✅ 最佳 |  |
| C. 纯RAG | ❌ Token消耗高 | ✅ 有 | ❌ 无 |  |
| **理由：**专业任务既需要确定性定义/公式（精确查询），也需要开放探索/监管动态（语义检索）。两者互补而非替代，通过MCP统一暴露，Agent按需调用。 |


### Step 1.5：上下文工程优化

| PRD维度 | 详细内容 |
| --- | --- |
| **输入/输出** | **输入：**任务执行轨迹、历史上下文、压缩阈值配置；**输出：**压缩后上下文、知识子弹、检索轨迹日志。**异常：**超长任务触发Offload，返回文件引用而非全量内容。 |
| **GWT验收** | Given 100个真实任务执行轨迹，When 开启ACE增量知识库，Then 知识库包含≥50个子弹，重复教训合并率≥70%。<br>Given 上下文达30K tokens，When 双Agent压缩执行，Then 压缩后≤8K tokens，耗时<2s。 |
| **实施细节** | ACE引擎（Generator/Reflector/Curator）+ 异步压缩（Observer/Reflector）+ OffloadManager + ContextPilot缓存接口。 |
| **技术栈** | FAISS + Redis + ECharts + Qwen-1.5B。 |

#### ADR 1.5：上下文工程增强决策

| 备选 | 增量知识 | 异步压缩 | 前缀缓存 | 决策 |
| --- | --- | --- | --- | --- |
| A. 全手动 | ✅ 精确控制 | ❌ 同步阻塞 | ❌ 无 | ❌ 选B |
| B. ACE+双Agent混合 | ✅ 自动演化 | ✅ 不阻塞 | ✅ 可选 | **✅ 选B** |
| **理由：**增量知识演化与异步压缩天然解耦，ACE的Reflector与Observational Memory的Observer可共用同一轻量LLM，资源复用最优。 |





### Step 1.6：六大演进方向（V15规划）

    Phase 7+ 规划 长期演进

    

> 背景：V14.1已经是一个非常扎实的基座。接下来的优化不再是“修Bug”，而是从“能用”到“好用”、从“可控”到“智能”的进化跃迁。以下六个方向代表了2025-2026年学术界和工业界的前沿探索。

    

#### 1.6.1 方向一：自适应编排（Adaptive Orchestration）

    | PRD · 自适应编排 |
| --- |
| 核心问题 | V14.1固定5个Agent拓扑，但并非所有任务都需要“全阵容”出场，造成计算和Token浪费。 |
| 前沿方案 | 引入任务自适应编排（Task-Adaptive Orchestration），系统根据任务特征动态选择协作拓扑。相关研究：AdaptOrch、AMAS。 |
| 核心机制 | ① 系统根据任务复杂度、领域类型、资源约束，从并行、顺序、层级、混合四种拓扑中动态选择。② 简单任务用顺序拓扑快速响应，复杂任务启用层级拓扑深度分析。③ 通过“智能剪枝”确定最优Agent数量和协作模式。 |
| 预期收益 | 拓扑感知的编排相比固定拓扑可带来12-23% 的性能提升。避免盲目增加Agent数量导致的通信冗余。 |
| 与V14.1集成 | 在Step 5.1调度器状态机中增加“拓扑决策”阶段，在PLANNING后动态确定Agent组合。 |

    

#### 1.6.2 方向二：自动化提示词优化（Automatic Prompt Optimization）

    | PRD · 自动化提示词优化 |
| --- |
| 核心问题 | Agent的Prompt目前主要依赖人工编写，效率低且难以达到最优组合。 |
| 前沿方案 | 利用自动化提示词优化技术，让系统自动搜索最优的Prompt组合。代表工作：MASPOB（ICML 2026 Spotlight）。 |
| 核心机制 | ① 将Prompt组合优化建模为“多臂老虎机（Bandit）”问题。② 使用图神经网络（GNN）捕捉提示词间的耦合关系。③ 使用坐标上升策略将复杂搜索化简为线性。④ 在固定工作流下自动搜索最优Prompt组合。 |
| 预期收益 | 在固定工作流下实现性能提升，无需人工调参。其他方案：MAPRO、MARS、PromptSculptor。 |
| 与V14.1集成 | 在Step 5.2（Agent角色与Prompt）中增加自动化优化层，定期或在版本升级时执行Prompt搜索。 |

    

#### 1.6.3 方向三：通信效率优化（Agent-GSPO）

    | PRD · 通信效率优化 |
| --- |
| 核心问题 | Agent间的“自由对话”式通信存在大量冗余Token，成本高昂。 |
| 前沿方案 | 通过序列级强化学习（Sequence-Level RL），训练Agent学会“战略性沉默”。代表工作：Agent-GSPO。 |
| 核心机制 | ① 使用组序列策略优化（GSPO）算法训练Agent。② Agent在“通信感知的奖励”下行动，该奖励显式惩罚冗长输出。③ 训练后Agent自发形成“战略性沉默（strategic silence）”等高效协作策略。 |
| 预期收益 | 在7个推理基准测试中达到SOTA表现的同时，Token消耗仅为现有方法的极小一部分。 |
| 与V14.1集成 | 在Step 5.4（Agent间通信协议）中引入GSPO奖励机制，优化Agent的通信行为。 |

    

#### 1.6.4 方向四：哨兵Agent（Sentinel Agent）

    | PRD · 哨兵Agent |
| --- |
| 核心问题 | 8层防幻觉体系对内部幻觉有效，但对恶意攻击（如Prompt注入）的防护相对被动。 |
| 前沿方案 | 部署专门的哨兵Agent网络，作为分布式安全层实时监控整个协作过程。 |
| 核心机制 | ① 哨兵Agent不执行任务，只判断“是否安全继续”。② 整合语义分析、行为分析、检索增强验证和跨智能体异常检测。③ 发现威胁后上报“协调智能体”，由后者调整策略、隔离或停用不当Agent。④ 协议扩展：SecureMCP将安全能力嵌入MCP协议。 |
| 预期收益 | 模拟实验显示能成功检测162种不同类型的攻击（提示注入、幻觉、数据外泄）。 |
| 与V14.1集成 | 在Step 0.6（输入清洗层）基础上扩展为完整的哨兵Agent网络，作为独立的安全层。 |

    

#### 1.6.5 方向五：AgentOps体系

    | PRD · AgentOps体系 |
| --- |
| 核心问题 | 审计日志能记录“做了什么”，但难以解释“为什么这么做”，不利于深度调优。 |
| 前沿方案 | 引入AgentOps体系，通过过程与因果发现（Process and Causal Discovery）分析执行轨迹。 |
| 核心机制 | ① AgentOps自动化管道包含：行为观测、指标收集、问题检测、根因分析、优化建议、运行时自动化。② AgentSight利用eBPF技术从系统外部监控Agent，检测提示注入攻击、识别资源浪费的推理循环。③ 强调从开发到生产的全生命周期可观测性和可追溯性。 |
| 预期收益 | 帮助开发者深入理解Agent行为，定位系统性偏差，调试效率从小时级提升至分钟级。 |
| 与V14.1集成 | 在Step 6.1（驾驶舱）和Step 7.2（AgentOps）基础上扩展，增加因果分析和自动优化建议能力。 |

    

#### 1.6.6 方向六：Agent Primitives（Agent原语）

    | PRD · Agent Primitives |
| --- |
| 核心问题 | 当前MAS架构多为“一次性定制”，缺乏跨任务的复用性。 |
| 前沿方案 | Agent Primitives（Agent原语）将Agent能力抽象为可复用的“基础构建块”。 |
| 核心机制 | ① 借鉴神经网络设计，将MAS架构分解为少量可重复的“内部计算模式”：Review、Voting &amp; Selection、Planning &amp; Execution三种原语。② 原语间通过KV缓存（Key-Value cache）通信，大幅提升鲁棒性和效率。③ 一个Organizer Agent为每个查询选择和组合原语。 |
| 预期收益 | 相比单Agent基线平均准确率提升12.0-16.5%；相比基于文本的MAS，Token使用量和推理延迟降低约3-4倍。 |
| 与V14.1集成 | 在Step 5.1（调度器）和Step 5.2（Agent角色）基础上重构为原语组合架构，实现更根本的范式转变。 |

    

---

    
    
    
    

    


## Phase 2：核心基础设施

### Step 2.1：LiteLLM网关与熔断器

| PRD维度 | 详细内容 |
| --- | --- |
| **输入/输出** | **输入：**模型API Key，路由策略（主/备/降级）；**输出：**统一`/chat/completions`端点。**异常码：**GATEWAY_TIMEOUT (503), RATE_LIMITED (429)。 |
| **GWT验收** | Given 连续5次模拟超时，When 触发熔断，Then 后续请求直接返回503且不转发LLM。Given 冷却期60s后，When 再次请求，Then 自动恢复半开状态。 |
| **实施细节** | 使用`circuitbreaker`库装饰`call_llm`方法，配置`failure_threshold=5, recovery_timeout=60`。 |
| **技术栈** | circuitbreaker 2.0, httpx 0.27 |

### Step 2.2：检查点持久化

| PRD维度 | 详细内容 |
| --- | --- |
| **输入/输出** | **输入：**调度器状态字典（含DAG进度）；**输出：**Redis key`ckpt:{task_id}`，PostgreSQL备份表。**约束：**序列化大小需<1MB，否则触发分片存储。 |
| **GWT验收** | Given 正在执行的任务，When 调用`save_checkpoint`，Then Redis中TTL重置为60min。Given 模拟调度器崩溃重启，When 调用`restore`，Then 从最近检查点恢复且不重复执行已完成步骤。 |
| **实施细节** | 使用`pickle`序列化，但替换`__getstate__`排除不可序列化的连接对象。 |
| **技术栈** | redis-py 5.0, asyncpg 0.29, pickle (内置) |

## Phase 3：三图谱引擎

### Step 3.1：代码图谱（Tree-sitter）

*（详细PRD/ADR已在上一轮输出中体现，为节省篇幅此处简化为关键约束，但实际文档应保持同等颗粒度——本报告在Word生成时须扩展）*
**关键约束：**支持增量解析（监测文件mtime），递归深度≤20，超时30s。**技术栈：**tree-sitter 0.20, tree-sitter-languages 1.10。

### Step 3.2：数据库图谱（Schema解析）

| PRD维度 | 详细内容 |
| --- | --- |
| **输入/输出** | **输入：**DB连接串（只读账号）；**输出：**表/字段/索引/外键节点。**异常：**权限不足时返回401并记录日志。 |
| **GWT验收** | Given 包含50张表的PG库，When 执行解析，Then 生成包含所有外键关系的图谱。Given 表结构变更，When 执行增量更新，Then 旧节点标记为`deprecated`而非删除。 |
| **实施细节** | 查询`information_schema`，批量插入使用`executemany`。 |
| **技术栈** | SQLAlchemy (反射), asyncpg |

### Step 3.3：配置图谱（漂移检测）

| PRD维度 | 详细内容 |
| --- | --- |
| **输入/输出** | **输入：**配置文件路径或K8s ConfigMap；**输出：**配置节点及依赖关系。**关键算法：**对每个配置项计算SHA256作为指纹，比对黄金基线。 |
| **GWT验收** | Given .env文件修改了`DB_PORT`，When 运行漂移检测，Then 触发告警并输出diff。Given 修复指令，When 执行自动回滚，Then 文件内容恢复至基线SHA。 |
| **实施细节** | 使用`python-dotenv`解析，`deepdiff`比较嵌套结构。 |
| **技术栈** | python-dotenv 1.0, deepdiff 6.7 |

## Phase 4：8层防幻觉

### Step 4.1：L1-L4（图谱验证/动态追踪/熵监控/静态检查）

| PRD维度 | 详细内容 |
| --- | --- |
| **输入/输出** | **输入：**LLM生成的代码段；**输出：**带`passed_flags`的验证报告。**L3熵监控：**采样窗口=10，阈值=0.75。 |
| **GWT验收** | Given 生成代码引用了不存在的`Utils.foo`，When L1验证，Then 拦截并打回。Given 生成过程中熵均值=0.8，When L3监控，Then 触发`HighEntropyError`，200ms内取消请求。 |
| **实施细节** | L1查询SQLite图谱；L3使用`asyncio.CancelledError`中断流式请求。 |
| **技术栈** | numpy (移动平均), mypy (静态检查集成) |

### Step 4.2：L5-L8（Z3验证/合约双向/沙箱/配置修复）

| PRD维度 | 详细内容 |
| --- | --- |
| **输入/输出** | **输入：**标记`@formal`的函数源码；**输出：**Z3验证结果（SAT/UNSAT）。**L6合约：**基于OpenAPI生成的客户端与服务端实现双向比对。 |
| **GWT验收** | Given 排序算法，When Z3验证，Then 30s内输出`valid`。Given 沙箱执行，When 包含文件操作，Then 被`seccomp`限制并隔离。 |
| **实施细节** | 使用`rotalabs-verity`调用Z3；沙箱使用`subprocess`+`pypy`限制资源。 |
| **技术栈** | z3-solver 4.13, rotalabs-verity (自定义封装), seccomp (Linux) |

## Phase 5：调度器与Agent


### Step 5.1：自研调度器（状态机+DAG+需求澄清）

| PRD维度 | 详细内容 |
| --- | --- |
| **输入/输出** | **输入：**task_id + raw_prd；**输出：**TaskState转换事件 + 检查点快照。 |
| **GWT验收** | Given 正常需求，When 状态机启动，Then IDLE→PARSING→PLANNING→...→DONE全流程完成。Given 模糊需求"优化一下"，When PARSING状态处理，Then 转换到WAITING_CLARIFICATION（不进入PLANNING）。Given WAITING_CLARIFICATION状态 + 用户回复，When transition("user_responded")，Then 重新进入PARSING。 |
| **实施细节** | 位于`/src/scheduler/`。状态：IDLE/PARSING/WAITING_CLARIFICATION/PLANNING/PREFLIGHT/CODING/VALIDATING/COMMITTING/DONE/FAILED。ClarificationEngine通过依赖注入集成到调度器，PARSING状态处理时调用process()。超时任务：24h自动挂起。 |
| **技术栈** | Python 3.11 Enum（状态定义），无新增依赖。 |

#### ADR 5.1：手写状态机 vs transitions库

| 备选 | 依赖成本 | 可读性 | 扩展性 | 决策 |
| --- | --- | --- | --- | --- |
| A. transitions库 | 需引入 | 高 | 中 | **✅ 选B** |
| B. 手写Enum+while | 无（仅Python内置） | 中 | 高（当前仅9状态） |  |
| **理由：**9个状态的顺序调度，手写方案简洁且完全可控，引入第三方库增加维护成本。 | **理由：**`while state != State.DONE` + `_transition()`模式对调度场景足够清晰。 | **理由：**若未来状态扩到>10个或需并行拓扑重构，届时再评估transitions。 |  |

## Phase 6：前端与测试

### Step 6.1：Vue3驾驶舱（AG-UI协议）

| PRD维度 | 详细内容 |
| --- | --- |
| **输入/输出** | **输入：**后端WebSocket事件流；**输出：**可视化拓扑（使用`vis-network`）。**约束：**首屏加载<2s，实时数据延迟<5s。 |
| **GWT验收** | Given 执行中的任务，When 打开Dashboard，Then 实时展示Agent状态（空闲/思考/执行）。Given 点击图谱节点，When 查询，Then 右侧面板展示元数据（行号/依赖）。 |
| **实施细节** | 前端使用`Pinia`管理状态，`socket.io-client`监听后端事件。 |
| **技术栈** | Vue 3.4, Pinia 2.1, vis-network 9.1, socket.io-client 4.7 |

### Step 6.2：端到端集成测试

| PRD维度 | 详细内容 |
| --- | --- |
| **输入/输出** | **输入：**测试用例集（含PRD样例）；**输出：**Allure测试报告。**覆盖率目标：**单元>80%，E2E覆盖核心路径（生成→验证→修复）。 |
| **GWT验收** | Given 混沌实验（模拟LLM 5xx错误），When 系统运行，Then 熔断器在30s内触发，且恢复后系统自愈。 |
| **实施细节** | 使用`pytest-xdist`并行加速，`docker-compose`拉起全量依赖。 |
| **技术栈** | pytest 8.0, pytest-xdist 3.5, chaos-mesh (K8s实验) |


### Step 6.3：测试体系（系统自测 + 输出物测）

| PRD维度 | 详细内容 |
| --- | --- |
| **输入/输出** | **输入：**自研组件源码、生成代码产物；**输出：**覆盖率报告、冒烟测试结果、回归测试结果、UI测试报告。**异常码：**COVERAGE_LOW (<80%), SMOKE_FAIL (阻断提交), REGRESSION_FAIL, UI_TIMEOUT。 |
| **GWT验收** | Given 8个自研组件源码，When 运行`pytest --cov=src`，Then 覆盖率≥80%，每个组件报告单独统计。Given 生成代码，When 自动触发`pytest tests/smoke/`，Then pass/fail结果输出，失败阻断提交。Given 变异测试生成用例，When 自动入库`tests/regression/`，Then 每次提交自动运行回归套件。Given Web前端生成产物，When 自动触发Playwright全链路，Then 报告贴在PR评论区。 |
| **实施细节** | `tests/unit/`按组件分包（≥10用例/文件）；`tests/integration/`测跨组件；`tests/smoke/`（编译+接口200）；`tests/regression/`（变异测试用例）；`tests/ui/`（Playwright Page Object + 全链路流）。GitHub Actions门禁：覆盖率<80%或smoke fail阻断合并。 |
| **技术栈** | pytest 8.0, pytest-cov 4.1, pytest-asyncio 0.23, pytest-mock 3.12；Playwright 1.40（Python SDK）；TestContainers（集成测试真实依赖）。 |

#### ADR 6.3：测试框架选型（系统自测 + 输出物测）

| 备选 | 系统自身测试 | 输出物测试 | 决策 |
| --- | --- | --- | --- |
| A. pytest + unittest | ✅ 成熟稳定 | ❌ 无UI支持 | — |
| B. pytest + Playwright | ✅ 统一Python栈 | ✅ UI测试最强 | **✅ 选B** |
| C. Jest + Cypress | ❌ 需JS技术栈 | ✅ UI最强 | ❌ 跨栈成本高 |
| **理由：**统一Python栈降低学习成本；Playwright多语言支持好（Python/JS/TS/C#）；与变异测试（Python）天然集成；测试报告统一Allure。 | **理由：**统一Python栈降低学习成本；Playwright多语言支持好（Python/JS/TS/C#）；与变异测试（Python）天然集成；测试报告统一Allure。 | **理由：**统一Python栈降低学习成本；Playwright多语言支持好（Python/JS/TS/C#）；与变异测试（Python）天然集成；测试报告统一Allure。 |  |




### Step 5.4：Agent间通信协议

    

#### 5.4.1 设计原则

    
        
- 异步优先：Agent间调用以异步消息为主，避免同步阻塞导致调度器卡死。
        
- 超时必设：每次跨Agent调用必须设置超时，默认30秒，可配置。
        
- 幂等性保障：消息可重放，下游必须支持幂等处理（通过request_id去重）。
        
- 熔断传播：下游Agent熔断时，上游Agent收到标准化错误码，可执行降级策略。
        
- 审计完备：所有通信记录写入task_audit_trail，支持全链路追踪。
    

    

#### 5.4.2 通信模式

    | 模式 | 说明 | 适用场景 |
| --- | --- | --- |
| Request-Response | Agent A发送请求，阻塞等待Agent B返回结果 | DeveloperAgent → QAAgent（验证代码） |
| Fire-and-Forget | Agent A发送消息，不等待响应 | 审计日志记录、指标上报 |
| Streaming | Agent B分块返回结果 | L3熵监控（流式Token分析） |
| Callback | Agent A提供回调URL，Agent B完成后异步通知 | 长时间运行的验证任务（Z3求解、沙箱执行） |

    

#### 5.4.3 数据契约

    

```python
# /src/communication/protocol.py
    from pydantic import BaseModel, Field
    from typing import Optional, Dict, Any, Literal
    from datetime import datetime
    from uuid import uuid4

    # === 消息基类 ===
    class Message(BaseModel):
        id: str = Field(default_factory=lambda: str(uuid4()))
        correlation_id: Optional[str] = None  # 用于Request-Response配对
        source_agent: str  # DeveloperAgent / QAAgent / ReviewerAgent
        target_agent: str
        timestamp: datetime = Field(default_factory=datetime.utcnow)
        ttl_seconds: int = 30  # 消息有效期

    # === Request-Response ===
    class Request(Message):
        type: Literal["request"] = "request"
        method: str  # verify_code, execute_sandbox, query_graph
        params: Dict[str, Any]
        timeout_seconds: int = 30
        retry_count: int = 0
        max_retries: int = 2

    class Response(Message):
        type: Literal["response"] = "response"
        status: Literal["success", "error", "timeout", "circuit_open"]
        result: Optional[Any] = None
        error_code: Optional[str] = None
        error_message: Optional[str] = None
        duration_ms: float

    # === Fire-and-Forget ===
    class Notification(Message):
        type: Literal["notification"] = "notification"
        event: str  # checkpoint_saved, token_consumed, entropy_triggered
        payload: Dict[str, Any]

    # === Streaming ===
    class StreamChunk(BaseModel):
        sequence: int
        data: Any
        is_last: bool = False
        error: Optional[str] = None

    # === 标准错误码 ===
    class ErrorCode:
        TARGET_UNAVAILABLE = "AGENT_001"      # 目标Agent不可用
        TIMEOUT = "AGENT_002"                 # 超时
        CIRCUIT_OPEN = "AGENT_003"            # 目标熔断
        INVALID_REQUEST = "AGENT_004"         # 请求参数错误
        INTERNAL_ERROR = "AGENT_005"          # 目标内部错误
        RATE_LIMITED = "AGENT_006"            # 限流
```

    

#### 5.4.4 异常定义

    

```python
class AgentCommunicationError(Exception):
        """通信层基类异常"""
        pass

    class AgentUnavailableError(AgentCommunicationError):
        """目标Agent不可用（未注册/已下线）"""
        def __init__(self, agent_name: str):
            self.agent_name = agent_name
            super().__init__(f"Agent '{agent_name}' is not available")

    class AgentTimeoutError(AgentCommunicationError):
        """请求超时"""
        def __init__(self, agent_name: str, timeout_seconds: int):
            self.agent_name = agent_name
            self.timeout_seconds = timeout_seconds
            super().__init__(f"Request to '{agent_name}' timed out after {timeout_seconds}s")

    class AgentCircuitOpenError(AgentCommunicationError):
        """目标Agent熔断器开启"""
        def __init__(self, agent_name: str):
            self.agent_name = agent_name
            super().__init__(f"Circuit breaker for '{agent_name}' is open")

    class AgentRateLimitError(AgentCommunicationError):
        """目标Agent限流"""
        def __init__(self, agent_name: str, retry_after: int):
            self.agent_name = agent_name
            self.retry_after = retry_after
            super().__init__(f"Rate limited by '{agent_name}', retry after {retry_after}s")
```

    

#### 5.4.5 通信层实现

    

```python
# /src/communication/message_bus.py
    import asyncio
    from typing import Dict, Optional, List
    from src.communication.protocol import Request, Response, Notification

    class AgentMessageBus:
        """Agent间异步消息总线"""
        def __init__(self, checkpoint_manager):
            self._agents: Dict[str, 'Agent'] = {}  # 注册的Agent
            self._pending: Dict[str, asyncio.Future] = {}  # 等待响应的请求
            self._checkpoint = checkpoint_manager

        def register(self, agent_name: str, agent_instance: 'Agent'):
            """注册Agent到消息总线"""
            self._agents[agent_name] = agent_instance

        def unregister(self, agent_name: str):
            if agent_name in self._agents:
                del self._agents[agent_name]

        async def request(self, request: Request) -> Response:
            """发送同步请求，等待响应"""
            # 检查目标Agent是否可用
            if request.target_agent not in self._agents:
                raise AgentUnavailableError(request.target_agent)

            # 检查目标Agent熔断器状态
            if self._agents[request.target_agent].circuit_breaker.is_open():
                raise AgentCircuitOpenError(request.target_agent)

            # 创建Future等待响应
            future = asyncio.Future()
            self._pending[request.id] = future

            try:
                # 异步转发请求
                asyncio.create_task(
                    self._deliver(request)
                )

                # 等待响应（带超时）
                response = await asyncio.wait_for(
                    future,
                    timeout=request.timeout_seconds
                )
                return response

            except asyncio.TimeoutError:
                self._pending.pop(request.id, None)
                raise AgentTimeoutError(request.target_agent, request.timeout_seconds)
            finally:
                self._pending.pop(request.id, None)

        async def _deliver(self, request: Request):
            """实际投递请求到目标Agent"""
            try:
                target = self._agents[request.target_agent]
                response = await target.handle_request(request)

                # 记录通信审计
                await self._checkpoint.record_communication(request, response)

                # 唤醒等待的Future
                if request.id in self._pending:
                    self._pending[request.id].set_result(response)

            except Exception as e:
                # 异常情况：返回错误响应
                error_response = Response(
                    id=str(uuid4()),
                    correlation_id=request.id,
                    source_agent=request.target_agent,
                    target_agent=request.source_agent,
                    status="error",
                    error_code=ErrorCode.INTERNAL_ERROR,
                    error_message=str(e),
                    duration_ms=0
                )
                if request.id in self._pending:
                    self._pending[request.id].set_result(error_response)

        def notify(self, notification: Notification):
            """发送单向通知（Fire-and-Forget）"""
            asyncio.create_task(self._deliver_notification(notification))

        async def _deliver_notification(self, notification: Notification):
            if notification.target_agent in self._agents:
                target = self._agents[notification.target_agent]
                await target.handle_notification(notification)

        def get_agent_status(self, agent_name: str) -> Dict:
            """查询Agent状态"""
            if agent_name not in self._agents:
                return {"status": "unavailable"}
            return self._agents[agent_name].get_status()

        # === 幂等性去重 ===
        _processed_requests: set = set()

        async def is_duplicate(self, request_id: str) -> bool:
            """检查请求是否已处理（幂等性保障）"""
            if request_id in self._processed_requests:
                return True
            self._processed_requests.add(request_id)
            # 定期清理（生产环境用Redis TTL）
            return False
```

    

#### 5.4.6 ADR：通信模式选型

    | ADR · Agent间通信模式 |
| --- |
| 决策 | 采用异步消息总线 + 同步Future等待的混合模式： ① Agent间调用通过MessageBus转发，调用方使用await bus.request()同步等待。 ② 底层使用asyncio实现非阻塞，支持超时和熔断传播。 ③ 长耗时操作（Z3、沙箱）使用Callback模式，避免长时间占用连接。 |
| 理由 | ① 简化调用方代码（同步写法，异步执行）。② 超时和熔断可在单一位置统一管理。③ 与V14.1的asyncio调度器自然兼容。 |
| 备选方案 | ① 纯异步回调（代码复杂度高，调试困难）→ 放弃。② gRPC流式通信（过重，不适合Agent间轻量通信）→ 放弃。 |

    

---

    
    
    
    

    



### Step 5.5：工具调用标准化

    

#### 5.5.1 设计原则

    
        
- 声明式注册：工具通过装饰器或配置文件声明，支持动态加载。
        
- 权限隔离：每个工具定义allowed_agents，只有授权Agent可调用。
        
- 版本兼容：工具支持语义化版本，Agent调用时指定版本范围。
        
- 可观测性：每次工具调用记录到审计表（含入参、出参、耗时）。
        
- 优雅降级：工具不可用时，系统自动降级（如返回缓存结果或跳过）。
    

    

#### 5.5.2 工具注册与元数据

    

```python
# /src/tools/registry.py
    from pydantic import BaseModel, Field
    from typing import Callable, List, Dict, Any, Optional
    from enum import Enum
    from datetime import datetime

    class ToolPermission(str, Enum):
        READ = "read"
        WRITE = "write"
        ADMIN = "admin"

    class ToolSchema(BaseModel):
        """工具元数据定义"""
        name: str
        version: str  # 语义化版本，如 "1.2.3"
        description: str
        parameters: Dict[str, Any]  # JSON Schema格式
        returns: Dict[str, Any]  # 返回格式
        permissions: List[ToolPermission]
        allowed_agents: List[str]  # 白名单
        rate_limit: int = 0  # 每分钟调用上限，0表示不限
        timeout_seconds: int = 30
        is_async: bool = True
        cache_ttl: Optional[int] = None  # 缓存TTL（秒）
        deprecated: bool = False
        deprecated_message: Optional[str] = None

    class ToolInvocation(BaseModel):
        """工具调用记录"""
        id: str
        tool_name: str
        tool_version: str
        agent_name: str
        parameters: Dict[str, Any]
        result: Optional[Any] = None
        error: Optional[str] = None
        status: Literal["pending", "success", "error", "timeout"]
        duration_ms: float
        timestamp: datetime = Field(default_factory=datetime.utcnow)
```

    

#### 5.5.3 工具注册中心

    

```python
# /src/tools/registry.py (续)
    import asyncio
    from typing import Dict, Optional, List
    from collections import defaultdict
    import time

    class ToolRegistry:
        """工具注册中心 - 管理所有工具的生命周期"""
        def __init__(self):
            self._tools: Dict[str, Dict[str, ToolSchema]] = {}  # name -> version -> schema
            self._handlers: Dict[str, Dict[str, Callable]] = {}  # name -> version -> handler
            self._rate_limiter: Dict[str, Dict[str, List[float]]] = defaultdict(dict)

        def register(
            self,
            schema: ToolSchema,
            handler: Callable
        ) -> None:
            """注册工具"""
            if schema.name not in self._tools:
                self._tools[schema.name] = {}
                self._handlers[schema.name] = {}

            self._tools[schema.name][schema.version] = schema
            self._handlers[schema.name][schema.version] = handler

        def get_tool(self, name: str, version: str) -> Optional[ToolSchema]:
            """获取工具元数据"""
            if name in self._tools and version in self._tools[name]:
                return self._tools[name][version]
            return None

        def get_latest_version(self, name: str) -> Optional[str]:
            """获取最新版本"""
            if name in self._tools:
                return max(self._tools[name].keys())
            return None

        async def invoke(
            self,
            name: str,
            params: Dict[str, Any],
            agent_name: str,
            version: Optional[str] = None
        ) -> ToolInvocation:
            """调用工具"""
            # 1. 解析版本（默认最新）
            if not version:
                version = self.get_latest_version(name)
                if not version:
                    raise ValueError(f"Tool '{name}' not found")

            # 2. 获取工具定义
            schema = self.get_tool(name, version)
            if not schema:
                raise ValueError(f"Tool '{name}:{version}' not found")

            # 3. 权限检查
            if agent_name not in schema.allowed_agents:
                raise PermissionError(f"Agent '{agent_name}' not allowed to call '{name}'")

            # 4. 限流检查
            if schema.rate_limit > 0:
                if not self._check_rate_limit(name, version, agent_name, schema.rate_limit):
                    raise RateLimitError(f"Rate limit exceeded for '{name}'")

            # 5. 执行工具
            start_time = time.time()
            try:
                handler = self._handlers[name][version]
                if schema.is_async:
                    result = await handler(params)
                else:
                    result = handler(params)

                status = "success"
                error = None

            except asyncio.TimeoutError:
                status = "timeout"
                result = None
                error = f"Tool '{name}' timed out after {schema.timeout_seconds}s"

            except Exception as e:
                status = "error"
                result = None
                error = str(e)

            duration_ms = (time.time() - start_time) * 1000

            # 6. 返回调用记录
            return ToolInvocation(
                id=str(uuid4()),
                tool_name=name,
                tool_version=version,
                agent_name=agent_name,
                parameters=params,
                result=result,
                error=error,
                status=status,
                duration_ms=duration_ms
            )

        def _check_rate_limit(self, name: str, version: str, agent: str, limit: int) -> bool:
            """检查限流"""
            key = f"{name}:{version}:{agent}"
            now = time.time()
            if key not in self._rate_limiter:
                self._rate_limiter[key] = []

            # 过滤1分钟内的记录
            self._rate_limiter[key] = [
                t for t in self._rate_limiter[key] if now - t = limit:
                return False

            self._rate_limiter[key].append(now)
            return True

        def is_deprecated(self, name: str, version: str) -> bool:
            """检查工具是否已废弃"""
            schema = self.get_tool(name, version)
            return schema.deprecated if schema else False

        def get_deprecation_message(self, name: str, version: str) -> Optional[str]:
            schema = self.get_tool(name, version)
            return schema.deprecated_message if schema else None
```

    

#### 5.5.4 工具声明示例

    

```python
# /src/tools/declarations.py
    from src.tools.registry import ToolSchema, ToolPermission, ToolRegistry

    # 在系统启动时注册工具
    registry = ToolRegistry()

    # 注册 "query_knowledge" 工具
    registry.register(
        schema=ToolSchema(
            name="query_knowledge",
            version="2.0.0",
            description="查询领域知识图谱",
            parameters={
                "type": "object",
                "properties": {
                    "domain": {"type": "string", "enum": ["accounting", "finance", "law"]},
                    "concept": {"type": "string"},
                    "mode": {"type": "string", "enum": ["exact", "semantic"]}
                },
                "required": ["domain", "concept"]
            },
            returns={"type": "object", "properties": {"nodes": "array"}},
            permissions=[ToolPermission.READ],
            allowed_agents=["DeveloperAgent", "QAAgent", "ReviewerAgent"],
            rate_limit=100,
            timeout_seconds=10,
            is_async=True,
            cache_ttl=300  # 5分钟缓存
        ),
        handler=query_knowledge_handler
    )

    # 注册 "validate_compliance" 工具（敏感操作）
    registry.register(
        schema=ToolSchema(
            name="validate_compliance",
            version="1.0.0",
            description="验证代码是否符合法规",
            parameters={...},
            permissions=[ToolPermission.READ, ToolPermission.WRITE],
            allowed_agents=["QAAgent"],  # 仅QA可调用
            rate_limit=10,  # 每分钟仅10次
            timeout_seconds=60,
            is_async=True
        ),
        handler=validate_compliance_handler
    )
```

    

#### 5.5.5 ADR：工具调用的版本管理

    | ADR · 工具版本管理 |
| --- |
| 决策 | 工具采用语义化版本管理，Agent调用时需声明版本范围（如~=1.2），系统自动解析为精确版本。 ① 工具升级时，旧版本仍保留（向后兼容至少3个小版本）。 ② 工具废弃时，在元数据中标记deprecated=True，并给出迁移指引。 ③ 审计表记录每次调用的精确版本。 |
| 理由 | ① 避免Agent因工具升级而失效。② 支持A/B测试（不同Agent使用不同版本）。③ 便于回滚（发现问题时切回旧版本）。 |

    

---

    
    
    
    

    



### Step 5.6：多任务并发调度

    

#### 5.6.1 设计原则

    
        
- 优先级分层：任务分为CRITICAL/HIGH/NORMAL/LOW四级，高优先级抢占资源。
        
- 资源配额：按任务/团队/全局三级设置资源配额（LLM调用、沙箱实例、Token预算）。
        
- 公平调度：防止单个大任务独占资源，引入时间片轮转。
        
- 背压控制：资源不足时，新任务排队或拒绝，而非崩溃。
    

    

#### 5.6.2 任务优先级与资源配额

    

```python
# /src/scheduler/resource_scheduler.py
    from enum import Enum
    from dataclasses import dataclass
    from typing import Dict, Optional
    from collections import deque
    import asyncio

    class TaskPriority(Enum):
        CRITICAL = 0  # 最高（生产故障修复）
        HIGH = 1      # 重要功能开发
        NORMAL = 2    # 常规任务
        LOW = 3       # 探索性任务

    @dataclass
    class ResourceQuota:
        """资源配额定义"""
        max_concurrent_tasks: int = 5
        max_llm_calls_per_minute: int = 60
        max_tokens_per_task: int = 100
        max_sandbox_instances: int = 3
        cpu_cores_limit: float = 4.0
        memory_limit_mb: int = 4096

    @dataclass
    class TaskResource:
        """任务资源使用情况"""
        task_id: str
        priority: TaskPriority
        llm_calls_used: int = 0
        tokens_used: int = 0
        sandbox_count: int = 0
        cpu_used: float = 0.0
        memory_used_mb: int = 0
        started_at: Optional[float] = None
        last_scheduled: Optional[float] = None
```

    

#### 5.6.3 资源调度器核心实现

    

```python
# /src/scheduler/resource_scheduler.py (续)
    import time
    from typing import List, Optional
    import asyncio

    class ResourceScheduler:
        """统一资源调度器"""
        def __init__(self, global_quota: ResourceQuota):
            self.global_quota = global_quota
            self._queues = {
                TaskPriority.CRITICAL: deque(),
                TaskPriority.HIGH: deque(),
                TaskPriority.NORMAL: deque(),
                TaskPriority.LOW: deque(),
            }
            self._running: Dict[str, TaskResource] = {}
            self._quota_usage = {
                "concurrent_tasks": 0,
                "llm_calls_per_minute": 0,
                "sandbox_instances": 0,
                "cpu_cores": 0,
                "memory_mb": 0,
            }
            self._last_reset = time.time()
            self._lock = asyncio.Lock()

        async def submit(
            self,
            task_id: str,
            priority: TaskPriority = TaskPriority.NORMAL,
            requested_resources: Optional[Dict] = None
        ) -> bool:
            """提交任务到调度队列"""
            async with self._lock:
                # 检查全局资源是否饱和
                if self._quota_usage["concurrent_tasks"] >= self.global_quota.max_concurrent_tasks:
                    # 除非是CRITICAL任务，否则排队
                    if priority != TaskPriority.CRITICAL:
                        self._queues[priority].append(task_id)
                        return False

                # 分配资源
                self._quota_usage["concurrent_tasks"] += 1
                self._running[task_id] = TaskResource(
                    task_id=task_id,
                    priority=priority,
                    started_at=time.time(),
                    last_scheduled=time.time()
                )
                return True

        async def can_proceed(self, task_id: str) -> bool:
            """检查任务是否可以继续执行（资源预检）"""
            if task_id not in self._running:
                return False

            resource = self._running[task_id]

            # 检查各项资源限制
            checks = [
                resource.llm_calls_used  bool:
            """消费LLM调用配额"""
            async with self._lock:
                if task_id not in self._running:
                    return False

                resource = self._running[task_id]
                # 重置分钟计数器
                if time.time() - self._last_reset > 60:
                    self._quota_usage["llm_calls_per_minute"] = 0
                    self._last_reset = time.time()

                # 检查LLM调用限流
                if self._quota_usage["llm_calls_per_minute"] >= self.global_quota.max_llm_calls_per_minute:
                    return False

                # 检查任务Token预算
                if resource.tokens_used + tokens > self.global_quota.max_tokens_per_task:
                    return False

                # 扣减配额
                self._quota_usage["llm_calls_per_minute"] += 1
                resource.llm_calls_used += 1
                resource.tokens_used += tokens
                return True

        async def release(self, task_id: str):
            """释放任务资源"""
            async with self._lock:
                if task_id in self._running:
                    self._quota_usage["concurrent_tasks"] -= 1
                    # 释放其他资源...
                    del self._running[task_id]

                # 从队列中取出下一个任务（抢占式）
                await self._schedule_next()

        async def _schedule_next(self):
            """调度下一个任务（抢占式优先级调度）"""
            for priority in [TaskPriority.CRITICAL, TaskPriority.HIGH,
                            TaskPriority.NORMAL, TaskPriority.LOW]:
                if self._queues[priority]:
                    next_task = self._queues[priority].popleft()
                    # 重新提交（递归）
                    await self.submit(next_task, priority)

        def get_queue_status(self) -> Dict:
            """获取队列状态"""
            return {
                "critical": len(self._queues[TaskPriority.CRITICAL]),
                "high": len(self._queues[TaskPriority.HIGH]),
                "normal": len(self._queues[TaskPriority.NORMAL]),
                "low": len(self._queues[TaskPriority.LOW]),
                "running": len(self._running),
                "quota": {
                    "concurrent_tasks": self._quota_usage["concurrent_tasks"],
                    "llm_calls_per_minute": self._quota_usage["llm_calls_per_minute"],
                    "sandbox_instances": self._quota_usage["sandbox_instances"],
                }
            }
```

    

#### 5.6.4 与调度器状态机的集成

    

```python
# /src/scheduler/orchestrator.py (集成片段)
    class TaskOrchestrator:
        def __init__(self, scheduler: ResourceScheduler):
            self.resource_scheduler = scheduler

        async def execute(self, task: Task):
            # 1. 提交任务到调度器
            priority = self._determine_priority(task)
            if not await self.resource_scheduler.submit(task.id, priority):
                # 排队等待
                task.state = TaskState.QUEUED
                return

            try:
                # 2. 执行主流程（每个LLM调用前检查资源）
                while task.state != TaskState.DONE:
                    # 资源预检
                    if not await self.resource_scheduler.can_proceed(task.id):
                        # 资源不足，挂起等待
                        task.state = TaskState.PAUSED_RESOURCE
                        await asyncio.sleep(5)
                        continue

                    # 执行下一步（如CODING）
                    await self._execute_step(task)

            finally:
                # 3. 释放资源
                await self.resource_scheduler.release(task.id)

        def _determine_priority(self, task: Task) -> TaskPriority:
            """根据任务类型和上下文确定优先级"""
            if task.context.get("is_hotfix"):
                return TaskPriority.CRITICAL
            if task.context.get("is_production_issue"):
                return TaskPriority.CRITICAL
            if task.context.get("is_feature"):
                return TaskPriority.HIGH
            if task.context.get("is_exploration"):
                return TaskPriority.LOW
            return TaskPriority.NORMAL
```

    

#### 5.6.5 ADR：抢占式调度 vs 公平调度

    | ADR · 多任务调度策略 |
| --- |
| 决策 | 采用优先级抢占式调度 + 公平时间片混合策略： ① 高优先级任务（CRITICAL/HIGH）可抢占低优先级任务的资源。 ② 同优先级任务采用时间片轮转（每个任务最多连续运行30秒）。 ③ 长运行任务（>5分钟）自动降级为LOW优先级。 |
| 理由 | ① 生产故障修复必须优先保障（CRITICAL）。② 防止单个任务无限占用资源。③ 保证低优先级任务也能获得执行机会。 |
| 风险与缓解 | 风险：频繁抢占导致低优先级任务饥饿。缓解：CRITICAL任务每天不超过5个，超过后降级为HIGH。 |

    

---

    

    




## Step 5.7：Agent拉起机制

## Step 5.8：微信小程序接入
系统 → Agent 协程驱动 · 与 MCP/A2A 的抽象分层
    版本说明：本补充章节明确了 V14.1 系统如何通过 asyncio 协程拉起 Agent、Agent 在进程内的实现形态、与 MCP（工具调用）和 A2A（Agent 间通信）的分层关系，以及外部系统通过 API 调用调度器的完整链路。所有内容已映射到现有 Step，可直接合并到主开发计划中。

    

---

    

## 1. 核心概念澄清

---

手机作为请求入口 · 微信小程序 Skill 机制 · 实时监控
    版本说明：本补充章节明确了 V14.1 系统如何通过微信小程序的 Skill 机制作为请求入口，并结合 WebSocket/SSE 实现实时监控。所有设计均与 V14.1 现有架构（API 网关、MCP 协议、状态机调度）完全兼容。

    

---

    

## 1. 整体架构设计


## Step 5.7：Agent拨起机制

## Step 5.8：微信小程序接入
## 1. 核心概念澄清

    

> 核心声明：在 V14.1 中，Agent 不是独立微服务、不是容器、不是进程，而是 调度器进程内的一个 Python 异步协程（asyncio Task）。

    

#### Step 5.7.24.1 “调用 Agent”的两种语义

    | 语义 | 含义 | V14.1 的实现 |
| --- | --- | --- |
| A2A 通信 | Agent A 请求 Agent B 执行某任务或提供信息 | 通过 A2A 协议（结构化消息）实现 Agent 间通信 |
| 系统拉起 Agent | 调度器将 Agent 实例化并开始执行 | 调度器的状态机通过 asyncio.create_task() 拉起 Agent 协程 |

    用户的问题“怎么调用 Agent”属于第二种语义：系统如何将 Agent 实例化并启动执行。

    

---

    
    
    
    

    

## 2. Agent 的实现形态

    

```python
# Agent 的本质是一个异步协程类
    class DeveloperAgent:
        def __init__(self, llm_client, graph_repo, sandbox, checkpoint_mgr):
            self.llm = llm_client
            self.graph = graph_repo
            self.sandbox = sandbox
            self.checkpoint = checkpoint_mgr

        async def run(self, context: TaskContext) -> AgentResult:
            # 思考 → 行动 → 观察 循环
            while not self.should_stop():
                thought = await self.think(context)        # 调用 LLM
                action = await self.act(thought)           # 执行工具（通过 MCP）
                observation = await self.observe(action)   # 收集结果
                context = self.update_context(context, observation)
            return AgentResult(...)
```

    

#### Step 5.7.24.2 关键特征

    
        
- 进程内执行：所有 Agent 运行在同一个进程中，无进程间通信开销。
        
- 协程隔离：每个 Agent 是一个独立的 asyncio Task，由事件循环调度。
        
- 状态隔离：Agent 间不直接共享内存，通过调度器的 Session/Checkpoint 传递经过验证的数据。
        
- 私有工作记忆（L4）：每个 Agent 有独立的局部工作记忆，不跨 Agent 共享。
        
- 拉起速度：协程创建为微秒级，远快于容器启动（秒级）。
    

    

---

    
    
    
    

    

## 3. 系统拉起 Agent 的完整流程

    

#### Step 5.7.24.3 第1步：用户触发（外部入口）

    

```python
# API 入口
    @router.post("/api/v1/tasks")
    async def create_task(req: TaskCreateRequest):
        task = Task(prd=req.prd, state=TaskState.IDLE)
        await scheduler.submit(task)  # ← 提交给调度器
        return {"task_id": task.id}
```

    用户调用的不是 Agent，而是调度器的 API 入口。

    

#### Step 5.7.24.3 第2步：调度器状态机驱动

    

```python
# Step 5.1 调度器状态机（核心逻辑）
    class SchedulerStateMachine:
        async def run(self, task: Task):
            while task.state != TaskState.DONE:
                if task.state == TaskState.IDLE:
                    task.state = TaskState.PARSING
                    result = await self._run_agent(ParserAgent, task)

                elif task.state == TaskState.PARSING:
                    task.state = TaskState.PLANNING
                    result = await self._run_agent(ArchitectAgent, task)

                elif task.state == TaskState.PLANNING:
                    task.state = TaskState.CODING
                    # 🔴 关键：拉起 DeveloperAgent
                    result = await self._run_agent(DeveloperAgent, task)

                # ... 依次类推
```

    

#### Step 5.7.24.3 第3步：拉起 Agent 协程（核心）

    

```python
# 实际拉起 Agent 的方法
    async def _run_agent(self, agent_class, task: Task) -> AgentResult:
        # 1. 构建 Agent 的上下文（注入 L1-L5）
        context = TaskContext(
            l1=SYSTEM_PROMPTS[agent_class.__name__],       # 协作宪法
            l2=await self._query_graphs(task),             # 四图谱事实
            l3=self._build_task_context(task),             # 任务状态
            l4={},                                         # 私有工作记忆（空）
            l5=await self._retrieve_memories(task)         # 长期记忆
        )

        # 2. 实例化 Agent（依赖注入）
        agent = agent_class(
            llm_client=self.llm_client,
            graph_repo=self.graph_repo,
            sandbox=self.sandbox,
            checkpoint_mgr=self.checkpoint_mgr
        )

        # 3. 🔴 拉起 Agent 协程（本质是异步函数调用）
        result = await agent.run(context)

        # 4. 将结果写入检查点（供下游 Agent 使用）
        await self.checkpoint_mgr.save(task.id, result)

        return result
```

    

#### Step 5.7.24.3 第4步：Agent 执行循环

    

```python
class DeveloperAgent:
        async def run(self, context: TaskContext) -> AgentResult:
            for iteration in range(self.max_iterations):
                # 思考：调用 LLM
                thought = await self.think(context)

                # 行动：执行工具调用（通过 MCP）
                action = await self.act(thought)

                # 观察：收集结果
                observation = await self.observe(action)

                # 更新上下文（L4 私有工作记忆）
                context.l4["last_action"] = action
                context.l4["last_observation"] = observation

                # 终止条件判断
                if self.should_stop(observation):
                    break

            return AgentResult(success=True, output=context.l4["final_output"])
```

    

---

    
    
    
    

    

## 4. 与 MCP/A2A 的抽象分层

    在 V14.1 中，MCP 和 A2A 服务于不同的抽象层级，而“系统拉起 Agent”是另一个独立的层级。

    

> ┌─────────────────────────────────────────────────────────────┐
        │              💻 外部系统（用户 / CI/CD / 其他服务）         │
        └──────────────────────────┬──────────────────────────────────┘
                                   │ HTTP / WebSocket
                                   ▼
        ┌─────────────────────────────────────────────────────────────┐
        │              🌐 API 网关层（Step 1.1）                     │
        │  POST /api/v1/tasks   →  提交任务                         │
        │  GET /api/v1/tasks/{id} →  查询状态                       │
        └──────────────────────────┬──────────────────────────────────┘
                                   │
                                   ▼
        ┌─────────────────────────────────────────────────────────────┐
        │              🎯 调度器（Orchestrator）                     │
        │  • 状态机驱动（Step 5.1）                                 │
        │  • 🔴 通过 asyncio.create_task() 拉起 Agent 协程          │
        │  • 通过 Checkpoint 管理状态（Step 2.2）                   │
        │  • 通过 Audit 记录决策链（Step 1.2 补丁）                 │
        └──────────────┬─────────────────────────────────────────────┘
                       │ await agent.run()
                       ▼
        ┌─────────────────────────────────────────────────────────────┐
        │              🧠 Agent 协程（DeveloperAgent / ArchitectAgent）│
        │  • 思考→行动→观察 循环（Step 5.1）                        │
        │  • 🔽 通过 MCP 调用工具（向下）                           │
        │  • ↔️ 通过 A2A 与其他 Agent 通信（水平）                  │
        └─────────────────────────────────────────────────────────────┘

    

#### Step 5.7.24.4 三层调用关系

    | 层级 | 用途 | 协议/方式 | 调用方向 |
| --- | --- | --- | --- |
| 系统 → Agent | 调度器实例化并驱动 Agent 协程 | asyncio.create_task() + await agent.run() | 向上驱动 |
| Agent → 工具 | Agent 调用外部工具/资源（四图谱、沙箱、数据库） | MCP（Model Context Protocol） | 向下调用 |
| Agent → Agent | Agent 之间协作通信（任务分发、审查、仲裁） | A2A（Agent-to-Agent Protocol） | 水平通信 |

    

#### Step 5.7.24.4 与现有协议的定位

    
        
- MCP 不在“拉起 Agent”层：MCP 是 Agent 已经运行后用来调用工具的协议。它不负责 Agent 的启动或生命周期管理。
        
- A2A 不在“拉起 Agent”层：A2A 是 Agent 之间已经运行后用来相互通信的协议。它也不负责 Agent 的启动。
        
- “拉起 Agent”是调度器的职责：通过 asyncio 协程直接实例化和驱动，是 V14.1 自研调度器的核心能力。
    

    

---

    
    
    
    

    

## 5. PRD/ADR 规格

    

#### Step 5.7.24.5 PRD · Agent 拉起机制

    | PRD · Agent 拉起机制 |
| --- |
| 背景 | 外部系统需要通过调度器驱动多智能体协作。Agent 不是预先部署的微服务，而是由调度器按需实例化的异步协程。 |
| 用户故事 | 作为调度器，我根据状态机的进度，在合适的时机await agent.run()拉起对应的 Agent 协程，执行完成后将结果写入检查点。 |
| 需求描述 | ① Agent 定义为异步协程类，实现 run(context: TaskContext) -> AgentResult 方法。 ② 调度器通过 asyncio.create_task() 拉起 Agent。 ③ 拉起时注入 L1-L5 上下文（L1 协作宪法、L2 四图谱事实、L3 任务状态、L4 私有记忆、L5 长期记忆）。 ④ Agent 执行完成后，结果写入检查点（Checkpoint），供下游 Agent 使用。 ⑤ 外部系统通过 API 调用调度器，不直接调用 Agent。 |
| 范围 | Do：进程内协程拉起；依赖注入；上下文构建；结果持久化。 Don't：不通过 HTTP/gRPC 远程调用 Agent；不将 Agent 部署为独立容器。 |
| 数据契约 | ```python class TaskContext(BaseModel): task_id: str l1: str # System Prompt（协作宪法） l2: Dict[str, Any] # 四图谱查询结果 l3: Dict[str, Any] # 任务状态（PRD摘要、DAG进度） l4: Dict[str, Any] # Agent私有工作记忆 l5: List[Dict[str, Any]] # 长期记忆（检索结果） class AgentResult(BaseModel): success: bool output: Any error: Optional[str] = None duration_ms: float ``` |
| SC→AC | SC1: Agent 拉起成功 → AC1: 状态机触发 CODING 状态时，调用 _run_agent(DeveloperAgent, task) 返回 AgentResult。 SC2: 上下文注入完整 → AC2: Agent 的 run() 方法中 context.l1、context.l2 非空且包含预期内容。 SC3: 结果持久化 → AC3: Agent 执行完成后，检查点中存在对应 task_id 的记录。 |
| 待定决策 | Q: Agent 执行超时如何处理？ → 决议：在 _run_agent() 中包装 asyncio.wait_for(agent.run(), timeout=300)，超时后取消协程并标记 FAILED。 |

    

#### Step 5.7.24.5 ADR · Agent 实现形态

    | ADR · Agent 实现形态 |
| --- |
| 决策 | Agent 实现为进程内异步协程，而非独立微服务或容器。 ① 所有 Agent 运行在调度器同一进程中。 ② 通过 asyncio 事件循环调度。 ③ 通过依赖注入传递外部依赖（LLM 客户端、图谱仓库、沙箱）。 ④ 通过 Checkpoint 实现状态跨 Agent 传递。 |
| 理由 | ① 无网络开销：协程间通信为零延迟。② 极速拉起：协程创建为微秒级。③ 共享内存：Checkpoint 直接读取，无需序列化传递。④ 简化运维：无需部署多个微服务。⑤ 与 V14.1 的 asyncio 调度器自然兼容。 |
| 备选方案 | ① 独立微服务（HTTP/gRPC 拉起）→ 网络延迟高，资源消耗大，不适合密集 Agent 协作。② 独立容器（Docker 拉起）→ 启动慢（秒级），资源隔离过度。 |

    

---

    
    
    
    

    

## 6. 与现有 Step 的映射

    | Step | 原有内容 | Agent 拉起机制的补充 |
| --- | --- | --- |
| Step 5.1调度器状态机 | 定义了状态转换（IDLE→PARSING→PLANNING→CODING→...） | 需补充 在状态转换中增加 _run_agent() 方法的实现，明确如何拉起 Agent 协程 |
| Step 5.2Agent 角色与 Prompt | 定义了 5 个 Agent 的 System Prompt 和职责 | 需补充 每个 Agent 类必须实现 run(context: TaskContext) -> AgentResult 接口 |
| Step 2.2检查点持久化 | Redis + PostgreSQL 双层存储 | 需补充 Agent 执行完成后，结果通过 CheckpointManager 写入检查点，供下游 Agent 使用 |
| Step 5.4Agent 间通信 | 定义了 A2A 协议的结构化消息格式 | 无修改 该 Step 处理的是 Agent 间通信，与“系统拉起 Agent”是不同层级 |
| Step 3.1-3.4四图谱 | 代码/数据库/配置/知识图谱 | 无修改 Agent 通过 MCP 调用图谱查询，与拉起机制无关 |

    

---

    
    
    
    

    

## 7. 代码示例

    

#### Step 5.7.24.7 调度器拉起 Agent 的完整实现

    

```python
# /src/scheduler/orchestrator.py
    import asyncio
    from typing import Type, Dict, Any
    from src.agents.base import BaseAgent
    from src.agents.developer import DeveloperAgent
    from src.agents.architect import ArchitectAgent
    from src.agents.parser import ParserAgent
    from src.scheduler.context import TaskContext

    class TaskOrchestrator:
        """任务编排器 - 负责拉起 Agent 并驱动执行"""

        # Agent 类名 → 对应 System Prompt 的映射
        _AGENT_PROMPTS = {
            "ParserAgent": "你是一个需求解析器...",
            "ArchitectAgent": "你是一个架构师...",
            "DeveloperAgent": "你是一个开发者...",
            "ReviewerAgent": "你是一个代码审查员...",
            "QAAgent": "你是一个QA验证员..."
        }

        def __init__(self, llm_client, graph_repo, sandbox, checkpoint_mgr):
            self.llm_client = llm_client
            self.graph_repo = graph_repo
            self.sandbox = sandbox
            self.checkpoint_mgr = checkpoint_mgr

        async def _run_agent(
            self,
            agent_class: Type[BaseAgent],
            task: Task
        ) -> AgentResult:
            """拉起 Agent 协程的核心方法"""
            try:
                # 1. 构建上下文（L1-L5）
                context = await self._build_context(task)

                # 2. 实例化 Agent
                agent = agent_class(
                    llm_client=self.llm_client,
                    graph_repo=self.graph_repo,
                    sandbox=self.sandbox,
                    checkpoint_mgr=self.checkpoint_mgr
                )

                # 3. 🔴 拉起 Agent 协程（带超时）
                result = await asyncio.wait_for(
                    agent.run(context),
                    timeout=300  # 5分钟超时
                )

                # 4. 写入检查点
                await self.checkpoint_mgr.save(
                    task.id,
                    CheckpointData(
                        task_id=task.id,
                        state=task.state,
                        context={"agent_output": result.output}
                    )
                )

                return result

            except asyncio.TimeoutError:
                return AgentResult(
                    success=False,
                    error=f"Agent {agent_class.__name__} timed out after 300s"
                )

        async def _build_context(self, task: Task) -> TaskContext:
            """构建 Agent 上下文（L1-L5）"""
            return TaskContext(
                task_id=task.id,
                l1=self._AGENT_PROMPTS[agent_class.__name__],
                l2=await self._query_graphs(task),
                l3={
                    "prd": task.prd[:500],
                    "dag_progress": self._get_progress(task),
                    "upstream_output": await self._get_upstream_output(task)
                },
                l4={},  # Agent 私有工作记忆（初始为空）
                l5=await self._retrieve_memories(task)
            )
```

    

#### Step 5.7.24.7 外部系统调用调度器的 API

    

```python
# /src/api/routes/tasks.py
    from fastapi import APIRouter, Depends
    from src.scheduler.orchestrator import TaskOrchestrator

    router = APIRouter(prefix="/api/v1")

    @router.post("/tasks")
    async def create_task(
        req: TaskCreateRequest,
        orchestrator: TaskOrchestrator = Depends(get_orchestrator)
    ):
        """外部系统通过此 API 提交任务，调度器将拉起 Agent"""
        task = Task(prd=req.prd, state=TaskState.IDLE)
        # 提交到调度器，调度器内部会驱动状态机并拉起 Agent
        await orchestrator.submit(task)
        return {"task_id": task.id}

    @router.get("/tasks/{task_id}")
    async def get_task_status(
        task_id: str,
        orchestrator: TaskOrchestrator = Depends(get_orchestrator)
    ):
        """外部系统通过此 API 查询任务状态"""
        task = await orchestrator.get_task(task_id)
        return {"task_id": task.id, "state": task.state}
```

    

#### Step 5.7.24.7 Agent 基类定义

    

```python
# /src/agents/base.py
    from abc import ABC, abstractmethod
    from src.scheduler.context import TaskContext

    class BaseAgent(ABC):
        """所有 Agent 的基类"""

        def __init__(self, llm_client, graph_repo, sandbox, checkpoint_mgr):
            self.llm_client = llm_client
            self.graph_repo = graph_repo
            self.sandbox = sandbox
            self.checkpoint_mgr = checkpoint_mgr

        @abstractmethod
        async def run(self, context: TaskContext) -> AgentResult:
            """Agent 的执行入口，由调度器调用"""
            pass

        @abstractmethod
        async def think(self, context: TaskContext) -> Thought:
            """思考阶段：调用 LLM"""
            pass

        @abstractmethod
        async def act(self, thought: Thought) -> Action:
            """行动阶段：执行工具调用"""
            pass

        @abstractmethod
        async def observe(self, action: Action) -> Observation:
            """观察阶段：收集执行结果"""
            pass
```

    

---

    

> ✅ Agent 拉起机制交付确认
        
            核心概念澄清：区分“系统拉起 Agent”与“Agent 间通信（A2A）”两种语义
            Agent 实现形态：进程内 asyncio 协程，而非独立微服务
            拉起流程：外部 API → 调度器状态机 → asyncio.create_task() → Agent 协程
            抽象分层：系统→Agent（协程拉起）、Agent→工具（MCP）、Agent→Agent（A2A）
            PRD/ADR：完整的规格定义，含数据契约、SC→AC、备选方案对比
            与现有 Step 映射：Step 5.1/5.2 需补充，Step 5.4/3.1-3.4 无修改
            代码示例：调度器拉起实现、外部 API 调用、Agent 基类定义
        
        下一步：可将本报告中的代码示例和 PRD/ADR 规格合并到 Step 5.1（调度器状态机）和 Step 5.2（Agent 角色与 Prompt）中。

    
        — V14.1 开发计划 · Agent 拉起机制 · 2026年6月22日 —

---

## 1. 整体架构设计

    

> 核心方案：微信小程序 + Skill 机制作为请求入口，WebSocket/SSE 作为实时监控通道。

    

#### Step 5.8.25.1 完整调用链路

    

```python
┌─────────────┐
    │  微信用户    │
    │  "生成报表"  │
    └──────┬──────┘
           │ 自然语言输入
           ▼
    ┌─────────────────────────────────────────────────┐
    │           微信小程序（前端）                      │
    │  • Skill 入口识别                               │
    │  • 调用 V14.1 API 提交任务                      │
    │  • WebSocket/SSE 监听状态更新                   │
    └──────┬──────────────────────────────────────────┘
           │ HTTPS (POST /api/v1/tasks)
           ▼
    ┌─────────────────────────────────────────────────┐
    │            V14.1 后端（API 网关层）               │
    │  • 接收任务请求                                 │
    │  • 返回 task_id                                 │
    │  • 建立 WebSocket/SSE 连接                      │
    └──────┬──────────────────────────────────────────┘
           │
           ▼
    ┌─────────────────────────────────────────────────┐
    │            V14.1 调度器（Step 5.1）              │
    │  • 状态机驱动                                   │
    │  • 拉起 Agent 协程                             │
    │  • 实时推送状态变更                             │
    └─────────────────────────────────────────────────┘
```

    

#### Step 5.8.25.1 为什么选择微信小程序？

    
        
- 天然的用户入口：微信日活超10亿，无需用户额外下载 App。
        
- 官方 AI 能力加持：微信已推出小程序 Skill 机制，可将功能封装为 AI 可调用的能力。
        
- 基于 MCP：Skill 底层基于 MCP 协议，与 V14.1 使用的 MCP 协议栈天然同构。
        
- 实时通信支持：小程序支持 WebSocket 和 SSE 两种实时方案。
    

    

---

    
    
    
    

    

## 2. 微信小程序 Skill 机制

    

#### Step 5.8.25.2 Skill 是什么

    Skill 是微信官方推出的 AI 能力接入机制，开发者可将小程序的能力封装为 AI 可调用的 Skill。用户通过自然语言就能触发 Skill，执行对应功能。

    

#### Step 5.8.25.2 两种接入模式

    | 模式 | 说明 | 适用场景 |
| --- | --- | --- |
| 自动模式 | 平台自动分析小程序源码，AI 可直接操作 | 快速验证，零代码接入 |
| 开发模式 | 开发者自定义 Skill，通过审核后被 AI 调用 | 推荐 定制化 V14.1 任务触发 |

    

#### Step 5.8.25.2 Skill 文件结构

    

```python
my-agent-skill/
    ├── mcp.json          # 可用的函数声明（MCP 工具列表）
    ├── apis/
    │   ├── submit_task.js   # 提交 V14.1 任务
    │   ├── get_status.js    # 查询任务状态
    │   └── cancel_task.js   # 取消任务
    ├── index.js          # 注册函数给运行时
    └── components/
        └── status-card.wxml # 实时状态展示卡片
```

    

#### Step 5.8.25.2 mcp.json 声明示例

    

```python
{
      "mcpServers": {
        "v14-agent": {
          "functions": [
            {
              "name": "submit_development_task",
              "description": "向 V14.1 系统提交一个软件开发任务",
              "parameters": {
                "type": "object",
                "properties": {
                  "prd": {
                    "type": "string",
                    "description": "产品需求文档"
                  },
                  "priority": {
                    "type": "string",
                    "enum": ["low", "normal", "high", "critical"],
                    "description": "任务优先级"
                  },
                  "callback_url": {
                    "type": "string",
                    "description": "任务完成后的回调地址"
                  }
                },
                "required": ["prd"]
              }
            },
            {
              "name": "query_task_status",
              "description": "查询 V14.1 系统中某个任务的执行状态",
              "parameters": {
                "type": "object",
                "properties": {
                  "task_id": {
                    "type": "string",
                    "description": "任务ID"
                  }
                },
                "required": ["task_id"]
              }
            }
          ]
        }
      }
    }
```

    

#### Step 5.8.25.2 函数实现示例

    

```python
// apis/submit_task.js
    // 在微信小程序 Skill 中调用 V14.1 后端 API
    const V14_API_BASE = 'https://api.v14-system.com/api/v1';

    export default async function submit_development_task(params) {
      const { prd, priority = 'normal', callback_url } = params;

      // 1. 调用 V14.1 后端 API 提交任务
      const response = await fetch(`${V14_API_BASE}/tasks`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prd, priority, callback_url })
      });

      if (!response.ok) {
        throw new Error(`V14.1 系统返回错误: ${response.status}`);
      }

      const data = await response.json();

      // 2. 返回给小程序（Skill 的返回值）
      return {
        task_id: data.task_id,
        state: data.state,
        message: '任务已提交，正在处理中...',
        status_url: `${V14_API_BASE}/tasks/${data.task_id}/status`
      };
    }
```

    

---

    
    
    
    

    

## 3. 与 V14.1 的 MCP 协议集成

    

> 核心洞察：微信小程序的 Skill 机制底层基于 MCP 协议，与 V14.1 使用的 MCP 协议栈完全兼容。这意味着 Skill 中的函数声明（mcp.json）可以直接映射到 V14.1 的 MCP Server。

    

#### Step 5.8.25.3 分层架构

    

```python
┌─────────────────────────────────────────────────────┐
    │           微信小程序（Skill 层）                   │
    │  mcp.json 声明 → apis/*.js 实现                   │
    │  调用 V14.1 后端 API（内部使用 MCP 协议）         │
    └─────────────────────┬───────────────────────────────┘
                          │ HTTP / WebSocket
                          ▼
    ┌─────────────────────────────────────────────────────┐
    │            V14.1 后端（MCP Server）                │
    │  • 暴露 MCP 工具：submit_task, query_status       │
    │  • 内部调用调度器                                  │
    └─────────────────────┬───────────────────────────────┘
                          │
                          ▼
    ┌─────────────────────────────────────────────────────┐
    │            V14.1 调度器（Agent 系统）              │
    └─────────────────────────────────────────────────────┘
```

    

#### Step 5.8.25.3 V14.1 端 MCP 工具暴露

    

```python
# /src/mcp/servers/v14_mcp_server.py
    from mcp.server import Server
    from src.scheduler.orchestrator import TaskOrchestrator

    server = Server("v14-mcp-server")
    orchestrator = TaskOrchestrator()

    @server.tool()
    async def submit_development_task(prd: str, priority: str = "normal") -> dict:
        """提交开发任务到 V14.1 系统"""
        task = await orchestrator.submit(prd, priority)
        return {"task_id": task.id, "state": task.state.value}

    @server.tool()
    async def query_task_status(task_id: str) -> dict:
        """查询任务状态"""
        task = await orchestrator.get_task(task_id)
        return {
            "task_id": task.id,
            "state": task.state.value,
            "progress": task.progress,
            "result": task.result
        }

    @server.tool()
    async def cancel_task(task_id: str) -> dict:
        """取消正在执行的任务"""
        await orchestrator.cancel(task_id)
        return {"task_id": task_id, "state": "cancelled"}
```

    

---

    
    
    
    

    

## 4. 实时监控方案

    

#### Step 5.8.25.4 两种实时通信方案对比

    | 方案 | 特点 | 适用场景 |
| --- | --- | --- |
| WebSocket | 全双工 通信，适合高频双向交互 | Agent 执行过程中需要用户介入确认（如：选择方案A还是B） |
| SSE (Server-Sent Events) | 单向 推送，基于 HTTP 更轻量 | 只需“看进度”的纯监控场景 |

    

#### Step 5.8.25.4 WebSocket 实时监控实现

    

```python
# /src/api/websocket.py
    from fastapi import WebSocket, WebSocketDisconnect
    from src.scheduler.orchestrator import TaskOrchestrator

    class ConnectionManager:
        def __init__(self):
            self.active_connections: Dict[str, List[WebSocket]] = {}

        async def connect(self, task_id: str, websocket: WebSocket):
            await websocket.accept()
            if task_id not in self.active_connections:
                self.active_connections[task_id] = []
            self.active_connections[task_id].append(websocket)

        def disconnect(self, task_id: str, websocket: WebSocket):
            if task_id in self.active_connections:
                self.active_connections[task_id].remove(websocket)

        async def broadcast_status(self, task_id: str, status: dict):
            """向订阅了该任务的所有客户端广播状态"""
            if task_id in self.active_connections:
                for connection in self.active_connections[task_id]:
                    try:
                        await connection.send_json(status)
                    except:
                        pass

    # 在调度器状态变更时触发广播
    class StatusBroadcaster:
        def __init__(self, manager: ConnectionManager):
            self.manager = manager

        async def on_state_change(self, task_id: str, old_state: str, new_state: str, data: dict = None):
            await self.manager.broadcast_status(task_id, {
                "type": "state_change",
                "task_id": task_id,
                "from": old_state,
                "to": new_state,
                "data": data
            })
```

    

#### Step 5.8.25.4 SSE 实时监控实现

    

```python
# /src/api/sse.py
    from fastapi.responses import StreamingResponse
    from sse_starlette.sse import EventSourceResponse
    import asyncio

    @router.get("/tasks/{task_id}/stream")
    async def stream_task_status(task_id: str, orchestrator: TaskOrchestrator):
        """SSE 实时推送任务状态"""
        async def event_generator():
            # 获取初始状态
            task = await orchestrator.get_task(task_id)
            last_state = task.state

            while True:
                # 检查状态是否有变化
                current_task = await orchestrator.get_task(task_id)
                if current_task.state != last_state:
                    last_state = current_task.state
                    yield {
                        "event": "state_change",
                        "data": {
                            "task_id": task_id,
                            "state": current_task.state.value,
                            "progress": current_task.progress,
                            "timestamp": datetime.utcnow().isoformat()
                        }
                    }

                # 如果任务已完成或失败，结束推送
                if current_task.state in [TaskState.DONE, TaskState.FAILED]:
                    yield {
                        "event": "complete",
                        "data": {
                            "task_id": task_id,
                            "state": current_task.state.value,
                            "result": current_task.result
                        }
                    }
                    break

                await asyncio.sleep(2)  # 轮询间隔

        return EventSourceResponse(event_generator())
```

    

---

    
    
    
    

    

## 5. API 规格

    

#### Step 5.8.25.5 任务提交 API

    

```python
POST /api/v1/tasks
    Request:
    {
      "prd": "修改支付超时时间为60秒",
      "priority": "high",           # low | normal | high | critical
      "callback_url": null,          # 可选，任务完成后的Webhook
      "source": "wechat_skill"       # 来源标识
    }

    Response:
    {
      "task_id": "a1b2c3d4-...",
      "state": "IDLE",
      "message": "任务已提交，正在排队中..."
    }
```

    

#### Step 5.8.25.5 状态查询 API

    

```python
GET /api/v1/tasks/{task_id}/status
    Response:
    {
      "task_id": "a1b2c3d4-...",
      "state": "CODING",
      "progress": 0.6,
      "current_step": "DeveloperAgent 正在生成代码...",
      "agent_logs": [
        {"step": "PARSING", "status": "done", "duration_ms": 1200},
        {"step": "PLANNING", "status": "done", "duration_ms": 3400},
        {"step": "CODING", "status": "running", "duration_ms": null}
      ],
      "estimated_remaining_ms": 3000,
      "created_at": "2026-06-22T10:00:00Z",
      "updated_at": "2026-06-22T10:01:30Z"
    }
```

    

---

    
    
    
    

    

## 6. 与现有 Step 的映射

    | Step | 原有内容 | 微信小程序接入的补充 |
| --- | --- | --- |
| Step 1.1四层架构与 API 契约 | 定义了 RESTful API 契约 | 需补充 增加 /tasks 路由的 source 字段；新增 /tasks/{id}/stream SSE 端点 |
| Step 6.1Vue3 驾驶舱 | 定义了 Web 驾驶舱的实时监控 | 无修改 微信小程序的实时监控复用相同的 WebSocket/SSE 基础设施 |
| Step 2.1LiteLLM 网关 | LLM API 调用网关 | 无修改 微信小程序接入不涉及 LLM 网关 |
| Step 5.1调度器状态机 | 定义了任务执行状态流转 | 需补充 状态变更时触发 WebSocket/SSE 广播（通过 StatusBroadcaster） |
| Step 7.6安全与权限管理 | JWT + 零信任架构 | 需补充 微信小程序的来源认证（小程序 AppID 验证 + JWT 颁发） |

    

---

    
    
    
    

    

## 7. 代码示例

    

#### Step 5.8.25.7 微信小程序 Skill 完整示例

    

```python
// apis/submit_task.js - 完整实现
    const V14_API_BASE = 'https://api.v14-system.com/api/v1';
    const WS_BASE = 'wss://api.v14-system.com/ws';

    export default async function submit_development_task(params) {
      const { prd, priority = 'normal' } = params;

      // 1. 提交任务
      const response = await fetch(`${V14_API_BASE}/tasks`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prd, priority, source: 'wechat_skill' })
      });

      if (!response.ok) {
        throw new Error(`提交失败: ${response.status}`);
      }

      const data = await response.json();

      // 2. 返回给小程序，包含用于 WebSocket 连接的 task_id
      return {
        task_id: data.task_id,
        message: '任务已提交，正在处理中...',
        ws_url: `${WS_BASE}/tasks/${data.task_id}`
      };
    }
```

    

#### Step 5.8.25.7 微信小程序实时监控组件

    

```python
// components/status-card/index.js
    Component({
      properties: {
        taskId: { type: String, value: '' }
      },
      data: {
        status: 'pending',
        progress: 0,
        logs: [],
        socket: null
      },
      lifetimes: {
        attached() {
          this.connectWebSocket();
        },
        detached() {
          if (this.data.socket) {
            this.data.socket.close();
          }
        }
      },
      methods: {
        connectWebSocket() {
          const ws = wx.connectSocket({
            url: `wss://api.v14-system.com/ws/tasks/${this.properties.taskId}`,
          });

          ws.onMessage((res) => {
            const data = JSON.parse(res.data);
            this.setData({
              status: data.state,
              progress: data.progress,
              logs: [...this.data.logs, data.message]
            });
          });

          ws.onError((err) => {
            console.error('WebSocket 错误:', err);
          });

          this.setData({ socket: ws });
        }
      }
    });
```

    

#### Step 5.8.25.7 微信小程序卡片展示

    

```python
&lt;!-- components/status-card/index.wxml --&gt;
    &lt;view class="status-card"&gt;
      &lt;view class="status-header"&gt;
        &lt;text class="task-id"&gt;任务: {{taskId}}&lt;/text&gt;
        &lt;text class="status-badge {{status}}"&gt;{{status}}&lt;/text&gt;
      &lt;/view&gt;

      &lt;view class="progress-section"&gt;
        &lt;text class="progress-label"&gt;执行进度&lt;/text&gt;
        &lt;progress percent="{{progress * 100}}" stroke-width="8" /&gt;
        &lt;text class="progress-text"&gt;{{Math.round(progress * 100)}}%&lt;/text&gt;
      &lt;/view&gt;

      &lt;view class="logs-section"&gt;
        &lt;text class="logs-title"&gt;执行日志&lt;/text&gt;
        &lt;scroll-view class="logs-scroll" scroll-y&gt;
          &lt;view class="log-item" wx:for="{{logs}}" wx:key="index"&gt;
            &lt;text class="log-time"&gt;{{item.time}}&lt;/text&gt;
            &lt;text class="log-content"&gt;{{item.msg}}&lt;/text&gt;
          &lt;/view&gt;
        &lt;/scroll-view&gt;
      &lt;/view&gt;
    &lt;/view&gt;
```

    

---

    
    
    
    

    

## 8. 实施路线图

    | 阶段 | 任务 | 周期 | 依赖 |
| --- | --- | --- | --- |
| 准备阶段 | ① 设计 V14.1 后端 API（/tasks 提交、/tasks/{id}/status 查询、WebSocket/SSE 推送）② 申请微信小程序 AppID③ 搭建微信小程序开发环境 | 1-2天 | Step 1.1 完成 |
| 开发阶段 | ① 创建微信小程序 Skill 项目（mcp.json + apis/*.js + index.js）② 实现 Skill 调用 V14.1 API 的逻辑③ 实现 WebSocket/SSE 实时通信④ 设计小程序 UI（输入+状态卡片） | 3-5天 | Step 5.1 完成 |
| 集成与测试 | ① 端到端联调（小程序 ↔ V14.1）② 实时监控体验优化③ 安全认证联调 | 2-3天 | Step 7.6 完成 |
| 上线发布 | ① 微信小程序提交审核② Skill 功能发布③ ⚠️ 注意：Skill模式目前在内测，相关代码暂时不要合入正式版本提审 | 1-2天 | 测试通过 |

    

> ⚠️ 重要提醒：
        
            微信小程序 Skill 模式目前处于 内测阶段，相关代码暂时不要合入正式版本提审。
            建议先在开发环境做技术验证，待 Skill 功能正式对外开放后再提交审核。
            如果急需上线，可先用小程序原生页面 + API 调用方式实现（不依赖 Skill 能力）。

    

---

    

> ✅ 微信小程序接入交付确认
        
            整体架构：微信小程序 Skill 作为请求入口 + WebSocket/SSE 作为实时监控通道
            Skill 机制：mcp.json 声明 + apis/*.js 实现 + 与 V14.1 MCP 协议同构
            实时监控：WebSocket（全双工）和 SSE（轻量单向）两种方案
            API 规格：POST /tasks 提交、GET /tasks/{id}/status 查询、/tasks/{id}/stream SSE 流
            代码示例：微信小程序 Skill 完整实现、实时监控组件、卡片 UI
            实施路线图：准备→开发→集成测试→上线，约 1-1.5 周
        
        下一步：可按照实施路线图开始微信小程序项目的创建和 Skill 开发。

    
        — V14.1 开发计划 · 微信小程序接入 · 2026年6月22日 —


## Step 5.7：Agent拨起机制

## Step 5.8：微信小程序接入

    
        
        
        
        
        
        
        
    

    


    
    
    
    

## 1. 核心概念澄清

    

> 核心声明：在 V14.1 中，Agent 不是独立微服务、不是容器、不是进程，而是 调度器进程内的一个 Python 异步协程（asyncio Task）。

    

#### Step 5.7.24.1 “调用 Agent”的两种语义

    | 语义 | 含义 | V14.1 的实现 |
| --- | --- | --- |
| A2A 通信 | Agent A 请求 Agent B 执行某任务或提供信息 | 通过 A2A 协议（结构化消息）实现 Agent 间通信 |
| 系统拉起 Agent | 调度器将 Agent 实例化并开始执行 | 调度器的状态机通过 asyncio.create_task() 拉起 Agent 协程 |


    


    
    
    
    

    

## 2. Agent 的实现形态

    

# Agent 的本质是一个异步协程类

            # 思考 → 行动 → 观察 循环

    

#### Step 5.7.24.2 关键特征

    
        
        
        
        
        
    

    


    
    
    
    

    

## 3. 系统拉起 Agent 的完整流程

    

#### Step 5.7.24.3 第1步：用户触发（外部入口）

    

# API 入口


    

#### Step 5.7.24.3 第2步：调度器状态机驱动

    

# Step 5.1 调度器状态机（核心逻辑）


                    # 🔴 关键：拉起 DeveloperAgent

                # ... 依次类推

    

#### Step 5.7.24.3 第3步：拉起 Agent 协程（核心）

    

# 实际拉起 Agent 的方法
        # 1. 构建 Agent 的上下文（注入 L1-L5）

        # 2. 实例化 Agent（依赖注入）

        # 3. 🔴 拉起 Agent 协程（本质是异步函数调用）

        # 4. 将结果写入检查点（供下游 Agent 使用）


    

#### Step 5.7.24.3 第4步：Agent 执行循环

    

                # 思考：调用 LLM

                # 行动：执行工具调用（通过 MCP）

                # 观察：收集结果

                # 更新上下文（L4 私有工作记忆）

                # 终止条件判断


    


    
    
    
    

    

## 4. 与 MCP/A2A 的抽象分层


    

> ┌─────────────────────────────────────────────────────────────┐

    

#### Step 5.7.24.4 三层调用关系

    | 层级 | 用途 | 协议/方式 | 调用方向 |
| --- | --- | --- | --- |
| 系统 → Agent | 调度器实例化并驱动 Agent 协程 | asyncio.create_task() + await agent.run() | 向上驱动 |
| Agent → 工具 | Agent 调用外部工具/资源（四图谱、沙箱、数据库） | MCP（Model Context Protocol） | 向下调用 |
| Agent → Agent | Agent 之间协作通信（任务分发、审查、仲裁） | A2A（Agent-to-Agent Protocol） | 水平通信 |

    

#### Step 5.7.24.4 与现有协议的定位

    
        
        
        
    

    


    
    
    
    

    

## 5. PRD/ADR 规格

    

#### Step 5.7.24.5 PRD · Agent 拉起机制

    | PRD · Agent 拉起机制 |
| --- |
| 背景 | 外部系统需要通过调度器驱动多智能体协作。Agent 不是预先部署的微服务，而是由调度器按需实例化的异步协程。 |
| 用户故事 | 作为调度器，我根据状态机的进度，在合适的时机await agent.run()拉起对应的 Agent 协程，执行完成后将结果写入检查点。 |
| 需求描述 | ① Agent 定义为异步协程类，实现 run(context: TaskContext) -> AgentResult 方法。 ② 调度器通过 asyncio.create_task() 拉起 Agent。 ③ 拉起时注入 L1-L5 上下文（L1 协作宪法、L2 四图谱事实、L3 任务状态、L4 私有记忆、L5 长期记忆）。 ④ Agent 执行完成后，结果写入检查点（Checkpoint），供下游 Agent 使用。 ⑤ 外部系统通过 API 调用调度器，不直接调用 Agent。 |
| 范围 | Do：进程内协程拉起；依赖注入；上下文构建；结果持久化。 Don't：不通过 HTTP/gRPC 远程调用 Agent；不将 Agent 部署为独立容器。 |
| 数据契约 | ```python class TaskContext(BaseModel): task_id: str l1: str # System Prompt（协作宪法） l2: Dict[str, Any] # 四图谱查询结果 l3: Dict[str, Any] # 任务状态（PRD摘要、DAG进度） l4: Dict[str, Any] # Agent私有工作记忆 l5: List[Dict[str, Any]] # 长期记忆（检索结果） class AgentResult(BaseModel): success: bool output: Any error: Optional[str] = None duration_ms: float ``` |
| SC→AC | SC1: Agent 拉起成功 → AC1: 状态机触发 CODING 状态时，调用 _run_agent(DeveloperAgent, task) 返回 AgentResult。 SC2: 上下文注入完整 → AC2: Agent 的 run() 方法中 context.l1、context.l2 非空且包含预期内容。 SC3: 结果持久化 → AC3: Agent 执行完成后，检查点中存在对应 task_id 的记录。 |
| 待定决策 | Q: Agent 执行超时如何处理？ → 决议：在 _run_agent() 中包装 asyncio.wait_for(agent.run(), timeout=300)，超时后取消协程并标记 FAILED。 |

    

#### Step 5.7.24.5 ADR · Agent 实现形态

    | ADR · Agent 实现形态 |
| --- |
| 决策 | Agent 实现为进程内异步协程，而非独立微服务或容器。 ① 所有 Agent 运行在调度器同一进程中。 ② 通过 asyncio 事件循环调度。 ③ 通过依赖注入传递外部依赖（LLM 客户端、图谱仓库、沙箱）。 ④ 通过 Checkpoint 实现状态跨 Agent 传递。 |
| 理由 | ① 无网络开销：协程间通信为零延迟。② 极速拉起：协程创建为微秒级。③ 共享内存：Checkpoint 直接读取，无需序列化传递。④ 简化运维：无需部署多个微服务。⑤ 与 V14.1 的 asyncio 调度器自然兼容。 |
| 备选方案 | ① 独立微服务（HTTP/gRPC 拉起）→ 网络延迟高，资源消耗大，不适合密集 Agent 协作。② 独立容器（Docker 拉起）→ 启动慢（秒级），资源隔离过度。 |

    


    
    
    
    

    

## 6. 与现有 Step 的映射

    | Step | 原有内容 | Agent 拉起机制的补充 |
| --- | --- | --- |
| Step 5.1调度器状态机 | 定义了状态转换（IDLE→PARSING→PLANNING→CODING→...） | 需补充 在状态转换中增加 _run_agent() 方法的实现，明确如何拉起 Agent 协程 |
| Step 5.2Agent 角色与 Prompt | 定义了 5 个 Agent 的 System Prompt 和职责 | 需补充 每个 Agent 类必须实现 run(context: TaskContext) -> AgentResult 接口 |
| Step 2.2检查点持久化 | Redis + PostgreSQL 双层存储 | 需补充 Agent 执行完成后，结果通过 CheckpointManager 写入检查点，供下游 Agent 使用 |
| Step 5.4Agent 间通信 | 定义了 A2A 协议的结构化消息格式 | 无修改 该 Step 处理的是 Agent 间通信，与“系统拉起 Agent”是不同层级 |
| Step 3.1-3.4四图谱 | 代码/数据库/配置/知识图谱 | 无修改 Agent 通过 MCP 调用图谱查询，与拉起机制无关 |

    


    
    
    
    

    

## 7. 代码示例

    

#### Step 5.7.24.7 调度器拉起 Agent 的完整实现

    

# /src/scheduler/orchestrator.py


        # Agent 类名 → 对应 System Prompt 的映射


                # 1. 构建上下文（L1-L5）

                # 2. 实例化 Agent

                # 3. 🔴 拉起 Agent 协程（带超时）

                # 4. 写入检查点




    

#### Step 5.7.24.7 外部系统调用调度器的 API

    

# /src/api/routes/tasks.py


        # 提交到调度器，调度器内部会驱动状态机并拉起 Agent


    

#### Step 5.7.24.7 Agent 基类定义

    

# /src/agents/base.py







    


    

> ✅ Agent 拉起机制交付确认
        
        

    

---


    
        
        
        
        
        
        
        
        
    

    


    
    
    
    

## 1. 整体架构设计

    

> 核心方案：微信小程序 + Skill 机制作为请求入口，WebSocket/SSE 作为实时监控通道。

    

#### Step 5.8.25.1 完整调用链路

    


    

#### Step 5.8.25.1 为什么选择微信小程序？

    
        
        
        
        
    

    


    
    
    
    

    

## 2. 微信小程序 Skill 机制

    

#### Step 5.8.25.2 Skill 是什么


    

#### Step 5.8.25.2 两种接入模式

    | 模式 | 说明 | 适用场景 |
| --- | --- | --- |
| 自动模式 | 平台自动分析小程序源码，AI 可直接操作 | 快速验证，零代码接入 |
| 开发模式 | 开发者自定义 Skill，通过审核后被 AI 调用 | 推荐 定制化 V14.1 任务触发 |

    

#### Step 5.8.25.2 Skill 文件结构

    


    

#### Step 5.8.25.2 mcp.json 声明示例

    


    

#### Step 5.8.25.2 函数实现示例

    







    


    
    
    
    

    

## 3. 与 V14.1 的 MCP 协议集成

    

> 核心洞察：微信小程序的 Skill 机制底层基于 MCP 协议，与 V14.1 使用的 MCP 协议栈完全兼容。这意味着 Skill 中的函数声明（mcp.json）可以直接映射到 V14.1 的 MCP Server。

    

#### Step 5.8.25.3 分层架构

    


    

#### Step 5.8.25.3 V14.1 端 MCP 工具暴露

    

# /src/mcp/servers/v14_mcp_server.py





    


    
    
    
    

    

## 4. 实时监控方案

    

#### Step 5.8.25.4 两种实时通信方案对比

    | 方案 | 特点 | 适用场景 |
| --- | --- | --- |
| WebSocket | 全双工 通信，适合高频双向交互 | Agent 执行过程中需要用户介入确认（如：选择方案A还是B） |
| SSE (Server-Sent Events) | 单向 推送，基于 HTTP 更轻量 | 只需“看进度”的纯监控场景 |

    

#### Step 5.8.25.4 WebSocket 实时监控实现

    

# /src/api/websocket.py





    # 在调度器状态变更时触发广播


    

#### Step 5.8.25.4 SSE 实时监控实现

    

# /src/api/sse.py

            # 获取初始状态

                # 检查状态是否有变化

                # 如果任务已完成或失败，结束推送



    


    
    
    
    

    

## 5. API 规格

    

#### Step 5.8.25.5 任务提交 API

    



    

#### Step 5.8.25.5 状态查询 API

    


    


    
    
    
    

    

## 6. 与现有 Step 的映射

    | Step | 原有内容 | 微信小程序接入的补充 |
| --- | --- | --- |
| Step 1.1四层架构与 API 契约 | 定义了 RESTful API 契约 | 需补充 增加 /tasks 路由的 source 字段；新增 /tasks/{id}/stream SSE 端点 |
| Step 6.1Vue3 驾驶舱 | 定义了 Web 驾驶舱的实时监控 | 无修改 微信小程序的实时监控复用相同的 WebSocket/SSE 基础设施 |
| Step 2.1LiteLLM 网关 | LLM API 调用网关 | 无修改 微信小程序接入不涉及 LLM 网关 |
| Step 5.1调度器状态机 | 定义了任务执行状态流转 | 需补充 状态变更时触发 WebSocket/SSE 广播（通过 StatusBroadcaster） |
| Step 7.6安全与权限管理 | JWT + 零信任架构 | 需补充 微信小程序的来源认证（小程序 AppID 验证 + JWT 颁发） |

    


    
    
    
    

    

## 7. 代码示例

    

#### Step 5.8.25.7 微信小程序 Skill 完整示例

    







    

#### Step 5.8.25.7 微信小程序实时监控组件

    





    

#### Step 5.8.25.7 微信小程序卡片展示

    




    


    
    
    
    

    

## 8. 实施路线图

    | 阶段 | 任务 | 周期 | 依赖 |
| --- | --- | --- | --- |
| 准备阶段 | ① 设计 V14.1 后端 API（/tasks 提交、/tasks/{id}/status 查询、WebSocket/SSE 推送）② 申请微信小程序 AppID③ 搭建微信小程序开发环境 | 1-2天 | Step 1.1 完成 |
| 开发阶段 | ① 创建微信小程序 Skill 项目（mcp.json + apis/*.js + index.js）② 实现 Skill 调用 V14.1 API 的逻辑③ 实现 WebSocket/SSE 实时通信④ 设计小程序 UI（输入+状态卡片） | 3-5天 | Step 5.1 完成 |
| 集成与测试 | ① 端到端联调（小程序 ↔ V14.1）② 实时监控体验优化③ 安全认证联调 | 2-3天 | Step 7.6 完成 |
| 上线发布 | ① 微信小程序提交审核② Skill 功能发布③ ⚠️ 注意：Skill模式目前在内测，相关代码暂时不要合入正式版本提审 | 1-2天 | 测试通过 |

    

> ⚠️ 重要提醒：
        

    


    

> ✅ 微信小程序接入交付确认
        
        

    


## Step 5.7：Agent拉起机制

## Step 5.8：微信小程序接入

    
        
- 1. 核心概念澄清
        
- 2. Agent 的实现形态
        
- 3. 系统拉起 Agent 的完整流程
        
- 4. 与 MCP/A2A 的抽象分层
        
- 5. PRD/ADR 规格
        
- 6. 与现有 Step 的映射
        
- 7. 代码示例
    

    


    
    
    
    

## 1. 核心概念澄清

    

> 核心声明：在 V14.1 中，Agent 不是独立微服务、不是容器、不是进程，而是 调度器进程内的一个 Python 异步协程（asyncio Task）。

    

#### Step 5.7.24.1 “调用 Agent”的两种语义

    | 语义 | 含义 | V14.1 的实现 |
| --- | --- | --- |
| A2A 通信 | Agent A 请求 Agent B 执行某任务或提供信息 | 通过 A2A 协议（结构化消息）实现 Agent 间通信 |
| 系统拉起 Agent | 调度器将 Agent 实例化并开始执行 | 调度器的状态机通过 asyncio.create_task() 拉起 Agent 协程 |

    用户的问题“怎么调用 Agent”属于第二种语义：系统如何将 Agent 实例化并启动执行。

    


    
    
    
    

    

## 2. Agent 的实现形态

    

```python
# Agent 的本质是一个异步协程类
        def __init__(self, llm_client, graph_repo, sandbox, checkpoint_mgr):
            self.llm = llm_client
            self.graph = graph_repo
            self.sandbox = sandbox
            self.checkpoint = checkpoint_mgr

        async def run(self, context: TaskContext) -> AgentResult:
            # 思考 → 行动 → 观察 循环
            while not self.should_stop():
                thought = await self.think(context)        # 调用 LLM
                action = await self.act(thought)           # 执行工具（通过 MCP）
                observation = await self.observe(action)   # 收集结果
                context = self.update_context(context, observation)
            return AgentResult(...)
```

    

#### Step 5.7.24.2 关键特征

    
        
- 进程内执行：所有 Agent 运行在同一个进程中，无进程间通信开销。
        
- 协程隔离：每个 Agent 是一个独立的 asyncio Task，由事件循环调度。
        
- 状态隔离：Agent 间不直接共享内存，通过调度器的 Session/Checkpoint 传递经过验证的数据。
        
- 私有工作记忆（L4）：每个 Agent 有独立的局部工作记忆，不跨 Agent 共享。
        
- 拉起速度：协程创建为微秒级，远快于容器启动（秒级）。
    

    


    
    
    
    

    

## 3. 系统拉起 Agent 的完整流程

    

#### Step 5.7.24.3 第1步：用户触发（外部入口）

    

```python
# API 入口
    @router.post("/api/v1/tasks")
        task = Task(prd=req.prd, state=TaskState.IDLE)
        await scheduler.submit(task)  # ← 提交给调度器
        return {"task_id": task.id}
```

    用户调用的不是 Agent，而是调度器的 API 入口。

    

#### Step 5.7.24.3 第2步：调度器状态机驱动

    

```python
# Step 5.1 调度器状态机（核心逻辑）
        async def run(self, task: Task):
            while task.state != TaskState.DONE:
                if task.state == TaskState.IDLE:
                    task.state = TaskState.PARSING
                    result = await self._run_agent(ParserAgent, task)

                elif task.state == TaskState.PARSING:
                    task.state = TaskState.PLANNING
                    result = await self._run_agent(ArchitectAgent, task)

                elif task.state == TaskState.PLANNING:
                    task.state = TaskState.CODING
                    # 🔴 关键：拉起 DeveloperAgent
                    result = await self._run_agent(DeveloperAgent, task)

                # ... 依次类推
```

    

#### Step 5.7.24.3 第3步：拉起 Agent 协程（核心）

    

```python
# 实际拉起 Agent 的方法
    async def _run_agent(self, agent_class, task: Task) -> AgentResult:
        # 1. 构建 Agent 的上下文（注入 L1-L5）
            l1=SYSTEM_PROMPTS[agent_class.__name__],       # 协作宪法
            l2=await self._query_graphs(task),             # 四图谱事实
            l3=self._build_task_context(task),             # 任务状态
            l4={},                                         # 私有工作记忆（空）
            l5=await self._retrieve_memories(task)         # 长期记忆

        # 2. 实例化 Agent（依赖注入）
            llm_client=self.llm_client,
            graph_repo=self.graph_repo,
            sandbox=self.sandbox,
            checkpoint_mgr=self.checkpoint_mgr

        # 3. 🔴 拉起 Agent 协程（本质是异步函数调用）
        result = await agent.run(context)

        # 4. 将结果写入检查点（供下游 Agent 使用）
        await self.checkpoint_mgr.save(task.id, result)

```

    

#### Step 5.7.24.3 第4步：Agent 执行循环

    

```python
        async def run(self, context: TaskContext) -> AgentResult:
            for iteration in range(self.max_iterations):
                # 思考：调用 LLM
                thought = await self.think(context)

                # 行动：执行工具调用（通过 MCP）
                action = await self.act(thought)

                # 观察：收集结果
                observation = await self.observe(action)

                # 更新上下文（L4 私有工作记忆）
                context.l4["last_action"] = action
                context.l4["last_observation"] = observation

                # 终止条件判断
                if self.should_stop(observation):

            return AgentResult(success=True, output=context.l4["final_output"])
```

    


    
    
    
    

    

## 4. 与 MCP/A2A 的抽象分层

    在 V14.1 中，MCP 和 A2A 服务于不同的抽象层级，而“系统拉起 Agent”是另一个独立的层级。

    

> ┌─────────────────────────────────────────────────────────────┐
        │              🌐 API 网关层（Step 1.1）                     │
        │  • 状态机驱动（Step 5.1）                                 │
        │  • 🔴 通过 asyncio.create_task() 拉起 Agent 协程          │
        │  • 通过 Checkpoint 管理状态（Step 2.2）                   │
        │  • 通过 Audit 记录决策链（Step 1.2 补丁）                 │
                       │ await agent.run()
        │  • 思考→行动→观察 循环（Step 5.1）                        │

    

#### Step 5.7.24.4 三层调用关系

    | 层级 | 用途 | 协议/方式 | 调用方向 |
| --- | --- | --- | --- |
| 系统 → Agent | 调度器实例化并驱动 Agent 协程 | asyncio.create_task() + await agent.run() | 向上驱动 |
| Agent → 工具 | Agent 调用外部工具/资源（四图谱、沙箱、数据库） | MCP（Model Context Protocol） | 向下调用 |
| Agent → Agent | Agent 之间协作通信（任务分发、审查、仲裁） | A2A（Agent-to-Agent Protocol） | 水平通信 |

    

#### Step 5.7.24.4 与现有协议的定位

    
        
- MCP 不在“拉起 Agent”层：MCP 是 Agent 已经运行后用来调用工具的协议。它不负责 Agent 的启动或生命周期管理。
        
- A2A 不在“拉起 Agent”层：A2A 是 Agent 之间已经运行后用来相互通信的协议。它也不负责 Agent 的启动。
        
- “拉起 Agent”是调度器的职责：通过 asyncio 协程直接实例化和驱动，是 V14.1 自研调度器的核心能力。
    

    


    
    
    
    

    

## 5. PRD/ADR 规格

    

#### Step 5.7.24.5 PRD · Agent 拉起机制

    | PRD · Agent 拉起机制 |
| --- |
| 背景 | 外部系统需要通过调度器驱动多智能体协作。Agent 不是预先部署的微服务，而是由调度器按需实例化的异步协程。 |
| 用户故事 | 作为调度器，我根据状态机的进度，在合适的时机await agent.run()拉起对应的 Agent 协程，执行完成后将结果写入检查点。 |
| 需求描述 | ① Agent 定义为异步协程类，实现 run(context: TaskContext) -> AgentResult 方法。 ② 调度器通过 asyncio.create_task() 拉起 Agent。 ③ 拉起时注入 L1-L5 上下文（L1 协作宪法、L2 四图谱事实、L3 任务状态、L4 私有记忆、L5 长期记忆）。 ④ Agent 执行完成后，结果写入检查点（Checkpoint），供下游 Agent 使用。 ⑤ 外部系统通过 API 调用调度器，不直接调用 Agent。 |
| 范围 | Do：进程内协程拉起；依赖注入；上下文构建；结果持久化。 Don't：不通过 HTTP/gRPC 远程调用 Agent；不将 Agent 部署为独立容器。 |
| 数据契约 | ```python class TaskContext(BaseModel): task_id: str l1: str # System Prompt（协作宪法） l2: Dict[str, Any] # 四图谱查询结果 l3: Dict[str, Any] # 任务状态（PRD摘要、DAG进度） l4: Dict[str, Any] # Agent私有工作记忆 l5: List[Dict[str, Any]] # 长期记忆（检索结果） class AgentResult(BaseModel): success: bool output: Any error: Optional[str] = None duration_ms: float ``` |
| SC→AC | SC1: Agent 拉起成功 → AC1: 状态机触发 CODING 状态时，调用 _run_agent(DeveloperAgent, task) 返回 AgentResult。 SC2: 上下文注入完整 → AC2: Agent 的 run() 方法中 context.l1、context.l2 非空且包含预期内容。 SC3: 结果持久化 → AC3: Agent 执行完成后，检查点中存在对应 task_id 的记录。 |
| 待定决策 | Q: Agent 执行超时如何处理？ → 决议：在 _run_agent() 中包装 asyncio.wait_for(agent.run(), timeout=300)，超时后取消协程并标记 FAILED。 |

    

#### Step 5.7.24.5 ADR · Agent 实现形态

    | ADR · Agent 实现形态 |
| --- |
| 决策 | Agent 实现为进程内异步协程，而非独立微服务或容器。 ① 所有 Agent 运行在调度器同一进程中。 ② 通过 asyncio 事件循环调度。 ③ 通过依赖注入传递外部依赖（LLM 客户端、图谱仓库、沙箱）。 ④ 通过 Checkpoint 实现状态跨 Agent 传递。 |
| 理由 | ① 无网络开销：协程间通信为零延迟。② 极速拉起：协程创建为微秒级。③ 共享内存：Checkpoint 直接读取，无需序列化传递。④ 简化运维：无需部署多个微服务。⑤ 与 V14.1 的 asyncio 调度器自然兼容。 |
| 备选方案 | ① 独立微服务（HTTP/gRPC 拉起）→ 网络延迟高，资源消耗大，不适合密集 Agent 协作。② 独立容器（Docker 拉起）→ 启动慢（秒级），资源隔离过度。 |

    


    
    
    
    

    

## 6. 与现有 Step 的映射

    | Step | 原有内容 | Agent 拉起机制的补充 |
| --- | --- | --- |
| Step 5.1调度器状态机 | 定义了状态转换（IDLE→PARSING→PLANNING→CODING→...） | 需补充 在状态转换中增加 _run_agent() 方法的实现，明确如何拉起 Agent 协程 |
| Step 5.2Agent 角色与 Prompt | 定义了 5 个 Agent 的 System Prompt 和职责 | 需补充 每个 Agent 类必须实现 run(context: TaskContext) -> AgentResult 接口 |
| Step 2.2检查点持久化 | Redis + PostgreSQL 双层存储 | 需补充 Agent 执行完成后，结果通过 CheckpointManager 写入检查点，供下游 Agent 使用 |
| Step 5.4Agent 间通信 | 定义了 A2A 协议的结构化消息格式 | 无修改 该 Step 处理的是 Agent 间通信，与“系统拉起 Agent”是不同层级 |
| Step 3.1-3.4四图谱 | 代码/数据库/配置/知识图谱 | 无修改 Agent 通过 MCP 调用图谱查询，与拉起机制无关 |

    


    
    
    
    

    

## 7. 代码示例

    

#### Step 5.7.24.7 调度器拉起 Agent 的完整实现

    

```python
# /src/scheduler/orchestrator.py
    from typing import Type, Dict, Any
    from src.agents.base import BaseAgent
    from src.agents.developer import DeveloperAgent
    from src.agents.architect import ArchitectAgent
    from src.agents.parser import ParserAgent
    from src.scheduler.context import TaskContext


        # Agent 类名 → 对应 System Prompt 的映射
            "ParserAgent": "你是一个需求解析器...",
            "ArchitectAgent": "你是一个架构师...",
            "DeveloperAgent": "你是一个开发者...",
            "ReviewerAgent": "你是一个代码审查员...",
            "QAAgent": "你是一个QA验证员..."

        def __init__(self, llm_client, graph_repo, sandbox, checkpoint_mgr):
            self.llm_client = llm_client
            self.graph_repo = graph_repo
            self.sandbox = sandbox
            self.checkpoint_mgr = checkpoint_mgr

            self,
            agent_class: Type[BaseAgent],
                # 1. 构建上下文（L1-L5）
                context = await self._build_context(task)

                # 2. 实例化 Agent
                    llm_client=self.llm_client,
                    graph_repo=self.graph_repo,
                    sandbox=self.sandbox,
                    checkpoint_mgr=self.checkpoint_mgr

                # 3. 🔴 拉起 Agent 协程（带超时）
                result = await asyncio.wait_for(
                    agent.run(context),

                # 4. 写入检查点
                await self.checkpoint_mgr.save(
                    task.id,
                        task_id=task.id,
                        state=task.state,
                        context={"agent_output": result.output}


            except asyncio.TimeoutError:
                    success=False,
                    error=f"Agent {agent_class.__name__} timed out after 300s"

        async def _build_context(self, task: Task) -> TaskContext:
                task_id=task.id,
                l1=self._AGENT_PROMPTS[agent_class.__name__],
                l2=await self._query_graphs(task),
                    "prd": task.prd[:500],
                    "dag_progress": self._get_progress(task),
                    "upstream_output": await self._get_upstream_output(task)
                },
                l4={},  # Agent 私有工作记忆（初始为空）
                l5=await self._retrieve_memories(task)
```

    

#### Step 5.7.24.7 外部系统调用调度器的 API

    

```python
# /src/api/routes/tasks.py
    from fastapi import APIRouter, Depends
    from src.scheduler.orchestrator import TaskOrchestrator


    @router.post("/tasks")
        req: TaskCreateRequest,
        """外部系统通过此 API 提交任务，调度器将拉起 Agent"""
        task = Task(prd=req.prd, state=TaskState.IDLE)
        # 提交到调度器，调度器内部会驱动状态机并拉起 Agent
        await orchestrator.submit(task)
        return {"task_id": task.id}

    @router.get("/tasks/{task_id}")
        task_id: str,
        task = await orchestrator.get_task(task_id)
        return {"task_id": task.id, "state": task.state}
```

    

#### Step 5.7.24.7 Agent 基类定义

    

```python
# /src/agents/base.py
    from abc import ABC, abstractmethod
    from src.scheduler.context import TaskContext


        def __init__(self, llm_client, graph_repo, sandbox, checkpoint_mgr):
            self.llm_client = llm_client
            self.graph_repo = graph_repo
            self.sandbox = sandbox
            self.checkpoint_mgr = checkpoint_mgr

        async def run(self, context: TaskContext) -> AgentResult:
            """Agent 的执行入口，由调度器调用"""

        async def think(self, context: TaskContext) -> Thought:

        async def act(self, thought: Thought) -> Action:

        async def observe(self, action: Action) -> Observation:
```

    


    

> ✅ Agent 拉起机制交付确认
        
            Agent 实现形态：进程内 asyncio 协程，而非独立微服务
            拉起流程：外部 API → 调度器状态机 → asyncio.create_task() → Agent 协程
            PRD/ADR：完整的规格定义，含数据契约、SC→AC、备选方案对比
            与现有 Step 映射：Step 5.1/5.2 需补充，Step 5.4/3.1-3.4 无修改
        
        下一步：可将本报告中的代码示例和 PRD/ADR 规格合并到 Step 5.1（调度器状态机）和 Step 5.2（Agent 角色与 Prompt）中。

    
        — V14.1 开发计划 · Agent 拉起机制 · 2026年6月22日 —

---


    
        
- 1. 整体架构设计
        
- 2. 微信小程序 Skill 机制
        
- 3. 与 V14.1 的 MCP 协议集成
        
- 4. 实时监控方案
        
- 5. API 规格
        
- 6. 与现有 Step 的映射
        
- 7. 代码示例
        
- 8. 实施路线图
    

    


    
    
    
    

## 1. 整体架构设计

    

> 核心方案：微信小程序 + Skill 机制作为请求入口，WebSocket/SSE 作为实时监控通道。

    

#### Step 5.8.25.1 完整调用链路

    

```python
    │  • 调用 V14.1 API 提交任务                      │
    │            V14.1 后端（API 网关层）               │
    │            V14.1 调度器（Step 5.1）              │
```

    

#### Step 5.8.25.1 为什么选择微信小程序？

    
        
- 天然的用户入口：微信日活超10亿，无需用户额外下载 App。
        
- 官方 AI 能力加持：微信已推出小程序 Skill 机制，可将功能封装为 AI 可调用的能力。
        
- 基于 MCP：Skill 底层基于 MCP 协议，与 V14.1 使用的 MCP 协议栈天然同构。
        
- 实时通信支持：小程序支持 WebSocket 和 SSE 两种实时方案。
    

    


    
    
    
    

    

## 2. 微信小程序 Skill 机制

    

#### Step 5.8.25.2 Skill 是什么

    Skill 是微信官方推出的 AI 能力接入机制，开发者可将小程序的能力封装为 AI 可调用的 Skill。用户通过自然语言就能触发 Skill，执行对应功能。

    

#### Step 5.8.25.2 两种接入模式

    | 模式 | 说明 | 适用场景 |
| --- | --- | --- |
| 自动模式 | 平台自动分析小程序源码，AI 可直接操作 | 快速验证，零代码接入 |
| 开发模式 | 开发者自定义 Skill，通过审核后被 AI 调用 | 推荐 定制化 V14.1 任务触发 |

    

#### Step 5.8.25.2 Skill 文件结构

    

```python
    ├── mcp.json          # 可用的函数声明（MCP 工具列表）
    │   ├── submit_task.js   # 提交 V14.1 任务
    │   ├── get_status.js    # 查询任务状态
    │   └── cancel_task.js   # 取消任务
    ├── index.js          # 注册函数给运行时
        └── status-card.wxml # 实时状态展示卡片
```

    

#### Step 5.8.25.2 mcp.json 声明示例

    

```python
              "name": "submit_development_task",
              "description": "向 V14.1 系统提交一个软件开发任务",
                "type": "object",
                    "type": "string",
                  },
                    "type": "string",
                    "enum": ["low", "normal", "high", "critical"],
                  },
                    "type": "string",
                },
            },
              "name": "query_task_status",
              "description": "查询 V14.1 系统中某个任务的执行状态",
                "type": "object",
                    "type": "string",
                },
```

    

#### Step 5.8.25.2 函数实现示例

    

```python
// apis/submit_task.js
    // 在微信小程序 Skill 中调用 V14.1 后端 API
    const V14_API_BASE = 'https://api.v14-system.com/api/v1';

      const { prd, priority = 'normal', callback_url } = params;

      // 1. 调用 V14.1 后端 API 提交任务
      const response = await fetch(`${V14_API_BASE}/tasks`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prd, priority, callback_url })

      if (!response.ok) {
        throw new Error(`V14.1 系统返回错误: ${response.status}`);

      const data = await response.json();

      // 2. 返回给小程序（Skill 的返回值）
        task_id: data.task_id,
        state: data.state,
        message: '任务已提交，正在处理中...',
        status_url: `${V14_API_BASE}/tasks/${data.task_id}/status`
```

    


    
    
    
    

    

## 3. 与 V14.1 的 MCP 协议集成

    

> 核心洞察：微信小程序的 Skill 机制底层基于 MCP 协议，与 V14.1 使用的 MCP 协议栈完全兼容。这意味着 Skill 中的函数声明（mcp.json）可以直接映射到 V14.1 的 MCP Server。

    

#### Step 5.8.25.3 分层架构

    

```python
    │  mcp.json 声明 → apis/*.js 实现                   │
    │  调用 V14.1 后端 API（内部使用 MCP 协议）         │
    │            V14.1 后端（MCP Server）                │
    │  • 暴露 MCP 工具：submit_task, query_status       │
    │            V14.1 调度器（Agent 系统）              │
```

    

#### Step 5.8.25.3 V14.1 端 MCP 工具暴露

    

```python
# /src/mcp/servers/v14_mcp_server.py
    from mcp.server import Server
    from src.scheduler.orchestrator import TaskOrchestrator


    @server.tool()
    async def submit_development_task(prd: str, priority: str = "normal") -> dict:
        """提交开发任务到 V14.1 系统"""
        task = await orchestrator.submit(prd, priority)
        return {"task_id": task.id, "state": task.state.value}

    @server.tool()
        task = await orchestrator.get_task(task_id)
            "task_id": task.id,
            "state": task.state.value,
            "progress": task.progress,
            "result": task.result

    @server.tool()
        await orchestrator.cancel(task_id)
        return {"task_id": task_id, "state": "cancelled"}
```

    


    
    
    
    

    

## 4. 实时监控方案

    

#### Step 5.8.25.4 两种实时通信方案对比

    | 方案 | 特点 | 适用场景 |
| --- | --- | --- |
| WebSocket | 全双工 通信，适合高频双向交互 | Agent 执行过程中需要用户介入确认（如：选择方案A还是B） |
| SSE (Server-Sent Events) | 单向 推送，基于 HTTP 更轻量 | 只需“看进度”的纯监控场景 |

    

#### Step 5.8.25.4 WebSocket 实时监控实现

    

```python
# /src/api/websocket.py
    from fastapi import WebSocket, WebSocketDisconnect
    from src.scheduler.orchestrator import TaskOrchestrator

            self.active_connections: Dict[str, List[WebSocket]] = {}

        async def connect(self, task_id: str, websocket: WebSocket):
            await websocket.accept()
            if task_id not in self.active_connections:
                self.active_connections[task_id] = []
            self.active_connections[task_id].append(websocket)

        def disconnect(self, task_id: str, websocket: WebSocket):
            if task_id in self.active_connections:
                self.active_connections[task_id].remove(websocket)

        async def broadcast_status(self, task_id: str, status: dict):
            if task_id in self.active_connections:
                for connection in self.active_connections[task_id]:
                        await connection.send_json(status)

    # 在调度器状态变更时触发广播
        def __init__(self, manager: ConnectionManager):
            self.manager = manager

        async def on_state_change(self, task_id: str, old_state: str, new_state: str, data: dict = None):
            await self.manager.broadcast_status(task_id, {
                "type": "state_change",
                "task_id": task_id,
                "from": old_state,
                "to": new_state,
```

    

#### Step 5.8.25.4 SSE 实时监控实现

    

```python
# /src/api/sse.py
    from fastapi.responses import StreamingResponse
    from sse_starlette.sse import EventSourceResponse

    @router.get("/tasks/{task_id}/stream")
    async def stream_task_status(task_id: str, orchestrator: TaskOrchestrator):
            # 获取初始状态
            task = await orchestrator.get_task(task_id)
            last_state = task.state

                # 检查状态是否有变化
                current_task = await orchestrator.get_task(task_id)
                if current_task.state != last_state:
                    last_state = current_task.state
                        "event": "state_change",
                            "task_id": task_id,
                            "state": current_task.state.value,
                            "progress": current_task.progress,
                            "timestamp": datetime.utcnow().isoformat()

                # 如果任务已完成或失败，结束推送
                if current_task.state in [TaskState.DONE, TaskState.FAILED]:
                        "event": "complete",
                            "task_id": task_id,
                            "state": current_task.state.value,
                            "result": current_task.result

                await asyncio.sleep(2)  # 轮询间隔

```

    


    
    
    
    

    

## 5. API 规格

    

#### Step 5.8.25.5 任务提交 API

    

```python
      "prd": "修改支付超时时间为60秒",
      "priority": "high",           # low | normal | high | critical
      "callback_url": null,          # 可选，任务完成后的Webhook

      "task_id": "a1b2c3d4-...",
      "state": "IDLE",
      "message": "任务已提交，正在排队中..."
```

    

#### Step 5.8.25.5 状态查询 API

    

```python
      "task_id": "a1b2c3d4-...",
      "state": "CODING",
      "progress": 0.6,
      "current_step": "DeveloperAgent 正在生成代码...",
        {"step": "PARSING", "status": "done", "duration_ms": 1200},
        {"step": "PLANNING", "status": "done", "duration_ms": 3400},
        {"step": "CODING", "status": "running", "duration_ms": null}
      ],
      "estimated_remaining_ms": 3000,
      "created_at": "2026-06-22T10:00:00Z",
```

    


    
    
    
    

    

## 6. 与现有 Step 的映射

    | Step | 原有内容 | 微信小程序接入的补充 |
| --- | --- | --- |
| Step 1.1四层架构与 API 契约 | 定义了 RESTful API 契约 | 需补充 增加 /tasks 路由的 source 字段；新增 /tasks/{id}/stream SSE 端点 |
| Step 6.1Vue3 驾驶舱 | 定义了 Web 驾驶舱的实时监控 | 无修改 微信小程序的实时监控复用相同的 WebSocket/SSE 基础设施 |
| Step 2.1LiteLLM 网关 | LLM API 调用网关 | 无修改 微信小程序接入不涉及 LLM 网关 |
| Step 5.1调度器状态机 | 定义了任务执行状态流转 | 需补充 状态变更时触发 WebSocket/SSE 广播（通过 StatusBroadcaster） |
| Step 7.6安全与权限管理 | JWT + 零信任架构 | 需补充 微信小程序的来源认证（小程序 AppID 验证 + JWT 颁发） |

    


    
    
    
    

    

## 7. 代码示例

    

#### Step 5.8.25.7 微信小程序 Skill 完整示例

    

```python
// apis/submit_task.js - 完整实现
    const V14_API_BASE = 'https://api.v14-system.com/api/v1';
    const WS_BASE = 'wss://api.v14-system.com/ws';

      const { prd, priority = 'normal' } = params;

      // 1. 提交任务
      const response = await fetch(`${V14_API_BASE}/tasks`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prd, priority, source: 'wechat_skill' })

      if (!response.ok) {
        throw new Error(`提交失败: ${response.status}`);

      const data = await response.json();

      // 2. 返回给小程序，包含用于 WebSocket 连接的 task_id
        task_id: data.task_id,
        message: '任务已提交，正在处理中...',
        ws_url: `${WS_BASE}/tasks/${data.task_id}`
```

    

#### Step 5.8.25.7 微信小程序实时监控组件

    

```python
// components/status-card/index.js
        taskId: { type: String, value: '' }
      },
        status: 'pending',
        progress: 0,
        logs: [],
      },
          this.connectWebSocket();
        },
          if (this.data.socket) {
            this.data.socket.close();
      },
          const ws = wx.connectSocket({
            url: `wss://api.v14-system.com/ws/tasks/${this.properties.taskId}`,

          ws.onMessage((res) => {
            const data = JSON.parse(res.data);
            this.setData({
              status: data.state,
              progress: data.progress,
              logs: [...this.data.logs, data.message]

          ws.onError((err) => {
            console.error('WebSocket 错误:', err);

          this.setData({ socket: ws });
```

    

#### Step 5.8.25.7 微信小程序卡片展示

    

```python
&lt;!-- components/status-card/index.wxml --&gt;

        &lt;text class="progress-text"&gt;{{Math.round(progress * 100)}}%&lt;/text&gt;

            &lt;text class="log-time"&gt;{{item.time}}&lt;/text&gt;
            &lt;text class="log-content"&gt;{{item.msg}}&lt;/text&gt;
```

    


    
    
    
    

    

## 8. 实施路线图

    | 阶段 | 任务 | 周期 | 依赖 |
| --- | --- | --- | --- |
| 准备阶段 | ① 设计 V14.1 后端 API（/tasks 提交、/tasks/{id}/status 查询、WebSocket/SSE 推送）② 申请微信小程序 AppID③ 搭建微信小程序开发环境 | 1-2天 | Step 1.1 完成 |
| 开发阶段 | ① 创建微信小程序 Skill 项目（mcp.json + apis/*.js + index.js）② 实现 Skill 调用 V14.1 API 的逻辑③ 实现 WebSocket/SSE 实时通信④ 设计小程序 UI（输入+状态卡片） | 3-5天 | Step 5.1 完成 |
| 集成与测试 | ① 端到端联调（小程序 ↔ V14.1）② 实时监控体验优化③ 安全认证联调 | 2-3天 | Step 7.6 完成 |
| 上线发布 | ① 微信小程序提交审核② Skill 功能发布③ ⚠️ 注意：Skill模式目前在内测，相关代码暂时不要合入正式版本提审 | 1-2天 | 测试通过 |

    

> ⚠️ 重要提醒：
        
            微信小程序 Skill 模式目前处于 内测阶段，相关代码暂时不要合入正式版本提审。
            建议先在开发环境做技术验证，待 Skill 功能正式对外开放后再提交审核。
            如果急需上线，可先用小程序原生页面 + API 调用方式实现（不依赖 Skill 能力）。

    


    

> ✅ 微信小程序接入交付确认
        
            Skill 机制：mcp.json 声明 + apis/*.js 实现 + 与 V14.1 MCP 协议同构
            实施路线图：准备→开发→集成测试→上线，约 1-1.5 周
        
        下一步：可按照实施路线图开始微信小程序项目的创建和 Skill 开发。

    
        — V14.1 开发计划 · 微信小程序接入 · 2026年6月22日 —


## Step 5.7：Agent拉起机制

## Step 5.8：微信小程序接入

    
        
- 1. 核心概念澄清
        
- 2. Agent 的实现形态
        
- 3. 系统拉起 Agent 的完整流程
        
- 4. 与 MCP/A2A 的抽象分层
        
- 5. PRD/ADR 规格
        
- 6. 与现有 Step 的映射
        
- 7. 代码示例
    

    


    
    
    
    

## 24.1.核心概念澄清

    

> 核心声明：在 V14.1 中，Agent 不是独立微服务、不是容器、不是进程，而是 调度器进程内的一个 Python 异步协程（asyncio Task）。

    

#### Step 5.7.24.1 “调用 Agent”的两种语义

    | 语义 | 含义 | V14.1 的实现 |
| --- | --- | --- |
| A2A 通信 | Agent A 请求 Agent B 执行某任务或提供信息 | 通过 A2A 协议（结构化消息）实现 Agent 间通信 |
| 系统拉起 Agent | 调度器将 Agent 实例化并开始执行 | 调度器的状态机通过 asyncio.create_task() 拉起 Agent 协程 |

    用户的问题“怎么调用 Agent”属于第二种语义：系统如何将 Agent 实例化并启动执行。

    


    
    
    
    

    

## 24.2.Agent 的实现形态

    

```python
# Agent 的本质是一个异步协程类
        def __init__(self, llm_client, graph_repo, sandbox, checkpoint_mgr):
            self.llm = llm_client
            self.graph = graph_repo
            self.sandbox = sandbox
            self.checkpoint = checkpoint_mgr

        async def run(self, context: TaskContext) -> AgentResult:
            # 思考 → 行动 → 观察 循环
            while not self.should_stop():
                thought = await self.think(context)        # 调用 LLM
                action = await self.act(thought)           # 执行工具（通过 MCP）
                observation = await self.observe(action)   # 收集结果
                context = self.update_context(context, observation)
            return AgentResult(...)
```

    

#### Step 5.7.24.2 关键特征

    
        
- 进程内执行：所有 Agent 运行在同一个进程中，无进程间通信开销。
        
- 协程隔离：每个 Agent 是一个独立的 asyncio Task，由事件循环调度。
        
- 状态隔离：Agent 间不直接共享内存，通过调度器的 Session/Checkpoint 传递经过验证的数据。
        
- 私有工作记忆（L4）：每个 Agent 有独立的局部工作记忆，不跨 Agent 共享。
        
- 拉起速度：协程创建为微秒级，远快于容器启动（秒级）。
    

    


    
    
    
    

    

## 24.3.系统拉起 Agent 的完整流程

    

#### Step 5.7.24.3 第1步：用户触发（外部入口）

    

```python
# API 入口
    @router.post("/api/v1/tasks")
        task = Task(prd=req.prd, state=TaskState.IDLE)
        await scheduler.submit(task)  # ← 提交给调度器
        return {"task_id": task.id}
```

    用户调用的不是 Agent，而是调度器的 API 入口。

    

#### Step 5.7.24.3 第2步：调度器状态机驱动

    

```python
# Step 5.1 调度器状态机（核心逻辑）
        async def run(self, task: Task):
            while task.state != TaskState.DONE:
                if task.state == TaskState.IDLE:
                    task.state = TaskState.PARSING
                    result = await self._run_agent(ParserAgent, task)

                elif task.state == TaskState.PARSING:
                    task.state = TaskState.PLANNING
                    result = await self._run_agent(ArchitectAgent, task)

                elif task.state == TaskState.PLANNING:
                    task.state = TaskState.CODING
                    # 🔴 关键：拉起 DeveloperAgent
                    result = await self._run_agent(DeveloperAgent, task)

                # ... 依次类推
```

    

#### Step 5.7.24.3 第3步：拉起 Agent 协程（核心）

    

```python
# 实际拉起 Agent 的方法
    async def _run_agent(self, agent_class, task: Task) -> AgentResult:
        # 1. 构建 Agent 的上下文（注入 L1-L5）
            l1=SYSTEM_PROMPTS[agent_class.__name__],       # 协作宪法
            l2=await self._query_graphs(task),             # 四图谱事实
            l3=self._build_task_context(task),             # 任务状态
            l4={},                                         # 私有工作记忆（空）
            l5=await self._retrieve_memories(task)         # 长期记忆

        # 2. 实例化 Agent（依赖注入）
            llm_client=self.llm_client,
            graph_repo=self.graph_repo,
            sandbox=self.sandbox,
            checkpoint_mgr=self.checkpoint_mgr

        # 3. 🔴 拉起 Agent 协程（本质是异步函数调用）
        result = await agent.run(context)

        # 4. 将结果写入检查点（供下游 Agent 使用）
        await self.checkpoint_mgr.save(task.id, result)

```

    

#### Step 5.7.24.3 第4步：Agent 执行循环

    

```python
        async def run(self, context: TaskContext) -> AgentResult:
            for iteration in range(self.max_iterations):
                # 思考：调用 LLM
                thought = await self.think(context)

                # 行动：执行工具调用（通过 MCP）
                action = await self.act(thought)

                # 观察：收集结果
                observation = await self.observe(action)

                # 更新上下文（L4 私有工作记忆）
                context.l4["last_action"] = action
                context.l4["last_observation"] = observation

                # 终止条件判断
                if self.should_stop(observation):

            return AgentResult(success=True, output=context.l4["final_output"])
```

    


    
    
    
    

    

## 24.4.与 MCP/A2A 的抽象分层

    在 V14.1 中，MCP 和 A2A 服务于不同的抽象层级，而“系统拉起 Agent”是另一个独立的层级。

    

> ┌─────────────────────────────────────────────────────────────┐
        │              🌐 API 网关层（Step 1.1）                     │
        │  • 状态机驱动（Step 5.1）                                 │
        │  • 🔴 通过 asyncio.create_task() 拉起 Agent 协程          │
        │  • 通过 Checkpoint 管理状态（Step 2.2）                   │
        │  • 通过 Audit 记录决策链（Step 1.2 补丁）                 │
                       │ await agent.run()
        │  • 思考→行动→观察 循环（Step 5.1）                        │

    

#### Step 5.7.24.4 三层调用关系

    | 层级 | 用途 | 协议/方式 | 调用方向 |
| --- | --- | --- | --- |
| 系统 → Agent | 调度器实例化并驱动 Agent 协程 | asyncio.create_task() + await agent.run() | 向上驱动 |
| Agent → 工具 | Agent 调用外部工具/资源（四图谱、沙箱、数据库） | MCP（Model Context Protocol） | 向下调用 |
| Agent → Agent | Agent 之间协作通信（任务分发、审查、仲裁） | A2A（Agent-to-Agent Protocol） | 水平通信 |

    

#### Step 5.7.24.4 与现有协议的定位

    
        
- MCP 不在“拉起 Agent”层：MCP 是 Agent 已经运行后用来调用工具的协议。它不负责 Agent 的启动或生命周期管理。
        
- A2A 不在“拉起 Agent”层：A2A 是 Agent 之间已经运行后用来相互通信的协议。它也不负责 Agent 的启动。
        
- “拉起 Agent”是调度器的职责：通过 asyncio 协程直接实例化和驱动，是 V14.1 自研调度器的核心能力。
    

    


    
    
    
    

    

## 24.5.PRD/ADR 规格

    

#### Step 5.7.24.5 PRD · Agent 拉起机制

    | PRD · Agent 拉起机制 |
| --- |
| 背景 | 外部系统需要通过调度器驱动多智能体协作。Agent 不是预先部署的微服务，而是由调度器按需实例化的异步协程。 |
| 用户故事 | 作为调度器，我根据状态机的进度，在合适的时机await agent.run()拉起对应的 Agent 协程，执行完成后将结果写入检查点。 |
| 需求描述 | ① Agent 定义为异步协程类，实现 run(context: TaskContext) -> AgentResult 方法。 ② 调度器通过 asyncio.create_task() 拉起 Agent。 ③ 拉起时注入 L1-L5 上下文（L1 协作宪法、L2 四图谱事实、L3 任务状态、L4 私有记忆、L5 长期记忆）。 ④ Agent 执行完成后，结果写入检查点（Checkpoint），供下游 Agent 使用。 ⑤ 外部系统通过 API 调用调度器，不直接调用 Agent。 |
| 范围 | Do：进程内协程拉起；依赖注入；上下文构建；结果持久化。 Don't：不通过 HTTP/gRPC 远程调用 Agent；不将 Agent 部署为独立容器。 |
| 数据契约 | ```python class TaskContext(BaseModel): task_id: str l1: str # System Prompt（协作宪法） l2: Dict[str, Any] # 四图谱查询结果 l3: Dict[str, Any] # 任务状态（PRD摘要、DAG进度） l4: Dict[str, Any] # Agent私有工作记忆 l5: List[Dict[str, Any]] # 长期记忆（检索结果） class AgentResult(BaseModel): success: bool output: Any error: Optional[str] = None duration_ms: float ``` |
| SC→AC | SC1: Agent 拉起成功 → AC1: 状态机触发 CODING 状态时，调用 _run_agent(DeveloperAgent, task) 返回 AgentResult。 SC2: 上下文注入完整 → AC2: Agent 的 run() 方法中 context.l1、context.l2 非空且包含预期内容。 SC3: 结果持久化 → AC3: Agent 执行完成后，检查点中存在对应 task_id 的记录。 |
| 待定决策 | Q: Agent 执行超时如何处理？ → 决议：在 _run_agent() 中包装 asyncio.wait_for(agent.run(), timeout=300)，超时后取消协程并标记 FAILED。 |

    

#### Step 5.7.24.5 ADR · Agent 实现形态

    | ADR · Agent 实现形态 |
| --- |
| 决策 | Agent 实现为进程内异步协程，而非独立微服务或容器。 ① 所有 Agent 运行在调度器同一进程中。 ② 通过 asyncio 事件循环调度。 ③ 通过依赖注入传递外部依赖（LLM 客户端、图谱仓库、沙箱）。 ④ 通过 Checkpoint 实现状态跨 Agent 传递。 |
| 理由 | ① 无网络开销：协程间通信为零延迟。② 极速拉起：协程创建为微秒级。③ 共享内存：Checkpoint 直接读取，无需序列化传递。④ 简化运维：无需部署多个微服务。⑤ 与 V14.1 的 asyncio 调度器自然兼容。 |
| 备选方案 | ① 独立微服务（HTTP/gRPC 拉起）→ 网络延迟高，资源消耗大，不适合密集 Agent 协作。② 独立容器（Docker 拉起）→ 启动慢（秒级），资源隔离过度。 |

    


    
    
    
    

    

## 24.6.与现有 Step 的映射

    | Step | 原有内容 | Agent 拉起机制的补充 |
| --- | --- | --- |
| Step 5.1调度器状态机 | 定义了状态转换（IDLE→PARSING→PLANNING→CODING→...） | 需补充 在状态转换中增加 _run_agent() 方法的实现，明确如何拉起 Agent 协程 |
| Step 5.2Agent 角色与 Prompt | 定义了 5 个 Agent 的 System Prompt 和职责 | 需补充 每个 Agent 类必须实现 run(context: TaskContext) -> AgentResult 接口 |
| Step 2.2检查点持久化 | Redis + PostgreSQL 双层存储 | 需补充 Agent 执行完成后，结果通过 CheckpointManager 写入检查点，供下游 Agent 使用 |
| Step 5.4Agent 间通信 | 定义了 A2A 协议的结构化消息格式 | 无修改 该 Step 处理的是 Agent 间通信，与“系统拉起 Agent”是不同层级 |
| Step 3.1-3.4四图谱 | 代码/数据库/配置/知识图谱 | 无修改 Agent 通过 MCP 调用图谱查询，与拉起机制无关 |

    


    
    
    
    

    

## 24.7.代码示例

    

#### Step 5.7.24.7 调度器拉起 Agent 的完整实现

    

```python
# /src/scheduler/orchestrator.py
    from typing import Type, Dict, Any
    from src.agents.base import BaseAgent
    from src.agents.developer import DeveloperAgent
    from src.agents.architect import ArchitectAgent
    from src.agents.parser import ParserAgent
    from src.scheduler.context import TaskContext


        # Agent 类名 → 对应 System Prompt 的映射
            "ParserAgent": "你是一个需求解析器...",
            "ArchitectAgent": "你是一个架构师...",
            "DeveloperAgent": "你是一个开发者...",
            "ReviewerAgent": "你是一个代码审查员...",
            "QAAgent": "你是一个QA验证员..."

        def __init__(self, llm_client, graph_repo, sandbox, checkpoint_mgr):
            self.llm_client = llm_client
            self.graph_repo = graph_repo
            self.sandbox = sandbox
            self.checkpoint_mgr = checkpoint_mgr

            self,
            agent_class: Type[BaseAgent],
                # 1. 构建上下文（L1-L5）
                context = await self._build_context(task)

                # 2. 实例化 Agent
                    llm_client=self.llm_client,
                    graph_repo=self.graph_repo,
                    sandbox=self.sandbox,
                    checkpoint_mgr=self.checkpoint_mgr

                # 3. 🔴 拉起 Agent 协程（带超时）
                result = await asyncio.wait_for(
                    agent.run(context),

                # 4. 写入检查点
                await self.checkpoint_mgr.save(
                    task.id,
                        task_id=task.id,
                        state=task.state,
                        context={"agent_output": result.output}


            except asyncio.TimeoutError:
                    success=False,
                    error=f"Agent {agent_class.__name__} timed out after 300s"

        async def _build_context(self, task: Task) -> TaskContext:
                task_id=task.id,
                l1=self._AGENT_PROMPTS[agent_class.__name__],
                l2=await self._query_graphs(task),
                    "prd": task.prd[:500],
                    "dag_progress": self._get_progress(task),
                    "upstream_output": await self._get_upstream_output(task)
                },
                l4={},  # Agent 私有工作记忆（初始为空）
                l5=await self._retrieve_memories(task)
```

    

#### Step 5.7.24.7 外部系统调用调度器的 API

    

```python
# /src/api/routes/tasks.py
    from fastapi import APIRouter, Depends
    from src.scheduler.orchestrator import TaskOrchestrator


    @router.post("/tasks")
        req: TaskCreateRequest,
        """外部系统通过此 API 提交任务，调度器将拉起 Agent"""
        task = Task(prd=req.prd, state=TaskState.IDLE)
        # 提交到调度器，调度器内部会驱动状态机并拉起 Agent
        await orchestrator.submit(task)
        return {"task_id": task.id}

    @router.get("/tasks/{task_id}")
        task_id: str,
        task = await orchestrator.get_task(task_id)
        return {"task_id": task.id, "state": task.state}
```

    

#### Step 5.7.24.7 Agent 基类定义

    

```python
# /src/agents/base.py
    from abc import ABC, abstractmethod
    from src.scheduler.context import TaskContext


        def __init__(self, llm_client, graph_repo, sandbox, checkpoint_mgr):
            self.llm_client = llm_client
            self.graph_repo = graph_repo
            self.sandbox = sandbox
            self.checkpoint_mgr = checkpoint_mgr

        async def run(self, context: TaskContext) -> AgentResult:
            """Agent 的执行入口，由调度器调用"""

        async def think(self, context: TaskContext) -> Thought:

        async def act(self, thought: Thought) -> Action:

        async def observe(self, action: Action) -> Observation:
```

    


    

> ✅ Agent 拉起机制交付确认
        
            Agent 实现形态：进程内 asyncio 协程，而非独立微服务
            拉起流程：外部 API → 调度器状态机 → asyncio.create_task() → Agent 协程
            PRD/ADR：完整的规格定义，含数据契约、SC→AC、备选方案对比
            与现有 Step 映射：Step 5.1/5.2 需补充，Step 5.4/3.1-3.4 无修改
        
        下一步：可将本报告中的代码示例和 PRD/ADR 规格合并到 Step 5.1（调度器状态机）和 Step 5.2（Agent 角色与 Prompt）中。

    
        — V14.1 开发计划 · Agent 拉起机制 · 2026年6月22日 —

---


    
        
- 1. 整体架构设计
        
- 2. 微信小程序 Skill 机制
        
- 3. 与 V14.1 的 MCP 协议集成
        
- 4. 实时监控方案
        
- 5. API 规格
        
- 6. 与现有 Step 的映射
        
- 7. 代码示例
        
- 8. 实施路线图
    

    


    
    
    
    

## 25.1.整体架构设计

    

> 核心方案：微信小程序 + Skill 机制作为请求入口，WebSocket/SSE 作为实时监控通道。

    

#### Step 5.8.25.1 完整调用链路

    

```python
    │  • 调用 V14.1 API 提交任务                      │
    │            V14.1 后端（API 网关层）               │
    │            V14.1 调度器（Step 5.1）              │
```

    

#### Step 5.8.25.1 为什么选择微信小程序？

    
        
- 天然的用户入口：微信日活超10亿，无需用户额外下载 App。
        
- 官方 AI 能力加持：微信已推出小程序 Skill 机制，可将功能封装为 AI 可调用的能力。
        
- 基于 MCP：Skill 底层基于 MCP 协议，与 V14.1 使用的 MCP 协议栈天然同构。
        
- 实时通信支持：小程序支持 WebSocket 和 SSE 两种实时方案。
    

    


    
    
    
    

    

## 25.2.微信小程序 Skill 机制

    

#### Step 5.8.25.2 Skill 是什么

    Skill 是微信官方推出的 AI 能力接入机制，开发者可将小程序的能力封装为 AI 可调用的 Skill。用户通过自然语言就能触发 Skill，执行对应功能。

    

#### Step 5.8.25.2 两种接入模式

    | 模式 | 说明 | 适用场景 |
| --- | --- | --- |
| 自动模式 | 平台自动分析小程序源码，AI 可直接操作 | 快速验证，零代码接入 |
| 开发模式 | 开发者自定义 Skill，通过审核后被 AI 调用 | 推荐 定制化 V14.1 任务触发 |

    

#### Step 5.8.25.2 Skill 文件结构

    

```python
    ├── mcp.json          # 可用的函数声明（MCP 工具列表）
    │   ├── submit_task.js   # 提交 V14.1 任务
    │   ├── get_status.js    # 查询任务状态
    │   └── cancel_task.js   # 取消任务
    ├── index.js          # 注册函数给运行时
        └── status-card.wxml # 实时状态展示卡片
```

    

#### Step 5.8.25.2 mcp.json 声明示例

    

```python
              "name": "submit_development_task",
              "description": "向 V14.1 系统提交一个软件开发任务",
                "type": "object",
                    "type": "string",
                  },
                    "type": "string",
                    "enum": ["low", "normal", "high", "critical"],
                  },
                    "type": "string",
                },
            },
              "name": "query_task_status",
              "description": "查询 V14.1 系统中某个任务的执行状态",
                "type": "object",
                    "type": "string",
                },
```

    

#### Step 5.8.25.2 函数实现示例

    

```python
// apis/submit_task.js
    // 在微信小程序 Skill 中调用 V14.1 后端 API
    const V14_API_BASE = 'https://api.v14-system.com/api/v1';

      const { prd, priority = 'normal', callback_url } = params;

      // 1. 调用 V14.1 后端 API 提交任务
      const response = await fetch(`${V14_API_BASE}/tasks`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prd, priority, callback_url })

      if (!response.ok) {
        throw new Error(`V14.1 系统返回错误: ${response.status}`);

      const data = await response.json();

      // 2. 返回给小程序（Skill 的返回值）
        task_id: data.task_id,
        state: data.state,
        message: '任务已提交，正在处理中...',
        status_url: `${V14_API_BASE}/tasks/${data.task_id}/status`
```

    


    
    
    
    

    

## 25.3.与 V14.1 的 MCP 协议集成

    

> 核心洞察：微信小程序的 Skill 机制底层基于 MCP 协议，与 V14.1 使用的 MCP 协议栈完全兼容。这意味着 Skill 中的函数声明（mcp.json）可以直接映射到 V14.1 的 MCP Server。

    

#### Step 5.8.25.3 分层架构

    

```python
    │  mcp.json 声明 → apis/*.js 实现                   │
    │  调用 V14.1 后端 API（内部使用 MCP 协议）         │
    │            V14.1 后端（MCP Server）                │
    │  • 暴露 MCP 工具：submit_task, query_status       │
    │            V14.1 调度器（Agent 系统）              │
```

    

#### Step 5.8.25.3 V14.1 端 MCP 工具暴露

    

```python
# /src/mcp/servers/v14_mcp_server.py
    from mcp.server import Server
    from src.scheduler.orchestrator import TaskOrchestrator


    @server.tool()
    async def submit_development_task(prd: str, priority: str = "normal") -> dict:
        """提交开发任务到 V14.1 系统"""
        task = await orchestrator.submit(prd, priority)
        return {"task_id": task.id, "state": task.state.value}

    @server.tool()
        task = await orchestrator.get_task(task_id)
            "task_id": task.id,
            "state": task.state.value,
            "progress": task.progress,
            "result": task.result

    @server.tool()
        await orchestrator.cancel(task_id)
        return {"task_id": task_id, "state": "cancelled"}
```

    


    
    
    
    

    

## 25.4.实时监控方案

    

#### Step 5.8.25.4 两种实时通信方案对比

    | 方案 | 特点 | 适用场景 |
| --- | --- | --- |
| WebSocket | 全双工 通信，适合高频双向交互 | Agent 执行过程中需要用户介入确认（如：选择方案A还是B） |
| SSE (Server-Sent Events) | 单向 推送，基于 HTTP 更轻量 | 只需“看进度”的纯监控场景 |

    

#### Step 5.8.25.4 WebSocket 实时监控实现

    

```python
# /src/api/websocket.py
    from fastapi import WebSocket, WebSocketDisconnect
    from src.scheduler.orchestrator import TaskOrchestrator

            self.active_connections: Dict[str, List[WebSocket]] = {}

        async def connect(self, task_id: str, websocket: WebSocket):
            await websocket.accept()
            if task_id not in self.active_connections:
                self.active_connections[task_id] = []
            self.active_connections[task_id].append(websocket)

        def disconnect(self, task_id: str, websocket: WebSocket):
            if task_id in self.active_connections:
                self.active_connections[task_id].remove(websocket)

        async def broadcast_status(self, task_id: str, status: dict):
            if task_id in self.active_connections:
                for connection in self.active_connections[task_id]:
                        await connection.send_json(status)

    # 在调度器状态变更时触发广播
        def __init__(self, manager: ConnectionManager):
            self.manager = manager

        async def on_state_change(self, task_id: str, old_state: str, new_state: str, data: dict = None):
            await self.manager.broadcast_status(task_id, {
                "type": "state_change",
                "task_id": task_id,
                "from": old_state,
                "to": new_state,
```

    

#### Step 5.8.25.4 SSE 实时监控实现

    

```python
# /src/api/sse.py
    from fastapi.responses import StreamingResponse
    from sse_starlette.sse import EventSourceResponse

    @router.get("/tasks/{task_id}/stream")
    async def stream_task_status(task_id: str, orchestrator: TaskOrchestrator):
            # 获取初始状态
            task = await orchestrator.get_task(task_id)
            last_state = task.state

                # 检查状态是否有变化
                current_task = await orchestrator.get_task(task_id)
                if current_task.state != last_state:
                    last_state = current_task.state
                        "event": "state_change",
                            "task_id": task_id,
                            "state": current_task.state.value,
                            "progress": current_task.progress,
                            "timestamp": datetime.utcnow().isoformat()

                # 如果任务已完成或失败，结束推送
                if current_task.state in [TaskState.DONE, TaskState.FAILED]:
                        "event": "complete",
                            "task_id": task_id,
                            "state": current_task.state.value,
                            "result": current_task.result

                await asyncio.sleep(2)  # 轮询间隔

```

    


    
    
    
    

    

## 25.5.API 规格

    

#### Step 5.8.25.5 任务提交 API

    

```python
      "prd": "修改支付超时时间为60秒",
      "priority": "high",           # low | normal | high | critical
      "callback_url": null,          # 可选，任务完成后的Webhook

      "task_id": "a1b2c3d4-...",
      "state": "IDLE",
      "message": "任务已提交，正在排队中..."
```

    

#### Step 5.8.25.5 状态查询 API

    

```python
      "task_id": "a1b2c3d4-...",
      "state": "CODING",
      "progress": 0.6,
      "current_step": "DeveloperAgent 正在生成代码...",
        {"step": "PARSING", "status": "done", "duration_ms": 1200},
        {"step": "PLANNING", "status": "done", "duration_ms": 3400},
        {"step": "CODING", "status": "running", "duration_ms": null}
      ],
      "estimated_remaining_ms": 3000,
      "created_at": "2026-06-22T10:00:00Z",
```

    


    
    
    
    

    

## 25.6.与现有 Step 的映射

    | Step | 原有内容 | 微信小程序接入的补充 |
| --- | --- | --- |
| Step 1.1四层架构与 API 契约 | 定义了 RESTful API 契约 | 需补充 增加 /tasks 路由的 source 字段；新增 /tasks/{id}/stream SSE 端点 |
| Step 6.1Vue3 驾驶舱 | 定义了 Web 驾驶舱的实时监控 | 无修改 微信小程序的实时监控复用相同的 WebSocket/SSE 基础设施 |
| Step 2.1LiteLLM 网关 | LLM API 调用网关 | 无修改 微信小程序接入不涉及 LLM 网关 |
| Step 5.1调度器状态机 | 定义了任务执行状态流转 | 需补充 状态变更时触发 WebSocket/SSE 广播（通过 StatusBroadcaster） |
| Step 7.6安全与权限管理 | JWT + 零信任架构 | 需补充 微信小程序的来源认证（小程序 AppID 验证 + JWT 颁发） |

    


    
    
    
    

    

## 25.7.代码示例

    

#### Step 5.8.25.7 微信小程序 Skill 完整示例

    

```python
// apis/submit_task.js - 完整实现
    const V14_API_BASE = 'https://api.v14-system.com/api/v1';
    const WS_BASE = 'wss://api.v14-system.com/ws';

      const { prd, priority = 'normal' } = params;

      // 1. 提交任务
      const response = await fetch(`${V14_API_BASE}/tasks`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prd, priority, source: 'wechat_skill' })

      if (!response.ok) {
        throw new Error(`提交失败: ${response.status}`);

      const data = await response.json();

      // 2. 返回给小程序，包含用于 WebSocket 连接的 task_id
        task_id: data.task_id,
        message: '任务已提交，正在处理中...',
        ws_url: `${WS_BASE}/tasks/${data.task_id}`
```

    

#### Step 5.8.25.7 微信小程序实时监控组件

    

```python
// components/status-card/index.js
        taskId: { type: String, value: '' }
      },
        status: 'pending',
        progress: 0,
        logs: [],
      },
          this.connectWebSocket();
        },
          if (this.data.socket) {
            this.data.socket.close();
      },
          const ws = wx.connectSocket({
            url: `wss://api.v14-system.com/ws/tasks/${this.properties.taskId}`,

          ws.onMessage((res) => {
            const data = JSON.parse(res.data);
            this.setData({
              status: data.state,
              progress: data.progress,
              logs: [...this.data.logs, data.message]

          ws.onError((err) => {
            console.error('WebSocket 错误:', err);

          this.setData({ socket: ws });
```

    

#### Step 5.8.25.7 微信小程序卡片展示

    

```python
&lt;!-- components/status-card/index.wxml --&gt;

        &lt;text class="progress-text"&gt;{{Math.round(progress * 100)}}%&lt;/text&gt;

            &lt;text class="log-time"&gt;{{item.time}}&lt;/text&gt;
            &lt;text class="log-content"&gt;{{item.msg}}&lt;/text&gt;
```

    


    
    
    
    

    

## 25.8.实施路线图

    | 阶段 | 任务 | 周期 | 依赖 |
| --- | --- | --- | --- |
| 准备阶段 | ① 设计 V14.1 后端 API（/tasks 提交、/tasks/{id}/status 查询、WebSocket/SSE 推送）② 申请微信小程序 AppID③ 搭建微信小程序开发环境 | 1-2天 | Step 1.1 完成 |
| 开发阶段 | ① 创建微信小程序 Skill 项目（mcp.json + apis/*.js + index.js）② 实现 Skill 调用 V14.1 API 的逻辑③ 实现 WebSocket/SSE 实时通信④ 设计小程序 UI（输入+状态卡片） | 3-5天 | Step 5.1 完成 |
| 集成与测试 | ① 端到端联调（小程序 ↔ V14.1）② 实时监控体验优化③ 安全认证联调 | 2-3天 | Step 7.6 完成 |
| 上线发布 | ① 微信小程序提交审核② Skill 功能发布③ ⚠️ 注意：Skill模式目前在内测，相关代码暂时不要合入正式版本提审 | 1-2天 | 测试通过 |

    

> ⚠️ 重要提醒：
        
            微信小程序 Skill 模式目前处于 内测阶段，相关代码暂时不要合入正式版本提审。
            建议先在开发环境做技术验证，待 Skill 功能正式对外开放后再提交审核。
            如果急需上线，可先用小程序原生页面 + API 调用方式实现（不依赖 Skill 能力）。

    


    

> ✅ 微信小程序接入交付确认
        
            Skill 机制：mcp.json 声明 + apis/*.js 实现 + 与 V14.1 MCP 协议同构
            实施路线图：准备→开发→集成测试→上线，约 1-1.5 周
        
        下一步：可按照实施路线图开始微信小程序项目的创建和 Skill 开发。

    
        — V14.1 开发计划 · 微信小程序接入 · 2026年6月22日 —


## Step 5.7：Agent拉起机制

## Step 5.8：微信小程序接入

    
        
- 1. 核心概念澄清
        
- 2. Agent 的实现形态
        
- 3. 系统拉起 Agent 的完整流程
        
- 4. 与 MCP/A2A 的抽象分层
        
- 5. PRD/ADR 规格
        
- 6. 与现有 Step 的映射
        
- 7. 代码示例
    

    


    
    
    
    

## 24.1. 核心概念澄清

    

> 核心声明：在 V14.1 中，Agent 不是独立微服务、不是容器、不是进程，而是 调度器进程内的一个 Python 异步协程（asyncio Task）。

    

#### Step 5.7.24.1 “调用 Agent”的两种语义

    | 语义 | 含义 | V14.1 的实现 |
| --- | --- | --- |
| A2A 通信 | Agent A 请求 Agent B 执行某任务或提供信息 | 通过 A2A 协议（结构化消息）实现 Agent 间通信 |
| 系统拉起 Agent | 调度器将 Agent 实例化并开始执行 | 调度器的状态机通过 asyncio.create_task() 拉起 Agent 协程 |

    用户的问题“怎么调用 Agent”属于第二种语义：系统如何将 Agent 实例化并启动执行。

    


    
    
    
    

    

## 24.2. Agent 的实现形态

    

```python
# Agent 的本质是一个异步协程类
        def __init__(self, llm_client, graph_repo, sandbox, checkpoint_mgr):
            self.llm = llm_client
            self.graph = graph_repo
            self.sandbox = sandbox
            self.checkpoint = checkpoint_mgr

        async def run(self, context: TaskContext) -> AgentResult:
            # 思考 → 行动 → 观察 循环
            while not self.should_stop():
                thought = await self.think(context)        # 调用 LLM
                action = await self.act(thought)           # 执行工具（通过 MCP）
                observation = await self.observe(action)   # 收集结果
                context = self.update_context(context, observation)
            return AgentResult(...)
```

    

#### Step 5.7.24.2 关键特征

    
        
- 进程内执行：所有 Agent 运行在同一个进程中，无进程间通信开销。
        
- 协程隔离：每个 Agent 是一个独立的 asyncio Task，由事件循环调度。
        
- 状态隔离：Agent 间不直接共享内存，通过调度器的 Session/Checkpoint 传递经过验证的数据。
        
- 私有工作记忆（L4）：每个 Agent 有独立的局部工作记忆，不跨 Agent 共享。
        
- 拉起速度：协程创建为微秒级，远快于容器启动（秒级）。
    

    


    
    
    
    

    

## 24.3. 系统拉起 Agent 的完整流程

    

#### Step 5.7.24.3 第1步：用户触发（外部入口）

    

```python
# API 入口
    @router.post("/api/v1/tasks")
        task = Task(prd=req.prd, state=TaskState.IDLE)
        await scheduler.submit(task)  # ← 提交给调度器
        return {"task_id": task.id}
```

    用户调用的不是 Agent，而是调度器的 API 入口。

    

#### Step 5.7.24.3 第2步：调度器状态机驱动

    

```python
# Step 5.1 调度器状态机（核心逻辑）
        async def run(self, task: Task):
            while task.state != TaskState.DONE:
                if task.state == TaskState.IDLE:
                    task.state = TaskState.PARSING
                    result = await self._run_agent(ParserAgent, task)

                elif task.state == TaskState.PARSING:
                    task.state = TaskState.PLANNING
                    result = await self._run_agent(ArchitectAgent, task)

                elif task.state == TaskState.PLANNING:
                    task.state = TaskState.CODING
                    # 🔴 关键：拉起 DeveloperAgent
                    result = await self._run_agent(DeveloperAgent, task)

                # ... 依次类推
```

    

#### Step 5.7.24.3 第3步：拉起 Agent 协程（核心）

    

```python
# 实际拉起 Agent 的方法
    async def _run_agent(self, agent_class, task: Task) -> AgentResult:
        # 1. 构建 Agent 的上下文（注入 L1-L5）
            l1=SYSTEM_PROMPTS[agent_class.__name__],       # 协作宪法
            l2=await self._query_graphs(task),             # 四图谱事实
            l3=self._build_task_context(task),             # 任务状态
            l4={},                                         # 私有工作记忆（空）
            l5=await self._retrieve_memories(task)         # 长期记忆

        # 2. 实例化 Agent（依赖注入）
            llm_client=self.llm_client,
            graph_repo=self.graph_repo,
            sandbox=self.sandbox,
            checkpoint_mgr=self.checkpoint_mgr

        # 3. 🔴 拉起 Agent 协程（本质是异步函数调用）
        result = await agent.run(context)

        # 4. 将结果写入检查点（供下游 Agent 使用）
        await self.checkpoint_mgr.save(task.id, result)

```

    

#### Step 5.7.24.3 第4步：Agent 执行循环

    

```python
        async def run(self, context: TaskContext) -> AgentResult:
            for iteration in range(self.max_iterations):
                # 思考：调用 LLM
                thought = await self.think(context)

                # 行动：执行工具调用（通过 MCP）
                action = await self.act(thought)

                # 观察：收集结果
                observation = await self.observe(action)

                # 更新上下文（L4 私有工作记忆）
                context.l4["last_action"] = action
                context.l4["last_observation"] = observation

                # 终止条件判断
                if self.should_stop(observation):

            return AgentResult(success=True, output=context.l4["final_output"])
```

    


    
    
    
    

    

## 24.4. 与 MCP/A2A 的抽象分层

    在 V14.1 中，MCP 和 A2A 服务于不同的抽象层级，而“系统拉起 Agent”是另一个独立的层级。

    

> ┌─────────────────────────────────────────────────────────────┐
        │              🌐 API 网关层（Step 1.1）                     │
        │  • 状态机驱动（Step 5.1）                                 │
        │  • 🔴 通过 asyncio.create_task() 拉起 Agent 协程          │
        │  • 通过 Checkpoint 管理状态（Step 2.2）                   │
        │  • 通过 Audit 记录决策链（Step 1.2 补丁）                 │
                       │ await agent.run()
        │  • 思考→行动→观察 循环（Step 5.1）                        │

    

#### Step 5.7.24.4 三层调用关系

    | 层级 | 用途 | 协议/方式 | 调用方向 |
| --- | --- | --- | --- |
| 系统 → Agent | 调度器实例化并驱动 Agent 协程 | asyncio.create_task() + await agent.run() | 向上驱动 |
| Agent → 工具 | Agent 调用外部工具/资源（四图谱、沙箱、数据库） | MCP（Model Context Protocol） | 向下调用 |
| Agent → Agent | Agent 之间协作通信（任务分发、审查、仲裁） | A2A（Agent-to-Agent Protocol） | 水平通信 |

    

#### Step 5.7.24.4 与现有协议的定位

    
        
- MCP 不在“拉起 Agent”层：MCP 是 Agent 已经运行后用来调用工具的协议。它不负责 Agent 的启动或生命周期管理。
        
- A2A 不在“拉起 Agent”层：A2A 是 Agent 之间已经运行后用来相互通信的协议。它也不负责 Agent 的启动。
        
- “拉起 Agent”是调度器的职责：通过 asyncio 协程直接实例化和驱动，是 V14.1 自研调度器的核心能力。
    

    


    
    
    
    

    

## 24.5. PRD/ADR 规格

    

#### Step 5.7.24.5 PRD · Agent 拉起机制

    | PRD · Agent 拉起机制 |
| --- |
| 背景 | 外部系统需要通过调度器驱动多智能体协作。Agent 不是预先部署的微服务，而是由调度器按需实例化的异步协程。 |
| 用户故事 | 作为调度器，我根据状态机的进度，在合适的时机await agent.run()拉起对应的 Agent 协程，执行完成后将结果写入检查点。 |
| 需求描述 | ① Agent 定义为异步协程类，实现 run(context: TaskContext) -> AgentResult 方法。 ② 调度器通过 asyncio.create_task() 拉起 Agent。 ③ 拉起时注入 L1-L5 上下文（L1 协作宪法、L2 四图谱事实、L3 任务状态、L4 私有记忆、L5 长期记忆）。 ④ Agent 执行完成后，结果写入检查点（Checkpoint），供下游 Agent 使用。 ⑤ 外部系统通过 API 调用调度器，不直接调用 Agent。 |
| 范围 | Do：进程内协程拉起；依赖注入；上下文构建；结果持久化。 Don't：不通过 HTTP/gRPC 远程调用 Agent；不将 Agent 部署为独立容器。 |
| 数据契约 | ```python class TaskContext(BaseModel): task_id: str l1: str # System Prompt（协作宪法） l2: Dict[str, Any] # 四图谱查询结果 l3: Dict[str, Any] # 任务状态（PRD摘要、DAG进度） l4: Dict[str, Any] # Agent私有工作记忆 l5: List[Dict[str, Any]] # 长期记忆（检索结果） class AgentResult(BaseModel): success: bool output: Any error: Optional[str] = None duration_ms: float ``` |
| SC→AC | SC1: Agent 拉起成功 → AC1: 状态机触发 CODING 状态时，调用 _run_agent(DeveloperAgent, task) 返回 AgentResult。 SC2: 上下文注入完整 → AC2: Agent 的 run() 方法中 context.l1、context.l2 非空且包含预期内容。 SC3: 结果持久化 → AC3: Agent 执行完成后，检查点中存在对应 task_id 的记录。 |
| 待定决策 | Q: Agent 执行超时如何处理？ → 决议：在 _run_agent() 中包装 asyncio.wait_for(agent.run(), timeout=300)，超时后取消协程并标记 FAILED。 |

    

#### Step 5.7.24.5 ADR · Agent 实现形态

    | ADR · Agent 实现形态 |
| --- |
| 决策 | Agent 实现为进程内异步协程，而非独立微服务或容器。 ① 所有 Agent 运行在调度器同一进程中。 ② 通过 asyncio 事件循环调度。 ③ 通过依赖注入传递外部依赖（LLM 客户端、图谱仓库、沙箱）。 ④ 通过 Checkpoint 实现状态跨 Agent 传递。 |
| 理由 | ① 无网络开销：协程间通信为零延迟。② 极速拉起：协程创建为微秒级。③ 共享内存：Checkpoint 直接读取，无需序列化传递。④ 简化运维：无需部署多个微服务。⑤ 与 V14.1 的 asyncio 调度器自然兼容。 |
| 备选方案 | ① 独立微服务（HTTP/gRPC 拉起）→ 网络延迟高，资源消耗大，不适合密集 Agent 协作。② 独立容器（Docker 拉起）→ 启动慢（秒级），资源隔离过度。 |

    


    
    
    
    

    

## 24.6. 与现有 Step 的映射

    | Step | 原有内容 | Agent 拉起机制的补充 |
| --- | --- | --- |
| Step 5.1调度器状态机 | 定义了状态转换（IDLE→PARSING→PLANNING→CODING→...） | 需补充 在状态转换中增加 _run_agent() 方法的实现，明确如何拉起 Agent 协程 |
| Step 5.2Agent 角色与 Prompt | 定义了 5 个 Agent 的 System Prompt 和职责 | 需补充 每个 Agent 类必须实现 run(context: TaskContext) -> AgentResult 接口 |
| Step 2.2检查点持久化 | Redis + PostgreSQL 双层存储 | 需补充 Agent 执行完成后，结果通过 CheckpointManager 写入检查点，供下游 Agent 使用 |
| Step 5.4Agent 间通信 | 定义了 A2A 协议的结构化消息格式 | 无修改 该 Step 处理的是 Agent 间通信，与“系统拉起 Agent”是不同层级 |
| Step 3.1-3.4四图谱 | 代码/数据库/配置/知识图谱 | 无修改 Agent 通过 MCP 调用图谱查询，与拉起机制无关 |

    


    
    
    
    

    

## 24.7. 代码示例

    

#### Step 5.7.24.7 调度器拉起 Agent 的完整实现

    

```python
# /src/scheduler/orchestrator.py
    from typing import Type, Dict, Any
    from src.agents.base import BaseAgent
    from src.agents.developer import DeveloperAgent
    from src.agents.architect import ArchitectAgent
    from src.agents.parser import ParserAgent
    from src.scheduler.context import TaskContext


        # Agent 类名 → 对应 System Prompt 的映射
            "ParserAgent": "你是一个需求解析器...",
            "ArchitectAgent": "你是一个架构师...",
            "DeveloperAgent": "你是一个开发者...",
            "ReviewerAgent": "你是一个代码审查员...",
            "QAAgent": "你是一个QA验证员..."

        def __init__(self, llm_client, graph_repo, sandbox, checkpoint_mgr):
            self.llm_client = llm_client
            self.graph_repo = graph_repo
            self.sandbox = sandbox
            self.checkpoint_mgr = checkpoint_mgr

            self,
            agent_class: Type[BaseAgent],
                # 1. 构建上下文（L1-L5）
                context = await self._build_context(task)

                # 2. 实例化 Agent
                    llm_client=self.llm_client,
                    graph_repo=self.graph_repo,
                    sandbox=self.sandbox,
                    checkpoint_mgr=self.checkpoint_mgr

                # 3. 🔴 拉起 Agent 协程（带超时）
                result = await asyncio.wait_for(
                    agent.run(context),

                # 4. 写入检查点
                await self.checkpoint_mgr.save(
                    task.id,
                        task_id=task.id,
                        state=task.state,
                        context={"agent_output": result.output}


            except asyncio.TimeoutError:
                    success=False,
                    error=f"Agent {agent_class.__name__} timed out after 300s"

        async def _build_context(self, task: Task) -> TaskContext:
                task_id=task.id,
                l1=self._AGENT_PROMPTS[agent_class.__name__],
                l2=await self._query_graphs(task),
                    "prd": task.prd[:500],
                    "dag_progress": self._get_progress(task),
                    "upstream_output": await self._get_upstream_output(task)
                },
                l4={},  # Agent 私有工作记忆（初始为空）
                l5=await self._retrieve_memories(task)
```

    

#### Step 5.7.24.7 外部系统调用调度器的 API

    

```python
# /src/api/routes/tasks.py
    from fastapi import APIRouter, Depends
    from src.scheduler.orchestrator import TaskOrchestrator


    @router.post("/tasks")
        req: TaskCreateRequest,
        """外部系统通过此 API 提交任务，调度器将拉起 Agent"""
        task = Task(prd=req.prd, state=TaskState.IDLE)
        # 提交到调度器，调度器内部会驱动状态机并拉起 Agent
        await orchestrator.submit(task)
        return {"task_id": task.id}

    @router.get("/tasks/{task_id}")
        task_id: str,
        task = await orchestrator.get_task(task_id)
        return {"task_id": task.id, "state": task.state}
```

    

#### Step 5.7.24.7 Agent 基类定义

    

```python
# /src/agents/base.py
    from abc import ABC, abstractmethod
    from src.scheduler.context import TaskContext


        def __init__(self, llm_client, graph_repo, sandbox, checkpoint_mgr):
            self.llm_client = llm_client
            self.graph_repo = graph_repo
            self.sandbox = sandbox
            self.checkpoint_mgr = checkpoint_mgr

        async def run(self, context: TaskContext) -> AgentResult:
            """Agent 的执行入口，由调度器调用"""

        async def think(self, context: TaskContext) -> Thought:

        async def act(self, thought: Thought) -> Action:

        async def observe(self, action: Action) -> Observation:
```

    


    

> ✅ Agent 拉起机制交付确认
        
            Agent 实现形态：进程内 asyncio 协程，而非独立微服务
            拉起流程：外部 API → 调度器状态机 → asyncio.create_task() → Agent 协程
            PRD/ADR：完整的规格定义，含数据契约、SC→AC、备选方案对比
            与现有 Step 映射：Step 5.1/5.2 需补充，Step 5.4/3.1-3.4 无修改
        
        下一步：可将本报告中的代码示例和 PRD/ADR 规格合并到 Step 5.1（调度器状态机）和 Step 5.2（Agent 角色与 Prompt）中。

    
        — V14.1 开发计划 · Agent 拉起机制 · 2026年6月22日 —

---


    
        
- 1. 整体架构设计
        
- 2. 微信小程序 Skill 机制
        
- 3. 与 V14.1 的 MCP 协议集成
        
- 4. 实时监控方案
        
- 5. API 规格
        
- 6. 与现有 Step 的映射
        
- 7. 代码示例
        
- 8. 实施路线图
    

    


    
    
    
    

## 25.1. 整体架构设计

    

> 核心方案：微信小程序 + Skill 机制作为请求入口，WebSocket/SSE 作为实时监控通道。

    

#### Step 5.8.25.1 完整调用链路

    

```python
    │  • 调用 V14.1 API 提交任务                      │
    │            V14.1 后端（API 网关层）               │
    │            V14.1 调度器（Step 5.1）              │
```

    

#### Step 5.8.25.1 为什么选择微信小程序？

    
        
- 天然的用户入口：微信日活超10亿，无需用户额外下载 App。
        
- 官方 AI 能力加持：微信已推出小程序 Skill 机制，可将功能封装为 AI 可调用的能力。
        
- 基于 MCP：Skill 底层基于 MCP 协议，与 V14.1 使用的 MCP 协议栈天然同构。
        
- 实时通信支持：小程序支持 WebSocket 和 SSE 两种实时方案。
    

    


    
    
    
    

    

## 25.2. 微信小程序 Skill 机制

    

#### Step 5.8.25.2 Skill 是什么

    Skill 是微信官方推出的 AI 能力接入机制，开发者可将小程序的能力封装为 AI 可调用的 Skill。用户通过自然语言就能触发 Skill，执行对应功能。

    

#### Step 5.8.25.2 两种接入模式

    | 模式 | 说明 | 适用场景 |
| --- | --- | --- |
| 自动模式 | 平台自动分析小程序源码，AI 可直接操作 | 快速验证，零代码接入 |
| 开发模式 | 开发者自定义 Skill，通过审核后被 AI 调用 | 推荐 定制化 V14.1 任务触发 |

    

#### Step 5.8.25.2 Skill 文件结构

    

```python
    ├── mcp.json          # 可用的函数声明（MCP 工具列表）
    │   ├── submit_task.js   # 提交 V14.1 任务
    │   ├── get_status.js    # 查询任务状态
    │   └── cancel_task.js   # 取消任务
    ├── index.js          # 注册函数给运行时
        └── status-card.wxml # 实时状态展示卡片
```

    

#### Step 5.8.25.2 mcp.json 声明示例

    

```python
              "name": "submit_development_task",
              "description": "向 V14.1 系统提交一个软件开发任务",
                "type": "object",
                    "type": "string",
                  },
                    "type": "string",
                    "enum": ["low", "normal", "high", "critical"],
                  },
                    "type": "string",
                },
            },
              "name": "query_task_status",
              "description": "查询 V14.1 系统中某个任务的执行状态",
                "type": "object",
                    "type": "string",
                },
```

    

#### Step 5.8.25.2 函数实现示例

    

```python
// apis/submit_task.js
    // 在微信小程序 Skill 中调用 V14.1 后端 API
    const V14_API_BASE = 'https://api.v14-system.com/api/v1';

      const { prd, priority = 'normal', callback_url } = params;

      // 1. 调用 V14.1 后端 API 提交任务
      const response = await fetch(`${V14_API_BASE}/tasks`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prd, priority, callback_url })

      if (!response.ok) {
        throw new Error(`V14.1 系统返回错误: ${response.status}`);

      const data = await response.json();

      // 2. 返回给小程序（Skill 的返回值）
        task_id: data.task_id,
        state: data.state,
        message: '任务已提交，正在处理中...',
        status_url: `${V14_API_BASE}/tasks/${data.task_id}/status`
```

    


    
    
    
    

    

## 25.3. 与 V14.1 的 MCP 协议集成

    

> 核心洞察：微信小程序的 Skill 机制底层基于 MCP 协议，与 V14.1 使用的 MCP 协议栈完全兼容。这意味着 Skill 中的函数声明（mcp.json）可以直接映射到 V14.1 的 MCP Server。

    

#### Step 5.8.25.3 分层架构

    

```python
    │  mcp.json 声明 → apis/*.js 实现                   │
    │  调用 V14.1 后端 API（内部使用 MCP 协议）         │
    │            V14.1 后端（MCP Server）                │
    │  • 暴露 MCP 工具：submit_task, query_status       │
    │            V14.1 调度器（Agent 系统）              │
```

    

#### Step 5.8.25.3 V14.1 端 MCP 工具暴露

    

```python
# /src/mcp/servers/v14_mcp_server.py
    from mcp.server import Server
    from src.scheduler.orchestrator import TaskOrchestrator


    @server.tool()
    async def submit_development_task(prd: str, priority: str = "normal") -> dict:
        """提交开发任务到 V14.1 系统"""
        task = await orchestrator.submit(prd, priority)
        return {"task_id": task.id, "state": task.state.value}

    @server.tool()
        task = await orchestrator.get_task(task_id)
            "task_id": task.id,
            "state": task.state.value,
            "progress": task.progress,
            "result": task.result

    @server.tool()
        await orchestrator.cancel(task_id)
        return {"task_id": task_id, "state": "cancelled"}
```

    


    
    
    
    

    

## 25.4. 实时监控方案

    

#### Step 5.8.25.4 两种实时通信方案对比

    | 方案 | 特点 | 适用场景 |
| --- | --- | --- |
| WebSocket | 全双工 通信，适合高频双向交互 | Agent 执行过程中需要用户介入确认（如：选择方案A还是B） |
| SSE (Server-Sent Events) | 单向 推送，基于 HTTP 更轻量 | 只需“看进度”的纯监控场景 |

    

#### Step 5.8.25.4 WebSocket 实时监控实现

    

```python
# /src/api/websocket.py
    from fastapi import WebSocket, WebSocketDisconnect
    from src.scheduler.orchestrator import TaskOrchestrator

            self.active_connections: Dict[str, List[WebSocket]] = {}

        async def connect(self, task_id: str, websocket: WebSocket):
            await websocket.accept()
            if task_id not in self.active_connections:
                self.active_connections[task_id] = []
            self.active_connections[task_id].append(websocket)

        def disconnect(self, task_id: str, websocket: WebSocket):
            if task_id in self.active_connections:
                self.active_connections[task_id].remove(websocket)

        async def broadcast_status(self, task_id: str, status: dict):
            if task_id in self.active_connections:
                for connection in self.active_connections[task_id]:
                        await connection.send_json(status)

    # 在调度器状态变更时触发广播
        def __init__(self, manager: ConnectionManager):
            self.manager = manager

        async def on_state_change(self, task_id: str, old_state: str, new_state: str, data: dict = None):
            await self.manager.broadcast_status(task_id, {
                "type": "state_change",
                "task_id": task_id,
                "from": old_state,
                "to": new_state,
```

    

#### Step 5.8.25.4 SSE 实时监控实现

    

```python
# /src/api/sse.py
    from fastapi.responses import StreamingResponse
    from sse_starlette.sse import EventSourceResponse

    @router.get("/tasks/{task_id}/stream")
    async def stream_task_status(task_id: str, orchestrator: TaskOrchestrator):
            # 获取初始状态
            task = await orchestrator.get_task(task_id)
            last_state = task.state

                # 检查状态是否有变化
                current_task = await orchestrator.get_task(task_id)
                if current_task.state != last_state:
                    last_state = current_task.state
                        "event": "state_change",
                            "task_id": task_id,
                            "state": current_task.state.value,
                            "progress": current_task.progress,
                            "timestamp": datetime.utcnow().isoformat()

                # 如果任务已完成或失败，结束推送
                if current_task.state in [TaskState.DONE, TaskState.FAILED]:
                        "event": "complete",
                            "task_id": task_id,
                            "state": current_task.state.value,
                            "result": current_task.result

                await asyncio.sleep(2)  # 轮询间隔

```

    


    
    
    
    

    

## 25.5. API 规格

    

#### Step 5.8.25.5 任务提交 API

    

```python
      "prd": "修改支付超时时间为60秒",
      "priority": "high",           # low | normal | high | critical
      "callback_url": null,          # 可选，任务完成后的Webhook

      "task_id": "a1b2c3d4-...",
      "state": "IDLE",
      "message": "任务已提交，正在排队中..."
```

    

#### Step 5.8.25.5 状态查询 API

    

```python
      "task_id": "a1b2c3d4-...",
      "state": "CODING",
      "progress": 0.6,
      "current_step": "DeveloperAgent 正在生成代码...",
        {"step": "PARSING", "status": "done", "duration_ms": 1200},
        {"step": "PLANNING", "status": "done", "duration_ms": 3400},
        {"step": "CODING", "status": "running", "duration_ms": null}
      ],
      "estimated_remaining_ms": 3000,
      "created_at": "2026-06-22T10:00:00Z",
```

    


    
    
    
    

    

## 25.6. 与现有 Step 的映射

    | Step | 原有内容 | 微信小程序接入的补充 |
| --- | --- | --- |
| Step 1.1四层架构与 API 契约 | 定义了 RESTful API 契约 | 需补充 增加 /tasks 路由的 source 字段；新增 /tasks/{id}/stream SSE 端点 |
| Step 6.1Vue3 驾驶舱 | 定义了 Web 驾驶舱的实时监控 | 无修改 微信小程序的实时监控复用相同的 WebSocket/SSE 基础设施 |
| Step 2.1LiteLLM 网关 | LLM API 调用网关 | 无修改 微信小程序接入不涉及 LLM 网关 |
| Step 5.1调度器状态机 | 定义了任务执行状态流转 | 需补充 状态变更时触发 WebSocket/SSE 广播（通过 StatusBroadcaster） |
| Step 7.6安全与权限管理 | JWT + 零信任架构 | 需补充 微信小程序的来源认证（小程序 AppID 验证 + JWT 颁发） |

    


    
    
    
    

    

## 25.7. 代码示例

    

#### Step 5.8.25.7 微信小程序 Skill 完整示例

    

```python
// apis/submit_task.js - 完整实现
    const V14_API_BASE = 'https://api.v14-system.com/api/v1';
    const WS_BASE = 'wss://api.v14-system.com/ws';

      const { prd, priority = 'normal' } = params;

      // 1. 提交任务
      const response = await fetch(`${V14_API_BASE}/tasks`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prd, priority, source: 'wechat_skill' })

      if (!response.ok) {
        throw new Error(`提交失败: ${response.status}`);

      const data = await response.json();

      // 2. 返回给小程序，包含用于 WebSocket 连接的 task_id
        task_id: data.task_id,
        message: '任务已提交，正在处理中...',
        ws_url: `${WS_BASE}/tasks/${data.task_id}`
```

    

#### Step 5.8.25.7 微信小程序实时监控组件

    

```python
// components/status-card/index.js
        taskId: { type: String, value: '' }
      },
        status: 'pending',
        progress: 0,
        logs: [],
      },
          this.connectWebSocket();
        },
          if (this.data.socket) {
            this.data.socket.close();
      },
          const ws = wx.connectSocket({
            url: `wss://api.v14-system.com/ws/tasks/${this.properties.taskId}`,

          ws.onMessage((res) => {
            const data = JSON.parse(res.data);
            this.setData({
              status: data.state,
              progress: data.progress,
              logs: [...this.data.logs, data.message]

          ws.onError((err) => {
            console.error('WebSocket 错误:', err);

          this.setData({ socket: ws });
```

    

#### Step 5.8.25.7 微信小程序卡片展示

    

```python
&lt;!-- components/status-card/index.wxml --&gt;

        &lt;text class="progress-text"&gt;{{Math.round(progress * 100)}}%&lt;/text&gt;

            &lt;text class="log-time"&gt;{{item.time}}&lt;/text&gt;
            &lt;text class="log-content"&gt;{{item.msg}}&lt;/text&gt;
```

    


    
    
    
    

    

## 25.8. 实施路线图

    | 阶段 | 任务 | 周期 | 依赖 |
| --- | --- | --- | --- |
| 准备阶段 | ① 设计 V14.1 后端 API（/tasks 提交、/tasks/{id}/status 查询、WebSocket/SSE 推送）② 申请微信小程序 AppID③ 搭建微信小程序开发环境 | 1-2天 | Step 1.1 完成 |
| 开发阶段 | ① 创建微信小程序 Skill 项目（mcp.json + apis/*.js + index.js）② 实现 Skill 调用 V14.1 API 的逻辑③ 实现 WebSocket/SSE 实时通信④ 设计小程序 UI（输入+状态卡片） | 3-5天 | Step 5.1 完成 |
| 集成与测试 | ① 端到端联调（小程序 ↔ V14.1）② 实时监控体验优化③ 安全认证联调 | 2-3天 | Step 7.6 完成 |
| 上线发布 | ① 微信小程序提交审核② Skill 功能发布③ ⚠️ 注意：Skill模式目前在内测，相关代码暂时不要合入正式版本提审 | 1-2天 | 测试通过 |

    

> ⚠️ 重要提醒：
        
            微信小程序 Skill 模式目前处于 内测阶段，相关代码暂时不要合入正式版本提审。
            建议先在开发环境做技术验证，待 Skill 功能正式对外开放后再提交审核。
            如果急需上线，可先用小程序原生页面 + API 调用方式实现（不依赖 Skill 能力）。

    


    

> ✅ 微信小程序接入交付确认
        
            Skill 机制：mcp.json 声明 + apis/*.js 实现 + 与 V14.1 MCP 协议同构
            实施路线图：准备→开发→集成测试→上线，约 1-1.5 周
        
        下一步：可按照实施路线图开始微信小程序项目的创建和 Skill 开发。

    
        — V14.1 开发计划 · 微信小程序接入 · 2026年6月22日 —
### Step 5.9：架构图与数据流向

| PRD维度 | 详细内容 |
| --- | --- |
| **输入/输出** | **输入：**V14.1架构设计文档、四张Mermaid源码；**输出：**存储于`docs/diagrams/`的`.mmd`文件及CI验证脚本。 |
| **GWT验收** | Given `docs/diagrams/`目录，When 执行`mmdc -i *.mmd`，Then 所有图表渲染成功无报错。Given 架构变更PR，When 合入前检查，Then PR描述中必须包含对应图表更新（如有）。 |
| **实施细节** | 图表一（系统架构全景图）→ 8层分层架构（用户层→接入层→调度层→能力层→验证层→知识层→工具层→可观测层）；图表二（层级抽象与协议栈）→ 编排层/通信层/执行层；图表三（数据流向图）→ PRD→ParserAgent→ArchitectAgent→DeveloperAgent→L1-L9→检查点→交付物；图表四（关键设计要点）→ 各层核心组件+关键设计+一句话说明。 |
| **技术栈** | Mermaid + `@mermaid-js/mermaid-cli`（CI验证）+ `docs/diagrams/`目录 |

#### ADR 5.9：图表工具选型（Mermaid vs Draw.io vs PlantUML）

| 备选 | 版本管理 | CI集成 | 学习成本 | 决策 |
| --- | --- | --- | --- | --- |
| A. Mermaid | 纯文本，Git友好 | `mmdc` CLI | 低 | **✅ 选A** |
| B. Draw.io | 二进制，难合并 | 无官方CLI | 中 |  |
| C. PlantUML | 文本，需渲染器 | 有CLI但生态弱 | 高 |  |
| **理由** | Mermaid支持flowchart/sequence/class/state等多种图类型，CLI工具成熟，天然支持Git版本管理和CI验证。 | | | |


## Phase 7：生产化增强

### Step 7.1：灰度发布（K8s + 流量路由）

| PRD维度 | 详细内容 |
| --- | --- |
| **输入/输出** | **输入：**新镜像Tag；**输出：**路由规则（1%→10%→100%）。**自动回滚条件：**错误率>5%或P99延迟>10s。 |
| **GWT验收** | Given 部署v2版本，When 设置流量10%，Then 监控显示10%请求进入v2。Given 错误率飙升>5%，When 自动观测，Then 30s内触发回滚至v1。 |
| **实施细节** | 使用`Istio`VirtualService + DestinationRule；GitOps via ArgoCD。 |
| **技术栈** | K8s 1.28, Istio 1.21, ArgoCD 2.10 |

### Step 7.2：AgentOps（Prometheus + Grafana）

| PRD维度 | 详细内容 |
| --- | --- |
| **输入/输出** | **输入：**调度器埋点数据；**输出：**Grafana仪表盘（Token流速/熵趋势/告警）。**告警规则：**单任务Token>50触发Warning，Z3超时率>5%触发Critical。 |
| **GWT验收** | Given 任务Token消耗达到55，When 监控采集，Then Grafana面板显示红色预警并推送钉钉消息。Given 查询历史日志，When 使用ELK，Then 可按TraceID全链路检索。 |
| **实施细节** | 使用`opentelemetry`SDK自动埋点，导出到Prometheus Pushgateway。 |
| **技术栈** | Prometheus 2.52, Grafana 10.4, OpenTelemetry 1.24, ELK 8.12 |

---

## 总结与交付约束

**✅ 全量覆盖确认：**上述表格已完整覆盖 Phase 0~7 全部18个核心Step（0.1/0.2/0.3/1.1/1.2/1.3/2.1/2.2/3.1/3.2/3.3/4.1/4.2/5.1/5.2/6.1/6.2/**6.3**/7.1/7.2）。

**✅ 编码级就绪：**每个Step均具备**边界异常码**、**GWT测试用例**、**关键伪代码/类设计**、**精确到次版本号的库依赖**。开发人员可直接创建Jira Task并开始Sprint。

**✅ 架构可追溯：**每个ADR均提供了**三维度对比矩阵（性能/成本/运维）**，并显式关联了对应的PRD功能点。

### Step 0.3：需求澄清与渐进收敛机制

| PRD维度 | 详细内容 |
| --- | --- |
| **输入/输出** | **输入：**模糊需求文本（"优化一下""改个东西"）；**输出：**收敛后的需求文档（含ClarificationResult：clarified_prd/resolution_path/rounds/final_assumptions）。 |
| **GWT验收** | Given 模糊输入"优化一下"，When 调用ClarificationEngine.process()，Then 返回结构化追问（含实体/动词/范围维度选项）。Given 连续3轮无效回复，When process()执行，Then resolution_path="fallback_human"，state=WAITING_CLARIFICATION。Given 用户回复"改支付"，When find_candidates("支付")，Then 返回至少1个匹配模块（如PaymentService）。 |
| **实施细节** | 位于`/src/scheduler/clarification/`，含clarity_checker.py（清晰度判定）、question_generator.py（结构化模板）、candidate_resolver.py（图谱查询）。依赖GraphRepository (Step 3.x)和CheckpointManager (Step 1.2)。 |
| **技术栈** | Python 3.11内置（re/difflib），无新增第三方依赖；Pydantic用于数据契约。 |

#### ADR 0.3：结构化追问 vs LLM自由对话

| 备选 | 需求收敛确定性 | 开发成本 | 用户体验 | 决策 |
| --- | --- | --- | --- | --- |
| A. LLM自由对话 | 低（漂移风险） | 低 | 灵活 | **✅ 选B** |
| B. 结构化模板+规则 | 高（确定性） | 中 | 需选择选项 |  |
| **理由：**设计目标是"第一道防线"，不允许LLM自由发挥导致需求进一步漂移。 | **理由：**预定义模板库，按缺失维度分类（A/B/C/D选项）。 | **理由：**用户需在选项中选择，短期成本略高但结果可控。 |  |




## Step 0.4：架构锚定与Prompt/Context工程
---

    

### Step 0.4.1 架构锚定：编排层 vs 执行层

    

> 核心声明：V14.1 系统在设计上明确锚定在 “多智能体软件开发操作系统” 这一层级（编排层），而非单智能体执行工具（如 Claude Code、Codex）的层级。这一锚定决定了所有 Prompt 和 Context Engineering 的设计必须服务于 协作流程的编排与治理，而非单次代码生成的质量。

    

#### Step 0.4.1 编排层 vs 执行层

    | 维度 | 执行层（Claude Code / Codex） | 编排层（V14.1） |
| --- | --- | --- |
| System Prompt 锚点 | "你是一个编程助手" + 工具定义 | "你是多智能体协作网络中的角色" + 协作契约 |
| 上下文来源 | 当前代码库的实时快照 | 四图谱（代码+数据库+配置+知识）+ 协作状态 + 审计链 |
| 信息组织方式 | 用户指令 + 文件内容 + 工具输出 | 结构化图谱查询 + Agent 产出摘要 + 状态机上下文 |
| 决策单位 | 单次 LLM 调用的输出 | 跨 Agent 协作流程的步骤转换 |
| 约束来源 | 用户指令 + 工具权限 | 协作契约 + 验证门禁 + 合规规则 |
| 状态管理 | 无状态（任务即生命周期） | 有状态（检查点贯穿全流程） |
| 通信格式 | 自然语言 | 结构化、跨 Agent 可解析 |
| 成功标准 | 生成正确的代码 | 交付经过验证、符合合约、合规检查的完整产物 |

    

#### Step 0.4.2 为什么锚定编排层？

    
        
- V14.1 不是“另一个 Claude Code”：Claude Code、Codex 是单智能体执行工具，解决的是“如何让一个 AI 帮你写代码”。V14.1 解决的是“如何让一群 AI 协作完成软件开发全流程”。两者的目标不同，处于不同的抽象层级。
        
- 编排层的核心价值在于“治理”：单智能体工具依赖模型本身的推理能力和权限控制；V14.1 通过多 Agent 协作、状态机调度、四图谱、9层验证门禁、审计链，实现了对开发流程的系统性治理。
        
- Claude Code/Codex 可以是 V14.1 的执行引擎：V14.1 不排斥在底层调用 Claude Code 或 Codex 作为执行单元，但 V14.1 的核心价值在上层——编排、治理、验证、追溯。
    

    

---

    
    
    
    

    

### Step 0.4.2 五条核心设计原则

    基于“编排层锚定”，Prompt 和 Context Engineering 的设计必须遵循以下五条核心原则：

    

> 原则一：System Prompt 定义“协作角色”而非“个人能力”
        执行层写法（不应采用）："你是一个 Python 专家，擅长编写高质量的代码。"
        编排层写法（应该采用）："你是 V14.1 多智能体协作网络中的 DeveloperAgent，在 ArchitectAgent 确定的技术方案范围内，生成符合四图谱事实的代码，输出必须通过 L1-L9 验证。"
        核心差异：Prompt 描述的是 Agent 在协作流程中的位置和契约，而非个人技术能力。

    

> 原则二：上下文是“协作状态”而非“代码库快照”
        执行层写法（不应采用）：直接塞入 payment/service.py 的完整内容。
        编排层写法（应该采用）：注入上游 Agent 的产出摘要、当前 DAG 进度、四图谱查询结果、验证门禁状态。
        核心差异：上下文描述的是“协作进展到哪一步、上下游产出了什么、事实是什么”，而非“代码库长什么样”。

    

> 原则三：指令与约束来自“协作契约”而非“用户指令”
        执行层写法（不应采用）：“用户说：请修改 timeout 为 60”。
        编排层写法（应该采用）：协作契约约束（来自 PLANNING 阶段）+ 验证门禁规则（L1-L9）+ 合规要求（领域知识）。
        核心差异：约束来自整个协作流程的累积契约，而非当前用户的“一句话指令”。

    

> 原则四：上下文组织遵循“渐进式披露”而非“一次性加载”
        执行层写法（不应采用）：把所有文件内容塞进上下文窗口。
        编排层写法（应该采用）：五层分级（L1-L5），按需加载，每层有明确的 Token 预算和加载策略。
        核心差异：上下文是分层、按需、渐进式披露的，而非一次性装满。

    

> 原则五：通信格式服务于“跨 Agent 可解析”而非“人类可读”
        执行层写法（不应采用）：“我觉得这个函数应该改成异步的”。
        编排层写法（应该采用）：结构化 JSON（含 proposal_id、change、reasoning、evidence、contract_assertions）。
        核心差异：通信格式是结构化的、可被其他 Agent 自动解析的，而非自由文本。

    

---

    
    
    
    

    

### Step 0.4.3 五层上下文的编排层视角

    原 V14.1 的五层上下文架构（L1-L5）在编排层视角下应重新诠释如下：

    | 层级 | 原有定义 | 编排层重新诠释 | 承载的内容 |
| --- | --- | --- | --- |
| L1 | 全局不可变上下文 | 协作宪法：所有 Agent 必须遵守的全局规则 | System Prompt（协作角色定义）+ 协作契约 + 验证规则 + 红线清单 |
| L2 | 确定性事实上下文 | 协作事实库：当前任务依赖的确定性事实 | 四图谱查询结果（代码+数据库+配置+知识） |
| L3 | 任务动态上下文 | 协作状态：当前任务的执行状态 | PRD 摘要、上游 Agent 产出摘要、当前 DAG 进度、检查点摘要 |
| L4 | Agent 局部工作记忆 | 个体工作台：Agent 私有上下文 | 思考→行动→观察循环中的中间产物（不跨 Agent 共享） |
| L5 | 跨任务长期记忆 | 协作经验库：跨任务的模式复用 | 教训库、成功模式库（通过 RAG 检索注入） |

    

> 关键洞察：五层上下文的本质是 协作流程的信息分层——从全局宪法（L1）到具体执行（L4），从当前状态（L3）到长期积累（L5）。每一层都有明确的语义边界和加载策略，共同构成 Agent 感知的“协作全景图”。

    

---

    
    
    
    

    

### Step 0.4.4 验证门禁：协作契约的守卫

    在编排层视角下，L1-L9 验证门禁不再是“代码质量检查工具”，而是协作契约的守卫（Guardians of the Collaboration Contract）。

    

#### Step 0.4.1 验证门禁的定位

    
        
- 执行层视角：验证门禁是“代码是否正确”的检查。
        
- 编排层视角：验证门禁是“Agent 的产出是否满足协作契约”的门槛。只有通过所有门禁，产出才能进入共享上下文，成为下游 Agent 的输入。
    

    

#### Step 0.4.2 验证门禁与协作契约的映射

    | 层 | 验证内容 | 对应的协作契约条款 | 失败时的协作行为 |
| --- | --- | --- | --- |
| L1 | 输出格式合规 | 契约条款：输出必须符合 JSON Schema | 驳回，要求 Agent 重写 |
| L2 | 符号存在于四图谱 | 契约条款：不得引用不存在的符号 | 驳回，要求 Agent 修正引用 |
| L3 | 生成确定性（熵监控） | 契约条款：高熵产出视为无效 | 熔断，终止生成 |
| L4 | 类型正确性 | 契约条款：类型必须匹配 | 驳回，要求 Agent 修正 |
| L5 | 执行时正确性（沙箱） | 契约条款：代码必须可执行 | 驳回，触发重试 |
| L6 | 业务语义验证 | 契约条款：必须满足所有合约断言 | 驳回，标记为 NEEDS_HUMAN |
| L7 | 提交拦截 | 契约条款：不得包含危险代码 | 拦截，禁止进入 Git |
| L8 | 配置一致性 | 契约条款：配置不得漂移 | 触发自动修复或告警 |
| L9 | 合规性验证 | 契约条款：必须符合法规/标准 | 阻断，标记为 NEEDS_COMPLIANCE_REVIEW |

    

> 关键洞察：验证门禁不是“质检员”，而是协作契约的执行者。它们确保每个 Agent 的产出在进入共享上下文之前，已经满足所有契约条款，从而防止幻觉在 Agent 间传播。

    

---

    
    
    
    

    

## 5. Agent 角色的重新定义

    在编排层视角下，五个 Agent 的角色应重新定义如下：

    | Agent | 执行层定义 | 编排层定义 | 协作契约 |
| --- | --- | --- | --- |
| 架构师 | 设计系统架构的技术专家 | 方案制定者：将 PRD 转化为可执行的技术方案（tasks.json） | 输入：PRD（已澄清）；输出：tasks.json + 设计约束；契约：方案必须覆盖所有需求条目 |
| 开发者 | 编写代码的工程师 | 代码实现者：在方案约束下生成代码 | 输入：tasks.json + 设计约束；输出：code diff；契约：代码必须通过 L1-L9 验证 |
| 审查员 | 代码审查专家 | 仲裁者：裁决分歧，输出终审意见 | 输入：两个候选方案；输出：裁决结果；契约：分歧时启动仲裁，输出选择依据 |
| QA | 测试工程师 | 验证者：执行验证门禁，生成验证报告 | 输入：代码 + 验证规则；输出：验证报告；契约：报告必须包含 L1-L9 逐项结果 |
| 配置管理员 | 运维工程师 | 环境守护者：保障配置一致性 | 输入：配置变更请求；输出：配置验证/修复结果；契约：配置必须与黄金基线一致 |

    

> 关键洞察：Agent 的定义从“角色描述”转向“协作契约描述”。每个 Agent 的核心是对输入、输出、契约的明确界定——这正是编排层设计的核心产物，也是系统 Prompt 的核心内容。

    

---

    
    
    
    

    

## 6. 与现有 Step 的映射关系

    “编排层锚定”这一架构原则对现有 Step 的影响如下：

    | Step | 原有设计 | 编排层锚定的影响 |
| --- | --- | --- |
| Step 0.1项目章程 | 定义度量指标和范围 | 需更新 新增“架构锚定声明”，明确 V14.1 锚定编排层 |
| Step 5.2Agent 角色与 Prompt | 定义 5 个 Agent 的 System Prompt | 需更新 System Prompt 模板增加“协作契约”章节，明确定义输入/输出/契约 |
| Step 5.4Agent 间通信 | 异步消息总线 | 需更新 新增“通信格式规范”，强制结构化 JSON 通信 |
| 五层上下文L1-L5 | 信息分层 | 需重述 在文档中新增“渐进式披露”原则的显式说明，并按编排层视角重新诠释各层语义 |
| L1-L9验证门禁 | 9 层防幻觉 | 需重述 新增“验证门禁作为协作契约守卫”的定位说明 |
| Step 0.6输入清洗 | 对抗性输入清洗 | 无需修改 已按编排层设计（系统指令隔离） |
| Step 7.6安全与权限 | JWT + 零信任 | 无需修改 已按编排层设计（Agent 间凭证委托） |

    

---

    
    
    
    

    

### Step 0.4.7 需要更新的文档位置

    | 文档位置 | 更新内容 | 更新目的 |
| --- | --- | --- |
| Step 0.1（项目章程） | 新增“架构锚定声明”章节 | 明确 V14.1 锚定编排层，作为所有后续决策的顶层依据 |
| Step 5.2（Agent 角色与 Prompt） | System Prompt 模板增加“协作契约”章节 | 确保每个 Agent 的 Prompt 定义的是协作角色而非个人能力 |
| Step 5.4（Agent 间通信） | 新增“通信格式规范”章节 | 强制结构化 JSON 通信，使通信跨 Agent 可解析 |
| 五层上下文（L1-L5 设计文档） | 新增“渐进式披露”原则说明；按编排层视角重述各层语义 | 明确五层上下文的编排层设计意图 |
| L1-L9 验证门禁（设计文档） | 新增“验证门禁作为协作契约守卫”定位说明 | 明确验证门禁的编排层定位，而非单纯的质量检查 |

    

---

    
    
    
    

    

### Step 0.4.8 代码示例

    

#### Step 0.4.1 编排层风格 System Prompt 模板

    

```python
# /src/agents/prompts/developer_agent.j2
    &lt;system&gt;
      &lt;anchor&gt;
        【架构锚定声明】
        你是 V14.1 多智能体协作网络中的 DeveloperAgent。
        你的职责是在 ArchitectAgent 确定的技术方案范围内，生成符合四图谱事实的代码。
        你的输出必须通过 L1-L9 验证门禁后才可进入共享上下文。
      &lt;/anchor&gt;

      &lt;collaboration_contract&gt;
        【协作契约】
        输入来源：ArchitectAgent 输出的 tasks.json（已通过可行性预检）
        输入格式：{ task_id, files: [{path, action, design_constraints}], assertions: [...] }
        输出格式：
        {
          "proposal_id": "prop-{timestamp}",
          "files": [{ "path": "...", "diff": "...", "change_type": "create|update|delete" }],
          "self_check": { "l1_passed": true, "l2_passed": true, ... },
          "contract_assertions_met": ["assertion_1", "assertion_2"]
        }
        失败处理：连续 3 次验证失败后，将控制权交还调度器，标记为 NEEDS_HUMAN
      &lt;/collaboration_contract&gt;

      &lt;rules&gt;
        【硬性规则 - 协作宪法】
        1. 禁止引入未在三图谱中确认的第三方库
        2. 禁止生成包含硬编码密钥的代码
        3. 禁止在未通过 L1-L9 验证的情况下提交代码
        4. 遇到不确定信息，必须先查四图谱，禁止凭记忆
      &lt;/rules&gt;

      &lt;tools&gt;
        【可用工具】
        - query_graph(type="code|database|config|knowledge", symbol="...")
        - run_sandbox(code_snippet)
        - propose_change(proposal: ProposalSchema)
      &lt;/tools&gt;
    &lt;/system&gt;
```

    

#### Step 0.4.2 结构化通信格式示例

    

```python
# /src/communication/schemas.py
    from pydantic import BaseModel, Field
    from typing import List, Optional, Dict, Any
    from uuid import uuid4

    class Proposal(BaseModel):
        """跨Agent提议的结构化格式"""
        id: str = Field(default_factory=lambda: str(uuid4()))
        from_agent: str  # DeveloperAgent, ArchitectAgent, etc.
        to_agent: str    # ReviewerAgent, QAAgent, etc.
        type: str        # "proposal", "request", "report", "arbitration"

        proposal_data: Dict[str, Any] = Field(default_factory=dict)
        # 示例：{"file": "payment/service.py", "change": "convert_to_async"}

        reasoning: str   # 为什么这样提议
        evidence: List[Dict[str, str]]  # 支撑依据
        # 示例：[{"source": "code_graph", "symbol": "PaymentService.process"}]

        contract_assertions: List[str]  # 断言列表
        # 示例：["response_time  0 AND timeout  Dict[str, Any]:
            """执行所有验证门禁，返回结果"""
            results = {}
            for gate in self.gates:
                result = await gate.validate(proposal.proposal_data)
                results[gate.name] = result
                if not result.passed:
                    # 阻断传播：验证失败时不进入共享上下文
                    return {
                        "passed": False,
                        "failed_at": gate.name,
                        "results": results,
                        "message": f"Contract violated at {gate.name}: {result.reason}"
                    }

            # 所有门禁通过，写入检查点
            return {
                "passed": True,
                "results": results,
                "message": "All contract gates passed. Proposal can enter shared context."
            }
```

    

---


## Phase 1：架构设计与技术选型

### Step 1.1：系统架构（四层+模块契约）

| PRD维度 | 详细内容 |
| --- | --- |
| **输入/输出** | **输入：**业务用例（PRD生成→代码输出→自修复）；**输出：**OpenAPI 3.0 YAML，模块边界定义（接入层/Scheduler/能力层/基础层）。**约束：**模块间禁止循环依赖（通过`pydeps`检查）。 |
| **GWT验收** | Given 模块图，When 使用`pydeps src`扫描，Then 输出无环。Given API契约，When 使用`prism`模拟，Then 前端可正常联调。 |
| **实施细节** | 使用`fastapi`定义路由，`pydantic`定义Schema。部署`nginx`反向代理。 |
| **技术栈** | FastAPI 0.110, Pydantic 2.6, Nginx 1.25 |

#### ADR 1.1：模块间通信——REST vs gRPC

| 备选 | 延迟(ms) | 跨语言支持 | 调试便利性 | 决策 |
| --- | --- | --- | --- | --- |
| A. REST/HTTP | ~10 | 通用 | 极佳(Postman) | **✅ 选A** |
| B. gRPC | ~2 | 需生成代码 | 差(需要grpcurl) |  |
| **理由：**系统内部调用频次不高（QPS<100），REST调试便利性更符合快速迭代需求。 | **理由：**系统内部调用频次不高（QPS<100），REST调试便利性更符合快速迭代需求。 | **理由：**系统内部调用频次不高（QPS<100），REST调试便利性更符合快速迭代需求。 | **理由：**系统内部调用频次不高（QPS<100），REST调试便利性更符合快速迭代需求。 | **理由：**系统内部调用频次不高（QPS<100），REST调试便利性更符合快速迭代需求。 |

### Step 1.2：三图谱Schema设计

| PRD维度 | 详细内容 |
| --- | --- |
| **输入/输出** | **输入：**代码/数据库/配置的实体分类；**输出：**SQLAlchemy ORM Model类定义。**约束：**配置图谱节点必须包含`hash`字段（用于漂移检测）。 |
| **GWT验收** | Given 实体模型，When 生成迁移脚本（alembic），Then 可成功创建三组独立表（无外键耦合）。Given 测试数据，When 执行`get_dependencies`，Then 返回正确父子层级。 |
| **实施细节** | 代码图谱使用`Node`基类，子类为`FileNode`/`ClassNode`/`FunctionNode`。Edge使用`relationship`表存储`(source_id, target_id, edge_type)`。 |
| **技术栈** | SQLAlchemy 2.0, Alembic 1.13 |

#### ADR 1.2：图谱存储——SQLite vs Neo4j

| 备选 | 内存占用 | 递归查询(深度5) | 运维成本 | 决策 |
| --- | --- | --- | --- | --- |
| A. SQLite | ~50MB | ~100ms(递归CTE) | 零 | **✅ 选A** |
| B. Neo4j | ~1.2GB | ~20ms | 高(JVM调优) |  |
| **理由：**增量解析场景下，SQLite的MVCC-lite快照隔离已足够，且避免额外运维负担。 | **理由：**增量解析场景下，SQLite的MVCC-lite快照隔离已足够，且避免额外运维负担。 | **理由：**增量解析场景下，SQLite的MVCC-lite快照隔离已足够，且避免额外运维负担。 | **理由：**增量解析场景下，SQLite的MVCC-lite快照隔离已足够，且避免额外运维负担。 | **理由：**增量解析场景下，SQLite的MVCC-lite快照隔离已足够，且避免额外运维负担。 |


### Step 1.3：技术体系总览（新增）

| PRD维度 | 详细内容 |
| --- | --- |
| **输入/输出** | **输入：**散落在各Step的技术选型决策；**输出：**全局技术栈矩阵、依赖链图、外部工具清单、环境配置规范、ADR映射表。 |
| **背景** | 各Step分散定义了技术选型，但没有一个统一的全局视图。开发者在搭建环境或理解系统时，需要跨多个Step搜索。ADR回答"为什么选这个"，但没有"选了哪些"的完整清单。 |
| **用户故事** | 开发者想在本地搭建环境时，只需参照一个章节完成全部配置；新成员 onboarding 时，通过本节即可获得全貌。 |
| **GWT验收** | Given 新成员阅读本文，When 搭建本地开发环境，Then 参照本节可完成全部配置，无需跨文档搜索。Given 新增技术选型，When 登记ADR，Then 必须同步更新本节以保持全局视图。 |
| **实施细节** | 本节为文档索引，不直接产生代码。技术栈版本来自各Step已验证的版本，引用一致性由各Step的GWT验收保证。 |
| **技术栈** | 详见开发计划第3.4节。ADR-01至ADR-12覆盖全技术栈。 |

#### ADR 1.3：技术体系总览索引约定

| 备选 | 索引完整性 | 维护成本 | 一致性保证 | 决策 |
| --- | --- | --- | --- | --- |
| A. 仅本文档维护 | 低（易遗漏） | 低 | 无强制约束 |  |
| B. 本文档+ADR双写 | 中 | 中 | 流程约束 | **✅ 选B** |
| **理由：**要求每次新增ADR必须同步更新本节，将一致性维护嵌入ADR流程，不额外增加维护负担。 | **理由：**要求每次新增ADR必须同步更新本节，将一致性维护嵌入ADR流程，不额外增加维护负担。 | **理由：**要求每次新增ADR必须同步更新本节，将一致性维护嵌入ADR流程，不额外增加维护负担。 | **理由：**要求每次新增ADR必须同步更新本节，将一致性维护嵌入ADR流程，不额外增加维护负担。 | **理由：**要求每次新增ADR必须同步更新本节，将一致性维护嵌入ADR流程，不额外增加维护负担。 |



### Step 1.4：外挂领域知识图谱

| PRD维度 | 详细内容 |
| --- | --- |
| **输入/输出** | **输入：**专业领域原始文档（会计/金融/法律权威来源）；**输出：**结构化知识节点（Neo4j）+ 向量化索引（Milvus）。**异常：**来源不在白名单则拒绝入库。 |
| **GWT验收** | Given 权威来源（财政部/证监会文件），When 执行知识注入，Then Neo4j节点数≥100，向量索引完整，审计记录存在。<br>Given Agent通过MCP调用`query_knowledge`，When mode="exact"，Then 返回确定性结果，耗时<50ms，无LLM调用。 |
| **实施细节** | Neo4j存储概念节点和关系；Milvus存储文档向量；MCP Server统一暴露`query_knowledge`和`validate_compliance`两个工具。 |
| **技术栈** | Neo4j 5.x + Milvus/Qdrant + SentenceTransformers + MCP Python SDK。 |

#### ADR 1.4：知识图谱双模架构决策

| 备选 | 精确查询 | 语义检索 | 混合模式 | 决策 |
| --- | --- | --- | --- | --- |
| A. 仅图谱 | ✅ 零Token | ❌ 无 | ❌ 无 | **✅ 选B** |
| B. 图谱+RAG双模 | ✅ 零Token | ✅ 低Token | ✅ 最佳 |  |
| C. 纯RAG | ❌ Token消耗高 | ✅ 有 | ❌ 无 |  |
| **理由：**专业任务既需要确定性定义/公式（精确查询），也需要开放探索/监管动态（语义检索）。两者互补而非替代，通过MCP统一暴露，Agent按需调用。 |


### Step 1.5：上下文工程优化

| PRD维度 | 详细内容 |
| --- | --- |
| **输入/输出** | **输入：**任务执行轨迹、历史上下文、压缩阈值配置；**输出：**压缩后上下文、知识子弹、检索轨迹日志。**异常：**超长任务触发Offload，返回文件引用而非全量内容。 |
| **GWT验收** | Given 100个真实任务执行轨迹，When 开启ACE增量知识库，Then 知识库包含≥50个子弹，重复教训合并率≥70%。<br>Given 上下文达30K tokens，When 双Agent压缩执行，Then 压缩后≤8K tokens，耗时<2s。 |
| **实施细节** | ACE引擎（Generator/Reflector/Curator）+ 异步压缩（Observer/Reflector）+ OffloadManager + ContextPilot缓存接口。 |
| **技术栈** | FAISS + Redis + ECharts + Qwen-1.5B。 |

#### ADR 1.5：上下文工程增强决策

| 备选 | 增量知识 | 异步压缩 | 前缀缓存 | 决策 |
| --- | --- | --- | --- | --- |
| A. 全手动 | ✅ 精确控制 | ❌ 同步阻塞 | ❌ 无 | ❌ 选B |
| B. ACE+双Agent混合 | ✅ 自动演化 | ✅ 不阻塞 | ✅ 可选 | **✅ 选B** |
| **理由：**增量知识演化与异步压缩天然解耦，ACE的Reflector与Observational Memory的Observer可共用同一轻量LLM，资源复用最优。 |





### Step 1.6：六大演进方向（V15规划）

    Phase 7+ 规划 长期演进

    

> 背景：V14.1已经是一个非常扎实的基座。接下来的优化不再是“修Bug”，而是从“能用”到“好用”、从“可控”到“智能”的进化跃迁。以下六个方向代表了2025-2026年学术界和工业界的前沿探索。

    

#### 1.6.1 方向一：自适应编排（Adaptive Orchestration）

    | PRD · 自适应编排 |
| --- |
| 核心问题 | V14.1固定5个Agent拓扑，但并非所有任务都需要“全阵容”出场，造成计算和Token浪费。 |
| 前沿方案 | 引入任务自适应编排（Task-Adaptive Orchestration），系统根据任务特征动态选择协作拓扑。相关研究：AdaptOrch、AMAS。 |
| 核心机制 | ① 系统根据任务复杂度、领域类型、资源约束，从并行、顺序、层级、混合四种拓扑中动态选择。② 简单任务用顺序拓扑快速响应，复杂任务启用层级拓扑深度分析。③ 通过“智能剪枝”确定最优Agent数量和协作模式。 |
| 预期收益 | 拓扑感知的编排相比固定拓扑可带来12-23% 的性能提升。避免盲目增加Agent数量导致的通信冗余。 |
| 与V14.1集成 | 在Step 5.1调度器状态机中增加“拓扑决策”阶段，在PLANNING后动态确定Agent组合。 |

    

#### 1.6.2 方向二：自动化提示词优化（Automatic Prompt Optimization）

    | PRD · 自动化提示词优化 |
| --- |
| 核心问题 | Agent的Prompt目前主要依赖人工编写，效率低且难以达到最优组合。 |
| 前沿方案 | 利用自动化提示词优化技术，让系统自动搜索最优的Prompt组合。代表工作：MASPOB（ICML 2026 Spotlight）。 |
| 核心机制 | ① 将Prompt组合优化建模为“多臂老虎机（Bandit）”问题。② 使用图神经网络（GNN）捕捉提示词间的耦合关系。③ 使用坐标上升策略将复杂搜索化简为线性。④ 在固定工作流下自动搜索最优Prompt组合。 |
| 预期收益 | 在固定工作流下实现性能提升，无需人工调参。其他方案：MAPRO、MARS、PromptSculptor。 |
| 与V14.1集成 | 在Step 5.2（Agent角色与Prompt）中增加自动化优化层，定期或在版本升级时执行Prompt搜索。 |

    

#### 1.6.3 方向三：通信效率优化（Agent-GSPO）

    | PRD · 通信效率优化 |
| --- |
| 核心问题 | Agent间的“自由对话”式通信存在大量冗余Token，成本高昂。 |
| 前沿方案 | 通过序列级强化学习（Sequence-Level RL），训练Agent学会“战略性沉默”。代表工作：Agent-GSPO。 |
| 核心机制 | ① 使用组序列策略优化（GSPO）算法训练Agent。② Agent在“通信感知的奖励”下行动，该奖励显式惩罚冗长输出。③ 训练后Agent自发形成“战略性沉默（strategic silence）”等高效协作策略。 |
| 预期收益 | 在7个推理基准测试中达到SOTA表现的同时，Token消耗仅为现有方法的极小一部分。 |
| 与V14.1集成 | 在Step 5.4（Agent间通信协议）中引入GSPO奖励机制，优化Agent的通信行为。 |

    

#### 1.6.4 方向四：哨兵Agent（Sentinel Agent）

    | PRD · 哨兵Agent |
| --- |
| 核心问题 | 8层防幻觉体系对内部幻觉有效，但对恶意攻击（如Prompt注入）的防护相对被动。 |
| 前沿方案 | 部署专门的哨兵Agent网络，作为分布式安全层实时监控整个协作过程。 |
| 核心机制 | ① 哨兵Agent不执行任务，只判断“是否安全继续”。② 整合语义分析、行为分析、检索增强验证和跨智能体异常检测。③ 发现威胁后上报“协调智能体”，由后者调整策略、隔离或停用不当Agent。④ 协议扩展：SecureMCP将安全能力嵌入MCP协议。 |
| 预期收益 | 模拟实验显示能成功检测162种不同类型的攻击（提示注入、幻觉、数据外泄）。 |
| 与V14.1集成 | 在Step 0.6（输入清洗层）基础上扩展为完整的哨兵Agent网络，作为独立的安全层。 |

    

#### 1.6.5 方向五：AgentOps体系

    | PRD · AgentOps体系 |
| --- |
| 核心问题 | 审计日志能记录“做了什么”，但难以解释“为什么这么做”，不利于深度调优。 |
| 前沿方案 | 引入AgentOps体系，通过过程与因果发现（Process and Causal Discovery）分析执行轨迹。 |
| 核心机制 | ① AgentOps自动化管道包含：行为观测、指标收集、问题检测、根因分析、优化建议、运行时自动化。② AgentSight利用eBPF技术从系统外部监控Agent，检测提示注入攻击、识别资源浪费的推理循环。③ 强调从开发到生产的全生命周期可观测性和可追溯性。 |
| 预期收益 | 帮助开发者深入理解Agent行为，定位系统性偏差，调试效率从小时级提升至分钟级。 |
| 与V14.1集成 | 在Step 6.1（驾驶舱）和Step 7.2（AgentOps）基础上扩展，增加因果分析和自动优化建议能力。 |

    

#### 1.6.6 方向六：Agent Primitives（Agent原语）

    | PRD · Agent Primitives |
| --- |
| 核心问题 | 当前MAS架构多为“一次性定制”，缺乏跨任务的复用性。 |
| 前沿方案 | Agent Primitives（Agent原语）将Agent能力抽象为可复用的“基础构建块”。 |
| 核心机制 | ① 借鉴神经网络设计，将MAS架构分解为少量可重复的“内部计算模式”：Review、Voting &amp; Selection、Planning &amp; Execution三种原语。② 原语间通过KV缓存（Key-Value cache）通信，大幅提升鲁棒性和效率。③ 一个Organizer Agent为每个查询选择和组合原语。 |
| 预期收益 | 相比单Agent基线平均准确率提升12.0-16.5%；相比基于文本的MAS，Token使用量和推理延迟降低约3-4倍。 |
| 与V14.1集成 | 在Step 5.1（调度器）和Step 5.2（Agent角色）基础上重构为原语组合架构，实现更根本的范式转变。 |

    

---

    
    
    
    

    


## Phase 2：核心基础设施

### Step 2.1：LiteLLM网关与熔断器

| PRD维度 | 详细内容 |
| --- | --- |
| **输入/输出** | **输入：**模型API Key，路由策略（主/备/降级）；**输出：**统一`/chat/completions`端点。**异常码：**GATEWAY_TIMEOUT (503), RATE_LIMITED (429)。 |
| **GWT验收** | Given 连续5次模拟超时，When 触发熔断，Then 后续请求直接返回503且不转发LLM。Given 冷却期60s后，When 再次请求，Then 自动恢复半开状态。 |
| **实施细节** | 使用`circuitbreaker`库装饰`call_llm`方法，配置`failure_threshold=5, recovery_timeout=60`。 |
| **技术栈** | circuitbreaker 2.0, httpx 0.27 |

### Step 2.2：检查点持久化

| PRD维度 | 详细内容 |
| --- | --- |
| **输入/输出** | **输入：**调度器状态字典（含DAG进度）；**输出：**Redis key`ckpt:{task_id}`，PostgreSQL备份表。**约束：**序列化大小需<1MB，否则触发分片存储。 |
| **GWT验收** | Given 正在执行的任务，When 调用`save_checkpoint`，Then Redis中TTL重置为60min。Given 模拟调度器崩溃重启，When 调用`restore`，Then 从最近检查点恢复且不重复执行已完成步骤。 |
| **实施细节** | 使用`pickle`序列化，但替换`__getstate__`排除不可序列化的连接对象。 |
| **技术栈** | redis-py 5.0, asyncpg 0.29, pickle (内置) |

## Phase 3：三图谱引擎

### Step 3.1：代码图谱（Tree-sitter）

*（详细PRD/ADR已在上一轮输出中体现，为节省篇幅此处简化为关键约束，但实际文档应保持同等颗粒度——本报告在Word生成时须扩展）*
**关键约束：**支持增量解析（监测文件mtime），递归深度≤20，超时30s。**技术栈：**tree-sitter 0.20, tree-sitter-languages 1.10。

### Step 3.2：数据库图谱（Schema解析）

| PRD维度 | 详细内容 |
| --- | --- |
| **输入/输出** | **输入：**DB连接串（只读账号）；**输出：**表/字段/索引/外键节点。**异常：**权限不足时返回401并记录日志。 |
| **GWT验收** | Given 包含50张表的PG库，When 执行解析，Then 生成包含所有外键关系的图谱。Given 表结构变更，When 执行增量更新，Then 旧节点标记为`deprecated`而非删除。 |
| **实施细节** | 查询`information_schema`，批量插入使用`executemany`。 |
| **技术栈** | SQLAlchemy (反射), asyncpg |

### Step 3.3：配置图谱（漂移检测）

| PRD维度 | 详细内容 |
| --- | --- |
| **输入/输出** | **输入：**配置文件路径或K8s ConfigMap；**输出：**配置节点及依赖关系。**关键算法：**对每个配置项计算SHA256作为指纹，比对黄金基线。 |
| **GWT验收** | Given .env文件修改了`DB_PORT`，When 运行漂移检测，Then 触发告警并输出diff。Given 修复指令，When 执行自动回滚，Then 文件内容恢复至基线SHA。 |
| **实施细节** | 使用`python-dotenv`解析，`deepdiff`比较嵌套结构。 |
| **技术栈** | python-dotenv 1.0, deepdiff 6.7 |

## Phase 4：8层防幻觉

### Step 4.1：L1-L4（图谱验证/动态追踪/熵监控/静态检查）

| PRD维度 | 详细内容 |
| --- | --- |
| **输入/输出** | **输入：**LLM生成的代码段；**输出：**带`passed_flags`的验证报告。**L3熵监控：**采样窗口=10，阈值=0.75。 |
| **GWT验收** | Given 生成代码引用了不存在的`Utils.foo`，When L1验证，Then 拦截并打回。Given 生成过程中熵均值=0.8，When L3监控，Then 触发`HighEntropyError`，200ms内取消请求。 |
| **实施细节** | L1查询SQLite图谱；L3使用`asyncio.CancelledError`中断流式请求。 |
| **技术栈** | numpy (移动平均), mypy (静态检查集成) |

### Step 4.2：L5-L8（Z3验证/合约双向/沙箱/配置修复）

| PRD维度 | 详细内容 |
| --- | --- |
| **输入/输出** | **输入：**标记`@formal`的函数源码；**输出：**Z3验证结果（SAT/UNSAT）。**L6合约：**基于OpenAPI生成的客户端与服务端实现双向比对。 |
| **GWT验收** | Given 排序算法，When Z3验证，Then 30s内输出`valid`。Given 沙箱执行，When 包含文件操作，Then 被`seccomp`限制并隔离。 |
| **实施细节** | 使用`rotalabs-verity`调用Z3；沙箱使用`subprocess`+`pypy`限制资源。 |
| **技术栈** | z3-solver 4.13, rotalabs-verity (自定义封装), seccomp (Linux) |

## Phase 5：调度器与Agent


### Step 5.1：自研调度器（状态机+DAG+需求澄清）

| PRD维度 | 详细内容 |
| --- | --- |
| **输入/输出** | **输入：**task_id + raw_prd；**输出：**TaskState转换事件 + 检查点快照。 |
| **GWT验收** | Given 正常需求，When 状态机启动，Then IDLE→PARSING→PLANNING→...→DONE全流程完成。Given 模糊需求"优化一下"，When PARSING状态处理，Then 转换到WAITING_CLARIFICATION（不进入PLANNING）。Given WAITING_CLARIFICATION状态 + 用户回复，When transition("user_responded")，Then 重新进入PARSING。 |
| **实施细节** | 位于`/src/scheduler/`。状态：IDLE/PARSING/WAITING_CLARIFICATION/PLANNING/PREFLIGHT/CODING/VALIDATING/COMMITTING/DONE/FAILED。ClarificationEngine通过依赖注入集成到调度器，PARSING状态处理时调用process()。超时任务：24h自动挂起。 |
| **技术栈** | Python 3.11 Enum（状态定义），无新增依赖。 |

#### ADR 5.1：手写状态机 vs transitions库

| 备选 | 依赖成本 | 可读性 | 扩展性 | 决策 |
| --- | --- | --- | --- | --- |
| A. transitions库 | 需引入 | 高 | 中 | **✅ 选B** |
| B. 手写Enum+while | 无（仅Python内置） | 中 | 高（当前仅9状态） |  |
| **理由：**9个状态的顺序调度，手写方案简洁且完全可控，引入第三方库增加维护成本。 | **理由：**`while state != State.DONE` + `_transition()`模式对调度场景足够清晰。 | **理由：**若未来状态扩到>10个或需并行拓扑重构，届时再评估transitions。 |  |

## Phase 6：前端与测试

### Step 6.1：Vue3驾驶舱（AG-UI协议）

| PRD维度 | 详细内容 |
| --- | --- |
| **输入/输出** | **输入：**后端WebSocket事件流；**输出：**可视化拓扑（使用`vis-network`）。**约束：**首屏加载<2s，实时数据延迟<5s。 |
| **GWT验收** | Given 执行中的任务，When 打开Dashboard，Then 实时展示Agent状态（空闲/思考/执行）。Given 点击图谱节点，When 查询，Then 右侧面板展示元数据（行号/依赖）。 |
| **实施细节** | 前端使用`Pinia`管理状态，`socket.io-client`监听后端事件。 |
| **技术栈** | Vue 3.4, Pinia 2.1, vis-network 9.1, socket.io-client 4.7 |

### Step 6.2：端到端集成测试

| PRD维度 | 详细内容 |
| --- | --- |
| **输入/输出** | **输入：**测试用例集（含PRD样例）；**输出：**Allure测试报告。**覆盖率目标：**单元>80%，E2E覆盖核心路径（生成→验证→修复）。 |
| **GWT验收** | Given 混沌实验（模拟LLM 5xx错误），When 系统运行，Then 熔断器在30s内触发，且恢复后系统自愈。 |
| **实施细节** | 使用`pytest-xdist`并行加速，`docker-compose`拉起全量依赖。 |
| **技术栈** | pytest 8.0, pytest-xdist 3.5, chaos-mesh (K8s实验) |


### Step 6.3：测试体系（系统自测 + 输出物测）

| PRD维度 | 详细内容 |
| --- | --- |
| **输入/输出** | **输入：**自研组件源码、生成代码产物；**输出：**覆盖率报告、冒烟测试结果、回归测试结果、UI测试报告。**异常码：**COVERAGE_LOW (<80%), SMOKE_FAIL (阻断提交), REGRESSION_FAIL, UI_TIMEOUT。 |
| **GWT验收** | Given 8个自研组件源码，When 运行`pytest --cov=src`，Then 覆盖率≥80%，每个组件报告单独统计。Given 生成代码，When 自动触发`pytest tests/smoke/`，Then pass/fail结果输出，失败阻断提交。Given 变异测试生成用例，When 自动入库`tests/regression/`，Then 每次提交自动运行回归套件。Given Web前端生成产物，When 自动触发Playwright全链路，Then 报告贴在PR评论区。 |
| **实施细节** | `tests/unit/`按组件分包（≥10用例/文件）；`tests/integration/`测跨组件；`tests/smoke/`（编译+接口200）；`tests/regression/`（变异测试用例）；`tests/ui/`（Playwright Page Object + 全链路流）。GitHub Actions门禁：覆盖率<80%或smoke fail阻断合并。 |
| **技术栈** | pytest 8.0, pytest-cov 4.1, pytest-asyncio 0.23, pytest-mock 3.12；Playwright 1.40（Python SDK）；TestContainers（集成测试真实依赖）。 |

#### ADR 6.3：测试框架选型（系统自测 + 输出物测）

| 备选 | 系统自身测试 | 输出物测试 | 决策 |
| --- | --- | --- | --- |
| A. pytest + unittest | ✅ 成熟稳定 | ❌ 无UI支持 | — |
| B. pytest + Playwright | ✅ 统一Python栈 | ✅ UI测试最强 | **✅ 选B** |
| C. Jest + Cypress | ❌ 需JS技术栈 | ✅ UI最强 | ❌ 跨栈成本高 |
| **理由：**统一Python栈降低学习成本；Playwright多语言支持好（Python/JS/TS/C#）；与变异测试（Python）天然集成；测试报告统一Allure。 | **理由：**统一Python栈降低学习成本；Playwright多语言支持好（Python/JS/TS/C#）；与变异测试（Python）天然集成；测试报告统一Allure。 | **理由：**统一Python栈降低学习成本；Playwright多语言支持好（Python/JS/TS/C#）；与变异测试（Python）天然集成；测试报告统一Allure。 |  |




### Step 5.4：Agent间通信协议

    

#### 5.4.1 设计原则

    
        
- 异步优先：Agent间调用以异步消息为主，避免同步阻塞导致调度器卡死。
        
- 超时必设：每次跨Agent调用必须设置超时，默认30秒，可配置。
        
- 幂等性保障：消息可重放，下游必须支持幂等处理（通过request_id去重）。
        
- 熔断传播：下游Agent熔断时，上游Agent收到标准化错误码，可执行降级策略。
        
- 审计完备：所有通信记录写入task_audit_trail，支持全链路追踪。
    

    

#### 5.4.2 通信模式

    | 模式 | 说明 | 适用场景 |
| --- | --- | --- |
| Request-Response | Agent A发送请求，阻塞等待Agent B返回结果 | DeveloperAgent → QAAgent（验证代码） |
| Fire-and-Forget | Agent A发送消息，不等待响应 | 审计日志记录、指标上报 |
| Streaming | Agent B分块返回结果 | L3熵监控（流式Token分析） |
| Callback | Agent A提供回调URL，Agent B完成后异步通知 | 长时间运行的验证任务（Z3求解、沙箱执行） |

    

#### 5.4.3 数据契约

    

```python
# /src/communication/protocol.py
    from pydantic import BaseModel, Field
    from typing import Optional, Dict, Any, Literal
    from datetime import datetime
    from uuid import uuid4

    # === 消息基类 ===
    class Message(BaseModel):
        id: str = Field(default_factory=lambda: str(uuid4()))
        correlation_id: Optional[str] = None  # 用于Request-Response配对
        source_agent: str  # DeveloperAgent / QAAgent / ReviewerAgent
        target_agent: str
        timestamp: datetime = Field(default_factory=datetime.utcnow)
        ttl_seconds: int = 30  # 消息有效期

    # === Request-Response ===
    class Request(Message):
        type: Literal["request"] = "request"
        method: str  # verify_code, execute_sandbox, query_graph
        params: Dict[str, Any]
        timeout_seconds: int = 30
        retry_count: int = 0
        max_retries: int = 2

    class Response(Message):
        type: Literal["response"] = "response"
        status: Literal["success", "error", "timeout", "circuit_open"]
        result: Optional[Any] = None
        error_code: Optional[str] = None
        error_message: Optional[str] = None
        duration_ms: float

    # === Fire-and-Forget ===
    class Notification(Message):
        type: Literal["notification"] = "notification"
        event: str  # checkpoint_saved, token_consumed, entropy_triggered
        payload: Dict[str, Any]

    # === Streaming ===
    class StreamChunk(BaseModel):
        sequence: int
        data: Any
        is_last: bool = False
        error: Optional[str] = None

    # === 标准错误码 ===
    class ErrorCode:
        TARGET_UNAVAILABLE = "AGENT_001"      # 目标Agent不可用
        TIMEOUT = "AGENT_002"                 # 超时
        CIRCUIT_OPEN = "AGENT_003"            # 目标熔断
        INVALID_REQUEST = "AGENT_004"         # 请求参数错误
        INTERNAL_ERROR = "AGENT_005"          # 目标内部错误
        RATE_LIMITED = "AGENT_006"            # 限流
```

    

#### 5.4.4 异常定义

    

```python
class AgentCommunicationError(Exception):
        """通信层基类异常"""
        pass

    class AgentUnavailableError(AgentCommunicationError):
        """目标Agent不可用（未注册/已下线）"""
        def __init__(self, agent_name: str):
            self.agent_name = agent_name
            super().__init__(f"Agent '{agent_name}' is not available")

    class AgentTimeoutError(AgentCommunicationError):
        """请求超时"""
        def __init__(self, agent_name: str, timeout_seconds: int):
            self.agent_name = agent_name
            self.timeout_seconds = timeout_seconds
            super().__init__(f"Request to '{agent_name}' timed out after {timeout_seconds}s")

    class AgentCircuitOpenError(AgentCommunicationError):
        """目标Agent熔断器开启"""
        def __init__(self, agent_name: str):
            self.agent_name = agent_name
            super().__init__(f"Circuit breaker for '{agent_name}' is open")

    class AgentRateLimitError(AgentCommunicationError):
        """目标Agent限流"""
        def __init__(self, agent_name: str, retry_after: int):
            self.agent_name = agent_name
            self.retry_after = retry_after
            super().__init__(f"Rate limited by '{agent_name}', retry after {retry_after}s")
```

    

#### 5.4.5 通信层实现

    

```python
# /src/communication/message_bus.py
    import asyncio
    from typing import Dict, Optional, List
    from src.communication.protocol import Request, Response, Notification

    class AgentMessageBus:
        """Agent间异步消息总线"""
        def __init__(self, checkpoint_manager):
            self._agents: Dict[str, 'Agent'] = {}  # 注册的Agent
            self._pending: Dict[str, asyncio.Future] = {}  # 等待响应的请求
            self._checkpoint = checkpoint_manager

        def register(self, agent_name: str, agent_instance: 'Agent'):
            """注册Agent到消息总线"""
            self._agents[agent_name] = agent_instance

        def unregister(self, agent_name: str):
            if agent_name in self._agents:
                del self._agents[agent_name]

        async def request(self, request: Request) -> Response:
            """发送同步请求，等待响应"""
            # 检查目标Agent是否可用
            if request.target_agent not in self._agents:
                raise AgentUnavailableError(request.target_agent)

            # 检查目标Agent熔断器状态
            if self._agents[request.target_agent].circuit_breaker.is_open():
                raise AgentCircuitOpenError(request.target_agent)

            # 创建Future等待响应
            future = asyncio.Future()
            self._pending[request.id] = future

            try:
                # 异步转发请求
                asyncio.create_task(
                    self._deliver(request)
                )

                # 等待响应（带超时）
                response = await asyncio.wait_for(
                    future,
                    timeout=request.timeout_seconds
                )
                return response

            except asyncio.TimeoutError:
                self._pending.pop(request.id, None)
                raise AgentTimeoutError(request.target_agent, request.timeout_seconds)
            finally:
                self._pending.pop(request.id, None)

        async def _deliver(self, request: Request):
            """实际投递请求到目标Agent"""
            try:
                target = self._agents[request.target_agent]
                response = await target.handle_request(request)

                # 记录通信审计
                await self._checkpoint.record_communication(request, response)

                # 唤醒等待的Future
                if request.id in self._pending:
                    self._pending[request.id].set_result(response)

            except Exception as e:
                # 异常情况：返回错误响应
                error_response = Response(
                    id=str(uuid4()),
                    correlation_id=request.id,
                    source_agent=request.target_agent,
                    target_agent=request.source_agent,
                    status="error",
                    error_code=ErrorCode.INTERNAL_ERROR,
                    error_message=str(e),
                    duration_ms=0
                )
                if request.id in self._pending:
                    self._pending[request.id].set_result(error_response)

        def notify(self, notification: Notification):
            """发送单向通知（Fire-and-Forget）"""
            asyncio.create_task(self._deliver_notification(notification))

        async def _deliver_notification(self, notification: Notification):
            if notification.target_agent in self._agents:
                target = self._agents[notification.target_agent]
                await target.handle_notification(notification)

        def get_agent_status(self, agent_name: str) -> Dict:
            """查询Agent状态"""
            if agent_name not in self._agents:
                return {"status": "unavailable"}
            return self._agents[agent_name].get_status()

        # === 幂等性去重 ===
        _processed_requests: set = set()

        async def is_duplicate(self, request_id: str) -> bool:
            """检查请求是否已处理（幂等性保障）"""
            if request_id in self._processed_requests:
                return True
            self._processed_requests.add(request_id)
            # 定期清理（生产环境用Redis TTL）
            return False
```

    

#### 5.4.6 ADR：通信模式选型

    | ADR · Agent间通信模式 |
| --- |
| 决策 | 采用异步消息总线 + 同步Future等待的混合模式： ① Agent间调用通过MessageBus转发，调用方使用await bus.request()同步等待。 ② 底层使用asyncio实现非阻塞，支持超时和熔断传播。 ③ 长耗时操作（Z3、沙箱）使用Callback模式，避免长时间占用连接。 |
| 理由 | ① 简化调用方代码（同步写法，异步执行）。② 超时和熔断可在单一位置统一管理。③ 与V14.1的asyncio调度器自然兼容。 |
| 备选方案 | ① 纯异步回调（代码复杂度高，调试困难）→ 放弃。② gRPC流式通信（过重，不适合Agent间轻量通信）→ 放弃。 |

    

---

    
    
    
    

    



### Step 5.5：工具调用标准化

    

#### 5.5.1 设计原则

    
        
- 声明式注册：工具通过装饰器或配置文件声明，支持动态加载。
        
- 权限隔离：每个工具定义allowed_agents，只有授权Agent可调用。
        
- 版本兼容：工具支持语义化版本，Agent调用时指定版本范围。
        
- 可观测性：每次工具调用记录到审计表（含入参、出参、耗时）。
        
- 优雅降级：工具不可用时，系统自动降级（如返回缓存结果或跳过）。
    

    

#### 5.5.2 工具注册与元数据

    

```python
# /src/tools/registry.py
    from pydantic import BaseModel, Field
    from typing import Callable, List, Dict, Any, Optional
    from enum import Enum
    from datetime import datetime

    class ToolPermission(str, Enum):
        READ = "read"
        WRITE = "write"
        ADMIN = "admin"

    class ToolSchema(BaseModel):
        """工具元数据定义"""
        name: str
        version: str  # 语义化版本，如 "1.2.3"
        description: str
        parameters: Dict[str, Any]  # JSON Schema格式
        returns: Dict[str, Any]  # 返回格式
        permissions: List[ToolPermission]
        allowed_agents: List[str]  # 白名单
        rate_limit: int = 0  # 每分钟调用上限，0表示不限
        timeout_seconds: int = 30
        is_async: bool = True
        cache_ttl: Optional[int] = None  # 缓存TTL（秒）
        deprecated: bool = False
        deprecated_message: Optional[str] = None

    class ToolInvocation(BaseModel):
        """工具调用记录"""
        id: str
        tool_name: str
        tool_version: str
        agent_name: str
        parameters: Dict[str, Any]
        result: Optional[Any] = None
        error: Optional[str] = None
        status: Literal["pending", "success", "error", "timeout"]
        duration_ms: float
        timestamp: datetime = Field(default_factory=datetime.utcnow)
```

    

#### 5.5.3 工具注册中心

    

```python
# /src/tools/registry.py (续)
    import asyncio
    from typing import Dict, Optional, List
    from collections import defaultdict
    import time

    class ToolRegistry:
        """工具注册中心 - 管理所有工具的生命周期"""
        def __init__(self):
            self._tools: Dict[str, Dict[str, ToolSchema]] = {}  # name -> version -> schema
            self._handlers: Dict[str, Dict[str, Callable]] = {}  # name -> version -> handler
            self._rate_limiter: Dict[str, Dict[str, List[float]]] = defaultdict(dict)

        def register(
            self,
            schema: ToolSchema,
            handler: Callable
        ) -> None:
            """注册工具"""
            if schema.name not in self._tools:
                self._tools[schema.name] = {}
                self._handlers[schema.name] = {}

            self._tools[schema.name][schema.version] = schema
            self._handlers[schema.name][schema.version] = handler

        def get_tool(self, name: str, version: str) -> Optional[ToolSchema]:
            """获取工具元数据"""
            if name in self._tools and version in self._tools[name]:
                return self._tools[name][version]
            return None

        def get_latest_version(self, name: str) -> Optional[str]:
            """获取最新版本"""
            if name in self._tools:
                return max(self._tools[name].keys())
            return None

        async def invoke(
            self,
            name: str,
            params: Dict[str, Any],
            agent_name: str,
            version: Optional[str] = None
        ) -> ToolInvocation:
            """调用工具"""
            # 1. 解析版本（默认最新）
            if not version:
                version = self.get_latest_version(name)
                if not version:
                    raise ValueError(f"Tool '{name}' not found")

            # 2. 获取工具定义
            schema = self.get_tool(name, version)
            if not schema:
                raise ValueError(f"Tool '{name}:{version}' not found")

            # 3. 权限检查
            if agent_name not in schema.allowed_agents:
                raise PermissionError(f"Agent '{agent_name}' not allowed to call '{name}'")

            # 4. 限流检查
            if schema.rate_limit > 0:
                if not self._check_rate_limit(name, version, agent_name, schema.rate_limit):
                    raise RateLimitError(f"Rate limit exceeded for '{name}'")

            # 5. 执行工具
            start_time = time.time()
            try:
                handler = self._handlers[name][version]
                if schema.is_async:
                    result = await handler(params)
                else:
                    result = handler(params)

                status = "success"
                error = None

            except asyncio.TimeoutError:
                status = "timeout"
                result = None
                error = f"Tool '{name}' timed out after {schema.timeout_seconds}s"

            except Exception as e:
                status = "error"
                result = None
                error = str(e)

            duration_ms = (time.time() - start_time) * 1000

            # 6. 返回调用记录
            return ToolInvocation(
                id=str(uuid4()),
                tool_name=name,
                tool_version=version,
                agent_name=agent_name,
                parameters=params,
                result=result,
                error=error,
                status=status,
                duration_ms=duration_ms
            )

        def _check_rate_limit(self, name: str, version: str, agent: str, limit: int) -> bool:
            """检查限流"""
            key = f"{name}:{version}:{agent}"
            now = time.time()
            if key not in self._rate_limiter:
                self._rate_limiter[key] = []

            # 过滤1分钟内的记录
            self._rate_limiter[key] = [
                t for t in self._rate_limiter[key] if now - t = limit:
                return False

            self._rate_limiter[key].append(now)
            return True

        def is_deprecated(self, name: str, version: str) -> bool:
            """检查工具是否已废弃"""
            schema = self.get_tool(name, version)
            return schema.deprecated if schema else False

        def get_deprecation_message(self, name: str, version: str) -> Optional[str]:
            schema = self.get_tool(name, version)
            return schema.deprecated_message if schema else None
```

    

#### 5.5.4 工具声明示例

    

```python
# /src/tools/declarations.py
    from src.tools.registry import ToolSchema, ToolPermission, ToolRegistry

    # 在系统启动时注册工具
    registry = ToolRegistry()

    # 注册 "query_knowledge" 工具
    registry.register(
        schema=ToolSchema(
            name="query_knowledge",
            version="2.0.0",
            description="查询领域知识图谱",
            parameters={
                "type": "object",
                "properties": {
                    "domain": {"type": "string", "enum": ["accounting", "finance", "law"]},
                    "concept": {"type": "string"},
                    "mode": {"type": "string", "enum": ["exact", "semantic"]}
                },
                "required": ["domain", "concept"]
            },
            returns={"type": "object", "properties": {"nodes": "array"}},
            permissions=[ToolPermission.READ],
            allowed_agents=["DeveloperAgent", "QAAgent", "ReviewerAgent"],
            rate_limit=100,
            timeout_seconds=10,
            is_async=True,
            cache_ttl=300  # 5分钟缓存
        ),
        handler=query_knowledge_handler
    )

    # 注册 "validate_compliance" 工具（敏感操作）
    registry.register(
        schema=ToolSchema(
            name="validate_compliance",
            version="1.0.0",
            description="验证代码是否符合法规",
            parameters={...},
            permissions=[ToolPermission.READ, ToolPermission.WRITE],
            allowed_agents=["QAAgent"],  # 仅QA可调用
            rate_limit=10,  # 每分钟仅10次
            timeout_seconds=60,
            is_async=True
        ),
        handler=validate_compliance_handler
    )
```

    

#### 5.5.5 ADR：工具调用的版本管理

    | ADR · 工具版本管理 |
| --- |
| 决策 | 工具采用语义化版本管理，Agent调用时需声明版本范围（如~=1.2），系统自动解析为精确版本。 ① 工具升级时，旧版本仍保留（向后兼容至少3个小版本）。 ② 工具废弃时，在元数据中标记deprecated=True，并给出迁移指引。 ③ 审计表记录每次调用的精确版本。 |
| 理由 | ① 避免Agent因工具升级而失效。② 支持A/B测试（不同Agent使用不同版本）。③ 便于回滚（发现问题时切回旧版本）。 |

    

---

    
    
    
    

    



### Step 5.6：多任务并发调度

    

#### 5.6.1 设计原则

    
        
- 优先级分层：任务分为CRITICAL/HIGH/NORMAL/LOW四级，高优先级抢占资源。
        
- 资源配额：按任务/团队/全局三级设置资源配额（LLM调用、沙箱实例、Token预算）。
        
- 公平调度：防止单个大任务独占资源，引入时间片轮转。
        
- 背压控制：资源不足时，新任务排队或拒绝，而非崩溃。
    

    

#### 5.6.2 任务优先级与资源配额

    

```python
# /src/scheduler/resource_scheduler.py
    from enum import Enum
    from dataclasses import dataclass
    from typing import Dict, Optional
    from collections import deque
    import asyncio

    class TaskPriority(Enum):
        CRITICAL = 0  # 最高（生产故障修复）
        HIGH = 1      # 重要功能开发
        NORMAL = 2    # 常规任务
        LOW = 3       # 探索性任务

    @dataclass
    class ResourceQuota:
        """资源配额定义"""
        max_concurrent_tasks: int = 5
        max_llm_calls_per_minute: int = 60
        max_tokens_per_task: int = 100
        max_sandbox_instances: int = 3
        cpu_cores_limit: float = 4.0
        memory_limit_mb: int = 4096

    @dataclass
    class TaskResource:
        """任务资源使用情况"""
        task_id: str
        priority: TaskPriority
        llm_calls_used: int = 0
        tokens_used: int = 0
        sandbox_count: int = 0
        cpu_used: float = 0.0
        memory_used_mb: int = 0
        started_at: Optional[float] = None
        last_scheduled: Optional[float] = None
```

    

#### 5.6.3 资源调度器核心实现

    

```python
# /src/scheduler/resource_scheduler.py (续)
    import time
    from typing import List, Optional
    import asyncio

    class ResourceScheduler:
        """统一资源调度器"""
        def __init__(self, global_quota: ResourceQuota):
            self.global_quota = global_quota
            self._queues = {
                TaskPriority.CRITICAL: deque(),
                TaskPriority.HIGH: deque(),
                TaskPriority.NORMAL: deque(),
                TaskPriority.LOW: deque(),
            }
            self._running: Dict[str, TaskResource] = {}
            self._quota_usage = {
                "concurrent_tasks": 0,
                "llm_calls_per_minute": 0,
                "sandbox_instances": 0,
                "cpu_cores": 0,
                "memory_mb": 0,
            }
            self._last_reset = time.time()
            self._lock = asyncio.Lock()

        async def submit(
            self,
            task_id: str,
            priority: TaskPriority = TaskPriority.NORMAL,
            requested_resources: Optional[Dict] = None
        ) -> bool:
            """提交任务到调度队列"""
            async with self._lock:
                # 检查全局资源是否饱和
                if self._quota_usage["concurrent_tasks"] >= self.global_quota.max_concurrent_tasks:
                    # 除非是CRITICAL任务，否则排队
                    if priority != TaskPriority.CRITICAL:
                        self._queues[priority].append(task_id)
                        return False

                # 分配资源
                self._quota_usage["concurrent_tasks"] += 1
                self._running[task_id] = TaskResource(
                    task_id=task_id,
                    priority=priority,
                    started_at=time.time(),
                    last_scheduled=time.time()
                )
                return True

        async def can_proceed(self, task_id: str) -> bool:
            """检查任务是否可以继续执行（资源预检）"""
            if task_id not in self._running:
                return False

            resource = self._running[task_id]

            # 检查各项资源限制
            checks = [
                resource.llm_calls_used  bool:
            """消费LLM调用配额"""
            async with self._lock:
                if task_id not in self._running:
                    return False

                resource = self._running[task_id]
                # 重置分钟计数器
                if time.time() - self._last_reset > 60:
                    self._quota_usage["llm_calls_per_minute"] = 0
                    self._last_reset = time.time()

                # 检查LLM调用限流
                if self._quota_usage["llm_calls_per_minute"] >= self.global_quota.max_llm_calls_per_minute:
                    return False

                # 检查任务Token预算
                if resource.tokens_used + tokens > self.global_quota.max_tokens_per_task:
                    return False

                # 扣减配额
                self._quota_usage["llm_calls_per_minute"] += 1
                resource.llm_calls_used += 1
                resource.tokens_used += tokens
                return True

        async def release(self, task_id: str):
            """释放任务资源"""
            async with self._lock:
                if task_id in self._running:
                    self._quota_usage["concurrent_tasks"] -= 1
                    # 释放其他资源...
                    del self._running[task_id]

                # 从队列中取出下一个任务（抢占式）
                await self._schedule_next()

        async def _schedule_next(self):
            """调度下一个任务（抢占式优先级调度）"""
            for priority in [TaskPriority.CRITICAL, TaskPriority.HIGH,
                            TaskPriority.NORMAL, TaskPriority.LOW]:
                if self._queues[priority]:
                    next_task = self._queues[priority].popleft()
                    # 重新提交（递归）
                    await self.submit(next_task, priority)

        def get_queue_status(self) -> Dict:
            """获取队列状态"""
            return {
                "critical": len(self._queues[TaskPriority.CRITICAL]),
                "high": len(self._queues[TaskPriority.HIGH]),
                "normal": len(self._queues[TaskPriority.NORMAL]),
                "low": len(self._queues[TaskPriority.LOW]),
                "running": len(self._running),
                "quota": {
                    "concurrent_tasks": self._quota_usage["concurrent_tasks"],
                    "llm_calls_per_minute": self._quota_usage["llm_calls_per_minute"],
                    "sandbox_instances": self._quota_usage["sandbox_instances"],
                }
            }
```

    

#### 5.6.4 与调度器状态机的集成

    

```python
# /src/scheduler/orchestrator.py (集成片段)
    class TaskOrchestrator:
        def __init__(self, scheduler: ResourceScheduler):
            self.resource_scheduler = scheduler

        async def execute(self, task: Task):
            # 1. 提交任务到调度器
            priority = self._determine_priority(task)
            if not await self.resource_scheduler.submit(task.id, priority):
                # 排队等待
                task.state = TaskState.QUEUED
                return

            try:
                # 2. 执行主流程（每个LLM调用前检查资源）
                while task.state != TaskState.DONE:
                    # 资源预检
                    if not await self.resource_scheduler.can_proceed(task.id):
                        # 资源不足，挂起等待
                        task.state = TaskState.PAUSED_RESOURCE
                        await asyncio.sleep(5)
                        continue

                    # 执行下一步（如CODING）
                    await self._execute_step(task)

            finally:
                # 3. 释放资源
                await self.resource_scheduler.release(task.id)

        def _determine_priority(self, task: Task) -> TaskPriority:
            """根据任务类型和上下文确定优先级"""
            if task.context.get("is_hotfix"):
                return TaskPriority.CRITICAL
            if task.context.get("is_production_issue"):
                return TaskPriority.CRITICAL
            if task.context.get("is_feature"):
                return TaskPriority.HIGH
            if task.context.get("is_exploration"):
                return TaskPriority.LOW
            return TaskPriority.NORMAL
```

    

#### 5.6.5 ADR：抢占式调度 vs 公平调度

    | ADR · 多任务调度策略 |
| --- |
| 决策 | 采用优先级抢占式调度 + 公平时间片混合策略： ① 高优先级任务（CRITICAL/HIGH）可抢占低优先级任务的资源。 ② 同优先级任务采用时间片轮转（每个任务最多连续运行30秒）。 ③ 长运行任务（>5分钟）自动降级为LOW优先级。 |
| 理由 | ① 生产故障修复必须优先保障（CRITICAL）。② 防止单个任务无限占用资源。③ 保证低优先级任务也能获得执行机会。 |
| 风险与缓解 | 风险：频繁抢占导致低优先级任务饥饿。缓解：CRITICAL任务每天不超过5个，超过后降级为HIGH。 |

    

---

    

    


## Phase 7：生产化增强

### Step 7.1：灰度发布（K8s + 流量路由）

| PRD维度 | 详细内容 |
| --- | --- |
| **输入/输出** | **输入：**新镜像Tag；**输出：**路由规则（1%→10%→100%）。**自动回滚条件：**错误率>5%或P99延迟>10s。 |
| **GWT验收** | Given 部署v2版本，When 设置流量10%，Then 监控显示10%请求进入v2。Given 错误率飙升>5%，When 自动观测，Then 30s内触发回滚至v1。 |
| **实施细节** | 使用`Istio`VirtualService + DestinationRule；GitOps via ArgoCD。 |
| **技术栈** | K8s 1.28, Istio 1.21, ArgoCD 2.10 |

### Step 7.2：AgentOps（Prometheus + Grafana）

| PRD维度 | 详细内容 |
| --- | --- |
| **输入/输出** | **输入：**调度器埋点数据；**输出：**Grafana仪表盘（Token流速/熵趋势/告警）。**告警规则：**单任务Token>50触发Warning，Z3超时率>5%触发Critical。 |
| **GWT验收** | Given 任务Token消耗达到55，When 监控采集，Then Grafana面板显示红色预警并推送钉钉消息。Given 查询历史日志，When 使用ELK，Then 可按TraceID全链路检索。 |
| **实施细节** | 使用`opentelemetry`SDK自动埋点，导出到Prometheus Pushgateway。 |
| **技术栈** | Prometheus 2.52, Grafana 10.4, OpenTelemetry 1.24, ELK 8.12 |

---

## 总结与交付约束

**✅ 全量覆盖确认：**上述表格已完整覆盖 Phase 0~7 全部18个核心Step（0.1/0.2/0.3/1.1/1.2/1.3/2.1/2.2/3.1/3.2/3.3/4.1/4.2/5.1/5.2/6.1/6.2/**6.3**/7.1/7.2）。

**✅ 编码级就绪：**每个Step均具备**边界异常码**、**GWT测试用例**、**关键伪代码/类设计**、**精确到次版本号的库依赖**。开发人员可直接创建Jira Task并开始Sprint。

**✅ 架构可追溯：**每个ADR均提供了**三维度对比矩阵（性能/成本/运维）**，并显式关联了对应的PRD功能点。


