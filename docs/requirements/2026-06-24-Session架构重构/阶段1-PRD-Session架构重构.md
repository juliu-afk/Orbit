# PRD+ADR：Session 架构重构——以项目绑定会话为维度的完整工作台

## 背景

当前 Orbit 驾驶舱是全局视角：监控 Tab 展示所有任务的聚合指标、聊天 Tab 通过 NL 匹配项目、运维/资源 Tab 各自独立。用户打开界面后无法回答一个基本问题——「我现在在看哪个项目的数据？」

三个核心概念（Task / Project / "Session"）完全解耦：
- **Task** 没有 `project_id` 字段，不知道属于哪个项目
- **Project** 只存在于 SQLite 注册表，和调度/沙箱/指标无关联
- **"Session"** 仅前端 Pinia 内存中的 `string[]` 数组，刷新即丢

用户打开驾驶舱 → 看到「任务成功率 85%」→ 不知道是哪个项目的成功率。切换到聊天 Tab → 匹配到项目 → 不知道这个匹配结果和监控里的指标有什么关系。这不是信息不足的问题，是信息缺少归属维度的问题。

**一句话问题定义**：全局聚合仪表盘无法回答「这是谁的数据」，缺少 Session 作为最小工作上下文单元。

---

## PRD（产品需求文档）

### 用户故事

| 优先级 | 用户故事 |
|--------|---------|
| **P0** | 作为开发者，我打开 Orbit 后选择一个项目路径（或新建项目），系统自动创建绑定该项目的 Session，之后所有操作（聊天/任务/指标/沙箱）都在此 Session 内，我知道我的每一个操作都归属于哪个项目。 |
| **P0** | 作为开发者，我在 Session A（绑定项目 X）中提到项目 Y 的代码，系统提示我「当前会话仅有项目 X 的完整读写权限，对 Y 仅有只读权限」，并询问是否切换到项目 Y 的会话。 |
| **P1** | 作为开发者，我在历史 Session 列表中选择一个之前的会话，系统恢复当时的聊天记录和任务状态，我可以继续上次未完成的工作。 |
| **P1** | 作为运维人员，我切换到不同 Session 时，指标卡片/DAG/告警/资源面板全部切换为当前 Session 的数据，而不是全局聚合。 |

### 需求描述

#### 1. Session = 项目绑定的工作上下文

```
用户打开 Orbit
  │
  ├── 首次使用 / 无活跃 Session
  │     │
  │     ├── 选项 A：打开已有项目 → 输入/浏览文件夹路径 → 验证路径存在
  │     │     → 若项目未注册 → 自动注册到 ProjectRegistry
  │     │     → 创建 Session，绑定该项目
  │     │
  │     └── 选项 B：新建项目 → 输入项目名 + 父目录
  │           → 创建文件夹 → 可选 git init
  │           → 注册到 ProjectRegistry
  │           → 创建 Session
  │
  └── 已有历史 Session → 列表选择 → 恢复聊天记录 + 任务状态
```

**Session 数据模型**：
```python
class Session:
    session_id: str          # UUID4 hex
    project_id: str          # FK → projects.name
    title: str               # 会话标题，从首条用户消息自动截取
    status: str              # active | archived
    created_at: float
    updated_at: float
```

**Project 模型扩展**（现有 `projects` 表加字段）：
```python
# 新增字段
local_path: str              # D:/Code-Insight-Financial（绝对路径，必填，唯一）
# 已有字段保持不变
name: str                    # 项目名 = 文件夹名
repo_url: str
description: str
tags: list[str]
```

#### 2. 沙箱隔离——以项目路径为边界

| 操作 | 本 Session 绑定项目 | 其它已注册项目 | 未注册路径 |
|------|-------------------|--------------|-----------|
| 读写文件 | ✅ 完整读写 | ❌ 只读 | ❌ 只读 |
| 执行代码 | ✅ 允许 | ❌ 拒绝 | ❌ 拒绝 |
| 读取源码 | ✅ 允许 | ✅ 允许 | ✅ 允许 |
| 安装依赖 | ✅ 允许 | ❌ 拒绝 | ❌ 拒绝 |

