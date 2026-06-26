## 目录

 
- 1. V14.1 五层上下文架构回顾
- 2. 开源项目对比与优化机会
- 3. 具体优化方案
- 4. 实施路线图与优先级
- 5. 代码示例

 

---

 

## 1. V14.1 五层上下文架构回顾

 
V14.1将上下文视为稀缺的战略资源，设计了五层分级架构：

 | 层级 | 名称 | 内容 | 访问方式 | Token策略 |
| --- | --- | --- | --- | --- |
| L1 | 全局不可变上下文 | System Prompt、硬性规则、Agent角色定义 | 每次LLM调用自动注入 | 固定开销（~2K tokens/Agent） |
| L2 | 确定性事实上下文 | 三图谱查询结果 | Agent主动调用 `query_graph()` | 按需加载（查询零Token，结果入窗口） |
| L3 | 任务动态上下文 | PRD摘要、历史步骤、检查点摘要 | 调度器状态转换时注入 | 动态窗口（滑动窗口，保留最近3步） |
| L4 | Agent局部工作记忆 | 思考→行动→观察循环中间产物 | Agent私有，不跨Agent共享 | 循环内复用 |
| L5 | 跨任务长期记忆 | 教训库、成功模式库 | RAG检索注入 | 按需检索（相似度>0.8时注入） |

 

---

 

## 2. 开源项目对比与优化机会

 

### 2.1 Agentic Context Engineering (ACE) —— 上下文增量学习

 
核心思想：斯坦福与SambaNova提出将Prompt视为“可演化的剧本”。三个角色：Generator执行任务、Reflector诊断轨迹提取教训、Curator合并教训为增量子弹。关键洞察：传统Prompt优化器存在简洁性偏差（迭代优化趋于泛化）和上下文崩溃（整体重写会缩减小心的上下文）。

 | 维度 | V14.1现有设计 | ACE可借鉴点 |
| --- | --- | --- |
| L5长期记忆 | 仅检索相似历史教训 | 可演化的“子弹”式增量知识（带使用次数、时间戳、来源工具） |
| 经验更新 | 静态存储，不随时间演化 | Reflector + Curator形成闭环，经验持续精炼 |
| 去重机制 | 无 | FAISS语义去重 |

 

### 2.2 Architext —— 上下文工程框架

 
核心思想：将上下文构建从“零散的字符串拼接”提升为“可操作、可组合、可演化的工程实体”。核心特性：Provider驱动的动态内容生成、列表式增删改查操作、可见性开关控制、智能缓存。

 | 维度 | V14.1现有设计 | Architext可借鉴点 |
| --- | --- | --- |
| 上下文构建 | Prompt模板+字符串拼接 | 声明式Provider对象，动态按需渲染 |
| 上下文操作 | 静态组装 | 运行时pop/insert/append/slice操作 |
| 可见性控制 | 无 | Provider.visible开关，保留但不渲染 |
| 缓存机制 | 无 | 内容变更时才刷新，否则复用缓存 |

 

### 2.3 Observational Memory（Mastra）—— 双Agent背景压缩

 
核心思想：使用Observer和Reflector两个背景Agent将对话历史压缩为带时间戳的观察日志。Observer在消息达30K tokens时压缩历史，Reflector在观察达40K tokens时重组浓缩。关键优势：稳定的上下文窗口可充分利用Prompt缓存，Token成本降低最高10倍。

 | 维度 | V14.1现有设计 | Observational Memory可借鉴点 |
| --- | --- | --- |
| L3压缩策略 | 滑动窗口+二次摘要 | 双Agent按阈值触发压缩，格式为文本观察 |
| 缓存利用 | 无 | 稳定上下文窗口可最大化Prompt缓存命中 |
| 压缩触发 | 固定步数 | 基于Token阈值（可配置） |

 

### 2.4 LangChain Deep Agents —— 三层压缩技术

 
核心思想：Deep Agents SDK实现三层压缩：① Offloading大工具结果（>20K tokens时替换为文件路径引用+前10行预览）；② Offloading大工具输入（上下文超85%时替换为文件指针）；③ Summarization（生成结构化摘要，包含session_intent、artifacts、next_steps）。主动压缩可在上下文仅达10-20%时就触发。

 | 维度 | V14.1现有设计 | Deep Agents可借鉴点 |
