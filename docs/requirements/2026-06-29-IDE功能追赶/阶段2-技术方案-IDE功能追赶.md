# 阶段 2 技术方案：Orbit IDE 功能追赶 — Phase 1 审查基础

> **基线文档**: `docs/requirements/2026-06-29-IDE功能追赶/阶段1-PRD-IDE功能追赶.md`
> **PRD+ADR**: `docs/PRD+ADR_IDE功能追赶.md` §9.0-9.3, §9.7
> **开发计划**: `docs/开发计划/06-IDE功能追赶计划.md`
> **日期**: 2026-06-29 | **状态**: 待用户确认

---

## 1. PRD 对照表

| # | 验收标准 | 技术覆盖 | 偏离说明 |
|---|---------|---------|---------|
| SC1 | 审查 5 文件 PR 闭环（含 GPG 签名），零切出 | Monaco DiffEditor + 审查面板 + Git API + GPG | 无 |
| SC2 | 1000 行 diff 加载 <2s | Monaco 虚拟滚动 + Vite code splitting + 懒加载 | 无 |
| SC3 | 18 项功能独立可验 | 每项对应独立组件/API + 单元测试 | 无 |
| SC4 | GPG Verified 标记 | `git commit -S<keyid>` + GitHub 自动验证 | 无 |

---

## 2. 总体架构

```
┌─ 前端 (Vue 3 + Monaco) ─────────────────────────────────────────┐
│                                                                   │
│  /review/:taskId  (ReviewView)                                    │
│  ┌──────────────┬──────────────────────┬──────────────────┐      │
│  │ FileTreePanel │  MonacoDiffEditor    │  ReviewToolbar    │      │
│  │ (自研递归组件) │  (并排/行内切换)      │  (批准/打回/提交)  │      │
│  │ 审查状态图标   │  glyph margin 按钮   │  GPG key 选择     │      │
│  │ 覆盖率着色     │  语法高亮            │  commit message   │      │
│  ├──────────────┴──────────────────────┴──────────────────┤      │
│  │ ProblemPanel   TestPanel    SearchPanel    OutlinePanel  │      │
│  └─────────────────────────────────────────────────────────┘      │
│                                                                   │
│  Pinia Stores: review | editor | diagnostics | git                │
│  HTTP: api.ts (已有) + WebSocket: useWebSocket.ts (已有)          │
└───────────────────────┬───────────────────────────────────────────┘
                        │
┌─ 后端 (FastAPI) ─────┼───────────────────────────────────────────┐
│                       │                                            │
│  /api/v1/files/*      /api/v1/review/*    /api/v1/git/*           │
│  /api/v1/codegraph/*  /api/v1/lsp/*       /api/v1/search/*        │
│  /api/v1/tests/*                                                    │
│                                                                   │
│  files/ (文件服务)   review/ (审查引擎+ORM)   lsp/ (诊断代理)     │
│                                                                   │
│  复用: codegraph/  compliance/  observability/  checkpoint/       │
└───────────────────────────────────────────────────────────────────┘
```

---

## 3. API 设计

### 3.1 文件服务 (`src/orbit/api/routes/files.py`)

| 方法 | 路径 | 请求 | 响应 | 错误码 |
|------|------|------|------|--------|
| GET | `/api/v1/files/tree` | `?task_id=X` | `{ files: [{path, size, status, review_status}] }` | 404 task 不存在 |
| GET | `/api/v1/files/read` | `?path=X[&task_id=Y]` | `{ content: str, language: str }` | 404 文件不存在 |
| GET | `/api/v1/files/diff` | `?path=X&rev_a=Y&rev_b=Z` | `{ original: str, modified: str, language: str, hunks: [...] }` | 400 rev 无效 |

**语言检测**：从文件扩展名映射，不需要后端语言服务。

### 3.2 审查引擎 (`src/orbit/api/routes/review.py`)

