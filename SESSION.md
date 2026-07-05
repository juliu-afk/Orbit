# Orbit 开发会话记录

## 2026-07-06 — Phase B 遗留收尾 (PR #212 · MERGED)

**背景**: 审计 19 项遗留，5 项不过时，全部收尾。

### 交付

| 层 | 内容 | 文件 |
|----|------|------|
| 前端 | TraceViewer——Trace 链路瀑布图 + span 详情 + OTEL 导出 | `TraceDrawer.vue` |
| 前端 | ConfigView——YAML 编辑 + Git 历史 + 分支管理 + 冲突解决 | `ConfigDrawer.vue` + 3 子组件 |
| 后端 | FeedbackEngine——轨迹分析→失败率/漂移率/效率→调优建议 | `feedback.py` |
| 后端 | TrajectoryCollector 生命周期接线 + /feedback 端点 | `main.py`, `observability.py` |
| 运维 | 代码签名 SOP + build-desktop.sh 签名占位 | `SOP-代码签名.md` |
| 测试 | `test_stream.py` 补 valid_values + 8 条 feedback 测试 | `test_stream.py`, `test_feedback.py` |

### 审查

- R1: P2-1（FeedbackEngine DB 路径 bug——永远读不到数据）+ P2-2（docstring 误导）→ 全修

### 关键决策

- FeedbackEngine 改为依赖注入——接受 TrajectoryCollector 实例，不自建连接
- 代码签名跳过证书购买（个人项目无营业执照），仅写 SOP 文档
- 14/19 遗留项判定为过时——MCP 已实现、沙箱已覆盖、上下文管线已替代等

---

## 2026-07-06 — Sprint 1 P0：开源项目借鉴 (PR #211 · MERGED)

**基于**: 4 个开源项目源码解构（pm-skills / Compound Engineering / turboVec / ECC）。
**报告**: `docs/open-source-deep-dive-2026-07-05.html`（生成于 `docs/research/`）

### 交付

| P0 | 内容 | 文件 |
|----|------|------|
| P0-1 | PrinciplesContextBuilder——蒸馏引擎→Agent system prompt | `context/builders/principles_builder.py` |
| P0-2 | StrategyContextBuilder——STRATEGY.md 三级降级锚点 | `context/builders/strategy_builder.py` |
| P0-3 | 6×SKILL.md 方法论注入（逆向 pm-skills prompt 框架） | `compose/skills/*.md` |
| P0-4 | turboVec+BGE 语义搜索（4-bit 8x压缩+TF-IDF降级） | `knowledge/embedding.py`, `knowledge/vector.py` |
| 修复 | 10 测试文件 `def @pytest.mark.skip` 语法错误（22处） | `tests/unit/test_*.py` |

### 依赖
- turbovec 0.8.0 (MIT) + sentence-transformers 5.6.0 (Apache 2.0)

### 审查
- WorkBuddy: P2×2——中文路径改名+测试缺口（后项下个 Sprint）
- 合并: squash merge → master

### 踩坑
- **Session auto-commit**: 非插件 hook——可能是 Claude session-end 自动保存导致变更直接提交到 master（commit message "test"）。后续切 feature 分支后再工作
- **Poetry resolver 失败**: `tz3-solver` typo 导致 `poetry add` 失败，改用 `pip install` 直装
- **Merge conflict**: squash merge 残留 `search()` 方法体缺失，修复后推送

---

## 2026-07-05 — CUA 模式迁移 Phase A (PR #199 · MERGED)

**基于**：三大 CUA 项目（OpenAI CUA Sample / trycua / OpenCUA）源码解构分析。
**报告**：`docs/research/CUA项目源码解构——Orbit可借鉴模式分析.html`
**完整文档**：`docs/requirements/2026-07-05-CUA模式迁移/`

### 交付

