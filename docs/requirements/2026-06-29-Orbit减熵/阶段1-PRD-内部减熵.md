# Orbit 内部代码减熵——阶段 1 PRD

> 基线文档：[[06-减熵体系]] | 日期：2026-06-29
> 关联文档：[[阶段2-技术方案-内部减熵]]

## 一、背景

Orbit 经 7 阶段快速迭代后，27 个模块 180+ .py 文件中累积了典型快速开发的"代码熵"：

- **重复实现**：CircuitBreaker 在 `gateway/` 和 `resource_guard/` 各实现一次
- **重复模块**：ClarifierAgent 和 ClarificationEngine 做同一件事
- **上帝类**：SchedulerOrchestrator 697 行管 7 种职责
- **空目录占坑**：5 个只有 0 字节 `__init__.py` 的空包
- **循环依赖风险**：orchestrator 有 5 个 TYPE_CHECKING + 4 个惰性导入
- **模板重复**：5 个防幻觉层都有相同的 "empty code, skipped" guard

这些熵不致命，但持续累积会拖慢迭代速度、增加认知负荷、让新人难理解。

**目标**：在不破坏功能的前提下，系统性消除以上熵源。核心原则——**删掉的行数 > 新增的行数**。

## 二、用户故事

### P0 故事

| ID | 故事 | 验收标准 |
|----|------|---------|
| US-1 | 作为维护者，我不希望两个地方有相同的熔断逻辑，改一处忘记另一处就会出 bug | ResourceGuard 通过组合使用 gateway.CircuitBreaker，不再有自己的熔断状态机 |
| US-2 | 作为维护者，我不希望两个模块做同一件事而有不同的实现细节和 bug 修复 | 删除 agents/clarifier.py 或 scheduler/clarifier.py 之一，只留一个 |

### P1 故事

| ID | 故事 | 验收标准 |
|----|------|---------|
| US-3 | 作为新开发者，我希望 SchedulerOrchestrator 拆成可独立理解的小类 | TaskRunner + DagRunner 各自 ≤300 行 |
| US-4 | 作为探索代码库的人，我不希望看到一堆空目录 | 5 个空目录删除或填内容 |

### P2 故事

| ID | 故事 | 验收标准 |
|----|------|---------|
| US-5 | 作为模块维护者，我希望依赖关系是单向的，不需要 TYPE_CHECKING 欺骗 | 消除 scheduler 包的惰性导入 |
| US-6 | 作为防幻觉层开发者，我希望修改 guard 逻辑时只改一处 | 抽取 base validator 的 `skip_if_empty` / `skip_if_no_sandbox` 装饰器 |

## 三、范围

**Do**：
- 消重 CircuitBreaker（删除 ResourceGuard 内嵌熔断）
- 消重 Clarifier（二选一）
- 拆 SchedulerOrchestrator 为 TaskRunner + DagRunner
- 删除/填充 5 个空目录
- 防幻觉层 guard 代码抽基类
- 画依赖图，提议断环方案

**Don't**：
- 不改变任何外部 API 契约
- 不新增功能/模块
- 不改变调度器状态机的行为逻辑
- 不改变防幻觉层判定逻辑
- 不做大型重构（如全面改用另一种架构模式）

## 四、Non-Goals

- 不做性能优化（除非伴随熵消除自然产生）
- 不改变测试框架或测试策略
- 不引入新的外部依赖
- 不重写任何与本次减熵无关的模块

## 五、边缘情况

| 场景 | 预期行为 |
|------|---------|
| 删除 agents/clarifier.py 后发现其他模块导入它 | grep 全量确认后删除导入，CI 验证 |
| Orchestrator 拆分类后状态迁移测试失败 | 保留原有测试，确保新类对原有接口兼容 |
| 空目录有隐式副作用（如 pyinstaller hiddenimports） | 逐个检查 `orbit.spec` 和构建脚本 |
| 防幻觉 guard 抽取后某层行为差异 | 每层独立单元测试，确保 ValidationResult 输出不变 |
| 循环依赖切断后某模块找不到引用 | 用 protocol/抽象基类替代直接导入 |

## 六、验收标准

| ID | 标准 | 测量方法 |
|----|------|---------|
| AC-1 | ResourceGuard 不再有独立的熔断状态机 | grep `_failure_count.*>=` resource_guard.py 返回空 |
| AC-2 | 只存在一个 Clarifier 实现 | `find src/orbit -name "clarifier.py"` 只返回 1 个文件 |
| AC-3 | Orchestrator 拆后全量回归通过 | `pytest tests/ -q` exit 0 |
| AC-4 | 5 个空目录全部处理 | `find src/orbit/api/dependencies src/orbit/graph/schemas src/orbit/graph/models src/orbit/core src/orbit/infrastructure -type f` 不再只有 `__init__.py` |
| AC-5 | 防幻觉层 guard 不重复 | 5 个 layer 文件中不再出现 `if not code.strip()` |
| AC-6 | 代码行数净减少 | `git diff --stat main...HEAD` 总删除 > 总新增 |
| AC-7 | 覆盖率不降 | `pytest --cov=src/orbit --cov-fail-under=80` 通过 |

## 七、待确认问题

| # | 问题 | 默认答案 |
|---|------|---------|
| Q1 | Clarifier 保留哪个——agents 还是 scheduler？ | 保留 scheduler/clarifier.py（ClarificationEngine），它更完整且被 orchestrator 直接调用 |
| Q2 | Orchestrator 拆到什么粒度？ | TaskRunner（单任务）+ DagRunner（DAG 编排）。CheckpointManager 已独立存在。 |
| Q3 | 空目录是删还是填？ | 逐个判断。api/dependencies/、infrastructure/ 删除。graph/schemas/、graph/models/ 填入已存在的 models/nodes.py 的迁移。core/ 删除。 |
