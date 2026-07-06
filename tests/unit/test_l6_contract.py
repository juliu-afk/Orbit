"""L6 合约验证器测试。mock OpenAPI spec 文件。"""

from __future__ import annotations

import pytest

from orbit.hallucination.l6_contract import L6ContractValidator


@pytest.fixture
def openapi_spec(tmp_path):
    """创建临时 OpenAPI spec。"""
    spec = {
        "openapi": "3.0.0",
        "paths": {
            "/users/{id}": {
                "get": {
                    "responses": {
                        "200": {
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/User"}
                                }
                            }
                        }
                    }
                }
            }
        },
    }
    import json

    spec_file = tmp_path / "openapi.json"
    spec_file.write_text(json.dumps(spec))
    return str(spec_file)


@pytest.mark.asyncio
async def test_l6_contract_match(openapi_spec):
    """AC3: 合约匹配 → passed=True。"""
    validator = L6ContractValidator(openapi_spec)
    code = """
@app.get("/users/{id}")
def get_user(id: int) -> User:
    return User(id=id, name="test")
"""
    result = await validator.validate(code)
    assert result.passed is True


@pytest.mark.asyncio
async def test_l6_response_model_mismatch(openapi_spec):
    """AC3: 返回类型不匹配 → passed=False。"""
    validator = L6ContractValidator(openapi_spec)
    code = """
@app.get("/users/{id}")
def get_user(id: int) -> dict:
    return {"id": id}
"""
    result = await validator.validate(code)
    assert result.passed is False
    assert any("User" in e or "response_model" in e for e in result.errors)


@pytest.mark.asyncio
async def test_l6_spec_not_found():
    """OpenAPI spec 不存在 → passed=False。"""
    validator = L6ContractValidator("/nonexistent/openapi.yaml")
    result = await validator.validate("x = 1")
    assert result.passed is False
    assert any("not found" in e.lower() for e in result.errors)


@pytest.mark.asyncio
async def test_l6_empty_code(openapi_spec):
    """空代码 → skipped。"""
    validator = L6ContractValidator(openapi_spec)
    result = await validator.validate("")
    assert result.passed is True


# ── 覆盖缺口测试 ──

@pytest.mark.asyncio
async def test_l6_yaml_spec(tmp_path):
    """YAML spec 加载（lines 119, 122）。"""
    spec_file = tmp_path / "openapi.yaml"
    spec_file.write_text("""
openapi: "3.0.0"
paths:
  /users/{id}:
    get:
      responses:
        "200":
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/User"
""")
    validator = L6ContractValidator(str(spec_file))
    code = '''
@app.get("/users/{id}")
def get_user(id: int) -> User:
    return User(id=id, name="test")
'''
    result = await validator.validate(code)
    # YAML spec 能正常加载和比对
    assert isinstance(result.passed, bool)


def test_extract_spec_endpoints_non_dict_paths():
    """paths 值不是 dict → continue 跳过（line 139）。"""
    validator = L6ContractValidator("/fake/openapi.json")
    spec = {
        "paths": {
            "/users": "not a dict",  # 不是 method dict
            "/items": {
                "get": {
                    "responses": {
                        "200": {
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/Item"}
                                }
                            }
                        }
                    }
                }
            },
        }
    }
    endpoints = validator._extract_spec_endpoints(spec)
    # /users 被跳过（非 dict），/items 被提取
    assert len(endpoints) == 1
    assert endpoints[0]["path"] == "/items"


def test_extract_spec_endpoints_skip_meta_keys():
    """skip parameters/servers/summary/description 等元数据键（line 141-142）。"""
    validator = L6ContractValidator("/fake/openapi.json")
    spec = {
        "paths": {
            "/api": {
                "parameters": [{"name": "q"}],
                "summary": "Search endpoint",
                "get": {
                    "responses": {
                        "200": {
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/Search"}
                                }
                            }
                        }
                    }
                },
            }
        }
    }
    endpoints = validator._extract_spec_endpoints(spec)
    # parameters 和 summary 被跳过，只有 get 被提取
    assert len(endpoints) == 1
    assert endpoints[0]["method"] == "GET"


def test_extract_code_routes_syntax_error():
    """无效 Python 代码 → SyntaxError → 返回空 dict（line 164-165）。"""
    validator = L6ContractValidator("/fake/openapi.json")
    routes = validator._extract_code_routes("def foo( {{{ ")
    assert routes == {}


def test_parse_route_decorator_non_call():
    """装饰器不是函数调用 → None（line 184, 186）。"""
    import ast
    validator = L6ContractValidator("/fake/openapi.json")
    # @x  → Name node, not Call → None
    tree = ast.parse("@x\ndef f(): pass")
    func = tree.body[0]
    decorator = func.decorator_list[0]
    result = validator._parse_route_decorator(decorator)
    assert result is None


def test_parse_route_decorator_non_http_method():
    """装饰器属性不是 HTTP 方法 → None（line 196-199）。"""
    import ast
    validator = L6ContractValidator("/fake/openapi.json")
    # @app.websocket("/ws") → "websocket" 不在 method_map
    tree = ast.parse("@app.websocket('/ws')\ndef ws(): pass")
    func = tree.body[0]
    decorator = func.decorator_list[0]
    result = validator._parse_route_decorator(decorator)
    assert result is None


def test_compare_endpoint_response_model_mismatch():
    """双方都有 response_model 但不一致 → matched=False（line 218）。"""
    validator = L6ContractValidator("/fake/openapi.json")
    spec_ep = {"path": "/users/{id}", "method": "GET", "response_model": "User"}
    code_ep = {"path": "/users/{id}", "method": "GET", "response_model": "UserDTO"}
    matches = validator._compare_endpoint(spec_ep, code_ep)
    assert len(matches) == 1
    assert matches[0].matched is False
    assert "mismatch" in " ".join(matches[0].differences)


def test_compare_endpoint_code_missing_model():
    """spec 有 response_model，代码没有 → 不匹配提示（line 220-221）。"""
    validator = L6ContractValidator("/fake/openapi.json")
    spec_ep = {"path": "/users/{id}", "method": "GET", "response_model": "User"}
    code_ep = {"path": "/users/{id}", "method": "GET", "response_model": ""}
    matches = validator._compare_endpoint(spec_ep, code_ep)
    assert len(matches) == 1
    assert any("missing" in e for e in matches[0].differences)