| 方法 | 路径 | 请求 | 响应 | 错误码 |
|------|------|------|------|--------|
| POST | `/api/v1/review/sessions` | `{ task_id: str }` | `{ review_id, status, files }` | 409 已有活跃审查 |
| GET | `/api/v1/review/sessions/{id}` | — | `{ review_id, task_id, status, decisions[], comments[] }` | 404 |
| POST | `/api/v1/review/sessions/{id}/decisions` | `{ file_path, hunk_index, decision: "approved"\|"rejected"\|"comment", comment? }` | `{ decision_id }` | 400/404 |
| POST | `/api/v1/review/sessions/{id}/comments` | `{ file_path, line_start, line_end, body }` | `{ comment_id }` | 400/404 |
| PATCH | `/api/v1/review/sessions/{id}/status` | `{ status: "approved"\|"changes_requested" }` | `{ review_id, new_status }` | 400 状态非法转换 |
| GET | `/api/v1/review/sessions/{id}/summary` | — | `{ total_files, approved, rejected, pending, coverage }` | 404 |

**状态机**：
```
PENDING → IN_REVIEW (打开审查页)
IN_REVIEW → CHANGES_REQUESTED (打回 Agent)
IN_REVIEW → APPROVED (全部 hunk 批准 + 无未解决注释)
APPROVED → MERGED (Git commit 成功)
```

### 3.3 Git 操作 (`src/orbit/api/routes/git.py`)

| 方法 | 路径 | 请求 | 响应 | 错误码 |
|------|------|------|------|--------|
| GET | `/api/v1/git/diff` | `?base=HEAD[&target=staging]` | `{ files: [{path, status, hunks}] }` | 400 |
| GET | `/api/v1/git/gpg-keys` | — | `{ keys: [{id, name, email, fingerprint}] }` | — |
| POST | `/api/v1/git/commit` | `{ message: str, files: [str], sign: bool, gpg_key_id?: str }` | `{ commit_hash, verified: bool }` | 400 msg 空 / 409 冲突 |
| GET | `/api/v1/git/merge-conflicts` | `?task_id=X` | `{ conflicts: [{file, ours, theirs, base}] }` | 404 无冲突 |
| POST | `/api/v1/git/resolve-conflict` | `{ file, resolution: "ours"\|"theirs"\|"custom", custom_content? }` | `{ resolved: bool }` | 400 |

**GPG 实现**：
```python
# 列出密钥
result = subprocess.run(["gpg", "--list-secret-keys", "--keyid-format", "LONG"],
                       capture_output=True, text=True)
# 签名提交
cmd = ["git", "commit", "-S" + gpg_key_id, "-m", message]
if files:
    cmd.extend(files)
```

### 3.4 代码导航 (`src/orbit/api/routes/codegraph.py` — 扩展现有)

| 方法 | 路径 | 请求 | 响应 |
|------|------|------|------|
| GET | `/api/v1/codegraph/definition` | `?file=X&symbol=Y&line=Z&col=W` | `{ file, line, col }` |
| GET | `/api/v1/codegraph/references` | `?file=X&symbol=Y` | `{ refs: [{file, line, col, context}] }` |
| GET | `/api/v1/codegraph/outline` | `?file=X` | `{ symbols: [{name, kind, line, children[]}] }` |

### 3.5 诊断 (`src/orbit/api/routes/lsp.py`)

| 方法 | 路径 | 请求 | 响应 |
|------|------|------|------|
| GET | `/api/v1/lsp/diagnostics` | `?task_id=X[&file=Y]` | `{ diagnostics: {file: [{line, col, severity, message, rule_id}]} }` |
| GET | `/api/v1/lsp/hover` | `?file=X&line=Y&col=Z` | `{ type_info: str \| null }` |

### 3.6 全局搜索 (`src/orbit/api/routes/search.py`)

