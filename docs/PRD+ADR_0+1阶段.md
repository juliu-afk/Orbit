## Step 0.1：项目章程与度量基线

| PRD (产品需求文档) |  |
| --- | --- |
| **背景** | 团队过往使用CrewAI等集成框架，出现Token消耗超标（单任务>40）及黑盒调度故障，需自研以达成极致性能目标。章程是后续所有架构决策的“宪法”，必须全员认同。 |
| **用户故事** | 作为技术负责人，我需要一份明确的章程，包含成功度量（Token≤35/任务、调度≤8s、幻觉率<3%），以便团队对齐并在争议时有决策依据。 |
| **需求描述** | ①输出章程文档（Markdown格式）；②定义可量化指标，每个指标须包含“测量方法”（例如Token通过LiteLLM的usage字段统计）；③建立风险登记册（至少5条）；④明确Scope In/Out（不涉及时序图谱）。 |
| **范围 (Do/Don't)** | **Do：**明确三图谱范围（代码/数据库/配置），定义RACI矩阵。**Don't：**不涉及时序图谱（留待V2），不包含实现细节。 |
| **数据契约** | 章程文件需包含以下YAML frontmatter（可被CI解析）： |
| | ``代码块-1`` |
| **异常定义** | 若评审未通过，标记为“REJECTED”并记录原因，重新提交。 |
| **成功标准→验收** | **SC1:**所有指标可自动化测量 →**AC1:**CI脚本能解析frontmatter并生成Prometheus指标定义（如`# TYPE task_tokens_total counter`）。 |
| | **SC2:**范围清晰无歧义 →**AC2:**评审会上逐条确认Scope Out，全部通过。 |
| **待定决策 (已决议)** | **Q:**若单任务Token偶尔超过35但平均低于35是否允许？ →**决议：**不允许超过，设为硬性红线，超过则CI失败（需人工豁免）。 |

| ADR (架构决策记录) |  |
| --- | --- |
| **技术栈版本** | 无代码依赖，仅需`markdownlint-cli@0.35`用于格式校验，`yq`用于解析YAML frontmatter。 |
| **架构位置** | 顶层治理层，存放于`docs/charter.md`，CI阶段作为门禁。 |
| **实施细节** | AC1: 在`.github/workflows/ci.yml`中添加任务： |
| | ``代码块-2`` |
| | AC2: 组织评审会议，使用PR流程，需至少2名架构师LGTM。 |
| **风险与缓解** | 风险：指标过严导致开发压力过大。缓解：设置“预警线”（Token=30）与“强制线”（Token=35），预警线仅提示不阻断。 |
| **需求错位** | 若业务方后期要求更高吞吐而非低延迟，指标需调整。当前已与业务方书面确认“效率+质量”优先。 |
| **技术约束** | 禁止在章程中提及时序图谱相关内容。 |
| **环境配置** | 无需环境变量。 |
| **依赖链** | 无外部依赖。 |

🧪 原子化测试用例 (pytest)：
import yaml, pytest
def test_charter_metrics_exist():
with open("docs/charter.md") as f:
content = f.read()
# 提取frontmatter
parts = content.split('---')
data = yaml.safe_load(parts[1])
assert data['metrics']['max_tokens_per_task'] <= 35
assert data['metrics']['max_schedule_latency_ms'] <= 8000
assert 'time_series_graph' in data['scope_out']

## Step 0.2：技术栈与环境初始化

| PRD |  |
| --- | --- |
| **背景** | 团队需统一Python版本、包管理工具及容器化方案，避免“环境不一致”导致的集成问题。必须做到新成员加入后5分钟内可启动全部服务。 |
| **用户故事** | 作为后端开发，我需要`make init`一键拉起所有服务（PostgreSQL/Redis/LiteLLM），以便快速开始编码。 |
| **需求描述** | ①使用Poetry管理依赖，锁定精确版本；②编写`docker-compose.yml`定义PostgreSQL 15、Redis 7.2、LiteLLM 1.40；③编写`Makefile`包含`init`（启动服务+安装依赖）、`test`（运行pytest）、`lint`（black/isort/mypy）；④配置`pre-commit`钩子；⑤提供`.env.example`模板。 |
| **范围** | **Do：**Python 3.11.8, Poetry, FastAPI, Uvicorn, Pydantic, SQLAlchemy, asyncpg, redis-py, LiteLLM。**Don't：**不引入Kubernetes或Docker Compose之外的编排工具；不实现服务高可用（留待生产阶段）。 |
| **数据契约** | **.env.example**内容： |
| | # 基础配置 |
| | APP_ENV=dev |
| | DEBUG=true |
| | # 数据库（PostgreSQL） |
| | DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/app |
| | # Redis |
| | REDIS_URL=redis://localhost:6379/0 |
| | # LiteLLM |
| | LITELLM_MASTER_KEY=sk-123456 |
| | LITELLM_PROXY_URL=http://localhost:4000 |
| | # 模型API Keys (Mock阶段用占位) |
| | OPENAI_API_KEY=sk-dummy |
| | DEEPSEEK_API_KEY=sk-dummy |
| **异常定义** | 若`docker-compose up`失败，脚本退出码非0，打印错误日志；若Poetry安装依赖失败，退出并提示手动修复。 |
| **成功标准→验收** | **SC1:**5分钟内拉起全部服务 →**AC1:**执行`make init`，所有容器健康（`docker-compose ps`显示状态为healthy）。 |
| | **SC2:**依赖锁定无冲突 →**AC2:**`poetry install --no-dev`成功，无依赖解析错误。 |
| | **SC3:**代码格式化检查通过 →**AC3:**运行`make lint`，输出无错误。 |
| **待定决策** | **Q:**使用Poetry还是Pipenv？ →**决议：**Poetry（依赖解析更快，且内置虚拟环境管理）。 |
| | **Q:**LiteLLM Proxy是否需要持久化存储？ →**决议：**MVP阶段使用内存存储，生产阶段再配置Redis。 |

| ADR |  |
| --- | --- |
| **技术栈版本** | Poetry 1.8.2, Python 3.11.8 (docker镜像), FastAPI 0.110.0, Pydantic 2.6.1, Uvicorn 0.27.1, SQLAlchemy 2.0.25, asyncpg 0.29.0, redis-py 5.0.1, LiteLLM 1.40.0 (docker镜像), Docker Compose 2.24+。 |
| **架构位置** | 基础设施层，提供运行时环境与依赖。 |
| **实施细节** | **docker-compose.yml 核心片段：** |
| | ``代码块-3`` |
| | **Makefile 示例：** |
| | ``代码块-4`` |
| **风险与缓解** | 风险：LiteLLM版本更新快，锁定镜像tag避免变动；PostgreSQL健康检查可能因启动慢而失败，增加`--wait`和重试。缓解：在Makefile中增加`sleep 5`后再次检查。 |
| **需求错位** | 若未来需接入国产信创数据库（如达梦），当前选型不兼容。但初期明确不涉及。 |
| **技术约束** | 不引入K8s，故`docker-compose`中不使用`deploy`资源限制字段（简化）。 |
| **环境配置** | 所有环境变量通过`.env`文件加载，`.env.example`提交至仓库，`.env`加入`.gitignore`。 |
| **依赖链** | Poetry → 安装依赖 → Docker Compose → 启动容器 → 应用运行。 |

🧪 原子化测试用例 (pytest)：
import subprocess, json, time
def test_docker_services_healthy():
# 等待服务启动
time.sleep(5)
result = subprocess.run(["docker-compose", "ps", "--format", "json"], capture_output=True)
containers = json.loads(result.stdout)
for c in containers:
assert c["State"] == "running"
assert "healthy" in c.get("Health", "")
def test_poetry_lock():
result = subprocess.run(["poetry", "check", "--lock"], capture_output=True)
assert result.returncode == 0
def test_env_example_exists():
assert os.path.exists(".env.example")
with open(".env.example") as f:
content = f.read()
assert "DATABASE_URL" in content


## Step 0.4：架构锚定与Prompt/Context工程
编排层设计原则 · 五条核心设计原则 · 五层上下文重述
版本说明：本补充章节明确V14.1系统锚定于“多智能体软件开发操作系统”这一架构层级（编排层），而非单智能体执行工具（执行层）。基于此锚定，系统性地重述了Prompt/Context Engineering的五条核心设计原则，并对五层上下文架构、验证门禁、Agent角色定义等核心模块进行了架构层面的重新诠释。
- 1. 架构锚定：编排层 vs 执行层
- 2. 五条核心设计原则
- 3. 五层上下文的编排层视角
- 4. 验证门禁：协作契约的守卫
- 5. Agent角色的重新定义
- 6. 与现有Step的映射关系
- 7. 需要更新的文档位置
- 8. 代码示例
#### 1. 架构锚定：编排层 vs 执行层
> **核心声明：V14.1 系统在设计上明确锚定在 “多智能体软件开发操作系统” 这一层级（编排层），而非单智能体执行工具（如 Claude Code、Codex）的层级。这一锚定决定了所有 Prompt 和 Context Engineering 的设计必须服务于 协作流程的编排与治理，而非单次代码生成的质量。**
#### 1.1 编排层 vs 执行层
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
#### 1.2 为什么锚定编排层？
- V14.1 不是“另一个 Claude Code”：Claude Code、Codex 是单智能体执行工具，解决的是“如何让一个 AI 帮你写代码”。V14.1 解决的是“如何让一群 AI 协作完成软件开发全流程”。两者的目标不同，处于不同的抽象层级。
- 编排层的核心价值在于“治理”：单智能体工具依赖模型本身的推理能力和权限控制；V14.1 通过多 Agent 协作、状态机调度、四图谱、9层验证门禁、审计链，实现了对开发流程的系统性治理。
- Claude Code/Codex 可以是 V14.1 的执行引擎：V14.1 不排斥在底层调用 Claude Code 或 Codex 作为执行单元，但 V14.1 的核心价值在上层——编排、治理、验证、追溯。
#### 2. 五条核心设计原则
基于“编排层锚定”，Prompt 和 Context Engineering 的设计必须遵循以下五条核心原则：
#### 原则一：System Prompt 定义“协作角色”而非“个人能力”
执行层写法（不应采用）："你是一个 Python 专家，擅长编写高质量的代码。"
编排层写法（应该采用）："你是 V14.1 多智能体协作网络中的 DeveloperAgent，在 ArchitectAgent 确定的技术方案范围内，生成符合四图谱事实的代码，输出必须通过 L1-L9 验证。"
核心差异：Prompt 描述的是 Agent 在协作流程中的位置和契约，而非个人技术能力。
#### 原则二：上下文是“协作状态”而非“代码库快照”
执行层写法（不应采用）：直接塞入 payment/service.py 的完整内容。
编排层写法（应该采用）：注入上游 Agent 的产出摘要、当前 DAG 进度、四图谱查询结果、验证门禁状态。
核心差异：上下文描述的是“协作进展到哪一步、上下游产出了什么、事实是什么”，而非“代码库长什么样”。
#### 原则三：指令与约束来自“协作契约”而非“用户指令”
执行层写法（不应采用）：“用户说：请修改 timeout 为 60”。
编排层写法（应该采用）：协作契约约束（来自 PLANNING 阶段）+ 验证门禁规则（L1-L9）+ 合规要求（领域知识）。
核心差异：约束来自整个协作流程的累积契约，而非当前用户的“一句话指令”。
#### 原则四：上下文组织遵循“渐进式披露”而非“一次性加载”
执行层写法（不应采用）：把所有文件内容塞进上下文窗口。
编排层写法（应该采用）：五层分级（L1-L5），按需加载，每层有明确的 Token 预算和加载策略。
核心差异：上下文是分层、按需、渐进式披露的，而非一次性装满。
#### 原则五：通信格式服务于“跨 Agent 可解析”而非“人类可读”
执行层写法（不应采用）：“我觉得这个函数应该改成异步的”。
编排层写法（应该采用）：结构化 JSON（含 proposal_id、change、reasoning、evidence、contract_assertions）。
核心差异：通信格式是结构化的、可被其他 Agent 自动解析的，而非自由文本。
#### 3. 五层上下文的编排层视角
原 V14.1 的五层上下文架构（L1-L5）在编排层视角下应重新诠释如下：
| 层级 | 原有定义 | 编排层重新诠释 | 承载的内容 |
| --- | --- | --- | --- |
| L1 | 全局不可变上下文 | 协作宪法：所有 Agent 必须遵守的全局规则 | System Prompt（协作角色定义）+ 协作契约 + 验证规则 + 红线清单 |
| L2 | 确定性事实上下文 | 协作事实库：当前任务依赖的确定性事实 | 四图谱查询结果（代码+数据库+配置+知识） |
| L3 | 任务动态上下文 | 协作状态：当前任务的执行状态 | PRD 摘要、上游 Agent 产出摘要、当前 DAG 进度、检查点摘要 |
| L4 | Agent 局部工作记忆 | 个体工作台：Agent 私有上下文 | 思考→行动→观察循环中的中间产物（不跨 Agent 共享） |
| L5 | 跨任务长期记忆 | 协作经验库：跨任务的模式复用 | 教训库、成功模式库（通过 RAG 检索注入） |
> **关键洞察：五层上下文的本质是 协作流程的信息分层——从全局宪法（L1）到具体执行（L4），从当前状态（L3）到长期积累（L5）。每一层都有明确的语义边界和加载策略，共同构成 Agent 感知的“协作全景图”。**
#### 4. 验证门禁：协作契约的守卫
在编排层视角下，L1-L9 验证门禁不再是“代码质量检查工具”，而是协作契约的守卫（Guardians of the Collaboration Contract）。
#### 4.1 验证门禁的定位
- 执行层视角：验证门禁是“代码是否正确”的检查。
- 编排层视角：验证门禁是“Agent 的产出是否满足协作契约”的门槛。只有通过所有门禁，产出才能进入共享上下文，成为下游 Agent 的输入。
#### 4.2 验证门禁与协作契约的映射
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
> **关键洞察：验证门禁不是“质检员”，而是协作契约的执行者。它们确保每个 Agent 的产出在进入共享上下文之前，已经满足所有契约条款，从而防止幻觉在 Agent 间传播。**
#### 5. Agent 角色的重新定义
在编排层视角下，五个 Agent 的角色应重新定义如下：
| Agent | 执行层定义 | 编排层定义 | 协作契约 |
| --- | --- | --- | --- |
| 架构师 | 设计系统架构的技术专家 | 方案制定者：将 PRD 转化为可执行的技术方案（tasks.json） | 输入：PRD（已澄清）；输出：tasks.json + 设计约束；契约：方案必须覆盖所有需求条目 |
| 开发者 | 编写代码的工程师 | 代码实现者：在方案约束下生成代码 | 输入：tasks.json + 设计约束；输出：code diff；契约：代码必须通过 L1-L9 验证 |
| 审查员 | 代码审查专家 | 仲裁者：裁决分歧，输出终审意见 | 输入：两个候选方案；输出：裁决结果；契约：分歧时启动仲裁，输出选择依据 |
| QA | 测试工程师 | 验证者：执行验证门禁，生成验证报告 | 输入：代码 + 验证规则；输出：验证报告；契约：报告必须包含 L1-L9 逐项结果 |
| 配置管理员 | 运维工程师 | 环境守护者：保障配置一致性 | 输入：配置变更请求；输出：配置验证/修复结果；契约：配置必须与黄金基线一致 |
> **关键洞察：Agent 的定义从“角色描述”转向“协作契约描述”。每个 Agent 的核心是对输入、输出、契约的明确界定——这正是编排层设计的核心产物，也是系统 Prompt 的核心内容。**
#### 6. 与现有 Step 的映射关系
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
#### 7. 需要更新的文档位置
| 文档位置 | 更新内容 | 更新目的 |
| --- | --- | --- |
| Step 0.1（项目章程） | 新增“架构锚定声明”章节 | 明确 V14.1 锚定编排层，作为所有后续决策的顶层依据 |
| Step 5.2（Agent 角色与 Prompt） | System Prompt 模板增加“协作契约”章节 | 确保每个 Agent 的 Prompt 定义的是协作角色而非个人能力 |
| Step 5.4（Agent 间通信） | 新增“通信格式规范”章节 | 强制结构化 JSON 通信，使通信跨 Agent 可解析 |
| 五层上下文（L1-L5 设计文档） | 新增“渐进式披露”原则说明；按编排层视角重述各层语义 | 明确五层上下文的编排层设计意图 |
| L1-L9 验证门禁（设计文档） | 新增“验证门禁作为协作契约守卫”定位说明 | 明确验证门禁的编排层定位，而非单纯的质量检查 |
#### 8. 代码示例
#### 8.1 编排层风格 System Prompt 模板
```
<system>
<anchor>
【架构锚定声明】
你是 V14.1 多智能体协作网络中的 DeveloperAgent。
你的职责是在 ArchitectAgent 确定的技术方案范围内，生成符合四图谱事实的代码。
你的输出必须通过 L1-L9 验证门禁后才可进入共享上下文。
</anchor>
<collaboration_contract>
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
</collaboration_contract>
<rules>
【硬性规则 - 协作宪法】
1. 禁止引入未在三图谱中确认的第三方库
2. 禁止生成包含硬编码密钥的代码
3. 禁止在未通过 L1-L9 验证的情况下提交代码
4. 遇到不确定信息，必须先查四图谱，禁止凭记忆
</rules>
<tools>
【可用工具】
- query_graph(type="code|database|config|knowledge", symbol="...")
- run_sandbox(code_snippet)
- propose_change(proposal: ProposalSchema)
</tools>
</system>
```
#### 8.2 结构化通信格式示例
```
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
reasoning: str   # 为什么这样提议
evidence: List[Dict[str, str]]  # 支撑依据
contract_assertions: List[str]  # 断言列表
"""执行所有验证门禁，返回结果"""
results = {}
for gate in self.gates:
result = await gate.validate(proposal.proposal_data)
results[gate.name] = result
if not result.passed:
return {
"passed": False,
"failed_at": gate.name,
"results": results,
"message": f"Contract violated at {gate.name}: {result.reason}"
}
return {
"passed": True,
"results": results,
"message": "All contract gates passed. Proposal can enter shared context."
}
```
> **✅ 架构锚定与Prompt/Context工程交付确认
架构锚定声明：编排层 vs 执行层的完整对比，明确 V14.1 的定位
五条核心设计原则：协作角色、协作状态、协作契约、渐进式披露、结构化通信
五层上下文重述：按编排层视角重新诠释 L1-L5 的语义
验证门禁重定位：作为协作契约的守卫，而非单纯的质量检查
Agent 角色重定义：从“角色描述”转向“协作契约描述”
与现有 Step 映射：明确需要更新的文档位置和修改内容
代码示例：编排层风格 System Prompt、结构化通信格式、协作契约守卫
下一步：可将本报告中的更新内容合并到主开发计划的对应 Step 中。**
— V14.1 开发计划 · 架构锚定与Prompt/Context工程 · 2026年6月22日 —

## Step 1.1：四层架构与API契约 (FastAPI)

| PRD |  |
| --- | --- |
| **背景** | 模块职责不清会导致循环依赖，须在编码前明确接入层、调度层、能力层、基础层边界，并定义统一的RESTful API契约，便于前后端并行开发。 |
| **用户故事** | 作为前端开发（未来），我需要OpenAPI 3.0契约，以便后续开发驾驶舱时模拟后端行为。 |
| **需求描述** | ①定义`/api/v1/tasks`（POST创建任务）、`/api/v1/tasks/{task_id}`（GET查询状态）、`/api/v1/tasks/{task_id}/cancel`（POST取消任务）；②使用Pydantic定义请求/响应模型，包含完整的字段校验；③集成FastAPI自动生成Swagger UI；④实现健康检查端点`/health`。 |
| **范围** | **Do：**定义核心CRUD及取消操作。**Don't：**不实现Admin API，不实现WebSocket（留V2），不实现真实的业务逻辑（仅返回mock响应）。 |
| **数据契约** | ``代码块-5`` |
| **异常定义** | ``代码块-6`` |
| | HTTP状态码：404 (Not Found), 400 (Bad Request), 409 (Conflict), 500 (Internal Error)。 |
| **成功标准→验收** | **SC1:**Swagger UI可访问 →**AC1:**启动服务后访问`/docs`显示所有端点。 |
| | **SC2:**请求/响应校验生效 →**AC2:**发送无效prd（长度<10）返回422，错误信息包含字段级校验失败。 |
| | **SC3:**无循环依赖 →**AC3:**运行`pydeps src --only-cycles`无输出。 |
| **待定决策** | **Q:**任务ID生成策略？ →**决议：**使用`uuid.uuid4().hex`（去掉连字符，缩短长度）。 |
| | **Q:**是否支持批量创建？ →**决议：**不支持，留待V2。 |

| ADR |  |
| --- | --- |
| **技术栈版本** | Backend: FastAPI 0.110, Uvicorn 0.27, Pydantic 2.6, python-multipart (用于表单), python-dotenv。 |
| **架构位置** | 接入层，位于`/src/api/`，包含`routes/`（路由定义）、`schemas/`（Pydantic模型）、`dependencies/`（依赖注入，如数据库会话）。 |
| **实施细节** | **项目结构：** |
| | ``代码块-7`` |
| | **main.py 示例：** |
| | ``代码块-8`` |
| **风险与缓解** | 风险：异步路由中误用同步阻塞代码（如`time.sleep`）。缓解：在Code Review中强制使用`asyncio.sleep`，并在CI中加入`pytest-asyncio`检测异步函数中是否调用了同步阻塞库。 |
| **需求错位** | 若后续需gRPC高性能调用，REST契约需重写。但当前QPS<100，REST足够。 |
| **技术约束** | 禁止定义Admin API，故Swagger中不出现`/admin`路径。 |
| **环境配置** | `API_V1_STR=/api/v1`，`PROJECT_NAME="Multi-Agent"`。 |
| **依赖链** | FastAPI → Uvicorn → Pydantic → 无其他依赖。 |

🧪 原子化测试用例 (pytest)：
import pytest
from httpx import AsyncClient
from src.main import app

@pytest.mark.asyncio
async def test_create_task():
async with AsyncClient(app=app, base_url="http://test") as client:
resp = await client.post("/api/v1/tasks", json={"prd": "write a sum function"})
assert resp.status_code == 200
data = resp.json()
assert "task_id" in data
assert data["state"] == "IDLE"

@pytest.mark.asyncio
async def test_invalid_prd():
async with AsyncClient(app=app, base_url="http://test") as client:
resp = await client.post("/api/v1/tasks", json={"prd": "short"})
assert resp.status_code == 422
errors = resp.json()["detail"]
assert any("prd" in err["loc"] for err in errors)

@pytest.mark.asyncio
async def test_health_endpoint():
async with AsyncClient(app=app, base_url="http://test") as client:
resp = await client.get("/health")
assert resp.status_code == 200
assert resp.json()["status"] == "ok"

## Step 1.2：三图谱Schema设计 (SQLAlchemy ORM)

| PRD |  |
| --- | --- |
| **背景** | 三图谱（代码/数据库/配置）是防幻觉的事实依据，需在编码前定义清晰的ORM模型，确保数据库表结构稳定，避免后续大规模迁移。 |
| **用户故事** | 作为后端开发，我需要SQLAlchemy Model定义，以便后续图谱引擎（Step 3.1-3.3）直接调用CRUD，无需重复设计。 |
| **需求描述** | ①定义基类`BaseNode`（id, name, type, meta JSON, created_at）；②定义`Edge`（source_id, target_id, edge_type）；③代码图谱子类（`CodeNode`）继承`BaseNode`并扩展`file_path`,`start_line`,`end_line`；④数据库图谱子类（`DbNode`）扩展`schema`,`db_type`；⑤配置图谱子类（`ConfigNode`）扩展`hash`,`file_path`,`env`；⑥所有模型使用`__tablename__`，无外键约束（物理隔离），确保各图谱独立。 |
| **范围 (Do/Don't)** | **Do：**定义三组独立表（code_nodes, db_nodes, config_nodes）及统一的`edges`表。**Don't：**不设计时序属性（history表），不添加外键约束（保持图谱独立）。 |
| **数据契约 (SQLAlchemy Model)** | ``代码块-9`` |
| **异常定义** | 若模型与现有表冲突，Alembic迁移时抛出`IntegrityError`，需手动处理。模型定义中不包含外键，故无引用完整性异常。 |
| **成功标准→验收** | **SC1:**模型可生成迁移脚本 →**AC1:**运行`alembic revision --autogenerate -m "init schema"`成功生成迁移文件，且执行`alembic upgrade head`成功创建表。 |
| | **SC2:**模型支持JSON查询 →**AC2:**编写测试：`session.query(CodeNode).filter(CodeNode.meta['author'].astext == 'alice')`可执行（PostgreSQL JSONB或SQLite JSON1）。 |
| | **SC3:**三表物理隔离 →**AC3:**`inspect(engine).get_foreign_keys('edges')`返回空列表，且各表无外键依赖。 |
| **待定决策** | **Q:**`meta`字段使用JSONB（Postgres）还是纯文本JSON？ →**决议：**使用`JSON`类型（SQLAlchemy可适配PG JSONB和SQLite JSON，开发与测试统一）。 |
| | **Q:**是否添加`updated_at`字段？ →**决议：**暂不添加，仅记录创建时间，后续V2再考虑。 |

| ADR |  |
| --- | --- |
| **技术栈版本** | SQLAlchemy 2.0.25, Alembic 1.13.0, asyncpg 0.29.0 (PG驱动), aiosqlite 0.19 (测试)。 |
| **架构位置** | 基础层（数据持久化），位于`/src/infrastructure/models/`，被`/src/graph/`和`/src/hallucination/`引用。 |
| **实施细节** | **初始化 Alembic：** |
| | ``代码块-10`` |
| | **迁移命令：** |
| | `alembic revision --autogenerate -m "init_schema"      alembic upgrade head` |
| | **异步引擎配置：** |
| | ``代码块-11`` |
| **风险与缓解** | 风险：SQLAlchemy 2.0移除了`query`，必须使用`select()`，团队可能不熟悉。缓解：提供示例代码片段并纳入Code Review检查清单；在`README`中注明。 |
| **需求错位** | 若将来需Neo4j，当前SQLAlchemy模型需完全推倒。但已评估SQLite+PG足够，且性能测试达标，暂不切换。 |
| **技术约束** | 禁止使用`ForeignKey`约束，确保三图谱物理隔离；禁止定义`history`表（V2再考虑）。 |
| **环境配置** | `DATABASE_URL=sqlite:///./graph.db`(开发)，`DATABASE_URL=postgresql+asyncpg://user:pass@localhost/app`(测试)。 |
| **依赖链** | SQLAlchemy → Alembic → asyncpg/aiosqlite → 数据库。 |

🧪 原子化测试用例 (pytest)：
import pytest
from sqlalchemy import inspect, select
from src.infrastructure.models import Base, CodeNode, DbNode, ConfigNode, Edge, engine

@pytest.mark.asyncio
async def test_all_tables_created():
async with engine.begin() as conn:
inspector = inspect(conn)
tables = await conn.run_sync(lambda sync_conn: inspector.get_table_names())
assert 'code_nodes' in tables
assert 'db_nodes' in tables
assert 'config_nodes' in tables
assert 'edges' in tables

@pytest.mark.asyncio
async def test_no_foreign_keys():
async with engine.begin() as conn:
inspector = inspect(conn)
fks = await conn.run_sync(lambda sync_conn: inspector.get_foreign_keys('edges'))
assert len(fks) == 0

@pytest.mark.asyncio
async def test_json_meta_operations(session):
node = CodeNode(name='test_func', type='function', file_path='/test.py', meta={'author': 'bob'})
session.add(node)
await session.commit()
# 查询meta中的author
stmt = select(CodeNode).where(CodeNode.meta['author'].astext == 'bob')
result = await session.execute(stmt)
found = result.scalar_one()
assert found.name == 'test_func'


**✅ 前置基础步骤全量交付确认：**以上四个Step覆盖了MVP阶段第一周的全部基础设施工作。开发人员可据此：

- **Step 0.1**→ 编写章程文档并配置CI门禁
- **Step 0.2**→ 搭建开发环境（Docker + Poetry + Makefile）
- **Step 1.1**→ 搭建FastAPI应用框架，定义API契约
- **Step 1.2**→ 定义SQLAlchemy ORM模型并生成数据库迁移

全部Step均包含可直接复制的代码片段、配置文件和测试用例，预计总工时约8小时（1人日）。后续功能开发（调度器、图谱引擎等）将以此为基础。



```
// 代码块-1
metrics:
  max_tokens_per_task: 35
  max_schedule_latency_ms: 8000
  max_hallucination_rate: 0.03
scope_in:
  - code_graph
  - db_graph
  - config_graph
scope_out:
  - time_series_graph
```


```
// 代码块-2
- name: Parse charter metrics
  run: |
    yq eval '.metrics' docs/charter.md > metrics.yaml
    # 检查max_tokens_per_task是否≤35
```


```
// 代码块-3
services:

      postgres:

        image: postgres:15-alpine

        environment: POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_DB

        healthcheck: {test: ["CMD-SHELL", "pg_isready -U postgres"], interval: 5s}

      redis:

        image: redis:7.2-alpine

        healthcheck: {test: ["CMD", "redis-cli", "ping"], interval: 5s}

      litellm:

        image: ghcr.io/berriai/litellm:main-v1.40.0

        environment: LITELLM_MASTER_KEY, DATABASE_URL (optional)

        command: --port 4000

        healthcheck: {test: ["CMD", "curl", "-f", "http://localhost:4000/health"], interval: 10s}
```


```
// 代码块-4
init: docker-up poetry-install

    docker-up: docker-compose up -d --wait

    poetry-install: poetry install

    test: poetry run pytest

    lint: poetry run black --check src tests && poetry run isort --check-only && poetry run mypy src
```


```
// 代码块-5
from pydantic import BaseModel, Field, HttpUrl, constr

    class TaskCreateRequest(BaseModel):

        prd: constr(min_length=10, max_length=5000) = Field(..., description="Product requirement document")

        language: str = Field("python", regex="^(python|javascript|java|go)$")

        callback_url: Optional[HttpUrl] = None  # 可选回调



    class TaskStatusResponse(BaseModel):

        task_id: str = Field(..., regex=r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$')

        state: str  # IDLE, PARSING, PLANNING, CODING, VERIFYING, DONE, FAILED

        progress: float = Field(ge=0.0, le=1.0)

        result: Optional[str] = None

        created_at: datetime

        updated_at: datetime
```


```
// 代码块-6
class HTTPExceptionDetail(BaseModel):

        detail: str

        error_code: str  # 如 "TASK_NOT_FOUND", "INVALID_STATE"

        timestamp: datetime
```


```
// 代码块-7
src/

    ├── api/

    │   ├── __init__.py

    │   ├── deps.py          # 依赖注入（get_db, get_redis）

    │   ├── routes/

    │   │   ├── tasks.py     # /tasks 路由

    │   │   └── health.py    # /health

    │   └── schemas/

    │       └── task.py      # Pydantic模型

    ├── core/

    │   └── config.py        # 读取环境变量

    └── main.py              # FastAPI app创建
```


```
// 代码块-8
from fastapi import FastAPI

    from src.api.routes import tasks, health

    app = FastAPI(title="Multi-Agent System", version="0.1.0")

    app.include_router(tasks.router, prefix="/api/v1")

    app.include_router(health.router)
```


```
// 代码块-9
from sqlalchemy import Column, String, JSON, Integer, Float, DateTime, func

    from sqlalchemy.ext.declarative import declarative_base

    Base = declarative_base()



    class BaseNode(Base):

        __abstract__ = True

        id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))

        name = Column(String(255), nullable=False, index=True)

        type = Column(String(50), nullable=False, index=True)

        meta = Column(JSON, default={})

        created_at = Column(DateTime, server_default=func.now(), index=True)



    class CodeNode(BaseNode):

        __tablename__ = 'code_nodes'

        file_path = Column(String(512), nullable=False)

        start_line = Column(Integer)

        end_line = Column(Integer)



    class DbNode(BaseNode):

        __tablename__ = 'db_nodes'

        schema = Column(String(128))

        db_type = Column(String(50))  # 'table', 'view', 'column'



    class ConfigNode(BaseNode):

        __tablename__ = 'config_nodes'

        hash = Column(String(64), nullable=False, index=True)  # SHA256

        file_path = Column(String(512), nullable=False)

        env = Column(String(50))



    class Edge(Base):

        __tablename__ = 'edges'

        id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))

        source_id = Column(String(36), nullable=False, index=True)

        target_id = Column(String(36), nullable=False, index=True)

        edge_type = Column(String(50), nullable=False, index=True)  # 'calls', 'inherits', 'references', 'depends'

        created_at = Column(DateTime, server_default=func.now())



    # 为提升查询性能，建议为edges添加联合索引

    # Index('idx_edges_source_type', source_id, edge_type)

    # Index('idx_edges_target_type', target_id, edge_type)
```


```
// 代码块-10
alembic init migrations

    # 编辑 alembic.ini 设置 sqlalchemy.url = sqlite:///./graph.db (开发)

    # 在 migrations/env.py 中导入 Base

    from src.infrastructure.models import Base

    target_metadata = Base.metadata
```


```
// 代码块-11
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

    engine = create_async_engine(settings.DATABASE_URL, echo=settings.DEBUG)

    AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)
```


# 多Agent自循环系统 · 阶段2核心强化 (Step 2.1 & 2.2) · 编码就绪级PRD/ADR

LiteLLM网关+熔断器 ｜ 检查点持久化（Redis+PG）

**交付声明：**本报告为阶段2（核心强化，W3-W6）的前两个步骤的终极细化文档。Step 2.1将MVP的Mock LLM替换为真实LiteLLM网关，并实现熔断器保障系统韧性；Step 2.2实现调度器状态检查点，支持崩溃恢复。这两个步骤与已交付的MVP代码无缝衔接（调度器调用LLMClient，检查点被调度器使用）。每个Step均包含字段级契约、精确函数签名、DDL/配置、原子化pytest用例，可直接编码。

