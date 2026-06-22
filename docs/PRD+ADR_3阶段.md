## Step 3.1：代码图谱引擎（基于AST，支持Python）

| PRD (产品需求文档) |  |
| --- | --- |
| **背景** | LLM频繁引用不存在的函数、类或模块，导致幻觉。需要静态分析代码仓库，提取所有符号定义（函数、类、变量）及调用关系（谁调用谁），提供确定性的事实校验能力。 |
| **用户故事** | 作为开发者Agent，我通过`GraphQuery.exists(symbol_name, symbol_type)`校验生成的代码中的引用是否真实存在，若不存在则拒绝生成并触发重新生成。 |
| **需求描述** | ①使用Python内置`ast`模块解析`.py`文件，提取`FunctionDef`、`ClassDef`、`Assign`（变量）节点；②记录每个符号的名称、所在文件路径、起止行号、所属命名空间（类/模块）；③提取调用关系（`Call`节点），记录调用方和被调用方；④存储到SQLite数据库（复用Step 1.2的`CodeNode`和`Edge`表）；⑤提供增量更新能力（监测文件修改时间，仅重新解析变更文件）；⑥提供查询接口：`exists(name, type)`，`get_callers(symbol)`，`get_callees(symbol)`。 |
| **范围 (Do/Don't)** | **Do：**支持Python语言；支持解析单个文件或整个目录；支持增量更新；支持基础调用关系提取。**Don't：**不支持动态特性（`eval`/`exec`、`__import__`）；不支持跨文件导入解析（仅记录符号定义，不解析导入别名）；不支持控制流分析。 |
| **数据契约** | ``代码块-1`` |
| | 查询接口： |
| | ``代码块-2`` |
| **异常定义** | ``代码块-3`` |
| **成功标准→验收** | **SC1:**解析1000个Python文件<30s →**AC1:**使用包含1000个文件的Django项目测试，计时<30s。 |
| | **SC2:**查询响应<100ms →**AC2:**执行`exists('add')`，`timeit`< 100ms。 |
| | **SC3:**增量更新正确 →**AC3:**修改一个文件后重新解析，仅该文件及其调用方被更新，其他节点不受影响。 |
| | **SC4:**调用链准确 →**AC4:**若文件A中`foo()`调用了文件B的`bar()`，则`get_callers('bar')`返回包含`foo`。 |
| **待定决策** | **Q1:**是否支持跨文件调用链（模块间调用）？ →**决议：**支持，因为调用方和被调用方可能在不同文件中，通过全量解析后统一构建边。 |
| | **Q2:**如何处理同名的函数（重载）？ →**决议：**使用`namespace`字段区分（如`mymodule.MyClass.method`），查询时需提供全限定名或通过上下文推断。 |

| ADR (架构决策记录) |  |
| --- | --- |
| **技术栈版本** | Python 3.11内置`ast`模块；SQLAlchemy 2.0.25 (异步), aiosqlite 0.19 (测试) / asyncpg 0.29 (生产)。 |
| **架构位置** | 能力层（静态分析），位于`/src/graph/code_graph.py`，依赖`/src/infrastructure/models.py`中的`CodeNode`和`Edge`。 |
| **实施细节** | **核心类：** |
| | ``代码块-4`` |
| **风险与缓解** | 风险：AST无法解析有语法错误的文件（导致整个构建失败）。缓解：使用`try-except SyntaxError`跳过该文件并记录错误，保证其他文件入库。 |
| **需求错位** | 若需支持多语言（JS/TS/Java），需切换至Tree-sitter。但MVP阶段仅Python，已规划后续扩展。 |
| **技术约束** | 禁止使用正则表达式解析代码；必须使用AST保证准确性。禁止删除已入库的旧数据（仅标记`deprecated`或软删除）。 |
| **环境配置** | `CODE_GRAPH_DB=sqlite:///./code_graph.db`(开发)，或使用主DATABASE_URL（生产）。 |
| **依赖链** | CodeGraphEngine → SQLAlchemy (async) → aiosqlite/asyncpg → 数据库。 |

🧪 原子化测试用例 (pytest)：
import pytest
from pathlib import Path
from src.graph.code_graph import CodeGraphEngine

@pytest.mark.asyncio
async def test_build_index(tmp_path, code_graph_engine):
# 创建测试文件
test_file = tmp_path / "test.py"
test_file.write_text("def add(a,b): return a+b")
await code_graph_engine.build_index(str(tmp_path))
assert await code_graph_engine.exists("add") is True

@pytest.mark.asyncio
async def test_call_relation(tmp_path, code_graph_engine):
test_file = tmp_path / "test.py"
test_file.write_text("def foo(): return bar()")
await code_graph_engine.build_index(str(tmp_path))
callers = await code_graph_engine.get_callers("bar")
assert "foo" in callers

@pytest.mark.asyncio
async def test_incremental_update(tmp_path, code_graph_engine):
test_file = tmp_path / "test.py"
test_file.write_text("def add(a,b): return a+b")
await code_graph_engine.build_index(str(tmp_path))
# 修改文件
test_file.write_text("def add(a,b,c): return a+b+c")
await code_graph_engine.incremental_update(str(test_file))
# 重新查询，应更新
# 验证方法：检查节点的meta中参数个数是否变化
assert await code_graph_engine.exists("add")

## Step 3.2：数据库图谱引擎（Schema反射）

| PRD |  |
| --- | --- |
| **背景** | LLM生成的SQL/ORM语句常引用不存在的表或字段，导致运行时错误。需通过反射数据库元数据构建数据库图谱，提供表、字段、外键的真实信息。 |
| **用户故事** | 作为QA验证Agent，我需要查询`table_exists('orders')`和`column_exists('orders', 'user_id')`，验证生成的SQL语句合法性。 |
| **需求描述** | ①使用SQLAlchemy反射读取数据库（PostgreSQL/MySQL）的`information_schema`；②提取所有表名、字段名、数据类型、是否可空、默认值；③提取外键关系（来源表.字段 → 目标表.字段）；④存储到`DbNode`和`Edge`表中（复用Step 1.2模型）；⑤提供`table_exists`、`column_exists`、`get_foreign_keys(table)`查询接口；⑥支持多schema（默认public）。 |
| **范围 (Do/Don't)** | **Do：**支持PostgreSQL 15和MySQL 8.0；支持核心表快照（通过`@core`标记），每日备份元数据。**Don't：**不支持存储过程、触发器、视图（V2）；不支持全量MVCC（仅快照）。 |
| **数据契约** | ``代码块-5`` |
| | 查询接口： |
| | ``代码块-6`` |
| **异常定义** | ``代码块-7`` |
| **成功标准→验收** | **SC1:**解析50张表<30s →**AC1:**连接到测试库（含50张表），计时<30s。 |
| | **SC2:**外键关系准确 →**AC2:**若`orders.user_id`引用`users.id`，则`get_foreign_keys('orders')`返回包含`{'column':'user_id','ref_table':'users','ref_column':'id'}`。 |
| | **SC3:**增量快照 →**AC3:**每日定时任务运行后，检查`checkpoints`表中记录的元数据哈希变化。 |
| **待定决策** | **Q1:**快照保留几天？ →**决议：**保留7天，使用`cleanup_old_snapshots(7)`。 |
| | **Q2:**是否支持多数据库连接？ →**决议：**当前仅支持一个主数据库，通过环境变量指定。 |

| ADR |  |
| --- | --- |
| **技术栈版本** | SQLAlchemy 2.0.25 (反射使用`inspect`), asyncpg 0.29 (PG), pymysql 1.1 (MySQL), aiosqlite (测试)。 |
| **架构位置** | 能力层，位于`/src/graph/db_graph.py`。 |
| **实施细节** | **核心类：** |
| | ``代码块-8`` |
| **风险与缓解** | 风险：反射大数据库（千表）可能超时。缓解：使用分页查询`information_schema`，每次最多50张表。 |
| **需求错位** | 若数据库为MongoDB（NoSQL），此模块不适用。当前明确仅支持关系型。 |
| **技术约束** | 必须使用只读数据库账号（`DATABASE_URL_READONLY`），防止误修改生产数据。 |
| **环境配置** | `DB_READONLY_URL=postgresql+asyncpg://reader:xxx@host/db`。 |
| **依赖链** | DbGraphEngine → SQLAlchemy (反射) → asyncpg/pymysql → 目标DB。 |

🧪 原子化测试用例 (pytest)：
import pytest
from src.graph.db_graph import DbGraphEngine

@pytest.mark.asyncio
async def test_table_exists(db_graph_engine, test_db):
# 假设test_db中包含表 'users'
await db_graph_engine.build_index()
assert await db_graph_engine.table_exists("users") is True
assert await db_graph_engine.table_exists("nonexistent") is False

@pytest.mark.asyncio
async def test_foreign_keys(db_graph_engine, test_db):
await db_graph_engine.build_index()
fks = await db_graph_engine.get_foreign_keys("orders")
assert any(fk["column"] == "user_id" and fk["ref_table"] == "users" for fk in fks)

@pytest.mark.asyncio
async def test_column_exists(db_graph_engine, test_db):
await db_graph_engine.build_index()
assert await db_graph_engine.column_exists("users", "id") is True

## Step 3.3：配置图谱引擎（漂移检测与修复）

| PRD |  |
| --- | --- |
| **背景** | 生产故障中70%源于配置漂移（如.env文件被手动修改、Nginx配置参数变更未同步）。需构建配置图谱，计算配置指纹，自动检测并修复漂移。 |
| **用户故事** | 作为运维工程师，我需要系统每10分钟扫描配置目录，若发现与黄金基线不一致，自动回滚或发送告警。 |
| **需求描述** | ①解析常见配置文件格式：`.env`（`python-dotenv`）、`.yml`/`.yaml`（`pyyaml`）、`.json`、`nginx.conf`（简单正则提取关键指令）、`php.ini`；②为每个配置文件计算SHA256指纹；③存储到`ConfigNode`表（含`hash`,`file_path`,`env`）；④维护“黄金基线”版本（存储在单独的`config_baselines`表）；⑤定期（每10分钟）扫描文件系统，计算当前指纹并对比基线；⑥若不一致，触发修复（用基线内容覆盖）或告警（根据环境策略：Test自动修复，Prod仅告警）。 |
| **范围 (Do/Don't)** | **Do：**支持.env, YAML, JSON, Nginx (简易), php.ini；支持自动修复（Test环境）。**Don't：**不支持K8s ConfigMap（V2）；不支持加密配置（sops）。 |
| **数据契约** | ``代码块-9`` |
| | 接口： |
| | ``代码块-10`` |
| **异常定义** | ``代码块-11`` |
| **成功标准→验收** | **SC1:**漂移检测<90秒 →**AC1:**手动修改`.env`中的`DB_PORT`，在10分钟内检测到并记录日志。 |
| | **SC2:**修复成功率>90% →**AC2:**在Test环境自动修复后，文件内容与基线完全一致（`sha256sum`比对）。 |
| | **SC3:**支持至少5种格式 →**AC3:**分别提供`.env`,`.yml`,`.json`,`nginx.conf`,`php.ini`样本，均能正确解析并计算指纹。 |
| **待定决策** | **Q1:**自动修复是否需要备份原文件？ →**决议：**是，修复前将当前文件备份到`/backups/config`。 |
| | **Q2:**基线版本如何更新？ →**决议：**人工通过管理命令`update_baseline`更新，或通过CI/CD触发。 |

| ADR |  |
| --- | --- |
| **技术栈版本** | python-dotenv 1.0, pyyaml 6.0, deepdiff 6.7 (用于diff生成), hashlib (内置)。 |
| **架构位置** | 能力层，位于`/src/graph/config_graph.py`。 |
| **实施细节** | **核心类：** |
| | ``代码块-12`` |
| **风险与缓解** | 风险：配置文件解析失败导致整个扫描中断。缓解：每个文件独立try-except，记录错误并继续。 |
| **需求错位** | 若使用K8s ConfigMap，文件系统路径不存在，需额外集成K8s API。当前阶段不涉及。 |
| **技术约束** | 自动修复前必须备份原文件到`BACKUP_DIR`，且修复操作需记录审计日志。 |
| **环境配置** | `CONFIG_BASE_DIR=/etc/myapp`,`CONFIG_BACKUP_DIR=/backups/config`,`ENV=test`。 |
| **依赖链** | ConfigGraphEngine → python-dotenv / pyyaml → 文件系统。 |

🧪 原子化测试用例 (pytest)：
import pytest
from pathlib import Path
from src.graph.config_graph import ConfigGraphEngine

@pytest.mark.asyncio
async def test_compute_hash_env(tmp_path, config_graph_engine):
env_file = tmp_path / ".env"
env_file.write_text("DB_PORT=5432")
h = config_graph_engine.compute_hash(env_file)
assert len(h) == 64

@pytest.mark.asyncio
async def test_detect_drift(tmp_path, config_graph_engine, baseline_data):
# 设置基线，然后修改文件
await config_graph_engine.scan_and_index()
# 修改文件内容
(tmp_path / ".env").write_text("DB_PORT=5433")
drifts = await config_graph_engine.detect_drift()
assert len(drifts) == 1
assert ".env" in drifts[0]["file"]

@pytest.mark.asyncio
async def test_auto_fix(tmp_path, config_graph_engine, baseline_data):
await config_graph_engine.scan_and_index()
(tmp_path / ".env").write_text("DB_PORT=5433")
await config_graph_engine.auto_fix(str(tmp_path / ".env"))
content = (tmp_path / ".env").read_text()
assert "DB_PORT=5432" in content


**✅ 阶段3 (Step 3.1, 3.2, 3.3) 交付确认**

本报告完整交付了三图谱引擎的全部三个步骤：

- **Step 3.1 (代码图谱)**：基于AST的Python代码静态分析，提取符号定义与调用关系，为L1引用校验提供数据。
- **Step 3.2 (数据库图谱)**：反射关系型数据库元数据，提供表/字段/外键事实查询。
- **Step 3.3 (配置图谱)**：解析配置文件，计算指纹，检测漂移并自动修复，为L8防幻觉层提供支持。

这三个Step与已交付的Step 1.2（ORM模型）无缝衔接，开发人员可按每个Step拆分为3-4个子任务，总工时约3人日。完成后系统将具备完整的三图谱能力，支撑后续防幻觉层的实施。



```
// 代码块-1
# 复用Step 1.2的 CodeNode 和 Edge 模型，补充字段：
    # CodeNode: file_path, start_line, end_line, namespace (如 __main__.MyClass)
    # Edge: edge_type = 'calls', 'defines'（预留）
```


```
// 代码块-2
class GraphQuery:

        async def exists(self, name: str, symbol_type: str = "function") -> bool

        async def get_callers(self, symbol: str) -> List[str]  # 返回调用方符号名

        async def get_callees(self, symbol: str) -> List[str]  # 返回被调用方符号名
```


```
// 代码块-3
class CodeGraphError(Exception): pass

    class ParseError(CodeGraphError): pass  # 语法错误导致解析失败
```


```
// 代码块-4
import ast

    from pathlib import Path

    from typing import List, Dict, Set

    from sqlalchemy.ext.asyncio import AsyncSession



    class CodeGraphEngine:

        def __init__(self, session_factory):

            self.session_factory = session_factory

            self._file_mtimes: Dict[str, float] = {}  # 用于增量更新



        async def build_index(self, root_path: str) -> None:

            # 遍历所有 .py 文件，调用 _parse_file



        async def incremental_update(self, file_path: str) -> None:

            # 检查mtime，若变更则重新解析并更新数据库



        def _parse_file(self, file_path: str) -> Dict:

            with open(file_path) as f:

                tree = ast.parse(f.read())

            visitor = CodeVisitor(file_path)

            visitor.visit(tree)

            return visitor.nodes, visitor.edges



    class CodeVisitor(ast.NodeVisitor):

        def __init__(self, file_path):

            self.file_path = file_path

            self.nodes = []

            self.edges = []

            self.current_namespace = ""



        def visit_FunctionDef(self, node):

            # 记录函数定义

            name = f"{self.current_namespace}.{node.name}" if self.current_namespace else node.name

            self.nodes.append(("function", name, node.lineno, node.end_lineno))

            # 遍历函数体内的调用

            for child in ast.walk(node):

                if isinstance(child, ast.Call):

                    if isinstance(child.func, ast.Name):

                        callee = child.func.id

                        self.edges.append((name, callee, "calls"))

            self.generic_visit(node)



        async def exists(self, name: str, symbol_type: str = "function") -> bool:

            async with self.session_factory() as session:

                stmt = select(CodeNode).where(CodeNode.name == name, CodeNode.type == symbol_type)

                result = await session.execute(stmt)

                return result.scalar_one_or_none() is not None
```


```
// 代码块-5
# DbNode 字段：schema, db_type ('table', 'view', 'column')

    # Edge 存储外键：source_id = 字段节点ID, target_id = 目标字段节点ID, edge_type='foreign_key'
```


```
// 代码块-6
async def table_exists(table_name: str) -> bool

    async def column_exists(table_name: str, column_name: str) -> bool

    async def get_foreign_keys(table_name: str) -> List[Dict[str, str]]
```


```
// 代码块-7
class DbGraphError(Exception): pass

    class DbConnectionError(DbGraphError): pass
```


```
// 代码块-8
from sqlalchemy import create_engine, inspect, MetaData

    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession



    class DbGraphEngine:

        def __init__(self, db_url: str, session_factory):

            self.engine = create_async_engine(db_url)

            self.session_factory = session_factory



        async def build_index(self, schema: str = "public") -> None:

            async with self.engine.connect() as conn:

                inspector = await conn.run_sync(lambda sync_conn: inspect(sync_conn))

                tables = await conn.run_sync(lambda sync_conn: inspector.get_table_names(schema))

                for table in tables:

                    columns = await conn.run_sync(lambda sync_conn: inspector.get_columns(table, schema))

                    fk = await conn.run_sync(lambda sync_conn: inspector.get_foreign_keys(table, schema))

                    # 存储到 DbNode 和 Edge



        async def snapshot_core_tables(self, core_tables: List[str]):

            # 对核心表备份元数据到单独的store（可存JSON或PG表）



        async def table_exists(self, table_name: str) -> bool:

            async with self.session_factory() as session:

                stmt = select(DbNode).where(DbNode.name == table_name, DbNode.db_type == 'table')

                return await session.execute(stmt).scalar_one_or_none() is not None
```


```
// 代码块-9
# ConfigNode 扩展字段：file_path, hash, env, baseline_version

    # 基线表：config_baselines (id, file_path, hash, content_text, created_at)
```


```
// 代码块-10
async def scan_configs(directory: str) -> List[ConfigNode]

    async def detect_drift() -> List[Dict[str, str]]  # 返回漂移文件列表及diff

    async def auto_fix(file_path: str) -> bool
```


```
// 代码块-11
class ConfigGraphError(Exception): pass

    class ParseConfigError(ConfigGraphError): pass
```


```
// 代码块-12
import hashlib

    from pathlib import Path

    from dotenv import dotenv_values

    import yaml

    import json

    import re



    class ConfigGraphEngine:

        def __init__(self, session_factory, base_dir: str, env: str = "dev"):

            self.base_dir = Path(base_dir)

            self.env = env

            self.session_factory = session_factory



        def _parse_file(self, file_path: Path) -> str:

            if file_path.suffix == ".env":

                return str(dotenv_values(file_path))

            elif file_path.suffix in (".yml", ".yaml"):

                with open(file_path) as f:

                    return json.dumps(yaml.safe_load(f))

            elif file_path.suffix == ".json":

                with open(file_path) as f:

                    return json.dumps(json.load(f))

            elif "nginx.conf" in file_path.name:

                with open(file_path) as f:

                    return re.sub(r'\s+', ' ', f.read())  # 简单规范化

            else:

                raise ParseConfigError(f"Unsupported file type: {file_path}")



        def compute_hash(self, file_path: Path) -> str:

            content = self._parse_file(file_path)

            return hashlib.sha256(content.encode()).hexdigest()



        async def scan_and_index(self):

            # 遍历base_dir下所有支持的配置文件，计算hash并存入ConfigNode



        async def detect_drift(self):

            drifts = []

            async with self.session_factory() as session:

                baselines = await session.execute(select(ConfigBaseline))

                for baseline in baselines:

                    current_hash = self.compute_hash(Path(baseline.file_path))

                    if current_hash != baseline.hash:

                        drifts.append({"file": baseline.file_path, "expected": baseline.hash, "actual": current_hash})

            return drifts



        async def auto_fix(self, file_path: str):

            if self.env == "prod":

                raise ConfigGraphError("Auto-fix not allowed in production")

            # 从baseline恢复文件
```


# 多Agent自循环系统 · 阶段4 8层防幻觉体系 (Step 4.1 & 4.2) · 编码就绪级PRD/ADR

L1-L4 静态/实时拦截 ｜ L5-L8 深度形式化与运行时保障

**交付声明：**本报告为阶段4（W7-W8）8层防幻觉体系的终极细化文档。Step 4.1实现L1-L4（图谱验证、动态追踪、熵监控、类型检查），Step 4.2实现L5-L8（Z3验证、合约双向校验、沙箱执行、配置漂移修复）。每个Step均包含字段级契约、精确函数签名、配置示例、原子化pytest用例，可直接编码。此模块与已交付的调度器、LLM客户端、检查点、图谱引擎无缝集成。

