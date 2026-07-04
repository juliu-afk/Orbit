# 阶段2 技术方案 — Inkeep 借鉴 5 项

> 日期：2026-07-04 | 基于阶段1 PRD（验收标准共 26 条），本次技术方案覆盖 26 条，无偏离。

## 1. PRD 对照表

| PRD 验收标准 | 技术方案覆盖 | 备注 |
|-------------|------------|------|
| S1.1-S1.5 (模型路由 5 条) | §2.1 TaskModelRouter | 新增 `gateway/task_router.py` |
| S2.1-S2.6 (三级存储 6 条) | §2.2 ArtifactTierManager | 新增 `graph/tier.py` + `hallucination/` 集成 |
| S3.1-S3.4 (按需加载 4 条) | §2.3 load_knowledge tool | `tools/` 注册 + `knowledge/engine.py` 接口 |
| S4.1-S4.6 (Trace 6 条) | §2.4 TraceSpan + API + UI | 新增 `observability/trace.py` + API + 前端组件 |
| S5.1-S5.8 (配置面板 8 条) | §2.5 ConfigStore + API + 前端页面 | 新增 `core/config_store.py` + 路由 + Vue 页面 |

## 2. 详细设计

### 2.1 US-1: TaskModelRouter（P0，纯后端）

**改动范围**：

| 文件 | 操作 | 说明 |
|------|------|------|
| `gateway/task_router.py` | **新增** | TaskModelRouter——task_type→model 映射 |
| `gateway/routing.py` | 修改 | 新增 `TaskType` 枚举，`select_model` 接受 task_type |
| `gateway/schemas.py` | 修改 | `LLMRequest` 新增 `task_type: TaskType \| None` |
| `gateway/client.py` | 修改 | `LLMClient.generate()` 读取 task_type 传给 router |
| `scheduler/task_runner.py` | 修改 | `_agent_cycle` 调用 LLM 时传入 task_type |
| `core/config/` | 新增目录 | 默认配置 YAML 文件 |

**数据模型**：

```python
class TaskType(StrEnum):
    REASONING = "reasoning"              # 架构设计/问题分析/决策
    STRUCTURED_OUTPUT = "structured_output"  # JSON Schema 约束输出
    SUMMARIZATION = "summarization"      # 日志摘要/代码diff摘要/长文本压缩

# 默认映射（YAML 可配置）
DEFAULT_TASK_MODEL_MAP = {
    TaskType.REASONING: "deepseek/deepseek-v4-pro",
    TaskType.STRUCTURED_OUTPUT: "deepseek/deepseek-v4-flash",
    TaskType.SUMMARIZATION: "openai/glm-4.7-flash",
}
```

**数据流**：

```
TaskRunner._agent_cycle()
  → 判断当前 task_type（根据 TaskState + agent_role 推导）
  → LLMClient.generate(prompt, task_type=TaskType.REASONING)
    → TaskModelRouter.select(task_type) → "deepseek/deepseek-v4-pro"
    → 现有 circuit_breaker + litellm 调用
```

**task_type 推导规则**（硬编码，简单可靠）：

```python
# TaskRunner 内部
_TASK_TYPE_MAP: dict[TaskState, TaskType] = {
    TaskState.PLANNING: TaskType.REASONING,
    TaskState.CODING: TaskType.REASONING,        # 代码生成需要推理
    TaskState.VERIFYING: TaskType.STRUCTURED_OUTPUT,  # 审查结果结构化
    TaskState.PARSING: TaskType.STRUCTURED_OUTPUT,    # 需求解析结构化
    TaskState.IDLE: TaskType.SUMMARIZATION,           # 闲聊/摘要
}
```

**单元测试覆盖**：
- `test_task_router_reasoning()` → 返回 Pro 模型
- `test_task_router_structured()` → 返回 Flash 模型
- `test_task_router_summarization()` → 返回 GLM fallback
- `test_task_router_unknown_type()` → 回退 default_model
- `test_task_router_circuit_open()` → 熔断时降级

---

### 2.2 US-2: ArtifactTierManager（P0，纯后端）

**改动范围**：

