# Orbit

> 轻量级多 Agent 软件开发自循环系统。
> 自研调度框架，替代 CrewAI 等黑盒框架。五图谱体系（3 引擎：代码/数据库/配置 + 知识图谱 + 元图谱）+ 9 层防幻觉体系 + 毫秒级熔断。

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Coverage](https://img.shields.io/badge/coverage-69%25-orange.svg)](#测试)

## 定位

Orbit 是**多智能体软件开发自循环系统**，锚定在**编排层**——不是单智能体执行工具（Claude Code / Codex），而是让一群 AI 协作完成软件开发全流程的治理系统。

核心价值：编排、治理、验证、追溯。

- **五图谱体系**：3 引擎（代码图谱 Tree-sitter / 数据库图谱 DDL+MVCC / 配置图谱 .env+Nginx+docker-compose）+ 知识图谱（外挂领域知识 + BGE 语义搜索）+ 元图谱（12 种跨图谱关系），统一存 CodeGraph SQLite
- **9 层防幻觉**：L1 静态校验 / L2 动态追踪 / L3 熵监控 / L4 类型检查 / L5 Z3 形式化 / L6 合约验证 / L7 沙箱执行 / L8 配置漂移检测 / L9 动态合规验证
- **毫秒级熔断**：Token 计数器 + 延迟阈值，超限即回滚到上一检查点
- **审计链**：`task_audit_trail` 记录每个 Agent 动作、状态转换、验证结果

## 核心指标

| 指标 | 目标 | 当前 |
|---|---|---|
| 调度层延迟 | ≤1500ms | 已仪表化 |
| 幻觉率 | <3% | 已仪表化 |
| 覆盖率 | ≥80% | 69%（冲刺中） |
| 源码模块 | — | 45 个 |
| Python LOC | — | ~48K |
| 测试文件 | — | 269 个 |

## 技术栈

| 层级 | 组件 | 版本 |
|---|---|---|
| 主语言 | Python | 3.11+ |
| 包管理 | Poetry | 1.8.2 |
| LLM 网关 | LiteLLM | >=1.84 |
| 代码图谱 | CodeGraph（Tree-sitter） | latest |
| 审计存储 | PostgreSQL + Redis | >=15 / >=7 |
| API | FastAPI + Pydantic v2 + Uvicorn | >=0.110 |
| ORM | SQLAlchemy 2.0.25 + Alembic 1.13.0 | - |
| 沙箱 | Docker Engine | >=24 |
| 前端 | Vue3 + Pinia + AG-UI | >=3.4 |
| 桌面壳 | Tauri (Rust WebView) | latest |
| 测试 | pytest / pytest-asyncio / mutmut / Playwright | >=8.0 |

完整技术栈矩阵见 [`docs/开发计划_V14.1.md`](docs/开发计划_V14.1.md) 第 3.4 节。

## 快速开始

### 方式 1：双击 exe（推荐）

下载 `Orbit.exe` (20MB) → 双击 → 浏览器自动打开 `http://127.0.0.1:18888`。

### 方式 2：源码启动

```bash
git clone https://github.com/juliu-afk/Orbit.git
cd Orbit

# 后端（零依赖启动——SQLite 无需 Docker/Redis）
poetry install
poetry run python src/orbit/launcher.py
# → http://127.0.0.1:18888

# 前端开发（可选——exe/后端已内置前端）
cd frontend && pnpm install && pnpm dev
# → http://localhost:5173
```

### 方式 3：Docker 全栈

```bash
cp .env.example .env
make init   # docker compose up + poetry install
make test   # 453 测试
```

## 项目结构

```
orbit/
├── pyproject.toml                  # Poetry 管理
├── Makefile                        # init / test / lint / run
├── docker-compose.yml              # PostgreSQL / Redis / LiteLLM
├── .env.example
├── src/orbit/                      # 主源码（45 个模块）
│   ├── scheduler/                  # 调度器状态机 + DAG + 离线调度
│   ├── graph/                      # 图谱引擎（代码/数据库/配置 + 元图谱）
│   │   ├── engines/                # code_graph / config_graph / db_graph
│   │   └── meta_graph.py           # 12 种跨图谱关系
│   ├── hallucination/              # L1-L8 防幻觉纵深防御
│   ├── compliance/                 # L9 动态合规验证
│   ├── sandbox/                    # Docker 隔离执行
│   ├── checkpoint/                 # 检查点管理（保存/回滚）
│   ├── agents/                     # Agent 工厂 + 10 角色定义
│   ├── gateway/                    # LiteLLM 网关 + 三层模型路由
│   ├── knowledge/                  # 知识图谱 + BGE 向量语义搜索
│   ├── modes/                      # 交互协议层（architect/clarify/review）
│   ├── memory/                     # 分层记忆（情节/画像/决策日志）
│   ├── evolution/                  # 自我进化（GEPA + SCOPE + 蒸馏）
│   ├── context/                    # 上下文预构建体系（prebuilders/builders/scanners）
│   ├── compression/                # Token 预算 + 上下文压缩
│   ├── observability/              # OpenTelemetry + 审计 + 反馈引擎
│   ├── metacognition/              # 元认知监控层
│   ├── api/                        # FastAPI 路由（31 个端点文件）
│   │   ├── routes/                 # API 端点
│   │   ├── schemas/                # Pydantic 模型
│   │   └── middleware/             # 中间件
│   ├── communication/              # Agent 消息总线（4 模式 + 幂等）
│   ├── tools/                      # 工具注册中心 + MCP Server
│   ├── compose/                    # 多 Agent 编排 + 技能方法论
│   ├── resource_guard/             # 资源熔断（令牌桶 + 预算 + 降级）
│   ├── backup/                     # 快照 + SHA256 校验 + 恢复
│   ├── versioning/                 # 版本注册表 + Schema 迁移
│   ├── worktree/                   # Git Worktree 隔离
│   ├── loop/                       # Goal+Loop 闭环调度
│   ├── goal/                       # Goal 生命周期管理
│   ├── dream/                      # /dream 异步后台任务
│   ├── brief/                      # 简洁规则引擎
│   ├── review/                     # 代码审查引擎
│   ├── security/                   # 安全扫描
│   ├── projects/                   # 项目注册表
│   ├── sessions/                   # 会话管理
│   ├── sharding/                   # 动态任务分片
│   ├── stream/                     # SSE 流式响应
│   ├── router/                     # 智能路由（RouterAgent + CC_SWITCH）
│   ├── lsp/                        # LSP 协议支持
│   ├── prompt/                     # Prompt 构建器
│   ├── events/                     # EventBus 事件总线
│   ├── files/                      # 文件操作
│   ├── integration/                # 外部集成（微信等）
│   ├── actors/                     # Actor 生命周期
│   ├── cli/                        # CLI 入口
│   ├── core/                       # 配置、日志、公共工具
│   └── infrastructure/             # DB 引擎、Session
├── frontend/                       # Vue3 + Pinia + AG-UI 驾驶舱
│   └── src/
│       ├── views/                  # Boot / Dashboard / TerminalShell
│       ├── components/             # 20+ 组件目录（chat/audit/charts/dag/ops/…）
│       ├── composables/            # 组合式函数
│       ├── stores/                 # Pinia 状态
│       └── router/                 # Vue Router
├── src-tauri/                      # Tauri 桌面壳（Rust）
├── tests/
│   ├── unit/                       # 197 个单元测试文件
│   ├── integration/                # 10 个集成测试文件
│   ├── e2e/                        # Playwright E2E
│   ├── ab/                         # A/B 测试
│   ├── chaos/                      # 混沌测试
│   └── lib/                        # 自定义断言库
├── alembic/                        # 数据库迁移
├── configs/                        # k8s / otel / alertmanager / grafana
├── chart/orbit/                    # Helm Chart
├── docs/
│   ├── charter.md                  # 项目章程（Step 0.1）
│   ├── 开发计划_V14.1.md           # 总体设计
│   ├── 产品路线图.md               # 版本历史 + 模块状态
│   ├── 已实现功能清单.md           # 功能→PR→版本号对照
│   ├── PRD+ADR_*.md                # 16+ Step 设计文档
│   └── requirements/               # 按迭代管理需求文档
├── scripts/                        # 构建/上下文生成脚本
└── Deliverables/                   # Tauri 桌面壳产物（Orbit.exe）
```

## 开发

完整开发流程见 [`AGENTS.md`](AGENTS.md)。关键约定：
- 四阶段工作流：PRD → 技术方案 → 编码+审查 → 测试门禁
- Conventional Commits，subject ≤50 字符
- 禁止 `git add -A`，精确指定文件
- 中文注释，面向非编程专业人士审计

## 文档

- [开发计划 V14.1](docs/开发计划_V14.1.md) — 总体设计（26 章）
- [项目章程](docs/charter.md) — 度量基线、范围、风险
- [产品路线图](docs/产品路线图.md) — 版本历史 + 迭代计划
- [已实现功能清单](docs/已实现功能清单.md) — 功能→PR→版本号对照
- [16+ Step PRD+ADR](docs/) — 逐步骤字段级契约

## 路线图

| 阶段 | Step | 内容 | 状态 |
|---|---|---|---|
| W1-W2 | 0.1-1.2 | 章程 / 环境 / API 契约 / 图谱 Schema | ✅ |
| W3-W4 | 2.1-2.2 | LiteLLM 网关 / 检查点 | ✅ |
| W5-W6 | 3.1-3.4 | 图谱引擎 + 知识图谱 | ✅ |
| W7-W8 | 4.1-4.3 | 9 层防幻觉 L1-L9 | ✅ |
| W9-W10 | 5.1-5.7 | 调度器状态机 + Agent 角色 + DAG | ✅ |
| W11-W12 | 6.1-6.3 | 驾驶舱 / E2E | ✅ |
| W13 | 7.1-7.5 | 灰度发布 + 可观测性 + DR | ✅ |
| W14+ | 8-10 | 元图谱 + IDE 追赶 + 驾驶舱翻新 | ✅ |
| 当前 | — | 覆盖率冲刺 + 交互协议层 + 自我进化 | 🔄 |

## 贡献

见 [CONTRIBUTING.md](CONTRIBUTING.md) 和 [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)。

## License

[MIT](LICENSE)
