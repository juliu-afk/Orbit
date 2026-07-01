# Code-Insight-Financial — Codex Context (AGENTS.md)

> 自动生成于 2026-07-01 13:45 UTC
> 源文件: CLAUDE.md (sha256:96576ae4)
>          WORKFLOW.md (sha256:b55dba58)
>          accounting-rules.md (sha256:MISSING)

> [WARN] 本文件由 scripts/build_codex_context.py 自动生成。
>       修改源文件后请重新运行脚本，不要手动编辑此文件。

---

# Orbit — 核心规则

> 轻量级多 Agent 软件开发自循环系统。
> 自研调度框架，替代 CrewAI 等黑盒框架。六图谱（代码/数据库/配置/知识/元图谱/文档）+ 9 层防幻觉体系 + 毫秒级熔断。
> 当前阶段：**编码阶段**。24 个源码模块已落地，持续迭代中。

## 文档索引

**收到新需求/新任务时，必须在回复用户之前先读取 `@docs/WORKFLOW.md`**——所有改动走阶段 1-4 流程。

| 文档 | 何时读 |
|------|--------|
| `@docs/WORKFLOW.md` | **收到新需求时必读**——阶段 1-4 完整流程 |
| `@docs/开发计划_V14.1.md` | 总体设计索引——指向 `docs/开发计划/` 下 4 个子文档（不要全量加载） |
| `@docs/PRD+ADR_0+1阶段.md` | Step 0.1-1.2 实现时读 |
| `@docs/PRD+ADR_2阶段.md` | Step 2.1-2.2 实现时读 |
| `@docs/PRD+ADR_3阶段.md` | Step 3.1-3.3 实现时读 |
| `@docs/PRD+ADR_4阶段.md` | Step 4.1-4.2 实现时读 |
| `@docs/PRD+ADR_5阶段.md` | Step 5.1-5.7 实现时读 |
| `@docs/PRD+ADR_6阶段.md` | Step 5.8-6.3 实现时读 |
| `@docs/PRD+ADR_7阶段.md` | Step 7.1 实现时读 |
| `@docs/PRD+ADR_MVP阶段.md` | 部署总结查询时读 |
| `@docs/PRD+ADR_工程化流程简版.md` | 全 Step 交叉参考时读（147K） |

## 术语定义

**核心模块**（`src/orbit/` 下已实现的 24 个模块）：
- `scheduler/` — 调度器状态机、Agent 角色编排
- `graph/` — 六图谱统一存储与查询（CodeGraph SQLite）
- `hallucination/` — L1-L8 八层防幻觉（熵监控/双向合约/配置漂移检测等）
- `sandbox/` — Docker 代码片段隔离执行
- `checkpoint/` — 检查点管理（保存/回滚）
- `agents/` — Agent 工厂 + 角色定义（base, clarifier, context, factory）
- `gateway/` — LiteLLM 网关
- `knowledge/` — 知识库管理
- `communication/` — 消息总线 + 协议
- `compliance/` — 合规规则引擎
- `observability/` — OpenTelemetry + structlog
- `api/` — FastAPI 路由 + Pydantic 模型
- 以及 `backup/`, `context/`, `core/`, `events/`, `infrastructure/`, `projects/`, `resource_guard/`, `sessions/`, `sharding/`, `tools/`, `versioning/`, `ws/`

**核心模型**：`Task`、`AgentRole`、`Checkpoint`、`GraphSnapshot`、`AuditEntry`、`CostRecord`。

**核心概念**：
- **六图谱**：代码图谱（Tree-sitter）+ 数据库图谱（DDL/MVCC）+ 配置图谱（.env/Nginx/docker-compose）+ 知识图谱（外挂领域知识）+ 元图谱（跨图谱关系）+ 文档图谱，统一存 CodeGraph SQLite
- **9 层防幻觉**：L1 静态校验 / L2 动态追踪 / L3 熵监控 / L4 沙箱执行 / L5 合约验证 / L6 双向合约定向 / L7 形式化验证（Z3）/ L8 配置漂移检测 / L9 动态合规验证
- **熔断**：Token 计数器 + 延迟阈值，超限即熔断回滚到上一检查点

