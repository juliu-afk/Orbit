# Reviewer Input — PR #59

> ⚠️ 本文档是精简审核上下文。完整 diff 在 `pr.diff`，仅在需要时读取具体片段。

## Task

请基于以下上下文审核 PR #59，输出 P0/P1/P2 和 RR-1~RR-5 覆盖情况。

## PR Metadata

- **PR**: #59
- **Title**: refactor: 模型体系重构——DS V4 Pro/Flash + GLM-5.2 + GLM-4.7 Flash 降级
- **Files**: 18 changed (+325/-394)
- **Reviews**: 0 | **Comments**: 8

### PR Description (摘要)

```text
## 改动摘要

### 模型体系重构成四层
| 角色 | 模型 | 计费 |
|------|------|------|
| architect/developer | DeepSeek V4 Pro | /usr/bin/bash.435//usr/bin/bash.87 per 1M |
| config_manager/clarifier | DeepSeek V4 Flash | /usr/bin/bash.14//usr/bin/bash.28 per 1M |
| reviewer/qa | GLM-5.2 | Coding Plan 订阅 |
| 降级兜底 | GLM-4.7 Flash | **免费** → 挂起人工 |

### 架构变更
- llm_client 单例 → agent_llms dict 按角色注入
- Scheduler 不再直接调 LLM，只编排 Agent
- 删 Qwen/Ollama 所有引用
- GLM 走 Coding Plan 订阅端点 /api/coding/paas/v4

### 文件
- 14 文件，+260/-473 行...
```

### Changed Files

- AGENTS.md
- CLAUDE.md
- docker-compose.yml
- src/orbit/api/main.py
- src/orbit/core/config.py
- src/orbit/gateway/client.py
- src/orbit/hallucination/schemas.py
- src/orbit/resource_guard/degradation.py
- src/orbit/scheduler/orchestrator.py
- tests/e2e/conftest.py
- tests/e2e/test_e2e_circuit_breaker.py
- tests/perf/conftest.py
- tests/unit/test_coverage_boost.py
- tests/unit/test_dev_pipeline.py
- tests/unit/test_integration_glue.py
- tests/unit/test_pr1_coverage.py
- tests/unit/test_resource_guard.py
- tests/unit/test_scheduler.py

### Existing Review Comments

- **juliu-afk**: ## PR #59 复审结论：Request Changes（2 P0 仍阻塞 + 1 合并冲突）

### 开发者已提交的修复
- `74d8b08` fix: CI残留——config熵阈值+conftest参数+模型名
- `020e735` fix: 删 conftest 未用 llm 变量+import（ruff F841）

### 问题检查清单

| 问题 | 上次状态 | 本次检查 | 结论 |
|------|---------|---------|------|
| P0-1 black 格式化 | ❌ fail | 新 commits 未触发 CI，无法验证 | **待验...
- **juliu-afk**: ## PR #59 复审结论：Request Changes（2 P0 仍阻塞 + 合并冲突未解）

### 开发者推送情况
- 最新 commit：`f3a5ee5` — ci: 强制触发 CI 重跑（black+linter+conftest 已修复）
- 但 `f3a5ee5` 是**空 commit**，无实际代码变更，CI 未触发。

### 问题检查清单

| 问题 | 上次状态 | 本次检查 | 结论 |
|------|---------|---------|------|
| P0-1 black 格式化 | 待验证 | CI 未重新运行，无法验证 | **待验证** |
|...
- **juliu-afk**: ## PR #59 Round 4 Review — Request Changes 🔴

**审查时间**: 2026-06-26 01:23 CST  
**审查 Commit**: `743481fb9b48f6560613d2001413b4ed7dfd181a`  
**前序 Review**: Round 3 → 开发者提交 `4dbce37d`（P0-2b + P0-3 尝试修复）+ `743481fb`（解决合并冲突）

---

### 已确认修复 ✅

| 项目 | Commit | 说明 |
|------|--------|------|
| 合并冲突 | `74348...
- **juliu-afk**: ## PR #59 Round 5 Review — Request Changes 🔴

**审查时间**: 2026-06-26 02:11 CST  
**审查 Commit**: `5233f4e18395504bf896e9bfa70114a6bbe3977d`  
**前序 Review**: Round 4 → 开发者提交 `f627ac58`（black 格式化）+ `5233f4e1`（ruff import 排序）

---

### 已确认修复 ✅

| 项目 | Commit | 说明 |
|------|--------|------|
| P0-1 black 格式...
- **juliu-afk**: ## Round 6 Review — Request Changes 🔴

本轮开发者提交 `6136af8` 修复了 P0-3（ZAI_API_KEY）和 P0-4（e2e conftest AgentFactory），代码层面方向正确。但本地运行测试后，发现 **2 个新的 P0 阻塞项**。

---

### 开发者修复确认 ✅

| Commit | 修复内容 | 状态 |
|--------|---------|------|
| `f627ac58` + `5233f4e1` | black 格式化 + ruff import 排序 | ✅ P0-1 修复 |
| `6136a...
- **juliu-afk**: ## Round 7 审查 — 2026-06-26

