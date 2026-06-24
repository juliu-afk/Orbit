# 技术方案 —— Session 架构重构

基于 [阶段1-PRD-Session架构重构.md](阶段1-PRD-Session架构重构.md)（验收标准 6 条），本方案覆盖 6 条，无偏离。

---

## 一、需求回顾

| # | 验收标准 | 对应技术实现 |
|---|---------|------------|
| AC1 | 顶栏始终显示项目名 | SessionBar 组件从 sessionStore 读 `projectName`，无任何分支隐藏 |
| AC2 | 新建 Session ≤3 步，3s 内进入 | NewSessionDialog → POST /sessions → Dashboard 刷新，路由层无阻塞 |
| AC3 | Session 切换后指标隔离 | agentOps 查询加 `?session_id=` 参数；WS 按 session 订阅 |
| AC4 | 沙箱写入越界报 Read-only | Sandbox._build_mounts() 生成 ro 挂载参数；Docker 层硬拦截 |
| AC5 | 跨项目提示弹窗 | chat WS 返回 `cross_project_warning` → chatStore → CrossProjectWarning 弹窗 |
| AC6 | 聊天记录持久化恢复 | GET /sessions/{id} 返回 messages[] → chatStore 恢复 |

---

## 二、数据库设计

### 2.1 `projects` 表扩展

```sql
-- 新增字段（已有表加列，用 ALTER TABLE ADD COLUMN + 默认值保证存量数据兼容）
ALTER TABLE projects ADD COLUMN local_path TEXT DEFAULT '' NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS idx_projects_local_path ON projects(local_path) WHERE local_path != '';
```

存量数据（"Orbit" 预注册）`local_path` 为空字符串，前端视为「路径未设置——需修复」。

### 2.2 `sessions` 表（新建）

```sql
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,                  -- UUID4 hex, 32 chars
    project_id TEXT NOT NULL,             -- FK → projects.name
    title TEXT DEFAULT '',                -- 会话标题，首条消息截取前 30 字符
    status TEXT DEFAULT 'active',         -- active | archived
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    FOREIGN KEY (project_id) REFERENCES projects(name) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_sessions_project ON sessions(project_id);
CREATE INDEX IF NOT EXISTS idx_sessions_status ON sessions(status);
CREATE INDEX IF NOT EXISTS idx_sessions_updated ON sessions(updated_at DESC);
```

### 2.3 `chat_messages` 表（新建）

```sql
CREATE TABLE IF NOT EXISTS chat_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,             -- FK → sessions.id
    role TEXT NOT NULL,                   -- user | system | agent
    content TEXT NOT NULL,
    candidates TEXT DEFAULT '[]',         -- JSON: MatchCandidate[]
    cross_project_warning TEXT DEFAULT NULL,
    created_at REAL NOT NULL,
    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_chat_session ON chat_messages(session_id);
CREATE INDEX IF NOT EXISTS idx_chat_created ON chat_messages(session_id, created_at);
```

### 2.4 ER 关系

```
projects (1) ──< (N) sessions ──< (N) chat_messages
                    │
                    └──< (N) tasks (session_id FK)
```

---

## 三、后端模块设计

### 3.1 `src/orbit/sessions/models.py`（新增）

```python
from dataclasses import dataclass, field
from typing import Any

@dataclass
class SessionRecord:
    session_id: str           # UUID4 hex
    project_name: str         # denormalized from projects.name
    title: str = ""
    status: str = "active"    # active | archived
    created_at: float = 0.0
    updated_at: float = 0.0

    def to_dict(self) -> dict[str, Any]: ...

@dataclass
class ChatMessageRecord:
    id: int | None = None
    session_id: str = ""
    role: str = ""            # user | system | agent
    content: str = ""
    candidates: list[dict] = field(default_factory=list)
    cross_project_warning: str | None = None
    created_at: float = 0.0
```

### 3.2 `src/orbit/sessions/registry.py`（新增）

