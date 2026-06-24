# 实现记录 —— Session 架构重构

基于 [阶段1-PRD](阶段1-PRD-Session架构重构.md)（6 条验收标准）+ [阶段2-技术方案](阶段2-技术方案-Session架构重构.md)。

## 方案引用

按技术方案设计，分三个 PR 交付：
- PR #1: 后端 Session + Project 扩展 + 跨项目检测（向后兼容）
- PR #2: 沙箱多卷挂载隔离
- PR #3: 前端 Session 单页面视图

## 改动清单

### 新增文件（7 个）

| 文件 | 用途 |
|------|------|
| `src/orbit/sessions/__init__.py` | Session 模块入口 |
| `src/orbit/sessions/models.py` | `SessionRecord` + `ChatMessageRecord` 数据类 |
| `src/orbit/sessions/registry.py` | `SessionRegistry` 类：Session CRUD + ChatMessage CRUD（SQLite，与 ProjectRegistry 共用 `data/projects.db`） |
| `src/orbit/api/routes/sessions.py` | Session API 端点：POST/GET/PATCH `/api/v1/sessions` |
| `src/orbit/api/routes/projects.py` | Project API 端点：POST/GET `/api/v1/projects` |
| `frontend/src/stores/session.ts` | Pinia Session Store：列表/切换/创建/消息恢复 |
| `frontend/src/components/layout/SessionBar.vue` | 顶栏：项目名 badge + Session 下拉 |
| `frontend/src/components/layout/NewSessionDialog.vue` | 新建 Session 弹窗：打开已有/新建项目二选一 |
| `frontend/src/components/chat/CrossProjectWarning.vue` | 跨项目引用警告弹窗 |

### 修改文件（12 个）

| 文件 | 改动 |
|------|------|
| `src/orbit/projects/models.py` | `ProjectRecord` 加 `local_path` 字段；`to_dict()` 含路径 |
| `src/orbit/projects/registry.py` | `_ensure_table()` 加 ALTER TABLE 存量兼容；`register()` 支持 `local_path`；新增 `get_by_path()`、`find_by_path_prefix()`；`_row_to_record()` 兼容 `local_path` 列缺失 |
| `src/orbit/api/schemas/task.py` | `TaskCreateRequest` 加 `session_id`（32char UUID4 hex）；`TaskStatusResponse` 加 `session_id` + `project_name` |
| `src/orbit/api/routes/tasks.py` | `create_task()` 验证 `session_id` 存在 + 取 `project_name` 填入响应 |
| `src/orbit/api/routes/chat.py` | 接收 `session_id`/`project_name`；跨项目检测（matched != current → `cross_project_warning`）；消息持久化到 `SessionRegistry`；向后兼容 `session_projects` 参数 |
| `src/orbit/sandbox/executor.py` | `Sandbox.__init__()` 加 `project_path`/`readonly_paths`；新增 `_build_mounts()` 方法；`run()` 加 `external_paths` 参数；新增 `_to_docker_path()` Windows 路径转换 |
| `src/orbit/api/main.py` | 注册 sessions + projects 路由 |
| `frontend/src/views/DashboardView.vue` | 4 Tab → 单页 Session 布局：顶栏（SessionBar + 状态灯）→ 欢迎页（无 Session）→ 工作台（指标/DAG/聊天/告警） |
| `frontend/src/stores/chat.ts` | 移除 `sessionProjects`；`send()` 加 `sessionId`/`projectName` 参数；加 `crossProjectWarning` + `dismissWarning()`；加 `restoreMessages()` |
| `frontend/src/stores/agentops.ts` | `fetchMetrics`/`fetchAlerts` URL 加 `?session_id=` 查询参数 |
| `frontend/src/stores/dashboard.ts` | 精简为仅管理 WS 连接状态 |
| `frontend/src/components/chat/ChatPanel.vue` | `handleSend()` 附 `session_id` + `project_name` |

### 测试文件（3 个）

| 文件 | 改动 |
|------|------|
| `tests/unit/test_task_api.py` | 所有 POST /tasks 请求加 `session_id`；新增 `session_id` fixture |
| `tests/unit/test_projects.py` | `_cleanup()` 从删除 DB 改为 deactivate 测试数据 |
| `tests/unit/test_context_matcher.py` | 同上 |
| `tests/integration/test_health_api.py` | `test_create_task_success` 加 `session_id` fixture |

## 偏差说明

严格按方案实现，无偏离。

## 回溯对照

| PRD 验收标准 | 方案设计决策 | 代码位置 |
|-------------|------------|---------|
| AC1: 顶栏始终显示项目名 | SessionBar 组件从 sessionStore 读 `currentProjectName` | `SessionBar.vue:4-6` |
| AC2: 新建 Session ≤3 步 | NewSessionDialog 二选一 → POST /sessions | `NewSessionDialog.vue` → `session.ts:createSession()` |
| AC3: 指标按 Session 隔离 | agentOps.fetchAll() URL 加 `?session_id=` | `agentops.ts:23-26` |
| AC4: 沙箱写入越界报错 | Sandbox._build_mounts() 生成 ro 挂载参数 | `executor.py:85-102` |
| AC5: 跨项目提示弹窗 | Chat WS 返回 `cross_project_warning` → CrossProjectWarning 弹窗 | `chat.py:72-78` → `CrossProjectWarning.vue` |
| AC6: 聊天记录持久化 | SessionRegistry.add_message() / get_messages() | `registry.py:176-230` |

## 测试结果

| 层 | 通过 | 失败 |
|----|------|------|
| 单元 | 134 | 0 |
| 集成 | 11 | 0 |
| **合计** | **145** | **0** |

TypeScript 类型检查通过，Vite 构建通过。