实现方式：Docker 沙箱启动时挂载多卷——
```bash
docker run \
  -v {project.local_path}:/workspace:rw \              # 绑定项目 → 读写
  -v {other_project.path}:/readonly/{name}:ro \         # 其它已注册项目 → 只读
  -v {unregistered_path}:/readonly/ext/{hash}:ro        # 未注册路径 → 只读
  --network none \
  python:3.12-slim python /tmp/script.py
```

#### 3. 跨项目检测与提示

Chat WebSocket handler 收到消息时：
1. `ContextMatcher` 从消息提取项目关键词
2. 对比当前 Session 的 `project_id`
3. 如果匹配到**当前项目** → 正常处理
4. 如果匹配到**其他已注册项目** → 返回 `warning: "cross_project"` + 项目名
5. 如果匹配到**未注册路径** → 标记为只读外部引用，允许读取但禁止写入

前端收到 `cross_project` warning 后弹出提示：
> 当前会话绑定项目「恪现财务软件」，仅对该项目有完整读写权限。  
> 对「Orbit」仅有只读权限。  
> 是否切换到「Orbit」的会话？（当前会话自动保存）

#### 4. 前端信息架构——Session 为顶栏

```
┌──────────────────────────────────────────────────────────┐
│ 📁 恪现财务软件  [修复导入校验 ▾]  [+ 新建会话]          │  ← 项目名 + Session 下拉
├──────────────────────────────────────────────────────────┤
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────┐ │
│  │ 成功率   │ │ Token    │ │ 拦截     │ │ 状态: 运行中  │ │  ← 当前 Session 指标
│  └──────────┘ └──────────┘ └──────────┘ └──────────────┘ │
├──────────────────────────┬───────────────────────────────┤
│                          │                               │
│  DAG 任务流 + 防幻觉     │  聊天 / Agent 交互             │  ← 左右分栏
│                          │                               │
├──────────────────────────┴───────────────────────────────┤
│  Token 消耗趋势  │  告警  │  组件健康                     │  ← 底部信息（Session 范围）
└──────────────────────────────────────────────────────────┘
```

- **顶栏**：项目名（来自文件夹名）始终可见；Session 下拉切换历史会话；[+ 新建会话] 按钮
- **4 个 Tab 合并**为单页面布局——监控/聊天/运维/资源不是独立频道，而是一个 Session 的 4 个视角
- **指标卡片**（成功率/Token/拦截/状态）仅反映当前 Session 关联的任务
- **ChatPanel** 消息历史持久化到 Session，切换会话时恢复

### 数据契约

#### 新增 API 端点

```
POST   /api/v1/sessions                   # 创建 Session
  请求: { project_name: str, title?: str }
  响应: { code: 0, data: { session_id, project_name, title, created_at } }

GET    /api/v1/sessions                   # 列出所有 Session
  响应: { code: 0, data: [{ session_id, project_name, title, status, created_at, updated_at }] }

GET    /api/v1/sessions/{session_id}       # 获取 Session 详情（含聊天记录）
  响应: { code: 0, data: { session, messages: [...] } }

PATCH  /api/v1/sessions/{session_id}       # 更新 Session（切换状态/改标题）
  请求: { status?: "active"|"archived", title?: str }
  响应: { code: 0, data: { ... } }

POST   /api/v1/projects                    # 注册或更新项目（扩展已有 registry API）
  请求: { name: str, local_path: str, repo_url?: str, description?: str, tags?: [str] }
  响应: { code: 0, data: { ...ProjectRecord } }

GET    /api/v1/projects                    # 列出所有已注册项目
  响应: { code: 0, data: [{ name, local_path, ... }] }
```

#### 修改现有数据模型

**Task → 加 session 归属**：
```python
# TaskCreateRequest 加字段
session_id: str  # 必填——任务必须归属一个 Session
# TaskStatusResponse 加字段
session_id: str
project_name: str
```