```python
class SessionRegistry:
    """Session + ChatMessage 持久化注册表。SQLite 存储。"""

    def __init__(self, db_path: str = "data/orbit.db"):
        # 与 ProjectRegistry 共用同一 SQLite 文件，方便 JOIN 查询

    # ── Session CRUD ──
    def create(self, project_name: str, title: str = "") -> SessionRecord:
        """新 Session: INSERT + 返回带 UUID 的 SessionRecord"""

    def get(self, session_id: str) -> SessionRecord | None: ...
    def list_all(self, status: str | None = None) -> list[SessionRecord]:
        """按 updated_at DESC，可选过滤 status"""
    def list_by_project(self, project_name: str) -> list[SessionRecord]: ...
    def update(self, session_id: str, **kwargs) -> SessionRecord | None:
        """Update title / status + touch updated_at"""
    def touch(self, session_id: str) -> None:
        """仅刷新 updated_at（收到 WS 消息时调用）"""

    # ── ChatMessage CRUD ──
    def add_message(self, session_id: str, role: str, content: str,
                    candidates: list[dict] | None = None,
                    cross_project_warning: str | None = None) -> ChatMessageRecord: ...
    def get_messages(self, session_id: str, limit: int = 50) -> list[ChatMessageRecord]: ...
```

### 3.3 `src/orbit/projects/models.py`（修改）

```python
@dataclass
class ProjectRecord:
    name: str
    local_path: str = ""      # ← 新增：项目文件夹绝对路径
    repo_url: str = ""
    description: str = ""
    # ... 其余字段不变
```

### 3.4 `src/orbit/projects/registry.py`（修改）

```python
class ProjectRegistry:
    # _ensure_table() 加 ALTER TABLE 逻辑（存量兼容）:
    #   ALTER TABLE projects ADD COLUMN local_path TEXT DEFAULT '';

    def register(self, ..., local_path: str = "") -> ProjectRecord:
        # INSERT 语句加 local_path 字段

    def get_by_path(self, local_path: str) -> ProjectRecord | None:
        """按路径查项目——验证路径是否已注册。"""

    def find_by_path_prefix(self, path: str) -> list[ProjectRecord]:
        """查找 path 下的子目录是否已注册（用于检测未注册路径的归属）。"""

    def _row_to_record(row) -> ProjectRecord:
        # 加 local_path 映射，兼容旧数据无此字段
```

### 3.5 `src/orbit/api/schemas/task.py`（修改）

```python
class TaskCreateRequest(BaseModel):
    prd: constr(min_length=10, max_length=5000)
    language: Literal["python", "javascript", "java", "go"] = "python"
    session_id: str = Field(..., min_length=32, max_length=32,  # ← 新增必填
                            description="归属 Session ID (UUID4 hex)")

class TaskStatusResponse(BaseModel):
    task_id: str
    state: TaskState
    progress: float
    result: str | None
    session_id: str = ""      # ← 新增
    project_name: str = ""    # ← 新增
    created_at: datetime
    updated_at: datetime
```

### 3.6 `src/orbit/api/routes/tasks.py`（修改）

```python
@router.post("")
async def create_task(req: TaskCreateRequest) -> TaskStatusResponse:
    # 修改点:
    # 1. 从 req.session_id 查 SessionRegistry → 验证 session 存在
    # 2. session 不存在 → 404 "会话 {session_id} 不存在"
    # 3. session 存在 → 取 project_name 填入响应
    # 4. TaskStatusResponse 携带 session_id + project_name
```

### 3.7 `src/orbit/api/routes/sessions.py`（新增）

```python
router = APIRouter(prefix="/sessions", tags=["sessions"])

@router.post("", summary="创建会话")
async def create_session(req: SessionCreateRequest) -> dict:
    """
    请求: { project_name: str, title?: str }
    逻辑:
      1. 验证 project_name 在 ProjectRegistry 中存在
      2. 验证对应 ProjectRecord.local_path 不为空
      3. SessionRegistry.create(project_name, title)
      4. 返回 SessionRecord.to_dict()
    错误: 404 project not found / 400 local_path 未设置
    """

@router.get("", summary="列出所有会话")
async def list_sessions(status: str | None = None) -> dict:
    """按 updated_at DESC。可选过滤 active/archived。"""

@router.get("/{session_id}", summary="获取会话详情")
async def get_session(session_id: str) -> dict:
    """返回 session + messages[]（最近 50 条）。"""

@router.patch("/{session_id}", summary="更新会话")
async def update_session(session_id: str, req: SessionUpdateRequest) -> dict:
    """更新 title / status。archived 后不可改回 active（终态）。"""
```