| 检查项 | 状态 |
|--------|------|
| CI 10/10 pass | ❌ 8/10（e2e + unit-test 3.11 失败） |
| pytest-cov ≥80% | ✅ 80.35% |
| P0 阻塞项清零 | ❌ 2 项待修复 |

### 已修复 ✅

- **P0-5** `_run_agent` 吞异常 → commit `72c0f42` 已改为向上抛出 `raise`，确认修复。

---

### P0-6 [未修复] `test_generate_stream_basic` 调用真...
- **juliu-afk**: ## Round 8 审查 — 2026-06-26

| 检查项 | 状态 |
|--------|------|
| CI 10/10 pass | ❌ 9/10（unit-test 3.11 失败，3.12 取消） |
| pytest-cov ≥80% | 待确认（无法拉取日志，上次 80.35%） |
| P0 阻塞项清零 | ❌ 1 项待修复 |

---

### 已修复 ✅

#### P0-7 E2E ClarifierAgent JSON 解析失败
**修复方式**：`src/orbit/agents/clarifier.py:176` 新增 mock 模式分支：
```p...
- **juliu-afk**: ## Round 9 审查 — 2026-06-26

| 检查项 | 状态 |
|--------|------|
| CI 核心测试 | ✅ e2e / unit-test 3.11 / unit-test 3.12 / integration / lint-typecheck / perf / security 全绿 |
| pytest-cov ≥80% | ✅（`--cov-fail-under=80` 通过） |
| P0 阻塞项清零 | ✅ P0-6 / P0-7 已修复 |
| build | ❌ Docker registry 超时（非代码问题） |

---

### 已修...

---

# PR Repo Map — #59

## PR Summary
- **PR**: #59
- **Title**: refactor: 模型体系重构——DS V4 Pro/Flash + GLM-5.2 + GLM-4.7 Flash 降级
- **Files Changed**: 18
- **Comments**: 8
- **Reviews**: 0

## Changed Files by Category

### Tests (9)
- tests/e2e/conftest.py
- tests/e2e/test_e2e_circuit_breaker.py
- tests/perf/conftest.py
- tests/unit/test_coverage_boost.py
- tests/unit/test_dev_pipeline.py
- tests/unit/test_integration_glue.py
- tests/unit/test_pr1_coverage.py
- tests/unit/test_resource_guard.py
- tests/unit/test_scheduler.py

### Docs (2)
- AGENTS.md
- CLAUDE.md

### Other (7)
- docker-compose.yml
- src/orbit/api/main.py
- src/orbit/core/config.py
- src/orbit/gateway/client.py
- src/orbit/hallucination/schemas.py
- src/orbit/resource_guard/degradation.py
- src/orbit/scheduler/orchestrator.py

## Permission Scan Summary

✅ 权限扫描未发现异常

详见 `rule-scan.md`。

## ⚠️ Historical Gotcha

**require_permission 权限字符串问题已反复出现 5 次**: PR#73 → #75 → #78 → #83 → #84。

Reviewer 必须检查:
1. 新增写端点是否都有 `require_permission` 保护？
2. 权限字符串拼写是否正确（module:action 格式）？
3. 权限是否在 `rbac.py` 和 seed 数据中注册？
4. 测试是否覆盖未授权/无权限场景？

## Suggested Reviewer Focus

1. **权限字符串是否正确** —— 每个新增/修改端点是否有匹配的 `require_permission`？
2. **API endpoint 是否有权限保护** —— 写端点必须有 RBAC，只读端点是否合理暴露？
4. **测试是否覆盖负向权限场景** —— 未授权用户是否返回 403？

---

# Rule Scan — PR #59 权限字符串扫描

**扫描范围**: 15 个 Python 文件
**发现调用**: 0 处 require_permission
**权限注册表**: 0 个已注册权限（来自 rbac.py Permission 枚举）
**扫描时间**: 自动生成

## 结果

[PASS] No suspicious permission issues found.

所有 `require_permission` 调用均使用合法字符串字面量且已在 rbac.py 注册。

---

## ⚠️ Historical Gotcha — require_permission

**权限字符串问题已反复出现 5 次**: PR#73 → #75 → #78 → #83 → #84。

Reviewer 必须逐项检查：

1. 权限字符串拼写是否正确（`module:action` 格式）？
2. 权限是否在 `backend/app/core/rbac.py` 中注册？
3. 权限是否在 seed 数据中授予了正确的角色？
4. 新增 API 端点是否都有 `require_permission` 保护？
5. 测试是否覆盖未授权/无权限场景（期望 403）？

---

## Required Review Output

请按以下格式输出审核结论：

```markdown
## 结论
是否建议合并：是/否

## P0 — 阻断合并
...

## P1 — 应修复
...

## P2 — 建议优化
...

## RR 覆盖
- RR-1: 需求/AC 对齐 — [通过/部分失败/不通过]
- RR-2: 实现正确性 — [通过/部分失败/不通过]
- RR-3: 权限/RBAC/数据隔离 — [通过/部分失败/不通过]
- RR-4: 测试覆盖 — [通过/部分失败/不通过]
- RR-5: 回归风险 — [通过/部分失败/不通过]

## 建议修复指令
...
```

---

*Generated by build_reviewer_input.py for PR #59*