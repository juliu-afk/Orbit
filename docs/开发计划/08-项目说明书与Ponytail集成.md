# 08 — 项目说明书 + 基础代码包库 + Ponytail 集成

**发布日期**：2026-07-02 | **状态**：实现中（A: 5/7, B: 6/6 ✅, C: 3/4）

**核心目标**：Orbit 接到项目时自动生成/索检结构化项目说明书和基础代码包，注入 Agent prompt，同时集成 Ponytail 决策阶梯约束代码生成行为。三层边界执行体系保证代码一致性。

---

## 目录

- [1. 问题陈述](#1-问题陈述)
- [2. Part A：项目说明书自动生成系统](#2-part-a项目说明书自动生成系统)
- [3. Part B：Ponytail 决策阶梯集成](#3-part-bponytail-决策阶梯集成)
- [4. Part C：CONTEXT.md 层级 + RUNE + 测试驱动 Prompt](#4-part-ccontextmd-层级--rune--测试驱动-prompt)
- [5. 五层边界执行体系](#5-五层边界执行体系)
- [6. 实施路线图](#6-实施路线图)
- [7. 技术规格](#7-技术规格)

---

## 1. 问题陈述

### 现状

Orbit 注册项目时仅记录 `name`、`local_path`、`repo_url`、`description` 等元数据。LLM Agent 每次任务需从零理解项目结构、技术栈、代码规范——重复消耗 token，产出不一致。

### 目标

1. 项目注册时自动生成 `.orbit/brief.md`（6 段式项目说明书）
2. D 盘集中基础代码包库 `D:\OrbitBasePackages\`，LLM 自决策是否注入
3. Ponytail 6 级决策阶梯约束 DeveloperAgent 代码生成
4. 五层边界执行体系：声明 → Prompt → 静态分析 → Pre-commit → ReviewAgent

---

## 2. Part A：项目说明书自动生成系统

### 2.1 新增模块：`src/orbit/brief/`

```
src/orbit/brief/
├── __init__.py          # 公共 API
├── models.py            # BriefRecord, BriefSection, BoundaryRule 数据结构
├── checker.py           # 检查 brief/base/boundaries 是否就绪
├── generator.py         # BriefGenerator — 使用 GLM-5.2 分析代码库生成说明书
├── storage.py           # 读写 .orbit/ 下的所有文件
├── injector.py          # 注入说明书到 PromptBuilder context 层
├── boundaries.py        # 边界规则解析 + lint/pre-commit 配置生成
└── package_library.py   # D:\OrbitBasePackages\ 的索检与注册
```

### 2.2 项目说明书结构（`.orbit/brief.md`）

```markdown
# Project Brief: <项目名>

## 1. 摘要
3-5 句：解决什么问题、用户是谁、成功标准是什么。

## 2. 技术栈
语言、框架、版本号、关键依赖。

## 3. 命令
构建、测试、lint、启动——精确可执行的 shell 命令。

## 4. 目录结构
每个目录的用途，一行说明。

## 5. 代码风格与模式
命名规范、格式化规则、带代码片段的模式示例。

## 6. 边界
- 必须做：<强制规则>
- 需确认：<需人工决策>
- 禁止做：<红线>
```

### 2.3 基础代码包库（`D:\OrbitBasePackages\`）

```
D:\OrbitBasePackages\
├── index.json                          # 总索引：所有包的元数据
│   [{                                  #   格式：
│     "id": "python-fastapi-minimal",   #     唯一 ID
│     "language": "python",             #     语言
│     "framework": "fastapi",           #     框架
│     "features": ["async", "pydantic", "sqlalchemy"],  # 特性标签
│     "description": "...",             #     一句话描述
│     "file_count": 12,                 #     文件数（估算 token 成本）
│     "estimated_tokens": 3500,         #     预估 token 数
│     "cookiecutter_compat": true,      #     是否兼容 Cookiecutter
│     "path": "python-fastapi-minimal/" #     库内路径
│   }]
├── python-fastapi-minimal/
│   ├── manifest.yaml        # 本包详细描述
│   └── template/            # 参数化模板（Cookiecutter 兼容）
│       ├── cookiecutter.json
│       └── {{project_slug}}/
│           ├── pyproject.toml
│           ├── src/__init__.py
│           ├── src/models/
│           ├── src/services/
│           ├── src/api/
│           └── tests/
├── react-vite-minimal/
│   ├── manifest.yaml
│   └── template/
└── ...（随使用积累增长）
```

### 2.4 索检 + LLM 决策流程

```
项目注册
  │
  ├─→ 1. CodeGraph 扫描代码库
  │     提取：[语言, 框架, 目录结构, 已有文件数]
  │
  ├─→ 2. 索检 D:\OrbitBasePackages\index.json
  │     匹配规则：语言相同 + 框架相同 + 特性标签交集 > 50%
  │     返回：候选包列表（仅 manifest 摘要，不含代码）
  │
  ├─→ 3. GLM-5.2 成本/收益决策（~200 tokens）
  │     输入：项目特征 + 候选包摘要（名称、描述、文件数、预估 token）
  │     输出：{ decision: "full"|"skeleton"|"skip",
  │             packages: [...],
  │             reason: "已有 12 个文件含自定义 auth，fastapi-full 会与现有代码冲突，
  │                      但 fastapi-minimal 的 pyproject.toml 和目录结构可复用 → skeleton" }
  │
  ├─→ 4. 按决策注入
  │     full:     模板全部文件渲染后写入 .orbit/base/ + 注入 Prompt
  │     skeleton: 仅目录树 + 关键配置文件名注入 Prompt
  │     skip:     不注入，仅记录决策理由
  │
  └─→ 5. 如果 LLM 决策 skip 或无匹配包
        生成新的基础代码包（GLM-5.2）→ 注册到 D:\OrbitBasePackages\
```

### 2.5 触发时机

| 触发点 | 条件 | 动作 |
|--------|------|------|
| `POST /api/v1/projects` | 新项目注册 | 异步：check → generate → store |
| `ComposeOrchestrator.execute()` | spec 指向新项目 | 同步：check → generate if missing |
| `GET /api/v1/projects/{name}/brief` | 手动请求 | 返回现有或 force-regenerate |
| `POST /api/v1/projects/{name}/brief/refresh` | 代码库重大变更后 | 重新分析 + 重新生成 |

### 2.6 Prompt 注入

修改 `src/orbit/prompt/builder.py` — `_build_context()`：

```
L1: stable（角色 + 工具 + 规则）
L2: 确定性事实（六图谱查询结果）
L2.5: 【新增】项目说明书 → 读取 .orbit/brief.md + .orbit/context.md 层级
L3: 任务动态上下文（PRD 摘要、历史步骤）
L4: Agent 工作记忆
L5: 跨任务长期记忆
```

入注量控制：项目说明书 ≤ 2000 tokens（`.orbit/brief.md` 设计上保持精简）。基础代码包按 LLM 决策控制。

---

## 3. Part B：Ponytail 决策阶梯集成

### 3.1 新增模块：`src/orbit/prompt/ponytail_rules.py`

Ponytail 6 级决策阶梯 + 安全底线 + 补充规则，作为 Python 常量存储，按需注入 DeveloperAgent prompt。

### 3.2 自适应强度

```python
def determine_ponytail_mode(
    task_type: str,        # "feature" | "bugfix" | "refactor" | "unknown"
    project_files: int,    # 已有文件数，0 = 新项目
    user_override: str | None = None  # 环境变量/API 设置
) -> str:  # "off" | "lite" | "full" | "ultra"
```

| 场景 | 自动模式 | 理由 |
|------|---------|------|
| 新项目/空目录 | `ultra` | 极简起步 |
| 成熟项目 + feature | `full` | 尊重已有模式 |
| 成熟项目 + bugfix | `lite` | 专注修复，建议不强制 |
| 成熟项目 + refactor | `ultra` | 鼓励删冗余 |
| 用户显式设置 | 以用户为准 | 始终可覆盖 |

### 3.3 DeveloperAgent 集成

修改 `src/orbit/agents/factory.py` — `DeveloperAgent.system_prompt()`：
- 模板注入后追加 Ponytail 规则段
- 根据当前模式裁剪规则文本（ultra 比 full 更激进）

### 3.4 Ponytail Review 维度

ReviewAgent 新增 `over-engineering` 审查维度：
- 检查每处修改是否违反决策阶梯
- 标记：不必要的抽象、stdlib 可替代、死代码、过早泛化
- 输出格式：`path:line: <severity>: <问题> → <更懒的替代>`

### 3.5 Ponytail 债务台账

`GET /api/v1/projects/{name}/ponytail-debt`：
- 扫描代码库 `# ponytail:` 注释
- 聚合为台账：[文件, 行号, 天花板, 升级触发条件]
- 存入 CodeGraph 可查询

---

## 4. Part C：CONTEXT.md 层级 + RUNE + 测试驱动 Prompt

### 4.1 CONTEXT.md 层级

Orbit 自动生成并强制注入目录级上下文文件：

```
repo/
├── .orbit/brief.md             # 项目级说明书
├── src/
│   ├── .orbit/context.md       # "核心业务逻辑——所有 models/services/api 路由"
│   ├── api/
│   │   └── .orbit/context.md   # "FastAPI 路由——仅参数校验+响应格式化，不写 SQL"
│   └── models/
│       └── .orbit/context.md   # "SQLAlchemy 模型——所有表映射，金额用 Decimal"
└── tests/
    └── .orbit/context.md       # "pytest——fixtures 在 conftest.py，金额断言精确到分"
```

**强制机制**：
- PromptBuilder 每次构建 context 时，从目标文件所在目录向上走，收集所有 `.orbit/context.md`
- 最近优先（子目录覆盖父目录）
- Agent 不可绕过——不读这些文件就得不到 context 注入

**生成时机**：
- 项目注册时 BriefGenerator 分析目录树，≥10 个子目录的项目自动生成
- `POST /api/v1/projects/{name}/context/refresh` 手动刷新

### 4.2 RUNE 启发式 Spec 增强

增强 Compose Spec 模型（`src/orbit/compose/models.py`），Task 新增可选字段：

```yaml
tasks:
  - id: "create-user-service"
    # 现有字段
    title: "用户服务"
    description: "实现用户 CRUD"

    # 新增 RUNE 启发字段（均可选）
    signature: "async def create_user(db: AsyncSession, data: UserCreate) -> User"
    behavior:
      - "WHEN email 已存在 THEN raise DuplicateError"
      - "WHEN password < 8 字符 THEN raise ValidationError"
    tests:
      - "assert (await create_user(db, valid_data)).email == valid_data.email"
      - "await create_user(db, duplicate_email_data)  # expect DuplicateError"
```

### 4.3 测试驱动 Prompt

当 Compose Task 包含 `tests` 字段时，ComposeOrchestrator 将断言注入 DeveloperAgent 的 volatile prompt 层：

```
## 验收标准（必须全部通过）
以下断言必须在任务完成前通过：
- assert (await create_user(db, valid_data)).email == valid_data.email
- await create_user(db, duplicate_email_data)  # expect DuplicateError
```

研究支撑：提示中包含断言可提升 pass@5 约 20-30 个百分点。

---

## 5. 五层边界执行体系

纯 Markdown 文本对 LLM 只是建议——必须有多层强制执行才能保证一致性。

### 5.1 边界声明文件（`.orbit/boundaries/rules.yaml`）

```yaml
version: "1.0"
rules:
  - id: "no-float-money"
    description: "金额一律用 Decimal，禁止 float/double"
    severity: error
    category: finance
    enforcement:
      static_analysis:
        ruff_rules: ["S301"]
        grep_pattern: 'float\(.*(?:amount|money|price|元|金额)'
      pre_commit: true
      review_checklist: true

  - id: "no-sql-injection"
    description: "禁止字符串拼接 SQL，必须用参数化查询"
    severity: error
    category: security
    enforcement:
      static_analysis:
        bandit_rules: ["B608"]
      pre_commit: true
      review_checklist: true
      runtime_assert: false

  - id: "no-eval"
    description: "禁止 eval/exec/compile"
    severity: error
    category: security
    enforcement:
      static_analysis:
        ruff_rules: ["S307"]
      pre_commit: true
      review_checklist: true

  - id: "no-unapproved-dependency"
    description: "新增依赖需人工确认"
    severity: warning
    category: governance
    enforcement:
      static_analysis: {}  # 无现成 lint 规则，靠 ReviewAgent
      review_checklist: true
```

### 5.2 五层执行

| 层 | 机制 | 何时触发 | LLM 可绕过？ |
|----|------|---------|-------------|
| **L1 声明** | `rules.yaml` — 机器可读规则定义 | 项目创建时生成 | N/A（数据） |
| **L2 Prompt** | 规则文本注入 Agent system prompt | 每次 Agent 调用 | **是** — LLM 可忽略文本 |
| **L3 静态分析** | 自动生成 ruff/eslint/bandit 配置 | 项目创建 + 规则变更时 | **否** — 确定性工具 |
| **L4 Pre-commit** | 自动生成 `.pre-commit-config.yaml` hooks | 项目创建时写入 | **否** — `git commit` 触发 |
| **L5 ReviewAgent** | 审查维度自动包含边界合规 | 每次代码审查 | **否** — 独立 Agent 审查 |

关键：L2（Prompt）只是提醒。L3-L5 是真正不可绕过的门禁。

### 5.3 生成流程

```
rules.yaml 声明
  │
  ├─→ L2: 生成 rules_text → 注入 Agent prompt
  ├─→ L3: 生成 ruff.toml / .eslintrc.json → 写入项目根
  ├─→ L4: 生成 .pre-commit-config.yaml → 写入项目根
  └─→ L5: 生成 review_checklist → 注入 ReviewerAgent
```

---

## 6. 实施路线图

### Part A：项目说明书 + 基础代码包库（预计 4 天）

| 步 | 内容 | 文件 |
|----|------|------|
| A1 | ✅ 创建 `src/orbit/brief/` 7 个核心文件 | models.py, checker.py, storage.py, generator.py, injector.py, package_library.py, boundaries.py |
| A2 | ✅ 创建 `D:\OrbitBasePackages\` 库 + index.json + 3 个初始包 | python-fastapi-minimal, react-vite-minimal, python-cli-minimal |
| A3 | ✅ 修改 PromptBuilder 注入 L2.5 | builder.py |
| A4 | ✅ 修改 project API 触发流程 | routes/projects.py |
| A5 | ✅ 修改 ComposeOrchestrator 触发 | compose/orchestrator.py |
| A6 | ✅ 更新 desktop_launcher.py / orbit.spec | launcher.py, orbit.spec |
| A7 | ❌ 单元 + 集成测试 | tests/unit/test_brief_*.py — 未创建 |

### Part B：Ponytail 决策阶梯（预计 2 天）

| 步 | 内容 | 文件 |
|----|------|------|
| B1 | ✅ 创建 Ponytail 规则模块 | prompt/ponytail_rules.py |
| B2 | ✅ 修改 DeveloperAgent 注入 | agents/factory.py |
| B3 | ✅ 添加 PONYTAIL_MODE 配置 | core/config.py |
| B4 | ✅ Ponytail review 维度 | review/ponytail.py |
| B5 | ✅ Ponytail debt API | api/routes/ponytail_debt.py |
| B6 | ✅ 测试 | tests/unit/test_ponytail_*.py |

### Part C：CONTEXT.md + RUNE + 测试驱动（预计 2 天）

| 步 | 内容 | 文件 |
|----|------|------|
| C1 | ✅ CONTEXT.md 自动生成 + PromptBuilder 强制注入 | brief/generator.py（扩展）, prompt/builder.py |
| C2 | ✅ Compose Spec 模型增强（signature/behavior/tests） | compose/models.py |
| C3 | ✅ 测试断言注入 DeveloperAgent prompt | compose/orchestrator.py |
| C4 | ❌ 测试 | tests/unit/test_context_md.py, tests/unit/test_spec_enhancement.py — 未创建 |

---

## 7. 技术规格

### 7.1 模型使用

| 环节 | 模型 | 理由 |
|------|------|------|
| 项目说明书生成 | `openai/glm-5.2`（Tier 3） | 用户指定——最强推理 |
| 基础代码包 LLM 决策 | `openai/glm-5.2`（Tier 3） | 用户指定——成本/收益权衡 |
| 基础代码包内容生成 | `openai/glm-5.2`（Tier 3） | 用户指定——代码质量最关键 |
| CONTEXT.md 生成 | `openai/glm-4.7-flash`（免费） | 摘要任务，不需最强模型 |
| Ponytail 规则注入 | 无 LLM 成本 | 纯文本拼接，确定性操作 |

### 7.2 Token 预算

| 组件 | 预估 token | 频次 |
|------|-----------|------|
| `.orbit/brief.md` | ≤ 2000 | 每次 Agent 调用（可缓存） |
| `.orbit/context.md` × N | ≤ 500/文件 | 每次 Agent 调用（可缓存） |
| 基础代码包（full） | 2000-5000 | 仅新项目首次，后续可缓存 |
| 基础代码包 LLM 决策 | ~200 | 仅新项目注册时 |
| Ponytail 规则段 | ~400 | 每次 DeveloperAgent 调用 |

### 7.3 关键依赖

- 现有：`src/orbit/gateway/client.py`（LLMClient + GLM-5.2）、`src/orbit/prompt/builder.py`（PromptBuilder）、`src/orbit/graph/`（CodeGraph）
- 新增：无外部依赖——全部复用 `litellm`、`PyYAML`（已有）、`jinja2`（已有）
