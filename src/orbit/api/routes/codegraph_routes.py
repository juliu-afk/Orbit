"""代码导航 API (Step 9 Phase 1.3)——Go to Def / References / Outline / Hover."""

from __future__ import annotations
import asyncio, ast
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

router = APIRouter(prefix="/codegraph", tags=["codegraph"])

_code_graph = None
_file_service = None


def set_code_graph(engine) -> None:
    global _code_graph
    _code_graph = engine


def set_file_service(svc) -> None:
    global _file_service
    _file_service = svc


class SymbolRef(BaseModel):
    name: str
    file: str
    line: int
    kind: str


class OutlineNode(BaseModel):
    name: str
    kind: str
    line: int
    children: list[OutlineNode] = []


@router.get("/definition")
async def go_to_definition(symbol: str = Query(...), file: str = Query("")):
    """Go to Definition——搜索符号定义。"""
    if _code_graph is None:
        raise HTTPException(status_code=503, detail="CodeGraph not available")
    try:
        defs = await _code_graph.find_definitions_cross_file(symbol)
        if defs:
            return {"file": defs[0], "line": 1, "name": symbol, "kind": "function"}
    except (RuntimeError, ValueError) as e:
        raise HTTPException(status_code=500, detail=str(e))
    return None


@router.get("/references")
async def find_references(symbol: str = Query(...)):
    """Find All References——通过 call 边反向查引用。"""
    if _code_graph is None:
        raise HTTPException(status_code=503, detail="CodeGraph not available")
    try:
        callers = await _code_graph.get_callers(symbol)
        return [{"name": c, "file": "", "line": 1, "kind": "function"} for c in callers]
    except (RuntimeError, ValueError) as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/outline")
async def get_outline(file: str = Query(...)):
    """文件大纲——异步 AST 解析提取函数/类。"""
    # P1: 始终通过 _file_service 读取，附带路径遍历防护
    if _file_service is None:
        raise HTTPException(status_code=503, detail="FileService not available")
    try:
        content = await _file_service.read_file(file)
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="File not found")

    # P1: 将 ast.parse 放入线程池避免阻塞
    def _parse():
        tree = ast.parse(content)
        items = []
        class_methods = set()  # P1: 避免方法在顶层+类内重复出现
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.ClassDef):
                children = []
                for n in ast.walk(node):
                    if isinstance(n, ast.FunctionDef):
                        class_methods.add(n.name)
                        children.append(OutlineNode(name=n.name, kind="method", line=n.lineno))
                items.append(
                    OutlineNode(name=node.name, kind="class", line=node.lineno, children=children)
                )
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.FunctionDef) and node.name not in class_methods:
                items.append(OutlineNode(name=node.name, kind="function", line=node.lineno))
        return sorted(items, key=lambda x: x.line)

    return await asyncio.to_thread(_parse)


@router.get("/hover")
async def get_hover_info(symbol: str = Query(...)):
    """悬停信息——从 CodeGraph meta 取类型签名。"""
    if _code_graph is None:
        return None
    try:
        exists = await _code_graph.exists(symbol)
        return f"**{symbol}**" if exists else None
    except (RuntimeError, ValueError):
        return None
