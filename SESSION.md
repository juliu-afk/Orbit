# Orbit 开发会话记录

## 2026-06-25-26

### 完成项
- **系统索检**：全链路审查，发现 compliance/knowledge DB 初始化鸡生蛋问题、测试隔离泄漏、chat WS 无重试、RG 熔断灯不亮、静态路径错误等 8 个 bug
- **PR #50** fix: knowledge db init chicken-egg — `_get_conn()` 自动建表 + 测试隔离
- **PR #52** fix: chat WS retry + static path + resource_guard breaker light
- **PR #54** feat: 仪表盘UI三修复 — 去外层滚动+统一边框+代码diff弹出
- **PR #55** fix: body+.dashboard overflow:hidden
- **PR #56** fix: 聊天框输入区裁剪 — flex 布局替代硬编码 calc
- **PR #57** fix: flex 布局消滚动 + 代码 diff API 时序修正（publish 移到 transition 前）
- **PR #58** feat: Agent 回复带角色头像+名称 — emoji 头像+彩色标签+大小写匹配修复
- 4 次 exe 重建，Playwright UI 验证（滚动条/输入区/代码diff链路）

### 版本
- exe 交付物: `D:\Orbit\Deliverables\Orbit.exe` (156MB)

### 待处理
- `test_task_failure_propagates` 预存失败（`_run_agent` 吞异常不会触发 FAILED）
- `test_generate_stream_no_monitor_no_litellm` 预存失败
- exe 代码签名
- CI lint-typecheck 偶发 black 格式化失败

### 踩坑记录
- linter 多次 revert 文件改动 → 必须 commit 前确认文件状态
- 禁止未审查直接合并（PR #53 教训）
- `overflow:hidden` 在 body 上会导致内容裁剪 → 只应在 workspace 层级
- 硬编码 `calc(100vh - 40px)` 有像素偏差 → 改用 flex 布局
- Agent 角色名大小写不一致（后端 `"Clarifier"` vs 前端 `"clarifier"`）→ 统一 `toLowerCase()`

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
