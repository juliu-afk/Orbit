# 05 · 使用说明 || 05 · Usage Guide

[← 返回目录 Back to index](README.md) · [← 上一章 技术方案](04-technical-stack.md)

> 面向使用者：怎么装、怎么配、怎么跑、怎么用。 || For users: how to install, configure, run, and use.

---

## 5.1 三种启动方式 || 5.1 Three Ways to Launch

### 方式 1：双击 exe（推荐） || Double-click the exe (recommended)

下载 `Orbit.exe`（约 20MB）→ 双击 → 浏览器自动打开 `http://127.0.0.1:18888`。 || Download `Orbit.exe` (~20MB) → double-click → browser opens `http://127.0.0.1:18888` automatically.
无需 Docker/Redis/PostgreSQL（内置 SQLite + 前端）。 || No Docker/Redis/PostgreSQL needed (built-in SQLite + frontend).

### 方式 2：源码启动 || From source

```bash
git clone https://github.com/juliu-afk/Orbit.git
cd Orbit

# 后端（零依赖——SQLite 无需 Docker/Redis）
poetry install
poetry run python src/orbit/launcher.py      # → http://127.0.0.1:18888
# 或开发热重载：
make dev                                       # uvicorn --reload --port 8000

# 前端开发（可选——exe/后端已内置前端）
cd frontend && pnpm install && pnpm dev        # → http://localhost:5173
```

### 方式 3：Docker 全栈 || Full stack via Docker

```bash
cp .env.example .env
make init     # docker compose up + poetry install
make test     # 运行测试
```

启动的基础设施容器（[`docker-compose.yml`](../../docker-compose.yml)）： || Infrastructure containers launched ([`docker-compose.yml`](../../docker-compose.yml)):

| 服务 || Service | 镜像 || Image | 端口 || Port | 用途 || Purpose |
|---|---|---|---|---|
| PostgreSQL 15 | `postgres:15` | 5432 | 审计存储、成本记录 || Audit storage, cost records |
| Redis 7.2 | `redis:7.2` | 6379 | 审计缓存、熔断器状态 || Audit cache, breaker state |
| LiteLLM | `ghcr.io/berriai/litellm:main-v1.40.0-stable` | 4000 | LLM 统一网关 || LLM unified gateway |

### 端口速查 || Port cheatsheet

| 启动方式 || Launch mode | 端口 || Port |
|---|---|---|
| exe 双击 / Docker || exe double-click / Docker | **18888** |
| `make dev` 源码热重载 || `make dev` hot-reload from source | **8000** |

## 5.2 配置项 || 5.2 Configuration

配置走环境变量（[`.env.example`](../../.env.example)）。**禁止在 `.env` 填真实密钥后提交**。 || Configuration via environment variables ([`.env.example`](../../.env.example)). **Never commit real secrets in `.env`**.

| KEY | 默认 || Default | 说明 || Description |
|---|---|---|---|---|
| `APP_ENV` | `dev` | 运行环境 || Runtime environment |
| `DEBUG` | `true` | 调试开关 || Debug switch |
| `PROJECT_NAME` | `Orbit` | 应用名称 || Application name |
| `API_V1_STR` | `/api/v1` | API v1 前缀 || API v1 prefix |
| `DATABASE_URL` | `sqlite+aiosqlite:///./data/graph.db` | 数据库连接串（开发 SQLite / 生产 PostgreSQL） || Database connection string (dev SQLite / prod PostgreSQL) |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis 连接串 || Redis connection string |
| `LITELLM_MASTER_KEY` | `REPLACE_WITH_YOUR_KEY` | LiteLLM 网关主密钥（占位） || LiteLLM gateway master key (placeholder) |
| `LITELLM_PROXY_URL` | `http://localhost:4000` | LiteLLM 代理地址 || LiteLLM proxy URL |
| `OPENAI_API_KEY` | `sk-dummy` | OpenAI 密钥（Mock 阶段占位） || OpenAI key (mock-stage placeholder) |
| `DEEPSEEK_API_KEY` | `sk-dummy` | DeepSeek 密钥（占位） || DeepSeek key (placeholder) |
| `DOCKER_HOST` | `unix:///var/run/docker.sock` | Docker 守护进程地址 || Docker daemon address |
| `SANDBOX_TIMEOUT_SECONDS` | `30` | 沙箱执行超时秒数 || Sandbox execution timeout in seconds |
| `ORBIT_AUTH_TOKEN` | （未设） | 设置后启用 AuthMiddleware 鉴权 || Enables AuthMiddleware authentication when set |
| `CORS_ORIGINS` | （未设） | CORS 白名单 || CORS whitelist |

> 生产还需在 `docker-compose.yml` 设置 `ZAI_API_KEY`（智谱）与 `POSTGRES_*`。 || For production, also set `ZAI_API_KEY` (Zhipu) and `POSTGRES_*` in `docker-compose.yml`.

其他配置目录 `configs/`：`peak_windows.yaml`（高峰时段）、`mcp_clients.yaml`（外部 MCP 服务器）、`k8s/`、`grafana/`、`alertmanager/`、`otel/`、`logstash/`。 || Other config directories `configs/`: `peak_windows.yaml` (peak hours), `mcp_clients.yaml` (external MCP servers), `k8s/`, `grafana/`, `alertmanager/`, `otel/`, `logstash/`.

## 5.3 CLI 命令 || 5.3 CLI

入口 `python -m orbit.cli`（[`src/orbit/cli/`](../../src/orbit/cli/)）： || Entry: `python -m orbit.cli` ([`src/orbit/cli/`](../../src/orbit/cli/)):

