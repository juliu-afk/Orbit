"""L6 合约-代码双向验证器（Step 4.2）。

WHY L6：OpenAPI 规格定义 API 契约（请求/响应模型、状态码），
但 LLM 生成的实现可能偏离契约——返回 dict 而非 Pydantic 模型、
缺失状态码等。L6 解析 OpenAPI spec 并与代码实现逐端点比对。

实现：prance 解析 OpenAPI 3.0 规格 → 提取端点/方法/模型 → AST 分析
路由代码 → 比对 response_model 类型名。

限制（PRD）：仅支持 OpenAPI 3.0，不支持 gRPC。
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

import structlog

from orbit.hallucination.schemas import (
    HallucinationLevel,
    L6ContractMatch,
    ValidationResult,
)

logger = structlog.get_logger()


class L6ContractValidator:
    """L6 OpenAPI 合约双向验证器。

    用法：
        validator = L6ContractValidator(openapi_path="openapi.yaml")
        result = await validator.validate(code)
        if not result.passed:
            # result.metadata["violations"] 含不匹配端点
            ...
    """

    def __init__(self, openapi_path: str):
        self._spec_path = Path(openapi_path)
        self._spec: dict[str, Any] | None = None  # 缓存解析结果

    async def validate(self, code: str) -> ValidationResult:
        """比对代码实现与 OpenAPI 规格。

        Args:
            code: 含 FastAPI 路由定义的代码

        Returns:
            ValidationResult：passed=False 存在不一致
        """
        if not code.strip():
            return ValidationResult(
                passed=True,
                level=HallucinationLevel.L6_CONTRACT,
                warnings=["empty code, skipped"],
            )

        # 解析 OpenAPI spec
        spec = await self._load_spec()
        if spec is None:
            return ValidationResult(
                passed=False,
                level=HallucinationLevel.L6_CONTRACT,
                errors=[f"OpenAPI spec not found: {self._spec_path}"],
            )

        # 提取 spec 定义的端点
        spec_endpoints = self._extract_spec_endpoints(spec)

        # 提取代码中定义的路由
        code_endpoints = self._extract_code_routes(code)

        # 比对
        violations: list[L6ContractMatch] = []
        for ep in spec_endpoints:
            key = (ep["path"], ep["method"])
            if key in code_endpoints:
                code_ep = code_endpoints[key]
                matches = self._compare_endpoint(ep, code_ep)
                violations.extend([m for m in matches if not m.matched])
            # NOTE: spec 中定义但代码未实现的端点不报错（可能是其他文件定义）

        if violations:
            return ValidationResult(
                passed=False,
                level=HallucinationLevel.L6_CONTRACT,
                errors=[
                    f"Contract violation: {v.endpoint} {v.method} - {'; '.join(v.differences)}"
                    for v in violations
                ],
                metadata={"violations": [v.model_dump() for v in violations]},
            )

        return ValidationResult(
            passed=True,
            level=HallucinationLevel.L6_CONTRACT,
            metadata={"checked_endpoints": len(spec_endpoints)},
        )

    async def _load_spec(self) -> dict[str, Any] | None:
        """加载 OpenAPI spec（缓存结果）。"""
        if self._spec is not None:
            return self._spec
        if not self._spec_path.exists():
            return None
        try:
            import json

            import yaml

            content = self._spec_path.read_text(encoding="utf-8")
            if self._spec_path.suffix in (".yaml", ".yml"):
                self._spec = yaml.safe_load(content)
            else:
                self._spec = json.loads(content)
            return self._spec
        except Exception as e:
            logger.warning("l6_spec_load_failed", path=str(self._spec_path), error=str(e))
            return None

    def _extract_spec_endpoints(self, spec: dict) -> list[dict[str, Any]]:
        """从 OpenAPI 3.0 spec 提取端点列表。

        返回 [{"path": "/users/{id}", "method": "get", "response_model": "User"}, ...]
        """
        endpoints: list[dict[str, Any]] = []
        paths = spec.get("paths", {})
        for path_url, methods in paths.items():
            if not isinstance(methods, dict):
                continue
            for method, details in methods.items():
                if method in ("parameters", "servers", "summary", "description"):
                    continue
                resp_model = ""
                responses = details.get("responses", {})
                if "200" in responses:
                    content = responses["200"].get("content", {})
                    json_schema = content.get("application/json", {})
                    ref = json_schema.get("schema", {}).get("$ref", "")
                    resp_model = ref.split("/")[-1] if ref else ""
                endpoints.append(
                    {
                        "path": path_url,
                        "method": method.upper(),
                        "response_model": resp_model,
                    }
                )
        return endpoints

    def _extract_code_routes(self, code: str) -> dict[str, Any]:
        """从代码中 AST 提取 FastAPI 路由定义。

        返回 {(path, method): {"response_model": str, ...}}
        """
        routes: dict[tuple[str, str], dict] = {}
        try:
            tree = ast.parse(code)
        except SyntaxError:
            return routes

        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                for decorator in node.decorator_list:
                    info = self._parse_route_decorator(decorator)
                    if info:
                        # 从返回注解推断 response_model
                        if node.returns and isinstance(node.returns, ast.Name):
                            info["response_model"] = node.returns.id
                        routes[(info["path"], info["method"])] = info
        return routes

    def _parse_route_decorator(self, decorator: ast.AST) -> dict[str, Any] | None:
        """解析 FastAPI 路由装饰器。

        @app.get("/users/{id}") → {"path": "/users/{id}", "method": "GET"}
        """
        if not isinstance(decorator, ast.Call):
            return None
        if not isinstance(decorator.func, ast.Attribute):
            return None
        method_map = {
            "get": "GET",
            "post": "POST",
            "put": "PUT",
            "delete": "DELETE",
            "patch": "PATCH",
        }
        method = method_map.get(decorator.func.attr, "")
        if not method:
            return None
        path = ""
        if decorator.args:
            first = decorator.args[0]
            if isinstance(first, ast.Constant):
                path = str(first.value)
        return {"path": path, "method": method, "response_model": ""}

    def _compare_endpoint(self, spec_ep: dict, code_ep: dict) -> list[L6ContractMatch]:
        """比对单个端点。"""
        matches: list[L6ContractMatch] = []
        spec_resp = spec_ep.get("response_model", "")
        code_resp = code_ep.get("response_model", "")
        matched = True
        differences: list[str] = []

        if spec_resp and code_resp and spec_resp != code_resp:
            matched = False
            differences.append(f"response_model mismatch: spec={spec_resp}, code={code_resp}")
        elif spec_resp and not code_resp:
            differences.append("code missing response_model type annotation")

        matches.append(
            L6ContractMatch(
                endpoint=spec_ep["path"],
                method=spec_ep["method"],
                request_model="",
                response_model=spec_resp,
                matched=matched,
                differences=differences,
            )
        )
        return matches
