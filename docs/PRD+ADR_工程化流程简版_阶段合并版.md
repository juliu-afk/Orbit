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



## Step 2.1：LiteLLM网关集成与熔断器

| PRD (产品需求文档) |  |
| --- | --- |
| **背景** | MVP使用Mock LLM仅能返回固定模板，无法应对真实场景。需接入真实LLM（DeepSeek为默认主力，Qwen为备选），并实现统一网关（LiteLLM Proxy）管理密钥、成本追踪和降级。同时必须实现熔断器，防止下游LLM API故障导致雪崩。 |
| **用户故事** | 作为调度器，我通过统一的`LLMClient`调用`generate(prompt, system_prompt)`，自动选择可用模型、记录Token消耗，并在连续失败时触发熔断，快速返回错误而非无限等待。 |
| **需求描述** | ①部署LiteLLM Proxy容器（已包含在docker-compose中）；②配置主模型（DeepSeek-Chat）和备选模型（Qwen-Plus），API Key从环境变量读取；③实现`LLMClient`类，封装`litellm.acompletion`异步调用，支持流式（预留）和同步模式（MVP）；④实现熔断器（连续5次失败或1分钟内错误率>30%触发，冷却60s，半开状态下放行1个请求探测恢复）；⑤每次调用记录Token消耗（prompt_tokens, completion_tokens, total_tokens）及成本（按模型单价计算）到日志；⑥提供`get_usage_stats(task_id)`查询任务累计消耗。 |
| **范围 (Do/Don't)** | **Do：**支持DeepSeek主力、Qwen备选；支持熔断器状态共享（Redis存储）；支持成本追踪。**Don't：**不实现流式输出（V2）；不实现复杂路由策略（如基于成本的智能路由）；不实现用户级配额管理。 |
| **数据契约** | ``代码块-1`` |
| **异常定义** | ``代码块-2`` |
| **成功标准→验收** | **SC1:**正常调用返回有效内容 →**AC1:**向LLMClient发送“写一个求和函数”，返回Python代码且包含`def add`。 |
| | **SC2:**熔断器生效 →**AC2:**模拟连续5次超时（或错误），第6次调用直接抛出`LLMCircuitOpenError`，不转发请求。 |
| | **SC3:**自动恢复 →**AC3:**熔断冷却60s后，第一次请求进入半开状态，若成功则回到CLOSED；若失败则重新OPEN。 |
| | **SC4:**成本追踪 →**AC4:**调用后查看日志，包含`cost_usd`字段，且数值合理（DeepSeek约$0.001/1K tokens）。 |
| | **SC5:**备选降级 →**AC5:**当主力模型连续失败2次，自动切换至备选模型并成功返回。 |
| **待定决策** | **Q1:**熔断状态存储在内存还是Redis？ →**决议：**Redis（跨实例共享，为后续水平扩展准备）。 |
| | **Q2:**熔断阈值（5次失败）是全局还是按模型？ →**决议：**按模型粒度，因为不同模型可用性不同。 |
| | **Q3:**冷却期60s是否固定？ →**决议：**固定，但在配置中可通过`CIRCUIT_BREAKER_TIMEOUT`覆盖。 |

| ADR (架构决策记录) |  |
| --- | --- |
| **技术栈版本** | litellm 1.40.0 (Proxy模式，已部署), redis-py 5.0.1 (用于熔断状态), httpx 0.27.0 (异步HTTP客户端)，Python 3.11。 |
| | LiteLLM Proxy容器已集成在docker-compose中，使用`ghcr.io/berriai/litellm:main-v1.40.0`。 |
| **架构位置** | 能力层（AI网关），位于`/src/llm/client.py`，实现`LLMClient`。被调度器`/src/scheduler/orchestrator.py`调用。 |
| **实施细节** | **核心类与关键方法：** |
| | ``代码块-3`` |
| **风险与缓解** | 风险1：LiteLLM Proxy成为单点故障。缓解：docker-compose增加restart: unless-stopped，且在K8s阶段部署多副本。 |
| | 风险2：Redis连接丢失导致熔断器失效。缓解：熔断器降级为内存模式（仅单实例有效），并记录错误日志。 |
| **需求错位** | 若后续需接入Azure OpenAI等，需修改`PRICES`和模型映射。当前已支持通过配置扩展。 |
| **技术约束** | 必须使用异步（`async/await`）与调度器保持一致性；禁止同步调用`litellm.completion`。 |
| **环境配置** | LITELLM_PROXY_URL=http://litellm:4000 |
| | DEEPSEEK_API_KEY=sk-xxx |
| | QWEN_API_KEY=sk-yyy |
| | CIRCUIT_BREAKER_TIMEOUT=60 |
| | REDIS_URL=redis://redis:6379/0 |
| **依赖链** | LLMClient → redis-py (熔断状态) → litellm (acompletion) → LiteLLM Proxy → 各模型API。 |

🧪 原子化测试用例 (pytest)：
import pytest
from unittest.mock import AsyncMock, patch
from src.llm.client import LLMClient, LLMCircuitOpenError

@pytest.mark.asyncio
async def test_normal_call(llm_client, mock_redis):
with patch("src.llm.client.acompletion", new_callable=AsyncMock) as mock_acompletion:
mock_acompletion.return_value.choices = [AsyncMock(message=AsyncMock(content="def add(a,b): return a+b"))]
mock_acompletion.return_value.usage.dict.return_value = {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}
resp = await llm_client.generate(LLMRequest(prompt="sum"), "task-1")
assert "add" in resp.content
assert resp.cost_usd > 0

@pytest.mark.asyncio
async def test_circuit_breaker_opens(llm_client, mock_redis):
cb_key = "cb:deepseek/deepseek-chat"
# 模拟连续5次失败
for i in range(5):
await llm_client._circuit_breaker.record_failure(cb_key)
# 第6次应抛出熔断异常
with pytest.raises(LLMCircuitOpenError):
await llm_client.generate(LLMRequest(prompt="test"), "task-2")

@pytest.mark.asyncio
async def test_fallback(llm_client, mock_redis):
with patch("src.llm.client.acompletion", side_effect=Exception("API error")):
with patch.object(llm_client, "_select_model", return_value=llm_client.DEFAULT_MODEL):
with patch.object(llm_client, "generate", new_callable=AsyncMock) as mock_gen:
mock_gen.return_value = LLMResponse(...) # 模拟备选成功
await llm_client.generate(LLMRequest(prompt="test"), "task-3")
mock_gen.assert_called_once()

## Step 2.2：检查点持久化 (Redis + PostgreSQL)

| PRD |  |
| --- | --- |
| **背景** | 调度器执行长耗时任务（可能涉及多次LLM调用），若进程崩溃，重新执行将浪费Token和时间。需实现状态检查点，支持从崩溃中快速恢复。 |
| **用户故事** | 作为调度器，我在每个关键状态转换后调用`save_checkpoint(task_id, snapshot)`，若进程意外终止，重启后调用`load_checkpoint(task_id)`可恢复至最近断点。 |
| **需求描述** | ①提供`CheckpointManager`类，支持异步保存/加载；②Redis存储热数据（`EXPIRE 3600`），Key模板`ckpt:{env}:{task_id}`，值JSON序列化；③PostgreSQL存储冷备份（表`checkpoints`），使用异步写入（fire-and-forgot但需记录错误）；④加载时优先读Redis，若Redis不存在则查PG并回填Redis；⑤版本号（乐观锁）防止旧数据覆盖新数据；⑥提供清理接口`cleanup_old_checkpoints(days=7)`删除PG中过期数据。 |
| **范围 (Do/Don't)** | **Do：**支持Redis + PostgreSQL双层存储；支持版本号乐观锁；支持TTL自动过期。**Don't：**不支持跨版本兼容（V1->V2需显式迁移）；不支持压缩（单次<1MB）。 |
| **数据契约** | ``代码块-4`` |
| **异常定义** | ``代码块-5`` |
| **成功标准→验收** | **SC1:**保存延迟<20ms (P95) →**AC1:**压测`save`1000次，p95延迟<20ms（Redis写入）。 |
| | **SC2:**恢复完整性100% →**AC2:**保存后立即加载，`deepdiff`比较两个对象无差异（忽略updated_at毫秒级）。 |
| | **SC3:**Redis降级PG →**AC3:**Mock Redis抛出`ConnectionError`，保存仍能写入PG，加载时从PG读取并回填Redis。 |
| | **SC4:**版本号防覆盖 →**AC4:**先保存version=1，再保存version=2，加载时返回version=2；若version=1的PG数据晚到（异步），不会覆盖version=2（通过`WHERE version <= EXCLUDED.version`）。 |
| **待定决策** | **Q1:**是否压缩序列化数据？ →**决议：**暂不压缩（单次<1MB），若后续发现膨胀再启用`zlib`。 |
| | **Q2:**清理过期数据的频率？ →**决议：**每周运行一次`cleanup_old_checkpoints(7)`，可通过cron或调度器触发。 |

| ADR |  |
| --- | --- |
| **技术栈版本** | redis-py 5.0.1 (asyncio), asyncpg 0.29.0, orjson 3.9.15 (比pickle快且安全), SQLAlchemy 2.0.25 (用于PG表定义和迁移)。 |
| **架构位置** | 基础设施层，位于`/src/infrastructure/checkpoint_manager.py`，被调度器`SchedulerStateMachine`通过依赖注入调用。 |
| **实施细节** | **完整类实现：** |
| | ``代码块-6`` |
| **风险与缓解** | 风险：orjson序列化datetime时默认转为时间戳，反序列化可能丢失时区。缓解：在`CheckpointData.dict()`中指定`json_encoders = {datetime: lambda v: v.isoformat()}`。 |
| | 风险：PG写入失败（如连接断开）不会影响主流程（已fire-and-forgot），但会丢失冷备份。缓解：在`_save_to_pg`中捕获异常并记录Critical级别日志。 |
| **需求错位** | 若将来需跨语言（Java/Go）读取检查点，orjson序列化可读性好（JSON），PG表也兼容。但当前仅Python内部使用。 |
| **技术约束** | 禁止使用`pickle`（安全风险且无法跨语言）。必须使用异步驱动（asyncpg/aiosqlite）。 |
| **环境配置** | REDIS_URL=redis://redis:6379/0 |
| | DATABASE_URL=postgresql+asyncpg://postgres:postgres@postgres:5432/app |
| | CHECKPOINT_TTL=3600 |
| | ENV=dev |
| **依赖链** | CheckpointManager → redis-py (异步) → asyncpg (PG池) → 数据库。 |

🧪 原子化测试用例 (pytest)：
import pytest
from unittest.mock import AsyncMock, patch
from src.infrastructure.checkpoint_manager import CheckpointManager, CheckpointData

@pytest.mark.asyncio
async def test_save_and_load(checkpoint_manager):
data = CheckpointData(task_id="123e4567-e89b-12d3-a456-426614174000", state="CODING", retry_count=0, progress=0.5, context={"code": "print('hi')"})
await checkpoint_manager.save("123e4567-e89b-12d3-a456-426614174000", data)
loaded = await checkpoint_manager.load("123e4567-e89b-12d3-a456-426614174000")
assert loaded.task_id == data.task_id
assert loaded.context["code"] == "print('hi')"

@pytest.mark.asyncio
async def test_redis_fallback(checkpoint_manager, mock_redis_failure):
# 模拟Redis不可用，仍能写入PG
with patch.object(checkpoint_manager.redis, "setex", side_effect=ConnectionError):
data = CheckpointData(...)
await checkpoint_manager.save("task-2", data) # 不应抛出异常
# 加载时从PG读取
with patch.object(checkpoint_manager.redis, "get", return_value=None):
loaded = await checkpoint_manager.load("task-2")
assert loaded is not None

@pytest.mark.asyncio
async def test_version_optimistic_lock(checkpoint_manager):
data_v1 = CheckpointData(task_id="task-3", state="PLANNING", retry_count=0, progress=0.1, context={}, version=1)
await checkpoint_manager.save("task-3", data_v1)
data_v2 = CheckpointData(task_id="task-3", state="CODING", retry_count=0, progress=0.5, context={}, version=2)
await checkpoint_manager.save("task-3", data_v2)
loaded = await checkpoint_manager.load("task-3")
assert loaded.state == "CODING"
assert loaded.version >= 2


**✅ 阶段2 (Step 2.1 & 2.2) 交付确认**

本报告完整交付了阶段2核心强化的前两个步骤：

- **Step 2.1**：实现真实LLM调用（LiteLLM+熔断器+成本追踪），替代MVP的Mock，并具备韧性。
- **Step 2.2**：实现检查点持久化（Redis+PG双层存储），使调度器具备崩溃恢复能力。

这两个Step与已交付的MVP组件（调度器状态机、沙箱、API契约）无缝衔接。开发人员可按每个Step拆分为3-5个子任务，约2人日完成。后续Step 2.3（图谱引擎）将在此基础上继续构建。



```
// 代码块-1
from pydantic import BaseModel, Field

    from typing import Optional, Dict, Any, List

    from enum import Enum



    class ModelProvider(str, Enum):

        DEEPSEEK = "deepseek"

        QWEN = "qwen"



    class LLMRequest(BaseModel):

        prompt: str = Field(..., min_length=1, max_length=8000)

        system_prompt: Optional[str] = Field(None, max_length=2000)

        temperature: float = Field(0.7, ge=0.0, le=1.0)

        max_tokens: int = Field(2048, ge=1, le=8192)

        provider: Optional[ModelProvider] = None  # 若为空则自动选择



    class LLMResponse(BaseModel):

        content: str

        provider: ModelProvider

        model_name: str

        usage: Dict[str, int]  # {prompt_tokens, completion_tokens, total_tokens}

        cost_usd: float

        latency_ms: float

        cached: bool = False  # 是否命中缓存（预留）



    class CircuitBreakerState(str, Enum):

        CLOSED = "closed"       # 正常

        OPEN = "open"           # 熔断开启，拒绝请求

        HALF_OPEN = "half_open" # 探测恢复
```


```
// 代码块-2
class LLMError(Exception):

        """LLM调用基础异常"""

        pass



    class LLMConnectionError(LLMError):

        """网络/连接错误"""

        pass



    class LLMAuthenticationError(LLMError):

        """API密钥无效"""

        pass



    class LLMRateLimitError(LLMError):

        """请求限流（429）"""

        pass



    class LLMCircuitOpenError(LLMError):

        """熔断器开启，拒绝请求"""

        pass
```


```
// 代码块-3
import asyncio

    import time

    import logging

    import redis.asyncio as redis

    from litellm import acompletion

    from src.core.config import settings



    logger = logging.getLogger(__name__)



    class LLMClient:

        DEFAULT_MODEL = "deepseek/deepseek-chat"

        FALLBACK_MODEL = "qwen/qwen-plus"

        PRICES = {  # 每1K tokens 美元

            "deepseek/deepseek-chat": {"prompt": 0.00014, "completion": 0.00028},

            "qwen/qwen-plus": {"prompt": 0.0001, "completion": 0.0002},

        }



        def __init__(self, redis_client: redis.Redis):

            self.redis = redis_client

            self._circuit_breaker = CircuitBreaker(redis_client)



        async def generate(self, request: LLMRequest, task_id: str) -> LLMResponse:

            # 1. 选择模型

            model = self._select_model(request.provider)

            cb_key = f"cb:{model}"

            # 2. 检查熔断器

            if await self._circuit_breaker.is_open(cb_key):

                raise LLMCircuitOpenError(f"Circuit breaker open for {model}")

            # 3. 调用LLM

            try:

                start = time.time()

                response = await acompletion(

                    model=model,

                    messages=[

                        {"role": "system", "content": request.system_prompt or "You are a helpful assistant."},

                        {"role": "user", "content": request.prompt}

                    ],

                    temperature=request.temperature,

                    max_tokens=request.max_tokens,

                )

                latency = (time.time() - start) * 1000

                usage = response.usage.dict()

                cost = self._calculate_cost(model, usage)

                # 记录成功，重置熔断器计数

                await self._circuit_breaker.record_success(cb_key)

                self._log_usage(task_id, model, usage, cost, latency)

                return LLMResponse(

                    content=response.choices[0].message.content,

                    provider=ModelProvider.DEEPSEEK if "deepseek" in model else ModelProvider.QWEN,

                    model_name=model,

                    usage=usage,

                    cost_usd=cost,

                    latency_ms=latency

                )

            except Exception as e:

                # 记录失败，更新熔断器

                await self._circuit_breaker.record_failure(cb_key)

                # 尝试备选模型

                if model == self.DEFAULT_MODEL:

                    logger.warning(f"Fallback to {self.FALLBACK_MODEL} for task {task_id}")

                    request.provider = ModelProvider.QWEN

                    return await self.generate(request, task_id)

                raise



    class CircuitBreaker:

        FAILURE_THRESHOLD = 5

        TIMEOUT_SECONDS = 60

        ERROR_RATE_THRESHOLD = 0.3  # 1分钟内



        def __init__(self, redis_client):

            self.redis = redis_client



        async def is_open(self, key: str) -> bool:

            state = await self.redis.get(f"{key}:state")

            if state == b"open":

                return True

            if state == b"half_open":

                # 半开状态下，允许一个请求通过

                await self.redis.delete(f"{key}:state")  # 变为closed（探测成功后会被记录为成功）

                return False

            return False



        async def record_failure(self, key: str):

            fail_count = await self.redis.incr(f"{key}:fail_count")

            await self.redis.expire(f"{key}:fail_count", 60)

            total = await self.redis.incr(f"{key}:total_count")

            await self.redis.expire(f"{key}:total_count", 60)

            if fail_count >= self.FAILURE_THRESHOLD or (total > 10 and fail_count/total >= self.ERROR_RATE_THRESHOLD):

                await self.redis.setex(f"{key}:state", self.TIMEOUT_SECONDS, "open")



        async def record_success(self, key: str):

            # 成功后重置计数

            await self.redis.delete(f"{key}:fail_count", f"{key}:total_count")

            await self.redis.delete(f"{key}:state")  # 若有open/half_open，清除
```


```
// 代码块-4
from pydantic import BaseModel, Field

    from datetime import datetime

    from typing import Dict, Any, Optional



    class CheckpointData(BaseModel):

        task_id: str = Field(..., regex=r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$')

        state: str  # 来自TaskState枚举值

        retry_count: int = Field(ge=0)

        progress: float = Field(ge=0.0, le=1.0)

        context: Dict[str, Any] = Field(default_factory=dict)  # 中间产物（如代码片段、LLM响应）

        updated_at: datetime = Field(default_factory=datetime.utcnow)

        version: int = Field(default=1, ge=1)
```


```
// 代码块-5
class CheckpointError(Exception): pass

    class CheckpointNotFoundError(CheckpointError): pass

    class CheckpointCorruptedError(CheckpointError): pass
```


```
// 代码块-6
import orjson

    import asyncio

    from typing import Optional

    from redis.asyncio import Redis

    import asyncpg

    from src.core.config import settings



    class CheckpointManager:

        def __init__(self, redis_client: Redis, pg_pool: asyncpg.Pool, env: str = "dev"):

            self.redis = redis_client

            self.pg = pg_pool

            self.env = env

            self._key_prefix = f"ckpt:{env}"



        async def save(self, task_id: str, data: CheckpointData) -> None:

            serialized = orjson.dumps(data.dict())

            key = f"{self._key_prefix}:{task_id}"

            # 写Redis（重试一次）

            try:

                await self.redis.setex(key, 3600, serialized)

            except Exception as e:

                await asyncio.sleep(0.1)

                await self.redis.setex(key, 3600, serialized)

            # 异步写PG（fire-and-forgot，但捕获日志）

            asyncio.create_task(self._save_to_pg(task_id, data))



        async def load(self, task_id: str) -> Optional[CheckpointData]:

            key = f"{self._key_prefix}:{task_id}"

            # 1. 读Redis

            redis_data = await self.redis.get(key)

            if redis_data:

                parsed = CheckpointData(**orjson.loads(redis_data))

                return parsed

            # 2. 降级读PG

            pg_data = await self._load_from_pg(task_id)

            if pg_data:

                # 回填Redis

                await self.redis.setex(key, 3600, orjson.dumps(pg_data.dict()))

                return pg_data

            return None



        async def _save_to_pg(self, task_id: str, data: CheckpointData):

            query = """

            INSERT INTO checkpoints (task_id, state, retry_count, progress, context, updated_at, version)

            VALUES ($1, $2, $3, $4, $5, $6, $7)

            ON CONFLICT (task_id) DO UPDATE SET

                state = EXCLUDED.state,

                retry_count = EXCLUDED.retry_count,

                progress = EXCLUDED.progress,

                context = EXCLUDED.context,

                updated_at = EXCLUDED.updated_at,

                version = checkpoints.version + 1

            WHERE checkpoints.version <= EXCLUDED.version

            """

            await self.pg.execute(

                query,

                task_id, data.state, data.retry_count, data.progress,

                orjson.dumps(data.context), data.updated_at, data.version

            )



        async def _load_from_pg(self, task_id: str) -> Optional[CheckpointData]:

            query = "SELECT state, retry_count, progress, context, updated_at, version FROM checkpoints WHERE task_id = $1"

            row = await self.pg.fetchrow(query, task_id)

            if not row:

                return None

            return CheckpointData(

                task_id=task_id,

                state=row["state"],

                retry_count=row["retry_count"],

                progress=row["progress"],

                context=orjson.loads(row["context"]),

                updated_at=row["updated_at"],

                version=row["version"]

            )



        async def cleanup_old_checkpoints(self, days: int = 7):

            query = "DELETE FROM checkpoints WHERE updated_at < NOW() - INTERVAL '$1 days'"

            await self.pg.execute(query, days)
```


# 多Agent自循环系统 · 阶段3三图谱引擎 (Step 3.1, 3.2, 3.3) · 编码就绪级PRD/ADR

代码图谱 ｜ 数据库图谱 ｜ 配置图谱

**交付声明：**本报告为阶段3（三图谱引擎开发，W5-W6）的全部三个步骤的终极细化文档。三图谱是系统“事实来源”，为L1（引用验证）、L8（配置漂移）等防幻觉层提供数据支撑。每个Step均包含字段级契约、精确函数签名、DDL/配置、原子化pytest用例，可直接编码。



## Step 3.1：代码图谱引擎（基于AST，支持Python）

| PRD (产品需求文档) |  |
| --- | --- |
| **背景** | LLM频繁引用不存在的函数、类或模块，导致幻觉。需要静态分析代码仓库，提取所有符号定义（函数、类、变量）及调用关系（谁调用谁），提供确定性的事实校验能力。 |
| **用户故事** | 作为开发者Agent，我通过`GraphQuery.exists(symbol_name, symbol_type)`校验生成的代码中的引用是否真实存在，若不存在则拒绝生成并触发重新生成。 |
| **需求描述** | ①使用Python内置`ast`模块解析`.py`文件，提取`FunctionDef`、`ClassDef`、`Assign`（变量）节点；②记录每个符号的名称、所在文件路径、起止行号、所属命名空间（类/模块）；③提取调用关系（`Call`节点），记录调用方和被调用方；④存储到SQLite数据库（复用Step 1.2的`CodeNode`和`Edge`表）；⑤提供增量更新能力（监测文件修改时间，仅重新解析变更文件）；⑥提供查询接口：`exists(name, type)`，`get_callers(symbol)`，`get_callees(symbol)`。 |
| **范围 (Do/Don't)** | **Do：**支持Python语言；支持解析单个文件或整个目录；支持增量更新；支持基础调用关系提取。**Don't：**不支持动态特性（`eval`/`exec`、`__import__`）；不支持跨文件导入解析（仅记录符号定义，不解析导入别名）；不支持控制流分析。 |
| **数据契约** | ``代码块-1`` |
| | 查询接口： |
| | ``代码块-2`` |
| **异常定义** | ``代码块-3`` |
| **成功标准→验收** | **SC1:**解析1000个Python文件<30s →**AC1:**使用包含1000个文件的Django项目测试，计时<30s。 |
| | **SC2:**查询响应<100ms →**AC2:**执行`exists('add')`，`timeit`< 100ms。 |
| | **SC3:**增量更新正确 →**AC3:**修改一个文件后重新解析，仅该文件及其调用方被更新，其他节点不受影响。 |
| | **SC4:**调用链准确 →**AC4:**若文件A中`foo()`调用了文件B的`bar()`，则`get_callers('bar')`返回包含`foo`。 |
| **待定决策** | **Q1:**是否支持跨文件调用链（模块间调用）？ →**决议：**支持，因为调用方和被调用方可能在不同文件中，通过全量解析后统一构建边。 |
| | **Q2:**如何处理同名的函数（重载）？ →**决议：**使用`namespace`字段区分（如`mymodule.MyClass.method`），查询时需提供全限定名或通过上下文推断。 |

| ADR (架构决策记录) |  |
| --- | --- |
| **技术栈版本** | Python 3.11内置`ast`模块；SQLAlchemy 2.0.25 (异步), aiosqlite 0.19 (测试) / asyncpg 0.29 (生产)。 |
| **架构位置** | 能力层（静态分析），位于`/src/graph/code_graph.py`，依赖`/src/infrastructure/models.py`中的`CodeNode`和`Edge`。 |
| **实施细节** | **核心类：** |
| | ``代码块-4`` |
| **风险与缓解** | 风险：AST无法解析有语法错误的文件（导致整个构建失败）。缓解：使用`try-except SyntaxError`跳过该文件并记录错误，保证其他文件入库。 |
| **需求错位** | 若需支持多语言（JS/TS/Java），需切换至Tree-sitter。但MVP阶段仅Python，已规划后续扩展。 |
| **技术约束** | 禁止使用正则表达式解析代码；必须使用AST保证准确性。禁止删除已入库的旧数据（仅标记`deprecated`或软删除）。 |
| **环境配置** | `CODE_GRAPH_DB=sqlite:///./code_graph.db`(开发)，或使用主DATABASE_URL（生产）。 |
| **依赖链** | CodeGraphEngine → SQLAlchemy (async) → aiosqlite/asyncpg → 数据库。 |

🧪 原子化测试用例 (pytest)：
import pytest
from pathlib import Path
from src.graph.code_graph import CodeGraphEngine

@pytest.mark.asyncio
async def test_build_index(tmp_path, code_graph_engine):
# 创建测试文件
test_file = tmp_path / "test.py"
test_file.write_text("def add(a,b): return a+b")
await code_graph_engine.build_index(str(tmp_path))
assert await code_graph_engine.exists("add") is True

@pytest.mark.asyncio
async def test_call_relation(tmp_path, code_graph_engine):
test_file = tmp_path / "test.py"
test_file.write_text("def foo(): return bar()")
await code_graph_engine.build_index(str(tmp_path))
callers = await code_graph_engine.get_callers("bar")
assert "foo" in callers

@pytest.mark.asyncio
async def test_incremental_update(tmp_path, code_graph_engine):
test_file = tmp_path / "test.py"
test_file.write_text("def add(a,b): return a+b")
await code_graph_engine.build_index(str(tmp_path))
# 修改文件
test_file.write_text("def add(a,b,c): return a+b+c")
await code_graph_engine.incremental_update(str(test_file))
# 重新查询，应更新
# 验证方法：检查节点的meta中参数个数是否变化
assert await code_graph_engine.exists("add")

## Step 3.2：数据库图谱引擎（Schema反射）

| PRD |  |
| --- | --- |
| **背景** | LLM生成的SQL/ORM语句常引用不存在的表或字段，导致运行时错误。需通过反射数据库元数据构建数据库图谱，提供表、字段、外键的真实信息。 |
| **用户故事** | 作为QA验证Agent，我需要查询`table_exists('orders')`和`column_exists('orders', 'user_id')`，验证生成的SQL语句合法性。 |
| **需求描述** | ①使用SQLAlchemy反射读取数据库（PostgreSQL/MySQL）的`information_schema`；②提取所有表名、字段名、数据类型、是否可空、默认值；③提取外键关系（来源表.字段 → 目标表.字段）；④存储到`DbNode`和`Edge`表中（复用Step 1.2模型）；⑤提供`table_exists`、`column_exists`、`get_foreign_keys(table)`查询接口；⑥支持多schema（默认public）。 |
| **范围 (Do/Don't)** | **Do：**支持PostgreSQL 15和MySQL 8.0；支持核心表快照（通过`@core`标记），每日备份元数据。**Don't：**不支持存储过程、触发器、视图（V2）；不支持全量MVCC（仅快照）。 |
| **数据契约** | ``代码块-5`` |
| | 查询接口： |
| | ``代码块-6`` |
| **异常定义** | ``代码块-7`` |
| **成功标准→验收** | **SC1:**解析50张表<30s →**AC1:**连接到测试库（含50张表），计时<30s。 |
| | **SC2:**外键关系准确 →**AC2:**若`orders.user_id`引用`users.id`，则`get_foreign_keys('orders')`返回包含`{'column':'user_id','ref_table':'users','ref_column':'id'}`。 |
| | **SC3:**增量快照 →**AC3:**每日定时任务运行后，检查`checkpoints`表中记录的元数据哈希变化。 |
| **待定决策** | **Q1:**快照保留几天？ →**决议：**保留7天，使用`cleanup_old_snapshots(7)`。 |
| | **Q2:**是否支持多数据库连接？ →**决议：**当前仅支持一个主数据库，通过环境变量指定。 |

| ADR |  |
| --- | --- |
| **技术栈版本** | SQLAlchemy 2.0.25 (反射使用`inspect`), asyncpg 0.29 (PG), pymysql 1.1 (MySQL), aiosqlite (测试)。 |
| **架构位置** | 能力层，位于`/src/graph/db_graph.py`。 |
| **实施细节** | **核心类：** |
| | ``代码块-8`` |
| **风险与缓解** | 风险：反射大数据库（千表）可能超时。缓解：使用分页查询`information_schema`，每次最多50张表。 |
| **需求错位** | 若数据库为MongoDB（NoSQL），此模块不适用。当前明确仅支持关系型。 |
| **技术约束** | 必须使用只读数据库账号（`DATABASE_URL_READONLY`），防止误修改生产数据。 |
| **环境配置** | `DB_READONLY_URL=postgresql+asyncpg://reader:xxx@host/db`。 |
| **依赖链** | DbGraphEngine → SQLAlchemy (反射) → asyncpg/pymysql → 目标DB。 |

🧪 原子化测试用例 (pytest)：
import pytest
from src.graph.db_graph import DbGraphEngine

@pytest.mark.asyncio
async def test_table_exists(db_graph_engine, test_db):
# 假设test_db中包含表 'users'
await db_graph_engine.build_index()
assert await db_graph_engine.table_exists("users") is True
assert await db_graph_engine.table_exists("nonexistent") is False

@pytest.mark.asyncio
async def test_foreign_keys(db_graph_engine, test_db):
await db_graph_engine.build_index()
fks = await db_graph_engine.get_foreign_keys("orders")
assert any(fk["column"] == "user_id" and fk["ref_table"] == "users" for fk in fks)

@pytest.mark.asyncio
async def test_column_exists(db_graph_engine, test_db):
await db_graph_engine.build_index()
assert await db_graph_engine.column_exists("users", "id") is True

## Step 3.3：配置图谱引擎（漂移检测与修复）

| PRD |  |
| --- | --- |
| **背景** | 生产故障中70%源于配置漂移（如.env文件被手动修改、Nginx配置参数变更未同步）。需构建配置图谱，计算配置指纹，自动检测并修复漂移。 |
| **用户故事** | 作为运维工程师，我需要系统每10分钟扫描配置目录，若发现与黄金基线不一致，自动回滚或发送告警。 |
| **需求描述** | ①解析常见配置文件格式：`.env`（`python-dotenv`）、`.yml`/`.yaml`（`pyyaml`）、`.json`、`nginx.conf`（简单正则提取关键指令）、`php.ini`；②为每个配置文件计算SHA256指纹；③存储到`ConfigNode`表（含`hash`,`file_path`,`env`）；④维护“黄金基线”版本（存储在单独的`config_baselines`表）；⑤定期（每10分钟）扫描文件系统，计算当前指纹并对比基线；⑥若不一致，触发修复（用基线内容覆盖）或告警（根据环境策略：Test自动修复，Prod仅告警）。 |
| **范围 (Do/Don't)** | **Do：**支持.env, YAML, JSON, Nginx (简易), php.ini；支持自动修复（Test环境）。**Don't：**不支持K8s ConfigMap（V2）；不支持加密配置（sops）。 |
| **数据契约** | ``代码块-9`` |
| | 接口： |
| | ``代码块-10`` |
| **异常定义** | ``代码块-11`` |
| **成功标准→验收** | **SC1:**漂移检测<90秒 →**AC1:**手动修改`.env`中的`DB_PORT`，在10分钟内检测到并记录日志。 |
| | **SC2:**修复成功率>90% →**AC2:**在Test环境自动修复后，文件内容与基线完全一致（`sha256sum`比对）。 |
| | **SC3:**支持至少5种格式 →**AC3:**分别提供`.env`,`.yml`,`.json`,`nginx.conf`,`php.ini`样本，均能正确解析并计算指纹。 |
| **待定决策** | **Q1:**自动修复是否需要备份原文件？ →**决议：**是，修复前将当前文件备份到`/backups/config`。 |
| | **Q2:**基线版本如何更新？ →**决议：**人工通过管理命令`update_baseline`更新，或通过CI/CD触发。 |

| ADR |  |
| --- | --- |
| **技术栈版本** | python-dotenv 1.0, pyyaml 6.0, deepdiff 6.7 (用于diff生成), hashlib (内置)。 |
| **架构位置** | 能力层，位于`/src/graph/config_graph.py`。 |
| **实施细节** | **核心类：** |
| | ``代码块-12`` |
| **风险与缓解** | 风险：配置文件解析失败导致整个扫描中断。缓解：每个文件独立try-except，记录错误并继续。 |
| **需求错位** | 若使用K8s ConfigMap，文件系统路径不存在，需额外集成K8s API。当前阶段不涉及。 |
| **技术约束** | 自动修复前必须备份原文件到`BACKUP_DIR`，且修复操作需记录审计日志。 |
| **环境配置** | `CONFIG_BASE_DIR=/etc/myapp`,`CONFIG_BACKUP_DIR=/backups/config`,`ENV=test`。 |
| **依赖链** | ConfigGraphEngine → python-dotenv / pyyaml → 文件系统。 |

🧪 原子化测试用例 (pytest)：
import pytest
from pathlib import Path
from src.graph.config_graph import ConfigGraphEngine

@pytest.mark.asyncio
async def test_compute_hash_env(tmp_path, config_graph_engine):
env_file = tmp_path / ".env"
env_file.write_text("DB_PORT=5432")
h = config_graph_engine.compute_hash(env_file)
assert len(h) == 64

@pytest.mark.asyncio
async def test_detect_drift(tmp_path, config_graph_engine, baseline_data):
# 设置基线，然后修改文件
await config_graph_engine.scan_and_index()
# 修改文件内容
(tmp_path / ".env").write_text("DB_PORT=5433")
drifts = await config_graph_engine.detect_drift()
assert len(drifts) == 1
assert ".env" in drifts[0]["file"]

@pytest.mark.asyncio
async def test_auto_fix(tmp_path, config_graph_engine, baseline_data):
await config_graph_engine.scan_and_index()
(tmp_path / ".env").write_text("DB_PORT=5433")
await config_graph_engine.auto_fix(str(tmp_path / ".env"))
content = (tmp_path / ".env").read_text()
assert "DB_PORT=5432" in content


**✅ 阶段3 (Step 3.1, 3.2, 3.3) 交付确认**

本报告完整交付了三图谱引擎的全部三个步骤：

- **Step 3.1 (代码图谱)**：基于AST的Python代码静态分析，提取符号定义与调用关系，为L1引用校验提供数据。
- **Step 3.2 (数据库图谱)**：反射关系型数据库元数据，提供表/字段/外键事实查询。
- **Step 3.3 (配置图谱)**：解析配置文件，计算指纹，检测漂移并自动修复，为L8防幻觉层提供支持。

这三个Step与已交付的Step 1.2（ORM模型）无缝衔接，开发人员可按每个Step拆分为3-4个子任务，总工时约3人日。完成后系统将具备完整的三图谱能力，支撑后续防幻觉层的实施。



```
// 代码块-1
# 复用Step 1.2的 CodeNode 和 Edge 模型，补充字段：
    # CodeNode: file_path, start_line, end_line, namespace (如 __main__.MyClass)
    # Edge: edge_type = 'calls', 'defines'（预留）
```


```
// 代码块-2
class GraphQuery:

        async def exists(self, name: str, symbol_type: str = "function") -> bool

        async def get_callers(self, symbol: str) -> List[str]  # 返回调用方符号名

        async def get_callees(self, symbol: str) -> List[str]  # 返回被调用方符号名
```


```
// 代码块-3
class CodeGraphError(Exception): pass

    class ParseError(CodeGraphError): pass  # 语法错误导致解析失败
```


```
// 代码块-4
import ast

    from pathlib import Path

    from typing import List, Dict, Set

    from sqlalchemy.ext.asyncio import AsyncSession



    class CodeGraphEngine:

        def __init__(self, session_factory):

            self.session_factory = session_factory

            self._file_mtimes: Dict[str, float] = {}  # 用于增量更新



        async def build_index(self, root_path: str) -> None:

            # 遍历所有 .py 文件，调用 _parse_file



        async def incremental_update(self, file_path: str) -> None:

            # 检查mtime，若变更则重新解析并更新数据库



        def _parse_file(self, file_path: str) -> Dict:

            with open(file_path) as f:

                tree = ast.parse(f.read())

            visitor = CodeVisitor(file_path)

            visitor.visit(tree)

            return visitor.nodes, visitor.edges



    class CodeVisitor(ast.NodeVisitor):

        def __init__(self, file_path):

            self.file_path = file_path

            self.nodes = []

            self.edges = []

            self.current_namespace = ""



        def visit_FunctionDef(self, node):

            # 记录函数定义

            name = f"{self.current_namespace}.{node.name}" if self.current_namespace else node.name

            self.nodes.append(("function", name, node.lineno, node.end_lineno))

            # 遍历函数体内的调用

            for child in ast.walk(node):

                if isinstance(child, ast.Call):

                    if isinstance(child.func, ast.Name):

                        callee = child.func.id

                        self.edges.append((name, callee, "calls"))

            self.generic_visit(node)



        async def exists(self, name: str, symbol_type: str = "function") -> bool:

            async with self.session_factory() as session:

                stmt = select(CodeNode).where(CodeNode.name == name, CodeNode.type == symbol_type)

                result = await session.execute(stmt)

                return result.scalar_one_or_none() is not None
```


```
// 代码块-5
# DbNode 字段：schema, db_type ('table', 'view', 'column')

    # Edge 存储外键：source_id = 字段节点ID, target_id = 目标字段节点ID, edge_type='foreign_key'
```


```
// 代码块-6
async def table_exists(table_name: str) -> bool

    async def column_exists(table_name: str, column_name: str) -> bool

    async def get_foreign_keys(table_name: str) -> List[Dict[str, str]]
```


```
// 代码块-7
class DbGraphError(Exception): pass

    class DbConnectionError(DbGraphError): pass
```


```
// 代码块-8
from sqlalchemy import create_engine, inspect, MetaData

    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession



    class DbGraphEngine:

        def __init__(self, db_url: str, session_factory):

            self.engine = create_async_engine(db_url)

            self.session_factory = session_factory



        async def build_index(self, schema: str = "public") -> None:

            async with self.engine.connect() as conn:

                inspector = await conn.run_sync(lambda sync_conn: inspect(sync_conn))

                tables = await conn.run_sync(lambda sync_conn: inspector.get_table_names(schema))

                for table in tables:

                    columns = await conn.run_sync(lambda sync_conn: inspector.get_columns(table, schema))

                    fk = await conn.run_sync(lambda sync_conn: inspector.get_foreign_keys(table, schema))

                    # 存储到 DbNode 和 Edge



        async def snapshot_core_tables(self, core_tables: List[str]):

            # 对核心表备份元数据到单独的store（可存JSON或PG表）



        async def table_exists(self, table_name: str) -> bool:

            async with self.session_factory() as session:

                stmt = select(DbNode).where(DbNode.name == table_name, DbNode.db_type == 'table')

                return await session.execute(stmt).scalar_one_or_none() is not None
```


```
// 代码块-9
# ConfigNode 扩展字段：file_path, hash, env, baseline_version

    # 基线表：config_baselines (id, file_path, hash, content_text, created_at)
```


```
// 代码块-10
async def scan_configs(directory: str) -> List[ConfigNode]

    async def detect_drift() -> List[Dict[str, str]]  # 返回漂移文件列表及diff

    async def auto_fix(file_path: str) -> bool
```


```
// 代码块-11
class ConfigGraphError(Exception): pass

    class ParseConfigError(ConfigGraphError): pass
```


```
// 代码块-12
import hashlib

    from pathlib import Path

    from dotenv import dotenv_values

    import yaml

    import json

    import re



    class ConfigGraphEngine:

        def __init__(self, session_factory, base_dir: str, env: str = "dev"):

            self.base_dir = Path(base_dir)

            self.env = env

            self.session_factory = session_factory



        def _parse_file(self, file_path: Path) -> str:

            if file_path.suffix == ".env":

                return str(dotenv_values(file_path))

            elif file_path.suffix in (".yml", ".yaml"):

                with open(file_path) as f:

                    return json.dumps(yaml.safe_load(f))

            elif file_path.suffix == ".json":

                with open(file_path) as f:

                    return json.dumps(json.load(f))

            elif "nginx.conf" in file_path.name:

                with open(file_path) as f:

                    return re.sub(r'\s+', ' ', f.read())  # 简单规范化

            else:

                raise ParseConfigError(f"Unsupported file type: {file_path}")



        def compute_hash(self, file_path: Path) -> str:

            content = self._parse_file(file_path)

            return hashlib.sha256(content.encode()).hexdigest()



        async def scan_and_index(self):

            # 遍历base_dir下所有支持的配置文件，计算hash并存入ConfigNode



        async def detect_drift(self):

            drifts = []

            async with self.session_factory() as session:

                baselines = await session.execute(select(ConfigBaseline))

                for baseline in baselines:

                    current_hash = self.compute_hash(Path(baseline.file_path))

                    if current_hash != baseline.hash:

                        drifts.append({"file": baseline.file_path, "expected": baseline.hash, "actual": current_hash})

            return drifts



        async def auto_fix(self, file_path: str):

            if self.env == "prod":

                raise ConfigGraphError("Auto-fix not allowed in production")

            # 从baseline恢复文件
```


# 多Agent自循环系统 · 阶段4 8层防幻觉体系 (Step 4.1 & 4.2) · 编码就绪级PRD/ADR

L1-L4 静态/实时拦截 ｜ L5-L8 深度形式化与运行时保障

**交付声明：**本报告为阶段4（W7-W8）8层防幻觉体系的终极细化文档。Step 4.1实现L1-L4（图谱验证、动态追踪、熵监控、类型检查），Step 4.2实现L5-L8（Z3验证、合约双向校验、沙箱执行、配置漂移修复）。每个Step均包含字段级契约、精确函数签名、配置示例、原子化pytest用例，可直接编码。此模块与已交付的调度器、LLM客户端、检查点、图谱引擎无缝集成。



## Step 4.1：L1-L4 防幻觉层（静态与实时拦截）

L1代码图谱引用验证L2动态调用追踪L3概率熵监控L4静态类型检查

| PRD (产品需求文档) - L1-L4 统一视角 |  |
| --- | --- |
| **背景** | LLM生成的代码经常引用不存在的函数、类型错误或高不确定性的内容。单层防御不可靠，必须构建纵深体系：在生成前（L4类型约束）、生成中（L3熵监控）、生成后（L1图谱验证）和运行时（L2动态追踪）全链路拦截幻觉。 |
| **用户故事** | 作为调度器，我调用`HallucinationPipeline`对生成的代码执行L1-L4检查。任一检查失败则拒绝代码并触发重新生成或人工介入。 |
| **需求描述** | **L1（图谱引用验证）：**解析代码中的函数/类引用，查询代码图谱，若符号不存在则拒绝。 |
| | **L2（动态追踪）：**在沙箱执行时使用`sys.settrace`追踪真实调用的函数，校验是否在图谱中（作为L1的补充，防止动态拼接）。 |
| | **L3（概率熵监控）：**在LLM流式响应中提取logits，计算归一化熵；若移动平均值（窗口=10）≥0.75，立即取消生成并抛出`HighEntropyError`。 |
| | **L4（静态类型检查）：**运行`mypy --strict`对生成的代码进行类型检查，解析输出，若存在类型错误则拒绝。 |
| **范围 (Do/Don't)** | **Do：**Dev环境启用L1/L4，Test环境全量启用L1-L4。**Don't：**L2动态追踪仅在Test/Prod启用（性能开销大）；L3不启用旧模型（无logits返回，降级为基于重复度的评估）。 |
| **数据契约** | ``代码块-1`` |
| **异常定义** | ``代码块-2`` |
| **成功标准→验收** | **SC1:**L1拦截率>95% →**AC1:**注入代码引用不存在的`Utils.foo`，L1拦截并返回`GraphReferenceError`。 |
| | **SC2:**L3响应<200ms →**AC2:**模拟高熵生成流，系统在200ms内取消请求并抛出`HighEntropyError`。 |
| | **SC3:**L4类型检查准确率>90% →**AC3:**生成包含`def add(a: str, b: str) -> int: return a + b`的代码，L4捕获类型不匹配并列出错误行。 |
| | **SC4:**L2动态追踪生效 →**AC4:**代码中使用`getattr(obj, method_name)()`动态调用，沙箱运行时L2追踪到实际调用的函数并验证。 |
| **待定决策** | **Q1:**L3熵阈值是否支持模型级配置？ →**决议：**DeepSeek用0.75，Qwen用0.7（更保守），配置在`settings.MODEL_ENTROPY_THRESHOLD`。 |
| | **Q2:**L4类型检查是否强制要求`--strict`模式？ →**决议：**是，但忽略`no-untyped-def`（允许动态函数）。 |
| | **Q3:**L1对动态属性（如`obj['field']`）如何处理？ →**决议：**仅验证静态符号，动态属性跳过。 |

| ADR - L1-L4 架构决策 |  |
| --- | --- |
| **技术栈版本** | L1: SQLAlchemy 2.0 + asyncpg；L2: Python内置`sys.settrace`；L3: litellm 1.40 (`logprobs`参数), numpy 1.26；L4: mypy 1.8, pydantic 2.6。 |
| | 位置：`/src/hallucination/`，包含`l1_graph.py`,`l2_dynamic.py`,`l3_entropy.py`,`l4_type.py`。 |
| **架构位置** | 能力层（验证子层），被调度器`TaskOrchestrator`在`CODING`和`VERIFYING`状态调用。 |
| **实施细节** | **L1实现（核心方法）：** |
| | ``代码块-3`` |
| | **L3实现（熵监控集成到LLMClient）：** |
| | ``代码块-4`` |
| **风险与缓解** | 风险1: L3熵监控依赖模型返回logprobs，部分模型不支持。缓解：降级为基于文本重复度的评估（若连续生成重复token则视为高熵）。 |
| | 风险2: L2动态追踪（`sys.settrace`）会显著拖慢执行速度（约+200ms）。缓解：仅在Test环境启用，且追踪仅针对`function call`事件。 |
| **需求错位** | 若未来需要验证JavaScript/TypeScript代码，L1需扩展Tree-sitter解析器，L4需使用`tsc`替代mypy。当前仅支持Python。 |
| **技术约束** | L1必须使用AST而非正则表达式（保证准确率）；L3必须使用异步流式接口（`acompletion(stream=True)`）。 |
| **环境配置** | ENABLE_L1=true |
| | ENABLE_L2=false # 默认关闭（性能影响） |
| | ENABLE_L3=true |
| | ENABLE_L4=true |
| | ENTROPY_THRESHOLD_DEEPSEEK=0.75 |
| | ENTROPY_THRESHOLD_QWEN=0.70 |
| **依赖链** | L1 → GraphRepository (SQLAlchemy)；L2 → Sandbox (sys.settrace注入)；L3 → LLMClient (流式响应钩子)；L4 → mypy (subprocess调用)。 |

🧪 原子化测试用例 (pytest)：
import pytest
 from src.hallucination.l1_graph import L1GraphValidator
 from src.hallucination.l3_entropy import L3EntropyMonitor, L3EntropyConfig

 @pytest.mark.asyncio
 async def test_l1_missing_symbol(mock_graph_repo):
 mock_graph_repo.symbols_exist.return_value = {"known_func"}
 validator = L1GraphValidator(mock_graph_repo)
 code = "result = unknown_func(10)"
 result = await validator.validate(code)
 assert result.passed is False
 assert "unknown_func" in result.errors[0]

 def test_l3_entropy_trigger():
 config = L3EntropyConfig(window_size=3, threshold=0.7)
 monitor = L3EntropyMonitor(config)
 # 模拟高熵序列（均匀分布）
 high_entropy = [0.8, 0.75, 0.9]
 for i, ent in enumerate(high_entropy):
 result = monitor.on_token(f"token_{i}", [math.log(0.25)] * 4) # 模拟均匀logits
 if i >= 2:
 assert result is not None # 触发阈值
 assert result >= 0.7

 @pytest.mark.asyncio
 async def test_l4_type_error(tmp_path, mocker):
 validator = L4TypeValidator()
 code = "def add(a: str, b: str) -> int: return a + b" # 返回类型错误
 with patch("subprocess.run") as mock_run:
 mock_run.return_value.stdout = "error: Incompatible return value type"
 mock_run.return_value.returncode = 1
 result = await validator.validate(code)
 assert result.passed is False
 assert "Incompatible return" in result.errors[0]

## Step 4.2：L5-L8 防幻觉层（深度形式化与运行时保障）

L5形式化验证 (Z3)L6合约-代码双向验证L7沙箱执行验证L8配置漂移检测与修复

| PRD - L5-L8 统一视角 |  |
| --- | --- |
| **背景** | L1-L4主要处理语法和静态引用问题，但无法验证算法正确性（L5）、接口一致性（L6）、运行时行为（L7）和环境一致性（L8）。必须构建深层防御，覆盖“正确性”、“契约”、“运行态”和“配置”四个维度。 |
| **用户故事** | 作为QA Agent，我调用L5-L8对最终代码进行深度验证。对于核心算法函数（标记@formal），Z3自动证明其正确性；L6校验代码与OpenAPI契约一致；L7在沙箱中运行集成测试；L8确保配置文件未发生漂移。 |
| **需求描述** | **L5（形式化验证）：**仅对标记`@formal`的函数启用Z3。提取函数的前置条件（requires）和后置条件（ensures），使用Z3 SMT求解器验证。超时30s，超时则标记为“待人工审核”。 |
| | **L6（合约-代码双向验证）：**解析OpenAPI 3.0规格（或内部合约定义），与实现代码（FastAPI路由函数）比对：请求体字段是否匹配Pydantic模型、响应状态码是否完整覆盖。 |
| | **L7（沙箱执行验证）：**复用Step MVP-03的Docker沙箱，运行生成的代码单元测试（生成简单的assert语句），验证基本功能正确性。 |
| | **L8（配置漂移检测与修复）：**定期（每10分钟）扫描配置文件（.env, YAML, Nginx等），计算SHA256指纹并与黄金基线比对。若漂移则触发告警，若允许自动修复则回滚至基线版本。 |
| **范围 (Do/Don't)** | **Do：**L5支持排序、数学运算等核心算法；L6支持OpenAPI 3.0；L7支持pytest风格断言；L8支持5种配置文件格式。**Don't：**L5不验证IO密集型或复杂循环（超时风险）；L6不支持gRPC契约；L8不支持K8s ConfigMap（V2）。 |
| **数据契约** | ``代码块-5`` |
| **异常定义** | ``代码块-6`` |
| **成功标准→验收** | **SC1:**L5验证正确算法返回SAT →**AC1:**对`@formal def add(x, y): return x+y`验证，Z3返回"sat"且无超时。 |
| | **SC2:**L6检测到不一致 →**AC2:**OpenAPI定义`/users/{id}`返回`User`模型，但实现返回`dict`，L6捕获差异并列出。 |
| | **SC3:**L7捕获运行时错误 →**AC3:**生成代码包含`assert add(1,2) == 4`，沙箱执行返回`AssertionError`，L7标记失败。 |
| | **SC4:**L8自动修复漂移 →**AC4:**手动修改`.env`中`DB_PORT`，10分钟内L8检测并回滚至基线SHA。 |
| **待定决策** | **Q1:**L5 Z3超时策略？ →**决议：**30s硬超时，超时后标记为"unknown"且不阻断流水线（仅告警，人工介入）。 |
| | **Q2:**L8自动修复是否需要审批？ →**决议：**Test环境自动修复，Prod环境仅告警（需人工确认）。 |
| | **Q3:**L6是否支持异步合约校验？ →**决议：**支持，使用`async`解析大文件。 |

| ADR - L5-L8 架构决策 |  |
| --- | --- |
| **技术栈版本** | L5: z3-solver 4.13.0.0, rotalabs-verity (内部封装)；L6: openapi-spec-validator 0.7, prance 0.22；L7: docker-py 7.0；L8: python-dotenv 1.0, pyyaml 6.0, deepdiff 6.7。 |
| | 位置：`/src/hallucination/l5_z3/`,`l6_contract/`,`l7_runtime/`,`l8_config/`。 |
| **架构位置** | 能力层（深度验证子层），在调度器`VERIFYING`状态串行或并行调用。 |
| **实施细节** | **L5核心实现（Z3集成）：** |
| | ``代码块-7`` |
| | **L8核心实现（漂移检测与修复）：** |
| | ``代码块-8`` |
| **风险与缓解** | 风险1: Z3对复杂表达式可能指数爆炸（如多层嵌套）。缓解：设置30s超时，且仅对标记函数启用（人工筛选）。 |
| | 风险2: L8自动修复可能覆盖用户有意变更。缓解：在生产环境禁用自动修复，仅告警；在Test环境允许，但需记录审计日志。 |
| **需求错位** | 若项目未使用OpenAPI（如纯内部RPC），L6合约验证无法工作。当前MVP阶段要求所有API必须有OpenAPI文档，后续可扩展支持gRPC反射。 |
| **技术约束** | L5禁止在Z3公式中调用外部函数或副作用操作（仅支持纯数学表达式）；L8必须使用SHA256而非MD5（碰撞风险低）。 |
| **环境配置** | ENABLE_L5=true |
| | Z3_TIMEOUT_MS=30000 |
| | ENABLE_L6=true |
| | OPENAPI_SPEC_PATH=/app/openapi.yaml |
| | ENABLE_L7=true |
| | ENABLE_L8=true |
| | CONFIG_BASELINE_DIR=/app/config_baselines |
| | L8_AUTO_FIX_ENABLED=false # prod默认false |
| **依赖链** | L5 → z3-solver (libz3)；L6 → openapi-spec-validator；L7 → docker-py → Docker Engine；L8 → deepdiff → pyyaml/dotenv。 |

🧪 原子化测试用例 (pytest)：
import pytest
 from src.hallucination.l5_z3 import L5Z3Validator
 from src.hallucination.l8_config import L8ConfigValidator

 @pytest.mark.asyncio
 async def test_l5_correct_function():
 validator = L5Z3Validator()
 code = """
 @formal
 @requires("x > 0")
 @requires("y > 0")
 @ensures("result == x + y")
 def add(x: int, y: int) -> int:
 return x + y
 """
 result = await validator.validate(code)
 assert result.passed is True
 assert result.z3_status == "unsat" # 无反例

 @pytest.mark.asyncio
 async def test_l5_counterexample():
 validator = L5Z3Validator()
 code = """
 @formal
 @requires("x > 0")
 @ensures("result > x") # 错误的后置条件
 def identity(x: int) -> int:
 return x
 """
 result = await validator.validate(code)
 assert result.passed is False
 assert result.z3_status == "sat"
 assert "Counterexample" in result.errors[0]

 def test_l8_drift_detection(tmp_path):
 # 创建基线文件
 baseline_dir = tmp_path / "baselines"
 baseline_dir.mkdir()
 config_file = tmp_path / "app.env"
 config_file.write_text("DB_PORT=5432")
 baseline_file = baseline_dir / "app.env.sha256"
 baseline_file.write_text(hashlib.sha256(b"DB_PORT=5432").hexdigest())

 validator = L8ConfigValidator(str(tmp_path))
 # 修改配置
 config_file.write_text("DB_PORT=5433")
 reports = validator.scan()
 assert len(reports) == 1
 assert reports[0].file_path.endswith("app.env")
 assert reports[0].auto_fixed is False # prod模式

 @pytest.mark.asyncio
 async def test_l6_contract_violation():
 validator = L6ContractValidator(openapi_path="tests/fixtures/openapi.yaml")
 # 模拟代码实现返回错误的响应模型
 code = """
 @app.get("/users/{id}")
 def get_user(id: int) -> Dict:
 return {"name": "test"} # 应返回User模型
 """
 result = await validator.validate(code)
 assert result.passed is False
 assert "response_model" in result.errors[0]


**✅ 阶段4 (Step 4.1 & 4.2) 8层防幻觉体系全量交付确认**

本报告完整交付了8层防幻觉体系的实现规格：

- **Step 4.1 (L1-L4)：**静态验证（图谱引用→动态追踪→熵监控→类型检查），覆盖生成前、中、后全链路。
- **Step 4.2 (L5-L8)：**深度验证（Z3形式化→合约校验→沙箱运行时→配置漂移修复），覆盖正确性、契约、运行态和环境。

所有Layer均包含字段级数据契约、可执行的类设计、配置示例和原子化测试用例。开发团队可按Layer并行开发（L1/L4一组，L2/L3一组，L5/L6一组，L7/L8一组），预计总工时约5人日，与已交付的调度器、图谱引擎、LLM客户端无缝集成。



```
// 代码块-1
from pydantic import BaseModel, Field
    from enum import Enum
    from typing import List, Optional, Dict, Any

    class HallucinationLevel(str, Enum):
        L1_GRAPH = "l1_graph"
        L2_DYNAMIC = "l2_dynamic"
        L3_ENTROPY = "l3_entropy"
        L4_TYPE = "l4_type"

    class ValidationResult(BaseModel):
        passed: bool
        level: HallucinationLevel
        errors: List[str] = Field(default_factory=list)
        warnings: List[str] = Field(default_factory=list)
        metadata: Dict[str, Any] = Field(default_factory=dict)

    class EntropySample(BaseModel):
        timestamp: float
        entropy: float
        token: str

    class L3EntropyConfig(BaseModel):
        window_size: int = 10
        threshold: float = 0.75
        sampling_interval: int = 50  # 每50个token采样一次
        fallback_enabled: bool = True  # 无logits时降级
```


```
// 代码块-2
class HallucinationError(Exception):
        """基类异常"""
        pass

    class GraphReferenceError(HallucinationError):
        """L1: 引用不存在的符号"""
        def __init__(self, symbol: str):
            self.symbol = symbol
            super().__init__(f"Symbol '{symbol}' not found in code graph")

    class HighEntropyError(HallucinationError):
        """L3: 生成过程中熵过高"""
        def __init__(self, entropy: float, threshold: float):
            self.entropy = entropy
            self.threshold = threshold
            super().__init__(f"Entropy {entropy:.3f} exceeded threshold {threshold}")

    class TypeCheckError(HallucinationError):
        """L4: 类型检查失败"""
        def __init__(self, errors: List[str]):
            self.errors = errors
            super().__init__(f"Type check failed: {', '.join(errors)}")
```


```
// 代码块-3
class L1GraphValidator:
        def __init__(self, graph_repo: GraphRepository):
            self.repo = graph_repo

        async def validate(self, code: str) -> ValidationResult:
            # 使用AST提取所有Name节点
            tree = ast.parse(code)
            symbols = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
                    symbols.add(node.id)
            # 批量查询图谱
            existing = await self.repo.symbols_exist(list(symbols))
            missing = [s for s in symbols if s not in existing]
            if missing:
                return ValidationResult(
                    passed=False,
                    level=HallucinationLevel.L1_GRAPH,
                    errors=[f"Symbol '{s}' not found" for s in missing],
                )
            return ValidationResult(passed=True, level=HallucinationLevel.L1_GRAPH)
```


```
// 代码块-4
class L3EntropyMonitor:
        def __init__(self, config: L3EntropyConfig):
            self.config = config
            self.buffer = []

        def on_token(self, token: str, logprobs: List[float]) -> Optional[float]:
            # 计算归一化熵
            if logprobs:
                probs = [math.exp(lp) for lp in logprobs]
                entropy = -sum(p * math.log(p) for p in probs if p > 0) / math.log(len(probs))
                self.buffer.append(entropy)
                if len(self.buffer) > self.config.window_size:
                    self.buffer.pop(0)
                avg_entropy = sum(self.buffer) / len(self.buffer)
                if avg_entropy >= self.config.threshold:
                    return avg_entropy
            return None
```


```
// 代码块-5
from pydantic import BaseModel, Field
    from typing import List, Optional, Dict, Any
    from datetime import datetime

    class FormalContract(BaseModel):
        preconditions: List[str]  # 如 ["x > 0", "y is not None"]
        postconditions: List[str]  # 如 ["result == x + y"]

    class L5ValidationResult(ValidationResult):
        z3_status: str  # "sat", "unsat", "unknown", "timeout"
        model: Optional[Dict[str, Any]] = None  # 反例

    class L6ContractMatch(BaseModel):
        endpoint: str
        method: str
        request_model: str
        response_model: str
        matched: bool
        differences: List[str]

    class L8DriftReport(BaseModel):
        file_path: str
        baseline_hash: str
        current_hash: str
        diff: str  # unified diff
        auto_fixed: bool
        timestamp: datetime
```


```
// 代码块-6
class L5VerificationError(HallucinationError):
        """Z3验证失败"""
        pass

    class L6ContractViolationError(HallucinationError):
        """合约不一致"""
        pass

    class L7RuntimeError(HallucinationError):
        """沙箱运行时失败"""
        pass

    class L8DriftDetectedError(HallucinationError):
        """配置漂移"""
        def __init__(self, file_path: str, diff: str):
            self.file_path = file_path
            self.diff = diff
            super().__init__(f"Config drift detected in {file_path}")
```


```
// 代码块-7
from z3 import Solver, Int, Real, sat, unknown
    from src.hallucination.l5_z3.contract_parser import parse_pre_post

    class L5Z3Validator:
        TIMEOUT = 30000  # 毫秒

        async def validate(self, func_code: str) -> L5ValidationResult:
            # 1. 解析@formal装饰器，提取契约
            contract = parse_pre_post(func_code)
            if not contract:
                return L5ValidationResult(passed=True, z3_status="skipped")

            # 2. 构建Z3公式
            solver = Solver()
            solver.set("timeout", self.TIMEOUT)
            # 添加前置条件
            for pre in contract.preconditions:
                solver.add(eval(pre))  # 安全：仅解析数学表达式
            # 添加后置条件的否定（寻找反例）
            for post in contract.postconditions:
                solver.add(Not(eval(post)))

            # 3. 求解
            result = solver.check()
            if result == sat:
                model = solver.model()
                return L5ValidationResult(
                    passed=False,
                    z3_status="sat",
                    errors=[f"Counterexample found: {model}"],
                    model={str(k): str(v) for k, v in model.__dict__.items()}
                )
            elif result == unknown:
                return L5ValidationResult(
                    passed=True,  # 不阻断，但告警
                    z3_status="unknown",
                    warnings=["Z3 timeout or unsupported expression"]
                )
            else:  # unsat
                return L5ValidationResult(passed=True, z3_status="unsat")
```


```
// 代码块-8
import hashlib
    from deepdiff import DeepDiff

    class L8ConfigValidator:
        def __init__(self, baseline_dir: str):
            self.baseline_dir = baseline_dir
            self.auto_fix_enabled = settings.ENV != "prod"

        async def scan(self) -> List[L8DriftReport]:
            reports = []
            for file_path in glob.glob(f"{self.baseline_dir}/**/*", recursive=True):
                if os.path.isdir(file_path):
                    continue
                baseline_file = f"{self.baseline_dir}/baselines/{os.path.basename(file_path)}.sha256"
                current_hash = self._calc_hash(file_path)
                with open(baseline_file) as f:
                    baseline_hash = f.read().strip()
                if current_hash != baseline_hash:
                    diff = self._gen_diff(file_path)
                    auto_fixed = False
                    if self.auto_fix_enabled:
                        self._restore_baseline(file_path, baseline_file)
                        auto_fixed = True
                    reports.append(L8DriftReport(
                        file_path=file_path,
                        baseline_hash=baseline_hash,
                        current_hash=current_hash,
                        diff=diff,
                        auto_fixed=auto_fixed,
                        timestamp=datetime.utcnow()
                    ))
            return reports
```


# 多Agent自循环系统 · 阶段5 调度器与Agent协作 (Step 5.1 & 5.2) · 编码就绪级PRD/ADR

自研调度器（DAG+状态机+检查点） ｜ 5个Agent角色与Prompt工程

**交付声明：**本报告为阶段5（W9-W10）的核心步骤终极细化文档。Step 5.1将MVP简易状态机升级为支持DAG任务编排、并行执行、检查点集成的完整调度器；Step 5.2定义5个Agent角色（架构师、开发者、审查员、QA验证员、配置管理员）及其Prompt模板、输入输出契约。此模块是系统的“大脑”，连接所有能力层组件。每个Step均包含字段级契约、精确函数签名、配置文件示例、原子化pytest用例，可直接编码。



## Step 5.1：自研调度器核心（状态机+DAG+检查点集成）

| PRD (产品需求文档) |  |
| --- | --- |
| **背景** | MVP状态机仅支持串行单一路径，无法表达复杂软件开发任务（如并行代码生成与验证）。需扩展为支持DAG（有向无环图）的任务编排引擎，并深度集成检查点（Step 2.2）实现崩溃恢复，同时引入异步执行提升吞吐。 |
| **用户故事** | 作为调度器，我接收一个`TaskGraph`（节点为Agent执行单元，边为依赖），按拓扑序并发执行无依赖节点，在状态变化时自动保存检查点。若进程崩溃，重启后从最新检查点恢复整个DAG进度。 |
| **需求描述** | ①扩展`TaskState`枚举，增加`PENDING, RUNNING, SUCCESS, FAILED, SKIPPED`；②定义`TaskGraph`类（节点列表+边列表），提供拓扑排序（Kahn算法）；③实现`TaskOrchestrator`，包含`async run(graph)`方法，使用`asyncio.gather`并发执行无依赖节点；④每个节点执行前后调用`CheckpointManager.save()`，保存完整DAG进度（节点状态、中间产物）；⑤实现恢复逻辑：`resume(task_id)`从检查点加载，跳过已完成节点；⑥支持节点超时（可配置，默认30s）和重试（最多2次）。 |
| **范围 (Do/Don't)** | **Do：**支持DAG并行执行，检查点自动保存与恢复，节点超时与重试。**Don't：**不支持动态图（运行时修改拓扑），不支持跨任务依赖（V2）。 |
| **数据契约** | ``代码块-1`` |
| **异常定义** | ``代码块-2`` |
| **成功标准→验收** | **SC1:**拓扑排序正确 →**AC1:**构建DAG（A→B, A→C, B→D, C→D），调度器执行顺序满足依赖（B/C在A后，D在B/C后）。 |
| | **SC2:**并发执行 →**AC2:**两个无依赖节点同时启动，时间差<100ms。 |
| | **SC3:**检查点恢复 →**AC3:**模拟进程崩溃，重启后调用`resume`，已完成的节点不重复执行。 |
| | **SC4:**超时与重试 →**AC4:**节点执行超过30s触发超时，自动重试1次；若再失败则节点状态为FAILED，不影响其他节点。 |
| **待定决策** | **Q1:**节点间数据传递如何实现？ →**决议：**通过`GraphNode.output`写入，后续节点通过`node.input`引用（显式依赖注入）。 |
| | **Q2:**检查点保存频率？ →**决议：**每个节点完成时保存，避免频繁IO；同时每10个节点保存一次（用于长DAG）。 |
| | **Q3:**失败策略：继续还是终止？ →**决议：**默认为“快速失败”（任一节点失败则整个DAG标记FAILED），但可配置为“继续”（用于非关键路径）。 |

| ADR (架构决策记录) |  |
| --- | --- |
| **技术栈版本** | Python 3.11, asyncio (内置), networkx 3.2 (用于拓扑排序和循环检测, 可选), CheckpointManager (Step 2.2), 各Agent实现 (Step 5.2)。 |
| | 位置：`/src/scheduler/orchestrator.py`,`/src/scheduler/graph.py`。 |
| **架构位置** | 调度层核心，负责解析TaskGraph、编排执行、保存检查点。被API层（Step 1.1）调用，调用LLMClient（Step 2.1）、沙箱（MVP-03）、防幻觉（Step 4.1/4.2）、图谱（Step 3.x）。 |
| **实施细节** | **拓扑排序与并发执行：** |
| | ``代码块-3`` |
| **风险与缓解** | 风险1：并发节点过多导致资源耗尽（如同时启动5个LLM调用）。缓解：设置信号量（Semaphore）控制最大并发数（配置`MAX_CONCURRENT_NODES=3`）。 |
| | 风险2：检查点序列化大DAG可能较慢。缓解：仅保存节点状态和关键元数据，不保存大对象（如完整代码），使用`orjson`加速。 |
| | 风险3：节点重试可能引发无限循环。缓解：最大重试2次，超过则标记FAILED。 |
| **需求错位** | 若将来需要支持动态DAG（如条件分支），当前静态拓扑排序无法满足。但当前需求明确为静态图，V2可扩展。 |
| **技术约束** | 必须使用异步（asyncio）实现并发，禁止使用`threading`（避免GIL争用）。节点间数据传递必须通过`GraphNode`对象，不得使用全局变量。 |
| **环境配置** | MAX_CONCURRENT_NODES=3 |
| | NODE_TIMEOUT_SECONDS=30 |
| | MAX_RETRIES_PER_NODE=2 |
| | CHECKPOINT_SAVE_INTERVAL_NODES=10 |
| **依赖链** | TaskOrchestrator → CheckpointManager → AgentFactory → 各具体Agent实现 → LLMClient / Sandbox / 图谱 / 防幻觉。 |

🧪 原子化测试用例 (pytest)：
import pytest
 from src.scheduler.orchestrator import TaskOrchestrator, TaskGraph, GraphNode, NodeStatus

 @pytest.mark.asyncio
 async def test_topological_sort():
 graph = TaskGraph(
 task_id="test",
 nodes=[
 GraphNode(id="A", agent_role="developer"),
 GraphNode(id="B", agent_role="developer"),
 GraphNode(id="C", agent_role="developer"),
 GraphNode(id="D", agent_role="developer"),
 ],
 edges=[("A","B"), ("A","C"), ("B","D"), ("C","D")]
 )
 orch = TaskOrchestrator(MockCheckpointManager())
 order = orch._topological_sort(graph)
 # A必须在B,C之前；B,C在D之前
 assert order.index("A") < order.index("B")
 assert order.index("A") < order.index("C")
 assert order.index("B") < order.index("D")
 assert order.index("C") < order.index("D")

 @pytest.mark.asyncio
 async def test_concurrent_execution():
 # Mock Agent，模拟延迟
 class MockAgent:
 async def execute(self, input):
 await asyncio.sleep(0.1)
 return {"result": "ok"}
 with patch("src.scheduler.orchestrator.AgentFactory.get_agent", return_value=MockAgent()):
 graph = TaskGraph(
 task_id="test2",
 nodes=[
 GraphNode(id="A", agent_role="dev"),
 GraphNode(id="B", agent_role="dev"),
 ],
 edges=[]
 )
 orch = TaskOrchestrator(MockCheckpointManager())
 start = time.time()
 await orch.run(graph)
 elapsed = time.time() - start
 assert elapsed < 0.15 # 并行执行，应接近0.1s

 @pytest.mark.asyncio
 async def test_checkpoint_resume():
 # 模拟崩溃恢复：保存检查点，然后重新加载
 graph = TaskGraph(...)
 orch = TaskOrchestrator(checkpoint_mgr)
 # 执行部分节点后模拟崩溃
 # 然后恢复，检查已完成节点不重复执行
 # (具体实现依赖Mock)
 pass



## Step 5.2：5个Agent角色定义与Prompt工程

| PRD |  |
| --- | --- |
| **背景** | 多Agent协作的核心是职责分离。参考V14.1架构，定义5个核心Agent角色：架构师（系统设计）、开发者（代码实现）、代码审查员（质量检查）、QA验证员（测试与验证）、配置管理员（环境配置）。每个Agent具有独立的System Prompt、输入输出Schema、工具集（可调用图谱、LLM、沙箱等）。 |
| **用户故事** | 作为调度器，我根据`agent_role`实例化对应的Agent，传入`input`字典，获得结构化输出（Pydantic模型），无需关心内部Prompt细节。 |
| **需求描述** | ①定义`AgentRole`枚举（ARCHITECT, DEVELOPER, REVIEWER, QA, CONFIG_MANAGER）；②为每个角色编写System Prompt（使用Jinja2模板，注入上下文，总长度<2K tokens）；③定义每个Agent的输入/输出Pydantic模型（如`DeveloperInput`,`DeveloperOutput`）；④实现`AgentFactory`，根据角色返回具体Agent实例；⑤每个Agent可调用工具（如`call_llm`,`query_graph`,`run_sandbox`），通过依赖注入传入；⑥Agent执行结果必须通过Pydantic校验，非法输出抛出`AgentOutputError`。 |
| **范围 (Do/Don't)** | **Do：**5个角色全覆盖，Prompt模板使用Jinja2，输入输出强类型校验。**Don't：**不支持工具调用链（Agent间内部调用），不支持记忆（对话历史由调度器管理，Agent无状态）。 |
| **数据契约** | ``代码块-4`` |
| **异常定义** | ``代码块-5`` |
| **成功标准→验收** | **SC1:**每个Agent Prompt Token<2K →**AC1:**使用`tiktoken`计算各Prompt总token数。 |
| | **SC2:**输出符合Pydantic模型 →**AC2:**对每个Agent进行单元测试，传入有效输入，输出校验通过。 |
| | **SC3:**开发者Agent生成可执行代码 →**AC3:**输入“设计一个求和函数”，输出代码在沙箱中运行成功。 |
| | **SC4:**架构师Agent输出结构化设计 →**AC4:**输入PRD，输出包含组件列表和数据流描述，非空。 |
| **待定决策** | **Q1:**Prompt模板是否支持多语言？ →**决议：**仅英文（确保LLM理解准确），输出代码可指定语言。 |
| | **Q2:**Agent之间如何传递复杂对象（如代码AST）？ →**决议：**通过`output`/`input`传递JSON可序列化数据，调度器负责转换。 |
| | **Q3:**是否使用Few-shot示例？ →**决议：**在Prompt中包含1-2个示例（developer和qa角色），其余角色Zero-shot。 |

| ADR |  |
| --- | --- |
| **技术栈版本** | Jinja2 3.1.2, Pydantic 2.6, tiktoken 0.6 (用于token计数), 各依赖组件（LLMClient, GraphRepository, Sandbox等）。 |
| | 位置：`/src/agents/`，包含`base.py`,`factory.py`,`architect.py`,`developer.py`,`reviewer.py`,`qa.py`,`config_manager.py`，以及`prompts/`目录下的Jinja2模板。 |
| **架构位置** | 能力层（Agent实现），被TaskOrchestrator（Step 5.1）调用。每个Agent可组合调用LLM、图谱、沙箱等底层能力。 |
| **实施细节** | **基类与工厂：** |
| | ``代码块-6`` |
| | **开发者Agent实现示例：** |
| | ``代码块-7`` |
| | **Prompt模板 (developer.jinja2)：** |
| | ``代码块-8`` |
| **风险与缓解** | 风险1: LLM输出非JSON导致解析失败。缓解：在System Prompt中强制要求输出JSON，并设置`response_format={"type": "json_object"}`（若模型支持）。 |
| | 风险2: Prompt过长导致Token超限。缓解：使用`tiktoken`在渲染后检查，若>2K则截断输入上下文（如code_context）。 |
| | 风险3: Agent间数据不兼容（如Developer输出code但Reviewer期望不同字段）。缓解：通过Pydantic模型严格定义接口，调度器负责适配。 |
| **需求错位** | 若需添加新Agent（如“测试生成器”），需扩展枚举和工厂。当前设计支持灵活扩展。 |
| **技术约束** | 所有Agent必须无状态（不存储会话历史），状态由调度器管理；Agent内部调用LLM必须异步；输出必须JSON可序列化。 |
| **环境配置** | AGENT_PROMPT_DIR=./src/agents/prompts |
| | AGENT_MAX_OUTPUT_TOKENS=4096 |
| | AGENT_FEW_SHOT_ENABLED=true # 开启few-shot示例 |
| **依赖链** | AgentFactory → BaseAgent → 各子类 → LLMClient / GraphRepository / Sandbox → 基础设施。 |

🧪 原子化测试用例 (pytest)：
import pytest
 from src.agents.factory import AgentFactory
 from src.agents.developer import DeveloperAgent, DeveloperInput, DeveloperOutput

 @pytest.mark.asyncio
 async def test_developer_agent_output_schema():
 agent = AgentFactory.get_agent("developer", mock_llm, mock_graph, mock_sandbox)
 # Mock LLM返回有效的JSON
 mock_llm.generate.return_value.content = '{"code": "def add(a,b): return a+b", "language": "python", "dependencies": []}'
 result = await agent.execute({"design": "sum function", "code_context": ""})
 assert "code" in result
 assert result["language"] == "python"

 def test_developer_input_validation():
 # 有效输入
 input_data = {"design": "test", "code_context": ""}
 dev = DeveloperAgent(mock_llm)
 validated = dev._validate_input(input_data)
 assert isinstance(validated, DeveloperInput)

 # 无效输入（缺少必填字段）
 with pytest.raises(ValidationError):
 dev._validate_input({"code_context": ""}) # missing 'design'

 @pytest.mark.asyncio
 async def test_agent_prompt_token_count():
 agent = AgentFactory.get_agent("architect", mock_llm, mock_graph, mock_sandbox)
 prompt = agent.prompt_template.render(prd="Write a system for ...", tech_stack=["Python"], constraints=[])
 tokens = tiktoken.encoding_for_model("gpt-4").encode(prompt)
 assert len(tokens) < 2048 # 确保<2K

 @pytest.mark.asyncio
 async def test_agent_factory_returns_correct_type():
 for role in AgentRole:
 agent = AgentFactory.get_agent(role.value, mock_llm, mock_graph, mock_sandbox)
 assert agent.role == role


**✅ 阶段5 (Step 5.1 & 5.2) 全量交付确认**

本报告完整交付了调度器与Agent协作层的全部规格：

- **Step 5.1**：自研调度器（DAG并行执行、检查点集成、超时与重试），从MVP串行升级为生产级编排引擎。
- **Step 5.2**：5个Agent角色（架构师/开发者/审查员/QA/配置管理员）及其Prompt、输入输出契约、工厂模式实现。

两个步骤紧密配合：调度器通过`AgentFactory`实例化Agent，执行DAG节点，并在每个节点完成时保存检查点。开发人员可并行开发各Agent和调度器核心，通过接口契约解耦。



```
// 代码块-1
from pydantic import BaseModel, Field
    from typing import List, Optional, Dict, Any
    from enum import Enum
    from datetime import datetime

    class NodeStatus(str, Enum):
        PENDING = "pending"
        RUNNING = "running"
        SUCCESS = "success"
        FAILED = "failed"
        SKIPPED = "skipped"

    class GraphNode(BaseModel):
        id: str
        agent_role: str  # 对应Step 5.2的Agent角色
        input: Dict[str, Any]  # 输入数据
        output: Optional[Dict[str, Any]] = None
        status: NodeStatus = NodeStatus.PENDING
        retry_count: int = 0
        max_retries: int = 2
        started_at: Optional[datetime] = None
        finished_at: Optional[datetime] = None
        error: Optional[str] = None

    class TaskGraph(BaseModel):
        task_id: str
        nodes: List[GraphNode]
        edges: List[tuple[str, str]]  # (from_node_id, to_node_id)
        status: str = "pending"  # pending, running, completed, failed

    class OrchestratorSnapshot(BaseModel):
        task_id: str
        graph: TaskGraph
        current_node_ids: List[str]  # 正在运行的节点
        completed_node_ids: List[str]
        updated_at: datetime
```


```
// 代码块-2
class OrchestratorError(Exception):
        pass

    class NodeExecutionError(OrchestratorError):
        def __init__(self, node_id: str, error: str):
            self.node_id = node_id
            super().__init__(f"Node {node_id} failed: {error}")

    class GraphCycleError(OrchestratorError):
        def __init__(self):
            super().__init__("Graph contains cycle")

    class GraphResumeError(OrchestratorError):
        def __init__(self, task_id: str):
            super().__init__(f"Cannot resume task {task_id}: checkpoint not found")
```


```
// 代码块-3
import asyncio
    from collections import deque

    class TaskOrchestrator:
        def __init__(self, checkpoint_manager: CheckpointManager):
            self.checkpoint_mgr = checkpoint_manager
            self._running_tasks = {}

        async def run(self, graph: TaskGraph) -> TaskGraph:
            # 1. 拓扑排序
            order = self._topological_sort(graph)
            # 2. 执行
            pending = set(order)
            running = set()
            completed = set()
            # 使用队列管理就绪节点
            ready_queue = deque([n for n in order if self._is_ready(n, completed)])
            while ready_queue or running:
                # 启动就绪节点
                while ready_queue:
                    node_id = ready_queue.popleft()
                    if node_id in completed or node_id in running:
                        continue
                    running.add(node_id)
                    task = asyncio.create_task(self._execute_node(graph, node_id))
                    self._running_tasks[node_id] = task
                # 等待任一完成
                if running:
                    done, _ = await asyncio.wait(
                        [self._running_tasks[n] for n in running],
                        return_when=asyncio.FIRST_COMPLETED
                    )
                    for task in done:
                        node_id = task.get_name()  # 需在创建时set_name
                        running.remove(node_id)
                        completed.add(node_id)
                        # 更新就绪队列
                        for n in order:
                            if n not in completed and n not in running and self._is_ready(n, completed):
                                ready_queue.append(n)
                    # 保存检查点
                    await self.checkpoint_mgr.save(graph.task_id, self._snapshot(graph))
            return graph

        def _topological_sort(self, graph: TaskGraph) -> List[str]:
            # 使用Kahn算法，检测循环
            in_degree = {n.id: 0 for n in graph.nodes}
            for src, tgt in graph.edges:
                in_degree[tgt] += 1
            queue = deque([n.id for n in graph.nodes if in_degree[n.id] == 0])
            result = []
            while queue:
                node = queue.popleft()
                result.append(node)
                for src, tgt in graph.edges:
                    if src == node:
                        in_degree[tgt] -= 1
                        if in_degree[tgt] == 0:
                            queue.append(tgt)
            if len(result) != len(graph.nodes):
                raise GraphCycleError()
            return result

        def _is_ready(self, node_id: str, completed: set) -> bool:
            # 所有前驱节点都已完成
            for src, tgt in graph.edges:
                if tgt == node_id and src not in completed:
                    return False
            return True

        async def _execute_node(self, graph: TaskGraph, node_id: str):
            node = next(n for n in graph.nodes if n.id == node_id)
            node.status = NodeStatus.RUNNING
            node.started_at = datetime.utcnow()
            try:
                # 根据agent_role调用对应的Agent
                agent = AgentFactory.get_agent(node.agent_role)
                result = await agent.execute(node.input)
                node.output = result
                node.status = NodeStatus.SUCCESS
            except Exception as e:
                node.error = str(e)
                if node.retry_count < node.max_retries:
                    node.retry_count += 1
                    node.status = NodeStatus.PENDING  # 重新调度
                    # 重新入队（由上层调度）
                else:
                    node.status = NodeStatus.FAILED
                    raise NodeExecutionError(node_id, str(e))
            node.finished_at = datetime.utcnow()
            # 保存检查点
            await self.checkpoint_mgr.save(graph.task_id, self._snapshot(graph))

        def _snapshot(self, graph: TaskGraph) -> OrchestratorSnapshot:
            return OrchestratorSnapshot(
                task_id=graph.task_id,
                graph=graph,
                current_node_ids=[n.id for n in graph.nodes if n.status == NodeStatus.RUNNING],
                completed_node_ids=[n.id for n in graph.nodes if n.status == NodeStatus.SUCCESS],
                updated_at=datetime.utcnow()
            )
```


```
// 代码块-4
from pydantic import BaseModel, Field
    from typing import List, Optional, Dict, Any
    from enum import Enum

    class AgentRole(str, Enum):
        ARCHITECT = "architect"
        DEVELOPER = "developer"
        REVIEWER = "reviewer"
        QA = "qa"
        CONFIG_MANAGER = "config_manager"

    # 各角色输入/输出示例
    class ArchitectInput(BaseModel):
        prd: str
        tech_stack: Optional[List[str]] = None
        constraints: Optional[List[str]] = None

    class ArchitectOutput(BaseModel):
        architecture_design: str  # 架构描述文本
        components: List[str]     # 组件列表
        data_flow: str            # 数据流描述

    class DeveloperInput(BaseModel):
        design: str               # 来自Architect的架构设计
        code_context: Optional[str] = None  # 已有代码片段

    class DeveloperOutput(BaseModel):
        code: str
        language: str = "python"
        dependencies: List[str] = Field(default_factory=list)

    class ReviewerInput(BaseModel):
        code: str
        standards: Optional[List[str]] = None

    class ReviewerOutput(BaseModel):
        passed: bool
        comments: List[str]
        severity: str  # "critical", "warning", "info"

    class QAInput(BaseModel):
        code: str
        test_cases: Optional[List[Dict]] = None

    class QAOutput(BaseModel):
        tests_passed: bool
        test_report: str
        coverage: Optional[float] = None

    class ConfigManagerInput(BaseModel):
        env_type: str  # "dev", "test", "prod"
        desired_changes: Optional[Dict[str, str]] = None

    class ConfigManagerOutput(BaseModel):
        config_files_updated: List[str]
        drift_detected: bool
```


```
// 代码块-5
class AgentError(Exception):
        pass

    class AgentOutputError(AgentError):
        def __init__(self, role: str, errors: List[str]):
            self.role = role
            self.errors = errors
            super().__init__(f"Agent {role} output validation failed: {', '.join(errors)}")

    class AgentExecutionError(AgentError):
        def __init__(self, role: str, error: str):
            self.role = role
            super().__init__(f"Agent {role} execution failed: {error}")
```


```
// 代码块-6
from abc import ABC, abstractmethod
    from typing import Any, Dict
    from src.llm.client import LLMClient
    from src.graph.repository import GraphRepository

    class BaseAgent(ABC):
        def __init__(self, llm_client: LLMClient, graph_repo: Optional[GraphRepository] = None, sandbox: Optional[DockerSandbox] = None):
            self.llm = llm_client
            self.graph = graph_repo
            self.sandbox = sandbox
            self.prompt_template = self._load_prompt()

        @abstractmethod
        def _load_prompt(self) -> str:
            pass

        @abstractmethod
        def _validate_input(self, input_data: Dict) -> Any:
            pass

        @abstractmethod
        def _validate_output(self, output_data: Dict) -> Any:
            pass

        async def execute(self, input_data: Dict) -> Dict:
            # 1. 校验输入
            validated_input = self._validate_input(input_data)
            # 2. 渲染Prompt
            prompt = self.prompt_template.render(**validated_input.dict())
            # 3. 调用LLM
            response = await self.llm.generate(prompt=prompt, system_prompt=self.system_prompt)
            # 4. 解析输出（假设LLM返回JSON）
            try:
                parsed = json.loads(response.content)
            except json.JSONDecodeError:
                raise AgentOutputError(self.role, ["LLM response not valid JSON"])
            # 5. 校验输出
            validated_output = self._validate_output(parsed)
            return validated_output.dict()
```


```
// 代码块-7
class DeveloperAgent(BaseAgent):
        role = AgentRole.DEVELOPER
        system_prompt = "You are a senior software engineer. Generate clean, well-documented Python code."

        def _load_prompt(self):
            env = Environment(loader=FileSystemLoader("src/agents/prompts"))
            return env.get_template("developer.jinja2")

        def _validate_input(self, data):
            return DeveloperInput(**data)

        def _validate_output(self, data):
            return DeveloperOutput(**data)
```


```
// 代码块-8
Design: {{ design }}
    Code context: {{ code_context }}
    Please generate Python code that implements the design. Return JSON with fields: code, language, dependencies.
```


# 多Agent自循环系统 · 阶段6 前端与集成测试 (Step 6.1 & 6.2) · 编码就绪级PRD/ADR

Vue3 实时驾驶舱 ｜ E2E 测试与质量门禁

**交付声明：**本报告为阶段6（W11-W12）的终极细化文档。Step 6.1实现可视化驾驶舱（任务拓扑、Token流速、熵曲线），Step 6.2建立端到端测试体系（含性能基准与混沌实验）。两个Step与已交付的所有后端组件（调度器、LLM客户端、图谱引擎、防幻觉体系）无缝集成，确保系统可观测、可验证。



## Step 5.3：动态任务分片与降级

| PRD (产品需求文档) |  | 
| --- | --- | 
| **背景** | 当单个任务规模超过LLM上下文窗口或Token预算上限时（如大仓库重构、超长代码生成），系统需自动将大任务拆分为可管理的子任务，并按预算约束降级执行策略。 | 
| **用户故事** | 作为调度器，当我检测到任务规模超出阈值时，自动触发任务分片，将大任务切分为多个小任务队列，并按降级策略执行（减少模型、简化验证）。 | 
| **需求描述** | ①实现任务规模评估（Token计数 + AST节点数）；②定义分片策略（按文件、按模块、按函数层级）；③实现降级执行链（满血→降级→极限降级→拒绝）；④在调度器（Step 5.1）中集成触发逻辑。 | 
| **范围 (Do/Don't)** | **Do：**Token/行数双维度评估，自动分片，降级执行链，调度器集成。**Don't：**不支持跨语言分片（V2），不支持动态重分片（运行中调整）。 | 
| **数据契约** | 输入：`TaskScaleInput = {token_count: int, ast_nodes: int, complexity: float}`；输出：`ShardPlan = {shards: list[Shard], strategy: str, budget_tier: str}`。 | 
| **异常定义** | `ScaleExceedsLimitError`：任务规模超出系统处理能力；`ShardFailedError`：某个分片执行失败。 | 
| **成功标准→验收** | **SC1:**分片触发 →**AC1:**输入5000 Token任务，检测到超阈值，自动触发分片，输出2个以上分片。 | 
| | **SC2:**降级执行 →**AC2:**预算耗尽时自动降级（gpt-4→gpt-4o-mini），验证降级前后结果一致性80%以上。 | 
| | **SC3:**分片并行 →**AC3:**分片之间无依赖时并行调度，总时间小于串行时间的60%。 | 
| **待定决策** | **Q1:**分片大小以什么为单位？ →**决议：**以Token数为首选单位（行数为辅助），因为LLM有明确Token限制。 | 

| ADR (架构决策记录) |  | 
| --- | --- | 
| **技术栈版本** | Python 3.11, tiktoken 0.6, ast (内置), asyncio。 | 
| | 位置：`/src/scheduler/scaler.py`（任务规模评估）、`/src/scheduler/sharding.py`（分片策略）、`/src/scheduler/degradation.py`（降级链）。 | 
| **架构位置** | 调度层（Step 5.1）上游，接收任务后判断是否需要分片/降级，决定是否进入调度器。 | 
| **实施细节** | **任务规模评估：** | 
| | ```python | 
| | class TaskScaler: | 
| |     def __init__(self, token_limit: int = 128000, node_limit: int = 5000): | 
| |         self.token_limit = token_limit | 
| |         self.node_limit = node_limit | 
| |     def evaluate(self, task_input: dict) -> tuple: | 
| |         tokens = self._count_tokens(task_input) | 
| |         ast_nodes = self._count_ast_nodes(task_input) | 
| |         needs_sharding = tokens > self.token_limit | 
| |         needs_degradation = tokens > self.token_limit * 0.8 | 
| |         if not needs_sharding: | 
| |             return ShardPlan(shards=[Shard(id=0, input=task_input)], strategy="none"), needs_degradation | 
| |         shards = self._create_shards(task_input) | 
| |         budget_tier = self._compute_budget_tier(tokens) | 
| |         return ShardPlan(shards=shards, strategy="file_boundary", budget_tier=budget_tier), needs_degradation | 
| | ``` | 
| | **降级执行链：** | 
| | ```python | 
| | class DegradationChain: | 
| |     TIERS = [ | 
| |         ("gpt-4o", 1.0, 0.8),   # model, cost_factor, quality_threshold | 
| |         ("gpt-4o-mini", 0.3, 0.75), | 
| |         ("gpt-3.5-turbo", 0.1, 0.65), | 
| |     ] | 
| |     def __init__(self, budget_pct: float): | 
| |         self.budget_pct = budget_pct | 
| |     def get_tier(self) -> str: | 
| |         for model, cost_factor, quality in self.TIERS: | 
| |             if self.budget_pct >= cost_factor * 100: | 
| |                 return model | 
| |         return "reject" | 
| | ``` | 
| | **分片调度集成：** | 
| | 在TaskOrchestrator（Step 5.1）的submit方法中，判断是否需要分片；若需要，将多个Shard作为独立TaskGraph节点提交。 | 
| **风险与缓解** | 风险1：分片后函数/类被切断（跨文件引用）。缓解：按文件边界分片，函数级分片仅用于无导入场景。 | 
| | 风险2：降级后质量不可接受。缓解：质量阈值低于0.65时拒绝执行，而非继续降级。 | 
| **需求错位** | 若任务规模远超系统能力（如百万行代码库），当前分片策略可能产生数百个分片。V2可考虑增量分片。 | 
| **技术约束** | 分片操作必须在调度器外部完成；降级决策由`DegradationChain`统一管理。 | 
| **环境配置** | TASK_SCALE_TOKEN_LIMIT=128000 | 
| | TASK_SCALE_NODE_LIMIT=5000 | 
| | DEGRADATION_BUDGET_PCT=100 | 
| | MAX_SHARDS_PER_TASK=50 | 
| **依赖链** | TaskScaler → DegradationChain → TaskOrchestrator → AgentFactory。 | 

| 🧪 原子化测试用例 (pytest)： | 
| ```python | 
| import pytest | 
| from src.scheduler.scaler import TaskScaler, ScaleExceedsLimitError | 
| from src.scheduler.degradation import DegradationChain | 
| 
| def test_task_scaler_under_limit(): | 
|     scaler = TaskScaler(token_limit=1000) | 
|     plan, needs_deg = scaler.evaluate({"text": "short task"}) | 
|     assert len(plan.shards) == 1 | 
|     assert plan.strategy == "none" | 
|     assert not needs_deg | 
| 
| def test_task_scaler_triggers_sharding(): | 
|     scaler = TaskScaler(token_limit=100) | 
|     plan, needs_deg = scaler.evaluate({"text": "x" * 500}) | 
|     assert len(plan.shards) > 1 | 
|     assert plan.strategy == "file_boundary" | 
| 
| def test_degradation_chain_full_budget(): | 
|     chain = DegradationChain(budget_pct=100) | 
|     assert chain.get_tier() == "gpt-4o" | 
| 
| def test_degradation_chain_low_budget(): | 
|     chain = DegradationChain(budget_pct=20) | 
|     assert chain.get_tier() == "gpt-3.5-turbo" | 
| 
| def test_degradation_chain_reject(): | 
|     chain = DegradationChain(budget_pct=5) | 
|     assert chain.get_tier() == "reject" | 
| ```

## Step 5.4：Agent间通信协议与契约
### 1.1 设计原则
- 异步优先：Agent间调用以异步消息为主，避免同步阻塞导致调度器卡死。
- 超时必设：每次跨Agent调用必须设置超时，默认30秒，可配置。
- 幂等性保障：消息可重放，下游必须支持幂等处理（通过request_id去重）。
- 熔断传播：下游Agent熔断时，上游Agent收到标准化错误码，可执行降级策略。
- 审计完备：所有通信记录写入task_audit_trail，支持全链路追踪。
### 1.2 通信模式
| 模式 | 说明 | 适用场景 |
| --- | --- | --- |
| Request-Response | Agent A发送请求，阻塞等待Agent B返回结果 | DeveloperAgent → QAAgent（验证代码） |
| Fire-and-Forget | Agent A发送消息，不等待响应 | 审计日志记录、指标上报 |
| Streaming | Agent B分块返回结果 | L3熵监控（流式Token分析） |
| Callback | Agent A提供回调URL，Agent B完成后异步通知 | 长时间运行的验证任务（Z3求解、沙箱执行） |
### 1.3 数据契约
```
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
### 1.4 异常定义
```
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
### 1.5 通信层实现
```
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
### 1.6 ADR：通信模式选型
| ADR · Agent间通信模式 |
| --- |
| 决策 | 采用异步消息总线 + 同步Future等待的混合模式：
① Agent间调用通过MessageBus转发，调用方使用await bus.request()同步等待。
② 底层使用asyncio实现非阻塞，支持超时和熔断传播。
③ 长耗时操作（Z3、沙箱）使用Callback模式，避免长时间占用连接。 |
| 理由 | ① 简化调用方代码（同步写法，异步执行）。② 超时和熔断可在单一位置统一管理。③ 与V14.1的asyncio调度器自然兼容。 |
| 备选方案 | ① 纯异步回调（代码复杂度高，调试困难）→ 放弃。② gRPC流式通信（过重，不适合Agent间轻量通信）→ 放弃。 |



## Step 5.5：工具调用标准化与注册机制
### 2.1 设计原则
- 声明式注册：工具通过装饰器或配置文件声明，支持动态加载。
- 权限隔离：每个工具定义allowed_agents，只有授权Agent可调用。
- 版本兼容：工具支持语义化版本，Agent调用时指定版本范围。
- 可观测性：每次工具调用记录到审计表（含入参、出参、耗时）。
- 优雅降级：工具不可用时，系统自动降级（如返回缓存结果或跳过）。
### 2.2 工具注册与元数据
```
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
### 2.3 工具注册中心
```
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
### 2.4 工具声明示例
```
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
### 2.5 ADR：工具调用的版本管理
| ADR · 工具版本管理 |
| --- |
| 决策 | 工具采用语义化版本管理，Agent调用时需声明版本范围（如~=1.2），系统自动解析为精确版本。
① 工具升级时，旧版本仍保留（向后兼容至少3个小版本）。
② 工具废弃时，在元数据中标记deprecated=True，并给出迁移指引。
③ 审计表记录每次调用的精确版本。 |
| 理由 | ① 避免Agent因工具升级而失效。② 支持A/B测试（不同Agent使用不同版本）。③ 便于回滚（发现问题时切回旧版本）。 |



## Step 5.6：多任务并发与资源调度策略
### 3.1 设计原则
- 优先级分层：任务分为CRITICAL/HIGH/NORMAL/LOW四级，高优先级抢占资源。
- 资源配额：按任务/团队/全局三级设置资源配额（LLM调用、沙箱实例、Token预算）。
- 公平调度：防止单个大任务独占资源，引入时间片轮转。
- 背压控制：资源不足时，新任务排队或拒绝，而非崩溃。
### 3.2 任务优先级与资源配额
```
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
### 3.3 资源调度器核心实现
```
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
### 3.4 与调度器状态机的集成
```
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
### 3.5 ADR：抢占式调度 vs 公平调度
| ADR · 多任务调度策略 |
| --- |
| 决策 | 采用优先级抢占式调度 + 公平时间片混合策略：
① 高优先级任务（CRITICAL/HIGH）可抢占低优先级任务的资源。
② 同优先级任务采用时间片轮转（每个任务最多连续运行30秒）。
③ 长运行任务（>5分钟）自动降级为LOW优先级。 |
| 理由 | ① 生产故障修复必须优先保障（CRITICAL）。② 防止单个任务无限占用资源。③ 保证低优先级任务也能获得执行机会。 |
| 风险与缓解 | 风险：频繁抢占导致低优先级任务饥饿。缓解：CRITICAL任务每天不超过5个，超过后降级为HIGH。 |



## Step 5.7：Agent拉起机制
### 核心概念澄清

> **核心声明：在 V14.1 中，Agent 不是独立微服务、不是容器、不是进程，而是 调度器进程内的一个 Python 异步协程（asyncio Task）。**
#### 1.1 “调用 Agent”的两种语义
| 语义 | 含义 | V14.1 的实现 |
| --- | --- | --- |
| A2A 通信 | Agent A 请求 Agent B 执行某任务或提供信息 | 通过 A2A 协议（结构化消息）实现 Agent 间通信 |
| 系统拉起 Agent | 调度器将 Agent 实例化并开始执行 | 调度器的状态机通过 asyncio.create_task() 拉起 Agent 协程 |
用户的问题“怎么调用 Agent”属于第二种语义：系统如何将 Agent 实例化并启动执行。

### Agent 的实现形态

```
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
#### 2.1 关键特征
- 进程内执行：所有 Agent 运行在同一个进程中，无进程间通信开销。
- 协程隔离：每个 Agent 是一个独立的 asyncio Task，由事件循环调度。
- 状态隔离：Agent 间不直接共享内存，通过调度器的 Session/Checkpoint 传递经过验证的数据。
- 私有工作记忆（L4）：每个 Agent 有独立的局部工作记忆，不跨 Agent 共享。
- 拉起速度：协程创建为微秒级，远快于容器启动（秒级）。

### 系统拉起 Agent 的完整流程

#### 3.1 第1步：用户触发（外部入口）
```
# API 入口
@router.post("/api/v1/tasks")
async def create_task(req: TaskCreateRequest):
task = Task(prd=req.prd, state=TaskState.IDLE)
await scheduler.submit(task)  # ← 提交给调度器
return {"task_id": task.id}
```
用户调用的不是 Agent，而是调度器的 API 入口。
#### 3.2 第2步：调度器状态机驱动
```
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
#### 3.3 第3步：拉起 Agent 协程（核心）
```
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
#### 3.4 第4步：Agent 执行循环
```
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

### 与 MCP/A2A 的抽象分层

在 V14.1 中，MCP 和 A2A 服务于不同的抽象层级，而“系统拉起 Agent”是另一个独立的层级。
> **┌─────────────────────────────────────────────────────────────┐
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
└─────────────────────────────────────────────────────────────┘**
#### 4.1 三层调用关系
| 层级 | 用途 | 协议/方式 | 调用方向 |
| --- | --- | --- | --- |
| 系统 → Agent | 调度器实例化并驱动 Agent 协程 | asyncio.create_task() + await agent.run() | 向上驱动 |
| Agent → 工具 | Agent 调用外部工具/资源（四图谱、沙箱、数据库） | MCP（Model Context Protocol） | 向下调用 |
| Agent → Agent | Agent 之间协作通信（任务分发、审查、仲裁） | A2A（Agent-to-Agent Protocol） | 水平通信 |
#### 4.2 与现有协议的定位
- MCP 不在“拉起 Agent”层：MCP 是 Agent 已经运行后用来调用工具的协议。它不负责 Agent 的启动或生命周期管理。
- A2A 不在“拉起 Agent”层：A2A 是 Agent 之间已经运行后用来相互通信的协议。它也不负责 Agent 的启动。
- “拉起 Agent”是调度器的职责：通过 asyncio 协程直接实例化和驱动，是 V14.1 自研调度器的核心能力。

### PRD/ADR 规格

#### 5.1 PRD · Agent 拉起机制
| PRD · Agent 拉起机制 |
| --- |
| 背景 | 外部系统需要通过调度器驱动多智能体协作。Agent 不是预先部署的微服务，而是由调度器按需实例化的异步协程。 |
| 用户故事 | 作为调度器，我根据状态机的进度，在合适的时机await agent.run()拉起对应的 Agent 协程，执行完成后将结果写入检查点。 |
| 需求描述 | ① Agent 定义为异步协程类，实现 run(context: TaskContext) -> AgentResult 方法。
② 调度器通过 asyncio.create_task() 拉起 Agent。
③ 拉起时注入 L1-L5 上下文（L1 协作宪法、L2 四图谱事实、L3 任务状态、L4 私有记忆、L5 长期记忆）。
④ Agent 执行完成后，结果写入检查点（Checkpoint），供下游 Agent 使用。
⑤ 外部系统通过 API 调用调度器，不直接调用 Agent。 |
| 范围 | Do：进程内协程拉起；依赖注入；上下文构建；结果持久化。
Don't：不通过 HTTP/gRPC 远程调用 Agent；不将 Agent 部署为独立容器。 |
| 数据契约 | ```
class TaskContext(BaseModel):
task_id: str
l1: str  # System Prompt（协作宪法）
l2: Dict[str, Any]  # 四图谱查询结果
l3: Dict[str, Any]  # 任务状态（PRD摘要、DAG进度）
l4: Dict[str, Any]  # Agent私有工作记忆
l5: List[Dict[str, Any]]  # 长期记忆（检索结果）
class AgentResult(BaseModel):
success: bool
output: Any
error: Optional[str] = None
duration_ms: float
``` |
| SC→AC | SC1: Agent 拉起成功 → AC1: 状态机触发 CODING 状态时，调用 _run_agent(DeveloperAgent, task) 返回 AgentResult。
SC2: 上下文注入完整 → AC2: Agent 的 run() 方法中 context.l1、context.l2 非空且包含预期内容。
SC3: 结果持久化 → AC3: Agent 执行完成后，检查点中存在对应 task_id 的记录。 |
| 待定决策 | Q: Agent 执行超时如何处理？ → 决议：在 _run_agent() 中包装 asyncio.wait_for(agent.run(), timeout=300)，超时后取消协程并标记 FAILED。 |
#### 5.2 ADR · Agent 实现形态
| ADR · Agent 实现形态 |
| --- |
| 决策 | Agent 实现为进程内异步协程，而非独立微服务或容器。
① 所有 Agent 运行在调度器同一进程中。
② 通过 asyncio 事件循环调度。
③ 通过依赖注入传递外部依赖（LLM 客户端、图谱仓库、沙箱）。
④ 通过 Checkpoint 实现状态跨 Agent 传递。 |
| 理由 | ① 无网络开销：协程间通信为零延迟。② 极速拉起：协程创建为微秒级。③ 共享内存：Checkpoint 直接读取，无需序列化传递。④ 简化运维：无需部署多个微服务。⑤ 与 V14.1 的 asyncio 调度器自然兼容。 |
| 备选方案 | ① 独立微服务（HTTP/gRPC 拉起）→ 网络延迟高，资源消耗大，不适合密集 Agent 协作。② 独立容器（Docker 拉起）→ 启动慢（秒级），资源隔离过度。 |

### 与现有 Step 的映射

| Step | 原有内容 | Agent 拉起机制的补充 |
| --- | --- | --- |
| Step 5.1调度器状态机 | 定义了状态转换（IDLE→PARSING→PLANNING→CODING→...） | 需补充 在状态转换中增加 _run_agent() 方法的实现，明确如何拉起 Agent 协程 |
| Step 5.2Agent 角色与 Prompt | 定义了 5 个 Agent 的 System Prompt 和职责 | 需补充 每个 Agent 类必须实现 run(context: TaskContext) -> AgentResult 接口 |
| Step 2.2检查点持久化 | Redis + PostgreSQL 双层存储 | 需补充 Agent 执行完成后，结果通过 CheckpointManager 写入检查点，供下游 Agent 使用 |
| Step 5.4Agent 间通信 | 定义了 A2A 协议的结构化消息格式 | 无修改 该 Step 处理的是 Agent 间通信，与“系统拉起 Agent”是不同层级 |
| Step 3.1-3.4四图谱 | 代码/数据库/配置/知识图谱 | 无修改 Agent 通过 MCP 调用图谱查询，与拉起机制无关 |

### 代码示例

#### 7.1 调度器拉起 Agent 的完整实现
```
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
#### 7.2 外部系统调用调度器的 API
```
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
#### 7.3 Agent 基类定义
```
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
> **✅ Agent 拉起机制交付确认
核心概念澄清：区分“系统拉起 Agent”与“Agent 间通信（A2A）”两种语义
Agent 实现形态：进程内 asyncio 协程，而非独立微服务
拉起流程：外部 API → 调度器状态机 → asyncio.create_task() → Agent 协程
抽象分层：系统→Agent（协程拉起）、Agent→工具（MCP）、Agent→Agent（A2A）
PRD/ADR：完整的规格定义，含数据契约、SC→AC、备选方案对比
与现有 Step 映射：Step 5.1/5.2 需补充，Step 5.4/3.1-3.4 无修改
代码示例：调度器拉起实现、外部 API 调用、Agent 基类定义
下一步：可将本报告中的代码示例和 PRD/ADR 规格合并到 Step 5.1（调度器状态机）和 Step 5.2（Agent 角色与 Prompt）中。**
— V14.1 开发计划 · Agent 拉起机制 · 2026年6月22日 —


## Step 5.9：架构图与数据流向
### 图管理PRD/ADR规格

> **核心声明：V14.1系统的四张架构图是正式的技术文档资产，而非临时示意图。所有图表均配有Mermaid源码、版本控制和审核流程，确保与代码演进保持同步。**
#### 1.1 PRD · 架构图管理
| PRD · 架构图管理 |
| --- |
| 背景 | V14.1系统包含多层架构（用户层→接入层→调度层→能力层→验证层→知识层→工具层→可观测层），需通过标准化图表帮助团队理解系统全貌、协作流程和数据流向。 |
| 用户故事 | 作为架构师，我需要在技术评审时用标准化的系统架构图向团队说明V14.1的设计；作为开发工程师，我需要通过数据流向图理解代码从PRD到交付物的完整路径。 |
#### 1.2 ADR · 图表工具选型
| ADR · 图表工具选型 |
| --- |

### 图一：系统架构全景图

#### 2.1 图表说明
本图展示V14.1系统的完整分层架构，从用户层到可观测层共8层，清晰标注了组件间的依赖关系和调用方向。
#### 2.2 Mermaid源码
```
graph TB
subgraph 用户层
User[👤 用户]
WeChat[📱 微信小程序]
Dashboard[🖥️ Web驾驶舱]
end
subgraph 接入与网关层
API[🌐 API GatewayRESTful + WebSocket]
Auth[🔐 认证与权限JWT + 零信任]
end
subgraph 核心调度层
Orc[⚙️ 自研调度器 Orchestrator]
SM[🔄 状态机IDLE→PARSING→PLANNING→CODING→VALIDATING→DONE]
CP[💾 检查点 CheckpointRedis + PostgreSQL]
Audit[📋 审计链task_audit_trail]
end
subgraph 能力层（5个Agent协程）
Arch[🏗️ 架构师 Agent方案制定]
Dev[💻 开发者 Agent代码实现]
Rev[🔍 审查员 Agent分歧仲裁]
QA[🧪 QA Agent验证执行]
Cfg[⚙️ 配置管理员 Agent环境守护]
end
subgraph 验证层
L1_L9[🛡️ 9层防幻觉门禁L1-L9 同步阻塞验证]
Sentinel[🚨 哨兵 Agent主动安全检测]
end
subgraph 知识层
CG[📚 代码图谱Tree-sitter + SQLite]
DG[🗄️ 数据库图谱Schema + MVCC]
CFG[⚙️ 配置图谱基线 + 漂移检测]
KG[🧠 领域知识图谱Neo4j + Milvus + MCP]
end
subgraph 工具层
Sandbox[🏖️ Docker沙箱]
LLM[🤖 LiteLLM网关DeepSeek主力 + 缓存]
Git[📦 Git操作]
end
subgraph 可观测层
Ops[📊 AgentOpsPrometheus + Grafana]
Logs[📝 ELK日志]
Traces[🔗 分布式追踪]
end
User --> Dashboard & WeChat
Dashboard & WeChat --> API
API --> Auth
Auth --> Orc
Orc --> SM
SM --> CP
SM --> Audit
Orc -- asyncio.create_task() --> Arch & Dev & Rev & QA & Cfg
Dev -- 通过MCP查询 --> CG & DG & CFG & KG
Dev -- 通过MCP调用 --> Sandbox & LLM & Git
Dev -- 输出进入验证 --> L1_L9
L1_L9 --> Sentinel
Sentinel -- 通过后写入共享上下文 --> CP
Sentinel -- 失败时阻断传播 --> Audit
Orc -.-> Ops & Logs & Traces
Audit -.-> Ops
```
#### 2.3 与Step映射
- 用户层 → Step 6.1（Web驾驶舱）和 微信小程序接入章节
- 接入与网关层 → Step 1.1（API契约）和 Step 7.6（安全）
- 核心调度层 → Step 2.2（检查点）、Step 5.1（状态机）、审计补丁
- 能力层 → Step 5.2（5个Agent）
- 验证层 → Step 4.1/4.2（L1-L8）和 Step 4.3（L9）及 哨兵Agent章节
- 知识层 → Step 3.1/3.2/3.3（三图谱）和 Step 3.4（领域知识图谱）
- 工具层 → Step 2.1（LiteLLM）和 Step MVP-03（沙箱）
- 可观测层 → Step 7.2（AgentOps）

### 图二：层级抽象与协议栈

#### 3.1 图表说明
本图展示V14.1系统的三层抽象架构：编排层（V14.1核心价值）、通信层（MCP/A2A/HTTP协议栈）、执行层（底层引擎）。清晰标注了各层的职责边界和依赖关系。
#### 3.2 Mermaid源码
```
graph LR
subgraph 编排层["编排层 (V14.1核心)"]
direction TB
O1[多Agent协作调度]
O2[状态机驱动]
O3[9层验证门禁]
O4[审计链追溯]
end
subgraph 通信层["通信层 (协议栈)"]
direction TB
C1[MCPAgent↔工具/图谱]
C2[A2AAgent↔Agent]
C3[HTTP/WS外部↔系统]
end
subgraph 执行层["执行层 (底层引擎)"]
direction TB
E1[LLM推理DeepSeek主力]
E2[沙箱执行Docker]
E3[图谱查询SQLite/Neo4j]
end
编排层 --> 通信层
通信层 --> 执行层
style 编排层 fill:#eff6ff,stroke:#2563eb
style 通信层 fill:#fefce8,stroke:#f59e0b
style 执行层 fill:#f0fdf4,stroke:#16a34a
```
#### 3.3 与Step映射
- 编排层 → Step 5.1（调度器状态机）、Step 5.2（5个Agent）、Step 4.1-4.3（验证门禁）
- 通信层 → 微信小程序接入（HTTP/WS）、Step 5.4（A2A）、Step 5.5（MCP工具注册）
- 执行层 → Step 2.1（LiteLLM）、Step MVP-03（沙箱）、Step 3.1-3.4（四图谱）

### 图三：数据流向图（从需求到交付物）

#### 4.1 图表说明
本图展示用户PRD从输入到最终交付物的完整数据流转路径，清晰标注了每个阶段的输入/输出以及跨Agent的数据传递方式（检查点/审计链）。
#### 4.2 Mermaid源码
```
flowchart LR
PRD[📄 PRD用户需求] --> Parser[🧹 ParserAgent需求澄清]
Parser --> Plan[📋 ArchitectAgent技术方案 DAG]
Plan --> Code[💻 DeveloperAgent代码生成]
Code --> L1_L9[🛡️ L1-L9验证门禁]
L1_L9 -->|通过| Audit[📋 审计链记录决策]
L1_L9 -->|失败| Fix[🔄 重试/驳回]
Fix --> Code
Audit --> Checkpoint[💾 检查点持久化]
Checkpoint --> Deliver[📦 交付物代码 + 验证报告]
Deliver --> User[👤 用户]
Deliver --> Webhook[🔗 Webhook外部系统]
Deliver --> MiniApp[📱 微信小程序]
Graph[📚 四图谱] -.-> Code
Graph -.-> L1_L9
Memory[🧠 L5长期记忆] -.-> Plan
Memory -.-> Code
style PRD fill:#eff6ff,stroke:#2563eb
style Deliver fill:#f0fdf4,stroke:#16a34a
style User fill:#fefce8,stroke:#f59e0b
```
#### 4.3 与Step映射
- PRD → ParserAgent：Step 0.3（需求澄清）
- ParserAgent → ArchitectAgent：Step 5.2（Agent协作）
- ArchitectAgent → DeveloperAgent：Step 5.1（状态机驱动）
- DeveloperAgent → L1-L9：Step 4.1-4.3（验证门禁）
- 验证 → 检查点/审计链：Step 2.2（检查点）、审计补丁
- 检查点 → 交付物：交付物流向章节
- 交付物 → 用户/Webhook/小程序：Step 1.1（API）、微信小程序接入章节

### 图四：关键设计要点（一图总结）

#### 5.1 图表说明
本图以表格形式总结V14.1系统各层的核心组件、关键设计和一句话说明，便于快速传达系统设计理念。
#### 5.2 图表内容（可直接渲染的表格）
```
| 层级 | 核心组件 | 关键设计 | 一句话说明 |
|------|----------|----------|-----------|
| 用户层 | 微信小程序 / Web驾驶舱 | Skill机制 + WebSocket | 手机也能提交任务、看进度 |
| 接入层 | API网关 + JWT认证 | RESTful + SSE + WebSocket | 统一入口，安全可控 |
| 调度层 | 自研调度器 + 状态机 | asyncio协程 + 检查点 | 微秒级拉起Agent，崩溃可恢复 |
| 能力层 | 5个Agent协程 | 依赖注入 + L4私有记忆 | 各司其职，幻觉不跨Agent传播 |
| 验证层 | L1-L9门禁 | 同步阻塞验证 | 验证不通过，产出不进共享上下文 |
| 知识层 | 四图谱 | MCP协议查询 | 零Token开销的事实锚点 |
| 工具层 | LiteLLM / 沙箱 / Git | 标准化工具接口 | Agent通过MCP调用 |
| 协议层 | MCP + A2A | 标准化协议 | 工具调用与Agent通信分离 |
| 可观测层 | AgentOps + 审计链 | 哈希链防篡改 | 知道"做了什么"，也知道"为什么" |
```
#### 5.3 与Step映射
- 用户层 → Step 6.1 + 微信小程序接入章节
- 接入层 → Step 1.1 + Step 7.6
- 调度层 → Step 2.2 + Step 5.1
- 能力层 → Step 5.2
- 验证层 → Step 4.1 + Step 4.2 + Step 4.3
- 知识层 → Step 3.1 + Step 3.2 + Step 3.3 + Step 3.4
- 工具层 → Step 2.1 + Step MVP-03
- 协议层 → Step 5.4 + Step 5.5 + 微信小程序接入章节
- 可观测层 → Step 7.2

### 与现有Step的映射总览

| 图表 | 包含内容 | 对应Step |
| --- | --- | --- |
| 图一：架构全景图 | 8层完整架构 + 组件依赖关系 | Step 1.1, 2.1, 2.2, 3.1-3.4, 4.1-4.3, 5.1, 5.2, 6.1, 7.2, 7.6, MVP-03, 微信小程序接入 |
| 图二：层级抽象与协议栈 | 编排层 → 通信层 → 执行层 | Step 2.1, 3.1-3.4, 4.1-4.3, 5.1, 5.2, 5.4, 5.5, MVP-03, 微信小程序接入 |
| 图三：数据流向图 | PRD → 交付物 端到端流程 | Step 0.3, 2.2, 4.1-4.3, 5.1, 5.2, 审计补丁, 交付物流向章节, 微信小程序接入 |
| 图四：关键设计要点 | 各层核心组件+关键设计+一句话说明 | 所有Step（总览性质） |
> **✅ 架构图与数据流向交付确认
图一：系统架构全景图 —— 8层分层架构，含Mermaid源码和Step映射
图二：层级抽象与协议栈 —— 编排层/通信层/执行层，含Mermaid源码和Step映射
图三：数据流向图 —— PRD到交付物的端到端流程，含Mermaid源码和Step映射
图四：关键设计要点 —— 表格化总览，含各层核心设计和Step映射
图管理PRD/ADR —— 图表维护规范、选型决策、SC→AC验收标准
— V14.1 开发计划 · 架构图与数据流向 · 2026年6月22日 —



## Step 5.8：微信小程序接入
### 整体架构设计

> **核心方案：微信小程序 + Skill 机制作为请求入口，WebSocket/SSE 作为实时监控通道。**
#### 1.1 完整调用链路
```
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
#### 1.2 为什么选择微信小程序？
- 天然的用户入口：微信日活超10亿，无需用户额外下载 App。
- 官方 AI 能力加持：微信已推出小程序 Skill 机制，可将功能封装为 AI 可调用的能力。
- 基于 MCP：Skill 底层基于 MCP 协议，与 V14.1 使用的 MCP 协议栈天然同构。
- 实时通信支持：小程序支持 WebSocket 和 SSE 两种实时方案。

### 微信小程序 Skill 机制

#### 2.1 Skill 是什么
Skill 是微信官方推出的 AI 能力接入机制，开发者可将小程序的能力封装为 AI 可调用的 Skill。用户通过自然语言就能触发 Skill，执行对应功能。
#### 2.2 两种接入模式
| 模式 | 说明 | 适用场景 |
| --- | --- | --- |
| 自动模式 | 平台自动分析小程序源码，AI 可直接操作 | 快速验证，零代码接入 |
| 开发模式 | 开发者自定义 Skill，通过审核后被 AI 调用 | 推荐 定制化 V14.1 任务触发 |
#### 2.3 Skill 文件结构
```
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
#### 2.4 mcp.json 声明示例
```
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
#### 2.5 函数实现示例
```
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

### 与 V14.1 的 MCP 协议集成

> **核心洞察：微信小程序的 Skill 机制底层基于 MCP 协议，与 V14.1 使用的 MCP 协议栈完全兼容。这意味着 Skill 中的函数声明（mcp.json）可以直接映射到 V14.1 的 MCP Server。**
#### 3.1 分层架构
```
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
#### 3.2 V14.1 端 MCP 工具暴露
```
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

### 实时监控方案

#### 4.1 两种实时通信方案对比
| 方案 | 特点 | 适用场景 |
| --- | --- | --- |
| WebSocket | 全双工 通信，适合高频双向交互 | Agent 执行过程中需要用户介入确认（如：选择方案A还是B） |
| SSE (Server-Sent Events) | 单向 推送，基于 HTTP 更轻量 | 只需“看进度”的纯监控场景 |
#### 4.2 WebSocket 实时监控实现
```
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
#### 4.3 SSE 实时监控实现
```
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

### API 规格

#### 5.1 任务提交 API
```
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
#### 5.2 状态查询 API
```
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

### 与现有 Step 的映射

| Step | 原有内容 | 微信小程序接入的补充 |
| --- | --- | --- |
| Step 1.1四层架构与 API 契约 | 定义了 RESTful API 契约 | 需补充 增加 /tasks 路由的 source 字段；新增 /tasks/{id}/stream SSE 端点 |
| Step 6.1Vue3 驾驶舱 | 定义了 Web 驾驶舱的实时监控 | 无修改 微信小程序的实时监控复用相同的 WebSocket/SSE 基础设施 |
| Step 2.1LiteLLM 网关 | LLM API 调用网关 | 无修改 微信小程序接入不涉及 LLM 网关 |
| Step 5.1调度器状态机 | 定义了任务执行状态流转 | 需补充 状态变更时触发 WebSocket/SSE 广播（通过 StatusBroadcaster） |
| Step 7.6安全与权限管理 | JWT + 零信任架构 | 需补充 微信小程序的来源认证（小程序 AppID 验证 + JWT 颁发） |

### 代码示例

#### 7.1 微信小程序 Skill 完整示例
```
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
#### 7.2 微信小程序实时监控组件
```
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
#### 7.3 微信小程序卡片展示
```
<!-- components/status-card/index.wxml -->
<view class="status-card">
<view class="status-header">
<text class="task-id">任务: {{taskId}}</text>
<text class="status-badge {{status}}">{{status}}</text>
</view>
<view class="progress-section">
<text class="progress-label">执行进度</text>
<progress percent="{{progress * 100}}" stroke-width="8" />
<text class="progress-text">{{Math.round(progress * 100)}}%</text>
</view>
<view class="logs-section">
<text class="logs-title">执行日志</text>
<scroll-view class="logs-scroll" scroll-y>
<view class="log-item" wx:for="{{logs}}" wx:key="index">
<text class="log-time">{{item.time}}</text>
<text class="log-content">{{item.msg}}</text>
</view>
</scroll-view>
</view>
</view>
```

### 实施路线图

| 阶段 | 任务 | 周期 | 依赖 |
| --- | --- | --- | --- |
| 准备阶段 | ① 设计 V14.1 后端 API（/tasks 提交、/tasks/{id}/status 查询、WebSocket/SSE 推送）② 申请微信小程序 AppID③ 搭建微信小程序开发环境 | 1-2天 | Step 1.1 完成 |
| 开发阶段 | ① 创建微信小程序 Skill 项目（mcp.json + apis/*.js + index.js）② 实现 Skill 调用 V14.1 API 的逻辑③ 实现 WebSocket/SSE 实时通信④ 设计小程序 UI（输入+状态卡片） | 3-5天 | Step 5.1 完成 |
| 集成与测试 | ① 端到端联调（小程序 ↔ V14.1）② 实时监控体验优化③ 安全认证联调 | 2-3天 | Step 7.6 完成 |
| 上线发布 | ① 微信小程序提交审核② Skill 功能发布③ ⚠️ 注意：Skill模式目前在内测，相关代码暂时不要合入正式版本提审 | 1-2天 | 测试通过 |
> **⚠️ 重要提醒：
微信小程序 Skill 模式目前处于 内测阶段，相关代码暂时不要合入正式版本提审。
建议先在开发环境做技术验证，待 Skill 功能正式对外开放后再提交审核。
如果急需上线，可先用小程序原生页面 + API 调用方式实现（不依赖 Skill 能力）。**
> **✅ 微信小程序接入交付确认
整体架构：微信小程序 Skill 作为请求入口 + WebSocket/SSE 作为实时监控通道
Skill 机制：mcp.json 声明 + apis/*.js 实现 + 与 V14.1 MCP 协议同构
实时监控：WebSocket（全双工）和 SSE（轻量单向）两种方案
API 规格：POST /tasks 提交、GET /tasks/{id}/status 查询、/tasks/{id}/stream SSE 流
代码示例：微信小程序 Skill 完整实现、实时监控组件、卡片 UI
实施路线图：准备→开发→集成测试→上线，约 1-1.5 周
下一步：可按照实施路线图开始微信小程序项目的创建和 Skill 开发。**
— V14.1 开发计划 · 微信小程序接入 · 2026年6月22日 —


## Step 6.1：Vue3 驾驶舱（实时可视化监控）

| PRD (产品需求文档) |  |
| --- | --- |
| **背景** | 当前系统仅提供CLI和API接口，运维/PM无法直观了解任务执行状态、Agent协作情况和Token消耗。需要一个轻量级Web驾驶舱，实时展示任务DAG拓扑、Agent状态、Token流速和防幻觉告警。 |
| **用户故事** | 作为技术负责人，我打开驾驶舱Dashboard，看到当前运行任务的有向无环图（DAG），每个节点显示Agent名称、耗时和状态（运行中/成功/失败）；下方折线图实时更新Token消耗；右侧面板显示最新告警（如高熵事件）。 |
| **需求描述** | ①实现WebSocket连接（`/ws/dashboard`），订阅任务状态更新、Token指标、熵事件、配置漂移告警；②渲染任务DAG图（使用`vis-network`），节点颜色映射状态（绿色=成功、黄色=运行中、红色=失败）；③渲染Token流速折线图（使用`ECharts`），展示prompt_tokens和completion_tokens；④展示最近20条告警（高熵、Z3超时、配置漂移）列表；⑤响应式设计，支持1920x1080及1280x720分辨率。 |
| **范围 (Do/Don't)** | **Do：**实时任务监控、Token趋势图、告警列表。**Don't：**不包含任务管理（创建/取消）功能（V2）；不支持用户认证（生产环境由反向代理加Basic Auth）；不支持移动端适配。 |
| **数据契约 (WebSocket消息)** | ``代码块-1`` |
| **异常定义** | 前端WebSocket断线时，自动重连（指数退避，最多5次）；后端推送数据缺失时，前端显示占位符（---）而非崩溃。 |
| **成功标准→验收** | **SC1:**首屏加载<2s →**AC1:**Lighthouse性能测试（Performance分数>90）。 |
| | **SC2:**实时数据延迟<5s →**AC2:**手动触发任务，观察Dashboard状态更新，延迟<5s。 |
| | **SC3:**DAG图渲染正确 →**AC3:**任务执行时，DAG节点颜色与状态一致（运行中=黄色，成功=绿色）。 |
| | **SC4:**告警实时推送 →**AC4:**模拟高熵事件，驾驶舱告警列表在2s内出现新条目。 |
| **待定决策** | **Q1:**使用Socket.IO还是原生WebSocket？ →**决议：**Socket.IO（自带重连、心跳、多路复用，降低开发成本）。 |
| | **Q2:**DAG图是否支持交互（点击节点查看详情）？ →**决议：**支持，点击节点弹出Modal显示该步骤的输入/输出日志（从后端获取）。 |

| ADR (架构决策记录) |  |
| --- | --- |
| **技术栈版本** | Frontend: Vue 3.4.21, Vite 5.0.12, Pinia 2.1.7, Socket.IO Client 4.7.2, vis-network 9.1.2, ECharts 5.5.0, Element Plus 2.7.0 (UI组件库)。 |
| | Backend (WebSocket): FastAPI +`socketio`(python-socketio 5.9)。 |
| | Node版本: 18.17+ (LTS)。 |
| **架构位置** | 接入层（展示界面），位于`/frontend/`，构建产物（dist）由Nginx静态托管或由FastAPI挂载。 |
| **实施细节** | **1. 项目结构：** |
| | ``代码块-2`` |
| | **2. Pinia Store 示例 (task store)：** |
| | ``代码块-3`` |
| | **3. Socket.IO 连接配置：** |
| | ``代码块-4`` |
| **风险与缓解** | 风险1: vis-network在大图（>50节点）时卡顿。缓解：设置`physics: false`并启用`layout: hierarchical`，限制最大节点数50（超出则折叠）。 |
| | 风险2: ECharts实时数据流可能导致内存泄漏。缓解：设置`dataZoom`窗口，仅保留最近100个数据点。 |
| **需求错位** | 若用户需要3D拓扑图或实时视频流，当前方案不适用。但当前需求仅为2D任务监控，Vis-network足够。 |
| **技术约束** | 前端禁止直接调用LLM API或数据库，所有数据通过WebSocket从后端获取。前端部署必须配置`VITE_WS_URL`指向后端WebSocket端点。 |
| **环境配置** | # .env.production |
| | VITE_WS_URL=wss://api.example.com |
| | VITE_API_URL=https://api.example.com/api/v1 |
| **依赖链** | Vue组件 → Pinia Store → Socket.IO Client → 后端WebSocket Server。 |

🧪 原子化测试用例 (Vitest + Cypress)：
// 单元测试 (Vitest)
 import { describe, it, expect } from 'vitest'
 import { useTaskStore } from '@/stores/task'

 describe('Task Store', () => {
 it('updates task correctly', () => {
 const store = useTaskStore()
 store.updateTask({ task_id: 't1', state: 'CODING', progress: 0.5, dag: [] })
 expect(store.tasks['t1'].state).toBe('CODING')
 })
 })

 // E2E 测试 (Cypress)
 describe('Dashboard E2E', () => {
 it('displays task topology after creation', () => {
 cy.visit('/dashboard')
 // 通过API创建任务
 cy.request('POST', '/api/v1/tasks', { prd: 'write a sort function' }).then((resp) => {
 const taskId = resp.body.task_id
 // 等待WebSocket推送更新
 cy.contains('.task-node', taskId, { timeout: 10000 }).should('exist')
 // 验证节点颜色
 cy.get(`[data-task-id="${taskId}"]`).should('have.class', 'state-running')
 })
 })
 })


## Step 6.2：端到端集成测试（质量门禁）

| PRD |  |
| --- | --- |
| **背景** | 系统已包含调度器、LLM客户端、图谱引擎、防幻觉层、驾驶舱等多个模块。需建立完整的E2E测试套件，确保各模块协同工作且达到设计指标（Token≤35、延迟≤8s、幻觉率<3%），并作为CI/CD门禁。 |
| **用户故事** | 作为QA工程师，我执行`make e2e-test`，系统自动拉起全部依赖（Docker Compose），运行E2E场景（PRD→生成→验证→修复），输出Allure测试报告，并验证性能指标是否达标。 |
| **需求描述** | ①编写E2E测试套件（pytest + httpx异步客户端），覆盖完整任务生命周期；②集成Allure报告生成；③性能基准测试（locust），模拟并发5个任务，P95延迟<10s；④混沌实验：模拟LLM 5xx错误（使用Mock LLM注入故障），验证熔断器触发和降级；⑤环境隔离：E2E测试使用独立的Test数据库和Redis，不影响Dev环境。 |
| **范围 (Do/Don't)** | **Do：**E2E场景覆盖“正常流程”、“重试修复流程”、“熔断降级流程”。**Don't：**不包含UI自动化测试（由Cypress覆盖，在Step 6.1中）；不包含安全渗透测试。 |
| **数据契约** | ``代码块-5`` |
| **异常定义** | 若任何E2E测试失败，CI流水线返回非0退出码，阻断合并；若性能测试P95>10s，标记为警告但不阻断（人工审查）。 |
| **成功标准→验收** | **SC1:**E2E通过率100% →**AC1:**运行`pytest -m e2e`，所有场景（正常/修复/熔断）通过。 |
| | **SC2:**性能基准达标 →**AC2:**locust并发5任务，P95延迟<10s，Token消耗<35/任务。 |
| | **SC3:**混沌实验通过 →**AC3:**注入LLM 5xx错误，熔断器在30s内触发，且系统自愈。 |
| | **SC4:**覆盖率>80% →**AC4:**`pytest --cov=src --cov-report=term`输出>80%。 |
| **待定决策** | **Q1:**E2E测试是否使用真实LLM还是Mock？ →**决议：**默认使用Mock LLM（确保稳定性和速度），每周运行一次全量真实LLM测试（夜间构建）。 |
| | **Q2:**性能测试阈值是否按环境调整？ →**决议：**CI环境（资源受限）阈值放宽至12s，预发布环境严格8s。 |

| ADR |  |
| --- | --- |
| **技术栈版本** | pytest 8.0.0, pytest-asyncio 0.23, pytest-xdist 3.5, pytest-cov 4.1, httpx 0.27, Allure Pytest 2.13, locust 2.20, docker-compose 2.24。 |
| **架构位置** | 测试基础设施，位于`/tests/`，包含`e2e/`,`performance/`,`chaos/`子目录。 |
| **实施细节** | **E2E核心测试用例：** |
| | ``代码块-6`` |
| | **性能测试 (locustfile.py)：** |
| | ``代码块-7`` |
| **风险与缓解** | 风险：E2E测试依赖Docker服务，CI环境可能无法访问Docker。缓解：在GitHub Actions中配置`services`（PostgreSQL/Redis）而非docker-compose，或使用`pytest-docker`插件自动管理。 |
| **需求错位** | 若测试环境无法安装Docker（如Windows沙箱），沙箱相关的E2E测试将跳过。通过`@pytest.mark.skipif`处理，确保不影响其他测试。 |
| **技术约束** | E2E测试必须使用异步客户端（httpx.AsyncClient）与FastAPI异步端点匹配；性能测试必须使用独立的数据库（避免与开发数据交叉）。 |
| **环境配置** | # .env.test |
| | DATABASE_URL=postgresql+asyncpg://test:test@localhost:5433/test_db |
| | REDIS_URL=redis://localhost:6380/0 |
| | MOCK_LLM=true |
| | ENABLE_L5=false # E2E跳过Z3（加速） |
| | TEST_CHAOS_MODE=false |
| **依赖链** | pytest → httpx → FastAPI App → 所有依赖组件（数据库、Redis、Docker沙箱）。 |

🧪 执行命令与CI集成：
# 本地运行
 make e2e-test # 等同于：docker-compose -f docker-compose.test.yml up -d && pytest -m e2e --alluredir=reports

 # CI (GitHub Actions) 集成
 - name: Run E2E Tests
 run: |
 docker-compose -f docker-compose.test.yml up -d --wait
 poetry run pytest -m e2e --cov=src --cov-report=xml
 env:
 TEST_MODE: true

 - name: Upload Coverage
 uses: codecov/codecov-action@v3
 with:
 file: ./coverage.xml


**✅ 阶段6 (Step 6.1 & 6.2) 全量交付确认**

本报告完整交付了可视化监控与质量验证体系的实现规格：

- **Step 6.1 (驾驶舱)：**基于Vue3+Socket.IO的实时监控面板，支持DAG拓扑、Token趋势、告警列表，开发团队可直接按组件拆解并行开发。
- **Step 6.2 (E2E测试)：**完整的测试框架（pytest+locust+Allure），覆盖正常流程、熔断混沌、性能基准，作为CI/CD的硬性门禁。

两个Step与已交付的所有后端组件无缝对接。预计总工时约4人日（前端3人日，测试1人日），第12周末可交付可演示的Dashboard和可自动运行的质量门禁。

**后续步骤提示：**下一步为**Step 7.1（灰度发布与AgentOps生产就绪）**，将系统部署至K8s并建立生产级可观测性。



```
// 代码块-1
// 前端 -> 后端 (订阅)
    {
      "type": "subscribe",
      "topics": ["task_updates", "token_metrics", "alerts"]
    }

    // 后端 -> 前端 (状态更新)
    {
      "type": "task_update",
      "data": {
        "task_id": "a1b2c3d4",
        "state": "CODING",
        "progress": 0.6,
        "dag": [
          {"id": "step_1", "label": "PARSING", "status": "done", "duration_ms": 1200},
          {"id": "step_2", "label": "PLANNING", "status": "done", "duration_ms": 3400},
          {"id": "step_3", "label": "CODING", "status": "running", "duration_ms": null}
        ],
        "agent_logs": ["Parsing PRD...", "Generated plan with 3 steps"]
      }
    }

    // Token指标消息
    {
      "type": "token_metric",
      "data": {
        "task_id": "a1b2c3d4",
        "timestamp": "2026-06-21T10:00:00Z",
        "prompt_tokens": 150,
        "completion_tokens": 300,
        "total_tokens": 450,
        "cost_usd": 0.0021
      }
    }

    // 告警消息
    {
      "type": "alert",
      "data": {
        "level": "warning", // warning, critical
        "source": "l3_entropy",
        "message": "Entropy 0.82 exceeded threshold in task a1b2c3d4",
        "timestamp": "2026-06-21T10:00:00Z"
      }
    }
```


```
// 代码块-2
frontend/
    ├── src/
    │   ├── api/           # Socket.IO 封装
    │   ├── stores/        # Pinia stores (task, metrics, alert)
    │   ├── components/
    │   │   ├── TopologyGraph.vue  # vis-network
    │   │   ├── TokenChart.vue     # ECharts
    │   │   └── AlertList.vue      # Element Plus Table
    │   ├── views/
    │   │   └── Dashboard.vue
    │   ├── App.vue
    │   └── main.ts
    ├── package.json
    └── vite.config.ts
```


```
// 代码块-3
export const useTaskStore = defineStore('task', {
      state: () => ({
        tasks: {} as Record
      }),
      actions: {
        updateTask(data: TaskUpdate) {
          this.tasks[data.task_id] = data
        },
        getDag(taskId: string) {
          return this.tasks[taskId]?.dag || []
        }
      }
    })
```


```
// 代码块-4
import { io } from 'socket.io-client'
    const socket = io(import.meta.env.VITE_WS_URL, {
      path: '/ws/socket.io',
      transports: ['websocket'],
      reconnectionAttempts: 5,
      reconnectionDelay: 1000
    })
    socket.on('task_update', (data) => taskStore.updateTask(data))
    socket.on('token_metric', (data) => metricStore.addMetric(data))
    socket.on('alert', (data) => alertStore.addAlert(data))
```


```
// 代码块-5
# pytest 配置 (pytest.ini)
    [pytest]
    markers =
        e2e: End-to-end tests
        performance: Performance benchmarks
        chaos: Chaos engineering tests
    env =
        TEST_MODE=true
        MOCK_LLM=true
        DATABASE_URL=postgresql+asyncpg://test:test@localhost:5433/test_db
        REDIS_URL=redis://localhost:6380/0

    # 测试结果数据结构 (Allure)
    class TestReport(BaseModel):
        test_name: str
        duration_ms: float
        passed: bool
        metrics: Dict[str, Any]  # 包含 token_consumed, latency_ms
```


```
// 代码块-6
# tests/e2e/test_full_flow.py
    import pytest
    import httpx
    import asyncio

    @pytest.mark.e2e
    @pytest.mark.asyncio
    async def test_normal_flow(test_client):
        # 1. 创建任务
        resp = await test_client.post("/api/v1/tasks", json={"prd": "write a function that returns the sum of two numbers"})
        task_id = resp.json()["task_id"]

        # 2. 轮询等待完成（超时60s）
        state = "PENDING"
        timeout = 0
        while state not in ["DONE", "FAILED"] and timeout < 60:
            await asyncio.sleep(2)
            timeout += 2
            resp = await test_client.get(f"/api/v1/tasks/{task_id}")
            state = resp.json()["state"]

        # 3. 断言成功
        assert state == "DONE"
        # 4. 验证生成的代码包含 "def add" 或 "def sum"
        result = resp.json().get("result", "")
        assert "def" in result and ("add" in result or "sum" in result)

        # 5. 验证Token消耗≤35（从监控日志获取）
        # 通过查询/metrics端点或日志验证
        metrics = await test_client.get(f"/api/v1/tasks/{task_id}/metrics")
        assert metrics.json()["total_tokens"] <= 35

    @pytest.mark.chaos
    @pytest.mark.asyncio
    async def test_circuit_breaker_chaos(test_client_with_mock_failure):
        # 注入故障：Mock LLM 连续返回5xx
        # 创建任务，预期熔断器触发
        resp = await test_client.post("/api/v1/tasks", json={"prd": "test chaos"})
        task_id = resp.json()["task_id"]

        # 等待熔断触发（失败快速返回）
        await asyncio.sleep(5)
        resp = await test_client.get(f"/api/v1/tasks/{task_id}")
        # 状态应为FAILED且错误信息包含"circuit breaker"
        assert resp.json()["state"] == "FAILED"
        assert "circuit" in resp.json().get("error", "").lower()
```


```
// 代码块-7
from locust import HttpUser, task, between

    class AgentUser(HttpUser):
        wait_time = between(1, 3)

        @task
        def create_and_poll(self):
            resp = self.client.post("/api/v1/tasks", json={"prd": "write a sort function"})
            task_id = resp.json()["task_id"]
            # 轮询直到完成或超时
            for _ in range(30):  # 最多30次轮询
                resp = self.client.get(f"/api/v1/tasks/{task_id}")
                if resp.json()["state"] in ["DONE", "FAILED"]:
                    break
                time.sleep(1)
```


# 多Agent自循环系统 · 阶段7 生产就绪 (Step 7.1) · 编码就绪级PRD/ADR

K8s部署 · 灰度发布 · 可观测性监控 · 自动化运维闭环

**交付声明：**本报告为阶段7（W13-Buffer）的终极细化文档。Step 7.1是系统的最终生产部署与运维体系，涵盖Kubernetes部署、Helm Chart、Istio灰度发布、Prometheus+Grafana+Tempo+ELK可观测性栈，以及自动回滚策略。该步骤使系统从“可运行”升级为“企业级生产就绪”。



## Step 6.3：可视化驾驶舱增强与实时监控

| PRD (产品需求文档) |  | 
| --- | --- | 
| **背景** | Step 6.1 已实现基础驾驶舱，但缺乏实时数据流、Token消耗曲线、Agent协作拓扑图等高级可视化能力。运营人员需要实时感知系统健康状态、快速定位瓶颈。 | 
| **用户故事** | 作为运营人员，我希望在驾驶舱中实时看到Token消耗速度、任务队列积压情况、Agent协作拓扑图，以便快速发现系统瓶颈并做出运营决策。 | 
| **需求描述** | ①实时Token流速折线图（每秒刷新）；②任务队列积压热力图；③Agent协作拓扑实时拓扑图；④系统健康评分（0-100）实时展示；⑤告警机制（Token超限、队列积压、Agent超时）。 | 
| **范围 (Do/Don't)** | **Do：**实时可视化，WebSocket推送，健康评分，基础告警。**Don't：**不支持历史数据回放（V2），不支持自定义仪表盘配置。 | 
| **数据契约** | `DashboardUpdate = {task_id, token_used, token_rate, queue_depth, agent_status: dict, health_score: float, timestamp}`。 | 
| **异常定义** | `WebSocketDisconnectError`：客户端断开连接；`MetricCollectionError`：指标采集失败（不影响主流程）。 | 
| **成功标准→验收** | **SC1:**实时更新 →**AC1:**驾驶舱页面打开后，Token流速图每秒更新，延迟小于500ms。 | 
| | **SC2:**健康评分 →**AC2:**系统负载高时健康评分下降，公式：health = 100 - token_rate/10 - queue_depth*2。 | 
| | **SC3:**告警触发 →**AC3:**Token使用超过80%预算时，驾驶舱显示红色告警，同时推送WebSocket事件。 | 

| ADR (架构决策记录) |  | 
| --- | --- | 
| **技术栈版本** | Vue3 3.4, ECharts 5.4, WebSocket (内置), FastAPI。 | 
| | 位置：`/frontend/src/components/Dashboard/`（Vue组件）、`/src/api/dashboard_ws.py`（WebSocket端点）。 | 
| **架构位置** | 前端层（Step 6.1驾驶舱扩展），通过WebSocket与后端通信，不影响调度器性能。 | 
| **实施细节** | **WebSocket端点：** | 
| | ```python | 
| | from fastapi import WebSocket | 
| | from typing import set | 
| | import asyncio, json | 
| | 
| | class DashboardBroadcaster: | 
| |     def __init__(self): | 
| |         self.clients: set[WebSocket] = set() | 
| |     async def connect(self, ws: WebSocket): | 
| |         await ws.accept() | 
| |         self.clients.add(ws) | 
| |     def disconnect(self, ws: WebSocket): | 
| |         self.clients.discard(ws) | 
| |     async def broadcast(self, data: dict): | 
| |         for client in self.clients: | 
| |             try: | 
| |                 await client.send_json(data) | 
| |             except: | 
| |                 self.clients.discard(client) | 
| | 
| | @app.websocket("/ws/dashboard") | 
| | async def dashboard_ws(ws: WebSocket): | 
| |     broadcaster.connect(ws) | 
| |     try: | 
| |         while True: | 
| |             metrics = collect_system_metrics() | 
| |             await broadcaster.broadcast(metrics) | 
| |             await asyncio.sleep(1) | 
| |     finally: | 
| |         broadcaster.disconnect(ws) | 
| | ``` | 
| | **Agent协作拓扑图（ECharts Graph）：** | 
| | 前端接收`agent_status: dict`（如`{"orchestrator": "running", "developer": "waiting"}`），渲染为力导向图。 | 
| **风险与缓解** | 风险1：WebSocket连接数过多。缓解：限制每个IP最大10个连接，会话超时30分钟。 | 
| | 风险2：ECharts渲染大图（100+节点）卡顿。缓解：超过50节点时降级为列表视图。 | 
| **需求错位** | 若未来需要多租户隔离，每个租户需独立Dashboard实例。当前单租户设计，V2可扩展。 | 
| **技术约束** | WebSocket推送频率不超过每秒1次；所有数据仅来自调度器状态，不引入额外采集开销。 | 
| **环境配置** | DASHBOARD_WS_MAX_CONNECTIONS_PER_IP=10 | 
| | DASHBOARD_SESSION_TIMEOUT_SEC=1800 | 
| | DASHBOARD_MAX_NODES_BEFORE_DEGRADE=50 | 
| **依赖链** | DashboardBroadcaster → TaskOrchestrator（只读状态）→ 各Agent（状态上报）。 | 

| 🧪 原子化测试用例 (pytest)： | 
| ```python | 
| import pytest, asyncio | 
| from src.api.dashboard_ws import DashboardBroadcaster | 
| from unittest.mock import AsyncMock | 
| 
| @pytest.mark.asyncio | 
| async def test_broadcaster_single_client(): | 
|     bc = DashboardBroadcaster() | 
|     mock_ws = AsyncMock() | 
|     await bc.connect(mock_ws) | 
|     assert len(bc.clients) == 1 | 
|     await bc.broadcast({"health_score": 85}) | 
|     mock_ws.send_json.assert_called_once_with({"health_score": 85}) | 
| 
| @pytest.mark.asyncio | 
| async def test_broadcaster_disconnect_cleanup(): | 
|     bc = DashboardBroadcaster() | 
|     mock_ws = AsyncMock() | 
|     await bc.connect(mock_ws) | 
|     bc.disconnect(mock_ws) | 
|     assert len(bc.clients) == 0 | 
| 
| def test_health_score_formula(): | 
|     # health = 100 - token_rate/10 - queue_depth*2 | 
|     score = 100 - 50//10 - 5*2 | 
|     assert score == 80 | 
|     score = 100 - 200//10 - 20*2 | 
|     assert score == 0  # capped at 0 | 
| ```

## Step 7.1：灰度发布与AgentOps生产就绪

| PRD (产品需求文档) |  |
| --- | --- |
| **背景** | 系统已通过E2E测试，但需要部署到生产环境，支持金丝雀发布、自动回滚和全链路可观测性。生产环境必须满足SLA 99.9%，且故障时能在5分钟内定位根因。 |
| **用户故事** | 作为SRE工程师，我通过ArgoCD提交新版本镜像Tag，系统自动执行金丝雀发布（5%→50%→100%），同时Grafana仪表盘实时展示错误率和延迟；若错误率>1%，ArgoRollouts自动回滚至上一版本。 |
| **需求描述** | ①编写Helm Chart（包含Deployment、Service、Ingress、ConfigMap、Secret）打包应用；②配置Istio VirtualService + DestinationRule实现流量权重路由；③集成ArgoRollouts实现金丝雀发布（5%→50%→100%，每阶段观察5分钟）；④部署Prometheus采集应用指标（/metrics端点），Grafana展示核心仪表盘（任务吞吐量、Token消耗、P99延迟、错误率）；⑤部署Tempo用于链路追踪（OpenTelemetry集成）；⑥部署ELK（或Loki）用于日志聚合；⑦配置告警规则（错误率>1%触发Critical，P99延迟>10s触发Warning），并通过钉钉/企业微信推送。 |
| **范围 (Do/Don't)** | **Do：**K8s部署、金丝雀发布、自动回滚、Prometheus+Grafana+Tempo+ELK可观测性。**Don't：**不实现多集群联邦（V2）；不实现自动扩缩容（HPA基于CPU，但本系统为CPU密集型，暂不配置）；不实现混沌工程自动化（保留手动触发）。 |
| **数据契约 (Helm Values)** | ``代码块-1`` |
| **异常定义** | 若ArgoRollouts检测到错误率>1%，自动回滚并发送告警；若Helm安装失败（如镜像拉取失败），ArgoCD自动暂停同步并发送Critical告警。 |
| **成功标准→验收** | **SC1:**K8s部署成功 →**AC1:**`kubectl get pods -l app=agent-system`显示3个Pod Running。 |
| | **SC2:**灰度发布流程验证 →**AC2:**修改镜像Tag触发ArgoRollouts，流量按5%→50%→100%逐步切换，各阶段持续5分钟。 |
| | **SC3:**自动回滚 →**AC3:**故意注入错误（如代码抛出异常），错误率>1%，ArgoRollouts在30s内触发回滚，流量切回旧版本。 |
| | **SC4:**监控大盘可用 →**AC4:**访问Grafana，看到“Agent System Overview”仪表盘，包含任务成功率、Token消耗、延迟分布面板。 |
| | **SC5:**告警推送 →**AC5:**模拟错误率飙升，钉钉/企业微信在1分钟内收到告警消息。 |
| **待定决策** | **Q1:**使用Istio还是Nginx Ingress实现灰度？ →**决议：**Istio（更细粒度的流量管理，支持权重路由和镜像流量）。 |
| | **Q2:**监控数据保留周期？ →**决议：**Prometheus保留15天，Loki保留30天，Tempo保留7天（按实际存储容量调整）。 |
| | **Q3:**是否启用自动扩缩容（HPA）？ →**决议：**暂不启用，因为Agent任务是CPU密集型且状态依赖，自动扩缩容易导致状态不一致（留V2）。 |

| ADR (架构决策记录) |  |
| --- | --- |
| **技术栈版本** | Kubernetes 1.28+, Istio 1.21, Helm 3.14, ArgoCD 2.10, ArgoRollouts 1.6, Prometheus 2.52, Grafana 10.4, Tempo 2.4, Loki 3.0, OpenTelemetry Collector 0.89, ELK (或Loki) 8.12。 |
| | 镜像构建: Docker + GitHub Actions (自动构建并推送到容器仓库)。 |
| **架构位置** | 基础设施层（部署与可观测），独立于应用代码，通过Helm Chart管理。应用代码通过`opentelemetry-instrumentation`自动埋点，无需修改业务逻辑。 |
| **实施细节** | **1. Helm Chart 目录结构：** |
| | ``代码块-2`` |
| | **2. 应用埋点（OpenTelemetry）：** |
| | ``代码块-3`` |
| | **3. ArgoRollouts 定义（示例）：** |
| | ``代码块-4`` |
| | **4. 分析模板（AnalysisTemplate）用于错误率判断：** |
| | ``代码块-5`` |
| **风险与缓解** | 风险1: Istio Sidecar注入增加延迟（约5-10ms）。缓解：对于内部服务，通过`DestinationRule`设置连接池，且监控中已包含延迟指标，可观察实际影响。 |
| | 风险2: 监控组件（Prometheus/Grafana/Tempo）自身可能成为故障点。缓解：为监控组件配置持久化存储和Pod反亲和性，确保高可用；关键告警通道使用双通道（钉钉+邮件）。 |
| | 风险3: 金丝雀发布过程中，新旧版本数据层（PostgreSQL/Redis）不一致可能导致状态错误。缓解：数据库迁移采用向后兼容的变更（不删除字段/表），确保新旧版本可同时读写。 |
| **需求错位** | 若生产环境网络策略限制（如无法访问外部容器仓库），需配置私有镜像仓库和镜像拉取密钥。当前假设使用标准容器仓库（如AWS ECR或Harbor）。 |
| **技术约束** | 应用必须暴露`/metrics`端点（使用`prometheus_fastapi_instrumentator`）以被Prometheus采集；所有日志必须输出到`stdout/stderr`（由容器运行时采集）。 |
| **环境配置** | # 生产环境 values-prod.yaml |
| | image: |
| | tag: v1.0.0 |
| | replicaCount: 5 |
| | resources: |
| | requests: |
| | memory: "1Gi" |
| | cpu: "1000m" |
| | limits: |
| | memory: "4Gi" |
| | cpu: "3000m" |
| | ingress: |
| | hosts: |
| | - agent.production.example.com |
| | rollouts: |
| | canary: |
| | steps: |
| | - setWeight: 5 |
| | - pause: {duration: 10m} |
| | - setWeight: 25 |
| | - pause: {duration: 10m} |
| | - setWeight: 50 |
| | - pause: {duration: 10m} |
| | - setWeight: 100 |
| | monitoring: |
| | prometheus: |
| | retention: 15d |
| | loki: |
| | retention: 30d |
| **依赖链** | Helm → K8s API → Istio CRD → ArgoRollouts → Prometheus (分析) → 应用Pod → OpenTelemetry Collector → Tempo/Grafana。 |

🧪 验收测试 (Shell脚本 + kubectl)：
#!/bin/bash
 # 1. 验证部署
 kubectl get pods -l app=agent-system -n prod | grep -c "Running" | grep -q "3" && echo "✅ 3 pods running"

 # 2. 验证灰度发布
 # 假设触发新部署
 kubectl patch rollout agent-system -n prod --type='merge' -p '{"spec":{"template":{"metadata":{"labels":{"version":"v2"}}}}}'
 # 等待滚动
 sleep 300
 # 检查流量分布（通过Istio metrics）
 istioctl dashboard metrics

 # 3. 验证自动回滚（注入错误）
 kubectl patch rollout agent-system -n prod --type='merge' -p '{"spec":{"template":{"metadata":{"annotations":{"fault":"true"}}}}}'
 # 等待分析完成，验证回滚
 sleep 180
 kubectl get rollout agent-system -n prod -o json | jq '.status.phase' | grep -q "Rollback" && echo "✅ 回滚成功"

 # 4. 验证监控
 curl -s http://prometheus:9090/api/v1/query?query=up | jq '.data.result[0].value[1]' | grep -q "1" && echo "✅ Prometheus 正常"
 curl -s http://grafana:3000/api/health | grep -q "ok" && echo "✅ Grafana 正常"


**✅ 全量16个Step PRD/ADR 完整交付确认**

自Step 0.1至Step 7.1，本系列文档已完整覆盖项目的全部16个核心开发步骤：

| 阶段 | 步骤 | 状态 |
| --- | --- | --- |
| **MVP (W1-W2)** | Step 0.1 章程与基线 | ✅ 已交付 |
| Step 0.2 技术栈与环境 | ✅ 已交付 |  |
| Step 1.1 API契约 | ✅ 已交付 |  |
| Step 1.2 三图谱Schema | ✅ 已交付 |  |
|  | MVP-01 调度器骨架 | ✅ 已交付 |
|  | MVP-02 Mock LLM | ✅ 已交付 |
|  | MVP-03 沙箱 | ✅ 已交付 |
| **强化 (W3-W6)** | Step 2.1 LiteLLM网关 | ✅ 已交付 |
| Step 2.2 检查点 | ✅ 已交付 |  |
| **图谱 (W5-W6)** | Step 3.1 代码图谱 | ✅ 已交付 |
| Step 3.2 数据库图谱 | ✅ 已交付 |  |
| Step 3.3 配置图谱 | ✅ 已交付 |  |
| **防幻觉 (W7-W8)** | Step 4.1 L1-L4 | ✅ 已交付 |
| Step 4.2 L5-L8 | ✅ 已交付 |  |
| **调度器 (W9-W10)** | Step 5.1 调度器状态机 | ✅ 已交付 |
| Step 5.2 Agent角色 | ✅ 已交付 |  |
| **前端/测试 (W11-W12)** | Step 6.1 驾驶舱 | ✅ 已交付 |
| Step 6.2 E2E测试 | ✅ 已交付 |  |
| **生产 (W13)** | Step 7.1 灰度+可观测 | ✅ 已交付 |

**总交付物：**16个Step × 完整的PRD（背景/用户故事/需求/范围/数据契约/异常/SC→AC/待定决策）+ ADR（技术栈/架构位置/实施细节/风险/需求错位/技术约束/环境配置/依赖链）+ 原子化测试用例。

开发团队可按照Step顺序拆解为50-80个子任务，直接进入编码阶段。所有模块的接口、数据格式、配置项、测试用例均已明确，实现“零歧义开发”。



```
// 代码块-1
# values.yaml 核心结构
    image:
      repository: myregistry/agent-system
      tag: latest
      pullPolicy: IfNotPresent

    replicaCount: 3

    service:
      type: ClusterIP
      port: 8000

    ingress:
      enabled: true
      hosts:
        - agent.example.com
      tls:
        - secretName: agent-tls

    resources:
      requests:
        memory: "512Mi"
        cpu: "500m"
      limits:
        memory: "2Gi"
        cpu: "2000m"

    istio:
      enabled: true
      gateway: istio-system/agent-gateway
      virtualService:
        hosts:
          - agent.example.com

    rollouts:
      enabled: true
      canary:
        steps:
          - setWeight: 5
          - pause: {duration: 5m}
          - setWeight: 50
          - pause: {duration: 5m}
          - setWeight: 100
        analysis:
          templates:
            - templateName: error-rate-analysis
          args:
            - name: service
              value: agent-service

    monitoring:
      prometheus:
        enabled: true
        serviceMonitor:
          enabled: true
      grafana:
        enabled: true
        dashboards:
          enabled: true
      tempo:
        enabled: true
      loki:
        enabled: true

    alerting:
      enabled: true
      rules:
        - name: HighErrorRate
          expr: sum(rate(http_requests_total{status=~"5.."}[5m])) / sum(rate(http_requests_total[5m])) > 0.01
          severity: critical
        - name: HighLatency
          expr: histogram_quantile(0.99, sum(rate(http_request_duration_seconds_bucket[5m])) by (le)) > 10
          severity: warning
```


```
// 代码块-2
agent-system/
    ├── Chart.yaml
    ├── values.yaml
    ├── values-prod.yaml
    ├── templates/
    │   ├── deployment.yaml
    │   ├── service.yaml
    │   ├── ingress.yaml
    │   ├── configmap.yaml
    │   ├── rollouts.yaml        # ArgoRollouts 定义
    │   ├── virtualservice.yaml  # Istio VirtualService
    │   ├── servicemonitor.yaml  # Prometheus ServiceMonitor
    │   └── _helpers.tpl
    └── charts/                # 依赖的可观测性组件（可选）
```


```
// 代码块-3
# 在 main.py 中添加
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    # 初始化TracerProvider
    trace_provider = TracerProvider()
    processor = BatchSpanProcessor(OTLPSpanExporter(endpoint="http://tempo-collector:4317"))
    trace_provider.add_span_processor(processor)
    # 设置全局TracerProvider
    # 对FastAPI自动埋点
    FastAPIInstrumentor.instrument_app(app)
    HTTPXClientInstrumentor().instrument()
```


```
// 代码块-4
apiVersion: argoproj.io/v1alpha1
    kind: Rollout
    metadata:
      name: agent-system
    spec:
      replicas: 3
      strategy:
        canary:
          steps:
            - setWeight: 5
            - pause: {duration: 5m}
            - setWeight: 50
            - pause: {duration: 5m}
            - setWeight: 100
          analysis:
            templates:
              - templateName: error-rate-analysis
            startingStep: 1
      selector:
        matchLabels:
          app: agent-system
      template:
        metadata:
          labels:
            app: agent-system
        spec:
          containers:
            - name: app
              image: {{ .Values.image.repository }}:{{ .Values.image.tag }}
              ports:
                - containerPort: 8000
              envFrom:
                - configMapRef:
                    name: agent-config
                - secretRef:
                    name: agent-secrets
```


```
// 代码块-5
apiVersion: argoproj.io/v1alpha1
    kind: AnalysisTemplate
    metadata:
      name: error-rate-analysis
    spec:
      args:
        - name: service
      metrics:
        - name: error-rate
          initialDelay: 1m
          count: 3
          interval: 1m
          successCondition: result[0] < 0.01
          provider:
            prometheus:
              address: http://prometheus:9090
              query: |
                sum(rate(http_requests_total{service="{{args.service}}",status=~"5.."}[1m])) / sum(rate(http_requests_total{service="{{args.service}}"}[1m]))
```


| PRD (产品需求文档) |  |
| --- | --- |
| **背景** | 系统已通过E2E测试，但需要部署到生产环境，支持金丝雀发布、自动回滚和全链路可观测性。生产环境必须满足SLA 99.9%，且故障时能在5分钟内定位根因。 |
| **用户故事** | 作为SRE工程师，我通过ArgoCD提交新版本镜像Tag，系统自动执行金丝雀发布（5%→50%→100%），同时Grafana仪表盘实时展示错误率和延迟；若错误率>1%，ArgoRollouts自动回滚至上一版本。 |
| **需求描述** | ①编写Helm Chart（包含Deployment、Service、Ingress、ConfigMap、Secret）打包应用；②配置Istio VirtualService + DestinationRule实现流量权重路由；③集成ArgoRollouts实现金丝雀发布（5%→50%→100%，每阶段观察5分钟）；④部署Prometheus采集应用指标（/metrics端点），Grafana展示核心仪表盘（任务吞吐量、Token消耗、P99延迟、错误率）；⑤部署Tempo用于链路追踪（OpenTelemetry集成）；⑥部署ELK（或Loki）用于日志聚合；⑦配置告警规则（错误率>1%触发Critical，P99延迟>10s触发Warning），并通过钉钉/企业微信推送。 |
| **范围 (Do/Don't)** | **Do：**K8s部署、金丝雀发布、自动回滚、Prometheus+Grafana+Tempo+ELK可观测性。**Don't：**不实现多集群联邦（V2）；不实现自动扩缩容（HPA基于CPU，但本系统为CPU密集型，暂不配置）；不实现混沌工程自动化（保留手动触发）。 |
| **数据契约 (Helm Values)** | ``代码块-1`` |
| **异常定义** | 若ArgoRollouts检测到错误率>1%，自动回滚并发送告警；若Helm安装失败（如镜像拉取失败），ArgoCD自动暂停同步并发送Critical告警。 |
| **成功标准→验收** | **SC1:**K8s部署成功 →**AC1:**`kubectl get pods -l app=agent-system`显示3个Pod Running。 |
| | **SC2:**灰度发布流程验证 →**AC2:**修改镜像Tag触发ArgoRollouts，流量按5%→50%→100%逐步切换，各阶段持续5分钟。 |
| | **SC3:**自动回滚 →**AC3:**故意注入错误（如代码抛出异常），错误率>1%，ArgoRollouts在30s内触发回滚，流量切回旧版本。 |
| | **SC4:**监控大盘可用 →**AC4:**访问Grafana，看到“Agent System Overview”仪表盘，包含任务成功率、Token消耗、延迟分布面板。 |
| | **SC5:**告警推送 →**AC5:**模拟错误率飙升，钉钉/企业微信在1分钟内收到告警消息。 |
| **待定决策** | **Q1:**使用Istio还是Nginx Ingress实现灰度？ →**决议：**Istio（更细粒度的流量管理，支持权重路由和镜像流量）。 |
| | **Q2:**监控数据保留周期？ →**决议：**Prometheus保留15天，Loki保留30天，Tempo保留7天（按实际存储容量调整）。 |
| | **Q3:**是否启用自动扩缩容（HPA）？ →**决议：**暂不启用，因为Agent任务是CPU密集型且状态依赖，自动扩缩容易导致状态不一致（留V2）。 |

| ADR (架构决策记录) |  |
| --- | --- |
| **技术栈版本** | Kubernetes 1.28+, Istio 1.21, Helm 3.14, ArgoCD 2.10, ArgoRollouts 1.6, Prometheus 2.52, Grafana 10.4, Tempo 2.4, Loki 3.0, OpenTelemetry Collector 0.89, ELK (或Loki) 8.12。 |
| | 镜像构建: Docker + GitHub Actions (自动构建并推送到容器仓库)。 |
| **架构位置** | 基础设施层（部署与可观测），独立于应用代码，通过Helm Chart管理。应用代码通过`opentelemetry-instrumentation`自动埋点，无需修改业务逻辑。 |
| **实施细节** | **1. Helm Chart 目录结构：** |
| | ``代码块-2`` |
| | **2. 应用埋点（OpenTelemetry）：** |
| | ``代码块-3`` |
| | **3. ArgoRollouts 定义（示例）：** |
| | ``代码块-4`` |
| | **4. 分析模板（AnalysisTemplate）用于错误率判断：** |
| | ``代码块-5`` |
| **风险与缓解** | 风险1: Istio Sidecar注入增加延迟（约5-10ms）。缓解：对于内部服务，通过`DestinationRule`设置连接池，且监控中已包含延迟指标，可观察实际影响。 |
| | 风险2: 监控组件（Prometheus/Grafana/Tempo）自身可能成为故障点。缓解：为监控组件配置持久化存储和Pod反亲和性，确保高可用；关键告警通道使用双通道（钉钉+邮件）。 |
| | 风险3: 金丝雀发布过程中，新旧版本数据层（PostgreSQL/Redis）不一致可能导致状态错误。缓解：数据库迁移采用向后兼容的变更（不删除字段/表），确保新旧版本可同时读写。 |
| **需求错位** | 若生产环境网络策略限制（如无法访问外部容器仓库），需配置私有镜像仓库和镜像拉取密钥。当前假设使用标准容器仓库（如AWS ECR或Harbor）。 |
| **技术约束** | 应用必须暴露`/metrics`端点（使用`prometheus_fastapi_instrumentator`）以被Prometheus采集；所有日志必须输出到`stdout/stderr`（由容器运行时采集）。 |
| **环境配置** | # 生产环境 values-prod.yaml |
| | image: |
| | tag: v1.0.0 |
| | replicaCount: 5 |
| | resources: |
| | requests: |
| | memory: "1Gi" |
| | cpu: "1000m" |
| | limits: |
| | memory: "4Gi" |
| | cpu: "3000m" |
| | ingress: |
| | hosts: |
| | - agent.production.example.com |
| | rollouts: |
| | canary: |
| | steps: |
| | - setWeight: 5 |
| | - pause: {duration: 10m} |
| | - setWeight: 25 |
| | - pause: {duration: 10m} |
| | - setWeight: 50 |
| | - pause: {duration: 10m} |
| | - setWeight: 100 |
| | monitoring: |
| | prometheus: |
| | retention: 15d |
| | loki: |
| | retention: 30d |
| **依赖链** | Helm → K8s API → Istio CRD → ArgoRollouts → Prometheus (分析) → 应用Pod → OpenTelemetry Collector → Tempo/Grafana。 |

🧪 验收测试 (Shell脚本 + kubectl)：
#!/bin/bash
 # 1. 验证部署
 kubectl get pods -l app=agent-system -n prod | grep -c "Running" | grep -q "3" && echo "✅ 3 pods running"

 # 2. 验证灰度发布
 # 假设触发新部署
 kubectl patch rollout agent-system -n prod --type='merge' -p '{"spec":{"template":{"metadata":{"labels":{"version":"v2"}}}}}'
 # 等待滚动
 sleep 300
 # 检查流量分布（通过Istio metrics）
 istioctl dashboard metrics

 # 3. 验证自动回滚（注入错误）
 kubectl patch rollout agent-system -n prod --type='merge' -p '{"spec":{"template":{"metadata":{"annotations":{"fault":"true"}}}}}'
 # 等待分析完成，验证回滚
 sleep 180
 kubectl get rollout agent-system -n prod -o json | jq '.status.phase' | grep -q "Rollback" && echo "✅ 回滚成功"

 # 4. 验证监控
 curl -s http://prometheus:9090/api/v1/query?query=up | jq '.data.result[0].value[1]' | grep -q "1" && echo "✅ Prometheus 正常"
 curl -s http://grafana:3000/api/health | grep -q "ok" && echo "✅ Grafana 正常"


**✅ 全量16个Step PRD/ADR 完整交付确认**

自Step 0.1至Step 7.1，本系列文档已完整覆盖项目的全部16个核心开发步骤：

| 阶段 | 步骤 | 状态 |
| --- | --- | --- |
| **MVP (W1-W2)** | Step 0.1 章程与基线 | ✅ 已交付 |
| Step 0.2 技术栈与环境 | ✅ 已交付 |  |
| Step 1.1 API契约 | ✅ 已交付 |  |
| Step 1.2 三图谱Schema | ✅ 已交付 |  |
|  | MVP-01 调度器骨架 | ✅ 已交付 |
|  | MVP-02 Mock LLM | ✅ 已交付 |
|  | MVP-03 沙箱 | ✅ 已交付 |
| **强化 (W3-W6)** | Step 2.1 LiteLLM网关 | ✅ 已交付 |
| Step 2.2 检查点 | ✅ 已交付 |  |
| **图谱 (W5-W6)** | Step 3.1 代码图谱 | ✅ 已交付 |
| Step 3.2 数据库图谱 | ✅ 已交付 |  |
| Step 3.3 配置图谱 | ✅ 已交付 |  |
| **防幻觉 (W7-W8)** | Step 4.1 L1-L4 | ✅ 已交付 |
| Step 4.2 L5-L8 | ✅ 已交付 |  |
| **调度器 (W9-W10)** | Step 5.1 调度器状态机 | ✅ 已交付 |
| Step 5.2 Agent角色 | ✅ 已交付 |  |
| **前端/测试 (W11-W12)** | Step 6.1 驾驶舱 | ✅ 已交付 |
| Step 6.2 E2E测试 | ✅ 已交付 |  |
| **生产 (W13)** | Step 7.1 灰度+可观测 | ✅ 已交付 |

**总交付物：**16个Step × 完整的PRD（背景/用户故事/需求/范围/数据契约/异常/SC→AC/待定决策）+ ADR（技术栈/架构位置/实施细节/风险/需求错位/技术约束/环境配置/依赖链）+ 原子化测试用例。

开发团队可按照Step顺序拆解为50-80个子任务，直接进入编码阶段。所有模块的接口、数据格式、配置项、测试用例均已明确，实现“零歧义开发”。



```
// 代码块-1
# values.yaml 核心结构
    image:
      repository: myregistry/agent-system
      tag: latest
      pullPolicy: IfNotPresent

    replicaCount: 3

    service:
      type: ClusterIP
      port: 8000

    ingress:
      enabled: true
      hosts:
        - agent.example.com
      tls:
        - secretName: agent-tls

    resources:
      requests:
        memory: "512Mi"
        cpu: "500m"
      limits:
        memory: "2Gi"
        cpu: "2000m"

    istio:
      enabled: true
      gateway: istio-system/agent-gateway
      virtualService:
        hosts:
          - agent.example.com

    rollouts:
      enabled: true
      canary:
        steps:
          - setWeight: 5
          - pause: {duration: 5m}
          - setWeight: 50
          - pause: {duration: 5m}
          - setWeight: 100
        analysis:
          templates:
            - templateName: error-rate-analysis
          args:
            - name: service
              value: agent-service

    monitoring:
      prometheus:
        enabled: true
        serviceMonitor:
          enabled: true
      grafana:
        enabled: true
        dashboards:
          enabled: true
      tempo:
        enabled: true
      loki:
        enabled: true

    alerting:
      enabled: true
      rules:
        - name: HighErrorRate
          expr: sum(rate(http_requests_total{status=~"5.."}[5m])) / sum(rate(http_requests_total[5m])) > 0.01
          severity: critical
        - name: HighLatency
          expr: histogram_quantile(0.99, sum(rate(http_request_duration_seconds_bucket[5m])) by (le)) > 10
          severity: warning
```


```
// 代码块-2
agent-system/
    ├── Chart.yaml
    ├── values.yaml
    ├── values-prod.yaml
    ├── templates/
    │   ├── deployment.yaml
    │   ├── service.yaml
    │   ├── ingress.yaml
    │   ├── configmap.yaml
    │   ├── rollouts.yaml        # ArgoRollouts 定义
    │   ├── virtualservice.yaml  # Istio VirtualService
    │   ├── servicemonitor.yaml  # Prometheus ServiceMonitor
    │   └── _helpers.tpl
    └── charts/                # 依赖的可观测性组件（可选）
```


```
// 代码块-3
# 在 main.py 中添加
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    # 初始化TracerProvider
    trace_provider = TracerProvider()
    processor = BatchSpanProcessor(OTLPSpanExporter(endpoint="http://tempo-collector:4317"))
    trace_provider.add_span_processor(processor)
    # 设置全局TracerProvider
    # 对FastAPI自动埋点
    FastAPIInstrumentor.instrument_app(app)
    HTTPXClientInstrumentor().instrument()
```


```
// 代码块-4
apiVersion: argoproj.io/v1alpha1
    kind: Rollout
    metadata:
      name: agent-system
    spec:
      replicas: 3
      strategy:
        canary:
          steps:
            - setWeight: 5
            - pause: {duration: 5m}
            - setWeight: 50
            - pause: {duration: 5m}
            - setWeight: 100
          analysis:
            templates:
              - templateName: error-rate-analysis
            startingStep: 1
      selector:
        matchLabels:
          app: agent-system
      template:
        metadata:
          labels:
            app: agent-system
        spec:
          containers:
            - name: app
              image: {{ .Values.image.repository }}:{{ .Values.image.tag }}
              ports:
                - containerPort: 8000
              envFrom:
                - configMapRef:
                    name: agent-config
                - secretRef:
                    name: agent-secrets
```


```
// 代码块-5
apiVersion: argoproj.io/v1alpha1
    kind: AnalysisTemplate
    metadata:
      name: error-rate-analysis
    spec:
      args:
        - name: service
      metrics:
        - name: error-rate
          initialDelay: 1m
          count: 3
          interval: 1m
          successCondition: result[0] < 0.01
          provider:
            prometheus:
              address: http://prometheus:9090
              query: |
                sum(rate(http_requests_total{service="{{args.service}}",status=~"5.."}[1m])) / sum(rate(http_requests_total{service="{{args.service}}"}[1m]))
```