| 方法 | 路径 | 请求 | 响应 |
|------|------|------|------|
| GET | `/api/v1/search` | `?q=X&type=file\|content&max=50` | `{ results: [{file, line?, context?}] }` |

### 3.7 测试结果 (`src/orbit/api/routes/tests.py`)

| 方法 | 路径 | 请求 | 响应 |
|------|------|------|------|
| GET | `/api/v1/tests/results` | `?task_id=X` | `{ summary: {pass, fail, skip}, cases: [{name, file, status, duration, error?}] }` |
| GET | `/api/v1/tests/coverage` | `?task_id=X` | `{ files: {path: {pct, missing_lines[]}} }` |

---

## 4. 数据模型

见 `docs/PRD+ADR_IDE功能追赶.md` §9.7。3 张表：`reviews` / `review_decisions` / `review_comments`。

**初始化**：
```python
# src/orbit/review/engine.py
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from src.orbit.core.config import settings

engine = create_async_engine(
    settings.DATABASE_URL.replace("sqlite+aiosqlite", "sqlite+aiosqlite")  # 保持一致性
    if "sqlite" in settings.DATABASE_URL
    else settings.DATABASE_URL
)
async_session = async_sessionmaker(engine, expire_on_commit=False)

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(ReviewBase.metadata.create_all)
```

**dev/prod 切换**：复用 `core/config.py:44` 的 `DATABASE_URL` 环境变量机制。dev 不设 = SQLite，生产设 = PostgreSQL。代码零改动。

---

## 5. 数据流

```
用户打开审查页
  GET /review/:taskId
    → ReviewView mounted
    → reviewStore.fetchSession(taskId)
      → GET /api/v1/review/sessions?task_id=X
      → 若不存在 → POST /api/v1/review/sessions {task_id}
    → fileStore.fetchTree(taskId)
      → GET /api/v1/files/tree?task_id=X
      → 渲染 FileTreePanel（审查状态图标初始化）

用户点击文件
  → GET /api/v1/files/diff?path=X&rev_a=checkpoint_before&rev_b=checkpoint_after
  → Monaco DiffEditor.setModel({original, modified})
  → 渲染 diff + glyph margin 按钮

用户点击 hunk 批准
  → POST /api/v1/review/sessions/{id}/decisions {file, hunk, "approved"}
  → reviewStore.updateHunkStatus(file, hunk, "approved")
  → FileTreePanel 更新该文件图标

用户触发 GPG 签名提交
  → GET /api/v1/git/gpg-keys → dropdown 选择密钥
  → POST /api/v1/git/commit {message, files, sign: true, gpg_key_id}
  → 返回 commit_hash + verified
  → reviewStore.status = "merged"

L4 mypy 诊断（后台异步）
  → lspService.run_mypy(changed_files)
  → 解析输出 → Diagnostic[]
  → GET /api/v1/lsp/diagnostics?task_id=X
  → ProblemPanel 渲染列表
```

---

## 6. 调度器/防幻觉/图谱影响

| 组件 | 影响 | 变更 |
|------|------|------|
| **调度器** | 无 | 审查阶段在 Agent 完成后，不修改状态机 |
| **防幻觉 L1-L8** | 无 | 仅 L4 mypy 输出新增管道（已有，为前端暴露 API） |
| **代码图谱** | 中 | 新增 3 个 REST API（definition/references/outline），底层复用 `CodeGraphEngine` |
| **数据库图谱** | 无 | Phase 1 不变 |
| **配置图谱** | 无 | 不变 |
| **合规引擎** | 无 | Phase 1 不变（Phase 3 加 diff 合规检查） |
| **检查点** | 低 | diff 生成读取 checkpoint before/after 快照 |

---

## 7. 前端组件树

