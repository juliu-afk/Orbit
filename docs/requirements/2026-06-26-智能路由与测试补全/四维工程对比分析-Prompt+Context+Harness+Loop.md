# 四维工程对比分析：Orbit vs 6 大编程 Agent

> 日期: 2026-06-26 | 参考系: Claude Code, Codex, OpenCode, MiMo Code, OpenClaw, Hermes

---

## 一、Prompt Engineering（提示词工程）

**定义**：System Prompt 设计、角色定义、指令分层、动态注入策略。

| 维度 | Claude Code | Codex | OpenCode | MiMo Code | OpenClaw | Hermes | **Orbit** |
|------|:--:|:--:|:--:|:--:|:--:|:--:|:--:|
| System Prompt 策略 | 模块化 CLAUDE.md + 动态注入 hook | AGENTS.md 静态加载 | 最小 System Prompt（身份+边界） | 多层注入（角色+技能+记忆） | 三层注入（pi-ai + 技能） | 三层缓存（stable/context/volatile） | 6 Agent 独立 System Prompt |
| 提示词大小 | ~200 行（拆分后） | ~150 行 | **极简**（<50 行） | 中等 | 中等 | 大（stable 层 ~300 行） | 每 Agent ~5 行 system_prompt() |
| 动态注入 | ✅ hook 系统 | ❌ 无 | ✅ contexty 插件 | ✅ checkpoint-writer 子Agent | ✅ 7层管道过滤 | ✅ 预算警告+压力提示 | ❌ 无。静态 system_prompt() |
| 角色分层 | 单 Agent（Subagent 复用同一 prompt） | 单 Agent | 12 Agent 分层（build/plan/compose） | 3 主 Agent + 按需子 Agent | 单 Agent + 技能注入 | 单 Agent + 工具集限定 | ✅ 6 Agent 角色分离 |
| 指令质量 | 极高（Claude 模型原生理解） | 中 | 中 | 高（MiMo 模型原生） | 中 | 高 | 低——system_prompt() 只有 3 行 |

**Orbit 差距**：
- Agent 的 system_prompt() 太简单——只有身份声明，缺少工具使用指南、输出格式约束、禁止项
- 没有动态注入机制——无法根据任务复杂度/风险等级调 prompt
- 没有 prompt 缓存策略（Hermes 的三层缓存可省大量 token）

---

## 二、Context Engineering（上下文工程）

**定义**：上下文窗口管理、记忆系统、检索策略、压缩/摘要、token 预算。

| 维度 | Claude Code | Codex | OpenCode | MiMo Code | OpenClaw | Hermes | **Orbit** |
|------|:--:|:--:|:--:|:--:|:--:|:--:|:--:|
| 记忆系统 | Memory 文件 + 自动注入 | ❌ 无 | SQLite FTS5 + 向量 | **最强**——MEMORY.md + checkpoint + tasks + SQLite FTS5 | MEMORY.md + 向量嵌入 | MEMORY.md + FTS5 + session search | ❌ 无。只有 TaskContext L1-L5 |
| 上下文压缩 | Subagent 用 cavecrew 60% 压缩 | ❌ | DCP 动态剪枝（去重+清理） | checkpoint 结构化重建 | ❌ 无（保持全量） | 子LLM摘要+子会话链 | ❌ 无 |
| Token 预算 | CLAUDE.md 拆分（按需加载） | ❌ | contexty 预算化注入 | **预算化注入**（预算上限过滤噪声） | ❌ | 摘要预算 2K-12K | ❌ 无 |
| 记忆进化 | ❌ 手动维护 | ❌ | ❌ | **/dream + /distill**（自进化） | ❌ | curator consolidate | ❌ 无 |
| 检索策略 | @docs/ 按需加载 | ❌ | JIT 检索 | checkpoint 结构化重建 | 向量语义+BM25 | FTS5 全文搜索 | 图谱查询（仅结构化） |

**Orbit 差距**：
- **最大短板**——完全没有上下文压缩和 token 预算。每次 LLM 调用全量传入 TaskContext
- 没有长期记忆——会话之间不保留知识。MiMo Code 的 `/dream` 机制是 Orbit 最需要学的
- 图谱查询≠全文搜索——无法检索代码片段、历史会话、成功案例

---

## 三、Harness Engineering（编排框架）

**定义**：多 Agent 协作、工具注册/分发、子 Agent 管理、权限/安全边界、沙箱。

