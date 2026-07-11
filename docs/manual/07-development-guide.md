# 07 · 再开发说明 · Development Guide

[← 返回目录 Back to index](README.md) · [← 上一章 API 参考](06-api-reference.md)

> 面向开发者：怎么改、怎么加功能、怎么测、怎么构建交付。完整流程见 [`docs/WORKFLOW.md`](../WORKFLOW.md) 与 [`CONTRIBUTING.md`](../../CONTRIBUTING.md)。

---

## 7.1 四阶段开发流程 · The Four-Stage Workflow

**核心规则**：每阶段结束**必须等用户显式确认**后方可进入下一阶段。"慢就是快"——阶段 1–2 对齐需求优先，写完再改不被允许。

```
阶段1 需求澄清 → 阶段2 技术方案 → 阶段3 编码实现 → 阶段3b 代码审查 → 阶段4 验证交付
```

### 阶段 1：需求澄清 → `阶段1-PRD-xxx.md`
结构化 PRD（背景 / 用户故事 P0–P2 / 验收标准 / 待确认问题 / Non-Goals）。
领域特化必须评估：调度器影响（状态转换/检查点/回滚/并发）、防幻觉影响（L1–L8 判定逻辑）、图谱影响（查询接口/存储格式/跨图谱协作）、边缘情况（LLM 超时、沙箱失败、空结果、竞态、回滚冲突）。
**Bug 门禁**：必须先复现再动代码，复现步骤记入 PRD。

### 阶段 2：技术方案 → `阶段2-技术方案-xxx.md`
**10 项必填要素，缺一不通过**：
1. PRD 对照表（逐条验收标准→方案覆盖，偏离标红）
2. API 设计（端点、Pydantic 模型、错误码）
3. 数据模型（SQLAlchemy 2.0、Alembic 迁移方向、索引）
4. 数据流（API→调度器→Agent→图谱→防幻觉→沙箱→审计）
5. 调度器状态变更（新增/修改状态、转换条件、检查点策略、回滚路径）
6. 防幻觉层影响（哪些层受影响、判定变化、误报漏报风险）
7. 图谱 Schema 变更（CodeGraph SQLite 表结构、查询接口变化）
8. 边界 case 清单（硬性，缺失即退回）
9. 风险与缓解（至少 3 条：性能/正确性/可维护性各一）
10. 依赖链（新增/变更内外部依赖）

### 阶段 3：编码实现 → `阶段3-实现记录-xxx.md`
feature 分支开发，Conventional Commits，commit 注明对应 Step。按方案实现，不做方案外改动。每个文件改完展示 diff → 用户审查 → 进入 3b。

### 阶段 3b：代码审查（强制）
审查维度（致命项必须修，最多 3 轮）：

| 维度 | 检查项 | 严重度 |
|---|---|---|
| 安全 | SQL 注入/XSS/命令注入/硬编码密钥 | 致命 |
| 调度器 | 状态转换完整性/检查点策略/回滚路径 | 致命 |
| 防幻觉 | L1–L8 链路影响/误报漏报风险 | 致命 |
| 方案偏差 | 是否按阶段 2 方案实现 | 严重 |
| 回溯一致性 | 代码→方案→PRD 可追溯 | 严重 |
| 测试覆盖 | 核心模块正 + 异常用例 | 严重 |
| 代码质量 | 三行相似不抽象/边界条件 | 一般 |

审查方式：核心模块强制 `/ce-code-review`（12 Agent 并行）；非核心可选 `/code-review`（轻量）。

### 阶段 4：验证交付 → `阶段4-测试报告-xxx.md`
测试决策树 + 9 项门禁（见 §7.3）。全绿方可 PR 合入。

## 7.2 模块地图速查 · Module Map

