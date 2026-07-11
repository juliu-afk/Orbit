# 10 · 再开发说明 || Development Guide

[← 返回目录 || Back to index](README.md) · [← 上一章：API 参考 || Prev: API Reference](09-api-reference.md)

> 面向开发者：怎么改、怎么加功能、怎么测、怎么构建交付。完整流程见 [`docs/WORKFLOW.md`](../WORKFLOW.md) 与 [`CONTRIBUTING.md`](../../CONTRIBUTING.md)。 || For developers: how to modify, add features, test, and build for delivery. See [`docs/WORKFLOW.md`](../WORKFLOW.md) and [`CONTRIBUTING.md`](../../CONTRIBUTING.md) for the complete workflow.

---

## 10.1 四阶段开发流程 || The Four-Stage Workflow

**核心规则**：每阶段结束**必须等用户显式确认**后方可进入下一阶段。"慢就是快"——阶段 1–2 对齐需求优先，写完再改不被允许。 || **Core rule**: Each stage **must wait for explicit user confirmation** before proceeding to the next. "Slow is fast" — aligning requirements in stages 1–2 takes priority; writing first and revising later is not allowed.

```
阶段1 需求澄清 → 阶段2 技术方案 → 阶段3 编码实现 → 阶段3b 代码审查 → 阶段4 验证交付
```

### 阶段 1：需求澄清 → `阶段1-PRD-xxx.md` || Stage 1: Requirement Clarification → `阶段1-PRD-xxx.md`
结构化 PRD（背景 / 用户故事 P0–P2 / 验收标准 / 待确认问题 / Non-Goals）。 || Structured PRD (background / user stories P0–P2 / acceptance criteria / open questions / Non-Goals).
领域特化必须评估：调度器影响（状态转换/检查点/回滚/并发）、防幻觉影响（L1–L8 判定逻辑）、图谱影响（查询接口/存储格式/跨图谱协作）、边缘情况（LLM 超时、沙箱失败、空结果、竞态、回滚冲突）。 || Domain-specific assessment required: scheduler impact (state transitions/checkpoints/rollback/concurrency), anti-hallucination impact (L1–L8 judgment logic), graph impact (query interfaces/storage formats/cross-graph collaboration), edge cases (LLM timeout, sandbox failure, empty results, race conditions, rollback conflicts).
**Bug 门禁**：必须先复现再动代码，复现步骤记入 PRD。 || **Bug gate**: Must reproduce before touching code; reproduction steps recorded in the PRD.

### 阶段 2：技术方案 → `阶段2-技术方案-xxx.md` || Stage 2: Technical Design → `阶段2-技术方案-xxx.md`
**10 项必填要素，缺一不通过**： || **10 required elements, all mandatory**:
1. PRD 对照表（逐条验收标准→方案覆盖，偏离标红） || PRD cross-reference (each acceptance criterion → design coverage, deviations marked in red)
2. API 设计（端点、Pydantic 模型、错误码） || API design (endpoints, Pydantic models, error codes)
3. 数据模型（SQLAlchemy 2.0、Alembic 迁移方向、索引） || Data model (SQLAlchemy 2.0, Alembic migration direction, indexes)
4. 数据流（API→调度器→Agent→图谱→防幻觉→沙箱→审计） || Data flow (API → scheduler → Agent → graph → anti-hallucination → sandbox → audit)
5. 调度器状态变更（新增/修改状态、转换条件、检查点策略、回滚路径） || Scheduler state changes (new/modified states, transition conditions, checkpoint strategy, rollback paths)
6. 防幻觉层影响（哪些层受影响、判定变化、误报漏报风险） || Anti-hallucination layer impact (which layers affected, judgment changes, false-positive/false-negative risks)
7. 图谱 Schema 变更（CodeGraph SQLite 表结构、查询接口变化） || Graph schema changes (CodeGraph SQLite table structure, query interface changes)
8. 边界 case 清单（硬性，缺失即退回） || Edge-case checklist (mandatory, missing items result in rejection)
9. 风险与缓解（至少 3 条：性能/正确性/可维护性各一） || Risks and mitigations (at least 3: one each for performance/correctness/maintainability)
10. 依赖链（新增/变更内外部依赖） || Dependency chain (new/changed internal and external dependencies)