| --- | --- | --- |
| 大工具结果 | 全量保留在上下文 | 超阈值自动offload到文件系统，仅留引用+预览 |
| 压缩触发时机 | 接近窗口满时 | 可配置阈值（10-20%即触发） |
| 摘要结构化 | 纯文本摘要 | 包含session_intent、artifacts、next_steps的字段化摘要 |

 

### 2.5 OpenViking —— 三层分级上下文加载

 
核心思想：将上下文管理建模为“文件系统”，采用L0/L1/L2三层分级结构按需加载。L0热数据（当前会话）、L1温数据（近期历史）、L2冷数据（长期存储），通过目录递归检索组合定位与语义搜索。支持可视化检索轨迹，便于调试。

 | 维度 | V14.1现有设计 | OpenViking可借鉴点 |
| --- | --- | --- |
| 上下文分级 | 五层但未明确冷热 | L0/L1/L2明确定义，按需逐级加载 |
| 检索可视化 | 仅审计日志 | 可视化检索轨迹，便于调试 |
| 自动压缩 | 手动触发 | 自动压缩对话内容、提取长期记忆 |

 

### 2.6 ContextPilot —— 上下文缓存复用

 
核心思想：上下文工程层的优化系统。智能上下文复用提升前缀缓存命中率、支持多种RAG库和推理引擎。测试数据：MultihopRAG上F1=64.68%（对比SGLang的64.15%），缓存命中率提升4-13倍，预填充延迟降低1.5-3.5倍，GPT-5.2测试中输入Token成本降低约36%。

 | 维度 | V14.1现有设计 | ContextPilot可借鉴点 |
| --- | --- | --- |
| 上下文缓存 | 无 | 智能前缀缓存复用 |
| 跨请求共享 | 无 | 多请求共享重叠上下文时最大化复用 |
| 成本优化 | 无 | 输入Token成本降低36% |

 

---

 

## 3. 具体优化方案

 

### 3.1 优化一：L5长期记忆升级为ACE增量知识库

 | PRD · ACE增量知识库 |
| --- |
| 目标 | 将L5从“静态教训库”升级为“可演化的增量知识库” |
| 核心机制 | ① Generator：执行任务，输出代码和决策轨迹。
 ② Reflector：诊断失败/成功原因，提取可复用的“子弹”（带使用次数、时间戳、来源工具）。
 ③ Curator：合并相似子弹，按语义去重（FAISS），更新知识库。 |
| 数据结构 | ```python
class KnowledgeBullet:
 id: str
 content: str # 具体教训或成功模式
 usage_count: int = 0
 last_used: datetime
 source_task_id: str
 source_agent: str # Developer/Reviewer/QA
 confidence_score: float # 0-1，由Reflector评估
 semantic_vector: List[float] # 用于去重
``` |
| SC→AC | SC: 经验持续精炼 → AC: 同一教训被使用3次后自动提升权重，1年未使用的教训自动归档。 |

 | ADR · ACE增量知识库 |
| --- |
| 技术栈 | FAISS（语义去重）+ PostgreSQL（知识存储）+ 独立轻量LLM（Reflector/Curator，可用Qwen-1.5B） |
| 影响Step | Step 3.4（领域知识图谱）、Step 5.2（Agent角色） |

 

### 3.2 优化二：L3压缩升级为双Agent异步压缩

 | PRD · 双Agent异步压缩 |
| --- |
| 目标 | 将L3滑动窗口升级为双Agent异步压缩，最大化Prompt缓存命中率 |
| 核心机制 | ① Observer：当累积上下文达30K tokens时，将历史压缩为“观察”追加到第一块。
 ② Reflector：当观察达40K tokens时，重组和浓缩观察。
 ③ 压缩在后台异步执行，不阻塞主流程。 |
| 压缩输出格式 | ```python
{
 "session_intent": "修改支付超时时间",
 "key_decisions": [
 {"step": "PLANNING", "decision": "仅修改config.php，不涉及service层"},
 {"step": "VALIDATING", "decision": "L3通过，L4通过"}
 ],
 "artifacts": [
 {"type": "code", "file": "config.php", "lines": "12-15"}
 ],
 "next_steps": "等待QA验证"
 }
``` |
| SC→AC | SC: Token成本降低 → AC: 测试100个任务，压缩后Token消耗降低40%，Agent决策质量无显著下降。 |

 | ADR · 双Agent异步压缩 |
