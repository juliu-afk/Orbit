# PR10 技术设计：graph-snapshots 历史代码图谱（EPIC）

> 日期：2026-07-11
> 性质：**后端大工程 EPIC，多人周**，非单会话可完成。本文为分阶段路线图。
> 调研来源：CodeGraphEngine/change_detector/git 集成/alembic 源码精读

## 一、目标
沿 git 历史时间轴，查看代码图谱随 commit 演进。前端时间滑块切换历史版本图谱。

## 二、现状（file:line）
- `codegraph_routes.py:239-250` get_graph_snapshots 返回**空数组桩**，前端未调用
- `CodeGraphEngine.build_index(dir)`（`graph/engines/code_graph.py:57`）**全量重建**（先 clear_all），中项目 10-30s
- CodeNode/Edge 模型（`graph/models/nodes.py:43,86`）**无 git_sha 字段**，存 `data/graph.db`
- **无 git 历史遍历代码**（gitpython 声明未用）。有 `incremental_update(file)`、`change_detector._git_diff_files`（:107）
- 前端 CodeGraphDrawer/CytoscapeCanvas/codegraph store **无任何时间轴/滑块**
- 迁移走 alembic（`alembic/versions/*.py`）+ main.py:435 create_all 幂等建表

## 三、存储方案对比

| 维度 | A 加git_sha列 | B 独立快照表 | C 按需重建 |
|------|--------------|-------------|-----------|
| 存储 | 高(400万行/千commit) | 中(1GB可压缩) | 极低 |
| 查询 | 快(索引) | 快(BLOB) | 慢(10-30s) |
| 复杂度 | 中高(改模型+迁移) | 低中(新表) | 低 |

**MVP 用 B（独立 graph_snapshots 表），后期按需迁 A。**

## 四、分阶段路线

### 阶段 P1 — MVP：按需重建 + 有限历史（3-5 天）
- 新增 `GET /codegraph/git-commits?project_id&limit` → git log 返回 commit 列表
- 新 `SnapshotManager`：`list_commits()` + `build_at_commit(hash)`（git checkout hash → build_index → 恢复；**git stash 保护未提交改动**）
- 改 get_graph_snapshots 返回 commit 列表 + built 状态
- 新 `GET /codegraph/graph-data-at?project_id&commit=HASH`
- 前端 CytoscapeCanvas 加 `<el-slider>`（commit 索引），切换调 graph-data-at
- 内存缓存 `{commit_hash: {nodes,edges}}`（重启即丢）
- **里程碑**：可拖时间轴看旧图谱

### 阶段 P2 — 持久化 + 后台预建（5-8 天）
- 新建 `graph_snapshots` 表（commit_hash UNIQUE, serialized_data BLOB zstd 压缩, commit 元数据）
- SnapshotManager `save_snapshot`/`load_snapshot`
- 启动后台协程（复用 LoopScheduler `loop/scheduler.py:186` 或 lifespan asyncio.create_task）：每 5min git fetch → 新 commit 逐一 `git worktree add` 建图存快照
- build_at_commit 先查 DB 缓存
- **里程碑**：秒级切换，多 commit 自动建

### 阶段 P3 — 增量 + git_sha 模型（5-10 天）
- CodeNode/Edge 加 `git_sha` 列（alembic 迁移）+ valid_from/valid_until
- build_index 接收 git_sha；incremental_update 只写变更文件（`git diff hash~1..hash`）
- 删除/重命名处理（标记 valid_until）
- **里程碑**：存储优化，千 commit 可接受

### 阶段 P4 — 差异可视 + 演进分析（3-5 天）
- `GET /codegraph/snapshot-diff?from&to` → 增删改节点/边
- 前端差异高亮（新增绿/删除红）
- `GET /codegraph/node-history?name` → 节点跨 commit 演进

## 五、关键风险
- git checkout 切历史版本需 stash 保护未提交改动（否则冲突/丢改动）
- build_index 每文件多次独立事务提交=性能瓶颈（大项目分钟级）
- git worktree add 磁盘开销（每 worktree 几百 MB 源码）
- 后台预建 CPU 占用影响主服务

## 六、建议
- 立独立 epic，出正式 PRD + 逐阶段技术方案
- P1 MVP 先落地（按需重建，接受 10-30s 切换等待 + 良好 loading）
- 前端时间滑块在 P1 前保持 disabled
- 每阶段独立 PR，触 graph 引擎核心→走 `/ce-code-review`

## 七、总览

| 阶段 | 描述 | 工作量 |
|------|------|--------|
| P1 | MVP 按需重建 | 3-5d |
| P2 | 持久化+后台预建 | 5-8d |
| P3 | 增量+git_sha | 5-10d |
| P4 | 差异可视 | 3-5d |
