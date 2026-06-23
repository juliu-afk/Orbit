# Orbit

> 轻量级多 Agent 软件开发自循环系统。
> 自研调度框架，替代 CrewAI 等黑盒框架。三图谱（代码/数据库/配置）+ 8 层防幻觉体系 + 毫秒级熔断。

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Coverage](https://img.shields.io/badge/coverage-%E2%89%A580%25-green.svg)](#测试)

## 定位

Orbit 是**多智能体软件开发自循环系统**，锚定在**编排层**——不是单智能体执行工具（Claude Code / Codex），而是让一群 AI 协作完成软件开发全流程的治理系统。

核心价值：编排、治理、验证、追溯。

- **三图谱**：代码图谱（Tree-sitter）+ 数据库图谱（DDL/MVCC 快照）+ 配置图谱（.env/Nginx/docker-compose），统一存 CodeGraph SQLite
- **8 层防幻觉**：L1 静态校验 / L2 动态追踪 / L3 熵监控 / L4 沙箱执行 / L5 合约验证 / L6 双向合约 / L7 形式化验证（Z3）/ L8 配置漂移检测
- **毫秒级熔断**：Token 计数器 + 延迟阈值，超限即回滚到上一检查点
- **审计链**：`task_audit_trail` 记录每个 Agent 动作、状态转换、验证结果

## 核心指标

| 指标 | 目标 | 说明 |
|---|---|---|
| 调度层延迟 | ≤1500ms | 不含验证层 |
| 幻觉率 | <3% | 验证层误判样本 / 总任务 |
| CI 覆盖率 | ≥80% | 调度器/防幻觉纯函数 100% |

## 技术栈

| 层级 | 组件 | 版本 |
|---|---|---|
| 主语言 | Python | 3.11+ |
| 包管理 | Poetry | 1.8.2 |
| LLM 网关 | LiteLLM | >=1.40 |
| 代码图谱 | CodeGraph（Tree-sitter） | latest |
| 审计存储 | PostgreSQL + Redis | >=15 / >=7 |
| API | FastAPI + Pydantic v2 + Uvicorn | >=0.110 |
| ORM | SQLAlchemy 2.0.25 + Alembic 1.13.0 | - |
| 沙箱 | Docker Engine | >=24 |
| 前端 | Vue3 + Pinia + AG-UI | >=3.4 |
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
├── src/orbit/
│   ├── scheduler/                  # 调度器状态机（Step 5.x）
│   ├── graph/                      # 三图谱：code / database / config（Step 3.x）
│   ├── hallucination/              # L1-L8 防幻觉（Step 4.x）
│   ├── sandbox/                    # Docker 隔离执行（Step 1.x）
│   ├── gateway/                    # LiteLLM 网关（Step 2.1）
│   ├── checkpoint/                 # 检查点管理（Step 2.2）
│   ├── audit/                      # task_audit_trail + 成本记录（Step 6.4）
│   ├── core/                       # 配置、日志、公共工具
│   ├── api/                        # FastAPI 路由 + Pydantic 模型
│   └── infrastructure/             # DB 引擎、Session
├── frontend/                       # Vue3 + Pinia + AG-UI 驾驶舱（Step 6.1）
├── tests/
│   ├── unit/
│   ├── integration/
│   └── e2e/                        # Playwright
├── alembic/                        # 数据库迁移
└── docs/
    ├── charter.md                  # 项目章程（Step 0.1）
    ├── 开发计划_V14.1.md
    └── PRD+ADR_*.md                # 16 Step 设计文档
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
- [16 Step PRD+ADR](docs/) — 逐步骤字段级契约

## 路线图

| 阶段 | Step | 内容 |
|---|---|---|
| W1-W2 | 0.1-1.2 | 章程 / 环境 / API 契约 / 三图谱 Schema |
| W3-W4 | 2.1-2.2 | LiteLLM 网关 / 检查点 |
| W5-W6 | 3.1-3.3 | 三图谱实现 |
| W7-W8 | 4.1-4.2 | 8 层防幻觉 |
| W9-W10 | 5.1-5.7 | 调度器状态机 |
| W11-W12 | 6.1-6.3 | 驾驶舱 / E2E |
| W13 | 7.1 | 灰度发布 + 可观测性 |

## 贡献

见 [CONTRIBUTING.md](CONTRIBUTING.md) 和 [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)。

## License

[MIT](LICENSE)