### 3.8 `src/orbit/api/routes/projects.py`（新增）

```python
router = APIRouter(prefix="/projects", tags=["projects"])

@router.post("", summary="注册或更新项目")
async def register_project(req: ProjectCreateRequest) -> dict:
    """
    请求: { name: str, local_path: str, repo_url?: str, ... }
    逻辑:
      1. 验证 local_path 存在 + 可读 (os.path.isdir + os.access)
      2. registry.register(...)
      3. 返回 ProjectRecord.to_dict()
    错误: 400 路径不存在 / 403 无权限
    """

@router.get("", summary="列出所有项目")
async def list_projects() -> dict:
    """返回所有活跃项目，含 local_path。"""

@router.get("/{name}", summary="查询单个项目")
async def get_project(name: str) -> dict:
    """按名称返回项目详情。404 if not found。"""
```

### 3.9 `src/orbit/api/routes/chat.py`（修改）

```python
# 关键改动: 接收 session_id + project_name, 持久化消息, 跨项目检测

@router.websocket("")
async def chat_endpoint(ws: WebSocket) -> None:
    await ws.accept()
    try:
        while True:
            raw = await ws.receive_text()
            payload = json.loads(raw)

            text = payload.get("text", "")
            session_id = payload.get("session_id", "")  # ← 新增
            project_name = payload.get("project_name", "")

            if not text.strip():
                await ws.send_json({"error": "输入为空", "code": 1, "data": None})
                continue

            # 上下文匹配
            result = _matcher.match(text, session_projects=None)

            # ── 新增: 跨项目检测 ──
            cross_warning = None
            if project_name:
                for c in result.candidates:
                    if c.project_name != project_name:
                        # 检测到匹配到其他项目
                        cross_warning = c.project_name
                        break

            # ── 新增: 消息持久化 ──
            if session_id:
                _session_registry.add_message(
                    session_id=session_id,
                    role="user",
                    content=text,
                    candidates=result.to_dict().get("candidates"),
                    cross_project_warning=cross_warning,
                )
                _session_registry.touch(session_id)

            response = {
                "code": 0,
                "data": {
                    **result.to_dict(),
                    "cross_project_warning": cross_warning,  # ← 新增
                },
                "message": "ok",
            }
            await ws.send_json(response)

    except WebSocketDisconnect:
        pass
```

### 3.10 `src/orbit/context/matcher.py`（修改）

```python
class ContextMatcher:
    def match(self, query: str, session_projects: list[str] | None = None,
              current_project: str = "") -> MatchResult:
        """
        新增参数 current_project——当前 Session 绑定的项目名。
        跨项目检测在 chat.py 调用层做（matcher 只负责匹配，不关心权限）。
        matcher 本身逻辑不变——匹配是纯粹的相关性计算。
        """
```

### 3.11 `src/orbit/sandbox/executor.py`（修改）

