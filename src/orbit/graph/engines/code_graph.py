"""代码图谱引擎（Step 3.1 + Phase 2 多语言扩展）。

Python 文件用 ast 标准库（零回归），TypeScript/SQL 用 tree-sitter。
提取符号定义（函数/类/变量）、调用关系、继承关系，
存入 CodeNode + Edge 表，提供确定性的事实查询（防幻觉 L1/L2 的数据源）。
"""

from __future__ import annotations

import ast
import uuid
from pathlib import Path

import structlog
from tree_sitter import Language, Parser, Query  # noqa: F401 — type hints

from orbit.graph.engines.base import GraphEngineBase
from orbit.graph.models.nodes import CodeNode, Edge

logger = structlog.get_logger("orbit.graph.code")


class CodeGraphError(Exception):
    """代码图谱错误基类。"""


class CodeGraphEngine(GraphEngineBase):
    """代码图谱引擎：多语言源码解析，提取符号 + 调用/继承关系。

    Python (.py) → ast（零回归）。TypeScript (.ts/.tsx) + SQL (.sql) → tree-sitter。
    查询接口：exists / get_callers / get_callees / find_definitions_with_positions
    """

    # Phase 2: 多语言 grammar 映射。tree-sitter parser 惰性初始化。
    _LANG_EXTS: dict[str, str] = {".ts": "typescript", ".tsx": "tsx", ".sql": "sql"}
    _parsers: dict[str, "Parser"] = {}

    def _get_parser(self, lang: str) -> "Parser":
        """惰性初始化 tree-sitter Parser——仅首次遇到该语言时加载 grammar。"""
        if lang in self._parsers:
            return self._parsers[lang]
        try:
            # tree-sitter 0.23+ auto-discovers Language via pip-installed grammar packages
            language = Language(getattr(__import__(f"tree_sitter_{lang}"), "language"))
            parser = Parser(language)
            # WHY 只存 parser 不复用 Language：Language 实例线程安全（底层 C 库）
            self._parsers[lang] = parser
            logger.info("ts_parser_loaded", lang=lang)
            return parser
        except ImportError:
            logger.warning("ts_grammar_missing", lang=lang)
            return None
        except Exception as e:
            logger.warning("ts_parser_failed", lang=lang, error=str(e))
            return None

    async def build_index(self, directory: str) -> int:
        """全量构建目录下所有支持语言的索引。返回解析文件数。"""
        await self.clear_all(CodeNode)
        root = Path(directory)
        # Phase 2: 扩展 glob——不仅 .py，含 .ts/.tsx/.sql
        patterns = ["*.py", "*.ts", "*.tsx", "*.sql"]
        files: list[Path] = []
        for pat in patterns:
            files.extend(root.rglob(pat))
        count = 0
        for f in files:
            ok = await self._parse_file(f)
            if ok:
                count += 1
        logger.info("code_graph_indexed", directory=directory, files=count)
        return count

    async def incremental_update(self, file_path: str) -> bool:
        """增量更新单个文件（SC3）。先删旧节点+边+import，再重新解析。

        P1-3: 清理 _import_edges——否则旧文件的 import 边残留，
        导致 find_importers_of 返回已删除文件的错结果。
        """
        path = Path(file_path)
        await self.delete_nodes_by_file(CodeNode, str(path))
        # 清理该文件的 import 边
        if hasattr(self, "_import_edges"):
            self._import_edges.pop(str(path), None)
        return await self._parse_file(path)

    async def _parse_file(self, path: Path) -> bool:
        """解析单个源文件——按扩展名路由到 ast 或 tree-sitter。"""
        ext = path.suffix
        if ext in self._LANG_EXTS:
            return await self._parse_with_tree_sitter(path, self._LANG_EXTS[ext])
        elif ext == ".py":
            return await self._parse_python_ast(path)
        # 不支持的语言静默跳过
        return False

    async def _parse_python_ast(self, path: Path) -> bool:
        """Python ast 路径——保持 Phase 1 行为不变（零回归）。"""
        try:
            content = path.read_text(encoding="utf-8")
            tree = ast.parse(content, filename=str(path))
        except SyntaxError as e:
            logger.warning("parse_syntax_error", file=str(path), error=str(e))
            return False
        except Exception as e:
            logger.warning("parse_failed", file=str(path), error=str(e))
            return False

        await self.delete_nodes_by_file(CodeNode, str(path))

        for node in ast.walk(tree):
            node_id = uuid.uuid4().hex
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                namespace = self._get_namespace(node, tree)
                await self.upsert_node(
                    CodeNode, node_id, name=node.name, type="function",
                    file_path=str(path), start_line=node.lineno,
                    end_line=getattr(node, "end_lineno", node.lineno),
                    meta={"namespace": namespace, "args": self._get_args(node)},
                )
            elif isinstance(node, ast.ClassDef):
                namespace = self._get_namespace(node, tree)
                await self.upsert_node(
                    CodeNode, node_id, name=node.name, type="class",
                    file_path=str(path), start_line=node.lineno,
                    end_line=getattr(node, "end_lineno", node.lineno),
                    meta={"namespace": namespace},
                )
            elif isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        await self.upsert_node(
                            CodeNode, node_id, name=target.id, type="variable",
                            file_path=str(path), start_line=node.lineno,
                            end_line=getattr(node, "end_lineno", node.lineno),
                            meta={"namespace": "__main__"},
                        )

        await self._extract_calls(tree, str(path))
        await self._extract_imports(tree, str(path))
        # Phase 3: DATA_FLOWS——变量赋值→使用链
        await self._extract_data_flows(tree, str(path))
        # Phase 3: 节点层级——建模块节点 + CONTAINS 边
        await self._build_hierarchy(str(path))
        return True

    async def _build_hierarchy(self, file_path: str) -> None:
        """为文件创建 Module 节点 + 链接符号→CONTAINS 边 + 设 parent_id。

        WHY: 节点层级（Module→Class→Function）让 Agent 能做
        "这个模块有哪些符号？" 的结构化查询。
        """
        # P2-1 fix: 用去扩展名+去前导src/的相对路径做唯一 module_name
        clean = file_path.replace("\\", "/")
        if "/src/" in clean:
            clean = clean.split("/src/", 1)[1]
        module_name = clean.rsplit(".", 1)[0]
        module_id = uuid.uuid4().hex
        await self.upsert_node(
            CodeNode, module_id, name=module_name, type="module",
            file_path=file_path, start_line=0, end_line=0,
            meta={"namespace": file_path},
        )
        # 查该文件下所有符号 → 建 CONTAINS 边 + 设 parent_id
        file_nodes = await self.find_nodes_by_file(CodeNode, file_path)
        for node in file_nodes:
            if node.id == module_id:
                continue
            # P1-1 fix: 设 parent_id——Module→Symbol 层级
            node.parent_id = module_id
            await self.add_edge(
                source_id=module_id, source_type="code",
                target_id=node.id, target_type="code",
                edge_type="contains",
            )

    async def _extract_data_flows(self, tree: ast.AST, file_path: str) -> None:
        """提取函数内变量赋值→使用关系为 DATA_FLOWS 边。

        WHY: Agent 追溯"这个变量在哪定义的→在哪使用的"。
        借鉴 CBM DATA_FLOWS——Python 实现分析每个函数体内 Name 节点。
        """
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            func_name = node.name
            assigned: dict[str, int] = {}
            used: list[tuple[str, int]] = []
            for child in ast.walk(node):
                if isinstance(child, ast.Name):
                    if isinstance(child.ctx, ast.Store):
                        assigned[child.id] = child.lineno
                    elif isinstance(child.ctx, ast.Load):
                        used.append((child.id, child.lineno))
            for var_name, use_line in used:
                if var_name in assigned:
                    # Phase 3: DATA_FLOWS——变量名直接用作节点名（与 _parse_python_ast 中 Assign 一致）
                    await self._record_data_flow(var_name, func_name, var_name, file_path, use_line)

    async def _record_data_flow(
        self, source: str, target: str, variable: str, file_path: str, line: int,
    ) -> None:
        src_node = await self.find_node_by_name(CodeNode, source)
        if src_node is None:
            nid = uuid.uuid4().hex
            await self.upsert_node(CodeNode, nid, name=source, type="variable",
                                   file_path=file_path, start_line=line, end_line=line,
                                   meta={"data_flow_var": variable})
            src_node = await self.find_node_by_name(CodeNode, source)
        if src_node is None:
            return
        tgt_node = await self.find_node_by_name(CodeNode, target)
        if tgt_node is None:
            return
        await self.add_edge(source_id=src_node.id, source_type="code",
                            target_id=tgt_node.id, target_type="code", edge_type="data_flows")

    async def _parse_with_tree_sitter(self, path: Path, lang: str) -> bool:
        """tree-sitter 解析 TypeScript/SQL 文件——提取函数/类/方法。"""
        parser = self._get_parser(lang)
        if parser is None:
            return False
        try:
            content = path.read_text(encoding="utf-8")
            tree = parser.parse(bytes(content, "utf-8"))
        except Exception as e:
            logger.warning("ts_parse_failed", file=str(path), error=str(e))
            return False

        await self.delete_nodes_by_file(CodeNode, str(path))
        root = tree.root_node
        await self._walk_ts_tree(root, content, str(path))
        # Phase 3: 节点层级——建模块节点 + CONTAINS 边
        await self._build_hierarchy(str(path))
        return True

    async def _walk_ts_tree(self, node, source: str, file_path: str) -> None:
        """递归遍历 tree-sitter CST——提取函数定义/类定义/调用 + 继承关系。

        WHY 不区分语言节点类型：tree-sitter grammar 各语言的节点类型名不同
        （Python function_definition, TS function_declaration, SQL statement）。
        通过 type 字符串 contains 匹配覆盖所有语言。
        """
        ntype = node.type
        # 函数/方法定义
        if "function" in ntype or "method" in ntype or "arrow_function" in ntype:
            name = self._ts_get_name(node, source)
            if name:
                nid = uuid.uuid4().hex
                await self.upsert_node(
                    CodeNode, nid, name=name, type="function",
                    file_path=file_path, start_line=node.start_point[0] + 1,
                    end_line=node.end_point[0] + 1,
                    meta={"namespace": self._ts_get_module(file_path)},
                )
        # 类定义
        elif "class" in ntype and "class_body" not in ntype:
            name = self._ts_get_name(node, source)
            if name:
                nid = uuid.uuid4().hex
                await self.upsert_node(
                    CodeNode, nid, name=name, type="class",
                    file_path=file_path, start_line=node.start_point[0] + 1,
                    end_line=node.end_point[0] + 1,
                    meta={"namespace": self._ts_get_module(file_path)},
                )
        # 调用表达式 → 提取 callee 名
        if "call" in ntype:
            callee_name = self._ts_get_callee_name(node, source)
            if callee_name:
                # 找到当前函数上下文——向上遍历找最近的 function/method/class
                func_ctx = self._ts_find_enclosing_function(node)
                if func_ctx:
                    caller_name = self._ts_get_name(func_ctx, source)
                    if caller_name:
                        await self._record_call_relation(caller_name, callee_name, file_path)
        # 继承关系
        if ntype in ("class_heritage", "extends_clause", "implements_clause"):
            await self._extract_ts_inherits(node, source, file_path)
        # 递归子节点
        for child in node.children:
            await self._walk_ts_tree(child, source, file_path)

    def _ts_get_name(self, node, source: str) -> str | None:
        """从 tree-sitter 节点提取名称——仅查直接子节点（P1-3 fix: 去递归）。"""
        for child in node.children:
            if child.type in ("identifier", "name", "property_identifier", "object_type"):
                return source[child.start_byte:child.end_byte]
        return None

    def _ts_get_callee_name(self, node, source: str) -> str | None:
        """从 call_expression 提取被调用函数名。"""
        for child in node.children:
            if child.type in ("identifier", "member_expression", "property_identifier"):
                if child.type == "member_expression":
                    # obj.method() → 返回 method 部分
                    for gc in child.children:
                        if gc.type == "property_identifier":
                            return source[gc.start_byte:gc.end_byte]
                return source[child.start_byte:child.end_byte]
            name = self._ts_get_callee_name(child, source)
            if name:
                return name
        return None

    def _ts_find_enclosing_function(self, node):
        """向上遍历找最近的函数/方法/类定义节点。"""
        current = node
        while current is not None:
            ntype = current.type
            if "function" in ntype or "method" in ntype or "arrow_function" in ntype or "class_declaration" in ntype:
                return current
            current = current.parent
        return None

    def _ts_get_module(self, file_path: str) -> str:
        """从文件路径推导模块名。"""
        parts = file_path.replace("\\", "/").split("/")
        return "/".join(parts[-3:]).rsplit(".", 1)[0] if len(parts) >= 3 else file_path

    async def _extract_ts_inherits(self, node, source: str, file_path: str) -> None:
        """提取 TypeScript extends/implements 继承关系→INHERITS边。"""
        # 找父节点 class_declaration → 获取子类名
        parent = node.parent
        if parent and "class" in parent.type:
            subclass_name = self._ts_get_name(parent, source)
            for child in node.children:
                if child.type == "identifier":
                    super_name = source[child.start_byte:child.end_byte]
                    await self._record_inherit_relation(subclass_name, super_name, file_path)

    async def _record_inherit_relation(self, subclass: str, superclass: str, file_path: str) -> None:
        """记录继承关系为 INHERITS 边。"""
        if not subclass or not superclass:
            return
        sub_node = await self.find_node_by_name(CodeNode, subclass)
        if sub_node is None:
            return
        super_node = await self.find_node_by_name(CodeNode, superclass)
        if super_node is None:
            return
        await self.add_edge(
            source_id=sub_node.id, source_type="code",
            target_id=super_node.id, target_type="code",
            edge_type="inherits",
        )

    async def _extract_calls(self, tree: ast.AST, file_path: str) -> None:
        """提取函数调用关系。记录 caller（函数内）→ callee（被调用名）。"""
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                caller_name = node.name
                for child in ast.walk(node):
                    if isinstance(child, ast.Call):
                        callee_name = self._get_call_name(child.func)
                        if callee_name:
                            # WHY 记录调用关系（边）：get_callers/get_callees 查询用
                            # source = caller, target = callee（按名暂存，查时解析）
                            await self._record_call_relation(caller_name, callee_name, file_path)

    async def _record_call_relation(self, caller: str, callee: str, file_path: str) -> None:
        """记录调用关系（用 Edge 表，source/target 用符号名构造临时 ID）。"""
        # 查 caller 和 callee 的真实 node_id（按名）
        caller_node = await self.find_node_by_name(CodeNode, caller)
        if caller_node is None:
            return
        callee_node = await self.find_node_by_name(CodeNode, callee)
        if callee_node is None:
            # callee 可能是内置函数/未解析，仍记录为"外部引用"（meta 里标记）
            return
        await self.add_edge(
            source_id=caller_node.id,
            source_type="code",
            target_id=callee_node.id,
            target_type="code",
            edge_type="calls",
        )

    def _get_namespace(self, node: ast.AST, tree: ast.Module) -> str:
        """推断符号的命名空间——向上遍历父节点找 ClassDef 拼接。

        WHY 嵌套命名空间: 类内方法 Calculator.compute 需与模块级函数
        calc_total 区分——否则 find_node_by_name 同名查找会冲突。
        构建 parent map → 向上收集 ClassDef 名 → 拼 Class.method 形式。
        模块级符号返回 "__main__"。
        """
        # 构建 parent map——一次遍历整个 AST
        parent_map: dict[ast.AST, ast.AST] = {}
        for parent in ast.walk(tree):
            for child in ast.iter_child_nodes(parent):
                parent_map[child] = parent

        # 向上查找所有 enclosing ClassDef
        classes: list[str] = []
        current: ast.AST = node
        while current in parent_map:
            parent = parent_map[current]
            if isinstance(parent, ast.ClassDef):
                classes.append(parent.name)
            if isinstance(parent, ast.Module):
                break
            current = parent

        if not classes:
            return "__main__"
        # 从外层到内层：OuterClass.InnerClass.method
        return ".".join(reversed(classes))

    def _get_args(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[str]:
        """提取函数参数名。"""
        args = [a.arg for a in node.args.args]
        return args

    def _get_call_name(self, node: ast.AST) -> str | None:
        """从 Call 节点提取被调用函数名。"""
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            return node.attr
        return None

    async def _extract_imports(self, tree: ast.AST, file_path: str) -> None:
        """Phase 3: 提取跨文件 import 关系——存入 Edge 表。

        import X → 边: file_path -(imports)→ X 对应模块文件
        from X import Y → 边: file_path -(imports symbol Y)→ X.Y
        """
        from_path = file_path
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    self._record_import_edge(from_path, alias.name, None)
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                for alias in node.names:
                    self._record_import_edge(from_path, module, alias.name)

    def _record_import_edge(self, from_path: str, module: str, symbol: str | None) -> None:
        """记录导入边到实例字典——简单快速，无需 DB session。

        WHY 字典而非 SQLAlchemy: import 边数量大（每个文件数十条），
        批量解析时逐条 upsert 太慢。内存存储足够（查询时按文件查）。
        """
        if not hasattr(self, "_import_edges"):
            self._import_edges: dict[str, list[dict]] = {}
        key = from_path
        self._import_edges.setdefault(key, []).append(
            {
                "module": module,
                "symbol": symbol,
            }
        )

    def find_imports_of(self, file_path: str) -> list[str]:
        """Phase 3: 查询某文件导入了哪些模块。"""
        edges = getattr(self, "_import_edges", {}).get(file_path, [])
        return [e["module"] for e in edges if e["module"]]

    async def find_definitions_cross_file(self, symbol_name: str) -> list[str]:
        """Phase 3: 查询哪些文件定义了该符号——跨文件定义发现。

        P1-1 修正: 原名 find_callers_cross_file 有误导性——此方法查询
        符号的"定义位置"而非"调用者"。改名为 find_definitions_cross_file。
        """
        from sqlalchemy import select as sa_select

        async with self.session_factory() as session:
            stmt = sa_select(CodeNode).where(CodeNode.name == symbol_name)
            result = await session.execute(stmt)
            nodes = result.scalars().all()
            return list({n.file_path for n in nodes if n.file_path})

    async def find_definitions_with_positions(
        self, symbol_name: str
    ) -> list[dict[str, Any]]:
        """查询符号定义位置——含行号信息。

        WHY: /codegraph/definition 端点需要返回精确行号，
        而非仅 file_path。CodeNode 已有 start_line/end_line 字段。
        """
        from sqlalchemy import select as sa_select

        async with self.session_factory() as session:
            stmt = sa_select(CodeNode).where(CodeNode.name == symbol_name)
            result = await session.execute(stmt)
            nodes = result.scalars().all()
            seen: set[str] = set()
            definitions: list[dict[str, Any]] = []
            for node in nodes:
                if not node.file_path or node.file_path in seen:
                    continue
                seen.add(node.file_path)
                definitions.append({
                    "file_path": node.file_path,
                    "start_line": node.start_line or 1,
                    "end_line": node.end_line or node.start_line or 1,
                    "name": node.name,
                    "kind": node.type or "function",
                })
            return definitions

    def find_importers_of(self, module_path: str) -> list[str]:
        """Phase 3: 哪些文件导入了指定模块（内存查询，毫秒级）。

        P2-8: 去重——一个文件可能多次 import 同一模块。
        """
        module_name = module_path.replace("/", ".").replace(".py", "").lstrip(".")
        results = []
        for file_path, imports in getattr(self, "_import_edges", {}).items():
            for entry in imports:
                entry_module = entry["module"]
                # 精确匹配 或 目标模块是父包（from X import Y where X=module_name）
                if entry_module == module_name or entry_module.startswith(module_name + "."):
                    results.append(file_path)
                    break  # 一个文件只计一次
        return list(set(results))

    # ---- 查询接口 ----

    async def exists(self, name: str, symbol_type: str | None = None) -> bool:
        """SC2: 符号是否存在（<100ms）。"""
        async with self.session_factory() as session:
            from sqlalchemy import select as sa_select

            stmt = sa_select(CodeNode).where(CodeNode.name == name)
            if symbol_type:
                stmt = stmt.where(CodeNode.type == symbol_type)
            result = await session.execute(stmt)
            return result.scalar_one_or_none() is not None

    async def get_callers(self, symbol_name: str) -> list[str]:
        """SC4: 查询谁调用了某符号（返回调用者名称列表）。"""
        target = await self.find_node_by_name(CodeNode, symbol_name)
        if target is None:
            return []
        edges = await self.get_edges(target.id, "calls", direction="in")
        # 查每个 source 的名称
        names = []
        for edge in edges:
            async with self.session_factory() as session:
                node = await session.get(CodeNode, edge.source_id)
                if node:
                    names.append(node.name)
        return names

    async def get_callees(self, symbol_name: str) -> list[str]:
        """查询某符号调用了谁。"""
        source = await self.find_node_by_name(CodeNode, symbol_name)
        if source is None:
            return []
        edges = await self.get_edges(source.id, "calls", direction="out")
        names = []
        for edge in edges:
            async with self.session_factory() as session:
                node = await session.get(CodeNode, edge.target_id)
                if node:
                    names.append(node.name)
        return names

    async def get_symbol_meta(self, symbol_name: str) -> dict | None:
        """获取符号的元数据——类型签名、文档等。

        WHY: /codegraph/hover 端点调用此方法，
        从 CodeNode.meta JSON 字段提取信息返回给前端。
        此前该方法不存在，hover 端点始终 500。
        """
        node = await self.find_node_by_name(CodeNode, symbol_name)
        if node is None:
            return None
        return node.meta or {}

    async def get_all_nodes(self) -> list[dict]:
        """返回所有代码图谱节点——供图谱可视化 API 使用。

        WHY 返回 list[dict] 而非 ORM 对象：API 层不需要 ORM session 管理，
        字典序列化直接适配 Cytoscape elements 格式。
        """
        from sqlalchemy import func, select as sa_select

        async with self.session_factory() as session:
            result = await session.execute(sa_select(CodeNode))
            nodes = result.scalars().all()
            return [
                {
                    "id": n.id,
                    "name": n.name,
                    "type": n.type,
                    "file_path": n.file_path,
                    "start_line": n.start_line,
                    "end_line": n.end_line,
                    "symbol_count": 0,  # 后续按 file_path 聚合计算
                    "in_degree": 0,
                    "out_degree": 0,
                }
                for n in nodes
            ]

    async def get_all_edges(self) -> list[dict]:
        """返回所有代码图谱边——供图谱可视化 API 使用。"""
        from sqlalchemy import select as sa_select

        async with self.session_factory() as session:
            result = await session.execute(
                sa_select(Edge).where(
                    (Edge.source_node_type == "code") | (Edge.target_node_type == "code")
                )
            )
            edges = result.scalars().all()
            return [
                {
                    "id": e.id,
                    "source_id": e.source_id,
                    "target_id": e.target_id,
                    "edge_type": e.edge_type,
                    "weight": e.weight or 1,
                }
                for e in edges
            ]
