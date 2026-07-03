---
project: Orbit
version: 0.1.0
stage: MVP
anchor_layer: orchestration  # V14.1 锚定编排层（Step 0.4 架构锚定声明）
metrics:
  max_schedule_latency_ms: 1500        # 调度层延迟（不含验证层），预警线 1200ms
  hallucination_rate_threshold: 0.03   # 幻觉率 < 3%
  ci_coverage_gate: 0.80               # CI 覆盖率门禁
  # max_tokens_per_task 字段保留供后续阶段启用；
  # 当前阶段（Step 0-1）不作为 CI 硬门禁，仅记录。
scope_in:
  - code_graph
  - database_graph
  - config_graph
  - scheduler_state_machine
  - hallucination_layers_L1_L8
  - sandbox_execution
scope_out:
  - time_series_graph                 # 时序图谱留待 V2
  - multi_cluster_federation          # 生产阶段才考虑
raci:
  R: 开发组
  A: 技术负责人
  C: 架构评审会
  I: 业务方
risks:
  - id: R-001
    desc: LLM 返回非结构化输出，防幻觉层全部漏判
    severity: high
    mitigation: Pydantic 结构化 + L1 校验 + 熔断回滚
  - id: R-002
    desc: 调度器状态机死锁，检查点无法回滚
    severity: high
    mitigation: 每状态转换写检查点，回滚路径单元测试覆盖
  - id: R-003
    desc: 三图谱 SQLite 并发写冲突
    severity: medium
    mitigation: WAL 模式 + 写串行化
  - id: R-004
    desc: 沙箱执行逃逸，LLM 生成代码污染宿主
    severity: high
    mitigation: Docker 隔离 + 资源限制 + 网络隔离
  - id: R-005
    desc: 编排层与执行层定位混淆，Prompt 退化为单智能体风格
    severity: medium
    mitigation: Step 0.4 架构锚定声明作为评审硬性检查项
---

# Orbit 项目章程

> 本文件是后续所有架构决策的"宪法"，争议时以此为准。
> 发布日期：2026-06-22 ｜ 状态：定稿

## 1. 战略定位

Orbit 是**多智能体软件开发自循环系统**，锚定在**编排层**（Step 0.4），不是单智能体执行工具。
核心价值：治理——通过多 Agent 协作 + 状态机调度 + 三图谱 + 8 层防幻觉 + 审计链，实现对开发流程的系统性治理。

## 2. 度量基线

| 指标 | 目标 | 测量方法 | 当前状态 |
|---|---|---|---|
| 调度层延迟 | ≤1500ms（预警 1200ms） | Prometheus Histogram `orbit_scheduling_latency_seconds` | 已仪表化 |
| 幻觉率 | <3% | Prometheus Counter `orbit_hallucination_validations_total` | 已仪表化 |
| CI 覆盖率 | ≥80% | pytest-cov 报告 | 已实现（CI `--cov-fail-under=80`） |
| 单任务 Token | ≤35（设计目标） | LiteLLM usage 字段统计 | **暂缓**——先跑通闭环，不作 CI 硬门禁 |

## 3. 范围

**In**：三图谱（代码/数据库/配置）、调度器状态机、防幻觉层 L1-L8、沙箱执行、审计链。
**Out**：时序图谱（V2）、多集群联邦（生产阶段）。

## 4. RACI

| 角色 | 职责 |
|---|---|
| R（执行）开发组 | 编码、测试、文档 |
| A（批准）技术负责人 | 架构决策、合并批准 |
| C（咨询）架构评审会 | PRD/技术方案评审 |
| I（知会）业务方 | 进度同步 |

## 5. 风险登记册

见 frontmatter `risks` 字段（5 条），CI 可解析。

## 6. 架构锚定声明（Step 0.4）

所有 Prompt/Context 设计必须服务于**协作流程的编排与治理**，而非单次代码生成质量。
评审时若发现 Prompt 退化为"你是一个 Python 专家"等执行层风格，直接打回。