| 文件 | 操作 | 说明 |
|------|------|------|
| `graph/tier.py` | **新增** | ArtifactTierManager——三级分级 + 动态调整 |
| `graph/__init__.py` | 修改 | 导出 ArtifactTierManager |
| `hallucination/__init__.py` | 修改 | 注册 L2.5 互补层（不改变 L1-L8 判定） |
| `core/config/artifact_tiers.yaml` | **新增** | 默认阈值配置 |

**数据模型**：

```python
class ArtifactTier(StrEnum):
    PREVIEW = "preview"    # ≤2KB 摘要，自动进上下文
    FULL = "full"          # 完整结果，按需 tool 查询
    OVERSIZED = "oversized"  # 拒绝加载，返回细化建议

@dataclass
class TieredResult:
    tier: ArtifactTier
    preview: str           # 摘要（所有 tier 都有）
    full_content: str | None  # 仅 FULL tier 非空
    size_bytes: int
    hint: str = ""         # oversized 时："请细化查询条件，如添加 domain 过滤"

class ArtifactTierManager:
    preview_threshold: int = 2048      # 2KB
    full_threshold: int = 65536        # 64KB
    # 动态调整统计
    _preview_hits: int = 0
    _preview_total: int = 0
    _oversized_count: int = 0
    _total_queries: int = 0
```

**调用链**：

```
六图谱查询 (CodeGraphEngine / DBGraphEngine / etc.)
  → ArtifactTierManager.classify(result)
    → 计算 result 大小
      → ≤ preview_threshold → PREVIEW (摘要截断到 2KB)
      → ≤ full_threshold    → FULL (preview + full_content)
      → > full_threshold    → OVERSIZED (preview + hint)
  → Agent 上下文只注入 preview
  → Agent 需要详情时调用 load_artifact tool → 返回 full_content
```

**动态调整逻辑**（每 100 次查询触发评估）：

```python
def _maybe_adjust(self):
    if self._total_queries < 100:
        return
    hit_rate = self._preview_hits / max(self._preview_total, 1)
    oversized_rate = self._oversized_count / max(self._total_queries, 1)
    if hit_rate < 0.8:
        self.preview_threshold = min(self.preview_threshold * 2, 8192)  # 翻倍，上限 8KB
    if oversized_rate > 0.1:
        self.full_threshold = min(self.full_threshold * 2, 262144)  # 翻倍，上限 256KB
    # 重置计数器
    self._preview_hits = self._preview_total = self._oversized_count = self._total_queries = 0
```

**与防幻觉层关系**：L3 熵监控管 token 成本安全侧，ArtifactTierManager 管信息密度侧。两者互补，不修改 L1-L8 的任何判定逻辑。

**单元测试覆盖**：
- `test_tier_preview()` → 1KB 结果 → PREVIEW
- `test_tier_full()` → 32KB 结果 → FULL
- `test_tier_oversized()` → 128KB 结果 → OVERSIZED
- `test_tier_boundary_preview()` → 2048 字节 → FULL（不等号 `<`）
- `test_dynamic_adjust_hit_rate_low()` → 命中率 < 80% → 升 preview 阈值
- `test_dynamic_adjust_oversized_high()` → oversized > 10% → 升 full 阈值

---

### 2.3 US-3: load_knowledge Tool（P1，纯后端）

**改动范围**：

| 文件 | 操作 | 说明 |
|------|------|------|
| `tools/knowledge_tools.py` | **新增** | `load_knowledge` tool handler |
| `tools/registry.py` | 修改 | 注册 load_knowledge 到 ToolRegistry |
| `knowledge/engine.py` | 修改 | 新增 `query_structured()` 方法（返回 dict 而非 QueryResult） |

**Tool Schema**（JSON Schema，LLM 可见）：

```python
LOAD_KNOWLEDGE_SCHEMA = {
    "name": "load_knowledge",
    "description": "按需从知识图谱加载领域知识。仅在需要了解特定概念时调用，不要预加载。",
    "parameters": {
        "type": "object",
        "properties": {
            "domain": {
                "type": "string",
                "description": "知识领域: accounting(会计) | taxation(税务) | auditing(审计) | software(软件工程)",
            },
            "concept": {
                "type": "string",
                "description": "概念名，如 'CurrentRatio' 'DoubleEntry' 'Voucher'",
            },
        },
        "required": ["domain", "concept"],
    },
}
```

**调用链**：