```python
class Sandbox:
    def __init__(self, ..., project_path: str = "", readonly_paths: list[str] | None = None):
        """
        新增参数:
          project_path: 当前项目路径 → 挂载为 /workspace:rw
          readonly_paths: 其他项目路径列表 → 挂载为 /readonly/N:ro
        """
        self.project_path = project_path
        self.readonly_paths = readonly_paths or []

    def _build_mounts(self, host_script: Path) -> list[str]:
        """生成 docker run -v 参数列表。"""
        mounts = [f"{host_script}:/tmp/{host_script.name}:ro"]

        # 绑定项目 → 读写
        if self.project_path:
            mounts.append(f"{self.project_path}:/workspace:rw")

        # 其他已注册项目 → 只读
        for i, rp in enumerate(self.readonly_paths[:5]):  # 最多 5 个
            name = Path(rp).name or f"ext_{i}"
            mounts.append(f"{rp}:/readonly/{name}:ro")

        return mounts

    async def run(self, code: str, language: str = "python",
                  external_paths: list[str] | None = None) -> str:
        """
        新增参数 external_paths: LLM 代码中引用的外部路径（未注册项目）。
        这些路径也加到 readonly 挂载，和已注册项目一样只读。
        """

    async def _run_in_container(self, host_script: Path,
                                external_paths: list[str] | None = None) -> str:
        cmd = ["docker", "run", "--rm", "--network", "none"]
        # 脚本挂载
        cmd.extend(["-v", f"{host_script}:/tmp/{host_script.name}:ro"])
        # 项目路径挂载
        if self.project_path:
            cmd.extend(["-v", f"{self.project_path}:/workspace:rw"])
        # 只读路径挂载（已注册 + 外部引用，最多 5+5=10 个）
        all_ro = (self.readonly_paths[:5] +
                  (external_paths or [])[:5])
        for i, rp in enumerate(all_ro):
            name = Path(rp).name or f"ext_{i}"
            cmd.extend(["-v", f"{rp}:/readonly/{name}:ro"])
        # ...
```

### 3.12 `src/orbit/api/main.py`（修改）

```python
# 在 create_app() 中新增两行:
app.include_router(sessions.router, prefix=settings.API_V1_STR)  # 新增
app.include_router(projects.router, prefix=settings.API_V1_STR)  # 新增
```

---

## 四、前端设计

### 4.1 新 Store：`session.ts`

```typescript
// frontend/src/stores/session.ts
export interface SessionSummary {
  session_id: string
  project_name: string
  title: string
  status: 'active' | 'archived'
  created_at: number
  updated_at: number
}

export interface ChatMessage {
  id: number
  role: 'user' | 'system' | 'agent'
  content: string
  candidates: Candidate[]
  cross_project_warning: string | null
  created_at: number
}

export const useSessionStore = defineStore('session', () => {
  const currentSessionId = ref<string | null>(null)
  const currentProjectName = ref<string>('')
  const currentTitle = ref<string>('')
  const sessions = ref<SessionSummary[]>([])
  const messages = ref<ChatMessage[]>([])
  const loading = ref(false)

  // ── Actions ──
  async function fetchSessions(): Promise<void>
  async function createSession(projectName: string, title?: string): Promise<string>
  async function switchSession(sessionId: string): Promise<void>
  //   → GET /sessions/{id} → 设置 current* + 填充 messages[]
  async function archiveSession(sessionId: string): Promise<void>

  // ── 指标过滤 ──
  function getMetricsFilter(): { session_id: string } | {}
  //   → currentSessionId 存在 → { session_id: currentSessionId }
  //   → 无 → {}（兜底全局）

  function reset(): void
})
```

### 4.2 修改 Store：`chat.ts`

```typescript
// 改动点:
// 1. 移除 sessionProjects: ref<string[]>([]) —— session 管理职责转移到 sessionStore
// 2. 移除 messages: ref<ChatMessage[]>([]) —— 消息持久化在 sessionStore
// 3. send() 发送时附加 session_id + project_name
// 4. handleResponse() 处理 cross_project_warning → 触发弹窗

function send(text: string) {
  if (!wsInstance || wsInstance.readyState !== WebSocket.OPEN) return
  wsInstance.send(JSON.stringify({
    type: 'chat',
    text: text.trim(),
    session_id: sessionStore.currentSessionId,    // ← 新增
    project_name: sessionStore.currentProjectName,  // ← 新增
  }))
}

const crossProjectWarning = ref<string | null>(null)

function handleResponse(data: MatchData & { cross_project_warning?: string }) {
  // ...原有逻辑
  if (data.cross_project_warning) {
    crossProjectWarning.value = data.cross_project_warning
  }
}

function dismissWarning() { crossProjectWarning.value = null }
```

### 4.3 修改 Store：`agentops.ts`

```typescript
// 改动点: fetchAll() 加 `?session_id=` 查询参数
// 指标/告警/健康 API 后端加 session_id 过滤（可选参数，不传=全局）

async function fetchMetrics() {
  const sessionId = sessionStore.currentSessionId
  const url = sessionId
    ? `${METRICS_URL}?session_id=${sessionId}`
    : METRICS_URL
  // ...
}
// fetchAlerts() / fetchHealth() 同理
```

