# 阶段1 PRD — Step 4.2 防幻觉层 L5-L8

> 基线来源：`docs/PRD+ADR_4阶段.md` Step 4.2 章节（PRD + ADR 已定稿）。
> 承接 Step 4.1（L1-L4 已交付 v0.6.0），本批次交付 L5-L8 深度验证层。

## 背景

L1-L4 覆盖语法/引用/熵/类型四层防御，但无法验证算法正确性（L5）、接口一致性（L6）、运行时行为（L7）和环境一致性（L8）。L5-L8 构成深度防御——正确性、契约、运行态、配置四维度。

## 用户故事

| 优先级 | 故事 |
|--------|------|
| P0 | 作为 QA Agent，我调用 L5-L8 对最终代码进行深度验证；L5 对 @formal 函数做 Z3 证明，L6 校验 API 契约，L7 沙箱运行测试，L8 检测配置漂移 |
| P1 | 作为运维，L8 在 Test 环境自动修复配置漂移，Prod 环境仅告警 |
| P1 | 作为开发者，L5 超时 30s 后标记 unknown（不阻断流水线），人工介入 |

## 验收标准

| # | 验收标准 | 对应层 |
|----|---------|--------|
| AC1 | `@formal def add(x,y): return x+y` → Z3 返回 unsat（无反例），passed=True | L5 |
| AC2 | `@formal def identity(x): return x` + `@ensures("result > x")` → Z3 返回 sat（有反例），passed=False | L5 |
| AC3 | OpenAPI 定义 `/users/{id}` 返回 `User` 模型，但实现返回 `dict` → L6 捕获响应类型不匹配 | L6 |
| AC4 | 生成代码 `assert add(1,2) == 4` → 沙箱执行 AssertionError → L7 标记失败 | L7 |
| AC5 | 手动改 `.env` 中 `DB_PORT` → 10min 内 L8 检测并回滚至基线 SHA | L8 |

## 范围

**Do:**
- L5 支持排序/数学运算等纯函数（标记 @formal）
- L6 支持 OpenAPI 3.0 YAML/JSON
- L7 复用 Sandbox（MVP-03）+ pytest 风格断言
- L8 支持 .env / YAML / JSON / TOML / .ini 5 种格式
- L5 30s 超时 → unknown（不阻断）
- L8 Test 自动修复，Prod 仅告警

**Don't:**
- L5 不验证 IO/复杂循环（超时风险）
- L6 不支持 gRPC 契约
- L8 不支持 K8s ConfigMap（V2）

## 边缘情况

| 场景 | 预期行为 |
|------|---------|
| 函数未标记 @formal | L5 跳过，返回 passed=True + z3_status="skipped" |
| @formal 函数无 precondition | 仅验证 postcondition 的反例存在性 |
| Z3 30s 超时 | 返回 passed=True + z3_status="timeout" + warning |
| OpenAPI spec 文件不存在 | L6 返回 passed=False，errors 含文件路径 |
| 沙箱不可用 | L7 跳过，passed=True + warning |
| 配置基线目录为空 | L8 返回空列表（无基线→无漂移） |
| 两个文件 hash 相同但格式不同 | 规范化后 hash（YAML 键序/JSON 格式化） |
| Prod 环境检测到漂移 | L8 仅告警不修复，auto_fixed=False |

## 已决议问题

| 问题 | 决议 |
|------|------|
| Q1: Z3 超时 | 30s 硬超时，标记 unknown，不阻断 |
| Q2: L8 自动修复审批 | Test 自动修复，Prod 仅告警 |
| Q3: L6 异步合约 | 支持 async 解析大文件 |

## 新增依赖

- `z3-solver >= 4.13.0` — L5 Z3 SMT 求解器
- `openapi-spec-validator >= 0.7` — L6 OpenAPI 校验
- `prance >= 0.22` — L6 OpenAPI 解析（支持 swagger→openapi 转换）
- `deepdiff >= 6.7` — L8 配置 diff
- `pyyaml >= 6.0` — L8 YAML 解析

---

> 阶段1 PRD 基线：基于 `docs/PRD+ADR_4阶段.md` Step 4.2，验收标准 5 条，边缘 8 类，已决议 3 项。
