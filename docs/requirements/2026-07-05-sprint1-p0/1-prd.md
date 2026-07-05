# 阶段1 PRD — Sprint 1 P0：闭合复利闭环 + 锚点 + 技能质量 + 向量存储

> 基线: [开源项目深度解构报告](../../open-source-deep-dive-2026-07-05.html) §7.2 Sprint 1
> 来源: 4 个开源项目对照分析（pm-skills / Compound Engineering / turboVec / ECC）
> 状态: ✅ 已确认 (2026-07-05)

---

## 1. 背景

Orbit 在基础设施层（编排/防幻觉/沙箱/熔断/图谱/自蒸馏）碾压同类项目。但报告发现 3 个结构性问题 + 1 个技术选型问题，Sprint 1 解决其中 4 个投入产出比最高的。

| # | 问题 | 来源 | 当前症状 |
|---|------|------|---------|
| 1 | 蒸馏引擎未接入上下文管线 | Compound 对比 | `DistillationEngine.top_principles()` 产出原则，但 Agent system prompt 不包含 |
| 2 | 缺少策略锚点机制 | Compound STRATEGY.md | Agent 不理解项目目标——每次需手动说明"我们在解决什么问题" |
| 3 | 技能是步骤清单，不是方法论注入 | pm-skills 对比 | `compose/skills/plan.md` 告诉 Agent "读文件→分析→输出"，不告诉"按什么框架思考" |
| 4 | 向量存储是纯 Python TF-IDF | turboVec 对比 | 中文 bigram 关键词匹配，无语义理解。规划迁移 Qdrant 但需外部服务——不匹配 Tauri 桌面部署 |

---

## 2. 用户故事

### P0-1: 蒸馏经验自动注入 Agent 上下文
**作为** Orbit 用户，
**我希望** Agent 执行任务时自动引用历史蒸馏出的策略原则，
**以便** 避免重复踩坑，每次任务都为下一次铺路。

验收标准:
- [ ] Agent system prompt 包含来自 `DistillationEngine.top_principles()` 的相关原则
- [ ] 原则按任务关键词过滤（如任务涉及"审计"→注入审计类原则）
- [ ] 蒸馏引擎无产出时，system prompt 不受影响（无多余空白/NULL 字符串）

### P0-2: 策略锚点自动对齐
**作为** Orbit 用户，
**我希望** 设定项目目标后，所有 Agent 自动理解"我们在解决什么问题、谁是用户、怎么衡量成功"，
**以便** 不需要每次新建任务时重复说明背景。

验收标准:
- [ ] 项目 `STRATEGY.md`（或 GoalSession）的目标/约束自动注入 Agent system prompt 顶部
- [ ] STRATEGY.md 缺失时，Agent 正常降级——不报错、不中断
- [ ] 支持项目级覆盖——不同项目可维护独立的 STRATEGY.md

### P0-3: 技能注入方法论框架
**作为** Orbit 用户，
**我希望** compose 技能不只是编排步骤，而是向 Agent 注入经过验证的思维框架，
**以便** Agent 产出的方案/代码/审查质量显著提升。

验收标准:
- [ ] 每个 SKILL.md 的 body 包含明确的思考框架（对应的方法论/反面示例/输出格式约束）
- [ ] `compose:plan` 注入方案设计框架（问题定义→约束→方案对比→推荐→风险→Non-Goals）
- [ ] `compose:review` 注入审查框架（正确性/安全/性能/可维护性各维度检查清单）
- [ ] 其余 4 个技能（debug/subagent/tdd/verify）有对应的领域最佳实践注入

### P0-4: turboVec 替换 TF-IDF 向量存储
**作为** Orbit 用户，
**我希望** 知识库搜索支持语义理解而非仅关键词匹配，
**以便** "税率计算"能找到"所得税费用"相关条目（当前 TF-IDF 匹配不到）。

验收标准:
- [ ] `knowledge/vector.py::VectorStore` 接口不变（`search(query, top_k)` 签名保留）
- [ ] 底层实现从 TF-IDF 切换到 `turbovec.TurboQuantIndex`
- [ ] 搜索结果质量：查询"税率计算"能返回"所得税费用"条目（语义匹配）
- [ ] 内存占用不增加（turbovec 2-bit: 16x 压缩）
- [ ] 不引入外部服务依赖（turbovec 是嵌入式 Rust 库，PyO3 绑定）

---

## 3. 成功指标