### 阶段 3：编码实现 → `阶段3-实现记录-xxx.md` || Stage 3: Implementation → `阶段3-实现记录-xxx.md`
feature 分支开发，Conventional Commits，commit 注明对应 Step。按方案实现，不做方案外改动。每个文件改完展示 diff → 用户审查 → 进入 3b。 || Develop on feature branches, Conventional Commits, each commit indicates the corresponding Step. Implement per the design, no out-of-scope changes. Show diff after each file change → user review → proceed to 3b.

### 阶段 3b：代码审查（强制） || Stage 3b: Code Review (Mandatory)
审查维度（致命项必须修，最多 3 轮）： || Review dimensions (critical items must be fixed, max 3 rounds):

| 维度 || Dimension | 检查项 || Check Item | 严重度 || Severity |
|---|---|---|---|---|
| 安全 || Security | SQL 注入/XSS/命令注入/硬编码密钥 || SQL injection/XSS/command injection/hardcoded keys | 致命 || Critical |
| 调度器 || Scheduler | 状态转换完整性/检查点策略/回滚路径 || State transition completeness/checkpoint strategy/rollback paths | 致命 || Critical |
| 防幻觉 || Anti-hallucination | L1–L8 链路影响/误报漏报风险 || L1–L8 chain impact/false-positive/false-negative risks | 致命 || Critical |
| 方案偏差 || Design deviation | 是否按阶段 2 方案实现 || Whether implemented per stage-2 design | 严重 || Major |
| 回溯一致性 || Traceability consistency | 代码→方案→PRD 可追溯 || Code → design → PRD traceable | 严重 || Major |
| 测试覆盖 || Test coverage | 核心模块正 + 异常用例 || Core module positive + error cases | 严重 || Major |
| 代码质量 || Code quality | 三行相似不抽象/边界条件 || Three similar lines → refactor/boundary conditions | 一般 || Minor |

审查方式：核心模块强制 `/ce-code-review`（12 Agent 并行）；非核心可选 `/code-review`（轻量）。 || Review method: core modules mandatory `/ce-code-review` (12 parallel Agents); non-core optional `/code-review` (lightweight).

### 阶段 4：验证交付 → `阶段4-测试报告-xxx.md` || Stage 4: Validation & Delivery → `阶段4-测试报告-xxx.md`
测试决策树 + 9 项门禁（见 §10.3）。全绿方可 PR 合入。 || Test decision tree + 9 gates (see §10.3). All green before PR merge.

## 10.2 模块地图速查 || Module Map