## 技术栈

| 层级 | 组件 |
|------|------|
| 主语言 | Python 3.14 |
| 包管理 | Poetry 1.8.2 |
| LLM 网关 | LiteLLM >=1.40 |
| API | FastAPI + Pydantic v2 + Uvicorn |
| ORM | SQLAlchemy 2.0.25 + Alembic |
| 沙箱 | Docker Engine >=24 |
| 前端 | Vue3 + Pinia + AG-UI |
| 桌面壳 | Tauri (Rust WebView) |
| 测试 | pytest + pytest-asyncio + Playwright |

## 项目结构

```
Orbit/
├── src/orbit/                     # 主源码（24 个模块）
│   ├── scheduler/                 # 调度器状态机
│   ├── graph/                     # 六图谱（code/database/config/knowledge/meta/document）
│   ├── hallucination/             # L1-L8 防幻觉
│   ├── sandbox/                   # Docker 隔离执行
│   ├── checkpoint/                # 检查点管理
│   ├── agents/                    # Agent 工厂
│   ├── gateway/                   # LiteLLM 网关
│   ├── knowledge/                 # 知识库
│   ├── api/                       # FastAPI 路由
│   ├── communication/             # 消息总线
│   ├── compliance/                # 合规引擎
│   ├── observability/             # 遥测
│   └── (backup/ context/ core/ events/ infrastructure/ projects/
│        resource_guard/ sessions/ sharding/ tools/ versioning/ ws/)
├── backend/                       # PyInstaller 打包配置 + static/
├── frontend/src/                  # Vue3 驾驶舱
│   ├── views/                     # 页面
│   ├── components/                # 通用组件（alerts/ audit/ charts/ chat/ dag/ ops/）
│   ├── composables/               # 组合式函数
│   ├── stores/                    # Pinia 状态
│   └── router/                    # Vue Router
├── src-tauri/                     # Tauri 桌面壳（Rust）
├── alembic/versions/              # 数据库迁移
├── configs/                       # k8s/otel/alertmanager/grafana
├── chart/orbit/                   # Helm Chart
├── scripts/                       # build_codex_context.py, build-desktop.sh
├── docs/                          # PRD+ADR + requirements/
├── .automations/pr-review/        # PR 审核 Token 节省工具
└── Deliverables/                  # Tauri 桌面壳产物（Orbit.exe）
```

## 实现约束

| # | 约束 | 理由 |
|---|------|------|
| 1 | **新模块 → 必须在 `orbit.spec` 的 `hiddenimports` 注册** | 否则 PyInstaller 漏打包 |
| 2 | **构建 exe 前 `rm -rf backend/build`** | 清除旧缓存 |
| 3 | **改后端后必须跑完整 `scripts/build-desktop.sh`** | Tauri 壳 ≠ 裸 PyInstaller 产物 |
| 4 | **LLM 调用必须经 LiteLLM 网关，禁止直连 provider** | 统一追踪 + 降级 |
| 5 | **沙箱执行代码 → Docker 隔离，禁止宿主机直接跑** | 安全基线 |
| 6 | **防幻觉层改动 → 审查 L1-L8 全链路，不能只改一层** | 单层改动影响上下游判定 |
| 7 | **调度器状态机改动 → 全路径回归（转换/检查点/回滚）** | 状态不一致 → 任务卡死 |
| 8 | **新依赖必须先问** | poetry add / pnpm add 前确认 |
| 9 | **API key / Token → 环境变量，禁止硬编码** | 安全基线 |

## 编码约定

### Python
- 类型标注：所有 public 函数写完整类型签名
- 异步：调度器/网关/沙箱一律 `async def`
- Pydantic v2 做 LLM 输出结构化与 API 契约
- ORM 用 SQLAlchemy 2.0 风格（`Mapped` / `mapped_column`）

### Vue3 / TypeScript
- `<script setup lang="ts">` 组合式 API
- strict 模式，禁止 `any`
- 状态进 Pinia store，不散落组件内

## 测试框架

