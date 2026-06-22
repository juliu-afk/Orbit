# Orbit 开发会话记录

## 2026-06-23

### 完成项
- PR #2 Step 2.1/2.2：LLM 网关（熔断器 + 主备降级 + 成本追踪）+ 检查点（Redis/PG 双层 + 乐观锁）
- PR #3 MVP-01/03：调度器骨架（状态机 + Agent 循环 + 检查点恢复）+ Docker 沙箱（网络隔离 + 超时）
- PR #4 GitHub Actions 全套：5 workflow（ci/test/security/integration/mutation）+ pre-commit + 历史 lint 清理
- PR #5 Step 3.1-3.3：三图谱引擎（代码 AST / 数据库反射 / 配置 5 格式 + 漂移检测）

### PR / Commit
- PR #2 → 合并 `2585ab1`（2 commit：feat + fix 审查修复）
- PR #3 → 合并 `c0c1650`（2 commit：feat + fix 审查修复）
- PR #4 → 合并 `42058b8`（2 commit：ci 配置 + lint 清理）
- PR #5 → 合并 `330ad69`（2 commit：feat 三图谱 + fix 审查修复）

### 关键决策
- **三图谱物理隔离**：无外键约束，跨图谱关系用 Edge 表软关联
- **AST 而非正则**：PRD 技术约束（代码图谱准确性）
- **反射而非 DDL 解析**：数据库图谱走 information_schema
- **配置规范化 hash**：相同配置不同格式（YAML 键序）产生相同 SHA256
- **Prod 禁止 auto_fix**：配置漂移仅告警，人工介入
- **基线实例属性**：消除全局 dict 多实例污染（PR#5 P2-3）

### 待处理
- Step 4.1 L1-L4 防幻觉（图谱验证/动态追踪/熵监控/类型检查）
- Step 4.2 L5-L8 防幻觉（Z3 验证/合约双向/沙箱执行/配置漂移修复）
- Step 5.1 调度器扩展为 DAG（拓扑排序 + 并发执行）

### CI 状态
- 5 个 workflow 全部就绪
- ruff/bandit/pytest 门禁生效
- 公开仓库 Linux runner 无限免费