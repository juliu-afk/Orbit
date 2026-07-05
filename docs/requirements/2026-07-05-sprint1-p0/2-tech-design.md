# 阶段2 技术方案 — Sprint 1 P0：复利闭环+锚点+技能+向量

> 基线: [阶段1 PRD](阶段1-PRD-Sprint1-P0.md)（4 条 P0 用户故事，7 条验收标准）
> 状态: 待用户确认

---

## 1. PRD 对照表

| # | PRD 验收标准 | 技术方案覆盖 | 备注 |
|---|------------|------------|------|
| P0-1.1 | Agent system prompt 含蒸馏原则 | 新 `context/prebuilders/principles_prebuilder.py` → 所有角色自动注入 | 按任务关键词过滤 |
| P0-1.2 | 原则按任务关键词过滤 | `DistillationEngine.search(query=task_description)` | 复用现有搜索接口 |
| P0-1.3 | 蒸馏引擎无产出时不影响 | fail-open——空列表 = 不注入 | |
| P0-2.1 | STRATEGY.md 自动注入 system prompt | 新 `context/prebuilders/strategy_prebuilder.py` | 注入到 system prompt 顶部 |
| P0-2.2 | STRATEGY.md 缺失时降级 | fail-open——文件不存在 = 返回空上下文 | |
| P0-2.3 | 项目级隔离 | 读取 `{project_root}/STRATEGY.md` | |
| P0-3.1 | 每个 SKILL.md 含思考框架 | 改 6 个 `compose/skills/*.md` | 逆向 pm-skills prompt 结构 |
| P0-3.2 | plan 注入方案设计框架 | 问题定义→约束→方案对比→推荐→风险→Non-Goals | Marty Cagan 8 章 PRD 框架子集 |
| P0-3.3 | review 注入审查框架 | 正确性/安全/性能/可维护性各维度检查清单 | |
| P0-4.1 | VectorStore 接口不变 | `search(query, top_k)` 签名保留 | |
| P0-4.2 | TF-IDF → turbovec | `TurboQuantIndex(dim=512)` + `BGE-small-zh-v1.5` | |
| P0-4.3 | 语义搜索质量提升 | 嵌入 → turbovec 搜索 → 排序 | |
| P0-4.4 | 内存不增加 | turbovec 2-bit 模式: 16x 压缩 | |
| P0-4.5 | 无外部服务依赖 | turbovec (嵌入式 Rust) + sentence-transformers (本地模型) | 模型首次使用下载 |

---

## 2. 影响范围

### 新增文件（4 个）

| 文件 | 用途 |
|------|------|
| `src/orbit/context/prebuilders/principles_prebuilder.py` | P0-1: 蒸馏原则注入 prebuilder |
| `src/orbit/context/prebuilders/strategy_prebuilder.py` | P0-2: STRATEGY.md 锚点 prebuilder |
| `src/orbit/knowledge/embedding.py` | P0-4: EmbeddingGenerator 抽象 + BGE 实现 |

### 修改文件（9 个）

| 文件 | 改动 | 对应 P0 |
|------|------|---------|
| `src/orbit/context/prebuilder.py` | 工厂方法注册 2 个新 prebuilder | P0-1, P0-2 |
| `src/orbit/context/prebuilders/__init__.py` | 导出新 prebuilder | P0-1, P0-2 |
| `src/orbit/brief/generator.py` | 新增 `generate_strategy_md()` 方法 | P0-2 |
| `src/orbit/knowledge/vector.py` | `VectorStore` 实现从 TF-IDF 切 turbovec | P0-4 |
| `compose/skills/plan.md` | 方法论注入——方案设计框架 | P0-3 |
| `compose/skills/review.md` | 方法论注入——审查框架 | P0-3 |
| `compose/skills/debug.md` | 方法论注入——根因分析框架 | P0-3 |
| `compose/skills/tdd.md` | 方法论注入——TDD 最佳实践 | P0-3 |
| `compose/skills/verify.md` | 方法论注入——验证门禁 | P0-3 |
| `compose/skills/subagent.md` | 方法论注入——子Agent 分派策略 | P0-3 |

**总计**: 4 新文件 + 10 修改 = 14 文件

---

## 3. 架构设计

### 3.1 数据流：蒸馏原则注入（P0-1）