完整职责表见 [02 整体架构 §2.3](02-architecture.md#23-模块地图--module-map)。核心模块改动触发强制回归：

| 核心模块 | 改动触发 |
|---|---|
| `scheduler/` | 状态转换/检查点/回滚全路径回归 |
| `hallucination/` + `compliance/` | 每层独立验证（误报/漏报各一） |
| `graph/` | 跨图谱协作查询回归 |
| `gateway/` | LLM 路由 + 降级回归 |

## 7.3 测试体系 · Testing

| 层级 | 目录 | 文件数 | 命令 | 时长 |
|---|---|---|---|---|
| 单元 | `tests/unit/` | ~255 | `pytest tests/unit/ -q` | 秒级 |
| 集成 | `tests/integration/` | 12 | `pytest tests/integration/ -q` | ≤1min |
| 冒烟 | `tests/e2e/` | 11 | `pytest tests/e2e/ -q -k "smoke"` | ≤2min |
| 回归 | `tests/e2e/` | 11 | `pytest tests/e2e/ -q` | ≤10min |
| 变异 | — | — | `mutmut run` | 按需 |
| 混沌 | `tests/chaos/` | 2 | `tox -e chaos` | 按需 |
| 其他 | `acceptance/ effectiveness/ perf/ ab/ stress/` | — | — | 按需 |

**测试工具库** `tests/lib/`：`assertions/`（网关/防幻觉/沙箱/任务断言）、`builders/`（chat/dag/goal/task 链）、`factories/`（agent/audit/checkpoint/…）、`mocks/`（checkpoint/circuit_breaker/code_graph/…）、`scenarios/`（6 场景：正常/熔断/检查点恢复/并发/边界/防幻觉/沙箱隔离）。

**覆盖率门禁**：≥80%（CI `--cov-fail-under`），调度器/防幻觉纯函数 100%。10 个自定义 pytest marker（`scenario_*` 系列）。

**新功能测试强制规则**：
- 新增 API 端点 → 至少 1 集成测试
- 新增调度器状态 → 覆盖所有转换路径
- 新增防幻觉层规则 → 正向 + 异常（误报/漏报各一）
- Bug 修复 → 1 条 `test_regression_` 用例（先复现→失败→修→通过）

## 7.4 exe 构建链路 · Desktop Build

**两段式：PyInstaller（后端）+ Tauri（桌面壳）**。命令：`bash scripts/build-desktop.sh` 或 `make exe`。

```
[1] 前端构建          frontend/ → pnpm build → frontend/dist/
[2] 复制静态文件       frontend/dist/* → backend/static/
[3] PyInstaller 后端   orbit.launcher:main → Deliverables/Orbit-backend.exe（~39MB）
[4] 替换 Tauri 内嵌     Orbit-backend.exe → src-tauri/orbit-backend.exe
[5] Tauri cargo build   src-tauri/ → cargo build --release → Deliverables/Orbit.exe
[6] API 冒烟           smoke_test.py（startup-probe + health + chat WS）
[7] 代码签名（可选）    signtool（需 CODE_SIGN_CERT + CODE_SIGN_PASSWORD）
```

- 仅前端改动：跳步骤 3，只 1+2+5。
- 仅后端改动：必须完整 1→2→3→4→5。
- 构建前强制 `python scripts/check_spec.py`（5 项检查）。

### orbit.spec 约束（[`backend/orbit.spec`](../../backend/orbit.spec)）

- 入口 `src/orbit/launcher.py`（隐式 import 所有 `api.routes.*`）。
- `_discover_orbit_modules()` 递归扫描 `src/orbit/` 所有 `.py`，跳过 `__pycache__`/`.venv`/`test_`/`_` 前缀。
- 手动 `_HIDDEN_IMPORTS`：基础设施 + 命名空间包（uvicorn/aiosqlite/tiktoken_ext/metacognition/evolution/agents.reflection…）。
- 数据文件：`certifi/cacert.pem` + `litellm/model_prices*.json`。
- hook：`backend/hooks/hook-litellm.py`（递归收集 litellm 全部 .py + .json）。
- `console=False`（Tauri 提供窗口）。

### 常见失败模式

1. **新模块未加 hiddenimports** → PyInstaller 漏打包（spec 自动扫描跳过懒 import）。
2. **`__pycache__` 残留** → 运行时行为与源码不一致，构建前清理。
3. **Vite 前端缓存** → 产物不含最新改动，清 `frontend/dist/` + `.vite/`。
4. **litellm 子模块遗漏** → 1727+ 模块靠 hook 收集。
5. **Tauri 内嵌 exe 未替换**（跳步骤 4）→ cargo build 用旧后端。

### 其他脚本 `scripts/`

`build_codex_context.py`（合并 CLAUDE/WORKFLOW→AGENTS.md）· `check_spec.py` · `smoke_test.py` · `check_effectiveness_ci.py` · `check_perf_thresholds.py` · `generate_benchmark.py` · `run_orbitbench.py` · `dr/recover.py`。

## 7.5 数据库迁移 · Migrations

- **双轨制**：SQL 原生脚本（`.sql`，数字编号 `NNN_desc.sql`）+ Alembic Python（`YYYYMMDD_desc.py`）。
- 自动生成：`alembic revision --autogenerate -m "..."`。
- SQL 脚本必须 `IF NOT EXISTS`（可重复执行）；Alembic 脚本必须含可回滚 `downgrade()`。
- `down_revision` 链条串联，禁止直接改数据库文件不写迁移脚本。

现有迁移：`002_goal_loop.sql`（Goal+Loop 表）· `003_trace_spans.sql`（Trace 表）· `20260707_add_severity_to_review_decisions.py` · `20260710_add_parent_id_to_code_nodes.py`。

## 7.6 贡献约定 · Conventions

### Git
| 规则 | 内容 |
|---|---|
| 分支命名 | `feat/<简称>` / `fix/<简称>` |
| master 保护 | 禁止直接 push master，走 PR |
| Commit | Conventional Commits，subject ≤50 字符，作用域如 `feat(scheduler):` |
| 绝对禁止 | `git push --force` / `+branch` / `--delete` / amend 已发布 commit / 向有开放 PR 的分支推送 / `git add -A` |
| 版本号 | SemVer，`git tag -a vX.Y.Z` + 更新 CHANGELOG.md |

### Python
类型标注（public 函数完整签名）· 中文注释写 WHY（面向非编程审计）· 模块/类 PascalCase，函数/变量 snake_case · SQLAlchemy 2.0（`Mapped`/`mapped_column`）· 调度器/网关/沙箱一律 `async def` · 行长 100 · Python 3.11–3.13 · Poetry · **新依赖必须先讨论**。

### 工具链
lint：ruff（E,F,I,UP,B,SIM，忽略 E501,B904）+ black（100）+ isort（profile=black）· typecheck：mypy `--strict` · 安全：bandit + pip-audit · pre-commit。

### Vue 前端
`<script setup lang="ts">` 组合式 API · strict，禁 `any` · 状态进 Pinia · 构建 `CI=true pnpm build` · 测试 vitest + Playwright。

### PR 检查清单
- [ ] 走完四阶段，文档齐全
- [ ] 测试全绿，覆盖率未下降
- [ ] 新增依赖已讨论
- [ ] 无硬编码密钥/Token
- [ ] commit 符合 Conventional Commits
- [ ] CHANGELOG 已更新（用户可见变更时）

---

[← 返回目录](README.md) · [下一章：附录 →](08-appendix.md)
</content>