**Chat WebSocket 响应 → 加跨项目 warning**：
```python
# MatchResult.to_dict() 新增字段
cross_project_warning: str | None  # "恪现财务软件" or None
```

#### Chat WebSocket 新协议

```
客户端 → 服务端:
{
  "type": "chat",
  "text": "用户输入",
  "session_id": "abc123",        # 新增：当前 Session ID
  "project_name": "恪现财务软件"   # 新增：当前绑定的项目
}

服务端 → 客户端（正常）:
{
  "code": 0,
  "data": {
    "query": "...",
    "keywords": [...],
    "candidates": [...],
    "source": "keyword_match",
    "requires_confirmation": true,
    "cross_project_warning": null
  }
}

服务端 → 客户端（跨项目检测）:
{
  "code": 0,
  "data": {
    "query": "...",
    "keywords": [...],
    "candidates": [{ project: "Orbit", ... }],
    "source": "keyword_match",
    "requires_confirmation": true,
    "cross_project_warning": "Orbit"   # ← 提示前端弹窗
  }
}
```

### 异常定义

| 异常 | 处理 |
|------|------|
| 用户输入的路径不存在 | 返回 400：`路径 {path} 不存在，请检查后重试` |
| 用户输入的路径无权访问 | 返回 403：`路径 {path} 无读取权限` |
| Session 绑定的项目已被删除/路径不存在 | Session 标记为 `archived`，提示用户「项目路径已失效，Session 已归档」 |
| 聊天中提到其他项目（跨项目引用） | 返回 `cross_project_warning`，前端弹提示，不自动切换 |
| 沙箱执行时访问越界路径（写入其他项目或未注册路径） | 沙箱层面 Docker volume 仅挂载 `:ro`，写入操作直接报 `Read-only file system` |
| 切换 Session 时当前 Session 有未完成任务 | 提示「当前有 N 个任务未完成，切换后任务将继续在后台运行。是否继续？」 |

### 成功标准 → 验收

| 成功标准 | 验收条件 |
|---------|---------|
| **SC1:** 用户打开 Orbit 即知道当前在哪个项目 | **AC1:** 顶栏始终显示项目名（文件夹名），无任何情况隐藏 |
| **SC2:** 新建 Session 流程 ≤3 步 | **AC2:** 选择路径 → 确认 → Session 创建完成（3 次点击），3s 内进入工作界面 |
| **SC3:** Session 切换后指标正确隔离 | **AC3:** Session A 有 3 个活跃任务，切换到 Session B 后指标卡片显示 Session B 的数据（不是聚合），抽样 10 次全部正确 |
| **SC4:** 沙箱隔离生效 | **AC4:** 在 Session A 的沙箱中尝试写入项目 B 的文件 → 报 `Read-only file system` 错误且无文件实际被修改 |
| **SC5:** 跨项目提示 | **AC5:** 在 Session A（绑定项目 X）中输入项目 Y 的代码问题 → 前端弹出跨项目提示，无法直接操作项目 Y |
| **SC6:** 聊天记录持久化 | **AC6:** 关闭页面再打开，选择同一 Session → 聊天记录完整恢复 |

### 范围（Do / Don't）

**Do：**
- Session 数据模型 + CRUD API
- Project 模型扩展（加 `local_path`）
- 前端 Session 选择器 + 新建 Session 流程（打开已有项目 / 新建项目）
- 沙箱以项目路径为挂载点，绑定项目 `rw`，其它 `ro`
- Task 模型加 `session_id` + `project_name`
- 聊天 WebSocket 加跨项目检测 + 前端提示弹窗
- 指标/告警/健康面板按 Session 过滤
- 聊天记录持久化到后端
- 全局 4 Tab → 单页面 Session 视图

**Don't：**
- 不实现多租户/团队 Session 共享（Phase 2）
- 不实现 Session 导出/导入
- 不修改 ProcessSandbox（Windows AppContainer）的隔离策略（MVP 仅 Docker）
- 不实现项目文件夹的自动发现（用户手动告知路径）

### 待定决策