```
TaskRunner._build_context()
  → ContextPrebuilder.build_for_role(role).build(raw_context)
    → PrinciplesPrebuilder.build(raw_context)
      → DistillationEngine.search(query=task.description)
        → strategy_principles 表 SQLite LIKE 搜索（已有）
      → 格式化为 markdown 段落
        """
        ## 历史经验（自动注入）
        - [编码] 避免: 在循环内调用 LLM → 改为批量处理
        - [测试] 成功模式: 先写回归测试 → 确认失败 → 修代码
        ...
        """
      → 注入 raw_context["system"]["principles"]
  → PromptBuilder 组装 system prompt
```

### 3.2 数据流：STRATEGY.md 锚点（P0-2）

```
TaskRunner._build_context()
  → ContextPrebuilder.build_for_role(role).build(raw_context)
    → StrategyPrebuilder.build(raw_context)
      → 读取 {project_root}/STRATEGY.md
        ├── 存在 → 解析 5 段结构→注入 raw_context["system"]["strategy"]
        └── 不存在 → BriefGenerator.generate_strategy_md() 自动生成
                      → 保存 STRATEGY.md → 注入
      → 注入 raw_context["system"]["strategy"]
  → PromptBuilder 组装 system prompt 顶部
```

### 3.3 数据流：turboVec 向量搜索（P0-4）

```
VectorStore.__init__()
  → EmbeddingGenerator（BGE-small-zh-v1.5，首次下载 ~100MB）
  → 遍历知识库条目 → embedding = gen.encode(text)
  → TurboQuantIndex(dim=512, bit_width=4).add(embeddings)

VectorStore.search(query, top_k)
  → query_embedding = gen.encode(query)
  → scores, indices = index.search(query_embedding, k=top_k)
  → 返回 [{concept, name_zh, definition, score, ...}]
```

### 3.4 技能方法论注入（P0-3）

改动仅限 SKILL.md 文件——不改 Python 代码。`ComposeParser` 已自动加载 frontmatter + body。

改造模式（以 plan.md 为例）：
```markdown
---
name: compose:plan
description: 写 specs-driven 实现方案——分析 spec 后输出架构设计
phase: plan
tools: [read_file, grep, glob]
agent_role: architect
---

# compose:plan

## 思考框架（必须遵守）

### 1. 问题定义
用一句话说清用户痛点，不是功能描述。
反面示例: "实现导出功能" ← 这是功能描述，不是问题定义
正面示例: "会计人员月末需向税务局提交增值税申报表，当前手动整理耗时 2 小时"

### 2. 约束清单
显式列出所有约束（技术/业务/时间），标注哪些是可协商的。

### 3. 方案对比（至少 2 个）
每个方案标注 trade-off:
- 方案 A: ... (优势: ... / 代价: ...)
- 方案 B: ... (优势: ... / 代价: ...)

### 4. 推荐方案
选一个，说清为什么。

### 5. 风险矩阵（至少 3 个）
每个风险标注 likelihood(高/中/低) × impact(高/中/低):
- 风险 1: ... (L:高, I:中) → 缓解: ...

### 6. Non-Goals
显式标注本次不做的事，防止范围蔓延。

## 流程
1. 读取 spec 文件——理解项目目标和约束
2. 分析现有代码结构——read_file + grep + glob 了解上下文
3. 按上述思考框架输出架构设计方案

## 输出格式
```markdown
# 实现方案: [标题]

## 1. 问题定义
...

## 2. 约束清单
...

## 3. 方案对比
...

## 4. 推荐方案
...

## 5. 风险矩阵
...

## 6. Non-Goals
...
```
```

---

## 4. 关键接口设计

### 4.1 EmbeddingGenerator（新增）

```python
# src/orbit/knowledge/embedding.py

from abc import ABC, abstractmethod

class EmbeddingGenerator(ABC):
    """嵌入向量生成器抽象——支持本地模型和远程 API 互换。"""

    dim: int  # 向量维度

    @abstractmethod
    def encode(self, texts: list[str]) -> list[list[float]]:
        """批量文本 → 向量列表。"""
        ...

    @abstractmethod
    def encode_query(self, query: str) -> list[float]:
        """单条查询文本 → 向量。"""
        ...


class BGEEmbeddingGenerator(EmbeddingGenerator):
    """BGE-small-zh-v1.5 本地嵌入——零网络依赖。

    首次使用自动下载模型（~100MB），缓存到 ~/.cache/huggingface/。
    """

    dim = 512

    def __init__(self):
        from sentence_transformers import SentenceTransformer
        self._model = SentenceTransformer("BAAI/bge-small-zh-v1.5")

    def encode(self, texts: list[str]) -> list[list[float]]:
        embeddings = self._model.encode(texts, normalize_embeddings=True)
        return embeddings.tolist()

    def encode_query(self, query: str) -> list[float]:
        # BGE 模型查询需加前缀
        embedding = self._model.encode(
            f"为这个句子生成表示以用于检索相关文章：{query}",
            normalize_embeddings=True
        )
        return embedding.tolist()
```