### 4.4 修改 Store：`dashboard.ts`

```typescript
// 移除 currentTaskId + lastUpdateTime
// 改为 thin wrapper——任务状态由 taskStore 管理，不在此 Store
export const useDashboardStore = defineStore('dashboard', () => {
  const wsStatus = ref<'connected' | 'connecting' | 'disconnected'>('disconnected')
  function setWsStatus(s: 'connected' | 'connecting' | 'disconnected') { wsStatus.value = s }
  return { wsStatus, setWsStatus }
})
```

### 4.5 新增组件：`SessionBar.vue`

```
Props: 无（数据从 sessionStore 读取）
子组件:
  ├── ProjectBadge     : 📁 + projectName
  ├── SessionDropdown  : el-dropdown, 列出 sessions[], 当前高亮
  └── NewSessionButton : el-button, 点击 → emit('new-session')
Events:
  @switch-session(sessionId: string)
  @new-session()
```

### 4.6 新增组件：`NewSessionDialog.vue`

```
Props: visible: boolean
内容:
  el-dialog 含两个 el-radio-button:
    Tab A "打开已有项目":
      el-input (placeholder: "项目文件夹路径，如 D:/Code-Insight-Financial")
      el-button "浏览..." (调用 showDirectoryPicker 或手动输入)
    Tab B "新建项目":
      el-input (placeholder: "项目名称")
      el-input (placeholder: "父目录路径")
  底部: [取消] [确认]
Events:
  @confirm(type: 'open'|'create', payload: { path?: string, name?: string, parentDir?: string })
  @cancel()
校验逻辑（前端即时校验，减少无效 API 请求）:
  - 路径非空
  - 路径不含非法字符（< > " | ? *）
  - 新建项目时项目名非空且父目录存在
```

### 4.7 新增组件：`CrossProjectWarning.vue`

```
Props: warningProjectName: string
内容:
  el-alert type="warning" show-icon :closable="false"
    标题: 跨项目引用
    正文: 当前会话绑定项目「{sessionStore.currentProjectName}」，仅对该项目有完整读写权限。
          对「{warningProjectName}」仅有只读权限。
          是否切换到「{warningProjectName}」的会话？
    操作按钮: [切换会话] [取消]
Events:
  @switch-to(projectName: string)  → sessionStore 查找/创建对应 Session → switchSession
  @dismiss()
```

### 4.8 修改组件：`GlobalStatusBar.vue`

```
改前: 连接状态 dot + taskId + lastUpdate
改后:
  连接状态 dot + projectName（来自 sessionStore）+ sessionTitle（来自 sessionStore）
  移除 taskId 和 lastUpdate
```

### 4.9 修改组件：`DashboardView.vue`

```
改前:
  <el-tabs v-model="activeTab">
    <el-tab-pane label="监控" name="monitor"> ... </el-tab-pane>
    <el-tab-pane label="聊天" name="chat"> ... </el-tab-pane>
    <el-tab-pane label="运维" name="ops"> ... </el-tab-pane>
    <el-tab-pane label="资源" name="resources"> ... </el-tab-pane>
  </el-tabs>

改后:
  <SessionBar @new-session="showNewDialog = true" />      ← 顶栏
  <div v-if="!sessionStore.currentSessionId" class="welcome">  ← 无 Session 引导页
    <el-empty description="选择一个项目开始工作">
      <el-button @click="showNewDialog = true">打开或新建项目</el-button>
    </el-empty>
  </div>
  <template v-else>                                        ← Session 工作台
    <MetricsRow ... />
    <ContentRow>
      <LeftPanel>  DAG + 防幻觉 + Token 趋势 + 告警  </LeftPanel>
      <RightPanel> <ChatPanel /> </RightPanel>
    </ContentRow>
    <BottomBar>
      <HealthPanel />
    </BottomBar>
  </template>
  <NewSessionDialog v-model:visible="showNewDialog" />
  <CrossProjectWarning v-if="chatStore.crossProjectWarning" ... />
```

### 4.10 URL 路由设计

