# 阶段1 PRD — Step 4.1 防幻觉层 L1-L4

> 基线来源：`docs/PRD+ADR_4阶段.md` Step 4.1 章节（PRD + ADR 已定稿）。
> 本 PRD 提取核心验收标准，作为阶段2方案和阶段4测试的追溯基线。

## 背景

LLM 生成代码常见幻觉：引用不存在的函数、类型错误、高不确定性输出。单层防御不可靠，必须纵深拦截。

L1-L4 覆盖生成全链路：
- **生成后**：L1 图谱引用验证（代码中符号是否在代码图谱中存在）
- **运行时**：L2 动态追踪（沙箱执行时 `sys.settrace` 追踪实际调用）
- **生成中**：L3 概率熵监控（LLM 流式输出 logprobs 熵值检测）
- **生成前/后**：L4 静态类型检查（mypy --strict）

## 用户故事

| 优先级 | 故事 |
|--------|------|
| P0 | 作为调度器，我调用 `HallucinationPipeline` 对生成代码执行 L1-L4 检查，任一失败则拒绝代码 |
| P1 | 作为运维，我在 Dev 环境启用 L1/L4，Test 环境全量启用 L1-L4，Prod 仅启用 L1/L4 |
| P1 | 作为开发者，L3 对不支持 logprobs 的模型自动降级为重复度检测 |

## 验收标准

| # | 验收标准 | 对应成功标准 |
|----|---------|-------------|
| AC1 | 注入引用不存在符号 `Utils.foo` 的代码，L1 拦截并返回 `GraphReferenceError` | SC1: L1 拦截率 >95% |
| AC2 | 模拟高熵生成流（窗口均值 ≥0.75），系统在 200ms 内取消请求并抛出 `HighEntropyError` | SC2: L3 响应 <200ms |
| AC3 | 生成类型错误代码 `def add(a: str, b: str) -> int: return a + b`，L4 捕获类型不匹配 | SC3: L4 准确率 >90% |
| AC4 | 代码使用 `getattr(obj, method_name)()` 动态调用，沙箱运行时 L2 追踪实际调用函数并验证 | SC4: L2 动态追踪生效 |

## 范围

**Do:**
- Dev 启用 L1/L4，Test 全量 L1-L4
- L3 不支持 logprobs 时降级为重复度评估
- L1 仅验证静态符号，动态属性（`obj['field']`）跳过
- L4 使用 `--strict` 但忽略 `no-untyped-def`

**Don't:**
- L2 仅 Test/Prod 启用（性能开销 ~200ms）
- L3 不启用旧模型（无 logprobs 返回）
- 不支持 Python 以外的语言（JS/TS 留待 V2）

## Non-Goals

- 不覆盖 L5-L8（形式化验证/合约/沙箱执行/配置漂移）—— 那是 Step 4.2
- 不实现跨语言验证（Tree-sitter JS/TS 解析器留待 V2）
- 不在此批次实现 `HallucinationPipeline` 统一编排（在 Step 5.1 调度器 DAG 中完成）

## 边缘情况

| 场景 | 预期行为 |
|------|---------|
| 代码为空字符串 | L1/L4 跳过（无符号可验证），返回 passed=True |
| LLM 模型不支持 logprobs | L3 降级为文本重复度检测，记录 warning |
| mypy 未安装或执行失败 | L4 返回 passed=False，errors=["mypy execution failed: ..."] |
| 代码图谱查询超时 | L1 返回 passed=False，errors=["Graph query timeout"] |
| 高熵窗口未满（<10 个采样） | L3 不触发，等待窗口填满 |
| 沙箱不可用 | L2 跳过，记录 warning |
| AST 解析失败（语法错误代码） | L1 返回 passed=False，errors 包含语法错误详情 |

## 已决议问题

| 问题 | 决议 |
|------|------|
| Q1: L3 熵阈值模型级配置 | DeepSeek 0.75, Qwen 0.70，配置在 `MODEL_ENTROPY_THRESHOLD` |
| Q2: L4 是否强制 `--strict` | 是，但忽略 `no-untyped-def` |
| Q3: L1 对动态属性处理 | 仅验证静态符号，动态属性跳过 |

## 与已有模块的关系

```
调度器（已有）──调用──→ HallucinationPipeline（本批次新增）
                        ├── L1GraphValidator ──→ GraphRepository（已有）
                        ├── L2DynamicTracer ──→ Sandbox（已有）
                        ├── L3EntropyMonitor ──→ LLMClient（已有 gateway）
                        └── L4TypeValidator ──→ mypy（subprocess）
```

## 依赖

- **已有**：GraphRepository（Step 1.2）、Sandbox（MVP-03）、LLM Gateway（Step 2.1）
- **新增外部**：mypy 1.8+（需 `poetry add mypy`，阶段2方案确认后安装）
- **新增内部**：`src/orbit/hallucination/` 包（4 文件 + pipeline）

---

> 阶段1 PRD 基线确认：基于 `docs/PRD+ADR_4阶段.md` Step 4.1，验收标准 4 条，边缘 7 类，已决议问题 3 项，无偏离。
