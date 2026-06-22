"""L6 合约验证器测试。mock OpenAPI spec 文件。"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from orbit.hallucination.l6_contract import L6ContractValidator
from orbit.hallucination.schemas import HallucinationLevel


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
    code = '''
@app.get("/users/{id}")
def get_user(id: int) -> User:
    return User(id=id, name="test")
'''
    result = await validator.validate(code)
    assert result.passed is True


@pytest.mark.asyncio
async def test_l6_response_model_mismatch(openapi_spec):
    """AC3: 返回类型不匹配 → passed=False。"""
    validator = L6ContractValidator(openapi_spec)
    code = '''
@app.get("/users/{id}")
def get_user(id: int) -> dict:
    return {"id": id}
'''
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
