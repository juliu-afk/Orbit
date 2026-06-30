# 减熵闭环修复 — 阶段 1 PRD

> 基线：[[06-减熵体系]] 六、闭环审计 | 日期：2026-06-30
> 审计发现：8/11 项减熵功能未接入系统调用链

## 一、背景

减熵 Phase A/B/C（PR #88~#109）已将 11 项功能代码落地，但 2026-06-30 闭环审计发现：

- **5 DEAD**：BaseValidator / DependencyGuard / TestGapDetector / ClaudeMdGenerator / EditStabilityDetector 零调用方
- **3 PARTIAL**：上下文裁剪 / 模板库 / 决策日志共因——`task_keywords` 参数从未被填充，功能入口被跳过
- **3 WIRED**：简洁规则 #9 / 编排器委托 / 熔断消重正常生效

本 PRD 覆盖闭环修复全部 4 个阶段，共 4 个 PR。

## 二、阶段拆分

| Phase | PR 名 | 修复范围 | 难度 | 激活功能 |
|:--:|------|------|:--:|------|
| 闭环-1 | `feat: 减熵闭环-1——task_keywords激活B1+B3+B5` | 关键词提取 + 传参 | 低 | US-B1/B3/B5 |
| 闭环-2 | `feat: 减熵闭环-2——编辑摇摆+依赖拦截接入` | B4 接入文件修改链 + B6 接入工具执行 | 中 | US-B4/B6 |
| 闭环-3 | `feat: 减熵闭环-3——测试空洞+CLAUDE.md生成接入` | B7 接入 QA 管线 + B8 接入项目初始化 | 中 | US-B7/B8 |
| 闭环-4 | `feat: 减熵闭环-4——BaseValidator接入L1-L8` | 装饰器接入 5 个防幻觉层 | 高 | US-6 |

## 三、闭环-1：task_keywords 激活 B1/B3/B5

### 问题

`TaskRunner._run_agent()` 调用 `AgentFactory.create()` 时不传 `task_keywords`，导致：
- B1 `extract_relevant_context()` 因 `ctx.get("keywords", [])` 为空被跳过
- B3 `_build_templates_prompt()` 因 `task_keywords` 为空返回 `""`
- B5 `DecisionLog.query()`/`record()` 因 `task_keywords` 为空被跳过

### 方案

在 `TaskRunner._run_agent()` 中，从 `context["prd"]` 提取关键词，传给 `AgentFactory.create(task_keywords=keywords)`。

**关键词提取**（纯 Python，零新依赖）：对 PRD 文本做简单分词——去停用词、保留 CamelCase/snake_case 标识符、取技术名词。

### 改动范围

| 文件 | 变更 |
|------|------|
| `scheduler/task_runner.py` | `_run_agent()` 提取关键词并传参 |
| `agents/react_agent.py` | `_task_keywords` 已在构造器接受，无需改 |
| `prompt/builder.py` | 当前 `_build_context` 读取 `ctx.get("keywords")`，需对齐 |

### 验收标准

- AC-1: `TaskRunner._run_agent()` 传非空 `task_keywords` 给 AgentFactory
- AC-2: `extract_relevant_context()` 被实际调用（日志/断点确认）
- AC-3: 模板匹配日志中出现命中记录
- AC-4: 决策日志 JSONL 文件有新记录写入
- AC-5: 现有测试无回归

## 四、闭环-2：编辑摇摆 + 依赖拦截

### 问题

- `EditStabilityDetector` 无人实例化、无人调用 `record_edit()` / `check()`
- `DependencyGuard` 无人实例化、无人调用 `check()`

### 方案

**B4**：在 Agent 工具执行层（文件写入操作时）调用 `record_edit()`。在 TaskRunner 任务开始前调用 `check()`，发现高熵文件 → 标记到 context。

**B6**：在工具注册中心的包安装工具（如 `pip install` / `poetry add` executor）中，安装前调用 `DependencyGuard.check()`。

### 改动范围

| 文件 | 变更 |
|------|------|
| `tools/` 工具执行层 | 文件写入 ← `record_edit()` |
| `scheduler/task_runner.py` | 任务前 ← `check()` 高熵检测 |
| `tools/` 包管理工具 | 安装前 ← `DependencyGuard.check()` |
| `resource_guard/dependency_guard.py` | 可能需调整为同步接口 |

### 验收标准

- AC-6: Agent 修改文件后 `_history[file_path]` 有新记录
- AC-7: 高熵文件被检测时 context 中出现 `entropy_warning`
- AC-8: 包安装前 DependencyGuard 输出拦截/放行日志

## 五、闭环-3：测试空洞 + CLAUDE.md 生成

### 改动

| 文件 | 变更 |
|------|------|
| QA Agent / Review 管线 | 调用 `TestGapDetector.detect()` |
| 项目初始化 / `/goal` 入口 | 调用 `ClaudeMdGenerator.generate()` |

### 验收标准

- AC-9: QA Agent 输出含测试空洞报告
- AC-10: 新建项目后 CLAUDE.md 被自动生成

## 六、闭环-4：BaseValidator 接入 L1-L8

### 改动

5 个防幻觉层文件（l1-l8 中使用了 `if not code.strip()` guard 的）改为导入 `skip_if_empty` / `skip_if_no_sandbox` 装饰器。

### 验收标准

- AC-11: L1-L8 不再包含裸 `if not code.strip()` guard
- AC-12: 全量防幻觉测试无回归

## 七、Non-Goals

- 不新增功能模块（只接入已有代码）
- 不改变防幻觉判定逻辑
- 不改变 Agent 行为逻辑
- 不引入新外部依赖

## 八、整体验收

| # | 标准 | 测量 |
|---|------|------|
| ALL-1 | 11/11 减熵功能可追踪到实际调用 | grep 确认每项 ≥1 调用方 |
| ALL-2 | 现有测试无回归 | pytest 全绿 |
| ALL-3 | 每 Phase 独立可合 | 独立 PR，独立 CI |