| 命令 || Command | 用途 || Description |
|---|---|---|
| `orbit init-packages` | 初始化基础代码包库（写 3 个内置模板到 `~/.orbit/base-packages/`，覆盖时确认） || Initialize base code package library (writes 3 built-in templates to `~/.orbit/base-packages/`, prompts on overwrite) |
| `orbit brief check <path>` | 检查/生成项目说明书：检查 `.orbit/brief.md/.boundaries/.base` 是否存在，缺失则用 GLM-5.2 自动生成 || Check/generate project brief: checks if `.orbit/brief.md/.boundaries/.base` exist, auto-generates missing ones via GLM-5.2 |

## 5.4 前端页面 || 5.4 Frontend Screens

前端路由（[`frontend/src/router/index.ts`](../../frontend/src/router/index.ts)）： || Frontend routes ([`frontend/src/router/index.ts`](../../frontend/src/router/index.ts)):

| 路径 || Route | 视图 || View | 功能 || Function |
|---|---|---|---|---|
| `/boot` | `BootView.vue` | 启动预检——轮询后端健康（env/db/agent），通过后自动跳 `/app` || Boot health check — polls backend health (env/db/agent), auto-navigates to `/app` on success |
| `/app` | `TerminalShell.vue` | **主工作台**——CSS Grid 四区：左文件树 + 中聊天 + 右 Agent 面板 + 底状态栏 || **Main workspace** — CSS Grid 4-zone: left file tree, center chat, right Agent panel, bottom status bar |
| `/mcp` | `McpView.vue` | MCP 服务器管理——查看/刷新外部 MCP 状态与工具列表 || MCP server management — view/refresh external MCP status and tool list |

主工作台 `/app` 内含组件：TerminalChat（终端风格聊天，`$` 前缀 + ANSI + 引用回复）、MonacoPanel（代码编辑器）、AgentInfoPanel（Agent LLM 配置 + 指标）、DAGDrawer / TokenChartDrawer / SearchDrawer / TraceDrawer / ConfigDrawer / CodeGraphDrawer（浮层抽屉）、StatusBar（连接态 + 高峰指示灯）、FileTreePanel、CommandPalette（`/` 触发）、WechatBindingPanel、HITL 人工干预弹窗。 || Main workspace `/app` components: TerminalChat (terminal-style chat, `$` prefix + ANSI + quote reply), MonacoPanel (code editor), AgentInfoPanel (Agent LLM config + metrics), DAGDrawer / TokenChartDrawer / SearchDrawer / TraceDrawer / ConfigDrawer / CodeGraphDrawer (overlay drawers), StatusBar (connection status + peak indicator), FileTreePanel, CommandPalette (`/` trigger), WechatBindingPanel, HITL human-in-the-loop dialog.

界面：Tailwind CSS v4 + 设计 tokens，Tauri 半透明 Mica 毛玻璃窗口（透明度 15–100% / Blur 0–20px，默认 45%/4px）。 || UI: Tailwind CSS v4 + design tokens, Tauri translucent Mica glass window (opacity 15–100% / Blur 0–20px, default 45%/4px).

## 5.5 主用户工作流 || 5.5 Primary User Workflow

```
[1] 启动
    BootView 预检（后端/DB/Agent 连通）→ 自动进 TerminalShell 主面板

[2] 项目注册
    NewSessionDialog → POST /api/v1/projects
    自动生成 .orbit/brief.md（项目说明书）+ CONTEXT.md（聊天上下文）

[3] 需求输入
    WebSocket /chat 自然语言 → ChatterAgent 首触判定：
      chat        → 直接回复
      programming → ClarifierAgent 多轮澄清 → 结构化 PRD
    或直接 Goal API 提交 PRD/模糊需求/批量目录

[4] 任务执行（Goal / Loop 模式）
    POST /api/v1/goal — 统一入口（IntakeRouter 智能判定）
      → DependencyAnalyzer 三层依赖检测
      → MetaOrchestrator 独立 Session 编排 + 自主 PR 合入
      → Agent 5 角色协作（Architect/Developer/Reviewer/QA/ConfigManager）
      → 防幻觉 L1–L9 复合验证
      → CritiqueAgent 批判门禁 + 跨模型审查
    POST /api/v1/loop — 定时重复（cron / 自然语言间隔）

[5] 监控与审查
    驾驶舱实时 WebSocket（DAG 拓扑 + Token 折线 + 告警）
    代码审查 API（POST /api/v1/review）
    TraceViewer 链路瀑布图；ConfigView 配置管理（YAML + Git 历史 + 分支）
    Ponytail 技术债务台账扫描

[6] 审计与可观测
    /observability/health · /metrics · /alerts · /audit · /lessons · /feedback
    备份管理器（SQLite 快照 + SHA256）· 版本注册表 · DR 恢复 CLI

[7] 可选：高峰避让
    OffPeakScheduler 四大厂商高峰判定 → 提交 Goal 时弹窗询问延迟/紧急
    排队队列 + 成本节省报告

[8] 可选：MCP 集成
    configs/mcp_clients.yaml 配置外部 MCP → 启动自动连接注册 → McpView 管理
```

## 5.6 集成通道 || 5.6 Integration Channels

- **微信**：iLink Bot API 双向对话（`/api/v1/wechat` + WechatBindingPanel），绑定管理 + 配置。 || **WeChat**: iLink Bot API bidirectional dialog (`/api/v1/wechat` + WechatBindingPanel), binding management + configuration.
- **MCP 客户端桥**：JSON-RPC 2.0 over stdio，接外部 MCP 服务器工具。 || **MCP Client Bridge**: JSON-RPC 2.0 over stdio, connects external MCP server tools.

---

[← 返回目录](README.md) · [下一章：API 参考 →](06-api-reference.md)
