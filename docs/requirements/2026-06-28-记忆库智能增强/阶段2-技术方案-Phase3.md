# Phase 3 技术方案——HyDE + Graph-RAG

> 基线: 阶段1-PRD + ADR #4 (HyDE), #5 (SQLite 邻接表), #6 (不引入外部向量库)

## 改动文件

| File | Change |
|------|--------|
| `memory/models.py` | MemoryEntry 新增 `hyde_questions` 字段 |
| `memory/store.py` | append_to_file 时生成 HyDE 假设问题；搜索时匹配 |
| `graph/models.py` | 新增 `CodeEdge` 模型 |
| `graph/engines/code_graph.py` | 新增 `_load_edges()` / `_save_edge()` / `find_callers()` / `find_imports()` |
| `migrations/` | 新 SQL 表 code_edges |

## 实现细节

### 1. HyDE 查询扩展
- 写入 memory 时，LLM 生成 3 条假设问答存入 `hyde_questions` JSON 列
- 检索时 FTS5 MATCH 覆盖 content + hyde_questions 双列
- 不需要 ChromaDB——SQLite FTS5 已支持多列索引

### 2. Graph-RAG 跨文件边
- 新 SQLite 表 `code_edges(source_path, target_path, relation_type, source_name, target_name)`
- `relation_type`: 'imports' | 'calls' | 'inherits'（内存字典存储，非 DB）
- 查询 API: `find_definitions_cross_file(name)` | `find_imports_of(file)` | `find_importers_of(module)`
- `_extract_imports` 在 AST 解析时自动填充边