| 层 | 内容 | 文件 |
|----|------|------|
| 调度器 | 循环上限 50 轮 + 步骤超时 120s/180s + 防抖 120ms + CODING 串行化 | `task_runner.py` |
| L2 | 反思式函数调用追踪——predicted_calls vs actual 偏差分 | `l2_dynamic.py` |
| L4 | 反思式行为对比——mypy got/expected 类型提取 + `_compare_behavior` | `l4_type.py` |
| L5 | 反思式契约对比——自述契约 vs Z3 验证 + `_describe_contract` | `l5_z3.py` |
| Schemas | L2ReflectionResult / L4BehaviorResult / L5ContractResult | `schemas.py` |
| 测试 | 60 条 CUA 专项 + 99 条已有零回归 = 159 全绿 | `test_cua_*.py` |

### 审查历程

- **R1**: P0-1(超时值) + P1-1~5(死代码/空壳/零测试/resume) + P2-1/2 → 全修
- **R2**: NEW-1(重复方法) + NEW-2(L4假阳性) + P1-1(实调测试) → 全修
- **合并**: 3 轮 rebase 解决 4 文件冲突 → force-with-lease → merge

### Phase B 待做

MCP 双向适配 + 审计数据飞轮 + 沙箱 BYOI（P1-P2，后续迭代）

### 关键决策

- 反思式 CoT 只附加信号（predicted vs actual），不改变现有 pass/fail 逻辑
- Agent 步骤超时 120s/180s（包裹整个 `agent.execute()`，非单个 tool call）
- L4 `_compare_behavior` 用 mypy got/expected 类型提取替代关键词匹配
- `GraphNode.serialize_tools` 死代码直接移除（CODING 状态检查已足够）

---

## 2026-07-03/04 — 覆盖率冲刺 73%→82% + create_app 懒加载 + exe 构建修复

### PR #190: feat: 覆盖率冲刺 73%→82% (SQUASH MERGED)

**46 文件，+5,354 行，25+ 测试文件，~500 tests。**

- **9 源码 Bug 修复**：跨午夜窗口判定、isfuture→iscoroutine、.pem 匹配、git 白名单、python -c 无空格等
- **新增测试文件**：`test_template_selector.py`(0%→71%)、`test_route_mocks.py`(35 mock 路由)、`test_verifier.py`、`test_dag_runner.py`、`test_shell.py` 等
- **扩展测试**：`test_merge_engine.py`、`test_offpeak_scheduler.py`、`test_tool_registry.py`
- **踩坑**：squash merge 只合了 6 个冲突文件——25 个测试文件丢失

### PR #193: feat: lazy create_app + SQLite 集成测试 + PR#190 测试补遗 (SQUASH MERGED)

**10 文件，+1,181/-1,016。**

- **create_app 懒加载**：`create_app(routes=[...])` 只导入指定路由——测试不再全量加载 27 个路由模块
- **SQLite 集成测试**：`test_session_integration.py` 26 tests（CRUD/messages/fork），参照 `test_review.py` 模式
- **测试补遗**：25 个测试文件从 feat/tests-from-190 合入（PR #190 squash 遗漏）
- **审查**：P0/P1/P2 各一轮全修（merge conflict markers、test_verifier.py 语法破坏、sqlite3 import 等）

### exe 构建修复 (master 直接 push)

- **PyInstaller 27 路由漏打包**：懒加载 `importlib.import_module()` 不能被 PyInstaller 静态分析→`launcher.py` 显式 import 全部 27 路由+`orbit.spec` hiddenimports 补充
- **peak_windows.yaml 24:00→23:59**：`datetime(hour=24)` ValueError
- **最终产物**：`Deliverables/Orbit.exe` 52MB（Tauri v2 GUI + WebView2 embedBootstrapper + PyInstaller 49MB 后端），10 端点全 200 验证通过

## 2026-07-04 — Inkeep 竞品借鉴 5 项 (PR #195)

### PR #195: feat(gateway): Inkeep 借鉴 5 项——模型路由+分级存储+按需加载+Trace+Git配置 (MERGED)

**30 文件，+4,766/-850。47 单元测试，0 回归。2 P1 + 4 P2 审查修复。**