```
Agent (ReAct 循环)
  → 需要了解"流动比率"概念
  → tool_call: load_knowledge(domain="accounting", concept="CurrentRatio")
    → ToolRegistry.invoke("load_knowledge", ...)
      → handler → KnowledgeEngine.query_structured(domain, concept)
        → SQLite 查询 → 返回结构化 dict
  → Agent 拿到知识片段，注入当前推理上下文
```

**`KnowledgeEngine.query_structured()` 新增方法**：

```python
def query_structured(self, domain: str, concept: str) -> dict:
    """返回结构化 dict，供 tool handler 使用。
    与现有 query() 区别：query() 返回 QueryResult 对象（内部用），
    query_structured() 返回 JSON-serializable dict（tool 接口用）。
    """
    result = self.query(domain, concept)
    if result is None:
        return {"found": False, "message": f"概念 '{concept}' 在领域 '{domain}' 中未找到"}
    return {"found": True, "content": result.content, "source_uri": result.source_uri}
```

**单元测试覆盖**：
- `test_load_knowledge_found()` → 返回结构化知识
- `test_load_knowledge_not_found()` → 返回 found=False
- `test_load_knowledge_empty_domain()` → 返回 found=False

---

### 2.4 US-4: Trace 驾驶舱（P2，后端+前端）

**改动范围**：

| 文件 | 操作 | 说明 |
|------|------|------|
| `observability/trace.py` | **新增** | TraceSpan 模型 + TraceStore + TraceCollector |
| `observability/__init__.py` | 修改 | 导出 trace 模块 |
| `api/routes/observability.py` | 修改 | 新增 `GET /observability/trace/{task_id}` + `GET /observability/trace/export/{task_id}` |
| `scheduler/task_runner.py` | 修改 | `_agent_cycle` / `_run_agent` 中埋 span |
| `frontend/src/components/ops/TraceViewer.vue` | **新增** | Trace 查看器组件 |
| `frontend/src/components/ops/OpsPanel.vue` | 修改 | 新增 "Trace" Tab |
| `frontend/src/stores/trace.ts` | **新增** | Pinia store |

**数据模型**：

```python
class SpanStatus(StrEnum):
    OK = "ok"
    ERROR = "error"
    TIMEOUT = "timeout"

class TraceSpan(BaseModel):
    span_id: str          # UUID
    parent_span_id: str | None  # 根 span 为 None
    task_id: str
    component: str        # "orchestrator" | "task_runner" | "sandbox" | "agent" | "tool"
    action: str           # "schedule" | "agent_call" | "tool_exec" | "verify" | "checkpoint"
    input_summary: str    # 输入摘要（截断到 256 字符）
    output_summary: str   # 输出摘要（截断到 256 字符）
    duration_ms: float
    status: SpanStatus
    created_at: datetime
    metadata: dict = {}   # 扩展字段（model, token_count, tool_name 等）

class TraceTree(BaseModel):
    task_id: str
    root_spans: list[TraceSpan]  # parent_span_id=None 的顶层 span
    total_duration_ms: float
    span_count: int
```

**埋点位置**（`task_runner.py`）：

```python
# orchestrator 调度
span = TraceCollector.start_span(task_id, component="orchestrator", action="schedule")
# ... 调度逻辑 ...
TraceCollector.end_span(span, status=SpanStatus.OK)

# agent 调用
span = TraceCollector.start_span(task_id, parent=parent_span_id,
    component="agent", action="agent_call")
# ... LLMClient.generate() ...
TraceCollector.end_span(span, status=SpanStatus.OK)

# 沙箱执行
span = TraceCollector.start_span(task_id, parent=parent_span_id,
    component="sandbox", action="tool_exec")
# ... docker exec ...
TraceCollector.end_span(span, status=SpanStatus.OK)
```

**API 设计**：

```
GET /observability/trace/{task_id}
  响应: { code: 0, data: TraceTree }

GET /observability/trace/{task_id}/export
  响应: application/json (OTEL JSON 格式)
  触发手动导出

GET /observability/trace/recent?limit=20
  响应: { code: 0, data: [TraceTree概要] }  # 列表页用
```

**前端 UI**：

