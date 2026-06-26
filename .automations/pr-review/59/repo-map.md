# PR Repo Map — #59

## PR Summary
- **PR**: #59
- **Title**: refactor: 模型体系重构——DS V4 Pro/Flash + GLM-5.2 + GLM-4.7 Flash 降级
- **Files Changed**: 18
- **Comments**: 8
- **Reviews**: 0

## Changed Files by Category

### Tests (9)
- tests/e2e/conftest.py
- tests/e2e/test_e2e_circuit_breaker.py
- tests/perf/conftest.py
- tests/unit/test_coverage_boost.py
- tests/unit/test_dev_pipeline.py
- tests/unit/test_integration_glue.py
- tests/unit/test_pr1_coverage.py
- tests/unit/test_resource_guard.py
- tests/unit/test_scheduler.py

### Docs (2)
- AGENTS.md
- CLAUDE.md

### Other (7)
- docker-compose.yml
- src/orbit/api/main.py
- src/orbit/core/config.py
- src/orbit/gateway/client.py
- src/orbit/hallucination/schemas.py
- src/orbit/resource_guard/degradation.py
- src/orbit/scheduler/orchestrator.py

## Permission Scan Summary

✅ 权限扫描未发现异常

详见 `rule-scan.md`。

## ⚠️ Historical Gotcha

**require_permission 权限字符串问题已反复出现 5 次**: PR#73 → #75 → #78 → #83 → #84。

Reviewer 必须检查:
1. 新增写端点是否都有 `require_permission` 保护？
2. 权限字符串拼写是否正确（module:action 格式）？
3. 权限是否在 `rbac.py` 和 seed 数据中注册？
4. 测试是否覆盖未授权/无权限场景？

## Suggested Reviewer Focus

1. **权限字符串是否正确** —— 每个新增/修改端点是否有匹配的 `require_permission`？
2. **API endpoint 是否有权限保护** —— 写端点必须有 RBAC，只读端点是否合理暴露？
4. **测试是否覆盖负向权限场景** —— 未授权用户是否返回 403？