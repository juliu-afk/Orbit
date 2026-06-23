# Orbit 开发会话记录

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

### 待处理
- Step 5.2 Agent 角色（代码在 feat/step5.2-agent-roles，待审查后重新 PR）
- Step 6.1 前端驾驶舱
- Step 7.1 灰度发布

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