| 级别 | 命令 | 时长 |
|------|------|------|
| 单元测试 | `pytest tests/unit/ -q --tb=short` | 秒级 |
| 集成测试 | `pytest tests/integration/ -q --tb=short` | ≤1min |
| 冒烟测试 | `pytest tests/e2e/ -q --tb=short -k "smoke"` | ≤2min |
| 回归测试 | `pytest tests/e2e/ -q --tb=short` | ≤10min |

覆盖率目标：调度器/防幻觉纯函数 100%，Service 模块 ≥95%，CI 门禁 ≥95%。

## 行为拦截清单

| 操作 | 规则 |
|------|------|
| 说"合并" | 逐条确认：用户验收？CI？审查？ |
| `git add -A` | ⛔ 禁止——精确指定文件 |
| 展示 diff 后 | 等用户说"commit"，不自动 commit |
| 新增 dep | 先问用户 |
| `git push --force` / `+branch` / `push --delete 后重建` | ⛔ 禁止——详见 `@docs/WORKFLOW.md` §6.2 |
| LLM 生成代码直接执行 | ⛔ 禁止——必须经沙箱 Docker 隔离 |
| 调度器状态机改动 | 审查全生命周期 + 检查点回滚路径 |
| 防幻觉层判定逻辑改动 | 审查 L1-L8 全链路影响 |
| LLM API key | ⛔ 禁止硬编码 |

## Token 节省规则

1. **按需加载文档**：WORKFLOW.md 收到新需求时读；其他文档仅相关时读
2. **Grep/Glob 优先**：避免整文件读取
3. **Subagent 用 cavecrew**：输出压缩 ~60%
4. **Memory 系统**：重复问题写入 memory，自动注入后续会话

## 插件环境

ECC + Compound 双插件部署。`ECC /security-scan` 阶段 4a 强制。
`/ce-code-review` 核心模块改动时启用。

## 通信模式

- 默认 caveman **full** 模式回复。丢冠词/填充词，保留技术准确
- 安全警告、不可逆操作确认、多步序列：自动降级回正常模式

## 例外

无例外。所有改动走完整四阶段流程。**收到需求时先读 `@docs/WORKFLOW.md`。**


---

# Orbit 开发工作流手册

> 完整工作流参考。核心规则见 `@CLAUDE.md`，本文档在进入任一阶段前按需加载。

---

## 1. 工作流概览

收到新需求时，按四阶段推进，**每阶段等待用户确认后再进入下一阶段**。

```
阶段1 需求澄清 → 阶段2 技术方案 → 阶段3 编码实现 → 阶段3b 代码审查 → 阶段4 验证交付
```

核心原则：**慢就是快**——宁可在阶段1-2花时间对齐需求，不要写完再改。

### 1.1 文档管理约定

- 同批次需求文档保存到 `docs/requirements/YYYY-MM-DD-需求简称/`
- 文件命名：`阶段1-PRD-xxx.md` / `阶段2-技术方案-xxx.md` / `阶段3-实现记录-xxx.md` / `阶段3b-代码审查-xxx.md` / `阶段4-测试报告-xxx.md`
- **阶段2 技术方案必填边界 case 清单**：逐类填「场景-预期行为」，不适用标 N/A+理由，禁止留空。阶段4 测试据此验收
- 文档一旦保存即视为基线，后续阶段必须引用和对照
- 实现阶段必须对照对应 Step 的 PRD+ADR（`docs/PRD+ADR_*.md`），偏离必须主动标记并说明理由

### 1.2 阶段切换与对齐规则

**进入新阶段前（AI 自主执行）**：
1. 重读前面所有阶段文档
2. 在新阶段产出开头显式引用前一阶段基线
3. 将前一阶段的验收标准作为本阶段输入约束——偏离必须主动标记
4. **阶段门禁（硬性规则）**：当前阶段产出完成后，AI 必须显式请求用户确认，等待"确认"或"进入阶段 N"后方可进入下一阶段

**用户质疑时必须启动「回溯链」**：
从 PRD → 技术方案 → 当前代码/输出，展示完整逻辑链，定位断点（需求变了？方案不对？代码问题？）

