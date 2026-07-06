# Orbit — 核心规则

> 轻量级多 Agent 软件开发自循环系统。
> 自研调度框架，替代 CrewAI 等黑盒框架。五图谱体系（3 引擎：代码/数据库/配置 + 知识图谱 + 元图谱）+ 9 层防幻觉体系 + 毫秒级熔断。
> 当前阶段：**覆盖率冲刺**。行覆盖 75% / 分支 60% / 综合 72%。目标 80%。分支覆盖是瓶颈（~2100 未覆盖分支）。

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

**核心模块**（`src/orbit/` 下已实现的 45 个模块）：
- `scheduler/` — 调度器状态机 + DAG + 离线调度 + 编辑稳定性检测
- `graph/` — 图谱引擎（代码/数据库/配置 + 元图谱 12 种跨图谱关系）
- `hallucination/` — L1-L8 八层防幻觉纵深防御
- `compliance/` — L9 动态合规验证（规则引擎 + 知识时效性检查）
- `sandbox/` — Docker 代码片段隔离执行
- `checkpoint/` — 检查点管理（保存/回滚）
- `agents/` — Agent 工厂 + 10 角色（base/chatter/clarifier/context/dream/factory/mcts/preact/react_agent/reflection）
- `gateway/` — LiteLLM 网关 + 三层模型路由（T1/T2/T3）+ 降级
- `knowledge/` — 知识图谱（SQLite + BGE 向量搜索 + TF-IDF 降级 + MCP）
- `modes/` — 交互协议层（architect/clarify/review + 三维度评分 + 模式可见性）
- `memory/` — 分层记忆（情节/画像/决策日志/SCOPE 双流）
- `evolution/` — 自我进化（GEPA Prompt 进化 + SCOPE + 自蒸馏 + ANCHOR 对齐）
- `context/` — 上下文预构建体系（5 prebuilder + 7 builder + 5 scanner）
- `compression/` — Token 预算追踪 + 上下文压缩
- `communication/` — Agent 消息总线（4 模式 + 幂等 + 熔断传播）
- `observability/` — OpenTelemetry + 审计 + 反馈引擎 + 轨迹收集
- `metacognition/` — 元认知监控层（次级 Monitor Agent）
- `api/` — FastAPI 路由（31 个端点文件）+ Pydantic 模型
- `compose/` — 多 Agent 编排 + 6×SKILL.md 方法论注入
- 以及 `actors/`, `backup/`, `brief/`, `cli/`, `dream/`, `events/`, `files/`, `goal/`, `goal_judge/`, `integration/`, `loop/`, `lsp/`, `projects/`, `prompt/`, `resource_guard/`, `review/`, `router/`, `security/`, `sessions/`, `sharding/`, `stream/`, `tools/`, `versioning/`, `worktree/`, `ws/`, `core/`, `infrastructure/`

**核心模型**：`Task`、`AgentRole`、`Checkpoint`、`GraphSnapshot`、`AuditEntry`、`CostRecord`。

**核心概念**：
- **五图谱体系**：3 引擎（代码图谱 Tree-sitter / 数据库图谱 DDL+MVCC / 配置图谱 .env+Nginx+docker-compose）+ 知识图谱（外挂领域知识 + BGE 语义搜索）+ 元图谱（12 种跨图谱关系：READS_FROM/WRITES_TO/DEPENDS_ON/REFERENCES 等），统一存 CodeGraph SQLite。注：文档图谱仅存在于设计文档，未实现代码
- **9 层防幻觉**：L1 静态校验 / L2 动态追踪 / L3 熵监控 / L4 类型检查 / L5 Z3 形式化 / L6 合约验证 / L7 沙箱执行 / L8 配置漂移检测 / L9 动态合规验证
- **熔断**：Token 计数器 + 延迟阈值，超限即熔断回滚到上一检查点

## 技术栈

| 层级 | 组件 |
|------|------|
| 主语言 | Python 3.11+ |
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
├── src/orbit/                     # 主源码（45 个模块）
│   ├── scheduler/                 # 调度器状态机 + DAG + 离线调度
│   ├── graph/                     # 图谱引擎（代码/数据库/配置 + 元图谱）
│   ├── hallucination/             # L1-L8 防幻觉纵深防御
│   ├── compliance/                # L9 动态合规验证
│   ├── sandbox/                   # Docker 隔离执行
│   ├── checkpoint/                # 检查点管理
│   ├── agents/                    # Agent 工厂 + 10 角色
│   ├── gateway/                   # LiteLLM 网关 + 三层模型路由
│   ├── knowledge/                 # 知识图谱 + BGE 向量语义搜索
│   ├── modes/                     # 交互协议层（architect/clarify/review）
│   ├── memory/                    # 分层记忆（情节/画像/决策日志）
│   ├── evolution/                 # 自我进化（GEPA + SCOPE + 蒸馏）
│   ├── context/                   # 上下文预构建体系
│   ├── compression/               # Token 预算 + 上下文压缩
│   ├── communication/             # 消息总线 + 协议
│   ├── observability/             # OTEL + 审计 + 反馈引擎
│   ├── metacognition/             # 元认知监控层
│   ├── api/                       # FastAPI 路由（31 端点文件）
│   ├── compose/                   # 多 Agent 编排 + 技能
│   └── (actors/ backup/ brief/ cli/ dream/ events/ files/ goal/
│        goal_judge/ integration/ loop/ lsp/ projects/ prompt/
│        resource_guard/ review/ router/ security/ sessions/
│        sharding/ stream/ tools/ versioning/ worktree/ ws/
│        core/ infrastructure/)
├── backend/                       # PyInstaller 打包配置 + static/
├── frontend/src/                  # Vue3 驾驶舱
│   ├── views/                     # Boot / Dashboard / TerminalShell
│   ├── components/                # 20+ 组件目录（chat/ audit/ charts/ dag/ ops/…）
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

覆盖率目标：调度器/防幻觉纯函数 100%，Service 模块 ≥80%（当前 69%，冲刺中），CI 门禁 ≥80%。

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
| PyInstaller 构建 | 必须经 `check_spec.py` + `smoke_test.py` 双重门禁 |
| orbit.spec 修改 | 禁止新增 Analysis/EXE 块——只改现有块；新增第三方依赖必须同步更新 `THIRD_PARTY_DATAS` 或 `hook-*.py` |
| 新加 import 第三方库 | 若有命名空间包（无 `__init__.py`）→ 加入 `_INFRA_IMPORTS`；若有数据文件（.json/.pem）→ 加入 hook 或 `THIRD_PARTY_DATAS` |

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