```
ReviewView.vue                          # 新路由页面
├── ReviewToolbar.vue                   # 顶栏：task 信息 + 审查状态 + commit 按钮
│   └── GpgKeySelector.vue             # GPG key 下拉
├── FileTreePanel.vue                   # 左侧：文件树 + 审查状态图标
│   └── FileTreeNode.vue (递归)         # 单节点渲染
├── MonacoDiffEditor.vue                # 中央：Monaco DiffEditor 封装
│   └── ReviewGutter.vue               # glyph margin 审批按钮
├── ProblemPanel.vue                    # 底部 Tab：诊断列表
├── TestPanel.vue                       # 底部 Tab：测试结果
├── SearchPanel.vue                     # 弹出：全局搜索
├── OutlinePanel.vue                    # 右侧：大纲
└── CommitPanel.vue                     # 弹出：commit message + 文件勾选 + GPG

新增 Pinia Stores:
  reviewStore.ts     # 审查会话、决定、状态
  editorStore.ts     # Monaco 实例引用、当前文件
  diagnosticsStore.ts # L4 mypy 诊断数据
  gitStore.ts        # Git 状态、GPG keys、commit
```

---

## 8. 边界 Case 清单

| 场景 | 预期行为 |
|------|---------|
| Monaco Editor JS bundle 加载失败 | 降级为纯文本 `<pre>` diff，显示警告横幅 |
| Diff 超过 5000 行 | Monaco 虚拟滚动，自动折叠未变更 hunk |
| L4 mypy 子进程超时（>5s） | 显示"诊断加载中"，不阻塞 diff 渲染 |
| 用户快速切换文件（<200ms） | 取消前一个文件的 diff 请求（AbortController） |
| Git 仓库非干净状态（未 stash 的改动） | 提示"工作区不干净"，显示未提交文件列表 |
| GPG keyring 为空 | GpgKeySelector 显示"无可用密钥"，sign 复选框禁用 |
| GPG 签名失败（key 过期/revoke） | 返回 `{error: "GPG 签名失败: key expired"}`，不阻塞 commit（可退化为无签名） |
| 三路合并 all-ours/all-theirs | 确认对话框 + 操作预览 |
| 审查过程中 Agent 被重新分派修改同一文件 | 审查状态标记为 stale，提示"此审查基于过时代码" |
| coverage.json 不存在 | 覆盖率视图显示"无数据"，文件树不染色 |
| pytest --json-report 文件不存在 | 测试面板显示"测试尚未运行" |

---

## 9. 风险与缓解

| 风险 | 严重 | 缓解 |
|------|------|------|
| Monaco Editor 打包体积导致首屏加载慢 | 中 | Vite code splitting + 审查页懒加载 + Monaco 语言 worker 按需加载 |
| mypy subprocess 阻塞 FastAPI event loop | 中 | `asyncio.create_subprocess_exec` + 独立线程池 + 5s timeout |
| Git 操作竞态（多 Agent 并发 commit） | 低 | 审查会话互斥锁 + Git index lock 检测 |
| GPG 跨平台兼容（Windows Gpg4win vs Linux gpg） | 低 | 子进程执行 `gpg --version` 检测可用性，不可用则禁用 GPG 功能 |
| 审查注释表在 PostgreSQL 下性能 | 低 | 索引 `(review_id, file_path)` + `(review_id, status)` |

---

## 10. 依赖链

```
前端:
  monaco-editor (npm) → MonacoDiffEditor.vue
  vite-plugin-monaco-editor (devDep) → Vite worker bundling
  Element Plus (已有) → UI 组件
  Pinia (已有) → 状态管理
  vis-network (已有) → Phase 1 不用，Phase 3 影响分析

后端:
  sqlalchemy[asyncio] (已有) → review models
  aiosqlite (已有) → dev database
  asyncpg (已有) → prod PostgreSQL
  GitPython (新增) → git 操作
  subprocess gpg → GPG key 列表 + 签名
```

---

> 下一阶段：阶段 3（编码实现）。按 `docs/开发计划/06-IDE功能追赶计划.md` Phase 1.1→1.4 顺序推进。
