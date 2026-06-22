# Orbit 开发会话记录

## 2026-06-22

### 完成项
- 项目骨架：`src/orbit/` 包结构 + `tests/` + `docs/` + `alembic/`
- Step 0.1 项目章程：`docs/charter.md`（YAML frontmatter + 5 条风险登记册 + 架构锚定声明）
- Step 0.2 环境初始化：`pyproject.toml`（Poetry）+ `Makefile` + `docker-compose.yml` + `.env.example`
- Step 1.1 API 契约：FastAPI 应用工厂 + tasks CRUD/cancel + health + Pydantic v2 schemas
- Step 1.2 三图谱 Schema：SQLAlchemy 2.0 ORM（CodeNode/DbNode/ConfigNode/Edge 物理隔离）
- 开发计划追加第 27 章（七开源工具融入方案，17610 字）
- 27 个单元测试全绿，覆盖率 96.86%

### PR / Commit
- PR #1 `feat: Step 0.2-1.2 环境与API契约` → 已合并到 master（merge commit `8c393b6`）
  - 3 个 commit：feat（代码）/ docs（文档）/ fix（审查修复）
- 复审通过：P1×3 + P2×6 全修，无新增问题

### 审查修复（10 项）
- P1-1: cancel_task 加 CANCELLED 状态 + 枚举值
- P1-2: uuid 导入提到文件顶部
- P1-3: config.py 注释改为准确描述
- P2-1: language 用 Literal 替代 constr 正则
- P2-2: /health 无前缀决策注释（K8s 探针惯例）
- P2-3: HealthResponse 版本从 importlib.metadata 读
- P2-4: test_cancel 断言状态 + test_cancel_already_cancelled
- P2-5: 补边界值测试（prd 9/10/5000/5001, language）
- P2-6: DbNode schema 注释修正

### 关键决策
- **Poetry 1.8.x + Python 3.14 不兼容**：Poetry CLI 报 cleo 错误。装 Python 3.12.8 + venv 跑测试，`pyproject.toml` 保持 Poetry 格式供 CI/Linux 用
- **包管理器选 Poetry**（开发计划 Step 0.2 指定）
- **Token ≤35 指标暂缓**（用户指示），保留章程字段但不作 CI 硬门禁
- **前端选 Vue3**（开发计划指定）
- **pydantic-settings → python-dotenv**（开发计划 3.4.1 指定）
- **TaskState 加 CANCELLED**：PRD 原始枚举无此值，但 cancel 端点语义必需（审查反馈 P1-1）

### 待处理
- Step 2.1 LiteLLM 网关 + 熔断器
- Step 2.2 检查点持久化（Redis + PostgreSQL）
- GitHub Actions CI（`.github/workflows/ci.yml`）尚未配置
- Poetry CLI 兼容问题需在 CI 环境（Linux）验证