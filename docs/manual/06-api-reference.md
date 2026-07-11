# 06 · API 参考 · API Reference

[← 返回目录 Back to index](README.md) · [← 上一章 使用说明](05-usage-guide.md)

> 路由注册见 [`src/orbit/api/main.py`](../../src/orbit/api/main.py)（`_ROUTE_MODULES` / `_ROUTE_SPEC`）。交互式文档：运行后访问 `/docs`（Swagger）或 `/redoc`。

---

## 6.1 统一约定 · Conventions

- 版本前缀：`/api/v1`（`API_V1_STR`）。
- 鉴权：设置 `ORBIT_AUTH_TOKEN` 后启用 AuthMiddleware；请求带 `Authorization: Bearer <token>`。
- 自动文档：`/docs`（Swagger UI）、`/redoc`（ReDoc）。
- 指标：`/metrics`（Prometheus）。

## 6.2 任务与目标 · Tasks & Goals

| 前缀 | 路由文件 | 代表端点 |
|---|---|---|
| `/health` | `health.py` | `GET /health`（含 Redis 探针） |
| `/api/v1/tasks` | `tasks.py` | `POST /tasks` 创建 · `GET /tasks/{id}` · `POST /tasks/{id}/cancel` |
| `/api/v1/goal` | `goal.py` | `POST /goal`（PRD/模糊需求/批量目录）· `POST /goal/{id}/cancel · pause · resume` |
| `/api/v1/loop` | `loop.py` | `POST /loop` 定时循环 · `GET /loop` · `DELETE /loop/{id}` |
| `/api/v1/compose` | `compose.py` | `POST /compose/run` 执行 spec 编排（限流 5 req/60s） |
| `/api/v1/dream` | `dream.py` | `POST /dream/run` 触发记忆合并 · `GET /dream/status` |
| `/api/v1/schedule` | `schedule.py` | `GET /peak-status` · `GET /queue` · `POST /queue/{id}/urgent` · `GET /savings-report` · `POST /reload-config` |

## 6.3 会话与项目 · Sessions & Projects

| 前缀 | 路由文件 | 代表端点 |
|---|---|---|
| `/api/v1/sessions` | `sessions.py` | `POST /sessions` · `GET /sessions` · `GET/PATCH /sessions/{id}` · `POST /sessions/{id}/fork` · `GET /sessions/{id}/forks` |
| `/api/v1/projects` | `projects.py` | `POST /projects` 注册 · `GET /projects` · `GET /projects/{name}` · `GET /projects/{name}/brief` · `POST /projects/{name}/brief/refresh` |
| `/api/v1/chat` | `chat.py` | `WebSocket /chat` 自然语言入口（ChatterAgent→意图路由→Chatter/Clarifier） |
| `/api/v1/agents` | `agent_llm.py` | `GET /agents/{name}/llm` 查询配置 · `POST /agents/{name}/llm/switch` 强制切换模型 |

## 6.4 验证与知识 · Validation & Knowledge

| 前缀 | 路由文件 | 代表端点 |
|---|---|---|
| `/api/v1/review` | `review.py` | `POST /review` 创建审查 · `GET /review/{id}` |
| `/api/v1/knowledge` | `knowledge.py` | `GET /knowledge?domain=...&concept=...` 领域知识查询（会计/金融/法律） |
| `/api/v1/compliance` | `compliance.py` | `GET /compliance/validate` · `/validate-all` · `/rules` |
| `/api/v1/compliance_check` | `compliance_routes.py` | Diff 合规标注 + 审查清单自动生成 |
| `/api/v1/causal` | `causal_routes.py` | `POST /learn` 学习因果图 · `POST /root-cause` 根因分析 · `GET /graph` · `POST /recommend` |

## 6.5 可观测与运维 · Observability & Ops

| 前缀 | 路由文件 | 代表端点 |
|---|---|---|
| `/api/v1/observability` | `observability.py` | `GET /health` · `/health/{component}` · `/metrics` · `/alerts` · `/alerts/history` · `/audit` · `POST/GET /lessons` · `/feedback` · `/grafana/dashboard` |
| `/api/v1/backup` | `backup.py` | `GET /snapshots` · `POST /snapshots` 创建快照 · `POST /restore` 恢复 |
| `/api/v1/versioning` | `versioning.py` | `GET /current` · `GET /versions` · `POST /install` |
| `/projects` | `ponytail_debt.py` | Ponytail 技术债务台账扫描 |

## 6.6 代码与文件 · Code & Files

| 前缀 | 路由文件 | 代表端点 |
|---|---|---|
| `/api/v1/files` | `files_routes.py` | `GET /tree` 文件树 · `GET /read?path=...` |
| `/api/v1/git` | `git_routes.py` | Git 操作（commit/branch/diff/log） |
| `/api/v1/search` | `search_routes.py` | `GET /search?q=...` 文件名 + 内容搜索（ripgrep） |
| `/api/v1/codegraph` | `codegraph_routes.py` | `GET /definition` Go-to-Def · `/references` · `/outline` · `/hover` · 图谱可视化 · `POST /build` |
| `/api/v1/tests` | `tests_routes.py` | 测试结果 + 覆盖率 API |
| `/api/v1/insights` | `insights_routes.py` | 风险评分、影响分析、模块健康 |
| `/api/v1/terminal` | `terminal_routes.py` | 集成终端命令执行 + 输出流（命令白名单） |
| `/api/v1/config` | `config_routes.py` | 配置管理（YAML 编辑 + Git 历史 + 分支 + 冲突解决） |

## 6.7 集成与窗口 · Integration & Window

| 前缀 | 路由文件 | 代表端点 |
|---|---|---|
| `/api/v1/wechat` | `wechat_routes.py` | 微信集成——绑定 + 配置 + iLink Bot API 双向对话 |
| `/app` | `app_routes.py` | 窗口控制（最小化/最大化/关闭） |

## 6.8 实时通道 · Real-time Channels

| 通道 | 路由 | 用途 |
|---|---|---|
| WebSocket | `/ws` | 驾驶舱实时监控（DAG/Token/告警推送） |
| WebSocket | `/ws/diagnostics/{task_id}` | 实时诊断推送（mypy 结果） |
| WebSocket | `/api/v1/chat` | 自然语言对话 |
| SSE | `stream/` 模块 | Agent 输出流式响应 |

---

[← 返回目录](README.md) · [下一章：再开发说明 →](07-development-guide.md)
</content>