### 4.2 VectorStore 改造（修改）

```python
# src/orbit/knowledge/vector.py
# 接口不变，实现切换

class VectorStore:
    def __init__(self, store: KnowledgeStore | None = None):
        self._store = store or KnowledgeStore()
        self._embedder = BGEEmbeddingGenerator()  # 新增
        self._index: TurboQuantIndex | None = None  # 替代 self._documents
        self._concepts: list[str] = []  # 槽位→概念名映射
        self._build_index()

    def _build_index(self):
        concepts = self._store.list_by_domain("accounting")
        texts = []
        for c in concepts:
            row = self._store.query_exact("accounting", c["concept"])
            if row:
                texts.append(f"{c['concept']} {row['name_zh']} {row['definition']}")
                self._concepts.append(c["concept"])

        # turbovec 零训练量化
        embeddings = self._embedder.encode(texts)
        self._index = TurboQuantIndex(dim=self._embedder.dim, bit_width=4)
        self._index.add(np.array(embeddings, dtype=np.float32))

    def search(self, query: str, top_k: int = 5) -> list[dict]:
        if self._index is None or len(self._concepts) == 0:
            return []
        query_vec = np.array(self._embedder.encode_query(query), dtype=np.float32)
        scores, indices = self._index.search(query_vec, k=min(top_k, len(self._concepts)))
        # 组装结果（与现有返回格式一致）
        ...
```

### 4.3 PrinciplesPrebuilder（新增）

```python
# src/orbit/context/prebuilders/principles_prebuilder.py

from orbit.context.prebuilder import ContextPrebuilder
from orbit.evolution.distill import DistillationEngine

class PrinciplesPrebuilder(ContextPrebuilder):
    """蒸馏引擎 → Agent system prompt 注入器。

    从 DistillationEngine 搜索与任务相关的策略原则，
    注入 raw_context["system"]["principles"]。
    """

    role = "_global"  # 全局 prebuilder——所有角色通用

    def __init__(self, distill_engine: DistillationEngine | None = None):
        self._engine = distill_engine

    def build(self, raw_context: dict) -> dict:
        if self._engine is None:
            return raw_context

        task_desc = raw_context.get("task", {}).get("description", "")
        if not task_desc:
            return raw_context

        principles = self._engine.search(task_desc, limit=5)
        if not principles:
            return raw_context

        # 格式化为 markdown 段落
        lines = ["## 历史经验（自动注入）"]
        for p in principles:
            lines.append(f"- [{p.category}] {p.principle}")
        raw_context.setdefault("system", {})["principles"] = "\n".join(lines)
        return raw_context
```

### 4.4 StrategyPrebuilder（新增）

```python
# src/orbit/context/prebuilders/strategy_prebuilder.py

from pathlib import Path
from orbit.context.prebuilder import ContextPrebuilder

class StrategyPrebuilder(ContextPrebuilder):
    """STRATEGY.md → Agent system prompt 顶部注入。

    读取项目 STRATEGY.md，注入 raw_context["system"]["strategy"]。
    文件缺失时调用 BriefGenerator 自动生成。
    """

    role = "_global"

    def build(self, raw_context: dict) -> dict:
        project_root = raw_context.get("project", {}).get("root", ".")
        strategy_path = Path(project_root) / "STRATEGY.md"

        if not strategy_path.exists():
            # 自动生成（异步→同步降级：生成失败不阻塞）
            strategy_path = self._auto_generate(project_root)

        if strategy_path and strategy_path.exists():
            content = strategy_path.read_text(encoding="utf-8")
            raw_context.setdefault("system", {})["strategy"] = (
                "## 项目策略锚点\n\n" + content[:3000]  # 截断到 3000 字符
            )

        return raw_context

    def _auto_generate(self, project_root: str) -> Path | None:
        try:
            from orbit.brief.generator import BriefGenerator
            gen = BriefGenerator()
            # 同步调用 LLM 生成（BriefGenerator.generate_strategy_md 新增方法）
            return gen.generate_strategy_md(project_root)
        except Exception:
            return None
```

---

## 5. 依赖变更

### 新增 Python 依赖