**问题定位原则**：
```
驾驶舱 UI 呈现问题 → 打开 dev 服务器/Vite 亲自操作 → 检查 AG-UI 通信链路 → 最后看源码
调度/Agent 行为异常 → 检查调度器状态机日志 → 检查检查点回滚路径 → 定位 Agent 角色逻辑
LLM 输出错误       → 检查 LiteLLM 网关日志 → 检查防幻觉层 L1-L8 判定 → 定位 Prompt/Context
图谱查询错误       → 检查 CodeGraph SQLite 数据 → 检查查询接口 → 定位解析
```

---

## 2. 阶段 1：需求澄清

**输出**：`阶段1-PRD-xxx.md`

1. 输出结构化 PRD：背景、用户故事（P0/P1/P2）、验收标准、待确认问题、Non-Goals
2. 补充领域特定内容：调度器影响（状态转换/检查点/回滚/并发）、防幻觉影响（L1-L8 判定逻辑）、图谱影响（查询接口/存储格式/跨图谱协作）、边缘情况（LLM 超时/熔断触发、沙箱执行失败、图谱查询空结果、并发 Agent 竞态、检查点回滚冲突）
3. 调度器/防幻觉/图谱变更强制对抗性验证
4. 保存 → 等待用户反馈 → 循环直到确认

**Bug 修复 → 先复现再动代码（强制）**：
按报告场景跑一遍确认问题存在（调度器用日志，UI 用 dev 服务器，LLM 用相同 prompt 复现）。记录复现步骤到阶段1 PRD。

---

## 3. 阶段 2：技术方案

**输出**：`阶段2-技术方案-xxx.md`

必填要素（缺一不通过）：
1. **PRD 对照表**：逐条列出验收标准 → 技术方案覆盖。偏离必须标红
2. **API 设计**：端点路径、请求/响应 Pydantic 模型、错误码
3. **数据模型**：SQLAlchemy 2.0 模型定义、Alembic 迁移方向、索引设计
4. **数据流**：完整链路（`API → 调度器 → Agent → 图谱查询 → 防幻觉层 → 沙箱 → 审计`）
5. **调度器状态变更**：新增/修改的状态、转换条件、检查点策略、回滚路径
6. **防幻觉层影响**：哪些层受影响、判定逻辑变化、误报/漏报风险评估
7. **图谱 Schema 变更**：CodeGraph SQLite 表结构变化、查询接口变化
8. **边界 case 清单**（硬性，缺失即退回）
9. **风险与缓解**：至少 3 条（性能/正确性/可维护性各一）
10. **依赖链**：新增/变更的内部模块依赖、外部依赖

---

## 4. 阶段 3：编码实现

**输出**：`阶段3-实现记录-xxx.md`

1. feature 分支开发，Conventional Commits格式，commit message 注明对应 Step
2. 按阶段2方案写代码，不做方案外改动
3. 每个文件改完展示 diff → 用户审查
4. 用户确认 diff 后 → 进入 3b 代码审查
5. 3b 审查通过 → commit → 编写实现记录 → 进入阶段 4

**实现记录内容**：方案引用、改动清单、偏差说明、回溯对照

---

## 5. 阶段 3b：代码审查（强制）

| 维度 | 检查项 | 严重程度 |
|------|--------|---------|
| **安全** | SQL注入 / XSS / 命令注入 / 硬编码密钥 | 致命 |
| **调度器** | 状态转换完整性 / 检查点策略 / 回滚路径 | 致命 |
| **防幻觉** | L1-L8 链路影响 / 误报漏报风险 | 致命 |
| **方案偏差** | 是否按阶段2方案实现 | 严重 |
| **回溯一致性** | 代码→方案→PRD 可追溯 | 严重 |
| **测试覆盖** | 核心模块正+异常用例 | 严重 |
| **代码质量** | 三行相似不抽象 / 边界条件 | 一般 |

**审查方式**：
- 核心模块强制 `/ce-code-review`（12 Agent 并行审查）
- 非核心模块可选 `/code-review`（轻量审查）
- 审查发现问题 → 修复 → 重新审查，循环最多 3 轮

门禁：致命问题必须修→重新审查；审查通过→commit→进入阶段 4。

---

## 6. 阶段 4：验证交付

### 6.1 测试执行