| 维度 | Claude Code | Codex | OpenCode | MiMo Code | OpenClaw | Hermes | **Orbit** |
|------|:--:|:--:|:--:|:--:|:--:|:--:|:--:|
| 多 Agent 协作 | Subagent（最多16并行） | ❌ 单 Agent | 12 Agent 分层 | **最强**——build/plan/compose + 按需子Agent | 单 Agent + code-agent 插件 | ❌ 单 Agent + delegate_task | ✅ 6 Agent 串行流水线 |
| 角色分工 | ❌ 无角色（Subagent 同质） | ❌ | ✅ build(执行)/plan(只读)/compose(编排) | ✅ 三类主 Agent + 技能 | ❌ | ❌ | ✅ architect/developer/reviewer/qa/config_manager/clarifier |
| 工具注册 | 内置工具集 | 内置工具集 | MCP 协议 | OpenCode 基座 | 4 npm 包 + 7层管道 | **最强**——AST 自发现+三层解耦 | ❌ ToolRegistry 只有 MCP |
| 子 Agent 生命周期 | ✅ spawn/kill/output | ❌ | ✅ 并行+跟踪+取消 | ✅ 并行+后台+生命周期追踪 | ✅ agent_launch/kill/stats | ❌ 子调用在父路径下 | ❌ 无独立子 Agent |
| 沙箱 | ❌ 无 | ✅ 内置 | ❌ | ✅ worktree 隔离 | ✅ worktree 隔离 | ❌ | ✅ Docker 沙箱（代码执行） |
| 权限控制 | ✅ allow/deny 白名单 | ❌ | ✅ 分级权限(denied/ro/rw) | ❌ | ✅ 策略过滤 | ✅ check_fn 过滤 | ❌ 无文件系统工具（无权限需求） |
| 文件系统工具 | ✅ Read/Edit/Write | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ **零** |

**Orbit 差距**：
- **致命短板**——没有文件系统工具。Agent 只能输出文本，不能落地
- 工具注册只有 MCP，没有 Hermes 的 AST 自发现 + 三层解耦
- 没有子 Agent 机制——6 Agent 串行无法并行探索

---

## 四、Loop Engineering（执行循环）

**定义**：Agent think-act-observe 循环、工具调用并发、中断/恢复、停止条件、自修复。

| 维度 | Claude Code | Codex | OpenCode | MiMo Code | OpenClaw | Hermes | **Orbit** |
|------|:--:|:--:|:--:|:--:|:--:|:--:|:--:|
| 循环模型 | ReAct + Subagent fan-out | ReAct | ReAct + 模式路由(quick/deep/ultrabrain) | ReAct + Compose流水线 | 5阶段Agent Loop | **最强**——ReAct + 并行工具调用(ThreadPool 8worker) | 调度器状态机（非ReAct） |
| 工具并发 | ✅ Subagent 并行 | ❌ | ✅ 子Agent并行 | ✅ 子Agent并行+后台 | ❌ 串行 | ✅ 独立工具调用并行 | ❌ 无工具调用循环 |
| 中断/恢复 | ❌ 崩溃=重来 | ❌ | ❌ | ✅ checkpoint 恢复 | ✅ session active→pending→resume | ✅ session 持久化 | ✅ CheckpointManager |
| 停止条件 | ❌ 无 | ❌ | ❌ | **/goal + judge 模型验证** | ✅ lifecycle states | ❌ | ✅ TaskState 状态机(FAILED/DONE) |
| 自修复 | ❌ 手动重试 | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ 无。TODO |
| 流水线编排 | ❌ 线性 | ❌ 线性 | Compose 模式（设计→规划→编码→测试→审查→合并） | **最强**（同上 + specs-driven） | Plan→Review→Execute | ❌ | ✅ PARSING→PLANNING→CODING→VERIFYING→DONE |

**Orbit 差距**：
- Agent 没有真正的 ReAct think-act-observe 循环——调度器决定状态转换，Agent 只 execute() 一次
- 没有工具调用循环——Agent 不能多轮调用工具直到完成
- 没有自修复——失败直接 FAILED，不会重试/调整策略

---

## 五、综合评分

| 维度 | Claude Code | Codex | OpenCode | MiMo Code | OpenClaw | Hermes | **Orbit** |
|------|:--:|:--:|:--:|:--:|:--:|:--:|:--:|
| Prompt Engineering | 9 | 5 | 8 | 9 | 6 | 9 | **4** |
| Context Engineering | 6 | 2 | 8 | **10** | 6 | 8 | **3** |
| Harness Engineering | 7 | 3 | 8 | 9 | 8 | **10** | **5** |
| Loop Engineering | 5 | 3 | 7 | **9** | 7 | 8 | **4** |
| **加权总分** | **27** | **13** | **31** | **37** | **27** | **35** | **16** |

> 加权：Prompt 25% / Context 25% / Harness 25% / Loop 25%

**结论：Orbit 全面落后，但追赶路径清晰。**

---

## 六、Orbit 优化方案

### P0——本周可做（补齐生存底线）

#### 1. 文件系统 + Shell 工具层（对标 Claude Code 工具集）