| 问题 | 决议 |
|------|------|
| Session 可否同时绑定多个项目？ | **不可。** 1 Session = 1 Project。多项目需求 → 开多个 Session |
| 聊天记录保留多久？ | 持久保留，Session archived 后仍可查看，不可新增消息 |
| 历史 Session 列表排序？ | 按 `updated_at` 降序，最近使用的排最前 |
| 项目名是否必须等于文件夹名？ | 默认等于文件夹名，用户可手动修改（不影响路径绑定） |

---

## ADR（架构决策记录）

### 决策 1：Session 作为第一公民，替代全局仪表盘

| 维度 | 决策 |
|------|------|
| **决策** | 以 Session（会话）为最小工作上下文单元，1 Session = 1 Project 绑定，所有交互（聊天/任务/指标/沙箱）都在 Session 范围内 |
| **备选方案** | A. 保持全局仪表盘，仅在聊天 Tab 加项目选择器 B. 全局仪表盘 + 按项目过滤的指标 |
| **理由** | 方案 A 无法解决「监控指标不知道归属谁」的问题。方案 B 增加了一层过滤逻辑但没有从根本上改变「全局优先」的心智模型。Session 优先方案把上下文选择提到最前面——用户打开 Orbit 的第一件事就是选择/确认上下文，之后所有信息自动归于该上下文，不再猜测 |
| **权衡** | 失去了「一眼看所有项目」的能力 → 但这在单用户开发场景不是需求，反而增加了噪音 |

### 决策 2：Project 加 `local_path`，沙箱以路径为边界

| 维度 | 决策 |
|------|------|
| **决策** | `projects` 表新增 `local_path TEXT NOT NULL UNIQUE` 字段，沙箱启动时以该路径为主挂载点（`rw`），其他已注册项目路径以 `:ro` 挂载 |
| **备选方案** | A. 沙箱仅挂载当前项目，不暴露其他项目路径 B. 沙箱挂载整个文件系统，通过文件级权限控制 |
| **理由** | 方案 A 过于严格——用户引用其他项目的代码是常见且合理的需求（如「参考 Orbit 的 ContextMatcher 实现」），应允许只读。方案 B 不安全且难以审计。当前方案在安全性和可用性之间取平衡 |
| **权衡** | 增加了 Docker run 命令的复杂性（多 `-v` 参数），但通过 sandbox executor 统一封装后可控 |

### 决策 3：跨项目检测在服务端做，不在前端

| 维度 | 决策 |
|------|------|
| **决策** | ContextMatcher 接收当前 Session 的 `project_name`，检测到匹配其他项目时返回 `cross_project_warning`，由前端弹窗提示。不阻止匹配结果返回，只标记警告 |
| **备选方案** | A. 前端比对候选列表和当前项目 B. 服务端直接拒绝跨项目匹配，不返回任何候选 |
| **理由** | 方案 A 不可靠——前端不知道所有已注册项目。方案 B 过于强势——用户可能确实需要查看其他项目信息，应该由用户决定。当前方案「检测 + 提示 + 用户选择」尊重用户决策权 |
| **权衡** | ContextMatcher 逻辑复杂度增加约 30 行，可接受 |

### 决策 4：前端 4 Tab 合并为单页面 Session 视图

| 维度 | 决策 |
|------|------|
| **决策** | 移除 `el-tabs`（监控/聊天/运维/资源），改为单一 Session 页面：顶栏（Session 选择器 + 指标卡）→ 中部左右分栏（DAG + 聊天）→ 底部信息栏（Token 趋势 + 告警 + 健康） |
| **备选方案** | A. 保留 4 Tab，仅在各 Tab 加 Session 选择器 B. 监控/运维/资源合并为一个「概览」Tab，聊天独立 |
| **理由** | 4 Tab 的设计来自「操作分类」思维（监控是一类操作、聊天是另一类），但 Session 模式下的正确分类是「这是我当前工作的所有相关信息」。用户不需要在 Tab 之间切换来理解自己的会话状态 |
| **权衡** | 单页面信息密度增加，需要仔细设计视觉层级——但信息都在同一上下文内，认知负担反而降低 |

