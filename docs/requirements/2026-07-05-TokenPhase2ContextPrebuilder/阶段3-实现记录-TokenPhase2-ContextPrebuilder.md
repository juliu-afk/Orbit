# 阶段3-实现记录-TokenPhase2-ContextPrebuilder

> 日期: 2026-07-05 | 版本: v1.0 | 状态: 编码完成，待代码审查
> 基于: [阶段2-技术方案](阶段2-技术方案-TokenPhase2-ContextPrebuilder.md)

---

## 方案引用

严格按阶段2技术方案实现，无偏离。

| 方案决策 | 实现 |
|---------|------|
| SCOPING 插入 PARSING→PLANNING | `STATE_TRANSITIONS` 更新 |
| 快车道跳过 SCOPING+PLANNING | `FAST_LANE_TRANSITIONS` 更新 |
| ContextPrebuilder fail-open | `try/except` + `logger.debug()` |
| 预构建与压缩管线正交 | 预构建改 TaskContext，压缩改 messages |
| SCOPING 纯规则引擎 | `_run_scoping()` 0 LLM 调用 |
| 5 个角色子类 | `prebuilders/clarifier.py` 等 5 文件 |

---

## 改动清单

### 新增文件（18 个）

| 文件 | 简述 |
|------|------|
| `src/orbit/context/prebuilder.py` | ContextPrebuilder 抽象基类 + 工厂方法 `build_for_role()` |
| `src/orbit/context/prebuilders/__init__.py` | 包初始化 |
| `src/orbit/context/prebuilders/clarifier.py` | Clarifier——删除代码细节，截断 PRD 到 3000 |
| `src/orbit/context/prebuilders/architect.py` | Architect——删除完整文件内容，注入影响面摘要 |
| `src/orbit/context/prebuilders/developer.py` | Developer——限制 ≤5 文件，删除完整 diff |
| `src/orbit/context/prebuilders/reviewer.py` | Reviewer——删除完整 diff，≤3000 diff 摘要 + 权限/schema 摘要 |
| `src/orbit/context/prebuilders/qa.py` | QA——删除完整代码，注入测试粒度指令 |
| `src/orbit/context/builders/__init__.py` | 包初始化 |
| `src/orbit/context/builders/test_builder.py` | 测试上下文——应跑测试清单 |
| `src/orbit/context/builders/design_builder.py` | 设计上下文——影响面+候选文件 |
| `src/orbit/context/builders/impl_builder.py` | 实现上下文——最小变更任务书 |
| `src/orbit/context/builders/debug_builder.py` | 调试上下文——根因候选+trace |
| `src/orbit/context/builders/req_builder.py` | 需求上下文——AC 提取+边界 |
| `src/orbit/context/builders/docs_builder.py` | 文档上下文——需更新文档清单 |
| `src/orbit/context/builders/release_builder.py` | 发布上下文——release notes+风险 |
| `src/orbit/context/scanners/base.py` | BaseScanner 抽象基类 |
| `src/orbit/context/scanners/__init__.py` | 包初始化——导出 5 个扫描器 |
| `src/orbit/context/scanners/affected_files.py` | git diff → 分类文件列表 |
| `src/orbit/context/scanners/import_deps.py` | Python AST → import 依赖图 |
| `src/orbit/context/scanners/test_coverage.py` | coverage.json → 覆盖率缺口 |
| `src/orbit/context/scanners/schema_change.py` | Alembic → 表/列变更 |
| `src/orbit/context/scanners/permission_string.py` | 正则 → 权限字符串比对 |
| `tests/unit/test_context_prebuilder.py` | 20 个单元测试——覆盖基类+5 子类 |

### 修改文件（3 个）

| 文件 | 简述 |
|------|------|
| `src/orbit/agents/context.py` | TaskContext 加 `max_chars_per_field=5000` + `_truncate_all()` |
| `src/orbit/api/schemas/task.py` | TaskState 加 `SCOPING` |
| `src/orbit/scheduler/task_runner.py` | ROLE_MAP/STATE_TRANSITIONS 更新 + `_run_scoping()` + `_decide_test_scope()` + ContextPrebuilder 集成 |
| `src/orbit/context/__init__.py` | 导出 ContextPrebuilder |

---

## 偏差说明

严格按方案实现，无偏离。

---

## 回溯对照

| PRD AC | 方案 § | 代码位置 |
|--------|-------|---------|
| AC1: 5 个 ContextPrebuilder | §3.3 | `context/prebuilders/clarifier.py` — `build()` 删除 l2; `reviewer.py` — `build()` 删除 full_diff; 等 5 文件 |
| AC2: TaskContext 字段 ≤5000 | §5 | `agents/context.py:67-89` — `_truncate_all()` 递归截断 |
| AC3: 7 个 Context Builder | §4.3 | `context/builders/test_builder.py` — `build()` 返回应测清单; 等 7 文件 |
| AC4: 5 个预扫描器 | §4.2 | `context/scanners/affected_files.py` — `scan()` git diff; 等 5 文件 |
| AC5: Reviewer 不含完整 diff | §3.3 | `context/prebuilders/reviewer.py:30` — `l2.pop("full_diff", None)` |
| AC6: SCOPING → 测试粒度 | §3.4 | `scheduler/task_runner.py:300-353` — `_run_scoping()`; `:838-862` — `_decide_test_scope()` |
| AC8: 压缩管线不受影响 | §7 | `scheduler/task_runner.py:364-375` — ContextPrebuilder 在 `_build_context` 之后、`agent.execute` 之前，不碰 messages |
| AC9: py_compile | — | 全部 24 文件通过 |

---

## 测试结果

```
tests/unit/test_context_prebuilder.py — 20 passed
tests/unit/test_agent_context.py — 6 passed (已有，无回归)
py_compile — 24/24 文件通过
```