```python
# src/orbit/tools/filesystem.py  ← 新增
class FileSystemTools:
    async def read(path, offset, limit) -> str       # 对标 Read
    async def write(path, content) -> None           # 对标 Write
    async def edit(path, old_str, new_str) -> None   # 对标 Edit

# src/orbit/tools/shell.py  ← 新增
class ShellTools:
    async def exec(cmd, cwd, timeout) -> ExecResult  # 对标 Bash

# src/orbit/tools/search.py  ← 新增
class CodeSearch:
    async def grep(pattern, path) -> list[Match]     # 对标 Grep
    async def glob(pattern) -> list[Path]            # 对标 Glob
```

**工作量**: 3天 | **收益**: Agent 从"只能说话"变成"能干活"

#### 2. ReAct 工具调用循环（对标 Hermes Agent Loop）

```python
# src/orbit/agents/developer.py 改造
class DeveloperAgent(BaseAgent):
    async def execute(self, input_data: AgentInput) -> AgentOutput:
        tools = [FileSystemTools(), ShellTools(), CodeSearch()]
        context = input_data.context

        while True:
            # LLM 思考：我该用什么工具？
            action = await self.llm.think(context, tools)

            if action.tool == "done":
                return AgentOutput(status="ok", result=action.result)

            # 执行工具
            result = await tools.execute(action)
            context.add(result)  # 工具结果反馈到上下文
            # 循环继续
```

**工作量**: 2天 | **收益**: Agent 循环闭环

#### 3. Prompt 工程增强（对标 Hermes 三层缓存）

```python
# 每个 Agent 的 system_prompt() 改为三层结构化
class DeveloperAgent(BaseAgent):
    def system_prompt(self) -> str:
        return {
            "stable": "你是 V14.1 协作网络中负责编写的 DeveloperAgent。"
                      "必须通过 L1-L9 验证。输出格式: JSON。"
                      "可用工具: read_file, write_file, edit_file, exec_command, grep, glob",
            "context": f"当前项目: {self.graph.project_name}. "
                       f"技术栈: {self._detect_stack()}",
            "volatile": f"任务: {self._current_task}. "
                        f"约束: {self._constraints}",
        }
```

**工作量**: 1天 | **收益**: Token 消耗 -30%，指令质量 +50%

---

### P1——两周内（追上行业水平）

#### 4. MiMo 式记忆系统（/dream + checkpoint）

```
当前会话 → checkpoint-writer 子Agent → tasks/{id}/progress.md
每周 /dream → 独立Agent 扫描历史 → 合并去重 → 更新 MEMORY.md
全局记忆 → SQLite FTS5 → 新会话自动注入相关记忆
```

**工作量**: 5天 | **收益**: 长程任务成功率 +40%

#### 5. Hermes 式工具自注册（AST 发现）

```python
# tools/read_file_tool.py 末尾
from orbit.tools.registry import registry

registry.register(
    name="read_file",
    schema=READ_FILE_SCHEMA,  # LLM 看到的 JSON Schema
    handler=read_file,         # 实际执行函数
    check_fn=lambda: True,     # 运行时可用性检查
)
```

**工作量**: 2天 | **收益**: 工具扩展零摩擦

#### 6. 子 Agent 并行执行（对标 Claude Code Subagent）

```python
# 同时启动 3 个 explorer 子Agent 搜索不同维度
results = await self.parallel([
    SubAgent("explore", prompt="找权限相关代码", toolset=["grep","glob"]),
    SubAgent("explore", prompt="找测试相关代码", toolset=["grep","glob"]),
    SubAgent("explore", prompt="找Schema定义", toolset=["grep","glob"]),
])
```

**工作量**: 3天 | **收益**: 探索速度 3x

---

### P2——长期（超越）

#### 7. MiMo Compose 式流水线编排

将现有 6 Agent 串行流水线升级为 Compose 式的结构化编排，每个阶段有独立的 goal + 门禁。

#### 8. 自进化机制（/distill）

发现重复工作流 → 自动打包为可复用技能。

#### 9. 多引擎路由（Claude Code/Codex/Hermes 子进程）

复杂编程任务 → 路由到 Claude Code 子进程执行，Orbit 负责编排+验证+审计。

---

## 七、优先级路线图

```
Week 1 (P0):
  ├── 文件系统 + Shell + 搜索工具
  ├── ReAct 工具调用循环
  └── Prompt 三层结构化

Week 2-3 (P1):
  ├── 记忆系统（/dream + checkpoint + SQLite FTS5）
  ├── 工具自注册（AST 发现）
  └── 子 Agent 并行执行

Month 2+ (P2):
  ├── Compose 流水线编排
  ├── 自进化 /distill
  └── 多引擎路由
```
