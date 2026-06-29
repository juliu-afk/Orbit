"""代码导航 API (Step 9 Phase 1.3)——Go to Def / References / Outline / Hover."""
from __future__ import annotations
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

router = APIRouter(prefix="/codegraph", tags=["codegraph"])

# 引擎由 main.py 注入
_code_graph = None
_file_service = None

def set_code_graph(engine) -> None:
    global _code_graph; _code_graph = engine

def set_file_service(svc) -> None:
    global _file_service; _file_service = svc

class SymbolRef(BaseModel):
    name: str; file: str; line: int; kind: str

class OutlineNode(BaseModel):
    name: str; kind: str; line: int; children: list[OutlineNode] = []


@router.get("/definition")
async def go_to_definition(symbol: str = Query(...), file: str = Query("")):
    """Go to Definition——搜索符号定义。复用 CodeGraph 的目录扫描+AST。"""
    if _code_graph is None:
        raise HTTPException(status_code=503, detail="CodeGraph not available")
    try:
        defs = await _code_graph.find_definitions_cross_file(symbol)
        if defs:
            return {"file": defs[0], "line": 1, "name": symbol, "kind": "function"}
    except Exception:
        pass
    return None


@router.get("/references")
async def find_references(symbol: str = Query(...)):
    """Find All References——通过 call 边反向查引用。"""
    if _code_graph is None:
        raise HTTPException(status_code=503, detail="CodeGraph not available")
    try:
        callers = await _code_graph.get_callers(symbol)
        return [{"name": c, "file": "", "line": 1, "kind": "function"} for c in callers]
    except Exception:
        return []


@router.get("/outline")
async def get_outline(file: str = Query(...)):
    """文件大纲——对 Python 文件做 AST 解析提取函数/类。"""
    import ast
    from pathlib import Path
    try:
        # 直接用 AST 解析，不依赖 CodeGraph
        if _file_service:
            content = await _file_service.read_file(file)
        else:
            content = Path(file).read_text(encoding="utf-8")
        tree = ast.parse(content)
        items = []
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                items.append(OutlineNode(name=node.name, kind="function", line=node.lineno))
            elif isinstance(node, ast.ClassDef):
                children = [OutlineNode(name=n.name, kind="method", line=n.lineno)
                    for n in ast.walk(node) if isinstance(n, ast.FunctionDef) and n != node]
                items.append(OutlineNode(name=node.name, kind="class", line=node.lineno, children=children))
        return sorted(items, key=lambda x: x.line)
    except Exception:
        return []


@router.get("/hover")
async def get_hover_info(symbol: str = Query(...)):
    """悬停信息——从 CodeGraph meta 取类型签名。"""
    if _code_graph is None:
        return None
    try:
        exists = await _code_graph.exists(symbol)
        return f"**{symbol}**" if exists else None
    except Exception:
        return None