| --- |
| 技术栈 | 轻量LLM（Qwen-1.5B）用于Observer/Reflector，Redis存储压缩状态，不阻塞主流程。 |
| 影响Step | Step 4.1（L3熵监控）、Step 5.3（动态任务分片） |

 

### 3.3 优化三：Deep Agents风格的大结果Offload

 | PRD · 大结果Offload |
| --- |
| 目标 | 沙箱执行结果和大图谱查询结果超过阈值时自动offload到文件系统 |
| 核心机制 | ① 工具结果Offload：沙箱执行结果>20K tokens时，替换为文件路径引用+前10行预览。
 ② 工具输入Offload：上下文超85%时，将旧工具调用替换为文件指针。
 ③ 早触发压缩：上下文仅达10-20%时即触发压缩评估，而非等到窗口满。 |
| 数据结构 | ```python
class OffloadReference:
 file_path: str
 preview_lines: List[str] # 前10行
 original_size_tokens: int
 created_at: datetime
 access_count: int # 被读回次数
``` |
| SC→AC | SC: 支持超长任务 → AC: 1000行日志输出的沙箱执行，上下文占用从15K降至2K。 |

 | ADR · 大结果Offload |
| --- |
| 技术栈 | 本地文件系统（/tmp/offload/）+ Redis索引（文件路径→任务ID映射） |
| 影响Step | Step MVP-03（沙箱）、Step 3.1-3.3（三图谱查询） |

 

### 3.4 优化四：ContextPilot前缀缓存集成

 | PRD · ContextPilot缓存集成 |
| --- |
| 目标 | 在多Agent并行执行时复用共享上下文（System Prompt + 图谱骨架），降低输入Token成本 |
| 核心机制 | ① 前缀缓存：L1（System Prompt）和L2（图谱骨架）在多个请求间共享时复用KV Cache。
 ② 缓存命中率监控：驾驶舱展示实时缓存命中率。
 ③ 与LiteLLM集成：利用LiteLLM的Prompt缓存能力。 |
| SC→AC | SC: 输入Token成本降低 → AC: 并行执行5个任务，输入Token成本降低≥30%。 |

 | ADR · ContextPilot缓存集成 |
| --- |
| 技术栈 | LiteLLM缓存API + Redis（跨实例共享缓存状态） |
| 影响Step | Step 2.1（LiteLLM网关） |

 

### 3.5 优化五：OpenViking三级冷热分级 + 检索可视化

 | PRD · 三级冷热分级 |
| --- |
| 目标 | 将五层映射为三级冷热体系，并在驾驶舱可视化检索轨迹 |
| 核心机制 | ① L0（热）：当前会话上下文（L1+L3），常驻窗口。
 ② L1（温）：图谱查询结果（L2），按需加载，缓存1小时。
 ③ L2（冷）：长期记忆（L5），按需检索，缓存1天。
 ④ 检索轨迹可视化：驾驶舱展示Agent每次查询访问的层级、命中的内容、跳过的内容。 |
| SC→AC | SC: 调试效率提升 → AC: 运维人员通过检索轨迹图可在3分钟内定位上下文策略问题（原需30分钟+）。 |

 | ADR · 三级冷热分级 |
| --- |
| 技术栈 | Redis（L0/L1缓存）+ PostgreSQL（L2持久化）+ ECharts（可视化） |
| 影响Step | Step 6.1（驾驶舱）、Step 7.2（AgentOps） |

 

---

 

## 4. 实施路线图与优先级

 | 优先级 | 优化项 | 对应开源项目 | 影响Step | 工作量 |
