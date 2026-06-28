# Phase 3 技术方案——HyDE + Graph-RAG

> 基线: 阶段1-PRD + ADR #4 (HyDE), #5 (SQLite 邻接表), #6 (不引入外部向量库)
> P2-7 修正: 文档对齐实际实现——HyDE 用文件存储（非 DB），Graph 用内存字典（非 SQL 表）

## 改动文件

| File | Change |
|------|--------|
| `memory/store.py` | `append_to_file` 新增可选 `llm_client` 参数；新增 `_generate_hyde_questions()` |
| `graph/engines/code_graph.py` | 新增 `_extract_imports()` / `find_definitions_cross_file()` / `find_imports_of()` / `find_importers_of()` |

## 实现细节

### 1. HyDE 查询扩展
- 写入时：LLM 生成 3 条假设问答，追加到文件 body 的 `## HyDE 假设问答` 分区
- 检索时：现有 `search()` 的 substring 匹配自动覆盖 HyDE 分区
- 失败静默降级：无 LLM 或调用失败时跳过，不阻塞写入
- 零外部依赖——复用文件存储而非 SQL/向量库

### 2. Graph-RAG 跨文件边
- AST 解析时 `_extract_imports` 提取 `import`/`from...import` 边
- 存储：实例字典 `_import_edges`（非 SQL 表，避免大批量 upsert 瓶颈）
- 查询 API:
  - `find_definitions_cross_file(name)` — 哪些文件定义了该符号（跨文件，async）
  - `find_imports_of(file)` — 某文件导入了哪些模块
  - `find_importers_of(module)` — 哪些文件导入了指定模块