**决策树**：
```
纯前端（驾驶舱）→ frontend vitest + Playwright 冒烟
纯后端（非核心）→ pytest unit + integration
触及核心模块    → + 全量回归
触及防幻觉层    → + 每层独立验证用例
触及调度器      → + 状态转换/检查点/回滚全路径回归
触及三图谱      → + 跨图谱协作查询回归
```

**执行命令**：

| 级别 | 命令 | 时长 |
|------|------|------|
| 单元测试 | `pytest tests/unit/ -q` | 秒级 |
| 集成测试 | `pytest tests/integration/ -q` | ≤1 分钟 |
| 冒烟测试 | `pytest tests/e2e/ -q -k "smoke"` | ≤2 分钟 |
| 回归测试 | `pytest tests/e2e/ -q` | ≤10 分钟 |
| 变异测试 | `mutmut run` | 按需 |
| 混沌测试 | `tox -e chaos` | 按需 |

**新功能追加测试（强制）**：
- 新增 API 端点 → 至少 1 个集成测试
- 新增调度器状态 → 单元测试覆盖所有转换路径
- 新增防幻觉层规则 → 正向+异常用例（误报/漏报各一）
- Bug 修复 → 1 条 `test_regression_` 用例

### 6.2 创建 PR

PR 标题 Conventional Commits，CI 自动触发。

**⚠️ 绝对禁止以下操作——强制规则，无例外：**
- **禁止 `git push --force` / `git push --force-with-lease` / `git push +branch`**
  原因：可能覆盖他人 PR 分支、丢失他人代码、污染仓库历史。
  如需更新 PR 分支，仅允许普通 `git push`（fast-forward）。
- **禁止向已有开放 PR 的远程分支推送**
  原因：覆盖他人工作。建分支前必须 `gh pr list --head <branch>` 确认无冲突。
- **禁止 `git push --delete` 远程分支后重建同名分支**
  原因：GitHub 自动关闭原 PR，丢失所有 review 历史。

### 6.3 门禁检查（9 项，全绿才能合并）

1. 安全扫描通过 / 2. 所有测试 exit code = 0 / 3. 覆盖率 ≥80% 且未下降（调度器/防幻觉纯函数 100%）
4. 触及核心模块时回归已跑 / 5. 新功能有对应测试 / 6. Bug 修复有 regression 用例
7. 前端改动有 Playwright 回归测试 / 8. 测试报告已保存 / 9. PR CI 绿灯

门禁不通过：分析根因 → 自动修复 → 从 4a 重新执行 → 循环最多 3 轮。

### 6.4 用户验收 + 合并

用户对照阶段1 PRD 逐条验证 → 确认"可以合并" → GitHub PR merge → master

### 6.5 版本号 + CHANGELOG

语义化版本，`git tag -a vX.Y.Z -m "版本说明"` + 更新 CHANGELOG.md

### 6.6 数据库迁移

Alembic：`alembic revision --autogenerate -m "description"`，迁移脚本必须可重复执行（含 downgrade）

### 6.7 收尾（每次 merge 到 master 后）

1. 更新功能清单 / 2. 更新路线图 / 3. 更新 SESSION.md / 4. 新错误模式 → 追加到拦截清单

---

## 7. exe 构建桌面版（强制两段式）

> **Deliverables/Orbit.exe 是 Tauri 桌面壳，不是裸 PyInstaller 产物。**
> 裸 PyInstaller 产物是 39MB 后端-only，无 UI 窗口，用户双击看不到任何东西。

```bash
bash scripts/build-desktop.sh
```

**关键关系**：
- `Deliverables/Orbit.exe` ← Tauri 构建输出，不是 PyInstaller 产物
- 仅改前端 → 跳 PyInstaller，跑前端构建 + Tauri 编译
- 新增 backend 模块 → 必须加到 `orbit.spec` `hiddenimports` 列表
- `console=False` 是正确的——Tauri 提供窗口


---

> [WARN] docs/accounting-rules.md 不存在

---

*Generated at 2026-07-01 13:45 UTC | Source hashes: CLAUDE.md=96576ae4, WORKFLOW.md=b55dba58, accounting-rules.md=MISSING*