### 技术栈版本

- 后端：FastAPI + SQLite (3 张新表/扩展)，Python 3.12+
- 前端：Vue 3.4 + Pinia + Element Plus + ECharts（已有，不新增依赖）
- 沙箱：Docker（已有，加多卷挂载参数）

### 架构位置

| 模块 | 文件 | 操作 |
|------|------|------|
| Session 模型 | `src/orbit/sessions/models.py` | **新增** |
| Session 注册表 | `src/orbit/sessions/registry.py` | **新增** |
| Session API | `src/orbit/api/routes/sessions.py` | **新增** |
| Project 模型 | `src/orbit/projects/models.py` | **修改**——加 `local_path` |
| Project 注册表 | `src/orbit/projects/registry.py` | **修改**——加 `local_path` 字段、`list_all()` 返回路径 |
| Project API | `src/orbit/api/routes/projects.py` | **新增**——CRUD 端点 |
| Task Schema | `src/orbit/api/schemas/task.py` | **修改**——加 `session_id`、`project_name` |
| Task Route | `src/orbit/api/routes/tasks.py` | **修改**——创建任务时关联 Session |
| Chat WebSocket | `src/orbit/api/routes/chat.py` | **修改**——接收 `session_id`/`project_name`，返回 `cross_project_warning` |
| ContextMatcher | `src/orbit/context/matcher.py` | **修改**——加跨项目检测逻辑 |
| Sandbox Executor | `src/orbit/sandbox/executor.py` | **修改**——多卷挂载（rw 当前项目 + ro 其他） |
| 前端 DashboardView | `frontend/src/views/DashboardView.vue` | **修改**——4 Tab → 单页面 Session 视图 |
| 前端 Session Store | `frontend/src/stores/session.ts` | **新增** |
| 前端 SessionSelector 组件 | `frontend/src/components/layout/SessionSelector.vue` | **新增** |
| 前端 NewSessionDialog 组件 | `frontend/src/components/layout/NewSessionDialog.vue` | **新增** |
| 前端 CrossProjectWarning | `frontend/src/components/chat/CrossProjectWarning.vue` | **新增** |
| 前端 Chat Store | `frontend/src/stores/chat.ts` | **修改**——消息通过后端持久化，加 `cross_project_warning` 处理 |
| 前端 AgentOps Store | `frontend/src/stores/agentops.ts` | **修改**——指标按 session_id 过滤 |
| 前端 GlobalStatusBar | `frontend/src/components/layout/GlobalStatusBar.vue` | **修改**——移除 taskId，改为项目名 + Session 标题 |

### 组件树（改后）

```
App.vue
└── DashboardView.vue
    ├── SessionBar.vue (新增)          # 顶栏: 项目名 + Session下拉 + 新建按钮
    │   ├── ProjectBadge               # 📁 项目文件夹名
    │   ├── SessionDropdown            # [Session标题 ▾] 历史Session切换
    │   └── NewSessionButton           # [+ 新建会话]
    ├── MetricsRow (改)                # 指标卡片——按session_id过滤
    │   ├── MetricsCard ×4
    │   └── CircuitBreakerLight ×3
    ├── ContentRow (改)                # 主内容区——左右分栏
    │   ├── LeftPanel                  # DAG + 防幻觉图 + Token趋势 + 告警
    │   │   ├── DagCanvas
    │   │   ├── HallucinationBarChart
    │   │   └── TokenChart
    │   └── RightPanel                # 聊天
    │       └── ChatPanel
    ├── BottomBar                      # 底部状态
    │   ├── AlertList
    │   └── HealthPanel
    └── NewSessionDialog.vue (新增)    # 新建Session弹窗
        ├── Tab: 打开已有项目（路径输入）
        └── Tab: 新建项目（名称 + 父目录）
```

### 风险与缓解