| --- | --- | --- | --- | --- |
| P1 | L5升级为ACE增量知识库 | ACE | Step 3.4 / 5.2 | 3-5天 |
| P1 | L3升级为双Agent异步压缩 | Observational Memory | Step 4.1 / 5.3 | 3-5天 |
| P1 | Deep Agents风格大结果Offload | Deep Agents | Step MVP-03 / 3.1-3.3 | 2-3天 |
| P2 | ContextPilot前缀缓存集成 | ContextPilot | Step 2.1 | 1-2天 |
| P2 | 三级冷热分级 + 检索可视化 | OpenViking | Step 6.1 / 7.2 | 3-5天 |
| P2 | Architext Provider框架 | Architext | Step 5.2 | 2-3天 |

 

> 建议启动顺序：
 
 第9-10周（与Phase 5并行）：优先实施三个P1优化（ACE增量知识库 + 双Agent异步压缩 + 大结果Offload），与现有架构契合度高，收益明显。
 第11-12周（Phase 6之后）：实施P2优化（ContextPilot缓存 + 三级冷热分级 + Architext框架），作为系统的增强层。

 

---

 

## 5. 代码示例

 

### 5.1 ACE增量知识库核心实现

 

```python
# /src/knowledge/ace_engine.py
 from typing import List, Optional
 from datetime import datetime
 import faiss
 import numpy as np

 class ACEKnowledgeEngine:
 def __init__(self, llm_client, vector_store):
 self.llm = llm_client
 self.vector_store = vector_store

 async def reflect(self, task_id: str, trajectory: Dict) -> Optional[KnowledgeBullet]:
 """Reflector: 分析执行轨迹，提取教训"""
 prompt = f"""
 分析以下任务执行轨迹，提取可复用的经验：
 任务：{trajectory['prd']}
 执行步骤：{trajectory['steps']}
 最终结果：{trajectory['result']}

 如果成功，提取"成功模式"（做了什么导致成功）。
 如果失败，提取"失败教训"（哪里出了问题）。
 输出格式：{{"type": "success|failure", "content": "...", "confidence": 0.0-1.0}}
 """
 response = await self.llm.generate(prompt)
 bullet = self._parse_bullet(response, task_id)
 return bullet

 async def curate(self, bullets: List[KnowledgeBullet]) -> List[KnowledgeBullet]:
 """Curator: 合并相似子弹，去重"""
 # 1. 语义去重（FAISS）
 vectors = [b.semantic_vector for b in bullets]
 if len(vectors) > 1:
 index = faiss.IndexFlatL2(len(vectors[0]))
 index.add(np.array(vectors))
 # 找到相似度>0.95的重复项
 duplicates = self._find_duplicates(index, vectors)

 # 2. 合并重复项
 merged = []
 for bullet in bullets:
 if bullet.id not in [d.id for d in duplicates]:
 merged.append(bullet)
 return merged
```

 

### 5.2 双Agent异步压缩实现

 

```python
# /src/scheduler/context_compressor.py
 import asyncio
 from typing import Dict, List

 class AsyncContextCompressor:
 def __init__(self, observer_llm, reflector_llm, token_threshold=30000):
 self.observer = observer_llm
 self.reflector = reflector_llm
 self.threshold = token_threshold

 async def compress(self, session_id: str, history: List[Dict]) -> Dict:
 """异步压缩L3上下文"""
 # 检查是否需要压缩
 total_tokens = self._estimate_tokens(history)
 if total_tokens 3:
 observation = await self._reflector_reorganize(accumulated)

 return {
 "compressed": True,
 "data": observation,
 "saved_tokens": total_tokens - self._estimate_tokens([observation])
 }

 async def _observer_compress(self, history: List[Dict]) -> Dict:
 prompt = f"""
 将以下对话历史压缩为结构化的"观察"：
 {history}

 输出格式（JSON）：
 {{
 "session_intent": "整体目标",
 "key_decisions": [{{"step": "...", "decision": "..."}}],
 "artifacts": [{{"type": "...", "file": "...", "lines": "..."}}],
 "next_steps": "预期下一步"
 }}
 """
 return await self.observer.generate(prompt)
```

 

### 5.3 大结果Offload实现

 

```python
# /src/sandbox/offload_manager.py
 import os
 import json
 from datetime import datetime

 class OffloadManager:
 def __init__(self, offload_dir="/tmp/offload"):
 self.offload_dir = offload_dir
 os.makedirs(offload_dir, exist_ok=True)

 def offload(self, content: str, task_id: str, step_name: str) -> Dict:
 """将大结果写入文件，返回引用"""
 tokens = self._estimate_tokens(content)
 if tokens str:
 """加载offload的内容"""
 file_path = os.path.join(self.offload_dir, f"{file_id}.json")
 with open(file_path, 'r') as f:
 data = json.load(f)
 return data["content"]
```

 

