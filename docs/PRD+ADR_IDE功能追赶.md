# Step 9: IDE 功能追赶——审查界面 + 智能管控

> **关联计划**: `docs/开发计划/06-IDE功能追赶计划.md`
> **需求文档目录**: `docs/requirements/2026-06-29-IDE功能追赶/`

---

## 9.0 总纲 PRD

| PRD · IDE 功能追赶 |  |
| --- | --- |
| **背景** | Orbit v0.17.0 已具备 Agent 编排、知识图谱、8 层防幻觉、合规验证等后端能力。但专业程序员审查 Agent 产出时，只能用 Git diff 命令行或切到 VS Code 看代码。Orbit 驾驶舱只有监控面板（DAG 拓扑/Token 折线/告警列表），缺少代码级审查界面。程序员不能盲批 Agent 的 diff——这是 Orbit 从"AI 工具"升级为"AI 开发平台"的瓶颈。 |
| **用户故事** | 作为专业程序员，我希望在 Orbit 界面内看到 Agent 改了什么代码（语法高亮 diff），逐段批准或打回，看到 mypy 类型错误标注，能跳转到函数定义评估影响范围，最后确认后由我亲自 commit——全程不切到 VS Code。 |
| **需求描述** | 补齐 53 项 IDE 功能，分 3 个 Phase 交付：<br>① **Phase 1 审查基础**（18 项，🔴 阻塞）：Diff 查看器+语法高亮+hunk 级审批+文件树+只读编辑器+问题面板+Git 面板+GPG 签名+导航+测试面板+覆盖率着色+失败测试关联。<br>② **Phase 2 审查增强+编辑干预**（19 项，🟡 重要）：Git Blame+审查注释系统+集成终端+实时诊断+快速修复+轻量编辑器+推理链展示+多 Agent 观点对比。<br>③ **Phase 3 智能审查**（18 项，🟢 加分）：风险评分+影响分析+合规标注+协作审查+模块仪表盘+知识图谱可视化+数据库 Schema 审查。 |
| **范围 (Do/Don't)** | **Do：**代码审查闭环（看 diff→审代码→导航→诊断→批注→终端验证→提交）；审查专用编辑器；诊断管道；智能审查辅助。<br>**Don't：**不替代 IDE（无多光标/分屏/Zen 模式/调试器）；不做实时协同编辑（Live Share）；不做插件市场；不做 Jupyter Notebook；不做 Copilot 式行内 AI 补全。 |
| **数据契约** | 见各 Phase ADR |
| **异常定义** | 若 Monaco Editor 加载失败（CDN 不可达），降级为纯文本 diff 模式。若 L4 mypy 诊断管道超时 5s，显示"诊断加载中"不阻塞审查流程。若 Git 操作冲突（多 Agent 并发），锁定审查会话为只读直到冲突解决。 |
| **成功标准→验收** | **SC1:** 程序员审查一个 5 文件 PR 的完整闭环（看 diff→批准 3 个文件→打回 2 个→提交）在 Orbit 内完成，零切出。**AC1:** E2E 测试覆盖完整审查闭环。<br>**SC2:** Diff 加载+渲染时间 <2s（1000 行 diff）。**AC2:** 性能基准测试。<br>**SC3:** L4 mypy 诊断延迟 <500ms（增量文件）。**AC3:** 诊断管道性能测试。<br>**SC4:** Phase 3 风险评分准确率 ≥80%（人工审查作为 ground truth）。**AC4:** 100 个 diff 样本，风险评分与人工审查一致 ≥80%。 |
| **待定决策** | **Q1:** Monaco Editor 通过 npm 包还是 CDN 加载？ → **决议：**npm 包（`monaco-editor`），由 Vite 打包。脱离网络可用，匹配 Orbit 本地运行定位。<br>**Q2:** 文件树用第三方库还是自研？ → **决议：**自研 Vue 3 递归组件。需深度集成审查状态图标（待审/已批/打回/覆盖率高/低），第三方库定制成本高。<br>**Q3:** 终端是否需要完整 PTY？ → **决议：**Phase 2 先做命令执行器（POST `/api/v1/terminal/exec`），按需升级到 WebSocket PTY。 |

---

## 9.1 ADR · 前端架构决策

| ADR · 审查界面前端架构 |  |
| --- | --- |
| **技术栈版本** | monaco-editor 0.50+, xterm.js 5.5+, vis-network 9.1+（已有）, Vue 3.5+, Pinia 2.2+, Element Plus 2.10+, Vite 6+ |
| **决策** | 审查界面采用 Monaco Editor 为核心，自研文件树+审查面板为外围，通过 Pinia stores 与现有 WebSocket EventBus 集成，而非引入新的前端框架。 |
| **理由** | 1. Monaco Editor 是 VS Code 同款编辑器，内置 DiffEditor/HoverProvider/CodeActionProvider/markers/语法高亮——一次性覆盖 20+ 功能需求。<br>2. Orbit 已有 Vue 3 + Pinia + Element Plus，新增 Monaco 不引入框架碎片。<br>3. 自研文件树可深度定制审查状态图标（与审查注释系统联动），第三方库灵活性不足。<br>4. 现有 WebSocket EventBus 已承载实时推送，诊断管道和审查更新复用此通道。 |
| **架构位置** | 前端新增 4 个视图：`ReviewView`（审查主页，替代 DashboardView 的次要位置或作为独立路由 `/review`）、`DiffPanel`（Monaco DiffEditor 封装）、`FileTreePanel`（自研文件树）、`ProblemPanel`（诊断列表）。新增 4 个 Pinia stores：`review`、`editor`、`diagnostics`、`git`。后端新增 4 个模块（见 9.2 ADR）。 |
| **实施细节** | **1. Monaco Editor 集成方式：**<br>```typescript<br>// frontend/src/components/editor/MonacoDiffEditor.vue<br>import * as monaco from 'monaco-editor';<br>// 使用 Vite worker 方式加载语言服务<br>// 支持：python, typescript, javascript, sql, yaml, toml, json, markdown<br>```<br>**2. 审查状态数据流：**<br>```<br>Agent 产出代码 → Checkpoint 快照 → 后端 diff 生成 API →<br>前端 Monaco DiffEditor 渲染 → 用户逐 hunk 批准/打回 →<br>POST /api/v1/review/decisions → 后端记录 →<br>全部通过 → 用户触发 commit → POST /api/v1/git/commit<br>```<br>**3. 诊断管道：**<br>```<br>L4 mypy subprocess → 解析输出 → 标准 Diagnostic[] →<br>WebSocket push → Pinia diagnostics store → Monaco markers 渲染<br>```<br>**4. 路由设计：**<br>```typescript<br>// frontend/src/router/index.ts 新增<br>{ path: '/review/:taskId', component: ReviewView, meta: { title: '代码审查' } }<br>{ path: '/review/:taskId/file/:filePath', component: FileReviewView }<br>``` |
| **风险与缓解** | 风险1：Monaco Editor 打包体积大（~5MB gzipped）。缓解：Vite code splitting + 按需加载语言支持 + 审查页面懒加载。<br>风险2：Monaco 的 Python 语言支持不如 VS Code 完整。缓解：接受——Orbit 不替代 IDE，审查级 Python 高亮+补全足够；深度 type checking 由 L4 mypy 后端提供。<br>风险3：大型 diff（>5000 行）Monaco DiffEditor 性能。缓解：虚拟滚动（Monaco 内置支持），超大 diff 自动折叠无变更区域。 |
| **需求错位** | 若未来用户要求审查非代码文件（PDF/图片/二进制），Monaco 不适用——届时需专用查看器组件。当前仅规划文本文件审查。 |
| **技术约束** | Monaco Editor 的 web workers 需 Vite 特殊配置（`vite-plugin-monaco-editor` 或手动 worker 配置）。xterm.js 的 PTY 后端需在 FastAPI 中管理子进程生命周期，禁止僵尸进程残留。 |
| **环境配置** | `frontend/.env` 无需新增（Monaco 打包到 bundle 内）。后端需新增 `ORBIT_WORKSPACE_DIR`（项目根目录，文件服务和 Git 操作的基础路径）。 |
| **依赖链** | Monaco Editor → DiffEditor/HoverProvider/CodeActionProvider/markers（覆盖 20+ 功能）<br>　　　　　　　→ 诊断管道（L4 mypy → WebSocket → Monaco markers）<br>　　　　　　　→ 导航（CodeGraph API → Monaco DefinitionProvider/ReferenceProvider）<br>xterm.js → 后端 PTY 管理 → 终端面板<br>自研文件树 → 文件服务 API → 审查状态装饰<br>vis-network（已有）→ DAG 交互增强 → Agent 节点 drill-down |

---

## 9.2 ADR · 后端模块架构

| ADR · 审查后端模块 |  |
| --- | --- |
| **技术栈版本** | FastAPI 0.110+, SQLAlchemy 2.0+, GitPython 3.1+, pytest 8.0+ |
| **决策** | 新增 4 个后端模块：`files`（文件服务）、`review`（审查引擎+SQLAlchemy ORM）、`lsp`（诊断代理）、`terminal`（终端代理）。审查模块采用 SQLAlchemy 2.0 ORM + `Mapped`/`mapped_column`（与 graph 模块一致），dev 默认 SQLite，生产通过 `DATABASE_URL` 环境变量切 PostgreSQL——零代码改动。 |
| **理由** | 1. 文件服务独立——文件 CRUD 和 diff 生成是审查的基础设施，被多个模块依赖。<br>2. 审查引擎独立——审查状态机（Pending→InReview→Approved→ChangesRequested）是新的业务领域，不应耦合到调度器。<br>3. LSP 代理独立——L4 mypy 输出→标准化诊断格式是数据转换管道，与防幻觉层的验证逻辑职责不同。<br>4. 终端代理独立——进程生命周期管理是独立关注点，与沙箱不同（沙箱隔离执行，终端交互执行）。 |
| **架构位置** | 均位于 `src/orbit/` 下，与现有模块平级。通过 `src/orbit/api/routes/` 暴露 REST API，通过 `src/orbit/ws/` 暴露 WebSocket（诊断推送）。 |
| **实施细节** | **1. `src/orbit/files/` 模块：**<br>```python<br># models.py<br>class FileInfo(BaseModel):<br>    path: str           # relative to workspace root<br>    size: int<br>    modified_at: datetime<br>    status: FileStatus  # ADDED | MODIFIED | DELETED | UNCHANGED<br><br># service.py<br>class FileService:<br>    async def list_files(workspace: str) -> list[FileInfo]<br>    async def read_file(path: str, rev: str | None) -> str<br>    async def diff(path: str, rev_a: str, rev_b: str) -> str  # unified diff<br>    async def diff_checkpoint(task_id: str) -> dict[str, str]  # per-task before/after<br>```<br>**2. `src/orbit/review/` 模块：**<br>```python<br># models.py<br>class ReviewDecision(BaseModel):<br>    task_id: str<br>    file_path: str<br>    hunk_index: int<br>    decision: DecisionEnum  # APPROVED | REJECTED | COMMENT<br>    comment: str | None<br><br>class ReviewStatus(str, Enum):<br>    PENDING = "pending"<br>    IN_REVIEW = "in_review"<br>    CHANGES_REQUESTED = "changes_requested"<br>    APPROVED = "approved"<br><br># service.py<br>class ReviewService:<br>    async def create_review(task_id: str) -> Review<br>    async def record_decision(decision: ReviewDecision) -> None<br>    async def get_summary(task_id: str) -> ReviewSummary<br>    async def transition_status(task_id: str, status: ReviewStatus) -> None<br>```<br>**3. `src/orbit/lsp/` 模块：**<br>```python<br># models.py<br>class Diagnostic(BaseModel):<br>    file_path: str<br>    line: int<br>    column: int<br>    severity: DiagnosticSeverity  # ERROR | WARNING | INFO<br>    message: str<br>    rule_id: str | None<br>    fix: CodeAction | None<br><br># service.py<br>class DiagnosticService:<br>    async def run_mypy(file_path: str) -> list[Diagnostic]<br>    async def run_ruff(file_path: str) -> list[Diagnostic]<br>    async def get_diagnostics(task_id: str) -> dict[str, list[Diagnostic]]<br>```<br>**4. `src/orbit/terminal/` 模块：**<br>```python<br># models.py<br>class TerminalSession(BaseModel):<br>    session_id: str<br>    cwd: str<br>    created_at: datetime<br><br>class ExecResult(BaseModel):<br>    exit_code: int<br>    stdout: str<br>    stderr: str<br>    duration_ms: int<br><br># service.py<br>class TerminalService:<br>    async def exec(command: str, cwd: str, timeout: int = 30) -> ExecResult<br>    # Phase 2 后期升级为 WebSocket PTY<br>``` |
| **风险与缓解** | 风险1：GitPython 在大仓库性能。缓解：仅操作 workspace 内的 git 仓库，diff 使用 `git diff --unified` 子进程。<br>风险2：mypy subprocess 超时阻塞。缓解：asyncio.create_subprocess_exec + 5s timeout + 增量文件检查（仅检查 diff 涉及的文件）。<br>风险3：终端命令注入。缓解：白名单命令模式（Phase 2 初始仅允许 `pytest`/`ruff`/`mypy`/`git` 系列命令），后续按需扩展。 |
| **需求错位** | 若 workspace 不是 git 仓库，文件服务的 diff 和 Git 提交功能不可用——降级为文件内容查看+手动操作提示。 |
| **技术约束** | 所有文件路径必须经过 WorkspaceGuard（已有）做路径遍历防护。Git 操作必须记录审计日志。终端子进程必须在 FastAPI shutdown 事件中清理（避免僵尸进程）。 |
| **依赖链** | files → GitPython / subprocess git<br>review → files (diff) + checkpoint (snapshot) + audit (log)<br>lsp → subprocess mypy/ruff + 文件系统<br>terminal → asyncio subprocess + WorkspaceGuard |

---

## 9.3 Phase 1 ADR · 审查基础详细设计（W1-W3）

### 9.3.1 Diff 审查组件

| 子功能 | 前端实现 | 后端 API |
|--------|---------|----------|
| Diff 查看器（并排+行内） | `MonacoDiffEditor.vue` 封装 `monaco.editor.createDiffEditor()` | `GET /api/v1/files/diff?path=X&rev_a=Y&rev_b=Z` |
| 语法高亮 | Monaco 内置语言支持：python/ts/js/sql/yaml/toml/json/md | 无（前端完成） |
| Hunk 级批准/拒绝 | 自定义 gutter 渲染（+ 行号旁按钮），点击触发 `reviewStore.approveHunk()` | `POST /api/v1/review/decisions` |
| 文件树 | `FileTreePanel.vue` 递归组件 + 审查状态图标（🔴待审/🟢已批/🟡修改/⚪无变更） | `GET /api/v1/files/tree?task_id=X` |
| 只读编辑器+审查注释 | Monaco `readOnly: true` + 自定义 CodeLens 或 glyph margin 渲染注释标记 | `GET /api/v1/files/read?path=X` + `POST /api/v1/review/comments` |
| 问题面板 | `ProblemPanel.vue` 表格：文件/行/严重级/消息/规则ID，点击跳转到编辑器对应行 | `GET /api/v1/diagnostics?task_id=X` |

### 9.3.2 导航实现

Orbit 已有 CodeGraph（AST 索引），只需暴露 REST API 并接入 Monaco Provider：

```
CodeGraph.query_symbols(file, symbol)
  → GET /api/v1/codegraph/definition?file=X&symbol=Y&line=Z&col=W
  → Monaco DefinitionProvider 注册
  → F12 / Ctrl+Click 触发

CodeGraph.query_references(file, symbol)
  → GET /api/v1/codegraph/references?file=X&symbol=Y
  → Monaco ReferenceProvider 注册
  → Shift+F12 触发

L4 mypy 输出类型信息
  → GET /api/v1/lsp/hover?file=X&line=Y&col=Z
  → Monaco HoverProvider 注册
  → 鼠标悬停触发

CodeGraph.get_outline(file)
  → GET /api/v1/codegraph/outline?file=X
  → OutlinePanel.vue 渲染
  → 点击跳转
```

### 9.3.3 全局搜索

```
全局搜索
  → GET /api/v1/search?q=X&type=[file|content]
  → 文件搜索：遍历文件树 + 模糊匹配（复用 ContextMatcher 中英文分词）
  → 内容搜索：ripgrep 子进程（后端）或 FTS 索引
  → SearchPanel.vue 渲染结果列表
```

### 9.3.4 测试可见性

```
pytest --json-report
  → 后端解析 JSON 报告
  → GET /api/v1/tests/results?task_id=X
  → TestPanel.vue 渲染：文件/测试名/状态/耗时/错误信息
  → 点击失败用例 → 展开错误详情 + 跳转到对应代码

coverage.json (coverage.py 输出)
  → 后端解析
  → GET /api/v1/tests/coverage?task_id=X
  → 文件树染色（绿色=覆盖>80%，黄色=50-80%，红色=<50%）
  → Monaco 行级装饰（绿色/红色 gutter 标记）
```

### 9.3.5 Git 操作

```
Git 提交面板（CommitPanel.vue）
  ├── 文件列表（checkbox 选择）——默认全选已批准文件
  ├── Commit message 输入框（Conventional Commits 格式提示）
  ├── Amended commit 复选框
  └── 提交按钮 → POST /api/v1/git/commit

三路合并编辑器
  └── Monaco 无内置三路合并视图 → 用两个 DiffEditor 并排（BASE→OURS | BASE→THEIRS）
      或使用 `monaco.editor.createModel()` 手动控制
```

---

## 9.4 Phase 2 ADR · 审查增强+编辑干预详细设计（W4-W8）

### 9.4.1 Blame 与注释

| 子功能 | 实现 |
|--------|------|
| Git Blame 内联 | `GET /api/v1/git/blame?file=X` → 每行返回 `(rev, author_type: AGENT\|HUMAN, agent_role, timestamp)` → Monaco 行号旁 decoration（Agent 蓝/Human 绿） |
| 审查注释系统 | 行级评论→`POST /api/v1/review/comments`→WebSocket 推送→Agent 认领→Agent 修复→CommentStatus: OPEN→IN_PROGRESS→RESOLVED |
| 审查历史 | `GET /api/v1/review/history?file=X&lines=Y-Z` → TimelinePanel 显示同段代码的修改链 |
| Agent 意图注释 | 后端在 diff 生成时注入：每个 hunk 附加 `## Agent Intent: {thinking_summary}` 注释（不影响实际代码）→ Monaco 内用 CodeLens 或注释装饰展示 |

### 9.4.2 实时诊断管道

```
Agent 写代码 → 文件保存到 workspace
  → 后端监听文件变更（watchdog 或轮询）
  → 触发增量 mypy check（仅变更文件）
  → 解析 mypy 输出 → Diagnostic[]
  → WebSocket push → Pinia diagnostics store
  → Monaco editor.setModelMarkers() 渲染红色/黄色波浪线
  → CodeActionProvider 注册快速修复
```

### 9.4.3 编辑与终端

| 子功能 | 实现 |
|--------|------|
| 轻量编辑器 | Monaco `readOnly: false` 切换——用户手动编辑后 `Ctrl+S` 保存 → `PUT /api/v1/files/write` |
| 基础补全 | Monaco 内置语言服务的单词补全 + CodeGraph 符号补全（`CompletionItemProvider` 注册） |
| 安全重命名 | Monaco RenameProvider → 触发 CodeGraph 全局引用分析 → 展示预览列表 → 确认 → `POST /api/v1/files/rename` |
| 集成终端 | `TerminalPanel.vue` + xterm.js → `POST /api/v1/terminal/exec` → 展示 stdout/stderr + 退出码 |
| 构建输出 | 终端输出 + 正则 Problem Matcher 解析 → 错误行可点击跳转 |
| 右键 Run 单测 | Monaco 右键菜单扩展 → "Run this test" → `POST /api/v1/terminal/exec {"command": "pytest path/to/test.py::test_name -v"}` |

---

## 9.5 Phase 3 ADR · 智能审查详细设计（W9-W10）

### 9.5.1 风险评分引擎

```
每个 diff 文件 → 聚合 L1-L8 检测结果：
  - L1 (AST 引用): 引用失败次数 / 总引用数 → 0-100
  - L2 (动态追踪): 调用链断裂次数
  - L3 (熵): 平均熵值 / 阈值
  - L4 (类型): mypy 错误数 / 行数
  - L5 (Z3): 形式化验证失败次数
  - L6 (合约): API schema 不一致数
  - L7 (运行时): 测试失败数 / 总断言数
  - L8 (配置): 配置漂移次数
  → 加权求和 → file_risk_score (0-100)

前端渲染：文件树旁风险徽章（低🟢/中🟡/高🔴）+ Diff 面板顶部风险摘要条
```

### 9.5.2 影响分析

```
CodeGraph.query_impact(symbol)
  → 反向依赖图（谁调用了这个被修改的函数）
  → 前向依赖图（这个函数调用了谁——被修改影响的）
  → 级联风险计算（直接调用者=高影响，间接=中影响，无调用者=低影响）
  → ImpactGraph.vue（vis-network 渲染影响关系图）
```

### 9.5.3 合规自动标注

```
ComplianceRule 引擎扫描 diff：
  - "金额字段非 Decimal" → diff 行标记 🔴 合规违规
  - "缺少 @require_permission 装饰器" → diff 行标记
  - "直接写了 SQL 而不是用 ORM" → diff 行标记
  → 问题面板新增 "合规" Tab
```

### 9.5.4 协作审查

```
ReviewSession
  - 多审查者通过 WebSocket 加入同一 session
  - 审查注释实时广播
  - 审查决定（批准/打回）需指定最小批准人数（可配置，默认 1）
  - ReviewStatus: PENDING→IN_REVIEW→CHANGES_REQUESTED→APPROVED→MERGED
```

### 9.5.5 项目洞察仪表盘

```
新增 /dashboard/insights 子页面：
  - Agent 贡献统计：
    - 过去 7/30 天：Agent 写/人改/打回率/一次通过率/平均审查时间
  - 技术债务热力图：
    - treemap：模块面积=代码行数，颜色=技术债务得分（改动频次×覆盖率逆数×幻觉率）
  - 模块健康卡片：
    - 每个模块（调度器/防幻觉/图谱/...）一张卡
    - 显示：改动频次/测试通过率/幻觉检测触发率/审查通过率/最近一次审查时间
```

---

## 9.6 API 端点总览

### Phase 1 新增（13 个端点）

| 方法 | 路径 | 功能 | 模块 |
|------|------|------|------|
| GET | `/api/v1/files/tree` | 获取文件树（含审查状态） | files |
| GET | `/api/v1/files/read` | 读取文件内容 | files |
| GET | `/api/v1/files/diff` | 获取文件 diff | files |
| POST | `/api/v1/review/decisions` | 记录 hunk 级审查决定 | review |
| GET | `/api/v1/review/summary/{task_id}` | 获取审查摘要 | review |
| POST | `/api/v1/review/comments` | 添加审查注释 | review |
| GET | `/api/v1/review/comments/{task_id}` | 获取审查注释 | review |
| GET | `/api/v1/codegraph/definition` | Go to Definition | codegraph |
| GET | `/api/v1/codegraph/references` | Find All References | codegraph |
| GET | `/api/v1/codegraph/outline` | 文件大纲 | codegraph |
| GET | `/api/v1/lsp/diagnostics` | 获取诊断列表 | lsp |
| GET | `/api/v1/lsp/hover` | 悬停类型信息 | lsp |
| GET | `/api/v1/search` | 全局搜索 | files + fts |
| GET | `/api/v1/tests/results` | 测试结果 | terminal |
| GET | `/api/v1/tests/coverage` | 覆盖率数据 | terminal |
| POST | `/api/v1/git/commit` | 提交代码 | files |

### Phase 2 新增（8 个端点）

| 方法 | 路径 | 功能 | 模块 |
|------|------|------|------|
| GET | `/api/v1/git/blame` | Git Blame | files |
| PUT | `/api/v1/files/write` | 保存文件（编辑器写入） | files |
| POST | `/api/v1/files/rename` | 安全重命名 | files |
| POST | `/api/v1/terminal/exec` | 执行终端命令 | terminal |
| WebSocket | `/ws/diagnostics` | 实时诊断推送 | lsp |
| GET | `/api/v1/review/history` | 审查历史 | review |
| GET | `/api/v1/review/agent-intent` | Agent 意图注释 | review |
| GET | `/api/v1/review/agent-viewpoints` | 多 Agent 观点对比 | review |

### Phase 3 新增（10 个端点）

| 方法 | 路径 | 功能 | 模块 |
|------|------|------|------|
| GET | `/api/v1/review/risk-score/{task_id}` | 风险评分 | review |
| GET | `/api/v1/codegraph/impact` | 影响分析 | codegraph |
| GET | `/api/v1/compliance/diff-check` | Diff 合规检查 | compliance |
| POST | `/api/v1/review/sessions` | 创建协作审查会话 | review |
| POST | `/api/v1/review/sessions/{id}/join` | 加入审查会话 | review |
| PATCH | `/api/v1/review/sessions/{id}/status` | 更新审查状态 | review |
| GET | `/api/v1/insights/agent-stats` | Agent 贡献统计 | observability |
| GET | `/api/v1/insights/tech-debt` | 技术债务热力图数据 | observability |
| GET | `/api/v1/insights/module-health` | 模块健康数据 | observability |
| GET | `/api/v1/insights/knowledge-graph` | 知识图谱可视化数据 | knowledge |

---

## 9.7 数据模型（SQLAlchemy 2.0 ORM）

> **存储决策**：审查模块使用 SQLAlchemy 2.0 ORM（与 graph 模块一致）。`Mapped`/`mapped_column` 语法。
> Dev 默认 `sqlite+aiosqlite:///./data/review.db`，生产通过 `DATABASE_URL=postgresql+asyncpg://...` 环境变量切换——代码零改动。
> 引擎复用 `core/config.py` 的 `DATABASE_URL` 机制，审查模块创建自己的 `async_sessionmaker`。

```python
# src/orbit/review/models.py
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy import String, Integer, DateTime, ForeignKey, Text
from datetime import datetime
import uuid

class ReviewBase(DeclarativeBase):
    """审查模块声明基类——独立于 graph 模块的 Base"""
    pass

class Review(ReviewBase):
    __tablename__ = "reviews"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    task_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending|in_review|changes_requested|approved
    created_by: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    # 关系
    decisions: Mapped[list["ReviewDecision"]] = relationship(back_populates="review", cascade="all, delete-orphan")
    comments: Mapped[list["ReviewComment"]] = relationship(back_populates="review", cascade="all, delete-orphan")

class ReviewDecision(ReviewBase):
    __tablename__ = "review_decisions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    review_id: Mapped[str] = mapped_column(String(36), ForeignKey("reviews.id"), nullable=False, index=True)
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    hunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    decision: Mapped[str] = mapped_column(String(20), nullable=False)  # approved|rejected|comment
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    decided_by: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    # 关系
    review: Mapped["Review"] = relationship(back_populates="decisions")

class ReviewComment(ReviewBase):
    __tablename__ = "review_comments"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    review_id: Mapped[str] = mapped_column(String(36), ForeignKey("reviews.id"), nullable=False, index=True)
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    line_start: Mapped[int] = mapped_column(Integer, nullable=False)
    line_end: Mapped[int] = mapped_column(Integer, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="open")  # open|in_progress|resolved
    assigned_to: Mapped[str | None] = mapped_column(String(100), nullable=True)  # agent role or human
    created_by: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # 关系
    review: Mapped["Review"] = relationship(back_populates="comments")
```

---

🧪 验收测试 (pytest)：

```python
class TestStep9Phase1ReviewFoundation:
    """Step 9 Phase 1 审查基础 - 验收测试"""

    def test_diff_viewer_loads_and_renders(self):
        """SC1: Diff 查看器加载 1000 行 diff <2s"""
        pass

    def test_hunk_approve_reject_cycle(self):
        """逐 hunk 批准/打回 → 审查决定持久化 → 摘要正确"""
        pass

    def test_file_tree_with_review_status(self):
        """文件树显示审查状态（待审/已批/打回/无变更）"""
        pass

    def test_problem_panel_shows_diagnostics(self):
        """L4 mypy 输出 → 问题面板渲染 → 点击跳转到代码行"""
        pass

    def test_go_to_definition_navigates(self):
        """F12 → CodeGraph API → Monaco 跳转到定义位置"""
        pass

    def test_find_all_references(self):
        """Shift+F12 → CodeGraph API → 引用列表"""
        pass

    def test_hover_type_info(self):
        """鼠标悬停 → L4 mypy → 类型信息显示"""
        pass

    def test_outline_view(self):
        """大纲视图：函数/类列表 → 点击跳转"""
        pass

    def test_global_search_by_filename(self):
        """Ctrl+P 文件名搜索"""
        pass

    def test_global_search_by_content(self):
        """Ctrl+Shift+F 内容搜索 → ripgrep → 结果列表"""
        pass

    def test_test_results_panel(self):
        """pytest --json-report → 测试面板渲染 → 点击失败展开详情"""
        pass

    def test_coverage_coloring(self):
        """coverage.json → 文件树染色 → Monaco 行级装饰"""
        pass

    def test_failed_test_to_diff_correlation(self):
        """点击失败测试→关联 Agent 改动→一键回退/重分派 Agent"""
        pass

    def test_git_commit_panel(self):
        """选文件→写 message→确认→POST /api/v1/git/commit→返回 commit hash"""
        pass

    def test_git_diff_vs_head(self):
        """Git diff vs HEAD → Diff Editor 渲染"""
        pass

    def test_merge_conflict_resolution(self):
        """三路合并编辑器 → 选择 OURS/THEIRS → 保存解决结果"""
        pass

    def test_full_review_closed_loop(self):
        """E2E: Agent 产出 5 文件 PR → 审查批准 3 个→打回 2 个→提交→闭环在 Orbit 内完成"""
        pass


class TestStep9Phase2ReviewEnhancement:
    """Step 9 Phase 2 审查增强+编辑干预 - 验收测试"""

    def test_git_blame_agent_vs_human(self):
        """Git Blame: 每行标注作者类型（Agent 蓝/Human 绿）"""
        pass

    def test_review_comment_lifecycle(self):
        """审查注释：创建→Agent 认领→修复→关闭 完整生命周期"""
        pass

    def test_review_history_timeline(self):
        """同段代码的修改审查链可视化"""
        pass

    def test_code_snapshot_before_after(self):
        """per-task 代码快照对比"""
        pass

    def test_agent_intent_annotation(self):
        """Diff hunk 附带 Agent thinking 摘要"""
        pass

    def test_dag_node_interactive_drilldown(self):
        """点击 DAG 节点→展示该步骤输入/输出/diff/日志"""
        pass

    def test_token_per_file_breakdown(self):
        """Token 消耗 per-file 明细"""
        pass

    def test_agent_reasoning_trace(self):
        """审查时查看 Agent reasoning trace"""
        pass

    def test_multi_agent_viewpoint_comparison(self):
        """Reviewer vs Developer 分歧 → 双方论据并排对比"""
        pass

    def test_real_time_diagnostics_wave(self):
        """文件保存→L4 mypy→WebSocket push→Monaco 波浪线 <500ms"""
        pass

    def test_quick_fix_code_action(self):
        """Lightbulb→"Add import"→代码自动修改"""
        pass

    def test_format_trigger(self):
        """一键格式化→ruff/black 执行→结果更新到编辑器"""
        pass

    def test_lightweight_editor_save(self):
        """Monaco 可写模式→Ctrl+S→文件保存"""
        pass

    def test_basic_code_completion(self):
        """人工编辑时 Monaco 单词补全+CodeGraph 符号补全"""
        pass

    def test_safe_rename_with_preview(self):
        """F2→预览引用→确认→全局重命名"""
        pass

    def test_integrated_terminal_exec(self):
        """xterm.js→执行命令→stdout/stderr 渲染"""
        pass

    def test_build_output_with_error_click(self):
        """构建输出→错误解析→点击跳转"""
        pass

    def test_right_click_run_single_test(self):
        """右键→Run this test→终端执行→结果面板更新"""
        pass


class TestStep9Phase3IntelligentReview:
    """Step 9 Phase 3 智能审查 - 验收测试"""

    def test_risk_score_accuracy(self):
        """SC4: 100 个 diff 样本，风险评分与人工审查一致 ≥80%"""
        pass

    def test_auto_review_summary(self):
        """PR 打开→自动摘要："3 低风险/1 中风险/1 高风险——改了核心逻辑" """
        pass

    def test_impact_analysis_visualization(self):
        """CodeGraph 依赖图→受影响模块可视化"""
        pass

    def test_test_gap_auto_marking(self):
        """函数 A 改动但测试未更新→标记"""
        pass

    def test_compliance_rule_annotation(self):
        """float 非 Decimal→diff 标红合规违规"""
        pass

    def test_review_checklist_auto_generation(self):
        """改核心模块→自动生成："必须检查借贷平衡/必须检查权限装饰器" """
        pass

    def test_multi_reviewer_collaboration(self):
        """两人同时审查→看到彼此注释"""
        pass

    def test_review_status_workflow(self):
        """Pending→In Review→Changes Requested→Approved→Merged 完整流转"""
        pass

    def test_agent_contribution_stats(self):
        """过去 7 天：Agent 写/人改/打回率/一次通过率"""
        pass

    def test_tech_debt_heatmap(self):
        """Treemap：模块面积=代码行数，颜色=技术债务得分"""
        pass

    def test_module_health_dashboard(self):
        """模块健康卡片：改动频次/测试通过率/幻觉率/审查通过率"""
        pass

    def test_knowledge_graph_interactive(self):
        """知识图谱点击→跳转对应代码"""
        pass

    def test_dark_light_theme_switch(self):
        """暗色/亮色主题切换"""
        pass

    def test_review_policy_configuration(self):
        """配置：哪些文件需多少层幻觉检测、哪些模块强制人工审查"""
        pass

    def test_keyboard_shortcut_customization(self):
        """快捷键自定义→配置持久化→生效"""
        pass

    def test_database_schema_visualization(self):
        """DBGraph→表关系图→点击表查看列"""
        pass

    def test_migration_script_review(self):
        """Alembic 迁移→before/after schema 对比"""
        pass

    def test_checkpoint_rollback_visualization(self):
        """检查点→可视化选择回滚点→预览→确认→执行"""
        pass
```

---

## 9.8 调度器/防幻觉/图谱影响分析

| 组件 | 影响 | 变更 |
|------|------|------|
| **调度器** | 低影响 | 无状态变更。审查阶段是 Agent 完成后的独立流程，不修改调度器状态机。新增 `CHECKPOINT` 状态（已有检查点功能）的可视化选择接口。 |
| **防幻觉 L1-L8** | 低影响 | 无判定逻辑变更。L4 mypy 输出现有管道改为同时推送前端（诊断面板）。L1 CodeGraph 查询新增 REST API 暴露（导航功能复用）。Phase 3 风险评分聚合读取各层已有指标，不修改判定逻辑。 |
| **代码图谱** | 中影响 | 新增 REST API 端点（definition/references/outline/impact），底层查询逻辑复用现有 CodeGraphEngine。需添加 endpoint 的 `require_permission` 并在 `rbac.py` 注册。 |
| **数据库图谱** | 低影响 | Phase 3 新增 schema 可视化 API，复用现有 DBGraphEngine 反射逻辑。 |
| **配置图谱** | 无影响 | 无变更。 |
| **知识图谱** | 低影响 | Phase 3 新增知识图谱可视化 API，复用现有 KnowledgeEngine 查询逻辑。 |
| **合规引擎** | 中影响 | Phase 3 新增 diff 合规检查模式（`check_diff()` 方法），在现有规则引擎上扩展，不修改已有规则。 |
| **检查点** | 低影响 | Phase 3 新增可视化回滚接口，复用现有 Checkpoint Manager。 |

---

## 9.9 边界 Case 清单

| 场景 | 预期行为 |
|------|---------|
| Monaco Editor 加载失败（CDN/网络不可达） | 降级为纯文本 `<pre>` diff 模式，功能受限但审查可继续 |
| Diff 超过 5000 行 | Monaco 虚拟滚动处理，自动折叠未变更区域 |
| L4 mypy 超时（>5s） | 显示"诊断加载中"骨架屏，不阻塞 diff 渲染和审查 |
| 同时打开 10+ 个文件的 diff | 分页/虚拟列表，只渲染当前可见的 2-3 个 diff |
| Git 仓库不存在（非 git workspace） | 文件树正常显示，diff/Git 提交功能不可用，显示提示 |
| Agent 并发修改同一文件导致冲突 | 审查会话锁定为只读，直到冲突在合并面板中解决 |
| 审查过程中 Agent 被重新分派修复同一文件 | 创建新的审查版本，旧审查保留只读 |
| 用户手动编辑 + Agent 改同一文件 | 用户编辑先 commit 或 stash，Agent 修改在用户版本之上应用 |
| 终端命令执行超时（>30s） | 返回部分输出 + "命令超时"标记，不阻塞 UI |
| 审查注释分配给不存在的 Agent 角色 | 提示"Agent 角色不存在"，注释保持在 OPEN 状态 |
| 三路合并中用户选择丢弃所有更改 | 提示确认→文件恢复为 BASE 版本 |
| 多个审查者同时批准/打回同一 hunk | 后到达的决定覆盖先到达的（last-write-wins），前端显示决策历史 |
| 覆盖率数据文件缺失（coverage.json 不存在） | 覆盖率视图显示"无数据"，不阻塞其他功能 |

---

> 阶段文档索引：
> - 阶段 1 PRD: `docs/requirements/2026-06-29-IDE功能追赶/阶段1-PRD-IDE功能追赶.md`
> - 阶段 2 技术方案: `docs/requirements/2026-06-29-IDE功能追赶/阶段2-技术方案-IDE功能追赶.md`
> - 开发计划: `docs/开发计划/06-IDE功能追赶计划.md`