基于 `docs/research/research-inkeep-analysis.md` 竞品分析，5 项设计模式自建增强：

- **US-1 TaskModelRouter**（P0）：reasoning→Pro, structured_output→Flash, summarization→nano——预计节省 40-60% token 成本
- **US-2 ArtifactTierManager**（P0）：preview/full/oversized 三级 + 动态阈值调整 + UTF-8 安全截断
- **US-3 load_knowledge tool**（P1）：Agent 按需拉取知识，AST 自注册，KnowledgeEngine 单例复用
- **US-4 TraceSpan**（P2 后端）：异步批量 flush（500ms/50条）+ 三层保留（7d/30d/OTEL导出）
- **US-5 ConfigStore**（P2 后端）：YAML+Git，branch/merge/rollback/diff/clash resolve——全部复用 git

**审查修复（0b4f824）**：
- P1-1: _flush_batch bare except → structlog.warning(exc_info=True)
- P1-2: start_worker 竞态 → asyncio.Lock
- P2-1~4: to_dict() 注释 + max(0,) 保护 + CREATE_NO_WINDOW + 单例
- 边缘: Alembic migration (003_trace_spans.sql) + orbit.spec hiddenimports ×2

**待后续 PR**：US-4/5 前端（TraceViewer.vue + ConfigView.vue + YamlEditor.vue + VersionHistory.vue）——后端 API 已就绪。

### 关键决策

- US-1 模型映射：Phase 1 Task-Type 硬编码 + YAML 可配置（4 方案中选 A），Phase 2 Agent 显式声明 Tier
- US-5 配置后端：真 Git（方案 A）而非 SQLite 线性历史——配置存 YAML 文件 + git 仓库，branch/merge/conflict 免费
- US-4/5 前端拆分：P2 优先级，后端先行交付（API 可通过 curl/Postman 测试），前端下个 PR 补齐

### 旧分支清理