```
/                        → 重定向到 /dashboard
/dashboard               → DashboardView（唯一视图）
/dashboard?session=xxx   → 直接打开指定 Session（深链接）
```

---

## 五、数据流

### 5.1 新建 Session 流程

```
用户点击 [+ 新建会话]
  → NewSessionDialog 弹出
  → 用户选择 Tab A（打开已有）→ 输入路径 "D:/Code-Insight-Financial"
  → 前端校验路径非空、无非法字符
  → 用户点 [确认]
  → POST /api/v1/projects  { name: "Code-Insight-Financial", local_path: "D:/Code-Insight-Financial" }
    → 后端验证路径存在 + 可读
    → register to ProjectRegistry
    → 返回 ProjectRecord
  → POST /api/v1/sessions  { project_name: "Code-Insight-Financial" }
    → SessionRegistry.create() → 返回 SessionRecord
  → sessionStore.currentSessionId = resp.session_id
  → sessionStore.currentProjectName = "Code-Insight-Financial"
  → DashboardView 从欢迎页 → 工作台
  → agentOpsStore.fetchAll() → 按 session_id 拉指标（当前为空）
  → chatStore 清空旧消息，等待新对话
```

### 5.2 Session 切换流程

```
用户在 SessionDropdown 中选择 "修复导入校验"
  → sessionStore.switchSession("abc123")
    → GET /api/v1/sessions/abc123
      → 返回 { session: {...}, messages: [50条] }
    → 更新 currentSessionId / currentProjectName / currentTitle
    → messages[] → chatStore 恢复聊天面板
    → 触发:
      1. WS re-subscribe → 发 { type: "subscribe", task_id: 旧task } + { type: "subscribe", task_id: 新task }
      2. agentOpsStore.fetchAll() → 新 session 的指标
      3. taskStore → 如果新 session 有活跃 task，加载 DAG
      4. opsStore.fetchAll() → 按项目过滤
      5. resourcesStore.fetchAll() → 按 session 过滤
```

### 5.3 聊天 + 跨项目检测流程

```
用户在 Session A (项目 "Code-Insight-Financial") 中输入:
  "参考 Orbit 的 ContextMatcher 实现类似的匹配逻辑"

前端:
  chatStore.send(text)
    → WS 发送 { type: "chat", text: "...", session_id: "A", project_name: "Code-Insight-Financial" }

后端 chat.py:
  text → ContextMatcher.match(query, current_project="Code-Insight-Financial")
    → 关键词: ["Orbit", "ContextMatcher", "匹配"]
    → 候选: [{ project: "Orbit", score: 0.8, ... }]
  → 跨项目检测: candidate.project_name ("Orbit") != current_project ("Code-Insight-Financial")
  → cross_warning = "Orbit"
  → 持久化消息到 chat_messages (session_id=A, cross_project_warning="Orbit")
  → WS 返回 { code: 0, data: { ..., cross_project_warning: "Orbit" } }

前端:
  chatStore.handleResponse(data)
    → candidates = [...] (仍展示匹配结果，供用户参考)
    → crossProjectWarning.value = "Orbit"
    → CrossProjectWarning 组件渲染弹窗:
       "当前会话绑定项目「Code-Insight-Financial」...
        对「Orbit」仅有只读权限。
        是否切换到「Orbit」的会话？"
    用户选择 [切换]:
      → sessionStore 查找 project_name="Orbit" 的 session
        → 存在 → switchSession(orbit_session_id)
        → 不存在 → POST /api/v1/sessions { project_name: "Orbit" }
          → switchSession(new_id)
    用户选择 [取消]:
      → crossProjectWarning = null, 弹窗消失
      → 用户继续在当前 Session 工作（引用 Orbit 代码 → 沙箱 ro 挂载）
```

### 5.4 沙箱执行流程