```toml
# pyproject.toml
[tool.poetry.dependencies]
turbovec = ">=0.1.0"           # MIT，Rust 向量索引
sentence-transformers = ">=3.0" # Apache 2.0，本地嵌入模型

# 首次安装后自动下载 BAAI/bge-small-zh-v1.5（~100MB），非打包进 exe
```

> ⚠️ 新依赖需先确认用户再装——按 CLAUDE.md 规则。

### 内部依赖链

```
principles_prebuilder.py → evolution/distill.py (DistillationEngine)
strategy_prebuilder.py   → brief/generator.py (BriefGenerator)
vector.py (改)           → knowledge/embedding.py (EmbeddingGenerator)
                         → turbovec (第三方)
prebuilder.py (改)       → principles_prebuilder, strategy_prebuilder
```

---

## 6. 边界 Case 清单

| 场景 | 预期行为 | 覆盖 |
|------|---------|------|
| 蒸馏引擎无原则（首次运行） | `search()` 返回空列表 → prebuilder 不注入 | P0-1 ✅ |
| STRATEGY.md 不存在 | `BriefGenerator` 自动生成 → 成功则注入，失败则静默跳过 | P0-2 ✅ |
| LLM 生成 STRATEGY.md 失败 | 返回 None → prebuilder 注入空 → Agent 正常执行 | P0-2 ✅ |
| turbovec 索引为空 | `search()` 返回空列表 | P0-4 ✅ |
| BGE 模型首次下载失败 | `EmbeddingGenerator.__init__` 抛异常 → VectorStore 降级为 TF-IDF | P0-4 ✅ |
| 知识库条目 < 10 | turbovec 小数据不退化，正常搜索 | P0-4 ✅ |
| SKILL.md frontmatter 缺失 | ComposeParser 已有容错——跳过 | P0-3 ✅ |
| 项目 root 路径无效 | `Path(project_root)` 不抛异常，`exists()` 返回 False → autogen | P0-2 ✅ |
| turbovec 索引构建 OOM（>1M 条目） | MVP 阶段不处理——知识库 < 10K 条目。未来: 分批 add | P0-4 ⚠️ |

---

## 7. 风险与缓解

| 风险 | 可能性 | 影响 | 缓解 |
|------|--------|------|------|
| turbovec + BGE 两个新依赖增加安装复杂度 | 高 | 低 | turbovec 是嵌入式库（pip install 即用），sentence-transformers 有预编译 wheel。安装失败时降级到 TF-IDF |
| BGE 模型下载（~100MB）首次使用卡顿 | 高 | 中 | 异步下载+进度提示。下载失败→降级到 TF-IDF |
| 蒸馏原则质量差（噪音）污染 Agent 上下文 | 低 | 中 | 现有剪枝机制（utility<0.15 自动剪枝）+ 仅注入 top-5 |
| pm-skills prompt 逆向不完整——缺少关键方法论细节 | 中 | 低 | 从 pm-skills 仓库直接读取 `create-prd`/`strategy-red-team` 的 system prompt 原文，不仅依赖报告描述 |
| STRATEGY.md 自动生成内容过时 | 低 | 高 | 标注生成时间+来源，Agent 可质疑。定期 `brief/generator.py` 重新生成 |

---

## 8. 调度器/防幻觉/图谱影响

| 模块 | 影响 | 说明 |
|------|------|------|
| **调度器** | 无状态变更 | P0-1/P0-2 是上下文注入——发生在 TaskRunner dispatch 前，不改调度状态机 |
| **防幻觉层** | 无变更 | P0-4 语义偏离检测是 P2 项。本次不改 L1-L9 |
| **图谱 Schema** | 无变更 | CodeGraph SQLite 表结构不变。新增数据不经过图谱 |
| **检查点** | 无变更 | 上下文注入是纯函数——不影响检查点保存/回滚 |

全部 4 项改动均为 **非核心模块改动**（不触及 scheduler/hallucination/graph 核心逻辑）。

---

## 9. 构建与打包影响

| 项目 | 影响 |
|------|------|
| PyInstaller | `orbit.spec` 需加 `hiddenimports`: `turbovec`, `sentence_transformers` |
| Tauri 壳 | 无影响——纯 Python 层改动 |
| exe 体积 | turbovec Rust .pyd ~5MB。BGE 模型不打包进 exe（运行时下载） |
| 桌面启动 | 首次使用知识库搜索时触发模型下载（~100MB），后续使用缓存 |

---

*技术方案基线，等待用户确认后进入阶段 3。*