```
OpsPanel.vue
  ├── Tab: 备份快照（现有）
  ├── Tab: 发布历史（现有）
  ├── Tab: SOP（现有）
  └── Tab: Trace 查看器（新增）
       └── TraceViewer.vue
            ├── 任务列表（最近 20 个任务）
            ├── DAG 图（复用 DagCanvas 的 vis-network 方案）
            │   └── 节点颜色: ok=绿 error=红 timeout=黄
            └── 选中 span → 侧边详情面板
                 ├── component / action
                 ├── duration_ms
                 ├── input_summary / output_summary
                 └── metadata（model, token_count 等）
```

**三层保留实现**：

```python
class TraceStore:
    FULL_RETENTION_DAYS = 7    # 可配置
    SUMMARY_RETENTION_DAYS = 30

    async def cleanup(self):
        # 7-30 天前：聚合子 span → 只保留 root span
        # >30 天前：删除
        ...
```

**E2E 测试**：`test_trace_create_and_view` — 创建任务 → 等完成 → `GET /observability/trace/{task_id}` → 验证 span 树完整。

---

### 2.5 US-5: 配置面板（P2，后端+前端）— 真 Git 后端

**方案决策**：配置存储 = YAML 文件 + Git 仓库。不用 SQLite 存配置——git 天然提供 branch/merge/diff/log/rollback，零额外存储设计。

**配置目录结构**：

```
~/.orbit/config/                  # Git 仓库根目录
├── model_routing.yaml            # US-1 模型映射
├── artifact_tiers.yaml           # US-2 阈值
├── prompts/
│   ├── architect.yaml
│   ├── developer.yaml
│   ├── reviewer.yaml
│   └── qa.yaml
├── hallucination.yaml            # L1-L8 参数
└── trace.yaml                    # US-4 保留天数
```

**改动范围**：

| 文件 | 操作 | 说明 |
|------|------|------|
| `core/config_store.py` | **新增** | ConfigStore——YAML 文件读写 + Git 操作封装 |
| `core/config/` | 新增目录 | 默认配置 YAML 文件（首次 init 时 copy 到 `~/.orbit/config/`） |
| `api/routes/config_routes.py` | **新增** | `GET/PUT /api/v1/config` + Git 历史/branch/merge/diff API |
| `frontend/src/views/ConfigView.vue` | **新增** | 配置页面 |
| `frontend/src/components/config/YamlEditor.vue` | **新增** | CodeMirror YAML 编辑器 |
| `frontend/src/components/config/VersionHistory.vue` | **新增** | Git log + diff + 回滚 + 分支列表 |
| `frontend/src/router/index.ts` | 修改 | 新增 `/config` 路由 |
| `frontend/src/stores/config.ts` | **新增** | Pinia store |

**Git 操作封装**（`ConfigStore` 内部，调 `git` CLI）：

| 方法 | Git 命令 | 说明 |
|------|---------|------|
| `init()` | `git init` + 首次 copy 默认 YAML + `git add -A && git commit` | 幂等——已存在则跳过 |
| `read(section)` | 读 YAML 文件 → parse → return dict | 不调 git |
| `write(section, data, author)` | 写 YAML 文件 → `git add` → `git commit -m` | 每次保存 = 一次 commit |
| `history(section)` | `git log --oneline --follow <file>` | 返回 commit 列表 |
| `diff(commit_a, commit_b, file)` | `git diff <a> <b> -- <file>` | 返回 unified diff |
| `rollback(section, commit_hash, author)` | `git checkout <hash> -- <file>` → `git commit -m` | 回滚 = 新 commit |
| `branches()` | `git branch --list` | 分支列表 |
| `create_branch(name)` | `git checkout -b <name>` | 创建分支 |
| `merge_branch(name, author)` | `git merge <name>` | 合并，冲突时返回冲突文件列表 |
| `conflict_content(file)` | 读文件原始内容（含 `<<<<<<<` 标记） | 前端展示冲突 |
| `resolve_conflict(file, resolved_content, author)` | 写文件 → `git add` → `git commit` | 手动解决冲突 |

**数据模型**：

```python
class ConfigSection(StrEnum):
    MODEL_ROUTING = "model_routing"
    ARTIFACT_TIERS = "artifact_tiers"
    PROMPTS = "prompts"
    HALLUCINATION = "hallucination"
    TRACE = "trace"

class GitCommit(BaseModel):
    hash: str              # short hash (7 char)
    full_hash: str         # full 40-char hash
    message: str
    author: str
    timestamp: datetime
    file: str              # 变更的配置文件路径

class GitBranch(BaseModel):
    name: str
    is_current: bool
    last_commit: GitCommit | None

class MergeResult(BaseModel):
    success: bool
    conflict_files: list[str]  # 冲突文件列表，空 = 无冲突
    message: str
```

