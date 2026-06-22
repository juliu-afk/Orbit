# 贡献指南

感谢你对 Orbit 的兴趣！本文档说明如何参与贡献。

## 开发环境

```bash
git clone https://github.com/<owner>/Orbit.git
cd Orbit
cp .env.example .env
make init    # 启动 PostgreSQL/Redis/LiteLLM + 安装依赖
make test    # 确认测试全绿
```

前置：Python 3.11+、Poetry 1.8.2、Docker。

## 开发流程（四阶段，强制）

所有改动必须走完整四阶段，无例外。详见 [`AGENTS.md`](AGENTS.md)。

1. **阶段1 PRD**：需求澄清，输出验收标准
2. **阶段2 技术方案**：API 设计 / 数据模型 / 边界 case 清单
3. **阶段3 编码 + 审查**：feature 分支，对照方案实现
4. **阶段4 测试门禁**：单元/集成/冒烟/回归全绿 + PR CI 绿

阶段之间等待确认，禁止跳过。改动越小文档越短，但不能没有。

## Git 约定

- **分支**：`feat/<简称>` / `fix/<简称>`，禁止直接 push master
- **Commit**：Conventional Commits，subject ≤50 字符
  - `feat(scheduler): 实现状态机 Step 5.1`
  - `fix(graph): 修复跨图谱查询空结果`
  - `docs(api): 补充 OpenAPI 示例`
- **禁止**：`git push --force`、`git add -A`、amend 已发布 commit

## 代码风格

- 类型标注：所有 public 函数写完整类型签名
- 注释用中文，业务/调度/防幻觉逻辑必须注释 WHY，面向非编程人士审计
- 命名：模块/类 PascalCase，函数/变量 snake_case
- ORM 用 SQLAlchemy 2.0 风格（`Mapped` / `mapped_column`）
- 异步：调度器/网关/沙箱一律 `async def`

## 测试

| 级别 | 命令 |
|---|---|
| 单元 | `pytest tests/unit/ -q` |
| 集成 | `pytest tests/integration/ -q` |
| 冒烟 | `pytest tests/e2e/ -q -k "smoke"` |
| 全量回归 | `pytest tests/e2e/ -q` |

覆盖率门禁 ≥80%，调度器/防幻觉纯函数 100%。

Bug 修复必须先写 `test_regression_` 复现用例。

## PR 检查清单

提交 PR 前确认：
- [ ] 走完四阶段，文档齐全
- [ ] 测试全绿，覆盖率未下降
- [ ] 新增依赖已讨论（禁止擅自加包）
- [ ] 无硬编码密钥/Token
- [ ] commit message 符合 Conventional Commits
- [ ] CHANGELOG 已更新（如涉及用户可见变更）

## 报告 Bug / 提建议

开 GitHub Issue，描述：
- 复现步骤
- 预期行为 vs 实际行为
- 环境信息（Python 版本、OS、Docker 版本）

## 安全漏洞

禁止在 GitHub Issue 公开安全漏洞。私发邮件给维护者。