完整职责表见 [03 整体架构 §3.3](03-architecture.md#3-3-模块地图-module-map)。核心模块改动触发强制回归： || See [Architecture §3.3](03-architecture.md#3-3-模块地图-module-map) for the full responsibility table. Core module changes trigger mandatory regression:

| 核心模块 || Core Module | 改动触发 || Change Trigger |
|---|---|---|
| `scheduler/` | 状态转换/检查点/回滚全路径回归 || Full-path regression for state transitions/checkpoints/rollback |
| `hallucination/` + `compliance/` | 每层独立验证（误报/漏报各一） || Each layer independently verified (one false-positive, one false-negative) |
| `graph/` | 跨图谱协作查询回归 || Cross-graph collaboration query regression |
| `gateway/` | LLM 路由 + 降级回归 || LLM routing + fallback regression |

## 10.3 测试体系 || Testing

| 层级 || Level | 目录 || Directory | 文件数 || File Count | 命令 || Command | 时长 || Duration |
|---|---|---|---|---|---|---|---|---|---|
| 单元 || Unit | `tests/unit/` | ~270 | `pytest tests/unit/ -q` | 秒级 || Seconds |
| 集成 || Integration | `tests/integration/` | 15 | `pytest tests/integration/ -q` | ≤1min |
| 冒烟 || Smoke | `tests/e2e/` | 11 | `pytest tests/e2e/ -q -k "smoke"` | ≤2min |
| 回归 || Regression | `tests/e2e/` | 11 | `pytest tests/e2e/ -q` | ≤10min |
| 变异 || Mutation | — | — | `mutmut run` | 按需 || On demand |
| 混沌 || Chaos | `tests/chaos/` | 2 | `tox -e chaos` | 按需 || On demand |
| 其他 || Other | `acceptance/` `effectiveness/` `perf/` `ab/` `stress/` | — | — | 按需 || On demand |

**测试工具库** `tests/lib/`：`assertions/`（网关/防幻觉/沙箱/任务断言）、`builders/`（chat/dag/goal/task 链）、`factories/`（agent/audit/checkpoint/…）、`mocks/`（checkpoint/circuit_breaker/code_graph/…）、`scenarios/`（6 场景：正常/熔断/检查点恢复/并发/边界/防幻觉/沙箱隔离）。 || **Test library** `tests/lib/`: `assertions/` (gateway/anti-hallucination/sandbox/task assertions), `builders/` (chat/dag/goal/task chain), `factories/` (agent/audit/checkpoint/…), `mocks/` (checkpoint/circuit_breaker/code_graph/…), `scenarios/` (6 scenarios: normal/breaker/checkpoint-recovery/concurrency/boundary/anti-hallucination/sandbox-isolation).

**覆盖率门禁**：≥80%（CI `--cov-fail-under`），调度器/防幻觉纯函数 100%。10 个自定义 pytest marker（`scenario_*` 系列）。 || **Coverage gate**: ≥80% (CI `--cov-fail-under`), scheduler/anti-hallucination pure functions 100%. 10 custom pytest markers (`scenario_*` series).

**新功能测试强制规则**： || **Mandatory testing rules for new features**:
- 新增 API 端点 → 至少 1 集成测试 || New API endpoint → at least 1 integration test
- 新增调度器状态 → 覆盖所有转换路径 || New scheduler state → cover all transition paths
- 新增防幻觉层规则 → 正向 + 异常（误报/漏报各一） || New anti-hallucination layer rule → positive + error (one false-positive, one false-negative)
- Bug 修复 → 1 条 `test_regression_` 用例（先复现→失败→修→通过） || Bug fix → 1 `test_regression_` case (reproduce → fail → fix → pass)

## 10.4 exe 构建链路 || Desktop Build

**两段式：PyInstaller（后端）+ Tauri（桌面壳）**。命令：`bash scripts/build-desktop.sh` 或 `make exe`。 || **Two-stage: PyInstaller (backend) + Tauri (desktop shell)**. Command: `bash scripts/build-desktop.sh` or `make exe`.

```
[1] 前端构建          frontend/ → pnpm build → frontend/dist/
[2] 复制静态文件       frontend/dist/* → backend/static/
[3] PyInstaller 后端   orbit.launcher:main → Deliverables/Orbit-backend.exe（~39MB）
[4] 替换 Tauri 内嵌     Orbit-backend.exe → src-tauri/orbit-backend.exe
[5] Tauri cargo build   src-tauri/ → cargo build --release → Deliverables/Orbit.exe
[6] API 冒烟           smoke_test.py（startup-probe + health + chat WS）
[7] 代码签名（可选）    signtool（需 CODE_SIGN_CERT + CODE_SIGN_PASSWORD）
```

- 仅前端改动：跳步骤 3，只 1+2+5。 || Frontend-only changes: skip step 3, only 1+2+5.
- 仅后端改动：必须完整 1→2→3→4→5。 || Backend-only changes: full 1→2→3→4→5 required.
- 构建前强制 `python scripts/check_spec.py`（5 项检查）。 || Pre-build: `python scripts/check_spec.py` mandatory (5 checks).

### orbit.spec 约束（`backend/orbit.spec`） || orbit.spec Constraints (`backend/orbit.spec`)

- 入口 `src/orbit/launcher.py`（隐式 import 所有 `api.routes.*`）。 || Entry: `src/orbit/launcher.py` (implicitly imports all `api.routes.*`).
- `_discover_orbit_modules()` 递归扫描 `src/orbit/` 所有 `.py`，跳过 `__pycache__`/`.venv`/`test_`/`_` 前缀。 || `_discover_orbit_modules()` recursively scans all `.py` files under `src/orbit/`, skipping `__pycache__`/`.venv`/`test_`/`_` prefixes.
- 手动 `_HIDDEN_IMPORTS`：基础设施 + 命名空间包（uvicorn/aiosqlite/tiktoken_ext/metacognition/evolution/agents.reflection…）。 || Manual `_HIDDEN_IMPORTS`: infrastructure + namespace packages (uvicorn/aiosqlite/tiktoken_ext/metacognition/evolution/agents.reflection…).
- 数据文件：`certifi/cacert.pem` + `litellm/model_prices*.json`。 || Data files: `certifi/cacert.pem` + `litellm/model_prices*.json`.
- hook：`backend/hooks/hook-litellm.py`（递归收集 litellm 全部 .py + .json）。 || Hook: `backend/hooks/hook-litellm.py` (recursively collects all litellm .py + .json).
- `console=False`（Tauri 提供窗口）。 || `console=False` (Tauri provides the window).

### 常见失败模式 || Common Failure Modes

1. **新模块未加 hiddenimports** → PyInstaller 漏打包（spec 自动扫描跳过懒 import）。 || **New module missing from hiddenimports** → PyInstaller misses it (spec auto-scan skips lazy imports).
2. **`__pycache__` 残留** → 运行时行为与源码不一致，构建前清理。 || **`__pycache__` residue** → runtime behavior diverges from source, clean before build.
3. **Vite 前端缓存** → 产物不含最新改动，清 `frontend/dist/` + `.vite/`。 || **Vite frontend cache** → output lacks latest changes, clear `frontend/dist/` + `.vite/`.
4. **litellm 子模块遗漏** → 1727+ 模块靠 hook 收集。 || **Missing litellm submodules** → 1727+ modules collected via hook.
5. **Tauri 内嵌 exe 未替换**（跳步骤 4）→ cargo build 用旧后端。 || **Tauri embedded exe not replaced** (skipped step 4) → cargo build uses old backend.

### 其他脚本 `scripts/` || Other Scripts `scripts/`

`build_codex_context.py`（合并 CLAUDE/WORKFLOW→AGENTS.md）· `check_spec.py` · `smoke_test.py` · `check_effectiveness_ci.py` · `check_perf_thresholds.py` · `generate_benchmark.py` · `run_orbitbench.py` · `dr/recover.py`。 || `build_codex_context.py` (merges CLAUDE/WORKFLOW→AGENTS.md) · `check_spec.py` · `smoke_test.py` · `check_effectiveness_ci.py` · `check_perf_thresholds.py` · `generate_benchmark.py` · `run_orbitbench.py` · `dr/recover.py`.

## 10.5 数据库迁移 || Migrations

- **双轨制**：SQL 原生脚本（`.sql`，数字编号 `NNN_desc.sql`）+ Alembic Python（`YYYYMMDD_desc.py`）。 || **Dual-track**: raw SQL scripts (`.sql`, numbered `NNN_desc.sql`) + Alembic Python (`YYYYMMDD_desc.py`).
- 自动生成：`alembic revision --autogenerate -m "..."`。 || Auto-generate: `alembic revision --autogenerate -m "..."`.
- SQL 脚本必须 `IF NOT EXISTS`（可重复执行）；Alembic 脚本必须含可回滚 `downgrade()`。 || SQL scripts must use `IF NOT EXISTS` (idempotent); Alembic scripts must include a reversible `downgrade()`.
- `down_revision` 链条串联，禁止直接改数据库文件不写迁移脚本。 || `down_revision` chain linked; direct database file modifications without migration scripts are prohibited.

现有迁移：`002_goal_loop.sql`（Goal+Loop 表）· `003_trace_spans.sql`（Trace 表）· `20260707_add_severity_to_review_decisions.py` · `20260710_add_parent_id_to_code_nodes.py`。 || Existing migrations: `002_goal_loop.sql` (Goal+Loop tables) · `003_trace_spans.sql` (Trace table) · `20260707_add_severity_to_review_decisions.py` · `20260710_add_parent_id_to_code_nodes.py`.

## 10.6 贡献约定 || Conventions

### Git
| 规则 || Rule | 内容 || Content |
|---|---|---|
| 分支命名 || Branch naming | `feat/<简称>` / `fix/<简称>` || `feat/<name>` / `fix/<name>` |
| master 保护 || master protection | 禁止直接 push master，走 PR || Direct push to master prohibited, use PR |
| Commit || Commit | Conventional Commits，subject ≤50 字符，作用域如 `feat(scheduler):` || Conventional Commits, subject ≤50 chars, scope e.g. `feat(scheduler):` |
| 绝对禁止 || Strictly prohibited | `git push --force` / `+branch` / `--delete` / amend 已发布 commit / 向有开放 PR 的分支推送 / `git add -A` || `git push --force` / `+branch` / `--delete` / amend published commits / push to branches with open PRs / `git add -A` |
| 版本号 || Versioning | SemVer，`git tag -a vX.Y.Z` + 更新 CHANGELOG.md || SemVer, `git tag -a vX.Y.Z` + update CHANGELOG.md |

### Python
类型标注（public 函数完整签名）· 中文注释写 WHY（面向非编程审计）· 模块/类 PascalCase，函数/变量 snake_case · SQLAlchemy 2.0（`Mapped`/`mapped_column`）· 调度器/网关/沙箱一律 `async def` · 行长 100 · Python 3.11–3.13 · Poetry · **新依赖必须先讨论**。 || Type annotations (full public function signatures) · Chinese comments explain WHY (for non-programmer auditors) · Modules/classes PascalCase, functions/variables snake_case · SQLAlchemy 2.0 (`Mapped`/`mapped_column`) · Scheduler/gateway/sandbox all `async def` · Line length 100 · Python 3.11–3.13 · Poetry · **New dependencies must be discussed first**.

### 工具链 || Toolchain
lint：ruff（E,F,I,UP,B,SIM，忽略 E501,B904）+ black（100）+ isort（profile=black）· typecheck：mypy `--strict` · 安全：bandit + pip-audit · pre-commit。 || lint: ruff (E,F,I,UP,B,SIM, ignores E501,B904) + black (100) + isort (profile=black) · typecheck: mypy `--strict` · security: bandit + pip-audit · pre-commit.

### Vue 前端 || Vue Frontend
`<script setup lang="ts">` 组合式 API · strict，禁 `any` · 状态进 Pinia · 构建 `CI=true pnpm build` · 测试 vitest + Playwright。 || `<script setup lang="ts">` Composition API · strict, no `any` · State in Pinia · Build: `CI=true pnpm build` · Test: vitest + Playwright.

### PR 检查清单 || PR Checklist
- [ ] 走完四阶段，文档齐全 || All four stages completed, documentation complete
- [ ] 测试全绿，覆盖率未下降 || All tests green, coverage not decreased
- [ ] 新增依赖已讨论 || New dependencies discussed
- [ ] 无硬编码密钥/Token || No hardcoded keys/tokens
- [ ] commit 符合 Conventional Commits || Commits follow Conventional Commits
- [ ] CHANGELOG 已更新（用户可见变更时） || CHANGELOG updated (for user-visible changes)

---

[← 返回目录 || Back to index](README.md) · [下一章：附录 → || Next: Appendix →](11-appendix.md)