### 5.4 上下文检索轨迹可视化数据

 

```python
# /src/api/routes/traces.py
 @router.get("/tasks/{task_id}/context-traces")
 async def get_context_traces(task_id: str, cm: CheckpointManager = Depends(...)):
 """返回Agent查询上下文的轨迹，供驾驶舱可视化"""
 traces = await cm.get_context_traces(task_id)
 # 格式用于ECharts桑葚图
 return {
 "task_id": task_id,
 "nodes": [
 {"id": "L1_System", "name": "L1 System Prompt", "level": 0},
 {"id": "L2_Graph", "name": "L2 图谱查询", "level": 1},
 {"id": "L3_Task", "name": "L3 任务上下文", "level": 2},
 {"id": "L5_Memory", "name": "L5 长期记忆", "level": 3}
 ],
 "edges": [
 {"source": "L1_System", "target": "DeveloperAgent", "value": 5},
 {"source": "L2_Graph", "target": "DeveloperAgent", "value": 12},
 {"source": "L3_Task", "target": "DeveloperAgent", "value": 3},
 {"source": "L5_Memory", "target": "DeveloperAgent", "value": 0} # 未被命中
 ]
 }
```

 

---

 

> ✅ 上下文工程优化篇交付确认
 
 ACE：L5长期记忆升级为增量知识库（Generator-Reflector-Curator）
 Architext：Provider框架 + 可见性控制 + 智能缓存
 Observational Memory：双Agent异步压缩 + Prompt缓存优化
 Deep Agents：大结果Offload + 早触发压缩 + 结构化摘要
 OpenViking：三级冷热分级 + 检索轨迹可视化
 ContextPilot：前缀缓存复用 + KV Cache优化
 
 总工作量：约14-21天（3-4周），建议第9-10周启动P1优化，第11-12周启动P2优化。

 
 — V14.1 开发计划 · 上下文工程优化篇 · 2026年6月22日 —

---

# 第16章 开源项目借鉴与System Prompt工程

# V14.1 开发计划 · 补充章节 (第二版)

 
幻觉拦截全链路 + 兜底策略（双Agent验证 + 人工回放）

 
发布说明：本补充章节包含：① 上一轮已发布的“开源项目借鉴与System Prompt工程”完整内容；② 新增“幻觉拦截全链路与兜底策略”章节，将此前讨论的“双Agent验证模式”和“审计图谱人工回放”正式化为可执行的PRD/ADR，并映射到具体Step模块。

 

---

 

## 目录

 
- 1. 开源项目借鉴与 System Prompt 工程（已发布）
- 2. 幻觉拦截全链路与兜底策略（新增）

 

---

 
 
 
 

## 1. 开源项目借鉴与 System Prompt 工程（已发布）

 
本节内容已在上一版补充章节中完整发布，此处仅保留要点索引，完整内容请参见上一版HTML报告。

 | 章节 | 核心内容 |
| --- | --- |
| 1.1 Fable 5 剖析 | 7大设计原则 + V14.1 System Prompt完整模板（含环境、规则、沉默、Effort控制） |
| 1.2 六大开源项目 | OpenRath、Parlant、HALO、MetaGPT、ReDel、OpenAgents 完整借鉴方案 |
| 1.3 模块映射 | 所有借鉴点映射到V14.1具体Step（0.3, 1.2, 2.2, 5.1, 5.2, 6.1, 7.2） |
| 1.4 实施路线图 | P0/P1/P2三级优先级 + 工作量估算 + 启动顺序 |
| 1.5 代码示例 | Session对象、Guidelines配置、Prompt引擎、回放接口 |

 

 
 
 
 

## 2. 幻觉拦截全链路与兜底策略（新增）

 
新增 Step 4.1/4.2/5.1/6.1 增量

 

