"""代码图谱引擎（Step 3.1）。

用 Python ast 模块解析源码，提取符号定义（函数/类/变量）和调用关系，
存入 CodeNode + Edge 表，提供确定性的事实查询（防幻觉 L1/L2 的数据源）。

WHY 用 ast 而非正则：AST 保证准确性，正则解析代码不可靠（PRD 技术约束）。
"""

from __future__ import annotations

import ast
import uuid
from pathlib import Path

import structlog

from orbit.graph.engines.base import GraphEngineBase
from orbit.graph.models.nodes import CodeNode, Edge

logger = structlog.get_logger("orbit.graph.code")


class CodeGraphError(Exception):
    """代码图谱错误基类。"""


class CodeGraphEngine(GraphEngineBase):
    """代码图谱引擎：解析 Python 源码，提取符号 + 调用关系。

    查询接口：
    - exists(name, type) → bool：符号是否存在
    - get_callers(name) → list：谁调用了这个符号
    - get_callees(name) → list：这个符号调用了谁
    """

    async def build_index(self, directory: str) -> int:
        """全量构建目录下所有 .py 文件的索引。返回解析文件数。

        WHY 先清空旧数据：Orbit 单工作区模式，切换项目目录时
        旧索引残留会导致图谱混合两个项目的数据。清空后全量重建。
        """
        await self.clear_all(CodeNode)
        root = Path(directory)
        py_files = list(root.rglob("*.py"))
        count = 0
        for py_file in py_files:
            ok = await self._parse_file(py_file)
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
        """解析单个 .py 文件，提取符号 + 调用关系。"""
        try:
            content = path.read_text(encoding="utf-8")
            tree = ast.parse(content, filename=str(path))
        except SyntaxError as e:
            # WHY 跳过语法错误文件：不阻断整个构建（PRD 风险缓解）
            logger.warning("parse_syntax_error", file=str(path), error=str(e))
            return False
        except Exception as e:
            logger.warning("parse_failed", file=str(path), error=str(e))
            return False

        # 先删旧数据（文件重新解析）
        await self.delete_nodes_by_file(CodeNode, str(path))

        # 遍历 AST 提取符号
        for node in ast.walk(tree):
            node_id = uuid.uuid4().hex
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                namespace = self._get_namespace(node, tree)
                await self.upsert_node(
                    CodeNode,
                    node_id,
                    name=node.name,
                    type="function",
                    file_path=str(path),
                    start_line=node.lineno,
                    end_line=getattr(node, "end_lineno", node.lineno),
                    meta={"namespace": namespace, "args": self._get_args(node)},
                )
            elif isinstance(node, ast.ClassDef):
                namespace = self._get_namespace(node, tree)
                await self.upsert_node(
                    CodeNode,
                    node_id,
                    name=node.name,
                    type="class",
                    file_path=str(path),
                    start_line=node.lineno,
                    end_line=getattr(node, "end_lineno", node.lineno),
                    meta={"namespace": namespace},
                )
            elif isinstance(node, ast.Assign):
                # 模块级变量赋值（仅记录简单名称）
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        await self.upsert_node(
                            CodeNode,
                            node_id,
                            name=target.id,
                            type="variable",
                            file_path=str(path),
                            start_line=node.lineno,
                            end_line=getattr(node, "end_lineno", node.lineno),
                            meta={"namespace": "__main__"},
                        )

        # 第二遍：提取调用关系（需在符号定义入库后）
        await self._extract_calls(tree, str(path))
        # Phase 3: 提取跨文件 import 关系
        await self._extract_imports(tree, str(path))
        return True

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
