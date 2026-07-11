"""LSP 诊断 HTTP API 路由——前端 ProblemPanel 一次性拉取 mypy 诊断。

WHY: 前端 diagnostics store 走一次性 HTTP GET（非 WS 订阅），需 /api/v1/lsp 前缀。
复用与 WS 端点(diagnostics_ws)同一个 DiagnosticService 实例，两者共存不冲突。
"""

from __future__ import annotations

from fastapi import APIRouter, Query

from orbit.lsp.service import DiagnosticService

router = APIRouter(prefix="/lsp", tags=["lsp"])
_diagnostic_service: DiagnosticService | None = None


def set_diagnostic_service(svc: DiagnosticService) -> None:
    global _diagnostic_service
    _diagnostic_service = svc


@router.get("/diagnostics")
async def get_diagnostics(
    task_id: str = Query(..., description="任务 ID（仅用于前端关联，不影响诊断结果）"),
    file: str | None = Query(None, description="指定文件，为空则返回空结果"),
):
    """HTTP 一次性拉取指定文件的 mypy 诊断结果。

    P2-3: 返回扁平 {diagnostics: {file: [...]}} 而非项目统一的 {code,data,message}。
    这是前端契约——diagnostics store 直接读 data.diagnostics（见 stores/diagnostics.ts），
    改成包装格式会破坏前端解析，故有意保留扁平结构。
    """
    if _diagnostic_service is None:
        return {"diagnostics": {}}
    files = [file] if file else []
    results = await _diagnostic_service.get_diagnostics(files) if files else {}
    return {"diagnostics": results}