**API 设计**：

```
# 配置读写
GET  /api/v1/config/{section}
  响应: { code: 0, data: { key: value, ... } }

PUT  /api/v1/config/{section}
  请求: { content: "...", author: "admin" }
  校验: YAML parse → 失败 400 + 行列号
  成功后 git commit
  响应: { code: 0, data: { section, commit_hash: "a1b2c3d" } }

# 版本历史
GET  /api/v1/config/{section}/history?limit=20
  响应: { code: 0, data: [GitCommit] }

GET  /api/v1/config/{section}/diff?from=<hash>&to=<hash>
  响应: { code: 0, data: { unified_diff: "..." } }

# 回滚
POST /api/v1/config/{section}/rollback
  请求: { commit_hash: "a1b2c3d", author: "admin" }
  响应: { code: 0, data: { new_commit_hash: "e5f6g7h" } }

# 分支操作
GET  /api/v1/config/branches
  响应: { code: 0, data: [GitBranch] }

POST /api/v1/config/branches
  请求: { name: "experiment", from_branch: "main" }
  响应: { code: 0, data: { name } }

POST /api/v1/config/merge
  请求: { from_branch: "experiment", into_branch: "main", author: "admin" }
  响应: { code: 0, data: MergeResult }

# 冲突解决
GET  /api/v1/config/conflict/{section}
  响应: { code: 0, data: { content_with_markers: "..." } }

PUT  /api/v1/config/conflict/{section}
  请求: { resolved_content: "...", author: "admin" }
  响应: { code: 0, data: { commit_hash } }
```

**前端 UI**：

```
ConfigView.vue
  ├── 顶部工具栏：当前分支 + 切换分支 + 创建分支 + 合并
  ├── 左侧：Section 列表
  │   ├── 模型路由
  │   ├── 分级阈值
  │   ├── Prompt 模板
  │   ├── 防幻觉参数
  │   └── Trace 设置
  └── 右侧：编辑区
       ├── YamlEditor.vue（CodeMirror，YAML 语法高亮）
       │   └── 保存按钮 → PUT + git commit
       ├── 校验错误提示（行号+列号）
       └── VersionHistory.vue
            ├── Git log 列表（commit hash + message + author + time）
            ├── 选中两个版本 → diff 对比（unified diff 语法高亮）
            ├── 回滚按钮 → 预览 diff → 确认 → git checkout + commit
            └── 合并冲突时 → 冲突文件列表 → 点击进入冲突编辑器 → 保存解决
```

**E2E 测试**：
- `test_config_edit_and_commit` — 编辑配置 → 保存 → 验证 git log 有新 commit
- `test_config_rollback` — 编辑两次 → 回滚到第一次 → 验证内容正确
- `test_config_branch_and_merge` — 创建分支 → 编辑 → 合并回 main → 验证内容合并
- `test_config_merge_conflict` — 两个分支改同一行 → 合并 → 验证返回冲突 → 解决冲突 → 验证合并完成

---

## 3. 跨切面关注点

### 3.1 调度器状态变更

**US-1 影响**：TaskRunner 调用 LLMClient 时新增 task_type 参数。不改变状态机转换逻辑、检查点策略、回滚路径。纯参数传递。

**US-4 影响**：TaskRunner 内部新增 span 埋点。埋点是旁路逻辑（observer 模式），不影响主流程。span 创建失败不阻塞任务执行。

### 3.2 防幻觉层影响

**US-2 影响**：ArtifactTierManager 与 L3（熵监控）互补——L3 管"超了没"，tier 管"怎么裁"。不修改 L1-L8 任何判定逻辑。在 `hallucination/__init__.py` 注册为 L2.5 互补层（文档层面），实际代码独立在 `graph/tier.py`。

### 3.3 图谱 Schema 变更

无 CodeGraph SQLite schema 变更。US-2 的分级逻辑在查询层（`graph/tier.py`），不改变图谱存储格式。

### 3.4 数据库迁移

仅新增 1 个 SQLite 表（`trace_spans`）。配置存储用 Git + YAML 文件，不需要 SQLite 表。Alembic 迁移：