```
Scheduler 触发 CODING 阶段 → 需要沙箱执行:
  task 携带 session_id
  → SandboxRunner 从 SessionRegistry.get(session_id) 获取 project_name
  → ProjectRegistry.get(project_name) 获取 local_path
  → ProjectRegistry.list_all() 获取所有项目路径（排除自身）作为 readonly_paths

Sandbox.run(code, language="python", external_paths=["D:/SomeOtherCode"])
  → _build_mounts():
      -v /tmp/script_abc.py:/tmp/script_abc.py:ro
      -v D:/Code-Insight-Financial:/workspace:rw         ← 绑定项目 rw
      -v D:/Orbit:/readonly/Orbit:ro                     ← 其他项目 ro
      -v D:/SomeOtherCode:/readonly/SomeOtherCode:ro     ← 外部引用 ro
  → docker run ... python /tmp/script_abc.py
  → LLM 代码中:
      open("/workspace/src/order.py", "w")  → ✅ 写入成功
      open("/readonly/Orbit/src/matcher.py") → ✅ 读取成功
      open("/readonly/Orbit/src/matcher.py", "w") → ❌ Read-only file system
```

---

## 六、与 PRD 对照表

| PRD 验收标准 | 方案节 | 关键代码位置 |
|-------------|--------|------------|
| AC1: 顶栏始终显示项目名 | 4.5 SessionBar.vue | `SessionBar.vue` → `sessionStore.currentProjectName` |
| AC2: 新建 Session ≤3 步 | 4.6 NewSessionDialog.vue + 5.1 数据流 | `NewSessionDialog.vue` → `POST /sessions` |
| AC3: 指标按 Session 隔离 | 4.3 agentops.ts + 5.2 切换流程 | `agentops.fetchAll()` 加 `?session_id=` |
| AC4: 沙箱写入越界报错 | 3.11 executor.py + 5.4 沙箱执行流 | `Sandbox._build_mounts()` → Docker `:ro` |
| AC5: 跨项目提示弹窗 | 3.9 chat.py + 4.7 CrossProjectWarning.vue | `chat.py` L67-72 + `CrossProjectWarning.vue` |
| AC6: 聊天记录持久化 | 3.2 registry.py + 4.1 session.ts | `SessionRegistry.get_messages()` → `sessionStore.switchSession()` |

---

## 七、分步交付计划

### PR #1：后端——Session + Project 扩展 + 跨项目检测
**文件**（7 个新增 + 6 个修改）:
- 新增: `sessions/models.py`, `sessions/registry.py`, `api/routes/sessions.py`, `api/routes/projects.py`
- 修改: `projects/models.py`, `projects/registry.py`, `api/schemas/task.py`, `api/routes/tasks.py`, `api/routes/chat.py`, `context/matcher.py`, `api/main.py`
- **不涉及前端改动**，向后兼容现有 Dashboard

### PR #2：沙箱——多卷挂载隔离
**文件**（1 个修改）:
- 修改: `sandbox/executor.py`（加 `project_path` + `readonly_paths` 参数，`_build_mounts()` 方法）

### PR #3：前端——Session 视图重构
**文件**（4 个新增 + 6 个修改）:
- 新增: `stores/session.ts`, `components/layout/SessionBar.vue`, `components/layout/NewSessionDialog.vue`, `components/chat/CrossProjectWarning.vue`
- 修改: `views/DashboardView.vue`, `stores/chat.ts`, `stores/agentops.ts`, `stores/dashboard.ts`, `components/layout/GlobalStatusBar.vue`

---

## 八、风险与冲突

| 风险 | 缓解 |
|------|------|
| `projects` 表加 `local_path` 字段，旧数据无此字段 | ALTER TABLE 加 `DEFAULT ''`；注册表 `_row_to_record` 兼容 `local_path` 列缺失 |
| 前端 4 Tab 布局全量替换，视觉回归风险 | PR #1+#2 先合，PR #3 单独审查；开发期间用 `VITE_LEGACY_TABS=true` 环境变量保留旧布局 |
| Chat 消息量增长 → SQLite 性能 | 每 session 默认返回最近 50 条；消息总量超 10 万时加归档策略（Phase 2） |
| 沙箱多卷挂载在 Windows Docker Desktop 上路径转换（`D:/xxx` → `/d/xxx` 或 `//d/xxx`） | `_build_mounts()` 内做平台检测：Windows → `//d/Code-Insight-Financial` 格式；Linux → 原样 |