> 背景：虽然V14.1已有8层防幻觉体系（L1-L8），但在极端情况下（如幻觉逻辑完美绕过所有静态和动态验证），系统仍需兜底策略。本补充章节正式引入 “双Agent验证模式”（借鉴MetaGPT）和 “审计图谱人工回放”（借鉴ReDel）作为最后两道防线。

 

### 2.1 兜底策略一：双Agent验证模式（运行时拦截）

 | PRD · 双Agent验证模式 |
| --- |
| 背景 | 单一Agent的输出即使通过L1-L8验证，仍可能存在业务语义层面的偏差（如逻辑正确但需求理解错误）。引入第二个Agent（Reviewer）进行交叉验证，可大幅降低此类风险。 |
| 用户故事 | 作为调度器，我在CODING阶段启动两个DeveloperAgent并行工作，若两者输出差异超过阈值，则触发三方仲裁（引入ReviewerAgent裁决）。 |
| 需求描述 | ① 在PLANNING阶段，若任务复杂度标记为“高”或“关键路径”，调度器启动双Agent模式。
 ② 两个DeveloperAgent并行执行CODING，产出两套代码方案。
 ③ 系统计算两套方案的语义相似度（使用MiniLM Embedding）。
 ④ 若相似度 ≥ 0.85（高相似），选择任一方案继续流程。
 ⑤ 若相似度 &lt; 0.85（分歧），触发三方仲裁：启动ReviewerAgent，结合两套方案和原始PRD输出裁决意见。
 ⑥ 仲裁结果（选择方案A、方案B、或重新生成）作为最终产出进入VALIDATING层。 |
| 数据契约 | |
| SC→AC | SC1: 高相似场景快速通过 → AC1: 两Agent输出相似度≥0.85，系统选择方案A，总耗时增加&lt;30%（双Agent并行开销）。
 SC2: 低相似触发仲裁 → AC2: 两Agent输出相似度&lt;0.85，ReviewerAgent被唤醒，输出仲裁意见及理由。
 SC3: 仲裁后产出质量提升 → AC3: 对100个复杂任务进行测试，仲裁后的代码在业务语义正确性上比单Agent提升≥15%。 |
| 待定决策 | Q: 双Agent模式是否全量启用？ → 决议：仅对标记为“复杂”或“高影响”的任务启用（在PLANNING阶段由ArchitectAgent标记），避免Token浪费。 |

 | ADR · 双Agent验证模式 |
| --- |
| 技术栈 | MiniLM 用于语义相似度计算（复用L3采样一致性的Embedding模型）；ReviewerAgent使用与DeveloperAgent相同的LLM但不同的System Prompt（专门负责“裁判”角色）。 |
| 架构位置 | 调度器 CODING 状态内部扩展，位于 /src/scheduler/dual_agent/，包含 dual_runner.py、similarity.py、arbitrator.py。 |
| 实施细节 | |
| 风险与缓解 | 风险：双Agent模式导致Token消耗翻倍。缓解：仅对复杂任务启用（PLANNING阶段标记），日常简单任务仍为单Agent模式。 |
| 影响Step | Step 5.1（调度器）、Step 5.2（Agent角色——新增ReviewerAgent） |

 

### 2.2 兜底策略二：审计图谱人工回放（事后追溯）

 | PRD · 审计图谱人工回放 |
| --- |
| 背景 | 即使双Agent验证也未能100%拦截所有幻觉，生产环境中仍可能出现污染。需提供事后追溯能力，快速定位污染源并回滚。 |
| 用户故事 | 作为运维工程师，当生产环境出现异常时，我通过驾驶舱的“任务回放”功能查看该任务的完整决策链（每个Agent的输入/输出、验证结果、工具调用），快速定位污染源并执行回滚。 |
| 需求描述 | ① 审计表 task_audit_trail 完整记录每个Agent的输入摘要、输出摘要、验证结果、工具调用。
 ② 驾驶舱提供“任务回放”页面，支持按时间线逐帧回放。
 ③ 每个回放帧显示：步骤名称、Agent角色、输入/输出摘要、验证层结果（L1-L8）、耗时、Token消耗。
 ④ 提供“一键回滚”功能：定位到污染步骤后，回滚到该步骤之前的检查点。
 ⑤ 提供“污染传播分析”：从污染点出发，高亮所有依赖该输出的下游步骤。 |