| 风险 | 缓解 |
|------|------|
| Docker 多卷挂载性能下降（挂载 10+ 项目的只读卷） | 仅挂载当前活跃项目 + 最近 5 个项目的只读卷，非全部已注册项目 |
| Session 切换时前端状态不一致（旧 Session 的 WS 消息残留） | 切换 Session 时先 unsubscribe 旧 task_id，再 subscribe 新 Session 的 task |
| 现有 E2E/集成测试大面积失败（改了无数接口） | 分两步交付：① 后端 Session + Project 扩展（向后兼容现有 API）→ ② 前端重布局。每步独立 PR，各自有测试覆盖 |
| 用户忘记当前 Session 绑定的项目，误以为是全局 | 顶栏始终显示项目名 + Session 标题，信息密度低但持续可见 |

### 需求错位

若未来需要「一个 Session 同时处理多个关联项目」→ Session-Project 关系从 1:1 改为 1:N，需重新设计沙箱挂载策略（多 rw 卷）和跨项目警告逻辑（从「拒绝」变「允许」）。

### 技术约束

- 不新增前端 npm 依赖
- Session/Project 元数据仍然用 SQLite（与现有 ProjectRegistry 一致），不引入 PostgreSQL
- Chat 消息持久化用 SQLite `chat_messages` 表，不做全文索引（Phase 2 考虑 pgvector 语义检索）
- Docker 必须可用（沙箱隔离依赖多卷挂载），不可用时降级为 ProcessSandbox + 单路径隔离

### 依赖链

- 依赖已有：ProjectRegistry（扩展）、Sandbox（扩展）、ContextMatcher（扩展）、Chat WebSocket（扩展）
- 被依赖：Task Scheduler（需 session_id）、AgentOps 指标（需按 session 聚合）
- 并行可做：前端 Session UI 和后端 Session API 可并行开发

---

## 测试策略

| 层 | 工具 | 用例数 | 覆盖 |
|----|------|--------|------|
| **单元** | pytest | 12 | Session CRUD / Project 扩展字段 / ContextMatcher 跨项目检测 / Sandbox 多卷挂载参数生成 / 权限矩阵（rw vs ro） |
| **集成** | pytest | 8 | Session API 端点 CRUD / Project API 端点 / Chat WS 跨项目警告 / Task 创建关联 session_id / 沙箱隔离验证（rw 写成功 + ro 写失败） |
| **E2E** | Playwright | 6 | 新建 Session（打开已有项目）流程 / 新建 Session（新建项目）流程 / 跨项目提示弹窗 / Session 切换后指标变化 / Session 切换后聊天记录恢复 / 4 Tab 消失 → 单页面布局 |
| **Store** | vitest | 4 | session store 初始化 / 切换 Session / agentOps 按 session 过滤 / chat 消息持久化 |
| **组件** | vitest + @vue/test-utils | 5 | SessionSelector 渲染 / NewSessionDialog 路径验证 / ProjectBadge 显示文件夹名 / CrossProjectWarning 弹窗 / MetricsCard session 隔离 |
| **合计** | | **35** | |

---

## 与现有 Step 的映射

| Step | 原有内容 | 本次改动 |
|------|---------|---------|
| Step 0.3 需求澄清 | 项目上下文匹配 | ContextMatcher 加跨项目检测 + `cross_project_warning` 返回 |
| Step 1.1 API 契约 | RESTful API 端点 | 新增 Session CRUD + Project CRUD 端点；Task schema 加 session 字段 |
| Step 4.1/4.2 防幻觉 | L1-L8 层 | 不变——防幻觉层只关心代码正确性，不涉及项目归属 |
| Step 5.1 调度器 | 任务状态机 + DAG | Task 创建时接收 `session_id`，DAG 节点不变 |
| Step 6.1 驾驶舱 | 4 Tab 全局仪表盘 | 重构为 Session 单页面视图，移除 Tab |
| Step 7.x 沙箱 | Docker 隔离执行 | 挂载策略从单文件 `/tmp/script.py` 改为多卷项目路径挂载 |
| AgentOps 体系 | 全局指标/告警/健康 | 指标按 session_id 聚合，告警携带 project_name |