删除 12 个 feat/* 分支（sla-wiring、tests-from-190、integration-tests-lazy-app 等）——内容已全部合入 master

### 覆盖率结果

- 起始：73.17% / 3,433 缺失
- 峰值：82.3% / 2,295 缺失
- 当前：~73%（分母膨胀后回落）
- 9 源码 bug 修复 / 25+ 测试文件 / 500+ tests / 0 测试失败

### 踩坑

- hook/linter 反复 revert Edit/Write 修改 → commit 前必须 git add + commit 冻结
- agent 生成测试 ~30% 失败率，且拉高分母（import 新模块）→ 后续用手写
- squash merge 丢新文件 → 需单独 cherry-pick
- 分支被自动切换（feat/sla-wiring→feat/chatter-agent→feat/serena-hardening）→ 频繁 git checkout -f
- gh CLI TLS/网络间歇故障
- PyInstaller 不能静态分析 `importlib.import_module()` → launcher.py 显式 import 兜底

### Serena 强化 + 偷师清单 A/B/C (master 直接 push)

- **Prompt 加固**：Serena 从建议升级为硬约束——5 条强制规则，禁止 grep/read_file 替代
- **A: hover 修复**：`code_graph.py` +`get_symbol_meta()`，/hover 不再 500
- **C: Go to Def 行号**：`find_definitions_with_positions()` 返回 `{file, line, end_line}`
- **B: CodeGraph → MCP**：`mcp_server.py` +3 代码导航工具（`find_symbol`/`find_referencing_symbols`/`get_symbols_overview`）

### 偷师清单状态

| 项 | 状态 | 说明 |
|----|------|------|
| A. hover bug | ✅ | get_symbol_meta |
| B. CodeGraph → MCP | ✅ | 3 代码工具 |
| C. Go to Def 行号 | ✅ | find_definitions_with_positions |
| D-H | 不搞 | MCP 桥借 Serena 轮子 |

## 2026-07-03 — MCP 客户端桥 + Serena 语义代码工具集成

### PR #188: feat: MCP 客户端桥——Orbit 消费外部 MCP 工具 (MERGED)

**背景**：调研 Serena (oraios/serena)，开源 LSP 驱动的语义代码导航工具，通过 MCP 协议暴露。
决定将 MCP 客户端能力集成到 Orbit，让 Agent 能调用外部 MCP 工具。

**交付**：
- `src/orbit/tools/mcp_client.py`: MCPClientConnection——JSON-RPC 2.0 over stdio，后台线程解决 Windows 管道阻塞
- `src/orbit/tools/registry.py`: connect_mcp_server() + schema 转换 + handler 工厂
- `src/orbit/api/main.py`: 启动时加载 configs/mcp_clients.yaml
- `configs/mcp_clients.yaml`: Serena 配置
- `tests/unit/test_mcp_client.py`: 13 单元测试

**审查修复**：
- R1: 3 致命 + 7 风险全部修复（stderr 死锁/readline 超时/disconnect 竞态等）
- R2: 5 P2 细节优化

### PR #191: feat: Serena 集成闭环——Agent 能实际使用 MCP 工具 (MERGED)

**问题**：PR #188 只建了基础设施。Agent 不知道 Serena 存在——ROLE_TOOLS 白名单没配，prompt 没教。

**交付**：
- `tools/registry.py`: MCP_ROLES 自动授予 architect/developer/reviewer/qa
- `prompt/builder.py`: _build_mcp_guide() 教会 Agent 优先用 Serena 做代码导航
- `api/main.py`: shutil.which() 检测安装状态+提示
- `mcp_clients.yaml`: enabled=true

**R3 修复**：f.txt 删除/import shutil 提顶/builder.py 前缀动态化

### Serena 验证
- `pip install serena-agent` → 22 工具可被发现
- 首次启动需下载 LSP 后端 (>90s)，后续秒级

### 文档
- `docs/research/serena-vs-orbit-comparison.md` — 调研对比分析
- `docs/requirements/2026-07-03-MCP-Client-Bridge/` — 阶段 1-4 完整文档

## 2026-07-03 — Clarifier .env 路径修复

### PR #185: fix: Clarifier LLM 调用失败——.env 路径 + PyInstaller 漏打包 (MERGED)

**根因**: Tauri 启动时 ORBIT_HOME=Deliverables/，load_dotenv() 从 CWD 找 .env 找不到
→ API key 为 sk-dummy → LLM 401。PyInstaller 三处漏打包进一步阻断。

**修复**:
- config.py: `_find_dotenv()` 向上搜索目录树
- clarifier.py: 降级消息暴露 error_type
- orbit.spec: +litellm 子模块(自定义hook) + certifi cacert.pem + tiktoken_ext
- hooks/hook-litellm.py: 手动 walk 补 115 个命名空间包子包

**踩坑**: linter 多次 revert 修改文件，PyInstaller 4 次增量构建逐层排障

## 2026-07-01-02 — 全链路测试库 + 覆盖率冲刺

### 测试库 Phase 1-5 (全部 MERGED)
- PR #140: 7 mocks + 10 factories + TaskChain
- PR #141: 4 builders + 8 assertions + 7 scenarios (33 tests)
- PR #145: R1+R2 审查修复
- PR #151: files/loop/lsp/review 76 tests
- PR #153: 测试库自身 113 tests + Chinese generator

### 覆盖率 Sprint 1-3 (全部 MERGED)
- PR #156: 门禁 80→95%%, ws/router 29→97%%, scheduler 22→72%%
- PR #157: 17 新模块
- PR #160: 9 goal子模块 + compression/models

### 生产修复
permission strict_mode, exec_command sandbox, SEC-8 regex, imports cleanup, ReviewView, logger 39 files

### 当前
覆盖率: 68→75%% (目标95%%, 缺口~20%%)
memory: orbit-coverage-sprint.md

## 2026-06-25-26

### 完成项
- PR #50 fix: knowledge db init chicken-egg — 自动建表+测试隔离
- PR #52 fix: chat WS retry + static path + resource_guard breaker
- PR #54 feat: 仪表盘UI三修复 — 去外层滚动+统一边框+代码diff弹出
- PR #55 fix: body+.dashboard overflow:hidden
- PR #56 fix: 聊天框输入区裁剪 — flex布局替代硬编码calc
- PR #57 fix: flex消滚动+代码diff API时序修正
- PR #58 feat: Agent回复带角色头像+名称
- 4次exe重建 + Playwright UI验证

### 待处理
- `test_task_failure_propagates` / `test_generate_stream` 预存失败
- exe 代码签名

### 踩坑
- linter多次revert文件→commit前必确认文件状态
- 禁未审查直接合并（PR #53教训）
- overflow:hidden在body上导致内容裁剪→只在workspace层级
- 硬编码calc(100vh-40px)有像素偏差→改flex布局
- Agent角色名大小写不一致→统一toLowerCase()

## 2026-06-24

### 完成项
- **Tauri 桌面窗口迁移**（PR #40 → squash merge `7449fdb`）
  - PyInstaller + 浏览器 → Tauri v2 原生窗口，单 exe 42MB
  - `include_bytes!` 嵌入 orbit-backend.exe，运行时解压 %TEMP%
  - WebView2 引导器嵌入，缺失时自动安装
  - GUI 子系统（无控制台），窗口关闭自动杀后端
  - launcher.py 删 webbrowser + 加 sys.stdout/stderr None 保护
  - Cargo mirror：清华 403 → 中科大（ustc）

### 改动文件
- 新增 `src-tauri/` (10 文件)：Rust 工程 + 图标
- 修改 `src/orbit/launcher.py`、`backend/orbit.spec`、`.gitignore`、`frontend/package.json`

### 交付物
- `D:\Orbit\Deliverables\Orbit.exe` (42MB) — 单文件，可直接分发

### 待处理
- exe 代码签名（消除 SmartScreen 警告）
- 无边框标题栏 / 系统托盘 / 多窗口（后续 Tauri 迭代）

## 2026-06-23

### 完成项
- PR #6 Step 4.1：防幻觉 L1-L4（v0.6.0）
- PR #7 Step 4.2：防幻觉 L5-L8 + CI 全修复（v0.7.0）
- PR #8 Step 5.1：调度器 DAG 拓扑排序 + 分层并发（v0.8.0）
- PR #9：revert Step 5.2 误直接提交 master
- PR #10：Step 5.2 Agent 角色（误未审查直接合并，已回退）
- PR #11：revert PR #10

### 今日交付
- 8 层防幻觉体系全部交付（L1-L8）
- DAG 调度器（拓扑排序 + 分层并发 + 检查点恢复）
- CI 全修复（mypy/ruff/bandit/integration）
- 全量 174/174 通过

### 版本
- v0.9.0：5 Agent 角色定义（PR #12，tag 待 push）

### 待处理
- Step 7.1 灰度发布
- Step 6.2 E2E 集成测试

## 2026-06-23（下午）

### 完成项
- **Step 6.1 驾驶舱**（PR #13）
  - 后端：EventBus (asyncio.Queue) + ConnectionManager + WebSocket 端点
  - 前端：Vue3+Vite+Pinia + vis-network DAG + ECharts Token + 告警列表
  - 实时通信：原生 WebSocket（零依赖，评估后放弃 Socket.IO）
  - 测试：后端 192 (+10) + 前端 13 = 205 全通过
  - 文档：PRD + 技术方案 + 审查 + 实现记录 4 份
- 文档同步：功能清单 + 路线图（Step 5.1/5.2 补录，测试数 150→174）

### 版本
- v0.10.0：Step 6.1 驾驶舱（PR #13，待合并）

### 关键决策
- 原生 WebSocket > Socket.IO（零依赖，完全可控）
- EventBus put_nowait（非阻塞，不卡调度器状态机）
- 前端 vis-network/ECharts 独立 chunk（首屏加载优化）
- P1 功能延后（DagNodeModal/任务列表）

### 踩坑记录
- vis-network 9.x 类型定义不完整 → as any 绕过（运行时正确）
- disconnect 日志在清空后计数 → 移到清空前
- git stash/pop 切换分支时 docs 文件的 CRLF 警告（无害）

### 踩坑记录
- 禁止未审查直接合并 PR（PR #10→#11 revert 教训）
- git add -A 禁止，精确指定文件
- 禁 force push
- revert 时注意保留后续修复（ci.yml mypy continue-on-error）
- PR #6 → v0.6.0（Step 4.1）
- PR #7 → v0.7.0（Step 4.2 + CI fix）
- 全量 150/150 通过
- CI 修复：pipx→pip、--no-root、black/isort/ruff/mypy 全量修复
- 审查修复 P1+P2 全修

### PR / Commit
- PR #6 → 合并 `933a26b`：feat(hallucination) Step 4.1 L1-L4
- 15 commit（feat ×1 + fix ×6 + style ×4 + docs ×4）

### 关键决策
- L3 流式集成留 Step 5.1（当前 LLMClient 非流式）
- L2 增加 code_engine 参数实现真实图谱验证（审查 P2 修复）
- L4 固定 `--disable-error-code no-untyped-def`（PRD Q2 决议）
- CI: pip install poetry 替代 pipx（消除隔离层冲突）

### 待处理
- Step 4.2 L5-L8 防幻觉（Z3 形式化/合约双向/沙箱执行/配置漂移修复）
- Step 5.1 调度器扩展为 DAG（拓扑排序 + 并发执行）
- CI 残余 mypy 2 错误（code_graph arg-type / orchestrator 5 项）
- CI integration 空套件退出码 5
- CI dependency scan 失败

### CI 状态
- unit-test (3.11/3.12): ✅ pass
- security scan: ✅ pass
- black/isort/ruff: ✅ pass
- mypy: ⚠️ 2 残余错误（已有，非本次引入）
- integration: ⚠️ 无测试（已有）
- dependency scan: ⚠️ 待查

## 2026-06-25/26

### 完成
- PR #59: 模型体系重构——DS V4 Pro/Flash + GLM-5.2 + GLM-4.7 Flash 降级
- 架构变更: llm_client 单例→agent_llms dict 按角色注入
- Scheduler 不再直接调 LLM，只编排 Agent
- 删 Qwen/Ollama 所有引用
- GLM 走 Coding Plan /api/coding/paas/v4 订阅端点
- .env: ZAI_API_KEY + DEEPSEEK_API_KEY 就位
- 18 文件，10 轮 CI 修复，全绿合并

### 模型体系
| 角色 | 模型 | 计费 |
|------|------|------|
| architect/developer | DeepSeek V4 Pro | 按量 |
| config_manager/clarifier | DeepSeek V4 Flash | 按量 |
| reviewer/qa | GLM-5.2 | Coding Plan 订阅 |
| 降级 | GLM-4.7 Flash | 免费→挂起人工 |

### 关键决策
- GLM 必须走 Coding Plan 端点，不能用标准端点（扣余额）
- 本地部署不考虑——单卡 5090 也跑不动 GLM-5.2 (750B)
- API 直接调最划算

## 2026-06-26（续）

### 完成
- PR #51 关闭——内容已通过 PR #50 合并，test isolation 修复 cherry-pick 到 master (d8da444)

## 2026-07-03 — 文档-代码对照审查 + 源码 TODO 清零

### 背景
docs/ 与 src/ 对照清查，发现 26 项未完成：12 源码 TODO、3 P2 修复、3 Charter SLA、5 覆盖率 AC、Ponytail A5/A7/C4。

### 完成 PR
- #175-#182: 8 个 PR 清零 12 处源码 TODO
  - 前端：TerminalChat 历史导航、AgentLLMStatus 详情弹窗、middleware 模板默认
  - 调度：dag_runner AgentFactory 路由、meta_orchestrator budget_tracker
  - 算法：ensemble LLM 3D 评分 + 真正融合逻辑
  - 存储：memory HyDE async、compressor session cold storage
  - 安全：沙箱外部路径 allowlist、code_graph 方法级命名空间
  - 流程：Ponytail A5 ComposeOrchestrator brief 检查
  - 可观测：Charter SLA 指标定义 + L4-L7/dag_runner/task_runner 埋点接线
  - 测试：circuit_breaker xfail 移除 + HyDE 异步测试
- #186: UI 修复——窗口拖动 + 项目选择器
- #189: ChatterAgent——通用对话首触点 + 意图路由（chat→DONE / programming→Clarifier）
- #184: SLA 指标接线
- #183: 文档同步（charter / Ponytail 步骤 / 代码审查 P2）

### 审查结论
26 项全部闭环。源码 TODO 清零。Charter 三项 SLA 全部仪表化。UI 三问题修复。

### 待办
- #190 覆盖率冲刺（另一会话）
- exe 重构建（另一会话）

## 2026-07-04 — ChatterAgent 聊天路由 + PyInstaller 打包防复发体系

### PR #196: fix: ChatterAgent 首触路由 + PyInstaller 打包防复发体系 (MERGE)

**9 文件，+539/-312。**

**问题**：打开 exe 聊天框发消息，ClarifierAgent 直接回 "暂时无法分析（FileNotFoundError）"——两个根因：
1. chat.py 硬编码 ClarifierAgent，忽略已写好的 ChatterAgent（用户首触点）
2. PyInstaller 打包漏 litellm 1727 子模块 + tiktoken 命名空间包 + DeepSeek api_key 未显式传

**修复**：
- `chat.py`：ChatterAgent 首触 → 意图路由(intent="chat"→直接回复 / intent="programming"→ClarifierAgent)
- `client.py`：DeepSeek 模型显式传 `settings.DEEPSEEK_API_KEY`，不再让 litellm 自己找
- `orbit.spec`：合并重复 Analysis 块 → `_discover_orbit_modules()` 自动发现 209 模块 + `THIRD_PARTY_DATAS` 集中管理
- `hook-litellm.py`：PyInstaller hook 文件系统扫描 1727 模块 + 38 JSON 数据文件
- `tiktoken_ext` + `tiktoken_ext.openai_public`：命名空间包加入 `_INFRA_IMPORTS`

### PyInstaller 打包防复发体系（7 层）

| 层 | 脚本 | 检查内容 |
|---|------|---------|
| 0 | check_spec | 结构——重复 Analysis/EXE |
| 1 | check_spec | 数据文件——cacert/litellm json |
| 2 | check_spec | 自动发现——209 orbit 模块 |
| 3 | check_spec | 路由对齐——29 api.routes |
| 4 | check_spec | Hook 验证——litellm 1727模块+38json |
| 4.5 | check_spec | 命名空间包——tiktoken_ext |
| 5 | check_spec | 关键依赖——6 库可导入 |
| 7 | smoke_test | 运行时——探针+health+chat WS |

- `build-desktop.sh` 步骤 0.5 强制运行 check_spec（失败阻断）+ 步骤 7 smoke_test
- 防住了 8/8 个本轮问题（含 3 个之前漏掉的第三方库问题，已补层 4/4.5/7）

### 踩坑
- `orbit.spec` 有两个 Analysis 块→PyInstaller 用最后一个→第一个的 datas 修复完全无效
- `SPECPATH` 是目录路径不是文件路径→check_spec 设错了导致 ROOT 偏移到 backend/，自动发现返回空
- litellm `collect_submodules()` 只收集 479/1727 模块（缺 tokenizers）→必须文件系统扫描
- tiktoken 编码数据在 `tiktoken_ext` 命名空间包→PyInstaller 不自动发现→需加入 hiddenimports
- chat.py `set_clarifier_llm` 注入只在 chat 路由加载时生效→加 `set_chatter_llm` 同步注入