| 指标 | 当前 | 目标 |
|------|------|------|
| Agent 上下文中策略原则命中率 | 0%（未接入） | >0%（至少注入 top-5 原则） |
| plan 技能产出方案结构完整度 | 无结构约束 | 100% 含问题定义/约束/方案对比/风险/Non-Goals |
| 知识库语义搜索 MAP@5 | TF-IDF 关键词级 | turboVec 语义级，至少 +10% |
| 引入新依赖 | 0 | 1（`turbovec`，MIT 许可，pip install） |

---

## 4. Non-Goals（本次不做）

- ❌ 不新建 68 个 pm-skills 风格技能——仅升级现有 6 个
- ❌ 不实现复合工作流推荐引擎（链式推荐是 P1 项）
- ❌ 不引入 Qdrant/Chroma 等外部向量服务（违反 Tauri 桌面零依赖约束）
- ❌ 不修改防幻觉层 L1-L9（语义偏离检测是 P2 项）
- ❌ 不实现并行审查 Agent（P1 项）

---

## 5. 边缘情况

| 场景 | 预期行为 |
|------|---------|
| 蒸馏引擎无任何原则（首次运行） | `top_principles()` 返回空列表，system prompt 不加原则段 |
| STRATEGY.md 文件不存在 | `strategy_prebuilder` 返回空上下文，不报错 |
| turboVec 索引为空（知识库无数据） | `search()` 返回空列表，不崩溃 |
| 知识库条目 < 10 条 | turboVec 正常索引和搜索（小数据集不退化） |
| 中文混合英文术语（如 "ROE"、"EBITDA"） | turboVec 嵌入模型正确处理多语言 |
| SKILL.md 格式错误（无 frontmatter） | ComposeParser 已有容错——跳过该文件，不影响其他技能加载 |
| 多个项目同时运行 | STRATEGY.md 项目级隔离——每个项目读自己的文件 |

---

## 6. 决策记录（已确认）

### 6.1 嵌入模型：本地 BGE-small-zh-v1.5

选 `BAAI/bge-small-zh-v1.5`（512-dim，~100MB，中英双语）。

| 对比维度 | OpenAI embedding | 本地 BGE |
|---------|-----------------|----------|
| 质量 | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ |
| 离线可用 | ❌ | ✅ |
| API 成本 | ~$0.02/M tokens | 零 |
| 延迟 | ~200ms | ~30ms |
| 打包体积 | 0 | +100MB（首次运行下载） |
| 隐私 | 文本离开本机 | 数据不出机器 |

理由: Orbit 是 Tauri 桌面应用，离线可用是核心约束。模型首次使用时通过 `sentence-transformers` 自动下载缓存。后续可通过抽象接口 `EmbeddingGenerator` 支持 OpenAI 作为可选配置。

### 6.2 STRATEGY.md：复用 brief/generator.py 自动生成

`brief/generator.py` 已有项目说明书生成逻辑。新增 `strategy_prebuilder` 调用 `BriefGenerator.generate_strategy_md()`，从 GoalSession/brief 中提取 Target Problem / Approach / Persona / Key Metrics / Tracks 五段结构。STRATEGY.md 缺失时自动生成+缓存，不阻塞任务。

### 6.3 技能模板：逆向 pm-skills prompt 模板

从 pm-skills 仓库的 `create-prd`、`strategy-red-team`、`intended-vs-implemented` 三个技能的 system prompt 中提取方法论框架结构，适配到 Orbit 的 6 个 SKILL.md。不照搬 68 个——只取与软件工程相关的设计模式。

### 6.4 分支策略：按流程走 feature 分支 + PR

分支名: `feat/sprint1-p0-compound-interest`。所有代码改动走此分支，阶段 3b 审查通过后 PR 合并。

---

## 7. 风险与假设

| 风险 | 可能性 | 影响 | 缓解 |
|------|--------|------|------|
| turbovec 嵌入 API 调用引入网络依赖 | 高（如果用 API） | 中 | 选本地模型（BGE/GTE），或接受嵌入 API 为唯一外部依赖 |
| 技能方法论注入后 Agent 输出过长 | 中 | 低 | system prompt 中控制输出格式，超长截断 |
| STRATEGY.md 内容过时导致 Agent 对齐错误目标 | 中 | 高 | 在 Agent prompt 中标注"策略锚点来源+更新时间"，Agent 可质疑 |
| 蒸馏原则质量差（噪音）污染 Agent 上下文 | 低 | 中 | 现有剪枝机制（utility_score<0.15 自动剪枝）。可选加人工审核标记 |

---

*PRD 基线，等待用户确认后进入阶段 2。*