| SC→AC | SC1: 完整回放 → AC1: 选择已完成任务，回放页面展示从IDLE到DONE的完整步骤序列，每步可展开查看详情。
 SC2: 污染源定位 → AC2: 在回放页面中，某步骤标记为“可疑”，可一键查看该步骤的前后依赖关系。
 SC3: 一键回滚 → AC3: 点击回滚按钮，系统恢复到指定检查点状态，耗时&lt;30秒。 |
| 待定决策 | Q: 回滚后是否自动重新执行后续步骤？ → 决议：由用户选择：A. 仅回滚不执行；B. 回滚后自动重新执行（带人工确认）。 |

 | ADR · 审计图谱人工回放 |
| --- |
| 技术栈 | 审计表（PostgreSQL）+ Vue3前端（Element Plus Timeline组件）+ WebSocket实时推送。回滚操作复用 Step 2.2 的检查点加载机制。 |
| 架构位置 | 前端驾驶舱 /frontend/src/views/AuditReplay.vue；后端路由 /api/v1/tasks/{task_id}/replay。 |
| 实施细节 | |
| 风险与缓解 | 风险：审计表数据量过大导致回放查询慢。缓解：按task_id分区，建立索引；设置查询限制（最多1000条记录）。 |
| 影响Step | Step 1.2（审计表）、Step 6.1（驾驶舱）、Step 2.2（检查点） |

 🧪 原子化测试用例：

 @pytest.mark.asyncio
 async def test_dual_agent_high_similarity():
 runner = DualAgentRunner(mock_llm, mock_graph, mock_session)
 # 模拟两个Agent生成相似代码
 mock_llm.generate.side_effect = ["def add(a,b): return a+b", "def add(x,y): return x+y"]
 result = await runner.run(mock_task)
 assert result.mode == "dual"
 assert result.similarity_score >= 0.85

 @pytest.mark.asyncio
 async def test_dual_agent_arbitration():
 runner = DualAgentRunner(mock_llm, mock_graph, mock_session)
 mock_llm.generate.side_effect = ["def add(a,b): return a+b", "def sub(a,b): return a-b"]
 result = await runner.run(mock_task)
 assert result.mode == "arbitration"
 assert result.arbitration_result is not None

 def test_replay_api():
 client = TestClient(app)
 resp = client.get("/api/v1/tasks/t1/replay")
 assert resp.status_code == 200
 assert "steps" in resp.json()
 assert len(resp.json()["steps"]) >= 3

 

### 2.3 幻觉拦截全链路总览

 
结合V14.1原有的8层防幻觉 + 本补充章节新增的2个兜底策略，形成完整的“发病→识别→拦截→修正→防止扩散→事后追溯”全链路：

 | 阶段 | 机制 | 对应层/模块 | 响应时间 | 说明 |
| --- | --- | --- | --- | --- |
| 实时拦截 | L3 熵监控 | Step 4.1 | ✅ 补充章节交付确认
 
 第一部分（已发布）：Fable 5 Prompt工程 + 六大开源项目借鉴方案
 第二部分（新增）：双Agent验证模式（PRD/ADR + 代码示例） + 审计图谱人工回放（PRD/ADR + 代码示例）
 
 开发工作量：双Agent验证约2-3天，审计回放约3-5天。建议在第7-8周与阶段四并行推进。
 与已有Step的集成点：Step 4.1/4.2（防幻觉层）、Step 5.1（调度器）、Step 5.2（Agent角色）、Step 6.1（驾驶舱）、Step 1.2（审计表）。

 
 — V14.1 开发计划 · 补充章节第二版 · 2026年6月22日 —

---

# 第17章 System Prompt工程完整模板

# V14.1 开发计划 · 补充章节

 
开源项目借鉴与 System Prompt 工程

 
发布说明：本补充章节整合了Fable 5逆向工程Prompt的深度剖析、六个高价值开源项目（OpenRath、Parlant、HALO、MetaGPT、ReDel、OpenAgents）的落地借鉴方法，以及与V14.1现有架构（三图谱、8层防幻觉、自研调度器）的融合方案。所有建议均可追溯至具体的Step模块，并提供可执行的代码示例和配置模板。

 

---