```bash
alembic revision --autogenerate -m "add trace_spans"
```

迁移脚本可重复执行（IF NOT EXISTS）。

---

## 4. 依赖链

```
US-1 (TaskModelRouter)
  └── core/config/ (YAML 配置)

US-2 (ArtifactTierManager)
  └── core/config/ (阈值配置)
  └── graph/ (六图谱查询结果)

US-3 (load_knowledge)
  └── knowledge/engine.py
  └── tools/registry.py

US-4 (Trace)
  └── observability/ (现有 OTEL + audit)
  └── scheduler/task_runner.py
  └── api/routes/observability.py
  └── frontend/ (TraceViewer)

US-5 (Config Panel)
  └── core/config_store.py
  └── api/routes/config_routes.py
  └── frontend/ (ConfigView + YamlEditor + VersionHistory)
```

**加载顺序**：US-5（配置基础设施）→ US-1（依赖配置）→ US-2（依赖配置）→ US-3（独立）→ US-4（Trace 后端）→ US-4（Trace 前端）+ US-5（配置前端）。

**并行机会**：US-3 独立于 US-1/US-2，可并行开发。US-4 后端与 US-5 后端可并行。

---

## 5. 边界 Case 清单

| 分类 | 场景 | 预期行为 |
|------|------|---------|
| **US-1** | task_type 为 None | 使用 default_model（DS V4 Pro） |
| **US-1** | 配置的模型在 provider 不可用 | circuit_breaker 熔断 → fallback_model |
| **US-1** | 同一任务多次 LLM 调用，task_type 不同 | 每次调用独立路由（不缓存 task_type） |
| **US-2** | 查询结果为空 | 跳过 tier 判定，返回空结果（无 tier 字段） |
| **US-2** | preview 摘要截断在多字节字符中间 | 用 UTF-8 safe truncate（找最近完整字节边界） |
| **US-2** | 动态调整后阈值超过模型上下文窗口 | 上限钳制：preview≤8KB, full≤min(256KB, context_window*0.2) |
| **US-3** | Agent 高频调用同一概念 | ToolRegistry 自带滑动窗口限流，无需额外处理 |
| **US-3** | domain 参数不在白名单 | 返回 found=False，"未知领域" |
| **US-4** | 任务执行中查询 trace | 返回已有 span（部分 trace），status 标记为 "in_progress" |
| **US-4** | trace_spans 表过大（>100万行） | cleanup 任务每 6h 运行，删除 >30 天数据 |
| **US-4** | OTEL 导出时任务仍在运行 | 导出当前快照，文件头标记 "partial" |
| **US-5** | YAML 语法错误 | HTTP 400 + `{line: 3, col: 12, message: "unexpected ':'"}` |
| **US-5** | 并发编辑同 section | 乐观锁：PUT 时传 `expected_version`，不匹配返回 409 |
| **US-5** | 回滚到一个格式已过时的版本 | 允许回滚（只存 JSON 快照），前端校验显示警告 |
| **US-5** | config_history 为空时回滚 | 404 "no previous versions" |
| **通用** | 数据库文件被锁定（SQLite busy） | 重试 3 次（WAL 模式），失败返回 503 |

## 6. 风险与缓解

| 风险 | 严重程度 | 缓解措施 |
|------|---------|---------|
| US-1 task_type 推导不准确（如 REVIEWING 误判为 REASONING） | 中 | 先硬编码 TaskState→TaskType 映射，日志记录每次路由决策，运行 1 周后审计调整 |
| US-2 动态调整过激（频繁升降阈值） | 低 | 每 100 次查询才评估一次，每次调整有上限（翻倍或减半） |
| US-4 span 埋点影响任务吞吐 | 中 | span 写入用异步队列（asyncio.Queue）+ 批量 flush，不阻塞主流程 |
| US-5 YAML 编辑器引入重依赖（Monaco ≈ 5MB） | 中 | 用 CodeMirror 6（~200KB gzipped），已支持 YAML 语法高亮 |
| US-2 + US-1 同时改动 gateway 层 | 中 | 两个 feature 在同一层但改动不同文件（task_router.py vs tier.py），无合并冲突 |

---

> **阶段门禁**：技术方案完成。等待用户确认后进入阶段 3（编码实现）。
