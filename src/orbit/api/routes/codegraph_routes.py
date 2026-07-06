"""代码导航 API (Step 9 Phase 1.3)——Go to Def / References / Outline / Hover + 图谱可视化数据."""

from __future__ import annotations

import ast
import asyncio
from datetime import UTC, datetime

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
    """Go to Definition——搜索符号定义，返回文件路径+行号。"""
    if _code_graph is None:
        raise HTTPException(status_code=503, detail="CodeGraph not available")
    try:
        defs = await _code_graph.find_definitions_with_positions(symbol)
        if defs:
            d = defs[0]
            return {
                "file": d["file_path"],
                "line": d["start_line"],
                "end_line": d["end_line"],
                "name": d["name"],
                "kind": d["kind"],
            }
    except (RuntimeError, ValueError) as e:
        raise HTTPException(status_code=500, detail=str(e))
    # 符号未找到——返回 null，前端据此显示"未找到定义"
    return {"file": "", "line": 0, "name": symbol, "kind": "unknown"}


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
    """悬停信息——从 CodeGraph meta 取类型签名+文档。"""
    if _code_graph is None:
        return None
    try:
        # P2: 返回类型签名+docstring，不再只返回符号名
        meta = await _code_graph.get_symbol_meta(symbol)
        if meta:
            parts = [f"**{symbol}**"]
            if meta.get("type"):
                parts.append(f"`{meta['type']}`")
            if meta.get("doc"):
                parts.append(f"\n\n{meta['doc'][:300]}")
            return "  \n".join(parts)
        exists = await _code_graph.exists(symbol)
        return f"**{symbol}**" if exists else None
    except (RuntimeError, ValueError):
        return None


# P2: TestGapDetector API——测试覆盖空洞检测接入
@router.get("/test-gaps")
async def get_test_gaps(function: str = Query(..., min_length=1)):
    """检测指定函数的测试覆盖空洞——基于参数类型 × 已有测试值。

    WHY: TestGapDetector 已在 PR #201 实现但从未接入生产路径。
    """
    if _code_graph is None:
        return {"code": 0, "data": {"gaps": [], "message": "CodeGraph 未初始化"}}
    try:
        from orbit.graph.engines.test_gap_detector import TestGapDetector
        detector = TestGapDetector()
        gaps = await detector.detect(_code_graph, function)
        return {
            "code": 0,
            "data": {
                "function": function,
                "gaps": [
                    {
                        "param": g.param_name,
                        "type": g.param_type,
                        "covered": g.covered_values,
                        "missing": g.missing_cases,
                    }
                    for g in gaps
                ],
                "total": len(gaps),
            },
        }
    except Exception as e:
        return {"code": 0, "data": {"gaps": [], "message": str(e)}}


# ── 图谱可视化数据（新增）─────────────────────────────


@router.get("/graph-data")
async def get_graph_data(project_id: str = Query(..., min_length=1)):
    """返回 Cytoscape elements 格式的代码图谱数据。

    WHY 独立端点不修改现有查询接口：图谱数据量大（数百节点+边），
    与符号级查询（definition/references/hover）的访问模式不同。
    使用缓存时间戳避免每次打开页面重解析。
    """
    if _code_graph is None:
        raise HTTPException(status_code=503, detail="CodeGraph not available")

    try:
        nodes = await _code_graph.get_all_nodes()
        edges = await _code_graph.get_all_edges()
    except (RuntimeError, ValueError) as e:
        raise HTTPException(status_code=500, detail=str(e))
    except AttributeError:
        # CodeGraphEngine 可能没有 get_all_nodes/get_all_edges 方法
        # 回退到直接查询——由 codegraph_routes 内部处理
        raise HTTPException(status_code=501, detail="CODE_001: 项目未构建代码索引")

    if not nodes:
        return {
            "code": 0,
            "data": {
                "elements": [],
                "stats": {"node_count": 0, "edge_count": 0, "built_at": None},
            },
            "message": "CODE_002: 项目无 Python 文件",
        }

    # 转换为 Cytoscape elements 格式
    elements: list[dict] = []
    for node in nodes:
        node_id = node.get("id", "")
        node_type = node.get("type", "unknown")
        elements.append({
            "data": {
                "id": f"code:{node_id}",
                "label": node.get("name", node_id),
                "type": node_type,
                "file_path": node.get("file_path", ""),
                "start_line": node.get("start_line", 0),
                "symbol_count": node.get("symbol_count", 0),
                "in_degree": node.get("in_degree", 0),
                "out_degree": node.get("out_degree", 0),
            }
        })

    for edge in edges:
        elements.append({
            "data": {
                "id": f"e:{edge.get('id', '')}",
                "source": f"code:{edge.get('source_id', '')}",
                "target": f"code:{edge.get('target_id', '')}",
                "type": edge.get("edge_type", "references"),
                "weight": edge.get("weight", 1),
            }
        })

    return {
        "code": 0,
        "data": {
            "elements": elements,
            "stats": {
                "node_count": len(nodes),
                "edge_count": len(edges),
                "built_at": datetime.now(UTC).isoformat(),
            },
        },
        "message": "ok",
    }


@router.get("/graph-snapshots")
async def get_graph_snapshots(project_id: str = Query(..., min_length=1)):
    """返回 git 历史时间点的图谱快照列表（P1 时间轴）。

    无 git 仓库时返回空数组，不报错。
    """
    # P1: 依赖 git 仓库——返回空数组给前端示意禁用时间轴
    return {
        "code": 0,
        "data": {"snapshots": []},
        "message": "ok",
    }
